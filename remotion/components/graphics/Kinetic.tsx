import type { FC } from 'react';
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { fontFamily, theme } from '../../theme';
import type { KineticGraphic } from '../../graphics';

/** Kinetic typography for a punchline: words drop in one by one, the final word in yellow. */
export const Kinetic: FC<{ graphic: KineticGraphic; durationInFrames: number }> = ({ graphic, durationInFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const words = graphic.lines.map((line) => line.split(/\s+/).filter(Boolean));
  const total = words.flat().length;
  const gap = Math.max(3, Math.min(8, Math.floor((durationInFrames * 0.6) / Math.max(1, total))));
  let n = 0;
  const out = interpolate(frame, [durationInFrames - 8, durationInFrames], [1, 0], { extrapolateLeft: 'clamp' });
  return (
    <AbsoluteFill
      style={{
        background: 'radial-gradient(ellipse at center, rgba(0,0,0,0.55) 0%, rgba(0,0,0,0.82) 100%)',
        justifyContent: 'center',
        alignItems: 'center',
        flexDirection: 'column',
        gap: 10,
        opacity: out,
      }}
    >
      {words.map((line, li) => (
        <div key={li} style={{ display: 'flex', gap: 26, flexWrap: 'wrap', justifyContent: 'center', maxWidth: 1600 }}>
          {line.map((w, wi) => {
            const k = n++;
            const pop = spring({ frame: frame - k * gap, fps, config: { damping: 11, stiffness: 180 } });
            const last = li === words.length - 1 && wi === line.length - 1;
            return (
              <span
                key={wi}
                style={{
                  fontFamily,
                  fontWeight: 900,
                  fontSize: total > 10 ? 104 : 136,
                  lineHeight: 1.05,
                  color: last ? theme.accent : theme.text,
                  textShadow: theme.shadow,
                  opacity: Math.min(1, pop * 1.6),
                  transform: `translateY(${(1 - pop) * 60}px) scale(${interpolate(pop, [0, 1], [1.25, 1])})`,
                  display: 'inline-block',
                }}
              >
                {w.toUpperCase()}
              </span>
            );
          })}
        </div>
      ))}
    </AbsoluteFill>
  );
};
