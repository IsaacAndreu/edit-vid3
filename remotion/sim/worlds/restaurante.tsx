// A restaurant kitchen at dinner time seen from above (remotion/sim/kitchen.ts): the ticket rail with the orders
// waiting, the cooks at their stations with the dish on the fire (a ring: how much is left), the pass where plates go
// out. Scenes:
//  comandas  one kitchen with its cooks `ocupacion` busy: the rail fills, the time from order to plate grows — at 90 %
//            it is not 10 % worse than at 80 %, it is almost double (Kingman, as at the tills)
//  orden     the same orders, left first come first cooked (the rail in order), right the quickest dish first: the
//            mean time drops, but the slow dishes wait and wait (the longest ticket, hours)
import type {FC} from 'react';
import {AbsoluteFill} from 'remotion';
import {C, FONT, Label, Panel} from '../hud';
import {addWords, num, tx} from '../i18n';
import {kitchenLong, runKitchen, type KitchenRun} from '../kitchen';
import {Pointers, type Anchor} from '../look';
import {Big, Note, param, SideTitle, type World, type WorldProps} from '../world';

addWords({
  ticketTime: {es: 'De la comanda al plato', pt: 'Do pedido ao prato', fr: 'De la commande à l’assiette', de: 'Von der Bestellung zum Teller', en: 'From order to plate'},
  onRail: {es: 'Comandas esperando', pt: 'Pedidos esperando', fr: 'Bons en attente', de: 'Wartende Bons', en: 'Tickets waiting'},
  inOrder: {es: 'Por orden de llegada', pt: 'Por ordem de chegada', fr: 'Dans l’ordre d’arrivée', de: 'Der Reihe nach', en: 'In the order they came'},
  quickFirst: {es: 'Lo rápido primero', pt: 'O rápido primeiro', fr: 'Le plus rapide d’abord', de: 'Das Schnelle zuerst', en: 'Quickest dish first'},
  slowestTicket: {es: 'La comanda que más espera', pt: 'O pedido que mais espera', fr: 'Le bon qui attend le plus', de: 'Der Bon, der am längsten wartet', en: 'The longest ticket'},
  busyCooks: {es: 'Cocineros ocupados el {p} %', pt: 'Cozinheiros ocupados {p} %', fr: 'Cuisiniers occupés {p} %', de: 'Köche zu {p} % beschäftigt', en: 'Cooks busy {p} %'},
  pass: {es: 'Pase', pt: 'Passe', fr: 'Passe', de: 'Pass', en: 'Pass'},
  kitchenNote: {es: 'Simulación · {n} cocineros · entrante ≈ 4 min, pasta ≈ 9, carne ≈ 15 · tiempo ×{x}', pt: 'Simulação · {n} cozinheiros · entrada ≈ 4 min, massa ≈ 9, carne ≈ 15 · tempo ×{x}', fr: 'Simulation · {n} cuisiniers · entrée ≈ 4 min, pâtes ≈ 9, viande ≈ 15 · temps ×{x}', de: 'Simulation · {n} Köche · Vorspeise ≈ 4 min, Pasta ≈ 9, Fleisch ≈ 15 · Zeit ×{x}', en: 'Simulation · {n} cooks · starter ≈ 4 min, pasta ≈ 9, steak ≈ 15 · time ×{x}'},
});

const COOKS = 3;
const LAPSE = 20;                                     // a busy evening in a few minutes of video
const FROM = 3600;
const DISH = ['#7bc96f', '#f2c14e', '#b5523b'];       // starter, pasta, steak
const mins = (s: number) => (s < 5400 ? `${Math.round(s / 60)} min` : `${Math.floor(s / 3600)} h ${String(Math.round((s % 3600) / 60)).padStart(2, '0')}`);

