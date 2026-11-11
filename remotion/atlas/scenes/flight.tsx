/**
 * Escenas de vuelos reales (prompts/accidentes-plan.md): perfil en el tiempo (altitud con el terreno, velocidad o
 * motores), cabina en texto, silueta de avión con piezas resaltadas y «lo que se sabe». Todo lo que sale de un vuelo
 * se lee de vuelo.json en cada fotograma; los textos y las citas llegan del storyboard con su fuente.
 */
import type { FC } from 'react';
import { AbsoluteFill } from 'remotion';
import { progress, reveal } from '../anim';
import { useAtlasTime, useTheme } from '../context';
import { clockToS, flightClock, FlightHud, fmtInt, sampleAt, sToClock, videoTimeOf, type FlightData, type FlightPoint } from '../flight';
import { fonts } from '../fonts';
import { useJsonFiles } from '../geo/useData';
import { PLANE_SIDE_PATH } from '../icons';
import { accentOn, themes } from '../theme';
import { sec } from '../time';
import { Mono, PaperCard, RichTitle, richText } from '../ui';
import { Header, useSceneOf } from './text';

const X0 = 300;
const X1 = 1660;
const Y0 = 880;
const TOP = 270;
const EARTH = '#C9B48E';

/* ── Perfil del vuelo ─────────────────────────────────────────────────────────────────────────────────────────── */

