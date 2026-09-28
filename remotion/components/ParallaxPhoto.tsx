import type { FC } from 'react';
import { AbsoluteFill, Img, interpolate, staticFile, useCurrentFrame } from 'remotion';
import { theme } from '../theme';
import type { Media } from '../types';

const hash = (text: string): number => [...text].reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 7);

/** A still with depth: the same photo blurred and enlarged behind, drifting one way, and the photo
 * framed in front, drifting the other way while it slowly grows. */
export const ParallaxPhoto: FC<{ media: Media; durationInFrames: number; seed: string }> = ({ media, durationInFrames, seed }) => {
  const frame = useCurrentFrame();
  const dir = hash(seed) % 2 === 0 ? 1 : -1;
  const p = interpolate(frame, [0, Math.max(1, durationInFrames)], [0, 1], { extrapolateRight: 'clamp' });
  const src = staticFile(media.src);
  return (
    <AbsoluteFill style={{ backgroundColor: '#000', overflow: 'hidden' }}>
      <Img
        src={src}
        style={{
          position: 'absolute',
          inset: -80,
          width: 'calc(100% + 160px)',
          height: 'calc(100% + 160px)',
          objectFit: 'cover',
          filter: 'blur(28px) brightness(0.45) saturate(1.2)',
          transform: `translateX(${dir * -60 * p}px) scale(${1.1 + 0.05 * p})`,
        }}
      />
      <AbsoluteFill style={{ justifyContent: 'center', alignItems: 'center' }}>
        <div
          style={{
            height: '78%',
            aspectRatio: media.width && media.height ? `${media.width} / ${media.height}` : '16 / 9',
            maxWidth: '82%',
            overflow: 'hidden',
            borderRadius: 14,
            border: `4px solid ${theme.accent}`,
            boxShadow: '0 30px 80px rgba(0,0,0,0.7)',
            transform: `translateX(${dir * 40 * p}px) scale(${1 + 0.06 * p})`,
          }}
        >
          <Img src={src} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
