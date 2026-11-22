"""From 5-8 reference videos of a niche to a channel ready to produce (prompt «qué canales empezar», part 3).

Input: five to eight YouTube links of one niche or format. Output: a FORMULA REPORT and, with a button, the channel.

What is taken from the references, and from where:
- how they do: views against their channel's normal (API: videos, channels, baseline) — a few units;
- titles: measured patterns (length, numbers, questions, capitals, a colon or a bar); the thumbnails are listed
  for the owner to look at (no model looks at them yet);
- the script, from the source's subtitles (already read elsewhere): duration, words per minute, how it opens, and
  one model call per video for structure, promises, close and kind of sentences;
- the montage (pipeline/medir_video.py on a 360p copy): ONLY after the owner sees the megabytes it would download
  through the proxy and confirms (`montage(..., confirm=True)`);
- where the material comes from: channels and sources credited in the descriptions.

What five of six references share is the formula; what only one does is not. The report says so, with each video's
figure next to it, and keeps what was MEASURED apart from what the model INTERPRETED.

«Crear canal» writes canales/<nombre>.yaml (the niche's searches, the references' channels as competitors for the
radar, the language, the closest montage recipe), its script structure (guion.estructura, own text), the credited
channels as material de partida, and five first ideas that are NOT the references'. The channel does not enter the
autopilot until a PILOT video made with the formula has been measured, put next to the references in a table, and
the owner has seen it (`pilot_seen`). Replicating is replicating the formula — never a script, a title or a
selection of clips of one video.
"""

from __future__ import annotations

import json
import re
import statistics
from datetime import date
from pathlib import Path
from typing import Any, Callable

FOLDER = "out/_formulas"
MIN_LINKS, MAX_LINKS = 5, 8
MB_PER_MINUTE_360 = 2.6          # a 360p stream with its picture only, what the montage measure needs

SCRIPT_SYSTEM = """
Te paso la transcripción de un vídeo de YouTube. Describe su FÓRMULA de guion, no su contenido. Devuelve SOLO JSON:
{"structure": ["bloque 1 en pocas palabras", "..."], "opening": "cómo abre (tipo de gancho, sin copiar frases)",
 "promises_every_seconds": número aproximado de segundos entre promesas o adelantos ("ahora verás…"),
 "closing": "cómo cierra", "sentence_kinds": {"hechos con fecha": 0-100, "citas": 0-100, "afirmación y prueba": 0-100,
 "opinión": 0-100}, "tone": "2-4 palabras"}
""".strip()

IDEAS_SYSTEM = """
Eres el guionista jefe de un canal nuevo de YouTube. Te paso la FÓRMULA que comparten sus vídeos de referencia y los
títulos de esas referencias. Propón 5 primeros vídeos para el canal nuevo que sigan la fórmula y que NO sean ninguno
de esos vídeos ni el mismo tema contado igual. Devuelve SOLO JSON:
{"ideas": [{"title": "...", "angle": "1 frase"}], "queries": ["3-5 búsquedas de YouTube del nicho"],
 "structure": "la estructura de guion del canal en 4-7 pasos numerados, en texto"}
""".strip()


# --- measured ----------------------------------------------------------------------------------------------------

def title_traits(title: str) -> dict[str, Any]:
    words = title.split()
    return {"chars": len(title), "number": bool(re.search(r"\d", title)), "question": "?" in title,
            "capitals": sum(1 for w in words if len(w) >= 3 and w.isupper()) >= 1,
            "separator": bool(re.search(r"[:|—–-]\s", title)), "emoji": bool(re.search(r"[\U0001F300-\U0001FAFF]", title))}


def script_numbers(words: list[tuple[str, float, float]], duration: float) -> dict[str, Any]:
    """From the timed subtitle words: words per minute and the first ~15 seconds (how it opens)."""

    if not words:
        return {"wpm": None, "opening": ""}
    spoken = max(1.0, words[-1][2] - words[0][1])
    return {"wpm": round(len(words) / spoken * 60), "opening": " ".join(w for w, a, _ in words if a < words[0][1] + 15)[:300],
            "talkShare": round(min(1.0, spoken / max(duration, 1.0)), 2)}


def credited(description: str) -> list[str]:
    """Channels and sources the description credits (links to channels, «Fuente:», «Footage:», «Credits»)."""

    out = re.findall(r"youtube\.com/(@[\w.-]+|channel/UC[\w-]{22})", description or "")
    for line in (description or "").splitlines():
        if re.match(r"\s*(fuentes?|sources?|footage|credits?|créditos|imágenes)\s*[:：-]", line, re.IGNORECASE):
            out.append(line.split(":", 1)[-1].strip()[:80])
    return list(dict.fromkeys(o.replace("channel/", "") for o in out if o))


