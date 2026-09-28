import type { FC } from 'react';
import { AbsoluteFill, Img, staticFile } from 'remotion';
import { fontFamily } from '../theme';
import { GridBackground } from './GridBackground';

export interface ThumbnailVariant {
  text: string; // 2-5 words, the big line
  background?: string | null; // peak-moment frame, darkened
  cutout?: string | null; // the protagonist without background
  accent: string; // colour of the highlighted word and the bar
  flip?: boolean; // cutout on the left, text on the right
}

/**
 * YouTube thumbnail (1280x720): the peak moment as a dark backdrop, the protagonist cut out big
 * on one side and a short, huge line on the other with its last word in the accent colour.
 */
export const Thumbnail: FC<{ variant: ThumbnailVariant }> = ({ variant }) => {
  const words = variant.text.trim().toUpperCase().split(/\s+/);
  const last = words.pop() ?? '';
  const size = variant.text.length > 22 ? 96 : variant.text.length > 14 ? 118 : 140;
  const side = variant.flip ? 'flex-start' : 'flex-end';
  return (
    <AbsoluteFill>
      <GridBackground />
      {variant.background ? (
        <AbsoluteFill>
          <Img src={staticFile(variant.background)} style={{ width: '100%', height: '100%', objectFit: 'cover', filter: 'saturate(1.2) contrast(1.1)' }} />
          <AbsoluteFill
            style={{
              background: `linear-gradient(${variant.flip ? 270 : 90}deg, rgba(0,0,0,0.88) 0%, rgba(0,0,0,0.55) 50%, rgba(0,0,0,0.15) 100%)`,
            }}
          />
        </AbsoluteFill>
      ) : null}
      {variant.cutout ? (
        <AbsoluteFill style={{ justifyContent: 'flex-end', alignItems: side, padding: variant.flip ? '0 0 0 40px' : '0 40px 0 0' }}>
          <Img
            src={staticFile(variant.cutout)}
            style={{ height: 760, marginBottom: -60, filter: `drop-shadow(0 0 28px ${variant.accent}) drop-shadow(0 20px 40px rgba(0,0,0,0.8))` }}
          />
        </AbsoluteFill>
      ) : null}
      <AbsoluteFill style={{ justifyContent: 'center', alignItems: variant.flip ? 'flex-end' : 'flex-start', padding: '0 60px' }}>
        <div style={{ display: 'flex', gap: 18, maxWidth: 720, flexDirection: variant.flip ? 'row-reverse' : 'row' }}>
          <div style={{ width: 14, backgroundColor: variant.accent }} />
          <div
            style={{
              fontFamily,
              fontWeight: 900,
              fontSize: size,
              lineHeight: 0.95,
              color: '#fff',
              letterSpacing: '-0.02em',
              textAlign: variant.flip ? 'right' : 'left',
              textShadow: '0 6px 24px rgba(0,0,0,0.9)',
            }}
          >
            {words.join(' ')} <span style={{ color: variant.accent }}>{last}</span>
          </div>
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
