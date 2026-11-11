/**
 * Textura equirectangular del mundo para atlas-globe: relieve sombreado, tinte de tierra, mar por profundidad,
 * hielo de Natural Earth; versión día (papel) y noche.
 *
 *   npm run atlas:data -- globe [ancho=4096] [zoom=4]   → public/atlas-data/globe/earth-{paper,night}.jpg + meta.json
 */
import { join } from 'node:path';
import { writeFileSync } from 'node:fs';
import { geoEquirectangular, geoPath } from 'd3-geo';
import sharp from 'sharp';
import { buildMosaic, countriesFeature, ensureDir, landFeature, OUT, run, sampleMosaic, TERRARIUM_SOURCE, WORLD_ATLAS_SOURCE } from './lib';
import { FLAT, lambert, PALETTES, ramp } from './palette';

run(async () => {
  const W = Number(process.argv[2] ?? 4096);
  const z = Number(process.argv[3] ?? 4);
  const H = W / 2;
  const mosaic = await buildMosaic(z, -180, 179.999, -85, 85);
  console.log('Muestreando…');
  const height = new Float32Array(W * H);
  for (let y = 0; y < H; y++) {
    const lat = 90 - ((y + 0.5) / H) * 180;
    for (let x = 0; x < W; x++) {
      const lon = -180 + ((x + 0.5) / W) * 360;
      height[y * W + x] = sampleMosaic(mosaic, lon, Math.max(-84.9, Math.min(84.9, lat)));
    }
  }
  const proj = geoEquirectangular().scale(W / (2 * Math.PI)).translate([W / 2, H / 2]).precision(0.1);
  const svg = (d: string) => Buffer.from(`<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}"><path d="${d}" fill="#fff"/></svg>`);
  const land = await sharp(svg(geoPath(proj)(landFeature('50m')) ?? '')).greyscale().raw().toBuffer();
  const iceFc = { type: 'FeatureCollection' as const, features: countriesFeature('50m').features.filter((f) => ['Antarctica', 'Greenland'].includes(f.properties.name)) };
  const ice = await sharp(svg(geoPath(proj)(iceFc) ?? '')).greyscale().raw().toBuffer();
  const mPerPx = (2 * Math.PI * 6371000) / W;
  // profundidad suavizada en el agua: las teselas de zoom bajo dejan lagos y mares interiores a escalones
  const depth = new Float32Array(W * H);
  for (let i = 0; i < W * H; i++) depth[i] = land[i] > 127 ? 0 : Math.min(0, height[i]);
  const blur = (src: Float32Array, r: number) => {
    const a = new Float32Array(W * H);
    const b = new Float32Array(W * H);
    for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
      let s = 0;
      for (let k = -r; k <= r; k++) s += src[y * W + ((x + k + W) % W)];
      a[y * W + x] = s / (2 * r + 1);
    }
    for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
      let s = 0;
      for (let k = -r; k <= r; k++) s += a[Math.min(H - 1, Math.max(0, y + k)) * W + x];
      b[y * W + x] = s / (2 * r + 1);
    }
    return b;
  };
  const smoothDepth = blur(depth, 5);
  const dir = join(OUT, 'globe');
  ensureDir(dir);
  for (const theme of ['paper', 'night'] as const) {
    const pal = PALETTES[theme];
    const rgb = Buffer.alloc(W * H * 3);
    for (let y = 0; y < H; y++) {
      const lat = 90 - ((y + 0.5) / H) * 180;
      const sx = mPerPx * Math.max(0.05, Math.cos((lat * Math.PI) / 180));
      for (let x = 0; x < W; x++) {
        const i = y * W + x;
        const isLand = land[i] > 127;
        const h = height[i];
        const l = Math.max(0, height[y * W + ((x - 1 + W) % W)]);
        const r = Math.max(0, height[y * W + ((x + 1) % W)]);
        const u = Math.max(0, height[Math.max(0, y - 1) * W + x]);
        const d = Math.max(0, height[Math.min(H - 1, y + 1) * W + x]);
        const shade = lambert(((r - l) * 3) / (2 * sx), ((d - u) * 3) / (2 * mPerPx));
        const base = ice[i] > 127 ? ramp([[0, pal.ice]], 0) : isLand ? ramp(pal.land, Math.max(0, h)) : ramp(pal.sea, smoothDepth[i]);
        const k = isLand ? 1 + (shade - FLAT) * pal.shadeStrength * 1.4 : 1 + (shade - FLAT) * 0.1;
        for (let c = 0; c < 3; c++) rgb[i * 3 + c] = Math.max(0, Math.min(255, base[c] * k));
      }
    }
    await sharp(rgb, { raw: { width: W, height: H, channels: 3 } }).jpeg({ quality: 82, mozjpeg: true }).toFile(join(dir, `earth-${theme}.jpg`));
    console.log(`  earth-${theme}.jpg`);
  }
  writeFileSync(join(dir, 'meta.json'), JSON.stringify({ width: W, height: H, projection: 'equirectangular', sources: [TERRARIUM_SOURCE, WORLD_ATLAS_SOURCE] }, null, 2) + '\n');
});
