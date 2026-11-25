"""Weekly radar, step 1: what is going viral in English, from WATCHED channels, grouped into niche-formulas.

(prompts: «radar semanal de nichos virales en inglés y huecos por idioma». Steps 0, 2-5 — the ceiling of each
language, the gap per language, the opportunity score — come after the owner has seen a real week of this list.)

Not by searches (100 units each) but by a watch list of small or new English channels: every week their latest
uploads (playlistItems, 1 unit) and their figures (videos, 1 unit per 50). 500 channels ≈ 1 000 units a week.

The list grows from:
- a few seeded searches a week (`radar.semanal_semillas`, `semanal_busquedas` of them, rotating; by views, last 90 days);
- the «most popular» chart of each country in `radar.semanal_paises` (1 unit each);
- the daily radar's outliers and rising channels (their channel ids, already paid for);
- the channels you paste or import (a CSV of any niche tool: every channel link, @handle or UC… id found in it).

A channel COUNTS when it is new (created, or its first video, within `semanal_meses`, 18), has at least
`semanal_min_largos` (5) long videos (≥ `semanal_min_minutos`, 7), their MEDIAN views reach `semanal_min_mediana`
(50 000) and it has under `semanal_max_subs` (300 000) subscribers. One video that exploded is kept to watch, not as a
niche. Channels not in English are kept apart (step 3 will want them: dubbing networks).

The model groups the counting channels' titles into niche-formulas (topic + title pattern) and names them; every
figure comes from the API. A niche-formula is STRONG with 3+ new channels, or one with 8+ long videos and a median of
twice the minimum. What matters is what RISES against the previous week (channels entering, median growing).

Quota: everything goes through ytapi's ledger, never below `radar.keep_for_queue`, and at most `radar.semanal_units` a
week. What does not fit tonight goes on tomorrow from where it stopped; a week that does not finish is carried on.

    python main.py --radar-semanal                 a pass now (the rest of the week's work that fits)
    python main.py --importar-canales FILE.csv     channels into the watch list
Result: out/_radar/semanal/<año>-W<semana>.json; the list: out/_radar/vigilados.json; studio → Radar semanal.
`radar.semanal: true` runs it from the watcher on `semanal_dia` (0 = Monday) after `semanal_hora`. Off by default.
"""

from __future__ import annotations

import json
import re
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .context import RunContext

FOLDER = Path("out") / "_radar" / "semanal"
WATCH = Path("out") / "_radar" / "vigilados.json"
STAGE = "radar"

SEEDS = ["what would happen if", "why you'd never want to", "how long would you survive", "what did ancient people",
         "the untold story of", "the rise and fall of", "deep sea creatures", "prehistoric animals",
         "bodycam police", "abandoned", "how it was built", "the most dangerous", "history explained",
         "engineering disaster", "remote tribe", "true crime documentary", "what happened to", "inside the"]

GROUP_SYSTEM = """
Eres analista de nichos de YouTube. Te paso canales NUEVOS en inglés que funcionan (mediana alta de visitas en vídeos
largos), cada uno con sus títulos más vistos. Agrúpalos en NICHOS-FÓRMULA: un mismo tema contado con una misma fórmula
(el patrón de título, el tipo de pregunta o promesa). Dos canales del mismo tema con fórmulas distintas van en grupos
distintos; un canal que no se parece a ninguno va solo. Usa SOLO los ids que te paso, cada uno en un único grupo.
Devuelve SOLO JSON: {"niches": [{"name": "nombre corto en español", "topic": "el tema, en español",
  "pattern": "el patrón de título en inglés, con X donde cambia (p. ej. «Why You'd Never Want To Meet a X»)",
  "faceless": "sí | no | no se sabe (por los títulos: si parece hecho sin cara, con voz en off y archivo)",
  "channels": ["UC…"]}]}
""".strip()


# --- small helpers -------------------------------------------------------------------------------------------------

