"""The finished video as a CapCut project to finish by hand: out/<slug>/capcut/ (and <slug>-capcut.zip).

CapCut does not open Premiere's XML, so everything is laid out to be dropped on its timeline, every track from 0:00,
in sync, and as a normal edit would have it: raw pieces, not one baked video.

- 1_video/: the video piece by piece in order (001_clip.mp4, 002_foto.mp4, 003_grafico.mp4…): each shot's own footage
  or photo, clean (no labels, no zoom, no colour grade: that is the editor's), and the designed pieces (graphics,
  maps, chapter cards, end screen) as they are in the video. Selected together and dragged onto the timeline they fall
  one after the other exactly as in the video. cortes.csv: where each one starts and what the voice says.
- 2_audio/: the voice, the music (already lowered under the voice) and the effects (original sound + sound effects),
  each full length from 0:00, and the final mix for reference.
- 3_musica_original/: the songs as they are, named by the second each one starts.
- 4_efectos_sueltos/: every sound effect and every moment of original sound on its own, named by the second it plays.
- rotulos.srt (the on-screen labels as editable text) and the subtitles .srt; capitulos.txt, creditos.txt, LEEME.txt.

    python main.py --capcut VÍDEO        (or a channel: every finished video of it)
"""

from __future__ import annotations

import csv
import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Any

from .context import RunContext
from .export import _link, chapter_markers

FOLDER = "capcut"

README = """CÓMO MONTARLO EN CAPCUT (escritorio)

1. Crea un proyecto nuevo de 1920x1080 a {fps} fps y arrastra esta carpeta entera a «Importar».
2. VÍDEO: en Medios, ordena por nombre, haz clic en 001 y mayúscula+clic en el último ({clips}); arrástralos todos
   juntos a la pista principal empezando en 0:00: quedan uno detrás de otro, como en el vídeo. Van limpios (sin
   rótulos, sin zoom, sin color): ponles tú las transiciones, el zoom y el filtro que quieras. Los «grafico» y
   «capitulo» son los gráficos y las tarjetas ya diseñados.
3. AUDIO: arrastra cada archivo de 2_audio a su propia pista, todos en 0:00:
     1_voz.wav       la narración
     2_musica.wav    la música, ya bajada bajo la voz
     3_efectos.wav   efectos de sonido y sonido original de los clips
   (0_mezcla_final.wav es la mezcla del vídeo publicado: solo de referencia, no la uses junto a las otras.)
4. TEXTOS: Texto → Subtítulos → Importar → rotulos.srt (los rótulos del vídeo, editables: cambia letra y estilo) y,
   si quieres subtítulos, el subtitulos.*.srt.
5. Si quieres cambiar la música o un efecto en concreto, en vez de 2_musica.wav / 3_efectos.wav usa los sueltos:
     3_musica_original/  cada canción entera (sin bajar); el nombre dice en qué segundo empieza
     4_efectos_sueltos/  cada efecto por separado; el nombre dice en qué segundo suena (02m14s300 = 2:14.300)
   cortes.csv tiene el inicio de cada clip de 1_video, y capitulos.txt dónde empieza cada capítulo.

Al exportar desde CapCut: 1080p, {fps} fps. creditos.txt: las fuentes, déjalas en la descripción de YouTube.
"""


def _stamp(seconds: float) -> str:
    """02m14s300: sorts by time in a file list."""

    ms = max(0, round(seconds * 1000))
    return f"{ms // 60000:02d}m{ms // 1000 % 60:02d}s{ms % 1000:03d}"


def _clock(seconds: float) -> str:
    return f"{int(seconds) // 60}:{int(seconds) % 60:02d}"


def _safe(name: str) -> str:
    return re.sub(r"[^\w.-]+", "-", name).strip("-")[:60] or "audio"


