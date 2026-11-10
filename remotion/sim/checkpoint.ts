// One security lane at an airport, station by station (deterministic, seeded): the line → the tray table, where
// passengers get ready (one at a time on a classic table, several at once on an automated lane, where whoever is
// ready first goes first) → the belt and the X-ray scanner, one tray every 18 s (200 an hour), at a fixed pace →
// meanwhile the passenger walks through the arch (a beep: back, off with the belt, through again) → the end of the belt,
// where the trays wait for their owner; when it is full the scanner has to stop.
// Kinds of traveller: frequent (ready in seconds, one or two trays), occasional, families (slow, many trays). Some of
// the occasional ones bring a bottle, the laptop in the bag, a buckle: their trouble shows over their head.
import {mulberry} from './world';

export type Kind = 0 | 1 | 2;                                   // frequent · occasional · family
export const TRAY_SECONDS = 18;                                 // the scanner: 200 trays an hour
const EXIT_CAP = 8;                                             // trays the end of the belt holds
const WALK = 4;                                                 // from the table to the arch
const BEEP_BACK = 40;                                           // back, belt off, through again
export const TROUBLE = ['💧', '💻', '🔔', '👜'] as const;     // a bottle, the laptop still in the bag, a buckle, a bag to open

export type Pax = {id: number; kind: Kind; arrive: number; trays: number; prep: number; trouble: number; beep: boolean;
  lane: number; prepStart: number; prepEnd: number; slot: number; archAt: number; collectStart: number; collectEnd: number};
export type Tray = {owner: number; lane: number; ready: number; scanStart: number; scanEnd: number};
export type LaneRun = {pax: Pax[]; trays: Tray[]; lanes: number; slots: number; span: number;
  scannerIdle: number[]; meanWait: (from?: number, to?: number, kind?: Kind) => number; perHour: number};

export type Setup = {slots: number; lanes?: number; split?: boolean; rate: number; span?: number; seed?: number;
  share?: [number, number, number]; wave?: (t: number) => number};

const PREP: [number, number][] = [[14, 6], [42, 18], [80, 30]];   // seconds at the table: mean, spread (frequent, occasional, family)
const TRAYS: [number, number][] = [[1, 1], [2, 0], [2, 1]];        // trays: from, extra (≈ 1.9 a person on average)

const SPLIT: number[][] = [[0], [1, 2], [3]];                  // with `split` (four lanes): which lanes each kind uses
const CACHE = new Map<string, LaneRun>();

