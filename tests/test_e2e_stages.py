"""End to end: `run_stages` with the REAL `STAGES` list over a tiny footage video (a few shots, ~35 s of voice).

17-11: a NameError in the «apertura» code stopped 11 videos after 3.5-7 h of work each, and tests/test_runner.py patches
the stages with fakes, so no test ever went through that line. Here every stage runs its own code from the first to the
last one; only the outside world is replaced, at its entry points:

- LLM / OpenAI: `openai.OpenAI` (chat completions of pipeline/llm.py, the vision judge, the moment check, the final
  review, GPT Image, Whisper by API). The fake answers each prompt by its system text (or its JSON schema name).
- YouTube: the yt-dlp extraction (`YouTubeSource._extract`: searches and video details), the HD/360p/audio ranges
  (`_download_range`, real small mp4/m4a made with ffmpeg), whole downloads, subtitles (`subtitle_file`, a VTT);
  storyboard sheets, json3 captions and the YouTube Data API (pipeline/ytapi.py) go through the HTTP double.
- HTTP (`requests.Session.request`): Pexels, Serper (Google Images), Wikimedia/Openverse, Wikipedia, image and video
  files, face models. Any other host answers a connection error; and a socket guard fails any connection that does
  not go through these doubles (yt-dlp, urllib…), so nothing here touches the network.
- TTS: not reached by the footage pipeline (the voice is materiales/<slug>/voz.mp3, made here with ffmpeg).
- Remotion: `Renderer.remotion` / `Renderer.stills` write what `npx remotion` would (an mp4 of the right size and
  length, PNG/JPEG sequences, a wav) with ffmpeg/Pillow.
- Heavy local ML that is not installed here: CLIP (`ClipScorer._load/embed_*`), RapidOCR, OpenCV's YuNet/SFace face
  models (`cv2.FaceDetectorYN` / `cv2.FaceRecognizerSF`), rembg and faster-whisper (fake modules).
- Rate limits (Pacer.wait, the shared YouTube pacer) do not sleep: they only pace real servers.

Several scenarios walk the different branches of «apertura», coldopen (moments, sound bites, quotes, official channels),
fallback (next option, protagonist, event footage, second search, web photo, Pexels, protagonist filler, protagonist
photo, title cards) and shorts (off, native, native failing → blurred, blurred, «nuevo»). `test_apertura_requests_*`
runs the studio's own opening search (`apertura.run_request`, what `main.py --apertura` does) for the branches that the
pipeline never reaches by itself (a YouTube link, an uploaded file).

Nothing is skipped. The only parts that cannot run here are the ones whose engine is the outside world itself
(Chromium/Remotion rendering, the ML models' weights, the network); their callers all run.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import types
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import cv2
import numpy as np
import pytest
import requests

ROOT = Path(__file__).resolve().parents[1]
SLUG = "yulo"
PERSON = "Carlos Yulo"

SCRIPT = """Carlos Yulo creció en Manila, al lado de un gimnasio. Su abuelo lo llevaba cada tarde.
## LOS PRIMEROS AÑOS
Con siete años ya hacía piruetas en el suelo. A los catorce se fue a entrenar a Japón.
Allí aprendió la disciplina que le cambiaría la vida.
## EL ORO DE PARÍS
En París 2024 salió al suelo con todo el país mirando. Clavó cada salto y ganó el oro.
Días después volvió a ganar en salto. Dos oros en unos mismos Juegos.
Filipinas entera salió a la calle a celebrarlo.
"""
# the videos without original sound moments (those need a sentence past the 30th second) are shorter: quicker
SHORT_SCRIPT = """Carlos Yulo creció en Manila, al lado de un gimnasio.
## EL ORO DE PARÍS
En París 2024 ganó dos oros. Filipinas entera salió a celebrarlo.
"""
TITLE = "Carlos Yulo: de Manila al oro de París"
SAID = "I never stopped believing in myself and today I proved it to everyone"
WORD_SECONDS, SENTENCE_PAUSE = 0.38, 0.35


# --- small real media made with ffmpeg / OpenCV ------------------------------------------------------------------


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True, capture_output=True)


def _pattern(seed: int, w: int, h: int) -> np.ndarray:
    """A picture of its own for every source (the pHash de-duplication must see different clips)."""

    rng = np.random.default_rng(seed)
    small = rng.integers(0, 255, (9, 16, 3), dtype=np.uint8)
    return cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)     # flat blocks: cheap to encode


def _jpeg(seed: int, w: int, h: int) -> bytes:
    return cv2.imencode(".jpg", _pattern(seed, w, h), [cv2.IMWRITE_JPEG_QUALITY, 80])[1].tobytes()


def _seed(text: str) -> int:
    return int(hashlib.sha1(text.encode()).hexdigest()[:8], 16)


def make_clip(path: Path, seconds: float, *, w: int = 1280, h: int = 720, seed: int = 0, audio: bool = True,
              audio_only: bool = False) -> Path:
    """A moving picture (so it is not «frozen») with a sound that has a loud moment (the sound bites look for one)."""

    path.parent.mkdir(parents=True, exist_ok=True)
    seconds = max(0.5, seconds)
    sound = ["-f", "lavfi", "-i", f"aevalsrc='0.08*sin(2*PI*330*t)*(1+8*between(mod(t,4),1.0,2.2))':s=48000:d={seconds:.3f}"]
    if audio_only:
        _ffmpeg(*sound, "-c:a", "aac", "-b:a", "64k", str(path))
        return path
    still = path.with_name(path.stem + ".pattern.png")
    cv2.imwrite(str(still), _pattern(seed, w + 64, h + 36))
    picture = ["-loop", "1", "-framerate", "30", "-t", f"{seconds:.3f}", "-i", str(still)]
    move = f"crop={w}:{h}:x='32+30*sin(t*2)':y='18+16*cos(t*2)',format=yuv420p"
    _ffmpeg(*picture, *(sound if audio else []), "-vf", move, "-r", "30", "-c:v", "libx264", "-preset", "ultrafast",
            "-crf", "30", *(["-c:a", "aac", "-b:a", "64k", "-shortest"] if audio else ["-an"]), "-t", f"{seconds:.3f}",
            str(path))
    still.unlink(missing_ok=True)
    return path


# --- the catalogue of YouTube videos of this little world --------------------------------------------------------


@dataclass
class Video:
    id: str
    title: str
    channel: str
    duration: int


def catalogue(official: bool) -> list[Video]:
    videos = [
        Video("yuloFloor01", "Carlos Yulo floor final Paris 2024 gold", "Olympics", 240),
        Video("yuloVault02", "Carlos Yulo vault final Paris 2024", "Olympics", 200),
        Video("yuloManila3", "Carlos Yulo Manila parade 2024 homecoming", "ABS-CBN News", 300),
        Video("yuloJapan04", "Carlos Yulo training in Japan documentary", "Gymnastics Stories", 420),
        Video("yuloInterv5", "Carlos Yulo interview after Paris 2024 gold", "Olympics", 180),
        Video("yuloStutt06", "Carlos Yulo Stuttgart 2019 world championships floor", "FIG Gymnastics", 260),
        Video("yuloKids007", "Carlos Yulo childhood gym Manila", "GMA News", 220),
        Video("yuloRings09", "Carlos Yulo rings and parallel bars 2023 Antwerp", "World Gymnastics TV", 280),
        Video("yuloPodiu10", "Carlos Yulo podium ceremony Paris 2024", "Olympics", 190),
        Video("yuloTrail08", "Carlos Yulo Paris 2024 official trailer", "Olympics" if official else "Fan Edits", 150),
    ]
    return videos


# --- LLM answers, by the system prompt they get --------------------------------------------------------------------


def _numbered(user: str) -> list[tuple[int, float, str]]:
    """«[3] (12s) text» / «[3] (12.0-15.1s) text» / «[3] text» lines → (n, start, text)."""

    out = []
    for line in user.splitlines():
        found = re.match(r"\[(\d+)\]\s*(?:\(([\d:.]+)(?:-[\d.]+)?s?\))?\s*(?:★\s*)?(.*)", line.strip())
        if found:
            stamp = found.group(2) or "0"
            seconds = sum(float(p) * 60 ** i for i, p in enumerate(reversed(stamp.split(":"))))
            out.append((int(found.group(1)), seconds, found.group(3)))
    return out


TOPICS = ["floor final", "vault", "Manila parade", "training Japan", "podium ceremony", "rings Antwerp", "childhood gym",
          "Stuttgart floor", "interview gold"]


def _broll(intent: str, n: int = 0, entities: list[str] | None = None) -> dict[str, Any]:
    topic = TOPICS[n % len(TOPICS)]
    return {"visualIntent": intent, "queriesEn": [f"Carlos Yulo {topic}", f"Carlos Yulo {TOPICS[(n + 3) % len(TOPICS)]}",
                                                  "Paris 2024 gymnastics"],
            "queriesEs": ["Carlos Yulo gimnasia"], "entities": entities if entities is not None else [PERSON],
            "mustContain": ["gymnast"], "avoid": ["talking head"], "preferredShot": "action", "moment": None}


class Brain:
    """The LLM of this world. Every prompt it does not know is written down (the test shows them)."""

    def __init__(self, scenario: "Scenario") -> None:
        self.s = scenario
        self.unknown: list[str] = []
        self.calls: dict[str, int] = {}
        self.lock = threading.Lock()

    def _count(self, name: str) -> None:
        with self.lock:
            self.calls[name] = self.calls.get(name, 0) + 1

    def chat(self, system: str, user: str) -> dict[str, Any]:
        from pipeline import (agrupar, apertura, coldopen, factcheck, fallback, graphics, package, planner, publish, quotes,
                              shorts, timeline)

        table = [
            (agrupar.SYSTEM, self.ideas),
            (planner.OUTLINE_SYSTEM, self.outline), (planner.LABEL_SYSTEM, self.label),
            (planner.PACING_SYSTEM, lambda u: {"slow": [], "fast": [5]}), (planner.LOW_SYSTEM, lambda u: {"low": []}),
            (factcheck.EXTRACT_SYSTEM, self.claims), (factcheck.JUDGE_SYSTEM, self.verdicts),
            (coldopen.MOMENTS_SYSTEM, self.moments), (quotes.QUOTES_SYSTEM, self.quotes),
            (quotes.TRANSLATE_SYSTEM, lambda u: {"text": "Nunca dejé de creer en mí y hoy lo he demostrado a todos"}),
            (apertura.PLAN_SYSTEM, self.plan), (apertura.PICK_SYSTEM, self.pick), (apertura.TRANSLATE_SYSTEM, self.lines),
            (shorts.SYSTEM, self.shorts), (shorts.NEW_SYSTEM, self.new_shorts), (fallback.RESEARCH_SYSTEM, self.research),
            (graphics.SYSTEM, self.graphics), (timeline.MUSIC_SYSTEM, self.music), (package.SYSTEM, self.titles),
            (publish.SYSTEM, self.publish),
        ]
        for prompt, answer in table:
            head = prompt.split("{")[0][:70]
            if system.startswith(head):
                self._count(answer.__name__ if hasattr(answer, "__name__") else head[:20])
                if self.s.llm_fails and answer.__name__ in self.s.llm_fails:
                    raise RuntimeError(f"LLM caído ({answer.__name__})")
                return answer(user)
        self.unknown.append(system[:90])
        return {}

    # planner
    def outline(self, user: str) -> dict[str, Any]:
        return {"context": "Carlos Yulo, Filipino gymnast, Manila and Paris 2024 Olympics, competition footage",
                "chapters": [], "subject": f"{PERSON} · artistic gymnastics",
                "peak": "Carlos Yulo Paris 2024 floor gold medal winning moment",
                "roles": {PERSON: "Gimnasta filipino", "Aldrin Yulo": "Su abuelo"},
                "events": [{"sentence": 0, "label": "Carlos Yulo childhood Manila gym", "tag": "MANILA", "place": None},
                           {"sentence": 5, "label": "Carlos Yulo Paris 2024 floor final", "tag": "PARÍS · 2024", "place": None}]}

    def label(self, user: str) -> dict[str, Any]:
        shots = json.loads(user.split("PLANOS:\n", 1)[1].split("\n\nRESPONDE", 1)[0])
        out = []
        for n, shot in enumerate(shots):
            item: dict[str, Any] = {"id": shot["id"], "type": "broll", "broll": _broll(f"floor routine {n}", n)}
            if shot.get("chapterTitle"):
                item["type"] = "chapter"
            elif "2024" in shot["text"] and not any(o.get("type") == "stat" for o in out):
                item.update(type="stat", stat={"value": "2024", "label": "París", "sign": "positive"})
            elif n == 2:
                item["broll"] = {**_broll("Manila streets", n), "moment": "spins on the floor"}
                item["rotulo"] = {"tipo": "nombre", "texto": PERSON}
            out.append(item)
        return {"shots": out}

    def ideas(self, user: str) -> dict[str, Any]:
        """planner.ideas: one idea per shot, the last a title read aloud, the rest literal (only the one with a narrated
        moment stays literal: agrupar.assign downgrades the others to ambient)."""

        ids = re.findall(r"^(s\d{3,4}) \(", user.split("PLANOS:\n", 1)[1], re.M)
        pairs = [[i] for i in ids]                         # one shot per idea: the short script has only four
        kinds = ["literal"] * max(0, len(pairs) - 1) + (["rotulo"] if len(pairs) > 1 else [])
        return {"ideas": [{"shots": pair, "kind": kind, "mustShow": [PERSON], "era": "Paris 2024",
                           "screenLine": "Oro en París"} for pair, kind in zip(pairs, kinds)]}

    # factcheck
    def claims(self, user: str) -> dict[str, Any]:
        return {"people": [PERSON], "wikipedia": ["Carlos Yulo"],
                "claims": [{"quote": "Dos oros", "claim": "Carlos Yulo ganó dos oros en París 2024",
                            "query": "Carlos Yulo two gold medals Paris 2024"}]}

    def verdicts(self, user: str) -> dict[str, Any]:
        return {"results": [{"n": 1, "verdict": "ok", "correction": None, "evidence": "Ganó suelo y salto",
                             "source": "https://en.wikipedia.org/wiki/Carlos_Yulo"}]}

    # coldopen
    def moments(self, user: str) -> dict[str, Any]:
        late = [n for n, start, _ in _numbered(user) if start >= 28]           # past the 30th second, 60 s apart
        return {"moments": [{"sentence": n} for n in late[-2:]] + [{"sentence": "nada"}, {"sentence": 0}]}

    def quotes(self, user: str) -> dict[str, Any]:
        sentences = _numbered(user)
        return {"quotes": [{"sentence": sentences[-2][0], "speaker": PERSON, "role": "gimnasta", "said_es": "Nunca dejé de creer",
                            "language": "en", "said_original": SAID, "search": "Carlos Yulo interview Paris 2024"},
                           {"sentence": 99, "speaker": "Nadie", "said_original": "x", "search": "x"}]}

    # apertura
    def plan(self, user: str) -> dict[str, Any]:
        said = SAID if self.s.apertura_said else ""
        return {"about": "Carlos Yulo diciendo que nunca dejó de creer", "speaker": PERSON, "role": "Gimnasta",
                "language": "en", "said": said, "searches": ["Carlos Yulo interview Paris 2024", "Carlos Yulo speech"]}

    def pick(self, user: str) -> dict[str, Any]:
        self.s.picks += 1
        answers = self.s.pick_answers or [{"found": True, "start": 11.0, "end": 19.5, "why": "lo dice"}]
        return answers[(self.s.picks - 1) % len(answers)]

    def lines(self, user: str) -> dict[str, Any]:
        lines = [l for l in user.splitlines() if l.strip()]
        return {"lines": [f"(es) {l}" for l in lines]}

    # shorts
    def shorts(self, user: str) -> dict[str, Any]:
        sentences = _numbered(user)
        last = sentences[-1][0]
        return {"shorts": [{"from": "x", "to": 2}, {"from": 0, "to": last // 2, "hook": "De *Manila* al oro", "title": "Yulo, de Manila al oro",
                            "description": "Su historia. #gimnasia #yulo #paris2024"},
                           {"from": last // 2 + 1, "to": last, "hook": "Dos oros en *París*", "title": "Dos oros",
                            "description": "París 2024. #gimnasia #oro #yulo"}]}

    def new_shorts(self, user: str) -> dict[str, Any]:
        text = ("Carlos Yulo creció al lado de un gimnasio en Manila. " * 9).strip()
        return {"shorts": [{"script": text, "title": "Yulo, de Manila al oro", "hook": "¿Cómo llegó al *oro*?",
                            "description": "Su historia. #gimnasia"},
                           {"script": "Demasiado corto.", "title": "No", "hook": "No", "description": ""}]}

    # timeline, package
    def graphics(self, user: str) -> dict[str, Any]:
        late = [n for n, start, _ in _numbered(user) if start >= 21]
        if not late:
            return {"graphics": []}
        return {"graphics": [{"type": "press", "from": late[0], "to": late[0], "data": {"items": [
            {"outlet": None, "headline": "Dos oros en unos mismos Juegos", "date": "2024", "highlight": "Dos oros"}]}}]}

    def music(self, user: str) -> dict[str, Any]:
        return {"moods": ["epica"] * len(_numbered(user))}

    def titles(self, user: str) -> dict[str, Any]:
        return {"titles": ["Carlos Yulo: de Manila al oro", "Dos oros en París", "El niño del gimnasio de Manila"],
                "thumbTexts": ["DOS OROS", "DE MANILA A PARÍS", "NADIE LO VIO VENIR"],
                "concepts": [{"scene": "a golden medal on a gym floor", "text": "DOS OROS", "side": "left"}]}

    def publish(self, user: str) -> dict[str, Any]:
        return {"description": "La historia de Carlos Yulo.", "tags": ["Carlos Yulo", "gimnasia"],
                "pinnedComment": "¿Quién es el mejor?", "communityPost": "Nuevo vídeo. ¿Lo sabías? Sí / No"}

    # fallback
    def research(self, user: str) -> dict[str, Any]:
        return {"queries": ["Carlos Yulo podium Paris 2024", "Carlos Yulo celebration Paris"]}


def verdict_for(scenario: "Scenario", prompt: str, letters: str) -> dict[str, Any]:
    accept = scenario.judge == "accept" or (scenario.judge == "mixed" and _seed(prompt) % 3 != 0)
    candidates = [{"letter": l, "shows": "a gymnast on the floor", "screenOrText": False, "onTopic": accept} for l in letters]
    return {"candidates": candidates, "ranking": list(letters) if accept else [], "score": 0.8 if accept else 0.1,
            "reason": "the athlete competing" if accept else "another athlete", "confidence": 0.9}


# --- the fake OpenAI client ----------------------------------------------------------------------------------------


class _Obj(types.SimpleNamespace):
    def model_dump(self) -> dict[str, Any]:
        return json.loads(json.dumps(self, default=lambda o: o.__dict__))


class FakeOpenAI:
    world: "World"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        world = FakeOpenAI.world
        self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=self._chat))
        self.responses = types.SimpleNamespace(create=self._responses)
        self.images = types.SimpleNamespace(generate=self._image, edit=self._image)
        self.audio = types.SimpleNamespace(transcriptions=types.SimpleNamespace(create=self._whisper))
        self.world = world

    def _chat(self, *, model: str, messages: list[dict[str, Any]], **kwargs: Any) -> Any:
        system = next(m["content"] for m in messages if m["role"] == "system")
        user = next(m["content"] for m in messages if m["role"] == "user")
        answer = self.world.brain.chat(system, user)
        usage = _Obj(prompt_tokens=1000, completion_tokens=200, prompt_cache_hit_tokens=0)
        return _Obj(usage=usage, choices=[_Obj(finish_reason="stop", message=_Obj(content=json.dumps(answer)))])

    def _responses(self, *, model: str, input: list[dict[str, Any]], text: dict[str, Any], **kwargs: Any) -> Any:
        name = text["format"]["name"]
        prompt = next(part["text"] for part in input[0]["content"] if part["type"] == "input_text")
        world = self.world
        if name == "shot_verdict":
            letters = re.search(r"Candidates on the sheet: ([A-Z, ]+)\.", prompt).group(1).replace(" ", "").split(",")
            answer = verdict_for(world.s, prompt, "".join(letters))
        elif name == "moment_check":
            answer = {"competition": world.s.competition, "why": "live floor final" if world.s.competition else "an interview"}
        elif name == "review":
            answer = {"problems": []}
        elif name == "scene_log":                    # the material's scene index (pipeline/indice.py)
            count = int(re.search(r"(\d+) scenes", prompt).group(1))
            answer = {"scenes": [{"n": n + 1, "en": "Carlos Yulo floor routine in the Manila gym",
                                  "es": "suelo, gimnasio, Manila"} for n in range(count)]}
        else:
            world.brain.unknown.append(f"responses:{name}")
            answer = {}
        world.brain._count(f"vision:{name}")
        usage = _Obj(input_tokens=2000, output_tokens=300, input_tokens_details=_Obj(cached_tokens=0))
        return _Obj(usage=usage, output_text=json.dumps(answer))

    def _image(self, *, model: str, prompt: str, **kwargs: Any) -> Any:
        png = cv2.imencode(".png", _pattern(_seed(prompt), 1536, 1024))[1].tobytes()
        self.world.brain._count("image")
        return _Obj(data=[_Obj(b64_json=base64.b64encode(png).decode())], usage=_Obj(input_tokens=100, output_tokens=1000))

    def _whisper(self, *, model: str, file: Any, **kwargs: Any) -> Any:
        return _Obj(**self.world.voice_transcript())


# --- HTTP: every host this pipeline talks to ------------------------------------------------------------------------


def _response(url: str, status: int = 200, content: bytes = b"", data: Any = None) -> requests.Response:
    response = requests.Response()
    response.status_code = status
    response._content = json.dumps(data).encode() if data is not None else content
    response._content_consumed = True                 # streamed reads (iter_content) come from _content
    response.url = url
    response.encoding = "utf-8"
    response.headers["Content-Type"] = "application/json" if data is not None else "application/octet-stream"
    response.reason = "OK" if status < 400 else "ERR"
    return response


# --- the scenario and the world -------------------------------------------------------------------------------------


@dataclass
class Scenario:
    name: str
    judge: str = "accept"                       # accept | reject | mixed
    official: bool = False                      # content.official_channels has the trailer's channel
    competition: bool = True                    # the moment check's answer
    fail_hd: str = ""                           # "" | "some" (half the videos) | "all": HD downloads refused
    fail_audio: bool = False                    # the downloads with sound (moments, quotes, opening) refused
    moments: int = 1
    sound_bites: int = 0
    quotes: int = 0
    apertura: str = "none"                      # none | auto | youtube | file | broken | auto-empty
    apertura_said: bool = True                  # the plan knows the words → matched in the transcript; else LLM pick
    pick_answers: list[dict[str, Any]] = field(default_factory=list)
    shorts: str = "off"                         # off | native | blur | native-fails | nuevo
    pexels: bool = False                        # fallback.pexels_for_person + a Pexels key
    serper: bool = True                         # web photos (Google Images through Serper)
    youtube_api: bool = False                   # searches through the YouTube Data API
    llm_fails: tuple[str, ...] = ()             # prompts whose call fails (the stage must survive it)
    no_subtitles: bool = False                  # videos without subtitles: faster-whisper over their audio
    endscreen: float = 0                        # the YouTube end screen (its own segment, cached across videos)
    subtitles: bool = False                     # burnt-in subtitles: one more pass over the whole video
    captions: bool = False                      # the broadcasts' captions name the athlete (identity confirmed)
    grade: bool = False                         # the colour grade of every clip (one more filter on each)
    script: str = SCRIPT
    extra: dict[str, Any] = field(default_factory=dict)
    own_clip: bool = False                      # a clip of your own in the material de partida (pipeline/material.py)
    picks: int = 0


REFUSED = {"yuloFloor01", "yuloJapan04", "yuloStutt06", "yuloRings09", "yuloVault02"}     # fail_hd: "some"


class World:
    def __init__(self, scenario: Scenario, root: Path) -> None:
        self.s = scenario
        self.root = root
        self.brain = Brain(scenario)
        self.videos = {v.id: v for v in catalogue(scenario.official)}
        self.downloads: list[tuple[str, str]] = []
        self.remotion: list[str] = []
        self.http: list[str] = []
        self.blocked_http: list[str] = []
        self.lock = threading.Lock()
        self.file_locks: dict[str, threading.Lock] = {}

    # voice
    def voice_words(self) -> list[tuple[str, float, float]]:
        words, t = [], 0.3
        for line in self.s.script.splitlines():
            for token in line.removeprefix("## ").split():
                words.append((token, t, t + WORD_SECONDS - 0.04))
                t += WORD_SECONDS + (SENTENCE_PAUSE if token.endswith(".") else 0)
        return words

    def voice_seconds(self) -> float:
        return self.voice_words()[-1][2] + 0.8

    def voice_transcript(self) -> dict[str, Any]:
        return {"duration": self.voice_seconds(), "language": "spanish",
                "words": [{"word": w, "start": a, "end": b} for w, a, b in self.voice_words()]}

    # YouTube
    def search_results(self, query: str) -> list[Video]:
        words = set(query.lower().split()) - {"carlos", "yulo"}
        pool = sorted(self.videos.values(), key=lambda v: (-len(words & set(v.title.lower().split())), _seed(query + v.id)))
        return pool[:6]

    def info(self, vid: str) -> dict[str, Any]:
        video = self.videos[vid]
        interval, columns, rows = 5.0, 5, 5
        frames = int(video.duration / interval)
        sheets = -(-frames // (columns * rows))
        far = int(time.time()) + 6 * 3600
        return {
            "id": vid, "title": video.title, "channel": video.channel, "uploader": video.channel,
            "duration": video.duration, "width": 1920, "height": 1080, "license": None, "live_status": "not_live",
            "formats": [
                {"format_id": "sb0", "protocol": "mhtml", "vcodec": "none", "acodec": "none", "width": 160, "height": 90,
                 "columns": columns, "rows": rows, "fps": 1 / interval,
                 "fragments": [{"url": f"https://i.ytimg.com/sb/{vid}/storyboard3_L2/M{k}.jpg"} for k in range(sheets)]},
                {"format_id": "136", "protocol": "https", "vcodec": "avc1.4d401f", "acodec": "none", "width": 1280,
                 "height": 720, "fps": 30, "filesize": 9_000_000, "url": f"https://rr1.googlevideo.com/videoplayback?expire={far}&id={vid}"},
                {"format_id": "137", "protocol": "https", "vcodec": "avc1.640028", "acodec": "none", "width": 1920,
                 "height": 1080, "fps": 30, "filesize": 18_000_000, "url": f"https://rr1.googlevideo.com/videoplayback?expire={far}&id={vid}"},
                {"format_id": "140", "protocol": "https", "vcodec": "none", "acodec": "mp4a.40.2", "abr": 128,
                 "url": f"https://rr1.googlevideo.com/videoplayback?expire={far}&id={vid}&a=1"},
            ],
            "automatic_captions": {"en": [{"ext": "json3", "url": f"https://www.youtube.com/api/timedtext?v={vid}&fmt=json3"}]},
        }

    def extract(self, url: str) -> dict[str, Any]:
        if url.startswith("ytsearch"):
            query = url.split(":", 1)[1]
            return {"entries": [{"id": v.id, "title": v.title, "channel": v.channel, "uploader": v.channel,
                                 "duration": v.duration, "url": f"https://www.youtube.com/watch?v={v.id}",
                                 "live_status": None, "view_count": 1000} for v in self.search_results(query)]}
        vid = parse_qs(urlparse(url).query)["v"][0]
        return self.info(vid)

    def refuses(self, vid: str, prefix: str) -> bool:
        if prefix in ("hdav", "au") and self.s.fail_audio:
            return True
        if prefix != "hd":
            return False
        return self.s.fail_hd == "all" or (self.s.fail_hd == "some" and vid in REFUSED)

    def download(self, vid: str, start: float, end: float, prefix: str, audio: bool, audio_only: bool, cache: Path) -> Path:
        with self.lock:
            self.downloads.append((vid, prefix))
        if self.refuses(vid, prefix):
            raise RuntimeError(f"yt-dlp download: HTTP Error 403: Forbidden ({vid})")
        suffix = ".m4a" if audio_only else ".mp4"
        target = cache / "videos" / vid / f"{prefix}_{start:.3f}_{end:.3f}{suffix}"
        with self.lock:
            lock = self.file_locks.setdefault(str(target), threading.Lock())
        with lock:                                     # two shots asking for the same range at once
            if not target.is_file():
                size = (640, 360) if prefix == "a360" else (1280, 720)
                part = target.with_name(f"{target.stem}.part{suffix}")
                # every few seconds of a video look different (another fragment is another picture)
                make_clip(part, end - start, w=size[0], h=size[1], seed=_seed(f"{vid}{int(start // 4)}"), audio=audio or audio_only,
                          audio_only=audio_only)
                part.replace(target)
        return target

    def vtt(self, vid: str) -> str:
        cues = ["WEBVTT", ""]
        lines = [f"Welcome back to {self.videos[vid].title}", "the crowd is on its feet now", "what a performance from the Filipino",
                 SAID, "thank you so much for being here", "it means everything to my country"]
        if not vid.startswith("yuloInterv"):
            lines[3] = "and the score is coming up on the board"
        for n, line in enumerate(lines):
            cues += [f"00:00:{3 + n * 4:02d}.000 --> 00:00:{6 + n * 4:02d}.500", line, ""]
        return "\n".join(cues)

    # HTTP
    def http_answer(self, method: str, url: str, params: Any, body: Any) -> requests.Response:
        parsed = urlparse(url)
        host, path = parsed.netloc, parsed.path
        with self.lock:
            self.http.append(f"{method} {host}{path}")
        query = {**{k: v[0] for k, v in parse_qs(parsed.query).items()}, **(params or {})}
        if host == "i.ytimg.com" and "/sb/" in path:
            vid, sheet = path.split("/")[2], path.rsplit("/M", 1)[1].split(".")[0]
            tiles = [[_pattern(_seed(f"{vid}{sheet}{r}{c}"), 160, 90) for c in range(5)] for r in range(5)]
            image = np.vstack([np.hstack(row) for row in tiles])
            return _response(url, content=cv2.imencode(".jpg", image)[1].tobytes())
        if host == "www.youtube.com" and path == "/api/timedtext":
            vid = query["v"]
            events = [{"tStartMs": 3000 + n * 4000, "dDurationMs": 3500, "segs": [{"utf8": line}]}
                      for n, line in enumerate(re.findall(r"\d --> .*\n(.+)", self.vtt(vid)))]
            return _response(url, data={"events": events})
        if host == "www.googleapis.com" and path.endswith("/search"):
            return _response(url, data={"items": [{"id": {"videoId": v.id}} for v in self.search_results(query["q"])]})
        if host == "www.googleapis.com" and path.endswith("/videos"):
            items = [{"id": vid, "snippet": {"title": self.videos[vid].title, "channelTitle": self.videos[vid].channel,
                                             "channelId": "UC" + vid, "publishedAt": "2024-08-05T00:00:00Z",
                                             "liveBroadcastContent": "none"},
                      "statistics": {"viewCount": "123456"},
                      "contentDetails": {"duration": f"PT{self.videos[vid].duration}S", "definition": "hd"},
                      "status": {"privacyStatus": "public", "uploadStatus": "processed"}}
                     for vid in str(query["id"]).split(",") if vid in self.videos]
            return _response(url, data={"items": items})
        if host == "google.serper.dev":
            if not self.s.serper:
                return _response(url, 403)
            q = json.loads(body)["q"] if isinstance(body, (str, bytes)) else (body or {}).get("q", "")
            return _response(url, data={"images": [
                {"title": f"{q} photo {n}", "imageUrl": f"https://photos.example.org/{_seed(q) % 999}-{n}.jpg",
                 "thumbnailUrl": f"https://photos.example.org/{_seed(q) % 999}-{n}-thumb.jpg",
                 "link": f"https://news.example.org/{q.replace(' ', '-')}-{n}", "imageWidth": 1200, "imageHeight": 1000,
                 "domain": "news.example.org"} for n in range(3)]})
        if host == "photos.example.org":
            return _response(url, content=_jpeg(_seed(path), 1200, 1000))
        if host == "api.pexels.com":
            if "/videos/" in path:
                return _response(url, data={"videos": [
                    {"id": 7001 + n, "duration": 12, "url": f"https://www.pexels.com/video/{7001 + n}/",
                     "image": f"https://images.pexels.com/videos/{7001 + n}/thumb.jpg", "user": {"name": "Ana Stock"},
                     "video_files": [{"width": 1920, "link": f"https://videos.pexels.com/{7001 + n}.mp4"}]} for n in range(2)]})
            return _response(url, data={"photos": [
                {"id": 8001 + n, "url": f"https://www.pexels.com/photo/{8001 + n}/", "photographer": "Luis Foto",
                 "src": {"medium": f"https://images.pexels.com/photos/{8001 + n}/m.jpg",
                         "large2x": f"https://images.pexels.com/photos/{8001 + n}/l.jpg"}} for n in range(2)]})
        if host == "images.pexels.com":
            return _response(url, content=_jpeg(_seed(path), 1600, 900))
        if host == "videos.pexels.com":
            clip = self.root / "cache" / "_pexels_src" / Path(path).name
            with self.lock:
                if not clip.is_file():
                    make_clip(clip, 12, w=1920, h=1080, seed=_seed(path), audio=False)
            return _response(url, content=clip.read_bytes())
        if host.endswith("wikipedia.org"):
            return _response(url, data={"query": {"pages": [{"title": "Carlos Yulo", "extract": "Carlos Yulo won two gold "
                                                             "medals at the 2024 Summer Olympics in Paris."}]}})
        if host in ("commons.wikimedia.org", "api.openverse.org", "api.openverse.engineering", "pixabay.com"):
            return _response(url, data={})
        if "face_" in path and path.endswith(".onnx"):
            return _response(url, content=b"\0" * 200_000)
        with self.lock:
            self.blocked_http.append(url)
        raise requests.ConnectionError(f"sin red en la prueba: {url}")


# --- doubles of local ML that is not installed here -----------------------------------------------------------------


class FakeFaceDetector:
    """One upright face at the top centre of any picture big enough (a portrait, a frame of the athlete)."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.size = (320, 320)

    @classmethod
    def create(cls, *args: Any, **kwargs: Any) -> "FakeFaceDetector":
        return cls()

    def setInputSize(self, size: tuple[int, int]) -> None:
        self.size = tuple(size)

    def detect(self, image: np.ndarray) -> tuple[int, np.ndarray | None]:
        h, w = image.shape[:2]
        if w < 300 or h < 200:
            return 0, None
        fw = min(110.0, 0.6 * w) if h > w else 0.12 * w   # a portrait cut out to the person still has a big face
        fh = 1.2 * fw
        x, y = 0.5 * w - fw / 2, 0.10 * h
        eye_y, nose_y, mouth_y = y + 0.35 * fh, y + 0.55 * fh, y + 0.78 * fh
        face = [x, y, fw, fh, x + 0.3 * fw, eye_y, x + 0.7 * fw, eye_y, x + 0.5 * fw, nose_y,
                x + 0.35 * fw, mouth_y, x + 0.65 * fw, mouth_y, 0.95]
        return 1, np.array([face], np.float32)


