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


class ShotsFile(_Strict):
    slug: str
    title: str
    durationSeconds: float = Field(gt=0)
    context: str = ""                                        # global visual context from the outline pass
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
