"""Stage 1 — align the narration with guion.txt.

Whisper only provides timings. The words in words.json are always the words of
the script: every script token is matched against Whisper's words with a
sequence alignment, and script tokens Whisper did not hear (numbers written as
digits, names spelled differently...) get interpolated timings from their
neighbours. Lines starting with ``## `` are chapter headings.
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass

from .context import RunContext
from .costs import record_cost
from .schemas import AlignmentStats, Chapter, Word, WordsFile
from .whisper_local import transcribe


STAGE = "align"
OUTPUT = "words.json"
_SENTENCE_END = re.compile(r"[.!?…:;][\"'»”)]*$")
OPENAI_WHISPER_USD_PER_MINUTE = 0.006


@dataclass
class ScriptToken:
    text: str
    norm: str
    sentence_end: bool
    heading: int | None  # index into headings when the token belongs to a "## " line


def normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(ch for ch in decomposed if ch.isalnum() and not unicodedata.combining(ch))


def parse_script(script: str) -> tuple[list[ScriptToken], list[str]]:
    tokens: list[ScriptToken] = []
    headings: list[str] = []
    for raw_line in script.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        heading_index: int | None = None
        if line.startswith("## "):
            line = line[3:].strip()
            if not line:
                continue
            headings.append(line)
            heading_index = len(headings) - 1
        line_tokens: list[ScriptToken] = []
        for piece in line.split():
            norm = normalize(piece)
            if not norm:
                # Punctuation-only token (—, «, ...): glue it to the previous word's text.
                if line_tokens:
                    line_tokens[-1].text += f" {piece}"
                    line_tokens[-1].sentence_end = bool(_SENTENCE_END.search(piece)) or line_tokens[-1].sentence_end
                continue
            line_tokens.append(
                ScriptToken(text=piece, norm=norm, sentence_end=bool(_SENTENCE_END.search(piece)), heading=heading_index)
            )
        if line_tokens:
            line_tokens[-1].sentence_end = True
        tokens.extend(line_tokens)
    return tokens, headings


def _distribute(lengths: list[int], start: float, end: float) -> list[tuple[float, float]]:
    total = sum(max(1, n) for n in lengths)
    span = max(0.0, end - start)
    cursor = start
    result = []
    for n in lengths:
        width = span * max(1, n) / total
        result.append((cursor, cursor + width))
        cursor += width
    return result


def align_tokens(
    tokens: list[ScriptToken],
    whisper_words: list[dict],
    duration: float,
) -> tuple[list[tuple[float, float]], list[bool]]:
    """Return per-token (start, end) and whether each token was actually heard."""

    heard = [(normalize(w["word"]), float(w["start"]), float(w["end"])) for w in whisper_words]
    heard = [w for w in heard if w[0]]
    script_norm = [t.norm for t in tokens]
    heard_norm = [w[0] for w in heard]

    times: list[tuple[float, float]] = [(0.0, 0.0)] * len(tokens)
    matched = [False] * len(tokens)
    matcher = difflib.SequenceMatcher(None, script_norm, heard_norm, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "insert":
            continue  # Whisper heard something that is not in the script: the script wins.
        if tag == "equal":
            for offset in range(i2 - i1):
                _, start, end = heard[j1 + offset]
                times[i1 + offset] = (start, end)
                matched[i1 + offset] = True
            continue
        if tag == "replace" and (i2 - i1) == (j2 - j1):
            # Same number of words, different spelling: keep 1:1 timings.
            for offset in range(i2 - i1):
                _, start, end = heard[j1 + offset]
                times[i1 + offset] = (start, end)
                similarity = difflib.SequenceMatcher(None, script_norm[i1 + offset], heard_norm[j1 + offset]).ratio()
                matched[i1 + offset] = similarity >= 0.6
            continue
        if tag == "replace":
            span_start, span_end = heard[j1][1], heard[j2 - 1][2]
        else:  # delete: script words with no audio counterpart
            span_start = heard[j1 - 1][2] if j1 > 0 else 0.0
            span_end = heard[j1][1] if j1 < len(heard) else duration
        lengths = [len(script_norm[i]) for i in range(i1, i2)]
        for offset, span in enumerate(_distribute(lengths, span_start, span_end)):
            times[i1 + offset] = span

    # Enforce monotonic, in-range timings.
    fixed: list[tuple[float, float]] = []
    previous_start = 0.0
    for start, end in times:
        start = min(max(start, previous_start), duration)
        end = min(max(end, start), duration)
        fixed.append((start, end))
        previous_start = start
    return fixed, matched


def build_words_file(
    *,
    slug: str,
    title: str,
    script: str,
    raw: dict,
    provider: str,
    model: str,
    language: str,
) -> WordsFile:
    tokens, headings = parse_script(script)
    if not tokens:
        raise ValueError("guion.txt no contiene palabras.")
    duration = max(float(raw.get("duration") or 0.0), max((float(w["end"]) for w in raw["words"]), default=0.0))
    times, matched = align_tokens(tokens, raw["words"], duration)

    heading_spoken: dict[int, bool] = {}
    for heading_index in range(len(headings)):
        flags = [matched[i] for i, t in enumerate(tokens) if t.heading == heading_index]
        heading_spoken[heading_index] = bool(flags) and sum(flags) / len(flags) >= 0.6

    words: list[Word] = []
    chapter_first_word: dict[int, int] = {}
    pending_chapters: list[int] = []
    body_total = body_matched = 0
    for i, token in enumerate(tokens):
        if token.heading is not None and not heading_spoken[token.heading]:
            if token.heading not in pending_chapters and token.heading not in chapter_first_word:
                pending_chapters.append(token.heading)
            continue
        if token.heading is not None and token.heading not in chapter_first_word:
            chapter_first_word[token.heading] = len(words)
        for heading_index in pending_chapters:
            chapter_first_word[heading_index] = len(words)
        pending_chapters.clear()
        if token.heading is None:
            body_total += 1
            body_matched += int(matched[i])
        start, end = times[i]
        words.append(
            Word(
                index=len(words),
                text=token.text,
                start=round(start, 3),
                end=round(end, 3),
                matched=matched[i],
                sentenceEnd=token.sentence_end,
            )
        )

    chapters = [
        Chapter(
            title=headings[h],
            wordIndex=chapter_first_word[h],
            start=words[chapter_first_word[h]].start,
            spoken=heading_spoken[h],
        )
        for h in sorted(chapter_first_word)
    ]
    return WordsFile(
        slug=slug,
        title=title,
        language=language,
        durationSeconds=round(duration, 3),
        words=words,
        chapters=chapters,
        alignment=AlignmentStats(
            provider=provider,
            model=model,
            scriptWords=body_total,
            whisperWords=len(raw["words"]),
            matchedWords=body_matched,
            matchRatio=round(body_matched / body_total, 4) if body_total else 0.0,
        ),
    )


def read_title(ctx: RunContext) -> str:
    """Working title: titulo.txt if there is one (optional), else the folder name. The YouTube titles themselves
    are written from the script in the package stage either way."""

    path = ctx.materials_dir / "titulo.txt"
    if path.is_file():
        title = path.read_text(encoding="utf-8").strip()
        if title:
            return title
    return ctx.slug


def inputs(ctx: RunContext) -> list:
    return [ctx.materials_dir / "guion.txt", ctx.materials_dir / "voz.mp3", ctx.materials_dir / "titulo.txt"]


def run(ctx: RunContext) -> None:
    cfg = ctx.section("align")
    provider = str(cfg.get("provider", "local"))
    model = str(cfg.get("model", "medium")) if provider == "local" else "whisper-1"
    language = str(cfg.get("language", "es"))
    audio = ctx.materials_dir / "voz.mp3"
    script_path = ctx.materials_dir / "guion.txt"
    for required in (audio, script_path):
        if not required.is_file():
            raise FileNotFoundError(f"Falta {required}")

    print(f"   Whisper ({provider}/{model})…")
    raw, cached = transcribe(
        audio,
        cache_dir=ctx.cache_dir,
        provider=provider,
        model=model,
        language=language,
        compute_type=str(cfg.get("compute_type", "int8")),
        openai_api_key=ctx.env("OPENAI_API_KEY") if provider == "openai" else "",
        device=str(cfg.get("device", "auto")),      # auto: an NVIDIA card if it works, else the processor
    )
    if provider == "openai" and not cached:
        record_cost(
            ctx,
            stage=STAGE,
            provider="openai",
            operation="whisper-1",
            usd=raw["duration"] / 60 * OPENAI_WHISPER_USD_PER_MINUTE,
        )
    print(f"   {len(raw['words'])} palabras de Whisper{' (caché)' if cached else ''}")

    words_file = build_words_file(
        slug=ctx.slug,
        title=read_title(ctx),
        script=script_path.read_text(encoding="utf-8"),
        raw=raw,
        provider=provider,
        model=model,
        language=language,
    )
    stats = words_file.alignment
    min_ratio = float(cfg.get("min_match_ratio", 0.8))
    if stats.matchRatio < min_ratio:
        raise RuntimeError(
            f"Solo el {stats.matchRatio:.0%} de las palabras del guion se oyen en la voz "
            f"(mínimo {min_ratio:.0%}). ¿Corresponden guion.txt y voz.mp3?"
        )
    ctx.write_json(OUTPUT, words_file.model_dump())
    print(
        f"   {stats.scriptWords} palabras del guion, {stats.matchRatio:.1%} alineadas con el audio; "
        f"{len(words_file.chapters)} capítulos ({words_file.durationSeconds:.1f} s)"
    )
    if not words_file.chapters:
        print("   Aviso: el guion no tiene líneas '## '; no hay capítulos marcados.")


def validate(ctx: RunContext) -> bool:
    WordsFile.model_validate(ctx.read_json(OUTPUT))
    return True
