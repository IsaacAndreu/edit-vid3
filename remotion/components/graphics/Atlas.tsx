import type { FC, ReactNode } from 'react';
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { geoCentroid, geoCircle, geoDistance, geoGraticule10, geoInterpolate, geoOrthographic, geoPath } from 'd3-geo';
import type { GeoPermissibleObjects } from 'd3-geo';
import { feature } from 'topojson-client';
import world50 from 'world-atlas/countries-50m.json';
import land50 from 'world-atlas/land-50m.json';
import land110 from 'world-atlas/land-110m.json';
import bathymetry from '../../data/bathymetry.json';
import GRAIN from '../../data/grain.png';
import world110 from 'world-atlas/countries-110m.json';
import type { AtlasGraphic } from '../../graphics';
import { theme } from '../../theme';
import { Vignette } from './Paper';

/**
 * Atlas deep dive (pipeline/atlas.py): a paper page with an orthographic globe that turns from one line's camera to
 * the next, great-circle routes, range rings, a polar zone, dots with names, paper cards and a stamp; some lines a clean
 * chart or a line drawing instead of the globe; the chapter bar on top and a serif title card per chapter. Every element
 * comes in at the frame of its word (from the Python side).
 */

const W = 1920;
const H = 1080;
const SERIF = "'DM Serif Display', Georgia, serif";
const MONO = "'JetBrains Mono', monospace";

type Feature = { type: string; properties: { name: string }; geometry: unknown };
const COUNTRIES = (feature(world50 as never, (world50 as never as { objects: { countries: never } }).objects.countries) as never as { features: Feature[] }).features;
const ICE = new Set(['Antarctica', 'Greenland']);
const LAND = COUNTRIES.filter((c) => !ICE.has(c.properties.name));
const ICY = COUNTRIES.filter((c) => ICE.has(c.properties.name));
// one merged landmass (no borders, like a relief map)
const LAND_FC = feature(land50 as never, (land50 as never as { objects: { land: never } }).objects.land) as unknown as GeoPermissibleObjects;
// the whole globe on screen: Natural Earth 1:110m is plenty (and ~10x fewer points to project every frame)
const LAND_FC_110 = feature(land110 as never, (land110 as never as { objects: { land: never } }).objects.land) as unknown as GeoPermissibleObjects;
const ICE_110 = { type: 'FeatureCollection', features: (feature(world110 as never, (world110 as never as { objects: { countries: never } }).objects.countries) as never as { features: Feature[] }).features.filter((c) => ICE.has(c.properties.name)) } as unknown as GeoPermissibleObjects;
const ICE_FC = { type: 'FeatureCollection', features: ICY } as unknown as GeoPermissibleObjects;
const GRATICULE = geoGraticule10();
// Natural Earth's bathymetry (scripts/build_bathymetry.py): the sea deeper than 200 / 2,000 / 4,000 / 6,000 m
const DEPTHS = (bathymetry as unknown as { features: { properties: { depth: number } }[] }).features as unknown as (GeoPermissibleObjects & { properties: { depth: number } })[];

const PALETTES = {
  paper: { page: '#ECE4D1', pageEdge: '#D9CFB8', ink: '#1E2833', soft: '#6B6355', oceanIn: '#D6E4EA', oceanOut: '#C3D6E0',
           depths: ['#BFD3DF', '#A9C4D5', '#93B4C9', '#82A6BE'],
           shelf: '#D3E2EA', land: '#E3D4B1', coast: '#8C7A5A', ice: '#F6F4EE', grid: 'rgba(30,40,51,0.07)', rim: '#1E2833', card: '#F4EEDF', halo: '#F4EEDF' },
  dark: { page: '#2A323B', pageEdge: '#1D232A', ink: '#E9E3D6', soft: '#9AA3AC', oceanIn: '#4A6377', oceanOut: '#41596C',
          depths: ['#3F576B', '#364D60', '#2E4456', '#283C4D'],
          shelf: '#4C667B', land: '#8E9FAE', coast: '#B7C3CD', ice: '#EEF2F5', grid: 'rgba(233,227,214,0.06)', rim: '#9FB0BE', card: '#F4EEDF', halo: '#1B232C' },
};
type Palette = typeof PALETTES.paper;

const clamp = (v: number, a = 0, b = 1) => Math.max(a, Math.min(b, v));
const ease = (t: number) => (t < 0.5 ? 4 * t ** 3 : 1 - (-2 * t + 2) ** 3 / 2);
const lerp = (a: number, b: number, t: number) => a + (b - a) * t;

/** The words of a title, the key one set apart: between *asterisks*, else the last word. */
const KeyTitle: FC<{ text: string; size: number; color: string; accent: string; align?: 'center' | 'left' }> = ({ text, size, color, accent, align = 'center' }) => {
  const words = text.split(/\s+/).filter(Boolean);
  let key = words.findIndex((w) => /\*/.test(w));
  if (key < 0) key = words.length - 1;
  return (
    <div style={{ fontFamily: SERIF, fontSize: size, color, textAlign: align, lineHeight: 1.12 }}>
      {words.map((w, i) => (
        <span key={i} style={i === key ? { fontStyle: 'italic', color: accent } : undefined}>
          {w.replace(/\*/g, '')}{i < words.length - 1 ? ' ' : ''}
        </span>
      ))}
    </div>
  );
};

/** The camera at frame f: the globe turns from the previous centre to this one (cubic in-out), pulling out on the way
 * when both are close-ups far apart, then drifts very slowly. */
