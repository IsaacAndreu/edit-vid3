"""Judge the sheets a video already has with another model, and compare the verdicts — to choose the judge's model
with data instead of by price alone:

    python -m pipeline.rejuzgar <vídeo> <modelo> [máx. hojas]      (40 by default)

It reads work/<vídeo>/judge/<plano>.jpg and the .json saved next to each one (what was asked and answered; sheets
judged before 11-2026 have none and are skipped), asks `<modelo>` with the same instructions, and writes
out/<vídeo>/rejuzgar-<modelo>.md: how often both accept the same first choice, accept/reject anything, and what it cost.
Answers are cached as usual (cache/judge/): running it again costs nothing.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import cv2

from .context import PROJECT_ROOT, RunContext


def compare(old: dict[str, Any], new: dict[str, Any]) -> dict[str, bool]:
    a, b = list(old.get("ranking") or []), list(new.get("ranking") or [])
    return {"sameFirst": bool(a and b and a[0] == b[0]), "bothReject": not a and not b,
            "onlyOldAccepts": bool(a) and not b, "onlyNewAccepts": not a and bool(b),
            "sameSet": set(a) == set(b)}


def run(root: Path, slug: str, model: str, limit: int = 40) -> dict[str, Any]:
    from . import judge
    from .schemas import ShotsFile

    ctx = RunContext.create(slug, root=root)
    ctx.config.setdefault("judge", {})["_model_override"] = model
    shots = {s.id: s for s in ShotsFile.model_validate(ctx.read_json("shots.json")).shots}
    rows = []
    for context_path in sorted((ctx.work_dir / "judge").glob("*.json"))[:limit]:
        try:
            saved = json.loads(context_path.read_text("utf-8"))
        except (OSError, ValueError):
            continue
        shot = shots.get(str(saved.get("shotId")))
        sheet = cv2.imread(str(context_path.with_suffix(".jpg")))
        if shot is None or sheet is None:
            continue
        verdict = judge.call_judge(ctx, shot, sheet, str(saved["letters"]), str(saved.get("topic") or ""),
                                   bool(saved.get("hook")), str(saved.get("subject") or ""), str(saved.get("sources") or ""))
        rows.append({"sheet": context_path.stem, "old": saved.get("verdict") or {}, "new": verdict,
                     **compare(saved.get("verdict") or {}, verdict)})
    spent = sum(float(e.get("usd") or 0) for e in ((ctx.read_json("costs.json").get("entries") or [])
                                                    if (ctx.work_dir / "costs.json").is_file() else [])
                if e.get("operation") == model and e.get("stage") == judge.STAGE)
    return {"slug": slug, "model": model, "rows": rows, "usd": round(spent, 3)}


def markdown(data: dict[str, Any]) -> str:
    rows = data["rows"]
    n = len(rows) or 1
    share = lambda key: f"{100 * sum(r[key] for r in rows) / n:.0f} %"      # noqa: E731
    lines = [f"# Rejuzgar {data['slug']} con {data['model']}", "",
             f"{len(rows)} hojas · gasto acumulado de ese modelo en este vídeo: {data['usd']:.3f} $", "",
             f"- Misma primera elección: {share('sameFirst')}",
             f"- Mismas opciones aceptadas: {share('sameSet')}",
             f"- Los dos lo rechazan todo: {share('bothReject')}",
             f"- Solo el modelo de antes acepta algo: {share('onlyOldAccepts')}",
             f"- Solo {data['model']} acepta algo: {share('onlyNewAccepts')}", "",
             "| Hoja | Antes | Ahora |", "|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['sheet']} | {''.join(r['old'].get('ranking') or []) or '—'} | "
                     f"{''.join(r['new'].get('ranking') or []) or '—'} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit("Uso: python -m pipeline.rejuzgar <vídeo> <modelo> [máx. hojas]")
    result = run(PROJECT_ROOT, sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 40)
    text = markdown(result)
    out = PROJECT_ROOT / "out" / sys.argv[1] / f"rejuzgar-{sys.argv[2]}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(text)
