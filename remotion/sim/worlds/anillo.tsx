// The phantom jam: cars on a 230 m ring (Sugiyama et al., 2008). Its clock is paced to the voice: the brake falls on
// the line that points at it (cues.brake), the first car stops on the line that speaks of the jam (cues.jam), and —
// with driver: suave — one car starts driving itself on the line that says so (cues.auto; Stern et al., 2018). With
// driver: calma nobody gets distracted (no noise, no brake) and the same ring flows. Overlay flow: the fundamental
// diagram (cars an hour against cars per kilometre), this ring's point on it.
import type {FC} from 'react';
import {AbsoluteFill, Easing, interpolate} from 'remotion';
import {Car, CITY, City, kindOf, toScreen, type Cam} from '../city';
import {C, FONT, Label, Panel} from '../hud';
import {addWords, tx} from '../i18n';
import {paint, Pointers, trail} from '../look';
import {flowCurve, PERTURB, RING, SAMPLE, ring, type Mode, type Ring} from '../traffic';
import {Note, param, type World, type WorldProps} from '../world';

addWords({
  selfDriving: {es: 'Conduce solo', pt: 'Conduz sozinho', fr: 'Conduite autonome', de: 'Fährt selbst', en: 'Drives itself'},
  flowChart: {es: 'Coches por hora según cuántos hay en la carretera', pt: 'Carros por hora conforme quantos há na estrada', fr: 'Voitures par heure selon leur nombre sur la route', de: 'Autos pro Stunde je nach Verkehrsdichte', en: 'Cars an hour by how many are on the road'},
  perKm: {es: 'coches por km', pt: 'carros por km', fr: 'voitures par km', de: 'Autos pro km', en: 'cars per km'},
  perHour: {es: 'coches/hora', pt: 'carros/hora', fr: 'voitures/heure', de: 'Autos/Stunde', en: 'cars/hour'},
  peak: {es: 'Máximo', pt: 'Máximo', fr: 'Maximum', de: 'Maximum', en: 'Peak'},
  breaks: {es: 'Se rompe', pt: 'Rompe-se', fr: 'Ça casse', de: 'Kippt', en: 'It breaks'},
  thisRing: {es: 'Este anillo', pt: 'Este anel', fr: 'Cet anneau', de: 'Dieser Ring', en: 'This ring'},
  modeSuave: {es: ' · un coche conduce solo', pt: ' · um carro conduz sozinho', fr: ' · une voiture autonome', de: ' · ein Auto fährt selbst', en: ' · one car drives itself'},
  carsN: {es: '{n} coches', pt: '{n} carros', fr: '{n} voitures', de: '{n} Autos', en: '{n} cars'},
  ringSpec: {es: '230 m de vuelta · a {v} km/h', pt: '230 m de volta · a {v} km/h', fr: '230 m de tour · à {v} km/h', de: '230 m Runde · {v} km/h', en: '230 m round · at {v} km/h'},
  noJamYet: {es: 'Aún sin atasco', pt: 'Ainda sem engarrafamento', fr: 'Pas encore de bouchon', de: 'Noch kein Stau', en: 'No jam yet'},
  oneStopped: {es: '1 parado', pt: '1 parado', fr: '1 à l’arrêt', de: '1 steht', en: '1 stopped'},
  nStopped: {es: '{n} parados', pt: '{n} parados', fr: '{n} à l’arrêt', de: '{n} stehen', en: '{n} stopped'},
  noWaves: {es: 'Sin ondas', pt: 'Sem ondas', fr: 'Plus de vagues', de: 'Keine Wellen', en: 'No waves'},
  tapFades: {es: 'El frenazo se apaga', pt: 'A travagem apaga-se', fr: 'Le coup de frein s’éteint', de: 'Das Bremsen verpufft', en: 'The tap fades'},
  tapGrows: {es: 'El mismo frenazo crece', pt: 'A mesma travagem cresce', fr: 'Le même coup de frein grandit', de: 'Dasselbe Bremsen wächst', en: 'The same tap grows'},
  modeCalma: {es: ' · sin despistes', pt: ' · sem distrações', fr: ' · sans distractions', de: ' · ohne Ablenkung', en: ' · no distractions'},
});

