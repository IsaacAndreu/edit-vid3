// The Iberian power grid, simplified but with real physics (remotion/sim/worlds/apagon.tsx draws it):
//  - the map: the peninsula's coast, its big cities (load) and power plants (nuclear, combined cycle, hydro, solar,
//    wind), lines between neighbours and the interconnections with France and Morocco;
//  - how power flows: a DC power flow (Kirchhoff: the current shares itself over every path at once, by each line's
//    impedance) — cut a line and every other line's flow changes in the same instant;
//  - the cascade (Motter & Lai, 2002, on lines): each line can carry (1 + margin) × its normal flow; one that goes over
//    trips, the flows are worked out again, and so on; an island left with less generation than load goes dark;
//  - frequency: one swing equation (inertia H), the governors' response, plants that trip below 48.8 Hz and the
//    automatic load shedding (relays that cut districts below 49 Hz);
//  - a sandpile (Bak, Tang & Wiesenfeld, 1987): grains one by one, avalanches of every size;
//  - the black start: hydro plants and the interconnections light islands that grow until they meet.
import {mulberry} from './world';

export type Kind = 'city' | 'nuclear' | 'cc' | 'hidro' | 'solar' | 'eolica' | 'link';
export type Node = {name: string; kind: Kind; x: number; y: number; size: number};
type Spec = {
  box: [number, number, number, number];               // lon min, lon max, lat min, lat max (what fills the screen)
  coast: [number, number][];                            // the land, as one outline
  borders?: [number, number][][];                       // inner borders (dashed)
  lakes?: [number, number][][];                         // water inside the land
  names: [string, number, number, number][];            // big faint names on the land: word key, lon, lat, size
  nodes: [string, Kind, number, number, number][];      // name (a word key for links), kind, lon, lat, size
  people: number;                                        // millions
  first?: [string, string];                              // the first fault (else: found)
};

