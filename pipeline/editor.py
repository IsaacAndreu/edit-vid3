"""Editor before the render: `python main.py --editor SLUG` → http://127.0.0.1:8766

A local page that plays the edit exactly as it will be rendered (Remotion Player with the same
components) and lets you fix it before spending the render time:
- swap a shot's footage for another option the analysis already found (with thumbnails);
- change or remove animated graphics, name/place labels, chapter titles and big stats;
- apply (re-downloads only the swapped shots and rebuilds the timeline) and render.

Every change is kept in work/<slug>/edits.json, so it survives re-running a stage: the judge applies
the footage swaps to its selection and the timeline applies the text changes when they run again.
Only listens on this PC (127.0.0.1).
"""

from __future__ import annotations

import json
import mimetypes
import os
import re
import subprocess
import sys
import threading
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from . import edit_model
from .context import RunContext

EDITS = "edits.json"
APP_DIR = Path(__file__).resolve().parent.parent / "editor"
THUMBS = "editor/thumbs"
MAX_OPTIONS = 9


# --- edits ------------------------------------------------------------------------------------------

def load(ctx: RunContext) -> dict[str, Any]:
    path = ctx.work_dir / EDITS
    return edit_model.normalise(json.loads(path.read_text("utf-8")) if path.is_file() else {})


def save(ctx: RunContext, edits: dict[str, Any]) -> None:
    ctx.write_json(EDITS, edit_model.normalise(edits))


def apply_to_timeline(timeline: dict[str, Any], edits: dict[str, Any]) -> dict[str, Any]:
    """The editor's changes on a timeline dict, without the steps that make files (see edit_model)."""

    return edit_model.build(timeline, edits)


def story(ctx: RunContext) -> dict[str, Any] | None:
    path = ctx.work_dir / "shots.json"
    return json.loads(path.read_text("utf-8")) if path.is_file() else None


def build(ctx: RunContext, base: dict[str, Any], edits: dict[str, Any] | None = None) -> dict[str, Any]:
    return edit_model.build(base, edits if edits is not None else load(ctx), ctx, story(ctx))


def apply_footage(ctx: RunContext, selections: list[Any]) -> list[Any]:
    """The judge's selections with the footage chosen in the editor (Selection models)."""

    from .schemas import Selection

    swaps = load(ctx)["footage"]
    if not swaps:
        return selections
    out = []
    for selection in selections:
        swap = swaps.get(selection.shotId)
        built = selection_for(ctx, selection.shotId, swap) if swap else None
        out.append(Selection.model_validate(built) if built else selection)
    return out


_OPTIONS: dict[str, Any] = {}


