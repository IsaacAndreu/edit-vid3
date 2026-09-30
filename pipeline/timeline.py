"""Stage 8 — build work/<slug>/timeline.json, the props of the Remotion composition.

Merges shots (what each shot shows), stage-6 media and stage-7 fallback media into a
frame-accurate list of shots, plus:
- groups: consecutive datacard/split shots sharing a panel (rows revealed step by step)
  and stat shots (one continuous number while the b-roll keeps cutting underneath);
- questions: the script's questions (¿…?) as floating text in the middle, words appearing as they are
  spoken; questions a breath apart are shown together;
- audio: the narration, optional music from assets/music/ (ducked while the voice speaks)
  and optional SFX from assets/sfx/ (whoosh on chapters, pop on data).

work/<slug>/ is Remotion's public dir, so every path here is relative to it; the voice
and any music/SFX are copied into work/<slug>/audio/.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

import hashlib

from .context import RunContext
from .llm import complete_json
from .ingest import probe
from .schemas import (
    MusicPart,
    FallbackFile,
    IngestFile,
    PanelStep,
    ShotsFile,
    Timeline,
    TimelineAudio,
    ColdOpenFile,
    TimelineClipAudio,
    TimelineGroup,
    TimelineLabel,
    TimelineMedia,
    TimelineSfx,
    TimelineShot,
    TimelineShake,
    TimelineTransition,
    WordsFile,
)
from .schemas import MAX_THIRD_PARTY_SECONDS
from .sourcing import needs_footage
from .sourcing.common import tokens


STAGE = "timeline"
OUTPUT = "timeline.json"
AUDIO_EXTENSIONS = (".mp3", ".wav", ".m4a", ".aac", ".ogg")


def speech_segments(words: WordsFile, fps: int, max_gap: float = 0.5) -> list[tuple[int, int]]:
    segments: list[list[float]] = []
    for word in words.words:
        if segments and word.start - segments[-1][1] <= max_gap:
            segments[-1][1] = max(segments[-1][1], word.end)
        else:
            segments.append([word.start, word.end])
    return [(round(a * fps), max(round(a * fps) + 1, round(b * fps))) for a, b in segments]


OPEN_PUNCT = "«“\"'(¡"
CLOSE_PUNCT = "»”\"')"


def question_spans(words: WordsFile) -> list[tuple[int, int]]:
    """(first, last) word indexes of each question in the script."""

    spans: list[tuple[int, int]] = []
    start: int | None = None
    sentence = 0
    for i, word in enumerate(words.words):
        text = word.text.lstrip(OPEN_PUNCT)
        if text.startswith("¿"):
            start = i
        tail = word.text.rstrip(CLOSE_PUNCT)
        if tail.endswith("?"):
            spans.append((start if start is not None else sentence, i))
            start = None
        if tail.endswith((".", "!", "?", ":", ";", "…")):
            sentence = i + 1
    return spans


QUESTION_STARTS = re.compile(
    r"^(¿|quieres|queréis|sabías|sabes|sabéis|te has|os habéis|alguna vez|has |habéis|qué|que harías|cómo|como es posible|"
    r"por qué|porque |cuánto|cuántos|cuántas|cuál|quién|dónde|crees|te imaginas|y si |podrías|puedes|es posible|"
    r"do you|did you|have you|would you|could you|can you|what|why|how|who|where|which|is it|are you|ever wondered)",
    re.IGNORECASE)


def opening_question(words: WordsFile, cfg: dict[str, Any]) -> tuple[int, int] | None:
    """The first sentence when it asks the viewer something, with or without question marks
    ("Quieres ser dueño de un casino."); timeline.opening_question: auto | true | false."""

    mode = str(cfg.get("opening_question", "auto")).lower()
    if mode in ("false", "no", "0") or not words.words:
        return None
    end = next((i for i, w in enumerate(words.words) if w.sentenceEnd or w.text.rstrip(CLOSE_PUNCT).endswith((".", "!", "?", "…"))),
               len(words.words) - 1)
    sentence = " ".join(w.text for w in words.words[: end + 1])
    asks = sentence.rstrip(CLOSE_PUNCT).endswith("?") or bool(QUESTION_STARTS.match(sentence.lstrip(OPEN_PUNCT + "¿")))
    if end + 1 > int(cfg.get("question_max_words", 30)) or not (asks or mode in ("true", "yes", "1")):
        return None
    return 0, end


def _as_question(texts: list[str], spanish: bool) -> list[str]:
    """Question marks on screen even if the script has none."""

    out = list(texts)
    last = out[-1].rstrip(".…!,;:")
    out[-1] = last if last.endswith("?") else last + "?"
    if spanish and not out[0].lstrip(OPEN_PUNCT).startswith("¿"):
        out[0] = "¿" + out[0][:1].upper() + out[0][1:]
    return out


def question_groups(words: WordsFile, shots: list[TimelineShot], groups: list[TimelineGroup], fps: int,
                    total: int, cfg: dict[str, Any], spanish: bool = True) -> list[TimelineGroup]:
    """Floating questions (centred text) that never overlap a data group or a chapter title. A video
    that opens with a question shows it whole from the very first frame ("q-open")."""

    if not cfg.get("questions", True):
        return []
    opening = opening_question(words, cfg)
    merge_gap = float(cfg.get("question_merge_gap", 2.5))
    hold = round(float(cfg.get("question_hold", 1.2)) * fps)
    lead = 3
    max_words = int(cfg.get("question_max_words", 30))
    merged: list[list[int]] = []
    for a, b in question_spans(words):
        if merged and words.words[a].start - words.words[merged[-1][1]].end <= merge_gap:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    blocked = sorted([(g.from_, g.from_ + g.durationInFrames) for g in groups]
                     + [(s.from_, s.from_ + s.durationInFrames) for s in shots if s.type == "chapter"])
    result: list[TimelineGroup] = []
    if opening:
        a, b = opening
        spoken_end = round(words.words[b].end * fps)
        end = min([total, spoken_end + hold] + [x for x, _ in blocked if x > 0])
        texts = _as_question([w.text for w in words.words[a : b + 1]], spanish)
        result.append(TimelineGroup.model_validate({
            "id": "q-open", "kind": "question", "from": 0, "durationInFrames": max(fps, end),
            "words": [{"text": t, "from": 0} for t in texts],        # whole question at once, from frame 0
        }))
        merged = [m for m in merged if m[1] < a or m[0] > b]
    for a, b in merged:
        if b - a + 1 > max_words:
            continue
        start = max(0, round(words.words[a].start * fps) - lead)
        spoken_end = round(words.words[b].end * fps)
        if any(x < spoken_end and start < y for x, y in blocked):
            continue
        end = min([total, spoken_end + hold] + [x for x, _ in blocked if x >= spoken_end])
        if result:
            previous = result[-1]
            if previous.from_ + previous.durationInFrames > start:
                previous.durationInFrames = max(1, start - previous.from_)
        result.append(TimelineGroup.model_validate({
            "id": f"q{len(result) + 1:02d}", "kind": "question", "from": start, "durationInFrames": end - start,
            "words": [{"text": w.text, "from": max(0, round(w.start * fps) - start)} for w in words.words[a : b + 1]],
        }))
    return result


def with_moments(timeline: Timeline, moments: list[tuple[str, float, float, str, int, int]], fps: int,
                 volume: float = 1.0) -> Timeline:
    """Pause the narration after peak sentences: (src, voice seconds, clip seconds, credit, w, h).

    Called before the cold open, when frames still equal voice frames. The pause goes at the shot
    boundary nearest the end of the sentence (within 1.5 s) that does not cut a panel or label;
    everything after it moves by the clip's length and the voice gets a gap there.
    """

    for src, after, seconds, credit, width, height in sorted(moments, key=lambda m: m[1]):
        target = round(after * fps) + sum(b for _, b in timeline.audio.voiceGaps)
        overlays = [(g.from_, g.from_ + g.durationInFrames) for g in [*timeline.groups, *timeline.labels]]
        options = [s.from_ for s in timeline.shots[1:] if abs(s.from_ - target) <= 1.5 * fps
                   and not any(a < s.from_ < b for a, b in overlays)]
        if not options:
            continue
        at = min(options, key=lambda f: abs(f - target))
        frames = max(1, min(round(seconds * fps), int(MAX_THIRD_PARTY_SECONDS * fps)))
        n = len(timeline.audio.voiceGaps) + 1

        def moved(item):
            return item.model_copy(update={"from_": item.from_ + frames}) if item.from_ >= at else item

        index = next(i for i, s in enumerate(timeline.shots) if s.from_ == at)
        pause = TimelineShot.model_validate({
            "id": f"m{n:02d}", "type": "broll", "from": at, "durationInFrames": frames, "text": "",
            "media": {"src": src, "kind": "video", "source": "youtube", "credit": credit, "layout": "full",
                      "width": width, "height": height},
            "coldOpen": True,
        })
        speech = []
        for a, b in timeline.audio.speech:
            if b <= at:
                speech.append((a, b))
            elif a >= at:
                speech.append((a + frames, b + frames))
            else:
                speech += [(a, at), (at + frames, b + frames)]
        voice_at = at - sum(b for _, b in timeline.audio.voiceGaps)
        audio = timeline.audio.model_copy(update={
            "clips": [*[moved(c) for c in timeline.audio.clips],
                      TimelineClipAudio.model_validate({"src": src, "from": at, "durationInFrames": frames, "volume": volume})],
            "speech": speech, "sfx": [moved(x) for x in timeline.audio.sfx],
            "voiceGaps": [*timeline.audio.voiceGaps, (voice_at, frames)],
        })
        shots = [*timeline.shots[:index], pause, *[moved(s) for s in timeline.shots[index:]]]
        timeline = Timeline.model_validate({
            **timeline.model_dump(by_alias=True),
            "durationInFrames": timeline.durationInFrames + frames,
            "shots": [s.model_dump(by_alias=True) for s in shots],
            "groups": [moved(g).model_dump(by_alias=True) for g in timeline.groups],
            "labels": [moved(label).model_dump(by_alias=True) for label in timeline.labels],
            "audio": audio.model_dump(by_alias=True),
        })
    return timeline


def with_cold_open(timeline: Timeline, clips: list[tuple[str, float, str, int, int]], fps: int,
                   volume: float = 1.0) -> Timeline:
    """Put the cold-open clips (src, seconds, credit, width, height) first, with their original
    sound, and push everything narrated — shots, overlays, SFX, speech and the voice — after them."""

    if not clips:
        return timeline
    cold: list[TimelineShot] = []
    sounds: list[TimelineClipAudio] = []
    cursor = 0
    for i, (src, seconds, credit, width, height) in enumerate(clips, start=1):
        frames = max(1, min(round(seconds * fps), int(MAX_THIRD_PARTY_SECONDS * fps)))
        cold.append(TimelineShot.model_validate({
            "id": f"c{i:02d}", "type": "broll", "from": cursor, "durationInFrames": frames, "text": "",
            "media": {"src": src, "kind": "video", "source": "youtube", "credit": credit, "layout": "card",
                      "width": width, "height": height},
            "coldOpen": True,
        }))
        sounds.append(TimelineClipAudio.model_validate({"src": src, "from": cursor, "durationInFrames": frames,
                                                         "volume": volume}))
        cursor += frames
    offset = cursor

    def moved(item):
        return item.model_copy(update={"from_": item.from_ + offset})

    audio = timeline.audio.model_copy(update={
        "voiceFrom": timeline.audio.voiceFrom + offset,
        "clips": [*sounds, *[moved(c) for c in timeline.audio.clips]],
        "speech": [(a + offset, b + offset) for a, b in timeline.audio.speech],
        "sfx": [moved(x) for x in timeline.audio.sfx],
    })
    return Timeline.model_validate({
        **timeline.model_dump(by_alias=True),
        "durationInFrames": timeline.durationInFrames + offset,
        "shots": [s.model_dump(by_alias=True) for s in [*cold, *[moved(x) for x in timeline.shots]]],
        "groups": [moved(g).model_dump(by_alias=True) for g in timeline.groups],
        "labels": [moved(label).model_dump(by_alias=True) for label in timeline.labels],
        "audio": audio.model_dump(by_alias=True),
    })


def _size(path: Path) -> tuple[int | None, int | None]:
    try:
        info = probe(path)
        return info["width"] or None, info["height"] or None
    except Exception:
        return None, None


def choose_layout(shot_id: str, shot_type: str, media: TimelineMedia, card_share: float, narrow: str = "card") -> str:
    """Framed card for stills and for sources that are not widescreen (kept uncropped), plus a
    deterministic share of ordinary clips for variety, as the channel style does. With
    `narrow="archive"` (timeline.narrow_layout) narrow clips stay full screen between black bars,
    with a film look, like TV archive footage."""

    if shot_type in ("chapter", "split"):
        return "full"
    if media.kind == "image":   # photos alternate between the framed card and the parallax move
        return "parallax" if int(hashlib.sha1(shot_id.encode()).hexdigest()[8:16], 16) % 2 else "card"
    if media.width and media.height and media.width / media.height < 1.6:
        return "archive" if narrow == "archive" and media.kind == "video" else "card"
    bucket = int(hashlib.sha1(shot_id.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    return "card" if bucket < card_share else "full"


def person_cards(ctx: RunContext, shots_file: ShotsFile, shots: list[TimelineShot], groups: list[TimelineGroup],
                 fps: int) -> None:
    """The first plain shot where the voice names each person (the protagonist after the hook) becomes
    their presentation card: the cutout from the people stage, with its own credit."""

    path = ctx.work_dir / "people.json"
    if not path.is_file():
        return
    hook = round(float(ctx.section("judge").get("hook_seconds", 30)) * fps)
    covered = [(g.from_, g.from_ + g.durationInFrames) for g in groups]
    taken: set[str] = set()
    for index, person in enumerate(ctx.read_json("people.json").get("people", [])):
        surname = tokens(person["name"].split()[-1])
        for shot in shots:
            start, end = shot.from_, shot.from_ + shot.durationInFrames
            if (shot.id in taken or shot.type != "broll" or shot.groupId or shot.media is None
                    or shot.durationInFrames < round(1.5 * fps) or (index == 0 and start < hook)
                    or any(a < end and start < b for a, b in covered) or not surname <= tokens(shot.text)):
                continue
            size = _size(ctx.work_dir / person["image"])
            shot.media = TimelineMedia(src=person["image"], kind="image", source=person.get("source") or "web",
                                       credit=person.get("credit"), layout="person", caption=person["name"],
                                       width=size[0], height=size[1])
            taken.add(shot.id)
            break


def place_labels(shots_file: ShotsFile, shots: list[TimelineShot], groups: list[TimelineGroup], fps: int,
                 cfg: dict[str, Any]) -> list[TimelineLabel]:
    """Lower-left tags: the place/date of each story event on its first plain shot, and the names and
    scores the planner marked. Never over a panel, a stat, a question or a chapter title, never two at once."""

    if not cfg.get("labels", True):
        return []
    hold = round(float(cfg.get("label_seconds", 2.5)) * fps)
    busy = [(g.from_, g.from_ + g.durationInFrames) for g in groups]
    busy += [(s.from_, s.from_ + s.durationInFrames) for s in shots
             if s.type == "chapter" or (s.media and s.media.layout == "person")]
    wanted: list[tuple[int, str, str]] = []            # (frame, kind, text)
    by_id = {s.id: s for s in shots}
    for shot in shots_file.shots:
        if shot.label is not None and shot.type == "broll":
            wanted.append((by_id[shot.id].from_, shot.label.kind, shot.label.text))
    for event in shots_file.events:
        if event.tag:
            first = next((s for s in shots_file.shots if s.startWord >= event.startWord), None)
            if first is not None:
                wanted.append((by_id[first.id].from_, "place", event.tag))
    labels: list[TimelineLabel] = []
    last_end = -1
    for start, kind, text in sorted(wanted):
        start += 4                                      # land just after the cut
        end = start + hold
        if start < last_end or any(a < end and start < b for a, b in busy) or end > shots[-1].from_ + shots[-1].durationInFrames:
            continue
        labels.append(TimelineLabel.model_validate({"kind": kind, "text": text, "from": start, "durationInFrames": hold}))
        last_end = end
    return labels


def _all_audio(folder: Path, prefix: str) -> list[Path]:
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.iterdir() if p.suffix.lower() in AUDIO_EXTENSIONS and p.name.lower().startswith(prefix))


MUSIC_USAGE = "music_usage.json"   # in cache/: which tracks each video used

MOODS = {
    "intriga": "misterio, investigación, contexto, preguntas, la historia se va desvelando",
    "triunfo": "victoria, oro, récord, podio, celebración, la gloria",
    "caida": "fracaso, lesión, derrota, tristeza, dudas, pérdida",
    "tension": "la espera antes de una final, presión, momento decisivo, suspense",
    "remontada": "superación, volver más fuerte, determinación, esfuerzo que da fruto",
    "infancia": "orígenes, niñez, familia, primeros pasos, recuerdos",
}



def moods_of(ctx: RunContext) -> dict[str, str]:
    """The moods music files can be named after: the shared ones plus the channel's (timeline.moods)."""

    extra = ctx.section("timeline").get("moods")
    return {**MOODS, **({str(k).lower(): str(v) for k, v in extra.items()} if isinstance(extra, dict) else {})}


