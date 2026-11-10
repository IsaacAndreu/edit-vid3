import type { CSSProperties, FC } from 'react';
import { interpolate, useCurrentFrame } from 'remotion';
import { fontFamily } from '../../theme';

export const STAMP_RED = '#e5383b';

/** A rubber stamp ("PROHIBIDO") that slams down at frame `at`: big and transparent → its size, tilted. */
export const Stamp: FC<{ text: string; at: number; size?: number; style?: CSSProperties }> = ({ text, at, size = 120, style }) => {
  const frame = useCurrentFrame();
  const t = interpolate(frame, [at - 5, at], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  if (frame < at - 5) {
    return null;
  }
  return (
    <div
      style={{
        position: 'absolute',
        fontFamily,
        fontWeight: 900,
        fontSize: size,
        letterSpacing: size * 0.06,
        color: STAMP_RED,
        border: `${Math.round(size * 0.09)}px solid ${STAMP_RED}`,
        borderRadius: size * 0.14,
        padding: `${size * 0.08}px ${size * 0.3}px`,
        opacity: t * 0.92,
        transform: `rotate(-12deg) scale(${interpolate(t, [0, 1], [2.4, 1])})`,
        // worn ink: a few lighter speckles over the stamp
        maskImage:
          'radial-gradient(circle at 20% 30%, rgba(0,0,0,0.55) 0 3%, black 4%), radial-gradient(circle at 70% 60%, rgba(0,0,0,0.6) 0 2%, black 3%)',
        maskComposite: 'intersect',
        mixBlendMode: 'multiply',
        whiteSpace: 'nowrap',
        ...style,
      }}
    >
      {text.toUpperCase()}
    </div>
  );
};

/** A small shake right after the stamp lands (px offset for the element it hits). */
export const stampShake = (frame: number, at: number): string => {
  const k = frame - at;
  if (k < 0 || k > 8) {
    return 'translate(0px, 0px)';
  }
  const amp = 10 * (1 - k / 8);
  return `translate(${Math.sin(k * 2.7) * amp}px, ${Math.cos(k * 3.1) * amp}px)`;
};
