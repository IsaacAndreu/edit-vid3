# edit-vid3

An automated YouTube video studio: you give it a script (or an idea) and it produces a finished, narrated, edited
video, ready for review. It runs on a server around the clock, manages several channels in several languages, and
keeps every number and place on screen tied to the script or to a public source — nothing is invented.

Made by **Isaac Andreu** and **Cesar Ferre Vasco**.

## What it does

- **Footage videos** — from the script and its voice-over it plans the shots, finds and vets clips (YouTube,
  Wikimedia Commons, Openverse, Pixabay, Pexels), cuts them to the narration, adds data cards, chapters, lower thirds
  and credits, checks the result and renders it with Remotion + ffmpeg. The full stage list is below.
- **Atlas** (`docs/atlas-authoring.md`, `prompts/atlas-plan.md`) — explainer videos drawn in code: paper relief maps,
  globes, 3D terrain, elevation profiles, charts and cards, all from public geographic data. A script is enough: the AI
  writes the scene list and the storyboard, the pipeline validates every anchor against the voice and renders it.
- **Air accident reconstructions** (`prompts/accidentes-plan.md`) — real flights rebuilt from the public flight data
  recorder tables of NTSB dockets: track on the map, vertical profile, cockpit instruments, a 3D aircraft and
  synthesized engine sound, with every event cited from the official report. Respectful by design: no victims, no
  crash replays. Also one-minute "what we know" Shorts generated automatically from breaking news.
- **Simulations and animated formats** — "what if" and "why" videos explained with simulated worlds and drawn scenes.
- **Many channels, many languages** — each channel is a profile in `canales/` (style, voice, language, music,
  branding). Finished videos can be dubbed automatically (English, Portuguese, German, French, Italian…), with the
  on-screen texts translated too.
- **Runs by itself** — a web studio to add scripts and review results, a queue that voices (GenAIPro), makes and dubs
  videos as they appear, a daily radar of ideas from competitor outliers, fact-checking of every script, thumbnails and
  title options, a Telegram bot, spend tracking and an autopilot per channel. Finished videos wait in «Para subir»
  for a human to review before they go out.

## Quick start

```bash
npm install
python -m pip install -r requirements.txt
npm run typecheck
python main.py --slug Video1                 # one video from materiales/Video1/
python main.py --atlas-guion <folder>        # an Atlas video from materiales/<folder>/guion.txt
python main.py --vigilar 5                   # the server: watches materiales/ and makes everything that appears
```

Running it on your own PC: [`docs/LOCAL.md`](docs/LOCAL.md). On a server: [`docs/VPS.md`](docs/VPS.md).
Rules for working on the code: [`CLAUDE.md`](CLAUDE.md).

## The footage pipeline

Specification: `CLAUDE.md`. Inputs live in `materiales/<slug>/` (`titulo.txt`, `guion.txt`, `voz.mp3`).
Running it on your own PC: see [`docs/LOCAL.md`](docs/LOCAL.md).

```bash
python -m pip install -r requirements.txt
python main.py --slug Video1 [--review] [--force planner] [--until timeline]
python main.py --all [--limit 3]     # queue: every pending materiales/<slug>, one after another; summary in out/_cola.md
```

Each stage reads and writes JSON in `work/<slug>/` and is skipped when its output is valid and
its inputs (files + its `config.yaml` section) are unchanged. `--force <etapa>` re-runs it.
Tunables live in `config.yaml`; API keys in `.env` (see `.env.example`). External API spend is
logged to `work/<slug>/costs.json`.

