"""Where viewers leave, against the script and the picture: the audience retention curve that YouTube Studio exports
(Analytics → Advanced mode → the video → Audience retention → Export current view, CSV) for a published video,
matched with its own timeline (out/<slug>/... work/<slug>/timeline.json): at each steep drop, what the voice was saying
and what was on screen. Nothing is connected to the channel: you export the CSV and upload it in the studio.

out/<slug>/retencion.md (the report), work/<slug>/retencion.json (the numbers, for the channel's lessons), and
out/_retencion/<canal>.md: across the channel's analysed videos, which kinds of shot keep viewers and which lose them.
"""

from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path
from typing import Any

from .context import RunContext

WINDOW = 10.0            # seconds: a drop is measured over this long
TOP = 5


def _number(text: str) -> float | None:
    text = text.strip().replace("%", "").replace(" ", "")
    if re.fullmatch(r"\d{1,2}:\d{2}(:\d{2})?", text):
        parts = [int(p) for p in text.split(":")]
        return float(parts[0] * 60 + parts[1]) if len(parts) == 2 else float(parts[0] * 3600 + parts[1] * 60 + parts[2])
    text = text.replace(",", ".") if text.count(",") == 1 and "." not in text else text.replace(",", "")
    try:
        return float(text)
    except ValueError:
        return None


def parse(text: str, duration: float) -> list[tuple[float, float]]:
    """[(second of the video, % of viewers still watching)] from YouTube Studio's CSV (or any two-column table:
    position — a fraction, a percentage or a time — and retention in %)."""

    dialect = csv.Sniffer().sniff(text[:2000], delimiters=",;\t") if text.strip() else csv.excel
    rows = []
    for row in csv.reader(io.StringIO(text), dialect):
        numbers = [_number(c) for c in row]
        numbers = [n for n in numbers if n is not None]
        if len(numbers) >= 2:
            rows.append((numbers[0], numbers[1]))
    if len(rows) < 5:
        raise ValueError("No encuentro la curva en el archivo: exporta la retención de audiencia del vídeo (CSV)")
    positions = [p for p, _ in rows]
    top = max(positions)
    if top <= 1.0001:                                 # a fraction of the video
        seconds = [p * duration for p in positions]
    elif top <= 100.0001 and duration > 100:          # a percentage of the video
        seconds = [p / 100 * duration for p in positions]
    else:                                             # seconds (or a time already read as seconds)
        seconds = positions
    values = [r for _, r in rows]
    if max(values) <= 1.5:                           # a fraction of viewers
        values = [v * 100 for v in values]
    return sorted(zip(seconds, values))


def at(curve: list[tuple[float, float]], t: float) -> float:
    for (a, x), (b, y) in zip(curve, curve[1:]):
        if a <= t <= b:
            return x + (y - x) * (t - a) / max(1e-9, b - a)
    return curve[0][1] if t < curve[0][0] else curve[-1][1]


def _on_screen(timeline: dict[str, Any], a: float, b: float) -> tuple[str, str]:
    """What the voice says and what is on screen in [a, b] seconds of the video."""

    fps = timeline["fps"]
    said = [s["text"] for s in timeline["shots"] if s["from"] / fps < b and (s["from"] + s["durationInFrames"]) / fps > a and s.get("text")]
    seen: list[str] = []
    for g in timeline.get("groups", []):
        if g["from"] / fps < b and (g["from"] + g["durationInFrames"]) / fps > a:
            graphic = g.get("graphic") or {}
            if graphic.get("type") == "sim":
                scene = (graphic.get("params") or {}).get("scene")
                seen.append(f"simulación {graphic['world']}" + (f" · {scene}" if scene else "") + (f" · {graphic['overlay']}" if graphic.get("overlay") not in (None, "none") else ""))
            elif graphic.get("type"):
                seen.append(f"gráfico {graphic['type']}")
            elif g.get("kind"):
                seen.append(g["kind"])
    if not seen:
        for s in timeline["shots"]:
            if s["from"] / fps < b and (s["from"] + s["durationInFrames"]) / fps > a and s.get("media"):
                media = s["media"]
                seen.append(f"{media.get('kind', 'plano')} de {media.get('source') or (media.get('credit') or 'archivo')}")
    return " ".join(said)[:400], ", ".join(dict.fromkeys(seen))[:200] or "—"


