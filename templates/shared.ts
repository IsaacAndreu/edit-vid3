/** Deterministic hash used to pick a motion variant from a media URL. */
export const hashSeed = (seed: string): number => {
  let hash = 0;

  for (let index = 0; index < seed.length; index += 1) {
    hash = (hash * 31 + seed.charCodeAt(index)) >>> 0;
  }

  return hash;
};
