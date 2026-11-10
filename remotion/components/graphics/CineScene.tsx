import type { FC, ReactNode } from 'react';
import { AbsoluteFill, interpolate, random, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import type { CineActor, CineGraphic } from '../../graphics';
import { Icon, pose, towards } from './Stickman';

/**
 * «Cine de monigotes» (pipeline/cine.py): animated short films with stickmen — the «¿Y si…?» films, the discipline
 * films and the vertical «rules» thrillers. Flat, thick-outlined figures with big heads (the hero always carries his
 * mark) in dark sets lit like a film: one warm practical, a cold fill and an accent (a door gap, a screen, a siren).
 * Shots: wide, medium, close (the face), POV phone (two stick thumbs), peephole (fisheye), over the shoulder, from
 * above, backlit silhouettes. On top: the HUD (day, clock), the rule sticker, a big title, a counter, the captions
 * word by word, the choice and the end card. Everything is a pure function of the frame.
 */

type Pt = [number, number];
const INK = '#14161c';
const BODY = '#efe9dc';
const RED = '#e5322d';

interface Light { top: string; bottom: string; wall: string; floor: string; practical: string; fill: string; dark: number }
const LIGHTS: Record<string, Light> = {
  warm: { top: '#2a2030', bottom: '#120e14', wall: '#3a2c2a', floor: '#2a1d16', practical: '#ffb35c', fill: '#3b5b9a', dark: 0.45 },
  cold: { top: '#1b2438', bottom: '#0b0f1a', wall: '#26324a', floor: '#1a2030', practical: '#9cc7ff', fill: '#4a6fb0', dark: 0.5 },
  dark: { top: '#0f1118', bottom: '#050608', wall: '#191c26', floor: '#11131a', practical: '#ffcf8a', fill: '#30406a', dark: 0.62 },
  red: { top: '#2a0d10', bottom: '#0c0405', wall: '#3a1416', floor: '#220b0c', practical: '#ff3b30', fill: '#5a1b2a', dark: 0.5 },
  dawn: { top: '#f3a35f', bottom: '#5b3a5e', wall: '#7a5a64', floor: '#4a3440', practical: '#ffd9a0', fill: '#ff9a62', dark: 0.18 },
  day: { top: '#9cc9ef', bottom: '#dfeaf2', wall: '#c9cfd6', floor: '#8d8f94', practical: '#fff4d6', fill: '#bcd7f0', dark: 0.05 },
  neon: { top: '#1a0f2e', bottom: '#07040e', wall: '#24163c', floor: '#140c22', practical: '#ff3ec8', fill: '#2ee6ff', dark: 0.42 },
};

const clamp = (v: number, a = 0, b = 1) => Math.max(a, Math.min(b, v));
const ease = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2);

// --- the figure ------------------------------------------------------------------------------------------------

const Mark: FC<{ mark: string; hx: number; hy: number; r: number; dir: number; color: string }> = ({ mark, hx, hy, r, dir, color }) => {
  if (mark === 'cap') return <path d={`M ${hx - r * 1.02} ${hy - r * 0.25} A ${r} ${r} 0 0 1 ${hx + r * 1.02} ${hy - r * 0.25} L ${hx + dir * r * 1.6} ${hy - r * 0.2} Z`} fill={color} stroke={INK} strokeWidth={r * 0.14} strokeLinejoin="round" />;
  if (mark === 'hood') return <path d={`M ${hx - r * 1.25} ${hy + r * 0.9} C ${hx - r * 1.5} ${hy - r * 1.6}, ${hx + r * 1.5} ${hy - r * 1.6}, ${hx + r * 1.25} ${hy + r * 0.9}`} fill="none" stroke={color} strokeWidth={r * 0.42} strokeLinecap="round" />;
  if (mark === 'scarf') return <path d={`M ${hx - r * 0.7} ${hy + r * 1.05} L ${hx + r * 0.7} ${hy + r * 1.05} M ${hx - dir * r * 0.4} ${hy + r * 1.05} l ${-dir * r * 0.5} ${r * 0.9}`} stroke={color} strokeWidth={r * 0.32} strokeLinecap="round" />;
  if (mark === 'none') return null;
  // the scar: a red X high on the forehead, like the hero of the rules films
  const x = hx - dir * r * 0.35;
  const y = hy - r * 0.45;
  const k = r * 0.28;
  return <path d={`M ${x - k} ${y - k} L ${x + k} ${y + k} M ${x + k} ${y - k} L ${x - k} ${y + k} M ${x - k * 0.2} ${y - k * 1.1} L ${x + k * 0.9} ${y - k * 0.1}`} stroke={color} strokeWidth={r * 0.16} strokeLinecap="round" />;
};

const Face: FC<{ x: number; y: number; r: number; face: string; dir: number; mouth: boolean; f: number; glow: boolean }> = ({ x, y, r, face, dir, mouth, f, glow }) => {
  const ex = x + dir * r * 0.2;
  const look = Math.sin(f / 37) * r * 0.05;
  const blink = (f % 97) > 92 ? 0.15 : 1;
  const eye = r * 0.15;
  const brow: Record<string, string> = {
    angry: `M ${ex - r * 0.55} ${y - r * 0.45} L ${ex - r * 0.12} ${y - r * 0.25} M ${ex + r * 0.55} ${y - r * 0.45} L ${ex + r * 0.12} ${y - r * 0.25}`,
    worried: `M ${ex - r * 0.5} ${y - r * 0.3} L ${ex - r * 0.12} ${y - r * 0.45} M ${ex + r * 0.5} ${y - r * 0.3} L ${ex + r * 0.12} ${y - r * 0.45}`,
    sad: `M ${ex - r * 0.5} ${y - r * 0.3} L ${ex - r * 0.12} ${y - r * 0.45} M ${ex + r * 0.5} ${y - r * 0.3} L ${ex + r * 0.12} ${y - r * 0.45}`,
    determined: `M ${ex - r * 0.52} ${y - r * 0.42} L ${ex - r * 0.1} ${y - r * 0.3} M ${ex + r * 0.52} ${y - r * 0.42} L ${ex + r * 0.1} ${y - r * 0.3}`,
    surprised: `M ${ex - r * 0.5} ${y - r * 0.55} Q ${ex - r * 0.3} ${y - r * 0.7} ${ex - r * 0.1} ${y - r * 0.55} M ${ex + r * 0.1} ${y - r * 0.55} Q ${ex + r * 0.3} ${y - r * 0.7} ${ex + r * 0.5} ${y - r * 0.55}`,
  };
  const lips: Record<string, string> = {
    happy: `M ${ex - r * 0.3} ${y + r * 0.3} Q ${ex} ${y + r * 0.58} ${ex + r * 0.3} ${y + r * 0.3}`,
    sad: `M ${ex - r * 0.28} ${y + r * 0.5} Q ${ex} ${y + r * 0.28} ${ex + r * 0.28} ${y + r * 0.5}`,
    angry: `M ${ex - r * 0.26} ${y + r * 0.45} L ${ex + r * 0.26} ${y + r * 0.42}`,
    determined: `M ${ex - r * 0.22} ${y + r * 0.42} L ${ex + r * 0.22} ${y + r * 0.42}`,
    worried: `M ${ex - r * 0.28} ${y + r * 0.45} q ${r * 0.14} -${r * 0.1} ${r * 0.28} 0 t ${r * 0.28} 0`,
    neutral: `M ${ex - r * 0.18} ${y + r * 0.42} L ${ex + r * 0.18} ${y + r * 0.42}`,
  };
  const eyeColor = glow ? '#ff3b30' : INK;
  return (
    <g>
      {glow ? <circle cx={ex} cy={y - r * 0.05} r={r * 0.9} fill="url(#cine-eyeglow)" /> : null}
      <ellipse cx={ex - r * 0.3 + look} cy={y - r * 0.05} rx={eye} ry={eye * (face === 'surprised' ? 1.35 : 1.1) * blink} fill={eyeColor} />
      <ellipse cx={ex + r * 0.3 + look} cy={y - r * 0.05} rx={eye} ry={eye * (face === 'surprised' ? 1.35 : 1.1) * blink} fill={eyeColor} />
      {brow[face] ? <path d={brow[face]} stroke={INK} strokeWidth={r * 0.1} strokeLinecap="round" fill="none" /> : null}
      {face === 'sad' ? <path d={`M ${ex + r * 0.32} ${y + r * 0.08} q ${r * 0.05} ${r * 0.18} 0 ${r * 0.28}`} stroke="#7fc4ff" strokeWidth={r * 0.08} fill="none" strokeLinecap="round" opacity={0.8} /> : null}
      {mouth ? (face === 'surprised' || face === 'scared'
        ? <ellipse cx={ex} cy={y + r * 0.45} rx={r * 0.13} ry={r * 0.18} fill={INK} />
        : <path d={lips[face] ?? lips.neutral} stroke={INK} strokeWidth={r * 0.1} strokeLinecap="round" fill="none" />) : null}
    </g>
  );
};

