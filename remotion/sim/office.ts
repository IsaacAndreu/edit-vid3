// An office week (deterministic, seeded): 36 people with their desks in an open-plan floor, a meeting room with a
// window, a coffee corner and the lifts. Monday morning one of them comes in coughing. Every minute of office time:
// - close contact: anyone within ~2 m of someone contagious may catch it;
// - the air: each room fills with what the contagious breathe out and empties as its air is renewed (the meeting room
//   slowly with its window shut, fast with it open); whoever is in the room breathes it.
// Caught on day d → contagious from the next day, coughing (symptoms) a day and a half later, over in about 5 days.
// `window`: the meeting room's window open. `home`: whoever has symptoms stays at home the next morning.
// Days: Monday to Friday of two weeks, 8:30 to 18:30 (nights and weekends skipped).
import {mulberry} from './world';

export const PEOPLE = 36;
export const ZERO = 0;
export const DAY_START = 8.5 * 3600;
export const DAY_LEN = 10 * 3600;
export const DAYS = 10;
export const STEP = 60;
const STEPS_PER_DAY = DAY_LEN / STEP;
export type OfficeParams = {window: number; home: number};

// the floor plan (screen pixels, 1 m ≈ 22 px)
export const PLAN = {
  lift: {x: 120, y: 540},
  meeting: {x: 1310, y: 90, w: 540, h: 400, door: {x: 1310, y: 400}},
  coffee: {x: 1310, y: 610, w: 540, h: 380, door: {x: 1310, y: 680}, machine: {x: 1800, y: 660}},
  open: {x: 250, y: 90, w: 1000, h: 900},
};
// desks: four islands of 3 × 3 (two facing rows), the 36 seats
export const DESKS: {x: number; y: number; face: number}[] = (() => {
  const out: {x: number; y: number; face: number}[] = [];
  const islands = [[360, 200], [760, 200], [360, 640], [760, 640]];
  for (const [ix, iy] of islands) {
    for (let r = 0; r < 2; r++) for (let c = 0; c < 4; c++) out.push({x: ix + c * 88, y: iy + r * 150, face: r ? -1 : 1});
  }
  // the last four by the windows
  for (let c = 0; c < 4; c++) out.push({x: 1180, y: 220 + c * 190, face: 0});
  return out.slice(0, PEOPLE);
})();

const MEETING_SEATS = Array.from({length: 20}, (_, k) => {
  const side = k < 10 ? -1 : 1;
  const i = k % 10;
  return {x: PLAN.meeting.x + 70 + i * 45, y: PLAN.meeting.y + 200 + side * 80};
});

export type Stop = {at: number; x: number; y: number; room: number};   // room: 0 open plan, 1 meeting, 2 coffee, 3 out
export type OfficeRun = {x: Float32Array[]; state: Uint8Array[]; air: Float32Array[]; links: {from: number; to: number; step: number}[];
  infectedAt: Int32Array; you: number; days: number; steps: number; counts: {ill: number; home: number; caught: number}[]};
export const SUS = 0, EXPOSED = 1, ILL = 2, OVER = 3, AWAY = 4;

