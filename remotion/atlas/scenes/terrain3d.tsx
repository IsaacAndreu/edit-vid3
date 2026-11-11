/**
 * atlas-terrain-3d (fase 5): bloque de terreno con datos reales (build-terrain) extruido con exageración vertical,
 * paredes laterales y filetes de tinta; cámara que se inclina de cenital a oblicua por keyframes; zona por encima de
 * un umbral teñida en rojo; rótulos, eje en km, línea de crucero y avión con su línea de altitud, proyectados con la
 * misma cámara en una capa 2D.
 */
import type { FC } from 'react';
import { useMemo } from 'react';
import { AbsoluteFill } from 'remotion';
import { ThreeCanvas } from '@remotion/three';
import { useThree } from '@react-three/fiber';
import {
  BufferAttribute,
  BufferGeometry,
  Color,
  DoubleSide,
  Line,
  LineBasicMaterial,
  PerspectiveCamera,
  ShaderMaterial,
  Vector3,
  type Texture,
} from 'three';
import { ease, progress, reveal } from '../anim';
import { useAtlasTime, useScene, useTheme } from '../context';
import { fonts } from '../fonts';
import { useJsonFiles } from '../geo/useData';
import { useTexture } from '../geo/useTexture';
import { PLANE_SIDE_PATH, PLANE_TOP_PATH } from '../icons';
import type { AtlasScene, LonLat } from '../schema';
import { accentOn, themes } from '../theme';
import { sec } from '../time';
import { Header, useSceneOf } from './text';
import { clockToS, flightClock, FlightHud, flownUntil, sampleAt, videoTimeOf, type FlightData } from '../flight';

type Terrain3d = Extract<AtlasScene, { type: 'atlas-terrain-3d' }>;
interface TerrainMeta {
  bbox: [number, number, number, number];
  kmLon: number;
  kmLat: number;
  widthKm: number;
  depthKm: number;
  cols: number;
  rows: number;
  maxM: number;
}

const W = 1920;
const H = 1080;
const FOV = 28;
const MOVE = 2.2;
const DEG = Math.PI / 180;

interface Cam {
  tilt: number;
  yaw: number;
  distance: number;
  target: LonLat | null;
  targetKm: number;
}

const cameraAt = (keys: (Cam & { t: number })[], t: number, center: LonLat): Cam => {
  // sin objetivo = el centro del bloque: así un keyframe con objetivo se interpola desde ahí, sin salto
  let cam: Cam = { ...keys[0], target: keys[0].target ?? center };
  for (let i = 1; i < keys.length; i++) {
    if (t <= keys[i].t) break;
    const p = ease(Math.min(1, (t - keys[i].t) / MOVE));
    const b = keys[i];
    const lerp = (x: number, y: number) => x + (y - x) * p;
    const ta = cam.target ?? center;
    const tb = b.target ?? center;
    cam = {
      tilt: lerp(cam.tilt, b.tilt),
      yaw: lerp(cam.yaw, b.yaw),
      distance: Math.exp(lerp(Math.log(cam.distance), Math.log(b.distance))),
      target: ta && tb ? [lerp(ta[0], tb[0]), lerp(ta[1], tb[1])] : null,
      targetKm: lerp(cam.targetKm, b.targetKm),
    };
  }
  return cam;
};

const terrainShader = (map: Texture, side: string) =>
  new ShaderMaterial({
    uniforms: {
      map: { value: map },
      thr: { value: -1 },
      reveal: { value: 0 },
      red: { value: new Color('#C8402F') },
      line: { value: new Color('#8E2A1E') },
      band: { value: 0.03 },
    },
    vertexShader: `
      varying vec2 vUv;
      varying float vElev;
      void main() {
        vUv = uv;
        vElev = position.y;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }`,
    fragmentShader: `
      uniform sampler2D map;
      uniform float thr;
      uniform float reveal;
      uniform vec3 red;
      uniform vec3 line;
      uniform float band;
      varying vec2 vUv;
      varying float vElev;
      void main() {
        vec3 col = texture2D(map, vUv).rgb;
        if (thr >= 0.0 && reveal > 0.0) {
          float above = step(thr, vElev);
          col = mix(col, red, above * 0.68 * reveal);
          float edge = 1.0 - smoothstep(0.0, band, abs(vElev - thr));
          col = mix(col, line, edge * reveal);
        }
        gl_FragColor = vec4(col, 1.0);
        #include <colorspace_fragment>
      }`,
    side: DoubleSide,
    name: `terrain-${side}`,
  });

