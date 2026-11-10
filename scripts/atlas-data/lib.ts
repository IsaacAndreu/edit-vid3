/** Utilidades de los scripts de datos: teselas Terrarium con caché, mosaico de alturas, Natural Earth. */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import sharp from 'sharp';
import type { FeatureCollection, MultiPolygon, Polygon } from 'geojson';
import { feature } from 'topojson-client';
import type { GeometryCollection, Topology } from 'topojson-specification';

export const ROOT = resolve(__dirname, '..', '..');
export const CACHE = join(ROOT, '.cache', 'atlas-data');
export const OUT = join(ROOT, 'public', 'atlas-data');

export const TERRARIUM_URL = 'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png';
export const TERRARIUM_SOURCE =
  'Elevación: Terrarium (tilezen/joerd) — SRTM, GMTED, ETOPO1 y otras fuentes públicas; https://github.com/tilezen/joerd/blob/master/docs/attribution.md';

export const ensureDir = (p: string) => mkdirSync(p, { recursive: true });

/** Descarga con caché en disco; falla con mensaje claro, nunca inventa datos. */
export const cachedFetch = async (url: string, cachePath: string, retries = 3): Promise<Buffer> => {
  if (existsSync(cachePath)) return readFileSync(cachePath);
  let lastError = '';
  for (let attempt = 0; attempt < retries; attempt++) {
    try {
      const res = await fetch(url);
      if (res.ok) {
        const buf = Buffer.from(await res.arrayBuffer());
        ensureDir(dirname(cachePath));
        writeFileSync(cachePath, buf);
        return buf;
      }
      lastError = `HTTP ${res.status}`;
      if (res.status === 403 || res.status === 404) break;
    } catch (err) {
      lastError = (err as Error & { cause?: { code?: string } }).cause?.code ?? (err as Error).message;
    }
    await new Promise((r) => setTimeout(r, 1000 * 2 ** attempt));
  }
  throw new Error(`No se pudo descargar ${url} (${lastError}). Sin datos reales no se genera nada.`);
};

/** Ejecuta tareas con concurrencia limitada. */
export const pool = async <T, R>(items: T[], limit: number, fn: (item: T, i: number) => Promise<R>): Promise<R[]> => {
  const out: R[] = new Array(items.length);
  let next = 0;
  await Promise.all(
    Array.from({ length: Math.min(limit, items.length) }, async () => {
      while (next < items.length) {
        const i = next++;
        out[i] = await fn(items[i], i);
      }
    }),
  );
  return out;
};

/* ── Web Mercator ── */
export const lonToTileX = (lon: number, z: number) => ((lon + 180) / 360) * 2 ** z;
export const latToTileY = (lat: number, z: number) => {
  const r = (Math.max(-85.0511, Math.min(85.0511, lat)) * Math.PI) / 180;
  return ((1 - Math.log(Math.tan(r) + 1 / Math.cos(r)) / Math.PI) / 2) * 2 ** z;
};

/** Fórmula Terrarium (tilezen/joerd docs/formats.md): (R·256 + G + B/256) − 32768. */
export const decodeTerrarium = (r: number, g: number, b: number) => r * 256 + g + b / 256 - 32768;

export interface Mosaic {
  z: number;
  x0: number;
  y0: number;
  cols: number;
  rows: number;
  width: number;
  height: number;
  data: Float32Array;
}

