from __future__ import annotations

import base64
import json
import math
import mimetypes
import re
import subprocess
import unicodedata
from dataclasses import dataclass
from pathlib import Path
import requests

from .clients.youtube_client import YouTubeCandidate


@dataclass(frozen=True)
class ScoredSegment:
    candidate: YouTubeCandidate
    start_seconds: float
    end_seconds: float
    relevance_score: float
    transcript_excerpt: str
    rationale: str = ""


_STOPWORDS = frozenset(
    "a an and are as at be by for from in into is it of on or that the this to with "
    "was were will you your el la las los un una unos unas de del y o en con por para "
    "que es al como lo se su sus sobre entre desde hasta".split()
)


def _normalize_tokens(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKD", text.casefold())
    without_marks = "".join(char for char in normalized if not unicodedata.combining(char))
    return [token for token in re.findall(r"[a-z0-9]+", without_marks) if token not in _STOPWORDS]


def _phrase_tokens(text: str) -> tuple[str, ...]:
    return tuple(_normalize_tokens(text))


def _phrase_appears(phrase: tuple[str, ...], transcript: list[str]) -> bool:
    if not phrase or len(phrase) < 2 or len(phrase) > len(transcript):
        return False
    return any(
        tuple(transcript[index : index + len(phrase)]) == phrase
        for index in range(len(transcript) - len(phrase) + 1)
    )


def _metadata_nudge(candidate: YouTubeCandidate, query_tokens: set[str]) -> float:
    metadata_tokens = set(_normalize_tokens(f"{candidate.title} {candidate.description}"))
    overlap = len(query_tokens & metadata_tokens)
    return 0.04 * overlap / len(query_tokens) if query_tokens else 0.0


def score_candidate_segments(
    candidate: YouTubeCandidate,
    visual_intent: str,
    keywords: list[str],
    *,
    max_clip_seconds: float = 5.0,
    top_k: int = 3,
) -> list[ScoredSegment]:
    """Rank transcript-supported windows; the absolute clip limit is five seconds."""

    if not math.isfinite(max_clip_seconds) or max_clip_seconds <= 0:
        raise ValueError("max_clip_seconds must be a finite number greater than zero.")
    if top_k <= 0:
        return []
    clip_limit_seconds = min(max_clip_seconds, 5.0)

    phrase_sources = [visual_intent, *keywords]
    phrases = [phrase for phrase in (_phrase_tokens(source) for source in phrase_sources) if phrase]
    query_tokens = {token for phrase in phrases for token in phrase}
    if not query_tokens:
        return []

    try:
        candidate_duration = float(candidate.duration_seconds)
    except (TypeError, ValueError):
        candidate_duration = math.inf
    if not math.isfinite(candidate_duration) or candidate_duration <= 0:
        candidate_duration = math.inf

    cues: list[tuple[float, float, str, int]] = []
    for index, cue in enumerate(candidate.subtitles):
        try:
            start = float(cue.start_seconds)
            end = float(cue.end_seconds)
        except (AttributeError, TypeError, ValueError):
            continue
        text = str(getattr(cue, "text", "")).strip()
        if not math.isfinite(start) or not math.isfinite(end) or not text or end <= start:
            continue
        start = max(0.0, start)
        end = min(end, candidate_duration)
        if end > start and _normalize_tokens(text):
            cues.append((start, end, text, index))

    cues.sort(key=lambda cue: (cue[0], cue[1], cue[3]))
    if not cues:
        return []

    metadata_nudge = _metadata_nudge(candidate, query_tokens)
    # Metadata is a tie-break nudge only: subtitle evidence determines eligibility
    # and contributes at least 96% of the final score.
    subtitle_threshold = 0.16
    found: dict[tuple[float, float, str], tuple[float, ScoredSegment]] = {}

    for first_index, (start, _, _, _) in enumerate(cues):
        if start >= candidate_duration:
            continue
        clip_limit = min(start + clip_limit_seconds, candidate_duration)
        for last_index in range(first_index, len(cues)):
            end = max(cue[1] for cue in cues[first_index : last_index + 1])
            if cues[last_index][0] >= clip_limit:
                break
            end = min(end, clip_limit)
            if end <= start:
                continue

            overlapping = [
                cue for cue in cues[first_index : last_index + 1]
                if cue[0] < end and cue[1] > start
            ]
            excerpt = " ".join(cue[2] for cue in overlapping).strip()
            transcript_tokens = _normalize_tokens(excerpt)
            if not transcript_tokens:
                continue

            overlap = query_tokens & set(transcript_tokens)
            if not overlap:
                continue
            coverage = len(overlap) / len(query_tokens)
            precision = len(overlap) / len(set(transcript_tokens))
            f1 = (2 * coverage * precision / (coverage + precision)) if coverage + precision else 0.0
            phrase_match = any(_phrase_appears(phrase, transcript_tokens) for phrase in phrases)
            phrase_bonus = 0.04 if phrase_match else 0.0
            subtitle_score = min(1.0, 0.65 * coverage + 0.35 * f1 + phrase_bonus)
            if subtitle_score < subtitle_threshold or (len(overlap) < 2 and len(query_tokens) > 1 and not phrase_match):
                continue

            final_score = min(1.0, subtitle_score * (1.0 - 0.04) + metadata_nudge)
            matched = sorted(overlap)
            metadata_note = f"; title/description nudge +{metadata_nudge:.3f}" if metadata_nudge else ""
            rationale = (
                f"Subtitle evidence matches {len(overlap)}/{len(query_tokens)} intent terms "
                f"({', '.join(matched[:8])}){metadata_note}."
            )
            segment = ScoredSegment(
                candidate=candidate,
                start_seconds=round(start, 3),
                end_seconds=round(end, 3),
                relevance_score=round(final_score, 6),
                transcript_excerpt=excerpt,
                rationale=rationale,
            )
            key = (segment.start_seconds, segment.end_seconds, excerpt)
            current = found.get(key)
            if current is None or subtitle_score > current[0]:
                found[key] = (subtitle_score, segment)

    ranked = sorted(
        found.values(),
        key=lambda item: (
            -item[1].relevance_score,
            -item[0],
            item[1].start_seconds,
            item[1].end_seconds,
            item[1].transcript_excerpt,
        ),
    )
    return [segment for _, segment in ranked[:top_k]]


def create_contact_sheet(
    clip_path: Path,
    output_path: Path,
    *,
    frame_count: int = 4,
) -> Path:
    """Sample evenly spaced frames into a tiled contact sheet using ffmpeg."""

    clip_path = Path(clip_path)
    output_path = Path(output_path)
    if not isinstance(frame_count, int) or isinstance(frame_count, bool) or frame_count < 1:
        raise ValueError("frame_count must be a positive integer.")
    if not clip_path.is_file():
        raise FileNotFoundError(f"Clip not found: {clip_path}")
    if clip_path.resolve() == output_path.resolve():
        raise ValueError("The contact-sheet output path must differ from the clip path.")

    try:
        probe = subprocess.run(
            [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "json", str(clip_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("ffprobe was not found; install ffmpeg/ffprobe and add it to PATH.") from exc
    if probe.returncode != 0:
        detail = (probe.stderr or "").strip()[:400]
        raise RuntimeError(f"Could not read clip duration with ffprobe. {detail}".strip())
    try:
        duration = float(json.loads(probe.stdout)["format"]["duration"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("ffprobe returned no valid clip duration.") from exc
    if not math.isfinite(duration) or duration <= 0:
        raise RuntimeError("ffprobe returned a non-positive clip duration.")

    columns = math.ceil(math.sqrt(frame_count))
    rows = math.ceil(frame_count / columns)
    fps = frame_count / duration
    sample_start = duration / (2 * frame_count)
    filter_graph = (
        f"fps={fps:.10f}:start_time={sample_start:.10f},"
        "scale=320:-1:force_original_aspect_ratio=decrease,"
        f"tile={columns}x{rows}:nb_frames={frame_count}:padding=2:margin=2"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(clip_path),
                "-vf", filter_graph, "-frames:v", "1", str(output_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("ffmpeg was not found; install ffmpeg and add it to PATH.") from exc
    if result.returncode != 0:
        detail = (result.stderr or "").strip()[:500]
        raise RuntimeError(f"ffmpeg could not create the contact sheet. {detail}".strip())
    if not output_path.is_file():
        raise RuntimeError(f"ffmpeg completed without creating the contact sheet: {output_path}")
    return output_path


class DeepSeekVisualJudge:
    """Optional, explicit-call visual judge using DeepSeek's Responses API."""

    def __init__(
        self,
        api_key: str,
        model: str = "deepseek-flash",
        base_url: str = "https://api.deepseek.com",
        timeout_seconds: float = 45,
    ) -> None:
        if not api_key.strip():
            raise ValueError("A DeepSeek API key is required for visual judging.")
        if not model.strip():
            raise ValueError("The DeepSeek model cannot be empty.")
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be a finite number greater than zero.")
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    def judge(
        self,
        visual_intent: str,
        candidates: list[ScoredSegment],
        contact_sheets: list[Path],
    ) -> list[tuple[int, float, str]]:
        if len(candidates) != len(contact_sheets):
            raise ValueError("Provide exactly one contact sheet for each candidate segment.")
        if not candidates:
            return []
        if not visual_intent.strip():
            raise ValueError("visual_intent cannot be empty when requesting visual judging.")

        content: list[dict[str, object]] = [
            {
                "type": "input_text",
                "text": (
                    "Judge how well each contact sheet visually matches the requested intent. "
                    "Subtitle evidence is context, not proof of what appears in the image. "
                    "Return one judgment for every candidate. candidate_index is zero-based.\n\n"
                    f"Visual intent: {visual_intent.strip()}\n\n"
                    + "\n".join(
                        f"Candidate {index}: time {candidate.start_seconds:.3f}-"
                        f"{candidate.end_seconds:.3f}s; subtitles: {candidate.transcript_excerpt!r}; "
                        f"subtitle relevance: {candidate.relevance_score:.3f}."
                        for index, candidate in enumerate(candidates)
                    )
                ),
            }
        ]
        for index, image_path in enumerate(contact_sheets):
            path = Path(image_path)
            if not path.is_file():
                raise FileNotFoundError(f"Contact sheet not found for candidate {index}: {path}")
            mime_type, _ = mimetypes.guess_type(path.name)
            if mime_type not in {"image/png", "image/jpeg", "image/webp", "image/gif"}:
                raise ValueError(f"Unsupported contact-sheet image type: {path.suffix or '(no extension)'}")
            image_data = base64.b64encode(path.read_bytes()).decode("ascii")
            content.append(
                {"type": "input_text", "text": f"Contact sheet for candidate {index}:"}
            )
            content.append(
                {
                    "type": "input_image",
                    "image_url": f"data:{mime_type};base64,{image_data}",
                }
            )

        schema = {
            "type": "object",
            "properties": {
                "judgments": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "candidate_index": {"type": "integer"},
                            "score": {"type": "number", "minimum": 0, "maximum": 1},
                            "reason": {"type": "string"},
                        },
                        "required": ["candidate_index", "score", "reason"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["judgments"],
            "additionalProperties": False,
        }
        payload = {
            "model": self._model,
            "input": [{"role": "user", "content": content}],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "visual_candidate_judgments",
                    "strict": True,
                    "schema": schema,
                }
            },
        }
        try:
            response = requests.post(
                f"{self._base_url}/v1/responses",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self._timeout_seconds,
            )
        except requests.RequestException:
            raise RuntimeError(
                "DeepSeek visual judging request failed; check connectivity, credentials, and model availability."
            ) from None
        if response.status_code >= 400:
            raise RuntimeError(f"DeepSeek visual judging failed with HTTP {response.status_code}.")
        try:
            response_payload = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError("DeepSeek visual judging returned an invalid response body.") from exc

        output_text = self._extract_output_text(response_payload)
        try:
            decoded = json.loads(output_text)
        except (TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError("DeepSeek visual judging returned invalid JSON judgments.") from exc
        judgments = decoded.get("judgments") if isinstance(decoded, dict) else None
        if not isinstance(judgments, list) or len(judgments) != len(candidates):
            raise ValueError("DeepSeek returned a candidate count that does not match the request.")

        validated: dict[int, tuple[int, float, str]] = {}
        for item in judgments:
            if not isinstance(item, dict):
                raise ValueError("DeepSeek returned a judgment with an invalid shape.")
            index = item.get("candidate_index")
            score = item.get("score")
            reason = item.get("reason")
            if (
                isinstance(index, bool)
                or not isinstance(index, int)
                or index < 0
                or index >= len(candidates)
                or index in validated
            ):
                raise ValueError("DeepSeek returned duplicate or out-of-range candidate indices.")
            if isinstance(score, bool) or not isinstance(score, (int, float)):
                raise ValueError(f"DeepSeek returned a non-numeric score for candidate {index}.")
            numeric_score = float(score)
            if not math.isfinite(numeric_score) or not 0.0 <= numeric_score <= 1.0:
                raise ValueError(f"DeepSeek returned an out-of-range score for candidate {index}.")
            if not isinstance(reason, str) or not reason.strip():
                raise ValueError(f"DeepSeek returned no explanation for candidate {index}.")
            validated[index] = (index, numeric_score, reason.strip())
        if set(validated) != set(range(len(candidates))):
            raise ValueError("DeepSeek omitted one or more candidate indices.")
        return [validated[index] for index in range(len(candidates))]

    @staticmethod
    def _extract_output_text(response_payload: object) -> str:
        if not isinstance(response_payload, dict):
            raise RuntimeError("DeepSeek visual judging returned an unexpected response shape.")
        direct = response_payload.get("output_text")
        if isinstance(direct, str):
            return direct
        output = response_payload.get("output")
        if isinstance(output, list):
            chunks = [
                item.get("text")
                for message in output
                if isinstance(message, dict)
                for item in message.get("content", [])
                if isinstance(item, dict) and item.get("type") == "output_text" and isinstance(item.get("text"), str)
            ]
            if chunks:
                return "\n".join(chunks)
        raise RuntimeError("DeepSeek visual judging response contained no output text.")
