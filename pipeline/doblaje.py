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
Devuelve SOLO JSON: {"title": "título traducido", "script": "el guion traducido"}.
""".strip()

NAMES = {"en": "English", "pt": "Portuguese (Brazil)", "fr": "French", "it": "Italian", "de": "German"}


def settings(ctx: RunContext) -> dict[str, Any]:
    cfg = ctx.section("dubbing")
    return {"enabled": bool(cfg.get("enabled", False)), "languages": [str(l) for l in cfg.get("languages", ["en"])],
            "voices": cfg.get("voices") or {}}


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
    language = NAMES.get(lang, lang)
    result = complete_json(ctx, stage="doblaje", section="planner", max_tokens=12000,
                           system=TRANSLATE_SYSTEM.replace("{language}", language),
                           user=f"TÍTULO: {title or '(sin título)'}\n\nGUION:\n{script}")
    text = str(result.get("script") or "").strip()
    if len(text.split()) < 0.5 * len(script.split()):
        raise RuntimeError(f"la traducción al {language} salió demasiado corta")
    target.write_text(text + "\n", encoding="utf-8")
    if result.get("title"):
        (folder / f"titulo-{lang}.txt").write_text(str(result["title"]).strip() + "\n", encoding="utf-8")
    return True


def voice(ctx: RunContext, lang: str) -> bool:
    """voz-<lang>.mp3 read by GenAIPro from guion-<lang>.txt with the channel's voice for that language."""

    from . import tts

    folder = ctx.materials_dir
    target = folder / f"voz-{lang}.mp3"
    spec = (settings(ctx)["voices"] or {}).get(lang) or {}
    if target.is_file() or not spec.get("voice_id"):
        return False
    lock = folder / f".voz-{lang}.generando"
    if not tts._take(lock):
        return False
    try:
        text = tts.narration_text((folder / f"guion-{lang}.txt").read_text("utf-8"))
        print(f"Doblaje {ctx.slug} → {lang}: voz con GenAIPro ({len(text)} caracteres)")
        result = tts.generate(ctx.env("GENAIPRO_API_KEY", required=False), text, {**tts.DEFAULTS, **spec}, target)
        try:
            from .costs import record_cost

            record_cost(ctx, stage="doblaje", provider="genaipro", operation=f"voz-{lang}",
                        usd=float(spec.get("usd_per_1k_chars", 0)) * result["chars"] / 1000,
                        details={"chars": result["chars"], "lang": lang})
        except Exception:
            pass
        return True
    finally:
        lock.unlink(missing_ok=True)


def prepare_all(root: Path, log: Any = print) -> int:
    """The voice thread's turn for dubs: finished videos of channels with dubbing on get their translated script and
    voice; the queue then makes the dubbed video. Returns how many voices it made."""

    from .context import video_folders
    from .housekeeping import is_done

    made = 0
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
        if ctx.section("dub").get("of") or ctx.config.get("compilation"):   # dubbed copies and compilations: no
            continue
        cfg = settings(ctx)
        if not cfg["enabled"]:
            continue
        for lang in cfg["languages"]:
            if (folder / f"voz-{lang}.mp3").is_file() or is_done(root, f"{folder.name}-{lang}"):
                continue
            try:
                translate(ctx, lang)
                if voice(ctx, lang):
                    made += 1
                    log(f"Doblaje de {folder.name} al {lang} listo para la cola")
            except Exception as error:
                failed.write_text(f"{lang}: {type(error).__name__}: {str(error)[:300]}", encoding="utf-8")
                log(f"Doblaje de {folder.name} al {lang}: {type(error).__name__}: {str(error)[:200]}")
    return made
