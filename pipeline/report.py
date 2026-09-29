"""Morning report card: out/<slug>/resumen.md and the head of the "video ready" message.

At a glance, whether a video can go up as it is or needs a look:
- how much of the time the protagonist is on screen (clips/photos of them, athlete cards);
- how much is generic stock (Pexels) or generated;
- weak shots (low judge score or an unsure judge) with their minute;
- script facts the fact check marked as wrong.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .context import RunContext

STOCK = ("Pexels", "generadas")


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.lower()))


def card(ctx: RunContext) -> dict[str, Any]:
    manifest = json.loads((ctx.out_dir / "manifest.json").read_text("utf-8")).get("shots", [])
    qa = json.loads((ctx.out_dir / "qa" / "qa.json").read_text("utf-8"))
    subject = ""
    if (ctx.work_dir / "shots.json").is_file():
        subject = json.loads((ctx.work_dir / "shots.json").read_text("utf-8")).get("subject") or ""
    person = subject.split("·")[0].strip()
    name = _tokens(person)
    footage = [r for r in manifest if r.get("media")]
    total = sum(r["end"] - r["start"] for r in footage) or 1.0
    on_screen = sum(r["end"] - r["start"] for r in footage
                    if name and (name <= _tokens(f"{r.get('title') or ''} {r.get('channel') or ''} {r.get('caption') or ''}")
                                 or r.get("decidedBy") in ("people", "coldopen")))
    shares = qa.get("shareBySeconds", {})
    stock = sum(v for k, v in shares.items() if any(s.lower() in k.lower() for s in STOCK))
    wrong = []
    if (ctx.work_dir / "factcheck.json").is_file():
        claims = json.loads((ctx.work_dir / "factcheck.json").read_text("utf-8")).get("claims", [])
        wrong = [c for c in claims if c.get("verdict") == "wrong"]
    weak = qa.get("lowScore", [])
    cfg = ctx.section("report")
    problems = []
    if person and on_screen / total < float(cfg.get("min_protagonist", 0.5)):
        problems.append(f"{person} sale poco")
    if stock > float(cfg.get("max_stock", 0.1)):
        problems.append("mucho metraje genérico")
    if wrong:
        problems.append(f"{len(wrong)} dato(s) del guion a corregir")
    if len(weak) > int(cfg.get("max_weak", 15)):
        problems.append(f"{len(weak)} planos flojos")
    return {"person": person, "protagonist": on_screen / total, "stock": stock, "weak": weak, "wrong": wrong,
            "problems": problems}


def text(result: dict[str, Any], limit: int = 8) -> str:
    verdict = "✅ Listo para subir" if not result["problems"] else "⚠️ Revisar: " + "; ".join(result["problems"])
    lines = [verdict, ""]
    if result["person"]:            # rankings and topic videos have no protagonist
        lines.append(f"• {result['person']} en pantalla: {result['protagonist']:.0%} del tiempo")
    lines += [f"• Metraje genérico (stock): {result['stock']:.0%}",
             f"• Planos flojos: {len(result['weak'])}"]
    lines += [f"   – {w}" for w in result["weak"][:limit]]
    if len(result["weak"]) > limit:
        lines.append(f"   – … y {len(result['weak']) - limit} más (qa/report.md)")
    lines.append(f"• Datos marcados ❌ en la verificación: {len(result['wrong'])}")
    lines += [f"   – «{(c.get('quote') or c.get('claim') or '')[:110]}» → {(c.get('correction') or '?')[:160]}"
              for c in result["wrong"][:5]]
    return "\n".join(lines)


def write(ctx: RunContext) -> str:
    """Write out/<slug>/resumen.md and return the text for the message ('' if QA has not run)."""

    if not (ctx.out_dir / "manifest.json").is_file() or not (ctx.out_dir / "qa" / "qa.json").is_file():
        return ""
    body = text(card(ctx))
    (ctx.out_dir / "resumen.md").write_text(f"# Resumen · {ctx.slug}\n\n{body}\n", encoding="utf-8")
    return body
