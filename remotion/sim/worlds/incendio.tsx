// A forest seen from above, cell by cell: a fire starts on the line that says so (cues.start) and spreads from tree
// to tree, more with the wind (towards the east). Below a certain density it dies out on its own (percolation);
// firebreaks — strips with no trees — stop it. Drawn on a canvas: thousands of cells every frame.
import {useLayoutEffect, useRef, type FC} from 'react';
import {AbsoluteFill} from 'remotion';
import {C} from '../hud';
import {addWords, tx} from '../i18n';
import {Big, mulberry, Note, param, type World, type WorldProps} from '../world';

addWords({
  burned: {es: 'Superficie quemada', pt: 'Área queimada', fr: 'Surface brûlée', de: 'Verbrannte Fläche', en: 'Area burned'},
  hectares: {es: 'hectáreas', pt: 'hectares', fr: 'hectares', de: 'Hektar', en: 'hectares'},
  burning: {es: 'Ardiendo ahora', pt: 'A arder agora', fr: 'En feu', de: 'Brennt gerade', en: 'Burning now'},
  startsHere: {es: 'Aquí empieza', pt: 'Começa aqui', fr: 'Ça commence ici', de: 'Hier fängt es an', en: 'It starts here'},
  firebreak: {es: 'Cortafuegos', pt: 'Aceiro', fr: 'Coupe-feu', de: 'Brandschneise', en: 'Firebreak'},
  fireNote: {es: 'Simulación · cada celda, un cuarto de hectárea · densidad del bosque {d} % · viento hacia el este', pt: 'Simulação · cada célula, um quarto de hectare · densidade da floresta {d} % · vento para leste', fr: 'Simulation · chaque case, un quart d’hectare · densité de la forêt {d} % · vent vers l’est', de: 'Simulation · jede Zelle ein Viertelhektar · Walddichte {d} % · Wind nach Osten', en: 'Simulation · each cell a quarter hectare · forest density {d} % · wind to the east'},
});

const COLS = 160;
const ROWS = 90;
const CELL = 12;                               // pixels
const RATE = 6;                                // steps per second of video
const BURN = 3;                                // steps a tree burns
const SPAN = 75 * RATE;
const GROUND = 0;
const TREE = 1;
const FIRE = 2;
const ASH = 3;
const BREAK = 4;
const ORIGIN = {x: 26, y: 45};
const BREAKS = [72, 118];                      // the firebreaks' first columns (4 cells wide)

type Run = {steps: Uint8Array[]; burned: number[]; burning: number[]};
const RUNS = new Map<string, Run>();

export const fire = (density: number, wind: number, breaks: number): Run => {
  const id = `${density}:${wind}:${breaks}`;
  if (RUNS.has(id)) return RUNS.get(id)!;
  const place = mulberry(17);
  const spread = mulberry(29);
  const grid = new Uint8Array(COLS * ROWS);
  for (let i = 0; i < grid.length; i++) grid[i] = place() < density ? TREE : GROUND;
  if (breaks) for (const b of BREAKS) for (let y = 0; y < ROWS; y++) for (let x = b; x < b + 4; x++) grid[y * COLS + x] = BREAK;
  const age = new Uint8Array(COLS * ROWS);
  const at = (x: number, y: number) => y * COLS + x;
  for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) grid[at(ORIGIN.x + dx, ORIGIN.y + dy)] = FIRE;
  const run: Run = {steps: [], burned: [], burning: []};
  for (let step = 0; step < SPAN; step++) {
    const next = Uint8Array.from(grid);
    let burning = 0;
    for (let y = 0; y < ROWS; y++) for (let x = 0; x < COLS; x++) {
      const i = at(x, y);
      if (grid[i] !== FIRE) continue;
      burning++;
      for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) {
        if (!dx && !dy) continue;
        const nx = x + dx;
        const ny = y + dy;
        if (nx < 0 || ny < 0 || nx >= COLS || ny >= ROWS || grid[at(nx, ny)] !== TREE) continue;
        const base = dx && dy ? 0.16 : 0.4;
        const blow = dx > 0 ? 1 + 1.2 * wind : dx < 0 ? 1 - 0.7 * wind : 1;
        if (spread() < base * blow) next[at(nx, ny)] = FIRE;
      }
      age[i]++;
      if (age[i] >= BURN) next[i] = ASH;
    }
    grid.set(next);
    let ash = 0;
    for (let i = 0; i < grid.length; i++) if (grid[i] === ASH || grid[i] === FIRE) ash++;
    run.steps.push(Uint8Array.from(grid));
    run.burned.push(ash);
    run.burning.push(burning);
  }
  RUNS.set(id, run);
  return run;
};

const paramsOf = (g: WorldProps['g']) => [param(g, 'density', 0.62), param(g, 'wind', 0.4), param(g, 'firebreaks', 0)] as const;
const startOf = (g: WorldProps['g']) => (g.cues?.start ?? g.since + 1.5) - g.since;

