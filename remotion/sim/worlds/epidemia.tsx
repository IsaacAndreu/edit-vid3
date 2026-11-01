// The epidemic explained, one idea per scene (all deterministic, seeded):
//  arbol      the infection tree from one case: R < 1 the branches die out, R = 1 one line goes on, R > 1 it opens
//             (`r`: 0.8 | 1 | 3; `contactos`: pocos | muchos — the same, told as contacts a day)
//  doble      ×2 every 5 days: the counter and a chart that looks flat for weeks and then shoots up
//  oculto     what you see today (the cases with symptoms a week later) against what there really is
//  palancas   an R meter and four levers that lower it; as it crosses 1 the red patch shrinks
//  caminos    quick vignettes — an office, a full bus, a wedding, a school, someone at work with a fever — first
//             with few crossings, then with many
//  inmunidad  herd immunity on a grid: the immune (blue) around the sick break the chain; `virus`: gripe | sarampion,
//             `inmunes`: the share; a baby in the middle
import type {FC, ReactElement} from 'react';
import {AbsoluteFill, interpolate} from 'remotion';
import {C, FONT, Label, Panel} from '../hud';
import {addWords, num, tx} from '../i18n';
import {mulberry, param, type WorldProps} from '../world';

addWords({
  treeTitle: {es: 'Cada enfermo contagia a {r} de media', pt: 'Cada doente infecta {r} em média', fr: 'Chaque malade en contamine {r} en moyenne', de: 'Jeder Kranke steckt im Schnitt {r} an', en: 'Each case infects {r} on average'},
  dies: {es: 'Se apaga sola', pt: 'Apaga-se sozinha', fr: 'Elle s’éteint seule', de: 'Sie erlischt von selbst', en: 'It dies out'},
  rHolds: {es: 'Se mantiene', pt: 'Mantém-se', fr: 'Elle se maintient', de: 'Sie hält sich', en: 'It holds steady'},
  grows: {es: 'Se multiplica', pt: 'Multiplica-se', fr: 'Elle se multiplie', de: 'Sie vervielfacht sich', en: 'It multiplies'},
  infectedSoFar: {es: 'Contagiados', pt: 'Infectados', fr: 'Contaminés', de: 'Angesteckt', en: 'Infected'},
  fewContacts: {es: 'Pocos contactos al día', pt: 'Poucos contatos por dia', fr: 'Peu de contacts par jour', de: 'Wenige Kontakte am Tag', en: 'Few contacts a day'},
  manyContacts: {es: 'Muchos contactos al día', pt: 'Muitos contatos por dia', fr: 'Beaucoup de contacts par jour', de: 'Viele Kontakte am Tag', en: 'Many contacts a day'},
  sameVirus: {es: 'Mismo virus', pt: 'Mesmo vírus', fr: 'Même virus', de: 'Dasselbe Virus', en: 'Same virus'},
  everyFive: {es: 'Cada 5 días ×2', pt: 'A cada 5 dias ×2', fr: 'Tous les 5 jours ×2', de: 'Alle 5 Tage ×2', en: 'Every 5 days ×2'},
  dayN: {es: 'Día {d}', pt: 'Dia {d}', fr: 'Jour {d}', de: 'Tag {d}', en: 'Day {d}'},
  cases: {es: 'casos', pt: 'casos', fr: 'cas', de: 'Fälle', en: 'cases'},
  seeToday: {es: 'Lo que ves hoy', pt: 'O que você vê hoje', fr: 'Ce que tu vois aujourd’hui', de: 'Was du heute siehst', en: 'What you see today'},
  reallyThere: {es: 'Lo que hay de verdad', pt: 'O que há de verdade', fr: 'Ce qu’il y a vraiment', de: 'Was wirklich da ist', en: 'What is really there'},
  weekAgo: {es: 'La foto de hace una semana', pt: 'A foto de uma semana atrás', fr: 'La photo d’il y a une semaine', de: 'Das Bild von vor einer Woche', en: 'A picture from a week ago'},
  noSymptoms: {es: 'Sin síntomas, pero contagian', pt: 'Sem sintomas, mas contagiam', fr: 'Sans symptômes, mais contagieux', de: 'Ohne Symptome, aber ansteckend', en: 'No symptoms, but contagious'},
  leverHome: {es: 'Quedarse en casa enfermo', pt: 'Ficar em casa doente', fr: 'Rester chez soi malade', de: 'Krank zu Hause bleiben', en: 'Stay home when sick'},
  leverHands: {es: 'Lavarse las manos', pt: 'Lavar as mãos', fr: 'Se laver les mains', de: 'Hände waschen', en: 'Wash your hands'},
  leverAir: {es: 'Ventilar', pt: 'Ventilar', fr: 'Aérer', de: 'Lüften', en: 'Open a window'},
  leverCrowd: {es: 'Evitar sitios cerrados y llenos', pt: 'Evitar lugares fechados e cheios', fr: 'Éviter les lieux clos et bondés', de: 'Volle, geschlossene Räume meiden', en: 'Avoid closed, crowded places'},
  rMeter: {es: 'Número R', pt: 'Número R', fr: 'Nombre R', de: 'R-Wert', en: 'R number'},
  office: {es: 'Oficina cerrada', pt: 'Escritório fechado', fr: 'Bureau fermé', de: 'Geschlossenes Büro', en: 'Closed office'},
  bus: {es: 'Autobús lleno', pt: 'Ônibus cheio', fr: 'Bus bondé', de: 'Voller Bus', en: 'Packed bus'},
  wedding: {es: 'Boda en un local pequeño', pt: 'Casamento num salão pequeno', fr: 'Mariage dans une petite salle', de: 'Hochzeit im kleinen Saal', en: 'Wedding in a small hall'},
  school: {es: 'Colegio', pt: 'Escola', fr: 'École', de: 'Schule', en: 'School'},
  fever: {es: 'A trabajar con fiebre', pt: 'Trabalhar com febre', fr: 'Au travail avec de la fièvre', de: 'Mit Fieber zur Arbeit', en: 'At work with a fever'},
  fewCrossings: {es: 'Pocos cruces', pt: 'Poucos cruzamentos', fr: 'Peu de croisements', de: 'Wenige Begegnungen', en: 'Few crossings'},
  manyCrossings: {es: 'Muchos cruces', pt: 'Muitos cruzamentos', fr: 'Beaucoup de croisements', de: 'Viele Begegnungen', en: 'Many crossings'},
  herdTitle: {es: 'Inmunidad de grupo', pt: 'Imunidade de grupo', fr: 'Immunité collective', de: 'Herdenimmunität', en: 'Herd immunity'},
  immuneShare: {es: '{p} % inmunes', pt: '{p} % imunes', fr: '{p} % immunisés', de: '{p} % immun', en: '{p} % immune'},
  flu: {es: 'Gripe · umbral ≈ {p} %', pt: 'Gripe · limiar ≈ {p} %', fr: 'Grippe · seuil ≈ {p} %', de: 'Grippe · Schwelle ≈ {p} %', en: 'Flu · threshold ≈ {p} %'},
  measles: {es: 'Sarampión · más del {p} %', pt: 'Sarampo · mais de {p} %', fr: 'Rougeole · plus de {p} %', de: 'Masern · über {p} %', en: 'Measles · over {p} %'},
  baby: {es: 'Bebé', pt: 'Bebê', fr: 'Bébé', de: 'Baby', en: 'Baby'},
  chainBreaks: {es: 'La cadena se rompe sola', pt: 'A cadeia se rompe sozinha', fr: 'La chaîne se rompt seule', de: 'Die Kette reißt von selbst', en: 'The chain breaks on its own'},
  chainGoes: {es: 'La cadena pasa', pt: 'A cadeia passa', fr: 'La chaîne passe', de: 'Die Kette läuft weiter', en: 'The chain gets through'},
});