// --- the countries -----------------------------------------------------------------------------------------------------------
const SPECS: Record<string, Spec> = {
  iberia: {
    box: [-9.8, 3.5, 35.4, 43.95],
    coast: [[-8.9, 43.2], [-8.4, 43.4], [-7.7, 43.75], [-7.0, 43.55], [-5.8, 43.6], [-4.5, 43.45], [-3.8, 43.47], [-3.0, 43.35],
      [-1.8, 43.38], [-1.4, 43.1], [-0.7, 42.85], [0.7, 42.85], [1.7, 42.5], [2.6, 42.4], [3.2, 42.35], [3.2, 41.9], [2.2, 41.4],
      [1.0, 41.05], [0.8, 40.7], [0.0, 40.0], [-0.3, 39.5], [0.2, 38.75], [-0.5, 38.3], [-0.75, 37.6], [-1.6, 37.3], [-2.0, 36.75],
      [-3.0, 36.72], [-4.4, 36.7], [-5.3, 36.15], [-5.6, 36.0], [-6.0, 36.3], [-6.4, 36.8], [-7.0, 37.2], [-7.4, 37.17], [-8.0, 37.0],
      [-8.9, 37.0], [-8.8, 37.9], [-8.8, 38.5], [-9.5, 38.75], [-9.3, 39.4], [-8.9, 40.2], [-8.65, 41.15], [-8.85, 41.9], [-8.9, 42.5],
      [-9.3, 42.9]],
    borders: [[[-8.87, 41.87], [-8.2, 42.1], [-6.6, 41.95], [-6.2, 41.6], [-6.9, 41.0], [-6.8, 40.3], [-7.0, 39.67], [-7.5, 39.6],
      [-7.0, 39.0], [-7.3, 38.4], [-7.0, 38.0], [-7.5, 37.5], [-7.4, 37.17]]],
    names: [['spain', -4.2, 40.0, 120], ['portugal', -8.0, 39.6, 44]],
    nodes: [
      ['Madrid', 'city', -3.7, 40.42, 6.7], ['Barcelona', 'city', 2.17, 41.39, 5.6], ['Valencia', 'city', -0.38, 39.47, 2.5],
      ['Sevilla', 'city', -5.98, 37.39, 1.9], ['Lisboa', 'city', -9.14, 38.72, 2.9], ['Porto', 'city', -8.61, 41.15, 1.7],
      ['Bilbao', 'city', -2.93, 43.26, 1.0], ['Zaragoza', 'city', -0.88, 41.65, 0.9], ['Málaga', 'city', -4.42, 36.72, 1.0],
      ['Murcia', 'city', -1.13, 37.99, 0.9], ['Vigo', 'city', -8.72, 42.24, 0.9], ['Valladolid', 'city', -4.72, 41.65, 0.6],
      ['Oviedo', 'city', -5.85, 43.36, 0.6], ['Alicante', 'city', -0.49, 38.35, 0.8], ['Córdoba', 'city', -4.78, 37.89, 0.5],
      ['Badajoz', 'city', -6.97, 38.88, 0.4], ['Pamplona', 'city', -1.64, 42.81, 0.4], ['Granada', 'city', -3.6, 37.18, 0.6],
      ['Almaraz', 'nuclear', -5.7, 39.81, 2.0], ['Ascó', 'nuclear', 0.57, 41.2, 2.0], ['Cofrentes', 'nuclear', -1.06, 39.23, 1.1],
      ['Trillo', 'nuclear', -2.6, 40.7, 1.0], ['Sagunto', 'cc', -0.25, 39.65, 1.2], ['Algeciras', 'cc', -5.4, 36.25, 1.2],
      ['Pego', 'cc', -8.2, 39.45, 1.0], ['Aldeadávila', 'hidro', -6.68, 41.2, 1.2], ['Alto Lindoso', 'hidro', -8.2, 41.85, 0.7],
      ['Belesar', 'hidro', -7.7, 42.6, 0.6], ['Extremadura', 'solar', -6.3, 38.95, 2.2], ['Andalucía', 'solar', -5.3, 37.6, 2.0],
      ['La Mancha', 'solar', -3.2, 39.1, 1.8], ['Alentejo', 'solar', -7.9, 38.1, 1.0], ['Galicia', 'eolica', -7.9, 43.1, 1.0],
      ['Aragón', 'eolica', -1.4, 41.3, 1.2], ['Navarra', 'eolica', -2.1, 42.4, 0.7], ['Castilla', 'eolica', -4.2, 42.2, 1.1],
      ['france', 'link', -1.2, 43.85, 1.0], ['france', 'link', 2.7, 42.95, 1.0], ['morocco', 'link', -5.75, 35.55, 0.6]],
    people: 58,
    first: ['Córdoba', 'Andalucía'],
  },
  alemania: {
    box: [5.6, 15.3, 47.1, 55.2],
    coast: [[7.0, 53.3], [8.0, 53.65], [8.6, 53.9], [8.9, 54.4], [8.6, 54.9], [9.4, 54.8], [10.0, 54.6], [10.9, 54.0], [11.5, 54.1],
      [12.3, 54.4], [13.4, 54.6], [14.2, 53.9], [14.4, 53.3], [14.6, 52.5], [14.7, 51.6], [15.0, 51.1], [14.3, 50.9], [12.9, 50.4],
      [12.1, 50.3], [12.5, 49.7], [13.8, 48.8], [13.0, 48.3], [12.9, 47.7], [13.0, 47.5], [12.2, 47.6], [11.0, 47.4], [10.2, 47.3],
      [9.6, 47.5], [8.6, 47.7], [7.6, 47.6], [7.5, 48.3], [8.2, 49.0], [6.4, 49.2], [6.4, 49.5], [6.1, 50.1], [6.0, 50.8], [5.9, 51.0],
      [6.2, 51.8], [6.8, 52.0], [7.0, 52.6], [7.2, 53.2]],
    names: [['germany', 10.4, 51.0, 120]],
    nodes: [
      ['Berlin', 'city', 13.4, 52.52, 3.7], ['Hamburg', 'city', 10.0, 53.55, 1.9], ['München', 'city', 11.58, 48.14, 1.5],
      ['Köln', 'city', 6.96, 50.94, 1.1], ['Frankfurt', 'city', 8.68, 50.11, 0.8], ['Stuttgart', 'city', 9.18, 48.78, 0.8],
      ['Düsseldorf', 'city', 6.78, 51.23, 0.6], ['Ruhrgebiet', 'city', 7.47, 51.51, 2.2], ['Leipzig', 'city', 12.37, 51.34, 0.6],
      ['Dresden', 'city', 13.74, 51.05, 0.55], ['Hannover', 'city', 9.73, 52.37, 0.55], ['Nürnberg', 'city', 11.08, 49.45, 0.5],
      ['Bremen', 'city', 8.8, 53.08, 0.55], ['Kiel', 'city', 10.13, 54.32, 0.3], ['Rostock', 'city', 12.1, 54.09, 0.3],
      ['Lausitz', 'cc', 14.3, 51.5, 1.8], ['Rheinland', 'cc', 6.5, 50.95, 1.8], ['Mannheim', 'cc', 8.47, 49.49, 1.0],
      ['Emsland', 'nuclear', 7.32, 52.47, 1.2], ['Alpen', 'hidro', 11.2, 47.6, 0.8], ['Inn', 'hidro', 12.9, 48.2, 0.5],
      ['Nordsee', 'eolica', 8.3, 54.25, 1.8], ['Schleswig', 'eolica', 9.6, 54.35, 1.2], ['Mecklenburg', 'eolica', 12.5, 53.6, 1.2],
      ['Niedersachsen', 'eolica', 9.5, 52.85, 1.2], ['Brandenburg', 'solar', 13.7, 52.05, 1.0], ['Bayern', 'solar', 10.8, 48.7, 1.6],
      ['Thüringen', 'eolica', 11.0, 50.9, 0.8],
      ['france', 'link', 7.25, 48.55, 1.0], ['austria', 'link', 13.0, 47.05, 1.0], ['poland', 'link', 15.4, 52.2, 1.0],
      ['netherlands', 'link', 5.65, 52.0, 1.0], ['denmark', 'link', 9.3, 55.15, 0.8]],
    people: 84,
  },
  brasil: {
    box: [-74.5, -34.0, -34.2, 5.6],
    coast: [[-60, 5.2], [-51.6, 4.3], [-50, 1.8], [-48.5, -1.0], [-44.3, -2.5], [-41, -2.9], [-38.5, -3.7], [-35.2, -5.5], [-34.8, -7.1],
      [-35, -9], [-37, -11], [-38.5, -13], [-39, -17.5], [-40.3, -20.3], [-41, -22], [-43.2, -22.9], [-45, -23.6], [-46.3, -24],
      [-48.5, -26], [-48.6, -28.5], [-50.2, -30.5], [-52.1, -32.2], [-53.4, -33.7], [-53.8, -32.5], [-55.8, -30.9], [-57.6, -30.2],
      [-56, -28], [-54.6, -25.6], [-54.3, -24.0], [-55.6, -22.5], [-57.9, -22.0], [-58.1, -19.8], [-57.6, -17.5], [-60.1, -16.3],
      [-60.4, -13.5], [-62.2, -13.1], [-65.3, -11.0], [-69.5, -11.0], [-70.6, -9.5], [-72.9, -9.2], [-73.9, -7.4], [-72.9, -5.1],
      [-70.0, -4.3], [-69.4, -1.3], [-69.9, 1.0], [-67.0, 1.2], [-64.0, 2.2], [-63.4, 3.9], [-61, 4.5]],
    names: [['brazil', -52.0, -11.0, 130]],
    nodes: [
      ['São Paulo', 'city', -46.63, -23.55, 6.0], ['Rio de Janeiro', 'city', -43.2, -22.9, 3.4], ['Belo Horizonte', 'city', -43.94, -19.92, 1.6],
      ['Brasília', 'city', -47.88, -15.79, 1.6], ['Salvador', 'city', -38.5, -12.97, 1.5], ['Fortaleza', 'city', -38.5, -3.73, 1.4],
      ['Recife', 'city', -34.9, -8.05, 1.1], ['Curitiba', 'city', -49.27, -25.43, 1.1], ['Porto Alegre', 'city', -51.23, -30.03, 1.0],
      ['Manaus', 'city', -60.02, -3.1, 1.2], ['Belém', 'city', -48.5, -1.45, 0.9], ['Goiânia', 'city', -49.25, -16.68, 0.9],
      ['Campinas', 'city', -47.06, -22.9, 0.9], ['Campo Grande', 'city', -54.6, -20.45, 0.5], ['Cuiabá', 'city', -56.1, -15.6, 0.5],
      ['Itaipu', 'hidro', -54.55, -25.2, 3.0], ['Belo Monte', 'hidro', -51.8, -3.3, 2.0], ['Tucuruí', 'hidro', -49.7, -3.8, 1.8],
      ['Furnas', 'hidro', -46.3, -20.7, 1.0], ['Sobradinho', 'hidro', -40.8, -9.4, 1.0], ['Jirau', 'hidro', -64.0, -9.2, 1.4],
      ['Ilha Solteira', 'hidro', -51.35, -20.4, 1.2], ['Angra', 'nuclear', -44.45, -23.0, 1.2], ['Nordeste', 'eolica', -37.3, -5.6, 1.8],
      ['Bahia', 'eolica', -41.0, -11.0, 1.3], ['Minas', 'solar', -44.5, -16.5, 1.1], ['Rio Grande', 'eolica', -52.5, -31.5, 0.6],
      ['Termelétricas', 'cc', -47.5, -22.6, 1.0],
      ['paraguay', 'link', -55.6, -25.9, 1.0], ['argentina', 'link', -57.0, -29.0, 0.6], ['uruguay', 'link', -54.6, -33.6, 0.5],
      ['venezuela', 'link', -61.0, 5.4, 0.4]],
    people: 203,
  },
  eeuu: {
    box: [-84.6, -69.2, 38.2, 46.7],
    coast: [[-84.5, 46.6], [-68.5, 46.6], [-67.0, 44.8], [-70.2, 43.6], [-70.8, 42.6], [-70.0, 41.7], [-71.4, 41.4], [-73.7, 40.9],
      [-74.0, 40.5], [-74.2, 39.5], [-74.9, 38.9], [-75.5, 39.3], [-75.1, 38.4], [-84.5, 38.3]],
    lakes: [
      [[-83.4, 41.7], [-82.5, 41.4], [-81.0, 41.8], [-79.8, 42.1], [-78.9, 42.9], [-80.0, 42.6], [-81.6, 42.6], [-83.1, 42.1]],
      [[-79.8, 43.3], [-79.0, 43.25], [-77.0, 43.3], [-76.2, 43.5], [-76.4, 44.1], [-77.5, 44.0], [-79.4, 43.65]],
      [[-84.5, 45.9], [-83.5, 46.0], [-81.7, 45.9], [-80.3, 45.4], [-79.7, 44.8], [-80.0, 44.5], [-81.3, 44.9], [-81.7, 43.6],
        [-82.4, 43.0], [-82.5, 43.7], [-83.4, 44.0], [-84.5, 45.5]]],
    borders: [[[-84.5, 46.4], [-83.6, 46.1], [-82.4, 45.0], [-82.4, 43.0], [-83.1, 42.1]], [[-78.9, 42.9], [-79.0, 43.25]],
      [[-76.2, 43.5], [-75.0, 45.0], [-71.5, 45.0], [-70.0, 46.6]]],
    names: [['canada', -78.0, 45.9, 70], ['usa', -78.5, 40.8, 110]],
    nodes: [
      ['New York', 'city', -74.0, 40.7, 6.0], ['Detroit', 'city', -83.05, 42.4, 1.8], ['Cleveland', 'city', -81.7, 41.45, 1.2],
      ['Toronto', 'city', -79.4, 43.75, 2.8], ['Ottawa', 'city', -75.7, 45.4, 0.9], ['Boston', 'city', -71.06, 42.36, 2.0],
      ['Philadelphia', 'city', -75.2, 39.95, 2.6], ['Pittsburgh', 'city', -80.0, 40.44, 1.1], ['Buffalo', 'city', -78.8, 42.85, 0.7],
      ['Albany', 'city', -73.8, 42.65, 0.5], ['Columbus', 'city', -83.0, 39.96, 1.0], ['Montréal', 'city', -73.57, 45.5, 1.8],
      ['Toledo', 'city', -83.55, 41.6, 0.5], ['Rochester', 'city', -77.6, 43.1, 0.5], ['Hartford', 'city', -72.7, 41.76, 0.6],
      ['Indian Point', 'nuclear', -73.95, 41.27, 1.2], ['Perry', 'nuclear', -81.15, 41.75, 1.0], ['Pickering', 'nuclear', -79.0, 43.85, 1.2],
      ['Niagara', 'hidro', -79.05, 43.05, 1.8], ['St. Lawrence', 'hidro', -74.8, 45.0, 1.0], ['Ohio Valley', 'cc', -81.0, 40.0, 1.8],
      ['Pennsylvania', 'cc', -77.6, 40.4, 1.6], ['New Jersey', 'cc', -74.6, 40.1, 1.0], ['Adirondack', 'eolica', -75.6, 43.8, 0.6],
      ['Michigan', 'cc', -84.0, 43.0, 1.0], ['Vermont', 'hidro', -72.6, 44.2, 0.5],
      ['quebec', 'link', -72.5, 46.45, 1.0], ['pjm', 'link', -77.8, 38.5, 1.0]],
    people: 55,
  },
};

