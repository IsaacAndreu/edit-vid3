// Boarding a plane seen from above (remotion/sim/boarding.ts): the cabin cut open — seats 3 + 3, the aisle, the bins
// above each row filling with bags — and the passengers walking in from the jet bridge, stopping to stow (a red ring:
// everyone behind them stands still, light red), squeezing past the ones already sitting. Scenes (param scene):
//  comparar     back to front by blocks (top) against `method` (bottom): the same plane, the same people
//  carrera      every method at once, one plane each: blocks, random, window-middle-aisle, Steffen, and blocks with no
//               carry-on; the times as they finish
//  experimento  Steffen's 2011 test: 72 people in a 12-row mock-up, blocks against Steffen (≈ 7 min against 3.5)
//  pasillo      close up on the aisle: one person stows a bag and the line behind them stops
//  asientos     one row close up: the window passenger arrives late and the aisle and middle ones stand up
//  bloques      back to front: everybody stops in the same stretch (the heat strip under the plane), the rest is empty
//  maletas      the share of people with a carry-on (maletas): the bins fill and the last ones hunt for room
//  puerta       queueing at the gate early against waiting seated: minutes standing, and when each gets to the seat
import type {FC, ReactElement} from 'react';
import {AbsoluteFill, interpolate} from 'remotion';
import {C, FONT, Label, Panel} from '../hud';
import {addWords, num, tx} from '../i18n';
import {Pointers, type Anchor} from '../look';
import {BOARD, meanTime, runBoarding, type BoardRun} from '../boarding';
import {Big, clamp, Note, param, SideTitle, type World, type WorldProps} from '../world';