const Forest: FC<{cells: Uint8Array; flicker: number}> = ({cells, flicker}) => {
  const ref = useRef<HTMLCanvasElement>(null);
  useLayoutEffect(() => {
    const ctx = ref.current?.getContext('2d');
    if (!ctx) return;
    ctx.fillStyle = '#4a5530';
    ctx.fillRect(0, 0, COLS * CELL, ROWS * CELL);
    const rnd = mulberry(3);
    for (let y = 0; y < ROWS; y++) for (let x = 0; x < COLS; x++) {
      const v = cells[y * COLS + x];
      const jitter = rnd();
      const cx = x * CELL + CELL / 2;
      const cy = y * CELL + CELL / 2;
      if (v === TREE) {
        ctx.fillStyle = jitter < 0.5 ? '#2c4a26' : '#35562c';
        ctx.beginPath();
        ctx.arc(cx, cy, CELL * (0.48 + jitter * 0.12), 0, Math.PI * 2);
        ctx.fill();
      } else if (v === ASH) {
        ctx.fillStyle = jitter < 0.5 ? '#2a2520' : '#332c25';
        ctx.fillRect(x * CELL, y * CELL, CELL, CELL);
      } else if (v === BREAK) {
        ctx.fillStyle = '#8a7a58';
        ctx.fillRect(x * CELL, y * CELL, CELL, CELL);
      } else if (v === FIRE) {
        const k = (jitter + flicker) % 1;
        ctx.fillStyle = 'rgba(255,120,30,0.35)';
        ctx.beginPath();
        ctx.arc(cx, cy, CELL * 1.5, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = k < 0.33 ? '#ffd23f' : k < 0.66 ? '#ff8c1a' : '#ff4b1a';
        ctx.beginPath();
        ctx.arc(cx, cy, CELL * 0.62, 0, Math.PI * 2);
        ctx.fill();
      }
    }
  }, [cells, flicker]);
  return <canvas ref={ref} width={COLS * CELL} height={ROWS * CELL} style={{position: 'absolute', left: 0, top: 0}} />;
};

const View: FC<WorldProps> = ({g, worldT, move, o}) => {
  const [density, wind, breaks] = paramsOf(g);
  const run = fire(density, wind, breaks);
  const step = Math.floor((worldT - startOf(g)) * RATE);
  const cells = step < 0 ? fire(density, wind, breaks).steps[0].map((v) => (v === FIRE ? TREE : v)) : run.steps[Math.min(step, SPAN - 1)];
  const burned = step < 0 ? 0 : run.burned[Math.min(step, SPAN - 1)];
  const burning = step < 0 ? 0 : run.burning[Math.min(step, SPAN - 1)];
  const zoom = (f: string) => (f === 'close' ? 2.2 : 1);
  const s = zoom(g.prev) + (zoom(g.focus) - zoom(g.prev)) * move;
  const ox = ORIGIN.x * CELL + CELL / 2;
  const oy = ORIGIN.y * CELL + CELL / 2;
  return (
    <AbsoluteFill style={{background: '#4a5530', overflow: 'hidden'}}>
      <div style={{position: 'absolute', inset: 0, transformOrigin: `${ox}px ${oy}px`, transform: `scale(${s})`}}>
        <Forest cells={cells} flicker={(worldT * 3) % 1} />
        <svg width={1920} height={1080} style={{position: 'absolute'}}>
          {o('start') > 0 && (
            <g opacity={o('start')}>
              <circle cx={ox} cy={oy} r={44 / s} fill="none" stroke={C.accent} strokeWidth={4 / s} />
              <text x={ox + 54 / s} y={oy - 30 / s} fill={C.text} fontFamily='"Barlow Condensed", sans-serif' fontWeight={800} fontSize={30 / s}
                    style={{textTransform: 'uppercase'}}>{tx('startsHere')}</text>
            </g>
          )}
          {breaks > 0 && o('firebreak') > 0 && BREAKS.map((b) => (
            <g key={b} opacity={o('firebreak')}>
              <rect x={b * CELL} y={0} width={4 * CELL} height={ROWS * CELL} fill="none" stroke={C.accent} strokeWidth={3 / s} strokeDasharray={`${12 / s} ${8 / s}`} />
              <text x={b * CELL + 2 * CELL} y={60} textAnchor="middle" fill={C.text} fontFamily='"Barlow Condensed", sans-serif' fontWeight={800}
                    fontSize={26 / s} style={{textTransform: 'uppercase'}}>{tx('firebreak')}</text>
            </g>
          ))}
        </svg>
      </div>
      <AbsoluteFill style={{background: 'radial-gradient(ellipse at center, rgba(0,0,0,0) 55%, rgba(5,8,18,0.55) 100%)'}} />
      <Big o={o('burned')} label={tx('burned')} value={Math.round(burned * 0.25).toLocaleString('es-ES')} color={C.accent}
           sub={`${tx('hectares')} · ${tx('burning')}: ${burning}`} style={{right: 48, top: 52, width: 340}} />
      <Note>{tx('fireNote', {d: Math.round(density * 100)})}</Note>
    </AbsoluteFill>
  );
};

export const incendio: World = {View};
