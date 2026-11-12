"""Revisión final de los planos, antes del render (dentro de la etapa qa): una mirada de conjunto a lo que de verdad va
a salir — un fotograma de cada plano con la frase que dice la voz y las fotos de las personas — que señala los planos
que no encajan: otra persona, otro suceso, otro tema, texto o calidad que estorban. No cambia nada: los deja en
out/<vídeo>/qa/revision.md, en el informe de planos y como aviso, para corregirlos en el editor antes de subir.

qa.review (true) · qa.review_batch (9 planos por hoja) · el modelo del juez (judge.model, con visión).
"""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .context import RunContext

STAGE = "qa"

REVIEW_INSTRUCTIONS = """
You are the final reviewer of a YouTube documentary before it is published. You get a sheet of numbered tiles: each
tile is one frame of a shot exactly as it will appear, and for each number the narration said over it. Reference
photos of the people the video names may follow. Flag ONLY clear problems a viewer would notice:
- "persona": the narration is about a named person and the tile clearly shows somebody else (compare with the
  reference photo when there is one; a crowd, a small or turned figure is NOT a problem);
- "suceso": the tile clearly shows a different specific event, place, team, aircraft or company than the one narrated;
- "tema": the tile has nothing to do with what is being said (unrelated stock footage, a different sport);
- "texto": big burned-in text, subtitles, a watermark or a channel logo over the picture;
- "calidad": black, frozen, very blurry or badly cropped.
Generic but fitting b-roll is FINE. When in doubt, do not flag. Return only JSON.
""".strip()

REVIEW_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["problems"],
    "properties": {"problems": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["n", "kind", "reason"],
        "properties": {"n": {"type": "integer"}, "kind": {"type": "string", "enum": ["persona", "suceso", "tema", "texto", "calidad"]},
                       "reason": {"type": "string"}}}}},
}

TILE = (384, 216)


def sheet(frames: list[np.ndarray]) -> np.ndarray:
    """3 columns of numbered tiles."""

    columns = 3
    rows = (len(frames) + columns - 1) // columns
    w, h = TILE
    out = np.full((rows * (h + 6) + 6, columns * (w + 6) + 6, 3), 24, np.uint8)
    for i, frame in enumerate(frames):
        y, x = 6 + (i // columns) * (h + 6), 6 + (i % columns) * (w + 6)
        out[y:y + h, x:x + w] = cv2.resize(frame, TILE, interpolation=cv2.INTER_AREA)
        cv2.rectangle(out, (x, y), (x + 46, y + 34), (0, 0, 0), -1)
        cv2.putText(out, str(i + 1), (x + 8, y + 26), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)
    return out


def _jpeg(image: np.ndarray, quality: int = 82) -> bytes:
    ok, data = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return data.tobytes() if ok else b""


def portraits(ctx: RunContext) -> list[tuple[str, bytes]]:
    """The verified photos of the people the video names (people.consensus), as the judge gets them."""

    if not (ctx.work_dir / "people.json").is_file():
        return []
    from .judge import portrait_bytes

    out = []
    for person in ctx.read_json("people.json").get("people") or []:
        image = ctx.work_dir / str(person.get("image") or "")
        if person.get("verified") is True and image.is_file():
            data = portrait_bytes(image, 240)
            if data:
                out.append((str(person["name"]), data))
    return out[:4]


def ask(ctx: RunContext, prompt: str, images: list[tuple[str, bytes]]) -> dict[str, Any]:
    cfg = ctx.section("judge")
    model = str(ctx.section("qa").get("review_model") or cfg.get("model", "gpt-5-mini"))
    digest = hashlib.sha256(json.dumps([model, REVIEW_INSTRUCTIONS, prompt]).encode() + b"".join(d for _, d in images)).hexdigest()[:32]
    path = ctx.cache_dir / "revision" / f"{digest}.json"
    if path.is_file():
        return json.loads(path.read_text("utf-8"))
    from openai import OpenAI

    from .costs import record_cost

    content: list[dict[str, Any]] = [{"type": "input_text", "text": prompt}]
    for label, data in images:
        content.append({"type": "input_text", "text": label})
        content.append({"type": "input_image", "image_url": "data:image/jpeg;base64," + base64.b64encode(data).decode(),
                        "detail": "high" if label.startswith("Sheet") else "low"})
    response = OpenAI(api_key=ctx.env("OPENAI_API_KEY")).responses.create(
        model=model, instructions=REVIEW_INSTRUCTIONS, reasoning={"effort": str(cfg.get("reasoning_effort", "low"))},
        input=[{"role": "user", "content": content}],
        text={"format": {"type": "json_schema", "name": "review", "strict": True, "schema": REVIEW_SCHEMA}},
    )
    prices = cfg.get("usd_per_mtok", {})
    usage = response.usage
    usd = (usage.input_tokens * float(prices.get("input", 0.25)) + usage.output_tokens * float(prices.get("output", 2.0))) / 1e6
    record_cost(ctx, stage=STAGE, provider="openai", operation=f"{model} revisión", usd=usd,
                details={"inputTokens": usage.input_tokens, "outputTokens": usage.output_tokens})
    result = json.loads(response.output_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return result


def review(ctx: RunContext, rows: list[dict[str, Any]], topic: str = "", log=print) -> list[dict[str, Any]]:
    """Problems found, one per flagged shot: {"shotId", "start", "kind", "reason"}. The rows get "review"."""

    cfg = ctx.section("qa")
    if not cfg.get("review", True) or not ctx.env("OPENAI_API_KEY", required=False):
        return []
    shots = [r for r in rows if r.get("_frame") is not None and r.get("media") and not r.get("coldOpen")
             and r.get("decidedBy") != "people" and r.get("source") != "generated"]
    batch = max(3, int(cfg.get("review_batch", 9)))
    people = portraits(ctx)
    problems: list[dict[str, Any]] = []
    errors = 0
    for i in range(0, len(shots), batch):
        group = shots[i:i + batch]
        lines = "\n".join(f"{n + 1}. «{r['text'][:220]}»" for n, r in enumerate(group))
        prompt = (f"Video topic: {topic}\n" if topic else "") + f"Narration (in the video's language) over each tile:\n{lines}"
        images = [("Sheet of tiles:", _jpeg(sheet([r["_frame"] for r in group])))]
        images += [(f"Reference photo: {name}", data) for name, data in people]
        try:
            found = ask(ctx, prompt, images)
        except Exception as error:     # a review: never costs the video
            errors += 1
            if errors == 1:
                log(f"   Revisión final no disponible: {str(error)[:120]}")
            if errors >= 2:
                break
            continue
        for item in found.get("problems") or []:
            n = int(item.get("n", 0)) - 1
            if 0 <= n < len(group):
                row = group[n]
                row["review"] = {"kind": item.get("kind"), "reason": str(item.get("reason", ""))[:240]}
                problems.append({"shotId": row["shotId"], "start": row["start"], **row["review"]})
    return problems


def write(ctx: RunContext, problems: list[dict[str, Any]], checked: int) -> Path:
    from .qa import mmss

    path = ctx.out_dir / "qa" / "revision.md"
    lines = [f"# Revisión final · {ctx.slug}", "", f"{checked} planos mirados · {len(problems)} a revisar", ""]
    names = {"persona": "Otra persona", "suceso": "Otro suceso", "tema": "Fuera de tema", "texto": "Texto encima",
             "calidad": "Calidad"}
    for p in problems:
        lines.append(f"- **{mmss(p['start'])}** ({p['shotId']}) · {names.get(p['kind'], p['kind'])}: {p['reason']}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
