// The airport security lane station by station (remotion/sim/checkpoint.ts), for the scenes a script about it asks for:
//  cadena    one lane from above: the line, the tray table, the belt into the X-ray scanner, the arch, the end of the
//            belt. Each station with what it could let through an hour — the table is the slowest (Herbie) and the
//            scanner, the expensive machine, stands idle with the belt half empty. Over the heads: the bottle, the
//            laptop, the buckle; a beep at the arch sends someone back while their trays block the end of the belt.
//            mesa: 1 (everyone at the same spot, one after another) | 4 (an automated lane: four get ready at once)
//  paralelo  the same passengers, one spot at the table (left) against four (right)
//  pistas    four lanes, everyone mixed (left) against lanes by kind of traveller with ski-slope signs (right)
//  normas    2001 and 2006: why the check got slower, step by step
//  manana    the morning hour by hour: waves of flights, and the line that takes hours to go down
import type {FC} from 'react';
import {AbsoluteFill, interpolate} from 'remotion';
import {C, FONT} from '../hud';
import {addWords, num, tx} from '../i18n';
import {runLane, stationRates, TRAY_SECONDS, TROUBLE, type LaneRun, type Pax} from '../checkpoint';
import {param, type WorldProps} from '../world';
import {Figure, LineChart, Split} from '../scenes';

