"""Copyright-claim risk before uploading: out/<slug>/derechos.md.

Every third-party clip is short (≤ 5 s) and credited, but Content ID looks at how much of ONE owner's
footage a video uses and whether it runs back to back. This groups the video's footage by source
channel — total seconds, longest stretch in a row, shots — and flags the owners that claim often
(broadcasters, leagues, federations, news agencies: `rights.strict_channels`, extendable). The list of
their shots, with times, is what to swap in the editor if you want to lower the risk.
Nothing is blocked: it is information to decide before publishing.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .context import RunContext

STRICT = [
    "Olympics", "Olympic Channel", "NBC", "NBC Sports", "NBC Olympics", "Peacock", "CBC", "BBC", "BBC Sport",
    "Eurosport", "Discovery", "RTVE", "Teledeporte", "beIN", "DAZN", "ESPN", "FOX", "CBS", "Sky Sports", "TNT Sports",
    "UEFA", "FIFA", "LaLiga", "NBA", "NFL", "MLB", "NHL", "Premier League", "FIG", "Gymnastics Channel",
    "USA Gymnastics", "Movistar", "Antena 3", "Telecinco", "laSexta", "Cuatro", "Mediaset", "Atresmedia", "Televisa",
    "TV Azteca", "CNN", "Bloomberg", "CNBC", "Reuters", "AP", "Associated Press", "AFP", "Getty", "Warner", "Sony",
    "Universal", "Disney", "Paramount", "HBO", "Netflix", "Vevo",
]


def _tokens(text: str) -> set[str]:
    import re

    return set(re.findall(r"[a-z0-9]+", text.lower()))


# Channels of one owner count together (Content ID works per owner, not per channel).
FAMILIES = {
    "Olympics (COI)": {"olympic", "olympics", "olympians", "paralympic", "paralympics", "ioc"},
    "NBC / Peacock": {"nbc", "peacock"},
    "BBC": {"bbc"},
    "RTVE": {"rtve", "teledeporte"},
    "Atresmedia": {"atresmedia", "antena", "lasexta"},
    "Mediaset": {"mediaset", "telecinco", "cuatro"},
    "FIG (gimnasia)": {"fig"},
}


def family(channel: str) -> str:
    have = _tokens(channel)
    return next((name for name, words in FAMILIES.items() if have & words), channel)


def is_strict(channel: str, strict: list[str]) -> bool:
    """A listed owner in the channel name: every word of it ('NBC Sports'), and a one-word name only at the
    start ('Universal Pictures' yes, 'El Universal Deportes' no)."""

    if family(channel) != channel:
        return True
    words = [w for w in __import__("re").findall(r"[a-z0-9]+", channel.lower())]
    for name in strict:
        wanted = _tokens(name)
        if not wanted or not wanted <= set(words):
            continue
        if len(wanted) > 1 or (words and words[0] in wanted):
            return True
    return False


def owners(rows: list[dict[str, Any]], strict: list[str], gap: float = 0.5) -> list[dict[str, Any]]:
    """Per source channel: seconds, shots, longest back-to-back stretch, strict owner or not."""

    by: dict[str, dict[str, Any]] = defaultdict(lambda: {"seconds": 0.0, "shots": [], "run": 0.0})
    third = [r for r in rows if r.get("category", "").startswith("terceros") and r.get("channel")]
    third.sort(key=lambda r: r["start"])
    current: tuple[str, float, float] | None = None       # channel, run start, run end
    for row in third:
        channel, seconds = family(str(row["channel"])), float(row["end"]) - float(row["start"])
        entry = by[channel]
        entry["seconds"] += seconds
        entry["shots"].append(row)
        if current and current[0] == channel and row["start"] - current[2] <= gap:
            current = (channel, current[1], row["end"])
        else:
            current = (channel, row["start"], row["end"])
        entry["run"] = max(entry["run"], current[2] - current[1])
    out = [{"channel": c, "seconds": round(e["seconds"], 1), "shots": e["shots"], "run": round(e["run"], 1),
            "strict": c in FAMILIES or is_strict(c, strict),
            "channels": sorted({str(r["channel"]) for r in e["shots"]})} for c, e in by.items()]
    return sorted(out, key=lambda o: (-o["strict"], -o["seconds"]))


def level(owner: dict[str, Any], cfg: dict[str, Any]) -> str:
    if not owner["strict"]:
        return "bajo"
    if owner["seconds"] >= float(cfg.get("high_seconds", 45)) or owner["run"] >= float(cfg.get("high_run", 10)):
        return "alto"
    return "medio"


def _clock(seconds: float) -> str:
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}"


def write(ctx: RunContext, rows: list[dict[str, Any]], duration: float) -> list[str]:
    """out/<slug>/derechos.md; returns the QA warnings (owners with high risk)."""

    cfg = ctx.section("rights")
    strict = [*STRICT, *[str(c) for c in cfg.get("strict_channels", [])]]
    found = owners(rows, strict)
    third = sum(o["seconds"] for o in found)
    lines = [f"# Riesgo de reclamaciones · {ctx.slug}", "",
             f"Metraje de terceros: {third:.0f} s de {duration:.0f} s ({100 * third / max(duration, 1):.0f} %) · "
             f"{len(found)} canales de origen.", "",
             "| Riesgo | Canal | Segundos | % del vídeo | Tramo seguido más largo | Planos |", "|---|---|---|---|---|---|"]
    for o in found:
        lines.append(f"| {level(o, cfg)} | {o['channel']} | {o['seconds']:.0f} | {100 * o['seconds'] / max(duration, 1):.1f} % "
                     f"| {o['run']:.1f} s | {len(o['shots'])} |")
    risky = [o for o in found if level(o, cfg) == "alto"]
    lines += ["", "## Qué significa", "",
              "- **alto**: canal que suele reclamar (cadenas, ligas, federaciones, agencias) con mucho metraje o tramos "
              "seguidos largos. Si el vídeo va monetizado, cambia en el editor los planos de abajo por otras fuentes.",
              "- **medio**: canal que suele reclamar pero con poco metraje y cortado: el riesgo es bajo.",
              "- **bajo**: canales que rara vez reclaman.",
              "- Reclamar no es un strike: normalmente solo reparte o quita los ingresos de ese vídeo."]
    for o in risky:
        lines += ["", f"## {o['channel']}: planos para cambiar", ""]
        if len(o["channels"]) > 1:
            lines += [f"Canales: {', '.join(o['channels'])}", ""]
        lines += [f"- {_clock(r['start'])} · {r['shotId']} · {float(r['end']) - float(r['start']):.1f} s · {r.get('title', '')[:70]}"
                  for r in o["shots"]]
    (ctx.out_dir / "derechos.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return [f"Riesgo alto de reclamación: {o['channel']} ({o['seconds']:.0f} s, tramo de {o['run']:.0f} s seguidos) → "
            "derechos.md" for o in risky]
