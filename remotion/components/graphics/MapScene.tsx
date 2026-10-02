import type { FC } from 'react';
import { useMemo } from 'react';
import { AbsoluteFill, Easing, Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';
import { geoArea, geoBounds, geoCentroid, geoCircle, geoDistance, geoGraticule10, geoInterpolate, geoMercator, geoOrthographic, geoPath } from 'd3-geo';
import type { GeoPermissibleObjects } from 'd3-geo';
import { feature } from 'topojson-client';
import world from 'world-atlas/countries-50m.json';
import { alpha, condensedFamily, fontFamily, theme } from '../../theme';
import type { MapGraphic } from '../../graphics';
import { GraphicTitle } from './GraphicTitle';

type Country = { type: 'Feature'; properties: { name: string }; geometry: GeoPermissibleObjects };

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const COUNTRIES = (feature(world as any, (world as any).objects.countries) as any).features as Country[];

const W = 1920;
const H = 1080;

const lerp = (a: number, b: number, t: number) => a + (b - a) * t;

/** The country's largest landmass (USA without Alaska/Hawaii, France without its overseas regions). */
const mainland = (c: Country): GeoPermissibleObjects => {
  const g = c.geometry as { type: string; coordinates: unknown[] };
  if (g.type !== 'MultiPolygon') return c.geometry;
  const polygons = g.coordinates.map((coordinates) => ({ type: 'Polygon', coordinates }) as GeoPermissibleObjects);
  return polygons.reduce((a, b) => (geoArea(b) > geoArea(a) ? b : a));
};

/** Bounding box [minLon, minLat, maxLon, maxLat] of a set of lon/lat pairs, at least `pad` degrees wide. */
const box = (coords: [number, number][], pad: number): [number, number, number, number] => {
  const lons = coords.map((c) => c[0]);
  const lats = coords.map((c) => c[1]);
  const cx = (Math.min(...lons) + Math.max(...lons)) / 2;
  const cy = (Math.min(...lats) + Math.max(...lats)) / 2;
  const w = Math.max(Math.max(...lons) - Math.min(...lons), pad);
  const h = Math.max(Math.max(...lats) - Math.min(...lats), pad * 0.6);
  return [cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2];
};

/** Mercator view (scale, centre) that fits a lon/lat box in the frame with margins. `tilted`: the
 * map will be enlarged 1.3x and leant back, so fit a smaller box, a little higher. */
const view = (b: [number, number, number, number], tilted = false) => {
  // corners as points: a polygon ring's winding would decide whether it means the box or the rest of the globe
  const outline = {
    type: 'MultiPoint',
    coordinates: [[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]], [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2]],
  } as GeoPermissibleObjects;
  const extent: [[number, number], [number, number]] = tilted
    ? [[W / 2 - 560, H / 2 - 290], [W / 2 + 560, H / 2 + 170]]
    : [[260, 200], [W - 260, H - 150]];
  const p = geoMercator().fitExtent(extent, outline);
  const centre = p.invert?.([W / 2, H / 2 + 25]) ?? [0, 0];
  return { scale: p.scale(), centre: centre as [number, number] };
};

/** Label boxes next to their pins without overlapping: right of the pin, else left, else lower. */
const labelSpots = (pins: ([number, number] | null)[], texts: string[]) => {
  const placed: { left: number; top: number; width: number }[] = [];
  const BOX_H = 74;
  const hits = (l: number, t: number, w: number) =>
    placed.some((q) => l < q.left + q.width + 12 && q.left < l + w + 12 && Math.abs(q.top - t) < BOX_H);
  return pins.map((xy, i) => {
    if (!xy) return null;
    const BOX_W = 44 + texts[i].length * 22;         // ~22 px per character at 34 px heavy type
    const options = [
      [xy[0] + 22, xy[1] - 62], [xy[0] - 22 - BOX_W, xy[1] - 62], [xy[0] + 22, xy[1] + 14], [xy[0] - 22 - BOX_W, xy[1] + 14],
      [xy[0] + 22, xy[1] - 140], [xy[0] + 22, xy[1] + 90],
    ];
    const [left, top] = options.find(([l, t]) => !hits(l, t, BOX_W)) ?? options[0];
    const spot = {
      left: Math.min(Math.max(left, 20), W - BOX_W - 20),
      top: Math.min(Math.max(top, 170), H - BOX_H - 20),
      width: BOX_W,
    };
    placed.push(spot);
    return spot;
  });
};

