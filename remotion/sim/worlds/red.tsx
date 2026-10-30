// A country's power grid at night: substations (each feeding a city's lights) joined by lines. One piece fails on
// the line that says so (cues.fail); its load moves to its neighbours, and any that goes over its capacity falls too,
// step by step. With little reserve (margin) a single fault darkens most of the country; with enough, it stays put.
import type {FC} from 'react';
import {AbsoluteFill, interpolate} from 'remotion';
import {C, Label, Panel} from '../hud';
import {addWords, tx} from '../i18n';
import {Big, clamp, mulberry, Note, param, type World, type WorldProps} from '../world';

addWords({
  blackout: {es: 'Sin luz', pt: 'Sem luz', fr: 'Sans courant', de: 'Ohne Strom', en: 'Without power'},
  substationsDown: {es: '{n} de {m} subestaciones caídas', pt: '{n} de {m} subestações em baixo', fr: '{n} postes sur {m} hors service', de: '{n} von {m} Umspannwerken ausgefallen', en: '{n} of {m} substations down'},
  lineLoad: {es: 'Carga de cada línea', pt: 'Carga de cada linha', fr: 'Charge de chaque ligne', de: 'Last jeder Leitung', en: 'Load on each line'},
  fine: {es: 'holgada', pt: 'folgada', fr: 'faible', de: 'gering', en: 'light'},
  limit: {es: 'al límite', pt: 'no limite', fr: 'à la limite', de: 'am Limit', en: 'at the limit'},
  failsHere: {es: 'Aquí falla', pt: 'Aqui falha', fr: 'Ici, la panne', de: 'Hier fällt es aus', en: 'It fails here'},
  gridNote: {es: 'Simulación · {n} subestaciones · al caer una, su carga pasa a las vecinas · reserva de cada línea: {m} %', pt: 'Simulação · {n} subestações · quando uma cai, a carga passa às vizinhas · reserva: {m} %', fr: 'Simulation · {n} postes · quand un tombe, sa charge passe aux voisins · réserve : {m} %', de: 'Simulation · {n} Umspannwerke · fällt eines aus, geht seine Last an die Nachbarn · Reserve: {m} %', en: 'Simulation · {n} substations · when one falls its load moves to its neighbours · reserve: {m} %'},
});

const W = 1920;
const H = 1080;
const STEP = 0.45;                         // seconds between one wave of failures and the next
const TRANSFER = 0.45;                     // share of a fallen piece's load its neighbours take (the rest is cut off)

// spare: how this substation's reserve compares with the country's (some were built bigger than others)
type Grid = {outline: string; nodes: {x: number; y: number; load: number; spare: number}[]; edges: [number, number][]; first: number};
type Cascade = {steps: {down: number[]; load: number[]}[]};