/** One stickman: limbs with a dark outline and a light core, a big round head, the face, the hero's mark. */
const Figure: FC<{ a: CineActor; ground: number; unit: number; W: number; f: number; mark: string; markColor: string; mouth: boolean;
  silhouette: boolean }> = ({ a, ground, unit, W, f, mark, markColor, mouth, silhouette }) => {
  const s = a.size * unit;
  const dir = a.facing === 'left' ? -1 : 1;
  const p = pose(a.pose, f + a.x * 40);
  const hip: Pt = [a.x * W, ground - 190 * s + p.drop];
  const neck = towards(hip, 180 - p.lean, 165 * s, dir);
  const r = 62 * s;
  const head = towards(neck, 180 - p.lean - p.head * 0.5, r * 0.95, dir);
  const limb = (from: Pt, x: number, y: number, l1: number, l2: number) => {
    const mid = towards(from, x, l1, dir);
    return `M ${from[0]} ${from[1]} L ${mid[0]} ${mid[1]} L ${towards(mid, y, l2, dir).join(' ')}`;
  };
  const shadowy = a.who === 'shadow';
  const other = a.who === 'other';
  const fill = silhouette || shadowy ? '#07080b' : other ? '#a9adb6' : BODY;
  const line = silhouette || shadowy ? '#07080b' : INK;
  const w = 13 * s;
  const paths = [limb(neck, p.arms[2], p.arms[3], 92 * s, 88 * s), limb(hip, p.legs[2], p.legs[3], 100 * s, 96 * s),
    `M ${hip[0]} ${hip[1]} L ${neck[0]} ${neck[1]}`, limb(hip, p.legs[0], p.legs[1], 100 * s, 96 * s),
    limb(neck, p.arms[0], p.arms[1], 92 * s, 88 * s)];
  const fallen = a.pose === 'fall' ? `rotate(${p.lean * dir * 0.6} ${hip[0]} ${ground})` : undefined;
  return (
    <g transform={fallen}>
      <ellipse cx={hip[0]} cy={ground + 6 * s} rx={95 * s} ry={14 * s} fill="#000" opacity={0.35} />
      {paths.map((d, i) => (
        <g key={i} opacity={i < 2 ? 0.88 : 1}>
          <path d={d} fill="none" stroke={line} strokeWidth={w * 2.1} strokeLinecap="round" strokeLinejoin="round" />
          <path d={d} fill="none" stroke={fill} strokeWidth={w} strokeLinecap="round" strokeLinejoin="round" />
        </g>
      ))}
      {a.who === 'hero' && mark === 'hood' ? <Mark mark="hood" hx={head[0]} hy={head[1]} r={r} dir={dir} color={markColor} /> : null}
      <circle cx={head[0]} cy={head[1]} r={r} fill={fill} stroke={line} strokeWidth={w * 0.9} />
      {silhouette ? (a.who === 'shadow' || a.face === 'angry' ? <Face x={head[0]} y={head[1]} r={r} face="neutral" dir={dir} mouth={false} f={f} glow /> : null)
        : <Face x={head[0]} y={head[1]} r={r} face={a.face} dir={dir} mouth={mouth && !shadowy} f={f} glow={shadowy} />}
      {(a.who === 'hero' || a.who === 'double') && mark !== 'hood' && !silhouette
        ? <Mark mark={mark} hx={head[0]} hy={head[1]} r={r} dir={dir} color={markColor} /> : null}
      {a.label ? <text x={head[0]} y={head[1] - r * 1.45} textAnchor="middle" fontFamily="Oswald" fontWeight={700}
        fontSize={34 * Math.max(1, unit)} fill="#fff" letterSpacing={3} style={{ paintOrder: 'stroke' }} stroke="#000" strokeWidth={6}>{a.label}</text> : null}
    </g>
  );
};

const handOf = (a: CineActor, ground: number, unit: number, W: number, f: number): Pt => {
  const s = a.size * unit;
  const dir = a.facing === 'left' ? -1 : 1;
  const p = pose(a.pose, f + a.x * 40);
  const hip: Pt = [a.x * W, ground - 190 * s + p.drop];
  const neck = towards(hip, 180 - p.lean, 165 * s, dir);
  return towards(towards(neck, p.arms[0], 92 * s, dir), p.arms[1], 88 * s, dir);
};

// --- the sets: each a few flat layers; the camera moves the far ones less --------------------------------------

interface SetProps { W: number; H: number; g: number; L: Light; f: number; seed: number }
type Layer = { depth: number; node: ReactNode };

const windowGrid = (x: number, y: number, w: number, h: number, cols: number, rows: number, seed: number, lit: string, off: string, f: number) => {
  const out: ReactNode[] = [];
  const cw = w / cols;
  const ch = h / rows;
  for (let c = 0; c < cols; c++) {
    for (let r = 0; r < rows; r++) {
      const on = random(`w${seed}-${c}-${r}`) > 0.62;
      const flick = on && random(`fl${seed}-${c}-${r}`) > 0.97 ? (Math.sin(f / 3 + c) > 0 ? 1 : 0.4) : 1;
      out.push(<rect key={`${c}-${r}`} x={x + c * cw + cw * 0.18} y={y + r * ch + ch * 0.18} width={cw * 0.64} height={ch * 0.6}
        fill={on ? lit : off} opacity={on ? 0.9 * flick : 0.8} />);
    }
  }
  return out;
};

// a light's glow: a radial gradient (soft falloff, no blur filter: cheap and never a flat stain)
const Glow: FC<{ x: number; y: number; r: number; color: string; o?: number }> = ({ x, y, r, color, o = 0.85 }) => {
  const id = `glow-${color.replace('#', '')}`;
  return (
    <g style={{ mixBlendMode: 'screen' }}>
      <defs><radialGradient id={id}><stop offset="0%" stopColor={color} stopOpacity={1} /><stop offset="35%" stopColor={color} stopOpacity={0.45} />
        <stop offset="100%" stopColor={color} stopOpacity={0} /></radialGradient></defs>
      <circle cx={x} cy={y} r={r} fill={`url(#${id})`} opacity={o} />
    </g>
  );
};

