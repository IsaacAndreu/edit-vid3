// Lifts (remotion/sim/lift.ts), the building cut open from the side: floors, shafts with their cabins going up and down
// (the number inside: people on board), people waiting on each floor (an arrow up or down), and on the side a ring with
// every car on its round trip — when they bunch, their dots come together. Scenes (param scene):
//  pico        9 in the morning, everyone going up from the lobby: each trip stops at almost every floor, the line grows
//  juntos      all day, two cars sweeping up and down, people on every floor: they start apart and end up together
//              (the late one finds more people and gets later, the one behind finds nobody and catches up)
//  autobuses   the same thing on a bus line (Newell & Potts, 1964): three buses on a ring end up in a bunch
//  reparto     the same building: any car stops for anyone (left, they bunch) against the system keeping them apart (right)
//  curva       the mean wait against how many people come: flat, then it shoots up (the 30 s line of a good office)
//  botones     one in two people press both buttons: cars going the other way stop for nobody (useless stops, counted)
//  zonas       the morning rush: every car to every floor (left) against half low floors, half high floors (right)
//  destino     the morning rush with a destination screen: each car takes the people going to its few floors
//  paternoster the open cabins that never stop: no wait, never bunched
//  otis        1854: Elisha Otis on a platform, the rope is cut and the safety brake bites
import type {FC, ReactElement} from 'react';
import {AbsoluteFill, interpolate} from 'remotion';
import {C, FONT, Label, Panel} from '../hud';
import {addWords, num, tx} from '../i18n';
import {LIFT, LOOP, bunching, liftLong, loopStats, phase, runLifts, runLoop, type LiftRun, type LoopRun} from '../lift';
import {Pointers, type Anchor} from '../look';
import {Big, clamp, Note, param, SideTitle, type World, type WorldProps} from '../world';