MUSIC_SYSTEM = """
Eres el montador musical de un vídeo documental de YouTube. Para cada tramo numerado del guion elige el
tono de la música de fondo, SOLO entre estos: {moods}. Evita cambiar de tono sin motivo: tramos
seguidos con el mismo ánimo llevan el mismo tono. Devuelve SOLO JSON: {{"moods": ["tono del tramo 0", ...]}}
""".strip()


def music_parts(ctx: RunContext, timeline: Timeline, tracks: dict[str, list[str]], default: str) -> list[dict]:
    """Chapter by chapter: the mood the LLM picks (among moods with tracks), tracks rotating per mood,
    consecutive chapters with the same mood merged into one part."""

    starts = [0] + [s.from_ for s in timeline.shots if s.type == "chapter" and s.from_ > 0]
    bounds = list(zip(starts, [*starts[1:], timeline.durationInFrames]))
    moods = [default] * len(bounds)
    if len(tracks) > 1:
        texts = []
        for a, b in bounds:
            text = " ".join(s.text for s in timeline.shots if a <= s.from_ < b and s.text)
            texts.append(text[:1500] or "(apertura con el sonido original de la competición)")
        try:
            listed = complete_json(ctx, stage=STAGE, section="planner", max_tokens=600,
                                   system=MUSIC_SYSTEM.format(moods=", ".join(f"{m} ({moods_of(ctx).get(m, m)})" for m in tracks)),
                                   user="\n\n".join(f"[{i}] {t}" for i, t in enumerate(texts))).get("moods", [])
            moods = [str(m).lower() if str(m).lower() in tracks else default for m in listed][:len(bounds)]
            moods += [moods[-1] if moods else default] * (len(bounds) - len(moods))
        except Exception as error:  # music by chapter is a nicety: one mood for all otherwise
            print(f"   Música por capítulos no disponible: {str(error)[:100]}")
    # Least used first across the channel's videos (cache/music_usage.json), so videos alternate tracks.
    registry = ctx.cache_dir / MUSIC_USAGE
    usage: dict[str, list[str]] = json.loads(registry.read_text("utf-8")) if registry.is_file() else {}
    count: dict[str, int] = {}
    for slug, names in usage.items():
        if slug != ctx.slug:
            for name in names:
                count[name] = count.get(name, 0) + 1
    queue = {m: sorted(srcs, key=lambda s: (count.get(Path(s).name, 0), Path(s).name)) for m, srcs in tracks.items()}
    parts: list[dict] = []
    used = {m: 0 for m in tracks}
    for (a, b), mood in zip(bounds, moods):
        if parts and parts[-1]["mood"] == mood:
            parts[-1]["durationInFrames"] = b - parts[-1]["from"]
            continue
        src = queue[mood][used[mood] % len(queue[mood])]
        used[mood] += 1
        parts.append({"src": src, "from": a, "durationInFrames": b - a, "mood": mood})
    usage[ctx.slug] = sorted({Path(p["src"]).name for p in parts})
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(json.dumps(usage, ensure_ascii=False, indent=1), encoding="utf-8")
    return parts


