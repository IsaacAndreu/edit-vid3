// Patient zero (or the first one to believe a hoax) in a town seen from above: everyone walking its streets, the
// infected in red passing it on as they cross, the recovered in green, the vaccinated in blue; counts and the curve.
import type {FC} from 'react';
import {AbsoluteFill} from 'remotion';
import {City, toScreen, type Cam} from '../city';
import {epidemic, I, PEOPLE, R, S, stepAt, STEPS_PER_DAY, V, ZERO, ZERO_AT} from '../contagion';
import {C, Label, Panel} from '../hud';
import {addWords, tx} from '../i18n';
import {Note, param, Spark, type World, type WorldProps} from '../world';

addWords({
  healthy: {es: 'Sanos', pt: 'Saudáveis', fr: 'Sains', de: 'Gesund', en: 'Healthy'},
  infected: {es: 'Contagiados', pt: 'Infectados', fr: 'Contaminés', de: 'Infiziert', en: 'Infected'},
  recovered: {es: 'Recuperados', pt: 'Recuperados', fr: 'Guéris', de: 'Genesen', en: 'Recovered'},
  vaccinated: {es: 'Vacunados', pt: 'Vacinados', fr: 'Vaccinés', de: 'Geimpft', en: 'Vaccinated'},
  unaware: {es: 'No lo han oído', pt: 'Não ouviram', fr: 'Pas au courant', de: 'Nicht gehört', en: 'Haven’t heard'},
  believers: {es: 'Se lo creen', pt: 'Acreditam', fr: 'Y croient', de: 'Glauben es', en: 'Believe it'},
  debunked: {es: 'Ya no se lo creen', pt: 'Já não acreditam', fr: 'N’y croient plus', de: 'Glauben es nicht mehr', en: 'No longer believe it'},
  immune: {es: 'Inmunes al bulo', pt: 'Imunes ao boato', fr: 'Immunisés', de: 'Immun', en: 'Immune to it'},
  patientZero: {es: 'Paciente cero', pt: 'Paciente zero', fr: 'Patient zéro', de: 'Patient null', en: 'Patient zero'},
  hoaxStarts: {es: 'Aquí empieza el bulo', pt: 'Aqui começa o boato', fr: 'Ici naît la rumeur', de: 'Hier beginnt das Gerücht', en: 'The hoax starts here'},
  curveTitle: {es: 'Contagiados cada día', pt: 'Infectados por dia', fr: 'Contaminés chaque jour', de: 'Infizierte pro Tag', en: 'Infected each day'},
  curveHoax: {es: 'Gente que se lo cree, día a día', pt: 'Gente que acredita, dia a dia', fr: 'Gens qui y croient, jour après jour', de: 'Leute, die es glauben, Tag für Tag', en: 'People who believe it, day by day'},
  peak: {es: 'Pico', pt: 'Pico', fr: 'Pic', de: 'Höhepunkt', en: 'Peak'},
  atHome: {es: 'Los contagiados se quedan en casa', pt: 'Os infectados ficam em casa', fr: 'Les contaminés restent chez eux', de: 'Infizierte bleiben zu Hause', en: 'The infected stay home'},
  contagionNote: {es: 'Simulación · {n} personas · se contagia al cruzarse por la calle · un día = 2 segundos', pt: 'Simulação · {n} pessoas · contágio ao cruzar-se na rua · um dia = 2 segundos', fr: 'Simulation · {n} personnes · contagion en se croisant · un jour = 2 secondes', de: 'Simulation · {n} Menschen · Ansteckung beim Begegnen · ein Tag = 2 Sekunden', en: 'Simulation · {n} people · passed on when they cross · a day = 2 seconds'},
});

const COLOURS = {[S]: '#c9d3e6', [I]: '#ff4b4b', [R]: '#3ddc84', [V]: '#5b8def'} as Record<number, string>;
const HOAX = {[S]: '#c9d3e6', [I]: '#c06bff', [R]: '#3ddc84', [V]: '#5b8def'} as Record<number, string>;

const paramsOf = (g: WorldProps['g']) => ({contagion: param(g, 'contagion', 0.5), vaccinated: param(g, 'vaccinated', 0),
                                           quarantine: param(g, 'quarantine', 0)});

const camera = (focus: string, zx: number, zy: number): Cam => (focus === 'close' ? {x: zx, y: zy, s: 7} : {x: 0, y: 0, s: 3.1});

