// Lifts in an office building at the morning rush (deterministic, seeded): people arrive in the lobby at random
// (Poisson), each going up to a floor; a lift at the lobby takes up to LIFT.cap of them, leaves when full or LIFT.dwell
// seconds after the first one got in, stops at every floor someone asked for (LIFT.stop seconds: doors and people out)
// and comes back down without stopping. `zones`: half the lifts serve only the low floors, the others only the high
// ones (an express run to the first of theirs) — fewer stops per trip, so each lift is back sooner.
import {mulberry} from './world';

export const LIFT = {floors: 12, cap: 10, perFloor: 1.6, start: 2, stop: 8, dwell: 8, step: 0.5, span: 2400};

export type Rider = {id: number; arrive: number; floor: number};
type Leg = {t: number; floor: number};                  // waypoints: at time t the lift is at `floor` (0 = lobby)
export type LiftFrame = {t: number; pos: number[]; open: number[]; load: number[]; queue: number[][]};
export type LiftRun = {riders: Rider[]; frames: LiftFrame[]; boarded: Map<number, number>; arrived: Map<number, number>;
  lifts: number; zones: number[][]; at: (t: number) => LiftFrame; stops: number[]};

export const riders = (rate: number, seed = 17, span = LIFT.span): Rider[] => {
  const rnd = mulberry(seed);
  const out: Rider[] = [];
  for (let t = 0, id = 0; t < span; id++) {
    t += -Math.log(1 - rnd()) / rate;
    out.push({id, arrive: t, floor: 1 + Math.floor(rnd() * LIFT.floors)});
  }
  return out;
};

/** The floors each lift serves: all of them, or (zones) the low half for the first half of the lifts. */
export const zonesOf = (lifts: number, zoned: boolean | 'bands'): number[][] => {
  const all = Array.from({length: LIFT.floors}, (_, i) => i + 1);
  if (!zoned || lifts < 2) return Array.from({length: lifts}, () => all);
  if (zoned === 'bands') {
    // destination dispatch: the screen sends people going to nearby floors to the same car (a band each)
    const size = Math.ceil(LIFT.floors / lifts);
    return Array.from({length: lifts}, (_, k) => all.filter((f) => f > k * size && f <= (k + 1) * size));
  }
  const low = Math.floor(lifts / 2);
  const cut = LIFT.floors / 2;
  return Array.from({length: lifts}, (_, i) => (i < low ? all.filter((f) => f <= cut) : all.filter((f) => f > cut)));
};

const RUNS = new Map<string, LiftRun>();

