import type { CSSProperties, FC } from 'react';
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import type { SceneProps } from '../types';

const STAGGER_IN_FRAMES = 2;

const containerStyle: CSSProperties = {
  alignItems: 'center',
  backgroundColor: 'transparent',
  display: 'flex',
  height: '100%',
  justifyContent: 'center',
  overflow: 'hidden',
  padding: '0 7%',
  width: '100%',
};

const textStyle: CSSProperties = {
  fontFamily: 'Inter, Arial, sans-serif',
  fontSize: 112,
  fontWeight: 900,
  letterSpacing: '-0.04em',
  lineHeight: 1.04,
  maxWidth: '90%',
  textAlign: 'center',
};

const KineticTextHook: FC<SceneProps> = ({ text, accentColor }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const words = text?.trim().split(/\s+/).filter(Boolean) ?? [];

  return (
    <AbsoluteFill style={containerStyle}>
      <div style={{ ...textStyle, color: accentColor }}>
        {words.map((word, index) => {
          const wordFrame = Math.max(0, frame - index * STAGGER_IN_FRAMES);
          const progress = spring({
            frame: wordFrame,
            fps,
            config: {
              damping: 18,
              mass: 0.6,
              stiffness: 170,
            },
          });
          const opacity = interpolate(progress, [0, 1], [0, 1], {
            extrapolateLeft: 'clamp',
            extrapolateRight: 'clamp',
          });
          const scale = interpolate(progress, [0, 1], [0.8, 1], {
            extrapolateLeft: 'clamp',
            extrapolateRight: 'clamp',
          });

          return (
            <span
              key={`${word}-${index}`}
              style={{
                display: 'inline-block',
                opacity,
                transform: `scale(${scale})`,
                transformOrigin: 'center center',
                whiteSpace: 'pre',
              }}
            >
              {word}{' '}
            </span>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

export default KineticTextHook;
