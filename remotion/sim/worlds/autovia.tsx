// Roadworks close a lane of a motorway. Two roads with the same cars: on top, drivers move over as soon as they see
// the sign (early merge: one long line, and cars stuck at the cones when nobody lets them in); below, both lanes are
// used to the end and the cars take turns at the cones (the zipper). Every car drives with the IDM.
import type {FC} from 'react';
import {AbsoluteFill} from 'remotion';
import {BODY, Car} from '../city';
import {C, Label, Panel} from '../hud';
import {addWords, tx} from '../i18n';
import {Big, mulberry, Note, param, SideTitle, type World, type WorldProps} from '../world';

addWords({
  earlyMerge: {es: 'Incorporación temprana', pt: 'Entrada antecipada', fr: 'Rabattement anticipé', de: 'Frühes Einfädeln', en: 'Early merge'},
  zipper: {es: 'Cremallera', pt: 'Fecho éclair', fr: 'Fermeture éclair', de: 'Reißverschluss', en: 'Zipper merge'},
  queueLength: {es: 'Longitud de la cola', pt: 'Comprimento da fila', fr: 'Longueur de la file', de: 'Staulänge', en: 'Queue length'},
  carsThrough: {es: 'Coches que han pasado', pt: 'Carros que passaram', fr: 'Voitures passées', de: 'Durchgekommene Autos', en: 'Cars through'},
  laneClosed: {es: 'Carril cerrado', pt: 'Faixa fechada', fr: 'Voie fermée', de: 'Spur gesperrt', en: 'Lane closed'},
  mergeHere: {es: 'Aquí se incorporan', pt: 'Aqui entram', fr: 'Ils s’insèrent ici', de: 'Hier wird eingefädelt', en: 'They merge here'},
  roadNote: {es: 'Simulación · los mismos coches en las dos · {n} coches por minuto', pt: 'Simulação · os mesmos carros nas duas · {n} carros por minuto', fr: 'Simulation · les mêmes voitures sur les deux · {n} voitures par minute', de: 'Simulation · dieselben Autos auf beiden · {n} Autos pro Minute', en: 'Simulation · the same cars on both · {n} cars a minute'},
});

const L = 640;                                   // metres of road
const CLOSE = 470;                               // the cones: the right lane ends here
const SIGN = 150;                                // the sign: early mergers move over from here
const DT = 1 / 30;
const SPAN = 140;
const WARM = 90;                                 // seconds driven before we look (the queue already there)
const VIEW = [120, 520];                         // the metres of road on screen: from before the sign to past the cones
const IDM = {v0: 25, T: 1.4, a: 1.4, b: 2.2, s0: 2.5};
const CAR = 4.4;
// the zipper: merging allowed in the last `from` metres; whoever lets a car in is within `reach`; the gaps accepted
const ZIP = {from: 30, reach: 25, front: 0.3, back0: 0.5, back: 0.4};

type Snap = {x: Float32Array; lane: Uint8Array; v: Float32Array; a: Float32Array; id: Int32Array; through: number};
type Road = Snap[];
const ROADS = new Map<string, Road>();

const idm = (v: number, gap: number, dv: number) => {
  const want = IDM.s0 + Math.max(0, v * IDM.T + (v * dv) / (2 * Math.sqrt(IDM.a * IDM.b)));
  return IDM.a * (1 - (v / IDM.v0) ** 4 - (want / Math.max(gap, 0.1)) ** 2);
};

