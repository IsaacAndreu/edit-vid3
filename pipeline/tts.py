"""The narration made from the script with GenAIPro (Labs: ElevenLabs voices) instead of recording it.

- The key: GENAIPRO_API_KEY in .env (genaipro.io → avatar → Manage Account → API Key). Never in the repository.
- A voice per channel: studio → Ajustes → «Voces por canal» (out/_voces.json): the voice ID, the model and the
  settings. The studio also searches GenAIPro's voices and plays a test with a channel's voice.
- A video with its script and no voz.mp3, in a channel that has a voice, is in the queue like any other: before its
  first stage the narration is generated (main._run_one → ensure). A voz.mp3 you upload is always used as it is.
- The text is the script without the `## chapter` lines (they are not narrated) and without markdown marks. A long
  script goes in pieces of up to `max_chars` (cut at paragraphs, then sentences), joined into one mp3.
- API (docs.genaipro.io/openapi.yaml): POST /v1/labs/task → task_id; GET /v1/labs/task/{id} until status
  «completed» → result (the mp3's URL); GET /v1/labs/voices; GET /v1/labs/credits.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
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

    def _call(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = self.http.request(method, BASE + path, headers=self.headers, timeout=60, **kwargs)
        except requests.RequestException as error:
            raise TTSError(f"GenAIPro no responde ({type(error).__name__})") from error
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
            status = str(task.get("status") or "")
            if status == "completed" and task.get("result"):
                return str(task["result"])
            if status in ("failed", "error"):
                raise TTSError(f"GenAIPro: la tarea {task_id} falló ({str(task.get('error') or task)[:200]})")
            time.sleep(every)
        raise TTSError(f"GenAIPro: la tarea {task_id} no terminó en {timeout / 60:.0f} min")

    def download(self, url: str, target: Path) -> Path:
        try:
            with self.http.get(url, stream=True, timeout=300) as response:
                response.raise_for_status()
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("wb") as out:
                    for chunk in response.iter_content(1 << 16):
                        out.write(chunk)
        except requests.RequestException as error:
            raise TTSError(f"No se pudo bajar el audio de GenAIPro ({type(error).__name__})") from error
        return target


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
    """The whole text as one mp3 at `target`. Returns {"chars", "pieces", "tasks"}."""

    api = GenAIPro(token, session)
    parts = pieces(text, int(voice.get("max_chars", MAX_CHARS)))
    if not parts:
        raise TTSError("El guion está vacío")
    tasks = []
    with tempfile.TemporaryDirectory() as tmp:
        files = []
        for number, part in enumerate(parts, start=1):
            task_id = api.create(part, voice)
            tasks.append(task_id)
            log(f"   Voz {number}/{len(parts)}: {len(part)} caracteres → tarea {task_id}")
            url = api.wait(task_id)
            files.append(api.download(url, Path(tmp) / f"{number:03d}.mp3"))
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_suffix(".generando.mp3")
        if len(files) == 1:
            partial.write_bytes(files[0].read_bytes())
        else:                                   # one file, re-encoded so the joins are clean
            listing = Path(tmp) / "list.txt"
            listing.write_text("".join(f"file '{f}'\n" for f in files), encoding="utf-8")
            done = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i",
                                   str(listing), "-c:a", "libmp3lame", "-b:a", "192k", str(partial)],
                                  capture_output=True, text=True)
            if done.returncode != 0:
                raise TTSError(f"No se pudieron unir los trozos de voz: {done.stderr[-200:]}")
        partial.replace(target)
    return {"chars": sum(len(p) for p in parts), "pieces": len(parts), "tasks": tasks}


def ensure(ctx: Any) -> bool:
    """Before a video's first stage: no voz.mp3, a script, and a voice for its channel → generate it. True if made."""

    voice_file = ctx.materials_dir / "voz.mp3"
    script = ctx.materials_dir / "guion.txt"
    if voice_file.is_file() or not script.is_file():
        return False
    voice = voice_for(ctx.root, ctx.channel or "")
    if not voice:
        return False
    text = narration_text(script.read_text("utf-8"))
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
