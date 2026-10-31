// A supermarket's tills seen from above (remotion/sim/shop.ts). Scenes (param scene):
//  comparar  left one line per till (each picks the shortest), right one line feeding every till; the same customers
//  eleccion  three (or five) lines and YOU in one: over hundreds of tries, how often is yours the fastest? 1 in 3
//  cabezas   two people with full carts against five with baskets: each person ≈ 40 s, each item ≈ 3 s (Dan Meyer)
//  limite    one till getting fuller (80, 90, 95 % busy) and Kingman's curve: the wait explodes near 100 %
//  iguales   the same shop with every customer different (left) and every customer taking the same time (right)
//  cambiar   YOU switch to the line that moved... and the one you left starts moving (and YOU, had you stayed)
//  contar    Little's law: count who leaves in a minute and the heads ahead of you: that is your wait
//  rapida    an express till (≤ 10 items): those with little wait less (the average of all does not improve)
// The figures in the panels come from the same shop run for 16 hours (shop.longRun), not from the minutes on screen.
import type {FC, ReactElement} from 'react';
import {AbsoluteFill, interpolate} from 'remotion';
import {C, FONT, Label, Panel} from '../hud';
import {addWords, tx, num} from '../i18n';
import {Pointers, type Anchor} from '../look';
import {SHOP, customers, kingman, longRun, lottery, runShop, waits, type Person, type ShopFrame, type ShopRun} from '../shop';
import {Big, Note, param, SideTitle, splitAt, type World, type WorldProps} from '../world';

addWords({
  manyLines: {es: 'Una cola por caja', pt: 'Uma fila por caixa', fr: 'Une file par caisse', de: 'Eine Schlange pro Kasse', en: 'A line per till'},
  oneLine: {es: 'Una sola cola', pt: 'Uma só fila', fr: 'Une seule file', de: 'Eine einzige Schlange', en: 'One single line'},
  averageWaitShort: {es: 'Espera media', pt: 'Espera média', fr: 'Attente moyenne', de: 'Mittlere Wartezeit', en: 'Average wait'},
  longestWait: {es: 'La espera más larga', pt: 'A espera mais longa', fr: 'L’attente la plus longue', de: 'Längste Wartezeit', en: 'Longest wait'},
  slowLine: {es: 'Eligió la cola lenta', pt: 'Escolheu a fila lenta', fr: 'A choisi la file lente', de: 'Hat die langsame Schlange erwischt', en: 'Picked the slow line'},
  queueNote: {es: 'Simulación · {n} cajas · cada persona ≈ 40 s y cada artículo ≈ 3 s · tiempo ×{x}', pt: 'Simulação · {n} caixas · cada pessoa ≈ 40 s e cada artigo ≈ 3 s · tempo ×{x}', fr: 'Simulation · {n} caisses · chaque personne ≈ 40 s, chaque article ≈ 3 s · temps ×{x}', de: 'Simulation · {n} Kassen · pro Person ≈ 40 s, pro Artikel ≈ 3 s · Zeit ×{x}', en: 'Simulation · {n} tills · each person ≈ 40 s, each item ≈ 3 s · time ×{x}'},
  youWord: {es: 'Tú', pt: 'Tu', fr: 'Vous', de: 'Du', en: 'You'},
  yoursFastest: {es: 'Tu cola fue la más rápida', pt: 'A tua fila foi a mais rápida', fr: 'Votre file a été la plus rapide', de: 'Deine Schlange war die schnellste', en: 'Your line was the fastest'},
  anotherFastest: {es: 'Otra cola fue más rápida', pt: 'Outra fila foi mais rápida', fr: 'Une autre file a été plus rapide', de: 'Eine andere war schneller', en: 'Another line was faster'},
  tries: {es: '{n} veces en el súper', pt: '{n} idas ao supermercado', fr: '{n} passages au supermarché', de: '{n} Einkäufe', en: '{n} trips to the shop'},
  fullCarts: {es: '2 personas · carros llenos', pt: '2 pessoas · carrinhos cheios', fr: '2 personnes · chariots pleins', de: '2 Personen · volle Wagen', en: '2 people · full carts'},
  baskets: {es: '5 personas · cestas', pt: '5 pessoas · cestos', fr: '5 personnes · paniers', de: '5 Personen · Körbe', en: '5 people · baskets'},
  doneIn: {es: 'Termina en {t}', pt: 'Termina em {t}', fr: 'Fini en {t}', de: 'Fertig in {t}', en: 'Done in {t}'},
  headsRule: {es: 'Cada persona ≈ 40 s · cada artículo ≈ 3 s', pt: 'Cada pessoa ≈ 40 s · cada artigo ≈ 3 s', fr: 'Chaque personne ≈ 40 s · chaque article ≈ 3 s', de: 'Pro Person ≈ 40 s · pro Artikel ≈ 3 s', en: 'Each person ≈ 40 s · each item ≈ 3 s'},
  countHeads: {es: 'Cuenta cabezas, no carros', pt: 'Conta cabeças, não carrinhos', fr: 'Comptez les têtes, pas les chariots', de: 'Köpfe zählen, nicht Wagen', en: 'Count heads, not carts'},
  busy: {es: 'Ocupada el {p} % del tiempo', pt: 'Ocupada {p} % do tempo', fr: 'Occupée {p} % du temps', de: '{p} % der Zeit belegt', en: 'Busy {p} % of the time'},
  waitCurve: {es: 'Espera según lo ocupada que está la caja', pt: 'Espera conforme a ocupação da caixa', fr: 'Attente selon l’occupation de la caisse', de: 'Wartezeit je nach Auslastung der Kasse', en: 'Wait by how busy the till is'},
  differentPeople: {es: 'Clientes distintos', pt: 'Clientes diferentes', fr: 'Clients différents', de: 'Unterschiedliche Kunden', en: 'Different customers'},
  samePeople: {es: 'Todos tardan lo mismo', pt: 'Todos demoram o mesmo', fr: 'Tous prennent le même temps', de: 'Alle brauchen gleich lang', en: 'Everyone takes the same time'},
  timesService: {es: '×{n} el tiempo de cobro', pt: '×{n} o tempo de pagamento', fr: '×{n} le temps de passage', de: '×{n} der Kassierzeit', en: '×{n} the time to pay'},
  ifStayed: {es: 'Tú, si te hubieras quedado', pt: 'Tu, se tivesses ficado', fr: 'Vous, si vous étiez resté', de: 'Du, wärst du geblieben', en: 'You, had you stayed'},
  switching: {es: 'Cambiándote', pt: 'Mudando', fr: 'En changeant', de: 'Mit Wechsel', en: 'Switching'},
  staying: {es: 'Quedándote', pt: 'Ficando', fr: 'En restant', de: 'Geblieben', en: 'Staying'},
  outPerMinute: {es: 'Salen por minuto', pt: 'Saem por minuto', fr: 'Sortent par minute', de: 'Gehen pro Minute', en: 'Out per minute'},
  ahead: {es: 'Delante de ti', pt: 'À tua frente', fr: 'Devant vous', de: 'Vor dir', en: 'Ahead of you'},
  yourWait: {es: 'Tu espera', pt: 'A tua espera', fr: 'Votre attente', de: 'Deine Wartezeit', en: 'Your wait'},
  express: {es: '≤ 10 artículos', pt: '≤ 10 artigos', fr: '≤ 10 articles', de: '≤ 10 Artikel', en: '≤ 10 items'},
  withExpress: {es: 'Con caja rápida', pt: 'Com caixa rápida', fr: 'Avec caisse express', de: 'Mit Expresskasse', en: 'With an express till'},
  noExpress: {es: 'Sin caja rápida', pt: 'Sem caixa rápida', fr: 'Sans caisse express', de: 'Ohne Expresskasse', en: 'No express till'},
  littleWait: {es: 'Los que llevan poco esperan', pt: 'Quem leva pouco espera', fr: 'Ceux qui ont peu attendent', de: 'Wer wenig hat, wartet', en: 'Those with little wait'},
});

