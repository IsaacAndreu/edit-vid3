"""Competition radar, once a day: the best videos of your niches right now, and niches you are not in yet.

For every channel profile (canales/*.yaml):
- the competitors' videos of the last `radar.days` that got at least `radar.min_ratio` times their own channel's
  usual views (ideas.competitors), and the outliers of the niche's searches (lab.queries, any channel);
- what is new since yesterday is marked, so the studio shows «nuevo».
Then new niches: the LLM proposes `radar.new_niches` searches next to each channel's niche (and a few unrelated,
`radar.free_niches`), and each one is measured on YouTube: how many videos beat their channel by 3x, how many of those
are from small channels (the sign that a new channel can get in), median views. The best go up the list.

Needs YOUTUBE_API_KEYS. Runs from the watcher (`--vigilar`, after `radar.hour`), from the studio («Buscar ahora») or
with `python main.py --radar`. Result: out/_radar/<fecha>.json and out/_radar/nichos.json (all niches measured).
"""

from __future__ import annotations

import json
import statistics
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .context import RunContext

FOLDER = "out/_radar"
STAGE = "radar"

NICHE_SYSTEM = """
Eres analista de nichos de YouTube para un creador que hace documentales sin cara (voz en off + clips de archivo +
gráficos), en español, de 8-15 minutos. Te paso {what}. Propón EXACTAMENTE {count} nichos que NO estén en la lista de
ya conocidos. Cada uno debe poder hacerse con metraje de archivo de YouTube y tener temas para 50+ vídeos.
Devuelve SOLO JSON: {"niches": [{"name": "nombre corto en español",
  "query": "búsqueda de YouTube (2-5 palabras, en el idioma donde más vídeos hay)",
  "why": "por qué podría funcionar (1 frase)"}]}
""".strip()


DISCOVERY = ["la historia de", "el caso de", "qué pasó con", "la verdad sobre", "el misterio de", "documental",
             "por qué nadie habla de", "cómo se hizo", "el día que", "la caída de", "el hombre que", "la mujer que"]

DISCOVER_SYSTEM = """
Eres analista de nichos de YouTube. Te paso vídeos en español que han superado 3 veces o más las visitas normales de
su canal en el último mes, todos de canales pequeños (menos de 100 mil suscriptores): la señal de que un tema funciona
y aún se puede entrar. Agrúpalos en nichos (un tema que da para 50+ vídeos de documental sin cara, con metraje de
archivo) y devuelve como mucho {count} nichos que NO estén en la lista de ya conocidos, del más prometedor al menos.
Devuelve SOLO JSON: {"niches": [{"name": "nombre corto en español", "query": "búsqueda de YouTube de 2-5 palabras",
  "why": "qué tienen en común los vídeos que funcionan (1 frase)", "videos": ["ids de los vídeos del grupo"]}]}
""".strip()


def discover(ctx: RunContext, api: Any, cfg: dict[str, Any], known: list[str], today: date | None = None) -> list[dict[str, Any]]:
    """New niches found in YouTube itself, not imagined: small channels' outliers of the last month for a few broad
    documentary searches (a different few every day), grouped into niches by the LLM."""

    from . import lab
    from .llm import complete_json

    seeds = [str(q) for q in cfg.get("discovery_queries", DISCOVERY)]
    per_day = int(cfg.get("discovery_per_day", 4))
    if not seeds or per_day <= 0:
        return []
    start = ((today or date.today()).toordinal() * per_day) % len(seeds)
    chosen = [seeds[(start + i) % len(seeds)] for i in range(min(per_day, len(seeds)))]
    hits: dict[str, dict[str, Any]] = {}
    for query in chosen:
        for v in lab.outliers(ctx, query, days=30, min_ratio=3, max_subs=100_000, language="es", api=api):
            hits.setdefault(v["id"], {**_slim(v, f"búsqueda «{query}»"), "seed": query})
    if len(hits) < 3:
        return []
    listing = "\n".join(f"{v['id']} · x{v['ratio']} · {v['views']} visitas · {v['subscribers']} subs · «{v['title']}» ({v['channel']})"
                        for v in sorted(hits.values(), key=lambda v: -(v["ratio"] or 0))[:60])
    result = complete_json(ctx, stage=STAGE, section="planner", max_tokens=1800, use_cache=False,
                           system=DISCOVER_SYSTEM.replace("{count}", str(int(cfg.get("discovered_niches", 3)))),
                           user="NICHOS YA CONOCIDOS (no repetir):\n" + "\n".join(f"- {k}" for k in known[-150:])
                                + "\n\nVÍDEOS QUE FUNCIONAN:\n" + listing)
    out = []
    for niche in result.get("niches", []):
        if isinstance(niche, dict) and niche.get("query"):
            found = [hits[i] for i in niche.get("videos", []) if i in hits]
            out.append({"name": str(niche.get("name") or niche["query"]), "query": str(niche["query"]),
                        "why": str(niche.get("why") or ""), "found": found[:6]})
    return out


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


