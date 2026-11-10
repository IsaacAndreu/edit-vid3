// A restaurant kitchen at dinner time (deterministic, seeded): orders (tickets) come in at random, each one a dish that
// takes its time — a starter ≈ 4 min, a pasta ≈ 9, a steak ≈ 15 — and `cooks` stations take the next ticket as they
// free up. `order`: fifo (first come, first cooked, as on the rail) or quick (the quickest dish first: the mean wait
// falls, but a long dish can wait and wait). `load`: how busy the cooks are (arrivals for that share of their time).
import {mulberry} from './world';

export const KITCHEN = {step: 5, span: 3 * 3600, dishes: [{name: 'starter', mean: 240}, {name: 'pasta', mean: 540}, {name: 'steak', mean: 900}]};
export type Ticket = {id: number; arrive: number; dish: number; cook: number};
export type KitchenFrame = {t: number; rail: number[]; cooking: number[]; left: number[]; served: number};
export type KitchenRun = {tickets: Ticket[]; frames: KitchenFrame[]; start: Map<number, number>; done: Map<number, number>;
  at: (t: number) => KitchenFrame; cooks: number};

const MEAN = KITCHEN.dishes.reduce((a, d) => a + d.mean, 0) / KITCHEN.dishes.length;

export const tickets = (cooks: number, load: number, seed = 19, span = KITCHEN.span): Ticket[] => {
  const rnd = mulberry(seed);
  const rate = (cooks * load) / MEAN;
  const out: Ticket[] = [];
  for (let t = 0, id = 0; t < span; id++) {
    t += -Math.log(1 - rnd()) / rate;
    const dish = Math.floor(rnd() * KITCHEN.dishes.length);
    out.push({id, arrive: t, dish, cook: KITCHEN.dishes[dish].mean * (0.75 + rnd() * 0.5)});
  }
  return out;
};

const RUNS = new Map<string, KitchenRun>();

export const runKitchen = (cooks: number, load: number, order: 'fifo' | 'quick', span = KITCHEN.span, keep = true): KitchenRun => {
  const id = `${cooks}:${load}:${order}:${span}`;
  if (RUNS.has(id)) return RUNS.get(id)!;
  const list = tickets(cooks, load, 19, span);
  const byId = new Map(list.map((x) => [x.id, x]));
  const rail: number[] = [];
  const cooking = Array(cooks).fill(-1);
  const left = Array(cooks).fill(0);
  const start = new Map<number, number>();
  const done = new Map<number, number>();
  const frames: KitchenFrame[] = [];
  let next = 0;
  let served = 0;
  for (let t = 0; t <= span; t += KITCHEN.step) {
    while (next < list.length && list[next].arrive <= t) rail.push(list[next++].id);
    for (let k = 0; k < cooks; k++) {
      if (cooking[k] >= 0) {
        left[k] -= KITCHEN.step;
        if (left[k] <= 0) {
          done.set(cooking[k], t);
          served++;
          cooking[k] = -1;
        }
      }
      if (cooking[k] < 0 && rail.length) {
        let pick = 0;
        if (order === 'quick') rail.forEach((x, i) => { if (byId.get(x)!.cook < byId.get(rail[pick])!.cook) pick = i; });
        const who = rail.splice(pick, 1)[0];
        cooking[k] = who;
        left[k] = byId.get(who)!.cook;
        start.set(who, t);
      }
    }
    if (keep) frames.push({t, rail: [...rail], cooking: [...cooking], left: [...left], served});
  }
  const at = (t: number) => frames[Math.max(0, Math.min(frames.length - 1, Math.round(t / KITCHEN.step)))];
  const run = {tickets: list, frames, start, done, at, cooks};
  if (keep) RUNS.set(id, run);
  return run;
};

/** From the order to the plate on the pass: mean and longest, of the tickets that came in between `from` and `to`. */
export const ticketTimes = (run: KitchenRun, from: number, to: number) => {
  const w: number[] = [];
  for (const x of run.tickets) {
    const d = run.done.get(x.id);
    if (d !== undefined && x.arrive >= from && x.arrive <= to) w.push(d - x.arrive);
  }
  return {mean: w.length ? w.reduce((a, b) => a + b, 0) / w.length : 0, longest: w.length ? Math.max(...w) : 0};
};

const LONG = new Map<string, ReturnType<typeof ticketTimes>>();
export const kitchenLong = (cooks: number, load: number, order: 'fifo' | 'quick') => {
  const id = `${cooks}:${load}:${order}`;
  if (!LONG.has(id)) LONG.set(id, ticketTimes(runKitchen(cooks, load, order, 400000, false), 5000, 390000));
  return LONG.get(id)!;
};
