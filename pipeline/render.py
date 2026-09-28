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


def is_fast(shot: dict[str, Any], groups: list[dict[str, Any]] = ()) -> bool:
    """Plain footage: only the credit badge is drawn on top, so ffmpeg can compose it."""

    media = shot.get("media") or {}
    a, b = shot["from"], shot["from"] + shot["durationInFrames"]
    covered = any(g["from"] < b and a < g["from"] + g["durationInFrames"] for g in groups)
    return (shot["type"] == "broll" and media.get("kind") == "video" and media.get("layout", "full") == "full"
            and not shot.get("groupId") and not covered)


def plan_segments(timeline: dict[str, Any], hybrid: bool = True) -> list[Segment]:
    segments: list[Segment] = []
    condensed = 0
    groups = [*timeline.get("groups", []), *timeline.get("labels", [])]   # anything drawn over the footage
    for shot in timeline["shots"]:
        if hybrid and is_fast(shot, groups):
            segments.append(Segment("ffmpeg", shot["from"], shot["durationInFrames"], [shot]))
            continue
        if segments and segments[-1].kind == "remotion":
            segments[-1].shots.append(shot)
            segments[-1].frames += shot["durationInFrames"]
        else:
            segments.append(Segment("remotion", shot["from"], shot["durationInFrames"], [shot], condensed))
        condensed += shot["durationInFrames"]
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
    total = sum(s["durationInFrames"] for s in shots)
    audio = {**timeline["audio"], "music": None, "speech": [], "sfx": [], "clips": [], "voiceFrom": 0}
    return {**timeline, "durationInFrames": total, "shots": shots, "groups": groups, "labels": labels, "audio": audio}


def media_seconds(path: Path) -> float:
    result = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                            capture_output=True, text=True)
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def graphic_media(graphic: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Photos/clips a graphic shows (rank, specs, the two sides of a comparison)."""

    if not graphic:
        return []
    found = [graphic.get("media"), (graphic.get("left") or {}).get("media"), (graphic.get("right") or {}).get("media")]
    return [m for m in found if isinstance(m, dict) and m.get("src")]


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
        self.encode = [
            "-c:v", "libx264", "-preset", str(self.cfg.get("preset", "veryfast")), "-crf", str(self.cfg.get("crf", 18)),
            "-pix_fmt", "yuv420p", "-r", str(self.fps), "-g", str(self.fps * 2), "-video_track_timescale", str(self.fps * 512),
            "-an",
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

        folder = self.ctx.cache_dir / "render" / "badges" / _hash(sorted(self._remotion_sig()))
        paths = {c: folder / f"{_hash(c)}.png" for c in credits}
        missing = [c for c in credits if not paths[c].is_file()]
        if missing:
            folder.mkdir(parents=True, exist_ok=True)
            tmp = self.dir / "badges"
            shutil.rmtree(tmp, ignore_errors=True)
            self.remotion("Badges", {"credits": missing}, tmp,
                          ["--sequence", "--image-format=png", f"--concurrency={self.concurrency()}"], set())
            frames = sorted(tmp.iterdir(), key=lambda p: int(re.findall(r"\d+", p.stem)[-1]))
            if len(frames) != len(missing):
                raise RuntimeError(f"Remotion devolvió {len(frames)} créditos, se esperaban {len(missing)}")
            for credit, frame in zip(missing, frames):
                shutil.move(str(frame), paths[credit])
            shutil.rmtree(tmp, ignore_errors=True)
        return paths

    def _remotion_sig(self) -> list:
        files = sorted(p for p in (self.ctx.root / "remotion").rglob("*") if p.is_file())
        return [[str(p.relative_to(self.ctx.root)), hashlib.sha256(p.read_bytes()).hexdigest()[:12]] for p in files]

    # --- ffmpeg segments ------------------------------------------------------------------

    def fast_segment(self, segment: Segment, badge: Path | None) -> Path:
        shot = segment.shots[0]
        clip = self.ctx.work_dir / shot["media"]["src"]
        key = _hash(self.enc_key, _file_sig(clip), segment.frames, _file_sig(badge) if badge else None)
        out = self.dir / "segments" / f"{shot['id']}-{key}.mp4"
        if out.is_file():
            return out
        out.parent.mkdir(parents=True, exist_ok=True)
        pad = f"setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop={segment.frames}"
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
            chains.append(f"[{index}:a]{stereo},atrim=end={clip['durationInFrames'] / self.fps:.3f},"
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
          f"Remotion {slow_frames} fotogramas ({len(slow)} tramos)")

    # 1. Remotion: the condensed timeline of slow shots, one pass.
    condensed_path = None
    if slow:
        props = condensed_props(timeline, segments)
        key = _hash(r.enc_key, props, r._remotion_sig(),
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
    cut_key = condensed_path.stem.split("-")[-1] if condensed_path else ""

    def build(segment: Segment) -> Path:
        if segment.kind == "ffmpeg":
            credit = segment.shots[0]["media"].get("credit")
            return r.fast_segment(segment, badges.get(shown(credit)) if credit else None)
        return r.cut_segment(segment, condensed_path, cut_key)

    with ThreadPoolExecutor(max_workers=max(1, int(r.cfg.get("parallel", 3)))) as pool:
        files = list(pool.map(build, segments))
    print(f"   ffmpeg: {len(files)} segmentos en {time.monotonic() - t:.0f} s")

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
    size = final.stat().st_size / 1e6
    print(f"   {final.relative_to(ctx.root)} · {timeline['durationInFrames'] / r.fps:.1f} s · {size:.0f} MB · "
          f"render total {time.monotonic() - started:.0f} s")


def _prune(folder: Path, keep: set[str]) -> None:
    if folder.is_dir():
        for path in folder.iterdir():
            if path.name not in keep:
                path.unlink()


def validate(ctx: RunContext) -> bool:
    report = ctx.out_dir / "qa" / "postflight.json"
    final = ctx.out_dir / OUTPUT
    return final.is_file() and report.is_file() and json.loads(report.read_text("utf-8")).get("status") == "ok"
