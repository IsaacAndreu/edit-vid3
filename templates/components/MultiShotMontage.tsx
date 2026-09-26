import type { CSSProperties, FC } from 'react';
import { AbsoluteFill, Easing, Img, Sequence, Video, interpolate, useCurrentFrame, useVideoConfig } from 'remotion';
import KenBurnsImage from './KenBurnsImage';
import type { SceneProps } from '../types';
import { resolveMediaUrl } from '../media';

const montageStyle: CSSProperties = {
  backgroundColor: 'transparent',
  height: '100%',
  overflow: 'hidden',
  width: '100%',
};

const mediaStyle: CSSProperties = {
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

type VideoShotProps = {
  durationInFrames: number;
  loop: boolean;
  url: string;
};

const VideoShot: FC<VideoShotProps> = ({ durationInFrames, loop, url }) => {
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
  const direction = hashSeed(url) % 2 === 0 ? 1 : -1;
  const scale = interpolate(progress, [0, 1], [1.04, 1.08]);
  const translateX = interpolate(progress, [0, 1], [direction * width * 0.008, -direction * width * 0.008]);
  const translateY = interpolate(progress, [0, 1], [height * 0.004, -height * 0.004]);

  return (
    <Video
      loop={loop}
      src={resolveMediaUrl(url)}
      muted
      style={{
        ...mediaStyle,
        transform: `scale(${scale}) translate3d(${translateX}px, ${translateY}px, 0)`,
        transformOrigin: 'center center',
      }}
    />
  );
};

type ShotLayerProps = {
  fadeInFrames: number;
  scene: Pick<SceneProps, 'accentColor' | 'sceneType'>;
  shot: NonNullable<SceneProps['shots']>[number];
  shotDurationInFrames: number;
};

const ShotLayer: FC<ShotLayerProps> = ({ fadeInFrames, scene, shot, shotDurationInFrames }) => {
  const frame = useCurrentFrame();
  const opacity =
    fadeInFrames === 0
      ? 1
      : interpolate(frame, [0, fadeInFrames], [0, 1], {
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
        });

  return (
    <AbsoluteFill style={{ opacity }}>
      {shot.type === 'image' ? (
        <KenBurnsImage
          imageUrl={shot.url}
          durationInFrames={shotDurationInFrames}
          accentColor={scene.accentColor}
          sceneType={scene.sceneType}
        />
      ) : (
        <VideoShot durationInFrames={shotDurationInFrames} loop={shot.provider !== 'youtube'} url={shot.url} />
      )}
    </AbsoluteFill>
  );
};

const MultiShotMontage: FC<SceneProps> = ({ durationInFrames, shots, ...scene }) => {
  if (!shots || shots.length === 0) {
    return <AbsoluteFill style={montageStyle} />;
  }

  const totalDurationInFrames = Math.max(1, durationInFrames);
  const shotCount = Math.min(shots.length, totalDurationInFrames);
  const activeShots = shots.slice(0, shotCount);
  const baseDurationInFrames = Math.floor(totalDurationInFrames / shotCount);
  const remainder = totalDurationInFrames % shotCount;
  let from = 0;

  return (
    <AbsoluteFill style={montageStyle}>
      {activeShots.map((shot, index) => {
        const shotDurationInFrames = baseDurationInFrames + (index < remainder ? 1 : 0);
        const fadeInFrames = index === 0 ? 0 : Math.min(5, Math.max(0, shotDurationInFrames - 1));
        const sequenceDurationInFrames =
          index === activeShots.length - 1
            ? shotDurationInFrames
            : shotDurationInFrames + fadeInFrames;
        const shotStart = from;
        from += shotDurationInFrames;

        return (
          <Sequence
            key={`${shot.type}-${shot.url}-${index}`}
            from={shotStart}
            durationInFrames={sequenceDurationInFrames}
          >
            <ShotLayer
              fadeInFrames={fadeInFrames}
              scene={scene}
              shot={shot}
              shotDurationInFrames={shotDurationInFrames}
            />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};

export default MultiShotMontage;