const SETS: Record<string, (p: SetProps) => Layer[]> = {
  bedroom: ({ W, H, g, L, seed }) => [
    { depth: 0.3, node: <><rect width={W} height={g} fill={L.wall} /><rect x={W * 0.58} y={g * 0.22} width={W * 0.24} height={g * 0.38} fill="#0d1526" stroke="#000" strokeWidth={10} />
      <circle cx={W * 0.74} cy={g * 0.3} r={W * 0.018} fill="#e8eefc" /><Glow x={W * 0.74} y={g * 0.3} r={W * 0.05} color="#9fb6ff" o={0.5} />
      <rect x={W * 0.14} y={g * 0.24} width={W * 0.1} height={g * 0.2} fill="#2b2230" stroke="#000" strokeWidth={6} /></> },
    { depth: 1, node: <><rect y={g} width={W} height={H - g} fill={L.floor} />
      <rect x={W * 0.05} y={g - H * 0.1} width={W * 0.34} height={H * 0.1} rx={12} fill="#2c3550" /><rect x={W * 0.05} y={g - H * 0.14} width={W * 0.09} height={H * 0.05} rx={14} fill="#d9d4c8" />
      <rect x={W * 0.42} y={g - H * 0.09} width={W * 0.06} height={H * 0.09} fill="#3a2a22" /><path d={`M ${W * 0.43} ${g - H * 0.09} l ${W * 0.02} -${H * 0.07} l ${W * 0.02} ${H * 0.07} Z`} fill={L.practical} />
      <Glow x={W * 0.45} y={g - H * 0.13} r={W * 0.12} color={L.practical} o={0.45} />{seed % 2 ? null : <rect x={W * 0.06} y={g + H * 0.03} width={W * 0.3} height={H * 0.04} fill="#000" opacity={0.25} />}</> },
  ],
  hallway: ({ W, H, g, L, f }) => {
    const vx = W * 0.5;
    const vy = g * 0.62;
    const lights = [0.25, 0.48, 0.66, 0.8];
    return [{ depth: 0.6, node: <>
      <rect width={W} height={H} fill={L.wall} />
      <path d={`M 0 0 L ${vx - W * 0.08} ${vy - H * 0.08} L ${vx + W * 0.08} ${vy - H * 0.08} L ${W} 0 Z`} fill="#0e0f14" />
      <path d={`M 0 ${H} L ${vx - W * 0.08} ${vy + H * 0.06} L ${vx + W * 0.08} ${vy + H * 0.06} L ${W} ${H} Z`} fill="#5a1e1e" />
      <path d={`M 0 0 L ${vx - W * 0.08} ${vy - H * 0.08} L ${vx - W * 0.08} ${vy + H * 0.06} L 0 ${H} Z`} fill="#25463c" />
      <path d={`M ${W} 0 L ${vx + W * 0.08} ${vy - H * 0.08} L ${vx + W * 0.08} ${vy + H * 0.06} L ${W} ${H} Z`} fill="#1f3c33" />
      <rect x={vx - W * 0.08} y={vy - H * 0.08} width={W * 0.16} height={H * 0.14} fill="#0a0a0d" />
      {[0.2, 0.45, 0.68].map((t, i) => <g key={i}>
        <path d={`M ${t * (vx - W * 0.08)} ${t * (vy - H * 0.08) + H * 0.2 * (1 - t)} l ${W * 0.06 * (1 - t * 0.8)} ${H * 0.02 * (1 - t)} l 0 ${H * 0.36 * (1 - t * 0.9)} l -${W * 0.06 * (1 - t * 0.8)} ${H * 0.04 * (1 - t)} Z`} fill="#6b3a24" opacity={0.9} />
        <path d={`M ${W - t * (W - vx - W * 0.08)} ${t * (vy - H * 0.08) + H * 0.2 * (1 - t)} l -${W * 0.06 * (1 - t * 0.8)} ${H * 0.02 * (1 - t)} l 0 ${H * 0.36 * (1 - t * 0.9)} l ${W * 0.06 * (1 - t * 0.8)} ${H * 0.04 * (1 - t)} Z`} fill="#6b3a24" opacity={0.9} /></g>)}
      {lights.map((t, i) => <g key={i}><ellipse cx={vx} cy={(vy - H * 0.08) * t} rx={W * 0.07 * (1.1 - t)} ry={H * 0.012 * (1.1 - t)} fill="#fff6dc" />
        <Glow x={vx} y={(vy - H * 0.08) * t + H * 0.03} r={W * 0.16 * (1.1 - t)} color={L.practical} o={0.35 + 0.08 * Math.sin(f / 9 + i)} /></g>)}
    </> }];
  },
  door: ({ W, H, g, L, f }) => {
    const flick = 0.75 + 0.25 * Math.sin(f / 4) * Math.sin(f / 7.3);
    return [
      { depth: 0.5, node: <><rect width={W} height={H} fill={L.wall} /><rect x={W * 0.28} y={g * 0.1} width={W * 0.44} height={g * 0.9} fill="#3d2418" stroke="#000" strokeWidth={14} />
        <rect x={W * 0.33} y={g * 0.18} width={W * 0.34} height={g * 0.3} fill="#33200f" stroke="#1c120a" strokeWidth={6} /><rect x={W * 0.33} y={g * 0.54} width={W * 0.34} height={g * 0.36} fill="#33200f" stroke="#1c120a" strokeWidth={6} />
        <circle cx={W * 0.65} cy={g * 0.55} r={W * 0.012} fill="#d8b46a" /><circle cx={W * 0.5} cy={g * 0.3} r={W * 0.008} fill="#000" stroke="#9a8a6a" strokeWidth={3} /></> },
      { depth: 1, node: <><rect y={g} width={W} height={H - g} fill={L.floor} /><rect x={W * 0.28} y={g - 6} width={W * 0.44} height={10} fill={L.practical} opacity={flick} />
        <path d={`M ${W * 0.28} ${g} L ${W * 0.72} ${g} L ${W * 0.95} ${H} L ${W * 0.05} ${H} Z`} fill={L.practical} opacity={0.22 * flick} />
        <Glow x={W * 0.5} y={g} r={W * 0.2} color={L.practical} o={0.55 * flick} /></> },
    ];
  },
  living: ({ W, H, g, L, f, seed }) => [
    { depth: 0.25, node: <><rect width={W} height={g} fill={L.wall} /><rect x={W * 0.08} y={g * 0.18} width={W * 0.36} height={g * 0.45} fill="#0b1222" stroke="#000" strokeWidth={10} />
      {windowGrid(W * 0.1, g * 0.3, W * 0.32, g * 0.3, 9, 4, seed, '#f2c46a', '#1a2236', f)}</> },
    { depth: 1, node: <><rect y={g} width={W} height={H - g} fill={L.floor} /><rect x={W * 0.5} y={g - H * 0.16} width={W * 0.4} height={H * 0.1} rx={18} fill="#2f3d5c" />
      <rect x={W * 0.5} y={g - H * 0.07} width={W * 0.4} height={H * 0.07} rx={10} fill="#25304a" />
      <rect x={W * 0.12} y={g - H * 0.2} width={W * 0.18} height={H * 0.11} fill="#0a0d14" stroke="#222" strokeWidth={6} />
      <rect x={W * 0.125} y={g - H * 0.195} width={W * 0.17} height={H * 0.1} fill={L.fill} opacity={0.55 + 0.2 * Math.sin(f / 5)} />
      <Glow x={W * 0.21} y={g - H * 0.14} r={W * 0.16} color={L.fill} o={0.4} /></> },
  ],
  street: ({ W, H, g, L, f, seed }) => [
    { depth: 0.2, node: <>{[0, 1, 2, 3, 4, 5].map((i) => { const x = (i / 6) * W; const h = g * (0.45 + random(`b${seed}${i}`) * 0.4);
      return <g key={i}><rect x={x} y={g - h} width={W / 6 - 8} height={h} fill="#141a29" />{windowGrid(x + 10, g - h + 20, W / 6 - 28, h - 40, 4, 7, seed + i, '#f6c96b', '#0d1220', f)}</g>; })}</> },
    { depth: 1, node: <><rect y={g} width={W} height={H - g} fill="#1d2027" /><rect y={g} width={W} height={H * 0.025} fill="#3a3d45" />
      {[0, 1, 2, 3, 4, 5, 6].map((i) => <rect key={i} x={((i * W) / 6 - (f * 4) % (W / 6))} y={g + (H - g) * 0.55} width={W / 14} height={8} fill="#d8c25a" opacity={0.7} />)}
      {[0.18, 0.82].map((x) => <g key={x}><rect x={W * x} y={g - H * 0.42} width={10} height={H * 0.42} fill="#2b2f38" /><circle cx={W * x + 5} cy={g - H * 0.42} r={14} fill="#ffe2a8" />
        <Glow x={W * x + 5} y={g - H * 0.4} r={W * 0.12} color={L.practical} o={0.5} /><path d={`M ${W * x - W * 0.07} ${g + 2} L ${W * x + W * 0.08} ${g + 2} L ${W * x + 5} ${g - H * 0.4} Z`} fill={L.practical} opacity={0.08} /></g>)}</> },
  ],
  city: ({ W, H, g, f, seed, L }) => [
    { depth: 0.4, node: <><rect width={W} height={H} fill="#1b2130" /><rect x={W * 0.04} y={-H * 0.05} width={W * 0.92} height={H * 1.1} fill="#262c3c" />
      {windowGrid(W * 0.06, H * 0.02, W * 0.88, H * 0.96, 7, 11, seed, '#f3c967', '#1c2333', f)}</> },
    { depth: 0.7, node: <Glow x={W * 0.5} y={H * 0.5} r={W * 0.4} color={L.fill} o={0.15} /> },
  ],
  above: ({ W, H, f, seed }) => {
    const cars: ReactNode[] = [];
    for (let i = 0; i < 14; i++) {
      const lane = i % 4;
      const speed = 2 + random(`cs${seed}${i}`) * 4;
      const y = ((random(`cy${seed}${i}`) * H * 1.4 + f * speed * (lane < 2 ? 1 : -1)) % (H * 1.4) + H * 1.4) % (H * 1.4) - H * 0.2;
      const colors = ['#e53935', '#f5b301', '#1e88e5', '#eceff1', '#43a047', '#5e35b1'];
      cars.push(<rect key={i} x={W * (0.36 + lane * 0.075)} y={y} width={W * 0.045} height={H * 0.05} rx={8} fill={colors[i % colors.length]} stroke="#000" strokeWidth={3} />);
    }
    const people: ReactNode[] = [];
    for (let i = 0; i < 30; i++) {
      const side = i % 2 ? W * (0.24 + random(`px${seed}${i}`) * 0.08) : W * (0.7 + random(`px${seed}${i}`) * 0.08);
      const y = ((random(`py${seed}${i}`) * H + f * (1 + random(`ps${seed}${i}`) * 3) * (i % 3 ? 1 : -1)) % H + H) % H;
      people.push(<circle key={i} cx={side} cy={y} r={W * 0.006} fill="#efe9dc" stroke="#000" strokeWidth={2} />);
    }
    return [{ depth: 1, node: <><rect width={W} height={H} fill="#2a2e36" /><rect x={W * 0.34} width={W * 0.32} height={H} fill="#1c1f25" />
      {[1, 2, 3].map((i) => <line key={i} x1={W * (0.34 + i * 0.08)} x2={W * (0.34 + i * 0.08)} y1={0} y2={H} stroke={i === 2 ? '#e6c23a' : '#9aa0aa'} strokeWidth={i === 2 ? 6 : 4} strokeDasharray={i === 2 ? undefined : '40 40'} />)}
      <rect width={W * 0.2} height={H} fill="#141821" /><rect x={W * 0.8} width={W * 0.2} height={H} fill="#141821" />{windowGrid(0, 0, W * 0.2, H, 3, 10, seed, '#f3c967', '#1b202b', f)}
      {cars}{people}</> }];
  },
  rooftop: ({ W, H, g, f, seed }) => [
    { depth: 0.15, node: <><rect width={W} height={H} fill="url(#cine-sky)" />{[...Array(40)].map((_, i) => <circle key={i} cx={random(`s${i}`) * W} cy={random(`t${i}`) * g * 0.5} r={1.6} fill="#fff" opacity={0.4 + 0.4 * Math.sin(f / 10 + i)} />)}</> },
    { depth: 0.35, node: <>{[...Array(9)].map((_, i) => { const h = g * (0.2 + random(`r${seed}${i}`) * 0.35); const x = (i / 9) * W;
      return <g key={i}><rect x={x} y={g - h} width={W / 9 - 6} height={h} fill="#0f1420" />{windowGrid(x + 6, g - h + 10, W / 9 - 18, h - 20, 3, 6, seed + i * 3, '#f2c46a', '#0c111b', f)}</g>; })}</> },
    { depth: 1, node: <><rect y={g} width={W} height={H - g} fill="#22252d" /><rect y={g - 12} width={W} height={24} fill="#3a3e48" /></> },
  ],
  office: ({ W, H, g, L, f }) => [
    { depth: 0.3, node: <><rect width={W} height={g} fill={L.wall} />{[0.1, 0.4, 0.7].map((x) => <g key={x}><rect x={W * x} y={g * 0.15} width={W * 0.2} height={g * 0.45} fill="#122038" />
      {[...Array(9)].map((_, i) => <rect key={i} x={W * x} y={g * 0.15 + i * g * 0.05} width={W * 0.2} height={g * 0.02} fill="#3b4660" opacity={0.7} />)}</g>)}</> },
    { depth: 1, node: <><rect y={g} width={W} height={H - g} fill={L.floor} />{[0.2, 0.62].map((x) => <g key={x}><rect x={W * x} y={g - H * 0.09} width={W * 0.24} height={H * 0.02} fill="#5b4636" />
      <rect x={W * (x + 0.06)} y={g - H * 0.19} width={W * 0.11} height={H * 0.1} fill="#0b0e15" stroke="#2c3240" strokeWidth={5} />
      <rect x={W * (x + 0.065)} y={g - H * 0.185} width={W * 0.1} height={H * 0.09} fill={L.fill} opacity={0.5 + 0.1 * Math.sin(f / 7 + x * 9)} />
      <Glow x={W * (x + 0.115)} y={g - H * 0.14} r={W * 0.1} color={L.fill} o={0.35} /></g>)}</> },
  ],
  gym: ({ W, H, g, L }) => [
    { depth: 0.3, node: <><rect width={W} height={g} fill="#1a1c22" /><rect x={W * 0.55} y={g * 0.2} width={W * 0.35} height={g * 0.7} fill="#2a3140" stroke="#555" strokeWidth={6} />
      {[0.2, 0.3, 0.4].map((y, i) => <g key={i}><rect x={W * 0.06} y={g * y + g * 0.2} width={W * 0.3} height={8} fill="#666" />{[0, 1, 2, 3, 4].map((k) => <circle key={k} cx={W * (0.08 + k * 0.06)} cy={g * y + g * 0.2} r={18 + k * 2} fill="#222" stroke="#555" strokeWidth={4} />)}</g>)}</> },
    { depth: 1, node: <><rect y={g} width={W} height={H - g} fill="#202020" />{[...Array(10)].map((_, i) => <line key={i} x1={(i / 10) * W} x2={(i / 10) * W - W * 0.1} y1={g} y2={H} stroke="#2c2c2c" strokeWidth={4} />)}
      <path d={`M ${W * 0.35} 0 L ${W * 0.65} 0 L ${W * 0.8} ${H} L ${W * 0.2} ${H} Z`} fill={L.practical} opacity={0.08} /><Glow x={W * 0.5} y={0} r={W * 0.2} color={L.practical} o={0.5} /></> },
  ],
  desk: ({ W, H, g, L, f }) => [
    { depth: 0.3, node: <><rect width={W} height={g} fill={L.wall} /><rect x={W * 0.62} y={g * 0.12} width={W * 0.22} height={g * 0.42} fill="#0b1222" stroke="#000" strokeWidth={8} />
      <circle cx={W * 0.78} cy={g * 0.22} r={W * 0.014} fill="#f4f1e8" /><rect x={W * 0.1} y={g * 0.2} width={W * 0.2} height={g * 0.05} fill="#3b2a1f" />{[0, 1, 2, 3, 4].map((i) => <rect key={i} x={W * (0.11 + i * 0.035)} y={g * 0.11} width={W * 0.025} height={g * 0.09} fill={['#7a2e2e', '#2e4f7a', '#3d6b3a', '#7a6a2e', '#5b3a6e'][i]} />)}</> },
    { depth: 1, node: <><rect y={g} width={W} height={H - g} fill={L.floor} /><rect x={W * 0.25} y={g - H * 0.08} width={W * 0.5} height={H * 0.025} fill="#4a3324" />
      <path d={`M ${W * 0.42} ${g - H * 0.08} l ${W * 0.02} -${H * 0.1} l ${W * 0.14} 0 l -${W * 0.02} ${H * 0.1} Z`} fill="#11151e" stroke="#30384a" strokeWidth={4} />
      <Glow x={W * 0.5} y={g - H * 0.14} r={W * 0.16} color={L.fill} o={0.45 + 0.05 * Math.sin(f / 6)} />
      <path d={`M ${W * 0.3} ${g - H * 0.08} l 0 -${H * 0.12} l ${W * 0.04} -${H * 0.03}`} stroke="#222" strokeWidth={8} fill="none" /><Glow x={W * 0.34} y={g - H * 0.22} r={W * 0.1} color={L.practical} o={0.6} /></> },
  ],
  mirror: ({ W, H, g, L }) => [
    { depth: 0.6, node: <><rect width={W} height={H} fill={L.wall} /><rect x={W * 0.3} y={g * 0.12} width={W * 0.4} height={g * 0.78} fill="#1d2a36" stroke="#0a0a0a" strokeWidth={16} />
      <rect x={W * 0.32} y={g * 0.14} width={W * 0.36} height={g * 0.74} fill="url(#cine-mirror)" /><Glow x={W * 0.5} y={g * 0.08} r={W * 0.12} color={L.practical} o={0.5} /></> },
    { depth: 1, node: <><rect y={g} width={W} height={H - g} fill={L.floor} /><rect x={W * 0.25} y={g - H * 0.04} width={W * 0.5} height={H * 0.05} fill="#d8d6d0" /></> },
  ],
  void: ({ W, H, g, L }) => [
    { depth: 0.5, node: <><rect width={W} height={H} fill="#06070a" /><path d={`M ${W * 0.44} 0 L ${W * 0.56} 0 L ${W * 0.78} ${g + H * 0.04} L ${W * 0.22} ${g + H * 0.04} Z`} fill={L.practical} opacity={0.1} /></> },
    { depth: 1, node: <><ellipse cx={W * 0.5} cy={g + 4} rx={W * 0.28} ry={H * 0.04} fill={L.practical} opacity={0.22} /><Glow x={W * 0.5} y={g} r={W * 0.2} color={L.practical} o={0.25} /></> },
  ],
  space: ({ W, H, g, f }) => [
    { depth: 0.1, node: <><rect width={W} height={H} fill="#03040a" />{[...Array(120)].map((_, i) => <circle key={i} cx={random(`x${i}`) * W} cy={random(`y${i}`) * H} r={random(`r${i}`) * 2.2 + 0.4} fill="#fff" opacity={0.3 + 0.6 * random(`o${i}`) * (0.7 + 0.3 * Math.sin(f / 8 + i))} />)}</> },
    { depth: 0.3, node: <><circle cx={W * 0.78} cy={H * 0.3} r={Math.min(W, H) * 0.22} fill="url(#cine-planet)" /><Glow x={W * 0.78} y={H * 0.3} r={Math.min(W, H) * 0.3} color="#4aa3ff" o={0.25} /></> },
    { depth: 1, node: <path d={`M 0 ${g} Q ${W * 0.5} ${g - H * 0.05} ${W} ${g} L ${W} ${H} L 0 ${H} Z`} fill="#2a2c33" /> },
  ],
  lab: ({ W, H, g, L, f }) => [
    { depth: 0.3, node: <><rect width={W} height={g} fill="#14202a" />{[0.08, 0.38, 0.68].map((x, k) => <g key={x}><rect x={W * x} y={g * 0.15} width={W * 0.24} height={g * 0.4} fill="#071018" stroke="#2c4a5a" strokeWidth={6} />
      <polyline points={[...Array(24)].map((_, i) => `${W * x + (i / 23) * W * 0.24},${g * 0.35 + Math.sin(i / 2 + f / 8 + k) * g * 0.08}`).join(' ')} fill="none" stroke="#3cf0b0" strokeWidth={4} /></g>)}</> },
    { depth: 1, node: <><rect y={g} width={W} height={H - g} fill="#1a2228" /><rect x={W * 0.1} y={g - H * 0.08} width={W * 0.8} height={H * 0.02} fill="#3a4a54" />
      {[0.2, 0.3, 0.7, 0.8].map((x, i) => <g key={x}><rect x={W * x} y={g - H * 0.16} width={W * 0.025} height={H * 0.08} rx={8} fill="none" stroke="#9fd" strokeWidth={4} />
        <rect x={W * x + 4} y={g - H * 0.11} width={W * 0.025 - 8} height={H * 0.025} fill={['#3cf0b0', '#ff5aa0', '#ffd23c', '#5ac8ff'][i]} /></g>)}<Glow x={W * 0.5} y={g * 0.4} r={W * 0.3} color="#3cf0b0" o={0.12} /></> },
  ],
  classroom: ({ W, H, g, L }) => [
    { depth: 0.3, node: <><rect width={W} height={g} fill="#3a3f36" /><rect x={W * 0.2} y={g * 0.15} width={W * 0.6} height={g * 0.45} fill="#1e3a2c" stroke="#5a3e25" strokeWidth={14} />
      <path d={`M ${W * 0.26} ${g * 0.3} q ${W * 0.05} -${g * 0.05} ${W * 0.1} 0 t ${W * 0.1} 0 M ${W * 0.5} ${g * 0.28} l ${W * 0.2} 0 M ${W * 0.5} ${g * 0.4} l ${W * 0.14} 0`} stroke="#e8e8dc" strokeWidth={5} fill="none" opacity={0.7} /></> },
    { depth: 1, node: <><rect y={g} width={W} height={H - g} fill="#5b4532" />{[0.1, 0.42, 0.74].map((x) => <rect key={x} x={W * x} y={g - H * 0.07} width={W * 0.18} height={H * 0.02} fill="#8a6a4a" />)}<Glow x={W * 0.5} y={0} r={W * 0.3} color={L.practical} o={0.2} /></> },
  ],
  nature: ({ W, H, g, f }) => [
    { depth: 0.1, node: <><rect width={W} height={H} fill="url(#cine-dawn)" /><circle cx={W * 0.5} cy={g * 0.78} r={Math.min(W, H) * 0.11} fill="#ffd38a" /><Glow x={W * 0.5} y={g * 0.78} r={Math.min(W, H) * 0.35} color="#ffb060" o={0.5} /></> },
    { depth: 0.35, node: <path d={`M 0 ${g * 0.85} Q ${W * 0.25} ${g * 0.6} ${W * 0.5} ${g * 0.82} T ${W} ${g * 0.75} L ${W} ${g} L 0 ${g} Z`} fill="#4a3550" /> },
    { depth: 1, node: <><path d={`M 0 ${g} Q ${W * 0.5} ${g - H * 0.04} ${W} ${g} L ${W} ${H} L 0 ${H} Z`} fill="#2a2235" />{[0.08, 0.86, 0.94].map((x) => <path key={x} d={`M ${W * x} ${g} l ${W * 0.04} -${H * 0.22} l ${W * 0.04} ${H * 0.22} Z`} fill="#1a1424" />)}
      {[...Array(12)].map((_, i) => <circle key={i} cx={(random(`n${i}`) * W + f * 0.6) % W} cy={g * 0.3 + random(`m${i}`) * g * 0.4} r={2.5} fill="#ffe6b0" opacity={0.5} />)}</> },
  ],
  rain: ({ W, H, g, f, seed }) => [
    { depth: 0.15, node: <><rect width={W} height={H} fill="#0d1420" />{[...Array(26)].map((_, i) => <circle key={i} cx={random(`k${seed}${i}`) * W} cy={g * 0.3 + random(`l${seed}${i}`) * g * 0.6} r={10 + random(`q${i}`) * 30} fill={['#f2b45a', '#e85a5a', '#5ab4f2'][i % 3]} opacity={0.18} filter="url(#cine-soft)" />)}</> },
    { depth: 0.6, node: <><rect x={W * 0.08} y={g * 0.06} width={W * 0.84} height={g * 0.86} fill="none" stroke="#1d1f26" strokeWidth={28} /><line x1={W * 0.5} x2={W * 0.5} y1={g * 0.06} y2={g * 0.92} stroke="#1d1f26" strokeWidth={18} />
      {[...Array(70)].map((_, i) => { const x = random(`rx${i}`) * W; const y = ((random(`ry${i}`) * H + f * (18 + random(`rv${i}`) * 10)) % H);
        return <line key={i} x1={x} x2={x - 6} y1={y} y2={y + 40} stroke="#9fb4d6" strokeWidth={2} opacity={0.45} />; })}</> },
    { depth: 1, node: <rect y={g} width={W} height={H - g} fill="#16181e" /> },
  ],
  stairs: ({ W, H, g, f }) => [
    { depth: 0.5, node: <><rect width={W} height={H} fill="#22262c" />{[...Array(9)].map((_, i) => <rect key={i} x={W * 0.1 + i * W * 0.09} y={g - (i + 1) * H * 0.06} width={W * 0.1} height={(i + 1) * H * 0.06} fill={i % 2 ? '#30353d' : '#2b3037'} />)}
      <polyline points={[...Array(10)].map((_, i) => `${W * 0.1 + i * W * 0.09},${g - (i + 1) * H * 0.06 - H * 0.12}`).join(' ')} stroke="#8a8f99" strokeWidth={8} fill="none" />
      <rect x={W * 0.78} y={H * 0.08} width={W * 0.1} height={H * 0.05} rx={6} fill="#13a85a" opacity={0.6 + 0.4 * (Math.sin(f / 3) > -0.8 ? 1 : 0)} /><Glow x={W * 0.83} y={H * 0.1} r={W * 0.1} color="#13e07a" o={0.4} /></> },
    { depth: 1, node: <rect y={g} width={W} height={H - g} fill="#1b1e23" /> },
  ],
  hospital: ({ W, H, g, f }) => [
    { depth: 0.3, node: <><rect width={W} height={g} fill="#c9d3d6" /><rect x={W * 0.66} y={g * 0.22} width={W * 0.18} height={g * 0.24} fill="#0b1015" stroke="#555" strokeWidth={6} />
      <polyline points={[...Array(30)].map((_, i) => { const x = (i / 29) * W * 0.17; const beat = ((i + Math.floor(f / 2)) % 12) === 0 ? -g * 0.08 : ((i + Math.floor(f / 2)) % 12) === 1 ? g * 0.05 : 0;
        return `${W * 0.665 + x},${g * 0.34 + beat}`; }).join(' ')} stroke="#3cf07a" strokeWidth={4} fill="none" /></> },
    { depth: 1, node: <><rect y={g} width={W} height={H - g} fill="#9aa5a8" /><rect x={W * 0.12} y={g - H * 0.1} width={W * 0.4} height={H * 0.08} rx={10} fill="#eef2f3" stroke="#7a8488" strokeWidth={5} /></> },
  ],
};
export const CINE_SETS = Object.keys(SETS);