def _read(path: Path) -> Any:
    try:
        return json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return None


def _write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    temporary.replace(path)


def week_of(now: datetime) -> str:
    year, week, _ = now.isocalendar()
    return f"{year}-W{week:02d}"


def _date(text: str) -> datetime | None:
    try:
        return datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None


def _months_ago(text: str, now: datetime) -> float | None:
    when = _date(text)
    return (now - when).days / 30.44 if when else None


CHANNEL_ID = re.compile(r"\b(UC[A-Za-z0-9_-]{22})\b")
HANDLE = re.compile(r"(?:youtube\.com/)?(@[A-Za-z0-9._-]{3,30})")


def parse_channels(text: str) -> list[str]:
    """Every channel id (UC…) or @handle in any text — a pasted list, a CSV exported from a niche tool."""

    found = CHANNEL_ID.findall(text) + [h for h in HANDLE.findall(text) if not h.endswith((".com", ".csv"))]
    return list(dict.fromkeys(found))


# --- the watch list ------------------------------------------------------------------------------------------------

def load_watch(root: Path) -> dict[str, Any]:
    data = _read(root / WATCH) or {}
    data.setdefault("channels", {})
    data.setdefault("pending", [])          # @handles still to resolve into ids (1 unit each)
    return data


def add(watch: dict[str, Any], ids: list[str], source: str, now: datetime) -> int:
    """New channels into the watch list (ids) or its pending handles. How many were new."""

    added = 0
    for item in ids:
        if item.startswith("@"):
            if item not in watch["pending"] and not any(c.get("handle", "").lower() == item.lower()
                                                        for c in watch["channels"].values()):
                watch["pending"].append(item)
                added += 1
        elif item not in watch["channels"]:
            watch["channels"][item] = {"id": item, "source": source, "added": now.date().isoformat(), "status": "nuevo"}
            added += 1
    return added


def import_text(root: Path, text: str, source: str = "importado", now: datetime | None = None) -> dict[str, Any]:
    """«Importar una lista»: the channels in a pasted text or a CSV, into the watch list (measured on the next pass)."""

    now = now or datetime.now(timezone.utc)
    watch = load_watch(root)
    found = parse_channels(text)
    added = add(watch, found, source, now)
    _write(root / WATCH, watch)
    return {"found": len(found), "added": added, "watched": len(watch["channels"]) + len(watch["pending"])}


# --- one channel ---------------------------------------------------------------------------------------------------

def english(videos: list[dict[str, Any]]) -> bool | None:
    """Is the channel in English? Most of its videos that say anything (audio language, language, title words)."""

    from .idiomas import in_language

    said = [in_language(v, "en") for v in videos]
    said = [s for s in said if s is not None]
    if not said:
        return None
    return sum(said) >= 0.6 * len(said)


