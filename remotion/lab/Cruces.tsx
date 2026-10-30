// Narrated scene: lights against a roundabout with the same cars, split screen. The simulation runs on its own; the
// voice decides the picture — each line of the script brings its focus (both sides, left or right) and its overlay
// (labels, demand, queue, yield, results, conflict points), cut on the line's own start and end.
import type {CSSProperties, FC} from 'react';
import {AbsoluteFill, Audio, Easing, interpolate, staticFile, useCurrentFrame} from 'remotion';
import '../theme';
import {BODY, Car, City, toScreen, type Cam} from './city';
import {C, FONT, Label, Panel} from './hud';
import {APPROACH, DEMAND, LANE, RING_R, STOP, sample, sim, type Snapshot} from './junction';

export type Line = {text: string; start: number; end: number; focus: 'both' | 'left' | 'right'; overlay: string};
export type CrucesProps = {audio: string; duration: number; scenes: Line[]};

export const FPS = 30;
const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;

const current = (scenes: Line[], t: number) => {
  let k = 0;
  for (let i = 0; i < scenes.length; i++) if (t >= scenes[i].start - 0.2) k = i;
  return k;
};

// where the divider stands and how close each camera is, for a focus
const LAYOUT = {both: {split: 960, left: 13, right: 13}, left: {split: 1340, left: 19, right: 9}, right: {split: 580, left: 9, right: 19}};

const layout = (scenes: Line[], t: number) => {
  const k = current(scenes, t);
  const now = LAYOUT[scenes[k].focus];
  const before = LAYOUT[k ? scenes[k - 1].focus : scenes[k].focus];
  const p = interpolate(t, [scenes[k].start - 0.2, scenes[k].start + 0.6], [0, 1], {...clamp, easing: Easing.inOut(Easing.cubic)});
  const mix = (a: number, b: number) => a + (b - a) * p;
  return {split: mix(before.split, now.split), left: mix(before.left, now.left), right: mix(before.right, now.right)};
};

// --- the two junctions --------------------------------------------------------------------------------------------
const Zebra: FC<{cam: Cam; arm: 'W' | 'E' | 'N' | 'S'; at: number}> = ({cam, arm, at}) => {
  const stripes = [];
  const horizontal = arm === 'W' || arm === 'E';
  const sign = arm === 'W' || arm === 'N' ? -1 : 1;
  for (let k = -4; k <= 4; k++) {
    const along = sign * at;
    const across = k * 1.0;
    const {sx, sy} = toScreen(cam, horizontal ? along : across, horizontal ? across : along);
    const w = (horizontal ? 2.6 : 0.55) * cam.s;
    const h = (horizontal ? 0.55 : 2.6) * cam.s;
    stripes.push(<rect key={k} x={sx - w / 2} y={sy - h / 2} width={w} height={h} fill="rgba(240,240,240,0.85)" />);
  }
  return <g>{stripes}</g>;
};

const SignalHead: FC<{cam: Cam; x: number; y: number; state: 'green' | 'amber' | 'red'}> = ({cam, x, y, state}) => {
  const {sx, sy} = toScreen(cam, x, y);
  const r = Math.max(2.5, cam.s * 0.45);
  const colour = {green: '#3ddc84', amber: '#f5b324', red: '#ff4b4b'}[state];
  return (
    <g>
      <circle cx={sx} cy={sy} r={r * 4} fill={colour} opacity={0.22} />
      <rect x={sx - r * 1.4} y={sy - r * 1.4} width={r * 2.8} height={r * 2.8} rx={r * 0.5} fill="#12161f" />
      <circle cx={sx} cy={sy} r={r} fill={colour} />
    </g>
  );
};

