import type { FC } from 'react';
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { alpha, fontFamily, theme } from '../../theme';
import type { PodiumGraphic } from '../../graphics';
import { GridBackground } from '../GridBackground';
import { GraphicTitle } from './GraphicTitle';
import { MediaBox } from './MediaBox';

export const PODIUM_RISE: Record<number, number> = { 3: 6, 2: 14, 1: 24 }; // keep in sync with pipeline/timeline.py
const METAL: Record<number, string> = { 1: '#f5c451', 2: '#c9d1d9', 3: '#cd7f4a' };
const HEIGHT: Record<number, number> = { 1: 330, 2: 240, 3: 170 };
const X: Record<number, number> = { 2: 330, 1: 760, 3: 1190 };

/** Podium: bronze, silver and gold blocks rise in turn, each athlete drops onto theirs; the winner
 * gets a glow and a burst of light. */
export const Podium: FC<{ graphic: PodiumGraphic; durationInFrames: number }> = ({ graphic, durationInFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const base = 960;
  const glow = interpolate(frame, [PODIUM_RISE[1] + 8, PODIUM_RISE[1] + 30], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  return (
    <AbsoluteFill style={{ fontFamily }}>
      <GridBackground />
      {graphic.title ? <GraphicTitle text={graphic.title} /> : null}
      <div
        style={{
          position: 'absolute',
          left: 660,
          top: 200,
          width: 600,
          height: 700,
          background: `radial-gradient(ellipse at 50% 60%, ${alpha(METAL[1], 0.35 * glow)} 0%, rgba(0,0,0,0) 70%)`,
        }}
      />
      {graphic.places.map((p) => {
        const rise = spring({ frame: frame - PODIUM_RISE[p.place], fps, config: { damping: 15, stiffness: 120 } });
        const drop = spring({ frame: frame - PODIUM_RISE[p.place] - 8, fps, config: { damping: 12, stiffness: 160 } });
        const h = HEIGHT[p.place] * rise;
        return (
          <div key={p.place}>
            <div
              style={{
                position: 'absolute',
                left: X[p.place],
                width: 400,
                top: base - h,
                height: h,
                background: `linear-gradient(180deg, ${METAL[p.place]} 0%, ${alpha(METAL[p.place], 0.55)} 100%)`,
                borderRadius: '10px 10px 0 0',
                boxShadow: p.place === 1 ? `0 0 ${60 * glow}px ${alpha(METAL[1], 0.6)}` : '0 10px 30px rgba(0,0,0,0.5)',
                display: 'flex',
                justifyContent: 'center',
                paddingTop: 16,
                overflow: 'hidden',
              }}
            >
              <div style={{ fontWeight: 900, fontSize: 130, color: 'rgba(0,0,0,0.35)', lineHeight: 1 }}>{p.place}</div>
            </div>
            <div
              style={{
                position: 'absolute',
                left: X[p.place],
                width: 400,
                bottom: 1080 - (base - HEIGHT[p.place]) + 16, // standing right on top of the block
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                gap: 12,
                opacity: frame < PODIUM_RISE[p.place] + 8 ? 0 : Math.min(1, drop * 1.5),
                transform: `translateY(${(1 - drop) * -140}px)`,
              }}
            >
              {p.media ? (
                <MediaBox media={p.media} width={200} height={200} durationInFrames={durationInFrames}
                  style={{ borderRadius: '50%', borderColor: METAL[p.place] }} face />
              ) : null}
              <div style={{ fontWeight: 900, fontSize: 44, color: theme.text, textAlign: 'center', textShadow: theme.shadow, lineHeight: 1.05 }}>
                {p.name.toUpperCase()}
              </div>
              {p.note ? <div style={{ fontWeight: 700, fontSize: 34, color: METAL[p.place] }}>{p.note}</div> : null}
            </div>
          </div>
        );
      })}
      <div style={{ position: 'absolute', left: 200, right: 200, top: base, height: 6, backgroundColor: theme.border }} />
    </AbsoluteFill>
  );
};
