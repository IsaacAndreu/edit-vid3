import type { FC } from 'react';
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { alpha, fontFamily, theme } from '../../theme';
import type { PlazoGraphic } from '../../graphics';
import { GridBackground } from '../GridBackground';

const START = 14; // keep in sync with pipeline/timeline.py (PLAZO_START, PLAZO_RUN)
const RUN = 120;

const clock = (sec: number) => {
  const s = Math.max(0, sec);
  const m = Math.floor(s / 60);
  const rest = s - m * 60;
  return `${m}:${rest < 10 ? '0' : ''}${rest.toFixed(rest % 1 ? 1 : 0)}`;
};

/** A deadline decided something: a stopwatch runs along a bar, the limit is a red line, each moment the script names
 * is marked as the clock passes it — past the limit, in red, with how far it was over («+4 s»). */
export const Plazo: FC<{ graphic: PlazoGraphic; durationInFrames: number }> = ({ graphic }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const span = Math.max(graphic.limit, ...graphic.marks.map((m) => m.seconds)) * 1.08;
  const now = interpolate(frame, [START, START + RUN], [0, span], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const shown = Math.min(now, Math.max(...graphic.marks.map((m) => m.seconds)));
  const W = 1500;
  const X = (sec: number) => 210 + (sec / span) * W;
  const over = shown > graphic.limit;
  const head = interpolate(frame, [0, 10], [0, 1], { extrapolateRight: 'clamp' });
  return (
    <AbsoluteFill style={{ fontFamily }}>
      <GridBackground />
      {graphic.title ? (
        <div style={{ position: 'absolute', top: 120, left: 0, right: 0, textAlign: 'center', fontWeight: 900, fontSize: 58,
                      color: theme.text, letterSpacing: 2, opacity: head, textShadow: theme.shadow }}>{graphic.title.toUpperCase()}</div>
      ) : null}
      {/* the stopwatch */}
      <div style={{ position: 'absolute', top: 175, left: 0, right: 0, textAlign: 'center', fontWeight: 900, fontSize: 150,
                    fontVariantNumeric: 'tabular-nums', color: over ? theme.negative : theme.accent,
                    textShadow: `0 0 60px ${alpha(over ? theme.negative : theme.accent, 0.45)}` }}>{clock(shown)}</div>
      <svg width={1920} height={1080} style={{ position: 'absolute', left: 0, top: 0 }}>
        <rect x={210} y={600} width={W} height={34} rx={17} fill={theme.panelRaised} stroke={theme.border} strokeWidth={3} />
        <rect x={210} y={600} width={Math.max(0, Math.min(X(graphic.limit), X(shown)) - 210)} height={34} rx={17} fill={theme.accent} />
        {over && <rect x={X(graphic.limit)} y={600} width={X(shown) - X(graphic.limit)} height={34} fill={theme.negative} />}
        {/* the limit */}
        <line x1={X(graphic.limit)} x2={X(graphic.limit)} y1={560} y2={680} stroke={theme.negative} strokeWidth={8} />
        <text x={X(graphic.limit) - 14} y={556} textAnchor="end" fill={theme.negative} fontFamily={fontFamily} fontWeight={900} fontSize={40}>
          {graphic.limitWord ?? 'LIMIT'} {clock(graphic.limit)}</text>
        {graphic.marks.map((m, i) => {
          const at = START + (m.seconds / span) * RUN;
          const pop = spring({ frame: frame - at, fps, config: { damping: 12, stiffness: 190 } });
          if (frame < at) return null;
          const late = m.seconds > graphic.limit;
          const y = i % 2 ? 840 : 500;
          return (
            <g key={i} opacity={Math.min(1, pop * 1.4)} transform={`translate(${X(m.seconds)} 617) scale(${0.6 + 0.4 * pop}) translate(${-X(m.seconds)} -617)`}>
              <circle cx={X(m.seconds)} cy={617} r={26} fill={late ? theme.negative : theme.positive} stroke="#000" strokeWidth={4} />
              <line x1={X(m.seconds)} x2={X(m.seconds)} y1={i % 2 ? 645 : 590} y2={i % 2 ? 790 : 540} stroke={theme.text} strokeWidth={3} />
              <text x={X(m.seconds)} y={y} textAnchor="middle" fill={late ? theme.negative : theme.positive} fontFamily={fontFamily}
                    fontWeight={900} fontSize={54}>{clock(m.seconds)}{late ? `  (+${(m.seconds - graphic.limit).toFixed((m.seconds - graphic.limit) % 1 ? 1 : 0)} s)` : ''}</text>
              {m.label ? <text x={X(m.seconds)} y={y + (i % 2 ? 52 : -62)} textAnchor="middle" fill={theme.text} fontFamily={fontFamily}
                               fontWeight={700} fontSize={36}>{m.label.toUpperCase()}</text> : null}
            </g>
          );
        })}
      </svg>
    </AbsoluteFill>
  );
};