const cameraAt = (g: AtlasGraphic, f: number, fps: number) => {
  const a = g.prev ?? g.camera;
  const b = g.camera;
  const turn = geoInterpolate([a.lon, a.lat], [b.lon, b.lat]);
  const far = geoDistance([a.lon, a.lat], [b.lon, b.lat]);           // radians
  const T = Math.round(fps * (far < 0.01 && Math.abs(a.zoom - b.zoom) < 0.05 ? 1 : 1.1 + 0.9 * clamp(far / Math.PI) + 0.12 * Math.abs(a.zoom - b.zoom)));
  const t = ease(clamp(f / T));
  const dip = Math.max(0, Math.min(a.zoom, b.zoom) - 1) * clamp(far / 0.6) * Math.sin(Math.PI * t);
  const [lon, lat] = turn(t);
  const zoom = lerp(a.zoom, b.zoom, t) - dip + 0.05 * clamp((f - T) / (fps * 10));
  // never exactly at a pole or a round number: the globe's horizon would lie exactly on the equator or a meridian,
  // where the map data has edges, and d3-geo then flips which side is inside from one frame to the next (flicker)
  return { lon: lon + 0.0731 + 0.25 * Math.max(0, f - T) / fps, lat: Math.max(-88.7, Math.min(88.7, lat + 0.0573)), zoom };
};

