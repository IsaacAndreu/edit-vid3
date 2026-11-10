/**
 * storyboard + transcripción → storyboard con tiempos absolutos ({ t } en cada At).
 *
 *   npm run atlas:anchors -- <storyboard.json> [transcript.json] [--out resolved.json]
 *
 * Sin transcript explícito usa audio.transcript (relativo a public/). Falla si una frase no
 * aparece o aparece más de una vez sin `nth`.
 */
import { writeFileSync } from 'node:fs';
import { loadStoryboard, run } from './load';
import { sceneTimings, sec } from '../../templates/atlas/time';

run(() => {
  const args = process.argv.slice(2);
  const outIndex = args.indexOf('--out');
  const out = outIndex >= 0 ? args[outIndex + 1] : undefined;
  const positional = outIndex >= 0 ? args.filter((_, i) => i !== outIndex && i !== outIndex + 1) : args;
  const [storyboardPath, transcriptPath] = positional;
  if (!storyboardPath) throw new Error('Uso: atlas:anchors <storyboard.json> [transcript.json] [--out archivo]');
  const { resolved } = loadStoryboard(storyboardPath, transcriptPath);
  const json = JSON.stringify(resolved, null, 2) + '\n';
  if (out) {
    writeFileSync(out, json);
    const total = resolved.meta.duration;
    const timings = total ? sceneTimings(resolved, total) : null;
    console.error(`Anclas resueltas → ${out}`);
    resolved.scenes.forEach((s, i) =>
      console.error(`  ${sec(s.start).toFixed(2).padStart(7)} s  ${s.id}${timings ? ` (${(timings[i].end - timings[i].start).toFixed(2)} s)` : ''}`),
    );
  } else {
    process.stdout.write(json);
  }
});
