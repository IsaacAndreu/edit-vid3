import type { FC, ReactNode } from 'react';
import type { Graphic } from '../../graphics';
import { Chart } from './Chart';
import { Compare } from './Compare';
import { Kinetic } from './Kinetic';
import { MapScene } from './MapScene';
import { RankCard } from './RankCard';
import { SpecCard } from './SpecCard';
import { TimelineScene } from './Timeline';
import { BannedCard } from './BannedCard';
import { Press } from './Press';
import { Article } from './Article';
import { SatelliteZoom } from './SatelliteZoom';
import { QuoteOverlay } from './QuoteOverlay';
import { RulePage } from './RulePage';
import { Cita } from './Cita';
import { Score } from './Score';
import { Split } from './Split';
import { Spotlight } from './Spotlight';
import { Replay } from './Replay';
import { Standings } from './Standings';
import { Strobe } from './Strobe';
import { PlayerCard } from './PlayerCard';
import { Podium } from './Podium';
import { Race } from './Race';
import { Scale } from './Scale';
import { Iceberg } from './Iceberg';
import { Receipt } from './Receipt';
import { TierList } from './TierList';
import { Search } from './Search';
import { Marker } from './Marker';
import { Lens } from './Lens';
import { Scroll } from './Scroll';
import { News } from './News';
import { Poster } from './Poster';
import { PinMap } from './PinMap';
import { Earth3D } from './Earth3D';
import { Bars3D } from './Bars3D';
import { Board } from './Board';
import { Post } from './Post';
import { GraphicFrame } from './GraphicFrame';
import { Grain } from './Paper';
import { AbsoluteFill, interpolate, useCurrentFrame } from 'remotion';

// The paper graphics bring their own look (texture, light, camera): a plain fade instead of the channel's pack
const PAPER = new Set(['search', 'marker', 'lens', 'scroll', 'news', 'poster', 'board', 'post']);

const Fade: FC<{ durationInFrames: number; children: ReactNode }> = ({ durationInFrames, children }) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 6, durationInFrames - 6, durationInFrames], [0, 1, 1, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  return <AbsoluteFill style={{ opacity }}>{children}</AbsoluteFill>;
};

/** Full-screen animated graphic of any kind, brought in and out the channel's way (GraphicFrame). */
export const GraphicScene: FC<{ graphic: Graphic; durationInFrames: number; seed?: string }> = ({ graphic, durationInFrames, seed }) =>
  graphic.type === 'quote' ? (
    // subtitles over a real statement: no entrance, the clip itself is the picture
    <QuoteOverlay graphic={graphic} durationInFrames={durationInFrames} />
  ) : PAPER.has(graphic.type) || (graphic.type === 'map' && graphic.style === 'pins') ? (
    <Fade durationInFrames={durationInFrames}>
      <GraphicBody graphic={graphic} durationInFrames={durationInFrames} />
    </Fade>
  ) : (
    <GraphicFrame durationInFrames={durationInFrames} seed={seed || graphic.type}>
      <GraphicBody graphic={graphic} durationInFrames={durationInFrames} />
      {/* a little film grain on every graphic: flat vector screens read as cheap next to the footage */}
      <Grain opacity={0.07} id={`grain-${seed || graphic.type}`} />
    </GraphicFrame>
  );

const GraphicBody: FC<{ graphic: Graphic; durationInFrames: number }> = ({ graphic, durationInFrames }) => {
  switch (graphic.type) {
    case 'map':
      return graphic.globe && graphic.earth ? (
        <Earth3D graphic={graphic} durationInFrames={durationInFrames} />
      ) : graphic.style === 'pins' && (graphic.points || []).length ? (
        <PinMap graphic={graphic} durationInFrames={durationInFrames} />
      ) : (
        <MapScene graphic={graphic} durationInFrames={durationInFrames} />
      );
    case 'search':
      return <Search graphic={graphic} durationInFrames={durationInFrames} />;
    case 'marker':
      return <Marker graphic={graphic} durationInFrames={durationInFrames} />;
    case 'lens':
      return <Lens graphic={graphic} durationInFrames={durationInFrames} />;
    case 'scroll':
      return <Scroll graphic={graphic} durationInFrames={durationInFrames} />;
    case 'news':
      return <News graphic={graphic} durationInFrames={durationInFrames} />;
    case 'poster':
      return <Poster graphic={graphic} durationInFrames={durationInFrames} />;
    case 'board':
      return <Board graphic={graphic} durationInFrames={durationInFrames} />;
    case 'post':
      return <Post graphic={graphic} durationInFrames={durationInFrames} />;
    case 'rank':
      return <RankCard graphic={graphic} durationInFrames={durationInFrames} />;
    case 'compare':
      return <Compare graphic={graphic} durationInFrames={durationInFrames} />;
    case 'chart':
      return graphic.three && graphic.chart === 'bar' ? (
        <Bars3D graphic={graphic} durationInFrames={durationInFrames} />
      ) : <Chart graphic={graphic} durationInFrames={durationInFrames} />;
    case 'timeline':
      return <TimelineScene graphic={graphic} durationInFrames={durationInFrames} />;
    case 'specs':
      return <SpecCard graphic={graphic} durationInFrames={durationInFrames} />;
    case 'kinetic':
      return <Kinetic graphic={graphic} durationInFrames={durationInFrames} />;
    case 'score':
      return <Score graphic={graphic} durationInFrames={durationInFrames} />;
    case 'satellite':
      return <SatelliteZoom graphic={graphic} durationInFrames={durationInFrames} />;
    case 'article':
      return <Article graphic={graphic} durationInFrames={durationInFrames} />;
    case 'press':
      return <Press graphic={graphic} durationInFrames={durationInFrames} />;
    case 'rule':
      return <RulePage graphic={graphic} durationInFrames={durationInFrames} />;
    case 'cita':
      return <Cita graphic={graphic} durationInFrames={durationInFrames} />;
    case 'split':
      return <Split graphic={graphic} durationInFrames={durationInFrames} />;
    case 'banned':
      return <BannedCard graphic={graphic} durationInFrames={durationInFrames} />;
    case 'spotlight':
      return <Spotlight graphic={graphic} durationInFrames={durationInFrames} />;
    case 'strobe':
      return <Strobe graphic={graphic} durationInFrames={durationInFrames} />;
    case 'replay':
      return <Replay graphic={graphic} durationInFrames={durationInFrames} />;
    case 'standings':
      return <Standings graphic={graphic} durationInFrames={durationInFrames} />;
    case 'podium':
      return <Podium graphic={graphic} durationInFrames={durationInFrames} />;
    case 'race':
      return <Race graphic={graphic} durationInFrames={durationInFrames} />;
    case 'card':
      return <PlayerCard graphic={graphic} durationInFrames={durationInFrames} />;
    case 'scale':
      return <Scale graphic={graphic} durationInFrames={durationInFrames} />;
    case 'tier':
      return <TierList graphic={graphic} durationInFrames={durationInFrames} />;
    case 'iceberg':
      return <Iceberg graphic={graphic} durationInFrames={durationInFrames} />;
    case 'receipt':
      return <Receipt graphic={graphic} durationInFrames={durationInFrames} />;
    default:
      return null;
  }
};