const BG = 'radial-gradient(ellipse at 50% 40%, #16213a 0%, #0a0f1c 75%)';
const big = (text: string, colour: string = C.text) => (
  <div style={{fontFamily: FONT, fontSize: 64, fontWeight: 800, color: colour, textTransform: 'uppercase', lineHeight: 1}}>{text}</div>
);

// --- the infection tree --------------------------------------------------------------------------------------------

type Node = {g: number; parent: number; x: number; y: number; kids: number};
const poisson = (rnd: () => number, l: number) => {
  let k = 0;
  let p = Math.exp(-l);
  let s = p;
  const u = rnd();
  while (u > s && k < 20) { k++; p *= l / k; s += p; }
  return k;
};
const TREES = new Map<string, {nodes: Node[]; total: number}>();
export const tree = (r: number) => {
  const key = String(r);
  if (TREES.has(key)) return TREES.get(key)!;
  // a seed whose tree tells the story: R < 1 dies within 3-4 generations, R > 1 opens wide
  const make = (seed: number) => {
    const rnd = mulberry(seed);
    const gens: number[][] = [[0]];
    const nodes: Node[] = [{g: 0, parent: -1, x: 0, y: 0, kids: 0}];
    let total = 1;
    for (let g = 1; g <= 7; g++) {
      const next: number[] = [];
      for (const i of gens[g - 1]) {
        const k = r === 1 ? 1 : poisson(rnd, r);
        nodes[i].kids = k;
        total += k;
        for (let c = 0; c < k && next.length < 90; c++) {
          nodes.push({g, parent: i, x: 0, y: 0, kids: 0});
          next.push(nodes.length - 1);
        }
      }
      gens.push(next);
      if (!next.length) break;
    }
    return {nodes, gens, total};
  };
  let best = make(1);
  for (let seed = 1; seed < 200; seed++) {
    const t = make(seed);
    const depth = t.gens.filter((g) => g.length).length;
    if (r < 1 ? depth >= 3 && depth <= 4 : r > 1 ? t.gens[3]?.length >= 18 : true) { best = t; break; }
  }
  best.gens.forEach((ids, g) => ids.forEach((id, k) => {
    best.nodes[id].x = 180 + g * 230;
    best.nodes[id].y = 560 + (k - (ids.length - 1) / 2) * Math.min(80, 760 / Math.max(1, ids.length));
  }));
  const out = {nodes: best.nodes, total: best.total};
  TREES.set(key, out);
  return out;
};

