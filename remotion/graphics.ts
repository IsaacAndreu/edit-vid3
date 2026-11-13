// Data of the animated graphics (timeline group kind "graphic"). Each one is drawn full screen over
// the shots it spans. The pipeline fills these from the script; the Showcase composition has samples.

import type { Media } from './types';

export interface GeoPoint {
  name: string;
  lon: number;
  lat: number;
  note?: string | null; // small line under the pin label ("1.º puesto", "2019")
  logo?: string | null; // company named there (Emirates in Dubai)
  logoMedia?: Media | null; // its logo (Wikimedia Commons), drawn in a round badge by the pin
  photo?: Media | null; // style 'pins': a photo of the place, pinned on the map as a polaroid
}

export interface MapGraphic {
  type: 'map';
  title?: string | null;
  countries?: string[]; // highlighted countries (English names, as in world-atlas)
  points?: GeoPoint[]; // pins, in the order they appear
  route?: boolean; // draw a line through the points in order (Manila → Tokyo → Paris)
  zoom?: number | null; // index of the point to zoom into at the end (country → city)
  globe?: boolean; // a rotating globe that turns to the first country/point
  date?: string | null; // said in the script: shown big over the map first ("17 de noviembre de 2013")
  regionLabel?: string | null; // name written inside the highlighted area ("SALÓN DE DUBÁI")
  rings?: { point: number; km: number; label?: string | null }[]; // range circles around points (ETOPS, autonomy)
  style?: 'pins' | null; // an old paper map that pans from place to place, a pinned polaroid at each
  ground?: { media: Media; west: number; north: number; east: number; south: number }[]; // satellite imagery under it
  credit?: string | null; // the imagery's credit, always on screen when there is ground
  earth?: { day: Media; night: Media; surface: Media; credit?: string | null } | null; // globe: photoreal Earth (Earth3D)
}

export interface RankGraphic {
  type: 'rank';
  rank: number;
  total?: number | null;
  name: string;
  subtitle?: string | null;
  media?: Media | null;
  stats?: { label: string; value: string }[];
}

export interface CompareSide {
  name: string;
  media?: Media | null;
  logo?: Media | null; // a brand's logo when there is no photo
}

export interface CompareGraphic {
  type: 'compare';
  title?: string | null;
  left: CompareSide;
  right: CompareSide;
  rows: { label: string; a: number; b: number; unit?: string | null; better?: 'high' | 'low' | null }[];
}

export interface ChartGraphic {
  type: 'chart';
  chart: 'bar' | 'line' | 'pie';
  title: string;
  unit?: string | null;
  data: { label: string; value: number }[];
  three?: boolean; // solid lit 3D bars (WebGL), set by the pipeline when graphics.bars_3d is on
  highlight?: string | null; // label to paint in the accent colour
}

export interface TimelineGraphic {
  type: 'timeline';
  title?: string | null;
  events: { year: string; text: string }[];
}

export interface SpecsGraphic {
  type: 'specs';
  kicker?: string | null; // small heading: "FICHA TÉCNICA" (products), "EN CIFRAS" (people)
  name: string;
  subtitle?: string | null;
  media?: Media | null;
  specs: { label: string; value: string; unit?: string | null }[];
}

export interface KineticGraphic {
  type: 'kinetic';
  lines: string[]; // each line appears word by word; the last word of the last line in yellow
  board?: boolean; // a shot with no footage: the words on the channel canvas (chalkboard) instead of over video
}

export interface ScoreGraphic {
  type: 'score';
  name?: string | null;
  title?: string | null;
  d: number;
  e: number;
  penalty?: number | null;
  total: number;
  labels: { d: string; e: string; penalty: string; total: string };
}

export interface PressGraphic {
  type: 'press';
  items: { outlet?: string | null; headline: string; date?: string | null; highlight?: string | null }[];
}

export interface QuoteGraphic {
  type: 'quote';
  speaker: string;
  role?: string | null;
  lines: { text: string; from: number; to: number }[]; // Spanish subtitles, frames from the start of the clip
}

export interface SatelliteGraphic {
  type: 'satellite';
  place: string;
  lon: number;
  lat: number;
  layers: { z: number; media: Media }[]; // 1920x1080 images centred on the place, wide → close
  labels?: { name: string; dx: number; dy: number }[]; // other spots, in pixels from the centre of the close view
  credit?: string | null; // imagery credit, always on screen
}

export interface ArticleGraphic {
  type: 'article';
  outlet?: string | null; // only if the script names it
  author?: string | null;
  headline: string;
  body: string; // 1-2 sentences of the script
  circles?: string[]; // figures/words of body circled in red one by one
}

