"""The narration made from the script with AI84.pro (MiniMax voices; also its ElevenLabs ones) or GenAIPro (Labs:
ElevenLabs voices) instead of recording it.

- The keys: AI84_API_KEY (ai84.pro → API Document → API Key, a paid account) and/or GENAIPRO_API_KEY in .env. Never in
  the repository. Each channel's voice says which provider reads it (`provider`: ai84 | genaipro; older voices with
  none are GenAIPro's); a new voice is AI84's when its key is there (`tts.provider`).
- AI84 (api.ai84.pro, `xi-api-key`): MiniMax system voices (GET /v1/minimax/voices, each with its own sample to listen
  to for free) and cloned ones (GET /v1/minimax/voices/cloned); POST /v1/minimax/text-to-speech/async → job_id, GET
  …/async/{id} until «done» → audio_url. No word timings: the align stage uses Whisper. GET /v1/credits.
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
AI84_BASE = "https://api.ai84.pro"
# AI84's own price list (POST /v1/estimate-credit-cost, 12/11): the HD models 1.15 credits a character, turbo and 01 1.0
AI84_CREDITS_PER_CHAR = {"hd": 1.15, "turbo": 1.0}


def ai84_credits_per_char(model: str) -> float:
    hd = model != "speech-01-hd" and (model.endswith("-hd") or model.endswith("-hd-preview"))
    return AI84_CREDITS_PER_CHAR["hd" if hd else "turbo"]
FILE = "out/_voces.json"
MODELS = ("eleven_multilingual_v2", "eleven_turbo_v2_5", "eleven_flash_v2_5", "eleven_v3", "eleven_v4")
MINIMAX_MODELS = ("speech-2.6-hd", "speech-2.6-turbo", "speech-2.8-hd", "speech-2.8-turbo", "speech-02-hd", "speech-02-turbo",
                  "speech-2.5-hd-preview", "speech-2.5-turbo-preview", "speech-01-hd", "speech-01-turbo")
DEFAULTS = {"model_id": "eleven_multilingual_v2", "stability": 0.5, "similarity": 0.75, "style": 0.0, "speed": 1.0,
            "use_speaker_boost": True}
MINIMAX_DEFAULTS = {"provider": "ai84", "engine": "minimax", "model_id": "speech-2.6-hd", "speed": 1.0, "pitch": 0,
                    "volume": 1.0}
PROVIDERS = {"ai84": "AI84", "genaipro": "GenAIPro"}
# MiniMax reads a language better told which one it is (language_boost): the video's language
LANGUAGE_BOOST = {"es": "Spanish", "pt": "Portuguese", "en": "English", "de": "German", "fr": "French", "it": "Italian"}


def is_minimax(voice: dict[str, Any] | None) -> bool:
    return bool(voice) and voice.get("provider") == "ai84" and voice.get("engine", "minimax") == "minimax"


def with_defaults(voice: dict[str, Any]) -> dict[str, Any]:
    """A saved voice with its provider's defaults under it: a MiniMax voice never gets an ElevenLabs model."""

    return {**(MINIMAX_DEFAULTS if is_minimax(voice) else DEFAULTS), **voice}


def provider_name(voice: dict[str, Any] | None) -> str:
    return PROVIDERS.get(str((voice or {}).get("provider") or "genaipro"), "GenAIPro")
MAX_CHARS = 4500
WAIT_SECONDS = 1800
LOCK = ".voz.generando"          # in the video's folder while its narration is being made (pid, time)
FAILED = "voz.error.json"        # the last failure: the background retries it after RETRY_MINUTES
RETRY_MINUTES = 30
TIMINGS = "voz.palabras.json"    # word timings from GenAIPro's subtitles: the align stage skips Whisper with them
SUBTITLE_CHARS = 18              # short cues → each word's time is close (the cue's span shared by its words)


class TTSError(RuntimeError):
    pass


USD_PER_1K_CHARS = 0.022         # GenAIPro (Labs): 22 $ the million characters; tts.usd_per_1k_chars to change it


