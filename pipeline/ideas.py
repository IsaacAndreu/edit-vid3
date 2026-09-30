"""Three video ideas a day, based on what works for the competition and on your own channel.

`python main.py --ideas` reads the latest videos of your channel and of the competitor channels in
config.yaml (`ideas:`) with yt-dlp — no YouTube API key — and scores each video against its own
channel: views / median views of that channel's recent videos. Outliers (≥ `min_ratio`) are what
the audience is asking for right now. The LLM turns them, plus your channel's best videos, into
3 ideas (title, protagonist, angle, hook, why) that are not already made or suggested before.
With YouTube API keys (YOUTUBE_API_KEYS) it also searches the whole niche (`lab.queries`) for
outliers of any channel, and reads the videos you saved in the panel.
Result: out/_ideas/<date>.md, and the same by email/Telegram if configured.
"""

from __future__ import annotations

import json
import statistics
from datetime import date
from pathlib import Path
from typing import Any

from .context import RunContext
from .llm import complete_json
from . import notify

STAGE = "ideas"
HISTORY = "out/_ideas/historial.json"


def ideas_dir(ctx: RunContext) -> Path:
    """out/_ideas/<canal>/ (out/_ideas/ without channel profiles)."""

    return ctx.root / "out" / "_ideas" / ctx.channel if ctx.channel else ctx.root / "out" / "_ideas"


def outliers_path(ctx: RunContext) -> Path | None:
    """The competition's outliers saved by the last --ideas: the series' own, the channel's, or the old global file."""

    folder = ideas_dir(ctx)
    for path in ([folder / f"outliers-{ctx.series}.json"] if ctx.series else []) + [
            folder / "outliers.json", ctx.root / "out" / "_ideas" / "outliers.json"]:
        if path.is_file():
            return path
    return None


def history_path(ctx: RunContext) -> Path:
    path = ideas_dir(ctx) / "historial.json"
    old = ctx.root / HISTORY          # before channel profiles: the gymnastics channel's history
    return old if not path.is_file() and old.is_file() and ctx.channel == "gimnasia" else path

ABOUT = ('un canal de YouTube en español de documentales deportivos (historias de atletas: gimnasia, '
         'atletismo, patinaje artístico…) con el formato "historia de un atleta de ~10 min"')

SYSTEM = """
Eres el estratega de contenido de {about}. Te paso los vídeos que MEJOR están funcionando ahora mismo en la competencia
(outliers: muchas más visitas que la media de su canal) y los mejores vídeos del propio canal.
Propón EXACTAMENTE {count} idea(s) nueva(s). Devuelve SOLO JSON:
{"ideas": [{"title": "título en español, gancho fuerte, máx. 70 caracteres",
            "protagonist": "atleta (o tema) principal",
            "sport": "deporte o sector",
            "angle": "el enfoque en 1-2 frases: qué historia se cuenta y por qué engancha",
            "hook": "las 2-3 primeras frases del vídeo, en español, que obliguen a quedarse",
            "why": "qué outliers/datos de la lista lo respaldan (cita títulos o canales)",
            "research": "qué hay que comprobar/buscar antes de escribir el guion"}]}
Reglas: no repitas temas ya hechos ni ya sugeridos (te los paso); no copies títulos: inspírate en
el patrón ({pattern}).
MUY IMPORTANTE: en "title", "angle" y "hook" NO afirmes datos concretos que no estén en la lista que
te paso (edades, fechas, número de títulos o medallas, lesiones, declaraciones de nadie). Escribe el
gancho con la tensión de la historia sin cifras inventadas ("una gimnasta que casi lo deja", no
"tres lesiones de rodilla"). Cualquier dato que la historia necesite va en "research" para comprobarlo.
""".strip()


def channel_url(handle_or_url: str) -> str:
    value = handle_or_url.strip()
    if value.startswith("http"):
        return value.rstrip("/") + ("" if value.rstrip("/").endswith("/videos") else "/videos")
    return f"https://www.youtube.com/{value if value.startswith('@') else '@' + value}/videos"


