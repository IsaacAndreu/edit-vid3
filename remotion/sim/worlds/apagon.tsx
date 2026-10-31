// The power grid of the Iberian peninsula at a blackout (remotion/sim/power.ts): the coast and the border, cities as
// clusters of houses with their windows lit, power plants with their own look (cooling towers, chimneys, a dam, solar
// fields, wind turbines turning), pylons and lines with the current running along them, and the links with France and
// Morocco. Scenes (param scene):
//  cascada     a line trips; its flow moves to its neighbours, which trip in turn: the cities go dark one by one
//              (margin: with 10-20 % ~70 % of the people lose power, with 30 % a corner, with 40 % nothing)
//  reparto     Kirchhoff: a line is cut and every other line's flow changes at once (thicker, thinner)
//  combado     one line seen from the side on a hot day: it heats, sags, touches the trees and trips
//  frecuencia  50 Hz: a plant trips, production and consumption no longer weigh the same, the needle falls; the relays
//              cut districts on purpose (deslastre) and it recovers — or, without them, plants trip and all goes dark
//  inercia     the same loss with heavy turbines turning (the frequency falls slowly and holds) and with solar panels
//              (it falls fast and everything trips)
//  arena       Bak, Tang & Wiesenfeld's sandpile: grains one by one, avalanches small and huge
//  arranque    the black start: hydro plants and the interconnections light islands that grow and synchronise;
//              golpe: everybody switches on at once and an island collapses again
//  isla        the north-east separates in time (and keeps France): it stays lit while the rest goes dark
import type {FC, ReactElement} from 'react';
import {useLayoutEffect, useRef} from 'react';
import {AbsoluteFill, interpolate} from 'remotion';
import {C, FONT, Label, Panel} from '../hud';
import {addWords, num, tx} from '../i18n';
import {Pointers, type Anchor} from '../look';
import {countryOf, freqAt, frequency, gridOf, PILE, sandpile, type FreqRun, type Grid} from '../power';
import {Big, clamp, mulberry, Note, param, SideTitle, type World, type WorldProps} from '../world';

addWords({
  spain: {es: 'España', pt: 'Espanha', fr: 'Espagne', de: 'Spanien', en: 'Spain'},
  portugal: {es: 'Portugal', pt: 'Portugal', fr: 'Portugal', de: 'Portugal', en: 'Portugal'},
  germany: {es: 'Alemania', pt: 'Alemanha', fr: 'Allemagne', de: 'Deutschland', en: 'Germany'},
  brazil: {es: 'Brasil', pt: 'Brasil', fr: 'Brésil', de: 'Brasilien', en: 'Brazil'},
  usa: {es: 'EE. UU.', pt: 'EUA', fr: 'États-Unis', de: 'USA', en: 'USA'},
  canada: {es: 'Canadá', pt: 'Canadá', fr: 'Canada', de: 'Kanada', en: 'Canada'},
  france: {es: 'Francia', pt: 'França', fr: 'France', de: 'Frankreich', en: 'France'},
  morocco: {es: 'Marruecos', pt: 'Marrocos', fr: 'Maroc', de: 'Marokko', en: 'Morocco'},
  austria: {es: 'Austria', pt: 'Áustria', fr: 'Autriche', de: 'Österreich', en: 'Austria'},
  poland: {es: 'Polonia', pt: 'Polônia', fr: 'Pologne', de: 'Polen', en: 'Poland'},
  netherlands: {es: 'Países Bajos', pt: 'Países Baixos', fr: 'Pays-Bas', de: 'Niederlande', en: 'Netherlands'},
  denmark: {es: 'Dinamarca', pt: 'Dinamarca', fr: 'Danemark', de: 'Dänemark', en: 'Denmark'},
  paraguay: {es: 'Paraguay', pt: 'Paraguai', fr: 'Paraguay', de: 'Paraguay', en: 'Paraguay'},
  argentina: {es: 'Argentina', pt: 'Argentina', fr: 'Argentine', de: 'Argentinien', en: 'Argentina'},
  uruguay: {es: 'Uruguay', pt: 'Uruguai', fr: 'Uruguay', de: 'Uruguay', en: 'Uruguay'},
  venezuela: {es: 'Venezuela', pt: 'Venezuela', fr: 'Venezuela', de: 'Venezuela', en: 'Venezuela'},
  quebec: {es: 'Quebec', pt: 'Quebec', fr: 'Québec', de: 'Québec', en: 'Québec'},
  pjm: {es: 'Sur (PJM)', pt: 'Sul (PJM)', fr: 'Sud (PJM)', de: 'Süden (PJM)', en: 'South (PJM)'},
});

