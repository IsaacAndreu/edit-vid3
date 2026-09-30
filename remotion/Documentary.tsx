import type { FC } from 'react';
import { AbsoluteFill, Sequence } from 'remotion';
import { AudioBed } from './components/AudioBed';
import { BRoll } from './components/BRoll';
import { Chapter } from './components/Chapter';
import { CreditBadge } from './components/CreditBadge';
import { CutMotion } from './components/CutMotion';
import { EndScreen } from './components/EndScreen';
import { GraphicScene } from './components/graphics/GraphicScene';
import { FramedCard } from './components/FramedCard';
import { LowerThird } from './components/LowerThird';
import { ParallaxPhoto } from './components/ParallaxPhoto';
import { PersonCard } from './components/PersonCard';
import { DataCard, SplitPanel } from './components/Panel';
import { Question } from './components/Question';
import { Stat } from './components/Stat';
import { applyBrand, theme } from './theme';
import type { Shot, TimelineProps } from './types';

/** What fills the frame under the overlays for one shot. */
const ShotBackground: FC<{ shot: Shot }> = ({ shot }) => {
  if (shot.type === 'endscreen') {
    return null; // drawn on its own layer, with the localised words
  }
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
  if (shot.media.layout === 'person') {
    return <PersonCard media={shot.media} durationInFrames={shot.durationInFrames} />;
  }
  if (shot.media.layout === 'parallax') {
    return <ParallaxPhoto media={shot.media} durationInFrames={shot.durationInFrames} seed={shot.id} />;
  }
  if (shot.media.layout === 'card') {
    return <FramedCard media={shot.media} durationInFrames={shot.durationInFrames} />;
  }
  return <BRoll media={shot.media} durationInFrames={shot.durationInFrames} seed={shot.id} />;
};

/**
 * Layers, bottom to top: shot footage/panel background → data groups (stat, datacard, split)
 * spanning their shots, question panels → lower-third labels → chapter titles → source credit → audio.
 */
/** "Fuente: X" → "Source: X" in dubbed versions (the data always keeps the Spanish prefix). */
export const localCredit = (credit: string, source?: string): string =>
  source && credit.startsWith('Fuente: ') ? `${source}: ${credit.slice('Fuente: '.length)}` : credit;

export const Documentary: FC<TimelineProps> = (props) => {
  applyBrand(props.brand);
  return <DocumentaryBody {...props} />;
};

const DocumentaryBody: FC<TimelineProps> = ({ shots, groups, labels = [], audio, locale, transitions = [], shakes = [] }) => (
  <AbsoluteFill style={{ backgroundColor: '#000' }}>
    <CutMotion transitions={transitions} shakes={shakes}>
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
        {group.kind === 'graphic' && group.graphic ? (
          <GraphicScene graphic={group.graphic} durationInFrames={group.durationInFrames} />
        ) : null}
        {group.kind === 'question' && group.words ? (
          <Question words={group.words} durationInFrames={group.durationInFrames} instant={group.id === 'q-open'} />
        ) : null}
      </Sequence>
    ))}
    </CutMotion>
    {labels.map((label, i) => (
      <Sequence key={`label-${i}`} from={label.from} durationInFrames={label.durationInFrames} name={`label ${label.text}`}>
        <LowerThird kind={label.kind} text={label.text} durationInFrames={label.durationInFrames} />
      </Sequence>
    ))}
    {shots
      .filter((shot) => shot.type === 'chapter' && shot.chapterTitle)
      .map((shot) => (
        <Sequence key={`chapter-${shot.id}`} from={shot.from} durationInFrames={shot.durationInFrames}>
          <Chapter title={shot.chapterTitle as string} number={shot.chapterNumber} word={locale?.chapter} />
        </Sequence>
      ))}
    {shots
      .filter((shot) => shot.type === 'endscreen')
      .map((shot) => (
        <Sequence key={`end-${shot.id}`} from={shot.from} durationInFrames={shot.durationInFrames}>
          <EndScreen next={locale?.next} subscribe={locale?.subscribe} />
        </Sequence>
      ))}
    {shots
      .filter((shot) => shot.media?.credit)
      // footage hidden under a full-screen graphic does not get its source badge
      .filter((shot) => !groups.some((g) => g.kind === 'graphic' && g.from <= shot.from && shot.from < g.from + g.durationInFrames))
      .map((shot) => (
        <Sequence key={`credit-${shot.id}`} from={shot.from} durationInFrames={shot.durationInFrames}>
          <CreditBadge credit={localCredit(shot.media?.credit as string, locale?.source)} />
        </Sequence>
      ))}
    <AudioBed audio={audio} />
  </AbsoluteFill>
);
