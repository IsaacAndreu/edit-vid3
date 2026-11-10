from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Collection

from .candidate_analyzer import DeepSeekVisualJudge, ScoredSegment, create_contact_sheet, score_candidate_segments
from .clients.youtube_client import YouTubeCandidate, YouTubeClient
from .runlog import log, short_error


# A clip is only used when the vision model sees the intent in its real frames.
MIN_VISUAL_SCORE = 0.55
JUDGE_ATTEMPTS = 2
JUDGE_RETRY_DELAY_SECONDS = 2.0

OUTCOME_SELECTED = "selected"
OUTCOME_NO_QUERY = "no-query"
OUTCOME_SEARCH_FAILED = "search-failed"
OUTCOME_NO_CANDIDATES = "no-candidates"
OUTCOME_NO_SUBTITLE_MATCH = "no-subtitle-match"
OUTCOME_DOWNLOAD_FAILED = "download-failed"
OUTCOME_JUDGE_FAILED = "judge-failed"
OUTCOME_BELOW_THRESHOLD = "below-threshold"
OUTCOME_ALREADY_USED = "already-used"


@dataclass(frozen=True)
class SelectedThirdPartyClip:
    path: Path
    candidate: YouTubeCandidate
    start_seconds: float
    end_seconds: float
    transcript_excerpt: str
    relevance_score: float
    visual_score: float
    reason: str
    contact_sheet: Path | None = None

    @property
    def duration_seconds(self) -> float:
        return self.end_seconds - self.start_seconds


@dataclass
class SelectionTrace:
    """Audit record of one selection attempt: what was searched, compared and why."""

    outcome: str = ""
    queries: list[str] = field(default_factory=list)
    search_errors: list[str] = field(default_factory=list)
    videos_found: int = 0
    finalists: list[dict[str, Any]] = field(default_factory=list)
    best_visual_score: float | None = None
    judge_error: str = ""
    seconds: dict[str, float] = field(default_factory=dict)

    @property
    def all_searches_failed(self) -> bool:
        return bool(self.queries) and len(self.search_errors) >= len(self.queries)

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "outcome": self.outcome,
            "queries": list(self.queries),
            "videosFound": self.videos_found,
            "finalists": [dict(item) for item in self.finalists],
            "seconds": {key: round(value, 2) for key, value in self.seconds.items()},
        }
        if self.search_errors:
            payload["searchErrors"] = list(self.search_errors)
        if self.best_visual_score is not None:
            payload["bestVisualScore"] = round(self.best_visual_score, 3)
        if self.judge_error:
            payload["judgeError"] = self.judge_error
        return payload


def _queries(visual_intent: str, keywords: list[str], transcript_context: str = "") -> list[str]:
    candidates = [visual_intent, transcript_context, *keywords]
    queries: list[str] = []
    seen: set[str] = set()
    for query in candidates:
        cleaned = " ".join(str(query).strip().split())
        normalized = cleaned.casefold()
        if cleaned and normalized not in seen:
            seen.add(normalized)
            queries.append(cleaned)
        if len(queries) >= 3:
            break
    return queries


_SHEET_LOCKS: dict[str, threading.Lock] = {}
_SHEET_LOCKS_GUARD = threading.Lock()


def _sheet_lock(path: Path) -> threading.Lock:
    with _SHEET_LOCKS_GUARD:
        return _SHEET_LOCKS.setdefault(str(path), threading.Lock())


def _map_in_order(function: Any, items: list[Any], parallel: int) -> list[Any]:
    """Run ``function`` over ``items`` concurrently, returning results in input order."""

    if parallel <= 1 or len(items) <= 1:
        return [function(item) for item in items]
    with ThreadPoolExecutor(max_workers=min(parallel, len(items)), thread_name_prefix="yt") as pool:
        return list(pool.map(function, items))


def _judge_with_retry(
    judge: DeepSeekVisualJudge,
    intent: str,
    segments: list[ScoredSegment],
    contact_sheets: list[Path],
) -> list[tuple[int, float, str]]:
    """One transient API failure must not waste clips that are already downloaded."""

    last_error: Exception | None = None
    for attempt in range(1, JUDGE_ATTEMPTS + 1):
        try:
            return judge.judge(intent, segments, contact_sheets)
        except Exception as error:
            last_error = error
            if attempt < JUDGE_ATTEMPTS:
                log.debug("Juez visual falló (intento %s): %s", attempt, short_error(error))
                time.sleep(JUDGE_RETRY_DELAY_SECONDS)
    assert last_error is not None
    raise last_error


