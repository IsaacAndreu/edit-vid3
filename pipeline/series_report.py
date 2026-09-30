"""Which series of a channel works best: `python main.py --series negocios`.

Each video in materiales/ with `canal: <canal>` and `serie: <serie>` is matched with its upload on
your channel (`ideas.my_channel`) by `youtube:` in its config.yaml (id or URL), else by title
(titulo.txt and the options in out/<slug>/youtube.txt). Views come from the YouTube Data API when
keys are set (with views per day, fair between old and new videos), else from yt-dlp. CTR and
retention are not public: copy them from YouTube Studio into the video's config.yaml
(`estadisticas: {ctr: 5.4, retencion: 41}`) and they are averaged too.
Result: out/_series/<canal>-<fecha>.md.
"""

from __future__ import annotations

import re
import statistics
import unicodedata
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from .context import RunContext, load_config

MIN_MATCH = 0.72


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.casefold())
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", "".join(c for c in text if not unicodedata.combining(c))).split())


def _youtube_id(value: str) -> str:
    found = re.search(r"(?:v=|youtu\.be/|shorts/)([\w-]{11})", value)
    return found.group(1) if found else value.strip()


def videos_of(root: Path, channel: str) -> list[dict[str, Any]]:
    """The channel's videos in materiales/ that belong to a series."""

    out = []
    for folder in sorted((root / "materiales").iterdir()) if (root / "materiales").is_dir() else []:
        path = folder / "config.yaml"
        cfg = load_config(path) if path.is_file() else {}
        if cfg.get("canal") != channel or not cfg.get("serie"):
            continue
        titles = []
        if (folder / "titulo.txt").is_file():
            titles.append((folder / "titulo.txt").read_text("utf-8").strip())
        published = root / "out" / folder.name / "youtube.txt"
        if published.is_file():
            titles += [re.sub(r"^\d+\.\s*", "", line).strip() for line in published.read_text("utf-8").splitlines()
                       if re.match(r"^\d+\.\s", line)]
        stats = cfg.get("estadisticas") or {}
        out.append({"slug": folder.name, "serie": str(cfg["serie"]), "titles": [t for t in titles if t],
                    "youtube": _youtube_id(str(cfg["youtube"])) if cfg.get("youtube") else "",
                    "ctr": stats.get("ctr"), "retention": stats.get("retencion")})
    return out


def channel_uploads(ctx: RunContext, handle: str, count: int = 80) -> list[dict[str, Any]]:
    from .ideas import _api, channel_videos, score

    api = _api(ctx)
    if api:
        from . import lab

        return lab.channel_report(ctx, handle, count=count, api=api)["videos"]
    return score(channel_videos(ctx, handle, count))


def match(video: dict[str, Any], uploads: list[dict[str, Any]]) -> dict[str, Any] | None:
    if video["youtube"]:
        return next((u for u in uploads if u["id"] == video["youtube"]), None)
    best, best_score = None, 0.0
    for upload in uploads:
        for title in video["titles"]:
            value = SequenceMatcher(None, _norm(title), _norm(upload["title"])).ratio()
            if value > best_score:
                best, best_score = upload, value
    return best if best_score >= MIN_MATCH else None


def _median(values: list[Any]) -> float | None:
    values = [float(v) for v in values if v is not None]
    return statistics.median(values) if values else None


def _fmt(value: float | None, suffix: str = "", digits: int = 0) -> str:
    return "—" if value is None else f"{value:,.{digits}f}".replace(",", ".") + suffix


def report(channel: str, root: Path | None = None) -> Path:
    from .context import PROJECT_ROOT
    from .ideas import series_of

    ctx = RunContext.create("_series", root=root or PROJECT_ROOT, channel=channel)
    handle = str(ctx.section("ideas").get("my_channel") or "").strip()
    if not handle:
        raise ValueError(f"Pon tu canal en canales/{channel}.yaml → ideas.my_channel (p. ej. \"@tucanal\")")
    videos = videos_of(ctx.root, channel)
    if not videos:
        raise ValueError(f"Ningún vídeo de materiales/ tiene `canal: {channel}` y `serie:` en su config.yaml")
    uploads = channel_uploads(ctx, handle)
    rows: dict[str, list[dict[str, Any]]] = {name: [] for name in series_of(ctx)}
    missing = []
    for video in videos:
        found = match(video, uploads)
        if found is None:
            missing.append(video["slug"])
            continue
        rows.setdefault(video["serie"], []).append({**video, **found})
    table = []
    for name, items in rows.items():
        table.append({"serie": name, "n": len(items),
                      "views": _median([i.get("views") for i in items]),
                      "perDay": _median([i.get("viewsPerDay") for i in items]),
                      "ratio": _median([i.get("ratio") for i in items]),
                      "ctr": _median([i.get("ctr") for i in items]),
                      "retention": _median([i.get("retention") for i in items]),
                      "best": max(items, key=lambda i: i.get("views") or 0) if items else None})
    key = "perDay" if any(r["perDay"] is not None for r in table) else "views"
    table.sort(key=lambda r: -(r[key] or -1))
    today = date.today().isoformat()
    lines = [f"# Series de {channel} · {today}", "",
             f"Canal: {handle} · {sum(r['n'] for r in table)} vídeos emparejados · orden: "
             + ("visitas por día (mediana)" if key == "perDay" else "visitas (mediana)"), "",
             "| Serie | Vídeos | Visitas (mediana) | Visitas/día | x mediana del canal | CTR | Retención | Mejor vídeo |",
             "|---|---|---|---|---|---|---|---|"]
    for r in table:
        best = r["best"]
        lines.append(f"| {r['serie']} | {r['n']} | {_fmt(r['views'])} | {_fmt(r['perDay'])} | {_fmt(r['ratio'], '', 1)} "
                     f"| {_fmt(r['ctr'], ' %', 1)} | {_fmt(r['retention'], ' %', 0)} "
                     f"| {best['title'] + ' (' + _fmt(best.get('views')) + ')' if best else '—'} |")
    lines += ["", "## Cómo leerlo", "",
              "- Con 1 vídeo por serie es una pista, no una conclusión: espera a 3 por serie antes de abandonar ninguna.",
              "- Compara vídeos de edad parecida (visitas/día corrige una parte, no todo: los primeros días pesan más).",
              "- CTR bajo → el problema es el título/miniatura; retención baja → el guion o el ritmo; los dos bien y pocas "
              "visitas → el tema no interesa."]
    empty = [r["serie"] for r in table if not r["n"]]
    if empty:
        lines += ["", f"Series sin vídeos publicados todavía: {', '.join(empty)}."]
    if missing:
        lines += ["", "## Sin emparejar", "",
                  "No encontré estos vídeos en el canal por el título; pon `youtube: <URL>` en su config.yaml:", ""]
        lines += [f"- {slug}" for slug in missing]
    out = ctx.root / "out" / "_series" / f"{channel}-{today}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out
