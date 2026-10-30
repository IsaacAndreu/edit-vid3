// Two junctions fed with exactly the same cars: a four-way crossing with traffic lights and a single-lane roundabout.
// Every car follows a path (approach → crossing or ring → exit) with the Intelligent Driver Model; at the lights it
// stops on red, at the roundabout it gives way to the cars already on the ring. Right-hand traffic, metres, y down.
// Simulated once at load and sampled 30 times a second.

export type Kind = 'lights' | 'roundabout';
export type Arm = 'W' | 'S' | 'E' | 'N';
export type Car = {id: number; x: number; y: number; h: number; v: number; a: number; waiting: boolean};
export type Snapshot = {cars: Car[]; done: number; waited: number; finished: number; green: 'EW' | 'NS' | null; amber: boolean};

export const APPROACH = 120;
export const LANE = 2.2;
export const RING_R = 13;
export const STOP = 7;                       // stop line: metres before the centre
export const FPS = 30;
const DT = 1 / FPS / 2;
const CAR = 4.4;
const IDM = {T: 1.2, a: 1.6, b: 2.6, s0: 2.0};
const V_ROAD = 13;
const V_TURN = 7;
const ARMS: Arm[] = ['W', 'S', 'E', 'N'];
// the arm's direction from the centre, and the ring angle where it meets the circle (y down: the ring turns with θ decreasing)
const ARM_ANGLE: Record<Arm, number> = {W: Math.PI, S: Math.PI / 2, E: 0, N: -Math.PI / 2};
const OUT_OF: Record<Arm, [number, number]> = {W: [-1, 0], S: [0, 1], E: [1, 0], N: [0, -1]};

type Piece = {kind: 'line'; x0: number; y0: number; x1: number; y1: number; len: number; key: string; v0: number}
  | {kind: 'arc'; th0: number; th1: number; len: number; key: string; v0: number};

const line = (x0: number, y0: number, x1: number, y1: number, key: string, v0 = V_ROAD): Piece =>
  ({kind: 'line', x0, y0, x1, y1, len: Math.hypot(x1 - x0, y1 - y0), key, v0});

// a point on the inbound / outbound lane of an arm, `d` metres from the centre (right-hand traffic)
const inbound = (arm: Arm, d: number): [number, number] => {
  const [ox, oy] = OUT_OF[arm];
  return [ox * d + oy * LANE, oy * d - ox * LANE];
};
const outbound = (arm: Arm, d: number): [number, number] => {
  const [ox, oy] = OUT_OF[arm];
  return [ox * d - oy * LANE, oy * d + ox * LANE];
};

const NEXT: Record<Arm, Arm> = {W: 'S', S: 'E', E: 'N', N: 'W'};      // first exit = turning right

const pathFor = (kind: Kind, from: Arm, exitsAhead: 1 | 2): Piece[] => {
  let to: Arm = NEXT[from];
  if (exitsAhead === 2) to = NEXT[to];
  if (kind === 'lights') {
    const [sx, sy] = inbound(from, APPROACH);
    const [px, py] = inbound(from, STOP);
    const [ex, ey] = outbound(to, STOP);
    const [fx, fy] = outbound(to, APPROACH);
    if (exitsAhead === 2) {
      return [line(sx, sy, px, py, `in:${from}`), line(px, py, ex, ey, `box:${from}`), line(ex, ey, fx, fy, `out:${to}`)];
    }
    // right turn: round the near corner (where the two lanes would meet), cut in three short pieces
    const horizontal = from === 'W' || from === 'E';
    const [qx, qy] = horizontal ? [outbound(to, 0)[0], inbound(from, 0)[1]] : [inbound(from, 0)[0], outbound(to, 0)[1]];
    const m1: [number, number] = [px + (qx - px) * 0.6, py + (qy - py) * 0.6];
    const m2: [number, number] = [qx + (ex - qx) * 0.4, qy + (ey - qy) * 0.4];
    return [line(sx, sy, px, py, `in:${from}`), line(px, py, m1[0], m1[1], `box:${from}`, V_TURN),
            line(m1[0], m1[1], m2[0], m2[1], `boxb:${from}`, V_TURN), line(m2[0], m2[1], ex, ey, `boxc:${from}`, V_TURN),
            line(ex, ey, fx, fy, `out:${to}`)];
  }
  const delta = Math.asin(LANE / RING_R);
  const th0 = ARM_ANGLE[from] - delta;                        // entry, on the inbound side
  let th1 = ARM_ANGLE[to] + delta;                            // exit, on the outbound side
  while (th1 >= th0) th1 -= 2 * Math.PI;
  const [sx, sy] = inbound(from, APPROACH);
  const ex0 = Math.cos(th0) * RING_R;
  const ey0 = Math.sin(th0) * RING_R;
  const ex1 = Math.cos(th1) * RING_R;
  const ey1 = Math.sin(th1) * RING_R;
  const [fx, fy] = outbound(to, APPROACH);
  return [line(sx, sy, ex0, ey0, `in:${from}`), {kind: 'arc', th0, th1, len: (th0 - th1) * RING_R, key: 'ring', v0: 8},
          line(ex1, ey1, fx, fy, `out:${to}`)];
};

