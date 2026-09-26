import type { FC } from 'react';
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { fontFamily, theme } from '../theme';
import type { QuestionWord } from '../types';

/** Lines end after a word closing a sentence or a question, so each question sits on its own line. */
const toLines = (words: QuestionWord[]): QuestionWord[][] => {
  const lines: QuestionWord[][] = [[]];
  for (const w of words) {
    lines[lines.length - 1].push(w);
    if (/[?.!…]["»”)]*$/.test(w.text)) lines.push([]);
  }
  return lines.filter((line) => line.length > 0);
};

/**
 * A question from the script as floating text in the middle of the frame, straight over the
 * footage (no card). Each line appears, centred, when the voice starts it; inside the line the
 * words brighten as they are spoken. The block drifts slowly upwards.
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
  const lines = toLines(words);
  const longest = Math.max(...lines.map((line) => line.reduce((n, w) => n + w.text.length + 1, 0)));
  const size = longest > 44 ? 68 : longest > 30 ? 80 : 96;
  return (
    <AbsoluteFill
      style={{
        background: 'radial-gradient(ellipse 70% 55% at center, rgba(0,0,0,0.62) 0%, rgba(0,0,0,0.38) 100%)',
        opacity: Math.min(enter, exit),
        justifyContent: 'center',
        alignItems: 'center',
      }}
    >
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: size * 0.28,
          maxWidth: 1600,
          padding: '0 80px',
          transform: `translateY(${drift}px)`,
        }}
      >
        {lines.map((line, index) => {
          const shown = interpolate(frame, [line[0].from - 3, line[0].from + 5], [0, 1], {
            extrapolateLeft: 'clamp',
            extrapolateRight: 'clamp',
          });
          return (
            <div
              key={`${line[0].from}-${index}`}
              style={{
                fontFamily,
                fontWeight: 900,
                fontSize: size,
                lineHeight: 1.12,
                color: theme.text,
                textAlign: 'center',
                textWrap: 'balance',
                textShadow: theme.shadow,
                letterSpacing: '-0.01em',
                opacity: shown,
                transform: `translateY(${interpolate(shown, [0, 1], [16, 0])}px)`,
              }}
            >
              {line.map((w, i) => {
                const lit = interpolate(frame, [w.from - 2, w.from + 4], [0, 1], {
                  extrapolateLeft: 'clamp',
                  extrapolateRight: 'clamp',
                });
                return (
                  <span key={`${w.from}-${i}`} style={{ opacity: interpolate(lit, [0, 1], [0.45, 1]) }}>
                    {w.text}
                    {i < line.length - 1 ? ' ' : ''}
                  </span>
                );
              })}
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
