import type { FC } from 'react';
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { alpha, fontFamily, theme } from '../../theme';
import type { ScaleGraphic } from '../../graphics';
import { GridBackground } from '../GridBackground';
import { GraphicTitle } from './GraphicTitle';

/** Size comparison on a ruler: each measure grows from the ground (or from the left for lengths)
 * next to everyday references (a person, a basketball hoop…), the main one in the brand colour
 * with a dashed line at its top. */
export const Scale: FC<{ graphic: ScaleGraphic; durationInFrames: number }> = ({ graphic }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const items = graphic.items.slice(0, 5);
  const max = Math.max(...items.map((i) => i.value)) * 1.12;
  const vertical = graphic.axis === 'height';
  const span = vertical ? 700 : 1500; // px of the axis
  const ticks = Array.from({ length: Math.floor(max) + 1 }, (_, i) => i);
  const fmt = (v: number) => v.toLocaleString('es-ES', { maximumFractionDigits: 2 });
  return (
    <AbsoluteFill style={{ fontFamily }}>
      <GridBackground />
      {graphic.title ? <GraphicTitle text={graphic.title} /> : null}
      {vertical ? (
        <>
          <div style={{ position: 'absolute', left: 250, top: 930, width: 1500, height: 4, backgroundColor: theme.text }} />
          {ticks.map((t) => (
            <div key={t} style={{ position: 'absolute', left: 150, top: 930 - (t / max) * span - 18, width: 1600, display: 'flex', alignItems: 'center', gap: 16 }}>
              <div style={{ width: 80, textAlign: 'right', fontSize: 28, color: theme.muted, fontWeight: 700 }}>{t} {graphic.unit}</div>
              <div style={{ flex: 1, height: 1, backgroundColor: alpha(theme.text, 0.12) }} />
            </div>
          ))}
          {items.map((item, i) => {
            const grow = spring({ frame: frame - 10 - i * 10, fps, config: { damping: 18, stiffness: 90 } });
            const h = (item.value / max) * span * grow;
            const color = item.reference ? alpha(theme.text, 0.25) : i === 0 ? theme.accent : theme.accent2;
            const x = 330 + i * (1300 / items.length);
            return (
              <div key={i}>
                <div style={{ position: 'absolute', left: x, top: 930 - h, width: 150, height: h, backgroundColor: color, borderRadius: '8px 8px 0 0',
                  border: item.reference ? `3px dashed ${alpha(theme.text, 0.5)}` : 'none', boxShadow: item.reference ? 'none' : `0 0 40px ${alpha(color, 0.4)}` }} />
                <div style={{ position: 'absolute', left: x - 60, width: 270, top: 930 - h - 70, textAlign: 'center', fontWeight: 900, fontSize: 44, color: item.reference ? theme.muted : theme.text, opacity: grow }}>
                  {fmt(item.value * grow)} {graphic.unit}
                </div>
                <div style={{ position: 'absolute', left: x - 60, width: 270, top: 950, textAlign: 'center', fontWeight: 700, fontSize: 30, color: item.reference ? theme.muted : theme.text, lineHeight: 1.1 }}>
                  {item.name}
                </div>
                {i === 0 && !item.reference ? (
                  <div style={{ position: 'absolute', left: 250, width: 1500, top: 930 - h, borderTop: `3px dashed ${alpha(theme.accent, 0.8 * grow)}` }} />
                ) : null}
              </div>
            );
          })}
        </>
      ) : (
        <>
          {items.map((item, i) => {
            const grow = spring({ frame: frame - 10 - i * 10, fps, config: { damping: 18, stiffness: 90 } });
            const w = (item.value / max) * span * grow;
            const color = item.reference ? alpha(theme.text, 0.25) : i === 0 ? theme.accent : theme.accent2;
            const y = 260 + i * (700 / items.length);
            return (
              <div key={i} style={{ position: 'absolute', left: 200, top: y }}>
                <div style={{ fontWeight: 700, fontSize: 32, color: item.reference ? theme.muted : theme.text, marginBottom: 10 }}>{item.name}</div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
                  <div style={{ width: w, height: 60, backgroundColor: color, borderRadius: 8, border: item.reference ? `3px dashed ${alpha(theme.text, 0.5)}` : 'none' }} />
                  <div style={{ fontWeight: 900, fontSize: 46, color: theme.text, opacity: grow }}>{fmt(item.value * grow)} {graphic.unit}</div>
                </div>
              </div>
            );
          })}
        </>
      )}
    </AbsoluteFill>
  );
};
