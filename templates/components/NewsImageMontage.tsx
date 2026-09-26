import type { CSSProperties, FC } from 'react';
import { AbsoluteFill, Easing, Img, Sequence, Video, interpolate, useCurrentFrame, useVideoConfig } from 'remotion';
import type { SceneProps } from '../types';
import { resolveMediaUrl } from '../media';

const TRANSITION_IN_FRAMES = 3;

const containerStyle: CSSProperties = {
  backgroundColor: 'transparent',
  height: '100%',
  overflow: 'hidden',
  width: '100%',
};

const mediaStyle: CSSProperties = {
  filter: 'contrast(1.12) saturate(0.9)',
  height: '100%',
  objectFit: 'cover',
  position: 'absolute',
  width: '100%',
};

const getRgba = (color: string, alpha: number): string => {
  const hex = color.trim().replace('#', '');

  if (/^[0-9a-f]{3}$/i.test(hex)) {
    const [red, green, blue] = hex.split('').map((channel) => Number.parseInt(`${channel}${channel}`, 16));
    return `rgba(${red}, ${green}, ${blue}, ${alpha})`;
  }

  if (/^[0-9a-f]{6}$/i.test(hex)) {
    const red = Number.parseInt(hex.slice(0, 2), 16);
    const green = Number.parseInt(hex.slice(2, 4), 16);
    const blue = Number.parseInt(hex.slice(4, 6), 16);
    return `rgba(${red}, ${green}, ${blue}, ${alpha})`;
  }

  return color;
};

type NewsShotProps = {
  accentColor: string;
  durationInFrames: number;
  fadeInFrames: number;
  headline?: string;
  label?: string;
  shot: NonNullable<SceneProps['shots']>[number];
};

const NewsShot: FC<NewsShotProps> = ({ accentColor, durationInFrames, fadeInFrames, headline, label, shot }) => {
  const frame = useCurrentFrame();
  const { height, width } = useVideoConfig();
  const fadeOpacity =
    fadeInFrames === 0
      ? 1
      : interpolate(frame, [0, fadeInFrames], [0, 1], {
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
        });
  const motionProgress = interpolate(
    frame,
    [0, Math.max(1, durationInFrames - 1)],
    [0, 1],
    {
      easing: Easing.inOut(Easing.ease),
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
    },
  );
  const scale = interpolate(motionProgress, [0, 1], [1.025, 1.04]);
  const translateX = interpolate(motionProgress, [0, 1], [-width * 0.003, width * 0.003]);
  const translateY = interpolate(motionProgress, [0, 1], [height * 0.002, -height * 0.002]);
  const ribbonText = headline?.trim() || label?.trim();

  return (
    <AbsoluteFill style={{ opacity: fadeOpacity }}>
      {shot.type === 'video' ? (
        <Video
          loop={shot.provider !== 'youtube'}
          src={resolveMediaUrl(shot.url)}
          muted
          style={{
            ...mediaStyle,
            transform: `scale(${scale}) translate3d(${translateX}px, ${translateY}px, 0)`,
          }}
        />
      ) : (
        <Img
          src={resolveMediaUrl(shot.url)}
          style={{
            ...mediaStyle,
            transform: `scale(${scale}) translate3d(${translateX}px, ${translateY}px, 0)`,
          }}
        />
      )}
      <div
        style={{
          background: 'radial-gradient(ellipse at center, transparent 44%, rgba(0, 0, 0, 0.58) 100%)',
          inset: 0,
          pointerEvents: 'none',
          position: 'absolute',
        }}
      />
      {ribbonText ? (
        <div
          style={{
            alignItems: 'center',
            backgroundColor: accentColor,
            boxSizing: 'border-box',
            display: 'flex',
            height: 68,
            left: 0,
            padding: '0 38px',
            position: 'absolute',
            right: 0,
            top: 0,
          }}
        >
          <div
            style={{
              backgroundColor: '#050607',
              color: '#ffffff',
              fontFamily: 'Arial, sans-serif',
              fontSize: 18,
              fontWeight: 800,
              letterSpacing: 2,
              marginRight: 22,
              padding: '9px 14px',
              whiteSpace: 'nowrap',
            }}
          >
            BREAKING
          </div>
          <div
            style={{
              color: '#050607',
              fontFamily: 'Arial, sans-serif',
              fontSize: 28,
              fontWeight: 800,
              letterSpacing: 0.5,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              textTransform: 'uppercase',
              whiteSpace: 'nowrap',
            }}
          >
            {ribbonText}
          </div>
        </div>
      ) : null}
      {label && headline ? (
        <div
          style={{
            backgroundColor: '#050607',
            borderLeft: `8px solid ${accentColor}`,
            bottom: '8%',
            color: '#ffffff',
            fontFamily: 'Arial, sans-serif',
            fontSize: 24,
            fontWeight: 800,
            left: '5%',
            letterSpacing: 1,
            padding: '12px 20px',
            position: 'absolute',
            textTransform: 'uppercase',
          }}
        >
          {label}
        </div>
      ) : null}
      <div
        style={{
          bottom: 26,
          color: getRgba('#ffffff', 0.72),
          fontFamily: 'Arial, sans-serif',
          fontSize: 15,
          fontWeight: 700,
          letterSpacing: 2,
          position: 'absolute',
          right: 38,
        }}
      >
        ARCHIVE / FIELD MATERIAL
      </div>
    </AbsoluteFill>
  );
};

const NewsImageMontage: FC<SceneProps> = ({ accentColor, durationInFrames, keywords, shots, text }) => {
  if (!shots || shots.length === 0) {
    return <AbsoluteFill style={containerStyle} />;
  }

  const totalDurationInFrames = Math.max(1, durationInFrames);
  const shotCount = Math.min(shots.length, totalDurationInFrames);
  const activeShots = shots.slice(0, shotCount);
  const baseDurationInFrames = Math.floor(totalDurationInFrames / shotCount);
  const remainder = totalDurationInFrames % shotCount;
  const lineColor = accentColor || '#ef4444';
  let from = 0;

  return (
    <AbsoluteFill style={containerStyle}>
      {activeShots.map((shot, index) => {
        const shotDurationInFrames = baseDurationInFrames + (index < remainder ? 1 : 0);
        const fadeInFrames = index === 0 ? 0 : Math.min(TRANSITION_IN_FRAMES, Math.max(0, shotDurationInFrames - 1));
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
            <NewsShot
              accentColor={lineColor}
              durationInFrames={shotDurationInFrames}
              fadeInFrames={fadeInFrames}
              headline={text}
              label={keywords?.[index]}
              shot={shot}
            />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};

export default NewsImageMontage;
