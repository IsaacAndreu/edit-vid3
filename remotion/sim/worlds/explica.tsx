// The wildcard world: for whatever no simulated world can show — a figure, a moment of history, a threshold curve, A
// against B, a chain of causes. Its words come from the line (graphic.texts, graphic.nums, cleaned in simulacion.py: a
// number only if the voice says it). Scenes (param scene):
//  dato      one big figure counting up, its label and a line under it
//  historia  a date and what happened: the year large, a card with who and what, a line of time behind
//  curva     a curve with its shape (forma: umbral, exponencial, lineal, campana, meseta), drawn as the voice goes,
//            its axes named, the turning point marked
//  comparar  A against B: two bars (with figures) or two cards
//  pasos     a chain of 3-5 steps lighting one after the other; bucle: the last feeds the first
import type {FC} from 'react';
import {AbsoluteFill, Easing, interpolate} from 'remotion';
import {C, FONT} from '../hud';
import {num} from '../i18n';
import {clamp, param, type World, type WorldProps} from '../world';

const Back: FC<{t: number}> = ({t}) => (
  <AbsoluteFill style={{background: 'radial-gradient(ellipse at 50% 40%, #16213a 0%, #0a0f1c 70%)'}}>
    <svg width={1920} height={1080} style={{position: 'absolute', opacity: 0.35}}>
      {Array.from({length: 25}, (_, i) => <line key={`v${i}`} x1={i * 80 + ((t * 6) % 80)} x2={i * 80 + ((t * 6) % 80)} y1={0} y2={1080} stroke="#1f2b45" />)}
      {Array.from({length: 14}, (_, i) => <line key={`h${i}`} x1={0} x2={1920} y1={i * 80} y2={i * 80} stroke="#1f2b45" />)}
    </svg>
  </AbsoluteFill>
);

const ease = (t: number, a: number, b: number) => interpolate(t, [a, b], [0, 1], {...clamp, easing: Easing.out(Easing.cubic)});

const Dato: FC<{texts: string[]; nums: number[]; t: number}> = ({texts, nums, t}) => {
  const k = ease(t, 0.2, 1.4);
  const value = nums.length ? num(nums[0] * k, Number.isInteger(nums[0]) ? 0 : 1) : texts[1] ?? '';
  return (
    <div style={{position: 'absolute', left: 0, right: 0, top: 260, textAlign: 'center', fontFamily: FONT}}>
      <div style={{fontSize: 46, fontWeight: 800, letterSpacing: 3, color: C.label, opacity: ease(t, 0, 0.5)}}>{texts[0] ?? ''}</div>
      <div style={{fontSize: 240, fontWeight: 800, color: C.accent, lineHeight: 1.05, fontVariantNumeric: 'tabular-nums', transform: `scale(${0.9 + 0.1 * k})`}}>
        {value}{nums.length && texts[1] ? <span style={{fontSize: 90, marginLeft: 20}}>{texts[1]}</span> : null}
      </div>
      <div style={{fontSize: 52, fontWeight: 800, color: C.text, opacity: ease(t, 0.9, 1.6), maxWidth: 1400, margin: '10px auto 0'}}>{texts[2] ?? ''}</div>
    </div>
  );
};

const Historia: FC<{texts: string[]; t: number}> = ({texts, t}) => {
  const k = ease(t, 0, 1.2);
  return (
    <>
      <svg width={1920} height={1080} style={{position: 'absolute'}}>
        <line x1={160} x2={1760} y1={760} y2={760} stroke="#3a4a6a" strokeWidth={6} />
        {Array.from({length: 9}, (_, i) => <line key={i} x1={160 + i * 200} x2={160 + i * 200} y1={745} y2={775} stroke="#3a4a6a" strokeWidth={4} />)}
        <circle cx={160 + 1600 * (0.15 + 0.6 * k)} cy={760} r={22} fill={C.you} />
      </svg>
      <div style={{position: 'absolute', left: 160, top: 150, fontFamily: FONT, fontSize: 260, fontWeight: 800, color: C.accent, lineHeight: 1,
                   opacity: ease(t, 0, 0.6), transform: `translateX(${(1 - k) * -40}px)`}}>{texts[0] ?? ''}</div>
      <div style={{position: 'absolute', left: 170, top: 450, width: 1500, fontFamily: FONT, opacity: ease(t, 0.5, 1.2)}}>
        <div style={{fontSize: 72, fontWeight: 800, color: C.text, textTransform: 'uppercase'}}>{texts[1] ?? ''}</div>
        <div style={{fontSize: 44, fontWeight: 700, color: C.label, marginTop: 10}}>{texts[2] ?? ''}</div>
      </div>
    </>
  );
};

