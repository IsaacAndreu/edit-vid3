import type { CSSProperties, FC } from 'react';
import { AbsoluteFill, Easing, interpolate, useCurrentFrame, useVideoConfig } from 'remotion';
import type { SceneProps } from '../types';

const DRAW_DURATION_IN_FRAMES = 22;

const baseStyle: CSSProperties = {
  backgroundColor: '#06110a',
  color: '#efffe8',
  fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
  height: '100%',
  overflow: 'hidden',
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

type ParsedData = {
  context: string;
  value: string;
};

const parseDataText = (text: string | undefined): ParsedData => {
  const normalizedText = text?.trim() ?? '';
  const valueMatch = normalizedText.match(/^([^\d]*[+-]?\d[\d.,]*(?:\s*[-–—]\s*[+-]?\d[\d.,]*)?(?:\s*[%€$£])?)(?:\s+[-—:]\s*|\s+)(.*)$/);

  if (!valueMatch) {
    return {
      context: '',
      value: normalizedText || 'DATA POINT',
    };
  }

  return {
    context: valueMatch[2].trim(),
    value: valueMatch[1].trim(),
  };
};

type PanelFrameProps = {
  accentColor: string;
  height: number;
  label: string;
  opacity: number;
  width: number;
  x: number;
  y: number;
};

const PanelFrame: FC<PanelFrameProps> = ({ accentColor, height, label, opacity, width, x, y }) => {
  const perimeter = 2 * (width + height);
  const strokeDashoffset = interpolate(
    useCurrentFrame(),
    [0, DRAW_DURATION_IN_FRAMES],
    [perimeter, 0],
    {
      easing: Easing.out(Easing.cubic),
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
    },
  );

  return (
    <>
      <rect
        fill={getRgba(accentColor, 0.07)}
        height={height}
        opacity={opacity}
        rx={10}
        stroke={accentColor}
        strokeDasharray={`${perimeter} ${perimeter}`}
        strokeDashoffset={strokeDashoffset}
        strokeWidth={2}
        width={width}
        x={x}
        y={y}
      />
      <text
        fill={accentColor}
        fontFamily="ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace"
        fontSize={18}
        fontWeight={700}
        letterSpacing={2}
        opacity={opacity}
        x={x + 28}
        y={y + 38}
      >
        {label}
      </text>
    </>
  );
};

const BlueprintDataPanel: FC<SceneProps> = ({ accentColor, durationInFrames, keywords, sceneType, text }) => {
  const frame = useCurrentFrame();
  const { height, width } = useVideoConfig();
  const lineColor = accentColor || '#9cff57';
  const data = parseDataText(text);
  const revealOpacity = interpolate(
    frame,
    [DRAW_DURATION_IN_FRAMES * 0.55, DRAW_DURATION_IN_FRAMES],
    [0, 1],
    {
      easing: Easing.out(Easing.quad),
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
    },
  );
  const contentOpacity = interpolate(
    frame,
    [DRAW_DURATION_IN_FRAMES * 0.7, DRAW_DURATION_IN_FRAMES + 8],
    [0, 1],
    {
      easing: Easing.out(Easing.quad),
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
    },
  );
  const mainPanel = {
    height: height * 0.52,
    width: width * 0.68,
    x: width * 0.1,
    y: height * 0.22,
  };
  const sidePanel = {
    height: height * 0.28,
    width: width * 0.18,
    x: width * 0.78,
    y: height * 0.22,
  };
  const keywordText = keywords?.slice(0, 3).join('  /  ') || `${sceneType.toUpperCase()}  /  ${durationInFrames} FRAMES`;

  return (
    <AbsoluteFill style={baseStyle}>
      <div
        style={{
          backgroundImage: `linear-gradient(to right, ${lineColor} 1px, transparent 1px), linear-gradient(to bottom, ${lineColor} 1px, transparent 1px)`,
          backgroundSize: '80px 80px',
          inset: 0,
          opacity: 0.13,
          position: 'absolute',
        }}
      />
      <div
        style={{
          background: `radial-gradient(circle at 50% 50%, ${getRgba(lineColor, 0.12)}, transparent 62%)`,
          inset: 0,
          position: 'absolute',
        }}
      />
      <div
        style={{
          color: lineColor,
          fontSize: 20,
          fontWeight: 700,
          left: width * 0.1,
          letterSpacing: 5,
          opacity: contentOpacity,
          position: 'absolute',
          textTransform: 'uppercase',
          top: height * 0.1,
        }}
      >
        BLUEPRINT // DATA SYSTEM
      </div>
      <svg
        height="100%"
        style={{ inset: 0, overflow: 'visible', position: 'absolute' }}
        viewBox={`0 0 ${width} ${height}`}
        width="100%"
      >
        <PanelFrame
          accentColor={lineColor}
          height={mainPanel.height}
          label="PRIMARY READOUT"
          opacity={revealOpacity}
          width={mainPanel.width}
          x={mainPanel.x}
          y={mainPanel.y}
        />
        {keywords?.length ? (
          <PanelFrame
            accentColor={lineColor}
            height={sidePanel.height}
            label="KEYWORDS"
            opacity={revealOpacity}
            width={sidePanel.width}
            x={sidePanel.x}
            y={sidePanel.y}
          />
        ) : null}
      </svg>
      <div
        style={{
          left: mainPanel.x + 28,
          maxWidth: mainPanel.width - 56,
          opacity: contentOpacity,
          position: 'absolute',
          top: mainPanel.y + 92,
        }}
      >
        <div
          style={{
            color: lineColor,
            fontSize: Math.min(width * 0.105, 170),
            fontWeight: 800,
            letterSpacing: -3,
            lineHeight: 0.95,
            textShadow: `0 0 22px ${getRgba(lineColor, 0.5)}`,
          }}
        >
          {data.value}
        </div>
        {data.context ? (
          <div
            style={{
              color: '#d5e8ce',
              fontSize: Math.min(width * 0.024, 42),
              lineHeight: 1.2,
              marginTop: 28,
              maxWidth: mainPanel.width * 0.82,
            }}
          >
            {data.context}
          </div>
        ) : null}
      </div>
      {keywords?.length ? (
        <div
          style={{
            color: '#d5e8ce',
            fontSize: 20,
            left: sidePanel.x + 28,
            lineHeight: 1.65,
            maxWidth: sidePanel.width - 56,
            opacity: contentOpacity,
            position: 'absolute',
            top: sidePanel.y + 76,
          }}
        >
          {keywords.slice(0, 3).map((keyword) => (
            <div key={keyword} style={{ whiteSpace: 'nowrap' }}>
              <span style={{ color: lineColor }}>+</span> {keyword.toUpperCase()}
            </div>
          ))}
        </div>
      ) : null}
      <div
        style={{
          bottom: height * 0.1,
          color: getRgba(lineColor, 0.72),
          fontSize: 18,
          left: width * 0.1,
          letterSpacing: 2,
          opacity: contentOpacity,
          position: 'absolute',
          textTransform: 'uppercase',
        }}
      >
        {keywordText}
      </div>
    </AbsoluteFill>
  );
};

export default BlueprintDataPanel;
