/**
 * atlas-globe (fase 5): globo ortográfico de three.js con la textura del mundo (build-globe), que gira por keyframes,
 * y encima las capas vectoriales con d3-geo y la misma proyección: siluetas, rutas de círculo máximo que se trazan,
 * puntos con nombre y etiquetas.
 */
import type { FC } from 'react';
import { useMemo } from 'react';
import { AbsoluteFill } from 'remotion';
import { ThreeCanvas } from '@remotion/three';
import { geoDistance, geoInterpolate, geoOrthographic, geoPath } from 'd3-geo';
import type { GeoPermissibleObjects } from 'd3-geo';
import type { Feature } from 'geojson';
import { drift, ease, progress, reveal } from '../anim';
import { useAtlasTime, useScene, useTheme } from '../context';
import { fonts } from '../fonts';
import { useJsonFiles } from '../geo/useData';
import { useTexture } from '../geo/useTexture';
import type { LonLat } from '../schema';
import { accentOn, themes } from '../theme';
import { sec } from '../time';
import { Header, useSceneOf } from './text';

const W = 1920;
const H = 1080;
const BASE_R = 430;
const MOVE = 1.8;
const DEG = Math.PI / 180;

const halo = (bg: string, w = 7) => ({ stroke: bg, strokeWidth: w, paintOrder: 'stroke' as const, strokeLinejoin: 'round' as const });