class FakeFaceRecognizer:
    @classmethod
    def create(cls, *args: Any, **kwargs: Any) -> "FakeFaceRecognizer":
        return cls()

    def alignCrop(self, image: np.ndarray, face: Any) -> np.ndarray:
        return image

    def feature(self, image: np.ndarray) -> np.ndarray:
        return np.ones((1, 128), np.float32)

    def match(self, a: Any, b: Any, kind: int = 0) -> float:
        return 0.9


class FakeOCR:
    """No text on screen; with `FakeOCR.caption`, the broadcast's caption naming the athlete on every big frame."""

    caption = ""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def __call__(self, image: np.ndarray, **kwargs: Any) -> tuple[list, float]:
        h, w = image.shape[:2]
        if not FakeOCR.caption or w < 1000:
            return [], 0.0
        box = [[60, h - 120], [420, h - 120], [420, h - 80], [60, h - 80]]
        return [[box, FakeOCR.caption, 0.95]], 0.0


def _rembg_module() -> types.ModuleType:
    module = types.ModuleType("rembg")

    def remove(rgb: np.ndarray, session: Any = None, only_mask: bool = False, **kwargs: Any) -> np.ndarray:
        h, w = rgb.shape[:2]
        mask = np.zeros((h, w), np.uint8)
        mask[int(0.08 * h): int(0.95 * h), int(0.35 * w): int(0.65 * w)] = 255
        if only_mask:
            return mask
        return np.dstack([rgb, mask])

    module.remove = remove
    module.new_session = lambda *a, **k: object()
    return module