const LAPSE = 2.5;                       // with no cue the jam (a minute and a half to grow) is shown faster
const R = RING.length / (2 * Math.PI);
const angle = (x: number) => -Math.PI / 2 + (2 * Math.PI * x) / RING.length;
const camera = (focus: string): Cam => (focus === 'chart' ? {x: 50, y: 0, s: 9.2} : {x: 0, y: 0, s: 12.6});

const speedColour = (v: number, top: number) => {
  const k = Math.min(1, v / top);
  if (k < 0.5) return `rgb(255, ${Math.round(70 + k * 2 * 140)}, 70)`;
  return `rgb(${Math.round(255 - (k - 0.5) * 2 * 194)}, ${Math.round(210 + (k - 0.5) * 2 * 10)}, ${Math.round(70 + (k - 0.5) * 2 * 62)})`;
};

const SpaceTime: FC<{r: Ring; simT: number; o: number}> = ({r, simT, o}) => {
  if (o <= 0.01) return null;                     // 22 lines of up to 220 points: only when it is on screen
  const W = 760;
  const H = 470;
  const span = Math.max(20, Math.min(simT, r.frames.length * SAMPLE));
  // one line per car (position against time), coloured by its speed, broken where it goes round the ring; the car
  // that braked first in yellow
  const lines = [];
  const step = Math.max(0.5, span / 220);
  for (let i = 0; i < r.cars; i++) {
    let prev: [number, number] | null = null;
    for (let t = 0; t <= simT; t += step) {
      const fr = r.frames[Math.min(r.frames.length - 1, Math.round(t / SAMPLE))];     // the stored steps: no blending needed
      const p: [number, number] = [(t / span) * W, H - (fr.x[i] / RING.length) * H];
      if (prev && Math.abs(p[1] - prev[1]) < H / 2) {
        lines.push(<line key={`${i}-${t}`} x1={prev[0]} y1={prev[1]} x2={p[0]} y2={p[1]}
                         stroke={i === PERTURB.car ? C.you : speedColour(fr.v[i], r.startSpeed)} strokeWidth={i === PERTURB.car ? 3 : 1.6} />);
      }
      prev = p;
    }
  }
  return (
    <Panel o={o} style={{right: 64, top: 150, width: W + 44}}>
      <Label>{tx('ringChart')}</Label>
      <svg width={W} height={H} style={{marginTop: 12, display: 'block', background: 'rgba(255,255,255,0.03)'}}>{lines}</svg>
      <div style={{display: 'flex', justifyContent: 'space-between', marginTop: 8}}>
        <Label>{tx('time')} →</Label>
        <Label><span style={{color: '#ff5a46'}}>■</span> {tx('stopped')} <span style={{color: '#3ddc84', marginLeft: 12}}>■</span> {tx('normalSpeed')}</Label>
      </div>
    </Panel>
  );
};

