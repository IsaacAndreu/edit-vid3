from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .candidate_analyzer import DeepSeekVisualJudge, ScoredSegment, create_contact_sheet, score_candidate_segments
from .clients.youtube_client import YouTubeCandidate, YouTubeClient


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

    @property
    def duration_seconds(self) -> float:
        return self.end_seconds - self.start_seconds


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
    preview_with_storyboards: bool = True,
    min_visual_score: float = 0.55,
) -> SelectedThirdPartyClip | None:
    """Search, shortlist by subtitle timing, then ask vision to verify real frames.

    With ``preview_with_storyboards`` the finalists are first ranked from their
    seek-bar storyboard thumbnails (CDN images, no media download) and only the
    winner is downloaded and verified on real frames; the next finalist is tried
    when the verification fails. Videos without storyboards keep the previous
    behaviour of downloading every finalist.
    """

    if not visual_intent.strip() and not keywords:
        return None

    found: dict[str, YouTubeCandidate] = {}
    for query in _queries(visual_intent, keywords, transcript_context):
        try:
            for candidate in youtube.search(query, limit=search_results_per_query):
                if candidate.video_id not in used_video_ids:
                    found.setdefault(candidate.video_id, candidate)
        except Exception as error:
            print(f"Aviso: búsqueda YouTube fallida para {query!r}: {error}")

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
        return None

    clip_dir = assets_dir / "third-party" / "clips"
    sheet_dir = assets_dir / "third-party" / "contact-sheets"

    judge_intent = visual_intent.strip()
    if selection_guidance.strip():
        judge_intent = f"{judge_intent}\n\nAdditional visual criteria: {selection_guidance.strip()}"

    order = list(range(len(finalists)))
    preview_scores: dict[int, float] = {}
    if preview_with_storyboards and len(finalists) > 1:
        order, preview_scores = _rank_by_storyboard_preview(finalists, youtube, judge, judge_intent, sheet_dir)

    if not preview_scores:
        return _download_all_and_judge(
            finalists, youtube, judge, judge_intent, clip_dir, sheet_dir, used_video_ids, min_visual_score
        )

    # Storyboards already ranked the finalists without downloading anything.
    # Download the best one only; verify it on real frames and move to the next
    # finalist when the verification fails.
    for position in order:
        segment = finalists[position]
        try:
            clip_path = youtube.download_clip(
                segment.candidate,
                segment.start_seconds,
                segment.end_seconds,
                clip_dir,
                max_clip_seconds=5.0,
            )
            sheet_path = sheet_dir / f"candidate-{position + 1:02d}-{clip_path.stem}.jpg"
            create_contact_sheet(clip_path, sheet_path, frame_count=4)
        except Exception as error:
            print(f"Aviso: no se pudo preparar clip {segment.candidate.video_id}: {error}")
            continue
        try:
            judgments = judge.judge(judge_intent, [segment], [sheet_path])
        except Exception as error:
            print(f"Aviso: evaluación visual DeepSeek fallida; se usa el fallback de media: {error}")
            return None
        if not judgments:
            continue
        _, visual_score, reason = judgments[0]
        visual_score = float(visual_score)
        if visual_score < min_visual_score:
            print(
                f"Aviso: clip {segment.candidate.video_id} descartado tras verificar frames reales "
                f"({visual_score:.2f}); se prueba el siguiente finalista."
            )
            continue
        used_video_ids.add(segment.candidate.video_id)
        return SelectedThirdPartyClip(
            path=clip_path,
            candidate=segment.candidate,
            start_seconds=segment.start_seconds,
            end_seconds=segment.end_seconds,
            transcript_excerpt=segment.transcript_excerpt,
            relevance_score=segment.relevance_score,
            visual_score=visual_score,
            reason=str(reason),
        )
    print("Aviso: ningún clip de terceros superó relevancia visual suficiente.")
    return None


