/**
 * Paquete de región: textura de relieve ya proyectada + mapa de alturas + meta.json.
 *
 *   npm run atlas:data -- region <id>        (definición en scripts/atlas-data/regions/<id>.json)
 *
 * Salida en public/atlas-data/regions/<id>/: relief.jpg, relief-night.jpg, height.png (16 bits,
 * mitad de resolución), meta.json. Todo determinista; las teselas se guardan en .cache/.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { geoArea, geoPath } from 'd3-geo';
import type { Feature, Polygon } from 'geojson';
import sharp from 'sharp';
import { makeProjection, type ProjectionSpec, type RegionMeta } from '../../remotion/atlas/geo/projection';
import { buildMosaic, ensureDir, landFeature, loadSeas, OUT, ROOT, run, sampleMosaic, SEAS_SOURCE, TERRARIUM_SOURCE, WORLD_ATLAS_SOURCE } from './lib';

interface RegionDef {
  id: string;
  bbox: [[number, number], [number, number]];
  projection: Omit<ProjectionSpec, 'scale' | 'translate'>;
  width: number;
  zoom: number;
  /** Margen en grados de las teselas alrededor de la vista (0,5 por defecto; menos en zonas pequeñas a mucho zoom). */
  margin?: number;
  /** Agua por altura en vez de la costa de Natural Earth (escala de ciudad: ríos y bahías que la costa 50m no tiene). */
  water?: { belowM: number } | { seas: true; riversBelowM?: number };
}

export const HEIGHT_MIN = -11000;
export const HEIGHT_MAX = 9000;

type RGB = [number, number, number];
const hex = (h: string): RGB => [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)];
const ramp = (stops: [number, string][], v: number): RGB => {
  const s = stops.map(([x, c]) => [x, hex(c)] as const);
  if (v <= s[0][0]) return [...s[0][1]] as RGB;
  for (let i = 1; i < s.length; i++) {
    if (v <= s[i][0]) {
      const t = (v - s[i - 1][0]) / (s[i][0] - s[i - 1][0]);
      return [0, 1, 2].map((k) => s[i - 1][1][k] + (s[i][1][k] - s[i - 1][1][k]) * t) as RGB;
    }
  }
  return [...s[s.length - 1][1]] as RGB;
};

/** Paletas: tinte hipsométrico pergamino (día) y gris azulado (noche); mar por profundidad. */
const PALETTES = {
  paper: {
    // muestreado de referencias/atlas/frames/0-21 (llanuras #DACDB2–#DED1B6, mar #98ABB0 → #C0CFD2 en la costa)
    land: [
      [0, '#E0D4B9'],
      [800, '#DBCEB2'],
      [2000, '#D2C2A2'],
      [3500, '#C7B28D'],
      [5000, '#BDA781'],
      [7000, '#B49F7B'],
    ] as [number, string][],
    sea: [
      [-6000, '#8FA3A9'],
      [-3000, '#98ABB0'],
      [-1000, '#A7B9BD'],
      [-150, '#B8C8CB'],
      [0, '#C3D1D3'],
    ] as [number, string][],
    shadeStrength: 0.42,
  },
  night: {
    land: [
      [0, '#8D9FA8'],
      [3000, '#8297A2'],
      [6000, '#76909C'],
    ] as [number, string][],
    sea: [
      [-6000, '#1C3142'],
      [-1000, '#22384A'],
      [0, '#2A4255'],
    ] as [number, string][],
    shadeStrength: 0.5,
  },
};

