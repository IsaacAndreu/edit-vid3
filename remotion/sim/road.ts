// Straight roads for the «carretera» world. Two models, both the Intelligent Driver Model as on the ring:
//  · platoon(): a short line of cars behind one that taps the brake; every driver reacts REACT seconds late, so each
//    brakes a little harder than the one ahead and, a few cars back, someone stops (the whole mechanism of a jam);
//  · road(): a long busy road (a big ring seen straight, so the waves have somewhere to go) with stop-and-go waves
//    travelling backwards; variants: one car that leaves a gap and rolls instead of stopping («hueco»), a stretch with
//    a lower limit before the waves («limite»), a second lane with its own waves («carril»).
// Deterministic (seeded noise) and simulated once per setting.

export const P = {v0: 16, T: 1.0, a: 0.5, b: 1.5, s0: 2.0, noise: 0.08};
export const CAR = 4.5;
const DT = 0.05;
export const SAMPLE = 0.1;

const mulberry = (seed: number) => () => {
  seed |= 0;
  seed = (seed + 0x6d2b79f5) | 0;
  let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
  t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
};
const gauss = (rnd: () => number) => Math.sqrt(-2 * Math.log(rnd() + 1e-12)) * Math.cos(2 * Math.PI * rnd());

const idm = (p: typeof P, v: number, gap: number, dv: number, v0 = p.v0) => {
  const want = p.s0 + Math.max(0, v * p.T + (v * dv) / (2 * Math.sqrt(p.a * p.b)));
  return p.a * (1 - (v / v0) ** 4 - (want / Math.max(gap, 0.1)) ** 2);
};

const equilibrium = (gap: number) => {
  let lo = 0;
  let hi = P.v0;
  for (let n = 0; n < 60; n++) {
    const m = (lo + hi) / 2;
    if (P.s0 + m * P.T > gap * Math.sqrt(Math.max(1e-9, 1 - (m / P.v0) ** 4))) hi = m;
    else lo = m;
  }
  return lo;
};

export type Frame = {x: Float32Array; v: Float32Array; a: Float32Array};

// --- the platoon -------------------------------------------------------------------------------------------------------
export const PLATOON = {cars: 8, react: 0.7, speed: 30 / 3.6, brakeFrom: 2, brakeTo: 3.2, brake: -1.6, span: 30};
const PP = {v0: 16, T: 1.0, a: 1.0, b: 1.5, s0: 2.0};

export type Platoon = {frames: Frame[]; minSpeed: number[]; hardest: number[]; at: (t: number) => Frame};
let PLAT: Platoon | null = null;
/** 8 cars at 30 km/h; the first brakes for a second; each driver sees it 0.7 s late. Car 0 is the first. */
export const platoon = (): Platoon => {
  if (PLAT) return PLAT;
  const {cars: n, react, speed, span} = PLATOON;
  const step = 0.02;
  const gap0 = PP.s0 + speed * PP.T + 0.5;
  const x = Array.from({length: n}, (_, i) => -i * (gap0 + CAR));
  const v = Array(n).fill(speed);
  const hist: {x: number[]; v: number[]}[] = [];
  const delay = Math.round(react / step);
  const minSpeed = Array(n).fill(speed);
  const hardest = Array(n).fill(0);
  const frames: Frame[] = [];
  const every = Math.round(SAMPLE / step);
  for (let s = 0; s * step <= span; s++) {
    const t = s * step;
    hist.push({x: [...x], v: [...v]});
    const past = hist[Math.max(0, hist.length - 1 - delay)];
    const acc = Array(n).fill(0);
    for (let i = 0; i < n; i++) {
      if (i === 0) {
        acc[i] = t > PLATOON.brakeFrom && t < PLATOON.brakeTo ? PLATOON.brake : (speed - v[i]) * 0.5;
        continue;
      }
      acc[i] = Math.max(-8, idm(PP as typeof P, past.v[i], past.x[i - 1] - past.x[i] - CAR, past.v[i] - past.v[i - 1]));
    }
    if (s % every === 0) frames.push({x: Float32Array.from(x), v: Float32Array.from(v), a: Float32Array.from(acc)});
    for (let i = 0; i < n; i++) {
      v[i] = Math.max(0, v[i] + acc[i] * step);
      x[i] += v[i] * step;
      if (i > 0) x[i] = Math.min(x[i], x[i - 1] - CAR - 0.5);           // never into the car ahead
      minSpeed[i] = Math.min(minSpeed[i], v[i]);
      hardest[i] = Math.max(hardest[i], -acc[i]);
    }
  }
  const at = (t: number) => frames[Math.max(0, Math.min(frames.length - 1, Math.round(t / SAMPLE)))];
  PLAT = {frames, minSpeed, hardest, at};
  return PLAT;
};