const Kitchen: FC<{run: KitchenRun; t: number; left: number; width: number}> = ({run, t, left, width}) => {
  const f = run.at(t);
  const byId = new Map(run.tickets.map((x) => [x.id, x]));
  const cx = left + width / 2;
  const gap = Math.min(260, (width - 140) / run.cooks);
  const stationX = (k: number) => cx + (k - (run.cooks - 1) / 2) * gap;
  const shown = f.rail.slice(0, Math.floor((width - 120) / 46) * 2);
  const perRow = Math.floor((width - 120) / 46);
  return (
    <svg width={1920} height={1080} style={{position: 'absolute', clipPath: `inset(0 ${1920 - left - width}px 0 ${left}px)`}}>
      <rect x={left} y={0} width={width} height={1080} fill="#c8c3b8" />
      {Array.from({length: Math.ceil(width / 60) + 1}, (_, i) => <line key={i} x1={left + i * 60} x2={left + i * 60} y1={0} y2={1080} stroke="rgba(0,0,0,0.07)" strokeWidth={2} />)}
      {Array.from({length: 19}, (_, i) => <line key={`y${i}`} x1={left} x2={left + width} y1={i * 60} y2={i * 60} stroke="rgba(0,0,0,0.07)" strokeWidth={2} />)}
      {/* the ticket rail, the orders waiting in their order */}
      <rect x={left + 40} y={140} width={width - 80} height={150} rx={6} fill="#5b6470" />
      <rect x={left + 40} y={140} width={width - 80} height={10} fill="#8a939e" />
      {shown.map((id, i) => {
        const x = left + 60 + (i % perRow) * 46;
        const y = 160 + Math.floor(i / perRow) * 64;
        const d = byId.get(id)!;
        const old = (t - d.arrive) / 1800;
        return (
          <g key={id} transform={`rotate(${((id * 37) % 7) - 3} ${x + 18} ${y})`}>
            <rect x={x} y={y} width={36} height={54} rx={2} fill={old > 1 ? '#ffd0cb' : '#fbf8f1'} stroke="rgba(0,0,0,0.25)" />
            <rect x={x + 6} y={y + 8} width={24} height={6} fill={DISH[d.dish]} />
            {[22, 30, 38].map((yy) => <line key={yy} x1={x + 6} x2={x + 30} y1={y + yy} y2={y + yy} stroke="rgba(0,0,0,0.25)" strokeWidth={2} />)}
          </g>
        );
      })}
      {f.rail.length > shown.length && (
        <text x={left + width - 60} y={310} textAnchor="end" fill={C.red} fontFamily={FONT} fontSize={30} fontWeight={800}>+{f.rail.length - shown.length}</text>
      )}
      {/* the stations: a range with its fire, the cook, the dish */}
      {Array.from({length: run.cooks}, (_, k) => {
        const x = stationX(k);
        const id = f.cooking[k];
        const d = id >= 0 ? byId.get(id)! : undefined;
        const done = d ? 1 - f.left[k] / d.cook : 0;
        return (
          <g key={k}>
            <rect x={x - 100} y={400} width={200} height={170} rx={8} fill="#3a3f46" stroke="#22262c" strokeWidth={4} />
            {[[-50, 445], [50, 445], [-50, 525], [50, 525]].map(([dx, dy], j) => (
              <circle key={j} cx={x + dx} cy={dy} r={30} fill="none" stroke={d && j === 0 ? '#ff7a2f' : '#555b63'} strokeWidth={6} opacity={d && j === 0 ? 0.6 + 0.4 * Math.sin(t / 3 + k) : 1} />
            ))}
            {d && (
              <g>
                <circle cx={x - 50} cy={445} r={22} fill={DISH[d.dish]} />
                <circle cx={x - 50} cy={445} r={36} fill="none" stroke="rgba(255,255,255,0.2)" strokeWidth={6} />
                <circle cx={x - 50} cy={445} r={36} fill="none" stroke={C.green} strokeWidth={6} strokeDasharray={`${2 * Math.PI * 36}`}
                        strokeDashoffset={`${2 * Math.PI * 36 * (1 - done)}`} transform={`rotate(-90 ${x - 50} 445)`} />
              </g>
            )}
            <g transform={`translate(${x} ${630})`}>
              <ellipse rx={26} ry={17} fill="#f4f4f2" stroke="rgba(0,0,0,0.35)" strokeWidth={2} />
              <circle r={12} fill="#f4f4f2" stroke="rgba(0,0,0,0.25)" />
              <circle cy={4} r={7} fill="#e8c4a0" />
            </g>
          </g>
        );
      })}
      {/* the pass: plates going out */}
      <rect x={left + 60} y={760} width={width - 120} height={70} rx={6} fill="#b9bec6" stroke="#8a919b" strokeWidth={3} />
      <text x={left + 80} y={810} fill="#4c535e" fontFamily={FONT} fontSize={30} fontWeight={800}>{tx('pass').toUpperCase()}</text>
      {Array.from({length: Math.min(8, f.served % 9)}, (_, j) => (
        <g key={j}>
          <circle cx={left + 220 + j * 70} cy={795} r={26} fill="#fff" stroke="#c9ced6" strokeWidth={3} />
          <circle cx={left + 220 + j * 70} cy={795} r={13} fill={DISH[(f.served + j) % 3]} />
        </g>
      ))}
    </svg>
  );
};

