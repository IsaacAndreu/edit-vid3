import type { FC } from 'react';
import { AbsoluteFill, Easing, interpolate, useCurrentFrame } from 'remotion';
import { alpha, fontFamily, palette, theme } from '../../theme';
import type { ChartGraphic } from '../../graphics';
import { GridBackground } from '../GridBackground';
import { GraphicTitle } from './GraphicTitle';

const W = 1700;
const H = 700;
const LEFT = 110;
const TOP = 230;

const label = (n: number, target: number, unit?: string | null) => {
  const decimals = Math.min(2, (String(target).split('.')[1] ?? '').length);
  const text = n.toLocaleString('es-ES', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
  return unit ? `${text} ${unit}` : text;
};

/** Colours of the chart: the channel's dark canvas, or (dataStyle 'light') dark ink on a warm paper page, like a
 * printed infographic; the highlighted bar keeps the accent. */
const ink = () =>
  theme.dataStyle === 'light'
    ? { text: '#1d1d1f', muted: '#5d5a54', neutral: 'rgba(0,0,0,0.2)', axis: 'rgba(0,0,0,0.3)', canvas: '#efece6', dot: '#efece6' }
    : { text: theme.text, muted: theme.muted, neutral: 'rgba(255,255,255,0.28)', axis: 'rgba(255,255,255,0.25)', canvas: theme.canvas, dot: '#000' };

const grow = (frame: number, from: number, to: number) =>
  interpolate(frame, [from, to], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic) });

const Bars: FC<{ g: ChartGraphic }> = ({ g }) => {
  const frame = useCurrentFrame();
  const data = g.data.slice(0, 12);
  const max = Math.max(...data.map((d) => d.value), 1);
  const slot = W / data.length;
  const c = ink();
  return (
    <div style={{ position: 'absolute', left: LEFT, top: TOP, width: W, height: H, display: 'flex', alignItems: 'flex-end' }}>
      {data.map((d, i) => {
        const k = grow(frame, 8 + i * 5, 34 + i * 5);
        const hot = g.highlight ? d.label === g.highlight : i === data.indexOf(data.reduce((a, b) => (b.value > a.value ? b : a)));
        return (
          <div key={i} style={{ width: slot, display: 'flex', flexDirection: 'column', alignItems: 'center', fontFamily }}>
            <div style={{ fontWeight: 800, fontSize: 36, color: hot ? theme.accent : c.text, opacity: Math.min(1, k * 2), marginBottom: 10 }}>
              {label(d.value * k, d.value, g.unit)}
            </div>
            <div
              style={{
                width: slot * 0.62,
                height: ((H - 150) * d.value * k) / max,
                backgroundColor: hot ? theme.accent : c.neutral,
                borderRadius: '10px 10px 0 0',
                boxShadow: hot && theme.dataStyle !== 'light' ? `0 0 40px ${alpha(theme.accent, 0.35)}` : 'none',
              }}
            />
            <div style={{ fontWeight: 700, fontSize: 30, color: c.muted, marginTop: 14, textAlign: 'center', height: 76 }}>{d.label}</div>
          </div>
        );
      })}
    </div>
  );
};

/** A line like a market ticker: it draws itself from left to right with a glow and a fading fill under it, a live
 * value tag rides the tip, faint price levels sit behind, and a badge counts the change from the first point to the
 * last (green up, red down). */