export interface CitaGraphic {
  type: 'cita';
  speaker?: string | null; // who said it, as the script names them
  text: string; // the quote, literal from the script
  highlight?: string[] | null; // its key words, in red
  media?: Media | null; // the speaker (cutout, photo or a clip of the passage), in black and white
}

export interface RuleGraphic {
  type: 'rule';
  source: string; // "CÓDIGO DE PUNTUACIÓN" or the generic "REGLAMENTO"
  article?: string | null;
  text: string;
  highlight?: string | null; // part of text swept with the marker
  stamp?: string | null; // "PROHIBIDO": slammed over the page
}

export interface SplitGraphic {
  type: 'split';
  title?: string | null;
  left: CompareSide;
  right: CompareSide;
}

export interface BannedGraphic {
  type: 'banned';
  name: string;
  number?: number | null;
  who?: string | null;
  reason?: string | null;
  since?: string | null; // "DESDE 2017"
  stamp: string;
  media?: Media | null;
}

export interface SpotlightGraphic {
  type: 'spotlight';
  name: string;
  still: Media; // the frozen frame, full screen
  cutout: Media; // the same frame with only the person (transparent PNG)
  anchor: [number, number]; // centre-x and top of the person, % of the frame
  height?: number | null; // % of the frame the person fills
}

export interface StrobeGraphic {
  type: 'strobe';
  name: string; // the move ("Mortal Yurchenko")
  note?: string | null;
  background: Media; // the scene without the athlete
  ghosts: (Media & { x: number; y: number; w: number; h: number })[]; // each position, % of the frame
}

export interface ReplayGraphic {
  type: 'replay';
  name?: string | null; // label at the key moment
  badge: string; // "REPETICIÓN"
  video: Media; // the clip with the speed ramp already applied
  track: [number, number, number, number, number][]; // [s, x, y, w, h] (% of the frame) of the athlete
  peak: number; // s of the key moment (slow motion)
}

export interface StandingsGraphic {
  type: 'standings';
  title?: string | null;
  rows: { name: string; score: string }[]; // in the order they are said; the board re-sorts itself
}

export interface PodiumGraphic {
  type: 'podium';
  title?: string | null;
  places: { place: 1 | 2 | 3; name: string; note?: string | null; media?: Media | null }[];
}

export interface RaceGraphic {
  type: 'race';
  title: string;
  unit?: string | null;
  steps: { label: string; values: Record<string, number> }[]; // bar chart race: one step per year/date
}

export interface CardGraphic {
  type: 'card';
  name: string;
  position?: string | null;
  headline: { label: string; value: string }; // the big figure on the corner
  stats: { label: string; value: string }[];
  media?: Media | null;
}

export interface ScaleGraphic {
  type: 'scale';
  title?: string | null;
  axis: 'height' | 'length';
  unit: string;
  items: { name: string; value: number; reference?: boolean }[]; // references: everyday objects for size
}

export interface TierGraphic {
  type: 'tier';
  tiers: string[]; // rows, best first ("S", "A", "B"…)
  items: { name: string; tier: string; media?: Media | null }[]; // everything placed so far
  current: number; // index in items of the one being placed now (flies in)
}

export interface IcebergGraphic {
  type: 'iceberg';
  levels: string[]; // titles, top (known) to bottom (obscure)
  current: number; // the level the camera sinks to
  items: { name: string; level: number }[]; // cases of the levels above, written on their layer
}

export interface ReceiptGraphic {
  type: 'receipt';
  title?: string | null;
  items: { label: string; value: string }[];
  total?: { label: string; value: string } | null;
}

export interface SearchGraphic {
  type: 'search';
  question: string; // typed letter by letter in a search engine box («¿Messi es el mejor jugador de la historia?»)
  engine?: string | null; // the wordmark over the box ('Google' by default)
}

export interface MarkerGraphic {
  type: 'marker';
  text: string; // a short phrase of the script, typed over a blurred newspaper and highlighted in yellow
}

export interface LensGraphic {
  type: 'lens';
  text: string; // a big short line («8 BALONES DE ORO») a magnifying glass sweeps across
}

export interface ScrollGraphic {
  type: 'scroll';
  title: string; // written on an old parchment unrolled on a wooden table («La leyenda del 10»)
  subtitle?: string | null; // place and year under an ornament («Rosario, 1987»)
}

