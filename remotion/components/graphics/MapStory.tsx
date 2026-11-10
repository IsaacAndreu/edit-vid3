import type { FC, ReactNode } from 'react';
import { geoArea, geoCentroid, geoGraticule10, geoMercator, geoPath } from 'd3-geo';
import { feature, mesh } from 'topojson-client';
import world50 from 'world-atlas/countries-50m.json';
import world110 from 'world-atlas/countries-110m.json';
import { AbsoluteFill, Img, interpolate, random, spring, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';
import type { MapaGraphic } from '../../graphics';

/**
 * Map explainer (pipeline/mapas.py), Johnny Harris / RealLifeLore look: one continuous camera over the world (Web
 * Mercator, 256 units = the globe); real satellite for the close-ups (land cut out over a drawn navy sea), a vintage
 * paper map for everything wider, the red marker drawn on top and boiling like ink (re-drawn 8 times a second), and
 * physical paper props: tags with tape, torn strips with a highlighter, tear-off calendar pages that flip, a rubber
 * stamp that shakes the camera. Every element comes in at its word (frames from the Python side).
 */

const RED = '#D9291D';
const PAPER = { ocean: '#A9C2C4', land: '#ECE2CA', tints: ['#E6C1A7', '#EEDAA4', '#D2DEB8'], coast: '#4a3322', border: '#6b4a32' };
const SAT_FADE: [number, number] = [7.3, 9.3];

type Feature = { type: string; id?: string; properties: { name: string }; geometry: unknown };
const clean = (features: Feature[]) => features.filter((f) => f.properties.name !== 'Antarctica' && geoArea(f as never) < 2 * Math.PI);
const COUNTRIES_50 = clean((feature(world50 as never, (world50 as never as { objects: { countries: never } }).objects.countries) as never as { features: Feature[] }).features);
const COUNTRIES_110 = clean((feature(world110 as never, (world110 as never as { objects: { countries: never } }).objects.countries) as never as { features: Feature[] }).features);
const BORDERS_50 = mesh(world50 as never, (world50 as never as { objects: { countries: never } }).objects.countries, (a: unknown, b: unknown) => a !== b);
const BORDERS_110 = mesh(world110 as never, (world110 as never as { objects: { countries: never } }).objects.countries, (a: unknown, b: unknown) => a !== b);
const GRATICULE = geoGraticule10();

const wx = (lon: number) => ((lon + 180) / 360) * 256;
const wy = (lat: number) => ((1 - Math.asinh(Math.tan((lat * Math.PI) / 180)) / Math.PI) / 2) * 256;
const unlat = (y: number) => (Math.atan(Math.sinh(Math.PI * (1 - (2 * y) / 256))) * 180) / Math.PI;
const unlon = (x: number) => (x / 256) * 360 - 180;
const clamp = (v: number, a = 0, b = 1) => Math.max(a, Math.min(b, v));
const quart = (t: number) => (t < 0.5 ? 8 * t ** 4 : 1 - (-2 * t + 2) ** 4 / 2);

interface Cam { x: number; y: number; z: number }

/** The camera at frame f: from the previous line's target to this one (quartic in-out), pulling out on the way when
 * the two places are far apart so both fit (the Google Earth jump), then a slow drift. */
const camera = (g: MapaGraphic, f: number, fps: number, W: number, H: number): Cam => {
  const a = { x: wx(g.prev.lon), y: wy(g.prev.lat), z: g.prev.zoom };
  const b = { x: wx(g.lon), y: wy(g.lat), z: g.zoom };
  let dx = b.x - a.x;
  if (dx > 128) dx -= 256;
  if (dx < -128) dx += 256;
  const dist = Math.hypot(dx, b.y - a.y);
  const fit = dist > 0 ? Math.log2((Math.min(W, H) * 0.7) / dist) : 99;
  const dip = Math.max(0, Math.min(a.z, b.z) - fit);
  const T = Math.round(fps * (1.3 + 0.12 * Math.abs(b.z - a.z) + 0.25 * dip));
  const t = clamp(f / T);
  const e = quart(t);
  const z = a.z + (b.z - a.z) * e - dip * Math.sin(Math.PI * t) + 0.12 * clamp((f - T) / (fps * 8));   // then a slow push
  return { x: a.x + dx * e, y: a.y + (b.y - a.y) * e, z };
};

/** A marker stroke: the polyline resampled every ~26 px, each point wobbling ±1.5 px, re-rolled 8 times a second. */
const wobble = (pts: [number, number][], seed: string, tick: number, amount = 1.5): [number, number][] => {
  const out: [number, number][] = [];
  for (let i = 0; i < pts.length - 1; i++) {
    const [x0, y0] = pts[i];
    const [x1, y1] = pts[i + 1];
    const steps = Math.max(1, Math.ceil(Math.hypot(x1 - x0, y1 - y0) / 26));
    for (let s = 0; s < steps; s++) out.push([x0 + ((x1 - x0) * s) / steps, y0 + ((y1 - y0) * s) / steps]);
  }
  out.push(pts[pts.length - 1]);
  return out.map(([x, y], i) => [x + (random(`${seed}x${i}t${tick}`) - 0.5) * 2 * amount + Math.sin(i * 0.7 + tick) * amount * 0.5,
    y + (random(`${seed}y${i}t${tick}`) - 0.5) * 2 * amount]);
};

const partial = (pts: [number, number][], p: number): [number, number][] => {
  if (p >= 1) return pts;
  const lengths = [0];
  for (let i = 1; i < pts.length; i++) lengths.push(lengths[i - 1] + Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]));
  const want = lengths[lengths.length - 1] * p;
  const out: [number, number][] = [pts[0]];
  for (let i = 1; i < pts.length; i++) {
    if (lengths[i] <= want) { out.push(pts[i]); continue; }
    const k = (want - lengths[i - 1]) / Math.max(1e-6, lengths[i] - lengths[i - 1]);
    out.push([pts[i - 1][0] + (pts[i][0] - pts[i - 1][0]) * k, pts[i - 1][1] + (pts[i][1] - pts[i - 1][1]) * k]);
    break;
  }
  return out;
};