addWords({
  peopleDark: {es: 'Sin luz', pt: 'Sem luz', fr: 'Sans courant', de: 'Ohne Strom', en: 'Without power'},
  millionsOf: {es: '≈ {n} de {m} millones de personas', pt: '≈ {n} de {m} milhões de pessoas', fr: '≈ {n} millions de personnes sur {m}', de: '≈ {n} von {m} Millionen Menschen', en: '≈ {n} of {m} million people'},
  darkFor: {es: 'A oscuras desde hace', pt: 'Às escuras há', fr: 'Dans le noir depuis', de: 'Dunkel seit', en: 'Dark for'},
  linesDown: {es: 'Líneas desconectadas', pt: 'Linhas desligadas', fr: 'Lignes coupées', de: 'Abgeschaltete Leitungen', en: 'Lines tripped'},
  firstFault: {es: 'El primer fallo', pt: 'A primeira falha', fr: 'La première panne', de: 'Der erste Fehler', en: 'The first fault'},
  linkCut: {es: 'Conexión cortada', pt: 'Ligação cortada', fr: 'Liaison coupée', de: 'Verbindung getrennt', en: 'Link cut'},
  cutHere: {es: 'Se corta esta línea', pt: 'Corta-se esta linha', fr: 'On coupe cette ligne', de: 'Diese Leitung wird getrennt', en: 'This line is cut'},
  flowChanges: {es: 'La corriente se reparte sola por todos los caminos', pt: 'A corrente reparte-se sozinha por todos os caminhos', fr: 'Le courant se répartit seul sur tous les chemins', de: 'Der Strom verteilt sich von selbst auf alle Wege', en: 'The current shares itself over every path'},
  lineTemp: {es: 'Temperatura del cable', pt: 'Temperatura do cabo', fr: 'Température du câble', de: 'Temperatur des Seils', en: 'Cable temperature'},
  lineLoadNow: {es: 'Carga de la línea', pt: 'Carga da linha', fr: 'Charge de la ligne', de: 'Last der Leitung', en: 'Line load'},
  tripped: {es: 'Desconectada', pt: 'Desligada', fr: 'Déconnectée', de: 'Abgeschaltet', en: 'Tripped'},
  alarmOff: {es: 'Alarma: no sonó', pt: 'Alarme: não tocou', fr: 'Alarme : muette', de: 'Alarm: stumm', en: 'Alarm: silent'},
  production: {es: 'Producción', pt: 'Produção', fr: 'Production', de: 'Erzeugung', en: 'Production'},
  consumption: {es: 'Consumo', pt: 'Consumo', fr: 'Consommation', de: 'Verbrauch', en: 'Consumption'},
  frequencyWord: {es: 'Frecuencia', pt: 'Frequência', fr: 'Fréquence', de: 'Frequenz', en: 'Frequency'},
  plantsTrip: {es: 'Saltan las protecciones: se desconectan centrales', pt: 'Disparam as proteções: centrais desligam-se', fr: 'Les protections sautent : des centrales décrochent', de: 'Schutz löst aus: Kraftwerke gehen vom Netz', en: 'Protections trip: plants disconnect'},
  shedding: {es: 'Deslastre: se cortan barrios a propósito', pt: 'Deslastre: cortam-se bairros de propósito', fr: 'Délestage : on coupe des quartiers exprès', de: 'Lastabwurf: Viertel werden absichtlich getrennt', en: 'Load shedding: districts cut on purpose'},
  blackoutAll: {es: 'Apagón', pt: 'Apagão', fr: 'Black-out', de: 'Blackout', en: 'Blackout'},
  recovered: {es: 'Se recupera', pt: 'Recupera', fr: 'Ça tient', de: 'Erholt sich', en: 'Recovers'},
  spinning: {es: 'Turbinas que giran', pt: 'Turbinas que giram', fr: 'Des turbines qui tournent', de: 'Drehende Turbinen', en: 'Spinning turbines'},
  panels: {es: 'Paneles solares', pt: 'Painéis solares', fr: 'Panneaux solaires', de: 'Solarpaneele', en: 'Solar panels'},
  holds: {es: 'Aguanta', pt: 'Aguenta', fr: 'Ça tient', de: 'Hält', en: 'Holds'},
  falls: {es: 'Se apaga todo', pt: 'Apaga-se tudo', fr: 'Tout s’éteint', de: 'Alles geht aus', en: 'Everything goes dark'},
  plantsLimit: {es: 'Por debajo, las centrales se desconectan', pt: 'Abaixo, as centrais desligam-se', fr: 'En dessous, les centrales décrochent', de: 'Darunter gehen Kraftwerke vom Netz', en: 'Below this, plants disconnect'},
  avalanche: {es: 'Última avalancha', pt: 'Última avalanche', fr: 'Dernière avalanche', de: 'Letzte Lawine', en: 'Last avalanche'},
  cellsWord: {es: '{n} casillas', pt: '{n} casas', fr: '{n} cases', de: '{n} Felder', en: '{n} cells'},
  grains: {es: 'Granos echados', pt: 'Grãos lançados', fr: 'Grains versés', de: 'Körner', en: 'Grains dropped'},
  sizes: {es: 'Cuántas avalanchas de cada tamaño', pt: 'Quantas avalanches de cada tamanho', fr: 'Combien d’avalanches de chaque taille', de: 'Wie viele Lawinen jeder Größe', en: 'How many avalanches of each size'},
  pileNote: {es: 'Montón de arena de Bak, Tang y Wiesenfeld (1987) · una casilla con 4 granos los reparte a sus 4 vecinas', pt: 'Monte de areia de Bak, Tang e Wiesenfeld (1987) · uma casa com 4 grãos reparte-os pelas 4 vizinhas', fr: 'Tas de sable de Bak, Tang et Wiesenfeld (1987) · une case à 4 grains les donne à ses 4 voisines', de: 'Sandhaufen von Bak, Tang und Wiesenfeld (1987) · ein Feld mit 4 Körnern gibt sie an seine 4 Nachbarn', en: 'Bak, Tang and Wiesenfeld’s sandpile (1987) · a cell with 4 grains gives them to its 4 neighbours'},
  withPower: {es: 'Con luz', pt: 'Com luz', fr: 'Avec courant', de: 'Mit Strom', en: 'With power'},
  hoursSince: {es: 'Horas desde el apagón', pt: 'Horas desde o apagão', fr: 'Heures depuis le black-out', de: 'Stunden seit dem Blackout', en: 'Hours since the blackout'},
  synced: {es: 'Islas sincronizadas', pt: 'Ilhas sincronizadas', fr: 'Îlots synchronisés', de: 'Inseln synchronisiert', en: 'Islands synchronised'},
  rushFail: {es: 'Demasiado consumo de golpe: vuelta a empezar', pt: 'Demasiado consumo de uma vez: volta ao início', fr: 'Trop de consommation d’un coup : on recommence', de: 'Zu viel Verbrauch auf einmal: von vorn', en: 'Too much load at once: start again'},
  selfStart: {es: 'Arrancan solas', pt: 'Arrancam sozinhas', fr: 'Démarrent seules', de: 'Starten von selbst', en: 'Start on their own'},
  islandSaved: {es: 'La isla se salva', pt: 'A ilha salva-se', fr: 'L’îlot est sauvé', de: 'Die Insel bleibt am Netz', en: 'The island is saved'},
  separates: {es: 'Se separa a tiempo', pt: 'Separa-se a tempo', fr: 'Se sépare à temps', de: 'Trennt sich rechtzeitig', en: 'Separates in time'},
  gridNote2: {es: 'Simulación · reparto de la corriente por las leyes de Kirchhoff · cada línea aguanta su carga normal + {m} % · cascada de Motter y Lai (2002)', pt: 'Simulação · repartição da corrente pelas leis de Kirchhoff · cada linha aguenta a sua carga normal + {m} % · cascata de Motter e Lai (2002)', fr: 'Simulation · répartition du courant par les lois de Kirchhoff · chaque ligne tient sa charge normale + {m} % · cascade de Motter et Lai (2002)', de: 'Simulation · Stromverteilung nach den Kirchhoffschen Gesetzen · jede Leitung trägt ihre normale Last + {m} % · Kaskade nach Motter und Lai (2002)', en: 'Simulation · current shared by Kirchhoff’s laws · each line carries its normal load + {m} % · Motter and Lai’s cascade (2002)'},
  freqNote: {es: 'Simulación · inercia {h} s · se pierde el {p} % de la producción · deslastre a 49,0 y 48,7 Hz · centrales fuera por debajo de 48,8 Hz', pt: 'Simulação · inércia {h} s · perde-se {p} % da produção · deslastre a 49,0 e 48,7 Hz · centrais fora abaixo de 48,8 Hz', fr: 'Simulation · inertie {h} s · {p} % de la production perdue · délestage à 49,0 et 48,7 Hz · centrales hors service sous 48,8 Hz', de: 'Simulation · Trägheit {h} s · {p} % der Erzeugung fallen aus · Lastabwurf bei 49,0 und 48,7 Hz · Kraftwerke aus unter 48,8 Hz', en: 'Simulation · inertia {h} s · {p} % of production lost · load shedding at 49.0 and 48.7 Hz · plants out below 48.8 Hz'},
  hotDay: {es: '14 de agosto · 35 °C · las líneas van cargadas', pt: '14 de agosto · 35 °C · as linhas vão carregadas', fr: '14 août · 35 °C · les lignes sont chargées', de: '14. August · 35 °C · die Leitungen sind voll', en: 'August 14 · 35 °C · the lines are loaded'},
});

