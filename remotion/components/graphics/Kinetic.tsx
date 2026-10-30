import type { FC } from 'react';
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { fontFamily, theme } from '../../theme';
import { GridBackground } from '../GridBackground';
import type { KineticGraphic } from '../../graphics';

/** Kinetic typography for a punchline: words drop in one by one, the final word in yellow. With the film finish
 * (brand.finish: cine) the line is written instead, as in war documentaries: a serif in sentence case, each word
 * coming out of a blur, the key word in the keyword colour, over the footage barely darkened. */
export const Kinetic: FC<{ graphic: KineticGraphic; durationInFrames: number }> = ({ graphic, durationInFrames }) =>
  theme.finish === 'cine' && !graphic.board ? (
    <CineLine graphic={graphic} durationInFrames={durationInFrames} />
  ) : (
    <Punch graphic={graphic} durationInFrames={durationInFrames} />
  );

const CineLine: FC<{ graphic: KineticGraphic; durationInFrames: number }> = ({ graphic, durationInFrames }) => {
  const frame = useCurrentFrame();
  // *word* marks the key word; without marks, the last word of the last line
  const words = graphic.lines.map((line) => line.split(/\s+/).filter(Boolean));
  const marked = words.flat().some((w) => /^\*.+\*[.,;:!?…]*$/.test(w));
  const total = words.flat().length;
  const gap = Math.max(4, Math.min(9, Math.floor((durationInFrames * 0.55) / Math.max(1, total))));
  const out = interpolate(frame, [durationInFrames - 10, durationInFrames], [1, 0], { extrapolateLeft: 'clamp' });
  const veil = interpolate(frame, [0, 8], [0, 1], { extrapolateRight: 'clamp' }) * out;
  let n = 0;
  return (
    <AbsoluteFill>
      <AbsoluteFill style={{ background: 'radial-gradient(ellipse at center, rgba(0,0,0,0.5) 0%, rgba(0,0,0,0.28) 60%, rgba(0,0,0,0.5) 100%)', opacity: veil }} />
      <AbsoluteFill style={{ justifyContent: 'center', alignItems: 'center', flexDirection: 'column', gap: 4, opacity: out }}>
        {words.map((line, li) => (
          <div key={li} style={{ display: 'flex', gap: 22, flexWrap: 'wrap', justifyContent: 'center', maxWidth: 1500 }}>
            {line.map((w, wi) => {
              const k = n++;
              const t = interpolate(frame - k * gap, [0, 12], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
              const key = marked ? /^\*.+\*[.,;:!?…]*$/.test(w) : li === words.length - 1 && wi === line.length - 1;
              return (
                <span
                  key={wi}
                  style={{
                    fontFamily: "'DM Serif Display', serif",
                    fontSize: total > 12 ? 84 : 104,
                    lineHeight: 1.15,
                    color: key ? theme.keyword : '#f4f1ea',
                    textShadow: '0 4px 24px rgba(0,0,0,0.7)',
                    opacity: t,
                    filter: `blur(${(1 - t) * 10}px)`,
                    transform: `translateY(${(1 - t) * 14}px)`,
                    display: 'inline-block',
                  }}
                >
                  {w.replace(/\*/g, '')}
                </span>
              );
            })}
          </div>
        ))}
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

const Punch: FC<{ graphic: KineticGraphic; durationInFrames: number }> = ({ graphic, durationInFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const words = graphic.lines.map((line) => line.split(/\s+/).filter(Boolean));
  const total = words.flat().length;
  const gap = Math.max(3, Math.min(8, Math.floor((durationInFrames * 0.6) / Math.max(1, total))));
  let n = 0;
  const out = interpolate(frame, [durationInFrames - 8, durationInFrames], [1, 0], { extrapolateLeft: 'clamp' });
  return (
    <AbsoluteFill>
    {graphic.board ? <GridBackground /> : null}
    <AbsoluteFill
      style={{
        background: graphic.board ? 'transparent' : 'radial-gradient(ellipse at center, rgba(0,0,0,0.55) 0%, rgba(0,0,0,0.82) 100%)',
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
                {w.replace(/\*/g, '').toUpperCase()}
              </span>
            );
          })}
        </div>
      ))}
    </AbsoluteFill>
    </AbsoluteFill>
  );
};