addWords({
  stLine: {es: 'Cola', pt: 'Fila', fr: 'File', de: 'Schlange', en: 'Line'},
  stTable: {es: 'Mesa de bandejas', pt: 'Mesa das bandejas', fr: 'Table des bacs', de: 'Wannentisch', en: 'Tray table'},
  stScanner: {es: 'Escáner de rayos X', pt: 'Raio X', fr: 'Scanner à rayons X', de: 'Röntgengerät', en: 'X-ray scanner'},
  stArch: {es: 'Arco', pt: 'Pórtico', fr: 'Portique', de: 'Torbogen', en: 'Arch'},
  stPickup: {es: 'Recogida', pt: 'Recolha', fr: 'Récupération', de: 'Abholung', en: 'Pick-up'},
  peopleHour: {es: '{n} personas/h', pt: '{n} pessoas/h', fr: '{n} personnes/h', de: '{n} Personen/h', en: '{n} people/h'},
  traysHour: {es: '{n} bandejas/h ≈ {m} personas/h', pt: '{n} bandejas/h ≈ {m} pessoas/h', fr: '{n} bacs/h ≈ {m} personnes/h', de: '{n} Wannen/h ≈ {m} Personen/h', en: '{n} trays/h ≈ {m} people/h'},
  scannerIdle: {es: 'Escáner parado', pt: 'Raio X parado', fr: 'Scanner à l’arrêt', de: 'Röntgengerät steht', en: 'Scanner idle'},
  idleNow: {es: 'Esperando bandejas', pt: 'À espera de bandejas', fr: 'Attend des bacs', de: 'Wartet auf Wannen', en: 'Waiting for trays'},
  waitTable: {es: 'Espera hasta la mesa', pt: 'Espera até a mesa', fr: 'Attente jusqu’à la table', de: 'Wartezeit bis zum Tisch', en: 'Wait to reach the table'},
  throughput: {es: 'Pasan por hora', pt: 'Passam por hora', fr: 'Passent par heure', de: 'Pro Stunde durch', en: 'Through per hour'},
  oneSpot: {es: 'Uno a uno en la misma mesa', pt: 'Um a um na mesma mesa', fr: 'Un par un à la même table', de: 'Einer nach dem anderen am Tisch', en: 'One at a time at the table'},
  fourSpots: {es: 'Cuatro puestos a la vez', pt: 'Quatro postos ao mesmo tempo', fr: 'Quatre postes à la fois', de: 'Vier Plätze gleichzeitig', en: 'Four spots at once'},
  beep: {es: '¡Pita!', pt: 'Apita!', fr: 'Ça sonne !', de: 'Piept!', en: 'Beep!'},
  mixed: {es: 'Todos mezclados', pt: 'Todos misturados', fr: 'Tout le monde mélangé', de: 'Alle gemischt', en: 'Everyone mixed'},
  byKind: {es: 'Carriles por tipo de viajero', pt: 'Faixas por tipo de viajante', fr: 'Files par type de voyageur', de: 'Spuren nach Reisetyp', en: 'Lanes by kind of traveller'},
  kExpert: {es: 'Expertos', pt: 'Experientes', fr: 'Habitués', de: 'Vielflieger', en: 'Experts'},
  kCasual: {es: 'Ocasionales', pt: 'Ocasionais', fr: 'Occasionnels', de: 'Gelegentliche', en: 'Casual'},
  kFamily: {es: 'Familias y más tiempo', pt: 'Famílias e mais tempo', fr: 'Familles et plus de temps', de: 'Familien und mehr Zeit', en: 'Families, more time'},
  expertsWait: {es: 'Espera de los expertos', pt: 'Espera dos experientes', fr: 'Attente des habitués', de: 'Wartezeit der Vielflieger', en: 'Experts’ wait'},
  everyoneWait: {es: 'Espera media de todos', pt: 'Espera média de todos', fr: 'Attente moyenne de tous', de: 'Mittlere Wartezeit aller', en: 'Everyone’s average wait'},
  rules2001: {es: '11-S: controles mucho más estrictos; EE. UU. crea una agencia solo para eso (TSA)', pt: '11/9: controles muito mais rigorosos; os EUA criam uma agência só para isso (TSA)', fr: '11-Septembre : contrôles bien plus stricts ; les États-Unis créent une agence dédiée (TSA)', de: '9/11: viel strengere Kontrollen; die USA gründen eine eigene Behörde (TSA)', en: '9/11: much stricter checks; the US creates an agency just for that (TSA)'},
  rules2006a: {es: 'Reino Unido desarticula un plan con explosivos líquidos en botellas de bebida', pt: 'O Reino Unido desmantela um plano com explosivos líquidos em garrafas', fr: 'Le Royaume-Uni déjoue un projet d’explosifs liquides dans des bouteilles', de: 'Großbritannien vereitelt einen Plan mit Flüssigsprengstoff in Getränkeflaschen', en: 'The UK foils a plot with liquid explosives in drink bottles'},
  rules2006b: {es: 'Europa: líquidos en envases de 100 ml, en bolsa transparente, fuera de la maleta', pt: 'Europa: líquidos em frascos de 100 ml, em saco transparente, fora da mala', fr: 'Europe : liquides en flacons de 100 ml, sachet transparent, hors du bagage', de: 'Europa: Flüssigkeiten in 100-ml-Behältern, im durchsichtigen Beutel, aus dem Gepäck', en: 'Europe: liquids in 100 ml containers, in a clear bag, out of the case'},
  secRulesTitle: {es: 'Cada norma, unos segundos más por pasajero', pt: 'Cada regra, uns segundos a mais por passageiro', fr: 'Chaque règle, quelques secondes de plus par passager', de: 'Jede Regel: ein paar Sekunden mehr pro Fluggast', en: 'Each rule, a few more seconds per passenger'},
  morningTitle: {es: 'La espera en el control a lo largo de la mañana', pt: 'A espera no controle ao longo da manhã', fr: 'L’attente au contrôle au fil de la matinée', de: 'Wartezeit an der Kontrolle über den Vormittag', en: 'The wait at security through the morning'},
  arrivalTime: {es: 'hora de llegada al control', pt: 'hora de chegada ao controle', fr: 'heure d’arrivée au contrôle', de: 'Ankunftszeit an der Kontrolle', en: 'time you reach security'},
  flightWave: {es: 'Oleada de vuelos', pt: 'Vaga de voos', fr: 'Vague de vols', de: 'Welle von Flügen', en: 'Wave of flights'},
  laneNote: {es: 'Simulación · escáner {n} bandejas/h · tiempo ×{x}', pt: 'Simulação · raio X {n} bandejas/h · tempo ×{x}', fr: 'Simulation · scanner {n} bacs/h · temps ×{x}', de: 'Simulation · Röntgen {n} Wannen/h · Zeit ×{x}', en: 'Simulation · scanner {n} trays/h · time ×{x}'},
});