def channel_videos(ctx: RunContext, handle: str, limit: int) -> dict[str, Any]:
    """Latest videos of a channel (newest first) with their views, via yt-dlp flat extraction."""

    import yt_dlp

    from .sourcing import _cookies_file

    options: dict[str, Any] = {"quiet": True, "extract_flat": "in_playlist", "playlistend": limit,
                               "skip_download": True}
    cookies = _cookies_file(ctx.section("sourcing").get("youtube", {}))
    if cookies and cookies.is_file():
        options["cookiefile"] = str(cookies)
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(channel_url(handle), download=False)
    videos = [{"id": e.get("id"), "title": e.get("title") or "", "views": e.get("view_count"),
               "duration": e.get("duration")}
              for e in info.get("entries") or [] if e and e.get("id")]
    return {"channel": info.get("channel") or handle, "subscribers": info.get("channel_follower_count"),
            "videos": videos}


def score(channel: dict[str, Any], min_duration: int = 240) -> list[dict[str, Any]]:
    """Each long video's views divided by the median of its channel (Shorts and unknown views ignored)."""

    long = [v for v in channel["videos"] if v["views"] is not None and (v["duration"] or 0) >= min_duration]
    if not long:
        return []
    median = statistics.median(v["views"] for v in long) or 1
    return [{**v, "channel": channel["channel"], "ratio": round(v["views"] / median, 1),
             "url": f"https://www.youtube.com/watch?v={v['id']}"} for v in long]


def _api(ctx: RunContext):
    """The YouTube Data API client when keys are configured (more data, whole-niche search), else None."""

    from .ytapi import YouTubeAPI

    api = YouTubeAPI(ctx)
    return api if api.keys else None


def _channel_scored(ctx: RunContext, api: Any, handle: str, limit: int) -> list[dict[str, Any]]:
    if api is None:
        return score(channel_videos(ctx, handle, limit))
    from . import lab

    report = lab.channel_report(ctx, handle, count=limit, api=api)
    return [{**v, "channel": report["title"], "subscribers": report["subscribers"]}
            for v in report["videos"] if not v["short"] and v["ratio"] is not None]


def done_topics(ctx: RunContext) -> list[str]:
    topics = []
    for folder in (ctx.root / "materiales").iterdir() if (ctx.root / "materiales").is_dir() else []:
        title = folder / "titulo.txt"
        topics.append(title.read_text("utf-8").strip() if title.is_file() else folder.name)
    history = history_path(ctx)
    if history.is_file():
        topics += [i["title"] for i in json.loads(history.read_text("utf-8"))]
    return topics


