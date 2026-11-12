/**
 * atlas-flight-cam: un vuelo real de cerca y a escala real. El avión (modelo genérico en código) se coloca en cada
 * fotograma con la posición, la altitud, el cabeceo, el alabeo y el rumbo del FDR sobre el bloque de terreno; la cámara
 * va por keyframes (detrás, al lado, desde el suelo, desde la cabina, girando) y pasa de una a otra en 1,6 s.
 *
 * Orientación: el FDR da rumbo magnético; para colocar el avión en el terreno (norte geográfico) se le suma la
 * diferencia mediana entre la trayectoria (posiciones) y ese rumbo en vuelo, calculada de los propios datos.
 * atlas-pfd: el PFD a pantalla grande con las frases del informe.
 */
import type { FC } from 'react';
import { useMemo } from 'react';
import { AbsoluteFill } from 'remotion';
import { ThreeCanvas } from '@remotion/three';
import { useThree } from '@react-three/fiber';
import { BackSide, Color, DoubleSide, Euler, PerspectiveCamera, Quaternion, ShaderMaterial, Vector3, type Group } from 'three';
import { ease, reveal } from '../anim';
import { useAtlasTime, useTheme } from '../context';
import { aircraftLength, buildAircraft, liveryOf, poseAircraft } from '../flight/aircraft3d';
import { clockToS, EngineAudio, flightClock, FlightHud, sampleAt, sToClock, trackAt, videoTimeOf, type FlightData, type FlightPoint } from '../flight';
import { Pfd } from '../flight/pfd';
import { fonts } from '../fonts';
import { useJsonFiles } from '../geo/useData';
import { useOptionalTexture, useTexture } from '../geo/useTexture';
import type { AtlasScene, LonLat } from '../schema';
import { accentOn, FLIGHT, type LiveryName } from '../theme';
import { sec } from '../time';
import { cornerStyle, Mono } from '../ui';
import { Header, useSceneOf } from './text';
import { buildTerrain, type TerrainMeta } from './terrain3d';

type FlightCam = Extract<AtlasScene, { type: 'atlas-flight-cam' }>;
type Key = FlightCam['camera'][number];

const W = 1920;
const H = 1080;
const MOVE = 1.6;
const DEG = Math.PI / 180;
const FT_KM = 0.0003048;

interface Pose {
  pos: Vector3;
  target: Vector3;
  up: Vector3;
  fov: number;
  inside: number; // 1 = cámara dentro de la cabina
}

/** Diferencia mediana (grados) entre la trayectoria y el rumbo magnético del FDR, solo en vuelo. */
const headingOffset = (data: FlightData): number => {
  const diffs: number[] = [];
  for (const p of data.points) {
    if (p.ground || p.hdg === null || p.gs < 80) continue;
    diffs.push((((trackAt(data, p.s) - p.hdg + 540) % 360) - 180));
  }
  diffs.sort((a, b) => a - b);
  return diffs.length ? diffs[diffs.length >> 1] : 0;
};

/** Cúpula de cielo centrada en la cámara: degradado por elevación, así el horizonte coincide con el del terreno. */
const skyMaterial = (top: string, horizon: string) =>
  new ShaderMaterial({
    uniforms: { top: { value: new Color(top) }, horizon: { value: new Color(horizon) } },
    vertexShader: `
      varying vec3 vDir;
      void main() {
        vDir = normalize(position);
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }`,
    fragmentShader: `
      uniform vec3 top;
      uniform vec3 horizon;
      varying vec3 vDir;
      void main() {
        gl_FragColor = vec4(mix(horizon, top, smoothstep(0.0, 0.22, vDir.y)), 1.0);
        #include <colorspace_fragment>
      }`,
    side: BackSide,
    depthWrite: false,
  });

const Rig: FC<{ pose: Pose; near: number }> = ({ pose, near }) => {
  const camera = useThree((s) => s.camera) as PerspectiveCamera;
  camera.fov = pose.fov;
  camera.near = near;
  camera.far = 400;
  camera.position.copy(pose.pos);
  camera.up.copy(pose.up);
  camera.lookAt(pose.target);
  camera.updateProjectionMatrix();
  camera.updateMatrixWorld();
  return null;
};

