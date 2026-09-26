export type SceneType = 'hook' | 'narrative' | 'stat' | 'transition' | 'avatar';

export interface SceneProps {
  text?: string;
  imageUrl?: string;
  videoUrl?: string;
  videoDurationInSeconds?: number;
  mediaProvider?: string;
  mediaClipDurationSeconds?: number;
  mediaSourceUrl?: string;
  mediaQuery?: string;
  mediaRelevanceScore?: number;
  mediaPhotographer?: string;
  shots?: {
    url: string;
    type: 'image' | 'video';
    provider?: string;
    durationInSeconds?: number;
    sourceUrl?: string;
    photographer?: string;
    query?: string;
    relevanceScore?: number;
  }[];
  timelinePoints?: { label: string; value?: string; position: number }[];
  comparisonColumns?: { title: string; items: string[] }[];
  keywords?: string[];
  durationInFrames: number;
  accentColor: string;
  sceneType: SceneType;
}

export interface SceneInput extends SceneProps {
  templateName: string;
}

export type VideoProps = {
  scenes: SceneInput[];
  audioUrl?: string;
} & Record<string, unknown>;
