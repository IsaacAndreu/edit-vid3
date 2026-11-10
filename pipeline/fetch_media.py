"""Media stage: third-party YouTube clips first, then Pexels, then GPT Image.

The work runs in phases so the slow part can go in parallel while the result
stays predictable:

1. plan every scene (what media its template needs, if any);
2. reuse what a previous run already resolved (checkpoint);
3. YouTube selection for the remaining scenes, several at a time  -> media_youtube_phase
4. Pexels for whatever YouTube did not cover, in scene order       -> media_stock_phase
5. local copies of the chosen Pexels files                         -> media_stock_phase
6. generated images as the last resort                             -> media_stock_phase

Scene-shaping helpers live in media_scene; shared state in media_context.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .candidate_analyzer import DeepSeekVisualJudge
from .checkpoint import MediaCheckpoint, scene_fingerprint
from .clients.pexels_client import PexelsClient
from .clients.youtube_client import YouTubeClient, YouTubeClientError
from .config import DEFAULT_MEDIA_CONCURRENCY, Settings
from .media_context import (
    KIND_AVATAR,
    KIND_NONE,
    KIND_OVERRIDE,
    KIND_SHOTS,
    KIND_SINGLE,
    NO_PROVIDER,
    MediaContext,
    MediaFetchError,
    MediaOptions,
    Plan,
)
from .media_local import resolve_avatar, resolve_override
from .media_scene import is_remote
from .media_stock_phase import ImagePhase, StockPhase
from .media_youtube_phase import YouTubePhase
from .runlog import log
from .templates import MEDIA_NONE, MEDIA_SHOTS, load_manifest
from .timing import METRICS
from .types import SceneDraft


__all__ = ["MediaFetchError", "MediaOptions", "MediaResolver", "fetch_media"]

_MANIFEST = load_manifest()
MONTAGE_TEMPLATES = {name for name, spec in _MANIFEST.templates.items() if spec.media == MEDIA_SHOTS}
YOUTUBE_MEDIA_TEMPLATES = {name for name, spec in _MANIFEST.templates.items() if spec.third_party}

_PROVIDER_LABELS = {
    "youtube": "YouTube",
    "pexels": "Pexels",
    "openai-image": "GPT Image",
    "local": "fichero local",
    "avatar": "avatar",
    NO_PROVIDER: "sin media (plantilla gráfica)",
}


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
        options = options or MediaOptions()
        self.context = MediaContext(
            settings=settings,
            assets_dir=assets_dir,
            options=options,
            checkpoint=MediaCheckpoint(options.checkpoint_path, load=options.resume),
            pexels=pexels or PexelsClient(settings.pexels_api_key),
            avatar_dir=avatar_dir,
            youtube=youtube,
            judge=judge,
            image_client=images,
        )
        self.youtube_phase = YouTubePhase(self.context)
        self.stock_phase = StockPhase(self.context)
        self.image_phase = ImagePhase(self.context)

    # ------------------------------------------------------------------
    # setup
    # ------------------------------------------------------------------
    def _prepare_third_party(self) -> None:
        context = self.context
        if not context.options.third_party_enabled:
            return
        try:
            if context.youtube is None:
                YouTubeClient.ensure_available()
                context.youtube = YouTubeClient(
                    max_parallel=context.settings.youtube_parallel,
                    single_pass_subtitles=context.settings.youtube_single_pass,
                )
            if context.judge is None:
                context.judge = DeepSeekVisualJudge(
                    context.settings.llm_api_key,
                    model=context.settings.deepseek_vision_model,
                    base_url=context.settings.deepseek_base_url,
                )
        except (YouTubeClientError, ValueError) as error:
            context.youtube = None
            context.judge = None
            log.warning(f"Aviso: YouTube/yt-dlp no disponible; se usará el fallback: {error}")
            return
        self.youtube_phase.enabled.set()

    # ------------------------------------------------------------------
    # planning
    # ------------------------------------------------------------------
    def _plan(self, index: int, original: SceneDraft) -> Plan:
        scene: SceneDraft = dict(original)  # type: ignore[assignment]
        scene_type = scene.get("sceneType", "narrative")
        spec = _MANIFEST.get(scene.get("templateName"))
        fingerprint = scene_fingerprint(scene, self.context.options.third_party_enabled)

        if scene_type == "avatar":
            return Plan(index, scene, KIND_AVATAR, spec, fingerprint=fingerprint)
        if scene.get("mediaOverride"):
            return Plan(index, scene, KIND_OVERRIDE, spec, fingerprint=fingerprint)
        # Transitions and templates that draw no media (title cards, data panels,
        # timelines, comparisons) need nothing fetched.
        if scene_type == "transition" or (spec is not None and spec.media == MEDIA_NONE):
            return Plan(index, scene, KIND_NONE, spec, fingerprint=fingerprint)

        keywords = list(scene.get("keywords") or [])
        if not keywords and scene.get("text"):
            keywords = [scene["text"][:120]]

        third_party = bool(self.youtube_phase.enabled.is_set() and spec is not None and spec.third_party)
        if spec is not None and spec.media == MEDIA_SHOTS:
            slots: list[str | None] = []
            if third_party:
                shot_keywords = keywords[:4] or [str(scene.get("visualIntent") or scene.get("text") or "")]
                slots = [keyword for keyword in shot_keywords if keyword.strip()]
            return Plan(index, scene, KIND_SHOTS, spec, keywords, third_party, slots, fingerprint)
        return Plan(
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
                if not (self.context.project_root / "public" / url.lstrip("/")).is_file():
                    return False
        return True

    @staticmethod
    def _picks(scene: SceneDraft) -> tuple[list[str], list[str]]:
        """Video ids and remote asset URLs a resolved scene is using."""

        video_ids = [str(scene["mediaVideoId"])] if scene.get("mediaVideoId") else []
        asset_urls = [str(scene[key]) for key in ("mediaRemoteUrl", "videoUrl", "imageUrl") if is_remote(scene.get(key))]
        for shot in scene.get("shots") or []:
            if not isinstance(shot, dict):
                continue
            if shot.get("videoId"):
                video_ids.append(str(shot["videoId"]))
            asset_urls.extend(str(shot[key]) for key in ("remoteUrl", "url") if is_remote(shot.get(key)))
        return video_ids, asset_urls

    def _remember_used(self, scene: SceneDraft) -> None:
        """Keep cross-scene de-duplication working for scenes resolved in an earlier run."""

        video_ids, asset_urls = self._picks(scene)
        self.context.used_video_ids.update(video_ids)
        self.context.used_asset_urls.update(asset_urls)

    def _apply_redo_requests(self, total_scenes: int) -> None:
        checkpoint = self.context.checkpoint
        redo = sorted(self.context.options.redo_scenes)
        if not redo:
            return
        unknown = [number for number in redo if not 1 <= number <= total_scenes]
        if unknown:
            raise MediaFetchError(
                f"No existen las escenas {unknown}; el plan tiene {total_scenes} escenas (1-{total_scenes})."
            )
        if not checkpoint.loaded:
            log.warning(
                "Aviso: no hay checkpoint de media previo; se resolverán todas las escenas, "
                "no solo las pedidas."
            )
        for number in redo:
            previous = checkpoint.stored_scene(number)
            if previous:
                video_ids, asset_urls = self._picks(previous)
                checkpoint.reject(number, video_ids=video_ids, asset_urls=asset_urls)
            checkpoint.forget_scene(number)
        checkpoint.save()

    # ------------------------------------------------------------------
    # orchestration
    # ------------------------------------------------------------------
    def resolve(self, scenes: list[SceneDraft]) -> list[SceneDraft]:
        context = self.context
        self._prepare_third_party()
        if self.youtube_phase.enabled.is_set():
            log.info("   Fuente visual: YouTube/terceros primero; Pexels y GPT Image como fallback.")
        else:
            log.info("   Fuente visual: Pexels primero (YouTube/terceros desactivado o no disponible).")

        self._apply_redo_requests(len(scenes))
        context.used_asset_urls.update(context.checkpoint.rejected_asset_urls())

        plans = [self._plan(index, scene) for index, scene in enumerate(scenes)]
        resolved: dict[int, SceneDraft] = {}
        pending: list[Plan] = []
        for plan in plans:
            stored = context.checkpoint.get_scene(plan.number, plan.fingerprint)
            if stored is not None and self._local_media_present(stored):
                resolved[plan.index] = stored
                self._remember_used(stored)
                context.providers[plan.index] = str(stored.get("mediaProvider") or NO_PROVIDER)
                METRICS.count("media.scenes_reused")
                METRICS.scene(
                    plan.number,
                    template=plan.scene.get("templateName"),
                    reused=True,
                    provider=context.providers[plan.index],
                )
            else:
                pending.append(plan)
        if resolved:
            log.info(f"   {len(resolved)} de {len(plans)} escenas reutilizadas del checkpoint de media.")

        # Scenes that need no lookup at all.
        lookups: list[Plan] = []
        for plan in pending:
            if plan.kind == KIND_AVATAR:
                resolve_avatar(context, plan)
            elif plan.kind == KIND_OVERRIDE:
                resolve_override(context, plan)
            elif plan.kind == KIND_NONE:
                context.providers[plan.index] = NO_PROVIDER
            else:
                lookups.append(plan)

        with METRICS.timed("media.youtube_phase"):
            clips = self.youtube_phase.run([plan for plan in lookups if plan.third_party])

        needs_image: list[Plan] = []
        with METRICS.timed("media.pexels_phase"):
            for plan in lookups:
                if plan.kind == KIND_SHOTS:
                    records = [clips[(plan.index, slot)] for slot in plan.slots if (plan.index, slot) in clips]
                    has_media = self.stock_phase.resolve_shots(plan, records)
                else:
                    has_media = self.stock_phase.resolve_single(plan, clips.get((plan.index, None)))
                if not has_media:
                    needs_image.append(plan)
            self.stock_phase.localize(lookups)

        with METRICS.timed("media.image_phase"):
            image_errors = self.image_phase.run(needs_image)

        for plan in pending:
            if plan.number in image_errors:
                continue
            traces = context.traces.get(plan.index)
            if traces:
                plan.scene["mediaSelectionTrace"] = traces
            resolved[plan.index] = plan.scene
            if plan.index not in context.transient_misses:
                context.checkpoint.put_scene(plan.number, plan.fingerprint, plan.scene)
            METRICS.scene(
                plan.number,
                template=plan.scene.get("templateName"),
                provider=context.providers.get(plan.index, NO_PROVIDER),
                reused=False,
                thirdPartySeconds=round(context.third_party_seconds.get(plan.index, 0.0), 2),
            )
        context.checkpoint.save()
        self._log_summary(len(plans), len(plans) - len(pending))
        if context.transient_misses:
            numbers = ", ".join(str(index + 1) for index in sorted(context.transient_misses))
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

    def _log_summary(self, total: int, reused: int) -> None:
        counts: dict[str, int] = {}
        for provider in self.context.providers.values():
            counts[provider] = counts.get(provider, 0) + 1
        parts = [f"{count} {_PROVIDER_LABELS.get(provider, provider)}" for provider, count in sorted(counts.items())]
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
