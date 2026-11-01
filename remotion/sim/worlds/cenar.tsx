// More of the restaurant (worlds/linekitchen.tsx), for the scenes a dinner script asks for:
//  pedir    your table of ten, dish by dish through the kitchen's stations: everyone orders something different (a
//           risotto, two steaks, the fish… most of it on the grill, which does five at a time) against ordering
//           alike (spread over the fryer, the cold side and the grill): the table eats when its LAST dish is ready
//  terraza  sitting down at once on the terrace or waiting at the bar for a table inside: with the kitchen flat out
//           the food comes at about the same time — the kitchen sets the pace, not where you wait
//  pista    the McDonald brothers, San Bernardino, 1948: the kitchen drawn in chalk on a tennis court and the staff
//           rehearsing their moves on it before it was built
import type {FC} from 'react';
import {AbsoluteFill, interpolate} from 'remotion';
import {C, FONT, Label, Panel} from '../hud';
import {addWords, tx} from '../i18n';
import {DISHES, STATIONS, waits} from '../linekitchen';
import {param, type WorldProps} from '../world';
import {Figure, Split} from '../scenes';

addWords({
  eachOwn: {es: 'Cada uno pide lo suyo', pt: 'Cada um pede o seu', fr: 'Chacun commande le sien', de: 'Jeder bestellt etwas anderes', en: 'Everyone orders their own'},
  alike: {es: 'Pedís parecido', pt: 'Pedem parecido', fr: 'Vous commandez pareil', de: 'Ihr bestellt Ähnliches', en: 'You order alike'},
  tableEats: {es: 'La mesa come a los', pt: 'A mesa come aos', fr: 'La table mange après', de: 'Der Tisch isst nach', en: 'The table eats after'},
  waitingTurn: {es: 'esperando turno', pt: 'à espera da vez', fr: 'attend son tour', de: 'wartet', en: 'waiting its turn'},
  emptyKitchen: {es: 'Aunque la cocina estuviera vacía', pt: 'Mesmo com a cozinha vazia', fr: 'Même cuisine vide', de: 'Selbst bei leerer Küche', en: 'Even with an empty kitchen'},
  burger: {es: 'Hamburguesa', pt: 'Hambúrguer', fr: 'Burger', de: 'Burger', en: 'Burger'},
  steak: {es: 'Chuletón', pt: 'Bife', fr: 'Côte de bœuf', de: 'Steak', en: 'Steak'},
  risotto: {es: 'Risotto', pt: 'Risoto', fr: 'Risotto', de: 'Risotto', en: 'Risotto'},
  croquetas: {es: 'Croquetas', pt: 'Croquetes', fr: 'Croquettes', de: 'Kroketten', en: 'Croquettes'},
  salad: {es: 'Ensalada', pt: 'Salada', fr: 'Salade', de: 'Salat', en: 'Salad'},
  fish: {es: 'Pescado', pt: 'Peixe', fr: 'Poisson', de: 'Fisch', en: 'Fish'},
  terraceNow: {es: 'A la terraza ya', pt: 'Na esplanada já', fr: 'En terrasse tout de suite', de: 'Sofort auf die Terrasse', en: 'The terrace, now'},
  barFirst: {es: 'Esperar mesa en la barra', pt: 'Esperar mesa no balcão', fr: 'Attendre une table au bar', de: 'An der Bar auf einen Tisch warten', en: 'Wait at the bar for a table'},
  stepBar: {es: 'En la barra', pt: 'No balcão', fr: 'Au bar', de: 'An der Bar', en: 'At the bar'},
  stepSeated: {es: 'Sentados, mirando la carta', pt: 'Sentados, a ver o cardápio', fr: 'Assis, la carte', de: 'Am Tisch, Karte lesen', en: 'Seated, reading the menu'},
  stepKitchen: {es: 'La comanda en la cocina', pt: 'O pedido na cozinha', fr: 'La commande en cuisine', de: 'Bestellung in der Küche', en: 'The order in the kitchen'},
  stepFood: {es: 'Llega la comida', pt: 'Chega a comida', fr: 'Le plat arrive', de: 'Das Essen kommt', en: 'The food arrives'},
  sinceDoor: {es: 'Desde que entráis', pt: 'Desde que entram', fr: 'Depuis l’entrée', de: 'Seit ihr reinkommt', en: 'Since you walked in'},
  kitchenPace: {es: 'La cocina marca el ritmo, no dónde esperas', pt: 'A cozinha dita o ritmo, não onde esperas', fr: 'La cuisine fixe le rythme, pas l’endroit où tu attends', de: 'Die Küche gibt das Tempo vor, nicht wo du wartest', en: 'The kitchen sets the pace, not where you wait'},
  sanBernardino: {es: 'San Bernardino, California · 1948', pt: 'San Bernardino, Califórnia · 1948', fr: 'San Bernardino, Californie · 1948', de: 'San Bernardino, Kalifornien · 1948', en: 'San Bernardino, California · 1948'},
  tennisCourt: {es: 'La cocina dibujada con tiza en una pista de tenis', pt: 'A cozinha desenhada a giz num campo de ténis', fr: 'La cuisine tracée à la craie sur un court de tennis', de: 'Die Küche mit Kreide auf einem Tennisplatz', en: 'The kitchen drawn in chalk on a tennis court'},
  brothers: {es: 'Los hermanos McDonald', pt: 'Os irmãos McDonald', fr: 'Les frères McDonald', de: 'Die McDonald-Brüder', en: 'The McDonald brothers'},
  chalkGrill: {es: 'Plancha', pt: 'Chapa', fr: 'Plaque', de: 'Grill', en: 'Grill'},
  chalkFries: {es: 'Patatas', pt: 'Batatas', fr: 'Frites', de: 'Pommes', en: 'Fries'},
  chalkShakes: {es: 'Batidos', pt: 'Batidos', fr: 'Milk-shakes', de: 'Shakes', en: 'Shakes'},
  chalkDress: {es: 'Montar', pt: 'Montar', fr: 'Garnir', de: 'Belegen', en: 'Dressing'},
  chalkWindow: {es: 'Ventanilla', pt: 'Janela', fr: 'Guichet', de: 'Schalter', en: 'Window'},
});

