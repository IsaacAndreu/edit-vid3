// A city seen from above, made from a seed: a grid of streets, blocks of houses with shaded roofs, trees and parks,
// and a clearing in the middle for whatever the scene needs (here a ring road). World units are metres.
import type {FC, ReactNode} from 'react';
import {random} from 'remotion';

export type Cam = {x: number; y: number; s: number};
export const toScreen = (cam: Cam, x: number, y: number) => ({sx: 960 + (x - cam.x) * cam.s, sy: 540 + (y - cam.y) * cam.s});

export const CITY = {
  ground: '#3c5a36',
  grass: '#4a6e3f',
  road: '#33363c',
  roadEdge: '#4a4d54',
  sidewalk: '#62656b',
  marking: '#d9c36a',
  roofs: ['#7a5f4f', '#8b6a52', '#6d7480', '#5f6672', '#8f8572', '#6a5a4c', '#9a7c62', '#55606b'],
  tree: '#2f5a2c',
  treeLight: '#3f7337',
  shadow: 'rgba(0,0,0,0.28)',
};

const BLOCK = 72;          // street spacing
const STREET = 9;          // street width
const EXTENT = 520;        // the city goes from -EXTENT to +EXTENT on both axes

type Rect = {x: number; y: number; w: number; h: number; c: string};
type Tree = {x: number; y: number; r: number};

const build = (clearing: number, ring: [number, number]) => {
  const houses: Rect[] = [];
  const trees: Tree[] = [];
  const parks: Rect[] = [];
  for (let bx = -EXTENT; bx < EXTENT; bx += BLOCK) {
    for (let by = -EXTENT; by < EXTENT; by += BLOCK) {
      const x0 = bx + STREET / 2 + 2;
      const y0 = by + STREET / 2 + 2;
      const size = BLOCK - STREET - 4;
      const cx = x0 + size / 2;
      const cy = y0 + size / 2;
      const nx = Math.max(x0, Math.min(0, x0 + size));
      const ny = Math.max(y0, Math.min(0, y0 + size));
      if (Math.hypot(nx, ny) < clearing + 4 || Math.hypot(cx, cy) < clearing) continue;      // the clearing: a park
      const seed = `${bx}:${by}`;
      if (random(`park${seed}`) < 0.12) {
        parks.push({x: x0, y: y0, w: size, h: size, c: CITY.grass});
        for (let i = 0; i < 14; i++) {
          trees.push({x: x0 + random(`tpx${seed}${i}`) * size, y: y0 + random(`tpy${seed}${i}`) * size, r: 2.2 + random(`tpr${seed}${i}`) * 2.2});
        }
        continue;
      }
      // a row of houses along each side of the block, gardens in the middle
      const per = 4 + Math.floor(random(`n${seed}`) * 3);
      const lot = size / per;
      for (const side of [0, 1, 2, 3]) {
        for (let i = 0; i < per; i++) {
          const k = `${seed}${side}${i}`;
          if (random(`skip${k}`) < 0.12) continue;
          const w = lot * (0.55 + random(`w${k}`) * 0.3);
          const d = 9 + random(`d${k}`) * 7;
          const along = i * lot + (lot - w) / 2;
          const c = CITY.roofs[Math.floor(random(`c${k}`) * CITY.roofs.length)];
          if (side === 0) houses.push({x: x0 + along, y: y0 + 1, w, h: d, c});
          if (side === 1) houses.push({x: x0 + along, y: y0 + size - d - 1, w, h: d, c});
          if (side === 2 && i > 0 && i < per - 1) houses.push({x: x0 + 1, y: y0 + along, w: d, h: w, c});
          if (side === 3 && i > 0 && i < per - 1) houses.push({x: x0 + size - d - 1, y: y0 + along, w: d, h: w, c});
        }
      }
      for (let i = 0; i < 5; i++) {
        trees.push({x: x0 + 18 + random(`tx${seed}${i}`) * (size - 36), y: y0 + 18 + random(`ty${seed}${i}`) * (size - 36), r: 1.8 + random(`tr${seed}${i}`) * 1.8});
      }
    }
  }
  // the park in the clearing: trees all round, none on the ring road
  for (let i = 0; i < 260; i++) {
    const r = Math.sqrt(random(`pr${i}`)) * clearing;
    const th = random(`pa${i}`) * 2 * Math.PI;
    if (r > ring[0] - 3 && r < ring[1] + 3) continue;
    if (r < ring[0] - 3 && random(`pin${i}`) < 0.6) continue;
    trees.push({x: Math.cos(th) * r, y: Math.sin(th) * r, r: 1.8 + random(`ps${i}`) * 2.4});
  }
  return {houses, trees, parks};
};

