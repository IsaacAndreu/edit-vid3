// Types of the editor's state (pipeline/editor.py) and the helpers that turn a drag into a change.

import type { TimelineProps } from '../../remotion/types';

export interface Media {
  src: string;
  kind: string;
  source: string;
  credit?: string | null;
}

export interface ShotInfo {
  id: string;
  type: string;
  from: number;
  durationInFrames: number;
  text: string;
  chapterTitle?: string | null;
  media?: Media | null;
  title?: string | null;
  channel?: string | null;
  candidateId?: string | null;
  start?: number | null;
  end?: number | null;
  decidedBy?: string | null;
  reason?: string | null;
  weak: boolean;
  swapped: boolean;
  options: number;
}

export interface Group {
  id: string;
  kind: string;
  from: number;
  durationInFrames: number;
  title?: string | null;
  note?: string | null;
  graphic?: Record<string, unknown> | null;
  stat?: Record<string, unknown> | null;
}

export interface LayoutLabel {
  kind: string;
  text: string;
  from: number;
  durationInFrames: number;
  _original?: string;
  _added?: number;
}

export interface LayoutSfx {
  src: string;
  from: number;
  volume: number;
  _key?: string;
  _added?: number;
}

export interface MusicPart {
  src: string;
  from: number;
  durationInFrames: number;
  mood: string;
}

export interface Layout {
  fps: number;
  durationInFrames: number;
  shots: { id: string; type: string; from: number; durationInFrames: number; text: string; media?: Media | null; chapterTitle?: string | null }[];
  groups: Group[];
  labels: LayoutLabel[];
  audio: { sfx: LayoutSfx[]; musicParts?: MusicPart[]; voiceFrom?: number; voiceGaps?: [number, number][] };
}

export interface Scene {
  id: string;
  title: string;
  shots: string[];
  from: number;
  to: number;
  fixed: boolean;
}

export interface Edits {
  footage: Record<string, { candidateId: string; start: number; end?: number; url?: string; title?: string; channel?: string }>;
  own: Record<string, { src: string; kind: string }>;
  media: Record<string, string>;
  cuts: Record<string, number>;
  texts: Record<string, unknown>;
  removed: string[];
  timing: Record<string, [number, number]>;
  added: Group[];
  labels: Record<string, string>;
  labelTiming: Record<string, [number, number]>;
  addedLabels: LayoutLabel[];
  music: Record<string, string>;
  sfx: { removed: string[]; moved: Record<string, number>; volume: Record<string, number>; added: LayoutSfx[] };
  order: string[];
  deleted: string[];
}

export interface Job {
  kind: string;
  running: boolean;
  ok: boolean | null;
  log: string[];
}

export interface State {
  slug: string;
  timeline: TimelineProps & { groups: Group[] };
  layout: Layout;
  shots: ShotInfo[];
  edits: Edits;
  scenes: Scene[];
  timeMap: [number, number, number][];
  words: [number, string][];
  removedGroups: { id: string; kind: string; type?: string | null; from: number; durationInFrames: number }[];
  rendered: boolean;
  job: Job;
}

export interface Option {
  index: number;
  candidateId: string;
  start: number;
  end: number;
  kind: string;
  source: string;
  title: string;
  channel: string;
  score: number;
  thumb: string;
  preview: string | null;
  previewFrom: number | null;
  previewTo: number | null;
  usedBy?: string | null; // another shot already shows it
}

export interface Template {
  type: string;
  name: string;
  seconds: number;
  data: Record<string, unknown>;
}

export interface Asset {
  src: string;
  name: string;
  mood: string;
}

export interface SearchResult {
  id: string;
  title: string;
  channel: string;
  duration: number | null;
  thumb: string;
  url: string;
}

export type Selection =
  | { kind: 'shot'; id: string }
  | { kind: 'group'; id: string }
  | { kind: 'label'; original?: string; added?: number }
  | { kind: 'sfx'; key?: string; added?: number }
  | { kind: 'music'; index: number }
  | { kind: 'scene'; id: string }
  | null;

export const api = async <T,>(path: string, body?: unknown): Promise<T> => {
  const response = await fetch(path, body === undefined ? undefined : {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error ?? response.statusText);
  }
  return data as T;
};

export const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value)) as T;

export const clock = (frame: number, fps: number) => {
  const s = Math.max(0, Math.floor(frame / fps));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
};

/** Pipeline frame → frame in the edited video (null if its scene was deleted). */
export const toView = (frame: number, map: [number, number, number][]): number | null => {
  if (!map.length) {
    return frame;
  }
  for (const [from, to, at] of map) {
    if (from <= frame && frame < to) {
      return frame - from + at;
    }
  }
  return null;
};

/** Frame in the edited video → pipeline frame. */
export const toBase = (frame: number, map: [number, number, number][]): number => {
  if (!map.length) {
    return frame;
  }
  for (const [from, to, at] of map) {
    if (at <= frame && frame < at + (to - from)) {
      return frame - at + from;
    }
  }
  return frame;
};

export const setPath = (target: Record<string, unknown>, path: string, value: unknown) => {
  const keys = path.split('.');
  let node: Record<string, unknown> | unknown[] = target;
  for (const key of keys.slice(0, -1)) {
    node = (Array.isArray(node) ? node[Number(key)] : node[key]) as Record<string, unknown>;
  }
  const last = keys[keys.length - 1];
  if (Array.isArray(node)) {
    node[Number(last)] = value;
  } else {
    node[last] = value;
  }
};

export const KIND_NAMES: Record<string, string> = {
  graphic: 'Gráfico', stat: 'Cifra grande', datacard: 'Panel de datos', split: 'Panel doble', question: 'Pregunta',
};

export const GRAPHIC_NAMES: Record<string, string> = {
  map: 'Mapa', compare: 'A vs B', chart: 'Gráfica', timeline: 'Línea de tiempo', specs: 'Ficha técnica', rank: 'Puesto',
  kinetic: 'Texto cinético', score: 'Nota', press: 'Prensa', rule: 'Reglamento', split: 'Pantalla partida',
  banned: 'Prohibido', spotlight: 'Congelado', strobe: 'Estroboscopia', replay: 'Repetición', standings: 'Marcador',
  podium: 'Podio', race: 'Carrera de barras', card: 'Carta', scale: 'Escala', tier: 'Tier list', iceberg: 'Iceberg', receipt: 'Ticket',
};

export const groupName = (g: Group) =>
  g.kind === 'graphic' ? GRAPHIC_NAMES[String(g.graphic?.type)] ?? String(g.graphic?.type) : KIND_NAMES[g.kind] ?? g.kind;
