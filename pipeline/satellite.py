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
