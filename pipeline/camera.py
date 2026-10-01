"""Camera moves and breathing room on the timeline (stage timeline):

- slow zoom: shots the planner marked `pace: slow` (emotional lines) push in slowly, 1.00 → 1.08;
- emphasis zoom: a quick 6-8 % punch-in on the word the narrator stresses (a figure, a key word),
  found in the voice itself: the word is clearly louder than the rest of its sentence;
- chapter pause: the narration stops for half a second when a chapter begins, the chapter card holds.

Zooms are stored on the shot's media as [start frame in the shot, frames, final scale]; Remotion and the
ffmpeg fast path of the render draw them the same way (ease-out, then hold).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

import numpy as np

from .schemas import Timeline, TimelineShot, WordsFile

FUNCTION = frozenset(
    "a al ante con de del desde el en entre hacia hasta la las lo los mi mis muy no o para por que se si sin su "
    "sus te tu tus un una unos unas y e ni ya más le les nos cuando donde como cada pero porque este esta esto ese "
    "esa eso the and of to in on at for with".split()
)
ZOOMABLE = ("full", "archive")


def voice_levels(path: Path, words: WordsFile) -> list[float]:
    """Loudness (dB) of every word in the narration."""

    try:
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                             capture_output=True, check=True, timeout=300).stdout
    except (subprocess.SubprocessError, OSError):
        return []
    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    levels = []
    for word in words.words:
        piece = samples[int(word.start * 16000): max(int(word.start * 16000) + 1, int(word.end * 16000))]
        rms = float(np.sqrt(np.mean(piece ** 2))) if piece.size else 0.0
        levels.append(20 * np.log10(max(rms, 1e-5)))
    return levels


def emphasis_words(words: WordsFile, levels: list[float], cfg: dict[str, Any]) -> list[int]:
    """Indexes of stressed words, strongest first: a figure or a content word ≥ `emphasis_db` louder than
    the median of its sentence."""

    if len(levels) != len(words.words):
        return []
    louder = float(cfg.get("emphasis_db", 2.5))
    found: list[tuple[float, int]] = []
    start = 0
    for i, word in enumerate(words.words):
        if not (word.sentenceEnd or i == len(words.words) - 1):
            continue
        median = float(np.median(levels[start: i + 1]))
        for j in range(start, i + 1):
            text = re.sub(r"[^\w%]", "", words.words[j].text.lower())
            figure = any(c.isdigit() for c in text)
            content = len(text) >= 6 and text not in FUNCTION
            margin = levels[j] - median
            if (figure and margin >= louder - 1.0) or (content and margin >= louder):
                found.append((margin + (1.0 if figure else 0.0), j))
        start = i + 1
    return [j for _, j in sorted(found, reverse=True)]


def add_zooms(shots: list[TimelineShot], paces: dict[str, str], words: WordsFile, levels: list[float], fps: int,
              cfg: dict[str, Any]) -> tuple[int, int]:
    """Slow zooms on `slow` shots, emphasis zooms on stressed words. Returns (slow, emphasis) counts."""

    slow = 0
    if cfg.get("slow_zoom", True):
        for shot in shots:
            if paces.get(shot.id) == "slow" and shot.media and shot.media.kind == "video" and shot.media.layout in ZOOMABLE:
                shot.media = shot.media.model_copy(update={"zoom": [0, shot.durationInFrames, float(cfg.get("slow_zoom_scale", 1.08))]})
                slow += 1
    if not cfg.get("emphasis_zoom", True):
        return slow, 0
    gap = round(float(cfg.get("emphasis_gap", 6.0)) * fps)
    scale = float(cfg.get("emphasis_scale", 1.07))
    most = int(len(shots) * float(cfg.get("emphasis_share", 0.12)))
    placed: list[int] = []
    for j in emphasis_words(words, levels, cfg):
        if len(placed) >= most:
            break
        at = round(words.words[j].start * fps)
        if any(abs(at - p) < gap for p in placed):
            continue
        shot = next((s for s in shots if s.from_ <= at < s.from_ + s.durationInFrames), None)
        if shot is None or not shot.media or shot.media.zoom or shot.type != "broll" or shot.media.layout not in ZOOMABLE:
            continue
        offset = max(0, at - shot.from_ - 2)              # lands just as the word starts
        if shot.durationInFrames - offset < 8:
            continue
        shot.media = shot.media.model_copy(update={"zoom": [offset, 6, scale]})
        placed.append(at)
    return slow, len(placed)


def voice_frame_at(gaps: list[tuple[int, int]], at: int) -> int:
    """Narration frame playing at timeline frame `at` (timeline frames = voice frames + earlier gaps)."""

    shift = 0
    for voice, frames in sorted(gaps):
        if voice + shift >= at:
            break
        shift += frames
    return at - shift


def with_chapter_pauses(timeline: Timeline, seconds: float, fps: int) -> Timeline:
    """The narration pauses `seconds` as each chapter starts; the chapter shot holds that much longer
    (its clip slowed down to fill it) and everything after it moves."""

    frames = round(seconds * fps)
    if frames <= 0:
        return timeline
    for chapter in [s.id for s in timeline.shots if s.type == "chapter" and s.from_ > 0]:
        shot = next(s for s in timeline.shots if s.id == chapter)
        at = shot.from_
        voice_at = voice_frame_at(list(timeline.audio.voiceGaps), at)

        def moved(item: Any) -> Any:
            return item.model_copy(update={"from_": item.from_ + frames}) if item.from_ > at or (
                item.from_ == at and not isinstance(item, TimelineShot)) else item

        longer = shot.durationInFrames + frames
        media = shot.media
        if media and media.kind == "video":
            media = media.model_copy(update={"rate": round(shot.durationInFrames / longer * (media.rate or 1.0), 4)})
        shots = [s.model_copy(update={"durationInFrames": longer, "media": media}) if s.id == chapter else moved(s)
                 for s in timeline.shots]
        speech = []
        for a, b in timeline.audio.speech:
            if b <= at:
                speech.append((a, b))
            elif a >= at:
                speech.append((a + frames, b + frames))
            else:
                speech += [(a, at), (at + frames, b + frames)]
        audio = timeline.audio.model_copy(update={
            "clips": [moved(c) for c in timeline.audio.clips], "sfx": [moved(x) for x in timeline.audio.sfx],
            "speech": speech, "voiceGaps": sorted([*timeline.audio.voiceGaps, (voice_at, frames)]),
        })
        timeline = Timeline.model_validate({
            **timeline.model_dump(by_alias=True),
            "durationInFrames": timeline.durationInFrames + frames,
            "shots": [s.model_dump(by_alias=True) for s in shots],
            "groups": [moved(g).model_dump(by_alias=True) for g in timeline.groups],
            "labels": [moved(label).model_dump(by_alias=True) for label in timeline.labels],
            "audio": audio.model_dump(by_alias=True),
        })
    return timeline
