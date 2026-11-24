"""«Material primero», stage 1: research and the case file (prompt «modo material primero»).

The current mode writes a script and then illustrates it. This mode first finds and READS the real material of the
topic, and only then is the script written from what was found. Nothing here downloads a video.

1. Research: from the title (and the owner's links, one per entry if given) the model names the entries of a top (or
   the chapters of a news piece or documentary) with searches in the language the footage exists in; the API finds
   3-6 sources per entry, ranked so that whoever FILMED it (bodycam, dashcam, a local newscast) comes before whoever
   summarizes it (a compilation, another top), with a cap in all.
2. For every source, without downloading the video: its subtitles with times (one request, cached) and, if
   `material_first.indice` is on, the scene index of pipeline/indice.py.
3. The case file (work/<vídeo>/expediente.json): per source the useful segments — from which second to which, what is
   seen, what is said LITERALLY (always re-read from the subtitles, never the model's words), in which language, and
   who speaks and as what (witness, journalist, police, relative, expert, the protagonist).

Who speaks is the delicate part: the subtitles do not say. The model reads it from what the video itself says and
from its title and description, with a confidence note; and a NAME only stays if it is written or said in the
source (title, description, subtitles) — otherwise only the role remains («una vecina», «el agente»). The on-screen
caption (OCR) is read later, on the downloaded clip, by the check of stage 4. Attributing a sentence to someone who
did not say it is the worst failure this mode can have.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

OUTPUT = "expediente.json"
ROLES = ("testigo", "periodista", "policía", "familiar", "experto", "protagonista", "narrador de la fuente", "otro")
ORIGINAL = re.compile(r"\b(bodycam|body cam|dashcam|dash cam|footage|raw|cámara corporal|cámara del coche|grabación|"
                      r"video original|vídeo original|exclusive|exclusiva|live|en directo|en vivo)\b", re.IGNORECASE)
NEWS = re.compile(r"\b(news|noticias|noticiero|telediario|informativo|tv|television|televisión|canal \d+|abc|nbc|cbs|"
                  r"fox|cnn|bbc|univision|telemundo|antena|rtve|kare|ktla|wsb|wfaa)\b", re.IGNORECASE)
DOCUMENTARY = re.compile(r"\b(documentary|documental|full episode|episodio completo)\b", re.IGNORECASE)
SUMMARY = re.compile(r"\b(top \d+|top\d+|compilation|recopilación|ranking|the most|los más|las más|\d+ (?:most|craziest))\b",
                     re.IGNORECASE)

PLAN_SYSTEM = """
Vas a preparar un vídeo de YouTube en modo «material primero»: antes de escribir nada se busca el material real.
Te paso el título, el tipo ({kind}), los minutos y, si los hay, los puestos o enlaces que ya ha elegido el dueño.
Devuelve los {count} {unit} que tendrá el vídeo: sucesos REALES y concretos (con lugar y fecha si los sabes), que
estén grabados (persecuciones con cámara de helicóptero o del coche patrulla, noticias de televisión, documentales).
Para cada uno, de 2 a 4 búsquedas de YouTube en el IDIOMA en que existe ese material (un caso de Texas, en inglés)
que encuentren a quien lo GRABÓ o lo dio en las noticias, no recopilaciones ni otros tops.
Devuelve SOLO JSON: {{"items": [{{"n": 1, "name": "nombre corto del caso", "where_when": "lugar y fecha",
"language": "en", "queries": ["...", "..."]}}]}}
""".strip()

SEGMENTS_SYSTEM = """
Te paso una fuente de vídeo sobre «{item}»: su título, su descripción y su transcripción con tiempos (y, si las hay,
las escenas que se ven). Señala los TRAMOS ÚTILES para un vídeo sobre ese suceso:
- "declaracion": una persona hablando del suceso (un testigo, la periodista que lo dio, el agente, un familiar);
- "secuencia": el suceso mismo grabado (la persecución, el choque, el arresto), aunque nadie hable;
- "dato": la fuente dice un dato concreto (velocidad, duración, kilómetros, daños, condena).
Para cada tramo: start y end en segundos (de la transcripción), qué se ve, el tipo, y quién habla:
{{"name": nombre SOLO si está escrito o dicho en la fuente (si no, null), "role": uno de {roles},
"gender": "hombre", "mujer" o null (por la voz y lo que se ve; solo para elegir la voz de un doblaje),
"evidence": de dónde lo sacas ("dicho en el vídeo", "título", "descripción", "deducido"), "confidence": 0-1}}.
No inventes nombres. No copies frases: los tiempos bastan (la frase literal se lee de la transcripción).
Devuelve SOLO JSON: {{"segments": [{{"start": 12.0, "end": 24.5, "type": "declaracion", "seen": "...",
"speaker": {{...}}, "fact": "el dato, si es de tipo dato"}}], "event_match": 0-1 (si la fuente es de ESE suceso)}}
""".strip()


# --- sources -------------------------------------------------------------------------------------------------------

def source_kind(video: dict[str, Any]) -> str:
    """«original» (who filmed it), «informativo», «documental», «recopilación» (a summary: last) or «otro»."""

    text = f"{video.get('title', '')} {video.get('description', '')[:300]}"
    channel = str(video.get("channel") or "")
    if SUMMARY.search(video.get("title", "")):
        return "recopilación"
    if ORIGINAL.search(text):
        return "original"
    if NEWS.search(channel) or NEWS.search(video.get("title", "")):
        return "informativo"
    if DOCUMENTARY.search(text):
        return "documental"
    return "otro"


RANK = {"original": 0, "informativo": 1, "documental": 2, "otro": 3, "recopilación": 9}


def about_entry(video: dict[str, Any], about: str) -> bool:
    """The result is about this entry: its title or description shares a meaningful word with the entry's name,
    place, date and searches (a name, «Montreal», «Produnova»…)."""

    from .huecos import _words

    wanted = _words(about)
    return not wanted or bool(wanted & _words(f"{video.get('title', '')} {str(video.get('description') or '')[:300]}"))


def pick_sources(videos: list[dict[str, Any]], per_item: int, taken: set[str]) -> list[dict[str, Any]]:
    """The best `per_item` sources of one entry: long enough, not a summary unless nothing else, not used by another
    entry, whoever filmed it first, then by views."""

    usable = [v for v in videos if v["id"] not in taken and 30 <= int(v.get("duration") or 0) <= 4 * 3600
              and v.get("live", "none") == "none"]
    for v in usable:
        v["kind"] = source_kind(v)
    good = [v for v in usable if v["kind"] != "recopilación"] or usable
    return sorted(good, key=lambda v: (RANK[v["kind"]], -int(v.get("views") or 0)))[:per_item]


# --- reading a source ----------------------------------------------------------------------------------------------

def chunks(words: list[tuple[str, float, float]], seconds: float = 10.0) -> list[tuple[float, float, str]]:
    """The timed words in ~`seconds` pieces, for the model: [(start, end, text)]."""

    out: list[tuple[float, float, str]] = []
    current: list[tuple[str, float, float]] = []
    for word in words:
        current.append(word)
        if word[2] - current[0][1] >= seconds:
            out.append((current[0][1], current[-1][2], " ".join(w for w, _, _ in current)))
            current = []
    if current:
        out.append((current[0][1], current[-1][2], " ".join(w for w, _, _ in current)))
    return out


def said_between(words: list[tuple[str, float, float]], start: float, end: float) -> str:
    """What the subtitles say in [start, end]: the literal sentence, never the model's version."""

    return " ".join(w for w, a, b in words if b > start + 0.05 and a < end - 0.05).strip()