export const Tree: FC<WorldProps> = ({g, worldT}) => {
  const contacts = param<string>(g, 'contactos', '');
  const r = contacts ? (contacts === 'muchos' ? 3 : 0.8) : Number(param(g, 'r', 3));
  const {nodes} = tree(r);
  const shown = worldT / 0.8;                         // a generation every 0.8 s
  const visible = nodes.filter((n) => n.g <= shown);
  const last = Math.max(...visible.map((n) => n.g));
  const label = r < 1 ? 'R < 1' : r === 1 ? 'R = 1' : 'R > 1';
  const colour = r < 1 ? C.green : r === 1 ? '#f5b324' : C.red;
  return (
    <AbsoluteFill style={{background: BG}}>
      <svg width={1920} height={1080} style={{position: 'absolute'}}>
        {visible.filter((n) => n.parent >= 0).map((n, i) => {
          const p = nodes[n.parent];
          const grow = Math.min(1, shown - n.g + 1);
          return <line key={`l${i}`} x1={p.x} y1={p.y} x2={p.x + (n.x - p.x) * grow} y2={p.y + (n.y - p.y) * grow} stroke="rgba(255,93,93,0.5)" strokeWidth={3} />;
        })}
        {visible.map((n, i) => {
          const active = n.g === Math.floor(shown);
          const dead = n.g < Math.floor(shown) && n.kids === 0;
          return (
            <g key={i}>
              {active && <circle cx={n.x} cy={n.y} r={22} fill={C.red} opacity={0.25} />}
              <circle cx={n.x} cy={n.y} r={i === 0 ? 16 : 11} fill={active ? C.red : '#8a93a6'} stroke="#0b1020" strokeWidth={2} />
              {dead && <path d={`M ${n.x + 16} ${n.y - 8} l 12 12 m 0 -12 l -12 12`} stroke="#8a93a6" strokeWidth={3} />}
            </g>
          );
        })}
      </svg>
      <Panel o={1} style={{left: 60, top: 50}}>
        {big(label, colour)}
        <Label>{contacts ? `${tx(contacts === 'muchos' ? 'manyContacts' : 'fewContacts')} · ${tx('sameVirus')} · R ≈ ${String(r).replace('.', ',')}`
          : tx('treeTitle', {r: String(r).replace('.', ',')})}</Label>
      </Panel>
      <Panel o={Math.min(1, shown / 3)} style={{right: 60, top: 50, width: 340}}>
        <Label>{tx('infectedSoFar')}</Label>
        <div style={{fontSize: 56, fontWeight: 800, color: colour}}>{num(visible.length)}</div>
        <Label>{tx(r < 1 ? 'dies' : r === 1 ? 'rHolds' : 'grows')}</Label>
      </Panel>
      {void last}
    </AbsoluteFill>
  );
};