// --- overlays ----------------------------------------------------------------------------------------------------

const Captions: FC<{ words: { t: string; f: number; key?: boolean }[]; f: number; W: number; H: number; vertical: boolean; accent: string }> = ({ words, f, W, H, vertical, accent }) => {
  if (!words.length) return null;
  // chunks of up to 3 words (a pause or a sentence end closes one); the word being said lights up
  const chunks: typeof words[] = [];
  words.forEach((w, i) => {
    const prev = words[i - 1];
    if (!chunks.length || chunks[chunks.length - 1].length >= 3 || (prev && (w.f - prev.f > 14 || /[.!?,;:]$/.test(prev.t)))) chunks.push([]);
    chunks[chunks.length - 1].push(w);
  });
  let current: typeof words | null = null;
  for (const c of chunks) if (c[0].f <= f) current = c;
  if (!current) return null;
  const at = current[0].f;
  const pop = interpolate(f - at, [0, 4], [0.86, 1], { extrapolateRight: 'clamp' });
  const size = vertical ? W * 0.075 : H * 0.075;
  return (
    <div style={{ position: 'absolute', left: 0, right: 0, top: vertical ? H * 0.6 : H * 0.8, textAlign: 'center', transform: `scale(${pop})` }}>
      {current.map((w, i) => {
        const said = w.f <= f;
        return <span key={i} style={{ fontFamily: 'Poppins', fontWeight: 700, fontSize: size, margin: `0 ${size * 0.14}px`, textTransform: 'uppercase',
          color: said && w.key ? accent : '#fff', opacity: said ? 1 : 0.0, WebkitTextStroke: `${size * 0.09}px #000`, paintOrder: 'stroke fill',
          textShadow: '0 6px 0 rgba(0,0,0,0.6)', letterSpacing: 1 }}>{w.t.replace(/[.,;:]+$/, '')}</span>;
      })}
    </div>
  );
};