const route = (rnd: () => number, k: number, day: number): Stop[] => {
  // a day's plan of one worker: in from the lifts, the desk, coffee once or twice, maybe a meeting, lunch, home
  const desk = DESKS[k];
  const base = day * DAY_LEN;
  const stops: Stop[] = [{at: base, ...PLAN.lift, room: 3}];
  const arrive = base + rnd() * 3600;
  stops.push({at: arrive, x: desk.x, y: desk.y, room: 0});
  const weekday = day % 5;
  const big = weekday === 1 && k < 20;                    // Tuesday 10:00-12:00: the big meeting, 20 people
  const small = !big && rnd() < 0.18;                    // or an hour's small meeting
  const coffeeAt = [base + 3600 * (1.2 + rnd() * 1.5), base + 3600 * (6 + rnd() * 2)];
  const plan: [number, number, Stop][] = [];
  if (big) plan.push([base + 1.5 * 3600, base + 3.5 * 3600, {at: 0, ...MEETING_SEATS[k], room: 1}]);
  if (small) {
    const s = base + 3600 * (2 + Math.floor(rnd() * 5));
    plan.push([s, s + 3600, {at: 0, ...MEETING_SEATS[(k * 7) % 20], room: 1}]);
  }
  for (const c of coffeeAt.slice(0, rnd() < 0.6 ? 2 : 1)) {
    const spot = {x: PLAN.coffee.x + 120 + rnd() * 330, y: PLAN.coffee.y + 90 + rnd() * 220};
    plan.push([c, c + 600, {at: 0, ...spot, room: 2}]);
  }
  const lunch = base + 3600 * (5.5 + rnd());
  if (rnd() < 0.5) plan.push([lunch, lunch + 2400, {at: 0, x: PLAN.coffee.x + 100 + rnd() * 380, y: PLAN.coffee.y + 120 + rnd() * 200, room: 2}]);
  else plan.push([lunch, lunch + 3000, {at: 0, ...PLAN.lift, room: 3}]);
  plan.sort((a, b) => a[0] - b[0]);
  let free = arrive + 300;
  for (const [s, e, spot] of plan) {
    if (s < free) continue;
    stops.push({...spot, at: s}, {at: e, x: desk.x, y: desk.y, room: 0});
    free = e + 300;
  }
  stops.push({at: base + DAY_LEN - 3600 + rnd() * 2400, ...PLAN.lift, room: 3});
  return stops;
};

export let AIR_RISK = 0.00005;
export let CLOSE_RISK = 0.0012;
export const tune = (a: number, c: number) => { AIR_RISK = a; CLOSE_RISK = c; };
const WALK = 240;                                        // a walk takes 4 minutes (so it reads on screen at any speed)

const RUNS = new Map<string, OfficeRun>();

