/**
 * atlas-diagram (fase 6): una ilustración SVG con capas identificadas (public/atlas-diagrams/*.svg) cuyas capas
 * cambian de estado con la voz (aparecer, colorearse, pasar a discontinua, moverse, girar) y llamadas con línea guía.
 * Los colores de la ilustración salen del tema por clases: el SVG no lleva colores propios de un vídeo.
 */
import type { FC } from 'react';
import { AbsoluteFill } from 'remotion';
import { ease, progress, reveal } from '../anim';
import { useAtlasTime, useScene, useTheme } from '../context';
import { useJsonFiles } from '../geo/useData';
import type { AtlasScene } from '../schema';
import { accentOn, themes, type ThemeName } from '../theme';
import { sec } from '../time';
import { Mono } from '../ui';
import { Header, useSceneOf } from './text';

type Diagram = Extract<AtlasScene, { type: 'atlas-diagram' }>;
type State = NonNullable<Diagram['states']>[number];

/** Paleta de dibujo: rellenos planos del tema (prompt maestro §4.16: sin degradados). */
const drawPalette = (theme: ThemeName) => {
  const t = themes[theme];
  return {
    ink: t.ink,
    paper: themes.paper.card,
    earth: '#D8C8A5',
    glass: '#A9C7DA',
    body: '#5F7690',
    bodyDark: '#2F4A63',
    amber: '#E3A64A',
    grey: '#8B8478',
    seat: '#C4B89E',
    seatBlue: '#7C93A8',
    red: t.accents.danger,
    good: themes.paper.accents.good,
  };
};

const colorOf = (theme: ThemeName, c: NonNullable<State['fill']>) => {
  const p = drawPalette(theme);
  switch (c) {
    case 'paper':
      return p.paper;
    case 'earth':
      return p.earth;
    case 'glass':
      return p.glass;
    case 'grey':
      return p.grey;
    case 'amber':
      return p.amber;
    case 'none':
      return 'none';
    default:
      return accentOn(theme, c);
  }
};

const hexLerp = (a: string, b: string, t: number) => {
  if (!a.startsWith('#') || !b.startsWith('#') || t >= 1) return t < 0.5 ? a : b;
  const pa = [1, 3, 5].map((i) => parseInt(a.slice(i, i + 2), 16));
  const pb = [1, 3, 5].map((i) => parseInt(b.slice(i, i + 2), 16));
  return '#' + pa.map((v, i) => Math.round(v + (pb[i] - v) * t).toString(16).padStart(2, '0')).join('');
};

interface Resolved {
  opacity: number;
  fill?: string;
  stroke?: string;
  dashed: boolean;
  x: number;
  y: number;
  rotate: number;
  scale: number;
}

/** Estado de una capa en el instante t: los cambios se encadenan, cada uno interpolando desde el anterior. */
const resolveLayer = (states: State[], theme: ThemeName, t: number): Resolved => {
  let cur: Resolved = { opacity: 1, dashed: false, x: 0, y: 0, rotate: 0, scale: 1 };
  for (const s of states) {
    const at = sec(s.at);
    if (t < at) break;
    const p = ease(Math.min(1, (t - at) / (s.seconds ?? 0.6)));
    const next: Resolved = {
      opacity: s.opacity ?? cur.opacity,
      fill: s.fill ? colorOf(theme, s.fill) : cur.fill,
      stroke: s.stroke ? colorOf(theme, s.stroke) : cur.stroke,
      dashed: s.dashed ?? cur.dashed,
      x: s.x ?? cur.x,
      y: s.y ?? cur.y,
      rotate: s.rotate ?? cur.rotate,
      scale: s.scale ?? cur.scale,
    };
    cur = {
      opacity: cur.opacity + (next.opacity - cur.opacity) * p,
      fill: next.fill && cur.fill ? hexLerp(cur.fill, next.fill, p) : next.fill,
      stroke: next.stroke && cur.stroke ? hexLerp(cur.stroke, next.stroke, p) : next.stroke,
      dashed: p > 0.5 ? next.dashed : cur.dashed,
      x: cur.x + (next.x - cur.x) * p,
      y: cur.y + (next.y - cur.y) * p,
      rotate: cur.rotate + (next.rotate - cur.rotate) * p,
      scale: cur.scale + (next.scale - cur.scale) * p,
    };
  }
  return cur;
};

const cssId = (id: string) => id.replace(/[^\w-]/g, '_');

