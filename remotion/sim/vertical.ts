// How a simulation shot fills a vertical (9:16) frame. Wide scenes (roads, split screens, a corridor) are cut in two
// halves stacked like two lines of text — the road goes on in the second one, the comparison reads top against bottom;
// compact ones (a ring, a map, one till) are enlarged around what matters, leaving room above and below for the title
// and the captions.
import type {SimGraphic} from '../graphics';

export type Vertical = {mode: 'halves'} | {mode: 'crop'; cx: number; cy: number; scale: number};

const scene = (g: SimGraphic, fallback: string) => String(g.params?.scene ?? fallback);

// the scenes shared by many worlds: two runs side by side (one above the other) and the charts (the whole picture, smaller)
const SPLITS = ['densidad', 'viento', 'cortafuegos', 'antes'];
const CHARTS = ['curva', 'vacunas', 'umbral', 'ojos', 'dilucion', 'trafico', 'verde', 'pasan'];
const SHARED = ['contagio', 'incendio', 'segregacion', 'manada', 'cruces', 'autovia'];

export const verticalOf = (g: SimGraphic): Vertical => {
  if (SHARED.includes(g.world)) {
    const sc = scene(g, '');
    if (SPLITS.includes(sc) || (sc === 'comparar' && g.world !== 'cruces' && g.world !== 'autovia')) return {mode: 'halves'};
    if (CHARTS.includes(sc)) return {mode: 'crop', cx: 960, cy: 540, scale: 0.56};
  }
  switch (g.world) {
    case 'carretera':
    case 'autovia':
      return {mode: 'halves'};
    case 'cruces':
      return g.focus === 'both' ? {mode: 'halves'} : {mode: 'crop', cx: g.focus === 'left' ? 700 : 1220, cy: 540, scale: 1.25};
    case 'anillo':
      return g.focus === 'compare' ? {mode: 'halves'} : {mode: 'crop', cx: g.focus === 'chart' ? 700 : 960, cy: 540, scale: 1.1};
    case 'colas': {
      const s = scene(g, 'comparar');
      if (['comparar', 'iguales', 'rapida'].includes(s)) return {mode: 'halves'};
      return {mode: 'crop', cx: s === 'eleccion' ? 760 : s === 'contar' ? 700 : s === 'limite' ? 960 : 960, cy: 520, scale: 1.25};
    }
    case 'inundacion':
      return scene(g, 'sube') === 'sube' ? {mode: 'crop', cx: 960, cy: 540, scale: 1.3} : {mode: 'halves'};
    case 'multitud': {
      const s = scene(g, 'evacuacion');
      return s === 'evacuacion' ? {mode: 'crop', cx: 1260, cy: 540, scale: 1.35} : {mode: 'halves'};
    }
    case 'aeropuerto':
      return {mode: 'halves'};
    case 'explica':
      return {mode: 'crop', cx: 960, cy: 540, scale: 0.56};
    case 'embarque':
      return scene(g, 'comparar') === 'puerta' ? {mode: 'halves'} : {mode: 'crop', cx: 960, cy: 540, scale: 1.0};
    case 'apagon':
      return scene(g, 'cascada') === 'inercia' ? {mode: 'halves'} : scene(g, 'cascada') === 'frecuencia' ? {mode: 'crop', cx: 1380, cy: 560, scale: 1.0}
        : {mode: 'crop', cx: 960, cy: 540, scale: 1.0};
    case 'metro':
      return scene(g, 'comparar') === 'comparar' ? {mode: 'halves'} : {mode: 'crop', cx: 960, cy: 560, scale: 1.2};
    case 'ascensores':
      return ['zonas', 'destino', 'reparto'].includes(scene(g, 'pico')) ? {mode: 'halves'} : ['juntos', 'botones'].includes(scene(g, 'pico'))
        ? {mode: 'crop', cx: 760, cy: 540, scale: 1.0} : {mode: 'crop', cx: 960, cy: 540, scale: 1.1};
    case 'restaurante':
      return scene(g, 'comandas') === 'orden' ? {mode: 'halves'} : {mode: 'crop', cx: 960, cy: 540, scale: 1.2};
    case 'aparcamiento':
      return scene(g, 'buscar') === 'comparar' ? {mode: 'halves'} : {mode: 'crop', cx: 960, cy: 540, scale: 1.15};
    default:
      return {mode: 'crop', cx: 960, cy: 540, scale: 1.15};
  }
};
