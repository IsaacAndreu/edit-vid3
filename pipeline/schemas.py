"""Pydantic schemas for the JSON files exchanged between stages."""

from __future__ import annotations

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
