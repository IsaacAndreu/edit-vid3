"""Official data behind the animated graphics: nothing wrong goes on screen in big numbers.

The graphics take their figures from the script (they must be said), so a wrong figure in the script
would also be a wrong podium, score or record on screen. Before the timeline places them:
1. a graphic over a passage the script's fact check already found WRONG is dropped;
2. every data graphic (podium, standings, score, card, records, charts, comparisons, spec sheets,
   timelines, receipts) is checked against Wikipedia (the fact check's articles) and a web search of
   its own, in one judged batch: "wrong" → dropped, "unverified" → kept and listed.
Result: work/<slug>/datacheck.json (reused while the graphics do not change) and
out/<slug>/datos-graficos.md; the QA lists the dropped ones.
"""

from __future__ import annotations

import hashlib
import json
import re
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import unquote

from .context import RunContext
from .llm import complete_json

STAGE = "datacheck"
OUTPUT = "datacheck.json"
REPORT = "datos-graficos.md"
DATA_TYPES = {"podium", "standings", "score", "card", "race", "scale", "chart", "compare", "specs", "timeline",
              "rank", "receipt"}

JUDGE_SYSTEM = """
Eres verificador de datos de gráficos de un documental. Cada gráfico muestra en pantalla unos datos (nombres,
cifras, años, puestos) que salen del guion. Decide SOLO con las pruebas que te paso (Wikipedia y búsquedas),
nunca con tu memoria, y SOLO sobre cifras, años, puestos y nombres (no sobre subtítulos o frases descriptivas):
- "ok": las pruebas confirman los datos del gráfico.
- "wrong": SOLO si una prueba da explícitamente OTRO valor para EXACTAMENTE el mismo dato (misma medida, misma
  competición, mismo periodo). Cita esa frase literal en "quote".
- "unverified": en cualquier otro caso. Si las pruebas hablan de una medida parecida pero distinta (títulos del
  concurso completo frente a oros en total, medallas de un aparato frente a totales, una temporada frente a la
  carrera), o no lo mencionan, es "unverified", NUNCA "wrong".
Devuelve SOLO JSON: {"results": [{"n": 1, "verdict": "ok|wrong|unverified", "quote": "frase literal de la prueba
si wrong, si no null", "correction": "qué está mal y el dato correcto, si wrong; si no null", "source": "URL de la
prueba o null"}]}
Escribe "correction" en el idioma del guion.
""".strip()


def _data(graphic: dict[str, Any]) -> dict[str, Any]:
    """The graphic without pictures or layout: what the viewer reads."""

    def clean(value: Any) -> Any:
        if isinstance(value, dict):
            return {k: clean(v) for k, v in value.items() if k not in ("media", "focus", "board", "flip") and v not in (None, "", [])}
        if isinstance(value, list):
            return [clean(v) for v in value]
        return value

    return clean(graphic)


def _names(graphic: dict[str, Any]) -> list[str]:
    found: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for k, v in value.items():
                if k in ("name", "title", "label") and isinstance(v, str):
                    found.append(v)
                else:
                    walk(v)
        elif isinstance(value, list):
            for v in value:
                walk(v)

    walk(graphic)
    return list(dict.fromkeys(found))[:4]


def _wrong_quotes(ctx: RunContext) -> list[dict[str, Any]]:
    path = ctx.work_dir / "factcheck.json"
    if not path.is_file():
        return []
    return [c for c in json.loads(path.read_text("utf-8")).get("claims", []) if c.get("verdict") == "wrong" and c.get("quote")]


def _overlaps(quote: str, passage: str) -> bool:
    a, b = quote.lower(), passage.lower()
    if a in b or b in a:
        return True
    match = SequenceMatcher(None, a, b).find_longest_match(0, len(a), 0, len(b))
    return match.size >= min(40, int(0.6 * len(a)))


def _in_evidence(quote: str, evidence: list[str]) -> bool:
    squash = lambda text: re.sub(r"\W+", " ", text.lower()).strip()  # noqa: E731
    wanted = squash(quote)
    return any(wanted in squash(block) for block in evidence)


def _articles(ctx: RunContext) -> list[str]:
    from .factcheck import wikipedia

    path = ctx.work_dir / "factcheck.json"
    urls = json.loads(path.read_text("utf-8")).get("articles", []) if path.is_file() else []
    texts = []
    for url in urls[:4]:
        found = re.match(r"https://(\w+)\.wikipedia\.org/wiki/(.+)", url)
        page = wikipedia(unquote(found.group(2)).replace("_", " "), found.group(1), 15000) if found else None
        if page:
            texts.append(f"### WIKIPEDIA: {page['title']} ({page['url']})\n{page['text']}")
    return texts


