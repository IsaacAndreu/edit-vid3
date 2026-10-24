import type { CSSProperties, FC } from 'react';
import { AbsoluteFill, Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';
import type { NewsGraphic } from '../../graphics';
import { Grain, GridPaper, typed, Vignette } from './Paper';

const YELLOW = '#f4d81c';

const highlighter = (percent: number): CSSProperties => ({
  backgroundImage: `linear-gradient(${YELLOW}, ${YELLOW})`,
  backgroundRepeat: 'no-repeat',
  backgroundSize: `${percent}% 100%`,
  boxDecorationBreak: 'clone',
  WebkitBoxDecorationBreak: 'clone',
  padding: '0 6px',
});

/** A news item on squared paper: red date tag, the headline typed and then swept with a highlighter, the line
 * under it, the newspaper's name in blackletter (only if the script names it) and the person cut out in black and
 * white on the right. */
export const News: FC<{ graphic: NewsGraphic; durationInFrames: number }> = ({ graphic, durationInFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const speed = Math.max(1, graphic.headline.length / Math.max(16, durationInFrames * 0.28));
  const head = typed(graphic.headline, frame, 8, speed);
  const done = 8 + graphic.headline.length / speed;
  const body = interpolate(frame, [done, done + 8], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const sweepHead = interpolate(frame, [done + 6, done + 18], [0, 100], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const sweepBody = interpolate(frame, [done + 16, done + 30], [0, 100], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const mast = interpolate(frame, [done + 24, done + 34], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const tag = spring({ frame, fps, config: { damping: 18, stiffness: 200 } });
  const person = spring({ frame: frame - 12, fps, config: { damping: 200, stiffness: 70 } });
  const media = graphic.media;
  const cutout = media?.kind === 'image' && (media.layout === 'person' || media.src.toLowerCase().endsWith('.png'));
  const push = interpolate(frame, [0, durationInFrames], [1, 1.05]);
  const size = graphic.headline.length > 70 ? 74 : graphic.headline.length > 45 ? 86 : 100;
  return (
    <AbsoluteFill style={{ overflow: 'hidden' }}>
      <AbsoluteFill style={{ transform: `scale(${push})` }}>
        <GridPaper />
      </AbsoluteFill>
      {media && media.kind === 'image' ? (
        <div style={{ position: 'absolute', right: cutout ? 40 : 110, bottom: cutout ? 0 : 170, width: cutout ? 720 : 600, height: cutout ? 900 : 600,
          opacity: person, transform: `translateY(${(1 - person) * 60}px)` }}>
          <Img src={staticFile(media.src)} style={{ width: '100%', height: '100%', objectFit: cutout ? 'contain' : 'cover',
            objectPosition: cutout ? 'right bottom' : media.focus ? `${media.focus[0]}% ${media.focus[1]}%` : 'center 30%',
            filter: 'grayscale(1) contrast(1.12) brightness(1.02)',
            ...(cutout ? {} : { border: '14px solid #f3efe6', boxShadow: '0 16px 30px rgba(0,0,0,0.35)', transform: 'rotate(2deg)' }) }} />
        </div>
      ) : null}
      <div style={{ position: 'absolute', left: 100, top: 90, width: media ? 1080 : 1600 }}>
        {graphic.date ? (
          <div style={{ display: 'inline-block', background: '#d42a2a', color: '#fff', fontFamily: "'Inter'", fontWeight: 800, fontSize: 40,
            padding: '8px 18px', borderRadius: 4, transform: `scale(${tag})`, transformOrigin: 'left center', marginBottom: 22 }}>
            {graphic.date.toUpperCase()}
          </div>
        ) : null}
        <div style={{ fontFamily: "'Poppins'", fontWeight: 700, fontSize: size, lineHeight: 1.22, color: '#1d1c1a' }}>
          <span style={highlighter(sweepHead)}>{head}</span>
        </div>
        {graphic.body ? (
          <div style={{ marginTop: 70, maxWidth: 940, fontFamily: "'Inter'", fontWeight: 500, fontSize: 40, lineHeight: 1.45, color: '#2b2925', opacity: body }}>
            <span style={highlighter(sweepBody)}>{graphic.body}</span>
          </div>
        ) : null}
      </div>
      {graphic.outlet ? (
        <div style={{ position: 'absolute', left: 110, bottom: 90, display: 'flex', alignItems: 'center', gap: 26, opacity: mast }}>
          <div style={{ width: 300 * mast, height: 3, background: '#2a2826' }} />
          <div style={{ fontFamily: "'UnifrakturMaguntia'", fontSize: 72, color: '#1d1c1a' }}>{graphic.outlet}</div>
        </div>
      ) : null}
      <Vignette strength={0.5} />
      <Grain opacity={0.18} id="news-grain" />
    </AbsoluteFill>
  );
};
