import type { FC } from 'react';
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { fontFamily, theme } from '../../theme';
import type { ReceiptGraphic } from '../../graphics';
import { GridBackground } from '../GridBackground';
import { countUp } from '../countUp';

const MONO = "'Courier New', 'DejaVu Sans Mono', 'Liberation Mono', monospace";
const WIDTH = 720;
const LINE = 64;

/** Cost breakdown as a till receipt: it comes out of the printer line by line, the total at the end. */
export const Receipt: FC<{ graphic: ReceiptGraphic; durationInFrames: number }> = ({ graphic, durationInFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const n = graphic.items.length;
  const every = Math.max(6, Math.min(12, Math.floor((durationInFrames * 0.55) / (n + 2))));
  const printed = interpolate(frame, [4, 4 + every * (n + 1)], [0, n + 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const header = 150;
  const bodyH = header + n * LINE + (graphic.total ? 150 : 40);
  const visible = Math.min(bodyH, header + Math.min(printed, n) * LINE + (printed > n ? 150 : 40)); // the paper grows as it prints
  const totalIn = spring({ frame: frame - (4 + every * (n + 1)), fps, config: { damping: 14, stiffness: 150 } });
  const counting = interpolate(frame, [4 + every * (n + 1), 4 + every * (n + 1) + 20], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const out = interpolate(frame, [durationInFrames - 8, durationInFrames], [1, 0], { extrapolateLeft: 'clamp' });
  const zigzag = Array.from({ length: 37 }, (_, i) => `${(i / 36) * 100}% ${i % 2 ? 100 : 'calc(100% - 14px)'}`).join(', ');
  return (
    <AbsoluteFill style={{ opacity: out }}>
      <GridBackground />
      <div style={{ position: 'absolute', left: (1920 - WIDTH - 80) / 2, top: 70, width: WIDTH + 80, height: 26, borderRadius: 13, backgroundColor: '#0c0c0c', boxShadow: '0 8px 20px rgba(0,0,0,0.6)' }} />
      <div style={{ position: 'absolute', left: (1920 - WIDTH) / 2, top: 84, width: WIDTH, height: visible + 14, overflow: 'hidden' }}>
        <div
          style={{
            position: 'absolute', left: 0, top: 0, width: WIDTH, height: bodyH, backgroundColor: '#f6f3ea',
            color: '#1b1b1b', fontFamily: MONO, fontWeight: 700, padding: '40px 46px 0', boxSizing: 'border-box',
            clipPath: `polygon(0 0, 100% 0, ${zigzag}, 0 calc(100% - 14px))`, boxShadow: '0 30px 80px rgba(0,0,0,0.55)',
          }}
        >
          <div style={{ textAlign: 'center', fontSize: 38, textTransform: 'uppercase', letterSpacing: '0.04em', height: 60 }}>
            {graphic.title || 'TICKET'}
          </div>
          <div style={{ borderTop: '3px dashed #999', margin: '10px 0 16px' }} />
          {graphic.items.map((item, i) => (
            <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', height: LINE, fontSize: 34, opacity: printed > i ? 1 : 0 }}>
              <span style={{ textTransform: 'uppercase', maxWidth: 420, overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis' }}>{item.label}</span>
              <span>{item.value}</span>
            </div>
          ))}
          {graphic.total ? (
            <>
              <div style={{ borderTop: '3px dashed #999', margin: '6px 0 18px' }} />
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', opacity: totalIn, transform: `scale(${interpolate(totalIn, [0, 1], [1.15, 1])})` }}>
                <span style={{ fontSize: 40, textTransform: 'uppercase' }}>{graphic.total.label}</span>
                <span style={{ fontFamily, fontWeight: 900, fontSize: 64, color: '#111', backgroundColor: theme.accent, padding: '0 14px', borderRadius: 6 }}>
                  {countUp(graphic.total.value, counting)}
                </span>
              </div>
            </>
          ) : null}
        </div>
      </div>
    </AbsoluteFill>
  );
};
