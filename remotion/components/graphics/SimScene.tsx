// A simulation video's shot (pipeline/simulacion.py): the world being simulated (remotion/sim/registry.ts), seen
// from above, with the camera and the panel the narration asks for. The simulation's clock is the video's own time
// since this world came on screen (graphic.since), so consecutive shots of one world are one continuous simulation;
// the camera moves from the previous shot's focus (graphic.prev) to this one's. Over any world: a section title, a
// figure the narrator says, the source the line cites, the closing recap. The channel's language, accent colour and
// map theme come with every shot (one per video: set here once per frame).
import type { FC } from 'react';
import { AbsoluteFill, Audio, Easing, interpolate, Sequence, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';
import type { SimGraphic } from '../../graphics';
import { countUp } from '../countUp';
import { setTheme } from '../../sim/city';
import { C, FONT, Label, Panel, Section, setAccent } from '../../sim/hud';
import { addWords, setLang, tx } from '../../sim/i18n';
import { Legend } from '../../sim/look';
import { WORLDS } from '../../sim/registry';
import { clamp } from '../../sim/world';

// --- sound: the street's hum under every shot of a world (continuing where the last shot left it), the world's clicks
// (a light changing in sight…), a soft tick when a panel comes in and on the world's own events (a car stopping…).
// Not played with the picture (the video's render is silent and its sound mixed apart): the SimAudio composition
// renders these alone into a track that render.py mixes under the voice.
export const SimSounds: FC<{ graphic: SimGraphic; durationInFrames: number; fps: number }> = ({ graphic, durationInFrames, fps }) => {
  const sounds = graphic.sounds;
  if (!sounds) return null;
  const length = durationInFrames / fps;
  const t0 = graphic.at - graphic.since;
  const own = WORLDS[graphic.world]?.sounds?.(graphic, length) ?? {};
  const ticks = [...(graphic.overlay !== 'none' || graphic.stat ? [0.35] : []), ...(own.ticks ?? [])].sort((a, b) => a - b);
  const clicks = own.clicks ?? [];
  const loop = 20 * fps;
  return (
    <>
      {sounds.ambient && <Audio src={staticFile(sounds.ambient)} loop volume={0.35} startFrom={Math.round(t0 * fps) % loop} />}
      {sounds.click && clicks.map((s) => (
        <Sequence key={`c${s}`} from={Math.round(s * fps)} durationInFrames={6}><Audio src={staticFile(sounds.click!)} volume={0.32} /></Sequence>
      ))}
      {sounds.tick && ticks.filter((s, i) => i === 0 || s - ticks[i - 1] > 0.25).map((s) => (
        <Sequence key={`t${s}`} from={Math.round(s * fps)} durationInFrames={6}><Audio src={staticFile(sounds.tick!)} volume={0.22} /></Sequence>
      ))}
    </>
  );
};

// --- one shot ---------------------------------------------------------------------------------------------------------
addWords({
  pause: {es: 'Pausa', pt: 'Pausa', fr: 'Pause', de: 'Pause', en: 'Pause'},
  rewind: {es: 'Otra vez', pt: 'Outra vez', fr: 'Encore', de: 'Nochmal', en: 'Again'},
  slowMo: {es: 'Cámara lenta · 0,5×', pt: 'Câmara lenta · 0,5×', fr: 'Ralenti · 0,5×', de: 'Zeitlupe · 0,5×', en: 'Slow motion · 0.5×'},
});

addWords({
  rulesTitle: {es: 'Las reglas', pt: 'As regras', fr: 'Les règles', de: 'Die Regeln', en: 'The rules'},
});

/** The closing summary as a montage: each idea of the list over its key scene of the video, played fast, one after
 * the other in the video's order; along the bottom the ideas ticked off as they pass. */
const Recap: FC<{ graphic: SimGraphic; real: number; length: number }> = ({ graphic, real, length }) => {
  const items = graphic.list;
  const clips = graphic.recap ?? [];
  const seg = length / items.length;
  const i = Math.min(items.length - 1, Math.floor(real / seg));
  const inSeg = real - i * seg;
  const clip = clips[i % clips.length];
  const world = WORLDS[clip.world] ?? WORLDS.cruces;
  const fast = inSeg * 2.2;                                   // «montaje rápido»: the scene runs at double speed
  const fade = interpolate(inSeg, [0, 0.25, seg - 0.25, seg], [0, 1, 1, 0], clamp);
  const on = (name: string) => (clip.overlay === name ? 1 : 0);
  return (
    <AbsoluteFill style={{ background: C.night }}>
      <AbsoluteFill style={{ opacity: fade, transform: `scale(${1.04 - 0.04 * Math.min(1, inSeg / seg)})` }}>
        <world.View g={clip} local={fast} real={inSeg} length={seg * 2.2} worldT={clip.at + fast - clip.since} move={1} on={1} o={on} />
      </AbsoluteFill>
      <AbsoluteFill style={{ background: 'linear-gradient(180deg, rgba(5,8,15,0) 55%, rgba(5,8,15,0.85) 100%)' }} />
      <div style={{ position: 'absolute', left: 0, right: 0, bottom: 150, textAlign: 'center', fontFamily: FONT, fontSize: 64, fontWeight: 800,
                    color: C.text, textTransform: 'uppercase', letterSpacing: 1, opacity: fade, textShadow: '0 4px 18px rgba(0,0,0,0.7)',
                    transform: `translateY(${(1 - fade) * 14}px)` }}>
        {items[i]}
      </div>
      <div style={{ position: 'absolute', left: 0, right: 0, bottom: 60, display: 'flex', justifyContent: 'center', gap: 18 }}>
        {items.map((text, k) => (
          <div key={text} style={{ display: 'flex', alignItems: 'center', gap: 8, fontFamily: FONT, fontSize: 22, fontWeight: 800,
                                   textTransform: 'uppercase', color: k === i ? C.you : k < i ? C.text : C.label,
                                   opacity: k <= i ? 1 : 0.55 }}>
            <span style={{ width: 24, height: 24, borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center',
                           background: k < i ? C.green : k === i ? C.you : 'rgba(255,255,255,0.15)', color: '#0b1020', fontSize: 16 }}>
              {k < i ? '✓' : k + 1}
            </span>
            {text.length > 26 ? `${text.slice(0, 24)}…` : text}
          </div>
        ))}
      </div>
      <div style={{ position: 'absolute', left: 64, top: 52, fontFamily: FONT, fontSize: 30, fontWeight: 800, color: C.label,
                    textTransform: 'uppercase', letterSpacing: 2 }}>{tx('recap')}</div>
    </AbsoluteFill>
  );
};

/** The rules of the system, numbered, one by one as the voice names them; the one switched off is struck out in red
 * (the key moment of a video: it stays on screen). */
const Rules: FC<{ graphic: SimGraphic; real: number }> = ({ graphic, real }) => {
  const from = graphic.rulesFrom ?? 0;
  const off = new Set(graphic.rulesOff ?? []);
  return (
    <Panel o={1} style={{ left: 64, top: 230, width: 470, padding: '20px 26px' }}>
      <Label>{tx('rulesTitle')}</Label>
      {(graphic.rules ?? []).map((r, i) => {
        const shown = i < from ? 1 : interpolate(real, [0.3 + (i - from) * 0.7, 0.7 + (i - from) * 0.7], [0, 1], clamp);
        const strike = r.off ? (off.has(i) ? interpolate(real, [0.6, 1.3], [0, 1], { ...clamp, easing: Easing.inOut(Easing.cubic) }) : 1) : 0;
        return (
          <div key={r.text} style={{ display: 'flex', alignItems: 'center', gap: 16, marginTop: 14, opacity: shown,
                                     transform: `translateX(${(1 - shown) * -20}px)` }}>
            <span style={{ width: 40, height: 40, borderRadius: 20, display: 'flex', alignItems: 'center', justifyContent: 'center',
                           fontSize: 24, fontWeight: 800, background: strike > 0.5 ? C.red : C.green, color: '#0b1020' }}>
              {strike > 0.5 ? '✕' : i + 1}
            </span>
            <span style={{ position: 'relative', fontSize: 30, fontWeight: 800, textTransform: 'uppercase',
                           color: strike > 0.5 ? 'rgba(242,244,248,0.45)' : C.text }}>
              {r.text}
              <span style={{ position: 'absolute', left: 0, top: '52%', height: 4, width: `${strike * 100}%`, background: C.red }} />
            </span>
          </div>
        );
      })}
    </Panel>
  );
};

/** The dial: a number of the world turned from its last value to this line's, the world reacting with it. */
const Dial: FC<{ dial: NonNullable<SimGraphic['dial']>; real: number }> = ({ dial, real }) => {
  const k = interpolate(real, [0.3, 1.6], [0, 1], { ...clamp, easing: Easing.inOut(Easing.cubic) });
  const value = dial.from + (dial.to - dial.from) * k;
  const span = Math.max(1e-9, dial.max - dial.min);
  const at = (v: number) => Math.max(0, Math.min(1, (v - dial.min) / span));
  const text = (v: number) => (dial.percent ? `${Math.round(v * 100)} %` : Math.abs(v) >= 10 || Number.isInteger(dial.to) ? String(Math.round(v)) : v.toFixed(2));
  const W = 420;
  return (
    <Panel o={interpolate(real, [0, 0.3], [0, 1], clamp)} style={{ right: 64, top: 52, width: W + 52 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <Label>{dial.label}</Label>
        <span style={{ fontSize: 44, fontWeight: 800, color: C.text, fontVariantNumeric: 'tabular-nums' }}>{text(value)}</span>
      </div>
      <div style={{ position: 'relative', height: 30, marginTop: 10 }}>
        <div style={{ position: 'absolute', left: 0, right: 0, top: 12, height: 6, borderRadius: 3, background: 'rgba(255,255,255,0.15)' }} />
        <div style={{ position: 'absolute', left: 0, width: at(value) * W, top: 12, height: 6, borderRadius: 3, background: C.you }} />
        <div style={{ position: 'absolute', left: at(dial.from) * W - 2, top: 6, width: 4, height: 18, background: 'rgba(255,255,255,0.35)' }} />
        <div style={{ position: 'absolute', left: at(value) * W - 14, top: 1, width: 28, height: 28, borderRadius: 14, background: C.you,
                      border: '3px solid #0b1020' }} />
      </div>
    </Panel>
  );
};

/** The key moment again (graphic.replay): the shot's own time, frozen, rewound and played at half speed, then catching
 * up so the next shot goes on where the world really is. Returns [time shown, phase]. */
export const replayTime = (local: number, length: number): [number, '' | 'pause' | 'rewind' | 'slow'] => {
  if (length < 5) return [local, ''];
  const key = Math.min(1.5, length * 0.3);
  const back = 2.4;
  const slowEnd = length - 0.7;
  if (local < key) return [local, ''];
  if (local < key + 0.9) return [key, 'pause'];
  if (local < key + 1.5) return [interpolate(local, [key + 0.9, key + 1.5], [key, key - back], {...clamp, easing: Easing.inOut(Easing.quad)}), 'rewind'];
  const slow = key - back + 0.5 * (Math.min(local, slowEnd) - key - 1.5);
  if (local < slowEnd) return [slow, 'slow'];
  return [interpolate(local, [slowEnd, length], [slow, length], clamp), ''];
};

export const SimScene: FC<{ graphic: SimGraphic; durationInFrames: number }> = ({ graphic, durationInFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const real = frame / fps;
  const length = durationInFrames / fps;
  const [local, phase] = graphic.replay ? replayTime(real, length) : [real, '' as const];
  const worldT = graphic.at + local - graphic.since;          // seconds since this world came on screen
  const move = interpolate(real, [0, 0.8], [0, 1], { ...clamp, easing: Easing.inOut(Easing.cubic) });
  const on = interpolate(real, [0, 0.35, length - 0.25, length], [0, 1, 1, 0.85], clamp);
  const o = (name: string) => (graphic.overlay === name ? on : 0);
  setLang(graphic.lang);
  setAccent(graphic.accent);
  setTheme(graphic.theme);
  const world = WORLDS[graphic.world] ?? WORLDS.cruces;
  const montage = !!(graphic.recap && graphic.recap.length > 0 && graphic.list.length > 0);
  const body = montage ? null : <world.View g={graphic} local={local} real={real} length={length} worldT={worldT} move={move} on={on} o={o} />;
  // the camera is never still: a slow breath in and out over the world's own clock (continuous from shot to shot);
  // a world comes in zooming from the last one and leaves zooming on (no blurred cut between two worlds)
  const breath = 1 + 0.035 * (0.5 - 0.5 * Math.cos((2 * Math.PI * (graphic.at + real - graphic.since)) / 26));
  const enter = graphic.enter ?? Math.abs(graphic.at - graphic.since) < 0.01;
  const zin = enter ? interpolate(real, [0, 0.55], [1.22, 1], { ...clamp, easing: Easing.out(Easing.cubic) }) : 1;
  const zout = graphic.exit ? interpolate(real, [length - 0.4, length], [1, 1.14], { ...clamp, easing: Easing.in(Easing.cubic) }) : 1;
  const dim = Math.max(enter ? interpolate(real, [0, 0.4], [0.55, 0], clamp) : 0,
                       graphic.exit ? interpolate(real, [length - 0.35, length], [0, 0.45], clamp) : 0);
  const statOn = graphic.statAt !== undefined
    ? interpolate(real, [graphic.statAt - 0.1, graphic.statAt + 0.25, length - 0.25, length], [0, 1, 1, 0.85], clamp) : on;
  const statFrom = graphic.statAt ?? 0.2;
  return (
    <AbsoluteFill>
      <AbsoluteFill style={{ transform: `scale(${breath * zin * zout})` }}>{body}</AbsoluteFill>
      {dim > 0 && <AbsoluteFill style={{ background: '#05080f', opacity: dim }} />}
      {phase !== '' && (
        <>
          {phase !== 'slow' && <AbsoluteFill style={{ background: 'rgba(5,8,15,0.25)' }} />}
          <div style={{ position: 'absolute', left: '50%', top: 150, transform: 'translateX(-50%)', fontFamily: FONT, fontSize: 52,
                        fontWeight: 800, letterSpacing: 2, color: phase === 'slow' ? C.text : C.accent, textTransform: 'uppercase',
                        background: C.panel, border: `2px solid ${C.accent}`, borderRadius: 10, padding: '8px 26px' }}>
            {phase === 'pause' ? `❚❚ ${tx('pause')}` : phase === 'rewind' ? `◀◀ ${tx('rewind')}` : tx('slowMo')}
          </div>
        </>
      )}
      {/* depth: the edges of every world a touch darker, the eye on the middle */}
      <AbsoluteFill style={{ background: 'radial-gradient(ellipse at 50% 50%, rgba(0,0,0,0) 58%, rgba(4,8,18,0.42) 100%)', pointerEvents: 'none' }} />
      {graphic.title && (
        <div style={{ position: 'absolute', left: 0, top: 96, width: 1920 }}>
          <Section text={graphic.title} o={on} f={frame} start={0} />
        </div>
      )}
      {graphic.legend && <Legend local={real} at={String(graphic.legend)} />}
      {graphic.rules && graphic.rules.length > 0 && <Rules graphic={graphic} real={real} />}
      {graphic.dial && <Dial dial={graphic.dial} real={real} />}
      {graphic.stat && (
        <Panel o={statOn} style={{ left: '50%', bottom: 70, transform: 'translateX(-50%)', textAlign: 'center', minWidth: 360 }}>
          <Label>{graphic.stat.label}</Label>
          <div style={{ fontSize: 64, fontWeight: 800, color: C.accent, lineHeight: 1.05, fontVariantNumeric: 'tabular-nums' }}>
            {countUp(graphic.stat.value, interpolate(real, [statFrom, statFrom + 0.9], [0, 1], { ...clamp, easing: Easing.out(Easing.cubic) }))}
          </div>
        </Panel>
      )}
      {graphic.source && (
        <div style={{ position: 'absolute', left: 48, bottom: 52, fontFamily: FONT, fontSize: 22, fontWeight: 700, letterSpacing: 1,
                      color: C.text, background: C.panel, border: `1px solid ${C.line}`, borderRadius: 4, padding: '5px 12px',
                      textTransform: 'uppercase', opacity: on }}>
          <span style={{ color: C.label }}>{tx('source')}:</span> {graphic.source}
        </div>
      )}
      {graphic.recap && graphic.recap.length > 0 && graphic.list.length > 0 && <Recap graphic={graphic} real={real} length={length} />}
      {graphic.list.length > 0 && !(graphic.recap && graphic.recap.length > 0) && (
        <>
          <AbsoluteFill style={{ background: C.night, opacity: 0.55 * on }} />
          <Panel o={on} style={{ left: '50%', top: '50%', transform: 'translate(-50%, -50%)', width: 780, padding: '28px 34px' }}>
            <Label color={C.accent}>{tx('recap')}</Label>
            {graphic.list.map((line, n) => {
              const shown = interpolate(real, [0.3 + n * 0.6, 0.6 + n * 0.6], [0, 1], clamp);
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
