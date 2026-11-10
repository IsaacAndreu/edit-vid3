# Python orchestrator

The pipeline is intentionally split into small stages:

- `cli.py` — command line: `run` (default), `render`, `doctor`, `report`, `studio`, `clean`.
- `runner.py` — runs the eight steps in order, with cache, checkpoint, timings and log.
- `config.py` — `.env` loading, startup validation and optional tuning values.
- `templates.py` — reads `templates/manifest.json`, the single source of template rules shared with Remotion.
- `preflight.py` — environment checks before any slow or paid work (`python main.py doctor`).
- `cache.py` — content-addressed JSON cache for transcripts and segmentations; atomic writes.
- `checkpoint.py` — resumable state of the media stage (`<output>.media.json`).
- `timing.py` / `runlog.py` — per-step and per-scene timings, call counters, console and file log.
- `clients/deepseek_client.py` — OpenAI SDK pointed at DeepSeek, JSON mode, thinking disabled; prompt template list comes from the manifest.
- `clients/pexels_client.py` — Pexels photo/video candidate search, cache, pacing, bounded retries, Full HD file choice and local copies.
- `clients/youtube_client.py` — public YouTube search/metadata/subtitles and bounded clip downloads through yt-dlp; clip output is capped at five seconds. Searches are cached, captions come from the same extraction as the metadata, and an already prepared clip is reused after re-checking its cap.
- `subtitles.py` — WebVTT and json3 caption parsers.
- `candidate_analyzer.py` — subtitle-timed segment relevance scoring, contact-sheet extraction and opt-in DeepSeek multimodal visual judging.
- `third_party_media.py` — searches distinct candidates, selects the best visual segment, retains a contact sheet for audit and records every compared candidate in a trace.
- `media_ranker.py` — deterministic candidate ranking using query specificity, available alt text, resolution and clip duration.
- `clients/openai_images.py` — GPT Image 2 generation and local asset persistence; an image already generated for the same prompt is reused.
- `transcribe.py` — Whisper API wrapper with word and segment timestamps plus source duration; oversized audio is compressed before upload.
- `segment.py` — converts LLM word-index boundaries into `durationInFrames` using real timestamps and repairs sparse boundaries into a continuous audio timeline.
- `fetch_media.py` — media stage orchestration: plan each scene, reuse the checkpoint, then run the phases. Templates that draw no media are skipped.
- `media_youtube_phase.py` — third-party clip selection for several scenes in parallel, with a circuit breaker.
- `media_stock_phase.py` — Pexels lookups in scene order, local copies of the chosen files, and the GPT Image fallback.
- `media_local.py` — scenes whose media is a local file (operator overrides, reserved avatar clips).
- `media_scene.py` / `media_context.py` — helpers that write media fields on a scene, and the state the phases share.
- `overrides.py` — per-scene manual corrections from `overrides.json`.
- `qa.py` — pre-render validation and `.qa.json` report; blocks invalid scene plans and any YouTube clip over five seconds before Remotion.
- `analytics.py` — writes `.timeline.json` scene markers and provenance for later review and retention analysis.
- `report.py` — static HTML review page built from the sidecar files.
- `render.py` — Remotion render command.
- `postflight.py` — normalizes final audio to -16 LUFS and verifies the rendered container/streams without re-encoding video.
- `media_tools.py` — shared ffprobe duration helper.
- `build_props.py` — writes the `{ "scenes": [...], "audioUrl": "..." }` contract consumed by `Root.tsx`, preserving structured scene fields.

Avatar remains reserved for a future iteration and is disabled in the current
segmentation prompt. If the model returns `avatar` anyway, the segment is
normalized to a regular narrative scene instead of requiring an avatar clip.

Run from the repository root:

```bash
python -m pip install -r requirements.txt
python main.py doctor
python main.py materiales/Video1
```

For a first smoke test without rendering:

```bash
python main.py materiales/Video1 --skip-render
```

See the top-level README for every command, the files each run leaves and how to redo a scene.

The stable boundary between the LLM and the rest of the pipeline is the JSON object with a `scenes` array and `start_word_index` / `end_word_index` fields. The segmenter also restricts the LLM to templates compatible with currently available assets, avoids generic lower-thirds, requires concrete English visual search queries, repairs skipped timeline gaps, and keeps visual text short enough for title/overlay templates.

## Selección de material de terceros

Para cada escena narrativa, el segmenter añade `visualIntent`, `mustContain`,
`avoid` y `preferredShot`. El pipeline busca primero candidatos públicos en
YouTube con yt-dlp, puntúa ventanas temporales de subtítulos, descarga solo los
finalistas (máximo 5 s), genera contact sheets y pide a DeepSeek Flash que
confirme la relevancia visual. Si faltan subtítulos, no se inventa un timestamp:
esa escena pasa a Pexels y, como último recurso, GPT Image.

Los contact sheets quedan en `public/pipeline-assets/<run>/third-party/contact-sheets/`
para revisar la decisión. El `.timeline.json` y `props.json` guardan URL,
uploader, título, consulta, timestamps, puntuaciones y motivo de selección.
El flag `--skip-third-party` desactiva YouTube para comparar con los fallbacks.
No se usan cookies ni cuentas. yt-dlp depende de cambios del sitio y puede
fallar temporalmente; en ese caso se continúa con Pexels.

Antes del primer uso, instalar dependencias Python y comprobar que `ffmpeg` y
`ffprobe` y Deno estén disponibles en `PATH`. yt-dlp usa un runtime JavaScript
para resolver los desafíos actuales de YouTube; Deno queda habilitado por
defecto. La guía oficial de yt-dlp también documenta cómo configurar Node si
preferís usarlo:

[Configuración oficial de runtimes EJS de yt-dlp](https://github.com/yt-dlp/yt-dlp/wiki/EJS)

```powershell
python -m pip install -r requirements.txt
deno --version
ffmpeg -version
ffprobe -version
```
