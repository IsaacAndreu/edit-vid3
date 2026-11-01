// The office from above (remotion/sim/office.ts), drawn like an architect's plan come to life: the open-plan floor
// with its four desk islands and the desks by the windows, the glass meeting room with its oval table and its window,
// the coffee corner, the lifts. People walk in in the morning, sit, get coffee, go to meetings, leave. Patient zero
// coughs; whoever is contagious glows red; the air of a room tints as it fills; the hidden network of who infected
// whom can be drawn on top. Also John Snow's map of Soho (1854) and the superspreaders (Lloyd-Smith 2005).
import type {FC, ReactElement} from 'react';
import {AbsoluteFill, interpolate} from 'remotion';
import {C, FONT, Label, Panel} from '../hud';
import {addWords, num, tx} from '../i18n';
import {AWAY, clockOf, DESKS, EXPOSED, ILL, OVER, PEOPLE, PLAN, runOffice, STEPS_PER_DAY, SUS, ZERO, type OfficeParams} from '../office';
import {Pointers} from '../look';
import {Note, param, type WorldProps} from '../world';
import {Figure, Split} from '../scenes';

addWords({
  monday: {es: 'Lunes', pt: 'Segunda', fr: 'Lundi', de: 'Montag', en: 'Monday'},
  tuesday: {es: 'Martes', pt: 'Terça', fr: 'Mardi', de: 'Dienstag', en: 'Tuesday'},
  wednesday: {es: 'Miércoles', pt: 'Quarta', fr: 'Mercredi', de: 'Mittwoch', en: 'Wednesday'},
  thursday: {es: 'Jueves', pt: 'Quinta', fr: 'Jeudi', de: 'Donnerstag', en: 'Thursday'},
  friday: {es: 'Viernes', pt: 'Sexta', fr: 'Vendredi', de: 'Freitag', en: 'Friday'},
  meetingRoom: {es: 'Sala de reuniones', pt: 'Sala de reuniões', fr: 'Salle de réunion', de: 'Besprechungsraum', en: 'Meeting room'},
  coffeeCorner: {es: 'Café', pt: 'Café', fr: 'Café', de: 'Kaffeeecke', en: 'Coffee'},
  lifts: {es: 'Ascensores', pt: 'Elevadores', fr: 'Ascenseurs', de: 'Aufzüge', en: 'Lifts'},
  windowOpen: {es: 'Ventana abierta', pt: 'Janela aberta', fr: 'Fenêtre ouverte', de: 'Fenster offen', en: 'Window open'},
  windowShut: {es: 'Ventana cerrada', pt: 'Janela fechada', fr: 'Fenêtre fermée', de: 'Fenster zu', en: 'Window shut'},
  caught: {es: 'Se han contagiado', pt: 'Infectaram-se', fr: 'Contaminés', de: 'Angesteckt', en: 'Have caught it'},
  sickNow: {es: 'Contagian ahora', pt: 'Contagiam agora', fr: 'Contagieux', de: 'Ansteckend', en: 'Contagious now'},
  stayHome: {es: 'En casa', pt: 'Em casa', fr: 'À la maison', de: 'Zu Hause', en: 'At home'},
  you: {es: 'Tú', pt: 'Você', fr: 'Toi', de: 'Du', en: 'You'},
  coughing: {es: 'Tose: «solo es un resfriado»', pt: 'Tosse: «é só um resfriado»', fr: 'Il tousse : « juste un rhume »', de: 'Hustet: „nur eine Erkältung“', en: 'Coughing: “just a cold”'},
  officeNote: {es: 'Simulación · {n} personas · contagio de cerca y por el aire de cada sala · 1 s = {x} min', pt: 'Simulação · {n} pessoas · contágio de perto e pelo ar · 1 s = {x} min', fr: 'Simulation · {n} personnes · contagion de près et par l’air · 1 s = {x} min', de: 'Simulation · {n} Personen · Ansteckung aus der Nähe und über die Luft · 1 s = {x} min', en: 'Simulation · {n} people · caught up close and through each room’s air · 1 s = {x} min'},
  byFriday: {es: 'Contagiados el viernes', pt: 'Infectados na sexta', fr: 'Contaminés vendredi', de: 'Angesteckt bis Freitag', en: 'Caught by Friday'},
  asUsual: {es: 'Como siempre', pt: 'Como sempre', fr: 'Comme d’habitude', de: 'Wie immer', en: 'As usual'},
  sickHome: {es: 'Los enfermos en casa', pt: 'Os doentes em casa', fr: 'Les malades à la maison', de: 'Kranke bleiben zu Hause', en: 'The sick stay home'},
  openWindow: {es: 'La ventana abierta', pt: 'A janela aberta', fr: 'La fenêtre ouverte', de: 'Das Fenster offen', en: 'The window open'},
  soho: {es: 'Soho, Londres, 1854', pt: 'Soho, Londres, 1854', fr: 'Soho, Londres, 1854', de: 'Soho, London, 1854', en: 'Soho, London, 1854'},
  pump: {es: 'Fuente de Broad Street', pt: 'Bomba de Broad Street', fr: 'Pompe de Broad Street', de: 'Pumpe der Broad Street', en: 'Broad Street pump'},
  deaths: {es: 'Muertes', pt: 'Mortes', fr: 'Morts', de: 'Tote', en: 'Deaths'},
  perDay: {es: 'Muertes por día (tabla de John Snow)', pt: 'Mortes por dia (tabela de John Snow)', fr: 'Morts par jour (tableau de John Snow)', de: 'Tote pro Tag (Tabelle von John Snow)', en: 'Deaths a day (John Snow’s table)'},
  handle: {es: 'Quitan la palanca · 8 sept.', pt: 'Tiram a alavanca · 8 set.', fr: 'Poignée retirée · 8 sept.', de: 'Schwengel entfernt · 8. Sept.', en: 'Handle removed · 8 Sept'},
  superTitle: {es: 'A cuántos contagió cada enfermo', pt: 'Quantos cada doente infectou', fr: 'Combien chaque malade a contaminé', de: 'Wie viele jeder Kranke ansteckte', en: 'How many each case infected'},
  superShare: {es: 'El {p} % de los enfermos causó el {q} % de los contagios', pt: '{p} % dos doentes causaram {q} % dos contágios', fr: '{p} % des malades ont causé {q} % des contaminations', de: '{p} % der Kranken verursachten {q} % der Ansteckungen', en: '{p} % of cases caused {q} % of infections'},
  nobody: {es: '{n} de {m} no contagiaron a nadie', pt: '{n} de {m} não infectaram ninguém', fr: '{n} sur {m} n’ont contaminé personne', de: '{n} von {m} steckten niemanden an', en: '{n} of {m} infected no one'},
  superNote: {es: 'Simulación con la dispersión medida en el SARS de 2003 (Lloyd-Smith y otros, 2005)', pt: 'Simulação com a dispersão medida no SARS de 2003 (Lloyd-Smith et al., 2005)', fr: 'Simulation avec la dispersion mesurée pour le SRAS 2003 (Lloyd-Smith et al., 2005)', de: 'Simulation mit der bei SARS 2003 gemessenen Streuung (Lloyd-Smith u. a., 2005)', en: 'Simulation with the spread measured for SARS in 2003 (Lloyd-Smith et al., 2005)'},
});