const LAPSE = 6;                                        // 1 s of video = 6 s at the checkpoint
const RATE = 90 / 3600;                                 // a busy lane: 90 people an hour
const START = 1500;                                     // 25 minutes in: the line has formed
const KIND_COLOURS = ['#4dabf7', '#ff922b', '#51cf66'];
const fmt = (s: number) => (s < 90 ? `${Math.round(s)} s` : `${Math.round(s / 60)} min`);

const queueSpot = (i: number): [number, number] => {
  const row = Math.floor(i / 6);
  const col = row % 2 ? 5 - (i % 6) : i % 6;
  return [560 - col * 84, 860 - row * 84];
};

/** Where a passenger is at time t (or null: not arrived yet, or gone). */
const placeOf = (p: Pax, t: number, inLine: number, tableY: (slot: number) => number, waitIdx: number): [number, number, string] | null => {
  if (t < p.arrive || t >= p.collectEnd) return null;
  if (t < p.prepStart) {
    const [x, y] = queueSpot(inLine);
    return inLine < 36 ? [x, y, 'line'] : null;
  }
  if (t < p.prepEnd) return [800, tableY(p.slot), 'table'];
  const walk = Math.min(1, (t - p.prepEnd) / 4);
  if (t < p.archAt) {
    if (p.beep && t > p.prepEnd + 4) return [1250, 760, 'back'];      // beeped: back, belt off, through again
    return [880 + walk * 420, 760, 'walk'];
  }
  if (t < p.collectStart) return [1560 + (waitIdx % 4) * 70, 790 + Math.floor(waitIdx / 4) * 70, 'wait'];
  return [1640, 640, 'pick'];
};