addWords({
  backToFront: {es: 'De atrás hacia delante, por bloques', pt: 'De trás para a frente, por blocos', fr: 'De l’arrière vers l’avant, par blocs', de: 'Von hinten nach vorn, in Blöcken', en: 'Back to front, by blocks'},
  methodRandom: {es: 'Al azar, sin grupos', pt: 'Ao acaso, sem grupos', fr: 'Au hasard, sans groupes', de: 'Zufällig, ohne Gruppen', en: 'Random, no groups'},
  methodSteffen: {es: 'Método Steffen', pt: 'Método Steffen', fr: 'Méthode Steffen', de: 'Steffen-Methode', en: 'Steffen method'},
  methodWindow: {es: 'Ventanilla, centro, pasillo', pt: 'Janela, meio, corredor', fr: 'Hublot, milieu, couloir', de: 'Fenster, Mitte, Gang', en: 'Window, middle, aisle'},
  noBags: {es: 'Sin maletas de mano', pt: 'Sem bagagem de mão', fr: 'Sans bagage cabine', de: 'Ohne Handgepäck', en: 'No carry-on bags'},
  boardingTime: {es: 'Tiempo de embarque', pt: 'Tempo de embarque', fr: 'Temps d’embarquement', de: 'Boarding-Zeit', en: 'Boarding time'},
  doneIn2: {es: 'Terminado', pt: 'Concluído', fr: 'Terminé', de: 'Fertig', en: 'Done'},
  stoppedBehind: {es: 'Parados en el pasillo', pt: 'Parados no corredor', fr: 'À l’arrêt dans le couloir', de: 'Stehen im Gang', en: 'Standing still in the aisle'},
  aisleEmpty: {es: 'Pasillo vacío', pt: 'Corredor vazio', fr: 'Couloir vide', de: 'Leerer Gang', en: 'Empty aisle'},
  whereStop: {es: 'Dónde se para la gente a guardar la maleta', pt: 'Onde as pessoas param para guardar a mala', fr: 'Où les gens s’arrêtent pour ranger leur valise', de: 'Wo die Leute zum Verstauen stehen bleiben', en: 'Where people stop to stow their bags'},
  binsFull: {es: 'Compartimentos llenos', pt: 'Compartimentos cheios', fr: 'Coffres pleins', de: 'Volle Gepäckfächer', en: 'Bins full'},
  hunting: {es: 'Buscando hueco', pt: 'À procura de espaço', fr: 'Cherchent de la place', de: 'Suchen Platz', en: 'Hunting for room'},
  withBag: {es: 'Con maleta de mano', pt: 'Com bagagem de mão', fr: 'Avec bagage cabine', de: 'Mit Handgepäck', en: 'With a carry-on'},
  experiment: {es: 'Experimento de 2011 · 72 personas · 12 filas', pt: 'Experiência de 2011 · 72 pessoas · 12 filas', fr: 'Expérience de 2011 · 72 personnes · 12 rangées', de: 'Experiment von 2011 · 72 Personen · 12 Reihen', en: 'The 2011 experiment · 72 people · 12 rows'},
  realResult: {es: 'En el experimento real: {t}', pt: 'Na experiência real: {t}', fr: 'Dans l’expérience réelle : {t}', de: 'Im echten Experiment: {t}', en: 'In the real experiment: {t}'},
  standUp: {es: 'Se levantan', pt: 'Levantam-se', fr: 'Se lèvent', de: 'Stehen auf', en: 'Stand up'},
  aisleBlocked: {es: 'Pasillo bloqueado', pt: 'Corredor bloqueado', fr: 'Couloir bloqué', de: 'Gang blockiert', en: 'Aisle blocked'},
  windowLast: {es: 'Llega tarde el de la ventanilla', pt: 'Chega tarde o da janela', fr: 'Le passager hublot arrive en dernier', de: 'Der Fensterplatz kommt zuletzt', en: 'The window seat arrives last'},
  windowFirst: {es: 'Primero el de la ventanilla', pt: 'Primeiro o da janela', fr: 'Le hublot d’abord', de: 'Zuerst der Fensterplatz', en: 'Window seat first'},
  queueEarly: {es: 'Haciendo cola antes de tiempo', pt: 'Na fila antes do tempo', fr: 'Dans la file en avance', de: 'Zu früh angestellt', en: 'Queueing early'},
  seatedWait: {es: 'Esperando sentado', pt: 'Esperando sentado', fr: 'Assis en attendant', de: 'Sitzend gewartet', en: 'Waiting seated'},
  standing: {es: 'De pie', pt: 'De pé', fr: 'Debout', de: 'Gestanden', en: 'Standing'},
  inSeat: {es: 'En tu asiento a los', pt: 'No teu lugar aos', fr: 'À ta place après', de: 'Am Platz nach', en: 'In your seat after'},
  callGroup: {es: 'Llaman a tu grupo', pt: 'Chamam o teu grupo', fr: 'On appelle ton groupe', de: 'Deine Gruppe wird aufgerufen', en: 'Your group is called'},
  gate: {es: 'Puerta', pt: 'Porta', fr: 'Porte', de: 'Gate', en: 'Gate'},
  boardNote: {es: 'Simulación · {n} pasajeros · un pasillo sin adelantar · guardar la maleta ≈ 4-13 s · levantarse para dejar pasar ≈ 4 s · tiempo ×{x}', pt: 'Simulação · {n} passageiros · um corredor sem ultrapassar · guardar a mala ≈ 4-13 s · levantar-se ≈ 4 s · tempo ×{x}', fr: 'Simulation · {n} passagers · un couloir sans dépassement · ranger la valise ≈ 4-13 s · se lever ≈ 4 s · temps ×{x}', de: 'Simulation · {n} Passagiere · ein Gang ohne Überholen · Verstauen ≈ 4-13 s · Aufstehen ≈ 4 s · Zeit ×{x}', en: 'Simulation · {n} passengers · one aisle, no overtaking · stowing ≈ 4-13 s · standing up ≈ 4 s · time ×{x}'},
});

