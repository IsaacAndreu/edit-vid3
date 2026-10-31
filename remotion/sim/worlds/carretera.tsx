// A straight road seen from above, on a dark field: the scenes a traffic script needs beyond the ring (road.ts).
//  frenazo   eight cars, the first taps the brake; each driver reacts late and brakes harder (bars over each car);
//            with who: acc, the same line as new cars on adaptive cruise control
//  onda      a busy road: the cars go right, the jam goes left (arrows, its speed); panel: why it lasts (what gets
//            out of the jam, what a clear road carries, what is arriving)
//  carril    two lanes, YOU in one: you pass four cars quickly, four cars take long to pass you (Redelmeier, 1999)
//  hueco     YOU leave a gap and roll at a steady speed instead of stopping: the queue melts before you get there
//  limite    gantries lower the limit before the waves: the cars arrive slowly, fewer stop
//  carriles  a third lane appears and fills up again (panel: lane kilometres and kilometres driven, +10 %)
//  rampa     the same busy road twice with an on-ramp: above, the cars squeeze in as they come and waves start; below,
//            a light on the ramp lets one in at a time and the road keeps moving (panel: cars an hour, stopped)
import type {FC, ReactElement} from 'react';
import {AbsoluteFill} from 'remotion';
import {Car, CITY} from '../city';
import {Fields, Roadside} from '../scenery';
import {paint, Pointers, trail, type Anchor} from '../look';
import {C, FONT, Label, Panel} from '../hud';
import {addWords, tx} from '../i18n';
import {PLATOON, RAMP, ROAD, VARIANT, capacity, jamOf, laneTimes, platoon, ramp, road, type Frame} from '../road';
import {Note, param, type World, type WorldProps} from '../world';

