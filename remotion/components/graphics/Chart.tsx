import type { FC } from 'react';
import { AbsoluteFill, Easing, interpolate, useCurrentFrame } from 'remotion';
import { fontFamily, theme } from '../../theme';
import type { ChartGraphic } from '../../graphics';
import { GridBackground } from '../GridBackground';
import { GraphicTitle } from './GraphicTitle';

const PALETTE = [theme.accent, '#3b82f6', '#f97316', '#22c55e', '#a855f7', '#ec4899', '#14b8a6', '#eab308'];
const W = 1700;
const H = 700;
const LEFT = 110;
const TOP = 230;

const label = (n: number, target: number, unit?: string | null) => {
  const decimals = Math.min(2, (String(target).split('.')[1] ?? '').length);
  const text = n.toLocaleString('es-ES', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
  return unit ? `${text} ${unit}` : text;
};

const grow = (frame: number, from: number, to: number) =>
  interpolate(frame, [from, to], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic) });

const Bars: FC<{ g: ChartGraphic }> = ({ g }) => {
  const frame = useCurrentFrame();
  const data = g.data.slice(0, 12);
  const max = Math.max(...data.map((d) => d.value), 1);
  const slot = W / data.length;
  return (
    <div style={{ position: 'absolute', left: LEFT, top: TOP, width: W, height: H, display: 'flex', alignItems: 'flex-end' }}>
      {data.map((d, i) => {
        const k = grow(frame, 8 + i * 5, 34 + i * 5);
        const hot = g.highlight ? d.label === g.highlight : i === data.indexOf(data.reduce((a, b) => (b.value > a.value ? b : a)));
        return (
          <div key={i} style={{ width: slot, display: 'flex', flexDirection: 'column', alignItems: 'center', fontFamily }}>
            <div style={{ fontWeight: 800, fontSize: 36, color: hot ? theme.accent : theme.text, opacity: Math.min(1, k * 2), marginBottom: 10 }}>
              {label(d.value * k, d.value, g.unit)}
            </div>
            <div
              style={{
                width: slot * 0.62,
                height: ((H - 150) * d.value * k) / max,
                backgroundColor: hot ? theme.accent : 'rgba(255,255,255,0.28)',
                borderRadius: '10px 10px 0 0',
                boxShadow: hot ? '0 0 40px rgba(255,212,0,0.35)' : 'none',
              }}
            />
            <div style={{ fontWeight: 700, fontSize: 30, color: theme.muted, marginTop: 14, textAlign: 'center', height: 76 }}>{d.label}</div>
          </div>
        );
      })}
    </div>
  );
};

const Line: FC<{ g: ChartGraphic }> = ({ g }) => {
  const frame = useCurrentFrame();
  const data = g.data.slice(0, 24);
  const values = data.map((d) => d.value);
  const min = Math.min(...values, 0);
  const max = Math.max(...values, 1);
  const x = (i: number) => (data.length === 1 ? W / 2 : (i * W) / (data.length - 1));
  const y = (v: number) => H - 120 - ((v - min) / (max - min || 1)) * (H - 200);
  const draw = grow(frame, 6, 50);
  const d = data.map((p, i) => `${i ? 'L' : 'M'}${x(i)},${y(p.value)}`).join(' ');
  const shown = Math.floor(draw * (data.length - 1) + 1e-6);
  return (
    <svg style={{ position: 'absolute', left: LEFT, top: TOP, overflow: 'visible' }} width={W} height={H}>
      <line x1={0} x2={W} y1={H - 120} y2={H - 120} stroke="rgba(255,255,255,0.25)" strokeWidth={2} />
      <path d={`${d} L${x(data.length - 1)},${H - 120} L${x(0)},${H - 120} Z`} fill="rgba(255,212,0,0.10)" opacity={draw} />
      <path d={d} fill="none" stroke={theme.accent} strokeWidth={7} strokeLinejoin="round" pathLength={1} strokeDasharray="1" strokeDashoffset={1 - draw} />
      {data.map((p, i) =>
        i <= shown ? (
          <g key={i}>
            <circle cx={x(i)} cy={y(p.value)} r={10} fill={theme.accent} stroke="#000" strokeWidth={3} />
            {i === shown || i === 0 || data.length <= 8 ? (
              <text x={x(i)} y={y(p.value) - 26} fill={theme.text} fontFamily={fontFamily} fontWeight={800} fontSize={32} textAnchor="middle">
                {label(p.value, p.value, g.unit)}
              </text>
            ) : null}
          </g>
        ) : null,
      )}
      {data.map((p, i) =>
        data.length <= 12 || i % Math.ceil(data.length / 12) === 0 ? (
          <text key={`x${i}`} x={x(i)} y={H - 70} fill={theme.muted} fontFamily={fontFamily} fontWeight={700} fontSize={28} textAnchor="middle">
            {p.label}
          </text>
        ) : null,
      )}
    </svg>
  );
};

const Pie: FC<{ g: ChartGraphic }> = ({ g }) => {
  const frame = useCurrentFrame();
  const data = g.data.slice(0, 8);
  const total = data.reduce((s, d) => s + d.value, 0) || 1;
  const sweep = grow(frame, 6, 44) * Math.PI * 2;
  const R = 300;
  const cx = 560;
  const cy = H / 2;
  let angle = -Math.PI / 2;
  const slices = data.map((d, i) => {
    const start = angle;
    const size = (d.value / total) * Math.PI * 2;
    angle += size;
    const end = Math.min(start + size, -Math.PI / 2 + sweep);
    if (end <= start) return null;
    const large = end - start > Math.PI ? 1 : 0;
    const p = (a: number) => `${cx + R * Math.cos(a)},${cy + R * Math.sin(a)}`;
    return <path key={i} d={`M${cx},${cy} L${p(start)} A${R},${R} 0 ${large} 1 ${p(end)} Z`} fill={PALETTE[i % PALETTE.length]} stroke="#07080b" strokeWidth={4} />;
  });
  return (
    <div style={{ position: 'absolute', left: LEFT, top: TOP, width: W, height: H }}>
      <svg width={W} height={H} style={{ position: 'absolute' }}>
        {slices}
        <circle cx={cx} cy={cy} r={R * 0.52} fill="#07080b" />
      </svg>
      <div style={{ position: 'absolute', left: 1000, top: 60, display: 'flex', flexDirection: 'column', gap: 22, fontFamily }}>
        {data.map((d, i) => {
          const show = grow(frame, 10 + i * 6, 24 + i * 6);
          return (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 20, opacity: show }}>
              <div style={{ width: 30, height: 30, borderRadius: 6, backgroundColor: PALETTE[i % PALETTE.length] }} />
              <div style={{ fontWeight: 700, fontSize: 36, color: theme.text }}>{d.label}</div>
              <div style={{ fontWeight: 900, fontSize: 36, color: theme.accent }}>{Math.round((d.value / total) * 100)}%</div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

/** Animated bar, line or pie chart on the channel canvas. */
export const Chart: FC<{ graphic: ChartGraphic; durationInFrames: number }> = ({ graphic }) => (
  <AbsoluteFill>
    <GridBackground />
    <GraphicTitle text={graphic.title} />
    {graphic.chart === 'line' ? <Line g={graphic} /> : graphic.chart === 'pie' ? <Pie g={graphic} /> : <Bars g={graphic} />}
  </AbsoluteFill>
);
