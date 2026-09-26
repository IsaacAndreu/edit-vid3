import type { FC } from 'react';
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { fontFamily, theme } from '../theme';
import type { QuestionWord } from '../types';

/**
 * A question from the script in a centred panel. The whole sentence is laid out from the
 * start (dimmed) so nothing reflows; each word lights up when the voice says it.
 */
export const Question: FC<{ words: QuestionWord[]; durationInFrames: number }> = ({ words, durationInFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enter = spring({ frame, fps, config: { damping: 200, stiffness: 180 }, durationInFrames: 10 });
  const exit = interpolate(frame, [durationInFrames - 6, durationInFrames], [1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const chars = words.reduce((n, w) => n + w.text.length + 1, 0);
  const size = chars > 80 ? 56 : chars > 45 ? 66 : 78;
  return (
    <AbsoluteFill
      style={{
        background: 'radial-gradient(ellipse at center, rgba(0,0,0,0.35) 0%, rgba(0,0,0,0.6) 100%)',
        justifyContent: 'center',
        alignItems: 'center',
        opacity: Math.min(enter, exit),
      }}
    >
      <div
        style={{
          backgroundColor: 'rgba(26,26,26,0.92)',
          borderTop: `8px solid ${theme.accent}`,
          borderRadius: 18,
          padding: '56px 84px 60px',
          maxWidth: 1480,
          boxShadow: '0 30px 80px rgba(0,0,0,0.55)',
          transform: `scale(${interpolate(enter, [0, 1], [0.94, 1])})`,
          textAlign: 'center',
        }}
      >
        <div style={{ fontFamily, fontWeight: 800, fontSize: size, lineHeight: 1.18, color: theme.text }}>
          {words.map((w, i) => {
            const lit = interpolate(frame, [w.from - 2, w.from + 4], [0, 1], {
              extrapolateLeft: 'clamp',
              extrapolateRight: 'clamp',
            });
            return (
              <span
                key={`${w.from}-${i}`}
                style={{
                  opacity: interpolate(lit, [0, 1], [0.22, 1]),
                  display: 'inline-block',
                  transform: `translateY(${interpolate(lit, [0, 1], [6, 0])}px)`,
                  marginRight: '0.26em',
                }}
              >
                {w.text}
              </span>
            );
          })}
        </div>
      </div>
    </AbsoluteFill>
  );
};
