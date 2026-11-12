/**
 * Perfil de elevación a lo largo del círculo máximo entre dos puntos, con datos Terrarium.
 *
 *   npm run atlas:data -- profile <id> <lon,lat> <lon,lat> [muestras=700] [zoom=9]
 *     → public/atlas-data/profiles/<id>.json  { from, to, km, samples: [[km, metros], …], source }
 *
 * Cada muestra es el MÁXIMO en una franja de ±2 km perpendicular a la ruta: así los picos que la línea roza no
 * desaparecen entre dos muestras (un perfil de vuelo se preocupa por lo más alto que hay debajo).
 */
import { join } from 'node:path';
import { geoDistance, geoInterpolate } from 'd3-geo';
import { buildMosaic, OUT, run, sampleMosaic, TERRARIUM_SOURCE, writeJson } from './lib';

const parse = (s: string | undefined): [number, number] => {
  const [lon, lat] = (s ?? '').split(',').map(Number);
  if (!Number.isFinite(lon) || !Number.isFinite(lat)) throw new Error(`Punto inválido "${s}": usa lon,lat`);
  return [lon, lat];
};

run(async () => {
  const [id, a, b, samplesArg, zoomArg] = process.argv.slice(2);
  if (!id) throw new Error('Uso: atlas:data profile <id> <lon,lat> <lon,lat> [muestras] [zoom]');
  const from = parse(a);
  const to = parse(b);
  const n = Number(samplesArg ?? 700);
  const z = Number(zoomArg ?? 9);
  const km = geoDistance(from, to) * 6371;
  const line = geoInterpolate(from, to);
  const lons = [from[0], to[0]];
  const lats = [from[1], to[1]];
  for (let i = 1; i < 20; i++) {
    const p = line(i / 20);
    lons.push(p[0]);
    lats.push(p[1]);
  }
  const mosaic = await buildMosaic(z, Math.min(...lons) - 0.3, Math.max(...lons) + 0.3, Math.min(...lats) - 0.3, Math.max(...lats) + 0.3);
  const samples: [number, number][] = [];
  for (let i = 0; i <= n; i++) {
    const t = i / n;
    const p = line(t);
    const q = line(Math.min(1, t + 1e-4));
    // dirección perpendicular aproximada en grados
    const dx = q[0] - p[0];
    const dy = q[1] - p[1];
    const len = Math.hypot(dx, dy) || 1;
    const px = (-dy / len) * (2 / 111);
    const py = (dx / len) * (2 / 111);
    let m = -Infinity;
    for (let k = -2; k <= 2; k++) m = Math.max(m, sampleMosaic(mosaic, p[0] + (px * k) / 2, p[1] + (py * k) / 2));
    samples.push([Number((t * km).toFixed(2)), Math.round(m)]);
  }
  const file = join(OUT, 'profiles', `${id}.json`);
  writeJson(file, { id, from, to, km: Math.round(km), zoom: z, samples, source: TERRARIUM_SOURCE });
  const max = samples.reduce((acc, s) => (s[1] > acc[1] ? s : acc));
  console.log(`${file}: ${Math.round(km)} km, ${samples.length} muestras, máximo ${max[1]} m a ${max[0].toFixed(0)} km`);
});
