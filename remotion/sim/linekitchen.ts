// A restaurant on a Saturday night (deterministic, seeded): tables arrive in clumps («none for ten minutes, then six
// at once»), each diner orders one dish, and every dish goes through the line's stations in order — the grill (and
// the hot line: steaks, risotto, fish), the fryer, the cold side, plating — each station working on a few dishes at a
// time, first come first served. A table gets its food when ALL its dishes are ready (they wait on the pass), or, with
// `share` (tapas, raciones al centro), each dish goes out as it is ready.
// The grill is the bottleneck by design: ≈ 53 dishes an hour, everything else 2-3 times that (Goldratt's Herbie).
// Fixes: `grill2` (a second grill: one more dish at a time there), `cold` (one more cook on the cold side: changes
// nothing), `menu` (a short menu: burgers, croquetas, salads, steadier times), `stagger` (the host seats a table every
// few minutes, the rest wait at the bar).
import {mulberry} from './world';

export const STATIONS = ['grill', 'fryer', 'cold', 'plate'] as const;
export type Fix = 'none' | 'grill2' | 'cold' | 'menu' | 'stagger';
export type KitchenSetup = {load: number; share: boolean; fix: Fix; evening?: boolean; burst?: number};   // burst: that many tables walk in at once (and nobody else)

// minutes at each station, in order
export const DISHES: {name: string; colour: string; route: [number, number][]}[] = [
  {name: 'burger', colour: '#c8823a', route: [[0, 5], [1, 3], [3, 1]]},
  {name: 'steak', colour: '#8b3a2b', route: [[0, 11], [3, 1]]},
  {name: 'risotto', colour: '#f2d27a', route: [[0, 14], [3, 1]]},
  {name: 'croquetas', colour: '#e0a94a', route: [[1, 5], [3, 0.8]]},
  {name: 'salad', colour: '#6fbf5f', route: [[2, 4], [3, 0.8]]},
  {name: 'fish', colour: '#9fc6e0', route: [[0, 8], [3, 1]]},
];
const MIX = [0.25, 0.12, 0.08, 0.2, 0.2, 0.15];
const SHORT_MIX = [0.4, 0, 0, 0.3, 0.3, 0];
const SIZES: [number, number][] = [[2, 0.45], [4, 0.35], [6, 0.12], [10, 0.08]];
const CAPACITY = [5, 3, 2, 2];                         // dishes at a time: grill, fryer baskets, cold side, plating
const STEP = 10;                                       // seconds
const ORDER_AFTER = 240;                               // reading the menu
const EATING = 45 * 60;
export const TABLES = 14;                              // tables in the dining room

export type Dish = {id: number; table: number; type: number; times: number[]; stage: number; ready: number};
export type Table = {id: number; size: number; colour: number; arrive: number; seat: number; order: number; dishes: number[];
  first: number; all: number; leave: number; slot: number};
export type Frame = {t: number; queue: number[][]; busy: {id: number; left: number; total: number}[][]; pass: number[];
  bar: number[]; seated: number[]; served: Set<number>};
export type KitchenLine = {dishes: Dish[]; tables: Table[]; frames: Frame[]; at: (t: number) => Frame; capacity: number[];
  grillPerHour: number; span: number};

const grillMinutes = (mix: number[]) => mix.reduce((a, w, k) => a + w * (DISHES[k].route.find(([s]) => s === 0)?.[1] ?? 0), 0);
const pick = (r: number, weights: number[]) => {
  let acc = 0;
  for (let k = 0; k < weights.length; k++) {
    acc += weights[k];
    if (r < acc) return k;
  }
  return weights.length - 1;
};

/** The evening's demand: arrivals ramp up from 20:00, peak around 21:45 above what the grill can do, then ease. */
export const eveningRate = (t: number) => {
  const h = 20 + t / 3600;
  return Math.max(0.15, Math.exp(-((h - 21.75) ** 2) / (2 * 0.55 ** 2)) * 1.12);
};