export const Lane: FC<{run: LaneRun; t: number; small?: boolean}> = ({run, t}) => {
  const rates = stationRates(run.slots);
  const slowTable = rates.table < rates.scanner;
  const tableY = (slot: number) => (run.slots === 1 ? 500 : 290 + slot * 140);
  const line = run.pax.filter((p) => p.arrive <= t && t < p.prepStart).sort((a, b) => a.arrive - b.arrive);
  const lineIdx = new Map(line.map((p, i) => [p.id, i]));
  const waiting = run.pax.filter((p) => p.archAt <= t && t < p.collectStart).sort((a, b) => a.archAt - b.archAt);
  const waitIdx = new Map(waiting.map((p, i) => [p.id, i]));
  // trays: on the belt before the scanner, inside it, at the end of the belt
  const before = run.trays.filter((x) => x.ready <= t && t < x.scanStart).sort((a, b) => a.ready - b.ready);
  const inside = run.trays.find((x) => x.scanStart <= t && t < x.scanEnd);
  const after = run.trays.filter((x) => x.scanEnd <= t && t < run.pax[x.owner].collectEnd).sort((a, b) => a.scanEnd - b.scanEnd);
  const idleSoFar = (() => {
    const from = START;
    let busy = 0;
    for (const x of run.trays) busy += Math.max(0, Math.min(x.scanEnd, t) - Math.max(x.scanStart, from));
    return t > from ? 1 - busy / (t - from) : 0;
  })();
  const recent = run.pax.filter((p) => p.prepStart <= t && p.prepStart > t - 600);
  const wait = recent.length ? recent.reduce((a, p) => a + p.prepStart - p.arrive, 0) / recent.length : 0;
  const station = (x: number, name: string, rate: string, red: boolean) => (
    <g>
      <text x={x} y={86} textAnchor="middle" fill={red ? C.red : C.text} fontFamily={FONT} fontSize={38} fontWeight={800} style={{textTransform: 'uppercase'}}>{name}</text>
      {rate && <text x={x} y={128} textAnchor="middle" fill={red ? C.red : '#9aa3b5'} fontFamily={FONT} fontSize={30} fontWeight={700}>{rate}</text>}
    </g>
  );
  return (
    <svg width={1920} height={1080} style={{position: 'absolute'}}>
      <rect width={1920} height={1080} fill="#d8d4cc" />
      {Array.from({length: 33}, (_, i) => <line key={i} x1={i * 60} x2={i * 60} y1={160} y2={1080} stroke="rgba(0,0,0,0.05)" strokeWidth={2} />)}
      <rect width={1920} height={160} fill="#151b2c" />
      {station(330, tx('stLine'), '', false)}
      {station(800, tx('stTable'), tx('peopleHour', {n: rates.table}), slowTable)}
      {station(1340, tx('stScanner'), tx('traysHour', {n: rates.trays, m: rates.scanner}), !slowTable)}
      {station(1700, tx('stPickup'), '', false)}
      {/* the line's tapes */}
      {[0, 1, 2, 3, 4, 5].map((r) => <line key={r} x1={110} x2={600} y1={902 - r * 84} y2={902 - r * 84} stroke="#495057" strokeWidth={4} strokeDasharray="2 10" />)}
      {/* the table */}
      <rect x={700} y={run.slots === 1 ? 420 : 220} width={200} height={run.slots === 1 ? 160 : 560} rx={10} fill="#9c7a54" stroke="#6b5136" strokeWidth={4} />
      {/* the belt and the scanner */}
      <rect x={900} y={470} width={960} height={70} fill="#343a40" />
      {Array.from({length: 24}, (_, i) => <line key={i} x1={900 + i * 40 + ((t * 8) % 40)} x2={900 + i * 40 + ((t * 8) % 40)} y1={472} y2={538} stroke="#495057" strokeWidth={3} />)}
      {before.slice(-9).map((x, i, all) => (
        <rect key={`b${run.trays.indexOf(x)}`} x={1230 - (all.length - 1 - i) * 36} y={480} width={32} height={50} rx={4} fill="#adb5bd" stroke="#212529" strokeWidth={2} />))}
      {inside && <rect x={1260 + ((t - inside.scanStart) / TRAY_SECONDS) * 150} y={480} width={32} height={50} rx={4} fill="#adb5bd" stroke="#212529" strokeWidth={2} />}
      {after.map((x, i) => (
        <rect key={`a${run.trays.indexOf(x)}`} x={1820 - i * 36} y={480} width={32} height={50} rx={4} fill={run.pax[x.owner].beep && t < run.pax[x.owner].archAt ? '#ff8787' : '#adb5bd'}
              stroke="#212529" strokeWidth={2} />))}
      <rect x={1260} y={430} width={180} height={150} rx={14} fill={inside ? '#2f9e44' : '#495057'} stroke="#212529" strokeWidth={5} />
      <text x={1350} y={515} textAnchor="middle" fill="#fff" fontFamily={FONT} fontSize={30} fontWeight={800}>RX</text>
      {!inside && <text x={1350} y={415} textAnchor="middle" fill={C.red} fontFamily={FONT} fontSize={30} fontWeight={800} style={{textTransform: 'uppercase'}}>{tx('idleNow')}</text>}
      {/* the arch */}
      <rect x={1300} y={700} width={22} height={120} fill="#868e96" /><rect x={1380} y={700} width={22} height={120} fill="#868e96" />
      <rect x={1300} y={692} width={102} height={18} fill="#868e96" />
      <text x={1350} y={860} textAnchor="middle" fill="#495057" fontFamily={FONT} fontSize={30} fontWeight={800} style={{textTransform: 'uppercase'}}>{tx('stArch')}</text>
      {run.pax.map((p) => {
        const at = placeOf(p, t, lineIdx.get(p.id) ?? 0, tableY, waitIdx.get(p.id) ?? 0);
        if (!at) return null;
        const [x, y, where] = at;
        const progress = where === 'table' ? (t - p.prepStart) / p.prep : 0;
        return (
          <g key={p.id} transform={`translate(${x} ${y}) scale(${where === 'walk' && t - p.prepEnd < 0.8 ? 1 + 0.35 * Math.sin(Math.PI * (t - p.prepEnd) / 0.8) : 1})`}>
            <ellipse cx={6} cy={9} rx={30} ry={20} fill="rgba(0,0,0,0.2)" />
            {where === 'walk' && t - p.prepEnd < 1.2 && <circle r={34 + (t - p.prepEnd) * 40} fill="none" stroke={C.green} strokeWidth={5} opacity={1 - (t - p.prepEnd) / 1.2} />}
            {where === 'table' && <circle r={44} fill="none" stroke="rgba(0,0,0,0.15)" strokeWidth={8} />}
            {where === 'table' && <circle r={44} fill="none" stroke={progress > 1 ? C.green : '#e8590c'} strokeWidth={8}
                                          strokeDasharray={`${Math.min(1, progress) * 276} 276`} transform="rotate(-90)" />}
            {where === 'back' && <circle r={46} fill="none" stroke={C.red} strokeWidth={6} />}
            <ellipse rx={30} ry={20} fill={KIND_COLOURS[p.kind]} stroke="rgba(0,0,0,0.45)" strokeWidth={3} />
            <circle r={13} fill="#3b2a1e" />
            {p.kind === 2 && <circle cx={30} cy={18} r={11} fill="#ffd8a8" stroke="rgba(0,0,0,0.4)" strokeWidth={2} />}
            {p.trouble >= 0 && (where === 'table' || where === 'line') && <text y={-36} textAnchor="middle" fontSize={40}>{TROUBLE[p.trouble]}</text>}
            {where === 'back' && <text y={-56} textAnchor="middle" fill={C.red} fontFamily={FONT} fontSize={34} fontWeight={800} style={{textTransform: 'uppercase'}}>{tx('beep')}</text>}
          </g>
        );
      })}
      {line.length > 36 && <text x={330} y={210} textAnchor="middle" fill="#212529" fontFamily={FONT} fontSize={36} fontWeight={800}>+{line.length - 36}</text>}
      <g transform="translate(40 960)">
        <rect width={420} height={100} rx={12} fill="#151b2c" />
        <text x={20} y={36} fill="#9aa3b5" fontFamily={FONT} fontSize={24} fontWeight={700} style={{textTransform: 'uppercase'}}>{tx('waitTable')}</text>
        <text x={20} y={84} fill={wait > 180 ? C.red : C.text} fontFamily={FONT} fontSize={46} fontWeight={800}>{fmt(wait)}</text>
      </g>
      <g transform="translate(1180 960)">
        <rect width={340} height={100} rx={12} fill="#151b2c" />
        <text x={20} y={36} fill="#9aa3b5" fontFamily={FONT} fontSize={24} fontWeight={700} style={{textTransform: 'uppercase'}}>{tx('scannerIdle')}</text>
        <text x={20} y={84} fill={idleSoFar > 0.15 ? C.red : C.green} fontFamily={FONT} fontSize={46} fontWeight={800}>{Math.round(idleSoFar * 100)} %</text>
      </g>
    </svg>
  );
};

