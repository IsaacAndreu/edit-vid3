import { createElement, type CSSProperties, type ComponentType } from 'react';
import KineticTextHook from './components/KineticTextHook';
import KenBurnsImage from './components/KenBurnsImage';
import BlueprintDataPanel from './components/BlueprintDataPanel';
import ComparisonPanel from './components/ComparisonPanel';
import LowerThird from './components/LowerThird';
import MultiShotMontage from './components/MultiShotMontage';
import NewsImageMontage from './components/NewsImageMontage';
import NumberCallout from './components/NumberCallout';
import StatOverlay from './components/StatOverlay';
import TimelineGraphic from './components/TimelineGraphic';
import TitleCard from './components/TitleCard';
import WhipTransition from './components/WhipTransition';
import type { SceneProps } from './types';

export type SceneTemplate = ComponentType<SceneProps>;

const placeholderStyle: CSSProperties = {
  alignItems: 'center',
  backgroundColor: '#050505',
  color: '#f9fafb',
  display: 'flex',
  flexDirection: 'column',
  fontFamily: 'Arial, sans-serif',
  gap: 16,
  height: '100%',
  justifyContent: 'center',
  padding: 64,
  textAlign: 'center',
  width: '100%',
};

const PlaceholderTemplate: SceneTemplate = ({
  text,
  accentColor,
  durationInFrames,
  sceneType,
}) =>
  createElement(
    'div',
    { style: placeholderStyle },
    createElement(
      'div',
      { style: { color: accentColor, fontSize: 32, fontWeight: 700 } },
      sceneType.toUpperCase(),
    ),
    createElement(
      'div',
      { style: { fontSize: 56, fontWeight: 700 } },
      text ?? 'Placeholder scene',
    ),
    createElement(
      'div',
      { style: { color: '#9ca3af', fontSize: 24 } },
      `${durationInFrames} frames · template placeholder`,
    ),
  );

/**
 * Add future templates here, for example:
 *
 * 'kinetic-text-hook': KineticTextHook,
 */
export const templates: Record<string, SceneTemplate> = {
  'blueprint-data-panel': BlueprintDataPanel,
  'comparison-panel': ComparisonPanel,
  'kinetic-text-hook': KineticTextHook,
  'kenburns-image': KenBurnsImage,
  'lower-third': LowerThird,
  'multi-shot-montage': MultiShotMontage,
  'news-image-montage': NewsImageMontage,
  'number-callout': NumberCallout,
  placeholder: PlaceholderTemplate,
  'stat-overlay': StatOverlay,
  'timeline-graphic': TimelineGraphic,
  'title-card': TitleCard,
  'whip-transition': WhipTransition,
};