export interface NewsGraphic {
  type: 'news';
  date?: string | null; // red tag («18 DIC 2022»)
  headline: string; // typed, then highlighted in yellow
  body?: string | null; // the line under it
  outlet?: string | null; // newspaper name in blackletter, only if the script names it
  media?: Media | null; // the person, a black and white cutout on the right
}

export interface StickmanActor {
  pose: string; // stand | walk | run | point | think | cheer | sad | sit | talk | shrug | fall | hold | give | wave | facepalm | jump
  face: string; // neutral | happy | sad | angry | surprised | worried
  x: number; // 0-1 across the screen
  facing: 'left' | 'right';
  label: string;
  size: number;
}

/** A shot of a simulation video (pipeline/simulacion.py): the simulated world (remotion/sim/worlds.json), where the
 * camera looks, which panel, the script's parameters, and the channel's language, colour and map theme. */
export interface SimGraphic {
  type: 'sim';
  world: string;
  focus: string;
  prev: string;         // the previous shot's focus (the camera moves from there)
  prevOverlay?: string; // the previous shot's panel, same world (the camera comes back from what it followed)
  overlay: string;
  params?: Record<string, number | string>;
  title: string;
  stat: { label: string; value: string } | null;
  source?: string;      // the study the line cites
  list: string[];
  at: number;           // seconds: when this shot starts in the video
  since: number;        // seconds: when this world came on screen with these parameters (its simulation's clock starts)
  cues?: Record<string, number>;   // video seconds when the voice cues the world's events (brake, jam, fail, start…)
  lang?: string;
  accent?: string;
  theme?: string;
  ambience?: string;    // the background sound: entrada (a few seconds as a world comes in) · siempre · no
  sounds?: Record<string, string>;   // ambient, click, tick, murmur, rain, crowd, kitchen, beep, ding, impact (timeline.py)
  replay?: boolean;     // the key moment: freeze («PAUSA»), rewind, again at half speed
  enter?: boolean;      // this world comes on screen here (zoom in from the last one)
  exit?: boolean;       // the next shot is another world (zoom out)
  legend?: string;      // the colour key, once a video: where it goes (top | bottom | right)
  statAt?: number;      // seconds into the shot: the voice says the figure
  marks?: { kind: string; at: number; text: string }[];   // what the voice points at, when (an arrow with its words)
  rules?: { text: string; off: boolean }[];   // the system's rules on screen, numbered; «off» ones struck out
  rulesFrom?: number;   // the rules before this index were already on screen (do not come in again)
  rulesOff?: number[];  // the rules this line switches off (the strike animates)
  rulesMini?: boolean;  // the rules were already explained: small, in a corner
  recap?: SimGraphic[];  // the closing summary: the key scenes of the video again, one per idea
  dial?: { label: string; from: number; to: number; min: number; max: number; percent?: boolean };   // a number turned
  ask?: string;         // «¿tú qué harías?»: the question the world stops on
  texts?: string[];     // world explica: its words (a label, a year, the steps…)
  nums?: number[];      // world explica: its figures (only ones the voice says)
  askHold?: number;     // seconds at the end of the shot: the world frozen with the question and a countdown
  loopTo?: SimGraphic;  // a Short's last shot: it ends on its first scene (the loop)
}

export interface StickmanProp { icon: string; x: number; y: number; label: string; held: boolean }

export interface StickmanGraphic {
  type: 'stickman';
  place: string; // plain | room | street | office | stage | nature | night | city
  actors: StickmanActor[];
  prop?: StickmanProp | null;
  bubble?: string;
  caption?: string;
  seed?: number;
  palette?: 'color' | 'paper'; // visual.palette: colour (default) or black lines on paper
}

export interface CineActor {
  pose: string; face: string; x: number; facing: 'left' | 'right'; label: string; size: number;
  who: 'hero' | 'other' | 'double' | 'shadow'; // the hero carries his mark; a shadow is the threat (black, glowing eyes)
}

/** A shot of a «cine de monigotes» video (pipeline/cine.py): a set lit like a film, the shot, the camera move, the
 * stickmen, and what goes on top (HUD, rule, title, counter, phone, choice, captions word by word, end card). */
export interface CineGraphic {
  type: 'cine';
  mode: string;          // y-si | disciplina | reglas
  set: string;
  shot: string;          // wide | medium | close | pov-phone | peephole | over | above | silhouette
  light: string;         // warm | cold | dark | red | dawn | day | neon
  move?: string;         // still | push | pull | pan-left | pan-right | shake
  actors?: CineActor[];
  prop?: StickmanProp | null;
  hero?: { mark: string; color: string };
  hud?: { day?: string; clock?: string; place?: string } | null;
  rule?: { n: number; text: string; at?: number; word?: string } | null;
  title?: string;
  titleAt?: number;
  counter?: { label: string; value: string; color?: string } | null;
  phone?: { from: string; messages: string[]; typing?: boolean } | null;
  choice?: { question: string; a: string; b: string; comment: string } | null;
  end?: { series: string; title: string; sub: string; follow: string } | null;
  words?: { t: string; f: number; key?: boolean }[];
  captions?: boolean;
  accent?: string;
  seed?: number;
}

