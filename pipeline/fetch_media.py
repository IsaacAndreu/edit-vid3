"""Media stage: third-party YouTube clips first, then Pexels, then GPT Image.

The work runs in phases so the slow part can go in parallel while the result
stays predictable:

1. plan every scene (what media its template needs, if any);
2. reuse what a previous run already resolved (checkpoint);
3. YouTube selection for the remaining scenes, several scenes at a time;
4. Pexels for whatever YouTube did not cover, in scene order;
5. local copies of the chosen Pexels files;
6. generated images as the last resort.
"""

from __future__ import annotations

import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .candidate_analyzer import DeepSeekVisualJudge
from .checkpoint import MediaCheckpoint, scene_fingerprint
from .clients.pexels_client import PexelsAsset, PexelsClient, PexelsError, PexelsRateLimitError
from .clients.youtube_client import YouTubeClient, YouTubeClientError
from .config import DEFAULT_MEDIA_CONCURRENCY, REMOTION_FPS, Settings
from .media_ranker import select_best_asset
from .media_tools import MediaToolError, probe_duration_seconds
from .runlog import log, short_error
from .templates import MEDIA_NONE, MEDIA_SHOTS, TemplateSpec, load_manifest
from .third_party_media import (
    OUTCOME_ALREADY_USED,
    OUTCOME_BELOW_THRESHOLD,
    OUTCOME_DOWNLOAD_FAILED,
    OUTCOME_JUDGE_FAILED,
    OUTCOME_NO_CANDIDATES,
    OUTCOME_NO_QUERY,
    OUTCOME_NO_SUBTITLE_MATCH,
    OUTCOME_SEARCH_FAILED,
    OUTCOME_SELECTED,
    SelectedThirdPartyClip,
    SelectionTrace,
    public_asset_url,
    select_third_party_clip,
)
from .timing import METRICS
from .types import SceneDraft


class MediaFetchError(RuntimeError):
    """Raised when a scene cannot be provided with its required media."""


_MANIFEST = load_manifest()
MONTAGE_TEMPLATES = {name for name, spec in _MANIFEST.templates.items() if spec.media == MEDIA_SHOTS}
YOUTUBE_MEDIA_TEMPLATES = {name for name, spec in _MANIFEST.templates.items() if spec.third_party}

OUTCOME_YOUTUBE_UNAVAILABLE = "youtube-unavailable"
OUTCOME_ERROR = "error"
# A miss with one of these outcomes is final for the scene; anything else
# (network, API, breaker) is worth retrying when the run is resumed.
_FINAL_MISS_OUTCOMES = {
    OUTCOME_NO_QUERY,
    OUTCOME_NO_CANDIDATES,
    OUTCOME_NO_SUBTITLE_MATCH,
    OUTCOME_BELOW_THRESHOLD,
}
# Misses caused by an outage rather than by the candidates themselves. A scene
# that fell back because of one of these is not stored as final, so the next
# run of the same command tries YouTube again for it.
_TRANSIENT_OUTCOMES = {
    OUTCOME_SEARCH_FAILED,
    OUTCOME_JUDGE_FAILED,
    OUTCOME_YOUTUBE_UNAVAILABLE,
    OUTCOME_ERROR,
}
_OUTCOME_LABELS = {
    OUTCOME_NO_QUERY: "sin consulta",
    OUTCOME_SEARCH_FAILED: "búsquedas fallidas",
    OUTCOME_NO_CANDIDATES: "sin resultados",
    OUTCOME_NO_SUBTITLE_MATCH: "sin coincidencia en subtítulos",
    OUTCOME_DOWNLOAD_FAILED: "descarga fallida",
    OUTCOME_JUDGE_FAILED: "juez visual falló",
    OUTCOME_BELOW_THRESHOLD: "relevancia visual insuficiente",
    OUTCOME_ALREADY_USED: "vídeo ya usado en otra escena",
    OUTCOME_YOUTUBE_UNAVAILABLE: "YouTube desactivado",
    OUTCOME_ERROR: "error inesperado",
}

YOUTUBE_BREAKER_THRESHOLD = 3
PEXELS_BREAKER_THRESHOLD = 3
IMAGE_ATTEMPTS = 2

KIND_AVATAR = "avatar"
KIND_NONE = "none"
KIND_OVERRIDE = "override"
KIND_SINGLE = "single"
KIND_SHOTS = "shots"

_VIDEO_SUFFIXES = {".mp4", ".mov", ".webm", ".m4v"}
_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


@dataclass
class MediaOptions:
    third_party_enabled: bool = True
    concurrency: int = DEFAULT_MEDIA_CONCURRENCY
    download_stock: bool = True
    checkpoint_path: Path | None = None
    # False ignores (and overwrites) whatever a previous run stored.
    resume: bool = True
    # 1-based scene numbers to resolve again, avoiding their previous pick.
    redo_scenes: frozenset[int] = frozenset()


@dataclass
class _Plan:
    index: int
    scene: SceneDraft
    kind: str
    spec: TemplateSpec | None
    keywords: list[str] = field(default_factory=list)
    third_party: bool = False
    slots: list[str | None] = field(default_factory=list)
    fingerprint: str = ""

    @property
    def number(self) -> int:
        return self.index + 1


