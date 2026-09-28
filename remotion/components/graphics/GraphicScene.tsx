import type { FC } from 'react';
import type { Graphic } from '../../graphics';
import { Chart } from './Chart';
import { Compare } from './Compare';
import { Kinetic } from './Kinetic';
import { MapScene } from './MapScene';
import { RankCard } from './RankCard';
import { SpecCard } from './SpecCard';
import { TimelineScene } from './Timeline';

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
    default:
      return null;
  }
};
