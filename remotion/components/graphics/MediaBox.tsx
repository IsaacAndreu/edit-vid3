import type { CSSProperties, FC } from 'react';
import { Img, OffthreadVideo, interpolate, staticFile, useCurrentFrame } from 'remotion';
import { theme } from '../../theme';
import type { Media } from '../../types';

/** A photo (slow zoom) or a muted clip in a framed box with the accent border. */
export const MediaBox: FC<{ media?: Media | null; width: number; height: number; durationInFrames: number; style?: CSSProperties }> = ({
  media,
  width,
  height,
  durationInFrames,
  style,
}) => {
  const frame = useCurrentFrame();
  const zoom = interpolate(frame, [0, durationInFrames], [1.0, 1.08], { extrapolateRight: 'clamp' });
  const fill: CSSProperties = { width: '100%', height: '100%', objectFit: 'cover', transform: `scale(${zoom})` };
  return (
    <div
      style={{
        width,
        height,
        overflow: 'hidden',
        borderRadius: 16,
        border: `4px solid ${theme.accent}`,
        backgroundColor: '#111',
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