def gather(ctx: RunContext) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(outliers of the competition and of the niche's searches, the channel's own best videos)."""

    cfg = ctx.section("ideas")
    limit = int(cfg.get("videos_per_channel", 40))
    competitors = [str(c) for c in cfg.get("competitors", []) if str(c).strip()]
    mine = str(cfg.get("my_channel") or "").strip()
    if not competitors and not mine and not ctx.section("lab").get("queries"):
        raise ValueError("Configura ideas.my_channel y/o ideas.competitors en config.yaml")
    min_ratio = float(cfg.get("min_ratio", 2.0))
    api = _api(ctx)
    outliers: list[dict[str, Any]] = []
    for handle in competitors:
        try:
            outliers += [v for v in _channel_scored(ctx, api, handle, limit) if v["ratio"] >= min_ratio]
        except Exception as error:  # one unreachable channel must not stop the ideas
            print(f"   {handle}: {str(error)[:120]}")
    if api:   # with API keys: also the outliers of the whole niche, not only of known channels
        from . import lab

        lab_cfg = ctx.section("lab")
        for query in lab_cfg.get("queries", [])[: int(lab_cfg.get("ideas_queries", 6))]:
            try:
                outliers += lab.outliers(ctx, str(query), days=int(lab_cfg.get("ideas_days", 180)),
                                         min_ratio=min_ratio, api=api)
            except Exception as error:
                print(f"   búsqueda «{query}»: {str(error)[:120]}")
                if type(error).__name__ == "NoKeysLeft":
                    break
    outliers = list({v["id"]: v for v in sorted(outliers, key=lambda v: v["ratio"] or 0)}.values())
    outliers.sort(key=lambda v: -(v["ratio"] or 0))
    best_mine: list[dict[str, Any]] = []
    if mine:
        try:
            best_mine = sorted(_channel_scored(ctx, api, mine, limit), key=lambda v: -v["views"])[:8]
        except Exception as error:
            print(f"   {mine}: {str(error)[:120]}")
    return outliers, best_mine


def propose(ctx: RunContext, outliers: list[dict[str, Any]], best_mine: list[dict[str, Any]], count: int,
            taken: list[str]) -> list[dict[str, Any]]:
    cfg = ctx.section("ideas")
    from .lab import saved

    marked = saved(ctx)[:10]
    listing = "\n".join(f"- [{v['channel']}] x{v['ratio']} · {v['views']} visitas · {v['title']}" for v in outliers[:40])
    own = "\n".join(f"- {v['views']} visitas (x{v['ratio']}) · {v['title']}" for v in best_mine)
    niches = ", ".join(cfg.get("niches", ["gimnasia", "atletismo", "patinaje artístico"]))
    system = SYSTEM.replace("{about}", str(cfg.get("about") or ABOUT)).replace(
        "{pattern}", str(cfg.get("pattern") or "atleta + tensión + figura famosa")).replace("{count}", str(count))
    result = complete_json(
        ctx, stage=STAGE, section="planner", system=system, max_tokens=1200 * count, use_cache=False,
        user=(f"NICHOS DEL CANAL: {niches}\n\nOUTLIERS DE LA COMPETENCIA:\n{listing or '(ninguno)'}\n\n"
              f"MEJORES VÍDEOS DEL CANAL:\n{own or '(sin datos)'}\n\n"
              f"VÍDEOS QUE EL DUEÑO GUARDÓ COMO REFERENCIA:\n"
              + ("\n".join(f"- {v.get('title')} ({v.get('channel')})" + (f" · nota: {v['note']}" if v.get("note") else "")
                           for v in marked) or "(ninguno)") + "\n\n"
              f"TEMAS YA HECHOS O YA SUGERIDOS (no repetir):\n" + "\n".join(f"- {t}" for t in taken[-60:])),
    )
    return [i for i in result.get("ideas", []) if isinstance(i, dict) and i.get("title")][:count]


def _idea_lines(idea: dict[str, Any], heading: str) -> list[str]:
    return [f"## {heading}", "",
            f"**Protagonista:** {idea.get('protagonist', '—')} · {idea.get('sport', '')}", "",
            f"**Enfoque:** {idea.get('angle', '')}", "", f"**Hook:** {idea.get('hook', '')}", "",
            f"**Por qué:** {idea.get('why', '')}", "", f"**Comprobar antes:** {idea.get('research', '')}", ""]


def _save_outliers(ctx: RunContext, outliers: list[dict[str, Any]]) -> None:
    folder = ideas_dir(ctx)
    folder.mkdir(parents=True, exist_ok=True)
    name = f"outliers-{ctx.series}.json" if ctx.series else "outliers.json"
    (folder / name).write_text(json.dumps(outliers[:40], ensure_ascii=False, indent=1), encoding="utf-8")


def _remember(ctx: RunContext, ideas: list[dict[str, Any]], today: str) -> None:
    history = history_path(ctx)
    past = json.loads(history.read_text("utf-8")) if history.is_file() else []
    folder = ideas_dir(ctx)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "historial.json").write_text(json.dumps(past + [
        {"date": today, "title": i["title"], **({"serie": i["serie"]} if i.get("serie") else {})} for i in ideas],
        ensure_ascii=False, indent=1), encoding="utf-8")


def run(ctx: RunContext) -> Path:
    outliers, best_mine = gather(ctx)
    print(f"   {len(outliers)} outliers en la competencia · {len(best_mine)} mejores vídeos propios")
    ideas = propose(ctx, outliers, best_mine, 3, done_topics(ctx))
    today = date.today().isoformat()
    lines = [f"# 3 ideas · {today}" + (f" · serie {ctx.series}" if ctx.series else ""), ""]
    for n, idea in enumerate(ideas, start=1):
        lines += _idea_lines(idea, f"{n}. {idea['title']}")
    if outliers:
        lines += ["## Lo que mejor funciona ahora en la competencia", ""]
        lines += [f"- x{v['ratio']} · {v['views']} visitas · [{v['channel']}] [{v['title']}]({v['url']})" for v in outliers[:10]]
    _save_outliers(ctx, outliers)                       # for thumbnail/title patterns
    folder = ideas_dir(ctx)
    out = folder / (f"{today}-{ctx.series}.md" if ctx.series else f"{today}.md")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _remember(ctx, [{**i, "serie": ctx.series} for i in ideas], today)
    body = "\n\n".join(f"{n}. {i['title']}\n{i.get('angle', '')}\nHook: {i.get('hook', '')}" for n, i in enumerate(ideas, 1))
    notify.send(ctx, f"3 ideas de vídeo{' · ' + ctx.channel if ctx.channel else ''} · {today}", body + f"\n\n(detalle en {out.relative_to(ctx.root)})")
    return out


def series_of(ctx: RunContext) -> dict[str, dict[str, Any]]:
    """The channel's series (canales/<canal>.yaml → series:), in the order they are written."""

    from .context import channel_profile

    return dict(channel_profile(ctx.root, ctx.channel).get("series") or {}) if ctx.channel else {}