def voice_usd(ctx: Any, voice: dict[str, Any], chars: float, result: dict[str, Any]) -> float:
    """What a narration cost: AI84 by its credits (tts.ai84_usd_per_1k_credits; 0 until it is set: credits are what
    AI84 counts), GenAIPro by its characters."""

    if result.get("provider") == "ai84":
        try:
            rate = float(ctx.section("tts").get("ai84_usd_per_1k_credits", 0) or 0)
        except Exception:
            rate = 0.0
        return rate * float(result.get("credits") or 0) / 1000
    return usd_per_1k_chars(ctx, voice) * chars / 1000


def usd_per_1k_chars(ctx: Any, voice: dict[str, Any] | None = None) -> float:
    """What 1,000 narrated characters cost: the voice's own price, else tts.usd_per_1k_chars, else 0.022 $. The
    voices never carried one, so every narration was recorded at 0.00 $ (about 0.30 $ a 12-15 minute video)."""

    own = (voice or {}).get("usd_per_1k_chars")
    if own is not None:
        return float(own)
    try:
        return float(ctx.section("tts").get("usd_per_1k_chars", USD_PER_1K_CHARS))
    except Exception:
        return USD_PER_1K_CHARS


# --- voices per channel -----------------------------------------------------------------------------------------

def _read(root: Path) -> dict[str, Any]:
    try:
        data = json.loads((root / FILE).read_text("utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def voices(root: Path) -> dict[str, dict[str, Any]]:
    """channel → its voice settings ({} when the channel has none)."""

    return {c: with_defaults(v) for c, v in _read(root).items() if isinstance(v, dict) and v.get("voice_id") and not c.startswith("_")}


def voice_for(root: Path, channel: str) -> dict[str, Any] | None:
    """The channel's voice; a channel built on another (`base: gimnasia`) speaks with that one until it has its own."""

    from .context import base_channel

    configured = voices(root)
    if channel in configured:
        return configured[channel]
    parent = base_channel(root, channel) if channel else None
    return configured.get(parent) if parent else None


def voice_for_video(ctx: Any) -> dict[str, Any] | None:
    """The voice of this video: the channel's, or for a video in another language (align.language), the channel's
    voice for that language in «Doblaje» (else the channel's own with the multilingual model)."""

    lang = str(ctx.section("align").get("language", "es"))
    if lang.startswith("es"):
        return voice_for(ctx.root, ctx.channel or "")
    from .doblaje import settings

    from .context import base_channel

    spec = (settings(ctx)["voices"] or {}).get(lang) or {}
    if spec.get("voice_id"):
        return with_defaults(spec)
    channel = ctx.channel or ""
    if channel in voices(ctx.root):                      # the channel's own voice (gimnasia-br: its Brazilian voice)
        return voice_for(ctx.root, channel)
    parent = base_channel(ctx.root, channel) if channel else None
    spec = ((dubbing_for(ctx.root, parent).get("voices") or {}).get(lang) or {}) if parent else {}
    return with_defaults(spec) if spec.get("voice_id") else voice_for(ctx.root, channel)   # its base's «pt» voice


def set_voice(root: Path, channel: str, body: dict[str, Any]) -> dict[str, Any]:
    """From the studio: {voice_id, name?, model_id?, stability?, similarity?, style?, speed?}; voice_id "" removes it."""

    data = _read(root)
    if not str(body.get("voice_id") or "").strip():
        data.pop(channel, None)
    else:
        entry = {"voice_id": str(body["voice_id"]).strip(), "name": str(body.get("name") or "").strip()}
        provider = str(body.get("provider") or "genaipro")
        if provider not in PROVIDERS:
            raise ValueError(f"Proveedor desconocido: {provider}")
        if provider == "ai84":
            entry.update(provider="ai84", engine="elevenlabs" if body.get("engine") == "elevenlabs" else "minimax")
        minimax = is_minimax(entry)
        if body.get("model_id"):
            if body["model_id"] not in (MINIMAX_MODELS if minimax else MODELS):
                raise ValueError(f"Modelo desconocido: {body['model_id']}")
            entry["model_id"] = body["model_id"]
        ranges = (("speed", 0.5, 2.0), ("pitch", -12, 12), ("volume", 0.1, 10)) if minimax else \
            (("stability", 0, 1), ("similarity", 0, 1), ("style", 0, 1), ("speed", 0.7, 1.2))
        for key, low, high in ranges:
            if body.get(key) not in (None, ""):
                entry[key] = min(high, max(low, float(body[key])))
        if minimax and body.get("language_boost"):
            entry["language_boost"] = str(body["language_boost"])[:30]
        data[channel] = entry
    path = root / FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return voices(root)


DUB_KEY = "_dubbing"                 # in out/_voces.json: {channel: {languages, voices, existing, since}}
DUB_LANGUAGES = ("pt", "de", "fr", "en", "it")


def dubbing_for(root: Path, channel: str) -> dict[str, Any]:
    """The studio's «Doblaje» of a channel ({} when off): languages, a voice per language (optional) and whether the
    videos made before it was turned on are dubbed too."""

    entry = (_read(root).get(DUB_KEY) or {}).get(channel) or {}
    return entry if entry.get("languages") else {}


def set_dubbing(root: Path, channel: str, body: dict[str, Any]) -> dict[str, Any]:
    """{languages: [pt, de…], voices: {pt: {voice_id, name}}, existing: bool}; no languages turns it off."""

    import time as _time

    data = _read(root)
    every = data.setdefault(DUB_KEY, {})
    languages = [str(l) for l in body.get("languages") or [] if str(l) in DUB_LANGUAGES]
    if not languages:
        every.pop(channel, None)
    else:
        before = every.get(channel) or {}
        voices_in = body.get("voices") or {}
        every[channel] = {
            "languages": languages,
            "voices": {l: {"voice_id": str((voices_in.get(l) or {}).get("voice_id") or "").strip(),
                           "name": str((voices_in.get(l) or {}).get("name") or "").strip(),
                           **({"provider": "ai84", "engine": "minimax"}
                              if (voices_in.get(l) or {}).get("provider") == "ai84" else {})}
                       for l in languages if str((voices_in.get(l) or {}).get("voice_id") or "").strip()},
            "existing": bool(body.get("existing", True)),
            "since": before.get("since") or _time.time(),
        }
    path = root / FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return dubbing_for(root, channel)


# --- the API ------------------------------------------------------------------------------------------------------

class GenAIPro:
    NAME = "GenAIPro"
    subtitles = True
    spent = 0.0

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
                raise TTSError(f"No se pudo bajar el audio de {getattr(self, 'NAME', 'GenAIPro')} ({type(error).__name__})") from error


class AI84:
    """api.ai84.pro: MiniMax voices (system and cloned) and its ElevenLabs ones. Same face as GenAIPro for generate()."""

    NAME = "AI84"
    RETRIES = GenAIPro.RETRIES
    subtitles = False                  # MiniMax gives no word timings: the align stage uses Whisper

    def __init__(self, token: str, session: Any = None) -> None:
        if not token:
            raise TTSError("Falta AI84_API_KEY en .env (ai84.pro → API Document → API Key; hace falta una cuenta de pago)")
        self.http = session or requests.Session()
        self.headers = {"xi-api-key": token}
        self.spent = 0.0               # credits of the jobs finished through this client
        self.quoted: dict[str, float] = {}   # job → the credits quoted when it was made (MiniMax's poll does not say)
        self.unpriced: list[str] = []  # jobs finished with no known price (resumed after a restart): generate() estimates
        self.kind: dict[str, str] = {}  # job → "minimax" | "elevenlabs" (which endpoint to poll)

    def _call(self, method: str, path: str, **kwargs: Any) -> Any:
        """Reads are retried on network errors, 429 and 5xx (a 5xx while polling is a job still running); a POST
        that creates a job is never repeated blindly (it would be paid twice)."""

        waits = list(self.RETRIES) if method == "GET" else []
        while True:
            try:
                response = self.http.request(method, AI84_BASE + path, headers=self.headers, timeout=60, **kwargs)
            except requests.RequestException as error:
                if waits:
                    time.sleep(waits.pop(0))
                    continue
                raise TTSError(f"AI84 no responde ({type(error).__name__})") from error
            if waits and (response.status_code == 429 or response.status_code >= 500):
                wait = waits.pop(0)
                try:
                    wait = max(wait, float(getattr(response, "headers", {}).get("Retry-After") or 0))
                except ValueError:
                    pass
                time.sleep(min(wait, 120))
                continue
            break
        if response.status_code >= 400:
            try:
                detail = response.json()
                detail = detail.get("message") or detail.get("error") or detail
            except ValueError:
                detail = response.text[:200]
            hint = " (hace falta una cuenta de pago en AI84)" if response.status_code == 403 else ""
            raise TTSError(f"AI84 {response.status_code}: {str(detail)[:300]}{hint}")
        return response.json() if response.content else {}

    def credits(self) -> float:
        return float(self._call("GET", "/v1/credits").get("credits") or 0)

    def search(self, query: str = "", language: str = "", gender: str = "", page_size: int = 60) -> list[dict[str, Any]]:
        """MiniMax system voices (and, without a search, the cloned ones first) in one shape: voice_id, name, tags,
        description, preview_url (MiniMax's own sample: listening costs nothing)."""

        out: list[dict[str, Any]] = []
        if not query and not language and not gender:
            try:
                for v in self._call("GET", "/v1/minimax/voices/cloned").get("data") or []:
                    out.append({"voice_id": v.get("canonical_voice_id"), "name": v.get("name"), "cloned": True,
                                "tags": ["clonada" if not v.get("is_system_shared") else "compartida"],
                                "preview_url": v.get("demo_audio"), "description": "", "provider": "ai84", "engine": "minimax"})
            except TTSError:
                pass
        # the tags MiniMax gives are like ["Spanish", "male", "adult"]: the language goes as the tag, the gender is
        # checked here on the tags (one tag per call)
        tag = LANGUAGE_BOOST.get(language[:2], language) if language else gender
        params = {k: v for k, v in {"search": query, "tag": tag, "page": 1, "page_size": min(200, page_size)}.items() if v}
        for v in self._call("GET", "/v1/minimax/voices", params=params).get("data") or []:
            info = v.get("minimax_voice") or {}
            tags = [str(t) for t in info.get("tag_list") or []]
            if language and gender and any(t.lower() in ("male", "female") for t in tags) and gender.lower() not in (t.lower() for t in tags):
                continue
            # the TTS endpoint wants MiniMax's own id for a system voice («209539195289713»), not the named one
            # («Spanish_HumorousElder»: 404 VOICE_NOT_FOUND, tried on the server 12/11)
            out.append({"voice_id": info.get("voice_id") or v.get("canonical_voice_id"), "name": v.get("name") or info.get("voice_name"),
                        "tags": tags, "preview_url": info.get("sample_audio"),
                        "description": info.get("description") or "", "provider": "ai84", "engine": "minimax"})
        return [v for v in out if v["voice_id"]]

    def system_id(self, named: str) -> str:
        """MiniMax's own id of a system voice saved by its named id, "" when there is none."""

        try:
            found = self._call("GET", "/v1/minimax/voices", params={"search": named, "page_size": 20}).get("data") or []
        except TTSError:
            return ""
        for v in found:
            if v.get("canonical_voice_id") == named:
                return str((v.get("minimax_voice") or {}).get("voice_id") or "")
        return ""

    def create(self, text: str, voice: dict[str, Any]) -> str:
        if is_minimax(voice):
            body = {"canonical_voice_id": voice["voice_id"], "text": text, "model": voice.get("model_id") or MINIMAX_DEFAULTS["model_id"],
                    "speed": voice.get("speed", 1.0), "pitch": voice.get("pitch", 0), "volume": voice.get("volume", 1.0),
                    "format": "mp3", "sample_rate": 44100, "bitrate": 128000, "channel": 1}
            if voice.get("language_boost"):
                body["language_boost"] = voice["language_boost"]
            try:
                made = self._call("POST", "/v1/minimax/text-to-speech/async", json=body)
            except TTSError as error:
                # a voice saved with its named id (before 12/11): MiniMax's own id instead, found in the voice list
                own = self.system_id(voice["voice_id"]) if "VOICE_NOT_FOUND" in str(error) or "not found" in str(error).lower() else ""
                if not own or own == voice["voice_id"]:
                    raise
                made = self._call("POST", "/v1/minimax/text-to-speech/async", json={**body, "canonical_voice_id": own})
            kind = "minimax"
        else:
            body = {"text": text, "voice_id": voice["voice_id"], "model_id": voice.get("model_id") or DEFAULTS["model_id"],
                    "voice_settings": {"stability": voice.get("stability", 0.5), "similarity_boost": voice.get("similarity", 0.75),
                                       "style": voice.get("style", 0.0), "speed": voice.get("speed", 1.0),
                                       "use_speaker_boost": voice.get("use_speaker_boost", True)}}
            made = self._call("POST", "/v2/text-to-speech/async", json=body)
            kind = "elevenlabs"
        job = made.get("job_id") or made.get("task_id")
        if not job:
            raise TTSError(f"AI84 no devolvió el trabajo: {str(made)[:200]}")
        self.kind[str(job)] = kind
        if made.get("credit_cost") is not None:
            self.quoted[str(job)] = float(made["credit_cost"])
        return str(job)

    def wait(self, job_id: str, timeout: float = WAIT_SECONDS, every: float = 4.0) -> str:
        """The mp3's URL once the job is «done». Statuses: queued, processing, done, failed (anything else: keep
        waiting). A 200 can carry a failed job: always its status."""

        kind = self.kind.get(job_id)
        paths = [f"/v1/minimax/text-to-speech/async/{job_id}"] if kind == "minimax" else \
            [f"/v2/text-to-speech/async/{job_id}"] if kind == "elevenlabs" else \
            [f"/v1/minimax/text-to-speech/async/{job_id}", f"/v2/text-to-speech/async/{job_id}"]   # resumed after a restart
        ends = time.monotonic() + timeout
        while time.monotonic() < ends:
            job: dict[str, Any] = {}
            for path in paths:
                try:
                    job = self._call("GET", path).get("job") or {}
                except TTSError as error:
                    if " 404" in str(error) and len(paths) > 1:
                        continue
                    raise
                if job:
                    if len(paths) > 1:
                        paths = [path]
                    break
            status = str(job.get("status") or "").lower()
            url = job.get("audio_url") or job.get("audioUrl")
            if status == "done" and url:
                cost = job.get("credit_cost")
                cost = float(cost) if cost is not None else self.quoted.get(job_id)
                if cost is None:
                    self.unpriced.append(job_id)
                else:
                    self.spent += cost
                return str(url)
            if status in ("failed", "error"):
                message = job.get("errorMessage") or job.get("error_message") or "sin detalle"
                key = job.get("errorMessageKey") or job.get("error_message_key") or ""
                raise TTSError(f"AI84: el trabajo {job_id} falló: {message}" + (f" ({key})" if key else ""))
            time.sleep(every)
        raise TTSError(f"AI84: el trabajo {job_id} no terminó en {timeout / 60:.0f} min")

    def subtitle(self, task_id: str, timeout: float = 120, every: float = 3.0) -> str:
        raise TTSError("AI84 no da los tiempos de las palabras")

    def download(self, url: str, target: Path) -> Path:
        return GenAIPro.download(self, url, target)       # type: ignore[arg-type]


def keys(root: Path) -> dict[str, str]:
    """The voice keys in .env, by provider."""

    from .context import RunContext

    ctx = RunContext.create("_voces", root=root)
    return {"ai84": ctx.env("AI84_API_KEY", required=False), "genaipro": ctx.env("GENAIPRO_API_KEY", required=False)}


def default_provider(root: Path) -> str:
    """The provider a new voice is searched and saved with: tts.provider, else AI84 when its key is there."""

    try:
        from .context import RunContext

        asked = str(RunContext.create("_voces", root=root).section("tts").get("provider") or "")
    except Exception:
        asked = ""
    if asked in PROVIDERS:
        return asked
    return "ai84" if keys(root)["ai84"] or not keys(root)["genaipro"] else "genaipro"


def client_for(voice: dict[str, Any], token: str | dict[str, str], session: Any = None) -> GenAIPro | AI84:
    """The API that reads this voice. `token`: the keys by provider (keys()), or one GenAIPro key (older callers)."""

    provider = str(voice.get("provider") or "genaipro")
    key = token.get(provider, "") if isinstance(token, dict) else (token if provider == "genaipro" else "")
    return AI84(key, session) if provider == "ai84" else GenAIPro(key, session)


# --- the script → the narration ---------------------------------------------------------------------------------

HEADINGS = {"guion", "guión", "script", "texto", "locución", "locucion", "narración", "narracion"}
SECTION = re.compile(r"^\s*\[([^\]]+)\]\s*:?\s*$")
CHAPTER_TAG = re.compile(r"^\s*cap[ií]tulo\s*[\divxlc]*\s*[:.\-–—]?\s*", re.IGNORECASE)


def clean_script(script: str) -> str:
    """A script written for reading, made ready to narrate: «[CAPÍTULO 1 — QUIÉN ESTÁ DETRÁS — 1:00]» becomes the
    chapter «## Quién está detrás»; «[GANCHO — 0:00]», «[CTA SUSCRIPCIÓN — 5:20]», «[TRIVIA]», «[CIERRE]» and a
    «GUIÓN» heading go; notes inside the text («[VERIFICAR cifra de Ross]») go. GenAIPro read them aloud."""

    out: list[str] = []
    for line in script.splitlines():
        if line.strip().strip(":").casefold() in HEADINGS:
            continue
        section = SECTION.match(line)
        if section:
            parts = [x.strip() for x in re.split(r"\s+[—–-]\s+|\s*[—–]\s*", section.group(1)) if x.strip()]
            parts = [x for x in parts if not re.fullmatch(r"(aprox\.?\s*)?\d{1,2}:\d{2}(:\d{2})?", x, re.IGNORECASE)]
            if parts and CHAPTER_TAG.match(parts[0]):
                title = CHAPTER_TAG.sub("", parts[0]).strip() or (parts[1] if len(parts) > 1 else "")
                if title:
                    title = title if not title.isupper() else title[:1] + title[1:].lower()
                    out += ["", f"## {title}", ""]
            continue                                   # gancho, CTA, trivia, cierre: just marks for the writer
        out.append(re.sub(r"\s*\[[^\]]*\]", "", line).rstrip())
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip() + "\n"


def narration_text(script: str) -> str:
    """What is said: no `## chapter` lines, no markdown marks, paragraphs kept."""

    lines = []
    for line in clean_script(script).splitlines():
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


def generate(token: str | dict[str, str], text: str, voice: dict[str, Any], target: Path, session: Any = None,
             log: Any = print) -> dict[str, Any]:
    """The whole text as one mp3 at `target`. Returns {"chars", "pieces", "tasks"}.

    Each piece's task and audio are kept in `.voz-trozos/` next to `target` until the end: after a restart (or a
    failure half way) the pieces already made are reused, not paid again."""

    import hashlib

    api = client_for(voice, token, session)
    parts = pieces(text, int(voice.get("max_chars", MAX_CHARS)))
    if not parts:
        raise TTSError("El guion está vacío")
    work = target.parent / (".voz-trozos" if target.stem == "voz" else f".{target.stem}-trozos")
    work.mkdir(parents=True, exist_ok=True)
    state_file = work / "tareas.json"
    try:
        state = json.loads(state_file.read_text("utf-8"))
    except (OSError, ValueError):
        state = {}
    # the pieces' names: GenAIPro's as always (a narration half made before an update is not paid again)
    fields = ("voice_id", *MINIMAX_DEFAULTS, "language_boost") if voice.get("provider") == "ai84" else ("voice_id", *DEFAULTS)
    settings = json.dumps({k: voice.get(k) for k in fields}, sort_keys=True)
    tasks, files = [], []
    reused = 0
    for number, part in enumerate(parts, start=1):
        key = hashlib.sha1((settings + part).encode("utf-8")).hexdigest()[:16]
        piece = work / f"{key}.mp3"
        files.append(piece)
        if piece.is_file() and piece.stat().st_size > 0:
            log(f"   Voz {number}/{len(parts)}: ya hecha antes, la reutilizo")
            tasks.append(state.get(key, ""))
            reused += len(part)
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
        if task_id in getattr(api, "unpriced", []):     # resumed after a restart: its price by the characters
            api.spent += len(part) * ai84_credits_per_char(str(voice.get("model_id") or ""))
        log(f"   Voz {number}/{len(parts)}: lista, descargando")
        partial_piece = piece.with_suffix(".bajando")
        api.download(url, partial_piece)
        if partial_piece.stat().st_size == 0:
            raise TTSError(f"{getattr(api, 'NAME', 'GenAIPro')} devolvió un audio vacío (tarea {task_id})")
        partial_piece.replace(piece)
    timed = getattr(api, "subtitles", True)
    cues: list[list[tuple[float, float, str]]] | None = [] if timed else None
    for number, (task_id, piece) in enumerate(zip(tasks, files) if timed else [], start=1):
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
    timings_path(target).unlink(missing_ok=True)
    if cues:
        try:
            write_timings(target, files, cues)
        except Exception as error:
            log(f"   No se pudieron guardar los tiempos de palabras ({str(error)[:120]}): se alineará con Whisper")
    import shutil

    shutil.rmtree(work, ignore_errors=True)
    total = sum(len(p) for p in parts)
    # «chars» is the whole narration; only paidChars were generated (and billed) this time
    return {"chars": total, "paidChars": total - reused, "reusedChars": reused, "pieces": len(parts), "tasks": tasks,
            "provider": str(voice.get("provider") or "genaipro"), "credits": getattr(api, "spent", 0.0)}


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


def timings_path(audio: Path) -> Path:
    """voz.mp3 → voz.palabras.json; voz-en.mp3 (a dub's voice next to the original) → voz-en.palabras.json."""

    return audio.parent / (TIMINGS if audio.stem == "voz" else f"{audio.stem}.palabras.json")


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
    timings_path(target).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def timings(audio: Path) -> dict[str, Any] | None:
    """The GenAIPro word timings of this voz.mp3 (as Whisper's {"words", "duration"}), if it has them."""

    try:
        data = json.loads(timings_path(audio).read_text("utf-8"))
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
    voice = voice_for_video(ctx)
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
        from . import factcheck

        if factcheck.blocks_voice(ctx):          # an atlas: its facts checked before paying the narration
            wrong = factcheck.gate(ctx)
            if wrong:
                raise WrongFacts(ctx, wrong)
        made = _make(ctx, voice, script, voice_file)
        (ctx.materials_dir / FAILED).unlink(missing_ok=True)
        return made
    except Exception as error:
        (ctx.materials_dir / FAILED).write_text(json.dumps(
            {"at": time.time(), "error": f"{type(error).__name__}: {str(error)[:300]}"}, ensure_ascii=False), encoding="utf-8")
        raise
    finally:
        lock.unlink(missing_ok=True)


class WrongFacts(RuntimeError):
    """The fact check found claims of the script wrong: the narration waits for the script to be fixed (or for
    materiales/<vídeo>/.datos-ok, when you checked them yourself)."""

    def __init__(self, ctx: Any, wrong: list[dict[str, Any]]):
        lines = "\n".join(f"• «{(c.get('quote') or c.get('claim') or '')[:120]}»"
                          + (f" → {str(c['correction'])[:120]}" if c.get("correction") else "") for c in wrong[:6])
        super().__init__(f"{len(wrong)} dato(s) del guion parecen incorrectos; la voz espera a que corrijas guion.txt "
                         f"(o crea materiales/{ctx.slug}/.datos-ok si ya lo comprobaste):\n{lines}")


def _make(ctx: Any, voice: dict[str, Any], script: Path, voice_file: Path) -> bool:
    text = narration_text(script.read_text("utf-8"))
    if str(ctx.section("align").get("language", "es")).startswith("es") and ctx.section("tts").get("numbers_in_words", True):
        from .numeros import spoken_numbers

        text = spoken_numbers(text)              # «413.240.000» read right; the graphics keep the digits
    lang = str(ctx.section("align").get("language", "es"))[:2]
    if is_minimax(voice) and not voice.get("language_boost") and lang in LANGUAGE_BOOST:
        voice = {**voice, "language_boost": LANGUAGE_BOOST[lang]}
    print(f"Voz con {provider_name(voice)} ({voice.get('name') or voice['voice_id']}, {voice['model_id']}): {len(text)} caracteres")
    started = time.monotonic()
    result = generate(keys(ctx.root), text, voice, voice_file)
    (ctx.materials_dir / "voz.genaipro.json").write_text(json.dumps(
        {"voice": voice, **result, "at": time.strftime("%Y-%m-%dT%H:%M:%S")}, ensure_ascii=False, indent=1), encoding="utf-8")
    try:
        from .costs import record_cost

        paid = result.get("paidChars", result["chars"])     # a restart reuses pieces: they are not paid twice
        provider = result.get("provider", "genaipro")
        record_cost(ctx, stage="voz", provider=provider, operation=voice["model_id"], usd=voice_usd(ctx, voice, paid, result),
                    details={"chars": paid, "pieces": result["pieces"], "credits": result.get("credits", 0)})
        if result.get("reusedChars"):
            from .ahorro import record

            record(ctx.work_dir, "voice", result["reusedChars"])
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
        check_credits(root, keys(root))
    except Exception as error:                   # never stops the voices
        log(f"Créditos de voz: {type(error).__name__}: {str(error)[:150]}")
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
            from . import capitulos, formats

            if formats.ensure_auto(ctx):             # the format first: you see it in the studio before the video
                ctx = RunContext.create(folder.name, root=root)

            capitulos.ensure(ctx)                # the chapters first: you see them in the studio before the video
            if ensure(ctx, wait=False):
                made += 1
                log(f"Voz de {folder.name} lista (generada en segundo plano)")
        except Exception as error:
            log(f"Voz de {folder.name}: {type(error).__name__}: {str(error)[:200]}")
            if not failed:                       # one message per video, not one every half hour
                _tell(root, f"🎙️ No se pudo generar la voz de {folder.name}:\n{str(error)[:300]}\n\n"
                            f"Lo reintento cada {RETRY_MINUTES} min.", folder.name)
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


def credits_per_video(root: Path) -> float:
    """The AI84 credits a whole narration took (voz.genaipro.json of the videos read with it), 0 until one is made."""

    from .context import video_folders

    made = []
    for folder in video_folders(root):
        try:
            data = json.loads((folder / "voz.genaipro.json").read_text("utf-8"))
            if data.get("provider") == "ai84" and float(data.get("credits") or 0) > 0 and data.get("paidChars", data.get("chars")):
                made.append(float(data["credits"]) * float(data["chars"]) / float(data.get("paidChars") or data["chars"]))
        except (OSError, ValueError, KeyError, TypeError, ZeroDivisionError):
            pass
    return sum(made) / len(made) if made else 0.0


def check_credits(root: Path, token: str | dict[str, str], session: Any = None, now: float | None = None) -> dict[str, Any] | None:
    """Every hour: the voice credits (AI84's when a channel reads with it, else GenAIPro's); a Telegram message
    (once a day) when they cover fewer than `tts.min_videos` (5) narrations, so the queue does not run dry at night."""

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
    tokens = token if isinstance(token, dict) else {"genaipro": token}
    use_ai84 = any(v.get("provider") == "ai84" for v in voices(root).values()) and tokens.get("ai84")
    if use_ai84:
        name = "AI84"
        left = AI84(tokens["ai84"], session).credits()
        per_video = credits_per_video(root) or chars_per_video(root) * float(cfg.get("ai84_credits_per_char", 1.0))
    else:
        if not tokens.get("genaipro"):
            return None
        name = "GenAIPro"
        rows = GenAIPro(tokens["genaipro"], session).credits()
        left = sum(float(r.get("amount") or 0) for r in (rows if isinstance(rows, list) else [rows]) if isinstance(r, dict))
        per_video = chars_per_video(root) * float(cfg.get("credits_per_char", 1.0))
    videos = left / per_video if per_video else 0
    state.update(checked=now, credits=left, videos=round(videos, 1))
    minimum = float(cfg.get("min_videos", 5))
    if videos < minimum and now - float(state.get("alerted") or 0) > 20 * 3600:
        state["alerted"] = now
        _tell(root, f"🎙️ Quedan {left:,.0f} créditos de {name}: unas {videos:.0f} voces más "
                    f"(~{per_video:,.0f} por vídeo). Recarga antes de que la cola se quede sin voz.".replace(",", "."))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state), encoding="utf-8")
    return state


def _tell(root: Path, text: str, slug: str = "") -> None:
    try:
        from .context import RunContext
        from .notify import telegram

        telegram(RunContext.create(slug or "_voces", root=root), text)     # a video's: to its owner
    except Exception:            # a message is never worth stopping anything for
        pass


def has_auto_voice(root: Path, folder: Path) -> bool:
    """A video without voz.mp3 that will get one generated (its channel has a voice)."""

    configured = voices(root)
    if not configured or not (folder / "guion.txt").is_file():
        return False
    from .web import _channel_of

    try:
        return voice_for(root, _channel_of(root, folder)) is not None
    except Exception:            # an unreadable config: the video simply waits for its voz.mp3
        return False
