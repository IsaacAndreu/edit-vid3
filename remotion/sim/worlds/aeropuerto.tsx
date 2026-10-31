// The security check at an airport seen from above (remotion/sim/security.ts): lanes with their walk-through arch and
// X-ray belt (trays going in), an officer at each, the passengers lining up. A passenger who is not ready (liquids,
// laptop, the arch beeping) holds their lane: red ring. Scenes:
//  filas       one line per lane (left) against one snake feeding every lane (right): the same people
//  preparados  the real mix (left) against everyone ready before the belt (right): the wait collapses
//  carriles    `carriles` lanes (left) against one more (right): near the limit one lane changes everything
import type {FC} from 'react';
import {AbsoluteFill} from 'remotion';
import {C, FONT} from '../hud';
import {addWords, tx} from '../i18n';
import {Pointers, type Anchor} from '../look';
import {rateFor, security, securityLong} from '../security';
import type {ShopFrame, ShopRun} from '../shop';
import {Big, Note, param, SideTitle, type World, type WorldProps} from '../world';
import {Shopper} from './colas';

addWords({
  linePerLane: {es: 'Una cola por control', pt: 'Uma fila por controle', fr: 'Une file par poste', de: 'Eine Schlange pro Spur', en: 'A line per lane'},
  snake: {es: 'Una sola cola en zigzag', pt: 'Uma só fila em zigue-zague', fr: 'Une seule file en zigzag', de: 'Eine Schlange im Zickzack', en: 'One snaking line'},
  realMix: {es: 'Como llega la gente', pt: 'Como as pessoas chegam', fr: 'Comme les gens arrivent', de: 'Wie die Leute kommen', en: 'As people really come'},
  allReady: {es: 'Todos preparados', pt: 'Todos preparados', fr: 'Tous prêts', de: 'Alle vorbereitet', en: 'Everyone ready'},
  lanesN: {es: '{n} controles abiertos', pt: '{n} controles abertos', fr: '{n} postes ouverts', de: '{n} Spuren offen', en: '{n} lanes open'},
  secNote: {es: 'Simulación · cada pasajero ≈ 30 s + 8 s por bandeja · 3 de cada 10 no vienen preparados (+40-120 s) · tiempo ×{x}', pt: 'Simulação · cada passageiro ≈ 30 s + 8 s por bandeja · 3 em cada 10 não vêm preparados (+40-120 s) · tempo ×{x}', fr: 'Simulation · chaque passager ≈ 30 s + 8 s par bac · 3 sur 10 ne sont pas prêts (+40-120 s) · temps ×{x}', de: 'Simulation · pro Fluggast ≈ 30 s + 8 s pro Wanne · 3 von 10 sind nicht vorbereitet (+40-120 s) · Zeit ×{x}', en: 'Simulation · each passenger ≈ 30 s + 8 s per tray · 3 in 10 are not ready (+40-120 s) · time ×{x}'},
});

const LAPSE = 4;
const BUSIEST = new Map<ShopRun, number>();
/** Where to start looking: a minute before the moment with most people waiting (between 5 and 28 minutes in). */
const busiest = (run: ShopRun) => {
  if (!BUSIEST.has(run)) {
    let best = 300;
    let most = -1;
    for (let t = 300; t < 1700; t += 10) {
      const n = run.at(t).lines.reduce((a, l) => a + l.length, 0);
      if (n > most) {
        most = n;
        best = t;
      }
    }
    BUSIEST.set(run, Math.max(0, best - 60));
  }
  return BUSIEST.get(run)!;
};
const fmt = (s: number) => (s < 60 ? `${Math.round(s)} s` : `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, '0')} min`);