def name_in_source(name: str | None, texts: list[str]) -> bool:
    """A name stays only if every word of it (3+ letters) is written or said in the source."""

    if not name or not str(name).strip():
        return False
    haystack = " ".join(texts).casefold()
    parts = [p for p in re.findall(r"[^\W\d_]{3,}", str(name).casefold())]
    return bool(parts) and all(p in haystack for p in parts)


def clean_segments(raw: dict[str, Any], words: list[tuple[str, float, float]], video: dict[str, Any],
                   duration: float) -> list[dict[str, Any]]:
    """The model's segments, checked: inside the video, the literal sentence re-read from the subtitles, a known role,
    and a name only when the source has it."""

    texts = [video.get("title", ""), video.get("description", ""), " ".join(w for w, _, _ in words)]
    out = []
    for seg in raw.get("segments") or []:
        try:
            start, end = max(0.0, float(seg["start"])), min(float(duration or 1e9), float(seg["end"]))
        except (KeyError, TypeError, ValueError):
            continue
        kind = str(seg.get("type") or "")
        if end - start < 1.0 or kind not in ("declaracion", "secuencia", "dato"):
            continue
        speaker = seg.get("speaker") if isinstance(seg.get("speaker"), dict) else {}
        role = str(speaker.get("role") or "otro")
        name = speaker.get("name")
        kept = name if name_in_source(name, texts) else None
        try:
            confidence = max(0.0, min(1.0, float(speaker.get("confidence") or 0)))
        except (TypeError, ValueError):
            confidence = 0.0
        said = said_between(words, start, end)
        if kind == "declaracion" and not said:
            continue                                  # a statement nobody can read: not a statement
        out.append({"start": round(start, 2), "end": round(end, 2), "type": kind,
                    "seen": " ".join(str(seg.get("seen") or "").split())[:200], "said": said[:1200],
                    "fact": " ".join(str(seg.get("fact") or "").split())[:200] or None,
                    "speaker": {"name": kept, "role": role if role in ROLES else "otro",
                                "evidence": str(speaker.get("evidence") or "")[:60],
                                "confidence": round(confidence if kept or not name else confidence * 0.5, 2),
                                "gender": speaker.get("gender") if speaker.get("gender") in ("hombre", "mujer") else None,
                                "droppedName": name if name and not kept else None}
                    if kind == "declaracion" else None})
    return out