// --- doubling ------------------------------------------------------------------------------------------------------

export const Doubling: FC<WorldProps> = ({worldT}) => {
  const day = Math.min(90, worldT * 9);
  const cases = Math.round(2 ** (day / 5));
  const W = 1300;
  const H = 560;
  const max = 2 ** 18;
  const pts: string[] = [];
  for (let d = 0; d <= day; d += 0.5) pts.push(`${(d / 90) * W},${H - (2 ** (d / 5) / max) * H}`);
  return (
    <AbsoluteFill style={{background: BG}}>
      <Panel o={1} style={{left: 60, top: 60, width: 420}}>
        {big(tx('everyFive'), C.red)}
        <Label>{tx('dayN', {d: Math.floor(day)})}</Label>
        <div style={{fontFamily: FONT, fontSize: 96, fontWeight: 800, color: C.text, fontVariantNumeric: 'tabular-nums'}}>{num(cases)}</div>
        <Label>{tx('cases')}</Label>
      </Panel>
      <svg width={1920} height={1080} style={{position: 'absolute'}}>
        <g transform="translate(540 260)">
          <line x1={0} y1={H} x2={W} y2={H} stroke="#8a93a6" strokeWidth={2} />
          <line x1={0} y1={0} x2={0} y2={H} stroke="#8a93a6" strokeWidth={2} />
          {[0, 30, 60, 90].map((d) => <text key={d} x={(d / 90) * W} y={H + 34} textAnchor="middle" fill={C.label} fontFamily={FONT} fontSize={26}>{tx('dayN', {d})}</text>)}
          <polyline points={pts.join(' ')} fill="none" stroke={C.red} strokeWidth={6} strokeLinejoin="round" />
        </g>
      </svg>
    </AbsoluteFill>
  );
};

// --- what you see against what there is ----------------------------------------------------------------------------

const FIELD = (() => {
  const rnd = mulberry(77);
  return Array.from({length: 320}, (_, i) => ({x: rnd(), y: rnd(), day: 2 + Math.log(1 + i) * 7 + rnd() * 3}));   // infected on `day`
})();

export const Hidden: FC<WorldProps> = ({worldT}) => {
  const today = Math.min(40, 14 + worldT * 2);       // a fortnight in to day 40: the gap opens and stays
  const half = (real: boolean) => (
    <svg width={900} height={720} style={{position: 'absolute', left: real ? 990 : 30, top: 260}}>
      <rect width={900} height={720} rx={14} fill="#121a2e" />
      {FIELD.map((p, i) => {
        const infected = p.day <= today;
        const visible = p.day <= today - 7;                  // symptoms, a test, a number in the news: a week later
        const silent = infected && !visible;
        const show = real ? infected : visible;
        return (
          <circle key={i} cx={30 + p.x * 840} cy={30 + p.y * 660} r={9}
                  fill={show && !(real && silent) ? C.red : '#c9d3e6'} stroke={real && silent ? C.red : 'none'} strokeWidth={real && silent ? 4 : 0}
                  fillOpacity={real && silent ? 0.25 : 1} />
        );
      })}
    </svg>
  );
  const seen = FIELD.filter((p) => p.day <= today - 7).length;
  const real = FIELD.filter((p) => p.day <= today).length;
  return (
    <AbsoluteFill style={{background: BG}}>
      {half(false)}
      {half(true)}
      <div style={{position: 'absolute', left: 30, top: 120}}>{big(tx('seeToday'))}<Label>{tx('weekAgo')} · {num(seen)}</Label></div>
      <div style={{position: 'absolute', left: 990, top: 120}}>{big(tx('reallyThere'), C.red)}<Label>{num(real)} · ○ {tx('noSymptoms')}</Label></div>
    </AbsoluteFill>
  );
};

