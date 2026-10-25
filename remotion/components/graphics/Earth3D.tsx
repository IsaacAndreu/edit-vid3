import type { FC } from 'react';
import { useEffect, useMemo, useState } from 'react';
import { AbsoluteFill, Easing, continueRender, delayRender, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';
import { ThreeCanvas } from '@remotion/three';
import * as THREE from 'three';
import type { MapGraphic } from '../../graphics';
import { fontFamily, theme } from '../../theme';
import { GraphicTitle } from './GraphicTitle';
import { Grain, Vignette } from './Paper';

const W = 1920;
const H = 1080;
const FOV = 35;
const SUN = new THREE.Vector3(-0.85, 0.3, 0.6).normalize(); // in camera space: from the upper left; the right edge in night

/** lat/lon (degrees) → a point on the unit sphere, matching three.js SphereGeometry's uv (u = 0 at 180° W). */
const toXYZ = (lat: number, lon: number, r = 1) => {
  const phi = (lat * Math.PI) / 180;
  const lambda = (lon * Math.PI) / 180;
  return new THREE.Vector3(r * Math.cos(phi) * Math.cos(lambda), r * Math.sin(phi), -r * Math.cos(phi) * Math.sin(lambda));
};

const EARTH_VERTEX = /* glsl */ `
  varying vec2 vUv;
  varying vec3 vNormal;
  varying vec3 vView;
  void main() {
    vUv = uv;
    vec4 world = modelMatrix * vec4(position, 1.0);
    vNormal = normalize(mat3(modelMatrix) * normal);
    vView = normalize(cameraPosition - world.xyz);
    gl_Position = projectionMatrix * viewMatrix * world;
  }
`;

// Day where the sun shines, the city lights on the night side, a soft terminator, the sun glinting on the oceans
// (roughness from the texture's green channel) and a little blue haze towards the rim.
const EARTH_FRAGMENT = /* glsl */ `
  uniform sampler2D day;
  uniform sampler2D night;
  uniform sampler2D surface;
  uniform vec3 sun;
  varying vec2 vUv;
  varying vec3 vNormal;
  varying vec3 vView;
  void main() {
    vec3 n = normalize(vNormal);
    float light = dot(n, sun);
    float dayMix = smoothstep(-0.12, 0.22, light);
    vec3 dayColor = texture2D(day, vUv).rgb * (0.25 + 0.95 * max(light, 0.0));
    vec3 nightColor = texture2D(night, vUv).rgb * vec3(1.15, 0.95, 0.7) * 1.6;
    vec3 color = mix(nightColor, dayColor, dayMix);
    float rough = texture2D(surface, vUv).g;
    vec3 h = normalize(sun + vView);
    float spec = pow(max(dot(n, h), 0.0), 180.0) * (1.0 - rough) * dayMix;
    color += vec3(1.0, 0.9, 0.75) * spec * 0.35;
    float rim = pow(1.0 - max(dot(n, vView), 0.0), 3.0);
    color = mix(color, vec3(0.35, 0.6, 1.0), rim * 0.45 * (0.3 + dayMix));
    gl_FragColor = vec4(color, 1.0);
  }
`;

const CLOUD_FRAGMENT = /* glsl */ `
  uniform sampler2D surface;
  uniform vec3 sun;
  varying vec2 vUv;
  varying vec3 vNormal;
  varying vec3 vView;
  void main() {
    float cloud = texture2D(surface, vUv).b;
    float light = max(dot(normalize(vNormal), sun), 0.0);
    gl_FragColor = vec4(vec3(1.0) * (0.15 + 0.9 * light), smoothstep(0.15, 0.8, cloud) * 0.85);
  }
`;

// The halo around the planet: a slightly bigger sphere seen from inside, glowing only towards its rim.
const ATMOSPHERE_VERTEX = /* glsl */ `
  varying vec3 vNormalView;
  void main() {
    vNormalView = normalize(normalMatrix * normal);
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;
const ATMOSPHERE_FRAGMENT = /* glsl */ `
  varying vec3 vNormalView;
  void main() {
    float glow = pow(max(0.0, 0.55 - dot(vNormalView, vec3(0.0, 0.0, 1.0))), 4.0) * 1.6;
    gl_FragColor = vec4(vec3(0.35, 0.65, 1.0), clamp(glow, 0.0, 0.85));
  }
`;

/** Textures in, before the first frame: Remotion waits for them. */
const useTextures = (srcs: string[]) => {
  const [textures, setTextures] = useState<THREE.Texture[] | null>(null);
  const [handle] = useState(() => delayRender('Earth textures'));
  useEffect(() => {
    const loader = new THREE.TextureLoader();
    Promise.all(srcs.map((s) => loader.loadAsync(staticFile(s)))).then((loaded) => {
      loaded.forEach((t) => {
        t.colorSpace = THREE.SRGBColorSpace;
        t.anisotropy = 8;
      });
      setTextures(loaded);
      continueRender(handle);
    }).catch(() => continueRender(handle));
  }, [handle, srcs]);
  return textures;
};

/**
 * A photorealistic Earth seen from space: the real day surface, the city lights on the night side, clouds, the sun
 * glinting on the oceans and a blue atmosphere, among stars. The camera flies in and turns until the first place
 * faces it; each place gets a glowing pin and its name, and a route is drawn as an arc over the curve of the planet.
 */
export const Earth3D: FC<{ graphic: MapGraphic; durationInFrames: number }> = ({ graphic, durationInFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const earth = graphic.earth!;
  const srcs = useMemo(() => [earth.day.src, earth.night.src, earth.surface.src], [earth]);
  const textures = useTextures(srcs);
  const points = graphic.points ?? [];

  // where to look: the middle of the places (or the first one)
  const lats = points.map((p) => p.lat);
  const lons = points.map((p) => p.lon);
  const focusLat = points.length ? (Math.min(...lats) + Math.max(...lats)) / 2 : 20;
  const focusLon = points.length ? (Math.min(...lons) + Math.max(...lons)) / 2 : 0;
  const spread = points.length > 1 ? Math.max(Math.max(...lats) - Math.min(...lats), Math.max(...lons) - Math.min(...lons)) : 0;

  const fly = interpolate(frame, [0, durationInFrames * 0.55], [0, 1], { extrapolateRight: 'clamp', easing: Easing.inOut(Easing.cubic) });
  const distance = interpolate(fly, [0, 1], [5.2, Math.max(2.05, Math.min(4.2, 2.3 + spread / 45))]);
  const lon = focusLon - 70 * (1 - fly);                 // the globe turns towards the place as the camera comes in
  const lat = focusLat * fly + 10 * (1 - fly);
  const target = toXYZ(lat, lon, 1);
  const camera = useMemo(() => new THREE.PerspectiveCamera(FOV, W / H, 0.1, 100), []);
  camera.position.copy(target.clone().multiplyScalar(distance));
  camera.up.set(0, 1, 0);
  camera.lookAt(0, 0, 0);
  camera.updateMatrixWorld();
  camera.updateProjectionMatrix();
  // the sun stays where it is on screen (upper left): its direction turned into world space
  const sun = SUN.clone().applyQuaternion(camera.quaternion);
  // one uniforms object per material, updated in place every frame (a new object each render is not picked up)
  const earthUniforms = useMemo(() => ({ day: { value: null as THREE.Texture | null }, night: { value: null as THREE.Texture | null },
    surface: { value: null as THREE.Texture | null }, sun: { value: new THREE.Vector3() } }), []);
  const cloudUniforms = useMemo(() => ({ surface: { value: null as THREE.Texture | null }, sun: { value: new THREE.Vector3() } }), []);
  earthUniforms.sun.value.copy(sun);
  cloudUniforms.sun.value.copy(sun);
  if (textures) {
    [earthUniforms.day.value, earthUniforms.night.value, earthUniforms.surface.value] = textures;
    cloudUniforms.surface.value = textures[2];
  }
  const cloudTurn = frame * 0.0006;

  const stars = useMemo(() => {
    const g = new THREE.BufferGeometry();
    const pts: number[] = [];
    for (let i = 0; i < 2500; i++) {
      const v = new THREE.Vector3(Math.sin(i * 12.9898) * 43758.5453 % 1, Math.sin(i * 78.233) * 12345.678 % 1, Math.sin(i * 39.425) * 9876.543 % 1)
        .normalize().multiplyScalar(40);
      pts.push(v.x, v.y, v.z);
    }
    g.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3));
    return g;
  }, []);

  // arcs between consecutive places, lifted over the surface in proportion to their length
  const arcs = useMemo(() => {
    if (!graphic.route || points.length < 2) return [];
    return points.slice(1).map((p, i) => {
      const a = toXYZ(points[i].lat, points[i].lon);
      const b = toXYZ(p.lat, p.lon);
      const lift = 1 + Math.min(0.35, a.distanceTo(b) * 0.25);
      const curve = new THREE.QuadraticBezierCurve3(a.clone().multiplyScalar(1.005),
        a.clone().add(b).normalize().multiplyScalar(lift), b.clone().multiplyScalar(1.005));
      return curve.getPoints(80);
    });
  }, [graphic.route, points]);
  const drawn = interpolate(frame, [durationInFrames * 0.45, durationInFrames * 0.8], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });

  // where each place lands on screen (for the HTML labels), hidden when it is behind the globe
  const labels = points.map((p, i) => {
    const world = toXYZ(p.lat, p.lon, 1.01);
    const facing = world.clone().normalize().dot(camera.position.clone().normalize()) > 0.15;
    const ndc = world.clone().project(camera);
    const at = 0.4 + (0.4 * i) / Math.max(1, points.length);
    const pop = spring({ frame: frame - at * durationInFrames, fps, config: { damping: 14, stiffness: 160 } });
    return { p, x: (ndc.x + 1) / 2 * W, y: (1 - ndc.y) / 2 * H, show: facing ? pop : 0, world };
  });

  return (
    <AbsoluteFill style={{ backgroundColor: '#000' }}>
      <ThreeCanvas width={W} height={H} camera={camera} gl={{ antialias: true, preserveDrawingBuffer: true }}>
        <points geometry={stars}>
          <pointsMaterial color="#ffffff" size={0.06} sizeAttenuation transparent opacity={0.7} />
        </points>
        {textures ? (
          <>
            <mesh>
              <sphereGeometry args={[1, 128, 128]} />
              <shaderMaterial vertexShader={EARTH_VERTEX} fragmentShader={EARTH_FRAGMENT}
                uniforms={earthUniforms} />
            </mesh>
            <mesh rotation={[0, cloudTurn, 0]}>
              <sphereGeometry args={[1.008, 96, 96]} />
              <shaderMaterial vertexShader={EARTH_VERTEX} fragmentShader={CLOUD_FRAGMENT} transparent depthWrite={false}
                uniforms={cloudUniforms} />
            </mesh>
          </>
        ) : null}
        <mesh>
          <sphereGeometry args={[1.07, 96, 96]} />
          <shaderMaterial vertexShader={ATMOSPHERE_VERTEX} fragmentShader={ATMOSPHERE_FRAGMENT} side={THREE.BackSide} transparent
            blending={THREE.AdditiveBlending} depthWrite={false} />
        </mesh>
        {arcs.map((pts, i) => {
          const n = Math.max(2, Math.round(pts.length * drawn));
          // a glowing tube (WebGL lines are one pixel wide whatever the width)
          const path = new THREE.CatmullRomCurve3(pts.slice(0, n));
          return (
            <mesh key={i}>
              <tubeGeometry args={[path, Math.max(2, n), 0.0045, 8, false]} />
              <meshBasicMaterial color={theme.accent} />
            </mesh>
          );
        })}
        {labels.map((l, i) => (
          <mesh key={`pin${i}`} position={l.world} scale={0.012 + 0.006 * l.show}>
            <sphereGeometry args={[1, 16, 16]} />
            <meshBasicMaterial color={theme.accent} />
          </mesh>
        ))}
      </ThreeCanvas>
      {labels.map((l, i) =>
        l.show > 0.01 ? (
          <div key={`l${i}`} style={{ position: 'absolute', left: l.x + 18, top: l.y - 34, opacity: Math.min(1, l.show),
            transform: `translateY(${(1 - l.show) * 12}px)`, fontFamily, color: '#fff', whiteSpace: 'nowrap',
            backgroundColor: 'rgba(0,0,0,0.6)', borderLeft: `5px solid ${theme.accent}`, padding: '6px 14px',
            boxShadow: '0 6px 20px rgba(0,0,0,0.5)' }}>
            <div style={{ fontWeight: 800, fontSize: 32, lineHeight: 1.1 }}>{l.p.name.toUpperCase()}</div>
            {l.p.note ? <div style={{ fontWeight: 600, fontSize: 22, color: theme.accent }}>{l.p.note}</div> : null}
          </div>
        ) : null,
      )}
      {labels.map((l, i) =>
        l.show > 0.01 ? (
          <div key={`r${i}`} style={{ position: 'absolute', left: l.x - 22, top: l.y - 22, width: 44, height: 44, borderRadius: 22,
            border: `3px solid ${theme.accent}`, opacity: Math.max(0, 0.8 - ((frame / fps + i * 0.3) % 1.4) / 1.4),
            transform: `scale(${0.5 + ((frame / fps + i * 0.3) % 1.4)})` }} />
        ) : null,
      )}
      <Vignette strength={0.35} />
      <Grain opacity={0.06} id="earth-grain" />
      {graphic.date ? (
        <div style={{ position: 'absolute', left: 70, top: graphic.title ? 170 : 60, fontFamily, fontWeight: 800, fontSize: 46, color: '#fff',
          textShadow: '0 4px 18px rgba(0,0,0,0.7)', opacity: interpolate(frame, [0, 10], [0, 1], { extrapolateRight: 'clamp' }) }}>
          {graphic.date}
        </div>
      ) : null}
      {earth.credit ? (
        <div style={{ position: 'absolute', right: 26, bottom: 18, fontFamily, fontSize: 18, color: 'rgba(255,255,255,0.7)' }}>{earth.credit}</div>
      ) : null}
      {graphic.title ? <GraphicTitle text={graphic.title} /> : null}
    </AbsoluteFill>
  );
};
