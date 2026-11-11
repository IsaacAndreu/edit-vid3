/**
 * atlas-elevation-profile (fase 4): corte de terreno con datos reales (build-profile), ejes en pies y km, trayectoria
 * de vuelo que se dibuja con un avión de perfil, umbrales, bandas, la altitud mínima segura escalonada calculada del
 * propio perfil, tramos en infracción y cambio de terreno en vivo (mar abierto ↔ meseta).
 */
import type { FC } from 'react';
import { AbsoluteFill } from 'remotion';
import { ease, progress, reveal } from '../anim';
import { useAtlasTime, useTheme } from '../context';
import { fonts } from '../fonts';
import { useJsonFiles } from '../geo/useData';
import { PLANE_SIDE_PATH } from '../icons';
import type { AtlasScene } from '../schema';
import { accentOn } from '../theme';
import { sec } from '../time';
import { Mono } from '../ui';
import { Header, useSceneOf } from './text';

type Profile = Extract<AtlasScene, { type: 'atlas-elevation-profile' }>;
interface ProfileData {
  km: number;
  samples: [number, number][];
}

const FT_PER_M = 3.28084;
const X0 = 300;
const X1 = 1680;
const Y0 = 900; // 0 ft
const TOP = 252; // axis.maxFt
const EARTH = '#C9B48E';
const SEA = '#9FBCCB';

/** Altitud de la trayectoria en x (0–1), interpolando entre sus puntos con la curva de cada tramo. */
const flightAlt = (points: NonNullable<Profile['flight']>['points'], x: number) => {
  if (x <= points[0].x) return points[0].ft;
  for (let i = 1; i < points.length; i++) {
    const a = points[i - 1];
    const b = points[i];
    if (x <= b.x) {
      const t = (x - a.x) / (b.x - a.x || 1);
      const curve = b.curve ?? 'ease';
      const k = curve === 'linear' ? t : curve === 'step' ? (t < 1 ? 0 : 1) : ease(t);
      return a.ft + (b.ft - a.ft) * k;
    }
  }
  return points[points.length - 1].ft;
};

