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

Run from the repository root (the old one-shot command line `--guion/--voz/--output` no longer exists; the
pipeline is driven by stages, see the main README):

```bash
python -m pip install -r requirements.txt -r requirements-dev.txt
python main.py --slug <vídeo>           # one video, every stage (pipeline/runner.py STAGES)
python main.py --vigilar                # the server's queue
python -m pipeline.puerta               # the quick check the deploy gate runs (pyflakes + import everything)
python -m pytest tests -q               # the suite (tests/test_e2e_stages.py runs every real stage, ~5 min)
```

Note: `fetch_media.py` and `clients/youtube_client.py` belong to that old path; nothing in the stage pipeline
imports `fetch_media.py` (youtube.py only reuses the client's json3 subtitle parser).