export const COUNTRIES = Object.keys(SPECS);
/** The country of a video: given, else by its language (a German dub on Germany, a Brazilian one on Brazil…). */
export const countryOf = (asked: string | undefined, lang: string | undefined) =>
  asked && SPECS[asked] ? asked : ({es: 'iberia', de: 'alemania', pt: 'brasil', en: 'eeuu'} as Record<string, string>)[String(lang || 'es').slice(0, 2)] ?? 'iberia';

export type Wave = {lines: number[]; dark: boolean[]; flow: number[]};
export type Cascade = {waves: Wave[]};
export type Restore = {lit: Uint8Array[]; merge: number[]; fallback: number[]};
export type Grid = {
  key: string; nodes: Node[]; edges: [number, number][]; coast: string; borders: string[]; lakes: string[];
  names: {word: string; x: number; y: number; size: number}[]; people: number; X: (lon: number) => number; Y: (lat: number) => number;
  links: number[]; cities: number[]; plants: number[]; injections: number[]; base: {flow: number[]; dark: boolean[]};
  first: number[]; region: number[]; regionCut: number[]; withLink: number[];
  flows: (on: boolean[], inj?: number[]) => {flow: number[]; dark: boolean[]};
  cascade: (margin: number, first?: number[], split?: number[], inj?: number[], safe?: number[]) => Cascade;
  darkShare: (dark: boolean[]) => number;
  blackStart: (rush: boolean) => Restore;
};