const Globe: FC<{ g: AtlasGraphic; p: Palette; accent: string }> = ({ g, p, accent }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const cam = cameraAt(g, frame, fps);
  const R = 350 * Math.pow(1.42, cam.zoom - 1);
  const cx = W / 2;
  const cy = H / 2 + 30;
  const projection = geoOrthographic().scale(R).translate([cx, cy]).rotate([-cam.lon, -cam.lat]).clipAngle(90).precision(R > 760 ? 0.6 : 1.6);   // the whole globe: coarser resampling, the same picture
  const path = geoPath(projection);
  const visible = (lat: number, lon: number) => geoDistance([lon, lat], [cam.lon, cam.lat]) < Math.PI / 2 - 0.02;
  const ink = p.ink;
  const red = accent;
  const since = (at: number) => frame - at;
  const highlighted = new Set((g.highlight ?? []).map((h) => h.name));
  const fine = R > 760;                      // close in: the 1:50m coast

  return (
    <svg width={W} height={H} style={{ position: 'absolute', inset: 0 }}>
      <defs>
        <radialGradient id="ocean" cx="42%" cy="38%" r="70%">
          <stop offset="0%" stopColor={p.oceanIn} />
          <stop offset="100%" stopColor={p.oceanOut} />
        </radialGradient>
                <radialGradient id="shadowg"><stop offset="90%" stopColor="rgba(0,0,0,0.22)" /><stop offset="100%" stopColor="rgba(0,0,0,0)" /></radialGradient>
        <pattern id="hatch" width="10" height="10" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <line x1="0" y1="0" x2="0" y2="10" stroke={red} strokeWidth="2" opacity="0.35" />
        </pattern>
        <clipPath id="disc"><circle cx={cx} cy={cy} r={R} /></clipPath>
      </defs>
      <circle cx={cx + 8} cy={cy + 14} r={R * 1.04} fill="url(#shadowg)" />
      <circle cx={cx} cy={cy} r={R} fill="url(#ocean)" />
      <g clipPath="url(#disc)">
        <path d={path(GRATICULE as never) ?? ''} fill="none" stroke={p.grid} strokeWidth={1} />
        {/* the ocean floor: each depth band darker, like a relief map (the shallow shelf stays pale along the coasts) */}
        {DEPTHS.map((d, i) => <path key={`depth${i}`} d={path(d) ?? ''} fill={p.depths[i] ?? p.depths[p.depths.length - 1]} />)}
        <path d={path(fine ? LAND_FC : LAND_FC_110) ?? ''} fill={p.land} stroke={p.coast} strokeWidth={0.8} strokeLinejoin="round" />
        <path d={path(fine ? ICE_FC : ICE_110) ?? ''} fill={p.ice} stroke={p.coast} strokeWidth={0.6} strokeLinejoin="round" />
        {COUNTRIES.filter((c) => highlighted.has(c.properties.name)).map((c, i) => {
          const group = (g.highlight ?? []).find((h) => h.name === c.properties.name)?.group ?? 0;
          const tint = [red, '#2F6E8F', '#5E8A4F', '#C9962E'][group] ?? red;
          return <path key={i} d={path(c as never) ?? ''} fill={tint} opacity={0.34} stroke={tint} strokeWidth={1.4} />;
        })}
        {g.meridians ? (() => {
          const m = g.meridians;
          const k = ease(clamp(since(m.at) / (fps * 1.2)));
          if (k <= 0) return null;
          const lines = [];
          for (let lon = -180; lon < 180; lon += m.step) {
            const line = { type: 'LineString', coordinates: Array.from({ length: 37 }, (_, j) => [lon + 0.01, -89 + (178 * j * k) / 36]) };
            lines.push(<path key={`mer${lon}`} d={path(line as never) ?? ''} fill="none" stroke={ink} strokeWidth={1.3} strokeOpacity={0.45} strokeDasharray="6 6" />);
          }
          return <g>{lines}</g>;
        })() : null}
        {g.night ? (() => {
          // the real night: everything more than 90° from the sun, darker through civil, nautical and astronomical
          // twilight; the sun's point moves from `from` to `to` over the shot (the terminator sweeps)
          const n = g.night;
          const local = since(n.at);
          const appear = clamp(local / (fps * 0.6));
          if (appear <= 0) return null;
          const t = ease(clamp(local / Math.max(1, durationInFrames - n.at)));
          let dl = n.to[1] - n.from[1];
          if (dl > 180) dl -= 360;
          if (dl < -180) dl += 360;
          const sun: [number, number] = [n.from[1] + dl * t, lerp(n.from[0], n.to[0], t)];
          const anti: [number, number] = [sun[0] + 180, -sun[1]];
          const shade = p === PALETTES.dark ? '#050A10' : '#0E1B2B';
          return (
            <g opacity={appear}>
              {[90, 84, 78, 72].map((radius, i) => (
                <path key={`night${radius}`} d={path(geoCircle().center(anti).radius(radius).precision(2)() as never) ?? ''}
                      fill={shade} opacity={i === 0 ? 0.36 : 0.15} />
              ))}
            </g>
          );
        })() : null}
        {g.zone ? (() => {
          const z = g.zone;
          const pole: [number, number] = [0, z.lat < 0 ? -90 : 90];
          const grow = clamp(since(z.at) / (fps * 1.0));
          const circle = geoCircle().center(pole).radius(Math.max(0.01, (90 - Math.abs(z.lat)) * ease(grow)))();
          return grow > 0 ? (
            <g>
              <path d={path(circle as never) ?? ''} fill="url(#hatch)" />
              <path d={path(circle as never) ?? ''} fill="none" stroke={red} strokeWidth={4} />
            </g>
          ) : null;
        })() : null}
        {(g.rings ?? []).map((r, i) => {
          const grow = ease(clamp(since(r.at) / (fps * 0.9)));
          if (grow <= 0) return null;
          const circle = geoCircle().center([r.lon, r.lat]).radius(Math.max(0.01, (r.km / 111.2) * grow))();
          return (
            <g key={`ring${i}`}>
              <path d={path(circle as never) ?? ''} fill={p === PALETTES.dark ? 'rgba(233,227,214,0.10)' : 'rgba(60,110,120,0.16)'}
                    stroke={ink} strokeWidth={1.6} strokeOpacity={0.75} />
            </g>
          );
        })}
        {(g.routes ?? []).map((r, i) => {
          const local = since(r.at);
          if (local < 0) return null;
          const many = r.style === 'many';
          const k = ease(clamp(local / (fps * (many ? 0.7 : 1.3))));
          const arc = geoInterpolate([r.from[1], r.from[0]], [r.to[1], r.to[0]]);
          const n = 72;
          const line = { type: 'LineString', coordinates: Array.from({ length: n + 1 }, (_, j) => arc(Math.min(k, j / n))) };
          return (
            <path key={`route${i}`} d={path(line as never) ?? ''} fill="none"
                  stroke={many ? (p === PALETTES.dark ? '#E8B64C' : '#C9962E') : red}
                  strokeWidth={many ? 2.4 : 4.2} strokeOpacity={many ? 0.85 : 1}
                  strokeDasharray={r.dashed ? '14 10' : undefined} strokeLinecap="round" />
          );
        })}
      </g>
      <circle cx={cx} cy={cy} r={R} fill="none" stroke={p.rim} strokeWidth={2.2} opacity={0.9} />
      {/* labels and dots on top, only on the visible side */}
      {(g.routes ?? []).filter((r) => r.label && r.style !== 'many').map((r, i) => {
        const local = since(r.at) - fps * 1.1;
        if (local < 0) return null;
        const mid = geoInterpolate([r.from[1], r.from[0]], [r.to[1], r.to[0]])(0.5);
        if (!visible(mid[1], mid[0])) return null;
        const [x, y] = projection(mid as [number, number]) ?? [0, 0];
        return (
          <g key={`rl${i}`} opacity={clamp(local / 8)}>
            <rect x={x - 70} y={y - 44} width={140} height={34} rx={3} fill={p.card} stroke={ink} strokeWidth={1} />
            <text x={x} y={y - 21} textAnchor="middle" fontFamily={MONO} fontSize={18} fontWeight={700} fill={PALETTES.paper.ink}>{r.label}</text>
          </g>
        );
      })}
      {(g.rings ?? []).filter((r) => r.label).map((r, i) => {
        const local = since(r.at) - fps * 0.5;
        if (local < 0 || !visible(r.lat, r.lon)) return null;
        const [x, y] = projection([r.lon, r.lat]) ?? [0, 0];
        return (
          <g key={`ringl${i}`} opacity={clamp(local / 8)}>
            <circle cx={x} cy={y} r={5} fill={ink} />
            <text x={x} y={y - 14} textAnchor="middle" fontFamily={MONO} fontSize={17} fontWeight={700} fill={ink}
                  stroke={p.halo} strokeWidth={5} paintOrder="stroke">{r.label}</text>
          </g>
        );
      })}
      {(g.points ?? []).map((pt, i) => {
        const local = since(pt.at);
        if (local < 0 || !visible(pt.lat, pt.lon)) return null;
        const [x, y] = projection([pt.lon, pt.lat]) ?? [0, 0];
        const pop = spring({ frame: local, fps, config: { damping: 12, stiffness: 220 }, durationInFrames: 12 });
        const right = x < cx;
        return (
          <g key={`pt${i}`}>
            <circle cx={x} cy={y} r={8 * pop} fill={ink} stroke={p.card} strokeWidth={2.5} />
            <text x={x + (right ? 16 : -16)} y={y + 6} textAnchor={right ? 'start' : 'end'} fontFamily={MONO} fontSize={19}
                  fontWeight={700} letterSpacing={1} fill={ink} opacity={clamp(local / 6)} stroke={p.halo} strokeWidth={6}
                  paintOrder="stroke">{pt.name}</text>
          </g>
        );
      })}
      {(g.tags ?? []).map((t, i) => {
        // the figure the line says («14:42», «1940»): a paper tag pinned by its place, or high on the globe
        const local = since(t.at);
        if (local < 0) return null;
        const placed = t.lat !== null && t.lon !== null && visible(t.lat, t.lon);
        const [px, py] = placed ? (projection([t.lon as number, t.lat as number]) ?? [cx, cy]) : [cx + (i - 0.5) * 260, cy - R * 0.55];
        const pop = spring({ frame: local, fps, config: { damping: 12, stiffness: 200 }, durationInFrames: 14 });
        const w = Math.max(120, t.text.length * 26 + 40);
        const x = Math.max(40, Math.min(W - w - 40, px + (placed ? 26 : -w / 2)));
        const y = Math.max(110, py - (placed ? 92 : 30));
        return (
          <g key={`tag${i}`} opacity={clamp(local / 5)} transform={`translate(${x + w / 2}, ${y + 30}) scale(${0.85 + 0.15 * pop}) translate(${-(x + w / 2)}, ${-(y + 30)})`}>
            {placed ? <line x1={px} y1={py} x2={x + 18} y2={y + 60} stroke={PALETTES.paper.ink} strokeWidth={1.6} /> : null}
            <rect x={x} y={y} width={w} height={60} fill={PALETTES.paper.card} stroke={PALETTES.paper.ink} strokeWidth={1.5} />
            <text x={x + w / 2} y={y + 42} textAnchor="middle" fontFamily={SERIF} fontSize={40} fill={PALETTES.paper.ink}>{t.text}</text>
          </g>
        );
      })}
      {(g.highlight ?? []).filter((h) => h.label).map((h, i) => {
        const c = COUNTRIES.find((x) => x.properties.name === h.name);
        if (!c) return null;
        const centre = geoCentroid(c as never) as [number, number];
        if (!visible(centre[1], centre[0])) return null;
        const [x, y] = projection(centre) ?? [0, 0];
        return <text key={`hl${i}`} x={x} y={y} textAnchor="middle" fontFamily={MONO} fontSize={18} fontWeight={700} fill={ink}
                     stroke={p.halo} strokeWidth={5} paintOrder="stroke">{h.label}</text>;
      })}
      {g.meridians?.labels ? (() => {
        const out = [];
        for (let lon = -180; lon < 180; lon += g.meridians.step) {
          // labels near the camera's latitude (not by a pole, where they all meet), only for the meridians in front
          const at: [number, number] = [lon, Math.max(-50, Math.min(50, cam.lat - 18))];
          if (!visible(at[1], at[0]) || geoDistance(at, [cam.lon, cam.lat]) > 1.0) continue;
          const [x, y] = projection(at) ?? [0, 0];
          const hours = Math.round(lon / 15);
          out.push(<text key={`ml${lon}`} x={x} y={y} textAnchor="middle" fontFamily={MONO} fontSize={16} fill={ink}
                         opacity={clamp(since(g.meridians.at) / 20) * 0.85} stroke={p.halo} strokeWidth={4} paintOrder="stroke">
            {lon === 0 ? '0°' : `${Math.abs(lon)}°${lon > 0 ? 'E' : 'O'}`}{g.meridians.step === 15 ? ` · ${hours >= 0 ? '+' : '−'}${Math.abs(hours)} h` : ''}</text>);
        }
        return <g>{out}</g>;
      })() : null}
    </svg>
  );
};

