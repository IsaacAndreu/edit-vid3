import {Composition} from 'remotion';
import {DURATION, FPS, RaceReplay} from './RaceReplay';

export const LabRoot = () => (
  <Composition id="RaceReplay" component={RaceReplay} durationInFrames={DURATION} fps={FPS} width={1920} height={1080} />
);
