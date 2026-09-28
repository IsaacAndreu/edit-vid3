"""Dubbed versions that reuse the finished video: same clips, same order, retimed to a new voice.

You record (or get) the narration in another language and leave it next to the original:
    materiales/CarlosYulo/voz-en.mp3            (+ optional guion-en.txt, the translated script)
Then `python main.py --dub CarlosYulo:en` (or the night queue, which picks these up by itself)
creates materiales/CarlosYulo-en/ and builds out/CarlosYulo-en/video-final.mp4 in ~15-25 min:

1. The new voice is transcribed/aligned (align stage, in the new language). Without a
   guion-en.txt, the transcript itself becomes the script.
2. The LLM matches each original sentence with where it starts in the new narration. Those
   anchors give a time map (piecewise linear), and every cut, panel, label and chapter of the
   original timeline is moved with it. Question panels take the new words as they are spoken.
3. A shot that now lasts longer than its clip plays in gentle slow motion (up to 1.5x, then the
   last frame holds); clips of third parties never pass 5 s (the next shot takes the rest).
4. On-screen texts (chapter titles, places, stat labels, panels) are translated; names and
   numbers stay. "CAPÍTULO"/"Fuente" become the words of the new language.
5. QA, render, Shorts and thumbnails/titles run as usual. No new search, judge or download.
"""

from __future__ import annotations

import bisect
import copy
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import yaml

from . import align
from .context import RunContext
from .llm import complete_json
from .schemas import MAX_THIRD_PARTY_SECONDS, Timeline
from .shorts import sentences

STAGE = "dub"
LANGUAGES = {
    "en": ("English", "CHAPTER", "Source"), "pt": ("Português", "CAPÍTULO", "Fonte"),
    "fr": ("Français", "CHAPITRE", "Source"), "it": ("Italiano", "CAPITOLO", "Fonte"),
    "de": ("Deutsch", "KAPITEL", "Quelle"), "es": ("Español", "CAPÍTULO", "Fuente"),
}
LINKED = ("media", "media_fallback", "people", "coldopen", "audio")
COPIED = ("shots.json", "selection.json", "fallback.json", "coldopen.json", "people.json", "costs.json")
MAX_SLOWMO = 1.5
MIN_SHOT_FRAMES = 12

MATCH_SYSTEM = """
Te paso las frases numeradas de la narración ORIGINAL de un documental y las de su versión
TRADUCIDA (que puede juntar o partir frases). Para cada frase original di en qué frase traducida
empieza su contenido. Los índices deben ir en orden creciente (o iguales si dos originales se
juntaron en una traducida). Devuelve SOLO JSON: {"map": [[original, traducida], ...]} con todas las
frases originales que puedas situar con seguridad.
""".strip()

TRANSLATE_SYSTEM = """
Traduce al {language} los textos en pantalla de un documental deportivo. Mantén MAYÚSCULAS si el
original las usa, nombres propios, cifras y la brevedad (mismo largo aproximado). Devuelve SOLO
JSON: {{"texts": {{"id": "traducción", ...}}}} con los mismos ids.
""".strip()


def dub_slug(slug: str, lang: str) -> str:
    return f"{slug}-{lang}"


def pending(root: Path) -> list[tuple[str, str]]:
    """(slug, lang) whose original video is done and has a voz-<lang>.mp3 without its dubbed video yet."""

    out = []
    materials = root / "materiales"
    for voice in sorted(materials.glob("*/voz-*.mp3")) if materials.is_dir() else []:
        slug, lang = voice.parent.name, voice.stem.split("-", 1)[1]
        if (root / "out" / slug / "video-final.mp4").is_file() \
                and not (root / "out" / dub_slug(slug, lang) / "video-final.mp4").is_file():
            out.append((slug, lang))
    return out


def prepare(root: Path, slug: str, lang: str) -> str:
    """materiales/<slug>-<lang>/ with the new voice (+ translated script) and the dub config."""

    source = root / "materiales" / slug
    voice = source / f"voz-{lang}.mp3"
    if not voice.is_file():
        raise FileNotFoundError(f"Falta {voice} (la narración traducida)")
    target = root / "materiales" / dub_slug(slug, lang)
    target.mkdir(parents=True, exist_ok=True)
    if not (target / "voz.mp3").is_file() or (target / "voz.mp3").stat().st_size != voice.stat().st_size:
        shutil.copy2(voice, target / "voz.mp3")
    if (source / f"guion-{lang}.txt").is_file():
        shutil.copy2(source / f"guion-{lang}.txt", target / "guion.txt")
    if (source / f"titulo-{lang}.txt").is_file():
        shutil.copy2(source / f"titulo-{lang}.txt", target / "titulo.txt")
    config: dict[str, Any] = {}
    if (source / "config.yaml").is_file():
        config = yaml.safe_load((source / "config.yaml").read_text("utf-8")) or {}
    config.setdefault("align", {})["language"] = lang
    config["align"]["min_match_ratio"] = 0.6          # a translated script never matches word for word
    config["dub"] = {"of": slug, "lang": lang}
    (target / "config.yaml").write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return target.name


