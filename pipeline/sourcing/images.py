"""Still-image sources with clear licences: Wikimedia Commons, Openverse, Pixabay (optional key).

Only licences that allow commercial use and modification are kept (a monetised channel
crops and animates the images), and every result carries its author and licence for the
on-screen credit and creditos.txt.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import requests

from ..schemas import BrollSpec, Candidate
from .common import (
    USER_AGENT,
    Pacer,
    SourceUnavailable,
    cached_json,
    download_file,
    fuse_ranks,
    http_get_json,
    key,
    strip_html,
    tokens,
)


WIKIMEDIA_API = "https://commons.wikimedia.org/w/api.php"
OPENVERSE_API = "https://api.openverse.org/v1/images/"
PIXABAY_API = "https://pixabay.com/api/"
_RESTRICTIVE = re.compile(r"\b(nc|nd)\b", re.IGNORECASE)  # non-commercial / no-derivatives
_OK_WIKIMEDIA_LICENCES = ("cc0", "public domain", "pd", "cc by", "cc-by", "cc by-sa", "cc-by-sa", "attribution")


# Words that describe camera motion or video formats: useless (or harmful) for still-image search.
_VIDEO_WORDS = frozenset(
    "spinning spin close up closeup close-up aerial drone footage shot shots time lapse timelapse slow motion "
    "pov view b-roll broll video clip 4k hd cinematic tracking pan panning zoom zooming moving walking".split()
)


def image_query(query: str, max_words: int = 4) -> str:
    kept = [w for w in query.split() if w.casefold() not in _VIDEO_WORDS]
    return " ".join(kept[:max_words]) or query


def _short(text: str, limit: int = 40) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


class ImageSources:
    def __init__(self, *, root: Path, cache_dir: Path, config: dict[str, Any], pixabay_key: str = "") -> None:
        self.root = root
        self.cache_dir = cache_dir
        self.cfg = config
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self.min_width = int(config.get("min_width", 1280))
        self.min_aspect = float(config.get("min_aspect", 1.2))
        self.pixabay_key = pixabay_key
        self.pacers = {
            "wikimedia": Pacer(float(config.get("wikimedia", {}).get("min_interval", 0.5))),
            "openverse": Pacer(float(config.get("openverse", {}).get("min_interval", 3.2))),
            "pixabay": Pacer(float(config.get("pixabay", {}).get("min_interval", 1.0))),
            "download": Pacer(0.2),
        }
        self.disabled: dict[str, str] = {}

    # --- query planning -------------------------------------------------------------

    def queries_for(self, broll: BrollSpec) -> dict[str, list[str]]:
        planned: dict[str, list[str]] = {}
        wm_cfg = self.cfg.get("wikimedia", {})
        if wm_cfg.get("enabled", True):
            # Commons shines for concrete named things; generic queries go last.
            planned["wikimedia"] = list(dict.fromkeys(
                [*broll.entities, *(image_query(q, 3) for q in [*broll.queriesLocal[:1], broll.queries[0]])]
            ))[
                : int(wm_cfg.get("queries_per_shot", 3))
            ]
        ov_cfg = self.cfg.get("openverse", {})
        if ov_cfg.get("enabled", True):
            planned["openverse"] = sorted(dict.fromkeys(image_query(q, 3) for q in broll.queries), key=lambda q: len(q.split()))[
                : int(ov_cfg.get("queries_per_shot", 1))
            ]
        px_cfg = self.cfg.get("pixabay", {})
        if px_cfg.get("enabled", True) and self.pixabay_key:
            planned["pixabay"] = sorted(dict.fromkeys(image_query(q, 3) for q in broll.queries), key=lambda q: len(q.split()))[
                : int(px_cfg.get("queries_per_shot", 1))
            ]
        return planned

    # --- search ---------------------------------------------------------------------

    def search(self, broll: BrollSpec, notes: list[str]) -> tuple[dict[str, list[str]], list[Candidate]]:
        planned = self.queries_for(broll)
        per_query: list[list[str]] = []
        found: dict[str, dict[str, Any]] = {}
        for source, queries in planned.items():
            if source in self.disabled:
                continue
            for query in queries:
                try:
                    results = getattr(self, f"_search_{source}")(query)
                except SourceUnavailable as error:
                    self.disabled[source] = str(error)
                    notes.append(f"{source} desactivado en esta ejecución: {error}")
                    break
                except Exception as error:  # one failing query must not sink the shot
                    notes.append(f"{source} {query!r}: {error}")
                    continue
                ids = []
                for item in results:
                    if item["landing"] in {f["landing"] for f in found.values() if f["id"] != item["id"]}:
                        continue  # same file reached through two sources
                    found.setdefault(item["id"], {**item, "query": query})
                    ids.append(item["id"])
                per_query.append(ids)
        scores = fuse_ranks(per_query)
        entity_tokens = tokens(" ".join(broll.entities))
        for item_id, item in found.items():
            if entity_tokens and entity_tokens & tokens(item["title"]):
                scores[item_id] = scores.get(item_id, 0.0) + 0.3
        ranked = sorted(found, key=lambda item_id: -scores.get(item_id, 0.0))[: int(self.cfg.get("max_per_shot", 6))]

        candidates: list[Candidate] = []
        for item_id in ranked:
            item = found[item_id]
            suffix = ".png" if item["mediaUrl"].lower().split("?")[0].endswith(".png") else ".jpg"
            target = self.cache_dir / "images" / item["source"] / f"{key(item['mediaUrl'])}{suffix}"
            try:
                download_file(self.session, item["mediaUrl"], target, pacer=self.pacers["download"])
            except Exception as error:
                notes.append(f"{item_id}: descarga fallida ({type(error).__name__})")
                continue
            candidates.append(
                Candidate(
                    id=item_id,
                    source=item["source"],
                    kind="image",
                    url=item["landing"],
                    title=item["title"],
                    channel=item["author"],
                    license=item["license"],
                    credit=item["credit"],
                    attribution=item["attribution"],
                    width=item["width"],
                    height=item["height"],
                    query=item["query"],
                    rankScore=round(scores.get(item_id, 0.0), 4),
                    imagePath=str(target.relative_to(self.root)),
                )
            )
        return planned, candidates

    def _usable(self, width: Any, height: Any, source: str = "") -> bool:
        try:
            width, height = int(width), int(height)
        except (TypeError, ValueError):
            return False
        min_width = int(self.cfg.get(source, {}).get("min_width", self.min_width))
        return width >= min_width and height > 0 and width / height >= self.min_aspect

    def _search_wikimedia(self, query: str) -> list[dict[str, Any]]:
        params = {
            "action": "query", "format": "json", "generator": "search", "gsrnamespace": 6,
            "gsrsearch": f"{query} filetype:bitmap", "gsrlimit": 12,
            "prop": "imageinfo", "iiprop": "url|size|extmetadata|mime", "iiurlwidth": 1920,
        }
        payload = cached_json(
            self.cache_dir / "search" / "wikimedia" / f"{key(params)}.json",
            lambda: http_get_json(self.session, WIKIMEDIA_API, params=params, pacer=self.pacers["wikimedia"]),
        )
        pages = sorted((payload.get("query") or {}).get("pages", {}).values(), key=lambda p: p.get("index", 0))
        results = []
        for page in pages:
            info = (page.get("imageinfo") or [{}])[0]
            meta = info.get("extmetadata") or {}
            licence = strip_html((meta.get("LicenseShortName") or {}).get("value", ""))
            if info.get("mime") not in ("image/jpeg", "image/png") or not self._usable(info.get("width"), info.get("height")):
                continue
            if not licence or not licence.casefold().startswith(_OK_WIKIMEDIA_LICENCES) or _RESTRICTIVE.search(licence):
                continue
            author = _short(strip_html((meta.get("Artist") or {}).get("value", ""))) or "Wikimedia Commons"
            title = page.get("title", "").removeprefix("File:").rsplit(".", 1)[0]
            landing = info.get("descriptionurl") or f"https://commons.wikimedia.org/wiki/{page.get('title', '')}"
            results.append({
                "id": f"wm:{page.get('pageid')}", "source": "wikimedia", "landing": landing, "title": title,
                "mediaUrl": info.get("thumburl") or info.get("url"), "width": info.get("width"), "height": info.get("height"),
                "author": author, "license": licence,
                "credit": f"Fuente: {author} / Wikimedia Commons",
                "attribution": f"\"{title}\" — {author}, {licence}, Wikimedia Commons: {landing}",
            })
        return results

    def _search_openverse(self, query: str) -> list[dict[str, Any]]:
        params = {"q": query, "page_size": 20, "license_type": "commercial,modification", "mature": "false"}
        payload = cached_json(
            self.cache_dir / "search" / "openverse" / f"{key(params)}.json",
            lambda: http_get_json(self.session, OPENVERSE_API, params=params, pacer=self.pacers["openverse"]),
        )
        results = []
        for item in payload.get("results", []):
            if not self._usable(item.get("width"), item.get("height"), "openverse") or not item.get("url"):
                continue
            if item.get("source") == "wikimedia" and self.cfg.get("wikimedia", {}).get("enabled", True):
                continue  # already searched directly on Commons
            licence = f"CC {str(item.get('license', '')).upper()} {item.get('license_version') or ''}".strip()
            if item.get("license") in ("cc0", "pdm"):
                licence = "CC0" if item["license"] == "cc0" else "Public Domain Mark"
            provider = str(item.get("source") or item.get("provider") or "Openverse").capitalize()
            author = _short(str(item.get("creator") or provider))
            title = _short(str(item.get("title") or query), 80)
            landing = item.get("foreign_landing_url") or item["url"]
            results.append({
                "id": f"ov:{item['id']}", "source": "openverse", "landing": landing, "title": title,
                "mediaUrl": item["url"], "width": item.get("width"), "height": item.get("height"),
                "author": author, "license": licence,
                "credit": f"Fuente: {author} / {provider}",
                "attribution": str(item.get("attribution") or f"\"{title}\" — {author}, {licence}: {landing}"),
            })
        return results

    def _search_pixabay(self, query: str) -> list[dict[str, Any]]:
        params = {"q": query[:100], "image_type": "photo", "orientation": "horizontal",
                  "min_width": self.min_width, "per_page": 12, "safesearch": "true"}
        payload = cached_json(
            self.cache_dir / "search" / "pixabay" / f"{key(params)}.json",
            lambda: http_get_json(
                self.session, PIXABAY_API, params={**params, "key": self.pixabay_key}, pacer=self.pacers["pixabay"]
            ),
        )
        results = []
        for hit in payload.get("hits", []):
            if not self._usable(hit.get("imageWidth"), hit.get("imageHeight")):
                continue
            author = _short(str(hit.get("user") or "Pixabay"))
            results.append({
                "id": f"px:{hit['id']}", "source": "pixabay", "landing": hit["pageURL"], "title": str(hit.get("tags", query)),
                "mediaUrl": hit.get("largeImageURL"), "width": hit.get("imageWidth"), "height": hit.get("imageHeight"),
                "author": author, "license": "Pixabay Content License",
                "credit": f"Fuente: {author} / Pixabay",
                "attribution": f"{author} — Pixabay Content License: {hit['pageURL']}",
            })
        return results
