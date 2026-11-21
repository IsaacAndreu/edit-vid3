"""Reference links for a new video («Nuevo vídeo» → «Enlaces de referencia»): what the script is written FROM.

The other kind of link, the library one, is the material de partida (pipeline/material.py): the clips the video is
cut from. A reference is only read: a YouTube video by its subtitles (one request per video, cached in
cache/videos/<id>/, like the opening clip's), a web page by its text. What comes back is plain text, capped per link,
for the script writer (organizar.draft_script) and the fixer of sentences without an image (imagen_guion.fix).
"""

from __future__ import annotations

import hashlib
import html
import re
from pathlib import Path
from typing import Any, Callable

MAX_LINKS = 6                   # each YouTube one is a request: a handful, never a list
PER_LINK_CHARS = 6000
USER_AGENT = "Mozilla/5.0 (compatible; edit-vid3 referencias)"


def split_links(text: Any) -> tuple[list[str], list[str]]:
    """(YouTube ids, other http(s) links), in order, once each, at most MAX_LINKS in all."""

    from .material import video_ids

    items = text if isinstance(text, list) else re.split(r"[\s,]+", str(text or ""))
    videos: list[str] = []
    pages: list[str] = []
    for item in (str(i).strip() for i in items):
        if not item:
            continue
        found = video_ids([item])
        if found and "youtu" in item or (found and "/" not in item):
            if found[0] not in videos:
                videos.append(found[0])
        elif re.match(r"https?://", item) and item not in pages:
            pages.append(item)
    keep = MAX_LINKS
    videos = videos[:keep]
    return videos, pages[: max(0, keep - len(videos))]


def page_text(raw: str) -> str:
    """The readable text of an HTML page: no scripts, styles, menus or tags."""

    raw = re.sub(r"(?is)<(script|style|noscript|nav|footer|header|aside|svg)\b.*?</\1>", " ", raw)
    raw = re.sub(r"(?i)<br\s*/?>|</p>|</h\d>|</li>", "\n", raw)
    text = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(line for line in lines if len(line.split()) >= 6)      # sentences, not menu entries


def _cached(root: Path, key: str, make: Callable[[], str]) -> str:
    path = root / "cache" / "referencias" / f"{hashlib.sha256(key.encode()).hexdigest()[:24]}.txt"
    if path.is_file():
        return path.read_text("utf-8")
    text = make()
    if text:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return text


def read(ctx: Any, links: Any, youtube: Any = None, get: Callable[[str], str] | None = None) -> str:
    """The references as one text block («» when there are none or none could be read)."""

    videos, pages = split_links(links)
    if not videos and not pages:
        return ""
    parts: list[str] = []
    language = str(ctx.section("align").get("language", "es"))[:2]
    opened = None
    for video_id in videos:
        def subtitles(video_id: str = video_id) -> str:
            nonlocal opened
            from .quotes import parse_vtt

            if youtube is None and opened is None:
                from .sourcing import youtube_source

                opened = youtube_source(ctx)
            source = youtube or opened
            for lang in dict.fromkeys([language, "es", "en"]):
                try:
                    path = source.subtitle_file(video_id, lang)
                except Exception as error:
                    print(f"   referencia yt:{video_id}: {str(error)[:100]}")
                    return ""
                if path is not None:
                    words = " ".join(text for _, _, text in parse_vtt(path.read_text("utf-8", errors="replace")))
                    return " ".join(words.split())[:PER_LINK_CHARS]
            return ""

        text = _cached(ctx.root, f"yt:{video_id}:{language}", subtitles)
        parts.append(f"[Vídeo youtu.be/{video_id}] " + (text or "(sin subtítulos: no se pudo leer)"))
    for url in pages:
        def fetch(url: str = url) -> str:
            if get is not None:
                raw = get(url)
            else:
                import requests

                try:
                    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
                    response.raise_for_status()
                    raw = response.text
                except Exception as error:
                    print(f"   referencia {url[:80]}: {str(error)[:100]}")
                    return ""
            return page_text(raw)[:PER_LINK_CHARS]

        text = _cached(ctx.root, f"web:{url}", fetch)
        parts.append(f"[Página {url}] " + (text or "(no se pudo leer)"))
    if opened is not None:
        try:
            opened.close()
        except Exception:
            pass
    return "\n\n".join(parts)
