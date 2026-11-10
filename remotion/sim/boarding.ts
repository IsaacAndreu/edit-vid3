// Boarding a plane, simulated person by person (deterministic, seeded). One aisle, one person per row of it, nobody
// overtakes: each passenger walks to their row (≈ 1 s a row), stops there to stow the carry-on (≈ 6-20 s; longer when
// the bin above is full: they open bins row after row looking for room) and then sits — if someone already sits
// between the aisle and their seat, that person stands up, steps out and sits again (≈ 6 s each). Whoever stops in the
// aisle stops everyone behind. Methods (the order at the door):
//  bloques   back to front by blocks of rows (3 groups, shuffled inside: what most airlines do)
//  azar      no order at all
//  vcp       windows, then middles, then aisles (shuffled inside)
//  steffen   Jason Steffen's (2008): windows of every other row from the back, one side then the other, then the other
//            rows; then middles, then aisles — people stowing two rows apart do not block each other
// Steffen's experiment (2011, 72 passengers in a mock-up of 12 rows): blocks ≈ 7 min, Steffen ≈ 3.5 min.
import {mulberry} from './world';

export const BOARD = {walk: 0.65, door: 1.4, stowMin: 4, stowMax: 13, search: 1.6, shuffle: 4, dt: 0.25, binCap: 2.6};
export type Pax = {row: number; seat: number; bag: boolean; group: number};
export type BoardFrame = {pos: Float32Array; phase: Uint8Array; blocked: Uint8Array; bins: Uint8Array; heat: Float32Array};   // phase: 0 outside, 1 aisle, 2 stowing, 3 seating, 4 seated
export type BoardRun = {pax: Pax[]; frames: BoardFrame[]; done: number; seatedAt: Float32Array; enteredAt: Float32Array;
  stops: Float32Array; hunt: Uint8Array; at: (t: number) => BoardFrame; rows: number; method: string};

const column = (seat: number) => (seat === 0 || seat === 5 ? 0 : seat === 1 || seat === 4 ? 1 : 2);   // window, middle, aisle

export const orderOf = (method: string, rows: number, bags: number, rnd: () => number): Pax[] => {
  const all: Pax[] = [];
  for (let row = 1; row <= rows; row++) for (let seat = 0; seat < 6; seat++) all.push({row, seat, bag: rnd() < bags, group: 0});
  const shuffle = (list: Pax[]) => list.map((p) => [rnd(), p] as const).sort((a, b) => a[0] - b[0]).map(([, p]) => p);
  const tag = (list: Pax[], g: number) => list.map((p) => ({...p, group: g}));
  if (method === 'bloques') {
    const third = Math.ceil(rows / 3);
    return [0, 1, 2].flatMap((g) => tag(shuffle(all.filter((p) => p.row > rows - third * (g + 1) && p.row <= rows - third * g)), g));
  }
  if (method === 'vcp') return [0, 1, 2].flatMap((c) => tag(shuffle(all.filter((p) => column(p.seat) === c)), c));
  if (method === 'steffen') {
    const out: Pax[] = [];
    for (const c of [0, 1, 2]) for (const parity of [rows % 2, 1 - (rows % 2)]) for (const side of [0, 1]) {
      out.push(...tag(all.filter((p) => column(p.seat) === c && p.row % 2 === parity && (p.seat < 3 ? 0 : 1) === side).sort((a, b) => b.row - a.row), c));
    }
    return out;
  }
  return tag(shuffle(all), 0);
};

const RUNS = new Map<string, BoardRun>();