/** A line of a map explainer (pipeline/mapas.py): the camera target (Web Mercator zoom), the previous one (the
 * camera flies between them), the satellite layers near it, and what the marker and the paper props draw — each
 * element with the frame of its word. */
export interface MapaGraphic {
  type: 'mapa';
  lat: number; lon: number; zoom: number;
  prev: { lat: number; lon: number; zoom: number };
  sat?: { z: number; lat: number; lon: number; src: string }[];
  credit?: string;
  circle?: { lat: number; lon: number; word: string; at: number } | null;
  tags?: { name: string; sub: string; lat: number; lon: number; at: number }[];
  line?: { points: [number, number][]; label: string; count: string; dashed: boolean; at: number } | null;
  props: { kind: string; top: string; big: string; sub: string; flip: { top: string; big: string; sub: string } | null; side: 'left' | 'right'; at: number }[];
  strips?: { text: string; lat: number; lon: number; at: number }[];
  stamp?: { text: string; at: number } | null;
  split?: { lon: number; left: string; right: string } | null;
  tracker?: { title: string; date: string; time: string; counter: string } | null;
  path?: { points: [number, number][]; at: number } | null;
  highlight?: { name: string; label: string }[];   // Natural Earth's English name, and the name on screen
  end?: { label: string; wrong: string; right: string } | null;
  seed?: number;
}

/** A line of an atlas deep dive (pipeline/atlas.py): the globe's camera and the previous one (it turns between
 * them), or a chart / line drawing / chapter title instead; every element with the frame of its word. */
export interface AtlasGraphic {
  type: 'atlas';
  view: 'globe' | 'chart' | 'icon' | 'title' | 'sat' | 'flat' | 'size' | 'scene';
  /** view 'scene': una escena de remotion/atlas/schema.ts (esfera, barras, densidad, pistas, agenda, resumen…),
   * con los tiempos en segundos desde el inicio del grupo ({ t }). pipeline/atlas.py la construye. */
  scene?: { type: string; [key: string]: unknown } | null;
  camera: { lat: number; lon: number; zoom: number };
  prev?: { lat: number; lon: number; zoom: number };
  push?: number;                 // zoom the camera gains over the scene (a moment: wide → closer)
  enter?: '' | 'aside';          // after a chart or a drawing: the globe comes back from the side
  lens?: { lat: number; lon: number; zoom: number; label: string; at: number; until?: number } | null;   // a magnifier
  dark?: boolean;
  sat?: { lat: number; lon: number; zoom: number; label: string; at: number; credit?: string; layers?: { src: string; z: number }[] } | null;
  flat?: { from: [number, number]; to: [number, number]; straight: string; curve: string; at: number } | null;
  size?: { country: string; to: [number, number]; compare: string; label: string; at: number } | null;
  counter?: { value: number; unit: string; label: string; at: number; until?: number } | null;
  countries?: { name: string; label: string; at: number; flag?: { src: string } }[];   // silhouette filled with its flag
  points?: { name: string; lat: number; lon: number; at: number; until?: number }[];
  routes?: { from: [number, number]; to: [number, number]; label: string; dashed: boolean; style: 'main' | 'many'; mover?: string; at: number; until?: number; trail?: boolean }[];
  tags?: { text: string; lat: number | null; lon: number | null; at: number }[];   // the line's figure on a paper tag
  rings?: { lat: number; lon: number; km: number; label: string; at: number; until?: number }[];
  zone?: { lat: number; label: string; at: number } | null;
  band?: { country: string; km: number; at: number; until?: number } | null;   // a country's coast, N km inland
  highlight?: { name: string; label: string; group?: number }[];
  night?: { from: [number, number]; to: [number, number]; clock: [string, string]; at: number; lights?: boolean } | null;  // subsolar points
  meridians?: { step: number; labels: boolean; at: number } | null;
  card?: { kind: 'date' | 'quote' | 'list' | 'checks' | 'note' | 'clocks' | 'choice' | 'photo'; big: string; title: string; lines: string[]; source: string;
           side: 'left' | 'right'; at: number; image?: { src: string }; kicker?: string } | null;   // photo: a place's picture (Wikimedia)
  stamp?: { text: string; at: number } | null;
  headline?: { text: string; at: number } | null;
  chart?: { kind: 'bars' | 'profile' | 'thermo'; title: string; unit: string;
            bars?: { label: string; value: number | null; unit: string }[];
            points?: number[]; line?: { value: number | null; label: string } | null; cruise?: number | null;
            value?: number; min?: number; max?: number; label?: string } | null;
  icon?: { name: string; label: string; at: number } | null;
  title?: { number: string; text: string };
  chapters?: string[];
  chapter?: number;
  brand?: string;
  seed?: number;
}