def plan_pieces(timeline: dict[str, Any]) -> list[dict[str, Any]]:
    """The video in order as pieces: «clip» (a shot's own footage), «foto» (a photo), «grafico» (a stretch a graphic,
    a map, a panel or a figure covers: consecutive shots under the same one are one piece), «capitulo», «final» (the
    end screen) and «video» (anything else drawn: from the finished video)."""

    groups = sorted(timeline.get("groups") or [], key=lambda g: g["from"])

    def group_at(a: int, b: int) -> dict[str, Any] | None:
        return next((g for g in groups if g["from"] < b and a < g["from"] + g["durationInFrames"]), None)

    pieces: list[dict[str, Any]] = []
    for shot in sorted(timeline.get("shots") or [], key=lambda s: s["from"]):
        a, frames = int(shot["from"]), int(shot["durationInFrames"])
        media = shot.get("media") or {}
        group = group_at(a, a + frames)
        if shot.get("type") == "chapter":
            kind = "capitulo"
        elif shot.get("type") == "endscreen":
            kind = "final"
        elif group is not None:
            kind = "grafico"
        elif media.get("kind") == "video":
            kind = "clip"
        elif media.get("kind") == "image":
            kind = "foto"
        else:
            kind = "video"
        if pieces and kind in ("grafico", "final", "video") and pieces[-1]["kind"] == kind \
                and pieces[-1].get("group") == (group or {}).get("id") and pieces[-1]["from"] + pieces[-1]["frames"] == a:
            pieces[-1]["frames"] += frames
            continue
        pieces.append({"kind": kind, "from": a, "frames": frames, "src": media.get("src") if kind in ("clip", "foto") else None,
                       "rate": media.get("rate"), "group": (group or {}).get("id"), "note": str(shot.get("text") or "")[:80]})
    return pieces


def _encode(inputs: list[str], target: Path, seconds: float, fps: int, rate: float | None = None) -> None:
    """One piece as 1920x1080 at the video's fps, exactly `seconds` long, no sound (the sound goes in its own tracks)."""

    speed = f"setpts=PTS/{rate:.4f}," if rate and 0 < rate < 1 else ""
    subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-t", f"{seconds:.4f}", "-an",
                    "-vf", f"{speed}scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,fps={fps},setsar=1",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", "-pix_fmt", "yuv420p", str(target)],
                   check=True, capture_output=True)


def _srt(items: list[tuple[int, int, str]], fps: int) -> str:
    def t(frames: float) -> str:
        ms = round(frames * 1000 / fps)
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"

    return "".join(f"{n}\n{t(a)} --> {t(a + d)}\n{text}\n\n" for n, (a, d, text) in enumerate(items, 1))


