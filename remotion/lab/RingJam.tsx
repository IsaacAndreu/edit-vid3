// «Why traffic stops for no reason»: 22 simulated cars on a ring in the middle of a city seen from above. One driver
// brakes for a second and a half; the wave grows until cars stand still, and the space-time chart shows it moving
// backwards. All drawn and simulated in code.
import type {FC} from 'react';
import {AbsoluteFill, Easing, interpolate, random, useCurrentFrame} from 'remotion';
import '../theme';
import {BODY, Car, City, toScreen, type Cam} from './city';
import {C, FONT, Label, Panel, Section, Tag, fade} from './hud';
import {FRAMES, PERTURB, RING, SAMPLE, at, meanSpeed, startSpeed, stopped} from './traffic';

export const FPS = 30;
export const DURATION = 2250;
const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;

// --- time: real time first, then a time-lapse while the jam grows, then real time again ---------------------------
const LAPSE_FROM = 600;
const LAPSE_TO = 1500;
const LAPSE = 2.5;
const simTime = (f: number) =>
  f < LAPSE_FROM ? f / FPS
    : f < LAPSE_TO ? LAPSE_FROM / FPS + ((f - LAPSE_FROM) / FPS) * LAPSE
      : LAPSE_FROM / FPS + ((LAPSE_TO - LAPSE_FROM) / FPS) * LAPSE + (f - LAPSE_TO) / FPS;
const frameOf = (t: number) => {
  for (let f = 0; f < DURATION; f++) if (simTime(f) >= t) return f;
  return DURATION;
};
const CHART_FROM = 1500;
const CHECK_FROM = 1950;

const R = RING.length / (2 * Math.PI);          // 36.6 m
const angle = (x: number) => -Math.PI / 2 + (2 * Math.PI * x) / RING.length;
const FIRST_STOP = FRAMES.findIndex((fr) => Array.from(fr.v).some((v) => v < 0.6)) * SAMPLE;

const camera = (f: number): Cam => {
  const s = interpolate(f, [0, 40, 260, CHART_FROM, CHART_FROM + 50, CHECK_FROM, DURATION],
                        [2.6, 2.6, 10.5, 10.5, 8.5, 8.5, 6], {...clamp, easing: Easing.inOut(Easing.cubic)});
  const x = interpolate(f, [CHART_FROM, CHART_FROM + 50, CHECK_FROM, CHECK_FROM + 40], [0, 50, 50, 0], {...clamp, easing: Easing.inOut(Easing.cubic)});
  return {x, y: 0, s};
};

// --- cars ---------------------------------------------------------------------------------------------------------
const Ring: FC<{cam: Cam; t: number; f: number}> = ({cam, t, f}) => {
  const c = toScreen(cam, 0, 0);
  const fr = at(t);
  const show = interpolate(f, [150, 230], [0, 1], clamp);
  const marked = f >= frameOf(PERTURB.from) - 10 && f <= frameOf(PERTURB.to) + 60;
  return (
    <g opacity={Math.max(show, 0.35)}>
      <circle cx={c.sx} cy={c.sy} r={(R + 5.5) * cam.s} fill={'#62656b'} />
      <circle cx={c.sx} cy={c.sy} r={(R + 3.6) * cam.s} fill={'#33363c'} />
      <circle cx={c.sx} cy={c.sy} r={(R - 3.6) * cam.s} fill={'#4a6e3f'} />
      <circle cx={c.sx} cy={c.sy} r={(R + 3.2) * cam.s} fill="none" stroke="rgba(255,255,255,0.75)" strokeWidth={Math.max(1, cam.s * 0.12)} />
      <circle cx={c.sx} cy={c.sy} r={(R - 3.2) * cam.s} fill="none" stroke="rgba(255,255,255,0.75)" strokeWidth={Math.max(1, cam.s * 0.12)} />
      {Array.from(fr.x).map((x, i) => {
        const th = angle(x);
        const sx = c.sx + Math.cos(th) * R * cam.s;
        const sy = c.sy + Math.sin(th) * R * cam.s;
        const braking = Math.min(1, Math.max(0, -fr.a[i] - 0.15) / 0.6) || (fr.v[i] < 0.6 ? 1 : 0);
        const mark = i === PERTURB.car && marked ? C.accent : fr.v[i] < 0.6 && t > FIRST_STOP ? C.red : undefined;
        return <Car key={i} sx={sx} sy={sy} deg={(th * 180) / Math.PI + 90} s={cam.s} color={BODY[i % BODY.length]} brake={braking} mark={mark} />;
      })}
    </g>
  );
};

