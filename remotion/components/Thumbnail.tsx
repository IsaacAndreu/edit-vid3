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
  poster?: boolean; // poster style: the cutout in black and white on a red sun, a red bar over the eyes
  focus?: [number, number] | null; // poster style: centre of the face in the cutout (% of width, % of height)
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
  variant.image ? (
    <ConceptThumbnail variant={variant} />
  ) : variant.poster && variant.cutout ? (
    <PosterThumbnail variant={variant} />
  ) : (
    <FrameThumbnail variant={variant} />
  );

/** Poster thumbnail (like the poster graphic): black night, a big red sun, the protagonist cut out in black and
 * white with a red bar over the eyes, and the words huge in white, the last one in red, beside them. */
const PosterThumbnail: FC<{ variant: ThumbnailVariant }> = ({ variant }) => {
  const words = variant.text.trim().toUpperCase().split(/\s+/);
  const last = words.pop() ?? '';
  const size = variant.text.length > 20 ? 92 : variant.text.length > 12 ? 112 : 136;
  const focus = variant.focus;
  const left = variant.flip;
  return (
    <AbsoluteFill style={{ backgroundColor: '#050505', overflow: 'hidden' }}>
      <svg width="1280" height="720" style={{ position: 'absolute', inset: 0 }}>
        {Array.from({ length: 90 }, (_, i) => {
          const r = (k: number) => { const x = Math.sin((i + k) * 12.9898) * 43758.5453; return x - Math.floor(x); };
          return <circle key={i} cx={r(1) * 1280} cy={r(2) * 720} r={0.5 + r(3) * 1.2} fill="#fff" opacity={0.15 + r(4) * 0.45} />;
        })}
      </svg>
      <div style={{ position: 'absolute', left: left ? 760 : 90, top: 70, width: 470, height: 470, borderRadius: '50%',
        background: 'radial-gradient(circle at 45% 40%, #ea2a30 0%, #d4161c 55%, #a50f14 100%)', boxShadow: '0 0 70px rgba(212,22,28,0.6)' }} />
      <div style={{ position: 'absolute', left: left ? 995 : 325, bottom: 0, height: 640, transform: 'translateX(-50%)' }}>
        <div style={{ position: 'relative', height: '100%' }}>
          <Img src={staticFile(variant.cutout as string)} style={{ height: '100%', width: 'auto', display: 'block', filter: 'grayscale(1) contrast(1.2)' }} />
          {focus ? (
            <div style={{ position: 'absolute', left: `${focus[0] - 15}%`, width: '30%', top: `${focus[1] - 4.5}%`, height: '5.5%',
              background: '#d4161c', boxShadow: '0 0 10px rgba(212,22,28,0.7)' }} />
          ) : null}
        </div>
      </div>
      <div style={{ position: 'absolute', left: -100, right: -100, bottom: -170, height: 300, borderRadius: '50%',
        background: 'radial-gradient(ellipse at 50% 40%, rgba(235,235,235,0.75) 0%, rgba(150,150,150,0.3) 45%, rgba(0,0,0,0) 70%)', filter: 'blur(14px)' }} />
      <AbsoluteFill style={{ justifyContent: 'center', alignItems: left ? 'flex-start' : 'flex-end', padding: '0 60px' }}>
        <div style={{ maxWidth: 640, fontFamily: "'Poppins', 'Inter'", fontWeight: 700, fontSize: size, lineHeight: 0.98, color: '#fff',
          letterSpacing: '-0.02em', textAlign: left ? 'left' : 'right', textShadow: '0 6px 24px rgba(0,0,0,0.9)' }}>
          {words.join(' ')} <span style={{ color: '#ff2a30' }}>{last}</span>
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

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