/** Two identical clocks: «22:00» in Varsovia and A Coruña. */
const Clock: FC<{ time: string; label: string; size: number; ink: string; accent: string }> = ({ time, label, size, ink, accent }) => {
  const [h, m] = time.split(':').map((x) => parseInt(x, 10) || 0);
  const ha = ((h % 12) + m / 60) * 30;
  const ma = m * 6;
  const hand = (angle: number, length: number, width: number, color: string) => (
    <line x1={0} y1={0} x2={length * Math.sin((angle * Math.PI) / 180)} y2={-length * Math.cos((angle * Math.PI) / 180)}
          stroke={color} strokeWidth={width} strokeLinecap="round" />
  );
  return (
    <div style={{ textAlign: 'center' }}>
      <svg width={size} height={size} viewBox="-50 -50 100 100">
        <circle r={46} fill="#FBF7EC" stroke={ink} strokeWidth={2.5} />
        {Array.from({ length: 12 }, (_, i) => (
          <line key={i} x1={0} y1={-40} x2={0} y2={i % 3 === 0 ? -33 : -36} stroke={ink} strokeWidth={i % 3 === 0 ? 2.5 : 1.2}
                transform={`rotate(${i * 30})`} />
        ))}
        {hand(ha, 22, 4.5, ink)}
        {hand(ma, 33, 2.8, ink)}
        <circle r={3} fill={accent} />
      </svg>
      <div style={{ fontFamily: SERIF, fontSize: 34, marginTop: 4 }}>{time}</div>
      <div style={{ fontFamily: MONO, fontSize: 15, letterSpacing: 2, color: '#5E584C' }}>{label}</div>
    </div>
  );
};