addWords({
  howHard: {es: 'Lo fuerte que frenó cada uno', pt: 'Com que força travou cada um', fr: 'La force du freinage de chacun', de: 'Wie stark jeder bremste', en: 'How hard each driver braked'},
  harderEach: {es: 'Cada uno frenó más fuerte que el de delante', pt: 'Cada um travou mais forte do que o da frente', fr: 'Chacun a freiné plus fort que celui de devant', de: 'Jeder bremste stärker als der vor ihm', en: 'Each one braked harder than the car ahead'},
  cruise: {es: 'Coches nuevos con control de crucero', pt: 'Carros novos com cruise control', fr: 'Voitures neuves avec régulateur adaptatif', de: 'Neue Autos mit Abstandstempomat', en: 'New cars on adaptive cruise control'},
  eachSpeed: {es: 'Velocidad de cada coche', pt: 'Velocidade de cada carro', fr: 'Vitesse de chaque voiture', de: 'Tempo jedes Autos', en: 'Each car’s speed'},
  theCars: {es: 'Los coches', pt: 'Os carros', fr: 'Les voitures', de: 'Die Autos', en: 'The cars'},
  theJam: {es: 'El atasco · unos {v} km/h', pt: 'O engarrafamento · cerca de {v} km/h', fr: 'Le bouchon · environ {v} km/h', de: 'Der Stau · etwa {v} km/h', en: 'The jam · about {v} km/h'},
  outOfJam: {es: 'Lo que sale del atasco', pt: 'O que sai do engarrafamento', fr: 'Ce qui sort du bouchon', de: 'Was aus dem Stau herauskommt', en: 'What gets out of the jam'},
  clearRoad: {es: 'Lo que lleva una carretera libre', pt: 'O que leva uma estrada livre', fr: 'Ce que porte une route dégagée', de: 'Was eine freie Straße schafft', en: 'What a clear road carries'},
  arriving: {es: 'Lo que está llegando', pt: 'O que está a chegar', fr: 'Ce qui arrive', de: 'Was gerade ankommt', en: 'What is arriving'},
  perHourShort: {es: '{n}/h', pt: '{n}/h', fr: '{n}/h', de: '{n}/h', en: '{n}/h'},
  you: {es: 'Tú', pt: 'Tu', fr: 'Vous', de: 'Du', en: 'You'},
  passFour: {es: 'Adelantas a 4 coches', pt: 'Ultrapassas 4 carros', fr: 'Vous doublez 4 voitures', de: 'Du überholst 4 Autos', en: 'You pass four cars'},
  passedFour: {es: '4 coches te adelantan', pt: '4 carros ultrapassam-te', fr: '4 voitures vous doublent', de: '4 Autos überholen dich', en: 'Four cars pass you'},
  sameSpeed: {es: 'Los dos carriles, la misma velocidad media', pt: 'As duas faixas, a mesma velocidade média', fr: 'Les deux voies, même vitesse moyenne', de: 'Beide Spuren, gleiches Durchschnittstempo', en: 'Both lanes, the same average speed'},
  theGap: {es: 'El hueco', pt: 'O espaço', fr: 'L’espace', de: 'Die Lücke', en: 'The gap'},
  stillRolling: {es: '{v} km/h · sigue rodando', pt: '{v} km/h · continua a andar', fr: '{v} km/h · roule encore', de: '{v} km/h · rollt weiter', en: '{v} km/h · still rolling'},
  nStoppedRoad: {es: '{n} parados', pt: '{n} parados', fr: '{n} à l’arrêt', de: '{n} stehen', en: '{n} stopped'},
  stoppedBehind: {es: 'Parados ahora', pt: 'Parados agora', fr: 'À l’arrêt', de: 'Stehen gerade', en: 'Stopped now'},
  withoutGap: {es: 'sin dejar hueco: {n}', pt: 'sem deixar espaço: {n}', fr: 'sans espace : {n}', de: 'ohne Lücke: {n}', en: 'without the gap: {n}'},
  arriveSlowly: {es: 'Llegan despacio', pt: 'Chegam devagar', fr: 'Ils arrivent lentement', de: 'Sie kommen langsam an', en: 'Arriving slowly'},
  withoutSigns: {es: 'Sin paneles', pt: 'Sem painéis', fr: 'Sans panneaux', de: 'Ohne Anzeigen', en: 'Without the signs'},
  withSigns: {es: 'Con paneles', pt: 'Com painéis', fr: 'Avec panneaux', de: 'Mit Anzeigen', en: 'With the signs'},
  newLane: {es: 'El carril nuevo', pt: 'A faixa nova', fr: 'La nouvelle voie', de: 'Die neue Spur', en: 'The new lane'},
  laneKm: {es: 'Kilómetros de carril', pt: 'Quilómetros de faixa', fr: 'Kilomètres de voie', de: 'Spurkilometer', en: 'Lane kilometres'},
  kmDriven: {es: 'Kilómetros recorridos', pt: 'Quilómetros percorridos', fr: 'Kilomètres parcourus', de: 'Gefahrene Kilometer', en: 'Kilometres driven'},
  roadNote: {es: 'Simulación con el modelo de conductor inteligente (IDM) · {n} coches por km', pt: 'Simulação com o modelo do condutor inteligente (IDM) · {n} carros por km', fr: 'Simulation avec le modèle du conducteur intelligent (IDM) · {n} voitures par km', de: 'Simulation mit dem Intelligent Driver Model (IDM) · {n} Autos pro km', en: 'Simulation with the Intelligent Driver Model (IDM) · {n} cars per km'},
  noMeter: {es: 'Sin semáforo en la entrada', pt: 'Sem semáforo na entrada', fr: 'Sans feu à l’entrée', de: 'Ohne Ampel an der Auffahrt', en: 'No light on the ramp'},
  withMeter: {es: 'Con semáforo en la entrada', pt: 'Com semáforo na entrada', fr: 'Avec feu à l’entrée', de: 'Mit Ampel an der Auffahrt', en: 'A light on the ramp'},
  carsHour: {es: 'Coches que pasan por hora', pt: 'Carros que passam por hora', fr: 'Voitures par heure', de: 'Autos pro Stunde', en: 'Cars through an hour'},
  waitRamp: {es: '{n} esperan en la rampa', pt: '{n} esperam na rampa', fr: '{n} attendent sur la bretelle', de: '{n} warten an der Auffahrt', en: '{n} waiting on the ramp'},
  rampNote: {es: 'Simulación (IDM) · los mismos coches salen y vuelven a entrar por la rampa', pt: 'Simulação (IDM) · os mesmos carros saem e voltam a entrar pela rampa', fr: 'Simulation (IDM) · les mêmes voitures sortent et reviennent par la bretelle', de: 'Simulation (IDM) · dieselben Autos fahren ab und wieder auf', en: 'Simulation (IDM) · the same cars leave and come back up the ramp'},
  platoonNote: {es: 'Simulación · cada conductor reacciona {r} s tarde', pt: 'Simulação · cada condutor reage {r} s atrasado', fr: 'Simulation · chaque conducteur réagit avec {r} s de retard', de: 'Simulation · jeder reagiert {r} s zu spät', en: 'Simulation · every driver reacts {r} s late'},
});

