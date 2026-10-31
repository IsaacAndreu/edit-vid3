// Shared scene pieces for the worlds: two runs of a world side by side (the same view at half size, each with its title
// and its figure) and a line chart drawn as the voice goes (several series, a marker, a threshold line). The curves'
// numbers come from the worlds' own simulations, computed once (remotion/sim/curves.json, made by running the engines).
import type {FC, ReactElement} from 'react';
import {AbsoluteFill, Easing, interpolate} from 'remotion';
import {C, FONT, Label, Panel} from './hud';
import {clamp} from './world';

/** Two views of a world side by side, each a whole 1920×1080 picture shrunk to half; titles above, figures below. */
export const Split: FC<{left: ReactElement; right: ReactElement; titles: [string, string]; figures?: [ReactElement | null, ReactElement | null]; bg?: string}> = (
  {left, right, titles, figures, bg = '#0b1020'}) => (
  <AbsoluteFill style={{background: bg}}>
    {[left, right].map((view, i) => (
      <div key={i} style={{position: 'absolute', left: i * 960 + 12, top: 240, width: 936, height: 527, overflow: 'hidden', borderRadius: 14,
                           boxShadow: '0 20px 60px rgba(0,0,0,0.5)'}}>
        <div style={{position: 'absolute', left: 0, top: 0, width: 1920, height: 1080, transform: 'scale(0.4875)', transformOrigin: 'top left'}}>{view}</div>
      </div>
    ))}
    {titles.map((t, i) => (
      <div key={t} style={{position: 'absolute', left: i * 960 + 40, top: 150, fontFamily: FONT, fontSize: 44, fontWeight: 800, color: C.text,
                           textTransform: 'uppercase'}}>
        {t}<div style={{height: 4, width: 110, background: i ? C.green : C.red, marginTop: 4}} />
      </div>
    ))}
    {figures?.map((f, i) => f && <div key={i} style={{position: 'absolute', left: i * 960 + 40, top: 800}}>{f}</div>)}
  </AbsoluteFill>
);

export type Series = {name: string; colour: string; pts: [number, number][]};

