import type { FC } from 'react';
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
import { RulePage } from './RulePage';
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

/** Full-screen animated graphic of any kind. */
export const GraphicScene: FC<{ graphic: Graphic; durationInFrames: number }> = ({ graphic, durationInFrames }) => {
  switch (graphic.type) {
    case 'map':
      return <MapScene graphic={graphic} durationInFrames={durationInFrames} />;
    case 'rank':
      return <RankCard graphic={graphic} durationInFrames={durationInFrames} />;
    case 'compare':
      return <Compare graphic={graphic} durationInFrames={durationInFrames} />;
    case 'chart':
      return <Chart graphic={graphic} durationInFrames={durationInFrames} />;
    case 'timeline':
      return <TimelineScene graphic={graphic} durationInFrames={durationInFrames} />;
    case 'specs':
      return <SpecCard graphic={graphic} durationInFrames={durationInFrames} />;
    case 'kinetic':
      return <Kinetic graphic={graphic} durationInFrames={durationInFrames} />;
    case 'score':
      return <Score graphic={graphic} durationInFrames={durationInFrames} />;
    case 'press':
      return <Press graphic={graphic} durationInFrames={durationInFrames} />;
    case 'rule':
      return <RulePage graphic={graphic} durationInFrames={durationInFrames} />;
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