def _options(ctx: RunContext, shot_id: str) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Usable analysed options of a shot (best first) and its candidates by id (cached per file version)."""

    scores_path = ctx.work_dir / "scores" / f"{shot_id}.json"
    cand_path = ctx.work_dir / "candidates" / f"{shot_id}.json"
    if not scores_path.is_file() or not cand_path.is_file():
        return [], {}
    key = f"{scores_path}:{scores_path.stat().st_mtime_ns}:{cand_path.stat().st_mtime_ns}"
    if key not in _OPTIONS:
        _OPTIONS[key] = _read_options(scores_path, cand_path)
    return _OPTIONS[key]


def _read_options(scores_path: Path, cand_path: Path) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    options = [o for o in json.loads(scores_path.read_text("utf-8")).get("options", []) if not o.get("discarded")]
    options.sort(key=lambda o: -float(o.get("total") or 0))
    candidates = {c["id"]: c for c in json.loads(cand_path.read_text("utf-8")).get("candidates", [])}
    return [o for o in options if o["candidateId"] in candidates], candidates


def selection_for(ctx: RunContext, shot_id: str, footage: dict[str, Any]) -> dict[str, Any] | None:
    """A selection entry for the footage chosen in the editor (an analysed option, a slip of it, or
    a video found with the editor's search)."""

    options, candidates = _options(ctx, shot_id)
    option = next((o for o in options if o["candidateId"] == footage.get("candidateId")
                   and (abs(float(o.get("start") or 0) - float(footage.get("start") or 0)) < 0.01 or "end" in footage)), None)
    candidate = candidates.get(str(footage.get("candidateId")))
    if option is None and candidate is not None and "end" in footage:     # slip of a candidate with no option at hand
        option = {"candidateId": candidate["id"], "source": candidate["source"], "kind": candidate["kind"]}
    return edit_model.selection_entry(shot_id, footage, option, candidate if option else None)


def patch_selection(ctx: RunContext) -> int:
    """Write the footage choices into selection.json now (so only ingest and later stages re-run)."""

    from .schemas import SelectionFile

    path = ctx.work_dir / "selection.json"
    selection = SelectionFile.model_validate_json(path.read_text("utf-8"))
    patched = apply_footage(ctx, selection.selections)
    changed = sum(a is not b for a, b in zip(selection.selections, patched))
    ctx.write_json("selection.json", SelectionFile(slug=selection.slug, selections=patched,
                                                    stats=selection.stats).model_dump(exclude_none=True))
    return changed


# --- what the page shows -------------------------------------------------------------------------------

def _frame(src: Path, seconds: float, target: Path, width: int = 320) -> Path | None:
    if not target.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        if src.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
            args = ["-i", str(src)]
        else:
            args = ["-ss", f"{max(0.0, seconds):.3f}", "-i", str(src)]
        subprocess.run(["ffmpeg", "-y", "-v", "error", *args, "-frames:v", "1", "-vf", f"scale={width}:-2",
                        "-q:v", "4", str(target)], check=False)
    return target if target.is_file() else None


def shot_thumb(ctx: RunContext, shot_id: str) -> Path | None:
    timeline = json.loads((ctx.work_dir / "timeline.json").read_text("utf-8"))
    shot = next((s for s in timeline["shots"] if s["id"] == shot_id), None)
    media = (shot or {}).get("media")
    if not media:
        return None
    src = ctx.work_dir / media["src"]
    return _frame(src, 0.4, ctx.work_dir / THUMBS / f"{shot_id}-{src.stat().st_mtime_ns if src.is_file() else 0}.jpg")


def option_thumb(ctx: RunContext, shot_id: str, index: int) -> Path | None:
    options, _ = _options(ctx, shot_id)
    if not 0 <= index < len(options):
        return None
    option = options[index]
    path = ctx.root / str(option.get("analysisPath") or "")
    if not path.is_file():
        return None
    middle = (float(option.get("start") or 0) + float(option.get("end") or 0)) / 2
    offset = _window_start(path)
    found = _frame(path, middle - offset, ctx.work_dir / THUMBS / f"{shot_id}-opt{index}.jpg")
    if found is not None and found.stat().st_size < 2500:   # an all-black frame compresses to almost nothing
        return None
    return found


def option_poster(ctx: RunContext, shot_id: str, index: str) -> str | None:
    options, _ = _options(ctx, shot_id)
    try:
        candidate = options[int(index)]["candidateId"]
    except (ValueError, IndexError):
        return None
    return f"https://i.ytimg.com/vi/{candidate[3:]}/mqdefault.jpg" if candidate.startswith("yt:") else None


def _window_start(path: Path) -> float:
    """Analysis windows are named a360_<start>_<end>.mp4 (seconds of the source video)."""

    found = re.match(r"a360_([\d.]+)_([\d.]+)", path.stem)
    return float(found.group(1)) if found else 0.0


def _voice_frames(ctx: RunContext, base: dict[str, Any]) -> list[list[Any]]:
    """[[frame, word]] of the narration in the pipeline's frames (before scene edits)."""

    path = ctx.work_dir / "words.json"
    if not path.is_file():
        return []
    fps = base["fps"]
    audio = base["audio"]
    gaps = audio.get("voiceGaps", [])
    out = []
    for word in json.loads(path.read_text("utf-8")).get("words", []):
        frame = round(word["start"] * fps)
        out.append([audio.get("voiceFrom", 0) + frame + sum(b for at, b in gaps if at <= frame), word["text"]])
    return out


def state(ctx: RunContext) -> dict[str, Any]:
    timeline = json.loads((ctx.work_dir / "timeline.json").read_text("utf-8"))
    base_path = ctx.work_dir / "timeline.base.json"
    base = json.loads(base_path.read_text("utf-8")) if base_path.is_file() else timeline
    selection = {}
    if (ctx.work_dir / "selection.json").is_file():
        selection = {s["shotId"]: s for s in json.loads((ctx.work_dir / "selection.json").read_text("utf-8"))["selections"]}
    qa = ctx.section("qa")
    low_score, low_conf = float(qa.get("low_score", 0.30)), float(qa.get("low_confidence", 0.6))
    edits = load(ctx)
    shots = []
    for shot in timeline["shots"]:
        chosen = selection.get(shot["id"], {})
        judge = chosen.get("judge") or {}
        weak = bool(chosen) and chosen.get("decidedBy") != "editor" and shot["id"] not in edits["own"] and (
            chosen.get("status") == "fallback" or (judge and float(judge.get("confidence") or 1) < low_conf)
            or (not judge and chosen.get("score") is not None and float(chosen["score"]) < low_score)
            or str((shot.get("media") or {}).get("source", "")).lower() in ("pexels", "generated"))
        shots.append({"id": shot["id"], "type": shot["type"], "from": shot["from"], "durationInFrames": shot["durationInFrames"],
                      "text": shot.get("text", ""), "chapterTitle": shot.get("chapterTitle"),
                      "media": shot.get("media"), "title": chosen.get("title"), "channel": chosen.get("channel"),
                      "candidateId": chosen.get("candidateId"), "start": chosen.get("start"), "end": chosen.get("end"),
                      "decidedBy": chosen.get("decidedBy"), "reason": judge.get("reason"), "weak": weak,
                      "swapped": shot["id"] in edits["footage"] or shot["id"] in edits["own"] or shot["id"] in edits["media"],
                      "options": len(_options(ctx, shot["id"])[0])})
    labels = [{"original": label["text"], "text": edits["labels"].get(label["text"], label["text"]), "from": label["from"],
               "durationInFrames": label["durationInFrames"], "kind": label["kind"]} for label in base.get("labels", [])]
    removed = [{"id": g["id"], "kind": g["kind"], "type": (g.get("graphic") or {}).get("type"), "from": g["from"],
                "durationInFrames": g["durationInFrames"]} for g in [*base["groups"], *edits["added"]]
               if g["id"] in set(edits["removed"])]
    # the tracks, in the pipeline's frames (before scene reordering): the page maps them with timeMap
    unedited = edit_model.build(base, {**edits, "order": [], "deleted": []}, keep_keys=True)
    return {"slug": ctx.slug, "timeline": timeline, "shots": shots, "edits": edits, "labels": labels, "removedGroups": removed,
            "layout": unedited, "scenes": edit_model.scenes(unedited, story(ctx)), "timeMap": edit_model.time_map(timeline),
            "words": _voice_frames(ctx, base), "baseDuration": base["durationInFrames"],
            "rendered": (ctx.out_dir / "video-final.mp4").is_file(), "job": JOB.status()}


def options(ctx: RunContext, shot_id: str) -> list[dict[str, Any]]:
    found, candidates = _options(ctx, shot_id)
    out = []
    for index, option in enumerate(found[:MAX_OPTIONS]):
        c = candidates[option["candidateId"]]
        path = str(option.get("analysisPath") or "")
        offset = _window_start(Path(path))
        out.append({"index": index, "candidateId": option["candidateId"], "start": option.get("start"), "end": option.get("end"),
                    "kind": option["kind"], "source": option["source"], "title": c["title"], "channel": c["channel"],
                    "score": round(float(option.get("total") or 0), 3), "thumb": f"/api/thumb/{shot_id}/{index}",
                    "preview": f"/root/{path}" if path.startswith("cache/") else None,
                    "previewFrom": round(float(option.get("start") or 0) - offset, 2) if option["kind"] == "video" else None,
                    "previewTo": round(float(option.get("end") or 0) - offset, 2) if option["kind"] == "video" else None})
    return out


def set_edits(ctx: RunContext, edits: dict[str, Any]) -> dict[str, Any]:
    """The page sends the whole set of changes (that is how undo/redo work)."""

    save(ctx, edits)
    refresh(ctx)
    return state(ctx)


def edit(ctx: RunContext, body: dict[str, Any]) -> dict[str, Any]:
    """One change (kept for simple clients and the tests)."""

    edits = load(ctx)
    kind = body.get("type")
    if kind == "footage":
        shot, option = str(body["shot"]), body.get("option")
        if option is None:
            edits["footage"].pop(shot, None)
        else:
            edits["footage"][shot] = {k: v for k, v in option.items() if v is not None}
    elif kind == "text":
        edits["texts"][str(body["key"])] = body["value"]
    elif kind == "label":
        edits["labels"][str(body["original"])] = str(body["value"])
    elif kind == "remove":
        if body["id"] not in edits["removed"]:
            edits["removed"].append(str(body["id"]))
    elif kind == "restore":
        edits["removed"] = [g for g in edits["removed"] if g != body["id"]]
    else:
        raise ValueError(f"cambio desconocido: {kind}")
    return set_edits(ctx, edits)


def refresh(ctx: RunContext, edits: dict[str, Any] | None = None) -> None:
    """timeline.json = the pipeline's edit (timeline.base.json) + the editor's changes."""

    base = ctx.work_dir / "timeline.base.json"
    if not base.is_file():
        return
    ctx.write_json("timeline.json", build(ctx, json.loads(base.read_text("utf-8")), edits))


# --- library: templates, music, sound effects, search, uploads ---------------------------------------------------

TEMPLATES: list[dict[str, Any]] = [
    {"type": "kinetic", "name": "Texto cinético", "seconds": 3, "data": {"lines": ["UNA FRASE", "QUE IMPACTA"]}},
    {"type": "map", "name": "Mapa", "seconds": 6, "data": {"title": "Título del mapa", "countries": [], "points": [], "route": False,
                                                          "zoom": None, "globe": False}},
    {"type": "compare", "name": "A vs B", "seconds": 7, "data": {"title": "A vs B", "left": {"name": "Atleta A"},
                                                                 "right": {"name": "Atleta B"}, "rows": [
        {"label": "Oros", "a": 2, "b": 1, "unit": None, "better": "high"}, {"label": "Mundiales", "a": 3, "b": 4, "unit": None, "better": "high"}]}},
    {"type": "chart", "name": "Gráfica", "seconds": 6, "data": {"chart": "bar", "title": "Título", "unit": None, "data": [
        {"label": "2016", "value": 10}, {"label": "2020", "value": 14}, {"label": "2024", "value": 19}]}},
    {"type": "timeline", "name": "Línea de tiempo", "seconds": 7, "data": {"title": "Su carrera", "events": [
        {"year": "2016", "text": "Primer hito"}, {"year": "2020", "text": "Segundo hito"}, {"year": "2024", "text": "Tercer hito"}]}},
    {"type": "specs", "name": "Ficha técnica", "seconds": 6, "data": {"kicker": "EN CIFRAS", "name": "Nombre", "subtitle": None, "specs": [
        {"label": "Edad", "value": "24", "unit": None}, {"label": "Altura", "value": "1,50", "unit": "m"}, {"label": "Oros", "value": "2", "unit": None}]}},
    {"type": "rank", "name": "Puesto de ranking", "seconds": 5, "data": {"rank": 1, "total": 10, "name": "Nombre", "subtitle": None,
                                                                         "stats": [{"label": "Dato", "value": "10"}]}},
    {"type": "score", "name": "Nota desglosada", "seconds": 5, "data": {"name": "Gimnasta", "title": "Suelo", "d": 6.6, "e": 8.4,
                                                                         "penalty": None, "total": 15.0, "labels": {}}},
    {"type": "press", "name": "Recortes de prensa", "seconds": 6, "data": {"items": [
        {"outlet": "Periódico", "headline": "Titular de la noticia", "date": None, "highlight": "noticia"}]}},
    {"type": "rule", "name": "Reglamento", "seconds": 6, "data": {"source": "REGLAMENTO", "article": None,
                                                                   "text": "Texto de la norma", "highlight": "norma", "stamp": "PROHIBIDO"}},
    {"type": "banned", "name": "Prohibido", "seconds": 5, "data": {"name": "Elemento", "number": None, "who": None, "reason": None,
                                                                    "since": None, "stamp": "PROHIBIDO"}},
    {"type": "standings", "name": "Marcador", "seconds": 7, "data": {"title": "Final", "rows": [
        {"name": "Atleta A", "score": "15.000"}, {"name": "Atleta B", "score": "14.900"}, {"name": "Atleta C", "score": "14.800"}]}},
    {"type": "podium", "name": "Podio", "seconds": 6, "data": {"title": "Final", "places": [
        {"place": 1, "name": "Oro", "note": None}, {"place": 2, "name": "Plata", "note": None}, {"place": 3, "name": "Bronce", "note": None}]}},
    {"type": "card", "name": "Carta de jugador", "seconds": 6, "data": {"name": "Atleta", "position": None,
                                                                         "headline": {"label": "Oros", "value": "2"},
                                                                         "stats": [{"label": "Mundiales", "value": "3"},
                                                                                   {"label": "Edad", "value": "24"},
                                                                                   {"label": "Medallas", "value": "8"}]}},
    {"type": "scale", "name": "Escala", "seconds": 6, "data": {"title": "Título", "axis": "height", "unit": "m", "items": [
        {"name": "La marca", "value": 2.45}, {"name": "Persona media", "value": 1.75, "reference": True}]}},
]


def templates(ctx: RunContext) -> list[dict[str, Any]]:
    from .graphics import fixed_words

    words = fixed_words(ctx)
    out = json.loads(json.dumps(TEMPLATES))
    for template in out:
        if template["type"] == "score":
            template["data"]["labels"] = {"d": words["d"], "e": words["e"], "penalty": words["pen"], "total": words["total"]}
    return out


def assets(ctx: RunContext) -> dict[str, Any]:
    """Music tracks and sound effects the page can choose (the channel's own first)."""

    folder = ctx.root / str(ctx.section("timeline").get("assets", "assets"))
    found: dict[str, list[dict[str, str]]] = {"music": [], "sfx": []}
    for kind in found:
        seen = set()
        for base in (folder / kind, ctx.root / "assets" / kind):
            for path in sorted(base.glob("*")) if base.is_dir() else []:
                if path.suffix.lower() in (".mp3", ".wav", ".m4a", ".ogg") and path.name not in seen:
                    seen.add(path.name)
                    found[kind].append({"src": str(path.relative_to(ctx.root)).replace("\\", "/"), "name": path.stem,
                                        "mood": path.stem.split("-")[0]})
    return found


def geocode(ctx: RunContext, query: str) -> dict[str, Any]:
    from .graphics import geocode as lookup

    found = lookup(ctx, query)
    if not found:
        raise ValueError(f"No encuentro «{query}»")
    return {"lon": found[0], "lat": found[1]}


def search(ctx: RunContext, query: str) -> list[dict[str, Any]]:
    """YouTube videos for a query typed in the editor (to use a part of one in a shot)."""

    import yt_dlp

    if not query.strip():
        raise ValueError("Escribe qué buscar")
    with yt_dlp.YoutubeDL({"quiet": True, "extract_flat": True, "skip_download": True, "noplaylist": True}) as ydl:
        info = ydl.extract_info(f"ytsearch12:{query}", download=False)
    out = []
    for entry in (info or {}).get("entries") or []:
        if not entry or not entry.get("id"):
            continue
        out.append({"id": entry["id"], "title": entry.get("title") or "", "channel": entry.get("channel") or entry.get("uploader") or "",
                    "duration": entry.get("duration"), "thumb": f"https://i.ytimg.com/vi/{entry['id']}/mqdefault.jpg",
                    "url": f"https://www.youtube.com/watch?v={entry['id']}"})
    return out


UPLOADS = "editor/uploads"
MAX_UPLOAD = 1_500_000_000


def upload(ctx: RunContext, name: str, data: bytes) -> dict[str, Any]:
    """A clip or photo of your own, to drop onto a shot."""

    kind = "image" if Path(name).suffix.lower() in (".jpg", ".jpeg", ".png", ".webp") else "video"
    if Path(name).suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov", ".m4v", ".webm"):
        raise ValueError("Formato no admitido: usa mp4, mov, webm, jpg, png o webp")
    folder = ctx.work_dir / UPLOADS
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / edit_model.sanitize_name(name)
    target.write_bytes(data)
    if kind == "video" and target.suffix.lower() != ".mp4":        # the browser and the render both want H.264 mp4
        converted = target.with_suffix(".mp4")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(target), "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                        "-pix_fmt", "yuv420p", "-an", str(converted)], check=True)
        target = converted
    return {"src": str(target.relative_to(ctx.work_dir)), "kind": kind}


def waveform(ctx: RunContext, per_second: int = 20) -> dict[str, Any]:
    """Peaks of the narration (in the pipeline's timeline frames) for the voice track."""

    import numpy as np

    base_path = ctx.work_dir / "timeline.base.json"
    base = json.loads(base_path.read_text("utf-8")) if base_path.is_file() else json.loads((ctx.work_dir / "timeline.json").read_text("utf-8"))
    cache = ctx.work_dir / "editor" / "waveform.json"
    voice = ctx.work_dir / base["audio"]["voice"]
    if cache.is_file() and cache.stat().st_mtime >= voice.stat().st_mtime:
        return json.loads(cache.read_text("utf-8"))
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(voice), "-ac", "1", "-ar", "8000", "-f", "s16le", "-"],
                         capture_output=True).stdout
    samples = np.abs(np.frombuffer(raw, dtype=np.int16).astype(np.float32))
    step = 8000 // per_second
    peaks = [float(samples[i:i + step].max()) for i in range(0, len(samples), step)] if len(samples) else []
    top = max(peaks) if peaks else 1.0
    result = {"perSecond": per_second, "peaks": [round(v / top, 3) for v in peaks], "voiceFrom": base["audio"].get("voiceFrom", 0),
              "gaps": base["audio"].get("voiceGaps", []), "fps": base["fps"]}
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(result), encoding="utf-8")
    return result


