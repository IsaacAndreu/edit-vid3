"""Original statements with subtitles: when the script quotes a real person ("Boeing es plenamente consciente del daño
que nos ha causado", dijo Tim Clark), the video plays that person SAYING it — their interview or press conference,
with their own voice, Spanish subtitles and their name and role — right after the narrator's sentence.

1. The LLM finds the quotes in the script that were most likely said on camera, with how they were probably said in
   the original language and a YouTube search for the video.
2. For each, the first search results whose title or channel names the speaker are read through their captions
   (YouTube's automatic subtitles; else the first minutes of audio through Whisper) to find WHERE the sentence is
   said: the window of words most like the original wording.
3. That piece (≤ `quotes.max_seconds`) is downloaded with its sound; the matched words are translated into Spanish
   and timed as subtitles. Nothing found with enough confidence → no clip (the narration alone carries the quote).
Runs inside the cold-open stage (same YouTube session, same "pause the narration" mechanism as the moments).
"""

from __future__ import annotations

import html
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from .context import RunContext
from .llm import complete_json

QUOTES_SYSTEM = """
Eres documentalista. Te paso la narración en frases numeradas. Busca CITAS DIRECTAS de personas reales con nombre
(directivos, políticos, deportistas, ingenieros…) que probablemente se dijeron ANTE UNA CÁMARA: entrevista, rueda de
prensa, presentación, programa de televisión, conferencia. No cuentan lo que alguien escribió en un libro, un correo o un
comunicado, ni frases sin autor. Máximo {count}. Devuelve SOLO JSON:
{{"quotes": [{{"sentence": 12, "speaker": "Tim Clark", "role": "presidente de Emirates (como lo dice el guion, o null)",
  "said_es": "la cita tal como aparece en el guion", "language": "en",
  "said_original": "cómo lo dijo probablemente en su idioma original (traducción literal si el guion la traduce)",
  "search": "búsqueda de YouTube EN EL IDIOMA ORIGINAL para encontrar ESE vídeo: persona + tema + año/evento"}}]}}
""".strip()

TRANSLATE_SYSTEM = """
Traduce al {lang} esta transcripción de lo que dice una persona en un vídeo, para subtítulos: fiel, natural y breve.
Devuelve SOLO JSON: {{"text": "…"}}
""".strip()

WORD = re.compile(r"[\w']+", re.UNICODE)


def norm(text: str) -> list[str]:
    return [w.lower().strip("'") for w in WORD.findall(text) if w.strip("'")]


def parse_vtt(text: str) -> list[tuple[float, float, str]]:
    """Cues of a WebVTT file as (start, end, text). YouTube's automatic captions repeat each line while the next one
    is typed in: only the new words of every cue are kept."""

    def seconds(stamp: str) -> float:
        parts = stamp.replace(",", ".").split(":")
        return sum(float(p) * 60 ** i for i, p in enumerate(reversed(parts)))

    cues: list[tuple[float, float, str]] = []
    seen_tail = ""
    for block in re.split(r"\n\s*\n", text.replace("\r", "")):
        lines = block.strip().split("\n")
        timing = next((l for l in lines if "-->" in l), None)
        if not timing:
            continue
        start, end = (seconds(x.strip().split()[0]) for x in timing.split("-->"))
        body = " ".join(lines[lines.index(timing) + 1:])
        body = html.unescape(re.sub(r"<[^>]+>", "", body)).strip()
        if not body:
            continue
        words = body.split()
        # drop the words that repeat the end of what was already written (rolling captions)
        overlap = 0
        tail = seen_tail.split()
        for k in range(min(len(words), len(tail)), 0, -1):
            if tail[-k:] == words[:k]:
                overlap = k
                break
        new = words[overlap:]
        if new:
            cues.append((start, end, " ".join(new)))
            seen_tail = " ".join((seen_tail.split() + new)[-30:])
    return cues


