"""Does the start of the script keep the title's promise? Checked BEFORE recording the voice.

«Los Fallos De Gimnasia Que SORPRENDIERON Al Mundo» lost a third of its audience by 0:30: the first 23 s were a
generic intro («La gimnasia es uno de los deportes más elegantes…»), the first story was not a fall, and the first
fall arrived at 2:07. The viewer clicked for falls and did not see one.

review(): the LLM reads the title and the numbered sentences and says what the title promises, in which sentence the
script first delivers it, whether the opening is generic, and proposes a ~15 s opening that starts with the strongest
moment (built only from facts already in the script). The seconds are estimated from the words
(`gancho.words_per_second`) or, with the voice already aligned, taken from it. Verdict: ✅ when the promise arrives
before `gancho.payoff_seconds` (20 s) and the opening is not generic.

Used by `python main.py --check <vídeo>` (→ out/<vídeo>/gancho.md) and by the studio («Revisar el gancho», on the
new-video page, with the script still pasted and no voice yet).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .context import RunContext
from .llm import complete_json

STAGE = "gancho"
OUTPUT = "gancho.md"

SYSTEM = """
Eres editor de guiones de YouTube y tu obsesión es la retención de los primeros 30 segundos. Te paso el TÍTULO del
vídeo y el guion en frases numeradas con el segundo aproximado en que se dice cada una.
Devuelve SOLO JSON:
{"promise": "qué espera ver quien hace clic en ese título, en 1 frase",
 "first_payoff": número de la PRIMERA frase que cumple esa promesa (que la cuenta o la enseña de verdad: el primer
                 fallo en un vídeo de fallos, el puesto 1 o el primero de la lista, el momento clave de la historia),
 "generic_opening": true si las primeras frases son una introducción genérica que podría ir en cualquier vídeo del tema
                    ("X es uno de los deportes más…", "hoy vamos a ver…", definiciones, contexto sin tensión),
 "strongest": número de la frase con el momento más impactante de todo el guion,
 "problems": ["problemas concretos del arranque, citando frases (máx. 4)"],
 "new_opening": "una apertura alternativa de 2-4 frases (~15 s de voz) que empiece POR el momento más fuerte o por la
                 promesa del título y deje una pregunta abierta. Usa SOLO hechos que ya están en el guion: ni cifras,
                 ni nombres, ni fechas nuevas.",
 "tips": ["1-3 cambios concretos para los primeros 30 s"],
 "topic_fit": "bien | dudoso | mal — SOLO si te paso LECCIONES DEL CANAL: si el tema, el ángulo y el título se parecen a lo
               que funcionó en el canal o a lo que fracasó (si no hay lecciones, \"\")",
 "topic_why": "por qué, citando la lección y su cifra (p. ej. «los vídeos de reglas y sanciones rinden 0.4x-0.6x»)",
 "titles": ["3 títulos alternativos con el patrón que SÍ funciona en el canal según las lecciones, usando solo hechos y
            nombres que están en el guion; si no hay lecciones, []"],
 "length_note": "si las lecciones dan una duración que funciona y el guion se aleja (te paso sus minutos), dilo; si no, \"\""}
""".strip()


def split_sentences(text: str) -> list[str]:
    text = re.sub(r"^\s*#+.*$", " ", text, flags=re.M)              # chapter headings are not narration
    parts = re.split(r"(?<=[.!?…])[»\"”']?\s+", " ".join(text.split()))
    return [p.strip() for p in parts if len(p.strip()) > 1]


def timed(sentences: list[str], words_per_second: float) -> list[dict[str, Any]]:
    out, clock = [], 0.0
    for n, sentence in enumerate(sentences):
        out.append({"n": n, "start": round(clock, 1), "text": sentence})
        clock += len(sentence.split()) / words_per_second
    return out


def review(ctx: RunContext, title: str, script: str, sents: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    cfg = ctx.section("gancho")
    sents = sents or timed(split_sentences(script), float(cfg.get("words_per_second", 2.6)))
    if len(sents) < 4:
        raise ValueError("El guion es demasiado corto para revisar el gancho")
    listing = "\n".join(f"[{s['n']}] ({s['start']:.0f}s) {s['text']}" for s in sents[:220])
    # what this channel's own uploads taught (pipeline/porque.py): the topic and the title judged against them too —
    # the scripts written elsewhere never saw them (atletismo: «trampas/escándalos 0.09x-0.61x, récord con nombre 1.41x»)
    from .porque import lessons

    learned = lessons(ctx.root, ctx.channel or "", int(cfg.get("lessons", 8))) if ctx.channel else []
    minutes = round(len(script.split()) / float(cfg.get("words_per_second", 2.6)) / 60, 1)
    extra = ("\n\nLECCIONES DEL CANAL (de sus vídeos subidos; ✓ funcionó, ✗ no):\n" + "\n".join(f"- {x}" for x in learned)
             + f"\n\nDURACIÓN DEL GUION: ~{minutes} min") if learned else ""
    result = complete_json(ctx, stage=STAGE, section="planner", max_tokens=3500, system=SYSTEM,
                           user=f"TÍTULO: {title}\n\nGUION:\n{listing}{extra}")

    def at(n: Any) -> float | None:
        try:
            return float(sents[int(n)]["start"])
        except (TypeError, ValueError, IndexError):
            return None

    payoff = at(result.get("first_payoff"))
    limit = float(cfg.get("payoff_seconds", 20))
    generic = bool(result.get("generic_opening"))
    late = payoff is None or payoff > limit
    if late:
        verdict = "❌ El título no se cumple hasta " + (f"el segundo {payoff:.0f}" if payoff is not None else "muy tarde")
    elif generic:
        verdict = "⚠️ Arranque genérico: la promesa llega a tiempo, pero las primeras frases no enganchan"
    else:
        verdict = "✅ El arranque cumple el título"
    sentence = lambda n: sents[int(n)]["text"] if at(n) is not None else ""   # noqa: E731
    return {
        "title": title, "verdict": verdict, "ok": not late and not generic, "promise": str(result.get("promise") or ""),
        "payoffSeconds": payoff, "payoffSentence": sentence(result.get("first_payoff")), "limit": limit,
        "generic": generic, "strongestSeconds": at(result.get("strongest")),
        "strongestSentence": sentence(result.get("strongest")),
        "problems": [str(p) for p in result.get("problems") or []][:4],
        "newOpening": str(result.get("new_opening") or ""), "tips": [str(t) for t in result.get("tips") or []][:3],
        "opening": " ".join(s["text"] for s in sents[:4]),
        "topicFit": str(result.get("topic_fit") or "") if learned else "", "topicWhy": str(result.get("topic_why") or "") if learned else "",
        "titles": [str(t) for t in result.get("titles") or []][:3] if learned else [],
        "lengthNote": str(result.get("length_note") or "") if learned else "", "minutes": minutes,
    }


def markdown(r: dict[str, Any]) -> str:
    lines = [f"# Gancho · {r['title']}", "", f"**{r['verdict']}**", "", f"**Lo que promete el título:** {r['promise']}", ""]
    if r["payoffSeconds"] is not None:
        lines += [f"**Primera vez que se cumple (≈{r['payoffSeconds']:.0f} s):** «{r['payoffSentence']}»", ""]
    if r["strongestSentence"]:
        lines += [f"**Momento más fuerte del guion (≈{r['strongestSeconds']:.0f} s):** «{r['strongestSentence']}»", ""]
    lines += [f"**Cómo empieza ahora:** «{r['opening'][:400]}»", ""]
    if r["problems"]:
        lines += ["## Problemas", ""] + [f"- {p}" for p in r["problems"]] + [""]
    if r["newOpening"]:
        lines += ["## Apertura propuesta (~15 s)", "", f"> {r['newOpening']}", "",
                  "_Solo usa hechos que ya están en tu guion: el vídeo empieza directamente con la voz._", ""]
    if r["tips"]:
        lines += ["## Cambios para los primeros 30 s", ""] + [f"- {t}" for t in r["tips"]] + [""]
    if r.get("topicFit"):
        icon = {"bien": "✅", "dudoso": "🟡", "mal": "🔴"}.get(r["topicFit"], "•")
        lines += ["## El tema y el título frente a lo que funciona en el canal", "", f"{icon} {r['topicWhy']}", ""]
        if r.get("lengthNote"):
            lines += [f"- Duración (~{r['minutes']} min): {r['lengthNote']}", ""]
        if r.get("titles"):
            lines += ["**Títulos con el patrón que funciona:**", ""] + [f"- {t}" for t in r["titles"]] + [""]
    return "\n".join(lines)


def title_of(ctx: RunContext) -> str:
    path = ctx.materials_dir / "titulo.txt"
    return path.read_text("utf-8").strip() if path.is_file() else ctx.slug


def run(ctx: RunContext) -> Path:
    """--check: the hook of materiales/<vídeo>/guion.txt (with the aligned voice's times when there are some)."""

    sents = None
    words = ctx.work_dir / "words.json"
    if words.is_file():
        from .shorts import sentences

        sents = [{"n": s["n"], "start": s["start"], "text": s["text"]}
                 for s in sentences(json.loads(words.read_text("utf-8"))["words"])]
    result = review(ctx, title_of(ctx), (ctx.materials_dir / "guion.txt").read_text("utf-8"), sents)
    ctx.out_dir.mkdir(parents=True, exist_ok=True)
    path = ctx.out_dir / OUTPUT
    path.write_text(markdown(result), encoding="utf-8")
    return path