const LAPSE = 4;                               // seconds of shop per second of video
const RATE = (tills: number) => (tills * 0.93) / 94;   // ~93 % busy with the average customer (≈ 94 s): a Saturday
const BUSIEST = new Map<ShopRun, number>();
/** Where to start looking: the moment of the run with most people waiting (between 6 and 25 minutes in). */
const busiest = (run: ShopRun) => {
  if (!BUSIEST.has(run)) {
    let best = 360;
    let most = -1;
    for (let t = 360; t < 1500; t += 10) {
      const n = run.at(t).lines.reduce((a, l) => a + l.length, 0);
      if (n > most) {
        most = n;
        best = t;
      }
    }
    BUSIEST.set(run, Math.max(0, best - 60));
  }
  return BUSIEST.get(run)!;
};
const FROM = 150;
const fmt = (s: number) => (s < 60 ? `${Math.round(s)} s` : `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, '0')} min`);

// --- drawing ------------------------------------------------------------------------------------------------------------
type Look = {you?: number; ghost?: [number, number]; slowMark?: boolean; expressTill?: boolean};
type Spot = {id: number; x: number; y: number; paying: boolean};

/** Where everyone is: the payer at each till, the lines below (or one snake for a single line). */
const layout = (f: ShopFrame, tills: number, left: number, width: number, single: boolean) => {
  const cx = left + width / 2;
  const gap = Math.min(200, (width - 120) / tills);
  const tillX = (i: number) => cx + (i - (tills - 1) / 2) * gap;
  const TILL_Y = 380;
  const spots: Spot[] = [];
  f.paying.forEach((id, i) => id >= 0 && spots.push({id, x: tillX(i), y: TILL_Y - 30, paying: true}));
  if (single) {
    f.lines[0].forEach((id, slot) => {
      const row = Math.floor(slot / 7);
      const col = slot % 7;
      spots.push({id, x: cx + ((row % 2 ? 6 - col : col) - 3) * 62, y: TILL_Y + 230 + row * 92, paying: false});
    });
  } else {
    f.lines.forEach((line, i) => line.forEach((id, slot) => spots.push({id, x: tillX(i), y: TILL_Y + 110 + slot * 92, paying: false})));
  }
  return {spots, tillX, TILL_Y, cx};
};

/** Where everyone is, walking: each person's place averaged over the last ~1.2 s, so when a line moves up people
 * walk to their new place instead of jumping there; `moving` says who is walking now (a little sway). */
const WALK = {samples: 8, step: 0.15};
const walking = (run: ShopRun, f: ShopFrame, left: number, width: number, single: boolean) => {
  const now = layout(f, run.tills, left, width, single);
  const past = Array.from({length: WALK.samples}, (_, k) => layout(run.at(Math.max(0, f.t - (k + 1) * WALK.step)), run.tills, left, width, single).spots);
  const spots = now.spots.map((spot) => {
    let x = spot.x;
    let y = spot.y;
    let n = 1;
    for (const list of past) {
      const before = list.find((p) => p.id === spot.id);
      if (!before) break;                              // just arrived: from here on
      x += before.x;
      y += before.y;
      n++;
    }
    const sx = x / n;
    const sy = y / n;
    return {...spot, x: sx, y: sy, moving: Math.hypot(sx - spot.x, sy - spot.y) > 1.5};
  });
  return {...now, spots};
};