# --- time map ------------------------------------------------------------------------------------

def anchors(pairs: list[tuple[int, int]], old: list[dict[str, Any]], new: list[dict[str, Any]],
            old_total: float, new_total: float) -> list[tuple[float, float]]:
    """(old time, new time) points, strictly increasing on both axes, from sentence matches."""

    points = [(0.0, 0.0)]
    for o, n in sorted(pairs):
        if not (0 <= o < len(old) and 0 <= n < len(new)):
            continue
        point = (old[o]["start"], new[n]["start"])
        if point[0] > points[-1][0] + 0.2 and point[1] > points[-1][1] + 0.2:
            points.append(point)
    if old_total > points[-1][0] and new_total > points[-1][1]:
        points.append((old_total, new_total))
    return points


def time_map(points: list[tuple[float, float]]):
    xs = [p[0] for p in points]

    def f(t: float) -> float:
        i = min(max(bisect.bisect_right(xs, t) - 1, 0), len(points) - 2)
        (x0, y0), (x1, y1) = points[i], points[i + 1]
        return y0 + (t - x0) * (y1 - y0) / (x1 - x0)

    return f


def retime(timeline: dict[str, Any], f, new_voice_seconds: float, max_third_party: float) -> dict[str, Any]:
    """Move every cut/overlay after the cold open with f (voice seconds → voice seconds)."""

    fps, vf = timeline["fps"], timeline["audio"].get("voiceFrom", 0)
    gaps = [tuple(g) for g in timeline["audio"].get("voiceGaps", [])]          # (voice frame, frames)
    new_gaps = [(round(f(at / fps) * fps), frames) for at, frames in gaps]
    total = vf + round(new_voice_seconds * fps) + sum(b for _, b in gaps)

    def frame(old: int) -> int:
        """Old video frame → new one: voice time goes through f, moments keep their length."""

        if old <= vf:
            return old
        voice, before = old - vf, 0
        for (at, frames), (new_at, _) in zip(gaps, new_gaps):
            start = at + before                   # where this pause begins in the old video (after vf)
            if voice < start:
                break
            if voice < start + frames:            # inside the pause: same offset from its start
                return vf + new_at + before + (voice - start)
            before += frames
        v = voice - before
        return vf + final_frame(round(f(v / fps) * fps), new_gaps)

    out = copy.deepcopy(timeline)
    shots = out["shots"]
    bounds = [frame(s["from"]) for s in shots] + [total]
    # keep order, a minimum length, and third-party clips ≤ 5 s (the next shot takes the rest)
    for i in range(1, len(shots)):
        bounds[i] = max(bounds[i], bounds[i - 1] + MIN_SHOT_FRAMES)
        media = shots[i - 1].get("media") or {}
        if media.get("kind") == "video" and media.get("source") == "youtube":
            bounds[i] = min(bounds[i], bounds[i - 1] + int(max_third_party * fps))
    for i in range(len(shots) - 1, 0, -1):               # squeeze back if the end was overrun
        bounds[i] = min(bounds[i], bounds[i + 1] - MIN_SHOT_FRAMES)
    for shot, a, b in zip(shots, bounds, bounds[1:]):
        shot["from"], shot["durationInFrames"] = a, b - a
    for item in [*out["groups"], *out.get("labels", [])]:
        a = frame(item["from"])
        b = min(total, max(a + 1, frame(item["from"] + item["durationInFrames"])))
        item["from"], item["durationInFrames"] = a, b - a
    for sfx in out["audio"].get("sfx", []):
        sfx["from"] = frame(sfx["from"])
    for clip in out["audio"].get("clips", []):
        clip["from"] = frame(clip["from"])
    out["audio"]["voiceGaps"] = [list(g) for g in new_gaps]
    out["durationInFrames"] = total
    return out


def final_frame(voice_frame: int, gaps: list) -> int:
    """Voice frame → frames after voiceFrom, counting the pauses before it."""

    return voice_frame + sum(frames for at, frames in gaps if at <= voice_frame)


# --- media ---------------------------------------------------------------------------------------

def _seconds(path: Path) -> float:
    result = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                            capture_output=True, text=True)
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def slow_motion(source: Path, target: Path, seconds: float) -> None:
    """Stretch a clip to `seconds`: slow motion up to 1.5x, then hold the last frame."""

    length = _seconds(source) or seconds
    factor = min(MAX_SLOWMO, seconds / length)
    hold = max(0.0, seconds - length * factor)
    target.parent.mkdir(parents=True, exist_ok=True)
    filters = f"setpts={factor:.4f}*PTS,fps=30" + (f",tpad=stop_mode=clone:stop_duration={hold:.3f}" if hold > 0 else "")
    result = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(source), "-vf", filters, "-an",
                             "-t", f"{seconds:.3f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "16",
                             "-pix_fmt", "yuv420p", str(target)], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg (cámara lenta): {result.stderr[-300:]}")


