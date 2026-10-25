"""Shorts from the finished video: out/<slug>/shorts/short-N.mp4 (1080x1920) + shorts.txt.

The LLM picks the strongest self-contained moments of the narration (25–58 s, starting on a sentence that hooks;
the sentences with a graphic or an original moment on screen are marked ★, the ones the video's opening chose too).

`shorts.style: native` (default): that stretch of the video's own timeline is rendered again in vertical with
Remotion — footage filling the 9:16 frame, every graphic (the paper ones, the maps…) in a 16:9 window in the upper
middle, big captions following the voice — and the finished video's own sound (voice, music, effects) is laid
under it. `blur` (and the fallback if Remotion fails): the 16:9 cut centred over a blurred copy of itself with
ffmpeg, ~1 min each. Both carry the hook line on top.
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
- no se solapan entre sí;
- las frases marcadas con ★ tienen en pantalla un gráfico o un momento original con su sonido: prefiere los
  tramos que tengan alguna, son los más vistosos en vertical.
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


def pick(ctx: RunContext, sents: list[dict[str, Any]], strong: set[int] | None = None) -> list[dict[str, Any]]:
    cfg = ctx.section("shorts")
    count, min_s, max_s = int(cfg.get("count", 3)), float(cfg.get("min_seconds", 25)), float(cfg.get("max_seconds", 58))
    strong = strong or set()
    listing = "\n".join(f"[{s['n']}] ({s['start']:.1f}-{s['end']:.1f}s) {'★ ' if s['n'] in strong else ''}{s['text']}"
                        for s in sents)
    result = complete_json(ctx, stage=STAGE, section="planner", max_tokens=3000,
                           user=f"IDIOMA DE hook/title/description: {ctx.language}\n\n" + listing[:60000],
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


def vertical_props(timeline: dict[str, Any], a: int, b: int, captions: list[dict[str, Any]]) -> dict[str, Any]:
    """Frames [a, b) of the video's timeline as a 1080x1920 timeline of their own (Documentary's vertical layout):
    the shots cut at both ends, the graphics that start inside (a graphic already half way is left out), the
    captions of those frames; silent (the finished video's sound goes under it)."""

    def inside(items: list[dict[str, Any]], whole: bool = True) -> list[dict[str, Any]]:
        out = []
        for item in items:
            start, end = item["from"], item["from"] + item["durationInFrames"]
            if start < a or start >= b or (whole and end - start < 8):
                continue
            out.append({**item, "from": start - a, "durationInFrames": min(end, b) - start})
        return out

    shots = []
    for shot in timeline["shots"]:
        start, end = shot["from"], shot["from"] + shot["durationInFrames"]
        if end <= a or start >= b or shot.get("type") == "endscreen":
            continue
        piece = {**shot, "from": max(start, a) - a, "durationInFrames": min(end, b) - max(start, a)}
        if start < a or end > b:                    # a piece of a longer shot: same move, from where it was
            piece.update(offset=(shot.get("offset") or 0) + max(0, a - start),
                         fullDuration=shot.get("fullDuration") or shot["durationInFrames"])
        shots.append(piece)
    audio = {**timeline["audio"], "music": None, "musicParts": [], "speech": [], "sfx": [], "clips": [],
             "voiceFrom": 0, "voiceGaps": []}
    return {**timeline, "width": W, "height": H, "durationInFrames": b - a, "shots": shots,
            "groups": inside(timeline["groups"]), "labels": [], "transitions": [], "shakes": [],
            "captions": inside(captions, whole=False), "endscreenFrames": 0, "audio": audio}


def render_native(ctx: RunContext, timeline: dict[str, Any], captions: list[dict[str, Any]], start: float,
                  length: float, hook: str, out: Path) -> None:
    """The stretch rendered vertical with Remotion, then the finished video's sound and the hook laid on top."""

    from .render import Renderer, graphic_media

    fps = timeline["fps"]
    a = max(0, round(start * fps))
    b = min(timeline["durationInFrames"], a + round(length * fps))
    props = vertical_props(timeline, a, b, captions)
    public = {s["media"]["src"] for s in props["shots"] if s.get("media")} | {props["audio"]["voice"]}
    public |= {m["src"] for g in props["groups"] for m in graphic_media(g.get("graphic"))}
    renderer = Renderer(ctx)
    raw = out.with_name(out.stem + ".raw.mp4")
    renderer.remotion("Documentary", props, raw, ["--muted", f"--concurrency={renderer.concurrency()}", "--codec=h264",
                                                  "--crf=18"], public)
    work = out.parent / "_tmp"
    work.mkdir(parents=True, exist_ok=True)
    (work / "hook.ass").write_text(ass([], hook, 0.0, length), encoding="utf-8")
    fonts = font_dir(ctx)
    (work / "fonts").mkdir(exist_ok=True)
    for f in fonts.glob("*.ttf"):
        if not (work / "fonts" / f.name).is_file():
            (work / "fonts" / f.name).write_bytes(f.read_bytes())
    seconds = (b - a) / fps
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw.resolve()), "-ss", f"{a / fps:.3f}", "-t", f"{seconds:.3f}",
           "-i", str((ctx.out_dir / "video-final.mp4").resolve()),
           "-filter_complex", f"[0:v]ass=hook.ass:fontsdir=fonts,format=yuv420p[v];"
                              f"[1:a]afade=t=in:d=0.15,afade=t=out:st={max(0.0, seconds - 0.4):.2f}:d=0.4[a]",
           "-map", "[v]", "-map", "[a]", "-r", str(fps), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
           "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(out.resolve())]
    result = subprocess.run(cmd, cwd=work, capture_output=True, text=True)
    raw.unlink(missing_ok=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg (short vertical): {result.stderr[-500:]}")


def strong_sentences(timeline: dict[str, Any], sents: list[dict[str, Any]], final: Any) -> set[int]:
    """Sentences with a graphic or an original moment (a clip with its own sound) on screen: the showy ones."""

    fps = timeline["fps"]
    spans = [(g["from"] / fps, (g["from"] + g["durationInFrames"]) / fps) for g in timeline["groups"]
             if g.get("kind") == "graphic"]
    spans += [(c["from"] / fps, (c["from"] + c.get("durationInFrames", 0)) / fps) for c in timeline["audio"].get("clips", [])
              if "from" in c]
    out = set()
    for s in sents:
        a, b = final(s["start"]), final(s["end"])
        if any(x < b and a < y for x, y in spans):
            out.add(s["n"])
    return out


def inputs(ctx: RunContext) -> list:
    return [ctx.out_dir / "video-final.mp4", ctx.work_dir / "words.json"]


def enabled(ctx: RunContext) -> bool:
    return bool(ctx.section("shorts").get("enabled", False))


def outputs(ctx: RunContext) -> list:
    return [ctx.out_dir / DIR / "shorts.txt"] if enabled(ctx) else []


def run(ctx: RunContext) -> None:
    if not enabled(ctx):
        print("   Shorts desactivados (python main.py --shorts <vídeo> para hacerlos)")
        return
    words = ctx.read_json("words.json")["words"]
    timeline = ctx.read_json("timeline.json")
    fps = timeline["fps"]
    offset = timeline["audio"].get("voiceFrom", 0) / fps   # narration starts after the cold open
    gaps = timeline["audio"].get("voiceGaps", [])

    def final(t: float) -> float:   # voice seconds → seconds in the video (cold open and moments included)
        return offset + t + sum(frames / fps for at, frames in gaps if at / fps <= t)

    sents = sentences(words)
    chosen = pick(ctx, sents, strong_sentences(timeline, sents, final))
    native = str(ctx.section("shorts").get("style", "native")) == "native" and timeline.get("height", 1080) < timeline.get("width", 1920)
    vertical_captions: list[dict[str, Any]] = []
    if native:
        from .schemas import Timeline, WordsFile
        from .timeline import captions

        try:
            vertical_captions = [c.model_dump(by_alias=True) for c in captions(
                WordsFile.model_validate(ctx.read_json("words.json")), Timeline.model_validate(timeline))]
        except Exception as error:             # no captions: the short still works
            print(f"   Shorts sin subtítulos: {str(error)[:100]}")
    out_dir = ctx.out_dir / DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("short-*.mp4"):
        old.unlink()
    notes = ["SHORTS · súbelos con «Vídeo relacionado» apuntando al vídeo largo", ""]
    for n, item in enumerate(chosen, 1):
        first, last = sents[item["from"]], sents[item["to"]]
        start = final(first["start"]) - 0.15
        length = final(last["end"]) - final(first["start"]) + 0.6
        spoken = [{**w, "start": final(w["start"]), "end": final(w["end"])}
                  for s in sents[item["from"]: item["to"] + 1] for w in s["words"]]
        subtitles = ass(spoken, str(item.get("hook") or ""), start, length)
        target = out_dir / f"short-{n}.mp4"
        made = False
        if native:
            try:
                render_native(ctx, timeline, vertical_captions, start, length, str(item.get("hook") or ""), target)
                made = True
            except Exception as error:          # the blurred version is always possible
                print(f"   short-{n}: vertical con Remotion no disponible ({str(error)[:120]}); va con fondo desenfocado")
        if not made:
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
    if not enabled(ctx):
        return True
    return (ctx.out_dir / DIR / "shorts.txt").is_file() and any((ctx.out_dir / DIR).glob("short-*.mp4"))