const d = (pts: [number, number][]) => pts.map(([x, y], i) => `${i ? 'L' : 'M'} ${x.toFixed(1)} ${y.toFixed(1)}`).join(' ');

/** The red marker: a dark red underlay a little wider, the red core, a pink highlight up-left. */
const Ink: FC<{ pts: [number, number][]; width: number; dash?: boolean }> = ({ pts, width, dash }) => {
  if (pts.length < 2) return null;
  const path = d(pts);
  const dashes = dash ? `${width * 2.6} ${width * 2.2}` : undefined;
  return (
    <g fill="none" strokeLinecap="round" strokeLinejoin="round">
      <path d={path} stroke="#7a120c" strokeWidth={width + 1.6} strokeDasharray={dashes} />
      <path d={path} stroke={RED} strokeWidth={width} strokeDasharray={dashes} />
      <path d={path} stroke="#ff9a8a" strokeWidth={width * 0.3} strokeOpacity={0.3} transform="translate(-1 -1)" strokeDasharray={dashes} />
    </g>
  );
};

const pop = (f: number, fps: number) => spring({ frame: f, fps, config: { damping: 9, stiffness: 190, mass: 0.7 } });

const Tape: FC<{ w: number; rot: number }> = ({ w, rot }) => (
  <div style={{ position: 'absolute', left: '50%', top: -w * 0.12, width: w * 0.42, height: w * 0.16, transform: `translateX(-50%) rotate(${rot}deg)`,
    background: 'rgba(235,228,200,0.72)', boxShadow: '0 1px 2px rgba(0,0,0,0.15)' }} />
);