const GRIDS = new Map<string, Grid>();

export const gridOf = (key: string): Grid => {
  if (GRIDS.has(key)) return GRIDS.get(key)!;
  const spec = SPECS[key] ?? SPECS.iberia;
  const [lo0, lo1, la0, la1] = spec.box;
  const cosLat = Math.cos((((la0 + la1) / 2) * Math.PI) / 180);
  const k = Math.min(1500 / ((lo1 - lo0) * cosLat), 960 / (la1 - la0));          // pixels per degree of latitude
  const X = (lon: number) => 960 + (lon - (lo0 + lo1) / 2) * k * cosLat;
  const Y = (lat: number) => 540 - (lat - (la0 + la1) / 2) * k;
  const path = (pts: [number, number][], close: boolean) => pts.map(([lo, la], i) => `${i ? 'L' : 'M'}${X(lo).toFixed(1)},${Y(la).toFixed(1)}`).join(' ') + (close ? ' Z' : '');
  const nodes: Node[] = spec.nodes.map(([name, kind, lon, lat, size]) => ({name, kind, x: X(lon), y: Y(lat), size}));
  const links = nodes.map((n, i) => (n.kind === 'link' ? i : -1)).filter((i) => i >= 0);
  const cities = nodes.map((n, i) => (n.kind === 'city' ? i : -1)).filter((i) => i >= 0);
  const plants = nodes.map((n, i) => (n.kind !== 'city' && n.kind !== 'link' ? i : -1)).filter((i) => i >= 0);
  const dist = (a: number, b: number) => Math.hypot(nodes[a].x - nodes[b].x, nodes[a].y - nodes[b].y);
  const near = (i: number, n: number) => nodes.map((_, j) => j).filter((j) => j !== i && nodes[j].kind !== 'link')
    .sort((a, b) => dist(i, a) - dist(i, b)).slice(0, n);
  const edges: [number, number][] = (() => {
    const set = new Set<string>();
    const add = (a: number, b: number) => set.add(a < b ? `${a}-${b}` : `${b}-${a}`);
    nodes.forEach((n, i) => { if (n.kind !== 'link') near(i, 4).forEach((j) => add(i, j)); });
    links.forEach((i) => near(i, 1).forEach((j) => add(i, j)));
    for (;;) {                                         // one grid: join any separate piece by its shortest line
      const list = [...set].map((e) => e.split('-').map(Number));
      const seen = new Set<number>([0]);
      const stack = [0];
      while (stack.length) {
        const v = stack.pop()!;
        for (const [a, b] of list) {
          const w = a === v ? b : b === v ? a : -1;
          if (w >= 0 && !seen.has(w)) { seen.add(w); stack.push(w); }
        }
      }
      if (seen.size === nodes.length) break;
      let best: [number, number] = [0, 0];
      let d = Infinity;
      for (const i of seen) for (let j = 0; j < nodes.length; j++) {
        if (!seen.has(j) && nodes[j].kind !== 'link' && nodes[i].kind !== 'link' && dist(i, j) < d) { d = dist(i, j); best = [i, j]; }
      }
      add(best[0], best[1]);
    }
    return [...set].map((e) => e.split('-').map(Number) as [number, number]);
  })();
  const isLink = (e: number) => links.includes(edges[e][0]) || links.includes(edges[e][1]);
  const injections = (() => {
    const load = cities.reduce((s, i) => s + nodes[i].size, 0);
    const gen = plants.reduce((s, i) => s + nodes[i].size, 0);
    return nodes.map((n) => (n.kind === 'city' ? -n.size : n.kind === 'link' ? 0 : (n.size * load) / gen));
  })();

  /** DC power flow over the lines still in (`on`); an island far short of generation collapses, a little short sheds
   * its smallest cities, one with more turns its plants down. */
  const flows = (on: boolean[], inj = injections) => {
    const n = nodes.length;
    const adj: number[][] = nodes.map(() => []);
    edges.forEach(([a, b], e) => { if (on[e]) { adj[a].push(e); adj[b].push(e); } });
    const island = Array(n).fill(-1);
    let count = 0;
    for (let s0 = 0; s0 < n; s0++) {
      if (island[s0] >= 0) continue;
      const stack = [s0];
      island[s0] = count;
      while (stack.length) {
        const v = stack.pop()!;
        for (const e of adj[v]) {
          const w = edges[e][0] === v ? edges[e][1] : edges[e][0];
          if (island[w] < 0) { island[w] = count; stack.push(w); }
        }
      }
      count++;
    }
    const p = [...inj];
    const dark = Array(n).fill(false);
    for (let c = 0; c < count; c++) {
      const members = nodes.map((_, i) => i).filter((i) => island[i] === c);
      const load = members.reduce((s, i) => s + Math.max(0, -p[i]), 0);
      const gen = members.reduce((s, i) => s + Math.max(0, p[i]), 0);
      if (load > 0 && gen < load * 0.8) {
        members.forEach((i) => { dark[i] = true; p[i] = 0; });
        continue;
      }
      let short = load - gen;
      if (short > 0) {
        for (const i of members.filter((j) => nodes[j].kind === 'city').sort((a, b) => nodes[a].size - nodes[b].size)) {
          if (short <= 0) break;
          short -= nodes[i].size;
          dark[i] = true;
          p[i] = 0;
        }
      }
      const left = members.reduce((s, i) => s + Math.max(0, -p[i]), 0);
      if (gen > 0) members.forEach((i) => { if (p[i] > 0) p[i] *= left / gen; });
    }
    const B = Array.from({length: n}, () => new Float64Array(n));
    edges.forEach(([a, b], e) => {
      if (!on[e]) return;
      const y = 100 / dist(a, b);
      B[a][a] += y; B[b][b] += y; B[a][b] -= y; B[b][a] -= y;
    });
    const ref = new Set<number>();
    for (let c = 0; c < count; c++) ref.add(island.indexOf(c));
    const idx = nodes.map((_, i) => i).filter((i) => !ref.has(i));
    const m = idx.length;
    const A = idx.map((i) => [...idx.map((j) => B[i][j]), p[i]]);
    for (let col = 0; col < m; col++) {
      let piv = col;
      for (let r = col + 1; r < m; r++) if (Math.abs(A[r][col]) > Math.abs(A[piv][col])) piv = r;
      [A[col], A[piv]] = [A[piv], A[col]];
      const d = A[col][col] || 1e-12;
      for (let r = 0; r < m; r++) {
        if (r === col || !A[r][col]) continue;
        const f = A[r][col] / d;
        for (let c2 = col; c2 <= m; c2++) A[r][c2] -= f * A[col][c2];
      }
    }
    const theta = Array(n).fill(0);
    idx.forEach((i, r) => { theta[i] = A[r][m] / (A[r][r] || 1e-12); });
    const flow = edges.map(([a, b], e) => (on[e] ? (theta[a] - theta[b]) * (100 / dist(a, b)) : 0));
    return {flow, dark};
  };
  const base = flows(edges.map(() => true));

  const cascades = new Map<string, Cascade>();
  const cascade = (margin: number, first: number[] = grid.first, split: number[] = [], inj = injections, safe: number[] = []): Cascade => {
    const id = `${margin}:${first}:${split}:${inj === injections ? '' : inj.join(',')}:${safe}`;
    if (cascades.has(id)) return cascades.get(id)!;
    const b0 = inj === injections ? base : flows(edges.map(() => true), inj);
    const mean = b0.flow.reduce((a, f) => a + Math.abs(f), 0) / b0.flow.length;
    // each line carries its normal flow + margin (a floor for the quiet ones); the lines inside a part that separated
    // in time (`safe`) are held by its own operators
    const cap = b0.flow.map((f, e) => (edges[e].every((i) => safe.includes(i)) ? Infinity : Math.max(Math.abs(f), 1.3 * mean) * (1 + margin)));
    const on = edges.map(() => true);
    const waves: Wave[] = [];
    let failing = [...first];
    const darkSoFar = Array(nodes.length).fill(false);
    for (let step = 0; failing.length && step < 40; step++) {
      failing.forEach((e) => { on[e] = false; });
      if (step === 1) split.forEach((e) => { on[e] = false; });
      const {flow, dark} = flows(on, inj);
      dark.forEach((d, i) => { if (d) darkSoFar[i] = true; });          // a city that went dark stays dark
      waves.push({lines: [...failing, ...(step === 1 ? split : [])], dark: [...darkSoFar], flow});
      failing = edges.map((_, e) => e).filter((e) => on[e] && Math.abs(flow[e]) > cap[e]);
    }
    const out = {waves};
    cascades.set(id, out);
    return out;
  };
  const darkShare = (dark: boolean[]) => {
    const all = cities.reduce((s, i) => s + nodes[i].size, 0);
    return cities.reduce((s, i) => s + (dark[i] ? nodes[i].size : 0), 0) / all;
  };

  const restores = new Map<boolean, Restore>();
  const blackStart = (rush: boolean): Restore => {
    if (restores.has(rush)) return restores.get(rush)!;
    const seeds = nodes.map((n, i) => (n.kind === 'hidro' || n.kind === 'link' ? i : -1)).filter((i) => i >= 0);
    const lit = new Uint8Array(nodes.length);
    const owner = Array(nodes.length).fill(-1);
    seeds.forEach((s0, j) => { lit[s0] = 1; owner[s0] = j; });
    const out: Restore = {lit: [Uint8Array.from(lit)], merge: [], fallback: []};
    const nb = nodes.map((_, i) => edges.filter(([a, b]) => a === i || b === i).map(([a, b]) => (a === i ? b : a)));
    let crashed = false;
    for (let step = 1; step < 200 && lit.some((v) => !v); step++) {
      const islands = [...new Set(owner.filter((o) => o >= 0))];
      const o = islands[step % islands.length];
      const members = owner.map((x, i) => (x === o ? i : -1)).filter((i) => i >= 0);
      const gen = members.reduce((s0, i) => s0 + (nodes[i].kind === 'city' ? 0 : nodes[i].size), 0);
      const load = members.reduce((s0, i) => s0 + (nodes[i].kind === 'city' ? nodes[i].size : 0), 0);
      const frontier = [...new Set(members.flatMap((i) => nb[i]))].filter((j) => !lit[j]);
      if (!frontier.length) continue;
      const wantPlant = load >= gen * 0.8;
      const pick = frontier.find((j) => (nodes[j].kind !== 'city') === wantPlant) ?? frontier[0];
      if (rush && !crashed && step > 14) {
        // everybody switches everything on at once: the island's frequency sinks and it falls again
        crashed = true;
        members.forEach((i) => { if (!seeds.includes(i)) { lit[i] = 0; owner[i] = -1; } });
        out.fallback.push(step);
        out.lit.push(Uint8Array.from(lit));
        continue;
      }
      lit[pick] = 1;
      owner[pick] = o;
      const touch = nb[pick].map((j) => owner[j]).filter((x) => x >= 0 && x !== o);
      if (touch.length) {
        out.merge.push(step);
        touch.forEach((x) => owner.forEach((y, i) => { if (y === x) owner[i] = o; }));
      }
      out.lit.push(Uint8Array.from(lit));
    }
    restores.set(rush, out);
    return out;
  };

  const grid: Grid = {
    key, nodes, edges, coast: path(spec.coast, true), borders: (spec.borders ?? []).map((b) => path(b, false)),
    lakes: (spec.lakes ?? []).map((l) => path(l, true)), names: spec.names.map(([word, lo, la, size]) => ({word, x: X(lo), y: Y(la), size})),
    people: spec.people, X, Y, links, cities, plants, injections, base, first: [], region: [], regionCut: [], withLink: injections,
    flows, cascade, darkShare, blackStart,
  };
  // the first fault: the one named, else a line of average load whose cascade depends on the margin (most of the
  // country dark with 15 %, nothing with 40 %), the longest cascade among them
  const named = spec.first ? edges.findIndex(([a, b]) => [nodes[a].name, nodes[b].name].sort().join() === [...spec.first!].sort().join()) : -1;
  if (named >= 0) grid.first = [named];
  else {
    let best = -1;
    let score = -1;
    edges.forEach((_, e) => {
      if (isLink(e)) return;
      const low = cascade(0.15, [e]);
      const high = cascade(0.4, [e]);
      const dLow = darkShare(low.waves[low.waves.length - 1].dark);
      const dHigh = darkShare(high.waves[high.waves.length - 1].dark);
      const sc = (dLow > 0.45 ? 10 : 0) + (dHigh < 0.1 ? 10 : 0) + dLow * 5 + low.waves.length * 0.2;
      if (sc > score) { score = sc; best = e; }
    });
    grid.first = [best];
  }
  // the island: the corner around the link to a neighbour (it keeps that power coming in) that best survives the
  // cascade while the rest goes dark
  let bestScore = -1;
  for (const l of links) {
    const around = [l, ...nodes.map((_, i) => i).filter((i) => i !== l && nodes[i].kind !== 'link').sort((a, b) => dist(l, a) - dist(l, b)).slice(0, 5)];
    const cut = edges.map((_, e) => e).filter((e) => around.includes(edges[e][0]) !== around.includes(edges[e][1]));
    const inj = injections.map((p, i) => (i === l ? around.reduce((s, j) => s + (nodes[j].kind === 'city' ? nodes[j].size : 0), 0) * 0.6 : p));
    const c = cascade(0.15, grid.first, cut, inj, around);
    const d = c.waves[c.waves.length - 1].dark;
    const saved = around.filter((i) => nodes[i].kind === 'city' && !d[i]).length;
    const sc = saved * 10 + darkShare(d) * 5 - (around.some((i) => grid.first.some((e) => edges[e].includes(i))) ? 100 : 0);
    if (sc > bestScore) { bestScore = sc; grid.region = around; grid.regionCut = cut; grid.withLink = inj; }
  }
  GRIDS.set(key, grid);
  return grid;
};

