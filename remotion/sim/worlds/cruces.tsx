// Lights against a roundabout with the same cars (junction.ts): the split moves to the side the voice talks about.
import type {FC} from 'react';
import {Easing, interpolate} from 'remotion';
import {CrucesView, LAYOUTS} from '../Cruces';
import {params, signalChanges} from '../junction';
import {clamp, param, type World, type WorldProps} from '../world';

const paramsOf = (g: WorldProps['g']) => params({demand: param(g, 'demand', 0.15), green: param(g, 'green', 22)});

const View: FC<WorldProps> = ({g, local, length, worldT, move, o}) => {
  const a = LAYOUTS[(g.prev in LAYOUTS ? g.prev : 'both') as keyof typeof LAYOUTS];
  const b = LAYOUTS[(g.focus in LAYOUTS ? g.focus : 'both') as keyof typeof LAYOUTS];
  const mix = (x: number, y: number) => x + (y - x) * move;
  const reveal = (from: number, to: number) => (g.overlay === 'conflicts' ? interpolate(local, [length * from, length * to], [0, 1], clamp) : 0);
  return <CrucesView simT={worldT} split={mix(a.split, b.split)} left={mix(a.left, b.left)} right={mix(a.right, b.right)}
                     focus={g.focus as 'both' | 'left' | 'right'} o={o} revealLights={reveal(0.05, 0.45)} revealRound={reveal(0.55, 0.8)}
                     pathsDrawn={interpolate(local, [0.2, 1.8], [0, 1], {...clamp, easing: Easing.inOut(Easing.cubic)})} p={paramsOf(g)} />;
};

// a relay click each time the lights change, when they are in sight
const sounds = (g: WorldProps['g'], length: number) => {
  if (g.focus === 'right') return {};
  const t0 = g.at - g.since;
  return {clicks: signalChanges(t0, t0 + length, paramsOf(g).green).map((c) => c - t0)};
};

export const cruces: World = {View, sounds};
