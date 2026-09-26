import type { FC } from 'react';
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { fontFamily, theme } from '../theme';
import type { QuestionWord } from '../types';

/**
 * A question from the script as floating text in the middle of the frame, straight over the
 * footage (no card). The whole sentence is laid out from the start, invisible, so nothing
 * reflows; each word fades up when the voice says it, and the block drifts slowly upwards.
 */
export const Question: FC<{ words: QuestionWord[]; durationInFrames: number }> = ({ words, durationInFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enter = spring({ frame, fps, config: { damping: 200, stiffness: 160 }, durationInFrames: 10 });
  const exit = interpolate(frame, [durationInFrames - 6, durationInFrames], [1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const drift = interpolate(frame, [0, durationInFrames], [10, -10]);
  const chars = words.reduce((n, w) => n + w.text.length + 1, 0);
  const size = chars > 80 ? 64 : chars > 45 ? 76 : 92;
  return (
    <AbsoluteFill
      style={{
        // Soft dark vignette behind the words only, so white text reads on any footage.
        background: 'radial-gradient(ellipse 60% 45% at center, rgba(0,0,0,0.5) 0%, rgba(0,0,0,0) 100%)',
        opacity: Math.min(enter, exit),
        justifyContent: 'center',
        alignItems: 'center',
      }}
    >
      <div
        style={{
          fontFamily,
          fontWeight: 900,
          fontSize: size,
          lineHeight: 1.15,
          color: theme.text,
          textAlign: 'center',
          maxWidth: 1500,
          padding: '0 80px',
          textShadow: theme.shadow,
          letterSpacing: '-0.01em',
          transform: `translateY(${drift}px)`,
        }}
      >
        {words.map((w, i) => {
          const lit = interpolate(frame, [w.from - 2, w.from + 5], [0, 1], {
            extrapolateLeft: 'clamp',
            extrapolateRight: 'clamp',
          });
          return (
            <span
              key={`${w.from}-${i}`}
              style={{
                opacity: lit,
                display: 'inline-block',
                transform: `translateY(${interpolate(lit, [0, 1], [14, 0])}px)`,
                marginRight: '0.24em',
              }}
            >
              {w.text}
            </span>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
