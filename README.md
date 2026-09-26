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
| 3-10 | sourcing, analysis, judge, ingest, fallback, timeline, qa, render | in progress |

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