class Job:
    """One pipeline run at a time in the background (apply / render), with its last log lines."""

    def __init__(self) -> None:
        self.process: subprocess.Popen | None = None
        self.kind = ""
        self.log: list[str] = []

    def status(self) -> dict[str, Any]:
        running = self.process is not None and self.process.poll() is None
        code = None if self.process is None or running else self.process.returncode
        return {"kind": self.kind, "running": running, "ok": code == 0 if code is not None else None, "log": self.log[-12:]}

    def start(self, ctx: RunContext, kind: str, args: list[str]) -> dict[str, Any]:
        if self.process is not None and self.process.poll() is None:
            raise RuntimeError("Ya hay un proceso en marcha")
        self.kind, self.log = kind, []
        self.process = subprocess.Popen([sys.executable, "-u", str(ctx.root / "main.py"), "--slug", ctx.slug, *args],
                                        cwd=ctx.root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                        env={**os.environ, "PYTHONUNBUFFERED": "1"})

        def read() -> None:
            assert self.process and self.process.stdout
            for line in self.process.stdout:
                line = line.rstrip()
                if line and not line.startswith(("[h264", "WARNING", "Warning")):
                    self.log.append(line[:300])

        threading.Thread(target=read, daemon=True).start()
        return self.status()


JOB = Job()


