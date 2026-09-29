import type { FC } from 'react';
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { alpha, fontFamily, theme } from '../../theme';
import type { ScoreGraphic } from '../../graphics';
import { GridBackground } from '../GridBackground';

const SCORE_LANDS = 40; // keep in sync with pipeline/timeline.py

/** A gymnastics score taken apart: difficulty + execution − penalty = the final score, each part
 * popping in and the total counting up with a bump. */
export const Score: FC<{ graphic: ScoreGraphic; durationInFrames: number }> = ({ graphic }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const lands = SCORE_LANDS + (graphic.penalty ? 12 : 0);
  const parts: { label: string; value: number; at: number; sign?: string }[] = [
    { label: graphic.labels.d, value: graphic.d, at: 10 },
    { label: graphic.labels.e, value: graphic.e, at: 22, sign: '+' },
  ];
  if (graphic.penalty) {
    parts.push({ label: graphic.labels.penalty, value: graphic.penalty, at: 34, sign: '−' });
  }
  const head = interpolate(frame, [0, 10], [0, 1], { extrapolateRight: 'clamp' });
  const total = spring({ frame: frame - lands, fps, config: { damping: 11, stiffness: 170 } });
  const counted = interpolate(frame, [lands - 14, lands], [0, graphic.total], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const box = (label: string, value: string, t: number, big = false) => (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 10,
        padding: big ? '24px 44px' : '20px 30px',
        backgroundColor: big ? theme.accent : theme.panelRaised,
        border: `3px solid ${big ? theme.accent : theme.border}`,
        borderRadius: 18,
        boxShadow: big ? `0 0 70px ${alpha(theme.accent, 0.45)}` : '0 14px 40px rgba(0,0,0,0.5)',
        opacity: Math.min(1, t * 1.5),
        transform: `scale(${interpolate(t, [0, 1], [0.6, 1])})`,
      }}
    >
      <div style={{ fontWeight: 800, fontSize: big ? 30 : 24, letterSpacing: 2, color: big ? '#111' : theme.muted }}>{label}</div>
      <div style={{ fontWeight: 900, fontSize: big ? 124 : 78, lineHeight: 1, color: big ? '#111' : theme.text, fontVariantNumeric: 'tabular-nums' }}>
        {value}
      </div>
    </div>
  );
  const op = (sign: string, at: number) => (
    <div style={{ fontWeight: 900, fontSize: 72, color: theme.muted, opacity: interpolate(frame, [at - 4, at], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }) }}>
      {sign}
    </div>
  );
  return (
    <AbsoluteFill style={{ fontFamily }}>
      <GridBackground />
      <div style={{ position: 'absolute', top: 150, left: 0, right: 0, textAlign: 'center', opacity: head }}>
        {graphic.name ? <div style={{ fontWeight: 900, fontSize: 76, color: theme.text, textShadow: theme.shadow }}>{graphic.name.toUpperCase()}</div> : null}
        {graphic.title ? <div style={{ fontWeight: 600, fontSize: 40, color: theme.accent, marginTop: 8, letterSpacing: 2 }}>{graphic.title.toUpperCase()}</div> : null}
      </div>
      <div style={{ position: 'absolute', top: 430, left: 0, right: 0, display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 22 }}>
        {parts.map((p) => {
          const t = spring({ frame: frame - p.at, fps, config: { damping: 14, stiffness: 160 } });
          return (
            <div key={p.label} style={{ display: 'flex', alignItems: 'center', gap: 22 }}>
              {p.sign ? op(p.sign, p.at) : null}
              {box(p.label, p.value.toFixed(3), t)}
            </div>
          );
        })}
        {op('=', lands - 4)}
        {box(graphic.labels.total, counted.toFixed(3), total, true)}
      </div>
    </AbsoluteFill>
  );
};
