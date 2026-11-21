"""What of a script can be shown, before the voice is recorded (bloque 5 of prompts/motor-punteria-prompt.md).

A script made of things nobody filmed («dejó el instituto», «mide un metro cuarenta y dos», «firmar contratos»)
becomes, however good the search, a video of filler and text. The reference channels write over what was filmed:
a competition with its date and venue, a score, a podium, a literal quote. This reads the script sentence by
sentence, before any money is spent on the voice and the searches, and says for each one:

- «imagen»: something that was filmed or photographed and can be shown as it is (a final, a fall, a ceremony, a
  trial, an interview, a place, a scene of the game);
- «ambiente»: no image of its own, but footage of who or what it is about fits (a decision, a feeling, a fact
  about their life, a figure);
- «sin_imagen»: not even that: abstract reasoning, lists of rules, hypotheticals, general statements, or a person
  or thing nobody will find footage of — with a one-line idea to fix it.

It is a warning, never a block: the studio shows the shares and the sentences, and you decide.
"""

from __future__ import annotations

from typing import Any

SYSTEM = """
Eres el montador de un canal de YouTube de documentales. Te pasan el guion de un vídeo, frase a frase y numerado,
ANTES de grabar la voz. Para cada frase dices qué se podrá enseñar en pantalla mientras se dice, con el material que
existe de verdad en YouTube, archivos de noticias, fotos de prensa o el propio juego.

- "imagen": lo que cuenta se grabó o se fotografió y se puede enseñar tal cual: una competición o un partido concreto,
  una caída, un podio, una ceremonia, una rueda de prensa, una entrevista, un juicio, un lugar nombrado, una escena
  o misión concreta del videojuego.
- "ambiente": no tiene imagen propia, pero sirve material de la persona o del tema del que se habla en esa época:
  una decisión, un sentimiento, un dato de su vida, una cifra, su familia, su forma de entrenar.
- "sin_imagen": ni eso: razonamientos abstractos, listas de normas, hipótesis («imagina que…»), frases generales
  sin nadie concreto, o una persona o cosa de la que casi seguro no hay ni una foto.

Para cada "sin_imagen" escribe en "idea" UNA forma corta de reescribirla apoyándola en algo que sí se grabó (el
momento, la fecha y el lugar en que pasó, una cita real, un dato que se pueda rotular), o "" si no se te ocurre.

Devuelve SOLO JSON: {"frases": [{"n": 1, "tipo": "imagen" | "ambiente" | "sin_imagen", "idea": ""}]}
Una entrada por frase, todas, en orden.
"""

BATCH = 60


def review(ctx: Any, script: str, title: str = "", ask: Any = None) -> dict[str, Any]:
    """{"counts", "shares", "sinImagen": [{"n", "text", "idea"}], "verdict", "sentences"}."""

    from .hook import split_sentences
    from .llm import complete_json

    sentences = [s for s in split_sentences(script) if len(s.split()) >= 3]
    if len(sentences) < 4:
        raise ValueError("El guion es demasiado corto para revisarlo")

    def call(batch: list[tuple[int, str]]) -> dict[str, Any]:
        listing = "\n".join(f"[{n}] {text}" for n, text in batch)
        user = (f"TÍTULO: {title or '(sin título)'}\n\nFRASES:\n{listing}")
        if ask is not None:
            return ask(user)
        # guion.model (claude-…): the same model that writes the drafts reads them; else the planner's
        section = "guion" if ctx.section("guion").get("model") else "planner"
        return complete_json(ctx, stage="guion", section=section, max_tokens=6000, system=SYSTEM, user=user)

    numbered = list(enumerate(sentences, start=1))
    labels: dict[int, dict[str, Any]] = {}
    for start in range(0, len(numbered), BATCH):
        batch = numbered[start:start + BATCH]
        try:
            answer = call(batch)
        except Exception as error:                     # one batch without an answer: those sentences stay unknown
            print(f"   imagen del guion: sin respuesta en un tramo ({str(error)[:120]})")
            continue
        for item in answer.get("frases") or []:
            try:
                n = int(item.get("n"))
            except (TypeError, ValueError):
                continue
            if str(item.get("tipo")) in ("imagen", "ambiente", "sin_imagen"):
                labels[n] = {"tipo": str(item["tipo"]), "idea": str(item.get("idea") or "").strip()[:240]}
    counts = {"imagen": 0, "ambiente": 0, "sin_imagen": 0, "sin_revisar": 0}
    rows = []
    for n, text in numbered:
        kind = labels.get(n, {}).get("tipo", "sin_revisar")
        counts[kind] += 1
        rows.append({"n": n, "text": text, "tipo": kind, "idea": labels.get(n, {}).get("idea", "")})
    total = len(numbered)
    shares = {k: round(100 * v / total) for k, v in counts.items()}
    return {"counts": counts, "shares": shares, "verdict": verdict(shares),
            "sinImagen": [r for r in rows if r["tipo"] == "sin_imagen"], "sentences": rows}


