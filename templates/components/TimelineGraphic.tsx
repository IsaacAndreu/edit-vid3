import type { CSSProperties, FC } from 'react';
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import type { SceneProps } from '../types';

const lineStyle: CSSProperties = {
  backgroundColor: 'transparent',
  height: '100%',
  overflow: 'hidden',
  width: '100%',
};

const clampPosition = (position: number): number =>
  Number.isFinite(position) ? Math.min(1, Math.max(0, position)) : 0;

type TimelinePoint = NonNullable<SceneProps['timelinePoints']>[number] & {
  normalizedPosition: number;
  originalIndex: number;
};

type PointLabelProps = {
  accentColor: string;
  above: boolean;
  label: string;
  opacity: number;
  scale: number;
  value?: string;
  x: number;
  y: number;
};

const PointLabel: FC<PointLabelProps> = ({ accentColor, above, label, opacity, scale, value, x, y }) => (
  <div
    style={{
      color: '#f3f7fb',
      left: x,
      maxWidth: 240,
      opacity,
      position: 'absolute',
      textAlign: 'center',
      top: y,
      transform: `translateX(-50%) scale(${scale})`,
      transformOrigin: above ? 'bottom center' : 'top center',
      width: 'max-content',
    }}
  >
    <div
      style={{
        color: '#e5ebf0',
        fontFamily: 'Inter, Arial, sans-serif',
        fontSize: 23,
        fontWeight: 600,
        lineHeight: 1.1,
        maxWidth: 240,
        overflowWrap: 'anywhere',
      }}
    >
      {label}
    </div>
    {value ? (
      <div
        style={{
          color: accentColor,
          fontFamily: 'Inter, Arial, sans-serif',
          fontSize: 28,
          fontWeight: 800,
          lineHeight: 1.1,
          marginTop: above ? 8 : 6,
        }}
      >
        {value}
      </div>
    ) : null}
  </div>
);

const TimelineGraphic: FC<SceneProps> = ({ accentColor, durationInFrames, timelinePoints }) => {
  const frame = useCurrentFrame();
  const { fps, height, width } = useVideoConfig();
  const lineColor = accentColor || '#9cff57';
  const horizontalPadding = width * 0.12;
  const lineWidth = Math.max(1, width - horizontalPadding * 2);
  const lineY = height * 0.53;
  const totalDurationInFrames = Math.max(1, durationInFrames);
  const normalizedPoints: TimelinePoint[] = (timelinePoints ?? [])
    .map((point, originalIndex) => ({
      ...point,
      normalizedPosition: clampPosition(point.position),
      originalIndex,
    }))
    .sort((first, second) => first.normalizedPosition - second.normalizedPosition || first.originalIndex - second.originalIndex);
  const lineProgress = interpolate(
    frame,
    [0, Math.max(1, totalDurationInFrames - 1)],
    [lineWidth, 0],
    {
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
    },
  );

  return (
    <AbsoluteFill style={lineStyle}>
      <svg height="100%" style={{ inset: 0, overflow: 'visible', position: 'absolute' }} viewBox={`0 0 ${width} ${height}`} width="100%">
        <line
          opacity={0.22}
          stroke={lineColor}
          strokeWidth={2}
          x1={horizontalPadding}
          x2={width - horizontalPadding}
          y1={lineY}
          y2={lineY}
        />
        <line
          stroke={lineColor}
          strokeDasharray={`${lineWidth} ${lineWidth}`}
          strokeDashoffset={lineProgress}
          strokeLinecap="round"
          strokeWidth={3}
          x1={horizontalPadding}
          x2={width - horizontalPadding}
          y1={lineY}
          y2={lineY}
        />
        {normalizedPoints.map((point, index) => {
          const pointFrame = point.normalizedPosition * Math.max(1, totalDurationInFrames - 1);
          const pointProgress = spring({
            frame: Math.max(0, frame - pointFrame),
            fps,
            config: {
              damping: 16,
              mass: 0.55,
              stiffness: 180,
            },
            durationInFrames: 8,
          });
          const pointX = horizontalPadding + lineWidth * point.normalizedPosition;
          const pointScale = interpolate(pointProgress, [0, 1], [0.45, 1], {
            extrapolateLeft: 'clamp',
            extrapolateRight: 'clamp',
          });

          return (
            <g key={`${point.label}-${point.originalIndex}`} opacity={pointProgress}>
              <circle cx={pointX} cy={lineY} fill="#0b1116" r={14 * pointScale} stroke={lineColor} strokeWidth={3} />
              <circle cx={pointX} cy={lineY} fill={lineColor} r={5 * pointScale} />
            </g>
          );
        })}
      </svg>
      {normalizedPoints.map((point, index) => {
        const pointFrame = point.normalizedPosition * Math.max(1, totalDurationInFrames - 1);
        const pointProgress = spring({
          frame: Math.max(0, frame - pointFrame),
          fps,
          config: {
            damping: 16,
            mass: 0.55,
            stiffness: 180,
          },
          durationInFrames: 8,
        });
        const pointX = horizontalPadding + lineWidth * point.normalizedPosition;
        const above = index % 2 === 0;
        const labelY = above ? lineY - 112 : lineY + 38;

        return (
          <PointLabel
            key={`${point.label}-label-${point.originalIndex}`}
            accentColor={lineColor}
            above={above}
            label={point.label}
            opacity={pointProgress}
            scale={interpolate(pointProgress, [0, 1], [0.82, 1], {
              extrapolateLeft: 'clamp',
              extrapolateRight: 'clamp',
            })}
            value={point.value}
            x={pointX}
            y={labelY}
          />
        );
      })}
    </AbsoluteFill>
  );
};

export default TimelineGraphic;