// --- your table of ten through the stations ------------------------------------------------------------------------

const CAP = [5, 3, 2, 2];                                  // the line's capacity (linekitchen.ts): grill, fryer, cold, plating
const STATION_COLOURS = ['#e8590c', '#fab005', '#4dabf7', '#adb5bd'];
const OWN = [2, 1, 1, 5, 2, 0, 5, 1, 3, 4];                // risotto ×2, steak ×3, fish ×2, burger, croquetas, salad
const ALIKE = [0, 0, 0, 3, 3, 3, 4, 4, 4, 0];             // burgers, croquetas, salads: spread over the stations

type Seg = {station: number; start: number; end: number};
/** Every dish through its route, five on the grill at a time and so on, first come first served (minutes). */
export const tableRun = (types: number[]) => {
  const free: number[][] = CAP.map((c) => Array(c).fill(0));
  const segs: Seg[][] = types.map(() => []);
  const ready = types.map(() => 0);
  const at = types.map(() => 0);
  const step = types.map(() => 0);
  // event by event: the dish that can start earliest goes next
  for (;;) {
    let best = -1;
    let bestStart = Infinity;
    for (let d = 0; d < types.length; d++) {
      const route = DISHES[types[d]].route;
      if (step[d] >= route.length) continue;
      const s = route[step[d]][0];
      const start = Math.max(at[d], Math.min(...free[s]));
      if (start < bestStart - 1e-9) { bestStart = start; best = d; }
    }
    if (best < 0) break;
    const [s, minutes] = DISHES[types[best]].route[step[best]];
    const k = free[s].indexOf(Math.min(...free[s]));
    const end = bestStart + minutes;
    free[s][k] = end;
    segs[best].push({station: s, start: bestStart, end});
    at[best] = end;
    step[best]++;
    if (step[best] >= DISHES[types[best]].route.length) ready[best] = end;
  }
  return {segs, ready, done: Math.max(...ready)};
};