/**
 * Map: highlighted countries light up, pins drop on cities with their labels, an optional route is
 * drawn through them, and it can zoom from the country into one city. With `globe`, an orthographic
 * globe turns until the place faces the camera.
 */
export const MapScene: FC<{ graphic: MapGraphic; durationInFrames: number }> = ({ graphic, durationInFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const flat = theme.mapStyle === 'flat' && !graphic.globe;   // top-down flat colours, solid highlight with its name
  const fill = theme.mapHighlight || theme.accent;
  const points = graphic.points ?? [];
  const highlighted = useMemo(
    () => COUNTRIES.filter((c) => (graphic.countries ?? []).some((n) => n.toLowerCase() === c.properties.name.toLowerCase())),
    [graphic.countries],
  );
  const t = (from: number, to: number) =>
    interpolate(frame, [from * durationInFrames, to * durationInFrames], [0, 1], {
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
      easing: Easing.inOut(Easing.cubic),
    });

  // --- projection -----------------------------------------------------------------------------
  let projection;
  let zoomed = 0;
  if (graphic.globe) {
    const target: [number, number] = highlighted.length
      ? (geoCentroid(mainland(highlighted[0])) as [number, number])
      : points.length
        ? [points[0].lon, points[0].lat]
        : [0, 20];
    const turn = t(0, 0.7);
    projection = geoOrthographic()
      .scale(interpolate(turn, [0, 1], [400, 470]))
      .translate([W / 2, H / 2 + 20])
      .rotate([-(target[0] - 140 * (1 - turn)), -lerp(0, target[1], turn)])
      .clipAngle(90);
  } else {
    const all: [number, number][] = points.map((p) => [p.lon, p.lat]);
    if (graphic.route && !flat) {
      // the great-circle arc between cities bows north/south: keep it in the frame
      for (let i = 1; i < points.length; i++) {
        const arc = geoInterpolate([points[i - 1].lon, points[i - 1].lat], [points[i].lon, points[i].lat]);
        for (const f of [0.25, 0.5, 0.75]) all.push(arc(f) as [number, number]);
      }
    }
    for (const c of highlighted) {
      const [[x0, y0], [x1, y1]] = geoBounds(mainland(c));
      all.push([x0, y0], [x1, y1]);
    }
    for (const r of graphic.rings ?? []) {        // the whole circle in the frame
      const p = points[r.point];
      if (!p) continue;
      const deg = r.km / 111.2;
      all.push([p.lon - deg / Math.cos((p.lat * Math.PI) / 180), p.lat - deg], [p.lon + deg / Math.cos((p.lat * Math.PI) / 180), p.lat + deg]);
    }
    const start = view(box(all.length ? all : [[0, 20]], 12), !flat);
    const zoomPoint = graphic.zoom != null ? points[graphic.zoom] : undefined;
    const end = zoomPoint ? view(box([[zoomPoint.lon, zoomPoint.lat]], 3), !flat) : start;
    const z = zoomPoint ? t(0.55, 0.85) : 0;
    const scale = Math.exp(lerp(Math.log(start.scale), Math.log(end.scale), z));
    zoomed = z;
    let centre = start.centre;
    if (zoomPoint && z > 0) {
      // Keep the target city on a straight path from where it is on the overview to the middle
      // of the frame while the scale grows, so it never leaves the picture mid-zoom.
      const mid: [number, number] = [W / 2, H / 2 + 25];
      const merc = (lon: number, lat: number): [number, number] => [
        (lon * Math.PI) / 180,
        Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360)),
      ];
      const [tx, ty] = merc(zoomPoint.lon, zoomPoint.lat);
      const [cx, cy] = merc(start.centre[0], start.centre[1]);
      const p0: [number, number] = [mid[0] + start.scale * (tx - cx), mid[1] - start.scale * (ty - cy)];
      const p: [number, number] = [lerp(p0[0], mid[0], z), lerp(p0[1], mid[1], z)];
      const x = tx - (p[0] - mid[0]) / scale;
      const y = ty + (p[1] - mid[1]) / scale;
      centre = [(x * 180) / Math.PI, (2 * Math.atan(Math.exp(y)) - Math.PI / 2) * (180 / Math.PI)];
    }
    projection = geoMercator()
      .scale(scale)
      .center(centre)
      .translate([W / 2, H / 2 + 25]);
  }
  const path = geoPath(projection);

  // --- timing ----------------------------------------------------------------------------------
  const light = t(0.05, 0.25);
  const pinAt = (i: number) => 0.15 + (0.45 * i) / Math.max(1, points.length);
  const route = graphic.route && points.length > 1 ? t(0.2, 0.6) : 0;
  // flat maps: each leg a clean curve on screen (a great circle over the pole looks wrong on a flat map)
  const screenPts = points.map((p) => projection([p.lon, p.lat]) as [number, number] | null);
  const bend = (a: [number, number], b: [number, number]): [number, number] => {
    const dx = b[0] - a[0];
    const dy = b[1] - a[1];
    const len = Math.hypot(dx, dy) || 1;
    const lift = Math.min(0.22 * len, 260);
    const nx = dy / len;
    const ny = -dx / len;
    const up = ny <= 0 ? 1 : -1;                          // always bow upwards on screen
    return [(a[0] + b[0]) / 2 + nx * lift * up, (a[1] + b[1]) / 2 + ny * lift * up];
  };
  const quad = (a: [number, number], c: [number, number], b: [number, number], f: number): [number, number] => [
    (1 - f) * (1 - f) * a[0] + 2 * (1 - f) * f * c[0] + f * f * b[0],
    (1 - f) * (1 - f) * a[1] + 2 * (1 - f) * f * c[1] + f * f * b[1],
  ];
  const flatLegs = flat && screenPts.every(Boolean)
    ? screenPts.slice(1).map((b, i) => ({ a: screenPts[i] as [number, number], b: b as [number, number], c: bend(screenPts[i] as [number, number], b as [number, number]) }))
    : [];
  const routePath =
    graphic.route && points.length > 1
      ? flat && flatLegs.length
        ? flatLegs.map((l, i) => `${i ? '' : `M${l.a[0]},${l.a[1]} `}Q${l.c[0]},${l.c[1]} ${l.b[0]},${l.b[1]}`).join(' ')
        : path({ type: 'LineString', coordinates: points.map((p) => [p.lon, p.lat]) } as GeoPermissibleObjects)
      : null;

  // --- camera: flat maps lean back in perspective (the SVG is tilted; labels and the plane are
  // placed on screen through the same transform so they stay upright and on their pins)
  const tiltDeg = graphic.globe || flat ? 0 : interpolate(frame, [0, durationInFrames], [30, 22]);
  const S = graphic.globe || flat ? 1 : 1.3;            // overscan so the tilted map fills the frame
  const P = 1500;
  const tilt = (xy: [number, number]): [number, number] => {
    if (!tiltDeg) return xy;
    const a = (tiltDeg * Math.PI) / 180;
    const X = (xy[0] - W / 2) * S;
    const Y = (xy[1] - H / 2) * S;
    const z = Y * Math.sin(a);
    const k = P / (P - z);
    return [W / 2 + X * k, H / 2 + Y * Math.cos(a) * k];
  };

  // --- the plane travelling on the route (ahead of the line as it is drawn)
  let plane: { xy: [number, number]; angle: number } | null = null;
  if (graphic.route && points.length > 1 && route > 0 && route < 1) {
    const legs = points.slice(1).map((p, i) => geoDistance([points[i].lon, points[i].lat], [p.lon, p.lat]));
    const at = (progress: number): [number, number] | null => {
      let left = progress * legs.reduce((s, x) => s + x, 0);
      for (let i = 0; i < legs.length; i++) {
        if (left <= legs[i] || i === legs.length - 1) {
          const f = legs[i] ? Math.min(1, left / legs[i]) : 1;
          const g = geoInterpolate([points[i].lon, points[i].lat], [points[i + 1].lon, points[i + 1].lat])(f);
          const xy = projection(g as [number, number]);
          return xy ? tilt(xy as [number, number]) : null;
        }
        left -= legs[i];
      }
      return null;
    };
    const flatAt = (progress: number): [number, number] | null => {
      const k = Math.min(flatLegs.length - 1, Math.floor(progress * flatLegs.length));
      const l = flatLegs[k];
      return l ? quad(l.a, l.c, l.b, progress * flatLegs.length - k) : null;
    };
    const pick = flat && flatLegs.length ? flatAt : at;
    const here = pick(route);
    const before = pick(Math.max(0, route - 0.02));
    if (here && before) {
      plane = { xy: here, angle: (Math.atan2(here[1] - before[1], here[0] - before[0]) * 180) / Math.PI };
    }
  }

  return (
    <AbsoluteFill style={{ backgroundColor: theme.ocean }}>
      <svg
        width={W}
        height={H}
        viewBox={`0 0 ${W} ${H}`}
        style={tiltDeg ? { transform: `perspective(${P}px) rotateX(${tiltDeg}deg) scale(${S})`, transformOrigin: '50% 50%' } : undefined}
      >
        <defs>
          <linearGradient id="landShade" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={alpha('#ffffff', 0.10)} />
            <stop offset="100%" stopColor={alpha('#000000', 0.25)} />
          </linearGradient>
          <filter id="relief" x="-10%" y="-10%" width="120%" height="130%">
            <feDropShadow dx="0" dy="5" stdDeviation="4" floodColor="#000" floodOpacity="0.7" />
          </filter>
          <radialGradient id="ocean" cx="50%" cy="45%" r="60%">
            <stop offset="0%" stopColor={theme.land} />
            <stop offset="100%" stopColor={theme.ocean} />
          </radialGradient>
          <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="6" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        {graphic.globe ? (
          <>
            <path d={path({ type: 'Sphere' } as GeoPermissibleObjects) ?? ''} fill="url(#ocean)" stroke="#2b3140" strokeWidth={2} />
            <path d={path(geoGraticule10()) ?? ''} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth={1} />
          </>
        ) : (
          <rect width={W} height={H} fill={flat ? theme.ocean : 'url(#ocean)'} />
        )}
        <g filter={flat ? undefined : 'url(#relief)'}>
          {COUNTRIES.map((c, i) => (
            <path key={i} d={path(c as never) ?? ''} fill={theme.land} stroke={flat ? alpha('#ffffff', 0.35) : theme.border}
              strokeWidth={flat ? 1 : 0.8} />
          ))}
        </g>
        {/* soft relief: light from above over the land */}
        {flat ? null : (
          <g opacity={0.9}>
            {COUNTRIES.map((c, i) => (
              <path key={`s${i}`} d={path(c as never) ?? ''} fill="url(#landShade)" stroke="none" />
            ))}
          </g>
        )}
        {/* flat: the highlighted area filled solid, as the explainers do */}
        {flat
          ? highlighted.map((c, i) => (
              <path key={`f${i}`} d={path(c as never) ?? ''} fill={fill} fillOpacity={0.95 * light}
                stroke="#ffffff" strokeOpacity={light} strokeWidth={2} />
            ))
          : null}
        {/* highlighted countries raised: a few darker copies below give them thickness */}
        {flat ? null : [8, 5, 2].map((dy) =>
          highlighted.map((c, i) => (
            <path
              key={`x${dy}-${i}`}
              d={path(c as never) ?? ''}
              transform={`translate(0,${dy * light})`}
              fill={alpha(theme.accent, 0.08 * light * (1 - 0.75 * zoomed))}
              stroke="none"
            />
          )),
        )}
        {flat ? null : highlighted.map((c, i) => (
          <path
            key={`h${i}`}
            d={path(c as never) ?? ''}
            fill={theme.accent}
            fillOpacity={0.24 * light * (1 - 0.75 * zoomed)}
            stroke={theme.accent}
            strokeOpacity={light}
            strokeWidth={2.5}
            filter="url(#glow)"
          />
        ))}
        {(graphic.rings ?? []).map((r, i) => {
          const p = points[r.point];
          if (!p) return null;
          // each circle grows from its airport, one after another, then stays (a true geodesic circle)
          const grow = t(0.12 + 0.12 * i, 0.32 + 0.12 * i);
          if (grow <= 0) return null;
          const ring = geoCircle().center([p.lon, p.lat]).radius((r.km / 111.2) * grow).precision(2)();
          return (
            <path key={`ring${i}`} d={path(ring as GeoPermissibleObjects) ?? ''} fill={alpha(flat ? '#ffffff' : theme.accent, 0.07)}
              stroke={flat ? '#ffffff' : theme.accent} strokeOpacity={0.85} strokeWidth={2.5} />
          );
        })}
        {routePath ? (
          <path
            d={routePath}
            fill="none"
            stroke={flat ? '#ffffff' : theme.accent}
            strokeWidth={5}
            strokeLinecap="round"
            strokeDasharray="1"
            strokeDashoffset={1 - route}
            pathLength={1}
            filter={flat ? undefined : 'url(#glow)'}
          />
        ) : null}
        {points.map((p, i) => {
          const xy = projection([p.lon, p.lat]);
          if (!xy) return null;
          const pop = spring({ frame: frame - pinAt(i) * durationInFrames, fps, config: { damping: 12, stiffness: 160 } });
          const pulse = (frame / fps + i * 0.3) % 1.4;
          return (
            <g key={`p${i}`} transform={`translate(${xy[0]},${xy[1]})`} opacity={Math.min(1, pop * 1.5)}>
              <circle r={10 + pulse * 26} fill="none" stroke={theme.accent} strokeOpacity={Math.max(0, 0.7 - pulse / 2)} strokeWidth={3} />
              <circle r={11 * pop} fill={theme.accent} stroke="#000" strokeWidth={3} />
            </g>
          );
        })}
      </svg>
      {labelSpots(
        points.map((p) => {
          const raw = projection([p.lon, p.lat]);
          const xy = raw ? tilt(raw as [number, number]) : null;
          return xy && xy[0] > 0 && xy[0] < W && xy[1] > 0 && xy[1] < H ? xy : null;   // off screen: no label
        }),
        points.map((p) => (p.note && p.note.length * 0.7 > p.name.length ? p.note.slice(0, Math.ceil(p.note.length * 0.7)) : p.name)),
      ).map((spot, i) => {
        const p = points[i];
        if (!spot) return null;
        const show = interpolate(frame, [pinAt(i) * durationInFrames + 4, pinAt(i) * durationInFrames + 12], [0, 1], {
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
        });
        return (
          <div
            key={`l${i}`}
            style={{
              position: 'absolute',
              left: spot.left,
              top: spot.top,
              opacity: show,
              transform: `translateY(${(1 - show) * 10}px)`,
              backgroundColor: 'rgba(0,0,0,0.78)',
              borderLeft: `6px solid ${theme.accent}`,
              padding: '8px 16px',
              fontFamily,
              color: theme.text,
              whiteSpace: 'nowrap',
            }}
          >
            <div style={{ fontWeight: 800, fontSize: 34, lineHeight: 1.1 }}>{p.name.toUpperCase()}</div>
            {p.note ? <div style={{ fontWeight: 600, fontSize: 24, color: theme.accent }}>{p.note}</div> : null}
          </div>
        );
      })}
      {plane ? (
        <svg
          width={64}
          height={64}
          viewBox="-32 -32 64 64"
          style={{ position: 'absolute', left: plane.xy[0] - 32, top: plane.xy[1] - 32, overflow: 'visible' }}
        >
          <g transform={`rotate(${plane.angle + 90})`} filter="drop-shadow(0 6px 6px rgba(0,0,0,0.6))">
            {/* a plane seen from above, nose up before the rotation */}
            <path
              d="M0,-26 C3,-26 4,-20 4,-14 L4,-6 L26,6 L26,11 L4,4 L3,18 L10,23 L10,27 L0,24 L-10,27 L-10,23 L-3,18 L-4,4 L-26,11 L-26,6 L-4,-6 L-4,-14 C-4,-20 -3,-26 0,-26 Z"
              fill={theme.text}
              stroke={theme.accent}
              strokeWidth={2}
            />
          </g>
        </svg>
      ) : null}
      {(graphic.rings ?? []).map((r, i) => {
        const p = points[r.point];
        if (!p || !r.label) return null;
        const show = t(0.3 + 0.12 * i, 0.38 + 0.12 * i);
        const raw = projection([p.lon, Math.min(85, p.lat + r.km / 111.2)]);   // the top of the circle
        const xy = raw ? tilt(raw as [number, number]) : null;
        if (!xy || show <= 0) return null;
        return (
          <div key={`rl${i}`} style={{
            position: 'absolute', left: xy[0], top: Math.max(40, xy[1]), transform: 'translate(-50%, -120%)', opacity: show,
            fontFamily: condensedFamily, fontWeight: 700, fontSize: 34, color: '#ffffff', backgroundColor: 'rgba(0,0,0,0.55)',
            padding: '2px 12px', borderRadius: 4, whiteSpace: 'nowrap',
          }}>
            {r.label}
          </div>
        );
      })}
      {graphic.regionLabel && highlighted.length
        ? (() => {
            const raw = projection(geoCentroid(mainland(highlighted[0])) as [number, number]);
            const xy = raw ? tilt(raw as [number, number]) : null;
            if (!xy || xy[0] < 0 || xy[0] > W || xy[1] < 0 || xy[1] > H) return null;
            return (
              <div style={{
                position: 'absolute', left: xy[0], top: xy[1] + 70, transform: 'translate(-50%, -50%)', opacity: light,
                fontFamily: condensedFamily, fontWeight: 700, fontSize: 44, letterSpacing: '0.04em', color: '#ffffff',
                textTransform: 'uppercase', whiteSpace: 'nowrap', textShadow: '0 3px 12px rgba(0,0,0,0.55)',
              }}>
                {graphic.regionLabel}
              </div>
            );
          })()
        : null}
      {points.map((p, i) => {
        if (!p.logoMedia) return null;
        const raw = projection([p.lon, p.lat]);
        const xy = raw ? tilt(raw as [number, number]) : null;
        if (!xy) return null;
        const pop = spring({ frame: frame - pinAt(i) * durationInFrames - 6, fps, config: { damping: 11, stiffness: 170 } });
        return (
          <div key={`logo${i}`} style={{
            position: 'absolute', left: xy[0] - 70, top: xy[1] - 170, width: 140, height: 140, borderRadius: 70,
            backgroundColor: '#ffffff', boxShadow: '0 10px 30px rgba(0,0,0,0.45)', border: `5px solid ${fill}`,
            display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden',
            transform: `scale(${pop})`, transformOrigin: '50% 100%',
          }}>
            <Img src={staticFile(p.logoMedia.src)} style={{ width: '78%', height: '78%', objectFit: 'contain' }} />
          </div>
        );
      })}
      {graphic.date
        ? (() => {
            // the date first big over the map, then up to the corner as the story starts moving
            const settle = interpolate(frame, [0.16 * durationInFrames, 0.26 * durationInFrames], [0, 1], {
              extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.inOut(Easing.cubic) });
            const appear = interpolate(frame, [0, 8], [0, 1], { extrapolateRight: 'clamp' });
            return (
              <div style={{
                position: 'absolute', left: lerp(110, 70, settle), top: lerp(H / 2 - 90, graphic.title ? 170 : 60, settle),
                opacity: appear, fontFamily: condensedFamily, fontWeight: 700, fontSize: lerp(120, 46, settle),
                color: '#ffffff', textShadow: '0 4px 18px rgba(0,0,0,0.55)', whiteSpace: 'nowrap',
                transform: `translateY(${(1 - appear) * 24}px)`,
              }}>
                {graphic.date}
              </div>
            );
          })()
        : null}
      {graphic.title ? <GraphicTitle text={graphic.title} /> : null}
    </AbsoluteFill>
  );
};
