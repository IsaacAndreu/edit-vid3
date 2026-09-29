import type { FC } from 'react';
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { alpha, fontFamily, theme } from '../../theme';
import type { StandingsGraphic } from '../../graphics';
import { GridBackground } from '../GridBackground';
import { GraphicTitle } from './GraphicTitle';

export const STANDINGS_START = 6; // keep in sync with pipeline/timeline.py
export const STANDINGS_STEP = 14;
const ROW = 104;

const value = (score: string) => Number(score.replace(',', '.')) || 0;

/** Live leaderboard: each score enters in the order it is told and the board re-sorts itself,
 * rows sliding to their new place; the leader is gold. */
export const Standings: FC<{ graphic: StandingsGraphic; durationInFrames: number }> = ({ graphic }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const rows = graphic.rows.slice(0, 8);
  const shown = rows.filter((_, i) => frame >= STANDINGS_START + i * STANDINGS_STEP).length;
  // ranking after k entries, and the previous one, to slide between them
  const order = (k: number) => rows.slice(0, k).map((r, i) => ({ r, i })).sort((a, b) => value(b.r.score) - value(a.r.score)).map((x) => x.i);
  const current = order(shown);
  const previous = order(Math.max(0, shown - 1));
  const since = frame - (STANDINGS_START + (shown - 1) * STANDINGS_STEP);
  const move = spring({ frame: since, fps, config: { damping: 200, stiffness: 140 } });
  const top = 250;
  return (
    <AbsoluteFill style={{ fontFamily }}>
      <GridBackground />
      {graphic.title ? <GraphicTitle text={graphic.title} /> : null}
      {rows.map((row, i) => {
        if (i >= shown) {
          return null;
        }
        const now = current.indexOf(i);
        const before = previous.indexOf(i);
        const place = before < 0 ? now : interpolate(move, [0, 1], [before, now]);
        const enter = i === shown - 1 ? move : 1;
        const leader = now === 0;
        return (
          <div
            key={i}
            style={{
              position: 'absolute',
              left: 360,
              width: 1200,
              top: top + place * ROW,
              height: ROW - 16,
              display: 'flex',
              alignItems: 'center',
              gap: 30,
              padding: '0 36px',
              borderRadius: 14,
              backgroundColor: leader ? theme.accent : theme.panelRaised,
              border: `3px solid ${leader ? theme.accent : theme.border}`,
              boxShadow: leader ? `0 0 50px ${alpha(theme.accent, 0.35)}` : '0 10px 30px rgba(0,0,0,0.45)',
              opacity: enter,
              transform: `translateX(${(1 - enter) * 120}px)`,
              color: leader ? '#111' : theme.text,
            }}
          >
            <div style={{ width: 60, fontWeight: 900, fontSize: 48, opacity: 0.8 }}>{now + 1}</div>
            <div style={{ flex: 1, fontWeight: 800, fontSize: 48 }}>{row.name.toUpperCase()}</div>
            <div style={{ fontWeight: 900, fontSize: 56, fontVariantNumeric: 'tabular-nums' }}>{row.score}</div>
          </div>
        );
      })}
    </AbsoluteFill>
  );
};