def shared(values: list[Any], n: int) -> bool:
    """Shared by the formula: all but at most one of the n references."""

    return sum(1 for v in values if v) >= max(1, n - 1)


def summarize(videos: list[dict[str, Any]]) -> dict[str, Any]:
    """The formula: medians of the measured numbers and the traits all but one share; and what only one does."""

    n = len(videos)
    med = lambda key: (statistics.median(v[key] for v in videos if v.get(key) is not None)  # noqa: E731
                       if any(v.get(key) is not None for v in videos) else None)
    traits = {}
    lonely = []
    for name in ("number", "question", "capitals", "separator", "emoji"):
        values = [v["title"][name] for v in videos]
        if shared(values, n):
            traits[name] = True
        elif sum(values) == 1:
            lonely.append(f"título con {name}: solo «{next(v['name'] for v in videos if v['title'][name])}»")
    montage = [v["montage"] for v in videos if v.get("montage")]
    out = {"measured": {"videos": n, "durationMinutes": round(med("duration") / 60, 1) if med("duration") else None,
                        "wpm": med("wpm"), "ratio": med("ratio"), "titleChars": med("titleChars"),
                        "titleTraits": sorted(traits), "montage": {k: statistics.median(m[k] for m in montage if m.get(k) is not None)
                                                                   for k in ("cutSeconds", "firstImage", "textShare", "cardShare")
                                                                   if any(m.get(k) is not None for m in montage)} if montage else None},
           "lonely": lonely}
    interpreted = [v.get("script") or {} for v in videos]
    blocks = [len(s.get("structure") or []) for s in interpreted if s.get("structure")]
    kinds: dict[str, list[float]] = {}
    for s in interpreted:
        for k, value in (s.get("sentence_kinds") or {}).items():
            if isinstance(value, (int, float)):
                kinds.setdefault(k, []).append(float(value))
    out["interpreted"] = {"blocks": statistics.median(blocks) if blocks else None,
                          "openings": [s.get("opening") for s in interpreted if s.get("opening")],
                          "promisesEverySeconds": statistics.median([s["promises_every_seconds"] for s in interpreted
                                                                     if isinstance(s.get("promises_every_seconds"), (int, float))])
                          if any(isinstance(s.get("promises_every_seconds"), (int, float)) for s in interpreted) else None,
                          "sentenceKinds": {k: round(statistics.median(v)) for k, v in kinds.items() if len(v) >= max(1, n - 1)}}
    sources = [c for v in videos for c in v.get("credited") or []]
    out["sources"] = [c for c in dict.fromkeys(sources) if sources.count(c) >= 1][:12]
    m = out["measured"]
    out["summary"] = (f"{m['durationMinutes']} min, {m['wpm']} palabras/min" if m["durationMinutes"] else "") + \
        (f", un corte cada {m['montage']['cutSeconds']} s" if m.get("montage") and m["montage"].get("cutSeconds") else "")
    return out


def recipe_for(montage: dict[str, Any] | None) -> str:
    """The closest montage recipe (pipeline/recetas.py) to what the references measured."""

    if not montage:
        return "persona"
    if (montage.get("cardShare") or 0) >= 20 or (montage.get("textShare") or 0) >= 15:
        return "teoria"
    if (montage.get("cutSeconds") or 3) >= 3.8:
        return "suceso"
    return "persona"


def analyse(root: Path, links: Any, api: Any = None, words_fn: Callable[[str], list] | None = None,
            llm_fn: Callable[[str, str], dict[str, Any]] | None = None, niche: str = "") -> dict[str, Any]:
    """The formula report of 5-8 references (no download: the montage comes apart, after a confirmation)."""

    from .material import video_ids

    ids = video_ids(links if isinstance(links, list) else re.split(r"[\s,]+", str(links or "")))[:MAX_LINKS]
    if len(ids) < MIN_LINKS:
        raise ValueError(f"Pega de {MIN_LINKS} a {MAX_LINKS} enlaces de vídeos de YouTube del mismo nicho ({len(ids)} reconocidos)")
    if api is None:
        from .context import RunContext
        from .ytapi import YouTubeAPI

        api = YouTubeAPI(RunContext.create("_formula", root=root))
    found = {v["id"]: v for v in api.videos(ids)}
    channels = {c["id"]: c for c in api.channels(sorted({v["channelId"] for v in found.values()}))}
    videos = []
    for vid in ids:
        v = found.get(vid)
        if v is None:
            continue
        channel = channels.get(v["channelId"]) or {}
        base = None
        try:
            base = api.baseline(channel) if channel else None
        except Exception:
            base = None
        words = words_fn(vid) if words_fn else []
        numbers = script_numbers(words, v["duration"])
        script = {}
        if llm_fn and words:
            try:
                script = llm_fn(SCRIPT_SYSTEM, " ".join(w for w, _, _ in words)[:24000]) or {}
            except Exception as error:
                script = {"error": str(error)[:120]}
        videos.append({"id": vid, "name": v["title"][:80], "channel": v.get("channel"), "channelId": v["channelId"],
                       "subscribers": channel.get("subscribers"), "views": v["views"], "duration": v["duration"],
                       "ratio": round(v["views"] / base, 2) if base else None, "titleChars": len(v["title"]),
                       "title": title_traits(v["title"]), "thumbnail": v.get("thumbnail"),
                       "language": v.get("audioLanguage") or v.get("language") or "", **numbers,
                       "script": script, "credited": credited(v.get("description") or ""), "montage": None})
    report = {"niche": niche or "", "date": date.today().isoformat(), "videos": videos, **summarize(videos),
              "montageMB": round(sum(v["duration"] for v in videos) / 60 * MB_PER_MINUTE_360)}
    save(root, report)
    return report


