import type { FC } from 'react';
import { AbsoluteFill } from 'remotion';

/** Lienzo vacío: el fondo, el HUD y las superposiciones los pone AtlasVideo. */
export const BlankScene: FC = () => <AbsoluteFill />;
