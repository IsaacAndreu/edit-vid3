import type { CSSProperties, FC } from 'react';
import { AbsoluteFill, Img, OffthreadVideo, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';
import type { AfirmacionGraphic, CirculoGraphic, FichaGraphic, ListaGraphic, PruebaGraphic } from '../../graphics';
import type { Media } from '../../types';
import { alpha, condensedFamily, fontFamily, theme } from '../../theme';
import { GridBackground } from '../GridBackground';

// Argument cards for theory, explainer and game channels: a character card, a row of evidence with ✓ / ✗, a numbered
// claim with its verdict stamp, a short list filled in one by one. Colours come from the channel's brand (theme);
// every word from the script (pipeline/graphics.py, argument_graphic).

const rise = (frame: number, at = 0, length = 12) =>
  interpolate(frame, [at, at + length], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });

const Picture: FC<{ media: Media; style: CSSProperties }> = ({ media, style }) => {
  const fit: CSSProperties = { width: '100%', height: '100%', objectFit: 'cover',
    objectPosition: media.focus ? `${media.focus[0]}% ${media.focus[1]}%` : 'center 30%' };
  return (
    <div style={{ overflow: 'hidden', ...style }}>
      {media.kind === 'video' ? <OffthreadVideo src={staticFile(media.src)} muted style={fit} />
        : <Img src={staticFile(media.src)} style={fit} />}
    </div>
  );
};

/** Who or what: portrait, where it comes from, the name, one line. */
export const Ficha: FC<{ graphic: FichaGraphic; durationInFrames: number }> = ({ graphic }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pop = spring({ frame, fps, config: { damping: 16, stiffness: 140 } });
  const text = rise(frame, 10, 14);
  const media = graphic.media;
  return (
    <AbsoluteFill style={{ fontFamily }}>
      <GridBackground />
      <div style={{ position: 'absolute', left: 260, top: 190, width: 1400, height: 700, borderRadius: 36,
        background: theme.panel ?? '#141414', border: `3px solid ${alpha(theme.accent, 0.5)}`, transform: `scale(${0.9 + 0.1 * pop})`,
        opacity: pop, boxShadow: `0 40px 90px rgba(0,0,0,0.55), 0 0 70px ${alpha(theme.accent, 0.12)}`, display: 'flex', overflow: 'hidden' }}>
        {media ? (
          <Picture media={media} style={{ width: 560, height: '100%', borderRight: `3px solid ${alpha(theme.accent, 0.5)}` }} />
        ) : (
          <div style={{ width: 560, height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: alpha(theme.accent, 0.12), fontFamily: condensedFamily, fontWeight: 700, fontSize: 260, color: theme.accent }}>
            {graphic.name.trim().charAt(0).toUpperCase()}
          </div>
        )}
        <div style={{ flex: 1, padding: '70px 70px', display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 26,
          opacity: text, transform: `translateX(${(1 - text) * 30}px)` }}>
          {graphic.origin ? (
            <div style={{ alignSelf: 'flex-start', padding: '8px 20px', borderRadius: 10, background: theme.accent, color: theme.canvas,
              fontSize: 30, fontWeight: 800, letterSpacing: 2, textTransform: 'uppercase' }}>{graphic.origin}</div>
          ) : null}
          <div style={{ fontFamily: condensedFamily, fontWeight: 700, fontSize: 104, lineHeight: 1, color: theme.text,
            textTransform: 'uppercase', textShadow: theme.shadow }}>{graphic.name}</div>
          {graphic.line ? <div style={{ fontSize: 40, lineHeight: 1.3, color: alpha(theme.text, 0.82) }}>{graphic.line}</div> : null}
        </div>
      </div>
    </AbsoluteFill>
  );
};

