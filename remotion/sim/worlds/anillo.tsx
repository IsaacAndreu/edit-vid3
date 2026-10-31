// The phantom jam: cars on a 230 m ring (Sugiyama et al., 2008). Its clock is paced to the voice: the brake falls on
// the line that points at it (cues.brake), the first car stops on the line that speaks of the jam (cues.jam), and —
// with driver: suave — one car starts driving itself on the line that says so (cues.auto; Stern et al., 2018). With
// driver: calma nobody gets distracted (no noise, no brake) and the same ring flows. Overlay flow: the fundamental
// diagram (cars an hour against cars per kilometre), this ring's point on it.
import type {FC} from 'react';
import {AbsoluteFill} from 'remotion';
import {BODY, Car, City, toScreen, type Cam} from '../city';
import {C, FONT, Label, Panel} from '../hud';
import {addWords, tx} from '../i18n';
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
  modeCalma: {es: ' · sin despistes', pt: ' · sem distrações', fr: ' · sans distractions', de: ' · ohne Ablenkung', en: ' · no distractions'},
});

const LAPSE = 2.5;                       // with no cue the jam (a minute and a half to grow) is shown faster
const R = RING.length / (2 * Math.PI);
const angle = (x: number) => -Math.PI / 2 + (2 * Math.PI * x) / RING.length;
const camera = (focus: string): Cam => (focus === 'chart' ? {x: 50, y: 0, s: 8.5} : {x: 0, y: 0, s: 10.5});

const speedColour = (v: number, top: number) => {
  const k = Math.min(1, v / top);
  if (k < 0.5) return `rgb(255, ${Math.round(70 + k * 2 * 140)}, 70)`;
  return `rgb(${Math.round(255 - (k - 0.5) * 2 * 194)}, ${Math.round(210 + (k - 0.5) * 2 * 10)}, ${Math.round(70 + (k - 0.5) * 2 * 62)})`;
};

const SpaceTime: FC<{r: Ring; simT: number; o: number}> = ({r, simT, o}) => {
  const W = 760;
  const H = 470;
  const span = Math.max(20, Math.min(simT, r.frames.length * SAMPLE));
  const dots = [];
  for (let s = 0; s <= simT; s += Math.max(0.5, span / 220)) {
    const fr = r.at(s);
    for (let i = 0; i < r.cars; i++) {
      dots.push(<rect key={`${s}-${i}`} x={(s / span) * W} y={H - (fr.x[i] / RING.length) * H} width={W / 220 + 0.8} height={2.4}
                      fill={speedColour(fr.v[i], r.startSpeed)} />);
    }
  }
  return (
    <Panel o={o} style={{right: 64, top: 150, width: W + 44}}>
      <Label>{tx('ringChart')}</Label>
      <svg width={W} height={H} style={{marginTop: 12, display: 'block', background: 'rgba(255,255,255,0.03)'}}>{dots}</svg>
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
        <text x={0} y={H + 26} fill={C.label} fontFamily={FONT} fontSize={17} letterSpacing={1.2}>{tx('perKm').toUpperCase()} →</text>
      </svg>
    </Panel>
  );
};

const clockOf = (g: WorldProps['g'], r: Ring, t: number) => r.clock(t, g.since, g.cues, LAPSE);

const modeOf = (g: WorldProps['g']): Mode => {
  const m = String(param<string>(g, 'driver', 'normal'));
  return m === 'suave' || m === 'calma' ? m : 'normal';
};

