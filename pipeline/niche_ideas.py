"""From the radar to a video: ideas for a niche (or «like this video»), saved ideas, and a niche turned into a channel.

- ideas(seed): the LLM turns the outliers of a niche (the videos that beat their own channel there) into concrete
  video ideas: title, format, angle, hook, an outline by chapters and what to check before writing. «Más ideas» asks
  again without repeating what it already proposed for that seed or what is already made.
- saved ideas (out/_radar/ideas-guardadas.json): what you keep; «Crear vídeo» opens the new-video form filled in.
- make_profile(niche): canales/<nombre>.yaml with the niche's search and the channels that win in it as competitors,
  so the daily radar follows it and videos can be made for it.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import unicodedata
from pathlib import Path
from typing import Any

import yaml

from .context import RunContext

FOLDER = "out/_radar/ideas"
SAVED = "out/_radar/ideas-guardadas.json"
STAGE = "radar"

SYSTEM = """
Eres el estratega de contenido de un creador que hace documentales sin cara (voz en off + clips de archivo de YouTube +
gráficos), en español, de 8-15 minutos. Te paso {what} y los vídeos que MEJOR funcionan ahí (muchas más visitas que la
media de su propio canal). Propón EXACTAMENTE {count} ideas de vídeo nuevas, distintas entre sí.
Devuelve SOLO JSON:
{"ideas": [{"title": "título en español, gancho fuerte, máx. 70 caracteres",
            "format": "uno de: {formats}",
            "protagonist": "persona, empresa, objeto o lugar principal",
            "angle": "qué historia se cuenta y por qué engancha (1-2 frases)",
            "hook": "las 2-3 primeras frases del vídeo",
            "outline": ["capítulo 1: …", "capítulo 2: …", "… (4-7 capítulos)"],
            "footage": "qué metraje de archivo existe en YouTube para contarlo (y si escasea, dilo)",
            "why": "qué vídeos de la lista lo respaldan (cita títulos)",
            "research": "datos que hay que comprobar antes de escribir"}]}
