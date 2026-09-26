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

The Python orchestrator lives in `pipeline/` and is launched from the repository root:

```bash
python -m pip install -r requirements.txt
python main.py --guion guion.txt --voz narracion.mp3 --output video_final.mp4
```

Create `.env` from `.env.example` first. The pipeline transcribes the audio with Whisper, segments using DeepSeek, searches YouTube for subtitle-timed third-party clips, and asks DeepSeek's vision-capable model to judge sampled frames. Each downloaded YouTube clip is hard-capped at five seconds; scenes without a suitable result fall back to Pexels and then GPT Image. Selection details and source/timestamps are recorded in the props and timeline manifests. Use `--skip-render` to inspect only the generated props.

Install `ffmpeg`/`ffprobe` and Deno as well as Python dependencies. Current yt-dlp YouTube support needs a JavaScript runtime; Deno is enabled automatically. See the [yt-dlp EJS setup guide](https://github.com/yt-dlp/yt-dlp/wiki/EJS). Use `--skip-third-party` to skip YouTube and test the Pexels/image fallbacks.

Avatar generation/import is intentionally disabled for now. The `--avatar-dir` option remains reserved for a future iteration.

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
