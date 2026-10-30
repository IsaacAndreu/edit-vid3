// A savanna seen from above: gazelles and lions. In a herd the gazelles keep together (boids: stay close, line up,
// don't collide) and a lion chasing one has others crossing its path — it keeps switching prey and tires before it
// catches any (the confusion effect). Scattered, each gazelle is alone, and the lions pick them off.
import type {FC} from 'react';
import {AbsoluteFill} from 'remotion';
import {C} from '../hud';
import {addWords, tx} from '../i18n';
import {Big, mulberry, Note, param, type World, type WorldProps} from '../world';

addWords({
  caught: {es: 'Gacelas cazadas', pt: 'Gazelas caçadas', fr: 'Gazelles attrapées', de: 'Gefangene Gazellen', en: 'Gazelles caught'},
  herdLabel: {es: 'La manada', pt: 'A manada', fr: 'Le troupeau', de: 'Die Herde', en: 'The herd'},
  savannaNote: {es: 'Simulación · {g} gacelas, {l} leones · {h}', pt: 'Simulação · {g} gazelas, {l} leões · {h}', fr: 'Simulation · {g} gazelles, {l} lions · {h}', de: 'Simulation · {g} Gazellen, {l} Löwen · {h}', en: 'Simulation · {g} gazelles, {l} lions · {h}'},
  inHerd: {es: 'en manada', pt: 'em manada', fr: 'en troupeau', de: 'in der Herde', en: 'in a herd'},
  scattered: {es: 'cada una a lo suyo', pt: 'cada uma por si', fr: 'chacune pour soi', de: 'jede für sich', en: 'each on its own'},
});

const GAZELLES = 150;
const FRAMES = 80 * 30;
const W = 1920;
const H = 1080;

type Hunt = {gx: Float32Array[]; gh: Float32Array[]; alive: Uint8Array[]; lx: Float32Array[]; lh: Float32Array[]; caught: number[]};
const HUNTS = new Map<string, Hunt>();

