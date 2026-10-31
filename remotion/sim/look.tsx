// What every traffic world shares so a video reads as one: the cars coloured by their speed (green going well, amber
// slow, red stopped — with the brake glow), the colour key once a video, and the arrows that point at what the voice
// names («este coche», «la onda», «el hueco») at the moment it names it.
import type {FC} from 'react';
import {interpolate} from 'remotion';
import {C, FONT} from './hud';
import {addWords, tx} from './i18n';

addWords({
  fast: {es: 'Va bien', pt: 'Anda bem', fr: 'Roule bien', de: 'Fließt', en: 'Moving'},
  slow: {es: 'Lento', pt: 'Lento', fr: 'Lent', de: 'Langsam', en: 'Slow'},
  standing: {es: 'Parado', pt: 'Parado', fr: 'À l’arrêt', de: 'Steht', en: 'Stopped'},
});

export const PAINT = {fast: '#3ddc84', slow: '#f5b041', stopped: '#ff4d4d'};

const mix = (a: string, b: string, k: number) => {
  const p = (h: string, i: number) => parseInt(h.slice(1 + 2 * i, 3 + 2 * i), 16);
  const c = [0, 1, 2].map((i) => Math.round(p(a, i) + (p(b, i) - p(a, i)) * Math.max(0, Math.min(1, k))));
  return `rgb(${c[0]}, ${c[1]}, ${c[2]})`;
};

/** A car's colour by its speed `v` against the road's free speed `top` (m/s). */
export const paint = (v: number, top: number) => {
  if (v < 0.6) return PAINT.stopped;
  const k = v / Math.max(0.1, top);
  return k >= 0.6 ? mix(PAINT.slow, PAINT.fast, (k - 0.6) / 0.25) : mix(PAINT.stopped, PAINT.slow, (k - 0.08) / 0.3);
};

/** The trail behind a car: how long (0 → 1) for its speed. */
export const trail = (v: number, top: number) => Math.max(0, Math.min(1, (v / Math.max(0.1, top) - 0.25) / 0.75));

/** The colour key: comes in with the first traffic shot of the video and stays a few seconds. */
export const Legend: FC<{local: number; at?: string}> = ({local, at = 'top'}) => {
  const o = interpolate(local, [0.4, 0.9, 7, 7.6], [0, 1, 1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  if (o <= 0) return null;
  const item = (colour: string, text: string) => (
    <div style={{display: 'flex', alignItems: 'center', gap: 10}}>
      <span style={{width: 34, height: 16, borderRadius: 5, background: colour, boxShadow: colour === PAINT.stopped ? `0 0 14px ${colour}` : 'none'}} />
      <span>{text}</span>
    </div>
  );
  const place = at === 'right' ? {right: 48, top: '50%', flexDirection: 'column' as const, gap: 14, transform: `translateY(-50%) translateX(${(1 - o) * 12}px)`}
    : at === 'bottom' ? {left: '50%', bottom: 64, gap: 28, transform: `translateX(-50%) translateY(${(1 - o) * 12}px)`}
      : {left: '50%', top: 40, gap: 28, transform: `translateX(-50%) translateY(${(1 - o) * -12}px)`};
  return (
    <div style={{position: 'absolute', display: 'flex', padding: '12px 20px', borderRadius: 8, background: C.panel,
                 border: `1px solid ${C.line}`, fontFamily: FONT, fontSize: 24, fontWeight: 800, letterSpacing: 1.2, color: C.text,
                 textTransform: 'uppercase', opacity: o, ...place}}>
      {item(PAINT.fast, tx('fast'))}
      {item(PAINT.slow, tx('slow'))}
      {item(PAINT.stopped, tx('standing'))}
    </div>
  );
};

export type Mark = {kind: string; at: number; text: string};
export type Anchor = {x: number; y: number};
const HOLD = 2.8;

/** The arrows of the shot: each one points at its anchor (screen pixels, from the world) from above, its words over
 * it, from the moment the voice says them for ~3 s. Anchors the world does not have are skipped. */
export const Pointers: FC<{marks?: Mark[]; local: number; at: Record<string, Anchor | null | undefined>}> = ({marks, local, at}) =>
  !(marks ?? []).some((m) => at[m.kind] && local - m.at > -0.1 && local - m.at < HOLD) ? null : (
  <svg width={1920} height={1080} style={{position: 'absolute', overflow: 'visible', pointerEvents: 'none'}}>
    {(marks ?? []).map((m) => {
      const p = at[m.kind];
      const t = local - m.at;
      if (!p || t < -0.1 || t > HOLD) return null;
      const o = interpolate(t, [-0.1, 0.15, HOLD - 0.35, HOLD], [0, 1, 1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
      const bob = 8 * Math.sin(t * 5);
      const up = p.y > 260;                                 // near the top: the label goes underneath
      const tipY = up ? p.y - 34 : p.y + 34;
      const baseY = up ? tipY - 70 + bob : tipY + 70 - bob;
      const labelY = up ? baseY - 22 : baseY + 46;
      const w = Math.max(120, m.text.length * 17 + 36);
      const x = Math.max(w / 2 + 20, Math.min(1900 - w / 2, p.x));
      return (
        <g key={`${m.kind}${m.at}`} opacity={o}>
          <line x1={p.x} y1={baseY} x2={p.x} y2={tipY + (up ? -14 : 14)} stroke={C.accent} strokeWidth={6} strokeLinecap="round" />
          <path d={up ? `M${p.x - 16},${tipY - 16} L${p.x},${tipY + 4} L${p.x + 16},${tipY - 16} Z` : `M${p.x - 16},${tipY + 16} L${p.x},${tipY - 4} L${p.x + 16},${tipY + 16} Z`}
                fill={C.accent} />
          <rect x={x - w / 2} y={labelY - 34} width={w} height={46} rx={8} fill={C.accent} />
          <text x={x} y={labelY - 2} textAnchor="middle" fill="#10131a" fontFamily={FONT} fontSize={30} fontWeight={800} letterSpacing={1}>{m.text}</text>
        </g>
      );
    })}
  </svg>
);