def _whisper_module(world: World) -> types.ModuleType:
    module = types.ModuleType("faster_whisper")

    class WhisperModel:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def transcribe(self, audio: Any, **kwargs: Any) -> tuple[list, Any]:
            words = [types.SimpleNamespace(word=f" {w}", start=10.0 + 0.4 * i, end=10.35 + 0.4 * i)
                     for i, w in enumerate(f"Hello everyone. {SAID}. Thank you.".split())]
            return [types.SimpleNamespace(words=words)], types.SimpleNamespace(duration=60.0, language="en")

    module.WhisperModel = WhisperModel
    return module


def _embed_images(self: Any, images: Any) -> np.ndarray:
    """A direction per picture (one of 40 «subjects», from its colours): cosine with a prompt ≈ 0.3, more when the
    prompt is about the same «subject» — so each shot prefers other fragments, as with the real CLIP."""

    out = np.zeros((len(images), 512), np.float32)
    for i, image in enumerate(images):
        arr = np.asarray(image, np.float32)
        k = 1 + int(arr.mean() * 13 + arr[..., 0].std() * 7) % 40 if arr.size else 1
        out[i, 0], out[i, k] = 1.0, 2.2
    return out / np.linalg.norm(out, axis=1, keepdims=True)


def _embed_texts(self: Any, texts: Any) -> np.ndarray:
    from pipeline import content_check

    odd = set(content_check.CARTOON) | set(content_check.BROKEN)      # our footage is neither cartoons nor broken
    out = np.zeros((len(texts), 512), np.float32)
    out[:, 0] = 1.0
    for i, text in enumerate(texts):
        out[i, 300 if text in odd else 1 + _seed(str(text)) % 40] = 0.8
    return out / np.linalg.norm(out, axis=1, keepdims=True)