export const SPINNING: Kind[] = ['nuclear', 'cc', 'hidro'];

// --- frequency ------------------------------------------------------------------------------------------------------------
export type FreqRun = {t: number[]; f: number[]; shed: number[]; tripped: number[]; collapse: number};
const FREQ = new Map<string, FreqRun>();

/** 30 s after losing `loss` (share of demand) of generation with inertia H (s): governors answer in seconds, plants trip
 * below 48.8 Hz (more loss), relays shed 6 % of load at 49.0 and 48.7 Hz if `shedding`; under 47.5 Hz: blackout. */
export const frequency = (H: number, loss: number, shedding: boolean, at = 2): FreqRun => {
  const id = `${H}:${loss}:${shedding}:${at}`;
  if (FREQ.has(id)) return FREQ.get(id)!;
  const dt = 0.01;
  let f = 50;
  let pg = 0;
  let lost = 0;
  let shed = 0;
  let nextTrip = 0;
  let collapse = -1;
  const out: FreqRun = {t: [], f: [], shed: [], tripped: [], collapse: -1};
  for (let t = 0; t <= 30; t += dt) {
    if (t >= at && lost === 0) lost = loss;
    if (collapse < 0) {
      if (shedding && f < 49.0 && shed < 0.06) shed = 0.06;
      if (shedding && f < 48.7 && shed < 0.12) shed = 0.12;
      if (f < 48.8 && t > nextTrip) { lost += 0.035; nextTrip = t + 0.4; }      // plants protect themselves
      const target = Math.min(0.1, 20 * (50 - f) / 50);
      pg += ((target - pg) / 5) * dt;
      const imbalance = -lost + pg + shed + 1.5 * (50 - f) / 50;
      f += (50 / (2 * H)) * imbalance * dt;
      if (f < 47.5) collapse = t;
    } else {
      f = Math.max(0, f - 8 * dt);
    }
    if (Math.round(t / dt) % 5 === 0) {
      out.t.push(Math.round(t * 100) / 100);
      out.f.push(f);
      out.shed.push(shed);
      out.tripped.push(lost);
    }
  }
  out.collapse = collapse;
  FREQ.set(id, out);
  return out;
};
export const freqAt = (r: FreqRun, t: number) => r.f[Math.max(0, Math.min(r.f.length - 1, Math.round(t / 0.05)))];

