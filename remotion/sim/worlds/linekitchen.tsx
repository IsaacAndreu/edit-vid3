// The restaurant on a Saturday night, line by line (remotion/sim/linekitchen.ts): the kitchen's four stations in a
// row (the grill, the fryer, the cold side, plating) with the dishes queuing in front of each, the pass where finished
// plates wait for the rest of their table, and the dining room — sixteen tables, each with its diners, its timer and,
// when the food comes, its plates. Also the scenes that compare (tapas al centro, a second grill, one more cook on
// the cold side, a short menu, seating a full house two at a time), the charts (the wait by table size, the evening
// hour by hour) and Goldratt's hike with Herbie.
import type {FC, ReactElement} from 'react';
import {AbsoluteFill} from 'remotion';
import {C, FONT, Label, Panel} from '../hud';
import {addWords, num, tx} from '../i18n';
import {DISHES, evening, runLine, STATIONS, TABLES, waits, type Fix, type KitchenLine, type KitchenSetup} from '../linekitchen';
import {Pointers, type Anchor} from '../look';
import {Note, param, type WorldProps} from '../world';
import {Figure, LineChart, Split} from '../scenes';

addWords({
  grill: {es: 'Plancha', pt: 'Chapa', fr: 'Plancha', de: 'Grill', en: 'Grill'},
  fryer: {es: 'Freidora', pt: 'Fritadeira', fr: 'Friteuse', de: 'Fritteuse', en: 'Fryer'},
  cold: {es: 'Parte fría', pt: 'Parte fria', fr: 'Garde-manger', de: 'Kalte Küche', en: 'Cold side'},
  plate: {es: 'Emplatado', pt: 'Empratamento', fr: 'Dressage', de: 'Anrichten', en: 'Plating'},
  passLine: {es: 'Pase: platos esperando a los de su mesa', pt: 'Passe: pratos à espera dos da mesa', fr: 'Passe : assiettes qui attendent leur table', de: 'Pass: Teller warten auf ihren Tisch', en: 'Pass: plates waiting for the rest of their table'},
  perHour: {es: '{n} platos/h', pt: '{n} pratos/h', fr: '{n} assiettes/h', de: '{n} Teller/h', en: '{n} dishes/h'},
  bottleneck: {es: 'El más lento', pt: 'O mais lento', fr: 'Le plus lent', de: 'Der Engpass', en: 'The slowest'},
  tableOf: {es: 'Mesa de {n}', pt: 'Mesa de {n}', fr: 'Table de {n}', de: 'Tisch für {n}', en: 'Table of {n}'},
  untilFood: {es: 'Hasta tener la comida', pt: 'Até ter a comida', fr: 'Jusqu’à être servi', de: 'Bis das Essen kommt', en: 'Until the food comes'},
  firstBite: {es: 'Hasta el primer bocado', pt: 'Até a primeira garfada', fr: 'Jusqu’à la première bouchée', de: 'Bis zum ersten Bissen', en: 'Until the first bite'},
  grillBusy: {es: 'Plancha ocupada el {p} %', pt: 'Chapa ocupada {p} %', fr: 'Plancha occupée {p} %', de: 'Grill zu {p} % belegt', en: 'Grill busy {p} %'},
  allTogether: {es: 'Todo a la vez', pt: 'Tudo junto', fr: 'Tout en même temps', de: 'Alles zusammen', en: 'All together'},
  toShare: {es: 'Al centro, según sale', pt: 'Ao centro, conforme sai', fr: 'Au centre, dès que c’est prêt', de: 'In die Mitte, sobald fertig', en: 'To share, as it comes'},
  secondGrill: {es: 'Una segunda plancha', pt: 'Uma segunda chapa', fr: 'Une deuxième plancha', de: 'Ein zweiter Grill', en: 'A second grill'},
  coldCook: {es: 'Un cocinero más en la parte fría', pt: 'Um cozinheiro a mais na parte fria', fr: 'Un cuisinier de plus au froid', de: 'Ein Koch mehr in der kalten Küche', en: 'One more cook on the cold side'},
  shortMenu: {es: 'Carta corta', pt: 'Cardápio curto', fr: 'Carte courte', de: 'Kurze Karte', en: 'A short menu'},
  asItIs: {es: 'Como está', pt: 'Como está', fr: 'Tel quel', de: 'Wie es ist', en: 'As it is'},
  seatAll: {es: 'Sientan a todos a la vez', pt: 'Sentam todos de uma vez', fr: 'Tout le monde assis d’un coup', de: 'Alle auf einmal gesetzt', en: 'Everyone seated at once'},
  seatTwo: {es: 'De dos en dos', pt: 'De dois em dois', fr: 'Deux par deux', de: 'Je zwei Tische', en: 'Two tables at a time'},
  peakQueue: {es: 'Platos en cola en la plancha (máx.)', pt: 'Pratos na fila da chapa (máx.)', fr: 'Assiettes en attente à la plancha (max.)', de: 'Teller in der Grill-Schlange (max.)', en: 'Dishes queuing at the grill (max.)'},
  meanWait: {es: 'Espera media', pt: 'Espera média', fr: 'Attente moyenne', de: 'Mittlere Wartezeit', en: 'Mean wait'},
  atBar: {es: 'En la barra', pt: 'No balcão', fr: 'Au bar', de: 'An der Bar', en: 'At the bar'},
  bySizeTitle: {es: 'Lo que espera cada mesa según cuántos sois', pt: 'Quanto espera cada mesa segundo quantos são', fr: 'L’attente de chaque table selon le nombre', de: 'Wartezeit je nach Tischgröße', en: 'How long a table waits, by its size'},
  diners: {es: 'comensales', pt: 'pessoas', fr: 'convives', de: 'Gäste', en: 'diners'},
  eveningTitle: {es: 'Lo que tarda la comida según la hora a la que pides', pt: 'Quanto demora a comida segundo a hora do pedido', fr: 'L’attente selon l’heure de la commande', de: 'Wartezeit je nach Bestellzeit', en: 'How long the food takes by when you order'},
  fullRoom: {es: 'Comedor lleno', pt: 'Salão cheio', fr: 'Salle pleine', de: 'Voller Saal', en: 'Full house'},
  hour: {es: 'hora del pedido', pt: 'hora do pedido', fr: 'heure de la commande', de: 'Bestellzeit', en: 'time you order'},
  lineNote: {es: 'Simulación · plancha {g} platos/h · {n} mesas · 1 s = {x} s', pt: 'Simulação · chapa {g} pratos/h · {n} mesas · 1 s = {x} s', fr: 'Simulation · plancha {g} assiettes/h · {n} tables · 1 s = {x} s', de: 'Simulation · Grill {g} Teller/h · {n} Tische · 1 s = {x} s', en: 'Simulation · grill {g} dishes/h · {n} tables · 1 s = {x} s'},
  hike: {es: 'El grupo avanza al ritmo de Herbie', pt: 'O grupo avança ao ritmo do Herbie', fr: 'Le groupe avance au rythme de Herbie', de: 'Die Gruppe geht in Herbies Tempo', en: 'The group moves at Herbie’s pace'},
  herbieFront: {es: 'Herbie delante y su mochila repartida', pt: 'Herbie à frente e a mochila repartida', fr: 'Herbie devant, son sac partagé', de: 'Herbie vorn, sein Rucksack verteilt', en: 'Herbie in front, his load shared'},
  walked: {es: 'Recorrido del grupo', pt: 'Percurso do grupo', fr: 'Distance du groupe', de: 'Strecke der Gruppe', en: 'The group has walked'},
});

