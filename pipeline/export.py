"""The finished video as a project to open in Premiere Pro or DaVinci Resolve: out/<slug>/premiere/ (and a .zip).

- media/: every render segment in order (picture only, graphics and labels already drawn): each cut of the video is
  its own clip on V1, so a shot can be trimmed, moved or swapped by hand.
- audio/: the voice, the music (already ducked under the voice) and the effects (original sound and SFX), each a
  full-length track from 0:00 — and the final mix, muted, as a reference.
- timeline.xml (Final Cut Pro 7 XML, which both import): V1 with the segments, A1-A3 with the tracks, A4 the mix,
  a marker at every chapter.
- subtítulos .srt and creditos.txt, and LEEME.txt with how to open it.
Nothing is rendered again: the segments are the render's own (hard links when possible, so no extra disk).
"""

from __future__ import annotations

import os
import shutil
import zipfile
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from .context import RunContext

FOLDER = "premiere"


def _link(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.unlink(missing_ok=True)
    try:
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target)


def _rate(fps: int) -> str:
    return f"<rate><timebase>{fps}</timebase><ntsc>FALSE</ntsc></rate>"


def _file(file_id: str, name: str, path: str, frames: int, fps: int, video: bool, audio: bool,
          width: int = 1920, height: int = 1080) -> str:
    media = ""
    if video:
        media += (f"<video><samplecharacteristics>{_rate(fps)}<width>{width}</width><height>{height}</height>"
                  "</samplecharacteristics></video>")
    if audio:
        media += "<audio><samplecharacteristics><depth>16</depth><samplerate>48000</samplerate></samplecharacteristics><channelcount>2</channelcount></audio>"
    return (f'<file id="{file_id}"><name>{escape(name)}</name><pathurl>{escape(path)}</pathurl>{_rate(fps)}'
            f"<duration>{frames}</duration><media>{media}</media></file>")


def _clip(clip_id: str, name: str, start: int, frames: int, fps: int, file_xml: str, enabled: bool = True) -> str:
    return (f'<clipitem id="{clip_id}"><name>{escape(name)}</name><enabled>{"TRUE" if enabled else "FALSE"}</enabled>'
            f"<duration>{frames}</duration>{_rate(fps)}<start>{start}</start><end>{start + frames}</end>"
            f"<in>0</in><out>{frames}</out>{file_xml}</clipitem>")


def timeline_xml(name: str, fps: int, total: int, width: int, height: int, video: list[dict[str, Any]],
                 audio: list[dict[str, Any]], markers: list[tuple[int, str]]) -> str:
    """FCP7 XML: video = [{path, name, start, frames}] on V1; audio = [{path, name, frames, enabled}] one track each."""

    vclips = "".join(_clip(f"v{n}", v["name"], v["start"], v["frames"], fps,
                           _file(f"fv{n}", v["name"], v["path"], v["frames"], fps, True, False, width, height))
                     for n, v in enumerate(video, 1))
    atracks = "".join(f"<track>{_clip(f'a{n}', a['name'], 0, a['frames'], fps, _file(f'fa{n}', a['name'], a['path'], a['frames'], fps, False, True), a.get('enabled', True))}</track>"
                      for n, a in enumerate(audio, 1))
    marks = "".join(f"<marker><name>{escape(text)}</name><in>{at}</in><out>-1</out></marker>" for at, text in markers)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n<xmeml version="5">'
            f'<sequence id="sequence-1"><name>{escape(name)}</name><duration>{total}</duration>{_rate(fps)}'
            f"<timecode>{_rate(fps)}<string>00:00:00:00</string><frame>0</frame><displayformat>NDF</displayformat></timecode>"
            f"{marks}<media><video><format><samplecharacteristics>{_rate(fps)}<width>{width}</width><height>{height}</height>"
            "<pixelaspectratio>square</pixelaspectratio></samplecharacteristics></format>"
            f"<track>{vclips}</track></video><audio>{atracks}</audio></media></sequence></xmeml>\n")


def chapter_markers(timeline: dict[str, Any]) -> list[tuple[int, str]]:
    out = []
    for shot in timeline.get("shots", []):
        if shot.get("type") == "chapter":
            out.append((int(shot["from"]), str(shot.get("chapterTitle") or shot.get("text") or "Capítulo")[:60]))
    return out