const Hud: FC<{ day?: string; clock?: string; place?: string; W: number; H: number; vertical: boolean }> = ({ day, clock, place, W, H, vertical }) => {
  if (!clock && !day) return null;
  const u = vertical ? W / 1080 : H / 1080;
  const [time, ampm] = (clock ?? '').split(' ');
  return (
    <div style={{ position: 'absolute', left: 42 * u, top: (vertical ? 120 : 40) * u, fontFamily: "'JetBrains Mono'", color: '#fff' }}>
      {day ? <div style={{ fontSize: 18 * u, color: RED, letterSpacing: 3 }}>● {day}</div> : null}
      {clock ? <div style={{ fontSize: 64 * u, fontWeight: 700, lineHeight: 1.05, textShadow: '0 3px 10px rgba(0,0,0,0.7)' }}>{time}<span style={{ fontSize: 22 * u, marginLeft: 6 * u }}>{ampm ?? ''}</span></div> : null}
      {place ? <div style={{ fontSize: 16 * u, opacity: 0.6, letterSpacing: 3, borderTop: '2px solid rgba(255,255,255,0.35)', paddingTop: 4 * u, marginTop: 4 * u, width: 150 * u }}>{place}</div> : null}
    </div>
  );
};

const Sticker: FC<{ n: number; text: string; f: number; fps: number; W: number; H: number; vertical: boolean; word: string }> = ({ n, text, f, fps, W, H, vertical, word }) => {
  const s = spring({ frame: f, fps, config: { damping: 11, stiffness: 170 } });
  const u = vertical ? W / 1080 : H / 1080;
  return (
    <div style={{ position: 'absolute', left: 0, right: 0, top: (vertical ? 270 : 90) * u, display: 'flex', flexDirection: 'column', alignItems: 'center',
      transform: `scale(${0.55 + 0.45 * s}) rotate(${-3 + 3 * (1 - s)}deg)`, opacity: clamp(s * 2) }}>
      <div style={{ background: RED, color: '#fff', fontFamily: 'Oswald', fontWeight: 700, fontSize: 22 * u, padding: `${2 * u}px ${10 * u}px`, letterSpacing: 2, borderRadius: 4 }}>{word} #{n}</div>
      <div style={{ fontFamily: 'Oswald', fontWeight: 700, fontSize: 92 * u, color: '#fff', textTransform: 'uppercase', lineHeight: 1.05, textAlign: 'center',
        maxWidth: W * 0.92, textShadow: '0 6px 18px rgba(0,0,0,0.8)', borderBottom: `${6 * u}px solid ${RED}`, padding: `0 ${10 * u}px` }}>{text}</div>
    </div>
  );
};

