import type { FC } from 'react';
import { AbsoluteFill, Easing, interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { alpha, fontFamily, theme } from '../../theme';
import type { TimelineGraphic } from '../../graphics';
import { GridBackground } from '../GridBackground';
import { GraphicTitle } from './GraphicTitle';

const STEP = 520; // px between milestones

/** Years along a line: the camera slides from milestone to milestone, each year lighting up with its text. */
export const TimelineScene: FC<{ graphic: TimelineGraphic; durationInFrames: number }> = ({ graphic, durationInFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const events = graphic.events.slice(0, 8);
  const per = durationInFrames / Math.max(1, events.length);
  // which milestone is in focus (moves smoothly between them)
  const focus = interpolate(
    frame,
    events.map((_, i) => i * per + per * 0.15),
    events.map((_, i) => i),
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.inOut(Easing.cubic) },
  );
  const offset = 960 - 260 - focus * STEP;
  return (
    <AbsoluteFill>
      <GridBackground />
      {graphic.title ? <GraphicTitle text={graphic.title} /> : null}
      <div style={{ position: 'absolute', left: 0, top: 560, width: '100%', height: 6, backgroundColor: 'rgba(255,255,255,0.18)' }} />
      <div
        style={{
          position: 'absolute',
          left: 0,
          top: 560,
          height: 6,
          width: 960,
          backgroundColor: theme.accent,
          boxShadow: `0 0 24px ${alpha(theme.accent, 0.5)}`,
        }}
      />
      {events.map((e, i) => {
        const x = offset + i * STEP + 260;
        const reached = spring({ frame: frame - i * per, fps, config: { damping: 200, stiffness: 140 } });
        const near = Math.max(0, 1 - Math.abs(focus - i));
        return (
          <div key={i}>
            <div
              style={{
                position: 'absolute',
                left: x - 220,
                width: 440,
                top: 330,
                height: 190,
                display: 'flex',
                alignItems: 'flex-end',
                justifyContent: 'center',
                fontFamily,
                fontWeight: 900,
                fontSize: interpolate(near, [0, 1], [70, 130]),
                lineHeight: 1,
                color: reached > 0.5 ? theme.accent : theme.muted,
                opacity: interpolate(reached, [0, 1], [0.35, 1]),
              }}
            >
              {e.year}
            </div>
            <div
              style={{
                position: 'absolute',
                left: x - 19,
                top: 544,
                width: 38,
                height: 38,
                borderRadius: '50%',
                backgroundColor: reached > 0.5 ? theme.accent : '#333',
                border: `6px solid ${theme.canvas}`,
                boxShadow: reached > 0.5 ? `0 0 24px ${alpha(theme.accent, 0.6)}` : 'none',
                transform: `scale(${interpolate(near, [0, 1], [0.8, 1.3])})`,
              }}
            />
            <div
              style={{
                position: 'absolute',
                left: x - 220,
                width: 440,
                top: 620,
                textAlign: 'center',
                fontFamily,
                fontWeight: 700,
                fontSize: 38,
                lineHeight: 1.2,
                color: theme.text,
                opacity: reached * interpolate(near, [0, 1], [0.4, 1]),
              }}
            >
              {e.text}
            </div>
          </div>
        );
      })}
    </AbsoluteFill>
  );
};
