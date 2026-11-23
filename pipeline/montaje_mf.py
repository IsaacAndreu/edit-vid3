"""«Material primero», stages 3, 4 and 6: from the blocks to the finished video (prompt «modo material primero»).

- Downloads: the exact segments, statements WITH their sound and sequences at the final quality, through the
  proxy; the MB are estimated first and the video stops if they pass `material_first.max_mb`. A clip with another
  channel's text burned along its bottom (subtitles, a «breaking news» strip) is cropped like the ingest does; one
  with text all over is dropped (another take, never someone else's words on screen).
- Every statement is checked: its clip is transcribed and must match the case file's sentence
  (`quotes.min_match`); if it does not, it does not go in. No name that does not come from the source (stage 1).
- The voice: the synthetic voice reads ONLY the narrator's blocks, one file per block, joined.
- The montage does not cut every 3 s: each block is a shot or a long sequence — the narration over the footage of
  its entry (its sequences, in order, with their ambient sound low), the statements as they are (the narration
  pauses, the person is heard, Spanish subtitles and who speaks), the entry cards. The source of each clip, top
  right, always; the channel's cap (`content.max_third_party_seconds`) for how long one source runs.
- Stage 4, the hook: its own step — a «director» call that receives the candidate moments of the case file (what is
  seen, what is said) and returns the order and length of each cut, a minute at most, original sound subtitled and
  a big word now and then; then the title card of the top.
- Stage 6, the statements dubbed: by default subtitled with the original voice; per channel
  (`material_first.dub_testimonies`) «una_voz» (one deep documentary voice for all) or «por_persona» (a different
  voice of the catalogue for each person, man or woman by who speaks) over the original kept low, always labelled
  as dubbed — never an imitation of the person's voice.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any, Callable

FPS = 30
CARD_SECONDS = 3.0
TITLE_SECONDS = 3.0
AMBIENT = 0.15                     # the sequences' own sound, low under the narration
DUB_ORIGINAL = 0.25                # the original voice under a dub, like a newscast
CHUNK_WORDS = 8

DIRECTOR_SYSTEM = """
Eres el director de un vídeo de YouTube de tipo «{kind}». Montas el GANCHO: de 6 a 10 cortes con los momentos más
fuertes de TODO el vídeo, en un minuto como mucho, antes del título. Te paso los momentos candidatos (id, qué se ve,
qué se dice, de qué puesto). Elige y ordena: que el primer corte enganche en un segundo, que se oiga a la gente (una
frase corta que se entienda sola), que haya acción entre las frases, y que no se destripe el número 1. Para cada
corte di cuántos segundos dura (1,5 a 6), desde qué segundo del momento empieza, y si lleva una PALABRA grande en
pantalla (una sola, en mayúsculas, de vez en cuando: «BLOQUEO», «DESTRUCTIVAS»).
Devuelve SOLO JSON: {{"cuts": [{{"id": "c3", "from": 0.0, "seconds": 2.5, "word": null}}]}}
""".strip()


# --- downloads ------------------------------------------------------------------------------------------------------

def download_mb(blocks: list[dict[str, Any]]) -> int:
    from .bloques import MB_PER_SECOND

    return round(sum(b["end"] - b["start"] for b in blocks if b["type"] in ("declaracion", "secuencia")) * MB_PER_SECOND)


def fetch_clips(ctx: Any, blocks: list[dict[str, Any]], fetch_fn: Callable[[str, float, float, Path], dict | None],
                log: Callable[[str], None] = print) -> dict[int, dict[str, Any]]:
    """{block position: {"path", "duration", "hasAudio"}} for every statement and sequence that came down."""

    folder = ctx.work_dir / "media_mf"
    folder.mkdir(parents=True, exist_ok=True)
    out: dict[int, dict[str, Any]] = {}
    for pos, block in enumerate(blocks):
        if block["type"] not in ("declaracion", "secuencia"):
            continue
        target = folder / f"{pos:03d}-{block['source']}-{block['start']:.1f}.mp4"
        info = fetch_fn(block["source"], float(block["start"]), float(block["end"] - block["start"]), target)
        if not info:
            log(f"   bloque {pos} ({block['type']}): no se pudo bajar {block['source']} {block['start']:.0f}-{block['end']:.0f} s")
            continue
        if block["type"] == "declaracion" and not info.get("hasAudio"):
            log(f"   bloque {pos}: la declaración llegó sin sonido; fuera")
            continue
        out[pos] = {"path": target, "duration": float(info["duration"]), "hasAudio": bool(info.get("hasAudio"))}
    return out


def default_fetch(ctx: Any, youtube: Any) -> Callable[[str, float, float, Path], dict | None]:
    """The segment WITH its sound at 1920x1080 (quotes.fetch), then the burned-text check of the fallback: cropped
    when the text is only on the edges (the ingest's crop), dropped when it covers the picture."""

    from .quotes import fetch

    def get(video_id: str, start: float, length: float, target: Path) -> dict | None:
        info = fetch(youtube, video_id, start, length, target)
        if info is None:
            return None
        try:
            from .content_check import ContentCheck

            why = ContentCheck(ctx).burned_text(target, "video", target.stat())
        except Exception:
            why = None
        if why:
            target.unlink(missing_ok=True)
            print(f"   {video_id} {start:.0f}s: {why}: otra toma")
            return None
        return info

    return get


# --- the statements' check ------------------------------------------------------------------------------------------

def default_transcribe(ctx: Any) -> Callable[[Path, str], list]:
    def transcribe(path: Path, lang: str) -> list:
        from faster_whisper import WhisperModel

        model = WhisperModel(str(ctx.section("quotes").get("whisper_model", "small")), device="cpu", compute_type="int8")
        segments, _ = model.transcribe(str(path), language=lang or None, word_timestamps=True, vad_filter=True)
        return [(w.word.strip(), w.start, w.end) for s in segments for w in (s.words or []) if w.word.strip()]
    return transcribe


def verify(blocks: list[dict[str, Any]], clips: dict[int, dict[str, Any]], transcribe: Callable[[Path, str], list],
           minimum: float, log: Callable[[str], None] = print) -> dict[int, float]:
    """Each statement's clip transcribed against the case file's sentence; those under `minimum` are dropped."""

    from .quotes import best_match

    scores: dict[int, float] = {}
    for pos, block in enumerate(blocks):
        if block["type"] != "declaracion" or pos not in clips:
            continue
        try:
            match = best_match(transcribe(clips[pos]["path"], str(block.get("lang") or "")), block["said"])
        except Exception as error:
            log(f"   bloque {pos}: no se pudo comprobar la declaración ({str(error)[:100]}); fuera")
            match = None
        score = match[2] if match else 0.0
        scores[pos] = round(score, 2)
        if score < minimum:
            log(f"   bloque {pos}: lo que se oye no coincide con la frase del expediente ({score:.2f} < {minimum}); fuera")
            clips.pop(pos, None)
    return scores


# --- the voice --------------------------------------------------------------------------------------------------------

def duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True)
    return float(out.stdout.strip() or 0)


