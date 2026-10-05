"""The publishing calendar: which video goes out on which day in each channel, what is missing and when.

- Every channel has publishing days and a time (studio → Calendario → Días de publicación; default Monday,
  Wednesday and Friday at 18:00). out/_calendario.json keeps it, with the days you pin a video to by hand.
- plan(): the next weeks, slot by slot. A slot holds the video published that day, the one you pinned there, or the
  next one of the channel by readiness (finished first, then in production, then waiting for its script/voice).
  When a video finishes it simply takes the first free slot of its channel.
- The queue makes first the video whose slot comes first (main.pending_slugs).
- A slot without a video, or whose video will not be ready, has a deadline: slot − `lead_hours` (36 h) is the last
  moment to have the script and the voice uploaded (a video takes ~2 h, the rest is margin to review it).
- The bot uses it: every morning what goes out today (with «Ya está subido»), the gaps of the coming days with their
  deadline, the channels with few videos in reserve; /hoy, /semana, /huecos; a summary every Sunday; and the views of
  each published video at 48 h and 7 days against the channel's usual.
- The board (studio → Tablero): idea → falta voz → en cola → hecho → subido, with the ideas saved in Competencia.
"""

from __future__ import annotations

import json
import re
import statistics
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

FILE = "out/_calendario.json"
WEEKDAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
SHORT = ["L", "M", "X", "J", "V", "S", "D"]
DEFAULT_DAYS = [0, 2, 4]
DEFAULT_TIME = "18:00"
READINESS = {"hecho": 0, "haciendo": 1, "en cola": 2, "error": 2, "falta voz": 3, "falta guion": 3}


# --- storage ----------------------------------------------------------------------------------------------------

