"""Stage 8 — build work/<slug>/timeline.json, the props of the Remotion composition.

Merges shots (what each shot shows), stage-6 media and stage-7 fallback media into a
frame-accurate list of shots, plus:
- groups: consecutive datacard/split shots sharing a panel (rows revealed step by step)
  and stat shots (one continuous number while the b-roll keeps cutting underneath);
- audio: the narration, optional music from assets/music/ (ducked while the voice speaks)
  and optional SFX from assets/sfx/ (whoosh on chapters, pop on data).

work/<slug>/ is Remotion's public dir, so every path here is relative to it; the voice
and any music/SFX are copied into work/<slug>/audio/.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from .context import RunContext
from .schemas import (
    FallbackFile,
    IngestFile,
    PanelStep,
    ShotsFile,
    Timeline,
    TimelineAudio,
    TimelineGroup,
    TimelineMedia,
    TimelineSfx,
    TimelineShot,
    WordsFile,
)
from .sourcing import needs_footage


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


def _first_audio(folder: Path, prefix: str = "") -> Path | None:
    if not folder.is_dir():
        return None
    files = sorted(p for p in folder.iterdir() if p.suffix.lower() in AUDIO_EXTENSIONS and p.name.lower().startswith(prefix))
    return files[0] if files else None


def inputs(ctx: RunContext) -> list:
    return [
        ctx.work_dir / "shots.json", ctx.work_dir / "words.json", ctx.work_dir / "media" / "_ingest.json",
        ctx.work_dir / "fallback.json", ctx.materials_dir / "voz.mp3", ctx.root / "assets",
    ]


def run(ctx: RunContext) -> None:
    cfg = ctx.section("timeline")
    fps = ctx.fps
    video = ctx.section("video")
    shots_file = ShotsFile.model_validate(ctx.read_json("shots.json"))
    words = WordsFile.model_validate(ctx.read_json("words.json"))
    total_frames = round(shots_file.durationSeconds * fps)

    # Media per shot: stage 6 first, stage 7 for the rest. Paths relative to the public dir.
    media: dict[str, TimelineMedia] = {}
    for item in IngestFile.model_validate_json((ctx.work_dir / "media" / "_ingest.json").read_text("utf-8")).media:
        media[item.shotId] = TimelineMedia(
            src=str((ctx.root / item.path).relative_to(ctx.work_dir)), kind=item.kind, source=item.source, credit=item.credit,
        )
    for item in FallbackFile.model_validate(ctx.read_json("fallback.json")).items:
        media.setdefault(item.shotId, TimelineMedia(
            src=str((ctx.root / item.path).relative_to(ctx.work_dir)), kind=item.kind, source=item.source,
            credit=item.credit,
        ))

    # Frame-accurate shots: each starts where the previous ended.
    starts = [round(s.start * fps) for s in shots_file.shots] + [total_frames]
    starts[0] = 0
    shots: list[TimelineShot] = []
    missing = []
    for index, shot in enumerate(shots_file.shots):
        m = media.get(shot.id) if needs_footage(shot) else None
        if needs_footage(shot) and m is None:
            missing.append(shot.id)
        shots.append(TimelineShot.model_validate({
            "id": shot.id, "type": shot.type, "from": starts[index],
            "durationInFrames": starts[index + 1] - starts[index], "text": shot.text,
            "media": m.model_dump() if m else None, "chapterTitle": shot.chapterTitle,
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
        height=int(video.get("height", 1080)), durationInFrames=total_frames, shots=shots, groups=groups,
        audio=TimelineAudio(
            voice=str(voice.relative_to(ctx.work_dir)), music=music,
            musicVolume=float(cfg.get("music_volume", 0.25)),
            duckedVolume=float(cfg.get("music_volume", 0.25)) * 10 ** (-float(cfg.get("duck_db", 18)) / 20),
            speech=speech_segments(words, fps), sfx=sfx,
        ),
    )
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