export const DiagramScene: FC = () => {
  const scene = useSceneOf('atlas-diagram');
  const { index } = useScene();
  const { name, tokens } = useTheme();
  const time = useAtlasTime();
  const data = useJsonFiles<string>([scene.diagram]);
  if (!data) return null;
  const [raw] = data;
  const svgText = raw.replace(/<\?xml[^>]*>/, '').replace(/<!--[\s\S]*?-->/g, '');
  const vb = /viewBox="([\d.\s-]+)"/.exec(svgText)?.[1].split(/\s+/).map(Number) ?? [0, 0, 1000, 1000];
  const box = scene.box ?? { x: 260, y: 230, w: 1400, h: 760 };
  const k = Math.min(box.w / vb[2], box.h / vb[3]);
  const ox = box.x + (box.w - vb[2] * k) / 2;
  const oy = box.y + (box.h - vb[3] * k) / 2;
  const toScreen = ([x, y]: [number, number]) => [ox + (x - vb[0]) * k, oy + (y - vb[1]) * k] as const;
  const scope = `atlas-diagram-${index}`;
  const pal = drawPalette(name);

  // estilos: paleta por clases + el estado actual de cada capa con cambios
  const byLayer = new Map<string, State[]>();
  for (const s of [...(scene.states ?? [])].sort((a, b) => sec(a.at) - sec(b.at))) {
    byLayer.set(s.layer, [...(byLayer.get(s.layer) ?? []), s]);
  }
  const S = `#${scope}`;
  let css = `
    ${S} svg { width: 100%; height: 100%; overflow: visible; }
    ${S} .ink { stroke: ${pal.ink}; stroke-width: 3.5; stroke-linejoin: round; }
    ${S} .line { fill: none; stroke: ${pal.ink}; stroke-width: 3.5; stroke-linecap: round; }
    ${S} .dash-ink { stroke-dasharray: 8 9; stroke-width: 2; stroke-opacity: 0.55; }
    ${S} .paper { fill: ${pal.paper}; } ${S} .earth { fill: ${pal.earth}; } ${S} .glass { fill: ${pal.glass}; }
    ${S} .body { fill: ${pal.body}; } ${S} .body-dark { fill: ${pal.bodyDark}; } ${S} .amber { fill: ${pal.amber}; }
    ${S} .grey { fill: ${pal.grey}; } ${S} .seat { fill: ${pal.seat}; } ${S} .seat-blue { fill: ${pal.seatBlue}; }
    ${S} .red { fill: ${pal.red}; } ${S} .good { fill: #9FC2AE; } ${S} .good-dots { fill: ${pal.good}; }
  `;
  for (const [layer, states] of byLayer) {
    const r = resolveLayer(states, name, time);
    const sel = `${S} #${cssId(layer)}`;
    css += `${sel} { opacity: ${r.opacity.toFixed(3)}; transform-box: fill-box; transform-origin: center;
      transform: translate(${r.x}px, ${r.y}px) rotate(${r.rotate}deg) scale(${r.scale}); }`;
    if (r.fill) css += `${sel}, ${sel} * { fill: ${r.fill} !important; }`;
    if (r.stroke) css += `${sel}, ${sel} * { stroke: ${r.stroke} !important; }`;
    if (r.dashed) css += `${sel}, ${sel} * { stroke-dasharray: 12 9 !important; }`;
  }
  const appear = reveal(time, sec({ t: 0 }), 0.01);

  return (
    <AbsoluteFill>
      <style>{css}</style>
      <Header top={92} />
      <div id={scope} style={{ position: 'absolute', left: ox, top: oy, width: vb[2] * k, height: vb[3] * k, opacity: appear.opacity }}
           dangerouslySetInnerHTML={{ __html: svgText }} />
      <svg width={1920} height={1080} style={{ position: 'absolute', inset: 0 }}>
        {(scene.callouts ?? []).map((c, i) => {
          if (!c.anchor) return null;
          const p = progress(time, sec(c.at), 0.5);
          if (p <= 0) return null;
          const [ax, ay] = toScreen(c.anchor);
          const [lx, ly] = toScreen(c.label);
          const color = c.accent ? accentOn(name, c.accent) : tokens.ink;
          const ex = c.align === 'right' ? lx + 8 : c.align === 'center' ? lx : lx - 8;
          return (
            <g key={i}>
              <line x1={ax} y1={ay} x2={ax + (ex - ax) * p} y2={ay + (ly - ay) * p} stroke={color} strokeWidth={2} />
              <circle cx={ax} cy={ay} r={3.5} fill={color} />
            </g>
          );
        })}
      </svg>
      {(scene.callouts ?? []).map((c, i) => {
        const r = reveal(time, sec(c.at) + (c.anchor ? 0.25 : 0), 0.5);
        if (r.opacity <= 0) return null;
        const [lx, ly] = toScreen(c.label);
        const color = c.accent ? accentOn(name, c.accent) : tokens.ink;
        const align = c.align ?? 'left';
        const pos =
          align === 'left' ? { left: lx } : align === 'right' ? { right: 1920 - lx } : { left: lx - 500, width: 1000, textAlign: 'center' as const };
        return (
          <div key={`t${i}`} style={{ position: 'absolute', top: ly - (c.sub ? 26 : 14), ...pos, ...r.style, lineHeight: 1.25 }}>
            <Mono size={c.size ?? 24} color={color} tracking="0.16em" style={{ fontWeight: 600 }}>
              {c.text}
            </Mono>
            {c.sub ? (
              <div>
                <Mono size={c.size ?? 24} color={color} tracking="0.16em" style={{ fontWeight: 600 }}>
                  {c.sub}
                </Mono>
              </div>
            ) : null}
          </div>
        );
      })}
      {(scene.meters ?? []).map((m, i) => {
        const at = sec(m.at);
        const r = reveal(time, at - 0.4, 0.5);
        if (r.opacity <= 0) return null;
        const v = m.from + (m.to - m.from) * progress(time, at, m.seconds, (x) => x);
        const color = m.accent ? accentOn(name, m.accent) : pal.amber;
        return (
          <div key={`m${i}`} style={{ position: 'absolute', left: m.x, top: m.y, width: m.w, ...r.style }}>
            <Mono size={21} color={tokens.ink} tracking="0.16em">
              {m.label}
            </Mono>
            <div style={{ marginTop: 10, height: 34, border: `2.5px solid ${tokens.ink}`, background: themes.paper.card, position: 'relative' }}>
              <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: `${v * 100}%`, background: color }} />
            </div>
          </div>
        );
      })}
    </AbsoluteFill>
  );
};