type Agent = {id: number; path: Piece[]; total: number; s: number; v: number; a: number; born: number; waited: number; from: Arm; committed: boolean};

const locate = (path: Piece[], s: number) => {
  let rest = s;
  for (let i = 0; i < path.length; i++) {
    if (rest <= path[i].len || i === path.length - 1) return {i, local: Math.min(rest, path[i].len)};
    rest -= path[i].len;
  }
  return {i: path.length - 1, local: path[path.length - 1].len};
};

const point = (p: Piece, local: number) => {
  if (p.kind === 'line') {
    const k = p.len ? local / p.len : 0;
    return {x: p.x0 + (p.x1 - p.x0) * k, y: p.y0 + (p.y1 - p.y0) * k, h: Math.atan2(p.y1 - p.y0, p.x1 - p.x0)};
  }
  const th = p.th0 - local / RING_R;
  return {x: Math.cos(th) * RING_R, y: Math.sin(th) * RING_R, h: th - Math.PI / 2};
};

// ring position as an arc length along the direction of travel, from a fixed origin (wraps every C)
const C = 2 * Math.PI * RING_R;
const ringU = (th: number) => ((((-th * RING_R) % C) + C) % C);

const mulberry = (seed: number) => () => {
  seed |= 0;
  seed = (seed + 0x6d2b79f5) | 0;
  let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
  t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
};

// the same arrivals for both junctions: [time, arm, exits ahead]
export const DEMAND = 0.15;                  // cars per second per arm
const arrivals = (span: number): [number, Arm, 1 | 2][] => {
  const rnd = mulberry(11);
  const out: [number, Arm, 1 | 2][] = [];
  for (const arm of ARMS) {
    let t = rnd() * 3;
    while (t < span) {
      out.push([t, arm, rnd() < 0.3 ? 1 : 2]);
      t += -Math.log(1 - rnd()) / DEMAND + 1.2;
    }
  }
  return out.sort((a, b) => a[0] - b[0]);
};

const CYCLE = {green: 22, amber: 3, allRed: 2};
const signal = (t: number) => {
  const half = CYCLE.green + CYCLE.amber + CYCLE.allRed;
  const k = t % (2 * half);
  const axis = k < half ? 'EW' : 'NS';
  const p = k % half;
  if (p < CYCLE.green) return {green: axis as 'EW' | 'NS', amber: false};
  if (p < CYCLE.green + CYCLE.amber) return {green: axis as 'EW' | 'NS', amber: true};
  return {green: null, amber: false};
};
const HALF = CYCLE.green + CYCLE.amber + CYCLE.allRed;
const BOUNDS = [0, CYCLE.green, CYCLE.green + CYCLE.amber, HALF].flatMap((b) => [b, b + HALF]).filter((b, i, all) => all.indexOf(b) === i);

/** At a scene time (the simulations' clock, without the warm-up): how long ago the lights last changed, and every
 * change between two scene times (for the click, and for the light to pulse). */
export const signalAge = (t: number) => {
  const k = (((t + WARMUP) % (2 * HALF)) + 2 * HALF) % (2 * HALF);
  return k - Math.max(...BOUNDS.filter((b) => b <= k + 1e-9));
};
export const signalChanges = (from: number, to: number): number[] => {
  const out: number[] = [];
  for (let n = Math.floor((from + WARMUP) / (2 * HALF)) - 1; n * 2 * HALF - WARMUP <= to; n++) {
    for (const b of BOUNDS) {
      const at = n * 2 * HALF + b - WARMUP;
      if (at > from && at <= to && !out.includes(at)) out.push(at);
    }
  }
  return out.sort((x, y) => x - y);
};

const axisOf = (arm: Arm) => (arm === 'W' || arm === 'E' ? 'EW' : 'NS');

const idm = (v: number, v0: number, gap: number, dv: number) => {
  const want = IDM.s0 + Math.max(0, v * IDM.T + (v * dv) / (2 * Math.sqrt(IDM.a * IDM.b)));
  return IDM.a * (1 - (v / v0) ** 4 - (want / Math.max(gap, 0.1)) ** 2);
};

