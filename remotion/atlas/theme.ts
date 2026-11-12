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

/**
 * Colores de los instrumentos de cabina (PFD) y del cielo de las vistas 3D de vuelo. El PFD usa la convención de
 * aviación (cielo azul, tierra marrón, cifras blancas): es lo que el espectador reconoce como «la pantalla del piloto».
 */
export const FLIGHT = {
  pfd: { sky: '#2F6FB0', ground: '#7A4F2A', ink: '#F4F4F0', bg: '#121418', frame: '#2A2D33', box: '#0A0B0D', magenta: '#D24BD8', amber: '#E7A63A', green: '#3FCF6A' },
  sky: { paper: { top: '#8FB3CF', horizon: '#E7E2D4' }, night: { top: '#0F1A26', horizon: '#3A4B5A' } },
  aircraft: { body: '#F2F0EA', belly: '#C9CCD1', engine: '#B7BBC2', window: '#1E2630', trim: '#2A2118' },
} as const;

/**
 * Pinturas genéricas del avión 3D: colores lisos, franja y cola de color. La decoración real de una compañía no va
 * aquí: va en el storyboard de cada caso (`livery` como objeto, con los logos que aporta el usuario).
 */
export const LIVERIES: Record<string, { body: string; belly: string; tail: string; engine: string; text: string; stripe: string | null }> = {
  white: { body: '#F2F0EA', belly: '#E4E2DC', tail: '#F2F0EA', engine: '#B7BBC2', text: '#2A2118', stripe: null },
  grey: { body: '#C9CDD2', belly: '#9EA4AB', tail: '#C9CDD2', engine: '#8E949B', text: '#1E2630', stripe: null },
  'stripe-blue': { body: '#F2F0EA', belly: '#C9CCD1', tail: '#2F5673', engine: '#B7BBC2', text: '#2F5673', stripe: '#2F5673' },
  'stripe-red': { body: '#F2F0EA', belly: '#C9CCD1', tail: '#B8322A', engine: '#B7BBC2', text: '#B8322A', stripe: '#B8322A' },
  'tail-blue': { body: '#F2F0EA', belly: '#C9CCD1', tail: '#2F5673', engine: '#B7BBC2', text: '#2A2118', stripe: null },
  'tail-red': { body: '#F2F0EA', belly: '#C9CCD1', tail: '#B8322A', engine: '#B7BBC2', text: '#2A2118', stripe: null },
  'tail-amber': { body: '#F2F0EA', belly: '#C9CCD1', tail: '#C98A2B', engine: '#B7BBC2', text: '#2A2118', stripe: null },
};
export type LiveryName = 'white' | 'grey' | 'stripe-blue' | 'stripe-red' | 'tail-blue' | 'tail-red' | 'tail-amber';
