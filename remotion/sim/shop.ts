// A supermarket's tills, simulated step by step (deterministic, seeded): customers arrive at random (Poisson), each
// with a basket or a cart, and take as long to pay as a person takes (≈ 40 s: greeting, bags, the card) plus each item
// (≈ 3 s) — Dan Meyer's timings — and now and then something slow (a coupon, a price check). The kinds of shop:
//  many    one line per till: each customer joins the line with fewest heads; `jockey` moves YOU at a moment
//  one     one line that feeds whichever till frees first
//  express till 0 only for ≤ 10 items, the others for everyone
// `equal`: everyone takes exactly the average time (rule two removed).
import {mulberry} from './world';

export const SHOP = {perPerson: 40, perItem: 3, slowShare: 0.12, slowMin: 45, slowMax: 110, step: 0.5, span: 1800};

export type Person = {id: number; arrive: number; items: number; service: number; slow: boolean};
export type ShopFrame = {t: number; lines: number[][]; paying: number[]; left: number[]};
export type ShopRun = {people: Person[]; frames: ShopFrame[]; start: Map<number, number>; end: Map<number, number>;
  tillOf: Map<number, number>; at: (t: number) => ShopFrame; tills: number};

export type Jockey = {you: number; at: number; to: number};

export const customers = (rate: number, equal = false, seed = 31, span = SHOP.span): Person[] => {
  const rnd = mulberry(seed);
  const out: Person[] = [];
  for (let t = 0, id = 0; t < span; id++) {
    t += -Math.log(1 - rnd()) / rate;
    const cart = rnd() < 0.45;
    const items = cart ? 12 + Math.floor(rnd() * 30) : 1 + Math.floor(rnd() * 9);
    const slow = rnd() < SHOP.slowShare;
    const service = SHOP.perPerson + SHOP.perItem * items + (slow ? SHOP.slowMin + rnd() * (SHOP.slowMax - SHOP.slowMin) : 0);
    out.push({id, arrive: t, items, service, slow});
  }
  if (equal) {          // the same people, the same average time each
    const mean = out.reduce((a, p) => a + p.service, 0) / out.length;
    for (const p of out) {
      p.service = mean;
      p.slow = false;
    }
  }
  return out;
};

const RUNS = new Map<string, ShopRun>();

export const runShop = (kind: 'many' | 'one' | 'express', tills: number, people: Person[], key: string, jockey?: Jockey,
                        span = SHOP.span, keep = true): ShopRun => {
  const id = `${kind}:${tills}:${key}:${jockey ? `${jockey.you}-${jockey.at}-${jockey.to}` : ''}:${span}`;
  if (RUNS.has(id)) return RUNS.get(id)!;
  const lines: number[][] = Array.from({length: kind === 'one' ? 1 : tills}, () => []);
  const paying = Array(tills).fill(-1);
  const left = Array(tills).fill(0);
  const start = new Map<number, number>();
  const end = new Map<number, number>();
  const tillOf = new Map<number, number>();
  const byId = new Map(people.map((p) => [p.id, p]));
  const frames: ShopFrame[] = [];
  let next = 0;
  const dt = SHOP.step;
  const heads = (i: number) => lines[i].length + (paying[i] >= 0 ? 1 : 0);
  let moved = false;
  for (let t = 0; t <= span; t += dt) {
    while (next < people.length && people[next].arrive <= t) {
      const p = people[next++];
      let line = 0;
      if (kind === 'many' || kind === 'express') {
        const open = Array.from({length: tills}, (_, i) => i).filter((i) => kind !== 'express' || i > 0 || p.items <= 10);
        line = open.reduce((a, b) => (heads(b) < heads(a) ? b : a));
        if (jockey && p.id === jockey.you) line = jockey.to === 0 ? 1 : 0;      // YOU picks the line you will leave
      }
      lines[line].push(p.id);
    }
    if (jockey && !moved && t >= jockey.at) {          // YOU leaves your line for the end of the other one
      moved = true;
      for (const l of lines) {
        const k = l.indexOf(jockey.you);
        if (k >= 0) l.splice(k, 1);
      }
      lines[jockey.to].push(jockey.you);
    }
    for (let i = 0; i < tills; i++) {
      if (paying[i] >= 0) {
        left[i] -= dt;
        if (left[i] <= 0) {
          end.set(paying[i], t);
          paying[i] = -1;
        }
      }
      if (paying[i] < 0) {
        const line = kind === 'one' ? lines[0] : lines[i];
        if (line.length) {
          const who = line.shift()!;
          paying[i] = who;
          left[i] = byId.get(who)!.service;
          start.set(who, t);
          tillOf.set(who, i);
        }
      }
    }
    if (keep) frames.push({t, lines: lines.map((l) => [...l]), paying: [...paying], left: [...left]});
  }
  const at = (t: number) => frames[Math.max(0, Math.min(frames.length - 1, Math.round(t / dt)))];
  const run = {people, frames, start, end, tillOf, at, tills};
  RUNS.set(id, run);
  return run;
};