const GROUP = ['#8fc1ff', '#c9a0ff', '#7fe0c0'];
const SKIN = ['#f1d3b5', '#e8c4a0', '#c99a6e', '#8d5a3b', '#d9a77a'];
const HAIR = ['#2b2118', '#4a3426', '#1d1d1f', '#8a6a46', '#c9b28a', '#5b5b5b'];
const mmss = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
const METHOD: Record<string, string> = {random: 'azar', azar: 'azar', steffen: 'steffen', window: 'vcp', vcp: 'vcp', sinmaletas: 'bloques', bloques: 'bloques'};
const NAME: Record<string, string> = {bloques: 'backToFront', azar: 'methodRandom', vcp: 'methodWindow', steffen: 'methodSteffen'};

/** A passenger from above: shoulders in their group's colour, head; a bag over their head while stowing. */
const Person: FC<{x: number; y: number; s: number; i: number; colour: string; ring?: string; tint?: number; bag?: boolean; lift?: number}> = (
  {x, y, s, i, colour, ring, tint = 0, bag, lift = 0}) => (
  <g transform={`translate(${x} ${y})`}>
    {tint > 0 && <circle r={s * 0.62} fill={C.red} opacity={0.22 * tint} />}
    {ring && <circle r={s * 0.55} fill="none" stroke={ring} strokeWidth={Math.max(2, s * 0.09)} />}
    <ellipse rx={s * 0.42} ry={s * 0.28} fill={colour} stroke="rgba(0,0,0,0.4)" strokeWidth={1.2} />
    <circle r={s * 0.17} fill={HAIR[i % HAIR.length]} />
    <circle cy={s * 0.05} r={s * 0.1} fill={SKIN[i % SKIN.length]} />
    {bag && <rect x={-s * 0.24} y={-s * 0.5 - lift * s * 0.35} width={s * 0.48} height={s * 0.3} rx={s * 0.06} fill="#4a4f5a" stroke="#22262c" strokeWidth={1} />}
  </g>
);

type Box = {x: number; y: number; w: number; h: number; from?: number; to?: number};

/** The cabin and everybody in it at second t: nose on the left with the door, rows to the right. `from`/`to`: the rows shown
 * (a close-up). */
