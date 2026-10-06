"""The narration made from the script with GenAIPro (Labs: ElevenLabs voices) instead of recording it.

- The key: GENAIPRO_API_KEY in .env (genaipro.io → avatar → Manage Account → API Key). Never in the repository.
- A voice per channel: studio → Ajustes → «Voces por canal» (out/_voces.json): the voice ID, the model and the
  settings. The studio also searches GenAIPro's voices and plays a test with a channel's voice.
- A video with its script and no voz.mp3, in a channel that has a voice, is in the queue like any other. The
  watcher makes its narration as soon as the video appears (a thread of its own, `prepare_all`, one video at a
  time), without waiting for its turn: when the turn comes, voz.mp3 is already in its folder. If it is not yet,
  ensure() (main._run_one) waits for the one being made or makes it. A voz.mp3 you upload is always used as it is.
- The text is the script without the `## chapter` lines (they are not narrated) and without markdown marks. A long
  script goes in pieces of up to `max_chars` (cut at paragraphs, then sentences), joined into one mp3.
- API (docs.genaipro.io/openapi.yaml): POST /v1/labs/task → task_id; GET /v1/labs/task/{id} until status
  «completed» → result (the mp3's URL); GET /v1/labs/voices; GET /v1/labs/credits.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

import requests

BASE = "https://genaipro.io/api"
FILE = "out/_voces.json"
MODELS = ("eleven_multilingual_v2", "eleven_turbo_v2_5", "eleven_flash_v2_5", "eleven_v3", "eleven_v4")
DEFAULTS = {"model_id": "eleven_multilingual_v2", "stability": 0.5, "similarity": 0.75, "style": 0.0, "speed": 1.0,
            "use_speaker_boost": True}
MAX_CHARS = 4500
WAIT_SECONDS = 1800
LOCK = ".voz.generando"          # in the video's folder while its narration is being made (pid, time)
FAILED = "voz.error.json"        # the last failure: the background retries it after RETRY_MINUTES
RETRY_MINUTES = 30
TIMINGS = "voz.palabras.json"    # word timings from GenAIPro's subtitles: the align stage skips Whisper with them
SUBTITLE_CHARS = 18              # short cues → each word's time is close (the cue's span shared by its words)


class TTSError(RuntimeError):
    pass


# --- voices per channel -----------------------------------------------------------------------------------------

def _read(root: Path) -> dict[str, Any]:
    try:
        data = json.loads((root / FILE).read_text("utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def voices(root: Path) -> dict[str, dict[str, Any]]:
    """channel → its voice settings ({} when the channel has none)."""

    return {c: {**DEFAULTS, **v} for c, v in _read(root).items() if isinstance(v, dict) and v.get("voice_id")}


def voice_for(root: Path, channel: str) -> dict[str, Any] | None:
    return voices(root).get(channel)


def set_voice(root: Path, channel: str, body: dict[str, Any]) -> dict[str, Any]:
    """From the studio: {voice_id, name?, model_id?, stability?, similarity?, style?, speed?}; voice_id "" removes it."""

    data = _read(root)
    if not str(body.get("voice_id") or "").strip():
        data.pop(channel, None)
    else:
        entry = {"voice_id": str(body["voice_id"]).strip(), "name": str(body.get("name") or "").strip()}
        if body.get("model_id"):
            if body["model_id"] not in MODELS:
                raise ValueError(f"Modelo desconocido: {body['model_id']}")
            entry["model_id"] = body["model_id"]
        for key, low, high in (("stability", 0, 1), ("similarity", 0, 1), ("style", 0, 1), ("speed", 0.7, 1.2)):
            if body.get(key) not in (None, ""):
                entry[key] = min(high, max(low, float(body[key])))
        data[channel] = entry
    path = root / FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return voices(root)


# --- the API ------------------------------------------------------------------------------------------------------

class GenAIPro:
    def __init__(self, token: str, session: Any = None) -> None:
        if not token:
            raise TTSError("Falta GENAIPRO_API_KEY en .env (genaipro.io → avatar → Manage Account → API Key)")
        self.http = session or requests.Session()
        self.headers = {"Authorization": f"Bearer {token}"}

    RETRIES = (2, 5, 10, 20, 40)       # seconds between tries of a read (avion7: one ConnectionError lost a voice)

    def _call(self, method: str, path: str, **kwargs: Any) -> Any:
        """One API call. Reads (GET) are retried on network errors, 429 and 5xx; a POST is never repeated blindly
        (a task created twice is paid twice)."""

        waits = list(self.RETRIES) if method == "GET" else []
        while True:
            try:
                response = self.http.request(method, BASE + path, headers=self.headers, timeout=60, **kwargs)
            except requests.RequestException as error:
                if waits:
                    time.sleep(waits.pop(0))
                    continue
                raise TTSError(f"GenAIPro no responde ({type(error).__name__})") from error
            if waits and (response.status_code == 429 or response.status_code >= 500):
                time.sleep(waits.pop(0))
                continue
            break
        if response.status_code >= 400:
            try:
                detail = response.json()
                detail = detail.get("message") or detail.get("error") or detail
            except ValueError:
                detail = response.text[:200]
            raise TTSError(f"GenAIPro {response.status_code}: {str(detail)[:300]}")
        return response.json() if response.content else {}

    def credits(self) -> list[dict[str, Any]]:
        return self._call("GET", "/v1/labs/credits")

    def search(self, query: str = "", language: str = "", gender: str = "", page_size: int = 30) -> list[dict[str, Any]]:
        params = {k: v for k, v in {"search": query, "language": language, "gender": gender, "page_size": page_size}.items() if v}
        return self._call("GET", "/v1/labs/voices", params=params)

    def create(self, text: str, voice: dict[str, Any]) -> str:
        body = {"input": text, "voice_id": voice["voice_id"], "model_id": voice.get("model_id", DEFAULTS["model_id"]),
                **{k: voice[k] for k in ("stability", "similarity", "style", "speed", "use_speaker_boost") if k in voice}}
        task = self._call("POST", "/v1/labs/task", json=body)
        task_id = task.get("task_id") or task.get("id")
        if not task_id:
            raise TTSError(f"GenAIPro no devolvió la tarea: {str(task)[:200]}")
        return str(task_id)

    def wait(self, task_id: str, timeout: float = WAIT_SECONDS, every: float = 5.0) -> str:
        """The mp3's URL once the task is completed."""

        ends = time.monotonic() + timeout
        while time.monotonic() < ends:
            task = self._call("GET", f"/v1/labs/task/{task_id}")
            status = str(task.get("status") or "").lower()
            result = task.get("result")
            if isinstance(result, dict):
                result = result.get("url") or result.get("audio") or ""
            if status in ("completed", "complete", "done", "success", "succeeded") and result:
                return str(result)
            if status in ("failed", "error", "cancelled", "canceled"):
                raise TTSError(f"GenAIPro: la tarea {task_id} falló ({str(task.get('error') or task)[:200]})")
            time.sleep(every)
        raise TTSError(f"GenAIPro: la tarea {task_id} no terminó en {timeout / 60:.0f} min")

    def subtitle(self, task_id: str, timeout: float = 120, every: float = 3.0) -> str:
        """The subtitle file's URL (short cues: a few words each, for word timings)."""

        made = self._call("POST", f"/v1/labs/task/subtitle/{task_id}",
                          json={"max_characters_per_line": SUBTITLE_CHARS, "max_lines_per_cue": 1,
                                "max_seconds_per_cue": 2})
        url = made.get("subtitle") if isinstance(made, dict) else None
        ends = time.monotonic() + timeout
        while not url and time.monotonic() < ends:
            time.sleep(every)
            url = self._call("GET", f"/v1/labs/task/{task_id}").get("subtitle")
        if not url:
            raise TTSError(f"GenAIPro no dio los subtítulos de la tarea {task_id}")
        return str(url)

    def download(self, url: str, target: Path) -> Path:
        waits = list(self.RETRIES)
        while True:
            try:
                with self.http.get(url, stream=True, timeout=300) as response:
                    response.raise_for_status()
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with target.open("wb") as out:
                        for chunk in response.iter_content(1 << 16):
                            out.write(chunk)
                return target
            except (requests.RequestException, RuntimeError) as error:
                if waits:
                    time.sleep(waits.pop(0))
                    continue
                raise TTSError(f"No se pudo bajar el audio de GenAIPro ({type(error).__name__})") from error


