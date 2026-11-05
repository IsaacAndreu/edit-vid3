"""Automatic dubbing: every finished video, also in other languages, for a second channel per language.

OFF by default (`dubbing.enabled: false`): turn it on per channel (canales/<canal>.yaml) when you have the channel in
the other language. Then, for each finished video of that channel and each `dubbing.languages` (e.g. [en]):
1. the script is translated (guion-<lang>.txt, `## ` chapters included, adapted for narration, not word for word),
   and the working title (titulo-<lang>.txt);
2. GenAIPro reads it with the channel's voice for that language (`dubbing.voices.<lang>`: voice_id, model…) into
   voz-<lang>.mp3, with its word timings (no Whisper later);
3. the queue's dub (pipeline/dub.py) does the rest by itself: <video>-<lang>/ with the same clips and order retimed
   to the new voice, every on-screen text translated (chapters, places, labels, panels, graphics), then QA, render,
   Shorts and titles in that language.
Cost: one cheap LLM call for the translation and the GenAIPro characters of the narration (as much as the original).

    dubbing:
      enabled: true
      languages: [en]
      voices:
        en: {voice_id: "…", model_id: eleven_multilingual_v2, name: "Narrator EN"}
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .context import RunContext

TRANSLATE_SYSTEM = """
Eres traductor y guionista de documentales de YouTube. Traduce el guion al {language} para que lo lea una voz en off
nativa: natural, con el mismo ritmo, gancho y tono, frases cortas, sin notas ni acotaciones. Mantén las líneas
«## TÍTULO» como líneas de capítulo (traduce el título, en MAYÚSCULAS). Los nombres propios se quedan; las cifras,
fechas y unidades se escriben como se dicen en {language} (dinero en la moneda original). Traduce también el título.
ESCRIBE EL GUION ENTERO EN {language}: ni una sola frase en español (la leerá una voz nativa de ese idioma).
Devuelve SOLO JSON: {"title": "título traducido", "script": "el guion traducido"}.
""".strip()

ADAPT_SYSTEM = """
Eres guionista nativo de YouTube para este público: {audience}. Recibes el guion de un vídeo explicativo en español.
NO lo traduzcas sin más: ADÁPTALO al {language} para que parezca hecho para ellos. El guion que devuelves está ENTERO
en {language} (lo lee una voz nativa): ni una frase en español, no un guion en español con palabras sueltas en
{language}. Solo la lista de cambios va en español.
{guide}
Reglas:
- Cambia los ejemplos cotidianos por los de allí (carreteras, tiendas, marcas, horarios, costumbres) y las monedas y
  unidades por las suyas (convierte la cifra, no inventes una nueva).
- Un caso local muy conocido que venga a cuento (un apagón, un atasco famoso, un estudio de allí) puede añadirse en
  1-2 frases, SOLO si estás seguro de los hechos (año, lugar, qué pasó) y sin cifras dudosas; si dudas, no lo pongas.
- Lo que se ve en pantalla es la misma simulación: no cambies lo que la voz describe de ella («este coche frena», «la
  cola de la izquierda»), ni las cifras que salen de ella, ni los estudios citados.
- La misma estructura, gancho, giro y cierre; la duración casi igual (±10 %). Mantén las líneas «## TÍTULO».
- Frases cortas, natural para leer en voz alta, sin notas ni acotaciones.
- Números como se escriben allí (decimal con coma en alemán, francés y portugués: 3,5; en francés los miles con
  espacio: 10 000). Una cifra que la voz pueda leer mal (decimales, años, porcentajes raros), escríbela en palabras.
