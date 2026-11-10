import type { FC } from 'react';
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { alpha, fontFamily, theme } from '../../theme';
import type { TierGraphic } from '../../graphics';
import { GridBackground } from '../GridBackground';
import { MediaBox } from './MediaBox';

// The classic tier-list colours, best row first.
const ROW_COLORS = ['#ff7f7f', '#ffbf7f', '#ffdf7f', '#ffff7f', '#bfff7f', '#7fbfff', '#bf7fff'];

const Tile: FC<{ name: string; media?: TierGraphic['items'][number]['media']; w: number; h: number; frames: number }> = ({
  name, media, w, h, frames,
}) => (
  <div style={{ position: 'relative', width: w, height: h, borderRadius: 10, overflow: 'hidden', backgroundColor: theme.panelRaised }}>
    {media ? <MediaBox media={media} width={w} height={h} durationInFrames={frames} style={{ border: 'none', borderRadius: 0 }} /> : null}
    <div
      style={{
        position: 'absolute', left: 0, right: 0, bottom: 0, padding: '18px 10px 8px',
        background: 'linear-gradient(0deg, rgba(0,0,0,0.85) 0%, rgba(0,0,0,0) 100%)',
        fontFamily, fontWeight: 800, fontSize: Math.max(18, Math.round(h * 0.17)), color: '#fff',
        textAlign: 'center', lineHeight: 1.05, textTransform: 'uppercase',
      }}
    >
      {name}
    </div>
  </div>
);

/** Tier list board: coloured rows (S, A, B…) with everything placed so far; the new element appears big
 * in the middle and flies into its row, which lights up. */
export const TierList: FC<{ graphic: TierGraphic; durationInFrames: number }> = ({ graphic, durationInFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const rows = graphic.tiers.length;
  const top = 70;
  const rowH = Math.min(175, Math.floor(940 / rows));
  const labelW = Math.round(rowH * 1.05);
  const left = 110;
  const tileH = rowH - 16;
  const tileW = Math.round(tileH * 1.5);
  const gap = 12;
  const current = graphic.items[graphic.current];
  const board = spring({ frame, fps, config: { damping: 200, stiffness: 160 }, durationInFrames: 10 });
  const fly = spring({ frame: frame - 16, fps, config: { damping: 18, stiffness: 110 } });
  const appear = spring({ frame: frame - 2, fps, config: { damping: 13, stiffness: 170 } });
  const slot = (index: number) => {
    const item = graphic.items[index];
    const row = graphic.tiers.indexOf(item.tier);
    const position = graphic.items.slice(0, index).filter((i) => i.tier === item.tier).length;
    return { x: left + labelW + 16 + position * (tileW + gap), y: top + row * rowH + 8 };
  };
  const target = slot(graphic.current);
  const bigW = tileW * 2.6;
  const bigH = tileH * 2.6;
  const x = interpolate(fly, [0, 1], [960 - bigW / 2, target.x]);
  const y = interpolate(fly, [0, 1], [540 - bigH / 2, target.y]);
  const scale = interpolate(fly, [0, 1], [2.6, 1]) * interpolate(appear, [0, 1], [0.6, 1]);
  const lit = graphic.tiers.indexOf(current.tier);
  const glow = interpolate(frame, [30, 36, 60], [0, 1, 0.25], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  return (
    <AbsoluteFill style={{ opacity: interpolate(frame, [durationInFrames - 6, durationInFrames], [1, 0], { extrapolateLeft: 'clamp' }) }}>
      <GridBackground />
      <div style={{ position: 'absolute', inset: 0, opacity: board }}>
        {graphic.tiers.map((t, r) => (
          <div
            key={t}
            style={{
              position: 'absolute', left, top: top + r * rowH, width: 1920 - 2 * left, height: rowH - 4,
              display: 'flex', backgroundColor: alpha('#000000', 0.45),
              boxShadow: r === lit ? `0 0 ${40 * glow}px ${alpha(ROW_COLORS[r % ROW_COLORS.length], 0.7 * glow)}` : 'none',
              border: `2px solid ${r === lit ? alpha(ROW_COLORS[r % ROW_COLORS.length], 0.4 + 0.6 * glow) : 'rgba(255,255,255,0.08)'}`,
            }}
          >
            <div
              style={{
                width: labelW, height: '100%', backgroundColor: ROW_COLORS[r % ROW_COLORS.length], display: 'flex',
                alignItems: 'center', justifyContent: 'center', fontFamily, fontWeight: 900, color: '#111',
                fontSize: t.length > 2 ? Math.round(rowH * 0.22) : Math.round(rowH * 0.5), textAlign: 'center', lineHeight: 1,
              }}
            >
              {t}
            </div>
          </div>
        ))}
        {graphic.items.map((item, i) =>
          i === graphic.current ? null : (
            <div key={item.name} style={{ position: 'absolute', left: slot(i).x, top: slot(i).y }}>
              <Tile name={item.name} media={item.media} w={tileW} h={tileH} frames={durationInFrames} />
            </div>
          ),
        )}
      </div>
      <div
        style={{
          position: 'absolute', left: x, top: y, width: tileW, height: tileH, transformOrigin: 'top left',
          transform: `scale(${scale})`, opacity: Math.min(1, appear * 1.5),
          filter: `drop-shadow(0 ${20 * (1 - fly)}px ${40 * (1 - fly)}px rgba(0,0,0,0.6))`,
        }}
      >
        <Tile name={current.name} media={current.media} w={tileW} h={tileH} frames={durationInFrames} />
      </div>
    </AbsoluteFill>
  );
};