// --- the levers that lower R ---------------------------------------------------------------------------------------

const LEVERS: [string, number][] = [['leverHome', 0.6], ['leverHands', 0.85], ['leverAir', 0.75], ['leverCrowd', 0.8]];
const R0 = 2.6;

export const Levers: FC<WorldProps> = ({g, worldT}) => {
  const set = Math.floor(Number(param(g, 'palancas', -1)));
  const on = Math.min(4, Math.max(0, set >= 0 ? set : Math.floor(worldT / 2.2)));
  let r = R0;
  for (let i = 0; i < on; i++) r *= LEVERS[i][1];
  const shown = interpolate(worldT % 2.2, [0, 0.8], [0, 1], {extrapolateRight: 'clamp'});
  const prev = LEVERS.slice(0, Math.max(0, on - 1)).reduce((a, [, k]) => a * k, R0);
  const value = on ? prev + (r - prev) * shown : r;
  const angle = -120 + (Math.min(4, value) / 4) * 240;
  const red = Math.max(0.05, Math.min(1, (value - 0.6) / 2.2));
  const rnd = mulberry(5);
  const town = Array.from({length: 180}, () => [rnd(), rnd()] as [number, number]);
  return (
    <AbsoluteFill style={{background: BG}}>
      <svg width={1920} height={1080} style={{position: 'absolute'}}>
        <g transform="translate(480 520)">
          {Array.from({length: 41}, (_, i) => {
            const a = ((-120 + i * 6) * Math.PI) / 180;
            const v = i / 10;
            return <line key={i} x1={Math.sin(a) * 300} y1={-Math.cos(a) * 300} x2={Math.sin(a) * (i % 10 ? 280 : 255)} y2={-Math.cos(a) * (i % 10 ? 280 : 255)}
                         stroke={v < 1 ? C.green : C.red} strokeWidth={i % 10 ? 3 : 6} />;
          })}
          {[0, 1, 2, 3, 4].map((v) => { const a = ((-120 + v * 60) * Math.PI) / 180;
            return <text key={v} x={Math.sin(a) * 215} y={-Math.cos(a) * 215 + 12} textAnchor="middle" fill={C.text} fontFamily={FONT} fontSize={40} fontWeight={800}>{v}</text>; })}
          <line x1={0} y1={0} x2={Math.sin((angle * Math.PI) / 180) * 250} y2={-Math.cos((angle * Math.PI) / 180) * 250} stroke={value < 1 ? C.green : C.red} strokeWidth={12} strokeLinecap="round" />
          <circle r={24} fill="#e6e9ef" />
          <text y={150} textAnchor="middle" fill={value < 1 ? C.green : C.red} fontFamily={FONT} fontSize={110} fontWeight={800}>R = {value.toFixed(1).replace('.', ',')}</text>
        </g>
        {town.map(([x, y], i) => <circle key={i} cx={1040 + x * 760} cy={600 + y * 380} r={9} fill={i / town.length < red * 0.7 ? C.red : '#c9d3e6'} />)}
      </svg>
      <div style={{position: 'absolute', left: 1040, top: 110, width: 780}}>
        <Label>{tx('rMeter')}</Label>
        {LEVERS.map(([name], i) => (
          <div key={name} style={{display: 'flex', alignItems: 'center', gap: 18, marginTop: 14, fontFamily: FONT, fontSize: 38, fontWeight: 800,
                                  color: i < on ? C.text : 'rgba(255,255,255,0.35)', textTransform: 'uppercase'}}>
            <span style={{width: 74, height: 38, borderRadius: 19, background: i < on ? C.green : '#3a4256', position: 'relative'}}>
              <span style={{position: 'absolute', top: 4, left: i < on ? 40 : 4, width: 30, height: 30, borderRadius: 15, background: '#fff'}} /></span>
            {tx(name)}
          </div>
        ))}
      </div>
    </AbsoluteFill>
  );
};

