"""Subtítulos de la narración, siempre en pantalla (timeline.subtitles), como los canales de crímenes reales y de
historias: abajo en el centro, una o dos líneas sobre una franja oscura, con la palabra clave de cada frase en el color
del canal.

- timeline (pipeline/timeline.py) los calcula de las palabras de la voz: `cues()` → timeline.subtitles (fotogramas
  del vídeo final, ya contando la apertura y las pausas de los momentos).
- el doblaje (pipeline/dub.py) los rehace con las palabras de la voz nueva.
- render (pipeline/render.py) los quema al final con libass (`burn()`); el vídeo sin ellos se guarda como
  video-limpio.mp4, del que salen los Shorts (que llevan sus propios subtítulos).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any, Callable

MAX_WORDS = 8            # una o dos líneas cortas
MAX_CHARS = 46
PAUSE = 0.45             # s de silencio que cierran un subtítulo
HOLD = 0.35              # s que sigue en pantalla tras la última palabra
CLEAN = "video-limpio.mp4"


def cues(words: list[dict[str, Any]], frame_of: Callable[[float], int], fps: int,
         blocked: list[tuple[int, int]] | None = None) -> list[dict[str, Any]]:
    """Trozos de hasta MAX_WORDS palabras / MAX_CHARS letras (un signo de puntuación o una pausa los cierra), puestos
    donde la voz los dice. `blocked`: tramos (fotogramas) con el texto ya en pantalla (paneles de pregunta)."""

    phrases: list[list[dict[str, Any]]] = []             # first by punctuation and pauses…
    for word in words:
        if not str(word.get("text", "")).strip():
            continue
        last = phrases[-1][-1] if phrases else None
        if (not phrases or float(word["start"]) - float(last["end"]) > PAUSE
                or re.search(r"[.!?…;:,]$", str(last["text"]).strip())):
            phrases.append([])
        phrases[-1].append(word)
    chunks: list[list[dict[str, Any]]] = []                # …then long phrases into even pieces
    for phrase in phrases:
        length = len(" ".join(str(w["text"]).strip() for w in phrase))
        pieces = max(1, -(-len(phrase) // MAX_WORDS), -(-length // MAX_CHARS))
        size = -(-len(phrase) // pieces)
        chunks += [phrase[i:i + size] for i in range(0, len(phrase), size)]
    out: list[dict[str, Any]] = []
    for i, chunk in enumerate(chunks):
        start = frame_of(float(chunk[0]["start"]))
        end = frame_of(float(chunk[-1]["end"])) + round(HOLD * fps)
        if i + 1 < len(chunks):
            end = min(end, frame_of(float(chunks[i + 1][0]["start"])))
        if end <= start or any(a < end and start < b for a, b in blocked or []):
            continue
        out.append({"from": start, "durationInFrames": end - start,
                    "text": " ".join(str(w["text"]).strip() for w in chunk)})
    return out


def _ts(seconds: float) -> str:
    seconds = max(0.0, seconds)
    return f"{int(seconds // 3600)}:{int(seconds % 3600 // 60):02d}:{seconds % 60:05.2f}"


def ass(subtitles: list[dict[str, Any]], fps: int, width: int, height: int, font: str = "Inter") -> str:
    """El archivo de libass: blanco sobre franja negra translúcida, la palabra clave en amarillo."""

    from .shorts import _ass_text, key_word

    size = round(height * 0.042)
    lines = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {width}", f"PlayResY: {height}", "WrapStyle: 0", "",
             "[V4+ Styles]",
             "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
             "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, "
             "MarginV, Encoding",
             f"Style: Sub,{font},{size},&H00FFFFFF,&H00FFFFFF,&HFF000000,&H70000000,0,0,0,0,100,100,0,0,4,"
             f"{round(size * 0.28)},0,2,{round(width * 0.18)},{round(width * 0.18)},{round(height * 0.075)},1",
             "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    for cue in subtitles:
        words = str(cue["text"]).split()
        key = key_word(words)
        text = " ".join("{\\c&H00D4FF&}" + _ass_text(w.replace("*", "")) + "{\\c&HFFFFFF&}" if i == key
                        else _ass_text(w.replace("*", "")) for i, w in enumerate(words))
        start = cue["from"] / fps
        lines.append(f"Dialogue: 0,{_ts(start)},{_ts(start + cue['durationInFrames'] / fps)},Sub,,0,0,0,,{text}")
    return "\n".join(lines) + "\n"


def burn(ctx: Any, final: Path, timeline: dict[str, Any], encoder: list[str] | None = None) -> bool:
    """Quema timeline["subtitles"] en el vídeo final (una pasada de ffmpeg); el original queda como video-limpio.mp4.
    False si no hay subtítulos o si libass falla (el vídeo se queda sin ellos, nunca se pierde)."""

    subtitles = timeline.get("subtitles") or []
    if not subtitles:
        final.with_name(CLEAN).unlink(missing_ok=True)      # a cut from an earlier render with subtitles: stale
        return False
    from .shorts import font_dir

    work = final.parent / "_subs"
    work.mkdir(parents=True, exist_ok=True)
    (work / "subs.ass").write_text(ass(subtitles, int(timeline["fps"]), int(timeline["width"]), int(timeline["height"])),
                                   encoding="utf-8")
    fonts = work / "fonts"
    fonts.mkdir(exist_ok=True)
    for f in font_dir(ctx).glob("*.ttf"):
        if not (fonts / f.name).is_file():
            (fonts / f.name).write_bytes(f.read_bytes())
    clean = final.with_name(CLEAN)
    final.replace(clean)
    tmp = final.with_suffix(".subs.mp4")
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(clean.resolve()), "-vf", "ass=subs.ass:fontsdir=fonts",
           *(encoder or ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18"]), "-pix_fmt", "yuv420p",
           "-c:a", "copy", "-movflags", "+faststart", str(tmp.resolve())]
    done = subprocess.run(cmd, cwd=work, capture_output=True, text=True)
    if done.returncode != 0 or not tmp.is_file():
        clean.replace(final)
        print(f"   Subtítulos no quemados ({(done.stderr or '').strip()[-160:]}): el vídeo sale sin ellos")
        return False
    tmp.replace(final)
    print(f"   Subtítulos: {len(subtitles)} en pantalla (sin ellos: out/{ctx.slug}/{CLEAN})")
    return True
