/** Carga de JSON de public/ (meta.json de región, GeoJSON) con delayRender: el fotograma espera a los datos. */
import { useEffect, useState } from 'react';
import { cancelRender, continueRender, delayRender, staticFile } from 'remotion';

const cache = new Map<string, unknown>();
const pending = new Map<string, Promise<unknown>>();

const load = (path: string): Promise<unknown> => {
  if (!pending.has(path)) {
    pending.set(
      path,
      fetch(staticFile(path)).then(async (res) => {
        if (!res.ok) throw new Error(`No se pudo leer ${path} (HTTP ${res.status}): ¿falta npm run atlas:data?`);
        const json = await res.json();
        cache.set(path, json);
        return json;
      }),
    );
  }
  return pending.get(path)!;
};

/** Varias rutas a la vez; devuelve null hasta que están todas. */
export const useJsonFiles = <T,>(paths: string[]): T[] | null => {
  const key = paths.join('|');
  const ready = () => paths.every((p) => cache.has(p));
  const [, setTick] = useState(0);
  useEffect(() => {
    if (ready()) return;
    const handle = delayRender(`atlas: ${key}`);
    Promise.all(paths.map(load))
      .then(() => {
        setTick((t) => t + 1);
        continueRender(handle);
      })
      .catch((err) => cancelRender(err));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return ready() ? (paths.map((p) => cache.get(p)) as T[]) : null;
};