def evaluate(channel: dict[str, Any], videos: list[dict[str, Any]], cfg: dict[str, Any], now: datetime) -> dict[str, Any]:
    """The channel's figures from its latest uploads, and whether it counts."""

    min_seconds = 60 * float(cfg.get("semanal_min_minutos", 7))
    long = [v for v in videos if v.get("duration", 0) >= min_seconds and v.get("live", "none") == "none"]
    views = sorted(v["views"] for v in long)
    median = int(statistics.median(views)) if views else 0
    seen_all = channel.get("videoCount") is not None and len(videos) >= int(channel.get("videoCount") or 0)
    first = min((v["published"] for v in videos), default="") if seen_all and videos else ""
    dates = sorted(d for d in (_date(v["published"]) for v in long) if d)
    weeks = max(1.0, (dates[-1] - dates[0]).days / 7) if len(dates) > 1 else 1.0
    created = _months_ago(channel.get("created", ""), now)
    started = _months_ago(first, now) if first else None
    months = float(cfg.get("semanal_meses", 18))
    new = (created is not None and created <= months) or (started is not None and started <= months)
    subs = channel.get("subscribers")
    lang = english(videos)
    figures = {
        "title": channel.get("title", ""), "handle": channel.get("handle", ""), "created": channel.get("created", ""),
        "firstVideo": first or None, "subscribers": subs, "videoCount": channel.get("videoCount"),
        "uploads": channel.get("uploads", ""), "long": len(long), "median": median, "max": views[-1] if views else 0,
        "perWeek": round(len(long) / weeks, 1) if len(dates) > 1 else None,
        "minutes": round(statistics.median(v["duration"] for v in long) / 60, 1) if long else None,
        "lastUpload": max((v["published"] for v in videos), default="") or None, "new": new, "english": lang,
        "top": [{"id": v["id"], "title": v["title"], "views": v["views"], "minutes": round(v["duration"] / 60, 1),
                 "published": v["published"][:10]} for v in sorted(long, key=lambda v: -v["views"])[:8]],
    }
    floor = int(cfg.get("semanal_min_mediana", 50_000))
    if lang is False:
        status = "otro_idioma"
    elif subs is not None and subs >= int(cfg.get("semanal_max_subs", 300_000)):
        status = "grande"
    elif not new:
        status = "viejo"
    elif len(long) >= int(cfg.get("semanal_min_largos", 5)) and median >= floor:
        status = "cuenta"
    elif figures["max"] >= floor:
        status = "exito_suelto"         # one video exploded: watched, not a niche
    else:
        status = "pequeño"
    return {**figures, "status": status}


def due(entry: dict[str, Any], week: str, now: datetime) -> bool:
    """Checked this week already? Old, big or other-language channels only every 4 weeks (they rarely change)."""

    if entry.get("week") == week:
        return False
    if entry.get("status") in ("viejo", "grande", "otro_idioma") and entry.get("checked"):
        when = _date(entry["checked"])
        return when is None or (now - when).days >= 28
    return True


# --- the quota of the week -----------------------------------------------------------------------------------------

class Purse:
    """What this pass may still spend: the week's `semanal_units` minus what it spent, and never below
    `keep_for_queue` of the day's quota (measured on ytapi's own ledger)."""

    def __init__(self, api: Any, state: dict[str, Any], cfg: dict[str, Any]) -> None:
        self.api, self.state = api, state
        self.week = int(cfg.get("semanal_units", 20_000))
        self.keep = int(cfg.get("keep_for_queue", 3000))
        self.start = self._used()

    def _used(self) -> int:
        try:
            return int(self.api.quota().get("used", 0))
        except Exception:
            return 0

    def spent_now(self) -> int:
        return max(0, self._used() - self.start)

    def can(self, units: int) -> bool:
        try:
            left = int(self.api.quota().get("left", 0))
        except Exception:
            left = 0
        return (int(self.state.get("units", 0)) + self.spent_now() + units <= self.week
                and left - units >= self.keep)

    def close(self) -> None:
        self.state["units"] = int(self.state.get("units", 0)) + self.spent_now()
        self.start = self._used()


# --- growing the list ----------------------------------------------------------------------------------------------