const spotsOf = (f: ShopFrame, lanes: number, left: number, width: number, single: boolean) => {
  const cx = left + width / 2;
  const gap = Math.min(190, (width - 120) / lanes);
  const laneX = (i: number) => cx + (i - (lanes - 1) / 2) * gap;
  const ARCH = 330;
  const out: {id: number; x: number; y: number; at: boolean}[] = [];
  f.paying.forEach((id, i) => id >= 0 && out.push({id, x: laneX(i) - 30, y: ARCH + 10, at: true}));
  if (single) {
    f.lines[0].forEach((id, slot) => {
      const row = Math.floor(slot / 8);
      const col = slot % 8;
      out.push({id, x: cx + ((row % 2 ? 7 - col : col) - 3.5) * 56, y: ARCH + 220 + row * 82, at: false});
    });
  } else {
    f.lines.forEach((line, i) => line.forEach((id, slot) => out.push({id, x: laneX(i) - 30, y: ARCH + 110 + slot * 78, at: false})));
  }
  return {spots: out, laneX, ARCH};
};

const Hall: FC<{run: ShopRun; t: number; left: number; width: number; single: boolean}> = ({run, t, left, width, single}) => {
  const f = run.at(t);
  const byId = new Map(run.people.map((p) => [p.id, p]));
  const {spots, laneX, ARCH} = spotsOf(f, run.tills, left, width, single);
  // where each one was ~1 s ago: they walk up the line instead of jumping
  const before = new Map(spotsOf(run.at(Math.max(0, t - 1)), run.tills, left, width, single).spots.map((s) => [s.id, s]));
  return (
    <svg width={1920} height={1080} style={{position: 'absolute', clipPath: `inset(0 ${1920 - left - width}px 0 ${left}px)`}}>
      <rect x={left} y={0} width={width} height={1080} fill="#9aa1a8" />
      {Array.from({length: Math.ceil(width / 80) + 1}, (_, i) => <line key={i} x1={left + i * 80} x2={left + i * 80} y1={0} y2={1080} stroke="rgba(255,255,255,0.12)" strokeWidth={2} />)}
      {Array.from({length: 14}, (_, i) => <line key={`y${i}`} x1={left} x2={left + width} y1={i * 80} y2={i * 80} stroke="rgba(255,255,255,0.12)" strokeWidth={2} />)}
      {/* airside: the gates beyond */}
      <rect x={left} y={0} width={width} height={170} fill="#6d7a87" />
      <text x={left + width / 2} y={110} textAnchor="middle" fill="rgba(255,255,255,0.55)" fontFamily={FONT} fontSize={44} fontWeight={800} letterSpacing={6}>✈ GATES A1–A24</text>
      {Array.from({length: run.tills}, (_, i) => {
        const x = laneX(i);
        const busy = f.paying[i] >= 0;
        const who = busy ? byId.get(f.paying[i]) : undefined;
        const shift = (t * 30) % 60;
        return (
          <g key={i}>
            {/* the belt and the X-ray tunnel */}
            <rect x={x + 6} y={ARCH - 150} width={46} height={260} rx={4} fill="#2f343b" />
            {busy && Array.from({length: Math.min(3, who?.items ?? 1)}, (_, j) => (
              <rect key={j} x={x + 11} y={ARCH + 60 - ((j * 60 + shift) % 200)} width={36} height={26} rx={4} fill="#c9ced6" stroke="#8a919b" />
            ))}
            <rect x={x - 2} y={ARCH - 110} width={62} height={90} rx={8} fill="#4f6f8f" stroke="#2a3a4a" strokeWidth={3} />
            {/* the arch */}
            <rect x={x - 54} y={ARCH - 30} width={8} height={70} fill="#d9dde3" />
            <rect x={x - 14} y={ARCH - 30} width={8} height={70} fill="#d9dde3" />
            <rect x={x - 54} y={ARCH - 34} width={48} height={10} rx={3} fill={who?.slow ? C.red : '#d9dde3'} />
            {/* the officer */}
            <g transform={`translate(${x - 80} ${ARCH - 70})`}>
              <ellipse rx={17} ry={11} fill="#1f3550" stroke="rgba(0,0,0,0.35)" strokeWidth={2} />
              <circle r={8} fill="#2b2118" />
            </g>
            <text x={x + 29} y={ARCH - 125} textAnchor="middle" fill="#fff" fontFamily={FONT} fontSize={22} fontWeight={800}>{i + 1}</text>
          </g>
        );
      })}
      {single && Array.from({length: 4}, (_, r) => (
        <line key={r} x1={left + width / 2 - 230} x2={left + width / 2 + 230} y1={ARCH + 261 + r * 82} y2={ARCH + 261 + r * 82} stroke="#3a6ea5" strokeWidth={4}
              strokeDasharray={r % 2 ? '0 50 410' : '410 50'} />
      ))}
      {spots.map(({id, x, y, at}) => {
        const p = byId.get(id)!;
        const b = before.get(id);
        const sx = b ? (x + b.x) / 2 : x;
        const sy = b ? (y + b.y) / 2 : y;
        return <Shopper key={id} x={sx} y={sy} id={id} items={1} paying slow={at && p.slow} scale={0.9} />;
      })}
    </svg>
  );
};