addWords({
  allFloors: {es: 'Todos a todas las plantas', pt: 'Todos a todos os andares', fr: 'Tous à tous les étages', de: 'Alle in alle Etagen', en: 'Every lift, every floor'},
  zoned: {es: 'Por zonas: bajas y altas', pt: 'Por zonas: baixos e altos', fr: 'Par zones : bas et hauts', de: 'Nach Zonen: unten und oben', en: 'Zoned: low and high floors'},
  waitingLobby: {es: 'Esperando abajo', pt: 'Esperando no térreo', fr: 'En attente au rez-de-chaussée', de: 'Warten unten', en: 'Waiting in the lobby'},
  stopsTrip: {es: 'Paradas por viaje', pt: 'Paradas por viagem', fr: 'Arrêts par trajet', de: 'Halte pro Fahrt', en: 'Stops per trip'},
  lobby: {es: 'Vestíbulo', pt: 'Térreo', fr: 'Hall', de: 'Foyer', en: 'Lobby'},
  liftNote: {es: 'Simulación · {n} ascensores de {c} personas · {f} plantas · cada parada ≈ 10 s + 1,5 s por persona · tiempo ×{x}', pt: 'Simulação · {n} elevadores de {c} pessoas · {f} andares · cada paragem ≈ 10 s + 1,5 s por pessoa · tempo ×{x}', fr: 'Simulation · {n} ascenseurs de {c} personnes · {f} étages · chaque arrêt ≈ 10 s + 1,5 s par personne · temps ×{x}', de: 'Simulation · {n} Aufzüge für {c} Personen · {f} Etagen · jeder Halt ≈ 10 s + 1,5 s pro Person · Zeit ×{x}', en: 'Simulation · {n} lifts of {c} people · {f} floors · each stop ≈ 10 s + 1.5 s a person · time ×{x}'},
  together: {es: 'Juntos', pt: 'Juntos', fr: 'Ensemble', de: 'Zusammen', en: 'Together'},
  apart: {es: 'Repartidos', pt: 'Espaçados', fr: 'Espacés', de: 'Verteilt', en: 'Spread out'},
  spacing: {es: 'Separación entre ascensores', pt: 'Distância entre elevadores', fr: 'Écart entre ascenseurs', de: 'Abstand der Aufzüge', en: 'Gap between lifts'},
  nearest: {es: 'Para el que esté más cerca', pt: 'Vai o mais próximo', fr: 'Le plus proche y va', de: 'Der nächste fährt', en: 'Nearest lift goes'},
  keepApart: {es: 'El sistema los mantiene repartidos', pt: 'O sistema mantém-nos espaçados', fr: 'Le système les espace', de: 'Das System hält sie verteilt', en: 'The system keeps them apart'},
  uselessStops: {es: 'Paradas para nadie', pt: 'Paragens para ninguém', fr: 'Arrêts pour personne', de: 'Halte für niemanden', en: 'Stops for nobody'},
  uselessHere: {es: 'Parada inútil', pt: 'Paragem inútil', fr: 'Arrêt inutile', de: 'Unnötiger Halt', en: 'Useless stop'},
  bothButtons: {es: 'La mitad pulsa los dos botones', pt: 'Metade carrega nos dois botões', fr: 'La moitié appuie sur les deux boutons', de: 'Die Hälfte drückt beide Knöpfe', en: 'Half press both buttons'},
  waitCurve: {es: 'Espera media según cuánta gente llega', pt: 'Espera média conforme quantos chegam', fr: 'Attente moyenne selon l’affluence', de: 'Mittlere Wartezeit je nach Andrang', en: 'Mean wait by how many people come'},
  perMinute: {es: '{n} personas por minuto', pt: '{n} pessoas por minuto', fr: '{n} personnes par minute', de: '{n} Personen pro Minute', en: '{n} people a minute'},
  goodOffice: {es: 'Un buen edificio: 30 s', pt: 'Um bom edifício: 30 s', fr: 'Un bon immeuble : 30 s', de: 'Gutes Bürohaus: 30 s', en: 'A good building: 30 s'},
  buttons: {es: 'Botones de siempre', pt: 'Botões de sempre', fr: 'Boutons classiques', de: 'Normale Knöpfe', en: 'Usual buttons'},
  destScreen: {es: 'Pantalla de destino', pt: 'Ecrã de destino', fr: 'Écran de destination', de: 'Zielwahl-Terminal', en: 'Destination screen'},
  neverWait: {es: 'Nunca esperas · nunca se juntan', pt: 'Nunca esperas · nunca se juntam', fr: 'On n’attend jamais · jamais groupés', de: 'Nie warten · nie gebündelt', en: 'You never wait · never bunched'},
  busLine: {es: 'Una línea de autobús', pt: 'Uma linha de autocarro', fr: 'Une ligne de bus', de: 'Eine Buslinie', en: 'A bus line'},
  busesTogether: {es: 'Autobuses juntos', pt: 'Autocarros juntos', fr: 'Bus groupés', de: 'Busse im Pulk', en: 'Buses bunched'},
  ropeCut: {es: '¡Cortad la cuerda!', pt: 'Cortem a corda!', fr: 'Coupez la corde !', de: 'Seil kappen!', en: 'Cut the rope!'},
  brake: {es: 'El freno se clava en las guías', pt: 'O travão crava nas guias', fr: 'Le frein mord les guides', de: 'Die Bremse greift in die Schienen', en: 'The brake bites the rails'},
});

const RUSH = 0.42;                          // people arriving per second at 9 a.m. (25 a minute)
const LAPSE = 4;                            // seconds of building per second of video
const FROM = 1200;                          // twenty minutes into the rush: the line has built up
const fmt = (s: number) => (s < 60 ? `${Math.round(s)} s` : `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, '0')} min`);
const ZONE = ['#8fc1ff', '#f5a623'];

/** The mean wait of those who got in during the last two minutes (what someone arriving now can expect). */
const recentWait = (run: LiftRun, t: number) => {
  let sum = 0;
  let n = 0;
  for (const p of run.riders) {
    const b = run.boarded.get(p.id);
    if (b !== undefined && b <= t && b > t - 120) {
      sum += b - p.arrive;
      n++;
    }
  }
  return n ? sum / n : 0;
};

