/** Paletas compartidas por los scripts de texturas (relieve, globo, terreno 3D). */
export type RGB = [number, number, number];
export const hex = (h: string): RGB => [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)];
export const ramp = (stops: [number, string][], v: number): RGB => {
  const s = stops.map(([x, c]) => [x, hex(c)] as const);
  if (v <= s[0][0]) return [...s[0][1]] as RGB;
  for (let i = 1; i < s.length; i++) {
    if (v <= s[i][0]) {
      const t = (v - s[i - 1][0]) / (s[i][0] - s[i - 1][0]);
      return [0, 1, 2].map((k) => s[i - 1][1][k] + (s[i][1][k] - s[i - 1][1][k]) * t) as RGB;
    }
  }
  return [...s[s.length - 1][1]] as RGB;
};

/** Tinte de tierra y mar por tema. Día: muestreado de los fotogramas de referencia; noche: gris azulado. */
export const PALETTES = {
  paper: {
    land: [[0, '#E0D4B9'], [800, '#DBCEB2'], [2000, '#D2C2A2'], [3500, '#C7B28D'], [5000, '#BDA781'], [7000, '#B49F7B']] as [number, string][],
    sea: [[-6000, '#8FA3A9'], [-3000, '#98ABB0'], [-1000, '#A7B9BD'], [-150, '#B8C8CB'], [0, '#C3D1D3']] as [number, string][],
    ice: '#F1EEE6',
    shadeStrength: 0.42,
  },
  night: {
    land: [[0, '#8D9FA8'], [3000, '#8297A2'], [6000, '#9FB0BA'], [8000, '#C9D3D9']] as [number, string][],
    sea: [[-6000, '#1A2D3D'], [-1000, '#22384A'], [0, '#2A4255']] as [number, string][],
    ice: '#D7DEE2',
    shadeStrength: 0.5,
  },
};

/** Sombreado Lambert con luz del noroeste a 45°. dzdx, dzdy en m/m (ya exagerados). */
export const lambert = (dzdx: number, dzdy: number) => {
  const az = (315 * Math.PI) / 180;
  const alt = (45 * Math.PI) / 180;
  const slope = Math.atan(Math.hypot(dzdx, dzdy));
  const aspect = Math.atan2(dzdy, -dzdx);
  return Math.cos(Math.PI / 2 - alt) * Math.cos(slope) + Math.sin(Math.PI / 2 - alt) * Math.sin(slope) * Math.cos(az - aspect);
};
export const FLAT = Math.cos(Math.PI / 4);
