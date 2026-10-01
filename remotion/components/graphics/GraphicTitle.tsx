import type { FC } from 'react';
import { interpolate, useCurrentFrame } from 'remotion';
import { monoFamily, pack, theme, titleFamily } from '../../theme';

/** Top-left heading of a graphic in the channel's way: a slanted accent slash (sport), a thin rule under a
 * serif title (editorial), a mono "//" tag (tech), or the plain accent bar. */
export const GraphicTitle: FC<{ text: string }> = ({ text }) => {
  const frame = useCurrentFrame();
  const show = interpolate(frame, [0, 10], [0, 1], { extrapolateRight: 'clamp' });
  const style = pack();
  const motion = theme.motion;
  const words = style.titleUpper ? text.toUpperCase() : text;
  return (
    <div
      style={{
        position: 'absolute', left: 110, top: 80, display: 'flex', alignItems: 'center', gap: 22, opacity: show,
        transform: `translateX(${(1 - show) * -30}px)`,
      }}
    >
      {motion === 'sport' ? (
        <div style={{ width: 18, height: 70, backgroundColor: theme.accent, transform: 'skewX(-18deg)' }} />
      ) : motion === 'tech' ? (
        <div style={{ fontFamily: monoFamily, fontWeight: 700, fontSize: 44, color: theme.accent }}>{'//'}</div>
      ) : motion === 'editorial' ? null : (
        <div style={{ width: 10, height: 64, backgroundColor: theme.accent }} />
      )}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <div
          style={{
            fontFamily: titleFamily, fontWeight: motion === 'editorial' ? 400 : motion === 'tech' ? 700 : 900,
            fontStyle: style.titleItalic ? 'italic' : 'normal', fontSize: motion === 'sport' ? 72 : motion === 'tech' ? 50 : 60,
            letterSpacing: motion === 'tech' ? '0.04em' : motion === 'sport' ? '0.01em' : undefined,
            color: theme.text, textShadow: theme.shadow, lineHeight: 1.05,
          }}
        >
          {words}
        </div>
        {motion === 'editorial' ? (
          <div style={{ height: 3, width: `${interpolate(frame, [6, 22], [0, 100], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' })}%`, backgroundColor: theme.accent }} />
        ) : null}
      </div>
    </div>
  );
};
