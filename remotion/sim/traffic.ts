// Cars on a ring road with the Intelligent Driver Model (Treiber et al.): each driver speeds up towards v0 and keeps
// a safe gap to the car ahead; nobody does anything wrong, yet one short brake grows into a jam that travels
// backwards. The setting of Sugiyama et al. (2008): 22 cars on a 230 m circle. Simulated once, deterministically
// (seeded noise), and sampled every SAMPLE seconds for the frames.

export const RING = {cars: 22, length: 230, carLength: 4.5};
const P = {v0: 16, T: 0.7, a: 0.2, b: 1.5, s0: 1.0, noise: 0.08};
export const PERTURB = {car: 0, from: 6, to: 7.5, decel: -1.5};     // one driver brakes a little
const DT = 0.05;
export const SAMPLE = 0.1;
export const SPAN = 360;

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

/** How the drivers behave: `normal` (every driver as people drive: a little noise, one short brake), `suave` (as
 * normal, until one car starts driving itself — Stern et al., Arizona 2018: it keeps a steady speed and leaves
 * room instead of closing it), `calma` (no distractions: no noise and no brake). */
export type Mode = 'normal' | 'suave' | 'calma';
export const SMOOTH = {lead: 15, share: 0.25, top: 0.7, hold: 100, rise: 150, room: 5, s0: 1, gain: 0.3, push: 0.25, brake: 0.8};

const simulate = (n: number, mode: Mode = 'normal', smoothAt = Infinity): Frame[] => {
  const {length: L, carLength} = RING;
  const rnd = mulberry(7);
  const x = Array.from({length: n}, (_, i) => (i * L) / n);
  const v = Array(n).fill(equilibrium(L / n - carLength));
  const acc = Array(n).fill(0);
  const frames: Frame[] = [];
  const every = Math.round(SAMPLE / DT);
  const auto = Math.floor(n / 2);                         // the car that drives itself (opposite the one that brakes)
  const avgGap = L / n - carLength;
  const even = equilibrium(avgGap);
  const noise = mode === 'calma' ? 0 : P.noise;
  for (let step = 0; step * DT <= SPAN; step++) {
    const t = step * DT;
    for (let i = 0; i < n; i++) {
      const j = (i + 1) % n;
      const gap = ((x[j] - x[i] + L) % L) - carLength;
      const dv = v[i] - v[j];
      if (mode === 'suave' && i === auto && t >= smoothAt) {
        // steady: the speed the ring would have with even gaps (a bit under), slower only as the gap ahead closes
        // (a long time headway), changing speed gently — it rolls up to the queue instead of stopping at it
        // first slow (the queue ahead drains while it holds the ones behind at a crawl, none stopped), then, once
        // the wave is gone, up to the speed of an even ring
        const share = SMOOTH.share + (SMOOTH.top - SMOOTH.share) * Math.max(0, Math.min(1, (t - smoothAt - SMOOTH.hold) / SMOOTH.rise));
        const cmd = even * share * Math.max(0, Math.min(1, (gap - SMOOTH.s0) / (avgGap * SMOOTH.room - SMOOTH.s0)));
        const want = P.s0 + Math.max(0, v[i] * 0.9 + (v[i] * dv) / (2 * Math.sqrt(P.a * P.b)));
        const safe = P.a * (1 - (v[i] / P.v0) ** 4 - (want / Math.max(gap, 0.1)) ** 2);
        acc[i] = Math.min(safe, Math.max(-SMOOTH.brake, Math.min(SMOOTH.push, SMOOTH.gain * (cmd - v[i]))));
        gauss(rnd);                                       // the same noise for everyone else as in the normal ring
        continue;
      }
      const want = P.s0 + Math.max(0, v[i] * P.T + (v[i] * dv) / (2 * Math.sqrt(P.a * P.b)));
      acc[i] = P.a * (1 - (v[i] / P.v0) ** 4 - (want / Math.max(gap, 0.1)) ** 2) + noise * gauss(rnd);
      if (mode !== 'calma' && i === PERTURB.car && t >= PERTURB.from && t < PERTURB.to) acc[i] = PERTURB.decel;
    }
    if (step % every === 0) frames.push({x: Float32Array.from(x), v: Float32Array.from(v), a: Float32Array.from(acc)});
    for (let i = 0; i < n; i++) {
      v[i] = Math.max(0, v[i] + acc[i] * DT);
      x[i] = (x[i] + v[i] * DT) % L;
    }
  }
  return frames;
};

/** Video seconds when the voice speaks of each event: the brake, the jam, the car that drives itself. */
export type Cues = {brake?: number; jam?: number; auto?: number};
/** After the car takes over, the minutes the wave takes to die out pass this many times faster than the video. */
export const AUTO_LAPSE = 8;