def _public_url(path: Path, project_root: Path) -> str:
    return public_asset_url(path, project_root)


def _avatar_source(scene: SceneDraft, avatar_dir: Path | None, scene_index: int) -> Path | str | None:
    configured = scene.get("videoUrl") or scene.get("avatar_path")
    if configured:
        path = Path(str(configured)).expanduser()
        return path if path.exists() else str(configured)

    if avatar_dir:
        candidates = sorted(
            path
            for path in avatar_dir.expanduser().glob(f"scene-{scene_index + 1:03d}.*")
            if path.suffix.lower() in {".mp4", ".mov", ".webm"}
        )
        if candidates:
            return candidates[0]
    return None


def _copy_local_avatar(
    source: Path,
    target_dir: Path,
    project_root: Path,
    scene_index: int,
) -> str:
    if not source.is_file():
        raise MediaFetchError(f"No existe el clip de avatar: {source}")
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"avatar-{scene_index + 1:03d}{source.suffix.lower()}"
    shutil.copy2(source, target)
    return _public_url(target, project_root)


def _visual_prompt(scene: SceneDraft, keywords: list[str]) -> str:
    text = scene.get("text", "").strip()
    keyword_text = ", ".join(keywords) or text
    return (
        "Cinematic 16:9 b-roll image for a YouTube documentary scene. "
        "Natural composition, realistic lighting, no text, no logos, no watermark. "
        f"Scene context: {text}. Visual keywords: {keyword_text}."
    )


def _assign_asset(
    scene: SceneDraft,
    asset: PexelsAsset,
    *,
    query: str | None = None,
    relevance_score: float | None = None,
) -> None:
    if asset.kind == "video":
        scene["videoUrl"] = asset.url
        if asset.duration_seconds is not None:
            scene["videoDurationInSeconds"] = asset.duration_seconds
    else:
        scene["imageUrl"] = asset.url
    scene["mediaSourceUrl"] = asset.source_url
    scene["mediaProvider"] = "pexels"
    if query:
        scene["mediaQuery"] = query
    if relevance_score is not None:
        scene["mediaRelevanceScore"] = round(relevance_score, 2)
    if asset.photographer:
        scene["mediaPhotographer"] = asset.photographer
    if asset.thumbnail_url:
        scene["mediaThumbnailUrl"] = asset.thumbnail_url


def _assign_montage_shots(
    scene: SceneDraft,
    keywords: list[str],
    pexels: PexelsClient,
    used_asset_urls: set[str],
    *,
    prefer_video: bool,
    existing_shots: list[dict[str, Any]] | None = None,
) -> bool:
    shots: list[dict[str, Any]] = list(existing_shots or [])
    existing_urls = {str(shot.get("url")) for shot in shots if isinstance(shot, dict)}
    shot_duration_seconds = (
        float(scene.get("durationInFrames", 1)) / REMOTION_FPS / max(1, min(4, len(keywords)))
    )
    for keyword in keywords[:4]:
        candidates = _asset_candidates(
            pexels,
            [keyword],
            used_asset_urls,
            prefer_video=prefer_video,
        )
        selected = select_best_asset(
            candidates,
            required_duration_seconds=shot_duration_seconds,
        )
        asset = selected[0] if selected else None
        if asset is None:
            continue
        if asset.url in existing_urls:
            continue
        shot: dict[str, Any] = {"url": asset.url, "type": asset.kind}
        if selected:
            shot["query"] = selected[2]
            shot["relevanceScore"] = round(selected[1], 2)
        shot["sourceUrl"] = asset.source_url
        shot["provider"] = "pexels"
        if asset.photographer:
            shot["photographer"] = asset.photographer
        if asset.duration_seconds is not None:
            shot["durationInSeconds"] = asset.duration_seconds
        if asset.thumbnail_url:
            shot["thumbnailUrl"] = asset.thumbnail_url
        shots.append(shot)
        existing_urls.add(asset.url)
        used_asset_urls.add(asset.url)

    if not shots:
        return False
    scene["shots"] = shots
    return True


def _scene_visual_intent(scene: SceneDraft, keyword: str | None = None) -> str:
    intent = str(scene.get("visualIntent") or "").strip()
    if keyword:
        return f"{intent}; specifically show {keyword}" if intent else keyword
    return intent or str(scene.get("text") or "").strip()


def _scene_selection_guidance(scene: SceneDraft) -> str:
    guidance: list[str] = []
    must_contain = [str(item).strip() for item in scene.get("mustContain", []) if str(item).strip()]
    avoid = [str(item).strip() for item in scene.get("avoid", []) if str(item).strip()]
    preferred_shot = str(scene.get("preferredShot") or "").strip()
    if must_contain:
        guidance.append("Must visibly include: " + ", ".join(must_contain))
    if avoid:
        guidance.append("Avoid: " + ", ".join(avoid))
    if preferred_shot:
        guidance.append(f"Preferred framing/action: {preferred_shot}")
    return "; ".join(guidance)


