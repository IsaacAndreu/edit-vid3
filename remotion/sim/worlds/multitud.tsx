// Crowds (remotion/sim/crowd.ts, the social force model): people seen from above who walk to a goal, keep their
// distance and push when they touch. Scenes (param scene):
//  evacuacion  a room empties through one door: the arch that forms in front of it, how many are out
//  columna     the same hurried crowd at the same door, without (left) and with a column just before it (right): the
//              column breaks the arch and everyone is out sooner
//  prisa       calm (left) against hurried (right): with hurry, bodies press hard against each other at the door
//  pasillo     a corridor walked both ways: lanes form by themselves, nobody organises them
import type {FC, ReactElement} from 'react';
import {AbsoluteFill} from 'remotion';
import {C, Label, Panel} from '../hud';
import {addWords, tx} from '../i18n';
import {Pointers, type Anchor} from '../look';
import {CORRIDOR, ROOM, corridor, corridorPeople, outBy, room, roomPeople, simulate, type Crowd} from '../crowd';
import {Big, Note, param, SideTitle, type World, type WorldProps} from '../world';

addWords({
  outside: {es: 'Han salido', pt: 'Saíram', fr: 'Sont sortis', de: 'Draußen', en: 'Out'},
  exitSign: {es: 'Salida', pt: 'Saída', fr: 'Sortie', de: 'Ausgang', en: 'Exit'},
  noColumn: {es: 'Puerta sola', pt: 'Só a porta', fr: 'Porte seule', de: 'Nur die Tür', en: 'Just the door'},
  withColumn: {es: 'Con una columna delante', pt: 'Com uma coluna à frente', fr: 'Avec une colonne devant', de: 'Mit einer Säule davor', en: 'A column in front'},
  lastOut: {es: 'El último sale a los', pt: 'O último sai aos', fr: 'Le dernier sort à', de: 'Der Letzte ist draußen nach', en: 'The last one out at'},
  calm: {es: 'Con calma', pt: 'Com calma', fr: 'Dans le calme', de: 'Ruhig', en: 'Calm'},
  hurry: {es: 'Con prisa', pt: 'Com pressa', fr: 'Dans la précipitation', de: 'In Eile', en: 'In a hurry'},
  crushed: {es: 'Aplastados ahora', pt: 'Esmagados agora', fr: 'Écrasés maintenant', de: 'Gerade eingeklemmt', en: 'Crushed now'},
  sameWay: {es: 'Rodeados de los que van en su dirección', pt: 'Rodeados dos que vão na mesma direção', fr: 'Entourés de ceux qui vont dans leur sens', de: 'Umgeben von Leuten in ihrer Richtung', en: 'Surrounded by people going their way'},
  crowdNote: {es: 'Simulación con el modelo de fuerzas sociales (Helbing, 2000) · {n} personas · cada una solo quiere llegar a su sitio', pt: 'Simulação com o modelo de forças sociais (Helbing, 2000) · {n} pessoas · cada uma só quer chegar ao seu destino', fr: 'Simulation avec le modèle des forces sociales (Helbing, 2000) · {n} personnes · chacune veut juste arriver', de: 'Simulation mit dem Social-Force-Modell (Helbing, 2000) · {n} Menschen · jede will nur ans Ziel', en: 'Simulation with the social force model (Helbing, 2000) · {n} people · each one only wants to get there'},
});

const N = 150;
const DOOR = 1.0;
const CALM = 1.0;
const HURRY = 5;
const CRUSH = 2500;                               // N: a body pressed harder than this is drawn as crushed

const run = (pillar: boolean, v0: number): Crowd => {
  (ROOM as {door: number}).door = DOOR;
  return simulate(`room:${pillar}:${v0}`, room(pillar), roomPeople(N, v0), 200);
};
const lane = (): Crowd => simulate('corridor', corridor(), corridorPeople(N), 160);

const SHIRT = ['#c9ced6', '#b5bcc6', '#d9dde3', '#a9b1bc'];
const HAIR = ['#2b2118', '#4a3426', '#1d1d1f', '#8a6a46', '#c9b28a'];

/** One person from above: shoulders, head; pressed bodies go red (the harder, the redder). */
const Person: FC<{x: number; y: number; s: number; i: number; push: number; tint?: string}> = ({x, y, s, i, push, tint}) => {
  const crush = Math.min(1, push / CRUSH);
  return (
    <g transform={`translate(${x} ${y})`}>
      {crush > 0.3 && <circle r={s * 0.5} fill={C.red} opacity={0.25 * crush} />}
      <ellipse rx={s * 0.27} ry={s * 0.19} fill={tint ?? SHIRT[i % SHIRT.length]} stroke={crush > 0.3 ? C.red : 'rgba(0,0,0,0.35)'}
               strokeWidth={crush > 0.3 ? 2.5 : 1.2} />
      <circle r={s * 0.12} fill={HAIR[i % HAIR.length]} />
    </g>
  );
};