def narration(ctx: Any, blocks: list[dict[str, Any]], speak: Callable[[str, Path], Path]) -> tuple[Path, dict[int, float]]:
    """One voice file per narrator block (cached by its text), joined into audio/voz.mp3: (file, {position: seconds})."""

    import hashlib

    folder = ctx.work_dir / "audio" / "narrador"
    folder.mkdir(parents=True, exist_ok=True)
    parts, seconds = [], {}
    for pos, block in enumerate(blocks):
        if block["type"] != "narrador":
            continue
        target = folder / f"{hashlib.sha1(block['text'].encode()).hexdigest()[:12]}.mp3"
        if not target.is_file():
            speak(block["text"], target)
        parts.append(target)
        seconds[pos] = duration(target)
    voice = ctx.work_dir / "audio" / "voz.mp3"
    listing = folder / "lista.txt"
    listing.write_text("".join(f"file '{p.resolve()}'\n" for p in parts), encoding="utf-8")
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
                    "-c:a", "libmp3lame", "-b:a", "192k", str(voice)], check=True)
    return voice, seconds


def default_speak(ctx: Any) -> Callable[[str, Path], Path]:
    from . import tts

    voice = tts.voice_for_video(ctx)
    if not voice:
        raise ValueError("El canal no tiene voz del narrador (Voces)")

    def speak(text: str, target: Path) -> Path:
        tts.generate(tts.keys(ctx.root), text, voice, target)
        return target

    return speak