const LAPSE = 40;                                       // 1 s of video = 40 s in the kitchen
const STEADY = 5400;                                    // an hour and a half into the evening: the queues have formed
const SX = [360, 800, 1240, 1640];
const TABLE_COLOURS = ['#ff6b6b', '#4dabf7', '#ffd43b', '#69db7c', '#da77f2', '#ff922b', '#3bc9db', '#f783ac'];
const mins = (s: number) => `${Math.max(0, Math.round(s / 60))} min`;

export const setupOf = (g: WorldProps['g']): KitchenSetup => ({
  load: param(g, 'ocupacion', 0.9), share: param<string>(g, 'regla', 'juntos') === 'centro',
  fix: ({plancha2: 'grill2', frio: 'cold', carta: 'menu'} as Record<string, Fix>)[param<string>(g, 'arreglo', 'ninguno')] ?? 'none',
});

/** Dishes an hour each station can get through, for the whole menu (a dish that skips a station costs it nothing). */
const stationRates = (run: KitchenLine) => STATIONS.map((_, s) => {
  const minutes = DISHES.reduce((a, d, k) => a + [0.25, 0.12, 0.08, 0.2, 0.2, 0.15][k] * (d.route.find(([st]) => st === s)?.[1] ?? 0), 0);
  return minutes > 0 ? Math.round((run.capacity[s] * 60) / minutes) : 999;
});

