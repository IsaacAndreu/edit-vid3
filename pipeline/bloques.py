"""«Material primero», stage 2: the script comes out of the case file, as a list of blocks.

One call to the script model writes the video as blocks, not as running text:
- narrador: what the voice says. Every fact it states points to the segment of the case file it comes from; what is
  not in the case file is not stated (a sentence with a figure or a date and no segment behind it is dropped);
- declaracion: a person speaking — the source, the exact seconds, the sentence (always re-read from the case file,
  never the model's words) and its translation; who speaks comes from the case file too, never from the model;
- secuencia: footage with its own ambient sound under the voice — source and seconds (within the channel's cap);
- tarjeta: number and title of the entry, a person card, a date, a map.

The model is told what each block is for and what makes this format good (whoever was there is seen and heard; the
narrator only links), not given a rigid template. A top's order must be justified by a fact of the case file (length,
speed, damage), said in the narration. The hook is stage 4: not here.

The owner sees the blocks in the studio before any money goes to voice and downloads, and can remove or change
statements (`edit`). The page also shows what the downloads would cost through the proxy.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable

OUTPUT = "bloques.json"
WORDS_PER_SECOND = 2.5                 # a calm narration
MB_PER_SECOND = 0.35                   # 720p30 with its sound, what a statement or a sequence is downloaded at

SYSTEM = """
Escribes el guion de un vídeo de YouTube en español, tipo «{kind}», tono «{tone}», unos {minutes} minutos, a partir de
un EXPEDIENTE con el material real que existe: por cada {unit}, sus fuentes y sus tramos (cada uno con un id).

Qué hace bueno a este formato: se VE y se OYE a quien estuvo allí (la periodista que lo dio, el agente, una vecina) y
el suceso mismo grabado; el narrador solo une, da contexto y los datos. Planos largos de una misma fuente, no cortes
cada pocos segundos. Todo lo que se ve es de ESE suceso.

Escribe el vídeo como una lista de BLOQUES:
- {{"type": "tarjeta", "item": n, "number": n, "title": "nombre del caso"}}: abre cada {unit_one} (en un top, con su número);
- {{"type": "narrador", "text": "lo que dice la voz", "refs": ["id", ...]}}: cada dato que afirmes (cifra, fecha, lugar,
  nombre, lo que pasó) lleva los ids de los tramos de donde sale. Si no está en el expediente, NO lo digas. Frases
  cortas, para el oído;
- {{"type": "declaracion", "ref": "id", "translation": "la frase en español si la fuente está en otro idioma"}}: una persona
  hablando, con su voz (solo tramos de tipo declaracion);
- {{"type": "secuencia", "ref": "id", "start": s, "end": s}}: el suceso grabado, con su sonido bajo la voz (segundos dentro
  del tramo; de 6 a {cap} segundos).
{order_rule}
{structure}
Devuelve SOLO JSON: {{"criterion": "el criterio del orden, dicho con un dato", "criterion_refs": ["id"],
"blocks": [ ... en el orden en que se ven ... ]}}
""".strip()

STRUCTURES = {
    "top": "Estructura: cada puesto abre con su tarjeta; dentro, el suceso grabado con la voz encima, una o dos personas "
           "que estuvieron allí, y más metraje; de 50 a 75 segundos por puesto. El número 1 al final.",
    "noticia": "Estructura de NOTICIA: qué ha pasado (lo grabado, en los primeros segundos), quién y dónde, el contexto que "
               "hace falta para entenderlo, las reacciones (los testimonios), y qué pasa ahora. Tarjetas solo para separar "
               "partes (sin número), una ficha de persona si alguien es clave.",
    "documental": "Estructura de DOCUMENTAL: capítulos con su tarjeta (título, sin número de puesto); dentro de cada uno, los "
                  "hechos en orden, con quienes los vivieron contándolos; el narrador da el contexto y las fechas.",
}

ORDER_RULE = ("El ORDEN del top tiene que poder justificarse con un dato del expediente (duración, velocidad, daños, "
              "kilómetros): elige el criterio, ordena por él (del puesto más bajo al número 1) y dilo en la narración.")


def segment_index(expediente: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Every segment of the case file by a short id: t1, t2… with its source and entry."""

    out: dict[str, dict[str, Any]] = {}
    n = 0
    for item in expediente.get("items") or []:
        for src in item.get("sources") or []:
            for seg in src.get("segments") or []:
                n += 1
                out[f"t{n}"] = {**seg, "id": f"t{n}", "item": item["n"], "source": src["id"], "url": src.get("url"),
                                "channel": src.get("channel"), "lang": src.get("subtitles")}
    return out