def _link_tree(source: Path, target: Path) -> None:
    """Hard links (no extra disk) with a copy fallback. Read-only use: never write to these files."""

    for path in source.rglob("*"):
        if not path.is_file():
            continue
        dest = target / path.relative_to(source)
        if dest.exists():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(path, dest)
        except OSError:
            shutil.copy2(path, dest)


# --- texts ---------------------------------------------------------------------------------------

def screen_texts(timeline: dict[str, Any]) -> dict[str, str]:
    texts: dict[str, str] = {"title": timeline["title"]}
    for shot in timeline["shots"]:
        if shot.get("chapterTitle"):
            texts[f"chapter:{shot['id']}"] = shot["chapterTitle"]
    for i, label in enumerate(timeline.get("labels", [])):
        if label["kind"] != "name":
            texts[f"label:{i}"] = label["text"]
    for group in timeline["groups"]:
        for key in ("title", "note"):
            if group.get(key):
                texts[f"group:{group['id']}:{key}"] = group[key]
        if group.get("stat") and group["stat"].get("label"):
            texts[f"stat:{group['id']}"] = group["stat"]["label"]
        for s, step in enumerate(group.get("steps", [])):
            for r, row in enumerate(step.get("rows", [])):
                for key, value in row.items():
                    if isinstance(value, str) and re.search(r"[A-Za-zÁÉÍÓÚáéíóúñÑ]{3}", value):
                        texts[f"row:{group['id']}:{s}:{r}:{key}"] = value
    return texts


def apply_texts(timeline: dict[str, Any], texts: dict[str, str]) -> None:
    timeline["title"] = texts.get("title", timeline["title"])
    for shot in timeline["shots"]:
        shot["chapterTitle"] = texts.get(f"chapter:{shot['id']}", shot.get("chapterTitle"))
    for i, label in enumerate(timeline.get("labels", [])):
        label["text"] = texts.get(f"label:{i}", label["text"])
    for group in timeline["groups"]:
        for key in ("title", "note"):
            if group.get(key):
                group[key] = texts.get(f"group:{group['id']}:{key}", group[key])
        if group.get("stat") and group["stat"].get("label"):
            group["stat"]["label"] = texts.get(f"stat:{group['id']}", group["stat"]["label"])
        for s, step in enumerate(group.get("steps", [])):
            for r, row in enumerate(step.get("rows", [])):
                for key in list(row):
                    row[key] = texts.get(f"row:{group['id']}:{s}:{r}:{key}", row[key])


def question_words(timeline: dict[str, Any], words: list[dict[str, Any]]) -> None:
    """Question panels show the new narration's words as they are spoken."""

    fps, vf = timeline["fps"], timeline["audio"].get("voiceFrom", 0)
    gaps = timeline["audio"].get("voiceGaps", [])

    def at(t: float) -> int:
        return vf + final_frame(round(t * fps), gaps)

    for group in timeline["groups"]:
        if group["kind"] != "question":
            continue
        a, b = group["from"], group["from"] + group["durationInFrames"]
        spoken = [w for w in words if a <= at(w["start"]) < b]
        group["words"] = [{"text": w["text"], "from": max(0, at(w["start"]) - a)} for w in spoken]


def speech_spans(words: list[dict[str, Any]], fps: int, offset: int, gap: float = 0.5,
                 pauses: list | None = None) -> list[list[int]]:
    spans: list[list[float]] = []
    for w in words:
        if spans and w["start"] - spans[-1][1] < gap:
            spans[-1][1] = w["end"]
        else:
            spans.append([w["start"], w["end"]])
    out = []
    for a, b in spans:
        fa, fb = round(a * fps), round(b * fps)
        cuts = [at for at, _ in pauses or [] if fa < at < fb]
        for s, e in zip([fa, *cuts], [*cuts, fb]):
            end = final_frame(e - 1, pauses or []) + 1 if e in cuts else final_frame(e, pauses or [])
            out.append([offset + final_frame(s, pauses or []), offset + end])
    return out


# --- run -----------------------------------------------------------------------------------------

def _script_from_voice(ctx: RunContext) -> None:
    from .whisper_local import transcribe

    cfg = ctx.section("align")
    raw, _ = transcribe(ctx.materials_dir / "voz.mp3", cache_dir=ctx.cache_dir, model=str(cfg.get("model", "medium")),
                        language=str(cfg.get("language", "en")), compute_type=str(cfg.get("compute_type", "int8")))
    text = " ".join(w["word"].strip() for w in raw["words"])
    (ctx.materials_dir / "guion.txt").write_text(text + "\n", encoding="utf-8")