const View: FC<WorldProps> = ({g, local, move, on, o}) => {
  const r = ring(param(g, 'cars', 22), modeOf(g));
  const simT = clockOf(g, r, g.at + local);
  const a = camera(g.prev);
  const b = camera(g.overlay === 'flow' ? 'chart' : g.focus);        // the curve takes the right half
  const cam = {x: a.x + (b.x - a.x) * move, y: 0, s: a.s + (b.s - a.s) * move};
  const show = (name: string) =>
    name === 'chart' && g.focus === 'chart' && g.overlay !== 'flow' ? on
      : (name === 'speed' || name === 'jam') && g.overlay === 'auto' ? on : o(name);
  const driving = r.mode === 'suave' && simT >= r.smoothAt;
  const autoCar = Math.floor(r.cars / 2);
  const fr = r.at(simT);
  const c = toScreen(cam, 0, 0);
  const now = r.stopped(simT);
  return (
    <AbsoluteFill style={{backgroundColor: C.night}}>
      <City cam={cam} clearing={58} ring={[R - 4, R + 6]} />
      <svg width={1920} height={1080} style={{position: 'absolute'}}>
        <circle cx={c.sx} cy={c.sy} r={(R + 5.5) * cam.s} fill="#62656b" />
        <circle cx={c.sx} cy={c.sy} r={(R + 3.6) * cam.s} fill="#33363c" />
        <circle cx={c.sx} cy={c.sy} r={(R - 3.6) * cam.s} fill="#4a6e3f" />
        {[R + 3.2, R - 3.2].map((rr) => <circle key={rr} cx={c.sx} cy={c.sy} r={rr * cam.s} fill="none" stroke="rgba(255,255,255,0.75)" strokeWidth={Math.max(1, cam.s * 0.12)} />)}
        {Array.from(fr.x).map((x, i) => {
          const th = angle(x);
          const braking = Math.min(1, Math.max(0, -fr.a[i] - 0.15) / 0.6) || (fr.v[i] < 0.6 ? 1 : 0);
          const brakeMark = i === PERTURB.car && show('brake') > 0.5 && simT >= PERTURB.from - 2 && simT <= PERTURB.to + 6;
          const mark = driving && i === autoCar ? C.green : brakeMark ? C.accent
            : fr.v[i] < 0.6 && simT > r.firstStop && show('jam') > 0.5 ? C.red : undefined;
          return <Car key={i} sx={c.sx + Math.cos(th) * R * cam.s} sy={c.sy + Math.sin(th) * R * cam.s} deg={(th * 180) / Math.PI + 90}
                      s={cam.s} color={BODY[i % BODY.length]} brake={braking} mark={mark} />;
        })}
        {driving && (() => {
          const th = angle(fr.x[autoCar]);
          const px = c.sx + Math.cos(th) * (R + 13) * cam.s;
          const py = c.sy + Math.sin(th) * (R + 13) * cam.s;
          return (
            <g opacity={Math.max(0.75, show('auto'))}>
              <rect x={px - 92} y={py - 20} width={184} height={40} rx={6} fill={C.panel} stroke={C.green} strokeWidth={2} />
              <text x={px} y={py + 9} textAnchor="middle" fill={C.green} fontFamily={FONT} fontSize={24} fontWeight={800}>
                {tx('selfDriving').toUpperCase()}
              </text>
            </g>
          );
        })()}
      </svg>
      <AbsoluteFill style={{background: 'radial-gradient(ellipse at center, rgba(0,0,0,0) 50%, rgba(5,8,18,0.6) 100%)'}} />
      <Panel o={show('speed')} style={{right: 64, top: 52, width: 250}}>
        <Label>{tx('meanSpeed')}</Label>
        <div style={{fontSize: 54, fontWeight: 800, color: C.accent, fontVariantNumeric: 'tabular-nums'}}>
          {(r.meanSpeed(simT) * 3.6).toFixed(0)} <span style={{fontSize: 26}}>KM/H</span>
        </div>
      </Panel>
      <Panel o={show('jam')} style={{right: 64, bottom: 80, width: 250}}>
        <Label>{tx('stoppedNow')}</Label>
        <div style={{fontSize: 54, fontWeight: 800, color: now ? C.red : C.text, fontVariantNumeric: 'tabular-nums'}}>{now}</div>
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
