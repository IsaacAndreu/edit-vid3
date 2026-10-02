"""Stage 10 — render out/<slug>/video-final.mp4 from work/<slug>/timeline.json.

Chrome (Remotion) costs ~150 ms per 1080p frame on a small machine, but most shots are
plain footage with a static credit badge, which ffmpeg can compose far faster. So the render
is hybrid, with the same pixels:

- "fast" shots (video b-roll, no panel/stat/chapter on top) → ffmpeg: the normalised clip
  (already 1920x1080, 30 fps) + the credit badge, drawn once per credit by Remotion as a
  transparent PNG (composition "Badges");
- every other shot (panels, stats, chapters, stills with Ken Burns, split screens) → one
  Remotion pass over a condensed timeline that contains only those shots, back to back;
- audio → ffmpeg: narration + optional music ducked under the voice + optional SFX, mastered
  to -16 LUFS with two-pass loudnorm (the same mix AudioBed plays in Remotion Studio);
- all segments share the same x264 settings and are joined without re-encoding.

Segments are cached by content, so a re-render after a small change only redoes what changed.
`render.hybrid: false` renders the whole timeline with Remotion instead (slow, reference).
"""

from __future__ import annotations

import glob
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .context import RunContext
from .encoder import use_nvenc, video_args
from .postflight import enforce_postflight, inspect_render, write_postflight_report
from .schemas import Timeline


STAGE = "render"
OUTPUT = "video-final.mp4"
VERSION = 1
RAMP_FRAMES = 8          # music fade around speech, as in remotion/components/AudioBed.tsx
MUSIC_LUFS = -20         # the bed before music_volume / ducking (the voice is ~-23 LUFS before mastering)
SFX_FRAMES = 90          # each SFX plays at most 3 s, as in AudioBed


@dataclass
class Segment:
    kind: str                         # "ffmpeg" (one fast shot) or "remotion" (a run of slow shots)
    start: int                        # frame in the final video
    frames: int
    shots: list[dict[str, Any]] = field(default_factory=list)
    condensed_start: int = 0          # where the run begins in the condensed Remotion render
    offset: int = 0                   # ffmpeg: frames of the shot before this piece (a shot split around a label)


# CSS sepia(0.22) as a colour matrix, as in remotion/components/ArchiveFootage.tsx
SEPIA = "colorchannelmixer=rr=0.866:rg=0.169:rb=0.042:gr=0.077:gg=0.931:gb=0.037:br=0.060:bg=0.117:bb=0.809"


def zoom_filter(zoom: list[float] | None, width: int, height: int, fps: int) -> str:
    """Scale up around the centre from frame zoom[0], over zoom[1] frames, to zoom[2] (ease-out, then hold)."""

    if not zoom:
        return ""
    start, frames, scale = float(zoom[0]), max(1.0, float(zoom[1])), float(zoom[2])
    z = f"(1+{scale - 1:.4f}*(1-pow(1-clip((t*{fps}-{start:.1f})/{frames:.1f},0,1),3)))"
    return (f",scale=w='2*trunc({width}*{z}/2)':h='2*trunc({height}*{z}/2)':eval=frame:flags=bicubic,"
            f"crop={width}:{height}:(iw-{width})/2:(ih-{height})/2")


def shot_filter(media: dict[str, Any], frames: int, fps: int) -> str:
    """ffmpeg chain for one fast shot: speed, zoom and, for archive footage, the film look between black bars."""

    rate = float(media.get("rate") or 1.0)
    chain = "setpts=PTS-STARTPTS" + (f",setpts=PTS/{rate:.4f},fps={fps}" if rate < 0.999 else "")
    width, height = int(media.get("width") or 1920), int(media.get("height") or 1080)
    chain += zoom_filter(media.get("zoom"), width, height, fps)
    if media.get("layout") == "archive":
        chain += (f",eq=contrast=1.06:saturation=0.88:brightness=-0.02,{SEPIA},noise=alls=12:allf=t,"
                  f"vignette=angle=PI/5,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black")
    return chain + f",tpad=stop_mode=clone:stop={frames}"


MIN_FAST = 15             # a stretch of plain footage shorter than this stays in Remotion (not worth a segment)


def _covered(a: int, b: int, overlays: list[dict[str, Any]]) -> list[tuple[int, int]]:
    """Frames of [a, b) with something drawn over or moving the footage, merged into ranges."""

    spans = sorted((max(a, o["from"]), min(b, o["from"] + o["durationInFrames"])) for o in overlays
                   if o["from"] < b and a < o["from"] + o["durationInFrames"])
    merged: list[list[int]] = []
    for x, y in spans:
        if merged and x <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], y)
        else:
            merged.append([x, y])
    return [(x, y) for x, y in merged]


def shot_pieces(shot: dict[str, Any], overlays: list[dict[str, Any]], hybrid: bool = True) -> list[tuple[str, int, int]]:
    """(kind, start, end) of a shot: plain footage goes to ffmpeg; only the frames with a label, transition,
    shake or graphic over them (or a shot that is not plain footage at all) go to Remotion."""

    a, b = shot["from"], shot["from"] + shot["durationInFrames"]
    media = shot.get("media") or {}
    plain = (shot["type"] == "broll" and media.get("kind") == "video" and media.get("layout", "full") in ("full", "archive")
             and not shot.get("groupId"))
    card = (shot["type"] == "broll" and media.get("kind") in ("video", "image") and media.get("layout") == "card"
            and not shot.get("groupId"))
    if hybrid and card:            # a framed card is composed by ffmpeg too, but only whole (its pop-in and push)
        return [("remotion" if _covered(a, b, overlays) else "ffmpeg", a, b)]
    if not hybrid or not plain:
        return [("remotion", a, b)]
    pieces: list[tuple[str, int, int]] = []
    cursor = a
    for x, y in [*_covered(a, b, overlays), (b, b)]:
        if x > cursor:
            pieces.append(("ffmpeg" if x - cursor >= MIN_FAST else "remotion", cursor, x))
        if y > x:
            pieces.append(("remotion", x, y))
        cursor = max(cursor, y)
    out: list[tuple[str, int, int]] = []
    for kind, x, y in pieces:                     # neighbouring Remotion bits become one
        if out and out[-1][0] == kind == "remotion" and out[-1][2] == x:
            out[-1] = (kind, out[-1][1], y)
        else:
            out.append((kind, x, y))
    return out


