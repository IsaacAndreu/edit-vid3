import type { FC } from 'react';
import { Composition } from 'remotion';
import { Documentary } from './Documentary';
import type { TimelineProps } from './types';

const empty: TimelineProps = {
  slug: 'empty',
  title: '',
  fps: 30,
  width: 1920,
  height: 1080,
  durationInFrames: 30,
  shots: [],
  groups: [],
  audio: { voice: '', musicVolume: 0, duckedVolume: 0, speech: [], sfx: [] },
};

/** Props = work/<slug>/timeline.json; render with --public-dir=work/<slug>. */
export const RemotionRoot: FC = () => (
  <Composition
    id="Documentary"
    component={Documentary}
    defaultProps={empty}
    durationInFrames={30}
    fps={30}
    width={1920}
    height={1080}
    calculateMetadata={({ props }) => ({
      durationInFrames: Math.max(1, props.durationInFrames),
      fps: props.fps,
      width: props.width,
      height: props.height,
    })}
  />
);
