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
    default:
      return null;
  }
};
