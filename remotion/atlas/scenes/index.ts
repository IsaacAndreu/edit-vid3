/**
 * Registro propio de escenas Atlas (separado de templates/registry.ts, que es de YoutubeVideo).
 * Cada fase añade aquí sus componentes; la clave coincide con `type` en schema.ts.
 */
import type { FC } from 'react';
import type { SceneType } from '../schema';
import { BlankScene } from './BlankScene';
import {
  AgendaScene,
  CardRowScene,
  ChapterCardScene,
  ChecklistScene,
  CtaScene,
  RecapScene,
  StatementScene,
  TitleOverlayScene,
} from './text';
import { ReliefMapScene } from './relief';
import { ElevationProfileScene } from './profile';
import { GlobeScene } from './globe';
import { Terrain3dScene } from './terrain3d';
import { DiagramScene } from './diagram';
import { AircraftScene, CockpitScene, FlightProfileScene, KnownScene } from './flight';
import { BarCompareScene, DialScene, DotDensityScene, RunwayCompareScene } from './charts';

export const atlasScenes: Partial<Record<SceneType, FC>> = {
  'atlas-blank': BlankScene,
  'atlas-chapter-card': ChapterCardScene,
  'atlas-agenda': AgendaScene,
  'atlas-title-overlay': TitleOverlayScene,
  'atlas-statement': StatementScene,
  'atlas-card-row': CardRowScene,
  'atlas-checklist': ChecklistScene,
  'atlas-recap': RecapScene,
  'atlas-cta': CtaScene,
  'atlas-dial': DialScene,
  'atlas-bar-compare': BarCompareScene,
  'atlas-dot-density': DotDensityScene,
  'atlas-runway-compare': RunwayCompareScene,
  'atlas-relief-map': ReliefMapScene,
  'atlas-elevation-profile': ElevationProfileScene,
  'atlas-globe': GlobeScene,
  'atlas-terrain-3d': Terrain3dScene,
  'atlas-diagram': DiagramScene,
  'atlas-flight-profile': FlightProfileScene,
  'atlas-cockpit': CockpitScene,
  'atlas-aircraft': AircraftScene,
  'atlas-known': KnownScene,
};