export const runLane = (setup: Setup): LaneRun => {
  const lanes = setup.lanes ?? 1;
  const span = setup.span ?? 3600;
  const share = setup.share ?? [0.35, 0.5, 0.15];
  const id = JSON.stringify({...setup, wave: setup.wave ? String(setup.wave) : ''});
  if (CACHE.has(id)) return CACHE.get(id)!;
  const rnd = mulberry(setup.seed ?? 31);
  const pax: Pax[] = [];
  for (let t = 0; t < span;) {
    const rate = setup.rate * (setup.wave ? setup.wave(t) : 1);
    t += -Math.log(1 - rnd()) / Math.max(1e-6, rate);
    if (t >= span) break;
    const r = rnd();
    const kind: Kind = r < share[0] ? 0 : r < share[0] + share[1] ? 1 : 2;
    const [mean, spread] = PREP[kind];
    const trouble = kind === 1 && rnd() < 0.3 ? Math.floor(rnd() * TROUBLE.length) : -1;
    const prep = Math.max(6, mean + (rnd() * 2 - 1) * spread + (trouble >= 0 ? 25 + rnd() * 35 : 0));
    pax.push({id: pax.length, kind, arrive: t, trays: TRAYS[kind][0] + Math.floor(rnd() * (TRAYS[kind][1] + 1)), prep, trouble,
              beep: rnd() < [0.04, 0.12, 0.15][kind] || trouble === 2, lane: 0, prepStart: Infinity, prepEnd: Infinity, slot: -1,
              archAt: Infinity, collectStart: Infinity, collectEnd: Infinity});
  }
  const trays: Tray[] = [];
  const queues: number[][] = Array.from({length: lanes}, () => []);
  const slots: number[][] = Array.from({length: lanes}, () => Array(setup.slots).fill(-1));
  const belt: number[][] = Array.from({length: lanes}, () => []);          // trays waiting for the scanner
  const scanning: number[] = Array(lanes).fill(-1);
  const exit: number[][] = Array.from({length: lanes}, () => []);          // trays out of the scanner, not collected
  const waiting: number[][] = Array.from({length: lanes}, () => []);       // through the arch, waiting for their trays
  const idle = Array(lanes).fill(0);
  let next = 0;
  const end = span + 3 * 3600;
  for (let now = 0; now < end; now++) {
    while (next < pax.length && pax[next].arrive <= now) {
      const p = pax[next++];
      // separate lanes by kind of traveller, or the shortest line
      // separate lanes by kind of traveller (four lanes: frequent · occasional · occasional · families), or any lane:
      // the shortest line of the ones it may use
      const allowed = setup.split ? SPLIT[p.kind] : queues.map((_, i) => i);
      const load = (i: number) => queues[i].length + slots[i].filter((s) => s >= 0).length;
      p.lane = allowed.reduce((best, i) => (load(i) < load(best) ? i : best), allowed[0]);
      queues[p.lane].push(p.id);
    }
    for (let l = 0; l < lanes; l++) {
      // the table: whoever is ready leaves (on an automated lane, in the order they finish)
      for (let k = 0; k < setup.slots; k++) {
        const who = slots[l][k];
        if (who >= 0 && pax[who].prepEnd <= now) {
          const p = pax[who];
          for (let n = 0; n < p.trays; n++) {
            trays.push({owner: who, lane: l, ready: now, scanStart: Infinity, scanEnd: Infinity});
            belt[l].push(trays.length - 1);
          }
          p.archAt = now + WALK + (p.beep ? BEEP_BACK : 0);
          waiting[l].push(who);
          slots[l][k] = -1;
        }
        if (slots[l][k] < 0 && queues[l].length) {
          const p = pax[queues[l].shift()!];
          p.prepStart = now;
          p.prepEnd = now + p.prep;
          p.slot = k;
          slots[l][k] = p.id;
        }
      }
      // the scanner: one tray at a time, at a fixed pace, unless the end of the belt is full
      if (scanning[l] >= 0 && trays[scanning[l]].scanEnd <= now) {
        exit[l].push(scanning[l]);
        scanning[l] = -1;
      }
      if (scanning[l] < 0 && belt[l].length && exit[l].length < EXIT_CAP) {
        const tr = trays[belt[l].shift()!];
        tr.scanStart = now;
        tr.scanEnd = now + TRAY_SECONDS;
        scanning[l] = trays.indexOf(tr);
      } else if (scanning[l] < 0 && now < span) idle[l]++;
      // the end of the belt: through the arch and all their trays out → they pick them up (and dress) and go
      for (const who of [...waiting[l]]) {
        const p = pax[who];
        const mine = exit[l].filter((x) => trays[x].owner === who);
        if (p.archAt <= now && p.collectStart === Infinity && mine.length === p.trays) {
          p.collectStart = now;
          p.collectEnd = now + 10 + 6 * p.trays;
        }
        if (p.collectEnd <= now) {
          exit[l] = exit[l].filter((x) => trays[x].owner !== who);
          waiting[l] = waiting[l].filter((x) => x !== who);
        }
      }
    }
  }
  const meanWait = (from = 600, to = span, kind?: Kind) => {
    const xs = pax.filter((p) => p.arrive >= from && p.arrive < to && (kind === undefined || p.kind === kind) && isFinite(p.prepStart))
      .map((p) => p.prepStart - p.arrive);
    return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0;
  };
  const done = pax.filter((p) => p.collectEnd <= span).length;
  const run: LaneRun = {pax, trays, lanes, slots: setup.slots, span, scannerIdle: idle.map((x) => x / span), meanWait,
                        perHour: (done / span) * 3600};
  CACHE.set(id, run);
  return run;
};

/** People an hour each station could let through on its own (mean of the mix). */
export const stationRates = (slots: number, share: [number, number, number] = [0.35, 0.5, 0.15]) => {
  const prep = share.reduce((a, w, k) => a + w * (PREP[k][0] + (k === 1 ? 0.3 * 42 : 0)), 0);
  const trays = share.reduce((a, w, k) => a + w * (TRAYS[k][0] + TRAYS[k][1] / 2), 0);
  return {table: Math.round((3600 / prep) * slots), scanner: Math.round(3600 / TRAY_SECONDS / trays), trays: Math.round(3600 / TRAY_SECONDS)};
};