export const FlightProfileScene: FC = () => {
  const scene = useSceneOf('atlas-flight-profile');
  const { name, tokens } = useTheme();
  const time = useAtlasTime();
  const data = useJsonFiles<FlightData>([scene.flight.data]);
  if (!data) return null;
  const [flight] = data;
  const from = clockToS(scene.flight.from);
  const to = clockToS(scene.flight.to);
  const now = flightClock(scene.flight, time);
  const { axis } = scene;
  const X = (s: number) => X0 + ((X1 - X0) * (s - from)) / (to - from || 1);
  const Y = (v: number) => Y0 - ((Y0 - TOP) * Math.max(0, Math.min(v, axis.max * 1.06))) / axis.max;
  const pts = flight.points.filter((p) => p.s >= from && p.s <= to);
  const value = (p: FlightPoint, k = 0): number | null =>
    scene.series === 'alt' ? Math.max(0, p.alt) : scene.series === 'kias' ? p.kias : p.n1[k];
  const lines = scene.series === 'n1' ? [0, 1] : [0];
  const line = (k: number, until: number) => {
    const shown = pts.filter((p) => p.s <= until);
    shown.push(sampleAt(flight, until));
    let d = '';
    let pen = false;
    for (const p of shown) {
      const v = value(p, k);
      if (v === null) {
        pen = false;
        continue;
      }
      d += `${pen ? 'L' : 'M'}${X(p.s).toFixed(1)},${Y(v).toFixed(1)}`;
      pen = true;
    }
    return d;
  };
  const tip = sampleAt(flight, now);
  const ticks = Array.from({ length: Math.floor(axis.max / axis.step) + 1 }, (_, i) => i * axis.step);
  // marcas del eje del tiempo: cada minuto entero dentro del tramo
  const minutes: number[] = [];
  for (let m = Math.ceil(from / 60) * 60; m <= to; m += 60) minutes.push(m);
  const appear = reveal(time, sec(scene.start), 0.6).opacity;
  const colors = [accentOn(name, 'danger'), accentOn(name, 'data')];
  const terrainD =
    scene.terrain && scene.series === 'alt' && pts.every((p) => p.terrain !== undefined)
      ? `M${X(pts[0].s)},${Y0} ` + pts.map((p) => `L${X(p.s).toFixed(1)},${Y(p.terrain ?? 0).toFixed(1)}`).join(' ') + ` L${X(pts[pts.length - 1].s)},${Y0} Z`
      : null;
  const tipV = value(tip, 0);
  const slope = (() => {
    const b = sampleAt(flight, now + 3);
    const vb = value(b, 0);
    if (tipV === null || vb === null) return 0;
    return (Math.atan2(Y(vb) - Y(tipV), X(now + 3) - X(now)) * 180) / Math.PI;
  })();

  return (
    <AbsoluteFill>
      <Header top={92} />
      <svg width={1920} height={1080} style={{ position: 'absolute', inset: 0, opacity: appear }}>
        {ticks.map((v) => (
          <g key={v}>
            {v > 0 ? <line x1={X0} x2={X1} y1={Y(v)} y2={Y(v)} stroke={tokens.inkSoft} strokeOpacity={0.45} strokeWidth={2} strokeDasharray="2 8" /> : null}
            <text x={X0 - 20} y={Y(v) + 7} textAnchor="end" fontFamily={fonts.mono} fontWeight={500} fontSize={21} letterSpacing={2.5} fill={tokens.inkSoft}>
              {fmtInt(v)} {axis.unit}
            </text>
          </g>
        ))}
        {minutes.map((m) => (
          <g key={m}>
            <line x1={X(m)} x2={X(m)} y1={Y0} y2={Y0 + 12} stroke={tokens.ink} strokeWidth={2} />
            <text x={X(m)} y={Y0 + 42} textAnchor="middle" fontFamily={fonts.mono} fontSize={20} letterSpacing={2} fill={tokens.inkSoft}>
              {sToClock(m).slice(0, 5)}
            </text>
          </g>
        ))}
        {terrainD ? <path d={terrainD} fill={EARTH} stroke={tokens.ink} strokeWidth={1.5} strokeOpacity={0.6} /> : null}
        <line x1={X0} x2={X1} y1={Y0} y2={Y0} stroke={tokens.ink} strokeWidth={2.5} />
        <line x1={X0} x2={X0} y1={TOP - 20} y2={Y0} stroke={tokens.ink} strokeWidth={2} />
        {(scene.refs ?? []).map((r, i) => {
          const p = progress(time, sec(r.at), 0.8);
          if (p <= 0) return null;
          const c = accentOn(name, r.accent ?? 'ink');
          return (
            <g key={`ref${i}`} opacity={p}>
              <line x1={X0} x2={X0 + (X1 - X0) * p} y1={Y(r.value)} y2={Y(r.value)} stroke={c} strokeWidth={3} strokeDasharray="14 9" />
              <text x={X1} y={Y(r.value) - 14} textAnchor="end" fontFamily={fonts.mono} fontWeight={600} fontSize={22} letterSpacing={2} fill={c}>
                {r.label}
              </text>
            </g>
          );
        })}
        {(scene.marks ?? []).map((m, i) => {
          const at = videoTimeOf(scene.flight, m.clock);
          const r = reveal(time, at, 0.5);
          if (r.opacity <= 0) return null;
          const s = clockToS(m.clock);
          const c = accentOn(name, m.accent ?? 'ink');
          const right = X(s) < X0 + (X1 - X0) * 0.7;
          return (
            <g key={`mk${i}`} opacity={r.opacity}>
              <line x1={X(s)} x2={X(s)} y1={TOP - 10} y2={Y0} stroke={c} strokeWidth={2.5} strokeDasharray="4 7" />
              <text x={X(s) + (right ? 14 : -14)} y={TOP + 6} textAnchor={right ? 'start' : 'end'} fontFamily={fonts.serif} fontWeight={600} fontSize={28} fill={c}>
                {m.label}
              </text>
              <text x={X(s) + (right ? 14 : -14)} y={TOP + 36} textAnchor={right ? 'start' : 'end'} fontFamily={fonts.mono} fontSize={19} letterSpacing={2} fill={tokens.inkSoft}>
                {m.sub ?? m.clock}
              </text>
            </g>
          );
        })}
        {lines.map((k) => (
          <path key={k} d={line(k, now)} fill="none" stroke={colors[k]} strokeWidth={5} strokeLinecap="round" strokeLinejoin="round" />
        ))}
        {scene.series === 'n1' && scene.legend
          ? scene.legend.map((label, k) => {
              const v = tip.n1[k];
              if (v === null) return null;
              return (
                <text key={label} x={X(now) + 16} y={Y(v) + (k ? 22 : -10)} fontFamily={fonts.mono} fontWeight={600} fontSize={20} letterSpacing={2} fill={colors[k]}>
                  {label}
                </text>
              );
            })
          : null}
        {scene.series === 'alt' && tipV !== null ? (
          <g transform={`translate(${X(now)} ${Y(tipV)}) rotate(${slope}) translate(-40 -16) scale(0.8)`}>
            <path d={PLANE_SIDE_PATH} fill="#F4EFE2" stroke={tokens.ink} strokeWidth={3} strokeLinejoin="round" />
          </g>
        ) : scene.series !== 'n1' && tipV !== null ? (
          <circle cx={X(now)} cy={Y(tipV)} r={9} fill={colors[0]} stroke={tokens.bg} strokeWidth={3} />
        ) : null}
      </svg>
      <div style={{ position: 'absolute', left: X0, top: Y0 + 70, display: 'flex', gap: 40, opacity: appear }}>
        <Mono size={22} color={tokens.ink}>{sToClock(now)}</Mono>
        {tipV !== null ? (
          <Mono size={22} color={colors[0]}>
            {scene.series === 'n1' ? `${Math.round(tip.n1[0] ?? 0)} % · ${Math.round(tip.n1[1] ?? 0)} %` : `${fmtInt(tipV)} ${axis.unit}`}
          </Mono>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};

/* ── Cabina en texto ──────────────────────────────────────────────────────────────────────────────────────────── */

export const CockpitScene: FC = () => {
  const scene = useSceneOf('atlas-cockpit');
  const { name, tokens } = useTheme();
  const time = useAtlasTime();
  const data = useJsonFiles<FlightData>([scene.flight.data]);
  if (!data) return null;
  const [flight] = data;
  const now = flightClock(scene.flight, time);
  const point = sampleAt(flight, now);
  const said = scene.lines.filter((l) => videoTimeOf(scene.flight, l.clock) <= time);
  const visible = said.slice(-(scene.visible ?? 4));
  return (
    <AbsoluteFill>
      <Header top={92} />
      <div style={{ position: 'absolute', left: 120, top: 250, width: 1080 }}>
        {visible.map((l, i) => {
          const at = videoTimeOf(scene.flight, l.clock);
          const r = reveal(time, at, 0.45);
          const old = i < visible.length - 1;
          return (
            <div key={`${l.clock}${l.who}`} style={{ display: 'flex', gap: 30, marginBottom: 34, ...r.style, opacity: r.opacity * (old ? 0.5 : 1) }}>
              <div style={{ width: 150, flexShrink: 0, paddingTop: 8 }}>
                <Mono size={22} color={tokens.inkSoft}>{l.clock}</Mono>
              </div>
              <div>
                <Mono size={20} color={accentOn(name, l.accent ?? 'data')}>{l.who}</Mono>
                <div style={{ fontFamily: fonts.serif, fontStyle: 'italic', fontSize: 44, lineHeight: 1.2, color: tokens.ink, marginTop: 6 }}>
                  «{l.text}»
                </div>
              </div>
            </div>
          );
        })}
      </div>
      <FlightHud
        show={['clock', ...scene.instruments]}
        point={point}
        theme={name}
        corner="tr"
        labels={scene.labels}
        style={{ top: 250 }}
      />
    </AbsoluteFill>
  );
};

/* ── Avión con piezas resaltadas ─────────────────────────────────────────────────────────────────────────────── */

type Part = 'engines' | 'engine-left' | 'engine-right' | 'wings' | 'flaps' | 'tail' | 'elevator' | 'rudder' | 'nose' | 'gear' | 'fuselage';

/**
 * Siluetas genéricas dibujadas aquí (no un modelo concreto de fabricante): cada pieza es un trazo con nombre para
 * poder resaltarla. Caja 1000×600; vista superior con el morro a la derecha, lateral con el morro a la derecha.
 */
const SHAPES: Record<'narrowbody' | 'bizjet', Record<'top' | 'side', Partial<Record<Part, string>>>> = {
  narrowbody: {
    top: {
      fuselage: 'M120 300 C120 282 140 274 175 274 L840 274 C900 274 950 288 975 300 C950 312 900 326 840 326 L175 326 C140 326 120 318 120 300 Z',
      wings: 'M560 274 L430 60 L395 60 L455 274 Z M560 326 L430 540 L395 540 L455 326 Z',
      flaps: 'M455 274 L430 190 L470 190 L500 274 Z M455 326 L430 410 L470 410 L500 326 Z',
      'engine-left': 'M520 190 L600 190 C612 190 612 214 600 214 L520 214 Z',
      'engine-right': 'M520 386 L600 386 C612 386 612 410 600 410 L520 410 Z',
      tail: 'M220 274 L150 170 L125 170 L160 274 Z M220 326 L150 430 L125 430 L160 326 Z',
      elevator: 'M160 274 L125 170 L145 170 L180 274 Z M160 326 L125 430 L145 430 L180 326 Z',
      nose: 'M900 278 C935 284 960 292 975 300 C960 308 935 316 900 322 Z',
    },
    side: {
      fuselage: 'M110 300 C110 272 140 262 180 262 L840 262 C905 262 950 280 980 300 C950 322 905 336 840 336 L180 336 C140 336 110 326 110 300 Z',
      tail: 'M150 262 L95 100 L150 100 L260 262 Z',
      rudder: 'M95 100 L80 100 L120 262 L150 262 Z',
      elevator: 'M120 250 L60 240 L60 256 L150 266 Z',
      wings: 'M430 318 L600 318 L640 336 L470 336 Z',
      'engine-left': 'M500 340 L600 340 C616 340 616 378 600 378 L500 378 C490 378 490 340 500 340 Z',
      'engine-right': 'M500 340 L600 340 C616 340 616 378 600 378 L500 378 C490 378 490 340 500 340 Z',
      nose: 'M900 268 C940 278 965 290 980 300 C965 312 940 324 900 332 Z',
      gear: 'M560 336 L560 400 M540 400 L580 400 M860 336 L860 392 M845 392 L875 392',
    },
  },
  bizjet: {
    top: {
      fuselage: 'M150 300 C150 286 170 280 200 280 L820 280 C880 280 930 290 960 300 C930 310 880 320 820 320 L200 320 C170 320 150 314 150 300 Z',
      wings: 'M520 280 L420 90 L392 90 L450 280 Z M520 320 L420 510 L392 510 L450 320 Z',
      flaps: 'M450 280 L428 205 L462 205 L488 280 Z M450 320 L428 395 L462 395 L488 320 Z',
      'engine-left': 'M250 236 L340 236 C352 236 352 266 340 266 L250 266 Z',
      'engine-right': 'M250 334 L340 334 C352 334 352 364 340 364 L250 364 Z',
      tail: 'M215 280 L150 190 L128 190 L170 280 Z M215 320 L150 410 L128 410 L170 320 Z',
      elevator: 'M170 280 L128 190 L146 190 L188 280 Z M170 320 L128 410 L146 410 L188 320 Z',
      nose: 'M890 284 C925 290 948 296 960 300 C948 304 925 310 890 316 Z',
    },
    side: {
      fuselage: 'M140 300 C140 278 165 270 200 270 L830 270 C890 270 935 286 965 300 C935 316 890 330 830 330 L200 330 C165 330 140 322 140 300 Z',
      tail: 'M175 270 L110 120 L160 120 L260 270 Z',
      rudder: 'M110 120 L94 120 L140 270 L175 270 Z',
      elevator: 'M96 124 L40 116 L40 132 L130 136 Z',
      wings: 'M430 316 L580 316 L612 330 L462 330 Z',
      'engine-left': 'M250 240 L340 240 C354 240 354 268 340 268 L250 268 C240 268 240 240 250 240 Z',
      'engine-right': 'M250 240 L340 240 C354 240 354 268 340 268 L250 268 C240 268 240 240 250 240 Z',
      nose: 'M890 274 C930 283 952 292 965 300 C952 308 930 317 890 326 Z',
      gear: 'M540 330 L540 390 M522 390 L558 390 M860 330 L860 384 M846 384 L874 384',
    },
  },
};
const ENGINES: Part[] = ['engine-left', 'engine-right'];
/** Punto de la pieza donde se engancha la llamada (caja 1000×600). */
const ANCHOR: Record<'top' | 'side', Partial<Record<Part, [number, number]>>> = {
  top: { engines: [560, 202], 'engine-left': [560, 202], 'engine-right': [560, 398], wings: [430, 110], flaps: [460, 200], tail: [150, 200], elevator: [140, 190], nose: [950, 300], fuselage: [700, 300] },
  side: { engines: [550, 378], 'engine-left': [550, 378], 'engine-right': [550, 378], wings: [530, 336], tail: [140, 140], rudder: [100, 130], elevator: [60, 248], nose: [960, 300], gear: [560, 400], fuselage: [700, 270] },
};

export const AircraftScene: FC = () => {
  const scene = useSceneOf('atlas-aircraft');
  const { name, tokens } = useTheme();
  const time = useAtlasTime();
  const shapes = SHAPES[scene.model][scene.view];
  const S = 1.3;
  const ox = 960 - 500 * S;
  const oy = 600 - 300 * S;
  const lit = (part: Part) =>
    (scene.highlights ?? []).filter((h) => h.part === part || (h.part === 'engines' && ENGINES.includes(part)));
  const order: Part[] = ['wings', 'flaps', 'tail', 'elevator', 'rudder', 'fuselage', 'nose', 'engine-left', 'engine-right', 'gear'];
  return (
    <AbsoluteFill>
      <Header top={92} />
      <svg width={1920} height={1080} style={{ position: 'absolute', inset: 0 }}>
        <g transform={`translate(${ox} ${oy}) scale(${S})`}>
          {order.map((part) => {
            const d = shapes[part];
            if (!d) return null;
            const hs = lit(part);
            const p = hs.length ? Math.max(...hs.map((h) => progress(time, sec(h.at), 0.6))) : 0;
            const c = hs.length ? accentOn(name, hs[hs.length - 1].accent ?? 'danger') : tokens.ink;
            const line = part === 'gear';
            const base = part === 'fuselage' || part === 'wings' || part === 'tail' || part === 'nose' ? '#F4EFE2' : '#E2D8C2';
            return (
              <path
                key={part}
                d={d}
                fill={line ? 'none' : p > 0 ? c : base}
                fillOpacity={line ? 0 : p > 0 ? 0.25 + 0.6 * p : 1}
                stroke={p > 0 ? c : tokens.ink}
                strokeWidth={(line ? 4 : 2.2) + 1.6 * p}
                strokeLinejoin="round"
                strokeLinecap="round"
              />
            );
          })}
        </g>
        {(scene.highlights ?? []).map((h, i) => {
          if (!h.label) return null;
          const r = reveal(time, sec(h.at) + 0.3, 0.5);
          if (r.opacity <= 0) return null;
          const [ax, ay] = ANCHOR[scene.view][h.part] ?? [500, 300];
          const x = ox + ax * S;
          const y = oy + ay * S;
          const up = y < 600;
          const ly = up ? Math.max(250, y - 150) : Math.min(960, y + 150);
          const lx = x + (x > 960 ? 120 : -120);
          const c = accentOn(name, h.accent ?? 'danger');
          return (
            <g key={`hl${i}`} opacity={r.opacity}>
              <circle cx={x} cy={y} r={7} fill={c} />
              <polyline points={`${x},${y} ${lx},${ly}`} fill="none" stroke={c} strokeWidth={2.5} />
              <text x={lx + (x > 960 ? 12 : -12)} y={ly + 9} textAnchor={x > 960 ? 'start' : 'end'} fontFamily={fonts.serif} fontWeight={600} fontSize={34} fill={c}>
                {h.label}
              </text>
              {h.sub ? (
                <text x={lx + (x > 960 ? 12 : -12)} y={ly + 42} textAnchor={x > 960 ? 'start' : 'end'} fontFamily={fonts.mono} fontSize={20} letterSpacing={2} fill={tokens.inkSoft}>
                  {h.sub}
                </text>
              ) : null}
            </g>
          );
        })}
      </svg>
    </AbsoluteFill>
  );
};

/* ── Lo que se sabe ──────────────────────────────────────────────────────────────────────────────────────────── */

const STATUS = { confirmed: 'CONFIRMADO', unconfirmed: 'SIN CONFIRMAR', unknown: 'SE DESCONOCE' };

export const KnownScene: FC = () => {
  const scene = useSceneOf('atlas-known');
  const { name, tokens } = useTheme();
  const time = useAtlasTime();
  const labels = { ...STATUS, ...scene.statusLabels };
  const color = { confirmed: accentOn(name, 'good'), unconfirmed: accentOn(name, 'amber'), unknown: tokens.inkSoft };
  return (
    <AbsoluteFill>
      <Header top={92} />
      <div style={{ position: 'absolute', right: 120, top: 98 }}>
        <Mono size={20} color={tokens.inkSoft}>{scene.asOf}</Mono>
      </div>
      <div style={{ position: 'absolute', left: 200, right: 200, top: 290, display: 'flex', flexDirection: 'column', gap: 22 }}>
        {scene.items.map((item, i) => {
          const r = reveal(time, sec(item.at), 0.5);
          const rich = richText(item.text);
          return (
            <div key={i} style={{ ...r.style }}>
              <PaperCard theme={name} padding="20px 30px" style={{ display: 'flex', alignItems: 'center', gap: 34 }}>
                <div style={{ width: 210, flexShrink: 0 }}>
                  <Mono size={19} color={color[item.status]} style={{ fontWeight: 700 }}>{labels[item.status]}</Mono>
                </div>
                <div style={{ flex: 1 }}>
                  <RichTitle rich={{ text: rich.text, accent: rich.accent }} theme="paper" size={36} color={themes.paper.ink} defaultAccent="danger" />
                  <div style={{ marginTop: 6 }}>
                    <Mono size={16} color={themes.paper.inkSoft}>{item.source}</Mono>
                  </div>
                </div>
              </PaperCard>
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
