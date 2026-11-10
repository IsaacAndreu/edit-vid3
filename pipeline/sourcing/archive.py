"""Historical footage in the public domain: Wikimedia Commons videos and the Internet Archive's free film collections.

For the old stretches of a story (Korbut in 1972, figure skating in 1908, Owens in 1936) YouTube has little and costs
requests, proxy and «are you a bot». These two have newsreels and old films that may be used freely, and they never
touch the YouTube budget or the home connection:

- Wikimedia Commons: every video is free (CC0, public domain, CC BY/BY-SA: credited like the photos); its 360p
  transcode is the preview, the original the final clip.
- Internet Archive: only collections or items that are plainly public domain (`ALLOWED_COLLECTIONS`: Prelinger, the
  Universal Newsreels…, or an item marked public domain). Television recordings and user uploads are left out.

Only shots that look historical ask (`historical`: an archive shot, or a year before `archive.max_year` (1980) in the
shot), a few candidates each. Each candidate's small preview is downloaded once (cache/archive/, shared by every
video) and becomes its storyboard (the thumbnails the analysis looks at) and the source of its 360p windows; the final
clip is cut from the original with ffmpeg (pipeline/ingest.py). The judge, the 5-second cap and the credits work as
for any other clip.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

import requests

from ..schemas import BrollSpec, Candidate, Shot, Storyboard
from .common import USER_AGENT, Pacer, cached_json, download_file, http_get_json, key, strip_html, tokens

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
ARCHIVE_SEARCH = "https://archive.org/advancedsearch.php"
ARCHIVE_METADATA = "https://archive.org/metadata/"
ALLOWED_COLLECTIONS = ("prelinger", "prelingerhomemovies", "universal_newsreels", "fedflix", "computerchronicles",
                       "classic_cartoons", "feature_films", "newsandpublicaffairs")
PD = re.compile(r"publicdomain|public domain|cc0|/mark/", re.I)
_RESTRICTIVE = re.compile(r"\b(nc|nd)\b", re.I)
_OK_LICENCES = ("cc0", "public domain", "pd", "cc by", "cc-by", "cc by-sa", "cc-by-sa", "attribution")
YEAR = re.compile(r"(?<!\d)(1[89]\d\d|20[0-2]\d)(?!\d)")


def historical(shot: Shot, max_year: int = 1980) -> bool:
    """An archive shot, or one whose search or story names a year before `max_year`."""

    broll = shot.broll
    if broll is None:
        return False
    if broll.preferredShot == "archive":
        return True
    text = " ".join([*broll.queries, *broll.queriesLocal, *broll.entities, str(broll.event or ""), str(shot.text or "")])
    return any(int(y) < max_year for y in YEAR.findall(text))


class ArchiveSource:
    def __init__(self, *, root: Path, cache_dir: Path, config: dict[str, Any], session: Any = None) -> None:
        self.root, self.cache_dir, self.cfg = root, cache_dir, config
        self.session = session or requests.Session()
        if not session:
            self.session.headers["User-Agent"] = USER_AGENT
        self.pacers = {"commons": Pacer(float(config.get("commons_min_interval", 1.0))),
                       "archive": Pacer(float(config.get("archive_min_interval", 1.0))),
                       "download": Pacer(1.0)}
        self.max_minutes = float(config.get("max_minutes", 30))       # longer films: too big a preview for a few seconds
        self.max_mb = float(config.get("max_preview_mb", 150))
        self.max_year = int(config.get("max_year", 1980))

    # --- per shot ---------------------------------------------------------------------

    def queries_for(self, broll: BrollSpec) -> list[str]:
        from .images import image_query

        # archive.org ANDs every word: short searches (a name, or the gist of the shot without decades and «newsreel»)
        plain = [" ".join(w for w in image_query(q, 5).split() if not re.fullmatch(r"\d{4}s?|newsreel|footage|old|film|archive", w, re.I))
                 for q in broll.queries[:2]]
        wanted = [*broll.entities[:1], *(" ".join(q.split()[:3]) for q in plain)]
        return list(dict.fromkeys(q for q in wanted if q.strip()))[: int(self.cfg.get("queries_per_shot", 2))]

    def search(self, broll: BrollSpec, notes: list[str]) -> tuple[list[str], list[Candidate]]:
        queries = self.queries_for(broll)
        must = {t for e in broll.entities for t in tokens(e)}
        found: dict[str, dict[str, Any]] = {}
        for query in queries:
            for searcher in (self._commons, self._archive):
                try:
                    for item in searcher(query):
                        text = f"{item['title']} {item.get('description', '')}"
                        if must and not (must & tokens(text)):          # a newsreel of someone else
                            continue
                        found.setdefault(item["id"], {**item, "query": query})
                except Exception as error:               # a free extra: never a reason to fail the shot
                    notes.append(f"archivo histórico {query!r}: {str(error)[:100]}")
        out: list[Candidate] = []
        for rank, item in enumerate(list(found.values())[: int(self.cfg.get("per_shot", 2))]):
            try:
                candidate = self._candidate(item, 1.0 / (rank + 2))
            except Exception as error:
                notes.append(f"archivo histórico {item['id']}: {str(error)[:100]}")
                continue
            if candidate is not None:
                out.append(candidate)
        return queries, out

    # --- searches ---------------------------------------------------------------------

    def _commons(self, query: str) -> list[dict[str, Any]]:
        params = {"action": "query", "format": "json", "generator": "search", "gsrnamespace": 6,
                  "gsrsearch": f"{query} filetype:video", "gsrlimit": 8,
                  "prop": "videoinfo", "viprop": "url|size|extmetadata|derivatives|mime"}
        payload = cached_json(self.cache_dir / "search" / "commons-video" / f"{key(params)}.json",
                              lambda: http_get_json(self.session, COMMONS_API, params=params, pacer=self.pacers["commons"]))
        out = []
        for page in sorted((payload.get("query") or {}).get("pages", {}).values(), key=lambda p: p.get("index", 0)):
            info = (page.get("videoinfo") or [{}])[0]
            meta = info.get("extmetadata") or {}
            licence = strip_html((meta.get("LicenseShortName") or {}).get("value", ""))
            if not licence or not licence.casefold().startswith(_OK_LICENCES) or _RESTRICTIVE.search(licence):
                continue
            seconds = float(info.get("duration") or 0)
            if not seconds or seconds > self.max_minutes * 60:
                continue
            small = sorted((d for d in info.get("derivatives") or [] if "360p" in str(d.get("transcodekey", ""))
                            or str(d.get("height", "")) == "360"), key=lambda d: int(d.get("height") or 0))
            preview = (small[0]["src"] if small else None) or info.get("url")
            title = page.get("title", "").removeprefix("File:").rsplit(".", 1)[0]
            if any(int(y) >= self.max_year for y in YEAR.findall(title)):      # a 2018 Olympics clip is not 1936
                continue
            author = " ".join(strip_html((meta.get("Artist") or {}).get("value", "")).split())[:40] or "Wikimedia Commons"
            landing = info.get("descriptionurl") or f"https://commons.wikimedia.org/wiki/{page.get('title', '')}"
            out.append({"id": f"wv:{page.get('pageid')}", "source": "wikimedia", "title": title, "landing": landing,
                        "description": strip_html((meta.get("ImageDescription") or {}).get("value", ""))[:300],
                        "preview": preview, "media": info.get("url"), "seconds": seconds,
                        "width": info.get("width"), "height": info.get("height"), "channel": author, "license": licence,
                        "credit": f"Fuente: {author} / Wikimedia Commons",
                        "attribution": f"\"{title}\" — {author}, {licence}, Wikimedia Commons: {landing}"})
        return out

    def _archive(self, query: str) -> list[dict[str, Any]]:
        collections = " OR ".join(f"collection:{c}" for c in ALLOWED_COLLECTIONS)
        params = {"q": f"({query}) AND mediatype:movies AND ({collections} OR licenseurl:*publicdomain*)",
                  "fl[]": ["identifier", "title", "year", "description", "licenseurl", "collection"],
                  "rows": 8, "output": "json"}
        payload = cached_json(self.cache_dir / "search" / "archive" / f"{key(params)}.json",
                              lambda: http_get_json(self.session, ARCHIVE_SEARCH, params=params, pacer=self.pacers["archive"]))
        out = []
        for doc in (payload.get("response") or {}).get("docs", []):
            groups = [c for c in doc.get("collection") or [] if not str(c).startswith("fav-")]
            curated = any(c in ALLOWED_COLLECTIONS for c in groups)
            free = curated or PD.search(str(doc.get("licenseurl") or ""))
            if not free or any(c in ("tvarchive", "television", "tvnews") for c in groups):
                continue
            years = [int(y) for y in YEAR.findall(f"{doc.get('year') or ''} {doc.get('title') or ''}")]
            # history only: a 2016 local-TV upload marked public domain is not 1936 (Jesse Owens searches)
            if (years and min(years) >= self.max_year) or (not years and not curated):
                continue
            meta = cached_json(self.cache_dir / "search" / "archive" / f"meta-{key(doc['identifier'])}.json",
                               lambda d=doc: http_get_json(self.session, ARCHIVE_METADATA + d["identifier"],
                                                           pacer=self.pacers["archive"]))
            files = [f for f in meta.get("files") or [] if str(f.get("name", "")).lower().endswith(".mp4")]
            if not files:
                continue
            by_size = sorted(files, key=lambda f: int(f.get("size") or 0))
            seconds = max((_seconds(f.get("length")) for f in files), default=0.0)
            if not seconds or seconds > self.max_minutes * 60:
                continue
            base = f"https://archive.org/download/{doc['identifier']}/"
            title = " ".join(str(doc.get("title") or doc["identifier"]).split())
            group = next((c for c in groups if c in ALLOWED_COLLECTIONS), "dominio público")
            out.append({"id": f"ar:{doc['identifier']}", "source": "archive", "title": title,
                        "landing": f"https://archive.org/details/{doc['identifier']}",
                        "description": strip_html(str(doc.get("description") or ""))[:300],
                        "preview": base + by_size[0]["name"], "media": base + by_size[-1]["name"], "seconds": seconds,
                        "width": None, "height": None, "channel": "Internet Archive", "license": "public domain",
                        "credit": "Fuente: Internet Archive",
                        "attribution": f"\"{title}\" — Internet Archive ({group}), dominio público: "
                                       f"https://archive.org/details/{doc['identifier']}"})
        return out

    # --- the candidate: preview + storyboard ------------------------------------------

    def _candidate(self, item: dict[str, Any], score: float) -> Candidate | None:
        folder = self.cache_dir / "archive" / key(item["id"])[:20]
        preview = folder / "preview.mp4"
        if not preview.is_file():
            head = self.session.head(item["preview"], allow_redirects=True, timeout=30)
            size = int(head.headers.get("Content-Length") or 0)
            if size > self.max_mb * 1e6:
                return None
            download_file(self.session, item["preview"], folder / "preview.src", pacer=self.pacers["download"])
            _to_mp4(folder / "preview.src", preview)
            (folder / "preview.src").unlink(missing_ok=True)
        board = storyboard(preview, folder, self.root, item["seconds"])
        return Candidate(
            id=item["id"], source=item["source"], kind="video", url=item["landing"], title=item["title"],
            channel=item["channel"], license=item["license"], credit=item["credit"], attribution=item["attribution"],
            durationSeconds=round(item["seconds"], 2), width=item.get("width"), height=item.get("height"),
            query=item["query"], rankScore=round(score, 4), storyboard=board, mediaUrl=item["media"],
            previewPath=str(preview.relative_to(self.root)),
        )


def _seconds(value: Any) -> float:
    """Archive.org lengths: «123.45» or «02:03» or «1:02:03»."""

    try:
        parts = [float(p) for p in str(value or "").split(":")]
    except ValueError:
        return 0.0
    total = 0.0
    for p in parts:
        total = total * 60 + p
    return total


def _to_mp4(source: Path, target: Path) -> None:
    """The preview as a small H.264 mp4 at 360p (webm transcodes, odd old encodings), the file the analysis reads."""

    tmp = target.with_suffix(".part.mp4")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(source), "-an", "-vf", "scale=-2:360", "-c:v", "libx264",
                    "-preset", "veryfast", "-crf", "28", str(tmp)], check=True, capture_output=True)
    tmp.replace(target)


def storyboard(preview: Path, folder: Path, root: Path, seconds: float) -> Storyboard:
    """YouTube-like storyboard sheets from the preview: one 160x90 thumbnail every few seconds, 10x10 per sheet."""

    interval = max(2.0, round(seconds / 300, 1))                # ≤ ~300 thumbnails
    frames = max(1, int(seconds // interval))
    meta = folder / "storyboard.json"
    if meta.is_file():
        return Storyboard.model_validate_json(meta.read_text("utf-8"))
    pattern = folder / "sb_%02d.jpg"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(preview), "-vf",
                    f"fps=1/{interval},scale=160:90:force_original_aspect_ratio=decrease,pad=160:90:(ow-iw)/2:(oh-ih)/2,tile=10x10",
                    "-q:v", "4", str(pattern)], check=True, capture_output=True)
    sheets = sorted(folder.glob("sb_*.jpg"))
    if not sheets:
        raise RuntimeError("sin fotogramas")
    board = Storyboard(sheets=[str(p.relative_to(root)) for p in sheets], columns=10, rows=10, tileWidth=160,
                       tileHeight=90, interval=interval, frames=min(frames, len(sheets) * 100))
    meta.write_text(board.model_dump_json(), encoding="utf-8")
    return board


def cut(source: str | Path, start: float, end: float, target: Path, height: int | None = None) -> Path:
    """[start, end] of a file or URL, re-encoded so it starts exactly there (the name keeps the source seconds, as
    YouTube windows do: «a360_<start>_<end>.mp4»)."""

    if target.is_file() and target.stat().st_size > 0:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".part.mp4")
    scale = ["-vf", f"scale=-2:{height}"] if height else []
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", str(source), "-an",
                    *scale, "-c:v", "libx264", "-preset", "veryfast", "-crf", "16" if not height else "26", str(tmp)],
                   check=True, capture_output=True, timeout=600)
    tmp.replace(target)
    return target

