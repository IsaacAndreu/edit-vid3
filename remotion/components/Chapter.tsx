import type { FC } from 'react';
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { condensedFamily, fontFamily, theme } from '../theme';
import { Scroll } from './graphics/Scroll';

export const roman = (n: number): string => {
  const table: [number, string][] = [[1000, 'M'], [900, 'CM'], [500, 'D'], [400, 'CD'], [100, 'C'], [90, 'XC'],
    [50, 'L'], [40, 'XL'], [10, 'X'], [9, 'IX'], [5, 'V'], [4, 'IV'], [1, 'I']];
  let out = '';
  for (const [value, letters] of table) {
    while (n >= value) {
      out += letters;
      n -= value;
    }
  }
  return out;
};

/** chapterStyle 'numbered': "CAPÍTULO I:" in the accent colour over the title in white, narrow type,
 * centred over the darkened footage; both rise in softly. */
const NumberedChapter: FC<{ title: string; number?: number | null; word?: string }> = ({ title, number, word }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const first = spring({ frame: frame - 3, fps, config: { damping: 200, stiffness: 140 }, durationInFrames: 14 });
  const second = spring({ frame: frame - 9, fps, config: { damping: 200, stiffness: 140 }, durationInFrames: 14 });
  const dim = interpolate(frame, [0, 8], [0, 1], { extrapolateRight: 'clamp' });
  const line = (enter: number) => ({ opacity: enter, transform: `translateY(${interpolate(enter, [0, 1], [26, 0])}px)` });
  return (
    <AbsoluteFill>
      <AbsoluteFill
        style={{ opacity: dim, background: 'radial-gradient(ellipse at center, rgba(0,0,0,0.5) 0%, rgba(0,0,0,0.78) 100%)' }}
      />
      <AbsoluteFill style={{ justifyContent: 'center', alignItems: 'center', flexDirection: 'column', gap: 4 }}>
        {number ? (
          <div
            style={{
              ...line(first), fontFamily: condensedFamily, fontWeight: 700, fontSize: 96, lineHeight: 1.05,
              color: theme.accent, textTransform: 'uppercase', letterSpacing: '0.01em', textShadow: theme.shadow,
            }}
          >
            {`${word || 'Capítulo'} ${roman(number)}:`}
          </div>
        ) : null}
        <div
          style={{
            ...line(number ? second : first), fontFamily: condensedFamily, fontWeight: 500, fontSize: 84, lineHeight: 1.1,
            color: theme.text, textAlign: 'center', maxWidth: 1500, textShadow: theme.shadow,
          }}
        >
          {title}
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

/**
 * Chapter card: "CAPÍTULO 01" in big heavy type with the chapter title under it, left-aligned
 * behind a yellow bar, over darkened footage. A colour wipe sweeps across as it comes in.
 */
/** A ranking video («Los 5 momentos más…»): chapters titled «#3 …», «Nº 3 …», «NÚMERO 3: …» or «3. …» are positions
 * of the countdown. Returns [position, title] or null. */
export const countdownOf = (title: string): [number, string] | null => {
  const m = /^\s*(?:#|N[ºo°.]+\s*|N[ÚU]MERO\s+|NUMBER\s+|NR\.?\s*)?(\d{1,2})\s*(?:[.:·—–\-)]\s*|\s+)(.+)$/i.exec(title);
  if (!m) return null;
  const marked = /^\s*(#|N[ºo°.]|N[ÚU]MERO|NUMBER|NR)/i.test(title) || /^\s*\d{1,2}\s*[.:·—–\-)]/.test(title);
  return marked ? [Number(m[1]), m[2].trim()] : null;
};

/** A position of the countdown: the number huge in the accent colour behind a bar, the title beside it. */
const CountdownChapter: FC<{ position: number; title: string }> = ({ position, title }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enter = spring({ frame: frame - 2, fps, config: { damping: 200, stiffness: 160 }, durationInFrames: 12 });
  const text = spring({ frame: frame - 8, fps, config: { damping: 200, stiffness: 160 }, durationInFrames: 12 });
  const dim = interpolate(frame, [0, 8], [0, 1], { extrapolateRight: 'clamp' });
  return (
    <AbsoluteFill>
      <AbsoluteFill style={{ opacity: dim, background: 'linear-gradient(90deg, rgba(0,0,0,0.82) 0%, rgba(0,0,0,0.45) 100%)' }} />
      <AbsoluteFill style={{ justifyContent: 'center', alignItems: 'flex-start', paddingLeft: 150 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 48 }}>
          <div style={{ width: 14, height: 300, backgroundColor: theme.accent, transform: `scaleY(${enter})` }} />
          <div
            style={{
              fontFamily, fontWeight: 900, fontSize: 300, lineHeight: 0.9, color: theme.accent, letterSpacing: '-0.04em',
              textShadow: theme.shadow, opacity: enter, transform: `translateX(${interpolate(enter, [0, 1], [-60, 0])}px)`,
            }}
          >
            {`#${position}`}
          </div>
          <div
            style={{
              fontFamily, fontWeight: 800, fontSize: 76, lineHeight: 1.05, color: theme.text, textTransform: 'uppercase',
              maxWidth: 1000, textShadow: theme.shadow, opacity: text,
              transform: `translateY(${interpolate(text, [0, 1], [24, 0])}px)`,
            }}
          >
            {title}
          </div>
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

export const Chapter: FC<{ title: string; number?: number | null; word?: string; frames?: number }> = (props) =>
  countdownOf(props.title) ? (
    <CountdownChapter position={countdownOf(props.title)![0]} title={countdownOf(props.title)![1]} />
  ) : theme.chapterStyle === 'numbered' ? (
    <NumberedChapter {...props} />
  ) : theme.chapterStyle === 'scroll' ? (
    <ScrollChapter {...props} />
  ) : (
    <BlockChapter {...props} />
  );

/** chapterStyle 'scroll': the chapter written on an old parchment unrolled on a wooden table (history channels),
 * «CAPÍTULO I» under the ornament. */
const ScrollChapter: FC<{ title: string; number?: number | null; word?: string; frames?: number }> = ({ title, number, word, frames }) => (
  <Scroll graphic={{ type: 'scroll', title, subtitle: number ? `${word || 'Capítulo'} ${roman(number)}` : null }}
    durationInFrames={Math.max(45, frames || 75)} quick />
);

const BlockChapter: FC<{ title: string; number?: number | null; word?: string }> = ({ title, number, word }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enter = spring({ frame: frame - 4, fps, config: { damping: 200, stiffness: 180 }, durationInFrames: 10 });
  const wipe = interpolate(frame, [0, 10], [-110, 110], { extrapolateRight: 'clamp' });
  const heading = number ? `${word || 'CAPÍTULO'} ${String(number).padStart(2, '0')}` : title;
  return (
    <AbsoluteFill>
      <AbsoluteFill
        style={{ background: 'linear-gradient(90deg, rgba(0,0,0,0.78) 0%, rgba(0,0,0,0.45) 55%, rgba(0,0,0,0.25) 100%)' }}
      />
      <AbsoluteFill style={{ justifyContent: 'center', alignItems: 'flex-start', paddingLeft: 140 }}>
        <div
          style={{
            display: 'flex',
            gap: 28,
            opacity: enter,
            transform: `translateX(${interpolate(enter, [0, 1], [-40, 0])}px)`,
          }}
        >
          <div style={{ width: 12, backgroundColor: theme.accent }} />
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div
              style={{
                fontFamily,
                fontWeight: 900,
                fontSize: 150,
                lineHeight: 0.95,
                color: theme.text,
                letterSpacing: '-0.03em',
                textShadow: theme.shadow,
              }}
            >
              {heading}
            </div>
            {number ? (
              <div
                style={{
                  fontFamily,
                  fontWeight: 800,
                  fontSize: 52,
                  color: theme.text,
                  textTransform: 'uppercase',
                  letterSpacing: '0.01em',
                  textShadow: theme.shadow,
                  maxWidth: 1400,
                }}
              >
                {title}
              </div>
            ) : null}
          </div>
        </div>
      </AbsoluteFill>
      <AbsoluteFill style={{ backgroundColor: theme.wipe, transform: `translateX(${wipe}%) skewX(-12deg)` }} />
    </AbsoluteFill>
  );
};
