import type { FC } from 'react';
import { AbsoluteFill, Img, interpolate, staticFile, useCurrentFrame } from 'remotion';
import { theme } from '../theme';
import type { Media } from '../types';

const hash = (text: string): number => [...text].reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 7);

/** A still with depth: the same photo blurred and enlarged behind, drifting one way, and the photo
 * framed in front, drifting the other way while it slowly grows. */
export const ParallaxPhoto: FC<{ media: Media; durationInFrames: number; seed: string }> = ({ media, durationInFrames, seed }) =>
  media.cutout ? <DepthPhoto media={media} durationInFrames={durationInFrames} seed={seed} /> : <FramedParallax media={media} durationInFrames={durationInFrames} seed={seed} />;

/** «2.5D»: the photo fills the frame and drifts slowly, a little softer and darker behind; its subject, cut out,
 * comes forward at its own pace (grows more, drifts the other way), so the picture opens up in depth. */
const DepthPhoto: FC<{ media: Media; durationInFrames: number; seed: string }> = ({ media, durationInFrames, seed }) => {
  const frame = useCurrentFrame();
  const dir = hash(seed) % 2 === 0 ? 1 : -1;
  const p = interpolate(frame, [0, Math.max(1, durationInFrames)], [0, 1], { extrapolateRight: 'clamp' });
  const ease = 1 - (1 - p) * (1 - p) * 0.35 - 0.65 * (1 - p);   // mostly linear, a touch of ease-out
  const layer = { position: 'absolute' as const, inset: 0, width: '100%', height: '100%', objectFit: 'cover' as const };
  return (
    <AbsoluteFill style={{ backgroundColor: '#000', overflow: 'hidden' }}>
      <Img
        src={staticFile((media.cutout as string).replace(/\.png$/, '-plate.jpg'))}
        style={{ ...layer, filter: 'blur(2px) brightness(0.78) saturate(1.05)',
          transform: `translateX(${dir * 36 * ease}px) scale(${1.1 + 0.03 * ease})` }}
      />
      {/* the cut-out's shadow: its own silhouette, black and blurred, drawn at a quarter of the size (a drop-shadow
          over the whole frame each frame was the dear part) */}
      <div style={{ position: 'absolute', left: 0, top: 18, width: 1920 / 4, height: 1080 / 4, transformOrigin: '0 0',
                    transform: `scale(4) translateX(${(dir * -30 * ease) / 4}px)`, opacity: 0.55 }}>
        <Img src={staticFile(media.cutout as string)}
             style={{ ...layer, filter: 'brightness(0) blur(7px)', transform: `scale(${1.12 + 0.1 * ease})`, transformOrigin: '50% 70%' }} />
      </div>
      <Img
        src={staticFile(media.cutout as string)}
        style={{ ...layer, transform: `translateX(${dir * -30 * ease}px) scale(${1.12 + 0.1 * ease})`, transformOrigin: '50% 70%' }}
      />
    </AbsoluteFill>
  );
};

const FramedParallax: FC<{ media: Media; durationInFrames: number; seed: string }> = ({ media, durationInFrames, seed }) => {
  const frame = useCurrentFrame();
  const dir = hash(seed) % 2 === 0 ? 1 : -1;
  const p = interpolate(frame, [0, Math.max(1, durationInFrames)], [0, 1], { extrapolateRight: 'clamp' });
  const src = staticFile(media.src);
  return (
    <AbsoluteFill style={{ backgroundColor: '#000', overflow: 'hidden' }}>
      {/* the blurred backdrop drawn at an eighth of the size and scaled up: a 28 px blur over 2 million pixels each
          frame was the dearest thing in a photo shot on a server without a GPU; at 1/8 it is 3.5 px over 35 000 */}
      <div style={{ position: 'absolute', left: -80, top: -80, width: (1920 + 160) / 8, height: (1080 + 160) / 8, overflow: 'hidden',
                    transformOrigin: '0 0', transform: `translateX(${dir * -60 * p}px) scale(${8 * (1.1 + 0.05 * p)})` }}>
        <Img src={src} style={{ width: '100%', height: '100%', objectFit: 'cover', filter: 'blur(3.5px) brightness(0.45) saturate(1.2)' }} />
      </div>
      <AbsoluteFill style={{ justifyContent: 'center', alignItems: 'center' }}>
        <div
          style={{
            height: '78%',
            aspectRatio: media.width && media.height ? `${media.width} / ${media.height}` : '16 / 9',
            maxWidth: '82%',
            overflow: 'hidden',
            borderRadius: 14,
            border: `4px solid ${theme.accent}`,
            boxShadow: '0 22px 40px rgba(0,0,0,0.6)',
            transform: `translateX(${dir * 40 * p}px) scale(${1 + 0.06 * p})`,
          }}
        >
          <Img src={src} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
