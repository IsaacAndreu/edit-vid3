/**
 * atlas-relief-map (fase 3): mapa de relieve sombreado ya proyectado (scripts/atlas-data/build-region.ts) con una
 * cámara por keyframes y capas vectoriales dibujadas con la misma proyección: siluetas (contornos de altura, países
 * movidos a escala real), rutas que se trazan, puntos, etiquetas y flechas. Todo el contenido llega del storyboard.
 */
import type { FC } from 'react';
import { useMemo } from 'react';
import { AbsoluteFill, Img, staticFile } from 'remotion';
import { geoBounds, geoCentroid, geoInterpolate, geoPath, geoRotation } from 'd3-geo';
import type { GeoPermissibleObjects, GeoProjection } from 'd3-geo';
import type { Feature, Geometry, Position } from 'geojson';
import { drift, ease, progress, reveal } from '../anim';
import { useAtlasTime, useScene, useTheme } from '../context';
import { fonts } from '../fonts';
import { makeProjection, type RegionMeta } from '../geo/projection';
import { useJsonFiles } from '../geo/useData';
import { PLANE_TOP_PATH } from '../icons';
import type { AtlasScene, LonLat } from '../schema';
import { accentOn, themes } from '../theme';
import { sec } from '../time';
import { Header, useSceneOf } from './text';

type Relief = Extract<AtlasScene, { type: 'atlas-relief-map' }>;
type Cam = { center: LonLat; zoom: number };

const W = 1920;
const H = 1080;
const MOVE = 1.8; // segundos de cada movimiento de cámara

/** Cámara en el instante t: cada keyframe empieza a moverse en su `at`; deriva lenta encima (§5). */
const cameraAt = (keys: { t: number; center: LonLat; zoom: number }[], t: number, start: number, end: number): Cam => {
  let cam: Cam = { center: keys[0].center, zoom: keys[0].zoom };
  for (let i = 1; i < keys.length; i++) {
    if (t <= keys[i].t) break;
    const p = ease(Math.min(1, (t - keys[i].t) / MOVE));
    const from = cam;
    const to = keys[i];
    // el centro se mueve por geodésica; el zoom en escala logarítmica (un zoom ×2 se siente igual a cualquier escala)
    cam = {
      center: geoInterpolate(from.center, to.center)(p) as LonLat,
      zoom: Math.exp(Math.log(from.zoom) + (Math.log(to.zoom) - Math.log(from.zoom)) * p),
    };
  }
  return { center: cam.center, zoom: cam.zoom * drift(t - start, end - start, 0.03) };
};

/** Mueve una geometría por la esfera para que su centroide caiga en `to`: conserva el tamaño real. */
const moveOnSphere = (geom: Geometry, from: LonLat, to: LonLat): Geometry => {
  const toOrigin = geoRotation([-from[0], -from[1]]);
  const toTarget = geoRotation([-to[0], -to[1]]).invert;
  const mapCoords = (c: unknown): unknown =>
    typeof (c as number[])[0] === 'number' ? toTarget(toOrigin(c as [number, number])) : (c as unknown[]).map(mapCoords);
  return { ...geom, coordinates: mapCoords((geom as { coordinates: unknown }).coordinates) } as Geometry;
};

