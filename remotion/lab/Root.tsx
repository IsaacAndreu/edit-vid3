import {Composition} from 'remotion';
import {DURATION, FPS, RaceReplay} from './RaceReplay';
import {DURATION as JAM_DURATION, RingJam} from './RingJam';

export const LabRoot = () => (
  <>
    <Composition id="RaceReplay" component={RaceReplay} durationInFrames={DURATION} fps={FPS} width={1920} height={1080} />
    <Composition id="RingJam" component={RingJam} durationInFrames={JAM_DURATION} fps={FPS} width={1920} height={1080} />
  </>
);
