"""Three video ideas a day, based on what works for the competition and on your own channel.

`python main.py --ideas` reads the latest videos of your channel and of the competitor channels in
config.yaml (`ideas:`) with yt-dlp — no YouTube API key — and scores each video against its own
channel: views / median views of that channel's recent videos. Outliers (≥ `min_ratio`) are what
the audience is asking for right now. The LLM turns them, plus your channel's best videos, into
3 ideas (title, protagonist, angle, hook, why) that are not already made or suggested before.
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

SYSTEM = """
Eres el estratega de contenido de un canal de YouTube en español de documentales deportivos
(historias de atletas: gimnasia, atletismo, patinaje artístico…) con el formato "historia de un
atleta de ~10 min". Te paso los vídeos que MEJOR están funcionando ahora mismo en la competencia
(outliers: muchas más visitas que la media de su canal) y los mejores vídeos del propio canal.
Propón EXACTAMENTE 3 ideas nuevas. Devuelve SOLO JSON:
{"ideas": [{"title": "título en español, gancho fuerte, máx. 70 caracteres",
            "protagonist": "atleta (o tema) principal",
            "sport": "deporte",
            "angle": "el enfoque en 1-2 frases: qué historia se cuenta y por qué engancha",
            "hook": "las 2-3 primeras frases del vídeo, en español, que obliguen a quedarse",
            "why": "qué outliers/datos de la lista lo respaldan (cita títulos o canales)",
            "research": "qué hay que comprobar/buscar antes de escribir el guion"}]}
Reglas: no repitas temas ya hechos ni ya sugeridos (te los paso); no copies títulos: inspírate en
el patrón (atleta + tensión + figura famosa).
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


def done_topics(ctx: RunContext) -> list[str]:
    topics = []
    for folder in (ctx.root / "materiales").iterdir() if (ctx.root / "materiales").is_dir() else []:
        title = folder / "titulo.txt"
        topics.append(title.read_text("utf-8").strip() if title.is_file() else folder.name)
    history = ctx.root / HISTORY
    if history.is_file():
        topics += [i["title"] for i in json.loads(history.read_text("utf-8"))]
    return topics


def run(ctx: RunContext) -> Path:
    cfg = ctx.section("ideas")
    limit = int(cfg.get("videos_per_channel", 40))
    competitors = [str(c) for c in cfg.get("competitors", []) if str(c).strip()]
    mine = str(cfg.get("my_channel") or "").strip()
    if not competitors and not mine:
        raise ValueError("Configura ideas.my_channel y/o ideas.competitors en config.yaml")
    outliers: list[dict[str, Any]] = []
    for handle in competitors:
        try:
            outliers += [v for v in score(channel_videos(ctx, handle, limit)) if v["ratio"] >= float(cfg.get("min_ratio", 2.0))]
        except Exception as error:  # one unreachable channel must not stop the ideas
            print(f"   {handle}: {str(error)[:120]}")
    outliers.sort(key=lambda v: -v["ratio"])
    best_mine: list[dict[str, Any]] = []
    if mine:
        try:
            best_mine = sorted(score(channel_videos(ctx, mine, limit)), key=lambda v: -v["views"])[:8]
        except Exception as error:
            print(f"   {mine}: {str(error)[:120]}")
    print(f"   {len(outliers)} outliers en la competencia · {len(best_mine)} mejores vídeos propios")
    listing = "\n".join(f"- [{v['channel']}] x{v['ratio']} · {v['views']} visitas · {v['title']}" for v in outliers[:25])
    own = "\n".join(f"- {v['views']} visitas (x{v['ratio']}) · {v['title']}" for v in best_mine)
    niches = ", ".join(cfg.get("niches", ["gimnasia", "atletismo", "patinaje artístico"]))
    result = complete_json(
        ctx, stage=STAGE, section="planner", system=SYSTEM, max_tokens=3000, use_cache=False,
        user=(f"NICHOS DEL CANAL: {niches}\n\nOUTLIERS DE LA COMPETENCIA:\n{listing or '(ninguno)'}\n\n"
              f"MEJORES VÍDEOS DEL CANAL:\n{own or '(sin datos)'}\n\n"
              f"TEMAS YA HECHOS O YA SUGERIDOS (no repetir):\n" + "\n".join(f"- {t}" for t in done_topics(ctx)[-60:])),
    )
    ideas = [i for i in result.get("ideas", []) if isinstance(i, dict) and i.get("title")][:3]
    today = date.today().isoformat()
    lines = [f"# 3 ideas · {today}", ""]
    for n, idea in enumerate(ideas, start=1):
        lines += [f"## {n}. {idea['title']}", "",
                  f"**Protagonista:** {idea.get('protagonist', '—')} · {idea.get('sport', '')}", "",
                  f"**Enfoque:** {idea.get('angle', '')}", "", f"**Hook:** {idea.get('hook', '')}", "",
                  f"**Por qué:** {idea.get('why', '')}", "", f"**Comprobar antes:** {idea.get('research', '')}", ""]
    if outliers:
        lines += ["## Lo que mejor funciona ahora en la competencia", ""]
        lines += [f"- x{v['ratio']} · {v['views']} visitas · [{v['channel']}] [{v['title']}]({v['url']})" for v in outliers[:10]]
    (ctx.root / "out" / "_ideas").mkdir(parents=True, exist_ok=True)
    (ctx.root / "out" / "_ideas" / "outliers.json").write_text(json.dumps(outliers[:40], ensure_ascii=False, indent=1),
                                                             encoding="utf-8")    # for thumbnail/title patterns
    out = ctx.root / "out" / "_ideas" / f"{today}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    history = ctx.root / HISTORY
    past = json.loads(history.read_text("utf-8")) if history.is_file() else []
    history.write_text(json.dumps(past + [{"date": today, "title": i["title"]} for i in ideas], ensure_ascii=False, indent=1),
                       encoding="utf-8")
    body = "\n\n".join(f"{n}. {i['title']}\n{i.get('angle', '')}\nHook: {i.get('hook', '')}" for n, i in enumerate(ideas, 1))
    notify.send(ctx, f"3 ideas de vídeo · {today}", body + f"\n\n(detalle en {out.relative_to(ctx.root)})")
    return out
