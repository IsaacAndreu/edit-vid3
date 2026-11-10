/**
 * Puente con el Atlas automático (pipeline/atlas.py → remotion/components/graphics/Atlas.tsx): una escena del
 * esquema de schema.ts dentro de un grupo del timeline. Los tiempos llegan en segundos desde el inicio del grupo
 * ({ t }); la página, el grano, la viñeta y la cabecera los pone Atlas.tsx.
 */
import type { FC } from 'react';
import { AbsoluteFill } from 'remotion';
import { SceneContext } from './context';
import { OverlayLayer, SourceNote } from './overlays';
import { atlasScenes } from './scenes';
import type { AtlasStoryboard } from './schema';
import { sceneSchema } from './schema';

const ROMAN = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X'];

export const EmbeddedAtlasScene: FC<{
  scene: unknown;
  durationInFrames: number;
  fps: number;
  chapters?: string[];
  brand?: string;
}> = ({ scene, durationInFrames, fps, chapters = [], brand = '' }) => {
  const parsed = sceneSchema.safeParse(scene);
  if (!parsed.success) {
    // Un JSON que no cumple el esquema no tumba el vídeo: el pipeline ya lo valida, esto es la red de seguridad.
    console.warn('Escena Atlas inválida:', parsed.error.issues.map((i) => `${i.path.join('.')}: ${i.message}`).join(' · '));
    return null;
  }
  const s = parsed.data;
  const Component = atlasScenes[s.type];
  if (!Component) return null;
  const storyboard: AtlasStoryboard = {
    meta: {
      slug: 'embebido',
      title: '',
      brand: { name: brand, icon: '' },
      chapters: chapters.map((label, i) => ({ numeral: ROMAN[i] ?? String(i + 1), label })),
      duration: durationInFrames / fps,
    },
    audio: {},
    scenes: [s],
  };
  return (
    <SceneContext.Provider value={{ storyboard, scene: s, index: 0, start: 0, end: durationInFrames / fps, origin: 0, previous: null }}>
      <AbsoluteFill>
        <Component />
        <OverlayLayer overlays={s.overlays} />
        <SourceNote />
      </AbsoluteFill>
    </SceneContext.Provider>
  );
};