const DAYS_ = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday'];
const SHIRTS = ['#4c6ef5', '#2b8a3e', '#e8590c', '#5f3dc4', '#0b7285', '#c2255c', '#495057', '#f08c00', '#1971c2', '#6741d9', '#2f9e44', '#862e9c'];
const HAIR = ['#2b1d14', '#5a3825', '#1a1a1a', '#a0522d', '#d8b26e', '#3d2b1f'];
export const officeParams = (g: WorldProps['g']): OfficeParams => ({window: param(g, 'ventana', 0), home: param(g, 'quarantine', 0)});
const LAPSE = [1, 6, 30];                               // office minutes per video second: live, normal, the week

/** The floor plan: walls, floors, furniture (everything that does not move). */
const Floor: FC<{windowOpen: boolean; t: number; air: Float32Array; showAir: number}> = ({windowOpen, t, air, showAir}) => {
  const m = PLAN.meeting;
  const c = PLAN.coffee;
  const tint = (v: number) => Math.min(0.55, v / 120) * showAir;
  return (
    <g>
      {/* the building: concrete, the outer windows (light coming in) */}
      <rect width={1920} height={1080} fill="#2a2d33" />
      <rect x={40} y={50} width={1840} height={980} fill="#d9d6cf" />
      {/* open-plan carpet tiles */}
      <rect x={PLAN.open.x} y={PLAN.open.y - 30} width={1030} height={930} fill="#a9adb3" />
      {Array.from({length: 18}, (_, i) => Array.from({length: 16}, (_, j) => (
        <rect key={`${i}-${j}`} x={PLAN.open.x + i * 57} y={PLAN.open.y - 30 + j * 58} width={57} height={58} fill={(i + j) % 2 ? '#a3a7ad' : '#acb0b6'} />
      )))}
      <rect x={PLAN.open.x} y={PLAN.open.y - 30} width={1030} height={930} fill="#ff3b30" opacity={tint(air[0] * 2.5)} />
      {/* outer windows: a strip of glass with daylight falling in */}
      {[[60, 50, 1800, 14], [60, 1016, 1800, 14]].map(([x, y, w, h], i) => <rect key={i} x={x} y={y} width={w} height={h} fill="#bfe3ff" />)}
      <rect x={60} y={64} width={1800} height={120} fill="url(#daylight)" opacity={0.5} />
      {/* the lifts */}
      <rect x={50} y={360} width={190} height={360} fill="#c3c0b8" />
      {[430, 560].map((y) => (
        <g key={y}>
          <rect x={50} y={y} width={26} height={110} fill="#8f969e" />
          <line x1={63} x2={63} y1={y} y2={y + 110} stroke="#5d646c" strokeWidth={2} />
          <rect x={84} y={y + 45} width={12} height={20} rx={3} fill="#2b2f36" />
          <path d={`M 90 ${y + 49} l -3 5 h 6 Z`} fill="#69db7c" />
        </g>
      ))}
      <text x={145} y={350} textAnchor="middle" fill="#3a3f46" fontFamily={FONT} fontSize={24} fontWeight={800} style={{textTransform: 'uppercase'}}>{tx('lifts')}</text>
      {/* the desks: white tops, a monitor, a keyboard, a chair, a mug here and there */}
      {DESKS.map((d, k) => {
        const flip = d.face === -1;
        const side = d.face === 0;
        return (
          <g key={k} transform={`translate(${d.x} ${d.y})`}>
            {side ? (
              <g>
                <rect x={-30} y={-48} width={60} height={96} rx={4} fill="#f4f2ee" stroke="#9a9a96" strokeWidth={2} />
                <rect x={18} y={-26} width={6} height={52} fill="#22252b" />
                <rect x={-4} y={-20} width={12} height={40} rx={2} fill="#d0d2d6" />
              </g>
            ) : (
              <g>
                <rect x={-40} y={flip ? -6 : -54} width={80} height={60} rx={4} fill="#f4f2ee" stroke="#9a9a96" strokeWidth={2} />
                <rect x={-24} y={flip ? 40 : -50} width={48} height={7} fill="#22252b" />
                <rect x={-20} y={flip ? 24 : -36} width={40} height={10} rx={2} fill="#d0d2d6" />
                {k % 3 === 0 && <circle cx={28} cy={flip ? 10 : -14} r={6} fill="#fff" stroke="#8a5a3c" strokeWidth={3} />}
              </g>
            )}
          </g>
        );
      })}
      {/* plants along the aisle */}
      {[[300, 520], [1150, 520], [700, 520], [300, 960], [1150, 70]].map(([x, y], i) => (
        <g key={i}><circle cx={x} cy={y} r={20} fill="#6b4f3a" />{[0, 1, 2, 3, 4].map((k) => <circle key={k} cx={x + Math.cos(k * 1.3) * 12} cy={y + Math.sin(k * 1.3) * 12} r={13} fill={k % 2 ? '#3f8f4f' : '#2f7a3f'} />)}</g>
      ))}
      {/* the meeting room: glass walls, blue carpet, the oval table, the window at the top */}
      <rect x={m.x} y={m.y} width={m.w} height={m.h} fill="#5b7088" />
      <rect x={m.x} y={m.y} width={m.w} height={m.h} fill="#ff3b30" opacity={tint(air[1])} />
      <rect x={m.x} y={m.y} width={m.w} height={m.h} fill="none" stroke="#dbe9f5" strokeWidth={6} opacity={0.85} />
      <rect x={m.x - 4} y={m.door.y - 10} width={8} height={70} fill="#d9d6cf" />
      <ellipse cx={m.x + m.w / 2} cy={m.y + m.h / 2} rx={235} ry={60} fill="#7a4e30" stroke="#5a3820" strokeWidth={4} />
      {Array.from({length: 20}, (_, k) => {
        const side = k < 10 ? -1 : 1;
        return <circle key={k} cx={m.x + 70 + (k % 10) * 45} cy={m.y + 200 + side * 92} r={13} fill="#30343b" />;
      })}
      <rect x={m.x + 140} y={m.y - 14} width={260} height={18} fill={windowOpen ? '#e7f5ff' : '#bfe3ff'} stroke="#7a8fa3" strokeWidth={3} />
      {windowOpen && Array.from({length: 7}, (_, i) => {
        const y = m.y + 10 + ((t * 40 + i * 50) % 300);
        return <path key={i} d={`M ${m.x + 160 + i * 38} ${y} q 10 20 0 40`} stroke="#e7f5ff" strokeWidth={4} fill="none" opacity={0.6 * (1 - (y - m.y) / 320)} />;
      })}
      {showAir > 0 && Array.from({length: 46}, (_, i) => {
        // the breath in the room: with the window shut it hangs there, with it open it drifts up and out
        const r1 = Math.abs(Math.sin(i * 12.9898) * 43758.5453) % 1;
        const r2 = Math.abs(Math.sin(i * 78.233) * 12543.123) % 1;
        const load = Math.min(1, air[1] / 80);
        let px = m.x + 30 + r1 * (m.w - 60) + Math.sin(t * 0.9 + i) * 18;
        let py = m.y + 30 + r2 * (m.h - 60) + Math.cos(t * 0.7 + i * 2) * 14;
        let fade = 1;
        if (windowOpen) {
          const a = (t * 0.22 + r1 * 0.7 + r2 * 0.3) % 1;               // 0 in the room … 1 well outside
          const wx = m.x + 160 + r1 * 220;
          px = px + (wx - px) * Math.min(1, a * 1.6);
          py = py + (m.y - 120 - py) * a;
          fade = a > 0.75 ? (1 - a) / 0.25 : 1;
        }
        return <circle key={`air${i}`} cx={px} cy={py} r={5} fill={load > 0.15 ? '#ff6b6b' : '#e7f5ff'} opacity={showAir * fade * (0.35 + 0.5 * load)} />;
      })}
      <text x={m.x + 20} y={m.y + 40} fill="#eef3f8" fontFamily={FONT} fontSize={28} fontWeight={800} style={{textTransform: 'uppercase'}}>{tx('meetingRoom')}</text>
      <text x={m.x + 20} y={m.y + m.h - 18} fill={windowOpen ? '#a5f3c0' : '#ffc9c9'} fontFamily={FONT} fontSize={24} fontWeight={800} style={{textTransform: 'uppercase'}}>
        {tx(windowOpen ? 'windowOpen' : 'windowShut')}</text>
      {/* the coffee corner: wood floor, counter, machine, fridge, two little tables, a sofa */}
      <rect x={c.x} y={c.y} width={c.w} height={c.h} fill="#b88b5e" />
      {Array.from({length: 10}, (_, i) => <line key={i} x1={c.x} x2={c.x + c.w} y1={c.y + i * 38} y2={c.y + i * 38} stroke="#a57a50" strokeWidth={3} />)}
      <rect x={c.x} y={c.y} width={c.w} height={c.h} fill="#ff3b30" opacity={tint(air[2])} />
      <rect x={c.x + c.w - 70} y={c.y + 10} width={60} height={c.h - 20} fill="#e9ecef" stroke="#9aa0a6" strokeWidth={3} />
      <rect x={c.machine.x - 22} y={c.machine.y - 26} width={44} height={52} rx={6} fill="#212529" />
      <circle cx={c.machine.x + 10} cy={c.machine.y - 12} r={4} fill="#ff4d4f" />
      <rect x={c.x + c.w - 66} y={c.y + c.h - 120} width={52} height={100} fill="#f8f9fa" stroke="#adb5bd" strokeWidth={3} />
      {[[c.x + 150, c.y + 140], [c.x + 330, c.y + 240]].map(([x, y], i) => (
        <g key={i}><circle cx={x} cy={y} r={42} fill="#efe6d8" stroke="#8a6a4a" strokeWidth={3} />{[0, 1, 2, 3].map((k) => <circle key={k} cx={x + Math.cos(k * Math.PI / 2) * 62} cy={y + Math.sin(k * Math.PI / 2) * 62} r={14} fill="#495057" />)}</g>
      ))}
      <rect x={c.x + 30} y={c.y + c.h - 80} width={200} height={56} rx={14} fill="#7048e8" opacity={0.8} />
      <text x={c.x + 20} y={c.y + 36} fill="#3d2b1f" fontFamily={FONT} fontSize={28} fontWeight={800} style={{textTransform: 'uppercase'}}>{tx('coffeeCorner')}</text>
      {/* inner walls */}
      <path d={`M ${m.x} ${m.y + m.h} L ${m.x} ${m.door.y + 60} M ${m.x} ${m.door.y - 10} L ${m.x} ${m.y}`} stroke="#3a3f46" strokeWidth={4} />
      <path d={`M ${c.x} ${c.y} L ${c.x} ${c.door.y - 10} M ${c.x} ${c.door.y + 80} L ${c.x} ${c.y + c.h}`} stroke="#3a3f46" strokeWidth={10} />
      <path d={`M ${c.x} ${c.y} L ${c.x + c.w} ${c.y}`} stroke="#3a3f46" strokeWidth={10} />
    </g>
  );
};