def subtitles(youtube: Any, video_id: str, languages: list[str]) -> tuple[list[tuple[str, float, float]], str]:
    """Timed words of a source and the language they came in ([] when it has none): the captions the analysis reads
    (youtube.captions, through the video's session: these do come on the server), then the subtitle file."""

    from .quotes import parse_vtt, timed_words

    try:
        cues = youtube.captions(video_id) if hasattr(youtube, "captions") else []
    except Exception:
        cues = []
    if cues:
        words = timed_words([(float(a), float(b), str(t)) for a, b, t in cues])
        if words:
            return words, "subtítulos"
    for lang in dict.fromkeys(languages):
        try:
            path = youtube.subtitle_file(video_id, lang)
        except Exception:
            path = None
        if path is not None:
            words = timed_words(parse_vtt(path.read_text("utf-8", errors="replace")))
            if words:
                return words, lang
    return [], ""


AUDIO_MB_PER_MINUTE = 1.0          # the audio alone (m4a ~128 kb/s), what a transcription needs


def transcribe_audio(ctx: Any, youtube: Any, video_id: str, seconds: float, lang: str) -> list[tuple[str, float, float]]:
    """A source with no subtitles at all: its audio only (about 1 MB a minute through the proxy), and Whisper."""

    from faster_whisper import WhisperModel

    audio = youtube.download_range(video_id, 0, seconds, fmt="ba[ext=m4a]/ba", prefix="mfa", audio_only=True)
    model = WhisperModel(str(ctx.section("quotes").get("whisper_model", "small")), device="cpu", compute_type="int8")
    segments, _ = model.transcribe(str(audio), language=lang or None, word_timestamps=True, vad_filter=True)
    return [(w.word.strip(), w.start, w.end) for s in segments for w in (s.words or []) if w.word.strip()]


# --- the whole case file ---------------------------------------------------------------------------------------------