const Gantt: FC<{types: number[]; t: number}> = ({types, t}) => {
  const run = tableRun(types);
  const X = (m: number) => 360 + m * 50;
  const now = Math.min(t, run.done + 0.5);
  return (
    <AbsoluteFill style={{background: C.night}}>
      <svg width={1920} height={1080} style={{position: 'absolute'}}>
        {[0, 5, 10, 15, 20, 25, 30].map((m) => (
          <g key={m}><line x1={X(m)} x2={X(m)} y1={90} y2={1000} stroke="rgba(255,255,255,0.08)" strokeWidth={2} />
            <text x={X(m)} y={1045} textAnchor="middle" fill="#8b93a7" fontFamily={FONT} fontSize={38}>{m} min</text></g>))}
        {types.map((type, d) => {
          const y = 110 + d * 88;
          const done = run.ready[d] <= now;
          const first = run.segs[d][0]?.start ?? 0;
          return (
            <g key={d}>
              <circle cx={60} cy={y + 30} r={22} fill={DISHES[type].colour} stroke="#000" strokeWidth={3} />
              <text x={100} y={y + 44} fill={C.text} fontFamily={FONT} fontSize={40} fontWeight={800}>{tx(DISHES[type].name)}</text>
              {first > 0.05 && now > 0 && <rect x={X(0)} y={y + 14} width={(Math.min(now, first)) * 50} height={32} rx={6} fill="none"
                                               stroke="#8b93a7" strokeWidth={3} strokeDasharray="8 6" />}
              {run.segs[d].map((sg, i) => sg.start < now && (
                <rect key={i} x={X(sg.start)} y={y + 8} width={(Math.min(now, sg.end) - sg.start) * 50} height={44} rx={8}
                      fill={STATION_COLOURS[sg.station]} />))}
              {/* finished early: it waits on the pass for the rest of the table */}
              {done && <rect x={X(run.ready[d])} y={y + 24} width={(now - run.ready[d]) * 50} height={12} rx={6} fill="rgba(255,107,107,0.55)" />}
            </g>
          );
        })}
        <line x1={X(now)} x2={X(now)} y1={90} y2={1000} stroke={C.you} strokeWidth={5} />
        {now >= run.done && <line x1={X(run.done)} x2={X(run.done)} y1={90} y2={1000} stroke={C.red} strokeWidth={6} strokeDasharray="14 8" />}
      </svg>
      <div style={{position: 'absolute', left: 360, top: 26, display: 'flex', gap: 30, fontFamily: FONT, fontSize: 38, fontWeight: 800, color: C.text,
                   textTransform: 'uppercase'}}>
        {STATIONS.map((s, i) => <span key={s}><span style={{display: 'inline-block', width: 26, height: 18, background: STATION_COLOURS[i], marginRight: 8, borderRadius: 4}} />{tx(s)}</span>)}
      </div>
    </AbsoluteFill>
  );
};

const Order: FC<WorldProps> = ({worldT}) => {
  const t = worldT * 1.8;                                  // 1 s of video = 1.8 min in the kitchen
  const own = tableRun(OWN);
  const alike = tableRun(ALIKE);
  const shown = (r: ReturnType<typeof tableRun>) => (t >= r.done ? `${Math.round(r.done)} min` : '…');
  return (
    <AbsoluteFill>
      <Split left={<Gantt types={OWN} t={t} />} right={<Gantt types={ALIKE} t={t} />} titles={[tx('eachOwn'), tx('alike')]}
             figures={[<Figure key="a" label={tx('tableEats')} value={shown(own)} colour={C.red} sub={tx('emptyKitchen')} />,
                       <Figure key="b" label={tx('tableEats')} value={shown(alike)} colour={C.green} sub={tx('emptyKitchen')} />]} />
    </AbsoluteFill>
  );
};

// --- the terrace now or the bar first ------------------------------------------------------------------------------

