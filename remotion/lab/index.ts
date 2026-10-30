// Formats being tried out, outside the documentary pipeline: npx remotion render remotion/lab/index.ts RaceReplay out.mp4
import {registerRoot} from 'remotion';
import {LabRoot} from './Root';

registerRoot(LabRoot);