def build(ctx: Any, title: str, kind: str = "top", count: int = 5, minutes: float = 6.0, links: list[str] | None = None,
          api: Any = None, youtube: Any = None, ask: Callable[[str, str], dict[str, Any]] | None = None,
          scenes_fn: Callable[[dict[str, Any]], list[dict[str, Any]]] | None = None,
          transcribe_fn: Callable[[str, float, str], list] | None = None) -> dict[str, Any]:
    """Research + case file, saved in work/<vídeo>/expediente.json."""

    from .idiomas import Budget, SEARCH_UNITS
    from .material import video_ids

    cfg = ctx.section("material_first") if hasattr(ctx, "section") else {}
    per_item = max(2, min(6, int(cfg.get("sources_per_item", 4))))
    total_cap = int(cfg.get("max_sources", 24))
    if ask is None:
        from .llm import complete_json

        def ask(system: str, user: str) -> dict[str, Any]:
            return complete_json(ctx, stage="expediente", section="planner", max_tokens=3000, system=system, user=user)
    if api is None:
        from .ytapi import YouTubeAPI

        api = YouTubeAPI(ctx)
    budget = Budget(ctx.root, api, {"gaps_units_per_day": int(cfg.get("api_units", 2500)),
                                    "keep_for_queue": int(cfg.get("keep_for_queue", 3000))})
    budget.spent = 0                                   # a cap per video, not per day
    unit = {"top": "puestos", "noticia": "partes", "documental": "capítulos"}.get(kind, "puestos")
    given = video_ids(links or [])
    owned: dict[str, dict[str, Any]] = {}
    if given:                                          # 1 unit: what each of the owner's links is about
        try:
            owned = {v["id"]: v for v in api.videos(given)}
        except Exception:
            owned = {}
        count = max(count, len(given))
    listing = "\n".join(f"{n}. {owned.get(vid, {}).get('title') or vid} ({owned.get(vid, {}).get('channel') or '?'})"
                        for n, vid in enumerate(given, 1))
    plan = ask(PLAN_SYSTEM.format(kind=kind, count=count, unit=unit),
               f"TÍTULO: {title}\nMINUTOS: {minutes}\n"
               + (f"ENLACES DEL DUEÑO: cada enlace ES un {unit[:-1] if unit.endswith('s') else unit}, en este orden "
                  f"(el {unit[:-1] if unit.endswith('s') else unit} n es el enlace n); nombra cada caso por lo que dice su "
                  f"título y busca más material de ESE caso:\n{listing}" if given else "ENLACES DEL DUEÑO: ninguno"))
    items = [i for i in (plan.get("items") or []) if isinstance(i, dict) and str(i.get("name") or "").strip()][:count]
    taken: set[str] = set()
    notes: list[str] = []
    audio_spent = 0.0                                  # MB of audio downloaded to transcribe sources without subtitles
    out_items = []
    for n, item in enumerate(items, 1):
        queries = [str(q) for q in (item.get("queries") or []) if str(q).strip()][:4]
        found: list[str] = [given[n - 1]] if n - 1 < len(given) else []
        for q in queries:
            if len(taken) >= total_cap or not budget.allows(SEARCH_UNITS + 2):
                notes.append(f"{item['name']}: búsqueda «{q}» sin hacer (tope de cuota del vídeo)")
                continue
            try:
                found += api.search(q, order="relevance", language=str(item.get("language") or "")[:2], max_results=15)
                budget.spend(SEARCH_UNITS + 2)
            except Exception as error:            # no API searches left today: yt-dlp's, as the normal mode does
                if youtube is None:
                    raise
                found += [str(e["id"]) for e in (youtube.search(q) or [])[:15] if e.get("id")]
                notes.append(f"{item['name']}: «{q}» buscado con yt-dlp ({str(error)[:80]})")
        videos = api.videos(list(dict.fromkeys(found))) if found else []
        own_id = given[n - 1] if n - 1 < len(given) else None
        about = " ".join([str(item.get("name") or ""), str(item.get("where_when") or ""), *queries,
                          str(owned.get(own_id, {}).get("title") or "")])
        off = [v for v in videos if v["id"] != own_id and not about_entry(v, about)]
        if off:                                        # another story that the search brought (an anime trailer…)
            notes.append(f"{item['name']}: {len(off)} resultado(s) de otra cosa descartados")
        videos = [v for v in videos if v not in off]
        chosen = pick_sources(videos, per_item, taken)
        if n - 1 < len(given):                         # the owner's own link always comes in, first
            own = next((v for v in videos if v["id"] == given[n - 1]), None)
            if own is not None:
                own["kind"] = own.get("kind") or source_kind(own)
                chosen = [own, *[v for v in chosen if v is not own]][:per_item]
        chosen = chosen[: max(0, total_cap - len(taken))]
        taken |= {v["id"] for v in chosen}
        sources = []
        for video in chosen:
            languages = [str(item.get("language") or "en")[:2], "es", "en"]
            words, lang = subtitles(youtube, video["id"], languages) if youtube is not None else ([], "")
            seconds = float(video.get("duration") or 0)
            audio_mb = seconds / 60 * AUDIO_MB_PER_MINUTE
            if (not words and youtube is not None and cfg.get("transcribe_audio", True)
                    and seconds <= 60 * float(cfg.get("transcribe_max_minutes", 20))
                    and audio_spent + audio_mb <= float(cfg.get("audio_mb", 300))):
                try:                                   # no subtitles: its audio, transcribed (the MB are counted)
                    words = (transcribe_fn or (lambda vid, secs, lg: transcribe_audio(ctx, youtube, vid, secs, lg)))(
                        video["id"], seconds, languages[0])
                    lang = f"transcrito ({round(audio_mb)} MB de audio)" if words else ""
                    audio_spent += audio_mb
                except Exception as error:
                    notes.append(f"{video['id']}: no se pudo transcribir su audio ({str(error)[:80]})")
            scenes = scenes_fn(video) if scenes_fn else []
            entry = {"id": video["id"], "url": f"https://www.youtube.com/watch?v={video['id']}", "title": video.get("title"),
                     "channel": video.get("channel"), "kind": video.get("kind"), "duration": video.get("duration"),
                     "views": video.get("views"), "subtitles": lang or None, "segments": [], "eventMatch": None}
            if not words and not scenes:
                entry["note"] = "sin subtítulos: para usar sus declaraciones habría que bajar su audio y transcribirlo"
                sources.append(entry)
                continue
            listing = "\n".join(f"[{a:.1f}-{b:.1f}] {t}" for a, b, t in chunks(words))[:20000]
            scene_lines = "\n".join(f"[{s.get('start')}-{s.get('end')}] {s.get('en') or s.get('es')}" for s in scenes)[:4000]
            try:
                raw = ask(SEGMENTS_SYSTEM.format(item=item["name"], roles=", ".join(ROLES)),
                          f"TÍTULO: {video.get('title')}\nCANAL: {video.get('channel')}\nDESCRIPCIÓN: "
                          f"{str(video.get('description') or '')[:600]}\n\nTRANSCRIPCIÓN:\n{listing or '(sin subtítulos)'}"
                          + (f"\n\nESCENAS:\n{scene_lines}" if scene_lines else ""))
            except Exception as error:
                entry["note"] = f"no se pudo leer: {str(error)[:120]}"
                sources.append(entry)
                continue
            entry["segments"] = clean_segments(raw, words, video, float(video.get("duration") or 0))
            try:
                entry["eventMatch"] = round(max(0.0, min(1.0, float(raw.get("event_match")))), 2)
            except (TypeError, ValueError):
                entry["eventMatch"] = None
            sources.append(entry)
        out_items.append({"n": n, "name": str(item["name"])[:120], "whereWhen": str(item.get("where_when") or "")[:120],
                          "language": str(item.get("language") or "")[:2], "queries": queries, "sources": sources})
    result = {"title": title, "kind": kind, "minutes": minutes, "items": out_items, "notes": notes,
              "apiUnits": budget.spent, "audioMB": round(audio_spent), "summary": summary(out_items)}
    ctx.write_json(OUTPUT, result)
    return result


def summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    """What material there is, per entry: sources, statements (and how many with a name from the source), footage."""

    rows = []
    for item in items:
        segs = [s for src in item["sources"] for s in src["segments"]]
        rows.append({"n": item["n"], "name": item["name"], "sources": len(item["sources"]),
                     "statements": sum(1 for s in segs if s["type"] == "declaracion"),
                     "named": sum(1 for s in segs if s["type"] == "declaracion" and (s["speaker"] or {}).get("name")),
                     "footageSeconds": round(sum(s["end"] - s["start"] for s in segs if s["type"] == "secuencia")),
                     "facts": sum(1 for s in segs if s["type"] == "dato")})
    weak = [r["name"] for r in rows if r["statements"] == 0 or r["footageSeconds"] < 20]
    return {"items": rows, "weak": weak}


def load(ctx: Any) -> dict[str, Any]:
    return json.loads((ctx.work_dir / OUTPUT).read_text("utf-8"))


# --- videos in this mode --------------------------------------------------------------------------------------------

def create(root: Path, title: str, channel: str = "", kind: str = "top", count: int = 5, minutes: float = 6.0,
           tone: str = "", links: list[str] | None = None) -> str:
    """A «material primero» video: materiales/[<canal>/]<slug>/ with its title and `material_first` settings. It has
    no script and no voice, so the normal queue never takes it."""

    import yaml

    from .niche_ideas import slugify

    title = " ".join(str(title).split())[:140]
    if len(title) < 5:
        raise ValueError("Escribe el título del vídeo")
    if kind not in ("top", "noticia", "documental"):
        raise ValueError("El tipo es top, noticia o documental")
    slug = slugify(title)[:40].strip("-") or "material"
    folder = root / "materiales" / channel / slug if channel else root / "materiales" / slug
    if folder.exists():
        raise ValueError(f"Ya existe {slug}")
    folder.mkdir(parents=True)
    (folder / "titulo.txt").write_text(title + "\n", encoding="utf-8")
    settings = {"modo": "material", "material_first": {"kind": kind, "count": max(1, min(10, int(count))), "minutes": float(minutes),
                                   "tone": str(tone)[:80], "links": [str(l) for l in (links or [])][:10]}}
    (folder / "config.yaml").write_text(yaml.safe_dump(settings, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return slug


def run(root: Path, slug: str) -> dict[str, Any]:
    """`python main.py --expediente <vídeo>`: the case file of a «material primero» video."""

    from .context import RunContext
    from .sourcing import youtube_source

    ctx = RunContext.create(slug, root=root)
    cfg = ctx.section("material_first")
    title = (ctx.materials_dir / "titulo.txt").read_text("utf-8").strip().splitlines()[0]
    youtube = youtube_source(ctx)
    try:
        return build(ctx, title, kind=str(cfg.get("kind") or "top"), count=int(cfg.get("count", 5)),
                     minutes=float(cfg.get("minutes", 6)), links=list(cfg.get("links") or []), youtube=youtube)
    finally:
        youtube.close()


def videos(root: Path) -> list[dict[str, Any]]:
    """The «material primero» videos and how far each got."""

    from .context import RunContext, video_folders

    out = []
    for folder in video_folders(root):
        try:
            import yaml

            cfg = yaml.safe_load((folder / "config.yaml").read_text("utf-8")) or {}
        except (OSError, ValueError):
            continue
        if not isinstance(cfg, dict) or not cfg.get("material_first"):
            continue
        work = RunContext.create(folder.name, root=root).work_dir
        title = (folder / "titulo.txt").read_text("utf-8").strip() if (folder / "titulo.txt").is_file() else folder.name
        out.append({"slug": folder.name, "title": title, **cfg["material_first"],
                    "expediente": (work / OUTPUT).is_file(), "bloques": (work / "bloques.json").is_file()})
    return out
