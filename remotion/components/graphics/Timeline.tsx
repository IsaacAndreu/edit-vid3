import type { FC } from 'react';
import { AbsoluteFill, Easing, interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { fontFamily, theme } from '../../theme';
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
          boxShadow: '0 0 24px rgba(255,212,0,0.5)',
        }}
      />
      {events.map((e, i) => {
        const x = offset + i * STEP + 260;
        const reached = spring({ frame: frame - i * per, fps, config: { damping: 200, stiffness: 140 } });
        const near = Math.max(0, 1 - Math.abs(focus - i));
        return (
          <div key={i} style={{ position: 'absolute', left: x - 200, top: 250, width: 400, textAlign: 'center', fontFamily }}>
            <div
              style={{
                fontWeight: 900,
                fontSize: interpolate(near, [0, 1], [70, 120]),
                color: reached > 0.5 ? theme.accent : theme.muted,
                opacity: interpolate(reached, [0, 1], [0.35, 1]),
                lineHeight: 1,
                height: 150,
                display: 'flex',
                alignItems: 'flex-end',
                justifyContent: 'center',
              }}
            >
              {e.year}
            </div>
            <div
              style={{
                margin: '120px auto 0',
                width: 34,
                height: 34,
                borderRadius: '50%',
                backgroundColor: reached > 0.5 ? theme.accent : '#333',
                border: '5px solid #07080b',
                transform: `translateY(-150px) scale(${interpolate(near, [0, 1], [0.8, 1.3])})`,
              }}
            />
            <div
              style={{
                marginTop: -40,
                fontWeight: 700,
                fontSize: 36,
                color: theme.text,
                opacity: reached * interpolate(near, [0, 1], [0.45, 1]),
                lineHeight: 1.2,
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