export const FlightCamScene: FC = () => {
  const scene = useSceneOf('atlas-flight-cam');
  const { name } = useTheme();
  const time = useAtlasTime();
  const dir = `atlas-data/terrain/${scene.terrain}`;
  const data = useJsonFiles<unknown>([`${dir}/meta.json`, `${dir}/heights.json`, scene.flight.data]);
  const texture = useTexture(`${dir}/tex-${name}.jpg`);
  const meta = data?.[0] as TerrainMeta | undefined;
  const heights = data?.[1] as number[] | undefined;
  const flight = data?.[2] as FlightData | undefined;
  const built = useMemo(() => (meta && heights && texture ? buildTerrain(meta, heights, texture, name) : null), [meta, heights, texture, name]);
  const custom = typeof scene.livery === 'object' ? scene.livery : null;
  const tailLogo = useOptionalTexture(custom?.tailLogo);
  const titlesLogo = useOptionalTexture(custom?.titlesLogo);
  const logosReady = (!custom?.tailLogo || tailLogo) && (!custom?.titlesLogo || titlesLogo);
  const plane = useMemo(
    () => buildAircraft(scene.model, { ...liveryOf(custom ?? (scene.livery as LiveryName | undefined)), tailLogo, titlesLogo }, scene.registration),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [scene.model, JSON.stringify(scene.livery), scene.registration, tailLogo, titlesLogo],
  );
  const skyMat = useMemo(() => skyMaterial(FLIGHT.sky[name].top, FLIGHT.sky[name].horizon), [name]);
  const offset = useMemo(() => (flight ? headingOffset(flight) : 0), [flight]);
  if (!meta || !heights || !built || !flight || !logosReady) return null;

  const { bbox, kmLon, kmLat, cols, rows } = meta;
  const lonC = (bbox[0] + bbox[2]) / 2;
  const latC = (bbox[1] + bbox[3]) / 2;
  const local = (ll: LonLat): [number, number] => [(ll[0] - lonC) * kmLon, -(ll[1] - latC) * kmLat];
  const groundKm = (ll: LonLat) => {
    const c = ((ll[0] - bbox[0]) / (bbox[2] - bbox[0])) * (cols - 1);
    const r = ((bbox[3] - ll[1]) / (bbox[3] - bbox[1])) * (rows - 1);
    const c0 = Math.max(0, Math.min(cols - 2, Math.floor(c)));
    const r0 = Math.max(0, Math.min(rows - 2, Math.floor(r)));
    const tc = Math.max(0, Math.min(1, c - c0));
    const tr = Math.max(0, Math.min(1, r - r0));
    const h = (rr: number, cc: number) => heights[rr * cols + cc];
    return ((h(r0, c0) * (1 - tc) + h(r0, c0 + 1) * tc) * (1 - tr) + (h(r0 + 1, c0) * (1 - tc) + h(r0 + 1, c0 + 1) * tc) * tr) / 1000;
  };

  const now = flightClock(scene.flight, time);
  const pt: FlightPoint = sampleAt(flight, now);
  const [px, pz] = local([pt.lon, pt.lat]);
  const L = aircraftLength(scene.model) / 1000;
  // el avión nunca por debajo del suelo (la altitud de presión corregida tiene unos metros de error)
  const py = Math.max(pt.alt * FT_KM, groundKm([pt.lon, pt.lat]) + 0.004);
  const P = new Vector3(px, py, pz);
  const heading = (pt.hdg ?? trackAt(flight, now)) + offset;
  const euler = new Euler(pt.roll * DEG, (90 - heading) * DEG, pt.pitch * DEG, 'YZX');
  const q = new Quaternion().setFromEuler(euler);
  const fwd = new Vector3(Math.sin(heading * DEG), 0, -Math.cos(heading * DEG));
  const right = new Vector3(Math.cos(heading * DEG), 0, Math.sin(heading * DEG));
  const UP = new Vector3(0, 1, 0);

  const poseOf = (k: Key, kt: number): Pose => {
    const d = (k.distanceM ?? 120) / 1000;
    const h = (k.heightM ?? (k.mode === 'ground' ? 2 : k.mode === 'side' ? 4 : 22)) / 1000;
    if (k.mode === 'cockpit') {
      const eye = new Vector3(L * 0.42 * 1000, 1.3, -0.55).multiplyScalar(0.001).applyQuaternion(q).add(P);
      const look = new Vector3(1, -0.04, 0).applyQuaternion(q).multiplyScalar(2).add(eye);
      return { pos: eye, target: look, up: new Vector3(0, 1, 0).applyQuaternion(q), fov: k.fov ?? 55, inside: 1 };
    }
    if (k.mode === 'ground') {
      const g = k.pos ?? [pt.lon, pt.lat];
      const [gx, gz] = local(g);
      return { pos: new Vector3(gx, groundKm(g) + h, gz), target: P.clone(), up: UP.clone(), fov: k.fov ?? 10, inside: 0 };
    }
    if (k.mode === 'side') {
      const pos = P.clone().addScaledVector(right, k.left ? -d : d).addScaledVector(UP, h).addScaledVector(fwd, -d * 0.15);
      return { pos, target: P.clone(), up: UP.clone(), fov: k.fov ?? 40, inside: 0 };
    }
    if (k.mode === 'orbit') {
      const a = (k.degPerSecond ?? 12) * (time - kt) * DEG;
      const dirV = fwd.clone().multiplyScalar(Math.cos(a)).addScaledVector(right, Math.sin(a));
      return { pos: P.clone().addScaledVector(dirV, -d).addScaledVector(UP, h), target: P.clone(), up: UP.clone(), fov: k.fov ?? 40, inside: 0 };
    }
    // chase
    return {
      pos: P.clone().addScaledVector(fwd, -d).addScaledVector(UP, h),
      target: P.clone().addScaledVector(fwd, L * 0.6),
      up: UP.clone(),
      fov: k.fov ?? 40,
      inside: 0,
    };
  };
  const keys = scene.camera.map((k) => ({ k, t: sec(k.at) }));
  let pose = poseOf(keys[0].k, keys[0].t);
  for (let i = 1; i < keys.length; i++) {
    if (time <= keys[i].t) break;
    const f = ease(Math.min(1, (time - keys[i].t) / MOVE));
    const b = poseOf(keys[i].k, keys[i].t);
    pose = {
      pos: pose.pos.clone().lerp(b.pos, f),
      target: pose.target.clone().lerp(b.target, f),
      up: pose.up.clone().lerp(b.up, f).normalize(),
      fov: pose.fov + (b.fov - pose.fov) * f,
      inside: pose.inside + (b.inside - pose.inside) * f,
    };
  }
  // impacto: el avión se desvanece a la hora del contacto y queda un anillo en el punto real (sin fuego ni restos)
  const impact = scene.impact;
  const impactS = impact ? clockToS(impact.clock) : Infinity;
  const impactVideoT = impact ? videoTimeOf(scene.flight, impact.clock) : Infinity;
  const planeFade = impact ? 1 - Math.max(0, Math.min(1, (time - impactVideoT) / (impact.fadeSeconds ?? 0.8))) : 1;
  const impactP = impact ? Math.max(0, Math.min(1, (time - impactVideoT) / 1.2)) : 0;
  const impactPt = impact ? sampleAt(flight, impactS) : pt;
  const [ix, iz] = local([impactPt.lon, impactPt.lat]);
  const impactPos = new Vector3(ix, groundKm([impactPt.lon, impactPt.lat]), iz);
  plane.traverse((o) => {
    const m = (o as { material?: { transparent: boolean; opacity: number } }).material;
    if (m) {
      m.transparent = true;
      m.opacity = planeFade;
    }
  });
  poseAircraft(plane, pt.flap, pt.gear);
  const camDist = pose.pos.distanceTo(P);
  const near = Math.max(0.0002, Math.min(0.02, camDist * 0.05));
  const sky = FLIGHT.sky[name];
  built.material.uniforms.fogColor.value = new Color(sky.horizon);
  built.material.uniforms.fogNear.value = 6;
  built.material.uniforms.fogFar.value = 32;
  const pfd = scene.pfd;
  const pfdIn = pfd ? reveal(time, sec(pfd.at), 0.5) : null;
  const frameIn = scene.cockpitFrame !== false ? pose.inside : 0;

  return (
    <AbsoluteFill>
      <ThreeCanvas width={W} height={H} camera={{ fov: 40 }} style={{ position: 'absolute' }}>
        <Rig pose={pose} near={near} />
        <mesh position={[pose.pos.x, pose.pos.y, pose.pos.z]} material={skyMat} renderOrder={-1}>
          <sphereGeometry args={[350, 32, 16]} />
        </mesh>
        <hemisphereLight args={['#FFFFFF', '#8A7F6A', 1.6]} />
        <directionalLight position={[-30, 60, 20]} intensity={2.4} />
        {/* suelo lejano alrededor del bloque, del color del horizonte: sin borde visible */}
        <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.003, 0]}>
          <planeGeometry args={[400, 400]} />
          <meshBasicMaterial color={sky.horizon} side={DoubleSide} toneMapped={false} />
        </mesh>
        <mesh geometry={built.top} material={built.material} />
        <primitive
          object={plane as Group}
          position={[P.x, P.y, P.z]}
          quaternion={q}
          scale={[0.001, 0.001, 0.001]}
          visible={pose.inside < 0.98 && planeFade > 0.01}
        />
        {impactP > 0 ? (
          <mesh position={[impactPos.x, impactPos.y + 0.0005, impactPos.z]} rotation={[-Math.PI / 2, 0, 0]}>
            <ringGeometry args={[0.03 + 0.05 * impactP, 0.036 + 0.05 * impactP, 48]} />
            <meshBasicMaterial color={FLIGHT.pfd.amber} transparent opacity={0.9 * Math.min(1, impactP * 2)} side={DoubleSide} toneMapped={false} />
          </mesh>
        ) : null}
      </ThreeCanvas>
      {scene.engineSound ? <EngineAudio playback={scene.flight} data={flight} file={scene.engineSound.file} volume={scene.engineSound.volume} /> : null}
      {frameIn > 0.01 ? <CockpitFrame opacity={frameIn} /> : null}
      {scene.cockpitPanel && pose.inside > 0.01 ? <CockpitPanel opacity={pose.inside} point={pt} /> : null}
      {pfd && pfdIn && pfdIn.opacity > 0 ? (
        <div style={{ ...cornerStyle(pfd.corner), ...pfdIn.style }}>
          <Pfd point={pt} size={pfd.size ?? 520} />
        </div>
      ) : null}
      {impact?.label && impactP > 0 ? (
        <div style={{ position: 'absolute', left: 0, right: 0, top: 860, textAlign: 'center', opacity: impactP }}>
          <Mono size={30} color={FLIGHT.pfd.ink} style={{ backgroundColor: FLIGHT.pfd.box, padding: '10px 22px' }}>{impact.label}</Mono>
        </div>
      ) : null}
      {scene.hud ? <FlightHud show={scene.hud.show} point={pt} theme={name} corner={scene.hud.corner} labels={scene.hud.labels} /> : null}
      <Header top={92} />
    </AbsoluteFill>
  );
};