/** A paper tag slapped onto a place: cream card, a colour bar, tape; the subtitle types in on the next word. */
const Tag: FC<{ name: string; sub: string; x: number; y: number; f: number; fps: number; u: number; color: string; seed: number }> = ({ name, sub, x, y, f, fps, u, color, seed }) => {
  if (f < 0) return null;
  const s = pop(f, fps);
  const rot = (random(`tag${seed}`) - 0.5) * 6;
  const typed = sub.slice(0, Math.max(0, Math.floor((f - fps * 0.35) / 2)));
  return (
    <div style={{ position: 'absolute', left: x + 30 * u, top: y - 90 * u, transform: `scale(${0.55 + 0.45 * s}) rotate(${rot * s}deg)`, transformOrigin: '0 100%',
      opacity: clamp(s * 3), background: '#f4ecd8', padding: `${10 * u}px ${18 * u}px ${8 * u}px ${24 * u}px`, boxShadow: '0 8px 18px rgba(0,0,0,0.35)',
      borderLeft: `${8 * u}px solid ${color}` }}>
      <Tape w={220 * u} rot={rot * -1.4} />
      <div style={{ fontFamily: 'Oswald', fontWeight: 700, fontSize: 46 * u, color: '#1d1a16', letterSpacing: 1, whiteSpace: 'nowrap', lineHeight: 1.1 }}>{name}</div>
      {sub ? <div style={{ fontFamily: "'Special Elite'", fontSize: 22 * u, color: '#3b342b', whiteSpace: 'nowrap', minHeight: 24 * u }}>{typed}</div> : null}
    </div>
  );
};

/** A tear-off calendar page (or a clock, a price tag, a note) that pops in and can flip to another value. */
const Prop: FC<{ p: MapaGraphic['props'][number]; f: number; fps: number; u: number; W: number; H: number; i: number }> = ({ p, f, fps, u, W, H, i }) => {
  if (f < 0) return null;
  const s = pop(f, fps);
  const flipAt = fps * 1.1;
  const flip = p.flip ? clamp((f - flipAt) / (fps * 0.35)) : 0;
  const face = flip > 0.5 && p.flip ? p.flip : p;
  const angle = flip < 0.5 ? flip * 180 : (flip - 1) * 180;
  const left = p.side === 'left' ? W * 0.12 + i * 40 * u : W * 0.68 - i * 40 * u;
  const header = flip > 0.5 ? '#c8322b' : '#2f5da8';
  const w = 230 * u;
  return (
    <div style={{ position: 'absolute', left, top: H * 0.3 + i * 30 * u, width: w, transform: `scale(${0.55 + 0.45 * s}) rotate(${p.side === 'left' ? -4 : 4}deg) perspective(800px) rotateX(${angle}deg)`,
      opacity: clamp(s * 3), boxShadow: '0 10px 24px rgba(0,0,0,0.4)', background: '#f7f2e6', textAlign: 'center', borderRadius: p.kind === 'clock' ? '50%' : 4 * u }}>
      {p.kind === 'calendar' ? <>
        <div style={{ background: header, color: '#fff', fontFamily: 'Oswald', fontWeight: 700, fontSize: 34 * u, padding: `${6 * u}px 0`, position: 'relative' }}>
          {face.top}
          {[0.3, 0.7].map((k) => <span key={k} style={{ position: 'absolute', left: `${k * 100}%`, top: -10 * u, width: 12 * u, height: 22 * u, border: `${3 * u}px solid #444`, borderRadius: 8 * u }} />)}
        </div>
        <div style={{ fontFamily: 'Oswald', fontWeight: 700, fontSize: 96 * u, color: '#1b1b1b', lineHeight: 1.1 }}>{face.big}</div>
        <div style={{ fontFamily: "'Special Elite'", fontSize: 20 * u, color: '#555', paddingBottom: 10 * u }}>{face.sub}</div>
      </> : p.kind === 'clock' ? (
        <svg width={w} height={w} viewBox="0 0 100 100">
          <circle cx={50} cy={50} r={46} fill="#f7f2e6" stroke="#222" strokeWidth={4} />
          {[...Array(12)].map((_, k) => <line key={k} x1={50} y1={8} x2={50} y2={14} stroke="#222" strokeWidth={2} transform={`rotate(${k * 30} 50 50)`} />)}
          {(() => { const [h, m] = (face.big.match(/\d+/g) ?? ['12', '0']).map(Number); return <>
            <line x1={50} y1={50} x2={50} y2={26} stroke="#222" strokeWidth={4} strokeLinecap="round" transform={`rotate(${((h % 12) + (m || 0) / 60) * 30} 50 50)`} />
            <line x1={50} y1={50} x2={50} y2={14} stroke={RED} strokeWidth={2.5} strokeLinecap="round" transform={`rotate(${(m || 0) * 6} 50 50)`} /></>; })()}
          <text x={50} y={72} textAnchor="middle" fontFamily="Oswald" fontSize={9} fill="#333">{face.top}</text>
        </svg>
      ) : <>
        <div style={{ fontFamily: 'Oswald', fontWeight: 700, fontSize: 28 * u, color: '#fff', background: p.kind === 'price' ? '#2e7d32' : p.kind === 'flag' ? header : '#555', padding: `${4 * u}px 0` }}>{face.top}</div>
        <div style={{ fontFamily: 'Oswald', fontWeight: 700, fontSize: 72 * u, color: '#1b1b1b' }}>{face.big}</div>
        <div style={{ fontFamily: "'Special Elite'", fontSize: 20 * u, color: '#555', paddingBottom: 8 * u }}>{face.sub}</div>
      </>}
    </div>
  );
};