const Mark: FC<{ ok: boolean; size: number; at: number }> = ({ ok, size, at }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pop = spring({ frame: frame - at, fps, config: { damping: 10, stiffness: 200 } });
  const color = ok ? theme.positive : theme.negative;
  return (
    <div style={{ width: size, height: size, borderRadius: '50%', background: alpha(color, 0.18), border: `4px solid ${color}`,
      display: 'flex', alignItems: 'center', justifyContent: 'center', transform: `scale(${pop})`, flex: 'none' }}>
      <svg width={size * 0.55} height={size * 0.55} viewBox="0 0 24 24">
        <path d={ok ? 'm5 12 5 5 9-10' : 'M6 6l12 12M18 6 6 18'} fill="none" stroke={color} strokeWidth={3.4}
          strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </div>
  );
};

/** Evidence rows: where it is said · what it says · what it matches, each with its ✓ or ✗. */
export const Prueba: FC<{ graphic: PruebaGraphic; durationInFrames: number }> = ({ graphic }) => {
  const frame = useCurrentFrame();
  const head = rise(frame, 0, 12);
  const rows = graphic.rows.slice(0, 4);
  const top = 540 - rows.length * 82 + (graphic.title ? 40 : 0);
  return (
    <AbsoluteFill style={{ fontFamily }}>
      <GridBackground />
      {graphic.title ? (
        <div style={{ position: 'absolute', top: top - 130, left: 0, right: 0, textAlign: 'center', opacity: head,
          fontFamily: condensedFamily, fontWeight: 700, fontSize: 64, letterSpacing: 3, color: theme.text,
          textTransform: 'uppercase', textShadow: theme.shadow }}>{graphic.title}</div>
      ) : null}
      {rows.map((row, i) => {
        const at = 10 + i * 16;
        const show = rise(frame, at, 12);
        return (
          <div key={i} style={{ position: 'absolute', left: 170, right: 170, top: top + i * 164, height: 136, borderRadius: 22,
            background: theme.panel ?? '#141414', border: `2px solid ${alpha(row.ok ? theme.positive : theme.negative, 0.45)}`,
            display: 'flex', alignItems: 'center', gap: 34, padding: '0 40px', opacity: show,
            transform: `translateY(${(1 - show) * 24}px)` }}>
            <div style={{ width: 380, fontSize: 28, fontWeight: 800, letterSpacing: 2, textTransform: 'uppercase',
              color: theme.accent }}>{row.source}</div>
            <div style={{ flex: 1, fontSize: 44, fontWeight: 700, color: theme.text }}>{row.fact}</div>
            <div style={{ fontSize: 30, color: alpha(theme.text, 0.65) }}>→</div>
            <div style={{ width: 360, fontFamily: condensedFamily, fontWeight: 700, fontSize: 48, color: theme.text,
              textTransform: 'uppercase' }}>{row.match}</div>
            <Mark ok={row.ok} size={86} at={at + 8} />
          </div>
        );
      })}
    </AbsoluteFill>
  );
};