def is_fast(shot: dict[str, Any], groups: list[dict[str, Any]] = ()) -> bool:
    """The whole shot goes to ffmpeg."""

    return [p[0] for p in shot_pieces(shot, list(groups))] == ["ffmpeg"]


CARD_MAX = (1480, 830)     # as remotion/components/FramedCard.tsx
CARD_MARGIN = 200          # room around the card for its shadow (0 30px 90px)


def card_box(media: dict[str, Any]) -> tuple[int, int]:
    """Inner size of a framed card (FramedCard.tsx): the source's aspect inside 1480x830."""

    w, h = media.get("width"), media.get("height")
    aspect = w / h if w and h else 16 / 9
    if aspect >= CARD_MAX[0] / CARD_MAX[1]:
        return CARD_MAX[0], round(CARD_MAX[0] / aspect)
    return round(CARD_MAX[1] * aspect), CARD_MAX[1]


def card_graph(media: dict[str, Any], frames: int, fps: int, badge: bool) -> str:
    """ffmpeg graph for a framed card: [0] the clip or photo, [1] the card's border and shadow (PNG), [2] the
    channel background, [3] the credit badge. Pops in (8 frames) and pushes in to 1.035 over the shot."""

    w, h = card_box(media)
    w, h = w - 10, h - 10                               # border-box: the 5 px border is inside the card's size
    sw, sh = w, h                                       # object-fit: cover of the source into the card
    if media.get("width") and media.get("height"):
        k = max(w / media["width"], h / media["height"])
        sw, sh = max(w, math.ceil(media["width"] * k)), max(h, math.ceil(media["height"] * k))
    rate = float(media.get("rate") or 1.0)
    src = "setpts=PTS-STARTPTS" + (f",setpts=PTS/{rate:.4f},fps={fps}" if rate < 0.999 else "")
    aw, ah = w + 10 + 2 * CARD_MARGIN, h + 10 + 2 * CARD_MARGIN
    e = "(1-pow(1-min(1,n/8),3))"
    scale = f"((0.94+0.06*{e})*(1+0.035*n/{max(1, frames)}))"
    graph = (f"[0:v]{src},scale={sw}:{sh}:flags=bicubic,crop={w}:{h},setsar=1,format=rgba,"
             f"tpad=stop_mode=clone:stop={frames}[v];"
             f"[1:v]format=rgba[f];[f][v]overlay={CARD_MARGIN + 5}:{CARD_MARGIN + 5}:format=auto[c];"
             f"[c]scale=w='2*trunc({aw}*{scale}/2)':h='2*trunc({ah}*{scale}/2)':eval=frame:flags=bicubic,"
             f"fade=t=in:s=0:n=6:alpha=1[cs];"
             f"[2:v][cs]overlay=x='960-overlay_w/2':y='528-overlay_h/2':eval=frame:format=auto")
    graph += "[o];[o][3:v]overlay=0:0:format=auto,format=yuv420p[v2]" if badge else ",format=yuv420p[v2]"
    return graph


def plan_segments(timeline: dict[str, Any], hybrid: bool = True) -> list[Segment]:
    segments: list[Segment] = []
    condensed = 0
    overlays = [*timeline.get("groups", []), *timeline.get("labels", []),   # anything drawn over the footage
                *timeline.get("transitions", []), *timeline.get("shakes", [])]  # or moving it (zoom / whip / shake)
    for shot in timeline["shots"]:
        if hybrid and shot["type"] == "endscreen" and not _covered(shot["from"], shot["from"] + shot["durationInFrames"], overlays):
            # the same in every video of the channel: rendered once and cached (Renderer.endscreen)
            segments.append(Segment("endscreen", shot["from"], shot["durationInFrames"], [shot]))
            continue
        vertical_card = timeline.get("height", 0) > timeline.get("width", 1) and (shot.get("media") or {}).get("layout") == "card"
        pieces = ([("remotion", shot["from"], shot["from"] + shot["durationInFrames"])] if vertical_card   # drawn as
                  else shot_pieces(shot, overlays, hybrid))                                                 # plain b-roll
        for kind, x, y in pieces:
            offset = x - shot["from"]
            if kind == "ffmpeg":
                segments.append(Segment("ffmpeg", x, y - x, [shot], offset=offset))
                continue
            # a piece of a longer shot: Remotion draws only its frames, starting `offset` frames into the shot
            piece = shot if len(pieces) == 1 else {**shot, "id": f"{shot['id']}~{offset}", "from": x,
                                                   "durationInFrames": y - x, "offset": offset,
                                                   "fullDuration": shot["durationInFrames"]}
            if segments and segments[-1].kind == "remotion":
                segments[-1].shots.append(piece)
                segments[-1].frames += y - x
            else:
                segments.append(Segment("remotion", x, y - x, [piece], condensed))
            condensed += y - x
    return segments


