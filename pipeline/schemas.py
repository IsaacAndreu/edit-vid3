"""Pydantic schemas for the JSON files exchanged between stages."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Stage 1: words.json -------------------------------------------------------------


class Word(_Strict):
    index: int = Field(ge=0)
    text: str = Field(min_length=1)          # exactly as written in guion.txt
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    matched: bool                            # False → timing interpolated, not heard by Whisper
    sentenceEnd: bool = False                # text ends with . ! ? … or closes a line

    @model_validator(mode="after")
    def _ordered(self) -> "Word":
        if self.end < self.start:
            raise ValueError(f"Palabra {self.index}: end < start")
        return self


class Chapter(_Strict):
    title: str = Field(min_length=1)
    wordIndex: int = Field(ge=0)             # first word of the chapter
    start: float = Field(ge=0)
    spoken: bool                             # whether the heading itself is narrated


class AlignmentStats(_Strict):
    provider: str
    model: str
    scriptWords: int
    whisperWords: int
    matchedWords: int
    matchRatio: float = Field(ge=0, le=1)


class WordsFile(_Strict):
    slug: str
    title: str
    language: str
    durationSeconds: float = Field(gt=0)
    words: list[Word] = Field(min_length=1)
    chapters: list[Chapter]
    alignment: AlignmentStats

    @model_validator(mode="after")
    def _consistent(self) -> "WordsFile":
        previous_start = 0.0
        for position, word in enumerate(self.words):
            if word.index != position:
                raise ValueError(f"Índice de palabra no correlativo en la posición {position}")
            if word.start + 1e-6 < previous_start:
                raise ValueError(f"Tiempos no monótonos en la palabra {position}")
            if word.end > self.durationSeconds + 0.05:
                raise ValueError(f"La palabra {position} termina después del audio")
            previous_start = word.start
        for chapter in self.chapters:
            if chapter.wordIndex >= len(self.words):
                raise ValueError(f"Capítulo {chapter.title!r} apunta fuera de las palabras")
        return self


# --- Stage 2: shots.json ------------------------------------------------------------

ShotType = Literal["broll", "datacard", "stat", "chapter", "split"]
Sign = Literal["positive", "negative", "neutral"]
PreferredShot = Literal["wide", "medium", "close-up", "aerial", "detail", "action", "archive"]
MIN_SHOT_SECONDS = 1.5
MAX_SHOT_SECONDS = 4.0


class BrollSpec(_Strict):
    """What footage to look for. Queries: 3-5 in English + 1-2 in the script language."""

    visualIntent: str = Field(min_length=3, max_length=300)
    queries: list[str] = Field(min_length=3, max_length=5)          # English
    queriesLocal: list[str] = Field(min_length=1, max_length=2)     # script language
    entities: list[str] = Field(default_factory=list, max_length=5)
    mustContain: list[str] = Field(default_factory=list, max_length=4)
    avoid: list[str] = Field(default_factory=list, max_length=5)
    preferredShot: PreferredShot = "medium"
    event: str | None = Field(default=None, max_length=160)   # story event this shot belongs to (search phrase)

    @model_validator(mode="before")
    @classmethod
    def _split_languages(cls, data):
        # The LLM returns {"queriesEn": [...], "queriesEs": [...]}; store English in `queries`.
        if isinstance(data, dict) and "queriesEn" in data:
            data = dict(data)
            data["queries"] = data.pop("queriesEn")
            data["queriesLocal"] = data.pop("queriesEs", data.get("queriesLocal", []))
        return data

    @model_validator(mode="after")
    def _no_blank_queries(self) -> "BrollSpec":
        if any(not q.strip() for q in [*self.queries, *self.queriesLocal]):
            raise ValueError("broll tiene queries vacías")
        return self


class DataRow(_Strict):
    label: str = Field(min_length=1, max_length=60)
    value: str = Field(min_length=1, max_length=24)
    sign: Sign = "neutral"


class DataPanel(_Strict):
    title: str = Field(min_length=1, max_length=60)
    rows: list[DataRow] = Field(min_length=1, max_length=6)
    note: str | None = Field(default=None, max_length=90)


class StatData(_Strict):
    value: str = Field(min_length=1, max_length=16)       # "2,7%", "305.800 M$", "700"
    label: str = Field(min_length=1, max_length=70)
    sign: Sign = "neutral"


LabelKind = Literal["name", "place", "date", "score"]


class OnScreenLabel(_Strict):
    """Small lower-left tag: a person's name, a place, a date or a score, as said in the narration."""

    kind: LabelKind
    text: str = Field(min_length=1, max_length=40)


