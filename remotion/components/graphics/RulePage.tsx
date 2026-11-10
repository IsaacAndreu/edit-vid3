import type { FC } from 'react';
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { theme } from '../../theme';
import type { RuleGraphic } from '../../graphics';
import { Highlighted } from './Highlighted';
import { Stamp, stampShake } from './Stamp';

const RULE_STAMP = 44; // keep in sync with pipeline/timeline.py
const SERIF = 'Georgia, "Times New Roman", "DejaVu Serif", serif';

/** A page of the rulebook: the rule in focus among blurred paragraphs, a marker sweeps the key part
 * and, when the rule bans something, a red stamp slams onto the page. */
export const RulePage: FC<{ graphic: RuleGraphic; durationInFrames: number }> = ({ graphic, durationInFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enter = spring({ frame, fps, config: { damping: 200, stiffness: 100 } });
  const push = interpolate(frame, [0, durationInFrames], [1, 1.07]);
  const filler = (rows: number, key: string) => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14, filter: 'blur(2px)', opacity: 0.4 }}>
      {Array.from({ length: rows }, (_, l) => (
        <div key={key + l} style={{ height: 13, backgroundColor: '#3f3a33', width: `${96 - ((l * 17) % 34)}%` }} />
      ))}
    </div>
  );
  return (
    <AbsoluteFill
      style={{
        backgroundColor: theme.canvas,
        backgroundImage: `radial-gradient(ellipse at 50% 45%, rgba(255,255,255,0.08) 0%, rgba(0,0,0,0.65) 75%)`,
        overflow: 'hidden',
      }}
    >
      <div
        style={{
          position: 'absolute',
          left: 360,
          top: 90,
          width: 1200,
          height: 980,
          padding: '60px 80px',
          backgroundColor: '#f6f3ec',
          color: '#1b1813',
          fontFamily: SERIF,
          boxShadow: '0 40px 90px rgba(0,0,0,0.6)',
          opacity: enter,
          transform: `translateY(${(1 - enter) * 120}px) rotate(-1.2deg) scale(${push}) ${stampShake(frame, RULE_STAMP)}`,
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', borderBottom: '2px solid #1b1813', paddingBottom: 14 }}>
          <div style={{ fontWeight: 700, fontSize: 34, letterSpacing: 3 }}>{graphic.source.toUpperCase()}</div>
          {graphic.article ? <div style={{ fontSize: 30, color: '#5a5245' }}>{graphic.article}</div> : null}
        </div>
        <div style={{ marginTop: 36 }}>{filler(5, 'a')}</div>
        <div style={{ marginTop: 36, fontSize: 50, lineHeight: 1.35, fontWeight: 600 }}>
          <Highlighted text={graphic.text} phrase={graphic.highlight} from={14} to={34} color="rgba(255, 214, 0, 0.7)" />
        </div>
        <div style={{ marginTop: 36 }}>{filler(6, 'b')}</div>
        {graphic.stamp ? <Stamp text={graphic.stamp} at={RULE_STAMP} size={130} style={{ right: 70, bottom: 150 }} /> : null}
      </div>
    </AbsoluteFill>
  );
};
