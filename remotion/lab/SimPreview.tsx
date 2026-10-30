// The program's simulation shots (SimScene) over a voice, without the rest of the documentary: to look at how a
// script's scenes come out. Props: {audio, duration, groups: [{from, durationInFrames, graphic}]} as timeline.json has them.
import type {FC} from 'react';
import {AbsoluteFill, Audio, Sequence, staticFile} from 'remotion';
import '../theme';
import type {SimGraphic} from '../graphics';
import {SimScene} from '../components/graphics/SimScene';

export type SimPreviewProps = {audio: string; duration: number; groups: {from: number; durationInFrames: number; graphic: SimGraphic}[]};

export const SimPreview: FC<SimPreviewProps> = ({audio, groups}) => (
  <AbsoluteFill style={{backgroundColor: '#0b1020'}}>
    {audio && <Audio src={staticFile(audio)} />}
    {groups.map((g, i) => (
      <Sequence key={i} from={g.from} durationInFrames={g.durationInFrames}>
        <SimScene graphic={g.graphic} durationInFrames={g.durationInFrames} />
      </Sequence>
    ))}
  </AbsoluteFill>
);