const Cabin: FC<{run: BoardRun; t: number; box: Box; label?: string; you?: number}> = ({run, t, box, label, you}) => {
  const rows = run.rows;
  const from = box.from ?? 1;
  const to = box.to ?? rows;
  const nose = from === 1 ? Math.min(140, box.w * 0.08) : 0;
  const pitch = (box.w - nose - 20) / (to - from + 1);
  const seat = Math.min(pitch * 0.82, (box.h - 30) / 7.2);
  const aisleH = seat * 1.15;
  const cy = box.y + box.h / 2;
  const rowX = (r: number) => box.x + nose + (r - from + 0.5) * pitch;
  const seatY = (sIdx: number) => (sIdx < 3 ? cy - aisleH / 2 - (3 - sIdx - 0.5) * seat : cy + aisleH / 2 + (sIdx - 3 + 0.5) * seat);
  const k = t / BOARD.dt;
  const f0 = run.at(Math.floor(k) * BOARD.dt);
  const f1 = run.at(Math.ceil(k) * BOARD.dt);
  const mix = k - Math.floor(k);
  const top = cy - aisleH / 2 - 3 * seat;
  const bottom = cy + aisleH / 2 + 3 * seat;
  const visible = (r: number) => r >= from - 0.5 && r <= to + 0.5;
  const people: ReactElement[] = [];
  const queue: number[] = [];
  run.pax.forEach((p, i) => {
    const ph = f1.phase[i];
    if (ph === 0) {
      queue.push(i);
      return;
    }
    const colour = i === you ? C.you : GROUP[p.group % GROUP.length];
    if (ph === 4 || (ph === 3 && f0.phase[i] === 4)) {
      if (visible(p.row)) people.push(<Person key={i} x={rowX(p.row)} y={seatY(p.seat)} s={seat} i={i} colour={colour} />);
      return;
    }
    const pos = f0.pos[i] < 0 ? f1.pos[i] : f0.pos[i] + (f1.pos[i] - f0.pos[i]) * mix;
    const x = pos <= 0 ? box.x + nose * 0.4 : rowX(pos);
    if (!visible(pos) && pos > 0) return;
    const stowing = ph === 2;
    const seating = ph === 3;
    people.push(
      <Person key={i} x={x} y={seating ? (cy + seatY(p.seat)) / 2 : cy} s={seat} i={i} colour={colour}
              ring={stowing ? C.red : i === you ? C.you : undefined} tint={f1.blocked[i] ? 1 : 0} bag={stowing && p.bag} lift={stowing ? 0.6 + 0.4 * Math.sin(t * 4 + i) : 0} />,
    );
  });
  const doneAt = run.done;
  return (
    <svg width={1920} height={1080} style={{position: 'absolute', overflow: 'visible'}}>
      {/* the fuselage */}
      <path d={`M${box.x + (from === 1 ? nose * 0.15 : 0)},${cy} ${from === 1 ? `Q${box.x},${top - 18} ${box.x + nose},${top - 18}` : `L${box.x},${top - 18}`} L${box.x + box.w},${top - 18}
               L${box.x + box.w},${bottom + 18} L${box.x + nose},${bottom + 18} ${from === 1 ? `Q${box.x},${bottom + 18} ${box.x + nose * 0.15},${cy}` : `L${box.x},${bottom + 18}`} Z`}
            fill="#e9ecf1" stroke="#9aa3ad" strokeWidth={3} />
      <rect x={box.x + nose} y={top - 6} width={box.w - nose} height={bottom - top + 12} fill="#c9ced6" />
      <rect x={box.x + nose} y={cy - aisleH / 2} width={box.w - nose} height={aisleH} fill="#7d8796" />
      {/* the bins over each row, filling with bags */}
      {Array.from({length: to - from + 1}, (_, j) => {
        const r = from + j;
        return [0, 1].map((side) => {
          const n = f1.bins[r * 2 + side];
          const full = n >= BOARD.binCap;
          const y = side ? bottom + 2 : top - 16;
          return (
            <g key={`b${r}${side}`}>
              <rect x={rowX(r) - pitch / 2 + 2} y={y} width={pitch - 4} height={14} rx={2} fill={full ? '#b25b52' : '#d9dde3'} stroke="#8a919b" strokeWidth={1} />
              <rect x={rowX(r) - pitch / 2 + 2} y={y} width={(pitch - 4) * Math.min(1, n / BOARD.binCap)} height={14} rx={2} fill={full ? '#e26b5f' : '#5d6470'} opacity={0.85} />
            </g>
          );
        });
      })}
      {/* the seats */}
      {Array.from({length: to - from + 1}, (_, j) => [0, 1, 2, 3, 4, 5].map((sIdx) => (
        <rect key={`s${j}${sIdx}`} x={rowX(from + j) - seat * 0.42} y={seatY(sIdx) - seat * 0.42} width={seat * 0.84} height={seat * 0.84} rx={seat * 0.18}
              fill="#3f5a8a" stroke="#2b3f63" strokeWidth={1} />
      )))}
      {pitch > 30 && Array.from({length: to - from + 1}, (_, j) => (
        <text key={`n${j}`} x={rowX(from + j)} y={cy + 5} textAnchor="middle" fill="rgba(255,255,255,0.35)" fontFamily={FONT} fontSize={Math.min(18, pitch * 0.4)} fontWeight={700}>{from + j}</text>
      ))}
      {from === 1 && <rect x={box.x + nose * 0.55} y={top - 30} width={nose * 0.32} height={14} rx={3} fill="#4c535e" />}
      {/* the line still in the jet bridge */}
      {from === 1 && queue.slice(0, 8).map((i, q) => (
        <Person key={`q${i}`} x={box.x - 30 - q * seat * 0.9} y={top - 40 - seat * 0.2} s={seat * 0.9} i={i} colour={i === you ? C.you : GROUP[run.pax[i].group % GROUP.length]} />
      ))}
      {people}
      {label && (
        <text x={box.x + nose + 8} y={top - 30} fill={C.text} fontFamily={FONT} fontSize={Math.min(34, box.h * 0.17)} fontWeight={800}
              style={{textTransform: 'uppercase'}}>{label}</text>
      )}
      <text x={box.x + box.w} y={top - 30} textAnchor="end" fill={t >= doneAt && doneAt > 0 ? C.green : C.text} fontFamily={FONT}
            fontSize={Math.min(40, box.h * 0.2)} fontWeight={800} style={{fontVariantNumeric: 'tabular-nums'}}>
        {t >= doneAt && doneAt > 0 ? `✓ ${mmss(doneAt)}` : mmss(t)}
      </text>
    </svg>
  );
};