export const hunt = (lions: number, herd: number): Hunt => {
  const id = `${lions}:${herd}`;
  if (HUNTS.has(id)) return HUNTS.get(id)!;
  const rnd = mulberry(19 + lions);
  const n = GAZELLES;
  const x = new Float32Array(n);
  const y = new Float32Array(n);
  const vx = new Float32Array(n);
  const vy = new Float32Array(n);
  const alive = new Uint8Array(n).fill(1);
  for (let k = 0; k < n; k++) {
    if (herd) {
      x[k] = 1150 + (rnd() - 0.5) * 300;
      y[k] = 540 + (rnd() - 0.5) * 240;
    } else {
      x[k] = 500 + rnd() * 1300;
      y[k] = 100 + rnd() * 880;
    }
    vx[k] = (rnd() - 0.5) * 1.2;
    vy[k] = (rnd() - 0.5) * 1.2;
  }
  const L = lions;
  const lx = new Float32Array(L);
  const ly = new Float32Array(L);
  const lvx = new Float32Array(L);
  const lvy = new Float32Array(L);
  const target = new Int32Array(L).fill(-1);
  const chase = new Float32Array(L);            // frames spent chasing
  const rest = new Float32Array(L);             // frames left resting (tired, or eating)
  for (let j = 0; j < L; j++) {
    lx[j] = 560 + rnd() * 180;                      // already near, crouched in the grass
    ly[j] = 150 + (j / Math.max(1, L - 1)) * 780;
  }
  const out: Hunt = {gx: [], gh: [], alive: [], lx: [], lh: [], caught: []};
  let caught = 0;
  for (let f = 0; f < FRAMES; f++) {
    // gazelles
    for (let k = 0; k < n; k++) {
      if (!alive[k]) continue;
      let ax = 0;
      let ay = 0;
      let cx = 0;
      let cy = 0;
      let ux = 0;
      let uy = 0;
      let near = 0;
      for (let m = 0; m < n; m++) {
        if (m === k || !alive[m]) continue;
        const dx = x[m] - x[k];
        const dy = y[m] - y[k];
        const d = Math.hypot(dx, dy);
        if (d < 16) {
          ax -= dx / (d + 0.1) * 0.25;
          ay -= dy / (d + 0.1) * 0.25;
        }
        if (herd && d < 80) {
          cx += x[m];
          cy += y[m];
          ux += vx[m];
          uy += vy[m];
          near++;
        }
      }
      if (near) {
        ax += (cx / near - x[k]) * 0.004 + (ux / near - vx[k]) * 0.06;
        ay += (cy / near - y[k]) * 0.004 + (uy / near - vy[k]) * 0.06;
      }
      // a stalking lion goes unnoticed until it is close; a sprinting one is seen from afar
      let fleeing = false;
      for (let j = 0; j < L; j++) {
        const dx = x[k] - lx[j];
        const dy = y[k] - ly[j];
        const d = Math.hypot(dx, dy);
        const sprinting = Math.hypot(lvx[j], lvy[j]) > 2.5;
        if (d < (sprinting ? 170 : 55)) {
          ax += (dx / d) * 0.6 + (rnd() - 0.5) * 0.9;      // away, zigzagging
          ay += (dy / d) * 0.6 + (rnd() - 0.5) * 0.9;
          fleeing = true;
        }
      }
      ax += (rnd() - 0.5) * 0.12;
      ay += (rnd() - 0.5) * 0.12;
      // the edges of the savanna turn them back
      if (x[k] < 60) ax += 0.3;
      if (x[k] > W - 60) ax -= 0.3;
      if (y[k] < 60) ay += 0.3;
      if (y[k] > H - 60) ay -= 0.3;
      vx[k] += ax;
      vy[k] += ay;
      const top = fleeing ? 4.2 : 1.1;
      const sp = Math.hypot(vx[k], vy[k]);
      if (sp > top) {
        vx[k] *= top / sp;
        vy[k] *= top / sp;
      }
      x[k] += vx[k];
      y[k] += vy[k];
    }
    // lions: the nearest gazelle; with others crowding round it, they lose it and pick again; they tire after 4 s
    for (let j = 0; j < L; j++) {
      if (rest[j] > 0) {
        rest[j]--;
        lvx[j] *= 0.9;
        lvy[j] *= 0.9;
      } else {
        const crowd = target[j] >= 0 ? [...Array(n).keys()].filter((m) => alive[m] && Math.hypot(x[m] - x[target[j]], y[m] - y[target[j]]) < 45).length : 0;
        if (target[j] < 0 || !alive[target[j]] || (crowd > 5 && f % 12 === 0 && rnd() < 0.6)) {
          let best = -1;
          let bd = Infinity;
          for (let k = 0; k < n; k++) {
            if (!alive[k]) continue;
            const d = Math.hypot(x[k] - lx[j], y[k] - ly[j]) + (k === target[j] ? 25 : 0) + rnd() * 40;
            if (d < bd) {
              bd = d;
              best = k;
            }
          }
          target[j] = best;
        }
        const t = target[j];
        if (t >= 0) {
          const dx = x[t] - lx[j];
          const dy = y[t] - ly[j];
          const d = Math.hypot(dx, dy);
          // stalk slowly up to striking distance, then sprint (faster than a gazelle, for a few seconds)
          const sprint = chase[j] > 0 || d < 95;
          const speed = sprint ? 6.2 : 1.3;
          if (sprint) chase[j]++;
          lvx[j] += (dx / d) * 0.5;
          lvy[j] += (dy / d) * 0.5;
          const sp = Math.hypot(lvx[j], lvy[j]);
          if (sp > speed) {
            lvx[j] *= speed / sp;
            lvy[j] *= speed / sp;
          }
          if (d < 11) {
            alive[t] = 0;
            caught++;
            rest[j] = 150;                 // eating
            chase[j] = 0;
          } else if (chase[j] > 75) {
            rest[j] = 110;                 // out of breath
            chase[j] = 0;
            target[j] = -1;
          }
        }
      }
      lx[j] += lvx[j];
      ly[j] += lvy[j];
    }
    const gh = new Float32Array(n);
    for (let k = 0; k < n; k++) gh[k] = Math.atan2(vy[k], vx[k]);
    const lh = new Float32Array(L);
    for (let j = 0; j < L; j++) lh[j] = Math.atan2(lvy[j], lvx[j]);
    out.gx.push(Float32Array.from([...x, ...y]));
    out.gh.push(gh);
    out.alive.push(Uint8Array.from(alive));
    out.lx.push(Float32Array.from([...lx, ...ly]));
    out.lh.push(lh);
    out.caught.push(caught);
  }
  HUNTS.set(id, out);
  return out;
};

const TREES = (() => {
  const rnd = mulberry(77);
  return Array.from({length: 26}, () => ({x: rnd() * W, y: rnd() * H, r: 18 + rnd() * 26}));
})();

