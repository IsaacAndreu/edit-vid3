"""Doblaje de los vídeos de --atlas-guion: el mismo vídeo en otro idioma, para el canal de ese idioma.

Cuando la cola termina un vídeo de guion + escenas cuyo canal dobla (`dubbing:` en canales/<canal>.yaml o «Voces por
canal → Doblaje» en el estudio), para cada idioma con canal y voz se crea materiales/<canal-idioma>/<slug>-<lang>/:
  guion.txt     el guion traducido (y adaptado al público, `localize:` del canal de destino)
  escenas.json  el mismo storyboard con los textos de pantalla traducidos y cada ancla {"say": …} cambiada por la
                frase equivalente que aparece literalmente en el guion traducido (se comprueba; un segundo intento
                con los fallos; si aún falta alguna, no se crea el doblaje y se dice por qué)
Ese vídeo entra en la cola como cualquier otro: la voz del canal de destino lo lee y se renderiza con sus tiempos.
Los datos (vuelos, regiones, bloques 3D) son los mismos: no se vuelven a generar.
"""

from __future__ import annotations

import copy
import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Callable

from .context import RunContext, find_video

SYSTEM = """
Traduces al {language} un vídeo documental: el guion de la voz, los textos que se ven en pantalla y las frases ancla.
{local}
Reglas:
- "guion": la narración entera traducida con naturalidad (no palabra por palabra), mismos párrafos, mismos datos,
  cifras y nombres; las cifras escritas como se dicen en voz alta en ese idioma, igual que en el original.
- "anchors": para cada id, la frase de 2-6 palabras de TU guion traducido que corresponde a la frase original: debe
  aparecer LITERALMENTE en tu "guion" (mismas palabras y orden; mayúsculas y signos dan igual).
- "texts": cada texto de pantalla traducido, igual de corto; conserva MAYÚSCULAS si el original las usa, los nombres
  propios, las cifras, las horas y los *asteriscos* alrededor de la palabra equivalente.
Devuelve SOLO JSON: {{"guion": "...", "anchors": {{"a1": "...", ...}}, "texts": {{"id": "...", ...}}}}
""".strip()

TEXT_KEYS = {"text", "label", "sub", "kicker", "sourceNote", "seaLabel", "name", "liftoffLabel", "doneLabel", "inside",
             "titles", "asOf", "who", "readout", "middle", "left", "right"}
NEVER = {"type", "id", "theme", "enter", "accent", "style", "marker", "stroke", "region", "terrain", "profile", "source",
         "data", "model", "view", "part", "mode", "series", "status", "corner", "clock", "ref", "unit", "say", "layout",
         "diagram", "cells", "from", "to", "registration", "tailLogo", "titlesLogo", "fill", "projection", "kind", "brand"}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(re.findall(r"[a-z0-9]+", s))


def collect(board: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """Las anclas ({"say"}) y los textos de pantalla del storyboard, cada uno con su ruta."""

    anchors: dict[str, dict[str, Any]] = {}
    texts: dict[str, str] = {}

    def walk(node: Any, path: str, key: str = "") -> None:
        if isinstance(node, dict):
            if "say" in node and isinstance(node["say"], str):
                anchors[path] = node
                return
            for k, v in node.items():
                if k not in NEVER:
                    walk(v, f"{path}.{k}" if path else k, k)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}.{i}", key)
        elif isinstance(node, str) and (key in TEXT_KEYS or key in ("title", "top", "bottom", "titleText")) and re.search(r"[^\W\d_]{2}", node):
            texts[path] = node

    walk(board, "")
    return anchors, texts