/** One row close up: the window passenger arrives late and the two already sitting stand up (left); the same row with
 * the window seat first (right). A small story, looped every 14 s. */
const Row: FC<{t: number}> = ({t}) => {
  const p = t % 14;
  const k = (a: number, b: number) => interpolate(p, [a, b], [0, 1], clamp);
  const lerp = (a: [number, number], b: [number, number], q: number): [number, number] => [a[0] + (b[0] - a[0]) * q, a[1] + (b[1] - a[1]) * q];
  const panelOf = (x0: number, title: string, people: [number, number, number, string, string?][], blocked: number, stood: number) => {
    const y0 = 260;
    return (
      <g key={title}>
        <rect x={x0} y={y0} width={860} height={560} rx={24} fill="#c9ced6" />
        <rect x={x0} y={y0 + 380} width={860} height={180} fill="#7d8796" />
        {[0, 1, 2].map((s2) => <rect key={s2} x={x0 + 70 + s2 * 190} y={y0 + 80} width={160} height={190} rx={26} fill="#3f5a8a" stroke="#2b3f63" strokeWidth={3} />)}
        {people.map(([x, y, i, colour, ring]) => <Person key={i} x={x0 + x} y={y0 + y} s={130} i={i} colour={colour} ring={ring} />)}
        <text x={x0} y={y0 - 30} fill={C.text} fontFamily={FONT} fontSize={44} fontWeight={800} style={{textTransform: 'uppercase'}}>{title}</text>
        <text x={x0 + 860} y={y0 + 630} textAnchor="end" fill={blocked > 0.5 ? C.red : C.green} fontFamily={FONT} fontSize={44} fontWeight={800}>
          {tx('aisleBlocked')}: {Math.round(blocked)} s · {tx('standUp')}: {stood}
        </text>
      </g>
    );
  };
  // seat centres (window, middle, aisle) and places in the aisle
  const seat = (s2: number): [number, number] => [150 + s2 * 190, 175];
  const aisle = (n: number): [number, number] => [560 + n * 120, 470];
  // left: aisle (A) and middle (M) are sitting; the window one (W) arrives
  const A = p < 3 ? seat(2) : p < 9.5 ? lerp(seat(2), aisle(1.6), k(3, 4)) : lerp(aisle(1.6), seat(2), k(9.5, 10.5));
  const M = p < 4.5 ? seat(1) : p < 8.5 ? lerp(seat(1), aisle(0.8), k(4.5, 5.8)) : lerp(aisle(0.8), seat(1), k(8.5, 9.6));
  const W = p < 1 ? [980, 470] as [number, number] : p < 6 ? lerp([980, 470], aisle(-0.6), k(1, 2.4)) : lerp(aisle(-0.6), seat(0), k(6, 7.5));
  const blockedL = Math.max(0, Math.min(p, 10.5) - 2.4);
  const behind: [number, number, number, string][] = [0, 1].map((n) => [760 + n * 110, 470, 5 + n, GROUP[1]]);
  // right: the window one sits first, then middle and aisle walk straight in
  const W2: [number, number] = p < 1 ? [980, 470] : p < 3 ? lerp([980, 470], seat(0), k(1, 3)) : seat(0);
  const M2: [number, number] = p < 3.5 ? [980, 470] : lerp([980, 470], seat(1), k(3.5, 5.2));
  const A2: [number, number] = p < 5.5 ? [980, 470] : lerp([980, 470], seat(2), k(5.5, 7));
  return (
    <svg width={1920} height={1080} style={{position: 'absolute', overflow: 'hidden'}}>
      {panelOf(60, tx('windowLast'), [
        ...behind.map(([x, y, i, c]) => [x, y, i, c] as [number, number, number, string]),
        [A[0], A[1], 1, GROUP[2]], [M[0], M[1], 2, GROUP[2]], [W[0], W[1], 0, C.you, p > 2.4 && p < 7.5 ? C.red : undefined],
      ], blockedL, p > 4.5 ? 2 : p > 3 ? 1 : 0)}
      {panelOf(1000, tx('windowFirst'), [[W2[0], W2[1], 0, C.you], [M2[0], M2[1], 2, GROUP[2]], [A2[0], A2[1], 1, GROUP[2]]], 0, 0)}
    </svg>
  );
};

