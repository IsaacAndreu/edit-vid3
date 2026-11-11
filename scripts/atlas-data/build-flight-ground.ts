/**
 * Terreno bajo un vuelo real: añade a cada muestra de vuelo.json la altura del suelo debajo (pies, Terrarium).
 *
 *   npm run atlas:data -- flight-ground public/accidentes/<caso>/vuelo.json [zoom=13]
 *
 * Con el agua a 0 (un río o el mar debajo dan 0 ft, no la profundidad). La fuente se añade a vuelo.json.
 */
import { readFileSync } from 'node:fs';
import { buildMosaic, run, sampleMosaic, TERRARIUM_SOURCE, writeJson } from './lib';

run(async () => {
  const [file, zoomArg] = process.argv.slice(2);
  if (!file) throw new Error('Uso: atlas:data flight-ground <vuelo.json> [zoom]');
  const data = JSON.parse(readFileSync(file, 'utf8'));
  const pts: { lat: number; lon: number; terrain?: number }[] = data.points;
  const lons = pts.map((p) => p.lon);
  const lats = pts.map((p) => p.lat);
  const mosaic = await buildMosaic(Number(zoomArg ?? 13), Math.min(...lons) - 0.01, Math.max(...lons) + 0.01, Math.min(...lats) - 0.01, Math.max(...lats) + 0.01);
  const raw = pts.map((p) => Math.max(0, sampleMosaic(mosaic, p.lon, p.lat)) * 3.28084);
  // mediana de 5 muestras: una sola muestra sobre una chimenea o un artefacto del DEM no es el terreno
  pts.forEach((p, i) => {
    const win = raw.slice(Math.max(0, i - 2), i + 3).sort((a, b) => a - b);
    p.terrain = Math.round(win[win.length >> 1]);
  });
  data.groundSource = `Terreno bajo la trayectoria: ${TERRARIUM_SOURCE} (agua = 0 ft; mediana de 5 muestras)`;
  writeJson(file, data);
  const max = pts.reduce((a, p) => Math.max(a, p.terrain ?? 0), 0);
  console.log(`${file}: suelo en ${pts.length} muestras, máximo ${max} ft`);
});
