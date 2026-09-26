import type { CSSProperties, FC } from 'react';
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import type { SceneProps } from '../types';

const TRANSITION_IN_FRAMES = 15;

const containerStyle: CSSProperties = {
  backgroundColor: 'transparent',
  height: '100%',
  overflow: 'hidden',
  width: '100%',
};

const barStyle: CSSProperties = {
  alignItems: 'center',
  bottom: '11%',
  boxSizing: 'border-box',
  display: 'flex',
  left: 0,
  maxWidth: '78%',
  minHeight: 92,
  padding: '20px 48px 20px 64px',
  position: 'absolute',
};

const labelStyle: CSSProperties = {
  color: '#ffffff',
  display: '-webkit-box',
  fontFamily: 'Inter, Arial, sans-serif',
  fontSize: 42,
  fontWeight: 700,
  lineHeight: 1.15,
  maxHeight: 98,
  overflow: 'hidden',
  WebkitBoxOrient: 'vertical',
  WebkitLineClamp: 2,
};

const LowerThird: FC<SceneProps> = ({ text, accentColor, durationInFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const exitStartFrame = Math.max(TRANSITION_IN_FRAMES, durationInFrames - TRANSITION_IN_FRAMES);

  const entryProgress = spring({
    frame,
    fps,
    config: {
      damping: 200,
    },
    durationInFrames: TRANSITION_IN_FRAMES,
  });
  const exitProgress = spring({
    frame: Math.max(0, frame - exitStartFrame),
    fps,
    config: {
      damping: 200,
    },
    durationInFrames: TRANSITION_IN_FRAMES,
  });
  const translateX =
    frame >= exitStartFrame
      ? interpolate(exitProgress, [0, 1], [0, -110], {
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
        })
      : interpolate(entryProgress, [0, 1], [-110, 0], {
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
        });

  return (
    <AbsoluteFill style={containerStyle}>
      <div
        style={{
          ...barStyle,
          backgroundColor: accentColor,
          transform: `translateX(${translateX}%)`,
        }}
      >
        <div style={labelStyle}>{text}</div>
      </div>
    </AbsoluteFill>
  );
};

export default LowerThird;
