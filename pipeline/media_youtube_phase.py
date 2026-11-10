"""Media phase 1: third-party YouTube clips, several scenes at a time."""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from .checkpoint import MediaCheckpoint
from .media_context import MediaContext, Plan
from .media_scene import clip_record, scene_selection_guidance, scene_visual_intent, trace_payload
from .runlog import log, short_error
from .third_party_media import (
    OUTCOME_ALREADY_USED,
    OUTCOME_BELOW_THRESHOLD,
    OUTCOME_DOWNLOAD_FAILED,
    OUTCOME_JUDGE_FAILED,
    OUTCOME_NO_CANDIDATES,
    OUTCOME_NO_QUERY,
    OUTCOME_NO_SUBTITLE_MATCH,
    OUTCOME_SEARCH_FAILED,
    SelectionTrace,
    select_third_party_clip,
)
from .timing import METRICS


OUTCOME_YOUTUBE_UNAVAILABLE = "youtube-unavailable"
OUTCOME_ERROR = "error"
# A miss with one of these outcomes is final for the scene and is remembered.
FINAL_MISS_OUTCOMES = {
    OUTCOME_NO_QUERY,
    OUTCOME_NO_CANDIDATES,
    OUTCOME_NO_SUBTITLE_MATCH,
    OUTCOME_BELOW_THRESHOLD,
}
# Misses caused by an outage rather than by the candidates themselves. A scene
# that fell back because of one of these is not stored as final, so the next
# run of the same command tries YouTube again for it.
TRANSIENT_OUTCOMES = {
    OUTCOME_SEARCH_FAILED,
    OUTCOME_JUDGE_FAILED,
    OUTCOME_YOUTUBE_UNAVAILABLE,
    OUTCOME_ERROR,
}
OUTCOME_LABELS = {
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

BREAKER_THRESHOLD = 3

ClipKey = tuple[int, "str | None"]
TaskResult = tuple["dict[str, Any] | None", SelectionTrace, float]


class YouTubePhase:
    def __init__(self, context: MediaContext) -> None:
        self.context = context
        self.enabled = threading.Event()
        self._health_lock = threading.Lock()
        self._consecutive_failures = 0

    # ------------------------------------------------------------------
    # health
    # ------------------------------------------------------------------
    def _note_health(self, trace: SelectionTrace) -> None:
        """Switch YouTube off after several selections in a row where every search failed."""

        if not trace.queries:
            return
        with self._health_lock:
            if not trace.all_searches_failed:
                self._consecutive_failures = 0
                return
            self._consecutive_failures += 1
            if self._consecutive_failures >= BREAKER_THRESHOLD and self.enabled.is_set():
                self.enabled.clear()
                reason = trace.search_errors[-1] if trace.search_errors else "sin detalle"
                log.warning(
                    f"Aviso: YouTube no responde ({self._consecutive_failures} selecciones seguidas con todas "
                    f"las búsquedas fallidas; último error: {reason}). Se desactiva para el resto del run "
                    "y se usa Pexels/GPT Image."
                )

    # ------------------------------------------------------------------
    # one selection
    # ------------------------------------------------------------------
    def _select(self, plan: Plan, slot: str | None) -> TaskResult:
        started = time.perf_counter()
        trace = SelectionTrace()
        if not self.enabled.is_set():
            trace.outcome = OUTCOME_YOUTUBE_UNAVAILABLE
            return None, trace, 0.0
        context = self.context
        assert context.youtube is not None and context.judge is not None
        scene = plan.scene
        record: dict[str, Any] | None = None
        try:
            clip = select_third_party_clip(
                visual_intent=scene_visual_intent(scene, slot),
                keywords=[slot] if slot is not None else plan.keywords,
                transcript_context=str(scene.get("text") or ""),
                selection_guidance=scene_selection_guidance(scene),
                youtube=context.youtube,
                judge=context.judge,
                assets_dir=context.assets_dir,
                used_video_ids=context.used_video_ids,
                excluded_video_ids=context.checkpoint.rejected_video_ids(plan.number),
                claim_lock=context.claim_lock,
                trace=trace,
            )
            if clip is not None:
                record = clip_record(clip, context.project_root)
        except Exception as error:
            trace.outcome = OUTCOME_ERROR
            trace.judge_error = short_error(error)
            log.warning(
                f"Aviso: selección de clip de terceros fallida en la escena {plan.number}; "
                f"se usará el fallback: {short_error(error)}"
            )
        self._note_health(trace)
        return record, trace, time.perf_counter() - started

    # ------------------------------------------------------------------
    # all selections
    # ------------------------------------------------------------------
    def _reuse_from_checkpoint(self, plans: list[Plan], results: dict[ClipKey, dict[str, Any]]) -> list[tuple[Plan, str | None]]:
        """Fill ``results`` with stored selections; return the ones still to do."""

        context = self.context
        pending: list[tuple[Plan, str | None]] = []
        for plan in plans:
            for slot in plan.slots:
                key = MediaCheckpoint.slot_key(plan.number, slot)
                found, record, stored_trace = context.checkpoint.get_third_party(key, plan.fingerprint)
                usable = found and (
                    record is None
                    or (context.project_root / "public" / str(record.get("url", "")).lstrip("/")).is_file()
                )
                if not usable:
                    pending.append((plan, slot))
                    continue
                METRICS.count("media.third_party_reused")
                if record is not None:
                    results[(plan.index, slot)] = record
                    if record.get("videoId"):
                        context.used_video_ids.add(str(record["videoId"]))
                if stored_trace:
                    context.traces.setdefault(plan.index, []).append(stored_trace)
        return pending

    def run(self, plans: list[Plan]) -> dict[ClipKey, dict[str, Any]]:
        """Return ``{(scene index, slot): clip record}`` for every clip that was selected."""

        context = self.context
        results: dict[ClipKey, dict[str, Any]] = {}
        pending = self._reuse_from_checkpoint(plans, results)
        if not pending:
            return results

        total = len(pending)
        workers = max(1, min(context.options.concurrency, total))
        log.info(
            f"   YouTube: {total} selecciones pendientes, {workers} en paralelo"
            + (f" ({len(results)} reutilizadas del checkpoint)." if results else ".")
        )
        done = 0

        def finish(plan: Plan, slot: str | None, outcome: TaskResult) -> None:
            nonlocal done
            record, trace, seconds = outcome
            done += 1
            payload = trace_payload(trace, slot, context.project_root)
            payload["totalSeconds"] = round(seconds, 2)
            context.traces.setdefault(plan.index, []).append(payload)
            context.third_party_seconds[plan.index] = context.third_party_seconds.get(plan.index, 0.0) + seconds
            if record is not None:
                results[(plan.index, slot)] = record
            elif trace.outcome in TRANSIENT_OUTCOMES:
                context.transient_misses.add(plan.index)
            if record is not None or trace.outcome in FINAL_MISS_OUTCOMES:
                context.checkpoint.put_third_party(
                    MediaCheckpoint.slot_key(plan.number, slot), plan.fingerprint, record, payload
                )
            label = f"escena {plan.number} ({plan.scene.get('templateName')})"
            if slot is not None:
                label += f" · «{slot}»"
            if record is not None:
                detail = f"YouTube ✓ visual {record['visualScore']:.2f}"
            else:
                detail = "sin clip de YouTube: " + OUTCOME_LABELS.get(trace.outcome, trace.outcome or "desconocido")
                if trace.outcome == OUTCOME_BELOW_THRESHOLD and trace.best_visual_score is not None:
                    detail += f" ({trace.best_visual_score:.2f})"
            log.info(f"   [{done}/{total}] {label}: {detail} · {seconds:.0f} s")
            METRICS.flush()

        if workers == 1:
            for plan, slot in pending:
                finish(plan, slot, self._select(plan, slot))
            return results

        pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="media")
        try:
            futures = {pool.submit(self._select, plan, slot): (plan, slot) for plan, slot in pending}
            for future in as_completed(futures):
                plan, slot = futures[future]
                finish(plan, slot, future.result())
        except BaseException:
            # Ctrl-C or an unexpected failure: stop handing out work; finished
            # selections are already in the checkpoint.
            self.enabled.clear()
            pool.shutdown(wait=False, cancel_futures=True)
            raise
        pool.shutdown(wait=True)
        return results
