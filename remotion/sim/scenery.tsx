// What is around a road so it reads as a real one: grass verges, a gravel edge, the guardrail, trees and bushes along
// it, a field or two — flat, in the theme's colours (city.tsx), placed in metres so they slide past as the camera
// follows the traffic. Deterministic (seeded by the metre).
import type {FC} from 'react';
import {random} from 'remotion';
import {CITY} from './city';

const EVERY = 9;                 // metres between possible trees on each side

/** The roadside of a straight horizontal road whose asphalt spans [y - half, y + half] pixels; `x0` the metre at
 * the left edge of the screen and `m` the pixels per metre. */
export const Roadside: FC<{y: number; half: number; x0: number; m: number; seed?: string; width?: number}> = (
  {y, half, x0, m, seed = 'r', width = 1920}) => {
  const first = Math.floor(x0 / EVERY) - 1;
  const last = Math.ceil((x0 + width / m) / EVERY) + 1;
  const items = [];
  for (let k = first; k <= last; k++) {
    for (const side of [-1, 1]) {
      const key = `${seed}${k}${side}`;
      const r = random(`t${key}`);
      if (r > 0.55) continue;
      const along = (k * EVERY + random(`a${key}`) * EVERY - x0) * m;
      const away = half + (14 + random(`d${key}`) * 70) * Math.max(0.6, m / 6);
      const yy = y + side * away;
      const size = (2.2 + random(`s${key}`) * 2.6) * m * 0.55;
      const bush = r < 0.18;
      items.push(
        <g key={key}>
          <circle cx={along + size * 0.3} cy={yy + size * 0.3} r={size} fill={CITY.shadow} />
          <circle cx={along} cy={yy} r={bush ? size * 0.6 : size} fill={CITY.tree} />
          {!bush && <circle cx={along - size * 0.25} cy={yy - size * 0.25} r={size * 0.55} fill={CITY.treeLight} />}
        </g>,
      );
    }
  }
  const post = 4 * m;
  const shift = ((-x0 * m) % post + post) % post;
  return (
    <g>
      {/* mown verges, a little lighter next to the road */}
      <rect x={0} y={y - half - 26} width={width} height={22} fill={CITY.grass} opacity={0.9} />
      <rect x={0} y={y + half + 4} width={width} height={22} fill={CITY.grass} opacity={0.9} />
      {/* the gravel edge */}
      <rect x={0} y={y - half - 5} width={width} height={5} fill={CITY.sidewalk} />
      <rect x={0} y={y + half} width={width} height={5} fill={CITY.sidewalk} />
      {/* the guardrail on the far side, its posts sliding by */}
      <line x1={0} x2={width} y1={y - half - 16} y2={y - half - 16} stroke="#b9bfc7" strokeWidth={3} opacity={0.8} />
      {Array.from({length: Math.ceil(width / post) + 1}, (_, i) => (
        <rect key={i} x={shift + i * post - 1.5} y={y - half - 20} width={3} height={8} fill="#8d939b" />
      ))}
      {items}
    </g>
  );
};

/** A field with crop rows behind everything (the ground of a road world). */
export const Fields: FC<{x0: number; m: number}> = ({x0, m}) => {
  const span = 260 * m;
  const shift = ((-x0 * m) % span + span) % span - span;
  return (
    <g opacity={0.5}>
      {Array.from({length: 10}, (_, i) => (
        <g key={i}>
          <rect x={shift + i * span} y={0} width={span - 12} height={1080} fill={i % 2 ? CITY.grass : CITY.ground} />
          {Array.from({length: 26}, (_, j) => (
            <line key={j} x1={shift + i * span} x2={shift + (i + 1) * span - 12} y1={j * 42} y2={j * 42} stroke={CITY.shadow} strokeWidth={1.5} opacity={0.4} />
          ))}
        </g>
      ))}
    </g>
  );
};