def montage(root: Path, report: dict[str, Any], confirm: bool = False, measure_fn: Callable[[str, int], dict] | None = None
            ) -> dict[str, Any]:
    """The montage of each reference (cuts, first image, text, cards), from a 360p copy downloaded through the proxy.
    Without `confirm` it only says how many MB that is."""

    if not confirm:
        return {"needsConfirmation": True, "mb": report.get("montageMB"),
                "message": f"Medir el montaje baja las {len(report['videos'])} referencias a 360p por el proxy: unos "
                           f"{report.get('montageMB')} MB. Confírmalo para seguir."}
    measure_fn = measure_fn or _measure_360
    for video in report["videos"]:
        try:
            video["montage"] = measure_fn(video["id"], int(video["duration"]))
        except Exception as error:
            video["montage"] = None
            video["montageError"] = str(error)[:160]
    report.update(summarize(report["videos"]))
    save(root, report)
    return report


def _measure_360(video_id: str, seconds: int) -> dict[str, Any]:
    from .config import PROJECT_ROOT
    from .context import RunContext
    from .medir_video import from_file
    from .sourcing import youtube_source

    youtube = youtube_source(RunContext.create("_formula", root=PROJECT_ROOT))
    try:
        path = youtube.download_range(video_id, 0, float(seconds), fmt="bv*[height<=360]", prefix="ref360")
    finally:
        youtube.close()
    return from_file(Path(path))


def save(root: Path, report: dict[str, Any]) -> Path:
    from .niche_ideas import slugify

    name = slugify(report.get("niche") or "-".join(v["id"] for v in report["videos"][:2])) or "formula"
    report["key"] = report.get("key") or name
    path = root / FOLDER / f"{report['key']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def load(root: Path, key: str) -> dict[str, Any]:
    return json.loads((root / FOLDER / f"{key}.json").read_text("utf-8"))


# --- the channel ---------------------------------------------------------------------------------------------------

