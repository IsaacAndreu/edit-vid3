// A river town seen from above when the river rises (the spatial spread engine, with water): the ground has heights,
// the water fills every place lower than its level that it can reach from the river (it does not jump hills), so
// streets in a hollow go under while a house on a rise stays dry. Scenes (param scene):
//  sube     the river rises: which houses go under, and how fast once it leaves its bed
//  dique    the same town twice: without a levee (left) and with one (right): dry for longer, then all at once
//  esponja  the same rain on a paved town (left) and a town with parks and soil that soaks (right)
import {memo, type FC} from 'react';
import {AbsoluteFill, interpolate} from 'remotion';
import {C, Label, Panel} from '../hud';
import {addWords, tx, num} from '../i18n';
import {Pointers, type Anchor} from '../look';
import {Big, clamp, mulberry, Note, param, SideTitle, type World, type WorldProps} from '../world';

addWords({
  flooded: {es: 'Casas inundadas', pt: 'Casas inundadas', fr: 'Maisons inondées', de: 'Überflutete Häuser', en: 'Houses flooded'},
  riverLevel: {es: 'Nivel del río', pt: 'Nível do rio', fr: 'Niveau du fleuve', de: 'Pegel', en: 'River level'},
  noLevee: {es: 'Sin dique', pt: 'Sem dique', fr: 'Sans digue', de: 'Ohne Deich', en: 'No levee'},
  withLevee: {es: 'Con dique', pt: 'Com dique', fr: 'Avec digue', de: 'Mit Deich', en: 'With a levee'},
  paved: {es: 'Todo asfaltado', pt: 'Tudo asfaltado', fr: 'Tout bétonné', de: 'Alles versiegelt', en: 'All paved'},
  sponge: {es: 'Parques y tierra que absorben', pt: 'Parques e terra que absorvem', fr: 'Parcs et sols qui absorbent', de: 'Parks und Boden, die aufsaugen', en: 'Parks and soil that soak it up'},
  floodNote: {es: 'Simulación · el agua llena lo que está por debajo de su nivel y puede alcanzar desde el río', pt: 'Simulação · a água enche o que está abaixo do seu nível e consegue alcançar a partir do rio', fr: 'Simulation · l’eau remplit ce qui est sous son niveau et qu’elle atteint depuis le fleuve', de: 'Simulation · das Wasser füllt, was unter seinem Pegel liegt und vom Fluss aus erreichbar ist', en: 'Simulation · the water fills what lies below its level and can be reached from the river'},
});

const CELL = 16;
const COLS = 120;
const ROWS = 68;
type Town = {h: Float32Array; river: Uint8Array; houses: {c: number; r: number; w: number; d: number}[]; roads: Uint8Array; parks: Uint8Array};

const town = (): Town => {
  const rnd = mulberry(23);
  const waves = Array.from({length: 7}, () => [rnd() * 0.05 + 0.01, rnd() * 0.05 + 0.01, rnd() * 6.28, 0.25 + rnd() * 0.6]);
  const h = new Float32Array(COLS * ROWS);
  const river = new Uint8Array(COLS * ROWS);
  const riverY = (c: number) => ROWS * 0.62 + Math.sin(c * 0.07) * 7 + Math.sin(c * 0.023 + 1) * 5;
  for (let r = 0; r < ROWS; r++) {
    for (let c = 0; c < COLS; c++) {
      const d = Math.abs(r - riverY(c));
      let z = Math.min(6, d * 0.16) + waves.reduce((s, [a, b, ph, amp]) => s + amp * Math.sin(c * a * 6 + r * b * 6 + ph), 0) * 0.6;
      if (d < 2.2) {
        z = -1.5;
        river[r * COLS + c] = 1;
      }
      h[r * COLS + c] = z;
    }
  }
  // the streets: a grid, with the houses in its blocks
  const roads = new Uint8Array(COLS * ROWS);
  for (let r = 0; r < ROWS; r++) for (let c = 0; c < COLS; c++) if ((c % 12 === 0 || r % 10 === 0) && !river[r * COLS + c]) roads[r * COLS + c] = 1;
  const parks = new Uint8Array(COLS * ROWS);
  const houses: Town['houses'] = [];
  for (let br = 0; br < ROWS; br += 10) {
    for (let bc = 0; bc < COLS; bc += 12) {
      const park = rnd() < 0.18;
      for (let r = br + 1; r < Math.min(ROWS, br + 10); r++) for (let c = bc + 1; c < Math.min(COLS, bc + 12); c++) if (park) parks[r * COLS + c] = 1;
      if (park) continue;
      for (let r = br + 2; r < br + 9; r += 3) {
        for (let c = bc + 2; c < bc + 11; c += 3) {
          if (r >= ROWS || c >= COLS || rnd() < 0.15) continue;
          if (Math.abs(r - riverY(c)) < 4) continue;
          houses.push({c, r, w: 2, d: 2});
        }
      }
    }
  }
  return {h, river, houses, roads, parks};
};
const TOWN = town();

