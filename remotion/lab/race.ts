// A 100 m race rebuilt from the official result: each athlete's distance over time from a sprint model
// v(t) = V·(1 − e^(−t'/τ))·(1 − k·max(0, t' − 4.5)²), t' = t − reaction, V solved so that d(final) = 100 m.
// τ and k were fitted so that the order at 10, 50 and 80 m matches the race report; Ta Lou-Smith pulls up at 40 m.

export type Athlete = {
  name: string;
  short: string;
  country: string;
  lane: number;
  time: number;          // official, seconds
  reaction: number;      // seconds (only Alfred's and Richardson's are published)
  reactionKnown: boolean;
  tau: number;
  k: number;
  color: string;
  injuredAt?: number;    // metres
  note?: string;
};

export const RACE = {
  title: 'Final de 100 m femenino',
  place: 'París 2024 · Stade de France',
  date: '3 de agosto de 2024 · bajo la lluvia',
};

export const ATHLETES: Athlete[] = [
  {name: 'Mujinga Kambundji', short: 'KAMBUNDJI', country: 'SUI', lane: 2, time: 10.99, reaction: 0.16, reactionKnown: false, tau: 0.946, k: 0.01, color: '#e5484d'},
  {name: 'Marie-Josée Ta Lou-Smith', short: 'TA LOU-SMITH', country: 'CIV', lane: 3, time: 13.84, reaction: 0.16, reactionKnown: false, tau: 1.0, k: 0.01, color: '#f5a623', injuredAt: 40},
  {name: 'Tia Clayton', short: 'CLAYTON', country: 'JAM', lane: 4, time: 11.04, reaction: 0.16, reactionKnown: false, tau: 1.058, k: 0.008, color: '#30a46c'},
  {name: 'Melissa Jefferson', short: 'JEFFERSON', country: 'USA', lane: 5, time: 10.92, reaction: 0.16, reactionKnown: false, tau: 1.025, k: 0.01, color: '#5b8def'},
  {name: 'Julien Alfred', short: 'ALFRED', country: 'LCA', lane: 6, time: 10.72, reaction: 0.144, reactionKnown: true, tau: 0.968, k: 0.009, color: '#ffd23f', note: 'NR'},
  {name: "Sha'Carri Richardson", short: 'RICHARDSON', country: 'USA', lane: 7, time: 10.87, reaction: 0.221, reactionKnown: true, tau: 1.013, k: 0.01, color: '#ff7ac6'},
  {name: 'Daryll Neita', short: 'NEITA', country: 'GBR', lane: 8, time: 10.96, reaction: 0.16, reactionKnown: false, tau: 0.979, k: 0.01, color: '#8e7cf8'},
  {name: 'Twanisha Terry', short: 'TERRY', country: 'USA', lane: 9, time: 10.97, reaction: 0.16, reactionKnown: false, tau: 0.883, k: 0.006, color: '#3dd6d0'},
];

const DT = 0.002;
const SPAN = 14.5;

const shape = (a: Athlete, t: number) => {
  const tp = t - a.reaction;
  if (tp <= 0) return 0;
  return (1 - Math.exp(-tp / a.tau)) * Math.max(0.2, 1 - a.k * Math.max(0, tp - 4.5) ** 2);
};

const integrate = (a: Athlete, v: (t: number) => number) => {
  const xs: number[] = [];
  let x = 0;
  for (let i = 0; i * DT <= SPAN; i++) {
    x += v(i * DT) * DT;
    xs.push(x);
  }
  return xs;
};

const build = (a: Athlete): number[] => {
  const unit = integrate(a, (t) => shape(a, t));
  if (!a.injuredAt) {
    const scale = 100 / unit[Math.round(a.time / DT)];
    return unit.map((x) => x * scale);
  }
  // as a healthy finalist up to the injury, then slowing down to a jog that reaches the line at her official time
  const healthy = unit.map((x) => (x * 100) / unit[Math.round(10.9 / DT)]);
  const hurt = healthy.findIndex((x) => x >= a.injuredAt!);
  const v0 = (healthy[hurt + 1] - healthy[hurt]) / DT;
  const run = (slow: number) => {
    const xs = healthy.slice(0, hurt + 1);
    let x = xs[hurt];
    for (let i = hurt + 1; i * DT <= SPAN; i++) {
      x += (slow + (v0 - slow) * Math.exp(-((i - hurt) * DT) / 0.7)) * DT;
      xs.push(x);
    }
    return xs;
  };
  let lo = 0.5;
  let hi = v0;
  for (let n = 0; n < 40; n++) {
    const mid = (lo + hi) / 2;
    if (run(mid)[Math.round(a.time / DT)] > 100) hi = mid;
    else lo = mid;
  }
  return run(lo);
};

const CURVES = new Map(ATHLETES.map((a) => [a.name, build(a)]));

export const distance = (a: Athlete, t: number): number => {
  const xs = CURVES.get(a.name)!;
  if (t <= 0) return 0;
  const i = Math.min(xs.length - 1, Math.floor(t / DT));
  return Math.min(a.injuredAt ? 100 : 100.6, xs[i]);
};

export const speed = (a: Athlete, t: number): number => {
  const h = 0.05;
  return (distance(a, t + h) - distance(a, Math.max(0, t - h))) / (t > h ? 2 * h : t + h);
};

export const timeAt = (a: Athlete, metres: number): number => {
  const xs = CURVES.get(a.name)!;
  const i = xs.findIndex((x) => x >= metres);
  return i < 0 ? Infinity : i * DT;
};

export const peakSpeed = (a: Athlete): number => {
  let best = 0;
  for (let t = 0; t < a.time; t += 0.05) best = Math.max(best, speed(a, t));
  return best;
};

export const order = (t: number): Athlete[] => [...ATHLETES].sort((a, b) => distance(b, t) - distance(a, t));
