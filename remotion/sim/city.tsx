// A city seen from above, made from a seed: a grid of streets, blocks of houses with shaded roofs, trees and parks,
// and a clearing in the middle for whatever the scene needs (here a ring road). World units are metres.
import {memo, type FC, type ReactNode} from 'react';
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
  night: false,
  minimal: false,           // no houses or trees: the streets faint on a dark field (the «dark» look)
};

// the map's look for the channel or the story (visual.theme): day, night (lit windows, headlights) or sepia (history)
const THEMES: Record<string, Partial<typeof CITY>> = {
  day: {ground: '#3c5a36', grass: '#4a6e3f', road: '#33363c', roadEdge: '#4a4d54', sidewalk: '#62656b', marking: '#d9c36a',
        roofs: ['#7a5f4f', '#8b6a52', '#6d7480', '#5f6672', '#8f8572', '#6a5a4c', '#9a7c62', '#55606b'], tree: '#2f5a2c',
        treeLight: '#3f7337', shadow: 'rgba(0,0,0,0.28)', night: false},
  night: {ground: '#141c17', grass: '#1a2a1c', road: '#1d1f24', roadEdge: '#2a2d33', sidewalk: '#2c2f35', marking: '#8a7a3a',
          roofs: ['#2b2f38', '#33302c', '#262b33', '#2f343c', '#38332c', '#2a2724', '#353a42', '#24282e'], tree: '#14261a',
          treeLight: '#1c3322', shadow: 'rgba(0,0,0,0.45)', night: true},
  sepia: {ground: '#8a7656', grass: '#93805c', road: '#5e4f3c', roadEdge: '#6e5e48', sidewalk: '#7c6a52', marking: '#c9b48a',
          roofs: ['#a08462', '#8f7454', '#b29470', '#7d6649', '#a6906c', '#94795a', '#ba9f7a', '#856b4e'], tree: '#5e5838',
          treeLight: '#736c47', shadow: 'rgba(40,25,10,0.3)', night: false},
  // one look for a whole traffic video: the dark field of the straight road (carretera), streets barely there
  dark: {ground: '#1d2a22', grass: '#223127', road: '#2b2e34', roadEdge: '#3a3e45', sidewalk: '#3a3e45', marking: '#6e6a52',
         roofs: ['#26312a'], tree: '#1f2b23', treeLight: '#26352b', shadow: 'rgba(0,0,0,0.3)', night: false, minimal: true},
};
export const setTheme = (name: string | undefined) => Object.assign(CITY, {minimal: false}, THEMES[String(name || 'day')] ?? THEMES.day);

const BLOCK = 72;          // street spacing
const STREET = 9;          // street width
const EXTENT = 504;        // the city goes from -EXTENT to +EXTENT on both axes (a street crossing at the origin)

type Rect = {x: number; y: number; w: number; h: number; c: string};
type Tree = {x: number; y: number; r: number};

