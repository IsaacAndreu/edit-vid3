import type { FC } from 'react';
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import type { GpsGraphic, PhoneGraphic, WantedGraphic } from '../../graphics';
import { alpha, condensedFamily, fontFamily, theme } from '../../theme';
import { GridBackground } from '../GridBackground';

// Video-game graphics for channels about a game. Colours come from the channel's brand (theme): the accent is the
// game's interface colour, accent2 its «danger» colour. Every text on them comes from the script
// (pipeline/graphics.py, game_graphic).

const STAR_FIRST = 18; // keep in sync with pipeline/timeline.py (graphic_cues, «wanted»)
const STAR_STEP = 7;

const starPath = (cx: number, cy: number, r: number): string => {
  const points: string[] = [];
  for (let i = 0; i < 10; i++) {
    const radius = i % 2 === 0 ? r : r * 0.45;
    const angle = -Math.PI / 2 + (i * Math.PI) / 5;
    points.push(`${(cx + radius * Math.cos(angle)).toFixed(1)},${(cy + radius * Math.sin(angle)).toFixed(1)}`);
  }
  return `M${points.join('L')}Z`;
};

const fadeIn = (frame: number, at = 0, length = 10) =>
  interpolate(frame, [at, at + length], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });

/** The wanted level: five stars light up one by one (as many as the script says, else all five flash between the
 * two police colours), under what brought the police. */
export const Wanted: FC<{ graphic: WantedGraphic; durationInFrames: number }> = ({ graphic }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const lit = graphic.stars ?? 5;
  const flashing = !graphic.stars;
  const head = fadeIn(frame, 0, 12);
  const R = 92;
  const gap = 230;
  const x0 = 960 - 2 * gap;
  return (
    <AbsoluteFill style={{ fontFamily }}>
      <GridBackground />
      <div style={{ position: 'absolute', top: 250, left: 0, right: 0, textAlign: 'center', opacity: head,
        transform: `translateY(${(1 - head) * 30}px)`, fontFamily: condensedFamily, fontWeight: 700, fontSize: 92,
        letterSpacing: 4, color: theme.text, textShadow: theme.shadow, textTransform: 'uppercase', padding: '0 120px' }}>
        {graphic.title}
      </div>
      <svg width={1920} height={1080} style={{ position: 'absolute', left: 0, top: 0 }}>
        {Array.from({ length: 5 }, (_, i) => {
          const at = STAR_FIRST + i * STAR_STEP;
          const on = i < lit && frame >= at;
          const pop = on ? spring({ frame: frame - at, fps, config: { damping: 9, stiffness: 220 } }) : 0;
          const blink = flashing && on ? Math.floor((frame - STAR_FIRST) / 6) % 2 === 0 : false;
          const color = on ? (flashing ? (blink ? theme.accent : theme.accent2) : theme.accent) : 'transparent';
          const cx = x0 + i * gap;
          const cy = 600;
          return (
            <g key={i}>
              <path d={starPath(cx, cy, R)} fill="none" stroke={alpha(theme.text, 0.35)} strokeWidth={6} strokeLinejoin="round" />
              {on ? (
                <path d={starPath(cx, cy, R * (0.6 + 0.4 * pop))} fill={color} stroke={alpha('#000000', 0.6)} strokeWidth={5}
                  strokeLinejoin="round" style={{ filter: `drop-shadow(0 0 22px ${alpha(color, 0.75)})` }} />
              ) : null}
            </g>
          );
        })}
      </svg>
    </AbsoluteFill>
  );
};

const PhoneIcon: FC<{ size: number; color: string }> = ({ size, color }) => (
  <svg width={size} height={size} viewBox="0 0 24 24">
    <path fill={color} d="M6.6 10.8a15.1 15.1 0 0 0 6.6 6.6l2.2-2.2a1 1 0 0 1 1-.25 11.4 11.4 0 0 0 3.6.57 1 1 0 0 1 1 1V20a1 1 0 0 1-1 1A17 17 0 0 1 3 4a1 1 0 0 1 1-1h3.5a1 1 0 0 1 1 1c0 1.25.2 2.45.57 3.6a1 1 0 0 1-.25 1z" />
  </svg>
);

