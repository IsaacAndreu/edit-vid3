// The look shared by the lab's formats: navy panels, small grey caps labels, orange accent, condensed type,
// section titles underlined in orange, tags for dates and places (the «simulation explainer» style).
import type {CSSProperties, FC, ReactNode} from 'react';
import {interpolate} from 'remotion';

export const C = {
  night: '#0b1020',
  panel: 'rgba(12, 18, 34, 0.92)',
  line: 'rgba(255,255,255,0.09)',
  label: '#93a0b8',
  text: '#f2f4f8',
  accent: '#f5a623',
  red: '#ff5d5d',
  green: '#3ddc84',
};
const ACCENT = C.accent;
/** The channel's accent colour (brand.accent) for every panel and mark of this render; none: the default orange. */
export const setAccent = (colour: string | undefined) => {
  C.accent = colour && /^#[0-9a-f]{3,8}$/i.test(colour) ? colour : ACCENT;
};
export const FONT = '"Barlow Condensed", "Oswald", sans-serif';
const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;

export const fade = (f: number, a: number, b: number, edge = 12) =>
  interpolate(f, [a, a + edge, b - edge, b], [0, 1, 1, 0], clamp);

/** A panel: navy glass with the accent along its left edge; it rises a little as it comes in, and its contents follow
 * a beat later (the edge first, then the words). */
export const Panel: FC<{style?: CSSProperties; o: number; children: ReactNode}> = ({style, o, children}) => (
  <div style={{position: 'absolute', background: C.panel, border: `1px solid ${C.line}`, borderRadius: 8, padding: '16px 22px 16px 26px',
               fontFamily: FONT, color: C.text, opacity: Math.min(1, o * 1.4), overflow: 'hidden',
               boxShadow: '0 18px 40px rgba(0,0,0,0.45), 0 2px 6px rgba(0,0,0,0.4)', backdropFilter: 'blur(6px)',
               transform: `translateY(${(1 - o) * 16}px)`, ...style}}>
    <div style={{position: 'absolute', left: 0, top: 0, bottom: 0, width: 4, background: C.accent,
                 transform: `scaleY(${Math.min(1, o * 1.6)})`, transformOrigin: 'top'}} />
    <div style={{opacity: interpolate(o, [0.35, 1], [0, 1], clamp)}}>{children}</div>
  </div>
);

export const Label: FC<{children: ReactNode; color?: string}> = ({children, color = C.label}) => (
  <div style={{fontSize: 15, fontWeight: 600, letterSpacing: 1.6, color, textTransform: 'uppercase'}}>{children}</div>
);

export const Section: FC<{text: string; o: number; f: number; start: number}> = ({text, o, f, start}) => (
  <div style={{position: 'absolute', left: 64, top: 52, fontFamily: FONT, opacity: o}}>
    <div style={{fontSize: 46, fontWeight: 800, color: C.text, letterSpacing: 1, textTransform: 'uppercase'}}>{text}</div>
    <div style={{height: 4, background: C.accent, marginTop: 4,
                 width: `${interpolate(f, [start, start + 18], [0, 100], clamp)}%`}} />
  </div>
);

export const Tag: FC<{text: string; o: number; style?: CSSProperties; color?: string}> = ({text, o, style, color = C.text}) => (
  <div style={{position: 'absolute', fontFamily: FONT, fontSize: 19, fontWeight: 700, letterSpacing: 1.2, color,
               background: C.panel, border: `1px solid ${C.line}`, borderRadius: 4, padding: '6px 12px', textTransform: 'uppercase',
               opacity: o, ...style}}>
    {text}
  </div>
);

