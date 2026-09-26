import type { FC } from 'react';
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { fontFamily, theme } from '../theme';

/** Chapter title: white uppercase, heavy, with shadow, over darkened b-roll. */
export const Chapter: FC<{ title: string }> = ({ title }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enter = spring({ frame, fps, config: { damping: 200, stiffness: 180 }, durationInFrames: 10 });
  const size = title.length > 22 ? 104 : title.length > 14 ? 128 : 150;
  return (
    <AbsoluteFill
      style={{
        background: 'radial-gradient(ellipse at center, rgba(0,0,0,0.35) 0%, rgba(0,0,0,0.55) 100%)',
        justifyContent: 'center',
        alignItems: 'center',
        padding: '0 120px',
      }}
    >
      <div
        style={{
          fontFamily,
          fontWeight: 900,
          fontSize: size,
          lineHeight: 1.02,
          color: theme.text,
          textAlign: 'center',
          textTransform: 'uppercase',
          letterSpacing: '-0.01em',
          textShadow: theme.shadow,
          opacity: interpolate(enter, [0, 1], [0, 1]),
          transform: `scale(${interpolate(enter, [0, 1], [0.94, 1])})`,
        }}
      >
        {title}
      </div>
    </AbsoluteFill>
  );
};
