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
import { setLang, tx } from '../../sim/i18n';
import { WORLDS } from '../../sim/registry';
import { clamp } from '../../sim/world';

// --- sound: the street's hum under every shot of a world (continuing where the last shot left it), the world's clicks
// (a light changing in sight…), a soft tick when a panel comes in and on the world's own events (a car stopping…)
const SimSounds: FC<{ graphic: SimGraphic; durationInFrames: number; fps: number }> = ({ graphic, durationInFrames, fps }) => {
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
export const SimScene: FC<{ graphic: SimGraphic; durationInFrames: number }> = ({ graphic, durationInFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const local = frame / fps;
  const length = durationInFrames / fps;
  const worldT = graphic.at + local - graphic.since;          // seconds since this world came on screen
  const move = interpolate(local, [0, 0.8], [0, 1], { ...clamp, easing: Easing.inOut(Easing.cubic) });
  const on = interpolate(local, [0, 0.35, length - 0.25, length], [0, 1, 1, 0.85], clamp);
  const o = (name: string) => (graphic.overlay === name ? on : 0);
  setLang(graphic.lang);
  setAccent(graphic.accent);
  setTheme(graphic.theme);
  const world = WORLDS[graphic.world] ?? WORLDS.cruces;
  const body = <world.View g={graphic} local={local} length={length} worldT={worldT} move={move} on={on} o={o} />;
  // a small zoom punch only when a world comes on screen (a real cut): a panel coming in, or the camera moving to the
  // other side, already says «new line» — a punch on top of them jarred
  const cut = Math.abs(graphic.at - graphic.since) < 0.01;
  const punch = cut ? 1 + 0.03 * Math.sin(Math.PI * Math.min(1, local / 0.5)) : 1;
  return (
    <AbsoluteFill>
      <AbsoluteFill style={{ transform: `scale(${punch})` }}>{body}</AbsoluteFill>
      {/* depth: the edges of every world a touch darker, the eye on the middle */}
      <AbsoluteFill style={{ background: 'radial-gradient(ellipse at 50% 50%, rgba(0,0,0,0) 58%, rgba(4,8,18,0.42) 100%)', pointerEvents: 'none' }} />
      <SimSounds graphic={graphic} durationInFrames={durationInFrames} fps={fps} />
      {graphic.title && (
        <div style={{ position: 'absolute', left: 0, top: 96, width: 1920 }}>
          <Section text={graphic.title} o={on} f={frame} start={0} />
        </div>
      )}
      {graphic.stat && (
        <Panel o={on} style={{ left: '50%', bottom: 70, transform: 'translateX(-50%)', textAlign: 'center', minWidth: 360 }}>
          <Label>{graphic.stat.label}</Label>
          <div style={{ fontSize: 64, fontWeight: 800, color: C.accent, lineHeight: 1.05, fontVariantNumeric: 'tabular-nums' }}>
            {countUp(graphic.stat.value, interpolate(local, [0.2, 1.1], [0, 1], { ...clamp, easing: Easing.out(Easing.cubic) }))}
          </div>
        </Panel>
      )}
      {graphic.source && (
        <div style={{ position: 'absolute', left: 48, bottom: 52, fontFamily: FONT, fontSize: 18, fontWeight: 700, letterSpacing: 1,
                      color: C.text, background: C.panel, border: `1px solid ${C.line}`, borderRadius: 4, padding: '5px 12px',
                      textTransform: 'uppercase', opacity: on }}>
          <span style={{ color: C.label }}>{tx('source')}:</span> {graphic.source}
        </div>
      )}
      {graphic.list.length > 0 && (
        <>
          <AbsoluteFill style={{ background: C.night, opacity: 0.55 * on }} />
          <Panel o={on} style={{ left: '50%', top: '50%', transform: 'translate(-50%, -50%)', width: 780, padding: '28px 34px' }}>
            <Label color={C.accent}>{tx('recap')}</Label>
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
