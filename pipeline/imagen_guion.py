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

import re
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
TRIES_FILE = "imagen_guion.intentos.json"   # materiales/<vídeo>/: rewrites already made (never lost with work/)


def _tries(ctx: Any) -> dict[str, Any]:
    import json

    try:
        return json.loads((ctx.materials_dir / TRIES_FILE).read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def _save_tries(ctx: Any, data: dict[str, Any]) -> None:
    import json

    (ctx.materials_dir / TRIES_FILE).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


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
    if mode == "parar" and int(_tries(ctx).get("tries", 0)) >= 1:
        mode = "aviso"                 # rewritten once already: it goes on, never a second rewrite (27-11: 8 loops)
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
    kept = {k: v for k, v in old.items() if k in ("autoTries", "synthetic", "continued", "autoFix")}
    target.write_text(json.dumps({**kept, "hash": digest, **result}, ensure_ascii=False, indent=1), encoding="utf-8")
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
        target.write_text(json.dumps({**kept, "hash": "", **result}, ensure_ascii=False, indent=1), encoding="utf-8")
        return (f"{share} % del guion no tiene imagen posible (límite {limit} %): reescribe las frases que dice "
                f"work/{ctx.slug}/{GATE_FILE} y vuelve a darle")
    return None


FIX_SYSTEM = """
Eres el guionista de un canal documental de YouTube. Te paso el guion entero y, numeradas, las frases que no se
podrán enseñar en pantalla (nadie grabó lo que cuentan), cada una con una idea de cómo arreglarla. Reescribe SOLO
esas frases para que cuenten lo mismo apoyándose en algo que sí se grabó o se fotografió: el momento concreto, con
su fecha y su lugar; una cita real; un dato que se pueda rotular. Mismo idioma, mismo tono, misma longitud más o
menos, y que encaje con la frase de antes y la de después. No inventes hechos: si hay MATERIAL DE REFERENCIA, sácalos
de ahí; si una frase no tiene arreglo sin inventar, déjala igual. Que suene natural, dicho en voz alta: no repitas la
misma fecha o el mismo dato en frases seguidas, y no metas una cifra donde no aporta nada. Nunca toques los títulos de
capítulo.

Devuelve SOLO JSON: {"cambios": [{"n": 3, "nueva": "la frase reescrita"}]}
"""


def headings(script: str) -> list[str]:
    """The chapter titles of a script: «## …» lines and lines written all in capitals (2+ words, no final period)."""

    out = []
    for line in script.splitlines():
        text = line.strip()
        letters = re.sub(r"[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", "", text)
        if text.startswith("#") or (len(text.split()) >= 2 and letters and text == text.upper()
                                     and not text.endswith(".")):
            out.append(text)
    return out


def without_heading(sentence: str, titles: list[str]) -> tuple[str, str]:
    """(title, rest): the sentence splitter glues a chapter title to the sentence after it; the title is never
    rewritten."""

    flat = " ".join(sentence.split())
    for title in titles:
        head = " ".join(title.split())
        if flat.startswith(head + " "):
            return title, flat[len(head):].strip()
    return "", flat


def restore_headings(original: str, fixed: str) -> str:
    """Every chapter title of `original` on its own line again in `fixed` (a rewrite that glued «## TITLE» to the
    next sentence made the whole paragraph a chapter title: newgym9)."""

    for title in headings(original):
        pattern = r"(^|\n)[ \t]*" + r"\s+".join(re.escape(w) for w in title.split()) + r"[ \t]+(?=\S)"
        fixed = re.sub(pattern, lambda m: f"{m.group(1)}{title}\n\n", fixed, count=1)
    return fixed


def replace_sentence(script: str, old: str, new: str) -> str:
    """The script with `old` (as split_sentences gave it: spaces joined) replaced once by `new`."""

    pattern = r"\s+".join(re.escape(word) for word in old.split())
    return re.sub(pattern, lambda _: new, script, count=1)


def fix(ctx: Any, script: str, title: str = "", references: str = "", review_fn: Any = None,
        ask: Any = None) -> dict[str, Any]:
    """«Arreglar lo que no se puede enseñar»: the sentences without an image rewritten over something filmed, then the
    script read again. {"script", "changed", "before", "after"} (before/after: review()'s result)."""

    from .llm import complete_json

    look = review_fn or review
    before = look(ctx, script, title)
    titles = headings(script)
    todo = []
    for r in before["sinImagen"]:
        _, rest = without_heading(r["text"], titles)       # the chapter title stays as it is
        if len(rest.split()) >= 3:
            todo.append({**r, "text": rest})
    if not todo:
        return {"script": script, "changed": 0, "before": before, "after": before}
    listing = "\n".join(f"[{r['n']}] {r['text']}" + (f"  (idea: {r['idea']})" if r.get("idea") else "") for r in todo)
    user = f"TÍTULO: {title or '(sin título)'}\n\nGUION:\n{script}\n\nFRASES SIN IMAGEN:\n{listing}"
    if references:
        user += f"\n\nMATERIAL DE REFERENCIA:\n{references}"
    if ask is not None:
        answer = ask(user)
    else:
        section = "guion" if ctx.section("guion").get("model") else "planner"
        from .organizar import retention_rules

        rules = retention_rules(ctx)               # guion.retencion: the rewrites keep the same rules
        answer = complete_json(ctx, stage="guion", section=section, max_tokens=8000,
                               system=FIX_SYSTEM + ("\n" + rules if rules else ""), user=user, use_cache=False)
    by_n = {r["n"]: r["text"] for r in todo}
    fixed, changed = script, 0
    for item in answer.get("cambios") or []:
        try:
            n = int(item.get("n"))
        except (TypeError, ValueError):
            continue
        new = " ".join(str(item.get("nueva") or "").split())
        if n in by_n and new and new != by_n[n]:
            again = replace_sentence(fixed, by_n[n], new)
            if again != fixed:
                fixed, changed = again, changed + 1
    fixed = restore_headings(script, fixed)
    after = look(ctx, fixed, title) if changed else before
    return {"script": fixed, "changed": changed, "before": before, "after": after}



class ScriptRewritten(RuntimeError):
    """The script was rewritten (and its synthetic voice made again): the video starts over with it."""


def rescue(ctx: Any, stopped: str, fix_fn: Any = None, ensure_voice: Any = None, send: Any = None) -> str:
    """When the check stops a video (too much of its script cannot be shown), it fixes itself instead of waiting for
    the owner (`guion.arreglar_solo`, on):

    - with the channel's synthetic voice, the sentences without an image are rewritten over something filmed
      (`fix`, with the video's reference links), the original kept as guion.original.txt, the voice made again (its
      unchanged pieces are reused, not paid twice) and ScriptRewritten is raised: the video starts over with it.
      At most `guion.arreglar_intentos` (1) times per video;
    - with the owner's own recorded voice (it cannot be remade), or once the rewrite was tried, or when nothing could
      be rewritten without inventing: the video goes on anyway and says so — the fill-in, photos and boards cover it.
    Returns "" to go on, or the stop message when `guion.arreglar_solo` is off."""

    import json

    cfg = ctx.section("guion")
    if not cfg.get("arreglar_solo", True):
        return stopped
    folder = ctx.materials_dir
    path = ctx.work_dir / GATE_FILE
    try:
        state = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        state = {}
    attempts = _tries(ctx)
    tries = max(int(state.get("autoTries", 0)), int(attempts.get("tries", 0)))   # the materials' count wins
    path.parent.mkdir(parents=True, exist_ok=True)
    synthetic = bool(state.get("synthetic")) or (folder / "voz.genaipro.json").is_file() \
        or not (folder / "voz.mp3").is_file()
    state["synthetic"] = synthetic              # remembered: the remade voice is the program's too
    note = None

    def tell(text: str) -> None:
        print(f"   {text}")
        try:
            if send is not None:
                send(text)
            else:
                from . import notify

                notify.telegram(ctx, f"{ctx.slug}: {text}")
        except Exception:
            pass

    # at most once per video, whatever arreglar_intentos says: each rewrite pays a voice and a new plan
    if synthetic and tries < min(1, int(cfg.get("arreglar_intentos", 1))):
        script_path = folder / "guion.txt"
        script = script_path.read_text("utf-8")
        title_path = folder / "titulo.txt"
        title = title_path.read_text("utf-8").strip().splitlines()[0] if title_path.is_file() else ""
        refs = ""
        if (folder / "referencias.txt").is_file():
            try:
                from . import referencias

                refs = referencias.read(ctx, (folder / "referencias.txt").read_text("utf-8"))
            except Exception:
                refs = ""
        try:
            result = (fix_fn or fix)(ctx, script, title, refs)
        except Exception as error:
            result = {"changed": 0}
            note = f"no se pudo reescribir ({str(error)[:100]})"
        state["autoTries"] = tries + 1
        _save_tries(ctx, {**attempts, "tries": tries + 1, "synthetic": synthetic})
        if result.get("changed"):
            if not (folder / "guion.original.txt").is_file():
                (folder / "guion.original.txt").write_text(script, encoding="utf-8")
            script_path.write_text(result["script"], encoding="utf-8")
            before = (result.get("before") or {}).get("shares", {}).get("sin_imagen")
            after = (result.get("after") or {}).get("shares", {}).get("sin_imagen")
            state["autoFix"] = {"changed": result["changed"], "before": before, "after": after}
            path.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
            for name in ("voz.mp3", "voz.genaipro.json"):         # the voice again, over the new script
                (folder / name).unlink(missing_ok=True)
            if ensure_voice is not None:
                ensure_voice(ctx)
            else:
                from . import tts

                tts.ensure(ctx, wait=True)
            tell(f"guion arreglado solo: {result['changed']} frases sin imagen reescritas sobre algo grabado"
                 + (f" (sin imagen: {before} % → {after} %)" if before is not None and after is not None else "")
                 + "; voz rehecha; el vídeo vuelve a empezar. El original queda en guion.original.txt")
            raise ScriptRewritten(f"guion reescrito ({result['changed']} frases): vuelvo a empezar con él")
        note = note or "ninguna frase se pudo reescribir sin inventar"
    state["continued"] = True
    path.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    why = (note if note else "la voz es la tuya grabada: no se puede rehacer" if not synthetic
           else "ya se intentó reescribir")
    tell(f"{stopped} — sigo igualmente ({why}): el relleno, las fotos y las pizarras taparán lo que no tenga imagen")
    return ""


def repair(root: Any, slug: str) -> int:
    """`python -m pipeline.imagen_guion <vídeo>`: a script rewritten before this fix gets its chapter titles back on
    their own lines (from guion.original.txt). Returns how many were repaired; the voice must be made again."""

    from .context import RunContext

    folder = RunContext.create(slug, root=root).materials_dir
    original = (folder / "guion.original.txt").read_text("utf-8")
    current = (folder / "guion.txt").read_text("utf-8")
    fixed = restore_headings(original, current)
    count = sum(1 for a, b in zip(current.splitlines(), fixed.splitlines()) if a != b) if fixed != current else 0
    if fixed != current:
        (folder / "guion.txt").write_text(fixed, encoding="utf-8")
    return count


if __name__ == "__main__":
    import sys

    from .config import PROJECT_ROOT

    if len(sys.argv) != 2:
        print("Uso: python -m pipeline.imagen_guion <vídeo>   (vuelve a poner en su línea los títulos de capítulo)")
        raise SystemExit(2)
    fixed_titles = repair(PROJECT_ROOT, sys.argv[1])
    print(f"{fixed_titles} título(s) de capítulo vueltos a su línea" if fixed_titles else "Los títulos ya estaban bien")
