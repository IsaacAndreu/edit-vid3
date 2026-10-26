"""«Por qué funcionó / por qué no»: each uploaded video against its own channel, and what to repeat next time.

- Curves: the watcher looks at every video uploaded in the last 31 days and records its views at 1 h, 3 h, 6 h, 12 h,
  1, 2, 4, 7, 14 and 30 days (out/_porque/curvas.json; one YouTube API unit per 50 videos).
- Normal: the channel's other videos at the same age — median and the middle half (p25-p75), the grey band.
- Why: at 48 h and at 7 days the LLM compares the video with the niche's winners (today's radar) and with the
  channel's own videos, on what can be checked — topic, title, length, opening of the script — and writes one
  lesson. out/_porque/<slug>.json.
- The lessons of each channel (`lessons`) go into the next script drafts (organizar.draft_script) and the autopilot.
"""

from __future__ import annotations

import json
import re
import statistics
import time
from datetime import datetime
from pathlib import Path
from typing import Any

FOLDER = Path("out") / "_porque"
CURVES = FOLDER / "curvas.json"
CHECKPOINTS = [1, 3, 6, 12, 24, 48, 96, 168, 336, 720]          # hours
ANALYSE_AT = (48, 168)

SYSTEM = """
Eres analista de un canal de YouTube de documentales. Te paso un vídeo del canal con sus visitas frente a lo normal del
canal a la misma edad, los vídeos que más funcionan ahora en su nicho (con cuánto superan a su canal) y los otros vídeos
del canal. Explica por qué funcionó o no SOLO con lo que se puede comprobar en esos datos. Devuelve SOLO JSON:
{"topic": "¿cuántos ganadores del nicho tratan este tema? cita el mejor si lo hay",
 "title": "palabras del título frente a los ganadores; qué palabras o patrones funcionan en el nicho y en el canal",
 "length": "su duración frente a los aciertos del canal y a los ganadores del nicho",
 "hook": "cómo empieza el guion y si promete lo mismo que el título",
 "lesson": "UNA lección concreta para el próximo guion del canal (qué repetir o qué evitar)"}
Frases cortas, con cifras de los datos. Si un dato falta, dilo; no inventes.
""".strip()


def _read(path: Path) -> Any:
    try:
        return json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return None


def _write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def _ts(iso: str) -> float:
    return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).timestamp()


# --- curves -----------------------------------------------------------------------------------------------------

def due(entry: dict[str, Any], now: float) -> bool:
    """A checkpoint reached and not yet recorded (or a video never looked at)."""

    if not entry.get("published"):
        return True
    age = (now - _ts(entry["published"])) / 3600
    done = set(entry.get("done", []))
    return age <= CHECKPOINTS[-1] + 24 and any(h <= age and h not in done for h in CHECKPOINTS)


def snapshot(root: Path, now: float | None = None, api: Any = None) -> list[str]:
    """Record the views of the videos with a checkpoint due. Returns the slugs that just passed 48 h or 7 days."""

    from . import agenda

    now = now or time.time()
    curves = _read(root / CURVES) or {}
    for video in agenda.videos(root):
        vid = agenda._video_id(video.get("url") or "")
        if video.get("status") == "subido" and vid:
            entry = curves.setdefault(video["slug"], {"channel": video["channel"], "id": vid, "points": [], "done": []})
            entry["id"], entry["channel"] = vid, video["channel"]
    todo = {slug: e for slug, e in curves.items() if due(e, now)}
    if not todo:
        return []
    if api is None:
        from .context import RunContext
        from .ytapi import YouTubeAPI

        api = YouTubeAPI(RunContext.create("_porque", root=root))
        if not api.keys:
            return []
    stats = {v["id"]: v for v in api.videos(sorted({e["id"] for e in todo.values()}))}
    passed = []
    for slug, entry in todo.items():
        info = stats.get(entry["id"])
        if not info or not info.get("published"):
            continue
        entry["published"] = info["published"]
        entry["title"], entry["duration"] = info.get("title") or entry.get("title"), info.get("duration") or entry.get("duration")
        age = (now - _ts(info["published"])) / 3600
        new = [h for h in CHECKPOINTS if h <= age and h not in entry["done"]]
        if not new:
            continue
        entry["points"].append([round(age, 2), int(info.get("views") or 0)])
        entry["done"] = sorted({*entry["done"], *new})
        if any(h in ANALYSE_AT for h in new):
            passed.append(slug)
    _write(root / CURVES, curves)
    return passed


def views_at(points: list[list[float]], hours: float) -> float | None:
    """Views at that age, straight between the two points around it (None beyond the last one)."""

    pts = sorted(points)
    if not pts or hours > pts[-1][0] + 1e-6:
        return None
    before = [(0.0, 0.0), *[(h, v) for h, v in pts]]
    for (h0, v0), (h1, v1) in zip(before, before[1:]):
        if h0 <= hours <= h1:
            return v0 + (v1 - v0) * ((hours - h0) / (h1 - h0) if h1 > h0 else 1)
    return None


def _quantile(values: list[float], q: float) -> float:
    values = sorted(values)
    pos = (len(values) - 1) * q
    lo, hi = int(pos), min(len(values) - 1, int(pos) + 1)
    return values[lo] + (values[hi] - values[lo]) * (pos - lo)