const Timeline: FC<{steps: {key: string; from: number; colour: string}[]; end: number; t: number}> = ({steps, end, t}) => {
  const X = (m: number) => 120 + m * 30;
  return (
    <AbsoluteFill style={{background: C.night}}>
      <svg width={1920} height={1080} style={{position: 'absolute'}}>
        {[0, 10, 20, 30, 40, 50].map((m) => (
          <g key={m}><line x1={X(m)} x2={X(m)} y1={250} y2={760} stroke="rgba(255,255,255,0.08)" strokeWidth={2} />
            <text x={X(m)} y={810} textAnchor="middle" fill="#8b93a7" fontFamily={FONT} fontSize={36}>{m} min</text></g>))}
        {steps.map((s, i) => {
          const to = i + 1 < steps.length ? steps[i + 1].from : end;
          if (t <= s.from) return null;
          const y = 270 + i * 150;
          return (
            <g key={s.key}>
              <rect x={X(s.from)} y={y} width={(Math.min(t, to) - s.from) * 30} height={90} rx={12} fill={s.colour} />
              {/* a short step: its name after the bar, on the dark */}
              <text x={(to - s.from) * 30 < 330 ? X(to) + 14 : X(s.from) + 16} y={y + 60} fill={(to - s.from) * 30 < 330 ? s.colour : '#0b1020'}
                    fontFamily={FONT} fontSize={44} fontWeight={800} style={{textTransform: 'uppercase'}}>{tx(s.key)}</text>
            </g>
          );
        })}
        {t >= end && <g><line x1={X(end)} x2={X(end)} y1={250} y2={760} stroke={C.green} strokeWidth={6} />
          <text x={X(end) - 14} y={236} textAnchor="end" fill={C.green} fontFamily={FONT} fontSize={52} fontWeight={800} style={{textTransform: 'uppercase'}}>{tx('stepFood')}</text></g>}
        <line x1={X(Math.min(t, end))} x2={X(Math.min(t, end))} y1={250} y2={760} stroke={C.you} strokeWidth={4} />
      </svg>
    </AbsoluteFill>
  );
};

