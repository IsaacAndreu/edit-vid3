export type ShotType = 'broll' | 'datacard' | 'stat' | 'chapter' | 'split';
export type Sign = 'positive' | 'negative' | 'neutral';

export interface Media {
  src: string; // relative to the public dir (work/<slug>/)
  kind: 'video' | 'image';
  source: string;
  credit?: string | null;
  layout?: 'full' | 'card';
  width?: number | null;
  height?: number | null;
}

export interface Shot {
  id: string;
  type: ShotType;
  from: number;
  durationInFrames: number;
  text: string;
  media?: Media | null;
  chapterTitle?: string | null;
  chapterNumber?: number | null;
  groupId?: string | null;
}

export interface DataRow {
  label: string;
  value: string;
  sign: Sign;
}

export interface PanelStep {
  from: number; // relative to the group
  rows: DataRow[];
}

export interface QuestionWord {
  text: string;
  from: number; // relative to the group: when the voice says it
}

export interface Group {
  id: string;
  kind: 'datacard' | 'split' | 'stat' | 'question';
  from: number;
  durationInFrames: number;
  title?: string | null;
  note?: string | null;
  steps: PanelStep[];
  stat?: { value: string; label: string; sign: Sign } | null;
  words?: QuestionWord[];
}

export type LabelKind = 'name' | 'place' | 'date' | 'score';

export interface Label {
  kind: LabelKind;
  text: string;
  from: number;
  durationInFrames: number;
}

export interface Sfx {
  src: string;
  from: number;
  volume: number;
}

export interface AudioSpec {
  voice: string;
  music?: string | null;
  musicVolume: number;
  duckedVolume: number;
  speech: [number, number][];
  sfx: Sfx[];
}

export interface TimelineProps {
  slug: string;
  title: string;
  fps: number;
  width: number;
  height: number;
  durationInFrames: number;
  shots: Shot[];
  groups: Group[];
  labels?: Label[];
  audio: AudioSpec;
  [key: string]: unknown;
}
