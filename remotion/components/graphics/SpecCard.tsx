import type { FC } from 'react';
import { AbsoluteFill, Easing, interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { fontFamily, theme } from '../../theme';
import type { SpecsGraphic } from '../../graphics';
import { countUp } from '../countUp';
import { GridBackground } from '../GridBackground';
import { MediaBox } from './MediaBox';

/** Spec sheet (robot, car, athlete): photo on the left, figures counting up in a technical grid. */
export const SpecCard: FC<{ graphic: SpecsGraphic; durationInFrames: number }> = ({ graphic, durationInFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enter = spring({ frame, fps, config: { damping: 200, stiffness: 120 } });
  const specs = graphic.specs.slice(0, 6);
  return (
    <AbsoluteFill>
      <GridBackground />
      <MediaBox
        media={graphic.media}
        width={760}
        height={860}
        durationInFrames={durationInFrames}
        style={{ position: 'absolute', left: 110, top: 110, opacity: enter, transform: `translateX(${(1 - enter) * -50}px)` }}
      />
      <div style={{ position: 'absolute', left: 960, top: 120, right: 110, fontFamily }}>
        <div style={{ fontWeight: 600, fontSize: 30, letterSpacing: '0.3em', color: theme.accent, opacity: enter }}>FICHA TÉCNICA</div>
        <div style={{ fontWeight: 900, fontSize: 88, color: theme.text, lineHeight: 1.02, marginTop: 8, opacity: enter }}>
          {graphic.name.toUpperCase()}
        </div>
        {graphic.subtitle ? <div style={{ fontWeight: 600, fontSize: 36, color: theme.muted, marginTop: 8 }}>{graphic.subtitle}</div> : null}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '26px 40px', marginTop: 50 }}>
          {specs.map((s, i) => {
            const show = spring({ frame: frame - 14 - i * 7, fps, config: { damping: 200, stiffness: 160 } });
            const count = interpolate(frame, [14 + i * 7, 40 + i * 7], [0, 1], {
              extrapolateLeft: 'clamp',
              extrapolateRight: 'clamp',
              easing: Easing.out(Easing.cubic),
            });
            return (
              <div
                key={i}
                style={{
                  borderTop: `3px solid ${theme.accent}`,
                  paddingTop: 14,
                  opacity: show,
                  transform: `translateY(${(1 - show) * 24}px)`,
                }}
              >
                <div style={{ fontWeight: 600, fontSize: 28, color: theme.muted, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                  {s.label}
                </div>
                <div style={{ fontWeight: 900, fontSize: 68, color: theme.text, fontVariantNumeric: 'tabular-nums' }}>
                  {countUp(s.value, count)}
                  {s.unit ? <span style={{ fontSize: 36, color: theme.accent, marginLeft: 10 }}>{s.unit}</span> : null}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </AbsoluteFill>
  );
};
