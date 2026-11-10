"""The opening clip: a real moment with its own sound and translated subtitles BEFORE the narration starts — e.g. Simone
Biles answering an Instagram question («You have to have a certain body type to be a gymnast») and her reply.

You see it before the video is made (new-video page, «🎬 Buscar clip de apertura»):
- you UPLOAD a video (the whole one: it is cut here), or give a YouTube link, with the seconds if you know them; or
  describe the moment («Simone Biles respondiendo en Instagram a lo del tipo de cuerpo»), or leave it empty and it is
  proposed from the title and the start of the script;
- subtitles are optional («Poner subtítulos traducidos»): off for a clip that already has them burnt in;
- `search()` finds the videos, reads them through their captions (else Whisper over the first minutes), picks the
  stretch (≤ `apertura.max_seconds`, 20) and translates every line into the video's language with its own timing;
- the page shows each candidate playing from that second with the translated lines; «Usar esta» (with the start and
  end adjustable) saves it as materiales/<vídeo>/apertura.json when the video is created.

In the pipeline (coldopen stage, `pick()`): that piece is downloaded WITH its sound, the narration starts after it
(timeline.with_opening) and the subtitles and the speaker's name are drawn over it (graphic "quote"). Nothing is chosen →
no opening, as before. Third-party footage: keep it short (credit on screen, like the quotes).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .context import RunContext
from .llm import complete_json

FILE = "apertura.json"
MAX_SECONDS = 20.0             # default `apertura.max_seconds`
LIMIT = 30.0                   # never longer, whatever the config says
CONTEXT = 15.0                 # translated lines kept around the stretch, to move its start and end on the page
YOUTUBE_ID = re.compile(r"(?:v=|youtu\.be/|shorts/|embed/|live/)([A-Za-z0-9_-]{11})|^([A-Za-z0-9_-]{11})$")

PLAN_SYSTEM = """
Eres documentalista de YouTube. El vídeo empezará con un CLIP REAL de unos segundos (antes de la voz del narrador),
con su sonido original y subtítulos: una persona real diciendo algo que engancha con el tema (una respuesta en una
entrevista o en redes, una rueda de prensa, una pregunta y su respuesta, un comentarista en el momento clave).
Te paso el título, el arranque del guion y lo que pide el autor (puede estar vacío: entonces propón tú el mejor).
Devuelve SOLO JSON:
{"about": "qué momento se busca, en 1 frase en español",
 "speaker": "quién habla (nombre real)", "role": "quién es, muy breve, en el idioma del vídeo (o null)",
 "language": "código del idioma en que HABLA en el clip (en, es, pt…)",
 "said": "lo que dice o probablemente dice, en SU idioma, si se sabe (o \"\")",
 "searches": ["2 búsquedas de YouTube en el idioma del clip para encontrar ESE vídeo: persona + situación + tema"]}
""".strip()

PICK_SYSTEM = """
Eres montador. Te paso la transcripción con segundos de un vídeo de YouTube y el momento que se busca para ABRIR otro
vídeo (antes del narrador). Elige el tramo continuo de como mucho {most:.0f} s que mejor lo cumpla: que se entienda solo
(si es una respuesta, que incluya la pregunta o lo justo para entenderla) y que termine en una frase completa.
Si el momento no está en esta transcripción, devuelve "found": false. Devuelve SOLO JSON:
{{"found": true, "start": 63.2, "end": 78.0, "why": "qué se ve y se oye, en 1 frase en español"}}
""".strip()

TRANSLATE_SYSTEM = """
Traduce al {lang} estas líneas de lo que dice alguien en un vídeo, para subtítulos: fieles, naturales y breves. Mismo
número de líneas y en el mismo orden (una línea puede seguir la frase de la anterior). Si ya están en {lang}, déjalas
casi igual, solo corregidas. Devuelve SOLO JSON: {{"lines": ["…", "…"]}}
""".strip()


def video_id(text: str) -> str | None:
    match = YOUTUBE_ID.search(str(text or "").strip())
    return (match.group(1) or match.group(2)) if match else None


def longest(ctx: RunContext) -> float:
    return min(LIMIT, float(ctx.section("apertura").get("max_seconds", MAX_SECONDS) or MAX_SECONDS))


def lines_of(words: list[tuple[str, float, float]], most_words: int = 9, gap: float = 0.7) -> list[dict[str, Any]]:
    """Timed words → subtitle lines {from, to, original}: a new line after a pause, a sentence end or `most_words`."""

    out: list[dict[str, Any]] = []
    current: list[tuple[str, float, float]] = []
    for word in words:
        if current and (word[1] - current[-1][2] > gap or len(current) >= most_words
                        or current[-1][0].rstrip().endswith((".", "?", "!"))):
            out.append(current)
            current = []
        current.append(word)
    if current:
        out.append(current)
    return [{"from": round(c[0][1], 2), "to": round(c[-1][2], 2), "original": " ".join(w for w, _, _ in c)} for c in out]


def translate(ctx: RunContext, lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Each line with "text" in the video's language (the original when the translation fails)."""

    if not lines:
        return []
    try:
        got = complete_json(ctx, stage="coldopen", section="planner", max_tokens=3000,
                            system=TRANSLATE_SYSTEM.format(lang=ctx.language),
                            user="\n".join(l["original"] for l in lines)).get("lines") or []
    except Exception:
        got = []
    ok = len(got) == len(lines)
    return [{**l, "text": str(got[i]).strip() if ok and str(got[i]).strip() else l["original"]} for i, l in enumerate(lines)]


