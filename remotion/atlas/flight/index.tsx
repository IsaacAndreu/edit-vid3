/**
 * Vuelos reales (prompts/accidentes-plan.md): vuelo.json de scripts/accidentes/vuelo.py, el reloj del vuelo a partir
 * del tiempo del vídeo, interpolación entre muestras y los instrumentos que leen los datos en cada fotograma.
 */
import type { FC } from 'react';
import { fonts } from '../fonts';
import type { FlightPlayback } from '../schema';
import { themes, type ThemeName } from '../theme';
import { sec } from '../time';
import { cornerStyle, PaperCard, type Corner } from '../ui';

export interface FlightPoint {
  s: number;
  lat: number;
  lon: number;
  alt: number;
  ra?: number;
  kias: number | null;
  gs: number;
  hdg: number | null;
  pitch: number;
  roll: number;
  n1: [number | null, number | null];
  ground: boolean;
  flap?: number;
  /** Altura del terreno bajo el avión en pies (accidentes:data suelo). */
  terrain?: number;
}

export interface FlightData {
  id: string;
  flight: string;
  aircraft: string;
  from: string;
  to: string;
  source: { document: string; url: string; license: string };
  points: FlightPoint[];
  events: { clock: string; s: number; text: string; ref: string }[];
}

export const clockToS = (clock: string): number => {
  const [h, m, s] = clock.split(':');
  return Number(h) * 3600 + Number(m) * 60 + Number(s);
};

export const sToClock = (s: number): string => {
  const r = Math.floor(s + 1e-6);
  const p = (n: number) => String(n).padStart(2, '0');
  return `${p(Math.floor(r / 3600))}:${p(Math.floor((r % 3600) / 60))}:${p(r % 60)}`;
};

/** Hora del vuelo (segundos desde medianoche) en el segundo `time` del vídeo. */
export const flightClock = (playback: FlightPlayback, time: number): number => {
  const from = clockToS(playback.from);
  const to = clockToS(playback.to);
  return Math.min(to, from + Math.max(0, time - sec(playback.at)) * (playback.rate ?? 1));
};

/** Segundo del vídeo en que el reloj del vuelo llega a `clock` (para que los hitos entren a su hora). */
export const videoTimeOf = (playback: FlightPlayback, clock: string): number =>
  sec(playback.at) + (clockToS(clock) - clockToS(playback.from)) / (playback.rate ?? 1);

const lerp = (a: number, b: number, f: number) => a + (b - a) * f;
const lerpNull = (a: number | null | undefined, b: number | null | undefined, f: number) =>
  a === null || a === undefined || b === null || b === undefined ? (f < 0.5 ? a ?? null : b ?? null) : lerp(a, b, f);

/** Índice de la última muestra con s ≤ t. */
const indexAt = (pts: FlightPoint[], t: number): number => {
  let lo = 0;
  let hi = pts.length - 1;
  if (t <= pts[0].s) return 0;
  if (t >= pts[hi].s) return hi;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (pts[mid].s <= t) lo = mid;
    else hi = mid - 1;
  }
  return lo;
};

/** El estado del avión en la hora t, interpolado entre las dos muestras que la rodean. */
export const sampleAt = (data: FlightData, t: number): FlightPoint => {
  const pts = data.points;
  const i = indexAt(pts, t);
  const a = pts[i];
  const b = pts[Math.min(i + 1, pts.length - 1)];
  const f = b.s === a.s ? 0 : Math.max(0, Math.min(1, (t - a.s) / (b.s - a.s)));
  const dh = a.hdg !== null && b.hdg !== null ? ((b.hdg - a.hdg + 540) % 360) - 180 : 0;
  return {
    s: t,
    lat: lerp(a.lat, b.lat, f),
    lon: lerp(a.lon, b.lon, f),
    alt: lerp(a.alt, b.alt, f),
    ra: a.ra !== undefined && b.ra !== undefined ? lerp(a.ra, b.ra, f) : undefined,
    kias: lerpNull(a.kias, b.kias, f),
    gs: lerp(a.gs, b.gs, f),
    hdg: a.hdg === null ? b.hdg : (a.hdg + dh * f + 360) % 360,
    pitch: lerp(a.pitch, b.pitch, f),
    roll: lerp(a.roll, b.roll, f),
    n1: [lerpNull(a.n1[0], b.n1[0], f), lerpNull(a.n1[1], b.n1[1], f)],
    ground: f < 0.5 ? a.ground : b.ground,
    terrain: a.terrain !== undefined && b.terrain !== undefined ? lerp(a.terrain, b.terrain, f) : undefined,
  };
};