/** A paper card: a date, a quote with its source, a list, a checklist or a note. */
const Card: FC<{ g: AtlasGraphic; p: Palette; accent: string }> = ({ g, p, accent }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const c = g.card;
  if (!c) return null;
  const local = frame - c.at;
  if (local < 0) return null;
  const pop = spring({ frame: local, fps, config: { damping: 15, stiffness: 160 }, durationInFrames: 16 });
  const ink = PALETTES.paper.ink;
  const left = c.side === 'left';
  const box: React.CSSProperties = {
    position: 'absolute', [left ? 'left' : 'right']: 110, bottom: c.kind === 'quote' ? 300 : 150, width: c.kind === 'quote' ? 520 : 470,
    background: p.card, border: `1.5px solid ${ink}`, boxShadow: '0 14px 40px rgba(0,0,0,0.28), inset 0 0 0 6px rgba(255,255,255,0.35)',
    padding: '26px 30px', color: ink, opacity: clamp(local / 6), transform: `translateY(${(1 - pop) * 30}px)`,
  };
  const small: React.CSSProperties = { fontFamily: MONO, fontSize: 15, letterSpacing: 2, textTransform: 'uppercase', color: '#5E584C' };
  let body: ReactNode = null;
  if (c.kind === 'date') {
    body = (
      <>
        <div style={{ fontFamily: SERIF, fontSize: 64, lineHeight: 1 }}>{c.big || c.title}</div>
        <div style={{ height: 2, background: ink, opacity: 0.25, margin: '12px 0' }} />
        {c.big && c.title ? <div style={{ ...small, color: ink }}>{c.title}</div> : null}
        {c.lines.map((l, i) => <div key={i} style={{ ...small, marginTop: 4 }}>{l}</div>)}
      </>
    );
  } else if (c.kind === 'quote') {
    body = (
      <>
        {c.title ? <div style={{ ...small, textAlign: 'center' }}>{c.title}</div> : null}
        {c.source ? <div style={{ ...small, fontSize: 12, textAlign: 'center', marginTop: 4, fontStyle: 'italic' }}>{c.source}</div> : null}
        <div style={{ fontFamily: SERIF, fontStyle: 'italic', fontSize: 31, lineHeight: 1.3, textAlign: 'center', marginTop: 18 }}>
          “{c.lines.join(' ')}”
        </div>
      </>
    );
  } else if (c.kind === 'clocks') {
    body = (
      <>
        {c.title ? <div style={{ ...small, textAlign: 'center', marginBottom: 10 }}>{c.title}</div> : null}
        <div style={{ display: 'flex', justifyContent: 'space-around', gap: 18 }}>
          {(c.lines.length ? c.lines : ['', '']).slice(0, 2).map((label, i) => (
            <Clock key={i} time={c.big || '22:00'} label={label} size={150} ink={ink} accent={accent} />
          ))}
        </div>
      </>
    );
  } else if (c.kind === 'choice') {
    // «¿Tú qué harías?»: the question, two options, and — when the line reveals it — the right one lit
    const answer = parseInt(c.source, 10);
    body = (
      <>
        <div style={{ ...small, color: accent }}>¿Tú qué harías?</div>
        <div style={{ fontFamily: SERIF, fontSize: 30, lineHeight: 1.25, marginTop: 8 }}>{c.title}</div>
        {c.lines.slice(0, 2).map((option, i) => {
          const lit = answer === i + 1 && local > fps * 1.2;
          return (
            <div key={i} style={{ marginTop: 12, padding: '10px 16px', border: `2px solid ${lit ? accent : ink}`, fontFamily: SERIF, fontSize: 26,
                                  background: lit ? 'rgba(184,50,42,0.10)' : 'transparent', opacity: clamp((local - 6 - i * 6) / 6) }}>
              <span style={{ fontFamily: MONO, fontSize: 18, marginRight: 12 }}>{'AB'[i]}</span>{option}{lit ? ' ✓' : ''}
            </div>
          );
        })}
      </>
    );
  } else if (c.kind === 'checks') {
    body = (
      <>
        {c.title ? <div style={small}>{c.title}</div> : null}
        {c.lines.map((l, i) => {
          const ticked = local > fps * (0.6 + 0.5 * i);
          return (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 14, marginTop: 12, fontFamily: SERIF, fontSize: 30 }}>
              <span style={{ width: 24, height: 24, border: `2px solid ${ink}`, display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                             fontSize: 20, color: accent }}>{ticked ? '✓' : ''}</span>
              {l}
            </div>
          );
        })}
      </>
    );
  } else {
    body = (
      <>
        {c.title ? <div style={small}>{c.title}</div> : null}
        {c.lines.map((l, i) => (
          <div key={i} style={{ fontFamily: SERIF, fontSize: 32, marginTop: 8, opacity: clamp((local - i * 8) / 6) }}>{l}</div>
        ))}
      </>
    );
  }
  return <div style={box}>{body}</div>;
};

const Stamp: FC<{ g: AtlasGraphic; accent: string }> = ({ g, accent }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  if (!g.stamp) return null;
  const local = frame - g.stamp.at;
  if (local < 0) return null;
  const hit = spring({ frame: local, fps, config: { damping: 9, stiffness: 260 }, durationInFrames: 10 });
  const right = g.card?.side !== 'right';
  return (
    <div style={{ position: 'absolute', [right ? 'right' : 'left']: 230, bottom: 160, transform: `rotate(-8deg) scale(${2 - hit})`,
                  opacity: clamp(local / 3), border: `4px solid ${accent}`, padding: '8px 22px', color: accent, fontFamily: MONO,
                  fontWeight: 800, fontSize: 34, letterSpacing: 4, boxShadow: `inset 0 0 0 2px ${accent}`, mixBlendMode: 'multiply' }}>
      {g.stamp.text}
    </div>
  );
};

const Headline: FC<{ g: AtlasGraphic; p: Palette; accent: string }> = ({ g, p, accent }) => {
  const frame = useCurrentFrame();
  if (!g.headline) return null;
  const local = frame - g.headline.at;
  if (local < 0) return null;
  return (
    <div style={{ position: 'absolute', top: 70, left: 0, right: 0, opacity: clamp(local / 10), transform: `translateY(${(1 - clamp(local / 12)) * 14}px)` }}>
      <KeyTitle text={g.headline.text} size={64} color={p.ink} accent={accent} />
    </div>
  );
};

/** The brand top left and the chapter bar top right: I · II · III · IV · V, the current one in the accent colour with
 * its name in italics under it. */