def select_third_party_clip(
    *,
    visual_intent: str,
    keywords: list[str],
    transcript_context: str = "",
    selection_guidance: str = "",
    youtube: YouTubeClient,
    judge: DeepSeekVisualJudge,
    assets_dir: Path,
    used_video_ids: set[str],
    search_results_per_query: int = 4,
    max_candidates_for_vision: int = 3,
    excluded_video_ids: Collection[str] = (),
    claim_lock: threading.Lock | None = None,
    parallel: int = 3,
    trace: SelectionTrace | None = None,
) -> SelectedThirdPartyClip | None:
    """Search, shortlist by subtitle timing, then ask vision to verify real frames.

    ``used_video_ids`` is shared between scenes: the winner is claimed under
    ``claim_lock`` so two scenes resolved in parallel never show the same video.
    ``trace`` (optional) receives the full audit of the attempt.
    """

    trace = trace if trace is not None else SelectionTrace()
    if not visual_intent.strip() and not keywords:
        trace.outcome = OUTCOME_NO_QUERY
        return None

    blocked = set(excluded_video_ids)
    queries = _queries(visual_intent, keywords, transcript_context)
    trace.queries = list(queries)

    def run_search(query: str) -> list[YouTubeCandidate]:
        try:
            return list(youtube.search(query, limit=search_results_per_query))
        except Exception as error:
            trace.search_errors.append(f"{query!r}: {short_error(error)}")
            log.warning(f"Aviso: búsqueda YouTube fallida para {query!r}: {short_error(error)}")
            return []

    started = time.perf_counter()
    found: dict[str, YouTubeCandidate] = {}
    for results in _map_in_order(run_search, queries, parallel):
        for candidate in results:
            if candidate.video_id not in used_video_ids and candidate.video_id not in blocked:
                found.setdefault(candidate.video_id, candidate)
    trace.seconds["search"] = time.perf_counter() - started
    trace.videos_found = len(found)
    if not found:
        trace.outcome = OUTCOME_SEARCH_FAILED if trace.all_searches_failed else OUTCOME_NO_CANDIDATES
        return None

    scored: list[ScoredSegment] = []
    for candidate in found.values():
        scoring_terms = [*keywords]
        if transcript_context.strip():
            scoring_terms.append(transcript_context.strip())
        scored.extend(
            score_candidate_segments(
                candidate,
                visual_intent,
                scoring_terms,
                max_clip_seconds=5.0,
            )
        )

    # Compare different source videos, not multiple adjacent moments of the same video.
    finalists: list[ScoredSegment] = []
    finalist_video_ids: set[str] = set()
    for segment in sorted(scored, key=lambda item: item.relevance_score, reverse=True):
        if segment.candidate.video_id in finalist_video_ids:
            continue
        finalists.append(segment)
        finalist_video_ids.add(segment.candidate.video_id)
        if len(finalists) >= max_candidates_for_vision:
            break
    if not finalists:
        trace.outcome = OUTCOME_NO_SUBTITLE_MATCH
        return None

    clip_dir = assets_dir / "third-party" / "clips"
    sheet_dir = assets_dir / "third-party" / "contact-sheets"

    def prepare(item: tuple[int, ScoredSegment]) -> tuple[ScoredSegment, Path, Path] | None:
        index, segment = item
        try:
            clip_path = youtube.download_clip(
                segment.candidate,
                segment.start_seconds,
                segment.end_seconds,
                clip_dir,
                max_clip_seconds=5.0,
            )
            sheet_path = sheet_dir / f"candidate-{index:02d}-{clip_path.stem}.jpg"
            # Two scenes resolved in parallel may shortlist the same clip at the same rank.
            with _sheet_lock(sheet_path):
                create_contact_sheet(clip_path, sheet_path, frame_count=4)
        except Exception as error:
            log.warning(
                f"Aviso: no se pudo preparar clip {segment.candidate.video_id}: {short_error(error)}"
            )
            trace.finalists.append(
                {**_finalist_record(segment), "prepared": False, "error": short_error(error)}
            )
            return None
        return segment, clip_path, sheet_path

    started = time.perf_counter()
    prepared = [
        item
        for item in _map_in_order(prepare, list(enumerate(finalists, start=1)), parallel)
        if item is not None
    ]
    trace.seconds["download"] = time.perf_counter() - started
    if not prepared:
        trace.outcome = OUTCOME_DOWNLOAD_FAILED
        return None

    downloaded = [item[0] for item in prepared]
    downloaded_paths = [item[1] for item in prepared]
    contact_sheets = [item[2] for item in prepared]
    records = [
        {**_finalist_record(segment), "prepared": True, "clip": clip.name, "contactSheet": str(sheet)}
        for segment, clip, sheet in prepared
    ]
    trace.finalists.extend(records)

    started = time.perf_counter()
    try:
        judge_intent = visual_intent.strip()
        if selection_guidance.strip():
            judge_intent = f"{judge_intent}\n\nAdditional visual criteria: {selection_guidance.strip()}"
        judgments = _judge_with_retry(judge, judge_intent, downloaded, contact_sheets)
    except Exception as error:
        # A transcript-only score is not enough to declare the visual relevant.
        trace.seconds["judge"] = time.perf_counter() - started
        trace.judge_error = short_error(error)
        trace.outcome = OUTCOME_JUDGE_FAILED
        log.warning(
            f"Aviso: evaluación visual DeepSeek fallida; se usa el fallback de media: {short_error(error)}"
        )
        return None
    trace.seconds["judge"] = time.perf_counter() - started

    choices = [
        (candidate_index, float(score), str(reason))
        for candidate_index, score, reason in judgments
        if 0 <= candidate_index < len(downloaded)
    ]
    for candidate_index, score, reason in choices:
        records[candidate_index]["visualScore"] = round(score, 3)
        records[candidate_index]["reason"] = reason
    if not choices:
        trace.outcome = OUTCOME_JUDGE_FAILED
        return None

    ranked = sorted(choices, key=lambda item: item[1], reverse=True)
    trace.best_visual_score = ranked[0][1]
    if ranked[0][1] < MIN_VISUAL_SCORE:
        trace.outcome = OUTCOME_BELOW_THRESHOLD
        log.info(
            f"Aviso: ningún clip de terceros superó relevancia visual suficiente ({ranked[0][1]:.2f})."
        )
        return None

    selected: tuple[int, float, str] | None = None
    lock = claim_lock if claim_lock is not None else threading.Lock()
    with lock:
        for candidate_index, score, reason in ranked:
            if score < MIN_VISUAL_SCORE:
                break
            video_id = downloaded[candidate_index].candidate.video_id
            if video_id in used_video_ids:
                # Another scene resolved in parallel took this video first.
                continue
            used_video_ids.add(video_id)
            selected = (candidate_index, score, reason)
            break
    if selected is None:
        trace.outcome = OUTCOME_ALREADY_USED
        return None

    selected_index, visual_score, reason = selected
    records[selected_index]["selected"] = True
    trace.outcome = OUTCOME_SELECTED
    selected_segment = downloaded[selected_index]
    return SelectedThirdPartyClip(
        path=downloaded_paths[selected_index],
        candidate=selected_segment.candidate,
        start_seconds=selected_segment.start_seconds,
        end_seconds=selected_segment.end_seconds,
        transcript_excerpt=selected_segment.transcript_excerpt,
        relevance_score=selected_segment.relevance_score,
        visual_score=visual_score,
        reason=reason,
        contact_sheet=contact_sheets[selected_index],
    )


def _finalist_record(segment: ScoredSegment) -> dict[str, Any]:
    candidate = segment.candidate
    return {
        "videoId": candidate.video_id,
        "url": candidate.url,
        "title": candidate.title,
        "uploader": candidate.uploader or "",
        "startSeconds": segment.start_seconds,
        "endSeconds": segment.end_seconds,
        "relevanceScore": round(segment.relevance_score, 3),
        "transcriptExcerpt": segment.transcript_excerpt,
    }


def public_asset_url(path: Path, project_root: Path) -> str:
    """Convert a local file under public/ to a Remotion URL."""

    public_dir = (project_root / "public").resolve()
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(public_dir)
    except ValueError as error:
        raise ValueError(f"El clip seleccionado debe vivir en {public_dir}.") from error
    return f"/{relative.as_posix()}"