def channels(root: Path) -> list[str]:
    return sorted(p.stem for p in (root / "canales").glob("*.yaml"))


def latest(root: Path) -> dict[str, Any] | None:
    days = sorted((root / FOLDER).glob("20*.json"))
    return _read(days[-1]) if days else None


def niches(root: Path) -> list[dict[str, Any]]:
    return _read(root / FOLDER / "nichos.json") or []


def _seen_before(root: Path, today: str) -> set[str]:
    seen: set[str] = set()
    for path in sorted((root / FOLDER).glob("20*.json"))[-14:]:
        if path.stem != today:
            for info in ((_read(path) or {}).get("channels") or {}).values():
                seen |= {v["id"] for v in info.get("top", [])}
    return seen


def _slim(video: dict[str, Any], why: str) -> dict[str, Any]:
    keep = ("id", "title", "channel", "channelHandle", "views", "ratio", "subscribers", "thumbnail", "url", "published",
            "duration", "ageDays", "viewsPerDay")
    return {**{k: video.get(k) for k in keep}, "why": why}


def channel_radar(ctx: RunContext, api: Any, cfg: dict[str, Any]) -> dict[str, Any]:
    from . import lab

    days, min_ratio = int(cfg.get("days", 30)), float(cfg.get("min_ratio", 2.0))
    min_views = int(cfg.get("min_views", 5000))
    found: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for handle in [str(c) for c in ctx.section("ideas").get("competitors", []) if str(c).strip()]:
        try:
            report = lab.channel_report(ctx, handle, count=int(cfg.get("videos_per_competitor", 30)), api=api)
        except Exception as error:
            errors.append(f"{handle}: {str(error)[:120]}")
            if type(error).__name__ == "NoKeysLeft":
                return {"top": [], "errors": errors}
            continue
        for v in report["videos"]:
            if (not v["short"] and v["ageDays"] <= days and (v["ratio"] or 0) >= min_ratio and v["views"] >= min_views):
                found[v["id"]] = _slim({**v, "channel": report["title"], "subscribers": report["subscribers"],
                                        "channelHandle": report.get("handle")}, f"competidor {handle}")
    for query in [str(q) for q in ctx.section("lab").get("queries", [])][: int(cfg.get("queries", 3))]:
        try:
            for v in lab.outliers(ctx, query, days=days, min_ratio=min_ratio, min_views=min_views, api=api):
                found.setdefault(v["id"], _slim(v, f"búsqueda «{query}»"))
        except Exception as error:
            errors.append(f"«{query}»: {str(error)[:120]}")
            if type(error).__name__ == "NoKeysLeft":
                break
    top = sorted(found.values(), key=lambda v: (-(v["ratio"] or 0), -v["views"]))[: int(cfg.get("keep", 20))]
    return {"top": top, "errors": errors}


def measure(ctx: RunContext, api: Any, query: str, days: int = 120) -> dict[str, Any]:
    """How open a niche is: outliers among the search results, and how many of them come from small channels."""

    from . import lab

    videos = lab.outliers(ctx, query, days=days, api=api)
    ratios = [v["ratio"] for v in videos if v["ratio"] is not None]
    hits = [v for v in videos if (v["ratio"] or 0) >= 3]
    small = [v for v in hits if v["subscribers"] is not None and v["subscribers"] < 100_000]
    median_ratio = round(statistics.median(ratios), 2) if ratios else 0.0
    score = round(min(10.0, len(hits) * 0.4 + len(small) * 0.8 + max(0.0, median_ratio - 1) * 2), 1)
    return {"videos": len(videos), "hits": len(hits), "smallHits": len(small), "medianRatio": median_ratio,
            "medianViews": int(statistics.median([v["views"] for v in videos])) if videos else 0, "score": score,
            "examples": [_slim(v, "") for v in sorted(hits, key=lambda v: -(v["ratio"] or 0))[:4]],
            # what works there, for «Ideas para este nicho» and for its competitors if it becomes a channel
            "titles": [{k: v.get(k) for k in ("title", "channel", "channelHandle", "views", "ratio")}
                       for v in sorted(videos, key=lambda v: -(v["ratio"] or 0))[:15]]}


