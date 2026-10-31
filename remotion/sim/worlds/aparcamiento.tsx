// A car park seen from above (remotion/sim/park.ts): cars come in, drive the aisles in order and take the first free
// space; parked cars leave after a while. Scenes:
//  buscar     one car park kept `ocupacion` full: the cars still looking (red, with their search time), YOU in yellow
//  ocupacion  the curve: mean time to find a space against how full the car park is — flat, then a wall past ~85 %
//             (Donald Shoup: price parking so ~1 space in 7 stays free)
//  comparar   the same car park at 70 % (left) and at 95 % (right), side by side
import type {FC} from 'react';
import {AbsoluteFill} from 'remotion';
import {C, FONT, Label, Panel} from '../hud';
import {Car, kindOf, BODY} from '../city';
import {addWords, num, tx} from '../i18n';
import {Pointers, type Anchor} from '../look';
import {CURVE, PARK, ROUTE, SPACES, runPark, searchAt, type ParkRun} from '../park';
import {Big, Note, param, SideTitle, type World, type WorldProps} from '../world';

addWords({
  searching: {es: 'Buscando sitio', pt: 'Procurando vaga', fr: 'Cherchent une place', de: 'Suchen einen Platz', en: 'Looking for a space'},
  searchTime: {es: 'Tiempo medio buscando', pt: 'Tempo médio procurando', fr: 'Temps moyen de recherche', de: 'Mittlere Suchzeit', en: 'Average search time'},
  full: {es: 'Lleno al {p} %', pt: 'Cheio a {p} %', fr: 'Plein à {p} %', de: 'Zu {p} % voll', en: '{p} % full'},
  howFull: {es: 'Lo lleno que está', pt: 'Quão cheio está', fr: 'Taux de remplissage', de: 'Wie voll', en: 'How full it is'},
  searchCurve: {es: 'Tiempo buscando sitio según lo lleno que está', pt: 'Tempo procurando vaga conforme a ocupação', fr: 'Temps de recherche selon le remplissage', de: 'Suchzeit je nach Belegung', en: 'Time to find a space by how full it is'},
  entrance: {es: 'Entrada', pt: 'Entrada', fr: 'Entrée', de: 'Einfahrt', en: 'Entrance'},
  parkNote: {es: 'Simulación · {n} plazas · cada coche coge la primera libre que ve · se van al cabo de un rato · tiempo ×{x}', pt: 'Simulação · {n} vagas · cada carro pega a primeira livre que vê · saem depois de um tempo · tempo ×{x}', fr: 'Simulation · {n} places · chaque voiture prend la première libre · elles repartent au bout d’un moment · temps ×{x}', de: 'Simulation · {n} Plätze · jedes Auto nimmt den ersten freien · sie fahren nach einer Weile · Zeit ×{x}', en: 'Simulation · {n} spaces · each car takes the first free one it sees · they leave after a while · time ×{x}'},
});

const LAPSE = 3;
const FROM = 900;
const fmt = (s: number) => (s < 60 ? `${Math.round(s)} s` : `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, '0')} min`);

/** Where along the route → a point on the screen: aisles left to right, driven down and up in turn. */
const geometry = (left: number, width: number) => {
  const aisleW = (width - 120) / PARK.aisles;
  const top = 240;
  const len = 720;
  const slotPx = len / PARK.perSide;
  const seg = PARK.perSide * PARK.slot + PARK.turn;
  const point = (d: number): [number, number, number] => {
    if (d >= ROUTE) {                                      // back along the bottom to the entrance
      const k = (d - ROUTE) / PARK.back;
      return [left + 60 + aisleW * (PARK.aisles - 0.5) * (1 - k), top + len + 50, 180];
    }
    const a = Math.floor(d / seg);
    const inA = d - a * seg;
    const x = left + 60 + aisleW * (a + 0.5);
    const down = a % 2 === 0;
    if (inA <= PARK.perSide * PARK.slot) {
      const yy = (inA / (PARK.perSide * PARK.slot)) * len;
      return [x, down ? top + yy : top + len - yy, down ? 90 : -90];
    }
    const k = (inA - PARK.perSide * PARK.slot) / PARK.turn;          // the turn into the next aisle
    return [x + aisleW * k, down ? top + len + 30 : top - 30, 0];
  };
  const space = (i: number): [number, number, number] => {
    const a = Math.floor(i / (PARK.perSide * 2));
    const side = i % 2 ? 1 : -1;
    const k = Math.floor((i % (PARK.perSide * 2)) / 2);
    const down = a % 2 === 0;
    const yy = (k + 0.5) * slotPx;
    return [left + 60 + aisleW * (a + 0.5) + side * aisleW * 0.3, down ? top + yy : top + len - yy, 0];
  };
  return {point, space, aisleW, top, len, slotPx};
};