def subtitles_of(lines: list[dict[str, Any]], start: float, end: float) -> list[dict[str, Any]]:
    """The lines inside [start, end], in seconds from the clip's start (what the pipeline draws)."""

    out = []
    for l in lines:
        a, b = max(float(l["from"]), start), min(float(l["to"]), end)
        if b - a >= 0.3 and l.get("text"):
            out.append({"text": l["text"], "from": round(a - start, 2), "to": round(b - start, 2)})
    return out


def _plan(ctx: RunContext, title: str, script: str, ask: str) -> dict[str, Any]:
    start = " ".join(script.split()[:350])
    plan = complete_json(ctx, stage="coldopen", section="planner", max_tokens=800, system=PLAN_SYSTEM,
                         user=f"Idioma del vídeo: {ctx.language}\nTÍTULO: {title or '—'}\nLO QUE PIDE EL AUTOR: {ask or '—'}\n"
                              f"ARRANQUE DEL GUION:\n{start}")
    plan["searches"] = [str(s) for s in (plan.get("searches") or []) if str(s).strip()][:2] or ([ask] if ask else [])
    return plan


def whisper(ctx: RunContext, path: Path, language: str) -> list[tuple[str, float, float]]:
    """Timed words of a local video (its first `apertura.whisper_minutes`, 20) through Whisper; [] when it fails."""

    try:
        import subprocess

        from faster_whisper import WhisperModel

        audio = path.with_suffix(".wav")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(path), "-t", str(60 * float(ctx.section("apertura").get(
            "whisper_minutes", 20))), "-vn", "-ac", "1", "-ar", "16000", str(audio)], check=True)
        model = WhisperModel(str(ctx.section("quotes").get("whisper_model", "small")), device="cpu", compute_type="int8")
        segments, _ = model.transcribe(str(audio), language=language or None, word_timestamps=True, vad_filter=True)
        words = [(w.word.strip(), w.start, w.end) for seg in segments for w in (seg.words or []) if w.word.strip()]
        audio.unlink(missing_ok=True)
        return words
    except Exception as error:
        print(f"   {path.name}: sin transcripción ({type(error).__name__}: {str(error)[:120]})")
        return []


def _stretch(ctx: RunContext, words: list[tuple[str, float, float]], plan: dict[str, Any], about: str, most: float,
             start: float | None, end: float | None) -> dict[str, Any] | None:
    """The seconds you gave, else where the expected words are said, else the LLM's pick from the transcript."""

    from .quotes import best_match

    if start is not None:
        return {"start": float(start), "end": min(float(end) if end else float(start) + most, float(start) + most),
                "why": "el tramo que has marcado"}
    said = str(plan.get("said") or "")
    match = best_match(words, said) if len(said.split()) >= 4 else None
    if match and match[2] >= float(ctx.section("apertura").get("min_match", 0.6)):
        a = max(0.0, match[0] - 1.5)          # a breath before: the question or the start of the sentence
        return {"start": a, "end": min(match[1] + 0.6, a + most), "why": f"dice «{match[3][:120]}»"}
    return _pick(ctx, words, about, most) if words else None


def _pick(ctx: RunContext, words: list[tuple[str, float, float]], about: str, most: float) -> dict[str, Any] | None:
    listing = "\n".join(f"[{l['from']:.1f}-{l['to']:.1f}] {l['original']}" for l in lines_of(words, 14))
    try:
        got = complete_json(ctx, stage="coldopen", section="planner", max_tokens=400, system=PICK_SYSTEM.format(most=most),
                            user=f"SE BUSCA: {about}\n\nTRANSCRIPCIÓN:\n{listing[:40000]}")
    except Exception:
        return None
    if not got.get("found"):
        return None
    try:
        start, end = float(got["start"]), float(got["end"])
    except (KeyError, TypeError, ValueError):
        return None
    if end <= start:
        return None
    return {"start": start, "end": min(end, start + most), "why": str(got.get("why") or "")}