# --- the montage ----------------------------------------------------------------------------------------------------

def cut(source: Path, target: Path, offset: float, seconds: float) -> Path:
    """A piece of a downloaded clip, exact, with its sound (the same normaliser as the cold open)."""

    from .coldopen import normalise_with_audio

    if not target.is_file():
        normalise_with_audio(source, target, offset=offset, duration=seconds, lut=None)
    return target


def subtitle_lines(text: str, frames: int, lead: int = 6) -> list[dict[str, int | str]]:
    words = text.split()
    chunks = [" ".join(words[i:i + CHUNK_WORDS]) for i in range(0, len(words), CHUNK_WORDS)] or [text]
    span = max(1, frames - lead - 6)
    total = sum(len(c) for c in chunks) or 1
    out, at = [], lead
    for chunk in chunks:
        length = max(1, round(span * len(chunk) / total))
        out.append({"text": chunk, "from": at, "to": min(frames, at + length)})
        at += length
    return out


ROLE_LABEL = {"testigo": "testigo", "periodista": "periodista", "policía": "agente", "familiar": "familiar",
              "experto": "experto", "protagonista": "protagonista", "narrador de la fuente": "", "otro": ""}


class Builder:
    """Shots, groups and sound laid one after the other; the voice advances only under the narrator's blocks."""

    def __init__(self, ctx: Any, cut_fn: Callable[[Path, Path, float, float], Path] = cut) -> None:
        self.ctx, self.cut_fn = ctx, cut_fn
        self.frame = self.voice = 0
        self.shots: list[dict[str, Any]] = []
        self.groups: list[dict[str, Any]] = []
        self.clips: list[dict[str, Any]] = []
        self.gaps: list[tuple[int, int]] = []
        self.speech: list[tuple[int, int]] = []
        self.n = 0

    def src(self, path: Path) -> str:
        return str(Path(path).resolve().relative_to(self.ctx.work_dir.resolve()))

    def card(self, title: str, number: int | None, seconds: float = CARD_SECONDS) -> None:
        frames = round(seconds * FPS)
        self.shots.append({"id": f"card{len(self.shots)}", "type": "chapter", "from": self.frame, "durationInFrames": frames,
                           "text": title, "chapterTitle": title[:60], **({"chapterNumber": number} if number else {})})
        self.gaps.append((self.voice, frames))
        self.frame += frames

    def footage(self, path: Path, offset: float, seconds: float, channel: str, volume: float, original: bool = False,
                text: str = "") -> int:
        self.n += 1
        piece = self.cut_fn(path, self.ctx.work_dir / "media_mf" / f"cut-{self.n:03d}.mp4", offset, seconds)
        frames = max(1, round(seconds * FPS))
        self.shots.append({"id": f"m{self.n:03d}", "type": "broll", "from": self.frame, "durationInFrames": frames,
                           "text": text, "coldOpen": original,
                           "media": {"src": self.src(piece), "kind": "video", "source": "youtube",
                                     "credit": f"Fuente: {channel or 'YouTube'}", "layout": "full"}})
        self.clips.append({"src": self.src(piece), "from": self.frame, "durationInFrames": frames, "volume": volume,
                           "fade": not original})
        start = self.frame
        self.frame += frames
        return start

    def narrate(self, seconds: float, pool: "Pool", text: str) -> None:
        frames = round(seconds * FPS)
        start = self.frame
        left = frames / FPS
        while left > 0.05:
            path, offset, take, channel = pool.take(left)
            self.footage(path, offset, take, channel, AMBIENT, text=text)
            left -= take
        self.speech.append((start, self.frame))
        self.voice += self.frame - start

    def statement(self, clip: dict[str, Any], block: dict[str, Any], dubbed: dict[str, Any] | None = None) -> None:
        start = self.footage(clip["path"], 0.0, clip["duration"], block.get("channel") or "",
                             DUB_ORIGINAL if dubbed else 1.0, original=True, text=block.get("said") or "")
        frames = self.frame - start
        self.gaps.append((self.voice, frames))
        who = block.get("speaker") or ROLE_LABEL.get(block.get("role") or "", "") or "testimonio"
        role = None if block.get("speaker") is None else ROLE_LABEL.get(block.get("role") or "", "") or None
        if dubbed:
            role = f"{role + ' · ' if role else ''}voz doblada"
            self.clips.append({"src": self.src(dubbed["path"]), "from": start, "durationInFrames": frames, "volume": 1.0,
                               "fade": True})
        text = block.get("translation") or block.get("said") or ""
        self.groups.append({"id": f"quote-{start}", "kind": "graphic", "from": start, "durationInFrames": frames,
                            "graphic": {"type": "quote", "speaker": who[:60], "role": role,
                                        "lines": subtitle_lines(text, frames)}})

    def word(self, text: str, start: int, frames: int) -> None:
        self.groups.append({"id": f"word-{start}", "kind": "graphic", "from": start, "durationInFrames": frames,
                            "graphic": {"type": "kinetic", "lines": [text.upper()[:24]]}})


