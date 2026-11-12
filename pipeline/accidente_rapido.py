"""Short de última hora de un accidente aéreo («lo que se sabe»), solo, en cuanto la noticia empieza a moverse.

Cada `rapido.every_minutes` (60) el vigilante busca las noticias de los canales con `rapido.enabled: true`
(canales/<canal>.yaml; búsquedas `radar.news_queries`, una por turno para no gastar cuota de la API de YouTube). Una
historia que ya cubren `rapido.min_channels` (2) canales distintos y va a más de `rapido.min_speed` (2.000) visitas
por hora pasa a la IA, que dice si es un accidente o incidente aéreo real y escribe, SOLO con lo que dicen esos
vídeos:
  · un guion de ~150 palabras en cinco partes (gancho, lugar, avión, datos, cierre), sin causas ni nombres de víctimas;
  · los datos, cada uno «confirmado» solo si lo cuentan al menos dos canales distintos (y dice cuáles), si no
    «sin confirmar»; nunca especula.
El lugar sale del aeropuerto que nombran (OurAirports, dominio público), nunca de coordenadas inventadas; sin
aeropuerto identificable no se hace el vídeo. Con eso se crea materiales/<canal>/<slug>/ (guion.txt, escenas.json
vertical, .urgente): la cola lo hace antes que todo, con la voz del canal, y Telegram avisa. Nunca se sube solo: espera
en «Para subir» a que alguien lo revise.

Estado: out/_rapido/estado.json — {canal: {lastCheck, queryIndex, done: [claves de historia], made: [...]}}.
"""

from __future__ import annotations

import csv
import json
import re
import time
import unicodedata
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .context import RunContext

STATE = Path("out") / "_rapido" / "estado.json"
AIRPORTS_URL = "https://raw.githubusercontent.com/davidmegginson/ourairports-data/main/airports.csv"
AIRPORTS = Path(".cache") / "ourairports" / "airports.csv"
SOURCE_AIRPORTS = "Aeropuertos: OurAirports (dominio público)"
MODELS = {"narrowbody", "widebody", "regionaljet", "turboprop", "bizjet"}

SYSTEM = """
Eres el redactor de un canal de YouTube en {language} que explica accidentes aéreos con respeto y sin morbo. Te paso
los vídeos que hay sobre una noticia de las últimas horas (título, canal, descripción). Decide si es un accidente o
incidente real de un avión o helicóptero y, si lo es, escribe un Short de ~45-55 segundos.

Reglas, sin excepción:
- SOLO lo que dicen esos vídeos. Nada de causas, culpables, especulación ni nombres de víctimas o tripulantes.
- Un dato es "confirmed" solo si lo cuentan al menos DOS canales distintos (pon sus nombres en "sources"); si lo dice
  uno solo, "unconfirmed". Lo que no se sabe todavía (la causa, por ejemplo) puede ir como "unknown".
- El guion en cinco partes cortas, en {language}, frases de 6-14 palabras, cifras escritas como se dicen:
  "gancho" (1 frase: qué ha pasado y dónde), "lugar" (dónde exactamente, junto a qué aeropuerto),
  "avion" (qué avión y, si se sabe, qué vuelo; si no se sabe el tipo, una frase neutra),
  "datos" (2-4 frases con lo confirmado y lo que aún no se sabe, diciendo «según…»),
  "cierre" (1-2 frases: que el vídeo se actualizará cuando salga el informe preliminar).
- "airport": el código OACI (4 letras) o IATA (3) del aeropuerto que se nombra (origen, destino o el más cercano al
  lugar del suceso según los vídeos). Si no se nombra ninguno, null.
- "model": el tipo genérico del avión si se sabe: narrowbody (A320, 737…), widebody (777, A330…), regionaljet (CRJ,
  Embraer E…), turboprop (ATR, Dash 8…), bizjet (Learjet, Citation…); si no, null.
Devuelve SOLO JSON:
{{"relevant": true|false, "title": "título del Short (máx. 60 caracteres, sin clickbait morboso)",
 "airport": "KPBI"|null, "place": "ciudad, país", "aircraft": "tipo como lo dicen"|null, "model": "..."|null,
 "date": "fecha local como la dicen"|null,
 "segments": {{"gancho": "...", "lugar": "...", "avion": "...", "datos": "...", "cierre": "..."}},
 "facts": [{{"text": "dato corto (máx. 60 caracteres, con *palabra clave*)", "status": "confirmed|unconfirmed|unknown",
            "sources": ["canal", "canal"]}}]}}
""".strip()


