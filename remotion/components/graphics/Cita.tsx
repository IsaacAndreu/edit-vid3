import type { CSSProperties, FC } from 'react';
import { AbsoluteFill, Img, OffthreadVideo, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';
import { fontFamily, theme } from '../../theme';
import type { CitaGraphic } from '../../graphics';

const RED = '#e3262f';

/** A quote card: black screen, the speaker in black and white on the left fading into the dark, and their words
 * big on the right, appearing word by word, the key words in red. */
export const Cita: FC<{ graphic: CitaGraphic; durationInFrames: number }> = ({ graphic, durationInFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enter = spring({ frame, fps, config: { damping: 200, stiffness: 90 } });
  const push = interpolate(frame, [0, durationInFrames], [1.0, 1.08]);
  const media = graphic.media;
  const cutout = media?.kind === 'image' && (media.layout === 'person' || media.src.toLowerCase().endsWith('.png'));
  const picture: CSSProperties = {
    width: '100%',
    height: '100%',
    objectFit: cutout ? 'contain' : 'cover',
    objectPosition: cutout ? 'center bottom' : media?.focus ? `${media.focus[0]}% ${media.focus[1]}%` : 'center 30%',
    transform: `scale(${push})`,
    filter: 'grayscale(1) contrast(1.1)',
  };
  const red = new Set((graphic.highlight || []).flatMap((h) => h.toLowerCase().split(/\s+/)).map((w) => w.replace(/[^\p{L}\p{N}]/gu, '')));
  const words = graphic.text.split(/\s+/).filter(Boolean);
  const gap = Math.max(2, Math.min(6, Math.floor((durationInFrames * 0.45) / Math.max(1, words.length))));
  const size = words.length > 22 ? 58 : words.length > 14 ? 68 : 80;
  return (
    <AbsoluteFill style={{ backgroundColor: '#000', overflow: 'hidden' }}>
      {media ? (
        <div style={{ position: 'absolute', left: 0, top: 0, width: 820, height: 1080, opacity: enter }}>
          {media.kind === 'video' ? (
            <OffthreadVideo src={staticFile(media.src)} muted style={picture} />
          ) : (
            <Img src={staticFile(media.src)} style={picture} />
          )}
          <AbsoluteFill style={{ background: 'linear-gradient(90deg, rgba(0,0,0,0) 55%, #000 100%)' }} />
        </div>
      ) : null}
      <div
        style={{
          position: 'absolute',
          left: media ? 860 : 220,
          right: media ? 110 : 220,
          top: 0,
          bottom: 0,
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          alignItems: media ? 'flex-start' : 'center',
          textAlign: media ? 'left' : 'center',
        }}
      >
        <div style={{ fontFamily, fontWeight: 900, fontSize: size, lineHeight: 1.12, color: theme.text, letterSpacing: '-0.01em' }}>
          {words.map((w, i) => {
            const pop = spring({ frame: frame - 6 - i * gap, fps, config: { damping: 18, stiffness: 170 } });
            const lit = red.has(w.toLowerCase().replace(/[^\p{L}\p{N}]/gu, ''));
            return (
              <span
                key={i}
                style={{
                  display: 'inline-block',
                  marginRight: '0.28em',
                  color: lit ? RED : theme.text,
                  opacity: Math.min(1, pop * 1.5),
                  transform: `translateY(${(1 - pop) * 24}px)`,
                }}
              >
                {i === 0 ? '«' : ''}
                {w}
                {i === words.length - 1 ? '»' : ''}
              </span>
            );
          })}
        </div>
        {graphic.speaker ? (
          <div
            style={{
              marginTop: 36,
              fontFamily,
              fontWeight: 700,
              fontSize: 34,
              letterSpacing: 2,
              color: 'rgba(255,255,255,0.75)',
              opacity: interpolate(frame, [12 + words.length * gap, 22 + words.length * gap], [0, 1], {
                extrapolateLeft: 'clamp',
                extrapolateRight: 'clamp',
              }),
            }}
          >
            — {graphic.speaker.toUpperCase()}
          </div>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};