// a supermarket as people know it, flat: tiled floor, shelves full of products, checkouts with their belt, cashier and
// bagging end; people from above (hair, shoulders) in quiet colours — the colour code stays for what matters: the
// customer holding a till up gets a red ring, YOU are yellow
const PRODUCTS = ['#d9534f', '#f0ad4e', '#5cb85c', '#5bc0de', '#e8e4dc', '#9b59b6', '#f7dc6f', '#e67e22', '#3498db', '#c0392b'];
const SHIRTS = ['#8d99ae', '#adb5bd', '#6c7a89', '#a3917b', '#7f8c8d', '#b0a8b9', '#8a9a8c', '#9fa8b3'];
const HAIR = ['#2b2118', '#4a3426', '#1d1d1f', '#8a6a46', '#c9b28a', '#5b5b5b', '#a0522d'];
const SKIN = ['#f1d3b5', '#e8c4a0', '#c99a6e', '#8d5a3b', '#d9a77a'];
const CAPS = ['#2e4a7d', '#7d2e2e', '#3a5f3a', '#2b2b2b'];

export const Shopper: FC<{x: number; y: number; id: number; items: number; you?: boolean; slow?: boolean; paying?: boolean; scale?: number;
  sway?: number; side?: boolean}> = ({x, y, id, items, you = false, slow = false, paying = false, scale = 1, sway = 0, side = false}) => {
  const k = scale;
  const cart = items > 10;
  const shirt = you ? C.you : SHIRTS[id % SHIRTS.length];
  return (
    <g transform={`translate(${x} ${y}) scale(${k})`}>
      {!paying && (cart ? (
        // a wire trolley ahead of them, its load showing
        <g transform={side ? 'translate(30 -14) rotate(-90) scale(0.8)' : 'translate(0 -68)'}>
          <rect x={-17} y={-4} width={34} height={44} rx={4} fill="rgba(210,215,222,0.18)" stroke="#c3c9d2" strokeWidth={2} />
          {[8, 18, 28].map((yy) => <line key={yy} x1={-17} x2={17} y1={yy} y2={yy} stroke="#c3c9d2" strokeWidth={1} opacity={0.6} />)}
          {Array.from({length: Math.min(9, Math.ceil(items / 5))}, (_, j) => (
            <rect key={j} x={-13 + (j % 3) * 9} y={36 - Math.floor(j / 3) * 11 - 8} width={8} height={9} rx={1.5} fill={PRODUCTS[(id + j) % PRODUCTS.length]} />
          ))}
        </g>
      ) : (
        // a red basket in hand
        <g transform="translate(20 6)">
          <rect x={-9} y={-7} width={18} height={14} rx={3} fill="#c0392b" stroke="#8e2a20" strokeWidth={1.5} />
          {Array.from({length: Math.min(3, items)}, (_, j) => <rect key={j} x={-6 + j * 4} y={-4} width={4} height={6} fill={PRODUCTS[(id + j) % PRODUCTS.length]} />)}
        </g>
      ))}
      <ellipse cx={4} cy={9} rx={21} ry={13} fill="rgba(0,0,0,0.28)" />
      {slow && paying && <circle r={34} fill="none" stroke={C.red} strokeWidth={4} opacity={0.9} />}
      {you && <circle r={30} fill="none" stroke={C.you} strokeWidth={4} />}
      <g transform={`rotate(${sway * 6})`}>
        <ellipse cx={0} cy={2} rx={19} ry={12} fill={shirt} stroke="rgba(0,0,0,0.35)" strokeWidth={2} />
        <ellipse cx={-14} cy={4 + sway * 3} rx={5} ry={6} fill={shirt} opacity={0.9} />
        <ellipse cx={14} cy={4 - sway * 3} rx={5} ry={6} fill={shirt} opacity={0.9} />
        {id % 5 === 3 && <ellipse cx={0} cy={-5} rx={11} ry={10} fill={HAIR[id % HAIR.length]} />}
        <circle cx={0} cy={0} r={9.5} fill={id % 5 === 0 ? SKIN[id % SKIN.length] : HAIR[id % HAIR.length]} />
        <circle cx={0} cy={3} r={6} fill={SKIN[id % SKIN.length]} />
        {id % 6 === 1 && (
          <g>
            <circle cx={0} cy={-1} r={9.5} fill={CAPS[id % CAPS.length]} />
            <rect x={-6} y={4} width={12} height={5} rx={2} fill={CAPS[id % CAPS.length]} opacity={0.85} />
          </g>
        )}
        {id % 4 === 2 && !paying && (
          // looking at the phone while waiting
          <g>
            <rect x={-5} y={10} width={10} height={14} rx={2} fill="#111418" />
            <rect x={-3.5} y={11.5} width={7} height={10} rx={1} fill="#8fd3ff" opacity={0.85} />
          </g>
        )}
      </g>
    </g>
  );
};

