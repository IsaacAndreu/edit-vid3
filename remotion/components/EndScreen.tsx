import type { FC } from 'react';
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { alpha, fontFamily, theme } from '../theme';
import { GridBackground } from './GridBackground';

/**
 * The last 20 s: the channel canvas with the empty frames where YouTube's end-screen elements go
 * (a suggested video on the left, the subscribe button on the right). Add the elements in YouTube
 * Studio over these frames. Music plays on; the narration has ended.
 */
export const EndScreen: FC<{ next?: string; subscribe?: string }> = ({ next, subscribe }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enter = spring({ frame: frame - 6, fps, config: { damping: 200, stiffness: 120 }, durationInFrames: 20 });
  const circle = spring({ frame: frame - 14, fps, config: { damping: 200, stiffness: 120 }, durationInFrames: 20 });
  const label = {
    fontFamily,
    fontWeight: 900,
    fontSize: 54,
    letterSpacing: '0.02em',
    color: theme.text,
    textShadow: theme.shadow,
  } as const;
  return (
    <AbsoluteFill>
      <GridBackground />
      {/* Suggested video: 880x495 (16:9) */}
      <div
        style={{
          position: 'absolute',
          left: 150,
          top: 250,
          opacity: enter,
          transform: `translateY(${interpolate(enter, [0, 1], [30, 0])}px)`,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 20, marginBottom: 28 }}>
          <div style={{ width: 10, height: 56, backgroundColor: theme.accent }} />
          <div style={label}>{next || 'SIGUIENTE HISTORIA'}</div>
        </div>
        <div
          style={{
            width: 880,
            height: 495,
            borderRadius: 18,
            border: `5px solid ${theme.accent}`,
            backgroundColor: 'rgba(0,0,0,0.55)',
            boxShadow: `0 0 60px ${alpha(theme.accent, 0.18)}`,
          }}
        />
      </div>
      {/* Subscribe: a 300 px circle */}
      <div
        style={{
          position: 'absolute',
          left: 1280,
          top: 360,
          width: 420,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: 34,
          opacity: circle,
          transform: `scale(${interpolate(circle, [0, 1], [0.85, 1])})`,
        }}
      >
        <div
          style={{
            width: 300,
            height: 300,
            borderRadius: '50%',
            border: `5px solid ${theme.accent}`,
            backgroundColor: 'rgba(0,0,0,0.55)',
            boxShadow: `0 0 60px ${alpha(theme.accent, 0.18)}`,
          }}
        />
        <div style={{ ...label, fontSize: 46 }}>{subscribe || 'SUSCRÍBETE'}</div>
      </div>
    </AbsoluteFill>
  );
};
