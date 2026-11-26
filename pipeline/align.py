"""Stage 1 — align the narration with guion.txt.

Whisper only provides timings. The words in words.json are always the words of
the script: every script token is matched against Whisper's words with a
sequence alignment, and script tokens Whisper did not hear (numbers written as
digits, names spelled differently...) get interpolated timings from their
neighbours. Lines starting with ``## `` are chapter headings.
"""

from __future__ import annotations

import difflib
import os
import re
import shutil
import subprocess
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
WORD_SECONDS = 1.2              # no spoken word lasts longer: Whisper stretches the last one over the silence after it
TAIL_KEEP_SECONDS = 1.0         # silence kept after the last word


def speech_end(words: list[Word]) -> float:
    """When the voice stops: the end of the last word, never more than WORD_SECONDS after it starts."""

    return max((min(w.end, w.start + WORD_SECONDS) for w in words), default=0.0)


MAX_PAUSE_SECONDS = 4.0         # a longer pause between two words of the script is cut out of the voice
PAUSE_KEEP_SECONDS = 1.0        # what is left of it


def long_pauses(words: list[Word], max_pause: float = MAX_PAUSE_SECONDS,
                keep: float = PAUSE_KEEP_SECONDS) -> list[tuple[float, float]]:
    """The stretches (start, end) of the voice to cut: pauses between two words longer than `max_pause`, each one
    left at `keep` seconds. Only two shots can share a pause (the one before and the one after, ≤ 5 s each), so a
    longer one can never be cut into shots (newgym11: 27 s of nothing after «nada.» made a 13.67 s shot and the
    planner fail on every retry)."""

    cuts: list[tuple[float, float]] = []
    for a, b in zip(words, words[1:]):
        end = min(a.end, a.start + WORD_SECONDS)
        if max_pause > 0 and b.start - end > max_pause:
            cuts.append((round(end + keep / 2, 3), round(b.start - keep / 2, 3)))
    return cuts


def shifted(t: float, cuts: list[tuple[float, float]]) -> float:
    """A time of the old voice in the voice without the cuts."""

    return round(t - sum(min(t, end) - start for start, end in cuts if t > start), 3)


def without_pauses(words_file: WordsFile, cuts: list[tuple[float, float]]) -> WordsFile:
    words = [w.model_copy(update={"start": shifted(w.start, cuts), "end": shifted(w.end, cuts)}) for w in words_file.words]
    chapters = [c.model_copy(update={"start": words[c.wordIndex].start}) for c in words_file.chapters]
    return words_file.model_copy(update={"words": words, "chapters": chapters,
                                         "durationSeconds": shifted(words_file.durationSeconds, cuts)})


def cut_voice(source, target, cuts: list[tuple[float, float]]) -> float:
    """`source` without the stretches in `cuts`, to `target` (mp3); returns the new length. Each part kept is cut with
    atrim and joined with concat: `aselect` with an expression did nothing on some ffmpeg builds (GitHub's CI kept
    the 30 s) while the words were moved anyway: voice and picture out of step."""

    kept = _kept(cuts)
    parts = []
    for i, (a, b) in enumerate(kept):
        end = "" if b >= 1e8 else f":end={b:.3f}"
        parts.append(f"[0:a]atrim=start={a:.3f}{end},asetpts=PTS-STARTPTS[k{i}]")
    graph = ";".join(parts) + ";" + "".join(f"[k{i}]" for i in range(len(kept))) + f"concat=n={len(kept)}:v=0:a=1[out]"
    done = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i", str(source),
                           "-filter_complex", graph, "-map", "[out]", "-c:a", "libmp3lame", "-q:a", "2", str(target)],
                          capture_output=True, timeout=900)
    if done.returncode != 0:
        raise RuntimeError(f"ffmpeg no pudo quitar las pausas de la voz: {done.stderr.decode(errors='replace')[-300:]}")
    return _seconds(target)


def _seconds(path) -> float:
    done = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                          capture_output=True, text=True, timeout=120)
    try:
        return float(done.stdout.strip())
    except ValueError:
        return 0.0