/** A torn paper strip with a yellow highlighter swipe across it. */
const Strip: FC<{ text: string; x: number; y: number; f: number; fps: number; u: number; seed: number }> = ({ text, x, y, f, fps, u, seed }) => {
  if (f < 0) return null;
  const s = pop(f, fps);
  const swipe = clamp((f - fps * 0.25) / (fps * 0.35));
  const jag = [...Array(14)].map((_, i) => `${(i / 13) * 100}% ${random(`j${seed}${i}`) * 12}%`).join(', ');
  const jag2 = [...Array(14)].map((_, i) => `${100 - (i / 13) * 100}% ${88 + random(`k${seed}${i}`) * 12}%`).join(', ');
  return (
    <div style={{ position: 'absolute', left: x - 160 * u, top: y, transform: `scale(${0.6 + 0.4 * s}) rotate(${(random(`r${seed}`) - 0.5) * 5}deg)`, opacity: clamp(s * 3),
      filter: 'drop-shadow(0 6px 10px rgba(0,0,0,0.35))' }}>
      <div style={{ background: '#f3ead2', padding: `${10 * u}px ${26 * u}px`, clipPath: `polygon(${jag}, ${jag2})`, position: 'relative' }}>
        <div style={{ position: 'absolute', left: 14 * u, top: '28%', height: '48%', width: `calc(${swipe * 100}% - ${28 * u}px)`, background: 'rgba(255,221,0,0.75)', borderRadius: 6 * u }} />
        <span style={{ position: 'relative', fontFamily: "'Special Elite'", fontSize: 34 * u, color: '#1d1a16', whiteSpace: 'nowrap', letterSpacing: 1 }}>{text}</span>
      </div>
    </div>
  );
};

