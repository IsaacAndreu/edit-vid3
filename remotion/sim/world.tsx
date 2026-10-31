// What every simulated world gets and gives (remotion/sim/worlds/*.tsx, listed in registry.ts and described in
// worlds.json): the shot (its graphic), the time inside it, how far the camera has moved from the previous focus, and
// each panel's opacity; it draws itself full screen and says when its sounds go.
import type {CSSProperties, FC, ReactNode} from 'react';
import type {SimGraphic} from '../graphics';
import {C, FONT, Label, Panel} from './hud';

export type WorldProps = {
  g: SimGraphic;
  local: number;              // seconds since this shot started (in a replay: the time shown, rewound and slowed)
  real?: number;              // seconds since this shot started on the clock (camera moves, arrows)
  length: number;             // the shot's length in seconds
  worldT: number;             // seconds since this world came on screen (its clock, before any pacing of its own)
  move: number;               // 0 → 1: the camera going from the previous shot's focus to this one's
  on: number;                 // this shot's panel opacity (fading in and out)
  o: (name: string) => number;
};

export type WorldSounds = {clicks: number[]; ticks: number[]};      // seconds inside the shot

export type World = {
  View: FC<WorldProps>;
  sounds?: (g: SimGraphic, length: number) => Partial<WorldSounds>;
};

export const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;

export const param = <T extends number | string>(g: SimGraphic, name: string, fallback: T): T => {
  const value = g.params?.[name];
  return (value === undefined ? fallback : typeof fallback === 'number' ? Number(value) : value) as T;
};

export const mulberry = (seed: number) => () => {
  seed |= 0;
  seed = (seed + 0x6d2b79f5) | 0;
  let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
  t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
};

/** A big figure in a panel. */
export const Big: FC<{label: string; value: string; color?: string; style?: CSSProperties; o: number; sub?: string}> = (
  {label, value, color = C.text, style, o, sub}) => (
  <Panel o={o} style={{width: 260, ...style}}>
    <Label>{label}</Label>
    <div style={{fontSize: 56, fontWeight: 800, color, fontVariantNumeric: 'tabular-nums', lineHeight: 1.05}}>{value}</div>
    {sub && <Label>{sub}</Label>}
  </Panel>
);

/** The small line at the bottom saying what is simulated and how. */
export const Note: FC<{children: ReactNode}> = ({children}) => (
  <div style={{position: 'absolute', left: 48, bottom: 22, fontFamily: FONT, fontSize: 20, letterSpacing: 1.1, color: 'rgba(255,255,255,0.62)',
               textTransform: 'uppercase'}}>{children}</div>
);

/** A title over one half (or band) of a split screen. */
export const SideTitle: FC<{text: string; style: CSSProperties}> = ({text, style}) => (
  <div style={{position: 'absolute', fontFamily: FONT, fontSize: 40, fontWeight: 800, color: C.text, textTransform: 'uppercase', ...style}}>
    {text}<div style={{height: 4, width: 110, background: C.accent, marginTop: 4}} />
  </div>
);

/** A small line chart of a series up to now (x: 0 → total), in a panel. */
export const Spark: FC<{values: number[]; total: number; max: number; color: string; w?: number; h?: number}> = ({values, total, max, color, w = 420, h = 150}) => {
  const xy = values.map((v, i) => [(i / Math.max(1, total - 1)) * w, h - 4 - (v / Math.max(1e-9, max)) * (h - 8)] as const);
  const pts = xy.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
  const last = xy[xy.length - 1];
  const id = `spark-${color.replace(/[^0-9a-z]/gi, '')}`;
  return (
    <svg width={w} height={h} style={{display: 'block', marginTop: 10, background: 'rgba(255,255,255,0.03)', borderRadius: 4}}>
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity={0.35} />
          <stop offset="100%" stopColor={color} stopOpacity={0} />
        </linearGradient>
      </defs>
      {[0.25, 0.5, 0.75].map((f) => <line key={f} x1={0} x2={w} y1={h * f} y2={h * f} stroke="rgba(255,255,255,0.06)" />)}
      {xy.length > 1 && <polygon points={`${xy[0][0]},${h} ${pts} ${last[0]},${h}`} fill={`url(#${id})`} />}
      <polyline points={pts} fill="none" stroke={color} strokeWidth={3} strokeLinejoin="round" strokeLinecap="round" />
      {last && <circle cx={last[0]} cy={last[1]} r={5} fill={color} stroke="#0b1020" strokeWidth={2} />}
    </svg>
  );
};

/** The split of the screen moving from the previous focus to this one: 'both' 960, one side wide 1340 / 580. */
export const splitAt = (prev: string, focus: string, move: number, sides: [string, string] = ['left', 'right']) => {
  const x = (f: string) => (f === sides[0] ? 1340 : f === sides[1] ? 580 : 960);
  return x(prev) + (x(focus) - x(prev)) * move;
};
