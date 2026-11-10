// People walking a town's streets (the city.tsx grid: a street every 72 m) and passing something on when they cross:
// a virus, or a hoax that people believe and share. Susceptible → infected (passes it on) → recovered (immune, or
// no longer believes it); the vaccinated never catch it. Simulated once per set of parameters, 30 steps a second of
// video: a day is 2 seconds.
import {mulberry} from './world';

export type ContagionParams = {contagion: number; vaccinated: number; quarantine: number};
export const S = 0;
export const I = 1;
export const R = 2;
export const V = 3;

export const PEOPLE = 400;
export const STEPS_PER_DAY = 60;
export const SPAN = 100 * 30;                         // 100 s of video: 50 days
const BLOCK = 72;
const NX = 4;                                         // intersections from -4 to 4 across, -3 to 3 down
const NY = 3;
const SPEED = 1.6;                                    // metres per step
const RADIUS = 5;
const SICK_DAYS = 7;
export const ZERO = 0;                                // patient zero
export const ZERO_AT = 30;                            // falls ill a second after the town comes on screen

export type Epidemic = {
  x: Float32Array[];                                  // per step: x, y of everyone
  state: Uint8Array[];                                // per step
  home: Float32Array;                                 // where each one stays in quarantine
  counts: [number, number, number, number][];         // per step: S, I, R, V
  peak: {step: number; infected: number};
};

const build = (p: ContagionParams): Epidemic => {
  const rnd = mulberry(23);                       // the walks: the same town whatever the parameters
  const luck = mulberry(41);                      // who is vaccinated, who catches it
  const n = PEOPLE;
  const node = () => [Math.floor(rnd() * (2 * NX + 1)) - NX, Math.floor(rnd() * (2 * NY + 1)) - NY];
  // each walks from intersection to intersection: where from, where to, how far along
  const from = Array.from({length: n}, node);
  const to = from.map(([i, j]) => [i, j]);
  const along = new Float32Array(n);
  const pick = (k: number) => {
    const [i, j] = from[k];
    const options = [[i + 1, j], [i - 1, j], [i, j + 1], [i, j - 1]].filter(([a, b]) => Math.abs(a) <= NX && Math.abs(b) <= NY);
    to[k] = options[Math.floor(rnd() * options.length)];
  };
  for (let k = 0; k < n; k++) {
    pick(k);
    along[k] = rnd() * BLOCK;
  }
  // patient zero starts in the middle of town
  from[ZERO] = [0, 0];
  pick(ZERO);
  const state = new Uint8Array(n);
  for (let k = 1; k < n; k++) if (luck() < p.vaccinated) state[k] = V;
  const sickSince = new Int32Array(n).fill(-1);
  const sickFor = Array.from({length: n}, () => SICK_DAYS * STEPS_PER_DAY + Math.floor(luck() * 2 * STEPS_PER_DAY));
  const home = new Float32Array(2 * n);
  const out: Epidemic = {x: [], state: [], home, counts: [], peak: {step: 0, infected: 0}};
  const chance = p.contagion * 0.07;
  const pos = new Float32Array(2 * n);
  for (let step = 0; step < SPAN; step++) {
    if (step === ZERO_AT) {
      state[ZERO] = I;
      sickSince[ZERO] = step;
    }
    for (let k = 0; k < n; k++) {
      const stays = p.quarantine && state[k] === I && step - sickSince[k] > STEPS_PER_DAY;
      if (!stays) {
        along[k] += SPEED;
        if (along[k] >= BLOCK) {
          along[k] -= BLOCK;
          from[k] = to[k];
          pick(k);
        }
      }
      const [i0, j0] = from[k];
      const [i1, j1] = to[k];
      const f = along[k] / BLOCK;
      // on the right of the street, so that people going both ways pass each other
      const side = 1.6 * (i1 !== i0 ? Math.sign(i1 - i0) : 0);
      const sideY = 1.6 * (j1 !== j0 ? -Math.sign(j1 - j0) : 0);
      pos[2 * k] = (i0 + (i1 - i0) * f) * BLOCK + sideY;
      pos[2 * k + 1] = (j0 + (j1 - j0) * f) * BLOCK + side;
      if (!stays) {
        home[2 * k] = pos[2 * k];
        home[2 * k + 1] = pos[2 * k + 1];
      }
    }
    // passing it on: a grid of 10 m cells
    const cells = new Map<number, number[]>();
    for (let k = 0; k < n; k++) {
      const c = Math.floor(pos[2 * k] / 10 + 100) * 1000 + Math.floor(pos[2 * k + 1] / 10 + 100);
      (cells.get(c) ?? cells.set(c, []).get(c)!).push(k);
    }
    const caught: number[] = [];
    for (let k = 0; k < n; k++) {
      if (state[k] !== I) continue;
      const home = p.quarantine && step - sickSince[k] > STEPS_PER_DAY;
      const cx = Math.floor(pos[2 * k] / 10 + 100);
      const cy = Math.floor(pos[2 * k + 1] / 10 + 100);
      for (let dx = -1; dx <= 1; dx++) for (let dy = -1; dy <= 1; dy++) {
        for (const m of cells.get((cx + dx) * 1000 + cy + dy) ?? []) {
          if (state[m] !== S) continue;
          if (Math.hypot(pos[2 * k] - pos[2 * m], pos[2 * k + 1] - pos[2 * m + 1]) > RADIUS) continue;
          // patient zero spends its first days out and about: an outbreak that dies in its first hour tells nothing
          const zero = k === ZERO && step - sickSince[k] < 2 * STEPS_PER_DAY ? 3 : 1;
          if (luck() < chance * zero * (home ? 0.1 : 1)) caught.push(m);
        }
      }
      if (step - sickSince[k] > sickFor[k]) state[k] = R;
    }
    for (const m of caught) {
      if (state[m] === S) {
        state[m] = I;
        sickSince[m] = step;
      }
    }
    const counts: [number, number, number, number] = [0, 0, 0, 0];
    for (let k = 0; k < n; k++) counts[state[k]]++;
    if (counts[I] > out.peak.infected) out.peak = {step, infected: counts[I]};
    out.x.push(Float32Array.from(pos));
    out.state.push(Uint8Array.from(state));
    out.counts.push(counts);
  }
  return out;
};

const CACHE = new Map<string, Epidemic>();
export const epidemic = (p: ContagionParams): Epidemic => {
  const id = `${p.contagion}:${p.vaccinated}:${p.quarantine}`;
  if (!CACHE.has(id)) CACHE.set(id, build(p));
  return CACHE.get(id)!;
};
export const stepAt = (t: number) => Math.max(0, Math.min(SPAN - 1, Math.round(t * 30)));