Devuelve SOLO JSON: {{"title": "título adaptado", "script": "el guion adaptado", "changes": ["cada adaptación que hiciste, en español"]}}
""".strip()

# who each language speaks to, unless the target channel says it (`localize:` in its profile)
AUDIENCES = {"en": "Estados Unidos (y quien vea en inglés)", "pt": "Brasil", "de": "Alemania, Austria y Suiza",
             "fr": "Francia (y la francofonía)", "it": "Italia"}


def localize(ctx: RunContext, lang: str) -> tuple[str, str] | None:
    """(audience, guide) to adapt a script to a language's viewers: the `localize:` of the channel the dub goes to
    (canales/<canal>.yaml), else, for a simulation channel, a plain one; None: a plain translation."""

    target = settings(ctx)["channels"].get(lang)
    guide = ""
    if target:
        try:
            guide = str(RunContext.create("_adapta", root=ctx.root, channel=target).config.get("localize") or "").strip()
        except Exception:
            guide = ""
    if not guide and not _drawn(ctx):
        return None
    return AUDIENCES.get(lang, lang), guide


def _drawn(ctx: RunContext) -> bool:
    """Simulations, stickman films and maps: the same picture in every language, a native voice per language."""

    from . import atlas, cine, mapas, simulacion

    return simulacion.active(ctx) or cine.active(ctx) or mapas.active(ctx) or atlas.active(ctx)


# the language as the prompts (in Spanish) name it
IN_SPANISH = {"en": "inglés", "pt": "portugués de Brasil", "fr": "francés", "it": "italiano", "de": "alemán", "es": "español"}
# the commonest short words of each language: enough to tell a script's language
STOPWORDS = {
    "es": "el la los las de del que y en un una es por con para no se lo su al como más pero sus le ya o este porque esta entre cuando muy sin sobre también",
    "de": "der die das und ist nicht ein eine zu den mit sich des auf für von dem im auch es an werden aus er hat dass sie nach wird bei noch wie",
    "en": "the and of to a in is that it for was on are with as his they be at one have this from by but not what all were when we",
    "pt": "o a os as de do da que e em um uma é para com não se no na por mais mas como dos das ao seu sua ou quando muito também",
    "fr": "le la les de des du et est un une que qui en pour pas ne se sur au avec dans ce il plus par mais ou sont aussi comme",
    "it": "il lo la i gli le di del della che e è un una per non con si in al dei come ma più anche sono questo nel alla",
}
_WORDS = {k: set(v.split()) for k, v in STOPWORDS.items()}


def language_of(text: str) -> str:
    """The language a script is written in (by its short common words); '' if too short to tell."""

    import re

    words = re.findall(r"[a-záéíóúàèìòùâêôãõçäöüßñ]+", text.lower())
    if len(words) < 30:
        return ""
    scores = sorted(((sum(1 for w in words if w in common), lang) for lang, common in _WORDS.items()), reverse=True)
    (best, lang), (second, _) = scores[0], scores[1]
    # sure only with enough little words and a clear winner (Spanish and Portuguese share many)
    return lang if best >= max(5, 0.08 * len(words)) and best >= 1.25 * second else ""


NAMES = {"en": "English", "pt": "Portuguese (Brazil)", "fr": "French", "it": "Italian", "de": "German"}


def settings(ctx: RunContext) -> dict[str, Any]:
    """`dubbing:` of the channel profile, or what the studio's «Voces por canal → Doblaje» set for this channel (that
    wins). A language without its own voice is read by the channel's voice with the multilingual model."""

    from . import tts

    cfg = ctx.section("dubbing")
    out = {"enabled": bool(cfg.get("enabled", False)), "languages": [str(l) for l in cfg.get("languages", ["en"])],
           "voices": dict(cfg.get("voices") or {}), "existing": True, "since": 0.0,
           "channels": {str(k): str(v) for k, v in (cfg.get("channels") or {}).items() if v}}
    channel = str(ctx.config.get("canal") or "")
    studio = tts.dubbing_for(ctx.root, channel) if channel else {}
    if studio:
        out.update(enabled=True, languages=list(studio["languages"]), existing=bool(studio.get("existing", True)),
                   since=float(studio.get("since") or 0))
        out["voices"].update({l: v for l, v in (studio.get("voices") or {}).items() if v.get("voice_id")})
    if _drawn(ctx):
        # a simulation channel (or a stickman film or a map: drawn in code too) dubs only with a GenAIPro voice of that language: the voice of the channel it goes to
        # (simulated-why's for English…) or the studio's «Doblaje» voice for it — never the Spanish voice reading it
        for lang in list(out["languages"]):
            target = out["channels"].get(lang)
            spec = dub_voice(ctx.root, target, (out["voices"].get(lang) or {}))
            if spec:
                out["voices"][lang] = spec
            else:
                out["voices"].pop(lang, None)
        out["languages"] = [l for l in out["languages"] if (out["voices"].get(l) or {}).get("voice_id")]
        # the languages switched off for this video (unticked in «Nuevo vídeo», or «No doblar» on its page). Only an
        # explicit «no» counts: a language that had no voice yet when the video was made is dubbed once it has one
        # (the old `dub_languages` kept what was ticked, so German, greyed out then, was never dubbed)
        out["offered"] = list(out["languages"])
        out["languages"] = [l for l in out["languages"] if l not in skipped(ctx)]
        out["enabled"] = out["enabled"] and bool(out["languages"])
        return out
    own = tts.voice_for(ctx.root, channel) if channel else None
    for lang in out["languages"]:
        if not (out["voices"].get(lang) or {}).get("voice_id") and own:
            out["voices"][lang] = {**own, "model_id": "eleven_multilingual_v2" if own.get("model_id") in
                                   ("eleven_turbo_v2_5", "eleven_flash_v2_5", None) else own["model_id"]}
    return out


