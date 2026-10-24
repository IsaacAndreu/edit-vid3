import type { FC } from 'react';
import { AbsoluteFill, interpolate, useCurrentFrame } from 'remotion';
import type { MarkerGraphic } from '../../graphics';
import { Grain, Newsprint, typed, Vignette } from './Paper';

/** A phrase typed over an old blurred newspaper and swept with a yellow highlighter. */
export const Marker: FC<{ graphic: MarkerGraphic; durationInFrames: number }> = ({ graphic, durationInFrames }) => {
  const frame = useCurrentFrame();
  const text = graphic.text;
  const speed = Math.max(0.8, text.length / Math.max(14, durationInFrames * 0.3));
  const shown = typed(text, frame, 6, speed);
  const done = 6 + text.length / speed;
  const sweep = interpolate(frame, [done + 2, done + 14], [0, 100], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const drift = interpolate(frame, [0, durationInFrames], [1.04, 1.12]);
  const size = text.length > 46 ? 68 : text.length > 30 ? 82 : 100;
  return (
    <AbsoluteFill style={{ overflow: 'hidden' }}>
      <AbsoluteFill style={{ transform: `scale(${drift})` }}>
        <Newsprint tone="#cfc8b8" />
      </AbsoluteFill>
      <AbsoluteFill style={{ backgroundColor: 'rgba(40,36,28,0.18)' }} />
      <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center', padding: '0 180px' }}>
        <div style={{ fontFamily: "'Special Elite', monospace", fontSize: size, lineHeight: 1.45, color: '#141210', textAlign: 'center' }}>
          <span
            style={{
              backgroundImage: 'linear-gradient(#f4d81c, #f4d81c)',
              backgroundRepeat: 'no-repeat',
              backgroundSize: `${sweep}% 78%`,
              backgroundPosition: '0 70%',
              boxDecorationBreak: 'clone',
              WebkitBoxDecorationBreak: 'clone',
              padding: '0 10px',
            }}
          >
            {shown}
          </span>
          <span style={{ opacity: frame < done || Math.floor(frame / 8) % 2 === 0 ? 0.9 : 0 }}>▌</span>
        </div>
      </AbsoluteFill>
      <Vignette strength={0.6} />
      <Grain opacity={0.2} id="marker-grain" />
    </AbsoluteFill>
  );
};
