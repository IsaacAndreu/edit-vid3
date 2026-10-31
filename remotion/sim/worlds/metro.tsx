// A metro platform seen from above (remotion/sim/crowd.ts, the social force model): a carriage with two doors, people
// getting off (light shirts) and people waiting to get on (blue). Scenes:
//  comparar  left those waiting stand in front of the doors and push in at once; right they wait beside the doors
//            until nobody else is getting off: the doors jam on the left, the right is emptied and filled in ~30 s
//  delante   only the blocked doors     · lados   only the free doors
import type {FC} from 'react';
import {AbsoluteFill} from 'remotion';
import {C, FONT, Label, Panel} from '../hud';
import {addWords, tx} from '../i18n';
import {Pointers, type Anchor} from '../look';
import {PLATFORM, platform, platformPeople, simulate, type Crowd} from '../crowd';
import {Big, Note, param, SideTitle, type World, type WorldProps} from '../world';
import {Person} from './multitud';

addWords({
  blockDoors: {es: 'Esperando delante de las puertas', pt: 'Esperando na frente das portas', fr: 'Devant les portes', de: 'Vor den Türen wartend', en: 'Waiting in front of the doors'},
  sideDoors: {es: 'Esperando a los lados', pt: 'Esperando dos lados', fr: 'Sur les côtés', de: 'Seitlich wartend', en: 'Waiting to the sides'},
  gotOff: {es: 'Han bajado', pt: 'Desceram', fr: 'Sont descendus', de: 'Ausgestiegen', en: 'Got off'},
  gotOn: {es: 'Han subido', pt: 'Subiram', fr: 'Sont montés', de: 'Eingestiegen', en: 'Got on'},
  doorsClose: {es: 'Las puertas cierran en', pt: 'As portas fecham em', fr: 'Fermeture des portes dans', de: 'Türen schließen in', en: 'Doors close in'},
  allDone: {es: 'Todos dentro y fuera a los', pt: 'Todos dentro e fora aos', fr: 'Tout le monde est passé à', de: 'Alle durch nach', en: 'Everyone through at'},
  metroNote: {es: 'Simulación con el modelo de fuerzas sociales (Helbing, 2000) · {n} bajan y {m} suben · puertas abiertas {d} s', pt: 'Simulação com o modelo de forças sociais (Helbing, 2000) · {n} descem e {m} sobem · portas abertas {d} s', fr: 'Simulation avec le modèle des forces sociales (Helbing, 2000) · {n} descendent, {m} montent · portes ouvertes {d} s', de: 'Simulation mit dem Social-Force-Modell (Helbing, 2000) · {n} steigen aus, {m} ein · Türen {d} s offen', en: 'Simulation with the social force model (Helbing, 2000) · {n} get off, {m} get on · doors open {d} s'},
});

const OFF = 30;
const ON = 30;
const OPEN = 40;                 // seconds the doors stay open
const SPEED = 1.5;               // seconds of platform per second of video

const runOf = (block: boolean): {c: Crowd; group: Uint8Array} => {
  const people = platformPeople(OFF, ON, block);
  const group = Uint8Array.from(people.map((p) => p.group));
  return {c: simulate(`metro:${block}`, platform(block, group), people, 60), group};
};
const count = (r: {c: Crowd; group: Uint8Array}, g: number, t: number) => r.c.outAt.filter((s, i) => r.group[i] === g && s <= t).length;
const allThrough = (r: {c: Crowd; group: Uint8Array}) => Math.max(...r.c.outAt);

