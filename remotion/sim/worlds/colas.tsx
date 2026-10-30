// A supermarket's tills seen from above, twice with the same customers (each takes as long to pay in both): on the
// left one line per till (each customer picks the shortest), on the right one line that feeds every till. Some
// customers are slow (a price check, coupons): on the left whoever is behind them waits; on the right nobody does.
import type {FC} from 'react';
import {AbsoluteFill} from 'remotion';
import {C, Label, Panel} from '../hud';
import {addWords, tx} from '../i18n';
import {Big, mulberry, Note, param, SideTitle, splitAt, type World, type WorldProps} from '../world';

addWords({
  manyLines: {es: 'Una cola por caja', pt: 'Uma fila por caixa', fr: 'Une file par caisse', de: 'Eine Schlange pro Kasse', en: 'A line per till'},
  oneLine: {es: 'Una sola cola', pt: 'Uma só fila', fr: 'Une seule file', de: 'Eine einzige Schlange', en: 'One single line'},
  averageWaitShort: {es: 'Espera media', pt: 'Espera média', fr: 'Attente moyenne', de: 'Mittlere Wartezeit', en: 'Average wait'},
  longestWait: {es: 'La espera más larga', pt: 'A espera mais longa', fr: 'L’attente la plus longue', de: 'Längste Wartezeit', en: 'Longest wait'},
  slowLine: {es: 'Eligió la cola lenta', pt: 'Escolheu a fila lenta', fr: 'A choisi la file lente', de: 'Hat die langsame Schlange erwischt', en: 'Picked the slow line'},
  hereWaited: {es: 'Aquí esperó {a} · con una sola cola, {b}', pt: 'Aqui esperou {a} · com uma só fila, {b}', fr: 'Ici : {a} · avec une seule file : {b}', de: 'Hier: {a} · mit einer Schlange: {b}', en: 'Waited {a} here · with one line, {b}'},
  queueNote: {es: 'Simulación · los mismos clientes en los dos · {n} cajas · tiempo ×{x}', pt: 'Simulação · os mesmos clientes nos dois · {n} caixas · tempo ×{x}', fr: 'Simulation · les mêmes clients des deux côtés · {n} caisses · temps ×{x}', de: 'Simulation · dieselben Kunden in beiden · {n} Kassen · Zeit ×{x}', en: 'Simulation · the same customers in both · {n} tills · time ×{x}'},
});

const LAPSE = 4;                               // seconds of shop per second of video
const SPAN = 220 * LAPSE;

type Customer = {arrive: number; service: number; till: number; start: number; end: number; shirt: string};
type Shop = {many: Customer[]; one: Customer[]};
const SHIRTS = ['#e5484d', '#5b8def', '#30a46c', '#f5a623', '#8e7cf8', '#3dd6d0', '#e8e4dc', '#ff7ac6'];
const SHOPS = new Map<string, Shop>();

export const shop = (tills: number, arrivals: number): Shop => {
  const id = `${tills}:${arrivals}`;
  if (SHOPS.has(id)) return SHOPS.get(id)!;
  const rnd = mulberry(31);
  const people: {arrive: number; service: number}[] = [];
  for (let t = 0; t < SPAN;) {
    t += -Math.log(1 - rnd()) / arrivals;
    const slow = rnd() < 0.15;
    people.push({arrive: t, service: slow ? 18 + rnd() * 25 : 5 + rnd() * 5});
  }
  // one line per till: each picks the line with fewest people when arriving
  const free = Array(tills).fill(0);
  const many: Customer[] = [];
  for (const [k, p] of people.entries()) {
    const waiting = (i: number) => many.filter((c) => c.till === i && c.end > p.arrive).length;
    let best = 0;
    for (let i = 1; i < tills; i++) if (waiting(i) < waiting(best)) best = i;
    const start = Math.max(p.arrive, free[best]);
    free[best] = start + p.service;
    many.push({...p, till: best, start, end: start + p.service, shirt: SHIRTS[k % SHIRTS.length]});
  }
  // one line: the first in line goes to whichever till frees first
  const tillFree = Array(tills).fill(0);
  const one: Customer[] = people.map((p, k) => {
    let best = 0;
    for (let i = 1; i < tills; i++) if (tillFree[i] < tillFree[best]) best = i;
    const start = Math.max(p.arrive, tillFree[best]);
    tillFree[best] = start + p.service;
    return {...p, till: best, start, end: start + p.service, shirt: SHIRTS[k % SHIRTS.length]};
  });
  const out = {many, one};
  SHOPS.set(id, out);
  return out;
};