const BigTitle: FC<{ text: string; f: number; fps: number; W: number; H: number; vertical: boolean }> = ({ text, f, fps, W, H, vertical }) => {
  const s = spring({ frame: f, fps, config: { damping: 13, stiffness: 140 } });
  const u = vertical ? W / 1080 : H / 1080;
  return (
    <div style={{ position: 'absolute', left: 0, right: 0, top: vertical ? H * 0.16 : H * 0.12, textAlign: 'center', transform: `translateY(${(1 - s) * 40}px)`, opacity: s }}>
      <span style={{ fontFamily: 'Oswald', fontWeight: 700, fontSize: (vertical ? 150 : 170) * u, color: '#fff', textTransform: 'uppercase', letterSpacing: 2,
        WebkitTextStroke: `${4 * u}px #000`, paintOrder: 'stroke fill', textShadow: '0 10px 30px rgba(0,0,0,0.7)' }}>{text}</span>
    </div>
  );
};

const Counter: FC<{ label: string; value: string; color: string; f: number; fps: number; W: number; H: number; vertical: boolean }> = ({ label, value, color, f, fps, W, H, vertical }) => {
  const s = spring({ frame: f, fps, config: { damping: 12, stiffness: 160 } });
  const u = vertical ? W / 1080 : H / 1080;
  // a figure counts up to its value as it comes in (digits only; the rest stays)
  const digits = value.match(/\d+/);
  const shown = digits ? value.replace(digits[0], String(Math.round(Number(digits[0]) * clamp(f / 18)))) : value;
  return (
    <div style={{ position: 'absolute', right: 44 * u, top: (vertical ? 120 : 44) * u, transform: `scale(${s})`, transformOrigin: '100% 0', textAlign: 'right' }}>
      {label ? <div style={{ fontFamily: 'Oswald', fontWeight: 700, fontSize: 24 * u, color: '#fff', letterSpacing: 2, opacity: 0.8 }}>{label}</div> : null}
      <div style={{ display: 'inline-block', fontFamily: "'JetBrains Mono'", fontWeight: 700, fontSize: 64 * u, color, border: `${4 * u}px solid ${color}`, borderRadius: 10 * u,
        padding: `${2 * u}px ${16 * u}px`, background: 'rgba(0,0,0,0.55)', textShadow: `0 0 18px ${color}` }}>{shown}</div>
    </div>
  );
};