const CACHE = new Map<string, ReturnType<typeof build>>();

export const City: FC<{cam: Cam; clearing: number; ring?: [number, number]; children?: ReactNode}> = ({cam, clearing, ring = [0, 0], children}) => {
  const id = `${clearing}:${ring}`;
  if (!CACHE.has(id)) CACHE.set(id, build(clearing, ring));
  const {houses, trees, parks} = CACHE.get(id)!;
  const p = (x: number, y: number) => toScreen(cam, x, y);
  const view = (x: number, y: number, w: number, h: number) => {
    const a = p(x, y);
    return a.sx < 1940 && a.sy < 1100 && a.sx + w * cam.s > -20 && a.sy + h * cam.s > -20;
  };
  const streets = [];
  for (let g = -EXTENT; g <= EXTENT; g += BLOCK) {
    const a = p(g - STREET / 2, -EXTENT);
    const b = p(-EXTENT, g - STREET / 2);
    streets.push(
      <rect key={`v${g}`} x={a.sx} y={a.sy} width={STREET * cam.s} height={2 * EXTENT * cam.s} fill={CITY.road} />,
      <rect key={`h${g}`} x={b.sx} y={b.sy} width={2 * EXTENT * cam.s} height={STREET * cam.s} fill={CITY.road} />,
      <line key={`vm${g}`} x1={p(g, 0).sx} x2={p(g, 0).sx} y1={p(0, -EXTENT).sy} y2={p(0, EXTENT).sy} stroke={CITY.marking}
            strokeWidth={Math.max(0.6, cam.s * 0.15)} strokeDasharray={`${cam.s * 3} ${cam.s * 3}`} opacity={0.7} />,
      <line key={`hm${g}`} y1={p(0, g).sy} y2={p(0, g).sy} x1={p(-EXTENT, 0).sx} x2={p(EXTENT, 0).sx} stroke={CITY.marking}
            strokeWidth={Math.max(0.6, cam.s * 0.15)} strokeDasharray={`${cam.s * 3} ${cam.s * 3}`} opacity={0.7} />,
    );
  }
  return (
    <svg width={1920} height={1080} style={{position: 'absolute'}}>
      <rect width={1920} height={1080} fill={CITY.ground} />
      {streets}
      <circle cx={p(0, 0).sx} cy={p(0, 0).sy} r={clearing * cam.s} fill={CITY.grass} />
      {parks.filter((r) => view(r.x, r.y, r.w, r.h)).map((r, i) => {
        const a = p(r.x, r.y);
        return <rect key={`p${i}`} x={a.sx} y={a.sy} width={r.w * cam.s} height={r.h * cam.s} fill={r.c} />;
      })}
      {houses.filter((r) => view(r.x, r.y, r.w, r.h)).map((r, i) => {
        const a = p(r.x, r.y);
        const off = 1.2 * cam.s;
        return (
          <g key={`hs${i}`}>
            <rect x={a.sx + off} y={a.sy + off} width={r.w * cam.s} height={r.h * cam.s} fill={CITY.shadow} />
            <rect x={a.sx} y={a.sy} width={r.w * cam.s} height={r.h * cam.s} fill={r.c} />
            <rect x={a.sx} y={a.sy} width={r.w * cam.s} height={(r.h * cam.s) / 2} fill="rgba(255,255,255,0.08)" />
          </g>
        );
      })}
      {trees.filter((t) => view(t.x - t.r, t.y - t.r, 2 * t.r, 2 * t.r)).map((t, i) => {
        const a = p(t.x, t.y);
        return (
          <g key={`t${i}`}>
            <circle cx={a.sx + cam.s * 0.8} cy={a.sy + cam.s * 0.8} r={t.r * cam.s} fill={CITY.shadow} />
            <circle cx={a.sx} cy={a.sy} r={t.r * cam.s} fill={CITY.tree} />
            <circle cx={a.sx - t.r * cam.s * 0.25} cy={a.sy - t.r * cam.s * 0.25} r={t.r * cam.s * 0.55} fill={CITY.treeLight} />
          </g>
        );
      })}
      {children}
    </svg>
  );
};
