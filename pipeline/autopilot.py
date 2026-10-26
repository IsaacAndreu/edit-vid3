"""Channel autopilot («Piloto automático», in the studio under Crecer): from the niche's outliers to a finished video.

Every day the radar finds the competition's outliers for each channel (pipeline/radar.py). Here each one becomes a
candidate with its evidence (how much it beat its own channel, views per hour, which title patterns do better in
the niche). «Hacer este vídeo» — or the autopilot on its own, `per_day` a day for a channel switched on — turns it
into the channel's OWN video on the subject (never a copy): an idea with its angle and hook, a full script in the
channel's format (organizar.draft_script), a new video in materiales/ with that script; the channel's GenAIPro voice
reads it (tts.prepare_all) and the queue makes it. It never uploads: the video waits in «Para subir».

State: out/_piloto/estado.json — {channel: {on, perDay, made: [{date, slug, title, from}], skipped: [ids], error}}.
"""

from __future__ import annotations

import json
import re
import statistics
from datetime import datetime
from pathlib import Path
from typing import Any

STATE = Path("out") / "_piloto" / "estado.json"

IDEA_SYSTEM = """
Eres el estratega de un canal documental de YouTube sin cara ({about}). Te paso un vídeo de la competencia que está
funcionando mucho mejor que lo normal en su canal. Propón UNA idea para un vídeo PROPIO del canal sobre ese tema o
uno muy cercano: otro ángulo, otra estructura y otro título — nunca una copia de ese vídeo. Devuelve SOLO JSON:
{"title": "título de trabajo con gancho, máx. 70 caracteres", "angle": "el enfoque en 1-2 frases",
 "hook": "las 2-3 primeras frases del vídeo", "outline": ["4-7 bloques del vídeo"],
 "research": "qué datos hay que comprobar al escribir", "angleTag": "el ángulo en 2-4 palabras (p. ej. 'el recurso oculto')"}
No afirmes cifras, fechas ni declaraciones que no puedas sostener: lo que haya que comprobar va en "research".
""".strip()


