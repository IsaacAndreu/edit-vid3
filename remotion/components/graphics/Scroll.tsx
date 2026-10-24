import type { FC } from 'react';
import { AbsoluteFill, Easing, interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import type { ScrollGraphic } from '../../graphics';
import { Grain, rand, Vignette, Wood } from './Paper';

const PW = 1120; // the parchment
const PH = 660;

/** Burnt, uneven edge of the parchment (a polygon with small random bites), in % of its box. */
const edge = (() => {
  const pts: string[] = [];
  const n = 28;
  for (let i = 0; i <= n; i++) pts.push(`${(i / n) * 100}% ${1 + rand(i) * 3}%`);
  for (let i = 0; i <= n * 0.6; i++) pts.push(`${98 - rand(i + 40) * 2.5}% ${(i / (n * 0.6)) * 100}%`);
  for (let i = n; i >= 0; i--) pts.push(`${(i / n) * 100}% ${97 - rand(i + 80) * 3}%`);
  for (let i = Math.floor(n * 0.6); i >= 0; i--) pts.push(`${1 + rand(i + 120) * 2.5}% ${(i / (n * 0.6)) * 100}%`);
  return `polygon(${pts.join(', ')})`;
})();

/** A rolled parchment on a wooden table unrolls downwards; a title is written on it word by word, an ornament
 * draws itself under it and then the place and year. A chapter of someone's life, the old-fashioned way. */
export const Scroll: FC<{ graphic: ScrollGraphic; durationInFrames: number; quick?: boolean }> = ({ graphic, durationInFrames, quick }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const roll = spring({ frame, fps, config: { damping: 200, stiffness: 120 } });
  const t0 = quick ? 18 : 36; // when the first word is written (a chapter card has less time)
  const open = interpolate(frame, quick ? [4, 18] : [10, 34], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic) });
  const words = graphic.title.split(/\s+/).filter(Boolean);
  const each = Math.max(3, Math.min(8, Math.floor((durationInFrames * 0.35) / Math.max(1, words.length))));
  const titleEnd = t0 + words.length * each;
  const line = interpolate(frame, [titleEnd, titleEnd + 16], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const sub = interpolate(frame, [titleEnd + 12, titleEnd + 24], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const push = interpolate(frame, [0, durationInFrames], [1, 1.06]);
  const left = 960 - PW / 2;
  const top = 540 - PH / 2;
  const size = graphic.title.length > 28 ? 64 : 80;
  return (
    <AbsoluteFill style={{ overflow: 'hidden' }}>
      <Wood />
      <AbsoluteFill style={{ transform: `scale(${push})` }}>
        {/* the parchment, shown from the top as it unrolls */}
        <div style={{ position: 'absolute', left, top, width: PW, height: PH, clipPath: `inset(0 0 ${(1 - open) * 100}% 0)`,
          filter: 'drop-shadow(0 18px 24px rgba(0,0,0,0.55))', transform: 'rotate(-0.8deg)' }}>
          <div style={{ position: 'absolute', inset: 0, clipPath: edge,
            background: 'radial-gradient(ellipse at 50% 45%, #efdcb2 0%, #e2c58f 55%, #b98d4f 92%, #6e4a22 100%)' }}>
            <AbsoluteFill style={{ background: 'linear-gradient(90deg, rgba(90,60,20,0.18), rgba(0,0,0,0) 20%, rgba(0,0,0,0) 80%, rgba(90,60,20,0.2))' }} />
            <AbsoluteFill style={{ background: 'linear-gradient(180deg, rgba(0,0,0,0) 48%, rgba(80,50,20,0.12) 50%, rgba(0,0,0,0) 52%)' }} />
            <div style={{ position: 'absolute', left: 70, right: 70, top: 140, textAlign: 'center', fontFamily: "'Cinzel'", fontWeight: 600,
              fontSize: size, lineHeight: 1.18, color: '#4a3320', letterSpacing: 1 }}>
              {words.map((w, i) => (
                <span key={i} style={{ opacity: interpolate(frame, [t0 + i * each, t0 + i * each + 6], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }), marginRight: '0.3em' }}>
                  {w}
                </span>
              ))}
            </div>
            <svg width={PW} height={40} style={{ position: 'absolute', left: 0, top: 380 }}>
              <g opacity={line} stroke="#5a4028" fill="none" strokeWidth={2}>
                <line x1={PW / 2 - 250 * line} y1={20} x2={PW / 2 - 14} y2={20} />
                <line x1={PW / 2 + 14} y1={20} x2={PW / 2 + 250 * line} y2={20} />
                <circle cx={PW / 2 - 256 * line} cy={20} r={4} />
                <circle cx={PW / 2 + 256 * line} cy={20} r={4} />
                <path d={`M ${PW / 2 - 9} 20 L ${PW / 2} 11 L ${PW / 2 + 9} 20 L ${PW / 2} 29 Z`} fill="#5a4028" />
              </g>
            </svg>
            {graphic.subtitle ? (
              <div style={{ position: 'absolute', left: 0, right: 0, top: 440, textAlign: 'center', fontFamily: "'DM Serif Display', Georgia, serif",
                fontSize: 42, color: '#5a4028', opacity: sub }}>
                {graphic.subtitle}
              </div>
            ) : null}
          </div>
        </div>
        {/* the roller, carried down while it unrolls, gone once open */}
        <div style={{ position: 'absolute', left: left - 30, width: PW + 60, height: 34, top: top - 18 + open * PH, borderRadius: 17,
          opacity: roll * (1 - interpolate(open, [0.85, 1], [0, 1], { extrapolateLeft: 'clamp' })),
          background: 'linear-gradient(180deg, #f3dfb4 0%, #d8b77c 40%, #9c7440 85%, #6d4d27 100%)', boxShadow: '0 10px 18px rgba(0,0,0,0.5)' }} />
      </AbsoluteFill>
      <Vignette strength={0.7} />
      <Grain opacity={0.16} id="scroll-grain" />
    </AbsoluteFill>
  );
};
