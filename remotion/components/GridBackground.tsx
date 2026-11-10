import type { FC } from 'react';
import { AbsoluteFill } from 'remotion';
import { alpha, theme } from '../theme';

// Chalk dust: fractal noise as an SVG data URI (no network, same on every frame).
const DUST =
  "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='512' height='512'>" +
  "<filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='3' stitchTiles='stitch'/>" +
  "<feColorMatrix values='0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 0.55 0'/></filter>" +
  "<rect width='100%' height='100%' filter='url(%23n)'/></svg>\")";
const SMUDGE =
  "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='1024' height='1024'>" +
  "<filter id='s'><feTurbulence type='fractalNoise' baseFrequency='0.006' numOctaves='4' seed='7'/>" +
  "<feColorMatrix values='0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 0.9 -0.35'/></filter>" +
  "<rect width='100%' height='100%' filter='url(%23s)'/></svg>\")";

/** Textured dark-grey chalkboard (graphicsStyle 'pizarra'): wiped chalk smudges, fine dust and a vignette. */
const Chalkboard: FC = () => (
  <AbsoluteFill style={{ backgroundColor: theme.canvas }}>
    <AbsoluteFill style={{ backgroundImage: SMUDGE, backgroundSize: '1024px 1024px', opacity: 0.16 }} />
    <AbsoluteFill style={{ backgroundImage: DUST, backgroundSize: '512px 512px', opacity: 0.1 }} />
    <AbsoluteFill style={{ background: 'radial-gradient(ellipse 80% 75% at 50% 50%, rgba(0,0,0,0) 55%, rgba(0,0,0,0.55) 100%)' }} />
  </AbsoluteFill>
);

/** The channel canvas behind framed cards: near-black, a fine grid and a warm glow at the bottom
 * (or the chalkboard, with graphicsStyle 'pizarra'). */
export const GridBackground: FC = () =>
  theme.graphicsStyle === 'pizarra' ? (
    <Chalkboard />
  ) : (
    <AbsoluteFill style={{ backgroundColor: theme.canvas }}>
      <AbsoluteFill
        style={{
          backgroundImage:
            'linear-gradient(rgba(255,255,255,0.07) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.07) 1px, transparent 1px)',
          backgroundSize: '64px 64px',
          backgroundPosition: 'center center',
        }}
      />
      <AbsoluteFill
        style={{
          background: `radial-gradient(ellipse 85% 45% at 50% 108%, ${theme.glow} 0%, ${alpha(theme.glow, 0.1)} 45%, rgba(0,0,0,0) 75%)`,
        }}
      />
    </AbsoluteFill>
  );
