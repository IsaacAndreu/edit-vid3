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
  board?: boolean; // a shot with no footage: the words on the channel canvas (chalkboard) instead of over video
}

export interface ScoreGraphic {
  type: 'score';
  name?: string | null;
  title?: string | null;
  d: number;
  e: number;
  penalty?: number | null;
  total: number;
  labels: { d: string; e: string; penalty: string; total: string };
}

export interface PressGraphic {
  type: 'press';
  items: { outlet?: string | null; headline: string; date?: string | null; highlight?: string | null }[];
}

export interface RuleGraphic {
  type: 'rule';
  source: string; // "CÓDIGO DE PUNTUACIÓN" or the generic "REGLAMENTO"
  article?: string | null;
  text: string;
  highlight?: string | null; // part of text swept with the marker
  stamp?: string | null; // "PROHIBIDO": slammed over the page
}

export interface SplitGraphic {
  type: 'split';
  title?: string | null;
  left: CompareSide;
  right: CompareSide;
}

export interface BannedGraphic {
  type: 'banned';
  name: string;
  number?: number | null;
  who?: string | null;
  reason?: string | null;
  since?: string | null; // "DESDE 2017"
  stamp: string;
  media?: Media | null;
}

export interface SpotlightGraphic {
  type: 'spotlight';
  name: string;
  still: Media; // the frozen frame, full screen
  cutout: Media; // the same frame with only the person (transparent PNG)
  anchor: [number, number]; // centre-x and top of the person, % of the frame
  height?: number | null; // % of the frame the person fills
}

export interface StrobeGraphic {
  type: 'strobe';
  name: string; // the move ("Mortal Yurchenko")
  note?: string | null;
  background: Media; // the scene without the athlete
  ghosts: (Media & { x: number; y: number; w: number; h: number })[]; // each position, % of the frame
}

export interface ReplayGraphic {
  type: 'replay';
  name?: string | null; // label at the key moment
  badge: string; // "REPETICIÓN"
  video: Media; // the clip with the speed ramp already applied
  track: [number, number, number, number, number][]; // [s, x, y, w, h] (% of the frame) of the athlete
  peak: number; // s of the key moment (slow motion)
}

export interface StandingsGraphic {
  type: 'standings';
  title?: string | null;
  rows: { name: string; score: string }[]; // in the order they are said; the board re-sorts itself
}

export interface PodiumGraphic {
  type: 'podium';
  title?: string | null;
  places: { place: 1 | 2 | 3; name: string; note?: string | null; media?: Media | null }[];
}

export interface RaceGraphic {
  type: 'race';
  title: string;
  unit?: string | null;
  steps: { label: string; values: Record<string, number> }[]; // bar chart race: one step per year/date
}

export interface CardGraphic {
  type: 'card';
  name: string;
  position?: string | null;
  headline: { label: string; value: string }; // the big figure on the corner
  stats: { label: string; value: string }[];
  media?: Media | null;
}

export interface ScaleGraphic {
  type: 'scale';
  title?: string | null;
  axis: 'height' | 'length';
  unit: string;
  items: { name: string; value: number; reference?: boolean }[]; // references: everyday objects for size
}

export type Graphic =
  | PodiumGraphic
  | RaceGraphic
  | CardGraphic
  | ScaleGraphic
  | StrobeGraphic
  | ReplayGraphic
  | StandingsGraphic
  | ScoreGraphic
  | PressGraphic
  | RuleGraphic
  | SplitGraphic
  | BannedGraphic
  | SpotlightGraphic
  | MapGraphic
  | RankGraphic
  | CompareGraphic
  | ChartGraphic
  | TimelineGraphic
  | SpecsGraphic
  | KineticGraphic;
