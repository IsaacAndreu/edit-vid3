// Two planes boarding at once, seen from above: on top back to front by blocks (what most airlines do), below the
// method the script picks — random, Steffen's (2008: alternate rows, windows first) or windows-middles-aisles. One
// aisle: whoever stops to stow a bag blocks everyone behind; whoever sits by the window makes the aisle side stand up.
import type {FC} from 'react';
import {AbsoluteFill} from 'remotion';
import {C, Label, Panel} from '../hud';
import {addWords, tx} from '../i18n';
import {mulberry, Note, param, type World, type WorldProps} from '../world';

addWords({
  backToFront: {es: 'De atrás hacia delante', pt: 'De trás para a frente', fr: 'De l’arrière vers l’avant', de: 'Von hinten nach vorn', en: 'Back to front'},
  methodRandom: {es: 'Sin orden', pt: 'Sem ordem', fr: 'Sans ordre', de: 'Ohne Reihenfolge', en: 'Random order'},
  methodSteffen: {es: 'Método Steffen', pt: 'Método Steffen', fr: 'Méthode Steffen', de: 'Steffen-Methode', en: 'Steffen method'},
  methodWindow: {es: 'Ventanilla, centro, pasillo', pt: 'Janela, meio, corredor', fr: 'Hublot, milieu, couloir', de: 'Fenster, Mitte, Gang', en: 'Window, middle, aisle'},
  boarding: {es: 'Embarcando', pt: 'Embarque', fr: 'Embarquement', de: 'Boarding', en: 'Boarding'},
  done: {es: 'Terminado', pt: 'Concluído', fr: 'Terminé', de: 'Fertig', en: 'Done'},
  seated: {es: 'Sentados', pt: 'Sentados', fr: 'Assis', de: 'Sitzen', en: 'Seated'},
  blocking: {es: 'Bloqueando el pasillo', pt: 'A bloquear o corredor', fr: 'Bloquent le couloir', de: 'Blockieren den Gang', en: 'Blocking the aisle'},
  planeNote: {es: 'Simulación · {n} pasajeros · un pasillo · tiempo ×{x}', pt: 'Simulação · {n} passageiros · um corredor · tempo ×{x}', fr: 'Simulation · {n} passagers · un couloir · temps ×{x}', de: 'Simulation · {n} Passagiere · ein Gang · Zeit ×{x}', en: 'Simulation · {n} passengers · one aisle · time ×{x}'},
});

const ROWS = 30;
const SEATS = 6;                                // A B C | aisle | D E F
const DT = 0.5;
const LAPSE = 30;                               // seconds of boarding per second of video
const SPAN = 2600;                              // seconds simulated
const WALK = 0.9;                               // seconds per row

type Pax = {row: number; seat: number; bag: number};
type Boarding = {pax: Pax[]; pos: Float32Array[]; state: Uint8Array[]; done: number};   // state: 0 outside, 1 walking, 2 stowing, 3 seated
const RUNS = new Map<string, Boarding>();

const order = (method: string, rnd: () => number): Pax[] => {
  const all: Pax[] = [];
  for (let row = 1; row <= ROWS; row++) for (let seat = 0; seat < SEATS; seat++) all.push({row, seat, bag: rnd() < 0.8 ? 6 + rnd() * 14 : 2});
  const shuffle = (list: Pax[]) => list.map((p) => [rnd(), p] as const).sort((a, b) => a[0] - b[0]).map(([, p]) => p);
  const column = (p: Pax) => (p.seat === 0 || p.seat === 5 ? 0 : p.seat === 1 || p.seat === 4 ? 1 : 2);   // window, middle, aisle
  if (method === 'backToFront') {
    return [...shuffle(all.filter((p) => p.row > 20)), ...shuffle(all.filter((p) => p.row > 10 && p.row <= 20)), ...shuffle(all.filter((p) => p.row <= 10))];
  }
  if (method === 'window') return [0, 1, 2].flatMap((c) => shuffle(all.filter((p) => column(p) === c)));
  if (method === 'steffen') {
    // windows of every other row from the back on one side, then the other side, then the other rows; then middles, aisles
    const out: Pax[] = [];
    for (const c of [0, 1, 2]) for (const parity of [0, 1]) for (const side of [0, 1]) {
      out.push(...all.filter((p) => column(p) === c && p.row % 2 === parity && (p.seat < 3 ? 0 : 1) === side).sort((a, b) => b.row - a.row));
    }
    return out;
  }
  return shuffle(all);
};