export const runLifts = (lifts: number, zoned: boolean | 'bands', rate: number, span = LIFT.span, keep = true): LiftRun => {
  const id = `${lifts}:${zoned}:${rate}:${span}`;
  if (RUNS.has(id)) return RUNS.get(id)!;
  const people = riders(rate, 17, span);
  const zones = zonesOf(lifts, zoned);
  const groups = [...new Set(zones.map((z) => z.join(',')))];             // one waiting line per set of floors
  const groupOf = (floor: number) => groups.findIndex((g) => g.split(',').map(Number).includes(floor));
  const liftGroup = zones.map((z) => groups.indexOf(z.join(',')));
  const queue: number[][] = groups.map(() => []);
  const byId = new Map(people.map((p) => [p.id, p]));
  const plan: Leg[][] = Array.from({length: lifts}, () => [{t: 0, floor: 0}]);
  const freeAt = Array(lifts).fill(0);                     // back at the lobby, doors open
  const inside: number[][] = Array.from({length: lifts}, () => []);
  const firstIn = Array(lifts).fill(-1);
  const boarded = new Map<number, number>();
  const arrived = new Map<number, number>();
  const stops: number[] = [];
  const frames: LiftFrame[] = [];
  let next = 0;
  const posAt = (k: number, t: number) => {
    const legs = plan[k];
    if (t <= legs[0].t) return legs[0].floor;
    for (let i = 1; i < legs.length; i++) {
      if (t <= legs[i].t) {
        const a = legs[i - 1];
        const b = legs[i];
        return a.floor + ((b.floor - a.floor) * (t - a.t)) / Math.max(1e-9, b.t - a.t);
      }
    }
    return legs[legs.length - 1].floor;
  };
  for (let t = 0; t <= span; t += LIFT.step) {
    while (next < people.length && people[next].arrive <= t) {
      const p = people[next++];
      queue[groupOf(p.floor)].push(p.id);
    }
    for (let k = 0; k < lifts; k++) {
      if (t < freeAt[k]) continue;
      const line = queue[liftGroup[k]];
      // the first free lift of its group at the lobby takes the people (the others wait behind it)
      const ahead = Array.from({length: k}, (_, j) => j).some((j) => liftGroup[j] === liftGroup[k] && t >= freeAt[j] && inside[j].length < LIFT.cap);
      if (!ahead) {
        while (line.length && inside[k].length < LIFT.cap) {
          const who = line.shift()!;
          inside[k].push(who);
          boarded.set(who, t);
          if (firstIn[k] < 0) firstIn[k] = t;
        }
      }
      if (inside[k].length && (inside[k].length >= LIFT.cap || t - firstIn[k] >= LIFT.dwell)) {
        // the trip: up, stopping at each floor asked for, then straight down
        const floors = [...new Set(inside[k].map((id) => byId.get(id)!.floor))].sort((a, b) => a - b);
        stops.push(floors.length);
        const legs: Leg[] = [{t, floor: 0}];
        let clock = t + LIFT.start;
        let at = 0;
        for (const f of floors) {
          clock += (f - at) * LIFT.perFloor;
          legs.push({t: clock, floor: f});
          for (const id of inside[k]) if (byId.get(id)!.floor === f) arrived.set(id, clock);
          clock += LIFT.stop;
          legs.push({t: clock, floor: f});
          at = f;
        }
        clock += LIFT.start + at * LIFT.perFloor;
        legs.push({t: clock, floor: 0});
        plan[k] = legs;
        freeAt[k] = clock;
        inside[k] = [];
        firstIn[k] = -1;
      }
    }
    if (keep) {
      frames.push({t, pos: plan.map((_, k) => posAt(k, t)), load: inside.map((l) => l.length),
        open: plan.map((legs, k) => (t >= freeAt[k] ? 1 : legs.some((l, i) => i > 0 && legs[i - 1].floor === l.floor && t >= legs[i - 1].t && t <= l.t) ? 1 : 0)),
        queue: queue.map((l) => [...l])});
    }
  }
  const at = (t: number) => frames[Math.max(0, Math.min(frames.length - 1, Math.round(t / LIFT.step)))];
  const run = {riders: people, frames, boarded, arrived, lifts, zones, at, stops};
  if (keep) RUNS.set(id, run);
  return run;
};

/** Mean and longest wait in the lobby of those who got in between `from` and `to`; mean stops per trip. */
export const liftWaits = (run: LiftRun, from: number, to: number) => {
  const w: number[] = [];
  for (const p of run.riders) {
    const b = run.boarded.get(p.id);
    if (b !== undefined && p.arrive >= from && p.arrive <= to) w.push(b - p.arrive);
  }
  return {mean: w.length ? w.reduce((a, b) => a + b, 0) / w.length : 0, longest: w.length ? Math.max(...w) : 0,
          stops: run.stops.reduce((a, b) => a + b, 0) / Math.max(1, run.stops.length)};
};

const LONG = new Map<string, ReturnType<typeof liftWaits>>();
export const liftLong = (lifts: number, zoned: boolean | 'bands', rate: number) => {
  const id = `${lifts}:${zoned}:${rate}`;
  if (!LONG.has(id)) LONG.set(id, liftWaits(runLifts(lifts, zoned, rate, 20000, false), 1000, 19000));
  return LONG.get(id)!;
};

// --- all day: cars sweeping up and down, people on every floor (bunching) ------------------------------------------------
// Each car goes up to the top and back down (a loop of 2 × floors), stopping where someone inside gets off or someone
// waiting goes its way. Nothing else — and yet a car a little late finds more people, stops longer, gets later, while
// the one behind finds the floors empty and catches up: they end up travelling together (bus bunching, Newell & Potts,
// 1964). Rules (`mode`):
//  cercano   any car stops for anyone (the usual)
//  reparto   the system keeps them apart: a car waits at the lobby until the one ahead is far enough (holding)
//  destino   destination dispatch: at the lobby each car takes only people going to its band of floors
//  botones   one in two people press both buttons: cars going the wrong way stop for nobody
export const LOOP = {floors: 14, cap: 12, perFloor: 1.4, stop: 10, perPerson: 1.5, dt: 0.5};
export type LoopFrame = {t: number; pos: number[]; dir: number[]; load: number[]; stopped: number[]; useless: number[];
  up: number[]; down: number[]};