SKIP = ".no-doblar-{lang}"           # in the video's folder: never dub it to that language
FORCE = ".doblar-{lang}"              # in the video's folder: dub it although it is older than «solo vídeos nuevos»


def skipped(ctx: RunContext) -> list[str]:
    folder = ctx.materials_dir
    listed = [str(l) for l in ctx.config.get("dub_skip") or []]
    return [l for l in NAMES if l in listed or (folder / SKIP.format(lang=l)).is_file()]


def choose(root: Path, slug: str, lang: str, on: bool) -> dict[str, Any]:
    """«Doblar a …» / «No doblar a …» on the video's page: also a video older than the dubbing setting, or one whose
    language was unticked when it was made."""

    from .context import find_video

    folder = find_video(root, slug)
    if not folder.is_dir():
        raise FileNotFoundError(slug)
    skip, force = folder / SKIP.format(lang=lang), folder / FORCE.format(lang=lang)
    if on:
        skip.unlink(missing_ok=True)
        force.write_text("", encoding="utf-8")
        (folder / "doblaje.error").unlink(missing_ok=True)      # try now, not in 6 h
        config = folder / "config.yaml"
        if config.is_file():                                     # the «Nuevo vídeo» list: drop this language from it
            import yaml

            data = yaml.safe_load(config.read_text("utf-8")) or {}
            if lang in [str(l) for l in data.get("dub_skip") or []]:
                data["dub_skip"] = [l for l in data["dub_skip"] if str(l) != lang]
                config.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    else:
        force.unlink(missing_ok=True)
        skip.write_text("", encoding="utf-8")
    return {"ok": True}


def dub_voice(root: Path, target: str | None, given: dict[str, Any]) -> dict[str, Any] | None:
    """The GenAIPro voice for a language: the target channel's own (not its base's: that one speaks Spanish), else
    the one set for that language in «Doblaje»; None when there is none."""

    from . import tts

    if target:
        own = tts.voices(root).get(target)
        if own and own.get("voice_id"):
            return own
    return {**tts.DEFAULTS, **given} if given.get("voice_id") else None


def options(root: Path, channel: str) -> list[dict[str, Any]]:
    """For «Nuevo vídeo»: the languages a simulation channel can dub to, each with the voice it would use (or none)."""

    ctx = RunContext.create("_doblaje", root=root, channel=channel)
    cfg = ctx.section("dubbing")
    channels = {str(k): str(v) for k, v in (cfg.get("channels") or {}).items() if v}
    from . import tts

    studio = tts.dubbing_for(root, channel)
    langs = list(dict.fromkeys([*(str(l) for l in cfg.get("languages") or []), *(studio.get("languages") or [])]))
    voices = {**dict(cfg.get("voices") or {}), **(studio.get("voices") or {})}
    out = []
    for lang in langs:
        spec = dub_voice(root, channels.get(lang), voices.get(lang) or {})
        out.append({"lang": lang, "name": NAMES.get(lang, lang), "channel": channels.get(lang),
                    "voice": (spec or {}).get("name") or ((spec or {}).get("voice_id") or "")[:12] or None})
    return out