const Person: FC<{x: number; y: number; k: number; state: number; t: number; you: boolean; zero: boolean; showRing: boolean}> = ({x, y, k, state, t, you, zero, showRing}) => {
  const ill = state === ILL;
  const pulse = 0.5 + 0.5 * Math.sin(t * 5 + k);
  return (
    <g transform={`translate(${x} ${y})`}>
      {ill && <circle r={34 + 6 * pulse} fill="#ff3b30" opacity={0.28} />}
      {state === OVER && showRing && <circle r={22} fill="none" stroke="#3ddc84" strokeWidth={3} opacity={0.8} />}
      <ellipse rx={20} ry={13} fill={SHIRTS[k % SHIRTS.length]} stroke="rgba(0,0,0,0.45)" strokeWidth={2} />
      <circle r={10} fill={HAIR[k % HAIR.length]} />
      <circle cy={3} r={6} fill="#e2b48c" opacity={0.0} />
      {zero && ill && Array.from({length: 5}, (_, i) => {
        const a = ((t * 3 + i * 1.3) % 1);
        return <circle key={i} cx={16 + a * 50 * Math.cos(i)} cy={-6 + a * 40 * Math.sin(i * 2)} r={3 + a * 3} fill="#ff8787" opacity={0.7 * (1 - a)} />;
      })}
      {you && <g><circle r={28} fill="none" stroke={C.you} strokeWidth={5} />
        <text y={-36} textAnchor="middle" fill={C.you} stroke="#000" strokeWidth={5} paintOrder="stroke" fontFamily={FONT} fontSize={28} fontWeight={800} style={{textTransform: 'uppercase'}}>{tx('you')}</text></g>}
    </g>
  );
};