// --- the long road -----------------------------------------------------------------------------------------------------
export const ROAD = {length: 1000, cars: 70, span: 300, tapEvery: 6, tapLength: 1.2, perturb: {car: 0, from: 4, to: 5.5, decel: -1.5}};
export type Variant = 'normal' | 'hueco' | 'limite';
/** hueco: car YOU drives itself from `from` on (steady, a long gap: it rolls up to the queue instead of stopping);
 * limite: from `from` on, between `at` and `at + length` metres the limit is `v0` (the gantries). */
export const VARIANT = {
  you: 45, hueco: {from: 100, share: 0.45, room: 3, gain: 0.3, push: 0.25, brake: 0.8},
  limite: {from: 30, at: 300, length: 350, v0: 7},
};

export type Road = {frames: Frame[]; at: (t: number) => Frame; L: number; cars: number; stopped: (t: number) => number;
  meanSpeed: (t: number) => number};
const ROADS = new Map<string, Road>();
/** For tuning: forget the simulated roads. */
export const _clear = () => ROADS.clear();

export const road = (variant: Variant = 'normal', seed = 7, cars = ROAD.cars): Road => {
  const key = `${variant}:${seed}:${cars}`;
  if (ROADS.has(key)) return ROADS.get(key)!;
  const L = ROAD.length;
  const n = cars;
  const rnd = mulberry(seed);
  const avg = L / n - CAR;
  const even = equilibrium(avg);
  const x = Array.from({length: n}, (_, i) => ((n - i) * L) / n % L);     // car 0 at the front, the rest behind
  const v = Array(n).fill(even);
  const acc = Array(n).fill(0);
  const frames: Frame[] = [];
  const every = Math.round(SAMPLE / DT);
  const per = ROAD.perturb;
  const taps = new Map<number, number>();                           // car → until when it brakes
  const tapRnd = mulberry(seed * 31 + 5);
  for (let step = 0; step * DT <= ROAD.span; step++) {
    const t = step * DT;
    // a real road is never left alone: every few seconds some driver taps the brake for a second
    if (ROAD.tapEvery > 0 && step % Math.round(ROAD.tapEvery / DT) === 0 && t > per.to) {
      taps.set(Math.floor(tapRnd() * n), t + ROAD.tapLength);
    }
    for (let i = 0; i < n; i++) {
      const j = (i - 1 + n) % n;                                       // the car ahead
      const gap = ((x[j] - x[i] + L) % L) - CAR;
      const dv = v[i] - v[j];
      const noise = P.noise * gauss(rnd);
      if (variant === 'hueco' && i === VARIANT.you && t >= VARIANT.hueco.from) {
        const h = VARIANT.hueco;
        const cmd = even * h.share * Math.max(0, Math.min(1, (gap - 1) / (avg * h.room - 1)));
        acc[i] = Math.min(idm({...P, T: 0.9}, v[i], gap, dv), Math.max(-h.brake, Math.min(h.push, h.gain * (cmd - v[i]))));
        continue;
      }
      let v0 = P.v0;
      if (variant === 'limite' && t >= VARIANT.limite.from) {
        const d = (x[i] - VARIANT.limite.at + L) % L;
        if (d < VARIANT.limite.length) v0 = VARIANT.limite.v0;
      }
      acc[i] = idm(P, v[i], gap, dv, v0) + noise;
      if (i === per.car && t >= per.from && t < per.to) acc[i] = per.decel;
      if (taps.has(i) && t < taps.get(i)!) acc[i] = Math.min(acc[i], per.decel);    // a tap: a lane change, a merge…
    }
    if (step % every === 0) frames.push({x: Float32Array.from(x), v: Float32Array.from(v), a: Float32Array.from(acc)});
    for (let i = 0; i < n; i++) {
      v[i] = Math.max(0, v[i] + acc[i] * DT);
      x[i] = (x[i] + v[i] * DT) % L;
    }
  }
  const at = (t: number) => frames[Math.max(0, Math.min(frames.length - 1, Math.round(t / SAMPLE)))];
  const out: Road = {
    frames, at, L, cars: n,
    stopped: (t) => Array.from(at(t).v).filter((s) => s < 0.6).length,
    meanSpeed: (t) => Array.from(at(t).v).reduce((a, b) => a + b, 0) / n,
  };
  ROADS.set(key, out);
  return out;
};

