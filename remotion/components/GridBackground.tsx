import type { FC } from 'react';
import { AbsoluteFill } from 'remotion';
import { alpha, theme } from '../theme';

/** The channel canvas behind framed cards: near-black, a fine grid and a warm glow at the bottom. */
export const GridBackground: FC = () => (
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