const Store: FC<{run: ShopRun; f: ShopFrame; left: number; width: number; single: boolean; look?: Look}> = (
  {run, f, left, width, single, look = {}}) => {
  const byId = new Map(run.people.map((p) => [p.id, p]));
  const {spots, tillX, TILL_Y, cx} = walking(run, f, left, width, single);
  const tile = 56;
  return (
    <svg width={1920} height={1080} style={{position: 'absolute', clipPath: `inset(0 ${1920 - left - width}px 0 ${left}px)`}}>
      <defs>
        <radialGradient id="ceiling"><stop offset="0%" stopColor="#fff6dc" stopOpacity={0.22} /><stop offset="100%" stopColor="#fff6dc" stopOpacity={0} /></radialGradient>
        <linearGradient id="counter" x1="0" y1="0" x2="1" y2="0"><stop offset="0%" stopColor="#8a929e" /><stop offset="100%" stopColor="#6c7480" /></linearGradient>
      </defs>
      {/* the floor */}
      <rect x={left} y={0} width={width} height={1080} fill="#77726a" />
      {Array.from({length: Math.ceil(width / tile) + 1}, (_, i) => (
        <line key={`fx${i}`} x1={left + i * tile} y1={0} x2={left + i * tile} y2={1080} stroke="rgba(255,255,255,0.08)" strokeWidth={2} />
      ))}
      {Array.from({length: 20}, (_, i) => <line key={`fy${i}`} x1={left} y1={i * tile} x2={left + width} y2={i * tile} stroke="rgba(255,255,255,0.08)" strokeWidth={2} />)}
      {/* the lights in the ceiling, pools on the floor */}
      {Array.from({length: Math.max(1, Math.round(width / 420))}, (_, i) => [0, 1].map((r) => (
        <ellipse key={`l${i}${r}`} cx={left + (i + 0.5) * (width / Math.max(1, Math.round(width / 420)))} cy={420 + r * 380} rx={300} ry={220} fill="url(#ceiling)" />
      )))}
      {/* side shelves: the shop goes on */}
      {[left + 4, left + width - 30].map((sx, side) => (
        <g key={`side${side}`}>
          <rect x={sx} y={240} width={26} height={820} rx={3} fill="#555c67" />
          {Array.from({length: 40}, (_, j) => (
            <rect key={j} x={sx + 4 + (j % 2) * 9} y={246 + Math.floor(j / 2) * 40 + (j % 3) * 3} width={8} height={30} rx={1.5}
                  fill={PRODUCTS[(j * 3 + side * 5) % PRODUCTS.length]} opacity={0.75} />
          ))}
        </g>
      ))}
      {/* the shelves behind the tills */}
      {[0].map((row) => (
        <g key={`row${row}`}>
          <rect x={left + 40} y={118 + row * 78} width={width - 80} height={44} rx={4} fill="#5d646f" />
          {Array.from({length: Math.floor((width - 96) / 13)}, (_, j) => (
            <rect key={j} x={left + 48 + j * 13} y={124 + row * 78 + ((j * 7 + row * 3) % 3) * 2} width={10} height={14 + ((j * 5 + row) % 3) * 4} rx={1.5}
                  fill={PRODUCTS[(j * 3 + row * 5) % PRODUCTS.length]} opacity={0.85} />
          ))}
          {Array.from({length: Math.floor((width - 96) / 13)}, (_, j) => (
            <rect key={`b${j}`} x={left + 48 + j * 13} y={146 + row * 78} width={10} height={10} rx={1.5}
                  fill={PRODUCTS[(j * 7 + row * 2 + 4) % PRODUCTS.length]} opacity={0.75} />
          ))}
        </g>
      ))}
      {/* the checkouts: belt, register, cashier, the lane number */}
      {Array.from({length: run.tills}, (_, i) => {
        const x = tillX(i) + 44;
        const busy = f.paying[i] >= 0;
        const payer = busy ? byId.get(f.paying[i]) : undefined;
        const onBelt = payer ? Math.max(0, Math.min(8, Math.ceil((f.left[i] / Math.max(1, payer.service)) * Math.min(8, payer.items / 3 + 1)))) : 0;
        const shift = (f.t * 18) % 16;
        return (
          <g key={`t${i}`}>
            <rect x={x - 16} y={TILL_Y - 104} width={40} height={150} rx={6} fill="rgba(0,0,0,0.3)" />
            <rect x={x - 20} y={TILL_Y - 110} width={40} height={150} rx={6} fill="url(#counter)" />
            <rect x={x - 14} y={TILL_Y - 104} width={28} height={110} rx={3} fill="#22262d" />
            {busy && Array.from({length: 7}, (_, j) => (
              <line key={j} x1={x - 14} x2={x + 14} y1={TILL_Y - 100 + ((j * 16 + shift) % 110)} y2={TILL_Y - 100 + ((j * 16 + shift) % 110)} stroke="rgba(255,255,255,0.08)" />
            ))}
            {Array.from({length: onBelt}, (_, j) => (
              <rect key={`it${j}`} x={x - 8 + (j % 2) * 4} y={TILL_Y - 2 - j * 12} width={12} height={10} rx={2} fill={PRODUCTS[(f.paying[i] + j) % PRODUCTS.length]} />
            ))}
            {busy && payer && f.left[i] < payer.service * 0.5 && (
              <g>
                <rect x={x - 46} y={TILL_Y - 104} width={18} height={20} rx={3} fill="#d9c7a3" stroke="#a8956f" strokeWidth={1.5} />
                {payer.items > 10 && <rect x={x - 46} y={TILL_Y - 80} width={18} height={20} rx={3} fill="#d9c7a3" stroke="#a8956f" strokeWidth={1.5} />}
              </g>
            )}
            <rect x={x - 22} y={TILL_Y - 150} width={44} height={34} rx={5} fill="#4c535e" />
            <rect x={x - 14} y={TILL_Y - 144} width={20} height={14} rx={2} fill={busy ? '#9fe3c0' : '#3a3f47'} />
            <g transform={`translate(${x + 44} ${TILL_Y - 132})`}>
              <ellipse cx={0} cy={2} rx={17} ry={11} fill="#2f6f9f" stroke="rgba(0,0,0,0.35)" strokeWidth={2} />
              <circle cx={0} cy={0} r={9} fill={HAIR[(i + 2) % HAIR.length]} />
              <circle cx={0} cy={3} r={5.5} fill="#e8c4a0" />
            </g>
            <rect x={x + 26} y={TILL_Y - 186} width={34} height={26} rx={5} fill={busy ? C.green : '#4c535e'} />
            <text x={x + 43} y={TILL_Y - 166} textAnchor="middle" fill="#0b1020" fontFamily={FONT} fontSize={20} fontWeight={800}>{i + 1}</text>
            {look.expressTill && i === 0 && (
              <text x={x - 60} y={TILL_Y - 166} textAnchor="middle" fill={C.text} fontFamily={FONT} fontSize={24} fontWeight={800}>{tx('express')}</text>
            )}
          </g>
        );
      })}
      {single && Array.from({length: 4}, (_, r) => (
        // the belt barriers of a single line: posts and their tape
        <g key={`bar${r}`}>
          <line x1={cx - 230} x2={cx + 230} y1={TILL_Y + 184 + r * 92} y2={TILL_Y + 184 + r * 92} stroke="#c9b458" strokeWidth={3} opacity={0.6}
                strokeDasharray={r % 2 ? '0 40 420' : '420 40'} />
          {[-230, 0, 230].map((dx) => <circle key={dx} cx={cx + dx} cy={TILL_Y + 184 + r * 92} r={6} fill="#9aa3ad" />)}
        </g>
      ))}
      {look.ghost && (
        <circle cx={look.ghost[0]} cy={look.ghost[1] - 8} r={24} fill="none" stroke={C.you} strokeWidth={3} strokeDasharray="6 5" opacity={0.7} />
      )}
      {spots.map(({id, x, y, paying, moving}) => {
        const p = byId.get(id)!;
        const you = look.you === id;
        return (
          <g key={id}>
            <Shopper x={x} y={y - 8} id={id} items={p.items} you={you} slow={p.slow && look.slowMark === true} paying={paying}
                     sway={moving ? Math.sin(f.t * 9 + id) : 0} side={single && !paying} />
            {you && <text x={x} y={y - 46} textAnchor="middle" fill={C.you} fontFamily={FONT} fontSize={28} fontWeight={800}>{tx('youWord').toUpperCase()}</text>}
          </g>
        );
      })}
    </svg>
  );
};