const Building: FC<{run: LiftRun; t: number; left: number; width: number}> = ({run, t, left, width}) => {
  const f = run.at(t);
  const floors = LIFT.floors;
  const top = 150;
  const bottom = 930;
  const h = (bottom - top) / (floors + 1);
  const y = (floor: number) => bottom - (floor + 1) * h;          // top of the band of `floor`
  const shaftW = Math.min(86, (width * 0.55) / run.lifts - 14);
  const shaftsX = left + width * 0.42 - (run.lifts * (shaftW + 14)) / 2;
  const zoned = run.zones.some((z) => z.length < floors);
  const groupOf = (k: number) => (zoned ? (run.zones[k][0] === 1 ? 0 : 1) : -1);
  return (
    <svg width={1920} height={1080} style={{position: 'absolute', clipPath: `inset(0 ${1920 - left - width}px 0 ${left}px)`}}>
      <rect x={left} y={0} width={width} height={1080} fill="#1b2433" />
      <rect x={left + 40} y={top - 30} width={width - 80} height={bottom - top + 30} fill="#2a3446" stroke="#3c475b" strokeWidth={4} />
      {Array.from({length: floors + 1}, (_, k) => (
        <g key={k}>
          <line x1={left + 40} x2={left + width - 40} y1={y(k) + h} y2={y(k) + h} stroke="#46526a" strokeWidth={3} />
          {/* windows */}
          {k > 0 && Array.from({length: 4}, (_, j) => (
            <rect key={j} x={left + width * 0.66 + j * ((width * 0.3) / 4)} y={y(k) + h * 0.25} width={(width * 0.3) / 4 - 10} height={h * 0.45}
                  fill={(k * 7 + j * 3) % 5 === 0 ? '#ffe6a3' : '#3b4a63'} opacity={0.75} />
          ))}
          <text x={left + 60} y={y(k) + h * 0.68} fill={C.label} fontFamily={FONT} fontSize={Math.min(26, h * 0.5)} fontWeight={800}>
            {k === 0 ? tx('lobby').toUpperCase() : k}
          </text>
        </g>
      ))}
      {Array.from({length: run.lifts}, (_, k) => {
        const x = shaftsX + k * (shaftW + 14);
        const pos = f.pos[k];
        const cabY = y(pos) + 4;
        const tint = groupOf(k) >= 0 ? ZONE[groupOf(k)] : '#d4d9e2';
        return (
          <g key={k}>
            <rect x={x} y={top - 20} width={shaftW} height={bottom - top + 20} fill="#141b27" />
            {zoned && (
              // the floors this lift serves, marked along its shaft
              <rect x={x + shaftW - 6} y={y(Math.max(...run.zones[k]))} width={6} height={(Math.max(...run.zones[k]) - Math.min(...run.zones[k]) + 1) * h}
                    fill={tint} opacity={0.7} />
            )}
            <rect x={x + 4} y={cabY} width={shaftW - 8} height={h - 8} rx={5} fill={tint} stroke={f.open[k] ? C.you : 'rgba(0,0,0,0.4)'}
                  strokeWidth={f.open[k] ? 3 : 2} />
            <text x={x + shaftW / 2} y={cabY + h * 0.62} textAnchor="middle" fill="#10131a" fontFamily={FONT} fontSize={Math.min(30, h * 0.6)} fontWeight={800}>
              {f.load[k] || ''}
            </text>
          </g>
        );
      })}
      {/* the people waiting in the lobby, one dot each, by line */}
      {(() => {
        // the people waiting, one dot each, in rows from the lobby down (a second line, zoned: after the first)
        const x0 = shaftsX + run.lifts * (shaftW + 14) + 24;
        const perRow = Math.max(6, Math.floor((left + width - 70 - x0) / 24));
        const dots = [];
        let row = 0;
        for (const [g, line] of f.queue.entries()) {
          const shown = line.slice(0, perRow * 4);
          shown.forEach((id, i) => dots.push(
            <circle key={`${g}-${id}`} cx={x0 + (i % perRow) * 24} cy={y(0) + h * 0.5 + (row + Math.floor(i / perRow)) * 22} r={10}
                    fill={zoned ? ZONE[g] : '#d4d9e2'} stroke="rgba(0,0,0,0.45)" strokeWidth={2} />));
          if (line.length > shown.length) {
            dots.push(<text key={`more${g}`} x={x0 + perRow * 24} y={y(0) + h * 0.5 + (row + 3) * 22 + 8} fill={C.red} fontFamily={FONT} fontSize={26} fontWeight={800}>+{line.length - shown.length}</text>);
          }
          row += Math.max(1, Math.ceil(shown.length / perRow));
        }
        return dots;
      })()}
    </svg>
  );
};

const fmtWait = (s: number) => (s < 60 ? `${Math.round(s)} s` : `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, '0')} min`);
const CAR = ['#ffd23f', '#8fc1ff', '#7fe0c0', '#c9a0ff'];
const DAY = 0.12;                           // people a second, all day: enough for the lifts to bunch

