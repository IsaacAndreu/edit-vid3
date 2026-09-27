import type { FC } from 'react';
import { Audio, Sequence, interpolate, staticFile } from 'remotion';
import type { AudioSpec } from '../types';

const RAMP = 8; // frames to fade the music down/up around speech

/** Narration + optional music ducked under the voice + optional SFX. Clip audio is muted, except the
 *  cold-open clips, which play their original sound before the narration starts. */
export const AudioBed: FC<{ audio: AudioSpec }> = ({ audio }) => {
  const musicVolume = (frame: number): number => {
    // Distance (in frames) to the nearest speech segment → 0 inside speech.
    let distance = Infinity;
    for (const [from, to] of audio.speech) {
      if (frame >= from && frame < to) return audio.duckedVolume;
      distance = Math.min(distance, frame < from ? from - frame : frame - to + 1);
    }
    return interpolate(distance, [0, RAMP], [audio.duckedVolume, audio.musicVolume], { extrapolateRight: 'clamp' });
  };
  return (
    <>
      <Sequence from={audio.voiceFrom ?? 0} layout="none">
        <Audio src={staticFile(audio.voice)} />
      </Sequence>
      {(audio.clips ?? []).map((c, i) => (
        <Sequence key={`clip-${i}`} from={c.from} durationInFrames={c.durationInFrames} layout="none">
          <Audio src={staticFile(c.src)} volume={c.volume ?? 1} />
        </Sequence>
      ))}
      {audio.music ? <Audio src={staticFile(audio.music)} loop volume={musicVolume} /> : null}
      {audio.sfx.map((s, i) => (
        <Sequence key={`${s.src}-${i}`} from={s.from} durationInFrames={90} layout="none">
          <Audio src={staticFile(s.src)} volume={s.volume} />
        </Sequence>
      ))}
    </>
  );
};