const LightsJunction: FC<{cam: Cam; snap: Snapshot}> = ({cam, snap}) => {
  const state = (axis: 'EW' | 'NS') => (snap.green === axis ? (snap.amber ? 'amber' : 'green') : 'red') as 'green' | 'amber' | 'red';
  // the stop line across the inbound half of each arm (right-hand traffic)
  const stop = (arm: 'W' | 'E' | 'N' | 'S') => {
    const [ox, oy] = {W: [-1, 0], E: [1, 0], N: [0, -1], S: [0, 1]}[arm];
    const a = toScreen(cam, ox * STOP, oy * STOP);
    const b = toScreen(cam, ox * STOP + 2 * oy * LANE, oy * STOP - 2 * ox * LANE);
    return <line key={arm} x1={a.sx} y1={a.sy} x2={b.sx} y2={b.sy} stroke="#f2f2f2" strokeWidth={Math.max(1.5, cam.s * 0.4)} />;
  };
  return (
    <g>
      {(['W', 'E', 'N', 'S'] as const).map((arm) => <Zebra key={arm} cam={cam} arm={arm} at={9.5} />)}
      {(['W', 'E', 'N', 'S'] as const).map(stop)}
      <SignalHead cam={cam} x={-6.5} y={6.5} state={state('EW')} />
      <SignalHead cam={cam} x={6.5} y={-6.5} state={state('EW')} />
      <SignalHead cam={cam} x={-6.5} y={-6.5} state={state('NS')} />
      <SignalHead cam={cam} x={6.5} y={6.5} state={state('NS')} />
    </g>
  );
};

const RoundaboutJunction: FC<{cam: Cam}> = ({cam}) => {
  const c = toScreen(cam, 0, 0);
  const splitters = (['W', 'E', 'N', 'S'] as const).map((arm) => {
    const horizontal = arm === 'W' || arm === 'E';
    const sign = arm === 'W' || arm === 'N' ? -1 : 1;
    const a = toScreen(cam, horizontal ? sign * 17 : -0.6, horizontal ? -0.6 : sign * 17);
    const w = (horizontal ? 9 : 1.2) * cam.s;
    const h = (horizontal ? 1.2 : 9) * cam.s;
    return <rect key={arm} x={horizontal && sign < 0 ? a.sx - w : a.sx} y={!horizontal && sign < 0 ? a.sy - h : a.sy} width={w} height={h}
                 rx={0.6 * cam.s} fill="#5f8a4f" stroke="#cfcfcf" strokeWidth={Math.max(1, cam.s * 0.12)} />;
  });
  return (
    <g>
      <circle cx={c.sx} cy={c.sy} r={(RING_R + 3.6) * cam.s} fill="#33363c" />
      <circle cx={c.sx} cy={c.sy} r={(RING_R + 3.4) * cam.s} fill="none" stroke="rgba(255,255,255,0.7)" strokeWidth={Math.max(1, cam.s * 0.12)} />
      <circle cx={c.sx} cy={c.sy} r={(RING_R - 3.4) * cam.s} fill="#62656b" />
      <circle cx={c.sx} cy={c.sy} r={(RING_R - 4.2) * cam.s} fill="#4a6e3f" />
      {[0, 1, 2, 3, 4, 5].map((k) => {
        const p = toScreen(cam, Math.cos(k) * 4.2, Math.sin(k * 1.7) * 4.2);
        return <circle key={k} cx={p.sx} cy={p.sy} r={2.1 * cam.s} fill={k % 2 ? '#2f5a2c' : '#3f7337'} />;
      })}
      {splitters}
    </g>
  );
};

const Cars: FC<{cam: Cam; snap: Snapshot; mark?: (car: Snapshot['cars'][number]) => string | undefined}> = ({cam, snap, mark}) => (
  <g>
    {snap.cars.map((car) => {
      const {sx, sy} = toScreen(cam, car.x, car.y);
      const brake = car.waiting ? 1 : Math.min(1, Math.max(0, -car.a - 0.4) / 1.2);
      return <Car key={car.id} sx={sx} sy={sy} deg={(car.h * 180) / Math.PI} s={cam.s} color={BODY[car.id % BODY.length]} brake={brake} mark={mark?.(car)} />;
    })}
  </g>
);

