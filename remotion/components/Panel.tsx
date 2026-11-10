import type { FC } from 'react';
import { AbsoluteFill, interpolate, useCurrentFrame } from 'remotion';
import { fontFamily, signColor, theme } from '../theme';
import type { PanelStep } from '../types';

const REVEAL = 8; // frames for a row to slide in

/** Rows at the current step; rows that are new at a step slide in when it starts. */
const PanelRows: FC<{ steps: PanelStep[]; width: number }> = ({ steps, width }) => {
  const frame = useCurrentFrame();
  const current = [...steps].reverse().find((s) => frame >= s.from) ?? steps[0];
  const firstSeen = new Map<string, number>();
  for (const step of steps) {
    for (const row of step.rows) {
      const k = `${row.label}|${row.value}`;
      if (!firstSeen.has(k)) firstSeen.set(k, step.from);
    }
  }
  return (
    <div style={{ width, display: 'flex', flexDirection: 'column' }}>
      {current.rows.map((row, i) => {
        const appear = (firstSeen.get(`${row.label}|${row.value}`) ?? 0) + i * 3;
        const t = interpolate(frame, [appear, appear + REVEAL], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
        return (
          <div
            key={`${row.label}-${i}`}
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'baseline',
              gap: 40,
              padding: '16px 0',
              borderBottom: `1px solid rgba(255,255,255,0.08)`,
              opacity: t,
              transform: `translateY(${(1 - t) * 14}px)`,
            }}
          >
            <span style={{ fontFamily, fontWeight: 400, fontSize: 40, color: theme.text }}>{row.label}</span>
            <span style={{ fontFamily, fontWeight: 600, fontSize: 42, color: signColor(row.sign), whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums' }}>
              {row.value}
            </span>
          </div>
        );
      })}
    </div>
  );
};

const PanelBody: FC<{ title?: string | null; note?: string | null; steps: PanelStep[]; width: number }> = ({
  title,
  note,
  steps,
  width,
}) => {
  const frame = useCurrentFrame();
  const enter = interpolate(frame, [0, 6], [0, 1], { extrapolateRight: 'clamp' });
  return (
    <div style={{ width, opacity: enter }}>
      {title ? (
        <div style={{ fontFamily, fontWeight: 800, fontSize: 30, color: theme.accent, letterSpacing: '0.14em', textTransform: 'uppercase', marginBottom: 10 }}>
          {title}
        </div>
      ) : null}
      <div style={{ height: 2, backgroundColor: theme.accent, opacity: 0.85, width: interpolate(frame, [0, 10], [0, width], { extrapolateRight: 'clamp' }), marginBottom: 8 }} />
      <PanelRows steps={steps} width={width} />
      {note ? <div style={{ fontFamily, fontWeight: 400, fontSize: 28, color: theme.muted, marginTop: 22 }}>{note}</div> : null}
    </div>
  );
};

/** Full-screen data card on the dark panel background. A card with only one or two rows is drawn bigger, so a
 * single fact fills the frame instead of floating small in the middle of an empty screen. */
export const DataCard: FC<{ title?: string | null; note?: string | null; steps: PanelStep[] }> = (props) => {
  const rows = Math.max(1, ...props.steps.map((s) => s.rows.length));
  const scale = rows <= 1 ? 1.6 : rows === 2 ? 1.4 : rows === 3 ? 1.15 : 1;
  return (
    <AbsoluteFill style={{ backgroundColor: theme.panel, justifyContent: 'center', alignItems: 'center' }}>
      <div style={{ transform: `scale(${scale})` }}>
        <PanelBody {...props} width={1180 / Math.min(scale, 1.4)} />
      </div>
    </AbsoluteFill>
  );
};

/** Right half of a split screen: the panel; the footage lives in the left half (see Split). */
export const SplitPanel: FC<{ title?: string | null; note?: string | null; steps: PanelStep[] }> = (props) => (
  <AbsoluteFill style={{ left: '50%', width: '50%', backgroundColor: theme.panel, justifyContent: 'center', alignItems: 'center' }}>
    <PanelBody {...props} width={760} />
  </AbsoluteFill>
);