const FlowChart: FC<{cars: number; o: number}> = ({cars, o}) => {
  const W = 760;
  const H = 430;
  const pts = flowCurve();
  const maxX = 140;
  const maxY = 2900;
  const X = (k: number) => (k / maxX) * W;
  const Y = (q: number) => H - (q / maxY) * H;
  const peak = pts.reduce((a, b) => (b.perHour > a.perHour ? b : a));
  const line = `${X(0)},${Y(0)} ` + pts.map((p) => `${X(p.perKm).toFixed(1)},${Y(p.perHour).toFixed(1)}`).join(' ');   // no cars, no flow
  const here = pts.find((p) => p.cars === cars) ?? peak;
  // the curve drawn from the left as the panel comes in
  const shown = Math.max(0.02, Math.min(1, o * 1.3));
  return (
    <Panel o={o} style={{right: 64, top: 150, width: W + 44}}>
      <Label>{tx('flowChart')}</Label>
      <svg width={W} height={H + 30} style={{marginTop: 12, display: 'block', overflow: 'visible'}}>
        <defs><clipPath id="flowclip"><rect x={0} y={-20} width={W * shown} height={H + 60} /></clipPath></defs>
        <rect x={X(peak.perKm)} y={0} width={W - X(peak.perKm)} height={H} fill="rgba(255,93,93,0.08)" />
        {[0.25, 0.5, 0.75].map((f) => <line key={f} x1={0} x2={W} y1={H * f} y2={H * f} stroke="rgba(255,255,255,0.06)" />)}
        <line x1={0} x2={W} y1={H} y2={H} stroke="rgba(255,255,255,0.25)" />
        <g clipPath="url(#flowclip)">
          <polygon points={`${line} ${X(pts[pts.length - 1].perKm)},${H}`} fill={C.accent} opacity={0.12} />
          <polyline points={line} fill="none" stroke={C.accent} strokeWidth={4} strokeLinejoin="round" />
        </g>
        <line x1={X(peak.perKm)} x2={X(peak.perKm)} y1={0} y2={H} stroke="rgba(255,255,255,0.35)" strokeDasharray="6 6" />
        <text x={X(peak.perKm) - 10} y={Y(peak.perHour) - 16} textAnchor="end" fill={C.text} fontFamily={FONT} fontSize={24} fontWeight={800}>
          {tx('peak')} · {Math.round(peak.perHour / 100) * 100} {tx('perHour')}
        </text>
        <text x={W - 10} y={30} textAnchor="end" fill={C.red} fontFamily={FONT} fontSize={24} fontWeight={800}>{tx('breaks').toUpperCase()} →</text>
        <circle cx={X(here.perKm)} cy={Y(here.perHour)} r={10} fill={C.accent} stroke="#0b1020" strokeWidth={3} opacity={o > 0.6 ? 1 : 0} />
        <text x={X(here.perKm) + 16} y={Y(here.perHour) - 12} fill={C.accent} fontFamily={FONT} fontSize={22} fontWeight={800} opacity={o > 0.6 ? 1 : 0}>
          {tx('thisRing')}: {cars}
        </text>
        <text x={0} y={H + 26} fill={C.label} fontFamily={FONT} fontSize={20} letterSpacing={1.2}>{tx('perKm').toUpperCase()} →</text>
      </svg>
    </Panel>
  );
};

const clockOf = (g: WorldProps['g'], r: Ring, t: number) => r.clock(t, g.since, g.cues, LAPSE);

const modeOf = (g: WorldProps['g']): Mode => {
  const m = String(param<string>(g, 'driver', 'normal'));
  return m === 'suave' || m === 'calma' ? m : 'normal';
};

// the stopped knot of the ring as angles (tail → front), or null
const knot = (fr: {x: Float32Array; v: Float32Array}) => {
  const L = RING.length;
  const xs = Array.from(fr.x).filter((_, i) => fr.v[i] < 0.6).sort((a, b) => a - b);
  if (xs.length < 2) return null;
  const runs: number[][] = [];
  for (const x of xs) {
    const last = runs[runs.length - 1];
    if (last && x - last[last.length - 1] < 14) last.push(x);
    else runs.push([x]);
  }
  if (runs.length > 1 && xs[0] + L - xs[xs.length - 1] < 14) runs[0] = [...runs.pop()!.map((x) => x - L), ...runs[0]];
  const big = runs.reduce((a, b) => (b.length > a.length ? b : a));
  return big.length >= 2 ? {tail: angle(big[0] - 3), front: angle(big[big.length - 1] + 3)} : null;
};

type RingProps = {r: Ring; simT: number; cx: number; cy: number; s: number; show: (n: string) => number; centre: number; arc: number};
/** The 230 m road with its cars; in the middle what it is and how it is going; a red arc over the stopped knot with an
 * arrow pointing back the way the jam travels. */