const ROAD_Y = 560;
const LANE = 38;

// the road band and its markings; lanes counted from the top
const Asphalt: FC<{lanes: number; y?: number; appear?: number}> = ({lanes, y = ROAD_Y, appear = 1}) => {
  const top = y - (lanes * LANE) / 2;
  return (
    <g>
      <rect x={0} y={top - 6} width={1920} height={lanes * LANE + 12} fill="#3a3e45" />
      <rect x={0} y={top} width={1920} height={lanes * LANE} fill="#2b2e34" />
      {Array.from({length: lanes - 1}, (_, k) => (
        <line key={k} x1={0} x2={1920} y1={top + (k + 1) * LANE} y2={top + (k + 1) * LANE} stroke="rgba(255,255,255,0.45)"
              strokeWidth={2.5} strokeDasharray="26 26" opacity={k === lanes - 2 ? appear : 1} />
      ))}
      <line x1={0} x2={1920} y1={top + 3} y2={top + 3} stroke="rgba(255,255,255,0.8)" strokeWidth={3} />
      <line x1={0} x2={1920} y1={top + lanes * LANE - 3} y2={top + lanes * LANE - 3} stroke="rgba(255,255,255,0.8)" strokeWidth={3} />
    </g>
  );
};

const laneY = (lanes: number, lane: number, y = ROAD_Y) => y - (lanes * LANE) / 2 + LANE * (lane + 0.5);

// one car with its brake glow (the red bloom that makes a wave visible from far away), coloured by its speed
const RoadCar: FC<{sx: number; sy: number; s: number; v: number; a: number; top: number; mark?: string}> = ({sx, sy, s, v, a, top, mark}) => {
  const brake = Math.min(1, Math.max(0, -a - 0.15) / 0.8) || (v < 0.6 ? 1 : 0);
  return (
    <g>
      {brake > 0.05 && <circle cx={sx - 2.2 * s} cy={sy} r={6 * s} fill="url(#glow)" opacity={brake} />}
      <Car sx={sx} sy={sy} deg={0} s={s} color={paint(v, top)} brake={brake} mark={mark} trail={trail(v, top)} />
    </g>
  );
};

const Defs = () => (
  <defs>
    <radialGradient id="glow"><stop offset="0%" stopColor="#ff2a2a" stopOpacity={0.55} /><stop offset="100%" stopColor="#ff2a2a" stopOpacity={0} /></radialGradient>
    <marker id="arrowR" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto"><path d="M0,0 L10,5 L0,10 Z" fill={C.text} /></marker>
    <marker id="arrowL" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto"><path d="M0,0 L10,5 L0,10 Z" fill={C.red} /></marker>
  </defs>
);

// the cars of a periodic road inside the window [x0, x0 + span) metres, in one lane
const TOP = 13;              // m/s: going well on the long road
const Traffic: FC<{f: Frame & {on?: Uint8Array}; L: number; x0: number; span: number; y: number; marks?: Record<number, string>}> = ({f, L, x0, span, y, marks = {}}) => {
  const m = 1920 / span;
  return (
    <g>
      {Array.from(f.x).map((x, i) => {
        const d = ((x - x0) % L + L) % L;
        if (d > span + 10 || (f.on && !f.on[i])) return null;
        return <RoadCar key={i} sx={d * m} sy={y} s={m * 1.05} v={f.v[i]} a={f.a[i]} top={TOP} mark={marks[i]} />;
      })}
    </g>
  );
};