def timed_words(cues: list[tuple[float, float, str]]) -> list[tuple[str, float, float]]:
    """Every word with its own time span, spread evenly over its cue."""

    out: list[tuple[str, float, float]] = []
    for start, end, text in cues:
        words = text.split()
        step = max(0.05, (end - start) / max(1, len(words)))
        for i, w in enumerate(words):
            out.append((w, start + i * step, start + (i + 1) * step))
    return out


def best_match(words: list[tuple[str, float, float]], quote: str) -> tuple[float, float, float, str] | None:
    """(start, end, similarity 0-1, original words) of the stretch of `words` most like `quote`."""

    wanted = norm(quote)
    if len(wanted) < 4 or not words:
        return None
    tokens = [norm(w)[0] if norm(w) else "" for w, _, _ in words]
    best: tuple[float, int, int] | None = None
    for size in range(max(3, int(len(wanted) * 0.7)), int(len(wanted) * 1.4) + 2):
        for i in range(0, max(1, len(tokens) - size + 1)):
            window = tokens[i:i + size]
            if not set(window) & set(wanted):
                continue
            matched = sum(b.size for b in SequenceMatcher(None, window, wanted, autojunk=False).get_matching_blocks())
            # mostly recall: better a clip that says the whole quote with a word too many than one that cuts it
            ratio = 0.7 * matched / len(wanted) + 0.3 * matched / len(window)
            if best is None or ratio > best[0]:
                best = (ratio, i, i + size)
    if best is None:
        return None
    ratio, a, b = best
    keep = set(wanted)
    while a < b - 1 and tokens[a] not in keep:          # trim words around the quote ("with Boeing…" → "Boeing…")
        a += 1
    while b - 1 > a and tokens[b - 1] not in keep:
        b -= 1
    return words[a][1], words[b - 1][2], ratio, " ".join(w for w, _, _ in words[a:b])