export const ElevationProfileScene: FC = () => {
  const scene = useSceneOf('atlas-elevation-profile');
  const { name, tokens } = useTheme();
  const time = useAtlasTime();
  const data = useJsonFiles<ProfileData>([scene.profile]);
  if (!data) return null;
  const [profile] = data;
  const { axis } = scene;
  // alturas del terreno (metros en los datos) en la unidad del eje
  const metric = axis.unit === 'm';
  const FT = metric ? 1 : FT_PER_M;
  const unitLabel = metric ? 'M' : 'FT';
  const X = (f: number) => X0 + (X1 - X0) * f;
  const Y = (ft: number) => Y0 - ((Y0 - TOP) * Math.min(ft, axis.maxFt * 1.08)) / axis.maxFt;
  const n = profile.samples.length;
  const terrainFt = (i: number) => Math.max(0, profile.samples[i][1] * FT);
  const fracOf = (i: number) => profile.samples[i][0] / profile.km;
  const terrainAt = (f: number) => {
    const i = Math.min(n - 1, Math.max(0, Math.round(f * (n - 1))));
    return terrainFt(i);
  };

  // terreno visible: 'sea' = 0; el cambio crece de 0 al perfil (o al revés)
  const groundAt = scene.groundAt ? sec(scene.groundAt) : -Infinity;
  const groundIn = scene.groundAt ? progress(time, groundAt, 1.2) : 1;
  let land = scene.ground === 'terrain' ? groundIn : 0;
  if (scene.swap) {
    const s = progress(time, sec(scene.swap.at), 1.4);
    land = scene.swap.to === 'terrain' ? Math.max(land, s) : land * (1 - s);
  }
  const aboutSea = scene.ground === 'sea' || scene.swap?.to === 'sea';
  const seaVisible = aboutSea ? 1 - land : 0;

  // altitud mínima segura escalonada, calculada del perfil
  const msaSteps: { a: number; b: number; ft: number }[] = [];
  if (scene.msa) {
    const segs = Math.max(1, Math.round(profile.km / scene.msa.segmentKm));
    for (let s = 0; s < segs; s++) {
      const a = s / segs;
      const b = (s + 1) / segs;
      let m = 0;
      for (let i = 0; i < n; i++) if (fracOf(i) >= a && fracOf(i) <= b) m = Math.max(m, terrainFt(i));
      msaSteps.push({ a, b, ft: Math.ceil((m + scene.msa.marginFt) / 100) * 100 });
    }
  }
  const msaAt = (f: number) => {
    const step = msaSteps.find((s) => f >= s.a && f <= s.b);
    return step ? step.ft : 0;
  };
  const msaP = scene.msa ? progress(time, sec(scene.msa.at), 1.4, (x) => x) : 0;

  // trayectoria
  const fl = scene.flight;
  const flP = fl ? progress(time, sec(fl.at), fl.drawSeconds, (x) => x) : 0;
  const altAt = (f: number) => {
    if (!fl) return 0;
    const raw = flightAlt(fl.points, f);
    return fl.stopAtMsa && msaP > 0 ? Math.max(raw, msaAt(f)) : raw;
  };
  const flStart = fl ? fl.points[0].x : 0;
  const flEnd = fl ? fl.points[fl.points.length - 1].x : 0;
  const tipF = flStart + (flEnd - flStart) * flP;
  const flightPath: string[] = [];
  if (fl && flP > 0) {
    const steps = 240;
    for (let k = 0; k <= steps; k++) {
      const f = flStart + ((tipF - flStart) * k) / steps;
      flightPath.push(`${k ? 'L' : 'M'}${X(f).toFixed(1)},${Y(altAt(f)).toFixed(1)}`);
    }
  }
  const dF = 0.004;
  const angle = (Math.atan2(Y(altAt(Math.min(1, tipF + dF))) - Y(altAt(tipF)), X(tipF + dF) - X(tipF)) * 180) / Math.PI;

  const terrainD =
    `M${X(0)},${Y0} ` +
    profile.samples.map((s, i) => `L${X(fracOf(i)).toFixed(1)},${Y(terrainFt(i) * land).toFixed(1)}`).join(' ') +
    ` L${X(1)},${Y0} Z`;
  const ticks = Array.from({ length: Math.floor(axis.maxFt / axis.stepFt) + 1 }, (_, i) => i * axis.stepFt);
  const axisIn = reveal(time, sec({ t: 0 }) + 0, 0.01).opacity;
  const middle = (scene.ends.middle ?? '').replace('{km}', profile.km.toLocaleString('en-US'));

  return (
    <AbsoluteFill>
      <Header top={92} />
      <svg width={1920} height={1080} style={{ position: 'absolute', inset: 0, opacity: axisIn }}>
        {ticks.map((ft) => (
          <g key={ft}>
            {ft > 0 ? <line x1={X0} x2={X1} y1={Y(ft)} y2={Y(ft)} stroke={tokens.inkSoft} strokeOpacity={0.45} strokeWidth={2} strokeDasharray="2 8" /> : null}
            <text x={X0 - 20} y={Y(ft) + 7} textAnchor="end" fontFamily={fonts.mono} fontWeight={500} fontSize={21} letterSpacing={2.5} fill={tokens.inkSoft}>
              {ft.toLocaleString('en-US')} {unitLabel}
            </text>
            {axis.km && !metric && ft > 0 ? (
              <text x={X0 - 20} y={Y(ft) + 33} textAnchor="end" fontFamily={fonts.mono} fontSize={16} letterSpacing={2} fill={tokens.inkSoft} opacity={0.8}>
                {((ft / FT_PER_M) / 1000).toFixed(1)} KM
              </text>
            ) : null}
          </g>
        ))}
        {scene.bands?.map((band, i) => {
          const p = progress(time, sec(band.at), 0.6);
          return (
            <rect key={`band${i}`} x={X0} width={X1 - X0} y={Y(band.toFt)} height={Y(band.fromFt) - Y(band.toFt)}
                  fill={accentOn(name, band.accent ?? 'data', tokens.inkSoft)} opacity={0.14 * p} />
          );
        })}
        {/* terreno */}
        <path d={terrainD} fill={EARTH} opacity={land > 0 ? 1 : 0} />
        <path
          d={profile.samples.map((s, i) => `${i ? 'L' : 'M'}${X(fracOf(i)).toFixed(1)},${Y(terrainFt(i) * land).toFixed(1)}`).join(' ')}
          fill="none"
          stroke={tokens.ink}
          strokeWidth={2.5}
          strokeLinejoin="round"
          opacity={land > 0 ? 1 : 0}
        />
        {seaVisible > 0 ? <line x1={X0} x2={X1} y1={Y0 - 5} y2={Y0 - 5} stroke={SEA} strokeWidth={10} opacity={seaVisible} /> : null}
        {scene.clearance
          ? (() => {
              const c = scene.clearance;
              const p = progress(time, sec(c.at), 1.0);
              if (p <= 0 || land <= 0) return null;
              const d = profile.samples
                .filter((_, i) => i % 2 === 0)
                .map((s, j) => `${j ? 'L' : 'M'}${X(s[0] / profile.km).toFixed(1)},${Y(Math.max(0, s[1] * FT) * land + c.ft).toFixed(1)}`)
                .join(' ');
              return <path d={d} fill="none" stroke={accentOn(name, c.accent ?? 'data')} strokeWidth={2} strokeDasharray="6 6" opacity={p} />;
            })()
          : null}
        {scene.thresholds?.map((th, i) => {
          const p = progress(time, sec(th.at), 0.8);
          return (
            <line key={`th${i}`} x1={X0} x2={X0 + (X1 - X0) * p} y1={Y(th.ft)} y2={Y(th.ft)} stroke={accentOn(name, th.accent)} strokeWidth={2.5} strokeDasharray="9 7" />
          );
        })}
        {/* altitud mínima segura escalonada, de izquierda a derecha */}
        {scene.msa && msaP > 0
          ? (() => {
              const pts: string[] = [];
              for (const [k, s] of msaSteps.entries()) {
                if (s.a > msaP) break;
                const b = Math.min(s.b, msaP);
                pts.push(`${k ? 'L' : 'M'}${X(s.a).toFixed(1)},${Y(s.ft).toFixed(1)}`, `L${X(b).toFixed(1)},${Y(s.ft).toFixed(1)}`);
              }
              return <path d={pts.join(' ')} fill="none" stroke={accentOn(name, scene.msa.accent ?? 'danger')} strokeWidth={3} strokeLinejoin="miter" />;
            })()
          : null}
        {/* tramos de la trayectoria por debajo de la MSA */}
        {scene.violations && fl && scene.msa
          ? (() => {
              const p = progress(time, sec(scene.violations.at), 0.6);
              if (p <= 0) return null;
              const rects = [];
              const steps = 400;
              for (let k = 0; k < steps; k++) {
                const f = flStart + ((tipF - flStart) * k) / steps;
                const g = flStart + ((tipF - flStart) * (k + 1)) / steps;
                const alt = flightAlt(fl.points, f);
                const msa = msaAt(f);
                if (alt < msa) rects.push(<rect key={k} x={X(f)} width={X(g) - X(f) + 0.5} y={Y(msa)} height={Y(alt) - Y(msa)} fill={tokens.accents.danger} opacity={0.55 * p} />);
              }
              return <g>{rects}</g>;
            })()
          : null}
        {fl && flP > 0 ? (
          <g>
            <path d={flightPath.join(' ')} fill="none" stroke={accentOn(name, fl.accent)} strokeWidth={3.5} strokeLinejoin="round" strokeLinecap="round" />
            {fl.plane !== false ? (
              <g transform={`translate(${X(tipF)} ${Y(altAt(tipF))}) rotate(${angle}) translate(-30 -20) scale(0.62)`}>
                <path d={PLANE_SIDE_PATH} fill="#F4EFE2" stroke={tokens.ink} strokeWidth={2.4} strokeLinejoin="round" />
              </g>
            ) : null}
          </g>
        ) : null}
        {scene.markers?.map((m, i) => {
          const p = progress(time, sec(m.at), 0.5);
          if (p <= 0) return null;
          const color = accentOn(name, m.accent);
          return m.line === 'full' ? (
            <line key={`mk${i}`} x1={X(m.x)} x2={X(m.x)} y1={TOP - 30} y2={Y0} stroke={color} strokeWidth={2} strokeDasharray="3 6" opacity={p} />
          ) : (
            <line key={`mk${i}`} x1={X(m.x)} x2={X(m.x)} y1={TOP + 4} y2={TOP + 30} stroke={color} strokeWidth={3} opacity={p} />
          );
        })}
        <line x1={X0} y1={TOP - 52} x2={X0} y2={Y0} stroke={tokens.ink} strokeWidth={2.5} />
        <line x1={X0} y1={Y0} x2={X1} y2={Y0} stroke={tokens.ink} strokeWidth={2.5} />
      </svg>
      {/* textos */}
      <Label x={X0 + 10} y={Y0 + 22} anchor="start" text={scene.ends.left} color={tokens.ink} />
      {middle ? <Label x={(X0 + X1) / 2} y={Y0 + 22} anchor="middle" text={middle} color={tokens.inkSoft} /> : null}
      <Label x={X1} y={Y0 + 22} anchor="end" text={scene.ends.right} color={tokens.ink} />
      {seaVisible > 0.05 && scene.seaLabel ? (
        <div style={{ position: 'absolute', left: X0, width: X1 - X0, top: Y0 + 14, textAlign: 'center', opacity: seaVisible }}>
          <span style={{ fontFamily: fonts.serifItalic, fontStyle: 'italic', fontSize: 32, letterSpacing: '0.24em', color: tokens.accents.data }}>
            {scene.seaLabel}
          </span>
        </div>
      ) : null}
      {scene.msa ? (
        <Label x={X1 - 10} y={Y(Math.max(...msaSteps.map((s) => s.ft)) ) - 56} anchor="end" text={scene.msa.label}
               color={accentOn(name, scene.msa.accent ?? 'danger')} opacity={progress(time, sec(scene.msa.at) + 0.8, 0.5)} />
      ) : null}
      {scene.clearance ? (
        <Label x={X0 + 30} y={Y(6800)} anchor="start" text={`---- ${scene.clearance.label}`} color={accentOn(name, scene.clearance.accent ?? 'data')}
               opacity={progress(time, sec(scene.clearance.at) + 0.5, 0.5)} />
      ) : null}
      {scene.thresholds?.map((th, i) => (
        <Label key={`thl${i}`} x={th.labelSide === 'right' ? X1 - 10 : X0 + 18} y={Y(th.ft) + 10} anchor={th.labelSide === 'right' ? 'end' : 'start'}
               text={th.label} color={accentOn(name, th.accent)} opacity={progress(time, sec(th.at) + 0.4, 0.5)} />
      ))}
      {scene.bands?.map((band, i) => (
        <Label key={`bl${i}`} x={X1 - 10} y={Y(band.toFt) - 34} anchor="end" text={band.label} color={accentOn(name, band.accent ?? 'data')}
               opacity={progress(time, sec(band.at) + 0.3, 0.5)} />
      ))}
      {scene.violations?.label && scene.msa ? (
        <Label x={X0 + 170} y={Y(Math.max(...msaSteps.map((s) => s.ft))) - 60} anchor="start" text={scene.violations.label}
               color={tokens.accents.danger} opacity={progress(time, sec(scene.violations.at) + 0.3, 0.5)} />
      ) : null}
      {scene.markers?.map((m, i) => (
        <Label key={`ml${i}`} x={X(m.x) + 10} y={TOP + (m.line === 'full' ? -64 : 2)} anchor="start" text={m.label}
               color={accentOn(name, m.accent)} opacity={progress(time, sec(m.at), 0.5)} />
      ))}
      {scene.notes?.map((note, i) => (
        <Label key={`nt${i}`} x={X(note.x)} y={Y(note.ft) - 14} anchor="middle" text={note.text} color={note.accent ? accentOn(name, note.accent) : tokens.ink}
               opacity={progress(time, sec(note.at), 0.5)} size={27} />
      ))}
    </AbsoluteFill>
  );
};

const Label: FC<{ x: number; y: number; anchor: 'start' | 'middle' | 'end'; text: string; color: string; opacity?: number; size?: number }> = ({
  x,
  y,
  anchor,
  text,
  color,
  opacity = 1,
  size = 22,
}) => (
  <div
    style={{
      position: 'absolute',
      top: y,
      ...(anchor === 'start' ? { left: x } : anchor === 'end' ? { right: 1920 - x } : { left: x - 600, width: 1200, textAlign: 'center' }),
      opacity,
    }}
  >
    <Mono size={size} color={color} tracking="0.16em" style={{ fontWeight: 600 }}>
      {text}
    </Mono>
  </div>
);
