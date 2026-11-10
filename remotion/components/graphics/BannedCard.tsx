import type { FC } from 'react';
import { AbsoluteFill, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { fontFamily, theme } from '../../theme';
import type { BannedGraphic } from '../../graphics';
import { GridBackground } from '../GridBackground';
import { MediaBox } from './MediaBox';
import { STAMP_RED, Stamp, stampShake } from './Stamp';

const BANNED_STAMP = 22; // keep in sync with pipeline/timeline.py

/** A banned element: its clip in a big frame, the stamp slamming over it, then name, who made it
 * famous, why it was banned and since when. */
export const BannedCard: FC<{ graphic: BannedGraphic; durationInFrames: number }> = ({ graphic, durationInFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enter = spring({ frame, fps, config: { damping: 200, stiffness: 120 } });
  const text = (at: number) => spring({ frame: frame - at, fps, config: { damping: 200, stiffness: 140 } });
  const line = (at: number) => ({ opacity: text(at), transform: `translateY(${(1 - text(at)) * 24}px)` });
  return (
    <AbsoluteFill style={{ fontFamily }}>
      <GridBackground />
      <div
        style={{
          position: 'absolute',
          left: 100,
          top: 170,
          opacity: enter,
          transform: `translateX(${(1 - enter) * -80}px) ${stampShake(frame, BANNED_STAMP)}`,
        }}
      >
        <MediaBox media={graphic.media} width={1000} height={680} durationInFrames={durationInFrames} style={{ borderColor: STAMP_RED }} />
        <Stamp text={graphic.stamp} at={BANNED_STAMP} size={110} style={{ left: 150, top: 260 }} />
      </div>
      <div style={{ position: 'absolute', left: 1190, top: 200, width: 640 }}>
        {graphic.number ? (
          <div style={{ ...line(4), fontWeight: 900, fontSize: 110, color: theme.accent, lineHeight: 1 }}>#{graphic.number}</div>
        ) : null}
        <div style={{ ...line(8), fontWeight: 900, fontSize: 80, color: theme.text, lineHeight: 1.02, marginTop: 10 }}>
          {graphic.name.toUpperCase()}
        </div>
        {graphic.who ? <div style={{ ...line(14), fontWeight: 600, fontSize: 42, color: theme.accent, marginTop: 18 }}>{graphic.who}</div> : null}
        {graphic.reason ? (
          <div style={{ ...line(BANNED_STAMP + 8), fontWeight: 500, fontSize: 38, color: theme.muted, marginTop: 30, lineHeight: 1.3 }}>
            {graphic.reason}
          </div>
        ) : null}
        {graphic.since ? (
          <div
            style={{
              ...line(BANNED_STAMP + 14),
              display: 'inline-block',
              marginTop: 34,
              padding: '10px 24px',
              fontWeight: 900,
              fontSize: 40,
              letterSpacing: 2,
              color: 'white',
              backgroundColor: STAMP_RED,
            }}
          >
            {graphic.since.toUpperCase()}
          </div>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};
