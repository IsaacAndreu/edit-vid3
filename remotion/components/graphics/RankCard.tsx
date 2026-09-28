import type { FC } from 'react';
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { fontFamily, theme } from '../../theme';
import type { RankGraphic } from '../../graphics';
import { GridBackground } from '../GridBackground';
import { MediaBox } from './MediaBox';

/** Countdown card: a huge "#3", the name, a photo or clip and 2-4 facts that pop in one by one. */
export const RankCard: FC<{ graphic: RankGraphic; durationInFrames: number }> = ({ graphic, durationInFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const number = spring({ frame, fps, config: { damping: 14, stiffness: 140 } });
  const body = spring({ frame: frame - 8, fps, config: { damping: 200, stiffness: 120 } });
  const stats = graphic.stats ?? [];
  return (
    <AbsoluteFill>
      <GridBackground />
      <div style={{ position: 'absolute', left: 110, top: 150, width: 800, fontFamily }}>
        <div
          style={{
            fontWeight: 900,
            fontSize: 260,
            lineHeight: 0.9,
            color: theme.accent,
            textShadow: '0 0 60px rgba(255,212,0,0.35)',
            transform: `scale(${interpolate(number, [0, 1], [1.4, 1])})`,
            transformOrigin: 'left center',
            opacity: Math.min(1, number * 1.4),
          }}
        >
          #{graphic.rank}
          {graphic.total ? <span style={{ fontSize: 70, color: theme.muted }}>/{graphic.total}</span> : null}
        </div>
        <div
          style={{
            marginTop: 26,
            opacity: body,
            transform: `translateY(${(1 - body) * 30}px)`,
          }}
        >
          <div style={{ fontWeight: 900, fontSize: 84, color: theme.text, lineHeight: 1.02 }}>{graphic.name.toUpperCase()}</div>
          {graphic.subtitle ? (
            <div style={{ fontWeight: 600, fontSize: 38, color: theme.muted, marginTop: 10 }}>{graphic.subtitle}</div>
          ) : null}
        </div>
        <div style={{ marginTop: 44, display: 'flex', flexDirection: 'column', gap: 18 }}>
          {stats.map((s, i) => {
            const show = spring({ frame: frame - 20 - i * 8, fps, config: { damping: 200, stiffness: 160 } });
            return (
              <div
                key={i}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'baseline',
                  borderBottom: '2px solid rgba(255,255,255,0.12)',
                  paddingBottom: 10,
                  opacity: show,
                  transform: `translateX(${(1 - show) * -40}px)`,
                }}
              >
                <span style={{ fontWeight: 600, fontSize: 34, color: theme.muted }}>{s.label}</span>
                <span style={{ fontWeight: 800, fontSize: 46, color: theme.text }}>{s.value}</span>
              </div>
            );
          })}
        </div>
      </div>
      <MediaBox
        media={graphic.media}
        width={860}
        height={720}
        durationInFrames={durationInFrames}
        style={{
          position: 'absolute',
          right: 110,
          top: 190,
          opacity: body,
          transform: `translateX(${(1 - body) * 60}px) rotate(1.2deg)`,
        }}
      />
    </AbsoluteFill>
  );
};
