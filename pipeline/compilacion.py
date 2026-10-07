"""Long compilations: 8-12 finished videos of a channel joined into one 2-3 hour video («3 HORAS de…», to fall asleep
to, marathons) — lots of watch time from work already done. No search, judge or download: the final videos are cut
before their end screen, each part gets a 3-second card («PARTE 3 · title» over a blurred frame of it, with a swoosh),
the whole starts with a title card, and youtube.txt carries the chapters (one per part), title options and the
description.

    python main.py --compilar negocios           (or the studio: Para subir → «Crear compilación»)

The parts: the channel's videos whose final file is still on disk and that no earlier compilation used, best first
(views on YouTube when known — «doblar lo que gana» —, else the newest), up to `compilations.max_minutes` (180) and
`compilations.max_videos` (12). The result is a video like any other: materiales/<canal>/<slug>/ + out/<slug>/, so it
shows in Inicio, «Para subir» and the calendar. Uploaded videos keep their final file while `compilations.keep_finals`
(true) so they can go into one (the disk cleanup still frees them when space runs low).
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from .context import RunContext

USED = "out/_compilaciones.json"
W, H, FPS = 1920, 1080, 30
CARD_SECONDS = 3.0
TITLE_SECONDS = 4.0

TITLE_SYSTEM = """
Eres el responsable de títulos de un canal documental de YouTube. Te paso los títulos de los vídeos que forman una
COMPILACIÓN larga de {minutes} minutos. Devuelve SOLO JSON: {"titles": ["3 títulos distintos en el idioma de los
vídeos, con la duración en grande y el gancho común, p. ej. '3 HORAS de las CAÍDAS más brutales de empresas'"],
"description": "2-3 frases que enganchen, sin emojis ni hashtags", "card": "texto corto en MAYÚSCULAS para la portada
(máx. 6 palabras)"}.
""".strip()


def _run(cmd: list[str], timeout: float = 3600) -> None:
    done = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if done.returncode != 0:
        raise RuntimeError(f"{cmd[0]}: {done.stderr[-400:]}")


def _duration(path: Path) -> float:
    done = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                          capture_output=True, text=True, timeout=60)
    try:
        return float(done.stdout.strip())
    except ValueError:
        return 0.0


def _used(root: Path) -> dict[str, Any]:
    try:
        return json.loads((root / USED).read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def candidates(root: Path, channel: str) -> list[dict[str, Any]]:
    """The channel's finished videos with their final file on disk, not in an earlier compilation, best first."""

    from . import agenda

    used = {s for c in _used(root).values() for s in c.get("videos", [])}
    try:
        from .estadisticas import report

        views = {v["slug"]: (v.get("youtube") or {}).get("views") or 0 for v in report(root)["videos"]}
    except Exception:
        views = {}
    out = []
    for video in agenda.videos(root):
        final = root / "out" / video["slug"] / "video-final.mp4"
        if (video["channel"] != channel or video["status"] not in ("hecho", "subido") or not final.is_file()
                or video["slug"] in used):
            continue
        cfg = _video_config(root, video["slug"])
        if (cfg.get("dub") or {}).get("of") or cfg.get("compilation"):
            continue
        out.append({**video, "views": views.get(video["slug"], 0), "final": final})
    return sorted(out, key=lambda v: (-v["views"], -(v["doneAt"] or 0)))


def _video_config(root: Path, slug: str) -> dict[str, Any]:
    from .context import find_video
    from .web import _json_yaml

    try:
        return _json_yaml(find_video(root, slug) / "config.yaml")
    except Exception:
        return {}


def _end_screen(root: Path, slug: str) -> float:
    try:
        t = json.loads((root / "work" / slug / "timeline.json").read_text("utf-8"))
        return float(t.get("endscreenFrames") or 0) / float(t.get("fps") or FPS)
    except (OSError, ValueError):
        return 0.0


def _font(root: Path) -> str | None:
    for path in [*(root / "cache" / "fonts").glob("*.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")]:
        if path.is_file():
            return str(path)
    return None


def card(root: Path, background: Path | None, big: str, small: str, target: Path) -> Path:
    """A 1920x1080 still: blurred, darkened frame (or black) with a small line and a big title."""

    from PIL import Image, ImageDraw, ImageFilter, ImageFont

    if background is not None and background.is_file():
        image = Image.open(background).convert("RGB").resize((W, H)).filter(ImageFilter.GaussianBlur(18))
        image = Image.blend(image, Image.new("RGB", (W, H), (0, 0, 0)), 0.55)
    else:
        image = Image.new("RGB", (W, H), (10, 10, 12))
    draw = ImageDraw.Draw(image)
    font_path = _font(root)

    def font(size: int):
        return ImageFont.truetype(font_path, size) if font_path else ImageFont.load_default()

    lines, size = _wrap(draw, big.upper(), font, 110, W - 240)
    y = H // 2 - (len(lines) * size * 1.1) // 2 + (40 if small else 0)
    if small:
        f = font(54)
        width = draw.textlength(small.upper(), font=f)
        draw.text(((W - width) / 2, y - 100), small.upper(), font=f, fill=(255, 212, 0))
    for line in lines:
        f = font(size)
        width = draw.textlength(line, font=f)
        draw.text(((W - width) / 2, y), line, font=f, fill=(255, 255, 255))
        y += size * 1.1
    image.save(target, quality=92)
    return target


def _wrap(draw: Any, text: str, font: Any, size: int, width: int) -> tuple[list[str], int]:
    while size > 40:
        lines, line = [], ""
        for word in text.split():
            trial = f"{line} {word}".strip()
            if draw.textlength(trial, font=font(size)) <= width:
                line = trial
            else:
                lines.append(line)
                line = word
        lines.append(line)
        lines = [l for l in lines if l]
        if len(lines) <= 3:
            return lines, size
        size -= 10
    return lines, size


def _encode_card(still: Path, seconds: float, swoosh: Path | None, target: Path) -> None:
    audio = (["-i", str(swoosh), "-filter_complex", f"[1:a]apad,atrim=0:{seconds},aresample=48000,volume=0.5[a]", "-map", "0:v", "-map", "[a]"]
             if swoosh and swoosh.is_file()
             else ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-map", "0:v", "-map", "1:a"])
    _run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-loop", "1", "-t", f"{seconds}", "-i", str(still), *audio,
          "-t", f"{seconds}", "-r", str(FPS), "-vf", f"scale={W}:{H},format=yuv420p,fade=in:0:8",
          "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
          str(target)])


def _encode_part(final: Path, seconds: float, target: Path) -> None:
    _run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(final), "-t", f"{seconds:.3f}",
          "-vf", f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,fps={FPS},format=yuv420p",
          "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
          str(target)], timeout=4 * 3600)