/** The gate: queueing early (left) against waiting seated until your group is called (right). */
const Gate: FC<{t: number; left: number; early: boolean; call: number; standUntil: number}> = (props) => (
  <>
    <GateMap {...props} />
    <Big o={1} label={tx('standing')} value={`${Math.round(standingOf(props))} min`} color={standingOf(props) > 10 ? C.red : C.green}
         style={{left: props.left + 40, top: 130, width: 300}} />
  </>
);
const standingOf = ({t, early, call, standUntil}: {t: number; early: boolean; call: number; standUntil: number}) =>
  early ? Math.min(t, standUntil) : Math.max(0, Math.min(t, standUntil) - call);
const GateMap: FC<{t: number; left: number; early: boolean; call: number; standUntil: number}> = ({t, left, early, call, standUntil}) => {
  const queue = 16;
  const youSeated = !early && t < call;
  return (
    <svg width={1920} height={1080} style={{position: 'absolute', clipPath: `inset(0 ${1920 - left - 958}px 0 ${left}px)`}}>
      <rect x={left} width={958} height={1080} fill="#b9b2a4" />
      {Array.from({length: 4}, (_, r) => Array.from({length: 7}, (_, c) => (
        <rect key={`${r}${c}`} x={left + 80 + c * 70} y={330 + r * 140} width={56} height={50} rx={8} fill="#5d6470" />
      )))}
      <rect x={left + 780} y={150} width={120} height={70} rx={8} fill="#2f3a4c" />
      <text x={left + 840} y={195} textAnchor="middle" fill="#fff" fontFamily={FONT} fontSize={30} fontWeight={800}>{tx('gate').toUpperCase()} B12</text>
      {Array.from({length: queue}, (_, q) => (
        <Person key={q} x={left + 840} y={270 + q * 46} s={46} i={q + 5} colour={GROUP[q % 3]} />
      ))}
      {Array.from({length: 9}, (_, s) => (
        <Person key={`s${s}`} x={left + 108 + (s % 7) * 70 + (s > 6 ? 0 : 0)} y={350 + Math.floor(s / 7) * 280 + (s % 2) * 140} s={46} i={s} colour={GROUP[(s + 1) % 3]} />
      ))}
      <Person x={youSeated ? left + 318 : left + 760} y={youSeated ? 490 : early ? 400 : 640} s={58} i={0} colour={C.you} ring={C.you} />
    </svg>
  );
};