def run(ctx: RunContext) -> None:
    cfg = ctx.section("dub")
    original = RunContext.create(str(cfg["of"]), root=ctx.root)
    lang = str(cfg.get("lang") or ctx.section("align").get("language", "en"))
    language, chapter_word, source_word = LANGUAGES.get(lang, (lang, "CHAPTER", "Source"))
    old_timeline = original.read_json("timeline.json")
    old_words = original.read_json("words.json")

    print(f"[1/6] Voz en {language}: transcripción y alineado")
    if not (ctx.materials_dir / "guion.txt").is_file():
        _script_from_voice(ctx)
    align.run(ctx)
    new_words = ctx.read_json("words.json")

    print("[2/6] Emparejando frases original ↔ traducción")
    old_s, new_s = sentences(old_words["words"]), sentences(new_words["words"])
    listing = ("ORIGINAL:\n" + "\n".join(f"[{s['n']}] {s['text']}" for s in old_s)
               + "\n\nTRADUCIDA:\n" + "\n".join(f"[{s['n']}] {s['text']}" for s in new_s))
    matched = complete_json(ctx, stage=STAGE, section="planner", system=MATCH_SYSTEM, user=listing[:100000], max_tokens=8000)
    pairs = [(int(p[0]), int(p[1])) for p in matched.get("map", []) if isinstance(p, list) and len(p) == 2]
    points = anchors(pairs, old_s, new_s, old_words["durationSeconds"], new_words["durationSeconds"])
    print(f"   {len(points) - 2} anclas de {len(old_s)} frases")

    print("[3/6] Reajustando cortes, paneles y rótulos")
    timeline = retime(old_timeline, time_map(points), new_words["durationSeconds"], MAX_THIRD_PARTY_SECONDS)
    timeline["slug"] = ctx.slug
    question_words(timeline, new_words["words"])
    timeline["audio"]["speech"] = speech_spans(new_words["words"], timeline["fps"], timeline["audio"].get("voiceFrom", 0),
                                               pauses=timeline["audio"].get("voiceGaps", []))
    timeline["locale"] = {"chapter": chapter_word, "source": source_word}

    print("[4/6] Material: reutilizando clips (cámara lenta donde el plano es más largo)")
    for folder in LINKED:
        if (original.work_dir / folder).is_dir():
            _link_tree(original.work_dir / folder, ctx.work_dir / folder)
    for name in COPIED:   # paths inside point at work/<original>/: make them point at this copy
        if (original.work_dir / name).is_file():
            text = (original.work_dir / name).read_text("utf-8")
            for sep in ("/", "\\\\"):
                text = text.replace(f"work{sep}{original.slug}{sep}", f"work{sep}{ctx.slug}{sep}")
            (ctx.work_dir / name).write_text(text, encoding="utf-8")
    voice = ctx.work_dir / "audio" / "voz.mp3"
    voice.unlink(missing_ok=True)          # a hard link to the original voice: never write through it
    shutil.copy2(ctx.materials_dir / "voz.mp3", voice)
    slowed = 0
    for shot in timeline["shots"]:
        media = shot.get("media") or {}
        if media.get("kind") != "video":
            continue
        seconds = shot["durationInFrames"] / timeline["fps"]
        source = ctx.work_dir / media["src"]
        if seconds > _seconds(source) + 0.05:
            target = Path("media_dub") / f"{shot['id']}-{shot['durationInFrames']}.mp4"
            if not (ctx.work_dir / target).is_file():
                slow_motion(source, ctx.work_dir / target, seconds)
            media["src"] = target.as_posix()
            slowed += 1
    print(f"   {slowed} planos en cámara lenta")

    print(f"[5/6] Traduciendo textos en pantalla al {language}")
    texts = screen_texts(timeline)
    translated = complete_json(ctx, stage=STAGE, section="planner", max_tokens=6000,
                               system=TRANSLATE_SYSTEM.format(language=language),
                               user=json.dumps(texts, ensure_ascii=False)).get("texts", {})
    apply_texts(timeline, {k: str(v) for k, v in translated.items() if k in texts and str(v).strip()})
    if not (ctx.materials_dir / "titulo.txt").is_file():
        (ctx.materials_dir / "titulo.txt").write_text(timeline["title"] + "\n", encoding="utf-8")
    Timeline.model_validate(timeline)
    ctx.write_json("timeline.json", timeline)

    print("[6/6] QA, render, Shorts y miniaturas")
    from . import package, qa, render, shorts

    for stage in (qa, render, shorts, package):
        print(f"   · {stage.__name__.rsplit('.', 1)[-1]}")
        stage.run(ctx)
