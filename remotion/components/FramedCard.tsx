import type { FC } from 'react';
import { AbsoluteFill, Img, OffthreadVideo, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';
import type { Media } from '../types';
import { GridBackground } from './GridBackground';

const MAX_W = 1480;
const MAX_H = 830;

/**
 * Footage or a photo as a framed card over the channel background, keeping the source frame
 * (vertical and 4:3 clips are not cropped). Pops in, then pushes in slowly for the whole shot.
 */
export const FramedCard: FC<{ media: Media; durationInFrames: number }> = ({ media, durationInFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const aspect = media.width && media.height ? media.width / media.height : 16 / 9;
  const width = aspect >= MAX_W / MAX_H ? MAX_W : Math.round(MAX_H * aspect);
  const height = aspect >= MAX_W / MAX_H ? Math.round(MAX_W / aspect) : MAX_H;
  const enter = spring({ frame, fps, config: { damping: 200, stiffness: 220 }, durationInFrames: 8 });
  const push = interpolate(frame, [0, Math.max(1, durationInFrames)], [1, 1.035]);
  const style = { width: '100%', height: '100%', objectFit: 'cover' as const };
  return (
    <AbsoluteFill>
      <GridBackground />
      <AbsoluteFill style={{ justifyContent: 'center', alignItems: 'center' }}>
        <div
          style={{
            width,
            height,
            marginTop: -24,
            border: '5px solid rgba(255,255,255,0.92)',
            boxShadow: '0 30px 90px rgba(0,0,0,0.75)',
            overflow: 'hidden',
            backgroundColor: '#000',
            opacity: enter,
            transform: `scale(${interpolate(enter, [0, 1], [0.94, 1]) * push})`,
          }}
        >
          {media.kind === 'video' ? (
            <OffthreadVideo src={staticFile(media.src)} muted playbackRate={media.rate || 1} style={style} />
          ) : (
            <Img src={staticFile(media.src)} style={style} />
          )}
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
