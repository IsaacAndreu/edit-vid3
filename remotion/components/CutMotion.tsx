import type { FC, ReactNode } from 'react';
import { AbsoluteFill, Easing, useCurrentFrame } from 'remotion';

export interface Transition {
  kind: 'zoom' | 'whip';
  from: number; // the cut is in the middle: from + durationInFrames / 2
  durationInFrames: number;
}

const ease = Easing.in(Easing.quad);

/**
 * Motion on key cuts (the ones with a whoosh): the outgoing shot punches in (zoom) or flies off
 * sideways (whip) with motion blur, and the incoming one lands from the same move. Wraps the
 * footage and graphics layers; labels and credits stay still on top.
 */
export const CutMotion: FC<{ transitions?: Transition[]; children: ReactNode }> = ({ transitions = [], children }) => {
  const frame = useCurrentFrame();
  const t = transitions.find((x) => frame >= x.from && frame < x.from + x.durationInFrames);
  if (!t) return <AbsoluteFill>{children}</AbsoluteFill>;
  const half = t.durationInFrames / 2;
  const d = frame - (t.from + half); // -half … half-1
  const k = ease(Math.max(0, 1 - Math.abs(d + 0.5) / half)); // 0 at the edges, 1 at the cut
  const blur = (t.kind === 'zoom' ? 12 : 18) * k;
  const transform =
    t.kind === 'zoom'
      ? `scale(${1 + 0.32 * k})`
      : // the shot grows as it slides so its edge never shows (1920 px wide: +2·|x|/1920)
        `translateX(${(d < 0 ? -1 : 1) * 520 * k}px) scale(${1 + (2 * 520 * k) / 1920 + 0.02})`;
  return (
    <AbsoluteFill style={{ overflow: 'hidden', backgroundColor: '#000' }}>
      <AbsoluteFill style={{ transform, filter: blur > 0.3 ? `blur(${blur.toFixed(1)}px)` : undefined }}>{children}</AbsoluteFill>
      {t.kind === 'zoom' ? <AbsoluteFill style={{ backgroundColor: '#fff', opacity: 0.22 * k ** 3 }} /> : null}
    </AbsoluteFill>
  );
};
