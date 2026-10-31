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
export const zonesOf = (lifts: number, zoned: boolean): number[][] => {
  const all = Array.from({length: LIFT.floors}, (_, i) => i + 1);
  if (!zoned || lifts < 2) return Array.from({length: lifts}, () => all);
  const low = Math.floor(lifts / 2);
  const cut = LIFT.floors / 2;
  return Array.from({length: lifts}, (_, i) => (i < low ? all.filter((f) => f <= cut) : all.filter((f) => f > cut)));
};

const RUNS = new Map<string, LiftRun>();

export const runLifts = (lifts: number, zoned: boolean, rate: number, span = LIFT.span, keep = true): LiftRun => {
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
export const liftLong = (lifts: number, zoned: boolean, rate: number) => {
  const id = `${lifts}:${zoned}:${rate}`;
  if (!LONG.has(id)) LONG.set(id, liftWaits(runLifts(lifts, zoned, rate, 20000, false), 1000, 19000));
  return LONG.get(id)!;
};
