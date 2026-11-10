import type { FC } from 'react';
import { AbsoluteFill, Easing, Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';
import type { PosterGraphic } from '../../graphics';
import { Grain, Stars } from './Paper';

const RED = '#d4161c';
const GOLD = '#e3a535';
const IMG_H = 860; // the cutout's height on screen

/** A propaganda-poster portrait: black night, a big red sun, the person rising in black and white from the mist,
 * a red bar slamming over their eyes with a glitch; then they slide aside for 2-4 words, or one huge word sits
 * behind their head. */
export const Poster: FC<{ graphic: PosterGraphic; durationInFrames: number }> = ({ graphic, durationInFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const sun = spring({ frame, fps, config: { damping: 14, stiffness: 120 } });
  const rise = spring({ frame: frame - 8, fps, config: { damping: 200, stiffness: 60 } });
  const barAt = 30;
  const bar = interpolate(frame, [barAt, barAt + 4], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const glitch = frame >= barAt && frame < barAt + 8 ? (frame % 2 ? 9 : -7) : 0;
  const words = graphic.words || [];
  const aside = words.length ? interpolate(frame, [barAt + 14, barAt + 30], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.inOut(Easing.cubic) }) : 0;
  const shift = -440 * aside;
  const big = graphic.big ? spring({ frame: frame - (barAt + 10), fps, config: { damping: 16, stiffness: 160 } }) : 0;
  const media = graphic.media;
  const focus = media?.focus;
  const push = interpolate(frame, [0, durationInFrames], [1, 1.05]);
  const each = Math.max(8, Math.min(16, Math.floor((durationInFrames - barAt - 34) / Math.max(1, words.length))));

  const person = (dx: number, tint: string | null) =>
    media ? (
      <div style={{ position: 'absolute', left: 960 + shift + dx, bottom: 0, height: IMG_H, transform: `translateX(-50%) translateY(${(1 - rise) * 260}px)`,
        opacity: tint ? 0.55 : rise, mixBlendMode: tint ? 'screen' : 'normal' }}>
        <div style={{ position: 'relative', height: '100%' }}>
          <Img src={staticFile(media.src)} style={{ height: '100%', width: 'auto', display: 'block',
            filter: tint ? `grayscale(1) brightness(1.1) drop-shadow(0 0 0 ${tint}) sepia(1) hue-rotate(${tint === 'red' ? '-50deg' : '150deg'})` : 'grayscale(1) contrast(1.15)' }} />
          {focus ? (
            <div style={{ position: 'absolute', left: `${focus[0] - 15}%`, width: '30%', top: `${focus[1] - 4.5}%`, height: '5.5%', background: RED,
              opacity: bar, transform: `scaleX(${0.4 + 0.6 * bar})`, boxShadow: '0 0 12px rgba(212,22,28,0.6)' }} />
          ) : null}
        </div>
      </div>
    ) : null;

  return (
    <AbsoluteFill style={{ overflow: 'hidden' }}>
      <Stars />
      <AbsoluteFill style={{ transform: `scale(${push})` }}>
        <div style={{ position: 'absolute', left: 960 + shift - 330, top: 150, width: 660, height: 660, borderRadius: '50%',
          background: `radial-gradient(circle at 45% 40%, #e3262c 0%, ${RED} 55%, #a50f14 100%)`, transform: `scale(${sun})`,
          boxShadow: '0 0 90px rgba(212,22,28,0.55)' }} />
        {graphic.big ? (
          <div style={{ position: 'absolute', left: 960 + shift, top: 250, transform: `translateX(-50%) scale(${0.6 + 0.4 * big})`, opacity: big,
            fontFamily: "'Poppins'", fontWeight: 700, fontSize: 300, lineHeight: 1, color: '#fff', letterSpacing: -6, whiteSpace: 'nowrap' }}>
            {graphic.big.toUpperCase()}
          </div>
        ) : null}
        {glitch ? person(glitch, 'red') : null}
        {glitch ? person(-glitch, 'cyan') : null}
        {person(0, null)}
        {/* the mist the person rises from */}
        <div style={{ position: 'absolute', left: -200, right: -200, bottom: -260, height: 520, borderRadius: '50%',
          background: 'radial-gradient(ellipse at 50% 40%, rgba(235,235,235,0.85) 0%, rgba(160,160,160,0.35) 45%, rgba(0,0,0,0) 70%)', filter: 'blur(20px)' }} />
      </AbsoluteFill>
      <div style={{ position: 'absolute', left: 1000, top: 200, opacity: aside }}>
        {words.map((w, i) => {
          const at = barAt + 26 + i * each;
          const o = interpolate(frame, [at, at + 8], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
          return (
            <div key={i} style={{ fontFamily: "'Cinzel'", fontWeight: 700, fontSize: 112, color: GOLD, letterSpacing: 4, marginLeft: (i % 2) * 90,
              marginBottom: 26, opacity: o, transform: `translateX(${(1 - o) * 30}px)`, textShadow: '0 4px 18px rgba(0,0,0,0.6)' }}>
              {w.toUpperCase()}
            </div>
          );
        })}
      </div>
      <Grain opacity={0.2} id="poster-grain" />
    </AbsoluteFill>
  );
};