class Shot(_Strict):
    id: str = Field(pattern=r"^s\d{3,4}$")
    type: ShotType
    startWord: int = Field(ge=0)
    endWord: int = Field(ge=0)
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    text: str = Field(min_length=1)                        # script words covered by this shot
    chapter: int = Field(ge=0)                              # index into ShotsFile.chapters
    broll: BrollSpec | None = None                          # footage (background for chapter/split/stat)
    panel: DataPanel | None = None                          # datacard / split
    panelId: str | None = None                              # consecutive shots sharing a panel render as one
    stat: StatData | None = None
    chapterTitle: str | None = Field(default=None, max_length=48)
    label: OnScreenLabel | None = None                      # lower-left tag (first mention of a person/score)

    @property
    def duration(self) -> float:
        return self.end - self.start

    @model_validator(mode="after")
    def _fields_for_type(self) -> "Shot":
        if self.endWord < self.startWord:
            raise ValueError(f"{self.id}: endWord < startWord")
        needs = {
            "broll": ("broll",),
            "chapter": ("broll", "chapterTitle"),
            "split": ("broll", "panel"),
            "datacard": ("panel",),
            "stat": ("stat",),
        }[self.type]
        missing = [name for name in needs if getattr(self, name) in (None, "")]
        if missing:
            raise ValueError(f"{self.id}: un plano {self.type} necesita {', '.join(missing)}")
        return self


class PlanChapter(_Strict):
    title: str = Field(min_length=1, max_length=48)
    startWord: int = Field(ge=0)
    fromScript: bool                                        # True when it came from a "## " line
    showTitle: bool = True                                  # False for the untitled intro before chapter 1


class StoryEvent(_Strict):
    """A stretch of the story about one concrete event: every shot in it searches for that event."""

    label: str = Field(min_length=3, max_length=160)        # English search phrase: who + what + year + where
    startWord: int = Field(ge=0)
    tag: str | None = Field(default=None, max_length=40)    # on-screen place/date in the script language


class ShotsFile(_Strict):
    slug: str
    title: str
    durationSeconds: float = Field(gt=0)
    context: str = ""                                        # global visual context from the outline pass
    subject: str = ""                                        # who/what the video is about ("Carlos Yulo · artistic gymnastics")
    events: list[StoryEvent] = Field(default_factory=list)
    chapters: list[PlanChapter]
    shots: list[Shot] = Field(min_length=1)

    @model_validator(mode="after")
    def _contiguous(self) -> "ShotsFile":
        previous_end = 0.0
        previous_word = -1
        for shot in self.shots:
            if abs(shot.start - previous_end) > 1e-3:
                raise ValueError(f"{shot.id}: hueco o solape en el tiempo ({previous_end:.3f} → {shot.start:.3f})")
            if shot.startWord != previous_word + 1:
                raise ValueError(f"{shot.id}: las palabras no son contiguas")
            if not MIN_SHOT_SECONDS - 1e-3 <= shot.duration <= MAX_SHOT_SECONDS + 1e-3:
                raise ValueError(f"{shot.id}: dura {shot.duration:.2f} s (permitido 1,5-4 s)")
            if shot.chapter >= max(1, len(self.chapters)):
                raise ValueError(f"{shot.id}: capítulo fuera de rango")
            previous_end = shot.end
            previous_word = shot.endWord
        if abs(previous_end - self.durationSeconds) > 1e-3:
            raise ValueError("Los planos no cubren todo el audio")
        return self