// --- the world ----------------------------------------------------------------------------------------------------------------
const View: FC<WorldProps> = ({g, worldT, local, real = local, o, on}) => {
  const scene = param<string>(g, 'scene', 'comparar');
  const method = METHOD[param<string>(g, 'method', 'steffen')] ?? 'steffen';
  const bags = param(g, 'maletas', 0.85);
  const panel = Math.max(o('panel'), o('timer'), on * 0.9);
  const marks: Record<string, Anchor | null> = {};
  let body: ReactElement;
  let n = 180;
  let lapse = 20;
  if (scene === 'carrera') {
    const list: [string, number, string][] = [['bloques', 0.85, tx('backToFront')], ['azar', 0.85, tx('methodRandom')], ['vcp', 0.85, tx('methodWindow')],
      ['steffen', 0.85, tx('methodSteffen')], ['bloques', 0, tx('noBags')]];
    const t = worldT * lapse;
    body = (
      <>
        <AbsoluteFill style={{background: '#121a2a'}} />
        {list.map(([m, b, name], k) => (
          <Cabin key={k} run={runBoarding(m, 30, b)} t={t} box={{x: 170, y: 72 + k * 198, w: 1700, h: 140}} label={name} />
        ))}
      </>
    );
  } else if (scene === 'experimento') {
    lapse = 12;
    n = 72;
    const t = worldT * lapse;
    const a = runBoarding('bloques', 12, 0.85);
    const b = runBoarding('steffen', 12, 0.85);
    body = (
      <>
        <AbsoluteFill style={{background: '#121a2a'}} />
        <div style={{position: 'absolute', left: 0, right: 0, top: 50, textAlign: 'center', fontFamily: FONT, fontSize: 40, fontWeight: 800, color: C.label,
                      textTransform: 'uppercase', letterSpacing: 2}}>{tx('experiment')}</div>
        <Cabin run={a} t={t} box={{x: 260, y: 170, w: 1400, h: 330}} label={tx('backToFront')} />
        <Cabin run={b} t={t} box={{x: 260, y: 600, w: 1400, h: 330}} label={tx('methodSteffen')} />
        <Big o={t > a.done ? panel : 0} label={tx('boardingTime')} value={mmss(a.done)} color={C.red} sub={tx('realResult', {t: '6:54'})}
             style={{right: 40, top: 330, width: 300}} />
        <Big o={t > b.done ? panel : 0} label={tx('boardingTime')} value={mmss(b.done)} color={C.green} sub={tx('realResult', {t: '3:36'})}
             style={{right: 40, top: 760, width: 300}} />
      </>
    );
  } else if (scene === 'pasillo') {
    lapse = 3;
    const run = runBoarding('bloques', 30, bags);
    const t = 30 + worldT * lapse;
    const f = run.at(t);
    const stopped = run.pax.filter((_, i) => f.blocked[i]).length;
    body = (
      <>
        <AbsoluteFill style={{background: '#121a2a'}} />
        <Cabin run={run} t={t} box={{x: 60, y: 200, w: 1800, h: 720, from: 19, to: 30}} />
        <Big o={panel} label={tx('stoppedBehind')} value={String(stopped)} color={stopped > 2 ? C.red : C.text} style={{left: 60, top: 40, width: 360}} />
      </>
    );
    marks.bag = {x: 960, y: 560};
  } else if (scene === 'asientos') {
    body = (
      <>
        <AbsoluteFill style={{background: '#121a2a'}} />
        <Row t={worldT} />
      </>
    );
  } else if (scene === 'bloques' || scene === 'maletas') {
    lapse = 12;
    const run = runBoarding(scene === 'bloques' ? 'bloques' : 'bloques', 30, bags);
    const t = worldT * lapse;
    const f = run.at(t);
    const inAisle = run.pax.map((_, i) => i).filter((i) => f.phase[i] >= 1 && f.phase[i] <= 3);
    const used = new Set(inAisle.map((i) => Math.round(f.pos[i])));
    const empty = 1 - used.size / 30;
    const maxHeat = Math.max(1, ...Array.from(f.heat));
    const box = {x: 140, y: 230, w: 1740, h: 420};
    const pitch = (box.w - Math.min(140, box.w * 0.08) - 20) / 30;
    const full = Array.from({length: 60}, (_, j) => f.bins[j + 2] >= BOARD.binCap).filter(Boolean).length;
    const hunting = inAisle.filter((i) => f.phase[i] === 2 && run.hunt[i] > 0).length;
    body = (
      <>
        <AbsoluteFill style={{background: '#121a2a'}} />
        <Cabin run={run} t={t} box={box} label={scene === 'maletas' ? `${tx('withBag')}: ${Math.round(bags * 100)} %` : tx('backToFront')} />
        {scene === 'bloques' ? (
          <svg width={1920} height={1080} style={{position: 'absolute'}}>
            <text x={box.x + 140} y={760} fill={C.label} fontFamily={FONT} fontSize={26} fontWeight={800} style={{textTransform: 'uppercase'}}>{tx('whereStop')}</text>
            {Array.from({length: 30}, (_, j) => {
              const h = (f.heat[j + 1] / maxHeat) * 200;
              return <rect key={j} x={box.x + Math.min(140, box.w * 0.08) + j * pitch + 3} y={980 - h} width={pitch - 6} height={h} rx={3} fill={C.red} opacity={0.85} />;
            })}
          </svg>
        ) : null}
        {scene === 'bloques' ? (
          <Big o={panel} label={tx('aisleEmpty')} value={`${Math.round(empty * 100)} %`} color={empty > 0.5 ? C.red : C.text}
               sub={`${tx('stoppedBehind')}: ${run.pax.filter((_, i) => f.blocked[i]).length}`} style={{right: 40, top: 40, width: 360}} />
        ) : (
          <>
            <Big o={panel} label={tx('boardingTime')} value={mmss(meanTime('bloques', 30, bags))} color={bags > 0.6 ? C.red : C.green}
                 style={{right: 40, top: 720, width: 360}} />
            <Big o={panel} label={tx('binsFull')} value={`${full} / 60`} color={full > 20 ? C.red : C.text} sub={`${tx('hunting')}: ${hunting}`}
                 style={{left: 140, top: 720, width: 360}} />
          </>
        )}
      </>
    );
  } else if (scene === 'puerta') {
    lapse = 60;
    const call = 26;                     // minutes in: your group is called
    const t = worldT * lapse / 60;       // minutes
    body = (
      <>
        <Gate t={t} left={0} early call={call} standUntil={call + 6} />
        <Gate t={t} left={962} early={false} call={call} standUntil={call + 6.5} />
        <div style={{position: 'absolute', left: 958, top: 0, width: 4, height: 1080, background: C.night}} />
        <SideTitle text={tx('queueEarly')} style={{left: 48, top: 40}} />
        <SideTitle text={tx('seatedWait')} style={{left: 1010, top: 40}} />
        {t > call && t < call + 2 && (
          <Panel o={1} style={{left: '50%', top: 480, transform: 'translateX(-50%)'}}>
            <div style={{fontSize: 44, fontWeight: 800, color: C.you, textTransform: 'uppercase'}}>📢 {tx('callGroup')}</div>
          </Panel>
        )}
        <Big o={t > call + 6 ? panel : 0} label={tx('inSeat')} value={`${num(call + 6, 0)} min`} style={{left: 48, bottom: 80, width: 320}} />
        <Big o={t > call + 6.5 ? panel : 0} label={tx('inSeat')} value={`${num(call + 6.5, 1)} min`} style={{left: 1010, bottom: 80, width: 320}} />
      </>
    );
  } else {
    // comparar: back to front against the method
    const t = worldT * lapse;
    const other = param<string>(g, 'method', 'steffen') === 'sinmaletas' ? ['bloques', 0] as const : [method, bags] as const;
    const a = runBoarding('bloques', 30, bags);
    const b = runBoarding(other[0], 30, other[1]);
    body = (
      <>
        <AbsoluteFill style={{background: '#121a2a'}} />
        <Cabin run={a} t={t} box={{x: 170, y: 150, w: 1700, h: 360}} label={tx('backToFront')} />
        <Cabin run={b} t={t} box={{x: 170, y: 620, w: 1700, h: 360}} label={param<string>(g, 'method', 'steffen') === 'sinmaletas' ? tx('noBags') : tx(NAME[method])} />
      </>
    );
  }
  return (
    <AbsoluteFill style={{background: C.night}}>
      {body}
      <Pointers marks={g.marks} local={real} at={marks} />
      <Note>{tx('boardNote', {n, x: lapse})}</Note>
    </AbsoluteFill>
  );
};

export const embarque: World = {View, ambient: 'murmur'};
