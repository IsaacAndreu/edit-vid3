import { loadFont } from '@remotion/fonts';
import inter400 from '@fontsource/inter/files/inter-latin-400-normal.woff2';
import inter500 from '@fontsource/inter/files/inter-latin-500-normal.woff2';
import inter600 from '@fontsource/inter/files/inter-latin-600-normal.woff2';
import inter800 from '@fontsource/inter/files/inter-latin-800-normal.woff2';
import inter900 from '@fontsource/inter/files/inter-latin-900-normal.woff2';
import oswald500 from '@fontsource/oswald/files/oswald-latin-500-normal.woff2';
import oswald700 from '@fontsource/oswald/files/oswald-latin-700-normal.woff2';

import barlow500 from '@fontsource/barlow-condensed/files/barlow-condensed-latin-500-normal.woff2';
import barlow600 from '@fontsource/barlow-condensed/files/barlow-condensed-latin-600-normal.woff2';
import barlow700 from '@fontsource/barlow-condensed/files/barlow-condensed-latin-700-normal.woff2';
import barlow800 from '@fontsource/barlow-condensed/files/barlow-condensed-latin-800-normal.woff2';
import barlow700i from '@fontsource/barlow-condensed/files/barlow-condensed-latin-700-italic.woff2';
import barlow800i from '@fontsource/barlow-condensed/files/barlow-condensed-latin-800-italic.woff2';
import dmSerif400 from '@fontsource/dm-serif-display/files/dm-serif-display-latin-400-normal.woff2';
import mono500 from '@fontsource/jetbrains-mono/files/jetbrains-mono-latin-500-normal.woff2';
import mono700 from '@fontsource/jetbrains-mono/files/jetbrains-mono-latin-700-normal.woff2';
import grotesk500 from '@fontsource/space-grotesk/files/space-grotesk-latin-500-normal.woff2';
import grotesk700 from '@fontsource/space-grotesk/files/space-grotesk-latin-700-normal.woff2';

// Inter from local files (no network at render time): 400 labels, 600 values, 800-900 titles/numbers.
for (const [url, weight] of [
  [inter400, '400'],
  [inter500, '500'],
  [inter600, '600'],
  [inter800, '800'],
  [inter900, '900'],
] as const) {
  loadFont({ family: 'Inter', url, weight });
}
// Oswald: the narrow type of numbered chapter cards ("CAPÍTULO I:").
for (const [url, weight] of [
  [oswald500, '500'],
  [oswald700, '700'],
] as const) {
  loadFont({ family: 'Oswald', url, weight });
}
// The channels' own type (brand.motion): sport → Barlow Condensed, editorial → DM Serif Display titles,
// tech → Space Grotesk + JetBrains Mono.
for (const [family, url, weight, style] of [
  ['Barlow Condensed', barlow500, '500', 'normal'],
  ['Barlow Condensed', barlow600, '600', 'normal'],
  ['Barlow Condensed', barlow700, '700', 'normal'],
  ['Barlow Condensed', barlow800, '800', 'normal'],
  ['Barlow Condensed', barlow700i, '700', 'italic'],
  ['Barlow Condensed', barlow800i, '800', 'italic'],
  ['DM Serif Display', dmSerif400, '400', 'normal'],
  ['JetBrains Mono', mono500, '500', 'normal'],
  ['JetBrains Mono', mono700, '700', 'normal'],
  ['Space Grotesk', grotesk500, '500', 'normal'],
  ['Space Grotesk', grotesk700, '700', 'normal'],
] as const) {
  loadFont({ family, url, weight, style });
}

// Every component writes these families; the channel's motion pack decides what they are (CSS variables set
// by applyBrand), so one brand switch changes the type of every graphic, label and card.
export const fontFamily = "var(--ev-body, 'Inter')";
export const titleFamily = "var(--ev-title, 'Inter')";
export const condensedFamily = "var(--ev-display, 'Oswald')";
export const monoFamily = "var(--ev-mono, 'JetBrains Mono')";

/** Motion packs: type and the way graphics come in and out, per channel (brand.motion). */
export type Motion = 'clean' | 'sport' | 'editorial' | 'tech';
export const PACKS: Record<Motion, { body: string; title: string; display: string; mono: string; titleItalic: boolean; titleUpper: boolean }> = {
  clean: { body: "'Inter'", title: "'Inter'", display: "'Oswald'", mono: "'JetBrains Mono'", titleItalic: false, titleUpper: true },
  sport: { body: "'Barlow Condensed', 'Inter'", title: "'Barlow Condensed', 'Inter'", display: "'Barlow Condensed', 'Oswald'",
    mono: "'Barlow Condensed'", titleItalic: true, titleUpper: true },
  editorial: { body: "'Inter'", title: "'DM Serif Display', 'Inter'", display: "'DM Serif Display', 'Oswald'",
    mono: "'JetBrains Mono'", titleItalic: false, titleUpper: false },
  tech: { body: "'Space Grotesk', 'Inter'", title: "'JetBrains Mono', 'Inter'", display: "'Space Grotesk', 'Oswald'",
    mono: "'JetBrains Mono'", titleItalic: false, titleUpper: true },
};

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
  // motion: 'clean' (neutral) | 'sport' (diagonal wipes, speed lines, condensed italic) | 'editorial' (soft fades,
  // magazine rules, serif titles) | 'tech' (glitch, corner brackets, scanlines, mono type)
  motion: 'clean',
  // mapStyle: 'tilted' (dark map leaning back, glowing borders) | 'flat' (top-down flat colours, the highlighted
  // area filled solid with its name inside, as aviation/business explainers do); mapHighlight: that fill
  mapStyle: 'tilted',
  mapHighlight: '',
  // articleStyle: 'dark' (navy desk, figures circled in red) | 'paper' (white page, yellow highlighter);
  // dataStyle: 'dark' | 'light' (charts on a light background, like printed infographics)
  articleStyle: 'dark',
  dataStyle: 'dark',
};

export type Brand = Partial<typeof DEFAULTS>;

export const theme = { ...DEFAULTS };

/** Called at the top of every composition with its props.brand (same props → same look on every frame). */
export const applyBrand = (brand?: Brand | null): void => {
  Object.assign(theme, DEFAULTS, brand ?? {});
  const pack = PACKS[(theme.motion as Motion) in PACKS ? (theme.motion as Motion) : 'clean'];
  if (typeof document !== 'undefined') {
    const root = document.documentElement.style;
    root.setProperty('--ev-body', pack.body);
    root.setProperty('--ev-title', pack.title);
    root.setProperty('--ev-display', pack.display);
    root.setProperty('--ev-mono', pack.mono);
  }
};

export const pack = () => PACKS[(theme.motion as Motion) in PACKS ? (theme.motion as Motion) : 'clean'];

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