def condensed_props(timeline: dict[str, Any], segments: list[Segment]) -> dict[str, Any]:
    """The slow shots back to back; groups keep their shape, shifted with their shots."""

    shift: dict[str, int] = {}
    shots = []
    for segment in segments:
        if segment.kind != "remotion":
            continue
        offset = segment.start - segment.condensed_start
        for shot in segment.shots:
            shift[shot["id"]] = offset
            shots.append({**shot, "from": shot["from"] - offset})
    def shifted(items: list[dict[str, Any]], what: str) -> list[dict[str, Any]]:
        # An overlay lies inside one run of slow shots (every shot it touches is slow): shift it with them.
        out = []
        for item in items:
            owner = next((s for s in shots if s["from"] + shift[s["id"]] <= item["from"]
                          < s["from"] + shift[s["id"]] + s["durationInFrames"]), None)
            if owner is None:
                raise RuntimeError(f"{what} en el fotograma {item['from']} no cae en un tramo de Remotion")
            out.append({**item, "from": item["from"] - shift[owner["id"]]})
        return out

    groups = shifted(timeline["groups"], "Un grupo")
    labels = shifted(timeline.get("labels", []), "Un rótulo")
    transitions = shifted(timeline.get("transitions", []), "Una transición")
    shakes = shifted(timeline.get("shakes", []), "Un temblor")
    total = sum(s["durationInFrames"] for s in shots)
    audio = {**timeline["audio"], "music": None, "speech": [], "sfx": [], "clips": [], "voiceFrom": 0}
    return {**timeline, "durationInFrames": total, "shots": shots, "groups": groups, "labels": labels,
            "transitions": transitions, "shakes": shakes, "audio": audio}