const View: FC<WorldProps> = ({g, worldT, move, o}) => {
  const lions = Math.round(param(g, 'lions', 6));
  const herd = param(g, 'herd', 1);
  const h = hunt(lions, herd);
  const f = Math.max(0, Math.min(FRAMES - 1, Math.round(worldT * 30)));
  const gx = h.gx[f];
  const lx = h.lx[f];
  const alive = h.alive[f];
  const zoom = (focus: string) => (focus === 'close' ? 2.1 : 1);
  const s = zoom(g.prev) + (zoom(g.focus) - zoom(g.prev)) * move;
  const fx = lx[0];
  const fy = lx[lions];
  const live = [...alive.keys()].filter((k) => alive[k]);
  const mx = live.reduce((a, k) => a + gx[k], 0) / Math.max(1, live.length);
  const my = live.reduce((a, k) => a + gx[GAZELLES + k], 0) / Math.max(1, live.length);
  const spread = Math.sqrt(live.reduce((a, k) => a + (gx[k] - mx) ** 2 + (gx[GAZELLES + k] - my) ** 2, 0) / Math.max(1, live.length));
  return (
    <AbsoluteFill style={{background: '#c4a465', overflow: 'hidden'}}>
      <div style={{position: 'absolute', inset: 0, transformOrigin: `${fx}px ${fy}px`, transform: `scale(${s})`}}>
        <svg width={W} height={H} style={{position: 'absolute'}}>
          <defs>
            <radialGradient id="patch"><stop offset="0" stopColor="#b8995a" /><stop offset="1" stopColor="#c4a465" stopOpacity={0} /></radialGradient>
          </defs>
          {TREES.map((t, i) => <circle key={`p${i}`} cx={(t.x * 1.7) % W} cy={(t.y * 1.3) % H} r={t.r * 5} fill="url(#patch)" />)}
          <ellipse cx={1500} cy={260} rx={150} ry={80} fill="#5b8aa8" opacity={0.85} />
          <ellipse cx={1500} cy={260} rx={170} ry={98} fill="none" stroke="#9c8a5a" strokeWidth={8} opacity={0.6} />
          {[...Array(GAZELLES).keys()].filter((k) => !alive[k]).map((k) => (
            <circle key={`d${k}`} cx={gx[k]} cy={gx[GAZELLES + k]} r={6} fill="#8a2d2d" opacity={0.6} />
          ))}
          {live.map((k) => (
            <g key={k} transform={`translate(${gx[k]} ${gx[GAZELLES + k]}) rotate(${(h.gh[f][k] * 180) / Math.PI})`}>
              <ellipse cx={0} cy={0} rx={8} ry={3.6} fill="#a8743f" stroke="#5a3b1c" strokeWidth={1} />
              <circle cx={7} cy={0} r={2.6} fill="#8c5e30" />
            </g>
          ))}
          {Array.from({length: lions}, (_, j) => (
            <g key={`l${j}`} transform={`translate(${lx[j]} ${lx[lions + j]}) rotate(${(h.lh[f][j] * 180) / Math.PI})`}>
              <ellipse cx={0} cy={2} rx={17} ry={8} fill="rgba(0,0,0,0.2)" />
              <ellipse cx={0} cy={0} rx={16} ry={7} fill="#d29a3c" stroke="#6b4512" strokeWidth={1.5} />
              <circle cx={13} cy={0} r={7} fill="#7a4a14" />
              <circle cx={15} cy={0} r={4} fill="#d29a3c" />
            </g>
          ))}
          {TREES.map((t, i) => (
            <g key={`t${i}`}>
              <circle cx={t.x + 8} cy={t.y + 8} r={t.r} fill="rgba(0,0,0,0.18)" />
              <circle cx={t.x} cy={t.y} r={t.r} fill="#4e6b2e" />
              <circle cx={t.x - t.r * 0.3} cy={t.y - t.r * 0.3} r={t.r * 0.5} fill="#5f8038" />
            </g>
          ))}
          {herd > 0 && o('herd') > 0 && (
            <g opacity={o('herd')}>
              <ellipse cx={mx} cy={my} rx={spread * 1.6} ry={spread * 1.3} fill="none" stroke={C.accent} strokeWidth={4} strokeDasharray="14 10" />
              <text x={mx + spread * 1.2} y={my - spread * 1.4} fill="#1a1f29" fontFamily='"Barlow Condensed", sans-serif' fontWeight={800} fontSize={30}
                    style={{textTransform: 'uppercase'}}>{tx('herdLabel')}</text>
            </g>
          )}
        </svg>
      </div>
      <AbsoluteFill style={{background: 'radial-gradient(ellipse at center, rgba(0,0,0,0) 55%, rgba(30,20,5,0.45) 100%)'}} />
      <Big o={o('caught')} label={tx('caught')} value={`${h.caught[f]}`} color={C.red} sub={`/ ${GAZELLES}`} style={{right: 48, top: 52}} />
      <Note>{tx('savannaNote', {g: GAZELLES, l: lions, h: tx(herd ? 'inHerd' : 'scattered')})}</Note>
    </AbsoluteFill>
  );
};

// a tick at every catch while the count is on
const sounds = (g: WorldProps['g'], length: number) => {
  if (g.overlay !== 'caught') return {};
  const h = hunt(Math.round(param(g, 'lions', 6)), param(g, 'herd', 1));
  const f0 = Math.round((g.at - g.since) * 30);
  const ticks: number[] = [];
  for (let f = f0 + 1; f < Math.min(FRAMES, f0 + length * 30); f++) if (h.caught[f] > h.caught[f - 1]) ticks.push((f - f0) / 30);
  return {ticks};
};

export const manada: World = {View, sounds};
