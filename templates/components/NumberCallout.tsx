import type { CSSProperties, FC } from 'react';
import { AbsoluteFill, Img, Video, interpolate, spring, useVideoConfig, useCurrentFrame } from 'remotion';
import type { SceneProps } from '../types';
import { resolveMediaUrl } from '../media';

const POP_IN_DURATION_IN_FRAMES = 14;

const containerStyle: CSSProperties = {
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

type ParsedCallout = {
  label: string;
  value: string;
};

const parseCalloutText = (text: string | undefined): ParsedCallout => {
  const normalizedText = text?.trim() ?? '';
  const rangeMatch = normalizedText.match(
    /([+-]?\d[\d.,]*\s*[%€$£]?)\s+(?:y|a|hasta)(?:\s+(?:el|la))?\s+([+-]?\d[\d.,]*\s*[%€$£]?)/i,
  );

  if (rangeMatch) {
    return {
      label: normalizedText
        .replace(rangeMatch[0], '')
        .replace(/^\s*[-—:|,]+\s*|\s*[-—:|,]+\s*$/g, '')
        .replace(/\s{2,}/g, ' ')
        .trim(),
      value: `${rangeMatch[1].trim()}–${rangeMatch[2].trim()}`,
    };
  }

  const valueMatch = normalizedText.match(/[+-]?\d[\d.,]*(?:\s*[-–—]\s*[+-]?\d[\d.,]*)?(?:\s*[%€$£])?/);

  if (!valueMatch) {
    return {
      label: normalizedText,
      value: '',
    };
  }

  return {
    label: normalizedText
      .replace(valueMatch[0], '')
      .replace(/^\s*[-—:|,]+\s*|\s*[-—:|,]+\s*$/g, '')
      .replace(/\s{2,}/g, ' ')
      .trim(),
    value: valueMatch[0].trim(),
  };
};

type BackgroundProps = {
  imageUrl?: string;
  mediaProvider?: string;
  videoUrl?: string;
};

const Background: FC<BackgroundProps> = ({ imageUrl, mediaProvider, videoUrl }) => {
  if (videoUrl) {
    return <Video loop={mediaProvider !== 'youtube'} src={resolveMediaUrl(videoUrl)} muted style={mediaStyle} />;
  }

  if (imageUrl) {
    return <Img src={resolveMediaUrl(imageUrl)} style={mediaStyle} />;
  }

  return null;
};

const NumberCallout: FC<SceneProps> = ({ accentColor, imageUrl, mediaProvider, text, videoUrl }) => {
  const frame = useCurrentFrame();
  const { fps, width } = useVideoConfig();
  const lineColor = accentColor || '#f6c945';
  const callout = parseCalloutText(text);
  const entryProgress = spring({
    frame,
    fps,
    config: {
      damping: 14,
      mass: 0.55,
      stiffness: 180,
    },
    durationInFrames: POP_IN_DURATION_IN_FRAMES,
  });
  const scale = interpolate(entryProgress, [0, 1], [0.72, 1]);
  const translateY = interpolate(entryProgress, [0, 1], [28, 0]);
  const calloutWidth = Math.min(width * 0.25, 500);

  return (
    <AbsoluteFill style={containerStyle}>
      <AbsoluteFill>
        <Background imageUrl={imageUrl} mediaProvider={mediaProvider} videoUrl={videoUrl} />
      </AbsoluteFill>
      <div
        style={{
          background: 'linear-gradient(90deg, transparent 48%, rgba(0, 0, 0, 0.12) 100%)',
          inset: 0,
          pointerEvents: 'none',
          position: 'absolute',
        }}
      />
      <div
        style={{
          bottom: '11%',
          opacity: entryProgress,
          position: 'absolute',
          right: '8%',
          transform: `translateY(${translateY}px) scale(${scale})`,
          transformOrigin: 'bottom right',
          width: calloutWidth,
        }}
      >
        <div
          style={{
            alignItems: 'flex-start',
            backgroundColor: 'rgba(7, 10, 15, 0.86)',
            border: '1px solid rgba(255, 255, 255, 0.24)',
            borderLeft: `8px solid ${lineColor}`,
            borderRadius: 10,
            boxShadow: '0 12px 32px rgba(0, 0, 0, 0.28)',
            boxSizing: 'border-box',
            display: 'flex',
            flexDirection: 'column',
            padding: '24px 30px 26px',
            position: 'relative',
          }}
        >
          {callout.value ? (
            <div
              style={{
                color: lineColor,
                fontFamily: 'Inter, Arial, sans-serif',
                fontSize: Math.min(width * 0.043, callout.value.length > 8 ? 64 : 82),
                fontWeight: 900,
                letterSpacing: '-0.055em',
                lineHeight: 0.98,
                maxWidth: '100%',
                overflowWrap: 'anywhere',
              }}
            >
              {callout.value}
            </div>
          ) : null}
          {callout.label ? (
            <div
              style={{
                color: '#ffffff',
                display: '-webkit-box',
                fontFamily: 'Inter, Arial, sans-serif',
                fontSize: callout.value ? Math.min(width * 0.014, 26) : Math.min(width * 0.021, 38),
                fontWeight: callout.value ? 600 : 750,
                lineHeight: 1.16,
                marginTop: callout.value ? 12 : 0,
                maxHeight: callout.value ? 66 : 132,
                overflow: 'hidden',
                WebkitBoxOrient: 'vertical',
                WebkitLineClamp: callout.value ? 2 : 3,
              }}
            >
              {callout.label}
            </div>
          ) : null}
        </div>
      </div>
    </AbsoluteFill>
  );
};

export default NumberCallout;