/** Cells under water at level `L` (m), reached from the river; `levee`: banks raised this much; `soak`: parks soak. */
const WET = new Map<string, Uint8Array>();
const wet = (L: number, levee = 0): Uint8Array => {
  const id = `${L.toFixed(2)}:${levee}`;
  if (WET.has(id)) return WET.get(id)!;
  const {h, river} = TOWN;
  const out = new Uint8Array(COLS * ROWS);
  const queue: number[] = [];
  for (let i = 0; i < out.length; i++) if (river[i]) {
    out[i] = 1;
    queue.push(i);
  }
  const ground = (i: number) => {
    if (!levee) return h[i];
    const r = Math.floor(i / COLS);
    const c = i % COLS;
    // the levee: the first cells beside the river raised
    for (const [dr, dc] of [[1, 0], [-1, 0], [2, 0], [-2, 0], [3, 0], [-3, 0]]) {
      const rr = r + dr;
      if (rr >= 0 && rr < ROWS && river[rr * COLS + c]) return h[i] + levee;
    }
    return h[i];
  };
  while (queue.length) {
    const i = queue.pop()!;
    const r = Math.floor(i / COLS);
    const c = i % COLS;
    for (const [dr, dc] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
      const rr = r + dr;
      const cc = c + dc;
      if (rr < 0 || rr >= ROWS || cc < 0 || cc >= COLS) continue;
      const j = rr * COLS + cc;
      if (!out[j] && ground(j) < L) {
        out[j] = 1;
        queue.push(j);
      }
    }
  }
  if (WET.size > 400) WET.clear();
  WET.set(id, out);
  return out;
};

const LEVEE = 1.6;
/** The river's level over the world's clock: rising from its bed to a flood peak. `rain` speeds it (paved town). */
const level = (t: number, rain = 1) => -1 + Math.min(4.6, Math.max(0, t - 1) * 0.24 * rain);
/** A levee holds until the river is over it; then the water pours in and finds the town at the river's level. */
const leveeLevel = (L: number) => (L < LEVEE + 0.2 ? Math.min(L, 0.2) : L);

const geometry = (left: number, width: number) => {
  const scale = Math.max(width / (COLS * CELL), 1080 / (ROWS * CELL));
  return {scale, ox: left + (width - COLS * CELL * scale) / 2};
};

/** The ground, the streets, the river and the levee: drawn once (memo), the water goes over it. */
const Terrain = memo(({left, width, levee, soak}: {left: number; width: number; levee: number; soak: boolean}) => {
  const {h, river, roads, parks} = TOWN;
  const {scale, ox} = geometry(left, width);
  const cells = [];
  for (let r = 0; r < ROWS; r++) {
    for (let c = 0; c < COLS; c++) {
      const i = r * COLS + c;
      const z = h[i];
      const ground = river[i] ? '#2c6aa0' : roads[i] ? '#9a958c' : parks[i] && soak ? '#4f8f45' : parks[i] ? '#6f8a5a'
        : `rgb(${Math.round(110 + z * 9)}, ${Math.round(140 + z * 8)}, ${Math.round(88 + z * 5)})`;
      cells.push(<rect key={i} x={ox + c * CELL * scale} y={r * CELL * scale} width={CELL * scale + 0.6} height={CELL * scale + 0.6} fill={ground} />);
    }
  }
  return (
    <g>
      {cells}
      {levee > 0 && Array.from({length: COLS}, (_, c) => {
        const rows = Array.from({length: ROWS}, (_, r) => r).filter((r) => river[r * COLS + c]);
        if (!rows.length) return null;
        return [rows[0] - 1, rows[rows.length - 1] + 1].map((r) => (
          <rect key={`l${c}${r}`} x={ox + c * CELL * scale} y={r * CELL * scale} width={CELL * scale + 0.6} height={CELL * scale * 0.7} fill="#8d7a5c" />
        ));
      })}
    </g>
  );
});