def _rank_by_storyboard_preview(
    finalists: list[ScoredSegment],
    youtube: YouTubeClient,
    judge: DeepSeekVisualJudge,
    judge_intent: str,
    sheet_dir: Path,
) -> tuple[list[int], dict[int, float]]:
    """Order finalists by a vision pass over seek-bar storyboards (no media download).

    Returns the original order and no scores when any finalist lacks a
    storyboard or the judge fails, so the caller falls back to downloading.
    """

    storyboard_sheet = getattr(youtube, "storyboard_sheet", None)
    if storyboard_sheet is None:
        return list(range(len(finalists))), {}
    sheets: list[Path] = []
    for index, segment in enumerate(finalists, start=1):
        preview_path = sheet_dir / f"preview-{index:02d}-{segment.candidate.video_id}.jpg"
        try:
            sheet = storyboard_sheet(
                segment.candidate,
                segment.start_seconds,
                segment.end_seconds,
                preview_path,
            )
        except Exception:
            sheet = None
        if sheet is None:
            return list(range(len(finalists))), {}
        sheets.append(Path(sheet))
    preview_intent = (
        f"{judge_intent}\n\nThese contact sheets are low-resolution seek-bar storyboard thumbnails "
        "sampled inside each candidate's time range; rank the candidates by how likely the real "
        "footage matches the intent."
    )
    try:
        judgments = judge.judge(preview_intent, finalists, sheets)
    except Exception as error:
        print(f"Aviso: previsualización por storyboards fallida; se descargan los finalistas: {error}")
        return list(range(len(finalists))), {}
    scores = {
        int(index): float(score)
        for index, score, _reason in judgments
        if 0 <= int(index) < len(finalists)
    }
    if len(scores) != len(finalists):
        return list(range(len(finalists))), {}
    order = sorted(range(len(finalists)), key=lambda index: (-scores[index], index))
    return order, scores


def _download_all_and_judge(
    finalists: list[ScoredSegment],
    youtube: YouTubeClient,
    judge: DeepSeekVisualJudge,
    judge_intent: str,
    clip_dir: Path,
    sheet_dir: Path,
    used_video_ids: set[str],
    min_visual_score: float,
) -> SelectedThirdPartyClip | None:
    downloaded: list[ScoredSegment] = []
    downloaded_paths: list[Path] = []
    contact_sheets: list[Path] = []
    for index, segment in enumerate(finalists, start=1):
        try:
            clip_path = youtube.download_clip(
                segment.candidate,
                segment.start_seconds,
                segment.end_seconds,
                clip_dir,
                max_clip_seconds=5.0,
            )
            sheet_path = sheet_dir / f"candidate-{index:02d}-{clip_path.stem}.jpg"
            create_contact_sheet(clip_path, sheet_path, frame_count=4)
        except Exception as error:
            print(f"Aviso: no se pudo preparar clip {segment.candidate.video_id}: {error}")
            continue
        downloaded.append(segment)
        downloaded_paths.append(clip_path)
        contact_sheets.append(sheet_path)

    if not downloaded:
        return None

    try:
        judgments = judge.judge(judge_intent, downloaded, contact_sheets)
    except Exception as error:
        # A transcript-only score is not enough to declare the visual relevant.
        print(f"Aviso: evaluación visual DeepSeek fallida; se usa el fallback de media: {error}")
        return None

    choices = [
        (candidate_index, float(score), str(reason))
        for candidate_index, score, reason in judgments
        if 0 <= candidate_index < len(downloaded)
    ]
    if not choices:
        return None

    selected_index, visual_score, reason = max(choices, key=lambda item: item[1])
    if visual_score < min_visual_score:
        print(f"Aviso: ningún clip de terceros superó relevancia visual suficiente ({visual_score:.2f}).")
        return None

    selected_segment = downloaded[selected_index]
    selected_path = downloaded_paths[selected_index]
    used_video_ids.add(selected_segment.candidate.video_id)
    return SelectedThirdPartyClip(
        path=selected_path,
        candidate=selected_segment.candidate,
        start_seconds=selected_segment.start_seconds,
        end_seconds=selected_segment.end_seconds,
        transcript_excerpt=selected_segment.transcript_excerpt,
        relevance_score=selected_segment.relevance_score,
        visual_score=visual_score,
        reason=reason,
    )


def public_asset_url(path: Path, project_root: Path) -> str:
    """Convert a local file under public/ to a Remotion URL."""

    public_dir = (project_root / "public").resolve()
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(public_dir)
    except ValueError as error:
        raise ValueError(f"El clip seleccionado debe vivir en {public_dir}.") from error
    return f"/{relative.as_posix()}"