export const Office: FC<{p: OfficeParams; step: number; t: number; showAir: number; showNet: number; showYou: number; showZero: number; labels?: boolean}> = (
  {p, step, t, showAir, showNet, showYou, showZero}) => {
  const run = runOffice(p);
  const s = Math.max(0, Math.min(run.steps - 1, step));
  const x = run.x[s];
  const st = run.state[s];
  // the chain from patient zero to «you», followed back link by link
  const parent = new Map(run.links.map((l) => [l.to, l]));
  const chain = new Set<typeof run.links[number]>();
  for (let k = run.you, guard = 0; k !== ZERO && parent.has(k) && guard < PEOPLE; guard++) { const l = parent.get(k)!; chain.add(l); k = l.from; }
  const lit = showNet > 0 && run.you >= 0;                // the network always shows the yellow path to «you»
  return (
    <svg width={1920} height={1080} style={{position: 'absolute'}}>
      <defs><linearGradient id="daylight" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#fff8e1" stopOpacity={0.9} /><stop offset="100%" stopColor="#fff8e1" stopOpacity={0} /></linearGradient></defs>
      <Floor windowOpen={p.window > 0} t={t} air={run.air[s]} showAir={showAir} />
      {/* who infected whom: the network nobody sees */}
      {showNet > 0 && run.links.filter((l) => l.step <= s).map((l, i) => {
        const a = [x[2 * l.from], x[2 * l.from + 1]];
        const b = [DESKS[l.to].x, DESKS[l.to].y];
        const age = Math.min(1, (s - l.step) / 60);
        const onChain = lit && chain.has(l);
        if (onChain) return null;
        return <path key={i} d={`M ${a[0]} ${a[1]} Q ${(a[0] + b[0]) / 2} ${Math.min(a[1], b[1]) - 60} ${b[0]} ${b[1]}`} stroke="#ff6b6b" strokeWidth={3}
                     fill="none" strokeDasharray="8 6" opacity={showNet * (lit ? 0.25 : 0.35 + 0.5 * (1 - age))} />;
      })}
      {lit && [...chain].filter((l) => l.step <= s).map((l, i) => {
        // drawn desk to desk so the yellow path reads as one line from patient zero to you
        const a = [DESKS[l.from].x, DESKS[l.from].y];
        const b = [DESKS[l.to].x, DESKS[l.to].y];
        return <path key={`c${i}`} d={`M ${a[0]} ${a[1]} Q ${(a[0] + b[0]) / 2} ${Math.min(a[1], b[1]) - 60} ${b[0]} ${b[1]}`} stroke={C.you} strokeWidth={7}
                     fill="none" strokeLinecap="round" opacity={showNet} />;
      })}
      {Array.from({length: PEOPLE}, (_, k) => {
        if (st[k] === AWAY) return null;
        const px = x[2 * k];
        const py = x[2 * k + 1];
        if (px < 140 && Math.abs(py - PLAN.lift.y) < 10) return null;          // out of the building
        return <Person key={k} x={px} y={py} k={k} state={st[k] === EXPOSED ? SUS : st[k]} t={t} you={(showYou > 0.5 || showNet > 0.5) && k === run.you}
                       zero={k === ZERO} showRing={showAir > 0 || showNet > 0} />;
      })}
      {showZero > 0 && (() => {
        const zx = x[2 * ZERO];
        const zy = x[2 * ZERO + 1];
        return (
          <g opacity={showZero}>
            <circle cx={zx} cy={zy} r={52} fill="none" stroke={C.accent} strokeWidth={4} />
            <text x={zx + 60} y={zy - 40} fill={C.text} fontFamily={FONT} fontSize={28} fontWeight={800} stroke="#000" strokeWidth={5} paintOrder="stroke"
                  style={{textTransform: 'uppercase'}}>{tx('coughing')}</text>
          </g>
        );
      })()}
    </svg>
  );
};