const CACHE = new Map<string, KitchenLine>();

export const runLine = (setup: KitchenSetup, span = 3 * 3600, keep = true, seed = 7): KitchenLine => {
  const key = `${setup.load}:${setup.share}:${setup.fix}:${setup.evening ?? false}:${span}:${keep}:${seed}`;
  if (CACHE.has(key)) return CACHE.get(key)!;
  const rnd = mulberry(seed);
  const mix = setup.fix === 'menu' ? SHORT_MIX : MIX;
  const spread = setup.fix === 'menu' ? 0.08 : 0.3;
  const capacity = CAPACITY.map((c, s) => c + ((setup.fix === 'grill2' && s === 0) || (setup.fix === 'cold' && s === 2) ? 1 : 0));
  // the same demand on the grill whatever the menu: the load is the grill's (the bottleneck's) busy share
  const perDish = grillMinutes(MIX) * 60;
  const grillPerHour = (CAPACITY[0] * 3600) / perDish;
  const meanSize = SIZES.reduce((a, [n, w]) => a + n * w, 0);
  const tablesPerSecond = (setup.load * CAPACITY[0]) / perDish / meanSize;
  // clumps of 1-4 tables (a cinema lets out, a group arrives): the same tables per hour, less evenly
  const tables: Table[] = [];
  const dishes: Dish[] = [];
  let t = setup.burst ? span : 0;
  for (let k = 0; k < (setup.burst ?? 0); k++) {         // a full house walks in at once (a party, the cinema lets out)
    const size = [4, 2, 6, 2, 4, 10, 2, 4, 6, 2][k % 10];
    tables.push({id: k, size, colour: k % 8, arrive: 60 + k * 15, seat: 0, order: 0, dishes: [], first: Infinity, all: Infinity, leave: Infinity, slot: -1});
  }
  while (t < span) {
    const rate = tablesPerSecond * (setup.evening ? eveningRate(t) : 1) / 1.45;
    t += -Math.log(1 - rnd()) / rate;
    const clump = rnd() < 0.7 ? 1 : 2 + Math.floor(rnd() * 2);
    for (let c = 0; c < clump && t < span; c++) {
      const id = tables.length;
      const size = SIZES[pick(rnd(), SIZES.map(([, w]) => w))][0];
      tables.push({id, size, colour: id % 8, arrive: t + c * 20, seat: 0, order: 0, dishes: [], first: Infinity, all: Infinity, leave: Infinity, slot: -1});
    }
  }
  // seating: at once (if there is a free table), or one every few minutes (`stagger`)
  // a burst: two tables every five minutes; otherwise a table every so often
  const gap = setup.fix === 'stagger' ? (setup.burst ? 150 : 0.55 / tablesPerSecond) : 0;
  let lastSeat = -Infinity;
  for (const tb of tables) {
    tb.seat = Math.max(tb.arrive, lastSeat + gap);
    lastSeat = tb.seat;
    tb.order = tb.seat + ORDER_AFTER * (setup.burst ? 1 + rnd() * 0.5 : 0.75 + rnd() * 1.75);
    for (let k = 0; k < tb.size; k++) {
      const type = pick(rnd(), mix);
      const times = DISHES[type].route.map(([, m]) => m * 60 * (1 - spread + 2 * spread * rnd()));
      dishes.push({id: dishes.length, table: tb.id, type, times, stage: 0, ready: Infinity});
      tb.dishes.push(dishes.length - 1);
    }
  }
  // the line, step by step
  const queue: number[][] = STATIONS.map(() => []);
  const busy: {id: number; left: number; total: number}[][] = STATIONS.map(() => []);
  const frames: Frame[] = [];
  const slots: number[] = Array(TABLES).fill(-1);
  const served = new Set<number>();
  let nextOrder = 0;
  const byOrder = [...tables].sort((a, b) => a.order - b.order);
  for (let now = 0; now <= span + 2 * 3600; now += STEP) {
    while (nextOrder < byOrder.length && byOrder[nextOrder].order <= now) {
      for (const id of byOrder[nextOrder].dishes) queue[DISHES[dishes[id].type].route[0][0]].push(id);
      nextOrder++;
    }
    for (let s = 0; s < STATIONS.length; s++) {
      for (const job of busy[s]) job.left -= STEP;
      const finished = busy[s].filter((j) => j.left <= 0);
      busy[s] = busy[s].filter((j) => j.left > 0);
      for (const job of finished) {
        const d = dishes[job.id];
        d.stage++;
        const route = DISHES[d.type].route;
        if (d.stage < route.length) queue[route[d.stage][0]].push(d.id);
        else {
          d.ready = now;
          const tb = tables[d.table];
          tb.first = Math.min(tb.first, now);
          if (tb.dishes.every((x) => dishes[x].ready <= now)) {
            tb.all = now;
            tb.leave = now + EATING;
          }
        }
      }
      while (busy[s].length < capacity[s] && queue[s].length) {
        const id = queue[s].shift()!;
        const d = dishes[id];
        const total = d.times[d.stage];
        busy[s].push({id, left: total, total});
      }
    }
    if (keep && now <= span) {
      // the dining room: a table keeps its slot from sitting down until it leaves
      for (let k = 0; k < TABLES; k++) if (slots[k] >= 0 && tables[slots[k]].leave <= now) slots[k] = -1;
      for (const tb of tables) {
        if (tb.seat <= now && tb.slot < 0 && tb.leave > now) {
          const free = slots.indexOf(-1);
          if (free >= 0) {
            slots[free] = tb.id;
            tb.slot = free;
          }
        }
      }
      for (const tb of tables) if ((setup.share ? tb.first : tb.all) <= now) served.add(tb.id);
      const pass = setup.share ? [] : dishes.filter((d) => d.ready <= now && tables[d.table].all > now).map((d) => d.id);
      const bar = tables.filter((tb) => tb.arrive <= now && tb.seat > now).map((tb) => tb.id);
      frames.push({t: now, queue: queue.map((q) => [...q]), busy: busy.map((b) => b.map((j) => ({...j}))), pass, bar,
                   seated: [...slots], served: new Set(served)});
    }
  }
  const at = (time: number) => frames[Math.max(0, Math.min(frames.length - 1, Math.round(time / STEP)))];
  const run = {dishes, tables, frames, at, capacity, grillPerHour, span};
  CACHE.set(key, run);
  return run;
};