export const runBoarding = (method: string, rows = 30, bags = 0.85, seed = 11, keep = true): BoardRun => {
  const id = `${method}:${rows}:${bags}:${seed}:${keep}`;
  if (RUNS.has(id)) return RUNS.get(id)!;
  const rnd = mulberry(seed);
  const pax = orderOf(method, rows, bags, rnd);
  const n = pax.length;
  const pos = new Float32Array(n).fill(-1);            // aisle cell (0 = the door, row r at cell r)
  const phase = new Uint8Array(n);
  const busy = new Float32Array(n);                    // seconds left of what they are doing
  const blocked = new Uint8Array(n);
  const seatedAt = new Float32Array(n).fill(-1);
  const enteredAt = new Float32Array(n).fill(-1);
  const stops = new Float32Array(rows + 1);            // seconds someone stood stowing at each row
  const huntOf = new Uint8Array(n);                    // rows they went through looking for room in the bins
  const heat = new Float32Array(rows + 1);             // seconds of stowing so far at each row
  const bins = new Uint8Array((rows + 1) * 2);         // bags in the bin of each row and side
  const seated = new Uint8Array((rows + 1) * 6);
  const cell = new Int32Array(rows + 2).fill(-1);      // who stands at each aisle cell
  const frames: BoardFrame[] = [];
  let next = 0;
  let lastEntry = -99;
  let done = 0;
  const dt = BOARD.dt;
  for (let t = 0; t < 7200; t += dt) {
    // at the door: the next one steps in when the first cell is free
    if (next < n && cell[0] < 0 && t - lastEntry >= BOARD.door) {
      pos[next] = 0;
      phase[next] = 1;
      busy[next] = BOARD.walk;
      cell[0] = next;
      enteredAt[next] = t;
      lastEntry = t;
      next++;
    }
    // the ones further in first, so a free cell moves back along the line in one step
    const order = Array.from({length: n}, (_, i) => i).filter((i) => phase[i] >= 1 && phase[i] <= 3).sort((a, b) => pos[b] - pos[a]);
    for (const i of order) {
      const p = pax[i];
      blocked[i] = 0;
      busy[i] -= dt;
      if (phase[i] === 1) {
        if (pos[i] >= p.row) {
          // at the row: stow the bag (hunting for room if the bin is full), then sit
          let stow = 0;
          if (p.bag) {
            const side = p.seat < 3 ? 0 : 1;
            let r = p.row;
            let hunt = 0;
            while (bins[r * 2 + side] >= BOARD.binCap && hunt < rows) {
              hunt++;
              r = p.row + (hunt % 2 ? Math.ceil(hunt / 2) : -Math.ceil(hunt / 2));
              if (r < 1 || r > rows) continue;
            }
            if (r >= 1 && r <= rows) bins[r * 2 + side]++;
            stow = BOARD.stowMin + rnd() * (BOARD.stowMax - BOARD.stowMin) + hunt * BOARD.search;
            huntOf[i] = Math.min(255, hunt);
          }
          phase[i] = 2;
          busy[i] = stow;
          stops[p.row] += stow;
        } else if (busy[i] <= 0) {
          const ahead = Math.floor(pos[i]) + 1;
          if (cell[ahead] < 0) {
            cell[Math.floor(pos[i])] = -1;
            pos[i] = ahead;
            cell[ahead] = i;
            busy[i] = BOARD.walk;
          } else {
            blocked[i] = 1;
          }
        }
      } else if (phase[i] === 2 && busy[i] <= 0) {
        // the people already sitting between the aisle and the seat stand up and let them in
        const base = p.row * 6;
        const between = p.seat < 3 ? [p.seat + 1, 2].filter((s, k, a) => s <= 2 && a.indexOf(s) === k) : [3, p.seat - 1].filter((s, k, a) => s >= 3 && a.indexOf(s) === k);
        const inWay = between.filter((s) => s !== p.seat && seated[base + s]).length;
        phase[i] = 3;
        busy[i] = inWay * BOARD.shuffle + 1;
      } else if (phase[i] === 3 && busy[i] <= 0) {
        phase[i] = 4;
        seated[p.row * 6 + p.seat] = 1;
        seatedAt[i] = t;
        cell[Math.floor(pos[i])] = -1;
      }
    }
    for (let i = 0; i < n; i++) if (phase[i] === 2) heat[pax[i].row] += dt;
    if (keep) {
      frames.push({pos: Float32Array.from(pos), phase: Uint8Array.from(phase), blocked: Uint8Array.from(blocked), bins: Uint8Array.from(bins),
                   heat: Float32Array.from(heat)});
    }
    if (next >= n && phase.every((ph) => ph === 4)) {
      done = t;
      break;
    }
  }
  const at = (t: number) => frames[Math.max(0, Math.min(frames.length - 1, Math.round(t / dt)))];
  const run = {pax, frames, done, seatedAt, enteredAt, stops, hunt: huntOf, at, rows, method};
  if (keep) RUNS.set(id, run);
  return run;
};

/** The mean over a few draws (other people, other bags): the figures the panels give. */
const MEANS = new Map<string, number>();
export const meanTime = (method: string, rows = 30, bags = 0.85) => {
  const id = `${method}:${rows}:${bags}`;
  if (!MEANS.has(id)) {
    const seeds = [11, 12, 13, 14, 15];
    MEANS.set(id, seeds.reduce((s, seed) => s + runBoarding(method, rows, bags, seed, false).done, 0) / seeds.length);
  }
  return MEANS.get(id)!;
};
