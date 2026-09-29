import type { FC } from 'react';
import { AbsoluteFill, Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';
import { alpha, fontFamily, theme } from '../../theme';
import type { StrobeGraphic } from '../../graphics';
import { GraphicTitle } from './GraphicTitle';

export const STROBE_START = 8; // keep in sync with pipeline/timeline.py
export const STROBE_STEP = 6;

/** Stroboscope: the scene without the athlete, then each position of the move appears in turn
 * (older ones fade back), joined by a dotted path; the last one glows. */
export const Strobe: FC<{ graphic: StrobeGraphic; durationInFrames: number }> = ({ graphic, durationInFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const ghosts = graphic.ghosts;
  const push = interpolate(frame, [0, durationInFrames], [1, 1.05]);
  const dim = interpolate(frame, [0, 10], [0, 1], { extrapolateRight: 'clamp' });
  const shown = ghosts.filter((_, i) => frame >= STROBE_START + i * STROBE_STEP).length;
  const centre = (g: (typeof ghosts)[number]) => [((g.x + g.w / 2) / 100) * 1920, ((g.y + g.h / 2) / 100) * 1080];
  const path = ghosts.slice(0, Math.max(1, shown)).map((g) => centre(g).join(',')).join(' ');
  return (
    <AbsoluteFill style={{ backgroundColor: '#000', overflow: 'hidden' }}>
      <AbsoluteFill style={{ transform: `scale(${push})` }}>
        <Img
          src={staticFile(graphic.background.src)}
          style={{ width: '100%', height: '100%', objectFit: 'cover', filter: `brightness(${1 - 0.35 * dim}) saturate(${1 - 0.5 * dim})` }}
        />
        <svg width={1920} height={1080} style={{ position: 'absolute', inset: 0 }}>
          <polyline points={path} fill="none" stroke={alpha(theme.accent, 0.85)} strokeWidth={5} strokeDasharray="4 14" strokeLinecap="round" />
        </svg>
        {ghosts.map((g, i) => {
          const at = STROBE_START + i * STROBE_STEP;
          if (frame < at) {
            return null;
          }
          const pop = spring({ frame: frame - at, fps, config: { damping: 14, stiffness: 200 } });
          const last = i === shown - 1;
          const age = shown - 1 - i;
          return (
            <Img
              key={i}
              src={staticFile(g.src)}
              style={{
                position: 'absolute',
                left: `${g.x}%`,
                top: `${g.y}%`,
                width: `${g.w}%`,
                height: `${g.h}%`,
                opacity: Math.min(1, pop * 1.5) * (last ? 1 : Math.max(0.45, 0.9 - age * 0.08)),
                transform: `scale(${interpolate(pop, [0, 1], [1.15, 1])})`,
                filter: last
                  ? `drop-shadow(0 0 5px ${theme.accent}) drop-shadow(0 0 22px ${alpha(theme.accent, 0.6)})`
                  : `drop-shadow(0 0 3px ${alpha('#ffffff', 0.5)})`,
              }}
            />
          );
        })}
      </AbsoluteFill>
      <div style={{ fontFamily }}>
        <GraphicTitle text={graphic.name} />
        {graphic.note ? (
          <div style={{ position: 'absolute', left: 142, top: 160, fontFamily, fontWeight: 600, fontSize: 38, color: theme.accent, opacity: dim, textShadow: theme.shadow }}>
            {graphic.note}
          </div>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};