def weekly(channel: str, root: Path | None = None) -> Path:
    """One idea per series of the channel: the week's test plan (out/_ideas/<canal>/semana-<fecha>.md)."""

    from .context import PROJECT_ROOT

    base = RunContext.create("_ideas", root=root or PROJECT_ROOT, channel=channel)
    catalog = series_of(base)
    if not catalog:
        raise ValueError(f"El canal {channel} no tiene series (canales/{channel}.yaml → series:)")
    today = date.today().isoformat()
    taken = done_topics(base)
    lines = [f"# Semana de prueba · {channel} · {today}", "",
             f"Un vídeo de cada serie ({len(catalog)}). Publícalos en días distintos a la misma hora; "
             "en 7 días compara con `python main.py --series " + channel + "`.", ""]
    picked: list[dict[str, Any]] = []
    for n, (name, spec) in enumerate(catalog.items(), start=1):
        ctx = RunContext.create("_ideas", root=base.root, channel=channel, series=name)
        print(f"   serie {name}…")
        outliers, best_mine = gather(ctx)
        ideas = propose(ctx, outliers, best_mine, 1, taken)
        _save_outliers(ctx, outliers)
        if not ideas:
            lines += [f"## {n}. {name}: sin idea (revisa el log)", ""]
            continue
        idea = {**ideas[0], "serie": name}
        taken.append(idea["title"])
        picked.append(idea)
        lines += _idea_lines(idea, f"{n}. [{name}] {idea['title']}")
        lines += [f"**Para prepararlo:** `materiales/<slug>/config.yaml` → `canal: {channel}` y `serie: {name}`", ""]
    out = ideas_dir(base) / f"semana-{today}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _remember(base, picked, today)
    notify.send(base, f"Semana de prueba · {channel} · {today}",
                "\n\n".join(f"[{i['serie']}] {i['title']}\nHook: {i.get('hook', '')}" for i in picked)
                + f"\n\n(detalle en {out.relative_to(base.root)})")
    return out