/** Descarga y decodifica todas las teselas que cubren [lonMin..lonMax]×[latMin..latMax]. */
export const buildMosaic = async (z: number, lonMin: number, lonMax: number, latMin: number, latMax: number): Promise<Mosaic> => {
  const n = 2 ** z;
  const x0 = Math.max(0, Math.floor(lonToTileX(lonMin, z)));
  const x1 = Math.min(n - 1, Math.floor(lonToTileX(lonMax, z)));
  const y0 = Math.max(0, Math.floor(latToTileY(latMax, z)));
  const y1 = Math.min(n - 1, Math.floor(latToTileY(latMin, z)));
  const cols = x1 - x0 + 1;
  const rows = y1 - y0 + 1;
  const width = cols * 256;
  const height = rows * 256;
  const data = new Float32Array(width * height);
  const tiles: [number, number][] = [];
  for (let y = y0; y <= y1; y++) for (let x = x0; x <= x1; x++) tiles.push([x, y]);
  let done = 0;
  await pool(tiles, 8, async ([x, y]) => {
    const url = TERRARIUM_URL.replace('{z}', String(z)).replace('{x}', String(x)).replace('{y}', String(y));
    const buf = await cachedFetch(url, join(CACHE, 'terrarium', String(z), String(x), `${y}.png`));
    const { data: px, info } = await sharp(buf).removeAlpha().raw().toBuffer({ resolveWithObject: true });
    if (info.width !== 256 || info.height !== 256) throw new Error(`Tesela ${z}/${x}/${y} con tamaño inesperado`);
    const ox = (x - x0) * 256;
    const oy = (y - y0) * 256;
    for (let j = 0; j < 256; j++) {
      for (let i = 0; i < 256; i++) {
        const k = (j * 256 + i) * 3;
        data[(oy + j) * width + ox + i] = decodeTerrarium(px[k], px[k + 1], px[k + 2]);
      }
    }
    done++;
    if (done % 50 === 0 || done === tiles.length) process.stderr.write(`  teselas ${done}/${tiles.length}\r`);
  });
  process.stderr.write('\n');
  return { z, x0, y0, cols, rows, width, height, data };
};

/** Altura (m) en un punto, interpolación bilineal sobre el mosaico. */
export const sampleMosaic = (m: Mosaic, lon: number, lat: number): number => {
  const fx = (lonToTileX(lon, m.z) - m.x0) * 256 - 0.5;
  const fy = (latToTileY(lat, m.z) - m.y0) * 256 - 0.5;
  const x = Math.max(0, Math.min(m.width - 2, Math.floor(fx)));
  const y = Math.max(0, Math.min(m.height - 2, Math.floor(fy)));
  const tx = Math.max(0, Math.min(1, fx - x));
  const ty = Math.max(0, Math.min(1, fy - y));
  const i = y * m.width + x;
  const a = m.data[i];
  const b = m.data[i + 1];
  const c = m.data[i + m.width];
  const d = m.data[i + m.width + 1];
  return a * (1 - tx) * (1 - ty) + b * tx * (1 - ty) + c * (1 - tx) * ty + d * tx * ty;
};

/* ── Natural Earth vía world-atlas (TopoJSON) ── */
type WorldTopo = Topology<{ land: GeometryCollection; countries: GeometryCollection }>;

export const WORLD_ATLAS_SOURCE = 'Costas y países: Natural Earth vía el paquete npm world-atlas (dominio público)';

export const loadWorld = (res: '110m' | '50m' = '50m'): WorldTopo =>
  JSON.parse(readFileSync(join(ROOT, 'node_modules', 'world-atlas', `countries-${res}.json`), 'utf8')) as WorldTopo;

export const landFeature = (res: '110m' | '50m' = '50m') => {
  const world = loadWorld(res);
  return feature(world, world.objects.land) as FeatureCollection<Polygon | MultiPolygon>;
};

export const countriesFeature = (res: '110m' | '50m' = '50m') => {
  const world = loadWorld(res);
  return feature(world, world.objects.countries) as FeatureCollection<Polygon | MultiPolygon, { name: string }>;
};

export const writeJson = (path: string, data: unknown) => {
  ensureDir(dirname(path));
  writeFileSync(path, JSON.stringify(data));
};

/** Redondea coordenadas para que los GeoJSON pesen poco. */
export const roundCoords = <T>(geom: T, digits = 3): T =>
  JSON.parse(JSON.stringify(geom, (_k, v) => (typeof v === 'number' ? Number(v.toFixed(digits)) : v))) as T;

export const run = (main: () => Promise<void>) => {
  main().catch((err: Error) => {
    console.error(err.message);
    process.exit(1);
  });
};