export const board = (method: string): Boarding => {
  if (RUNS.has(method)) return RUNS.get(method)!;
  const rnd = mulberry(method.length * 7 + 3);
  const pax = order(method, rnd);
  const n = pax.length;
  const at = new Float32Array(n).fill(-1);          // aisle position (rows from the door); -1 outside
  const state = new Uint8Array(n);
  const busyUntil = new Float32Array(n);
  const seatedRow: number[][] = Array.from({length: ROWS + 1}, () => []);
  let next = 0;
  let done = 0;
  const out: Boarding = {pax, pos: [], state: [], done: 0};
  for (let step = 0; step * DT < SPAN; step++) {
    const t = step * DT;
    // walking: one row per WALK seconds, never into someone ahead in the aisle
    const inAisle = [...state.keys()].filter((k) => state[k] === 1 || state[k] === 2).sort((a, b) => at[b] - at[a]);
    for (const k of inAisle) {
      if (state[k] === 2) {
        if (t >= busyUntil[k]) {
          state[k] = 3;
          seatedRow[pax[k].row].push(pax[k].seat);
          done = t;
        }
        continue;
      }
      const target = pax[k].row;
      const ahead = inAisle.filter((j) => j !== k && at[j] > at[k]).map((j) => at[j]);
      const limit = ahead.length ? Math.min(...ahead) - 1 : Infinity;
      at[k] = Math.min(target, at[k] + DT / WALK, limit);
      if (at[k] >= target - 1e-6) {
        // the bag, then whoever must stand up to let them in
        const side = pax[k].seat < 3 ? [0, 1, 2] : [5, 4, 3];
        const inWay = seatedRow[target].filter((s) => side.indexOf(s) > side.indexOf(pax[k].seat)).length;
        state[k] = 2;
        busyUntil[k] = t + pax[k].bag + inWay * 7;
      }
    }
    // the next passenger steps in when the door is clear
    if (next < n && !inAisle.some((j) => at[j] < 0.9)) {
      state[next] = 1;
      at[next] = 0;
      next++;
    }
    out.pos.push(Float32Array.from(at));
    out.state.push(Uint8Array.from(state));
  }
  out.done = done;
  RUNS.set(method, out);
  return out;
};

const fmt = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;

