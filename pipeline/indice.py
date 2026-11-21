"""The scene index of the material de partida (bloque 4, second part): each video or clip you gave is cut into
scenes once, and each scene gets one line describing what is seen, so a sentence finds ITS scene by meaning — not
whatever CLIP likes best in a 20-minute gameplay video.

How a source is indexed (once: cache/material/indice/<source>.json, shared by every video of every channel):
1. its storyboard thumbnails (YouTube's own, or the ones made from your clip's preview: no proxy, no download) are
   embedded with CLIP and cut where the picture changes (cosine below `indice.scene_cut`, 0.82) or every
   `indice.max_scene_seconds` (20);
2. one sheet with the middle thumbnail of every scene (up to `indice.per_sheet`, 30, per call) goes to a cheap vision
   model (`indice.model`, judge.model by default) that writes one line per scene, in English and in Spanish keywords
   («red sports car racing along a beach at night» · «coche, playa, noche»);
3. the tags you wrote for your clip («Vice Beach de noche») are kept with every scene of it.

How a shot uses it (analysis, `analysis.index_windows`, on whenever there is material): for every material source
among its candidates, the scene whose words best match the shot (its sentence, what it is meant to show, its
searches, its idea) becomes one more window to look at, marked `hint: indice`; the judge sees those first.
"""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np

SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["scenes"],
    "properties": {"scenes": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["n", "en", "es"],
        "properties": {"n": {"type": "integer"}, "en": {"type": "string"}, "es": {"type": "string"}}}}},
}
INSTRUCTIONS = """Each numbered tile is one scene of a video (a documentary source, a news report or video-game footage).
For every number write what is SEEN, concretely, as a video editor would log it: who or what, doing what, where, day or
night, close or wide — «red sports car speeding along a beach road at night, wide shot», «gymnast on the balance beam,
arena, close». In "en" one short line in English (max 15 words); in "es" 3-6 Spanish keywords («coche, playa, noche,
persecución»). If a tile is a title card, a logo, a menu or a talking head, say so plainly."""


