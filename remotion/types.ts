import type { Graphic } from './graphics';
import type { Brand } from './theme';
import type { Shake, Transition } from './components/CutMotion';

export type ShotType = 'broll' | 'datacard' | 'stat' | 'chapter' | 'split' | 'endscreen';
export type Sign = 'positive' | 'negative' | 'neutral';

export interface Media {
  src: string; // relative to the public dir (work/<slug>/)
  kind: 'video' | 'image';
  source: string;
  credit?: string | null;
  layout?: 'full' | 'card' | 'person' | 'parallax' | 'archive';
  caption?: string | null; // person cards: the name
  width?: number | null;
  height?: number | null;
  focus?: [number, number] | null; // graphics: centre of the face (% of width, % of height) to crop around
  seconds?: number | null; // clips inside graphics: their length, to slow them down or loop them
  zoom?: [number, number, number] | null; // [start frame in the shot, frames, final scale]: ease-out push-in, then hold
  rate?: number | null; // playback speed < 1 when the shot outlasts its clip
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
  coldOpen?: boolean;
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

export interface Caption {
  from: number;
  durationInFrames: number;
  words: QuestionWord[]; // "from" relative to the caption
}

export interface QuestionWord {
  text: string;
  from: number; // relative to the group: when the voice says it
}

export interface Group {
  id: string;
  kind: 'datacard' | 'split' | 'stat' | 'question' | 'graphic';
  from: number;
  durationInFrames: number;
  title?: string | null;
  note?: string | null;
  steps: PanelStep[];
  stat?: { value: string; label: string; sign: Sign } | null;
  words?: QuestionWord[];
  graphic?: Graphic | null;
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

export interface ClipAudio {
  src: string;
  from: number;
  durationInFrames: number;
  volume?: number;
  fade?: boolean; // sound bites: short fade in/out
}

export interface AudioSpec {
  voice: string;
  voiceFrom?: number;
  clips?: ClipAudio[];
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
  captions?: Caption[]; // native vertical shorts: big captions, a few words at a time
  audio: AudioSpec;
  locale?: { chapter?: string; source?: string; next?: string; subscribe?: string };
  brand?: Brand | null;
  transitions?: Transition[];
  shakes?: Shake[];
  [key: string]: unknown;
}
