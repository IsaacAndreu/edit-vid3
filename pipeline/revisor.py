"""The automatic reviewer, report mode: which shots of a finished video are objectively wrong, with the proof.

    python -m pipeline.revisor <vídeo> [<vídeo>…] [--modelo M] [--max-usd 1.0]

It changes nothing: it writes out/<slug>/revisor/ (informe.md, revisor.json and hoja-N.jpg, the flagged shots with
their frame and their sentence) so that one look says whether the reviewer has judgement. Only objective faults, the
ones anybody would agree on — never taste:

- `no_tiene_que_ver`: the footage has nothing to do with what the sentence says (Paris said, a football match shown);
- `persona_equivocada`: the sentence (or the video) is about someone and clearly someone else is shown;
- `dibujo_animado`: a cartoon or a video game where real footage was meant;
- `roto`: black, frozen, broken or unreadable frames (measured, no model);
- `texto_marca_agua`: a watermark or big foreign text covering the picture;
- `repetido`: the same clip, or nearly the same frames, shown again (measured, no model).

The model sees, for every shot, two frames of the very seconds the video uses, the sentence said over it, the
sentences around it and what the shot was meant to show; with a reference photo of the protagonist when there is
one. A shot is flagged only with a one-line proof («la frase dice X; en la imagen sale Y») and a confidence.
The reasons are the studio's «Errores» reasons (pipeline/feedback.py), so both can be compared.

Config (`revisor:` in config.yaml, all optional): model (judge.model by default), usd_per_mtok (judge's by
default), max_usd (1.0 per video), shots_per_sheet (8), detail (high).
"""

from __future__ import annotations

import base64
import hashlib
import json
import subprocess
import sys
import textwrap
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .context import PROJECT_ROOT, RunContext

STAGE = "revisor"
OUT_DIR = "revisor"
PROBLEMS = {
    "no_tiene_que_ver": "No tiene que ver con la frase",
    "persona_equivocada": "Sale otra persona",
    "dibujo_animado": "Dibujo animado / videojuego",
    "roto": "Roto, negro o muy mala calidad",
    "texto_marca_agua": "Texto encima o marca de agua",
    "repetido": "Repetido",
    "hueco_tapado": "Hueco tapado con el clip de otro plano",
}
# who chose a shot, from least to most deliberate: in a repeated pair the reviewer blames the least deliberate one
# (newgym3: the judge's right choices at 9:27-10:39 were blamed for the borrowed copies of the first minutes)
AUTHORITY = {"": 0, "protagonist-filler": 1, "neighbour": 2, "protagonist": 2, "event-footage": 2, "protagonist-photo": 2,
             "library-photo": 2, "web-photo": 2, "editor": 9, "coldopen": 8}
MODEL_PROBLEMS = ("no_tiene_que_ver", "persona_equivocada", "dibujo_animado", "texto_marca_agua", "roto")
TILE = (384, 216)                     # each frame on the sheet; two per shot, side by side

INSTRUCTIONS = """You review the finished cut of a documentary-style YouTube video narrated in Spanish. Each numbered
tile shows TWO frames of one shot, taken from the exact seconds the video uses, and below the sheet you get, for each
number, the sentence narrated over that shot, the narration around it and what the shot was meant to show.

Flag ONLY objective faults, the kind any viewer would agree on. Never judge taste, beauty, pacing or whether a better
clip could exist. A loosely related, generic or symbolic shot is OK: documentaries use illustrative footage (a crowd
for «la gente», a stadium for «la competición», a city for a place, archive footage for the past). Problems:

- unrelated: the footage clearly has nothing to do with what is said (another sport, another country, another era,
  another kind of thing entirely). A generic or symbolic image that fits the idea is NOT unrelated.
- wrong_person: a specific person is meant (named in the sentence or the protagonist of the passage) and the person
  clearly shown is someone else (different sex, clearly different face from the reference photo, another sport's
  athlete). If you cannot tell who it is (small, from behind, blurred), it is OK.
- cartoon_game: a cartoon, animation or video-game footage where real footage was meant.
- watermark: a large watermark, logo or foreign text overlay that covers the picture (small channel logos in a
  corner and the video's own subtitles at the bottom are OK).
- broken: black, blank, frozen-looking, corrupted or unreadable frames.

Ambient shots are OK. Many sentences have no image of their own: a decision, a feeling, school, family or money
facts, an age, a height, a list of titles, a chapter title read aloud, the goodbye («suscríbete»). The edit then shows
the person the video is about (from the VIDEO SUBJECT line), at work or in their usual setting: that is OK, never
unrelated — unless the footage clearly contradicts the sentence (another event that the sentence places elsewhere,
a wedding over a sentence about a competition).

Be strict with yourself: when in doubt, answer ok. For every flagged shot write the evidence in ONE short sentence in
Spanish with this shape: «la frase dice …; en la imagen sale …». confidence: 0.0-1.0, how sure you are that a viewer
would agree it is wrong."""

SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["shots"],
    "properties": {"shots": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["n", "verdict", "problem", "evidence", "confidence"],
        "properties": {
            "n": {"type": "integer"},
            "verdict": {"type": "string", "enum": ["ok", "wrong"]},
            "problem": {"type": "string", "enum": ["none", "unrelated", "wrong_person", "cartoon_game", "watermark",
                                                   "broken"]},
            "evidence": {"type": "string"},
            "confidence": {"type": "number"},
        }}}},
}
MODEL_TO_REASON = {"unrelated": "no_tiene_que_ver", "wrong_person": "persona_equivocada",
                   "cartoon_game": "dibujo_animado", "watermark": "texto_marca_agua", "broken": "roto"}


# --- what is on screen ---------------------------------------------------------------------------------------

def _read(path: Path) -> Any:
    try:
        return json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return None


def _grab(path: Path, at: float | None) -> np.ndarray | None:
    """One frame of a file at `at` seconds (None: its last frame)."""

    where = ["-sseof", "-0.1"] if at is None else ["-ss", f"{max(0.0, at):.3f}"]
    try:
        done = subprocess.run(["ffmpeg", "-v", "error", *where, "-i", str(path), "-frames:v", "1", "-f", "image2pipe",
                               "-vcodec", "mjpeg", "-"], capture_output=True, timeout=60)
    except subprocess.TimeoutExpired:
        return None
    return cv2.imdecode(np.frombuffer(done.stdout, np.uint8), cv2.IMREAD_COLOR) if done.stdout else None


def frames_of(work: Path, shot: dict[str, Any], fps: float, final: Path | None = None) -> list[np.ndarray]:
    """Two frames (at 30 % and 70 % of the shot) from the shot's own media, at the seconds the video plays; when that
    file cannot be read (gone after the render, an odd encoding), from the finished video at the shot's time."""

    media = shot.get("media") or {}
    src = work / str(media.get("src") or "")
    shares = (0.3, 0.7)
    out: list[np.ndarray] = []
    if src.is_file() and media.get("kind") == "image":
        image = cv2.imread(str(src))
        out = [image, image] if image is not None else []
    elif src.is_file():
        rate = float(media.get("rate") or 1.0)
        for share in shares:
            at = (int(shot.get("offset") or 0) + share * int(shot.get("durationInFrames") or 1)) / fps * rate
            image = _grab(src, at)
            if image is None:                     # past the end of a short clip: its last frame
                image = _grab(src, None)
            if image is not None:
                out.append(image)
    if not out and final is not None and final.is_file():
        for share in shares:
            image = _grab(final, (int(shot.get("from") or 0) + share * int(shot.get("durationInFrames") or 1)) / fps)
            if image is not None:
                out.append(image)
    return out


def dhash(image: np.ndarray, size: int = 8) -> int:
    grey = cv2.resize(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), (size + 1, size), interpolation=cv2.INTER_AREA)
    bits = (grey[:, 1:] > grey[:, :-1]).flatten()
    return int("".join("1" if b else "0" for b in bits), 2)


def broken(images: list[np.ndarray]) -> str | None:
    """Black or flat frames (no model needed)."""

    if not images:
        return "no se pudo leer ningún fotograma del plano"
    for image in images:
        grey = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        if grey.mean() < 12:
            return f"fotograma casi negro (brillo medio {grey.mean():.0f} de 255)"
        if grey.std() < 5:
            return f"fotograma plano, sin imagen (contraste {grey.std():.1f})"
    return None