# --- Remotion: what `npx remotion` would leave ------------------------------------------------------------------------


def fake_remotion(world: World):
    def remotion(self: Any, composition: str, props: dict[str, Any], output: Path, extra: list[str], public: set[str]) -> None:
        with world.lock:
            world.remotion.append(composition)
        for rel in public:                                 # what the bundle would read must exist
            assert (self.ctx.work_dir / rel).is_file(), f"Remotion ({composition}) no encontraría {rel}"
        if composition == "Documentary" and world.s.shorts == "native-fails" and props.get("height", 0) > props.get("width", 1):
            raise RuntimeError(f"Falló el render de Remotion ({composition}):\nChrome se cerró")
        if "--sequence" in extra:
            output.mkdir(parents=True, exist_ok=True)
            count = {"Badges": len(props.get("credits", [])), "Thumbnails": len(props.get("variants", []))}.get(composition, 1)
            jpeg = "--image-format=jpeg" in extra
            for n in range(count):
                image = np.zeros((1080, 1920, 4 if not jpeg else 3), np.uint8)
                image[..., :3] = _pattern(n + 3, 1920, 1080)
                if not jpeg:
                    image[..., 3] = 0
                    image[980:1040, 60:600, 3] = 255
                cv2.imwrite(str(output / f"element-{n}.{'jpeg' if jpeg else 'png'}"), image)
            return
        fps = int(props.get("fps") or 30)
        frames = int(props.get("durationInFrames") or sum(s["durationInFrames"] for s in props.get("shots", [])) or fps)
        seconds = frames / fps
        if "--codec=wav" in extra:
            _ffmpeg("-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", f"{seconds:.3f}", str(output))
            return
        w, h = int(props.get("width") or 1920), int(props.get("height") or 1080)
        _ffmpeg("-f", "lavfi", "-i", f"color=c=0x26405a:size={w}x{h}:rate={fps}", "-vf",
                f"drawbox=x='mod(t*360,{w - 200})':y={h // 3}:w=200:h=200:color=0xf5c451:t=fill", "-frames:v", str(frames),
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "35", "-pix_fmt", "yuv420p", str(output))

    def stills(self: Any, composition: str, props: dict[str, Any], frames: list[int], public: set[str]) -> list[Path]:
        with world.lock:
            world.remotion.append(f"{composition}:stills")
        out = []
        for n, _ in enumerate(frames):
            target = self.dir / f"still-{n:02d}.jpg"
            cv2.imwrite(str(target), _pattern(n, 480, 270))
            out.append(target)
        return out

    return remotion, stills


