/** Textura de three.js desde public/, con delayRender hasta que está cargada. */
import { useEffect, useState } from 'react';
import { cancelRender, continueRender, delayRender, staticFile } from 'remotion';
import { SRGBColorSpace, TextureLoader, type Texture } from 'three';

const cache = new Map<string, Texture>();

export const useTexture = (path: string): Texture | null => {
  const [, setTick] = useState(0);
  useEffect(() => {
    if (cache.has(path)) return;
    const handle = delayRender(`textura ${path}`);
    new TextureLoader().load(
      staticFile(path),
      (tex) => {
        tex.colorSpace = SRGBColorSpace;
        tex.anisotropy = 8;
        cache.set(path, tex);
        setTick((t) => t + 1);
        continueRender(handle);
      },
      undefined,
      () => cancelRender(new Error(`No se pudo cargar ${path}: ¿falta npm run atlas:data?`)),
    );
  }, [path]);
  return cache.get(path) ?? null;
};
