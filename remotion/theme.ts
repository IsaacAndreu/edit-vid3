import { loadFont } from '@remotion/fonts';
import inter400 from '@fontsource/inter/files/inter-latin-400-normal.woff2';
import inter500 from '@fontsource/inter/files/inter-latin-500-normal.woff2';
import inter600 from '@fontsource/inter/files/inter-latin-600-normal.woff2';
import inter800 from '@fontsource/inter/files/inter-latin-800-normal.woff2';
import inter900 from '@fontsource/inter/files/inter-latin-900-normal.woff2';
import oswald500 from '@fontsource/oswald/files/oswald-latin-500-normal.woff2';
import oswald700 from '@fontsource/oswald/files/oswald-latin-700-normal.woff2';

// Inter from local files (no network at render time): 400 labels, 600 values, 800-900 titles/numbers.
export const fontFamily = 'Inter';
for (const [url, weight] of [
  [inter400, '400'],
  [inter500, '500'],
  [inter600, '600'],
  [inter800, '800'],
  [inter900, '900'],
] as const) {
  loadFont({ family: fontFamily, url, weight });
}

// Oswald: the narrow type of numbered chapter cards ("CAPÍTULO I:").
export const condensedFamily = 'Oswald';
for (const [url, weight] of [
  [oswald500, '500'],
  [oswald700, '700'],
] as const) {
  loadFont({ family: condensedFamily, url, weight });
}

/** Channel brand kit. Defaults below; each channel overrides them from config.yaml (`brand:`),
 * which reaches every composition as props.brand and is applied with applyBrand(). */
const DEFAULTS = {
  panel: '#1a1a1a', // background of data panels
  panelRaised: '#262626',
  text: '#ffffff',
  muted: '#8a8a8a',
  accent: '#ffd400', // main colour: stats, titles, dividers, highlights
  accent2: '#3b82f6', // second colour: the "B" side of comparisons, second chart series, maps
  canvas: '#07080b', // channel background behind framed cards (grid)
  glow: 'rgba(255,196,0,0.38)', // glow at the bottom of the canvas
  label: '#1f4fd8', // lower-third tags (names, places, scores)
  wipe: '#ff8a00', // chapter transition
  ocean: '#0a0d13', // maps
  land: '#1b2029',
  border: '#2b3140',
  positive: '#4ade80',
  negative: '#f87171',
  neutral: '#ffffff',
  shadow: '0 6px 30px rgba(0,0,0,0.6), 0 2px 8px rgba(0,0,0,0.75)',
  // Styles (not colours): chapterStyle 'block' ("CAPÍTULO 01" + bar) | 'numbered' ("CAPÍTULO I:" in narrow type);
  // statStyle 'panel' (dimmed frame + label) | 'bare' (only the giant figure over the footage);
  // graphicsStyle 'grid' (dark grid + glow) | 'pizarra' (textured dark-grey chalkboard, thin lines).
  chapterStyle: 'block',
  statStyle: 'panel',
  graphicsStyle: 'grid',
};

export type Brand = Partial<typeof DEFAULTS>;

export const theme = { ...DEFAULTS };

/** Called at the top of every composition with its props.brand (same props → same look on every frame). */
export const applyBrand = (brand?: Brand | null): void => {
  Object.assign(theme, DEFAULTS, brand ?? {});
};

/** A colour ('#rrggbb' or 'rgba(...)') with another opacity. */
export const alpha = (color: string, a: number): string => {
  if (color.startsWith('#') && color.length === 7) {
    const n = parseInt(color.slice(1), 16);
    return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
  }
  return color.replace(/rgba?\(([^,]+),([^,]+),([^,)]+)(?:,[^)]+)?\)/, `rgba($1,$2,$3,${a})`);
};

/** Series colours for charts: the two brand colours first. */
export const palette = (): string[] => [theme.accent, theme.accent2, '#f97316', '#22c55e', '#ec4899', '#14b8a6', '#eab308', '#a3a3a3'];

export const signColor = (sign: string): string =>
  sign === 'positive' ? theme.positive : sign === 'negative' ? theme.negative : theme.neutral;