def _set(board: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    node: Any = board
    for p in parts[:-1]:
        node = node[int(p)] if isinstance(node, list) else node[p]
    last = parts[-1]
    if isinstance(node, list):
        node[int(last)] = value
    else:
        node[last] = value


def translate(ask: Callable[[str, str], dict[str, Any]], language: str, local: str, script: str,
              board: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """(guion traducido, storyboard traducido). Lanza ValueError si las anclas no aparecen en el guion traducido."""

    anchors, texts = collect(board)
    ids = {f"a{i}": path for i, path in enumerate(anchors)}
    user = json.dumps({"guion": script, "anchors": {k: anchors[p]["say"] for k, p in ids.items()}, "texts": texts}, ensure_ascii=False)
    system = SYSTEM.format(language=language, local=local)
    missing: list[str] = []
    for attempt in range(2):
        extra = "" if not missing else ("\n\nEN EL INTENTO ANTERIOR estas anclas no aparecían literalmente en tu guion: "
                                        + ", ".join(missing) + ". Corrígelas.")
        answer = ask(system, user + extra)
        out = str(answer.get("guion") or "").strip()
        got = answer.get("anchors") or {}
        missing = [k for k in ids if not str(got.get(k) or "").strip() or _norm(str(got[k])) not in _norm(out)]
        if out and not missing:
            new = copy.deepcopy(board)
            for k, path in ids.items():
                _set(new, path, {**anchors[path], "say": str(got[k]).strip()})
            for path, text in (answer.get("texts") or {}).items():
                if path in texts and str(text).strip():
                    _set(new, path, str(text).strip())
            return out, new
    raise ValueError(f"anclas que no aparecen en el guion traducido: {', '.join(missing[:8])}")


def _source(root: Path, folder: Path, slug: str) -> dict[str, Any]:
    """escenas.json del vídeo, o el storyboard que la IA escribió desde escenas.md (con sus datos)."""

    if (folder / "escenas.json").is_file():
        return json.loads((folder / "escenas.json").read_text(encoding="utf-8"))
    clean = re.sub(r"[^a-z0-9-]+", "-", slug.lower()).strip("-")
    board = json.loads((root / "storyboards" / f"{clean}.json").read_text(encoding="utf-8"))
    board["audio"] = {}
    board["meta"].pop("duration", None)
    data_file = root / "public" / "atlas-work" / clean / "data.json"
    data = json.loads(data_file.read_text(encoding="utf-8")) if data_file.is_file() else []
    return {"storyboard": board, "data": data}


def make(root: Path, slug: str, lang: str, channel: str, ask: Callable[[str, str], dict[str, Any]]) -> Path | None:
    from .doblaje import AUDIENCES, IN_SPANISH

    folder = find_video(root, slug)
    target = root / "materiales" / channel / f"{slug}-{lang}"
    if target.exists():
        return None
    given = _source(root, folder, slug)
    board = given.get("storyboard", given)
    board = {**board, "audio": {}}
    script = (folder / "guion.txt").read_text(encoding="utf-8")
    tctx = RunContext.create("_doblaje", root=root, channel=channel)
    local = str(tctx.config.get("localize") or "").strip()
    local = f"Adáptalo al público de {AUDIENCES.get(lang, lang)}: {local[:600]}" if local else ""
    new_script, new_board = translate(ask, IN_SPANISH.get(lang, lang), local, script, board)
    new_board["meta"] = {**new_board["meta"], "slug": re.sub(r"[^a-z0-9-]+", "-", f"{slug}-{lang}".lower()).strip("-")}
    group = root / "materiales" / channel
    group.mkdir(parents=True, exist_ok=True)
    if not (group / "config.yaml").is_file():
        (group / "config.yaml").write_text(f"canal: {channel}\n", encoding="utf-8")
    target.mkdir(parents=True)
    (target / "guion.txt").write_text(new_script + "\n", encoding="utf-8")
    out = {k: v for k, v in given.items() if k not in ("storyboard",)}
    out["storyboard"] = new_board
    (target / "escenas.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if (folder / ".urgente").is_file():
        (target / ".urgente").write_text("doblaje de un vídeo urgente\n", encoding="utf-8")
    return target


def after_done(root: Path, slug: str, log: Callable[[str], None] = print) -> list[Path]:
    """Los doblajes de un vídeo de Atlas recién terminado, según el doblaje de su canal (idiomas con canal y voz)."""

    from .doblaje import settings, targets
    from .llm import complete_json

    ctx = RunContext.create(slug, root=root)
    try:
        cfg = settings(ctx)
    except Exception as error:
        log(f"Doblaje de {slug}: {error}")
        return []
    if not cfg.get("enabled"):
        return []
    made: list[Path] = []
    for lang in targets(ctx, cfg):
        channel = cfg["channels"].get(lang)
        if not channel or lang not in (cfg.get("voices") or {}):      # sin voz en ese idioma no hay doblaje
            continue

        def ask(system: str, user: str) -> dict[str, Any]:
            return complete_json(ctx, stage="atlas_doblaje", system=system, user=user, section="atlas_guion", max_tokens=16000)

        try:
            target = make(root, slug, lang, channel, ask)
        except Exception as error:
            log(f"Doblaje de {slug} al {lang}: {str(error)[:300]}")
            continue
        if target:
            log(f"Doblaje de {slug} al {lang}: {target.relative_to(root)} (a la cola)")
            made.append(target)
    return made