def _clip_record(clip: SelectedThirdPartyClip, project_root: Path) -> dict[str, Any]:
    """Single provenance record of a selected YouTube clip (also the montage shot shape)."""

    candidate = clip.candidate
    record: dict[str, Any] = {
        "url": public_asset_url(clip.path, project_root),
        "type": "video",
        "provider": "youtube",
        "sourceUrl": candidate.url,
        "sourceTitle": candidate.title,
        "query": candidate.query,
        "uploader": candidate.uploader or "",
        "startSeconds": clip.start_seconds,
        "endSeconds": clip.end_seconds,
        "durationInSeconds": clip.duration_seconds,
        "relevanceScore": round(clip.relevance_score, 3),
        "visualScore": round(clip.visual_score, 3),
        "selectionReason": clip.reason,
        "transcriptExcerpt": clip.transcript_excerpt,
        "videoId": candidate.video_id,
    }
    if clip.contact_sheet is not None:
        try:
            record["contactSheet"] = public_asset_url(clip.contact_sheet, project_root)
        except ValueError:
            pass
    return record


def _apply_clip_provenance(scene: SceneDraft, record: dict[str, Any]) -> None:
    """Copy a clip record to the scene-level provenance fields."""

    scene["mediaProvider"] = "youtube"
    scene["mediaSourceUrl"] = str(record["sourceUrl"])
    scene["mediaSourceTitle"] = str(record.get("sourceTitle") or "")
    scene["mediaUploader"] = str(record.get("uploader") or "")
    scene["mediaQuery"] = str(record.get("query") or "")
    scene["mediaStartSeconds"] = float(record["startSeconds"])
    scene["mediaEndSeconds"] = float(record["endSeconds"])
    scene["mediaClipDurationSeconds"] = float(record["durationInSeconds"])
    scene["mediaSelectionScore"] = float(record["relevanceScore"])
    scene["mediaVisualScore"] = float(record["visualScore"])
    scene["mediaSelectionReason"] = str(record["selectionReason"])
    scene["mediaTranscriptExcerpt"] = str(record["transcriptExcerpt"])
    if record.get("videoId"):
        scene["mediaVideoId"] = str(record["videoId"])
    if record.get("contactSheet"):
        scene["mediaContactSheet"] = str(record["contactSheet"])


def _asset_candidates(
    pexels: PexelsClient,
    keywords: list[str],
    used_asset_urls: set[str],
    *,
    prefer_video: bool,
) -> list[tuple[PexelsAsset, str, int]]:
    candidates: list[tuple[PexelsAsset, str, int]] = []
    for query_index, keyword in enumerate(keywords[:3]):
        if prefer_video:
            videos = pexels.search_video_candidates(keyword, exclude_urls=used_asset_urls)
            candidates.extend((asset, keyword, query_index) for asset in videos)
            if not videos:
                images = pexels.search_image_candidates(keyword, exclude_urls=used_asset_urls)
                candidates.extend((asset, keyword, query_index) for asset in images)
        else:
            images = pexels.search_image_candidates(keyword, exclude_urls=used_asset_urls)
            candidates.extend((asset, keyword, query_index) for asset in images)
            if not images:
                videos = pexels.search_video_candidates(keyword, exclude_urls=used_asset_urls)
                candidates.extend((asset, keyword, query_index) for asset in videos)
    return candidates


def _select_scene_asset(
    scene: SceneDraft,
    keywords: list[str],
    pexels: PexelsClient,
    used_asset_urls: set[str],
    *,
    prefer_video: bool,
) -> tuple[PexelsAsset, float, str] | None:
    selected = select_best_asset(
        _asset_candidates(pexels, keywords, used_asset_urls, prefer_video=prefer_video),
        required_duration_seconds=float(scene.get("durationInFrames", 1)) / REMOTION_FPS,
    )
    return selected


def _is_remote(url: object) -> bool:
    return isinstance(url, str) and url.startswith(("http://", "https://"))


def _trace_payload(trace: SelectionTrace, slot: str | None, project_root: Path) -> dict[str, Any]:
    payload = trace.as_dict()
    if slot is not None:
        payload["keyword"] = slot
    for finalist in payload["finalists"]:
        sheet = finalist.get("contactSheet")
        if sheet:
            try:
                finalist["contactSheet"] = public_asset_url(Path(sheet), project_root)
            except ValueError:
                pass
    return payload