def verdict(shares: dict[str, int]) -> str:
    """One line: whether this script will be shown or mostly covered."""

    if shares.get("sin_imagen", 0) >= 20:
        return (f"⚠️ {shares['sin_imagen']} % de las frases no tienen imagen posible: saldrán como texto o relleno. "
                "Mira las ideas de abajo antes de grabar.")
    if shares.get("imagen", 0) < 25:
        return (f"⚠️ Solo {shares.get('imagen', 0)} % de las frases tienen imagen propia: el vídeo será sobre todo "
                "material de ambiente de la persona. Apóyalo en momentos grabados (competiciones, fechas, citas).")
    return f"✅ {shares.get('imagen', 0)} % con imagen propia y {shares.get('ambiente', 0)} % de ambiente: se puede enseñar."


GATE_FILE = "imagen_guion.json"        # work/<slug>/: the last check, with the hash of the script it read


def gate(ctx: Any, review_fn: Any = None, send: Any = None) -> str | None:
    """`guion.revisar_antes` (off): before the first stage that searches and downloads, this video's script is read
    once (again only if you change it). «aviso»: the share without an image and the ideas to fix it go to Telegram
    and the video goes on; «parar»: when `guion.max_sin_imagen` % (35) or more cannot be shown, it also stops here,
    before any money goes to searches — the message (returned) says what to rewrite. elasesinodelkickboxing: 70 % of
    its 343 shots ended without an image after all the searching."""

    import hashlib
    import json

    mode = str(ctx.section("guion").get("revisar_antes") or "").strip().lower()
    if mode in ("", "false", "no", "0", "off"):
        return None
    script_path = ctx.materials_dir / "guion.txt"
    if not script_path.is_file():
        return None
    script = script_path.read_text("utf-8")
    digest = hashlib.sha256(script.encode()).hexdigest()[:16]
    target = ctx.work_dir / GATE_FILE
    try:
        old = json.loads(target.read_text("utf-8"))
    except (OSError, ValueError):
        old = {}
    if old.get("hash") == digest:                     # this very script was read already (and you went on)
        return None
    title_path = ctx.materials_dir / "titulo.txt"
    title = title_path.read_text("utf-8").strip().splitlines()[0] if title_path.is_file() else ""
    try:
        result = (review_fn or review)(ctx, script, title)
    except Exception as error:                        # the check never stops a video by failing itself
        print(f"   revisión del guion antes de empezar: {str(error)[:160]}")
        return None
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"hash": digest, **result}, ensure_ascii=False, indent=1), encoding="utf-8")
    share = int(result["shares"].get("sin_imagen", 0))
    limit = int(ctx.section("guion").get("max_sin_imagen", 35))
    stop = mode == "parar" and share >= limit
    ideas = [f"[{r['n']}] {r['text'][:90]} → {r['idea']}" for r in result["sinImagen"] if r.get("idea")][:8]
    text = (f"{ctx.slug}: {result['verdict']}\n" + ("\n".join(ideas) + "\n" if ideas else "")
            + ("PARADO antes de buscar: reescribe esas frases en guion.txt y dale a «Hacer ahora» (o pon "
               "guion: {revisar_antes: aviso} en su config.yaml para hacerlo tal cual)." if stop else ""))
    if share >= limit or result["shares"].get("imagen", 0) < 25:
        if send is not None:
            send(text)
        else:
            from . import notify

            notify.telegram(ctx, text)
    if stop:
        target.write_text(json.dumps({"hash": "", **result}, ensure_ascii=False, indent=1), encoding="utf-8")
        return (f"{share} % del guion no tiene imagen posible (límite {limit} %): reescribe las frases que dice "
                f"work/{ctx.slug}/{GATE_FILE} y vuelve a darle")
    return None

