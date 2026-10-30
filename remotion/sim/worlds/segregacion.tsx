// Schelling's model (1971): a town of houses of two colours, mixed at random. Each family moves to a free house if
// fewer than `tolerance` of its neighbours are like it. Nobody wants to live apart — 35 % is a mild wish — and yet,
// round after round, the town splits into blocks of one colour.
import {useLayoutEffect, useRef, type FC} from 'react';
import {AbsoluteFill} from 'remotion';
import {C, Label, Panel} from '../hud';
import {addWords, tx} from '../i18n';
import {mulberry, Note, param, Spark, type World, type WorldProps} from '../world';

addWords({
  sameNeighbours: {es: 'Vecinos iguales, de media', pt: 'Vizinhos iguais, em média', fr: 'Voisins semblables, en moyenne', de: 'Gleiche Nachbarn, im Schnitt', en: 'Like neighbours, on average'},
  wantToMove: {es: 'Quieren mudarse', pt: 'Querem mudar-se', fr: 'Veulent déménager', de: 'Wollen umziehen', en: 'Want to move'},
  round: {es: 'Ronda', pt: 'Ronda', fr: 'Tour', de: 'Runde', en: 'Round'},
  schellingNote: {es: 'Modelo de Schelling (1971) · cada familia quiere que al menos el {t} % de sus vecinos sean como ella', pt: 'Modelo de Schelling (1971) · cada família quer que pelo menos {t} % dos vizinhos sejam como ela', fr: 'Modèle de Schelling (1971) · chaque famille veut au moins {t} % de voisins semblables', de: 'Schelling-Modell (1971) · jede Familie will mindestens {t} % gleiche Nachbarn', en: 'Schelling’s model (1971) · each family wants at least {t} % of its neighbours to be like it'},
});

const COLS = 48;
const ROWS = 27;
const CELL = 40;
const RATE = 1.5;                               // rounds per second of video
const ROUNDS = 80;
const EMPTY = 0;
const COLOURS = ['', '#f5a623', '#5b8def'];

type Town = {rounds: Uint8Array[]; unhappy: Uint8Array[]; share: number[]};
const TOWNS = new Map<number, Town>();

const neighbours = (grid: Uint8Array, i: number) => {
  const x = i % COLS;
  const y = Math.floor(i / COLS);
  let same = 0;
  let all = 0;
  for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) {
    if (!dx && !dy) continue;
    const nx = x + dx;
    const ny = y + dy;
    if (nx < 0 || ny < 0 || nx >= COLS || ny >= ROWS) continue;
    const v = grid[ny * COLS + nx];
    if (v !== EMPTY) {
      all++;
      if (v === grid[i]) same++;
    }
  }
  return {same, all};
};

export const schelling = (tolerance: number): Town => {
  if (TOWNS.has(tolerance)) return TOWNS.get(tolerance)!;
  const rnd = mulberry(13);
  const grid = new Uint8Array(COLS * ROWS);
  for (let i = 0; i < grid.length; i++) {
    const r = rnd();
    grid[i] = r < 0.1 ? EMPTY : r < 0.55 ? 1 : 2;
  }
  const town: Town = {rounds: [], unhappy: [], share: []};
  for (let round = 0; round < ROUNDS; round++) {
    const sad = new Uint8Array(grid.length);
    let total = 0;
    let families = 0;
    for (let i = 0; i < grid.length; i++) {
      if (grid[i] === EMPTY) continue;
      const {same, all} = neighbours(grid, i);
      families++;
      total += all ? same / all : 1;
      if (all && same / all < tolerance) sad[i] = 1;
    }
    town.rounds.push(Uint8Array.from(grid));
    town.unhappy.push(sad);
    town.share.push(total / families);
    // the unhappy move, one by one, to a free house picked at random
    // a quarter of them each round: the town changes over a minute, as the narration tells it
    const movers = [...sad.keys()].filter((i) => sad[i] && rnd() < 0.25);
    for (const i of movers) {
      const free = [];
      for (let j = 0; j < grid.length; j++) if (grid[j] === EMPTY) free.push(j);
      const j = free[Math.floor(rnd() * free.length)];
      grid[j] = grid[i];
      grid[i] = EMPTY;
    }
  }
  TOWNS.set(tolerance, town);
  return town;
};