const fmt = (s: number) => (s < 60 ? `${Math.round(s)} s` : `${Math.floor(s / 60)} min ${String(Math.round(s % 60)).padStart(2, '0')}`);

const stats = (list: Customer[], t: number) => {
  const served = list.filter((c) => c.start <= t);
  const waits = served.map((c) => c.start - c.arrive);
  return {average: waits.length ? waits.reduce((a, b) => a + b, 0) / waits.length : 0, longest: waits.length ? Math.max(...waits) : 0};
};

// one shop drawn in a band of the screen [left, left + width)
const Store: FC<{list: Customer[]; tills: number; t: number; left: number; width: number; single: boolean; unlucky?: number}> = (
  {list, tills, t, left, width, single, unlucky}) => {
  const cx = left + width / 2;
  const gap = Math.min(190, (width - 120) / tills);
  const tillX = (i: number) => cx + (i - (tills - 1) / 2) * gap;
  const TILL_Y = 400;
  const items = [];
  // waiting: by order of arrival in its line
  const waiting = list.map((c, k) => [c, k] as const).filter(([c]) => c.arrive <= t && c.start > t);
  const place = (k: number, slot: number, c: Customer): [number, number] => {
    if (!single) return [tillX(c.till), TILL_Y + 90 + slot * 52];
    const row = Math.floor(slot / 7);
    const col = slot % 7;
    const x = cx + ((row % 2 ? 6 - col : col) - 3) * 56;
    return [x, TILL_Y + 170 + row * 60];
  };
  const slots = new Map<number, number>();
  if (single) waiting.forEach(([, k], n) => slots.set(k, n));
  else for (let i = 0; i < tills; i++) waiting.filter(([c]) => c.till === i).forEach(([, k], n) => slots.set(k, n));
  for (const [c, k] of waiting) {
    const [x, y] = place(k, slots.get(k)!, c);
    items.push({k, x, y, c, paying: false});
  }
  for (const [k, c] of list.entries()) {
    if (c.start <= t && c.end > t) items.push({k, x: tillX(c.till), y: TILL_Y + 34, c, paying: true});
  }
  return (
    <svg width={1920} height={1080} style={{position: 'absolute', clipPath: `inset(0 ${1920 - left - width}px 0 ${left}px)`}}>
      <rect x={left} y={0} width={width} height={1080} fill="#2b313c" />
      {Array.from({length: 40}, (_, i) => <line key={i} x1={left + i * 48} y1={0} x2={left + i * 48} y2={1080} stroke="rgba(255,255,255,0.035)" />)}
      {Array.from({length: 40}, (_, i) => <line key={`h${i}`} x1={left} y1={i * 48} x2={left + width} y2={i * 48} stroke="rgba(255,255,255,0.035)" />)}
      {Array.from({length: 3}, (_, i) => (
        <g key={`s${i}`}>
          <rect x={left + 60} y={200 + i * 34} width={width - 120} height={20} rx={4} fill="#454c59" />
          {Array.from({length: Math.floor((width - 140) / 26)}, (_, j) => (
            <rect key={j} x={left + 66 + j * 26} y={203 + i * 34} width={18} height={14} rx={2} fill={['#e5484d', '#f5a623', '#3ddc84', '#5b8def'][(i + j) % 4]} opacity={0.55} />
          ))}
        </g>
      ))}
      {Array.from({length: tills}, (_, i) => (
        <g key={`t${i}`}>
          <rect x={tillX(i) - 46} y={TILL_Y - 30} width={92} height={44} rx={5} fill="#596170" />
          <rect x={tillX(i) - 38} y={TILL_Y - 22} width={56} height={28} rx={3} fill="#3a3f4a" />
          <circle cx={tillX(i) + 30} cy={TILL_Y - 8} r={9} fill="#3ddc84" />
        </g>
      ))}
      {single && <rect x={cx - 200} y={TILL_Y + 120} width={400} height={6} rx={3} fill="#c9ccd2" opacity={0.25} />}
      {items.map(({k, x, y, c, paying}) => (
        <g key={k}>
          <rect x={x - 16} y={y + 8} width={32} height={22} rx={4} fill="#9aa3ad" stroke="#c9ccd2" strokeWidth={2} opacity={paying ? 0 : 0.9} />
          <circle cx={x} cy={y - 8} r={17} fill={c.shirt} stroke="#12161f" strokeWidth={3} />
          <circle cx={x} cy={y - 8} r={7} fill="#f1d3b5" />
          {c.service > 17 && <text x={x + 20} y={y - 18} fontSize={18} fill="#ffd23f">●</text>}
          {unlucky === k && <circle cx={x} cy={y - 8} r={30} fill="none" stroke={C.red} strokeWidth={5} />}
        </g>
      ))}
    </svg>
  );
};

