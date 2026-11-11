/**
 * Bloque de terreno para atlas-terrain-3d: rejilla de alturas en un plano local (km) y su textura con sombreado y
 * curvas de nivel, día y noche.
 *
 *   npm run atlas:data -- terrain <id> <lonMin,latMin,lonMax,latMax> <columnas> <zoom> <curvas_m> [suavizado=1]
 *     → public/atlas-data/terrain/<id>/{meta.json, heights.json, tex-paper.jpg, tex-night.jpg}
 *
 * x = km hacia el este y z = km hacia el norte desde el centro (aproximación local, buena para bloques < 3.500 km).
 */
import { writeFileSync } from 'node:fs';
import { join } from 'node:path';
import sharp from 'sharp';
import { buildMosaic, ensureDir, OUT, run, sampleMosaic, TERRARIUM_SOURCE } from './lib';
import { FLAT, lambert, PALETTES, ramp } from './palette';

run(async () => {
  const [id, bboxArg, colsArg, zoomArg, stepArg, smoothArg] = process.argv.slice(2);
  // radio de suavizado de la malla en celdas: con exageraciones grandes el ruido del DEM se vuelve agujas
  const smoothR = Number(smoothArg ?? 1);
  const bbox = (bboxArg ?? '').split(',').map(Number);
  if (!id || bbox.length !== 4) throw new Error('Uso: atlas:data terrain <id> <lonMin,latMin,lonMax,latMax> <columnas> <zoom> <curvas_m>');
  const [lonMin, latMin, lonMax, latMax] = bbox;
  const cols = Number(colsArg ?? 400);
  const z = Number(zoomArg ?? 7);
  const step = Number(stepArg ?? 500);
  const lat0 = (latMin + latMax) / 2;
  const kmLon = 111.32 * Math.cos((lat0 * Math.PI) / 180);
  const kmLat = 110.57;
  const widthKm = (lonMax - lonMin) * kmLon;
  const depthKm = (latMax - latMin) * kmLat;
  const rows = Math.round((cols * depthKm) / widthKm);
  const mosaic = await buildMosaic(z, lonMin - 0.1, lonMax + 0.1, latMin - 0.1, latMax + 0.1);
  // rejilla de alturas (fila 0 = norte)
  const raw: number[] = [];
  for (let r = 0; r < rows; r++) {
    const lat = latMax - (r / (rows - 1)) * (latMax - latMin);
    for (let c = 0; c < cols; c++) raw.push(Math.max(0, sampleMosaic(mosaic, lonMin + (c / (cols - 1)) * (lonMax - lonMin), lat)));
  }
  const heights: number[] = raw.map((_, i) => {
    if (smoothR <= 0) return Math.round(raw[i]);
    const r0 = Math.floor(i / cols);
    const c0 = i % cols;
    let a = 0;
    let n = 0;
    for (let dr = -smoothR; dr <= smoothR; dr++)
      for (let dc = -smoothR; dc <= smoothR; dc++) {
        const rr = Math.min(rows - 1, Math.max(0, r0 + dr));
        const cc = Math.min(cols - 1, Math.max(0, c0 + dc));
        a += raw[rr * cols + cc];
        n++;
      }
    return Math.round(a / n);
  });
  // textura 4× más fina que la rejilla, con curvas de nivel cada `step` m
  const TW = Math.min(4096, cols * 4);
  const TH = Math.round((TW * depthKm) / widthKm);
  const tex = new Float32Array(TW * TH);
  for (let y = 0; y < TH; y++) {
    const lat = latMax - ((y + 0.5) / TH) * (latMax - latMin);
    for (let x = 0; x < TW; x++) tex[y * TW + x] = Math.max(0, sampleMosaic(mosaic, lonMin + ((x + 0.5) / TW) * (lonMax - lonMin), lat));
  }
  const mPerPx = (widthKm * 1000) / TW;
  // alturas suavizadas sólo para trazar curvas de nivel limpias (el sombreado usa las reales)
  const smooth = new Float32Array(TW * TH);
  {
    const R = 4;
    const tmp = new Float32Array(TW * TH);
    for (let y = 0; y < TH; y++)
      for (let x = 0; x < TW; x++) {
        let a = 0;
        for (let k = -R; k <= R; k++) a += tex[y * TW + Math.min(TW - 1, Math.max(0, x + k))];
        tmp[y * TW + x] = a / (2 * R + 1);
      }
    for (let y = 0; y < TH; y++)
      for (let x = 0; x < TW; x++) {
        let a = 0;
        for (let k = -R; k <= R; k++) a += tmp[Math.min(TH - 1, Math.max(0, y + k)) * TW + x];
        smooth[y * TW + x] = a / (2 * R + 1);
      }
  }
  const dir = join(OUT, 'terrain', id);
  ensureDir(dir);
  for (const theme of ['paper', 'night'] as const) {
    const pal = PALETTES[theme];
    const rgb = Buffer.alloc(TW * TH * 3);
    const lineInk = theme === 'paper' ? [90, 72, 50] : [235, 240, 244];
    for (let y = 0; y < TH; y++) {
      for (let x = 0; x < TW; x++) {
        const i = y * TW + x;
        const h = tex[i];
        const l = tex[y * TW + Math.max(0, x - 1)];
        const r = tex[y * TW + Math.min(TW - 1, x + 1)];
        const u = tex[Math.max(0, y - 1) * TW + x];
        const d = tex[Math.min(TH - 1, y + 1) * TW + x];
        const shade = lambert(((r - l) * 2) / (2 * mPerPx), ((d - u) * 2) / (2 * mPerPx));
        const base = ramp(pal.land, h);
        const k = 1 + (shade - FLAT) * pal.shadeStrength * 1.5;
        // curva de nivel: el píxel cruza un múltiplo de `step` respecto a algún vecino
        const sh = smooth[i];
        const band = Math.floor(sh / step);
        const line = band !== Math.floor(smooth[y * TW + Math.min(TW - 1, x + 1)] / step) || band !== Math.floor(smooth[Math.min(TH - 1, y + 1) * TW + x] / step);
        for (let c = 0; c < 3; c++) {
          const v = base[c] * k;
          rgb[i * 3 + c] = Math.max(0, Math.min(255, line ? v * 0.7 + lineInk[c] * 0.3 : v));
        }
      }
    }
    await sharp(rgb, { raw: { width: TW, height: TH, channels: 3 } }).jpeg({ quality: 85, mozjpeg: true }).toFile(join(dir, `tex-${theme}.jpg`));
  }
  const maxM = Math.max(...heights);
  writeFileSync(join(dir, 'heights.json'), JSON.stringify(heights));
  writeFileSync(
    join(dir, 'meta.json'),
    JSON.stringify({ id, bbox: [lonMin, latMin, lonMax, latMax], smooth: smoothR, lat0, kmLon, kmLat, widthKm, depthKm, cols, rows, maxM, contourStep: step, zoom: z, source: TERRARIUM_SOURCE }, null, 2) + '\n',
  );
  console.log(`${dir}: ${Math.round(widthKm)}×${Math.round(depthKm)} km, ${cols}×${rows}, máx ${maxM} m, textura ${TW}×${TH}`);
});