def apply(ctx: RunContext) -> dict[str, Any]:
    changed = patch_selection(ctx)
    JOB.start(ctx, "apply", ["--until", "timeline"])
    return {**JOB.status(), "changed": changed}


def render(ctx: RunContext) -> dict[str, Any]:
    return JOB.start(ctx, "render", [])


# --- server ------------------------------------------------------------------------------------------------

def build_app(root: Path) -> Path:
    """Bundle editor/src/main.tsx (+ the Remotion components) into editor/dist/app.js when out of date."""

    out = APP_DIR / "dist" / "app.js"
    sources = [*APP_DIR.joinpath("src").rglob("*.ts*"), *root.joinpath("remotion").rglob("*.ts*")]
    if out.is_file() and all(p.stat().st_mtime <= out.stat().st_mtime for p in sources):
        return out
    print("Preparando el editor (una vez)…")
    esbuild = root / "node_modules" / ".bin" / ("esbuild.cmd" if os.name == "nt" else "esbuild")
    subprocess.run([str(esbuild), str(APP_DIR / "src" / "main.tsx"), "--bundle", f"--outfile={out}", "--minify",
                    "--format=iife", "--loader:.woff2=file", "--loader:.woff=file", "--loader:.ttf=file",
                    "--public-path=/app/", "--define:process.env.NODE_ENV=\"production\"", "--jsx=automatic"],
                   check=True, cwd=root)
    return out


