# YouTube Video Templates

Skeleton for data-driven long-form video composition with Remotion, TypeScript, and React.

## Commands

```bash
npm install
npm run start
npm run typecheck
npm run render
```

`npm run render` uses `example-props.json` as the composition input.

## Automated pipeline

Specification: `CLAUDE.md`. Inputs live in `materiales/<slug>/` (`titulo.txt`, `guion.txt`, `voz.mp3`).

```bash
python -m pip install -r requirements.txt
python main.py --slug Video1 [--review] [--force planner] [--until timeline]
```

Each stage reads and writes JSON in `work/<slug>/` and is skipped when its output is valid and
its inputs (files + its `config.yaml` section) are unchanged. `--force <etapa>` re-runs it.
Tunables live in `config.yaml`; API keys in `.env` (see `.env.example`). External API spend is
logged to `work/<slug>/costs.json`.

| # | Stage | Status |
|---|-------|--------|
| 1 | `align` → `words.json` (local faster-whisper + forced alignment to the script) | done |
| 2 | `planner` → `shots.json` + `shots.md` (DP cutter 1.5-4 s + DeepSeek labelling, pydantic-validated, no invented figures) | done |
| 3 | `sourcing` → `candidates/<shot>.json` (YouTube via yt-dlp — metadata + storyboard thumbnails only — plus Wikimedia Commons, Openverse, Pixabay; global cache) | done (YouTube from a datacenter needs cookies) |
| 4 | `analysis` → `scores/<shot>.json` (CLIP on thumbnails, then 360p windows around the best moments: scenes, OCR, faces, sharpness, motion, entity mentions; ≤5 s spans) | done |
| 5 | `judge` → `selection.json` (priority YouTube → stills; no repeated fragments by timestamps/pHash; `gpt-5-mini` vision judge only on doubtful shots, 2 rounds max, else fallback) | done |
| 6 | `ingest` → `media/` (HD span only, frame-accurate, 1920x1080 cover, 30 fps, no audio, LUT; stills 16:9) | done |
| 7 | `fallback` → `fallback.json` + `media_fallback/` (next vetted option → Pexels video/photo by CLIP → GPT Image) | done |
| 8 | `timeline` → `timeline.json` (Remotion props) + `remotion/` templates: BRoll, DataCard, Stat, Chapter, Split, CreditBadge, AudioBed | done |
| 9 | `qa` → `out/<slug>/qa/{contact-sheet.jpg, report.md}`, `manifest.json`, `creditos.txt` (blocks the render on third-party clips > 5 s, missing credits or files; flags low scores and repeats; share per source; API spend) | done |
| 10 | render | pending |

Preview a project in Remotion Studio: `npx remotion studio remotion/index.ts --props=work/<slug>/timeline.json --public-dir=work/<slug>`

## Adding a template

1. Create a component in `templates/components/` that accepts `SceneProps`.
2. Export it from `templates/registry.ts` under a stable string key.
3. Set that key as `templateName` in the external composition JSON.

The external orchestrator only needs to send:

```json
{
  "scenes": [
    {
      "templateName": "placeholder",
      "durationInFrames": 180,
      "accentColor": "#f97316",
      "sceneType": "hook"
    }
  ]
}
```