const build = (clearing: number, ring: [number, number], disc: boolean) => {
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
      if (disc && (Math.hypot(nx, ny) < clearing + 4 || Math.hypot(cx, cy) < clearing)) continue;      // the clearing: a park
      const seed = `${bx}:${by}`;
      if (random(`park${seed}`) < 0.12) {
        parks.push({x: x0, y: y0, w: size, h: size, c: 'grass'});
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
          const c = `r${Math.floor(random(`c${k}`) * 8)}`;      // the theme's roof colour, chosen when drawn
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
  if (!disc) {         // no park: only what stands inside the clearing goes (a roundabout takes the corners of the blocks)
    const near = (r: Rect) => Math.hypot(Math.max(r.x, Math.min(0, r.x + r.w)), Math.max(r.y, Math.min(0, r.y + r.h)));
    for (let i = houses.length - 1; i >= 0; i--) if (near(houses[i]) < clearing + 3) houses.splice(i, 1);
    for (let i = trees.length - 1; i >= 0; i--) if (Math.hypot(trees[i].x, trees[i].y) < clearing + 3) trees.splice(i, 1);
  }
  // the park in the clearing: trees all round, none on the ring road
  for (let i = 0; i < 260; i++) {
    const r = Math.sqrt(random(`pr${i}`)) * clearing;
    const th = random(`pa${i}`) * 2 * Math.PI;
    if (r > ring[0] - 3 && r < ring[1] + 3) continue;
    if (!disc && (Math.abs(Math.cos(th) * r) < STREET || Math.abs(Math.sin(th) * r) < STREET)) continue;   // not on the streets
    if (r < ring[0] - 3 && random(`pin${i}`) < 0.6) continue;
    trees.push({x: Math.cos(th) * r, y: Math.sin(th) * r, r: 1.8 + random(`ps${i}`) * 2.4});
  }
  return {houses, trees, parks};
};

const CACHE = new Map<string, ReturnType<typeof build>>();

type CityProps = {cam: Cam; clearing: number; ring?: [number, number]; disc?: boolean; width?: number; children?: ReactNode};

/** The map. Thousands of shapes: drawn again only when the camera or the look changes (memo), not on every frame —
 * the cars go in a layer of their own above it. */
export const City: FC<CityProps> = (props) => <CityMap {...props} look={`${CITY.ground}:${CITY.minimal}:${CITY.night}`} />;

const same = (a: CityProps & {look: string}, b: CityProps & {look: string}) =>
  a.look === b.look && a.clearing === b.clearing && a.disc === b.disc && a.width === b.width && !a.children && !b.children
  && String(a.ring) === String(b.ring) && Math.abs(a.cam.x - b.cam.x) < 1e-3 && Math.abs(a.cam.y - b.cam.y) < 1e-3
  && Math.abs(a.cam.s - b.cam.s) < 1e-4;

const CityMap = memo((
  {cam, clearing, ring = [0, 0] as [number, number], disc = true, width = 1920, children}: CityProps & {look: string}) => {
  const id = `${clearing}:${ring}:${disc}`;
  if (!CACHE.has(id)) CACHE.set(id, build(clearing, ring, disc));
  const built = CACHE.get(id)!;
  const {houses, trees, parks} = CITY.minimal ? {houses: [], trees: [], parks: []} : built;
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
      <rect key={`v${g}`} x={a.sx} y={a.sy} width={STREET * cam.s} height={2 * EXTENT * cam.s} fill={CITY.road} opacity={CITY.minimal && disc ? 0.45 : 1} />,
      <rect key={`h${g}`} x={b.sx} y={b.sy} width={2 * EXTENT * cam.s} height={STREET * cam.s} fill={CITY.road} opacity={CITY.minimal && disc ? 0.45 : 1} />,
      <line key={`vm${g}`} x1={p(g, 0).sx} x2={p(g, 0).sx} y1={p(0, -EXTENT).sy} y2={p(0, EXTENT).sy} stroke={CITY.marking}
            strokeWidth={Math.max(0.6, cam.s * 0.15)} strokeDasharray={`${cam.s * 3} ${cam.s * 3}`} opacity={0.7} />,
      <line key={`hm${g}`} y1={p(0, g).sy} y2={p(0, g).sy} x1={p(-EXTENT, 0).sx} x2={p(EXTENT, 0).sx} stroke={CITY.marking}
            strokeWidth={Math.max(0.6, cam.s * 0.15)} strokeDasharray={`${cam.s * 3} ${cam.s * 3}`} opacity={0.7} />,
    );
  }
  return (
    <svg width={width} height={1080} style={{position: 'absolute'}}>
      <rect width={width} height={1080} fill={CITY.ground} />
      {streets}
      {disc && <circle cx={p(0, 0).sx} cy={p(0, 0).sy} r={clearing * cam.s} fill={CITY.grass} />}
      {parks.filter((r) => view(r.x, r.y, r.w, r.h)).map((r, i) => {
        const a = p(r.x, r.y);
        return <rect key={`p${i}`} x={a.sx} y={a.sy} width={r.w * cam.s} height={r.h * cam.s} fill={CITY.grass} />;
      })}
      {houses.filter((r) => view(r.x, r.y, r.w, r.h)).map((r, i) => {
        const a = p(r.x, r.y);
        const off = 1.2 * cam.s;
        return (
          <g key={`hs${i}`}>
            <rect x={a.sx + off} y={a.sy + off} width={r.w * cam.s} height={r.h * cam.s} fill={CITY.shadow} />
            <rect x={a.sx} y={a.sy} width={r.w * cam.s} height={r.h * cam.s} fill={CITY.roofs[Number(r.c.slice(1)) % CITY.roofs.length]} />
            {CITY.night && i % 5 < 2 && (     // a lit window at night
              <rect x={a.sx + r.w * cam.s * 0.3} y={a.sy + r.h * cam.s * 0.35} width={r.w * cam.s * 0.25} height={r.h * cam.s * 0.25}
                    fill="#ffcf73" opacity={0.85} />
            )}
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
}, same);

// --- a car seen from above (metres → pixels with s); brake lights glow with `brake` (0-1) ----------------------------
export const BODY = ['#e8e4dc', '#c9ccd2', '#2d3440', '#8a2d2d', '#3b5e8c', '#d9d2b0', '#4c4f56', '#9aa3ad'];

/** `trail` (0 → 1): a short fading streak behind the car, longer the faster it goes. */
export type Kind = 'car' | 'small' | 'suv' | 'van';
/** A vehicle's body for car number `i` (the same car keeps it): mostly cars, some small ones, SUVs and vans. */
export const kindOf = (i: number): Kind => (i % 11 === 3 ? 'van' : i % 7 === 2 ? 'suv' : i % 5 === 1 ? 'small' : 'car');
const SIZE: Record<Kind, [number, number]> = {car: [4.4, 1.9], small: [3.7, 1.75], suv: [4.7, 2.0], van: [5.1, 2.05]};

/** `trail` (0 → 1): a short fading streak behind the car, longer the faster it goes; `kind`: the body. */
export const Car: FC<{sx: number; sy: number; deg: number; s: number; color: string; brake: number; mark?: string; trail?: number; kind?: Kind}> = (
  {sx, sy, deg, s, color, brake, mark, trail = 0, kind = 'car'}) => {
  const [L, W] = SIZE[kind];
  const l = L * s;
  const w = W * s;
  const tail = l * 1.9 * trail;
  const glass = 'rgba(20,26,36,0.62)';
  return (
    <g transform={`translate(${sx} ${sy}) rotate(${deg})`}>
      {tail > 1 && (
        <>
          <path d={`M${-l / 2},${-w * 0.42} L${-l / 2 - tail},${-w * 0.12} L${-l / 2 - tail},${w * 0.12} L${-l / 2},${w * 0.42} Z`} fill={color} opacity={0.16} />
          <path d={`M${-l / 2},${-w * 0.3} L${-l / 2 - tail * 0.55},${-w * 0.08} L${-l / 2 - tail * 0.55},${w * 0.08} L${-l / 2},${w * 0.3} Z`} fill={color} opacity={0.22} />
        </>
      )}
      {mark && <circle r={l * 0.95} fill="none" stroke={mark} strokeWidth={Math.max(1.5, s * 0.25)} opacity={0.9} />}
      {CITY.night && <path d={`M${l * 0.45},${-w * 0.35} L${l * 2.6},${-w * 1.3} L${l * 2.6},${w * 1.3} L${l * 0.45},${w * 0.35} Z`} fill="#fff1b8" opacity={0.16} />}
      <rect x={-l / 2 + s * 0.25} y={-w / 2 + s * 0.25} width={l} height={w} rx={s * (kind === 'van' ? 0.35 : 0.55)} fill="rgba(0,0,0,0.35)" />
      <rect x={-l / 2} y={-w / 2} width={l} height={w} rx={s * (kind === 'van' ? 0.35 : 0.55)} fill={color} />
      {kind === 'van' ? (
        <>
          <rect x={l / 2 - l * 0.24} y={-w / 2 + s * 0.18} width={l * 0.13} height={w - s * 0.36} rx={s * 0.15} fill={glass} />
          <rect x={-l / 2 + s * 0.3} y={-w / 2 + s * 0.3} width={l * 0.62} height={w - s * 0.6} rx={s * 0.12} fill="rgba(255,255,255,0.14)" />
        </>
      ) : (
        <>
          <rect x={l * (kind === 'small' ? 0.08 : 0.12)} y={-w / 2 + s * 0.2} width={l * 0.16} height={w - s * 0.4} rx={s * 0.22} fill={glass} />
          <rect x={-l * 0.2} y={-w / 2 + s * 0.28} width={l * 0.3} height={w - s * 0.56} rx={s * 0.18} fill="rgba(255,255,255,0.16)" />
          <rect x={-l / 2 + l * 0.08} y={-w / 2 + s * 0.24} width={l * 0.1} height={w - s * 0.48} rx={s * 0.18} fill={glass} />
          {kind === 'suv' && [-1, 1].map((k) => (
            <line key={k} x1={-l * 0.2} x2={l * 0.1} y1={k * (w / 2 - s * 0.32)} y2={k * (w / 2 - s * 0.32)} stroke="rgba(0,0,0,0.35)" strokeWidth={s * 0.12} />
          ))}
        </>
      )}
      <circle cx={l / 2 - s * 0.15} cy={-w / 2 + s * 0.35} r={s * 0.22} fill="#fff6cf" />
      <circle cx={l / 2 - s * 0.15} cy={w / 2 - s * 0.35} r={s * 0.22} fill="#fff6cf" />
      {brake > 0 && (
        <g opacity={brake}>
          <circle cx={-l / 2} cy={0} r={w * 1.1} fill="#ff2d2d" opacity={0.28} />
          <rect x={-l / 2 - s * 0.05} y={-w / 2 + s * 0.15} width={s * 0.35} height={w - s * 0.3} fill="#ff3b3b" />
        </g>
      )}
    </g>
  );
};

