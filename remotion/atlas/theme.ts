/**
 * Tokens de diseño del estilo Atlas (prompts/atlas-master-prompt.md §2).
 * Único sitio con colores: los componentes leen de aquí, el storyboard sólo nombra `Accent`.
 */
export type ThemeName = 'paper' | 'night';
export type Accent = 'danger' | 'data' | 'good' | 'amber' | 'ink';

export interface ThemeTokens {
  bg: string;
  vignette: string;
  ink: string;
  inkSoft: string;
  land: string;
  regionFill: string;
  sea: string;
  seaDeep: string;
  card: string;
  cardOpacity: number;
  grid: string;
  accents: Record<Accent, string>;
}

export const themes: Record<ThemeName, ThemeTokens> = {
  paper: {
    bg: '#E7DFC9',
    vignette: '#C7BDA7',
    ink: '#2A2118',
    inkSoft: '#6F6657',
    land: '#D4C6AB',
    regionFill: '#AE8C5F',
    sea: '#A9C3D0',
    seaDeep: '#91A5A8',
    card: '#EFE8D8',
    cardOpacity: 1,
    grid: 'rgba(42, 33, 24, 0.22)',
    accents: {
      danger: '#C8402F',
      data: '#2F5673',
      good: '#3D7A5C',
      amber: '#C98A2B',
      ink: '#2A2118',
    },
  },
  night: {
    bg: '#192733',
    vignette: '#101A22',
    ink: '#EDE6D3',
    inkSoft: '#8FA0AB',
    land: '#8FA3AD',
    regionFill: 'rgba(200, 64, 47, 0.45)',
    sea: '#22384A',
    seaDeep: '#1B2E3D',
    card: '#EFE8D8',
    cardOpacity: 0.85,
    grid: 'rgba(237, 230, 211, 0.18)',
    accents: {
      danger: '#E0A84A',
      data: '#EDE6D3',
      good: '#7FB394',
      amber: '#E0A84A',
      ink: '#EDE6D3',
    },
  },
};

/** Tinta sobre tarjeta: las tarjetas son siempre claras, también en tema noche. */
export const cardInk = themes.paper.ink;
export const cardInkSoft = themes.paper.inkSoft;

export const accentOn = (theme: ThemeName, accent: Accent | undefined, fallback?: string): string =>
  accent ? themes[theme].accents[accent] : fallback ?? themes[theme].ink;

export const VIDEO = {
  width: 1920,
  height: 1080,
  fps: 30,
  /** Fundido cruzado entre escenas, en segundos (§1: 0,4–0,6 s). */
  crossfade: 0.5,
} as const;

/** Medidas comunes en píxeles a 1920×1080. */
export const LAYOUT = {
  margin: 72,
  hudTop: 54,
  monoSize: 22,
  monoTracking: '0.18em',
} as const;
