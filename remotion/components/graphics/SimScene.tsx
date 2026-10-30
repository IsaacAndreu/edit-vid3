// A simulation video's shot (pipeline/simulacion.py): the world being simulated, seen from above, with the camera and
// the panel the narration asks for. The simulation's clock is the video's own time since this world came on screen
// (graphic.since), so consecutive shots of one world are one continuous simulation; the camera moves from the previous
// shot's focus (graphic.prev) to this one's.
import type { FC } from 'react';
import { AbsoluteFill, Audio, Easing, interpolate, Sequence, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';
import type { SimGraphic } from '../../graphics';
import { BODY, Car, City, toScreen, type Cam } from '../../lab/city';
import { CrucesView, LAYOUTS } from '../../lab/Cruces';
import { signalChanges } from '../../lab/junction';
import { C, FONT, Label, Panel, Section } from '../../lab/hud';
import { FIRST_STOP, FRAMES, PERTURB, RING, SAMPLE, at, clock, meanSpeed, startSpeed, stopped } from '../../lab/traffic';

const clamp = { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' } as const;
const RING_LAPSE = 2.5;                    // the ring's jam takes a minute and a half to grow: shown faster

// --- the ring: a phantom jam -------------------------------------------------------------------------------------------
const R = RING.length / (2 * Math.PI);
const angle = (x: number) => -Math.PI / 2 + (2 * Math.PI * x) / RING.length;

const ringCamera = (focus: string): Cam => (focus === 'chart' ? { x: 50, y: 0, s: 8.5 } : { x: 0, y: 0, s: 10.5 });

const speedColour = (v: number) => {
  const k = Math.min(1, v / startSpeed());
  if (k < 0.5) return `rgb(255, ${Math.round(70 + k * 2 * 140)}, 70)`;
  return `rgb(${Math.round(255 - (k - 0.5) * 2 * 194)}, ${Math.round(210 + (k - 0.5) * 2 * 10)}, ${Math.round(70 + (k - 0.5) * 2 * 62)})`;
};

const SpaceTime: FC<{ simT: number; o: number }> = ({ simT, o }) => {
  const W = 760;
  const H = 470;
  const span = Math.max(20, Math.min(simT, FRAMES.length * SAMPLE));
  const dots = [];
  for (let s = 0; s <= simT; s += Math.max(0.5, span / 220)) {
    const fr = at(s);
    for (let i = 0; i < RING.cars; i++) {
      dots.push(<rect key={`${s}-${i}`} x={(s / span) * W} y={H - (fr.x[i] / RING.length) * H} width={W / 220 + 0.8} height={2.4} fill={speedColour(fr.v[i])} />);
    }
  }
  return (
    <Panel o={o} style={{ right: 64, top: 150, width: W + 44 }}>
      <Label>Posición de cada coche en el anillo, segundo a segundo</Label>
      <svg width={W} height={H} style={{ marginTop: 12, display: 'block', background: 'rgba(255,255,255,0.03)' }}>{dots}</svg>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 8 }}>
        <Label>Tiempo →</Label>
        <Label><span style={{ color: '#ff5a46' }}>■</span> parado <span style={{ color: '#3ddc84', marginLeft: 12 }}>■</span> a velocidad normal</Label>
      </div>
    </Panel>
  );
};

