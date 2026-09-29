import type { FC } from 'react';
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { theme } from '../../theme';
import type { PressGraphic } from '../../graphics';
import { Highlighted } from './Highlighted';

const PRESS_STEP = 16; // keep in sync with pipeline/timeline.py
const SERIF = 'Georgia, "Times New Roman", "DejaVu Serif", serif';
const SPOTS = [
  { x: 150, y: 150, r: -4 },
  { x: 820, y: 330, r: 3 },
  { x: 330, y: 620, r: -1.5 },
];

/** Newspaper clippings dropping one by one on a dark desk, the key words swept with a marker. */
export const Press: FC<{ graphic: PressGraphic; durationInFrames: number }> = ({ graphic, durationInFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const items = graphic.items.slice(0, 3);
  const push = interpolate(frame, [0, durationInFrames], [1, 1.06]);
  return (
    <AbsoluteFill
      style={{
        backgroundColor: theme.canvas,
        backgroundImage: `radial-gradient(ellipse at 50% 40%, rgba(255,255,255,0.07) 0%, rgba(0,0,0,0.6) 75%)`,
        overflow: 'hidden',
      }}
    >
      <AbsoluteFill style={{ transform: `scale(${push})` }}>
        {items.map((item, i) => {
          const at = 4 + i * PRESS_STEP;
          const t = spring({ frame: frame - at, fps, config: { damping: 16, stiffness: 190 } });
          const spot = items.length === 1 ? { x: 360, y: 280, r: -2 } : SPOTS[i];
          return (
            <div
              key={i}
              style={{
                position: 'absolute',
                left: spot.x,
                top: spot.y,
                width: 960,
                padding: '30px 42px 38px',
                backgroundColor: '#f2ede2',
                backgroundImage: 'linear-gradient(180deg, rgba(0,0,0,0) 60%, rgba(120,100,60,0.08) 100%)',
                color: '#15120d',
                fontFamily: SERIF,
                boxShadow: '0 30px 60px rgba(0,0,0,0.55)',
                clipPath: 'polygon(0 1%, 3% 0, 30% 1.5%, 62% 0, 97% 1%, 100% 3%, 99% 60%, 100% 98%, 70% 100%, 35% 98.5%, 2% 100%, 0 70%)',
                opacity: frame < at ? 0 : Math.min(1, t * 2),
                transform: `rotate(${spot.r + (1 - t) * 8}deg) scale(${interpolate(t, [0, 1], [1.35, 1])})`,
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', borderBottom: '3px double #15120d', paddingBottom: 10 }}>
                <div style={{ fontWeight: 700, fontSize: 40, letterSpacing: 1, fontVariant: 'small-caps' }}>
                  {item.outlet ?? ' '}
                </div>
                <div style={{ fontSize: 24, color: '#5a5245' }}>{item.date ?? ''}</div>
              </div>
              <div style={{ fontWeight: 800, fontSize: 58, lineHeight: 1.1, marginTop: 18 }}>
                <Highlighted text={item.headline} phrase={item.highlight} from={at + 10} to={at + 24} color="rgba(255, 214, 0, 0.75)" />
              </div>
              {/* columns of body text, out of focus */}
              <div style={{ display: 'flex', gap: 22, marginTop: 20, filter: 'blur(1.6px)', opacity: 0.55 }}>
                {[0, 1, 2].map((c) => (
                  <div key={c} style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 9 }}>
                    {[0, 1, 2, 3].map((l) => (
                      <div key={l} style={{ height: 9, backgroundColor: '#4a443a', width: `${88 - ((l * 13 + c * 7) % 30)}%` }} />
                    ))}
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
