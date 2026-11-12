/**
 * Máximo de elevación por celda de 1°×1° (para la rejilla de altitudes mínimas seguras).
 *
 *   npm run atlas:data -- cells <id> <lonMin,latMin,lonMax,latMax> [zoom=9] [--peaks archivo.json]
 *     → public/atlas-data/cells/<id>.json  { cells: [{ lon, lat, m, peak? }], … }   (lon/lat = esquina suroeste)
 *
 * El máximo se toma píxel a píxel del mosaico. Los DEM suavizan las cumbres (el Everest sale ~1 % bajo), así que
 * --peaks admite cumbres medidas con su fuente ([{ name, lon, lat, m, source }]): si una cae en una celda y es más
 * alta que el DEM, manda la cumbre. Nunca se inventa: sin --peaks, se queda el DEM.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { buildMosaic, latToTileY, lonToTileX, OUT, run, TERRARIUM_SOURCE, writeJson } from './lib';

interface Peak {
  name: string;
  lon: number;
  lat: number;
  m: number;
  source: string;
}

run(async () => {
  const args = process.argv.slice(2);
  const peaksAt = args.indexOf('--peaks');
  const peaks: Peak[] = peaksAt >= 0 ? (JSON.parse(readFileSync(args[peaksAt + 1], 'utf8')) as Peak[]) : [];
  const [id, bboxArg, zoomArg] = args.filter((_, i) => peaksAt < 0 || (i !== peaksAt && i !== peaksAt + 1));
  const bbox = (bboxArg ?? '').split(',').map(Number);
  if (!id || bbox.length !== 4 || bbox.some((v) => !Number.isFinite(v))) {
    throw new Error('Uso: atlas:data cells <id> <lonMin,latMin,lonMax,latMax> [zoom] [--peaks archivo.json]');
  }
  const [lonMin, latMin, lonMax, latMax] = bbox.map((v, i) => (i < 2 ? Math.floor(v) : Math.ceil(v)));
  const z = Number(zoomArg ?? 9);
  const mosaic = await buildMosaic(z, lonMin, lonMax, latMin, latMax);
  const cells: { lon: number; lat: number; m: number; peak?: string }[] = [];
  for (let lat = latMin; lat < latMax; lat++) {
    for (let lon = lonMin; lon < lonMax; lon++) {
      const x0 = Math.max(0, Math.floor((lonToTileX(lon, z) - mosaic.x0) * 256));
      const x1 = Math.min(mosaic.width - 1, Math.ceil((lonToTileX(lon + 1, z) - mosaic.x0) * 256));
      const y0 = Math.max(0, Math.floor((latToTileY(lat + 1, z) - mosaic.y0) * 256));
      const y1 = Math.min(mosaic.height - 1, Math.ceil((latToTileY(lat, z) - mosaic.y0) * 256));
      let m = -Infinity;
      for (let y = y0; y < y1; y++) for (let x = x0; x < x1; x++) m = Math.max(m, mosaic.data[y * mosaic.width + x]);
      const cell: { lon: number; lat: number; m: number; peak?: string } = { lon, lat, m: Math.round(m) };
      for (const p of peaks) {
        if (p.lon >= lon && p.lon < lon + 1 && p.lat >= lat && p.lat < lat + 1 && p.m > cell.m) {
          cell.m = p.m;
          cell.peak = `${p.name} (${p.source})`;
        }
      }
      cells.push(cell);
    }
  }
  const file = join(OUT, 'cells', `${id}.json`);
  writeJson(file, { id, bbox: [lonMin, latMin, lonMax, latMax], zoom: z, cells, source: TERRARIUM_SOURCE, peaks });
  const top = cells.reduce((a, c) => (c.m > a.m ? c : a));
  console.log(`${file}: ${cells.length} celdas; la más alta ${top.m} m en ${top.lon},${top.lat}${top.peak ? ' — ' + top.peak : ''}`);
});