def _kept(cuts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    kept, at = [], 0.0
    for start, end in cuts:
        kept.append((at, start))
        at = end
    return kept + [(at, 1e9)]


def trimmed_duration(words: list[Word], duration: float) -> float:
    """The length the video keeps: silence or music after the last word is cut to TAIL_KEEP_SECONDS, because no
    shot can be cut where nothing is said (newgym11: 13.7 s of tail made the last shot 13.67 s and the planner
    fail on every retry)."""

    return min(duration, round(speech_end(words) + TAIL_KEEP_SECONDS, 3)) if words else duration


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

    end = trimmed_duration(words, duration)
    if end < duration:
        words = [w.model_copy(update={"end": round(min(w.end, end), 3), "start": round(min(w.start, end), 3)}) for w in words]
        duration = end

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

    from .tts import timings

    spoken = timings(audio) if cfg.get("use_tts_timings", True) else None
    if spoken is not None:                  # a GenAIPro voice: its subtitles give the times, no Whisper needed
        words_file = build_words_file(slug=ctx.slug, title=read_title(ctx), script=script_path.read_text(encoding="utf-8"),
                                      raw=spoken, provider="genaipro", model="subtitles", language=language)
        if words_file.alignment.matchRatio >= max(float(cfg.get("min_match_ratio", 0.8)), 0.85):
            print(f"   Tiempos de las palabras de GenAIPro (sin Whisper): {len(spoken['words'])} palabras")
            _finish(ctx, words_file)
            return
        print(f"   Los tiempos de GenAIPro solo cuadran un {words_file.alignment.matchRatio:.0%}: uso Whisper")

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
        threads=cfg.get("cpu_threads"),             # half the cores by default: it runs beside a render (fase 5.5)
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
    _finish(ctx, words_file)


def _finish(ctx: RunContext, words_file: WordsFile) -> None:
    stats = words_file.alignment
    min_ratio = float(ctx.section("align").get("min_match_ratio", 0.8))
    if stats.matchRatio < min_ratio:
        raise RuntimeError(
            f"Solo el {stats.matchRatio:.0%} de las palabras del guion se oyen en la voz "
            f"(mínimo {min_ratio:.0%}). ¿Corresponden guion.txt y voz.mp3?"
        )
    cuts = long_pauses(words_file.words, float(ctx.section("align").get("max_pause_seconds", MAX_PAUSE_SECONDS)))
    if cuts:
        # the voice itself loses them (the original stays as voz.original.mp3), so picture and sound stay together
        audio = ctx.materials_dir / "voz.mp3"
        backup = ctx.materials_dir / "voz.original.mp3"
        if not backup.exists():
            shutil.copy2(audio, backup)
        temporary = audio.with_name("voz.sin-pausas.mp3")
        before = _seconds(audio)
        expected = before - sum(b - a for a, b in cuts)
        got = cut_voice(audio, temporary, cuts)
        if before and abs(got - expected) <= 0.5:
            os.replace(temporary, audio)
            words_file = without_pauses(words_file, cuts)
            print("   Pausas largas quitadas de la voz: " + ", ".join(f"{b - a:.1f} s en {a:.0f} s" for a, b in cuts)
                  + " (la voz de antes: voz.original.mp3)")
        else:                   # the cut did not come out as asked: the voice and the words stay as they were, together
            temporary.unlink(missing_ok=True)
            raise RuntimeError(f"No se pudieron quitar las pausas largas de la voz (salió de {got:.1f} s y debía "
                               f"quedar en {expected:.1f} s): pon align.max_pause_seconds: 0 para dejarlas")
    ctx.write_json(OUTPUT, words_file.model_dump())
    print(
        f"   {stats.scriptWords} palabras del guion, {stats.matchRatio:.1%} alineadas con el audio; "
        f"{len(words_file.chapters)} capítulos ({words_file.durationSeconds:.1f} s)"
    )
    if not words_file.chapters:
        print("   Aviso: el guion no tiene líneas '## '; no hay capítulos marcados.")


def validate(ctx: RunContext) -> bool:
    words_file = WordsFile.model_validate(ctx.read_json(OUTPUT))
    # made before the tail was trimmed: again (Whisper's transcription is cached, so it costs nothing)
    if long_pauses(words_file.words, float(ctx.section("align").get("max_pause_seconds", MAX_PAUSE_SECONDS))):
        return False                        # a pause no shot can be cut in: the voice loses it
    voice, backup = ctx.materials_dir / "voz.mp3", ctx.materials_dir / "voz.original.mp3"
    if backup.is_file() and voice.is_file() and abs(_seconds(voice) - _seconds(backup)) < 0.5:
        return False                        # the old cut (aselect) moved the words but not the voice: again, properly
    return trimmed_duration(words_file.words, words_file.durationSeconds) >= words_file.durationSeconds - 1e-3
