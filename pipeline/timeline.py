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


def question_groups(words: WordsFile, shots: list[TimelineShot], groups: list[TimelineGroup], fps: int,
                    total: int, cfg: dict[str, Any]) -> list[TimelineGroup]:
    """Floating questions (centred text) that never overlap a data group or a chapter title."""

    if not cfg.get("questions", True):
        return []
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


def choose_layout(shot_id: str, shot_type: str, media: TimelineMedia, card_share: float) -> str:
    """Framed card for stills and for sources that are not widescreen (kept uncropped), plus a
    deterministic share of ordinary clips for variety, as the channel style does."""

    if shot_type in ("chapter", "split"):
        return "full"
    if media.kind == "image":   # photos alternate between the framed card and the parallax move
        return "parallax" if int(hashlib.sha1(shot_id.encode()).hexdigest()[8:16], 16) % 2 else "card"
    if media.width and media.height and media.width / media.height < 1.6:
        return "card"
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

MUSIC_SYSTEM = """
Eres el montador musical de un documental deportivo. Para cada tramo numerado del guion elige el
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
                                   system=MUSIC_SYSTEM.format(moods=", ".join(f"{m} ({MOODS.get(m, m)})" for m in tracks)),
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


def with_graphics(ctx: RunContext, words: WordsFile, shots: list[TimelineShot], groups: list[TimelineGroup],
                  labels: list[TimelineLabel], fps: int, total: int) -> tuple[list[TimelineGroup], list[TimelineLabel]]:
    """Animated graphics (maps, A vs B, charts…) over the shots of the sentences they explain.

    Each one is snapped to shot boundaries and skipped where it would cover a data panel, a stat,
    a question, a chapter card or an athlete card; lower-third labels under it are dropped.
    """

    from . import graphics
    from .shorts import sentences

    planned = graphics.plan(ctx, sentences([w.model_dump() for w in words.words]), words.durationSeconds)
    if not planned:
        return groups, labels
    people = []
    if (ctx.work_dir / "people.json").is_file():
        people = json.loads((ctx.work_dir / "people.json").read_text("utf-8")).get("people", [])
    bounds = [s.from_ for s in shots] + [total]
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
            return pick.model_dump(exclude_none=True) if pick else None

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
    labels = [label for label in labels
              if not any(g.from_ < label.from_ + label.durationInFrames and label.from_ < g.from_ + g.durationInFrames for g in added)]
    if added:
        print("   Gráficos: " + ", ".join(f"{g.graphic['type']} {g.from_ / fps:.0f}s" for g in added))
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
    for index, shot in enumerate(shots_file.shots):
        m = media.get(shot.id) if needs_footage(shot) else None
        if needs_footage(shot) and m is None:
            missing.append(shot.id)
        if m is not None:
            m = m.model_copy(update={"layout": choose_layout(shot.id, shot.type, m, card_share)})
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

    groups += question_groups(words, shots, groups, fps, total_frames, cfg)
    groups.sort(key=lambda g: g.from_)
    person_cards(ctx, shots_file, shots, groups, fps)
    labels = place_labels(shots_file, shots, groups, fps, cfg)
    groups, labels = with_graphics(ctx, words, shots, groups, labels, fps, total_frames)

    # Audio: voice (always), music and SFX only if the files exist.
    audio_dir = ctx.work_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    voice = audio_dir / "voz.mp3"
    shutil.copy2(ctx.materials_dir / "voz.mp3", voice)
    assets = ctx.root / str(cfg.get("assets", "assets"))

    def publish(path: Path | None) -> str | None:
        if path is None:
            return None
        target = audio_dir / path.name
        if not target.is_file() or target.stat().st_size != path.stat().st_size:
            shutil.copy2(path, target)
        return str(target.relative_to(ctx.work_dir))

    tracks: dict[str, list[str]] = {}
    for path in _all_audio(assets / "music", ""):
        mood = path.stem.split("-")[0].lower()
        tracks.setdefault(mood if mood in MOODS else "general", []).append(publish(path))
    default = str(cfg.get("music_default", "intriga"))
    default = default if default in tracks else next(iter(tracks), "")
    music = tracks[default][0] if tracks else None
    whooshes = [publish(p) for p in _all_audio(assets / "sfx", "whoosh")]
    pop = publish(_first_audio(assets / "sfx", "pop"))
    sfx: list[TimelineSfx] = []
    impact = publish(_first_audio(assets / "sfx", "impact"))
    for kind, at in animation_cues(groups):
        src = pop if kind == "pop" else impact
        if src:
            sfx.append(TimelineSfx.model_validate({"src": src, "from": at, "volume": float(
                cfg.get("pop_volume", 0.35) if kind == "pop" else cfg.get("impact_volume", 0.6))}))

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
        extra = transition_sfx(timeline, whooshes, float(cfg.get("whoosh_volume", 0.6)), float(cfg.get("sfx_min_gap", 4.0)),
                               str(cfg.get("whoosh_main", "")), int(cfg.get("whoosh_other_every", 4)))
        timeline = timeline.model_copy(update={"audio": timeline.audio.model_copy(update={
            "sfx": sorted([*timeline.audio.sfx, *extra], key=lambda x: x.from_)})})
        if cfg.get("transitions", True):
            timeline = timeline.model_copy(update={"transitions": key_cuts(timeline, [x.from_ + 4 for x in extra])})
        sfx = timeline.audio.sfx
    ctx.write_json(OUTPUT, timeline.model_dump(by_alias=True, exclude_none=True))
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