# --- the test's project: config, materials -----------------------------------------------------------------------


def scenario_config(s: Scenario) -> dict[str, Any]:
    """What this test changes over the real config.yaml + canal + formato: speed, and the branch to walk."""

    fast_images = {name: {"min_interval": 0} for name in ("wikimedia", "openverse", "pixabay", "web")}
    config: dict[str, Any] = {
        "align": {"provider": "openai", "use_tts_timings": False},
        "pacing": {"base_seconds": 4.5, "hook_seconds": 6, "hook_shot_seconds": 3.0},
        "grade": {"enabled": s.grade},
        "planner": {"parallel": 1},
        "sourcing": {"parallel": 2, "youtube": {"min_interval": 0, "concurrency": 2, "cookies": "never",
                                               "api_search": s.youtube_api, "results_per_query": 6, "videos_per_shot": 2,
                                               "cookies_file": "", "cookies_dir": ""},
                     "images": {**fast_images, "max_per_shot": 2, "wikimedia": {"enabled": False, "min_interval": 0},
                                "openverse": {"enabled": False, "min_interval": 0},
                                "web": {"enabled": s.serper, "queries_per_shot": 1, "min_interval": 0}},
                     "archive": {"enabled": False}},
        "analysis": {"fine_windows": 1, "extra_windows_with_entities": 0, "moments_per_video": 1, "said_videos": 1,
                     "precompute_during_sourcing": True},
        "judge": {"parallel": 4},
        "content": {"title_blocklist": ["trailer"], **({"official_channels": ["Olympics"]} if s.official else {})},
        "ingest": {"parallel": 3, "preset": "ultrafast", "crf": 32},
        "fallback": {"pexels_for_person": s.pexels, "research_minutes": 2},
        "speed": {"fallback_parallel": 3},
        "timeline": {"moments": s.moments, "sound_bites": s.sound_bites, "bite_gap": 6, "bite_from": 2,
                     "bite_contrast": 3, "endscreen_seconds": s.endscreen, "spotlights": 1,
                     "subtitles": s.subtitles},
        "quotes": {"count": s.quotes, "whisper_minutes": 1},
        "apertura": {"auto": s.apertura in ("auto", "auto-empty"), "auto_ask": "Yulo hablando del oro", "whisper_minutes": 1},
        "shorts": {"enabled": s.shorts != "off", "count": 1, "min_seconds": 6, "max_seconds": 14,
                   **({"style": {"native-fails": "native"}.get(s.shorts, s.shorts)} if s.shorts != "off" else {})},
        "render": {"preset": "ultrafast", "crf": 32, "parallel": 4},
        "qa": {"review": True},
    }
    return _merge(config, s.extra)


