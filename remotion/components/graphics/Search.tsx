import type { FC } from 'react';
import { AbsoluteFill, Easing, interpolate, useCurrentFrame } from 'remotion';
import type { SearchGraphic } from '../../graphics';
import { Grain, typed, Vignette } from './Paper';

const COLORS = ['#4285F4', '#EA4335', '#FBBC05', '#4285F4', '#34A853', '#EA4335'];
const BOX_W = 780;
const SIZE = 30; // the query's type size at rest
const CHAR = SIZE * 0.53; // average width of a letter of Poppins 500

/** Someone searches the question: the search engine's page, the camera close on the box while the question is
 * typed (it follows the cursor), then back to see the whole page. */
export const Search: FC<{ graphic: SearchGraphic; durationInFrames: number }> = ({ graphic, durationInFrames }) => {
  const frame = useCurrentFrame();
  const query = graphic.question;
  const speed = Math.max(0.7, Math.min(1.6, query.length / Math.max(20, durationInFrames * 0.5)));
  const start = 14;
  const shown = typed(query, frame, start, speed);
  const done = start + query.length / speed;
  const close = interpolate(frame, [0, start], [1, 2.3], { extrapolateRight: 'clamp', easing: Easing.inOut(Easing.cubic) });
  const back = interpolate(frame, [done + 6, done + 22], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.inOut(Easing.cubic) });
  const scale = close + (1.45 - close) * back;
  // the cursor, in page pixels from the centre: the camera keeps it a little right of the middle while typing
  const caret = -BOX_W / 2 + 34 + Math.min(shown.length, 46) * CHAR;
  const follow = Math.max(0, caret - 120) * (1 - back);
  const blink = Math.floor(frame / 8) % 2 === 0 || frame < done;
  const engine = graphic.engine || 'Google';
  const google = engine.toLowerCase() === 'google';
  return (
    <AbsoluteFill style={{ background: 'radial-gradient(ellipse 70% 65% at 50% 45%, #ffffff 0%, #ececec 55%, #bdbdbd 100%)', overflow: 'hidden' }}>
      <AbsoluteFill style={{ transform: `scale(${scale}) translate(${-follow}px, ${30 * (1 - back)}px)`, transformOrigin: '50% 47%' }}>
        <div style={{ position: 'absolute', left: 0, right: 0, top: 380, textAlign: 'center', fontFamily: "'Poppins'", fontWeight: 500, fontSize: 104, letterSpacing: -3 }}>
          {[...engine].map((c, i) => (
            <span key={i} style={{ color: google ? COLORS[i % COLORS.length] : '#333' }}>
              {c}
            </span>
          ))}
        </div>
        <div
          style={{
            position: 'absolute', left: 960 - BOX_W / 2, top: 530, width: BOX_W, height: 64, borderRadius: 32, background: '#fff',
            border: '1.5px solid #8a8a8a', boxShadow: '0 2px 8px rgba(0,0,0,0.12)', display: 'flex', alignItems: 'center', padding: '0 28px',
            fontFamily: "'Poppins'", fontWeight: 500, fontSize: SIZE, color: '#202124', whiteSpace: 'nowrap', overflow: 'hidden',
          }}
        >
          <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'clip' }}>
            {shown}
            <span style={{ opacity: blink ? 1 : 0, fontWeight: 400 }}>|</span>
          </span>
          <svg width="30" height="30" viewBox="0 0 24 24" style={{ marginLeft: 14, flex: 'none' }}>
            <circle cx="10" cy="10" r="6.5" stroke="#3c4043" strokeWidth="2.4" fill="none" />
            <line x1="15" y1="15" x2="21" y2="21" stroke="#3c4043" strokeWidth="2.6" strokeLinecap="round" />
          </svg>
        </div>
      </AbsoluteFill>
      <Vignette strength={0.28} />
      <Grain opacity={0.12} id="search-grain" />
    </AbsoluteFill>
  );
};