def grow(root: Path, api: Any, cfg: dict[str, Any], watch: dict[str, Any], purse: Purse, now: datetime) -> dict[str, int]:
    """Seeded searches, the countries' «most popular» and the daily radar's channels into the watch list."""

    from .ytapi import NoKeysLeft

    floor = int(cfg.get("semanal_min_mediana", 50_000))
    min_seconds = 60 * float(cfg.get("semanal_min_minutos", 7))
    got = {"busquedas": 0, "populares": 0, "radar": 0}
    seeds = [str(s) for s in (cfg.get("semanal_semillas") or SEEDS)]
    per_week = int(cfg.get("semanal_busquedas", 6))
    start = (now.isocalendar()[1] * per_week) % max(1, len(seeds))
    for query in [seeds[(start + i) % len(seeds)] for i in range(min(per_week, len(seeds)))]:
        if not purse.can(101):
            break
        try:
            ids = api.search(query, days=90, order="viewCount", language="en")
            found = [v for v in api.videos(ids) if v["views"] >= floor and v["duration"] >= min_seconds]
        except NoKeysLeft:
            break
        got["busquedas"] += add(watch, [v["channelId"] for v in found if v.get("channelId")], f"búsqueda «{query}»", now)
    for region in [str(r) for r in (cfg.get("semanal_paises") or ["US", "GB"])]:
        if not purse.can(1):
            break
        try:
            found = [v for v in api.popular(region) if v["duration"] >= min_seconds]
        except NoKeysLeft:
            break
        got["populares"] += add(watch, [v["channelId"] for v in found if v.get("channelId")], f"populares {region}", now)
    for report in sorted((root / "out" / "_radar").glob("2*.json"))[-7:]:      # the daily radar's last week
        data = _read(report) or {}
        ids = [str(v.get("channelId")) for v in (data.get("rising") or []) if v.get("channelId")]
        for info in (data.get("channels") or {}).values():
            ids += [str(v.get("channelId")) for v in (info.get("top") or []) if v.get("channelId")]
        got["radar"] += add(watch, ids, "radar diario", now)
    return got


def resolve_pending(api: Any, watch: dict[str, Any], purse: Purse, now: datetime) -> None:
    """The pasted @handles into channel ids (1 unit each)."""

    for handle in list(watch["pending"]):
        if not purse.can(1):
            return
        try:
            channel = api.channel(handle)
        except Exception as error:
            if "Cuota" in str(error) or type(error).__name__ == "NoKeysLeft":
                return
            channel = None
        watch["pending"].remove(handle)
        if channel:
            add(watch, [channel["id"]], "pegado", now)


def refresh(api: Any, cfg: dict[str, Any], watch: dict[str, Any], week: str, purse: Purse, now: datetime) -> int:
    """This week's figures of every channel due, as far as the purse goes. How many are still due."""

    from .ytapi import NoKeysLeft

    most = int(cfg.get("semanal_max_vigilados", 1500))
    due_ids = [cid for cid, e in watch["channels"].items() if due(e, week, now)][:most]
    for start in range(0, len(due_ids), 50):
        batch = due_ids[start:start + 50]
        if not purse.can(1 + 2 * len(batch)):
            break
        try:
            infos = {c["id"]: c for c in api.channels(batch)}
        except NoKeysLeft:
            break
        for cid in batch:
            entry = watch["channels"][cid]
            info = infos.get(cid)
            if not info:
                entry.update(status="desaparecido", week=week, checked=now.isoformat(timespec="seconds"))
                continue
            subs = info.get("subscribers")
            created = _months_ago(info.get("created", ""), now)
            # plainly big, or old with too many videos to see the first one: not worth 2 units every week
            if (subs is not None and subs >= int(cfg.get("semanal_max_subs", 300_000))) or \
                    (created is not None and created > float(cfg.get("semanal_meses", 18)) and info.get("videoCount", 0) > 50):
                entry.update(title=info.get("title", ""), handle=info.get("handle", ""), subscribers=subs,
                             created=info.get("created", ""), status="grande" if subs and subs >= int(cfg.get("semanal_max_subs", 300_000)) else "viejo",
                             week=week, checked=now.isoformat(timespec="seconds"))
                continue
            if not purse.can(2):
                return len([c for c in due_ids if due(watch["channels"][c], week, now)])
            try:
                videos = api.uploads(info["uploads"], 50) if info.get("uploads") else []
            except NoKeysLeft:
                return len([c for c in due_ids if due(watch["channels"][c], week, now)])
            figures = evaluate(info, videos, cfg, now)
            history = dict(entry.get("history") or {})
            history[week] = {"median": figures["median"], "long": figures["long"], "subscribers": figures["subscribers"]}
            entry.update(figures, history=dict(sorted(history.items())[-12:]), week=week,
                         checked=now.isoformat(timespec="seconds"))
    return len([c for c in due_ids if due(watch["channels"][c], week, now)])