const RingView: FC<{ simT: number; cam: Cam; o: (name: string) => number }> = ({ simT, cam, o }) => {
  const fr = at(simT);
  const c = toScreen(cam, 0, 0);
  const now = stopped(simT);
  return (
    <AbsoluteFill style={{ backgroundColor: C.night }}>
      <City cam={cam} clearing={58} ring={[R - 4, R + 6]} />
      <svg width={1920} height={1080} style={{ position: 'absolute' }}>
        <circle cx={c.sx} cy={c.sy} r={(R + 5.5) * cam.s} fill="#62656b" />
        <circle cx={c.sx} cy={c.sy} r={(R + 3.6) * cam.s} fill="#33363c" />
        <circle cx={c.sx} cy={c.sy} r={(R - 3.6) * cam.s} fill="#4a6e3f" />
        {[R + 3.2, R - 3.2].map((r) => <circle key={r} cx={c.sx} cy={c.sy} r={r * cam.s} fill="none" stroke="rgba(255,255,255,0.75)" strokeWidth={Math.max(1, cam.s * 0.12)} />)}
        {Array.from(fr.x).map((x, i) => {
          const th = angle(x);
          const braking = Math.min(1, Math.max(0, -fr.a[i] - 0.15) / 0.6) || (fr.v[i] < 0.6 ? 1 : 0);
          const brakeMark = i === PERTURB.car && o('brake') > 0.5 && simT >= PERTURB.from - 2 && simT <= PERTURB.to + 6;
          const mark = brakeMark ? C.accent : fr.v[i] < 0.6 && simT > FIRST_STOP && o('jam') > 0.5 ? C.red : undefined;
          return <Car key={i} sx={c.sx + Math.cos(th) * R * cam.s} sy={c.sy + Math.sin(th) * R * cam.s} deg={(th * 180) / Math.PI + 90}
                      s={cam.s} color={BODY[i % BODY.length]} brake={braking} mark={mark} />;
        })}
      </svg>
      <AbsoluteFill style={{ background: 'radial-gradient(ellipse at center, rgba(0,0,0,0) 50%, rgba(5,8,18,0.6) 100%)' }} />
      <Panel o={o('speed')} style={{ right: 64, top: 52, width: 250 }}>
        <Label>Velocidad media</Label>
        <div style={{ fontSize: 54, fontWeight: 800, color: C.accent, fontVariantNumeric: 'tabular-nums' }}>
          {(meanSpeed(simT) * 3.6).toFixed(0)} <span style={{ fontSize: 26 }}>KM/H</span>
        </div>
      </Panel>
      <Panel o={o('jam')} style={{ right: 64, bottom: 80, width: 250 }}>
        <Label>Parados ahora</Label>
        <div style={{ fontSize: 54, fontWeight: 800, color: now ? C.red : C.text, fontVariantNumeric: 'tabular-nums' }}>{now}</div>
        <Label>de {RING.cars} coches</Label>
      </Panel>
      <SpaceTime simT={simT} o={o('chart')} />
      <div style={{ position: 'absolute', left: 64, bottom: 30, fontFamily: FONT, fontSize: 14, letterSpacing: 1.2, color: 'rgba(255,255,255,0.5)' }}>
        SIMULACIÓN CON EL MODELO DE CONDUCTOR INTELIGENTE (IDM) · 22 COCHES EN UN CÍRCULO DE 230 M
      </div>
    </AbsoluteFill>
  );
};

// --- sound: the street's hum under every shot of a world (continuing where the last shot left it), a relay click when
// the lights change (when they are in sight), a soft tick when a panel comes in and each time a car stands still in the jam
const SimSounds: FC<{ graphic: SimGraphic; durationInFrames: number; fps: number }> = ({ graphic, durationInFrames, fps }) => {
  const sounds = graphic.sounds;
  if (!sounds) return null;
  const length = durationInFrames / fps;
  const t0 = graphic.at - graphic.since;
  const cues: number[] = [];                       // seconds in this shot
  const clicks: number[] = [];
  if (graphic.overlay !== 'none' || graphic.stat) cues.push(0.35);
  if (graphic.world === 'cruces' && graphic.focus !== 'right') clicks.push(...signalChanges(t0, t0 + length).map((c) => c - t0));
  if (graphic.world === 'anillo' && graphic.overlay === 'jam') {
    let before = stopped(clock(graphic.at, graphic.since, graphic.cues, RING_LAPSE));
    for (let s = 0.1; s < length; s += 0.1) {
      const now = stopped(clock(graphic.at + s, graphic.since, graphic.cues, RING_LAPSE));
      if (now > before) cues.push(s);
      before = now;
    }
  }
  const loop = 20 * fps;
  return (
    <>
      {sounds.ambient && <Audio src={staticFile(sounds.ambient)} loop volume={0.35} startFrom={Math.round(t0 * fps) % loop} />}
      {sounds.click && clicks.map((s) => (
        <Sequence key={`c${s}`} from={Math.round(s * fps)} durationInFrames={6}><Audio src={staticFile(sounds.click!)} volume={0.32} /></Sequence>
      ))}
      {sounds.tick && cues.filter((s, i) => i === 0 || s - cues[i - 1] > 0.25).map((s) => (
        <Sequence key={`t${s}`} from={Math.round(s * fps)} durationInFrames={6}><Audio src={staticFile(sounds.tick!)} volume={0.22} /></Sequence>
      ))}
    </>
  );
};