def media_seconds(path: Path) -> float:
    result = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                            capture_output=True, text=True)
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def graphic_media(graphic: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Photos/clips a graphic shows (rank, specs, both sides of a comparison, a spotlight's frames…)."""

    found: list[dict[str, Any]] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            if value.get("src") and value.get("kind") in ("image", "video"):
                found.append(value)
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(graphic or {})
    return found


def voice_chains(index: int, voice_from: int, gaps: list, fps: int, stereo: str) -> list[str]:
    """The narration, delayed by the cold open and split at each moment so it pauses there."""

    delay = round(voice_from / fps * 1000)
    if not gaps:
        return [f"[{index}:a]{stereo}" + (f",adelay={delay}:all=1" if delay else "") + "[voice]"]
    cuts = [0, *[at for at, _ in gaps]]
    chains = [f"[{index}:a]{stereo},asplit={len(cuts)}" + "".join(f"[vs{k}]" for k in range(len(cuts)))]
    shift = 0
    for k, start in enumerate(cuts):
        if k:
            shift += gaps[k - 1][1]
        end = f":end={cuts[k + 1] / fps:.4f}" if k + 1 < len(cuts) else ""
        ms = round((voice_from + start + shift) / fps * 1000)
        chains.append(f"[vs{k}]atrim=start={start / fps:.4f}{end},asetpts=PTS-STARTPTS"
                      + (f",adelay={ms}:all=1" if ms else "") + f"[vp{k}]")
    chains.append("".join(f"[vp{k}]" for k in range(len(cuts))) + f"amix=inputs={len(cuts)}:normalize=0,asetpts=N/SR/TB[voice]")   # continuous timestamps, or apad never ends
    return chains


def music_volume_expr(speech: list[list[int]] | list[tuple[int, int]], fps: int, total: int,
                      music: float, ducked: float) -> str:
    """ffmpeg `volume` expression (t in seconds) for AudioBed's ducking curve."""

    ramp = RAMP_FRAMES / fps
    gaps, cursor = [], 0
    for a, b in speech:
        if a > cursor:
            gaps.append((cursor, a, cursor > 0))
        cursor = max(cursor, b)
    if cursor < total:
        gaps.append((cursor, total, True))
    if not speech:
        return f"{music:.5f}"
    terms = [f"{ducked:.5f}"]
    for a, b, after_speech in gaps:
        t0, t1 = a / fps, b / fps
        near = [f"(t-{t0:.4f})"] if after_speech else []
        if b < total:
            near.append(f"({t1:.4f}-t)")
        dist = near[0] if len(near) == 1 else f"min({near[0]},{near[1]})"
        level = f"min(1,{dist}/{ramp:.4f})" if near else "1"
        terms.append(f"{music - ducked:.5f}*between(t,{t0:.4f},{t1:.4f})*{level}")
    return "+".join(terms)


def _hash(*parts: Any) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(json.dumps(part, sort_keys=True, default=str).encode())
    return digest.hexdigest()[:16]


def _file_sig(path: Path) -> list:
    stat = path.stat()
    return [path.name, stat.st_size, int(stat.st_mtime)]


def _run(cmd: list[str], what: str) -> subprocess.CompletedProcess:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip()[-1500:]
        raise RuntimeError(f"Falló {what}:\n{tail}")
    return result


def ensure_node_modules(root: Path) -> None:
    """`npm install` when package.json lists a package node_modules lacks (new fonts after a git pull)."""

    try:
        manifest = json.loads((root / "package.json").read_text("utf-8"))
    except (OSError, ValueError):
        return
    wanted = {**manifest.get("dependencies", {}), **manifest.get("devDependencies", {})}
    missing = [name for name in wanted if not (root / "node_modules" / name / "package.json").is_file()]
    if not missing:
        return
    print(f"   Instalando paquetes de Node que faltan ({', '.join(missing[:4])}…): npm install")
    npm = shutil.which("npm") or "npm"
    result = subprocess.run([npm, "install", "--no-audit", "--no-fund"], cwd=str(root), capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Falló npm install (ejecútalo a mano):\n{(result.stderr or result.stdout)[-800:]}")


def _browser(cfg: dict[str, Any]) -> str | None:
    value = str(cfg.get("browser_executable", "auto") or "auto")
    if value != "auto":
        return value
    found = sorted(glob.glob("/opt/pw-browsers/chromium_headless_shell-*/chrome-linux/headless_shell"))
    return found[-1] if found else None


class Renderer:
    def __init__(self, ctx: RunContext) -> None:
        self.ctx = ctx
        self.cfg = ctx.section("render")
        self.fps = ctx.fps
        self.dir = ctx.work_dir / "render"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.set_encoder(use_nvenc(self.cfg))

    def set_encoder(self, nvenc: bool) -> None:
        """Every segment with the same settings (they are joined without re-encoding): the graphics card's
        encoder when it works (render.encoder: auto), else x264."""

        self.nvenc = nvenc
        self.encode = [
            *video_args(self.cfg, self.cfg.get("crf", 18), str(self.cfg.get("preset", "veryfast")), nvenc=nvenc),
            "-r", str(self.fps), "-g", str(self.fps * 2), "-video_track_timescale", str(self.fps * 512), "-an",
        ]
        self.enc_key = _hash(self.encode, VERSION)

    # --- Remotion -------------------------------------------------------------------------

    def remotion(self, composition: str, props: dict[str, Any], output: Path, extra: list[str], public: set[str]) -> None:
        """Bundle a slim public dir (hard links to just the files used) and render once."""

        public_dir = self.dir / "public"
        bundle_dir = self.dir / "bundle"
        shutil.rmtree(public_dir, ignore_errors=True)
        shutil.rmtree(bundle_dir, ignore_errors=True)
        for rel in public:
            source, target = self.ctx.work_dir / rel, public_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.link(source, target)
            except OSError:
                shutil.copy2(source, target)
        props_file = self.dir / f"{composition}.props.json"
        props_file.write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")
        npx = shutil.which("npx") or "npx"
        root = str(self.ctx.root)
        ensure_node_modules(self.ctx.root)
        try:
            subprocess.run([npx, "remotion", "bundle", "remotion/index.ts", f"--public-dir={public_dir}",
                            f"--out-dir={bundle_dir}", "--log=error"], cwd=root, check=True, capture_output=True, text=True)
            cmd = [npx, "remotion", "render", str(bundle_dir), composition, str(output), f"--props={props_file}",
                   "--log=error", *extra]
            browser = _browser(self.cfg)
            if browser:
                cmd.append(f"--browser-executable={browser}")
            result = subprocess.run(cmd, cwd=root, capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(f"Falló el render de Remotion ({composition}):\n{(result.stderr or result.stdout)[-1500:]}")
        except subprocess.CalledProcessError as error:
            raise RuntimeError(f"Falló el bundle de Remotion:\n{(error.stderr or error.stdout or '')[-1500:]}") from error
        finally:
            shutil.rmtree(bundle_dir, ignore_errors=True)
            shutil.rmtree(public_dir, ignore_errors=True)

    def concurrency(self) -> str:
        value = int(self.cfg.get("concurrency", 0) or 0)
        return str(value if value > 0 else (os.cpu_count() or 2))

    def badges(self, credits: list[str]) -> dict[str, Path]:
        """One transparent 1920x1080 PNG per distinct credit text, cached by text."""

        folder = self.ctx.cache_dir / "render" / "badges" / _hash(sorted(self._remotion_sig()), self.ctx.section("brand"))
        paths = {c: folder / f"{_hash(c)}.png" for c in credits}
        missing = [c for c in credits if not paths[c].is_file()]
        if missing:
            folder.mkdir(parents=True, exist_ok=True)
            tmp = self.dir / "badges"
            shutil.rmtree(tmp, ignore_errors=True)
            self.remotion("Badges", {"credits": missing, "brand": self.ctx.section("brand")}, tmp,
                          ["--sequence", "--image-format=png", f"--concurrency={self.concurrency()}"], set())
            frames = sorted(tmp.iterdir(), key=lambda p: int(re.findall(r"\d+", p.stem)[-1]))
            if len(frames) != len(missing):
                raise RuntimeError(f"Remotion devolvió {len(frames)} créditos, se esperaban {len(missing)}")
            for credit, frame in zip(missing, frames):
                shutil.move(str(frame), paths[credit])
            shutil.rmtree(tmp, ignore_errors=True)
        return paths

    def backdrop(self) -> Path:
        """The channel background (GridBackground) as a PNG, cached by brand and Remotion code."""

        path = self.ctx.cache_dir / "render" / "backdrop" / f"{_hash(self._remotion_sig(), self.ctx.section('brand'))}.png"
        if not path.is_file():
            tmp = self.dir / "backdrop"
            shutil.rmtree(tmp, ignore_errors=True)
            self.remotion("Backdrop", {"brand": self.ctx.section("brand")}, tmp,
                          ["--sequence", "--image-format=png"], set())
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(next(tmp.iterdir())), path)
            shutil.rmtree(tmp, ignore_errors=True)
        return path

    def card_frame(self, w: int, h: int) -> Path:
        """Transparent PNG of a card's white border and soft shadow (FramedCard.tsx), with a hole for the footage."""

        path = self.ctx.cache_dir / "render" / "cards" / f"{w}x{h}-v2.png"
        if path.is_file():
            return path
        from PIL import Image, ImageDraw, ImageFilter

        m = CARD_MARGIN
        size = (w + 10 + 2 * m, h + 10 + 2 * m)
        shadow = Image.new("L", size, 0)
        ImageDraw.Draw(shadow).rectangle([m, m + 30, m + w + 9, m + h + 39], fill=round(0.75 * 255))
        shadow = shadow.filter(ImageFilter.GaussianBlur(45))
        box = Image.new("L", size, 0)
        ImageDraw.Draw(box).rectangle([m, m, m + w + 9, m + h + 9], fill=255)
        alpha = Image.composite(Image.new("L", size, 0), shadow, box)      # no shadow under the card itself
        ImageDraw.Draw(alpha).rectangle([m, m, m + w + 9, m + h + 9], fill=round(0.92 * 255))
        ImageDraw.Draw(alpha).rectangle([m + 5, m + 5, m + w + 4, m + h + 4], fill=0)
        colour = Image.new("RGB", size, (0, 0, 0))
        ImageDraw.Draw(colour).rectangle([m, m, m + w + 9, m + h + 9], fill=(255, 255, 255))
        colour.putalpha(alpha)
        path.parent.mkdir(parents=True, exist_ok=True)
        colour.save(path)
        return path

    def card_segment(self, segment: Segment, badge: Path | None) -> Path:
        shot = segment.shots[0]
        media = shot["media"]
        source = self.ctx.work_dir / media["src"]
        w, h = card_box(media)
        frame, back = self.card_frame(w - 10, h - 10), self.backdrop()
        graph = card_graph(media, segment.frames, self.fps, badge is not None)
        key = _hash(self.enc_key, _file_sig(source), _file_sig(frame), _file_sig(back),
                    _file_sig(badge) if badge else None, graph)
        out = self.dir / "segments" / f"{shot['id']}-card-{key}.mp4"
        if out.is_file():
            return out
        out.parent.mkdir(parents=True, exist_ok=True)
        still = ["-loop", "1", "-framerate", str(self.fps)]
        inputs = [*(still if media["kind"] == "image" else []), "-i", str(source), *still, "-i", str(frame),
                  *still, "-i", str(back), *([*still, "-i", str(badge)] if badge else [])]
        tmp = out.with_suffix(".tmp.mp4")
        _run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", graph, "-map", "[v2]",
              "-frames:v", str(segment.frames), *self.encode, str(tmp)], f"la tarjeta {shot['id']}")
        tmp.replace(out)
        return out

    def endscreen(self, timeline: dict[str, Any], segment: Segment) -> Path:
        """The end screen as a finished segment, cached across videos (same brand, words, length and code)."""

        props = {**{k: timeline[k] for k in ("fps", "width", "height") if k in timeline},
                 "slug": "endscreen", "title": "", "durationInFrames": segment.frames,
                 "shots": [{**segment.shots[0], "from": 0, "text": ""}], "groups": [], "labels": [], "transitions": [],
                 "shakes": [], "captions": [], "brand": timeline.get("brand"), "locale": timeline.get("locale"),
                 "audio": {"voice": timeline["audio"]["voice"], "musicVolume": 0, "duckedVolume": 0, "speech": [],
                           "sfx": [], "clips": [], "music": None, "voiceFrom": 0}}
        key = _hash(VERSION, props, self._remotion_sig(), self.enc_key)
        out = self.ctx.cache_dir / "render" / "endscreen" / f"{key}.mp4"
        if not out.is_file():
            raw = self.dir / "endscreen.tmp.mp4"
            self.remotion("Documentary", props, raw, ["--muted", f"--concurrency={self.concurrency()}", "--codec=h264",
                                                      "--crf=12", f"--x264-preset={self.cfg.get('preset', 'veryfast')}"],
                          {props["audio"]["voice"]})
            out.parent.mkdir(parents=True, exist_ok=True)
            tmp = out.with_suffix(".tmp.mp4")
            _run(["ffmpeg", "-y", "-v", "error", "-i", str(raw), "-frames:v", str(segment.frames), *self.encode, str(tmp)],
                 "la pantalla final")
            tmp.replace(out)
            raw.unlink(missing_ok=True)
        return out

    def _remotion_sig(self) -> list:
        files = sorted(p for p in (self.ctx.root / "remotion").rglob("*") if p.is_file())
        return [[str(p.relative_to(self.ctx.root)), hashlib.sha256(p.read_bytes()).hexdigest()[:12]] for p in files]

    # --- ffmpeg segments ------------------------------------------------------------------

    def fast_segment(self, segment: Segment, badge: Path | None) -> Path:
        shot = segment.shots[0]
        clip = self.ctx.work_dir / shot["media"]["src"]
        pad = shot_filter(shot["media"], segment.offset + segment.frames, self.fps)
        if segment.offset:     # a later piece of a split shot: the same chain (speed, zoom…), from that frame
            pad += f",trim=start_frame={segment.offset},setpts=PTS-STARTPTS"
        key = _hash(self.enc_key, _file_sig(clip), segment.frames, _file_sig(badge) if badge else None, pad)
        out = self.dir / "segments" / f"{shot['id']}-{segment.offset}-{key}.mp4"
        if out.is_file():
            return out
        out.parent.mkdir(parents=True, exist_ok=True)
        if badge:
            graph = f"[0:v]{pad}[b];[b][1:v]overlay=0:0:format=auto,format=yuv420p[v]"
            inputs = ["-i", str(clip), "-loop", "1", "-framerate", str(self.fps), "-i", str(badge)]
        else:
            graph = f"[0:v]{pad},format=yuv420p[v]"
            inputs = ["-i", str(clip)]
        tmp = out.with_suffix(".tmp.mp4")
        _run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", graph, "-map", "[v]",
              "-frames:v", str(segment.frames), *self.encode, str(tmp)], f"el segmento {shot['id']}")
        tmp.replace(out)
        return out

    def cut_segment(self, segment: Segment, condensed: Path, key: str) -> Path:
        out = self.dir / "segments" / f"r{segment.start:06d}-{key}.mp4"
        if out.is_file():
            return out
        out.parent.mkdir(parents=True, exist_ok=True)
        a, b = segment.condensed_start, segment.condensed_start + segment.frames
        seek = max(0.0, (a - self.fps) / self.fps)
        trim = f"trim=start={(a - 0.5) / self.fps:.5f}:end={(b - 0.5) / self.fps:.5f},setpts=PTS-STARTPTS"
        tmp = out.with_suffix(".tmp.mp4")
        _run(["ffmpeg", "-y", "-v", "error", "-copyts", "-ss", f"{seek:.5f}", "-i", str(condensed), "-vf", trim,
              "-frames:v", str(segment.frames), *self.encode, str(tmp)], f"el tramo {segment.start}")
        tmp.replace(out)
        return out

    # --- audio ------------------------------------------------------------------------------

    def chapter_bed(self, parts: list[dict[str, Any]], seconds: float) -> Path:
        """One bed from the chapter parts: each track looped to its part, cross-faded into the next
        (the fade ends where the next chapter starts)."""

        fade = float(self.cfg.get("music_crossfade", 4.0))
        beds, lengths = [], []
        for i, part in enumerate(parts):
            length = part["durationInFrames"] / self.fps + (fade if i + 1 < len(parts) else 0.0)
            if i + 1 == len(parts):
                length = max(length, seconds - part["from"] / self.fps)
            beds.append(self.music_bed(self.ctx.work_dir / part["src"], length))
            lengths.append(length)
        out = self.dir / f"music-parts-{_hash([_file_sig(b) for b in beds], lengths, fade)}.wav"
        if out.is_file():
            return out
        chain = ";".join(f"[{i}:a]atrim=end={length:.3f},asetpts=PTS-STARTPTS[p{i}]" for i, length in enumerate(lengths))
        chain += ";[p0]anull[x0]" + "".join(
            f";[x{i - 1}][p{i}]acrossfade=d={fade}:c1=tri:c2=tri[x{i}]" for i in range(1, len(beds)))
        _run(["ffmpeg", "-y", "-v", "error", *[a for b in beds for a in ("-i", str(b))], "-filter_complex", chain,
              "-map", f"[x{len(beds) - 1}]", "-ar", "48000", "-ac", "2", str(out)], "la música por capítulos")
        return out

    def music_bed(self, track: Path, seconds: float) -> Path:
        """The track levelled to MUSIC_LUFS (any track sits the same under the voice) and repeated
        until the video ends, each repetition cross-faded into the next."""

        fade = float(self.cfg.get("music_crossfade", 4.0))
        length = media_seconds(track)
        copies = 1 if length <= 0 or length >= seconds else max(1, math.ceil((seconds - fade) / max(1.0, length - fade)) + 1)
        out = self.dir / f"music-{_hash(_file_sig(track), copies, fade, MUSIC_LUFS)}.wav"
        if out.is_file():
            return out
        chain = "[0:a]anull[m0]" + "".join(
            f";[m{i - 1}][{i}:a]acrossfade=d={fade}:c1=tri:c2=tri[m{i}]" for i in range(1, copies))
        chain += f";[m{copies - 1}]loudnorm=I={MUSIC_LUFS}:TP=-2:LRA=11[bed]"
        _run(["ffmpeg", "-y", "-v", "error", *[a for _ in range(copies) for a in ("-i", str(track))],
              "-filter_complex", chain, "-map", "[bed]", "-ar", "48000", "-ac", "2", str(out)],
             "el bucle de la música")
        return out

    def audio(self, timeline: dict[str, Any]) -> Path:
        audio = timeline["audio"]
        total = timeline["durationInFrames"]
        seconds = total / self.fps
        work = self.ctx.work_dir
        inputs: list[str] = []
        files: list[Path] = []

        def add(path: Path, *pre: str) -> int:
            inputs.extend([*pre, "-i", str(path)])
            files.append(path)
            return len(files) - 1

        stereo = "aresample=48000,aformat=channel_layouts=stereo"
        chains = voice_chains(add(work / audio["voice"]), audio.get("voiceFrom", 0), audio.get("voiceGaps", []),
                              self.fps, stereo)
        mix = ["[voice]"]
        if audio.get("music"):
            parts = audio.get("musicParts") or []
            index = add(self.chapter_bed(parts, seconds) if len(parts) > 1 else
                        self.music_bed(work / (parts[0]["src"] if parts else audio["music"]), seconds))
            # ducked under the voice AND under the original sound of the cold open / moments
            busy = sorted([*[tuple(s) for s in audio.get("speech", [])],
                           *[(c["from"], c["from"] + c["durationInFrames"]) for c in audio.get("clips", [])]])
            expr = music_volume_expr(busy, self.fps, total, audio["musicVolume"], audio["duckedVolume"])
            fade = min(3.0, seconds / 4)          # the music fades out with the end screen
            chains.append(f"[{index}:a]{stereo},atrim=end={seconds:.4f},volume=eval=frame:volume='{expr}',"
                          f"afade=t=out:st={seconds - fade:.3f}:d={fade:.3f}[music]")
            mix.append("[music]")
        # Original sound of the cold-open clips (the only clip audio ever used), then SFX.
        for n, clip in enumerate(audio.get("clips", [])):
            index = add(work / clip["src"])
            delay = round(clip["from"] / self.fps * 1000)
            length = clip["durationInFrames"] / self.fps
            fades = (f"afade=t=in:d={min(0.12, length / 4):.3f},afade=t=out:st={max(0.0, length - 0.3):.3f}:d={min(0.3, length / 2):.3f},"
                     if clip.get("fade") else "")                     # sound bites: no clicks at the edges
            chains.append(f"[{index}:a]{stereo},atrim=end={length:.3f},{fades}"
                          f"volume={clip.get('volume', 1.0)},adelay={delay}:all=1[c{n}]")
            mix.append(f"[c{n}]")
        for n, sfx in enumerate(audio.get("sfx", [])):
            index = add(work / sfx["src"])
            delay = round(sfx["from"] / self.fps * 1000)
            chains.append(f"[{index}:a]{stereo},atrim=end={SFX_FRAMES / self.fps:.3f},"
                          f"volume={sfx['volume']},adelay={delay}:all=1[s{n}]")
            mix.append(f"[s{n}]")
        mixed = (f"{''.join(mix)}amix=inputs={len(mix)}:duration=longest:normalize=0," if len(mix) > 1 else f"{mix[0]}anull,")
        base = ";".join(chains) + f";{mixed}apad,atrim=end={seconds:.4f}"
        target, peak = float(self.cfg.get("loudness", -16)), float(self.cfg.get("true_peak", -1.5))
        key = _hash(VERSION, base, [_file_sig(f) for f in files], target, peak)
        out = self.dir / f"audio-{key}.wav"
        if out.is_file():
            return out
        measure = _run(["ffmpeg", "-hide_banner", "-nostats", *inputs, "-filter_complex",
                        f"{base},loudnorm=I={target}:TP={peak}:LRA=11:print_format=json", "-f", "null", "-"],
                       "la medición de sonoridad")
        stats = json.loads(re.findall(r"\{[^{}]*\"input_i\"[^{}]*\}", measure.stderr)[-1])
        norm = (f"loudnorm=I={target}:TP={peak}:LRA=11:measured_I={stats['input_i']}:measured_TP={stats['input_tp']}:"
                f"measured_LRA={stats['input_lra']}:measured_thresh={stats['input_thresh']}:offset={stats['target_offset']}:"
                f"linear=true")
        tmp = out.with_suffix(".tmp.wav")
        _run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", f"{base},{norm},aresample=48000",
              "-c:a", "pcm_s16le", str(tmp)], "la mezcla de audio")
        tmp.replace(out)
        print(f"   Audio: {stats['input_i']} LUFS → {target} LUFS (pico {peak} dBTP)")
        return out