export type Ring = {
  cars: number;
  mode: Mode;
  smoothAt: number;                        // suave: when the car starts driving itself (Infinity otherwise)
  frames: Frame[];
  at: (t: number) => Frame;
  firstStop: number;                       // Infinity: with this few cars the jam never stops anyone
  stopped: (t: number) => number;
  meanSpeed: (t: number) => number;
  startSpeed: number;
  clock: (t: number, since: number, cues?: Cues, lapse?: number) => number;
};

const build = (cars: number, mode: Mode): Ring => {
  // the self-driving car takes over once the jam is there (as in the experiment: the waves first, then the car)
  const smoothAt = mode === 'suave' && Number.isFinite(ring(cars).firstStop) ? ring(cars).firstStop + SMOOTH.lead : Infinity;
  const frames = simulate(cars, mode, smoothAt);
  // before the start (t < 0) the cars were already going round at the same speed: the first frame, turned back
  const at = (t: number): Frame => {
    if (t >= 0) return frames[Math.min(frames.length - 1, Math.round(t / SAMPLE))];
    const first = frames[0];
    return {x: first.x.map((x) => (((x + first.v[0] * t) % RING.length) + RING.length) % RING.length), v: first.v, a: first.a.map(() => 0)};
  };
  const stop = frames.findIndex((fr) => Array.from(fr.v).some((v) => v < 0.6));
  const firstStop = stop < 0 ? Infinity : stop * SAMPLE;
  // the simulation's clock for a video time, so that the brake falls when the voice points at it (cues.brake) and
  // the first car stands still when the voice speaks of the jam (cues.jam); in between it runs faster or slower,
  // never backwards, and with no cue it runs `lapse` times faster than the video
  const clock = (t: number, since: number, cues: Cues = {}, lapse = 2.5): number => {
    const points: [number, number][] = [];
    if (cues.brake !== undefined) points.push([cues.brake + 0.6, PERTURB.from]);
    if (cues.jam !== undefined && Number.isFinite(firstStop) && (cues.brake === undefined || cues.jam > cues.brake + 1)) {
      points.push([cues.jam + 0.8, firstStop]);
    }
    // the car starts driving itself on the line that says so (suave), after the jam is there
    const auto = cues.auto !== undefined && Number.isFinite(smoothAt) && (!points.length || cues.auto > points[points.length - 1][0] + 1);
    if (auto) points.push([cues.auto! + 0.6, smoothAt]);
    if (!points.length) return (t - since) * lapse;
    const [t0, s0] = points[0];
    if (t <= t0) return s0 - (t0 - t);                                  // real time up to the first cue
    for (let i = 1; i < points.length; i++) {
      const [a, sa] = points[i - 1];
      const [b, sb] = points[i];
      if (t <= b) return sa + ((t - a) / (b - a)) * (sb - sa);
    }
    const [tl, sl] = points[points.length - 1];
    return sl + (t - tl) * (auto ? AUTO_LAPSE : points.length > 1 ? 1.5 : lapse);
  };
  return {
    cars, mode, smoothAt, frames, at, firstStop, clock, startSpeed: frames[0].v[0],
    stopped: (t) => Array.from(at(t).v).filter((v) => v < 0.6).length,
    meanSpeed: (t) => Array.from(at(t).v).reduce((sum, v) => sum + v, 0) / cars,
  };
};

/** The fundamental diagram of the ring: for 6 to 32 cars, how many cars an hour pass a point once the traffic has
 * settled (the last 150 s of 300), against how many there are per kilometre. Rises with more cars up to a peak, then
 * falls: the most a road carries is right at the edge of where it breaks. */
let CURVE: {cars: number; perKm: number; perHour: number; kmh: number}[] | null = null;
export const flowCurve = () => {
  if (CURVE) return CURVE;
  CURVE = [];
  for (let n = 6; n <= 32; n++) {
    const frames = simulate(n);
    const late = frames.filter((_, k) => k * SAMPLE >= 150 && k * SAMPLE <= 300);
    const v = late.reduce((sum, fr) => sum + fr.v.reduce((a, b) => a + b, 0) / n, 0) / late.length;
    CURVE.push({cars: n, perKm: n / (RING.length / 1000), perHour: (v * n * 3600) / RING.length, kmh: v * 3.6});
  }
  return CURVE;
};

const RINGS = new Map<string, Ring>();
/** The ring with `cars` cars and these drivers (simulated the first time it is asked for). */
export const ring = (cars: number = RING.cars, mode: Mode = 'normal'): Ring => {
  const n = Math.max(12, Math.min(30, Math.round(cars)));
  const key = `${n}:${mode}`;
  if (!RINGS.has(key)) RINGS.set(key, build(n, mode));
  return RINGS.get(key)!;
};

// the lab's scenes use the classic ring of 22 cars
const CLASSIC = ring();
export const FRAMES = CLASSIC.frames;
export const at = CLASSIC.at;
export const FIRST_STOP = CLASSIC.firstStop;
export const clock = CLASSIC.clock;
export const stopped = CLASSIC.stopped;
export const meanSpeed = CLASSIC.meanSpeed;
export const startSpeed = () => CLASSIC.startSpeed;
