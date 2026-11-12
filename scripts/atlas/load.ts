/** Carga y valida un storyboard desde disco, resolviendo anclas contra la transcripción. */
import { existsSync, readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { parseStoryboard, type AtlasStoryboard } from '../../remotion/atlas/schema';
import { resolveStoryboardAnchors, type Transcript } from '../../remotion/atlas/time';

export const ROOT = resolve(__dirname, '..', '..');
export const PUBLIC_DIR = join(ROOT, 'public');

export const PREINSTALLED_SHELL =
  '/opt/pw-browsers/chromium-1243/chrome-linux64/chrome';
export const browserExecutable = (): string | null =>
  process.env.REMOTION_BROWSER ?? (existsSync(PREINSTALLED_SHELL) ? PREINSTALLED_SHELL : null);

export const readJson = (path: string): unknown => {
  if (!existsSync(path)) throw new Error(`No existe ${path}`);
  try {
    return JSON.parse(readFileSync(path, 'utf8'));
  } catch (err) {
    throw new Error(`${path} no es JSON válido: ${(err as Error).message}`);
  }
};

export const loadTranscript = (path: string): Transcript => {
  const json = readJson(path) as Transcript;
  if (!Array.isArray(json.words)) throw new Error(`${path} no tiene "words" (salida de pipeline/transcribe.py)`);
  return json;
};

export const loadStoryboard = (
  storyboardPath: string,
  transcriptOverride?: string,
): { raw: AtlasStoryboard; resolved: AtlasStoryboard } => {
  const raw = parseStoryboard(readJson(storyboardPath));
  const transcriptPath = transcriptOverride ?? (raw.audio.transcript ? join(PUBLIC_DIR, raw.audio.transcript) : undefined);
  const transcript = transcriptPath ? loadTranscript(transcriptPath) : null;
  return { raw, resolved: resolveStoryboardAnchors(raw, transcript) };
};

/** Ejecuta main() mostrando sólo el mensaje del error (legible) y saliendo con código 1. */
export const run = (main: () => Promise<void> | void) => {
  Promise.resolve()
    .then(main)
    .catch((err: Error) => {
      console.error(err.message);
      process.exit(1);
    });
};
