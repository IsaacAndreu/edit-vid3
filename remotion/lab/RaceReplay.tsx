// A race rebuilt from data, seen from above, with live panels (the «simulation explainer» look):
// Paris 2024, women's 100 m final. All drawn in code: no footage.
import type {CSSProperties, FC, ReactNode} from 'react';
import {AbsoluteFill, Easing, interpolate, random, useCurrentFrame} from 'remotion';
import '../theme';
import {C as HUD, FONT, Label, Panel, Section, Tag, fade} from './hud';
import {ATHLETES, RACE, distance, order, peakSpeed, speed, timeAt, type Athlete} from './race';

export const FPS = 30;
export const DURATION = 2250;                  // 75 s

// --- timeline (frames) ----------------------------------------------------------------------------------------
const INTRO_END = 150;
const LANES_END = 390;
const GUN = 570;                               // the race starts
const SLOW = 0.4;                              // race seconds per real second
const FINISH = GUN + Math.round((11.1 / SLOW) * FPS);
const RESULTS_END = FINISH + 240;
const GAP_END = RESULTS_END + 300;

const raceTime = (f: number) => Math.max(0, ((f - GUN) / FPS) * SLOW);
const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;

const C = {...HUD, track: '#5b3f8c', trackDark: '#4a3275', infield: '#2f6b3d', stand: '#1a2236'};   // Paris 2024: purple track

// --- world → screen ---------------------------------------------------------------------------------------------
const LANE_W = 1.22;
const LANES = 9;
const laneY = (lane: number) => (lane - 0.5) * LANE_W;   // metres from the inner edge
const TRACK_H = LANES * LANE_W;

type Cam = {x: number; y: number; s: number};

const camera = (f: number): Cam => {
  const leader = Math.max(...ATHLETES.map((a) => distance(a, raceTime(f))));
  const keys: [number, Cam][] = [
    [0, {x: 50, y: TRACK_H / 2, s: 16}],
    [INTRO_END, {x: 50, y: TRACK_H / 2, s: 18}],
    [INTRO_END + 70, {x: 4, y: TRACK_H / 2, s: 52}],
    [GUN, {x: 6, y: TRACK_H / 2, s: 46}],
  ];
  if (f <= GUN) {
    for (let i = keys.length - 1; i >= 0; i--) {
      if (f >= keys[i][0]) {
        const [f0, a] = keys[i];
        const [f1, b] = keys[Math.min(i + 1, keys.length - 1)];
        const p = f1 === f0 ? 1 : interpolate(f, [f0, f1], [0, 1], {...clamp, easing: Easing.inOut(Easing.cubic)});
        return {x: a.x + (b.x - a.x) * p, y: a.y + (b.y - a.y) * p, s: a.s + (b.s - a.s) * p};
      }
    }
  }
  if (f <= FINISH) {
    const follow = Math.min(98, Math.max(6, leader - 2));
    const ease = interpolate(f, [GUN, GUN + 40], [0, 1], clamp);
    return {x: 6 + (follow - 6) * ease, y: TRACK_H / 2, s: interpolate(f, [FINISH - 60, FINISH], [46, 60], clamp)};
  }
  // after the line: a slow pull back over the finish
  return {x: interpolate(f, [FINISH, RESULTS_END], [97, 92], clamp), y: TRACK_H / 2,
          s: interpolate(f, [FINISH, FINISH + 90, GAP_END, DURATION], [60, 34, 34, 22], {...clamp, easing: Easing.inOut(Easing.cubic)})};
};

const toScreen = (cam: Cam, x: number, y: number) => ({sx: 960 + (x - cam.x) * cam.s, sy: 540 + (y - cam.y) * cam.s});

