import { existsSync } from 'node:fs';
import { Config } from '@remotion/cli/config';

Config.setVideoImageFormat('jpeg');

// @remotion/three (globo y terreno 3D, fase 5) necesita WebGL en render sin pantalla.
// "angle" usa la GPU si existe y si no cae a SwiftShader (software); en máquinas sin GPU,
// "swangle" fuerza SwiftShader sobre ANGLE, que es lo que usa Remotion Lambda.
Config.setChromiumOpenGlRenderer(process.env.REMOTION_GL === 'angle' ? 'angle' : 'swangle');

// En el contenedor cloud hay un Chromium preinstalado (el completo: lee el almacén NSS con el CA
// del proxy, necesario para bajar las fuentes); en otras máquinas Remotion usa el suyo.
const PREINSTALLED_SHELL = '/opt/pw-browsers/chromium-1243/chrome-linux64/chrome';
if (!process.env.REMOTION_BROWSER && existsSync(PREINSTALLED_SHELL)) {
  Config.setBrowserExecutable(PREINSTALLED_SHELL);
} else if (process.env.REMOTION_BROWSER) {
  Config.setBrowserExecutable(process.env.REMOTION_BROWSER);
}
