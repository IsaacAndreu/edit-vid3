import type { CSSProperties, FC } from 'react';
import { AbsoluteFill, Img, OffthreadVideo, interpolate, staticFile, useCurrentFrame } from 'remotion';
import type { Media } from '../types';

const cover: CSSProperties = { width: '100%', height: '100%', objectFit: 'cover' };

// Deterministic per-shot variation of the Ken Burns move (zoom in/out, pan direction).
const hash = (text: string): number => [...text].reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 7);

const KenBurns: FC<{ src: string; durationInFrames: number; seed: string }> = ({ src, durationInFrames, seed }) => {
  const frame = useCurrentFrame();
  const h = hash(seed);
  const zoomIn = h % 2 === 0;
  const progress = interpolate(frame, [0, Math.max(1, durationInFrames)], [0, 1], { extrapolateRight: 'clamp' });
  const scale = zoomIn ? 1.0 + 0.08 * progress : 1.08 - 0.08 * progress;
  const dx = ((h >> 3) % 3) - 1; // -1, 0, 1
  const dy = ((h >> 5) % 3) - 1;
  return (
    <AbsoluteFill style={{ overflow: 'hidden' }}>
      <Img
        src={staticFile(src)}
        style={{ ...cover, transform: `scale(${scale}) translate(${dx * 1.5 * progress}%, ${dy * 1.0 * progress}%)` }}
      />
    </AbsoluteFill>
  );
};

/** Full-bleed footage: third-party video (muted, never looped) or a still with a slow Ken Burns move. */
export const BRoll: FC<{ media: Media; durationInFrames: number; seed: string; dim?: number }> = ({
  media,
  durationInFrames,
  seed,
  dim = 0,
}) => (
  <AbsoluteFill style={{ backgroundColor: '#000' }}>
    {media.kind === 'video' ? (
      <OffthreadVideo src={staticFile(media.src)} muted style={cover} />
    ) : (
      <KenBurns src={media.src} durationInFrames={durationInFrames} seed={seed} />
    )}
    {dim > 0 ? <AbsoluteFill style={{ backgroundColor: `rgba(0,0,0,${dim})` }} /> : null}
  </AbsoluteFill>
);
