import type { FC } from 'react';
import { useMemo } from 'react';
import { AbsoluteFill, Easing, interpolate, useCurrentFrame } from 'remotion';
import { ThreeCanvas } from '@remotion/three';
import * as THREE from 'three';
import type { ChartGraphic } from '../../graphics';
import { fontFamily, theme } from '../../theme';
import { countUp } from '../countUp';
import { GraphicTitle } from './GraphicTitle';
import { Grain, Vignette } from './Paper';

const W = 1920;
const H = 1080;
const MAX_H = 3.2; // the tallest bar, in scene units
const FOG = '#0d0e12';

/**
 * Bars as solid blocks on a glossy dark floor: they rise one after another with the value counting up above each,
 * lit from the side so they have volume, while the camera drifts slowly around them. The highest bar takes the
 * channel's colour, the rest a graphite grey.
 */
export const Bars3D: FC<{ graphic: ChartGraphic; durationInFrames: number }> = ({ graphic, durationInFrames }) => {
  const frame = useCurrentFrame();
  const data = graphic.data.slice(0, 8);
  const max = Math.max(...data.map((d) => d.value), 1e-9);
  const gap = 1.55;
  const x0 = (-(data.length - 1) * gap) / 2;
  const orbit = interpolate(frame, [0, durationInFrames], [-0.32, 0.18]);
  const camera = useMemo(() => new THREE.PerspectiveCamera(30, W / H, 0.1, 100), []);
  const radius = 8.6 + data.length * 0.85;
  camera.position.set(Math.sin(orbit) * radius, 2.6, Math.cos(orbit) * radius);
  camera.lookAt(0, 1.75, 0);
  camera.updateMatrixWorld();
  camera.updateProjectionMatrix();
  const top = data.reduce((best, d, i) => (d.value > data[best].value ? i : best), 0);
  const rise = (i: number) => interpolate(frame, [8 + i * 7, 34 + i * 7], [0, 1], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic) });
  const unit = graphic.unit ? ` ${graphic.unit}` : '';
  const labels = data.map((d, i) => {
    const k = rise(i);
    const h = Math.max(0.02, (d.value / max) * MAX_H * k);
    const head = new THREE.Vector3(x0 + i * gap, h + 0.35, 0).project(camera);
    const foot = new THREE.Vector3(x0 + i * gap, -0.05, 0.75).project(camera);
    return { d, k, h, head: [(head.x + 1) / 2 * W, (1 - head.y) / 2 * H], foot: [(foot.x + 1) / 2 * W, (1 - foot.y) / 2 * H] };
  });
  return (
    <AbsoluteFill style={{ background: FOG }}>
      <ThreeCanvas width={W} height={H} camera={camera} gl={{ antialias: true, preserveDrawingBuffer: true }} shadows>
        {/* the floor fades into the same colour as the sky, so there is no horizon line */}
        <color attach="background" args={[FOG]} />
        <fog attach="fog" args={[FOG, radius * 0.9, radius * 2.2]} />
        <ambientLight intensity={0.35} />
        <spotLight position={[0, 9, 3]} angle={0.55} penumbra={0.9} intensity={60} distance={30} castShadow />
        <directionalLight position={[-6, 9, 6]} intensity={2.4} castShadow shadow-mapSize-width={2048} shadow-mapSize-height={2048}
          shadow-camera-left={-12} shadow-camera-right={12} shadow-camera-top={12} shadow-camera-bottom={-12} />
        <pointLight position={[6, 4, 5]} intensity={18} color={theme.accent} distance={20} />
        <mesh rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
          <planeGeometry args={[60, 60]} />
          <meshStandardMaterial color="#1d1f25" roughness={0.42} metalness={0.3} />
        </mesh>
        {labels.map((l, i) => (
          <mesh key={i} position={[x0 + i * gap, l.h / 2, 0]} castShadow>
            <boxGeometry args={[1.05, l.h, 1.05]} />
            <meshStandardMaterial color={i === top ? theme.accent : '#5b5e66'} roughness={0.28} metalness={0.25}
              emissive={i === top ? theme.accent : '#000000'} emissiveIntensity={i === top ? 0.18 : 0} />
          </mesh>
        ))}
      </ThreeCanvas>
      {labels.map((l, i) => (
        <div key={`v${i}`}>
          <div style={{ position: 'absolute', left: l.head[0], top: l.head[1], transform: 'translate(-50%, -100%)', opacity: Math.min(1, l.k * 2),
            fontFamily, fontWeight: 900, fontSize: 50, textAlign: 'center', lineHeight: 1.05, color: i === top ? theme.accent : '#ffffff', textShadow: '0 4px 16px rgba(0,0,0,0.8)',
            whiteSpace: 'nowrap' }}>
            {countUp(String(l.d.value), l.k)}
            {unit ? <span style={{ display: 'block', fontSize: 22, fontWeight: 700, color: '#aeb2bb', textAlign: 'center', marginTop: -6 }}>{unit.trim()}</span> : null}
          </div>
          <div style={{ position: 'absolute', left: l.foot[0], top: l.foot[1] + 14, transform: 'translateX(-50%)', opacity: Math.min(1, l.k * 3),
            fontFamily, fontWeight: 700, fontSize: 32, color: '#d6d8de', whiteSpace: 'nowrap', textShadow: '0 2px 10px rgba(0,0,0,0.9)' }}>
            {l.d.label}
          </div>
        </div>
      ))}
      <Vignette strength={0.45} />
      <Grain opacity={0.06} id="bars3d-grain" />
      {graphic.title ? <GraphicTitle text={graphic.title} /> : null}
    </AbsoluteFill>
  );
};
