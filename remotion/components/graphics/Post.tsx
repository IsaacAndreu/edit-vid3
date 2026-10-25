import type { FC } from 'react';
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import type { PostGraphic } from '../../graphics';
import { alpha, fontFamily, theme } from '../../theme';
import { MediaBox } from './MediaBox';
import { Grain, Vignette } from './Paper';

const PLATFORM: Record<string, string> = { x: 'X', instagram: 'Instagram', facebook: 'Facebook', tiktok: 'TikTok' };

/** Outline icons of the action row (generic shapes, no counts: the numbers would be made up). */
const Icon: FC<{ d: string }> = ({ d }) => (
  <svg width={40} height={40} viewBox="0 0 24 24" fill="none" stroke="#8b929c" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round">
    <path d={d} />
  </svg>
);
const ICONS = [
  'M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z', // reply
  'M17 2l4 4-4 4M3 11V9a3 3 0 0 1 3-3h15M7 22l-4-4 4-4M21 13v2a3 3 0 0 1-3 3H3', // share again
  'M12 21s-7.5-4.6-9.5-9.2C1 8.3 3.3 4.5 7 4.5c2.1 0 3.7 1.2 5 3 1.3-1.8 2.9-3 5-3 3.7 0 6 3.8 4.5 7.3C19.5 16.4 12 21 12 21z', // like
  'M4 12v7a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-7M16 6l-4-4-4 4M12 2v13', // send
];

/** What someone published, recreated as a generic social media card: it rises out of the dark, the text appears word
 * by word, and the camera leans in slowly. */
export const Post: FC<{ graphic: PostGraphic; durationInFrames: number }> = ({ graphic, durationInFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enter = spring({ frame: frame - 2, fps, config: { damping: 16, stiffness: 110 } });
  const words = graphic.text.split(/\s+/);
  const shown = interpolate(frame, [14, 14 + Math.min(durationInFrames * 0.5, words.length * 3.2)], [0, words.length], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const size = words.length > 28 ? 46 : words.length > 16 ? 54 : 64;
  const lean = interpolate(frame, [0, durationInFrames], [1, 1.06]);
  const meta = [graphic.date, graphic.platform ? PLATFORM[graphic.platform] : null].filter(Boolean).join(' · ');
  return (
    <AbsoluteFill style={{ backgroundColor: '#07080a', overflow: 'hidden' }}>
      <AbsoluteFill style={{ background: `radial-gradient(ellipse 55% 60% at 50% 55%, ${alpha(theme.accent, 0.22)}, rgba(0,0,0,0) 70%)` }} />
      <AbsoluteFill style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', perspective: 1600 }}>
        <div style={{ width: 1180, padding: '52px 60px 40px', boxSizing: 'border-box', borderRadius: 34, backgroundColor: '#14171c',
          border: '1px solid rgba(255,255,255,0.09)', fontFamily, color: '#eef0f3', opacity: enter,
          boxShadow: `0 50px 120px rgba(0,0,0,0.7), 0 0 80px ${alpha(theme.accent, 0.12)}`,
          transform: `translateY(${(1 - enter) * 120}px) rotateX(${(1 - enter) * 16}deg) scale(${lean})` }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 26 }}>
            {graphic.media ? (
              <MediaBox media={graphic.media} width={112} height={112} durationInFrames={durationInFrames}
                style={{ borderRadius: '50%', border: 'none', boxShadow: 'none' }} face />
            ) : (
              <div style={{ width: 112, height: 112, borderRadius: '50%', backgroundColor: theme.accent, color: '#000', display: 'flex',
                alignItems: 'center', justifyContent: 'center', fontWeight: 900, fontSize: 52 }}>{graphic.author[0]?.toUpperCase()}</div>
            )}
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 800, fontSize: 44 }}>{graphic.author}</div>
              {meta ? <div style={{ fontSize: 32, color: '#8b929c' }}>{meta}</div> : null}
            </div>
            <div style={{ fontSize: 46, color: '#8b929c', alignSelf: 'flex-start' }}>···</div>
          </div>
          <div style={{ marginTop: 34, fontSize: size, lineHeight: 1.28, fontWeight: 500, minHeight: size * 2.6 }}>
            {words.map((w, i) => (
              <span key={i} style={{ opacity: interpolate(shown - i, [0, 1], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }) }}>
                {w}{' '}
              </span>
            ))}
          </div>
          <div style={{ marginTop: 26, paddingTop: 24, borderTop: '1px solid rgba(255,255,255,0.08)', display: 'flex', justifyContent: 'space-between' }}>
            {ICONS.map((d, i) => <Icon key={i} d={d} />)}
          </div>
        </div>
      </AbsoluteFill>
      <Vignette strength={0.5} />
      <Grain opacity={0.06} id="post-grain" />
    </AbsoluteFill>
  );
};