def translate(ctx: RunContext, lang: str) -> bool:
    """guion-<lang>.txt and titulo-<lang>.txt from the original (once). True if written now."""

    from .llm import complete_json

    folder = ctx.materials_dir
    target = folder / f"guion-{lang}.txt"
    if target.is_file():
        return False
    script = (folder / "guion.txt").read_text("utf-8")
    title_file = folder / "titulo.txt"
    title = title_file.read_text("utf-8").strip() if title_file.is_file() else ""
    language = IN_SPANISH.get(lang, NAMES.get(lang, lang))
    local = localize(ctx, lang)
    system = (ADAPT_SYSTEM.format(audience=local[0], language=language, guide=local[1]) if local
              else TRANSLATE_SYSTEM.replace("{language}", language))
    result: dict[str, Any] = {}
    text = ""
    for attempt in range(2):
        # a script «adapted» in Spanish with a few words of the other language (sim3 into German: Handy, U-Bahn,
        # Ampeln in Spanish sentences) is read by the native voice as Spanish: never accepted
        extra = "" if not attempt else (f"\n\nATENCIÓN: la vez anterior devolviste el guion en español. Escríbelo ENTERO en "
                                        f"{language}, frase por frase.")
        result = complete_json(ctx, stage="doblaje", section="planner", max_tokens=12000, system=system + extra,
                               user=f"TÍTULO: {title or '(sin título)'}\n\nGUION:\n{script}", use_cache=attempt == 0)
        text = str(result.get("script") or "").strip()
        if language_of(text) in ("", lang[:2]):
            break
        print(f"   La adaptación al {language} salió en {IN_SPANISH.get(language_of(text), language_of(text))}: otra vez")
    else:
        raise RuntimeError(f"la adaptación al {language} no salió en {language} (dos intentos)")
    if len(text.split()) < 0.5 * len(script.split()):
        raise RuntimeError(f"la traducción al {language} salió demasiado corta")
    target.write_text(text + "\n", encoding="utf-8")
    if result.get("title"):
        (folder / f"titulo-{lang}.txt").write_text(str(result["title"]).strip() + "\n", encoding="utf-8")
    changes = [str(c) for c in result.get("changes") or [] if str(c).strip()]
    if local and changes:                  # what was adapted, to check before the voice is read (studio → Doblaje)
        (folder / f"adaptacion-{lang}.md").write_text(f"# Adaptación al {language} ({local[0]})\n\n"
                                                      + "\n".join(f"- {c}" for c in changes) + "\n", encoding="utf-8")
        print(f"   Adaptado al {language}: " + " · ".join(changes[:4]))
    return True


APPROVED = ".aprobado-{lang}"        # in the video's folder: the adapted script was checked (dubbing.review)


def waiting_review(ctx: RunContext, lang: str) -> bool:
    """`dubbing.review: true` (the first videos of a language): the voice waits until the adapted script is approved
    on the video's page (or yours is pasted there) — a native check before it is read."""

    folder = ctx.materials_dir
    return bool(ctx.section("dubbing").get("review")) and not (folder / APPROVED.format(lang=lang)).is_file() \
        and not (folder / OWN.format(lang=lang)).is_file()


def approve(root: Path, slug: str, lang: str) -> dict[str, Any]:
    from .context import find_video

    folder = find_video(root, slug)
    (folder / APPROVED.format(lang=lang)).write_text(time.strftime("%Y-%m-%dT%H:%M:%S"), encoding="utf-8")
    return {"ok": True}


