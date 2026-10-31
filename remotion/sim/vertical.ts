// How a simulation shot fills a vertical (9:16) frame. Wide scenes (roads, split screens, a corridor) are cut in two
// halves stacked like two lines of text — the road goes on in the second one, the comparison reads top against bottom;
// compact ones (a ring, a map, one till) are enlarged around what matters, leaving room above and below for the title
// and the captions.
import type {SimGraphic} from '../graphics';

export type Vertical = {mode: 'halves'} | {mode: 'crop'; cx: number; cy: number; scale: number};

const scene = (g: SimGraphic, fallback: string) => String(g.params?.scene ?? fallback);

export const verticalOf = (g: SimGraphic): Vertical => {
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
    default:
      return {mode: 'crop', cx: 960, cy: 540, scale: 1.15};
  }
};
