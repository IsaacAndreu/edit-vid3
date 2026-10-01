import type { FC } from 'react';
import { AbsoluteFill, Sequence, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { ArchiveFootage } from './components/ArchiveFootage';
import { AudioBed } from './components/AudioBed';
import { BRoll } from './components/BRoll';
import { Chapter } from './components/Chapter';
import { CreditBadge } from './components/CreditBadge';
import { CutMotion } from './components/CutMotion';
import { EndScreen } from './components/EndScreen';
import { FilmBurn } from './components/FilmBurn';
import { GraphicScene } from './components/graphics/GraphicScene';
import { FramedCard } from './components/FramedCard';
import { GridBackground } from './components/GridBackground';
import { LowerThird } from './components/LowerThird';
import { ParallaxPhoto } from './components/ParallaxPhoto';
import { PersonCard } from './components/PersonCard';
import { DataCard, SplitPanel } from './components/Panel';
import { Question } from './components/Question';
import { Stat } from './components/Stat';
import { applyBrand, fontFamily, theme } from './theme';
import type { Caption, Group, Shot, TimelineProps } from './types';

/** What fills the frame under the overlays for one shot. */
const ShotBackground: FC<{ shot: Shot }> = ({ shot }) => {
  if (shot.type === 'endscreen') {
    return null; // drawn on its own layer, with the localised words
  }
  if (shot.type === 'datacard') {
    return <AbsoluteFill style={{ backgroundColor: theme.panel }} />;
  }
  if (!shot.media) {
    return <GridBackground />; // a shot nothing could fill: its key words go on the channel canvas
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
  if (shot.media.layout === 'archive') {
    return <ArchiveFootage media={shot.media} seed={shot.id} />;
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

/** What a data group draws (stat, panels, animated graphic, question), in a 1920x1080 frame. */
const GroupContent: FC<{ group: Group }> = ({ group }) => (
  <>
    {group.kind === 'stat' && group.stat ? <Stat value={group.stat.value} label={group.stat.label} /> : null}
    {group.kind === 'datacard' ? <DataCard title={group.title} note={group.note} steps={group.steps} /> : null}
    {group.kind === 'split' ? <SplitPanel title={group.title} note={group.note} steps={group.steps} /> : null}
    {group.kind === 'graphic' && group.graphic ? (
      <GraphicScene graphic={group.graphic} durationInFrames={group.durationInFrames} seed={group.id} />
    ) : null}
    {group.kind === 'question' && group.words ? (
      <Question words={group.words} durationInFrames={group.durationInFrames} instant={group.id === 'q-open'} />
    ) : null}
  </>
);

export const Documentary: FC<TimelineProps> = (props) => {
  applyBrand(props.brand);
  return props.height > props.width ? <VerticalBody {...props} /> : <DocumentaryBody {...props} />;
};

/** One caption: its words pop in as the voice says them, the word being said in the accent colour. */
const CaptionChunk: FC<{ caption: Caption }> = ({ caption }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pop = spring({ frame, fps, config: { damping: 12, stiffness: 220 }, durationInFrames: 8 });
  const said = caption.words.filter((w) => w.from <= frame).length - 1;
  return (
    <div
      style={{
        position: 'absolute', left: 60, right: 60, top: '70%', display: 'flex', flexWrap: 'wrap', justifyContent: 'center',
        gap: '0 22px', transform: `scale(${0.85 + 0.15 * pop})`,
      }}
    >
      {caption.words.map((w, i) => (
        <span
          key={i}
          style={{
            fontFamily, fontWeight: 900, fontSize: 92, lineHeight: 1.08, textTransform: 'uppercase',
            color: i === said ? theme.accent : '#fff', opacity: w.from <= frame + 1 ? 1 : 0.0,
            WebkitTextStroke: '6px #000', paintOrder: 'stroke fill', textShadow: '0 8px 24px rgba(0,0,0,0.6)',
          }}
        >
          {w.text}
        </span>
      ))}
    </div>
  );
};

/**
 * Native vertical short (height > width): footage fills the tall frame, every data group (graphics, stats,
 * panels, questions) plays in a 16:9 window in the upper middle, and big captions follow the voice.
 */
const VerticalBody: FC<TimelineProps> = ({ shots, groups, captions = [], audio, locale, width, height }) => {
  const scale = width / 1920;
  const windowTop = Math.round(height * 0.36 - (1080 * scale) / 2);
  return (
    <AbsoluteFill style={{ backgroundColor: '#000' }}>
      {shots.map((shot) => (
        <Sequence key={shot.id} from={shot.from} durationInFrames={shot.durationInFrames} name={`${shot.id} ${shot.type}`}>
          {shot.media && shot.type !== 'endscreen' ? (
            <BRoll media={shot.media} durationInFrames={shot.durationInFrames} seed={shot.id} />
          ) : (
            <GridBackground />
          )}
        </Sequence>
      ))}
      {groups.map((group) => (
        <Sequence key={group.id} from={group.from} durationInFrames={group.durationInFrames} name={`${group.kind} ${group.id}`}>
          {group.kind === 'stat' && group.stat ? (
            // the giant figure fills the vertical frame's width, over the footage
            <AbsoluteFill style={{ top: '-12%' }}>
              <Stat value={group.stat.value} label={group.stat.label} />
            </AbsoluteFill>
          ) : (
          <div
            style={{
              position: 'absolute', left: 0, top: windowTop, width: 1920, height: 1080, overflow: 'hidden',
              transform: `scale(${scale})`, transformOrigin: 'top left', borderRadius: 24,
              boxShadow: group.kind === 'graphic' ? '0 30px 80px rgba(0,0,0,0.6)' : 'none',
            }}
          >
            <GroupContent group={group} />
          </div>
          )}
        </Sequence>
      ))}
      {captions.map((caption, i) => (
        <Sequence key={`cap-${i}`} from={caption.from} durationInFrames={caption.durationInFrames} name={`caption ${i}`}>
          <CaptionChunk caption={caption} />
        </Sequence>
      ))}
      {shots
        .filter((shot) => shot.media?.credit)
        .filter((shot) => !groups.some((g) => g.kind === 'graphic' && g.from <= shot.from && shot.from < g.from + g.durationInFrames))
        .map((shot) => (
          <Sequence key={`credit-${shot.id}`} from={shot.from} durationInFrames={shot.durationInFrames}>
            <CreditBadge credit={localCredit(shot.media?.credit as string, locale?.source)} />
          </Sequence>
        ))}
      <AudioBed audio={audio} />
    </AbsoluteFill>
  );
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
        <GroupContent group={group} />
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
          <FilmBurn seed={shot.id} />
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