const spotOf = (f: ShopFrame, tills: number, left: number, width: number, single: boolean, id: number): Anchor | null => {
  const s = layout(f, tills, left, width, single).spots.find((x) => x.id === id);
  return s ? {x: s.x, y: s.y - 8} : null;
};

// --- the jockey: a YOU who switches and loses (found once, deterministically) ------------------------------------------
const JOCKEY = new Map<string, {you: number; at: number; stay: ShopRun; go: ShopRun; stayEnd: number; goEnd: number}>();
const findJockey = (tills: number) => {
  const key = String(tills);
  if (JOCKEY.has(key)) return JOCKEY.get(key)!;
  const people = customers(RATE(tills), false, 47);
  let best: {you: number; at: number; stay: ShopRun; go: ShopRun; stayEnd: number; goEnd: number} | null = null;
  for (const p of people) {
    if (p.arrive < 400 || p.arrive > 1400) continue;
    // YOU joins line 0 behind a slow payer; 25 s later line 1 has moved and YOU goes to its end
    const at = Math.round(p.arrive + 25);
    const stay = runShop('many', tills, people, 'jockey', {you: p.id, at: 1e9, to: 1});
    const f = stay.at(p.arrive + 1);
    const line0 = f.lines.findIndex((l) => l.includes(p.id));
    if (line0 !== 0 || f.paying[0] < 0 || !people[f.paying[0]].slow) continue;
    const go = runShop('many', tills, people, 'jockey', {you: p.id, at, to: 1});
    const stayEnd = stay.start.get(p.id) ?? 1e9;
    const goEnd = go.start.get(p.id) ?? 1e9;
    if (goEnd - stayEnd > 20 && (!best || goEnd - stayEnd > best.goEnd - best.stayEnd)) best = {you: p.id, at, stay, go, stayEnd, goEnd};
  }
  if (!best) {
    const p = people.find((x) => x.arrive > 600)!;
    const stay = runShop('many', tills, people, 'jockey', {you: p.id, at: 1e9, to: 1});
    const go = runShop('many', tills, people, 'jockey', {you: p.id, at: p.arrive + 25, to: 1});
    best = {you: p.id, at: p.arrive + 25, stay, go, stayEnd: stay.start.get(p.id) ?? 0, goEnd: go.start.get(p.id) ?? 0};
  }
  JOCKEY.set(key, best);
  return best;
};

// --- the scenes ---------------------------------------------------------------------------------------------------------
const bar = (label: string, value: number, max: number, text: string, colour: string, o: number) => (
  <div key={label} style={{display: 'flex', alignItems: 'center', gap: 14, marginTop: 10}}>
    <div style={{width: 280, fontSize: 22, fontWeight: 700, textTransform: 'uppercase', color: colour}}>{label}</div>
    <div style={{flex: 1, height: 12, background: 'rgba(255,255,255,0.08)', borderRadius: 6}}>
      <div style={{width: `${Math.min(100, (value / Math.max(1e-9, max)) * 100 * Math.min(1, o * 1.3))}%`, height: 12, background: colour, borderRadius: 6}} />
    </div>
    <div style={{width: 120, textAlign: 'right', fontSize: 28, fontWeight: 800, fontVariantNumeric: 'tabular-nums'}}>{text}</div>
  </div>
);

