import type { FC, ReactNode } from 'react';
import { AbsoluteFill, interpolate, random, useCurrentFrame } from 'remotion';

/**
 * Effects of one shot, chosen in the editor (edits.json → shot.fx): a colour grade or a look, blur, a vignette, film
 * grain and a camera move. Speed is not here: it is the clip's playback rate (media.rate). The render draws a shot with
 * effects in Remotion (pipeline/render.py), so the editor's player and the final video are the same.
 */
export interface ShotFx {
  look?: 'none' | 'bn' | 'sepia' | 'frio' | 'calido' | 'vintage' | 'dramatico' | null;
  brightness?: number | null; // 1 = as is
  contrast?: number | null;
  saturation?: number | null;
  temperature?: number | null; // -1 cold … 1 warm
  blur?: number | null; // px
  vignette?: number | null; // 0 … 1
  grain?: number | null; // 0 … 1
  move?: 'none' | 'in' | 'out' | 'left' | 'right' | null; // a slow push or pan over the shot
  durationInFrames?: number; // filled by Documentary: the shot's whole length (for the move)
}

const LOOKS: Record<string, string> = {
  bn: 'grayscale(1) contrast(1.12)',
  sepia: 'sepia(0.75) contrast(1.05) brightness(0.98)',
  frio: 'saturate(0.9) hue-rotate(-12deg) brightness(1.02)',
  calido: 'sepia(0.25) saturate(1.15) hue-rotate(-6deg)',
  vintage: 'sepia(0.4) contrast(0.9) saturate(0.8) brightness(1.06)',
  dramatico: 'contrast(1.35) saturate(0.75) brightness(0.92)',
};

export const fxFilter = (fx: ShotFx): string => {
  const parts: string[] = [];
  if (fx.look && LOOKS[fx.look]) parts.push(LOOKS[fx.look]);
  if (fx.brightness != null && fx.brightness !== 1) parts.push(`brightness(${fx.brightness})`);
  if (fx.contrast != null && fx.contrast !== 1) parts.push(`contrast(${fx.contrast})`);
  if (fx.saturation != null && fx.saturation !== 1) parts.push(`saturate(${fx.saturation})`);
  if (fx.temperature) parts.push(fx.temperature > 0 ? `sepia(${(0.35 * fx.temperature).toFixed(2)})` : `hue-rotate(${(-18 * fx.temperature).toFixed(1)}deg) saturate(${(1 + 0.1 * fx.temperature).toFixed(2)})`);
  if (fx.blur) parts.push(`blur(${fx.blur}px)`);
  return parts.join(' ');
};

const moveOf = (fx: ShotFx, frame: number): string => {
  if (!fx.move || fx.move === 'none') return '';
  const p = interpolate(frame, [0, Math.max(1, fx.durationInFrames ?? 1)], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  if (fx.move === 'in') return `scale(${1 + 0.12 * p})`;
  if (fx.move === 'out') return `scale(${1.12 - 0.12 * p})`;
  const dx = (fx.move === 'left' ? -1 : 1) * 4 * (p - 0.5);
  return `scale(1.1) translateX(${dx.toFixed(2)}%)`;
};

/** Film grain: a fresh noise pattern every frame, deterministic for the render. */
const Grain: FC<{ amount: number }> = ({ amount }) => {
  const frame = useCurrentFrame();
  const seed = Math.floor(random(`grain-${frame}`) * 1000);
  return (
    <AbsoluteFill style={{ opacity: Math.min(0.5, 0.35 * amount), mixBlendMode: 'overlay', pointerEvents: 'none' }}>
      <svg width="100%" height="100%" aria-hidden>
        <filter id={`fxg-${seed}`}><feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves={2} seed={seed} /></filter>
        <rect width="100%" height="100%" filter={`url(#fxg-${seed})`} />
      </svg>
    </AbsoluteFill>
  );
};

export const hasFx = (fx?: ShotFx | null): boolean =>
  !!fx && !!(fxFilter(fx) || fx.vignette || fx.grain || (fx.move && fx.move !== 'none'));

export const ShotFxLayer: FC<{ fx?: ShotFx | null; children: ReactNode }> = ({ fx, children }) => {
  const frame = useCurrentFrame();
  if (!fx || !hasFx(fx)) return <>{children}</>;
  const filter = fxFilter(fx), transform = moveOf(fx, frame);
  return (
    <AbsoluteFill style={{ overflow: 'hidden' }}>
      <AbsoluteFill style={{ filter: filter || undefined, transform: transform || undefined }}>{children}</AbsoluteFill>
      {fx.vignette ? (
        <AbsoluteFill style={{ background: `radial-gradient(ellipse at center, rgba(0,0,0,0) 45%, rgba(0,0,0,${Math.min(0.9, 0.85 * fx.vignette).toFixed(2)}) 100%)` }} />
      ) : null}
      {fx.grain ? <Grain amount={fx.grain} /> : null}
    </AbsoluteFill>
  );
};