# --- the script → the narration ---------------------------------------------------------------------------------

def narration_text(script: str) -> str:
    """What is said: no `## chapter` lines, no markdown marks, paragraphs kept."""

    lines = []
    for line in script.splitlines():
        if re.match(r"^\s*#", line):
            continue
        line = re.sub(r"[*_`>]+", "", line).strip()
        lines.append(line)
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def pieces(text: str, max_chars: int = MAX_CHARS) -> list[str]:
    """Up to max_chars each, cut between paragraphs, else between sentences, else between words."""

    out: list[str] = []
    current = ""
    units: list[str] = []
    for paragraph in [p.strip() for p in text.split("\n\n") if p.strip()]:
        if len(paragraph) <= max_chars:
            units.append(paragraph)
            continue
        for sentence in re.split(r"(?<=[.!?…])\s+", paragraph):
            while len(sentence) > max_chars:
                cut = sentence.rfind(" ", 0, max_chars)
                units.append(sentence[: cut if cut > 0 else max_chars])
                sentence = sentence[cut if cut > 0 else max_chars:].strip()
            units.append(sentence)
    for unit in units:
        if current and len(current) + 2 + len(unit) > max_chars:
            out.append(current)
            current = unit
        else:
            current = f"{current}\n\n{unit}" if current else unit
    if current:
        out.append(current)
    return out


