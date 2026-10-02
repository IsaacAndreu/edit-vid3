import type { FC } from 'react';
import { AbsoluteFill, interpolate, useCurrentFrame } from 'remotion';
import type { QuoteGraphic } from '../../graphics';
import { condensedFamily, fontFamily, theme } from '../../theme';

/**
 * Over a real statement (their own clip, their own voice): who is speaking in a name card at the lower left for the
 * first seconds, and what they say in Spanish as subtitles in the brand's accent colour along the bottom.
 */
export const QuoteOverlay: FC<{ graphic: QuoteGraphic; durationInFrames: number }> = ({ graphic, durationInFrames }) => {
  const frame = useCurrentFrame();
  const card = interpolate(frame, [4, 12, Math.min(durationInFrames - 6, 105), Math.min(durationInFrames, 115)], [0, 1, 1, 0], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const line = (graphic.lines ?? []).find((l) => l.from <= frame && frame < l.to);
  return (
    <AbsoluteFill style={{ pointerEvents: 'none' }}>
      <div style={{
        position: 'absolute', left: 80, bottom: 190, opacity: card, transform: `translateX(${(1 - card) * -40}px)`,
        display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: 4,
      }}>
        <div style={{ backgroundColor: '#ffffff', color: '#0b0b0b', padding: '6px 18px', fontFamily: condensedFamily,
          fontWeight: 700, fontSize: 44, lineHeight: 1.1 }}>
          {graphic.speaker}
        </div>
        {graphic.role ? (
          <div style={{ backgroundColor: theme.accent, color: '#0b0b0b', padding: '4px 18px', fontFamily, fontWeight: 600, fontSize: 26 }}>
            {graphic.role}
          </div>
        ) : null}
      </div>
      {line ? (
        <div style={{ position: 'absolute', left: 120, right: 120, bottom: 70, textAlign: 'center' }}>
          <span style={{
            fontFamily, fontWeight: 700, fontSize: 46, lineHeight: 1.3, color: theme.accent,
            textShadow: '0 0 6px #000, 0 2px 4px #000, 0 0 2px #000', WebkitTextStroke: '1.5px rgba(0,0,0,0.85)',
            paintOrder: 'stroke fill',
          }}>
            {line.text}
          </span>
        </div>
      ) : null}
    </AbsoluteFill>
  );
};