# ── estado ──────────────────────────────────────────────────────────────────────────────────────────────────────────

def _read(root: Path) -> dict[str, Any]:
    try:
        return json.loads((root / STATE).read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def _write(root: Path, state: dict[str, Any]) -> None:
    (root / STATE).parent.mkdir(parents=True, exist_ok=True)
    (root / STATE).write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


def _settings(ctx: RunContext) -> dict[str, Any]:
    cfg = ctx.section("rapido") or {}
    return {"enabled": bool(cfg.get("enabled", False)), "every": float(cfg.get("every_minutes", 60)),
            "minChannels": int(cfg.get("min_channels", 2)), "minSpeed": float(cfg.get("min_speed", 2000)),
            "hours": float(cfg.get("hours", 12))}


# ── aeropuertos (OurAirports) ───────────────────────────────────────────────────────────────────────────────────────

def airports(root: Path) -> list[dict[str, str]]:
    path = root / AIRPORTS
    if not path.is_file() or time.time() - path.stat().st_mtime > 30 * 86400:
        path.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(AIRPORTS_URL, path)
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def find_airport(rows: list[dict[str, str]], code: str | None) -> dict[str, Any] | None:
    """Un aeropuerto por su código OACI o IATA: nombre, ciudad, país y coordenadas."""

    if not code:
        return None
    code = code.strip().upper()
    for r in rows:
        if code in (r.get("ident", "").upper(), r.get("gps_code", "").upper(), r.get("icao_code", "").upper(), r.get("iata_code", "").upper()):
            try:
                return {"code": code, "name": r["name"], "city": r.get("municipality", ""), "country": r.get("iso_country", ""),
                        "lon": float(r["longitude_deg"]), "lat": float(r["latitude_deg"])}
            except (KeyError, ValueError):
                return None
    return None


# ── historias candidatas ────────────────────────────────────────────────────────────────────────────────────────────

AVIATION = re.compile(r"(avi[oó]n|avioneta|aeronave|helic[oó]ptero|jet|vuelo|aeropuerto|pista|aterriz|despeg|"
                      r"plane|aircraft|airliner|helicopter|flight|airport|runway|crash|accidente a[eé]reo|siniestro)", re.I)


def _key(story: dict[str, Any]) -> str:
    s = unicodedata.normalize("NFKD", story["name"].lower())
    return "".join(c for c in s if c.isalnum() or c == " ").strip()


def candidates(stories: list[dict[str, Any]], done: set[str], min_channels: int, min_speed: float) -> list[dict[str, Any]]:
    """Las historias de aviación que ya se mueven (varios canales, muchas visitas por hora) y no se han hecho."""

    out = []
    for s in stories:
        titles = " ".join(v.get("title", "") for v in s["videos"])
        if _key(s) in done or s["channels"] < min_channels or s["speed"] < min_speed or not AVIATION.search(titles):
            continue
        out.append(s)
    return out


# ── el Short ────────────────────────────────────────────────────────────────────────────────────────────────────────

def _first_words(text: str, n: int = 4) -> str:
    return " ".join(re.findall(r"[\wÀ-ÿ'’.,]+", text)[:n]).strip(" .,")


def storyboard(slug: str, info: dict[str, Any], airport: dict[str, Any], now: datetime) -> dict[str, Any]:
    """El storyboard vertical: globo → mapa del aeropuerto → avión (si se sabe el tipo) → lo que se sabe → cierre."""

    seg = info["segments"]
    say = {k: {"say": _first_words(seg[k])} for k in seg}
    pos = [round(airport["lon"], 4), round(airport["lat"], 4)]
    region = f"acc-{slug}"
    stamp = now.strftime("%d %b %Y · %H:%M").upper()
    sources = sorted({s for f in info["facts"] for s in f.get("sources", [])})
    note = ("FUENTES: " + ", ".join(sources[:4]).upper())[:110] if sources else "FUENTES: MEDIOS"
    scenes: list[dict[str, Any]] = [
        {"id": "gancho", "type": "atlas-globe", "start": {"t": 0}, "theme": "paper", "enter": "fade",
         "kicker": f"ÚLTIMA HORA · {stamp}",
         "camera": [{"at": {"t": 0}, "center": pos, "zoom": 1.4}, {"at": {"t": 1.2}, "center": pos, "zoom": 3.2}],
         "points": [{"name": airport["city"] or airport["name"], "pos": pos, "at": {"t": 1.6}, "marker": "event", "accent": "danger"}],
         },
        {"id": "lugar", "type": "atlas-relief-map", "start": say["lugar"], "theme": "paper", "enter": "fade",
         "kicker": f"{airport['name'].upper()} · {airport['code']}", "sourceNote": f"{SOURCE_AIRPORTS.upper()} · RELIEVE: TERRARIUM",
         "region": region, "camera": [{"at": say["lugar"], "center": pos, "zoom": 1.2}],
         "points": [{"name": airport["name"], "pos": pos, "at": say["lugar"], "marker": "airport"}]},
    ]
    if info.get("model") in MODELS:
        scenes.append({"id": "avion", "type": "atlas-aircraft", "start": say["avion"], "theme": "paper", "enter": "fade",
                       "kicker": f"{(info.get('aircraft') or 'AVIÓN').upper()} · SILUETA GENÉRICA",
                       "model": "bizjet" if info["model"] == "bizjet" else "narrowbody", "view": "side"})
    items = []
    for i, f in enumerate(info["facts"][:5]):
        status = f.get("status") if f.get("status") in ("confirmed", "unconfirmed", "unknown") else "unconfirmed"
        src = ", ".join(f.get("sources") or []) or "—"
        items.append({"status": status, "text": f["text"][:70], "source": src.upper()[:60], "at": {**say["datos"], "offset": 0.3 + 0.9 * i}})
    if items:
        scenes.append({"id": "datos", "type": "atlas-known", "start": say["datos"], "theme": "paper", "enter": "fade",
                       "kicker": "LO QUE SE SABE", "title": {"text": "Lo que se sabe *por ahora*", "accent": "danger"},
                       "asOf": f"ACTUALIZADO: {stamp}", "sourceNote": note, "items": items})
    scenes.append({"id": "cierre", "type": "atlas-statement", "start": say["cierre"], "theme": "paper", "enter": "fade",
                   "title": {"text": "Lo actualizaremos con el *informe preliminar*", "accent": "danger"}})
    return {
        "vertical": True,
        "storyboard": {
            "meta": {"slug": slug, "title": info["title"], "brand": {"name": "ATLAS", "icon": "✦"}, "chapters": [],
                     "short": {"top": {"text": info["title"]}, "bottom": note}},
            "audio": {},
            "scenes": scenes,
        },
        "data": [{"kind": "region", "id": region, "bbox": [[pos[0] - 0.45, pos[1] - 0.3], [pos[0] + 0.45, pos[1] + 0.3]],
                  "projection": {"type": "mercator"}, "width": 3000, "zoom": 11, "margin": 0.05,
                  "water": {"seas": True, "riversBelowM": 1.0}}],
    }


def script_of(info: dict[str, Any]) -> str:
    seg = info["segments"]
    return "\n\n".join(seg[k].strip() for k in ("gancho", "lugar", "avion", "datos", "cierre") if seg.get(k)) + "\n"


def make(root: Path, channel: str, story: dict[str, Any], ask: Callable[[str, str], dict[str, Any]],
         now: datetime | None = None) -> Path | None:
    """Una historia → materiales/<canal>/<slug>/ listo para la cola (o None si no es un accidente o falta el lugar)."""

    from .doblaje import IN_SPANISH

    now = now or datetime.now()
    ctx = RunContext.create("_rapido", root=root, channel=channel)
    lang = str(ctx.section("align").get("language", "es"))[:2]
    lines = [f"- «{v['title']}» ({v['channel']}, hace {v.get('ageHours', 0):.0f} h): {' '.join(str(v.get('description') or '').split())[:600]}"
             for v in story["videos"][:6]]
    info = ask(SYSTEM.format(language=IN_SPANISH.get(lang, lang)), "VÍDEOS SOBRE LA NOTICIA:\n" + "\n".join(lines))
    if not info.get("relevant") or not isinstance(info.get("segments"), dict):
        return None
    if not all(str(info["segments"].get(k) or "").strip() for k in ("gancho", "lugar", "datos", "cierre")):
        return None
    info["segments"].setdefault("avion", "")
    if not info["segments"]["avion"].strip():
        info["model"] = None
    airport = find_airport(airports(root), info.get("airport"))
    if not airport:
        return None
    for f in info.get("facts") or []:     # «confirmado» solo con dos canales distintos que existan entre los vídeos
        known = {v["channel"] for v in story["videos"]}
        srcs = [s for s in (f.get("sources") or []) if s in known]
        f["sources"] = srcs
        if f.get("status") == "confirmed" and len(set(srcs)) < 2:
            f["status"] = "unconfirmed"
    info["facts"] = [f for f in info.get("facts") or [] if str(f.get("text") or "").strip()]
    slug = re.sub(r"[^a-z0-9]+", "-", unicodedata.normalize("NFKD", f"ultima-{airport['code']}-{now:%m%d-%H%M}").encode("ascii", "ignore").decode().lower()).strip("-")
    folder = root / "materiales" / channel / slug
    folder.parent.mkdir(parents=True, exist_ok=True)
    if not (folder.parent / "config.yaml").is_file():
        (folder.parent / "config.yaml").write_text(f"canal: {channel}\n", encoding="utf-8")
    folder.mkdir(parents=True, exist_ok=False)
    (folder / "guion.txt").write_text(script_of(info), encoding="utf-8")
    (folder / "escenas.json").write_text(json.dumps(storyboard(slug, info, airport, now), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (folder / ".urgente").write_text(now.isoformat(timespec="seconds") + "\n", encoding="utf-8")
    (folder / "fuentes.json").write_text(json.dumps({"story": story["name"], "videos": [{k: v.get(k) for k in ("title", "channel", "url", "published")} for v in story["videos"]],
                                                     "facts": info["facts"], "airport": airport}, ensure_ascii=False, indent=1), encoding="utf-8")
    return folder


def run_if_due(root: Path, api: Any = None, ask: Callable[[str, str], dict[str, Any]] | None = None, now: datetime | None = None) -> list[Path]:
    """Desde el vigilante: para cada canal con rapido.enabled, una búsqueda de noticias cada every_minutes."""

    from . import noticias
    from .radar import channels

    state = _read(root)
    made: list[Path] = []
    for channel in channels(root):
        ctx = RunContext.create("_rapido", root=root, channel=channel)
        cfg = _settings(ctx)
        if not cfg["enabled"]:
            continue
        entry = state.setdefault(channel, {"lastCheck": 0, "queryIndex": 0, "done": [], "made": []})
        if time.time() - float(entry.get("lastCheck") or 0) < cfg["every"] * 60:
            continue
        queries = [str(q) for q in (ctx.section("radar").get("news_queries") or [])]
        if not queries:
            continue
        query = queries[int(entry.get("queryIndex", 0)) % len(queries)]
        entry["queryIndex"] = int(entry.get("queryIndex", 0)) + 1
        entry["lastCheck"] = time.time()
        _write(root, state)
        try:
            if api is None:
                from .ytapi import YouTubeAPI

                api = YouTubeAPI(RunContext.create("_radar", root=root))
            videos = noticias.search(api, query, cfg["hours"], 1000, now)
        except Exception as error:
            print(f"Última hora · {channel} «{query}»: {str(error)[:160]}")
            continue
        stories = noticias.group(videos)
        for story in candidates(stories, set(entry.get("done") or []), cfg["minChannels"], cfg["minSpeed"]):
            entry["done"] = [*entry.get("done", []), _key(story)][-300:]
            _write(root, state)
            if ask is None:
                from .llm import complete_json

                def ask(system: str, user: str, _ctx: RunContext = ctx) -> dict[str, Any]:
                    return complete_json(_ctx, stage="rapido", system=system, user=user, section="planner", max_tokens=3000, use_cache=False)
            try:
                folder = make(root, channel, story, ask, now)
            except Exception as error:
                print(f"Última hora · {channel} «{story['name']}»: {str(error)[:200]}")
                continue
            if folder is None:
                continue
            entry["made"] = [*entry.get("made", []), {"at": datetime.now().isoformat(timespec="minutes"), "slug": folder.name, "story": story["name"]}][-100:]
            _write(root, state)
            made.append(folder)
            _tell(root, folder, story)
    return made


def _tell(root: Path, folder: Path, story: dict[str, Any]) -> None:
    try:
        from .notify import telegram

        telegram(RunContext.create(folder.name, root=root),
                 f"🛫 Última hora: «{story['name']}» ({story['channels']} canales, {story['speed']:,}/h).\n"
                 f"Short en preparación: {folder.name} (va primero en la cola). Revísalo antes de subirlo: "
                 f"materiales/{folder.parent.name}/{folder.name}/fuentes.json tiene de dónde sale cada dato.".replace(",", "."))
    except Exception:
        pass