class Pool:
    """The footage of an entry (its sequences in order), taken a piece at a time under the narration; when it runs
    out it starts again from the first sequence (never another entry's footage)."""

    def __init__(self, pieces: list[tuple[Path, float, str]], cap: float) -> None:
        self.pieces = [p for p in pieces if p[1] > 0.5]
        self.cap = cap
        self.i, self.used = 0, 0.0

    def take(self, wanted: float) -> tuple[Path, float, float, str]:
        if not self.pieces:
            raise ValueError("un puesto sin ninguna secuencia descargada: no hay qué enseñar bajo la voz")
        path, length, channel = self.pieces[self.i]
        left = length - self.used
        take = min(wanted, left, self.cap)
        offset = self.used
        self.used += take
        if self.used >= length - 0.05:
            self.i, self.used = (self.i + 1) % len(self.pieces), 0.0
        return path, offset, take, channel


def item_of(blocks: list[dict[str, Any]], index: dict[str, dict[str, Any]]) -> list[int | None]:
    """The entry of each block: cards say it; the rest by their segment, or the last card's."""

    current, out = None, []
    for block in blocks:
        if block["type"] == "tarjeta" and block.get("item"):
            current = block["item"]
        elif block.get("ref") in index:
            current = index[block["ref"]]["item"]
        out.append(current)
    return out


CARD_WORD = {"top": "PUESTO", "noticia": "PARTE", "documental": "CAPÍTULO"}