def generate(token: str, text: str, voice: dict[str, Any], target: Path, session: Any = None,
             log: Any = print) -> dict[str, Any]:
    """The whole text as one mp3 at `target`. Returns {"chars", "pieces", "tasks"}.

    Each piece's task and audio are kept in `.voz-trozos/` next to `target` until the end: after a restart (or a
    failure half way) the pieces already made are reused, not paid again."""

    import hashlib

    api = GenAIPro(token, session)
    parts = pieces(text, int(voice.get("max_chars", MAX_CHARS)))
    if not parts:
        raise TTSError("El guion está vacío")
    work = target.parent / ".voz-trozos"
    work.mkdir(parents=True, exist_ok=True)
    state_file = work / "tareas.json"
    try:
        state = json.loads(state_file.read_text("utf-8"))
    except (OSError, ValueError):
        state = {}
    settings = json.dumps({k: voice.get(k) for k in ("voice_id", *DEFAULTS)}, sort_keys=True)
    tasks, files = [], []
    for number, part in enumerate(parts, start=1):
        key = hashlib.sha1((settings + part).encode("utf-8")).hexdigest()[:16]
        piece = work / f"{key}.mp3"
        files.append(piece)
        if piece.is_file() and piece.stat().st_size > 0:
            log(f"   Voz {number}/{len(parts)}: ya hecha antes, la reutilizo")
            tasks.append(state.get(key, ""))
            continue
        task_id = state.get(key)
        if task_id:
            log(f"   Voz {number}/{len(parts)}: retomo la tarea {task_id}")
        else:
            task_id = api.create(part, voice)
            state[key] = task_id
            state_file.write_text(json.dumps(state), encoding="utf-8")
            log(f"   Voz {number}/{len(parts)}: {len(part)} caracteres → tarea {task_id}")
        tasks.append(task_id)
        if (target.parent / LOCK).is_file():                  # still alive: a long narration is not a stale lock
            (target.parent / LOCK).touch()
        url = api.wait(task_id)
        log(f"   Voz {number}/{len(parts)}: lista, descargando")
        partial_piece = piece.with_suffix(".bajando")
        api.download(url, partial_piece)
        if partial_piece.stat().st_size == 0:
            raise TTSError(f"GenAIPro devolvió un audio vacío (tarea {task_id})")
        partial_piece.replace(piece)
    cues: list[list[tuple[float, float, str]]] | None = []
    for number, (task_id, piece) in enumerate(zip(tasks, files), start=1):
        vtt = piece.with_suffix(".vtt")
        try:
            if not vtt.is_file():
                if not task_id:
                    raise TTSError("sin tarea")
                api.download(api.subtitle(task_id), vtt)
            cues.append(parse_cues(vtt.read_text("utf-8", errors="replace")))
        except Exception as error:      # no subtitles: the align stage uses Whisper as always
            log(f"   Subtítulos de GenAIPro no disponibles ({str(error)[:120]}): se alineará con Whisper")
            cues = None
            break
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(".generando.mp3")
    if len(files) == 1:
        partial.write_bytes(files[0].read_bytes())
    else:                                       # one file, re-encoded so the joins are clean
        listing = work / "list.txt"
        listing.write_text("".join(f"file '{f.resolve()}'\n" for f in files), encoding="utf-8")
        done = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i",
                               str(listing), "-c:a", "libmp3lame", "-b:a", "192k", str(partial)],
                              capture_output=True, text=True)
        if done.returncode != 0:
            raise TTSError(f"No se pudieron unir los trozos de voz: {done.stderr[-200:]}")
    partial.replace(target)
    (target.parent / TIMINGS).unlink(missing_ok=True)
    if cues:
        try:
            write_timings(target, files, cues)
        except Exception as error:
            log(f"   No se pudieron guardar los tiempos de palabras ({str(error)[:120]}): se alineará con Whisper")
    import shutil

    shutil.rmtree(work, ignore_errors=True)
    return {"chars": sum(len(p) for p in parts), "pieces": len(parts), "tasks": tasks}