export const runOffice = (p: OfficeParams): OfficeRun => {
  const key = `${p.window}:${p.home}`;
  if (RUNS.has(key)) return RUNS.get(key)!;
  const rnd = mulberry(91);
  const luck = mulberry(17);
  const plans: Stop[][][] = Array.from({length: DAYS}, (_, d) => Array.from({length: PEOPLE}, (_, k) => route(rnd, k, d)));
  const state = new Uint8Array(PEOPLE);
  const infectedAt = new Int32Array(PEOPLE).fill(-1);
  const symptomsAt = new Int32Array(PEOPLE).fill(-1);
  state[ZERO] = ILL;
  infectedAt[ZERO] = -STEPS_PER_DAY * 2;
  symptomsAt[ZERO] = 0;
  const air = new Float32Array(3);
  const out: OfficeRun = {x: [], state: [], air: [], links: [], infectedAt, you: -1, days: DAYS, steps: DAYS * STEPS_PER_DAY, counts: []};
  const pos = new Float32Array(2 * PEOPLE);
  const room = new Uint8Array(PEOPLE);
  for (let step = 0; step < DAYS * STEPS_PER_DAY; step++) {
    const t = step * STEP;
    const day = Math.floor(step / STEPS_PER_DAY);
    if (step % STEPS_PER_DAY === 0) {
      // the morning: who has symptoms stays at home (with `home`), illnesses move on
      for (let k = 0; k < PEOPLE; k++) {
        if (state[k] === EXPOSED && step - infectedAt[k] >= STEPS_PER_DAY) state[k] = ILL;
        if ((state[k] === ILL || state[k] === AWAY) && step - infectedAt[k] >= 5 * STEPS_PER_DAY) state[k] = OVER;
      }
    }
    for (let k = 0; k < PEOPLE; k++) {
      if (state[k] === EXPOSED && step - infectedAt[k] >= STEPS_PER_DAY) state[k] = ILL;
      if (state[k] === ILL && symptomsAt[k] < 0 && step - infectedAt[k] >= 2.5 * STEPS_PER_DAY) symptomsAt[k] = step;
      const away = p.home && symptomsAt[k] >= 0 && symptomsAt[k] < day * STEPS_PER_DAY && state[k] === ILL;
      const plan = plans[day][k];
      let i = 0;
      while (i + 1 < plan.length && plan[i + 1].at <= t) i++;
      const a = plan[i];
      const b = plan[i + 1];
      const along = b ? Math.min(1, Math.max(0, (t - a.at) / WALK)) : 1;
      const prev = i > 0 ? plan[i - 1] : a;
      const f = Math.min(1, (t - a.at) / WALK);
      const x = away ? PLAN.lift.x : prev.x + (a.x - prev.x) * Math.max(0, f);
      const y = away ? PLAN.lift.y : prev.y + (a.y - prev.y) * Math.max(0, f);
      void along;
      pos[2 * k] = x;
      pos[2 * k + 1] = y;
      room[k] = away ? 3 : f < 1 ? 0 : a.room;
    }
    // the air of each room: what the contagious breathe out, renewed at its rate (per minute)
    const renew = [0.06, p.window ? 0.3 : 0.01, 0.08];
    const volume = [8, 0.8, 1.5];
    for (let r = 0; r < 3; r++) {
      let emit = 0;
      for (let k = 0; k < PEOPLE; k++) if (room[k] === r && state[k] === ILL) emit += k === ZERO || symptomsAt[k] >= 0 ? 1.4 : 1;
      air[r] = air[r] * (1 - renew[r]) + emit / volume[r];
    }
    for (let k = 0; k < PEOPLE; k++) {
      if (state[k] !== SUS || room[k] === 3) continue;
      let risk = AIR_RISK * air[room[k]];
      let from = -1;
      for (let j = 0; j < PEOPLE; j++) {
        if (state[j] !== ILL || room[j] === 3) continue;
        const d = Math.hypot(pos[2 * j] - pos[2 * k], pos[2 * j + 1] - pos[2 * k + 1]);
        if (d < 50) {
          risk += CLOSE_RISK * (1 - d / 50);
          from = j;
        }
      }
      if (luck() < risk) {
        state[k] = EXPOSED;
        infectedAt[k] = step;
        if (from < 0) {                                  // through the air: whoever contagious shared the room longest
          for (let j = 0; j < PEOPLE; j++) if (state[j] === ILL && room[j] === room[k]) { from = j; break; }
        }
        out.links.push({from: from < 0 ? ZERO : from, to: k, step});
      }
    }
    out.x.push(Float32Array.from(pos));
    out.state.push(Uint8Array.from(state.map((s, k) => (p.home && s === ILL && symptomsAt[k] >= 0 && symptomsAt[k] < day * STEPS_PER_DAY ? AWAY : s))));
    out.air.push(Float32Array.from(air));
    let ill = 0, home = 0, caught = 0;
    for (let k = 0; k < PEOPLE; k++) {
      if (state[k] === ILL) ill++;
      if (out.state[step][k] === AWAY) home++;
      if (state[k] !== SUS) caught++;
    }
    out.counts.push({ill, home, caught});
  }
  // «you»: someone who caught it late in the first week from someone other than patient zero, sitting far from him
  const late = out.links.filter((l) => l.from !== ZERO && Math.floor(l.step / STEPS_PER_DAY) >= 2 && Math.floor(l.step / STEPS_PER_DAY) <= 4);
  late.sort((a, b) => Math.hypot(DESKS[b.to].x - DESKS[ZERO].x, DESKS[b.to].y - DESKS[ZERO].y) - Math.hypot(DESKS[a.to].x - DESKS[ZERO].x, DESKS[a.to].y - DESKS[ZERO].y));
  out.you = late[0]?.to ?? PEOPLE - 1;
  RUNS.set(key, out);
  return out;
};

export const stepOf = (seconds: number) => Math.round(seconds / STEP);
export const clockOf = (step: number) => {
  const day = Math.floor(step / STEPS_PER_DAY);
  const t = DAY_START + (step % STEPS_PER_DAY) * STEP;
  return {day, weekday: day % 5, hh: Math.floor(t / 3600), mm: Math.floor((t % 3600) / 60)};
};
export {STEPS_PER_DAY};
