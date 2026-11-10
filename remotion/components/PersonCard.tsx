import type { FC } from 'react';
import { AbsoluteFill, Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';
import { fontFamily, theme } from '../theme';
import type { Media } from '../types';
import { GridBackground } from './GridBackground';

/**
 * Presentation card the first time the narration names someone: the person cut out (no background)
 * over the channel grid with a warm glow, sliding in from the right, and the name big on the left
 * (first name white, surname yellow). The cutout keeps its own credit in the badge.
 */
export const PersonCard: FC<{ media: Media; durationInFrames: number }> = ({ media, durationInFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enter = spring({ frame, fps, config: { damping: 200, stiffness: 140 }, durationInFrames: 14 });
  const text = spring({ frame: frame - 5, fps, config: { damping: 200, stiffness: 160 }, durationInFrames: 12 });
  const push = interpolate(frame, [0, Math.max(1, durationInFrames)], [1, 1.04]);
  const parts = (media.caption ?? '').trim().split(/\s+/);
  const surname = parts.length > 1 ? parts[parts.length - 1] : parts[0] ?? '';
  const first = parts.length > 1 ? parts.slice(0, -1).join(' ') : '';
  const aspect = media.width && media.height ? media.width / media.height : 0.75;
  const height = 960;
  return (
    <AbsoluteFill>
      <GridBackground />
      <AbsoluteFill
        style={{ background: `radial-gradient(circle 520px at 72% 55%, ${theme.glow} 0%, rgba(0,0,0,0) 70%)`, opacity: enter }}
      />
      <AbsoluteFill style={{ justifyContent: 'flex-end', alignItems: 'center', paddingLeft: '44%' }}>
        <Img
          src={staticFile(media.src)}
          style={{
            height,
            width: Math.round(height * aspect),
            objectFit: 'contain',
            filter: 'drop-shadow(0 30px 60px rgba(0,0,0,0.6))',
            opacity: enter,
            transform: `translateX(${interpolate(enter, [0, 1], [180, 0])}px) scale(${push})`,
            transformOrigin: 'bottom center',
          }}
        />
      </AbsoluteFill>
      <AbsoluteFill style={{ justifyContent: 'center', alignItems: 'flex-start', paddingLeft: 140 }}>
        <div style={{ display: 'flex', gap: 26, opacity: text, transform: `translateX(${interpolate(text, [0, 1], [-50, 0])}px)` }}>
          <div style={{ width: 12, backgroundColor: theme.accent }} />
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            {first ? (
              <div style={{ fontFamily, fontWeight: 800, fontSize: 84, color: theme.text, lineHeight: 1, textTransform: 'uppercase', textShadow: theme.shadow }}>
                {first}
              </div>
            ) : null}
            <div
              style={{
                fontFamily,
                fontWeight: 900,
                fontSize: surname.length > 9 ? 150 : 200,
                color: theme.accent,
                lineHeight: 0.95,
                letterSpacing: '-0.03em',
                textTransform: 'uppercase',
                textShadow: theme.shadow,
              }}
            >
              {surname}
            </div>
          </div>
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