const View: FC<WorldProps> = ({g, worldT, local, real = local, o, on}) => {
  const scene = param<string>(g, 'scene', 'filas');
  const lanes = Math.round(param(g, 'carriles', 4));
  const panel = Math.max(o('panel'), on * 0.9);
  const rate = rateFor(scene === 'carriles' ? lanes : 4);
  const marks: Record<string, Anchor | null> = {arch: {x: 480, y: 330}, line: {x: 1440, y: 700}};
  const [A, B] = scene === 'preparados'
    ? [[security('one', 4, rate, false), securityLong('one', 4, rate, false), tx('realMix'), true],
       [security('one', 4, rate, true), securityLong('one', 4, rate, true), tx('allReady'), true]] as const
    : scene === 'carriles'
      ? [[security('one', lanes, rate, false), securityLong('one', lanes, rate, false), tx('lanesN', {n: lanes}), true],
         [security('one', lanes + 1, rate, false), securityLong('one', lanes + 1, rate, false), tx('lanesN', {n: lanes + 1}), true]] as const
      : [[security('many', 4, rate, false), securityLong('many', 4, rate, false), tx('linePerLane'), false],
         [security('one', 4, rate, false), securityLong('one', 4, rate, false), tx('snake'), true]] as const;
  const t = busiest(A[0]) + worldT * LAPSE;            // both sides at the same moment, the busy one of the left
  return (
    <AbsoluteFill style={{background: C.night}}>
      <Hall run={A[0]} t={t} left={0} width={958} single={A[3]} />
      <Hall run={B[0]} t={t} left={962} width={958} single={B[3]} />
      <div style={{position: 'absolute', left: 958, top: 0, width: 4, height: 1080, background: C.night}} />
      <SideTitle text={A[2]} style={{left: 48, top: 30}} />
      <SideTitle text={B[2]} style={{left: 1010, top: 30}} />
      <Big o={panel} label={tx('averageWaitShort')} value={fmt(A[1].mean)} color={A[1].mean > B[1].mean ? C.red : C.green}
           sub={`${tx('longestWait')}: ${fmt(A[1].longest)}`} style={{left: 48, bottom: 60, width: 330}} />
      <Big o={panel} label={tx('averageWaitShort')} value={fmt(B[1].mean)} color={B[1].mean > A[1].mean ? C.red : C.green}
           sub={`${tx('longestWait')}: ${fmt(B[1].longest)}`} style={{left: 1010, bottom: 60, width: 330}} />
      <Pointers marks={g.marks} local={real} at={marks} />
      <Note>{tx('secNote', {x: LAPSE})}</Note>
    </AbsoluteFill>
  );
};

export const aeropuerto: World = {View, ambient: 'murmur'};
