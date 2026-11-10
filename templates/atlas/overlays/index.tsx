/**
 * Superposiciones que se montan sobre cualquier escena vía `overlays[]`:
 * info-card, stamp, counter, legend. La nota de fuente (`sourceNote`) va en SourceNote.
 */
import type { FC } from 'react';
import { AbsoluteFill } from 'remotion';
import { progress, reveal, stampHit } from '../anim';
import { useAtlasTime, useScene, useTheme } from '../context';
import { fonts } from '../fonts';
import type { Overlay } from '../schema';
import { accentOn, themes } from '../theme';
import { sec } from '../time';
import { Caps, cornerStyle, Mono, PaperCard, RichTitle } from '../ui';

type OverlayOf<K extends Overlay['kind']> = Extract<Overlay, { kind: K }>;

const InfoCard: FC<{ overlay: OverlayOf<'info-card'> }> = ({ overlay }) => {
  const time = useAtlasTime();
  const { name } = useTheme();
  const start = sec(overlay.at);
  const enter = reveal(time, start, 0.5);
  const exit = overlay.until ? 1 - progress(time, sec(overlay.until), 0.5) : 1;
  if (enter.opacity <= 0) return null;
  return (
    <div style={{ ...cornerStyle(overlay.corner), ...enter.style, opacity: enter.opacity * exit }}>
      <PaperCard theme={name} padding="30px 40px 34px" style={{ minWidth: 440, maxWidth: 760 }}>
        {overlay.kicker ? (
          <div style={{ borderBottom: `1.5px solid ${themes.paper.inkSoft}`, paddingBottom: 12, marginBottom: 18 }}>
            <Caps size={22} color={themes.paper.inkSoft}>
              {overlay.kicker}
            </Caps>
          </div>
        ) : null}
        <RichTitle rich={overlay.title} theme={name} onCard size={overlay.lines?.length ? 38 : 60} />
        {overlay.lines?.map((line, i) => {
          const r = reveal(time, line.at ? sec(line.at) : start + 0.3 + i * 0.6, 0.5);
          return (
            <div
              key={i}
              style={{
                ...r.style,
                marginTop: 14,
                fontFamily: fonts.serif,
                fontWeight: 600,
                fontSize: 36,
                letterSpacing: '-0.01em',
                color: line.accent ? accentOn('paper', line.accent) : themes.paper.ink,
              }}
            >
              {line.text}
            </div>
          );
        })}
        {overlay.sub ? (
          <div style={{ marginTop: 14 }}>
            <Caps size={20} color={themes.paper.accents.data} tracking="0.1em">
              {overlay.sub}
            </Caps>
          </div>
        ) : null}
      </PaperCard>
    </div>
  );
};

/** Sello de caucho rojo: mono, girado −4°, entra con golpe de escala, tinta irregular. */
const Stamp: FC<{ overlay: OverlayOf<'stamp'> }> = ({ overlay }) => {
  const time = useAtlasTime();
  const { tokens } = useTheme();
  const hit = stampHit(time, sec(overlay.at));
  if (hit.opacity <= 0) return null;
  const color = tokens.accents.danger;
  const id = `stamp-${overlay.text.replace(/\W/g, '')}`;
  return (
    <div
      style={{
        position: 'absolute',
        left: `${overlay.x * 100}%`,
        top: `${overlay.y * 100}%`,
        transform: `translate(-50%, -50%) rotate(-4deg) scale(${hit.scale})`,
        opacity: hit.opacity * 0.95,
      }}
    >
      <svg width="0" height="0" style={{ position: 'absolute' }}>
        <filter id={id}>
          <feTurbulence type="fractalNoise" baseFrequency="0.7" numOctaves={2} seed={11} result="noise" />
          <feColorMatrix in="noise" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 -1.6 1.75" result="mask" />
          <feComposite in="SourceGraphic" in2="mask" operator="in" />
        </filter>
      </svg>
      <div
        style={{
          filter: `url(#${id})`,
          border: `5px solid ${color}`,
          borderRadius: 8,
          padding: '12px 26px',
          boxShadow: `inset 0 0 0 3px transparent, inset 0 0 0 6px ${color}`,
        }}
      >
        <Mono size={42} color={color} tracking="0.16em" style={{ fontWeight: 600 }}>
          {overlay.text}
        </Mono>
      </div>
    </div>
  );
};

/** Separa una cadena en números y texto: "1,440 km · 1 h 42" → [1440, " km · ", 1, " h ", 42]. */
const NUMBER_RE = /\d[\d,]*(?:\.\d+)?/g;
const splitNumbers = (s: string) => {
  const nums: { value: number; decimals: number; grouped: boolean; pad: number }[] = [];
  const text = s.split(NUMBER_RE);
  for (const m of s.match(NUMBER_RE) ?? []) {
    const plain = m.replace(/,/g, '');
    const decimals = plain.includes('.') ? plain.split('.')[1].length : 0;
    nums.push({ value: Number(plain), decimals, grouped: m.includes(','), pad: /^0\d/.test(plain) ? plain.length : 0 });
  }
  return { nums, text };
};
const formatNum = (v: number, f: { decimals: number; grouped: boolean; pad: number }) => {
  const s = v.toLocaleString('en-US', {
    minimumFractionDigits: f.decimals,
    maximumFractionDigits: f.decimals,
    useGrouping: f.grouped,
  });
  return f.pad ? s.padStart(f.pad, '0') : s;
};

