import { createContext, useContext } from 'react';
import { useCurrentFrame, useVideoConfig } from 'remotion';
import type { AtlasScene, AtlasStoryboard } from './schema';
import type { ThemeName } from './theme';
import { themes } from './theme';

export interface SceneContextValue {
  storyboard: AtlasStoryboard;
  scene: AtlasScene;
  index: number;
  /** Segundos absolutos (desde el inicio del vídeo) en que empieza y acaba la escena. */
  start: number;
  end: number;
  /** Escena anterior, para entradas 'continuous'. */
  previous: AtlasScene | null;
}

export const SceneContext = createContext<SceneContextValue | null>(null);

export const useScene = (): SceneContextValue => {
  const value = useContext(SceneContext);
  if (!value) throw new Error('useScene() fuera de una escena Atlas');
  return value;
};

/** Tiempo absoluto del vídeo, en segundos, dentro de una escena (compatible con `sec(at)`). */
export const useAtlasTime = (): number => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { start } = useScene();
  return start + frame / fps;
};

export const useTheme = (): { name: ThemeName; tokens: (typeof themes)[ThemeName] } => {
  const { scene } = useScene();
  return { name: scene.theme, tokens: themes[scene.theme] };
};