const Chain: FC<WorldProps> = ({g, worldT}) => {
  const slots = Number(param(g, 'mesa', 1)) >= 4 ? 4 : 1;
  const run = runLane({slots, rate: RATE});
  return (
    <AbsoluteFill style={{background: C.night}}>
      <Lane run={run} t={START + worldT * LAPSE} />
      <div style={{position: 'absolute', left: 500, bottom: 40, fontFamily: FONT, fontSize: 22, color: '#495057'}}>{tx('laneNote', {n: 200, x: LAPSE})}</div>
    </AbsoluteFill>
  );
};

const Parallel: FC<WorldProps> = ({worldT}) => {
  const a = runLane({slots: 1, rate: RATE});
  const b = runLane({slots: 4, rate: RATE});
  const t = START + worldT * LAPSE;
  const fig = (r: LaneRun, colour: string) => (
    <Figure label={tx('waitTable')} value={fmt(r.meanWait(START, 3600))} colour={colour}
            sub={`${tx('throughput')}: ${num(Math.round(r.perHour))} · ${tx('scannerIdle')}: ${Math.round(r.scannerIdle[0] * 100)} %`} />
  );
  return <Split left={<Lane run={a} t={t} />} right={<Lane run={b} t={t} />} titles={[tx('oneSpot'), tx('fourSpots')]}
                figures={[fig(a, C.red), fig(b, C.green)]} />;
};

// --- lanes by kind of traveller --------------------------------------------------------------------------------------