def kind_of(timeline: dict[str, Any], t: float) -> str:
    """The kind of picture at second t (for the channel's lessons)."""

    fps = timeline["fps"]
    for g in timeline.get("groups", []):
        if g["from"] / fps <= t < (g["from"] + g["durationInFrames"]) / fps:
            graphic = g.get("graphic") or {}
            if graphic.get("type") == "sim":
                if graphic.get("list"):
                    return "resumen final"
                if graphic.get("replay"):
                    return "pausa y repetición"
                if graphic.get("rules"):
                    return "reglas"
                return f"simulación {graphic['world']}"
            if graphic.get("type"):
                return f"gráfico {graphic['type']}"
            return str(g.get("kind") or "panel")
    for s in timeline["shots"]:
        if s["from"] / fps <= t < (s["from"] + s["durationInFrames"]) / fps:
            if s.get("coldOpen"):
                return "apertura"
            media = s.get("media") or {}
            return f"metraje {media.get('source') or media.get('kind') or ''}".strip()
    return "otro"


def analyse(ctx: RunContext, text: str) -> dict[str, Any]:
    timeline = ctx.read_json("timeline.json")
    duration = timeline["durationInFrames"] / timeline["fps"]
    curve = parse(text, duration)
    hook = at(curve, 30)
    mean = sum(v for _, v in curve) / len(curve)
    drops = []
    t = 30.0
    while t + WINDOW < duration * 0.92:               # the very end (the end screen) always drops
        drops.append((at(curve, t) - at(curve, t + WINDOW), t))
        t += 2.0
    chosen: list[tuple[float, float]] = []
    for loss, start in sorted(drops, reverse=True):
        if loss <= 0.5 or len(chosen) >= TOP:
            break
        if all(abs(start - s) > WINDOW for _, s in chosen):
            chosen.append((loss, start))
    chosen.sort(key=lambda x: x[1])
    moments = []
    for loss, start in chosen:
        said, seen = _on_screen(timeline, start, start + WINDOW)
        moments.append({"at": round(start, 1), "loss": round(loss, 1), "said": said, "seen": seen})
    # rises: people going back to watch again (a strong moment)
    rises = []
    for (a, x), (b, y) in zip(curve, curve[1:]):
        if y - x > 1.0 and a > 15:
            said, seen = _on_screen(timeline, a - 3, b + 3)
            rises.append({"at": round(a, 1), "gain": round(y - x, 1), "said": said, "seen": seen})
    # how fast each kind of picture loses viewers (% per minute)
    kinds: dict[str, list[float]] = {}
    for (a, x), (b, y) in zip(curve, curve[1:]):
        if a < 30 or b > duration * 0.92 or b <= a:
            continue
        kinds.setdefault(kind_of(timeline, (a + b) / 2), []).append((x - y) / (b - a) * 60)
    per_kind = {k: round(sum(v) / len(v), 2) for k, v in kinds.items() if len(v) >= 3}
    result = {"slug": ctx.slug, "hook30": round(hook, 1), "mean": round(mean, 1), "duration": round(duration, 1),
              "drops": moments, "rises": sorted(rises, key=lambda r: -r["gain"])[:3], "perKind": per_kind}
    result["advice"] = advice(ctx, result)
    ctx.write_json("retencion.json", result)
    ctx.out_dir.mkdir(parents=True, exist_ok=True)
    (ctx.out_dir / "retencion.md").write_text(report(result), encoding="utf-8")
    channel = str(ctx.config.get("canal") or "")
    if channel:
        lessons(ctx.root, channel)
    return result