const Houses: FC<{grid: Uint8Array; sad: Uint8Array; mark: number}> = ({grid, sad, mark}) => {
  const ref = useRef<HTMLCanvasElement>(null);
  useLayoutEffect(() => {
    const ctx = ref.current?.getContext('2d');
    if (!ctx) return;
    ctx.fillStyle = '#3c5a36';
    ctx.fillRect(0, 0, COLS * CELL, ROWS * CELL);
    for (let i = 0; i < grid.length; i++) {
      const x = (i % COLS) * CELL;
      const y = Math.floor(i / COLS) * CELL;
      ctx.fillStyle = '#4a6e3f';
      ctx.fillRect(x + 2, y + 2, CELL - 4, CELL - 4);
      if (grid[i] === EMPTY) continue;
      ctx.fillStyle = 'rgba(0,0,0,0.3)';
      ctx.fillRect(x + 9, y + 9, CELL - 14, CELL - 14);
      ctx.fillStyle = COLOURS[grid[i]];
      ctx.fillRect(x + 6, y + 6, CELL - 14, CELL - 14);
      ctx.fillStyle = 'rgba(255,255,255,0.18)';
      ctx.fillRect(x + 6, y + 6, CELL - 14, (CELL - 14) / 2);
      if (mark > 0.3 && sad[i]) {
        ctx.strokeStyle = `rgba(255,255,255,${mark})`;
        ctx.lineWidth = 3;
        ctx.strokeRect(x + 3, y + 3, CELL - 6, CELL - 6);
      }
    }
  }, [grid, sad, mark]);
  return <canvas ref={ref} width={COLS * CELL} height={ROWS * CELL} style={{position: 'absolute', left: 0, top: 0}} />;
};

const View: FC<WorldProps> = ({g, worldT, o}) => {
  const tolerance = param(g, 'tolerance', 0.35);
  const town = schelling(tolerance);
  const round = Math.max(0, Math.min(ROUNDS - 1, Math.floor(worldT * RATE) - 2));     // a second of the mixed town first
  const sad = town.unhappy[round];
  const unhappy = sad.reduce((s, v) => s + v, 0);
  return (
    <AbsoluteFill style={{background: '#3c5a36'}}>
      <Houses grid={town.rounds[round]} sad={sad} mark={o('unhappy')} />
      <AbsoluteFill style={{background: 'radial-gradient(ellipse at center, rgba(0,0,0,0) 55%, rgba(5,8,18,0.55) 100%)'}} />
      <Panel o={o('share')} style={{right: 48, top: 52, width: 460}}>
        <Label>{tx('sameNeighbours')}</Label>
        <div style={{fontSize: 56, fontWeight: 800, color: C.accent, fontVariantNumeric: 'tabular-nums'}}>{Math.round(town.share[round] * 100)} %</div>
        <Spark values={town.share.slice(0, round + 1)} total={40} max={1} color={C.accent} h={110} />
        <Label>{tx('round')} {round}</Label>
      </Panel>
      <Panel o={o('unhappy')} style={{right: 48, top: 52, width: 300}}>
        <Label>{tx('wantToMove')}</Label>
        <div style={{fontSize: 56, fontWeight: 800, fontVariantNumeric: 'tabular-nums'}}>{unhappy}</div>
        <Label>{tx('round')} {round}</Label>
      </Panel>
      <Note>{tx('schellingNote', {t: Math.round(tolerance * 100)})}</Note>
    </AbsoluteFill>
  );
};

export const segregacion: World = {View};