def repeats(items: list[dict[str, Any]], max_hamming: int = 6, already: set[str] | None = None) -> dict[str, str]:
    """shot id → proof, one per repeated PAIR: the same stretch of the same source video, or nearly identical frames.
    The shot blamed is the least deliberate of the two (AUTHORITY: a borrowed copy before the filler, the filler
    before the judge's choice), the later one on a tie. Pieces of one shot (s012, s012-2) are one shot. A pair whose
    weaker side is already flagged (`already`, the borrowed shots) adds nothing: the original is never blamed for it."""

    already = set(already or ())
    out: dict[str, str] = {}
    seen: list[dict[str, Any]] = []
    rank = lambda item: AUTHORITY.get(str(item.get("method") or ""), 3)       # noqa: E731
    for item in items:
        base = item["id"].split("-")[0]
        for earlier in seen:
            if earlier["id"].split("-")[0] == base or earlier["id"] in out:
                continue
            same_source = (item.get("candidateId") and item.get("candidateId") == earlier.get("candidateId")
                           and None not in (item.get("start"), item.get("end"), earlier.get("start"), earlier.get("end"))
                           and min(item["end"], earlier["end"]) - max(item["start"], earlier["start"]) > 0.5)
            close = [bin(a ^ b).count("1") for a in item.get("hashes", []) for b in earlier.get("hashes", [])]
            if same_source or (close and min(close) <= max_hamming):
                why = "el mismo tramo del mismo vídeo de origen" if same_source else "fotogramas casi idénticos"
                blamed, kept = (earlier, item) if rank(earlier) < rank(item) else (item, earlier)
                if blamed["id"] not in already:
                    out[blamed["id"]] = f"repite el plano {kept['id']} (a los {_clock(kept['at'])}): {why}"
                break
        seen.append(item)
    return out


def _clock(seconds: float) -> str:
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}"


# --- the model -----------------------------------------------------------------------------------------------

def sheet(entries: list[dict[str, Any]], columns: int = 2) -> np.ndarray:
    width, height = TILE
    rows = (len(entries) + columns - 1) // columns
    canvas = np.zeros((rows * (height + 6), columns * (2 * width + 12), 3), np.uint8)
    for i, entry in enumerate(entries):
        y, x = (i // columns) * (height + 6), (i % columns) * (2 * width + 12)
        for k, image in enumerate((entry["images"] * 2)[:2]):
            canvas[y:y + height, x + k * width:x + (k + 1) * width] = cv2.resize(image, TILE, interpolation=cv2.INTER_AREA)
        cv2.rectangle(canvas, (x, y), (x + 54, y + 40), (0, 0, 0), -1)
        cv2.putText(canvas, str(entry["n"]), (x + 6, y + 31), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 255, 255), 2)
    return canvas


def brief(entries: list[dict[str, Any]], subject: str) -> str:
    lines = [f"VIDEO SUBJECT / PROTAGONIST: {subject}" if subject else "VIDEO SUBJECT: (see the narration)"]
    for e in entries:
        lines.append(f"\n#{e['n']}")
        lines.append(f"Sentence (Spanish): {e['text']}")
        if e.get("around") and e["around"].strip() != e["text"].strip():
            lines.append(f"Around it: {e['around']}")
        if e.get("intent"):
            lines.append(f"Meant to show: {e['intent']}")
        if e.get("kind") == "literal":
            lines.append("LITERAL: this very thing must be seen")
        elif e.get("kind") == "ambiente":
            lines.append("AMBIENT: no image of its own; footage of who it is about is fine")
        if e.get("entities"):
            lines.append(f"Named: {', '.join(e['entities'])}")
    return "\n".join(lines)