export const simulate = (kind: Kind, span: number): Snapshot[] => {
  const queue = arrivals(span);
  const cars: Agent[] = [];
  const out: Snapshot[] = [];
  let next = 0;
  let id = 0;
  let done = 0;
  let waitedTotal = 0;
  let finished = 0;
  const steps = Math.round(span / DT);
  for (let step = 0; step <= steps; step++) {
    const t = step * DT;
    // arrivals: a car comes in when its turn has come and the start of its lane is clear
    while (next < queue.length && queue[next][0] <= t) {
      const [, arm, ahead] = queue[next];
      const blocked = cars.some((c) => c.from === arm && c.s < 9);
      if (blocked) break;
      const path = pathFor(kind, arm, ahead);
      cars.push({id: id++, path, total: path.reduce((s, p) => s + p.len, 0), s: 0, v: 10, a: 0, born: t, waited: 0, from: arm, committed: false});
      next++;
    }
    const sig = signal(t);
    const where = cars.map((c) => locate(c.path, c.s));
    const onRing = cars.map((c, k) => {
      const p = c.path[where[k].i];
      return p.kind === 'arc' ? ringU(p.th0 - where[k].local / RING_R) : null;
    });
    for (let k = 0; k < cars.length; k++) {
      const c = cars[k];
      const {i, local} = where[k];
      const piece = c.path[i];
      let gap = Infinity;
      let dv = 0;
      const lead = (g: number, other: number) => {
        if (g < gap) {
          gap = g;
          dv = c.v - other;
        }
      };
      // the car ahead on the same stretch, or at the start of the next one
      for (let j = 0; j < cars.length; j++) {
        if (j === k) continue;
        const o = cars[j];
        const wo = where[j];
        const po = o.path[wo.i];
        if (piece.key === 'ring' && onRing[j] !== null && onRing[k] !== null) {
          const g = (((onRing[j]! - onRing[k]!) % C) + C) % C - CAR;
          if (g > -CAR + 0.5) lead(Math.max(0.1, g), o.v);
        } else if (piece.key === 'ring' && onRing[k] !== null && o.committed && po.key.startsWith('in:')) {
          // a car already entering in front of us: it counts as being on the ring at its entry
          const entry = ringU((o.path[wo.i + 1] as {th0: number}).th0) - (po.len - wo.local);
          const ahead = (((entry - onRing[k]!) % C) + C) % C;
          if (ahead < 30) lead(Math.max(0.1, ahead - CAR), o.v);
        } else if (po.key === piece.key && wo.local > local) {
          lead(wo.local - local - CAR, o.v);
        } else if (i + 1 < c.path.length && po.key === c.path[i + 1].key) {
          if (po.key === 'ring' && onRing[j] !== null) {
            const entry = ringU((c.path[i + 1] as {th0: number}).th0);
            const ahead = (((onRing[j]! - entry) % C) + C) % C;
            if (ahead < 20) lead(piece.len - local + ahead - CAR, o.v);
          } else if (po.key !== 'ring' && !po.key.startsWith('box')) {
            lead(piece.len - local + wo.local - CAR, o.v);
          }
        }
      }
      const remaining = piece.len - local;
      if (piece.key.startsWith('in:')) {
        if (kind === 'lights') {
          // red, or amber with room to stop: the stop line is the car ahead
          const mine = sig.green === axisOf(c.from);
          const canStop = remaining > (c.v * c.v) / (2 * IDM.b) + 1;
          if (!mine || (sig.amber && canStop)) lead(Math.max(0.1, remaining - 0.5), c.v);
        } else if (remaining < 25) {
          // give way: a car on the ring about to pass the entry
          const entry = ringU((c.path[i + 1] as {th0: number}).th0);
          // a car on the ring that would reach the entry within ~2.5 s (or is passing it now), or one already entering
          // from the previous arm
          const coming = onRing.some((u, j) => u !== null && ((((entry - u) % C) + C) % C < 6 + 2.5 * cars[j].v
                                                               || (((u - entry) % C) + C) % C < 4));
          if (!c.committed && coming) lead(Math.max(0.1, remaining - 4), c.v);
          else if (remaining < 9) c.committed = true;
        }
      }
      c.a = idm(c.v, piece.v0, gap, dv);
    }
    for (const c of cars) {
      c.v = Math.max(0, c.v + c.a * DT);
      c.s += c.v * DT;
      if (c.v < 1) c.waited += DT;
    }
    for (let k = cars.length - 1; k >= 0; k--) {
      if (cars[k].s >= cars[k].total) {
        done++;
        waitedTotal += cars[k].waited;
        finished++;
        cars.splice(k, 1);
      }
    }
    if (step % 2 === 0) {
      out.push({
        cars: cars.map((c) => {
          const {i, local} = locate(c.path, c.s);
          const p = point(c.path[i], local);
          return {id: c.id, x: p.x, y: p.y, h: p.h, v: c.v, a: c.a, waiting: c.v < 1 && c.path[i].key.startsWith('in:')};
        }),
        done, waited: waitedTotal, finished, green: sig.green, amber: sig.amber,
      });
    }
  }
  return out;
};

export const WARMUP = 25;                    // seconds simulated before the scene starts: queues already formed
export const SPAN = 300;                     // a world may stay on screen for minutes: then its clock stops
// simulated the first time they are needed (every documentary's render loads this module)
const SIMS: Partial<Record<Kind, Snapshot[]>> = {};
export const sim = (kind: Kind): Snapshot[] => (SIMS[kind] ??= simulate(kind, SPAN));
export const sample = (run: Snapshot[], t: number) => run[Math.max(0, Math.min(run.length - 1, Math.round((t + WARMUP) * FPS)))];