/** Las muestras entre `from` y t, con la punta interpolada al final. */
export const flownUntil = (data: FlightData, from: number, t: number): FlightPoint[] => {
  const out = data.points.filter((p) => p.s >= from && p.s < t);
  out.push(sampleAt(data, t));
  return out;
};

/** Rumbo de la trayectoria (grados, 0 = norte, sentido horario) cerca de t: sale de las posiciones, no de la brújula. */
export const trackAt = (data: FlightData, t: number): number => {
  const a = sampleAt(data, t - 2);
  const b = sampleAt(data, t + 2);
  const dx = (b.lon - a.lon) * Math.cos((a.lat * Math.PI) / 180);
  const dy = b.lat - a.lat;
  if (Math.abs(dx) + Math.abs(dy) < 1e-9) return a.hdg ?? 0;
  return ((Math.atan2(dx, dy) * 180) / Math.PI + 360) % 360;
};

export const fmtInt = (v: number) => Math.round(v).toLocaleString('es-ES').replace(/ /g, ' ');

const DEFAULT_LABELS = { clock: 'HORA', alt: 'ALTITUD', kias: 'VELOCIDAD', n1: 'MOTORES' };
export type HudItem = 'clock' | 'alt' | 'kias' | 'n1';

/** Panel de instrumentos: lee la muestra del instante y la escribe en mono; los motores como dos barras. */
export const FlightHud: FC<{
  show: HudItem[];
  point: FlightPoint;
  theme: ThemeName;
  corner?: Corner;
  labels?: Partial<Record<HudItem, string>>;
  timezone?: string;
  style?: React.CSSProperties;
}> = ({ show, point, theme, corner = 'tr', labels, timezone, style }) => {
  const ink = themes.paper.ink;
  const soft = themes.paper.inkSoft;
  const danger = themes.paper.accents.danger;
  const L = { ...DEFAULT_LABELS, ...labels };
  const row = (label: string, value: React.ReactNode, key: string) => (
    <div key={key} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 28, marginTop: 6 }}>
      <span style={{ fontFamily: fonts.mono, fontSize: 18, letterSpacing: '0.16em', color: soft }}>{label}</span>
      <span style={{ fontFamily: fonts.mono, fontSize: 30, fontWeight: 600, color: ink, fontVariantNumeric: 'tabular-nums' }}>{value}</span>
    </div>
  );
  const bar = (v: number | null) => (
    <div style={{ width: 120, height: 12, border: `1.5px solid ${ink}`, position: 'relative' }}>
      <div
        style={{
          position: 'absolute',
          left: 0,
          top: 0,
          bottom: 0,
          width: `${Math.max(0, Math.min(100, v ?? 0))}%`,
          backgroundColor: (v ?? 0) < 50 ? danger : ink,
        }}
      />
    </div>
  );
  return (
    <div style={{ ...cornerStyle(corner), ...style }}>
      <PaperCard theme={theme} padding="20px 28px 22px" style={{ minWidth: 330 }}>
        {show.map((item) => {
          if (item === 'clock') return row(L.clock, `${sToClock(point.s)}${timezone ? ` ${timezone}` : ''}`, item);
          if (item === 'alt') return row(L.alt, `${fmtInt(Math.max(0, point.alt))} ft`, item);
          if (item === 'kias') return row(L.kias, point.kias === null ? '—' : `${Math.round(point.kias)} kt`, item);
          return (
            <div key={item} style={{ marginTop: 10 }}>
              <span style={{ fontFamily: fonts.mono, fontSize: 18, letterSpacing: '0.16em', color: soft }}>{L.n1}</span>
              {[0, 1].map((k) => (
                <div key={k} style={{ display: 'flex', alignItems: 'center', gap: 14, marginTop: 6 }}>
                  <span style={{ fontFamily: fonts.mono, fontSize: 18, color: soft, width: 18 }}>{k + 1}</span>
                  {bar(point.n1[k])}
                  <span style={{ fontFamily: fonts.mono, fontSize: 24, fontWeight: 600, color: ink, width: 90, textAlign: 'right' }}>
                    {point.n1[k] === null ? '—' : `${Math.round(point.n1[k] as number)} %`}
                  </span>
                </div>
              ))}
            </div>
          );
        })}
      </PaperCard>
    </div>
  );
};
