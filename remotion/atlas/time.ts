/**
 * Resolución de tiempos: anclas de texto (`{ say }`) → segundos absolutos (`{ t }`).
 * Código puro, compartido por la composición (calculateMetadata) y por scripts/atlas.
 */
import type { At, AtlasStoryboard } from './schema';

export interface TranscriptWord {
  word: string;
  start: number;
  end: number;
}

export interface Transcript {
  words: TranscriptWord[];
  duration_seconds?: number;
}

const normalizeToken = (token: string): string =>
  token
    .toLowerCase()
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/[’']/g, '')
    .replace(/[^\p{L}\p{N}]+/gu, '');

const tokenize = (text: string): string[] =>
  text
    .split(/[\s—–-]+/)
    .map(normalizeToken)
    .filter(Boolean);

/** Tokens de la transcripción con el índice de la palabra de origen (Whisper puede partir "8,849"). */
const transcriptTokens = (words: TranscriptWord[]) => {
  const tokens: { token: string; wordIndex: number }[] = [];
  words.forEach((w, wordIndex) => {
    for (const token of tokenize(w.word)) tokens.push({ token, wordIndex });
  });
  return tokens;
};

export class AnchorError extends Error {}

const findOccurrences = (words: TranscriptWord[], phrase: string): number[] => {
  const needle = tokenize(phrase);
  if (needle.length === 0) throw new AnchorError(`la frase "${phrase}" no tiene palabras`);
  const hay = transcriptTokens(words);
  const starts: number[] = [];
  for (let i = 0; i + needle.length <= hay.length; i++) {
    let ok = true;
    for (let j = 0; j < needle.length; j++) {
      if (hay[i + j].token !== needle[j]) {
        ok = false;
        break;
      }
    }
    if (ok) starts.push(words[hay[i].wordIndex].start);
  }
  return starts;
};

export const resolveAt = (at: At, transcript: Transcript | null, where: string): number => {
  if ('t' in at) return at.t;
  if (!transcript) {
    throw new AnchorError(`${where}: ancla {say: "${at.say}"} pero el storyboard no tiene audio.transcript`);
  }
  const hits = findOccurrences(transcript.words, at.say);
  if (hits.length === 0) {
    throw new AnchorError(`${where}: la frase "${at.say}" no aparece en la transcripción`);
  }
  if (hits.length > 1 && at.nth === undefined) {
    throw new AnchorError(
      `${where}: la frase "${at.say}" aparece ${hits.length} veces (en ${hits
        .map((s) => s.toFixed(2) + ' s')
        .join(', ')}); añade "nth"`,
    );
  }
  const index = (at.nth ?? 1) - 1;
  if (index >= hits.length) {
    throw new AnchorError(`${where}: nth=${at.nth} pero "${at.say}" sólo aparece ${hits.length} veces`);
  }
  return Math.max(0, hits[index] + (at.offset ?? 0));
};

const isAt = (value: unknown): value is At =>
  typeof value === 'object' &&
  value !== null &&
  !Array.isArray(value) &&
  (typeof (value as { say?: unknown }).say === 'string' ||
    (Object.keys(value).length === 1 && typeof (value as { t?: unknown }).t === 'number'));

/**
 * Devuelve una copia del storyboard en la que cada `At` es `{ t }`.
 * Reúne todos los errores en uno solo para que se vean de una vez.
 */
export const resolveStoryboardAnchors = (
  storyboard: AtlasStoryboard,
  transcript: Transcript | null,
): AtlasStoryboard => {
  const errors: string[] = [];
  const walk = (value: unknown, path: string): unknown => {
    if (isAt(value)) {
      try {
        return { t: resolveAt(value, transcript, path) };
      } catch (err) {
        if (err instanceof AnchorError) {
          errors.push(err.message);
          return { t: 0 };
        }
        throw err;
      }
    }
    if (Array.isArray(value)) return value.map((v, i) => walk(v, `${path}[${i}]`));
    if (value && typeof value === 'object') {
      return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, walk(v, path ? `${path}.${k}` : k)]));
    }
    return value;
  };
  const resolved = walk(storyboard, '') as AtlasStoryboard;
  if (errors.length) throw new AnchorError('Anclas sin resolver — ' + errors.join(' · '));
  return resolved;
};

/** Segundos de un `At` ya resuelto. */
export const sec = (at: At): number => {
  if ('t' in at) return at.t;
  throw new AnchorError(`ancla sin resolver: {say: "${at.say}"}`);
};

export interface SceneTiming {
  index: number;
  /** Segundo en que empieza la escena. */
  start: number;
  /** Segundo en que empieza la siguiente (o el final del vídeo). */
  end: number;
}

/** Cada escena termina cuando empieza la siguiente. Exige orden estrictamente creciente. */
export const sceneTimings = (storyboard: AtlasStoryboard, totalSeconds: number): SceneTiming[] => {
  const starts = storyboard.scenes.map((s) => sec(s.start));
  const timings = starts.map((start, index) => ({
    index,
    start,
    end: index + 1 < starts.length ? starts[index + 1] : totalSeconds,
  }));
  const bad = timings.filter((t) => t.end <= t.start);
  if (bad.length) {
    throw new AnchorError(
      'Escenas sin duración (cada escena debe empezar después de la anterior y antes del final):\n' +
        bad
          .map((t) => `  · ${storyboard.scenes[t.index].id}: empieza en ${t.start.toFixed(2)} s y acaba en ${t.end.toFixed(2)} s`)
          .join('\n'),
    );
  }
  return timings;
};