// a few cars driving the city streets, for life
const Traffic: FC<{cam: Cam; f: number}> = ({cam, f}) => {
  const cars = Array.from({length: 46}, (_, k) => {
    const vertical = random(`tv${k}`) < 0.5;
    const line = (Math.floor(random(`tl${k}`) * 14) - 7) * 72;
    if (Math.abs(line) < 100) return null;
    const dir = random(`td${k}`) < 0.5 ? 1 : -1;
    const along = ((random(`to${k}`) * 1040 + dir * (f / FPS) * (9 + random(`ts${k}`) * 5)) % 1040 + 1040) % 1040 - 520;
    const lane = dir * 2.2;
    const wx = vertical ? line + lane : along;
    const wy = vertical ? along : line - lane;
    if (Math.hypot(wx, wy) < 64) return null;          // the park: no street there
    const {sx, sy} = toScreen(cam, wx, wy);
    if (sx < -40 || sx > 1960 || sy < -40 || sy > 1120) return null;
    const deg = vertical ? (dir > 0 ? 90 : -90) : dir > 0 ? 0 : 180;
    return <Car key={k} sx={sx} sy={sy} deg={deg} s={cam.s} color={BODY[k % BODY.length]} brake={0} />;
  });
  return <g>{cars}</g>;
};

// --- space-time chart: every car's position (up) against time (across), coloured by speed ------------------------
const speedColour = (v: number) => {
  const k = Math.min(1, v / startSpeed());
  if (k < 0.5) return `rgb(255, ${Math.round(70 + k * 2 * 140)}, 70)`;
  return `rgb(${Math.round(255 - (k - 0.5) * 2 * 194)}, ${Math.round(210 + (k - 0.5) * 2 * 10)}, ${Math.round(70 + (k - 0.5) * 2 * 62)})`;
};

const SpaceTime: FC<{t: number; o: number; f: number}> = ({t, o, f}) => {
  const W = 760;
  const H = 470;
  const from = 0;
  const to = Math.min(t, 110);
  const grow = interpolate(f, [CHART_FROM + 20, CHART_FROM + 160], [0, 1], clamp);
  const until = from + (to - from) * grow;
  const dots = [];
  for (let s = from; s <= until; s += 0.5) {
    const fr = at(s);
    for (let i = 0; i < RING.cars; i++) {
      dots.push(<rect key={`${s}-${i}`} x={(s / 110) * W} y={H - (fr.x[i] / RING.length) * H} width={W / 220 + 0.8} height={2.4}
                      fill={speedColour(fr.v[i])} />);
    }
  }
  return (
    <Panel o={o} style={{right: 64, top: 150, width: W + 44}}>
      <Label>Posición de cada coche en el anillo, segundo a segundo</Label>
      <svg width={W} height={H} style={{marginTop: 12, display: 'block', background: 'rgba(255,255,255,0.03)'}}>
        {dots}
        <line x1={(PERTURB.from / 110) * W} x2={(PERTURB.from / 110) * W} y1={0} y2={H} stroke={C.accent} strokeDasharray="4 6" />
      </svg>
      <div style={{display: 'flex', justifyContent: 'space-between', marginTop: 8}}>
        <Label>Tiempo →</Label>
        <Label color={C.accent}>│ El frenazo</Label>
        <Label><span style={{color: '#ff5a46'}}>■</span> parado <span style={{color: '#3ddc84', marginLeft: 12}}>■</span> a velocidad normal</Label>
      </div>
    </Panel>
  );
};