const Bars: FC<{rows: {label: string; value: number; text: string; colour: string}[]; max: number; o: number; style: object}> = ({rows, max, o, style}) => (
  <Panel o={o} style={{width: 700, ...style}}>
    {rows.map((r) => (
      <div key={r.label} style={{display: 'flex', alignItems: 'center', gap: 14, marginTop: 8}}>
        <div style={{width: 300, fontSize: 22, fontWeight: 700, letterSpacing: 1, textTransform: 'uppercase', color: r.colour}}>{r.label}</div>
        <div style={{flex: 1, height: 10, background: 'rgba(255,255,255,0.08)', borderRadius: 5}}>
          <div style={{width: `${Math.min(100, (r.value / max) * 100 * Math.min(1, o * 1.3))}%`, height: 10, background: r.colour, borderRadius: 5}} />
        </div>
        <div style={{width: 110, textAlign: 'right', fontSize: 26, fontWeight: 800, fontVariantNumeric: 'tabular-nums'}}>{r.text}</div>
      </div>
    ))}
  </Panel>
);

const Caption: FC<{text: string; x: number; y: number; colour?: string; anchor?: 'start' | 'middle' | 'end'; o?: number}> = ({text, x, y, colour = C.text, anchor = 'middle', o = 1}) => (
  <text x={x} y={y} textAnchor={anchor} fill={colour} fontFamily={FONT} fontSize={26} fontWeight={800} letterSpacing={1.4} opacity={o}
        style={{textTransform: 'uppercase'}}>{text.toUpperCase()}</text>
);

// --- frenazo / acc ---------------------------------------------------------------------------------------------------
const Platoon: FC<{g: WorldProps['g']; t: number; o: WorldProps['o']; on: number}> = ({g, t, o, on}) => {
  const p = platoon();
  const f = p.at(t);
  const centre = Array.from(f.x).reduce((a, b) => a + b, 0) / f.x.length;
  const span = 190;
  const x0 = centre - span / 2;
  const m = 1920 / span;
  const k = Math.min(p.frames.length - 1, Math.round(t / 0.1));
  // the hardest each one has braked so far
  const hardest = Array.from({length: f.x.length}, (_, i) => {
    let best = 0;
    for (let s = 0; s <= k; s++) best = Math.max(best, -p.frames[s].a[i]);
    return best;
  });
  const acc = param<string>(g, 'who', 'personas') === 'acc';
  const showBars = Math.max(o('labels'), o('panel'), acc ? on : 0);
  return (
    <svg width={1920} height={1080} style={{position: 'absolute'}}>
      <Defs />
      <Fields x0={x0} m={m} />
      <Roadside y={ROAD_Y} half={LANE / 2 + 6} x0={x0} m={m} seed="p" />
      <Asphalt lanes={1} />
      {Array.from(f.x).map((x, i) => (
        <g key={i}>
          <RoadCar sx={(x - x0) * m} sy={ROAD_Y} s={m * 0.95} v={f.v[i]} a={f.a[i]} top={PLATOON.speed} />
          <text x={(x - x0) * m} y={ROAD_Y + 62} textAnchor="middle" fill={C.label} fontFamily={FONT} fontSize={26} fontWeight={800}>{i + 1}</text>
          <rect x={(x - x0) * m - 9} y={ROAD_Y - 60 - Math.min(260, hardest[i] * 34)} width={18} height={Math.min(260, hardest[i] * 34)}
                fill={i ? C.red : C.accent} opacity={showBars} rx={3} />
          {o('panel') > 0 && (() => {
            const pts = [];
            for (let s = 0; s <= k; s += 3) pts.push(`${(x - x0) * m - 40 + (s / Math.max(1, p.frames.length)) * 80},${ROAD_Y + 120 - p.frames[s].v[i] * 4}`);
            return <polyline points={pts.join(' ')} fill="none" stroke={C.accent} strokeWidth={2.5} opacity={o('panel')} />;
          })()}
        </g>
      ))}
      <Caption text={tx('howHard')} x={60} y={250} anchor="start" colour={C.label} o={showBars} />
      <Caption text={tx(acc ? 'cruise' : 'harderEach')} x={1860} y={250} anchor="end" colour={acc ? C.accent : C.red} o={showBars} />
      {o('panel') > 0 && <Caption text={tx('eachSpeed')} x={60} y={ROAD_Y + 160} anchor="start" colour={C.label} o={o('panel')} />}
    </svg>
  );
};