const View: FC<WorldProps> = ({g, worldT, move, o}) => {
  const e = epidemic(paramsOf(g));
  const hoax = param<string>(g, 'mode', 'virus') === 'bulo';
  const colour = hoax ? HOAX : COLOURS;
  const step = stepAt(worldT);
  const x = e.x[step];
  const st = e.state[step];
  const [zx, zy] = [x[2 * ZERO], x[2 * ZERO + 1]];
  const a = camera(g.prev, zx, zy);
  const b = camera(g.focus, zx, zy);
  const cam = {x: a.x + (b.x - a.x) * move, y: a.y + (b.y - a.y) * move, s: a.s + (b.s - a.s) * move};
  const r = Math.max(5.5, cam.s * 1.5);
  const counts = e.counts[step];
  const stays = paramsOf(g).quarantine > 0;
  const days = Math.floor(step / STEPS_PER_DAY);
  const daily = Array.from({length: days + 1}, (_, d) => e.counts[Math.min(step, d * STEPS_PER_DAY)][I]);
  const z = toScreen(cam, zx, zy);
  const names = hoax ? ['unaware', 'believers', 'debunked', 'immune'] : ['healthy', 'infected', 'recovered', 'vaccinated'];
  return (
    <AbsoluteFill style={{backgroundColor: C.night}}>
      <City cam={cam} clearing={0} disc={false} />
      <AbsoluteFill style={{background: 'rgba(8,12,22,0.42)'}} />
      <svg width={1920} height={1080} style={{position: 'absolute'}}>
        {Array.from({length: PEOPLE}, (_, k) => {
          const {sx, sy} = toScreen(cam, x[2 * k], x[2 * k + 1]);
          if (sx < -10 || sx > 1930 || sy < -10 || sy > 1090) return null;
          const s = st[k];
          const home = stays && s === I && Math.hypot(x[2 * k] - e.home[2 * k], x[2 * k + 1] - e.home[2 * k + 1]) < 0.01 && step > ZERO_AT + STEPS_PER_DAY;
          return (
            <g key={k}>
              {s === I && <circle cx={sx} cy={sy} r={r * 2.4} fill={colour[I]} opacity={0.25} />}
              {s === V && o('vaccine') > 0.3 && <circle cx={sx} cy={sy} r={r * 1.9} fill="none" stroke={colour[V]} strokeWidth={2} opacity={o('vaccine')} />}
              {home && o('quarantine') > 0.3 && <rect x={sx - r * 2} y={sy - r * 2} width={r * 4} height={r * 4} fill="none" stroke="#ffffff" strokeWidth={1.5} opacity={0.8} />}
              <circle cx={sx} cy={sy} r={r} fill={colour[s]} stroke="#0b1020" strokeWidth={1} />
            </g>
          );
        })}
        {o('zero') > 0 && (
          <g opacity={o('zero')}>
            <circle cx={z.sx} cy={z.sy} r={r * 5} fill="none" stroke={C.accent} strokeWidth={3} />
            <text x={z.sx + r * 6} y={z.sy - r * 3} fill={C.text} fontFamily='"Barlow Condensed", sans-serif' fontWeight={800} fontSize={26}
                  style={{textTransform: 'uppercase'}}>{tx(hoax ? 'hoaxStarts' : 'patientZero')}</text>
          </g>
        )}
      </svg>
      <AbsoluteFill style={{background: 'radial-gradient(ellipse at center, rgba(0,0,0,0) 55%, rgba(5,8,18,0.55) 100%)'}} />
      <Panel o={o('counts')} style={{right: 48, top: 52, width: 300}}>
        <Label>{tx('day')} {days}</Label>
        {[S, I, R, V].filter((s) => s !== V || counts[V] > 0).map((s) => (
          <div key={s} style={{display: 'flex', alignItems: 'center', gap: 10, marginTop: 8, fontSize: 24, fontWeight: 700}}>
            <span style={{width: 14, height: 14, borderRadius: 7, background: colour[s]}} />
            <span style={{flex: 1, textTransform: 'uppercase'}}>{tx(names[s])}</span>
            <span style={{fontVariantNumeric: 'tabular-nums', color: s === I ? colour[I] : C.text}}>{counts[s]}</span>
          </div>
        ))}
      </Panel>
      <Panel o={o('curve')} style={{right: 48, top: 52, width: 470}}>
        <Label>{tx(hoax ? 'curveHoax' : 'curveTitle')}</Label>
        <Spark values={daily} total={Math.max(days + 1, 30)} max={Math.max(e.peak.infected, 10)} color={colour[I]} />
        <div style={{display: 'flex', justifyContent: 'space-between', marginTop: 8, fontSize: 20, fontWeight: 700}}>
          <span>{tx('day').toUpperCase()} {days}</span>
          {step >= e.peak.step && <span style={{color: colour[I]}}>{tx('peak').toUpperCase()}: {e.peak.infected} · {tx('day').toUpperCase()} {Math.round(e.peak.step / STEPS_PER_DAY)}</span>}
        </div>
      </Panel>
      <Panel o={o('quarantine')} style={{left: '50%', bottom: 70, transform: 'translateX(-50%)'}}>
        <div style={{fontSize: 30, fontWeight: 800, textTransform: 'uppercase'}}>{tx('atHome')}</div>
      </Panel>
      <Note>{tx('contagionNote', {n: PEOPLE})}</Note>
    </AbsoluteFill>
  );
};

// a tick each time ten more people catch it while the counts are on
const sounds = (g: WorldProps['g'], length: number) => {
  if (g.overlay !== 'counts' && g.overlay !== 'curve') return {};
  const e = epidemic(paramsOf(g));
  const t0 = g.at - g.since;
  const ticks: number[] = [];
  let before = Math.floor(e.counts[stepAt(t0)][I] / 10);
  for (let s = 0.1; s < length; s += 0.1) {
    const now = Math.floor(e.counts[stepAt(t0 + s)][I] / 10);
    if (now > before) ticks.push(s);
    before = now;
  }
  return {ticks};
};

export const contagio: World = {View, sounds};