const Header: FC<{ g: AtlasGraphic; p: Palette; accent: string }> = ({ g, p, accent }) => {
  const chapters = g.chapters ?? [];
  const roman = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X'];
  return (
    <>
      {g.brand ? (
        <div style={{ position: 'absolute', left: 64, top: 52, fontFamily: MONO, fontSize: 18, letterSpacing: 5, color: p.ink, opacity: 0.85,
                      textTransform: 'uppercase', display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ fontSize: 22, color: accent }}>✦</span>{g.brand}
        </div>
      ) : null}
      {chapters.length ? (
        <div style={{ position: 'absolute', right: 64, top: 44, display: 'flex', gap: 34 }}>
          {chapters.slice(0, 10).map((name, i) => {
            const on = i + 1 === g.chapter;
            return (
              <div key={i} style={{ position: 'relative', textAlign: 'center', minWidth: 30 }}>
                <div style={{ fontFamily: SERIF, fontSize: 26, color: on ? accent : p.soft, opacity: on ? 1 : 0.75 }}>{roman[i]}</div>
                {on ? <div style={{ height: 2, background: accent, margin: '4px auto 0', width: 38 }} /> : null}
                {on ? (
                  <div style={{ position: 'absolute', top: 44, right: '50%', transform: 'translateX(50%)', whiteSpace: 'nowrap',
                                fontFamily: SERIF, fontStyle: 'italic', fontSize: 22, letterSpacing: 1, color: p.ink }}>{name}</div>
                ) : null}
              </div>
            );
          })}
        </div>
      ) : null}
    </>
  );
};

/** «I — Nobody to *fly to*»: the chapter's title card. */
const TitleCard: FC<{ g: AtlasGraphic; p: Palette; accent: string }> = ({ g, p, accent }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = g.title;
  if (!t) return null;
  const a = clamp(frame / (fps * 0.5));
  const b = clamp((frame - fps * 0.25) / (fps * 0.6));
  return (
    <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 26, opacity: a }}>
        <div style={{ width: 120 * a, height: 1.5, background: p.ink, opacity: 0.5 }} />
        <div style={{ fontFamily: SERIF, fontSize: 64, color: p.ink }}>{t.number}</div>
        <div style={{ width: 120 * a, height: 1.5, background: p.ink, opacity: 0.5 }} />
      </div>
      <div style={{ marginTop: 26, opacity: b, transform: `translateY(${(1 - b) * 16}px)` }}>
        <KeyTitle text={t.text} size={84} color={p.ink} accent={accent} />
      </div>
    </AbsoluteFill>
  );
};

const fmt = (v: number) => (Math.abs(v) >= 1000 ? v.toLocaleString('es-ES') : String(Math.round(v * 10) / 10));

