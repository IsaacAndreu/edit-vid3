import type { FC } from 'react';
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { alpha, fontFamily, theme } from '../../theme';
import type { IcebergGraphic } from '../../graphics';

const TOP = 170; // where the first level starts (the tip)
const BAND = 400; // height of each level
const W = 1920;

/** Half-width of the iceberg at height y: a small peak above the water, a huge rounded mass below that
 * bulges near the surface and narrows towards the bottom, with jagged facets. */
const halfWidth = (y: number, water: number, bottom: number, side: number): number => {
  const jag = Math.sin(y / 53 + side * 2.1) * 22 + Math.sin(y / 17 + side * 0.7) * 9 + Math.sin(y / 7 + side) * 4;
  if (y <= water) {
    const t = Math.max(0, (y - (TOP - 60)) / (water - TOP + 60));
    return Math.max(0, 250 * Math.pow(t, 0.8) + jag * 0.5 * t);
  }
  const d = (y - water) / (bottom - water);
  const bulge = d < 0.3 ? Math.sin((d / 0.3) * (Math.PI / 2)) : Math.pow(Math.cos(((d - 0.3) / 0.7) * (Math.PI / 2)), 0.7);
  return Math.max(30, 250 + bulge * (d < 0.3 ? 560 : 560 + 250) - (d < 0.3 ? 0 : 250) + jag);
};

/** Iceberg video: the whole iceberg with one layer per level; at each new level the camera sinks to it,
 * its title comes up, and the cases of the levels above stay written on their layers. */
export const Iceberg: FC<{ graphic: IcebergGraphic; durationInFrames: number }> = ({ graphic, durationInFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const n = graphic.levels.length;
  const water = TOP + BAND * 0.62; // most of level 1 above the water
  const bottom = TOP + n * BAND;
  const height = bottom + 260;
  const center = (k: number) => TOP + k * BAND + BAND / 2;
  const sink = spring({ frame, fps, config: { damping: 200, stiffness: 40 }, durationInFrames: 45 });
  const from = graphic.current > 0 ? center(graphic.current - 1) : center(0) - 250;
  const cam = interpolate(sink, [0, 1], [from, center(graphic.current)]) - 540;
  const title = spring({ frame: frame - 30, fps, config: { damping: 16, stiffness: 150 } });
  const out = interpolate(frame, [durationInFrames - 8, durationInFrames], [1, 0], { extrapolateLeft: 'clamp' });

  const edge = (side: number) => {
    const pts: string[] = [];
    for (let y = TOP - 40; y <= bottom; y += 12) {
      pts.push(`${W / 2 + side * halfWidth(y, water, bottom, side)},${y}`);
    }
    return side < 0 ? pts : pts.reverse();
  };
  const polygon = [...edge(-1), ...edge(1)].join(' ');
  const iceStop = (water / height) * 100;
  return (
    <AbsoluteFill style={{ backgroundColor: '#01060b', opacity: out, overflow: 'hidden' }}>
      <svg width={W} height={height} style={{ position: 'absolute', left: 0, top: -cam }}>
        <defs>
          <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#0d1a26" />
            <stop offset="1" stopColor="#2c4a63" />
          </linearGradient>
          <linearGradient id="sea" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#15608f" />
            <stop offset="0.35" stopColor="#0a2f4a" />
            <stop offset="1" stopColor="#01060b" />
          </linearGradient>
          <linearGradient id="ice" x1="0" y1="0" x2="0" y2={height} gradientUnits="userSpaceOnUse">
            <stop offset="0" stopColor="#ffffff" />
            <stop offset={`${iceStop}%`} stopColor="#cfe9f7" />
            <stop offset={`${iceStop + 0.1}%`} stopColor="#8cc9e8" stopOpacity="0.9" />
            <stop offset="55%" stopColor="#2b7fae" stopOpacity="0.75" />
            <stop offset="100%" stopColor="#0b2537" stopOpacity="0.9" />
          </linearGradient>
        </defs>
        <rect x={0} y={0} width={W} height={water} fill="url(#sky)" />
        <rect x={0} y={water} width={W} height={height - water} fill="url(#sea)" />
        <polygon points={polygon} fill="url(#ice)" />
        <rect x={0} y={water - 2} width={W} height={4} fill="rgba(255,255,255,0.55)" />
        {graphic.levels.map((_, k) =>
          k === 0 ? null : (
            <line key={k} x1={60} x2={W - 60} y1={TOP + k * BAND} y2={TOP + k * BAND} stroke="rgba(255,255,255,0.28)"
              strokeWidth={3} strokeDasharray="18 14" />
          ),
        )}
      </svg>
      <div style={{ position: 'absolute', left: 0, top: -cam, width: W, height }}>
        {graphic.levels.map((t, k) => (
          <div
            key={k}
            style={{
              position: 'absolute', left: 70, top: TOP + k * BAND + 18, fontFamily, fontWeight: 800, fontSize: 30,
              color: k === graphic.current ? theme.accent : 'rgba(255,255,255,0.7)', textTransform: 'uppercase',
              textShadow: '0 2px 8px rgba(0,0,0,0.7)', maxWidth: 420,
            }}
          >
            {k + 1}. {t}
          </div>
        ))}
        {graphic.items.map((item, i) => {
          const same = graphic.items.filter((x) => x.level === item.level);
          const idx = same.indexOf(item);
          const cols = 3;
          const x = W / 2 + ((idx % cols) - 1) * 380 - 170;
          const y = TOP + item.level * BAND + 90 + Math.floor(idx / cols) * 70;
          return (
            <div
              key={i}
              style={{
                position: 'absolute', left: x, top: y, width: 340, textAlign: 'center', fontFamily, fontWeight: 700,
                fontSize: 30, color: '#fff', padding: '6px 10px', borderRadius: 8, backgroundColor: 'rgba(0,0,0,0.45)',
                textShadow: '0 2px 6px rgba(0,0,0,0.8)',
              }}
            >
              {item.name}
            </div>
          );
        })}
      </div>
      <AbsoluteFill style={{ justifyContent: 'flex-end', alignItems: 'center', paddingBottom: 90 }}>
        <div style={{ opacity: title, transform: `translateY(${(1 - title) * 40}px)`, textAlign: 'center', fontFamily }}>
          <div style={{ fontWeight: 800, fontSize: 40, color: theme.accent, textShadow: theme.shadow, letterSpacing: '0.04em' }}>
            NIVEL {graphic.current + 1}
          </div>
          <div
            style={{
              fontWeight: 900, fontSize: 96, color: '#fff', textTransform: 'uppercase', lineHeight: 1,
              textShadow: `0 6px 30px rgba(0,0,0,0.8), 0 0 40px ${alpha(theme.accent, 0.25)}`, maxWidth: 1600,
            }}
          >
            {graphic.levels[graphic.current]}
          </div>
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