export const GlobeScene: FC = () => {
  const scene = useSceneOf('atlas-globe');
  const { start, end } = useScene();
  const { name, tokens } = useTheme();
  const time = useAtlasTime();
  const texture = useTexture(`atlas-data/globe/earth-${name}.jpg`);
  const shapeFiles = (scene.shapes ?? []).map((s) => s.source);
  const shapes = useJsonFiles<Feature>(shapeFiles);

  const keys = useMemo(() => scene.camera.map((c) => ({ t: sec(c.at), center: c.center, zoom: c.zoom })), [scene]);
  let center: LonLat = keys[0].center;
  let zoom = keys[0].zoom;
  for (let i = 1; i < keys.length; i++) {
    if (time <= keys[i].t) break;
    const p = ease(Math.min(1, (time - keys[i].t) / MOVE));
    center = geoInterpolate(center, keys[i].center)(p) as LonLat;
    zoom = Math.exp(Math.log(zoom) + (Math.log(keys[i].zoom) - Math.log(zoom)) * p);
  }
  // deriva: el globo nunca queda quieto (gira despacio y se acerca un 3 %)
  center = [center[0] + 0.25 * (time - start), center[1]];
  const R = BASE_R * zoom * drift(time - start, end - start, 0.03);
  const projection = geoOrthographic()
    .rotate([-center[0], -center[1]])
    .scale(R)
    .translate([W / 2, H / 2])
    .clipAngle(90)
    .precision(0.3);
  const path = geoPath(projection);
  const visible = (ll: LonLat) => geoDistance(ll, center) < Math.PI / 2 - 0.01;
  const P = (ll: LonLat) => projection(ll) ?? [-999, -999];
  const bg = tokens.bg;
  const rim = name === 'night' ? 'rgba(237,230,211,0.55)' : 'rgba(42,33,24,0.55)';

  return (
    <AbsoluteFill>
      {texture ? (
        <ThreeCanvas width={W} height={H} orthographic camera={{ position: [0, 0, 2000], near: 0.1, far: 10000, zoom: 1 }} style={{ position: 'absolute' }}>
          {/* lon 0 de la textura queda de cara a la cámara con rotación y = −90°; luego se gira a la longitud y se inclina a la latitud */}
          <group rotation={[center[1] * DEG, 0, 0]}>
            <mesh rotation={[0, (-90 - center[0]) * DEG, 0]} scale={R}>
              <sphereGeometry args={[1, 160, 96]} />
              <meshBasicMaterial map={texture} toneMapped={false} />
            </mesh>
          </group>
        </ThreeCanvas>
      ) : null}
      <svg width={W} height={H} style={{ position: 'absolute', inset: 0 }}>
        <circle cx={W / 2} cy={H / 2} r={R} fill="none" stroke={rim} strokeWidth={2} />
        {shapes
          ? (scene.shapes ?? []).map((shape, i) => {
              const p = progress(time, sec(shape.at), 0.9);
              if (p <= 0) return null;
              const d = path(shapes[i] as GeoPermissibleObjects) ?? '';
              // la región destacada es roja también de noche (el «peligro» ámbar es para líneas y textos)
              const red = themes.paper.accents.danger;
              const stroke = shape.stroke && shape.stroke !== 'danger' ? accentOn(name, shape.stroke) : red;
              return (
                <g key={shape.id} opacity={p}>
                  {shape.fill !== false ? <path d={d} fill={stroke === red ? red : stroke} fillOpacity={name === 'night' ? 0.42 : 0.32} /> : null}
                  <path d={d} fill="none" stroke={stroke} strokeWidth={1.8} strokeOpacity={0.8} />
                </g>
              );
            })
          : null}
        {(scene.routes ?? []).map((route) => {
          const at = sec(route.at);
          const p = progress(time, at, route.drawSeconds, (x) => x);
          if (p <= 0) return null;
          // la ruta como serie de puntos por círculo máximo; sólo la parte visible, y hasta donde va dibujada
          const pts: LonLat[] = [];
          for (let i = 1; i < route.path.length; i++) {
            const inter = geoInterpolate(route.path[i - 1], route.path[i]);
            for (let j = i === 1 ? 0 : 1; j <= 48; j++) pts.push(inter(j / 48) as LonLat);
          }
          const upto = Math.max(1, Math.round(ease(p) * (pts.length - 1)));
          let d = '';
          let pen = false;
          for (let k = 0; k <= upto; k++) {
            if (!visible(pts[k])) {
              pen = false;
              continue;
            }
            const [x, y] = P(pts[k]);
            d += `${pen ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`;
            pen = true;
          }
          const color = accentOn(name, route.accent);
          return (
            <path key={route.id} d={d} fill="none" stroke={color} strokeWidth={3} strokeLinecap="round" strokeLinejoin="round"
                  strokeDasharray={route.style === 'dashed' ? '11 8' : route.style === 'dotted' ? '1 8' : undefined} />
          );
        })}
        {(() => {
          const taken: [number, number, number, number][] = [];
          const free = (b: [number, number, number, number]) => !taken.some((t) => b[0] < t[2] && b[2] > t[0] && b[1] < t[3] && b[3] > t[1]);
          return (scene.points ?? []).map((pt, i) => {
            if (!visible(pt.pos)) return null;
            const r = reveal(time, sec(pt.at), 0.4);
            const [x, y] = P(pt.pos);
            taken.push([x - 8, y - 8, x + 8, y + 8]);
            const w = pt.name.length * 15 + 8;
            const tries: [number, number, 'start' | 'end' | 'middle'][] = [
              [x + 14, y + 9, 'start'], [x - 14, y + 9, 'end'], [x, y - 16, 'middle'], [x, y + 34, 'middle'],
            ];
            const box = ([tx, ty, anchor]: [number, number, string]): [number, number, number, number] => {
              const l = anchor === 'start' ? tx : anchor === 'end' ? tx - w : tx - w / 2;
              return [l, ty - 24, l + w, ty + 6];
            };
            const spot = tries.find((t) => free(box(t))) ?? tries[0];
            taken.push(box(spot));
            if (r.opacity <= 0) return null;
            const ink = name === 'night' ? themes.night.ink : tokens.ink;
            return (
              <g key={`pt${i}`} opacity={r.opacity}>
                <circle cx={x} cy={y} r={5} fill={name === 'night' ? '#F4EFE2' : tokens.ink} stroke={bg} strokeWidth={2} />
                <text x={spot[0]} y={spot[1]} textAnchor={spot[2]} fontFamily={fonts.serif} fontWeight={600} fontSize={27} fill={ink} {...halo(bg)}>
                  {pt.name}
                </text>
              </g>
            );
          });
        })()}
      </svg>
      {(scene.labels ?? []).map((label, i) => {
        if (!visible(label.pos)) return null;
        const r = reveal(time, sec(label.at), 0.6);
        if (r.opacity <= 0) return null;
        const [x, y] = P(label.pos);
        return (
          <div key={`lb${i}`} style={{ position: 'absolute', left: x - 400, width: 800, top: y - 16, textAlign: 'center', ...r.style }}>
            <span
              style={{
                fontFamily: label.style === 'mono' ? fonts.mono : fonts.serif,
                fontWeight: 600,
                fontSize: 23,
                letterSpacing: '0.2em',
                textTransform: 'uppercase',
                color: label.accent ? accentOn(name, label.accent) : tokens.inkSoft,
                WebkitTextStroke: `7px ${bg}`,
                paintOrder: 'stroke fill',
              }}
            >
              {label.text}
            </span>
          </div>
        );
      })}
      <Header top={92} />
    </AbsoluteFill>
  );
};