const Phone: FC<{ messages: string[]; from: string; f: number; dur: number; fps: number; W: number; H: number; typing: boolean; light: Light }> = ({ messages, from, f, dur, fps, W, H, typing, light }) => {
  const m = Math.min(W, H);
  const pw = Math.min(m * 0.56, H * 0.86 / 2.05);
  const ph = pw * 2.05;
  const x = W / 2 - pw / 2;
  const y = H * 0.5 - ph * 0.52 + Math.sin(f / 23) * 6;
  const shown = Math.max(1, Math.ceil(messages.length * clamp(f / (dur * 0.7))));
  return (
    <AbsoluteFill style={{ background: `radial-gradient(ellipse at 50% 40%, ${light.top} 0%, #06060a 80%)` }}>
      <svg width={W} height={H} style={{ position: 'absolute' }}>
        <rect x={x} y={y} width={pw} height={ph} rx={pw * 0.13} fill="#0a0a0c" stroke="#2a2a30" strokeWidth={pw * 0.03} />
        <rect x={x + pw * 0.38} y={y + pw * 0.05} width={pw * 0.24} height={pw * 0.06} rx={pw * 0.03} fill="#000" />
        <circle cx={W / 2} cy={y + pw * 0.2} r={pw * 0.05} fill="#9a9aa2" />
        <text x={W / 2} y={y + pw * 0.31} textAnchor="middle" fill="#ddd" fontFamily="Inter" fontSize={pw * 0.04}>{from}</text>
        {messages.slice(0, shown).map((text, i) => {
          const lines = text.match(/.{1,26}(\s|$)/g) ?? [text];
          const top = y + pw * 0.42 + i * pw * 0.2;
          const pop = spring({ frame: f - (i * dur * 0.7) / messages.length, fps, config: { damping: 14 } });
          return <g key={i} opacity={pop} transform={`translate(0 ${(1 - pop) * 20})`}>
            <rect x={x + pw * 0.08} y={top} width={pw * 0.78} height={pw * (0.07 + 0.055 * lines.length)} rx={pw * 0.05} fill="#2c2c33" />
            {lines.map((line, k) => <text key={k} x={x + pw * 0.13} y={top + pw * (0.075 + k * 0.055)} fill="#f2f2f2" fontFamily="Inter" fontSize={pw * 0.045}>{line.trim()}</text>)}
          </g>;
        })}
        {typing ? <g>{[0, 1, 2].map((i) => <circle key={i} cx={x + pw * (0.14 + i * 0.05)} cy={y + pw * 0.48 + messages.length * pw * 0.2} r={pw * 0.015} fill="#bbb" opacity={0.4 + 0.6 * (Math.floor(f / 6) % 3 === i ? 1 : 0)} />)}</g> : null}
        {/* two stick thumbs */}
        {[-1, 1].map((d) => <g key={d}>
          <path d={`M ${W / 2 + d * pw * 0.62} ${H} L ${W / 2 + d * pw * 0.62} ${y + ph * 0.72} L ${W / 2 + d * pw * 0.42} ${y + ph * 0.6}`} fill="none" stroke={INK} strokeWidth={m * 0.07} strokeLinecap="round" strokeLinejoin="round" />
          <path d={`M ${W / 2 + d * pw * 0.62} ${H} L ${W / 2 + d * pw * 0.62} ${y + ph * 0.72} L ${W / 2 + d * pw * 0.42} ${y + ph * 0.6}`} fill="none" stroke={BODY} strokeWidth={m * 0.04} strokeLinecap="round" strokeLinejoin="round" /></g>)}
      </svg>
    </AbsoluteFill>
  );
};

const Choice: FC<{ question: string; a: string; b: string; f: number; fps: number; W: number; H: number; vertical: boolean; comment: string }> = ({ question, a, b, f, fps, W, H, vertical, comment }) => {
  const s = spring({ frame: f, fps, config: { damping: 12 } });
  const u = vertical ? W / 1080 : H / 1080;
  const pill = (text: string, color: string, k: number) => {
    const t = spring({ frame: f - 8 - k * 6, fps, config: { damping: 12 } });
    return <div style={{ display: 'inline-block', margin: 12 * u, padding: `${10 * u}px ${28 * u}px`, border: `${4 * u}px solid ${color}`, borderRadius: 40 * u, color,
      fontFamily: 'Poppins', fontWeight: 700, fontSize: 34 * u, textTransform: 'uppercase', background: 'rgba(0,0,0,0.6)', transform: `scale(${t})` }}>{text}</div>;
  };
  return (
    <div style={{ position: 'absolute', left: 0, right: 0, top: vertical ? H * 0.12 : H * 0.1, textAlign: 'center', opacity: s }}>
      <div style={{ fontFamily: 'Oswald', fontWeight: 700, fontSize: 96 * u, color: '#fff', textTransform: 'uppercase', textShadow: '0 6px 20px #000' }}>{question}</div>
      <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'center' }}>{pill(a, '#b6f23a', 0)}{b ? pill(b, RED, 1) : null}</div>
      {comment ? <div style={{ fontFamily: 'Poppins', fontWeight: 700, fontSize: 26 * u, color: '#fff', opacity: 0.8, marginTop: 8 * u }}>{comment}</div> : null}
    </div>
  );
};

const EndCard: FC<{ series: string; title: string; sub: string; follow: string; W: number; H: number; vertical: boolean; f: number; fps: number }> = ({ series, title, sub, follow, W, H, vertical, f, fps }) => {
  const s = spring({ frame: f, fps, config: { damping: 14 } });
  const u = vertical ? W / 1080 : H / 1080;
  return (
    <AbsoluteFill style={{ background: '#050507', alignItems: 'center', justifyContent: 'center', textAlign: 'center' }}>
      <div style={{ opacity: s, transform: `scale(${0.9 + 0.1 * s})` }}>
        {series ? <div style={{ fontFamily: 'Oswald', fontWeight: 500, fontSize: 34 * u, color: '#ddd', letterSpacing: 1, textTransform: 'uppercase' }}>{series}</div> : null}
        <div style={{ fontFamily: 'Oswald', fontWeight: 700, fontSize: 170 * u, color: '#fff', lineHeight: 1.05, textTransform: 'uppercase' }}>{title}</div>
        {sub ? <div style={{ fontFamily: "'JetBrains Mono'", fontSize: 26 * u, color: '#bbb', marginBottom: 20 * u }}>{sub}</div> : null}
        {follow ? <div style={{ display: 'inline-block', border: `${3 * u}px solid #fff`, borderRadius: 30 * u, padding: `${6 * u}px ${22 * u}px`, fontFamily: 'Poppins', fontWeight: 700,
          fontSize: 24 * u, color: '#fff', textTransform: 'uppercase' }}>{follow}</div> : null}
      </div>
    </AbsoluteFill>
  );
};

// --- the scene ---------------------------------------------------------------------------------------------------

