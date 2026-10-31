// Lights against a roundabout with the same cars (junction.ts): the split moves to the side the voice talks about.
import type {FC} from 'react';
import {Easing, interpolate} from 'remotion';
import {CrucesView, LAYOUTS} from '../Cruces';
import {params, signalChanges} from '../junction';
import {clamp, param, type World, type WorldProps} from '../world';
import {addWords, tx} from '../i18n';
import {C} from '../hud';
import {LineChart} from '../scenes';
import CURVES from '../curves.json';

const paramsOf = (g: WorldProps['g']) => params({demand: param(g, 'demand', 0.15), green: param(g, 'green', 22)});

const Base: FC<WorldProps> = ({g, local, length, worldT, move, o}) => {
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

addWords({
  trafficCurve: {es: 'Espera media por coche según el tráfico', pt: 'Espera média por carro conforme o trânsito', fr: 'Attente moyenne par voiture selon le trafic', de: 'Mittlere Wartezeit je nach Verkehr', en: 'Average wait per car by traffic'},
  carsPerSecond: {es: 'coches por segundo y calle', pt: 'carros por segundo e rua', fr: 'voitures par seconde et rue', de: 'Autos pro Sekunde und Straße', en: 'cars a second per street'},
  greenCurve: {es: 'Espera en el semáforo según los segundos de verde', pt: 'Espera no semáforo conforme os segundos de verde', fr: 'Attente au feu selon la durée du vert', de: 'Wartezeit an der Ampel je nach Grünphase', en: 'Wait at the lights by seconds of green'},
  greenSeconds: {es: 'segundos de verde', pt: 'segundos de verde', fr: 'secondes de vert', de: 'Sekunden Grün', en: 'seconds of green'},
  crossOver: {es: 'Aquí ganan los semáforos', pt: 'Aqui ganham os semáforos', fr: 'Ici, les feux gagnent', de: 'Hier gewinnt die Ampel', en: 'Here the lights win'},
  waitWord: {es: 'espera', pt: 'espera', fr: 'attente', de: 'Wartezeit', en: 'wait'},
});

const View: FC<WorldProps> = (props) => {
  const {g, worldT} = props;
  const scene = param<string>(g, 'scene', 'comparar');
  if (scene === 'trafico') {
    const rows = CURVES.junction as number[][];
    return <LineChart t={worldT} draw={3} x={[0.05, 0.3]} y={[0, 20]} title={tx('trafficCurve')} xLabel={tx('carsPerSecond')} yLabel={tx('waitWord')}
                      xFmt={(v) => v.toFixed(2).replace('.', ',')} yFmt={(v) => `${v} s`} xTicks={[0.05, 0.1, 0.15, 0.2, 0.25, 0.3]} yTicks={[5, 10, 15, 20]}
                      marker={{x: 0.19, label: tx('crossOver')}}
                      series={[{name: tx('lights'), colour: C.red, pts: rows.map((r) => [r[0], r[1]] as [number, number])},
                               {name: tx('roundabout'), colour: C.green, pts: rows.map((r) => [r[0], r[2]] as [number, number])}]} />;
  }
  if (scene === 'verde') {
    return <LineChart t={worldT} draw={3} x={[10, 60]} y={[0, 25]} title={tx('greenCurve')} xLabel={tx('greenSeconds')} yLabel={tx('waitWord')}
                      yFmt={(v) => `${v} s`} xTicks={[10, 20, 30, 40, 50, 60]} yTicks={[5, 10, 15, 20, 25]}
                      series={[{name: tx('lights'), colour: C.red, pts: CURVES.green as [number, number][]}]} />;
  }
  return <Base {...props} />;
};

export const cruces: World = {View, sounds};
