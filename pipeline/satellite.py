"""Satellite zoom to a place (a factory, an airport, a headquarters), as aviation/business explainers do.

Free imagery only, with its credit on screen:
- USGS National Map imagery (public domain): sharp down to buildings, for the United States;
- Sentinel-2 cloudless 2016 by EOX (CC BY 4.0): the whole world, down to airport level (~zoom 13).
Three stitched layers (wide, middle, close) of 1920x1080 centred on the place are prepared here; Remotion
(SatelliteZoom.tsx) flies continuously from the wide one to the close one and pins the labels.
Tiles are cached in cache/satellite/ and fetched politely, one at a time.
"""

from __future__ import annotations

import io
import math
import time
from pathlib import Path
from typing import Any

import requests

from .context import RunContext
from .sourcing.common import key

SOURCES = {
    "usgs": {"url": "https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/{z}/{y}/{x}",
             "max": 16, "credit": "Imagen: USGS National Map"},
    "eox": {"url": "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless_3857/default/g/{z}/{y}/{x}.jpg",
            "max": 13, "credit": "Imagen: Sentinel-2 cloudless 2016 de EOX (CC BY 4.0)"},
}
W, H = 1920, 1080
USER_AGENT = "edit-vid3/1.0 (documentary graphics; satellite)"


def in_usa(lat: float, lon: float) -> bool:
    return (24 <= lat <= 50 and -125 <= lon <= -66) or (51 <= lat <= 72 and -170 <= lon <= -129) or (18 <= lat <= 23 and -161 <= lon <= -154)


def world_px(lat: float, lon: float, z: int) -> tuple[float, float]:
    """Web Mercator pixel of a point at zoom z (256-px tiles)."""

    n = 256 * 2 ** z
    x = (lon + 180) / 360 * n
    y = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n
    return x, y


def _tile(ctx: RunContext, source: str, z: int, x: int, y: int, session: Any) -> bytes | None:
    path = ctx.cache_dir / "satellite" / source / str(z) / str(x) / f"{y}.jpg"
    if path.is_file():
        return path.read_bytes()
    url = SOURCES[source]["url"].format(z=z, x=x, y=y)
    for attempt in range(3):
        try:
            response = session.get(url, timeout=30, headers={"User-Agent": USER_AGENT})
            if response.status_code == 200 and response.content:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(response.content)
                time.sleep(0.05)
                return response.content
            if response.status_code in (404, 400):
                return None
        except requests.RequestException:
            pass
        time.sleep(1.5 * (attempt + 1))
    return None