/** The building for cars sweeping up and down: shafts, cabins, the people waiting on each floor (▲ ▼ and a count). */
const Tower: FC<{run: LoopRun; t: number; left: number; width: number}> = ({run, t, left, width}) => {
  const f = run.at(t);
  const F = LOOP.floors;
  const top = 140;
  const bottom = 960;
  const h = (bottom - top) / (F + 1);
  const y = (floor: number) => bottom - (floor + 1) * h;
  const shaftW = Math.min(90, width * 0.12);
  const x0 = left + width * 0.2;
  return (
    <svg width={1920} height={1080} style={{position: 'absolute', clipPath: `inset(0 ${1920 - left - width}px 0 ${left}px)`}}>
      <rect x={left} width={width} height={1080} fill="#1b2433" />
      <rect x={left + 30} y={top - 20} width={width * 0.62} height={bottom - top + 20} fill="#2a3446" stroke="#3c475b" strokeWidth={4} />
      {Array.from({length: F + 1}, (_, k) => (
        <g key={k}>
          <line x1={left + 30} x2={left + 30 + width * 0.62} y1={y(k) + h} y2={y(k) + h} stroke="#46526a" strokeWidth={2} />
          <text x={left + 46} y={y(k) + h * 0.7} fill={C.label} fontFamily={FONT} fontSize={Math.min(24, h * 0.6)} fontWeight={800}>{k === 0 ? tx('lobby').toUpperCase() : k}</text>
          {/* the people waiting here: a dot each, up on the left of the arrow, down on the right */}
          {Array.from({length: Math.min(10, f.up[k])}, (_, j) => <circle key={`u${j}`} cx={x0 + run.cars * (shaftW + 12) + 30 + j * 15} cy={y(k) + h * 0.35} r={6} fill="#d4d9e2" />)}
          {Array.from({length: Math.min(10, f.down[k])}, (_, j) => <circle key={`d${j}`} cx={x0 + run.cars * (shaftW + 12) + 30 + j * 15} cy={y(k) + h * 0.72} r={6} fill="#9aa3ad" />)}
          {f.up[k] > 0 && <text x={x0 + run.cars * (shaftW + 12) + 14} y={y(k) + h * 0.45} fill={C.green} fontFamily={FONT} fontSize={16} fontWeight={800}>▲</text>}
          {f.down[k] > 0 && <text x={x0 + run.cars * (shaftW + 12) + 14} y={y(k) + h * 0.82} fill="#ff9b8f" fontFamily={FONT} fontSize={16} fontWeight={800}>▼</text>}
        </g>
      ))}
      {f.pos.map((pos, k) => {
        const x = x0 + k * (shaftW + 12);
        return (
          <g key={k}>
            <rect x={x} y={top - 10} width={shaftW} height={bottom - top + 10} fill="#141b27" />
            <rect x={x + 4} y={y(pos) + 3} width={shaftW - 8} height={h - 6} rx={5} fill={CAR[k % CAR.length]} stroke={f.stopped[k] ? '#ffffff' : 'rgba(0,0,0,0.4)'} strokeWidth={f.stopped[k] ? 3 : 2} />
            <text x={x + shaftW / 2} y={y(pos) + h * 0.66} textAnchor="middle" fill="#10131a" fontFamily={FONT} fontSize={Math.min(24, h * 0.55)} fontWeight={800}>
              {f.dir[k] > 0 ? '▲' : '▼'}{f.load[k] || ''}
            </text>
            {f.useless[k] > 0 && (
              <text x={x + shaftW + 8} y={y(pos) + h * 0.66} fill={C.red} fontFamily={FONT} fontSize={22} fontWeight={800}>✕ {tx('uselessHere').toUpperCase()}</text>
            )}
          </g>
        );
      })}
    </svg>
  );
};

