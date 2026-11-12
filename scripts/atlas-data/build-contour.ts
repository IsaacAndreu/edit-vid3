/**
 * Contorno de altura de un paquete de región, como GeoJSON en lon/lat.
 *
 *   npm run atlas:data -- contour <id> <metros>      → public/atlas-data/regions/<id>/contour-<metros>.geojson
 *
 * Sale del mapa de alturas del paquete (datos reales), suavizado un poco y sin islas diminutas, para que el
 * contorno se lea como el del original («LAND ABOVE 3,000 M»): una forma principal con sus huecos (cuencas).
 */
import { readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { contours } from 'd3-contour';
import { geoArea } from 'd3-geo';
import type { Feature, MultiPolygon, Position } from 'geojson';
import sharp from 'sharp';
import { makeProjection, type RegionMeta } from '../../remotion/atlas/geo/projection';
import { OUT, roundCoords, run } from './lib';

/** Douglas-Peucker en píxeles. */
const simplify = (pts: Position[], tol: number): Position[] => {
  if (pts.length < 4) return pts;
  const keep = new Uint8Array(pts.length);
  keep[0] = keep[pts.length - 1] = 1;
  const stack: [number, number][] = [[0, pts.length - 1]];
  while (stack.length) {
    const [a, b] = stack.pop()!;
    const [ax, ay] = pts[a];
    const [bx, by] = pts[b];
    const len = Math.hypot(bx - ax, by - ay) || 1;
    let best = -1;
    let bestD = tol;
    for (let i = a + 1; i < b; i++) {
      const d = Math.abs((bx - ax) * (ay - pts[i][1]) - (ax - pts[i][0]) * (by - ay)) / len;
      if (d > bestD) {
        bestD = d;
        best = i;
      }
    }
    if (best >= 0) {
      keep[best] = 1;
      stack.push([a, best], [best, b]);
    }
  }
  return pts.filter((_, i) => keep[i]);
};

/** Anillo cerrado: se parte por el punto más lejano del inicio y se simplifica cada mitad. */
const simplifyRing = (ring: Position[], tol: number): Position[] => {
  const pts = ring.slice(0, -1);
  let far = 0;
  let farD = -1;
  for (let i = 1; i < pts.length; i++) {
    const d = Math.hypot(pts[i][0] - pts[0][0], pts[i][1] - pts[0][1]);
    if (d > farD) {
      farD = d;
      far = i;
    }
  }
  const a = simplify(pts.slice(0, far + 1), tol);
  const b = simplify([...pts.slice(far), pts[0]], tol);
  const out = [...a, ...b.slice(1)];
  return out.length >= 4 ? out : ring;
};

const ringArea = (r: Position[]) => {
  let s = 0;
  for (let i = 0, j = r.length - 1; i < r.length; j = i++) s += (r[j][0] + r[i][0]) * (r[j][1] - r[i][1]);
  return Math.abs(s / 2);
};

run(async () => {
  const [id, metersArg] = process.argv.slice(2);
  const meters = Number(metersArg);
  if (!id || !Number.isFinite(meters)) throw new Error('Uso: atlas:data contour <id> <metros>');
  const dir = join(OUT, 'regions', id);
  const meta = JSON.parse(readFileSync(join(dir, 'meta.json'), 'utf8')) as RegionMeta;
  const projection = makeProjection(meta.projection);
  const { data, info } = await sharp(join(dir, meta.files.height)).toColourspace('grey16').raw({ depth: 'ushort' }).toBuffer({ resolveWithObject: true });
  const raw = new Uint16Array(data.buffer, data.byteOffset, data.byteLength / 2);
  const hw = info.width;
  const hh = info.height;
  const { min, max } = meta.heightEncoding;
  const values = new Float64Array(hw * hh);
  for (let i = 0; i < hw * hh; i++) values[i] = min + (raw[i * info.channels] / 65535) * (max - min);
  // Suavizado (caja 9×9 a mitad de resolución) para que el borde no siga cada barranco.
  const smooth = new Float64Array(hw * hh);
  const r = 4;
  for (let y = 0; y < hh; y++) {
    for (let x = 0; x < hw; x++) {
      let acc = 0;
      let n = 0;
      for (let dy = -r; dy <= r; dy++) {
        const yy = Math.max(0, Math.min(hh - 1, y + dy));
        for (let dx = -r; dx <= r; dx++) {
          acc += values[yy * hw + Math.max(0, Math.min(hw - 1, x + dx))];
          n++;
        }
      }
      smooth[y * hw + x] = acc / n;
    }
  }
  const [contour] = contours().size([hw, hh]).thresholds([meters])(Array.from(smooth));
  const scale = meta.width / hw;
  const minArea = (hw * hh) / 4000; // islas y huecos de menos de 1/4000 de la imagen fuera
  const polygons: Position[][][] = [];
  for (const poly of contour.coordinates) {
    if (ringArea(poly[0]) < minArea) continue;
    const rings = poly
      .filter((ring, k) => k === 0 || ringArea(ring) >= minArea)
      .map((ring) =>
        simplifyRing(ring, 1.6).map(([x, y]) => {
          const ll = projection.invert!([x * scale, y * scale]);
          if (!ll) throw new Error('Punto del contorno fuera de la proyección');
          return [ll[0], ll[1]] as Position;
        }),
      );
    polygons.push(rings);
  }
  if (!polygons.length) throw new Error(`No hay tierra por encima de ${meters} m en la región ${id}`);
  // En pantalla (y hacia abajo) el sentido de giro se invierte respecto a lon/lat: d3-geo leería el complemento.
  const fixed = polygons.map((rings) =>
    rings.map((ring, k) => {
      const f: Feature<MultiPolygon> = { type: 'Feature', properties: {}, geometry: { type: 'MultiPolygon', coordinates: [[ring]] } };
      const big = geoArea(f) > 2 * Math.PI;
      return (k === 0) === big ? [...ring].reverse() : ring;
    }),
  );
  const feature: Feature<MultiPolygon> = {
    type: 'Feature',
    properties: { region: id, meters, source: meta.sources[0] },
    geometry: roundCoords({ type: 'MultiPolygon', coordinates: fixed }, 3),
  };
  const file = join(dir, `contour-${meters}.geojson`);
  writeFileSync(file, JSON.stringify(feature));
  const km2 = (geoArea(feature) * 6371 ** 2).toFixed(0);
  console.log(`${file}: ${fixed.length} polígonos, ${fixed.reduce((s, p) => s + p.reduce((t, r) => t + r.length, 0), 0)} puntos, ≈${km2} km²`);
});