export interface BoardGraphic {
  type: 'board';
  center: string; // the name everything leads to, pinned in the middle
  photo?: Media | null;
  items: { name: string; note?: string | null; photo?: Media | null }[]; // 3-5 pinned around it, red string to the centre
}

export interface PostGraphic {
  type: 'post';
  author: string;
  text: string; // what they published, word for word as the script quotes it
  platform?: 'x' | 'instagram' | 'facebook' | 'tiktok' | null; // only when the script says where
  date?: string | null;
  media?: Media | null; // the author's avatar
}

export interface PosterGraphic {
  type: 'poster';
  words: string[]; // 2-4 words that appear one by one beside the person («TALENTO», «SACRIFICIO»)
  big?: string | null; // one huge word behind their head («GOAT»)
  media?: Media | null; // the person's cutout, in black and white, a red bar over the eyes
}

/** A key date as a page of the calendar: the month big, the year, a row of days and THE day marked (true crime). */
export interface CalendarGraphic {
  type: 'calendar';
  day: number;
  month: number; // 1-12
  year?: number | null;
  monthName: string; // in the video's language («ABRIL»)
  weekdays: string[]; // seven short names, Monday first, in the video's language ([] when the year is not said)
  weekday: number; // 0 = Monday … 6 = Sunday, of the marked day
  label?: string | null; // what happened, ≤ 6 words of the script («la noche del martillo»)
}

export interface PlazoGraphic {
  type: 'plazo';
  title?: string | null;
  limit: number; // seconds
  limitWord?: string;
  marks: { seconds: number; label?: string | null }[];
}

export interface CambioGraphic {
  type: 'cambio';
  name: string;
  before: string;
  after: string;
  fromPlace?: string | null;
  toPlace?: string | null;
  reason?: string | null;
}

/** A ready-made scene of templates/ inserted from the editor (props as templates/types.ts SceneProps). */
export interface SceneGraphic {
  type: 'scene';
  template: string;
  sceneType?: 'hook' | 'narrative' | 'stat' | 'transition' | 'avatar';
  kicker?: string | null; // the small line over the title («Capítulo 1»)
  text?: string | null;
  keywords?: string[] | null;
  timelinePoints?: { label: string; value?: string; position: number }[] | null;
  comparisonColumns?: { title: string; items: string[] }[] | null;
  imageUrl?: string | null;
  videoUrl?: string | null;
  accentColor?: string | null;
}

/** A clip or photo of your own over the edit (uploaded in the editor). */
export interface ClipGraphic {
  type: 'clip';
  src: string; // relative to work/<slug>/
  kind: 'video' | 'image';
  fit?: 'cover' | 'contain';
  place?: 'full' | 'pip';
  volume?: number | null; // its own sound (0 / none: muted)
}

export type Graphic =
  | SceneGraphic
  | ClipGraphic
  | AtlasGraphic
  | PlazoGraphic
  | CalendarGraphic
  | CambioGraphic
  | SearchGraphic
  | MarkerGraphic
  | LensGraphic
  | ScrollGraphic
  | NewsGraphic
  | PosterGraphic
  | TierGraphic
  | IcebergGraphic
  | ReceiptGraphic
  | PodiumGraphic
  | RaceGraphic
  | CardGraphic
  | ScaleGraphic
  | StrobeGraphic
  | ReplayGraphic
  | StandingsGraphic
  | ScoreGraphic
  | PressGraphic
  | ArticleGraphic
  | SatelliteGraphic
  | QuoteGraphic
  | RuleGraphic
  | CitaGraphic
  | SplitGraphic
  | BannedGraphic
  | SpotlightGraphic
  | MapGraphic
  | RankGraphic
  | CompareGraphic
  | BoardGraphic
  | StickmanGraphic
  | CineGraphic
  | MapaGraphic
  | SimGraphic
  | PostGraphic
  | ChartGraphic
  | TimelineGraphic
  | SpecsGraphic
  | KineticGraphic;
