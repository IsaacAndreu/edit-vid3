import type { FC } from 'react';
import { useMemo } from 'react';
import { AbsoluteFill, Easing, Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';
import { geoMercator, geoPath } from 'd3-geo';
import type { GeoPermissibleObjects } from 'd3-geo';
import { feature } from 'topojson-client';
import world from 'world-atlas/countries-110m.json';
import type { MapGraphic } from '../../graphics';
import { Grain, rand, Vignette } from './Paper';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const LAND = (feature(world as any, (world as any).objects.countries) as any).features as { geometry: GeoPermissibleObjects }[];

const W = 1920;
const H = 1080;
const SCALE = 300; // the whole world on a 1920-wide page
const CLOSE = 2.6; // how close the camera gets to each place

/** An old paper world map: the camera travels from place to place and pins a polaroid of each one with a red
 * pushpin and its name handwritten under the photo; the earlier ones stay pinned. */
export const PinMap: FC<{ graphic: MapGraphic; durationInFrames: number }> = ({ graphic, durationInFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const projection = useMemo(() => geoMercator().scale(SCALE).translate([W / 2, H / 2 + 120]), []);
  const path = useMemo(() => geoPath(projection), [projection]);
  const land = useMemo(() => LAND.map((f) => path(f.geometry) || '').join(' '), [path]);
  const points = (graphic.points || []).map((p) => ({ ...p, xy: projection([p.lon, p.lat]) as [number, number] }));
  const intro = 18;
  const each = Math.max(24, (durationInFrames - intro) / Math.max(1, points.length));
  // the camera: the whole map, then each place in turn (moves during the first 40 % of its time)
  const stops = [{ x: W / 2, y: H / 2, s: 1 }, ...points.map((p) => ({ x: p.xy[0], y: p.xy[1] + 70, s: CLOSE }))];
  const k = Math.min(points.length, Math.max(0, Math.floor((frame - intro) / each) + 1));
  const into = k === 0 ? 0 : interpolate(frame - intro - (k - 1) * each, [0, each * 0.4], [0, 1], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.inOut(Easing.cubic) });
  const a = stops[Math.max(0, k - 1)];
  const b = stops[k];
  const cam = { x: a.x + (b.x - a.x) * into, y: a.y + (b.y - a.y) * into, s: a.s + (b.s - a.s) * into };
  return (
    <AbsoluteFill style={{ backgroundColor: '#c9b48a', overflow: 'hidden' }}>
      <AbsoluteFill style={{ transform: `translate(${W / 2}px, ${H / 2}px) scale(${cam.s}) translate(${-cam.x}px, ${-cam.y}px)`, transformOrigin: '0 0' }}>
        <svg width={W} height={H} style={{ position: 'absolute', left: 0, top: 0, overflow: 'visible' }}>
          <rect x={-W} y={-H} width={3 * W} height={3 * H} fill="#cdb98f" />
          <path d={land} fill="#e2cd9b" stroke="#7b5a2c" strokeWidth={1.6 / cam.s} strokeLinejoin="round" />
        </svg>
        {points.map((p, i) => {
          const at = intro + i * each + each * 0.35;
          const drop = spring({ frame: frame - at, fps, config: { damping: 15, stiffness: 140 } });
          if (frame < at) return null;
          const tilt = (rand(i + 3) - 0.5) * 12;
          return (
            <div key={i} style={{ position: 'absolute', left: p.xy[0], top: p.xy[1], width: 0, height: 0 }}>
              <div style={{ position: 'absolute', left: -110, top: -40, width: 220, transform: `scale(${(1.8 / CLOSE) * (1.35 - 0.35 * drop)}) rotate(${tilt}deg)`,
                transformOrigin: '50% 0', opacity: drop }}>
                <div style={{ background: '#f6f3ec', padding: '12px 12px 48px', boxShadow: '0 14px 22px rgba(0,0,0,0.45)' }}>
                  {p.photo ? (
                    <Img src={staticFile(p.photo.src)} style={{ width: 196, height: 240, objectFit: 'cover', display: 'block', filter: 'sepia(0.15) contrast(1.05)' }} />
                  ) : (
                    <div style={{ width: 196, height: 240, background: '#8f7d5a' }} />
                  )}
                  <div style={{ position: 'absolute', left: 18, bottom: 6, fontFamily: "'Caveat'", fontWeight: 700, fontSize: 36, color: '#9b1c1c' }}>{p.name}</div>
                </div>
                <svg width={44} height={56} style={{ position: 'absolute', left: 150, top: -26 }}>
                  <line x1={18} y1={26} x2={24} y2={52} stroke="#777" strokeWidth={3} />
                  <ellipse cx={18} cy={20} rx={16} ry={9} fill="#9e0f12" />
                  <circle cx={18} cy={14} r={12} fill="#e02a2a" />
                  <circle cx={14} cy={10} r={4} fill="rgba(255,255,255,0.6)" />
                </svg>
              </div>
            </div>
          );
        })}
      </AbsoluteFill>
      {graphic.title ? (
        <div style={{ position: 'absolute', left: 80, top: 60, fontFamily: "'Cinzel'", fontWeight: 700, fontSize: 48, color: '#4a3320',
          opacity: interpolate(frame, [0, 10], [0, 1], { extrapolateRight: 'clamp' }) * interpolate(frame, [intro + 10, intro + 20], [1, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }) }}>
          {graphic.title}
        </div>
      ) : null}
      <Vignette strength={0.55} color="40,25,5" />
      <Grain opacity={0.22} id="pinmap-grain" />
    </AbsoluteFill>
  );
};
