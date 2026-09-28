"""Fact check of the script: out/<slug>/verificacion.md with every checkable claim and a verdict.

Best run BEFORE recording the voice (`python main.py --check <slug>` only needs guion.txt), since a
wrong date found after recording means recording again. It also runs as a stage of the pipeline.

1. The LLM lists the verifiable claims of the script (dates, results, ages, records, quotes…),
   each with a web search query, plus the Wikipedia pages of the people involved.
2. Evidence: those Wikipedia articles (script language + English) and web search snippets
   (Serper if SERPER_API_KEY, else DuckDuckGo) for each claim.
3. The LLM judges each claim ONLY against that evidence: ok / wrong (with the correction and the
   source) / unverified (the evidence does not say — check it yourself).
It never blocks the video unless `factcheck.block_on_wrong: true`.
"""

from __future__ import annotations

import json
from typing import Any

import requests

from .context import RunContext
from .llm import complete_json

STAGE = "factcheck"
OUTPUT = "factcheck.json"
REPORT = "verificacion.md"
USER_AGENT = "edit-vid3-factcheck/1.0 (documentary fact checking)"

EXTRACT_SYSTEM = """
Eres verificador de datos de documentales deportivos. Del guion, lista las afirmaciones
COMPROBABLES: fechas, años, edades, resultados, puntuaciones, puestos, medallas, récords, lugares,
nombres de competiciones, cifras y citas atribuidas a alguien. No listes opiniones ni frases
dramáticas sin datos. Máximo 25, las más importantes primero. Devuelve SOLO JSON:
{"people": ["nombres completos de las personas principales"],
 "wikipedia": ["títulos exactos de artículos de Wikipedia EN INGLÉS de esas personas/eventos (máx. 4)"],
 "claims": [{"quote": "fragmento literal del guion", "claim": "la afirmación en una frase autónoma",
             "query": "búsqueda web EN INGLÉS para comprobarla"}]}
""".strip()

JUDGE_SYSTEM = """
Eres verificador de datos. Para cada afirmación decide SOLO con las pruebas que te paso
(artículos de Wikipedia y resultados de búsqueda), nunca con tu memoria:
- "ok": las pruebas lo confirman.
- "wrong": las pruebas lo contradicen claramente. Da la corrección.
- "unverified": las pruebas no lo mencionan o son ambiguas.
Devuelve SOLO JSON: {"results": [{"n": 1, "verdict": "ok|wrong|unverified",
  "correction": "dato correcto si wrong, si no null", "evidence": "frase breve de la prueba",
  "source": "URL de la prueba o null"}]}
Escribe "correction" y "evidence" en el idioma del guion.
""".strip()


def wikipedia(title: str, lang: str, limit: int = 25000, session: Any = None) -> dict[str, str] | None:
    """Plain text of a Wikipedia article (follows redirects), or None."""

    session = session or requests
    try:
        response = session.get(f"https://{lang}.wikipedia.org/w/api.php", timeout=30, headers={"User-Agent": USER_AGENT},
                               params={"action": "query", "prop": "extracts", "explaintext": 1, "redirects": 1,
                                       "titles": title, "format": "json", "formatversion": 2})
        pages = response.json().get("query", {}).get("pages", [])
    except (requests.RequestException, ValueError):
        return None
    page = next((p for p in pages if p.get("extract")), None)
    if not page:
        return None
    url = f"https://{lang}.wikipedia.org/wiki/{page['title'].replace(' ', '_')}"
    return {"title": page["title"], "url": url, "text": page["extract"][:limit]}


def interlanguage(title: str, lang: str, session: Any = None) -> str | None:
    """The title of the same article in another language (en → es)."""

    session = session or requests
    try:
        response = session.get("https://en.wikipedia.org/w/api.php", timeout=30, headers={"User-Agent": USER_AGENT},
                               params={"action": "query", "prop": "langlinks", "lllang": lang, "redirects": 1,
                                       "titles": title, "format": "json", "formatversion": 2})
        for page in response.json().get("query", {}).get("pages", []):
            for link in page.get("langlinks", []):
                return link.get("title")
    except (requests.RequestException, ValueError):
        return None
    return None


def web_snippets(ctx: RunContext, query: str, count: int = 5) -> list[dict[str, str]]:
    """Title, snippet and URL of the first web results (Serper, else DuckDuckGo)."""

    serper = ctx.env("SERPER_API_KEY", required=False)
    try:
        if serper:
            response = requests.post("https://google.serper.dev/search", json={"q": query, "num": count},
                                     headers={"X-API-KEY": serper}, timeout=30)
            response.raise_for_status()
            return [{"title": r.get("title", ""), "snippet": r.get("snippet", ""), "url": r.get("link", "")}
                    for r in response.json().get("organic", [])[:count]]
        from ddgs import DDGS

        return [{"title": r.get("title", ""), "snippet": r.get("body", ""), "url": r.get("href", "")}
                for r in DDGS().text(query, max_results=count)]
    except Exception as error:  # evidence is best effort: an unverified claim is still reported
        print(f"   búsqueda «{query[:60]}»: {type(error).__name__}")
        return []


def inputs(ctx: RunContext) -> list:
    return [ctx.materials_dir / "guion.txt"]