def with_seconds(ctx: RunContext, media: dict[str, Any]) -> dict[str, Any]:
    """Clips inside graphics carry their length, so Remotion slows them down or loops them instead of
    leaving a frozen last frame when the graphic lasts longer than the clip."""

    if media.get("kind") == "video" and "seconds" not in media:
        from .render import media_seconds

        seconds = media_seconds(ctx.work_dir / media["src"])
        if seconds > 0:
            media["seconds"] = round(seconds, 3)
    return media


def motion_graphic(ctx: RunContext, graphic: dict[str, Any], clips: list[dict[str, Any]], sessions: dict[str, Any],
                   n: int) -> dict[str, Any] | None:
    """A stroboscope or a speed-ramped replay from the first clip of the passage where it works."""

    from . import motion

    if "rembg" not in sessions:
        try:
            from rembg import new_session

            sessions["rembg"] = new_session(str(ctx.section("people").get("model", "u2net_human_seg")))
        except Exception:  # rembg missing: no motion graphics
            sessions["rembg"] = None
    if sessions["rembg"] is None:
        return None
    for k, clip in enumerate(clips[:4]):
        name = f"g{n}-{k}"
        if graphic["type"] == "strobe":
            made = motion.strobe(ctx, ctx.work_dir / clip["src"], name, sessions["rembg"])
        else:
            made = motion.replay(ctx, ctx.work_dir / clip["src"], name, sessions["rembg"])
        if made:
            return {**graphic, **made}
    return None