def voice(ctx: RunContext, lang: str) -> bool:
    """voz-<lang>.mp3 read by GenAIPro from guion-<lang>.txt with the channel's voice for that language."""

    from . import tts

    folder = ctx.materials_dir
    if waiting_review(ctx, lang):
        return False
    target = folder / f"voz-{lang}.mp3"
    spec = (settings(ctx)["voices"] or {}).get(lang) or {}
    if target.is_file() or not spec.get("voice_id"):
        return False
    lock = folder / f".voz-{lang}.generando"
    if not tts._take(lock):
        return False
    try:
        text = tts.narration_text((folder / f"guion-{lang}.txt").read_text("utf-8"))
        found = language_of(text)
        if found and found != lang[:2]:
            raise RuntimeError(f"guion-{lang}.txt está en {IN_SPANISH.get(found, found)}, no en {IN_SPANISH.get(lang, lang)}: "
                               "no se graba (pega el bueno en la página del vídeo, o bórralo y se adapta de nuevo)")
        print(f"Doblaje {ctx.slug} → {lang}: voz con GenAIPro ({len(text)} caracteres)")
        result = tts.generate(ctx.env("GENAIPRO_API_KEY", required=False), text, {**tts.DEFAULTS, **spec}, target)
        try:
            from .costs import record_cost

            paid = result.get("paidChars", result["chars"])
            record_cost(ctx, stage="doblaje", provider="genaipro", operation=f"voz-{lang}",
                        usd=float(spec.get("usd_per_1k_chars", 0)) * paid / 1000,
                        details={"chars": paid, "lang": lang})
            if result.get("reusedChars"):
                from .ahorro import record

                record(ctx.work_dir, "voice", result["reusedChars"])
        except Exception:
            pass
        return True
    finally:
        lock.unlink(missing_ok=True)


def targets(ctx: RunContext, cfg: dict[str, Any]) -> list[str]:
    """The languages this video is dubbed to: never its own (a video made in Portuguese is not dubbed to Portuguese:
    the four gimbr videos got a second Portuguese voice from GenAIPro before this)."""

    own = str(ctx.section("align").get("language", "es"))[:2]
    return [lang for lang in cfg["languages"] if lang[:2] != own]


OWN = ".guion-{lang}.propio"          # in the video's folder: guion-<lang>.txt was pasted by you, not translated
MANUAL = "doblado-a-mano.json"         # in out/<slug>-<lang>/: you dubbed it yourself, the queue never does it


def _older(cfg: dict[str, Any], final: Path) -> bool:
    """Made before dubbing was turned on with «solo los vídeos nuevos»."""

    return bool(not cfg["existing"] and cfg["since"] and final.is_file() and final.stat().st_mtime < cfg["since"])


def _forced(folder: Path, lang: str) -> bool:
    """You asked for it on its page («Doblar a …»), or pasted its script yourself."""

    return (folder / FORCE.format(lang=lang)).is_file() or (folder / OWN.format(lang=lang)).is_file()


def status(root: Path, slug: str) -> list[dict[str, Any]]:
    """Each dubbing language of this video's channel: its script (yours or translated), voice and dubbed video."""

    from .housekeeping import is_done

    ctx = RunContext.create(slug, root=root)
    if ctx.section("dub").get("of"):
        return []
    cfg = settings(ctx)
    offered = targets(ctx, {"languages": cfg.get("offered") or (cfg["languages"] if cfg["enabled"] else [])})
    if not offered:
        return []
    folder = ctx.materials_dir
    skip = skipped(ctx)
    final = root / "out" / slug / "video-final.mp4"
    old = _older(cfg, final)
    out = []
    for lang in offered:
        dubbed = f"{slug}-{lang}"
        script = folder / f"guion-{lang}.txt"
        out.append({"lang": lang, "name": NAMES.get(lang, lang), "slug": dubbed,
                    "script": script.read_text("utf-8") if script.is_file() else "",
                    "title": (folder / f"titulo-{lang}.txt").read_text("utf-8").strip() if (folder / f"titulo-{lang}.txt").is_file() else "",
                    "own": (folder / OWN.format(lang=lang)).is_file(), "voice": (folder / f"voz-{lang}.mp3").is_file(),
                    "voiceId": bool((cfg["voices"].get(lang) or {}).get("voice_id")),
                    "manual": (root / "out" / dubbed / MANUAL).is_file(),
                    "review": waiting_review(ctx, lang) and script.is_file(),
                    "adapted": (folder / f"adaptacion-{lang}.md").read_text("utf-8") if (folder / f"adaptacion-{lang}.md").is_file() else "",
                    "skipped": lang in skip, "old": old and not _forced(folder, lang),
                    "done": is_done(root, dubbed), "error": (folder / "doblaje.error").read_text("utf-8")
                    if (folder / "doblaje.error").is_file() else ""})
    return out


