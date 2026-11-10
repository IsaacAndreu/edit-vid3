// The words the simulation panels write, in each channel's language (align.language: es, pt, fr, de, en). The
// language is set once per render (SimScene, from graphic.lang): every shot of a video shares it.
type Lang = 'es' | 'pt' | 'fr' | 'de' | 'en';
let LANG: Lang = 'es';

export const setLang = (code: string | undefined) => {
  const c = String(code || 'es').slice(0, 2).toLowerCase();
  LANG = (['es', 'pt', 'fr', 'de', 'en'].includes(c) ? c : 'es') as Lang;
};

const D: Record<string, Record<Lang, string>> = {
  // shared
  recap: {es: 'Lo que hemos visto', pt: 'O que vimos', fr: 'Ce que nous avons vu', de: 'Was wir gesehen haben', en: 'What we saw'},
  source: {es: 'Fuente', pt: 'Fonte', fr: 'Source', de: 'Quelle', en: 'Source'},
  simulation: {es: 'Simulación', pt: 'Simulação', fr: 'Simulation', de: 'Simulation', en: 'Simulation'},
  time: {es: 'Tiempo', pt: 'Tempo', fr: 'Temps', de: 'Zeit', en: 'Time'},
  day: {es: 'Día', pt: 'Dia', fr: 'Jour', de: 'Tag', en: 'Day'},
  // junctions
  lights: {es: 'Semáforos', pt: 'Semáforos', fr: 'Feux', de: 'Ampeln', en: 'Traffic lights'},
  roundabout: {es: 'Rotonda', pt: 'Rotunda', fr: 'Rond-point', de: 'Kreisverkehr', en: 'Roundabout'},
  sameTraffic: {es: 'El mismo tráfico a los dos', pt: 'O mesmo tráfego nos dois', fr: 'Le même trafic des deux côtés', de: 'Derselbe Verkehr für beide', en: 'The same traffic for both'},
  carsPerMinute: {es: 'coches por minuto', pt: 'carros por minuto', fr: 'voitures par minute', de: 'Autos pro Minute', en: 'cars per minute'},
  perStreet: {es: 'en cada calle', pt: 'em cada rua', fr: 'dans chaque rue', de: 'pro Straße', en: 'on each street'},
  waitingNow: {es: 'Esperando ahora', pt: 'Esperando agora', fr: 'En attente', de: 'Wartend', en: 'Waiting now'},
  greenFor: {es: 'Verde para', pt: 'Verde para', fr: 'Vert pour', de: 'Grün für', en: 'Green for'},
  eastWest: {es: 'Este-oeste', pt: 'Leste-oeste', fr: 'Est-ouest', de: 'Ost-West', en: 'East-west'},
  northSouth: {es: 'Norte-sur', pt: 'Norte-sul', fr: 'Nord-sud', de: 'Nord-Süd', en: 'North-south'},
  onlyRule: {es: 'La única regla', pt: 'A única regra', fr: 'La seule règle', de: 'Die einzige Regel', en: 'The only rule'},
  giveWay: {es: 'Cede al que ya está dentro', pt: 'Ceda a quem já está dentro', fr: 'Cède à qui est déjà dedans', de: 'Vorfahrt für den, der schon drin ist', en: 'Give way to who is already in'},
  averageWait: {es: 'Espera media por coche', pt: 'Espera média por carro', fr: 'Attente moyenne par voiture', de: 'Mittlere Wartezeit pro Auto', en: 'Average wait per car'},
  passed: {es: 'Han pasado', pt: 'Passaram', fr: 'Sont passées', de: 'Durchgefahren', en: 'Got through'},
  conflictPoints: {es: 'Puntos de choque', pt: 'Pontos de colisão', fr: 'Points de conflit', de: 'Konfliktpunkte', en: 'Conflict points'},
  crossing: {es: 'Cruce', pt: 'Cruzamento', fr: 'Croisement', de: 'Kreuzen', en: 'Crossing'},
  merging: {es: 'Incorporación', pt: 'Entrada', fr: 'Insertion', de: 'Einfädeln', en: 'Merging'},
  diverging: {es: 'Salida', pt: 'Saída', fr: 'Sortie', de: 'Ausfahren', en: 'Diverging'},
  junctionNote: {es: 'Simulación · mismas llegadas en los dos cruces · {n} m de acceso por calle', pt: 'Simulação · mesmas chegadas nos dois cruzamentos · {n} m de acesso por rua', fr: 'Simulation · mêmes arrivées aux deux carrefours · {n} m d’accès par rue', de: 'Simulation · gleiche Ankünfte an beiden Kreuzungen · {n} m Zufahrt je Straße', en: 'Simulation · the same arrivals at both junctions · {n} m approach per street'},
  // ring
  meanSpeed: {es: 'Velocidad media', pt: 'Velocidade média', fr: 'Vitesse moyenne', de: 'Durchschnittstempo', en: 'Average speed'},
  stoppedNow: {es: 'Parados ahora', pt: 'Parados agora', fr: 'À l’arrêt', de: 'Stehen gerade', en: 'Stopped now'},
  ofCars: {es: 'de {n} coches', pt: 'de {n} carros', fr: 'sur {n} voitures', de: 'von {n} Autos', en: 'of {n} cars'},
  ringChart: {es: 'Posición de cada coche en el anillo, segundo a segundo', pt: 'Posição de cada carro no anel, segundo a segundo', fr: 'Position de chaque voiture sur l’anneau, seconde par seconde', de: 'Position jedes Autos auf dem Ring, Sekunde für Sekunde', en: 'Each car’s position on the ring, second by second'},
  stopped: {es: 'parado', pt: 'parado', fr: 'à l’arrêt', de: 'steht', en: 'stopped'},
  normalSpeed: {es: 'a velocidad normal', pt: 'velocidade normal', fr: 'vitesse normale', de: 'normales Tempo', en: 'normal speed'},
  ringNote: {es: 'Simulación con el modelo de conductor inteligente (IDM) · {n} coches en un círculo de 230 m', pt: 'Simulação com o modelo do condutor inteligente (IDM) · {n} carros num círculo de 230 m', fr: 'Simulation avec le modèle du conducteur intelligent (IDM) · {n} voitures sur un cercle de 230 m', de: 'Simulation mit dem Intelligent Driver Model (IDM) · {n} Autos auf einem 230-m-Kreis', en: 'Simulation with the Intelligent Driver Model (IDM) · {n} cars on a 230 m circle'},
};

/** A panel's words in the video's language; {n}, {x}… are filled from `vars`. Unknown keys come back as they are. */
export const tx = (key: string, vars: Record<string, string | number> = {}): string => {
  const entry = D[key];
  let text = entry ? entry[LANG] ?? entry.es : key;
  for (const [k, v] of Object.entries(vars)) text = text.replace(`{${k}}`, String(v));
  return text;
};

/** More words for a world (each world file adds its own). */
export const addWords = (words: Record<string, Record<Lang, string>>) => Object.assign(D, words);
export type Words = Record<string, Record<Lang, string>>;

const LOCALES: Record<Lang, string> = {es: 'es-ES', pt: 'pt-BR', fr: 'fr-FR', de: 'de-DE', en: 'en-US'};
/** A number as it is written in the channel's language: 3,5 in Spanish, German, Portuguese and French; 3.5 in English;
 * thousands 1.390 (de, pt), 1 390 (fr), 1,390 (en), 1390 (es: four figures are not grouped). */
export const num = (value: number, digits = 0): string =>
  new Intl.NumberFormat(LOCALES[LANG], {minimumFractionDigits: digits, maximumFractionDigits: digits}).format(value);
