"""Shorts from the finished video: out/<slug>/shorts/short-N.mp4 (1080x1920) + shorts.txt.

The LLM picks the best self-contained moments of the narration (25–58 s, starting on a sentence
that hooks). Each one is cut from video-final.mp4 and made vertical with ffmpeg: the shot centred
over a blurred copy of itself, a hook line on top and big word-by-word captions (the current word
in yellow), like the documentary Shorts that work. No re-planning, no Remotion: ~1 min each.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

from .context import RunContext
from .llm import complete_json

STAGE = "shorts"
DIR = "shorts"
W, H = 1080, 1920

SYSTEM = """
Eres editor de Shorts de YouTube de un canal de historias de atletas. Te paso la narración de un
documental en frases numeradas con sus tiempos. Elige los {count} mejores momentos para Shorts:
- cada uno es un rango CONTINUO de frases [from, to] de {min_s}-{max_s} segundos en total;
- se entiende solo, sin haber visto el vídeo, y la PRIMERA frase engancha (un dato brutal, un
  giro, una pregunta); termina en un final con fuerza, no a medias;
- no se solapan entre sí.
Devuelve SOLO JSON: {{"shorts": [{{"from": 12, "to": 19,
  "hook": "texto de arriba en pantalla, 3-7 palabras, en el idioma de la narración, sin inventar datos",
  "title": "título del Short en el idioma de la narración, máx. 80 caracteres",
  "description": "1-2 frases + 3 hashtags"}}]}}
