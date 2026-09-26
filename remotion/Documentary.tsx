import type { FC } from 'react';
import { AbsoluteFill, Sequence } from 'remotion';
import { AudioBed } from './components/AudioBed';
import { BRoll } from './components/BRoll';
import { Chapter } from './components/Chapter';
import { CreditBadge } from './components/CreditBadge';
import { DataCard, SplitPanel } from './components/Panel';
import { Question } from './components/Question';
import { Stat } from './components/Stat';
import { theme } from './theme';
import type { Shot, TimelineProps } from './types';

/** What fills the frame under the overlays for one shot. */
const ShotBackground: FC<{ shot: Shot }> = ({ shot }) => {
  if (shot.type === 'datacard' || !shot.media) {
    return <AbsoluteFill style={{ backgroundColor: theme.panel }} />;
  }
  if (shot.type === 'split') {
    // Footage in the left half, fading into the panel colour.
    return (
      <AbsoluteFill style={{ backgroundColor: theme.panel }}>
        <AbsoluteFill style={{ width: '50%', overflow: 'hidden' }}>
          <BRoll media={shot.media} durationInFrames={shot.durationInFrames} seed={shot.id} />
          <AbsoluteFill style={{ background: `linear-gradient(90deg, rgba(26,26,26,0) 70%, ${theme.panel} 100%)` }} />
        </AbsoluteFill>
      </AbsoluteFill>
    );
  }
  return <BRoll media={shot.media} durationInFrames={shot.durationInFrames} seed={shot.id} />;
};

/**
 * Layers, bottom to top: shot footage/panel background → data groups (stat, datacard, split)
 * spanning their shots, question panels → chapter titles → source credit → audio.
 */
export const Documentary: FC<TimelineProps> = ({ shots, groups, audio }) => (
  <AbsoluteFill style={{ backgroundColor: '#000' }}>
    {shots.map((shot) => (
      <Sequence key={shot.id} from={shot.from} durationInFrames={shot.durationInFrames} name={`${shot.id} ${shot.type}`}>
        <ShotBackground shot={shot} />
      </Sequence>
    ))}
    {groups.map((group) => (
      <Sequence key={group.id} from={group.from} durationInFrames={group.durationInFrames} name={`${group.kind} ${group.id}`}>
        {group.kind === 'stat' && group.stat ? <Stat value={group.stat.value} label={group.stat.label} /> : null}
        {group.kind === 'datacard' ? <DataCard title={group.title} note={group.note} steps={group.steps} /> : null}
        {group.kind === 'split' ? <SplitPanel title={group.title} note={group.note} steps={group.steps} /> : null}
        {group.kind === 'question' && group.words ? (
          <Question words={group.words} durationInFrames={group.durationInFrames} />
        ) : null}
      </Sequence>
    ))}
    {shots
      .filter((shot) => shot.type === 'chapter' && shot.chapterTitle)
      .map((shot) => (
        <Sequence key={`chapter-${shot.id}`} from={shot.from} durationInFrames={shot.durationInFrames}>
          <Chapter title={shot.chapterTitle as string} />
        </Sequence>
      ))}
    {shots
      .filter((shot) => shot.media?.credit)
      .map((shot) => (
        <Sequence key={`credit-${shot.id}`} from={shot.from} durationInFrames={shot.durationInFrames}>
          <CreditBadge credit={shot.media?.credit as string} />
        </Sequence>
      ))}
    <AudioBed audio={audio} />
  </AbsoluteFill>
);