// the standard count of conflict points: 32 at a four-way crossing (16 crossing, 8 merging, 8 diverging), 8 at a
// single-lane roundabout (4 merging, 4 diverging)
const CROSS = '#ff5d5d';
const MERGE = '#f5a623';
const DIVERGE = '#5b8def';
const conflictPoints = (kind: 'lights' | 'roundabout'): [number, number, string][] => {
  const pts: [number, number, string][] = [];
  if (kind === 'lights') {
    for (const x of [-3.3, -1.1, 1.1, 3.3]) for (const y of [-3.3, -1.1, 1.1, 3.3]) pts.push([x, y, CROSS]);
    for (const [ox, oy] of [[-1, 0], [1, 0], [0, -1], [0, 1]]) {
      const ix = ox * 6.2 + oy * LANE;
      const iy = oy * 6.2 - ox * LANE;
      const ex = ox * 6.2 - oy * LANE;
      const ey = oy * 6.2 + ox * LANE;
      pts.push([ix + oy * 0.9, iy - ox * 0.9, DIVERGE], [ix - oy * 0.9, iy + ox * 0.9, DIVERGE]);
      pts.push([ex + oy * 0.9, ey - ox * 0.9, MERGE], [ex - oy * 0.9, ey + ox * 0.9, MERGE]);
    }
  } else {
    const delta = Math.asin(LANE / RING_R);
    for (const th of [Math.PI, Math.PI / 2, 0, -Math.PI / 2]) {
      pts.push([Math.cos(th - delta) * RING_R, Math.sin(th - delta) * RING_R, MERGE]);
      pts.push([Math.cos(th + delta) * RING_R, Math.sin(th + delta) * RING_R, DIVERGE]);
    }
  }
  return pts;
};

const Conflicts: FC<{cam: Cam; kind: 'lights' | 'roundabout'; o: number; reveal: number}> = ({cam, kind, o, reveal}) => {
  const pts = conflictPoints(kind);
  const shown = Math.floor(Math.max(0, Math.min(1, reveal)) * pts.length);
  return (
    <g opacity={o}>
      {pts.slice(0, shown).map(([x, y, colour], i) => {
        const {sx, sy} = toScreen(cam, x, y);
        return (
          <g key={i}>
            <circle cx={sx} cy={sy} r={cam.s * 1.4} fill={colour} opacity={0.25} />
            <circle cx={sx} cy={sy} r={Math.max(3, cam.s * 0.55)} fill={colour} stroke="#0b1020" strokeWidth={1.5} />
          </g>
        );
      })}
    </g>
  );
};

// --- one side of the split ------------------------------------------------------------------------------------------
const Side: FC<{kind: 'lights' | 'roundabout'; left: number; width: number; scale: number; simT: number; dim: boolean;
                o: (name: string) => number; reveal: number}> = ({kind, left, width, scale, simT, dim, o, reveal}) => {
  const centre = left + width / 2;
  const cam: Cam = {x: (960 - centre) / scale, y: 0, s: scale};
  const snap = sample(sim(kind), simT);
  const mark = (car: Snapshot['cars'][number]) => {
    if (kind === 'lights' && car.waiting && o('queue') > 0.5) return C.red;
    if (kind === 'roundabout' && car.waiting && o('yield') > 0.5) return C.accent;
    return undefined;
  };
  return (
    <div style={{position: 'absolute', inset: 0, clipPath: `inset(0 ${1920 - left - width}px 0 ${left}px)`}}>
      <City cam={cam} clearing={kind === 'roundabout' ? 21 : 0} ring={kind === 'roundabout' ? [RING_R - 5, RING_R + 4] : [0, 0]} disc={false} />
      <svg width={1920} height={1080} style={{position: 'absolute'}}>
        {kind === 'lights' ? <LightsJunction cam={cam} snap={snap} /> : <RoundaboutJunction cam={cam} />}
        <Cars cam={cam} snap={snap} mark={mark} />
        <Conflicts cam={cam} kind={kind} o={o('conflicts')} reveal={reveal} />
      </svg>
      <AbsoluteFill style={{background: '#050814', opacity: dim ? 0.45 : 0}} />
    </div>
  );
};

