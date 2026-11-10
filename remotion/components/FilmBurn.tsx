import type { FC } from 'react';
import { AbsoluteFill, interpolate, random, useCurrentFrame } from 'remotion';

const GRAIN =
  "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='300' height='300'>" +
  "<filter id='g'><feTurbulence type='fractalNoise' baseFrequency='0.8' numOctaves='2' stitchTiles='stitch'/>" +
  "<feColorMatrix values='0 0 0 0 0.5  0 0 0 0 0.5  0 0 0 0 0.5  0 0 0 1 0'/></filter>" +
  "<rect width='100%' height='100%' filter='url(%23g)'/></svg>\")";

/**
 * Film burn at the start of a chapter: a warm light leak sweeps across from one side and burns out
 * to a flash, with heavy grain, then clears to the chapter card (the first ~18 frames of the shot).
 */
export const FilmBurn: FC<{ seed: string; frames?: number }> = ({ seed, frames = 18 }) => {
  const frame = useCurrentFrame();
  if (frame > frames) {
    return null;
  }
  const fromLeft = random(`${seed}-side`) > 0.5;
  const sweep = interpolate(frame, [0, frames * 0.6], [-40, 110], { extrapolateRight: 'clamp' });
  const x = fromLeft ? sweep : 100 - sweep;
  const flash = interpolate(frame, [0, 3, 7, frames], [0.2, 0.6, 0.4, 0], { extrapolateRight: 'clamp' });
  const grain = interpolate(frame, [0, frames], [0.5, 0], { extrapolateRight: 'clamp' });
  return (
    <AbsoluteFill style={{ pointerEvents: 'none' }}>
      <AbsoluteFill
        style={{
          mixBlendMode: 'screen', opacity: flash,
          background: `radial-gradient(ellipse 55% 120% at ${x}% 50%, rgba(255,214,150,1) 0%, rgba(255,120,40,0.85) 35%, rgba(180,30,0,0.4) 60%, rgba(0,0,0,0) 80%)`,
        }}
      />
      <AbsoluteFill style={{ backgroundColor: '#fff3dc', opacity: interpolate(frame, [2, 4, 8], [0, 0.18, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }) }} />
      <AbsoluteFill
        style={{
          backgroundImage: GRAIN, opacity: grain, mixBlendMode: 'overlay',
          backgroundPosition: `${Math.floor(random(`${seed}-${frame}`) * 300)}px ${Math.floor(random(`${seed}-y${frame}`) * 300)}px`,
        }}
      />
    </AbsoluteFill>
  );
};