def find_quotes(ctx: RunContext, sents: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    listing = "\n".join(f"[{s['n']}] ({s['start']:.0f}s) {s['text']}" for s in sents)
    try:
        found = complete_json(ctx, stage="coldopen", section="planner", max_tokens=1500, user=listing[:60000],
                              system=QUOTES_SYSTEM.format(count=count)).get("quotes", [])
    except Exception as error:  # quotes are a bonus
        print(f"   Sin declaraciones: {str(error)[:120]}")
        return []
    out = []
    for q in found:
        try:
            n = int(q["sentence"])
            sent = sents[n]
        except (KeyError, IndexError, TypeError, ValueError):
            continue
        if not q.get("speaker") or not q.get("said_original") or not q.get("search"):
            continue
        out.append({**q, "after": sent["end"], "sentence_text": sent["text"]})
    return out


def transcript(ctx: RunContext, youtube: Any, video_id: str, language: str, minutes: float) -> list[tuple[str, float, float]]:
    """Timed words of a video: its captions, else Whisper over its first `minutes` of audio."""

    path = youtube.captions(video_id, language)
    if path is not None:
        return timed_words(parse_vtt(path.read_text("utf-8", errors="replace")))
    if not ctx.section("quotes").get("whisper", True):
        return []
    try:
        from faster_whisper import WhisperModel

        audio = youtube.download_range(video_id, 0, minutes * 60, fmt="ba[ext=m4a]/ba", prefix="qa", audio_only=True)
        model = WhisperModel(str(ctx.section("quotes").get("whisper_model", "small")), device="cpu", compute_type="int8")
        segments, _ = model.transcribe(str(audio), language=language or None, word_timestamps=True, vad_filter=True)
        return [(w.word.strip(), w.start, w.end) for s in segments for w in (s.words or []) if w.word.strip()]
    except Exception as error:
        print(f"   yt:{video_id}: sin transcripción ({type(error).__name__})")
        return []


def subtitles(ctx: RunContext, original: str, clip_seconds: float, lead: float, lang: str = "español") -> list[dict[str, Any]]:
    """The matched words in Spanish, in chunks of ≤ 8 words timed over the clip (seconds from the clip start)."""

    try:
        text = str(complete_json(ctx, stage="coldopen", section="planner", max_tokens=400, user=original,
                                 system=TRANSLATE_SYSTEM.format(lang=lang)).get("text") or "").strip()
    except Exception:
        text = ""
    words = (text or original).split()
    chunks = [" ".join(words[i:i + 8]) for i in range(0, len(words), 8)] or [original]
    span = max(0.5, clip_seconds - lead - 0.2)
    total = sum(len(c) for c in chunks) or 1
    out, at = [], lead
    for c in chunks:
        length = span * len(c) / total
        out.append({"text": c, "from": round(at, 2), "to": round(at + length, 2)})
        at += length
    return out


def fetch(youtube: Any, video_id: str, start: float, length: float, target: Path) -> dict[str, Any] | None:
    """[start, start+length] of a video WITH its sound, normalised to 1920x1080; its probe, or None."""

    from .coldopen import AUDIO_FORMAT, normalise_with_audio
    from .ingest import probe

    try:
        if not target.is_file():
            source = youtube.download_range(video_id, start, start + length + 0.5, fmt=AUDIO_FORMAT, prefix="hdav", audio=True)
            normalise_with_audio(source, target, offset=start - float(source.stem.split("_")[1]), duration=length, lut=None)
        info = probe(target)
        return info if info["hasAudio"] else None
    except Exception as error:   # one statement fewer
        print(f"   yt:{video_id}: {str(error)[-120:]}")
        return None


def pick_quotes(ctx: RunContext, youtube: Any, out_dir: Path) -> list[dict[str, Any]]:
    """Clips of real statements: [{path, …ColdOpenClip fields, afterSeconds, speaker, role, subtitles}]."""

    from .shorts import sentences
    from .sourcing.common import tokens

    cfg = ctx.section("quotes")
    count = int(cfg.get("count", 0) or 0)
    if count <= 0:
        return []
    sents = sentences(ctx.read_json("words.json")["words"])
    longest = float(cfg.get("max_seconds", 12))
    found = []
    for q in find_quotes(ctx, sents, count):
        surname = tokens(q["speaker"].split()[-1])
        language = str(q.get("language") or "en")[:2]
        done = False
        for entry in youtube.search(str(q["search"]))[: int(cfg.get("videos_per_quote", 4))]:
            if done:
                break
            title = f"{entry.get('title') or ''} {entry.get('channel') or entry.get('uploader') or ''}"
            if not surname <= tokens(title) or (entry.get("duration") or 0) > 60 * float(cfg.get("max_video_minutes", 40)):
                continue
            words = transcript(ctx, youtube, entry["id"], language, float(cfg.get("whisper_minutes", 12)))
            match = best_match(words, str(q["said_original"]))
            if not match or match[2] < float(cfg.get("min_match", 0.55)):
                continue
            start, end, score, original = match
            start, end = max(0.0, start - 0.3), min(end + 0.5, start + longest)
            channel = entry.get("channel") or entry.get("uploader") or "YouTube"
            target = out_dir / f"q{len(found) + 1:02d}-{entry['id']}-{start:.1f}.mp4"
            info = fetch(youtube, entry["id"], start, end - start, target)
            if not info:
                continue
            found.append({"path": str(target.relative_to(ctx.root)), "candidateId": f"yt:{entry['id']}",
                          "url": f"https://www.youtube.com/watch?v={entry['id']}", "title": entry.get("title"),
                          "channel": channel, "start": round(start, 3), "end": round(start + info["duration"], 3),
                          "durationSeconds": round(info["duration"], 3), "width": info["width"], "height": info["height"],
                          "credit": f"Fuente: {channel}", "attribution": f"\"{entry.get('title')}\" — {channel}",
                          "afterSeconds": round(q["after"], 3), "speaker": q["speaker"], "role": q.get("role"),
                          "match": round(score, 2), "subtitles": subtitles(ctx, original, info["duration"], 0.3)})
            print(f"   Declaración de {q['speaker']}: {entry['id']} {start:.1f}-{end:.1f} s (parecido {score:.2f})")
            done = True
        if not done:
            print(f"   Declaración de {q['speaker']}: no se encontró el vídeo donde lo dice")
    return found