/** A numbered claim and, a beat later, its verdict stamped across it. */
export const Afirmacion: FC<{ graphic: AfirmacionGraphic; durationInFrames: number }> = ({ graphic, durationInFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const card = rise(frame, 0, 14);
  const stampAt = Math.min(36, Math.round(durationInFrames * 0.4));
  const stamp = spring({ frame: frame - stampAt, fps, config: { damping: 9, stiffness: 180 } });
  const color = graphic.ok ? theme.positive : theme.negative;
  return (
    <AbsoluteFill style={{ fontFamily }}>
      <GridBackground />
      <div style={{ position: 'absolute', left: 240, right: 240, top: 250, height: 580, borderRadius: 34,
        background: theme.panel ?? '#141414', border: `3px solid ${alpha(theme.text, 0.16)}`, opacity: card,
        transform: `translateY(${(1 - card) * 30}px)`, padding: '70px 90px', boxSizing: 'border-box' }}>
        <div style={{ fontFamily: condensedFamily, fontWeight: 700, fontSize: 58, letterSpacing: 4, color: theme.accent,
          textTransform: 'uppercase' }}>{graphic.label}</div>
        <div style={{ marginTop: 34, fontSize: 64, lineHeight: 1.22, fontWeight: 700, color: theme.text }}>«{graphic.claim}»</div>
      </div>
      {frame >= stampAt ? (
        <div style={{ position: 'absolute', right: 300, top: 590, transform: `rotate(-9deg) scale(${2 - stamp})`, opacity: stamp,
          padding: '18px 48px', border: `10px solid ${color}`, borderRadius: 18, color, fontFamily: condensedFamily,
          fontWeight: 700, fontSize: 112, letterSpacing: 6, textTransform: 'uppercase', background: alpha('#000000', 0.35),
          boxShadow: `0 0 40px ${alpha(color, 0.35)}` }}>{graphic.verdict}</div>
      ) : null}
    </AbsoluteFill>
  );
};

/** A short list filled in one item at a time over the card's length. */
export const Lista: FC<{ graphic: ListaGraphic; durationInFrames: number }> = ({ graphic, durationInFrames }) => {
  const frame = useCurrentFrame();
  const items = graphic.items.slice(0, 6);
  const step = Math.max(8, Math.floor((durationInFrames * 0.7) / Math.max(1, items.length)));
  const head = rise(frame, 0, 12);
  return (
    <AbsoluteFill style={{ fontFamily }}>
      <GridBackground />
      <div style={{ position: 'absolute', left: 360, right: 360, top: 170, opacity: head }}>
        <div style={{ fontFamily: condensedFamily, fontWeight: 700, fontSize: 76, letterSpacing: 3, color: theme.text,
          textTransform: 'uppercase', borderBottom: `5px solid ${theme.accent}`, paddingBottom: 18, textShadow: theme.shadow }}>
          {graphic.title}
        </div>
        {items.map((item, i) => {
          const show = rise(frame, 12 + i * step, 10);
          return (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 28, marginTop: 34, opacity: show,
              transform: `translateX(${(1 - show) * 40}px)` }}>
              <div style={{ width: 64, height: 64, borderRadius: 14, background: theme.accent, color: theme.canvas,
                display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: condensedFamily, fontWeight: 700,
                fontSize: 40, flex: 'none' }}>{i + 1}</div>
              <div style={{ fontSize: 50, fontWeight: 700, color: theme.text }}>{item}</div>
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

/** A hand-drawn circle around the proof, over the shot's footage (no background of its own). */
export const Circulo: FC<{ graphic: CirculoGraphic; durationInFrames: number }> = ({ graphic }) => {
  const frame = useCurrentFrame();
  const [x0, y0, x1, y1] = graphic.box;
  const cx = ((x0 + x1) / 2) * 19.2;
  const cy = ((y0 + y1) / 2) * 10.8;
  const rx = Math.max(60, ((x1 - x0) / 2) * 19.2 * 1.08);
  const ry = Math.max(36, ((y1 - y0) / 2) * 10.8 * 1.3);
  const draw = interpolate(frame, [6, 24], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  // an ellipse that does not quite close, a little tilted: drawn by hand, not by a program
  const steps = 64;
  const points = Array.from({ length: steps + 6 }, (_, i) => {
    const a = (i / steps) * Math.PI * 2 - Math.PI / 2;
    const wobble = 1 + 0.035 * Math.sin(a * 2 + 0.6) + 0.015 * Math.sin(a * 3);
    return `${(cx + rx * wobble * Math.cos(a)).toFixed(1)},${(cy + ry * wobble * Math.sin(a)).toFixed(1)}`;
  });
  const length = 2 * Math.PI * Math.sqrt((rx * rx + ry * ry) / 2) * 1.1;
  return (
    <AbsoluteFill>
      <svg width={1920} height={1080} style={{ position: 'absolute', inset: 0 }}>
        <polyline points={points.join(' ')} fill="none" stroke={theme.accent} strokeWidth={9} strokeLinecap="round"
          strokeLinejoin="round" strokeDasharray={length} strokeDashoffset={length * (1 - draw)}
          transform={`rotate(-4 ${cx} ${cy})`} style={{ filter: `drop-shadow(0 0 10px ${alpha('#000000', 0.7)})` }} />
      </svg>
    </AbsoluteFill>
  );
};