# --- word timings from the subtitles (instead of Whisper) ---------------------------------------------------------

_CUE_TIME = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})\s*-->\s*(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})")


def _seconds(h: str | None, m: str, s: str, ms: str) -> float:
    return int(h or 0) * 3600 + int(m) * 60 + int(s) + int(ms.ljust(3, "0")) / 1000


def parse_cues(text: str) -> list[tuple[float, float, str]]:
    """WebVTT or SRT → [(start, end, text)]."""

    cues = []
    for block in re.split(r"\n\s*\n", text.replace("\r", "")):
        lines = [l for l in block.strip().splitlines() if l.strip()]
        for i, line in enumerate(lines):
            found = _CUE_TIME.search(line)
            if found:
                g = found.groups()
                words = re.sub(r"<[^>]+>", "", " ".join(lines[i + 1:])).strip()
                if words:
                    cues.append((_seconds(*g[:4]), _seconds(*g[4:]), words))
                break
    return cues


def _duration(path: Path) -> float:
    done = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                          capture_output=True, text=True)
    return float(done.stdout.strip())


def _audio_id(path: Path) -> str:
    import hashlib

    digest = hashlib.sha1()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_timings(target: Path, files: list[Path], cues: list[list[tuple[float, float, str]]]) -> None:
    """voz.palabras.json: every spoken word with its time in voz.mp3 (each piece shifted by those before it); the
    words of a cue share its span by length. Tied to this voz.mp3 by its hash: another voice → Whisper."""

    words, offset = [], 0.0
    for piece, piece_cues in zip(files, cues):
        for start, end, text in piece_cues:
            tokens = text.split()
            total = sum(max(1, len(t)) for t in tokens)
            cursor = start
            for token in tokens:
                width = (end - start) * max(1, len(token)) / total
                words.append({"word": token, "start": round(offset + cursor, 3), "end": round(offset + cursor + width, 3)})
                cursor += width
        offset += _duration(piece)
    if not words:
        raise TTSError("subtítulos vacíos")
    data = {"source": "genaipro", "audio": _audio_id(target), "duration": round(_duration(target), 3), "words": words}
    (target.parent / TIMINGS).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def timings(audio: Path) -> dict[str, Any] | None:
    """The GenAIPro word timings of this voz.mp3 (as Whisper's {"words", "duration"}), if it has them."""

    try:
        data = json.loads((audio.parent / TIMINGS).read_text("utf-8"))
        if data.get("audio") == _audio_id(audio) and data.get("words"):
            return {"words": data["words"], "duration": float(data["duration"]), "language": "es"}
    except (OSError, ValueError, TypeError, KeyError):
        pass
    return None


