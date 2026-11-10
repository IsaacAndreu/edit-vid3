import type { FC } from 'react';
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { alpha, fontFamily, theme } from '../../theme';
import type { SplitGraphic } from '../../graphics';
import type { Media } from '../../types';
import { GridBackground } from '../GridBackground';
import { MediaBox } from './MediaBox';

// The seam: one slanted line, and both clips are cut exactly along it.
const TOP = 1005;
const BOTTOM = 915;
const HALF = 1010; // width of each clip (a little more than half, so the slant never shows a gap)

/** Two clips side by side, cut along one slanted seam: each slides in from its side with its name,
 * then the seam line draws itself from top to bottom. */
export const Split: FC<{ graphic: SplitGraphic; durationInFrames: number }> = ({ graphic, durationInFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const a = spring({ frame: frame - 2, fps, config: { damping: 200, stiffness: 110 } });
  const b = spring({ frame: frame - 10, fps, config: { damping: 200, stiffness: 110 } });
  const line = interpolate(frame, [8, 20], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const panel = (media: Media | null | undefined, name: string, side: 'left' | 'right', t: number, color: string) => (
    <AbsoluteFill
      style={{
        clipPath:
          side === 'left'
            ? `polygon(0 0, ${TOP}px 0, ${BOTTOM}px 1080px, 0 1080px)`
            : `polygon(${TOP}px 0, 1920px 0, 1920px 1080px, ${BOTTOM}px 1080px)`,
        transform: `translateX(${(1 - t) * (side === 'left' ? -1100 : 1100)}px)`,
      }}
    >
      <MediaBox
        media={media}
        width={HALF}
        height={1080}
        durationInFrames={durationInFrames}
        style={{ position: 'absolute', top: 0, [side]: 0, border: 'none', borderRadius: 0, boxShadow: 'none' }}
      />
      <div
        style={{
          position: 'absolute',
          bottom: 80,
          [side]: 80,
          fontFamily,
          fontWeight: 900,
          fontSize: 58,
          color: '#111',
          backgroundColor: color,
          padding: '8px 26px',
          boxShadow: '0 10px 30px rgba(0,0,0,0.55)',
          opacity: interpolate(t, [0.6, 1], [0, 1], { extrapolateLeft: 'clamp' }),
        }}
      >
        {name.toUpperCase()}
      </div>
    </AbsoluteFill>
  );
  return (
    <AbsoluteFill>
      <GridBackground />
      {panel(graphic.left.media, graphic.left.name, 'left', a, theme.accent)}
      {panel(graphic.right.media, graphic.right.name, 'right', b, theme.accent2)}
      <svg width={1920} height={1080} style={{ position: 'absolute', inset: 0 }}>
        <line
          x1={TOP}
          y1={0}
          x2={TOP + (BOTTOM - TOP) * line}
          y2={1080 * line}
          stroke={alpha('#000000', 0.55)}
          strokeWidth={26}
        />
        <line
          x1={TOP}
          y1={0}
          x2={TOP + (BOTTOM - TOP) * line}
          y2={1080 * line}
          stroke={theme.accent}
          strokeWidth={10}
          style={{ filter: `drop-shadow(0 0 14px ${alpha(theme.accent, 0.9)})` }}
        />
      </svg>
      {graphic.title ? (
        <div
          style={{
            position: 'absolute',
            top: 50,
            left: '50%',
            transform: `translateX(-50%) translateY(${(1 - line) * -30}px)`,
            fontFamily,
            fontWeight: 900,
            fontSize: 48,
            color: theme.text,
            backgroundColor: alpha(theme.canvas, 0.88),
            border: `3px solid ${theme.accent}`,
            padding: '10px 34px',
            borderRadius: 12,
            whiteSpace: 'nowrap',
            opacity: line,
          }}
        >
          {graphic.title.toUpperCase()}
        </div>
      ) : null}
    </AbsoluteFill>
  );
};