def _merge(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in extra.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def build_project(tmp: Path, s: Scenario) -> None:
    """tmp/ is the project: the real config.yaml, channels, formats and assets; the video's own materials."""

    import yaml

    shutil.copy2(ROOT / "config.yaml", tmp / "config.yaml")
    for name in ("canales", "formatos"):
        shutil.copytree(ROOT / name, tmp / name)
    for name in ("assets", "remotion", "package.json"):
        (tmp / name).symlink_to(ROOT / name)
    modules = next((p for p in (ROOT / "node_modules", ROOT.parents[2] / "node_modules") if (p / "@fontsource").is_dir()), None)
    if modules is not None:
        (tmp / "node_modules").symlink_to(modules)
    else:                                       # the fonts of the Shorts' captions, as font_dir() would leave them
        fonts = tmp / "cache" / "fonts"
        fonts.mkdir(parents=True)
        system = sorted(Path("/usr/share/fonts").rglob("*.ttf"))
        assert system, "hace falta node_modules/@fontsource o alguna fuente TTF del sistema"
        shutil.copy2(system[0], fonts / "Inter-Black.ttf")
    folder = tmp / "materiales" / SLUG
    folder.mkdir(parents=True)
    (folder / "guion.txt").write_text(s.script, encoding="utf-8")
    (folder / "titulo.txt").write_text(TITLE + "\n", encoding="utf-8")
    world_seconds = World(s, tmp).voice_seconds()
    _ffmpeg("-f", "lavfi", "-i", f"sine=frequency=180:duration={world_seconds:.2f}", "-ac", "1", "-b:a", "64k",
            str(folder / "voz.mp3"))
    (folder / "config.yaml").write_text(yaml.safe_dump(scenario_config(s), allow_unicode=True), encoding="utf-8")
    if s.own_clip:                              # a recording of your own, with what it shows
        (folder / "material").mkdir()
        _ffmpeg("-f", "lavfi", "-i", "testsrc2=s=1280x720:r=30:d=12", "-pix_fmt", "yuv420p", str(folder / "material" / "yulo-suelo.mp4"))
        (folder / "material.json").write_text(json.dumps({"clips": {"yulo-suelo.mp4": "Carlos Yulo suelo Manila gimnasio"}}),
                                              encoding="utf-8")
    if s.apertura in ("youtube", "broken"):
        (folder / "apertura.json").write_text(json.dumps({
            "id": "yuloInterv5", "url": "https://www.youtube.com/watch?v=yuloInterv5", "title": "Carlos Yulo interview",
            "channel": "Olympics", "start": 15.0, "end": 21.0, "speaker": PERSON, "role": "Gimnasta",
            "subtitles": [{"text": "Nunca dejé de creer en mí", "from": 0.2, "to": 2.5},
                          {"text": "más allá del clip", "from": 30.0, "to": 31.0}]}), encoding="utf-8")
    if s.apertura == "file":
        make_clip(folder / "apertura.mp4", 8, seed=99)
        (folder / "apertura.json").write_text(json.dumps({
            "file": "apertura.mp4", "start": 1.0, "end": 6.0, "speaker": PERSON, "role": None, "channel": "",
            "subtitles": [{"text": "Hola a todos", "from": 0.3, "to": 2.0}]}), encoding="utf-8")


# --- the doubles, all at once ---------------------------------------------------------------------------------------


@contextmanager
def _fake_modules(modules: dict[str, Any]) -> Iterator[None]:
    before = {name: sys.modules.get(name) for name in modules}
    sys.modules.update(modules)
    try:
        yield
    finally:
        for name, module in before.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


def outside_world(world: World, monkeypatch: pytest.MonkeyPatch) -> ExitStack:
    import openai

    from pipeline import llm, render
    from pipeline.analysis import clip as clip_module
    from pipeline.analysis import detectors
    from pipeline.sourcing import common, youtube

    for name in ("LLM_API_KEY", "OPENAI_API_KEY", "PEXELS_API_KEY", "SERPER_API_KEY", "PIXABAY_API_KEY", "YOUTUBE_API_KEY",
                 "YOUTUBE_API_KEYS", "YOUTUBE_PROXY", "YOUTUBE_METADATA_PROXY", "YOUTUBE_COOKIES_B64", "EDITVID_SIN_YOUTUBE",
                 "TELEGRAM_BOT_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    from pipeline import sin_youtube

    monkeypatch.delenv(sin_youtube.ENV, raising=False)
    monkeypatch.setenv("LLM_API_KEY", "test-llm")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai")
    if world.s.pexels:
        monkeypatch.setenv("PEXELS_API_KEY", "test-pexels")
    if world.s.serper:
        monkeypatch.setenv("SERPER_API_KEY", "test-serper")
    if world.s.youtube_api:
        monkeypatch.setenv("YOUTUBE_API_KEY", "test-youtube-api")

    FakeOpenAI.world = world
    FakeOCR.caption = "C. YULO PHI" if world.s.captions else ""
    stack = ExitStack()

    def request(session: Any, method: str, url: str, params: Any = None, data: Any = None, json: Any = None,
                **kwargs: Any) -> requests.Response:
        return world.http_answer(method.upper(), url, params, data if data is not None else json)

    real_connect = socket.socket.connect

    def guarded_connect(sock: socket.socket, address: Any) -> Any:
        if sock.family == getattr(socket, "AF_UNIX", None):
            return real_connect(sock, address)
        raise ConnectionRefusedError(f"la prueba no sale a la red: {address}")

    def extract(self: Any, url: str, extra: dict[str, Any]) -> Any:
        return world.extract(url)

    def download_range(self: Any, video_id: str, start: float, end: float, *, fmt: str, prefix: str,
                       audio: bool = False, audio_only: bool = False) -> Path:
        return world.download(video_id, start, end, prefix, audio, audio_only, self.cache_dir)

    def subtitle_file(self: Any, video_id: str, language: str = "en") -> Path | None:
        if world.s.no_subtitles:
            return None
        path = self.cache_dir / "videos" / video_id / f"subs.{language}.vtt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(world.vtt(video_id), encoding="utf-8")
        return path

    remotion, stills = fake_remotion(world)
    patches = [
        patch.object(openai, "OpenAI", FakeOpenAI), patch.object(llm, "OpenAI", FakeOpenAI),
        patch.object(requests.sessions.Session, "request", request),
        patch.object(socket.socket, "connect", guarded_connect),
        patch.object(common.Pacer, "wait", lambda self: None),
        patch.object(common.SharedPacer, "wait", lambda self: None),
        patch.object(youtube.YouTubeSource, "_extract", extract),
        patch.object(youtube.YouTubeSource, "_download_range", download_range),
        patch.object(youtube.YouTubeSource, "_fetch_whole", lambda self, *a, **k: None),
        patch.object(youtube.YouTubeSource, "subtitle_file", subtitle_file),
        patch.object(youtube, "proxy_reachable", lambda proxy, timeout=5.0: True),
        patch.object(clip_module.ClipScorer, "_load", lambda self: None),
        patch.object(clip_module.ClipScorer, "embed_images", _embed_images),
        patch.object(clip_module.ClipScorer, "embed_texts", _embed_texts),
        patch.object(detectors, "_make_ocr", lambda side: FakeOCR()),
        patch.object(cv2, "FaceDetectorYN", FakeFaceDetector),
        patch.object(cv2, "FaceRecognizerSF", FakeFaceRecognizer),
        patch.object(render.Renderer, "remotion", remotion),
        patch.object(render.Renderer, "stills", stills),
        # only these three entries: patch.dict(sys.modules) would also drop, on the way out, every module first
        # imported meanwhile, leaving two copies of them for the tests that run later
        _fake_modules({"rembg": _rembg_module(), "faster_whisper": _whisper_module(world),
                       "rapidocr_onnxruntime": types.SimpleNamespace(RapidOCR=FakeOCR)}),
    ]
    for p in patches:
        stack.enter_context(p)
    return stack


# --- the scenarios ---------------------------------------------------------------------------------------------------


SCENARIOS = [
    # the judge takes everything; moments, sound bites and quotes with an official channel; the opening found by
    # itself (its words matched in the subtitles); vertical Shorts with Remotion; searches through the YouTube API
    Scenario("acepta", judge="accept", official=True, moments=1, sound_bites=2, quotes=1, apertura="auto",
             shorts="native", youtube_api=True, endscreen=5, subtitles=True, captions=True),
    # the judge turns everything down: protagonist filler and, for a narrated moment nobody filmed, a photo of the
    # protagonist (no stock in a video about a person); the second search's call fails; the moment check says
    # «interview»; an opening chosen by hand on YouTube; Shorts over a blurred copy
    Scenario("rechaza", judge="reject", competition=False, moments=1, quotes=1, apertura="youtube", shorts="blur",
             llm_fails=("research",)),
    # half the HD downloads refused (next option, event footage, second search), the downloads with sound too
    # (moments/quotes come back empty); your own uploaded file as the opening; Pexels allowed for a person;
    # vertical Shorts fail in Remotion → the blurred ones; no subtitles anywhere → faster-whisper
    Scenario("descargas", judge="mixed", fail_hd="some", fail_audio=True, moments=1, sound_bites=1, quotes=1, apertura="file",
             shorts="native-fails", no_subtitles=True, pexels=True),
    # every HD download refused and no web photos: nothing real left → the shots end as text cards; the opening
    # search finds nothing (the LLM pick says no); a broken factcheck call; Shorts written as new videos
    Scenario("sin-material", judge="accept", fail_hd="all", serper=False, moments=0, apertura="auto-empty",
             apertura_said=False, pick_answers=[{"found": False}], shorts="nuevo", llm_fails=("claims",), script=SHORT_SCRIPT,
             extra={"qa": {"max_empty_share": 1.0}}),
    # nothing with the original sound: the cold open stage writes its empty file and leaves; no Shorts; the colour
    # grade on (it measures every clip: costly, so only in this short video)
    Scenario("minimo", moments=0, shorts="off", script=SHORT_SCRIPT, grade=True, extra={"quotes": {"count": 0}, "apertura": {"auto": False}}),
    # planner.ideas: shots grouped into ideas (one search each, the same sources for all their shots), a literal idea
    # never filled with another moment of the person, the last one a title read aloud: no footage searched for it
    Scenario("ideas", judge="mixed", moments=0, shorts="off", script=SHORT_SCRIPT,
             extra={"planner": {"ideas": True}, "revisor": {"enabled": True, "max_usd": 0.2}}, own_clip=True),
]


def run_scenario(tmp: Path, s: Scenario, monkeypatch: pytest.MonkeyPatch) -> tuple[Any, World, list[str]]:
    from pipeline import runner
    from pipeline.context import RunContext

    build_project(tmp, s)
    world = World(s, tmp)
    with outside_world(world, monkeypatch):
        ctx = RunContext.create(SLUG, root=tmp)
        executed = runner.run_stages(ctx)
    return ctx, world, executed


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s.name for s in SCENARIOS])
def test_every_stage_runs_its_real_code(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, scenario: Scenario) -> None:
    from pipeline import runner
    from pipeline.schemas import ColdOpenFile, FallbackFile, SelectionFile

    started = time.monotonic()
    ctx, world, executed = run_scenario(tmp_path, scenario, monkeypatch)
    assert executed == runner.STAGE_NAMES                         # every stage ran, none skipped
    assert not world.blocked_http, f"peticiones sin doble: {world.blocked_http[:5]}"
    assert not world.brain.unknown, f"prompts sin respuesta en la prueba: {world.brain.unknown}"
    final = ctx.out_dir / "video-final.mp4"
    assert final.is_file() and final.stat().st_size > 10_000
    probe = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json",
                                       str(final)], capture_output=True, text=True, check=True).stdout)
    assert float(probe["format"]["duration"]) >= world.voice_seconds() - 1

    coldopen = ColdOpenFile.model_validate(ctx.read_json("coldopen.json"))
    fallback = FallbackFile.model_validate(ctx.read_json("fallback.json"))
    selection = SelectionFile.model_validate(ctx.read_json("selection.json"))
    methods = sorted({i.method for i in fallback.items})
    print(f"\n[{scenario.name}] {time.monotonic() - started:.0f} s · relleno {methods} · sin resolver "
          f"{len(fallback.unresolved)} · momentos {len(coldopen.moments)} · golpes {len(coldopen.bites)} · "
          f"citas {len(coldopen.quotes)} · apertura {bool(coldopen.opening)} · Remotion {sorted(set(world.remotion))}")

    if scenario.name == "acepta":
        assert sum(s.status == "selected" and s.decidedBy == "judge" for s in selection.selections) >= 3
        assert coldopen.moments and coldopen.quotes and coldopen.opening
        assert json.loads((ctx.materials_dir / "apertura.json").read_text())["auto"] is True
        assert len(list((ctx.out_dir / "shorts").glob("short-*.mp4"))) >= 1
    if scenario.name == "rechaza":
        assert not coldopen.moments                                   # «an interview»: not competition footage
        assert coldopen.opening and coldopen.opening.candidateId == "yt:yuloInterv5"
        assert "protagonist-filler" in methods
        assert "protagonist-photo" in methods, fallback.unresolved      # step 2c of the fallback
    if scenario.name == "descargas":
        assert coldopen.opening is not None and coldopen.opening.candidateId == "file:apertura.mp4"
        assert not coldopen.moments and not coldopen.quotes
        assert methods and any(i.reason.startswith("descarga fallida") for i in fallback.items)
        assert len(list((ctx.out_dir / "shorts").glob("short-*.mp4"))) >= 1
    if scenario.name == "sin-material":
        assert coldopen.opening is None and not (ctx.materials_dir / "apertura.json").is_file()
        assert json.loads((ctx.work_dir / "apertura.auto.json").read_text())["found"] is False
        from pipeline.context import find_video

        assert (find_video(tmp_path, f"{SLUG}-short1") / "config.yaml").is_file()     # a new video in the queue
    if scenario.name == "ideas":
        from pipeline.schemas import ShotsFile

        planned = ShotsFile.model_validate(ctx.read_json("shots.json")).shots
        kinds = {s.id: s.idea.kind for s in planned if s.idea is not None}
        has_moment = any(s.broll is not None and s.broll.moment for s in planned)
        assert len(kinds) == len(planned) and "rotulo" in kinds.values()
        assert ("literal" in kinds.values()) == has_moment                 # literal only with a narrated action
        literal_ideas = {s.idea.id for s in planned if s.idea is not None and s.idea.kind == "literal"}
        assert all(any(x.broll is not None and x.broll.moment for x in planned
                       if x.idea is not None and x.idea.id == idea) for idea in literal_ideas)   # only with an action
        rotulos = {sid for sid, kind in kinds.items() if kind == "rotulo"}
        assert not rotulos & {p.stem for p in (ctx.work_dir / "candidates").glob("*.json")}   # never searched
        literal = {sid for sid, kind in kinds.items() if kind == "literal"}
        assert not any(i.shotId in literal and i.method == "protagonist-filler" for i in fallback.items)
        offered = [json.loads(p.read_text()) for p in (ctx.work_dir / "candidates").glob("s*.json")]
        assert all(any(c["source"] == "propio" for c in o["candidates"]) for o in offered)   # your clip, for every shot
        from pipeline.schemas import Timeline

        mine = [x for x in Timeline.model_validate(ctx.read_json("timeline.json")).shots if x.media and x.media.source == "propio"]
        assert all(x.media.credit is None for x in mine)                       # no «Fuente:» over your own clip
        # the judge accepted it, and material it accepted wins over any master video — however CLIP scored it
        assert mine and any(x.source == "propio" and x.pickedBy == "material" for x in selection.selections)
        hinted = [o for p in (ctx.work_dir / "scores").glob("s*.json")
                  for o in json.loads(p.read_text())["options"] if o.get("hint") == "indice"]
        assert hinted and all(o["source"] == "propio" for o in hinted)   # the scene found by its description
        reviewed = json.loads((ctx.out_dir / "revisor" / "revisor.json").read_text())
        assert "skipped" not in reviewed and reviewed["shots"] > 0            # the reviewer ran in the queue
    if scenario.name == "minimo":
        assert coldopen == ColdOpenFile(slug=SLUG)
        assert not (ctx.out_dir / "shorts").exists() or not list((ctx.out_dir / "shorts").glob("*.mp4"))

    # a second run with nothing changed does nothing at all (and validates every output); with downloads that
    # failed, ingest tries them again (its retry_if) and what depends on it follows
    with outside_world(world, monkeypatch):
        again = runner.run_stages(ctx)
    assert again == [] or (scenario.fail_hd and again[0] == "ingest"), again