/** The lane next door (Redelmeier and Tibshirani, 1999): two lanes with the same traffic, each with its own waves.
 * Over the run, while YOUR car (lane 0, car `you`) is faster it overtakes the other lane's cars quickly (they are
 * bunched, slow); while it is slower, the cars that overtake it are spread out (fast), so they take longer to go by.
 * Returns the seconds it took, on average, to pass 4 cars and to be passed by 4. */
export const laneTimes = (until: number, you = VARIANT.you, from = 20) => {
  const a = road('normal', 7);
  const b = road('normal', 19);
  const L = a.L;
  let passingTime = 0;
  let passedTime = 0;
  let passes = 0;
  let passedBy = 0;
  let before: number[] | null = null;
  for (let t = from; t <= until; t += SAMPLE) {
    const fa = a.at(t);
    const fb = b.at(t);
    const rel = Array.from(fb.x, (xb) => ((xb - fa.x[you] + L * 1.5) % L) - L / 2);   // + ahead of you
    if (before) {
      for (let k = 0; k < rel.length; k++) {
        if (Math.abs(rel[k] - before[k]) > L / 4) continue;                          // the wrap at ±L/2, not a pass
        if (before[k] > 0 && rel[k] <= 0) passes++;
        if (before[k] < 0 && rel[k] >= 0) passedBy++;
      }
    }
    before = rel;
    // the other lane beside you: the mean speed of its cars within 25 m
    const near = rel.map((d, k) => [Math.abs(d), fb.v[k]] as const).filter(([d]) => d < 25);
    const vb = near.length ? near.reduce((s, [, v]) => s + v, 0) / near.length : fa.v[you];
    if (fa.v[you] > vb + 0.5) passingTime += SAMPLE;
    else if (vb > fa.v[you] + 0.5) passedTime += SAMPLE;
  }
  return {passingTime, passedTime, passes, passedBy,
    passFour: passes ? (4 * passingTime) / passes : 0, passedFour: passedBy ? (4 * passedTime) / passedBy : 0};
};

/** The most cars an hour one lane carries, with every gap even (the top of the flow curve of this model). */
export const capacity = () => {
  let best = 0;
  for (let gap = 2; gap < 120; gap += 0.5) best = Math.max(best, (equilibrium(gap) * 3600) / (gap + CAR));
  return best;
};

/** The biggest knot of stopped cars on a periodic road: where it is (its front and tail, metres), or null. */
export const jamOf = (f: Frame, L: number) => {
  const stopped = Array.from(f.x).filter((_, i) => f.v[i] < 1).sort((a, b) => a - b);
  if (!stopped.length) return null;
  // runs of stopped cars no more than 15 m apart (around the wrap too)
  const runs: number[][] = [];
  for (const x of stopped) {
    const last = runs[runs.length - 1];
    if (last && x - last[last.length - 1] < 15) last.push(x);
    else runs.push([x]);
  }
  if (runs.length > 1 && stopped[0] + L - stopped[stopped.length - 1] < 15) {
    runs[0] = [...runs.pop()!.map((x) => x - L), ...runs[0]];
  }
  const big = runs.reduce((a, b) => (b.length > a.length ? b : a));
  return {tail: big[0], front: big[big.length - 1], cars: big.length};
};