// --- where it travels: five vignettes, few crossings then many -----------------------------------------------------

const VIGNETTES = ['office', 'bus', 'wedding', 'school', 'fever'];

const Vignette: FC<{kind: string; many: boolean; t: number; x: number; y: number; seed: number}> = ({kind, many, t, x, y, seed}) => {
  const rnd = mulberry(seed);
  const n = many ? 26 : 7;
  const people = Array.from({length: n}, () => [30 + rnd() * 500, 60 + rnd() * 230] as [number, number]);
  // the red spreads from the first one to whoever is near, faster the more there are
  const reach = many ? t * 90 : t * 18;
  const room: ReactElement[] = [];
  if (kind === 'office') for (let i = 0; i < 6; i++) room.push(<rect key={i} x={50 + (i % 3) * 170} y={80 + Math.floor(i / 3) * 120} width={120} height={50} rx={4} fill="#d8d6d0" />);
  if (kind === 'bus') room.push(<rect key="b" x={20} y={70} width={520} height={220} rx={40} fill="#f2c94c" />, ...Array.from({length: 10}, (_, i) => <rect key={i} x={50 + (i % 5) * 95} y={95 + Math.floor(i / 5) * 120} width={60} height={50} rx={6} fill="#c79a2a" />));
  if (kind === 'wedding') for (let i = 0; i < 4; i++) room.push(<circle key={i} cx={110 + (i % 2) * 300} cy={130 + Math.floor(i / 2) * 120} r={50} fill="#efe6d8" />);
  if (kind === 'school') for (let i = 0; i < 8; i++) room.push(<rect key={i} x={50 + (i % 4) * 125} y={90 + Math.floor(i / 4) * 110} width={80} height={44} fill="#b08a5a" />);
  if (kind === 'fever') room.push(<rect key="f" x={40} y={80} width={480} height={200} rx={8} fill="#cfd4dc" />,
    <text key="t" x={280} y={190} textAnchor="middle" fontSize={90}>🤒</text>);
  return (
    <g transform={`translate(${x} ${y})`}>
      <rect width={560} height={320} rx={16} fill="#1b2438" />
      {room}
      {people.map(([px, py], i) => {
        const d = Math.hypot(px - people[0][0], py - people[0][1]);
        return <circle key={i} cx={px} cy={py} r={11} fill={i === 0 || d < reach ? C.red : '#e6e9ef'} stroke="#0b1020" strokeWidth={2} />;
      })}
      <text x={20} y={40} fill={C.text} fontFamily={FONT} fontSize={32} fontWeight={800} style={{textTransform: 'uppercase'}}>{tx(kind)}</text>
    </g>
  );
};

export const Paths: FC<WorldProps> = ({g, worldT, length}) => {
  const forced = param<string>(g, 'mezcla', '');
  const many = forced ? forced === 'muchos' : worldT > length / 2;
  const t = many && !forced ? worldT - length / 2 : worldT;
  return (
    <AbsoluteFill style={{background: BG}}>
      <svg width={1920} height={1080} style={{position: 'absolute'}}>
        {VIGNETTES.map((kind, i) => <Vignette key={kind} kind={kind} many={many} t={t} x={60 + (i % 3) * 610} y={180 + Math.floor(i / 3) * 400} seed={11 + i} />)}
      </svg>
      <div style={{position: 'absolute', left: 60, top: 60}}>{big(tx(many ? 'manyCrossings' : 'fewCrossings'), many ? C.red : C.text)}</div>
    </AbsoluteFill>
  );
};

// --- herd immunity on a grid ---------------------------------------------------------------------------------------