def create_channel(root: Path, report: dict[str, Any], name: str,
                   llm_fn: Callable[[str, str], dict[str, Any]] | None = None) -> dict[str, Any]:
    """canales/<nombre>.yaml from the formula, the credited channels as material de partida, five first ideas that are
    not the references', and the pilot still to be seen (the autopilot refuses the channel until then)."""

    import yaml

    from . import material
    from .niche_ideas import save as save_idea, slugify

    slug = slugify(name)
    if not slug:
        raise ValueError("Nombre de canal no válido")
    path = root / "canales" / f"{slug}.yaml"
    if path.exists():
        raise ValueError(f"Ya existe el canal {slug}")
    m = report.get("measured") or {}
    languages = [v.get("language", "")[:2] for v in report["videos"] if v.get("language")]
    language = max(set(languages), key=languages.count) if languages else "es"
    titles = [v["name"] for v in report["videos"]]
    told = (llm_fn(IDEAS_SYSTEM, json.dumps({"formula": {k: report.get(k) for k in ("measured", "interpreted")},
                                             "references": titles}, ensure_ascii=False)) if llm_fn else {}) or {}
    ideas = [i for i in (told.get("ideas") or []) if isinstance(i, dict) and str(i.get("title") or "").strip()
             and str(i["title"]).casefold() not in {t.casefold() for t in titles}][:5]
    queries = [str(q) for q in (told.get("queries") or []) if str(q).strip()][:5] or [report.get("niche") or titles[0]]
    recipe = recipe_for(m.get("montage"))
    profile = {
        "ideas": {"about": f"un canal de YouTube de {report.get('niche') or 'este nicho'} con la fórmula de sus referencias",
                  "my_channel": "", "competitors": list(dict.fromkeys(v["channelId"] for v in report["videos"])),
                  "niches": [report.get("niche") or queries[0]]},
        "lab": {"queries": queries},
        "align": {"language": language},
        "montaje": {"receta": recipe},
        "guion": {"estructura": str(told.get("structure") or "").strip() or None},
        "formula": {"key": report["key"], "pilot": "pendiente"},
    }
    if not profile["guion"]["estructura"]:
        profile.pop("guion")
    header = (f"# Canal creado desde {len(report['videos'])} vídeos de referencia ({date.today().strftime('%d-%m-%Y')}): "
              f"out/_formulas/{report['key']}.json\n# No entra en el piloto automático hasta que veas su vídeo piloto "
              "al lado de las referencias.\n\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header + yaml.safe_dump(profile, allow_unicode=True, sort_keys=False, width=110), encoding="utf-8")
    group = root / "materiales" / slug
    group.mkdir(parents=True, exist_ok=True)
    if not (group / "config.yaml").exists():
        (group / "config.yaml").write_text(f"canal: {slug}\n", encoding="utf-8")
    sources = [s for s in report.get("sources") or [] if s.startswith(("@", "UC"))]
    if sources:
        material.save(group, channels=sources)
    for n, idea in enumerate(ideas, 1):               # an id each: saving one without it would drop the others
        save_idea(root, {"id": f"formula-{slug}-{n}", "title": idea["title"], "angle": idea.get("angle", "")}, slug)
    report["channel"] = slug
    save(root, report)
    return {"channel": slug, "recipe": recipe, "language": language, "ideas": ideas, "materialChannels": sources}


def pilot_table(root: Path, report: dict[str, Any], pilot_slug: str) -> list[dict[str, Any]]:
    """The pilot measured with the same tool, next to each reference (and the formula's medians)."""

    from .medir_video import measure

    rows = [{"name": f"PILOTO · {pilot_slug}", **measure(root, pilot_slug)}]
    rows += [{"name": v["name"], **(v.get("montage") or {})} for v in report["videos"]]
    rows.append({"name": "fórmula (mediana)", **((report.get("measured") or {}).get("montage") or {})})
    report["pilot"] = {"slug": pilot_slug, "table": rows, "seen": False}
    save(root, report)
    return rows


def pilot_seen(root: Path, key: str) -> None:
    report = load(root, key)
    if not report.get("pilot"):
        raise ValueError("Aún no hay vídeo piloto medido")
    report["pilot"]["seen"] = True
    save(root, report)


def autopilot_allowed(root: Path, channel: str) -> tuple[bool, str]:
    """A channel made from a formula enters the autopilot only once its pilot was seen next to the references."""

    from .context import RunContext

    try:
        config = RunContext.create("_formula", root=root, channel=channel).config
    except Exception:
        return True, ""
    key = (config.get("formula") or {}).get("key")
    if not key:
        return True, ""
    try:
        report = load(root, key)
    except (OSError, ValueError):
        return False, "falta el informe de su fórmula"
    if not (report.get("pilot") or {}).get("seen"):
        return False, "primero haz su vídeo piloto y míralo al lado de las referencias (out/_formulas)"
    return True, ""


# --- production wiring (the tests pass their own) -------------------------------------------------------------------

def production(root: Path) -> tuple[Callable[[str], list], Callable[[str, str], dict[str, Any]]]:
    """The subtitles of a reference (cached, one request per video, Spanish then English) and the model calls."""

    from .context import RunContext
    from .llm import complete_json
    from .quotes import parse_vtt, timed_words
    from .sourcing import youtube_source

    ctx = RunContext.create("_formula", root=root)

    def words(video_id: str) -> list:
        youtube = youtube_source(ctx)
        try:
            for lang in ("es", "en", "pt"):
                try:
                    path = youtube.subtitle_file(video_id, lang)
                except Exception:
                    path = None
                if path is not None:
                    return timed_words(parse_vtt(path.read_text("utf-8", errors="replace")))
        finally:
            youtube.close()
        return []

    def llm(system: str, text: str) -> dict[str, Any]:
        return complete_json(ctx, stage="radar", section="planner", max_tokens=1500, system=system, user=text)

    return words, llm


def listing(root: Path) -> list[dict[str, Any]]:
    out = []
    for path in sorted((root / FOLDER).glob("*.json"), key=lambda p: -p.stat().st_mtime) if (root / FOLDER).is_dir() else []:
        try:
            r = json.loads(path.read_text("utf-8"))
        except (OSError, ValueError):
            continue
        out.append({k: r.get(k) for k in ("key", "niche", "date", "summary", "measured", "interpreted", "lonely",
                                          "sources", "montageMB", "channel", "pilot")}
                   | {"videos": [{k: v.get(k) for k in ("id", "name", "channel", "views", "ratio", "wpm", "duration",
                                                        "montage", "thumbnail")} for v in r.get("videos") or []]})
    return out