def propose_niches(ctx: RunContext, about: str, known: list[str], count: int) -> list[dict[str, Any]]:
    from .llm import complete_json

    result = complete_json(
        ctx, stage=STAGE, section="planner", max_tokens=1500, use_cache=False,
        system=NICHE_SYSTEM.replace("{what}", about).replace("{count}", str(count)),
        user="NICHOS YA CONOCIDOS (no repetir):\n" + "\n".join(f"- {k}" for k in known[-150:]))
    return [n for n in result.get("niches", []) if isinstance(n, dict) and n.get("query")][:count]


def run(root: Path, *, force: bool = False) -> Path:
    from .ytapi import NoKeysLeft, YouTubeAPI

    base = RunContext.create("_radar", root=root)
    today = _local_now(base.config).date().isoformat()
    target = root / FOLDER / f"{today}.json"
    if target.is_file() and not force:
        return target
    cfg = base.section("radar")
    api = YouTubeAPI(base)
    if not api.keys:
        raise SystemExit("El radar necesita YOUTUBE_API_KEYS en .env")
    seen = _seen_before(root, today)
    report: dict[str, Any] = {"date": today, "started": datetime.now().isoformat(timespec="seconds"), "channels": {}}
    if cfg.get("rising", True):                    # small channels with far more views than subscribers, first
        try:
            from . import revelacion

            report["rising"] = revelacion.scan(root, api)
        except NoKeysLeft:
            report["rising"] = []
        except Exception as error:
            print(f"   canales revelación: {str(error)[:160]}")
    measured = niches(root)
    known = [n["name"] for n in measured] + [n["query"] for n in measured]
    out_of_quota = False
    for name in channels(root):
        ctx = RunContext.create("_radar", root=root, channel=name)
        print(f"Radar · {name}")
        info = channel_radar(ctx, api, cfg)
        for video in info["top"]:
            video["new"] = video["id"] not in seen
        report["channels"][name] = info
        out_of_quota = any("Cuota" in e for e in info["errors"])
        known += [str(n) for n in ctx.section("ideas").get("niches", [])] + [str(q) for q in ctx.section("lab").get("queries", [])]
        if out_of_quota:
            break
    # new niches: next to each channel's, and some unrelated
    asks = [(name, f"el nicho de este canal: {RunContext.create('_radar', root=root, channel=name).section('ideas').get('about', name)}. "
                   "Busca nichos CERCANOS (mismo público, otro tema)", int(cfg.get("new_niches", 1)))
            for name in report["channels"]]
    asks.append(("libre", "nada: busca nichos de documental en español que crezcan ahora, de cualquier tema",
                 int(cfg.get("free_niches", 2))))
    fresh: list[dict[str, Any]] = []
    if not out_of_quota and cfg.get("discovery", True):        # niches found in YouTube itself
        try:
            for niche in discover(base, api, cfg, known):
                stats = measure(base, api, niche["query"], int(cfg.get("niche_days", 120)))
                entry = {"name": niche["name"], "query": niche["query"], "why": niche["why"], "near": "descubierto",
                         "date": today, **stats}
                if niche["found"]:                             # the videos that revealed it come first
                    entry["examples"] = (niche["found"] + entry["examples"])[:6]
                fresh.append(entry)
                known += [entry["name"], entry["query"]]
                print(f"   nicho descubierto «{entry['name']}»: nota {entry['score']} · {entry['smallHits']} éxitos de canales pequeños")
        except NoKeysLeft:
            out_of_quota = True
        except Exception as error:
            print(f"   descubrir nichos: {str(error)[:160]}")
    if not out_of_quota and cfg.get("gaps", True):             # «Huecos»: demand against competition (huecos.py)
        try:
            from . import huecos

            signals = [f"canal pequeño que crece: {c.get('format') or c.get('title')} ({c.get('niche') or ''})"
                       for c in report.get("rising") or [] if (c.get("fit") or 0) >= 5]
            signals += [f"nicho descubierto: {n['name']} — {n.get('why', '')}" for n in fresh]
            report["gaps"] = huecos.scan(root, api, signals, known, today)
        except NoKeysLeft:
            out_of_quota = True
        except Exception as error:
            print(f"   huecos: {str(error)[:160]}")
    for near, about, count in asks:
        if out_of_quota or count <= 0:
            break
        try:
            proposals = propose_niches(base, about, known, count)
        except Exception as error:
            print(f"   nichos ({near}): {str(error)[:120]}")
            continue
        for niche in proposals:
            try:
                stats = measure(base, api, str(niche["query"]), int(cfg.get("niche_days", 120)))
            except NoKeysLeft:
                out_of_quota = True
                break
            except Exception as error:
                print(f"   «{niche['query']}»: {str(error)[:120]}")
                continue
            entry = {"name": str(niche.get("name") or niche["query"]), "query": str(niche["query"]),
                     "why": str(niche.get("why") or ""), "near": near, "date": today, **stats}
            fresh.append(entry)
            known += [entry["name"], entry["query"]]
            print(f"   nicho «{entry['name']}»: nota {entry['score']} · {entry['hits']} outliers ({entry['smallHits']} de canales pequeños)")
    measured = sorted(measured + fresh, key=lambda n: -n["score"])[:200]
    _write(root / FOLDER / "nichos.json", measured)
    report["niches"] = fresh
    if not out_of_quota and cfg.get("news", True):            # «Noticias del día» (pipeline/noticias.py)
        try:
            from . import noticias

            report["news"] = noticias.scan(root, api)
        except Exception as error:
            print(f"   noticias: {str(error)[:160]}")
    report["outOfQuota"] = out_of_quota
    report["finished"] = datetime.now().isoformat(timespec="seconds")
    _write(target, report)
    _notify(base, report)
    return target