const RingRoad: FC<RingProps> = ({r, simT, cx, cy, s, show, centre, arc}) => {
  const fr = r.at(simT);
  const driving = r.mode === 'suave' && simT >= r.smoothAt;
  const autoCar = Math.floor(r.cars / 2);
  const now = r.stopped(simT);
  const k = knot(fr);
  const ra = (R + 9) * s;
  const pt = (th: number, rr = ra) => `${cx + Math.cos(th) * rr},${cy + Math.sin(th) * rr}`;
  const status = now === 1 ? tx('oneStopped') : now ? tx('nStopped', {n: now}) : driving ? tx('noWaves') : tx('noJamYet');
  return (
    <g>
      <circle cx={cx} cy={cy} r={(R + 5.5) * s} fill={CITY.sidewalk} />
      <circle cx={cx} cy={cy} r={(R + 3.6) * s} fill={CITY.road} />
      <circle cx={cx} cy={cy} r={(R - 3.6) * s} fill={CITY.grass} />
      {[R + 3.2, R - 3.2].map((rr) => <circle key={rr} cx={cx} cy={cy} r={rr * s} fill="none" stroke="rgba(255,255,255,0.75)" strokeWidth={Math.max(1, s * 0.12)} />)}
      {centre > 0 && (
        <g opacity={centre}>
          <circle cx={cx} cy={cy} r={(R - 6) * s} fill="rgba(8,12,22,0.55)" />
          <text x={cx} y={cy - 6} textAnchor="middle" fill={C.text} fontFamily={FONT} fontSize={Math.max(30, s * 6.4)} fontWeight={800}>
            {tx('carsN', {n: r.cars}).toUpperCase()}
          </text>
          <text x={cx} y={cy + s * 3.6} textAnchor="middle" fill={C.label} fontFamily={FONT} fontSize={Math.max(15, s * 2)} fontWeight={700} letterSpacing={1.2}>
            {tx('ringSpec', {v: Math.round(r.startSpeed * 3.6)}).toUpperCase()}
          </text>
          <text x={cx} y={cy + s * 7.4} textAnchor="middle" fill={now ? C.red : driving ? C.green : C.text} fontFamily={FONT}
                fontSize={Math.max(17, s * 2.4)} fontWeight={800} letterSpacing={1.2}>{status.toUpperCase()}</text>
        </g>
      )}
      {k && arc > 0 && (() => {
        let a = k.tail;
        let b = k.front;
        if (b < a) b += 2 * Math.PI;
        const big = b - a > Math.PI ? 1 : 0;
        const back = a - 0.22;                                         // the arrow: the jam goes backwards
        return (
          <g opacity={arc}>
            <path d={`M${pt(a)} A${ra},${ra} 0 ${big} 1 ${pt(b)}`} fill="none" stroke={C.red} strokeWidth={Math.max(4, s * 0.7)} strokeLinecap="round" />
            <path d={`M${pt(a)} A${ra},${ra} 0 0 0 ${pt(back)}`} fill="none" stroke={C.red} strokeWidth={Math.max(3, s * 0.45)} />
            <path d={`M${pt(back, ra - s * 1.6)} L${pt(back - 0.06)} L${pt(back, ra + s * 1.6)} Z`} fill={C.red} />
          </g>
        );
      })()}
      {Array.from(fr.x).map((x, i) => {
        const th = angle(x);
        const braking = Math.min(1, Math.max(0, -fr.a[i] - 0.15) / 0.6) || (fr.v[i] < 0.6 ? 1 : 0);
        const brakeMark = i === PERTURB.car && show('brake') > 0.5 && simT >= PERTURB.from - 2 && simT <= PERTURB.to + 6;
        const mark = driving && i === autoCar ? C.you : brakeMark ? C.you
          : fr.v[i] < 0.6 && simT > r.firstStop && show('jam') > 0.5 ? C.red : undefined;
        return <Car key={i} sx={cx + Math.cos(th) * R * s} sy={cy + Math.sin(th) * R * s} deg={(th * 180) / Math.PI + 90}
                    s={s} color={paint(fr.v[i], r.startSpeed)} brake={braking} mark={mark} trail={0.8 * trail(fr.v[i], r.startSpeed)} kind={kindOf(i)} />;
      })}
      {driving && (() => {
        const th = angle(fr.x[autoCar]);
        const px = cx + Math.cos(th) * (R + 13) * s;
        const py = cy + Math.sin(th) * (R + 13) * s;
        return (
          <g opacity={Math.max(0.75, show('auto'))}>
            <rect x={px - 92} y={py - 20} width={184} height={40} rx={6} fill={C.panel} stroke={C.you} strokeWidth={2} />
            <text x={px} y={py + 9} textAnchor="middle" fill={C.you} fontFamily={FONT} fontSize={24} fontWeight={800}>
              {tx('selfDriving').toUpperCase()}
            </text>
          </g>
        );
      })()}
    </g>
  );
};