const Lot: FC<{run: ParkRun; t: number; left: number; width: number; you?: number}> = ({run, t, left, width, you}) => {
  const f = run.at(t);
  const {point, space, aisleW, top, len, slotPx} = geometry(left, width);
  const s = Math.min(slotPx / 2.6, aisleW * 0.38 / 4.6);
  const searching = new Map(run.searches.map((c) => [c.id, c]));
  return (
    <svg width={1920} height={1080} style={{position: 'absolute', clipPath: `inset(0 ${1920 - left - width}px 0 ${left}px)`}}>
      <rect x={left} y={0} width={width} height={1080} fill="#4a5a3f" />
      <rect x={left + 40} y={top - 70} width={width - 80} height={len + 160} rx={10} fill="#3b3f46" />
      {Array.from({length: SPACES}, (_, i) => {
        const [x, y] = space(i);
        const side = i % 2 ? 1 : -1;
        return (
          <g key={i}>
            <line x1={x - side * aisleW * 0.18} x2={x + side * aisleW * 0.18} y1={y - slotPx / 2} y2={y - slotPx / 2} stroke="rgba(255,255,255,0.55)" strokeWidth={2} />
            {f.taken[i] ? <Car sx={x} sy={y} deg={0} s={s} color={BODY[(i * 7) % BODY.length]} brake={0} kind={kindOf(i)} /> : null}
          </g>
        );
      })}
      {Array.from({length: PARK.aisles}, (_, a) => (
        <text key={a} x={left + 60 + aisleW * (a + 0.5)} y={a % 2 === 0 ? top - 40 : top + len + 70} textAnchor="middle" fill="rgba(255,255,255,0.5)"
              fontFamily={FONT} fontSize={40} fontWeight={800}>{a % 2 === 0 ? '↓' : '↑'}</text>
      ))}
      <text x={left + 60 + aisleW * 0.5} y={top - 80} textAnchor="middle" fill="#fff" fontFamily={FONT} fontSize={28} fontWeight={800}>
        ▼ {tx('entrance').toUpperCase()}
      </text>
      {f.cars.map((car) => {
        const [x, y, deg] = point(car.d);
        const done = searching.get(car.id);
        const mine = car.id === you;
        const looking = done ? t - done.arrive : 0;
        return (
          <g key={car.id}>
            <Car sx={x} sy={y} deg={deg} s={s} color={mine ? C.you : C.red} brake={0} kind={kindOf(car.id)} mark={mine ? C.you : undefined} />
            {looking > 20 && (
              <text x={x + 26} y={y - 18} fill={mine ? C.you : '#ffd0cb'} fontFamily={FONT} fontSize={24} fontWeight={800}>{fmt(looking)}</text>
            )}
          </g>
        );
      })}
    </svg>
  );
};

/** The car to follow as YOU: one that arrives soon after the shot starts and has to look for a while. */
const yours = (run: ParkRun, t: number) => {
  const c = run.searches.find((x) => x.arrive > t + 2 && x.done - x.arrive > 25) ?? run.searches.find((x) => x.arrive > t);
  return c?.id;
};