const Terrace: FC<WorldProps> = ({worldT}) => {
  const t = worldT * 3.5;                                  // 1 s = 3.5 min
  const kitchen = Math.round(waits({load: 0.9, share: false, fix: 'none'}).bySize[10] ?? 48) - 4;   // order → food, flat out
  const bar = 18;
  // the kitchen works through orders in turn: ordering a quarter of an hour later, the queue in front is about as long,
  // so the food lands at nearly the same minute (a little later)
  const a = [{key: 'stepSeated', from: 0, colour: '#ffd8a8'}, {key: 'stepKitchen', from: 4, colour: '#ff8787'}];
  const b = [{key: 'stepBar', from: 0, colour: '#a5d8ff'}, {key: 'stepSeated', from: bar, colour: '#ffd8a8'}, {key: 'stepKitchen', from: bar + 4, colour: '#ff8787'}];
  const endA = 4 + kitchen;
  const endB = endA + 2;
  const fig = (end: number, colour: string) => <Figure label={tx('sinceDoor')} value={t >= end ? `${end} min` : '…'} colour={colour} />;
  return (
    <AbsoluteFill>
      <Split left={<Timeline steps={a} end={endA} t={t} />} right={<Timeline steps={b} end={endB} t={t} />}
             titles={[tx('terraceNow'), tx('barFirst')]} figures={[fig(endA, C.text), fig(endB, C.text)]} />
      <div style={{position: 'absolute', left: 0, right: 0, top: 60, textAlign: 'center', fontFamily: FONT, fontSize: 46, fontWeight: 800,
                   color: C.you, textTransform: 'uppercase', opacity: interpolate(t, [endB, endB + 3], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'})}}>
        {tx('kitchenPace')}
      </div>
    </AbsoluteFill>
  );
};

// --- the McDonald brothers' tennis court ---------------------------------------------------------------------------

const COURT = {x: 300, y: 150, w: 1320, h: 780};
const SPOTS: Record<string, [number, number]> = {
  chalkGrill: [520, 330], chalkFries: [1100, 330], chalkShakes: [1400, 330], chalkDress: [820, 560], chalkWindow: [960, 840],
};
// each worker's round: from their station to the next and back, along the chalk
const ROUNDS: [string, string][] = [['chalkGrill', 'chalkDress'], ['chalkGrill', 'chalkDress'], ['chalkDress', 'chalkWindow'],
  ['chalkFries', 'chalkWindow'], ['chalkShakes', 'chalkWindow'], ['chalkDress', 'chalkWindow'], ['chalkGrill', 'chalkGrill'], ['chalkFries', 'chalkFries']];

const Court: FC<WorldProps> = ({worldT}) => {
  const chalk = interpolate(worldT, [0.3, 3.5], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const walk = Math.max(0, worldT - 3);
  const lines: [string, string][] = [['chalkGrill', 'chalkDress'], ['chalkFries', 'chalkDress'], ['chalkShakes', 'chalkWindow'], ['chalkDress', 'chalkWindow']];
  return (
    <AbsoluteFill style={{background: '#4f7a3a'}}>
      <svg width={1920} height={1080} style={{position: 'absolute'}}>
        <rect x={COURT.x - 60} y={COURT.y - 50} width={COURT.w + 120} height={COURT.h + 100} fill="#2f6f8f" />
        <rect x={COURT.x} y={COURT.y} width={COURT.w} height={COURT.h} fill="#3b86a8" stroke="#f1f3f5" strokeWidth={8} />
        <line x1={COURT.x + COURT.w / 2} x2={COURT.x + COURT.w / 2} y1={COURT.y - 30} y2={COURT.y + COURT.h + 30} stroke="#dee2e6" strokeWidth={10} />
        <line x1={COURT.x} x2={COURT.x + COURT.w} y1={COURT.y + 110} y2={COURT.y + 110} stroke="#f1f3f5" strokeWidth={6} />
        <line x1={COURT.x} x2={COURT.x + COURT.w} y1={COURT.y + COURT.h - 110} y2={COURT.y + COURT.h - 110} stroke="#f1f3f5" strokeWidth={6} />
        {/* the kitchen in chalk: counters as rectangles, the routes between them */}
        <g opacity={chalk} stroke="#fff8e1" strokeWidth={5} fill="none" strokeDasharray="14 6">
          {Object.entries(SPOTS).map(([k, [x, y]]) => <rect key={k} x={x - 120} y={y - 45} width={240} height={90} rx={6} />)}
          {lines.map(([a, b], i) => <line key={i} x1={SPOTS[a][0]} y1={SPOTS[a][1] + 45} x2={SPOTS[b][0]} y2={SPOTS[b][1] - 45} strokeDasharray="4 12" />)}
        </g>
        <g opacity={chalk}>
          {Object.entries(SPOTS).map(([k, [x, y]]) => (
            <text key={k} x={x} y={y + 12} textAnchor="middle" fill="#fff8e1" fontFamily="'Caveat', 'Comic Sans MS', cursive" fontSize={44}
                  fontWeight={700}>{tx(k)}</text>))}
        </g>
        {/* the staff rehearsing: back and forth between their two spots */}
        {ROUNDS.map(([a, b], i) => {
          const phase = (walk * 0.45 + i * 0.37) % 2;
          const k = phase < 1 ? phase : 2 - phase;
          const ease = k * k * (3 - 2 * k);
          const off = ((i % 3) - 1) * 46;
          const x = SPOTS[a][0] + off + (SPOTS[b][0] - SPOTS[a][0]) * ease;
          const y = SPOTS[a][1] + 70 + (SPOTS[b][1] - SPOTS[a][1]) * ease;
          return (
            <g key={i} transform={`translate(${x} ${y})`} opacity={interpolate(worldT, [2.5, 3.2], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'})}>
              <ellipse rx={30} ry={20} fill="#f8f9fa" stroke="rgba(0,0,0,0.4)" strokeWidth={3} />
              <circle r={13} fill="#ffffff" stroke="rgba(0,0,0,0.3)" strokeWidth={2} />
            </g>
          );
        })}
        {/* the two brothers watching from the side, one with a clipboard */}
        {[0, 1].map((k) => (
          <g key={k} transform={`translate(${190} ${430 + k * 110})`}>
            <ellipse rx={32} ry={21} fill={k ? '#495057' : '#343a40'} stroke="#000" strokeWidth={3} />
            <circle r={14} fill="#c9a27a" stroke="rgba(0,0,0,0.4)" strokeWidth={2} />
            {k === 0 && <rect x={22} y={-16} width={22} height={30} fill="#f1f3f5" stroke="#000" strokeWidth={2} />}
          </g>
        ))}
      </svg>
      <Panel o={1} style={{left: 48, top: 40}}>
        <div style={{fontSize: 38, fontWeight: 800, textTransform: 'uppercase'}}>{tx('sanBernardino')}</div>
        <Label>{tx('tennisCourt')}</Label>
      </Panel>
      <div style={{position: 'absolute', left: 60, top: 600, width: 260, fontFamily: FONT, fontSize: 30, fontWeight: 800, color: '#fff',
                   textTransform: 'uppercase', textShadow: '0 2px 6px #000'}}>{tx('brothers')}</div>
    </AbsoluteFill>
  );
};

export const DINNER_SCENES: Record<string, FC<WorldProps>> = {pedir: Order, terraza: Terrace, pista: Court};