def layer(ctx: RunContext, source: str, lat: float, lon: float, z: int, target: Path, session: Any = None) -> bool:
    """A 1920x1080 image at zoom z with the place exactly in the middle."""

    from PIL import Image

    session = session or requests.Session()
    cx, cy = world_px(lat, lon, z)
    left, top = cx - W / 2, cy - H / 2
    canvas = Image.new("RGB", (W, H), (20, 30, 40))
    got = 0
    for ty in range(int(top // 256), int((top + H) // 256) + 1):
        for tx in range(int(left // 256), int((left + W) // 256) + 1):
            if ty < 0 or ty >= 2 ** z:
                continue
            data = _tile(ctx, source, z, tx % 2 ** z, ty, session)
            if not data:
                continue
            try:
                image = Image.open(io.BytesIO(data)).convert("RGB")
            except OSError:
                continue
            canvas.paste(image, (round(tx * 256 - left), round(ty * 256 - top)))
            got += 1
    if not got:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(target, quality=88)
    return True


def prepare(ctx: RunContext, graphic: dict[str, Any]) -> dict[str, Any] | None:
    """Fill a "satellite" graphic with its layers (media in work/<slug>/graphics/satellite/) and label offsets."""

    lat, lon = float(graphic["lat"]), float(graphic["lon"])
    source = "usgs" if in_usa(lat, lon) else "eox"
    close = SOURCES[source]["max"]
    zooms = [close - 6, close - 4, close - 2, close]   # every 2 levels: never more than 4x upscaled
    name = key(f"{source}:{lat:.5f}:{lon:.5f}")[:12]
    layers = []
    used: set[str] = set()
    session = requests.Session()
    for z in zooms:
        # the wide views from Sentinel-2 everywhere (USGS has blank tiles over the border); USGS for the detail
        src = "eox" if z <= SOURCES["eox"]["max"] - 1 or source == "eox" else "usgs"
        target = ctx.work_dir / "graphics" / "satellite" / f"{name}-{src}-z{z}.jpg"
        if target.is_file() or layer(ctx, src, lat, lon, z, target, session):
            used.add(src)
            layers.append({"z": z, "media": {"src": str(target.relative_to(ctx.work_dir)).replace("\\", "/"),
                                              "kind": "image", "source": source}})
    if len(layers) < 2:
        print(f"   Satélite de {graphic.get('place')}: sin imágenes ({source})")
        return None
    cx, cy = world_px(lat, lon, close)
    labels = []
    for extra in graphic.get("labels") or []:
        x, y = world_px(float(extra["lat"]), float(extra["lon"]), close)
        dx, dy = x - cx, y - cy
        if abs(dx) < W / 2 - 80 and abs(dy) < H / 2 - 60:            # inside the close view
            labels.append({"name": extra["name"], "dx": round(dx), "dy": round(dy)})
    credit = " · ".join(SOURCES[s]["credit"] if i == 0 else SOURCES[s]["credit"].removeprefix("Imagen: ")
                        for i, s in enumerate(sorted(used, reverse=True)))
    return {**graphic, "layers": layers, "labels": labels, "credit": credit}


# --- satellite ground under the flat maps (graphics «map») ------------------------------------------------------

def lonlat(x: float, y: float, z: int) -> tuple[float, float]:
    """Inverse of world_px: (lon, lat) of a Web Mercator pixel at zoom z."""

    n = 256 * 2 ** z
    return x / n * 360 - 180, math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))


def mosaic(ctx: RunContext, west: float, south: float, east: float, north: float, target: Path, *, width: int = 2600,
           max_tiles: int = 150, session: Any = None) -> dict[str, Any] | None:
    """Sentinel-2 imagery covering the box, at the first zoom that gives it about `width` pixels across (never more
    than `max_tiles` tiles), tile-aligned: the media and the lon/lat of its edges, for MapScene to lay under the map."""

    from PIL import Image

    south, north = max(-84.0, south), min(84.0, north)
    z = 1
    for zoom in range(1, SOURCES["eox"]["max"] + 1):
        x0, y0 = world_px(north, west, zoom)
        x1, y1 = world_px(south, east, zoom)
        tiles = (int(x1 // 256) - int(x0 // 256) + 1) * (int(y1 // 256) - int(y0 // 256) + 1)
        if tiles > max_tiles:
            break
        z = zoom
        if x1 - x0 >= width:
            break
    x0, y0 = world_px(north, west, z)
    x1, y1 = world_px(south, east, z)
    tx0, ty0, tx1, ty1 = int(x0 // 256), max(0, int(y0 // 256)), int(x1 // 256), min(2 ** z - 1, int(y1 // 256))
    if not target.is_file():
        session = session or requests.Session()
        canvas = Image.new("RGB", ((tx1 - tx0 + 1) * 256, (ty1 - ty0 + 1) * 256), (12, 24, 38))
        got = 0
        for ty in range(ty0, ty1 + 1):
            for tx in range(tx0, tx1 + 1):
                data = _tile(ctx, "eox", z, tx % 2 ** z, ty, session)
                if not data:
                    continue
                try:
                    canvas.paste(Image.open(io.BytesIO(data)).convert("RGB"), ((tx - tx0) * 256, (ty - ty0) * 256))
                    got += 1
                except OSError:
                    continue
        if not got:
            return None
        target.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(target, quality=86)
    w, n = lonlat(tx0 * 256, ty0 * 256, z)
    e, s = lonlat((tx1 + 1) * 256, (ty1 + 1) * 256, z)
    return {"media": {"src": str(target.relative_to(ctx.work_dir)).replace("\\", "/"), "kind": "image", "source": "eox"},
            "west": round(w, 5), "north": round(n, 5), "east": round(e, 5), "south": round(s, 5), "zoom": z}


def country_boxes(root: Path) -> dict[str, tuple[float, float, float, float]]:
    """(west, south, east, north) of every country's largest piece, from the world-atlas TopoJSON the maps draw."""

    import json

    path = root / "node_modules" / "world-atlas" / "countries-50m.json"
    if not path.is_file():
        return {}
    topo = json.loads(path.read_text("utf-8"))
    sx, sy = topo["transform"]["scale"]
    ox, oy = topo["transform"]["translate"]
    arcs = []
    for arc in topo["arcs"]:
        x = y = 0
        pts = []
        for dx, dy in arc:
            x, y = x + dx, y + dy
            pts.append((x * sx + ox, y * sy + oy))
        arcs.append(pts)

    def ring(indexes: list[int]) -> list[tuple[float, float]]:
        return [pt for i in indexes for pt in (arcs[i] if i >= 0 else arcs[~i][::-1])]

    out = {}
    for geo in topo["objects"]["countries"]["geometries"]:
        name = (geo.get("properties") or {}).get("name")
        polygons = geo.get("arcs") or []
        if geo.get("type") == "Polygon":
            polygons = [polygons]
        rings = [ring(poly[0]) for poly in polygons if poly]
        if not name or not rings:
            continue
        def area(r):
            return abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(r, r[1:] + r[:1]))) / 2
        biggest = max(rings, key=area)
        lons, lats = [p[0] for p in biggest], [p[1] for p in biggest]
        out[name.lower()] = (min(lons), min(lats), max(lons), max(lats))
    return out


def ground(ctx: RunContext, graphic: dict[str, Any]) -> list[dict[str, Any]]:
    """The satellite layers under a flat map: the whole view, and a sharper one around the city it zooms into."""

    if graphic.get("globe") or graphic.get("style") == "pins" or not ctx.section("graphics").get("satellite_maps", True):
        return []
    lons, lats = [], []
    for p in graphic.get("points") or []:
        lons.append(float(p["lon"]))
        lats.append(float(p["lat"]))
    boxes = country_boxes(ctx.root) if graphic.get("countries") else {}
    for name in graphic.get("countries") or []:
        b = boxes.get(str(name).lower())
        if b:
            lons += [b[0], b[2]]
            lats += [b[1], b[3]]
    if not lons:
        return []
    width, height = max(lons) - min(lons), max(lats) - min(lats)
    pad = max(18.0, 0.9 * max(width, height))                          # the view's margins and the tilted overscan
    session = requests.Session()
    out = []
    box = (max(-180.0, min(lons) - pad), min(lats) - pad * 0.7, min(180.0, max(lons) + pad), max(lats) + pad * 0.7)
    if box[2] - box[0] > 100:                                           # half the world in view: all of it
        box = (-180.0, box[1], 180.0, box[3])
    name = key(f"{box}")[:12]
    wide = mosaic(ctx, *box, ctx.work_dir / "graphics" / "maps" / f"{name}-wide.jpg", session=session)
    if wide:
        out.append(wide)
    zoom = graphic.get("zoom")
    if isinstance(zoom, int) and 0 <= zoom < len(graphic.get("points") or []):
        p = graphic["points"][zoom]
        lon, lat = float(p["lon"]), float(p["lat"])
        close = mosaic(ctx, lon - 6, lat - 4, lon + 6, lat + 4, ctx.work_dir / "graphics" / "maps" / f"{name}-close.jpg",
                       width=2200, max_tiles=120, session=session)
        if close:
            out.append(close)
    return out