export const OfficeScene: FC<WorldProps> = ({g, worldT, o, on, local, real = local}) => {
  const p = officeParams(g);
  const run = runOffice(p);
  const speed = LAPSE[Math.max(0, Math.min(2, Math.round(param(g, 'ritmo', 1))))];
  const startDay = Math.max(0, Math.min(4, Math.round(param(g, 'dia', 0))));
  const step = Math.round(startDay * STEPS_PER_DAY + worldT * speed);
  const s = Math.max(0, Math.min(run.steps - 1, step));
  const clock = clockOf(s);
  const counts = run.counts[s];
  const panel = Math.max(o('counts'), on * 0.9);
  return (
    <AbsoluteFill style={{background: C.night}}>
      <Office p={p} step={s} t={worldT} showAir={o('aire')} showNet={o('red')} showYou={o('tu')} showZero={o('zero')} />
      <Panel o={1} style={{left: 280, top: 70, padding: '10px 20px'}}>
        <div style={{fontSize: 40, fontWeight: 800, textTransform: 'uppercase', fontVariantNumeric: 'tabular-nums'}}>
          {tx(DAYS_[clock.weekday])} {clock.hh}:{String(clock.mm).padStart(2, '0')}</div>
      </Panel>
      <Panel o={panel} style={{right: 90, top: 520, width: 300}}>
        <Label>{tx('caught')}</Label>
        <div style={{fontSize: 56, fontWeight: 800, color: counts.caught > PEOPLE / 2 ? C.red : C.text}}>{num(counts.caught)} / {PEOPLE}</div>
        <Label color="#ff8787">{tx('sickNow')}: {num(counts.ill)}</Label>
        {p.home > 0 && <Label>{tx('stayHome')}: {num(counts.home)}</Label>}
      </Panel>
      <Pointers marks={g.marks} local={real} at={{cafe: PLAN.coffee.machine, sala: {x: PLAN.meeting.x + 270, y: PLAN.meeting.y + 200}, ascensor: PLAN.lift}} />
      <Note>{tx('officeNote', {n: PEOPLE, x: speed})}</Note>
    </AbsoluteFill>
  );
};