export const Line: FC<{run: KitchenLine; t: number; share: boolean; highlight?: boolean}> = ({run, t, share, highlight}) => {
  const f = run.at(t);
  const rates = stationRates(run);
  const slow = rates.indexOf(Math.min(...rates));
  const passTables = new Map<number, number[]>();
  for (const id of f.pass) {
    const d = run.dishes[id];
    passTables.set(d.table, [...(passTables.get(d.table) ?? []), id]);
  }
  return (
    <svg width={1920} height={1080} style={{position: 'absolute'}}>
      {/* the kitchen: tiles, then the line */}
      <rect width={1920} height={630} fill="#c9c6bf" />
      {Array.from({length: 33}, (_, i) => <line key={i} x1={i * 60} x2={i * 60} y1={0} y2={630} stroke="rgba(0,0,0,0.06)" strokeWidth={2} />)}
      {Array.from({length: 11}, (_, i) => <line key={`h${i}`} x1={0} x2={1920} y1={i * 60} y2={i * 60} stroke="rgba(0,0,0,0.06)" strokeWidth={2} />)}
      {STATIONS.map((name, s) => {
        const x = SX[s];
        const q = f.queue[s];
        const cap = run.capacity[s];
        const hot = q.length > 8;
        return (
          <g key={name}>
            {s < 3 && <path d={`M ${x + 175} 290 l 40 0 l -10 -10 m 10 10 l -10 10`} stroke="rgba(0,0,0,0.35)" strokeWidth={4} fill="none" />}
            <text x={x} y={70} textAnchor="middle" fill={s === slow && highlight ? C.red : '#2b2f36'} fontFamily={FONT} fontSize={40} fontWeight={800}
                  style={{textTransform: 'uppercase'}}>{tx(name)}</text>
            {highlight && <text x={x} y={104} textAnchor="middle" fill={s === slow ? C.red : '#4b5059'} fontFamily={FONT} fontSize={28} fontWeight={700}>{tx('perHour', {n: rates[s]})}</text>}
            {/* the cooks behind the counter */}
            {Array.from({length: Math.min(cap, 3)}, (_, k) => (
              <g key={k} transform={`translate(${x + (k - (Math.min(cap, 3) - 1) / 2) * 70} 150)`}>
                <ellipse rx={26} ry={17} fill="#f6f6f4" stroke="rgba(0,0,0,0.35)" strokeWidth={2} />
                <circle r={12} fill="#ffffff" stroke="rgba(0,0,0,0.25)" />
                <circle cy={4} r={7} fill="#e2b48c" />
              </g>
            ))}
            <rect x={x - 160} y={190} width={320} height={190} rx={10} fill={s === 0 ? '#3a3f46' : s === 2 ? '#b8c3cc' : '#5a6068'}
                  stroke={s === slow && highlight ? C.red : '#22262c'} strokeWidth={s === slow && highlight ? 8 : 4} />
            {/* what is on it now: a ring per dish, how much is left */}
            {Array.from({length: cap}, (_, k) => {
              const job = f.busy[s][k];
              const cx = x - 160 + (320 / (cap + 1)) * (k + 1);
              const cy = 285;
              const z = cap >= 4 ? 0.72 : 1;                       // five on the grill: smaller rings
              const done = job ? 1 - job.left / job.total : 0;
              return (
                <g key={k}>
                  <circle cx={cx} cy={cy} r={30 * z} fill="none" stroke={job && s !== 2 ? '#ff7a2f' : 'rgba(255,255,255,0.25)'} strokeWidth={5}
                          opacity={job && s !== 2 ? 0.55 + 0.45 * Math.sin(t / 2 + k) : 1} />
                  {job && <circle cx={cx} cy={cy} r={20 * z} fill={DISHES[run.dishes[job.id].type].colour} />}
                  {job && <circle cx={cx} cy={cy} r={34 * z} fill="none" stroke={C.green} strokeWidth={5} strokeDasharray={`${2 * Math.PI * 34 * z}`}
                                  strokeDashoffset={`${2 * Math.PI * 34 * z * (1 - done)}`} transform={`rotate(-90 ${cx} ${cy})`} />}
                </g>
              );
            })}
            {/* the dishes waiting for this station */}
            {q.slice(0, 24).map((id, i) => {
              const tx_ = x - 150 + (i % 8) * 38;
              const ty = 410 + Math.floor(i / 8) * 46;
              const d = run.dishes[id];
              return (
                <g key={id}>
                  <rect x={tx_} y={ty} width={30} height={40} rx={3} fill="#fbf8f1" stroke={TABLE_COLOURS[run.tables[d.table].colour]} strokeWidth={3} />
                  <rect x={tx_ + 5} y={ty + 7} width={20} height={7} fill={DISHES[d.type].colour} />
                </g>
              );
            })}
            {q.length > 24 && <text x={x + 150} y={560} textAnchor="end" fill={C.red} fontFamily={FONT} fontSize={34} fontWeight={800}>+{q.length - 24}</text>}
            {hot && <rect x={x - 165} y={400} width={330} height={150} rx={8} fill="none" stroke={C.red} strokeWidth={4} strokeDasharray="12 8" opacity={0.8} />}
          </g>
        );
      })}
      {/* the pass */}
      <rect x={40} y={590} width={1840} height={80} rx={8} fill="#b9bec6" stroke="#8a919b" strokeWidth={3} />
      {!share && <text x={60} y={582} fill="#2b2f36" fontFamily={FONT} fontSize={26} fontWeight={800} style={{textTransform: 'uppercase'}}>{tx('passLine')}</text>}
      {(() => {
        let x = 80;
        const out: ReactElement[] = [];
        for (const [table, ids] of passTables) {
          if (x > 1840) break;
          const colour = TABLE_COLOURS[run.tables[table].colour];
          ids.slice(0, 10).forEach((id, j) => {
            out.push(<g key={id}><circle cx={x + j * 30} cy={630} r={22} fill="#fff" stroke={colour} strokeWidth={4} />
              <circle cx={x + j * 30} cy={630} r={10} fill={DISHES[run.dishes[id].type].colour} /></g>);
          });
          x += Math.min(ids.length, 10) * 30 + 40;
        }
        return out;
      })()}
      {/* the dining room */}
      <rect y={690} width={1920} height={390} fill="#5b4636" />
      {Array.from({length: 40}, (_, i) => <line key={i} x1={i * 52} x2={i * 52 - 40} y1={690} y2={1080} stroke="rgba(0,0,0,0.12)" strokeWidth={3} />)}
      {Array.from({length: TABLES}, (_, k) => {
        const id = f.seated[k];
        if (k >= 14) return null;                              // 7 a row: the right end is the panel's
        const cx = 130 + (k % 7) * 220;
        const cy = k < 7 ? 790 : 960;
        if (id < 0) return <circle key={k} cx={cx} cy={cy} r={40} fill="#7a6250" opacity={0.6} />;
        const tb = run.tables[id];
        const r = {2: 34, 4: 44, 6: 54, 10: 66}[tb.size] ?? 44;
        const colour = TABLE_COLOURS[tb.colour];
        const servedDishes = tb.dishes.filter((d) => run.dishes[d].ready <= f.t && (share || tb.all <= f.t));
        const waiting = !f.served.has(id);
        const wait = f.t - tb.arrive;
        return (
          <g key={k}>
            {Array.from({length: tb.size}, (_, c) => {
              const a = (c / tb.size) * Math.PI * 2;
              return <circle key={c} cx={cx + Math.cos(a) * (r + 18)} cy={cy + Math.sin(a) * (r + 18)} r={11} fill="#efe6d8" stroke="rgba(0,0,0,0.4)" strokeWidth={2} />;
            })}
            <circle cx={cx} cy={cy} r={r} fill="#d8c3a5" stroke={colour} strokeWidth={6} />
            {servedDishes.map((d, j) => {
              const a = (j / tb.size) * Math.PI * 2;
              return <circle key={d} cx={cx + Math.cos(a) * r * 0.62} cy={cy + Math.sin(a) * r * 0.62} r={9} fill={DISHES[run.dishes[d].type].colour} stroke="#fff" strokeWidth={2} />;
            })}
            {waiting && f.t >= tb.seat && (
              <text x={cx} y={cy + 9} textAnchor="middle" fill={wait > 1800 ? C.red : '#2b2f36'} fontFamily={FONT} fontSize={28} fontWeight={800}>{mins(wait)}</text>
            )}
          </g>
        );
      })}
    </svg>
  );
};

