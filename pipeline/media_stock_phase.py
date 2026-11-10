"""Media phases 2-4: Pexels, local copies of its files, and generated images."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from .clients.pexels_client import PexelsError, PexelsRateLimitError
from .media_context import KIND_SHOTS, KIND_SINGLE, MediaContext, Plan
from .media_scene import (
    apply_clip_provenance,
    assign_asset,
    assign_montage_shots,
    is_remote,
    select_scene_asset,
    visual_prompt,
)
from .media_tools import MediaToolError, probe_duration_seconds
from .runlog import log, short_error
from .third_party_media import public_asset_url


PEXELS_BREAKER_THRESHOLD = 3
IMAGE_ATTEMPTS = 2


class StockPhase:
    """Pexels lookups run one at a time, in scene order, so the result is predictable."""

    def __init__(self, context: MediaContext) -> None:
        self.context = context
        self._available = True
        self._failures = 0

    def _call(self, description: str, function: Callable[[], Any]) -> Any:
        """Run one Pexels lookup; failures degrade to the next provider instead of crashing."""

        if not self._available:
            return None
        try:
            result = function()
        except PexelsRateLimitError as error:
            log.warning(f"Aviso: {error}")
            self._available = False
            return None
        except PexelsError as error:
            self._failures += 1
            log.warning(f"Aviso: Pexels falló en {description}: {error}")
            if self._failures >= PEXELS_BREAKER_THRESHOLD:
                self._available = False
                log.warning(
                    "Aviso: Pexels falló varias veces seguidas; se desactiva para el resto del run "
                    "y se usa GPT Image."
                )
            return None
        self._failures = 0
        return result

    def resolve_single(self, plan: Plan, record: dict[str, Any] | None) -> bool:
        """Return True when the scene has media; False when it needs a generated image."""

        context = self.context
        scene = plan.scene
        if record is not None:
            scene["videoUrl"] = str(record["url"])
            scene["videoDurationInSeconds"] = float(record["durationInSeconds"])
            apply_clip_provenance(scene, record)
            context.providers[plan.index] = "youtube"
            return True

        prefer_video = plan.spec.prefer_video if plan.spec is not None else True
        selected = self._call(
            f"la escena {plan.number}",
            lambda: select_scene_asset(
                scene, plan.keywords, context.pexels, context.used_asset_urls, prefer_video=prefer_video
            ),
        )
        if selected:
            asset, score, query = selected
            assign_asset(scene, asset, query=query, relevance_score=score)
            context.used_asset_urls.add(asset.url)
            context.providers[plan.index] = "pexels"
            return True
        return False

    def resolve_shots(self, plan: Plan, records: list[dict[str, Any]]) -> bool:
        context = self.context
        scene = plan.scene
        third_party_shots = [dict(record) for record in records]
        if third_party_shots:
            scene["shots"] = third_party_shots
            apply_clip_provenance(scene, third_party_shots[0])
        prefer_video = plan.spec.prefer_video if plan.spec is not None else False
        self._call(
            f"la escena {plan.number}",
            lambda: assign_montage_shots(
                scene,
                plan.keywords,
                context.pexels,
                context.used_asset_urls,
                prefer_video=prefer_video,
                existing_shots=third_party_shots,
            ),
        )
        if scene.get("shots"):
            context.providers[plan.index] = "youtube" if third_party_shots else "pexels"
            return True
        return False

    def localize(self, plans: list[Plan]) -> None:
        """Copy the chosen Pexels files next to the other assets so the render needs no network."""

        context = self.context
        if not context.options.download_stock:
            return
        # (holder, url key, remote-url key, duration key for videos)
        targets: list[tuple[dict[str, Any], str, str, str | None]] = []
        for plan in plans:
            scene: dict[str, Any] = plan.scene  # type: ignore[assignment]
            if scene.get("mediaProvider") == "pexels":
                if is_remote(scene.get("videoUrl")):
                    targets.append((scene, "videoUrl", "mediaRemoteUrl", "videoDurationInSeconds"))
                if is_remote(scene.get("imageUrl")):
                    targets.append((scene, "imageUrl", "mediaRemoteUrl", None))
            for shot in scene.get("shots") or []:
                if isinstance(shot, dict) and shot.get("provider") == "pexels" and is_remote(shot.get("url")):
                    duration_key = "durationInSeconds" if shot.get("type") == "video" else None
                    targets.append((shot, "url", "remoteUrl", duration_key))
        if not targets:
            return

        stock_dir = context.assets_dir / "stock"

        def download(target: tuple[dict[str, Any], str, str, str | None]) -> bool:
            holder, key, remote_key, duration_key = target
            remote = str(holder[key])
            try:
                local = context.pexels.download_asset(remote, stock_dir)
                holder[key] = public_asset_url(local, context.project_root)
                holder[remote_key] = remote
            except (PexelsError, OSError, ValueError) as error:
                log.debug("No se pudo copiar %s en local: %s", remote, short_error(error))
                return False
            if duration_key is not None:
                # The API reports whole seconds; the render loops on the real length.
                try:
                    duration = probe_duration_seconds(local)
                    if duration > 0:
                        holder[duration_key] = round(duration, 3)
                except MediaToolError:
                    pass
            return True

        workers = max(1, min(4, len(targets)))
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="stock") as pool:
            failures = sum(0 if ok else 1 for ok in pool.map(download, targets))
        log.info(
            f"   Pexels: {len(targets) - failures} ficheros copiados a local"
            + (f"; {failures} se quedan con URL remota." if failures else ".")
        )


class ImagePhase:
    """Last resort: one generated image per scene that no provider could cover."""

    def __init__(self, context: MediaContext) -> None:
        self.context = context

    def _generate(self, plan: Plan) -> str | None:
        context = self.context
        scene = plan.scene
        scene_type = scene.get("sceneType", "narrative")
        # Heuristic placeholder until the LLM marks key scenes explicitly.
        quality = "high" if plan.kind == KIND_SINGLE and scene_type in {"hook", "stat"} else "medium"
        last_error: Exception | None = None
        for attempt in range(1, IMAGE_ATTEMPTS + 1):
            try:
                generated_path = context.images.generate_image(
                    visual_prompt(scene, plan.keywords),
                    context.assets_dir / "images",
                    quality=quality,
                )
            except Exception as error:
                last_error = error
                log.debug("GPT Image falló en la escena %s (intento %s): %s", plan.number, attempt, short_error(error))
                if attempt < IMAGE_ATTEMPTS:
                    time.sleep(2.0)
                continue
            url = public_asset_url(generated_path, context.project_root)
            if plan.kind == KIND_SHOTS:
                scene["shots"] = [{"url": url, "type": "image", "provider": "openai-image"}]
            else:
                scene["imageUrl"] = url
            scene["mediaProvider"] = "openai-image"
            context.providers[plan.index] = "openai-image"
            return None
        assert last_error is not None
        return short_error(last_error)

    def run(self, plans: list[Plan]) -> dict[int, str]:
        """Generate fallbacks; return ``{scene number: error}`` for the ones that failed."""

        if not plans:
            return {}
        log.info(f"   GPT Image: {len(plans)} escena(s) sin material de YouTube ni Pexels.")
        try:
            _ = self.context.images  # build the client once, before the worker threads need it
        except Exception as error:
            return {plan.number: short_error(error) for plan in plans}
        workers = max(1, min(2, self.context.options.concurrency, len(plans)))
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="image") as pool:
            outcomes = list(pool.map(self._generate, plans))
        return {plan.number: error for plan, error in zip(plans, outcomes) if error}