const COLS = 34;
const ROWS = 18;
const HERDS = new Map<string, {immune: boolean[]; infectedAt: number[]; baby: number}>();
export const herd = (virus: string, share: number) => {
  const key = `${virus}:${share}`;
  if (HERDS.has(key)) return HERDS.get(key)!;
  const rnd = mulberry(29);
  const n = COLS * ROWS;
  const baby = Math.floor(ROWS / 2) * COLS + Math.floor(COLS / 2) + 3;
  const immune = Array.from({length: n}, (_, i) => i !== baby && rnd() < share);
  const seed = Math.floor(ROWS / 2) * COLS + 4;
  immune[seed] = false;
  // each case reaches its neighbours: flu the 8 around (R ≈ 1.6 in a crowd), measles everyone 2 cells away (R ≈ 15)
  const radius = virus === 'sarampion' ? 2.3 : 1.5;
  const p = virus === 'sarampion' ? 0.85 : 0.22;
  const infectedAt = Array(n).fill(-1);
  infectedAt[seed] = 0;
  let front = [seed];
  for (let gen = 1; front.length && gen < 60; gen++) {
    const next: number[] = [];
    for (const i of front) {
      const [x, y] = [i % COLS, Math.floor(i / COLS)];
      for (let dy = -3; dy <= 3; dy++) for (let dx = -3; dx <= 3; dx++) {
        const j = (y + dy) * COLS + (x + dx);
        if (y + dy < 0 || y + dy >= ROWS || x + dx < 0 || x + dx >= COLS || Math.hypot(dx, dy) > radius || infectedAt[j] >= 0 || immune[j]) continue;
        if (rnd() < p) { infectedAt[j] = gen; next.push(j); }
      }
    }
    front = next;
  }
  const out = {immune, infectedAt, baby};
  HERDS.set(key, out);
  return out;
};

export const Herd: FC<WorldProps> = ({g, worldT}) => {
  const virus = param<string>(g, 'virus', 'gripe');
  const given = Number(param(g, 'inmunes', 'auto'));
  const share = Number.isFinite(given) ? given : virus === 'sarampion' ? 0.93 : 0.4;
  const {immune, infectedAt, baby} = herd(virus, share);
  const gen = worldT * 3;
  const reached = infectedAt[baby] >= 0 && infectedAt[baby] <= gen;
  const total = infectedAt.filter((x) => x >= 0).length;
  const done = gen > Math.max(...infectedAt);
  return (
    <AbsoluteFill style={{background: BG}}>
      <svg width={1920} height={1080} style={{position: 'absolute'}}>
        {immune.map((imm, i) => {
          const x = 140 + (i % COLS) * 48;
          const y = 260 + Math.floor(i / COLS) * 42;
          const sick = infectedAt[i] >= 0 && infectedAt[i] <= gen;
          const active = sick && gen - infectedAt[i] < 3;
          if (i === baby) return (
            <g key={i}><circle cx={x} cy={y} r={20} fill="none" stroke={C.you} strokeWidth={3} />
              <circle cx={x} cy={y} r={8} fill={reached ? C.red : '#fff3c4'} />
              <text x={x} y={y - 26} textAnchor="middle" fill={C.you} fontFamily={FONT} fontSize={24} fontWeight={800} style={{textTransform: 'uppercase'}}>{tx('baby')}</text></g>);
          return <circle key={i} cx={x} cy={y} r={active ? 14 : 12} fill={imm ? '#5b8def' : active ? C.red : sick ? '#8a93a6' : '#e6e9ef'} />;
        })}
      </svg>
      <Panel o={1} style={{left: 60, top: 40}}>
        {big(tx('herdTitle'))}
        <Label>{tx(virus === 'sarampion' ? 'measles' : 'flu', {p: virus === 'sarampion' ? 90 : 40})} · {tx('immuneShare', {p: Math.round(share * 100)})}</Label>
      </Panel>
      <Panel o={done ? 1 : 0} style={{right: 60, top: 40}}>
        {big(tx(total < 30 ? 'chainBreaks' : 'chainGoes'), total < 30 ? C.green : C.red)}
        <Label>{tx('infectedSoFar')}: {num(total)}</Label>
      </Panel>
    </AbsoluteFill>
  );
};

export const EPIDEMIC_SCENES: Record<string, FC<WorldProps>> = {arbol: Tree, doble: Doubling, oculto: Hidden, palancas: Levers, caminos: Paths, inmunidad: Herd};