const STEP = 0.75;                       // seconds between one wave of the cascade and the next
const fmtClock = (s: number) => `${Math.floor(s / 3600)}:${String(Math.floor((s % 3600) / 60)).padStart(2, '0')}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
const hz = (f: number) => num(Math.max(0, f), 2);

// --- the fixed geometry: each city's houses ---------------------------------------------------------------------------------
type House = {x: number; y: number; w: number; h: number; d: number};       // d: 0 → 1, when it goes dark within its city
const HOUSES = new Map<string, House[][]>();
const housesOf = (G: Grid) => {
  if (!HOUSES.has(G.key)) {
    HOUSES.set(G.key, G.nodes.map((n, i) => {
      if (n.kind !== 'city') return [];
      const rnd = mulberry(100 + i);
      const count = Math.round(10 + Math.min(7, n.size) * 9);
      const r = 14 + Math.min(7, n.size) * 6;
      return Array.from({length: count}, () => {
        const a = rnd() * Math.PI * 2;
        const d = Math.sqrt(rnd()) * r;
        return {x: n.x + Math.cos(a) * d, y: n.y + Math.sin(a) * d * 0.8, w: 5 + rnd() * 5, h: 5 + rnd() * 4, d: rnd()};
      });
    }));
  }
  return HOUSES.get(G.key)!;
};

/** The grid being drawn (set per frame from the shot: its country, by the video's language or params.pais). */
let G: Grid = gridOf('iberia');

// --- drawing ----------------------------------------------------------------------------------------------------------------
const LIVE = '#9fe8ff';
const DEAD = '#2b3446';

/** A pylon from above: a small lattice cross. */
const pylons = (a: number, b: number) => {
  const [x1, y1, x2, y2] = [G.nodes[a].x, G.nodes[a].y, G.nodes[b].x, G.nodes[b].y];
  const len = Math.hypot(x2 - x1, y2 - y1);
  const n = Math.max(1, Math.floor(len / 40));
  return Array.from({length: n - 1}, (_, k) => [x1 + ((x2 - x1) * (k + 1)) / n, y1 + ((y2 - y1) * (k + 1)) / n]);
};

const PlantIcon: FC<{kind: string; x: number; y: number; on: number; t: number; s?: number}> = ({kind, x, y, on, t, s = 1}) => {
  const body = on > 0.5 ? '#dfe6ef' : '#4a5263';
  const glow = on > 0.5 ? 0.9 : 0;
  let icon: ReactElement;
  if (kind === 'nuclear') {
    icon = (
      <g>
        {[-11, 9].map((dx) => <path key={dx} d={`M${dx - 9},12 Q${dx - 5},0 ${dx - 7},-12 L${dx + 7},-12 Q${dx + 5},0 ${dx + 9},12 Z`} fill={body} stroke="#1b2230" strokeWidth={1.5} />)}
        {on > 0.5 && [0, 1, 2].map((k) => {
          const p = (t * 0.5 + k / 3) % 1;
          return <circle key={k} cx={-11 + 3 * p} cy={-14 - 22 * p} r={5 + 7 * p} fill="#ffffff" opacity={0.35 * (1 - p)} />;
        })}
      </g>
    );
  } else if (kind === 'cc') {
    icon = (
      <g>
        <rect x={-14} y={-4} width={22} height={16} fill={body} stroke="#1b2230" strokeWidth={1.5} />
        {[10, 15].map((cx) => <rect key={cx} x={cx - 2} y={-18} width={4} height={30} fill={body} stroke="#1b2230" strokeWidth={1} />)}
        {on > 0.5 && [0, 1].map((k) => {
          const p = (t * 0.6 + k / 2) % 1;
          return <circle key={k} cx={12 + 4 * p} cy={-20 - 16 * p} r={3 + 5 * p} fill="#c9d1db" opacity={0.4 * (1 - p)} />;
        })}
      </g>
    );
  } else if (kind === 'hidro') {
    icon = (
      <g>
        <path d="M-16,-10 Q0,4 16,-10 L16,-4 Q0,10 -16,-4 Z" fill={body} stroke="#1b2230" strokeWidth={1.5} />
        <path d="M-16,-12 Q0,-2 16,-12 L16,-22 L-16,-22 Z" fill="#2f6fae" opacity={0.85} />
        {on > 0.5 && <path d={`M-4,6 Q0,${12 + 3 * Math.sin(t * 6)} 4,6`} stroke="#8fd3ff" strokeWidth={3} fill="none" />}
      </g>
    );
  } else if (kind === 'solar') {
    icon = (
      <g>
        {Array.from({length: 9}, (_, k) => (
          <rect key={k} x={-18 + (k % 3) * 13} y={-14 + Math.floor(k / 3) * 10} width={11} height={8} fill={on > 0.5 ? '#2f63c4' : '#2a3242'}
                stroke={on > 0.5 ? '#9fc1ff' : '#3a4252'} strokeWidth={1} />
        ))}
      </g>
    );
  } else if (kind === 'eolica') {
    const a = on > 0.5 ? t * 160 : 20;
    icon = (
      <g>
        {[-10, 10].map((dx, k) => (
          <g key={dx} transform={`translate(${dx} ${k ? 4 : -4})`}>
            <circle r={2.5} fill={body} />
            {[0, 120, 240].map((b) => <line key={b} x1={0} y1={0} x2={0} y2={-14} stroke={body} strokeWidth={2.5} strokeLinecap="round"
                                             transform={`rotate(${a + b + k * 40})`} />)}
          </g>
        ))}
      </g>
    );
  } else {
    icon = <circle r={8} fill={body} />;
  }
  return (
    <g transform={`translate(${x} ${y}) scale(${s})`}>
      {glow > 0 && <circle r={26} fill={C.you} opacity={0.08} />}
      {icon}
    </g>
  );
};

type MapState = {
  lineOn: (e: number) => boolean;
  flow?: number[];
  dark: (i: number) => number;          // 0 lit → 1 dark (houses go off in turn)
  heat?: (e: number) => number;         // 0 → 1 line load against its limit (overlay load)
  flash?: (e: number) => number;        // a line tripping now
  t: number;
  shed?: (i: number) => boolean;        // cut on purpose (a yellow ring)
  labels?: boolean;
};

const heatColour = (h: number) => (h < 0.85 ? '#3ddc84' : h < 1 ? '#f5b324' : '#ff4b4b');

/** The peninsula: sea, land, border, lines with the current running, plants, cities. `k`, `ox`, `oy`: scale and place. */
const GridMap: FC<{s: MapState; k?: number; ox?: number; oy?: number; clip?: [number, number]}> = ({s, k = 1, ox = 0, oy = 0, clip}) => {
  const flow = s.flow ?? G.base.flow;
  return (
    <svg width={1920} height={1080} style={{position: 'absolute', ...(clip ? {clipPath: `inset(0 ${1920 - clip[0] - clip[1]}px 0 ${clip[0]}px)`} : {})}}>
      <defs>
        <radialGradient id="sea" cx="50%" cy="45%" r="75%"><stop offset="0%" stopColor="#0d1e36" /><stop offset="100%" stopColor="#050b16" /></radialGradient>
        <linearGradient id="land" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#1c2a3d" /><stop offset="100%" stopColor="#172233" /></linearGradient>
      </defs>
      <rect width={1920} height={1080} fill="url(#sea)" />
      <g transform={`translate(${ox} ${oy}) scale(${k})`}>
        <path d={G.coast} fill="none" stroke="#1f3b5e" strokeWidth={18} opacity={0.35} strokeLinejoin="round" />
        <path d={G.coast} fill="url(#land)" stroke="#3a5478" strokeWidth={3} strokeLinejoin="round" />
        {G.lakes.map((d, j) => <path key={`l${j}`} d={d} fill="#0b1a30" stroke="#3a5478" strokeWidth={2} />)}
        {G.borders.map((d, j) => <path key={`b${j}`} d={d} fill="none" stroke="#3a4a63" strokeWidth={2} strokeDasharray="8 7" />)}
        {G.names.map((n) => (
          <text key={n.word} x={n.x} y={n.y} fill="rgba(255,255,255,0.07)" fontFamily={FONT} fontSize={n.size} fontWeight={800} textAnchor="middle">
            {tx(n.word).toUpperCase()}
          </text>
        ))}
        {/* lines: pylons, the cable, and the current running along it */}
        {G.edges.map(([a, b], e) => {
          const on = s.lineOn(e);
          const f = flow[e] ?? 0;
          const [from, to] = f >= 0 ? [a, b] : [b, a];
          const w = on ? 1.5 + Math.min(5, Math.abs(f) * 1.6) : 1.5;
          const colour = !on ? DEAD : s.heat ? heatColour(s.heat(e)) : LIVE;
          const flash = s.flash?.(e) ?? 0;
          return (
            <g key={e}>
              {pylons(a, b).map(([x, y], j) => <path key={j} d={`M${x - 3},${y - 3} L${x + 3},${y + 3} M${x + 3},${y - 3} L${x - 3},${y + 3}`} stroke="#56627a" strokeWidth={1.5} />)}
              <line x1={G.nodes[a].x} y1={G.nodes[a].y} x2={G.nodes[b].x} y2={G.nodes[b].y} stroke={colour} strokeWidth={w} opacity={on ? 0.35 : 0.5}
                    strokeDasharray={on ? undefined : '5 7'} />
              {on && Math.abs(f) > 0.02 && (
                <line x1={G.nodes[from].x} y1={G.nodes[from].y} x2={G.nodes[to].x} y2={G.nodes[to].y} stroke={colour} strokeWidth={w} strokeLinecap="round"
                      strokeDasharray="6 22" strokeDashoffset={-(s.t * (40 + 60 * Math.min(2, Math.abs(f)))) % 28} opacity={0.95} />
              )}
              {flash > 0 && <line x1={G.nodes[a].x} y1={G.nodes[a].y} x2={G.nodes[b].x} y2={G.nodes[b].y} stroke={C.red} strokeWidth={8 * flash + 2} opacity={flash} strokeLinecap="round" />}
            </g>
          );
        })}
        {/* plants and links */}
        {G.nodes.map((n, i) => {
          if (n.kind === 'city') return null;
          const off = s.dark(i) > 0.5;
          if (n.kind === 'link') {
            return (
              <g key={i}>
                <circle cx={n.x} cy={n.y} r={9} fill={off ? DEAD : LIVE} stroke="#0b1020" strokeWidth={3} />
                <text x={n.x} y={n.y + (n.y < 200 ? -18 : 32)} textAnchor="middle" fill={C.label} fontFamily={FONT} fontSize={24} fontWeight={800}>{tx(n.name).toUpperCase()}</text>
              </g>
            );
          }
          return <PlantIcon key={i} kind={n.kind} x={n.x} y={n.y} on={off ? 0 : 1} t={s.t + i} s={0.9 + n.size * 0.15} />;
        })}
        {/* cities: their houses, lit or not */}
        {G.cities.map((i) => {
          const n = G.nodes[i];
          const dk = s.dark(i);
          const shed = s.shed?.(i);
          return (
            <g key={i}>
              {dk < 1 && <circle cx={n.x} cy={n.y} r={(22 + n.size * 9) * 1.6} fill="#ffcf73" opacity={0.13 * (1 - dk)} />}
              {housesOf(G)[i].map((h, j) => {
                const off = dk > h.d;
                const twinkle = off && ((j * 7919 + Math.floor(s.t * 1.5) * 31) % 23 === 0);       // a torch, a phone
                return <rect key={j} x={h.x - h.w / 2} y={h.y - h.h / 2} width={h.w} height={h.h} rx={1}
                             fill={off ? (twinkle ? '#cfe3ff' : '#38425a') : '#ffd88a'} opacity={off ? (twinkle ? 0.9 : 1) : 0.95} />;
              })}
              {shed && <circle cx={n.x} cy={n.y} r={30 + n.size * 8} fill="none" stroke={C.you} strokeWidth={3} strokeDasharray="6 5" />}
              {(s.labels ?? true) && n.size >= 0.9 && (
                <text x={n.x} y={n.y + 26 + n.size * 7} textAnchor="middle" fill={dk > 0.5 ? '#5d6880' : '#f2f4f8'} fontFamily={FONT} fontSize={22} fontWeight={800}
                      style={{paintOrder: 'stroke'}} stroke="#0b1020" strokeWidth={4}>{n.name.toUpperCase()}</text>
              )}
            </g>
          );
        })}
      </g>
    </svg>
  );
};

// --- the cascade, as the map sees it at a moment ------------------------------------------------------------------------------
const cascadeState = (waves: {lines: number[]; dark: boolean[]; flow: number[]}[], since: number, t: number) => {
  const k = Math.floor(since / STEP);                         // the wave we are at (−1: before the fault)
  const off = new Map<number, number>();                      // line → when it tripped
  const darkAt = new Map<number, number>();                   // node → when it went dark
  waves.slice(0, Math.max(0, k + 1)).forEach((w, j) => {
    w.lines.forEach((e) => off.has(e) || off.set(e, j * STEP));
    w.dark.forEach((d, i) => d && !darkAt.has(i) && darkAt.set(i, j * STEP + 0.25));
  });
  const flow = k >= 0 ? waves[Math.min(k, waves.length - 1)].flow : G.base.flow;
  const state: MapState = {
    t,
    lineOn: (e) => !off.has(e),
    flow,
    dark: (i) => (darkAt.has(i) ? Math.min(1, Math.max(0, (since - darkAt.get(i)!) / 1.2)) : 0),
    flash: (e) => (off.has(e) ? interpolate(since - off.get(e)!, [0, 0.6], [1, 0], clamp) : 0),
  };
  const dark = G.nodes.map((_, i) => darkAt.has(i) && since >= darkAt.get(i)!);
  const done = k >= waves.length - 1;
  return {state, dark, off, done, end: (waves.length - 1) * STEP + 1.2};
};

const DarkPanel: FC<{dark: boolean[]; o: number; clock?: number}> = ({dark, o, clock}) => {
  const share = G.darkShare(dark);
  return (
    <Big o={o} label={tx('peopleDark')} value={`${Math.round(share * 100)} %`} color={share > 0.3 ? C.red : C.text}
         sub={clock !== undefined && clock > 0 ? `${tx('millionsOf', {n: Math.round(share * G.people), m: G.people})} · ${fmtClock(clock)}`
           : tx('millionsOf', {n: Math.round(share * G.people), m: G.people})}
         style={{right: 48, top: 52, width: 400}} />
  );
};

// --- the scenes ---------------------------------------------------------------------------------------------------------------
const FreqGauge: FC<{f: number; x: number; y: number; r?: number}> = ({f, x, y, r = 210}) => {
  const lo = 47.5;
  const hi = 51;
  const ang = (v: number) => Math.PI * (1 - (Math.max(lo, Math.min(hi, v)) - lo) / (hi - lo));
  const pt = (v: number, rr: number) => [x + Math.cos(ang(v)) * rr, y - Math.sin(ang(v)) * rr];
  const arc = (a: number, b: number, colour: string) => {
    const [x1, y1] = pt(a, r);
    const [x2, y2] = pt(b, r);
    return <path d={`M${x1},${y1} A${r},${r} 0 0 1 ${x2},${y2}`} stroke={colour} strokeWidth={22} fill="none" />;
  };
  const [nx, ny] = pt(f, r - 30);
  const colour = f > 49.8 ? C.green : f > 49 ? '#f5b324' : C.red;
  return (
    <svg width={1920} height={1080} style={{position: 'absolute', pointerEvents: 'none'}}>
      {arc(lo, 48.8, '#7a1f1f')}{arc(48.8, 49.5, '#7a5a12')}{arc(49.5, 50.5, '#1d6b45')}{arc(50.5, hi, '#7a5a12')}
      {[48, 49, 50, 51].map((v) => {
        const [tx1, ty1] = pt(v, r + 16);
        const [tx2, ty2] = pt(v, r + 42);
        return (
          <g key={v}>
            <line x1={pt(v, r - 12)[0]} y1={pt(v, r - 12)[1]} x2={tx1} y2={ty1} stroke="#fff" strokeWidth={3} />
            <text x={tx2} y={ty2 + 8} textAnchor="middle" fill={C.label} fontFamily={FONT} fontSize={26} fontWeight={800}>{v}</text>
          </g>
        );
      })}
      <line x1={x} y1={y} x2={nx} y2={ny} stroke={colour} strokeWidth={8} strokeLinecap="round" />
      <circle cx={x} cy={y} r={14} fill={colour} />
      <text x={x} y={y + 80} textAnchor="middle" fill={colour} fontFamily={FONT} fontSize={86} fontWeight={800} style={{fontVariantNumeric: 'tabular-nums'}}>{hz(f)} Hz</text>
    </svg>
  );
};

/** The balance: production on one pan, consumption on the other; it tilts with the imbalance. */
const Scale: FC<{prod: number; cons: number; x: number; y: number}> = ({prod, cons, x, y}) => {
  const tilt = Math.max(-18, Math.min(18, (cons - prod) * 140));
  const pan = (side: number, label: string, value: number, colour: string) => {
    const px = x + side * 190 * Math.cos((tilt * Math.PI) / 180);
    const py = y + side * 190 * Math.sin((tilt * Math.PI) / 180);
    return (
      <g>
        <line x1={px} y1={py} x2={px - 60} y2={py + 70} stroke="#9aa3ad" strokeWidth={2} />
        <line x1={px} y1={py} x2={px + 60} y2={py + 70} stroke="#9aa3ad" strokeWidth={2} />
        <path d={`M${px - 75},${py + 70} Q${px},${py + 110} ${px + 75},${py + 70} Z`} fill={colour} />
        <text x={px} y={py + 140} textAnchor="middle" fill={C.text} fontFamily={FONT} fontSize={28} fontWeight={800}>{label.toUpperCase()}</text>
        <text x={px} y={py + 172} textAnchor="middle" fill={colour} fontFamily={FONT} fontSize={30} fontWeight={800}>{Math.round(value * 100)} %</text>
      </g>
    );
  };
  return (
    <svg width={1920} height={1080} style={{position: 'absolute', pointerEvents: 'none'}}>
      <path d={`M${x - 26},${y + 230} L${x},${y} L${x + 26},${y + 230} Z`} fill="#4c535e" />
      <line x1={x - 190 * Math.cos((tilt * Math.PI) / 180)} y1={y - 190 * Math.sin((tilt * Math.PI) / 180)}
            x2={x + 190 * Math.cos((tilt * Math.PI) / 180)} y2={y + 190 * Math.sin((tilt * Math.PI) / 180)} stroke="#c9ced6" strokeWidth={8} strokeLinecap="round" />
      {pan(-1, tx('production'), prod, '#3ddc84')}
      {pan(1, tx('consumption'), cons, '#ffcf73')}
    </svg>
  );
};

const FreqChart: FC<{r: FreqRun; t: number; x: number; y: number; w: number; h: number; colour: string}> = ({r, t, x, y, w, h, colour}) => {
  const lo = 47.5;
  const hi = 50.3;
  const span = 20;
  const Yf = (f: number) => y + h - ((Math.max(lo, Math.min(hi, f)) - lo) / (hi - lo)) * h;
  const pts: string[] = [];
  for (let s = 0; s <= Math.min(t, span); s += 0.1) pts.push(`${(x + (s / span) * w).toFixed(1)},${Yf(freqAt(r, s)).toFixed(1)}`);
  return (
    <svg width={1920} height={1080} style={{position: 'absolute', pointerEvents: 'none'}}>
      <rect x={x} y={y} width={w} height={h} fill="rgba(255,255,255,0.03)" rx={6} />
      <line x1={x} x2={x + w} y1={Yf(50)} y2={Yf(50)} stroke="rgba(255,255,255,0.25)" strokeDasharray="6 6" />
      <line x1={x} x2={x + w} y1={Yf(48.8)} y2={Yf(48.8)} stroke={C.red} strokeWidth={2} strokeDasharray="10 8" />
      <text x={x + w - 8} y={Yf(48.8) - 10} textAnchor="end" fill={C.red} fontFamily={FONT} fontSize={22} fontWeight={800}>48,8 Hz · {tx('plantsLimit').toUpperCase()}</text>
      <text x={x + 8} y={Yf(50) - 10} fill={C.label} fontFamily={FONT} fontSize={22} fontWeight={800}>50 Hz</text>
      <polyline points={pts.join(' ')} fill="none" stroke={colour} strokeWidth={5} strokeLinejoin="round" />
    </svg>
  );
};

const Turbines: FC<{f: number; spin: number; x: number; y: number}> = ({f, spin, x, y}) => (
  <svg width={1920} height={1080} style={{position: 'absolute', pointerEvents: 'none'}}>
    {[0, 1, 2].map((k) => {
      const cx = x + (k - 1) * 230;
      const ang = spin * 360 + k * 30;
      return (
        <g key={k} transform={`translate(${cx} ${y})`}>
          <circle r={95} fill="#2a3242" stroke="#5b6475" strokeWidth={6} />
          <circle r={95} fill="none" stroke={f > 48 ? '#9fe8ff' : '#3a4252'} strokeWidth={3} strokeDasharray="20 12" transform={`rotate(${ang})`} />
          {Array.from({length: 8}, (_, j) => <rect key={j} x={-4} y={-88} width={8} height={70} rx={3} fill="#c9ced6" transform={`rotate(${ang + j * 45})`} />)}
          <circle r={22} fill="#7f8896" />
        </g>
      );
    })}
  </svg>
);

const SolarField: FC<{x: number; y: number; on: boolean}> = ({x, y, on}) => (
  <svg width={1920} height={1080} style={{position: 'absolute', pointerEvents: 'none'}}>
    {Array.from({length: 18}, (_, k) => (
      <g key={k} transform={`translate(${x - 300 + (k % 6) * 100} ${y - 110 + Math.floor(k / 6) * 80}) skewX(-12)`}>
        <rect width={86} height={56} rx={3} fill={on ? '#2f63c4' : '#2a3242'} stroke={on ? '#9fc1ff' : '#3a4252'} strokeWidth={2} />
        {[1, 2, 3].map((j) => <line key={j} x1={(86 * j) / 4} x2={(86 * j) / 4} y1={0} y2={56} stroke="rgba(255,255,255,0.25)" />)}
      </g>
    ))}
    <rect x={x + 330} y={y - 40} width={70} height={90} rx={6} fill="#4c535e" stroke="#8a919b" strokeWidth={2} />
    <text x={x + 365} y={y + 12} textAnchor="middle" fill={C.text} fontFamily={FONT} fontSize={30} fontWeight={800}>≈</text>
  </svg>
);

const Pile: FC<{grid: Uint8Array; hit: Uint16Array; fresh: number}> = ({grid, hit, fresh}) => {
  const ref = useRef<HTMLCanvasElement>(null);
  const cell = 40;
  useLayoutEffect(() => {
    const ctx = ref.current?.getContext('2d');
    if (!ctx) return;
    const shades = ['#14202f', '#3b3a2c', '#8a6d33', '#e0a84a'];
    for (let i = 0; i < grid.length; i++) {
      ctx.fillStyle = shades[grid[i]];
      ctx.fillRect((i % PILE.w) * cell, Math.floor(i / PILE.w) * cell, cell - 2, cell - 2);
    }
    if (fresh > 0) {
      ctx.fillStyle = `rgba(255,255,255,${0.75 * fresh})`;
      for (const i of hit) ctx.fillRect((i % PILE.w) * cell, Math.floor(i / PILE.w) * cell, cell - 2, cell - 2);
    }
  }, [grid, hit, fresh]);
  return <canvas ref={ref} width={PILE.w * cell} height={PILE.h * cell} style={{position: 'absolute', left: 0, top: 0}} />;
};

// a side view of one line on a hot afternoon: it heats, sags, touches the trees and trips
const Sag: FC<{since: number; touchAt: number}> = ({since, touchAt}) => {
  const p = Math.min(1, Math.max(0, since / touchAt));
  const after = since - touchAt;
  const sag = 70 + 190 * p;
  const temp = 45 + 50 * p;
  const load = 82 + 28 * p;
  const tripped = after > 0;
  const spark = after > 0 ? interpolate(after, [0, 0.12, 0.8], [0, 1, 0], clamp) : 0;
  const L = 320;
  const R = 1600;
  const top = 330;
  const curve = `M${L},${top} Q${(L + R) / 2},${top + 2 * sag} ${R},${top}`;
  return (
    <>
      <svg width={1920} height={1080} style={{position: 'absolute'}}>
        <defs><linearGradient id="hot" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#f2a65a" /><stop offset="100%" stopColor="#f7d49a" /></linearGradient></defs>
        <rect width={1920} height={1080} fill="url(#hot)" />
        <circle cx={1650} cy={150} r={70} fill="#fff4c9" opacity={0.9} />
        {/* heat shimmer over the ground */}
        {Array.from({length: 6}, (_, k) => <path key={k} d={`M${200 + k * 280},860 q20,-${10 + 6 * Math.sin(since * 3 + k)} 40,0 t40,0`} stroke="rgba(255,255,255,0.35)" fill="none" strokeWidth={3} />)}
        <rect y={860} width={1920} height={220} fill="#a58a4f" />
        {/* the trees nobody pruned, right under the middle of the span */}
        {[-170, -60, 50, 160].map((dx, k) => (
          <g key={dx} transform={`translate(${960 + dx} 860)`}>
            <rect x={-10} y={-120} width={20} height={120} fill="#5b3f24" />
            <circle cx={0} cy={-200 - (k % 2) * 30} r={95} fill={k % 2 ? '#3f6b35' : '#4c7d3e'} />
          </g>
        ))}
        {/* pylons */}
        {[L, R].map((x) => (
          <g key={x}>
            <path d={`M${x - 70},860 L${x - 18},${top - 40} L${x + 18},${top - 40} L${x + 70},860`} fill="none" stroke="#5d6470" strokeWidth={8} />
            {Array.from({length: 7}, (_, k) => {
              const y1 = 860 - k * 80;
              const w = 70 - (k * 52) / 7;
              return <path key={k} d={`M${x - w},${y1} L${x + w - 8},${y1 - 80} M${x + w},${y1} L${x - w + 8},${y1 - 80}`} stroke="#6c7480" strokeWidth={3} />;
            })}
            <line x1={x - 90} x2={x + 90} y1={top - 10} y2={top - 10} stroke="#5d6470" strokeWidth={10} />
          </g>
        ))}
        <path d={curve} fill="none" stroke={tripped ? '#3a3f47' : interpolate(p, [0, 1], [0, 1]) > 0.7 ? '#ff7a2f' : '#2b2f36'} strokeWidth={7} />
        {!tripped && <path d={curve} fill="none" stroke="#ffdf7a" strokeWidth={3} strokeDasharray="12 30" strokeDashoffset={-since * 120} opacity={0.8} />}
        {spark > 0 && (
          <g opacity={spark}>
            <circle cx={960} cy={top + sag} r={120 * spark} fill="#ffffff" opacity={0.6} />
            <path d={`M960,${top + sag} l-30,60 l40,10 l-30,70 M960,${top + sag} l35,50 l-25,20 l40,60`} stroke="#fff" strokeWidth={6} fill="none" />
          </g>
        )}
      </svg>
      <Big o={1} label={tx('lineTemp')} value={`${Math.round(temp)} °C`} color={temp > 80 ? C.red : C.text} style={{left: 48, top: 52, width: 330}} />
      <Big o={1} label={tx('lineLoadNow')} value={tripped ? '0 %' : `${Math.round(load)} %`} color={load > 100 && !tripped ? C.red : C.text}
           sub={tripped ? tx('tripped').toUpperCase() : undefined} style={{left: 400, top: 52, width: 300}} />
      {after > 1.2 && (
        <Panel o={interpolate(after, [1.2, 1.6], [0, 1], clamp)} style={{right: 48, top: 52, width: 380}}>
          <div style={{fontSize: 40, fontWeight: 800, color: C.red, textTransform: 'uppercase'}}>🔕 {tx('alarmOff')}</div>
        </Panel>
      )}
    </>
  );
};

const mid = (e: number) => ({x: (G.nodes[G.edges[e][0]].x + G.nodes[G.edges[e][1]].x) / 2, y: (G.nodes[G.edges[e][0]].y + G.nodes[G.edges[e][1]].y) / 2});

// --- the world ----------------------------------------------------------------------------------------------------------------
const View: FC<WorldProps> = ({g, worldT, local, real = local, o, on}) => {
  G = gridOf(countryOf(param<string>(g, 'pais', ''), g.lang));
  const scene = param<string>(g, 'scene', 'cascada');
  const margin = param(g, 'margin', 0.15);
  const panel = Math.max(o('panel'), o('cascade'), on * 0.9);
  const failAt = (g.cues?.fail ?? g.since + 3) - g.since;          // seconds into this world
  const since = worldT - failAt;
  const t = worldT;
  const marks: Record<string, Anchor | null> = {};
  const firstLine = G.edges[G.first[0]];
  marks.fail = {x: (G.nodes[firstLine[0]].x + G.nodes[firstLine[1]].x) / 2, y: (G.nodes[firstLine[0]].y + G.nodes[firstLine[1]].y) / 2};
  marks.france = {x: G.nodes[G.links[0]].x, y: G.nodes[G.links[0]].y + 20};
  let body: ReactElement;
  let note = tx('gridNote2', {m: Math.round(margin * 100)});

  if (scene === 'combado') {
    body = <Sag since={worldT} touchAt={Math.max(4, failAt + 3)} />;
    note = tx('hotDay');
  } else if (scene === 'frecuencia') {
    const shedding = param<string>(g, 'deslastre', 'si') !== 'no';
    const r = frequency(3, 0.12, shedding);
    const tt = Math.max(0, (worldT - failAt) * 0.6 + 2);              // a little slower than real time
    const i = Math.min(r.f.length - 1, Math.round(tt / 0.05));
    const collapsed = r.collapse >= 0 && tt >= r.collapse;
    const f = collapsed ? 0 : freqAt(r, tt);
    const shed = r.shed[i];
    const lost = r.tripped[i];
    const shedCities = G.cities.filter((c) => G.nodes[c].size < 0.9).slice(0, shed > 0.07 ? 6 : shed > 0 ? 3 : 0);
    const state: MapState = {
      t, lineOn: () => !collapsed, dark: (c) => (collapsed ? 1 : shedCities.includes(c) ? 1 : 0), shed: (c) => shedCities.includes(c), labels: false,
    };
    body = (
      <>
        <GridMap s={state} k={0.6} ox={-170} oy={130} />
        <FreqGauge f={f} x={1380} y={430} />
        <Scale prod={collapsed ? 0 : 1 - lost + Math.min(0.1, 0.4 * (50 - f))} cons={collapsed ? 0 : 1 - shed} x={1380} y={640} />
        <Panel o={lost > 0.13 || shed > 0 || collapsed ? 1 : 0} style={{left: 48, top: 52, width: 760}}>
          <div style={{fontSize: 36, fontWeight: 800, textTransform: 'uppercase', color: collapsed ? C.red : shed > 0 ? C.you : C.red}}>
            {collapsed ? tx('blackoutAll') : shed > 0 ? tx('shedding') : tx('plantsTrip')}
          </div>
        </Panel>
      </>
    );
    note = tx('freqNote', {h: 3, p: 12});
  } else if (scene === 'inercia') {
    const tt = Math.max(0, (worldT - failAt) * 0.7 + 2);
    const a = frequency(6, 0.08, false);
    const b = frequency(1.5, 0.08, false);
    const fa = a.collapse >= 0 && tt >= a.collapse ? 0 : freqAt(a, tt);
    const fb = b.collapse >= 0 && tt >= b.collapse ? 0 : freqAt(b, tt);
    const spinA = (worldT * 0.9 * Math.min(1, fa / 50));
    body = (
      <>
        <AbsoluteFill style={{background: '#0b1324'}} />
        <Turbines f={fa} spin={spinA} x={480} y={330} />
        <SolarField x={1400} y={330} on={b.collapse < 0 || tt < b.collapse} />
        <div style={{position: 'absolute', left: 958, top: 0, width: 4, height: 1080, background: C.night}} />
        <SideTitle text={tx('spinning')} style={{left: 48, top: 40}} />
        <SideTitle text={tx('panels')} style={{left: 1010, top: 40}} />
        <FreqChart r={a} t={tt} x={60} y={560} w={840} h={360} colour={C.green} />
        <FreqChart r={b} t={tt} x={1020} y={560} w={840} h={360} colour={C.red} />
        <Big o={panel} label={tx('frequencyWord')} value={`${hz(fa)} Hz`} color={fa > 49 ? C.green : C.red}
             sub={tt > 8 ? tx('holds').toUpperCase() : undefined} style={{left: 600, top: 120, width: 320}} />
        <Big o={panel} label={tx('frequencyWord')} value={`${hz(fb)} Hz`} color={fb > 49 ? C.text : C.red}
             sub={b.collapse >= 0 && tt > b.collapse ? tx('falls').toUpperCase() : undefined} style={{left: 1560, top: 120, width: 320}} />
      </>
    );
    note = tx('freqNote', {h: '6 / 1,5', p: 8});
  } else if (scene === 'arena') {
    const pile = sandpile();
    const n = Math.max(0, Math.min(pile.grids.length - 1, Math.floor(worldT * 4)));
    const fresh = interpolate((worldT * 4) % 1, [0, 1], [1, 0.2], clamp);
    const sizes = pile.sizes.slice(0, n + 1);
    const bins = [1, 10, 100, 1000];
    const count = bins.map((b, k) => sizes.filter((s) => s >= b && s < (bins[k + 1] ?? 1e9)).length);
    const top = Math.max(1, ...count);
    body = (
      <>
        <Pile grid={pile.grids[n]} hit={pile.toppled[n]} fresh={fresh} />
        <Big o={panel} label={tx('avalanche')} value={tx('cellsWord', {n: num(pile.sizes[n])})} color={pile.sizes[n] > 100 ? C.red : C.text}
             sub={`${tx('grains')}: ${num(n + 1)}`} style={{right: 48, top: 52, width: 420}} />
        <Panel o={panel} style={{right: 48, top: 300, width: 420}}>
          <Label>{tx('sizes')}</Label>
          {count.map((c, k) => (
            <div key={k} style={{display: 'flex', alignItems: 'center', gap: 12, marginTop: 10, fontSize: 24, fontWeight: 800}}>
              <span style={{width: 110}}>{['1-9', '10-99', '100-999', '1000+'][k]}</span>
              <span style={{height: 22, width: 240 * (c / top), background: k > 1 ? C.red : C.accent, borderRadius: 3}} />
              <span>{c}</span>
            </div>
          ))}
        </Panel>
      </>
    );
    note = tx('pileNote');
  } else if (scene === 'arranque') {
    const rush = param<string>(g, 'golpe', 'no') === 'si';
    const rs = G.blackStart(rush);
    const stepT = 0.9;
    const k = Math.max(0, Math.min(rs.lit.length - 1, Math.floor(Math.max(0, worldT - failAt + 1) / stepT)));
    const lit = rs.lit[k];
    const share = 1 - G.darkShare(G.nodes.map((_, i) => !lit[i]));
    const merged = rs.merge.some((m) => k >= m && k < m + 2);
    const fell = rs.fallback.some((m) => k >= m && k < m + 3);
    const hours = 16 * Math.pow(k / Math.max(1, rs.lit.length - 1), 1.3);
    const state: MapState = {t, lineOn: (e) => !!(lit[G.edges[e][0]] && lit[G.edges[e][1]]), flow: G.base.flow, dark: (i) => (lit[i] ? 0 : 1)};
    body = (
      <>
        <GridMap s={state} />
        {fell && <AbsoluteFill style={{background: C.red, opacity: 0.12}} />}
        <Big o={panel} label={tx('withPower')} value={`${Math.round(share * 100)} %`} color={share > 0.6 ? C.green : C.text}
             sub={`${tx('hoursSince')}: ${num(hours, 0)} h`} style={{right: 48, top: 52, width: 400}} />
        {(merged || fell || k < 3) && (
          <Panel o={1} style={{left: 48, top: 52, width: 620}}>
            <div style={{fontSize: 34, fontWeight: 800, textTransform: 'uppercase', color: fell ? C.red : k < 3 ? C.text : C.green}}>
              {fell ? tx('rushFail') : k < 3 ? `💧 ${tx('selfStart')}` : tx('synced')}
            </div>
          </Panel>
        )}
      </>
    );
  } else if (scene === 'reparto') {
    const cut = since > 0;
    const after = G.flows(G.edges.map((_, e) => !G.first.includes(e)));
    const mix = cut ? interpolate(since, [0, 0.35], [0, 1], clamp) : 0;
    const flow = G.base.flow.map((f, e) => f + (after.flow[e] - f) * mix);
    const changes = G.edges.map((_, e) => e).filter((e) => !G.first.includes(e))
      .map((e) => [e, (Math.abs(after.flow[e]) - Math.abs(G.base.flow[e])) / Math.max(0.2, Math.abs(G.base.flow[e]))] as const)
      .sort((a, b) => b[1] - a[1])
      .filter(([e], k, all) => all.slice(0, k).every(([o]) => Math.hypot(mid(o).x - mid(e).x, mid(o).y - mid(e).y) > 110)).slice(0, 4);
    const state: MapState = {t, lineOn: (e) => !(cut && G.first.includes(e)), flow, dark: () => 0,
                             flash: (e) => (G.first.includes(e) && cut ? interpolate(since, [0, 0.6], [1, 0], clamp) : 0)};
    body = (
      <>
        <GridMap s={state} />
        {cut && changes.map(([e, d]) => {
          const [a, b] = G.edges[e];
          return (
            <div key={e} style={{position: 'absolute', left: (G.nodes[a].x + G.nodes[b].x) / 2 - 40, top: (G.nodes[a].y + G.nodes[b].y) / 2 - 24, fontFamily: FONT,
                                 fontSize: 28, fontWeight: 800, color: '#0b1020', background: C.you, borderRadius: 6, padding: '2px 8px', opacity: mix}}>
              +{Math.round(d * 100)} %
            </div>
          );
        })}
        <Panel o={cut ? 1 : 0} style={{left: 48, top: 52, width: 560}}>
          <div style={{fontSize: 32, fontWeight: 800, textTransform: 'uppercase'}}>{tx('flowChanges')}</div>
        </Panel>
      </>
    );
  } else {
    // cascada · isla
    const island = scene === 'isla';
    const c = island ? G.cascade(0.15, G.first, G.regionCut, G.withLink, G.region) : G.cascade(margin);
    const s = cascadeState(c.waves, since, t);
    const clock = s.done ? (since - s.end) * 30 : 0;               // the dark goes on: half a minute a second
    const linkCut = G.darkShare(s.dark) > 0.3 && !island;
    const xs = G.region.map((i) => G.nodes[i].x);
    const ys = G.region.map((i) => G.nodes[i].y);
    const zone = {x: (Math.min(...xs) + Math.max(...xs)) / 2, y: (Math.min(...ys) + Math.max(...ys)) / 2,
                  rx: (Math.max(...xs) - Math.min(...xs)) / 2 + 70, ry: (Math.max(...ys) - Math.min(...ys)) / 2 + 60};
    // past a third of the people in the dark, the links with the neighbours open to protect them
    const state: MapState = {...s.state, lineOn: (e) => s.state.lineOn(e) && !(linkCut && G.edges[e].some((i) => G.links.includes(i))),
                             heat: o('load') > 0.3 ? (e) => Math.abs((c.waves[0]?.flow ?? G.base.flow)[e]) / (Math.abs(G.base.flow[e]) * (1 + margin) + 0.2) : undefined};
    body = (
      <>
        <GridMap s={state} />
        {island && since > STEP && (
          <svg width={1920} height={1080} style={{position: 'absolute', pointerEvents: 'none'}}>
            <ellipse cx={zone.x} cy={zone.y} rx={zone.rx} ry={zone.ry} fill="none" stroke={C.you} strokeWidth={5} strokeDasharray="14 10"
                     opacity={interpolate(since, [STEP, STEP + 0.5], [0, 1], clamp)} />
            <text x={zone.x} y={zone.y - zone.ry - 16} textAnchor="middle" fill={C.you} fontFamily={FONT} fontSize={34} fontWeight={800}>
              {(s.done ? tx('islandSaved') : tx('separates')).toUpperCase()}
            </text>
          </svg>
        )}
        {linkCut && (
          <div style={{position: 'absolute', ...(G.nodes[G.links[0]].x > 1200 ? {right: 1920 - G.nodes[G.links[0]].x + 30} : {left: G.nodes[G.links[0]].x + 30}),
                       top: G.nodes[G.links[0]].y + 14, fontFamily: FONT, fontSize: 28, fontWeight: 800, color: C.red, textTransform: 'uppercase'}}>✕ {tx('linkCut')}</div>
        )}
        <DarkPanel dark={s.dark} o={since > 0 ? panel : 0} clock={clock} />
        <Big o={since > 0 ? panel * 0.95 : 0} label={tx('linesDown')} value={String(s.off.size)} color={s.off.size > 3 ? C.red : C.text}
             style={{right: 48, top: 260, width: 400}} />
        {o('fail') > 0 && (
          <div style={{position: 'absolute', left: marks.fail!.x + 30, top: marks.fail!.y - 50, fontFamily: FONT, fontSize: 30, fontWeight: 800,
                       color: C.you, textTransform: 'uppercase', opacity: o('fail')}}>⚡ {tx('firstFault')}</div>
        )}
      </>
    );
  }
  return (
    <AbsoluteFill style={{background: '#050b16'}}>
      {body}
      <Pointers marks={g.marks} local={real} at={marks} />
      <Note>{note}</Note>
    </AbsoluteFill>
  );
};

// a relay click at each wave of the cascade, a hit at the first fault and at a collapse
const sounds = (g: WorldProps['g'], length: number) => {
  G = gridOf(countryOf(param<string>(g, 'pais', ''), g.lang));
  const scene = param<string>(g, 'scene', 'cascada');
  const failAt = (g.cues?.fail ?? g.since + 3) - g.since;
  const t0 = g.at - g.since;
  const inShot = (s: number) => s - t0;
  const keep = (list: number[]) => list.map(inShot).filter((s) => s >= 0 && s < length);
  if (scene === 'cascada' || scene === 'isla') {
    const c = scene === 'isla' ? G.cascade(0.15, G.first, G.regionCut, G.withLink, G.region) : G.cascade(param(g, 'margin', 0.15));
    return {clicks: keep(c.waves.map((_, k) => failAt + k * STEP)), hits: keep([failAt])};
  }
  if (scene === 'combado') return {hits: keep([Math.max(4, failAt + 3)])};
  if (scene === 'reparto') return {hits: keep([failAt])};
  if (scene === 'frecuencia') {
    const r = frequency(3, 0.12, param<string>(g, 'deslastre', 'si') !== 'no');
    const at = (x: number) => failAt + (x - 2) / 0.6;
    const shedAt = r.t[r.shed.findIndex((s) => s > 0)];
    return {hits: keep([failAt, ...(r.collapse >= 0 ? [at(r.collapse)] : [])]), clicks: keep(shedAt !== undefined ? [at(shedAt)] : [])};
  }
  if (scene === 'arena') {
    const pile = sandpile();
    return {ticks: keep(pile.sizes.map((_, k) => k / 4).filter((_, k) => k % 2 === 0)), hits: keep(pile.sizes.map((s, k) => (s > 150 ? k / 4 : -1)).filter((s) => s >= 0))};
  }
  if (scene === 'arranque') {
    const rs = G.blackStart(param<string>(g, 'golpe', 'no') === 'si');
    return {clicks: keep(rs.merge.map((m) => failAt - 1 + m * 0.9)), hits: keep(rs.fallback.map((m) => failAt - 1 + m * 0.9))};
  }
  return {};
};

export const apagon: World = {View, sounds};