def assemble(ctx: Any, blocks: list[dict[str, Any]], clips: dict[int, dict[str, Any]], seconds: dict[int, float],
             voice: Path, items: list[int | None], hook: list[dict[str, Any]] | None = None, title: str = "",
             dubbed: dict[int, dict[str, Any]] | None = None, cut_fn: Callable = cut, kind: str = "top") -> dict[str, Any]:
    """The timeline (pipeline/schemas.Timeline): hook, title card, then the blocks."""

    from . import tope
    from .schemas import Timeline

    cap = tope.seconds(ctx)
    pools: dict[Any, Pool] = {}
    for item in dict.fromkeys(items):
        pieces = [(clips[p]["path"], clips[p]["duration"], blocks[p].get("channel") or "")
                  for p, b in enumerate(blocks) if b["type"] == "secuencia" and items[p] == item and p in clips]
        pools[item] = Pool(pieces, cap)
    every = [p for pool in pools.values() for p in pool.pieces]
    b = Builder(ctx, cut_fn)
    for cut_ in hook or []:                           # stage 4: the director's cuts, original sound
        start = b.footage(cut_["path"], cut_["from"], cut_["seconds"], cut_.get("channel") or "", 1.0, original=True,
                          text=cut_.get("said") or "")
        frames = b.frame - start
        b.gaps.append((b.voice, frames))
        if cut_.get("said"):
            b.groups.append({"id": f"hookq-{start}", "kind": "graphic", "from": start, "durationInFrames": frames,
                             "graphic": {"type": "quote", "speaker": cut_.get("who") or "", "role": None,
                                         "lines": subtitle_lines(cut_.get("translation") or cut_["said"], frames, lead=2)}})
        elif cut_.get("word"):
            b.word(cut_["word"], start, frames)
    if hook and title:
        b.card(title, None, TITLE_SECONDS)
    for pos, block in enumerate(blocks):
        if block["type"] == "tarjeta":
            b.card(block.get("title") or "", block.get("number"))
        elif block["type"] == "narrador" and pos in seconds:
            pool = pools.get(items[pos])
            if pool is None or not pool.pieces:
                pool = Pool(every, cap)               # an entry with no footage of its own: the video's, never empty
            b.narrate(seconds[pos], pool, block["text"])
        elif block["type"] == "declaracion" and pos in clips:
            b.statement(clips[pos], block, (dubbed or {}).get(pos))
    video = ctx.section("video") or {}
    timeline = {"slug": ctx.slug, "title": title or ctx.slug, "fps": FPS, "width": int(video.get("width", 1920)),
                "height": int(video.get("height", 1080)), "durationInFrames": b.frame, "shots": b.shots,
                "groups": b.groups, "audio": {"voice": b.src(voice), "voiceFrom": 0, "clips": b.clips,
                                              "speech": b.speech, "voiceGaps": b.gaps},
                "brand": {k: str(v) for k, v in (ctx.section("brand") or {}).items()},
                "locale": {"chapter": CARD_WORD.get(kind, "PUESTO")}}
    return Timeline.model_validate(timeline).model_dump(by_alias=True)   # with every default the render reads


# --- stage 4: the hook ----------------------------------------------------------------------------------------------

def hook_candidates(blocks: list[dict[str, Any]], clips: dict[int, dict[str, Any]], items: list[int | None],
                    last_item: int | None) -> list[dict[str, Any]]:
    """The moments the director chooses from: statements and sequences that came down, never of the number 1."""

    out = []
    for pos, block in enumerate(blocks):
        if pos not in clips or block["type"] not in ("declaracion", "secuencia"):
            continue
        if last_item is not None and items[pos] == last_item:
            continue                                  # the number 1 is not given away in the hook
        out.append({"id": f"c{pos}", "pos": pos, "type": block["type"], "item": items[pos],
                    "seen": block.get("seen") or "", "said": block.get("said") or "",
                    "seconds": round(clips[pos]["duration"], 1)})
    return out