def _notify(ctx: RunContext, report: dict[str, Any]) -> None:
    from . import notify

    lines = []
    if report.get("rising"):
        from .revelacion import telegram_lines as rising_lines

        rising = rising_lines(report["rising"])
        if rising:
            lines += ["🚀 Canales pequeños que revientan (formatos para copiar):", *rising, ""]
    for name, info in report["channels"].items():
        new = [v for v in info["top"] if v.get("new")][:3]
        if new:
            lines.append(f"{name}:")
            lines += [f"  x{v['ratio']} · {v['views']:,} · {v['title']} ({v['channel']})".replace(",", ".") for v in new]
    if report.get("news"):
        from .noticias import telegram_lines

        news = telegram_lines(report["news"])
        if news:
            lines += ["📰 Noticias que suben ahora (vídeo en 24 h):", *news]
    if report.get("gaps"):
        from .huecos import telegram_lines as gap_lines

        gaps = gap_lines(report["gaps"])
        if gaps:
            lines += ["🎯 Huecos: público y poca competencia en español:", *gaps, ""]
    best = sorted(report.get("niches", []), key=lambda n: -n["score"])[:3]
    if best:
        lines.append("Nichos nuevos:")
        lines += [f"  {n['name']} · nota {n['score']} · {n['smallHits']} éxitos de canales pequeños" for n in best]
    if lines:
        try:
            notify.send(ctx, f"📡 Radar del día · {report['date']}", "\n".join(lines))
        except Exception:
            pass


def due(root: Path, config: dict[str, Any]) -> bool:
    """For the watcher: on, not done today, and past `radar.hour`."""

    cfg = config.get("radar") or {}
    if not cfg.get("enabled", True) or (root / FOLDER / f"{_local_now(config).date().isoformat()}.json").is_file():
        return False
    marker = root / FOLDER / ".intento"
    if marker.is_file() and time.time() - marker.stat().st_mtime < 3 * 3600:    # failed earlier today: not in a loop
        return False
    return _local_now(config).hour >= int(cfg.get("hour", 13))


def _local_now(config: dict[str, Any]) -> datetime:
    """Your clock, not the server's (a VPS runs in UTC): radar.timezone, else mychannel.timezone, else Madrid."""

    from zoneinfo import ZoneInfo

    zone = (config.get("radar") or {}).get("timezone") or (config.get("mychannel") or {}).get("timezone") or "Europe/Madrid"
    try:
        return datetime.now(ZoneInfo(str(zone)))
    except Exception:
        return datetime.now()


def run_if_due(root: Path) -> None:
    try:
        if not due(root, RunContext.create("_radar", root=root).config):
            return
    except Exception:                           # no config.yaml (tests) or a broken one: the videos go on
        return
    marker = root / FOLDER / ".intento"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(datetime.now().isoformat())
    try:
        print(f"Radar de competencia → {run(root).relative_to(root)}")
    except BaseException as error:              # SystemExit (no keys) included: the videos go on
        if isinstance(error, KeyboardInterrupt):
            raise
        print(f"Radar: {str(error)[:200]}")