def with_graphics(ctx: RunContext, words: WordsFile, shots: list[TimelineShot], groups: list[TimelineGroup],
                  labels: list[TimelineLabel], fps: int, total: int) -> tuple[list[TimelineGroup], list[TimelineLabel]]:
    """Animated graphics (maps, A vs B, charts…) over the shots of the sentences they explain.

    Each one is snapped to shot boundaries and skipped where it would cover a data panel, a stat,
    a question, a chapter card or an athlete card; lower-third labels under it are dropped.
    """

    from . import graphics
    from .shorts import sentences

    sents = sentences([w.model_dump() for w in words.words])
    weak = weak_sentences(ctx, sents) if ctx.section("graphics").get("cover_weak") else set()
    planned = graphics.plan(ctx, sents, words.durationSeconds, weak=weak)
    people = []
    if (ctx.work_dir / "people.json").is_file():
        people = json.loads((ctx.work_dir / "people.json").read_text("utf-8")).get("people", [])
    bounds = [s.from_ for s in shots] + [total]
    sessions: dict[str, Any] = {}
    added: list[TimelineGroup] = []
    blocked = [(g.from_, g.from_ + g.durationInFrames) for g in groups]
    blocked += [(s.from_, s.from_ + s.durationInFrames) for s in shots if s.type == "chapter" or (s.media and s.media.layout == "person")]
    for n, item in enumerate(planned, 1):
        a = min(bounds, key=lambda f: abs(f - item["start"] * fps))
        b = min(bounds, key=lambda f: abs(f - item["end"] * fps))
        # the longest stretch of [a, b) free of panels, stats, questions, chapter and athlete cards
        cuts = sorted({a, b, *[x for lo, hi in blocked + [(g.from_, g.from_ + g.durationInFrames) for g in added]
                               for x in (lo, hi) if a < x < b]})
        free = [(lo, hi) for lo, hi in zip(cuts, cuts[1:])
                if not any(x < hi and lo < y for x, y in blocked + [(g.from_, g.from_ + g.durationInFrames) for g in added])]
        if not free:
            continue
        a, b = max(free, key=lambda r: r[1] - r[0])
        covered = [s for s in shots if a <= s.from_ < b]
        if b - a < 3 * fps or not covered:
            continue
        graphic = dict(item["graphic"])

        def footage() -> dict[str, Any] | None:   # a photo of this passage (else a clip) for cards without a portrait
            media = [s.media for s in covered if s.media]
            pick = next((m for m in media if m.kind == "image"), media[0] if media else None)
            return with_seconds(ctx, pick.model_dump(exclude_none=True)) if pick else None

        def clips() -> list[dict[str, Any]]:   # the passage's own clips, each once
            seen: dict[str, dict[str, Any]] = {}
            for s in covered:
                if s.media and s.media.kind == "video" and s.media.src not in seen:
                    seen[s.media.src] = with_seconds(ctx, s.media.model_dump(exclude_none=True))
            return list(seen.values())

        if graphic["type"] in ("strobe", "replay"):
            made = motion_graphic(ctx, graphic, clips(), sessions, n)
            if not made:
                continue
            graphic = made
            longest = round((6.0 if graphic["type"] == "strobe" else graphic.pop("seconds")) * fps)
            b = min(b, a + longest)                          # the shots after it show as usual
        if graphic["type"] == "banned":
            graphic["media"] = next(iter(clips()), None) or footage()
        if graphic["type"] == "split":
            options = clips()

            def side(name: str, taken: str | None) -> dict[str, Any] | None:
                wanted = set(re.findall(r"\w+", name.lower()))
                for s in covered:
                    if s.media and s.media.kind == "video" and s.media.src != taken \
                            and wanted & set(re.findall(r"\w+", s.text.lower())):
                        return with_seconds(ctx, s.media.model_dump(exclude_none=True))
                return None

            left = side(graphic["left"]["name"], None)
            right = side(graphic["right"]["name"], left["src"] if left else None)
            left = left or next((m for m in options if not right or m["src"] != right["src"]), None) \
                or graphics.portrait(ctx, graphic["left"]["name"], people)
            right = right or next((m for m in reversed(options) if not left or m["src"] != left["src"]), None) \
                or graphics.portrait(ctx, graphic["right"]["name"], people)
            if not left or not right or left["src"] == right["src"]:
                continue
            graphic["left"]["media"], graphic["right"]["media"] = left, right
        if graphic["type"] == "podium":
            for place in graphic["places"]:
                place["media"] = graphics.portrait(ctx, place["name"], people)
        if graphic["type"] == "card":
            graphic["media"] = graphics.portrait(ctx, graphic["name"], people) or footage()
        if graphic["type"] in ("rank", "specs"):
            face = graphics.portrait(ctx, graphic["name"], people)
            graphic["media"] = face or footage()
            if graphic["type"] == "specs":
                graphic["kicker"] = "EN CIFRAS" if face else "FICHA TÉCNICA"
        if graphic["type"] == "compare":
            for side in ("left", "right"):
                graphic[side]["media"] = graphics.portrait(ctx, graphic[side]["name"], people)
        added.append(TimelineGroup.model_validate({"id": f"graphic-{n}", "kind": "graphic", "from": a,
                                                   "durationInFrames": b - a, "graphic": graphic}))
    boards = chalkboards(shots, [*groups, *added], fps)
    labels = [label for label in labels
              if not any(g.from_ < label.from_ + label.durationInFrames and label.from_ < g.from_ + g.durationInFrames
                         for g in [*added, *boards])]
    if added:
        print("   Gráficos: " + ", ".join(f"{g.graphic['type']} {g.from_ / fps:.0f}s" for g in added))
    if boards:
        print(f"   Pizarra (plano sin imagen): {len(boards)} · " + ", ".join(f"{g.from_ / fps:.0f}s" for g in boards))
    return sorted([*groups, *added, *boards], key=lambda g: g.from_), labels


def weak_sentences(ctx: RunContext, sents: list[dict[str, Any]]) -> set[int]:
    """Sentences whose footage is weak: a low score nobody judged, a fallback stand-in, or nothing at all.
    graphics.cover_weak puts the animated graphics there first."""

    low = float(ctx.section("qa").get("low_score", ctx.section("judge").get("min_score", 0.30)))
    weak: set[str] = set()
    if (ctx.work_dir / "selection.json").is_file():
        weak |= {s["shotId"] for s in ctx.read_json("selection.json").get("selections", [])
                 if s.get("score") is not None and s["score"] < low and not s.get("judge")}
    if (ctx.work_dir / "fallback.json").is_file():
        data = ctx.read_json("fallback.json")
        weak |= {i["shotId"] for i in data.get("items", []) if i.get("method") != "next-option"} | set(data.get("unresolved", {}))
    out: set[int] = set()
    for shot in ShotsFile.model_validate(ctx.read_json("shots.json")).shots:
        if shot.id not in weak:
            continue
        end = shot.start + shot.duration
        for s in sents:
            if min(end, s["end"]) - max(shot.start, s["start"]) >= 0.5 * min(shot.duration, s["end"] - s["start"]):
                out.add(s["n"])
    return out