ADVICE = """
Eres analista de retención de YouTube. Te paso dónde se fue la gente en un vídeo (segundo, % perdido en 10 s, lo
que decía la voz y lo que se veía) y dónde volvió a verlo. Da 3-5 consejos CONCRETOS para el próximo guion de este
canal (qué cortar, qué adelantar, cómo enganchar en esos momentos), en español, de una frase cada uno, sin generalidades.
Devuelve SOLO JSON: {"tips": ["…"]}
""".strip()


def advice(ctx: RunContext, result: dict[str, Any]) -> list[str]:
    try:
        from .llm import complete_json

        answer = complete_json(ctx, stage="retencion", section="planner", system=ADVICE, max_tokens=900,
                               user=json.dumps({k: result[k] for k in ("hook30", "mean", "drops", "rises", "perKind")}, ensure_ascii=False))
        return [str(t)[:300] for t in answer.get("tips") or []][:5]
    except Exception as error:        # the numbers are there anyway
        print(f"   Retención: sin consejos ({str(error)[:100]})")
        return []


def _clock(s: float) -> str:
    return f"{int(s) // 60}:{int(s) % 60:02d}"


def report(r: dict[str, Any]) -> str:
    lines = [f"# Retención · {r['slug']}", "",
             f"- **A los 30 s sigue el {r['hook30']} %** de la gente (el gancho).",
             f"- Retención media: **{r['mean']} %** de un vídeo de {_clock(r['duration'])}.", ""]
    if r["drops"]:
        lines += ["## Dónde se va la gente", ""]
        for d in r["drops"]:
            lines += [f"**{_clock(d['at'])}** · se va un {d['loss']} % en 10 s", f"- Se dice: «{d['said']}»", f"- Se ve: {d['seen']}", ""]
    if r["rises"]:
        lines += ["## Dónde vuelven a verlo (lo más fuerte)", ""]
        for d in r["rises"]:
            lines += [f"**{_clock(d['at'])}** · +{d['gain']} % · «{d['said'][:160]}» · {d['seen']}", ""]
    if r["perKind"]:
        lines += ["## Lo que pierde gente más rápido (% por minuto)", ""]
        lines += [f"- {k}: {v}" for k, v in sorted(r["perKind"].items(), key=lambda kv: -kv[1])] + [""]
    if r.get("advice"):
        lines += ["## Para el próximo guion", ""] + [f"- {t}" for t in r["advice"]] + [""]
    return "\n".join(lines)


def lessons(root: Path, channel: str) -> Path | None:
    """Across the channel's analysed videos: the hook at 30 s and how fast each kind of picture loses viewers."""

    from .web import _channel_of
    from .context import video_folders

    rows = []
    for folder in video_folders(root):
        path = root / "work" / folder.name / "retencion.json"
        if path.is_file() and _channel_of(root, folder) == channel:
            rows.append(json.loads(path.read_text("utf-8")))
    if not rows:
        return None
    kinds: dict[str, list[float]] = {}
    for r in rows:
        for k, v in r.get("perKind", {}).items():
            kinds.setdefault(k, []).append(v)
    lines = [f"# Lo que aprende {channel} de su retención ({len(rows)} vídeos)", "",
             f"- Gancho medio (a los 30 s): **{sum(r['hook30'] for r in rows) / len(rows):.1f} %**",
             f"- Retención media: **{sum(r['mean'] for r in rows) / len(rows):.1f} %**", "",
             "## Qué pierde gente más rápido (% por minuto, media)", ""]
    lines += [f"- {k}: {sum(v) / len(v):.2f} ({len(v)} vídeos)" for k, v in sorted(kinds.items(), key=lambda kv: -sum(kv[1]) / len(kv[1]))]
    out = root / "out" / "_retencion" / f"{channel}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out
