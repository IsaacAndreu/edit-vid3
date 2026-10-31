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
import { addWords, num, setLang, tx } from '../../sim/i18n';
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
  const world = WORLDS[graphic.world];
  const own = world?.sounds?.(graphic, length) ?? {};
  const hold = graphic.askHold ?? 0;
  const holdFrom = length - hold;
  const ticks = [...(graphic.overlay !== 'none' || graphic.stat ? [0.35] : []), ...(own.ticks ?? []),
                 ...(hold > 0 ? [holdFrom + 0.4, holdFrom + 1.4, holdFrom + 2.4].filter((s) => s < length - 0.1) : [])]
    .filter((s) => hold <= 0 || s < holdFrom || s >= holdFrom + 0.3).sort((a, b) => a - b);
  // a hit on the key moments: the replay's freeze, a rule switched off, the question, the opening and its cut
  const hits = [...(own.hits ?? []), ...(graphic.replay && length >= 5 ? [Math.min(1.5, length * 0.3)] : []),
                ...(graphic.rulesOff && graphic.rulesOff.length > 0 ? [0.6] : []), ...(hold > 0 ? [holdFrom] : []),
                ...(graphic.teaser ? [0.05, length - 0.12] : [])].filter((s) => s >= 0 && s < length).sort((a, b) => a - b);
  const clicks = (own.clicks ?? []).filter((s) => hold <= 0 || s < holdFrom);
  const beeps = (own.beeps ?? []).filter((s) => hold <= 0 || s < holdFrom);
  const dings = (own.dings ?? []).filter((s) => hold <= 0 || s < holdFrom);
  const place = world?.ambient ?? 'ambient';
  const ambient = place === 'none' ? undefined : sounds[place] ?? sounds.ambient;
  const level = place === 'rain' ? 0.24 : place === 'crowd' ? 0.32 : place === 'murmur' ? 0.4 : place === 'kitchen' ? 0.26 : 0.35;
  const loop = 20 * fps;
  const at = (list: number[], src: string | undefined, key: string, volume: number, frames = 8) => src
    ? list.filter((s, i) => i === 0 || s - list[i - 1] > 0.12).map((s) => (
      <Sequence key={`${key}${s}`} from={Math.round(s * fps)} durationInFrames={frames}><Audio src={staticFile(src)} volume={volume} /></Sequence>))
    : null;
  return (
    <>
      {ambient && <Audio src={staticFile(ambient)} loop volume={(f) => level * (hold > 0 && f / fps >= holdFrom ? 0.35 : 1)}
                         startFrom={Math.round(t0 * fps) % loop} />}
      {at(clicks, sounds.click, 'c', 0.32, 6)}
      {at(ticks.filter((s, i) => i === 0 || s - ticks[i - 1] > 0.25), sounds.tick, 't', 0.22, 6)}
      {at(beeps, sounds.beep, 'b', 0.16, 6)}
      {at(dings, sounds.ding, 'd', 0.3, Math.round(1.3 * fps))}
      {at(hits, sounds.impact, 'h', 0.45, Math.round(1.1 * fps))}
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
  teaser: {es: 'En este vídeo', pt: 'Neste vídeo', fr: 'Dans cette vidéo', de: 'In diesem Video', en: 'In this video'},
  youDecide: {es: '¿Tú qué harías?', pt: 'E você, o que faria?', fr: 'Et toi, tu ferais quoi ?', de: 'Was würdest du tun?', en: 'What would you do?'},
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
  const text = (v: number) => (dial.percent ? `${Math.round(v * 100)} %` : Math.abs(v) >= 10 || Number.isInteger(dial.to) ? num(Math.round(v)) : num(v, 2));
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

/** The opening (graphic.teaser): the strongest moment of the video, framed as a preview — black bands, a tag, and a
 * white flash into the voice's hook. */
const Teaser: FC<{ real: number; length: number }> = ({ real, length }) => {
  const bands = interpolate(real, [0, 0.4, length - 0.3, length], [0, 1, 1, 0], clamp);
  const flash = interpolate(real, [length - 0.25, length - 0.08, length], [0, 0.9, 0], clamp);
  const tag = interpolate(real, [0.2, 0.6], [0, 1], clamp);
  return (
    <>
      <div style={{ position: 'absolute', left: 0, right: 0, top: 0, height: 90 * bands, background: '#000' }} />
      <div style={{ position: 'absolute', left: 0, right: 0, bottom: 0, height: 90 * bands, background: '#000' }} />
      <div style={{ position: 'absolute', left: 64, top: 120, display: 'flex', alignItems: 'center', gap: 12, fontFamily: FONT, fontSize: 30,
                    fontWeight: 800, letterSpacing: 2, textTransform: 'uppercase', color: C.text, opacity: tag,
                    background: C.panel, border: `2px solid ${C.accent}`, borderRadius: 8, padding: '6px 18px' }}>
        <span style={{ width: 14, height: 14, borderRadius: 7, background: C.red, opacity: 0.5 + 0.5 * Math.round((real * 2) % 1) }} />
        {tx('teaser')}
      </div>
      {flash > 0 && <AbsoluteFill style={{ background: '#fff', opacity: flash }} />}
    </>
  );
};

/** «¿Tú qué harías?»: the world frozen, the question in the middle and a 3-2-1 that runs out before the answer. */
const Ask: FC<{ question: string; real: number; hold: number; o: number }> = ({ question, real, hold, o }) => {
  const left = Math.max(1, Math.ceil(hold - real));
  const ring = Math.max(0, Math.min(1, real / Math.max(0.1, hold)));
  const pop = interpolate(real % 1, [0, 0.15], [1.25, 1], clamp);
  return (
    <>
      <AbsoluteFill style={{ background: 'rgba(5,8,15,0.5)', opacity: o }} />
      <div style={{ position: 'absolute', left: 0, right: 0, top: '30%', textAlign: 'center', fontFamily: FONT, opacity: o,
                    transform: `translateY(${(1 - o) * 20}px)` }}>
        <div style={{ fontSize: 34, fontWeight: 800, letterSpacing: 3, color: C.you, textTransform: 'uppercase' }}>{tx('youDecide')}</div>
        <div style={{ fontSize: 76, fontWeight: 800, color: C.text, textTransform: 'uppercase', marginTop: 10, padding: '0 120px',
                      textShadow: '0 4px 18px rgba(0,0,0,0.7)' }}>{question}</div>
        <svg width={150} height={150} style={{ marginTop: 26 }}>
          <circle cx={75} cy={75} r={62} fill="rgba(11,16,32,0.8)" stroke="rgba(255,255,255,0.15)" strokeWidth={8} />
          <circle cx={75} cy={75} r={62} fill="none" stroke={C.you} strokeWidth={8} strokeLinecap="round"
                  strokeDasharray={`${2 * Math.PI * 62}`} strokeDashoffset={`${2 * Math.PI * 62 * ring}`} transform="rotate(-90 75 75)" />
          <text x={75} y={98} textAnchor="middle" fontFamily={FONT} fontSize={68 * pop} fontWeight={800} fill={C.text}>{left}</text>
        </svg>
      </div>
    </>
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
  const hold = graphic.askHold ?? 0;
  const holdFrom = length - hold;
  const [played, phase] = graphic.replay && !hold ? replayTime(real, length) : [real, '' as const];
  const local = hold > 0 ? Math.min(played, holdFrom) : played;   // «¿tú qué harías?»: the world stops on the question
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
  const asking = hold > 0 ? interpolate(real, [holdFrom, holdFrom + 0.3], [0, 1], clamp) : 0;
  const loop = graphic.loopTo;
  const back = loop ? interpolate(real, [length - 0.7, length], [0, 1], clamp) : 0;
  return (
    <AbsoluteFill>
      <AbsoluteFill style={{ transform: `scale(${breath * zin * zout * (graphic.teaser ? 1.06 : 1)})` }}>{body}</AbsoluteFill>
      {loop && back > 0 && (
        // a Short ends on its first scene: watched again, it does not jump
        <AbsoluteFill style={{ opacity: back }}>
          {(() => { const first = WORLDS[loop.world] ?? WORLDS.cruces;
            return <first.View g={loop} local={0} real={0} length={length} worldT={loop.at - loop.since} move={1} on={0} o={() => 0} />; })()}
        </AbsoluteFill>
      )}
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
      {graphic.teaser && <Teaser real={real} length={length} />}
      {asking > 0 && graphic.ask && <Ask question={graphic.ask} real={real - holdFrom} hold={hold} o={asking} />}
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
