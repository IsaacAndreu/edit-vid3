"""Still-image sources: Wikimedia Commons, Openverse, Pixabay (optional key) — with clear licences —
and web photos of the named people/events (like a Google Images search).

For the free-licence sources only licences that allow commercial use and modification are kept.
Web photos (`images.web`) are press/editorial pictures without a free licence — the same material
sports channels use; they are credited with their website. They come from Google Images through
Serper (SERPER_API_KEY) or, without a key, from DuckDuckGo (works from a home connection; data
centres get junk). A web photo is kept only if the searched name appears in its title or URL.
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
SERPER_IMAGES_API = "https://google.serper.dev/images"
_RESTRICTIVE = re.compile(r"\b(nc|nd)\b", re.IGNORECASE)  # non-commercial / no-derivatives
_OK_WIKIMEDIA_LICENCES = ("cc0", "public domain", "pd", "cc by", "cc-by", "cc by-sa", "cc-by-sa", "attribution")


# Words that describe camera motion or video formats: useless (or harmful) for still-image search.
_VIDEO_WORDS = frozenset(
    "spinning spin close up closeup close-up aerial drone footage shot shots time lapse timelapse slow motion "
    "pov view b-roll broll video clip 4k hd cinematic tracking pan panning zoom zooming moving walking".split()
)


# Stock agencies serve their previews with a big watermark across the picture (and sell the licence).
WATERMARKED = ("alamy", "gettyimages", "shutterstock", "istockphoto", "dreamstime", "depositphotos", "123rf",
               "adobestock", "stock.adobe", "agefotostock", "superstock", "bigstockphoto", "pond5", "photoshelter",
               "imago-images", "dpa-picture", "aflo", "zumapress", "sportsphoto", "pinterest", "pinimg", "asiatravel",
               "bridgemanimages", "bridgeman", "granger.com", "topfoto", "akg-images", "maryevans", "ullsteinbild",
               "mediadrumimages", "rexfeatures", "artofit", "fity.club",
               # re-posting / SEO spam sites (avion8: an FBI raid «wallpaper», a logo vector, a LinkedIn scrape)
               "wallpapers.com", "wallpaper", "glimpsetrio", "infoupdate.org", "freelogovectors", "logos-world",
               "pngtree", "pngwing", "vecteezy", "storytelling.org", "ukobbq")


def watermarked(text: str, extra: Any = None) -> bool:
    """A picture from a stock agency (watermarked preview) or a site that only re-posts others' pictures."""

    low = text.lower()
    return any(site in low for site in (*WATERMARKED, *[str(s).lower() for s in (extra or [])]))


def image_query(query: str, max_words: int = 4) -> str:
    kept = [w for w in query.split() if w.casefold() not in _VIDEO_WORDS]
    return " ".join(kept[:max_words]) or query


def web_queries(broll: BrollSpec) -> list[tuple[str, set[str]]]:
    """Photo searches for the named people/places of a shot: the name alone, then the name with the
    shot's event context. Each carries the name tokens a result must mention."""

    out: list[tuple[str, set[str]]] = []
    for entity in broll.entities[:2]:
        must = tokens(entity)
        if not must:
            continue
        event = broll.event or ""
        if event and must <= tokens(event):
            out.append((event, must))
        out.append((entity, must))
    seen: set[str] = set()
    return [(q, m) for q, m in out if not (q in seen or seen.add(q))]


def mentions(must: set[str], text: str) -> bool:
    """All name tokens (e.g. {'carlos', 'yulo'}) appear in the title/URL — so 'Carlos Alcaraz' never passes."""

    found = tokens(text.replace("-", " ").replace("_", " ").replace("/", " "))
    return bool(must) and must <= found


def site_name(url: str) -> str:
    host = re.sub(r"^https?://", "", url.strip()).split("/")[0].lower()
    return host.removeprefix("www.") or "web"


def _short(text: str, limit: int = 40) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


