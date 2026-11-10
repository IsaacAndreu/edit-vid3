import type { FC } from 'react';
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { alpha, fontFamily, theme } from '../theme';
import { GridBackground } from './GridBackground';

/**
 * The last 20 s: the channel canvas with the empty frames where YouTube's end-screen elements go
 * (a suggested video on the left, the subscribe button on the right). Add the elements in YouTube
 * Studio over these frames. Music plays on; the narration has ended.
 */
/** The atlas page's end screen: the same frames for YouTube's elements, drawn in ink on paper with serif labels. */
const PaperEnd: FC<{ next?: string; subscribe?: string; enter: number; circle: number }> = ({ next, subscribe, enter, circle }) => {
  const ink = '#1E2833';
  const serif = "'DM Serif Display', Georgia, serif";
  const raw = next || 'La siguiente historia';
  const text = raw === raw.toUpperCase() ? raw.charAt(0) + raw.slice(1).toLowerCase() : raw;   // «SIGUIENTE HISTORIA» → sentence case
  const words = text.split(' ');
  return (
    <AbsoluteFill style={{ background: 'radial-gradient(ellipse 75% 70% at 50% 45%, #ECE4D1 55%, #D9CFB8 100%)' }}>
      <div style={{ position: 'absolute', left: 150, top: 250, opacity: enter, transform: `translateY(${interpolate(enter, [0, 1], [24, 0])}px)` }}>
        <div style={{ fontFamily: serif, fontSize: 56, color: ink, marginBottom: 26 }}>
          {words.slice(0, -1).join(' ')} <span style={{ fontStyle: 'italic', color: theme.accent }}>{words[words.length - 1].toLowerCase()}</span>
        </div>
        <div style={{ width: 880, height: 495, border: `2px solid ${ink}`, background: 'rgba(255,255,255,0.25)',
                      boxShadow: '0 14px 40px rgba(0,0,0,0.18), inset 0 0 0 8px rgba(255,255,255,0.35)' }} />
      </div>
      <div style={{ position: 'absolute', left: 1280, top: 360, width: 420, display: 'flex', flexDirection: 'column', alignItems: 'center',
                    gap: 34, opacity: circle, transform: `scale(${interpolate(circle, [0, 1], [0.9, 1])})` }}>
        <div style={{ width: 300, height: 300, borderRadius: '50%', border: `2px solid ${ink}`, background: 'rgba(255,255,255,0.25)',
                      boxShadow: '0 14px 40px rgba(0,0,0,0.18)' }} />
        <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 30, letterSpacing: 6, color: ink }}>{(subscribe || 'SUSCRÍBETE').toUpperCase()}</div>
      </div>
      <AbsoluteFill style={{ background: 'radial-gradient(ellipse 62% 58% at 50% 48%, rgba(90,70,40,0) 40%, rgba(90,70,40,0.22) 100%)' }} />
    </AbsoluteFill>
  );
};

export const EndScreen: FC<{ next?: string; subscribe?: string }> = ({ next, subscribe }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enter = spring({ frame: frame - 6, fps, config: { damping: 200, stiffness: 120 }, durationInFrames: 20 });
  const circle = spring({ frame: frame - 14, fps, config: { damping: 200, stiffness: 120 }, durationInFrames: 20 });
  if (theme.endStyle === 'paper') {
    return <PaperEnd next={next} subscribe={subscribe} enter={enter} circle={circle} />;
  }
  const label = {
    fontFamily,
    fontWeight: 900,
    fontSize: 54,
    letterSpacing: '0.02em',
    color: theme.text,
    textShadow: theme.shadow,
  } as const;
  return (
    <AbsoluteFill>
      <GridBackground />
      {/* Suggested video: 880x495 (16:9) */}
      <div
        style={{
          position: 'absolute',
          left: 150,
          top: 250,
          opacity: enter,
          transform: `translateY(${interpolate(enter, [0, 1], [30, 0])}px)`,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 20, marginBottom: 28 }}>
          <div style={{ width: 10, height: 56, backgroundColor: theme.accent }} />
          <div style={label}>{next || 'SIGUIENTE HISTORIA'}</div>
        </div>
        <div
          style={{
            width: 880,
            height: 495,
            borderRadius: 18,
            border: `5px solid ${theme.accent}`,
            backgroundColor: 'rgba(0,0,0,0.55)',
            boxShadow: `0 0 60px ${alpha(theme.accent, 0.18)}`,
          }}
        />
      </div>
      {/* Subscribe: a 300 px circle */}
      <div
        style={{
          position: 'absolute',
          left: 1280,
          top: 360,
          width: 420,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: 34,
          opacity: circle,
          transform: `scale(${interpolate(circle, [0, 1], [0.85, 1])})`,
        }}
      >
        <div
          style={{
            width: 300,
            height: 300,
            borderRadius: '50%',
            border: `5px solid ${theme.accent}`,
            backgroundColor: 'rgba(0,0,0,0.55)',
            boxShadow: `0 0 60px ${alpha(theme.accent, 0.18)}`,
          }}
        />
        <div style={{ ...label, fontSize: 46 }}>{subscribe || 'SUSCRÍBETE'}</div>
      </div>
    </AbsoluteFill>
  );
};