def direct(kind: str, candidates: list[dict[str, Any]], ask: Callable[[str, str], dict[str, Any]],
           blocks: list[dict[str, Any]], clips: dict[int, dict[str, Any]], limit: float = 60.0) -> list[dict[str, Any]]:
    """The director's cuts, checked: known moments, inside their clip, 1.5-6 s each, a minute at most in all."""

    if not candidates:
        return []
    listing = "\n".join(f"[{c['id']}] {c['type']} · puesto {c['item']} · {c['seconds']} s · se ve: {c['seen'] or '-'}"
                        + (f" · dice: «{c['said'][:160]}»" if c["said"] else "") for c in candidates)
    raw = ask(DIRECTOR_SYSTEM.format(kind=kind), listing)
    by_id = {c["id"]: c for c in candidates}
    cuts, total = [], 0.0
    for c in raw.get("cuts") or []:
        cand = by_id.get(str(c.get("id")))
        if cand is None:
            continue
        clip = clips[cand["pos"]]
        try:
            start = max(0.0, float(c.get("from") or 0))
            seconds = max(1.5, min(6.0, float(c.get("seconds") or 2.5)))
        except (TypeError, ValueError):
            continue
        seconds = min(seconds, clip["duration"] - start)
        if seconds < 1.0 or total + seconds > limit:
            continue
        block = blocks[cand["pos"]]
        word = str(c.get("word") or "").strip()
        cuts.append({"path": clip["path"], "from": round(start, 2), "seconds": round(seconds, 2),
                     "channel": block.get("channel"), "word": word if word and block["type"] == "secuencia" else None,
                     "said": block.get("said") if block["type"] == "declaracion" else None,
                     "translation": block.get("translation"),
                     "who": block.get("speaker") or ROLE_LABEL.get(block.get("role") or "", "")})
        total += seconds
    return cuts[:10]


# --- stage 6: the statements dubbed ----------------------------------------------------------------------------------

def dub_voices(mode: str, blocks: list[dict[str, Any]], catalogue: dict[str, Any]) -> dict[int, dict[str, Any]]:
    """Which catalogue voice reads each statement: «una_voz» one for all; «por_persona» one per person, man or woman
    by who speaks (a person keeps theirs across the video). {} for «subtitulo» or with no voices set."""

    if mode not in ("una_voz", "por_persona"):
        return {}
    out: dict[int, dict[str, Any]] = {}
    if mode == "una_voz":
        voice = catalogue.get("documental") or catalogue.get("hombre") or next(iter(catalogue.values()), None)
        return {p: voice for p, b in enumerate(blocks) if b["type"] == "declaracion" and voice}
    given: dict[str, dict[str, Any]] = {}
    turns = {"hombre": 0, "mujer": 0}
    for pos, block in enumerate(blocks):
        if block["type"] != "declaracion":
            continue
        who = block.get("speaker") or f"{block.get('role')}-{block.get('ref')}"
        if who not in given:
            gender = block.get("gender") if block.get("gender") in ("hombre", "mujer") else "hombre"
            options = catalogue.get({"hombre": "hombres", "mujer": "mujeres"}[gender]) or [catalogue.get(gender)]
            options = [o for o in options if o]
            if not options:
                continue
            given[who] = options[turns[gender] % len(options)]
            turns[gender] += 1
        out[pos] = given[who]
    return out


def dub(ctx: Any, blocks: list[dict[str, Any]], clips: dict[int, dict[str, Any]], voices: dict[int, dict[str, Any]],
        speak_with: Callable[[str, dict[str, Any], Path], Path]) -> dict[int, dict[str, Any]]:
    """Each statement's Spanish line read by its catalogue voice; the original stays under it."""

    import hashlib

    folder = ctx.work_dir / "audio" / "doblaje"
    folder.mkdir(parents=True, exist_ok=True)
    out = {}
    for pos, voice in voices.items():
        block = blocks[pos]
        text = block.get("translation") if (block.get("lang") or "es") != "es" else ""
        if pos not in clips or not text:
            continue                                  # already in Spanish, or no translation: subtitles only
        target = folder / f"{hashlib.sha1((text + json.dumps(voice, sort_keys=True)).encode()).hexdigest()[:12]}.mp3"
        if not target.is_file():
            speak_with(text, voice, target)
        out[pos] = {"path": target}
    return out


