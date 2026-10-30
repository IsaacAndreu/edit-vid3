// Cars on a ring road with the Intelligent Driver Model (Treiber et al.): each driver speeds up towards v0 and keeps
// a safe gap to the car ahead; nobody does anything wrong, yet one short brake grows into a jam that travels
// backwards. The setting of Sugiyama et al. (2008): 22 cars on a 230 m circle. Simulated once, deterministically
// (seeded noise), and sampled every SAMPLE seconds for the frames.

export const RING = {cars: 22, length: 230, carLength: 4.5};
const P = {v0: 16, T: 0.7, a: 0.2, b: 1.5, s0: 1.0, noise: 0.08};
export const PERTURB = {car: 0, from: 6, to: 7.5, decel: -1.5};     // one driver brakes a little
const DT = 0.05;
export const SAMPLE = 0.1;
export const SPAN = 130;

const mulberry = (seed: number) => () => {
  seed |= 0;
  seed = (seed + 0x6d2b79f5) | 0;
  let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
  t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
};

const gauss = (rnd: () => number) => Math.sqrt(-2 * Math.log(rnd() + 1e-12)) * Math.cos(2 * Math.PI * rnd());

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

const simulate = (): Frame[] => {
  const {cars: n, length: L, carLength} = RING;
  const rnd = mulberry(7);
  const x = Array.from({length: n}, (_, i) => (i * L) / n);
  const v = Array(n).fill(equilibrium(L / n - carLength));
  const acc = Array(n).fill(0);
  const frames: Frame[] = [];
  const every = Math.round(SAMPLE / DT);
  for (let step = 0; step * DT <= SPAN; step++) {
    const t = step * DT;
    for (let i = 0; i < n; i++) {
      const j = (i + 1) % n;
      const gap = ((x[j] - x[i] + L) % L) - carLength;
      const dv = v[i] - v[j];
      const want = P.s0 + Math.max(0, v[i] * P.T + (v[i] * dv) / (2 * Math.sqrt(P.a * P.b)));
      acc[i] = P.a * (1 - (v[i] / P.v0) ** 4 - (want / Math.max(gap, 0.1)) ** 2) + P.noise * gauss(rnd);
      if (i === PERTURB.car && t >= PERTURB.from && t < PERTURB.to) acc[i] = PERTURB.decel;
    }
    if (step % every === 0) frames.push({x: Float32Array.from(x), v: Float32Array.from(v), a: Float32Array.from(acc)});
    for (let i = 0; i < n; i++) {
      v[i] = Math.max(0, v[i] + acc[i] * DT);
      x[i] = (x[i] + v[i] * DT) % L;
    }
  }
  return frames;
};

export const FRAMES = simulate();

export const at = (t: number): Frame => FRAMES[Math.max(0, Math.min(FRAMES.length - 1, Math.round(t / SAMPLE)))];

export const stopped = (t: number) => Array.from(at(t).v).filter((v) => v < 0.6).length;
export const meanSpeed = (t: number) => Array.from(at(t).v).reduce((s, v) => s + v, 0) / RING.cars;
export const startSpeed = () => FRAMES[0].v[0];