/** A room and its door, drawn in the band [left, left + width): floor, walls, the exit sign, the people. */
const Room: FC<{c: Crowd; t: number; left: number; width: number; pillar: boolean}> = ({c, t, left, width, pillar}) => {
  const w = ROOM.w + 3;
  const s = Math.min((width - 80) / w, 880 / ROOM.h);
  const ox = left + (width - w * s) / 2;
  const oy = 540 - (ROOM.h * s) / 2;
  const X = (m: number) => ox + m * s;
  const Y = (m: number) => oy + m * s;
  const f = c.at(t);
  const top = ROOM.h / 2 - DOOR / 2;
  const bottom = ROOM.h / 2 + DOOR / 2;
  const tiles = [];
  for (let gx = 0; gx < ROOM.w; gx += 1.5) tiles.push(<line key={`x${gx}`} x1={X(gx)} x2={X(gx)} y1={Y(0)} y2={Y(ROOM.h)} stroke="rgba(0,0,0,0.08)" />);
  for (let gy = 0; gy < ROOM.h; gy += 1.5) tiles.push(<line key={`y${gy}`} x1={X(0)} x2={X(ROOM.w)} y1={Y(gy)} y2={Y(gy)} stroke="rgba(0,0,0,0.08)" />);
  return (
    <svg width={1920} height={1080} style={{position: 'absolute', clipPath: `inset(0 ${1920 - left - width}px 0 ${left}px)`}}>
      <rect x={left} y={0} width={width} height={1080} fill="#3d4450" />
      <rect x={X(ROOM.w)} y={Y(top) - s} width={3 * s} height={(DOOR + 2) * s} fill="#58606c" />
      <rect x={X(0)} y={Y(0)} width={ROOM.w * s} height={ROOM.h * s} fill="#b9b2a4" />
      {tiles}
      {/* walls: thick, with the door gap */}
      {[[0, 0, ROOM.w, 0], [0, ROOM.h, ROOM.w, ROOM.h], [0, 0, 0, ROOM.h], [ROOM.w, 0, ROOM.w, top], [ROOM.w, bottom, ROOM.w, ROOM.h]].map(([a, b, cc, d], k) => (
        <line key={k} x1={X(a)} y1={Y(b)} x2={X(cc)} y2={Y(d)} stroke="#2a2f37" strokeWidth={s * 0.35} strokeLinecap="square" />
      ))}
      <rect x={X(ROOM.w) - s * 0.9} y={Y(top) - s * 1.3} width={s * 1.8} height={s * 0.7} rx={4} fill="#1f9d55" />
      <text x={X(ROOM.w)} y={Y(top) - s * 0.8} textAnchor="middle" fill="#fff" fontFamily='"Barlow Condensed", sans-serif' fontSize={Math.max(14, s * 0.42)} fontWeight={800}>
        {tx('exitSign').toUpperCase()} →
      </text>
      {pillar && <circle cx={X(ROOM.w - 1.1)} cy={Y(ROOM.h / 2)} r={0.35 * s} fill="#6b7280" stroke="#2a2f37" strokeWidth={3} />}
      {Array.from(f.x).map((x, i) => (f.out[i] || x > ROOM.w + 2.5 ? null : <Person key={i} x={X(x)} y={Y(f.y[i])} s={s} i={i} push={f.push[i]} />))}
    </svg>
  );
};

const lastOut = (c: Crowd) => Math.max(...c.outAt.filter(Number.isFinite));
const crushedNow = (c: Crowd, t: number) => Array.from(c.at(t).push).filter((p, i) => !c.at(t).out[i] && p > CRUSH).length;