export const MapStory: FC<{ graphic: MapaGraphic; durationInFrames: number }> = ({ graphic: g, durationInFrames: dur }) => {
  const f = useCurrentFrame();
  const { fps, width: W, height: H } = useVideoConfig();
  const u = Math.min(W, H) / 1080;
  const tick = Math.floor((f * 8) / fps);                  // the ink boils at 8 fps
  const stamp = g.stamp && f >= g.stamp.at ? f - g.stamp.at : -1;
  const shake = stamp >= 0 ? 16 * Math.exp(-stamp / 5) : 0;
  const cam = camera(g, f, fps, W, H);
  const k = 2 ** cam.z;
  const hx = Math.sin(f / 29) * 2 + (shake ? (random(`sh${f}`) - 0.5) * 2 * shake : 0);
  const hy = Math.sin(f / 37) * 2 + (shake ? (random(`sv${f}`) - 0.5) * 2 * shake : 0);
  const rot = Math.sin(f / 41) * 0.06;
  // screen position of a point (the shortest way round the date line)
  const px = (lat: number, lon: number): [number, number] => {
    let dx = wx(lon) - cam.x;
    if (dx > 128) dx -= 256;
    if (dx < -128) dx += 256;
    return [W / 2 + dx * k, H / 2 + (wy(lat) - cam.y) * k];
  };
  const satOpacity = clamp((cam.z - SAT_FADE[0]) / (SAT_FADE[1] - SAT_FADE[0]));
  const paper = satOpacity < 1;
  const lon0 = unlon(cam.x);
  const lat0 = unlat(cam.y);
  const projection = geoMercator().rotate([-lon0, 0]).scale((256 * k) / (2 * Math.PI)).translate([W / 2, H / 2 + (wy(0) - cam.y) * k])
    .clipExtent([[-60, -60], [W + 60, H + 60]]);
  const path = geoPath(projection as never);
  const countries = cam.z >= 4.5 ? COUNTRIES_50 : COUNTRIES_110;
  const borders = cam.z >= 4.5 ? BORDERS_50 : BORDERS_110;
  const lit = new Set((g.highlight ?? []).map((h) => h.name));
  const names: Record<string, string> = Object.fromEntries((g.highlight ?? []).map((h) => [h.name, h.label || h.name]));
  const splitX = g.split ? px(g.lat, g.split.lon)[0] : null;

  const map = paper ? (
    <svg width={W} height={H} style={{ position: 'absolute', opacity: 1 - satOpacity }}>
      <rect width={W} height={H} fill={PAPER.ocean} />
      {[30, 19, 10].map((w, i) => (
        <path key={w} d={path({ type: 'FeatureCollection', features: countries } as never) ?? ''} fill="none" stroke="#7e9ea3" strokeOpacity={0.18 + i * 0.08} strokeWidth={w * u} strokeLinejoin="round" />
      ))}
      {countries.map((c, i) => (
        <path key={c.id ?? i} d={path(c as never) ?? ''} fill={lit.has(c.properties.name) ? (g.split && i % 2 ? '#c96b5c' : '#b8463a') : PAPER.tints[(Number(c.id) || i) % 3]}
          fillOpacity={lit.has(c.properties.name) ? 0.85 : 1} />
      ))}
      <path d={path(GRATICULE as never) ?? ''} fill="none" stroke="#5b4a3a" strokeOpacity={0.26} strokeWidth={1} />
      <path d={path(borders as never) ?? ''} fill="none" stroke={PAPER.border} strokeWidth={1.2 * u} strokeDasharray={`${5 * u} ${4 * u}`} />
      <path d={path({ type: 'FeatureCollection', features: countries } as never) ?? ''} fill="none" stroke={PAPER.coast} strokeWidth={1.25 * u} />
      {cam.z < 7 ? countries.map((c, i) => {
        if (!lit.has(c.properties.name)) return null;            // only the countries the line names, in its language
        const area = geoArea(c as never);
        const p = projection(geoCentroid(c as never));
        if (!p || p[0] < 40 || p[0] > W - 40 || p[1] < 40 || p[1] > H - 40) return null;
        return <text key={`l${i}`} x={p[0]} y={p[1]} textAnchor="middle" fontFamily="Cinzel" fontWeight={700} fontSize={Math.min(28, 12 + Math.sqrt(area) * k * 2) * u}
          letterSpacing={4 * u} fill="#3b2d22" fillOpacity={0.8}>{(names[c.properties.name] ?? c.properties.name).toUpperCase()}</text>;
      }) : null}
    </svg>
  ) : null;

  const sat = satOpacity > 0 && g.sat?.length ? (
    <div style={{ position: 'absolute', inset: 0, opacity: satOpacity, background: 'radial-gradient(ellipse at 50% 50%, #14304A 0%, #0B1E31 80%)' }}>
      {[...g.sat].sort((a, b) => a.z - b.z).map((layer, i) => {
        const scale = 2 ** (cam.z - layer.z);
        const [cx, cy] = px(layer.lat, layer.lon);
        // the finer mosaic fades in as the camera passes its level
        const o = i === 0 ? 1 : clamp((cam.z - (layer.z - 1.2)) / 0.8);
        if (o <= 0 || scale < 0.05) return null;
        return <Img key={i} src={staticFile(layer.src)} style={{ position: 'absolute', left: cx - 960 * scale, top: cy - 540 * scale, width: 1920 * scale, height: 1080 * scale,
          opacity: o, maskImage: 'radial-gradient(ellipse 50% 50% at 50% 50%, #000 82%, transparent 100%)', WebkitMaskImage: 'radial-gradient(ellipse 50% 50% at 50% 50%, #000 82%, transparent 100%)' }} />;
      })}
    </div>
  ) : null;

  const ink: ReactNode[] = [];
  const width = 8.5 * u;
  if (g.split && splitX !== null) {
    ink.push(<rect key="sl" x={0} y={0} width={Math.max(0, splitX)} height={H} fill="#b3261e" opacity={0.16} />);
    ink.push(<rect key="sr" x={splitX} y={0} width={Math.max(0, W - splitX)} height={H} fill="#1e4fb3" opacity={0.16} />);
    ink.push(<Ink key="sx" pts={wobble([[splitX, -20], [splitX, H + 20]], 'split', tick)} width={width} />);
  }
  if (g.line && f >= g.line.at) {
    const p = clamp((f - g.line.at) / (fps * 0.8));
    const pts = g.line.points.map(([la, lo]) => px(la, lo));
    ink.push(<Ink key="line" pts={partial(wobble(pts, 'line', tick), p)} width={width} dash={g.line.dashed} />);
  }
  if (g.path && f >= g.path.at) {
    const pts = g.path.points.map(([la, lo]) => px(la, lo));
    const p = clamp((f - g.path.at) / Math.max(1, dur - g.path.at - fps * 0.3));
    const done = partial(pts, p);
    ink.push(<path key="path" d={d(pts)} fill="none" stroke="#fff" strokeOpacity={0.6} strokeWidth={4 * u} strokeDasharray={`${2 * u} ${12 * u}`} strokeLinecap="round" />);
    const head = done[done.length - 1];
    ink.push(<g key="pathhead"><circle cx={head[0]} cy={head[1]} r={22 * u} fill="#fff" opacity={0.25} /><circle cx={head[0]} cy={head[1]} r={8 * u} fill={RED} stroke="#fff" strokeWidth={3 * u} /></g>);
  }
  if (g.circle && f >= g.circle.at) {
    const [cx, cy] = px(g.circle.lat, g.circle.lon);
    const r = Math.max(70 * u, Math.min(W, H) * 0.16);
    const turns = 1.12;
    const pts: [number, number][] = [...Array(64)].map((_, i) => {
      const a = -Math.PI * 0.75 + (i / 63) * turns * Math.PI * 2;
      const rr = r * (1 + 0.06 * Math.sin(i / 7) + (i / 63) * 0.05);
      return [cx + Math.cos(a) * rr * 1.08, cy + Math.sin(a) * rr * 0.92];
    });
    const p = clamp((f - g.circle.at) / (fps * 0.55));
    ink.push(<Ink key="circle" pts={partial(wobble(pts, 'circle', tick, 1.2), p)} width={width} />);
    if (g.circle.word && p >= 1) {
      const wp = clamp((f - g.circle.at - fps * 0.55) / (fps * 0.4));
      ink.push(<text key="cword" x={cx + r * 1.15} y={cy - r * 0.7} fontFamily="Caveat" fontWeight={700} fontSize={64 * u} fill={RED}
        transform={`rotate(-8 ${cx + r * 1.15} ${cy - r * 0.7})`} style={{ clipPath: `inset(0 ${100 - wp * 100}% 0 0)` }}>{g.circle.word}</text>);
    }
  }

  const lineCount = g.line?.count && f >= g.line.at + fps * 0.6 ? (() => {
    const pts = g.line.points.map(([la, lo]) => px(la, lo));
    const mid = pts[Math.floor(pts.length / 2)];
    const t = clamp((f - g.line.at - fps * 0.6) / (fps * 0.8));
    const m = g.line.count.match(/[\d.,]+/);
    const value = m ? Number(m[0].replace(',', '.')) : 0;
    const shown = m ? g.line.count.replace(m[0], (value * t).toFixed(m[0].includes(',') || m[0].includes('.') ? 1 : 0).replace('.', m[0].includes(',') ? ',' : '.')) : g.line.count;
    const s = pop(f - g.line.at - fps * 0.6, fps);
    return <div style={{ position: 'absolute', left: mid[0] + 26 * u, top: mid[1] - 40 * u, transform: `scale(${0.6 + 0.4 * s})`, background: '#141414', color: '#fff',
      fontFamily: 'Oswald', fontWeight: 700, fontSize: 44 * u, padding: `${4 * u}px ${16 * u}px`, boxShadow: '0 8px 18px rgba(0,0,0,0.4)' }}>{shown}
      {g.line.label ? <div style={{ fontFamily: "'Special Elite'", fontSize: 18 * u, fontWeight: 400, opacity: 0.8 }}>{g.line.label}</div> : null}</div>;
  })() : null;

  const stampEl = g.stamp && stamp >= 0 ? (() => {
    const s = spring({ frame: stamp, fps, config: { damping: 14, stiffness: 260 } });
    return <div style={{ position: 'absolute', left: W / 2, top: H * 0.38, transform: `translate(-50%, -50%) scale(${2.2 - 1.2 * s}) rotate(-9deg)`, opacity: clamp(s * 2),
      border: `${8 * u}px solid ${RED}`, color: RED, fontFamily: 'Oswald', fontWeight: 700, fontSize: 130 * u, padding: `0 ${30 * u}px`, letterSpacing: 6 * u,
      mixBlendMode: satOpacity > 0.5 ? 'normal' : 'multiply', textShadow: satOpacity > 0.5 ? '0 0 12px rgba(0,0,0,0.35)' : undefined, maskImage: 'repeating-radial-gradient(circle at 30% 40%, #000 0 3px, rgba(0,0,0,0.7) 3px 5px)' }}>{g.stamp.text}</div>;
  })() : null;

  return (
    <AbsoluteFill style={{ background: '#0B1E31', overflow: 'hidden' }}>
      <AbsoluteFill style={{ transform: `translate(${hx}px, ${hy}px) rotate(${rot}deg) scale(1.01)` }}>
        {sat}
        {map}
        <svg width={W} height={H} style={{ position: 'absolute' }}>{ink}</svg>
        {g.split && splitX !== null ? <>
          <div style={{ position: 'absolute', right: W - splitX + 30 * u, bottom: H * 0.08, fontFamily: 'Oswald', fontWeight: 700, fontSize: 110 * u, color: '#c0392b', opacity: 0.75, letterSpacing: 6 * u }}>{g.split.left}</div>
          <div style={{ position: 'absolute', left: splitX + 30 * u, bottom: H * 0.08, fontFamily: 'Oswald', fontWeight: 700, fontSize: 110 * u, color: '#2f6fd6', opacity: 0.75, letterSpacing: 6 * u }}>{g.split.right}</div>
        </> : null}
        {(g.tags ?? []).map((t, i) => { const [x, y] = px(t.lat, t.lon); return <Tag key={i} name={t.name} sub={t.sub} x={x} y={y} f={f - t.at} fps={fps} u={u} seed={i + (g.seed ?? 0) * 7} color={['#c0392b', '#2f5da8', '#2e7d32'][i % 3]} />; })}
        {(g.strips ?? []).map((s, i) => { const [x, y] = px(s.lat, s.lon); return <Strip key={i} text={s.text} x={x} y={y + 40 * u + i * 80 * u} f={f - s.at} fps={fps} u={u} seed={i} />; })}
        {lineCount}
      </AbsoluteFill>
      {(g.props ?? []).map((p, i) => <Prop key={i} p={p} f={f - p.at} fps={fps} u={u} W={W} H={H} i={i} />)}
      {g.tracker ? (
        <div style={{ position: 'absolute', left: 40 * u, top: 40 * u, background: '#f4ecd8', padding: `${12 * u}px ${20 * u}px`, transform: 'rotate(-2deg)', boxShadow: '0 8px 18px rgba(0,0,0,0.4)',
          fontFamily: "'Special Elite'", color: '#2a241c', fontSize: 20 * u, minWidth: 220 * u }}>
          <Tape w={220 * u} rot={3} />
          <div>{g.tracker.title}</div><div>{g.tracker.date}</div>
          <div style={{ fontFamily: 'Oswald', fontWeight: 700, fontSize: 52 * u, color: '#1b1b1b', lineHeight: 1.1 }}>{g.tracker.time}</div>
          <div>{g.tracker.counter}</div>
        </div>
      ) : null}
      {stampEl}
      {g.end && f >= 0 ? (() => {
        const s = pop(f - fps * 0.3, fps);
        const strike = clamp((f - fps * 1.0) / (fps * 0.35));
        const write = clamp((f - fps * 1.4) / (fps * 0.5));
        return <div style={{ position: 'absolute', left: '50%', bottom: H * 0.1, transform: `translateX(-50%) scale(${0.6 + 0.4 * s}) rotate(-1.5deg)`, opacity: clamp(s * 3),
          background: '#f4ecd8', padding: `${14 * u}px ${36 * u}px`, boxShadow: '0 12px 24px rgba(0,0,0,0.45)', textAlign: 'center' }}>
          <Tape w={300 * u} rot={-2} />
          <div style={{ fontFamily: "'Special Elite'", fontSize: 22 * u, color: '#3b342b' }}>{g.end.label}</div>
          <div style={{ position: 'relative', display: 'inline-block', fontFamily: 'Oswald', fontWeight: 700, fontSize: 96 * u, color: '#1b1b1b' }}>
            {g.end.wrong}
            <svg style={{ position: 'absolute', left: 0, top: 0, width: '100%', height: '100%', overflow: 'visible' }} viewBox="0 0 100 100" preserveAspectRatio="none">
              <path d={`M -4 55 Q 25 40 50 58 T 104 45`} stroke={RED} strokeWidth={7} fill="none" strokeLinecap="round" pathLength={1} strokeDasharray="1 1" strokeDashoffset={1 - strike} vectorEffect="non-scaling-stroke" />
            </svg>
          </div>
          <div style={{ fontFamily: 'Caveat', fontWeight: 700, fontSize: 92 * u, color: RED, clipPath: `inset(0 ${100 - write * 100}% 0 0)`, marginTop: -10 * u }}>{g.end.right}</div>
        </div>;
      })() : null}
      {satOpacity > 0.5 ? <>
        <div style={{ position: 'absolute', left: 30 * u, bottom: 26 * u, fontFamily: "'Special Elite'", fontSize: 18 * u, color: '#fff', opacity: 0.7, letterSpacing: 1 }}>
          {Math.abs(lat0).toFixed(4)}° {lat0 >= 0 ? 'N' : 'S'}   {Math.abs(lon0).toFixed(4)}° {lon0 >= 0 ? 'E' : 'W'}</div>
        {g.credit ? <div style={{ position: 'absolute', right: 24 * u, bottom: 22 * u, fontFamily: 'Inter', fontSize: 12 * u, color: '#fff', opacity: 0.55, maxWidth: W * 0.5, textAlign: 'right' }}>{g.credit}</div> : null}
      </> : null}
      {/* paper texture over everything (strong on paper, light on satellite), grain and a warm vignette */}
      <AbsoluteFill style={{ pointerEvents: 'none', mixBlendMode: 'multiply', opacity: 0.85 * (1 - satOpacity) + 0.22 * satOpacity,
        backgroundImage: 'radial-gradient(circle at 20% 30%, rgba(120,90,50,0.10) 0 2px, transparent 3px), radial-gradient(circle at 70% 60%, rgba(120,90,50,0.08) 0 1px, transparent 2px), linear-gradient(115deg, rgba(150,120,80,0.10), rgba(255,255,255,0) 40%, rgba(150,120,80,0.12))',
        backgroundSize: '7px 7px, 5px 5px, 100% 100%' }} />
      <AbsoluteFill style={{ pointerEvents: 'none', opacity: 0.07, mixBlendMode: 'overlay', backgroundImage: 'repeating-radial-gradient(circle at 17% 32%, #fff 0 1px, transparent 1px 3px)',
        backgroundPosition: `${(f * 37) % 97}px ${(f * 53) % 89}px` }} />
      <AbsoluteFill style={{ pointerEvents: 'none', background: 'radial-gradient(ellipse at 50% 50%, rgba(0,0,0,0) 55%, rgba(60,30,10,0.45) 100%)' }} />
    </AbsoluteFill>
  );
};
