import type { FC } from 'react';
import { AbsoluteFill, Easing, interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { alpha, fontFamily, theme } from '../theme';
import { countUp } from './countUp';

/** statStyle 'bare': only the giant figure in the accent colour straight over the footage, no dimming
 * or panel ("23.000.000€ anuales"); a label of 1-2 words rides on the same line, a longer one is dropped. */
const BareStat: FC<{ value: string; label: string }> = ({ value, label }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pop = spring({ frame, fps, config: { damping: 14, stiffness: 190 }, durationInFrames: 12 });
  const counting = interpolate(frame, [0, 16], [0, 1], { extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic) });
  const unit = label.trim().split(/\s+/).length <= 2 ? label.trim() : '';
  const text = unit ? `${value} ${unit}` : value;
  const size = text.length > 22 ? 96 : text.length > 16 ? 116 : text.length > 10 ? 140 : 170;
  return (
    <AbsoluteFill style={{ justifyContent: 'center', alignItems: 'center', padding: '0 90px' }}>
      <div
        style={{
          fontFamily,
          fontWeight: 900,
          fontSize: size,
          lineHeight: 1,
          color: theme.accent,
          letterSpacing: '-0.035em',
          whiteSpace: 'nowrap',
          fontVariantNumeric: 'tabular-nums',
          textShadow: '0 4px 18px rgba(0,0,0,0.55), 0 2px 4px rgba(0,0,0,0.7)',
          opacity: Math.min(1, pop * 1.5),
          transform: `scale(${interpolate(pop, [0, 1], [0.82, 1])})`,
        }}
      >
        {countUp(value, counting)}
        {unit ? <span style={{ fontWeight: 800 }}>{` ${unit}`}</span> : null}
      </div>
    </AbsoluteFill>
  );
};

/** One big number in yellow over the footage (reference: "$20-50M"), counting up, with a short label. */
export const Stat: FC<{ value: string; label: string }> = (props) =>
  theme.statStyle === 'bare' ? <BareStat {...props} /> : <PanelStat {...props} />;

const PanelStat: FC<{ value: string; label: string }> = ({ value, label }) => {
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