/** The round trip as a ring: each car a dot on its loop (up the right side, down the left); bunched cars sit together. */
const Ring: FC<{run: LoopRun; t: number; cx: number; cy: number; r?: number; bus?: boolean}> = ({run, t, cx, cy, r = 170, bus = false}) => {
  const f = run.at(t);
  const F = LOOP.floors;
  const ang = (ph: number) => -Math.PI / 2 + ph * Math.PI * 2;
  return (
    <svg width={1920} height={1080} style={{position: 'absolute', pointerEvents: 'none'}}>
      <circle cx={cx} cy={cy} r={r} fill="none" stroke={bus ? '#4a5263' : '#3c475b'} strokeWidth={bus ? 44 : 10} />
      {bus && <circle cx={cx} cy={cy} r={r} fill="none" stroke="#e8e4dc" strokeWidth={2} strokeDasharray="14 14" />}
      {Array.from({length: 2 * F}, (_, s2) => {
        const floor = s2 <= F ? s2 : 2 * F - s2;
        const waiting = s2 < F ? f.up[floor] : f.down[floor];
        const a = ang(s2 / (2 * F));
        const px = cx + Math.cos(a) * (r + (bus ? 46 : 22));
        const py = cy + Math.sin(a) * (r + (bus ? 46 : 22));
        return (
          <g key={s2}>
            <circle cx={cx + Math.cos(a) * r} cy={cy + Math.sin(a) * r} r={bus ? 5 : 3} fill="#6c7480" />
            {Array.from({length: Math.min(6, waiting)}, (_, j) => (
              <circle key={j} cx={px + Math.cos(a) * j * (bus ? 18 : 11)} cy={py + Math.sin(a) * j * (bus ? 18 : 11)} r={bus ? 8 : 4} fill="#d4d9e2" stroke="#10131a" strokeWidth={bus ? 2 : 0} />
            ))}
          </g>
        );
      })}
      {f.pos.map((pos, k) => {
        const a = ang(phase(pos, f.dir[k]));
        const x = cx + Math.cos(a) * r;
        const y = cy + Math.sin(a) * r;
        return bus ? (
          <g key={k} transform={`translate(${x} ${y}) rotate(${(a * 180) / Math.PI + 90})`}>
            <rect x={-58} y={-24} width={116} height={48} rx={10} fill={CAR[k % CAR.length]} stroke="#10131a" strokeWidth={3} />
            {[-38, -16, 6, 28].map((wx) => <rect key={wx} x={wx - 8} y={-17} width={16} height={34} rx={3} fill="rgba(20,26,36,0.55)" />)}
          </g>
        ) : <circle key={k} cx={x} cy={y} r={22} fill={CAR[k % CAR.length]} stroke="#10131a" strokeWidth={3} />;
      })}
    </svg>
  );
};

const Gap: FC<{run: LoopRun; t: number; style: React.CSSProperties; o: number}> = ({run, t, style, o}) => {
  const b = bunching(run.at(t));
  return (
    <Panel o={o} style={{width: 380, ...style}}>
      <Label>{tx('spacing')}</Label>
      <div style={{position: 'relative', height: 26, marginTop: 10, borderRadius: 13, background: 'rgba(255,255,255,0.12)'}}>
        <div style={{position: 'absolute', left: 0, top: 0, bottom: 0, width: `${(1 - b) * 100}%`, borderRadius: 13, background: b > 0.6 ? C.red : C.green}} />
      </div>
      <div style={{fontSize: 40, fontWeight: 800, marginTop: 6, color: b > 0.6 ? C.red : C.green, textTransform: 'uppercase'}}>{b > 0.6 ? tx('together') : tx('apart')}</div>
    </Panel>
  );
};

const recentLoopWait = (run: LoopRun, t: number) => {
  let sum = 0;
  let n = 0;
  run.boardedAt.forEach((b, i) => {
    if (b >= 0 && b <= t && b > t - 180) { sum += b - run.arrive[i]; n++; }
  });
  return n ? sum / n : 0;
};

const Paternoster: FC<{t: number}> = ({t}) => {
  const floors = 7;
  const h = 120;
  const top = 120;
  const shift = (t * 0.35 * h) % h;
  return (
    <svg width={1920} height={1080} style={{position: 'absolute'}}>
      <rect width={1920} height={1080} fill="#2a2420" />
      {Array.from({length: floors + 1}, (_, k) => (
        <g key={k}>
          <rect x={560} y={top + k * h} width={800} height={10} fill="#5b4a3a" />
          <text x={520} y={top + k * h + 60} textAnchor="end" fill="#c9b28a" fontFamily={FONT} fontSize={30} fontWeight={800}>{floors - k}</text>
        </g>
      ))}
      {[0, 1].map((side) => Array.from({length: floors + 2}, (_, k) => {
        const yy = side === 0 ? top - h + k * h + (h - shift) : top - h + k * h + shift;
        const x = 700 + side * 300;
        return (
          <g key={`${side}-${k}`}>
            <rect x={x} y={yy + 8} width={220} height={h - 20} fill="#7a5a3a" stroke="#c9a46a" strokeWidth={4} />
            <rect x={x + 10} y={yy + 18} width={200} height={h - 40} fill="#3a2a1e" />
            {(k + side) % 3 === 0 && <circle cx={x + 110} cy={yy + 60} r={22} fill={C.you} />}
            <text x={x + 110} y={yy + 4} textAnchor="middle" fill="#c9b28a" fontFamily={FONT} fontSize={26}>{side ? '▼' : '▲'}</text>
          </g>
        );
      }))}
    </svg>
  );
};