def _file(handler: BaseHTTPRequestHandler, path: Path) -> None:
    """A file with HTTP Range support (the player seeks inside videos)."""

    size = path.stat().st_size
    kind = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    start, end = 0, size - 1
    ranged = handler.headers.get("Range", "")
    found = re.match(r"bytes=(\d*)-(\d*)", ranged)
    if found and (found.group(1) or found.group(2)):
        if found.group(1):
            start = int(found.group(1))
            end = int(found.group(2)) if found.group(2) else size - 1
        else:
            start = max(0, size - int(found.group(2)))
        end = min(end, size - 1)
        handler.send_response(206)
        handler.send_header("Content-Range", f"bytes {start}-{end}/{size}")
    else:
        handler.send_response(200)
    handler.send_header("Content-Type", kind)
    handler.send_header("Accept-Ranges", "bytes")
    handler.send_header("Content-Length", str(end - start + 1))
    handler.send_header("Cache-Control", "no-cache")
    handler.end_headers()
    with path.open("rb") as stream:
        stream.seek(start)
        remaining = end - start + 1
        try:
            while remaining > 0:
                chunk = stream.read(min(1 << 20, remaining))
                if not chunk:
                    break
                handler.wfile.write(chunk)
                remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass


def _inside(base: Path, relative: str) -> Path | None:
    path = (base / unquote(relative)).resolve()
    return path if path.is_file() and base.resolve() in path.parents else None