// --- the sandpile -----------------------------------------------------------------------------------------------------------
export const PILE = {w: 48, h: 27};
export type Pile = {grids: Uint8Array[]; toppled: Uint16Array[]; sizes: number[]};
let PILE_RUN: Pile | null = null;
export const sandpile = (): Pile => {
  if (PILE_RUN) return PILE_RUN;
  const {w, h} = PILE;
  const rnd = mulberry(7);
  const g = new Uint8Array(w * h);
  for (let i = 0; i < g.length; i++) g[i] = Math.floor(rnd() * 4);
  const drop = (cell: number, record: number[] | null) => {
    g[cell]++;
    const stack = [cell];
    while (stack.length) {
      const c = stack.pop()!;
      while (g[c] >= 4) {
        g[c] -= 4;
        if (record) record.push(c);
        const x = c % w;
        const y = Math.floor(c / w);
        for (const [nx, ny] of [[x + 1, y], [x - 1, y], [x, y + 1], [x, y - 1]]) {
          if (nx < 0 || ny < 0 || nx >= w || ny >= h) continue;             // grains falling off the edge
          const d = ny * w + nx;
          g[d]++;
          if (g[d] >= 4) stack.push(d);
        }
      }
    }
  };
  for (let k = 0; k < 40000; k++) drop(Math.floor(rnd() * w * h), null);          // to the critical state
  const out: Pile = {grids: [], toppled: [], sizes: []};
  for (let k = 0; k < 500; k++) {
    const rec: number[] = [];
    drop(Math.floor(rnd() * w * h), rec);
    out.grids.push(Uint8Array.from(g));
    out.toppled.push(Uint16Array.from(new Set(rec)));
    out.sizes.push(rec.length);
  }
  PILE_RUN = out;
  return out;
};
