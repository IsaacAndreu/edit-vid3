import type { FC } from 'react';
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { alpha, fontFamily, theme } from '../../theme';
import type { ReplayGraphic } from '../../graphics';
import { Clip } from './MediaBox';

/** Where the athlete is at time t (linear between tracked samples). */
const at = (track: ReplayGraphic['track'], t: number): [number, number, number, number] | null => {
  if (!track.length || t < track[0][0] - 0.3 || t > track[track.length - 1][0] + 0.3) {
    return null;
  }
  const k = track.findIndex((p) => p[0] >= t);
  if (k <= 0) {
    const p = track[k === 0 ? 0 : track.length - 1];
    return [p[1], p[2], p[3], p[4]];
  }
  const [a, b] = [track[k - 1], track[k]];
  const f = (t - a[0]) / Math.max(1e-6, b[0] - a[0]);
  return [1, 2, 3, 4].map((i) => a[i] + (b[i] - a[i]) * f) as [number, number, number, number];
};

/** Replay with a speed ramp (baked into the clip): "REPLAY" badge, a ring following the athlete,
 * their path drawn behind them, and at the slow-motion peak a flash and the name of the move. */
export const Replay: FC<{ graphic: ReplayGraphic; durationInFrames: number }> = ({ graphic, durationInFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  const now = at(graphic.track, t);
  const peakFrame = Math.round(graphic.peak * fps);
  const flash = interpolate(frame, [peakFrame - 1, peakFrame, peakFrame + 6], [0, 0.45, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const label = spring({ frame: frame - peakFrame, fps, config: { damping: 16, stiffness: 170 } });
  const slow = Math.abs(t - graphic.peak) < 0.5 / 0.35 / 2 + 0.3;
  const blink = Math.floor(frame / 12) % 2 === 0;
  return (
    <AbsoluteFill style={{ backgroundColor: '#000' }}>
      <Clip media={graphic.video} fps={fps} durationInFrames={durationInFrames} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
      <AbsoluteFill style={{ background: 'radial-gradient(ellipse at 50% 50%, rgba(0,0,0,0) 55%, rgba(0,0,0,0.55) 100%)' }} />
      {now ? (
        // tracking brackets around the athlete
        <div
          style={{
            position: 'absolute',
            left: `${now[0] - 1.5}%`,
            top: `${now[1] - 2.5}%`,
            width: `${now[2] + 3}%`,
            height: `${now[3] + 5}%`,
          }}
        >
          {[0, 1, 2, 3].map((i) => (
            <div
              key={i}
              style={{
                position: 'absolute',
                width: 46,
                height: 46,
                [i < 2 ? 'top' : 'bottom']: 0,
                [i % 2 ? 'right' : 'left']: 0,
                borderTop: i < 2 ? `6px solid ${theme.accent}` : undefined,
                borderBottom: i >= 2 ? `6px solid ${theme.accent}` : undefined,
                borderLeft: i % 2 === 0 ? `6px solid ${theme.accent}` : undefined,
                borderRight: i % 2 ? `6px solid ${theme.accent}` : undefined,
                filter: `drop-shadow(0 0 6px ${alpha(theme.accent, 0.9)})`,
              }}
            />
          ))}
        </div>
      ) : null}
      <div
        style={{
          position: 'absolute',
          left: 70,
          top: 60,
          display: 'flex',
          alignItems: 'center',
          gap: 16,
          padding: '10px 24px',
          backgroundColor: alpha('#000000', 0.6),
          border: `3px solid ${theme.accent}`,
          fontFamily,
          fontWeight: 900,
          fontSize: 40,
          color: theme.text,
          letterSpacing: 3,
        }}
      >
        <div style={{ width: 20, height: 20, borderRadius: 10, backgroundColor: '#e5383b', opacity: blink ? 1 : 0.25 }} />
        {graphic.badge}
        {slow ? <span style={{ color: theme.accent, fontSize: 32 }}>× 0.35</span> : null}
      </div>
      {graphic.name ? (
        <div
          style={{
            position: 'absolute',
            // next to the athlete when tracked, else bottom right
            left: now ? `${Math.min(70, now[0] + now[2] + 3)}%` : undefined,
            right: now ? undefined : 90,
            top: now ? `${Math.max(12, now[1] - 4)}%` : undefined,
            bottom: now ? undefined : 110,
            fontFamily,
            fontWeight: 900,
            fontSize: 60,
            color: '#111',
            backgroundColor: theme.accent,
            padding: '8px 26px',
            opacity: frame < peakFrame ? 0 : label,
            transform: `scale(${interpolate(label, [0, 1], [1.4, 1])})`,
            boxShadow: '0 12px 40px rgba(0,0,0,0.6)',
            whiteSpace: 'nowrap',
          }}
        >
          {graphic.name.toUpperCase()}
        </div>
      ) : null}
      <AbsoluteFill style={{ backgroundColor: 'white', opacity: flash }} />
    </AbsoluteFill>
  );
};