run(async () => {
  const id = process.argv[2];
  if (!id) throw new Error('Uso: build-region <id>');
  const def = JSON.parse(readFileSync(join(ROOT, 'scripts', 'atlas-data', 'regions', `${id}.json`), 'utf8')) as RegionDef;
  const [[lonMin, latMin], [lonMax, latMax]] = def.bbox;

  // Proyección ajustada al ancho pedido.
  const ring: [number, number][] = [];
  for (let i = 0; i <= 40; i++) ring.push([lonMin + ((lonMax - lonMin) * i) / 40, latMin]);
  for (let i = 0; i <= 40; i++) ring.push([lonMax, latMin + ((latMax - latMin) * i) / 40]);
  for (let i = 0; i <= 40; i++) ring.push([lonMax - ((lonMax - lonMin) * i) / 40, latMax]);
  for (let i = 0; i <= 40; i++) ring.push([lonMin, latMax - ((latMax - latMin) * i) / 40]);
  const bboxFeature: Feature<Polygon> = { type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [ring.reverse()] } };
  const projection = makeProjection(def.projection).fitWidth(def.width, bboxFeature);
  const [[bx0, by0], [bx1, by1]] = geoPath(projection).bounds(bboxFeature);
  const W = def.width;
  const H = Math.round(by1 - by0);
  projection.translate([projection.translate()[0] - bx0, projection.translate()[1] - by0]);
  const spec: ProjectionSpec = { ...def.projection, scale: projection.scale(), translate: projection.translate() as [number, number] };
  console.log(`Región ${id}: ${W}×${H} px, ${def.projection.type}`);

  // Extensión geográfica real de la imagen (sus esquinas caen fuera del bbox en una cónica).
  let gLonMin = 180, gLonMax = -180, gLatMin = 90, gLatMax = -90;
  const edge = (x: number, y: number) => {
    const ll = projection.invert!([x, y]);
    if (!ll) return;
    gLonMin = Math.min(gLonMin, ll[0]);
    gLonMax = Math.max(gLonMax, ll[0]);
    gLatMin = Math.min(gLatMin, ll[1]);
    gLatMax = Math.max(gLatMax, ll[1]);
  };
  for (let x = 0; x <= W; x += 32) (edge(x, 0), edge(x, H));
  for (let y = 0; y <= H; y += 32) (edge(0, y), edge(W, y));
  console.log(`Extensión: lon ${gLonMin.toFixed(1)}…${gLonMax.toFixed(1)}, lat ${gLatMin.toFixed(1)}…${gLatMax.toFixed(1)}`);

  const margin = def.margin ?? 0.5;
  const mosaic = await buildMosaic(def.zoom, gLonMin - margin, gLonMax + margin, gLatMin - margin, gLatMax + margin);

  // Alturas en el espacio proyectado.
  console.log('Muestreando alturas…');
  const height = new Float32Array(W * H);
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      const ll = projection.invert!([x + 0.5, y + 0.5]);
      height[y * W + x] = ll ? sampleMosaic(mosaic, ll[0], ll[1]) : 0;
    }
  }

  // Máscara de tierra de Natural Earth (el DEM tiene depresiones bajo el nivel del mar en tierra).
  console.log('Máscara de tierra…');
  const landPath = geoPath(projection)(landFeature('50m')) ?? '';
  // agua por altura: sobre las alturas medianas de un entorno de 7×7 (los ríos del DEM traen manchas de 1-2 m)
  const waterMask = (below = (def.water as { belowM: number }).belowM) => {
    const r = 3;
    const out = new Uint8Array(W * H);
    const win: number[] = [];
    for (let y = 0; y < H; y++) {
      for (let x = 0; x < W; x++) {
        win.length = 0;
        for (let dy = -r; dy <= r; dy += 1) {
          const yy = Math.max(0, Math.min(H - 1, y + dy));
          for (let dx = -r; dx <= r; dx += 1) win.push(height[yy * W + Math.max(0, Math.min(W - 1, x + dx))]);
        }
        win.sort((a, b) => a - b);
        out[y * W + x] = win[win.length >> 1] > below ? 255 : 0;
      }
    }
    return Buffer.from(out);
  };
  // mares y estuarios de OSM: el océano es un polígono enorme con la tierra como agujeros; se pinta todo de agua y
  // encima, en blanco, los agujeros (la tierra) que tocan la vista
  const seasMask = async () => {
    const seas = await loadSeas();
    const near = (ring: number[][]) => ring.some(([lon, lat]) => lon >= gLonMin - 0.2 && lon <= gLonMax + 0.2 && lat >= gLatMin - 0.2 && lat <= gLatMax + 0.2);
    const land: number[][][][] = [];
    let sea = false;
    for (const f of seas.features) {
      const all = f.geometry.type === 'Polygon' ? [f.geometry.coordinates as unknown as number[][][]] : f.geometry.coordinates;
      for (const poly of all) {
        const holes = poly.slice(1).filter(near);
        if (!holes.length && !near(poly[0])) continue;
        sea = true;
        for (const h of holes) {
          // d3 toma como interior el lado de menor área: un anillo al revés sería «todo menos la isla»
          const ring = geoArea({ type: 'Polygon', coordinates: [h] }) > 2 * Math.PI ? [...h].reverse() : h;
          land.push([ring]);
        }
      }
    }
    if (!sea) throw new Error('La región no toca ningún mar de OSM: usa "water": {"belowM": …} o quita "water".');
    const d = geoPath(projection.clipExtent([[-10, -10], [W + 10, H + 10]]))({ type: 'MultiPolygon', coordinates: land }) ?? '';
    projection.clipExtent(null);
    return sharp(Buffer.from(`<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}"><rect width="100%" height="100%" fill="#000"/><path d="${d}" fill="#fff"/></svg>`))
      .greyscale()
      .raw()
      .toBuffer();
  };
  // el río más arriba de donde OSM cierra el mar: lo bajo (mediana del entorno) conectado con el mar, por inundación
  const withRivers = (mask: Buffer, below: number) => {
    const low = waterMask(below);
    const queue: number[] = [];
    for (let i = 0; i < W * H; i++) if (mask[i] === 0) queue.push(i);
    while (queue.length) {
      const i = queue.pop()!;
      const x = i % W;
      for (const j of [i - 1, i + 1, i - W, i + W]) {
        if (j < 0 || j >= W * H || (j === i - 1 && x === 0) || (j === i + 1 && x === W - 1)) continue;
        if (mask[j] !== 0 && low[j] === 0) {
          mask[j] = 0;
          queue.push(j);
        }
      }
    }
    return mask;
  };
  const mask = def.water && 'seas' in def.water
    ? def.water.riversBelowM !== undefined
      ? withRivers(await seasMask(), def.water.riversBelowM)
      : await seasMask()
    : def.water
    ? waterMask()
    : await sharp(Buffer.from(`<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}"><path d="${landPath}" fill="#fff"/></svg>`))
        .greyscale()
        .raw()
        .toBuffer();

  // Sombreado: luz del noroeste a 45°, exageración vertical moderada, mezcla de dos escalas.
  const metersPerPixel = 6371000 / projection.scale();
  const shadeAt = (step: number) => {
    const out = new Float32Array(W * H);
    const az = (315 * Math.PI) / 180;
    const alt = (45 * Math.PI) / 180;
    const ex = 2.2;
    for (let y = 0; y < H; y++) {
      const ya = Math.max(0, y - step);
      const yb = Math.min(H - 1, y + step);
      for (let x = 0; x < W; x++) {
        const xa = Math.max(0, x - step);
        const xb = Math.min(W - 1, x + step);
        const dzdx = ((Math.max(0, height[y * W + xb]) - Math.max(0, height[y * W + xa])) * ex) / ((xb - xa) * metersPerPixel);
        const dzdy = ((Math.max(0, height[yb * W + x]) - Math.max(0, height[ya * W + x])) * ex) / ((yb - ya) * metersPerPixel);
        const slope = Math.atan(Math.hypot(dzdx, dzdy));
        const aspect = Math.atan2(dzdy, -dzdx);
        const shade = Math.cos(Math.PI / 2 - alt) * Math.cos(slope) + Math.sin(Math.PI / 2 - alt) * Math.sin(slope) * Math.cos(az - aspect);
        out[y * W + x] = shade;
      }
    }
    return out;
  };
  // Profundidad suavizada en el agua: las teselas traen lagos y mares interiores a escalones (Caspio, Aral).
  console.log('Suavizando el agua…');
  const depth = new Float32Array(W * H);
  for (let i = 0; i < W * H; i++) depth[i] = mask[i] > 127 ? 0 : Math.min(0, height[i]);
  const boxBlur = (src: Float32Array, r: number) => {
    const tmp = new Float32Array(W * H);
    const out = new Float32Array(W * H);
    for (let y = 0; y < H; y++) {
      let acc = 0;
      for (let x = -r; x <= r; x++) acc += src[y * W + Math.max(0, Math.min(W - 1, x))];
      for (let x = 0; x < W; x++) {
        tmp[y * W + x] = acc / (2 * r + 1);
        acc += src[y * W + Math.min(W - 1, x + r + 1)] - src[y * W + Math.max(0, x - r)];
      }
    }
    for (let x = 0; x < W; x++) {
      let acc = 0;
      for (let y = -r; y <= r; y++) acc += tmp[Math.max(0, Math.min(H - 1, y)) * W + x];
      for (let y = 0; y < H; y++) {
        out[y * W + x] = acc / (2 * r + 1);
        acc += tmp[Math.min(H - 1, y + r + 1) * W + x] - tmp[Math.max(0, y - r) * W + x];
      }
    }
    return out;
  };
  const smoothDepth = boxBlur(boxBlur(depth, 6), 6);
  console.log('Sombreado…');
  const fine = shadeAt(1);
  const broad = shadeAt(4);
  const flat = Math.cos(Math.PI / 4);

  const dir = join(OUT, 'regions', id);
  ensureDir(dir);
  for (const theme of ['paper', 'night'] as const) {
    const pal = PALETTES[theme];
    const rgb = Buffer.alloc(W * H * 3);
    for (let i = 0; i < W * H; i++) {
      const isLand = mask[i] > 127;
      const h = height[i];
      const base = isLand ? ramp(pal.land, Math.max(0, h)) : ramp(pal.sea, smoothDepth[i]);
      const s = 0.6 * fine[i] + 0.4 * broad[i];
      const k = isLand ? 1 + (s - flat) * pal.shadeStrength * 1.6 : 1 + (s - flat) * 0.12;
      rgb[i * 3] = Math.max(0, Math.min(255, base[0] * k));
      rgb[i * 3 + 1] = Math.max(0, Math.min(255, base[1] * k));
      rgb[i * 3 + 2] = Math.max(0, Math.min(255, base[2] * k));
    }
    const file = theme === 'paper' ? 'relief.jpg' : 'relief-night.jpg';
    await sharp(rgb, { raw: { width: W, height: H, channels: 3 } }).jpeg({ quality: 80, mozjpeg: true }).toFile(join(dir, file));
    console.log(`  ${file}`);
  }

  // Alturas a mitad de resolución, 16 bits: v = (m − MIN) / (MAX − MIN) · 65535.
  const hw = Math.floor(W / 2);
  const hh = Math.floor(H / 2);
  const h16 = new Uint16Array(hw * hh);
  for (let y = 0; y < hh; y++) {
    for (let x = 0; x < hw; x++) {
      const i = 2 * y * W + 2 * x;
      const m = (height[i] + height[i + 1] + height[i + W] + height[i + W + 1]) / 4;
      h16[y * hw + x] = Math.round(((Math.max(HEIGHT_MIN, Math.min(HEIGHT_MAX, m)) - HEIGHT_MIN) / (HEIGHT_MAX - HEIGHT_MIN)) * 65535);
    }
  }
  // Un Uint16Array como entrada raw: sharp lo trata como 16 bits por canal.
  await sharp(h16, { raw: { width: hw, height: hh, channels: 1 } }).toColourspace('grey16').png({ compressionLevel: 9 }).toFile(join(dir, 'height.png'));

  const meta: RegionMeta = {
    id,
    width: W,
    height: H,
    projection: spec,
    metersPerPixel,
    bbox: def.bbox,
    files: { relief: 'relief.jpg', reliefNight: 'relief-night.jpg', height: 'height.png' },
    heightEncoding: { min: HEIGHT_MIN, max: HEIGHT_MAX, note: 'PNG gris 16 bits a mitad de resolución; metros = MIN + v/65535·(MAX−MIN)' },
    sources: [TERRARIUM_SOURCE, def.water && 'seas' in def.water ? SEAS_SOURCE : WORLD_ATLAS_SOURCE],
  };
  await import('node:fs').then((fs) => fs.writeFileSync(join(dir, 'meta.json'), JSON.stringify(meta, null, 2) + '\n'));
  console.log(`Listo: ${dir}`);
});
