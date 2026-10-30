import type { FC } from 'react';
import { AbsoluteFill, random, useCurrentFrame } from 'remotion';

// Fine noise as an SVG data URI, moved to a new random offset every frame (as in ArchiveFootage, finer).
const GRAIN =
  "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='256' height='256'>" +
  "<filter id='g'><feTurbulence type='fractalNoise' baseFrequency='1.1' numOctaves='2' stitchTiles='stitch'/>" +
  "<feColorMatrix values='0 0 0 0 0.5  0 0 0 0 0.5  0 0 0 0 0.5  0 0 0 0.85 0'/></filter>" +
  "<rect width='100%' height='100%' filter='url(%23g)'/></svg>\")";

/**
 * The film finish over the whole video (brand.finish: cine): grain that moves every frame, a vignette, a breath of
 * flicker and, a few times a minute, a speck of dust or a hairline scratch for a handful of frames. Light enough
 * that footage, graphics and text read as before — it only takes the digital edge off.
 */
export const FilmFinish: FC = () => {
  const frame = useCurrentFrame();
  const gx = Math.floor(random(`fx-${frame}`) * 256);
  const gy = Math.floor(random(`fy-${frame}`) * 256);
  const flicker = (random(`fl-${Math.floor(frame / 2)}`) - 0.5) * 0.035;
  // dust and scratches: each lasts 3-6 frames, decided per 6-frame window
  const window = Math.floor(frame / 6);
  const dust = random(`dust-${window}`) < 0.08;
  const scratch = random(`scr-${window}`) < 0.04;
  return (
    <AbsoluteFill style={{ pointerEvents: 'none' }}>
      <AbsoluteFill style={{ backgroundImage: GRAIN, backgroundPosition: `${gx}px ${gy}px`, opacity: 0.11, mixBlendMode: 'overlay' }} />
      <AbsoluteFill
        style={{
          background: 'radial-gradient(ellipse at 50% 48%, rgba(0,0,0,0) 52%, rgba(0,0,0,0.38) 88%, rgba(0,0,0,0.6) 100%)',
        }}
      />
      <AbsoluteFill style={{ backgroundColor: flicker > 0 ? '#fff' : '#000', opacity: Math.abs(flicker) }} />
      {dust ? (
        <svg width={1920} height={1080} style={{ position: 'absolute', opacity: 0.55 }}>
          {Array.from({ length: 3 }, (_, i) => (
            <ellipse
              key={i}
              cx={random(`dx-${window}-${i}`) * 1920}
              cy={random(`dy-${window}-${i}`) * 1080}
              rx={1.5 + random(`dr-${window}-${i}`) * 3}
              ry={1 + random(`ds-${window}-${i}`) * 2}
              fill={i % 2 ? '#111' : '#eee'}
            />
          ))}
        </svg>
      ) : null}
      {scratch ? (
        <div
          style={{
            position: 'absolute', top: 0, bottom: 0, width: 1.5, left: 200 + random(`sx-${window}`) * 1520,
            background: 'linear-gradient(180deg, rgba(255,255,255,0) 0%, rgba(255,255,255,0.35) 30%, rgba(255,255,255,0.2) 80%, rgba(255,255,255,0) 100%)',
          }}
        />
      ) : null}
    </AbsoluteFill>
  );
};
