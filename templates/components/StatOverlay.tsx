import type { CSSProperties, FC } from 'react';
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import type { SceneProps } from '../types';

const COUNT_DURATION_IN_FRAMES = 36;
const PULSE_DURATION_IN_FRAMES = 8;

const containerStyle: CSSProperties = {
  alignItems: 'center',
  backgroundColor: 'transparent',
  display: 'flex',
  flexDirection: 'column',
  height: '100%',
  justifyContent: 'center',
  padding: '0 8%',
  textAlign: 'center',
  width: '100%',
};

const numberStyle: CSSProperties = {
  fontFamily: 'Inter, Arial, sans-serif',
  fontSize: 180,
  fontWeight: 900,
  letterSpacing: '-0.05em',
  lineHeight: 0.95,
};

const labelStyle: CSSProperties = {
  color: '#ffffff',
  display: '-webkit-box',
  fontFamily: 'Inter, Arial, sans-serif',
  fontSize: 42,
  fontWeight: 600,
  lineHeight: 1.15,
  maxHeight: 96,
  marginTop: 28,
  maxWidth: '80%',
  overflow: 'hidden',
  WebkitBoxOrient: 'vertical',
  WebkitLineClamp: 2,
};

type ParsedStat = {
  decimalPlaces: number;
  label: string;
  prefix: string;
  suffix: string;
  value: number;
};

const parseStatText = (text: string | undefined): ParsedStat => {
  const normalizedText = text?.trim() ?? '';
  const valueMatch = normalizedText.match(/[+-]?\d[\d.,]*(?:\s*[-–—]\s*[+-]?\d[\d.,]*)?(?:\s*[%€$£])?/);

  if (!valueMatch) {
    return {
      decimalPlaces: 0,
      label: normalizedText,
      prefix: '',
      suffix: '',
      value: 0,
    };
  }

  const rawValue = valueMatch[0].replace(/\s*[%€$£]\s*$/, '').trim();
  const label = normalizedText
    .replace(valueMatch[0], '')
    .replace(/^\s*[-—:|,]+\s*|\s*[-—:|,]+\s*$/g, '')
    .replace(/\s{2,}/g, ' ')
    .trim();
  const trailingText = normalizedText.slice(valueMatch.index! + valueMatch[0].length);
  const inlineSuffix = valueMatch[0].match(/[%€$£]\s*$/)?.[0].trim() ?? '';
  const lastDot = rawValue.lastIndexOf('.');
  const lastComma = rawValue.lastIndexOf(',');
  const decimalSeparator = lastComma > lastDot ? ',' : '.';
  const separatorIndex = Math.max(lastDot, lastComma);
  const digitsAfterSeparator = separatorIndex === -1 ? 0 : rawValue.length - separatorIndex - 1;
  const hasDecimalPart = separatorIndex !== -1 && digitsAfterSeparator > 0 && digitsAfterSeparator < 3;
  const decimalPlaces = hasDecimalPart ? digitsAfterSeparator : 0;
  const normalizedValue = hasDecimalPart
    ? rawValue
        .replace(decimalSeparator === ',' ? /\./g : /,/g, '')
        .replace(decimalSeparator, '.')
    : rawValue.replace(/[.,]/g, '');
  const value = Number(normalizedValue);
  const trailingMatch = trailingText.match(/^(\s*[%A-Za-z€$£]*)/);

  return {
    decimalPlaces,
    label,
    prefix: '',
    suffix: inlineSuffix || trailingMatch?.[1].trim() || '',
    value: Number.isFinite(value) ? value : 0,
  };
};

const formatValue = (value: number, decimalPlaces: number): string =>
  value.toLocaleString('en-US', {
    maximumFractionDigits: decimalPlaces,
    minimumFractionDigits: decimalPlaces,
  });

const StatOverlay: FC<SceneProps> = ({ text, accentColor }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const stat = parseStatText(text);
  const introProgress = spring({
    frame,
    fps,
    config: {
      damping: 22,
      mass: 0.7,
      stiffness: 170,
    },
    durationInFrames: 18,
  });
  const animatedValue = interpolate(
    frame,
    [0, COUNT_DURATION_IN_FRAMES],
    [0, stat.value],
    {
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
    },
  );
  const pulseScale = interpolate(
    frame,
    [COUNT_DURATION_IN_FRAMES, COUNT_DURATION_IN_FRAMES + PULSE_DURATION_IN_FRAMES / 2, COUNT_DURATION_IN_FRAMES + PULSE_DURATION_IN_FRAMES],
    [1, 1.06, 1],
    {
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
    },
  );

  return (
    <AbsoluteFill style={containerStyle}>
      <div
        style={{
          ...numberStyle,
          color: accentColor,
          opacity: introProgress,
          transform: `scale(${interpolate(introProgress, [0, 1], [0.84, 1]) * pulseScale})`,
        }}
      >
        {stat.prefix}
        {formatValue(animatedValue, stat.decimalPlaces)}
        {stat.suffix}
      </div>
      {stat.label ? <div style={{ ...labelStyle, opacity: introProgress }}>{stat.label}</div> : null}
    </AbsoluteFill>
  );
};

export default StatOverlay;
