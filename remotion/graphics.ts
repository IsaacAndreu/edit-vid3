// Data of the animated graphics (timeline group kind "graphic"). Each one is drawn full screen over
// the shots it spans. The pipeline fills these from the script; the Showcase composition has samples.

import type { Media } from './types';

export interface GeoPoint {
  name: string;
  lon: number;
  lat: number;
  note?: string | null; // small line under the pin label ("1.º puesto", "2019")
}

export interface MapGraphic {
  type: 'map';
  title?: string | null;
  countries?: string[]; // highlighted countries (English names, as in world-atlas)
  points?: GeoPoint[]; // pins, in the order they appear
  route?: boolean; // draw a line through the points in order (Manila → Tokyo → Paris)
  zoom?: number | null; // index of the point to zoom into at the end (country → city)
  globe?: boolean; // a rotating globe that turns to the first country/point
}

export interface RankGraphic {
  type: 'rank';
  rank: number;
  total?: number | null;
  name: string;
  subtitle?: string | null;
  media?: Media | null;
  stats?: { label: string; value: string }[];
}

export interface CompareSide {
  name: string;
  media?: Media | null;
}

export interface CompareGraphic {
  type: 'compare';
  title?: string | null;
  left: CompareSide;
  right: CompareSide;
  rows: { label: string; a: number; b: number; unit?: string | null; better?: 'high' | 'low' | null }[];
}

export interface ChartGraphic {
  type: 'chart';
  chart: 'bar' | 'line' | 'pie';
  title: string;
  unit?: string | null;
  data: { label: string; value: number }[];
  highlight?: string | null; // label to paint in the accent colour
}

export interface TimelineGraphic {
  type: 'timeline';
  title?: string | null;
  events: { year: string; text: string }[];
}

export interface SpecsGraphic {
  type: 'specs';
  kicker?: string | null; // small heading: "FICHA TÉCNICA" (products), "EN CIFRAS" (people)
  name: string;
  subtitle?: string | null;
  media?: Media | null;
  specs: { label: string; value: string; unit?: string | null }[];
}

export interface KineticGraphic {
  type: 'kinetic';
  lines: string[]; // each line appears word by word; the last word of the last line in yellow
}

export type Graphic =
  | MapGraphic
  | RankGraphic
  | CompareGraphic
  | ChartGraphic
  | TimelineGraphic
  | SpecsGraphic
  | KineticGraphic;
