"""out/<vídeo>/qa/planos.html: cada plano en una fila — cuándo sale, qué dice la voz, un fotograma, de dónde viene
(título, canal, enlace con el segundo exacto), quién lo eligió y por qué (la nota y la razón del juez, el vídeo maestro
del suceso, el motivo del relleno) y lo que dijo la revisión final. Un archivo solo, con las imágenes dentro: se abre
en el navegador o desde «Archivos» del estudio, y en un minuto se ve por qué salió cada imagen.
"""

from __future__ import annotations

import base64
import html
from pathlib import Path
from typing import Any

import cv2

DECIDED = {"judge": "juez", "score": "nota", "editor": "a mano", "people": "tarjeta de persona", "coldopen": "apertura"}
REVIEW = {"persona": "Otra persona", "suceso": "Otro suceso", "tema": "Fuera de tema", "texto": "Texto encima",
          "calidad": "Calidad"}


def _thumb(frame: Any) -> str:
    if frame is None:
        return ""
    small = cv2.resize(frame, (256, 144), interpolation=cv2.INTER_AREA)
    ok, data = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 70])
    return f'<img src="data:image/jpeg;base64,{base64.b64encode(data.tobytes()).decode()}" alt="">' if ok else ""


def _link(row: dict[str, Any]) -> str:
    url = row.get("url") or ""
    if not url:
        return ""
    start = row.get("sourceStart")
    if start is not None and ("youtube.com" in url or "youtu.be" in url):
        url += ("&" if "?" in url else "?") + f"t={int(float(start))}"
    title = row.get("title") or url
    return f'<a href="{html.escape(url)}" target="_blank" rel="noopener">{html.escape(str(title)[:90])}</a>'


def write(path: Path, slug: str, rows: list[dict[str, Any]]) -> Path:
    from .qa import mmss

    body = []
    for row in rows:
        if not row.get("media") and row.get("type") != "broll":
            continue
        decided = str(row.get("decidedBy") or "—")
        why = []
        judge = row.get("judge") or {}
        if judge:
            why.append(f"juez {judge.get('score', 0):.2f} (seguro {judge.get('confidence', 0):.0%}): {judge.get('reason', '')}")
        elif row.get("score") is not None:
            why.append(f"nota {float(row['score']):.2f}")
        if row.get("master"):
            why.append("<b>vídeo maestro del suceso</b>")
        if row.get("fallbackReason"):
            why.append(f"relleno: {row['fallbackReason']}")
        review = row.get("review")
        flag = (f'<div class="flag">⚠ {REVIEW.get(review.get("kind"), review.get("kind"))}: {html.escape(review.get("reason", ""))}</div>'
                if review else "")
        source = " · ".join(x for x in [_link(row), html.escape(str(row.get("channel") or "")),
                                        html.escape(str(row.get("credit") or "")) if not row.get("url") else ""] if x)
        body.append(
            f'<tr class="{"bad" if review else ""}"><td class="t">{mmss(row["start"])}<br><small>{row["shotId"]}</small></td>'
            f'<td>{_thumb(row.get("_frame"))}</td>'
            f'<td>«{html.escape(row.get("text") or "")}»{flag}</td>'
            f'<td>{source or "—"}<br><small>{html.escape(DECIDED.get(decided, decided))}</small></td>'
            f'<td><small>{"<br>".join(w if w.startswith("<b>") else html.escape(w) for w in why)}</small></td></tr>')
    flagged = sum(1 for r in rows if r.get("review"))
    page = f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Planos · {html.escape(slug)}</title><style>
body{{font-family:system-ui,sans-serif;margin:16px;background:#111;color:#eee}} h1{{font-size:20px}}
table{{border-collapse:collapse;width:100%}} td{{border-top:1px solid #333;padding:8px;vertical-align:top;font-size:14px}}
td.t{{white-space:nowrap;color:#aaa}} img{{width:256px;border-radius:4px;display:block}} a{{color:#7cc4ff}}
tr.bad td{{background:#2a1515}} .flag{{color:#ff8a80;margin-top:6px;font-weight:600}} small{{color:#999}}
</style></head><body><h1>{html.escape(slug)} · {len(body)} planos · {flagged} a revisar</h1>
<table>{''.join(body)}</table></body></html>"""
    path.write_text(page, encoding="utf-8")
    return path