Reglas: no copies títulos de la lista, inspírate en su patrón. No repitas las ideas ya propuestas ni los temas ya hechos.
NO afirmes datos concretos que no estén en la lista (cifras, fechas, récords, declaraciones): la tensión sin cifras
inventadas; cualquier dato va en "research". Descarta ideas sin metraje de archivo posible.
""".strip()


def _read(path: Path) -> Any:
    try:
        return json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return None


def _write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def seed_key(seed: dict[str, Any]) -> str:
    raw = f"{seed.get('kind')}:{seed.get('query') or seed.get('id') or ''}".lower()
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def slugify(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", plain).strip("-")[:40]


def _formats(root: Path) -> dict[str, str]:
    out = {}
    for path in sorted((root / "formatos").glob("*.yaml")):
        try:
            data = yaml.safe_load(path.read_text("utf-8")) or {}
        except yaml.YAMLError:
            data = {}
        out[path.stem] = str(data.get("descripcion") or data.get("nombre") or path.stem)
    return out


def _niche(root: Path, query: str) -> dict[str, Any] | None:
    from . import radar

    return next((n for n in radar.niches(root) if n.get("query", "").lower() == query.lower()), None)


def evidence(root: Path, seed: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    """(what the ideas are for, the winning videos to learn from)."""

    from . import radar

    if seed.get("kind") == "video":
        latest = radar.latest(root) or {}
        profile = str(seed.get("channel") or "")
        others = ((latest.get("channels") or {}).get(profile) or {}).get("top", [])
        video = {k: seed.get(k) for k in ("title", "views", "ratio")} | {"channel": seed.get("author") or ""}
        about = ""
        if profile:
            try:
                about = RunContext.create("_ideas", root=root, channel=profile).section("ideas").get("about", "")
            except Exception:
                about = ""
        what = (f"este vídeo que está funcionando muy bien: «{seed.get('title')}» ({seed.get('author') or '?'}, "
                f"{seed.get('ratio')}x su canal). Las ideas deben ser «como este»: mismo público y mismo tipo de gancho"
                + (f", para {about}" if about else ""))
        return what, [video] + [v for v in others if v.get("title") != seed.get("title")][:15]
    query = str(seed.get("query") or "").strip()
    if not query:
        raise ValueError("Falta el nicho")
    entry = _niche(root, query) or {}
    videos = entry.get("titles") or entry.get("examples") or []
    if len(videos) < 6:                              # an older radar kept only 4 examples: search the niche again
        from . import lab

        ctx = RunContext.create("_ideas", root=root)
        try:
            videos = [v for v in lab.outliers(ctx, query, days=int(ctx.section("radar").get("niche_days", 120)))
                      if (v["ratio"] or 0) >= 1.5][:20] or videos
        except Exception as error:
            if not videos:
                raise ValueError(f"No puedo buscar el nicho en YouTube: {str(error)[:160]}") from error
    name = seed.get("name") or entry.get("name") or query
    return f"el nicho «{name}» (búsqueda de YouTube: «{query}»)" + (f": {entry['why']}" if entry.get("why") else ""), videos


def ideas(root: Path, seed: dict[str, Any], count: int = 5, more: bool = False) -> dict[str, Any]:
    """Ideas for a seed (cached; `more` adds a new batch without repeats)."""

    from .ideas import done_topics
    from .llm import complete_json

    path = root / FOLDER / f"{seed_key(seed)}.json"
    cached = _read(path) or {}
    if cached.get("ideas") and not more:
        return cached
    what, videos = evidence(root, seed)
    formats = _formats(root)
    ctx = RunContext.create("_ideas", root=root)
    listing = "\n".join(f"- x{v.get('ratio')} · {v.get('views')} visitas · [{v.get('channel', '')}] {v.get('title')}"
                        for v in videos[:25])
    before = [i["title"] for i in cached.get("ideas", [])]
    try:
        taken = done_topics(ctx)[-60:]
    except Exception:
        taken = []
    result = complete_json(
        ctx, stage=STAGE, section="planner", max_tokens=1300 * count, use_cache=False,
        system=SYSTEM.replace("{what}", what).replace("{count}", str(count)).replace("{formats}", ", ".join(formats)),
        user=(f"VÍDEOS QUE MEJOR FUNCIONAN:\n{listing or '(pocos datos)'}\n\n"
              f"FORMATOS DISPONIBLES:\n" + "\n".join(f"- {k}: {v}" for k, v in formats.items()) + "\n\n"
              "IDEAS YA PROPUESTAS (no repetir):\n" + ("\n".join(f"- {t}" for t in before) or "(ninguna)") + "\n\n"
              "TEMAS YA HECHOS (no repetir):\n" + ("\n".join(f"- {t}" for t in taken) or "(ninguno)")))
    fresh = []
    for idea in result.get("ideas", [])[:count]:
        if not isinstance(idea, dict) or not idea.get("title"):
            continue
        if idea.get("format") not in formats:
            idea["format"] = ""
        idea["outline"] = [str(x) for x in idea.get("outline") or []][:8]
        idea["id"] = hashlib.sha256(f"{seed_key(seed)}:{idea['title']}".encode()).hexdigest()[:12]
        fresh.append(idea)
    data = {"seed": seed, "what": what, "evidence": videos[:8], "ideas": cached.get("ideas", []) + fresh,
            "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    _write(path, data)
    return data


def cached_ideas(root: Path) -> dict[str, int]:
    """seed key → how many ideas it already has (the studio shows «ver ideas (5)»)."""

    return {p.stem: len((_read(p) or {}).get("ideas", [])) for p in (root / FOLDER).glob("*.json")}


# --- saved ideas ------------------------------------------------------------------------------------------------

def saved(root: Path) -> list[dict[str, Any]]:
    return _read(root / SAVED) or []


def save(root: Path, idea: dict[str, Any], channel: str = "") -> list[dict[str, Any]]:
    keep = ("id", "title", "format", "protagonist", "angle", "hook", "outline", "footage", "why", "research")
    if not str(idea.get("title") or "").strip():
        raise ValueError("Idea sin título")
    items = [i for i in saved(root) if i.get("id") != idea.get("id")]
    items.insert(0, {**{k: idea.get(k) for k in keep}, "channel": channel, "savedAt": time.strftime("%Y-%m-%dT%H:%M:%S")})
    _write(root / SAVED, items)
    return items


def unsave(root: Path, idea_id: str) -> list[dict[str, Any]]:
    items = [i for i in saved(root) if i.get("id") != idea_id]
    _write(root / SAVED, items)
    return items


def brief(idea: dict[str, Any]) -> str:
    """idea.md next to the script of a video made from an idea."""

    lines = [f"# {idea.get('title', '')}", ""]
    for key, name in (("format", "Formato"), ("protagonist", "Protagonista"), ("angle", "Enfoque"), ("hook", "Gancho"),
                      ("footage", "Metraje"), ("why", "Por qué"), ("research", "Comprobar antes")):
        if idea.get(key):
            lines += [f"**{name}:** {idea[key]}", ""]
    if idea.get("outline"):
        lines += ["## Esquema", ""] + [f"- {x}" for x in idea["outline"]] + [""]
    return "\n".join(lines)


# --- a niche becomes a channel ----------------------------------------------------------------------------------

def make_profile(root: Path, query: str, name: str = "") -> dict[str, Any]:
    entry = _niche(root, query)
    if entry is None:
        raise ValueError("Ese nicho no está en la lista")
    slug = slugify(name or entry["name"])
    if not slug:
        raise ValueError("Nombre de canal no válido")
    path = root / "canales" / f"{slug}.yaml"
    if path.exists():
        raise ValueError(f"Ya existe el canal {slug}")
    videos = entry.get("titles") or entry.get("examples") or []
    handles = list(dict.fromkeys(str(v["channelHandle"]) for v in sorted(videos, key=lambda v: -(v.get("ratio") or 0))
                                 if v.get("channelHandle")))[:5]
    profile = {
        "ideas": {"about": f"un canal de YouTube en español de documentales sobre {entry['name']}"
                           + (f" ({entry['why']})" if entry.get("why") else ""),
                  "my_channel": "", "competitors": handles, "niches": [entry["name"]]},
        "lab": {"queries": list(dict.fromkeys([entry["query"], entry["name"]]))},
    }
    header = (f"# Perfil creado desde el radar ({time.strftime('%d-%m-%Y')}): nicho «{entry['name']}», nota {entry.get('score')}.\n"
              "# Se mezcla encima de config.yaml: añade aquí format:, brand:, music:… cuando le des identidad propia.\n\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header + yaml.safe_dump(profile, allow_unicode=True, sort_keys=False, width=110), encoding="utf-8")
    group = root / "materiales" / slug
    group.mkdir(parents=True, exist_ok=True)
    if not (group / "config.yaml").exists():
        (group / "config.yaml").write_text(f"canal: {slug}\n", encoding="utf-8")
    return {"channel": slug, "competitors": handles}