// --- panels -----------------------------------------------------------------------------------------------------------
const stats = (run: Snapshot[], t: number) => {
  const a = sample(run, 0);
  const b = sample(run, t);
  const passed = b.finished - a.finished;
  return {passed, wait: passed ? (b.waited - a.waited) / passed : 0, waiting: b.cars.filter((c) => c.waiting).length};
};

const Big: FC<{label: string; value: string; color?: string; style?: CSSProperties; o: number}> = ({label, value, color = C.text, style, o}) => (
  <Panel o={o} style={{width: 260, ...style}}>
    <Label>{label}</Label>
    <div style={{fontSize: 56, fontWeight: 800, color, fontVariantNumeric: 'tabular-nums', lineHeight: 1.05}}>{value}</div>
  </Panel>
);

/** The split screen at one moment: where the divider stands, how close each camera is, which side is in focus, the
 * opacity of each overlay, how much of each set of conflict points shows (0-1). `simT`: the simulations' clock. */
export type CrucesState = {simT: number; split: number; left: number; right: number; focus: 'both' | 'left' | 'right';
                           o: (name: string) => number; revealLights: number; revealRound: number};

export const CrucesView: FC<CrucesState> = ({simT, split, left, right, focus, o, revealLights, revealRound}) => {
  const L = stats(sim('lights'), simT);
  const R = stats(sim('roundabout'), simT);
  const perMinute = Math.round(60 / (1 / DEMAND + 1.2));
  const green = sample(sim('lights'), simT).green;
  const titleStyle: CSSProperties = {position: 'absolute', top: 44, fontFamily: FONT, fontSize: 40, fontWeight: 800, color: C.text, textTransform: 'uppercase'};
  return (
    <AbsoluteFill style={{backgroundColor: C.night}}>
      <Side kind="lights" left={0} width={split} scale={left} simT={simT} dim={focus === 'right'} o={o} reveal={revealLights} />
      <Side kind="roundabout" left={split} width={1920 - split} scale={right} simT={simT} dim={focus === 'left'} o={o} reveal={revealRound} />
      <div style={{position: 'absolute', left: split - 2, top: 0, width: 4, height: 1080, background: C.night}} />
      <AbsoluteFill style={{background: 'radial-gradient(ellipse at center, rgba(0,0,0,0) 55%, rgba(5,8,18,0.55) 100%)', pointerEvents: 'none'}} />

      <div style={{...titleStyle, left: 48}}>Semáforos<div style={{height: 4, width: 120, background: C.accent, marginTop: 4}} /></div>
      <div style={{...titleStyle, left: split + 48}}>Rotonda<div style={{height: 4, width: 100, background: C.accent, marginTop: 4}} /></div>

      <Panel o={o('demand')} style={{left: '50%', bottom: 70, transform: 'translateX(-50%)', textAlign: 'center', width: 640}}>
        <Label>El mismo tráfico a los dos</Label>
        <div style={{fontSize: 38, fontWeight: 800, marginTop: 4}}>~{perMinute} COCHES POR MINUTO <span style={{color: C.label, fontSize: 26}}>EN CADA CALLE</span></div>
      </Panel>

      <Big o={o('queue')} label="Esperando ahora" value={String(L.waiting)} color={C.red} style={{left: 48, bottom: 70}} />
      <Panel o={o('queue')} style={{left: 340, bottom: 70}}>
        <Label>Verde para</Label>
        <div style={{fontSize: 34, fontWeight: 800, color: C.green}}>{green === 'EW' ? 'ESTE-OESTE' : green === 'NS' ? 'NORTE-SUR' : '—'}</div>
      </Panel>
      <Big o={o('yield')} label="Esperando ahora" value={String(R.waiting)} color={C.accent} style={{right: 48, bottom: 70}} />
      <Panel o={o('yield')} style={{right: 340, bottom: 70}}>
        <Label>La única regla</Label>
        <div style={{fontSize: 30, fontWeight: 800}}>CEDE AL QUE YA ESTÁ DENTRO</div>
      </Panel>

      <Big o={o('results')} label="Espera media por coche" value={`${L.wait.toFixed(1)} s`} color={C.red} style={{left: 48, bottom: 70, width: 300}} />
      <Big o={o('results')} label="Espera media por coche" value={`${R.wait.toFixed(1)} s`} color={C.green} style={{left: split + 48, bottom: 70, width: 300}} />
      <Big o={o('results')} label="Han pasado" value={String(L.passed)} style={{left: 380, bottom: 70, width: 200}} />
      <Big o={o('results')} label="Han pasado" value={String(R.passed)} style={{left: split + 380, bottom: 70, width: 200}} />

      <Big o={o('conflicts') * Math.min(1, revealLights * 4)} label="Puntos de choque" value="32" color={CROSS} style={{left: 48, bottom: 70, width: 220}} />
      <Big o={o('conflicts') * Math.min(1, revealRound * 4)} label="Puntos de choque" value="8" color={C.green} style={{left: split + 48, bottom: 70, width: 220}} />
      <Panel o={o('conflicts')} style={{left: '50%', top: 130, transform: 'translateX(-50%)', display: 'flex', gap: 22, padding: '10px 18px'}}>
        {[[CROSS, 'Cruce'], [MERGE, 'Incorporación'], [DIVERGE, 'Salida']].map(([colour, name]) => (
          <span key={name} style={{display: 'flex', alignItems: 'center', gap: 8, fontSize: 18, fontWeight: 700, letterSpacing: 1}}>
            <span style={{width: 12, height: 12, borderRadius: 6, background: colour}} />{name.toUpperCase()}
          </span>
        ))}
      </Panel>

      <div style={{position: 'absolute', left: 48, bottom: 24, fontFamily: FONT, fontSize: 14, letterSpacing: 1.2, color: 'rgba(255,255,255,0.5)'}}>
        SIMULACIÓN · MISMAS LLEGADAS EN LOS DOS CRUCES · {APPROACH} M DE ACCESO POR CALLE
      </div>
    </AbsoluteFill>
  );
};

