/**
 * Silueta de un país de Natural Earth (world-atlas 50m), para compararla a escala real en un mapa.
 *
 *   npm run atlas:data -- country <nombre en inglés> [id]   → public/atlas-data/shapes/<id>.geojson
 */
import { join } from 'node:path';
import { geoArea } from 'd3-geo';
import { countriesFeature, OUT, roundCoords, run, writeJson, WORLD_ATLAS_SOURCE } from './lib';

run(async () => {
  const [name, idArg] = process.argv.slice(2);
  if (!name) throw new Error('Uso: atlas:data country <nombre en inglés> [id]');
  const all = countriesFeature('50m').features;
  const found = all.find((f) => f.properties.name.toLowerCase() === name.toLowerCase());
  if (!found) {
    const near = all.map((f) => f.properties.name).filter((n) => n.toLowerCase().includes(name.toLowerCase().slice(0, 4)));
    throw new Error(`"${name}" no está en Natural Earth.${near.length ? ' ¿Quizá: ' + near.join(', ') + '?' : ''}`);
  }
  const id = idArg ?? name.toLowerCase().replace(/[^a-z0-9]+/g, '-');
  const file = join(OUT, 'shapes', `${id}.geojson`);
  writeJson(file, { type: 'Feature', properties: { name: found.properties.name, source: WORLD_ATLAS_SOURCE }, geometry: roundCoords(found.geometry, 3) });
  console.log(`${file}: ${found.properties.name}, ≈${(geoArea(found) * 6371 ** 2).toFixed(0)} km²`);
});