const Plane: FC<{run: Boarding; t: number; top: number; scale: number; blocked: number; title: string; o: number}> = ({run, t, top, scale, blocked, title, o}) => {
  const step = Math.min(run.pos.length - 1, Math.floor(t / DT));
  const pos = run.pos[step];
  const state = run.state[step];
  const ROW = 50 * scale;
  const SEAT = 22 * scale;
  const left = 960 - (ROWS * ROW) / 2 + 40;
  const mid = top;
  const seatY = (seat: number) => mid + (seat < 3 ? -(3 - seat) * SEAT - SEAT * 0.6 : (seat - 2) * SEAT + SEAT * 0.6) + SEAT / 2 - SEAT / 2;
  const width = SEAT * 7.6;
  const seated = state.reduce((s, v) => s + (v === 3 ? 1 : 0), 0);
  const finished = seated === run.pax.length;
  const shownT = finished ? run.done : t;
  return (
    <g>
      <path d={`M${left - 90 * scale},${mid} Q${left - 90 * scale},${mid - width / 2} ${left},${mid - width / 2} L${left + ROWS * ROW + 30},${mid - width / 2}
               L${left + ROWS * ROW + 30},${mid + width / 2} L${left},${mid + width / 2} Q${left - 90 * scale},${mid + width / 2} ${left - 90 * scale},${mid} Z`}
            fill="#e8ebf0" stroke="#9aa3ad" strokeWidth={3} />
      <rect x={left - 10} y={mid - SEAT * 0.45} width={ROWS * ROW + 30} height={SEAT * 0.9} fill="#c9ced6" />
      {Array.from({length: ROWS}, (_, r) => Array.from({length: SEATS}, (_, s) => (
        <rect key={`${r}-${s}`} x={left + r * ROW + ROW * 0.2} y={seatY(s) - SEAT * 0.42} width={ROW * 0.6} height={SEAT * 0.84} rx={4 * scale} fill="#7d8796" />
      )))}
      {run.pax.map((p, k) => {
        if (state[k] === 0) return null;
        const x = state[k] === 3 ? left + (p.row - 1) * ROW + ROW / 2 : left + (Math.max(0, pos[k]) - 1) * ROW + ROW / 2;
        const y = state[k] === 3 ? seatY(p.seat) : mid;
        const isBlock = state[k] === 2;
        return (
          <g key={k}>
            {isBlock && blocked > 0.3 && <circle cx={x} cy={y} r={SEAT * 0.95} fill="none" stroke={C.accent} strokeWidth={3} opacity={blocked} />}
            <circle cx={x} cy={y} r={SEAT * 0.38} fill={state[k] === 3 ? '#3ddc84' : isBlock ? C.accent : '#e5484d'} stroke="#1a1f29" strokeWidth={1.5} />
          </g>
        );
      })}
      <text x={left - 80 * scale} y={mid - width / 2 - 18} fill={C.text} fontFamily='"Barlow Condensed", sans-serif' fontWeight={800} fontSize={34}
            style={{textTransform: 'uppercase'}}>{title}</text>
      <g opacity={o}>
        <rect x={left + ROWS * ROW - 300} y={mid - width / 2 - 64} width={330} height={52} rx={6} fill={C.panel} />
        <text x={left + ROWS * ROW - 284} y={mid - width / 2 - 28} fill={finished ? C.green : C.text} fontFamily='"Barlow Condensed", sans-serif' fontWeight={800} fontSize={32}>
          {(finished ? tx('done') : tx('boarding')).toUpperCase()} {fmt(shownT)} · {seated}/{run.pax.length}
        </text>
      </g>
    </g>
  );
};

const NAMES: Record<string, string> = {random: 'methodRandom', steffen: 'methodSteffen', window: 'methodWindow'};

const View: FC<WorldProps> = ({g, worldT, move, o}) => {
  const method = String(param(g, 'method', 'steffen'));
  const t = worldT * LAPSE;
  const share = (f: string) => (f === 'top' ? 0.66 : f === 'bottom' ? 0.34 : 0.5);
  const s = share(g.prev) + (share(g.focus) - share(g.prev)) * move;
  const scaleTop = g.focus === 'bottom' ? 0.8 : g.focus === 'top' ? 1.1 : 1;
  const scaleBottom = g.focus === 'top' ? 0.8 : g.focus === 'bottom' ? 1.1 : 1;
  const timer = o('timer');
  const blocked = o('blocked');
  const a = board('backToFront');
  const b = board(method);
  const stowing = (run: Boarding) => run.state[Math.min(run.state.length - 1, Math.floor(t / DT))].reduce((n, v) => n + (v === 2 ? 1 : 0), 0);
  return (
    <AbsoluteFill style={{background: '#1b2433'}}>
      <svg width={1920} height={1080} style={{position: 'absolute'}}>
        <Plane run={a} t={t} top={1080 * s * 0.55} scale={scaleTop} blocked={blocked} title={tx('backToFront')} o={timer} />
        <Plane run={b} t={t} top={1080 * s + 1080 * (1 - s) * 0.5} scale={scaleBottom} blocked={blocked} title={tx(NAMES[method] ?? 'methodSteffen')} o={timer} />
      </svg>
      <Panel o={blocked} style={{right: 48, bottom: 70, width: 360}}>
        <Label>{tx('blocking')}</Label>
        <div style={{display: 'flex', gap: 30, fontSize: 40, fontWeight: 800, marginTop: 6}}>
          <span>↑ {stowing(a)}</span><span>↓ {stowing(b)}</span>
        </div>
      </Panel>
      <Note>{tx('planeNote', {n: ROWS * SEATS, x: LAPSE})}</Note>
    </AbsoluteFill>
  );
};

export const embarque: World = {View, ambient: 'murmur'};