const Otis: FC<{t: number}> = ({t}) => {
  const rise = interpolate(t, [0, 3], [0, 1], clamp);
  const cut = t > 4.5;
  const drop = cut ? interpolate(t - 4.5, [0, 0.25], [0, 40], clamp) : 0;
  const py = 820 - rise * 460 + drop;
  return (
    <svg width={1920} height={1080} style={{position: 'absolute'}}>
      <rect width={1920} height={1080} fill="#d9c9a3" />
      <text x={1700} y={180} textAnchor="end" fill="#5b4a3a" fontFamily={FONT} fontSize={140} fontWeight={800} opacity={0.5}>1854</text>
      {/* the tower and its toothed rails */}
      {[760, 1160].map((x) => (
        <g key={x}>
          <rect x={x - 14} y={150} width={28} height={800} fill="#6b4f35" />
          {Array.from({length: 40}, (_, k) => <path key={k} d={`M${x + (x < 900 ? 14 : -14)},${170 + k * 20} l${x < 900 ? 12 : -12},10 l${x < 900 ? -12 : 12},10`} fill="#4a3624" />)}
        </g>
      ))}
      <rect x={740} y={130} width={440} height={30} fill="#6b4f35" />
      <circle cx={960} cy={145} r={26} fill="#4a3624" />
      {/* the rope: whole, then cut */}
      {!cut ? <line x1={960} y1={170} x2={960} y2={py} stroke="#8a6a46" strokeWidth={6} /> : (
        <>
          <line x1={960} y1={170} x2={960} y2={320} stroke="#8a6a46" strokeWidth={6} />
          <line x1={960} y1={py - 120} x2={960} y2={py} stroke="#8a6a46" strokeWidth={6} />
        </>
      )}
      {/* the platform with Otis on it, the pawls biting the rails */}
      <rect x={780} y={py} width={360} height={24} fill="#5b4a3a" />
      <g transform={`translate(960 ${py - 70})`}>
        <rect x={-22} y={0} width={44} height={70} rx={10} fill="#2b2b2b" />
        <circle cy={-14} r={20} fill="#e8c4a0" />
        <rect x={-26} y={-40} width={52} height={14} fill="#1d1d1f" />
        <rect x={-16} y={-62} width={32} height={26} fill="#1d1d1f" />
      </g>
      {cut && [790, 1130].map((x) => <path key={x} d={`M${x},${py + 12} l${x < 900 ? -24 : 24},-14`} stroke={C.red} strokeWidth={8} />)}
      {/* the crowd */}
      {Array.from({length: 18}, (_, k) => <circle key={k} cx={180 + k * 90} cy={1010 - (k % 2) * 20} r={28} fill={['#3a2a1e', '#5b4a3a', '#2b2b2b'][k % 3]} />)}
      <text x={960} y={1060} textAnchor="middle" fill="#3a2a1e" fontFamily={FONT} fontSize={36} fontWeight={800}>
        {(t < 4 ? '' : !cut ? tx('ropeCut') : tx('brake')).toUpperCase()}
      </text>
    </svg>
  );
};