const country = (): Grid => {
  const rnd = mulberry(5);
  const harm = Array.from({length: 6}, () => [rnd() * 0.12, rnd() * Math.PI * 2]);
  const radius = (th: number) => 1 + harm.reduce((s, [a, ph], k) => s + a * Math.sin((k + 2) * th + ph), 0);
  const cx = 1010;
  const cy = 560;
  const rx = 520;
  const ry = 400;
  const outline = Array.from({length: 120}, (_, i) => {
    const th = (i / 120) * Math.PI * 2;
    return `${(cx + Math.cos(th) * rx * radius(th)).toFixed(1)},${(cy + Math.sin(th) * ry * radius(th)).toFixed(1)}`;
  }).join(' ');
  const inside = (x: number, y: number) => {
    const th = Math.atan2((y - cy) / ry, (x - cx) / rx);
    return Math.hypot((x - cx) / rx, (y - cy) / ry) < radius(th) * 0.9;
  };
  const nodes: Grid['nodes'] = [];
  for (let tries = 0; nodes.length < 44 && tries < 5000; tries++) {
    const x = cx + (rnd() * 2 - 1) * rx;
    const y = cy + (rnd() * 2 - 1) * ry;
    if (inside(x, y) && nodes.every((n) => Math.hypot(n.x - x, n.y - y) > 72)) nodes.push({x, y, load: 0.6 + rnd() * rnd() * 1.6, spare: 0.4 + rnd() * 1.2});
  }
  const edges = new Set<string>();
  nodes.forEach((n, i) => {
    nodes.map((m, j) => [j, Math.hypot(m.x - n.x, m.y - n.y)] as const).filter(([j]) => j !== i).sort((a, b) => a[1] - b[1]).slice(0, 3)
      .forEach(([j]) => edges.add(i < j ? `${i}-${j}` : `${j}-${i}`));
  });
  const list = [...edges].map((e) => e.split('-').map(Number) as [number, number]);
  // the first fault: a busy hub near the middle
  const degree = nodes.map((_, i) => list.filter(([a, b]) => a === i || b === i).length);
  const first = nodes.map((n, i) => [i, degree[i] * n.load - Math.hypot(n.x - cx, n.y - cy) / 200] as const).sort((a, b) => b[1] - a[1])[0][0];
  return {outline, nodes, edges: list, first};
};

export const GRID = country();
const neighbours = GRID.nodes.map((_, i) => GRID.edges.filter(([a, b]) => a === i || b === i).map(([a, b]) => (a === i ? b : a)));

const CASCADES = new Map<number, Cascade>();
export const cascade = (margin: number): Cascade => {
  if (CASCADES.has(margin)) return CASCADES.get(margin)!;
  const load = GRID.nodes.map((n) => n.load);
  const cap = GRID.nodes.map((n) => n.load * (1 + margin * n.spare));
  const dead = new Set<number>();
  const steps: Cascade['steps'] = [];
  let failing = [GRID.first];
  while (failing.length) {
    failing.forEach((i) => dead.add(i));
    for (const i of failing) {
      // most of what it carried goes to the neighbours still up, in proportion to what each can take
      const alive = neighbours[i].filter((j) => !dead.has(j));
      const room = alive.reduce((s, j) => s + cap[j], 0);
      for (const j of alive) load[j] += (TRANSFER * load[i] * cap[j]) / room;
    }
    steps.push({down: [...failing], load: [...load]});
    failing = GRID.nodes.map((_, i) => i).filter((i) => !dead.has(i) && load[i] > cap[i]);
  }
  const out = {steps};
  CASCADES.set(margin, out);
  return out;
};

const total = GRID.nodes.reduce((s, n) => s + n.load, 0);