def listing(expediente: dict[str, Any], index: dict[str, dict[str, Any]]) -> str:
    """The case file as the model reads it: entries, sources and their segments with ids."""

    by_item: dict[int, list[dict[str, Any]]] = {}
    for seg in index.values():
        by_item.setdefault(seg["item"], []).append(seg)
    lines = []
    for item in expediente.get("items") or []:
        lines.append(f"\n## {item['n']}. {item['name']} ({item.get('whereWhen') or ''})")
        for seg in by_item.get(item["n"], []):
            who = seg.get("speaker") or {}
            speaker = f" · habla: {who.get('name') or who.get('role')}" if who else ""
            lines.append(f"[{seg['id']}] {seg['type']} {seg['start']:.0f}-{seg['end']:.0f}s ({seg.get('channel')}, "
                         f"{seg.get('lang') or '?'}){speaker} · se ve: {seg.get('seen') or '-'}"
                         + (f" · dato: {seg['fact']}" if seg.get("fact") else "")
                         + (f" · dice: «{str(seg.get('said') or '')[:300]}»" if seg.get("said") else ""))
    return "\n".join(lines)


def check(raw: dict[str, Any], index: dict[str, dict[str, Any]], cap: float, kind: str = "top") -> dict[str, Any]:
    """The model's blocks, made safe: refs that exist, statements re-read from the case file with their speaker from
    it, sequences inside their segment and under the cap, narration without a source dropped when it states a fact."""

    blocks, notes = [], []
    for raw_block in raw.get("blocks") or []:
        if not isinstance(raw_block, dict):
            continue
        kind_ = raw_block.get("type")
        if kind_ == "tarjeta":
            blocks.append({"type": "tarjeta", "item": raw_block.get("item"), "number": raw_block.get("number"),
                           "title": " ".join(str(raw_block.get("title") or "").split())[:80]})
        elif kind_ == "narrador":
            text = " ".join(str(raw_block.get("text") or "").split())[:600]
            refs = [r for r in raw_block.get("refs") or [] if r in index]
            if not text:
                continue
            if not refs and re.search(r"\d", text):
                notes.append(f"quitada una frase sin fuente: «{text[:90]}»")
                continue
            blocks.append({"type": "narrador", "text": text, "refs": refs, "connector": not refs})
        elif kind_ == "declaracion":
            seg = index.get(str(raw_block.get("ref") or ""))
            if seg is None or seg["type"] != "declaracion" or not seg.get("said"):
                notes.append(f"quitada una declaración que no está en el expediente ({raw_block.get('ref')})")
                continue
            who = seg.get("speaker") or {}
            blocks.append({"type": "declaracion", "ref": seg["id"], "source": seg["source"], "url": seg.get("url"),
                           "channel": seg.get("channel"), "start": seg["start"], "end": min(seg["end"], seg["start"] + cap),
                           "said": seg["said"], "lang": seg.get("lang"),
                           "translation": " ".join(str(raw_block.get("translation") or "").split())[:600] or None,
                           "speaker": who.get("name") or None, "role": who.get("role") or "otro",
                           "gender": who.get("gender"), "seen": seg.get("seen") or ""})
        elif kind_ == "secuencia":
            seg = index.get(str(raw_block.get("ref") or ""))
            if seg is None:
                notes.append(f"quitada una secuencia que no está en el expediente ({raw_block.get('ref')})")
                continue
            try:
                start = max(seg["start"], float(raw_block.get("start", seg["start"])))
                end = min(seg["end"], float(raw_block.get("end", seg["end"])))
            except (TypeError, ValueError):
                start, end = seg["start"], seg["end"]
            end = min(end, start + cap)
            if end - start < 2:
                continue
            blocks.append({"type": "secuencia", "ref": seg["id"], "source": seg["source"], "url": seg.get("url"),
                           "channel": seg.get("channel"), "start": round(start, 2), "end": round(end, 2),
                           "seen": seg.get("seen") or ""})
    criterion = " ".join(str(raw.get("criterion") or "").split())[:200]
    criterion_refs = [r for r in raw.get("criterion_refs") or [] if r in index]
    if kind == "top" and not (criterion and criterion_refs):
        notes.append("el orden del top no se justifica con un dato del expediente")
    return {"blocks": blocks, "criterion": criterion or None, "criterionRefs": criterion_refs, "notes": notes}