/** Two rings side by side, 12 and 23 cars, the same tap at the same moment: on the emptier one it fades, on the
 * fuller one it grows into a jam (the tipping point). */
const Compare: FC<{g: WorldProps['g']; local: number; on: number; o: WorldProps['o']}> = ({g, local, on, o}) => {
  const sides = [ring(12, modeOf(g)), ring(23, modeOf(g))];
  const show = (n: string) => (n === 'jam' ? Math.max(o('jam'), on * 0.6) : o(n));
  return (
    <AbsoluteFill style={{background: 'radial-gradient(ellipse at center, #26352b 0%, #1d2a22 70%)'}}>
      <svg width={1920} height={1080} style={{position: 'absolute'}}>
        {sides.map((r, i) => {
          const t = clockOf(g, r, g.at + local);
          const cx = i ? 1400 : 520;
          return (
            <g key={i}>
              <RingRoad r={r} simT={t} cx={cx} cy={520} s={8} show={show} centre={1} arc={on} />
              <text x={cx} y={940} textAnchor="middle" fill={i ? C.red : C.green} fontFamily={FONT} fontSize={30} fontWeight={800} letterSpacing={1.4}
                    opacity={on}>{tx(i ? 'tapGrows' : 'tapFades').toUpperCase()}</text>
            </g>
          );
        })}
      </svg>
      <Note>{tx('ringNote', {n: '12 · 23'})}</Note>
    </AbsoluteFill>
  );
};

/** Where the camera goes to look at one car: towards it and closer, the ring still in sight. */
const closeUp = (r: Ring, simT: number, i: number): Cam => {
  const th = angle(r.at(simT).x[i]);
  return {x: Math.cos(th) * R * 0.62, y: Math.sin(th) * R * 0.62, s: 19};
};

const mixCam = (a: Cam, b: Cam, k: number): Cam => ({x: a.x + (b.x - a.x) * k, y: a.y + (b.y - a.y) * k, s: a.s + (b.s - a.s) * k});