README = """CÓMO ABRIRLO

Premiere Pro: Archivo > Importar… > timeline.xml. Si algún clip sale «sin conexión», clic derecho >
Vincular medios… y elige esta misma carpeta (están en media/ y audio/).

DaVinci Resolve: File > Import > Timeline… > timeline.xml, con «Automatically import source clips into
media pool» marcado. Si pide la carpeta, elige esta.

QUÉ HAY

V1  el vídeo, un clip por corte (con los gráficos, rótulos y créditos ya dibujados)
A1  la voz
A2  la música (ya baja bajo la voz)
A3  efectos: sonido original y golpes de sonido
A4  la mezcla final, silenciada (de referencia)
Marcadores: un marcador en cada capítulo.
subtitulos.*.srt: subtítulos · creditos.txt: las fuentes (déjalas en la descripción si cambias algo)

Al exportar desde Premiere/DaVinci: 1920x1080, {fps} fps, H.264, audio a -16 LUFS.
"""


def export(ctx: RunContext, zip_it: bool = True) -> Path:
    from .render import OUTPUT, Renderer, media_seconds, plan_segments

    timeline = ctx.read_json("timeline.json")
    renderer = Renderer(ctx)
    fps = renderer.fps
    listing = renderer.dir / "segments.txt"
    if not (ctx.out_dir / OUTPUT).is_file() or not listing.is_file():
        raise RuntimeError("Primero hay que renderizar el vídeo: la exportación usa los tramos del render.")
    files = [Path(line[len("file '"):-1]) for line in listing.read_text("utf-8").splitlines() if line.startswith("file '")]
    segments = plan_segments(timeline, bool(renderer.cfg.get("hybrid", True)))
    if len(files) != len(segments) or not all(f.is_file() for f in files):
        raise RuntimeError("Los tramos del render no están completos: vuelve a renderizar y exporta otra vez.")

    folder = ctx.out_dir / FOLDER
    if folder.is_dir():
        shutil.rmtree(folder)
    video = []
    for n, (segment, source) in enumerate(zip(segments, files), 1):
        name = f"{n:03d}_{segment.shots[0]['id'].split('~')[0]}.mp4"
        _link(source, folder / "media" / name)
        video.append({"path": f"media/{name}", "name": name, "start": segment.start, "frames": segment.frames})

    total = int(timeline["durationInFrames"])
    audio = []
    for only, label in (("voice", "voz"), ("music", "musica"), ("effects", "efectos")):
        stem = renderer.audio(timeline, only)
        if stem is not None:
            _link(stem, folder / "audio" / f"{label}.wav")
            audio.append({"path": f"audio/{label}.wav", "name": f"{label}.wav", "frames": total})
    mix = sorted(renderer.dir.glob("audio-*.wav"), key=lambda p: p.stat().st_mtime)
    if mix:
        _link(mix[-1], folder / "audio" / "mezcla-final.wav")
        audio.append({"path": "audio/mezcla-final.wav", "name": "mezcla-final.wav",
                      "frames": min(total, round(media_seconds(mix[-1]) * fps) or total), "enabled": False})

    for extra in [*ctx.out_dir.glob("subtitulos.*.srt"), ctx.out_dir / "creditos.txt"]:
        if extra.is_file():
            _link(extra, folder / extra.name)
    video_cfg = ctx.section("video")
    (folder / "timeline.xml").write_text(
        timeline_xml(ctx.slug, fps, total, int(video_cfg.get("width", 1920)), int(video_cfg.get("height", 1080)),
                     video, audio, chapter_markers(timeline)), encoding="utf-8")
    (folder / "LEEME.txt").write_text(README.replace("{fps}", str(fps)), encoding="utf-8")
    print(f"   Proyecto para Premiere/DaVinci: {folder.relative_to(ctx.root)} · {len(video)} clips · {len(audio)} pistas de audio")
    if not zip_it:
        return folder
    archive = ctx.out_dir / f"{ctx.slug}-premiere.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_STORED) as z:     # video does not compress: just packed
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                z.write(path, f"{ctx.slug}-premiere/{path.relative_to(folder)}")
    print(f"   Descarga: {archive.relative_to(ctx.root)} ({archive.stat().st_size / 1e6:.0f} MB)")
    return archive