/** The character's phone slides up: a message typed into a bubble under who sent it, or an incoming call. */
export const Phone: FC<{ graphic: PhoneGraphic; durationInFrames: number }> = ({ graphic, durationInFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const rise = spring({ frame, fps, config: { damping: 18, stiffness: 110 } });
  const W = 520;
  const H = 960;
  const words = graphic.text.split(' ');
  const typed = Math.round(interpolate(frame, [16, Math.max(24, durationInFrames * 0.55)], [0, words.length],
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }));
  const ring = graphic.kind === 'llamada' ? Math.sin(frame / 2.2) * 6 * (frame % 30 < 18 ? 1 : 0) : 0;
  return (
    <AbsoluteFill style={{ fontFamily }}>
      <GridBackground />
      <div style={{ position: 'absolute', left: 960 - W / 2, top: 1080 - (H + 60) * rise, width: W, height: H,
        borderRadius: 64, background: '#050607', border: `10px solid ${alpha(theme.text, 0.18)}`,
        boxShadow: `0 40px 90px rgba(0,0,0,0.7), 0 0 80px ${alpha(theme.accent, 0.18)}`, overflow: 'hidden' }}>
        <div style={{ position: 'absolute', inset: 0, background: `linear-gradient(180deg, ${alpha(theme.accent, 0.16)}, ${theme.panel ?? '#0c1411'} 60%)` }} />
        <div style={{ position: 'absolute', top: 70, left: 0, right: 0, textAlign: 'center' }}>
          <div style={{ width: 150, height: 150, margin: '0 auto', borderRadius: '50%', background: alpha(theme.accent, 0.2),
            border: `4px solid ${theme.accent}`, display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontFamily: condensedFamily, fontSize: 84, fontWeight: 700, color: theme.accent }}>
            {graphic.from.trim().charAt(0).toUpperCase()}
          </div>
          <div style={{ marginTop: 22, fontFamily: condensedFamily, fontWeight: 700, fontSize: 52, color: theme.text, padding: '0 30px' }}>
            {graphic.from}
          </div>
        </div>
        {graphic.kind === 'llamada' ? (
          <>
            <div style={{ position: 'absolute', top: 420, left: 40, right: 40, textAlign: 'center', fontSize: 36, lineHeight: 1.3,
              color: alpha(theme.text, 0.85) }}>{words.slice(0, typed).join(' ')}</div>
            <div style={{ position: 'absolute', bottom: 90, left: 0, right: 0, display: 'flex', justifyContent: 'space-around' }}>
              {[theme.negative, theme.positive].map((color, i) => (
                <div key={i} style={{ width: 130, height: 130, borderRadius: '50%', background: color, display: 'flex',
                  alignItems: 'center', justifyContent: 'center', transform: `rotate(${i === 0 ? 135 : ring}deg)` }}>
                  <PhoneIcon size={64} color="#ffffff" />
                </div>
              ))}
            </div>
          </>
        ) : (
          <div style={{ position: 'absolute', top: 400, left: 34, right: 70, padding: '26px 30px', borderRadius: '34px 34px 34px 8px',
            background: theme.panelRaised ?? alpha(theme.text, 0.12), border: `2px solid ${alpha(theme.accent, 0.4)}`,
            fontSize: 38, lineHeight: 1.32, color: theme.text, opacity: fadeIn(frame, 12, 6) }}>
            {words.slice(0, Math.max(1, typed)).join(' ')}
            {typed < words.length ? <span style={{ color: theme.accent }}> ▌</span> : null}
          </div>
        )}
      </div>
    </AbsoluteFill>
  );
};

/** The minimap: streets of a city seen from above, the route drawing itself to the marker, and the place named. */
export const Gps: FC<{ graphic: GpsGraphic; durationInFrames: number }> = ({ graphic, durationInFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const S = 760;
  const draw = interpolate(frame, [8, Math.min(durationInFrames * 0.6, 70)], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const pin = spring({ frame: frame - 62, fps, config: { damping: 10, stiffness: 180 } });
  const pulse = (frame % 40) / 40;
  const route = 'M 120 660 L 120 520 L 300 520 L 300 330 L 520 330 L 520 200 L 610 200';
  const length = 140 + 180 + 190 + 220 + 130 + 90;
  const label = fadeIn(frame, 40, 14);
  const streets: string[] = [];
  for (let i = 0; i <= 8; i++) {
    streets.push(`M ${i * 95} 0 L ${i * 95 + 40} ${S}`);
    streets.push(`M 0 ${i * 95} L ${S} ${i * 95 - 30}`);
  }
  return (
    <AbsoluteFill style={{ fontFamily }}>
      <GridBackground />
      <div style={{ position: 'absolute', left: 170, top: 160, width: S, height: S, borderRadius: 40, overflow: 'hidden',
        background: theme.land, border: `6px solid ${alpha(theme.accent, 0.55)}`, boxShadow: '0 30px 80px rgba(0,0,0,0.6)' }}>
        <svg width={S} height={S}>
          <rect x={0} y={560} width={S} height={200} fill={theme.ocean} />
          {streets.map((d, i) => <path key={i} d={d} stroke={alpha(theme.text, 0.13)} strokeWidth={i % 3 ? 6 : 12} />)}
          <path d={route} fill="none" stroke={theme.accent} strokeWidth={16} strokeLinecap="round" strokeLinejoin="round"
            strokeDasharray={length} strokeDashoffset={length * (1 - draw)} style={{ filter: `drop-shadow(0 0 10px ${alpha(theme.accent, 0.7)})` }} />
          <circle cx={120} cy={660} r={18} fill="#ffffff" stroke="#000000" strokeWidth={4} />
          <circle cx={610} cy={200} r={30 + 70 * pulse} fill="none" stroke={theme.accent2} strokeWidth={5} opacity={pin * (1 - pulse)} />
          <g transform={`translate(610 200) scale(${pin}) translate(0 -8)`}>
            <path d="M0 0 C -34 -46 -34 -86 0 -86 C 34 -86 34 -46 0 0 Z" fill={theme.accent2} stroke="#000000" strokeWidth={4} />
            <circle cx={0} cy={-58} r={13} fill="#ffffff" />
          </g>
        </svg>
      </div>
      <div style={{ position: 'absolute', left: 1010, top: 360, width: 760, opacity: label, transform: `translateX(${(1 - label) * 40}px)` }}>
        {graphic.note ? (
          <div style={{ fontSize: 34, letterSpacing: 3, color: theme.accent, textTransform: 'uppercase', fontWeight: 700 }}>{graphic.note}</div>
        ) : null}
        <div style={{ fontFamily: condensedFamily, fontWeight: 700, fontSize: 110, lineHeight: 1.02, color: theme.text, textShadow: theme.shadow }}>
          {graphic.place}
        </div>
        {graphic.distance ? (
          <div style={{ marginTop: 18, display: 'inline-block', padding: '10px 22px', borderRadius: 12, background: alpha(theme.accent, 0.18),
            border: `2px solid ${theme.accent}`, fontSize: 44, fontWeight: 800, color: theme.accent }}>{graphic.distance}</div>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};