def inputs(ctx: RunContext) -> list:
    return [ctx.work_dir / "timeline.json", ctx.root / "remotion", ctx.root / "pipeline" / "render.py"]


def run(ctx: RunContext) -> None:
    started = time.monotonic()
    timeline = ctx.read_json("timeline.json")
    Timeline.model_validate(timeline)
    r = Renderer(ctx)
    hybrid = bool(r.cfg.get("hybrid", True))
    segments = plan_segments(timeline, hybrid)
    fast = [s for s in segments if s.kind == "ffmpeg"]
    slow = [s for s in segments if s.kind == "remotion"]
    fast_frames, slow_frames = sum(s.frames for s in fast), sum(s.frames for s in slow)
    print(f"   {len(timeline['shots'])} planos · ffmpeg {fast_frames} fotogramas ({len(fast)} planos) · "
          f"Remotion {slow_frames} fotogramas ({len(slow)} tramos)"
          + (" · pantalla final aparte (en caché)" if any(s.kind == "endscreen" for s in segments) else ""))

    # 1. Remotion: the condensed timeline of slow shots, one pass.
    condensed_path = None
    if slow:
        props = condensed_props(timeline, segments)
        key = _hash(VERSION, props, r._remotion_sig(),
                    sorted(_file_sig(ctx.work_dir / s["media"]["src"]) for s in props["shots"] if s.get("media")))
        condensed_path = r.dir / f"remotion-{key}.mp4"
        if not condensed_path.is_file():
            t = time.monotonic()
            public = {s["media"]["src"] for s in props["shots"] if s.get("media")} | {props["audio"]["voice"]}
            public |= {m["src"] for g in props["groups"] for m in graphic_media(g.get("graphic"))}
            tmp = r.dir / "remotion.tmp.mp4"
            r.remotion("Documentary", props, tmp,
                       ["--muted", f"--concurrency={r.concurrency()}", "--codec=h264", "--crf=12",
                        f"--x264-preset={r.cfg.get('preset', 'veryfast')}"], public)
            tmp.replace(condensed_path)
            spent = time.monotonic() - t
            print(f"   Remotion: {slow_frames} fotogramas en {spent:.0f} s ({slow_frames / max(spent, 0.1):.1f} fps)")

    # 2. ffmpeg: fast shots with their credit badge, and the slow runs cut from the condensed render.
    t = time.monotonic()
    source_word = (timeline.get("locale") or {}).get("source")

    def shown(credit: str) -> str:   # dubbed versions: "Fuente: X" → "Source: X"
        return f"{source_word}: {credit[len('Fuente: '):]}" if source_word and credit.startswith("Fuente: ") else credit

    credits = sorted({shown(s.shots[0]["media"]["credit"]) for s in fast if s.shots[0]["media"].get("credit")})
    badges = r.badges(credits) if credits else {}

    # Remotion jobs share one work folder: the backdrop and the end screen before the parallel part
    if any(s.kind == "ffmpeg" and s.shots[0]["media"].get("layout") == "card" for s in segments):
        r.backdrop()
    ends: dict[int, Path] = {}

    def build(segment: Segment) -> Path:
        if segment.kind == "endscreen":
            return ends[segment.start]
        if segment.kind == "ffmpeg":
            credit = segment.shots[0]["media"].get("credit")
            badge = badges.get(shown(credit)) if credit else None
            if segment.shots[0]["media"].get("layout") == "card":
                return r.card_segment(segment, badge)
            return r.fast_segment(segment, badge)
        return r.cut_segment(segment, condensed_path, _hash(condensed_path.stem, r.enc_key))

    def build_all() -> list[Path]:
        ends.clear()
        ends.update({s.start: r.endscreen(timeline, s) for s in segments if s.kind == "endscreen"})
        with ThreadPoolExecutor(max_workers=max(1, int(r.cfg.get("parallel", 3)))) as pool:
            return list(pool.map(build, segments))

    try:
        files = build_all()
    except RuntimeError as error:
        if not r.nvenc:
            raise
        print(f"   La gráfica falló al codificar ({str(error).splitlines()[-1][:100]}); repito con x264")
        r.set_encoder(False)
        files = build_all()
    print(f"   ffmpeg: {len(files)} segmentos en {time.monotonic() - t:.0f} s"
          + (" (codificados con la gráfica)" if r.nvenc else ""))

    # 3. Audio mix + master, then join everything without re-encoding the video.
    audio = r.audio(timeline)
    listing = r.dir / "segments.txt"
    listing.write_text("".join(f"file '{f.resolve()}'\n" for f in files), encoding="utf-8")
    ctx.out_dir.mkdir(parents=True, exist_ok=True)
    final = ctx.out_dir / OUTPUT
    tmp = final.with_suffix(".tmp.mp4")
    _run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(listing), "-i", str(audio),
          "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", str(r.cfg.get("audio_bitrate", "192k")),
          "-movflags", "+faststart", str(tmp)], "el montaje final")
    tmp.replace(final)
    _prune(r.dir / "segments", {f.name for f in files})
    for old in r.dir.glob("remotion-*.mp4"):
        if old != condensed_path:
            old.unlink()
    for old in r.dir.glob("audio-*.wav"):
        if old != audio:
            old.unlink()

    # 4. Postflight: streams, resolution, A/V durations.
    video = ctx.section("video")
    issues = inspect_render(final, timeline["durationInFrames"] / r.fps,
                            (int(video.get("width", 1920)), int(video.get("height", 1080))))
    (ctx.out_dir / "qa").mkdir(parents=True, exist_ok=True)
    write_postflight_report(ctx.out_dir / "qa" / "postflight.json", issues)
    enforce_postflight(issues)
    try:
        graphics_sheet(ctx, final, timeline)
    except Exception as error:  # a review aid: never costs the video
        print(f"   graficos.md no disponible: {str(error)[:120]}")
    size = final.stat().st_size / 1e6
    print(f"   {final.relative_to(ctx.root)} · {timeline['durationInFrames'] / r.fps:.1f} s · {size:.0f} MB · "
          f"render total {time.monotonic() - started:.0f} s")