export const LAYOUTS = LAYOUT;

// the lab's narrated test: one line of escenas.json at a time
export const Cruces: FC<CrucesProps> = ({audio, scenes}) => {
  const f = useCurrentFrame();
  const t = f / FPS;
  const line = scenes[current(scenes, t)];
  const {split, left, right} = layout(scenes, t);
  // an overlay is on during its own line, fading in and out
  const o = (name: string) => {
    const s = scenes.find((x) => x.overlay === name);
    if (!s) return 0;
    const end = name === 'results' || name === 'conflicts' ? (scenes[scenes.indexOf(s) + 1]?.start ?? s.end + 3) - 0.1 : s.end + 0.3;
    return interpolate(t, [s.start - 0.1, s.start + 0.35, end - 0.3, end], [0, 1, 1, 0], clamp);
  };
  const c = scenes.find((x) => x.overlay === 'conflicts');
  return (
    <AbsoluteFill>
      <Audio src={staticFile(audio)} />
      <CrucesView simT={t} split={split} left={left} right={right} focus={line.focus} o={o}
                  revealLights={c ? interpolate(t, [c.start + 0.3, c.start + 3.2], [0, 1], clamp) : 0}
                  revealRound={c ? interpolate(t, [c.start + 4.2, c.start + 5.4], [0, 1], clamp) : 0} />
    </AbsoluteFill>
  );
};