def search(ctx: RunContext, *, title: str = "", script: str = "", ask: str = "", url: str = "", file: str = "",
           start: float | None = None, end: float | None = None, subtitles: bool = True, youtube: Any = None) -> dict[str, Any]:
    """Candidates for the opening: {"plan": …, "candidates": [{id|file, url, title, channel, start, end, why, speaker,
    role, lines: [{from, to, original, text}] (video seconds, CONTEXT around the stretch)}]}, best first."""

    from .quotes import transcript

    cfg = ctx.section("apertura")
    most = longest(ctx)
    given = video_id(url)
    plan = _plan(ctx, title, script, ask or (f"lo que se dice en {url}" if given else ""))
    language = str(plan.get("language") or "en")[:2]
    about = str(plan.get("about") or ask or title)
    found: list[dict[str, Any]] = []

    def candidate(words: list[tuple[str, float, float]], stretch: dict[str, Any], **fields: Any) -> dict[str, Any]:
        near = [w for w in words if w[2] >= stretch["start"] - CONTEXT and w[1] <= stretch["end"] + CONTEXT]
        return {**fields, "start": round(stretch["start"], 2), "end": round(stretch["end"], 2), "why": stretch["why"],
                "speaker": plan.get("speaker") or "", "role": plan.get("role"),
                "lines": translate(ctx, lines_of(near)) if subtitles else []}

    if file:                                       # your own video: cut here, no YouTube at all
        path = Path(file)
        if not path.is_file():
            raise FileNotFoundError("No llegó el vídeo subido: vuelve a elegirlo")
        need = subtitles or start is None
        words = whisper(ctx, path, language) if need else []
        stretch = _stretch(ctx, words, plan, about, most, start, end)
        if stretch:
            found.append(candidate(words, stretch, file=path.stem.removeprefix("apertura-"), id=None, url="",
                                   title=None, channel=None))
        return {"plan": _public(plan), "candidates": found, "maxSeconds": most}

    from .sourcing import youtube_source

    own = youtube is None
    youtube = youtube or youtube_source(ctx)
    try:
        if given:
            info = youtube.info(given)
            entries = [{"id": given, "title": info.get("title"), "channel": info.get("channel") or info.get("uploader"),
                        "duration": info.get("duration")}]
        else:
            seen: set[str] = set()
            entries = []
            for query in plan["searches"]:
                for entry in youtube.search(query)[: int(cfg.get("videos_per_search", 4))]:
                    if entry.get("id") and entry["id"] not in seen:
                        seen.add(entry["id"])
                        entries.append(entry)
        for entry in entries:
            if len(found) >= int(cfg.get("candidates", 3)):
                break
            if not given and (entry.get("duration") or 0) > 60 * float(cfg.get("max_video_minutes", 40)):
                continue
            words = transcript(ctx, youtube, entry["id"], language, float(cfg.get("whisper_minutes", 12)))
            stretch = _stretch(ctx, words, plan, about, most, start if given else None, end)
            if not stretch:
                print(f"   yt:{entry['id']}: no está el momento")
                continue
            found.append(candidate(words, stretch, id=entry["id"], url=f"https://www.youtube.com/watch?v={entry['id']}",
                                   title=entry.get("title"), channel=entry.get("channel") or entry.get("uploader") or "YouTube"))
            print(f"   Apertura: yt:{entry['id']} {stretch['start']:.1f}-{stretch['end']:.1f} s · {stretch['why'][:80]}")
    finally:
        if own:
            youtube.close()
    return {"plan": _public(plan), "candidates": found, "maxSeconds": most}


def _public(plan: dict[str, Any]) -> dict[str, Any]:
    return {k: plan.get(k) for k in ("about", "speaker", "role", "language", "said", "searches")}


def choice(candidate: dict[str, Any], start: float | None = None, end: float | None = None, most: float = LIMIT,
           subtitles: bool = True, credit: str = "") -> dict[str, Any]:
    """What is saved as apertura.json from a candidate and the start/end/subtitles/credit set on the page."""

    own = str(candidate.get("file") or "")
    vid = None if own else video_id(candidate.get("url") or candidate.get("id") or "")
    if not vid and not re.fullmatch(r"[0-9a-f]{12}|apertura\.mp4", own):
        raise ValueError("El clip de apertura no tiene ni vídeo de YouTube ni vídeo subido")
    a = float(candidate.get("start") or 0) if start is None else float(start)
    b = float(candidate.get("end") or a + most) if end is None else float(end)
    if b - a < 1:
        raise ValueError("El clip de apertura dura menos de 1 s")
    b = min(b, a + min(most, LIMIT))
    lines = candidate.get("lines") or []
    source = str(credit or "").strip() or candidate.get("channel") or ("" if own else "YouTube")
    return {"id": vid, "url": f"https://www.youtube.com/watch?v={vid}" if vid else "", "file": own or None,
            "title": candidate.get("title"), "channel": source, "start": round(a, 2), "end": round(b, 2),
            "speaker": str(candidate.get("speaker") or ""), "role": candidate.get("role"),
            "subtitles": (subtitles_of(lines, a, b) if lines else list(candidate.get("subtitles") or [])) if subtitles else []}