export const kitchenMarks: Record<string, Anchor> = {plancha: {x: SX[0], y: 300}, pase: {x: 960, y: 630}, mesas: {x: 960, y: 860}};

const LineScene: FC<WorldProps> = ({g, worldT, local, real = local, o, on}) => {
  const setup = setupOf(g);
  const run = runLine(setup);
  const t = STEADY + worldT * LAPSE;
  const w = waits(setup);
  const panel = Math.max(o('panel'), on * 0.9);
  const f = run.at(t);
  return (
    <AbsoluteFill style={{background: C.night}}>
      <Line run={run} t={t} share={setup.share} highlight={g.overlay === 'cuello' || param<string>(g, 'cuello', 'no') === 'si'} />
      <Panel o={panel} style={{right: 36, bottom: 60, width: 330}}>
        <Label>{tx(setup.share ? 'firstBite' : 'untilFood')}</Label>
        {[2, 10].map((n) => (
          <div key={n} style={{display: 'flex', justifyContent: 'space-between', fontSize: 34, fontWeight: 800, marginTop: 4}}>
            <span style={{textTransform: 'uppercase'}}>{tx('tableOf', {n})}</span>
            <span style={{color: (w.bySize[n] ?? 0) > 40 ? C.red : C.text}}>{Math.round(w.bySize[n] ?? 0)} min</span>
          </div>
        ))}
        <Label>{tx('grillBusy', {p: Math.round(setup.load * 100)})}</Label>
        {f.bar.length > 0 && <Label>{tx('atBar')}: {num(f.bar.length)}</Label>}
      </Panel>
      <Pointers marks={g.marks} local={real} at={kitchenMarks} />
      <Note>{tx('lineNote', {g: Math.round(run.grillPerHour), n: TABLES, x: LAPSE})}</Note>
    </AbsoluteFill>
  );
};