def normal(curves: dict[str, Any], channel: str, exclude: str) -> list[dict[str, Any]]:
    """[{hours, median, low, high}] of the channel's other videos at each checkpoint (at least 2 videos)."""

    band = []
    for h in CHECKPOINTS:
        values = [v for slug, e in curves.items() if slug != exclude and e.get("channel") == channel
                  for v in [views_at(e.get("points") or [], h)] if v is not None]
        if len(values) >= 2:
            band.append({"hours": h, "median": round(statistics.median(values)), "low": round(_quantile(values, 0.25)),
                         "high": round(_quantile(values, 0.75)), "videos": len(values)})
    return band


def compare(curves: dict[str, Any], slug: str) -> dict[str, Any]:
    entry = curves.get(slug) or {}
    band = normal(curves, entry.get("channel"), slug)
    points = sorted(entry.get("points") or [])
    out: dict[str, Any] = {"points": points, "normal": band, "title": entry.get("title")}
    if points:
        age, views = points[-1]
        others = [v for other, e in curves.items() if other != slug and e.get("channel") == entry.get("channel")
                  for v in [views_at(e.get("points") or [], age)] if v is not None]
        usual = round(statistics.median(others)) if len(others) >= 2 else None
        if usual:
            out["ratio"] = round(views / usual, 2)
        out.update(age=age, views=views, usual=usual)
    return out


# --- why ----------------------------------------------------------------------------------------------------------

def _opening(root: Path, slug: str) -> str:
    from .web import find_video

    try:
        text = (find_video(root, slug) / "guion.txt").read_text("utf-8")
    except (OSError, FileNotFoundError):
        return ""
    text = re.sub(r"^##.*$", "", text, flags=re.M)
    return " ".join(re.split(r"(?<=[.!?])\s+", " ".join(text.split()))[:3])[:500]


def _age_words(hours: float) -> str:
    return f"{hours:.0f} h" if hours < 48 else f"{hours / 24:.0f} días"


def analyse(root: Path, slug: str) -> dict[str, Any]:
    from . import radar
    from .context import RunContext
    from .llm import complete_json

    curves = _read(root / CURVES) or {}
    entry = curves.get(slug)
    if not entry:
        raise ValueError("Ese vídeo aún no tiene visitas registradas (hace falta su enlace de YouTube)")
    data = compare(curves, slug)
    channel = entry["channel"]
    top = ((radar.latest(root) or {}).get("channels") or {}).get(channel, {}).get("top") or []
    winners = "\n".join(f"- x{v.get('ratio')} · {v.get('views')} visitas · {round((v.get('duration') or 0) / 60, 1)} min · «{v.get('title')}»"
                        for v in top[:15]) or "(sin radar hoy)"
    own = []
    for other, e in curves.items():
        if other != slug and e.get("channel") == channel and e.get("points"):
            c = compare(curves, other)
            own.append(f"- {c.get('ratio') or '?'}x lo normal · {round((e.get('duration') or 0) / 60, 1)} min · «{e.get('title')}»")
    verdict = ("funcionó" if (data.get("ratio") or 0) >= 1.3 else "no funcionó" if (data.get("ratio") or 1) <= 0.75 else "normal")
    ctx = RunContext.create("_porque", root=root, channel=channel)
    result = complete_json(
        ctx, stage="porque", section="planner", system=SYSTEM, max_tokens=1500,
        user=(f"VÍDEO: «{entry.get('title')}» · {round((entry.get('duration') or 0) / 60, 1)} min\n"
              f"VISITAS: {data.get('views')} a {_age_words(data.get('age') or 0)}; lo normal del canal a esa edad: "
              f"{data.get('usual') or 'sin datos'} ({data.get('ratio') or '?'}x) → {verdict}\n"
              f"ARRANQUE DEL GUION: {_opening(root, slug) or '(no disponible)'}\n\n"
              f"GANADORES DEL NICHO AHORA:\n{winners}\n\nOTROS VÍDEOS DEL CANAL:\n" + ("\n".join(own) or "(ninguno)")))
    report = {"slug": slug, "channel": channel, "verdict": verdict, "at": datetime.now().isoformat(timespec="seconds"),
              "age": data.get("age"), "views": data.get("views"), "usual": data.get("usual"), "ratio": data.get("ratio"),
              **{k: str(result.get(k) or "") for k in ("topic", "title", "length", "hook", "lesson")}}
    _write(root / FOLDER / f"{slug}.json", report)
    return report


def saved(root: Path, slug: str) -> dict[str, Any] | None:
    return _read(root / FOLDER / f"{slug}.json")


def lessons(root: Path, channel: str, count: int = 5) -> list[str]:
    """The latest lessons of the channel's videos, the clearest results first (for the next scripts)."""

    found = [r for r in (_read(p) for p in sorted((root / FOLDER).glob("*.json")) if p.name != CURVES.name)
             if isinstance(r, dict) and r.get("channel") == channel and r.get("lesson") and r.get("verdict") != "normal"]
    found.sort(key=lambda r: (-abs((r.get("ratio") or 1) - 1), r.get("at") or ""))
    return [f"{'✓' if r['verdict'] == 'funcionó' else '✗'} «{r.get('slug')}» ({r.get('ratio')}x): {r['lesson']}" for r in found[:count]]


def run(root: Path) -> None:
    """From the watcher: new points on the curves, and the analysis of the videos that just reached 48 h or 7 days."""

    for slug in snapshot(root):
        try:
            report = analyse(root, slug)
            print(f"Por qué · {slug}: {report['verdict']} ({report.get('ratio') or '?'}x) · {report['lesson'][:120]}")
        except Exception as error:
            print(f"Por qué · {slug}: {str(error)[:160]}")