# --- the studio's opening search (main.py --apertura): the branches the pipeline does not reach by itself ---------


APERTURA_REQUESTS = [
    # a YouTube link with its seconds: no search, the stretch you marked, translated subtitles
    ("enlace", {"url": "https://youtu.be/yuloInterv5", "start": "0:12", "end": "20", "language": "en"}, {}, 1),
    # a link without seconds: its words found in the subtitles (the plan knew them)
    ("enlace-sin-segundos", {"url": "https://www.youtube.com/watch?v=yuloInterv5"}, {}, 1),
    # your uploaded file, seconds given and no subtitles: no Whisper at all
    ("archivo", {"file": "apertura-0123456789ab.mp4", "start": "1", "end": "4", "subtitles": False}, {}, 1),
    # your uploaded file without seconds: Whisper (faster-whisper) finds where the words are said
    ("archivo-whisper", {"file": "apertura-0123456789ab.mp4"}, {}, 1),
    # the file did not arrive
    ("archivo-perdido", {"file": "no-esta.mp4"}, {}, 0),
    # nothing given: searched; the LLM picks the stretch (no words known), every way it can answer
    ("busqueda-llm", {"title": TITLE, "script": SCRIPT, "ask": "Yulo hablando del oro"},
     {"apertura_said": False, "pick_answers": [{"found": True, "start": "x", "end": 3}, {"found": True, "start": 9, "end": 4},
                                               {"found": False}, {"found": True, "start": 11.0, "end": 60.0, "why": "lo dice"}]}, 1),
    # the pick call itself fails, and so does the translation (the original lines stay)
    ("busqueda-fallos", {"title": TITLE, "script": SCRIPT}, {"apertura_said": False, "llm_fails": ("pick", "lines")}, 0),
    # videos too long to read through are skipped
    ("videos-largos", {"title": TITLE, "script": SCRIPT, "channel": "gimnasia"},
     {"extra": {"apertura": {"max_video_minutes": 1}}}, 0),
    # a second that is not a second
    ("segundo-malo", {"url": "https://youtu.be/yuloInterv5", "start": "doce"}, {}, 0),
]