// --- the composition ------------------------------------------------------------------------------------------------
export const RingJam: FC = () => {
  const f = useCurrentFrame();
  const t = simTime(f);
  const cam = camera(f);
  const brakeAt = frameOf(PERTURB.from);
  const stopAt = frameOf(FIRST_STOP);
  const intro = fade(f, 0, 300, 18);
  const setup = fade(f, 300, LAPSE_FROM + 10);
  const jam = fade(f, LAPSE_FROM, CHART_FROM + 10);
  const chart = fade(f, CHART_FROM, CHECK_FROM + 10);
  const end = fade(f, CHECK_FROM, DURATION + 30);
  const live = fade(f, 230, CHECK_FROM + 10);
  const now = stopped(t);
  return (
    <AbsoluteFill style={{backgroundColor: C.night}}>
      <City cam={cam} clearing={58} ring={[R - 4, R + 6]}>
        <Traffic cam={cam} f={f} />
      </City>
      <svg width={1920} height={1080} style={{position: 'absolute'}}>
        <Ring cam={cam} t={t} f={f} />
      </svg>
      <AbsoluteFill style={{background: 'radial-gradient(ellipse at center, rgba(0,0,0,0) 50%, rgba(5,8,18,0.6) 100%)'}} />
      <AbsoluteFill style={{background: C.night, opacity: interpolate(f, [CHART_FROM, CHART_FROM + 40, CHECK_FROM, CHECK_FROM + 30, DURATION - 60, DURATION],
                                                                      [0, 0.25, 0.25, 0.5, 0.5, 0.7], clamp)}} />

      <Section text="Atascos sin motivo" o={intro} f={f} start={10} />
      <Tag text="2008 · 22 coches · un círculo de 230 metros" o={intro} style={{left: 64, top: 140}} />

      <Section text="Todos a la misma velocidad" o={setup} f={f} start={300} />
      <Section text="El atasco fantasma" o={jam} f={f} start={LAPSE_FROM} />
      <Section text="La huella del atasco" o={chart} f={f} start={CHART_FROM} />

      <Panel o={live} style={{right: 64, top: 52, width: 250}}>
        <Label>Velocidad media</Label>
        <div style={{fontSize: 54, fontWeight: 800, color: C.accent, fontVariantNumeric: 'tabular-nums'}}>
          {(meanSpeed(t) * 3.6).toFixed(0)} <span style={{fontSize: 26}}>KM/H</span>
        </div>
        <Label>{f >= LAPSE_FROM && f < LAPSE_TO ? `Tiempo ×${LAPSE}` : 'Tiempo real'} · {t.toFixed(0)} s</Label>
      </Panel>
      <Panel o={live * (f < CHART_FROM ? 1 : 0.0)} style={{right: 64, bottom: 80, width: 250}}>
        <Label>Parados ahora</Label>
        <div style={{fontSize: 54, fontWeight: 800, color: now ? C.red : C.text, fontVariantNumeric: 'tabular-nums'}}>{now}</div>
        <Label>de {RING.cars} coches</Label>
      </Panel>

      <Tag text="Un conductor frena un poco · 1,5 segundos" o={fade(f, brakeAt - 5, brakeAt + 120, 8)} color={C.accent}
           style={{left: '50%', bottom: 90, transform: 'translateX(-50%)', fontSize: 24}} />
      <Tag text="Nadie ha chocado. No hay obras ni semáforos" o={fade(f, stopAt, stopAt + 150, 8)} color={C.red}
           style={{left: '50%', bottom: 90, transform: 'translateX(-50%)', fontSize: 24}} />
      <Tag text="Los coches avanzan, pero el atasco va hacia atrás" o={fade(f, stopAt + 170, LAPSE_TO, 8)}
           style={{left: '50%', bottom: 90, transform: 'translateX(-50%)', fontSize: 24}} />

      <SpaceTime t={t} o={chart} f={f} />
      <Tag text="Cada franja roja es el atasco: avanza el tiempo y baja por el anillo" o={chart}
           style={{right: 64, top: 760, fontSize: 20}} color={C.label} />

      <Panel o={end} style={{left: '50%', top: '50%', transform: 'translate(-50%, -50%)', width: 760, padding: '28px 34px'}}>
        <Label color={C.accent}>Lo que hemos visto</Label>
        {['Nadie hizo nada mal', 'Bastó un frenazo de un segundo y medio',
          'Con poco espacio, cada uno frena un poco más que el de delante', 'El atasco viaja hacia atrás, contra el tráfico'].map((line, n) => {
          const on = interpolate(f, [CHECK_FROM + 20 + n * 40, CHECK_FROM + 34 + n * 40], [0, 1], clamp);
          return (
            <div key={line} style={{display: 'flex', alignItems: 'center', gap: 14, marginTop: 14, fontSize: 28, fontWeight: 700, opacity: on, fontFamily: FONT}}>
              <span style={{width: 26, height: 26, border: `2px solid ${C.accent}`, borderRadius: 3, color: C.accent, fontSize: 22,
                            display: 'flex', alignItems: 'center', justifyContent: 'center'}}>✓</span>
              <span style={{textTransform: 'uppercase'}}>{line}</span>
            </div>
          );
        })}
      </Panel>

      <div style={{position: 'absolute', left: 64, bottom: 30, fontFamily: FONT, fontSize: 14, letterSpacing: 1.2, color: 'rgba(255,255,255,0.5)'}}>
        SIMULACIÓN CON EL MODELO DE CONDUCTOR INTELIGENTE (IDM) · EL MISMO MONTAJE QUE EL EXPERIMENTO DE SUGIYAMA ET AL. (2008)
      </div>
    </AbsoluteFill>
  );
};
