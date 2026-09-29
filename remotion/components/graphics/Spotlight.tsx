import type { FC } from 'react';
import { AbsoluteFill, Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';
import { alpha, fontFamily, theme } from '../../theme';
import type { SpotlightGraphic } from '../../graphics';

/** Freeze frame + spotlight: the clip stops with a flash, the scene goes dark and grey, the person
 * stays in colour with a glowing outline, the camera pushes in on them and their name slides in. */
export const Spotlight: FC<{ graphic: SpotlightGraphic; durationInFrames: number }> = ({ graphic, durationInFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const [x, y] = graphic.anchor;
  const dim = interpolate(frame, [0, 8], [0, 1], { extrapolateRight: 'clamp' });
  const flash = interpolate(frame, [0, 1, 7], [0, 0.8, 0], { extrapolateRight: 'clamp' });
  const push = interpolate(frame, [0, durationInFrames], [1, 1.1]);
  const tag = spring({ frame: frame - 6, fps, config: { damping: 18, stiffness: 150 } });
  const origin = `${x}% ${Math.min(90, y + (graphic.height ?? 40) / 2)}%`;
  const full = { position: 'absolute' as const, inset: 0, width: '100%', height: '100%', objectFit: 'cover' as const };
  const right = x < 62; // the name goes on the side with more room
  const headY = Math.max(8, y - 2);
  return (
    <AbsoluteFill style={{ backgroundColor: '#000', overflow: 'hidden' }}>
      <AbsoluteFill style={{ transform: `scale(${push})`, transformOrigin: origin }}>
        <Img
          src={staticFile(graphic.still.src)}
          style={{ ...full, filter: `grayscale(${dim}) brightness(${1 - 0.62 * dim}) blur(${dim * 3}px)` }}
        />
        <Img
          src={staticFile(graphic.cutout.src)}
          style={{
            ...full,
            filter: `drop-shadow(0 0 ${4 * dim}px ${theme.accent}) drop-shadow(0 0 ${22 * dim}px ${alpha(theme.accent, 0.55)})`,
          }}
        />
      </AbsoluteFill>
      {/* frozen-frame corners */}
      {[0, 1, 2, 3].map((i) => (
        <div
          key={i}
          style={{
            position: 'absolute',
            width: 70,
            height: 70,
            opacity: dim,
            [i < 2 ? 'top' : 'bottom']: 50,
            [i % 2 ? 'right' : 'left']: 60,
            borderTop: i < 2 ? `6px solid ${theme.accent}` : undefined,
            borderBottom: i >= 2 ? `6px solid ${theme.accent}` : undefined,
            borderLeft: i % 2 === 0 ? `6px solid ${theme.accent}` : undefined,
            borderRight: i % 2 ? `6px solid ${theme.accent}` : undefined,
          }}
        />
      ))}
      <div
        style={{
          position: 'absolute',
          top: `${headY}%`,
          [right ? 'left' : 'right']: `${right ? x + 7 : 100 - x + 7}%`,
          display: 'flex',
          alignItems: 'center',
          flexDirection: right ? 'row' : 'row-reverse',
          gap: 0,
          opacity: tag,
        }}
      >
        <div style={{ width: 90 * tag, height: 5, backgroundColor: theme.accent }} />
        <div
          style={{
            fontFamily,
            fontWeight: 900,
            fontSize: 64,
            color: '#111',
            backgroundColor: theme.accent,
            padding: '10px 28px',
            transform: `translateX(${(1 - tag) * (right ? -40 : 40)}px)`,
            boxShadow: '0 12px 40px rgba(0,0,0,0.6)',
            whiteSpace: 'nowrap',
          }}
        >
          {graphic.name.toUpperCase()}
        </div>
      </div>
      <AbsoluteFill style={{ backgroundColor: 'white', opacity: flash }} />
    </AbsoluteFill>
  );
};
