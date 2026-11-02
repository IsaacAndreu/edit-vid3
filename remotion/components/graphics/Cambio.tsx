import type { FC } from 'react';
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { alpha, fontFamily, theme } from '../../theme';
import type { CambioGraphic } from '../../graphics';
import { GridBackground } from '../GridBackground';

const SWAP = 34; // keep in sync with pipeline/timeline.py (CAMBIO_SWAP)

/** A score or a place that changed (an inquiry, a review, a ruling): the old one, struck out in red, and the new one
 * landing with a bump; the place moves below (quinta → tercera). */
export const Cambio: FC<{ graphic: CambioGraphic; durationInFrames: number }> = ({ graphic }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const head = interpolate(frame, [0, 10], [0, 1], { extrapolateRight: 'clamp' });
  const strike = interpolate(frame, [SWAP - 10, SWAP - 2], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const land = spring({ frame: frame - SWAP, fps, config: { damping: 10, stiffness: 170 } });
  const up = /\d/.test(graphic.after) && /\d/.test(graphic.before)
    ? parseFloat(graphic.after.replace(',', '.')) >= parseFloat(graphic.before.replace(',', '.')) : true;
  const colour = up ? theme.positive : theme.negative;
  const box = (value: string, big: boolean) => (
    <div style={{ position: 'relative', padding: big ? '26px 56px' : '22px 44px', borderRadius: 20, fontWeight: 900,
                  fontSize: big ? 150 : 110, lineHeight: 1, fontVariantNumeric: 'tabular-nums',
                  background: big ? colour : theme.panelRaised, color: big ? '#0b0b0b' : theme.muted,
                  border: `3px solid ${big ? colour : theme.border}`, boxShadow: big ? `0 0 80px ${alpha(colour, 0.45)}` : 'none' }}>
      {value}
      {!big && <div style={{ position: 'absolute', left: 20, right: 20, top: '50%', height: 12, background: theme.negative,
                             transform: `scaleX(${strike}) rotate(-8deg)`, transformOrigin: 'left center', borderRadius: 6 }} />}
    </div>
  );
  return (
    <AbsoluteFill style={{ fontFamily }}>
      <GridBackground />
      <div style={{ position: 'absolute', top: 150, left: 0, right: 0, textAlign: 'center', opacity: head }}>
        <div style={{ fontWeight: 900, fontSize: 76, color: theme.text, textShadow: theme.shadow }}>{graphic.name.toUpperCase()}</div>
        {graphic.reason ? <div style={{ fontWeight: 700, fontSize: 40, color: theme.accent, marginTop: 8, letterSpacing: 2 }}>{graphic.reason.toUpperCase()}</div> : null}
      </div>
      <div style={{ position: 'absolute', top: 400, left: 0, right: 0, display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 50 }}>
        {box(graphic.before, false)}
        <div style={{ fontSize: 110, fontWeight: 900, color: theme.muted, opacity: strike }}>→</div>
        <div style={{ opacity: Math.min(1, land * 1.5), transform: `scale(${interpolate(land, [0, 1], [0.5, 1])})` }}>{box(graphic.after, true)}</div>
      </div>
      {graphic.fromPlace || graphic.toPlace ? (
        <div style={{ position: 'absolute', top: 740, left: 0, right: 0, textAlign: 'center', fontWeight: 900, fontSize: 64,
                      textTransform: 'uppercase', color: theme.text }}>
          <span style={{ color: theme.muted }}>{graphic.fromPlace ?? ''}</span>
          <span style={{ opacity: land }}>{graphic.toPlace ? <>{'  →  '}<span style={{ color: colour }}>{graphic.toPlace}</span></> : null}</span>
        </div>
      ) : null}
    </AbsoluteFill>
  );
};