/** Polilínea en pantalla parcialmente dibujada (0–1), con el punto y el rumbo de la punta. */
const partial = (pts: [number, number][], p: number) => {
  const lens = [0];
  for (let i = 1; i < pts.length; i++) lens.push(lens[i - 1] + Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]));
  const total = lens[lens.length - 1];
  const target = total * p;
  const out: [number, number][] = [pts[0]];
  let tip = pts[0];
  let angle = 0;
  for (let i = 1; i < pts.length; i++) {
    angle = Math.atan2(pts[i][1] - pts[i - 1][1], pts[i][0] - pts[i - 1][0]);
    if (lens[i] <= target) {
      out.push(pts[i]);
      tip = pts[i];
    } else {
      const f = (target - lens[i - 1]) / (lens[i] - lens[i - 1] || 1);
      tip = [pts[i - 1][0] + (pts[i][0] - pts[i - 1][0]) * f, pts[i - 1][1] + (pts[i][1] - pts[i - 1][1]) * f];
      out.push(tip);
      break;
    }
  }
  const mid = (() => {
    const half = total / 2;
    for (let i = 1; i < pts.length; i++) {
      if (lens[i] >= half) {
        const f = (half - lens[i - 1]) / (lens[i] - lens[i - 1] || 1);
        return [pts[i - 1][0] + (pts[i][0] - pts[i - 1][0]) * f, pts[i - 1][1] + (pts[i][1] - pts[i - 1][1]) * f] as [number, number];
      }
    }
    return pts[0];
  })();
  return { d: out.map((q, i) => `${i ? 'L' : 'M'}${q[0].toFixed(1)},${q[1].toFixed(1)}`).join(''), tip, angle, mid };
};

interface CellsData {
  cells: { lon: number; lat: number; m: number }[];
}

/** MSA de una celda: punto más alto en pies + margen, redondeado hacia arriba a 100 ft. */
export const cellMsa = (m: number, marginFt: number) => Math.ceil((Math.max(0, m) * 3.28084 + marginFt) / 100) * 100;

/**
 * Rejilla de 1°×1° sobre el mapa: cada celda con su altitud mínima segura (31¹ = 31.100 ft), las que pasan del
 * umbral en rojo (y rellenas si se pide), y una celda destacada con contorno rojo grueso.
 */
const Graticule: FC<{
  g: NonNullable<Relief['graticule']>;
  data: CellsData;
  P: (ll: LonLat) => [number, number];
  time: number;
  theme: 'paper' | 'night';
}> = ({ g, data, P, time, theme }) => {
  const appear = progress(time, sec(g.at), 0.8);
  if (appear <= 0) return null;
  const numbers = progress(time, sec(g.numbersAt ?? g.at), 0.6);
  const th = g.threshold;
  const thP = th ? progress(time, sec(th.at), 0.8) : 0;
  const ink = themes[theme].ink;
  const danger = themes[theme].accents.danger;
  const quad = (lon: number, lat: number) => {
    const pts: [number, number][] = [];
    for (let i = 0; i <= 4; i++) pts.push(P([lon + i / 4, lat]));
    for (let i = 0; i <= 4; i++) pts.push(P([lon + 1, lat + i / 4]));
    for (let i = 0; i <= 4; i++) pts.push(P([lon + 1 - i / 4, lat + 1]));
    for (let i = 0; i <= 4; i++) pts.push(P([lon, lat + 1 - i / 4]));
    return pts;
  };
  return (
    <g>
      {data.cells.map((c) => {
        const pts = quad(c.lon, c.lat);
        const xs = pts.map((p) => p[0]);
        if (Math.max(...xs) < -50 || Math.min(...xs) > 1970) return null;
        const msa = cellMsa(c.m, g.marginFt);
        const high = th ? msa >= th.value : false;
        const d = 'M' + pts.map((p) => `${p[0].toFixed(1)},${p[1].toFixed(1)}`).join('L') + 'Z';
        return (
          <path key={`${c.lon},${c.lat}`} d={d} fill={high && th?.fill ? danger : 'none'} fillOpacity={high && th?.fill ? 0.42 * thP : 0}
                stroke={ink} strokeOpacity={0.45 * appear} strokeWidth={1.3} />
        );
      })}
      {numbers > 0
        ? data.cells.map((c) => {
            const [x0, y0] = P([c.lon, c.lat]);
            const [x1, y1] = P([c.lon + 1, c.lat + 1]);
            const size = Math.min(Math.abs(x1 - x0), Math.abs(y1 - y0));
            if (size < 46) return null;
            const [cx, cy] = P([c.lon + 0.5, c.lat + 0.5]);
            if (cx < -40 || cx > 1960 || cy < -40 || cy > 1120) return null;
            const msa = cellMsa(c.m, g.marginFt);
            const high = th ? msa >= th.value && thP > 0.5 : false;
            const fs = Math.min(30, size * 0.36);
            return (
              <text key={`n${c.lon},${c.lat}`} x={cx} y={cy + fs * 0.36} textAnchor="middle" fontFamily={fonts.mono} fontWeight={600} fontSize={fs}
                    fill={high ? danger : ink} opacity={numbers}>
                {Math.floor(msa / 1000)}
                <tspan fontSize={fs * 0.6} dy={-fs * 0.42}>{Math.round((msa % 1000) / 100)}</tspan>
              </text>
            );
          })
        : null}
      {g.highlight
        ? (() => {
            const lon = Math.floor(g.highlight[0]);
            const lat = Math.floor(g.highlight[1]);
            const pts = quad(lon, lat);
            return <path d={'M' + pts.map((p) => `${p[0].toFixed(1)},${p[1].toFixed(1)}`).join('L') + 'Z'} fill="none" stroke={danger} strokeWidth={4} opacity={numbers} />;
          })()
        : null}
    </g>
  );
};

