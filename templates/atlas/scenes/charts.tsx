/**
 * Gráficos sin geografía (fase 2): dial, bar-compare, dot-density, runway-compare.
 * Las cifras cuentan y terminan exactamente en el texto del storyboard.
 */
import type { FC } from 'react';
import { AbsoluteFill, random } from 'remotion';
import { progress, reveal } from '../anim';
import { useAtlasTime, useTheme } from '../context';
import { fonts } from '../fonts';
import { PlaneTop } from '../icons';
import { tweenValue } from '../overlays';
import { accentOn, themes } from '../theme';
import { sec } from '../time';
import { Mono, RichTitle, richText } from '../ui';
import { Center, Header, useAtOr, useSceneOf } from './text';

const HEADER_TOP = 126;

/* ── atlas-dial ─────────────────────────────────────────────────────────── */

const polar = (cx: number, cy: number, r: number, frac: number) => {
  const a = frac * 2 * Math.PI - Math.PI / 2;
  return [cx + r * Math.cos(a), cy + r * Math.sin(a)] as const;
};

/** Sector entre dos fracciones de vuelta (0 = arriba, sentido horario). */
const sectorPath = (cx: number, cy: number, r: number, a: number, b: number) => {
  if (b - a >= 0.9999) return `M ${cx - r} ${cy} a ${r} ${r} 0 1 0 ${2 * r} 0 a ${r} ${r} 0 1 0 ${-2 * r} 0`;
  if (b - a <= 0.0001) return '';
  const [x1, y1] = polar(cx, cy, r, a);
  const [x2, y2] = polar(cx, cy, r, b);
  return `M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${b - a > 0.5 ? 1 : 0} 1 ${x2} ${y2} Z`;
};

