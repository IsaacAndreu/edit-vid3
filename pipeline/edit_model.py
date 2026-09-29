"""The edited timeline: the pipeline's edit (timeline.base.json) + the changes made in the editor
(work/<slug>/edits.json), rebuilt from scratch every time so any change can be undone.

Changes, in the order they are applied:
- shots: own footage uploaded by hand, footage taken from another shot (drag one shot onto another
  swaps them), moved cuts (trimming a shot moves the cut it shares with its neighbour; the zoom/whip
  transition and its whoosh move with it);
- graphics and stats: removed, retimed (dragged / resized), texts and figures changed, new ones from
  the templates;
- labels: text changed or removed, retimed, new ones;
- audio: another music track for a chapter, sound effects moved / removed / re-levelled / added;
- scenes: reordered or deleted, narration included (the voice is re-cut by scene, see reorder()).

Coordinates: every change is stored in the pipeline's own frames (before any scene reordering), so a
later reorder never breaks it. The page converts with the `timeMap` returned in the state.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

MIN_SHOT = 12                     # frames: no shot shorter than this after a trim
EMPTY: dict[str, Any] = {"footage": {}, "own": {}, "media": {}, "cuts": {}, "texts": {}, "removed": [], "timing": {},
                         "added": [], "labels": {}, "labelTiming": {}, "addedLabels": [], "music": {},
                         "sfx": {"removed": [], "moved": {}, "volume": {}, "added": []}, "order": [], "deleted": []}


def normalise(edits: dict[str, Any] | None) -> dict[str, Any]:
    out = copy.deepcopy(EMPTY)
    for key, value in (edits or {}).items():
        if key == "sfx" and isinstance(value, dict):
            out["sfx"].update(value)
        elif key in out and value is not None:
            out[key] = value
    return out


def is_empty(edits: dict[str, Any]) -> bool:
    e = normalise(edits)
    return not any(v for k, v in e.items() if k != "sfx") and not any(e["sfx"].values())


def sfx_key(item: dict[str, Any]) -> str:
    return f"{Path(item['src']).name}@{item['from']}"


def _set_path(target: Any, path: str, value: Any) -> None:
    """target["a"]["b"][0]["c"] = value from "a.b.0.c" (only where that path already exists)."""

    keys = path.split(".")
    for key in keys[:-1]:
        target = target[int(key)] if isinstance(target, list) else target[key]
    last = keys[-1]
    if isinstance(target, list):
        target[int(last)] = value
    elif last in target:
        target[last] = value


# --- shots ----------------------------------------------------------------------------------------

def _shots(t: dict[str, Any], e: dict[str, Any]) -> dict[int, int]:
    """Media swaps, own uploads and moved cuts. Returns {old cut frame: new cut frame}."""

    shots = t["shots"]
    by_id = {s["id"]: s for s in shots}
    base_media = {s["id"]: copy.deepcopy(s.get("media")) for s in shots}
    for target, source in e["media"].items():
        if target in by_id and source in base_media and base_media[source] and by_id[target].get("media"):
            by_id[target]["media"] = copy.deepcopy(base_media[source])
    for target, own in e["own"].items():
        if target in by_id and own.get("src"):
            by_id[target]["media"] = {"src": own["src"], "kind": own.get("kind", "video"), "source": "propio",
                                      "credit": own.get("credit") or "Fuente: propia", "layout": "full"}
    moved: dict[int, int] = {}
    for i, shot in enumerate(shots):
        if i == 0 or shot["id"] not in e["cuts"] or shot["type"] == "endscreen":
            continue
        prev = shots[i - 1]
        end = shot["from"] + shot["durationInFrames"]
        new = int(e["cuts"][shot["id"]])
        new = max(prev["from"] + MIN_SHOT, min(end - MIN_SHOT, new))
        moved[shot["from"]] = new
        prev["durationInFrames"] = new - prev["from"]
        shot["durationInFrames"] = end - new
        shot["from"] = new
    return moved


def _follow_cut(frame: int, moved: dict[int, int], reach: int = 7) -> int:
    """A frame tied to a cut (transition, whoosh) moves with it."""

    for old, new in moved.items():
        if abs(frame - old) <= reach:
            return frame + new - old
    return frame


# --- groups and labels ---------------------------------------------------------------------------------

def _groups(t: dict[str, Any], e: dict[str, Any]) -> dict[str, tuple[int, int, int]]:
    """Removals, retiming, texts and new groups. Returns {group id: (old from, old end, shift)}."""

    removed = set(e["removed"])
    t["groups"] = [g for g in t["groups"] if g["id"] not in removed]
    t["groups"] += [copy.deepcopy(g) for g in e["added"] if g.get("id") not in removed]
    groups = {g["id"]: g for g in t["groups"]}
    for key, value in e["texts"].items():
        kind, _, rest = key.partition(":")
        try:
            if kind == "group":
                gid, _, path = rest.partition(":")
                if gid in groups:
                    _set_path(groups[gid], path, value)
            elif kind == "chapter":
                shot = next((s for s in t["shots"] if s["id"] == rest), None)
                if shot:
                    shot["chapterTitle"] = value
        except (KeyError, IndexError, ValueError, TypeError):
            continue                       # the timeline changed since: that edit no longer applies
    shifts: dict[str, tuple[int, int, int]] = {}
    total = t["durationInFrames"]
    for gid, (start, length) in e["timing"].items():
        g = groups.get(gid)
        if not g:
            continue
        old = (g["from"], g["from"] + g["durationInFrames"])
        g["durationInFrames"] = max(15, min(int(length), total))
        g["from"] = max(0, min(int(start), total - g["durationInFrames"]))
        shifts[gid] = (old[0], old[1], g["from"] - old[0])
    t["groups"].sort(key=lambda g: g["from"])
    return shifts


def _labels(t: dict[str, Any], e: dict[str, Any]) -> None:
    out = []
    for label in t.get("labels", []):
        original = label["text"]
        text = e["labels"].get(original, original)
        if not text:
            continue
        label = {**label, "text": text, "_original": original}
        if original in e["labelTiming"]:
            start, length = e["labelTiming"][original]
            label["from"], label["durationInFrames"] = max(0, int(start)), max(15, int(length))
        out.append(label)
    out += [{**copy.deepcopy(label), "_added": i} for i, label in enumerate(e["addedLabels"]) if label.get("text")]
    t["labels"] = sorted(out, key=lambda label: label["from"])


# --- audio ------------------------------------------------------------------------------------------------

def _audio(t: dict[str, Any], e: dict[str, Any], moved: dict[int, int], shifts: dict[str, tuple[int, int, int]]) -> None:
    audio = t["audio"]
    for index, src in e["music"].items():
        parts = audio.get("musicParts") or []
        if src and 0 <= int(index) < len(parts):
            parts[int(index)]["src"] = src
            parts[int(index)]["mood"] = Path(src).stem.split("-")[0]
    removed, moved_sfx, volume = set(e["sfx"]["removed"]), e["sfx"]["moved"], e["sfx"]["volume"]
    out = []
    for item in audio.get("sfx", []):
        key = sfx_key(item)
        if key in removed:
            continue
        item = {**item, "_key": key}
        if key in moved_sfx:
            item["from"] = max(0, int(moved_sfx[key]))
        elif "whoosh" in Path(item["src"]).name.lower():
            item["from"] = max(0, _follow_cut(item["from"], moved))
        else:                                     # pops and impacts ride with their graphic
            for start, end, shift in shifts.values():
                if start <= item["from"] < end:
                    item["from"] += shift
                    break
        if key in volume:
            item["volume"] = max(0.01, min(1.0, float(volume[key])))
        out.append(item)
    out += [{**item, "_added": i} for i, item in enumerate(e["sfx"]["added"]) if item.get("src")]
    audio["sfx"] = sorted(out, key=lambda s: s["from"])
    t["transitions"] = [{**tr, "from": max(0, _follow_cut(tr["from"] + tr.get("durationInFrames", 12) // 2, moved)
                                        - tr.get("durationInFrames", 12) // 2)} for tr in t.get("transitions", [])]
    for shake in t.get("shakes", []):
        for start, end, shift in shifts.values():
            if start <= shake["from"] < end:
                shake["from"] += shift
                break


# --- scenes --------------------------------------------------------------------------------------------------

def scenes(timeline: dict[str, Any], story: dict[str, Any] | None, min_seconds: float = 6.0) -> list[dict[str, Any]]:
    """The video in scenes: the opening (cold open), one per story event (a case of a list, a stage of a
    life…), the end screen. Very short events join the previous scene."""

    fps = timeline["fps"]
    events = sorted((story or {}).get("events", []), key=lambda ev: ev.get("startWord", 0))
    words = {s["id"]: s.get("startWord", 0) for s in (story or {}).get("shots", [])}

    def event_at(start: int) -> int:
        return max([i for i, ev in enumerate(events) if ev.get("startWord", 0) <= start], default=0)

    # each shot's event; a shot the script does not place (chapter card) goes with the scene it opens,
    # and only the shots before the narration make the opening
    shot_list = timeline["shots"]
    owners: list[int] = []
    for i, shot in enumerate(shot_list):
        if shot["type"] == "endscreen":
            owners.append(10_000)
        elif shot["id"] in words:
            owners.append(event_at(words[shot["id"]]))
        else:
            following = next((s for s in shot_list[i + 1:] if s["id"] in words), None)
            seen = any(s["id"] in words for s in shot_list[:i])
            owners.append(event_at(words[following["id"]]) if following and seen else -1 if not seen else owners[-1])
    owner = {shot["id"]: owners[i] for i, shot in enumerate(shot_list)}

    def event_of(shot: dict[str, Any]) -> int:
        return owner[shot["id"]]

    out: list[dict[str, Any]] = []
    for shot in timeline["shots"]:
        index = event_of(shot)
        if out and out[-1]["event"] == index:
            out[-1]["shots"].append(shot["id"])
            out[-1]["to"] = shot["from"] + shot["durationInFrames"]
            continue
        if index == -1:
            title = "APERTURA"
        elif index == 10_000:
            title = "PANTALLA FINAL"
        else:
            ev = events[index] if events else {}
            words_ = shot.get("text", "").split()
            title = ev.get("tag") or (" ".join(words_[:6]) + ("…" if len(words_) > 6 else "")) or ev.get("label", "")
        out.append({"id": f"sc-{shot['id']}", "event": index, "title": title, "shots": [shot["id"]], "from": shot["from"],
                    "to": shot["from"] + shot["durationInFrames"], "fixed": index in (-1, 10_000)})
    merged: list[dict[str, Any]] = []
    for scene in out:
        if merged and not scene["fixed"] and not merged[-1]["fixed"] and (scene["to"] - scene["from"]) < min_seconds * fps:
            merged[-1]["shots"] += scene["shots"]
            merged[-1]["to"] = scene["to"]
        else:
            merged.append(scene)
    return [{k: v for k, v in s.items() if k != "event"} for s in merged]


def _within(start: int, blocks: list[tuple[int, int, int]]) -> int | None:
    """New frame of an old frame, or None if its scene was deleted."""

    for old_from, old_to, new_from in blocks:
        if old_from <= start < old_to:
            return start - old_from + new_from
    return None


def reorder(ctx: Any, t: dict[str, Any], scene_list: list[dict[str, Any]], order: list[str], deleted: list[str]) -> dict[str, Any]:
    """Scenes in a new order (or some deleted), narration included: the voice track is rebuilt in
    video time (cold-open delay and moment pauses included) and cut by scene."""

    movable = [s for s in scene_list if not s["fixed"]]
    by_id = {s["id"]: s for s in movable}
    wanted = [by_id[i] for i in order if i in by_id] + [s for s in movable if s["id"] not in order]
    wanted = [s for s in wanted if s["id"] not in set(deleted)]
    if [s["id"] for s in wanted] == [s["id"] for s in movable]:
        return t
    head = [s for s in scene_list if s["fixed"] and s["title"] == "APERTURA"]
    tail = [s for s in scene_list if s["fixed"] and s["title"] == "PANTALLA FINAL"]
    blocks: list[tuple[int, int, int]] = []
    cursor = 0
    for scene in head + wanted + tail:
        blocks.append((scene["from"], scene["to"], cursor))
        cursor += scene["to"] - scene["from"]
    fps = t["fps"]
    audio = t["audio"]
    voice = _voice_track(ctx, t, blocks, cursor)
    out = copy.deepcopy(t)
    out["durationInFrames"] = cursor

    def moved(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        kept = []
        for item in items:
            new = _within(item["from"], blocks)
            if new is not None:
                kept.append({**item, "from": new})
        return sorted(kept, key=lambda x: x["from"])

    out["shots"] = moved(t["shots"])
    out["groups"] = moved(t["groups"])
    out["labels"] = moved(t.get("labels", []))
    out["transitions"] = moved(t.get("transitions", []))
    out["shakes"] = moved(t.get("shakes", []))
    new_audio = out["audio"]
    new_audio["sfx"] = moved(audio.get("sfx", []))
    new_audio["clips"] = moved(audio.get("clips", []))
    new_audio["speech"] = sorted([(a - o + n, min(b, e) - o + n) for a, b in audio.get("speech", [])
                                  for o, e, n in blocks if o <= a < e])
    parts = audio.get("musicParts") or []
    pieces = []
    for o, e, n in blocks:                        # each scene keeps the track it had
        part = next((p for p in parts if p["from"] <= o < p["from"] + p["durationInFrames"]), None)
        if part:
            if pieces and pieces[-1]["src"] == part["src"] and pieces[-1]["from"] + pieces[-1]["durationInFrames"] == n:
                pieces[-1]["durationInFrames"] += e - o
            else:
                pieces.append({**part, "from": n, "durationInFrames": e - o})
    new_audio["musicParts"] = pieces
    new_audio["voice"] = voice
    new_audio["voiceFrom"] = 0
    new_audio["voiceGaps"] = []
    out["endscreenFrames"] = t.get("endscreenFrames", 0) if tail else 0
    out["edited"] = {"voiceFrom": audio.get("voiceFrom", 0), "voiceGaps": audio.get("voiceGaps", []),
                     "blocks": [list(b) for b in blocks], "fps": fps}
    return out


def _voice_track(ctx: Any, t: dict[str, Any], blocks: list[tuple[int, int, int]], total: int) -> str:
    """work/<slug>/editor/voz-<hash>.wav: the narration as heard in the video, cut and joined by scene."""

    from .render import voice_chains

    audio = t["audio"]
    fps = t["fps"]
    source = ctx.work_dir / audio["voice"]
    key = hashlib.sha1(json.dumps([blocks, audio.get("voiceFrom"), audio.get("voiceGaps"), source.stat().st_mtime],
                                  default=str).encode()).hexdigest()[:12]
    target = ctx.work_dir / "editor" / f"voz-{key}.wav"
    if target.is_file():
        return str(target.relative_to(ctx.work_dir))
    target.parent.mkdir(parents=True, exist_ok=True)
    chains = voice_chains(0, audio.get("voiceFrom", 0), audio.get("voiceGaps", []), fps, "aresample=48000,aformat=channel_layouts=stereo")
    graph = ";".join(chains) + f";[voice]apad,atrim=0:{max(b[1] for b in blocks) / fps:.4f},asplit={len(blocks)}" \
        + "".join(f"[b{k}]" for k in range(len(blocks)))
    for k, (o, e, _) in enumerate(blocks):
        graph += f";[b{k}]atrim={o / fps:.4f}:{e / fps:.4f},asetpts=PTS-STARTPTS[c{k}]"
    graph += ";" + "".join(f"[c{k}]" for k in range(len(blocks))) + f"concat=n={len(blocks)}:v=0:a=1[out]"
    result = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(source), "-filter_complex", graph, "-map", "[out]",
                             "-t", f"{total / fps:.4f}", "-c:a", "pcm_s16le", str(target)], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"No se pudo recortar la voz: {result.stderr[-300:]}")
    return str(target.relative_to(ctx.work_dir))


# --- clips shorter than their shot ------------------------------------------------------------------------

_LENGTHS: dict[str, float] = {}


def _seconds(path: Path) -> float:
    key = f"{path}:{path.stat().st_mtime_ns}" if path.is_file() else str(path)
    if key not in _LENGTHS:
        result = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                                capture_output=True, text=True)
        try:
            _LENGTHS[key] = float(result.stdout.strip())
        except ValueError:
            _LENGTHS[key] = 0.0
    return _LENGTHS[key]


def stretch(ctx: Any, t: dict[str, Any]) -> None:
    """A shot made longer than its clip: gentle slow motion (up to 1.5x), then the last frame held."""

    from .dub import slow_motion

    fps = t["fps"]
    for shot in t["shots"]:
        media = shot.get("media")
        if not media or media.get("kind") != "video":
            continue
        source = ctx.work_dir / media["src"]
        length = _seconds(source)
        need = shot["durationInFrames"] / fps
        if not length or need <= length + 0.04:
            continue
        target = ctx.work_dir / "editor" / "stretched" / f"{source.stem}-{shot['durationInFrames']}.mp4"
        if not target.is_file():
            slow_motion(source, target, need)
        media["src"] = str(target.relative_to(ctx.work_dir))


def ensure_assets(ctx: Any, t: dict[str, Any]) -> None:
    """Music/sfx chosen in the editor straight from assets/ are copied next to the others (work/audio/)."""

    audio = t["audio"]
    for item in [*(audio.get("musicParts") or []), *audio.get("sfx", [])]:
        src = item["src"]
        if src.startswith("assets/"):
            source = ctx.root / src
            target = ctx.work_dir / "audio" / source.name
            if source.is_file() and not target.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            item["src"] = f"audio/{source.name}"


# --- all together -------------------------------------------------------------------------------------------

def _strip(t: dict[str, Any]) -> dict[str, Any]:
    """Drop the editor's bookkeeping keys (the timeline schema does not allow extra fields)."""

    for item in [*t.get("labels", []), *t["audio"].get("sfx", [])]:
        for key in ("_original", "_added", "_key"):
            item.pop(key, None)
    return t