def _read(root: Path) -> dict[str, Any]:
    try:
        return json.loads((root / STATE).read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def _write(root: Path, state: dict[str, Any]) -> None:
    path = root / STATE
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def channel_state(root: Path, channel: str) -> dict[str, Any]:
    return {"on": False, "perDay": 1, "made": [], "skipped": [], **_read(root).get(channel, {})}


def configure(root: Path, channel: str, on: bool | None = None, per_day: int | None = None) -> dict[str, Any]:
    state = _read(root)
    entry = {**channel_state(root, channel)}
    if on is not None:
        entry["on"] = bool(on)
    if per_day is not None:
        entry["perDay"] = max(1, min(3, int(per_day)))
    state[channel] = entry
    _write(root, state)
    return entry


def skip(root: Path, channel: str, video_id: str) -> dict[str, Any]:
    state = _read(root)
    entry = {**channel_state(root, channel)}
    entry["skipped"] = list(dict.fromkeys([*entry["skipped"], video_id]))[-200:]
    state[channel] = entry
    _write(root, state)
    return entry


# --- candidates -------------------------------------------------------------------------------------------------

def _first_word(title: str) -> str:
    words = re.findall(r"[^\W\d_]+", title.lower())
    return words[0] if words else ""


def patterns(top: list[dict[str, Any]], min_group: int = 2) -> dict[str, float]:
    """First word of the title → how much better its videos do than the niche's median (only the clear ones)."""

    ratios = [float(v.get("ratio") or 0) for v in top if v.get("ratio")]
    if len(ratios) < 4:
        return {}
    median = statistics.median(ratios)
    groups: dict[str, list[float]] = {}
    for v in top:
        if v.get("ratio"):
            groups.setdefault(_first_word(str(v.get("title") or "")), []).append(float(v["ratio"]))
    return {w: round(statistics.median(r) / median, 1) for w, r in groups.items()
            if w and len(r) >= min_group and median and statistics.median(r) / median >= 1.3}


def evidence(video: dict[str, Any], found: dict[str, float]) -> list[str]:
    lines = []
    if video.get("ratio"):
        lines.append(f"x{float(video['ratio']):.1f} lo normal de su canal")
    if video.get("viewsPerDay"):
        lines.append(f"{round(float(video['viewsPerDay']) / 24):,} visitas/hora ({video.get('channel') or '—'})".replace(",", "."))
    word = _first_word(str(video.get("title") or ""))
    if word in found:
        lines.append(f"los títulos «{word.capitalize()}…» hacen x{found[word]} en el nicho")
    if video.get("new"):
        lines.append("nuevo hoy")
    return lines


def candidates(root: Path, channel: str, limit: int = 8) -> list[dict[str, Any]]:
    from . import radar

    report = radar.latest(root) or {}
    top = list(((report.get("channels") or {}).get(channel) or {}).get("top") or [])
    entry = channel_state(root, channel)
    used = {m.get("from") for m in entry["made"]} | set(entry["skipped"])
    found = patterns(top)
    out = []
    for video in top:
        if video.get("id") in used:
            continue
        out.append({**{k: video.get(k) for k in ("id", "title", "channel", "views", "ratio", "thumbnail", "url", "viewsPerDay")},
                    "evidence": evidence(video, found)})
    return out[:limit]


# --- making a video ---------------------------------------------------------------------------------------------

def idea_from(root: Path, channel: str, video: dict[str, Any]) -> dict[str, Any]:
    from .context import RunContext
    from .llm import complete_json
    from .porque import lessons

    from .repeticion import recent_titles

    ctx = RunContext.create("_piloto", root=root, channel=channel)
    recent = recent_titles(root, channel)
    about = str(ctx.section("ideas").get("about") or channel)
    result = complete_json(ctx, stage="piloto", section="planner", system=IDEA_SYSTEM.replace("{about}", about),
                           max_tokens=1500, use_cache=False,
                           user=(f"VÍDEO QUE FUNCIONA: «{video.get('title')}» ({video.get('channel')}), "
                                 f"{video.get('views')} visitas, x{video.get('ratio')} lo normal de su canal.\n"
                                 f"POR QUÉ: {'; '.join(evidence(video, {}))}"
                                 + "".join(f"\nLECCIÓN DEL CANAL: {x}" for x in lessons(root, channel))
                                 + ("\nÚLTIMOS TÍTULOS DEL CANAL (no repitas su estructura, solo cambiando los nombres: YouTube "
                                    "castiga el contenido repetitivo):\n" + "\n".join(f"- {t}" for t in recent) if recent else "")))
    if not str(result.get("title") or "").strip():
        raise RuntimeError("La idea ha salido vacía")
    return {**result, "note": f"Inspirado en «{video.get('title')}» ({video.get('channel')}): vídeo propio, no una copia"}


def _name(root: Path, channel: str) -> str:
    from .web import video_folders

    taken = {f.name for f in video_folders(root)}
    base = re.sub(r"[^A-Za-z0-9]+", "", channel)[:20] or "video"
    day = datetime.now().strftime("%m%d")
    n = 1
    while f"{base}-auto{day}-{n}" in taken:
        n += 1
    return f"{base}-auto{day}-{n}"


def make(root: Path, channel: str, video_id: str | None = None) -> dict[str, Any]:
    """The candidate `video_id` (or the best one) → its idea → its script → a new video waiting for its voice."""

    from .organizar import draft_script
    from .web import create_video

    pool = candidates(root, channel, limit=50)
    pick = next((c for c in pool if c["id"] == video_id), None) if video_id else (pool[0] if pool else None)
    if pick is None:
        raise ValueError("No hay ninguna idea para este canal todavía (el radar las trae cada día)")
    idea = idea_from(root, channel, pick)
    draft = draft_script(root, channel, idea)
    name = _name(root, channel)
    create_video(root, {"name": name, "channel": channel, "script": draft["script"], "title": draft["title"],
                        "idea": {**idea, "title": draft["title"]}, **({"format": draft["format"]} if draft.get("format") else {})})
    state = _read(root)
    entry = {**channel_state(root, channel)}
    entry["made"] = [*entry["made"], {"date": datetime.now().date().isoformat(), "slug": name, "title": draft["title"],
                                      "from": pick["id"], "fromTitle": pick["title"], "angle": idea.get("angleTag")}][-100:]
    entry.pop("error", None)
    state[channel] = entry
    _write(root, state)
    print(f"Piloto automático · {channel}: {name} «{draft['title']}» ({draft['words']} palabras), de «{pick['title']}»")
    return {"slug": name, "title": draft["title"], "words": draft["words"]}


def due_channels(root: Path, today: str | None = None) -> list[str]:
    today = today or datetime.now().date().isoformat()
    state = _read(root)
    return [c for c, entry in state.items() if isinstance(entry, dict) and entry.get("on")
            and sum(1 for m in entry.get("made", []) if m.get("date") == today) < int(entry.get("perDay", 1))
            and entry.get("errorDate") != today]


def run_if_due(root: Path) -> None:
    """From the watcher, every few minutes: one video for each channel switched on that has not had today's."""

    for channel in due_channels(root):
        try:
            make(root, channel)
        except Exception as error:      # tried again tomorrow; the studio shows why
            state = _read(root)
            entry = {**channel_state(root, channel), "error": str(error)[:300],
                     "errorDate": datetime.now().date().isoformat()}
            state[channel] = entry
            _write(root, state)
            print(f"Piloto automático · {channel}: {str(error)[:200]}")


def overview(root: Path) -> dict[str, Any]:
    """For the studio: every channel, its switch, today's candidates and what the autopilot made."""

    from . import radar
    from .tts import voice_for

    out = []
    for channel in radar.channels(root):
        entry = channel_state(root, channel)
        try:
            voice = voice_for(root, channel) is not None
        except Exception:
            voice = False
        out.append({"channel": channel, **entry, "voice": voice, "candidates": candidates(root, channel),
                    "made": list(reversed(entry["made"]))[:12]})
    return {"channels": out, "radarDate": (radar.latest(root) or {}).get("date")}