// --- the stadium ------------------------------------------------------------------------------------------------
const Stadium: FC<{cam: Cam}> = ({cam}) => {
  const left = -40;
  const right = 140;
  const p = (x: number, y: number) => toScreen(cam, x, y);
  const a = p(left, 0);
  const b = p(right, TRACK_H);
  const lines = [];
  for (let i = 0; i <= LANES; i++) {
    const y = p(0, i * LANE_W).sy;
    lines.push(<line key={`l${i}`} x1={a.sx} x2={b.sx} y1={y} y2={y} stroke="rgba(255,255,255,0.85)" strokeWidth={Math.max(1, cam.s * 0.05)} />);
  }
  const marks = [];
  for (let m = 0; m <= 100; m += 10) {
    const x = p(m, 0).sx;
    const major = m === 0 || m === 100;
    marks.push(
      <line key={`m${m}`} x1={x} x2={x} y1={p(0, 0).sy} y2={p(0, TRACK_H).sy}
            stroke={major ? '#ffffff' : 'rgba(255,255,255,0.18)'} strokeWidth={major ? Math.max(2, cam.s * 0.1) : 1}
            strokeDasharray={major ? undefined : '6 8'} />,
      <text key={`t${m}`} x={x} y={p(0, TRACK_H).sy + cam.s * 0.9} fill="rgba(255,255,255,0.55)" fontFamily={FONT}
            fontWeight={600} fontSize={Math.max(12, cam.s * 0.55)} textAnchor="middle">{m} M</text>,
    );
  }
  // stands: blocks of seats and a crowd of tiny dots, fixed by seed
  const crowd = [];
  for (let i = 0; i < 520; i++) {
    const x = left + random(`cx${i}`) * (right - left);
    const top = random(`cs${i}`) < 0.5;
    const y = top ? -9 + random(`cy${i}`) * 5.5 : TRACK_H + 3.5 + random(`cy${i}`) * 5.5;
    const q = p(x, y);
    crowd.push(<circle key={`c${i}`} cx={q.sx} cy={q.sy} r={Math.max(1, cam.s * 0.16)}
                       fill={['#8aa0c8', '#c9d3e6', '#f5a623', '#5b6b8c'][Math.floor(random(`cc${i}`) * 4)]} opacity={0.55} />);
  }
  const stand = (y0: number, y1: number, key: string) => {
    const s0 = p(left, y0);
    const s1 = p(right, y1);
    return <rect key={key} x={s0.sx} y={s0.sy} width={s1.sx - s0.sx} height={s1.sy - s0.sy} fill={C.stand} />;
  };
  const lane = Array.from({length: LANES}, (_, i) => {
    const y0 = p(left, i * LANE_W);
    const y1 = p(right, (i + 1) * LANE_W);
    return <rect key={`lane${i}`} x={y0.sx} y={y0.sy} width={y1.sx - y0.sx} height={y1.sy - y0.sy}
                 fill={i % 2 ? C.track : C.trackDark} />;
  });
  const cell = LANE_W / 4;
  const checks = [];
  for (let i = 0; i < LANES * 4; i++) {
    for (let j = 0; j < 2; j++) {
      const q = p(100 + j * cell, i * cell);
      checks.push(<rect key={`ck${i}-${j}`} x={q.sx} y={q.sy} width={cell * cam.s} height={cell * cam.s}
                        fill={(i + j) % 2 ? '#ffffff' : '#111111'} opacity={0.85} />);
    }
  }
  const numbers = Array.from({length: LANES}, (_, i) => {
    const q = p(-1.6, laneY(i + 1));
    return <text key={`n${i}`} x={q.sx} y={q.sy + cam.s * 0.25} fill="rgba(255,255,255,0.8)" fontFamily={FONT} fontWeight={800}
                 fontSize={Math.max(10, cam.s * 0.7)} textAnchor="middle">{i + 1}</text>;
  });
  const infield = [p(left, -3), p(right, 0)];
  const outer = [p(left, TRACK_H), p(right, TRACK_H + 3)];
  return (
    <svg width={1920} height={1080} style={{position: 'absolute'}}>
      <rect width={1920} height={1080} fill={C.night} />
      {stand(-10, -3, 'st1')}
      {stand(TRACK_H + 3, TRACK_H + 10, 'st2')}
      <rect x={infield[0].sx} y={infield[0].sy} width={infield[1].sx - infield[0].sx} height={infield[1].sy - infield[0].sy} fill={C.infield} />
      <rect x={outer[0].sx} y={outer[0].sy} width={outer[1].sx - outer[0].sx} height={outer[1].sy - outer[0].sy} fill={C.track} opacity={0.8} />
      {lane}
      {lines}
      {marks}
      {checks}
      {numbers}
      {crowd}
    </svg>
  );
};

// --- rain and grade ---------------------------------------------------------------------------------------------
const Rain: FC = () => {
  const f = useCurrentFrame();
  const drops = Array.from({length: 140}, (_, i) => {
    const x = (random(`rx${i}`) * 2200 + f * 9) % 2200 - 140;
    const y = (random(`ry${i}`) * 1200 + f * 38 * (0.7 + random(`rv${i}`) * 0.6)) % 1200 - 60;
    return <line key={i} x1={x} y1={y} x2={x - 7} y2={y + 26} stroke="rgba(200,215,255,0.22)" strokeWidth={1.4} />;
  });
  return (
    <svg width={1920} height={1080} style={{position: 'absolute'}}>
      {drops}
    </svg>
  );
};