// --- comparisons ------------------------------------------------------------------------------------------------

const VARIANT: Record<string, {setup: Partial<KitchenSetup>; name: string}> = {
  centro: {setup: {share: true}, name: 'toShare'},
  plancha2: {setup: {fix: 'grill2'}, name: 'secondGrill'},
  frio: {setup: {fix: 'cold'}, name: 'coldCook'},
  carta: {setup: {fix: 'menu'}, name: 'shortMenu'},
};

const Compare: FC<WorldProps> = (props) => {
  const {g, worldT} = props;
  const que = param<string>(g, 'que', 'centro');
  const v = VARIANT[que] ?? VARIANT.centro;
  const load = param(g, 'ocupacion', 0.9);
  const a: KitchenSetup = {load, share: false, fix: 'none'};
  const b: KitchenSetup = {...a, ...v.setup};
  const t = STEADY + worldT * LAPSE;
  const wa = waits(a);
  const wb = waits(b);
  const big = que === 'centro' ? 10 : 4;
  const side = (s: KitchenSetup) => (
    <AbsoluteFill style={{background: C.night}}><Line run={runLine(s)} t={t} share={s.share} highlight={que !== 'centro'} /></AbsoluteFill>
  );
  return (
    <Split left={side(a)} right={side(b)} titles={[tx(que === 'centro' ? 'allTogether' : 'asItIs'), tx(v.name)]}
           figures={[<Figure key="a" label={`${tx('tableOf', {n: big})} · ${tx('untilFood')}`} value={`${Math.round(wa.bySize[big])} min`} colour={C.red} />,
                     <Figure key="b" label={`${tx('tableOf', {n: big})} · ${tx(que === 'centro' ? 'firstBite' : 'untilFood')}`}
                             value={`${Math.round(wb.bySize[big])} min`} colour={wb.bySize[big] < wa.bySize[big] - 3 ? C.green : C.text} />]} />
  );
};