const View: FC<WorldProps> = ({g, worldT, o}) => {
  const margin = param(g, 'margin', 0.2);
  const c = cascade(margin);
  const failAt = (g.cues?.fail ?? g.since + 3) - g.since;            // seconds into this world
  const k = Math.floor((worldT - failAt) / STEP);                    // the wave of failures we are at (−1: none yet)
  const down = new Set<number>(c.steps.slice(0, Math.max(0, k + 1)).flatMap((s) => s.down));
  const load = k >= 0 ? c.steps[Math.min(k, c.steps.length - 1)].load : GRID.nodes.map((n) => n.load);
  const dark = GRID.nodes.reduce((s, n, i) => s + (down.has(i) ? n.load : 0), 0) / total;
  const ratio = (i: number) => load[i] / (GRID.nodes[i].load * (1 + margin * GRID.nodes[i].spare));
  const heat = (r: number) => (r < 0.88 ? '#3ddc84' : r < 0.97 ? '#f5b324' : '#ff4b4b');
  const showLoad = o('load');
  const flow = (worldT * 60) % 40;
  const first = GRID.nodes[GRID.first];
  return (
    <AbsoluteFill style={{background: '#060a14'}}>
      <svg width={W} height={H} style={{position: 'absolute'}}>
        <polygon points={GRID.outline} fill="#0f1726" stroke="#2b3c5c" strokeWidth={3} />
        {GRID.edges.map(([a, b], n) => {
          const off = down.has(a) || down.has(b);
          const r = Math.max(ratio(a), ratio(b));
          const colour = off ? '#2a3140' : showLoad > 0.3 ? heat(r) : '#5b7fb8';
          return (
            <line key={n} x1={GRID.nodes[a].x} y1={GRID.nodes[a].y} x2={GRID.nodes[b].x} y2={GRID.nodes[b].y} stroke={colour}
                  strokeWidth={off ? 2 : 3 + 2 * showLoad} strokeDasharray={off ? '4 8' : '14 26'} strokeDashoffset={off ? 0 : -flow} opacity={off ? 0.6 : 0.9} />
          );
        })}
        {GRID.nodes.map((n, i) => {
          const off = down.has(i);
          const when = c.steps.findIndex((s) => s.down.includes(i));
          const flash = off ? interpolate(worldT - (failAt + when * STEP), [0, 0.5], [1, 0], clamp) : 0;
          const glow = 14 + n.load * 18;
          return (
            <g key={i}>
              {!off && <circle cx={n.x} cy={n.y} r={glow * 1.8} fill="#ffcf73" opacity={0.12} />}
              {!off && <circle cx={n.x} cy={n.y} r={glow * 0.7} fill="#ffd98f" opacity={0.35} />}
              {flash > 0 && <circle cx={n.x} cy={n.y} r={glow * (1 + 2 * (1 - flash))} fill="none" stroke="#ff4b4b" strokeWidth={4} opacity={flash} />}
              <rect x={n.x - 6} y={n.y - 6} width={12} height={12} fill={off ? '#3a4050' : showLoad > 0.3 ? heat(ratio(i)) : '#e8eef8'} stroke="#060a14" strokeWidth={2} />
            </g>
          );
        })}
        {o('fail') > 0 && (
          <g opacity={o('fail')}>
            <circle cx={first.x} cy={first.y} r={40} fill="none" stroke={C.accent} strokeWidth={4} />
            <text x={first.x + 50} y={first.y - 30} fill={C.text} fontFamily='"Barlow Condensed", sans-serif' fontWeight={800} fontSize={30}
                  style={{textTransform: 'uppercase'}}>{tx('failsHere')}</text>
          </g>
        )}
      </svg>
      <Big o={o('cascade')} label={tx('blackout')} value={`${Math.round(dark * 100)} %`} color={dark > 0.3 ? C.red : C.accent}
           sub={tx('substationsDown', {n: down.size, m: GRID.nodes.length})} style={{right: 48, top: 52, width: 340}} />
      <Panel o={showLoad} style={{right: 48, bottom: 70}}>
        <Label>{tx('lineLoad')}</Label>
        <div style={{display: 'flex', gap: 18, marginTop: 8, fontSize: 20, fontWeight: 700, textTransform: 'uppercase'}}>
          {[['#3ddc84', tx('fine')], ['#f5b324', '90 %'], ['#ff4b4b', tx('limit')]].map(([colour, name]) => (
            <span key={name} style={{display: 'flex', alignItems: 'center', gap: 8}}><span style={{width: 26, height: 5, background: colour}} />{name}</span>
          ))}
        </div>
      </Panel>
      <Note>{tx('gridNote', {n: GRID.nodes.length, m: Math.round(margin * 100)})}</Note>
    </AbsoluteFill>
  );
};

// a relay click at every wave of failures
const sounds = (g: WorldProps['g'], length: number) => {
  const c = cascade(param(g, 'margin', 0.2));
  const failAt = (g.cues?.fail ?? g.since + 3) - g.since;
  const t0 = g.at - g.since;
  return {clicks: c.steps.map((_, k) => failAt + k * STEP - t0).filter((s) => s >= 0 && s < length)};
};

export const red: World = {View, sounds};