export type LoopRun = {frames: LoopFrame[]; waits: number[]; boardedAt: number[]; arrive: number[]; stops: number[];
  at: (t: number) => LoopFrame; cars: number; mode: string; useless: number};

const LOOPS = new Map<string, LoopRun>();

export const runLoop = (cars: number, mode: string, rate: number, span = 3600, keep = true, seed = 5): LoopRun => {
  const id = `${cars}:${mode}:${rate}:${span}:${keep}:${seed}`;
  if (LOOPS.has(id)) return LOOPS.get(id)!;
  const F = LOOP.floors;
  const rnd = mulberry(seed);
  type P = {from: number; to: number; at: number; both: boolean; car: number};
  const people: P[] = [];
  for (let t = 0; t < span;) {
    t += -Math.log(1 - rnd()) / rate;
    const r = rnd();
    const from = r < 0.5 ? 0 : 1 + Math.floor(rnd() * F);
    let to = r < 0.5 ? 1 + Math.floor(rnd() * F) : r < 0.75 ? 0 : 1 + Math.floor(rnd() * F);
    if (to === from) to = from === F ? 0 : from + 1;
    people.push({from, to, at: t, both: mode === 'botones' && rnd() < 0.5 && from > 0, car: Math.floor(((to - 1) / F) * cars)});
  }
  const waiting: number[][] = Array.from({length: (F + 1) * 2}, () => []);         // [floor*2 + (up ? 0 : 1)]
  const phantom = new Uint8Array((F + 1) * 2);                                     // a button pressed by nobody going that way
  const inside: number[][] = Array.from({length: cars}, () => []);
  // start evenly spread over the loop
  const pos = Array.from({length: cars}, (_, k) => { const ph = (k / cars) * 2 * F; return ph <= F ? ph : 2 * F - ph; });
  const dir = Array.from({length: cars}, (_, k) => ((k / cars) * 2 * F < F ? 1 : -1));
  const dwell = Array(cars).fill(0);
  const stoppedAt = Array(cars).fill(-1);
  const lastLobby = Array(cars).fill(-1e9);
  const holdSince = Array(cars).fill(-1);
  const waits: number[] = [];
  const boardedAt = Array(people.length).fill(-1);
  const stops: number[] = [];
  let tripStops = Array(cars).fill(0);
  let useless = 0;
  const uselessNow = Array(cars).fill(0);
  const frames: LoopFrame[] = [];
  let next = 0;
  const headway = (2 * F * LOOP.perFloor + 2 * F * 0.4 * LOOP.stop) / cars;        // a rough round trip / cars
  for (let t = 0; t <= span; t += LOOP.dt) {
    while (next < people.length && people[next].at <= t) {
      const p = people[next];
      waiting[p.from * 2 + (p.to > p.from ? 0 : 1)].push(next);
      if (p.both) phantom[p.from * 2 + (p.to > p.from ? 1 : 0)] = 1;
      next++;
    }
    for (let k = 0; k < cars; k++) {
      uselessNow[k] = Math.max(0, uselessNow[k] - LOOP.dt);
      if (dwell[k] > 0) {
        dwell[k] -= LOOP.dt;
        continue;
      }
      const at = Math.round(pos[k]);
      if (Math.abs(pos[k] - at) < 1e-6 && stoppedAt[k] !== at) {
        // arriving at a floor: turn at the ends, let people out and in, or go on
        if (at === F) dir[k] = -1;
        if (at === 0) dir[k] = 1;
        const slot = at * 2 + (dir[k] > 0 ? 0 : 1);
        const out = inside[k].filter((i) => people[i].to === at);
        let line = waiting[slot];
        if (mode === 'destino' && at === 0) line = line.filter((i) => people[i].car === k);
        const room = LOOP.cap - (inside[k].length - out.length);
        const taking = line.slice(0, Math.max(0, room));
        const ghost = phantom[slot] === 1 && !out.length && !taking.length;
        if ((at === 0 || at === F) && mode === 'reparto' && t > 30) {
          // holding: the car leaves the lobby only when the last one left long enough ago
          // the car ahead must be at least most of 1/cars of the loop away (and nobody waits more than a minute)
          const here = at === 0 ? 0 : 0.5;
          const ahead = Math.min(...pos.map((q, j) => (j === k ? 1 : ((phase(q, dir[j]) - here + 1) % 1) || 1)));
          if (ahead < 0.9 / cars && (holdSince[k] < 0 || t - holdSince[k] < 90)) {
            if (holdSince[k] < 0) holdSince[k] = t;
            inside[k] = inside[k].filter((i) => people[i].to !== at).concat(taking);
            waiting[slot] = waiting[slot].filter((i) => !taking.includes(i));
            taking.forEach((i) => { boardedAt[i] = t; waits.push(t - people[i].at); });
            dwell[k] = LOOP.dt;
            continue;                                    // still at the lobby, looked at again next step
          }
        }
        holdSince[k] = -1;
        stoppedAt[k] = at;
        if (out.length || taking.length || ghost) {
          inside[k] = inside[k].filter((i) => people[i].to !== at).concat(taking);
          waiting[slot] = waiting[slot].filter((i) => !taking.includes(i));
          taking.forEach((i) => { boardedAt[i] = t; waits.push(t - people[i].at); });
          phantom[slot] = 0;
          dwell[k] = LOOP.stop + LOOP.perPerson * (out.length + taking.length);
          tripStops[k]++;
          if (ghost) { useless++; uselessNow[k] = 4; }
        }
        if (at === 0) { lastLobby[k] = t; stops.push(tripStops[k]); tripStops[k] = 0; }
        if (dwell[k] > 0) continue;
      }
      // on towards the next floor (landing exactly on it)
      const target = Math.abs(pos[k] - Math.round(pos[k])) < 1e-6 ? Math.round(pos[k]) + dir[k] : dir[k] > 0 ? Math.ceil(pos[k]) : Math.floor(pos[k]);
      const moved = pos[k] + (dir[k] * LOOP.dt) / LOOP.perFloor;
      pos[k] = dir[k] > 0 ? Math.min(moved, target) : Math.max(moved, target);
      if (Math.abs(pos[k] - target) < 1e-6) { pos[k] = target; stoppedAt[k] = -1; }
    }
    if (keep) {
      frames.push({t, pos: [...pos], dir: [...dir], load: inside.map((l) => l.length), stopped: dwell.map((d) => (d > 0 ? 1 : 0)),
                   useless: [...uselessNow], up: waiting.filter((_, j) => j % 2 === 0).map((l) => l.length), down: waiting.filter((_, j) => j % 2 === 1).map((l) => l.length)});
    }
  }
  const at = (t: number) => frames[Math.max(0, Math.min(frames.length - 1, Math.round(t / LOOP.dt)))];
  const run = {frames, waits, boardedAt, arrive: people.map((p) => p.at), stops, at, cars, mode, useless};
  if (keep) LOOPS.set(id, run);
  return run;
};

