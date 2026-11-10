import type { FC } from 'react';
import { AbsoluteFill, interpolate, useCurrentFrame } from 'remotion';
import { fontFamily, theme } from '../theme';
import type { LabelKind } from '../types';

/** Small lower-left tag (a name, a place/date or a score), as said in the narration. Wipes in from the left. */
export const LowerThird: FC<{ kind: LabelKind; text: string; durationInFrames: number }> = ({ kind, text, durationInFrames }) => {
  const frame = useCurrentFrame();
  const reveal = interpolate(frame, [0, 8], [0, 100], { extrapolateRight: 'clamp' });
  const exit = interpolate(frame, [durationInFrames - 6, durationInFrames], [1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const upper = kind === 'place' || kind === 'date';
  return (
    <AbsoluteFill style={{ justifyContent: 'flex-end', alignItems: 'flex-start', padding: '0 0 104px 96px', opacity: exit }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'stretch',
          transform: 'skewX(-10deg)',
          clipPath: `inset(0 ${100 - reveal}% 0 0)`,
          boxShadow: '0 10px 30px rgba(0,0,0,0.45)',
        }}
      >
        <div style={{ width: 10, backgroundColor: theme.accent }} />
        <div
          style={{
            backgroundColor: theme.label,
            color: theme.text,
            fontFamily,
            fontWeight: 800,
            fontStyle: 'italic',
            fontSize: 40,
            letterSpacing: upper ? '0.02em' : '0',
            textTransform: upper ? 'uppercase' : 'none',
            padding: '10px 26px 12px 20px',
            whiteSpace: 'nowrap',
            fontVariantNumeric: 'tabular-nums',
          }}
        >
          <span style={{ display: 'inline-block', transform: 'skewX(10deg)' }}>{text}</span>
        </div>
      </div>
    </AbsoluteFill>
  );
};