def _lock_alive(lock: Path) -> bool:
    try:
        pid = int(lock.read_text().split()[0])
    except (OSError, ValueError, IndexError):
        return lock.is_file() and time.time() - lock.stat().st_mtime < WAIT_SECONDS
    if time.time() - lock.stat().st_mtime > WAIT_SECONDS * 2:       # a crash left it behind long ago
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _take(lock: Path) -> bool:
    """The right to make this narration (one process, one thread at a time)."""

    if lock.is_file() and not _lock_alive(lock):
        lock.unlink(missing_ok=True)
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w") as out:
        out.write(f"{os.getpid()} {time.strftime('%Y-%m-%dT%H:%M:%S')}\n")
    return True


def clear_own_locks(root: Path) -> None:
    """At the watcher's start: a lock with our own pid is from before a self-restart (exec keeps the pid)."""

    from .context import video_folders

    for folder in video_folders(root):
        lock = folder / LOCK
        try:
            if int(lock.read_text().split()[0]) == os.getpid():
                lock.unlink(missing_ok=True)
        except (OSError, ValueError, IndexError):
            pass


def generating(folder: Path) -> bool:
    return _lock_alive(folder / LOCK)


def ensure(ctx: Any, wait: bool = True) -> bool:
    """No voz.mp3, a script, and a voice for its channel → generate it. True if made here.

    While another thread or process is making it (the watcher's background), wait for it (`wait`) or return."""

    voice_file = ctx.materials_dir / "voz.mp3"
    script = ctx.materials_dir / "guion.txt"
    if voice_file.is_file() or not script.is_file():
        return False
    voice = voice_for(ctx.root, ctx.channel or "")
    if not voice:
        return False
    lock = ctx.materials_dir / LOCK
    while not _take(lock):
        if not wait:
            return False
        print("   La voz se está generando en segundo plano: espero a que acabe…")
        while _lock_alive(lock) and not voice_file.is_file():
            time.sleep(5)
        if voice_file.is_file():
            return False
    try:
        if voice_file.is_file():                 # made while we waited for the lock
            return False
        made = _make(ctx, voice, script, voice_file)
        (ctx.materials_dir / FAILED).unlink(missing_ok=True)
        return made
    except Exception as error:
        (ctx.materials_dir / FAILED).write_text(json.dumps(
            {"at": time.time(), "error": f"{type(error).__name__}: {str(error)[:300]}"}, ensure_ascii=False), encoding="utf-8")
        raise
    finally:
        lock.unlink(missing_ok=True)


def _make(ctx: Any, voice: dict[str, Any], script: Path, voice_file: Path) -> bool:
    text = narration_text(script.read_text("utf-8"))
    if str(ctx.section("align").get("language", "es")).startswith("es") and ctx.section("tts").get("numbers_in_words", True):
        from .numeros import spoken_numbers

        text = spoken_numbers(text)              # «413.240.000» read right; the graphics keep the digits
    print(f"Voz con GenAIPro ({voice.get('name') or voice['voice_id']}, {voice['model_id']}): {len(text)} caracteres")
    started = time.monotonic()
    result = generate(ctx.env("GENAIPRO_API_KEY", required=False), text, voice, voice_file)
    (ctx.materials_dir / "voz.genaipro.json").write_text(json.dumps(
        {"voice": voice, **result, "at": time.strftime("%Y-%m-%dT%H:%M:%S")}, ensure_ascii=False, indent=1), encoding="utf-8")
    try:
        from .costs import record_cost

        record_cost(ctx, stage="voz", provider="genaipro", operation=voice["model_id"],
                    usd=float(voice.get("usd_per_1k_chars", 0)) * result["chars"] / 1000,
                    details={"chars": result["chars"], "pieces": result["pieces"]})
    except Exception:
        pass
    print(f"   voz.mp3 lista en {time.monotonic() - started:.0f} s ({result['pieces']} trozo(s))")
    return True