/** A line chart drawn from left to right over `draw` seconds; x / y ranges, labels, an optional marker and threshold. */
export const LineChart: FC<{series: Series[]; t: number; draw?: number; x: [number, number]; y: [number, number]; xLabel: string; yLabel: string;
  title: string; xFmt?: (v: number) => string; yFmt?: (v: number) => string; xTicks?: number[]; yTicks?: number[];
  marker?: {x: number; label: string}; band?: {from: number; to: number; label: string}; hline?: {y: number; label: string}}> = (
  {series, t, draw = 2.5, x, y, xLabel, yLabel, title, xFmt = String, yFmt = String, xTicks = [], yTicks = [], marker, band, hline}) => {
  const W = 1380;
  const H = 600;
  const X = (v: number) => ((v - x[0]) / (x[1] - x[0])) * W;
  const Y = (v: number) => H - ((Math.max(y[0], Math.min(y[1], v)) - y[0]) / (y[1] - y[0])) * H;
  const grow = interpolate(t, [0.2, draw], [0, 1], {...clamp, easing: Easing.inOut(Easing.cubic)});
  const until = x[0] + (x[1] - x[0]) * grow;
  return (
    <AbsoluteFill style={{background: 'radial-gradient(ellipse at 50% 40%, #16213a 0%, #0a0f1c 75%)'}}>
      <Panel o={1} style={{left: '50%', top: 90, transform: 'translateX(-50%)', width: W + 190, padding: '26px 40px'}}>
        <div style={{fontFamily: FONT, fontSize: 40, fontWeight: 800, color: C.text, textTransform: 'uppercase'}}>{title}</div>
        <div style={{display: 'flex', gap: 30, marginTop: 8}}>
          {series.map((s) => (
            <span key={s.name} style={{display: 'flex', alignItems: 'center', gap: 10, fontFamily: FONT, fontSize: 26, fontWeight: 800, color: s.colour,
                                       textTransform: 'uppercase'}}><span style={{width: 30, height: 6, background: s.colour, borderRadius: 3}} />{s.name}</span>
          ))}
        </div>
        <svg width={W} height={H + 70} viewBox={`-130 -10 ${W + 140} ${H + 80}`} style={{display: 'block', marginTop: 14, overflow: 'visible'}}>
          {band && <rect x={X(band.from)} y={0} width={X(band.to) - X(band.from)} height={H} fill="rgba(255,93,93,0.1)" />}
          {band && <text x={X(band.from) + 10} y={34} fill={C.red} fontFamily={FONT} fontSize={28} fontWeight={800}>{band.label.toUpperCase()}</text>}
          <line x1={0} x2={0} y1={0} y2={H} stroke="#5b6b8a" strokeWidth={3} />
          <line x1={0} x2={W} y1={H} y2={H} stroke="#5b6b8a" strokeWidth={3} />
          {yTicks.map((v) => (
            <g key={`y${v}`}>
              <line x1={0} x2={W} y1={Y(v)} y2={Y(v)} stroke="rgba(255,255,255,0.06)" />
              <text x={-14} y={Y(v) + 9} textAnchor="end" fill={C.label} fontFamily={FONT} fontSize={26}>{yFmt(v)}</text>
            </g>
          ))}
          {xTicks.map((v) => <text key={`x${v}`} x={X(v)} y={H + 40} textAnchor="middle" fill={C.label} fontFamily={FONT} fontSize={26}>{xFmt(v)}</text>)}
          <text x={W} y={H + 74} textAnchor="end" fill={C.label} fontFamily={FONT} fontSize={26} fontWeight={800}>{xLabel.toUpperCase()} →</text>
          <text x={-110} y={-2} fill={C.label} fontFamily={FONT} fontSize={26} fontWeight={800}>↑ {yLabel.toUpperCase()}</text>
          {hline && (
            <g>
              <line x1={0} x2={W} y1={Y(hline.y)} y2={Y(hline.y)} stroke={C.you} strokeWidth={3} strokeDasharray="12 10" />
              <text x={W - 8} y={Y(hline.y) - 12} textAnchor="end" fill={C.you} fontFamily={FONT} fontSize={28} fontWeight={800}>{hline.label.toUpperCase()}</text>
            </g>
          )}
          {series.map((s) => {
            const shown = s.pts.filter(([px]) => px <= until + 1e-9);
            const lastPt = shown[shown.length - 1];
            return (
              <g key={s.name}>
                <polyline points={shown.map(([px, py]) => `${X(px)},${Y(py)}`).join(' ')} fill="none" stroke={s.colour} strokeWidth={7} strokeLinejoin="round" strokeLinecap="round" />
                {lastPt && <circle cx={X(lastPt[0])} cy={Y(lastPt[1])} r={10} fill={s.colour} stroke="#0b1020" strokeWidth={3} />}
              </g>
            );
          })}
          {marker && grow >= 1 && (
            <g>
              <line x1={X(marker.x)} x2={X(marker.x)} y1={0} y2={H} stroke={C.you} strokeWidth={3} />
              <text x={X(marker.x) + 12} y={70} fill={C.you} fontFamily={FONT} fontSize={30} fontWeight={800}>{marker.label.toUpperCase()}</text>
            </g>
          )}
        </svg>
      </Panel>
    </AbsoluteFill>
  );
};

/** A figure for under one side of a Split. */
export const Figure: FC<{label: string; value: string; colour?: string; sub?: string}> = ({label, value, colour = C.text, sub}) => (
  <Panel o={1} style={{position: 'relative', minWidth: 300}}>
    <Label>{label}</Label>
    <div style={{fontFamily: FONT, fontSize: 64, fontWeight: 800, color: colour, whiteSpace: 'nowrap'}}>{value}</div>
    {sub && <Label>{sub}</Label>}
  </Panel>
);
