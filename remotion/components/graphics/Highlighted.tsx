import type { FC } from 'react';
import { interpolate, useCurrentFrame } from 'remotion';
import { alpha, theme } from '../../theme';

/** Text with one phrase swept by a marker between frames `from` and `to`. */
export const Highlighted: FC<{ text: string; phrase?: string | null; from: number; to: number; color?: string }> = ({
  text,
  phrase,
  from,
  to,
  color,
}) => {
  const frame = useCurrentFrame();
  const at = phrase ? text.toLowerCase().indexOf(phrase.toLowerCase()) : -1;
  if (!phrase || at < 0) {
    return <>{text}</>;
  }
  const p = interpolate(frame, [from, to], [0, 100], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const marker = color ?? alpha(theme.accent, 0.6);
  return (
    <>
      {text.slice(0, at)}
      <span
        style={{
          backgroundImage: `linear-gradient(${marker}, ${marker})`,
          backgroundRepeat: 'no-repeat',
          backgroundSize: `${p}% 78%`,
          backgroundPosition: '0 70%',
          boxDecorationBreak: 'clone',
          WebkitBoxDecorationBreak: 'clone',
        }}
      >
        {text.slice(at, at + phrase.length)}
      </span>
      {text.slice(at + phrase.length)}
    </>
  );
};
