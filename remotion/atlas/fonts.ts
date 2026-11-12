/**
 * Tres familias, nunca más (prompt maestro §2), desde archivos locales: el render no necesita red.
 * Fraunces (serif de titulares y cifras, con su cursiva) e IBM Plex Mono (antetítulos y etiquetas).
 */
import { loadFont } from '@remotion/fonts';
import fr400 from '@fontsource/fraunces/files/fraunces-latin-400-normal.woff2';
import fr500 from '@fontsource/fraunces/files/fraunces-latin-500-normal.woff2';
import fr600 from '@fontsource/fraunces/files/fraunces-latin-600-normal.woff2';
import fr700 from '@fontsource/fraunces/files/fraunces-latin-700-normal.woff2';
import fr400i from '@fontsource/fraunces/files/fraunces-latin-400-italic.woff2';
import fr500i from '@fontsource/fraunces/files/fraunces-latin-500-italic.woff2';
import fr600i from '@fontsource/fraunces/files/fraunces-latin-600-italic.woff2';
import fr700i from '@fontsource/fraunces/files/fraunces-latin-700-italic.woff2';
import pm400 from '@fontsource/ibm-plex-mono/files/ibm-plex-mono-latin-400-normal.woff2';
import pm500 from '@fontsource/ibm-plex-mono/files/ibm-plex-mono-latin-500-normal.woff2';
import pm600 from '@fontsource/ibm-plex-mono/files/ibm-plex-mono-latin-600-normal.woff2';
import pm400i from '@fontsource/ibm-plex-mono/files/ibm-plex-mono-latin-400-italic.woff2';

const SERIF = 'Fraunces';
const MONO = 'IBM Plex Mono';

const loaded = Promise.all(
  (
    [
      [SERIF, fr400, '400', 'normal'],
      [SERIF, fr500, '500', 'normal'],
      [SERIF, fr600, '600', 'normal'],
      [SERIF, fr700, '700', 'normal'],
      [SERIF, fr400i, '400', 'italic'],
      [SERIF, fr500i, '500', 'italic'],
      [SERIF, fr600i, '600', 'italic'],
      [SERIF, fr700i, '700', 'italic'],
      [MONO, pm400, '400', 'normal'],
      [MONO, pm500, '500', 'normal'],
      [MONO, pm600, '600', 'normal'],
      [MONO, pm400i, '400', 'italic'],
    ] as const
  ).map(([family, url, weight, style]) => loadFont({ family, url, weight, style })),
);

export const fonts = {
  serif: `'${SERIF}', Georgia, serif`,
  serifItalic: `'${SERIF}', Georgia, serif`,
  mono: `'${MONO}', monospace`,
  monoItalic: `'${MONO}', monospace`,
};

export const waitForFonts = () => loaded;
