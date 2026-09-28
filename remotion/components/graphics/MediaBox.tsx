import type { CSSProperties, FC } from 'react';
import { Img, OffthreadVideo, interpolate, staticFile, useCurrentFrame } from 'remotion';
import { theme } from '../../theme';
import type { Media } from '../../types';

/** A photo (slow zoom) or a muted clip in a framed box with the accent border. */
export const MediaBox: FC<{
  media?: Media | null;
  width: number;
  height: number;
  durationInFrames: number;
  style?: CSSProperties;
  face?: boolean; // avatar circle: head and shoulders, even from a full-body cutout
}> = ({ media, width, height, durationInFrames, style, face = false }) => {
  const frame = useCurrentFrame();
  const zoom = interpolate(frame, [0, durationInFrames], [1.0, 1.08], { extrapolateRight: 'clamp' });
  // A cutout (transparent PNG of a person) is shown whole, standing on the bottom edge; photos and
  // clips fill the box, cropped around the upper third where faces usually are.
  const cutout = media?.kind === 'image' && (media.layout === 'person' || media.src.toLowerCase().endsWith('.png'));
  const focus = media?.focus;
  const fill: CSSProperties = face
    ? focus
      ? {
          width: '100%',
          height: '100%',
          objectFit: 'cover',
          objectPosition: `${focus[0]}% ${focus[1]}%`,
          transform: `scale(${1.6 * zoom})`,
          transformOrigin: `${focus[0]}% ${focus[1]}%`,
        }
      : { width: '100%', height: '100%', objectFit: 'cover', objectPosition: 'center 8%', transform: `scale(${1.6 * zoom})`, transformOrigin: 'center 12%' }
    : focus && !cutout
      ? { width: '100%', height: '100%', objectFit: 'cover', objectPosition: `${focus[0]}% ${focus[1]}%`, transform: `scale(${zoom})` }
      : cutout
    ? { width: '100%', height: '100%', objectFit: 'contain', objectPosition: 'center bottom', transform: `scale(${zoom})`, transformOrigin: 'center bottom' }
    : { width: '100%', height: '100%', objectFit: 'cover', objectPosition: 'center 28%', transform: `scale(${zoom})` };
  return (
    <div
      style={{
        width,
        height,
        overflow: 'hidden',
        borderRadius: 16,
        border: `4px solid ${theme.accent}`,
        backgroundColor: cutout ? 'rgba(20,22,28,0.9)' : '#111',
        backgroundImage: cutout ? 'radial-gradient(ellipse at 50% 100%, rgba(255,212,0,0.22) 0%, rgba(0,0,0,0) 65%)' : undefined,
        boxShadow: '0 20px 60px rgba(0,0,0,0.6)',
        ...style,
      }}
    >
      {media ? (
        media.kind === 'video' ? (
          <OffthreadVideo src={staticFile(media.src)} muted style={fill} />
        ) : (
          <Img src={staticFile(media.src)} style={fill} />
        )
      ) : null}
    </div>
  );
};