// --- one shot ---------------------------------------------------------------------------------------------------------
export const SimScene: FC<{ graphic: SimGraphic; durationInFrames: number }> = ({ graphic, durationInFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const local = frame / fps;
  const length = durationInFrames / fps;
  const worldT = graphic.at + local - graphic.since;          // seconds since this world came on screen
  const move = interpolate(local, [0, 0.8], [0, 1], { ...clamp, easing: Easing.inOut(Easing.cubic) });
  const on = interpolate(local, [0, 0.35, length - 0.25, length], [0, 1, 1, 0.85], clamp);
  const o = (name: string) => (graphic.overlay === name ? on : 0);
  let body;
  if (graphic.world === 'anillo') {
    const a = ringCamera(graphic.prev);
    const b = ringCamera(graphic.focus);
    const cam = { x: a.x + (b.x - a.x) * move, y: 0, s: a.s + (b.s - a.s) * move };
    body = <RingView simT={clock(graphic.at + local, graphic.since, graphic.cues, RING_LAPSE)} cam={cam} o={(name) => (name === 'chart' && graphic.focus === 'chart' ? on : o(name))} />;
  } else {
    const a = LAYOUTS[(graphic.prev in LAYOUTS ? graphic.prev : 'both') as keyof typeof LAYOUTS];
    const b = LAYOUTS[(graphic.focus in LAYOUTS ? graphic.focus : 'both') as keyof typeof LAYOUTS];
    const mix = (x: number, y: number) => x + (y - x) * move;
    const reveal = (from: number, to: number) => (graphic.overlay === 'conflicts' ? interpolate(local, [length * from, length * to], [0, 1], clamp) : 0);
    body = <CrucesView simT={worldT} split={mix(a.split, b.split)} left={mix(a.left, b.left)} right={mix(a.right, b.right)}
                       focus={graphic.focus as 'both' | 'left' | 'right'} o={o} revealLights={reveal(0.05, 0.45)} revealRound={reveal(0.55, 0.8)}
                       pathsDrawn={interpolate(local, [0.2, 1.8], [0, 1], { ...clamp, easing: Easing.inOut(Easing.cubic) })} />;
  }
  // a small zoom punch only when a world comes on screen (a real cut): a panel coming in, or the camera moving to the
  // other side, already says «new line» — a punch on top of them jarred
  const cut = Math.abs(graphic.at - graphic.since) < 0.01;
  const punch = cut ? 1 + 0.03 * Math.sin(Math.PI * Math.min(1, local / 0.5)) : 1;
  return (
    <AbsoluteFill>
      <AbsoluteFill style={{ transform: `scale(${punch})` }}>{body}</AbsoluteFill>
      <SimSounds graphic={graphic} durationInFrames={durationInFrames} fps={fps} />
      {graphic.title && (
        <div style={{ position: 'absolute', left: 0, top: 96, width: 1920 }}>
          <Section text={graphic.title} o={on} f={frame} start={0} />
        </div>
      )}
      {graphic.stat && (
        <Panel o={on} style={{ left: '50%', bottom: 70, transform: 'translateX(-50%)', textAlign: 'center', minWidth: 360 }}>
          <Label>{graphic.stat.label}</Label>
          <div style={{ fontSize: 64, fontWeight: 800, color: C.accent, lineHeight: 1.05 }}>{graphic.stat.value}</div>
        </Panel>
      )}
      {graphic.list.length > 0 && (
        <>
          <AbsoluteFill style={{ background: C.night, opacity: 0.55 * on }} />
          <Panel o={on} style={{ left: '50%', top: '50%', transform: 'translate(-50%, -50%)', width: 780, padding: '28px 34px' }}>
            <Label color={C.accent}>Lo que hemos visto</Label>
            {graphic.list.map((line, n) => {
              const shown = interpolate(local, [0.3 + n * 0.6, 0.6 + n * 0.6], [0, 1], clamp);
              return (
                <div key={line} style={{ display: 'flex', alignItems: 'center', gap: 14, marginTop: 14, fontSize: 28, fontWeight: 700, opacity: shown }}>
                  <span style={{ width: 26, height: 26, border: `2px solid ${C.accent}`, borderRadius: 3, color: C.accent, fontSize: 22,
                                 display: 'flex', alignItems: 'center', justifyContent: 'center' }}>✓</span>
                  <span>{line}</span>
                </div>
              );
            })}
          </Panel>
        </>
      )}
    </AbsoluteFill>
  );
};
