/** Iconos vectoriales genéricos del estilo (sin contenido de un vídeo concreto). */
import type { FC } from 'react';

/** Avión visto desde arriba, apuntando a la derecha, en una caja de 100×100. */
export const PLANE_TOP_PATH =
  'M97 50 C97 47 94 45.5 89 45.5 L62 45.5 L42 8 L34.5 8 L46.5 45.5 L22 45.5 L13.5 31 L8.5 31 L12.5 45.5 ' +
  'C9 46 7 48 7 50 C7 52 9 54 12.5 54.5 L8.5 69 L13.5 69 L22 54.5 L46.5 54.5 L34.5 92 L42 92 L62 54.5 ' +
  'L89 54.5 C94 54.5 97 53 97 50 Z';

export const PlaneTop: FC<{ size: number; fill: string; stroke: string; rotate?: number; x?: number; y?: number }> = ({
  size,
  fill,
  stroke,
  rotate = 0,
  x = 0,
  y = 0,
}) => (
  <g transform={`translate(${x} ${y}) rotate(${rotate}) translate(${-size / 2} ${-size / 2}) scale(${size / 100})`}>
    <path d={PLANE_TOP_PATH} fill={fill} stroke={stroke} strokeWidth={4} strokeLinejoin="round" />
  </g>
);

/** Avión de perfil, apuntando a la derecha, en una caja de 100×40 (para los perfiles de altitud). */
export const PLANE_SIDE_PATH =
  'M5 22 C5 18 10 17 20 17 L82 17 C90 17 96 19 98 21 C96 23 90 24.5 82 24.5 L20 24.5 C10 24.5 5 23.5 5 22 Z ' +
  'M8 18 L3 5 L11 5 L23 17 Z M44 21.5 L63 21.5 L51 31 L41 31 Z';