const SHAPES: Record<string, (x: number) => number> = {
  umbral: (x) => (x < 0.7 ? 0.08 + x * 0.12 : 0.164 + Math.pow((x - 0.7) / 0.3, 2.2) * 0.8),
  exponencial: (x) => (Math.exp(3.2 * x) - 1) / (Math.exp(3.2) - 1),
  lineal: (x) => x,
  campana: (x) => Math.exp(-Math.pow((x - 0.5) / 0.18, 2)),
  meseta: (x) => 1 - Math.exp(-4 * x),
};

const Curva: FC<{texts: string[]; t: number; shape: string; length: number}> = ({texts, t, shape, length}) => {
  const f = SHAPES[shape] ?? SHAPES.umbral;
  const W = 1300;
  const H = 620;
  const x0 = 360;
  const y0 = 170;
  const grow = ease(t, 0.3, Math.max(1.5, length * 0.7));
  const pts = Array.from({length: 101}, (_, i) => i / 100).filter((x) => x <= grow).map((x) => `${x0 + x * W},${y0 + H - f(x) * H}`).join(' ');
  const knee = shape === 'umbral' ? 0.7 : shape === 'campana' ? 0.5 : shape === 'meseta' ? 0.35 : shape === 'exponencial' ? 0.75 : -1;
  return (
    <svg width={1920} height={1080} style={{position: 'absolute'}}>
      <line x1={x0} x2={x0} y1={y0} y2={y0 + H} stroke="#5b6b8a" strokeWidth={4} />
      <line x1={x0} x2={x0 + W} y1={y0 + H} y2={y0 + H} stroke="#5b6b8a" strokeWidth={4} />
      <text x={x0 - 30} y={y0 + H / 2} textAnchor="middle" fill={C.label} fontFamily={FONT} fontSize={38} fontWeight={800}
            transform={`rotate(-90 ${x0 - 30} ${y0 + H / 2})`}>{(texts[0] ?? '').toUpperCase()}</text>
      <text x={x0 + W / 2} y={y0 + H + 70} textAnchor="middle" fill={C.label} fontFamily={FONT} fontSize={38} fontWeight={800}>{(texts[1] ?? '').toUpperCase()} →</text>
      {knee > 0 && grow > knee && (
        <g opacity={ease(t, 0.3 + knee * Math.max(1.2, length * 0.7), 0.8 + knee * Math.max(1.2, length * 0.7))}>
          <line x1={x0 + knee * W} x2={x0 + knee * W} y1={y0} y2={y0 + H} stroke={C.red} strokeWidth={3} strokeDasharray="12 10" />
          <text x={x0 + knee * W + 16} y={y0 + 40} fill={C.red} fontFamily={FONT} fontSize={40} fontWeight={800}>{(texts[2] ?? '').toUpperCase()}</text>
        </g>
      )}
      <polyline points={pts} fill="none" stroke={C.accent} strokeWidth={9} strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
};

const Comparar: FC<{texts: string[]; nums: number[]; t: number}> = ({texts, nums, t}) => {
  const k = ease(t, 0.3, 1.6);
  const top = Math.max(1e-9, ...nums.slice(0, 2).map(Math.abs));
  return (
    <div style={{position: 'absolute', left: 0, right: 0, top: 200, display: 'flex', justifyContent: 'center', gap: 160, fontFamily: FONT}}>
      {[0, 1].map((i) => {
        const v = nums[i];
        const colour = i ? C.green : C.red;
        return (
          <div key={i} style={{width: 560, textAlign: 'center', opacity: ease(t, i * 0.4, i * 0.4 + 0.5)}}>
            <div style={{height: 480, display: 'flex', alignItems: 'flex-end', justifyContent: 'center'}}>
              {v !== undefined ? (
                <div style={{width: 260, height: 460 * (Math.abs(v) / top) * k, background: colour, borderRadius: 14}} />
              ) : (
                <div style={{width: 440, height: 300, border: `6px solid ${colour}`, borderRadius: 20, display: 'flex', alignItems: 'center', justifyContent: 'center',
                             fontSize: 120, fontWeight: 800, color: colour}}>{i ? 'B' : 'A'}</div>
              )}
            </div>
            {v !== undefined && <div style={{fontSize: 96, fontWeight: 800, color: colour, fontVariantNumeric: 'tabular-nums'}}>{num(v * k, Number.isInteger(v) ? 0 : 1)}</div>}
            <div style={{fontSize: 52, fontWeight: 800, color: C.text, textTransform: 'uppercase', marginTop: 8}}>{texts[i] ?? ''}</div>
          </div>
        );
      })}
    </div>
  );
};

const Pasos: FC<{texts: string[]; t: number; length: number; loop: boolean}> = ({texts, t, length, loop}) => {
  const steps = texts.slice(0, 5);
  const each = Math.max(0.8, (length * 0.8) / Math.max(1, steps.length));
  const W = 1700 / steps.length;
  return (
    <svg width={1920} height={1080} style={{position: 'absolute'}}>
      {steps.map((s, i) => {
        const on = ease(t, i * each, i * each + 0.5);
        const x = 110 + i * W;
        return (
          <g key={i} opacity={0.25 + 0.75 * on}>
            <rect x={x} y={400} width={W - 90} height={260} rx={22} fill={on > 0.9 ? '#1d2a44' : '#141c2e'} stroke={on > 0.9 ? C.accent : '#2a3a5a'} strokeWidth={5} />
            <foreignObject x={x + 16} y={420} width={W - 122} height={220}>
              <div style={{fontFamily: FONT, fontSize: steps.length > 4 ? 40 : 48, fontWeight: 800, color: C.text, textTransform: 'uppercase', textAlign: 'center',
                           display: 'flex', alignItems: 'center', justifyContent: 'center', height: 220, lineHeight: 1.1}}>{s}</div>
            </foreignObject>
            {i < steps.length - 1 && <path d={`M${x + W - 80},530 l50,0 m-16,-16 l16,16 l-16,16`} stroke={C.accent} strokeWidth={6} fill="none" opacity={ease(t, i * each + 0.4, i * each + 0.8)} />}
          </g>
        );
      })}
      {loop && steps.length > 1 && (
        <path d={`M${110 + (steps.length - 1) * W + (W - 90) / 2},680 C${110 + (steps.length - 1) * W},860 ${200},860 ${110 + (W - 90) / 2},680`}
              stroke={C.red} strokeWidth={6} fill="none" strokeDasharray="16 12" opacity={ease(t, steps.length * each, steps.length * each + 0.6)} />
      )}
    </svg>
  );
};

const View: FC<WorldProps> = ({g, real = 0, length}) => {
  const scene = param<string>(g, 'scene', 'dato');
  const texts = g.texts ?? [];
  const nums = g.nums ?? [];
  return (
    <AbsoluteFill>
      <Back t={real} />
      {scene === 'historia' ? <Historia texts={texts} t={real} />
        : scene === 'curva' ? <Curva texts={texts} t={real} shape={param<string>(g, 'forma', 'umbral')} length={length} />
          : scene === 'comparar' ? <Comparar texts={texts} nums={nums} t={real} />
            : scene === 'pasos' ? <Pasos texts={texts} t={real} length={length} loop={param<string>(g, 'bucle', 'no') === 'si'} />
              : <Dato texts={texts} nums={nums} t={real} />}
    </AbsoluteFill>
  );
};

export const explica: World = {View, ambient: 'none'};