export const DialScene: FC = () => {
  const scene = useSceneOf('atlas-dial');
  const { name, tokens } = useTheme();
  const time = useAtlasTime();
  const atOr = useAtOr();
  const { dial } = scene;
  const start = sec(dial.at);
  const p = progress(time, start, dial.seconds, (x) => x);
  const value = dial.from + (dial.to - dial.from) * p;
  const frac = Math.min(1, value / dial.max);
  const color = accentOn(name, dial.accent);
  const cx = 960;
  const cy = 556;
  const r = 192;
  const face = reveal(time, atOr(undefined, 0.2));
  const [a, b] = dial.fill === 'elapsed' ? [0, frac] : [frac, 1];
  const [hx, hy] = polar(cx, cy, r * 0.98, frac);
  const readoutAt = atOr(scene.readout.at, 0.4);
  const r0 = reveal(time, readoutAt);
  const shownValue = p >= 1 ? String(dial.to) : String(Math.round(value));
  const { text, accent } = richText(scene.readout.text);
  const readout = text.replace('{value}', shownValue);
  return (
    <AbsoluteFill>
      <Header top={HEADER_TOP} />
      <svg width={1920} height={1080} style={{ position: 'absolute', ...face.style }}>
        <circle cx={cx} cy={cy} r={r} fill={themes.paper.card} />
        <path d={sectorPath(cx, cy, r, a, b)} fill={color} opacity={dial.accent === 'good' ? 0.4 : 0.3} />
        {Array.from({ length: 12 }, (_, i) => {
          const [x1, y1] = polar(cx, cy, r - 2, i / 12);
          const [x2, y2] = polar(cx, cy, r - 24, i / 12);
          return <line key={i} x1={x1} y1={y1} x2={x2} y2={y2} stroke={tokens.ink} strokeWidth={3} />;
        })}
        <circle cx={cx} cy={cy} r={r} fill="none" stroke={tokens.ink} strokeWidth={4} />
        {dial.hand !== false && p > 0 ? <line x1={cx} y1={cy} x2={hx} y2={hy} stroke={color} strokeWidth={5} strokeLinecap="round" /> : null}
        <circle cx={cx} cy={cy} r={8} fill={tokens.ink} />
      </svg>
      <Center top={scene.readout.style === 'mono' ? 774 : 750} style={r0.style}>
        {scene.readout.style === 'mono' ? (
          <Mono size={36} color={tokens.ink} tracking="0.16em" style={{ fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>
            {readout}
          </Mono>
        ) : (
          <RichTitle rich={{ text: readout, accent }} theme={name} size={84} defaultAccent="good" style={{ fontVariantNumeric: 'tabular-nums' }} />
        )}
      </Center>
    </AbsoluteFill>
  );
};

/* ── atlas-bar-compare ──────────────────────────────────────────────────── */

const formatAxis = (format: string, v: number) => format.replace('{v}', v.toLocaleString('en-US'));

export const BarCompareScene: FC = () => {
  const scene = useSceneOf('atlas-bar-compare');
  const { name, tokens } = useTheme();
  const time = useAtlasTime();
  const atOr = useAtOr();
  const { axis, bars } = scene;
  const hasTitle = Boolean(scene.title);
  const top = hasTitle ? 236 : 260;
  const base = hasTitle ? 900 : 860;
  const left = scene.labels === 'above' ? 520 : 380;
  const right = scene.side ? 1500 : 1540;
  const y = (v: number) => base - (v / axis.max) * (base - top);
  const n = bars.length;
  const slot = scene.labels === 'above' ? Math.min(200, (right - left) / (n + 1.6)) : (right - left) / (n + 0.6);
  const barW = scene.labels === 'above' ? Math.min(100, slot * 0.5) : Math.min(280, slot * 0.62);
  const cx = (i: number) => left + slot * (0.8 + i);
  const axisIn = reveal(time, atOr(undefined, 0.15));
  const ticks = Array.from({ length: Math.floor(axis.max / axis.step) + 1 }, (_, i) => i * axis.step);
  const earthFill = '#C9B48E';
  return (
    <AbsoluteFill>
      <Header top={hasTitle ? HEADER_TOP - 34 : HEADER_TOP} />
      <svg width={1920} height={1080} style={{ position: 'absolute' }}>
        <defs>
          <pattern id="atlas-hatch" width="20" height="36" patternUnits="userSpaceOnUse">
            <rect width="20" height="36" fill="#F3EEE3" />
            <line x1="0" y1="35" x2="20" y2="35" stroke={themes.paper.accents.data} strokeOpacity={0.25} strokeWidth={2} />
          </pattern>
        </defs>
        <g opacity={axisIn.opacity}>
          {scene.threshold?.band ? (
            <rect
              x={left}
              y={top}
              width={right - left}
              height={y(scene.threshold.value) - top}
              fill={accentOn(name, scene.threshold.accent)}
              opacity={0.13 * progress(time, sec(scene.threshold.at), 0.6)}
            />
          ) : null}
          {ticks.map((v) =>
            axis.style === 'grid' ? (
              v > 0 ? (
                <line key={v} x1={left} x2={right} y1={y(v)} y2={y(v)} stroke={tokens.inkSoft} strokeOpacity={0.45} strokeWidth={2} strokeDasharray="2 8" />
              ) : null
            ) : (
              <line key={v} x1={left - 14} x2={left} y1={y(v)} y2={y(v)} stroke={tokens.ink} strokeWidth={2} />
            ),
          )}
          {axis.style === 'ticks' ? <line x1={left} x2={left} y1={top} y2={base} stroke={tokens.ink} strokeWidth={2} /> : null}
          <line x1={left - (axis.style === 'grid' ? 80 : 0)} x2={right} y1={base} y2={base} stroke={tokens.ink} strokeWidth={3} />
        </g>
        {bars.map((bar, i) => {
          const g = progress(time, sec(bar.at), 1.0);
          const h = (base - y(bar.value)) * g;
          const x = cx(i) - barW / 2;
          return (
            <g key={i}>
              <rect
                x={x}
                y={base - h}
                width={barW}
                height={h}
                fill={bar.style === 'hatched' ? 'url(#atlas-hatch)' : earthFill}
                stroke={bar.style === 'hatched' ? themes.paper.accents.data : tokens.ink}
                strokeWidth={3}
              />
            </g>
          );
        })}
        {scene.ghost
          ? (() => {
              const gh = scene.ghost;
              const p = progress(time, sec(gh.at), 0.6);
              const x = cx(gh.bar) - barW / 2;
              const yTop = y(gh.value);
              const yBar = y(bars[gh.bar].value);
              return (
                <g opacity={p}>
                  <path
                    d={`M ${x} ${yBar} L ${x} ${yTop} L ${x + barW} ${yTop} L ${x + barW} ${yBar}`}
                    fill="none"
                    stroke={tokens.ink}
                    strokeWidth={2.5}
                    strokeDasharray="8 7"
                  />
                </g>
              );
            })()
          : null}
        {scene.threshold
          ? (() => {
              const th = scene.threshold;
              const p = progress(time, sec(th.at), 0.8);
              return (
                <line
                  x1={left}
                  x2={left + (right - left) * p}
                  y1={y(th.value)}
                  y2={y(th.value)}
                  stroke={accentOn(name, th.accent)}
                  strokeWidth={3}
                  strokeDasharray="12 8"
                />
              );
            })()
          : null}
      </svg>
      {/* Etiquetas del eje */}
      {ticks.map((v) =>
        axis.style === 'grid' && v === 0 ? null : (
          <div
            key={v}
            style={{ position: 'absolute', right: 1920 - left + (axis.style === 'grid' ? 24 : 28), top: y(v) - 13, opacity: axisIn.opacity }}
          >
            <Mono size={21} color={tokens.inkSoft} tracking="0.14em">
              {formatAxis(axis.format, v)}
            </Mono>
          </div>
        ),
      )}
      {axis.base ? (
        <div
          style={{
            position: 'absolute',
            ...(axis.style === 'grid' ? { right: 1920 - right, top: base - 40 } : { left: (left + right) / 2 - 100, width: 200, top: base + 18, textAlign: 'center' }),
            opacity: axisIn.opacity,
          }}
        >
          <Mono size={21} color={tokens.inkSoft} tracking="0.16em">
            {axis.base}
          </Mono>
        </div>
      ) : null}
      {bars.map((bar, i) => {
        const at = sec(bar.at);
        const g = progress(time, at, 1.0);
        const label = reveal(time, at);
        const value = tweenValue(null, bar.display, g);
        const yTop = base - (base - y(bar.value)) * g;
        const insideGhost = scene.ghost?.bar === i;
        const valueColor = accentOn(name, bar.valueAccent, tokens.ink);
        return (
          <div key={i}>
            {scene.labels === 'below' ? (
              <>
                <div style={{ position: 'absolute', left: cx(i) - 250, width: 500, top: base + 22, textAlign: 'center', ...label.style }}>
                  <span style={{ fontFamily: fonts.serifItalic, fontStyle: 'italic', fontSize: 38, letterSpacing: '0.24em', color: tokens.ink }}>
                    {bar.label}
                  </span>
                </div>
                <div
                  style={{
                    position: 'absolute',
                    left: cx(i) - 200,
                    width: 400,
                    top: insideGhost ? yTop + 18 : yTop - 74,
                    textAlign: 'center',
                    opacity: label.opacity,
                    fontFamily: fonts.serif,
                    fontWeight: 600,
                    fontSize: 44,
                    letterSpacing: '-0.02em',
                    color: valueColor,
                  }}
                >
                  {value}
                </div>
              </>
            ) : (
              <div style={{ position: 'absolute', left: cx(i) - 160, width: 320, top: yTop - 100, textAlign: 'center', opacity: label.opacity }}>
                <div style={{ fontFamily: fonts.serif, fontWeight: 600, fontSize: 32, letterSpacing: '-0.02em', color: tokens.ink }}>{bar.label}</div>
                <Mono size={23} color={valueColor} tracking="0.12em" style={{ fontVariantNumeric: 'tabular-nums' }}>
                  {value}
                </Mono>
              </div>
            )}
            {bar.inside ? (
              <div
                style={{
                  position: 'absolute',
                  left: cx(i) - barW / 2,
                  width: barW,
                  top: base - (base - y(bar.value)) * 0.55,
                  textAlign: 'center',
                  opacity: progress(time, at + 0.8, 0.5),
                }}
              >
                <Mono size={24} color={themes.paper.accents.data} tracking="0.2em">
                  {bar.inside}
                </Mono>
              </div>
            ) : null}
          </div>
        );
      })}
      {scene.ghost ? (
        <div
          style={{
            position: 'absolute',
            left: cx(scene.ghost.bar) + barW / 2 + 22,
            top: y(scene.ghost.value) - 14,
            opacity: progress(time, sec(scene.ghost.at), 0.6),
          }}
        >
          <Mono size={22} color={themes.paper.accents.data} tracking="0.16em">
            {scene.ghost.label}
          </Mono>
        </div>
      ) : null}
      {scene.threshold ? (
        <div style={{ position: 'absolute', right: 1920 - right, top: y(scene.threshold.value) - 40, opacity: progress(time, sec(scene.threshold.at) + 0.5, 0.5) }}>
          <Mono size={22} color={accentOn(name, scene.threshold.accent)} tracking="0.16em">
            {scene.threshold.label}
          </Mono>
        </div>
      ) : null}
      {scene.side
        ? (() => {
            const side = scene.side;
            const sAt = sec(side.at);
            return (
              <div style={{ position: 'absolute', left: right + 80, top: top + 120, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 18 }}>
                <div style={reveal(time, sAt).style}>
                  <Mono size={19} color={tokens.inkSoft} tracking="0.18em">
                    {side.kicker}
                  </Mono>
                </div>
                {side.items.map((item, i) => (
                  <div
                    key={i}
                    style={{
                      ...reveal(time, sAt + 0.35 * (i + 1)).style,
                      width: 260,
                      padding: '10px 0',
                      textAlign: 'center',
                      border: `3px solid ${tokens.ink}`,
                      backgroundColor: themes.paper.card,
                    }}
                  >
                    <Mono size={22} color={tokens.ink} tracking="0.2em" style={{ fontWeight: 600 }}>
                      {item}
                    </Mono>
                  </div>
                ))}
              </div>
            );
          })()
        : null}
    </AbsoluteFill>
  );
};

/* ── atlas-dot-density ──────────────────────────────────────────────────── */

export const DotDensityScene: FC = () => {
  const scene = useSceneOf('atlas-dot-density');
  const { name, tokens } = useTheme();
  const time = useAtlasTime();
  const n = scene.boxes.length;
  const box = 360;
  const gap = 110;
  const left0 = (1920 - (n * box + (n - 1) * gap)) / 2;
  const top = 362;
  const cells = scene.grid * scene.grid;
  return (
    <AbsoluteFill>
      <Header top={HEADER_TOP} />
      {scene.boxes.map((b, i) => {
        const at = sec(b.at);
        const r = reveal(time, at);
        const drop = progress(time, at + 0.4, 1.4);
        const pct = 100 + (b.percent - 100) * drop;
        const keep = Math.round((cells * pct) / 100);
        // Orden de eliminación fijo por caja: siempre desaparecen los mismos puntos.
        const order = Array.from({ length: cells }, (_, k) => k).sort((x, y) => random(`dot-${i}-${x}`) - random(`dot-${i}-${y}`));
        const kept = new Set(order.slice(0, keep));
        const color = b.accent ? accentOn(name, b.accent) : tokens.inkSoft;
        const cell = (box - 24) / scene.grid;
        const left = left0 + i * (box + gap);
        return (
          <div key={i} style={{ position: 'absolute', left, top, width: box, ...r.style }}>
            <svg width={box} height={box}>
              <rect x={1.5} y={1.5} width={box - 3} height={box - 3} fill={themes.paper.card} stroke={tokens.ink} strokeWidth={3} />
              {Array.from({ length: cells }, (_, k) => {
                const gx = k % scene.grid;
                const gy = Math.floor(k / scene.grid);
                const jx = (random(`jx-${i}-${k}`) - 0.5) * cell * 0.16;
                const jy = (random(`jy-${i}-${k}`) - 0.5) * cell * 0.16;
                const visible = kept.has(k);
                return (
                  <circle
                    key={k}
                    cx={12 + cell * (gx + 0.5) + jx}
                    cy={12 + cell * (gy + 0.5) + jy}
                    r={6}
                    fill={color}
                    opacity={visible ? (b.accent ? 0.6 : 0.75) : 0}
                  />
                );
              })}
            </svg>
            <div style={{ textAlign: 'center', marginTop: 30 }}>
              <Mono size={22} color={tokens.inkSoft} tracking="0.18em">
                {b.label}
              </Mono>
              <div
                style={{
                  fontFamily: fonts.serif,
                  fontWeight: 600,
                  fontSize: 56,
                  letterSpacing: '-0.02em',
                  color: b.accent ? accentOn(name, b.accent) : tokens.ink,
                  fontVariantNumeric: 'tabular-nums',
                }}
              >
                {tweenValue('100%', b.display, drop)}
              </div>
            </div>
          </div>
        );
      })}
    </AbsoluteFill>
  );
};

/* ── atlas-runway-compare ───────────────────────────────────────────────── */

export const RunwayCompareScene: FC = () => {
  const scene = useSceneOf('atlas-runway-compare');
  const { tokens } = useTheme();
  const time = useAtlasTime();
  const left = 280;
  const width = 1340;
  const firstTop = 526;
  const spacing = 220;
  const runwayH = 68;
  return (
    <AbsoluteFill>
      <Header top={HEADER_TOP} />
      {scene.notes?.map((note, i) => (
        <Center key={i} top={300 + i * 46} style={reveal(time, sec(note.at)).style}>
          <Mono size={27} color={tokens.ink} tracking="0.18em" style={{ fontWeight: 500 }}>
            {note.text}
          </Mono>
        </Center>
      ))}
      <svg width={1920} height={1080} style={{ position: 'absolute' }}>
        {scene.runways.map((rw, i) => {
          const at = sec(rw.at);
          const y = firstTop + i * spacing;
          const show = progress(time, at - 0.6, 0.5);
          // Acelera desde parado: posición ∝ t² hasta el despegue, luego sigue a velocidad constante.
          const t = Math.max(0, time - at);
          const u = t / rw.seconds;
          const along = u <= 1 ? rw.liftoff * u * u : rw.liftoff + 2 * rw.liftoff * (u - 1);
          const px = left + 40 + Math.min(1.02, along) * (width - 60);
          const lifted = u >= 1;
          const liftX = left + 40 + rw.liftoff * (width - 60);
          const climb = lifted ? Math.min(1, (u - 1) * 2) : 0;
          return (
            <g key={i} opacity={show}>
              <rect x={left} y={y} width={width} height={runwayH} fill="#57524A" />
              {Array.from({ length: 24 }, (_, k) => (
                <line
                  key={k}
                  x1={left + 20 + k * 56}
                  x2={left + 50 + k * 56}
                  y1={y + runwayH / 2}
                  y2={y + runwayH / 2}
                  stroke="#E9E2D0"
                  strokeOpacity={0.8}
                  strokeWidth={3}
                />
              ))}
              {lifted ? (
                <g opacity={progress(time, at + rw.seconds, 0.3)}>
                  <line x1={liftX} x2={liftX} y1={y - 12} y2={y + runwayH + 14} stroke={themes.paper.accents.good} strokeWidth={3} />
                </g>
              ) : null}
              {/* Sombra en el suelo y avión que se separa al despegar */}
              <PlaneTop size={64} fill="rgba(0,0,0,0.25)" stroke="none" x={px + climb * 10} y={y + runwayH / 2 + climb * 16} />
              <PlaneTop size={64 + climb * 10} fill="#F4EFE2" stroke={tokens.ink} x={px} y={y + runwayH / 2} />
            </g>
          );
        })}
      </svg>
      {scene.runways.map((rw, i) => {
        const at = sec(rw.at);
        const y = firstTop + i * spacing;
        const liftX = left + 40 + rw.liftoff * (width - 60);
        return (
          <div key={i}>
            <div style={{ position: 'absolute', left, top: y - 46, opacity: progress(time, at - 0.6, 0.5) }}>
              <Mono size={24} color={tokens.ink} tracking="0.18em">
                {rw.label}
              </Mono>
            </div>
            {rw.liftoffLabel ? (
              <div style={{ position: 'absolute', left: liftX - 10, top: y + runwayH + 16, opacity: progress(time, at + rw.seconds, 0.4) }}>
                <Mono size={20} color={themes.paper.accents.good} tracking="0.18em">
                  {rw.liftoffLabel}
                </Mono>
              </div>
            ) : null}
          </div>
        );
      })}
      {scene.footer ? (
        <Center top={958} style={reveal(time, sec(scene.footer.at)).style}>
          <Mono size={25} color={accentOn('paper', scene.footer.accent ?? 'data')} tracking="0.18em">
            {scene.footer.text}
          </Mono>
        </Center>
      ) : null}
    </AbsoluteFill>
  );
};