def load(root: Path) -> dict[str, Any]:
    try:
        data = json.loads((root / FILE).read_text("utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save(root: Path, data: dict[str, Any]) -> None:
    path = root / FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def channels(root: Path) -> list[str]:
    from .context import video_folders
    from .web import _channel_of, channels as profiles

    found = set(profiles(root))
    for folder in video_folders(root):
        if not any(p.startswith("_") for p in folder.relative_to(root / "materiales").parts):
            found.add(_channel_of(root, folder))
    return sorted(c for c in found if c)


def settings(root: Path) -> dict[str, Any]:
    data = load(root)
    schedule = data.get("schedule") or {}
    return {
        "schedule": {c: {"days": list((schedule.get(c) or {}).get("days", DEFAULT_DAYS)),
                         "time": str((schedule.get(c) or {}).get("time", DEFAULT_TIME)),
                         "enabled": bool((schedule.get(c) or {}).get("enabled", True))} for c in channels(root)},
        "lead_hours": float(data.get("lead_hours", 36)),
        "buffer": int(data.get("buffer", 2)),
        "morning_hour": int(data.get("morning_hour", 9)),
        "assigned": dict(data.get("assigned") or {}),
        "ideas": list(data.get("ideas") or []),
    }


def update(root: Path, body: dict[str, Any]) -> dict[str, Any]:
    """From the studio: {"channel", "days", "time", "enabled"} for a channel, and/or lead_hours, buffer,
    morning_hour; {"assign": slug, "date": "YYYY-MM-DD" or ""} pins (or unpins) a video to a day."""

    data = load(root)
    if body.get("channel"):
        channel = str(body["channel"])
        entry = dict((data.setdefault("schedule", {})).get(channel) or {})
        if "days" in body:
            entry["days"] = sorted({int(d) for d in body["days"] if 0 <= int(d) <= 6})
        if "time" in body:
            if not re.fullmatch(r"\d{1,2}:\d{2}", str(body["time"])):
                raise ValueError("Hora como 18:00")
            entry["time"] = str(body["time"])
        if "enabled" in body:
            entry["enabled"] = bool(body["enabled"])
        data["schedule"][channel] = entry
    for key, kind in (("lead_hours", float), ("buffer", int), ("morning_hour", int)):
        if key in body:
            data[key] = kind(body[key])
    if body.get("assign"):
        assigned = data.setdefault("assigned", {})
        if body.get("date"):
            date.fromisoformat(str(body["date"]))
            assigned[str(body["assign"])] = str(body["date"])
        else:
            assigned.pop(str(body["assign"]), None)
    save(root, data)
    return settings(root)


# --- videos and their state ----------------------------------------------------------------------------------------

def _published_day(info: dict[str, Any]) -> str | None:
    at = str(info.get("at") or "")
    return at[:10] if re.match(r"\d{4}-\d{2}-\d{2}", at) else None


def videos(root: Path) -> list[dict[str, Any]]:
    """Every video with its channel and where it is: subido / hecho / haciendo / en cola / error / en pausa /
    falta guion / falta voz."""

    from . import housekeeping
    from .context import VIDEO_FILES, video_folders
    from .web import _channel_of, _json, _json_yaml, running

    try:
        failed = _json(root / "out" / "_vigilar.json") or {}
    except Exception:
        failed = {}
    out = []
    for folder in video_folders(root):
        if any(p.startswith("_") for p in folder.relative_to(root / "materiales").parts):
            continue
        if not any((folder / n).is_file() for n in VIDEO_FILES):      # a channel's folder with only its config
            continue
        if (_json_yaml(folder / "config.yaml").get("dub") or {}).get("of"):   # a dubbed copy goes with its original
            continue
        slug = folder.name
        published = housekeeping.published(root, slug)
        final = root / "out" / slug / "video-final.mp4"
        if published:
            status = "subido"
        elif housekeeping.is_done(root, slug):
            status = "hecho"
        elif (folder / ".en-espera").is_file():
            status = "en pausa"
        elif running(_json(root / "work" / slug / "current.json")):
            status = "haciendo"
        elif not (folder / "guion.txt").is_file():
            status = "falta guion"
        elif not (folder / "voz.mp3").is_file():
            status = "falta voz"
        else:
            status = "error" if slug in failed else "en cola"
        title_file = folder / "titulo.txt"
        out.append({
            "slug": slug, "channel": _channel_of(root, folder), "status": status,
            "title": title_file.read_text("utf-8").strip() if title_file.is_file() else "",
            "published": _published_day(published) if published else None, "url": (published or {}).get("url") or "",
            "doneAt": final.stat().st_mtime if final.is_file() else None, "created": folder.stat().st_mtime,
        })
    return out


# --- the plan ----------------------------------------------------------------------------------------------------

def _at(day: date, clock: str) -> datetime:
    hour, minute = (int(x) for x in clock.split(":"))
    return datetime(day.year, day.month, day.day, hour, minute)


def plan(root: Path, start: date | None = None, days: int = 14, now: datetime | None = None,
         listed: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """The slots of every channel from `start` (today) for `days` days, each with its video (or None)."""

    now = now or datetime.now()
    start = start or now.date()
    cfg = settings(root)
    listed = listed if listed is not None else videos(root)
    lead = timedelta(hours=cfg["lead_hours"])
    by_channel: dict[str, list[dict[str, Any]]] = {}
    for video in listed:
        by_channel.setdefault(video["channel"], []).append(video)
    slots: list[dict[str, Any]] = []
    for channel, rule in cfg["schedule"].items():
        if not rule["enabled"]:
            continue
        mine = by_channel.get(channel, [])
        pinned = {v["slug"]: cfg["assigned"][v["slug"]] for v in mine if v["slug"] in cfg["assigned"]}
        days_here = [start + timedelta(days=n) for n in range(days)]
        wanted = [d for d in days_here if d.weekday() in rule["days"]]
        wanted += [date.fromisoformat(d) for d in pinned.values() if start <= date.fromisoformat(d) < start + timedelta(days=days)]
        wanted += [date.fromisoformat(v["published"]) for v in mine if v["published"]
                   and start <= date.fromisoformat(v["published"]) < start + timedelta(days=days)]
        mine_slots = [{"date": d.isoformat(), "time": rule["time"], "channel": channel, "video": None}
                      for d in sorted(set(wanted))]
        used: set[str] = set()
        for slot in mine_slots:                                       # what went out that day
            video = next((v for v in mine if v["published"] == slot["date"] and v["slug"] not in used), None)
            if video:
                slot["video"] = video
                used.add(video["slug"])
        for slot in mine_slots:                                       # what you pinned to that day
            if slot["video"] is None:
                video = next((v for v in mine if pinned.get(v["slug"]) == slot["date"] and v["slug"] not in used
                              and v["status"] != "subido"), None)
                if video:
                    slot["video"], slot["pinned"] = video, True
                    used.add(video["slug"])
        ready = sorted((v for v in mine if v["slug"] not in used and v["status"] in READINESS and v["slug"] not in pinned),
                       key=lambda v: (READINESS[v["status"]], v["doneAt"] or v["created"]))
        for slot in mine_slots:                                       # the next ones, readiest first
            if slot["video"] is None and _at(date.fromisoformat(slot["date"]), slot["time"]) >= now - timedelta(hours=12) and ready:
                slot["video"] = ready.pop(0)
        for slot in mine_slots:
            when = _at(date.fromisoformat(slot["date"]), slot["time"])
            video = slot["video"]
            slot["deadline"] = (when - lead).isoformat(timespec="minutes")
            slot["past"] = when < now
            slot["ok"] = bool(video and video["status"] in ("hecho", "subido"))
            needs_materials = video is None or video["status"] in ("falta guion", "falta voz")
            slot["gap"] = not slot["ok"] and not slot["past"] and (video is None or video["status"] not in ("haciendo", "en cola"))
            slot["late"] = not slot["ok"] and not slot["past"] and needs_materials and now > when - lead
        slots += mine_slots
    return sorted(slots, key=lambda s: (s["date"], s["time"], s["channel"]))


def priority(root: Path) -> dict[str, str]:
    """slug → the day it goes out, for the queue: the nearest slot first."""

    try:
        return {s["video"]["slug"]: f"{s['date']} {s['time']}" for s in plan(root, days=60) if s["video"]}
    except Exception:            # the calendar never stops the queue
        return {}


def reserve(root: Path, listed: list[dict[str, Any]] | None = None) -> dict[str, int]:
    """Finished videos not yet uploaded, per channel: the cushion."""

    listed = listed if listed is not None else videos(root)
    cfg = settings(root)
    return {c: sum(1 for v in listed if v["channel"] == c and v["status"] == "hecho")
            for c, rule in cfg["schedule"].items() if rule["enabled"]}


# --- texts for the bot ----------------------------------------------------------------------------------------

def _day(iso: str) -> str:
    d = date.fromisoformat(iso)
    today = date.today()
    if d == today:
        return "hoy"
    if d == today + timedelta(days=1):
        return "mañana"
    return f"{WEEKDAYS[d.weekday()]} {d.day}"


def _deadline(iso: str) -> str:
    when = datetime.fromisoformat(iso)
    return f"{_day(when.date().isoformat())} a las {when:%H:%M}"


def _name(video: dict[str, Any] | None) -> str:
    if not video:
        return "— sin vídeo —"
    return f"{video['title'] or video['slug']} ({video['status']})"


def today_text(root: Path) -> str:
    today = date.today().isoformat()
    slots = [s for s in plan(root, days=1) if s["date"] == today]
    if not slots:
        return "📅 Hoy no toca publicar en ningún canal."
    lines = ["📅 Hoy toca publicar:"]
    for s in slots:
        mark = "✅ subido" if s["video"] and s["video"]["status"] == "subido" else "🟢 listo" if s["ok"] else "🔴 no está listo"
        lines.append(f"• {s['channel']} a las {s['time']}: {_name(s['video'])} — {mark}")
    return "\n".join(lines)


def week_text(root: Path, days: int = 7) -> str:
    lines = ["🗓 Próximos 7 días:"]
    current = ""
    for s in plan(root, days=days):
        if s["date"] != current:
            current = s["date"]
            lines.append(f"\n{_day(current).capitalize()}:")
        icon = "✅" if s["ok"] else "⏳" if s["video"] and s["video"]["status"] in ("haciendo", "en cola") else "🔴"
        lines.append(f"  {icon} {s['channel']} {s['time']} · {_name(s['video'])}")
    return "\n".join(lines) if len(lines) > 1 else "🗓 No hay días de publicación en los próximos 7 días (Calendario en el estudio)."


def gaps_text(root: Path, days: int = 7) -> str:
    gaps = [s for s in plan(root, days=days) if s["gap"]]
    if not gaps:
        return "👍 Sin huecos en los próximos 7 días."
    lines = ["⚠️ Huecos en los próximos 7 días:"]
    for s in gaps:
        what = "no tiene vídeo" if not s["video"] else f"«{s['video']['slug']}» {s['video']['status']}"
        lines.append(f"• {s['channel']} · {_day(s['date'])} {s['time']}: {what}. "
                     + ("⏰ ¡ya vas tarde!" if s["late"] else f"Guion y voz antes del {_deadline(s['deadline'])}"))
    return "\n".join(lines)


def reserve_text(root: Path) -> str:
    cfg = settings(root)
    low = {c: n for c, n in reserve(root).items() if n < cfg["buffer"]}
    if not low:
        return ""
    return "📦 Pocos vídeos de reserva (listos sin subir): " + ", ".join(f"{c} {n}" for c, n in low.items()) + \
        f" (objetivo {cfg['buffer']})"


def morning_text(root: Path) -> str:
    parts = [today_text(root), gaps_text(root), reserve_text(root)]
    return "☀️ Buenos días\n\n" + "\n\n".join(p for p in parts if p)


def weekly_text(root: Path) -> str:
    """Sunday: what went out, what it cost per channel, what is coming and what is missing."""

    from .bot import cost_entries

    since = date.today() - timedelta(days=7)
    listed = videos(root)
    out = [v for v in listed if v["published"] and date.fromisoformat(v["published"]) > since]
    spent: dict[str, float] = {}
    channel_of = {v["slug"]: v["channel"] for v in listed}
    for entry in cost_entries(root):
        if str(entry.get("at", ""))[:10] > since.isoformat():
            channel = channel_of.get(str(entry.get("slug") or ""), "otros")
            spent[channel] = spent.get(channel, 0.0) + float(entry.get("usd") or 0)
    lines = ["📊 Resumen de la semana", "", f"Publicados: {len(out)}"]
    lines += [f"  • {v['channel']}: {v['title'] or v['slug']}" for v in out]
    if spent:
        lines += ["", "Gasto de API: " + ", ".join(f"{c} {usd:.2f} $" for c, usd in sorted(spent.items(), key=lambda kv: -kv[1]))
                  + f" · total {sum(spent.values()):.2f} $"]
    lines += ["", week_text(root), "", gaps_text(root)]
    return "\n".join(lines)


# --- views after publishing ---------------------------------------------------------------------------------

def _video_id(url: str) -> str | None:
    match = re.search(r"(?:v=|youtu\.be/|shorts/)([A-Za-z0-9_-]{11})", url or "")
    return match.group(1) if match else None


def tracking(root: Path, now: float | None = None) -> list[str]:
    """Views of each published video at 48 h and at 7 days, against the median of the channel's earlier ones at the
    same moment. Returns the messages to send (each one once). Needs the video's link (found on your channel or
    pasted with «Ya está subido») and YOUTUBE_API_KEYS."""

    from .context import RunContext
    from .ytapi import YouTubeAPI

    now = now or time.time()
    data = load(root)
    history = data.setdefault("views", {})
    due: list[tuple[dict[str, Any], str, str]] = []
    for video in videos(root):
        vid = _video_id(video["url"])
        if not vid or not video["published"]:
            continue
        info_at = datetime.fromisoformat(video["published"]).timestamp()
        for label, hours in (("48h", 48), ("7d", 168)):
            if now - info_at >= hours * 3600 and label not in history.get(video["slug"], {}):
                due.append((video, vid, label))
    if not due:
        return []
    try:
        api = YouTubeAPI(RunContext.create("_agenda", root=root))
        if not api.keys:
            return []
        stats = {v["id"]: v for v in api.videos(sorted({vid for _, vid, _ in due}))}
    except Exception as error:
        print(f"(Vistas no consultadas: {str(error)[:100]})")
        return []
    messages = []
    for video, vid, label in due:
        views = int((stats.get(vid) or {}).get("views") or (stats.get(vid) or {}).get("viewCount") or 0)
        earlier = [h[label] for slug, h in history.items() if label in h and h.get("channel") == video["channel"]]
        history.setdefault(video["slug"], {"channel": video["channel"]})[label] = views
        when = "48 h" if label == "48h" else "7 días"
        if len(earlier) >= 2:
            usual = statistics.median(earlier)
            ratio = views / usual if usual else 0
            verdict = ("🔥 el doble de lo normal" if ratio >= 2 else "📈 por encima de lo normal" if ratio >= 1.2
                       else "➖ en la media" if ratio >= 0.8 else "📉 por debajo de lo normal")
            messages.append(f"{verdict} · {video['channel']}: «{video['title'] or video['slug']}» lleva {views:,} vistas "
                            f"a las {when} (lo normal en el canal: {int(usual):,})".replace(",", "."))
        else:
            messages.append(f"👀 {video['channel']}: «{video['title'] or video['slug']}» lleva {views:,} vistas a las {when}"
                            .replace(",", ".") + " (aún pocos vídeos para comparar)")
    save(root, data)
    return messages


# --- the board ------------------------------------------------------------------------------------------------------

COLUMNS = ["idea", "falta voz", "en cola", "hecho", "subido"]


def board(root: Path) -> dict[str, list[dict[str, Any]]]:
    """Idea → falta voz (or script) → en cola (also making it, paused or failed) → hecho → subido."""

    from . import niche_ideas

    cfg = settings(root)
    columns: dict[str, list[dict[str, Any]]] = {c: [] for c in COLUMNS}
    days = {s["video"]["slug"]: s["date"] for s in plan(root, days=60) if s["video"]}
    for idea in [*cfg["ideas"], *niche_ideas.saved(root)]:
        columns["idea"].append({"kind": "idea", "id": idea.get("id"), "title": idea.get("title"),
                                "channel": idea.get("channel") or "", "note": idea.get("note") or idea.get("angle") or "",
                                "date": idea.get("date") or "", "idea": idea})
    for video in videos(root):
        column = ("subido" if video["status"] == "subido" else "hecho" if video["status"] == "hecho"
                  else "falta voz" if video["status"] in ("falta voz", "falta guion") else "en cola")
        columns[column].append({**video, "kind": "video", "date": days.get(video["slug"], "")})
    columns["subido"] = sorted(columns["subido"], key=lambda v: v.get("published") or "", reverse=True)[:12]
    return columns


def add_idea(root: Path, title: str, channel: str = "", note: str = "", day: str = "") -> dict[str, Any]:
    if not title.strip():
        raise ValueError("Pon un título a la idea")
    if day:
        date.fromisoformat(day)
    data = load(root)
    idea = {"id": f"tablero-{int(time.time() * 1000)}", "title": title.strip(), "channel": channel, "note": note.strip(),
            "date": day, "created": time.strftime("%Y-%m-%dT%H:%M:%S")}
    data.setdefault("ideas", []).insert(0, idea)
    save(root, data)
    return idea


def remove_idea(root: Path, idea_id: str) -> None:
    from . import niche_ideas

    data = load(root)
    data["ideas"] = [i for i in data.get("ideas") or [] if i.get("id") != idea_id]
    save(root, data)
    niche_ideas.unsave(root, idea_id)
