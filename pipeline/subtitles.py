"""Subtitle cue model and parsers (WebVTT and YouTube json3)."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from html import unescape
from pathlib import Path


@dataclass(frozen=True)
class SubtitleCue:
    start_seconds: float
    end_seconds: float
    text: str


_TAG_RE = re.compile(r"<[^>]*>")
_TIMING_RE = re.compile(r"^\s*(\S+)\s+-->\s+(\S+)")


def clean_subtitle_text(text: str) -> str:
    return " ".join(unescape(_TAG_RE.sub("", text)).split())


def parse_timestamp(timestamp: str) -> float | None:
    normalized = timestamp.replace(",", ".")
    pieces = normalized.split(".", 1)
    clock = pieces[0].split(":")
    if len(clock) == 2:
        hours = 0
        minutes, seconds = clock
    elif len(clock) == 3:
        hours, minutes, seconds = clock
    else:
        return None
    try:
        fraction = float(f"0.{pieces[1]}") if len(pieces) == 2 else 0.0
        value = int(hours) * 3600 + int(minutes) * 60 + int(seconds) + fraction
    except ValueError:
        return None
    return float(value) if math.isfinite(value) else None


def parse_vtt(content: str) -> list[SubtitleCue]:
    lines = content.lstrip("﻿").splitlines()
    cues: list[SubtitleCue] = []
    index = 0
    while index < len(lines):
        timing = _TIMING_RE.match(lines[index])
        if timing is None:
            index += 1
            continue
        start = parse_timestamp(timing.group(1))
        end = parse_timestamp(timing.group(2))
        index += 1
        text_lines: list[str] = []
        while index < len(lines) and lines[index].strip():
            if re.match(r"^\s*\S+\s+-->\s+\S+", lines[index]):
                break
            text_lines.append(lines[index])
            index += 1
        text = clean_subtitle_text(" ".join(text_lines))
        if start is not None and end is not None and end > start and text:
            cues.append(SubtitleCue(start, end, text))
        while index < len(lines) and not lines[index].strip():
            index += 1
    return cues


def parse_json3(content: str) -> list[SubtitleCue]:
    try:
        payload = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return []
    cues: list[SubtitleCue] = []
    for event in payload.get("events", []) if isinstance(payload, dict) else []:
        if not isinstance(event, dict):
            continue
        try:
            start = float(event["tStartMs"]) / 1000
            end = start + float(event["dDurationMs"]) / 1000
        except (KeyError, TypeError, ValueError):
            continue
        segments = event.get("segs", [])
        text = clean_subtitle_text(
            "".join(str(segment.get("utf8", "")) for segment in segments if isinstance(segment, dict))
        )
        if math.isfinite(start) and math.isfinite(end) and end > start and text:
            cues.append(SubtitleCue(start, end, text))
    return cues


def subtitle_language_rank(path: Path, video_id: str) -> tuple[int, str]:
    """Spanish tracks first, then English, then anything else."""

    suffix = path.name.removeprefix(f"{video_id}.")
    language = suffix.split(".", 1)[0].casefold()
    if language == "es" or language.startswith("es-"):
        rank = 0
    elif language == "en" or language.startswith("en-"):
        rank = 1
    else:
        rank = 2
    return rank, path.name.casefold()


def read_best_subtitles(directory: Path, video_id: str) -> tuple[SubtitleCue, ...]:
    """Parse the preferred subtitle file yt-dlp wrote for ``video_id`` in ``directory``."""

    try:
        subtitle_files = [
            path
            for path in directory.iterdir()
            if path.is_file()
            and path.suffix.lower() in {".vtt", ".json3"}
            and path.name.startswith(f"{video_id}.")
        ]
    except OSError:
        return ()
    subtitle_files.sort(key=lambda path: subtitle_language_rank(path, video_id))
    for path in subtitle_files:
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError):
            continue
        cues = parse_vtt(text) if path.suffix.lower() == ".vtt" else parse_json3(text)
        if cues:
            unique = {
                (cue.start_seconds, cue.end_seconds, cue.text): cue
                for cue in cues
                if cue.text
            }
            return tuple(sorted(unique.values(), key=lambda cue: (cue.start_seconds, cue.end_seconds)))
    return ()