def prepare_all(root: Path, log: Any = print) -> int:
    """The watcher's background: every video waiting in the queue whose narration GenAIPro has to make, made now
    (oldest first), not when its turn comes. Held videos («Quitar de la cola») and finished ones are left alone; a
    failure is retried after RETRY_MINUTES and told to Telegram once. Returns how many it made."""

    from .context import RunContext, video_folders

    if not voices(root):
        return 0
    try:
        check_credits(root, RunContext.create("_voces", root=root).env("GENAIPRO_API_KEY", required=False) or "")
    except Exception as error:                   # never stops the voices
        log(f"Créditos de GenAIPro: {type(error).__name__}: {str(error)[:150]}")
    made = 0
    materials = root / "materiales"
    for folder in sorted(video_folders(root), key=lambda d: d.stat().st_mtime):
        if any(part.startswith(("_", ".")) for part in folder.relative_to(materials).parts):
            continue
        if (folder / "voz.mp3").is_file() or (folder / ".en-espera").is_file() or not has_auto_voice(root, folder):
            continue
        try:
            failed = json.loads((folder / FAILED).read_text("utf-8"))
        except (OSError, ValueError):
            failed = None
        if failed and time.time() - float(failed.get("at") or 0) < RETRY_MINUTES * 60:
            continue
        from .housekeeping import is_done

        if is_done(root, folder.name) or generating(folder):
            continue
        try:
            ctx = RunContext.create(folder.name, root=root)
            from . import capitulos

            capitulos.ensure(ctx)                # the chapters first: you see them in the studio before the video
            if ensure(ctx, wait=False):
                made += 1
                log(f"Voz de {folder.name} lista (generada en segundo plano)")
        except Exception as error:
            log(f"Voz de {folder.name}: {type(error).__name__}: {str(error)[:200]}")
            if not failed:                       # one message per video, not one every half hour
                _tell(root, f"🎙️ No se pudo generar la voz de {folder.name} con GenAIPro:\n{str(error)[:300]}\n\n"
                            f"Lo reintento cada {RETRY_MINUTES} min.")
    return made


CREDITS_STATE = "out/_voces_creditos.json"
VIDEO_CHARS = 14000              # a 15-minute script, until real ones are measured (voz.genaipro.json)


def chars_per_video(root: Path) -> float:
    from .context import video_folders

    made = []
    for folder in video_folders(root):
        try:
            made.append(float(json.loads((folder / "voz.genaipro.json").read_text("utf-8"))["chars"]))
        except (OSError, ValueError, KeyError, TypeError):
            pass
    return sum(made) / len(made) if made else VIDEO_CHARS


def check_credits(root: Path, token: str, session: Any = None, now: float | None = None) -> dict[str, Any] | None:
    """Every hour: GenAIPro's credits; a Telegram message (once a day) when they cover fewer than
    `tts.min_videos` (5) narrations, so the queue does not run dry in the middle of the night."""

    now = time.time() if now is None else now
    path = root / CREDITS_STATE
    try:
        state = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        state = {}
    if now - float(state.get("checked") or 0) < 3600 or not token or not voices(root):
        return None
    from .context import RunContext

    cfg = RunContext.create("_voces", root=root).section("tts") if (root / "config.yaml").is_file() else {}
    rows = GenAIPro(token, session).credits()
    left = sum(float(r.get("amount") or 0) for r in (rows if isinstance(rows, list) else [rows]) if isinstance(r, dict))
    per_video = chars_per_video(root) * float(cfg.get("credits_per_char", 1.0))
    videos = left / per_video if per_video else 0
    state.update(checked=now, credits=left, videos=round(videos, 1))
    minimum = float(cfg.get("min_videos", 5))
    if videos < minimum and now - float(state.get("alerted") or 0) > 20 * 3600:
        state["alerted"] = now
        _tell(root, f"🎙️ Quedan {left:,.0f} créditos de GenAIPro: unas {videos:.0f} voces más "
                    f"(~{per_video:,.0f} por vídeo). Recarga antes de que la cola se quede sin voz.".replace(",", "."))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state), encoding="utf-8")
    return state


def _tell(root: Path, text: str) -> None:
    try:
        from .context import RunContext
        from .notify import telegram

        telegram(RunContext.create("_voces", root=root), text)
    except Exception:            # a message is never worth stopping anything for
        pass


def has_auto_voice(root: Path, folder: Path) -> bool:
    """A video without voz.mp3 that will get one generated (its channel has a voice)."""

    configured = voices(root)
    if not configured or not (folder / "guion.txt").is_file():
        return False
    from .web import _channel_of

    try:
        return _channel_of(root, folder) in configured
    except Exception:            # an unreadable config: the video simply waits for its voz.mp3
        return False