const SIGNS = [
  (x: number, y: number) => <polygon key="d" points={`${x},${y - 26} ${x + 26},${y} ${x},${y + 26} ${x - 26},${y}`} fill="#111" stroke="#fff" strokeWidth={3} />,
  (x: number, y: number) => <rect key="s" x={x - 22} y={y - 22} width={44} height={44} fill="#1c7ed6" stroke="#fff" strokeWidth={3} />,
  (x: number, y: number) => <circle key="c" cx={x} cy={y} r={24} fill="#2f9e44" stroke="#fff" strokeWidth={3} />,
];
const LANE_KIND = [0, 1, 1, 2];

const Lanes: FC<{run: LaneRun; t: number; split: boolean}> = ({run, t, split}) => (
  <svg width={1920} height={1080} style={{position: 'absolute'}}>
    <rect width={1920} height={1080} fill="#d8d4cc" />
    {Array.from({length: run.lanes}, (_, l) => {
      const y = 170 + l * 230;
      const line = run.pax.filter((p) => p.lane === l && p.arrive <= t && t < p.prepStart).sort((a, b) => a.arrive - b.arrive);
      const at = run.pax.find((p) => p.lane === l && p.prepStart <= t && t < p.prepEnd);
      return (
        <g key={l}>
          <rect x={60} y={y - 70} width={1800} height={140} rx={12} fill="rgba(0,0,0,0.05)" />
          {split && SIGNS[LANE_KIND[l]](120, y)}
          {line.slice(0, 14).map((p, i) => (
            <g key={p.id} transform={`translate(${1100 - i * 70} ${y})`}>
              <ellipse rx={26} ry={18} fill={KIND_COLOURS[p.kind]} stroke="rgba(0,0,0,0.45)" strokeWidth={3} />
              <circle r={11} fill="#3b2a1e" />
            </g>))}
          {line.length > 14 && <text x={160} y={y + 12} fill="#212529" fontFamily={FONT} fontSize={36} fontWeight={800}>+{line.length - 14}</text>}
          <rect x={1160} y={y - 50} width={170} height={100} rx={8} fill="#9c7a54" />
          {at && <g transform={`translate(1245 ${y})`}><circle r={36} fill="none" stroke="#e8590c" strokeWidth={7}
                                                                strokeDasharray={`${Math.min(1, (t - at.prepStart) / at.prep) * 226} 226`} transform="rotate(-90)" />
            <ellipse rx={26} ry={18} fill={KIND_COLOURS[at.kind]} stroke="rgba(0,0,0,0.45)" strokeWidth={3} /><circle r={11} fill="#3b2a1e" /></g>}
          <rect x={1330} y={y - 24} width={480} height={48} fill="#343a40" />
          <rect x={1500} y={y - 45} width={130} height={90} rx={10} fill="#495057" />
        </g>
      );
    })}
    <g transform="translate(1200 1040)">
      {[0, 1, 2].map((k) => (
        <g key={k} transform={`translate(${k * 230} 0)`}>
          <circle r={14} fill={KIND_COLOURS[k]} />
          <text x={24} y={10} fill="#212529" fontFamily={FONT} fontSize={28} fontWeight={800}>{tx(['kExpert', 'kCasual', 'kFamily'][k])}</text>
        </g>))}
    </g>
  </svg>
);

const Slopes: FC<WorldProps> = ({worldT}) => {
  const setup = {slots: 1, lanes: 4, rate: 220 / 3600, span: 7200, seed: 5};
  const a = runLane({...setup, split: false});
  const b = runLane({...setup, split: true});
  const t = 2400 + worldT * LAPSE;
  const fig = (r: LaneRun, colour: string) => (
    <Figure label={tx('expertsWait')} value={fmt(r.meanWait(1200, 7200, 0))} colour={colour}
            sub={`${tx('everyoneWait')}: ${fmt(r.meanWait(1200, 7200))}`} />
  );
  return <Split left={<Lanes run={a} t={t} split={false} />} right={<Lanes run={b} t={t} split />} titles={[tx('mixed'), tx('byKind')]}
                figures={[fig(a, C.text), fig(b, C.green)]} />;
};

// --- 2001 and 2006 ---------------------------------------------------------------------------------------------------

