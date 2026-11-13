import type { FC } from 'react';
import { AbsoluteFill, Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';
import { theme } from '../../theme';
import type { LineupGraphic } from '../../graphics';

/**
 * Two to four people side by side, as true-crime channels show the accused (or the victim and the accused) when the
 * story talks about them together: tall photos coming in one after another, a slow push over all of them, each
 * person's name typed in red under their photo. The photos and names come from the people stage (people.json).
 */
export const Lineup: FC<{ graphic: LineupGraphic; durationInFrames: number }> = ({ graphic, durationInFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const n = graphic.people.length;
  const width = n >= 4 ? 400 : n === 3 ? 500 : 620;
  const push = interpolate(frame, [0, durationInFrames], [1, 1.05]);
  return (
    <AbsoluteFill style={{ backgroundColor: '#050505', justifyContent: 'center', alignItems: 'center' }}>
      <div style={{ display: 'flex', gap: 28, transform: `scale(${push})` }}>
        {graphic.people.map((person, i) => {
          const enter = spring({ frame: frame - i * 6, fps, config: { damping: 200, stiffness: 110 } });
          const typed = Math.floor(interpolate(frame, [10 + i * 6, 10 + i * 6 + person.name.length * 1.2], [0, person.name.length],
            { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }));
          return (
            <div key={person.name} style={{ width, opacity: enter, transform: `translateY(${(1 - enter) * 40}px)`, textAlign: 'center' }}>
              <div style={{ width, height: 760, overflow: 'hidden', backgroundColor: '#111',
                            boxShadow: '0 20px 50px rgba(0,0,0,0.7)', filter: 'contrast(1.05) saturate(0.85)' }}>
                <Img src={staticFile(person.media.src)} style={{ width: '100%', height: '100%', objectFit: 'cover',
                                                                 objectPosition: 'center 25%' }} />
              </div>
              <div style={{ marginTop: 22, fontFamily: "'Special Elite', 'Courier New', monospace", fontSize: n >= 4 ? 34 : 42,
                            color: theme.typewriter, whiteSpace: 'nowrap', textShadow: '0 2px 2px rgba(0,0,0,0.8)', minHeight: 50 }}>
                {person.name.slice(0, typed)}
              </div>
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
