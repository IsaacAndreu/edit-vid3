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
  if (theme.labelStyle === 'typewriter' && kind !== 'score') {
    return <TypedLabel kind={kind} text={text} durationInFrames={durationInFrames} exit={exit} />;
  }
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

/**
 * brand.labelStyle: typewriter — as true-crime channels label their footage: a name typed in red over the person's
 * photo (centred, low), a place or a date typed in red in the lower-left corner, like a stamp on a case file.
 */
const TypedLabel: FC<{ kind: LabelKind; text: string; durationInFrames: number; exit: number }> = ({ kind, text, exit }) => {
  const frame = useCurrentFrame();
  const name = kind === 'name';
  const shown = Math.floor(interpolate(frame, [2, 2 + Math.min(22, text.length * 1.3)], [0, text.length],
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }));
  const cursor = shown < text.length && Math.floor(frame / 4) % 2 === 0;
  return (
    <AbsoluteFill style={{ justifyContent: 'flex-end', alignItems: name ? 'center' : 'flex-start', opacity: exit,
                           padding: name ? '0 0 120px 0' : '0 0 92px 88px' }}>
      <div style={{ fontFamily: "'Special Elite', 'Courier New', monospace", fontSize: name ? 70 : 40, color: theme.typewriter,
                    letterSpacing: name ? '0.04em' : '0.02em', whiteSpace: 'nowrap',
                    textShadow: '0 2px 2px rgba(0,0,0,0.85), 0 0 18px rgba(0,0,0,0.65)' }}>
        {text.slice(0, shown)}
        <span style={{ opacity: cursor ? 1 : 0 }}>▍</span>
      </div>
    </AbsoluteFill>
  );
};