const Grade: FC = () => (
  <AbsoluteFill style={{background: 'radial-gradient(ellipse at center, rgba(0,0,0,0) 55%, rgba(0,0,0,0.55) 100%)', pointerEvents: 'none'}} />
);

// --- athletes ---------------------------------------------------------------------------------------------------
const Runners: FC<{cam: Cam; t: number; show: number; f: number}> = ({cam, t, show, f}) => {
  const items = ATHLETES.map((a, n) => {
    const appear = interpolate(f, [INTRO_END + 70 + n * 14, INTRO_END + 90 + n * 14], [0, 1], clamp);
    if (appear <= 0) return null;
    const d = distance(a, t);
    const {sx, sy} = toScreen(cam, d, laneY(a.lane));
    const r = Math.max(5, cam.s * 0.32);
    const trail = toScreen(cam, Math.max(0, d - Math.min(d, speed(a, t) * 0.5)), laneY(a.lane));
    const hurt = a.injuredAt && d >= a.injuredAt;
    return (
      <g key={a.name} opacity={appear * (hurt ? 0.55 : 1)}>
        {t > 0 && <line x1={trail.sx} y1={sy} x2={sx} y2={sy} stroke={a.color} strokeOpacity={0.35} strokeWidth={r * 0.9} strokeLinecap="round" />}
        <circle cx={sx} cy={sy} r={r * 2.2} fill={a.color} opacity={0.18} />
        <circle cx={sx} cy={sy} r={r} fill={a.color} stroke="#0b1020" strokeWidth={2} />
        {show > 0 && (
          <g opacity={show}>
            <rect x={sx + r * 1.6} y={sy - 13} width={a.short.length * 9.5 + 46} height={26} rx={3} fill={C.panel} />
            <text x={sx + r * 1.6 + 8} y={sy + 6} fill={C.label} fontFamily={FONT} fontWeight={600} fontSize={16}>{a.lane}</text>
            <text x={sx + r * 1.6 + 24} y={sy + 6} fill={hurt ? C.red : C.text} fontFamily={FONT} fontWeight={700} fontSize={16} letterSpacing={0.6}>{a.short}</text>
          </g>
        )}
      </g>
    );
  });
  return <svg width={1920} height={1080} style={{position: 'absolute'}}>{items}</svg>;
};

// --- HUD pieces -------------------------------------------------------------------------------------------------
// --- moments of the race (from the race report) ------------------------------------------------------------------
const alfred = ATHLETES.find((a) => a.short === 'ALFRED')!;
const richardson = ATHLETES.find((a) => a.short === 'RICHARDSON')!;
const talou = ATHLETES.find((a) => a.short === 'TA LOU-SMITH')!;
const atRace = (seconds: number) => GUN + Math.round((seconds / SLOW) * FPS);

const CALLOUTS = [
  {at: atRace(timeAt(alfred, 10)), text: '10 m: Alfred, primera · Richardson, séptima', color: C.text},
  {at: atRace(timeAt(talou, 40)), text: '40 m: Ta Lou-Smith se lesiona', color: C.red},
  {at: atRace(timeAt(alfred, 50)), text: '50 m: Alfred · Kambundji · Neita · Jefferson', color: C.text},
  {at: atRace(timeAt(alfred, 80)), text: '80 m: Richardson ya es segunda', color: C.accent},
];

const fmt = (s: number) => s.toFixed(2);