const View: FC<WorldProps> = ({g, worldT, local, real = local, o, on}) => {
  const scene = param<string>(g, 'scene', 'evacuacion');
  const panel = Math.max(o('panel'), on * 0.9);
  const marks: Record<string, Anchor | null> = {};
  let body: ReactElement;
  if (scene === 'columna' || scene === 'prisa') {
    const pillarScene = scene === 'columna';
    const a = pillarScene ? run(false, HURRY) : run(false, CALM);
    const b = pillarScene ? run(true, HURRY) : run(false, HURRY);
    const t = worldT * 3;
    body = (
      <>
        <Room c={a} t={t} left={0} width={958} pillar={false} />
        <Room c={b} t={t} left={962} width={958} pillar={pillarScene} />
        <div style={{position: 'absolute', left: 958, top: 0, width: 4, height: 1080, background: C.night}} />
        <SideTitle text={tx(pillarScene ? 'noColumn' : 'calm')} style={{left: 48, top: 44}} />
        <SideTitle text={tx(pillarScene ? 'withColumn' : 'hurry')} style={{left: 1010, top: 44}} />
        {pillarScene ? (
          <>
            <Big o={panel} label={tx('lastOut')} value={`${Math.round(lastOut(a))} s`} color={C.red} style={{left: 48, bottom: 60, width: 330}} />
            <Big o={panel} label={tx('lastOut')} value={`${Math.round(lastOut(b))} s`} color={C.green} style={{left: 1010, bottom: 60, width: 330}} />
          </>
        ) : (
          <>
            <Big o={panel} label={tx('crushed')} value={String(crushedNow(a, t))} color={C.green} sub={`${tx('outside')}: ${outBy(a, t)}`}
                 style={{left: 48, bottom: 60, width: 300}} />
            <Big o={panel} label={tx('crushed')} value={String(crushedNow(b, t))} color={crushedNow(b, t) ? C.red : C.text} sub={`${tx('outside')}: ${outBy(b, t)}`}
                 style={{left: 1010, bottom: 60, width: 300}} />
          </>
        )}
      </>
    );
  } else if (scene === 'pasillo') {
    const c = lane();
    const t = Math.min(159, worldT * 9);
    const f = c.at(t);
    const s = 1920 / CORRIDOR.w;
    const y0 = 540 - (CORRIDOR.h * s) / 2;
    let same = 0;
    let all = 0;
    for (let i = 0; i < c.n; i++) for (let j = 0; j < c.n; j++) {
      if (i === j) continue;
      const dx = Math.abs(f.x[i] - f.x[j]);
      if (Math.hypot(Math.min(dx, CORRIDOR.w - dx), f.y[i] - f.y[j]) < 1.2) {
        all++;
        if (c.group[i] === c.group[j]) same++;
      }
    }
    body = (
      <>
        <svg width={1920} height={1080} style={{position: 'absolute'}}>
          <rect width={1920} height={1080} fill="#3d4450" />
          <rect x={0} y={y0} width={1920} height={CORRIDOR.h * s} fill="#b9b2a4" />
          {Array.from({length: 27}, (_, k) => <line key={k} x1={k * 72} x2={k * 72} y1={y0} y2={y0 + CORRIDOR.h * s} stroke="rgba(0,0,0,0.08)" />)}
          <line x1={0} x2={1920} y1={y0} y2={y0} stroke="#2a2f37" strokeWidth={14} />
          <line x1={0} x2={1920} y1={y0 + CORRIDOR.h * s} y2={y0 + CORRIDOR.h * s} stroke="#2a2f37" strokeWidth={14} />
          {Array.from(f.x).map((x, i) => (
            <Person key={i} x={x * s} y={y0 + f.y[i] * s} s={s} i={i} push={0} tint={c.group[i] ? '#8fc1ff' : '#eef1f5'} />
          ))}
          <text x={60} y={y0 - 40} fill="#eef1f5" fontFamily='"Barlow Condensed", sans-serif' fontSize={34} fontWeight={800}>→ →</text>
          <text x={1860} y={y0 + CORRIDOR.h * s + 64} textAnchor="end" fill="#8fc1ff" fontFamily='"Barlow Condensed", sans-serif' fontSize={34} fontWeight={800}>← ←</text>
        </svg>
        <Panel o={panel} style={{left: '50%', bottom: 90, transform: 'translateX(-50%)', textAlign: 'center', width: 640}}>
          <Label>{tx('sameWay')}</Label>
          <div style={{fontSize: 62, fontWeight: 800, color: same / Math.max(1, all) > 0.75 ? C.green : C.text}}>{Math.round((same / Math.max(1, all)) * 100)} %</div>
        </Panel>
      </>
    );
  } else {
    const c = run(false, CALM);
    const t = worldT * 3;
    const w = ROOM.w + 3;
    const s = Math.min((1920 - 80) / w, 880 / ROOM.h);
    const ox = (1920 - w * s) / 2;
    marks.door = {x: ox + ROOM.w * s, y: 540};
    body = (
      <>
        <Room c={c} t={t} left={0} width={1920} pillar={false} />
        <Panel o={panel} style={{right: 64, top: 52, width: 300}}>
          <Label>{tx('outside')}</Label>
          <div style={{fontSize: 56, fontWeight: 800, fontVariantNumeric: 'tabular-nums'}}>{outBy(c, t)} <span style={{fontSize: 26, color: C.label}}>/ {N}</span></div>
          <Label>{Math.round(t)} s</Label>
        </Panel>
      </>
    );
  }
  return (
    <AbsoluteFill style={{background: C.night}}>
      {body}
      <Pointers marks={g.marks} local={real} at={marks} />
      <Note>{tx('crowdNote', {n: N})}</Note>
    </AbsoluteFill>
  );
};

export const multitud: World = {View};
