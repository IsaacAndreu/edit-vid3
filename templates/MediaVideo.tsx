import type { CSSProperties, FC } from 'react';
import { Loop, OffthreadVideo, Video, getRemotionEnvironment, useVideoConfig } from 'remotion';
import { resolveMediaUrl } from './media';

const REMOTE_URL_PATTERN = /^https?:/i;

type MediaVideoProps = {
  /** Path under public/ or a remote URL, exactly as it comes in the props. */
  url: string;
  /** Stock footage loops; third-party clips play once and hold their last frame. */
  loop: boolean;
  /** Real duration of the file. Needed to loop frame-accurately while rendering. */
  durationInSeconds?: number;
  style?: CSSProperties;
};

/**
 * Silent background/shot video.
 *
 * While rendering, local files are decoded with <OffthreadVideo>, which extracts
 * exact frames with FFmpeg instead of seeking an HTML5 video in every browser tab.
 * In the Studio preview, and for remote URLs, the regular <Video> is used.
 */
export const MediaVideo: FC<MediaVideoProps> = ({ durationInSeconds, loop, style, url }) => {
  const { fps } = useVideoConfig();
  const src = resolveMediaUrl(url);
  const offthread = getRemotionEnvironment().isRendering && !REMOTE_URL_PATTERN.test(url);

  if (!offthread) {
    return <Video loop={loop} muted src={src} style={style} />;
  }

  if (!loop) {
    return <OffthreadVideo muted src={src} style={style} />;
  }

  // One frame of margin: container durations are often rounded up.
  const loopFrames = durationInSeconds ? Math.floor(durationInSeconds * fps) - 1 : 0;
  if (loopFrames < 1) {
    return <Video loop muted src={src} style={style} />;
  }

  return (
    <Loop durationInFrames={loopFrames} layout="none">
      <OffthreadVideo muted src={src} style={style} />
    </Loop>
  );
};
