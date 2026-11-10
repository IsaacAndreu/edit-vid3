import type { FC } from 'react';
import { AbsoluteFill, Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';
import { alpha, fontFamily, theme } from '../../theme';
import type { CardGraphic } from '../../graphics';
import { GridBackground } from '../GridBackground';
import { MediaBox } from './MediaBox';

export const CARD_LANDS = 18; // keep in sync with pipeline/timeline.py
const CARD = { w: 620, h: 900 };

/** Video-game player card: it spins in, lands with a flash, a holographic shine sweeps across and
 * the stats pop in one by one. Cutouts stand on the card; photos and clips fill the top half. */
export const PlayerCard: FC<{ graphic: CardGraphic; durationInFrames: number }> = ({ graphic, durationInFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const spin = spring({ frame, fps, config: { damping: 14, stiffness: 70 }, durationInFrames: CARD_LANDS });
  const shine = interpolate(frame, [CARD_LANDS, CARD_LANDS + 30], [-60, 160], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const flash = interpolate(frame, [CARD_LANDS - 1, CARD_LANDS, CARD_LANDS + 8], [0, 0.6, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const float = Math.sin(frame / 18) * 6;
  const media = graphic.media;
  const cutout = media?.kind === 'image' && (media.layout === 'person' || media.src.toLowerCase().endsWith('.png'));
  const gold = theme.accent;
  return (
    <AbsoluteFill style={{ fontFamily, perspective: 1600 }}>
      <GridBackground />
      <div
        style={{
          position: 'absolute',
          left: (1920 - CARD.w) / 2,
          top: (1080 - CARD.h) / 2 + float,
          width: CARD.w,
          height: CARD.h,
          transform: `rotateY(${(1 - spin) * 540}deg) scale(${interpolate(spin, [0, 1], [0.4, 1])})`,
          borderRadius: 34,
          overflow: 'hidden',
          background: `linear-gradient(160deg, ${alpha(gold, 0.95)} 0%, ${alpha(gold, 0.55)} 45%, ${theme.panel} 46%, ${theme.panelRaised} 100%)`,
          border: `6px solid ${gold}`,
          boxShadow: `0 40px 90px rgba(0,0,0,0.65), 0 0 80px ${alpha(gold, 0.35)}`,
          backfaceVisibility: 'hidden',
        }}
      >
        <div style={{ position: 'absolute', left: 36, top: 30, color: '#111', lineHeight: 1 }}>
          <div style={{ fontWeight: 900, fontSize: 110 }}>{graphic.headline.value}</div>
          <div style={{ fontWeight: 800, fontSize: 26, letterSpacing: 2, maxWidth: 200 }}>{graphic.headline.label.toUpperCase()}</div>
          {graphic.position ? <div style={{ fontWeight: 700, fontSize: 24, marginTop: 10, maxWidth: 200 }}>{graphic.position.toUpperCase()}</div> : null}
        </div>
        {media ? (
          cutout ? (
            <Img src={staticFile(media.src)} style={{ position: 'absolute', right: -10, top: 30, height: 440, objectFit: 'contain' }} />
          ) : (
            <MediaBox media={media} width={360} height={380} durationInFrames={durationInFrames}
              style={{ position: 'absolute', right: 30, top: 40, borderColor: '#111', borderRadius: 18 }} />
          )
        ) : null}
        <div style={{ position: 'absolute', left: 0, right: 0, top: 470, textAlign: 'center', fontWeight: 900, fontSize: 58, color: theme.text }}>
          {graphic.name.toUpperCase()}
        </div>
        <div style={{ position: 'absolute', left: 60, right: 60, top: 550, height: 3, backgroundColor: alpha(gold, 0.6) }} />
        <div style={{ position: 'absolute', left: 50, right: 50, top: 580, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '18px 30px' }}>
          {graphic.stats.slice(0, 6).map((s, i) => {
            const show = spring({ frame: frame - CARD_LANDS - 12 - i * 6, fps, config: { damping: 200, stiffness: 180 } });
            return (
              <div key={i} style={{ display: 'flex', alignItems: 'baseline', gap: 14, opacity: show, transform: `translateY(${(1 - show) * 20}px)` }}>
                <div style={{ fontWeight: 900, fontSize: 50, color: gold, minWidth: 90, textAlign: 'right' }}>{s.value}</div>
                <div style={{ fontWeight: 700, fontSize: 26, color: theme.muted, letterSpacing: 1 }}>{s.label.toUpperCase()}</div>
              </div>
            );
          })}
        </div>
        <div
          style={{
            position: 'absolute',
            inset: 0,
            background: `linear-gradient(115deg, rgba(255,255,255,0) ${shine - 20}%, rgba(255,255,255,0.45) ${shine}%, rgba(255,255,255,0) ${shine + 20}%)`,
            mixBlendMode: 'overlay',
          }}
        />
      </div>
      <AbsoluteFill style={{ backgroundColor: 'white', opacity: flash }} />
    </AbsoluteFill>
  );
};