def key_phrase(text: str, most: int = 8) -> str:
    """The script's own words that carry a sentence: the clause with most long words/numbers, ≤ `most` words."""

    text = " ".join(text.split()).strip(" ,.;:¿?¡!…")
    if len(text.split()) <= most:
        return text
    parts = [p.strip(" ,.;:¿?¡!…") for p in re.split(r"[,;:]|\b(?:que|y|pero|porque)\b", text) if p and p.strip()]
    fitting = [p for p in parts if 2 <= len(p.split()) <= most]
    if fitting:
        return max(fitting, key=lambda p: sum(1 for w in re.findall(r"\w+", p) if len(w) > 4 or w.isdigit()))
    return " ".join(text.split()[:most])


def chalkboards(shots: list[TimelineShot], groups: list[TimelineGroup], fps: int) -> list[TimelineGroup]:
    """Shots left without footage (timeline.pizarra) show their key words on the chalkboard canvas."""

    out: list[TimelineGroup] = []
    for shot in shots:
        if shot.media is not None or shot.type != "broll" or shot.groupId:
            continue
        start, end = shot.from_, shot.from_ + shot.durationInFrames
        if any(g.from_ < end and start < g.from_ + g.durationInFrames for g in groups):
            continue
        phrase = key_phrase(shot.text)
        if not phrase:
            continue
        words = phrase.split()
        lines = [" ".join(words[: (len(words) + 1) // 2]), " ".join(words[(len(words) + 1) // 2:])] if len(words) > 4 else [phrase]
        out.append(TimelineGroup.model_validate({"id": f"board-{shot.id}", "kind": "graphic", "from": start,
                                                 "durationInFrames": shot.durationInFrames,
                                                 "graphic": {"type": "kinetic", "lines": [l for l in lines if l], "board": True}}))
    return out


SPOTLIGHT_DIR = "spotlight"


def spotlight_images(ctx: RunContext, clip: Path, seconds: float, name: str, session: Any) -> dict[str, Any] | None:
    """The frozen frame (1920x1080) and the same frame with only the person (transparent PNG), plus
    where the person's head is (% of the frame) for the name tag; None if there is no clear person."""

    import subprocess

    import cv2
    import numpy as np
    from rembg import remove

    out = ctx.work_dir / SPOTLIGHT_DIR
    out.mkdir(parents=True, exist_ok=True)
    still = out / f"{name}.jpg"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{seconds:.3f}", "-i", str(clip), "-frames:v", "1",
                    "-vf", "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080", "-q:v", "2", str(still)],
                   check=False)
    image = cv2.imread(str(still))
    if image is None:
        return None
    rgba = np.array(remove(cv2.cvtColor(image, cv2.COLOR_BGR2RGB), session=session))
    alpha = rgba[..., 3] > 128
    coverage = float(alpha.mean())
    if not 0.015 <= coverage <= 0.45:
        return None                                        # nobody, or a crowd/close-up filling the frame
    count, labels_, stats, _ = cv2.connectedComponentsWithStats(alpha.astype(np.uint8))
    if count < 2:
        return None
    biggest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    if stats[biggest, cv2.CC_STAT_AREA] < 0.7 * alpha.sum():
        return None                                        # several people: no single one to point at
    rgba[..., 3] = np.where(labels_ == biggest, rgba[..., 3], 0)
    cutout = out / f"{name}.png"
    cv2.imwrite(str(cutout), cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGRA))
    x, y, w, h = (int(v) for v in stats[biggest, :4])
    if h > 0.85 * 1080 or y < 0.03 * 1080:
        return None                                        # a close-up or a cut-off head: nothing to point at
    return {"still": str(still.relative_to(ctx.work_dir)), "cutout": str(cutout.relative_to(ctx.work_dir)),
            "anchor": [round((x + w / 2) / 19.2, 1), round(y / 10.8, 1)], "height": round(h / 10.8, 1)}


def source_title(ctx: RunContext, candidate: str) -> str:
    """Lower-case title + channel of a YouTube candidate ("yt:<id>"), from yt-dlp's cached info."""

    if not candidate.startswith("yt:"):
        return ""
    path = ctx.cache_dir / "videos" / candidate[3:] / "ytdlp-info.json"
    try:
        info = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return ""
    return f"{info.get('title') or ''} {info.get('channel') or info.get('uploader') or ''}".lower()


def with_spotlights(ctx: RunContext, words: WordsFile, shots: list[TimelineShot], groups: list[TimelineGroup],
                    labels: list[TimelineLabel], subject: str, fps: int) -> tuple[list[TimelineGroup], list[TimelineLabel]]:
    """Freeze frame + spotlight: the first time the narration names someone over a clip, the clip
    stops, everything but that person goes dark and their name appears next to them."""

    cfg = ctx.section("timeline")
    limit = int(cfg.get("spotlights", 3))
    if limit <= 0:
        return groups, labels
    people = []
    if (ctx.work_dir / "people.json").is_file():
        people = [p["name"] for p in json.loads((ctx.work_dir / "people.json").read_text("utf-8")).get("people", [])]
    subject = subject.split("·")[0].strip()
    names = list(dict.fromkeys([n for n in [subject, *people] if n]))
    if not names:
        return groups, labels
    try:
        from rembg import new_session

        session = new_session(str(ctx.section("people").get("model", "u2net_human_seg")))
    except Exception:  # rembg missing: no spotlights, like no athlete cards
        return groups, labels
    sources = {}
    if (ctx.work_dir / "media" / "_ingest.json").is_file():
        sources = {m["shotId"]: m.get("candidateId") or "" for m in
                   json.loads((ctx.work_dir / "media" / "_ingest.json").read_text("utf-8")).get("media", [])}
    busy = [(g.from_, g.from_ + g.durationInFrames) for g in groups]
    added: list[TimelineGroup] = []
    for name in names:
        surname = re.findall(r"\w+", name.lower())[-1:]
        mentions = [w for w in words.words if surname and re.sub(r"\W", "", w.text.lower()) == surname[0]]
        for word in mentions[:12]:          # the first mention over a full-screen clip of that person
            at = round(word.end * fps)
            shot = next((s for s in shots if s.from_ <= at < s.from_ + s.durationInFrames), None)
            if not shot or not shot.media or shot.media.kind != "video" or shot.media.layout != "full" \
                    or surname[0] not in source_title(ctx, sources.get(shot.id, "")):
                continue                                   # only when the clip is known to show that person
            start = max(at, shot.from_ + round(0.5 * fps))
            end = start + round(float(cfg.get("spotlight_seconds", 2.6)) * fps)   # full screen: may run past the cut
            if start > shot.from_ + shot.durationInFrames - 3 or end > shots[-1].from_ + shots[-1].durationInFrames or any(a < end and start < b for a, b in busy):
                continue
            found = spotlight_images(ctx, ctx.work_dir / shot.media.src, (start - shot.from_) / fps,
                                     f"{shot.id}-{len(added)}", session)
            if not found:
                continue
            added.append(TimelineGroup.model_validate({
                "id": f"spotlight-{len(added) + 1}", "kind": "graphic", "from": start, "durationInFrames": end - start,
                "graphic": {"type": "spotlight", "name": name, "anchor": found["anchor"], "height": found["height"],
                            "still": {"src": found["still"], "kind": "image", "source": shot.media.source},
                            "cutout": {"src": found["cutout"], "kind": "image", "source": shot.media.source}}}))
            busy.append((start, end))
            break
        if len(added) == limit:
            break
    if added:
        print("   Congelados con foco: " + ", ".join(f"{g.graphic['name']} {g.from_ / fps:.0f}s" for g in added))
    labels = [label for label in labels
              if not any(g.from_ < label.from_ + label.durationInFrames and label.from_ < g.from_ + g.durationInFrames for g in added)]
    return sorted([*groups, *added], key=lambda g: g.from_), labels


