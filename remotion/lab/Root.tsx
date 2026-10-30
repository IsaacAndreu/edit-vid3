import {Composition} from 'remotion';
import {Cruces, FPS as CRUCES_FPS, type CrucesProps} from './Cruces';
import {DURATION, FPS, RaceReplay} from './RaceReplay';
import {DURATION as JAM_DURATION, RingJam} from './RingJam';

const SAMPLE: CrucesProps = {audio: 'voz.mp3', duration: 10, scenes: [{text: '', start: 0, end: 10, focus: 'both', overlay: 'labels'}]};

export const LabRoot = () => (
  <>
    <Composition id="RaceReplay" component={RaceReplay} durationInFrames={DURATION} fps={FPS} width={1920} height={1080} />
    <Composition id="RingJam" component={RingJam} durationInFrames={JAM_DURATION} fps={FPS} width={1920} height={1080} />
    {/* narrated: out/<test>/escenas.json (voice timings + what each line shows) with --props, the voice in --public-dir */}
    <Composition id="Cruces" component={Cruces} defaultProps={SAMPLE} fps={CRUCES_FPS} width={1920} height={1080} durationInFrames={300}
                 calculateMetadata={({props}) => ({durationInFrames: Math.ceil(props.duration * CRUCES_FPS)})} />
  </>
);