const View: FC<WorldProps> = ({g, worldT, local, real = local, o, on}) => {
  const scene = param<string>(g, 'scene', 'comandas');
  const load = param(g, 'ocupacion', 0.9);
  const panel = Math.max(o('panel'), on * 0.9);
  const t = FROM + worldT * LAPSE;
  const marks: Record<string, Anchor | null> = {rail: {x: 960, y: 215}};
  let body;
  if (scene === 'orden') {
    const a = runKitchen(COOKS, 0.9, 'fifo');
    const b = runKitchen(COOKS, 0.9, 'quick');
    const la = kitchenLong(COOKS, 0.9, 'fifo');
    const lb = kitchenLong(COOKS, 0.9, 'quick');
    body = (
      <>
        <Kitchen run={a} t={t} left={0} width={958} />
        <Kitchen run={b} t={t} left={962} width={958} />
        <div style={{position: 'absolute', left: 958, top: 0, width: 4, height: 1080, background: C.night}} />
        <SideTitle text={tx('inOrder')} style={{left: 48, top: 40}} />
        <SideTitle text={tx('quickFirst')} style={{left: 1010, top: 40}} />
        <Big o={panel} label={tx('ticketTime')} value={mins(la.mean)} color={C.text} sub={`${tx('slowestTicket')}: ${mins(la.longest)}`}
             style={{left: 48, bottom: 60, width: 380}} />
        <Big o={panel} label={tx('ticketTime')} value={mins(lb.mean)} color={C.green} sub={`${tx('slowestTicket')}: ${mins(lb.longest)}`}
             style={{left: 1010, bottom: 60, width: 380}} />
      </>
    );
  } else {
    const run = runKitchen(COOKS, load, 'fifo');
    const long = kitchenLong(COOKS, load, 'fifo');
    body = (
      <>
        <Kitchen run={run} t={t} left={0} width={1920} />
        <Panel o={panel} style={{right: 64, bottom: 60, width: 400}}>
          <Label>{tx('ticketTime')}</Label>
          <div style={{fontSize: 56, fontWeight: 800, color: long.mean > 1500 ? C.red : C.text}}>{mins(long.mean)}</div>
          <Label>{tx('busyCooks', {p: Math.round(load * 100)})}</Label>
          <Label>{tx('onRail')}: {num(run.at(t).rail.length)}</Label>
        </Panel>
      </>
    );
  }
  return (
    <AbsoluteFill style={{background: C.night}}>
      {body}
      <Pointers marks={g.marks} local={real} at={marks} />
      <Note>{tx('kitchenNote', {n: COOKS, x: LAPSE})}</Note>
    </AbsoluteFill>
  );
};

export const restaurante: World = {View, ambient: 'kitchen'};
