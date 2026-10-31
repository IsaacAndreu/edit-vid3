// Lifts at the morning rush (remotion/sim/lift.ts), the building cut open from the side: the floors, the shafts with
// their cabins going up and down (the number inside: people on board), the lobby with the people waiting. Scenes:
//  pico   one building at 9 in the morning: the line in the lobby grows, each trip stops at almost every floor
//  zonas  the same people and lifts: left every lift goes to every floor; right half of them only to the low floors
//         and half only to the high ones — fewer stops per trip, each lift back sooner, the wait drops
import type {FC} from 'react';
import {AbsoluteFill} from 'remotion';
import {C, FONT, Label, Panel} from '../hud';
import {addWords, tx} from '../i18n';
import {LIFT, liftLong, runLifts, type LiftRun} from '../lift';
import {Pointers, type Anchor} from '../look';
import {Big, Note, param, SideTitle, type World, type WorldProps} from '../world';

addWords({
  allFloors: {es: 'Todos a todas las plantas', pt: 'Todos a todos os andares', fr: 'Tous à tous les étages', de: 'Alle in alle Etagen', en: 'Every lift, every floor'},
  zoned: {es: 'Por zonas: bajas y altas', pt: 'Por zonas: baixos e altos', fr: 'Par zones : bas et hauts', de: 'Nach Zonen: unten und oben', en: 'Zoned: low and high floors'},
  waitingLobby: {es: 'Esperando abajo', pt: 'Esperando no térreo', fr: 'En attente au rez-de-chaussée', de: 'Warten unten', en: 'Waiting in the lobby'},
  stopsTrip: {es: 'Paradas por viaje', pt: 'Paradas por viagem', fr: 'Arrêts par trajet', de: 'Halte pro Fahrt', en: 'Stops per trip'},
  lobby: {es: 'Vestíbulo', pt: 'Térreo', fr: 'Hall', de: 'Foyer', en: 'Lobby'},
  liftNote: {es: 'Simulación · {n} ascensores de {c} personas · 12 plantas · llegan {r} personas por minuto · tiempo ×{x}', pt: 'Simulação · {n} elevadores de {c} pessoas · 12 andares · chegam {r} pessoas por minuto · tempo ×{x}', fr: 'Simulation · {n} ascenseurs de {c} personnes · 12 étages · {r} personnes par minute · temps ×{x}', de: 'Simulation · {n} Aufzüge für {c} Personen · 12 Etagen · {r} Personen pro Minute · Zeit ×{x}', en: 'Simulation · {n} lifts of {c} people · 12 floors · {r} people a minute · time ×{x}'},
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

const View: FC<WorldProps> = ({g, worldT, local, real = local, o, on}) => {
  const scene = param<string>(g, 'scene', 'pico');
  const lifts = Math.round(param(g, 'ascensores', 4));
  const panel = Math.max(o('panel'), on * 0.9);
  const t = FROM + worldT * LAPSE;
  const marks: Record<string, Anchor | null> = {lobby: {x: 960, y: 950}};
  let body;
  if (scene === 'zonas') {
    const a = runLifts(lifts, false, RUSH);
    const b = runLifts(lifts, true, RUSH);
    const la = liftLong(lifts, false, RUSH);
    const lb = liftLong(lifts, true, RUSH);
    body = (
      <>
        <Building run={a} t={t} left={0} width={958} />
        <Building run={b} t={t} left={962} width={958} />
        <div style={{position: 'absolute', left: 958, top: 0, width: 4, height: 1080, background: C.night}} />
        <SideTitle text={tx('allFloors')} style={{left: 48, top: 40}} />
        <SideTitle text={tx('zoned')} style={{left: 1010, top: 40}} />
        <Big o={panel} label={tx('averageWaitShort')} value={fmt(la.mean)} color={C.red} sub={`${tx('stopsTrip')}: ${la.stops.toFixed(1)}`}
             style={{right: 1010, top: 130, width: 300}} />
        <Big o={panel} label={tx('averageWaitShort')} value={fmt(lb.mean)} color={C.green} sub={`${tx('stopsTrip')}: ${lb.stops.toFixed(1)}`}
             style={{right: 48, top: 130, width: 300}} />
      </>
    );
  } else {
    const run = runLifts(lifts, false, RUSH);
    const waiting = run.at(t).queue.reduce((s, l) => s + l.length, 0);
    body = (
      <>
        <Building run={run} t={t} left={0} width={1920} />
        <Panel o={panel} style={{right: 64, top: 52, width: 340}}>
          <Label>{tx('averageWaitShort')}</Label>
          <div style={{fontSize: 56, fontWeight: 800, color: recentWait(run, t) > 60 ? C.red : C.text, fontVariantNumeric: 'tabular-nums'}}>{fmt(recentWait(run, t))}</div>
          <Label>{tx('waitingLobby')}: {waiting}</Label>
          <Label>{tx('stopsTrip')}: {liftLong(lifts, false, RUSH).stops.toFixed(1)}</Label>
        </Panel>
      </>
    );
  }
  return (
    <AbsoluteFill style={{background: C.night}}>
      {body}
      <Pointers marks={g.marks} local={real} at={marks} />
      <Note>{tx('liftNote', {n: lifts, c: LIFT.cap, r: Math.round(RUSH * 60), x: LAPSE})}</Note>
    </AbsoluteFill>
  );
};

// a bell each time a cabin opens at the lobby (in sight: the first building)
const sounds = (g: WorldProps['g'], length: number) => {
  const run = runLifts(Math.round(param(g, 'ascensores', 4)), false, RUSH);
  const t0 = FROM + (g.at - g.since) * LAPSE;
  const dings: number[] = [];
  for (let s = 0.5; s < length; s += 0.5) {
    const a = run.at(t0 + (s - 0.5) * LAPSE);
    const b = run.at(t0 + s * LAPSE);
    if (b.pos.some((p, k) => p < 0.02 && a.pos[k] >= 0.02)) dings.push(s);
  }
  return {dings};
};

export const ascensores: World = {View, sounds, ambient: 'murmur'};