const Seat: FC<WorldProps> = ({worldT}) => {
  const a = runLine({load: 0.9, share: false, fix: 'none', burst: 10});
  const b = runLine({load: 0.9, share: false, fix: 'stagger', burst: 10});
  const t = worldT * LAPSE * 1.5;
  const peak = (r: KitchenLine) => Math.max(...r.frames.map((x) => x.queue[0].length));
  const mean = (r: KitchenLine) => r.tables.reduce((s, tb) => s + (tb.all - tb.arrive), 0) / r.tables.length;
  return (
    <Split left={<AbsoluteFill style={{background: C.night}}><Line run={a} t={t} share={false} /></AbsoluteFill>}
           right={<AbsoluteFill style={{background: C.night}}><Line run={b} t={t} share={false} /></AbsoluteFill>}
           titles={[tx('seatAll'), tx('seatTwo')]}
           figures={[<Figure key="a" label={tx('peakQueue')} value={num(peak(a))} colour={C.red} sub={`${tx('meanWait')}: ${mins(mean(a))}`} />,
                     <Figure key="b" label={tx('peakQueue')} value={num(peak(b))} colour={C.green} sub={`${tx('meanWait')}: ${mins(mean(b))}`} />]} />
  );
};

const BySize: FC<WorldProps> = ({worldT, g}) => {
  const load = param(g, 'ocupacion', 0.9);
  const together = waits({load, share: false, fix: 'none'}).bySize;
  const shared = waits({load, share: true, fix: 'none'}).bySize;
  const pts = (by: Record<number, number>) => [2, 4, 6, 10].map((n) => [n, by[n] ?? 0] as [number, number]);
  return <LineChart t={worldT} draw={3} x={[2, 10]} y={[0, 70]} title={tx('bySizeTitle')} xLabel={tx('diners')} yLabel="min"
                    xTicks={[2, 4, 6, 8, 10]} yTicks={[15, 30, 45, 60]}
                    series={[{name: tx('allTogether'), colour: C.red, pts: pts(together)}, {name: tx('toShare'), colour: C.green, pts: pts(shared)}]} />;
};

const Evening: FC<WorldProps> = ({worldT}) => {
  const pts = evening();
  return <LineChart t={worldT} draw={3.5} x={[20.5, 24]} y={[0, 80]} title={tx('eveningTitle')} xLabel={tx('hour')} yLabel="min"
                    xFmt={(v) => `${Math.floor(v)}:${String(Math.round((v % 1) * 60)).padStart(2, '0')}`} xTicks={[21, 22, 23, 24]} yTicks={[20, 40, 60, 80]}
                    band={{from: 21.5, to: 22.25, label: tx('fullRoom')}} series={[{name: tx('untilFood'), colour: C.red, pts}]} />;
};

// --- Goldratt's hike: the group walks at Herbie's pace ------------------------------------------------------------

