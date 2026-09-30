import type { FC } from 'react';
import { AbsoluteFill, OffthreadVideo, random, staticFile, useCurrentFrame } from 'remotion';
import type { Media } from '../types';

// Film grain: fine noise as an SVG data URI, moved to a new random offset every frame.
const GRAIN =
  "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='300' height='300'>" +
  "<filter id='g'><feTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/>" +
  "<feColorMatrix values='0 0 0 0 0.5  0 0 0 0 0.5  0 0 0 0 0.5  0 0 0 0.9 0'/></filter>" +
  "<rect width='100%' height='100%' filter='url(%23g)'/></svg>\")";

/**
 * Archive footage (layout "archive"): a 4:3 or other narrow clip kept whole between black side bars,
 * with a film look — warm, slightly faded colour, moving grain, a soft vignette and a hint of gate weave.
 */
export const ArchiveFootage: FC<{ media: Media; seed: string }> = ({ media, seed }) => {
  const frame = useCurrentFrame();
  const aspect = media.width && media.height ? media.width / media.height : 4 / 3;
  const width = Math.min(1920, Math.round(1080 * aspect));
  const weaveX = (random(`${seed}-x-${Math.floor(frame / 2)}`) - 0.5) * 2.2;
  const weaveY = (random(`${seed}-y-${Math.floor(frame / 2)}`) - 0.5) * 1.6;
  const grainX = Math.floor(random(`${seed}-gx-${frame}`) * 300);
  const grainY = Math.floor(random(`${seed}-gy-${frame}`) * 300);
  const flicker = 1 + (random(`${seed}-f-${frame}`) - 0.5) * 0.035;
  return (
    <AbsoluteFill style={{ backgroundColor: '#000', justifyContent: 'center', alignItems: 'center' }}>
      <div style={{ position: 'relative', width, height: 1080, overflow: 'hidden', transform: `translate(${weaveX}px, ${weaveY}px)` }}>
        <OffthreadVideo
          src={staticFile(media.src)}
          muted
          style={{
            width: '100%',
            height: '100%',
            objectFit: 'cover',
            filter: `sepia(0.22) saturate(0.88) contrast(1.06) brightness(${0.97 * flicker})`,
          }}
        />
        <AbsoluteFill style={{ backgroundImage: GRAIN, backgroundPosition: `${grainX}px ${grainY}px`, opacity: 0.16, mixBlendMode: 'overlay' }} />
        <AbsoluteFill style={{ background: 'radial-gradient(ellipse 75% 70% at 50% 50%, rgba(0,0,0,0) 60%, rgba(0,0,0,0.45) 100%)' }} />
      </div>
    </AbsoluteFill>
  );
};