def with_endscreen(timeline: Timeline, frames: int) -> Timeline:
    """Append the end screen (YouTube's end-screen elements go over it) after the narration."""

    if frames <= 0:
        return timeline
    end = TimelineShot.model_validate({"id": "end", "type": "endscreen", "from": timeline.durationInFrames,
                                       "durationInFrames": frames, "text": ""})
    return Timeline.model_validate({
        **timeline.model_dump(by_alias=True),
        "durationInFrames": timeline.durationInFrames + frames,
        "shots": [*[s.model_dump(by_alias=True) for s in timeline.shots], end.model_dump(by_alias=True)],
        "endscreenFrames": frames,
    })


def key_cuts(timeline: Timeline, cuts: list[int], half: int = 6) -> list[TimelineTransition]:
    """Visual transitions on the cuts that carry a whoosh: a zoom punch into chapter cards and
    graphics, a whip pan elsewhere. Only on real shot boundaries, never over the first frames."""

    starts = {s.from_: s for s in timeline.shots}
    zoom_at = {s.from_ for s in timeline.shots if s.type in ("chapter", "endscreen")}
    zoom_at |= {g.from_ for g in timeline.groups if g.kind == "graphic"}
    zoom_at |= {g.from_ + g.durationInFrames for g in timeline.groups if g.kind == "graphic"}
    out = []
    for at in cuts:
        if at in starts and half <= at <= timeline.durationInFrames - half:
            out.append(TimelineTransition.model_validate({"kind": "zoom" if at in zoom_at else "whip",
                                                          "from": at - half, "durationInFrames": 2 * half}))
    return out


def transition_sfx(timeline: Timeline, files: list[str], volume: float, min_gap: float = 4.0,
                   main: str = "", other_every: int = 4) -> list[TimelineSfx]:
    """Whooshes at the transitions, rotating through the files, never two closer than `min_gap` s.

    By priority: chapter cards, entering/leaving the original-sound moments and the cold open,
    athlete cards, then stat/panel entries.
    """

    if not files:
        return []
    fps = timeline.fps
    points: list[int] = [s.from_ for s in timeline.shots if s.type == "chapter"]
    moments = [s for s in timeline.shots if s.coldOpen]
    points += [s.from_ for s in moments if s.from_ > 0] + [s.from_ + s.durationInFrames for s in moments]
    points += [s.from_ for s in timeline.shots if s.type == "endscreen"]
    points += [s.from_ for s in timeline.shots if s.media and s.media.layout == "person"]
    points += [g.from_ for g in timeline.groups if g.kind in ("graphic", "stat", "datacard", "split")]
    placed: list[int] = []
    for point in points:
        at = max(0, point - 4)                    # the swoosh peaks just as the cut lands
        if at < timeline.durationInFrames and all(abs(at - p) >= min_gap * fps for p in placed):
            placed.append(at)
    first = next((f for f in files if main and main.lower() in Path(f).name.lower()), None)
    others = [f for f in files if f != first] or files
    chosen = []
    for i, at in enumerate(sorted(placed)):
        if first and (not other_every or (i + 1) % other_every):
            chosen.append((first, at))                  # the main whoosh most of the time…
        else:
            step = i // max(1, other_every) if first else i
            chosen.append((others[step % len(others)], at))   # …another one now and then (or plain rotation)
    return [TimelineSfx.model_validate({"src": src, "from": at, "volume": volume}) for src, at in chosen]


STAT_LANDS = 18   # frame the Stat counter reaches its figure (remotion/components/Stat.tsx)


# Frames at which the Remotion components land their big moments (keep in sync with the .tsx files).
SCORE_LANDS = 40       # Score.tsx: the total
PRESS_STEP = 16        # Press.tsx: one clipping every 16 frames
RULE_STAMP = 44        # RulePage.tsx: the stamp hits the page
BANNED_STAMP = 22      # BannedCard.tsx: the stamp hits the card
PODIUM_RISE = {3: 6, 2: 14, 1: 24}         # Podium.tsx: when each block rises
CARD_LANDS = 18                             # PlayerCard.tsx: the card finishes its flip
STROBE_START, STROBE_STEP = 8, 6            # Strobe.tsx: one position every 6 frames
STANDINGS_START, STANDINGS_STEP = 6, 14     # Standings.tsx: one row every 14 frames


