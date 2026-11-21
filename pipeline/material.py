"""Material de partida: the videos, channels and own clips you give a video (bloque 4 of
prompts/motor-punteria-prompt.md, first part). The search takes from them first, before searching YouTube blind
sentence by sentence — what a GTA video needs (searching «el atraco al banco» finds anything) and what helps any
channel that knows where its good footage is.

Where it lives:
- materiales/<vídeo>/material.json: {"videos": [YouTube ids], "channels": [channel URLs or @handles],
  "clips": {"<file>": "your tags: Vice Beach de noche, persecución"}}; the clips in materiales/<vídeo>/material/;
- materiales/<canal>/material.json: the same for every video of the channel (the studio's «guardar en el canal»).

What the search does with it (pipeline/sourcing/__init__.py):
- every video you pasted is a candidate of every shot that needs footage (its details: one extraction each,
  cached); the title blocklist never drops it (you chose it: «GTA», «gameplay» are what you want);
- the channels' latest uploads (`material.channel_videos`, 50) come from the YouTube API (two quota units per 50, no
  proxy, cached a week); each shot gets the `material.channel_per_shot` (2) whose titles share most words with it;
- your clips are candidates too, ranked by how many words of the shot their tags or name share; they are yours:
  no 5-second cap of third-party clips and no «Fuente:» on screen.
`material.youtube_search: false` (per channel) leaves the blind search out when there is material.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from pathlib import Path
from typing import Any

MATERIAL_QUERY = "material de partida"
FILE = "material.json"
CLIPS_DIR = "material"
VIDEO_EXTENSIONS = (".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi")
_ID = re.compile(r"(?:v=|youtu\.be/|/shorts/|/embed/|/live/)([A-Za-z0-9_-]{11})")
_BARE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


def video_ids(items: Any) -> list[str]:
    """YouTube ids from links or ids, in order, once each («https://youtu.be/x», «watch?v=x», «x»)."""

    text = items if isinstance(items, str) else "\n".join(str(i) for i in items or [])
    out: list[str] = []
    for token in re.split(r"[\s,]+", text):
        token = token.strip()
        found = _ID.search(token)
        vid = found.group(1) if found else token if _BARE_ID.match(token) else None
        if vid and vid not in out:
            out.append(vid)
    return out


def channel_refs(items: Any) -> list[str]:
    """Channel links or @handles, cleaned («https://www.youtube.com/@Rockstar/videos» → «@Rockstar», a UC… id)."""

    text = items if isinstance(items, str) else "\n".join(str(i) for i in items or [])
    out: list[str] = []
    for token in re.split(r"[\s,]+", text):
        token = token.strip()
        if not token:
            continue
        found = re.search(r"(UC[\w-]{22})", token) or re.search(r"(@[\w.-]+)", token)
        ref = found.group(1) if found else None
        if ref and ref not in out:
            out.append(ref)
    return out


def read(folder: Path) -> dict[str, Any]:
    try:
        data = json.loads((folder / FILE).read_text("utf-8"))
    except (OSError, ValueError):
        data = {}
    return {"videos": video_ids(data.get("videos") or []), "channels": channel_refs(data.get("channels") or []),
            "clips": {str(k): str(v) for k, v in (data.get("clips") or {}).items()}}


def save(folder: Path, videos: Any = None, channels: Any = None, clips: dict[str, str] | None = None) -> dict[str, Any]:
    """Write material.json (only the parts given change); returns what is saved."""

    data = read(folder)
    if videos is not None:
        data["videos"] = video_ids(videos)
    if channels is not None:
        data["channels"] = channel_refs(channels)
    if clips is not None:
        data["clips"] = {**data["clips"], **{str(k): str(v).strip()[:300] for k, v in clips.items()}}
    folder.mkdir(parents=True, exist_ok=True)
    (folder / FILE).write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return data


def clip_name(name: str) -> str:
    """A safe file name for an uploaded clip (letters, digits, - _ .), its extension kept."""

    stem, dot, ext = name.rpartition(".")
    if not dot or f".{ext.lower()}" not in VIDEO_EXTENSIONS:
        raise ValueError("Sube un vídeo (mp4, mov, mkv, webm…)")
    clean = re.sub(r"[^A-Za-z0-9_-]+", "-", stem).strip("-")[:60] or "clip"
    return f"{clean}.{ext.lower()}"


def gather(ctx: Any) -> dict[str, Any]:
    """The video's material plus its channel's (materiales/<canal>/material.json), with the own clips on disk."""

    own = read(ctx.materials_dir)
    group = ctx.materials_dir.parent
    shared = read(group) if group.name != "materiales" else {"videos": [], "channels": [], "clips": {}}
    clips_dir = ctx.materials_dir / CLIPS_DIR
    files = sorted(p for p in clips_dir.iterdir() if p.suffix.lower() in VIDEO_EXTENSIONS) if clips_dir.is_dir() else []
    return {"videos": list(dict.fromkeys([*own["videos"], *shared["videos"]])),
            "channels": list(dict.fromkeys([*own["channels"], *shared["channels"]])),
            "clips": [(p, own["clips"].get(p.name, "")) for p in files]}


def _words(text: str) -> set[str]:
    from .sourcing.common import tokens

    return tokens(text)


def _shot_words(shot: Any) -> set[str]:
    broll = getattr(shot, "broll", None)
    parts = [str(getattr(shot, "text", "") or "")]
    if broll is not None:
        parts += [broll.visualIntent, *broll.queries, *broll.queriesLocal, *broll.entities, str(broll.event or "")]
    idea = getattr(shot, "idea", None)
    if idea is not None:
        parts += [idea.summary or "", *idea.facts]
    return _words(" ".join(parts))


class Material:
    """What the search takes from first, per shot; built lazily and once per video (thread-safe)."""

    def __init__(self, ctx: Any, youtube: Any = None) -> None:
        self.ctx, self.youtube = ctx, youtube
        self.cfg = dict(ctx.section("material") or {})
        self.data = gather(ctx)
        self._lock = threading.Lock()
        self._seeds: list[Any] | None = None
        self._own: list[Any] | None = None
        self._uploads: list[dict[str, Any]] | None = None
        self._made: dict[str, Any] = {}

    @property
    def active(self) -> bool:
        return bool(self.data["videos"] or self.data["channels"] or self.data["clips"])

    def signature(self) -> str:
        """What the material is: links, channels and each clip's name, size and tags (a shot's search depends on it)."""

        clips = [(p.name, p.stat().st_size, tags) for p, tags in self.data["clips"]]
        return hashlib.sha1(json.dumps([self.data["videos"], self.data["channels"], clips,
                                        self.cfg.get("youtube_search", True)]).encode()).hexdigest()[:16]

    @property
    def youtube_search(self) -> bool:
        return bool(self.cfg.get("youtube_search", True)) or not self.active

    # --- the pieces ---------------------------------------------------------------------------------------------
    def seeds(self, notes: list[str]) -> list[Any]:
        with self._lock:
            if self._seeds is None:
                self._seeds = []
                if self.youtube is not None:
                    for vid in self.data["videos"][: int(self.cfg.get("max_videos", 12))]:
                        made = self.youtube.candidate(vid, {"query": MATERIAL_QUERY}, 1.0, notes)
                        if made is not None:
                            self._seeds.append(made)
                        else:
                            notes.append(f"material de partida yt:{vid}: no se puede usar (ver notas)")
            return list(self._seeds)

    def uploads(self, notes: list[str]) -> list[dict[str, Any]]:
        """The channels' latest uploads: API only (two units per 50, no proxy), cached a week per channel."""

        with self._lock:
            if self._uploads is not None:
                return list(self._uploads)
            self._uploads = []
            api = getattr(self.youtube, "api", None) if self.youtube is not None else None
            count = int(self.cfg.get("channel_videos", 50))
            for ref in self.data["channels"]:
                path = self.ctx.cache_dir / "material" / "canales" / f"{hashlib.sha1(f'{ref}|{count}'.encode()).hexdigest()[:16]}.json"
                try:
                    if path.is_file() and time.time() - path.stat().st_mtime < 7 * 86400:
                        found = json.loads(path.read_text("utf-8"))
                    elif api is None:
                        notes.append(f"material de partida {ref}: sin clave de la API de YouTube no se listan sus vídeos")
                        continue
                    else:
                        channel = api.channel(ref)
                        found = [v for v in api.uploads(channel["uploads"], count)
                                 if v.get("duration", 0) >= 30 and v.get("live") == "none"]
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_text(json.dumps(found, ensure_ascii=False), encoding="utf-8")
                    self._uploads += [dict(v, query=MATERIAL_QUERY) for v in found]
                except Exception as error:                # one channel's trouble never stops the search
                    notes.append(f"material de partida {ref}: {str(error)[:120]}")
            return list(self._uploads)

    def own(self) -> list[Any]:
        """Your clips as candidates: a small local preview and its storyboard (cache/material/propio/)."""

        from .schemas import Candidate
        from .sourcing.archive import _to_mp4, storyboard

        with self._lock:
            if self._own is not None:
                return list(self._own)
            self._own = []
            for path, tags in self.data["clips"]:
                stat = path.stat()
                digest = hashlib.sha1(f"{path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}".encode()).hexdigest()[:14]
                folder = self.ctx.cache_dir / "material" / "propio" / digest
                preview = folder / "preview.mp4"
                try:
                    if not preview.is_file():
                        folder.mkdir(parents=True, exist_ok=True)
                        _to_mp4(path, preview)
                    seconds = _duration(preview)
                    board = storyboard(preview, folder, self.ctx.root, seconds)
                except Exception as error:
                    print(f"   material propio {path.name}: no se puede leer ({str(error)[:120]})")
                    continue
                title = tags or path.stem.replace("-", " ").replace("_", " ")
                self._own.append(Candidate(
                    id=f"propio:{digest}", source="propio", kind="video", url=f"file:{path.name}", title=title,
                    channel="material propio", license="propio", credit="Fuente: material propio",
                    attribution=f"Material propio: {path.name}", durationSeconds=round(seconds, 2), query=MATERIAL_QUERY,
                    rankScore=1.0, storyboard=board, mediaUrl=str(path.resolve()),
                    previewPath=str(preview.relative_to(self.ctx.root))))
            return list(self._own)

    # --- per shot -----------------------------------------------------------------------------------------------
    def for_shot(self, shot: Any, notes: list[str]) -> list[Any]:
        """This shot's candidates from the material, best first: your clips (by shared words), the pasted videos,
        and the channels' uploads whose titles share most words with the shot."""

        if not self.active:
            return []
        words = _shot_words(shot)
        out: list[Any] = []
        own = sorted(self.own(), key=lambda c: -len(words & _words(c.title)))
        out += [c.model_copy(update={"rankScore": round(2.0 + 0.1 * len(words & _words(c.title)), 4)})
                for c in own[: int(self.cfg.get("own_per_shot", 4))]]
        out += [c.model_copy(update={"rankScore": 1.5}) for c in self.seeds(notes)]
        per_shot = int(self.cfg.get("channel_per_shot", 2))
        if per_shot and self.data["channels"] and self.youtube is not None:
            ranked = sorted((v for v in self.uploads(notes) if len(words & _words(v.get("title", ""))) >= 2),
                            key=lambda v: (-len(words & _words(v.get("title", ""))), -int(v.get("views") or 0)))
            for entry in ranked:
                if per_shot <= 0:
                    break
                with self._lock:
                    made = self._made.get(entry["id"], False)
                if made is False:
                    made = self.youtube.candidate(entry["id"], entry, 1.0, notes)
                    with self._lock:
                        self._made[entry["id"]] = made
                if made is not None:
                    out.append(made.model_copy(update={"rankScore": 1.2}))
                    per_shot -= 1
        seen: set[str] = set()
        return [c for c in out if not (c.id in seen or seen.add(c.id))]


def chosen_material(candidate: Any) -> bool:
    """A candidate from the material de partida: the title blocklist never drops it."""

    return getattr(candidate, "query", None) == MATERIAL_QUERY


def _duration(path: Path) -> float:
    import subprocess

    done = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
                          capture_output=True, text=True, timeout=60)
    return float((json.loads(done.stdout or "{}").get("format") or {}).get("duration") or 0)