const View: FC<WorldProps> = ({g, worldT, local, real = local, o, on}) => {
  const scene = param<string>(g, 'scene', 'pico');
  const lifts = Math.round(param(g, 'ascensores', 4));
  const panel = Math.max(o('panel'), on * 0.9);
  const marks: Record<string, Anchor | null> = {lobby: {x: 960, y: 950}};
  let body: ReactElement;
  let lapse = LAPSE;
  let floors = LIFT.floors;
  let cars = lifts;
  if (scene === 'juntos' || scene === 'botones') {
    lapse = 8;
    floors = LOOP.floors;
    cars = 2;
    const run = runLoop(2, scene === 'botones' ? 'botones' : 'cercano', DAY);
    const t = worldT * lapse;
    const counted = run.frames.slice(0, Math.round(t / LOOP.dt) + 1).reduce((s2, fr, j, all) => s2 + fr.useless.filter((u, k) => u > 3.9 && !(all[j - 1]?.useless[k] > 3.9)).length, 0);
    body = (
      <>
        <Tower run={run} t={t} left={0} width={1150} />
        <Ring run={run} t={t} cx={1500} cy={380} />
        {scene === 'juntos' ? <Gap run={run} t={t} o={panel} style={{right: 60, top: 640}} /> : (
          <Big o={panel} label={tx('uselessStops')} value={String(counted)} color={counted > 0 ? C.red : C.text}
               sub={`${tx('averageWaitShort')}: ${fmtWait(loopStats(2, 'botones', DAY).wait)} (${fmtWait(loopStats(2, 'cercano', DAY).wait)})`} style={{right: 60, top: 640, width: 380}} />
        )}
        {scene === 'botones' && <SideTitle text={tx('bothButtons')} style={{left: 48, top: 40}} />}
      </>
    );
  } else if (scene === 'autobuses') {
    lapse = 8;
    floors = LOOP.floors;
    cars = 3;
    const run = runLoop(3, 'cercano', 0.17);
    const t = worldT * lapse;
    body = (
      <>
        <AbsoluteFill style={{background: '#3b4a33'}} />
        <Ring run={run} t={t} cx={960} cy={560} r={380} bus />
        <SideTitle text={tx('busLine')} style={{left: 48, top: 40}} />
        <Gap run={run} t={t} o={panel} style={{right: 48, top: 40}} />
      </>
    );
  } else if (scene === 'reparto') {
    lapse = 8;
    floors = LOOP.floors;
    cars = 2;
    const a = runLoop(2, 'cercano', DAY);
    const b = runLoop(2, 'reparto', DAY);
    const t = worldT * lapse;
    const sa = loopStats(2, 'cercano', DAY);
    const sb = loopStats(2, 'reparto', DAY);
    body = (
      <>
        <Tower run={a} t={t} left={0} width={958} />
        <Tower run={b} t={t} left={962} width={958} />
        <Ring run={a} t={t} cx={760} cy={300} r={110} />
        <Ring run={b} t={t} cx={1722} cy={300} r={110} />
        <div style={{position: 'absolute', left: 958, top: 0, width: 4, height: 1080, background: C.night}} />
        <SideTitle text={tx('nearest')} style={{left: 48, top: 40}} />
        <SideTitle text={tx('keepApart')} style={{left: 1010, top: 40}} />
        <Big o={panel} label={tx('averageWaitShort')} value={fmtWait(sa.wait)} color={C.red} sub={`${tx('spacing')}: ${Math.round((1 - sa.bunch) * 100)} %`}
             style={{left: 590, top: 520, width: 330}} />
        <Big o={panel} label={tx('averageWaitShort')} value={fmtWait(sb.wait)} color={C.green} sub={`${tx('spacing')}: ${Math.round((1 - sb.bunch) * 100)} %`}
             style={{left: 1552, top: 520, width: 330}} />
      </>
    );
  } else if (scene === 'curva') {
    const rates = [0.03, 0.05, 0.07, 0.09, 0.11, 0.13, 0.145];
    const pts = rates.map((r) => [r, Math.min(300, loopStats(2, 'cercano', r).wait)] as const);
    const W = 1300;
    const H = 600;
    const X = (r: number) => ((r - 0.02) / 0.13) * W;
    const Y = (w: number) => H - (w / 300) * H;
    const grow = Math.min(1, real / 3);
    body = (
      <>
        <AbsoluteFill style={{background: '#121a2a'}} />
        <Panel o={on} style={{left: '50%', top: 130, transform: 'translateX(-50%)', width: W + 140, padding: '24px 40px'}}>
          <Label>{tx('waitCurve')}</Label>
          <svg width={W} height={H + 60} viewBox={`-120 0 ${W + 120} ${H + 60}`} style={{display: 'block', marginTop: 16, overflow: 'visible'}}>
            <line x1={0} x2={W} y1={Y(30)} y2={Y(30)} stroke={C.green} strokeWidth={3} strokeDasharray="10 8" />
            <text x={10} y={Y(30) - 12} fill={C.green} fontFamily={FONT} fontSize={28} fontWeight={800}>{tx('goodOffice').toUpperCase()}</text>
            {[60, 120, 180, 240, 300].map((w) => <text key={w} x={-14} y={Y(w) + 8} textAnchor="end" fill={C.label} fontFamily={FONT} fontSize={24}>{fmtWait(w)}</text>)}
            {rates.map((r) => <text key={r} x={X(r)} y={H + 44} textAnchor="middle" fill={C.label} fontFamily={FONT} fontSize={24}>{Math.round(r * 60)}</text>)}
            <polyline points={pts.filter(([r]) => X(r) <= W * grow + 1).map(([r, w]) => `${X(r)},${Y(w)}`).join(' ')} fill="none" stroke={C.accent} strokeWidth={6} />
          </svg>
          <Label>{tx('perMinute', {n: '→'})}</Label>
        </Panel>
      </>
    );
  } else if (scene === 'paternoster') {
    body = (
      <>
        <Paternoster t={worldT} />
        <Big o={panel} label={tx('averageWaitShort')} value="0 s" color={C.green} sub={tx('neverWait')} style={{right: 60, top: 60, width: 380}} />
      </>
    );
  } else if (scene === 'otis') {
    body = <Otis t={worldT} />;
  } else if (scene === 'zonas' || scene === 'destino') {
    const t = FROM + worldT * LAPSE;
    const a = runLifts(lifts, false, RUSH);
    const b = runLifts(lifts, scene === 'destino' ? 'bands' : true, RUSH);
    const la = liftLong(lifts, false, RUSH);
    const lb = liftLong(lifts, scene === 'destino' ? 'bands' : true, RUSH);
    body = (
      <>
        <Building run={a} t={t} left={0} width={958} />
        <Building run={b} t={t} left={962} width={958} />
        <div style={{position: 'absolute', left: 958, top: 0, width: 4, height: 1080, background: C.night}} />
        <SideTitle text={scene === 'destino' ? tx('buttons') : tx('allFloors')} style={{left: 48, top: 40}} />
        <SideTitle text={scene === 'destino' ? tx('destScreen') : tx('zoned')} style={{left: 1010, top: 40}} />
        <Big o={panel} label={tx('averageWaitShort')} value={fmtWait(la.mean)} color={C.red} sub={`${tx('stopsTrip')}: ${num(la.stops, 1)}`}
             style={{right: 1010, top: 130, width: 300}} />
        <Big o={panel} label={tx('averageWaitShort')} value={fmtWait(lb.mean)} color={C.green} sub={`${tx('stopsTrip')}: ${num(lb.stops, 1)}`}
             style={{right: 48, top: 130, width: 300}} />
      </>
    );
  } else {
    const run = runLifts(lifts, false, RUSH);
    const t = FROM + worldT * LAPSE;
    const waiting = run.at(t).queue.reduce((s2, l) => s2 + l.length, 0);
    body = (
      <>
        <Building run={run} t={t} left={0} width={1920} />
        <Panel o={panel} style={{right: 64, top: 52, width: 380}}>
          <Label>{tx('averageWaitShort')}</Label>
          <div style={{fontSize: 72, fontWeight: 800, color: recentWait(run, t) > 60 ? C.red : C.text, fontVariantNumeric: 'tabular-nums'}}>{fmtWait(recentWait(run, t))}</div>
          <Label>{tx('waitingLobby')}: {waiting}</Label>
          <Label>{tx('stopsTrip')}: {num(liftLong(lifts, false, RUSH).stops, 1)}</Label>
        </Panel>
      </>
    );
  }
  return (
    <AbsoluteFill style={{background: C.night}}>
      {body}
      <Pointers marks={g.marks} local={real} at={marks} />
      {scene !== 'otis' && scene !== 'paternoster' && scene !== 'curva' && (
        <Note>{tx('liftNote', {n: cars, c: scene === 'juntos' || scene === 'botones' || scene === 'reparto' || scene === 'autobuses' ? LOOP.cap : LIFT.cap, f: floors, x: lapse})}</Note>
      )}
    </AbsoluteFill>
  );
};