@pytest.mark.parametrize("case, body, changes, found", APERTURA_REQUESTS, ids=[c[0] for c in APERTURA_REQUESTS])
def test_apertura_requests_from_the_studio(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str,
                                           body: dict[str, Any], changes: dict[str, Any], found: int) -> None:
    import yaml

    from pipeline import apertura

    s = Scenario(f"apertura-{case}", shorts="off", **changes)
    build_project(tmp_path, s)
    if s.extra:                                          # run_request reads the project's config (no video folder)
        base = yaml.safe_load((tmp_path / "config.yaml").read_text("utf-8"))
        (tmp_path / "config.yaml").write_text(yaml.safe_dump(_merge(base, s.extra), allow_unicode=True), "utf-8")
    if "file" in body:
        uploads = tmp_path / "materiales" / "_subidas"
        if body["file"] != "no-esta.mp4":
            make_clip(uploads / body["file"], 6, seed=7)
        body = {**body, "file": str(uploads / body["file"])}
    request = tmp_path / "peticion.json"
    request.write_text(json.dumps(body), encoding="utf-8")
    world = World(s, tmp_path)
    with outside_world(world, monkeypatch):
        result = apertura.run_request(tmp_path, request)
    saved = json.loads(request.with_name("peticion.resultado.json").read_text("utf-8"))
    assert saved == json.loads(json.dumps(result))
    assert len(result["candidates"]) >= found, result
    if case in ("archivo-perdido", "segundo-malo"):
        assert result["error"]
    for candidate in result["candidates"]:
        assert candidate["end"] > candidate["start"] and candidate["end"] - candidate["start"] <= apertura.LIMIT
        data = apertura.choice(candidate, most=apertura.MAX_SECONDS, subtitles=body.get("subtitles", True) is not False)
        assert data["id"] or data["file"]
    assert not world.blocked_http and not world.brain.unknown
