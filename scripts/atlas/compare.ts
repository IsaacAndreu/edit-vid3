/**
 * Parejas original/render, una por fila, para el bucle visual y las puertas de decisión.
 *
 *   npm run atlas:compare -- <salida.jpg> <render.png>=<referencia.jpg> [...]
 *
 * La referencia puede ser un nombre de referencias/atlas/frames sin extensión ("1-00_chapter-card").
 */
import { existsSync } from 'node:fs';
import { join } from 'node:path';
import sharp from 'sharp';
import { ROOT, run } from './load';

const W = 960;
const H = 540;
const LABEL = 30;

run(async () => {
  const [out, ...pairs] = process.argv.slice(2);
  if (!out || pairs.length === 0) throw new Error('Uso: atlas:compare <salida.jpg> <render>=<referencia> ...');
  const tiles: sharp.OverlayOptions[] = [];
  for (const [i, pair] of pairs.entries()) {
    const [render, refArg] = pair.split('=');
    const ref = existsSync(refArg) ? refArg : join(ROOT, 'referencias', 'atlas', 'frames', `${refArg}.jpg`);
    const top = i * (H + LABEL);
    const label = (text: string, left: number) => ({
      input: Buffer.from(
        `<svg width="${W}" height="${LABEL}"><rect width="100%" height="100%" fill="#111"/><text x="10" y="21" font-family="monospace" font-size="15" fill="#eee">${text.replace(/[<>&]/g, '')}</text></svg>`,
      ),
      left,
      top,
    });
    tiles.push(label(`render · ${render.split('/').pop()}`, 0), label(`original · ${ref.split('/').pop()}`, W));
    tiles.push({ input: await sharp(render).resize(W, H).toBuffer(), left: 0, top: top + LABEL });
    tiles.push({ input: await sharp(ref).resize(W, H).toBuffer(), left: W, top: top + LABEL });
  }
  await sharp({ create: { width: 2 * W, height: pairs.length * (H + LABEL), channels: 3, background: '#000' } })
    .composite(tiles)
    .jpeg({ quality: 85 })
    .toFile(out);
  console.log(out);
});
