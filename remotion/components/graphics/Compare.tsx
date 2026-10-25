import type { FC } from 'react';
import { AbsoluteFill, Easing, Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';
import { fontFamily, theme } from '../../theme';
import type { CompareGraphic } from '../../graphics';
import { GridBackground } from '../GridBackground';
import { GraphicTitle } from './GraphicTitle';
import type { CompareSide } from '../../graphics';
import { MediaBox } from './MediaBox';


/** A value counting up, with the same decimals as the final figure. */
const format = (n: number, target: number) => {
  const decimals = Math.min(3, (String(target).split('.')[1] ?? '').length);
  return n.toLocaleString('es-ES', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
};

/** The picture of a side: its photo in the avatar circle, else its logo on a white card, else its initials — never an
 * empty circle. */
const Badge: FC<{ side: CompareSide; color: string; durationInFrames: number }> = ({ side, color, durationInFrames }) =>
  side.media ? (
    <MediaBox media={side.media} width={200} height={200} durationInFrames={durationInFrames} style={{ borderRadius: '50%', borderColor: color }} face />
  ) : side.logo ? (
    <div style={{ width: 200, height: 200, borderRadius: 32, backgroundColor: '#f4f4f2', border: `4px solid ${color}`, display: 'flex',
      alignItems: 'center', justifyContent: 'center', boxShadow: '0 20px 60px rgba(0,0,0,0.6)' }}>
      <Img src={staticFile(side.logo.src)} style={{ width: 150, height: 150, objectFit: 'contain' }} />
    </div>
  ) : (
    <div style={{ width: 200, height: 200, borderRadius: '50%', border: `4px solid ${color}`, display: 'flex', alignItems: 'center',
      justifyContent: 'center', background: `radial-gradient(circle at 35% 30%, ${color}55, #111 75%)`, fontFamily, fontWeight: 900,
      fontSize: 84, color: '#fff', boxShadow: '0 20px 60px rgba(0,0,0,0.6)' }}>
      {side.name.split(/\s+/).filter((w) => /^\p{L}/u.test(w)).slice(0, 2).map((w) => w[0]).join('').toUpperCase()}
    </div>
  );

/** A vs B: the two sides with photo and name, and one row per figure with bars growing from the
 * centre (the better value of each row glows). */
export const Compare: FC<{ graphic: CompareGraphic; durationInFrames: number }> = ({ graphic, durationInFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enter = spring({ frame, fps, config: { damping: 200, stiffness: 120 } });
  const rows = graphic.rows.slice(0, 5);
  const side = (name: string, align: 'left' | 'right') => (
    <div
      style={{
        fontFamily,
        fontWeight: 900,
        fontSize: 54,
        color: align === 'left' ? theme.accent : theme.accent2,
        textAlign: align,
        textShadow: theme.shadow,
      }}
    >
      {name.toUpperCase()}
    </div>
  );
  return (
    <AbsoluteFill>
      <GridBackground />
      {graphic.title ? <GraphicTitle text={graphic.title} /> : null}
      <div style={{ position: 'absolute', top: 190, left: 110, right: 110, display: 'flex', justifyContent: 'space-between' }}>
        <div style={{ opacity: enter, transform: `translateX(${(1 - enter) * -60}px)`, display: 'flex', gap: 28, alignItems: 'center' }}>
          <Badge side={graphic.left} color={theme.accent} durationInFrames={durationInFrames} />
          {side(graphic.left.name, 'left')}
        </div>
        <div style={{ fontFamily, fontWeight: 900, fontSize: 70, color: theme.muted, alignSelf: 'center', opacity: enter }}>VS</div>
        <div style={{ opacity: enter, transform: `translateX(${(1 - enter) * 60}px)`, display: 'flex', gap: 28, alignItems: 'center' }}>
          {side(graphic.right.name, 'right')}
          <Badge side={graphic.right} color={theme.accent2} durationInFrames={durationInFrames} />
        </div>
      </div>
      <div style={{ position: 'absolute', top: 470, left: 110, right: 110, display: 'flex', flexDirection: 'column', gap: 34 }}>
        {rows.map((row, i) => {
          const grow = interpolate(frame, [14 + i * 10, 40 + i * 10], [0, 1], {
            extrapolateLeft: 'clamp',
            extrapolateRight: 'clamp',
            easing: Easing.out(Easing.cubic),
          });
          const max = Math.max(Math.abs(row.a), Math.abs(row.b)) || 1;
          const aWins = row.better === 'low' ? row.a < row.b : row.a > row.b;
          const bWins = row.better === 'low' ? row.b < row.a : row.b > row.a;
          const unit = row.unit ? ` ${row.unit}` : '';
          const bar = (value: number, color: string, wins: boolean, dir: 'left' | 'right') => (
            <div style={{ flex: 1, display: 'flex', justifyContent: dir === 'left' ? 'flex-end' : 'flex-start' }}>
              <div
                style={{
                  width: `${(Math.abs(value) / max) * 100 * grow}%`,
                  height: 46,
                  backgroundColor: color,
                  opacity: wins ? 1 : 0.45,
                  borderRadius: dir === 'left' ? '8px 0 0 8px' : '0 8px 8px 0',
                  boxShadow: wins ? `0 0 30px ${color}` : 'none',
                }}
              />
            </div>
          );
          return (
            <div key={i} style={{ fontFamily, opacity: Math.min(1, grow * 3) }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', color: theme.text, fontWeight: 800, fontSize: 40 }}>
                <span style={{ color: aWins ? theme.accent : theme.text }}>{format(row.a * grow, row.a)}{unit}</span>
                <span style={{ color: theme.muted, fontWeight: 600, fontSize: 32 }}>{row.label}</span>
                <span style={{ color: bWins ? theme.accent2 : theme.text }}>{format(row.b * grow, row.b)}{unit}</span>
              </div>
              <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                {bar(row.a, theme.accent, aWins, 'left')}
                {bar(row.b, theme.accent2, bWins, 'right')}
              </div>
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