// a bell each time a cabin opens at the lobby; a hit when the rope is cut
const sounds = (g: WorldProps['g'], length: number) => {
  const scene = param<string>(g, 'scene', 'pico');
  const t0 = g.at - g.since;
  if (scene === 'otis') return {hits: [4.5 - t0].filter((s2) => s2 >= 0 && s2 < length)};
  if (scene === 'juntos' || scene === 'botones' || scene === 'reparto') {
    const run = runLoop(2, scene === 'botones' ? 'botones' : 'cercano', DAY);
    const dings: number[] = [];
    for (let s2 = 0.5; s2 < length; s2 += 0.5) {
      const a = run.at((t0 + s2 - 0.5) * 8);
      const b = run.at((t0 + s2) * 8);
      if (b.pos.some((p, k) => p === 0 && a.pos[k] > 0)) dings.push(s2);
    }
    return {dings};
  }
  const run = runLifts(Math.round(param(g, 'ascensores', 4)), false, RUSH);
  const start = FROM + t0 * LAPSE;
  const dings: number[] = [];
  for (let s2 = 0.5; s2 < length; s2 += 0.5) {
    const a = run.at(start + (s2 - 0.5) * LAPSE);
    const b = run.at(start + s2 * LAPSE);
    if (b.pos.some((p, k) => p < 0.02 && a.pos[k] >= 0.02)) dings.push(s2);
  }
  return {dings};
};

export const ascensores: World = {View, sounds, ambient: 'murmur'};