def set_script(root: Path, slug: str, lang: str, script: str, title: str = "") -> dict[str, Any]:
    """Your own translation: guion-<lang>.txt (+ titulo-<lang>.txt); the voice is read from it with that language's
    voice and the dubbed video made by the queue, even for a video made before dubbing was turned on."""

    from .context import find_video
    from .housekeeping import is_done

    text = script.strip()
    if len(text.split()) < 50:
        raise ValueError("Pega el guion entero (tiene menos de 50 palabras)")
    if is_done(root, f"{slug}-{lang}"):
        raise ValueError(f"{slug}-{lang} ya está hecho: bórralo o archívalo antes de doblarlo otra vez")
    folder = find_video(root, slug)
    (folder / f"guion-{lang}.txt").write_text(text + "\n", encoding="utf-8")
    if title.strip():
        (folder / f"titulo-{lang}.txt").write_text(title.strip() + "\n", encoding="utf-8")
    (folder / OWN.format(lang=lang)).write_text("", encoding="utf-8")
    for stale in (f"voz-{lang}.mp3", f"voz-{lang}.palabras.json", "doblaje.error"):   # read again from the new script
        (folder / stale).unlink(missing_ok=True)
    return {"ok": True}


def mark_manual(root: Path, slug: str, lang: str, done: bool = True) -> dict[str, Any]:
    """«Ya lo doblé yo»: that dubbed video counts as done and the queue never makes it (False undoes it)."""

    import json

    from .housekeeping import REMOVED

    target = root / "out" / f"{slug}-{lang}"
    if done:
        target.mkdir(parents=True, exist_ok=True)
        stamp = {"manual": True, "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
        (target / MANUAL).write_text(json.dumps(stamp), encoding="utf-8")
        if not (target / "video-final.mp4").is_file():
            (target / REMOVED).write_text(json.dumps(stamp), encoding="utf-8")    # counts as done
    else:
        if (target / MANUAL).is_file():
            (target / MANUAL).unlink()
            (target / REMOVED).unlink(missing_ok=True)
    return {"ok": True}


WRONG = "video-final.voz-equivocada.mp4"   # in out/<slug>-<lang>/: a dub that came out with the voice in Spanish


def _aside_shorts(root: Path, dubbed: str, before: float, log: Any) -> None:
    """The Shorts of a dub written from its wrong-language script (sim6-de-short1 «El tapón de la puerta del metro»),
    made before `before`: put aside in materiales/_descartados/; the redone dub makes its own."""

    import shutil

    from .context import video_folders
    from .housekeeping import published

    materials = root / "materiales"
    for short in [f for f in video_folders(root) if f.name.startswith(f"{dubbed}-short")
                  and not any(part.startswith(("_", ".")) for part in f.relative_to(materials).parts)]:
        if published(root, short.name):
            log(f"{short.name}: salió de un doblaje con la voz equivocada y ya está en YouTube: revísalo")
            continue
        try:
            made = short / "guion.txt" if (short / "guion.txt").is_file() else short   # written once, when it was made
            if made.stat().st_mtime >= before:           # made from the redone dub: it stays
                continue
        except OSError:
            continue
        aside = root / "materiales" / "_descartados" / short.name
        aside.parent.mkdir(parents=True, exist_ok=True)
        if aside.exists():
            shutil.rmtree(aside)
        short.replace(aside)
        final = root / "out" / short.name / "video-final.mp4"
        if final.is_file():
            final.replace(final.with_name(WRONG))
        log(f"{short.name}: apartado (salió del guion equivocado de {dubbed}); se hará otro con el doblaje bueno")


def repair_wrong_language(root: Path, log: Any = print) -> int:
    """Dubs whose «translated» script is not in their language (a Spanish script with a few German words: the native
    voice read Spanish): the script, title and voice go, and the dubbed video is put aside so the queue makes it
    again — unless it is already on YouTube (then only a warning). Your own scripts are never touched."""

    import json as _json

    from .context import find_video, video_folders
    from .housekeeping import published

    fixed = 0
    # a dub already put aside (by an earlier version of this, without its Shorts): the Shorts made before it go too
    for out in (root / "out").glob("*/" + WRONG) if (root / "out").is_dir() else []:
        # when it was put aside: rehecho.json (the renamed video keeps the date of its render, before its Shorts)
        stamp = out.parent / "rehecho.json"
        _aside_shorts(root, out.parent.name, stamp.stat().st_mtime if stamp.is_file() else time.time(), log)
    for folder in video_folders(root):
        for script in folder.glob("guion-*.txt"):
            lang = script.stem.split("-", 1)[1]
            if lang not in NAMES or (folder / OWN.format(lang=lang)).is_file():
                continue
            try:
                found = language_of(script.read_text("utf-8"))
            except OSError:
                continue
            if not found or found == lang[:2]:
                continue
            dubbed = f"{folder.name}-{lang}"
            if published(root, dubbed):
                log(f"Doblaje {dubbed}: la voz salió en {IN_SPANISH.get(found, found)} y ya está en YouTube: rehazlo a mano "
                    "(bórralo de YouTube, «No, aún no está subido» y vuelve a doblarlo)")
                continue
            for name in (f"guion-{lang}.txt", f"titulo-{lang}.txt", f"voz-{lang}.mp3", f"voz-{lang}.palabras.json",
                         f"adaptacion-{lang}.md", APPROVED.format(lang=lang), "doblaje.error"):
                (folder / name).unlink(missing_ok=True)
            target = find_video(root, dubbed)
            if target.is_dir():
                for name in ("voz.mp3", "voz.palabras.json", "guion.txt", "titulo.txt"):
                    (target / name).unlink(missing_ok=True)
            final = root / "out" / dubbed / "video-final.mp4"
            if final.is_file():
                final.replace(final.with_name(WRONG))
                (root / "out" / dubbed / "rehecho.json").write_text(_json.dumps(
                    {"why": f"la voz salió en {IN_SPANISH.get(found, found)}", "at": time.strftime("%Y-%m-%dT%H:%M:%S")}),
                    encoding="utf-8")
            _aside_shorts(root, dubbed, time.time(), log)
            log(f"Doblaje {dubbed}: el guion estaba en {IN_SPANISH.get(found, found)}, no en {IN_SPANISH.get(lang, lang)}: "
                "se adapta, se graba y se hace otra vez (sus Shorts, apartados en materiales/_descartados/)")
            fixed += 1
    return fixed


def prepare_all(root: Path, log: Any = print) -> int:
    """The voice thread's turn for dubs: finished videos of channels with dubbing on get their translated script and
    voice; the queue then makes the dubbed video. Returns how many voices it made."""

    from .context import video_folders
    from .housekeeping import is_done

    made = 0
    try:
        repair_wrong_language(root, log)
    except Exception as error:                  # never stops the dubbing of the rest
        log(f"Revisión de idioma de los doblajes: {type(error).__name__}: {str(error)[:200]}")
    materials = root / "materiales"
    for folder in video_folders(root):
        if any(part.startswith(("_", ".")) for part in folder.relative_to(materials).parts):
            continue
        if not (folder / "guion.txt").is_file() or not is_done(root, folder.name):
            continue
        failed = folder / "doblaje.error"
        if failed.is_file() and time.time() - failed.stat().st_mtime < 6 * 3600:
            continue
        try:
            ctx = RunContext.create(folder.name, root=root)
        except Exception:
            continue
        if ctx.section("dub").get("of") or ctx.config.get("compilation") or ctx.section("shorts").get("of"):
            continue                       # dubbed copies, compilations and Shorts (each dub makes its own): no
        cfg = settings(ctx)
        if not cfg["enabled"]:
            continue
        final = root / "out" / folder.name / "video-final.mp4"
        old = _older(cfg, final)
        for lang in targets(ctx, cfg):
            if (folder / f"voz-{lang}.mp3").is_file() or is_done(root, f"{folder.name}-{lang}"):
                continue
            if old and not _forced(folder, lang):
                continue                        # «solo los vídeos nuevos», unless you pasted its script yourself
            try:
                translate(ctx, lang)
                if voice(ctx, lang):
                    made += 1
                    log(f"Doblaje de {folder.name} al {lang} listo para la cola")
            except Exception as error:
                failed.write_text(f"{lang}: {type(error).__name__}: {str(error)[:300]}", encoding="utf-8")
                log(f"Doblaje de {folder.name} al {lang}: {type(error).__name__}: {str(error)[:200]}")
    return made