class ImageSources:
    def __init__(self, *, root: Path, cache_dir: Path, config: dict[str, Any], pixabay_key: str = "",
                 serper_key: str = "") -> None:
        self.root = root
        self.cache_dir = cache_dir
        self.cfg = config
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self.min_width = int(config.get("min_width", 1280))
        self.min_aspect = float(config.get("min_aspect", 1.2))
        self.pixabay_key = pixabay_key
        self.serper_key = serper_key
        self.web_must: dict[str, set[str]] = {}   # web query → name tokens a result must mention
        self.pacers = {
            "web": Pacer(float(config.get("web", {}).get("min_interval", 1.5))),
            "wikimedia": Pacer(float(config.get("wikimedia", {}).get("min_interval", 0.5))),
            "openverse": Pacer(float(config.get("openverse", {}).get("min_interval", 3.2))),
            "pixabay": Pacer(float(config.get("pixabay", {}).get("min_interval", 1.0))),
            "download": Pacer(1.0),  # upload.wikimedia.org blocks bursts (robot policy)
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
        web_cfg = self.cfg.get("web", {})
        if web_cfg.get("enabled", True) and broll.entities:
            queries = web_queries(broll)[: int(web_cfg.get("queries_per_shot", 2))]
            for query, must in queries:
                self.web_must[query] = must
            if queries:
                planned["web"] = [q for q, _ in queries]
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
            suffix = ".png" if item["analysisUrl"].lower().split("?")[0].endswith(".png") else ".jpg"
            target = self.cache_dir / "images" / item["source"] / f"{key(item['analysisUrl'])}{suffix}"
            try:
                download_file(self.session, item["analysisUrl"], target, pacer=self.pacers["download"])
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
                    mediaUrl=item["mediaUrl"],
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
            "prop": "imageinfo", "iiprop": "url|size|extmetadata|mime", "iiurlwidth": 640,
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
            thumb = info.get("thumburl") or info.get("url")
            full = info.get("url")
            if thumb and "/640px-" in thumb and int(info.get("width") or 0) > 1920:
                full = thumb.replace("/640px-", "/1920px-")  # Commons scales on demand; originals can be huge
            results.append({
                "id": f"wm:{page.get('pageid')}", "source": "wikimedia", "landing": landing, "title": title,
                "analysisUrl": thumb, "mediaUrl": full, "width": info.get("width"), "height": info.get("height"),
                "author": author, "license": licence,
                "credit": f"Fuente: {author} / Wikimedia Commons",
                "attribution": f"\"{title}\" — {author}, {licence}, Wikimedia Commons: {landing}",
            })
        return results

    def _search_web(self, query: str) -> list[dict[str, Any]]:
        """Google Images (Serper) or DuckDuckGo; only results that mention the searched name."""

        cfg = self.cfg.get("web", {})
        if self.serper_key:
            provider = "serper"
            payload = cached_json(
                self.cache_dir / "search" / "web" / f"serper-{key(query)}.json",
                lambda: self._serper(query, int(cfg.get("results", 20))),
            )
            raw = [{"title": i.get("title", ""), "image": i.get("imageUrl"), "thumbnail": i.get("thumbnailUrl"),
                    "url": i.get("link"), "width": i.get("imageWidth"), "height": i.get("imageHeight"),
                    "domain": i.get("domain") or i.get("source")} for i in payload.get("images", [])]
        else:
            provider = "ddg"
            payload = cached_json(
                self.cache_dir / "search" / "web" / f"ddg-{key(query)}.json",
                lambda: {"images": self._ddg(query, int(cfg.get("results", 20)))},
            )
            raw = payload.get("images", [])
        must = self.web_must.get(query) or tokens(query)
        min_width = int(cfg.get("min_width", 800))
        results = []
        for item in raw:
            image, thumb, page = item.get("image"), item.get("thumbnail") or item.get("image"), item.get("url") or ""
            if not image or not mentions(must, f"{item.get('title', '')} {page} {image}"):
                continue
            try:
                width, height = int(item.get("width") or 0), int(item.get("height") or 0)
            except (TypeError, ValueError):
                continue
            if width < min_width or not height or not 0.5 <= width / height <= 2.6:
                continue
            domain = site_name(item.get("domain") or page or image)
            if watermarked(f"{domain} {page} {image}", cfg.get("blocked_sites")):
                continue
            title = _short(str(item.get("title") or query), 80)
            results.append({
                "id": f"web:{key(image)[:16]}", "source": "web", "landing": page or image, "title": title,
                "analysisUrl": thumb, "mediaUrl": image, "width": width, "height": height,
                "author": domain, "license": f"editorial ({provider})",
                "credit": f"Fuente: {domain}",
                "attribution": f"\"{title}\" — {domain}: {page or image}",
            })
        return results

    def _serper(self, query: str, num: int) -> dict[str, Any]:
        self.pacers["web"].wait()
        response = self.session.post(SERPER_IMAGES_API, json={"q": query, "num": num},
                                     headers={"X-API-KEY": self.serper_key}, timeout=30)
        if response.status_code in (401, 403):
            raise SourceUnavailable(f"Serper rechazó la clave ({response.status_code})")
        response.raise_for_status()
        return response.json()

    def _ddg(self, query: str, num: int) -> list[dict[str, Any]]:
        try:
            from ddgs import DDGS
        except ImportError as error:
            raise SourceUnavailable("instala 'ddgs' o define SERPER_API_KEY para buscar fotos web") from error
        self.pacers["web"].wait()
        return [dict(i) for i in DDGS().images(query, max_results=num)]

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
                "analysisUrl": item["url"], "mediaUrl": item["url"], "width": item.get("width"), "height": item.get("height"),
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
                "analysisUrl": hit.get("webformatURL") or hit.get("largeImageURL"), "mediaUrl": hit.get("largeImageURL"),
                "width": hit.get("imageWidth"), "height": hit.get("imageHeight"),
                "author": author, "license": "Pixabay Content License",
                "credit": f"Fuente: {author} / Pixabay",
                "attribution": f"{author} — Pixabay Content License: {hit['pageURL']}",
            })
        return results
