import type { CSSProperties, FC } from 'react';
import { AbsoluteFill, Easing, Img, interpolate, useCurrentFrame, useVideoConfig } from 'remotion';
import type { SceneProps } from '../types';
import { resolveMediaUrl } from '../media';

type MotionMode = 'zoom-in' | 'zoom-out' | 'pan-left' | 'pan-right';

const imageContainerStyle: CSSProperties = {
  backgroundColor: 'transparent',
  height: '100%',
  overflow: 'hidden',
  width: '100%',
};

const imageStyle: CSSProperties = {
  height: '100%',
  objectFit: 'cover',
  position: 'absolute',
  width: '100%',
};

const hashSeed = (seed: string): number => {
  let hash = 0;

  for (let index = 0; index < seed.length; index += 1) {
    hash = (hash * 31 + seed.charCodeAt(index)) >>> 0;
  }

  return hash;
};

const getMotionMode = (seed: string): MotionMode => {
  const modes: MotionMode[] = ['zoom-in', 'zoom-out', 'pan-left', 'pan-right'];
  return modes[hashSeed(seed) % modes.length];
};

const KenBurnsImage: FC<SceneProps> = ({ imageUrl, text, durationInFrames }) => {
  const frame = useCurrentFrame();
  const { height, width } = useVideoConfig();

  if (!imageUrl) {
    return <AbsoluteFill style={imageContainerStyle} />;
  }

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
  const mode = getMotionMode(`${imageUrl}:${text ?? ''}`);
  const scale =
    mode === 'zoom-in'
      ? interpolate(progress, [0, 1], [1.1, 1.15])
      : mode === 'zoom-out'
        ? interpolate(progress, [0, 1], [1.15, 1.1])
        : 1.12;
  const translateX =
    mode === 'pan-left'
      ? interpolate(progress, [0, 1], [width * 0.025, -width * 0.025])
      : mode === 'pan-right'
        ? interpolate(progress, [0, 1], [-width * 0.025, width * 0.025])
        : 0;
  const translateY = mode === 'zoom-in' ? interpolate(progress, [0, 1], [height * 0.01, 0]) : 0;

  return (
    <AbsoluteFill style={imageContainerStyle}>
      <Img
        src={resolveMediaUrl(imageUrl)}
        style={{
          ...imageStyle,
          transform: `scale(${scale}) translate3d(${translateX}px, ${translateY}px, 0)`,
          transformOrigin: 'center center',
        }}
      />
    </AbsoluteFill>
  );
};

export default KenBurnsImage;