def make_handler(ctx: RunContext, port: int) -> type[BaseHTTPRequestHandler]:
    allowed = {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:
            pass

        def _json(self, status: int, payload: Any) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _run(self, action: Any) -> None:
            try:
                self._json(200, action())
            except FileNotFoundError:
                self._json(404, {"error": "no existe"})
            except (ValueError, RuntimeError, KeyError) as error:
                self._json(400, {"error": str(error)})
            except Exception as error:
                traceback.print_exc()
                self._json(500, {"error": f"{type(error).__name__}: {error}"})

        def do_GET(self) -> None:
            url = urlparse(self.path)
            path = url.path
            if path in ("/", "/index.html"):
                data = (APP_DIR / "index.html").read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            if path.startswith("/app/"):
                found = _inside(APP_DIR / "dist", path[len("/app/"):])
            elif path.startswith("/work/"):              # the edit's media: staticFile() in the components
                found = _inside(ctx.work_dir, path[len("/work/"):])
            elif path.startswith("/root/cache/"):        # analysis clips of the alternatives
                found = _inside(ctx.root / "cache", path[len("/root/cache/"):])
            elif path.startswith("/api/thumb/"):
                parts = path.split("/")[3:]
                try:
                    found = (shot_thumb(ctx, parts[0]) if len(parts) == 1 else option_thumb(ctx, parts[0], int(parts[1])))
                except (OSError, ValueError, KeyError):
                    found = None
                if found is None and len(parts) == 2:     # no local frame: YouTube's own thumbnail
                    fallback = option_poster(ctx, parts[0], parts[1])
                    if fallback:
                        self.send_response(302)
                        self.send_header("Location", fallback)
                        self.end_headers()
                        return
            else:
                query = parse_qs(url.query)
                q = (query.get("q") or [""])[0]
                routes = {"/api/state": lambda: state(ctx), "/api/job": JOB.status, "/api/templates": lambda: templates(ctx),
                          "/api/assets": lambda: assets(ctx), "/api/waveform": lambda: waveform(ctx),
                          "/api/geocode": lambda: geocode(ctx, q), "/api/search": lambda: search(ctx, q)}
                if path in routes:
                    self._run(routes[path])
                elif path.startswith("/api/options/"):
                    self._run(lambda: options(ctx, path.rsplit("/", 1)[1]))
                else:
                    self._json(404, {"error": "no existe"})
                return
            if found is None:
                self._json(404, {"error": "no existe"})
            else:
                _file(self, found)

        def do_POST(self) -> None:
            if self.headers.get("Origin") not in allowed:
                self._json(403, {"error": "origen no permitido"})
                return
            url = urlparse(self.path)
            if url.path == "/api/upload" and self.headers.get("Content-Type") == "application/octet-stream":
                length = int(self.headers.get("Content-Length") or 0)
                if length > MAX_UPLOAD:
                    self._json(400, {"error": "archivo demasiado grande"})
                    return
                name = (parse_qs(url.query).get("name") or ["archivo"])[0]
                data = self.rfile.read(length)
                self._run(lambda: upload(ctx, name, data))
                return
            if self.headers.get("Content-Type") != "application/json":
                self._json(403, {"error": "tipo no permitido"})
                return
            length = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                self._json(400, {"error": "JSON no válido"})
                return
            path = urlparse(self.path).path
            actions = {"/api/edit": lambda: edit(ctx, body), "/api/edits": lambda: set_edits(ctx, body.get("edits") or {}),
                       "/api/apply": lambda: apply(ctx), "/api/render": lambda: render(ctx)}
            if path in actions:
                self._run(actions[path])
            else:
                self._json(404, {"error": "no existe"})

    return Handler


def serve(ctx: RunContext, port: int = 8766, open_browser: bool = True) -> None:
    if not (ctx.work_dir / "timeline.json").is_file():
        raise SystemExit(f"{ctx.slug} aún no tiene montaje: lanza antes `python main.py --slug {ctx.slug} --review`")
    base = ctx.work_dir / "timeline.base.json"          # made by the timeline stage; older runs: the current one
    if not base.is_file() and not any(load(ctx).values()):
        base.write_text((ctx.work_dir / "timeline.json").read_text("utf-8"), encoding="utf-8")
    if not edit_model.is_empty(load(ctx)):
        refresh(ctx)                                     # the changes on top of the current pipeline edit
    build_app(ctx.root)
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(ctx, port))
    url = f"http://127.0.0.1:{port}"
    print(f"Editor de {ctx.slug} en {url}  (Ctrl+C para cerrarlo)")
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