const KIDS = 8;
const hikers = (front: boolean, t: number) => {
  const base = 1.0;
  const speed = Array.from({length: KIDS}, (_, k) => base * (1.25 - (k % 3) * 0.06));
  const herbie = front ? 0 : 4;
  speed[herbie] = front ? base * 0.8 : base * 0.55;          // in front, his pack shared out: a bit quicker
  const order = Array.from({length: KIDS}, (_, k) => k);
  if (front) order.unshift(...order.splice(herbie, 1));
  const pos = order.map((_, i) => -i * 2.2);
  for (let s = 0; s < t; s += 0.1) {
    for (let i = 0; i < KIDS; i++) {
      const k = order[i];
      let v = speed[k];
      if (i > 0) v = Math.min(v, Math.max(0, (pos[i - 1] - 2.2 - pos[i]) / 0.1));         // never through the one ahead
      // the ones ahead of Herbie stop and wait when they are too far ahead
      const hi = order.indexOf(herbie);
      if (!front && i < hi && pos[i] - pos[hi] > 9 + (hi - i) * 2.2) v = 0;
      pos[i] += v * 0.1;
    }
  }
  return {order, pos, herbie};
};

const Hike: FC<WorldProps> = ({g, worldT}) => {
  const front = param<string>(g, 'herbie', 'detras') === 'delante';
  const {order, pos, herbie} = hikers(front, worldT * 3);
  const last = Math.min(...pos);
  const cam = last + 14;
  const X = (p: number) => 760 + (p - cam) * 52;
  const Y = (p: number) => 640 - Math.sin(p / 9) * 60 - p * 1.2 + cam * 1.2;
  return (
    <AbsoluteFill style={{background: 'linear-gradient(#9ed0f0, #e6f2f8 55%, #c9dcb0 56%, #9fbf7f)'}}>
      <svg width={1920} height={1080} style={{position: 'absolute'}}>
        {[0, 1, 2].map((k) => <path key={k} d={`M 0 ${520 + k * 30} Q 480 ${380 + k * 40} 960 ${500 + k * 25} T 1920 ${470 + k * 35} L 1920 1080 L 0 1080 Z`}
                                      fill={['#b9d39a', '#a7c788', '#93b874'][k]} />)}
        {Array.from({length: 60}, (_, i) => {
          const p = cam - 22 + i * 0.8;
          return <circle key={i} cx={X(p)} cy={Y(p) + 30} r={10} fill="#d9c49a" />;
        })}
        {order.map((k, i) => {
          const x = X(pos[i]);
          const y = Y(pos[i]);
          const isH = k === herbie;
          const step = Math.sin(worldT * 9 + i) * 8;
          return (
            <g key={k} transform={`translate(${x} ${y}) scale(1.7)`}>
              {isH && <rect x={-36} y={-112} width={34} height={56} rx={8} fill="#c0392b" stroke="#000" strokeWidth={3} />}
              <line x1={0} y1={-40} x2={-10 + step} y2={0} stroke="#1b1b1b" strokeWidth={7} strokeLinecap="round" />
              <line x1={0} y1={-40} x2={10 - step} y2={0} stroke="#1b1b1b" strokeWidth={7} strokeLinecap="round" />
              <line x1={0} y1={-40} x2={0} y2={-90} stroke="#1b1b1b" strokeWidth={7} strokeLinecap="round" />
              <circle cy={-108} r={18} fill="#f4e3c8" stroke="#1b1b1b" strokeWidth={4} />
              {isH && <text y={-140} textAnchor="middle" fill="#c0392b" fontFamily={FONT} fontSize={34} fontWeight={800}>HERBIE</text>}
            </g>
          );
        })}
      </svg>
      <Panel o={1} style={{left: 48, top: 48}}>
        <div style={{fontSize: 36, fontWeight: 800, textTransform: 'uppercase'}}>{tx(front ? 'herbieFront' : 'hike')}</div>
        <Label>{tx('walked')}: {(Math.max(0, last + (KIDS - 1) * 2.2) / 10).toFixed(1)} km</Label>
      </Panel>
    </AbsoluteFill>
  );
};

export const LINE_SCENES: Record<string, FC<WorldProps>> = {cocina: LineScene, comparar: Compare, sentar: Seat, mesas: BySize, noche: Evening, herbie: Hike};