export const OfficeCompare: FC<WorldProps> = ({g, worldT}) => {
  const que = param<string>(g, 'que', 'cuarentena');
  const right: OfficeParams = que === 'ventana' ? {window: 1, home: 0} : {window: 0, home: 1};
  const left: OfficeParams = {window: 0, home: 0};
  const step = Math.round(worldT * 30);
  const friday = 5 * STEPS_PER_DAY - 1;
  const side = (p: OfficeParams) => <AbsoluteFill style={{background: C.night}}><Office p={p} step={step} t={worldT} showAir={1} showNet={0} showYou={0} showZero={0} /></AbsoluteFill>;
  return (
    <Split left={side(left)} right={side(right)} titles={[tx('asUsual'), tx(que === 'ventana' ? 'openWindow' : 'sickHome')]}
           figures={[<Figure key="a" label={tx('byFriday')} value={`${runOffice(left).counts[friday].caught} / ${PEOPLE}`} colour={C.red} />,
                     <Figure key="b" label={tx('byFriday')} value={`${runOffice(right).counts[friday].caught} / ${PEOPLE}`} colour={C.green} />]} />
  );
};

// --- John Snow's map: Soho, 1854 -----------------------------------------------------------------------------------

// deaths a day, 19 August - 30 September 1854 (Snow's table of fatal attacks)
const SNOW = [1, 1, 1, 0, 1, 1, 0, 1, 1, 1, 1, 8, 56, 143, 116, 54, 46, 36, 20, 28, 12, 11, 5, 5, 1, 3, 0, 1, 4, 2, 3, 0, 0, 2, 1, 1, 1, 1, 1, 0, 0, 0];
const HANDLE_DAY = 20;                                   // 8 September
const PUMP = {x: 860, y: 470};

