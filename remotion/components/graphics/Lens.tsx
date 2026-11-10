import type { CSSProperties, FC } from 'react';
import { AbsoluteFill, Easing, interpolate, useCurrentFrame } from 'remotion';
import type { LensGraphic } from '../../graphics';
import { Grain, Vignette } from './Paper';

const R = 150; // the glass
const ZOOM = 1.75;

/** A short line in big letters on white paper; a magnifying glass sweeps across it and stops on the last word,
 * the letters under the glass enlarged with a little colour fringe. */
export const Lens: FC<{ graphic: LensGraphic; durationInFrames: number }> = ({ graphic, durationInFrames }) => {
  const frame = useCurrentFrame();
  const text = graphic.text.toUpperCase();
  const size = text.length > 22 ? 96 : text.length > 14 ? 120 : 140;
  const width = text.length * size * 0.47; // Oswald 700 capitals
  const last = text.split(' ').pop() || text;
  const stop = 960 + width / 2 - (last.length * size * 0.47) / 2;
  const travel = Math.min(durationInFrames * 0.7, 70);
  const x = interpolate(frame, [0, travel], [-260, stop], { extrapolateRight: 'clamp', easing: Easing.inOut(Easing.cubic) });
  const y = 540 + Math.sin(frame / 9) * 10 * (frame < travel ? 1 : 0.3);
  const line: CSSProperties = {
    position: 'absolute', left: 0, right: 0, top: 540 - size * 0.62, height: size * 1.3, textAlign: 'center', fontFamily: "'Oswald'", fontWeight: 700,
    fontSize: size, letterSpacing: 2, color: '#1b1b1b', whiteSpace: 'nowrap',
  };
  const top = 540 - size * 0.62;
  const zoomed = (color: string, dx: number): CSSProperties => ({
    ...line, color, transform: `translateX(${dx}px) scale(${ZOOM})`, transformOrigin: `${x}px ${y - top}px`,
  });
  return (
    <AbsoluteFill style={{ backgroundColor: '#e7e6e2', overflow: 'hidden' }}>
      <AbsoluteFill style={{ background: 'radial-gradient(ellipse 60% 55% at 50% 50%, rgba(255,255,255,0.85), rgba(255,255,255,0) 70%)' }} />
      <div style={line}>{text}</div>
      {/* under the glass */}
      <div style={{ position: 'absolute', inset: 0, clipPath: `circle(${R - 8}px at ${x}px ${y}px)`, backgroundColor: '#f1f0ec' }}>
        <div style={{ ...zoomed('rgba(230,40,40,0.55)', -4), mixBlendMode: 'multiply' }}>{text}</div>
        <div style={{ ...zoomed('rgba(30,170,230,0.55)', 4), mixBlendMode: 'multiply' }}>{text}</div>
        <div style={zoomed('#111', 0)}>{text}</div>
        <div style={{ position: 'absolute', left: x - R, top: y - R, width: 2 * R, height: 2 * R, borderRadius: '50%',
          background: 'radial-gradient(circle at 35% 30%, rgba(255,255,255,0.35), rgba(255,255,255,0) 45%)' }} />
      </div>
      {/* the glass, its ring and the handle */}
      <svg width="1920" height="1080" style={{ position: 'absolute', inset: 0, overflow: 'visible' }}>
        <g transform={`translate(${x} ${y})`} style={{ filter: 'drop-shadow(8px 14px 10px rgba(0,0,0,0.35))' }}>
          <g transform="rotate(42)">
            <rect x={R + 2} y={-15} width={46} height={30} rx={6} fill="#c9a032" />
            <rect x={R + 46} y={-18} width={190} height={36} rx={16} fill="#121212" />
          </g>
          <circle r={R} fill="none" stroke="#151515" strokeWidth={16} />
          <circle r={R - 8} fill="none" stroke="rgba(255,255,255,0.4)" strokeWidth={2} />
        </g>
      </svg>
      <Vignette strength={0.42} />
      <Grain opacity={0.14} id="lens-grain" />
    </AbsoluteFill>
  );
};
