/** Valida un storyboard (esquema + anclas + duraciones) sin renderizar. */
import { loadStoryboard, run } from './load';
import { sceneTimings } from '../../templates/atlas/time';

run(() => {
  const path = process.argv[2];
  if (!path) throw new Error('Uso: atlas:validate <storyboard.json>');
  const { resolved } = loadStoryboard(path);
  if (resolved.meta.duration) sceneTimings(resolved, resolved.meta.duration);
  console.log(`OK: ${path} · ${resolved.scenes.length} escenas`);
});