def ask(ctx: RunContext, cfg: dict[str, Any], entries: list[dict[str, Any]], subject: str,
        portrait: tuple[str, bytes] | None) -> tuple[list[dict[str, Any]], float]:
    """One sheet to the vision model: its verdicts and what it cost (0 when it came from the cache)."""

    from .sourcing.common import cached_json

    model = str(cfg.get("model") or ctx.section("judge").get("model", "gpt-5-mini"))
    ok, encoded = cv2.imencode(".jpg", sheet(entries), [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        raise RuntimeError("no se pudo codificar la hoja")
    image = encoded.tobytes()
    prompt = brief(entries, subject)
    detail = str(cfg.get("detail", "high"))
    key = hashlib.sha256(json.dumps([model, INSTRUCTIONS, prompt, detail]).encode() + image
                         + (portrait[1] if portrait else b"")).hexdigest()[:32]
    spent = [0.0]

    def produce() -> dict[str, Any]:
        from openai import OpenAI

        from .costs import record_cost

        content: list[dict[str, Any]] = [
            {"type": "input_text", "text": prompt},
            {"type": "input_image", "image_url": "data:image/jpeg;base64," + base64.b64encode(image).decode(),
             "detail": detail}]
        if portrait:
            content += [{"type": "input_text", "text": f"Reference photo of {portrait[0]}"},
                        {"type": "input_image", "image_url": "data:image/jpeg;base64," + base64.b64encode(portrait[1]).decode(),
                         "detail": "low"}]
        client = OpenAI(api_key=ctx.env("OPENAI_API_KEY"), timeout=240, max_retries=2)
        response = client.responses.create(
            model=model, instructions=INSTRUCTIONS, prompt_cache_key="revisor",
            reasoning={"effort": str(cfg.get("reasoning_effort", "medium"))},
            input=[{"role": "user", "content": content}],
            text={"format": {"type": "json_schema", "name": "review", "strict": True, "schema": SCHEMA}})
        prices = cfg.get("usd_per_mtok") or ctx.section("judge").get("usd_per_mtok", {})
        usage = response.usage
        cached = int(getattr(getattr(usage, "input_tokens_details", None), "cached_tokens", 0) or 0)
        usd = ((usage.input_tokens - cached) * float(prices.get("input", 0.25))
               + cached * float(prices.get("input_cache_hit", float(prices.get("input", 0.25)) / 10))
               + usage.output_tokens * float(prices.get("output", 2.0))) / 1e6
        spent[0] = usd
        record_cost(ctx, stage=STAGE, provider="openai", operation=model, usd=usd,
                    details={"shots": [e["id"] for e in entries]})
        return json.loads(response.output_text)

    answer = cached_json(ctx.cache_dir / "revisor" / f"{key}.json", produce)
    return list(answer.get("shots") or []), spent[0]


# --- the review ----------------------------------------------------------------------------------------------

def review(root: Path, slug: str, model: str | None = None, max_usd: float | None = None,
           ask_model: Any = None) -> dict[str, Any]:
    from . import feedback
    from .judge import portrait_bytes, surrounding
    from .schemas import Shot

    ctx = RunContext.create(slug, root=root)
    cfg = dict(ctx.section("revisor") or {})
    if model:
        cfg["model"] = model
    budget = float(max_usd if max_usd is not None else cfg.get("max_usd", 1.0))
    work = ctx.work_dir
    timeline = _read(work / "timeline.json")
    if not timeline:
        raise FileNotFoundError(f"work/{slug}/timeline.json: el vídeo aún no está montado")
    fps = float(timeline.get("fps") or 30)
    plan = {}
    for raw in (_read(work / "shots.json") or {}).get("shots") or []:     # one by one: an old video's file may not
        try:                                                                # meet today's schema in every field
            plan[raw["id"]] = Shot.model_validate(raw)
        except (ValueError, KeyError, TypeError):
            continue
    listed = {s["id"]: s for s in feedback.shots(root, slug)}
    people = (_read(work / "people.json") or {}).get("people") or []
    subject = ", ".join(str(p.get("name")) for p in people[:2] if p.get("name"))
    portrait = None
    if people and people[0].get("image"):
        image_path = work / str(people[0]["image"])        # people.json paths are relative to the work folder
        data = portrait_bytes(image_path if image_path.is_file() else root / str(people[0]["image"]))
        portrait = (str(people[0].get("name") or "el protagonista"), data) if data else None

    final = ctx.out_dir / "video-final.mp4"
    on_screen = [shot for shot in timeline.get("shots") or [] if shot["id"] in listed]   # no graphics, no end screen
    # footage shots that ended with no picture at all (text on screen): the reviewer cannot flag them, so the baseline
    # counts them apart — fewer pictures must never look like fewer faults (newgym3-ideas: 92 of 231)
    as_text = sum(1 for shot in timeline.get("shots") or []
                  if shot.get("type") == "broll" and not shot.get("media") and not shot.get("groupId"))
    print(f"{slug}: leyendo los fotogramas de {len(on_screen)} planos…", flush=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        grabbed = list(pool.map(lambda shot: frames_of(work, shot, fps, final), on_screen))
    # media file → the shot that chose it (the one with a selection of its own, wherever it is in the video: in
    # newgym3 the wedding chosen for 9:57 was the original, its copies at 0:58-1:48 the borrowed ones)
    owner: dict[str, str] = {}
    for shot in on_screen:
        if listed[shot["id"]].get("method"):
            owner.setdefault(str((shot.get("media") or {}).get("src") or ""), shot["id"])
    for shot in on_screen:                         # a file only borrowed shots show: the first of them owns it
        owner.setdefault(str((shot.get("media") or {}).get("src") or ""), shot["id"])
    items: list[dict[str, Any]] = []
    for shot, images in zip(on_screen, grabbed):
        base = shot["id"].split("-")[0]
        src = str((shot.get("media") or {}).get("src") or "")
        borrowed = owner.get(src) if not listed[shot["id"]].get("method") and owner.get(src) != shot["id"] else None
        spec = plan.get(base)
        broll = spec.broll if spec is not None else None
        items.append({**listed[shot["id"]], "images": images, "hashes": [dhash(i) for i in images], "borrowed": borrowed,
                      "kind": spec.idea.kind if spec is not None and spec.idea is not None else None,
                      "intent": broll.visualIntent if broll else "", "entities": list(broll.entities) if broll else [],
                      "around": surrounding(list(plan.values()), base) if plan else ""})

    flagged: dict[str, dict[str, Any]] = {}
    unreadable = [i["id"] for i in items if not i["images"]]    # neither its clip nor the final video: not judged
    for item in items:
        if item.get("borrowed"):
            # a shot with no clip of its own, covered in the edit with another shot's (timeline.fill_empty_shots)
            flagged[item["id"]] = {"problem": "hueco_tapado", "confidence": 1.0, "by": "medida",
                                   "evidence": f"hueco sin clip propio, tapado con el clip del plano {item['borrowed']}"}
            continue
        why = broken(item["images"]) if item["images"] else None
        if why:
            flagged[item["id"]] = {"problem": "roto", "evidence": why, "confidence": 1.0, "by": "medida"}
    for shot_id, why in repeats(items, already=set(flagged)).items():
        flagged.setdefault(shot_id, {"problem": "repetido", "evidence": why, "confidence": 1.0, "by": "medida"})

    per_sheet = max(1, int(cfg.get("shots_per_sheet", 8)))
    todo = [i for i in items if i["images"] and i["id"] not in flagged]
    for n, item in enumerate(todo, 1):
        item["n"] = n
    sheets = [todo[i:i + per_sheet] for i in range(0, len(todo), per_sheet)]
    asked = ask_model or (lambda entries: ask(ctx, cfg, entries, subject, portrait))
    spent, reviewed, stopped = 0.0, 0, False
    workers = max(1, int(cfg.get("parallel", 4)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending = list(sheets)
        while pending and not stopped:              # a few sheets at a time: the budget is checked between them
            batch, pending = pending[:workers], pending[workers:]
            for entries, (answers, usd) in zip(batch, pool.map(asked, batch)):
                spent += usd
                reviewed += len(entries)
                print(f"   modelo: {reviewed} de {len(todo)} planos vistos · {spent:.3f} $", flush=True)
                by_n = {e["n"]: e for e in entries}
                for answer in answers:
                    entry = by_n.get(int(answer.get("n") or -1))
                    if entry is None or answer.get("verdict") != "wrong" or answer.get("problem") not in MODEL_TO_REASON:
                        continue
                    flagged[entry["id"]] = {"problem": MODEL_TO_REASON[answer["problem"]],
                                            "evidence": str(answer.get("evidence") or "").strip(),
                                            "confidence": round(float(answer.get("confidence") or 0), 2), "by": "modelo"}
            if spent >= budget and pending:
                stopped = True

    rows = []
    for item in items:
        if item["id"] in flagged:
            rows.append({k: item.get(k) for k in ("id", "at", "text", "method", "source", "title", "url", "channel",
                                                   "candidateId", "start", "end", "kind")} | flagged[item["id"]]
                        | {"label": (item.get("label") or {}).get("reason") if item.get("label") else None})
    result = {"slug": slug, "model": str(cfg.get("model") or ctx.section("judge").get("model", "gpt-5-mini")),
              "shots": len(items), "asText": as_text, "reviewedByModel": reviewed, "usd": round(spent, 4),
              "stoppedAtBudget": stopped, "budget": budget, "unreadable": unreadable, "flagged": rows}
    out = ctx.out_dir / OUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    (out / "revisor.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    images = {i["id"]: i["images"] for i in items}
    sheets_written = flagged_sheets(out, rows, images)
    (out / "informe.md").write_text(markdown(result, sheets_written), encoding="utf-8")
    return result


# --- what you look at ----------------------------------------------------------------------------------------

def flagged_sheets(out: Path, rows: list[dict[str, Any]], images: dict[str, list[np.ndarray]], per_sheet: int = 6) -> list[str]:
    """hoja-N.jpg: each flagged shot with its two frames and, under them, its time, problem, sentence and proof."""

    from PIL import Image, ImageDraw, ImageFont

    for old in out.glob("hoja-*.jpg"):
        old.unlink()
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 17)
        bold = ImageFont.truetype("DejaVuSans-Bold.ttf", 18)
    except OSError:
        font = bold = ImageFont.load_default()
    width, height = TILE
    block = height + 150
    names = []
    for start in range(0, len(rows), per_sheet):
        chunk = rows[start:start + per_sheet]
        canvas = Image.new("RGB", (2 * width + 20, block * len(chunk)), (18, 18, 18))
        draw = ImageDraw.Draw(canvas)
        for i, row in enumerate(chunk):
            y = i * block
            for k, image in enumerate((images.get(row["id"]) or [])[:2]):
                rgb = cv2.cvtColor(cv2.resize(image, TILE, interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB)
                canvas.paste(Image.fromarray(rgb), (10 + k * width, y + 6))
            text_y = y + height + 12
            draw.text((10, text_y), f"{_clock(float(row.get('at') or 0))} · {row['id']} · {PROBLEMS[row['problem']]} "
                                    f"· seguridad {row['confidence']:.0%} · {row.get('method') or '?'}",
                      fill=(255, 210, 80), font=bold)
            lines = textwrap.wrap(f"Frase: {row.get('text') or ''}", 80)[:2] + textwrap.wrap(f"Prueba: {row['evidence']}", 80)[:3]
            for j, line in enumerate(lines):
                draw.text((10, text_y + 26 + j * 22), line, fill=(235, 235, 235), font=font)
        name = f"hoja-{start // per_sheet + 1}.jpg"
        canvas.save(out / name, quality=85)
        names.append(name)
    return names


def markdown(result: dict[str, Any], sheets: list[str]) -> str:
    rows = result["flagged"]
    lines = [f"# Revisión automática · {result['slug']}", "",
             f"Modo informe: no se ha cambiado nada. Modelo {result['model']} · {result['shots']} planos con imagen · "
             f"{result['reviewedByModel']} vistos por el modelo · {result['usd']:.3f} $"
             + (f" · **parado al llegar al tope de {result['budget']} $**" if result["stoppedAtBudget"] else "")
             + (f" · sin poder leer (no revisados): {', '.join(result.get('unreadable') or [])}" if result.get("unreadable") else ""),
             "",
             f"**Planos marcados: {len(rows)}**", ""]
    if rows:
        counts: dict[str, int] = {}
        methods: dict[str, int] = {}
        for r in rows:
            counts[r["problem"]] = counts.get(r["problem"], 0) + 1
            methods[r.get("method") or "?"] = methods.get(r.get("method") or "?", 0) + 1
        lines += ["- Por motivo: " + ", ".join(f"{PROBLEMS[k]} {n}" for k, n in sorted(counts.items(), key=lambda kv: -kv[1])),
                  "- Por quién eligió el plano: " + ", ".join(f"{k} {n}" for k, n in sorted(methods.items(), key=lambda kv: -kv[1])),
                  "- Hojas con imagen y frase: " + ", ".join(sheets), "",
                  "| Minuto | Plano | Motivo | Seguridad | Prueba | Frase | Elegido por | Origen |", "|---|---|---|---|---|---|---|---|"]
        for r in rows:
            source = f"[{(r.get('title') or r.get('source') or '')[:40]}]({r['url']})" if r.get("url") else (r.get("source") or "")
            if r.get("start") is not None:
                source += f" {float(r['start']):.0f}-{float(r['end'] or 0):.0f} s"
            cell = lambda text: str(text or "").replace("|", "/").replace("\n", " ")
            lines.append(f"| {_clock(float(r.get('at') or 0))} | {r['id']} | {PROBLEMS[r['problem']]} | {r['confidence']:.0%} | "
                         f"{cell(r['evidence'])} | {cell(r.get('text'))[:120]} | {r.get('method') or '?'} | {cell(source)} |")
    lines += ["", "«Roto» y «Repetido» se miden (sin modelo); el resto lo dice el modelo de visión con los fotogramas del",
              "momento exacto que usa el vídeo. Nada de gustos: solo fallos objetivos.", ""]
    return "\n".join(lines)


# --- in the queue (bloque 3.3): the «revisor» stage, between the edit and the QA -------------------------------

OBJECTIVE = ("persona_equivocada", "dibujo_animado", "texto_marca_agua")


def to_fix(result: dict[str, Any], cfg: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """What goes back to the fill-in: (shot id → {reason, candidateId, start, end, evidence}, shots to show as text).

    Measured faults (a repeated stretch, a broken clip) always; in a literal idea anything the model is sure of
    (`revisor.min_confidence`, 0.85); in an ambient idea only the objective ones (another person, a cartoon, a
    watermark); in a video planned without ideas only those, and only when it is very sure
    (`revisor.min_confidence_sin_ideas`, 0.95). A shot covered with another shot's clip becomes text."""

    sure = float(cfg.get("min_confidence", 0.85))
    very_sure = float(cfg.get("min_confidence_sin_ideas", 0.95))
    wrong: dict[str, dict[str, Any]] = {}
    as_text: list[str] = []
    for row in result.get("flagged") or []:
        problem, confidence, kind = row["problem"], float(row.get("confidence") or 0), row.get("kind")
        if problem == "hueco_tapado":
            as_text.append(row["id"])
            continue
        if row.get("by") == "medida":
            act = problem in ("repetido", "roto")
        elif kind == "literal":
            act = confidence >= sure
        elif kind == "ambiente":
            act = problem in OBJECTIVE and confidence >= sure
        elif kind is None:
            act = problem in OBJECTIVE and confidence >= very_sure
        else:
            act = False                                  # a title read aloud: nothing to fix
        if act:
            wrong[row["id"].split("-")[0]] = {"reason": problem, "candidateId": row.get("candidateId"),
                                              "start": row.get("start"), "end": row.get("end"),
                                              "evidence": row.get("evidence"), "by": "revisor"}
    return wrong, as_text


AGAIN = ("fallback", "coldopen", "timeline")         # what is done again with the reviewer's corrections


def stage_run(ctx: RunContext, review_fn: Any = None) -> None:
    """`revisor.enabled` (off): the finished edit is reviewed before the render; what `to_fix` picks goes back to the
    fill-in ONCE (work/<slug>/revision.auto.json, its own file next to your revision.json), the fill-in, the cold
    open and the edit are done again, and the result is reviewed again: what is still flagged stays in
    out/<slug>/revisor/ (informe.md, hojas) for you."""

    import time as _time

    from . import feedback

    cfg = dict(ctx.section("revisor") or {})
    out = ctx.out_dir / OUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    target = out / "revisor.json"
    if not cfg.get("enabled", False):
        target.write_text(json.dumps({"skipped": "revisor.enabled apagado"}), encoding="utf-8")
        return
    look = review_fn or (lambda: review(ctx.root, ctx.slug))
    first = look()
    auto = ctx.work_dir / feedback.REVISION_AUTO
    wrong, as_text = to_fix(first, cfg)
    final, again = first, False
    if (wrong or as_text) and not auto.is_file():
        auto.parent.mkdir(parents=True, exist_ok=True)
        auto.write_text(json.dumps({"wrong": wrong, "noBorrow": as_text, "at": _time.strftime("%Y-%m-%d %H:%M")},
                                   ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"   Revisor: {len(wrong)} planos vuelven al relleno y {len(as_text)} huecos tapados pasan a texto; "
              f"se rehacen {', '.join(AGAIN)}")
        from .runner import STAGES, mark_done

        for stage in [s for s in STAGES if s.name in AGAIN]:
            began = _time.monotonic()
            stage.run(ctx)
            mark_done(ctx, stage, _time.monotonic() - began)
        final, again = look(), True
    elif auto.is_file():
        print("   Revisor: ya devolvió sus planos al relleno una vez; no se repite")
    summary = {**final, "before": len(first.get("flagged") or []), "sentBack": len(wrong) if again else 0,
               "asText": len(as_text) if again else 0}
    target.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"   Revisor: {summary['before']} marcados antes, {len(final.get('flagged') or [])} después")


def stage_inputs(ctx: RunContext) -> list:
    return [ctx.work_dir / "timeline.json"]


def main(argv: list[str]) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="python -m pipeline.revisor", description=__doc__.splitlines()[0])
    parser.add_argument("videos", nargs="+")
    parser.add_argument("--modelo", default=None)
    parser.add_argument("--max-usd", type=float, default=None)
    parser.add_argument("--telegram", action="store_true", help="manda el resumen y las hojas al Telegram del canal")
    parser.add_argument("--base", action="store_true",
                        help="junta el resumen de todos en out/_revisor_base.md (la línea base para comparar)")
    args = parser.parse_args(argv)
    results = []
    for slug in args.videos:
        try:
            result = review(PROJECT_ROOT, slug, args.modelo, args.max_usd)
        except FileNotFoundError as error:          # not edited yet: the others still go, and the table says so
            print(f"{slug}: sin revisar — {error}")
            results.append({"slug": slug, "missing": str(error)})
            continue
        results.append(result)
        line = (f"{slug}: {len(result['flagged'])} de {result['shots']} planos marcados · {result['usd']:.3f} $ · "
                f"out/{slug}/{OUT_DIR}/informe.md")
        print(line)
        if args.telegram:
            send_telegram(PROJECT_ROOT, slug, result)
    if args.base:
        target = PROJECT_ROOT / "out" / "_revisor_base.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(baseline(results), encoding="utf-8")
        print(f"Línea base: {target.relative_to(PROJECT_ROOT)}")
    return 0


BASE_COLUMNS = ("hueco_tapado", "repetido", "no_tiene_que_ver", "persona_equivocada", "dibujo_animado",
                "texto_marca_agua", "roto")


def baseline(results: list[dict[str, Any]]) -> str:
    """One row per video: shots flagged per 100, and by reason (repeats counted as pairs: one per pair, on its
    weaker side). The number to compare before and after each change to the engine."""

    import time

    head = ["Vídeo", "Planos", "En texto", "Marcados por 100", "Huecos tapados", "Repetidos (parejas)", "No tiene que ver",
            "…en literales", "Otra persona", "Dibujos", "Marca de agua", "Roto", "No revisados", "Modelo", "$"]
    lines = [f"# Línea base del revisor · {time.strftime('%Y-%m-%d %H:%M')}", "",
             "Marcados por cada 100 planos con imagen; cada pareja de repetidos cuenta una vez, en su lado más débil "
             "(un préstamo antes que el relleno, el relleno antes que la elección del juez). «En texto»: planos de "
             "metraje que acabaron sin imagen (el revisor no puede marcarlos): una mejora no vale si sube esa columna.", "",
             "| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for r in results:
        if r.get("missing"):
            lines.append(f"| {r['slug']} | sin montar todavía |" + " |" * (len(head) - 2))
            continue
        counts = {k: 0 for k in BASE_COLUMNS}
        for row in r["flagged"]:
            counts[row["problem"]] = counts.get(row["problem"], 0) + 1
        per100 = 100 * len(r["flagged"]) / max(1, r["shots"])
        literal = sum(1 for row in r["flagged"] if row["problem"] == "no_tiene_que_ver" and row.get("kind") == "literal")
        labelled = any(row.get("kind") for row in r["flagged"])
        cells = [str(counts[k]) for k in BASE_COLUMNS]
        cells.insert(3, str(literal) if labelled else "—")
        lines.append(f"| {r['slug']} | {r['shots']} | {r.get('asText', '—')} | {per100:.0f} | "
                     + " | ".join(cells)
                     + f" | {len(r.get('unreadable') or [])} | {r['model']} | {r['usd']:.3f} |")
    lines += ["", "«…en literales»: los «no tiene que ver» en ideas que tenían que verse tal cual (planner.ideas); «—» en "
              "vídeos planificados sin ideas.", ""]
    return "\n".join(lines)


def send_telegram(root: Path, slug: str, result: dict[str, Any], limit: int = 8) -> bool:
    """The summary and the sheets (each flagged shot with its frames, sentence and proof) to the channel's chat."""

    from . import notify

    ctx = RunContext.create(slug, root=root)
    counts: dict[str, int] = {}
    for row in result["flagged"]:
        counts[PROBLEMS[row["problem"]]] = counts.get(PROBLEMS[row["problem"]], 0) + 1
    text = (f"🔎 Revisión automática de {slug} (modo informe, no ha cambiado nada)\n"
            f"{len(result['flagged'])} de {result['shots']} planos marcados · {result['usd']:.2f} $\n"
            + "\n".join(f"• {k}: {n}" for k, n in sorted(counts.items(), key=lambda kv: -kv[1]))
            + "\n\nMira las hojas: ¿lo marcado está mal de verdad?")
    sheets = sorted((ctx.out_dir / OUT_DIR).glob("hoja-*.jpg"), key=lambda p: int(p.stem.split("-")[1]))[:limit]
    return notify.telegram(ctx, text, sheets)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
