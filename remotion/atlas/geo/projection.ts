/**
 * Proyección compartida entre los scripts de datos (que generan la textura ya proyectada) y la
 * escena de mapa (que dibuja vectores encima con la misma proyección). Plan §2.4.
 */
import type { GeoProjection } from 'd3-geo';
import { geoConicConformal, geoConicEqualArea, geoEquirectangular, geoMercator } from 'd3-geo';

export interface ProjectionSpec {
  type: 'conicConformal' | 'conicEqualArea' | 'mercator' | 'equirectangular';
  rotate?: [number, number] | [number, number, number];
  parallels?: [number, number];
  center?: [number, number];
  scale: number;
  translate: [number, number];
}

/** meta.json de un paquete de región (public/atlas-data/regions/<id>/meta.json). */
export interface RegionMeta {
  id: string;
  /** Tamaño en píxeles de relief.jpg; la proyección da coordenadas en ese espacio. */
  width: number;
  height: number;
  projection: ProjectionSpec;
  /** Metros por píxel en el centro (aprox.). */
  metersPerPixel: number;
  bbox: [[number, number], [number, number]];
  files: { relief: string; reliefNight: string; height: string };
  heightEncoding: { min: number; max: number; note: string };
  sources: string[];
}

export const makeProjection = (spec: Omit<ProjectionSpec, 'scale' | 'translate'> & Partial<ProjectionSpec>): GeoProjection => {
  let p: GeoProjection;
  switch (spec.type) {
    case 'conicConformal':
      p = geoConicConformal();
      break;
    case 'conicEqualArea':
      p = geoConicEqualArea();
      break;
    case 'mercator':
      p = geoMercator();
      break;
    case 'equirectangular':
      p = geoEquirectangular();
      break;
  }
  if (spec.parallels && 'parallels' in p) (p as GeoProjection & { parallels: (v: [number, number]) => GeoProjection }).parallels(spec.parallels);
  if (spec.rotate) p.rotate(spec.rotate);
  if (spec.center) p.center(spec.center);
  if (spec.scale !== undefined) p.scale(spec.scale);
  if (spec.translate) p.translate(spec.translate);
  return p.precision(0.2);
};