def check(ctx: RunContext, planned: list[dict[str, Any]], sents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Verdict per data graphic: [{"i", "type", "at", "data", "verdict", "correction", "source"}]."""

    from .factcheck import web_snippets

    items = []
    for i, item in enumerate(planned):
        graphic = item["graphic"]
        if graphic.get("type") not in DATA_TYPES:
            continue
        passage = " ".join(s["text"] for s in sents if s["end"] > item["start"] - 1 and s["start"] < item["end"] + 1)
        items.append({"i": i, "type": graphic["type"], "at": round(item["start"], 1), "data": _data(graphic), "passage": passage})
    if not items:
        return []
    signature = hashlib.sha256(json.dumps([[x["type"], x["data"]] for x in items], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    path = ctx.work_dir / OUTPUT
    if path.is_file():
        cached = json.loads(path.read_text("utf-8"))
        if cached.get("signature") == signature:
            return cached["results"]
    wrong = _wrong_quotes(ctx)
    evidence = _articles(ctx)
    for n, x in enumerate(items, 1):
        bad = next((c for c in wrong if _overlaps(str(c["quote"]), x["passage"])), None)
        if bad:
            x.update(verdict="wrong", correction=f"el guion aquí está mal según la verificación: {bad.get('correction') or bad['claim']}",
                     source=bad.get("source"))
            continue
        query = " ".join([*_names(x["data"]), *re.findall(r"\b(?:19|20)\d{2}\b", json.dumps(x["data"]))[:2]])[:120]
        found = web_snippets(ctx, query) if query.strip() else []
        evidence.append(f"### BÚSQUEDA para el gráfico {n}\n" + "\n".join(f"- {r['title']}: {r['snippet']} ({r['url']})" for r in found))
    pending = [(n, x) for n, x in enumerate(items, 1) if "verdict" not in x]
    if pending:
        listing = "\n".join(f"{n}. [{x['type']}] datos: {json.dumps(x['data'], ensure_ascii=False)} · guion: «{x['passage'][:300]}»"
                            for n, x in pending)
        try:
            judged = complete_json(ctx, stage=STAGE, section="factcheck", system=JUDGE_SYSTEM, max_tokens=4000,
                                   user=f"GRÁFICOS:\n{listing}\n\nPRUEBAS:\n" + "\n\n".join(evidence)[:120000])
        except Exception as error:  # a failed check keeps the graphics (they are what the script says)
            print(f"   Verificación de gráficos no disponible: {str(error)[:120]}")
            judged = {}
        verdicts = {int(r.get("n", 0)): r for r in judged.get("results", []) if isinstance(r, dict)}
        for n, x in pending:
            v = verdicts.get(n, {})
            verdict = v.get("verdict") if v.get("verdict") in ("ok", "wrong", "unverified") else "unverified"
            quote = str(v.get("quote") or "").strip()
            if verdict == "wrong" and (len(quote) < 12 or not _in_evidence(quote, evidence)):
                verdict = "unverified"                 # a "wrong" must quote the evidence, word for word
            x.update(verdict=verdict, correction=v.get("correction") if verdict != "ok" else None,
                     source=v.get("source"), quote=quote or None)
    results = [{k: x.get(k) for k in ("i", "type", "at", "data", "verdict", "correction", "source", "quote")} for x in items]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"signature": signature, "results": results}, ensure_ascii=False, indent=1), encoding="utf-8")
    return results


def _clock(seconds: float) -> str:
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}"


def report(ctx: RunContext, results: list[dict[str, Any]]) -> None:
    icon = {"ok": "✅", "wrong": "❌ quitado", "unverified": "❔"}
    lines = [f"# Datos de los gráficos · {ctx.slug}", "",
             f"{sum(r['verdict'] == 'ok' for r in results)} confirmados · {sum(r['verdict'] == 'wrong' for r in results)} "
             f"quitados por datos erróneos · {sum(r['verdict'] == 'unverified' for r in results)} sin confirmar", "",
             "| | Momento (voz) | Gráfico | Datos | Nota |", "|---|---|---|---|---|"]
    for r in results:
        data = json.dumps(r["data"], ensure_ascii=False)
        note = (r.get("correction") or "") + (f" — «{r['quote']}»" if r.get("quote") else "") + (f" ({r['source']})" if r.get("source") else "")
        lines.append(f"| {icon[r['verdict']]} | {_clock(r['at'])} | {r['type']} | {data[:160]} | {note[:220]} |")
    if any(r["verdict"] == "wrong" for r in results):
        lines += ["", "Un gráfico quitado sale de una frase del guion con un dato erróneo: corrige también la frase "
                      "(y la voz) si puedes."]
    ctx.out_dir.mkdir(parents=True, exist_ok=True)
    (ctx.out_dir / REPORT).write_text("\n".join(lines) + "\n", encoding="utf-8")


def filter_planned(ctx: RunContext, planned: list[dict[str, Any]], sents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The planned graphics minus the ones with wrong data (graphics.verify, on by default)."""

    if not ctx.section("graphics").get("verify", True) or not planned:
        return planned
    results = check(ctx, planned, sents)
    if not results:
        return planned
    report(ctx, results)
    dropped = {r["i"] for r in results if r["verdict"] == "wrong"}
    counts = {v: sum(r["verdict"] == v for r in results) for v in ("ok", "wrong", "unverified")}
    print(f"   Datos de gráficos: {counts['ok']} confirmados · {counts['wrong']} quitados · {counts['unverified']} sin confirmar")
    for r in results:
        if r["verdict"] == "wrong":
            print(f"   ✗ {r['type']} en {_clock(r['at'])}: {(r.get('correction') or '')[:140]}")
    return [item for i, item in enumerate(planned) if i not in dropped]
