import type { FC } from 'react';
import { AbsoluteFill, Easing, interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { alpha, fontFamily, theme } from '../theme';
import { countUp } from './countUp';

/** One big number in yellow over the footage (reference: "$20-50M"), counting up, with a short label. */
export const Stat: FC<{ value: string; label: string }> = ({ value, label }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enter = spring({ frame, fps, config: { damping: 200, stiffness: 200 }, durationInFrames: 8 });
  const counting = interpolate(frame, [0, 18], [0, 1], { extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic) });
  const size = value.length > 12 ? 150 : value.length > 8 ? 190 : 230;
  // the moment the figure lands (frame 18): a flash of the brand colour and a small bump
  const hit = interpolate(frame, [18, 19, 32], [0, 1, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  return (
    <AbsoluteFill
      style={{
        background: 'radial-gradient(ellipse at center, rgba(0,0,0,0.45) 0%, rgba(0,0,0,0.62) 100%)',
        justifyContent: 'center',
        alignItems: 'center',
        flexDirection: 'column',
        gap: 18,
        padding: '0 120px',
      }}
    >
      <AbsoluteFill
        style={{
          background: `radial-gradient(ellipse 55% 40% at 50% 46%, ${alpha(theme.accent, 0.5 * hit)} 0%, rgba(0,0,0,0) 70%)`,
        }}
      />
      <div
        style={{
          fontFamily,
          fontWeight: 900,
          fontSize: size,
          lineHeight: 1,
          color: theme.accent,
          letterSpacing: '-0.02em',
          textShadow: theme.shadow,
          opacity: enter,
          transform: `scale(${interpolate(enter, [0, 1], [0.9, 1]) * (1 + 0.07 * hit)})`,
          fontVariantNumeric: 'tabular-nums',
          whiteSpace: 'nowrap',
        }}
      >
        {countUp(value, counting)}
      </div>
      <div
        style={{
          fontFamily,
          fontWeight: 600,
          fontSize: 46,
          color: theme.text,
          textAlign: 'center',
          textShadow: theme.shadow,
          maxWidth: 1400,
          opacity: interpolate(frame, [6, 14], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }),
        }}
      >
        {label}
      </div>
    </AbsoluteFill>
  );
};