// --- the composition --------------------------------------------------------------------------------------------
export const RaceReplay: FC = () => {
  const f = useCurrentFrame();
  const t = raceTime(f);
  const cam = camera(f);
  const leaderOrder = order(Math.min(t, 11.2));
  const labels = interpolate(f, [INTRO_END + 70, INTRO_END + 110, GUN + 30, GUN + 60, FINISH + 20, FINISH + 50], [0, 1, 1, 0.0, 0, 1], clamp);

  const intro = fade(f, 0, INTRO_END + 20, 18);
  const lanes = fade(f, INTRO_END + 60, LANES_END + 20);
  const reaction = fade(f, LANES_END, GUN + 50);
  const racing = fade(f, GUN, FINISH + 15, 15);
  const results = fade(f, FINISH + 20, RESULTS_END);
  const gap = fade(f, RESULTS_END, GAP_END);
  const end = fade(f, GAP_END, DURATION + 30);

  const gapRichardson = 100 - distance(richardson, alfred.time);
  const top = Math.max(...[alfred, richardson].map(peakSpeed));

  return (
    <AbsoluteFill style={{backgroundColor: C.night}}>
      <Stadium cam={cam} />
      <Runners cam={cam} t={t} show={labels} f={f} />
      <Rain />
      <Grade />
      <AbsoluteFill style={{background: C.night, opacity: interpolate(f, [GAP_END - 20, GAP_END + 20], [0, 0.55], clamp)}} />

      {/* 1 · title */}
      <Section text="La final" o={intro} f={f} start={8} />
      <Tag text={`${RACE.place} · ${RACE.date}`} o={intro} style={{left: 64, top: 140}} />

      {/* 2 · the lanes */}
      <Section text="Ocho atletas, nueve calles" o={lanes} f={f} start={INTRO_END + 60} />
      <Tag text="Calle 1 vacía" o={lanes} style={{left: 64, top: 140}} color={C.label} />

      {/* 3 · the reaction */}
      <Section text="El disparo" o={reaction} f={f} start={LANES_END} />
      <Panel o={reaction} style={{left: 64, bottom: 80, width: 520}}>
        <Label>Tiempo de reacción</Label>
        {[alfred, richardson].map((a, n) => {
          const grow = interpolate(f, [LANES_END + 20 + n * 15, LANES_END + 50 + n * 15], [0, 1], clamp);
          return (
            <div key={a.name} style={{marginTop: 14}}>
              <div style={{display: 'flex', justifyContent: 'space-between', fontSize: 20, fontWeight: 700}}>
                <span>{a.short}</span><span style={{color: n ? C.red : C.accent}}>{a.reaction.toFixed(3)} s</span>
              </div>
              <div style={{height: 10, background: 'rgba(255,255,255,0.08)', marginTop: 6, borderRadius: 2}}>
                <div style={{height: 10, width: `${(a.reaction / 0.25) * 100 * grow}%`, background: n ? C.red : C.accent, borderRadius: 2}} />
              </div>
            </div>
          );
        })}
        <div style={{marginTop: 16, fontSize: 18, fontWeight: 700, color: C.label, opacity: interpolate(f, [LANES_END + 80, LANES_END + 100], [0, 1], clamp)}}>
          RICHARDSON SALE <span style={{color: C.red}}>{((richardson.reaction - alfred.reaction) * 1000).toFixed(0)} MILÉSIMAS</span> TARDE
        </div>
      </Panel>

      {/* 4 · the race */}
      <Panel o={racing} style={{right: 64, top: 52, width: 230}}>
        <Label>Tiempo</Label>
        <div style={{fontSize: 52, fontWeight: 800, fontVariantNumeric: 'tabular-nums'}}>{fmt(Math.min(t, 11.1))}</div>
        <Label color={C.accent}>Cámara lenta ×{SLOW}</Label>
      </Panel>
      <Panel o={racing} style={{right: 64, bottom: 80, width: 300}}>
        <Label>Alfred ahora</Label>
        <div style={{fontSize: 52, fontWeight: 800, color: C.accent, fontVariantNumeric: 'tabular-nums'}}>
          {(speed(alfred, Math.min(t, alfred.time)) * 3.6).toFixed(1)} <span style={{fontSize: 26}}>KM/H</span>
        </div>
      </Panel>
      <Panel o={racing} style={{left: 64, top: 52, width: 300, padding: '14px 18px'}}>
        <Label>Posición</Label>
        {leaderOrder.map((a, n) => (
          <div key={a.name} style={{display: 'flex', gap: 10, fontSize: 19, fontWeight: 700, marginTop: 4,
                                    color: a.injuredAt && distance(a, t) >= a.injuredAt ? C.red : C.text}}>
            <span style={{width: 18, color: C.label}}>{n + 1}</span>
            <span style={{width: 10, height: 10, borderRadius: 5, background: a.color, marginTop: 7}} />
            <span>{a.short}</span>
          </div>
        ))}
      </Panel>
      {CALLOUTS.map((c) => (
        <Tag key={c.text} text={c.text} o={fade(f, c.at, c.at + 75, 8) * racing} color={c.color}
             style={{left: '50%', bottom: 90, transform: 'translateX(-50%)', fontSize: 24}} />
      ))}

      {/* 5 · results */}
      <Section text="Resultado" o={results} f={f} start={FINISH + 20} />
      <Panel o={results} style={{left: 64, top: 150, width: 560}}>
        <Label>Tiempos oficiales</Label>
        {[...ATHLETES].sort((a, b) => a.time - b.time).map((a, n) => (
          <div key={a.name} style={{display: 'flex', alignItems: 'center', gap: 12, fontSize: 22, fontWeight: 700, marginTop: 8,
                                    opacity: interpolate(f, [FINISH + 30 + n * 6, FINISH + 42 + n * 6], [0, 1], clamp)}}>
            <span style={{width: 22, color: n < 3 ? C.accent : C.label}}>{n + 1}</span>
            <span style={{width: 10, height: 10, borderRadius: 5, background: a.color}} />
            <span style={{flex: 1}}>{a.name.toUpperCase()} <span style={{color: C.label, fontSize: 17}}>{a.country}</span></span>
            {a.note && <span style={{fontSize: 15, color: '#0b1020', background: C.accent, borderRadius: 3, padding: '1px 6px'}}>{a.note}</span>}
            <span style={{width: 70, textAlign: 'right', fontVariantNumeric: 'tabular-nums', color: a.injuredAt ? C.red : C.text}}>{fmt(a.time)}</span>
          </div>
        ))}
      </Panel>

      {/* 6 · the gap */}
      <Section text="La distancia" o={gap} f={f} start={RESULTS_END} />
      <Panel o={gap} style={{left: 64, top: 150, width: 620}}>
        <Label>Cuando Alfred cruzó la meta</Label>
        <div style={{fontSize: 30, fontWeight: 700, marginTop: 10}}>
          RICHARDSON ESTABA A <span style={{color: C.accent, fontSize: 56, fontWeight: 800}}>
            {(gapRichardson * interpolate(f, [RESULTS_END + 20, RESULTS_END + 60], [0, 1], clamp)).toFixed(1)} M</span>
        </div>
        <div style={{marginTop: 18}}>
          <Label>Velocidad punta (reconstruida)</Label>
          {[alfred, richardson].map((a) => {
            const v = peakSpeed(a) * 3.6;
            return (
              <div key={a.name} style={{display: 'flex', alignItems: 'center', gap: 12, marginTop: 10, fontSize: 20, fontWeight: 700}}>
                <span style={{width: 120}}>{a.short}</span>
                <div style={{flex: 1, height: 12, background: 'rgba(255,255,255,0.08)', borderRadius: 2}}>
                  <div style={{height: 12, borderRadius: 2, background: a.color,
                               width: `${(v / (top * 3.6)) * 100 * interpolate(f, [RESULTS_END + 60, RESULTS_END + 100], [0, 1], clamp)}%`}} />
                </div>
                <span style={{width: 100, textAlign: 'right'}}>{v.toFixed(1)} KM/H</span>
              </div>
            );
          })}
        </div>
        <div style={{marginTop: 18, fontSize: 18, fontWeight: 700, color: C.label}}>
          LA VENTAJA LA SACÓ EN LA SALIDA: RICHARDSON CORRIÓ IGUAL DE RÁPIDO, PERO EMPEZÓ DETRÁS
        </div>
      </Panel>

      {/* 7 · what to remember */}
      <Panel o={end} style={{left: '50%', top: '50%', transform: 'translate(-50%, -50%)', width: 720, padding: '28px 34px'}}>
        <Label color={C.accent}>Lo que decidió la final</Label>
        {['Alfred salió primera y nunca dejó de liderar', `Richardson reaccionó ${((richardson.reaction - alfred.reaction) * 1000).toFixed(0)} milésimas más tarde`,
          'Remontó hasta segunda, pero no le dio', 'Primera medalla olímpica de Santa Lucía'].map((line, n) => {
          const on = interpolate(f, [GAP_END + 20 + n * 40, GAP_END + 34 + n * 40], [0, 1], clamp);
          return (
            <div key={line} style={{display: 'flex', alignItems: 'center', gap: 14, marginTop: 14, fontSize: 28, fontWeight: 700, opacity: on}}>
              <span style={{width: 26, height: 26, border: `2px solid ${C.accent}`, borderRadius: 3, color: C.accent, fontSize: 22,
                            display: 'flex', alignItems: 'center', justifyContent: 'center'}}>✓</span>
              <span style={{textTransform: 'uppercase'}}>{line}</span>
            </div>
          );
        })}
      </Panel>

      <div style={{position: 'absolute', left: 64, bottom: 30, fontFamily: FONT, fontSize: 14, letterSpacing: 1.2, color: 'rgba(255,255,255,0.45)'}}>
        RECONSTRUCCIÓN A PARTIR DE LOS TIEMPOS OFICIALES Y LA CRÓNICA DE LA CARRERA · POSICIONES INTERMEDIAS APROXIMADAS
      </div>
    </AbsoluteFill>
  );
};