def estimate(blocks: list[dict[str, Any]]) -> dict[str, Any]:
    """Seconds of narration, of other people's voices and of footage; the MB the downloads would cost."""

    words = sum(len(b["text"].split()) for b in blocks if b["type"] == "narrador")
    voices = sum(b["end"] - b["start"] for b in blocks if b["type"] == "declaracion")
    footage = sum(b["end"] - b["start"] for b in blocks if b["type"] == "secuencia")
    narration = words / WORDS_PER_SECOND
    total = narration + voices + 4 * sum(1 for b in blocks if b["type"] == "tarjeta")
    return {"narrationSeconds": round(narration), "voiceSeconds": round(voices), "footageSeconds": round(footage),
            "minutes": round(total / 60, 1), "otherVoiceShare": round(voices / total, 2) if total else 0,
            "downloadMB": round((voices + footage) * MB_PER_SECOND), "clips": sum(1 for b in blocks if b["type"] in
                                                                             ("declaracion", "secuencia"))}


def write(ctx: Any, ask: Callable[[str, str], dict[str, Any]] | None = None) -> dict[str, Any]:
    """The blocks of a «material primero» video, from its case file (work/<vídeo>/bloques.json)."""

    from . import tope
    from .expediente import load

    expediente = load(ctx)
    cfg = ctx.section("material_first")
    kind = str(expediente.get("kind") or "top")
    index = segment_index(expediente)
    cap = tope.seconds(ctx)
    if ask is None:
        from .llm import complete_json

        def ask(system: str, user: str) -> dict[str, Any]:
            return complete_json(ctx, stage="bloques", section="guion" if ctx.section("guion").get("model") else "planner",
                                 max_tokens=8000, system=system, user=user)
    unit, unit_one = {"top": ("puesto", "cada puesto"), "noticia": ("parte", "cada parte"),
                      "documental": ("capítulo", "cada capítulo")}.get(kind, ("puesto", "cada puesto"))
    structure = STRUCTURES.get(kind, "")
    own = str((ctx.config.get("guion") or {}).get("estructura") or "").strip()
    if own:                                   # the channel's own structure (guion.estructura) on top, like the normal mode
        from .organizar import STRUCTURES as CHANNEL_STRUCTURES

        structure += "\nEstructura del canal: " + CHANNEL_STRUCTURES.get(own, own)
    system = SYSTEM.format(kind=kind, tone=str(cfg.get("tone") or "serio y directo"), minutes=expediente.get("minutes", 6),
                           unit=unit, unit_one=unit_one, cap=int(cap), order_rule=ORDER_RULE if kind == "top" else "",
                           structure=structure)
    raw = ask(system, f"TÍTULO: {expediente.get('title')}\n\nEXPEDIENTE:{listing(expediente, index)}")
    result = check(raw, index, cap, kind)
    result.update({"title": expediente.get("title"), "kind": kind, "estimate": estimate(result["blocks"])})
    ctx.write_json(OUTPUT, result)
    return result


def edit(ctx: Any, position: int, action: str, ref: str | None = None) -> dict[str, Any]:
    """The owner's change before voice and downloads: «quitar» a block, or «cambiar» a statement for another
    statement of the case file."""

    from .expediente import load

    path = ctx.work_dir / OUTPUT
    data = json.loads(path.read_text("utf-8"))
    blocks = data["blocks"]
    if not 0 <= position < len(blocks):
        raise ValueError("Ese bloque no existe")
    if action == "quitar":
        del blocks[position]
    elif action == "cambiar":
        if blocks[position]["type"] != "declaracion":
            raise ValueError("Solo se cambian declaraciones")
        from . import tope

        index = segment_index(load(ctx))
        fixed = check({"blocks": [{"type": "declaracion", "ref": ref}]}, index, tope.seconds(ctx), kind="")
        if not fixed["blocks"]:
            raise ValueError("Esa no es una declaración del expediente")
        blocks[position] = fixed["blocks"][0]
    else:
        raise ValueError("Acción no válida")
    data["estimate"] = estimate(blocks)
    data["edited"] = True
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data
