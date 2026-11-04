import type { FC } from 'react';
import { AbsoluteFill, interpolate, Sequence, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { ArchiveFootage } from './components/ArchiveFootage';
import { AudioBed } from './components/AudioBed';
import { BRoll } from './components/BRoll';
import { Chapter } from './components/Chapter';
import { CreditBadge } from './components/CreditBadge';
import { CutMotion } from './components/CutMotion';
import { EndScreen } from './components/EndScreen';
import { FilmBurn } from './components/FilmBurn';
import { FilmFinish } from './components/FilmFinish';
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
import type { SimGraphic } from './graphics';
import { verticalOf } from './sim/vertical';

/** A shot's footage; a piece of a split shot (render) plays from `offset` frames into the whole shot. */
const ShotLayer: FC<{ shot: Shot }> = ({ shot }) =>
  shot.offset ? (
    <Sequence from={-shot.offset} name={`${shot.id} +${shot.offset}`}>
      <ShotBackground shot={{ ...shot, durationInFrames: shot.fullDuration ?? shot.durationInFrames + shot.offset }} />
    </Sequence>
  ) : (
    <ShotBackground shot={shot} />
  );

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

/** Questions are see-through text: drawn after the rest, so a simulation running under one stays visible. */
const onTop = (groups: Group[]): Group[] => [
  ...groups.filter((g) => g.kind !== 'question'), ...groups.filter((g) => g.kind === 'question'),
];

/** A simulation shot in a vertical frame (sim/vertical.ts): two stacked halves, or enlarged around what matters. */
const SimVertical: FC<{ group: Group; width: number; height: number }> = ({ group, width, height }) => {
  const v = verticalOf(group.graphic as unknown as SimGraphic);
  if (v.mode === 'halves') {
    // each half covers its half of the phone, edge to edge (a little cut above and below), a thin line between them
    const slot = height / 2;
    const k = Math.max(width / 960, slot / 1080);
    const dx = (960 * k - width) / 2;
    const dy = (1080 * k - slot) / 2;
    return (
      <AbsoluteFill style={{ backgroundColor: '#0b1020' }}>
        {[0, 1].map((half) => (
          <div key={half} style={{ position: 'absolute', left: 0, top: half * slot, width, height: slot, overflow: 'hidden',
                                   borderTop: half ? '4px solid #0b1020' : 'none' }}>
            <div style={{ position: 'absolute', left: -half * 960 * k - dx, top: -dy, width: 1920, height: 1080, transform: `scale(${k})`, transformOrigin: 'top left' }}>
              <GroupContent group={group} />
            </div>
          </div>
        ))}
      </AbsoluteFill>
    );
  }
  // the whole height of the phone, centred on what matters (cx, cy): the animation, edge to edge
  const k = v.scale < 1 ? v.scale : Math.max(v.scale, height / 1080);      // a chart (scale < 1) stays whole
  const h = 1080 * k;
  const top = Math.min(0, Math.max(height - h, height / 2 - v.cy * k));
  const x = Math.max(0, Math.min(1920 * k - width, v.cx * k - width / 2));
  return (
    <AbsoluteFill style={{ backgroundColor: '#0b1020' }}>
      <div style={{ position: 'absolute', left: 0, top, width, height: Math.max(h, height), overflow: 'hidden' }}>
        <div style={{ position: 'absolute', left: -x, top: 0, width: 1920, height: 1080, transform: `scale(${k})`, transformOrigin: 'top left' }}>
          <GroupContent group={group} />
        </div>
      </div>
    </AbsoluteFill>
  );
};

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
        // in the middle of the frame: above YouTube's buttons and title at the bottom, over the seam of two halves
        position: 'absolute', left: 60, right: 60, top: '50%', display: 'flex', flexWrap: 'wrap', justifyContent: 'center',
        gap: '0 22px', transform: `translateY(-50%) scale(${0.85 + 0.15 * pop})`,
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

const STOP = new Set(['para', 'como', 'pero', 'porque', 'cuando', 'donde', 'este', 'esta', 'with', 'that', 'this',
  'from', 'what', 'have', 'they', 'were', 'your', 'mais', 'você', 'para', 'sobre', 'eine', 'einer', 'nicht', 'dass']);

/** The word to set apart: the one between *asterisks*, else a figure, else the longest word that is not a filler. */
export const keyWord = (words: string[]): number => {
  if (words.length < 2) return -1;
  const marked = words.findIndex((w) => /^\*.+\*[.,!?…:;]?$/.test(w));
  if (marked >= 0) return marked;
  const figure = words.findIndex((w) => /\d/.test(w));
  if (figure >= 0) return figure;
  let best = -1;
  words.forEach((w, i) => {
    const bare = w.replace(/[^\p{L}]/gu, '');
    if (bare.length >= 4 && !STOP.has(bare.toLowerCase()) && (best < 0 || bare.length > words[best].replace(/[^\p{L}]/gu, '').length)) best = i;
  });
  return best;
};

/**
 * The hook as kinetic type (shorts.hook_style: kinetic): big bold words that come in one after another, with the key
 * word in a serif italic of the accent colour — legible over any footage thanks to a soft dark veil on top.
 */
const KineticBanner: FC<{ text: string; frames: number; cta?: boolean }> = ({ text, frames, cta }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const words = text.split(/\s+/).filter(Boolean);
  const key = keyWord(words);
  const out = interpolate(frame, [frames - 8, frames], [1, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const step = Math.max(2, Math.min(5, Math.floor((frames * 0.35) / Math.max(1, words.length))));
  return (
    <AbsoluteFill style={{ opacity: out, pointerEvents: 'none' }}>
      <div style={{ position: 'absolute', left: 0, right: 0, top: 0, height: 760,
                    background: 'linear-gradient(180deg, rgba(0,0,0,0.8) 0%, rgba(0,0,0,0.5) 55%, rgba(0,0,0,0) 100%)' }} />
      <div style={{ position: 'absolute', left: 60, right: 60, top: 170, display: 'flex', flexWrap: 'wrap',
                    justifyContent: 'center', columnGap: 22, rowGap: 0, textAlign: 'center' }}>
        {cta ? (
          <span style={{ fontSize: 70, marginRight: 4, color: theme.accent, transform: `scale(${spring({ frame, fps, durationInFrames: 12 })})` }}>▶</span>
        ) : null}
        {words.map((raw, i) => {
          const local = frame - i * step;
          const pop = spring({ frame: local, fps, config: { damping: 14, stiffness: 190 }, durationInFrames: 14 });
          const isKey = i === key;
          const word = raw.replace(/\*/g, '');
          return (
            <span key={i} style={{
              display: 'inline-block', opacity: Math.min(1, Math.max(0, local / 4)),
              transform: `translateY(${(1 - pop) * 34}px) scale(${0.92 + 0.08 * pop})`,
              filter: `blur(${Math.max(0, (1 - pop) * 6)}px)`,
              fontFamily: isKey ? "'DM Serif Display', serif" : fontFamily,
              fontStyle: isKey ? 'italic' : 'normal', fontWeight: isKey ? 400 : 900,
              fontSize: isKey ? 104 : 88, lineHeight: 1.1, letterSpacing: isKey ? 0 : -1,
              color: isKey ? theme.accent : '#fff', textShadow: '0 6px 28px rgba(0,0,0,0.75), 0 2px 4px rgba(0,0,0,0.6)',
            }}>
              {word}
            </span>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

/** A Short's banner on top: its hook for the first seconds, «full video on my channel» for the last ones. */
const ShortBanner: FC<{ text: string; frames: number; cta?: boolean }> = ({ text, frames, cta }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pop = spring({ frame, fps, config: { damping: 13, stiffness: 200 }, durationInFrames: 12 });
  const out = interpolate(frame, [frames - 8, frames], [1, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  return (
    <div style={{ position: 'absolute', left: 50, right: 50, top: 150, display: 'flex', justifyContent: 'center',
                  opacity: out, transform: `translateY(${(1 - pop) * -40}px) scale(${0.9 + 0.1 * pop})` }}>
      <div style={{ background: cta ? theme.accent : '#fff', color: '#0b0b0b', borderRadius: 22, padding: '18px 30px',
                    fontFamily, fontWeight: 900, fontSize: cta ? 64 : 70, lineHeight: 1.08, textAlign: 'center',
                    textTransform: 'uppercase', boxShadow: '0 18px 50px rgba(0,0,0,0.55)', maxWidth: 980 }}>
        {cta ? `▶ ${text.replace(/\*/g, '')}` : text.replace(/\*/g, '')}
      </div>
    </div>
  );
};

/**
 * Native vertical short (height > width): footage fills the tall frame, every data group (graphics, stats,
 * panels, questions) plays in a 16:9 window in the upper middle, and big captions follow the voice.
 */
const VerticalBody: FC<TimelineProps> = ({ shots, groups, captions = [], audio, locale, width, height, short, durationInFrames, fps }) => {
  const banner = Math.min(5 * fps, Math.floor(durationInFrames / 3));     // 5 s, a third of a very short one at most
  const scale = width / 1920;
  const windowTop = Math.round(height * 0.36 - (1080 * scale) / 2);
  return (
    <AbsoluteFill style={{ backgroundColor: '#000' }}>
      {shots.map((shot) => (
        <Sequence key={shot.id} from={shot.from} durationInFrames={shot.durationInFrames} name={`${shot.id} ${shot.type}`}>
          {shot.media && shot.type !== 'endscreen' ? (
            <Sequence from={-(shot.offset ?? 0)}>
              <BRoll media={shot.media} durationInFrames={shot.fullDuration ?? shot.durationInFrames} seed={shot.id} />
            </Sequence>
          ) : (
            <GridBackground />
          )}
        </Sequence>
      ))}
      {onTop(groups).map((group) => (
        <Sequence key={group.id} from={group.from} durationInFrames={group.durationInFrames} name={`${group.kind} ${group.id}`}>
          {group.kind === 'stat' && group.stat ? (
            // the giant figure fills the vertical frame's width, over the footage
            <AbsoluteFill style={{ top: '-12%' }}>
              <Stat value={group.stat.value} label={group.stat.label} />
            </AbsoluteFill>
          ) : (
          <>
          {group.graphic?.type === 'sim' ? (
            <SimVertical group={group} width={width} height={height} />
          ) : group.graphic?.type === 'cine' || group.graphic?.type === 'mapa' || group.graphic?.type === 'atlas' ? (
            // drawn for the tall frame itself (pipeline/cine.py, pipeline/mapas.py): full screen
            <GroupContent group={group} />
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
          </>
          )}
        </Sequence>
      ))}
      {theme.finish === 'cine' ? <FilmFinish /> : null}
      {captions.map((caption, i) => (
        <Sequence key={`cap-${i}`} from={caption.from} durationInFrames={caption.durationInFrames} name={`caption ${i}`}>
          <CaptionChunk caption={caption} />
        </Sequence>
      ))}
      {short?.hook ? (
        <Sequence from={0} durationInFrames={banner} name="hook">
          {short.style === 'box' ? <ShortBanner text={short.hook} frames={banner} /> : <KineticBanner text={short.hook} frames={banner} />}
        </Sequence>
      ) : null}
      {short?.cta ? (
        <Sequence from={durationInFrames - banner} durationInFrames={banner} name="full video">
          {short.style === 'box' ? <ShortBanner text={short.cta} frames={banner} cta /> : <KineticBanner text={short.cta} frames={banner} cta />}
        </Sequence>
      ) : null}
      {shots
        .filter((shot) => shot.media?.credit)
        .filter((shot) => !groups.some((g) => g.kind === 'graphic' && g.graphic?.type !== 'quote'
        && g.from <= shot.from && shot.from < g.from + g.durationInFrames))
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
        <ShotLayer shot={shot} />
      </Sequence>
    ))}
    {onTop(groups).map((group) => (
      <Sequence key={group.id} from={group.from} durationInFrames={group.durationInFrames} name={`${group.kind} ${group.id}`}>
        <GroupContent group={group} />
      </Sequence>
    ))}
    </CutMotion>
    {theme.finish === 'cine' ? <FilmFinish /> : null}
    {labels.map((label, i) => (
      <Sequence key={`label-${i}`} from={label.from} durationInFrames={label.durationInFrames} name={`label ${label.text}`}>
        <LowerThird kind={label.kind} text={label.text} durationInFrames={label.durationInFrames} />
      </Sequence>
    ))}
    {shots
      // an atlas draws its own chapter card (the paper «I — El mapa»): the generic one would cover it
      .filter((shot) => shot.type === 'chapter' && shot.chapterTitle
        && !groups.some((g) => g.graphic?.type === 'atlas' && g.from <= shot.from && shot.from < g.from + g.durationInFrames))
      .map((shot) => (
        <Sequence key={`chapter-${shot.id}`} from={shot.from} durationInFrames={shot.chapterFrames || shot.durationInFrames}>
          <Chapter title={shot.chapterTitle as string} number={shot.chapterNumber} word={locale?.chapter}
            frames={shot.chapterFrames || shot.durationInFrames} />
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