export const SnowMap: FC<WorldProps> = ({g, worldT, local, real = local}) => {
  const day = Math.min(SNOW.length, Math.floor(worldT * 3));
  const total = SNOW.slice(0, day).reduce((a, b) => a + b, 0);
  // streets: a crooked grid, Broad Street through the middle
  const streets: [number, number, number, number, string?][] = [
    [120, 470, 1500, 470, 'BROAD STREET'], [120, 250, 1500, 230], [120, 700, 1500, 720], [120, 900, 1500, 900],
    [300, 120, 320, 1000], [560, 120, 540, 1000], [860, 120, 860, 1000], [1120, 120, 1140, 1000], [1380, 120, 1360, 1000],
  ];
  const marks: ReactElement[] = [];
  const rnd = (i: number) => (Math.sin(i * 12.9898) * 43758.5453) % 1;
  let n = 0;
  for (let d = 0; d < day; d++) {
    for (let k = 0; k < SNOW[d]; k++, n++) {
      // houses near the pump, by distance (most within a couple of blocks)
      const a = Math.abs(rnd(n + 1)) * Math.PI * 2;
      const r = 40 + Math.abs(rnd(n + 7)) ** 1.6 * 520;
      const hx = PUMP.x + Math.cos(a) * r;
      const hy = PUMP.y + Math.sin(a) * r * 0.75;
      // snap to the nearest street, stacked like Snow's bars
      const street = Math.abs(hy - 470) < 110 ? 470 : Math.abs(hy - 250) < 110 ? 240 : Math.abs(hy - 710) < 110 ? 710 : 900;
      const side = hy < street ? -1 : 1;
      const slot = Math.round(hx / 14);
      marks.push(<rect key={n} x={slot * 14 - 5} y={street + side * (16 + ((n * 7) % 9) * 7) - 3} width={10} height={5} fill="#111" />);
    }
  }
  return (
    <AbsoluteFill style={{background: '#efe4c8'}}>
      <svg width={1920} height={1080} style={{position: 'absolute'}}>
        <rect width={1920} height={1080} fill="#efe4c8" />
        {Array.from({length: 120}, (_, i) => <circle key={i} cx={(i * 197) % 1920} cy={(i * 331) % 1080} r={60} fill="#e2d4b0" opacity={0.25} />)}
        {streets.map(([x1, y1, x2, y2, name], i) => (
          <g key={i}>
            <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="#fbf6ea" strokeWidth={34} />
            <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="#8a7a5a" strokeWidth={36} strokeOpacity={0.25} />
            {name && <text x={x1 + 30} y={y1 + 8} fill="#5a4a2a" fontFamily="Cinzel" fontWeight={700} fontSize={22} letterSpacing={6}>{name}</text>}
          </g>
        ))}
        {marks}
        <g transform={`translate(${PUMP.x} ${PUMP.y})`}>
          {day <= HANDLE_DAY && <g><line x1={14} y1={-6} x2={70} y2={-44} stroke="#fbf6ea" strokeWidth={18} strokeLinecap="round" />
            <line x1={14} y1={-6} x2={70} y2={-44} stroke="#3b2d22" strokeWidth={11} strokeLinecap="round" />
            <circle cx={70} cy={-44} r={10} fill="#3b2d22" /></g>}
          {day > HANDLE_DAY && <g opacity={Math.max(0, 1 - (day - HANDLE_DAY) / 4)}>
            <line x1={14} y1={-6 + (day - HANDLE_DAY) * 18} x2={70} y2={-44 + (day - HANDLE_DAY) * 22} stroke="#3b2d22" strokeWidth={11} strokeLinecap="round" />
            <text x={60} y={30} fill="#1d4ed8" fontFamily={FONT} fontSize={26} fontWeight={800} stroke="#efe4c8" strokeWidth={6} paintOrder="stroke"
                  style={{textTransform: 'uppercase'}}>{tx('handle')}</text></g>}
          <circle r={18} fill="#1d4ed8" stroke="#fff" strokeWidth={4} />
          <text y={-32} textAnchor="middle" fill="#1d4ed8" fontFamily={FONT} fontSize={30} fontWeight={800} stroke="#efe4c8" strokeWidth={6} paintOrder="stroke"
                style={{textTransform: 'uppercase'}}>{tx('pump')}</text>
        </g>
        {[[330, 860], [1300, 300], [560, 160]].map(([x, y], i) => <circle key={i} cx={x} cy={y} r={11} fill="#6b7280" stroke="#fff" strokeWidth={3} />)}
        {/* the deaths a day */}
        <g transform="translate(1540 640)">
          <rect x={-20} y={-90} width={360} height={430} fill="#fbf6ea" stroke="#8a7a5a" strokeWidth={2} />
          <text x={0} y={-60} fill="#3b2d22" fontFamily={FONT} fontSize={22} fontWeight={800} style={{textTransform: 'uppercase'}}>{tx('perDay')}</text>
          {SNOW.slice(0, day).map((v, i) => <rect key={i} x={i * 7.6} y={300 - v * 2} width={6} height={v * 2} fill={i >= HANDLE_DAY ? '#6b7280' : '#111'} />)}
          {day > HANDLE_DAY && <g><line x1={HANDLE_DAY * 7.6} x2={HANDLE_DAY * 7.6} y1={0} y2={300} stroke="#1d4ed8" strokeWidth={3} strokeDasharray="6 5" />
            <text x={160} y={326} textAnchor="middle" fill="#1d4ed8" fontFamily={FONT} fontSize={18} fontWeight={800} style={{textTransform: 'uppercase'}}>{tx('handle')}</text></g>}
        </g>
      </svg>
      <Panel o={1} style={{left: 48, top: 40}}>
        <div style={{fontSize: 38, fontWeight: 800, textTransform: 'uppercase'}}>{tx('soho')}</div>
        <Label>John Snow</Label>
        <Label>{tx('deaths')}: {num(total)}</Label>
      </Panel>
      <Pointers marks={g.marks} local={real} at={{bomba: PUMP}} />
    </AbsoluteFill>
  );
};