def export(ctx: RunContext, zip_it: bool = True) -> Path:
    from .render import OUTPUT, Renderer, sim_track

    timeline = ctx.read_json("timeline.json")
    renderer = Renderer(ctx)
    fps = renderer.fps
    final = ctx.out_dir / OUTPUT
    if not final.is_file():
        raise RuntimeError("Primero tiene que estar el vídeo terminado (video-final.mp4).")
    folder = ctx.out_dir / FOLDER
    if folder.is_dir():
        shutil.rmtree(folder)

    # 1. the picture, piece by piece: raw clips and photos (no text, no zoom, no colour: yours to do), the designed
    #    pieces (graphics, maps, chapter cards, end screen) as they are in the video
    pieces = plan_pieces(timeline)
    video_dir = folder / "1_video"
    video_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for n, piece in enumerate(pieces, 1):
        target = video_dir / f"{n:03d}_{piece['kind']}.mp4"
        seconds = piece["frames"] / fps
        source = ctx.work_dir / piece["src"] if piece.get("src") else None
        try:
            if piece["kind"] == "clip" and source and source.is_file():
                _encode(["-i", str(source)], target, seconds, fps, rate=piece.get("rate"))
            elif piece["kind"] == "foto" and source and source.is_file():
                _encode(["-loop", "1", "-i", str(source)], target, seconds, fps)
            else:
                raise FileNotFoundError("from the video")
        except (FileNotFoundError, subprocess.CalledProcessError):
            # a designed piece, or a clip the server already cleaned: that stretch of the finished video
            if piece["kind"] in ("clip", "foto"):
                target = target.with_name(f"{n:03d}_{piece['kind']}-del-video.mp4")
            _encode(["-ss", f"{piece['from'] / fps:.4f}", "-i", str(final)], target, seconds, fps)
        rows.append([target.name, _clock(piece["from"] / fps), f"{seconds:.2f}", piece["kind"], piece.get("note", "")])
    clips = rows
    how = "clips limpios"
    with (folder / "cortes.csv").open("w", newline="", encoding="utf-8") as out:
        writer = csv.writer(out)
        writer.writerow(["archivo", "empieza", "dura (s)", "tipo", "qué dice la voz"])
        writer.writerows(rows)
    labels = [x for x in timeline.get("labels") or [] if str(x.get("text") or "").strip()]
    if labels:
        (folder / "rotulos.srt").write_text(_srt([(x["from"], x["durationInFrames"], x["text"]) for x in labels], fps),
                                            encoding="utf-8")

    # 2. the audio tracks, full length from 0:00
    total = int(timeline["durationInFrames"])
    track = sim_track(renderer, timeline)
    if track:
        timeline["audio"]["simTrack"] = track
    tracks = 0
    for only, label in (("voice", "1_voz"), ("music", "2_musica"), ("effects", "3_efectos")):
        try:
            stem = renderer.audio(timeline, only)
        except Exception as error:              # a source file cleaned: the other tracks still go
            print(f"   CapCut: sin pista {label} ({str(error)[:100]})")
            stem = None
        if stem is not None:
            _link(stem, folder / "2_audio" / f"{label}.wav")
            tracks += 1
    mix = sorted(renderer.dir.glob("audio-*.wav"), key=lambda p: p.stat().st_mtime)
    if mix:
        _link(mix[-1], folder / "2_audio" / "0_mezcla_final.wav")
    else:                                       # the mix from the final video itself
        (folder / "2_audio").mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(final), "-vn", "-c:a", "pcm_s16le",
                        str(folder / "2_audio" / "0_mezcla_final.wav")], capture_output=True)

    # 3. the songs as they are, 4. every effect and original sound on its own
    audio = timeline["audio"]
    work = ctx.work_dir
    songs = audio.get("musicParts") or ([{"src": audio["music"], "from": 0}] if audio.get("music") else [])
    for n, part in enumerate(songs, 1):
        source = work / part["src"]
        if source.is_file():
            _link(source, folder / "3_musica_original" / f"{_stamp(part.get('from', 0) / fps)}_{n:02d}_{_safe(source.name)}")
    loose = 0
    for item in audio.get("sfx") or []:
        source = work / item["src"]
        if source.is_file():
            _link(source, folder / "4_efectos_sueltos" / f"{_stamp(item['from'] / fps)}_{_safe(source.name)}")
            loose += 1
    for clip in audio.get("clips") or []:
        source = work / str(clip.get("src") or "")
        if clip.get("src") and source.is_file():
            _link(source, folder / "4_efectos_sueltos" / f"{_stamp(clip['from'] / fps)}_sonido-original_{_safe(source.name)}")
            loose += 1

    # 5. subtitles, chapters, credits, how to
    for extra in [*ctx.out_dir.glob("subtitulos.*.srt"), ctx.out_dir / "creditos.txt"]:
        if extra.is_file():
            _link(extra, folder / extra.name)
    chapters = chapter_markers(timeline)
    if chapters:
        (folder / "capitulos.txt").write_text("".join(f"{_clock(f / fps)} {title}\n" for f, title in chapters), encoding="utf-8")
    (folder / "LEEME.txt").write_text(README.replace("{fps}", str(fps)).replace("{clips}", clips[-1][0] if clips else "—"),
                                      encoding="utf-8")
    print(f"   CapCut: {folder.relative_to(ctx.root)} · {len(clips)} clips ({how}) · {tracks} pistas de audio · "
          f"{len(songs)} canciones · {loose} efectos sueltos · {_clock(total / fps)} de vídeo")
    if not zip_it:
        return folder
    archive = ctx.out_dir / f"{ctx.slug}-capcut.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_STORED) as z:     # video and audio do not compress: just packed
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                z.write(path, f"{ctx.slug}-capcut/{path.relative_to(folder)}")
    print(f"   Descarga: {archive.relative_to(ctx.root)} ({archive.stat().st_size / 1e6:.0f} MB)")
    return archive


def targets(root: Path, name: str) -> list[str]:
    """A video's slug, or every finished video (with its video-final.mp4) of the channel `name`."""

    if (root / "out" / name / "video-final.mp4").is_file():
        return [name]
    from .context import video_folders
    from .web import _channel_of

    return sorted(folder.name for folder in video_folders(root)
                  if _channel_of(root, folder) == name and (root / "out" / folder.name / "video-final.mp4").is_file())