/** Pone la cámara de three igual que la calculada (la capa 2D proyecta con la misma). */
const Rig: FC<{ position: Vector3; target: Vector3; near: number; far: number }> = ({ position, target, near, far }) => {
  const camera = useThree((s) => s.camera) as PerspectiveCamera;
  camera.fov = FOV;
  camera.near = near;
  camera.far = far;
  camera.position.copy(position);
  camera.lookAt(target);
  camera.updateProjectionMatrix();
  camera.updateMatrixWorld();
  return null;
};

export const Terrain3dScene: FC = () => {
  const scene = useSceneOf('atlas-terrain-3d');
  const { previous } = useScene();
  const { name, tokens } = useTheme();
  const time = useAtlasTime();
  const dir = `atlas-data/terrain/${scene.terrain}`;
  const data = useJsonFiles<unknown>([`${dir}/meta.json`, `${dir}/heights.json`, ...(scene.flight ? [scene.flight.data] : [])]);
  const texture = useTexture(`${dir}/tex-${name}.jpg`);
  const meta = data?.[0] as TerrainMeta | undefined;
  const heights = data?.[1] as number[] | undefined;
  const flightData = scene.flight ? (data?.[2] as FlightData | undefined) : undefined;

  const built = useMemo(() => {
    if (!meta || !heights || !texture) return null;
    const { cols, rows, widthKm, depthKm } = meta;
    const pos = new Float32Array(cols * rows * 3);
    const uv = new Float32Array(cols * rows * 2);
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const i = r * cols + c;
        pos[i * 3] = (c / (cols - 1) - 0.5) * widthKm;
        pos[i * 3 + 1] = heights[i] / 1000;
        pos[i * 3 + 2] = (r / (rows - 1) - 0.5) * depthKm;
        uv[i * 2] = c / (cols - 1);
        uv[i * 2 + 1] = 1 - r / (rows - 1);
      }
    }
    const idx: number[] = [];
    for (let r = 0; r < rows - 1; r++) {
      for (let c = 0; c < cols - 1; c++) {
        const a = r * cols + c;
        idx.push(a, a + cols, a + 1, a + 1, a + cols, a + cols + 1);
      }
    }
    const top = new BufferGeometry();
    top.setAttribute('position', new BufferAttribute(pos, 3));
    top.setAttribute('uv', new BufferAttribute(uv, 2));
    top.setIndex(idx);
    // paredes: de cada borde hasta el nivel 0
    const edge = (cells: number[]) => cells.map((i) => [pos[i * 3], pos[i * 3 + 1], pos[i * 3 + 2]] as [number, number, number]);
    const north = edge(Array.from({ length: cols }, (_, c) => c));
    const south = edge(Array.from({ length: cols }, (_, c) => (rows - 1) * cols + c));
    const west = edge(Array.from({ length: rows }, (_, r) => r * cols));
    const east = edge(Array.from({ length: rows }, (_, r) => r * cols + cols - 1));
    const wall = (pts: [number, number, number][]) => {
      const p = new Float32Array(pts.length * 6);
      pts.forEach(([x, y, z], k) => {
        p.set([x, y, z, x, 0, z], k * 6);
      });
      const ix: number[] = [];
      for (let k = 0; k < pts.length - 1; k++) ix.push(k * 2, k * 2 + 1, k * 2 + 2, k * 2 + 2, k * 2 + 1, k * 2 + 3);
      const g = new BufferGeometry();
      g.setAttribute('position', new BufferAttribute(p, 3));
      g.setIndex(ix);
      return g;
    };
    const walls = [north, south, west, east].map(wall);
    // filetes: borde superior, base y aristas verticales
    const loop = [...north, ...east.slice(1), ...[...south].reverse().slice(1), ...[...west].reverse().slice(1)];
    const lineGeom = (pts: [number, number, number][]) => new BufferGeometry().setFromPoints(pts.map((p) => new Vector3(...p)));
    const hw = widthKm / 2;
    const hd = depthKm / 2;
    const outline = [
      lineGeom(loop),
      lineGeom([[-hw, 0, -hd], [hw, 0, -hd], [hw, 0, hd], [-hw, 0, hd], [-hw, 0, -hd]]),
      ...[north[0], north[cols - 1], south[0], south[cols - 1]].map(([x, y, z]) => lineGeom([[x, 0, z], [x, y, z]])),
    ];
    return { top, walls, outline, material: terrainShader(texture, name) };
  }, [meta, heights, texture, name]);

  if (!meta || !heights || !built) return null;

  const { widthKm, depthKm, bbox, kmLon, kmLat, cols, rows } = meta;
  const lonC = (bbox[0] + bbox[2]) / 2;
  const latC = (bbox[1] + bbox[3]) / 2;
  const local = (ll: LonLat): [number, number] => [(ll[0] - lonC) * kmLon, -(ll[1] - latC) * kmLat];
  const groundKm = (ll: LonLat) => {
    const c = ((ll[0] - bbox[0]) / (bbox[2] - bbox[0])) * (cols - 1);
    const r = ((bbox[3] - ll[1]) / (bbox[3] - bbox[1])) * (rows - 1);
    const c0 = Math.max(0, Math.min(cols - 2, Math.floor(c)));
    const r0 = Math.max(0, Math.min(rows - 2, Math.floor(r)));
    const tc = c - c0;
    const tr = r - r0;
    const h = (rr: number, cc: number) => heights[rr * cols + cc];
    return ((h(r0, c0) * (1 - tc) + h(r0, c0 + 1) * tc) * (1 - tr) + (h(r0 + 1, c0) * (1 - tc) + h(r0 + 1, c0 + 1) * tc) * tr) / 1000;
  };

  const extrude = scene.extrude ? progress(time, sec(scene.extrude.at), scene.extrude.seconds) : 1;
  const yScale = scene.exaggeration * Math.max(0.002, extrude);
  const keys = scene.camera.map((c) => ({
    t: sec(c.at),
    tilt: c.tilt,
    yaw: c.yaw,
    distance: c.distance,
    target: c.target ?? null,
    targetKm: c.targetKm ?? 0,
  }));
  const cam = cameraAt(keys, time, [lonC, latC]);
  // deriva: un giro muy lento para que el bloque nunca esté quieto. Una escena 'continuous' sobre el mismo bloque
  // sigue la deriva de la anterior (si empezara de cero, la cámara saltaría en el cambio de escena).
  const chained = scene.enter === 'continuous' && previous?.type === 'atlas-terrain-3d' && previous.terrain === scene.terrain;
  const driftFrom = chained ? sec(previous.camera[0].at) : keys[0].t;
  const yaw = cam.yaw + 0.6 * (time - driftFrom);
  const S = Math.max(widthKm, depthKm);
  const [tx, tz] = cam.target ? local(cam.target) : [0, 0];
  const target = new Vector3(tx, cam.targetKm * yScale, tz);
  const d = cam.distance * S;
  const position = new Vector3(
    tx + d * Math.cos(cam.tilt * DEG) * Math.sin(yaw * DEG),
    target.y + d * Math.sin(cam.tilt * DEG),
    tz + d * Math.cos(cam.tilt * DEG) * Math.cos(yaw * DEG),
  );
  const near = d * 0.02;
  const far = d * 20;
  const projCam = new PerspectiveCamera(FOV, W / H, near, far);
  projCam.position.copy(position);
  projCam.lookAt(target);
  projCam.updateProjectionMatrix();
  projCam.updateMatrixWorld();
  const project = (x: number, yKm: number, z: number) => {
    const v = new Vector3(x, yKm * yScale, z).project(projCam);
    return [((v.x + 1) / 2) * W, ((1 - v.y) / 2) * H, v.z] as const;
  };

  const th = scene.threshold;
  const thP = th ? progress(time, sec(th.at), 0.9) : 0;
  built.material.uniforms.thr.value = th ? th.m / 1000 : -1;
  built.material.uniforms.reveal.value = thP;
  built.material.uniforms.band.value = 0.045 * (S / 3000) * 30 / scene.exaggeration;
  const sideColor = name === 'night' ? '#5B6F7D' : '#D6C7A6';
  const lineColor = name === 'night' ? '#1A2632' : tokens.ink;
  const bg = tokens.bg;

  return (
    <AbsoluteFill>
      <ThreeCanvas width={W} height={H} camera={{ fov: FOV }} style={{ position: 'absolute' }}>
        <Rig position={position} target={target} near={near} far={far} />
        <group scale={[1, yScale, 1]}>
          <mesh geometry={built.top} material={built.material} />
          {built.walls.map((g, i) => (
            <mesh key={i} geometry={g}>
              <meshBasicMaterial color={sideColor} side={DoubleSide} toneMapped={false} />
            </mesh>
          ))}
          {built.outline.map((g, i) => (
            <primitive key={`l${i}`} object={new Line(g, new LineBasicMaterial({ color: new Color(lineColor) }))} />
          ))}
        </group>
      </ThreeCanvas>
      <svg width={W} height={H} style={{ position: 'absolute', inset: 0 }}>
        {scene.cruise
          ? (() => {
              const c = scene.cruise;
              const p = progress(time, sec(c.at), 0.8);
              const [x1, y1] = project(-S * 1.5, c.km, 0);
              const [x2, y2] = project(S * 1.5, c.km, 0);
              const color = accentOn(name, c.accent ?? 'amber');
              return <line x1={x1} y1={y1} x2={x1 + (x2 - x1) * p} y2={y1 + (y2 - y1) * p} stroke={color} strokeWidth={2.5} />;
            })()
          : null}
        {scene.axis
          ? (() => {
              const a = scene.axis;
              const p = progress(time, sec(a.at), 0.6);
              const ticks = Array.from({ length: Math.floor(a.maxKm / a.stepKm) + 1 }, (_, i) => i * a.stepKm);
              const ax = widthKm / 2 + S * 0.05;
              const [bx, by] = project(ax, 0, depthKm / 2);
              const [tx2, ty2] = project(ax, a.maxKm, depthKm / 2);
              return (
                <g opacity={p}>
                  <line x1={bx} y1={by} x2={tx2} y2={ty2} stroke={tokens.inkSoft} strokeWidth={2} />
                  {ticks.map((k) => {
                    const [x, y] = project(ax, k, depthKm / 2);
                    return (
                      <g key={k}>
                        <line x1={x} y1={y} x2={x + 12} y2={y} stroke={tokens.inkSoft} strokeWidth={2} />
                        <text x={x + 20} y={y + 7} fontFamily={fonts.mono} fontSize={21} letterSpacing={3} fill={tokens.inkSoft}>{`${k} KM`}</text>
                      </g>
                    );
                  })}
                </g>
              );
            })()
          : null}
        {scene.plane
          ? (() => {
              const pl = scene.plane;
              const p = progress(time, sec(pl.at), pl.seconds, (x) => x);
              const r = progress(time, sec(pl.at) - 0.4, 0.4);
              if (r <= 0) return null;
              const ll: LonLat = [pl.from[0] + (pl.to[0] - pl.from[0]) * p, pl.from[1] + (pl.to[1] - pl.from[1]) * p];
              const [lx, lz] = local(ll);
              const [x, y] = project(lx, pl.km, lz);
              const [gx, gy] = project(lx, groundKm(ll), lz);
              const [ax0] = project(...([local(pl.from)[0], pl.km, local(pl.from)[1]] as [number, number, number]));
              const [ax1] = project(...([local(pl.to)[0], pl.km, local(pl.to)[1]] as [number, number, number]));
              const flip = ax1 < ax0;
              const color = accentOn(name, pl.accent ?? 'danger');
              const [sx, sy] = project(local(pl.from)[0], pl.km, local(pl.from)[1]);
              return (
                <g opacity={r}>
                  {pl.trail ? <line x1={sx} y1={sy} x2={x} y2={y} stroke={tokens.inkSoft} strokeWidth={2} strokeDasharray="7 7" /> : null}
                  {pl.dropLine !== false ? <line x1={x} y1={y + 8} x2={gx} y2={gy} stroke={color} strokeWidth={2.5} strokeDasharray="5 5" /> : null}
                  <g transform={`translate(${x} ${y}) scale(${flip ? -1 : 1} 1) translate(-40 -18) scale(0.8)`}>
                    <path d={PLANE_SIDE_PATH} fill="#F4EFE2" stroke={themes.paper.ink} strokeWidth={2} strokeLinejoin="round" />
                  </g>
                </g>
              );
            })()
          : null}
        {scene.flight && flightData
          ? (() => {
              const fl = scene.flight;
              const now = flightClock(fl, time);
              const from = clockToS(fl.from);
              const flown = flownUntil(flightData, from, now);
              const KM = 0.0003048;
              const air = flown.map((q) => {
                const [lx, lz] = local([q.lon, q.lat]);
                return project(lx, Math.max(0, q.alt) * KM, lz);
              });
              const ground = flown.map((q) => {
                const [lx, lz] = local([q.lon, q.lat]);
                return project(lx, groundKm([q.lon, q.lat]), lz);
              });
              const d = (pts: readonly (readonly [number, number, number])[]) => pts.map((q, i) => `${i ? 'L' : 'M'}${q[0].toFixed(1)},${q[1].toFixed(1)}`).join('');
              const color = accentOn(name, fl.accent ?? 'danger');
              const appear = progress(time, sec(fl.at) - 0.6, 0.6);
              const tip = air[air.length - 1];
              const next = sampleAt(flightData, now + 2);
              const [nx, nz] = local([next.lon, next.lat]);
              const ahead = project(nx, Math.max(0, next.alt) * KM, nz);
              const angle = (Math.atan2(ahead[1] - tip[1], ahead[0] - tip[0]) * 180) / Math.PI;
              return (
                <g opacity={appear}>
                  <path d={d(ground)} fill="none" stroke={tokens.ink} strokeOpacity={0.45} strokeWidth={2.5} strokeDasharray="6 7" />
                  {fl.dropLines !== false
                    ? air.map((q, i) =>
                        i % 8 === 0 ? <line key={`dl${i}`} x1={q[0]} y1={q[1]} x2={ground[i][0]} y2={ground[i][1]} stroke={color} strokeOpacity={0.35} strokeWidth={1.5} /> : null,
                      )
                    : null}
                  <path d={d(air)} fill="none" stroke={bg} strokeOpacity={0.8} strokeWidth={9} strokeLinecap="round" strokeLinejoin="round" />
                  <path d={d(air)} fill="none" stroke={color} strokeWidth={4.5} strokeLinecap="round" strokeLinejoin="round" />
                  <line x1={tip[0]} y1={tip[1]} x2={ground[ground.length - 1][0]} y2={ground[ground.length - 1][1]} stroke={color} strokeWidth={2.5} strokeDasharray="5 5" />
                  {(fl.marks ?? []).map((m, i) => {
                    const r = reveal(time, videoTimeOf(fl, m.clock), 0.5);
                    if (r.opacity <= 0) return null;
                    const q = sampleAt(flightData, clockToS(m.clock));
                    const [lx, lz] = local([q.lon, q.lat]);
                    const [x, y] = project(lx, Math.max(0, q.alt) * KM, lz);
                    const mc = accentOn(name, m.accent ?? 'ink');
                    return (
                      <g key={`m${i}`} opacity={r.opacity}>
                        <circle cx={x} cy={y} r={9} fill={themes.paper.card} stroke={mc} strokeWidth={3.5} />
                        <text x={x + 26} y={y - 8} fontFamily={fonts.serif} fontWeight={600} fontSize={30} fill={mc} stroke={bg} strokeWidth={7} paintOrder="stroke">
                          {m.label}
                        </text>
                        <text x={x + 26} y={y + 22} fontFamily={fonts.mono} fontSize={20} letterSpacing={2} fill={tokens.inkSoft} stroke={bg} strokeWidth={6} paintOrder="stroke">
                          {m.sub ?? m.clock}
                        </text>
                      </g>
                    );
                  })}
                  <g transform={`translate(${tip[0]} ${tip[1]}) rotate(${angle}) translate(-26 -26) scale(0.52)`}>
                    <path d={PLANE_TOP_PATH} fill="#F4EFE2" stroke={themes.paper.ink} strokeWidth={5} strokeLinejoin="round" />
                  </g>
                </g>
              );
            })()
          : null}
        {(scene.labels ?? []).map((label, i) => {
          if (label.style === 'range') return null;
          const r = progress(time, sec(label.at), 0.5);
          if (r <= 0) return null;
          const [lx, lz] = local(label.pos);
          const [x, y] = project(lx, groundKm(label.pos), lz);
          return (
            <g key={`pk${i}`} opacity={r}>
              <circle cx={x} cy={y} r={5} fill={name === 'night' ? '#F4EFE2' : tokens.ink} stroke={bg} strokeWidth={2} />
              {label.style === 'peak' ? <line x1={x} y1={y} x2={x + 52} y2={y + 46} stroke={tokens.ink} strokeWidth={2} /> : null}
            </g>
          );
        })}
      </svg>
      {scene.cruise
        ? (() => {
            const c = scene.cruise;
            const [x1, y1] = project(-widthKm * 0.36, c.km, 0);
            return (
              <Tag x={x1} y={y1 - 52} color={accentOn(name, c.accent ?? 'amber')} bg={bg} opacity={progress(time, sec(c.at) + 0.4, 0.5)} mono size={26}>
                {c.label}
              </Tag>
            );
          })()
        : null}
      {(scene.labels ?? []).map((label, i) => {
        const r = reveal(time, sec(label.at), 0.5);
        if (r.opacity <= 0) return null;
        const [lx, lz] = local(label.pos);
        const [x, y] = project(lx, groundKm(label.pos), lz);
        const color = label.accent ? accentOn(name, label.accent) : label.style === 'range' ? tokens.accents.danger : tokens.ink;
        if (label.style === 'peak') {
          return (
            <div key={`lb${i}`} style={{ position: 'absolute', left: x + 56, top: y + 34, ...r.style }}>
              <span style={{ fontFamily: fonts.serif, fontWeight: 600, fontSize: 30, color, WebkitTextStroke: `7px ${bg}`, paintOrder: 'stroke fill' }}>
                {label.text}
              </span>
            </div>
          );
        }
        if (label.style === 'value') {
          // cifra junto a la cumbre: a la derecha del punto
          return (
            <div key={`lb${i}`} style={{ position: 'absolute', left: x + 44, top: y + 4, ...r.style, lineHeight: 1.05 }}>
              <Tag x={0} y={0} color={color} bg={bg} mono size={26} static>
                {label.text}
              </Tag>
              {label.sub ? (
                <Tag x={0} y={0} color={color} bg={bg} mono size={26} static>
                  {label.sub}
                </Tag>
              ) : null}
            </div>
          );
        }
        return (
          <div key={`lb${i}`} style={{ position: 'absolute', left: x - 400, width: 800, top: y - 50, textAlign: 'center', ...r.style }}>
            <Tag x={0} y={0} color={color} bg={bg} mono size={28} static>
              {label.text}
            </Tag>
            {label.sub ? (
              <Tag x={0} y={0} color={color} bg={bg} mono size={24} static>
                {label.sub}
              </Tag>
            ) : null}
          </div>
        );
      })}
      {th?.label && th.labelPos
        ? (() => {
            const [lx, lz] = local(th.labelPos);
            const [x, y] = project(lx, groundKm(th.labelPos), lz);
            return (
              <div style={{ position: 'absolute', left: x - 400, width: 800, top: y - 22, textAlign: 'center', opacity: progress(time, sec(th.at) + 0.5, 0.5) }}>
                <Tag x={0} y={0} color={name === 'night' ? '#F4EFE2' : '#FBF3E4'} bg={themes.paper.accents.danger} mono size={30} static>
                  {th.label}
                </Tag>
              </div>
            );
          })()
        : null}
      {scene.base
        ? (() => {
            const [x, y] = project(-widthKm / 2, 0, depthKm / 2);
            return (
              <Tag x={x + 10} y={y + 18} color={tokens.inkSoft} bg={bg} mono size={22} opacity={progress(time, sec(scene.base.at), 0.5)}>
                {scene.base.label}
              </Tag>
            );
          })()
        : null}
      {scene.flight?.hud && flightData ? (
        <FlightHud show={scene.flight.hud.show} point={sampleAt(flightData, flightClock(scene.flight, time))} theme={name} corner={scene.flight.hud.corner} labels={scene.flight.hud.labels} />
      ) : null}
      <Header top={92} />
    </AbsoluteFill>
  );
};

const Tag: FC<{
  x: number;
  y: number;
  color: string;
  bg: string;
  children: string;
  mono?: boolean;
  size?: number;
  opacity?: number;
  static?: boolean;
}> = ({ x, y, color, bg, children, mono, size = 24, opacity = 1, static: inFlow }) => (
  <div
    style={{
      ...(inFlow ? {} : { position: 'absolute' as const, left: x, top: y }),
      opacity,
      fontFamily: mono ? fonts.mono : fonts.serif,
      fontWeight: 600,
      fontSize: size,
      letterSpacing: '0.18em',
      textTransform: 'uppercase',
      color,
      whiteSpace: 'nowrap',
      WebkitTextStroke: `7px ${bg}`,
      paintOrder: 'stroke fill',
    }}
  >
    {children}
  </div>
);