export const road = (zipper: boolean, demand: number): Road => {
  const key = `${zipper}:${demand}`;
  if (ROADS.has(key)) return ROADS.get(key)!;
  const rnd = mulberry(37);
  const cars: {x: number; lane: number; v: number; a: number; id: number}[] = [];
  const out: Road = [];
  let next = 0;
  let id = 0;
  let through = 0;
  for (let step = 0; step * DT < SPAN + WARM; step++) {
    const t = step * DT;
    // arrivals: each picks a lane; when the start of both is full the car waits off screen (the queue goes on back)
    if (t >= next) {
      const want = rnd() < 0.5 ? 0 : 1;
      const lane = [want, 1 - want].find((l) => !cars.some((c) => c.lane === l && c.x < 12));
      if (lane !== undefined) {
        const lead = cars.filter((c) => c.lane === lane).sort((a, b) => a.x - b.x)[0];
        cars.push({x: 0, lane, v: lead ? Math.min(20, lead.v) : 20, a: 0, id: id++});
        next = Math.max(next, t - 30) + -Math.log(1 - rnd()) / demand;
      }
    }
    const ahead = (c: {x: number; lane: number}, lane: number) => {
      let best: (typeof cars)[number] | null = null;
      for (const o of cars) if (o !== c && o.lane === lane && o.x > c.x && (!best || o.x < best.x)) best = o;
      return best;
    };
    const behind = (x: number, lane: number) => {
      let best: (typeof cars)[number] | null = null;
      for (const o of cars) if (o.lane === lane && o.x <= x && (!best || o.x > best.x)) best = o;
      return best;
    };
    // who lets whom in: at the zipper every car reaching the last metres, one each; with early merge only the cars
    // stuck at the cones, when nobody else has let them in
    const partner = new Map<(typeof cars)[number], (typeof cars)[number]>();
    for (const o of cars) {
      if (o.lane !== 1 || (zipper ? o.x < CLOSE - ZIP.from : o.x < CLOSE - 15 || o.v > 3)) continue;
      const c = behind(o.x, 0);
      if (c && o.x - c.x < ZIP.reach && (!partner.has(c) || partner.get(c)!.x > o.x)) partner.set(c, o);
    }
    for (const c of cars) {
      const lead = ahead(c, c.lane);
      let gap = lead ? lead.x - c.x - CAR : Infinity;
      let dv = lead ? c.v - lead.v : 0;
      // the closing lane ends at the cones
      if (c.lane === 1 && CLOSE - c.x - 2 < gap) {
        gap = CLOSE - c.x - 2;
        dv = c.v;
      }
      // a car on the open lane lets in the one car on the closing lane just ahead of it
      const o = partner.get(c);
      if (o && o.x - c.x - CAR < gap) {
        gap = Math.max(0.5, o.x - c.x - CAR);
        dv = c.v - o.v;
      }
      c.a = idm(c.v, gap, dv);
    }
    for (const c of cars) {
      c.v = Math.max(0, c.v + c.a * DT);
      c.x += c.v * DT;
    }
    // changing lanes: early mergers from the sign on, zipper only at the cones
    for (const c of cars) {
      if (c.lane !== 1) continue;
      const allowed = zipper ? c.x > CLOSE - ZIP.from : c.x > SIGN;
      const stuck = zipper || (c.x > CLOSE - 15 && c.v < 3);
      if (!allowed) continue;
      const front = ahead({x: c.x - 0.01, lane: 0}, 0);
      const back = behind(c.x, 0);
      // the early mergers move over only into a comfortable gap; those who reach the cones stop and squeeze in when
      // someone lets them — at the zipper the open lane makes room for everyone and a short gap is enough
      const okFront = !front || front.x - c.x - CAR > IDM.s0 + c.v * (stuck ? ZIP.front : 0.9);
      const okBack = !back || c.x - back.x - CAR > (stuck ? ZIP.back0 : IDM.s0) + back.v * (stuck ? ZIP.back : 1.3);
      if (okFront && okBack) {
        c.lane = 0;
      }
    }
    for (let k = cars.length - 1; k >= 0; k--) {
      if (cars[k].x > L) {
        cars.splice(k, 1);
        if (t >= WARM) through++;
      }
    }
    if (t >= WARM && step % 1 === 0) {
      out.push({x: Float32Array.from(cars.map((c) => c.x)), lane: Uint8Array.from(cars.map((c) => c.lane)), v: Float32Array.from(cars.map((c) => c.v)),
                a: Float32Array.from(cars.map((c) => c.a)), id: Int32Array.from(cars.map((c) => c.id)), through});
    }
  }
  ROADS.set(key, out);
  return out;
};

/** How far back from the cones the line of slow cars reaches (metres). */
export const queue = (s: Snap) => {
  let far = CLOSE;
  for (let k = 0; k < s.x.length; k++) if (s.v[k] < 8 && s.x[k] < CLOSE && s.x[k] < far) far = s.x[k];
  return CLOSE - far;
};