/**
 * Interpola entre dos valores con la misma forma ("450 km · 0 h 32" → "1,440 km · 1 h 42"):
 * cada número cuenta; el último fotograma muestra exactamente el texto del storyboard.
 */
export const tweenValue = (from: string | null, to: string, p: number): string => {
  if (p >= 1) return to;
  const b = splitNumbers(to);
  const a = from ? splitNumbers(from) : { nums: b.nums.map((n) => ({ ...n, value: 0 })), text: b.text };
  if (a.nums.length !== b.nums.length || a.text.join('|') !== b.text.join('|')) return p < 0.5 && from ? from : to;
  let out = '';
  b.text.forEach((t, i) => {
    out += t;
    if (i < b.nums.length) out += formatNum(a.nums[i].value + (b.nums[i].value - a.nums[i].value) * p, b.nums[i]);
  });
  return out;
};

const Counter: FC<{ overlay: OverlayOf<'counter'> }> = ({ overlay }) => {
  const time = useAtlasTime();
  const { name } = useTheme();
  const enter = reveal(time, sec(overlay.at), 0.5);
  if (enter.opacity <= 0) return null;
  let current = overlay.steps[0].value;
  let previous: string | null = null;
  let p = 1;
  overlay.steps.forEach((step, i) => {
    const t = sec(step.at);
    if (time >= t) {
      previous = i > 0 ? overlay.steps[i - 1].value : null;
      current = step.value;
      p = progress(time, t, 1.0);
    }
  });
  const shown = time < sec(overlay.steps[0].at) ? tweenValue(null, current, 0) : tweenValue(previous, current, p);
  return (
    <div style={{ ...cornerStyle(overlay.corner), ...enter.style }}>
      <PaperCard theme={name} padding="28px 36px 30px" style={{ minWidth: 520 }}>
        <div style={{ borderBottom: `1.5px solid ${themes.paper.inkSoft}`, paddingBottom: 12, marginBottom: 16 }}>
          <Caps size={22} color={themes.paper.inkSoft}>
            {overlay.kicker}
          </Caps>
        </div>
        <div
          style={{
            fontFamily: fonts.serif,
            fontWeight: 600,
            fontSize: 64,
            letterSpacing: '-0.02em',
            fontVariantNumeric: 'tabular-nums',
            color: themes.paper.ink,
            whiteSpace: 'nowrap',
          }}
        >
          {shown}
        </div>
        {overlay.sub ? (
          <div style={{ marginTop: 8 }}>
            <Caps size={19} color={themes.paper.inkSoft} tracking="0.08em">
              {overlay.sub}
            </Caps>
          </div>
        ) : null}
      </PaperCard>
    </div>
  );
};

const Legend: FC<{ overlay: OverlayOf<'legend'> }> = ({ overlay }) => {
  const time = useAtlasTime();
  const { name } = useTheme();
  const enter = reveal(time, sec(overlay.at), 0.5);
  if (enter.opacity <= 0) return null;
  const night = name === 'night';
  return (
    <div style={{ ...cornerStyle(overlay.corner), ...enter.style }}>
      <div
        style={{
          backgroundColor: night ? 'rgba(25,39,51,0.55)' : themes.paper.card,
          border: `2px solid ${night ? 'rgba(237,230,211,0.35)' : themes.paper.inkSoft}`,
          padding: '20px 28px',
          display: 'flex',
          flexDirection: 'column',
          gap: 14,
        }}
      >
        {overlay.items.map((item, i) => {
          const color = accentOn(name, item.accent);
          return (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 22 }}>
              <svg width={64} height={30}>
                {item.style === 'fill' ? (
                  <rect x={4} y={3} width={56} height={24} fill={color} opacity={0.65} stroke={color} />
                ) : (
                  <line
                    x1={4}
                    x2={60}
                    y1={15}
                    y2={15}
                    stroke={color}
                    strokeWidth={4}
                    strokeDasharray={item.style === 'dashed' ? '9 7' : undefined}
                  />
                )}
              </svg>
              <Caps size={22} color={night ? themes.night.ink : themes.paper.ink}>
                {item.label}
              </Caps>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export const atlasOverlays: { [K in Overlay['kind']]: FC<{ overlay: OverlayOf<K> }> } = {
  'info-card': InfoCard,
  stamp: Stamp,
  counter: Counter,
  legend: Legend,
};

export const OverlayLayer: FC<{ overlays: Overlay[] | undefined }> = ({ overlays }) => {
  if (!overlays?.length) return null;
  return (
    <AbsoluteFill style={{ pointerEvents: 'none' }}>
      {overlays.map((overlay, i) => {
        const Component = atlasOverlays[overlay.kind] as FC<{ overlay: Overlay }>;
        return <Component key={i} overlay={overlay} />;
      })}
    </AbsoluteFill>
  );
};

/** Nota de fuente o de honestidad ("ILLUSTRATIVE") en mono diminuta al pie. */
export const SourceNote: FC = () => {
  const { scene, start } = useScene();
  const { tokens } = useTheme();
  const time = useAtlasTime();
  if (!scene.sourceNote) return null;
  return (
    <div style={{ position: 'absolute', right: 88, bottom: 40, opacity: 0.85 * progress(time, start + 0.4, 0.6) }}>
      <Mono size={16} color={tokens.inkSoft} tracking="0.16em">
        {scene.sourceNote}
      </Mono>
    </div>
  );
};