# --- Stage 3: candidates/<shot_id>.json ---------------------------------------------

Source = Literal["youtube", "wikimedia", "openverse", "pixabay", "web"]


class AnalysisRange(_Strict):
    """A low-res local file covering [start, end] seconds of the source video."""

    path: str                                                # relative to the project root
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    reason: str = ""                                         # full | subtitle hit "..." | sampled


class Storyboard(_Strict):
    """YouTube's seek-bar thumbnails: a cheap visual index of the whole video."""

    sheets: list[str] = Field(min_length=1)                  # local JPGs, relative to the project root, in order
    columns: int = Field(ge=1)
    rows: int = Field(ge=1)
    tileWidth: int = Field(ge=1)
    tileHeight: int = Field(ge=1)
    interval: float = Field(gt=0)                            # seconds between consecutive thumbnails
    frames: int = Field(ge=1)

    def locate(self, index: int) -> tuple[int, int, int]:
        """Frame index → (sheet, x, y) of its tile."""

        per_sheet = self.columns * self.rows
        sheet, cell = divmod(index, per_sheet)
        return sheet, (cell % self.columns) * self.tileWidth, (cell // self.columns) * self.tileHeight


class Candidate(_Strict):
    id: str                                                  # "yt:<videoId>", "wm:<pageId>", "ov:<uuid>"...
    source: Source
    kind: Literal["video", "image"]
    url: str                                                 # human page (YouTube watch URL, Commons file page...)
    title: str
    channel: str                                             # YouTube channel / image author — goes into the credit
    uploader: str | None = None
    license: str                                             # "youtube-standard", "creative-commons", "CC BY-SA 4.0"...
    credit: str                                              # exact on-screen text: "Fuente: <...>"
    attribution: str                                         # long form for creditos.txt
    durationSeconds: float | None = None
    width: int | None = None
    height: int | None = None
    query: str                                               # first query that surfaced it
    rankScore: float = Field(ge=0)                           # search-rank fusion, before any visual analysis
    storyboard: Storyboard | None = None                     # videos: thumbnails of the whole video
    imagePath: str | None = None                             # images: analysis-size local copy
    mediaUrl: str | None = None                              # images: full-resolution original (for ingest)

    @model_validator(mode="after")
    def _media_present(self) -> "Candidate":
        if self.kind == "video" and not self.storyboard:
            raise ValueError(f"{self.id}: vídeo sin storyboard para analizar")
        if self.kind == "image" and not self.imagePath:
            raise ValueError(f"{self.id}: imagen sin fichero local")
        if not self.credit.startswith("Fuente: ") or len(self.credit) <= len("Fuente: "):
            raise ValueError(f"{self.id}: crédito inválido {self.credit!r}")
        return self


class ShotCandidates(_Strict):
    shotId: str
    specHash: str                                            # hash of the shot's broll spec + sourcing config
    queries: dict[str, list[str]]                            # source → queries actually run
    candidates: list[Candidate]
    notes: list[str] = Field(default_factory=list)           # e.g. "youtube bloqueado: ..."


# --- Stage 4: scores/<shot_id>.json ---------------------------------------------------

MAX_THIRD_PARTY_SECONDS = 5.0


class OptionScores(_Strict):
    clip: float                                              # CLIP similarity shot text ↔ frames (raw cosine)
    entity: float = 0.0                                      # 1 = source transcript names an entity of the shot
    sharpness: float = 0.0                                   # 0-1
    motion: float = 0.0                                      # 0-1
    textArea: float = 0.0                                    # fraction of the frame covered by text
    faceArea: float = 0.0                                    # largest face / frame


class Option(_Strict):
    """One usable fragment (video) or picture (image) for a shot, with its local-analysis score."""

    candidateId: str
    source: Source
    kind: Literal["video", "image"]
    pass_: Literal["coarse", "fine"] = Field(alias="pass")   # fine = checked on a 360p download
    start: float | None = None                               # source-video seconds
    end: float | None = None
    analysisPath: str | None = None                          # 360p window file or image, relative to root
    scores: OptionScores
    total: float
    discarded: str | None = None                             # reason, when the option must not be used
    phash: str | None = None                                 # 64-bit perceptual hash, for de-duplication

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    @model_validator(mode="after")
    def _video_span(self) -> "Option":
        if self.kind == "video":
            if self.start is None or self.end is None or self.end <= self.start:
                raise ValueError(f"{self.candidateId}: fragmento sin tramo válido")
            if self.end - self.start > MAX_THIRD_PARTY_SECONDS + 1e-6:
                raise ValueError(f"{self.candidateId}: fragmento de {self.end - self.start:.2f} s (> 5 s)")
        return self


class ShotScores(_Strict):
    shotId: str
    inputsHash: str
    needed: float = Field(gt=0, le=MAX_THIRD_PARTY_SECONDS)  # seconds of footage the shot needs (≤ 5)
    prompts: list[str]
    options: list[Option]                                    # best first; discarded ones last
    notes: list[str] = Field(default_factory=list)


# --- Stage 5: selection.json --------------------------------------------------------


class JudgeVerdict(_Strict):
    choice: str                                              # "A" | "B" | "C" | "none"
    selectedStart: float | None = None
    selectedEnd: float | None = None
    score: float = Field(ge=0, le=1)
    reason: str
    confidence: float = Field(ge=0, le=1)
    model: str
    round: int = 1                                           # contact sheet: judge/<shot>.jpg (1) or judge/<shot>-2.jpg


class Selection(_Strict):
    shotId: str
    status: Literal["selected", "fallback"]                 # fallback → stage 7 (Pexels / GPT Image)
    decidedBy: Literal["score", "judge", "fallback"]
    candidateId: str | None = None
    source: str | None = None                                # youtube | wikimedia | openverse | pixabay | pexels | generated
    kind: Literal["video", "image"] | None = None
    start: float | None = None                               # source seconds (videos)
    end: float | None = None
    analysisPath: str | None = None                          # low-res local copy (360p window / image thumbnail)
    mediaUrl: str | None = None                              # full-resolution image (images)
    url: str | None = None                                   # page of the source
    title: str | None = None
    channel: str | None = None
    license: str | None = None
    credit: str | None = None                                # exact on-screen text, copied from the candidate
    attribution: str | None = None
    score: float | None = None                               # stage-4 total of the chosen option
    judge: JudgeVerdict | None = None
    phash: str | None = None

    @model_validator(mode="after")
    def _complete(self) -> "Selection":
        if self.status == "selected":
            missing = [n for n in ("candidateId", "source", "kind", "credit", "url") if not getattr(self, n)]
            if missing:
                raise ValueError(f"{self.shotId}: selección incompleta ({', '.join(missing)})")
            if self.kind == "video":
                if self.start is None or self.end is None or not 0 < self.end - self.start <= MAX_THIRD_PARTY_SECONDS + 1e-6:
                    raise ValueError(f"{self.shotId}: tramo de vídeo inválido o > 5 s")
            if not self.credit.startswith("Fuente: "):
                raise ValueError(f"{self.shotId}: crédito inválido")
        return self


class SelectionFile(_Strict):
    slug: str
    selections: list[Selection]
    stats: dict[str, int | float] = Field(default_factory=dict)


# --- Stage 6: media/_ingest.json ------------------------------------------------------


class IngestedMedia(_Strict):
    shotId: str
    kind: Literal["video", "image"]
    path: str                                                # relative to the project root
    source: str
    candidateId: str
    start: float | None = None                               # source seconds actually used
    end: float | None = None
    durationSeconds: float | None = None                     # of the rendered clip (videos)
    width: int
    height: int
    fps: float | None = None
    hasAudio: bool = False
    lut: str | None = None
    credit: str
    specHash: str                                            # selection + ingest settings → skip when unchanged

    @model_validator(mode="after")
    def _checks(self) -> "IngestedMedia":
        if self.kind == "video":
            if self.durationSeconds is None or self.durationSeconds > MAX_THIRD_PARTY_SECONDS + 1 / 30 + 1e-6:
                raise ValueError(f"{self.shotId}: clip de {self.durationSeconds} s (máximo 5 s)")
            if self.hasAudio:
                raise ValueError(f"{self.shotId}: el clip conserva audio")
            if (self.width, self.height) != (1920, 1080):
                raise ValueError(f"{self.shotId}: clip de {self.width}x{self.height}, se esperaba 1920x1080")
        if not self.credit.startswith("Fuente: "):
            raise ValueError(f"{self.shotId}: crédito inválido")
        return self


class IngestFile(_Strict):
    slug: str
    media: list[IngestedMedia]
    skipped: list[str] = Field(default_factory=list)         # fallback shots → stage 7
    failed: dict[str, str] = Field(default_factory=dict)     # shot → error (stage 7 covers them too)


# --- Stage 7: fallback.json -----------------------------------------------------------


class FallbackItem(_Strict):
    shotId: str
    reason: str                                              # why the shot needed a fallback
    method: Literal["next-option", "protagonist", "web-photo", "pexels-video", "pexels-photo", "generated"]
    kind: Literal["video", "image"]
    path: str                                                # normalised media, relative to the project root
    source: str                                              # youtube | wikimedia | openverse | pexels | generated
    candidateId: str
    url: str | None = None
    start: float | None = None
    end: float | None = None
    durationSeconds: float | None = None
    credit: str | None = None                                # None only for generated images
    attribution: str | None = None
    clip: float | None = None                                # CLIP similarity, when measured here
    costUsd: float = 0.0
    specHash: str

    @model_validator(mode="after")
    def _checks(self) -> "FallbackItem":
        if self.source == "generated":
            return self
        if not self.credit or not self.credit.startswith("Fuente: "):
            raise ValueError(f"{self.shotId}: el material de terceros necesita crédito")
        if self.kind == "video" and (self.durationSeconds is None or self.durationSeconds > MAX_THIRD_PARTY_SECONDS + 1 / 30 + 1e-6):
            raise ValueError(f"{self.shotId}: clip de más de 5 s")
        return self


class FallbackFile(_Strict):
    slug: str
    items: list[FallbackItem]
    unresolved: dict[str, str] = Field(default_factory=dict)  # shot → why nothing worked


# --- Stage 8: timeline.json (Remotion props) ------------------------------------------


class TimelineMedia(_Strict):
    src: str                                                 # relative to work/<slug>/ (Remotion public dir)
    kind: Literal["video", "image"]
    source: str
    credit: str | None = None                                # on-screen "Fuente: …"; None for generated images
    layout: Literal["full", "card", "person"] = "full"       # card: framed over the channel background; person: cutout card
    caption: str | None = None                               # person cards: the name
    width: int | None = None                                 # of the media file (cards keep the source frame)
    height: int | None = None


class ColdOpenClip(_Strict):
    """A few seconds of the protagonist's peak with its ORIGINAL sound, before the narration starts."""

    path: str                                                # relative to the project root
    candidateId: str
    url: str
    title: str | None = None
    channel: str | None = None
    start: float
    end: float
    durationSeconds: float = Field(gt=0, le=MAX_THIRD_PARTY_SECONDS + 1 / 30 + 1e-6)
    width: int
    height: int
    credit: str
    attribution: str | None = None


class ColdOpenFile(_Strict):
    slug: str
    seconds: float = 0
    clips: list[ColdOpenClip] = Field(default_factory=list)


class TimelineLabel(_Strict):
    kind: LabelKind
    text: str
    from_: int = Field(alias="from", ge=0)
    durationInFrames: int = Field(ge=1)

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class TimelineShot(_Strict):
    id: str
    type: ShotType
    from_: int = Field(alias="from", ge=0)                   # frame
    durationInFrames: int = Field(ge=1)
    text: str
    media: TimelineMedia | None = None
    chapterTitle: str | None = None
    chapterNumber: int | None = None                         # 1, 2, … for "CAPÍTULO 01"
    groupId: str | None = None                               # panel / stat group this shot belongs to
    coldOpen: bool = False                                   # plays with its original sound, before the narration

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class PanelStep(_Strict):
    from_: int = Field(alias="from", ge=0)                   # frame, relative to the group
    rows: list[DataRow]

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class QuestionWord(_Strict):
    text: str
    from_: int = Field(alias="from", ge=0)                   # relative to the group: when the voice says it

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class TimelineGroup(_Strict):
    id: str
    kind: Literal["datacard", "split", "stat", "question"]
    from_: int = Field(alias="from", ge=0)
    durationInFrames: int = Field(ge=1)
    title: str | None = None
    note: str | None = None
    steps: list[PanelStep] = Field(default_factory=list)     # datacard / split: rows revealed step by step
    stat: StatData | None = None
    words: list[QuestionWord] = Field(default_factory=list)  # question: script words revealed as spoken

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class TimelineSfx(_Strict):
    src: str
    from_: int = Field(alias="from", ge=0)
    volume: float = Field(gt=0, le=1)

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class TimelineClipAudio(_Strict):
    """Original sound of a cold-open clip (the only clip audio ever used)."""

    src: str
    from_: int = Field(alias="from", ge=0)
    durationInFrames: int = Field(ge=1)
    volume: float = Field(default=1.0, gt=0, le=1.5)

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class TimelineAudio(_Strict):
    voice: str
    voiceFrom: int = Field(default=0, ge=0)                  # the narration starts after the cold open
    clips: list[TimelineClipAudio] = Field(default_factory=list)
    music: str | None = None
    musicVolume: float = 0.25
    duckedVolume: float = 0.03                               # ≈ −18 dB below musicVolume while the voice speaks
    speech: list[tuple[int, int]] = Field(default_factory=list)   # [from, to) frames with narration
    sfx: list[TimelineSfx] = Field(default_factory=list)


class Timeline(_Strict):
    slug: str
    title: str
    fps: int
    width: int
    height: int
    durationInFrames: int = Field(ge=1)
    shots: list[TimelineShot]
    groups: list[TimelineGroup]
    labels: list[TimelineLabel] = Field(default_factory=list)
    audio: TimelineAudio

    @model_validator(mode="after")
    def _consistent(self) -> "Timeline":
        cursor = 0
        for shot in self.shots:
            if shot.from_ != cursor:
                raise ValueError(f"{shot.id}: empieza en el fotograma {shot.from_}, se esperaba {cursor}")
            cursor += shot.durationInFrames
            if shot.type != "datacard" and shot.media is None:
                raise ValueError(f"{shot.id}: plano {shot.type} sin medio")
            if shot.media and shot.media.source != "generated" and not (shot.media.credit or "").startswith("Fuente: "):
                raise ValueError(f"{shot.id}: medio de terceros sin crédito")
            if shot.media and shot.media.kind == "video" and shot.media.source == "youtube" \
                    and shot.durationInFrames > MAX_THIRD_PARTY_SECONDS * self.fps + 1:
                raise ValueError(f"{shot.id}: clip de terceros de más de 5 s")
        if cursor != self.durationInFrames:
            raise ValueError(f"Los planos suman {cursor} fotogramas y el vídeo dura {self.durationInFrames}")
        return self