def graphic_cues(graphic: dict[str, Any], frames: int) -> list[tuple[str, int]]:
    """When each element of an animated graphic appears (same timings as its Remotion component)."""

    kind = graphic.get("type")
    if kind == "map":
        n = len(graphic.get("points") or [])
        return [("pop", round((0.15 + 0.45 * i / max(1, n)) * frames)) for i in range(n)]
    if kind == "chart":
        n = len(graphic.get("data") or [])
        if graphic.get("chart") == "line":
            return [("pop", round(6 + 44 * i / max(1, n - 1))) for i in range(min(n, 24))]
        if graphic.get("chart") == "pie":
            return [("pop", 10 + i * 6) for i in range(min(n, 8))]
        return [("pop", 8 + i * 5) for i in range(min(n, 12))]
    if kind == "compare":
        return [("pop", 14 + i * 10) for i in range(min(len(graphic.get("rows") or []), 5))]
    if kind == "specs":
        return [("pop", 14 + i * 7) for i in range(min(len(graphic.get("specs") or []), 6))]
    if kind == "rank":
        return [("impact", 2)] + [("pop", 20 + i * 8) for i in range(min(len(graphic.get("stats") or []), 4))]
    if kind == "timeline":
        n = min(len(graphic.get("events") or []), 8)
        return [("pop", round(i * frames / max(1, n))) for i in range(n)]
    if kind == "score":
        steps = [("pop", 10), ("pop", 22)] + ([("pop", 34)] if graphic.get("penalty") else [])
        return steps + [("impact", SCORE_LANDS + (12 if graphic.get("penalty") else 0))]
    if kind == "press":
        return [("pop", 4 + i * PRESS_STEP) for i in range(min(len(graphic.get("items") or []), 3))]
    if kind == "rule":
        return [("pop", 4)] + ([("impact", RULE_STAMP)] if graphic.get("stamp") else [])
    if kind == "banned":
        return [("impact", BANNED_STAMP)]
    if kind == "split":
        return [("pop", 4), ("pop", 12)]
    if kind == "spotlight":
        return [("impact", 1)]
    if kind == "podium":
        n = len(graphic.get("places") or [])
        return [("pop", PODIUM_RISE[p["place"]]) for p in graphic.get("places") or [] if p["place"] != 1][: n] \
            + [("impact", PODIUM_RISE[1] + 8)]
    if kind == "card":
        return [("impact", CARD_LANDS)] + [("pop", CARD_LANDS + 12 + i * 6) for i in range(min(len(graphic.get("stats") or []), 6))]
    if kind == "scale":
        return [("pop", 10 + i * 10) for i in range(len(graphic.get("items") or []))]
    if kind == "race":
        n = len(graphic.get("steps") or [])
        return [("pop", round(i * frames * 0.85 / max(1, n - 1))) for i in range(n)]
    if kind == "strobe":
        return [("pop", STROBE_START + i * STROBE_STEP) for i in range(len(graphic.get("ghosts") or []))]
    if kind == "replay":
        return [("impact", round(float(graphic.get("peak") or 0) * 30))]
    if kind == "standings":
        return [("pop", STANDINGS_START + i * STANDINGS_STEP) for i in range(min(len(graphic.get("rows") or []), 8))]
    if kind == "kinetic":
        words = sum(len(str(line).split()) for line in graphic.get("lines") or [])
        gap = max(3, min(8, int(frames * 0.6 / max(1, words))))
        return [("impact", (words - 1) * gap)]
    return []


def animation_cues(groups: list[TimelineGroup], min_gap: int = 3) -> list[tuple[str, int]]:
    """Sounds glued to the animations: a pop per bar/pin/row/milestone/panel row, an impact when a
    big figure lands (stats, ranking numbers, the last word of kinetic text)."""

    cues: list[tuple[str, int]] = []
    for group in groups:
        if group.kind == "stat":
            cues.append(("impact", group.from_ + STAT_LANDS))
        elif group.kind == "graphic" and group.graphic:
            cues += [(k, group.from_ + at) for k, at in graphic_cues(group.graphic, group.durationInFrames)
                     if at < group.durationInFrames]
        elif group.kind in ("datacard", "split"):
            cues += [("pop", group.from_ + step.from_) for step in group.steps]
    out: list[tuple[str, int]] = []
    for kind, at in sorted(cues, key=lambda c: c[1]):
        if not out or at - out[-1][1] >= min_gap or kind == "impact":
            out.append((kind, at))
    return out


def _first_audio(folder: Path, prefix: str = "") -> Path | None:
    if not folder.is_dir():
        return None
    files = sorted(p for p in folder.iterdir() if p.suffix.lower() in AUDIO_EXTENSIONS and p.name.lower().startswith(prefix))
    return files[0] if files else None


def inputs(ctx: RunContext) -> list:
    return [
        ctx.work_dir / "shots.json", ctx.work_dir / "words.json", ctx.work_dir / "media" / "_ingest.json",
        ctx.work_dir / "fallback.json", ctx.work_dir / "coldopen.json", ctx.work_dir / "people.json", ctx.materials_dir / "voz.mp3", ctx.root / "assets",
    ]


