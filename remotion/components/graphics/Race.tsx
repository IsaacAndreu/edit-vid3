import type { FC } from 'react';
import { AbsoluteFill, interpolate, useCurrentFrame } from 'remotion';
import { fontFamily, palette, theme } from '../../theme';
import type { RaceGraphic } from '../../graphics';
import { GridBackground } from '../GridBackground';
import { GraphicTitle } from './GraphicTitle';

const BAR = 92;

/** Bar chart race: the values glide from one year to the next and the bars overtake each other;
 * the current year is huge in the corner. */
export const Race: FC<{ graphic: RaceGraphic; durationInFrames: number }> = ({ graphic, durationInFrames }) => {
  const frame = useCurrentFrame();
  const steps = graphic.steps;
  const names = Array.from(new Set(steps.flatMap((s) => Object.keys(s.values))));
  const colors = palette();
  // position along the steps (0 … n-1), finishing at 85 % of the graphic
  const pos = interpolate(frame, [0, durationInFrames * 0.85], [0, steps.length - 1], { extrapolateRight: 'clamp' });
  const k = Math.min(steps.length - 2, Math.floor(pos));
  const f = Math.min(1, pos - k);
  const ease = f < 0.5 ? 2 * f * f : 1 - (-2 * f + 2) ** 2 / 2;
  const value = (name: string, i: number) => steps[i].values[name] ?? 0;
  const now = names.map((n) => ({ n, v: value(n, k) + (value(n, k + 1) - value(n, k)) * ease }));
  const rank = (i: number) => [...names].sort((a, b) => value(b, i) - value(a, i));
  const [before, after] = [rank(k), rank(k + 1)];
  const max = Math.max(...now.map((x) => x.v), 1);
  const shown = names.slice(0, 8);
  const label = steps[Math.round(pos)].label;
  return (
    <AbsoluteFill style={{ fontFamily }}>
      <GridBackground />
      <GraphicTitle text={graphic.title} />
      {shown.map((name) => {
        const place = before.indexOf(name) + (after.indexOf(name) - before.indexOf(name)) * ease;
        const v = now.find((x) => x.n === name)!.v;
        const color = colors[names.indexOf(name) % colors.length];
        return (
          <div key={name} style={{ position: 'absolute', left: 110, top: 220 + place * BAR, display: 'flex', alignItems: 'center', gap: 20 }}>
            <div style={{ width: 300, textAlign: 'right', fontWeight: 800, fontSize: 38, color: theme.text }}>{name}</div>
            <div style={{ width: (v / max) * 1150, height: BAR - 22, backgroundColor: color, borderRadius: 8 }} />
            <div style={{ fontWeight: 900, fontSize: 42, color: theme.text, fontVariantNumeric: 'tabular-nums' }}>
              {Math.round(v).toLocaleString('es-ES')}
              {graphic.unit ? <span style={{ fontSize: 28, color: theme.muted }}> {graphic.unit}</span> : null}
            </div>
          </div>
        );
      })}
      <div style={{ position: 'absolute', right: 110, bottom: 70, fontWeight: 900, fontSize: 200, color: theme.accent, opacity: 0.9, lineHeight: 1 }}>
        {label}
      </div>
    </AbsoluteFill>
  );
};