def _summary(graphic: dict[str, Any]) -> str:
    """A short line of what a graphic says: its title or name and the first figures."""

    head = graphic.get("title") or graphic.get("name") or " / ".join(graphic.get("lines") or [])
    if not head and isinstance(graphic.get("left"), dict):
        head = f"{graphic['left'].get('name')} vs {graphic.get('right', {}).get('name')}"
    figures: list[str] = []

    def walk(value: Any) -> None:
        if len(figures) >= 4:
            return
        if isinstance(value, dict):
            for k, v in value.items():
                if k in ("value", "score", "year", "total", "d", "e", "place") and not isinstance(v, (dict, list)):
                    figures.append(str(v))
                elif k not in ("media", "focus"):
                    walk(v)
        elif isinstance(value, list):
            for v in value:
                walk(v)

    walk(graphic)
    return (str(head or "")[:60] + (f" · {', '.join(figures)}" if figures else "")).replace("|", "/")


def graphics_sheet(ctx: RunContext, final: Path, timeline: dict[str, Any]) -> None:
    """out/<slug>/graficos.md: one frame of every animated graphic of the final video, with its moment and what
    it says, to review them at a glance (and drop one in the editor if it does not convince)."""

    groups = [g for g in timeline.get("groups", []) if g.get("kind") == "graphic" and g.get("graphic")]
    folder = ctx.out_dir / "graficos"
    if folder.is_dir():
        for old in folder.glob("*.jpg"):
            old.unlink()
    if not groups:
        return
    folder.mkdir(parents=True, exist_ok=True)
    fps = int(timeline.get("fps", 30))
    lines = [f"# Gráficos · {ctx.slug}", "", f"{len(groups)} gráficos animados. Para quitar uno: el editor "
             "(`python main.py --slug <vídeo> --review`) antes de renderizar.", "",
             "| Momento | Tipo | Qué dice | Imagen |", "|---|---|---|---|"]
    for n, g in enumerate(groups, 1):
        at = (g["from"] + max(1, int(g["durationInFrames"] * 0.7))) / fps      # once it has finished coming in
        image = folder / f"{n:02d}-{g['graphic']['type']}.jpg"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{at:.2f}", "-i", str(final), "-frames:v", "1",
                        "-vf", "scale=640:-2", "-q:v", "4", str(image)], capture_output=True, timeout=60)
        clock = f"{int(g['from'] / fps // 60)}:{int(g['from'] / fps % 60):02d}"
        picture = f"![{g['graphic']['type']}](graficos/{image.name})" if image.is_file() else "—"
        lines.append(f"| {clock} | {g['graphic']['type']} | {_summary(g['graphic'])} | {picture} |")
    (ctx.out_dir / "graficos.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"   Revisión de gráficos: {ctx.out_dir.relative_to(ctx.root) / 'graficos.md'}")


def _prune(folder: Path, keep: set[str]) -> None:
    if folder.is_dir():
        for path in folder.iterdir():
            if path.name not in keep:
                path.unlink()


def validate(ctx: RunContext) -> bool:
    report = ctx.out_dir / "qa" / "postflight.json"
    final = ctx.out_dir / OUTPUT
    return final.is_file() and report.is_file() and json.loads(report.read_text("utf-8")).get("status") == "ok"