| # | Stage | Status |
|---|-------|--------|
| 1 | `align` → `words.json` (local faster-whisper + forced alignment to the script) | done |
| 2 | `planner` → `shots.json` + `shots.md` (DP cutter 1.5-4 s + DeepSeek labelling, pydantic-validated, no invented figures — digits or words; story thread: subject + events, every shot searches for its event; protagonist first; hook shows the protagonist's peak; name/score labels) | done |
| 3 | `sourcing` → `candidates/<shot>.json` (YouTube via yt-dlp — metadata + storyboard thumbnails only — plus Wikimedia Commons, Openverse, Pixabay; global cache) | done (YouTube from a datacenter needs cookies) |
| 4 | `analysis` → `scores/<shot>.json` (CLIP on thumbnails, then 360p windows around the best moments: scenes, OCR, faces, sharpness, motion, entity mentions; ≤5 s spans) | done |
| 5 | `judge` → `selection.json` (priority YouTube → stills; no repeated fragments by timestamps/pHash; `gpt-5-mini` vision judge on every shot (`judge.all`) with the topic, subject, event and source titles; flags screens/off-topic per candidate; 2 rounds max, else fallback) | done |
| 6 | `ingest` → `media/` (HD span only, frame-accurate, 30 fps, no audio, LUT; widescreen cover-cropped to 1920x1080, 4:3/vertical kept uncropped for cards) | done |
| 7 | `fallback` → `fallback.json` + `media_fallback/` (also replaces downloaded look-alikes; next vetted option → other fragments of the protagonist → Pexels by CLIP → GPT Image) | done |
| 7b | `people` → `people.json` + `people/` (protagonist and named people cut out with rembg from a photo — or a frame of their own videos — for a presentation card; kept in the athlete library) | done |
| 8 | `coldopen` → `coldopen.json` + `coldopen/` (optional, `timeline.cold_open_seconds`: the protagonist's peak with its original sound before the narration, clips ≤ 5 s) | done |
| 9 | `timeline` → `timeline.json` (Remotion props) + `remotion/` templates: BRoll, FramedCard over GridBackground, LowerThird labels, DataCard, Stat, Question, Chapter ("CAPÍTULO 01 \| título"), Split, CreditBadge, AudioBed | done |
| 10 | `qa` → `out/<slug>/qa/{contact-sheet.jpg, report.md}`, `manifest.json`, `creditos.txt` (blocks the render on third-party clips > 5 s, missing credits or files; flags low scores and repeats; share per source; API spend) | done |
| 11 | `render` → `out/<slug>/video-final.mp4` (hybrid: plain footage + credit badge composed by ffmpeg, panels/stats/chapters/stills in one Remotion pass; audio mastered to -16 LUFS; segments joined without re-encoding; postflight checks) | done |
| 0 | `factcheck` → `out/<slug>/verificacion.md`: script claims checked against Wikipedia + web results (`--check <slug>` before recording) | done |
| 11b | `shorts` → `out/<slug>/shorts/short-{1,2,3}.mp4`: vertical 25-58 s moments with hook line and word-by-word captions (ffmpeg) | done |
| 12 | `package` → `out/<slug>/miniaturas/miniatura-{1,2,3}.jpg` + 3 title options in `youtube.txt` (patterned on the competition's outliers), sent by email/Telegram | done |
|  | `python main.py --dub <slug>:<lang>` → `out/<slug>-<lang>/`: dubbed version reusing the finished edit, retimed to the translated voice (also picked up by the queue from `materiales/<slug>/voz-<lang>.mp3`) | done |
|  | `python main.py --ideas` → `out/_ideas/<date>.md`: 3 daily video ideas from competitor outliers (views / channel median) and your own best videos | done |
|  | `python main.py --panel` → local research panel at http://127.0.0.1:8765: niche-wide outlier search, channel analysis, saved videos, ideas (YouTube Data API, several keys rotated) | done |

Athlete library: `cache/library/<person>/` keeps the vetted videos/photos and the cutout of each
protagonist; later videos about the same person get those sources as extra candidates (other
moments — `cache/used_fragments.json` stops any fragment from appearing in two videos).

Per-video options: `materiales/<slug>/config.yaml` is merged over `config.yaml` for that video only
(e.g. `timeline: {cold_open_seconds: 10}`).

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