const Chart: FC<{ g: AtlasGraphic; p: Palette; accent: string }> = ({ g, p, accent }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const c = g.chart;
  if (!c) return null;
  const ink = p.ink;
  const title = (
    <div style={{ position: 'absolute', left: 160, top: 190, fontFamily: MONO, fontSize: 20, letterSpacing: 3, color: ink, opacity: 0.85 }}>{c.title}</div>
  );
  if (c.kind === 'bars' && c.bars) {
    const max = Math.max(...c.bars.map((b) => b.value ?? 0), 1);
    return (
      <AbsoluteFill>
        <div style={{ position: 'absolute', left: 160, top: H / 2 - (c.bars.length * 130) / 2 - 40, fontFamily: MONO, fontSize: 20,
                      letterSpacing: 3, color: ink, opacity: 0.85 }}>{c.title}</div>
        {c.bars.map((b, i) => {
          const k = ease(clamp((frame - fps * (0.3 + 0.9 * i)) / (fps * 1.0)));
          const width = 1300 * ((b.value ?? 0) / max) * k;
          const shown = Number.isInteger(b.value ?? 0) ? Math.round((b.value ?? 0) * k) : (b.value ?? 0) * k;
          return (
            <div key={i} style={{ position: 'absolute', left: 160, top: H / 2 - (c.bars!.length * 130) / 2 + 40 + i * 130, opacity: clamp((frame - fps * (0.2 + 0.9 * i)) / 6) }}>
              <div style={{ fontFamily: MONO, fontSize: 17, letterSpacing: 2, color: p.soft, textTransform: 'uppercase' }}>{b.label}</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 22, marginTop: 10 }}>
                <div style={{ width: Math.max(4, width), height: 44, background: i === c.bars!.length - 1 ? '#2F5674' : '#6F6553' }} />
                <div style={{ fontFamily: SERIF, fontSize: 40, color: ink }}>{fmt(shown)} {b.unit || c.unit}</div>
              </div>
            </div>
          );
        })}
      </AbsoluteFill>
    );
  }
  if (c.kind === 'profile' && c.points) {
    const top = Math.max(...c.points, c.line?.value ?? 0, c.cruise ?? 0) * 1.1 || 1;
    const x0 = 160, x1 = 1760, y0 = 880, y1 = 260;
    const X = (i: number) => x0 + ((x1 - x0) * i) / (c.points!.length - 1);
    const Y = (v: number) => y0 - ((y0 - y1) * v) / top;
    const grow = ease(clamp((frame - fps * 0.4) / (fps * 1.4)));
    const terrain = `M${x0},${y0} ` + c.points.map((v, i) => `L${X(i)},${Y(v * grow)}`).join(' ') + ` L${x1},${y0} Z`;
    const ticks = [0, top / 4, top / 2, (3 * top) / 4].map((v) => Math.round(v));
    const plane = clamp((frame - fps * 0.8) / (fps * 4));
    const cruise = c.cruise ?? null;
    return (
      <AbsoluteFill>
        {title}
        <svg width={W} height={H} style={{ position: 'absolute', inset: 0 }}>
          <line x1={x0} y1={y0} x2={x1} y2={y0} stroke={ink} strokeWidth={1.5} />
          <line x1={x0} y1={y0} x2={x0} y2={y1} stroke={ink} strokeWidth={1.5} />
          {ticks.map((v, i) => (
            <g key={i}>
              <line x1={x0 - 10} y1={Y(v)} x2={x0} y2={Y(v)} stroke={ink} />
              <text x={x0 - 18} y={Y(v) + 6} textAnchor="end" fontFamily={MONO} fontSize={16} fill={p.soft}>{v} {c.unit}</text>
            </g>
          ))}
          <path d={terrain} fill={p.ice} stroke={ink} strokeWidth={2} />
          {c.line ? (
            <g opacity={clamp((frame - fps * 1.2) / 8)}>
              <line x1={x0} y1={Y(c.line.value!)} x2={x1} y2={Y(c.line.value!)} stroke="#3C7A6E" strokeWidth={2.5} strokeDasharray="12 8" />
              <text x={x0 + 14} y={Y(c.line.value!) - 12} fontFamily={MONO} fontSize={17} fontWeight={700} fill="#3C7A6E">{c.line.label}</text>
              {/* the terrain above the safe line, in red */}
              <clipPath id="above"><rect x={x0} y={y1 - 50} width={x1 - x0} height={Y(c.line.value!) - y1 + 50} /></clipPath>
              <path d={terrain} fill="none" stroke={accent} strokeWidth={5} clipPath="url(#above)" />
            </g>
          ) : null}
          {cruise !== null ? (
            <g>
              <line x1={x0} y1={Y(cruise)} x2={x1} y2={Y(cruise)} stroke={ink} strokeWidth={1} strokeDasharray="4 8" opacity={0.5} />
              <text x={x1} y={Y(cruise) - 12} textAnchor="end" fontFamily={MONO} fontSize={16} fill={p.soft}>{`${fmt(cruise)} ${c.unit}`}</text>
              <g transform={`translate(${x0 + (x1 - x0) * plane}, ${Y(cruise)}) scale(1.6)`}><path d={ICON_PATHS.plane} fill={ink} transform="translate(-12,-12) rotate(90 12 12)" /></g>
            </g>
          ) : null}
        </svg>
      </AbsoluteFill>
    );
  }
  if (c.kind === 'thermo' && c.value !== undefined && c.min !== undefined && c.max !== undefined) {
    const k = ease(clamp((frame - fps * 0.4) / (fps * 1.6)));
    const v = lerp(c.max, c.value, k);
    const x = 560, top = 250, bottom = 820;
    const Y = (t: number) => bottom - ((bottom - top) * (t - c.min!)) / (c.max! - c.min!);
    const ticks = Array.from({ length: 5 }, (_, i) => c.min! + ((c.max! - c.min!) * i) / 4);
    return (
      <AbsoluteFill>
        {title}
        <svg width={W} height={H} style={{ position: 'absolute', inset: 0 }}>
          <rect x={x - 22} y={top - 20} width={44} height={bottom - top + 40} rx={22} fill={p.card} stroke={ink} strokeWidth={2.5} />
          <rect x={x - 11} y={Y(v)} width={22} height={bottom - Y(v) + 20} fill="#2F5674" />
          <circle cx={x} cy={bottom + 46} r={42} fill="#2F5674" stroke={ink} strokeWidth={2.5} />
          {ticks.map((t, i) => (
            <g key={i}>
              <line x1={x - 50} y1={Y(t)} x2={x - 30} y2={Y(t)} stroke={ink} />
              <text x={x - 60} y={Y(t) + 6} textAnchor="end" fontFamily={MONO} fontSize={17} fill={p.soft}>{Math.round(t)} {c.unit}</text>
            </g>
          ))}
          <line x1={x + 30} y1={Y(v)} x2={x + 90} y2={Y(v)} stroke={ink} strokeWidth={1.5} />
          <text x={x + 104} y={Y(v) + 14} fontFamily={SERIF} fontSize={52} fill={ink}>{Math.round(v)} {c.unit}</text>
          {c.label ? <text x={x + 106} y={Y(v) + 52} fontFamily={MONO} fontSize={18} letterSpacing={2} fill={accent}
                          opacity={clamp((frame - fps * 2) / 8)}>{c.label}</text> : null}
        </svg>
      </AbsoluteFill>
    );
  }
  return null;
};