/** Where a car is on its loop (0 → 1): going up from the lobby, then coming down. */
export const phase = (pos: number, dir: number) => (dir > 0 ? pos : 2 * LOOP.floors - pos) / (2 * LOOP.floors);

/** How bunched the cars are now: 0 evenly spread, 1 all together (for 2 cars: 1 − the gap between them / half a loop). */
export const bunching = (f: LoopFrame) => {
  const ph = f.pos.map((p, k) => phase(p, f.dir[k])).sort((a, b) => a - b);
  const gaps = ph.map((p, k) => ((ph[(k + 1) % ph.length] - p + 1) % 1) || (ph.length === 1 ? 1 : 0));
  const ideal = 1 / ph.length;
  return Math.min(1, gaps.reduce((s, g) => s + Math.abs(g - ideal), 0) / (2 * (1 - ideal)));
};

const LOOP_STATS = new Map<string, {wait: number; bunch: number; stops: number}>();
export const loopStats = (cars: number, mode: string, rate: number) => {
  const id = `${cars}:${mode}:${rate}`;
  if (!LOOP_STATS.has(id)) {
    const r = runLoop(cars, mode, rate, 14400, true, 9);
    const w = r.waits.slice(Math.floor(r.waits.length * 0.15));
    const fr = r.frames.slice(Math.floor(r.frames.length * 0.15));
    LOOP_STATS.set(id, {wait: w.reduce((a, b) => a + b, 0) / Math.max(1, w.length), bunch: fr.reduce((s, f) => s + bunching(f), 0) / Math.max(1, fr.length),
                        stops: r.stops.reduce((a, b) => a + b, 0) / Math.max(1, r.stops.length)});
    LOOPS.delete(`${cars}:${mode}:${rate}:14400:true:9`);
  }
  return LOOP_STATS.get(id)!;
};