class MediaResolver:
    """Resolves the media of a whole scene plan. One instance per run."""

    def __init__(
        self,
        settings: Settings,
        assets_dir: Path,
        options: MediaOptions | None = None,
        *,
        avatar_dir: Path | None = None,
        pexels: PexelsClient | None = None,
        images: Any | None = None,
        youtube: YouTubeClient | None = None,
        judge: DeepSeekVisualJudge | None = None,
    ) -> None:
        self.settings = settings
        self.project_root = settings.project_root
        self.assets_dir = assets_dir
        self.options = options or MediaOptions()
        self.avatar_dir = avatar_dir
        self.pexels = pexels or PexelsClient(settings.pexels_api_key)
        self._images = images
        self.youtube = youtube
        self.judge = judge
        self.checkpoint = MediaCheckpoint(self.options.checkpoint_path, load=self.options.resume)

        self.used_video_ids: set[str] = set()
        self.used_asset_urls: set[str] = set()
        self._claim_lock = threading.Lock()
        self._health_lock = threading.Lock()
        self._youtube_enabled = threading.Event()
        self._youtube_failures = 0
        self._pexels_available = True
        self._pexels_failures = 0
        self._providers: dict[int, str] = {}

    # ------------------------------------------------------------------
    # setup
    # ------------------------------------------------------------------
    def _prepare_third_party(self) -> None:
        if not self.options.third_party_enabled:
            return
        try:
            if self.youtube is None:
                YouTubeClient.ensure_available()
                self.youtube = YouTubeClient(
                    max_parallel=self.settings.youtube_parallel,
                    single_pass_subtitles=self.settings.youtube_single_pass,
                )
            if self.judge is None:
                self.judge = DeepSeekVisualJudge(
                    self.settings.llm_api_key,
                    model=self.settings.deepseek_vision_model,
                    base_url=self.settings.deepseek_base_url,
                )
        except (YouTubeClientError, ValueError) as error:
            self.youtube = None
            self.judge = None
            log.warning(f"Aviso: YouTube/yt-dlp no disponible; se usará el fallback: {error}")
            return
        self._youtube_enabled.set()

    @property
    def images(self) -> Any:
        if self._images is None:
            from .clients.openai_images import OpenAIImageClient

            self._images = OpenAIImageClient(self.settings)
        return self._images

    # ------------------------------------------------------------------
    # planning
    # ------------------------------------------------------------------
    def _plan(self, index: int, original: SceneDraft) -> _Plan:
        scene: SceneDraft = dict(original)  # type: ignore[assignment]
        scene_type = scene.get("sceneType", "narrative")
        template_name = scene.get("templateName")
        spec = _MANIFEST.get(template_name)
        fingerprint = scene_fingerprint(scene, self.options.third_party_enabled)

        if scene_type == "avatar":
            return _Plan(index, scene, KIND_AVATAR, spec, fingerprint=fingerprint)
        if scene.get("mediaOverride"):
            return _Plan(index, scene, KIND_OVERRIDE, spec, fingerprint=fingerprint)
        # Transitions and templates that draw no media (title cards, data panels,
        # timelines, comparisons) need nothing fetched.
        if scene_type == "transition" or (spec is not None and spec.media == MEDIA_NONE):
            return _Plan(index, scene, KIND_NONE, spec, fingerprint=fingerprint)

        keywords = list(scene.get("keywords") or [])
        if not keywords and scene.get("text"):
            keywords = [scene["text"][:120]]

        third_party = bool(self._youtube_enabled.is_set() and spec is not None and spec.third_party)
        if spec is not None and spec.media == MEDIA_SHOTS:
            slots: list[str | None] = []
            if third_party:
                shot_keywords = keywords[:4] or [str(scene.get("visualIntent") or scene.get("text") or "")]
                slots = [keyword for keyword in shot_keywords if keyword.strip()]
            return _Plan(index, scene, KIND_SHOTS, spec, keywords, third_party, slots, fingerprint)
        return _Plan(
            index, scene, KIND_SINGLE, spec, keywords, third_party, [None] if third_party else [], fingerprint
        )

    # ------------------------------------------------------------------
    # checkpoint reuse
    # ------------------------------------------------------------------
    def _local_media_present(self, scene: SceneDraft) -> bool:
        urls: list[object] = [scene.get("videoUrl"), scene.get("imageUrl")]
        urls.extend(shot.get("url") for shot in scene.get("shots") or [] if isinstance(shot, dict))
        for url in urls:
            if isinstance(url, str) and url.startswith("/"):
                if not (self.project_root / "public" / url.lstrip("/")).is_file():
                    return False
        return True

    def _remember_used(self, scene: SceneDraft) -> None:
        """Keep cross-scene de-duplication working for scenes resolved in an earlier run."""

        if scene.get("mediaVideoId"):
            self.used_video_ids.add(str(scene["mediaVideoId"]))
        for key in ("mediaRemoteUrl", "videoUrl", "imageUrl"):
            if _is_remote(scene.get(key)):
                self.used_asset_urls.add(str(scene[key]))
        for shot in scene.get("shots") or []:
            if not isinstance(shot, dict):
                continue
            if shot.get("videoId"):
                self.used_video_ids.add(str(shot["videoId"]))
            for key in ("remoteUrl", "url"):
                if _is_remote(shot.get(key)):
                    self.used_asset_urls.add(str(shot[key]))

    def _apply_redo_requests(self, total_scenes: int) -> None:
        redo = sorted(self.options.redo_scenes)
        if not redo:
            return
        unknown = [number for number in redo if not 1 <= number <= total_scenes]
        if unknown:
            raise MediaFetchError(
                f"No existen las escenas {unknown}; el plan tiene {total_scenes} escenas (1-{total_scenes})."
            )
        if not self.checkpoint.loaded:
            log.warning(
                "Aviso: no hay checkpoint de media previo; se resolverán todas las escenas, "
                "no solo las pedidas."
            )
        for number in redo:
            previous = self.checkpoint.stored_scene(number)
            if previous:
                video_ids = [str(previous.get("mediaVideoId") or "")]
                asset_urls = [
                    str(previous.get(key) or "")
                    for key in ("mediaRemoteUrl", "videoUrl", "imageUrl")
                    if _is_remote(previous.get(key))
                ]
                for shot in previous.get("shots") or []:
                    if isinstance(shot, dict):
                        video_ids.append(str(shot.get("videoId") or ""))
                        asset_urls.extend(
                            str(shot[key]) for key in ("remoteUrl", "url") if _is_remote(shot.get(key))
                        )
                self.checkpoint.reject(number, video_ids=video_ids, asset_urls=asset_urls)
            self.checkpoint.forget_scene(number)
        self.checkpoint.save()

    # ------------------------------------------------------------------
    # phase: YouTube
    # ------------------------------------------------------------------
    def _note_youtube_health(self, trace: SelectionTrace) -> None:
        if not trace.queries:
            return
        with self._health_lock:
            if not trace.all_searches_failed:
                self._youtube_failures = 0
                return
            self._youtube_failures += 1
            if self._youtube_failures >= YOUTUBE_BREAKER_THRESHOLD and self._youtube_enabled.is_set():
                self._youtube_enabled.clear()
                reason = trace.search_errors[-1] if trace.search_errors else "sin detalle"
                log.warning(
                    f"Aviso: YouTube no responde ({self._youtube_failures} selecciones seguidas con todas "
                    f"las búsquedas fallidas; último error: {reason}). Se desactiva para el resto del run "
                    "y se usa Pexels/GPT Image."
                )

    def _third_party_task(self, plan: _Plan, slot: str | None) -> tuple[dict[str, Any] | None, SelectionTrace, float]:
        started = time.perf_counter()
        trace = SelectionTrace()
        if not self._youtube_enabled.is_set():
            trace.outcome = OUTCOME_YOUTUBE_UNAVAILABLE
            return None, trace, 0.0
        assert self.youtube is not None and self.judge is not None
        scene = plan.scene
        record: dict[str, Any] | None = None
        try:
            clip = select_third_party_clip(
                visual_intent=_scene_visual_intent(scene, slot),
                keywords=[slot] if slot is not None else plan.keywords,
                transcript_context=str(scene.get("text") or ""),
                selection_guidance=_scene_selection_guidance(scene),
                youtube=self.youtube,
                judge=self.judge,
                assets_dir=self.assets_dir,
                used_video_ids=self.used_video_ids,
                excluded_video_ids=self.checkpoint.rejected_video_ids(plan.number),
                claim_lock=self._claim_lock,
                trace=trace,
            )
            if clip is not None:
                record = _clip_record(clip, self.project_root)
        except Exception as error:
            trace.outcome = OUTCOME_ERROR
            trace.judge_error = short_error(error)
            log.warning(
                f"Aviso: selección de clip de terceros fallida en la escena {plan.number}; "
                f"se usará el fallback: {short_error(error)}"
            )
        self._note_youtube_health(trace)
        return record, trace, time.perf_counter() - started

    def _run_third_party(self, plans: list[_Plan]) -> dict[tuple[int, str | None], dict[str, Any]]:
        """Return ``{(scene index, slot): clip record}`` and per-scene traces in ``self._traces``."""

        results: dict[tuple[int, str | None], dict[str, Any]] = {}
        pending: list[tuple[_Plan, str | None]] = []
        for plan in plans:
            for slot in plan.slots:
                key = MediaCheckpoint.slot_key(plan.number, slot)
                found, record, trace_payload = self.checkpoint.get_third_party(key, plan.fingerprint)
                usable = found and (
                    record is None
                    or (self.project_root / "public" / str(record.get("url", "")).lstrip("/")).is_file()
                )
                if usable:
                    METRICS.count("media.third_party_reused")
                    if record is not None:
                        results[(plan.index, slot)] = record
                        if record.get("videoId"):
                            self.used_video_ids.add(str(record["videoId"]))
                    if trace_payload:
                        self._traces.setdefault(plan.index, []).append(trace_payload)
                else:
                    pending.append((plan, slot))
        if not pending:
            return results

        total = len(pending)
        workers = max(1, min(self.options.concurrency, total))
        log.info(
            f"   YouTube: {total} selecciones pendientes, {workers} en paralelo"
            + (f" ({len(results)} reutilizadas del checkpoint)." if results else ".")
        )
        done = 0

        def finish(plan: _Plan, slot: str | None, outcome: tuple[dict[str, Any] | None, SelectionTrace, float]) -> None:
            nonlocal done
            record, trace, seconds = outcome
            done += 1
            payload = _trace_payload(trace, slot, self.project_root)
            payload["totalSeconds"] = round(seconds, 2)
            self._traces.setdefault(plan.index, []).append(payload)
            self._third_party_seconds[plan.index] = self._third_party_seconds.get(plan.index, 0.0) + seconds
            if record is not None:
                results[(plan.index, slot)] = record
            elif trace.outcome in _TRANSIENT_OUTCOMES:
                self._transient_misses.add(plan.index)
            if record is not None or trace.outcome in _FINAL_MISS_OUTCOMES:
                self.checkpoint.put_third_party(
                    MediaCheckpoint.slot_key(plan.number, slot), plan.fingerprint, record, payload
                )
            label = f"escena {plan.number} ({plan.scene.get('templateName')})"
            if slot is not None:
                label += f" · «{slot}»"
            if record is not None:
                detail = f"YouTube ✓ visual {record['visualScore']:.2f}"
            else:
                detail = "sin clip de YouTube: " + _OUTCOME_LABELS.get(trace.outcome, trace.outcome or "desconocido")
                if trace.outcome == OUTCOME_BELOW_THRESHOLD and trace.best_visual_score is not None:
                    detail += f" ({trace.best_visual_score:.2f})"
            log.info(f"   [{done}/{total}] {label}: {detail} · {seconds:.0f} s")
            METRICS.flush()

        if workers == 1:
            for plan, slot in pending:
                finish(plan, slot, self._third_party_task(plan, slot))
            return results

        pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="media")
        try:
            futures = {pool.submit(self._third_party_task, plan, slot): (plan, slot) for plan, slot in pending}
            for future in as_completed(futures):
                plan, slot = futures[future]
                finish(plan, slot, future.result())
        except BaseException:
            # Ctrl-C or an unexpected failure: stop handing out work; finished
            # selections are already in the checkpoint.
            self._youtube_enabled.clear()
            pool.shutdown(wait=False, cancel_futures=True)
            raise
        pool.shutdown(wait=True)
        return results

    # ------------------------------------------------------------------
    # phase: Pexels
    # ------------------------------------------------------------------
    def _pexels_call(self, description: str, function: Callable[[], Any]) -> Any:
        """Run one Pexels lookup; failures degrade to the next provider instead of crashing."""

        if not self._pexels_available:
            return None
        try:
            result = function()
        except PexelsRateLimitError as error:
            log.warning(f"Aviso: {error}")
            self._pexels_available = False
            return None
        except PexelsError as error:
            self._pexels_failures += 1
            log.warning(f"Aviso: Pexels falló en {description}: {error}")
            if self._pexels_failures >= PEXELS_BREAKER_THRESHOLD:
                self._pexels_available = False
                log.warning(
                    "Aviso: Pexels falló varias veces seguidas; se desactiva para el resto del run "
                    "y se usa GPT Image."
                )
            return None
        self._pexels_failures = 0
        return result

    def _resolve_single(self, plan: _Plan, record: dict[str, Any] | None) -> bool:
        """Return True when the scene has media; False when it needs a generated image."""

        scene = plan.scene
        if record is not None:
            scene["videoUrl"] = str(record["url"])
            scene["videoDurationInSeconds"] = float(record["durationInSeconds"])
            _apply_clip_provenance(scene, record)
            self._providers[plan.index] = "youtube"
            return True

        prefer_video = plan.spec.prefer_video if plan.spec is not None else True
        selected = self._pexels_call(
            f"la escena {plan.number}",
            lambda: _select_scene_asset(
                scene, plan.keywords, self.pexels, self.used_asset_urls, prefer_video=prefer_video
            ),
        )
        if selected:
            asset, score, query = selected
            _assign_asset(scene, asset, query=query, relevance_score=score)
            self.used_asset_urls.add(asset.url)
            self._providers[plan.index] = "pexels"
            return True
        return False

    def _resolve_shots(self, plan: _Plan, records: list[dict[str, Any]]) -> bool:
        scene = plan.scene
        third_party_shots = [dict(record) for record in records]
        if third_party_shots:
            scene["shots"] = third_party_shots
            _apply_clip_provenance(scene, third_party_shots[0])
        prefer_video = plan.spec.prefer_video if plan.spec is not None else False
        self._pexels_call(
            f"la escena {plan.number}",
            lambda: _assign_montage_shots(
                scene,
                plan.keywords,
                self.pexels,
                self.used_asset_urls,
                prefer_video=prefer_video,
                existing_shots=third_party_shots,
            ),
        )
        if scene.get("shots"):
            self._providers[plan.index] = "youtube" if third_party_shots else "pexels"
            return True
        return False

    # ------------------------------------------------------------------
    # phase: local copies of Pexels files
    # ------------------------------------------------------------------
    def _localize_stock(self, plans: list[_Plan]) -> None:
        if not self.options.download_stock:
            return
        targets: list[tuple[dict[str, Any], str, str]] = []  # (holder, url key, remote key)
        for plan in plans:
            scene: dict[str, Any] = plan.scene  # type: ignore[assignment]
            if scene.get("mediaProvider") == "pexels":
                for key in ("videoUrl", "imageUrl"):
                    if _is_remote(scene.get(key)):
                        targets.append((scene, key, "mediaRemoteUrl"))
            for shot in scene.get("shots") or []:
                if isinstance(shot, dict) and shot.get("provider") == "pexels" and _is_remote(shot.get("url")):
                    targets.append((shot, "url", "remoteUrl"))
        if not targets:
            return

        stock_dir = self.assets_dir / "stock"
        failures = 0

        def download(target: tuple[dict[str, Any], str, str]) -> bool:
            holder, key, remote_key = target
            remote = str(holder[key])
            try:
                local = self.pexels.download_asset(remote, stock_dir)
                holder[key] = public_asset_url(local, self.project_root)
                holder[remote_key] = remote
                return True
            except (PexelsError, OSError, ValueError) as error:
                log.debug("No se pudo copiar %s en local: %s", remote, short_error(error))
                return False

        workers = max(1, min(4, len(targets)))
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="stock") as pool:
            for ok in pool.map(download, targets):
                failures += 0 if ok else 1
        log.info(
            f"   Pexels: {len(targets) - failures} ficheros copiados a local"
            + (f"; {failures} se quedan con URL remota." if failures else ".")
        )

    # ------------------------------------------------------------------
    # phase: generated images
    # ------------------------------------------------------------------
    def _generate_image(self, plan: _Plan) -> str | None:
        scene = plan.scene
        scene_type = scene.get("sceneType", "narrative")
        # Heuristic placeholder until the LLM marks key scenes explicitly.
        quality = "high" if plan.kind == KIND_SINGLE and scene_type in {"hook", "stat"} else "medium"
        last_error: Exception | None = None
        for attempt in range(1, IMAGE_ATTEMPTS + 1):
            try:
                generated_path = self.images.generate_image(
                    _visual_prompt(scene, plan.keywords),
                    self.assets_dir / "images",
                    quality=quality,
                )
            except Exception as error:
                last_error = error
                log.debug("GPT Image falló en la escena %s (intento %s): %s", plan.number, attempt, short_error(error))
                if attempt < IMAGE_ATTEMPTS:
                    time.sleep(2.0)
                continue
            url = _public_url(generated_path, self.project_root)
            if plan.kind == KIND_SHOTS:
                scene["shots"] = [{"url": url, "type": "image", "provider": "openai-image"}]
            else:
                scene["imageUrl"] = url
            scene["mediaProvider"] = "openai-image"
            self._providers[plan.index] = "openai-image"
            return None
        assert last_error is not None
        return short_error(last_error)

    def _run_images(self, plans: list[_Plan]) -> dict[int, str]:
        """Generate fallbacks; return ``{scene number: error}`` for the ones that failed."""

        if not plans:
            return {}
        log.info(f"   GPT Image: {len(plans)} escena(s) sin material de YouTube ni Pexels.")
        try:
            _ = self.images  # build the client once, before the worker threads need it
        except Exception as error:
            return {plan.number: short_error(error) for plan in plans}
        errors: dict[int, str] = {}
        workers = max(1, min(2, self.options.concurrency, len(plans)))
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="image") as pool:
            for plan, error in zip(plans, pool.map(self._generate_image, plans)):
                if error:
                    errors[plan.number] = error
        return errors

    # ------------------------------------------------------------------
    # local overrides
    # ------------------------------------------------------------------
    def _resolve_override(self, plan: _Plan) -> None:
        scene = plan.scene
        source = Path(str(scene["mediaOverride"])).expanduser()
        if not source.is_file():
            raise MediaFetchError(f"Escena {plan.number}: no existe el fichero de override {source}.")
        suffix = source.suffix.lower()
        if suffix not in _VIDEO_SUFFIXES | _IMAGE_SUFFIXES:
            raise MediaFetchError(
                f"Escena {plan.number}: {source.name} no es un vídeo o imagen admitido "
                f"({', '.join(sorted(_VIDEO_SUFFIXES | _IMAGE_SUFFIXES))})."
            )
        target_dir = self.assets_dir / "overrides"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"scene-{plan.number:03d}{suffix}"
        shutil.copy2(source, target)
        url = _public_url(target, self.project_root)
        is_video = suffix in _VIDEO_SUFFIXES
        duration: float | None = None
        if is_video:
            try:
                duration = probe_duration_seconds(target)
            except MediaToolError:
                duration = None

        for key in ("imageUrl", "videoUrl", "videoDurationInSeconds", "shots"):
            scene.pop(key, None)  # type: ignore[misc]
        if plan.spec is not None and plan.spec.media == MEDIA_SHOTS:
            shot: dict[str, Any] = {"url": url, "type": "video" if is_video else "image", "provider": "local"}
            if duration:
                shot["durationInSeconds"] = duration
            scene["shots"] = [shot]
        elif is_video:
            scene["videoUrl"] = url
            if duration:
                scene["videoDurationInSeconds"] = duration
        else:
            scene["imageUrl"] = url
        scene["mediaProvider"] = "local"
        scene["mediaSourceUrl"] = str(source)
        self._providers[plan.index] = "local"

    # ------------------------------------------------------------------
    # orchestration
    # ------------------------------------------------------------------
    def resolve(self, scenes: list[SceneDraft]) -> list[SceneDraft]:
        self._traces: dict[int, list[dict[str, Any]]] = {}
        self._third_party_seconds: dict[int, float] = {}
        self._transient_misses: set[int] = set()
        self._prepare_third_party()
        if self._youtube_enabled.is_set():
            log.info("   Fuente visual: YouTube/terceros primero; Pexels y GPT Image como fallback.")
        else:
            log.info("   Fuente visual: Pexels primero (YouTube/terceros desactivado o no disponible).")

        self._apply_redo_requests(len(scenes))
        self.used_asset_urls.update(self.checkpoint.rejected_asset_urls())

        plans = [self._plan(index, scene) for index, scene in enumerate(scenes)]
        resolved: dict[int, SceneDraft] = {}
        pending: list[_Plan] = []
        for plan in plans:
            stored = self.checkpoint.get_scene(plan.number, plan.fingerprint)
            if stored is not None and self._local_media_present(stored):
                resolved[plan.index] = stored
                self._remember_used(stored)
                self._providers[plan.index] = str(stored.get("mediaProvider") or "ninguno")
                METRICS.count("media.scenes_reused")
                METRICS.scene(plan.number, template=plan.scene.get("templateName"), reused=True,
                              provider=self._providers[plan.index])
            else:
                pending.append(plan)
        if resolved:
            log.info(f"   {len(resolved)} de {len(plans)} escenas reutilizadas del checkpoint de media.")

        # Scenes that need no lookup at all.
        lookups: list[_Plan] = []
        for plan in pending:
            if plan.kind == KIND_AVATAR:
                self._resolve_avatar(plan)
            elif plan.kind == KIND_OVERRIDE:
                self._resolve_override(plan)
            elif plan.kind == KIND_NONE:
                self._providers[plan.index] = "ninguno"
            else:
                lookups.append(plan)

        with METRICS.timed("media.youtube_phase"):
            clips = self._run_third_party([plan for plan in lookups if plan.third_party])

        needs_image: list[_Plan] = []
        with METRICS.timed("media.pexels_phase"):
            for plan in lookups:
                if plan.kind == KIND_SHOTS:
                    records = [clips[(plan.index, slot)] for slot in plan.slots if (plan.index, slot) in clips]
                    has_media = self._resolve_shots(plan, records)
                else:
                    has_media = self._resolve_single(plan, clips.get((plan.index, None)))
                if not has_media:
                    needs_image.append(plan)
            self._localize_stock(lookups)

        with METRICS.timed("media.image_phase"):
            image_errors = self._run_images(needs_image)

        for plan in pending:
            if plan.number in image_errors:
                continue
            traces = self._traces.get(plan.index)
            if traces:
                plan.scene["mediaSelectionTrace"] = traces
            resolved[plan.index] = plan.scene
            if plan.index not in self._transient_misses:
                self.checkpoint.put_scene(plan.number, plan.fingerprint, plan.scene)
            METRICS.scene(
                plan.number,
                template=plan.scene.get("templateName"),
                provider=self._providers.get(plan.index, "ninguno"),
                reused=False,
                thirdPartySeconds=round(self._third_party_seconds.get(plan.index, 0.0), 2),
            )
        self.checkpoint.save()
        self._log_summary(len(plans), len(plans) - len(pending))
        if self._transient_misses:
            numbers = ", ".join(str(index + 1) for index in sorted(self._transient_misses))
            log.warning(
                f"Aviso: las escenas {numbers} usan el fallback porque YouTube o el juez visual fallaron "
                "de forma transitoria. Si relanzas el mismo comando se reintentan solo esas."
            )

        if image_errors:
            numbers = ", ".join(str(number) for number in sorted(image_errors))
            first_error = image_errors[min(image_errors)]
            raise MediaFetchError(
                f"No se pudo obtener material para las escenas {numbers}: YouTube y Pexels no dieron "
                f"resultado y GPT Image falló ({first_error}). Lo ya resuelto está guardado: relanza el "
                "mismo comando para reintentar solo esas escenas, o fija un fichero con --overrides."
            )
        return [resolved[index] for index in range(len(plans))]

    def _resolve_avatar(self, plan: _Plan) -> None:
        scene = plan.scene
        source = _avatar_source(scene, self.avatar_dir, plan.index)
        if source is None:
            raise MediaFetchError(
                f"La escena {plan.number} es avatar pero no tiene videoUrl ni clip "
                "scene-NNN.* en --avatar-dir."
            )
        if isinstance(source, Path):
            scene["videoUrl"] = _copy_local_avatar(
                source,
                self.assets_dir / "avatars",
                self.project_root,
                plan.index,
            )
        else:
            scene["videoUrl"] = source
        self._providers[plan.index] = "avatar"

    def _log_summary(self, total: int, reused: int) -> None:
        counts: dict[str, int] = {}
        for provider in self._providers.values():
            counts[provider] = counts.get(provider, 0) + 1
        labels = {
            "youtube": "YouTube",
            "pexels": "Pexels",
            "openai-image": "GPT Image",
            "local": "fichero local",
            "avatar": "avatar",
            "ninguno": "sin media (plantilla gráfica)",
        }
        parts = [f"{count} {labels.get(provider, provider)}" for provider, count in sorted(counts.items())]
        suffix = f" · {reused} reutilizadas" if reused else ""
        log.info(f"   Material de {total} escenas: " + " · ".join(parts) + suffix)
        for provider, count in counts.items():
            METRICS.count(f"media.provider.{provider}", count)


def fetch_media(
    scenes: list[SceneDraft],
    settings: Settings,
    *,
    assets_dir: Path,
    avatar_dir: Path | None = None,
    third_party_enabled: bool = True,
    options: MediaOptions | None = None,
    pexels: PexelsClient | None = None,
    images: Any | None = None,
    youtube: YouTubeClient | None = None,
    judge: DeepSeekVisualJudge | None = None,
) -> list[SceneDraft]:
    """Resolve third-party YouTube media first, then Pexels and generated images."""

    if options is None:
        options = MediaOptions(
            third_party_enabled=third_party_enabled,
            concurrency=getattr(settings, "media_concurrency", DEFAULT_MEDIA_CONCURRENCY),
            download_stock=getattr(settings, "download_stock", True),
        )
    resolver = MediaResolver(
        settings,
        assets_dir,
        options,
        avatar_dir=avatar_dir,
        pexels=pexels,
        images=images,
        youtube=youtube,
        judge=judge,
    )
    return resolver.resolve(scenes)