def run(ctx: RunContext) -> None:
    cfg = ctx.section("timeline")
    fps = ctx.fps
    video = ctx.section("video")
    shots_file = ShotsFile.model_validate(ctx.read_json("shots.json"))
    words = WordsFile.model_validate(ctx.read_json("words.json"))
    total_frames = round(shots_file.durationSeconds * fps)

    # Media per shot: stage 6, replaced by stage 7 where fallback stepped in (failed download,
    # rejected by the judge, or a look-alike of an earlier shot). Paths relative to the public dir.
    media: dict[str, TimelineMedia] = {}
    for item in IngestFile.model_validate_json((ctx.work_dir / "media" / "_ingest.json").read_text("utf-8")).media:
        media[item.shotId] = TimelineMedia(
            src=str((ctx.root / item.path).relative_to(ctx.work_dir)), kind=item.kind, source=item.source, credit=item.credit,
            width=item.width, height=item.height,
        )
    for item in FallbackFile.model_validate(ctx.read_json("fallback.json")).items:
        size = _size(ctx.root / item.path)
        media[item.shotId] = TimelineMedia(
            src=str((ctx.root / item.path).relative_to(ctx.work_dir)), kind=item.kind, source=item.source,
            credit=item.credit, width=size[0], height=size[1],
        )

    # Frame-accurate shots: each starts where the previous ended.
    starts = [round(s.start * fps) for s in shots_file.shots] + [total_frames]
    starts[0] = 0
    shots: list[TimelineShot] = []
    missing = []
    chapter_number = 0
    card_share = float(cfg.get("card_share", 0.25))
    narrow = str(cfg.get("narrow_layout", "card"))
    # timeline.pizarra: a shot nothing could fill (no stock, no generated images in this channel)
    # becomes a chalkboard card with its key words instead of stopping the video
    fallback = FallbackFile.model_validate(ctx.read_json("fallback.json"))
    boards = set(fallback.unresolved) if cfg.get("pizarra") else set()
    for shot_id in boards:
        media.pop(shot_id, None)
    for index, shot in enumerate(shots_file.shots):
        m = media.get(shot.id) if needs_footage(shot) else None
        if needs_footage(shot) and m is None and shot.id not in boards:
            missing.append(shot.id)
        if m is not None:
            m = m.model_copy(update={"layout": choose_layout(shot.id, shot.type, m, card_share, narrow)})
        if shot.type == "chapter":
            chapter_number += 1
        shots.append(TimelineShot.model_validate({
            "id": shot.id, "type": shot.type, "from": starts[index],
            "durationInFrames": starts[index + 1] - starts[index], "text": shot.text,
            "media": m.model_dump() if m else None, "chapterTitle": shot.chapterTitle,
            "chapterNumber": chapter_number if shot.type == "chapter" else None,
            "groupId": shot.panelId or (f"stat-{shot.id}" if shot.type == "stat" else None),
        }))
    if missing:
        raise RuntimeError(f"Planos sin medio (¿falta ejecutar ingest/fallback?): {', '.join(missing[:10])}")

    # Groups: panels (datacard/split) and stats, spanning their consecutive shots.
    groups: list[TimelineGroup] = []
    by_id = {s.id: s for s in shots_file.shots}
    for shot in shots:
        if shot.groupId is None:
            continue
        source = by_id[shot.id]
        if groups and groups[-1].id == shot.groupId:
            group = groups[-1]
            group.durationInFrames = shot.from_ + shot.durationInFrames - group.from_
            if source.panel and source.panel.rows != group.steps[-1].rows:
                group.steps.append(PanelStep.model_validate({"from": shot.from_ - group.from_, "rows": source.panel.rows}))
            continue
        kind = "stat" if source.type == "stat" else source.type
        groups.append(TimelineGroup.model_validate({
            "id": shot.groupId, "kind": kind, "from": shot.from_, "durationInFrames": shot.durationInFrames,
            "title": source.panel.title if source.panel else None,
            "note": source.panel.note if source.panel else None,
            "steps": [{"from": 0, "rows": [r.model_dump() for r in source.panel.rows]}] if source.panel else [],
            "stat": source.stat.model_dump() if source.stat else None,
        }))

    groups += question_groups(words, shots, groups, fps, total_frames, cfg,
                              spanish=str(ctx.section("align").get("language", "es")) == "es")
    groups.sort(key=lambda g: g.from_)
    person_cards(ctx, shots_file, shots, groups, fps)
    labels = place_labels(shots_file, shots, groups, fps, cfg)
    groups, labels = with_graphics(ctx, words, shots, groups, labels, fps, total_frames)
    groups, labels = with_spotlights(ctx, words, shots, groups, labels, shots_file.subject or "", fps)

    # Audio: voice (always), music and SFX only if the files exist.
    audio_dir = ctx.work_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    voice = audio_dir / "voz.mp3"
    shutil.copy2(ctx.materials_dir / "voz.mp3", voice)
    assets = ctx.root / str(cfg.get("assets", "assets"))

    def folder(name: str, prefix: str = "") -> Path:
        """The channel's own music/sfx (e.g. assets/robots/sfx/), else the shared assets/<name>/."""

        own = assets / name
        return own if _all_audio(own, prefix) or assets == ctx.root / "assets" else ctx.root / "assets" / name

    def publish(path: Path | None) -> str | None:
        if path is None:
            return None
        target = audio_dir / path.name
        if not target.is_file() or target.stat().st_size != path.stat().st_size:
            shutil.copy2(path, target)
        return str(target.relative_to(ctx.work_dir))

    tracks: dict[str, list[str]] = {}
    for path in _all_audio(folder("music"), ""):
        mood = path.stem.split("-")[0].lower()
        tracks.setdefault(mood if mood in moods_of(ctx) else "general", []).append(publish(path))
    default = str(cfg.get("music_default", "intriga"))
    default = default if default in tracks else next(iter(tracks), "")
    music = tracks[default][0] if tracks else None
    whooshes = [publish(p) for p in _all_audio(folder("sfx", "whoosh"), "whoosh")]
    pop = publish(_first_audio(folder("sfx", "pop"), "pop"))
    sfx: list[TimelineSfx] = []
    impact = publish(_first_audio(folder("sfx", "impact"), "impact"))
    for kind, at in animation_cues(groups):
        src = pop if kind == "pop" else impact
        if src:
            sfx.append(TimelineSfx.model_validate({"src": src, "from": at, "volume": float(
                cfg.get("pop_volume", 0.25) if kind == "pop" else cfg.get("impact_volume", 0.22))}))

    timeline = Timeline(
        slug=ctx.slug, title=shots_file.title, fps=fps, width=int(video.get("width", 1920)),
        height=int(video.get("height", 1080)), durationInFrames=total_frames, shots=shots, groups=groups, labels=labels,
        audio=TimelineAudio(
            voice=str(voice.relative_to(ctx.work_dir)), music=music,
            musicVolume=float(cfg.get("music_volume", 0.25)),
            duckedVolume=float(cfg.get("music_volume", 0.25)) * 10 ** (-float(cfg.get("duck_db", 18)) / 20),
            speech=speech_segments(words, fps), sfx=sfx,
        ),
    )
    cold = ctx.work_dir / "coldopen.json"
    if cold.is_file():
        opening = ColdOpenFile.model_validate(ctx.read_json("coldopen.json"))
        clips = opening.clips
        timeline = with_moments(timeline, [
            (str((ctx.root / m.path).relative_to(ctx.work_dir)), m.afterSeconds, m.durationSeconds, m.credit, m.width, m.height)
            for m in opening.moments if m.afterSeconds is not None
        ], fps, float(cfg.get("moment_volume", 1.0)))
        timeline = with_cold_open(timeline, [
            (str((ctx.root / c.path).relative_to(ctx.work_dir)), c.durationSeconds, c.credit, c.width, c.height)
            for c in clips
        ], fps, float(cfg.get("cold_open_volume", 1.0)))
        # the opening question stays on screen from the very first frame, over the cold open too
        timeline = timeline.model_copy(update={"groups": [
            g.model_copy(update={"from_": 0, "durationInFrames": g.durationInFrames + g.from_}) if g.id == "q-open" else g
            for g in timeline.groups]})
    timeline = timeline.model_copy(update={"brand": {k: str(v) for k, v in ctx.section("brand").items()}})
    timeline = with_endscreen(timeline, round(float(cfg.get("endscreen_seconds", 0) or 0) * fps))
    if tracks and cfg.get("music_by_chapter", True):
        parts = music_parts(ctx, timeline, tracks, default)
        timeline = timeline.model_copy(update={"audio": timeline.audio.model_copy(update={
            "musicParts": [MusicPart.model_validate(p) for p in parts]})})
        print("   Música: " + " → ".join(f"{p['mood']} ({Path(p['src']).stem})" for p in parts))
    if cfg.get("shake", True):   # shake where the impacts ended up (after the cold open / moments moved them)
        timeline = timeline.model_copy(update={"shakes": [TimelineShake.model_validate({"from": x.from_})
                                                          for x in timeline.audio.sfx if "impact" in Path(x.src).name]})
    if whooshes:
        extra = transition_sfx(timeline, whooshes, float(cfg.get("whoosh_volume", 0.22)), float(cfg.get("sfx_min_gap", 4.0)),
                               str(cfg.get("whoosh_main", "")), int(cfg.get("whoosh_other_every", 4)))
        timeline = timeline.model_copy(update={"audio": timeline.audio.model_copy(update={
            "sfx": sorted([*timeline.audio.sfx, *extra], key=lambda x: x.from_)})})
        if cfg.get("transitions", True):
            timeline = timeline.model_copy(update={"transitions": key_cuts(timeline, [x.from_ + 4 for x in extra])})
        sfx = timeline.audio.sfx
    from . import editor

    payload = timeline.model_dump(by_alias=True, exclude_none=True)
    ctx.write_json("timeline.base.json", payload)        # as the pipeline made it; the editor's changes go on top
    ctx.write_json(OUTPUT, editor.build(ctx, payload))
    kinds: dict[str, int] = {}
    for group in groups:
        kinds[group.kind] = kinds.get(group.kind, 0) + 1
    credited = sum(1 for s in shots if s.media and s.media.credit)
    print(f"   {len(shots)} planos · {total_frames} fotogramas ({total_frames / fps:.1f} s) · grupos: "
          + ", ".join(f"{k} {v}" for k, v in kinds.items()))
    print(f"   Créditos en pantalla: {credited} · música: {music or 'no (assets/music/ vacío)'} · "
          f"SFX: {len(sfx) if sfx else 'no (assets/sfx/ vacío)'}")


def validate(ctx: RunContext) -> bool:
    timeline = Timeline.model_validate(ctx.read_json(OUTPUT))
    for shot in timeline.shots:
        if shot.media and not (ctx.work_dir / shot.media.src).is_file():
            raise FileNotFoundError(shot.media.src)
    return True