def check(ctx: RunContext) -> dict[str, Any]:
    script = (ctx.materials_dir / "guion.txt").read_text("utf-8")
    lang = str(ctx.section("align").get("language", "es"))
    listed = complete_json(ctx, stage=STAGE, section="factcheck", system=EXTRACT_SYSTEM, max_tokens=4000,
                           user=f"GUION:\n{script[:30000]}")
    claims = [c for c in listed.get("claims", []) if isinstance(c, dict) and c.get("claim")][:25]
    articles = []
    for title in [str(t) for t in listed.get("wikipedia", [])][:4]:
        for page in (wikipedia(title, "en", 20000),
                     wikipedia(local, lang, 12000) if lang != "en" and (local := interlanguage(title, lang)) else None):
            if page and page["url"] not in {a["url"] for a in articles}:
                articles.append(page)
    print(f"   {len(claims)} afirmaciones · {len(articles)} artículos de Wikipedia")
    evidence = [f"### WIKIPEDIA: {a['title']} ({a['url']})\n{a['text']}" for a in articles]
    for n, claim in enumerate(claims, 1):
        found = web_snippets(ctx, str(claim.get("query") or claim["claim"]))
        claim["web"] = found
        evidence.append(f"### BÚSQUEDA para la afirmación {n}\n" + "\n".join(
            f"- {r['title']}: {r['snippet']} ({r['url']})" for r in found))
    listing = "\n".join(f"{n}. {c['claim']}" for n, c in enumerate(claims, 1))
    judged = complete_json(ctx, stage=STAGE, section="factcheck", system=JUDGE_SYSTEM, max_tokens=6000,
                           user=f"AFIRMACIONES:\n{listing}\n\nPRUEBAS:\n" + "\n\n".join(evidence)[:120000]) if claims else {}
    verdicts = {int(r.get("n", 0)): r for r in judged.get("results", []) if isinstance(r, dict)}
    results = []
    for n, claim in enumerate(claims, 1):
        verdict = verdicts.get(n, {})
        results.append({"n": n, "quote": claim.get("quote", ""), "claim": claim["claim"],
                        "verdict": verdict.get("verdict") if verdict.get("verdict") in ("ok", "wrong", "unverified") else "unverified",
                        "correction": verdict.get("correction"), "evidence": verdict.get("evidence"),
                        "source": verdict.get("source")})
    return {"people": listed.get("people", []), "articles": [a["url"] for a in articles], "claims": results}


def report(result: dict[str, Any]) -> str:
    claims = result["claims"]
    count = {v: sum(1 for c in claims if c["verdict"] == v) for v in ("wrong", "unverified", "ok")}
    lines = ["# Verificación del guion", ""]
    if result.get("error"):
        lines += [f"No se pudo verificar ({result['error']}). Repite con `python main.py --check <vídeo>`.", ""]
    lines += [
             f"❌ {count['wrong']} a corregir · ⚠️ {count['unverified']} sin confirmar · ✅ {count['ok']} confirmadas", "",
             "Revisado solo contra Wikipedia y resultados de búsqueda: «sin confirmar» no significa que esté mal, "
             "sino que conviene comprobarlo a mano.", ""]
    for verdict, heading in (("wrong", "## ❌ A corregir"), ("unverified", "## ⚠️ Sin confirmar"), ("ok", "## ✅ Confirmadas")):
        items = [c for c in claims if c["verdict"] == verdict]
        if not items:
            continue
        lines += [heading, ""]
        for c in items:
            lines.append(f"- **«{c['quote'] or c['claim']}»**")
            if c.get("correction"):
                lines.append(f"  - Correcto: {c['correction']}")
            if c.get("evidence"):
                lines.append(f"  - Prueba: {c['evidence']}")
            if c.get("source"):
                lines.append(f"  - Fuente: {c['source']}")
        lines.append("")
    if result.get("articles"):
        lines += ["## Artículos consultados", ""] + [f"- {u}" for u in result["articles"]]
    return "\n".join(lines) + "\n"


def run(ctx: RunContext) -> None:
    try:
        result = check(ctx)
    except Exception as error:  # the check must never cost the night's video
        print(f"   Verificación no disponible: {type(error).__name__}: {str(error)[:150]}")
        result = {"people": [], "articles": [], "claims": [], "error": str(error)[:300]}
    ctx.write_json(OUTPUT, result)
    ctx.out_dir.mkdir(parents=True, exist_ok=True)
    (ctx.out_dir / REPORT).write_text(report(result), encoding="utf-8")
    wrong = [c for c in result["claims"] if c["verdict"] == "wrong"]
    print(f"   {len(wrong)} datos a corregir · informe en {ctx.out_dir / REPORT}")
    if wrong and ctx.section("factcheck").get("block_on_wrong", False):
        raise RuntimeError(f"{len(wrong)} datos del guion parecen incorrectos: revisa {ctx.out_dir / REPORT}")


def validate(ctx: RunContext) -> bool:
    return (ctx.work_dir / OUTPUT).is_file() and (ctx.out_dir / REPORT).is_file()


def summary(ctx: RunContext) -> str:
    """One line for the final message, e.g. '❌ 2 datos a corregir · ⚠️ 5 sin confirmar'."""

    path = ctx.work_dir / OUTPUT
    if not path.is_file():
        return ""
    claims = json.loads(path.read_text("utf-8")).get("claims", [])
    wrong = sum(1 for c in claims if c["verdict"] == "wrong")
    unverified = sum(1 for c in claims if c["verdict"] == "unverified")
    return f"Verificación del guion: ❌ {wrong} a corregir · ⚠️ {unverified} sin confirmar (verificacion.md)"