def _frame(video: Path, at: float, target: Path) -> Path | None:
    done = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", f"{at:.2f}", "-i", str(video),
                           "-frames:v", "1", "-q:v", "3", str(target)], capture_output=True, timeout=60)
    return target if done.returncode == 0 and target.is_file() else None


def mmss(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def build(root: Path, channel: str, slugs: list[str] | None = None, log: Any = print) -> str:
    """Make the compilation; returns its slug (materiales/<canal>/<slug>/, out/<slug>/video-final.mp4)."""

    from .context import find_video
    from .llm import complete_json

    base = RunContext.create("_compilacion", root=root, channel=channel)
    cfg = base.section("compilations")
    pool = candidates(root, channel)
    if slugs:
        by = {v["slug"]: v for v in pool}
        pool = [by[s] for s in slugs if s in by]
    chosen, total = [], 0.0
    for video in pool:
        length = max(0.0, _duration(video["final"]) - _end_screen(root, video["slug"]))
        if length < 60:
            continue
        if chosen and (total + length > 60 * float(cfg.get("max_minutes", 180)) or len(chosen) >= int(cfg.get("max_videos", 12))):
            break
        chosen.append({**video, "length": length})
        total += length
    if len(chosen) < int(cfg.get("min_videos", 3)):
        raise RuntimeError(f"Hacen falta al menos {cfg.get('min_videos', 3)} vídeos terminados de {channel} con su vídeo final "
                           f"en disco y sin usar en otra compilación (hay {len(chosen)}).")
    minutes = round(total / 60)
    titles = [v["title"] or v["slug"] for v in chosen]
    try:
        meta = complete_json(base, stage="compilacion", section="planner", max_tokens=700,
                             system=TITLE_SYSTEM.replace("{minutes}", str(minutes)),
                             user="\n".join(f"- {t}" for t in titles))
    except Exception:
        meta = {}
    hours = f"{total / 3600:.1f}".replace(".0", "").replace(".", ",")
    head = str(meta.get("card") or f"{hours} HORAS DE HISTORIAS")
    slug = f"compilacion-{channel}-{time.strftime('%Y%m%d-%H%M')}"
    channel_folder = find_video(root, chosen[0]["slug"]).parent
    folder = channel_folder / slug
    out = root / "out" / slug
    folder.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    swoosh = next(iter(sorted((root / "assets" / "sfx").glob("whoosh*.mp3"))), None)
    with tempfile.TemporaryDirectory(dir=out) as tmp_name:
        tmp = Path(tmp_name)
        pieces: list[Path] = []
        first_frame = _frame(chosen[0]["final"], 20, tmp / "f0.jpg")
        _encode_card(card(root, first_frame, head, f"{len(chosen)} historias", tmp / "title.jpg"), TITLE_SECONDS, swoosh,
                     tmp / "000-title.mp4")
        pieces.append(tmp / "000-title.mp4")
        chapters, at = [("0:00", "Intro")], TITLE_SECONDS
        for n, video in enumerate(chosen, start=1):
            log(f"   Parte {n}/{len(chosen)}: {video['slug']} ({video['length'] / 60:.0f} min)")
            frame = _frame(video["final"], min(30.0, video["length"] / 3), tmp / f"f{n}.jpg")
            card_file = tmp / f"{n:03d}-card.mp4"
            _encode_card(card(root, frame, video["title"] or video["slug"], f"Parte {n}", tmp / f"c{n}.jpg"), CARD_SECONDS,
                         swoosh, card_file)
            part = tmp / f"{n:03d}-part.mp4"
            _encode_part(video["final"], video["length"], part)
            chapters.append((mmss(at), f"{n}. {video['title'] or video['slug']}"))
            at += CARD_SECONDS + video["length"]
            pieces += [card_file, part]
        listing = tmp / "list.txt"
        listing.write_text("".join(f"file '{p.resolve()}'\n" for p in pieces), encoding="utf-8")
        _run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy",
              "-movflags", "+faststart", str(out / "video-final.mp4")], timeout=3600)
        if first_frame:
            stills = out / "fotogramas"
            stills.mkdir(exist_ok=True)
            for n in range(min(8, len(chosen))):
                f = tmp / f"f{n + 1}.jpg"
                if f.is_file():
                    f.replace(stills / f"fotograma-{n + 1}.jpg")
    title_options = [str(t).strip() for t in meta.get("titles", []) if str(t).strip()][:3] or [f"{hours} HORAS de {channel}"]
    description = str(meta.get("description") or "").strip()
    (folder / "titulo.txt").write_text(title_options[0] + "\n", encoding="utf-8")
    (folder / "guion.txt").write_text("Compilación:\n" + "\n".join(f"- {t}" for t in titles) + "\n", encoding="utf-8")
    (folder / "config.yaml").write_text(f"compilation:\n  videos: [{', '.join(v['slug'] for v in chosen)}]\n", encoding="utf-8")
    (out / "youtube.txt").write_text(
        "TÍTULO (elige uno)\n" + "\n".join(f"{n}. {t}" for n, t in enumerate(title_options, 1)) + "\n\n"
        + "DESCRIPCIÓN\n" + (description + "\n\n" if description else "") + "\n".join(f"{t} {c}" for t, c in chapters) + "\n\n"
        + "ETIQUETAS\n" + ", ".join(dict.fromkeys(["compilación", "documental", channel, *[t.split(":")[0] for t in titles[:6]]])) + "\n",
        encoding="utf-8")
    used = _used(root)
    used[slug] = {"channel": channel, "videos": [v["slug"] for v in chosen], "minutes": minutes,
                  "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    (root / USED).parent.mkdir(parents=True, exist_ok=True)
    (root / USED).write_text(json.dumps(used, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"Compilación {slug}: {len(chosen)} vídeos, {minutes} min → out/{slug}/video-final.mp4")
    return slug


def status(root: Path) -> list[dict[str, Any]]:
    """Per channel: how many videos are ready for a compilation and how many minutes they make."""

    from .radar import channels

    out = []
    for name in channels(root):
        pool = candidates(root, name)
        if pool:
            out.append({"channel": name, "videos": len(pool), "titles": [v["title"] or v["slug"] for v in pool[:12]]})
    return out