const View: FC<WorldProps> = ({g, worldT, local, real = local, move, o, on}) => {
  const scene = param<string>(g, 'scene', 'comparar');
  const tills = Math.round(param(g, 'tills', scene === 'eleccion' ? 3 : 4));
  const base = runShop('many', tills, customers(RATE(tills), false, 31), 'base');
  const t = busiest(base) + worldT * LAPSE;
  const panelO = Math.max(o('panel'), o('wait'), o('results'));
  const marks: Record<string, Anchor | null> = {};
  let body: ReactElement;

  if (scene === 'eleccion') {
    const people = customers(RATE(tills), false, 31);
    const run = runShop('many', tills, people, 'base');
    const f = run.at(t);
    const you = f.lines[0][Math.min(2, f.lines[0].length - 1)] ?? -1;
    const tally = lottery(tills, 400);
    const n = Math.max(1, Math.min(400, Math.floor(interpolate(worldT, [0.5, 6], [1, 400], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}) ** 1)));
    const mine = tally[n - 1];
    marks.you = spotOf(f, tills, 0, 1150, false, you);
    body = (
      <>
        <Store run={run} f={f} left={0} width={1150} single={false} look={{you}} />
        <Panel o={Math.max(panelO, on * 0.9)} style={{right: 64, top: 300, width: 640}}>
          <Label>{tx('tries', {n})}</Label>
          {bar(tx('yoursFastest'), mine, n, `${Math.round((mine / n) * 100)} %`, C.green, 1)}
          {bar(tx('anotherFastest'), n - mine, n, `${Math.round(((n - mine) / n) * 100)} %`, C.red, 1)}
        </Panel>
      </>
    );
  } else if (scene === 'cabezas') {
    // two lines at two tills, deterministic: 2 full carts (25 items) against 5 baskets (3 items)
    const left = [25, 25];
    const right = [3, 3, 3, 3, 3];
    const time = (items: number) => SHOP.perPerson + SHOP.perItem * items;
    const clock = Math.max(0, worldT - 0.5) * 18;           // seconds of shop
    const lineState = (list: number[]) => {
      let done = 0;
      let acc = 0;
      for (const it of list) {
        if (clock >= acc + time(it)) {
          acc += time(it);
          done++;
        } else break;
      }
      return {done, total: list.reduce((a, b) => a + time(b), 0)};
    };
    const A = lineState(left);
    const B = lineState(right);
    const drawLine = (list: number[], x: number, done: number, total: number, label: string, colour: string) => (
      <g>
        <rect x={x - 60} y={260} width={120} height={56} rx={8} fill="#56606f" />
        {list.slice(done).map((items, k) => (
          <Shopper key={k} x={x} y={450 + k * 118} id={k + (x > 900 ? 3 : 0)} items={items} scale={1.6} />
        ))}
        <text x={x} y={200} textAnchor="middle" fill={colour} fontFamily={FONT} fontSize={34} fontWeight={800}>{label.toUpperCase()}</text>
        <text x={x} y={240} textAnchor="middle" fill={C.text} fontFamily={FONT} fontSize={30} fontWeight={800}>
          {done >= list.length ? `✓ ${fmt(total)}` : tx('doneIn', {t: fmt(total)})}
        </text>
      </g>
    );
    body = (
      <>
        <svg width={1920} height={1080} style={{position: 'absolute'}}>
          <rect width={1920} height={1080} fill="#3b4048" />
          {Array.from({length: 35}, (_, i) => <line key={i} x1={i * 56} y1={0} x2={i * 56} y2={1080} stroke="rgba(255,255,255,0.05)" />)}
          {Array.from({length: 20}, (_, i) => <line key={`y${i}`} x1={0} y1={i * 56} x2={1920} y2={i * 56} stroke="rgba(255,255,255,0.05)" />)}
          {drawLine(left, 620, A.done, A.total, tx('fullCarts'), C.green)}
          {drawLine(right, 1300, B.done, B.total, tx('baskets'), C.red)}
        </svg>
        <Panel o={Math.max(panelO, on * 0.9)} style={{left: '50%', bottom: 60, transform: 'translateX(-50%)', textAlign: 'center'}}>
          <div style={{fontSize: 34, fontWeight: 800}}>{tx('headsRule').toUpperCase()}</div>
          <Label color={C.accent}>{tx('countHeads')}</Label>
        </Panel>
      </>
    );
  } else if (scene === 'limite') {
    const busy = Number(param(g, 'ocupacion', 0.9));
    const people = customers(busy / 94, false, 53);
    const run = runShop('one', 1, people, `lim${busy}`);
    const f = run.at(busiest(run) + worldT * LAPSE);
    const W = 700;
    const H = 420;
    const X = (r: number) => ((r - 0.7) / 0.29) * W;
    const Y = (k: number) => H - Math.min(1, k / 40) * H;
    const curve = (cs2: number) => Array.from({length: 99}, (_, i) => 0.7 + i * 0.00293).map((r) => `${X(r).toFixed(1)},${Y(kingman(r, 1, cs2)).toFixed(1)}`).join(' ');
    const here = kingman(busy, 1, 1);
    body = (
      <>
        <Store run={run} f={f} left={0} width={900} single={false} />
        <Panel o={Math.max(panelO, on * 0.95)} style={{right: 64, top: 160, width: W + 50}}>
          <Label>{tx('waitCurve')}</Label>
          <svg width={W} height={H + 40} style={{display: 'block', marginTop: 12, overflow: 'visible'}}>
            {[0.8, 0.9, 0.95].map((r) => <line key={r} x1={X(r)} x2={X(r)} y1={0} y2={H} stroke="rgba(255,255,255,0.12)" strokeDasharray="5 6" />)}
            <polyline points={curve(0.1)} fill="none" stroke={C.green} strokeWidth={3} opacity={0.8} />
            <polyline points={curve(1)} fill="none" stroke={C.red} strokeWidth={4} />
            <circle cx={X(busy)} cy={Y(here)} r={11} fill={C.accent} stroke="#0b1020" strokeWidth={3} />
            <text x={X(busy) - 16} y={Y(here) - 18} textAnchor="end" fill={C.accent} fontFamily={FONT} fontSize={30} fontWeight={800}>
              {tx('timesService', {n: Math.round(here)})}
            </text>
            {[0.8, 0.9, 0.95].map((r) => <text key={r} x={X(r)} y={H + 32} textAnchor="middle" fill={C.label} fontFamily={FONT} fontSize={22} fontWeight={700}>{Math.round(r * 100)} %</text>)}
          </svg>
          <div style={{display: 'flex', gap: 24, marginTop: 6}}>
            <Label color={C.red}>■ {tx('differentPeople')}</Label><Label color={C.green}>■ {tx('samePeople')}</Label>
          </div>
        </Panel>
        <div style={{position: 'absolute', left: 64, top: 160, fontFamily: FONT, fontSize: 40, fontWeight: 800, color: C.text, textTransform: 'uppercase'}}>
          {tx('busy', {p: Math.round(busy * 100)})}
        </div>
      </>
    );
  } else if (scene === 'iguales') {
    const split = splitAt(g.prev, g.focus, move);
    const v = runShop('many', tills, customers(RATE(tills), false, 31), 'base');
    const e = runShop('many', tills, customers(RATE(tills), true, 31), 'equal');
    const A = longRun('many', tills, RATE(tills));
    const B = longRun('many', tills, RATE(tills), true);
    body = (
      <>
        <Store run={v} f={v.at(t)} left={0} width={split} single={false} />
        <Store run={e} f={e.at(t)} left={split} width={1920 - split} single={false} />
        <div style={{position: 'absolute', left: split - 2, top: 0, width: 4, height: 1080, background: C.night}} />
        <SideTitle text={tx('differentPeople')} style={{left: 48, top: 44}} />
        <SideTitle text={tx('samePeople')} style={{left: split + 48, top: 44}} />
        <Big o={panelO} label={tx('averageWaitShort')} value={fmt(A.mean)} color={C.red} style={{left: 48, bottom: 70}} />
        <Big o={panelO} label={tx('averageWaitShort')} value={fmt(B.mean)} color={C.green} style={{left: split + 48, bottom: 70}} />
      </>
    );
  } else if (scene === 'cambiar') {
    const j = findJockey(3);
    const t = people0(j.stay, j.you) - 6 + worldT * LAPSE;          // YOU arrives a second and a half in
    const run = t < j.at ? j.stay : j.go;
    const f = run.at(t);
    const ghostF = j.stay.at(t);
    const ghostSpot = t >= j.at ? spotOf(ghostF, 3, 0, 1920, false, j.you) : null;
    marks.you = spotOf(f, 3, 0, 1920, false, j.you);
    const slowPayer = f.paying[0];
    marks.slow = slowPayer >= 0 ? spotOf(f, 3, 0, 1920, false, slowPayer) : null;
    const over = Math.max(o('results'), o('panel'));
    body = (
      <>
        <Store run={run} f={f} left={0} width={1920} single={false} look={{you: j.you, slowMark: true, ghost: ghostSpot ? [ghostSpot.x, ghostSpot.y + 8] : undefined}} />
        {ghostSpot && (
          <div style={{position: 'absolute', left: ghostSpot.x - 160, top: ghostSpot.y + 30, width: 320, textAlign: 'center', fontFamily: FONT,
                       fontSize: 22, fontWeight: 800, color: C.you, opacity: 0.85, textTransform: 'uppercase'}}>{tx('ifStayed')}</div>
        )}
        <Panel o={over} style={{right: 64, top: 160, width: 560}}>
          {bar(tx('staying'), j.stayEnd - people0(j.stay, j.you), j.goEnd - people0(j.go, j.you), fmt(j.stayEnd - people0(j.stay, j.you)), C.green, over)}
          {bar(tx('switching'), j.goEnd - people0(j.go, j.you), j.goEnd - people0(j.go, j.you), fmt(j.goEnd - people0(j.go, j.you)), C.red, over)}
        </Panel>
      </>
    );
  } else if (scene === 'contar') {
    const people = customers(RATE(1), false, 61);
    const run = runShop('one', 1, people, 'count');
    const tc = busiest(run) + worldT * LAPSE;
    const f = run.at(tc);
    const out = run.people.filter((p) => {
      const e = run.end.get(p.id);
      return e !== undefined && e > tc - 60 * 4 && e <= tc;
    }).length / 4;                              // per minute, over the last four
    const you = f.lines[0][f.lines[0].length - 1] ?? -1;
    const ahead = Math.max(0, f.lines[0].indexOf(you)) + (f.paying[0] >= 0 ? 1 : 0);
    marks.you = spotOf(f, 1, 0, 1000, false, you);
    body = (
      <>
        <Store run={run} f={f} left={0} width={1000} single={false} look={{you}} />
        <Panel o={Math.max(panelO, on * 0.95)} style={{right: 90, top: 260, width: 640}}>
          {[[tx('outPerMinute'), num(out, 1)], [tx('ahead'), String(ahead)],
            [tx('yourWait'), out > 0 ? `≈ ${fmt((ahead / out) * 60)}` : '—']].map(([a, b], k) => (
            <div key={a} style={{display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginTop: k ? 14 : 0}}>
              <span style={{fontSize: 28, fontWeight: 700, textTransform: 'uppercase', color: k === 2 ? C.you : C.label}}>{a}</span>
              <span style={{fontSize: 52, fontWeight: 800, color: k === 2 ? C.you : C.text, fontVariantNumeric: 'tabular-nums'}}>{b}</span>
            </div>
          ))}
        </Panel>
      </>
    );
  } else if (scene === 'rapida') {
    const split = splitAt(g.prev, g.focus, move);
    const people = customers(RATE(tills), false, 31);
    const a = runShop('many', tills, people, 'base');
    const b = runShop('express', tills, people, 'base');
    const A = longRun('many', tills, RATE(tills));
    const B = longRun('express', tills, RATE(tills));
    body = (
      <>
        <Store run={a} f={a.at(t)} left={0} width={split} single={false} />
        <Store run={b} f={b.at(t)} left={split} width={1920 - split} single={false} look={{expressTill: true}} />
        <div style={{position: 'absolute', left: split - 2, top: 0, width: 4, height: 1080, background: C.night}} />
        <SideTitle text={tx('noExpress')} style={{left: 48, top: 44}} />
        <SideTitle text={tx('withExpress')} style={{left: split + 48, top: 44}} />
        <Big o={panelO} label={tx('littleWait')} value={fmt(A.small)} color={C.red} style={{left: 48, bottom: 70, width: 340}} />
        <Big o={panelO} label={tx('littleWait')} value={fmt(B.small)} color={C.green} style={{left: split + 48, bottom: 70, width: 340}} />
      </>
    );
  } else {
    // comparar: a line per till against one line
    const split = splitAt(g.prev, g.focus, move);
    const people = customers(RATE(tills), false, 31);
    const many = runShop('many', tills, people, 'base');
    const one = runShop('one', tills, people, 'base');
    const fa = many.at(t);
    const A = longRun('many', tills, RATE(tills));
    const B = longRun('one', tills, RATE(tills));
    // the customer the choice cost most so far (on screen now)
    let unlucky = -1;
    let worst = 0;
    for (const p of people) {
      if (p.arrive > t || p.arrive < t - 300) continue;
      const sa = Math.min(many.start.get(p.id) ?? t, t) - p.arrive;
      const sb = (one.start.get(p.id) ?? t) - p.arrive;
      if (sa - sb > worst && fa.lines.some((l) => l.includes(p.id))) {
        worst = sa - sb;
        unlucky = p.id;
      }
    }
    const slowSaid = (g.marks ?? []).some((m) => m.kind === 'slow' && real >= m.at - 0.2) || o('unlucky') > 0.3;
    marks.slow = fa.paying.map((id) => (id >= 0 && people[id].slow ? spotOf(fa, tills, 0, split, false, id) : null)).find(Boolean) ?? null;
    marks.line = {x: split + (1920 - split) / 2, y: 560};
    marks.you = o('unlucky') > 0.3 && unlucky >= 0 ? spotOf(fa, tills, 0, split, false, unlucky) : null;
    body = (
      <>
        <Store run={many} f={fa} left={0} width={split} single={false} look={{you: o('unlucky') > 0.3 ? unlucky : undefined, slowMark: slowSaid}} />
        <Store run={one} f={one.at(t)} left={split} width={1920 - split} single />
        <div style={{position: 'absolute', left: split - 2, top: 0, width: 4, height: 1080, background: C.night}} />
        {g.focus === 'right' && <div style={{position: 'absolute', left: 0, top: 0, width: split, height: 1080, background: 'rgba(5,8,20,0.45)'}} />}
        {g.focus === 'left' && <div style={{position: 'absolute', left: split, top: 0, right: 0, height: 1080, background: 'rgba(5,8,20,0.45)'}} />}
        <SideTitle text={tx('manyLines')} style={{left: 48, top: 44}} />
        <SideTitle text={tx('oneLine')} style={{left: split + 48, top: 44}} />
        <Big o={panelO} label={tx('averageWaitShort')} value={fmt(A.mean)} color={C.red} style={{left: 48, bottom: 70}} />
        <Big o={panelO} label={tx('averageWaitShort')} value={fmt(B.mean)} color={C.green} style={{left: split + 48, bottom: 70}} />
        <Big o={o('results')} label={tx('longestWait')} value={fmt(A.longest)} style={{left: 340, bottom: 70, width: 300}} />
        <Big o={o('results')} label={tx('longestWait')} value={fmt(B.longest)} style={{left: split + 340, bottom: 70, width: 300}} />
      </>
    );
  }
  return (
    <AbsoluteFill style={{background: C.night}}>
      {body}
      <Pointers marks={g.marks} local={real} at={marks} />
      <Note>{tx('queueNote', {n: scene === 'cabezas' ? 2 : scene === 'contar' || scene === 'limite' ? 1 : tills, x: LAPSE})}</Note>
    </AbsoluteFill>
  );
};

/** When this person arrived (the wait = start − arrival). */
const people0 = (run: ShopRun, id: number) => (run.people.find((p: Person) => p.id === id)?.arrive ?? 0);

export const colas: World = {View};