const Platform: FC<{r: {c: Crowd; group: Uint8Array}; t: number; left: number; width: number}> = ({r, t, left, width}) => {
  const {w, car, h, doors, door} = PLATFORM;
  const s = Math.min((width - 120) / w, 820 / h);
  const ox = left + (width - w * s) / 2;
  const oy = 560 - (h * s) / 2;
  const X = (m: number) => ox + m * s;
  const Y = (m: number) => oy + m * s;
  const f = r.c.at(Math.min(t, 59.9));
  const closing = t > OPEN - 3 ? Math.min(1, (t - (OPEN - 3)) / 3) : 0;
  return (
    <svg width={1920} height={1080} style={{position: 'absolute', clipPath: `inset(0 ${1920 - left - width}px 0 ${left}px)`}}>
      <rect x={left} y={0} width={width} height={1080} fill="#2b2f36" />
      {/* the tracks behind the carriage */}
      <rect x={left} y={Y(0) - 70} width={width} height={60} fill="#1c1f24" />
      {[0, 1].map((k) => <line key={k} x1={left} x2={left + width} y1={Y(0) - 52 + k * 24} y2={Y(0) - 52 + k * 24} stroke="#7d848e" strokeWidth={4} />)}
      {/* the carriage */}
      <rect x={X(0)} y={Y(0)} width={w * s} height={car * s} rx={14} fill="#d9dde3" stroke="#8a919b" strokeWidth={6} />
      {Array.from({length: 7}, (_, k) => <rect key={k} x={X(1 + k * 2.1)} y={Y(0.25)} width={s * 1.1} height={s * 0.5} rx={4} fill="#aab4c0" />)}
      {/* the platform, its yellow line and the stairs out */}
      <rect x={X(0) - 30} y={Y(car)} width={w * s + 60} height={(h - car) * s} fill="#8d8f93" />
      <line x1={X(0) - 30} x2={X(w) + 30} y1={Y(car + 0.5)} y2={Y(car + 0.5)} stroke="#f2c14e" strokeWidth={6} strokeDasharray="18 10" />
      {Array.from({length: 6}, (_, k) => <rect key={k} x={X(3) + k * 3} y={Y(h - 0.6) + k * 3} width={X(13) - X(3) - k * 6} height={6} fill="#6f7277" />)}
      {doors.map((d) => (
        <g key={d}>
          <rect x={X(d - door / 2)} y={Y(car) - 7} width={(door / 2) * s * closing} height={14} fill="#8a919b" />
          <rect x={X(d + door / 2) - (door / 2) * s * closing} y={Y(car) - 7} width={(door / 2) * s * closing} height={14} fill="#8a919b" />
          <rect x={X(d) - 26} y={Y(car) + 10} width={52} height={20} rx={4} fill={closing > 0 ? C.red : C.green} opacity={0.9} />
        </g>
      ))}
      {Array.from(f.x).map((x, i) => (f.out[i] ? null : (
        <Person key={i} x={X(x)} y={Y(f.y[i])} s={s} i={i} push={f.push[i]} tint={r.group[i] ? '#8fc1ff' : undefined} />
      )))}
    </svg>
  );
};

const View: FC<WorldProps> = ({g, worldT, local, real = local, o, on}) => {
  const scene = param<string>(g, 'scene', 'comparar');
  const panel = Math.max(o('panel'), on * 0.9);
  const t = Math.min(OPEN, worldT * SPEED);
  const marks: Record<string, Anchor | null> = {doors: {x: 960, y: 330}};
  const stats = (r: {c: Crowd; group: Uint8Array}) => `${tx('gotOff')}: ${count(r, 0, t)}/${OFF} · ${tx('gotOn')}: ${count(r, 1, t)}/${ON}`;
  let body;
  if (scene === 'comparar') {
    const a = runOf(true);
    const b = runOf(false);
    body = (
      <>
        <Platform r={a} t={t} left={0} width={958} />
        <Platform r={b} t={t} left={962} width={958} />
        <div style={{position: 'absolute', left: 958, top: 0, width: 4, height: 1080, background: C.night}} />
        <SideTitle text={tx('blockDoors')} style={{left: 48, top: 30}} />
        <SideTitle text={tx('sideDoors')} style={{left: 1010, top: 30}} />
        <Big o={panel} label={tx('gotOn')} value={`${count(a, 1, t)}/${ON}`} color={count(a, 1, t) < count(b, 1, t) ? C.red : C.text} sub={`${tx('gotOff')}: ${count(a, 0, t)}/${OFF}`}
             style={{left: 48, bottom: 50, width: 300}} />
        <Big o={panel} label={tx('gotOn')} value={`${count(b, 1, t)}/${ON}`} color={C.green} sub={`${tx('gotOff')}: ${count(b, 0, t)}/${OFF}`}
             style={{left: 1010, bottom: 50, width: 300}} />
      </>
    );
  } else {
    const r = runOf(scene === 'delante');
    const through = allThrough(r);
    body = (
      <>
        <Platform r={r} t={t} left={0} width={1920} />
        <Panel o={panel} style={{right: 64, bottom: 50, width: 420}}>
          <Label>{tx('doorsClose')}</Label>
          <div style={{fontSize: 56, fontWeight: 800, color: OPEN - t < 8 ? C.red : C.text, fontVariantNumeric: 'tabular-nums'}}>{Math.max(0, Math.ceil(OPEN - t))} s</div>
          <Label>{stats(r)}</Label>
          {Number.isFinite(through) && t >= through && <Label color={C.green}>{tx('allDone')} {Math.round(through)} s</Label>}
        </Panel>
      </>
    );
  }
  return (
    <AbsoluteFill style={{background: C.night}}>
      {body}
      <Pointers marks={g.marks} local={real} at={marks} />
      <Note>{tx('metroNote', {n: OFF, m: ON, d: OPEN})}</Note>
    </AbsoluteFill>
  );
};

export const metro: World = {View, ambient: 'crowd'};
