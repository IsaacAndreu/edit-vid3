"""Resumable state of the media stage (``<output>.media.json``).

Two levels are stored so an interrupted run loses as little as possible:

* ``thirdParty``: the result of each YouTube selection attempt (the slow part),
  written as soon as that attempt ends;
* ``scenes``: scenes whose media is completely resolved.

Entries carry a fingerprint of the scene plan, so editing the script, the
segmentation or an override invalidates only the scenes that changed.
"""

from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path
from typing import Any

from .cache import atomic_write_json, read_json
from .types import SceneDraft


CHECKPOINT_VERSION = 1
_FINGERPRINT_KEYS = (
    "text",
    "keywords",
    "visualIntent",
    "mustContain",
    "avoid",
    "preferredShot",
    "sceneType",
    "templateName",
    "durationInFrames",
    "start_word_index",
    "end_word_index",
    "mediaOverride",
)


def scene_fingerprint(scene: SceneDraft, *extra: object) -> str:
    payload = {key: scene.get(key) for key in _FINGERPRINT_KEYS}
    encoded = json.dumps([payload, [str(item) for item in extra]], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:20]


class MediaCheckpoint:
    """Thread-safe checkpoint. With ``path=None`` it only lives in memory."""

    def __init__(self, path: Path | None = None, *, load: bool = True) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._third_party: dict[str, dict[str, Any]] = {}
        self._scenes: dict[str, dict[str, Any]] = {}
        self._rejected: dict[str, dict[str, list[str]]] = {}
        self.loaded = False
        if path is not None and load:
            payload = read_json(path)
            if isinstance(payload, dict) and payload.get("version") == CHECKPOINT_VERSION:
                self._third_party = dict(payload.get("thirdParty") or {})
                self._scenes = dict(payload.get("scenes") or {})
                self._rejected = dict(payload.get("rejected") or {})
                self.loaded = bool(self._third_party or self._scenes)

    # ---- persistence -------------------------------------------------
    def save(self) -> None:
        if self.path is None:
            return
        with self._lock:
            payload = {
                "version": CHECKPOINT_VERSION,
                "thirdParty": self._third_party,
                "scenes": self._scenes,
                "rejected": self._rejected,
            }
            try:
                atomic_write_json(self.path, payload)
            except OSError:
                pass

    # ---- third-party attempts ---------------------------------------
    @staticmethod
    def slot_key(scene_number: int, slot: str | None) -> str:
        return f"{scene_number}:{'' if slot is None else slot}"

    def get_third_party(self, key: str, fingerprint: str) -> tuple[bool, dict[str, Any] | None, dict[str, Any] | None]:
        with self._lock:
            entry = self._third_party.get(key)
        if not isinstance(entry, dict) or entry.get("fingerprint") != fingerprint:
            return False, None, None
        return True, entry.get("record"), entry.get("trace")

    def put_third_party(
        self,
        key: str,
        fingerprint: str,
        record: dict[str, Any] | None,
        trace: dict[str, Any] | None,
    ) -> None:
        with self._lock:
            self._third_party[key] = {"fingerprint": fingerprint, "record": record, "trace": trace}
        self.save()

    # ---- resolved scenes --------------------------------------------
    def get_scene(self, scene_number: int, fingerprint: str) -> SceneDraft | None:
        with self._lock:
            entry = self._scenes.get(str(scene_number))
        if not isinstance(entry, dict) or entry.get("fingerprint") != fingerprint:
            return None
        scene = entry.get("scene")
        return dict(scene) if isinstance(scene, dict) else None  # type: ignore[return-value]

    def put_scene(self, scene_number: int, fingerprint: str, scene: SceneDraft) -> None:
        with self._lock:
            self._scenes[str(scene_number)] = {"fingerprint": fingerprint, "scene": dict(scene)}

    def stored_scene(self, scene_number: int) -> SceneDraft | None:
        """Whatever was stored for the scene, regardless of fingerprint."""

        with self._lock:
            entry = self._scenes.get(str(scene_number))
        scene = entry.get("scene") if isinstance(entry, dict) else None
        return dict(scene) if isinstance(scene, dict) else None  # type: ignore[return-value]

    def forget_scene(self, scene_number: int) -> None:
        prefix = f"{scene_number}:"
        with self._lock:
            self._scenes.pop(str(scene_number), None)
            for key in [key for key in self._third_party if key.startswith(prefix)]:
                self._third_party.pop(key, None)

    # ---- rejected picks (operator asked to redo a scene) -------------
    def reject(self, scene_number: int, *, video_ids: list[str], asset_urls: list[str]) -> None:
        with self._lock:
            entry = self._rejected.setdefault(str(scene_number), {"videoIds": [], "assetUrls": []})
            for video_id in video_ids:
                if video_id and video_id not in entry["videoIds"]:
                    entry["videoIds"].append(video_id)
            for url in asset_urls:
                if url and url not in entry["assetUrls"]:
                    entry["assetUrls"].append(url)

    def rejected_video_ids(self, scene_number: int) -> set[str]:
        with self._lock:
            return set((self._rejected.get(str(scene_number)) or {}).get("videoIds") or [])

    def rejected_asset_urls(self) -> set[str]:
        with self._lock:
            urls: set[str] = set()
            for entry in self._rejected.values():
                urls.update(entry.get("assetUrls") or [])
            return urls