def chosen(ctx: RunContext) -> dict[str, Any] | None:
    path = ctx.materials_dir / FILE
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    if data.get("file"):
        return data if (ctx.materials_dir / str(data["file"])).is_file() else None
    return data if video_id(data.get("url") or data.get("id") or "") else None


def pick(ctx: RunContext, youtube: Any, out_dir: Path) -> dict[str, Any] | None:
    """The chosen opening cut WITH its sound (your file, or downloaded): the fields of schemas.OpeningClip, or None."""

    from .coldopen import normalise_with_audio
    from .ingest import probe
    from .quotes import fetch

    data = chosen(ctx)
    if not data:
        return None
    start = max(0.0, float(data.get("start") or 0))
    length = min(longest(ctx), max(1.0, float(data.get("end") or start + MAX_SECONDS) - start))
    own = ctx.materials_dir / str(data["file"]) if data.get("file") else None
    vid = None if own else video_id(data.get("url") or data["id"])
    target = out_dir / f"apertura-{vid or 'propio'}-{start:.1f}-{length:.1f}.mp4"
    if own:
        try:
            if not target.is_file() or target.stat().st_mtime < own.stat().st_mtime:
                normalise_with_audio(own, target, offset=start, duration=length, lut=None)
            info = probe(target)
        except Exception as error:
            print(f"   Apertura: no se pudo recortar {own.name} ({str(error)[-160:]})")
            info = None
    else:
        info = fetch(youtube, vid, start, length, target)
    if not info or not info.get("hasAudio", True):
        print(f"   Apertura: no se pudo sacar el clip {vid or own.name} {start:.1f} s (el vídeo empieza con la voz)")
        return None
    seconds = min(info["duration"], length)
    channel = str(data.get("channel") or "")
    print(f"   Apertura: {vid and 'yt:' + vid or own.name} {start:.1f}-{start + seconds:.1f} s · "
          f"{len(data.get('subtitles') or [])} subtítulos")
    return {"path": str(target.relative_to(ctx.root)), "candidateId": f"yt:{vid}" if vid else f"file:{own.name}",
            "url": data.get("url") or "", "title": data.get("title"), "channel": channel or None,
            "start": round(start, 3), "end": round(start + seconds, 3),
            "durationSeconds": round(seconds, 3), "width": info["width"], "height": info["height"],
            # every third-party picture carries its source (schemas.Timeline): yours without one → who speaks
            "credit": f"Fuente: {channel or data.get('speaker') or 'vídeo original'}",
            "attribution": f"\"{data.get('title')}\" — {channel}" if data.get("title") and channel else None,
            "afterSeconds": 0.0, "speaker": str(data.get("speaker") or ""), "role": data.get("role"),
            "subtitles": [x for x in (data.get("subtitles") or []) if float(x["from"]) < seconds]}


def run_request(root: Path, request: Path) -> dict[str, Any]:
    """`main.py --apertura FILE`: the web's search request (JSON) → FILE with ".resultado.json"."""

    body = json.loads(request.read_text("utf-8"))
    channel = str(body.get("channel") or "") or None
    ctx = RunContext.create("_apertura", root=root, channel=channel)
    if body.get("language") and body["language"] != "es":
        ctx.config.setdefault("align", {})["language"] = body["language"]
    out = request.with_name(request.stem + ".resultado.json")
    try:
        result = search(ctx, title=str(body.get("title") or ""), script=str(body.get("script") or ""),
                        ask=str(body.get("ask") or ""), url=str(body.get("url") or ""), file=str(body.get("file") or ""),
                        start=_seconds(body.get("start")), end=_seconds(body.get("end")),
                        subtitles=body.get("subtitles") is not False)
    except Exception as error:
        result = {"error": f"{type(error).__name__}: {str(error)[:300]}", "candidates": []}
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return result


def _seconds(value: Any) -> float | None:
    """«75», «1:15», «01:02:03» → seconds; empty → None."""

    text = str(value or "").strip()
    if not text:
        return None
    try:
        return float(sum(float(p) * 60 ** i for i, p in enumerate(reversed(text.replace(",", ".").split(":")))))
    except ValueError:
        raise ValueError(f"Segundo no válido: {text}") from None