const haloStyle = (bg: string, w = 7) => ({ stroke: bg, strokeWidth: w, paintOrder: 'stroke' as const, strokeLinejoin: 'round' as const });

export const ReliefMapScene: FC = () => {
  const scene = useSceneOf('atlas-relief-map');
  const { previous, start, end } = useScene();
  const { name, tokens } = useTheme();
  const time = useAtlasTime();
  const regionDir = `atlas-data/regions/${scene.region}`;
  const shapeFiles = (scene.shapes ?? []).map((s) => s.source);
  const data = useJsonFiles<unknown>([`${regionDir}/meta.json`, ...shapeFiles, ...(scene.graticule ? [scene.graticule.cells] : [])]);

  const keys = useMemo(() => {
    const own = scene.camera.map((c) => ({ t: sec(c.at), center: c.center, zoom: c.zoom }));
    // 'continuous': la cámara arranca donde la dejó la escena anterior del mismo mapa
    if (scene.enter === 'continuous' && previous?.type === 'atlas-relief-map' && previous.region === scene.region) {
      const last = previous.camera[previous.camera.length - 1];
      return [{ t: start, center: last.center, zoom: last.zoom }, ...own.map((k) => ({ ...k, t: Math.max(k.t, start + 0.01) }))];
    }
    return own;
  }, [scene, previous, start]);

  if (!data) return null;
  const [metaJson, ...rest] = data;
  const shapeJson = rest.slice(0, shapeFiles.length);
  const cellsJson = scene.graticule ? (rest[shapeFiles.length] as CellsData) : null;
  const meta = metaJson as RegionMeta;
  const base = makeProjection(meta.projection);
  const cam = cameraAt(keys, time, start, end);
  const baseK = Math.max(W / meta.width, H / meta.height);
  const k = baseK * cam.zoom;
  let [cx, cy] = base(cam.center) ?? [meta.width / 2, meta.height / 2];
  // que la imagen cubra siempre el cuadro
  cx = Math.min(meta.width - W / 2 / k, Math.max(W / 2 / k, cx));
  cy = Math.min(meta.height - H / 2 / k, Math.max(H / 2 / k, cy));
  const tx = W / 2 - cx * k;
  const ty = H / 2 - cy * k;
  const projection: GeoProjection = makeProjection({
    ...meta.projection,
    scale: meta.projection.scale * k,
    translate: [meta.projection.translate[0] * k + tx, meta.projection.translate[1] * k + ty],
  });
  const path = geoPath(projection);
  const P = (ll: LonLat) => projection(ll) ?? [-999, -999];
  const bg = tokens.bg;
  const danger = tokens.accents.danger;

  return (
    <AbsoluteFill>
      <Img
        src={staticFile(`${regionDir}/${name === 'night' ? meta.files.reliefNight : meta.files.relief}`)}
        style={{ position: 'absolute', left: 0, top: 0, width: meta.width, height: meta.height, transformOrigin: '0 0', transform: `translate(${tx}px, ${ty}px) scale(${k})` }}
      />
      <svg width={W} height={H} style={{ position: 'absolute', inset: 0 }}>
        {(scene.shapes ?? []).map((shape, i) => {
          const feature = shapeJson[i] as Feature;
          const at = sec(shape.at);
          const p = progress(time, at, 0.9);
          if (p <= 0) return null;
          let geom = feature.geometry;
          if (shape.moveTo) {
            const from = geoCentroid(feature as GeoPermissibleObjects) as LonLat;
            const travel = ease(Math.min(1, Math.max(0, (time - at - 0.3) / 1.6)));
            geom = moveOnSphere(geom, from, geoInterpolate(from, shape.moveTo)(travel) as LonLat);
          }
          const d = path(geom as GeoPermissibleObjects) ?? '';
          const stroke = accentOn(name, shape.stroke ?? (shape.moveTo ? 'data' : 'danger'));
          return (
            <g key={shape.id}>
              {shape.fill !== false ? (
                <path
                  d={d}
                  fill={shape.moveTo ? '#E9E5DC' : themes[name].regionFill}
                  fillOpacity={(shape.moveTo ? 0.62 : 0.42) * p}
                />
              ) : null}
              <path
                d={d}
                fill="none"
                stroke={stroke}
                strokeWidth={2.5}
                strokeLinejoin="round"
                strokeDasharray={shape.moveTo ? '7 6' : undefined}
                opacity={p}
              />
            </g>
          );
        })}
        {scene.graticule && cellsJson ? <Graticule g={scene.graticule} data={cellsJson} P={P} time={time} theme={name} /> : null}
        {(scene.arrows ?? []).map((arrow, i) => {
          const p = progress(time, sec(arrow.at), 0.7);
          if (p <= 0) return null;
          const a = P(arrow.from);
          const b = P(arrow.to);
          const x = a[0] + (b[0] - a[0]) * p;
          const y = a[1] + (b[1] - a[1]) * p;
          const ang = Math.atan2(b[1] - a[1], b[0] - a[0]);
          const color = accentOn(name, arrow.accent);
          return (
            <g key={`arrow${i}`}>
              <line x1={a[0]} y1={a[1]} x2={x} y2={y} stroke={color} strokeWidth={4} strokeLinecap="round" />
              <path
                d={`M ${x} ${y} L ${x - 16 * Math.cos(ang - 0.45)} ${y - 16 * Math.sin(ang - 0.45)} M ${x} ${y} L ${x - 16 * Math.cos(ang + 0.45)} ${y - 16 * Math.sin(ang + 0.45)}`}
                stroke={color}
                strokeWidth={4}
                strokeLinecap="round"
                fill="none"
              />
            </g>
          );
        })}
        {(scene.routes ?? []).map((route) => {
          const at = sec(route.at);
          const p = progress(time, at, route.drawSeconds, (x) => x);
          if (p <= 0) return null;
          const pts: [number, number][] = [];
          for (let i = 0; i < route.path.length; i++) {
            if (i > 0 && route.greatCircle) {
              const inter = geoInterpolate(route.path[i - 1], route.path[i]);
              for (let j = 1; j <= 24; j++) pts.push(P(inter(j / 24) as LonLat));
            } else {
              pts.push(P(route.path[i]));
            }
          }
          const { d, tip, angle, mid } = partial(pts, ease(p));
          const color = accentOn(name, route.accent);
          return (
            <g key={route.id}>
              <path
                d={d}
                fill="none"
                stroke={color}
                strokeWidth={route.style === 'dotted' ? 3 : 3.5}
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeDasharray={route.style === 'dashed' ? '14 9' : route.style === 'dotted' ? '1 9' : undefined}
              />
              {route.icon === 'plane' && p < 1 ? (
                <g transform={`translate(${tip[0]} ${tip[1]}) rotate(${(angle * 180) / Math.PI}) translate(-22 -22) scale(0.44)`}>
                  <path d={PLANE_TOP_PATH} fill="#F4EFE2" stroke={tokens.ink} strokeWidth={5} />
                </g>
              ) : null}
              {route.label ? (
                <text
                  x={mid[0] + 12}
                  y={mid[1] - 12}
                  fontFamily={fonts.mono}
                  fontWeight={600}
                  fontSize={24}
                  letterSpacing={2}
                  fill={color}
                  opacity={progress(time, at + route.drawSeconds * 0.5, 0.4)}
                  {...haloStyle(bg)}
                >
                  {route.label}
                </text>
              ) : null}
            </g>
          );
        })}
        {(() => {
          // nombres sin pisarse: a la derecha, a la izquierda, arriba o abajo del punto, el primer sitio libre
          const taken: [number, number, number, number][] = [];
          const free = (b: [number, number, number, number]) =>
            !taken.some((t) => b[0] < t[2] && b[2] > t[0] && b[1] < t[3] && b[3] > t[1]);
          return (scene.points ?? []).map((pt, i) => {
            const at = sec(pt.at);
            const r = reveal(time, at, 0.4);
            const [x, y] = P(pt.pos);
            taken.push([x - 10, y - 10, x + 10, y + 10]);
            const w = pt.name.length * 15 + 8;
            const tries: [number, number, 'start' | 'end' | 'middle'][] = [
              [x + 16, y + 9, 'start'], [x - 16, y + 9, 'end'], [x, y - 18, 'middle'], [x, y + 36, 'middle'],
            ];
            const box = ([tx, ty, anchor]: [number, number, string]): [number, number, number, number] => {
              const l = anchor === 'start' ? tx : anchor === 'end' ? tx - w : tx - w / 2;
              return [l, ty - 24, l + w, ty + 6];
            };
            const spot = tries.find((t) => free(box(t))) ?? tries[0];
            taken.push(box(spot));
            if (r.opacity <= 0) return null;
            const color = pt.accent ? accentOn(name, pt.accent) : tokens.ink;
            return (
              <g key={`pt${i}`} opacity={r.opacity}>
                {pt.marker === 'airport' ? (
                  <g>
                    <circle cx={x} cy={y} r={11} fill={themes.paper.card} stroke={tokens.ink} strokeWidth={2.5} />
                    <path d={`M ${x - 5} ${y + 3} L ${x} ${y - 4} L ${x + 5} ${y + 3}`} fill="none" stroke={tokens.ink} strokeWidth={2.5} />
                  </g>
                ) : (
                  <circle cx={x} cy={y} r={pt.marker === 'event' ? 8 : 5.5} fill={color} stroke={bg} strokeWidth={2} />
                )}
                <text x={spot[0]} y={spot[1]} textAnchor={spot[2]} fontFamily={fonts.serif} fontWeight={600} fontSize={27} fill={color} {...haloStyle(bg)}>
                  {pt.name}
                </text>
                {pt.value ? (
                  <text x={spot[0]} y={spot[1] + 30} textAnchor={spot[2]} fontFamily={fonts.mono} fontWeight={600}
                        fontSize={21} letterSpacing={2} fill={color} {...haloStyle(bg)}>
                    {pt.value}
                  </text>
                ) : null}
              </g>
            );
          });
        })()}
      </svg>
      {/* textos de siluetas y etiquetas sueltas, en HTML para el espaciado de letras */}
      {(scene.shapes ?? []).map((shape, i) => {
        if (!shape.label && !shape.sub) return null;
        const feature = shapeJson[i] as Feature;
        const at = sec(shape.at);
        const r = reveal(time, at + 0.5, 0.6);
        if (r.opacity <= 0) return null;
        const color = accentOn(name, shape.stroke ?? (shape.moveTo ? 'data' : 'danger'));
        if (shape.moveTo) {
          // la silueta movida: el rótulo a su derecha, arriba
          const [[w0, s0], [e0, n0]] = geoBounds(feature as GeoPermissibleObjects);
          const from = geoCentroid(feature as GeoPermissibleObjects) as LonLat;
          const corner = moveOnSphere({ type: 'Point', coordinates: [e0, n0 - (n0 - s0) * 0.25] } as Geometry, from, shape.moveTo) as { coordinates: Position };
          const [x, y] = P(corner.coordinates as LonLat);
          void w0;
          return (
            <div key={`sl${i}`} style={{ position: 'absolute', left: x + 20, top: y - 20, ...r.style, textAlign: 'center' }}>
              {shape.label ? <Caption text={shape.label} color={color} bg={bg} size={26} /> : null}
              {shape.sub ? <Caption text={shape.sub} color={color} bg={bg} size={21} /> : null}
            </div>
          );
        }
        const [x, y] = P(geoCentroid(feature as GeoPermissibleObjects) as LonLat);
        const [[, south]] = geoBounds(feature as GeoPermissibleObjects);
        const [, ySouth] = P([geoCentroid(feature as GeoPermissibleObjects)[0], south]);
        return (
          <div key={`sl${i}`}>
            {shape.label ? (
              <div style={{ position: 'absolute', left: x - 400, width: 800, top: y - 22, textAlign: 'center', ...r.style }}>
                <RegionName text={shape.label} bg={bg} color={name === 'night' ? tokens.ink : '#F4EFE2'} outline={tokens.ink} />
              </div>
            ) : null}
            {shape.sub ? (
              <div style={{ position: 'absolute', left: x - 400, width: 800, top: Math.min(H - (scene.sourceNote ? 140 : 80), ySouth - 30), textAlign: 'center', ...reveal(time, at + 0.9, 0.6).style }}>
                <Caption text={shape.sub} color={color} bg={bg} size={23} mono />
              </div>
            ) : null}
          </div>
        );
      })}
      {(scene.labels ?? []).map((label, i) => {
        const r = reveal(time, sec(label.at), 0.6);
        if (r.opacity <= 0) return null;
        const [x, y] = P(label.pos);
        return (
          <div key={`lb${i}`} style={{ position: 'absolute', left: x - 400, width: 800, top: y - 16, textAlign: 'center', ...r.style }}>
            {label.style === 'region' ? (
              <Caption text={label.text} color={label.accent ? accentOn(name, label.accent) : tokens.inkSoft} bg={bg} size={24} spacing="0.3em" />
            ) : (
              <Caption text={label.text} color={accentOn(name, label.accent ?? 'data')} bg={bg} size={22} mono />
            )}
          </div>
        );
      })}
      <Header top={92} />
    </AbsoluteFill>
  );
};

const Caption: FC<{ text: string; color: string; bg: string; size: number; mono?: boolean; spacing?: string }> = ({
  text,
  color,
  bg,
  size,
  mono,
  spacing,
}) => (
  <div
    style={{
      fontFamily: mono ? fonts.mono : fonts.serif,
      fontWeight: mono ? 600 : 500,
      fontSize: size,
      letterSpacing: spacing ?? (mono ? '0.16em' : '0.1em'),
      textTransform: 'uppercase',
      color,
      whiteSpace: 'nowrap',
      WebkitTextStroke: `7px ${bg}`,
      paintOrder: 'stroke fill',
    }}
  >
    {text}
  </div>
);

/** Nombre de región grande sobre la silueta: versalitas muy espaciadas, claras con contorno de tinta. */
const RegionName: FC<{ text: string; bg: string; color: string; outline: string }> = ({ text, color, outline }) => (
  <div
    style={{
      fontFamily: fonts.serif,
      fontWeight: 600,
      fontSize: 27,
      letterSpacing: '0.32em',
      textTransform: 'uppercase',
      color,
      whiteSpace: 'nowrap',
      WebkitTextStroke: `3px ${outline}`,
      paintOrder: 'stroke fill',
    }}
  >
    {text}
  </div>
);