const Curve: FC<{o: number; full: number; real: number}> = ({o, full, real}) => {
  const W = 1180;
  const H = 520;
  const max = 180;
  const X = (p: number) => ((p - 0.45) / 0.55) * W;
  const Y = (s: number) => H - (Math.min(max, s) / max) * H;
  const grow = Math.min(1, real / 2.5);
  const pts = CURVE.filter(([p]) => X(p) <= W * grow + 1).map(([p, s]) => `${X(p)},${Y(s)}`).join(' ');
  return (
    <Panel o={o} style={{left: '50%', top: 150, transform: 'translateX(-50%)', width: W + 80, padding: '24px 40px'}}>
      <Label>{tx('searchCurve')}</Label>
      <svg width={W} height={H + 50} viewBox={`-110 0 ${W + 110} ${H + 50}`} style={{display: 'block', marginTop: 16, overflow: 'visible'}}>
        <rect x={X(0.85)} y={0} width={W - X(0.85)} height={H} fill="rgba(255,93,93,0.12)" />
        <line x1={X(0.85)} x2={X(0.85)} y1={0} y2={H} stroke={C.red} strokeWidth={3} strokeDasharray="8 8" />
        <text x={X(0.85) + 10} y={30} fill={C.red} fontFamily={FONT} fontSize={30} fontWeight={800}>85 %</text>
        {[0.5, 0.6, 0.7, 0.8, 0.9, 1].map((p) => (
          <text key={p} x={X(p)} y={H + 40} textAnchor="middle" fill={C.label} fontFamily={FONT} fontSize={26}>{Math.round(p * 100)} %</text>
        ))}
        {[60, 120, 180].map((s) => <text key={s} x={-12} y={Y(s) + 8} textAnchor="end" fill={C.label} fontFamily={FONT} fontSize={24}>{fmt(s)}</text>)}
        <polyline points={pts} fill="none" stroke={C.accent} strokeWidth={6} strokeLinejoin="round" />
        {grow >= 1 && <circle cx={X(full)} cy={Y(searchAt(full))} r={12} fill={C.you} stroke="#0b1020" strokeWidth={3} />}
      </svg>
    </Panel>
  );
};

const View: FC<WorldProps> = ({g, worldT, local, real = local, o, on}) => {
  const scene = param<string>(g, 'scene', 'buscar');
  const full = param(g, 'ocupacion', 0.9);
  const panel = Math.max(o('panel'), on * 0.9);
  const t = FROM + worldT * LAPSE;
  const marks: Record<string, Anchor | null> = {};
  let body;
  if (scene === 'comparar') {
    const a = runPark(0.7);
    const b = runPark(0.98);
    body = (
      <>
        <Lot run={a} t={t} left={0} width={958} />
        <Lot run={b} t={t} left={962} width={958} />
        <div style={{position: 'absolute', left: 958, top: 0, width: 4, height: 1080, background: C.night}} />
        <SideTitle text={tx('full', {p: 70})} style={{left: 48, top: 30}} />
        <SideTitle text={tx('full', {p: 95})} style={{left: 1010, top: 30}} />
        <Big o={panel} label={tx('searchTime')} value={fmt(searchAt(0.7))} color={C.green} style={{left: 48, bottom: 60, width: 300}} />
        <Big o={panel} label={tx('searchTime')} value={fmt(searchAt(0.955))} color={C.red} style={{left: 1010, bottom: 60, width: 300}} />
      </>
    );
  } else {
    const run = runPark(full >= 0.95 ? 0.98 : full >= 0.85 ? 0.9 : full);     // the drawn car park as full as asked
    const you = yours(run, FROM + (g.at - g.since) * LAPSE);
    const car = run.at(t).cars.find((c) => c.id === you);
    if (car) {
      const [x, y] = geometry(0, 1920).point(car.d);
      marks.you = {x, y};
    }
    body = (
      <>
        <Lot run={run} t={t} left={0} width={1920} you={you} />
        {scene === 'ocupacion' && <AbsoluteFill style={{background: 'rgba(5,8,15,0.55)'}} />}
        {scene === 'ocupacion' ? <Curve o={on} full={full} real={real} /> : (
          <Panel o={panel} style={{right: 64, top: 52, width: 340}}>
            <Label>{tx('searchTime')}</Label>
            <div style={{fontSize: 56, fontWeight: 800, color: searchAt(full) > 60 ? C.red : C.text}}>{fmt(searchAt(full))}</div>
            <Label>{tx('howFull')}: {Math.round(full * 100)} %</Label>
            <Label>{tx('searching')}: {num(run.at(t).cars.length)}</Label>
          </Panel>
        )}
      </>
    );
  }
  return (
    <AbsoluteFill style={{background: C.night}}>
      {body}
      <Pointers marks={g.marks} local={real} at={marks} />
      <Note>{tx('parkNote', {n: SPACES, x: LAPSE})}</Note>
    </AbsoluteFill>
  );
};

export const aparcamiento: World = {View};