/** Marco genérico de cabina: parachoques del panel abajo y montantes del parabrisas (no es la cabina de un modelo). */
const CockpitFrame: FC<{ opacity: number }> = ({ opacity }) => {
  const c = FLIGHT.pfd.bg;
  return (
    <svg width={W} height={H} style={{ position: 'absolute', inset: 0, opacity }}>
      <path d={`M 0 ${H} L 0 820 C 520 760 1400 760 ${W} 820 L ${W} ${H} Z`} fill={c} />
      <path d={`M 0 0 L 230 0 L 120 790 L 0 805 Z`} fill={c} />
      <path d={`M ${W} 0 L ${W - 230} 0 L ${W - 120} 790 L ${W} 805 Z`} fill={c} />
      <path d={`M 0 0 L ${W} 0 L ${W} 70 C 1400 110 520 110 0 70 Z`} fill={c} />
      <path d={`M 935 92 L 985 92 L 975 780 L 945 780 Z`} fill={c} />
    </svg>
  );
};

/**
 * Panel de instrumentos genérico bajo el parabrisas: PFD del comandante y del copiloto y, en el centro, los dos
 * motores (N1) en esfera, todo leído de los datos del instante. No reproduce el panel de un fabricante.
 */
const CockpitPanel: FC<{ opacity: number; point: FlightPoint }> = ({ opacity, point }) => {
  const c = FLIGHT.pfd;
  const top = 760;
  const gauge = (v: number | null, label: string, x: number) => {
    const r = 54;
    const cy = top + 150;
    const frac = Math.max(0, Math.min(1.1, (v ?? 0) / 100));
    const a0 = Math.PI * 0.75;
    const a = a0 + frac * Math.PI * 1.5 * (1 / 1.1);
    const arc = (from: number, to: number) =>
      `M ${x + r * Math.cos(from)} ${cy + r * Math.sin(from)} A ${r} ${r} 0 ${to - from > Math.PI ? 1 : 0} 1 ${x + r * Math.cos(to)} ${cy + r * Math.sin(to)}`;
    return (
      <g key={label}>
        <path d={arc(a0, a0 + Math.PI * 1.5)} fill="none" stroke={c.ink} strokeOpacity={0.35} strokeWidth={6} />
        <path d={arc(a0, Math.max(a0 + 0.001, a))} fill="none" stroke={(v ?? 0) < 50 ? c.amber : c.green} strokeWidth={6} />
        <line x1={x} y1={cy} x2={x + (r - 8) * Math.cos(a)} y2={cy + (r - 8) * Math.sin(a)} stroke={c.ink} strokeWidth={3} />
        <text x={x} y={cy + 66} textAnchor="middle" fill={c.ink} fontSize={26} fontFamily={fonts.mono} fontWeight={600}>
          {v === null ? '--' : v.toFixed(1)}
        </text>
        <text x={x} y={cy - r - 14} textAnchor="middle" fill={c.ink} fillOpacity={0.7} fontSize={18} fontFamily={fonts.mono}>{label}</text>
      </g>
    );
  };
  return (
    <div style={{ position: 'absolute', inset: 0, opacity }}>
      <svg width={W} height={H} style={{ position: 'absolute', inset: 0 }}>
        <path d={`M 0 ${top - 40} C 520 ${top - 90} 1400 ${top - 90} ${W} ${top - 40} L ${W} ${H} L 0 ${H} Z`} fill={c.frame} />
        <path d={`M 0 ${top - 40} C 520 ${top - 90} 1400 ${top - 90} ${W} ${top - 40} L ${W} ${top - 22} C 1400 ${top - 72} 520 ${top - 72} 0 ${top - 22} Z`} fill={c.bg} />
        <rect x={810} y={top + 40} width={300} height={230} rx={8} fill={c.box} stroke={c.bg} strokeWidth={6} />
        {gauge(point.n1[0], 'N1 1', 885)}
        {gauge(point.n1[1], 'N1 2', 1035)}
      </svg>
      <div style={{ position: 'absolute', left: 300, top: top + 10 }}>
        <Pfd point={point} size={300} />
      </div>
      <div style={{ position: 'absolute', left: W - 300 - 300, top: top + 10 }}>
        <Pfd point={point} size={300} />
      </div>
    </div>
  );
};

