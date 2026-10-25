import type { FC } from 'react';
import { AbsoluteFill, Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';
import type { BoardGraphic } from '../../graphics';
import type { Media } from '../../types';
import { Grain, Vignette, rand } from './Paper';

const HAND = "'Caveat', cursive";
const TYPE = "'Special Elite', 'Courier New', monospace";
const CX = 960;
const CY = 540;
const STRING = '#b3121a';

/** Cork: a brown fractal noise with darker flecks (an SVG filter, no image file). */
const Cork: FC = () => (
  <AbsoluteFill style={{ backgroundColor: '#9c6d43' }}>
    <svg width="100%" height="100%" style={{ position: 'absolute', inset: 0 }}>
      <filter id="cork">
        <feTurbulence type="fractalNoise" baseFrequency="0.55" numOctaves="4" seed="7" />
        <feColorMatrix type="matrix" values="0 0 0 0 0.32  0 0 0 0 0.2  0 0 0 0 0.1  0 0 0 -1.6 1.15" />
      </filter>
      <rect width="100%" height="100%" filter="url(#cork)" />
    </svg>
    <AbsoluteFill style={{ background: 'radial-gradient(ellipse 60% 55% at 50% 45%, rgba(255,210,150,0.22), rgba(0,0,0,0) 70%)' }} />
  </AbsoluteFill>
);

/** A red pushpin seen from above. */
const Pin: FC<{ x: number; y: number }> = ({ x, y }) => (
  <div style={{ position: 'absolute', left: x - 15, top: y - 15, width: 30, height: 30, borderRadius: '50%', zIndex: 5,
    background: 'radial-gradient(circle at 35% 30%, #ff7a7a 0%, #d11a1a 45%, #6e0606 100%)', boxShadow: '4px 7px 8px rgba(0,0,0,0.5)' }} />
);

/** A polaroid of the name's photo, or a typed index card when there is none. */
const Card: FC<{ name: string; photo?: Media | null; x: number; y: number; w: number; tilt: number; k: number }> = ({ name, photo, x, y, w, tilt, k }) => {
  const h = photo ? w * 1.18 : w * 0.66;
  return (
    <div style={{ position: 'absolute', left: x - w / 2, top: y - h / 2, width: w, height: h, opacity: Math.min(1, k * 2),
      transform: `rotate(${tilt}deg) scale(${interpolate(k, [0, 1], [1.25, 1])})`, boxShadow: '10px 16px 22px rgba(0,0,0,0.45)',
      backgroundColor: photo ? '#f5f3ee' : '#f2e8c9', boxSizing: 'border-box', padding: photo ? `${w * 0.06}px ${w * 0.06}px 0` : 18,
      backgroundImage: photo ? undefined : 'repeating-linear-gradient(180deg, rgba(0,0,0,0) 0 34px, rgba(60,90,160,0.25) 34px 36px)' }}>
      {photo ? (
        <>
          <div style={{ width: '100%', height: w * 0.86, overflow: 'hidden', backgroundColor: '#222' }}>
            <Img src={staticFile(photo.src)} style={{ width: '100%', height: '100%', objectFit: photo.src.endsWith('.png') ? 'contain' : 'cover',
              objectPosition: 'center 20%', filter: 'sepia(0.25) contrast(1.05) saturate(0.85)', backgroundColor: '#e9e6df' }} />
          </div>
          <div style={{ fontFamily: HAND, fontWeight: 700, fontSize: w * 0.15, color: '#1d1d1d', textAlign: 'center', lineHeight: 1.1,
            marginTop: 6, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{name}</div>
        </>
      ) : (
        <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', textAlign: 'center',
          fontFamily: TYPE, fontSize: w * 0.12, color: '#1b1b1b', textTransform: 'uppercase', lineHeight: 1.15 }}>{name}</div>
      )}
    </div>
  );
};

/** An evidence board: the centre pinned first, then each name around it with a sticky note of how it is linked and a
 * red string stretched from the centre to it, while the camera leans towards the newest card and pulls back. */
export const Board: FC<{ graphic: BoardGraphic; durationInFrames: number }> = ({ graphic, durationInFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const items = graphic.items.slice(0, 5);
  const n = items.length;
  const step = Math.max(12, Math.min(26, Math.floor((durationInFrames * 0.6) / (n + 1))));
  const start = (i: number) => 10 + (i + 1) * step;
  // the four corners, then under the centre, with a little jitter so it looks pinned by hand
  const SLOTS = [[400, 290], [1520, 290], [1520, 790], [400, 790], [960, 890]];
  const spots = items.map((_, i) => ({ x: SLOTS[i][0] + (rand(i + 3) - 0.5) * 50, y: SLOTS[i][1] + (rand(i + 11) - 0.5) * 40,
    tilt: (rand(i + 5) - 0.5) * 12 }));
  const centerK = spring({ frame: frame - 4, fps, config: { damping: 13, stiffness: 140 } });
  const itemK = (i: number) => spring({ frame: frame - start(i), fps, config: { damping: 13, stiffness: 150 } });
  const pull = (i: number) => interpolate(frame, [start(i) + 6, start(i) + 20], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  // camera: leans towards each new card, then pulls back to show the whole board
  const keys = [0, ...items.map((_, i) => start(i)), start(n - 1) + 24, durationInFrames];
  const fx = interpolate(frame, keys, [CX, ...spots.map((s) => CX + (s.x - CX) * 0.5), CX, CX], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const fy = interpolate(frame, keys, [CY, ...spots.map((s) => CY + (s.y - CY) * 0.5), CY, CY], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const zoom = interpolate(frame, [0, start(n - 1) + 24, durationInFrames], [1.32, 1.12, 1.0], { extrapolateRight: 'clamp' });
  const pinOf = (x: number, y: number, w: number, photo: Media | null | undefined, tilt: number) => {
    const d = (photo ? w * 1.18 : w * 0.66) / 2 - 16; // the top middle of the card, turned with it
    const t = (tilt * Math.PI) / 180;
    return [x + d * Math.sin(t), y - d * Math.cos(t)];
  };
  const centerW = 300;
  const [cpx, cpy] = pinOf(CX, CY, centerW, graphic.photo, -2);
  return (
    <AbsoluteFill style={{ backgroundColor: '#2a1c10', overflow: 'hidden' }}>
      <AbsoluteFill style={{ transform: `translate(${CX - fx}px, ${CY - fy}px) scale(${zoom})`, transformOrigin: `${fx}px ${fy}px` }}>
        <Cork />
        <svg width={1920} height={1080} style={{ position: 'absolute', inset: 0, overflow: 'visible' }}>
          <defs>
            <filter id="string-shadow"><feDropShadow dx="3" dy="6" stdDeviation="3" floodOpacity="0.45" /></filter>
          </defs>
          {items.map((item, i) => {
            const [px, py] = pinOf(spots[i].x, spots[i].y, 250, item.photo, spots[i].tilt);
            const sag = 40 + Math.abs(px - cpx) * 0.06;
            return (
              <path key={i} d={`M${cpx},${cpy} Q${(cpx + px) / 2},${(cpy + py) / 2 + sag} ${px},${py}`} fill="none" stroke={STRING}
                strokeWidth={5} strokeLinecap="round" pathLength={1} strokeDasharray="1" strokeDashoffset={1 - pull(i)} filter="url(#string-shadow)" />
            );
          })}
        </svg>
        {items.map((item, i) => {
          if (!item.note) return null;
          const s = spots[i];
          const left = s.x <= CX || i === 4; // the one under the centre keeps its note on its right
          return (
            <div key={`n${i}`} style={{ position: 'absolute', left: left ? s.x + 150 : s.x - 370, top: i === 4 ? s.y - 30 : s.y < CY ? s.y + 30 : s.y - 150, width: 220,
              minHeight: 150, padding: '20px 16px', boxSizing: 'border-box', backgroundColor: '#f7e36b', opacity: pull(i),
              transform: `rotate(${-s.tilt * 0.8}deg)`, boxShadow: '6px 10px 14px rgba(0,0,0,0.35)', fontFamily: HAND, fontWeight: 700,
              fontSize: 38, lineHeight: 1.05, color: '#222' }}>
              {item.note}
            </div>
          );
        })}
        <Card name={graphic.center} photo={graphic.photo} x={CX} y={CY} w={centerW} tilt={-2} k={centerK} />
        {items.map((item, i) => (
          <Card key={i} name={item.name} photo={item.photo} x={spots[i].x} y={spots[i].y} w={250} tilt={spots[i].tilt} k={itemK(i)} />
        ))}
        {centerK > 0.05 ? <Pin x={cpx} y={cpy} /> : null}
        {items.map((item, i) => {
          const [px, py] = pinOf(spots[i].x, spots[i].y, 250, item.photo, spots[i].tilt);
          return itemK(i) > 0.05 ? <Pin key={i} x={px} y={py} /> : null;
        })}
      </AbsoluteFill>
      <Vignette strength={0.6} />
      <Grain opacity={0.1} id="board-grain" />
    </AbsoluteFill>
  );
};
