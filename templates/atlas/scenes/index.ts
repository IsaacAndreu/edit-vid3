/**
 * Registro propio de escenas Atlas (separado de templates/registry.ts, que es de YoutubeVideo).
 * Cada fase añade aquí sus componentes; la clave coincide con `type` en schema.ts.
 */
import type { FC } from 'react';
import type { SceneType } from '../schema';
import { BlankScene } from './BlankScene';

export const atlasScenes: Partial<Record<SceneType, FC>> = {
  'atlas-blank': BlankScene,
};