const Map2D: FC<{left: number; width: number; L: number; levee?: number; soak?: boolean}> = ({left, width, L, levee = 0, soak = false}) => {
  const {h, river, houses} = TOWN;
  const w = wet(levee ? leveeLevel(L) : L, levee);
  const {scale, ox} = geometry(left, width);
  // the water in runs along each row (one shape per run, not per cell), deeper = darker
  const water = [];
  for (let r = 0; r < ROWS; r++) {
    let c = 0;
    while (c < COLS) {
      const i = r * COLS + c;
      if (!w[i] || river[i]) {
        c++;
        continue;
      }
      let e = c;
      let deep = 0;
      while (e < COLS && w[r * COLS + e] && !river[r * COLS + e]) {
        deep = Math.max(deep, L - h[r * COLS + e]);
        e++;
      }
      water.push(<rect key={`w${i}`} x={ox + c * CELL * scale} y={r * CELL * scale} width={(e - c) * CELL * scale + 0.6} height={CELL * scale + 0.6}
                       fill="#2f78c4" opacity={Math.min(0.88, 0.5 + deep * 0.1)} />);
      c = e;
    }
  }
  return (
    <g>
      <Terrain left={left} width={width} levee={levee} soak={soak} />
      {water}
      {houses.map((hs, k) => {
        const i = hs.r * COLS + hs.c;
        const under = w[i] && !river[i];
        const x = ox + hs.c * CELL * scale;
        const y = hs.r * CELL * scale;
        const size = hs.w * CELL * scale;
        return (
          <g key={k}>
            <rect x={x + 3} y={y + 3} width={size} height={size} fill="rgba(0,0,0,0.25)" />
            <rect x={x} y={y} width={size} height={size} fill={['#b5655a', '#c28a5c', '#8f6f63', '#a9a19a'][k % 4]} stroke={under ? C.red : 'rgba(0,0,0,0.3)'}
                  strokeWidth={under ? 3 : 1} />
            <rect x={x} y={y} width={size} height={size / 2} fill="rgba(255,255,255,0.12)" />
          </g>
        );
      })}
    </g>
  );
};

const floodedCount = (L: number, levee = 0) => {
  const w = wet(levee ? leveeLevel(L) : L, levee);
  return TOWN.houses.filter((hs) => w[hs.r * COLS + hs.c]).length;
};

const View: FC<WorldProps> = ({g, worldT, local, real = local, o, on}) => {
  const scene = param<string>(g, 'scene', 'sube');
  const panel = Math.max(o('panel'), on * 0.9);
  const t = worldT * 1.6;
  const marks: Record<string, Anchor | null> = {};
  let body;
  if (scene === 'dique' || scene === 'esponja') {
    const levee = scene === 'dique';
    const L = level(t);
    const Ls = levee ? L : level(t, 0.62);                 // the soaking town: less water reaches the river
    const La = levee ? L : level(t, 1.25);                 // the paved one: all of it, and faster
    const a = levee ? floodedCount(L) : floodedCount(La);
    const b = levee ? floodedCount(L, LEVEE) : floodedCount(Ls);
    body = (
      <>
        <svg width={1920} height={1080} style={{position: 'absolute'}}>
          <Map2D left={0} width={958} L={levee ? L : La} />
          <Map2D left={962} width={958} L={levee ? L : Ls} levee={levee ? LEVEE : 0} soak={!levee} />
        </svg>
        <div style={{position: 'absolute', left: 958, top: 0, width: 4, height: 1080, background: C.night}} />
        <SideTitle text={tx(levee ? 'noLevee' : 'paved')} style={{left: 48, top: 44}} />
        <SideTitle text={tx(levee ? 'withLevee' : 'sponge')} style={{left: 1010, top: 44}} />
        <Big o={panel} label={tx('flooded')} value={String(a)} color={a ? C.red : C.text} style={{left: 48, bottom: 70}} />
        <Big o={panel} label={tx('flooded')} value={String(b)} color={b ? C.red : C.green} style={{left: 1010, bottom: 70}} />
      </>
    );
  } else {
    const L = level(t);
    const n = floodedCount(L);
    const first = TOWN.houses.find((hs) => wet(L)[hs.r * COLS + hs.c]);
    const {scale, ox} = geometry(0, 1920);
    marks.house = first ? {x: ox + (first.c + 1) * CELL * scale, y: (first.r + 1) * CELL * scale} : null;
    body = (
      <>
        <svg width={1920} height={1080} style={{position: 'absolute'}}>
          <Map2D left={0} width={1920} L={L} />
        </svg>
        <Panel o={panel} style={{right: 64, top: 52, width: 330}}>
          <Label>{tx('riverLevel')}</Label>
          <div style={{fontSize: 52, fontWeight: 800, fontVariantNumeric: 'tabular-nums'}}>+{num(Math.max(0, L + 1), 1)} m</div>
          <Label>{tx('flooded')}</Label>
          <div style={{fontSize: 52, fontWeight: 800, color: n ? C.red : C.text, fontVariantNumeric: 'tabular-nums'}}>
            {n} <span style={{fontSize: 26, color: C.label}}>/ {TOWN.houses.length}</span>
          </div>
        </Panel>
      </>
    );
  }
  return (
    <AbsoluteFill style={{background: '#6f8f5a', opacity: interpolate(real, [0, 0.2], [0.98, 1], clamp)}}>
      {body}
      <Pointers marks={g.marks} local={real} at={marks} />
      <Note>{tx('floodNote')}</Note>
    </AbsoluteFill>
  );
};

export const inundacion: World = {View};