/** Line drawings (24-unit grid), drawn stroke by stroke. */
const ICON_PATHS: Record<string, string> = {
  plane: 'M12 2c.8 0 1.3.9 1.3 2v5.2l8.2 4.6v2.1l-8.2-2.5v4.4l2.4 1.8v1.7L12 20.4l-3.7.9v-1.7l2.4-1.8v-4.4l-8.2 2.5v-2.1l8.2-4.6V4c0-1.1.5-2 1.3-2z',
  twinjet: 'M12 2c.8 0 1.3.9 1.3 2v5.2l8.2 4.6v2.1l-8.2-2.5v4.4l2.4 1.8v1.7L12 20.4l-3.7.9v-1.7l2.4-1.8v-4.4l-8.2 2.5v-2.1l8.2-4.6V4c0-1.1.5-2 1.3-2zM6.2 11.6a1 1.6 0 1 0 2 0a1 1.6 0 1 0-2 0M15.8 11.6a1 1.6 0 1 0 2 0a1 1.6 0 1 0-2 0',
  ship: 'M3 16l2 4h14l2-4H3zM6 16V10h12v6M9 10V6h6v4M12 6V3',
  train: 'M6 3h12a2 2 0 0 1 2 2v10a3 3 0 0 1-3 3H7a3 3 0 0 1-3-3V5a2 2 0 0 1 2-2zM4 10h16M8 15h.01M16 15h.01M7 18l-2 3M17 18l2 3',
  car: 'M3 13l2-5a2 2 0 0 1 2-1h10a2 2 0 0 1 2 1l2 5v4H3v-4zM3 13h18M7 17v2M17 17v2M7 15h.01M17 15h.01',
  truck: 'M2 6h11v10H2zM13 9h4l4 4v3h-8M6 19a2 2 0 1 0 0-4a2 2 0 0 0 0 4M17 19a2 2 0 1 0 0-4a2 2 0 0 0 0 4',
  thermometer: 'M10 4a2 2 0 0 1 4 0v10.5a4 4 0 1 1-4 0zM12 9v8M14 6h2M14 9h2M14 12h2',
  fuel: 'M5 5h9l3 3v12H5zM5 10h12M9 5V3h3v2M17 8l2-2 1 1v9a2 2 0 0 1-2 2',
  hospital: 'M4 21V7l8-4 8 4v14H4zM10 11h4M12 9v4M9 21v-4h6v4',
  building: 'M5 21V3h10v18M15 9h4v12M8 7h4M8 11h4M8 15h4M3 21h18',
  person: 'M12 7a3 3 0 1 0 0-6a3 3 0 0 0 0 6zM5 22v-4a7 7 0 0 1 14 0v4',
  people: 'M8 8a3 3 0 1 0 0-6a3 3 0 0 0 0 6zM17 9a2.5 2.5 0 1 0 0-5a2.5 2.5 0 0 0 0 5zM2 21v-3a6 6 0 0 1 12 0v3M14 15a5 5 0 0 1 8 4v2',
  clock: 'M12 22a10 10 0 1 0 0-20a10 10 0 0 0 0 20zM12 6v6l4 2',
  mountain: 'M2 20l7-12 4 6 3-4 6 10H2zM9 8l2 3',
  snow: 'M12 2v20M3.3 7l17.4 10M3.3 17L20.7 7M9 4l3 2 3-2M9 20l3-2 3 2',
  factory: 'M2 21V10l6 3V10l6 3V6h4l2 15H2zM6 17h2M11 17h2M16 17h2',
  money: 'M2 6h20v12H2zM12 15a3 3 0 1 0 0-6a3 3 0 0 0 0 6zM5 9v.01M19 15v.01',
  phone: 'M7 2h10a1 1 0 0 1 1 1v18a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1zM11 19h2',
  satellite: 'M9 9l6 6M7 11l4-4 6 6-4 4zM3 7l4 4M7 3l4 4M17 13l4 4M13 17l4 4M15 21a6 6 0 0 0 6-6',
  lighthouse: 'M9 22l1-14h4l1 14H9zM8 8h8M10 8V5h4v3M12 2v3M4 5l4 1M20 5l-4 1M6 22h12',
  bridge: 'M2 16h20M2 16c4-8 16-8 20 0M6 16v4M18 16v4M10 12v4M14 12v4',
  warning: 'M12 3l10 18H2L12 3zM12 10v5M12 18v.01',
};

const IconView: FC<{ g: AtlasGraphic; p: Palette; accent: string }> = ({ g, p, accent }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  if (!g.icon) return null;
  const d = ICON_PATHS[g.icon.name] ?? ICON_PATHS.warning;
  const k = clamp(frame / (fps * 1.4));
  return (
    <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center' }}>
      <svg width={520} height={520} viewBox="-1 -1 26 26">
        <path d={d} fill="none" stroke={p.ink} strokeWidth={0.32} strokeLinecap="round" strokeLinejoin="round"
              pathLength={1} strokeDasharray={1} strokeDashoffset={1 - ease(k)} />
        {g.icon.name === 'twinjet' ? (
          <g opacity={clamp((frame - fps * 1.3) / 10)}>
            <ellipse cx={7.2} cy={11.6} rx={1.2} ry={1.8} fill={accent} opacity={0.85} />
            <ellipse cx={16.8} cy={11.6} rx={1.2} ry={1.8} fill={accent} opacity={0.85} />
          </g>
        ) : null}
      </svg>
      {g.icon.label ? (
        <div style={{ marginTop: 10, fontFamily: MONO, fontSize: 22, letterSpacing: 4, color: p.ink, opacity: clamp((frame - g.icon.at - fps * 0.4) / 8) }}>
          {g.icon.label}
        </div>
      ) : null}
    </AbsoluteFill>
  );
};

export const Atlas: FC<{ graphic: AtlasGraphic; durationInFrames: number }> = ({ graphic: g }) => {
  const p = g.dark ? PALETTES.dark : PALETTES.paper;
  const accent = g.dark ? '#E2A33B' : theme.accent;
  const memo = { p, accent };
  return (
    <AbsoluteFill style={{ background: `radial-gradient(ellipse 75% 70% at 50% 45%, ${p.page} 55%, ${p.pageEdge} 100%)` }}>
      {g.view === 'title' ? <TitleCard g={g} {...memo} /> : g.view === 'chart' ? <Chart g={g} {...memo} />
        : g.view === 'icon' ? <IconView g={g} {...memo} /> : <Globe g={g} {...memo} />}
      {g.view === 'globe' ? <><Card g={g} {...memo} /><Stamp g={g} accent={accent} /><Headline g={g} {...memo} /></> : null}
      <Header g={g} {...memo} />
      {/* paper grain from a fixed tile: the SVG noise filter was recomputed on every frame (a quarter of the render) */}
      <AbsoluteFill style={{ backgroundImage: `url(${GRAIN})`, backgroundSize: '256px 256px', opacity: g.dark ? 0.1 : 0.16,
                             mixBlendMode: 'multiply', pointerEvents: 'none' }} />
      <Vignette strength={g.dark ? 0.45 : 0.22} color={g.dark ? '0,0,0' : '90,70,40'} />
    </AbsoluteFill>
  );
};
