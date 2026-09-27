import type { FC } from 'react';
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { fontFamily, theme } from '../theme';

/**
 * Chapter card: "CAPÍTULO 01" in big heavy type with the chapter title under it, left-aligned
 * behind a yellow bar, over darkened footage. A colour wipe sweeps across as it comes in.
 */
export const Chapter: FC<{ title: string; number?: number | null }> = ({ title, number }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enter = spring({ frame: frame - 4, fps, config: { damping: 200, stiffness: 180 }, durationInFrames: 10 });
  const wipe = interpolate(frame, [0, 10], [-110, 110], { extrapolateRight: 'clamp' });
  const heading = number ? `CAPÍTULO ${String(number).padStart(2, '0')}` : title;
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
