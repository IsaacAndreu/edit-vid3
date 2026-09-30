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
  image?: string | null; // concept style: one generated picture with a single idea
  side?: 'left' | 'right'; // concept style: where the picture left room for the label
}

/** Black or white, whichever reads better on `color`. */
const ink = (color: string): string => {
  const n = parseInt(color.replace('#', '').padEnd(6, '0').slice(0, 6), 16);
  const [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  return 0.299 * r + 0.587 * g + 0.114 * b > 150 ? '#0b0b0b' : '#ffffff';
};

/** Concept thumbnail: the picture carries the idea; 0-4 words on a brand-colour label, qash style. */
const ConceptThumbnail: FC<{ variant: ThumbnailVariant }> = ({ variant }) => {
  const words = variant.text.trim().toUpperCase();
  const size = words.length > 16 ? 76 : words.length > 9 ? 92 : 112;
  return (
    <AbsoluteFill style={{ backgroundColor: '#111' }}>
      <Img src={staticFile(variant.image as string)} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
      {words ? (
        <AbsoluteFill
          style={{ justifyContent: 'center', alignItems: variant.side === 'left' ? 'flex-start' : 'flex-end', padding: '0 56px' }}
        >
          <div
            style={{
              maxWidth: 520, fontFamily, fontWeight: 900, fontSize: size, lineHeight: 1.02, letterSpacing: '-0.02em',
              color: ink(variant.accent), backgroundColor: variant.accent, padding: '14px 26px 18px',
              textAlign: variant.side === 'left' ? 'left' : 'right', boxShadow: '0 18px 40px rgba(0,0,0,0.45)',
              boxDecorationBreak: 'clone', WebkitBoxDecorationBreak: 'clone',
            }}
          >
            {words}
          </div>
        </AbsoluteFill>
      ) : null}
    </AbsoluteFill>
  );
};

/**
 * YouTube thumbnail (1280x720): the peak moment as a dark backdrop, the protagonist cut out big
 * on one side and a short, huge line on the other with its last word in the accent colour.
 */
export const Thumbnail: FC<{ variant: ThumbnailVariant }> = ({ variant }) =>
  variant.image ? <ConceptThumbnail variant={variant} /> : <FrameThumbnail variant={variant} />;

const FrameThumbnail: FC<{ variant: ThumbnailVariant }> = ({ variant }) => {
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
