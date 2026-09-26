# Python orchestrator

The pipeline is intentionally split into small stages:

- `config.py` — `.env` loading and startup validation.
- `clients/deepseek_client.py` — OpenAI SDK pointed at DeepSeek, JSON mode, thinking disabled.
- `clients/pexels_client.py` — Pexels photo/video candidate search, cache, pacing, bounded 429 retries, metadata and per-run URL de-duplication.
- `clients/youtube_client.py` — public YouTube search/metadata/subtitles and bounded clip downloads through yt-dlp; clip output is capped at five seconds.
- `candidate_analyzer.py` — subtitle-timed segment relevance scoring, contact-sheet extraction and opt-in DeepSeek multimodal visual judging.
- `third_party_media.py` — searches distinct candidates, selects the best visual segment and retains a contact sheet for audit.
- `media_ranker.py` — deterministic candidate ranking using query specificity, available alt text, resolution and clip duration.
- `clients/openai_images.py` — GPT Image 2 generation and local asset persistence.
- `transcribe.py` — Whisper API wrapper with word and segment timestamps plus source duration.
- `segment.py` — converts LLM word-index boundaries into `durationInFrames` using real timestamps and repairs sparse boundaries into a continuous audio timeline.
- `fetch_media.py` — third-party YouTube clips first, Pexels fallback, GPT Image final fallback, media provenance, and legacy avatar clip copying.
- `qa.py` — pre-render validation and `.qa.json` report; blocks invalid scene plans and any YouTube clip over five seconds before Remotion.
- `analytics.py` — writes `.timeline.json` scene markers for later YouTube retention analysis.
- `postflight.py` — normalizes final audio to -16 LUFS and verifies the rendered container/streams without re-encoding video.
- `build_props.py` — writes the `{ "scenes": [...], "audioUrl": "..." }` contract consumed by `Root.tsx`, preserving structured scene fields.

Avatar remains reserved for a future iteration and is disabled in the current
segmentation prompt. If the model returns `avatar` anyway, the segment is
normalized to a regular narrative scene instead of requiring an avatar clip.

Run from the repository root:

```bash
python -m pip install -r requirements.txt
python main.py --guion guion.txt --voz narracion.mp3 --output video_final.mp4
```

For a first smoke test without rendering:

```bash
python main.py --guion guion.txt --voz narracion.mp3 --output video_final.mp4 --skip-render
```

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