/** Long-run waits (minutes): until the food (all of it, or the first dish with `share`), from arriving at the door. */
export const waits = (setup: KitchenSetup) => {
  const run = runLine(setup, 60 * 3600, false, 11);
  const by = new Map<number, number[]>();
  const all: number[] = [];
  for (const tb of run.tables) {
    if (tb.arrive < 2 * 3600 || !isFinite(tb.all)) continue;            // warmed up
    const w = ((setup.share ? tb.first : tb.all) - tb.arrive) / 60;
    all.push(w);
    by.set(tb.size, [...(by.get(tb.size) ?? []), w]);
  }
  const mean = (xs: number[]) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0);
  return {mean: mean(all), bySize: Object.fromEntries([...by.entries()].map(([k, v]) => [k, mean(v)])) as Record<number, number>,
          grillPerHour: run.grillPerHour};
};

/** The evening hour by hour: the mean wait of the tables that ordered in each quarter of an hour. */
export const evening = () => {
  const run = runLine({load: 1, share: false, fix: 'none', evening: true}, 4 * 3600, false, 5);
  const out: [number, number][] = [];
  for (let q = 0; q < 16; q++) {
    const xs = run.tables.filter((tb) => tb.arrive >= q * 900 && tb.arrive < (q + 1) * 900 && isFinite(tb.all)).map((tb) => (tb.all - tb.arrive) / 60);
    if (xs.length) out.push([20 + (q + 0.5) / 4, xs.reduce((a, b) => a + b, 0) / xs.length]);
  }
  return out;
};
