// People in a space (the social force model, Helbing et al., 2000): each one walks towards its goal at its own
// speed, keeps a little distance from the others and from the walls, and when bodies touch they push and rub. Nothing
// else: arches at a door, clogging when everyone hurries, lanes in a corridor come out of these rules by themselves.
// Deterministic (seeded), simulated once per setting, sampled every SAMPLE seconds.
import {mulberry} from './world';

export const SAMPLE = 0.1;
const DT = 0.02;
const P = {tau: 0.5, A: 2000, B: 0.08, k: 1.2e5, kappa: 2.4e5, mass: 80};

export type Wall = [number, number, number, number];          // a segment x1, y1, x2, y2 (metres)
export type Space = {w: number; h: number; walls: Wall[]; goals: (x: number, y: number, i: number) => [number, number]; done: (x: number, y: number) => boolean;
  pillars?: [number, number, number][];                        // x, y, radius
  wrap?: number};                                               // a loop in x of this length (a corridor)
export type CrowdFrame = {x: Float32Array; y: Float32Array; push: Float32Array; out: Uint8Array};
export type Crowd = {frames: CrowdFrame[]; at: (t: number) => CrowdFrame; n: number; outAt: number[]; space: Space; group: Uint8Array};

const closest = (px: number, py: number, [x1, y1, x2, y2]: Wall): [number, number] => {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const k = Math.max(0, Math.min(1, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy || 1)));
  return [x1 + k * dx, y1 + k * dy];
};

const RUNS = new Map<string, Crowd>();

export const simulate = (key: string, space: Space, people: {x: number; y: number; v0: number; r: number; group?: number}[], span: number): Crowd => {
  if (RUNS.has(key)) return RUNS.get(key)!;
  const n = people.length;
  const x = Float64Array.from(people.map((p) => p.x));
  const y = Float64Array.from(people.map((p) => p.y));
  const vx = new Float64Array(n);
  const vy = new Float64Array(n);
  const r = Float64Array.from(people.map((p) => p.r));
  const v0 = Float64Array.from(people.map((p) => p.v0));
  const out = new Uint8Array(n);
  const push = new Float32Array(n);
  const outAt = Array(n).fill(Infinity);
  const frames: CrowdFrame[] = [];
  const every = Math.round(SAMPLE / DT);
  const cell = 1.2;
  for (let step = 0; step * DT <= span; step++) {
    // neighbours through a grid
    const grid = new Map<number, number[]>();
    for (let i = 0; i < n; i++) {
      if (out[i]) continue;
      const k = Math.floor(x[i] / cell) * 4096 + Math.floor(y[i] / cell);
      (grid.get(k) ?? grid.set(k, []).get(k)!).push(i);
    }
    const fx = new Float64Array(n);
    const fy = new Float64Array(n);
    push.fill(0);
    for (let i = 0; i < n; i++) {
      if (out[i]) continue;
      const [gx, gy] = space.goals(x[i], y[i], i);
      const dx = gx - x[i];
      const dy = gy - y[i];
      const d = Math.hypot(dx, dy) || 1;
      fx[i] += (P.mass * (v0[i] * dx / d - vx[i])) / P.tau;
      fy[i] += (P.mass * (v0[i] * dy / d - vy[i])) / P.tau;
      const ci = Math.floor(x[i] / cell);
      const cj = Math.floor(y[i] / cell);
      for (let a = -1; a <= 1; a++) for (let b = -1; b <= 1; b++) {
        for (const j of grid.get((ci + a) * 4096 + cj + b) ?? []) {
          if (j <= i) continue;
          const ex = x[i] - x[j];
          const ey = y[i] - y[j];
          const dist = Math.hypot(ex, ey) || 1e-6;
          const rij = r[i] + r[j];
          if (dist > rij + 1.2) continue;
          const nx = ex / dist;
          const ny = ey / dist;
          let f = P.A * Math.exp((rij - dist) / P.B);
          let tx = 0;
          let ty = 0;
          if (dist < rij) {                                    // bodies touching: pushing and rubbing
            f += P.k * (rij - dist);
            const dvt = (vx[j] - vx[i]) * -ny + (vy[j] - vy[i]) * nx;
            tx = P.kappa * (rij - dist) * dvt * -ny;
            ty = P.kappa * (rij - dist) * dvt * nx;
            push[i] += P.k * (rij - dist);
            push[j] += P.k * (rij - dist);
          }
          fx[i] += f * nx + tx;
          fy[i] += f * ny + ty;
          fx[j] -= f * nx + tx;
          fy[j] -= f * ny + ty;
        }
      }
      const obstacles: Wall[] = space.walls;
      for (const wall of obstacles) {
        const [qx, qy] = closest(x[i], y[i], wall);
        const ex = x[i] - qx;
        const ey = y[i] - qy;
        const dist = Math.hypot(ex, ey) || 1e-6;
        if (dist > r[i] + 1) continue;
        const nx = ex / dist;
        const ny = ey / dist;
        let f = P.A * Math.exp((r[i] - dist) / P.B);
        if (dist < r[i]) {
          f += P.k * (r[i] - dist);
          push[i] += P.k * (r[i] - dist);
          const vt = vx[i] * -ny + vy[i] * nx;
          fx[i] -= P.kappa * (r[i] - dist) * vt * -ny;
          fy[i] -= P.kappa * (r[i] - dist) * vt * nx;
        }
        fx[i] += f * nx;
        fy[i] += f * ny;
      }
      for (const [px, py, pr] of space.pillars ?? []) {
        const ex = x[i] - px;
        const ey = y[i] - py;
        const dist = Math.hypot(ex, ey) || 1e-6;
        const gap = dist - pr;
        if (gap > r[i] + 1) continue;
        let f = P.A * Math.exp((r[i] - gap) / P.B);
        if (gap < r[i]) f += P.k * (r[i] - gap);
        fx[i] += (f * ex) / dist;
        fy[i] += (f * ey) / dist;
      }
    }
    for (let i = 0; i < n; i++) {
      if (out[i]) continue;
      vx[i] += (fx[i] / P.mass) * DT;
      vy[i] += (fy[i] / P.mass) * DT;
      const sp = Math.hypot(vx[i], vy[i]);
      const top = v0[i] * 1.3;
      if (sp > top) {
        vx[i] *= top / sp;
        vy[i] *= top / sp;
      }
      x[i] += vx[i] * DT;
      y[i] += vy[i] * DT;
      if (space.wrap) x[i] = ((x[i] % space.wrap) + space.wrap) % space.wrap;
      if (space.done(x[i], y[i])) {
        out[i] = 1;
        outAt[i] = step * DT;
      }
    }
    if (step % every === 0) {
      frames.push({x: Float32Array.from(x), y: Float32Array.from(y), push: Float32Array.from(push), out: Uint8Array.from(out)});
    }
  }
  const at = (t: number) => frames[Math.max(0, Math.min(frames.length - 1, Math.round(t / SAMPLE)))];
  const crowd = {frames, at, n, outAt, space, group: Uint8Array.from(people.map((p) => p.group ?? 0))};
  RUNS.set(key, crowd);
  return crowd;
};

