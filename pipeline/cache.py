"""Content-addressed JSON cache and atomic file helpers."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .templates import PROJECT_ROOT


CACHE_DIR_ENV = "EDIT_VID3_CACHE_DIR"


def default_cache_dir() -> Path:
    configured = os.getenv(CACHE_DIR_ENV, "").strip()
    return Path(configured).expanduser() if configured else PROJECT_ROOT / ".cache" / "edit-vid3"


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(*parts: str) -> str:
    digest = hashlib.sha256()
    for part in parts:
        encoded = part.encode("utf-8")
        digest.update(str(len(encoded)).encode("ascii") + b":")
        digest.update(encoded)
    return digest.hexdigest()


def atomic_write_text(path: Path, text: str) -> None:
    """Write through a temp file so a crash never leaves a half-written file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(text)
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def atomic_write_json(path: Path, payload: Any) -> None:
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def read_json(path: Path) -> Any | None:
    """Return parsed JSON, or ``None`` when the file is missing or corrupt."""

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


class JsonCache:
    """Tiny on-disk cache: ``<root>/<namespace>/<key>.json``."""

    def __init__(self, root: Path | None = None, *, enabled: bool = True) -> None:
        self.root = root or default_cache_dir()
        self.enabled = enabled

    def _path(self, namespace: str, key: str) -> Path:
        return self.root / namespace / f"{key}.json"

    def get(self, namespace: str, key: str) -> Any | None:
        if not self.enabled:
            return None
        return read_json(self._path(namespace, key))

    def put(self, namespace: str, key: str, value: Any) -> None:
        """Always stores, even when reads are disabled, so ``--fresh`` refreshes the entry."""

        try:
            atomic_write_json(self._path(namespace, key), value)
        except OSError:
            pass