const Highway: FC<{s: Snap; top: number; scale: number; mark: number}> = ({s, top, scale, mark}) => {
  const m = 1920 / (VIEW[1] - VIEW[0]);
  const px = (x: number) => (x - VIEW[0]) * m;
  const lane = 40 * scale;
  const laneY = (l: number) => top + (l === 0 ? -lane / 2 : lane / 2);
  const q = queue(s);
  return (
    <g>
      <rect x={0} y={top - lane * 1.4} width={1920} height={lane * 2.8} fill="#4a6e3f" />
      <rect x={0} y={top - lane} width={px(CLOSE + 25)} height={lane * 2} fill="#33363c" />
      <rect x={px(CLOSE + 25)} y={top - lane} width={1920} height={lane} fill="#33363c" />
      <line x1={0} y1={top} x2={px(CLOSE)} y2={top} stroke="#f2f2f2" strokeWidth={3} strokeDasharray="22 22" />
      <line x1={0} y1={top - lane} x2={1920} y2={top - lane} stroke="#f2f2f2" strokeWidth={3} />
      <line x1={0} y1={top + lane} x2={px(CLOSE + 25)} y2={top + lane} stroke="#f2f2f2" strokeWidth={3} />
      {Array.from({length: 9}, (_, i) => {
        const x = px(CLOSE - 10 + i * 4);
        const y = top + lane * (0.9 - i * 0.1);
        return <path key={i} d={`M${x},${y - 9} L${x + 7},${y + 7} L${x - 7},${y + 7} Z`} fill="#ff8c1a" stroke="#ffffff" strokeWidth={1.5} />;
      })}
      <rect x={px(SIGN) - 26} y={top + lane + 6} width={52} height={34} rx={4} fill="#f5b324" stroke="#1a1f29" strokeWidth={2} />
      <text x={px(SIGN)} y={top + lane + 30} textAnchor="middle" fontSize={22} fontWeight={800} fill="#1a1f29">⇤</text>
      {mark > 0 && q > 5 && (
        <g opacity={mark}>
          <line x1={px(CLOSE - q)} y1={top - lane - 14} x2={px(CLOSE)} y2={top - lane - 14} stroke={C.red} strokeWidth={5} />
          <line x1={px(CLOSE - q)} y1={top - lane - 24} x2={px(CLOSE - q)} y2={top - lane - 4} stroke={C.red} strokeWidth={5} />
        </g>
      )}
      {Array.from(s.x).map((x, k) => {
        const braking = Math.min(1, Math.max(0, -s.a[k] - 0.3) / 1.5) || (s.v[k] < 1 ? 1 : 0);
        return <Car key={s.id[k]} sx={px(x)} sy={laneY(s.lane[k])} deg={0} s={m * 1.35 * Math.min(1.15, scale)} color={BODY[s.id[k] % BODY.length]} brake={braking} />;
      })}
    </g>
  );
};

const View: FC<WorldProps> = ({g, worldT, move, o}) => {
  const demand = param(g, 'demand', 0.55);
  const early = road(false, demand);
  const zip = road(true, demand);
  const f = Math.max(0, Math.min(early.length - 1, zip.length - 1, Math.round(worldT * 30)));
  const share = (focus: string) => (focus === 'top' ? 0.62 : focus === 'bottom' ? 0.38 : 0.5);
  const s = share(g.prev) + (share(g.focus) - share(g.prev)) * move;
  const scale = (focus: string, mine: string) => (focus === mine ? 1.25 : focus === 'both' ? 1 : 0.85);
  const a = early[f];
  const b = zip[f];
  const qShow = Math.max(o('queue'), o('results'));
  return (
    <AbsoluteFill style={{background: '#3c5a36'}}>
      <svg width={1920} height={1080} style={{position: 'absolute'}}>
        <Highway s={a} top={1080 * s * 0.55} scale={scale(g.focus, 'top')} mark={qShow} />
        <Highway s={b} top={1080 * s + 1080 * (1 - s) * 0.5} scale={scale(g.focus, 'bottom')} mark={qShow} />
        {o('merge') > 0 && [1080 * s * 0.55, 1080 * s + 1080 * (1 - s) * 0.5].map((y, i) => (
          <g key={i} opacity={o('merge')}>
            <circle cx={((i ? CLOSE - 12 : SIGN + 40) - VIEW[0]) * (1920 / (VIEW[1] - VIEW[0]))} cy={y} r={60} fill="none" stroke={C.accent} strokeWidth={4} />
          </g>
        ))}
      </svg>
      <SideTitle text={tx('earlyMerge')} style={{left: 48, top: Math.max(30, 1080 * s * 0.55 - 150)}} />
      <SideTitle text={tx('zipper')} style={{left: 48, top: 1080 * s + 1080 * (1 - s) * 0.5 - 150}} />
      <Panel o={qShow} style={{right: 48, top: 52, width: 360}}>
        <Label>{tx('queueLength')}</Label>
        <div style={{display: 'flex', justifyContent: 'space-between', fontSize: 34, fontWeight: 800, marginTop: 6}}>
          <span style={{color: C.red}}>↑ {Math.round(queue(a))} m</span><span style={{color: C.green}}>↓ {Math.round(queue(b))} m</span>
        </div>
      </Panel>
      <Big o={o('results')} label={tx('carsThrough')} value={`${a.through} · ${b.through}`} style={{right: 48, bottom: 70, width: 360}} />
      <Panel o={o('merge')} style={{left: '50%', bottom: 70, transform: 'translateX(-50%)'}}>
        <div style={{fontSize: 30, fontWeight: 800, textTransform: 'uppercase'}}>{tx('mergeHere')}</div>
      </Panel>
      <Note>{tx('roadNote', {n: Math.round(demand * 60)})}</Note>
    </AbsoluteFill>
  );
};

export const autovia: World = {View};
