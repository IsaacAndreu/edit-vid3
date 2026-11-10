"""Photos of places (cities, stadiums) for the pinned polaroids of the old paper map (map style «pins»).

The lead image of the place's English Wikipedia article (a skyline, a landmark): free-licensed files from Commons,
found with one request (generator=search + pageimages). Cached in cache/places/; a place without a photo just gets
an empty polaroid frame.
"""

from __future__ import annotations

import json
import shutil
from typing import Any

import requests

from .context import RunContext
from .sourcing.common import key

API = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "edit-vid3/1.0 (documentary graphics; place photos)"


def find(query: str, session: Any = None) -> str | None:
    """URL of a ~800 px photo of the place `query` («Barcelona, Spain»), or None."""

    response = (session or requests).get(API, params={
        "action": "query", "format": "json", "generator": "search", "gsrsearch": query, "gsrlimit": 1,
        "prop": "pageimages", "piprop": "thumbnail", "pithumbsize": 800}, headers={"User-Agent": USER_AGENT}, timeout=30)
    response.raise_for_status()
    for page in (response.json().get("query") or {}).get("pages", {}).values():
        url = (page.get("thumbnail") or {}).get("source")
        if url and not url.lower().split("?")[0].endswith((".svg.png", ".gif")):   # a flag or a map is no photo
            return url
    return None


def photo(ctx: RunContext, query: str, session: Any = None) -> dict[str, Any] | None:
    """Media dict of the photo, copied into work/<slug>/graphics/places/ (Remotion's public dir), or None."""

    if not query:
        return None
    cached = ctx.cache_dir / "places" / f"{key(query.lower())[:16]}.jpg"
    meta = cached.with_suffix(".json")
    if not cached.is_file() and not meta.is_file():
        url = None
        try:
            url = find(query, session)
            if url:
                response = (session or requests).get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
                response.raise_for_status()
                cached.parent.mkdir(parents=True, exist_ok=True)
                cached.write_bytes(response.content)
        except (requests.RequestException, ValueError) as error:
            print(f"   foto de {query}: no disponible ({type(error).__name__})")
            return None                                   # not remembered: try again next time
        meta.parent.mkdir(parents=True, exist_ok=True)
        meta.write_text(json.dumps({"query": query, "url": url}), encoding="utf-8")
    if not cached.is_file():
        return None
    target = ctx.work_dir / "graphics" / "places" / cached.name
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.is_file():
        shutil.copy2(cached, target)
    return {"src": str(target.relative_to(ctx.work_dir)).replace("\\", "/"), "kind": "image", "source": "wikimedia",
            "credit": "Foto: Wikipedia"}