def build(base: dict[str, Any], edits: dict[str, Any], ctx: Any = None, story: dict[str, Any] | None = None,
          keep_keys: bool = False) -> dict[str, Any]:
    """The edited timeline. Without ctx (tests, quick checks) the steps that make files are skipped.
    keep_keys: leave the bookkeeping keys on (for the editor page's tracks)."""

    e = normalise(edits)
    t = copy.deepcopy(base)
    moved = _shots(t, e)
    shifts = _groups(t, e)
    _labels(t, e)
    _audio(t, e, moved, shifts)
    if ctx is not None:
        ensure_assets(ctx, t)
        stretch(ctx, t)
        if e["order"] or e["deleted"]:
            t = reorder(ctx, t, scenes(t, story), e["order"], e["deleted"])
    return t if keep_keys else _strip(t)


def time_map(t: dict[str, Any]) -> list[list[int]]:
    """[[old from, old to, new from]] when scenes were reordered (the page stores changes in old frames)."""

    return (t.get("edited") or {}).get("blocks") or []


def selection_entry(shot_id: str, footage: dict[str, Any], option: dict[str, Any] | None,
                    candidate: dict[str, Any] | None) -> dict[str, Any] | None:
    """A selection.json entry for footage chosen in the editor: an analysed option, the same video a
    little earlier/later (slip), or a YouTube video found with the editor's own search."""

    start = float(footage.get("start") or 0)
    if option is not None and candidate is not None:
        end = float(footage.get("end") or option.get("end") or start + 3)
        c = candidate
        entry = {"candidateId": option["candidateId"], "source": option["source"], "kind": option["kind"],
                 "analysisPath": option.get("analysisPath") if "end" not in footage else None, "mediaUrl": c.get("mediaUrl"),
                 "url": c["url"], "title": c["title"], "channel": c["channel"], "license": c["license"],
                 "credit": c["credit"], "attribution": c["attribution"], "score": option.get("total"),
                 "phash": option.get("phash") if "end" not in footage else None}
    elif footage.get("url") and str(footage.get("candidateId", "")).startswith("yt:"):
        end = float(footage.get("end") or start + 3)
        channel = str(footage.get("channel") or "YouTube")
        title = str(footage.get("title") or "")
        entry = {"candidateId": footage["candidateId"], "source": "youtube", "kind": "video", "url": footage["url"],
                 "title": title, "channel": channel, "license": "youtube-standard", "credit": f"Fuente: {channel}",
                 "attribution": f"{channel} — \"{title}\": {footage['url']}"}
    else:
        return None
    entry.update({"shotId": shot_id, "status": "selected", "decidedBy": "editor", "start": start, "end": end})
    return {k: v for k, v in entry.items() if v is not None}


def remap_subtitle_time(timeline: Any, frame: int) -> float | None:
    """Video time of a narration frame after scene edits (None if that scene was deleted)."""

    edited = getattr(timeline, "edited", None) or {}
    blocks = edited.get("blocks") or []
    old = edited.get("voiceFrom", 0) + frame + sum(b for at, b in edited.get("voiceGaps", []) if at <= frame)
    new = _within(old, [tuple(b) for b in blocks])
    return None if new is None else new / timeline.fps


def sanitize_name(name: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(name).name).strip("-.") or "archivo"
    return stem[:80]
