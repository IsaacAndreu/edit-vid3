import type { CSSProperties, FC } from 'react';
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import type { SceneProps } from '../types';

const TITLE_IN_DURATION_IN_FRAMES = 22;
const ACCENT_IN_DELAY_IN_FRAMES = 5;
const ACCENT_IN_DURATION_IN_FRAMES = 16;
const EXIT_DURATION_IN_FRAMES = 8;

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

const TitleCard: FC<SceneProps> = ({ accentColor, durationInFrames, sceneType, text }) => {
  const frame = useCurrentFrame();
  const { fps, width } = useVideoConfig();
  const title = text?.trim() || 'Untitled section';
  const lineColor = accentColor || '#9cff57';
  const titleFontSize = Math.min(width * (title.length > 52 ? 0.06 : 0.078), title.length > 52 ? 116 : 150);
  const exitStartFrame = Math.max(TITLE_IN_DURATION_IN_FRAMES, durationInFrames - EXIT_DURATION_IN_FRAMES);

  const titleProgress = spring({
    frame,
    fps,
    config: {
      damping: 30,
      mass: 0.85,
      stiffness: 125,
    },
    durationInFrames: TITLE_IN_DURATION_IN_FRAMES,
  });
  const accentProgress = spring({
    frame: Math.max(0, frame - ACCENT_IN_DELAY_IN_FRAMES),
    fps,
    config: {
      damping: 34,
      mass: 0.7,
      stiffness: 155,
    },
    durationInFrames: ACCENT_IN_DURATION_IN_FRAMES,
  });
  const exitProgress = spring({
    frame: Math.max(0, frame - exitStartFrame),
    fps,
    config: {
      damping: 30,
      mass: 0.7,
      stiffness: 150,
    },
    durationInFrames: EXIT_DURATION_IN_FRAMES,
  });
  const titleOpacity = interpolate(titleProgress, [0, 1], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const titleScale = interpolate(titleProgress, [0, 1], [1.12, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const titleTranslateY = interpolate(titleProgress, [0, 1], [22, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const accentWidth = interpolate(accentProgress, [0, 1], [0, Math.min(width * 0.14, 260)], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const exitOpacity = interpolate(exitProgress, [0, 1], [1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  return (
    <AbsoluteFill
      style={{
        backgroundColor: '#030303',
        backgroundImage: `radial-gradient(circle at 50% 46%, ${getRgba(lineColor, 0.08)} 0%, rgba(3, 3, 3, 0) 42%), linear-gradient(135deg, #070707 0%, #020202 100%)`,
        color: '#f4f5f6',
        overflow: 'hidden',
      }}
    >
      <div
        style={{
          background: `linear-gradient(90deg, transparent, ${getRgba(lineColor, 0.13)}, transparent)`,
          height: 1,
          left: '7%',
          opacity: titleOpacity * exitOpacity,
          position: 'absolute',
          right: '7%',
          top: '28%',
        }}
      />
      <div
        style={{
          borderLeft: `2px solid ${lineColor}`,
          bottom: '22%',
          left: '7%',
          opacity: accentProgress * exitOpacity,
          position: 'absolute',
          top: '22%',
          transform: `scaleY(${interpolate(accentProgress, [0, 1], [0.2, 1])})`,
          transformOrigin: 'center',
        }}
      />
      <div
        style={{
          alignItems: 'center',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          inset: 0,
          opacity: exitOpacity,
          padding: '0 10%',
          position: 'absolute',
          textAlign: 'center',
        }}
      >
        <div
          style={{
            color: lineColor,
            fontFamily: 'Inter, Arial, sans-serif',
            fontSize: 22,
            fontWeight: 700,
            letterSpacing: '0.24em',
            marginBottom: 24,
            opacity: titleOpacity,
            textTransform: 'uppercase',
          }}
        >
          {sceneType}
        </div>
        <div
          style={{
            fontFamily: 'Inter, Arial, sans-serif',
            fontSize: titleFontSize,
            fontWeight: 850,
            letterSpacing: '-0.045em',
            lineHeight: 1.02,
            maxWidth: '82%',
            opacity: titleOpacity,
            textShadow: '0 12px 36px rgba(0, 0, 0, 0.45)',
            transform: `translateY(${titleTranslateY}px) scale(${titleScale})`,
          }}
        >
          {title}
        </div>
        <div
          style={{
            backgroundColor: lineColor,
            boxShadow: `0 0 22px ${getRgba(lineColor, 0.55)}`,
            height: 5,
            marginTop: 34,
            opacity: titleOpacity,
            width: accentWidth,
          }}
        />
      </div>
      <div
        style={{
          background: `linear-gradient(90deg, ${getRgba(lineColor, 0.72)}, transparent)`,
          bottom: '13%',
          height: 1,
          left: '7%',
          opacity: accentProgress * exitOpacity,
          position: 'absolute',
          right: '46%',
        }}
      />
    </AbsoluteFill>
  );
};

export default TitleCard;