const Line: FC<{ g: ChartGraphic }> = ({ g }) => {
  const frame = useCurrentFrame();
  const data = g.data.slice(0, 24);
  const values = data.map((d) => d.value);
  const lo = Math.min(...values);
  const hi = Math.max(...values, lo + 1e-9);
  const pad = (hi - lo) * 0.12;
  const min = lo >= 0 && lo < (hi - lo) * 0.5 ? 0 : lo - pad; // start at zero unless the line lives far above it
  const max = hi + pad;
  const base = H - 120;
  const x = (i: number) => (data.length === 1 ? W / 2 : (i * (W - 140)) / (data.length - 1));
  const y = (v: number) => base - ((v - min) / (max - min || 1)) * (H - 200);
  const draw = grow(frame, 6, 64);
  const at = draw * Math.max(0, data.length - 1);
  const i0 = Math.min(data.length - 1, Math.floor(at));
  const f = at - i0;
  const next = data[Math.min(data.length - 1, i0 + 1)].value;
  const tipValue = data[i0].value + (next - data[i0].value) * f;
  const tip = [x(i0) + (x(Math.min(data.length - 1, i0 + 1)) - x(i0)) * f, y(tipValue)];
  const pts = [...data.slice(0, i0 + 1).map((p, i) => [x(i), y(p.value)]), tip];
  const d = pts.map(([px, py], i) => `${i ? 'L' : 'M'}${px},${py}`).join(' ');
  const c = ink();
  const light = theme.dataStyle === 'light';
  const first = data[0].value;
  const change = first ? ((tipValue - first) / Math.abs(first)) * 100 : 0;
  const up = change >= 0;
  const trend = up ? '#22c55e' : '#ef4444';
  const levels = [0, 1, 2, 3, 4].map((k) => min + ((max - min) * k) / 4);
  const decimals = Math.min(2, (String(hi).split('.')[1] ?? '').length);
  const pulse = 1 + 0.35 * Math.abs(Math.sin(frame / 6));
  const peak = values.indexOf(hi);
  const tagW = Math.max(120, label(tipValue, hi, g.unit).length * 21 + 34);
  return (
    <svg style={{ position: 'absolute', left: LEFT, top: TOP, overflow: 'visible' }} width={W} height={H}>
      <defs>
        <linearGradient id="line-fill" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={theme.accent} stopOpacity={light ? 0.28 : 0.38} />
          <stop offset="100%" stopColor={theme.accent} stopOpacity={0} />
        </linearGradient>
        <filter id="line-glow" x="-10%" y="-30%" width="120%" height="160%">
          <feGaussianBlur stdDeviation="9" />
        </filter>
      </defs>
      {levels.map((v, k) => (
        <g key={`l${k}`}>
          <line x1={0} x2={W - 140} y1={y(v)} y2={y(v)} stroke={c.axis} strokeWidth={k ? 1.5 : 2} strokeDasharray={k ? '6 10' : undefined} opacity={k ? 0.6 : 1} />
          <text x={W - 120} y={y(v) + 9} fill={c.muted} fontFamily={fontFamily} fontWeight={700} fontSize={24}>
            {v.toLocaleString('es-ES', { maximumFractionDigits: decimals })}
          </text>
        </g>
      ))}
      <path d={`${d} L${tip[0]},${base} L${x(0)},${base} Z`} fill="url(#line-fill)" />
      {light ? null : <path d={d} fill="none" stroke={theme.accent} strokeWidth={14} strokeLinejoin="round" opacity={0.55} filter="url(#line-glow)" />}
      <path d={d} fill="none" stroke={theme.accent} strokeWidth={6} strokeLinejoin="round" strokeLinecap="round" />
      {/* the peak stays marked once the line has passed it */}
      {peak <= at && peak !== i0 && data.length > 2 ? (
        <g>
          <circle cx={x(peak)} cy={y(hi)} r={9} fill={theme.accent} stroke={c.dot} strokeWidth={3} />
          <text x={x(peak)} y={y(hi) - 24} fill={c.text} fontFamily={fontFamily} fontWeight={800} fontSize={30} textAnchor="middle">
            {label(hi, hi, g.unit)}
          </text>
        </g>
      ) : null}
      <line x1={tip[0]} x2={tip[0]} y1={tip[1]} y2={base} stroke={theme.accent} strokeWidth={2} strokeDasharray="4 8" opacity={0.6} />
      <circle cx={tip[0]} cy={tip[1]} r={16 * pulse} fill={theme.accent} opacity={0.25} />
      <circle cx={tip[0]} cy={tip[1]} r={10} fill={theme.accent} stroke={c.dot} strokeWidth={3} />
      <g transform={`translate(${tip[0] > (W - 140) * 0.8 ? tip[0] - 22 - tagW : tip[0] + 22}, ${tip[1] - 64})`}>
        <rect x={0} y={0} rx={10} width={tagW} height={52} fill={theme.accent} />
        <text x={17} y={37} fill={light ? '#fff' : '#000'} fontFamily={fontFamily} fontWeight={900} fontSize={32}>
          {label(tipValue, hi, g.unit)}
        </text>
      </g>
      {data.length > 1 ? (
        <g transform={`translate(${W - 140 - 250}, ${-70})`} opacity={grow(frame, 10, 22)}>
          <rect x={0} y={0} rx={12} width={250} height={60} fill={alpha(trend, 0.16)} stroke={trend} strokeWidth={2} />
          <text x={125} y={42} fill={trend} fontFamily={fontFamily} fontWeight={900} fontSize={34} textAnchor="middle">
            {`${up ? '▲' : '▼'} ${up ? '+' : '−'}${Math.abs(change).toLocaleString('es-ES', { maximumFractionDigits: Math.abs(change) < 10 ? 1 : 0 })}%`}
          </text>
        </g>
      ) : null}
      {data.map((p, i) =>
        data.length <= 12 || i % Math.ceil(data.length / 12) === 0 ? (
          <text key={`x${i}`} x={x(i)} y={H - 70} fill={c.muted} opacity={i <= at ? 1 : 0.35} fontFamily={fontFamily} fontWeight={700} fontSize={28} textAnchor="middle">
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
  const c = ink();
  let angle = -Math.PI / 2;
  const slices = data.map((d, i) => {
    const start = angle;
    const size = (d.value / total) * Math.PI * 2;
    angle += size;
    const end = Math.min(start + size, -Math.PI / 2 + sweep);
    if (end <= start) return null;
    const large = end - start > Math.PI ? 1 : 0;
    const p = (a: number) => `${cx + R * Math.cos(a)},${cy + R * Math.sin(a)}`;
    return <path key={i} d={`M${cx},${cy} L${p(start)} A${R},${R} 0 ${large} 1 ${p(end)} Z`} fill={palette()[i % 8]} stroke={c.canvas} strokeWidth={4} />;
  });
  return (
    <div style={{ position: 'absolute', left: LEFT, top: TOP, width: W, height: H }}>
      <svg width={W} height={H} style={{ position: 'absolute' }}>
        {slices}
        <circle cx={cx} cy={cy} r={R * 0.52} fill={c.canvas} />
      </svg>
      <div style={{ position: 'absolute', left: 1000, top: 60, display: 'flex', flexDirection: 'column', gap: 22, fontFamily }}>
        {data.map((d, i) => {
          const show = grow(frame, 10 + i * 6, 24 + i * 6);
          return (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 20, opacity: show }}>
              <div style={{ width: 30, height: 30, borderRadius: 6, backgroundColor: palette()[i % 8] }} />
              <div style={{ fontWeight: 700, fontSize: 36, color: c.text }}>{d.label}</div>
              <div style={{ fontWeight: 900, fontSize: 36, color: theme.accent }}>{Math.round((d.value / total) * 100)}%</div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

/** Light page behind a dataStyle 'light' chart: warm paper with a faint grid. */
const PaperBackground: FC = () => (
  <AbsoluteFill style={{ backgroundColor: '#efece6' }}>
    <AbsoluteFill
      style={{
        backgroundImage:
          'linear-gradient(rgba(0,0,0,0.05) 1px, transparent 1px), linear-gradient(90deg, rgba(0,0,0,0.05) 1px, transparent 1px)',
        backgroundSize: '64px 64px', backgroundPosition: 'center center',
      }}
    />
  </AbsoluteFill>
);

/** Animated bar, line or pie chart on the channel canvas (or on a light page with dataStyle 'light'). */
export const Chart: FC<{ graphic: ChartGraphic; durationInFrames: number }> = ({ graphic }) => (
  <AbsoluteFill>
    {theme.dataStyle === 'light' ? <PaperBackground /> : <GridBackground />}
    <GraphicTitle text={graphic.title} color={theme.dataStyle === 'light' ? '#1d1d1f' : undefined} />
    {graphic.chart === 'line' ? <Line g={graphic} /> : graphic.chart === 'pie' ? <Pie g={graphic} /> : <Bars g={graphic} />}
  </AbsoluteFill>
);