// --- superspreaders: R about 3 but very uneven (negative binomial, k = 0.16, as measured for SARS) ------------------

const CASES = 40;
const secondary = (() => {
  const rnd = (() => { let s = 11 * 7919; return () => ((s = (s * 16807) % 2147483647) / 2147483647); })();   // a sample like the measured ones (largest ≈ 25)
  const gamma = (k: number): number => {                // Marsaglia-Tsang (k < 1 via the boost)
    if (k < 1) return gamma(1 + k) * rnd() ** (1 / k);
    const d = k - 1 / 3;
    const c = 1 / Math.sqrt(9 * d);
    for (;;) {
      const u = rnd();
      const v0 = Math.sqrt(-2 * Math.log(rnd())) * Math.cos(2 * Math.PI * u);
      const v = (1 + c * v0) ** 3;
      if (v > 0 && Math.log(rnd()) < 0.5 * v0 * v0 + d - d * v + d * Math.log(v)) return d * v;
    }
  };
  const poisson = (l: number) => { let k = 0; let p = Math.exp(-l); let s = p; const u = rnd(); while (u > s && k < 200) { k++; p *= l / k; s += p; } return k; };
  return Array.from({length: CASES}, () => poisson((gamma(0.16) * 3) / 0.16)).sort((a, b) => b - a);
})();

export const Superspreaders: FC<WorldProps> = ({worldT}) => {
  const grow = interpolate(worldT, [0.3, 2.5], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const total = secondary.reduce((a, b) => a + b, 0);
  const top = Math.max(1, Math.round(CASES * 0.2));
  const share = Math.round((100 * secondary.slice(0, top).reduce((a, b) => a + b, 0)) / Math.max(1, total));
  const zero = secondary.filter((v) => v === 0).length;
  const max = Math.max(...secondary);
  return (
    <AbsoluteFill style={{background: 'radial-gradient(ellipse at 50% 40%, #16213a 0%, #0a0f1c 75%)'}}>
      <Panel o={1} style={{left: 120, top: 90, width: 1680, height: 820}}>
        <div style={{fontSize: 40, fontWeight: 800, textTransform: 'uppercase'}}>{tx('superTitle')}</div>
        <svg width={1600} height={600} style={{marginTop: 20}}>
          {secondary.map((v, i) => {
            const h = (v / max) * 520 * grow;
            return (
              <g key={i}>
                <rect x={i * 40} y={560 - h} width={30} height={Math.max(h, 2)} fill={i < top ? C.red : '#8a93a6'} rx={3} />
                {v > 0 && grow > 0.9 && <text x={i * 40 + 15} y={550 - h} textAnchor="middle" fill={C.text} fontFamily={FONT} fontSize={22} fontWeight={700}>{v}</text>}
                <circle cx={i * 40 + 15} cy={585} r={10} fill={i < top ? C.red : '#c9d3e6'} />
              </g>
            );
          })}
        </svg>
        <div style={{fontSize: 36, fontWeight: 800, color: C.red, marginTop: 6, opacity: grow}}>{tx('superShare', {p: 20, q: share})}</div>
        <Label>{tx('nobody', {n: zero, m: CASES})}</Label>
      </Panel>
      <Note>{tx('superNote')}</Note>
    </AbsoluteFill>
  );
};
