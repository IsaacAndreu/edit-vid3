import type { FC } from 'react';
import { interpolate, useCurrentFrame } from 'remotion';
import { fontFamily, theme } from '../../theme';

/** Top-left heading of a graphic, with the channel's yellow bar. */
export const GraphicTitle: FC<{ text: string }> = ({ text }) => {
  const frame = useCurrentFrame();
  const show = interpolate(frame, [0, 10], [0, 1], { extrapolateRight: 'clamp' });
  return (
    <div
      style={{
        position: 'absolute',
        left: 110,
        top: 80,
        display: 'flex',
        alignItems: 'center',
        gap: 22,
        opacity: show,
        transform: `translateX(${(1 - show) * -30}px)`,
      }}
    >
      <div style={{ width: 10, height: 64, backgroundColor: theme.accent }} />
      <div style={{ fontFamily, fontWeight: 900, fontSize: 60, color: theme.text, textShadow: theme.shadow }}>
        {text.toUpperCase()}
      </div>
    </div>
  );
};