# --- niche-formulas ------------------------------------------------------------------------------------------------

def group(ctx: Any, counting: list[dict[str, Any]], ask: Callable[..., dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """The model's grouping of the counting channels (names, topic, pattern): words only, never figures."""

    if not counting:
        return []
    listing = "\n\n".join(f"{c['id']} · {c.get('title', '')} · {c.get('long')} vídeos largos, mediana {c.get('median')}\n"
                          + "\n".join(f"  - {t['title']}" for t in (c.get("top") or [])[:8]) for c in counting)
    if ask is None:
        from .llm import complete_json

        def ask(**kw: Any) -> dict[str, Any]:
            return complete_json(ctx, stage=STAGE, section="planner", max_tokens=4000, use_cache=False, **kw)
    try:
        answer = ask(system=GROUP_SYSTEM, user="CANALES:\n\n" + listing)
    except Exception as error:
        print(f"   Radar semanal: el modelo no agrupó ({str(error)[:120]}): un nicho por canal")
        answer = {}
    known = {c["id"] for c in counting}
    taken: set[str] = set()
    groups = []
    for raw in (answer.get("niches") or []) if isinstance(answer, dict) else []:
        ids = [str(i) for i in raw.get("channels") or [] if str(i) in known and str(i) not in taken]
        if ids:
            taken.update(ids)
            groups.append({"name": str(raw.get("name") or "")[:80], "topic": str(raw.get("topic") or "")[:200],
                           "pattern": str(raw.get("pattern") or "")[:160], "faceless": str(raw.get("faceless") or "")[:20],
                           "channels": ids})
    for c in counting:                        # anything the model left out: a niche of its own, named by its channel
        if c["id"] not in taken:
            groups.append({"name": c.get("title", c["id"]), "topic": "", "pattern": "", "faceless": "", "channels": [c["id"]],
                           "ungrouped": True})
    return groups


def figures(niche: dict[str, Any], channels: dict[str, dict[str, Any]], cfg: dict[str, Any]) -> dict[str, Any]:
    """The niche's numbers, all from the API: channels, videos, median of medians, duration, rhythm, strength."""

    members = [channels[c] for c in niche["channels"] if c in channels]
    medians = sorted(m.get("median", 0) for m in members)
    floor = int(cfg.get("semanal_min_mediana", 50_000))
    out = {
        "channelCount": len(members), "videos": sum(int(m.get("long") or 0) for m in members),
        "median": int(statistics.median(medians)) if medians else 0, "best": max(medians, default=0),
        "minutes": round(statistics.median([m["minutes"] for m in members if m.get("minutes")]), 1)
        if any(m.get("minutes") for m in members) else None,
        "perWeek": round(statistics.median([m["perWeek"] for m in members if m.get("perWeek")]), 1)
        if any(m.get("perWeek") for m in members) else None,
        "newest": max((m.get("created") or "" for m in members), default="")[:10] or None,
    }
    out["strong"] = len(members) >= 3 or any(int(m.get("long") or 0) >= 8 and int(m.get("median") or 0) >= 2 * floor
                                             for m in members)
    return out


def _match(niche: dict[str, Any], before: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The same niche last week: most channels in common (half or more of the smaller one), else the same name."""

    mine = set(niche["channels"])
    best, overlap = None, 0.0
    for old in before:
        theirs = set(old.get("channels") or [])
        share = len(mine & theirs) / max(1, min(len(mine), len(theirs)))
        if share > overlap:
            best, overlap = old, share
    if best is not None and overlap >= 0.5:
        return best
    return next((o for o in before if o.get("name", "").casefold() == niche.get("name", "").casefold()), None)


def trend(niche: dict[str, Any], before: list[dict[str, Any]]) -> dict[str, Any]:
    old = _match(niche, before)
    if old is None:
        return {"label": "nuevo", "newChannels": len(niche["channels"]), "medianChange": None}
    entered = [c for c in niche["channels"] if c not in set(old.get("channels") or [])]
    was = int((old.get("figures") or {}).get("median") or 0)
    now = int(niche["figures"]["median"])
    change = round((now - was) / was, 2) if was else None
    rising = bool(entered) or (change is not None and change >= 0.15)
    falling = change is not None and change <= -0.15 and not entered
    return {"label": "sube" if rising else "baja" if falling else "estable", "newChannels": len(entered),
            "entered": entered, "medianChange": change}


def rank(niches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Strong first, then rising, then by the median of their channels' medians."""

    order = {"sube": 0, "nuevo": 1, "estable": 2, "baja": 3}
    return sorted(niches, key=lambda n: (not n["figures"]["strong"], order.get(n["trend"]["label"], 2),
                                         -n["figures"]["median"]))


def previous(root: Path, week: str) -> dict[str, Any] | None:
    for path in sorted((root / FOLDER).glob("*-W*.json"), reverse=True):
        if path.stem < week:
            data = _read(path)
            if data and data.get("done"):
                return data
    return None


def build(ctx: Any, root: Path, watch: dict[str, Any], week: str, cfg: dict[str, Any],
          ask: Callable[..., dict[str, Any]] | None = None) -> dict[str, Any]:
    channels = watch["channels"]
    counting = [c for c in channels.values() if c.get("status") == "cuenta" and c.get("week") == week]
    niches = []
    for raw in group(ctx, counting, ask):
        raw["figures"] = figures(raw, channels, cfg)
        niches.append(raw)
    before = (previous(root, week) or {}).get("niches") or []
    for niche in niches:
        niche["trend"] = trend(niche, before)
    singles = sorted((c for c in channels.values() if c.get("status") == "exito_suelto" and c.get("week") == week),
                     key=lambda c: -(c.get("max") or 0))
    summary: dict[str, int] = {}
    for c in channels.values():
        summary[c.get("status", "nuevo")] = summary.get(c.get("status", "nuevo"), 0) + 1
    return {"niches": rank(niches), "singles": [{k: c.get(k) for k in ("id", "title", "handle", "max", "long", "median",
                                                                        "subscribers", "created", "top")} for c in singles[:40]],
            "channels": {c["id"]: {k: c.get(k) for k in ("id", "title", "handle", "created", "firstVideo", "subscribers",
                                                         "long", "median", "max", "perWeek", "minutes", "top", "source")}
                         for c in counting},
            "watch": summary}


# --- the pass ------------------------------------------------------------------------------------------------------

def run(root: Path, *, api: Any = None, ask: Callable[..., dict[str, Any]] | None = None,
        now: datetime | None = None) -> dict[str, Any]:
    """This week's pass, as far as the quota goes: grow the list once, measure what is due, and when nothing is due
    any more, group and rank. The week's file says where it stands (done or not, units spent)."""

    from .ytapi import YouTubeAPI

    ctx = RunContext.create("_radar", root=root)
    cfg = ctx.section("radar")
    now = now or datetime.now(timezone.utc)
    week = week_of(now)
    path = root / FOLDER / f"{week}.json"
    state = _read(path) or {"week": week, "started": now.isoformat(timespec="seconds"), "units": 0, "done": False}
    if state.get("done"):
        return state
    api = api or YouTubeAPI(ctx)
    if not getattr(api, "keys", True):
        raise SystemExit("El radar semanal necesita YOUTUBE_API_KEY en .env")
    watch = load_watch(root)
    purse = Purse(api, state, cfg)
    if not state.get("grown"):
        state["grown"] = grow(root, api, cfg, watch, purse, now)
        print(f"   Radar semanal: lista de vigilancia +{sum(state['grown'].values())} canales "
              f"({', '.join(f'{k} {v}' for k, v in state['grown'].items())})")
    resolve_pending(api, watch, purse, now)
    left = refresh(api, cfg, watch, week, purse, now)
    _write(root / WATCH, watch)
    purse.close()
    state.update(left=left, watched=len(watch["channels"]), updated=now.isoformat(timespec="seconds"))
    # grouped with what is measured so far, every pass: a week the quota never finishes still shows its list
    state.update(build(ctx, root, watch, week, cfg, ask), done=not left)
    if left:
        print(f"   Radar semanal: quedan {left} canales por medir esta semana (sigue en la próxima pasada) · "
              f"{state['units']} unidades gastadas")
    else:
        state["finished"] = now.isoformat(timespec="seconds")
    _write(path, state)
    strong = [n for n in state["niches"] if n["figures"]["strong"]]
    print(f"   Radar semanal {week}{'' if state['done'] else ' (a medias)'}: {len(state['niches'])} nichos-fórmula ({len(strong)} fuertes) de "
          f"{len(state['channels'])} canales que cuentan · {state['units']} unidades")
    return state


def latest(root: Path) -> dict[str, Any] | None:
    weeks = sorted((root / FOLDER).glob("*-W*.json"))
    return _read(weeks[-1]) if weeks else None


def report(root: Path) -> dict[str, Any]:
    """What the studio's page shows: the latest week (finished or not), the weeks kept, the watch list's size."""

    weeks = sorted(p.stem for p in (root / FOLDER).glob("*-W*.json"))
    current = latest(root) or {}
    done = current if current.get("niches") is not None else previous(root, "9999-W99")
    watch = load_watch(root)
    summary: dict[str, int] = {}
    for c in watch["channels"].values():
        summary[c.get("status", "nuevo")] = summary.get(c.get("status", "nuevo"), 0) + 1
    return {"current": {k: current.get(k) for k in ("week", "done", "left", "units", "watched", "updated", "grown")},
            "week": done, "weeks": weeks, "watch": summary, "pending": len(watch["pending"])}


# --- when ----------------------------------------------------------------------------------------------------------

DAYS = {"lunes": 0, "martes": 1, "miércoles": 2, "miercoles": 2, "jueves": 3, "viernes": 4, "sábado": 5, "sabado": 5,
        "domingo": 6}


def is_due(root: Path, config: dict[str, Any], now: datetime | None = None) -> bool:
    """On, and either this week's pass has not finished and it is past `semanal_dia`/`semanal_hora`, or a pass is
    half way (it goes on any night). Never twice in 3 hours."""

    from .radar import _local_now

    cfg = config.get("radar") or {}
    if not cfg.get("semanal", False):
        return False
    local = now or _local_now(config)
    state = _read(root / FOLDER / f"{week_of(local)}.json") or {}
    if state.get("done"):
        return False
    marker = root / FOLDER / ".intento"
    if marker.is_file() and time.time() - marker.stat().st_mtime < 3 * 3600:
        return False
    if state:                                            # started this week: carry on (the quota is new each day)
        return local.hour >= int(cfg.get("semanal_hora", 2))
    day = cfg.get("semanal_dia", 0)
    day = DAYS.get(str(day).lower(), day) if not isinstance(day, int) else day
    return local.weekday() > int(day) or (local.weekday() == int(day) and local.hour >= int(cfg.get("semanal_hora", 2)))


def run_if_due(root: Path) -> None:
    try:
        if not is_due(root, RunContext.create("_radar", root=root).config):
            return
    except Exception:                                  # no config.yaml (tests) or a broken one: the videos go on
        return
    marker = root / FOLDER / ".intento"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(datetime.now().isoformat())
    try:
        run(root)
    except BaseException as error:                     # SystemExit (no keys) included: the videos go on
        if isinstance(error, KeyboardInterrupt):
            raise
        print(f"Radar semanal: {str(error)[:200]}")
