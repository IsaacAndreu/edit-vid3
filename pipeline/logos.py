"""Company logos (airlines, manufacturers, brands) for the graphics, from Wikimedia Commons.

Commons keeps most corporate logos as SVG files ("Emirates logo.svg"); its thumbnail service renders them as a
transparent PNG of the asked width, so no SVG library is needed here. Cached in cache/logos/; a logo that cannot
be found (or a Commons that refuses the request) just means a map pin without logo.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

import requests

from .context import RunContext
from .sourcing.common import key, tokens

API = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "edit-vid3/1.0 (documentary graphics; logos)"


def _api(session: Any, **params: Any) -> dict[str, Any]:
    response = session.get(API, params={**params, "format": "json"}, headers={"User-Agent": USER_AGENT}, timeout=30)
    response.raise_for_status()
    return response.json()


def find(name: str, session: Any = None) -> str | None:
    """URL of a PNG rendering of `name`'s logo on Commons, or None."""

    session = session or requests
    wanted = tokens(name)
    found = _api(session, action="query", list="search", srsearch=f"{name} logo", srnamespace=6, srlimit=15)
    titles = [r["title"] for r in found.get("query", {}).get("search", [])]

    def good(title: str) -> bool:
        low = title.lower()
        return "logo" in low and wanted <= tokens(title) and not re.search(r"\.(jpe?g|gif|webm|pdf)$", low)

    for title in sorted((t for t in titles if good(t)), key=lambda t: (not t.lower().endswith(".svg"), len(t))):
        info = _api(session, action="query", titles=title, prop="imageinfo", iiprop="url", iiurlwidth=400)
        for page in info.get("query", {}).get("pages", {}).values():
            for item in page.get("imageinfo", []):
                if item.get("thumburl"):
                    return item["thumburl"]
    return None


def logo(ctx: RunContext, name: str, session: Any = None) -> dict[str, Any] | None:
    """Media dict of the logo, copied into work/<slug>/graphics/logos/ (Remotion's public dir), or None."""

    if not name or not ctx.section("graphics").get("logos", True):
        return None
    cached = ctx.cache_dir / "logos" / f"{key(name.lower())[:16]}.png"
    meta = cached.with_suffix(".json")
    if not cached.is_file() and not meta.is_file():
        url = None
        try:
            url = find(name, session)
            if url:
                response = (session or requests).get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
                response.raise_for_status()
                cached.parent.mkdir(parents=True, exist_ok=True)
                cached.write_bytes(response.content)
        except (requests.RequestException, ValueError) as error:
            print(f"   logo de {name}: no disponible ({type(error).__name__})")
            return None                                   # not remembered: try again next time
        meta.parent.mkdir(parents=True, exist_ok=True)
        meta.write_text(json.dumps({"name": name, "url": url}), encoding="utf-8")
    if not cached.is_file():
        return None
    target = ctx.work_dir / "graphics" / "logos" / cached.name
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.is_file():
        shutil.copy2(cached, target)
    return {"src": str(target.relative_to(ctx.work_dir)).replace("\\", "/"), "kind": "image", "source": "wikimedia",
            "credit": "Logo: Wikimedia Commons"}