""".strip()


def sentences(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out, current = [], []
    for word in words:
        current.append(word)
        if word.get("sentenceEnd") or re.search(r"[.!?…]$", word["text"]):
            out.append(current)
            current = []
    if current:
        out.append(current)
    return [{"n": n, "start": s[0]["start"], "end": s[-1]["end"], "words": s,
             "text": " ".join(w["text"] for w in s)} for n, s in enumerate(out)]


def fit(sents: list[dict[str, Any]], first: int, last: int, min_s: float, max_s: float) -> tuple[int, int] | None:
    """Clamp a sentence range to [min_s, max_s] seconds (drop from the end, extend at the end)."""

    first, last = max(0, first), min(len(sents) - 1, last)
    if first > last:
        return None
    while last > first and sents[last]["end"] - sents[first]["start"] > max_s:
        last -= 1
    while last + 1 < len(sents) and sents[last]["end"] - sents[first]["start"] < min_s \
            and sents[last + 1]["end"] - sents[first]["start"] <= max_s:
        last += 1
    length = sents[last]["end"] - sents[first]["start"]
    return (first, last) if min_s * 0.8 <= length <= max_s else None


def pick(ctx: RunContext, sents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cfg = ctx.section("shorts")
    count, min_s, max_s = int(cfg.get("count", 3)), float(cfg.get("min_seconds", 25)), float(cfg.get("max_seconds", 58))
    listing = "\n".join(f"[{s['n']}] ({s['start']:.1f}-{s['end']:.1f}s) {s['text']}" for s in sents)
    result = complete_json(ctx, stage=STAGE, section="planner", max_tokens=3000, user=listing[:60000],
                           system=SYSTEM.format(count=count, min_s=int(min_s), max_s=int(max_s)))
    chosen, taken = [], set()
    for item in result.get("shorts", []):
        try:
            span = fit(sents, int(item["from"]), int(item["to"]), min_s, max_s)
        except (KeyError, TypeError, ValueError):
            continue
        if not span or taken & set(range(span[0], span[1] + 1)):
            continue
        taken |= set(range(span[0], span[1] + 1))
        chosen.append({**item, "from": span[0], "to": span[1]})
        if len(chosen) == count:
            break
    return chosen


def _ass_text(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")")


def ass(words: list[dict[str, Any]], hook: str, offset: float, total: float, font: str = "Inter") -> str:
    """ASS subtitles: the hook on top the whole time; captions of ≤3 words with the spoken one in yellow."""

    def ts(t: float) -> str:
        t = max(0.0, t)
        return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"

    lines = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 0", "",
             "[V4+ Styles]",
             "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
             "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
             f"Style: Hook,{font},84,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,1,0,0,0,100,100,0,0,1,7,2,8,70,70,260,1",
             f"Style: Cap,{font},96,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,1,0,0,0,100,100,0,0,1,8,3,2,60,60,430,1",
             "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
             f"Dialogue: 0,{ts(0)},{ts(total)},Hook,,0,0,0,,{_ass_text(hook.upper())}"]
    chunks, current = [], []
    for word in words:
        current.append(word)
        if len(current) == 3 or re.search(r"[.,;:!?…]$", word["text"]):
            chunks.append(current)
            current = []
    if current:
        chunks.append(current)
    for c, chunk in enumerate(chunks):
        chunk_end = chunks[c + 1][0]["start"] if c + 1 < len(chunks) else chunk[-1]["end"] + 0.3
        for i, word in enumerate(chunk):
            end = chunk[i + 1]["start"] if i + 1 < len(chunk) else chunk_end
            text = " ".join(("{\\c&H00D4FF&}" + _ass_text(w["text"].upper()) + "{\\c&HFFFFFF&}") if j == i
                            else _ass_text(w["text"].upper()) for j, w in enumerate(chunk))
            lines.append(f"Dialogue: 1,{ts(word['start'] - offset)},{ts(min(total, end - offset))},Cap,,0,0,0,,{text}")
    return "\n".join(lines) + "\n"


def font_dir(ctx: RunContext) -> Path:
    """Inter Black as TTF (libass cannot read the woff2 the Remotion side uses)."""

    target = ctx.cache_dir / "fonts"
    ttf = target / "Inter-Black.ttf"
    if not ttf.is_file():
        from fontTools.ttLib import TTFont

        target.mkdir(parents=True, exist_ok=True)
        font = TTFont(ctx.root / "node_modules/@fontsource/inter/files/inter-latin-900-normal.woff")
        font.flavor = None
        font.save(ttf)
    return target


def render_short(ctx: RunContext, video: Path, start: float, length: float, subtitles: str, out: Path) -> None:
    zoom = float(ctx.section("shorts").get("zoom", 1.1))    # the 16:9 shot a bit wider than the screen
    fg_w = round(W * zoom / 2) * 2
    work = out.parent / "_tmp"
    work.mkdir(parents=True, exist_ok=True)
    (work / "subs.ass").write_text(subtitles, encoding="utf-8")
    fonts = font_dir(ctx)
    (work / "fonts").mkdir(exist_ok=True)
    for f in fonts.glob("*.ttf"):
        if not (work / "fonts" / f.name).is_file():
            (work / "fonts" / f.name).write_bytes(f.read_bytes())
    graph = (f"[0:v]split[a][b];[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
             f"boxblur=40:4,eq=brightness=-0.18[bg];[b]scale={fg_w}:-2,crop={min(fg_w, W)}:ih[fg];"
             f"[bg][fg]overlay=(W-w)/2:(H-h)/2-40,ass=subs.ass:fontsdir=fonts,format=yuv420p[v];"
             f"[0:a]afade=t=in:d=0.15,afade=t=out:st={max(0.0, length - 0.4):.2f}:d=0.4[a]")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{start:.3f}", "-t", f"{length:.3f}", "-i", str(video.resolve()),
           "-filter_complex", graph, "-map", "[v]", "-map", "[a]", "-r", "30",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "192k",
           "-movflags", "+faststart", str(out.resolve())]
    result = subprocess.run(cmd, cwd=work, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg (short): {result.stderr[-500:]}")


def inputs(ctx: RunContext) -> list:
    return [ctx.out_dir / "video-final.mp4", ctx.work_dir / "words.json"]


def run(ctx: RunContext) -> None:
    words = ctx.read_json("words.json")["words"]
    timeline = ctx.read_json("timeline.json")
    offset = timeline["audio"].get("voiceFrom", 0) / timeline["fps"]   # narration starts after the cold open
    sents = sentences(words)
    chosen = pick(ctx, sents)
    out_dir = ctx.out_dir / DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("short-*.mp4"):
        old.unlink()
    notes = ["SHORTS · súbelos con «Vídeo relacionado» apuntando al vídeo largo", ""]
    for n, item in enumerate(chosen, 1):
        first, last = sents[item["from"]], sents[item["to"]]
        start = offset + first["start"] - 0.15
        length = last["end"] - first["start"] + 0.6
        spoken = [w for s in sents[item["from"]: item["to"] + 1] for w in s["words"]]
        subtitles = ass(spoken, str(item.get("hook") or ""), first["start"] - 0.15, length)
        target = out_dir / f"short-{n}.mp4"
        render_short(ctx, ctx.out_dir / "video-final.mp4", start, length, subtitles, target)
        print(f"   short-{n}.mp4 · {length:.0f} s · {item.get('hook', '')}")
        notes += [f"short-{n}.mp4 ({length:.0f} s)", f"TÍTULO: {item.get('title', '')}",
                  f"DESCRIPCIÓN: {item.get('description', '')}", ""]
    tmp = out_dir / "_tmp"
    if tmp.is_dir():
        for f in sorted(tmp.rglob("*"), reverse=True):
            f.unlink() if f.is_file() else f.rmdir()
        tmp.rmdir()
    (out_dir / "shorts.txt").write_text("\n".join(notes), encoding="utf-8")
    ctx.write_json("shorts.json", {"shorts": chosen})


def validate(ctx: RunContext) -> bool:
    return (ctx.out_dir / DIR / "shorts.txt").is_file() and any((ctx.out_dir / DIR).glob("short-*.mp4"))