const Rules: FC<WorldProps> = ({worldT}) => {
  const cards: [string, string, string][] = [['2001', 'rules2001', '🛂'], ['2006 · ago.', 'rules2006a', '🧴'], ['2006 · nov.', 'rules2006b', '💧']];
  const items = ['🧥', '⌚', '👞', '💻', '🧴', '📱'];
  return (
    <AbsoluteFill style={{background: 'radial-gradient(ellipse at 50% 40%, #16213a 0%, #0a0f1c 75%)'}}>
      <div style={{position: 'absolute', left: 120, top: 70, fontFamily: FONT, fontSize: 56, fontWeight: 800, color: C.text, textTransform: 'uppercase'}}>{tx('secRulesTitle')}</div>
      <svg width={1920} height={1080} style={{position: 'absolute'}}>
        <line x1={160} x2={1760} y1={330} y2={330} stroke="#495057" strokeWidth={6} />
      </svg>
      {cards.map(([year, key, icon], i) => {
        const o = interpolate(worldT, [0.5 + i * 2.2, 1.1 + i * 2.2], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
        return (
          <div key={key} style={{position: 'absolute', left: 160 + i * 560, top: 260, width: 480, opacity: o, transform: `translateY(${(1 - o) * 30}px)`}}>
            <div style={{width: 140, height: 140, borderRadius: 70, background: '#1f2a44', border: `6px solid ${C.you}`, display: 'flex', alignItems: 'center',
                         justifyContent: 'center', fontSize: 70}}>{icon}</div>
            <div style={{fontFamily: FONT, fontSize: 60, fontWeight: 800, color: C.you, marginTop: 18}}>{year}</div>
            <div style={{fontFamily: FONT, fontSize: 34, fontWeight: 700, color: C.text, lineHeight: 1.2, marginTop: 8}}>{tx(key)}</div>
          </div>
        );
      })}
      {/* the tray filling up: one more thing to take out, rule after rule */}
      <div style={{position: 'absolute', left: 160, top: 860, width: 1600, height: 140, borderRadius: 18, background: '#adb5bd', display: 'flex',
                   alignItems: 'center', gap: 40, padding: '0 40px', boxSizing: 'border-box'}}>
        {items.map((it, i) => (
          <span key={i} style={{fontSize: 80, opacity: interpolate(worldT, [1 + i * 1.1, 1.4 + i * 1.1], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'})}}>{it}</span>))}
      </div>
    </AbsoluteFill>
  );
};

// --- the morning ------------------------------------------------------------------------------------------------------

const WAVES = [[6.0, 0.55], [7.5, 0.5], [9.25, 0.45]];        // hour, width: banks of departures
const wave = (t: number) => {
  const h = 5 + t / 3600;
  return 0.55 + WAVES.reduce((a, [c, w]) => a + 0.75 * Math.exp(-((h - c) ** 2) / (2 * w * w)), 0);
};

const Morning: FC<WorldProps> = ({worldT}) => {
  const run = runLane({slots: 1, lanes: 4, rate: 260 / 3600, span: 6 * 3600, seed: 9, wave});
  const pts: [number, number][] = [];
  for (let q = 0; q < 24; q++) {
    const from = q * 900;
    const w = run.meanWait(from, from + 900);
    pts.push([5 + (q + 0.5) / 4, w / 60]);
  }
  const peak = Math.max(...pts.map(([, v]) => v));
  return <LineChart t={worldT} draw={3.5} x={[5, 11]} y={[0, Math.max(10, Math.ceil(peak / 10) * 10)]} title={tx('morningTitle')} xLabel={tx('arrivalTime')}
                    yLabel="min" xFmt={(v) => `${Math.floor(v)}:${String(Math.round((v % 1) * 60)).padStart(2, '0')}`} xTicks={[5, 6, 7, 8, 9, 10, 11]}
                    band={{from: 5.6, to: 6.4, label: tx('flightWave')}} series={[{name: tx('waitTable'), colour: C.red, pts}]} />;
};

export const CHECKPOINT_SCENES: Record<string, FC<WorldProps>> = {cadena: Chain, paralelo: Parallel, pistas: Slopes, normas: Rules, manana: Morning};