/** Mean and longest wait (arrival → paying) of those who started paying between `from` and `to`. */
export const waits = (run: ShopRun, from: number, to: number) => {
  const w: number[] = [];
  for (const p of run.people) {
    const s = run.start.get(p.id);
    if (s !== undefined && s >= from && s <= to) w.push(s - p.arrive);
  }
  return {mean: w.length ? w.reduce((a, b) => a + b, 0) / w.length : 0, longest: w.length ? Math.max(...w) : 0, n: w.length};
};

/** «Which line wins?»: `tills` lines of `ahead` people each, random people; how often YOUR line (line 0) empties
 * first, over the first `trials` tries. */
export const lottery = (tills: number, trials: number, ahead = 3, seed = 5) => {
  const rnd = mulberry(seed);
  let mine = 0;
  const tally: number[] = [];
  for (let k = 0; k < trials; k++) {
    const times = Array.from({length: tills}, () => {
      let s = 0;
      for (let j = 0; j < ahead; j++) {
        const items = rnd() < 0.45 ? 12 + Math.floor(rnd() * 30) : 1 + Math.floor(rnd() * 9);
        s += SHOP.perPerson + SHOP.perItem * items + (rnd() < SHOP.slowShare ? SHOP.slowMin + rnd() * 60 : 0);
      }
      return s;
    });
    if (times[0] <= Math.min(...times)) mine++;
    tally.push(mine);
  }
  return tally;
};

/** Kingman's formula: the mean wait in a queue, in units of the mean service time, for an occupation `rho` and the
 * variability of arrivals and of service (squared coefficients of variation). */
export const kingman = (rho: number, ca2 = 1, cs2 = 1) => (rho / (1 - rho)) * ((ca2 + cs2) / 2);

const LONG = new Map<string, {mean: number; longest: number; small: number}>();
/** The same shop over 16 hours (no frames kept): the figures the panels give, without the noise of half an hour.
 * `small`: the mean wait of those with ≤ 10 items. */
export const longRun = (kind: 'many' | 'one' | 'express', tills: number, rate: number, equal = false) => {
  const id = `${kind}:${tills}:${rate}:${equal}`;
  if (!LONG.has(id)) {
    const span = 60000;
    const people = customers(rate, equal, 31, span);
    const run = runShop(kind, tills, people, `long${rate}${equal}`, undefined, span, false);
    const w = waits(run, 1000, span - 1000);
    const small = people.filter((p) => p.items <= 10 && run.start.has(p.id) && p.arrive > 1000 && p.arrive < span - 1000);
    LONG.set(id, {...w, small: small.reduce((a, p) => a + run.start.get(p.id)! - p.arrive, 0) / Math.max(1, small.length)});
    RUNS.clear();                                   // the long run is not drawn: do not keep it
  }
  return LONG.get(id)!;
};
