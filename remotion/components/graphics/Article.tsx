import type { FC, ReactNode } from 'react';
import { AbsoluteFill, Easing, interpolate, useCurrentFrame } from 'remotion';
import type { ArticleGraphic } from '../../graphics';
import { alpha, fontFamily, theme, titleFamily } from '../../theme';

export const CIRCLE_AT = 34;     // pipeline/timeline.py ARTICLE_CIRCLE: the first red circle
export const CIRCLE_STEP = 16;   // and one more every 16 frames

/** A phrase circled by hand in red: an oval drawn left to right around the words, slightly tilted. */
const Circled: FC<{ children: ReactNode; from: number }> = ({ children, from }) => {
  const frame = useCurrentFrame();
  const draw = interpolate(frame, [from, from + 12], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic) });
  return (
    <span style={{ position: 'relative', display: 'inline-block', whiteSpace: 'nowrap', color: draw > 0.5 ? '#ffffff' : undefined }}>
      {children}
      <span style={{
        position: 'absolute', left: '-8%', right: '-8%', top: '-14%', bottom: '-14%', border: '4px solid #e5262b',
        borderRadius: '50%', transform: 'rotate(-2.5deg)', clipPath: `inset(-10% ${(1 - draw) * 110}% -10% -10%)`,
        boxShadow: '0 0 0 1px rgba(229,38,43,0.25)',
      }} />
    </span>
  );
};

/**
 * A newspaper article on a dark navy desk, as aviation/business explainers show them: the outlet and byline in a
 * small card, the headline in a serif face, one paragraph of the story, and its key figures circled in red one by
 * one while the camera pushes in slowly.
 */
export const Article: FC<{ graphic: ArticleGraphic; durationInFrames: number }> = ({ graphic, durationInFrames }) => {
  const frame = useCurrentFrame();
  const enter = interpolate(frame, [0, 14], [0, 1], { extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic) });
  const push = interpolate(frame, [0, durationInFrames], [1, 1.07]);
  const circles = graphic.circles ?? [];

  // the body with each circled phrase wrapped (first occurrence, case-insensitive)
  const parts: ReactNode[] = [];
  let rest = graphic.body;
  circles.forEach((c, i) => {
    const at = rest.toLowerCase().indexOf(c.toLowerCase());
    if (at < 0) return;
    parts.push(rest.slice(0, at));
    parts.push(<Circled key={i} from={CIRCLE_AT + i * CIRCLE_STEP}>{rest.slice(at, at + c.length)}</Circled>);
    rest = rest.slice(at + c.length);
  });
  parts.push(rest);

  return (
    <AbsoluteFill style={{
      background: `radial-gradient(ellipse at 50% 30%, ${alpha(theme.panelRaised, 1)} 0%, ${theme.canvas} 80%)`,
      justifyContent: 'center', alignItems: 'center', overflow: 'hidden',
    }}>
      <div style={{ width: 1360, transform: `scale(${push}) translateY(${(1 - enter) * 40}px)`, opacity: enter, textAlign: 'center' }}>
        {graphic.outlet || graphic.author ? (
          <div style={{
            display: 'inline-flex', gap: 14, alignItems: 'center', backgroundColor: '#ffffff', color: '#111',
            padding: '8px 18px', borderRadius: 4, fontFamily, fontWeight: 700, fontSize: 26, marginBottom: 34,
          }}>
            {graphic.outlet ? <span style={{ textTransform: 'uppercase', letterSpacing: '0.06em' }}>{graphic.outlet}</span> : null}
            {graphic.outlet && graphic.author ? <span style={{ opacity: 0.4 }}>/</span> : null}
            {graphic.author ? <span style={{ fontWeight: 500 }}>Por {graphic.author}</span> : null}
          </div>
        ) : null}
        <div style={{ fontFamily: titleFamily, fontWeight: theme.motion === 'editorial' ? 400 : 800, fontSize: 70, lineHeight: 1.12, color: theme.text, marginBottom: 40 }}>
          {graphic.headline}
        </div>
        <div style={{
          fontFamily: titleFamily, fontSize: 40, lineHeight: 1.6, color: alpha(theme.text, 0.82), textAlign: 'left',
          maxWidth: 1200, margin: '0 auto',
        }}>
          {parts}
        </div>
      </div>
    </AbsoluteFill>
  );
};