/* ── PFD a pantalla grande ─────────────────────────────────────────────────────────────────────────────────────── */

export const PfdScene: FC = () => {
  const scene = useSceneOf('atlas-pfd');
  const { name, tokens } = useTheme();
  const time = useAtlasTime();
  const data = useJsonFiles<FlightData>([scene.flight.data]);
  if (!data) return null;
  const [flight] = data;
  const now = flightClock(scene.flight, time);
  const pt = sampleAt(flight, now);
  const size = scene.size ?? (scene.lines ? 700 : 860);
  const said = (scene.lines ?? []).filter((l) => videoTimeOf(scene.flight, l.clock) <= time).slice(-3);
  return (
    <AbsoluteFill>
      <Header top={92} />
      {scene.engineSound ? <EngineAudio playback={scene.flight} data={flight} file={scene.engineSound.file} volume={scene.engineSound.volume} /> : null}
      <div style={{ position: 'absolute', top: 230, left: scene.lines ? 140 : (W - size) / 2 }}>
        <Pfd point={pt} size={size} />
        <div style={{ marginTop: 14 }}>
          <Mono size={22} color={tokens.inkSoft}>{sToClock(now)}</Mono>
        </div>
      </div>
      {scene.lines ? (
        <div style={{ position: 'absolute', left: 140 + size + 80, right: 100, top: 260 }}>
          {said.map((l, i) => {
            const r = reveal(time, videoTimeOf(scene.flight, l.clock), 0.45);
            return (
              <div key={l.clock + l.who} style={{ marginBottom: 34, ...r.style, opacity: r.opacity * (i < said.length - 1 ? 0.5 : 1) }}>
                <Mono size={20} color={accentOn(name, l.accent ?? 'data')}>{`${l.clock} · ${l.who}`}</Mono>
                <div style={{ fontFamily: fonts.serif, fontStyle: 'italic', fontSize: 40, lineHeight: 1.2, color: tokens.ink, marginTop: 6 }}>«{l.text}»</div>
              </div>
            );
          })}
        </div>
      ) : null}
    </AbsoluteFill>
  );
};