const View: FC<WorldProps> = ({g, local, real = local, move, on, o}) => {
  if (g.focus === 'compare') return <Compare g={g} local={local} on={on} o={o} />;
  const r = ring(param(g, 'cars', 22), modeOf(g));
  const simT = clockOf(g, r, g.at + local);
  const a = camera(g.prev);
  const b = camera(g.overlay === 'flow' ? 'chart' : g.focus);        // the curve takes the right half
  let cam = mixCam(a, b, move);
  // the camera follows what the voice speaks of: in on the car that brakes (or the one that drives itself) while the
  // line is about it, back out from it on the next line, when the jam (or the calm) is the point
  const ease = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.inOut(Easing.cubic)} as const;
  const followed = g.overlay === 'auto' ? Math.floor(r.cars / 2) : PERTURB.car;
  if (g.focus === 'ring' && (g.overlay === 'brake' || g.overlay === 'auto')) {
    cam = mixCam(cam, closeUp(r, simT, followed), interpolate(real, [0.2, 1.6], [0, 1], ease));
  } else if (g.focus === 'ring' && (g.prevOverlay === 'brake' || g.prevOverlay === 'auto')) {
    cam = mixCam(closeUp(r, simT, g.prevOverlay === 'auto' ? Math.floor(r.cars / 2) : PERTURB.car), cam, interpolate(real, [0, 1.8], [0, 1], ease));
  }
  const show = (name: string) =>
    name === 'chart' && g.focus === 'chart' && g.overlay !== 'flow' ? on
      : name === 'speed' && g.overlay === 'auto' ? on : o(name);
  const c = toScreen(cam, 0, 0);
  const now = r.stopped(simT);
  const fr = r.at(simT);
  const onRing = (x: number, out = 0) => {
    const th = angle(x);
    return {x: c.sx + Math.cos(th) * (R + out) * cam.s, y: c.sy + Math.sin(th) * (R + out) * cam.s};
  };
  const k = knot(fr);
  const jamAt = k ? (() => {
    let mid = (k.tail + k.front) / 2;
    if (k.front < k.tail) mid += Math.PI;
    return {x: c.sx + Math.cos(mid) * R * cam.s, y: c.sy + Math.sin(mid) * R * cam.s};
  })() : null;
  return (
    <AbsoluteFill style={{backgroundColor: C.night}}>
      <City cam={cam} clearing={58} ring={[R - 4, R + 6]} />
      <svg width={1920} height={1080} style={{position: 'absolute'}}>
        <RingRoad r={r} simT={simT} cx={c.sx} cy={c.sy} s={cam.s} show={show} centre={g.focus === 'ring' ? 0.92 : 0} arc={g.focus === 'ring' ? 0.95 : 0} />
      </svg>
      <AbsoluteFill style={{background: 'radial-gradient(ellipse at center, rgba(0,0,0,0) 50%, rgba(5,8,18,0.6) 100%)'}} />
      <Pointers marks={g.marks} local={real} at={{car: onRing(fr.x[PERTURB.car]), auto: r.mode === 'suave' ? onRing(fr.x[Math.floor(r.cars / 2)]) : null, jam: jamAt}} />
      <Panel o={show('speed')} style={{right: 64, top: 52, width: 270}}>
        <Label>{tx('meanSpeed')}</Label>
        <div style={{fontSize: 58, fontWeight: 800, color: C.accent, fontVariantNumeric: 'tabular-nums'}}>
          {(r.meanSpeed(simT) * 3.6).toFixed(0)} <span style={{fontSize: 28}}>KM/H</span>
        </div>
      </Panel>
      <Panel o={show('jam')} style={{right: 64, bottom: 80, width: 270}}>
        <Label>{tx('stoppedNow')}</Label>
        <div style={{fontSize: 58, fontWeight: 800, color: now ? C.red : C.text, fontVariantNumeric: 'tabular-nums'}}>{now}</div>
        <Label>{tx('ofCars', {n: r.cars})}</Label>
      </Panel>
      <SpaceTime r={r} simT={simT} o={show('chart')} />
      <FlowChart cars={r.cars} o={o('flow')} />
      <Note>{tx('ringNote', {n: r.cars})}{r.mode === 'suave' ? tx('modeSuave') : r.mode === 'calma' ? tx('modeCalma') : ''}</Note>
    </AbsoluteFill>
  );
};

// a tick each time one more car stands still while the jam panel is on
const sounds = (g: WorldProps['g'], length: number) => {
  if (g.overlay !== 'jam') return {};
  const r = ring(param(g, 'cars', 22), modeOf(g));
  const ticks: number[] = [];
  let before = r.stopped(clockOf(g, r, g.at));
  for (let s = 0.1; s < length; s += 0.1) {
    const now = r.stopped(clockOf(g, r, g.at + s));
    if (now > before) ticks.push(s);
    before = now;
  }
  return {ticks};
};

export const anillo: World = {View, sounds};
