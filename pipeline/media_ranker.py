from __future__ import annotations

import re
import unicodedata
from dataclasses import replace
from typing import Iterable

from .clients.pexels_client import PexelsAsset


_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


def _normalize(text: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFKD", text.lower())
        if not unicodedata.combining(character)
    )


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_PATTERN.findall(_normalize(text)))


def score_asset(
    asset: PexelsAsset,
    query: str,
    *,
    query_index: int,
    required_duration_seconds: float,
) -> float:
    """Rank an API candidate without pretending stock metadata is semantic truth."""

    query_tokens = _tokens(query)
    metadata_tokens = _tokens(asset.alt_text)
    overlap = len(query_tokens & metadata_tokens)
    score = 100.0 - (query_index * 6.0) - (asset.result_rank * 4.0)
    score += min(12.0, len(query_tokens) * 2.0)
    score += min(18.0, overlap * 6.0)

    if asset.width and asset.width >= 1920:
        score += 4.0
    if asset.height and asset.height >= 1080:
        score += 2.0

    if asset.kind == "video" and asset.duration_seconds is not None:
        duration_gap = required_duration_seconds - asset.duration_seconds
        if duration_gap <= 0:
            score += 16.0
        else:
            score -= min(24.0, duration_gap * 3.0)

    return score


def select_best_asset(
    candidates: Iterable[tuple[PexelsAsset, str, int]],
    *,
    required_duration_seconds: float,
) -> tuple[PexelsAsset, float, str] | None:
    ranked = [
        (
            score_asset(
                asset,
                query,
                query_index=query_index,
                required_duration_seconds=required_duration_seconds,
            ),
            asset,
            query,
        )
        for asset, query, query_index in candidates
    ]
    if not ranked:
        return None
    score, asset, query = max(ranked, key=lambda item: item[0])
    return replace(asset), score, query