# --- the whole stage ---------------------------------------------------------------------------------------------------

def run(root: Path, slug: str, *, youtube: Any = None, fetch_fn: Callable | None = None, transcribe: Callable | None = None,
        speak: Callable | None = None, ask: Callable | None = None, speak_with: Callable | None = None,
        render: bool = True, log: Callable[[str], None] = print) -> dict[str, Any]:
    """`python main.py --montar <vídeo>`: downloads, checks, voice, hook, montage and render of a «material primero»
    video from its blocks (work/<vídeo>/bloques.json)."""

    from .bloques import OUTPUT as BLOCKS, segment_index
    from .context import RunContext
    from .expediente import load

    ctx = RunContext.create(slug, root=root)
    cfg = ctx.section("material_first")
    data = json.loads((ctx.work_dir / BLOCKS).read_text("utf-8"))
    blocks = data["blocks"]
    mb = download_mb(blocks)
    cap_mb = int(cfg.get("max_mb", 1500))
    if mb > cap_mb:
        raise ValueError(f"Bajar sus tramos costaría ~{mb} MB por el proxy (tope material_first.max_mb = {cap_mb}): "
                         "quita bloques o sube el tope")
    log(f"   Bajando {sum(1 for b in blocks if b['type'] in ('declaracion', 'secuencia'))} tramos (~{mb} MB por el proxy)")
    opened = None
    if fetch_fn is None:
        if youtube is None:
            from .sourcing import youtube_source

            youtube = opened = youtube_source(ctx)
        fetch_fn = default_fetch(ctx, youtube)
    try:
        clips = fetch_clips(ctx, blocks, fetch_fn, log)
    finally:
        if opened is not None:
            opened.close()
    scores = verify(blocks, clips, transcribe or default_transcribe(ctx),
                    float(ctx.section("quotes").get("min_match", 0.55)), log)
    voice, seconds = narration(ctx, blocks, speak or default_speak(ctx))
    index = segment_index(load(ctx))
    items = item_of(blocks, index)
    hook: list[dict[str, Any]] = []
    if cfg.get("hook", True):
        if ask is None:
            from .llm import complete_json

            def ask(system: str, user: str) -> dict[str, Any]:
                return complete_json(ctx, stage="gancho", section="planner", max_tokens=1500, system=system, user=user)
        numbers = [b.get("number") for b in blocks if b["type"] == "tarjeta" and b.get("number")]
        last = next((b["item"] for b in blocks if b["type"] == "tarjeta" and numbers and b.get("number") == min(numbers)),
                    None) if data.get("kind") == "top" else None
        hook = direct(str(data.get("kind") or "top"), hook_candidates(blocks, clips, items, last), ask, blocks, clips,
                      float(cfg.get("hook_seconds", 60)))
    mode = str(cfg.get("dub_testimonies") or "subtitulo")
    voices = dub_voices(mode, blocks, cfg.get("dub_voices") or {})
    dubbed = {}
    if voices:
        if speak_with is None:
            from . import tts

            def speak_with(text: str, voice: dict[str, Any], target: Path) -> Path:
                # only {voice_id} in the config: the model and provider defaults, as every voice of the catalogue
                tts.generate(tts.keys(root), text, tts.with_defaults(dict(voice)), target)
                return target
        dubbed = dub(ctx, blocks, clips, voices, speak_with)
    timeline = assemble(ctx, blocks, clips, seconds, voice, items, hook, str(data.get("title") or ""), dubbed,
                        kind=str(data.get("kind") or "top"))
    ctx.write_json("timeline.json", timeline)
    summary = {"clips": len(clips), "statementsChecked": scores, "hookCuts": len(hook), "dubbed": len(dubbed),
               "seconds": round(timeline["durationInFrames"] / FPS, 1)}
    ctx.write_json("montaje_mf.json", summary)
    if render:
        from . import render as render_stage

        render_stage.run(ctx)
    return summary