const View: FC<WorldProps> = ({g, worldT, move, o}) => {
  const tills = Math.round(param(g, 'tills', 4));
  const s = shop(tills, param(g, 'arrivals', 0.38));
  const t = 150 + worldT * LAPSE;                                      // the shop already busy when we look
  const split = splitAt(g.prev, g.focus, move);
  const A = stats(s.many, t);
  const B = stats(s.one, t);
  // the customer (served or still waiting) for whom the line choice cost the most so far
  let unlucky = -1;
  let worst = 0;
  s.many.forEach((c, k) => {
    if (c.arrive > t || c.start < t - 40) return;
    const extra = Math.min(c.start, t) - c.arrive - (s.one[k].start - s.one[k].arrive);
    if (extra > worst) {
      worst = extra;
      unlucky = k;
    }
  });
  const show = o('unlucky') > 0.3 ? unlucky : undefined;
  return (
    <AbsoluteFill style={{background: C.night}}>
      <Store list={s.many} tills={tills} t={t} left={0} width={split} single={false} unlucky={show} />
      <Store list={s.one} tills={tills} t={t} left={split} width={1920 - split} single />
      <div style={{position: 'absolute', left: split - 2, top: 0, width: 4, height: 1080, background: C.night}} />
      {g.focus === 'right' && <div style={{position: 'absolute', left: 0, top: 0, width: split, height: 1080, background: 'rgba(5,8,20,0.45)'}} />}
      {g.focus === 'left' && <div style={{position: 'absolute', left: split, top: 0, right: 0, height: 1080, background: 'rgba(5,8,20,0.45)'}} />}
      <SideTitle text={tx('manyLines')} style={{left: 48, top: 44}} />
      <SideTitle text={tx('oneLine')} style={{left: split + 48, top: 44}} />
      <Big o={Math.max(o('wait'), o('results'))} label={tx('averageWaitShort')} value={fmt(A.average)} color={C.red} style={{left: 48, bottom: 70}} />
      <Big o={Math.max(o('wait'), o('results'))} label={tx('averageWaitShort')} value={fmt(B.average)} color={C.green} style={{left: split + 48, bottom: 70}} />
      <Big o={o('results')} label={tx('longestWait')} value={fmt(A.longest)} style={{left: 340, bottom: 70}} />
      <Big o={o('results')} label={tx('longestWait')} value={fmt(B.longest)} style={{left: split + 340, bottom: 70}} />
      {show !== undefined && show >= 0 && (
        <Panel o={o('unlucky')} style={{left: 48, top: 150, width: 420}}>
          <Label color={C.red}>{tx('slowLine')}</Label>
          <div style={{fontSize: 24, fontWeight: 700, marginTop: 6}}>
            {tx('hereWaited', {a: fmt(Math.min(s.many[show].start, t) - s.many[show].arrive), b: fmt(s.one[show].start - s.one[show].arrive)})}
          </div>
        </Panel>
      )}
      <Note>{tx('queueNote', {n: tills, x: LAPSE})}</Note>
    </AbsoluteFill>
  );
};

export const colas: World = {View};