def segment(times: list[float], vectors: np.ndarray, cut: float = 0.82, longest: float = 20.0,
            step: float = 5.0) -> list[tuple[float, float, int]]:
    """Scenes over a source's thumbnails: (start, end, index of the middle thumbnail). A new scene where consecutive
    thumbnails stop looking alike (cosine < `cut`) or the scene reaches `longest` seconds."""

    if not times:
        return []
    scenes: list[tuple[float, float, int]] = []
    first = 0
    for i in range(1, len(times) + 1):
        ends = i == len(times)
        if not ends:
            similar = float(vectors[i] @ vectors[i - 1]) >= cut
            if similar and times[i] - times[first] < longest:
                continue
        end = times[i] if not ends else times[i - 1] + step
        scenes.append((round(times[first], 2), round(end, 2), (first + i - 1) // 2))
        first = i
    return scenes


def _sheet(tiles: list[np.ndarray], columns: int = 6, size: tuple[int, int] = (240, 135)) -> np.ndarray:
    w, h = size
    rows = (len(tiles) + columns - 1) // columns
    canvas = np.zeros((rows * (h + 4), columns * (w + 4), 3), np.uint8)
    for n, tile in enumerate(tiles):
        y, x = (n // columns) * (h + 4), (n % columns) * (w + 4)
        canvas[y:y + h, x:x + w] = cv2.resize(tile, size, interpolation=cv2.INTER_AREA)
        cv2.rectangle(canvas, (x, y), (x + 40, y + 28), (0, 0, 0), -1)
        cv2.putText(canvas, str(n + 1), (x + 4, y + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 255, 255), 2)
    return canvas


def describe(ctx: Any, tiles: list[np.ndarray]) -> list[dict[str, str]]:
    """One line per tile from the vision model (cached by the sheet's bytes)."""

    from .costs import record_cost
    from .sourcing.common import cached_json

    cfg = dict(ctx.section("indice") or {})
    model = str(cfg.get("model") or ctx.section("judge").get("model", "gpt-5-mini"))
    ok, encoded = cv2.imencode(".jpg", _sheet(tiles), [cv2.IMWRITE_JPEG_QUALITY, 82])
    if not ok:
        return []
    image = encoded.tobytes()
    key = hashlib.sha256(json.dumps([model, INSTRUCTIONS, len(tiles)]).encode() + image).hexdigest()[:32]

    def produce() -> dict[str, Any]:
        from openai import OpenAI

        client = OpenAI(api_key=ctx.env("OPENAI_API_KEY"), timeout=180, max_retries=2)
        response = client.responses.create(
            model=model, instructions=INSTRUCTIONS, reasoning={"effort": "low"},
            input=[{"role": "user", "content": [
                {"type": "input_text", "text": f"{len(tiles)} scenes, numbered 1-{len(tiles)}."},
                {"type": "input_image", "image_url": "data:image/jpeg;base64," + base64.b64encode(image).decode(),
                 "detail": "high"}]}],
            text={"format": {"type": "json_schema", "name": "scene_log", "strict": True, "schema": SCHEMA}})
        prices = cfg.get("usd_per_mtok") or ctx.section("judge").get("usd_per_mtok", {})
        usage = response.usage
        usd = (usage.input_tokens * float(prices.get("input", 0.25)) + usage.output_tokens * float(prices.get("output", 2.0))) / 1e6
        record_cost(ctx, stage="analysis", provider="openai", operation=model, usd=usd, details={"indice": len(tiles)})
        return json.loads(response.output_text)

    answer = cached_json(ctx.cache_dir / "material" / "descripciones" / f"{key}.json", produce)
    by_n = {int(s.get("n") or 0): s for s in answer.get("scenes") or []}
    return [{"en": str((by_n.get(i + 1) or {}).get("en") or ""), "es": str((by_n.get(i + 1) or {}).get("es") or "")}
            for i in range(len(tiles))]


def index_path(ctx: Any, candidate_id: str) -> Path:
    return ctx.cache_dir / "material" / "indice" / f"{hashlib.sha1(candidate_id.encode()).hexdigest()[:20]}.json"


def scenes_for(ctx: Any, candidate: Any, clip: Any, cfg: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """The source's scenes [{start, end, en, es, tags}], made once and kept (cache/material/indice/)."""

    from .analysis import storyboard_frames

    path = index_path(ctx, candidate.id)
    try:
        return json.loads(path.read_text("utf-8"))["scenes"]
    except (OSError, ValueError, KeyError):
        pass
    own = dict(ctx.section("indice") or {})
    times, tiles = storyboard_frames(candidate, ctx.root, {**(cfg or {}), "edge_margin": 0.0,
                                                           "max_frames_cap": int(own.get("max_thumbnails", 240)),
                                                           "frames_every_seconds": 2.0})
    if not tiles:
        return []
    vectors = clip.embed_images(tiles)
    step = float(getattr(candidate.storyboard, "interval", 5.0) or 5.0)
    cuts = segment(times, vectors, float(own.get("scene_cut", 0.82)), float(own.get("max_scene_seconds", 20)), step)
    per_sheet = int(own.get("per_sheet", 30))
    lines: list[dict[str, str]] = []
    middles = [tiles[m] for _, _, m in cuts]
    for start in range(0, len(middles), per_sheet):
        try:
            lines += describe(ctx, middles[start:start + per_sheet])
        except Exception as error:                     # no description: the scene still has its tags and CLIP
            print(f"   índice de {candidate.id}: sin descripción ({str(error)[:100]})")
            lines += [{"en": "", "es": ""}] * len(middles[start:start + per_sheet])
    tags = candidate.title if candidate.source == "propio" else ""
    scenes = [{"start": a, "end": b, "en": line["en"], "es": line["es"], "tags": tags}
              for (a, b, _), line in zip(cuts, lines)]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"candidate": candidate.id, "title": candidate.title, "scenes": scenes},
                               ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"   índice de {candidate.id}: {len(scenes)} escenas descritas")
    return scenes


def shot_words(shot: Any) -> set[str]:
    from .material import _shot_words

    return _shot_words(shot)


def best_scene(scenes: list[dict[str, Any]], words: set[str], minimum: int = 2) -> dict[str, Any] | None:
    """The scene whose description, keywords and tags share most words with the shot (at least `minimum`)."""

    from .sourcing.common import tokens

    best, score = None, minimum - 1
    for scene in scenes:
        shared = len(words & tokens(" ".join([scene.get("en", ""), scene.get("es", ""), scene.get("tags", "")])))
        if shared > score:
            best, score = scene, shared
    return best
