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

import shutil
from pathlib import Path
from typing import Any

import hashlib

from .context import RunContext
from .ingest import probe
from .schemas import (
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
    if media.kind == "image":
        return "card"
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

    music = publish(_first_audio(assets / "music"))
    whoosh = publish(_first_audio(assets / "sfx", "whoosh"))
    pop = publish(_first_audio(assets / "sfx", "pop"))
    sfx: list[TimelineSfx] = []
    if whoosh:
        sfx += [TimelineSfx.model_validate({"src": whoosh, "from": max(0, s.from_ - 4), "volume": float(cfg.get("whoosh_volume", 0.6))})
                for s in shots if s.type == "chapter"]
    if pop:
        for group in groups:
            for step in (group.steps or [PanelStep.model_validate({"from": 0, "rows": []})]):
                sfx.append(TimelineSfx.model_validate({"src": pop, "from": group.from_ + step.from_, "volume": float(cfg.get("pop_volume", 0.5))}))

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
        clips = ColdOpenFile.model_validate(ctx.read_json("coldopen.json")).clips
        timeline = with_cold_open(timeline, [
            (str((ctx.root / c.path).relative_to(ctx.work_dir)), c.durationSeconds, c.credit, c.width, c.height)
            for c in clips
        ], fps, float(cfg.get("cold_open_volume", 1.0)))
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
