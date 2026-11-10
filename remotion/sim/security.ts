// The security check at an airport, with the tills' engine (shop.ts): passengers arrive at random and each takes its
// time at the belt — ≈ 30 s for one who comes ready (liquids out, laptop out, nothing in the pockets), and now and then
// one who is not (≈ +40-120 s: the liquids, the laptop, the belt, the arch beeping). `ready`: everyone comes ready.
import {mulberry} from './world';
import {runShop, waits, type Person, type ShopRun} from './shop';

export const SECURITY = {base: 30, perBag: 8, unready: 0.3, extraMin: 40, extraMax: 120};

export const passengers = (rate: number, ready = false, seed = 29, span = 1800): Person[] => {
  const rnd = mulberry(seed);
  const out: Person[] = [];
  for (let t = 0, id = 0; t < span; id++) {
    t += -Math.log(1 - rnd()) / rate;
    const items = 1 + Math.floor(rnd() * 3);                       // trays
    const slow = rnd() < SECURITY.unready;
    const extra = SECURITY.extraMin + rnd() * (SECURITY.extraMax - SECURITY.extraMin);
    out.push({id, arrive: t, items, service: SECURITY.base + SECURITY.perBag * items + (slow && !ready ? extra : 0), slow: slow && !ready});
  }
  return out;
};

/** The mean service time of the real mix (for the arrivals that keep the lanes ~`busy`). */
export const MEAN_SERVICE = SECURITY.base + SECURITY.perBag * 2 + SECURITY.unready * (SECURITY.extraMin + SECURITY.extraMax) / 2;
export const rateFor = (lanes: number, busy = 0.92) => (lanes * busy) / MEAN_SERVICE;

export const security = (kind: 'many' | 'one', lanes: number, rate: number, ready: boolean, span = 1800, keep = true): ShopRun =>
  runShop(kind, lanes, passengers(rate, ready, 29, span), `sec:${rate}:${ready}`, undefined, span, keep);

const LONG = new Map<string, {mean: number; longest: number}>();
export const securityLong = (kind: 'many' | 'one', lanes: number, rate: number, ready: boolean) => {
  const id = `${kind}:${lanes}:${rate}:${ready}`;
  if (!LONG.has(id)) {
    const w = waits(security(kind, lanes, rate, ready, 60000, false), 1000, 59000);
    LONG.set(id, {mean: w.mean, longest: w.longest});
  }
  return LONG.get(id)!;
};