const platoonAnchors = (t: number): Record<string, Anchor> => {
  const f = platoon().at(t);
  const centre = Array.from(f.x).reduce((a, b) => a + b, 0) / f.x.length;
  const m = 1920 / 190;
  const at = (i: number) => ({x: (f.x[i] - (centre - 95)) * m, y: ROAD_Y});
  return {car: at(0), jam: at(f.x.length - 1)};
};

// --- the on-ramp ------------------------------------------------------------------------------------------------------
const RAMP_VIEW = {before: 140, span: 380};
const rampFlow = new Map<boolean, number>();
/** Cars an hour past the middle of the road, over the settled part of the run. */
const flowOf = (metered: boolean) => {
  if (!rampFlow.has(metered)) {
    const r = ramp(metered);
    let passes = 0;
    for (let t = 100; t < RAMP.span - 0.2; t += 0.1) {
      const a = r.at(t);
      const b = r.at(t + 0.1);
      for (let i = 0; i < r.cars; i++) if (a.on[i] && b.on[i] && a.x[i] < 500 && b.x[i] >= 500) passes++;
    }
    rampFlow.set(metered, (passes / (RAMP.span - 100.2)) * 3600);
  }
  return rampFlow.get(metered)!;
};

const RampRoad: FC<{metered: boolean; simT: number; y: number; o: WorldProps['o']}> = ({metered, simT, y, o}) => {
  const r = ramp(metered);
  const f = r.at(simT);
  const x0 = RAMP.merge - RAMP_VIEW.before;
  const m = 1920 / RAMP_VIEW.span;
  const mx = RAMP_VIEW.before * m;
  const end = {x: mx, y: y + LANE / 2 + 4};
  const start = {x: mx - 330, y: y + 150};
  const len = Math.hypot(end.x - start.x, end.y - start.y);
  const ux = (end.x - start.x) / len;
  const uy = (end.y - start.y) / len;
  // a light shows green for a moment each time it lets a car in
  const before = r.at(Math.max(0, simT - 0.7));
  const justIn = Array.from(f.on).some((v, i) => v && !before.on[i] && Math.abs(f.x[i] - RAMP.merge) < 15);
  const waiting = Math.min(f.waiting, 14);
  return (
    <g>
      <path d={`M${start.x - ux * 400},${start.y - uy * 400} L${end.x + ux * 40},${end.y + uy * 40}`} stroke="#3a3e45" strokeWidth={LANE + 10} />
      <path d={`M${start.x - ux * 400},${start.y - uy * 400} L${end.x + ux * 40},${end.y + uy * 40}`} stroke="#2b2e34" strokeWidth={LANE - 2} />
      <Roadside y={y} half={LANE / 2 + 6} x0={x0} m={m} seed={metered ? 'm' : 'f'} />
      <Asphalt lanes={1} y={y} />
      {Array.from({length: waiting}, (_, k) => {
        const d = 40 + k * 26;
        return <RoadCar key={k} sx={end.x - ux * d} sy={end.y - uy * d} s={m * 1.05} v={metered ? 0 : 1.2} a={0} top={TOP} />;
      }).map((car, k) => <g key={k} transform={`rotate(${(Math.atan2(uy, ux) * 180) / Math.PI} ${end.x - ux * (40 + k * 26)} ${end.y - uy * (40 + k * 26)})`}>{car}</g>)}
      <Traffic f={f} L={r.L} x0={x0} span={RAMP_VIEW.span} y={y} />
      {metered && (
        <g>
          <rect x={end.x - 70} y={end.y + 18} width={30} height={62} rx={8} fill="#0d0f13" stroke="#444" strokeWidth={2} />
          <circle cx={end.x - 55} cy={end.y + 35} r={10} fill={justIn ? '#333' : '#ff3b30'} />
          <circle cx={end.x - 55} cy={end.y + 62} r={10} fill={justIn ? '#3ddc84' : '#333'} />
        </g>
      )}
      <Caption text={tx(metered ? 'withMeter' : 'noMeter')} x={60} y={y - 60} anchor="start" colour={metered ? C.green : C.red} />
      <Caption text={tx('waitRamp', {n: f.waiting})} x={start.x - 40} y={start.y + 70} anchor="middle" colour={C.label} o={Math.max(o('labels'), 0.9)} />
      <Caption text={tx('nStoppedRoad', {n: r.stopped(simT)})} x={1860} y={y - 60} anchor="end" colour={r.stopped(simT) ? C.red : C.green} />
    </g>
  );
};

