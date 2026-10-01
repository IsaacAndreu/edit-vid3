import type { CSSProperties, FC, ReactNode } from 'react';
import { AbsoluteFill, Easing, interpolate, random, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { alpha, monoFamily, theme } from '../../theme';

const PAPER =
  "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='240' height='240'>" +
  "<filter id='p'><feTurbulence type='fractalNoise' baseFrequency='0.65' numOctaves='3' stitchTiles='stitch'/>" +
  "<feColorMatrix values='0 0 0 0 0.6  0 0 0 0 0.55  0 0 0 0 0.45  0 0 0 0.5 0'/></filter>" +
  "<rect width='100%' height='100%' filter='url(%23p)'/></svg>\")";

/** sport: a diagonal wipe in with a bounce, speed lines, diagonal stripes in a corner, a wipe out the other way. */
const Sport: FC<{ durationInFrames: number; seed: string; children: ReactNode }> = ({ durationInFrames, seed, children }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enter = spring({ frame, fps, config: { damping: 13, stiffness: 240 }, durationInFrames: 14 });
  const wipe = interpolate(frame, [0, 9], [-20, 125], { extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic) });
  const out = interpolate(frame, [durationInFrames - 8, durationInFrames], [-20, 125], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.in(Easing.cubic) });
  const clip = frame < durationInFrames - 8
    ? `polygon(0% 0%, ${wipe}% 0%, ${wipe - 18}% 100%, 0% 100%)`
    : `polygon(${out}% 0%, 100% 0%, 100% 100%, ${out - 18}% 100%)`;
  const lines = frame < 14 ? [0, 1, 2, 3, 4] : [];
  return (
    <AbsoluteFill>
      <AbsoluteFill style={{ clipPath: clip, transform: `translateX(${(1 - enter) * -70}px)` }}>{children}</AbsoluteFill>
      {lines.map((i) => {
        const y = 12 + random(`${seed}-l${i}`) * 76;
        const x = interpolate(frame, [0, 13], [-40, 140]) - i * 9;
        return (
          <div key={i} style={{
            position: 'absolute', top: `${y}%`, left: `${x}%`, width: `${18 + i * 6}%`, height: 6 + (i % 2) * 6,
            background: `linear-gradient(90deg, ${alpha(theme.accent, 0)} 0%, ${alpha(theme.accent, 0.9)} 100%)`,
            transform: 'skewX(-24deg)', opacity: interpolate(frame, [0, 4, 13], [0, 1, 0]),
          }} />
        );
      })}
      <div style={{
        position: 'absolute', right: 70, bottom: 60, width: 150, height: 28, opacity: 0.55 * enter,
        backgroundImage: `repeating-linear-gradient(115deg, ${theme.accent} 0 10px, transparent 10px 22px)`,
        clipPath: frame < durationInFrames - 8 ? undefined : `inset(0 0 0 ${out}%)`,
      }} />
    </AbsoluteFill>
  );
};

/** editorial: a slow fade up, paper texture, two thin magazine rules that draw from the centre, a soft fade out. */
const Editorial: FC<{ durationInFrames: number; children: ReactNode }> = ({ durationInFrames, children }) => {
  const frame = useCurrentFrame();
  const enter = interpolate(frame, [0, 16], [0, 1], { extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic) });
  const leave = interpolate(frame, [durationInFrames - 10, durationInFrames], [1, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const rule = interpolate(frame, [4, 24], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.inOut(Easing.cubic) });
  const ruleStyle: CSSProperties = { position: 'absolute', left: 110, right: 110, height: 2, backgroundColor: alpha(theme.text, 0.35), transform: `scaleX(${rule})` };
  return (
    <AbsoluteFill style={{ opacity: enter * leave }}>
      <AbsoluteFill style={{ transform: `translateY(${(1 - enter) * 26}px)` }}>{children}</AbsoluteFill>
      <AbsoluteFill style={{ backgroundImage: PAPER, opacity: 0.07, mixBlendMode: 'overlay', pointerEvents: 'none' }} />
      <div style={{ ...ruleStyle, top: 44 }} />
      <div style={{ ...ruleStyle, bottom: 44 }} />
    </AbsoluteFill>
  );
};

/** tech: a short glitch in (RGB split, jitter, flicker), corner brackets closing in, scanlines, a mono readout,
 * and a CRT switch-off at the end. */
const Tech: FC<{ durationInFrames: number; seed: string; children: ReactNode }> = ({ durationInFrames, seed, children }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const glitch = frame < 7;
  const jitter = glitch ? (random(`${seed}-j${frame}`) - 0.5) * 26 : 0;
  const flicker = glitch ? [0.2, 1, 0.45, 1, 0.7, 1, 1][frame] : 1;
  const close = interpolate(frame, [0, 11], [70, 0], { extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic) });
  const off = interpolate(frame, [durationInFrames - 8, durationInFrames - 2], [1, 0.012], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const offFade = interpolate(frame, [durationInFrames - 3, durationInFrames], [1, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const bracket = (corner: 'tl' | 'tr' | 'bl' | 'br'): CSSProperties => {
    const top = corner[0] === 't';
    const left = corner[1] === 'l';
    return {
      position: 'absolute', width: 70, height: 70, borderColor: theme.accent, borderStyle: 'solid', borderWidth: 0,
      [top ? 'borderTopWidth' : 'borderBottomWidth']: 5, [left ? 'borderLeftWidth' : 'borderRightWidth']: 5,
      [top ? 'top' : 'bottom']: 40 - close, [left ? 'left' : 'right']: 60 - close,
    } as CSSProperties;
  };
  const seconds = (frame / fps).toFixed(1).padStart(4, '0');
  return (
    <AbsoluteFill style={{ transform: `scaleY(${off})`, opacity: offFade, filter: off < 1 ? `brightness(${1 + (1 - off) * 1.5})` : undefined }}>
      <AbsoluteFill style={{
        transform: `translateX(${jitter}px)`, opacity: flicker,
        filter: glitch ? 'drop-shadow(6px 0 0 rgba(255,0,70,0.75)) drop-shadow(-6px 0 0 rgba(0,230,255,0.75))' : undefined,
      }}>
        {children}
      </AbsoluteFill>
      <AbsoluteFill style={{
        pointerEvents: 'none', opacity: 0.5,
        backgroundImage: 'repeating-linear-gradient(0deg, rgba(255,255,255,0.05) 0 1px, transparent 1px 4px)',
      }} />
      <div style={bracket('tl')} />
      <div style={bracket('tr')} />
      <div style={bracket('bl')} />
      <div style={bracket('br')} />
      <div style={{
        position: 'absolute', left: 140, bottom: 50, fontFamily: monoFamily, fontWeight: 500, fontSize: 22,
        letterSpacing: '0.12em', color: alpha(theme.text, 0.6),
      }}>
        {`● REC  T+${seconds}  //  ${seed.toUpperCase().slice(0, 12)}`}
      </div>
    </AbsoluteFill>
  );
};

/** The channel's way of bringing a graphic in and out (brand.motion), around any graphic. */
export const GraphicFrame: FC<{ durationInFrames: number; seed: string; children: ReactNode }> = ({ durationInFrames, seed, children }) => {
  switch (theme.motion) {
    case 'sport':
      return <Sport durationInFrames={durationInFrames} seed={seed}>{children}</Sport>;
    case 'editorial':
      return <Editorial durationInFrames={durationInFrames}>{children}</Editorial>;
    case 'tech':
      return <Tech durationInFrames={durationInFrames} seed={seed}>{children}</Tech>;
    default:
      return <>{children}</>;
  }
};