export const CineScene: FC<{ graphic: CineGraphic; durationInFrames: number }> = ({ graphic: g, durationInFrames: dur }) => {
  const f = useCurrentFrame();
  const { fps, width: W, height: H } = useVideoConfig();
  const vertical = H > W;
  const L = LIGHTS[g.light] ?? LIGHTS.dark;
  const seed = g.seed ?? 0;
  const p = clamp(f / Math.max(1, dur));
  const accent = g.accent || '#ffd400';
  if (g.end) {
    return <EndCard series={g.end.series} title={g.end.title} sub={g.end.sub} follow={g.end.follow} W={W} H={H} vertical={vertical} f={f} fps={fps} />;
  }
  const overlays = (
    <>
      <Hud day={g.hud?.day} clock={g.hud?.clock} place={g.hud?.place} W={W} H={H} vertical={vertical} />
      {g.counter ? <Counter label={g.counter.label} value={g.counter.value} color={g.counter.color || '#b6f23a'} f={f} fps={fps} W={W} H={H} vertical={vertical} /> : null}
      {g.rule ? <Sticker n={g.rule.n} text={g.rule.text} f={f - (g.rule.at ?? 0)} fps={fps} W={W} H={H} vertical={vertical} word={g.rule.word || 'REGLA'} /> : null}
      {g.title && !g.rule && !g.choice ? <BigTitle text={g.title} f={f - (g.titleAt ?? 0)} fps={fps} W={W} H={H} vertical={vertical} /> : null}
      {g.choice ? <Choice question={g.choice.question} a={g.choice.a} b={g.choice.b} comment={g.choice.comment} f={f} fps={fps} W={W} H={H} vertical={vertical} /> : null}
      {g.captions !== false ? <Captions words={g.words ?? []} f={f} W={W} H={H} vertical={vertical} accent={accent} /> : null}
    </>
  );
  if (g.shot === 'pov-phone') {
    return (
      <AbsoluteFill>
        <Phone messages={g.phone?.messages ?? []} from={g.phone?.from ?? ''} typing={Boolean(g.phone?.typing)} f={f} dur={dur} fps={fps} W={W} H={H} light={L} />
        {overlays}
        <Grain f={f} />
      </AbsoluteFill>
    );
  }
  // camera: the shot frames the hero (close = his face, medium = his chest), then the move, a handheld drift and
  // a shake on «shake»; the set's far layers move less (parallax)
  const ground = H * (vertical ? 0.8 : 0.84);
  const unit = Math.min(W, H) / 1080 * (vertical ? 1.18 : 1.25);
  const actors = g.actors ?? [];
  const hero = actors.find((a) => a.who === 'hero') ?? actors[0];
  const hx = hero ? hero.x * W : W / 2;
  const headY = ground - (190 + 165 + 62) * unit * (hero?.size ?? 1);
  const shot = g.shot === 'peephole' || g.shot === 'over' || g.shot === 'above' || g.shot === 'silhouette' ? 'wide' : g.shot;
  const zoom = shot === 'close' ? 3.1 : shot === 'medium' ? 1.75 : 1;
  const fx = shot === 'wide' ? W / 2 : hx;
  const fy = shot === 'close' ? headY + 20 * unit : shot === 'medium' ? headY + 95 * unit : H / 2;
  const move = g.move ?? 'still';
  const k = ease(p);
  const push = move === 'push' ? 1 + 0.14 * k : move === 'pull' ? 1.14 - 0.14 * k : 1.03;
  const pan = move === 'pan-left' ? (0.5 - k) * W * 0.08 : move === 'pan-right' ? (k - 0.5) * W * 0.08 : 0;
  const shake = move === 'shake' ? Math.exp(-f / 10) * 26 : 0;
  const hand = 3 * Math.sin(f / 31) + 2 * Math.sin(f / 13.7);
  const sx = shake * (random(`sx${f}`) - 0.5) * 2 + hand;
  const sy = shake * (random(`sy${f}`) - 0.5) * 2 + 2 * Math.sin(f / 23);
  const enter = interpolate(f, [0, 6], [1.05, 1], { extrapolateRight: 'clamp' });
  const Z = zoom * push * enter;
  const cam = (depth: number) => {
    const z = 1 + (Z - 1) * (0.55 + 0.45 * depth);
    const tx = W / 2 - fx * z + (pan + sx) * depth;
    const ty = H / 2 - fy * z + sy * depth;
    return `translate(${tx} ${ty}) scale(${z})`;
  };
  const set = g.shot === 'above' ? 'above' : g.shot === 'peephole' ? 'hallway' : g.set;
  const layers = (SETS[set] ?? SETS.void)({ W, H, g: ground, L, f, seed });
  const silhouette = g.shot === 'silhouette';
  const figures = g.shot === 'above' ? null : actors.map((a, i) => {
    // the peephole: whoever is outside walks closer
    const near = g.shot === 'peephole' && a.who !== 'hero' ? { ...a, x: 0.5, size: a.size * (0.8 + 0.6 * k) } : a;
    if (g.shot === 'peephole' && a.who === 'hero') return null;
    return <Figure key={i} a={near} ground={ground} unit={unit} W={W} f={f} mark={g.hero?.mark ?? 'scar'} markColor={g.hero?.color ?? RED} mouth={g.mode !== 'reglas'} silhouette={silhouette} />;
  });
  const holder = g.prop?.held ? actors.reduce<CineActor | null>((best, a) => (!best || Math.abs(a.x - (g.prop?.x ?? 0.5)) < Math.abs(best.x - (g.prop?.x ?? 0.5)) ? a : best), null) : null;
  const propAt: Pt | null = g.prop ? (holder ? handOf(holder, ground, unit, W, f) : [g.prop.x * W, g.prop.y * H]) : null;
  const scene = (
    <svg width={W} height={H} style={{ position: 'absolute' }}>
      <defs>
        <filter id="cine-soft" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation={Math.min(W, H) * 0.03} /></filter>
        <radialGradient id="cine-eyeglow"><stop offset="0%" stopColor="#ff2a2a" stopOpacity={0.55} /><stop offset="100%" stopColor="#ff2a2a" stopOpacity={0} /></radialGradient>
        <linearGradient id="cine-sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={L.top} /><stop offset="100%" stopColor={L.bottom} /></linearGradient>
        <linearGradient id="cine-dawn" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#3b2a5a" /><stop offset="70%" stopColor="#f08a5d" /><stop offset="100%" stopColor="#ffd08a" /></linearGradient>
        <linearGradient id="cine-mirror" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stopColor="#4a6070" /><stop offset="50%" stopColor="#24323e" /><stop offset="100%" stopColor="#38505e" /></linearGradient>
        <radialGradient id="cine-planet" cx="35%" cy="35%"><stop offset="0%" stopColor="#8fd0ff" /><stop offset="60%" stopColor="#2a6fb8" /><stop offset="100%" stopColor="#0b1d3a" /></radialGradient>
        <radialGradient id="cine-vignette" cx="50%" cy="50%" r="75%"><stop offset="55%" stopColor="#000" stopOpacity={0} /><stop offset="100%" stopColor="#000" stopOpacity={0.85} /></radialGradient>
      </defs>
      <rect width={W} height={H} fill={L.bottom} />
      {layers.map((layer, i) => <g key={i} transform={cam(layer.depth)}>{layer.node}</g>)}
      {silhouette ? <g transform={cam(0.8)}><Glow x={hx} y={ground - 260 * unit} r={Math.min(W, H) * 0.55} color={L.practical} o={0.95} />
        <rect x={hx - Math.min(W, H) * 0.17} y={ground - Math.min(W, H) * 0.78} width={Math.min(W, H) * 0.34} height={Math.min(W, H) * 0.78} fill="#fff3d6" opacity={0.92} />
        <path d={`M ${hx - Math.min(W, H) * 0.17} ${ground} L ${hx + Math.min(W, H) * 0.17} ${ground} L ${hx + Math.min(W, H) * 0.45} ${H} L ${hx - Math.min(W, H) * 0.45} ${H} Z`} fill="#fff3d6" opacity={0.25} /></g> : null}
      <g transform={cam(1)}>
        {figures}
        {g.prop && propAt ? <g transform={`translate(${propAt[0]} ${propAt[1]}) scale(${unit * 1.15})`}><Icon name={g.prop.icon} ink={INK} colorful /></g> : null}
      </g>
      {/* the light: the scene darkened towards the edges, the cold fill on one side, the practical's warmth */}
      <rect width={W} height={H} fill={L.fill} opacity={0.1} style={{ mixBlendMode: 'screen' }} />
      <rect width={W} height={H} fill="url(#cine-vignette)" opacity={L.dark + 0.25} />
      {g.shot === 'over' && hero ? (
        <g transform={`translate(${W * 0.12} ${H * 0.98}) scale(${unit * 2.6})`}>
          <path d="M -140 0 C -140 -120 -60 -160 0 -160 C 60 -160 140 -120 140 0 Z" fill="#07080b" />
          <circle cx={0} cy={-230} r={95} fill="#07080b" />
        </g>
      ) : null}
    </svg>
  );
  return (
    <AbsoluteFill style={{ backgroundColor: '#000', overflow: 'hidden' }}>
      {g.shot === 'peephole' ? (
        <AbsoluteFill style={{ background: '#000' }}>
          <div style={{ position: 'absolute', left: W / 2 - Math.min(W, H) * 0.47, top: H * 0.45 - Math.min(W, H) * 0.47, width: Math.min(W, H) * 0.94, height: Math.min(W, H) * 0.94,
            borderRadius: '50%', overflow: 'hidden', boxShadow: 'inset 0 0 120px 60px #000' }}>
            <div style={{ position: 'absolute', left: -(W - Math.min(W, H) * 0.94) / 2, top: -(H * 0.45 - Math.min(W, H) * 0.47), width: W, height: H, transform: 'scale(1.25)', filter: 'saturate(1.2)' }}>{scene}</div>
            <div style={{ position: 'absolute', inset: 0, borderRadius: '50%', boxShadow: 'inset 0 0 80px 40px rgba(0,0,0,0.95)', border: '3px solid rgba(160,200,255,0.25)' }} />
          </div>
        </AbsoluteFill>
      ) : scene}
      {overlays}
      <Grain f={f} />
    </AbsoluteFill>
  );
};

/** Film grain: a few moving noise dots, cheap (no filters per frame). */
const Grain: FC<{ f: number }> = ({ f }) => (
  <AbsoluteFill style={{ pointerEvents: 'none', opacity: 0.07, mixBlendMode: 'overlay',
    backgroundImage: 'repeating-radial-gradient(circle at 17% 32%, #fff 0 1px, transparent 1px 3px)', backgroundPosition: `${(f * 37) % 97}px ${(f * 53) % 89}px` }} />
);