// --- the long road scenes ----------------------------------------------------------------------------------------------
const LAPSE = 1.5;
const START: Record<string, number> = {onda: 120, carril: 120, hueco: 92, limite: 150, carriles: 140};

const View: FC<WorldProps> = ({g, worldT, local, real = local, on, o}) => {
  const scene = param<string>(g, 'scene', 'onda');
  if (scene === 'frenazo') {
    const cue = g.cues?.brake;
    const t = cue === undefined ? worldT : PLATOON.brakeFrom - 0.6 + (g.at + local - cue);
    return (
      <AbsoluteFill style={{background: CITY.ground}}>
        <Platoon g={g} t={Math.max(0, Math.min(PLATOON.span, t))} o={o} on={on} />
        <Pointers marks={g.marks} local={real} at={platoonAnchors(Math.max(0, Math.min(PLATOON.span, t)))} />
        <Note>{tx('platoonNote', {r: PLATOON.react})}</Note>
      </AbsoluteFill>
    );
  }
  if (scene === 'rampa') {
    const t = Math.min(RAMP.span, 60 + worldT * LAPSE);
    const free = flowOf(false);
    const metered = flowOf(true);
    return (
      <AbsoluteFill style={{background: CITY.ground}}>
        <svg width={1920} height={1080} style={{position: 'absolute'}}>
          <Defs />
          <RampRoad metered={false} simT={t} y={300} o={o} />
          <RampRoad metered simT={t} y={700} o={o} />
        </svg>
        <Bars o={o('panel')} max={Math.max(free, metered)} style={{right: 64, bottom: 60}} rows={[
          {label: `${tx('carsHour')} · ${tx('noMeter')}`, value: free, text: String(Math.round(free / 10) * 10), colour: C.red},
          {label: `${tx('carsHour')} · ${tx('withMeter')}`, value: metered, text: String(Math.round(metered / 10) * 10), colour: C.green},
        ]} />
        <Pointers marks={g.marks} local={real} at={{jam: (() => {
          const r = ramp(false);
          const j = jamOf({...r.at(t), x: r.at(t).x.map((x, i) => (r.at(t).on[i] ? x : -9999))}, r.L);
          return j ? {x: ((((j.tail + j.front) / 2 - (RAMP.merge - RAMP_VIEW.before)) % r.L + r.L) % r.L) * (1920 / RAMP_VIEW.span), y: 300} : null;
        })()}} />
        <Note>{tx('rampNote')}</Note>
      </AbsoluteFill>
    );
  }
  const simT = Math.min(ROAD.span, (START[scene] ?? 120) + worldT * LAPSE);
  const L = ROAD.length;
  const variant = scene === 'hueco' ? 'hueco' : scene === 'limite' ? 'limite' : 'normal';
  const r = road(variant);
  const f = r.at(simT);
  const you = VARIANT.you;
  const follow = scene === 'hueco' || scene === 'carril';
  const span = scene === 'limite' ? 400 : 240;            // close enough to see each car
  // onda: the camera stays where the jam was when the scene began, so the jam is seen sliding back through it
  const startJam = scene === 'onda' ? jamOf(r.at(START.onda), L) : null;
  const x0 = follow ? f.x[you] - span * 0.62 : scene === 'limite' ? VARIANT.limite.at - 60
    : startJam ? startJam.front - span * 0.72 : 380;
  const m = 1920 / span;
  const sx = (x: number) => (((x - x0) % L + L) % L) * m;
  const lanes = scene === 'carril' ? 2 : scene === 'carriles' ? 3 : 1;
  const yOf = (lane: number) => laneY(lanes, lane);
  let overlay: ReactElement | null = null;
  let panel: ReactElement | null = null;

  if (scene === 'onda') {
    const jam = jamOf(f, L);
    const before = jamOf(r.at(Math.max(0, simT - 6)), L);
    const speed = jam && before ? Math.round(Math.abs(((jam.front - before.front + L * 1.5) % L) - L / 2) / 6 * 3.6) : 0;
    if (jam) {
      const a = sx(jam.tail) - 30;
      const b = sx(jam.tail) + (jam.front - jam.tail) * m + 30;
      overlay = (
        <g opacity={o('labels')}>
          <rect x={a} y={ROAD_Y - 38} width={b - a} height={76} rx={10} fill="none" stroke={C.red} strokeWidth={3} />
          <line x1={(a + b) / 2 + 120} x2={(a + b) / 2 - 120} y1={ROAD_Y + 80} y2={ROAD_Y + 80} stroke={C.red} strokeWidth={4} markerEnd="url(#arrowL)" />
          <Caption text={tx('theJam', {v: Math.max(5, speed)})} x={(a + b) / 2} y={ROAD_Y + 118} colour={C.red} />
          <line x1={(a + b) / 2 - 120} x2={(a + b) / 2 + 120} y1={ROAD_Y - 80} y2={ROAD_Y - 80} stroke={C.text} strokeWidth={4} markerEnd="url(#arrowR)" />
          <Caption text={tx('theCars')} x={(a + b) / 2} y={ROAD_Y - 100} />
        </g>
      );
      // why it lasts: flow out of the jam's front, a clear road's most, the flow arriving at its tail
      const flow = (from: number, len: number) => {
        let n = 0;
        let v = 0;
        for (let i = 0; i < r.cars; i++) {
          const d = ((f.x[i] - from) % L + L) % L;
          if (d < len) {
            n++;
            v += f.v[i];
          }
        }
        return n ? (n / len) * (v / n) * 3600 : 0;
      };
      const out = flow(jam.front, 120);
      const top = capacity();
      const arriving = flow(jam.tail - 220, 200);
      panel = <Bars o={o('panel')} max={top} style={{left: '50%', bottom: 90, transform: 'translateX(-50%)'}} rows={[
        {label: tx('outOfJam'), value: out, text: tx('perHourShort', {n: Math.round(out / 10) * 10}), colour: C.red},
        {label: tx('clearRoad'), value: top, text: tx('perHourShort', {n: Math.round(top / 10) * 10}), colour: C.text},
        {label: tx('arriving'), value: arriving, text: tx('perHourShort', {n: Math.round(arriving / 10) * 10}), colour: C.accent},
      ]} />;
    }
  }
  if (scene === 'carril') {
    const lt = laneTimes(ROAD.span);
    panel = <Bars o={o('panel')} max={Math.max(lt.passFour, lt.passedFour)} style={{left: '50%', bottom: 90, transform: 'translateX(-50%)'}} rows={[
      {label: tx('passFour'), value: lt.passFour, text: `${lt.passFour.toFixed(0)} s`, colour: C.text},
      {label: tx('passedFour'), value: lt.passedFour, text: `${lt.passedFour.toFixed(0)} s`, colour: C.accent},
    ]} />;
    overlay = <Caption text={tx('sameSpeed')} x={960} y={ROAD_Y - 110} colour={C.label} o={Math.max(o('labels'), o('panel'))} />;
  }
  if (scene === 'hueco') {
    const driving = simT >= VARIANT.hueco.from;
    // the car ahead of you
    let ahead = -1;
    let gap = Infinity;
    for (let i = 0; i < r.cars; i++) {
      const d = ((f.x[i] - f.x[you]) % L + L) % L;
      if (i !== you && d > 0 && d < gap) {
        gap = d;
        ahead = i;
      }
    }
    const ys = ROAD_Y;
    overlay = (
      <g>
        {driving && ahead >= 0 && (
          <g opacity={Math.max(o('labels'), 0.85)}>
            <line x1={sx(f.x[you]) + 28} x2={sx(f.x[you]) + gap * m - 28} y1={ys} y2={ys} stroke={C.you} strokeWidth={3} strokeDasharray="10 8" />
            <Caption text={tx('theGap')} x={sx(f.x[you]) + (gap * m) / 2} y={ys - 50} colour={C.you} />
          </g>
        )}
        <Caption text={driving ? `${tx('you')} · ${tx('stillRolling', {v: Math.round(f.v[you] * 3.6)})}` : tx('you')} x={sx(f.x[you])} y={ys + 72}
                 colour={C.you} />
      </g>
    );
    const without = road('normal').stopped(simT);
    panel = (
      <Panel o={o('panel')} style={{right: 64, top: 60, width: 330}}>
        <Label>{tx('stoppedBehind')}</Label>
        <div style={{fontSize: 56, fontWeight: 800, color: C.green, fontVariantNumeric: 'tabular-nums'}}>{r.stopped(simT)}</div>
        <Label color={C.red}>{tx('withoutGap', {n: without})}</Label>
      </Panel>
    );
  }
  if (scene === 'limite') {
    const lim = VARIANT.limite;
    const active = simT >= lim.from;
    const gantries = [0, 0.5, 1].map((k) => lim.at + k * lim.length);
    overlay = (
      <g>
        {gantries.map((x) => (
          <g key={x}>
            <rect x={sx(x) - 4} y={ROAD_Y - 60} width={8} height={120} fill="#111" />
            <circle cx={sx(x)} cy={ROAD_Y - 78} r={26} fill="#0d0d0d" stroke={active ? '#e8483f' : '#333'} strokeWidth={6} />
            <text x={sx(x)} y={ROAD_Y - 69} textAnchor="middle" fill="#fff" fontFamily={FONT} fontWeight={800} fontSize={24}>
              {active ? Math.round(lim.v0 * 3.6) : ''}
            </text>
          </g>
        ))}
        <Caption text={tx('arriveSlowly')} x={sx(lim.at + lim.length / 2)} y={ROAD_Y + 90} colour={C.accent} o={Math.max(o('labels'), 0.0)} />
      </g>
    );
    const without = road('normal').stopped(simT);
    panel = <Bars o={o('panel')} max={Math.max(1, without, r.stopped(simT))} style={{left: '50%', bottom: 90, transform: 'translateX(-50%)'}} rows={[
      {label: tx('withoutSigns'), value: without, text: String(without), colour: C.red},
      {label: tx('withSigns'), value: r.stopped(simT), text: String(r.stopped(simT)), colour: C.green},
    ]} />;
  }
  if (scene === 'carriles') {
    panel = <Bars o={o('panel')} max={115} style={{left: '50%', bottom: 90, transform: 'translateX(-50%)'}} rows={[
      {label: tx('laneKm'), value: 110, text: '+10 %', colour: C.text},
      {label: tx('kmDriven'), value: 110, text: '+10 %', colour: C.accent},
    ]} />;
    overlay = <Caption text={tx('newLane')} x={60} y={laneY(3, 2) + 8} anchor="start" colour={C.accent} o={o('labels')} />;
  }

  const appear = Math.min(1, worldT / 1.5);
  return (
    <AbsoluteFill style={{background: CITY.ground}}>
      <svg width={1920} height={1080} style={{position: 'absolute'}}>
        <Defs />
        <Fields x0={x0} m={m} />
        <Roadside y={ROAD_Y} half={(lanes * LANE) / 2 + 6} x0={x0} m={m} />
        <Asphalt lanes={lanes} appear={scene === 'carriles' ? appear : 1} />
        <Traffic f={f} L={L} x0={x0} span={span} y={yOf(0)} marks={follow ? {[you]: C.you} : {}} />
        {lanes >= 2 && <Traffic f={road('normal', 19).at(simT)} L={L} x0={x0} span={span} y={yOf(1)} />}
        {lanes >= 3 && <g opacity={appear}><Traffic f={road('normal', 23).at(simT)} L={L} x0={x0} span={span} y={yOf(2)} /></g>}
        {overlay}
      </svg>
      {panel}
      <Pointers marks={g.marks} local={real} at={(() => {
        const jam = jamOf(f, L);
        const jamAt = jam ? {x: sx((jam.tail + jam.front) / 2), y: yOf(0)} : null;
        let ahead = -1;
        let gap = Infinity;
        for (let i = 0; i < r.cars; i++) {
          const d = ((f.x[i] - f.x[you]) % L + L) % L;
          if (i !== you && d > 0 && d < gap) { gap = d; ahead = i; }
        }
        const youAt = {x: sx(f.x[you]), y: yOf(0)};
        return {car: follow ? youAt : jam ? {x: sx(jam.tail) - 30 * m * 0.2, y: yOf(0)} : null, jam: jamAt,
                gap: follow && ahead >= 0 ? {x: sx(f.x[you]) + (gap * m) / 2, y: yOf(0)} : null};
      })()} />
      <Note>{tx('roadNote', {n: Math.round(ROAD.cars / (L / 1000))})}</Note>
    </AbsoluteFill>
  );
};

export const carretera: World = {View};
