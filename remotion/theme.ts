import { loadFont } from '@remotion/fonts';
import inter400 from '@fontsource/inter/files/inter-latin-400-normal.woff2';
import inter500 from '@fontsource/inter/files/inter-latin-500-normal.woff2';
import inter600 from '@fontsource/inter/files/inter-latin-600-normal.woff2';
import inter800 from '@fontsource/inter/files/inter-latin-800-normal.woff2';
import inter900 from '@fontsource/inter/files/inter-latin-900-normal.woff2';

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

export const theme = {
  panel: '#1a1a1a', // background of data panels (spec)
  panelRaised: '#262626',
  text: '#ffffff',
  muted: '#8a8a8a',
  accent: '#ffd400', // yellow: stats, titles, dividers (reference style)
  canvas: '#07080b', // channel background behind framed cards (grid)
  glow: 'rgba(255,196,0,0.38)', // warm glow at the bottom of the canvas
  label: '#1f4fd8', // lower-third tags (names, places, scores)
  wipe: '#ff8a00', // chapter transition
  positive: '#4ade80',
  negative: '#f87171',
  neutral: '#ffffff',
  shadow: '0 6px 30px rgba(0,0,0,0.6), 0 2px 8px rgba(0,0,0,0.75)',
};

export const signColor = (sign: string): string =>
  sign === 'positive' ? theme.positive : sign === 'negative' ? theme.negative : theme.neutral;
