import { loadFont as loadFraunces } from '@remotion/google-fonts/Fraunces';
import { loadFont as loadPlexMono } from '@remotion/google-fonts/IBMPlexMono';

/** Tres familias, nunca más (prompt maestro §2). */
const serif = loadFraunces('normal', { weights: ['400', '600', '700'], subsets: ['latin', 'latin-ext'] });
const serifItalic = loadFraunces('italic', { weights: ['400', '600', '700'], subsets: ['latin', 'latin-ext'] });
const mono = loadPlexMono('normal', { weights: ['400', '500', '600'], subsets: ['latin', 'latin-ext'] });
const monoItalic = loadPlexMono('italic', { weights: ['400'], subsets: ['latin', 'latin-ext'] });

export const fonts = {
  serif: serif.fontFamily,
  serifItalic: serifItalic.fontFamily,
  mono: mono.fontFamily,
  monoItalic: monoItalic.fontFamily,
};

export const waitForFonts = () =>
  Promise.all([serif.waitUntilDone(), serifItalic.waitUntilDone(), mono.waitUntilDone(), monoItalic.waitUntilDone()]);
