import type { CSSProperties, FC } from 'react';
import { AbsoluteFill, Easing, interpolate, useCurrentFrame, useVideoConfig } from 'remotion';
import type { SceneProps } from '../types';

const STREAK_COUNT = 8;

const containerStyle: CSSProperties = {
  backgroundColor: 'transparent',
  height: '100%',
  overflow: 'hidden',
  width: '100%',
};

const WhipTransition: FC<SceneProps> = ({ durationInFrames }) => {
  const frame = useCurrentFrame();
  const { height, width } = useVideoConfig();
  const progress = interpolate(
    frame,
    [0, Math.max(1, durationInFrames - 1)],
    [0, 1],
    {
      easing: Easing.inOut(Easing.ease),
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
    },
  );
  const streakWidth = width * 0.28;

  return (
    <AbsoluteFill style={containerStyle}>
      {Array.from({ length: STREAK_COUNT }, (_, index) => {
        const trailOffset = index * 0.035;
        const streakProgress = Math.max(0, progress - trailOffset);
        const x = interpolate(
          streakProgress,
          [0, 1],
          [-streakWidth * 1.5, width + streakWidth * 1.5],
          {
            easing: Easing.inOut(Easing.ease),
            extrapolateLeft: 'clamp',
            extrapolateRight: 'clamp',
          },
        );
        const opacity =
          interpolate(progress, [0, 0.18, 0.55, 1], [0, 0.3, 0.78, 0], {
            easing: Easing.inOut(Easing.ease),
            extrapolateLeft: 'clamp',
            extrapolateRight: 'clamp',
          }) * (1 - index * 0.07);

        return (
          <div
            key={index}
            style={{
              background:
                'linear-gradient(90deg, transparent 0%, rgba(17, 24, 39, 0.2) 34%, rgba(255, 255, 255, 0.9) 50%, rgba(17, 24, 39, 0.2) 66%, transparent 100%)',
              filter: `blur(${18 + index * 3}px)`,
              height: height * 1.4,
              left: 0,
              opacity,
              position: 'absolute',
              top: -height * 0.2,
              transform: `translate3d(${x}px, 0, 0) skewX(-12deg)`,
              width: streakWidth * (1 - index * 0.035),
            }}
          />
        );
      })}
    </AbsoluteFill>
  );
};

export default WhipTransition;
