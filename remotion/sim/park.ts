// A car park: drivers come in, drive along the aisles in order (the route passes every space once, the ones near the
// entrance first) and take the first free space they see; parked cars leave after a while. How long it takes to find a
// space depends on how full the car park is — and not in a straight line: past ~85 % (Shoup's rule) the search blows up.
// Deterministic (seeded); arrivals keep the car park at about `full` of its spaces.
import {mulberry} from './world';

export const PARK = {aisles: 4, perSide: 16, slot: 2.6, turn: 14, speed: 2.5, back: 40, stay: 1800, step: 0.5, span: 3600};
export const SPACES = PARK.aisles * PARK.perSide * 2;
export const ROUTE = PARK.aisles * (PARK.perSide * PARK.slot + PARK.turn);      // metres along all the aisles, once
/** Where along the route each space is seen (metres): aisle by aisle, both sides of the aisle at once. */
export const spaceAt = (i: number) => {
  const aisle = Math.floor(i / (PARK.perSide * 2));
  const k = Math.floor((i % (PARK.perSide * 2)) / 2);
  return aisle * (PARK.perSide * PARK.slot + PARK.turn) + (k + 0.5) * PARK.slot;
};

export type Searcher = {id: number; arrive: number; d: number; done: number; space: number; laps: number};
export type ParkFrame = {t: number; taken: Uint8Array; cars: {id: number; d: number}[]};
export type ParkRun = {frames: ParkFrame[]; searches: Searcher[]; at: (t: number) => ParkFrame; full: number};

const RUNS = new Map<string, ParkRun>();

export const runPark = (full: number, span = PARK.span, keep = true, seed = 23): ParkRun => {
  const id = `${full}:${span}:${keep}:${seed}`;
  if (RUNS.has(id)) return RUNS.get(id)!;
  const rnd = mulberry(seed);
  const taken = new Uint8Array(SPACES);
  const leaves = new Float64Array(SPACES).fill(Infinity);
  // the start: the car park as full as asked, the spaces near the entrance taken first (as people do)
  for (let i = 0; i < SPACES; i++) {
    if (rnd() < Math.min(0.99, full * (1.25 - (0.5 * i) / SPACES))) {
      taken[i] = 1;
      leaves[i] = -Math.log(1 - rnd()) * PARK.stay;
    }
  }
  const rate = (full * SPACES) / PARK.stay;
  const searches: Searcher[] = [];
  let occupied = 0;
  let samples = 0;
  const driving: Searcher[] = [];
  const frames: ParkFrame[] = [];
  let nextArrival = -Math.log(1 - rnd()) / rate;
  let n = 0;
  const loop = ROUTE + PARK.back;
  for (let t = 0; t <= span; t += PARK.step) {
    for (let i = 0; i < SPACES; i++) if (taken[i] && leaves[i] <= t) taken[i] = 0;
    while (nextArrival <= t) {
      driving.push({id: n++, arrive: nextArrival, d: 0, done: -1, space: -1, laps: 0});
      nextArrival += -Math.log(1 - rnd()) / rate;
    }
    for (const car of [...driving]) {
      const before = car.d;
      car.d += PARK.speed * PARK.step;
      const lap = Math.floor(before / loop);
      const a = before - lap * loop;
      const b = car.d - lap * loop;
      // the free spaces passed in this step, first come first served
      let found = -1;
      for (let i = 0; i < SPACES && found < 0; i++) {
        const s = spaceAt(i);
        if (!taken[i] && s >= a && s < b) found = i;
      }
      if (found >= 0) {
        taken[found] = 1;
        leaves[found] = t + -Math.log(1 - rnd()) * PARK.stay;
        car.done = t;
        car.space = found;
        car.laps = lap;
        searches.push(car);
        driving.splice(driving.indexOf(car), 1);
      }
    }
    if (t > 2000 && Math.round(t) % 20 === 0) {
      occupied += taken.reduce((a, b) => a + b, 0) / SPACES;
      samples++;
    }
    if (keep) frames.push({t, taken: Uint8Array.from(taken), cars: driving.map((c) => ({id: c.id, d: c.d % loop}))});
  }
  const at = (t: number) => frames[Math.max(0, Math.min(frames.length - 1, Math.round(t / PARK.step)))];
  const run = {frames, searches, at, full: samples ? occupied / samples : full};
  if (keep) RUNS.set(id, run);
  return run;
};

/** The mean search (arrival → parked) of those who arrived between `from` and `to`, and how full it really was. */
export const searchTime = (run: ParkRun, from: number, to: number) => {
  const s = run.searches.filter((c) => c.arrive >= from && c.arrive <= to).map((c) => c.done - c.arrive);
  return {mean: s.length ? s.reduce((a, b) => a + b, 0) / s.length : 0, longest: s.length ? Math.max(...s) : 0};
};

/** Mean search time against how full the car park really was: demand from 50 to 95 %, four car parks each, 8 hours
 * (computed with runPark(demand, 30000, false, seed 41-44) — see parkCurve — and kept here: too slow for every frame). */
export const CURVE: [number, number][] = [[0.495, 21.2], [0.587, 25.1], [0.7, 30.2], [0.785, 34.5], [0.832, 39.6], [0.88, 63.6], [0.921, 72], [0.955, 172]];

export const parkCurve = () => {
  const out: [number, number][] = [];
  for (const demand of [0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.93, 0.95]) {
    let occ = 0;
    let wait = 0;
    for (const seed of [41, 42, 43, 44]) {
      const r = runPark(demand, 30000, false, seed);
      occ += r.full / 4;
      wait += searchTime(r, 2000, 28000).mean / 4;
    }
    out.push([Math.round(occ * 1000) / 1000, Math.round(wait * 10) / 10]);
  }
  return out;
};

/** The search time the curve gives for a car park this full (interpolated). */
export const searchAt = (full: number) => {
  const c = CURVE;
  if (full <= c[0][0]) return c[0][1];
  for (let i = 1; i < c.length; i++) {
    if (full <= c[i][0]) return c[i - 1][1] + ((c[i][1] - c[i - 1][1]) * (full - c[i - 1][0])) / (c[i][0] - c[i - 1][0]);
  }
  return c[c.length - 1][1];
};