// --- the spaces ----------------------------------------------------------------------------------------------------------
export const ROOM = {w: 18, h: 13, door: 1.2};

/** A room with one door in the middle of its right wall; `pillar`: a column a little before the door. */
export const room = (pillar: boolean): Space => {
  const {w, h, door} = ROOM;
  const top = h / 2 - door / 2;
  const bottom = h / 2 + door / 2;
  return {
    w: w + 4, h,
    walls: [[0, 0, w, 0], [0, h, w, h], [0, 0, 0, h], [w, 0, w, top], [w, bottom, w, h]],
    pillars: pillar ? [[w - 1.1, h / 2, 0.35]] : [],
    goals: (px, py) => (px < w - 0.2 ? [w + 0.6, Math.max(top + 0.3, Math.min(bottom - 0.3, py))] : [w + 5, h / 2]),
    done: (px) => px > w + 2.5,
  };
};

/** The people of a room: `n` spread over it, `v0` desired speed (hurry: ~3 m/s; calm: ~1.2 m/s). */
export const roomPeople = (n: number, v0: number, seed = 3) => {
  const rnd = mulberry(seed);
  const out: {x: number; y: number; v0: number; r: number}[] = [];
  for (let tries = 0; out.length < n && tries < 20000; tries++) {
    const x = 0.6 + rnd() * (ROOM.w - 3);
    const y = 0.6 + rnd() * (ROOM.h - 1.2);
    if (out.every((p) => Math.hypot(p.x - x, p.y - y) > 0.62)) out.push({x, y, v0: v0 * (0.9 + rnd() * 0.2), r: 0.25 + rnd() * 0.05});
  }
  return out;
};

export const CORRIDOR = {w: 40, h: 5};
/** A corridor walked both ways (periodic in x): group 0 goes right, group 1 left. */
export const corridor = (): Space => ({
  w: CORRIDOR.w, h: CORRIDOR.h,
  walls: [[-5, 0, CORRIDOR.w + 5, 0], [-5, CORRIDOR.h, CORRIDOR.w + 5, CORRIDOR.h]],
  goals: (px, py, i) => (i % 2 === 0 ? [px + 5, py] : [px - 5, py]),
  done: () => false,
  wrap: CORRIDOR.w,
});

export const corridorPeople = (n: number, seed = 9) => {
  const rnd = mulberry(seed);
  const out: {x: number; y: number; v0: number; r: number; group: number}[] = [];
  for (let tries = 0; out.length < n && tries < 20000; tries++) {
    const x = rnd() * CORRIDOR.w;
    const y = 0.4 + rnd() * (CORRIDOR.h - 0.8);
    if (out.every((p) => Math.hypot(p.x - x, p.y - y) > 0.6)) out.push({x, y, v0: 1.3 * (0.85 + rnd() * 0.3), r: 0.24, group: out.length % 2});
  }
  return out;
};

/** How many are out by each second. */
export const outBy = (c: Crowd, t: number) => c.outAt.filter((s) => s <= t).length;
