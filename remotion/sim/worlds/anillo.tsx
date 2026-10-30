// The phantom jam: cars on a 230 m ring (Sugiyama et al., 2008). Its clock is paced to the voice: the brake falls on
// the line that points at it (cues.brake), the first car stops on the line that speaks of the jam (cues.jam).
import type {FC} from 'react';
import {AbsoluteFill} from 'remotion';
import {BODY, Car, City, toScreen, type Cam} from '../city';
import {C, Label, Panel} from '../hud';
import {tx} from '../i18n';
import {PERTURB, RING, SAMPLE, ring, type Ring} from '../traffic';
import {Note, param, type World, type WorldProps} from '../world';

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

const clockOf = (g: WorldProps['g'], r: Ring, t: number) => r.clock(t, g.since, g.cues, LAPSE);

const View: FC<WorldProps> = ({g, local, move, on, o}) => {
  const r = ring(param(g, 'cars', 22));
  const simT = clockOf(g, r, g.at + local);
  const a = camera(g.prev);
  const b = camera(g.focus);
  const cam = {x: a.x + (b.x - a.x) * move, y: 0, s: a.s + (b.s - a.s) * move};
  const show = (name: string) => (name === 'chart' && g.focus === 'chart' ? on : o(name));
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
          const mark = brakeMark ? C.accent : fr.v[i] < 0.6 && simT > r.firstStop && show('jam') > 0.5 ? C.red : undefined;
          return <Car key={i} sx={c.sx + Math.cos(th) * R * cam.s} sy={c.sy + Math.sin(th) * R * cam.s} deg={(th * 180) / Math.PI + 90}
                      s={cam.s} color={BODY[i % BODY.length]} brake={braking} mark={mark} />;
        })}
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
      <Note>{tx('ringNote', {n: r.cars})}</Note>
    </AbsoluteFill>
  );
};

// a tick each time one more car stands still while the jam panel is on
const sounds = (g: WorldProps['g'], length: number) => {
  if (g.overlay !== 'jam') return {};
  const r = ring(param(g, 'cars', 22));
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
