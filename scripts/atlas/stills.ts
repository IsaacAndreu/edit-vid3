/**
 * Dos fotogramas por escena (mitad y final) + hoja de contactos, para el bucle visual.
 *
 *   npm run atlas:stills -- <storyboard.json> [--scene id1,id2] [--at 12.5,30]
 *
 * Salida en out/stills/<slug>/: NN-<id>-mid.png, NN-<id>-end.png y contact-sheet.jpg.
 * --scene limita a esas escenas; --at añade fotogramas en esos segundos absolutos.
 */
import { mkdirSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { bundle } from '@remotion/bundler';
import { renderStill, selectComposition } from '@remotion/renderer';
import sharp from 'sharp';
import { sceneTimings } from '../../remotion/atlas/time';
import { browserExecutable, loadStoryboard, PUBLIC_DIR, readJson, ROOT, run } from './load';

const THUMB_W = 640;
const THUMB_H = 360;
const LABEL_H = 34;
const COLS = 4;

const escapeXml = (s: string) => s.replace(/[<>&"]/g, (c) => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;', '"': '&quot;' })[c]!);

run(async () => {
  const args = process.argv.slice(2);
  const flag = (name: string) => {
    const i = args.indexOf(name);
    return i >= 0 ? args[i + 1] : undefined;
  };
  const storyboardPath = args.find((a, i) => !a.startsWith('--') && !args[i - 1]?.startsWith('--'));
  if (!storyboardPath) throw new Error('Uso: atlas:stills <storyboard.json> [--scene a,b] [--at 1.5,7]');

  const { resolved } = loadStoryboard(storyboardPath);
  const onlyScenes = flag('--scene')?.split(',');
  const extraTimes = flag('--at')?.split(',').map(Number) ?? [];

  const bundled = await bundle({ entryPoint: join(ROOT, 'remotion', 'index.ts'), publicDir: PUBLIC_DIR });
  const inputProps = readJson(storyboardPath) as Record<string, unknown>;
  const exe = browserExecutable();
  const common = {
    serveUrl: bundled,
    inputProps,
    browserExecutable: exe,
    chromiumOptions: { gl: 'swangle' as const },
  };
  const composition = await selectComposition({ ...common, id: 'AtlasVideo' });
  const fps = composition.fps;
  const totalSeconds = composition.durationInFrames / fps;
  const timings = sceneTimings(resolved, totalSeconds);

  const outDir = join(ROOT, 'out', 'stills', resolved.meta.slug);
  rmSync(outDir, { recursive: true, force: true });
  mkdirSync(outDir, { recursive: true });

  const shots: { file: string; label: string }[] = [];
  const shoot = async (frame: number, name: string, label: string) => {
    const f = Math.min(composition.durationInFrames - 1, Math.max(0, frame));
    const file = join(outDir, `${name}.png`);
    await renderStill({ ...common, composition, frame: f, output: file, imageFormat: 'png' });
    shots.push({ file, label: `${label} · ${(f / fps).toFixed(2)} s` });
    console.log(`  ${file}`);
  };

  for (const t of timings) {
    const scene = resolved.scenes[t.index];
    if (onlyScenes && !onlyScenes.includes(scene.id)) continue;
    const nn = String(t.index).padStart(2, '0');
    const startF = Math.round(t.start * fps);
    const endF = Math.round(t.end * fps) - 1;
    await shoot(Math.round((startF + endF) / 2), `${nn}-${scene.id}-mid`, `${scene.id} (${scene.type}) mitad`);
    await shoot(endF, `${nn}-${scene.id}-end`, `${scene.id} (${scene.type}) final`);
  }
  for (const s of extraTimes) await shoot(Math.round(s * fps), `t-${s.toFixed(2)}`, `t=${s}`);

  const rows = Math.ceil(shots.length / COLS);
  const sheet = sharp({
    create: { width: COLS * THUMB_W, height: rows * (THUMB_H + LABEL_H), channels: 3, background: '#222' },
  });
  const tiles = await Promise.all(
    shots.map(async (shot, i) => {
      const thumb = await sharp(shot.file).resize(THUMB_W, THUMB_H).png().toBuffer();
      const label = Buffer.from(
        `<svg width="${THUMB_W}" height="${LABEL_H}"><rect width="100%" height="100%" fill="#111"/><text x="10" y="23" font-family="monospace" font-size="16" fill="#eee">${escapeXml(shot.label)}</text></svg>`,
      );
      const x = (i % COLS) * THUMB_W;
      const y = Math.floor(i / COLS) * (THUMB_H + LABEL_H);
      return [
        { input: label, left: x, top: y },
        { input: thumb, left: x, top: y + LABEL_H },
      ];
    }),
  );
  const sheetFile = join(outDir, 'contact-sheet.jpg');
  await sheet.composite(tiles.flat()).jpeg({ quality: 85 }).toFile(sheetFile);
  console.log(`Hoja de contactos: ${sheetFile}`);
});
