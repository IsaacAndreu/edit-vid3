// Deterministic data for the Estudio mock (see mock.js). Everything is derived from one seeded PRNG; the only
// thing that moves between runs is «today» (dates are relative to it).
"use strict";

const ORDER = ["factcheck", "align", "planner", "sourcing", "analysis", "judge", "ingest", "people", "fallback", "coldopen",
  "timeline", "qa", "render", "shorts", "package"];

function mulberry32(seed) {
  let a = seed >>> 0;
  return () => { a |= 0; a = (a + 0x6d2b79f5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}
function hashOf(text) { let h = 2166136261; for (const c of String(text)) { h ^= c.charCodeAt(0); h = Math.imul(h, 16777619); } return h >>> 0; }
function rng(seed) {
  const r = mulberry32(typeof seed === "number" ? seed : hashOf(seed));
  const api = {
    next: r,
    int: (a, b) => a + Math.floor(r() * (b - a + 1)),
    float: (a, b, d = 2) => +(a + r() * (b - a)).toFixed(d),
    pick: (list) => list[Math.floor(r() * list.length)],
    chance: (p) => r() < p,
    shuffle: (list) => { const out = [...list]; for (let i = out.length - 1; i > 0; i--) { const j = Math.floor(r() * (i + 1)); [out[i], out[j]] = [out[j], out[i]]; } return out; },
    id: (n = 11) => { const abc = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-"; let s = ""; for (let i = 0; i < n; i++) s += abc[Math.floor(r() * abc.length)]; return s; },
  };
  return api;
}

const DAY_MS = 86400000;
const NOW = Date.now();
const isoDay = (ms) => new Date(ms).toISOString().slice(0, 10);
const TODAY = isoDay(NOW);
const day = (n) => isoDay(NOW + n * DAY_MS);
const isoAt = (ms) => new Date(ms).toISOString().slice(0, 19);
const hhmm = (ms) => new Date(ms).toISOString().slice(11, 16);
const slugify = (t) => String(t).toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
const thumb = (id) => `https://i.ytimg.com/vi/${id}/mqdefault.jpg`;
const avatar = (id) => `https://yt3.ggpht.com/${id}=s88-c-k-c0x00ffffff-no-rj`;
const watch = (id) => `https://www.youtube.com/watch?v=${id}`;
const IDLE = () => ({running: false, failed: false, log: ""});

// --- channels -------------------------------------------------------------------------------------------------------
const SUBJECTS = {
  "gimnasia": ["Nadia Comaneci", "Simone Biles", "Olga Korbut", "Yelena Mújina", "Kohei Uchimura", "Vera Čáslavská"],
  "aviones": ["el Concorde", "el Airbus A380", "el Boeing 737 MAX", "el Tupolev Tu-144", "el Spruce Goose", "el Antonov An-225"],
  "historia-rara": ["la Gran Guerra del Emú", "la valla de los dingos de Australia", "la inundación de melaza de Boston", "el ejército fantasma de 1944", "el hombre que vendió la Torre Eiffel", "la epidemia de risa de Tanganica"],
  "coches": ["el SEAT 600", "el Tucker 48", "el Trabant", "el Renault 5 Turbo", "el Hispano-Suiza", "el Ford Edsel"],
  "atletismo": ["Usain Bolt", "Jarmila Kratochvílová", "Bob Beamon", "Abebe Bikila", "Florence Griffith", "Emil Zátopek"],
  "natacion": ["Michael Phelps", "Mark Spitz", "Ian Thorpe", "Eric «la Anguila» Moussambani", "Katie Ledecky", "Mireia Belmonte"],
  "ciclismo": ["Marco Pantani", "Miguel Induráin", "Lance Armstrong", "Eddy Merckx", "Luis Ocaña", "Fausto Coppi"],
  "trenes": ["el Talgo", "el Transiberiano", "el AVE a La Meca", "el Maglev de Shanghái", "el Orient Express", "el tren de Sóller"],
  "barcos": ["el Titanic", "el Vasa", "el Ever Given", "el Costa Concordia", "el Bismarck", "el Prestige"],
  "espacio": ["el Apolo 13", "la estación Mir", "el Challenger", "la sonda Voyager 1", "el transbordador Burán", "el telescopio Hubble"],
  "imperios": ["el Imperio romano", "el Imperio mongol", "Bizancio", "el Imperio otomano", "el Imperio español", "Cartago"],
  "crimenes": ["el robo del siglo de Buenos Aires", "D. B. Cooper", "el asalto al tren de Glasgow", "el Dioni", "el robo de la Mona Lisa", "el atraco al Banco Central de 1981"],
  "estafas": ["Bernie Madoff", "Theranos", "Fórum Filatélico", "el Fyre Festival", "Enron", "la Nueva Rumasa"],
  "ingenieria": ["la presa de Vajont", "el puente de Tacoma", "el canal de Panamá", "el Eurotúnel", "la torre de Pisa", "el puente de Génova"],
  "submarinos": ["el Kursk", "el ARA San Juan", "el USS Thresher", "el Titán de OceanGate", "el K-19", "el submarino de Isaac Peral"],
  "alpinismo": ["el desastre del Everest de 1996", "Reinhold Messner", "el K2", "Edurne Pasaban", "la cara norte del Eiger", "Juanito Oiarzabal"],
  "ajedrez": ["Bobby Fischer", "Garri Kaspárov", "Deep Blue", "Magnus Carlsen", "Judit Polgár", "José Raúl Capablanca"],
  "formula1": ["Ayrton Senna", "Niki Lauda", "Fernando Alonso", "Brawn GP", "el Gran Premio de Indianápolis de 2005", "Gilles Villeneuve"],
  "boxeo": ["Muhammad Ali", "Mike Tyson", "Julio César Chávez", "Roberto «Mano de Piedra» Durán", "Urtain", "Manny Pacquiao"],
  "tenis": ["Rafa Nadal", "Björn Borg", "Monica Seles", "Arantxa Sánchez Vicario", "Marat Safin", "Juan Martín del Potro"],
  "medicina": ["la talidomida", "la gripe de 1918", "la lobotomía", "el aceite de colza", "la penicilina", "el primer trasplante de corazón"],
  "dinosaurios": ["el Tiranosaurio rex", "el Spinosaurus", "el meteorito de Chicxulub", "el Megalodón", "el Argentinosaurus", "las huellas de La Rioja"],
  "volcanes": ["el Krakatoa", "el volcán de La Palma", "Pompeya", "el Tambora", "el monte Santa Helena", "el Nevado del Ruiz"],
  "simulacion-trafico": ["los atascos fantasma", "la rotonda turbo", "el semáforo inteligente", "la autopista de 26 carriles", "el efecto acordeón", "el carril bus-VAO"],
  "simulacion-ciudades": ["una ciudad sin coches", "la supermanzana de Barcelona", "Brasilia", "la ciudad de 15 minutos", "un metro sin conductor", "Benidorm"],
  "mapas-guerras": ["la Reconquista", "las guerras púnicas", "la guerra de los Cien Años", "la caída de Constantinopla", "la batalla del Ebro", "el desembarco de Normandía"],
  "monigotes-dinero": ["el interés compuesto", "la inflación", "una hipoteca a tipo variable", "el euríbor", "un plan de pensiones", "la burbuja de los tulipanes"],
};
const DUBBED = {"gimnasia-br": ["gimnasia", "pt"], "aviones-br": ["aviones", "pt"], "historia-rara-en": ["historia-rara", "en"]};
const BASE_CHANNELS = Object.keys(SUBJECTS);
const CHANNELS = [...BASE_CHANNELS, ...Object.keys(DUBBED)].sort();            // 30, as channels(root) lists them
const KINDS = Object.fromEntries(CHANNELS.map((c) => [c, c.startsWith("simulacion") ? "simulacion" : c.startsWith("mapas") ? "mapas" : c.startsWith("monigotes") ? "stickman" : "metraje"]));
const FORMATS = ["historia", "caso-real", "caida-y-regreso", "ranking", "explicacion", "simulacion", "mapas", "short-dato"];
const PARTNERS = {marc: ["ajedrez", "coches", "simulacion-trafico", "trenes", "volcanes"], laia: ["boxeo", "tenis"]};

const TEMPLATES = [
  "La caída de {x}: el error que nadie quiso ver",
  "Por qué {x} desapareció de un día para otro",
  "{X}: la historia que nunca te contaron",
  "El día que {x} lo cambió todo (y casi nadie lo recuerda)",
  "Cómo {x} pasó de la gloria al olvido en solo tres años",
  "El secreto mejor guardado de {x}",
  "{X}, explicado en 12 minutos",
  "Lo que de verdad pasó con {x}",
  "La increíble y trágica historia de {x}, el proyecto de 4.000 millones que acabó abandonado y que hoy casi nadie quiere recordar",
  "{X}: 7 decisiones que lo hundieron (la quinta es la que nadie menciona en los documentales)",
];
const SHORT_TEMPLATES = ["{X} en 40 segundos", "El dato de {x} que no sabías", "¿Sabías esto de {x}?", "{X}: el momento exacto"];
const fill = (t, x) => { const out = t.replace("{x}", x).replace("{X}", x[0].toUpperCase() + x.slice(1)); return out.replace(/ de el /g, " del ").replace(/ a el /g, " al "); };

const ERRORS = [
  "Stopped: Parado por la señal SIGTERM (reinicio del servicio) en la etapa sourcing",
  "YouTubeBlocked: YouTube dice «confirma que no eres un bot» en 14 de 16 descargas (rainproxy-resi-es)",
  "RuntimeError: 41 de 58 planos sin ninguna imagen: el juez rechazó casi todo lo encontrado",
  "ProxyDown: el proxy casa-pc:8899 no responde (Tunnel connection failed: 502 Bad Gateway)",
  "ApiSearchesShort: se acabaron las búsquedas hoy (cuota de la API de YouTube agotada en las 6 claves)",
  "OpenRouter: sin saldo (402 insufficient credits) al pedir el veredicto del juez",
  "Traceback (most recent call last):\n  File \"/srv/edit-vid3/main.py\", line 412, in run_stage\n    stage.run(ctx)\n  File \"/srv/edit-vid3/pipeline/judge.py\", line 212, in pick\n    frames = candidate[\"frames\"]\nKeyError: 'frames'",
  "GenAIPro: la voz no se pudo generar (tts 429: créditos agotados este mes)",
  "ffmpeg salió con código 1 al montar el plano s034 (moov atom not found)",
];

// --- videos ---------------------------------------------------------------------------------------------------------
const SPECIAL = {haciendo: "delorean", reintento: "pegaso-z102", error: "saab-quiebra", hecho: "citroen-ds", publicado: "lancia-stratos"};
const SLUGS = {...SPECIAL, review: "citroen-ds", decisions: "citroen-ds", library: "niki-lauda", search: "dingos", partner: "marc"};

function buildVideos() {
  const r = rng(20261111);
  const videos = [], usedSlug = new Set(), usedCombo = new Set();
  const weights = BASE_CHANNELS.map((c) => (PARTNERS.marc.includes(c) ? 16 : ["gimnasia", "aviones", "historia-rara"].includes(c) ? 18 : r.int(5, 13)));
  const total = weights.reduce((a, b) => a + b, 0);
  const pickChannel = () => { let x = r.next() * total; for (let i = 0; i < weights.length; i++) { x -= weights[i]; if (x <= 0) return BASE_CHANNELS[i]; } return BASE_CHANNELS[0]; };
  const titleFor = (channel, short) => {
    for (let n = 0; n < 200; n++) {
      const subject = r.pick(SUBJECTS[channel]), templates = short ? SHORT_TEMPLATES : TEMPLATES;
      const i = r.int(0, templates.length - 1 - (short ? 0 : r.chance(0.8) ? 2 : 0));
      const key = `${channel}|${subject}|${short}|${i}`;
      if (usedCombo.has(key)) continue;
      usedCombo.add(key);
      return [subject, fill(templates[i], subject)];
    }
    const subject = r.pick(SUBJECTS[channel]);
    return [subject, fill("{X}: parte " + r.int(2, 9), subject)];
  };
  const slugFor = (subject, short) => {
    const words = slugify(subject).split("-").filter((w) => !["el", "la", "los", "las", "de", "del", "un", "una", "que", "a"].includes(w));
    const base = words.slice(0, 2).join("-").slice(0, 22) + (short ? "-short" : "");
    let slug = base, n = 1;
    while (usedSlug.has(slug)) slug = `${base}-${++n}`;
    usedSlug.add(slug);
    return slug;
  };
  const make = (state, fixed = {}) => {
    const channel = fixed.channel || pickChannel();
    const short = fixed.short ?? r.chance(0.25);
    const [subject, title] = fixed.title ? [fixed.subject, fixed.title] : titleFor(channel, short);
    const slug = fixed.slug || slugFor(subject, short);
    usedSlug.add(slug);
    const v = {slug, channel, status: state.status, quotaWait: null, short, archived: false, stage: null, stagesDone: 0, costUsd: 0,
      error: null, lastError: null, voice: null, retryAt: null, updated: 0, hasVideo: false, published: null, removed: null,
      title: fixed.noTitle ? "" : title, minutes: 0};
    const ageDays = (a, b) => (NOW - r.float(a, b, 3) * DAY_MS) / 1000;
    if (state.status === "haciendo") {
      const n = fixed.stageNumber || r.int(3, 13);
      v.stage = {stage: ORDER[n - 1], number: n, of: 15, started: isoAt(NOW - r.int(2, 34) * 60000) + "Z", pid: 40000 + r.int(1, 9999)};
      v.stagesDone = n - 1; v.updated = (NOW - r.int(20, 200) * 1000) / 1000;
    } else if (state.status === "en cola") {
      v.updated = ageDays(0.04, 6);
      if (state.kind === "retry") { v.lastError = r.pick(ERRORS.filter((e) => !/cuota|SIGTERM/.test(e))); v.retryAt = hhmm(NOW + r.int(10, 170) * 60000); v.stagesDone = r.int(2, 9); }
      else if (state.kind === "retry-turn") { v.lastError = ERRORS[0]; v.stagesDone = r.int(3, 11); }
      else if (state.kind === "quota-yt") { v.quotaWait = "espera a YouTube: 9 planos sin vídeo de YouTube; faltan 2 personas del guion"; v.stagesDone = 8; }
      else if (state.kind === "quota-api") { v.quotaWait = "cuota de la API de YouTube · hasta las 09:00"; v.stagesDone = 3; }
      else if (state.kind === "started") v.stagesDone = r.int(3, 12);
      else if (state.kind === "voice") v.voice = "generando";
    } else if (state.status === "error") {
      v.error = state.error; v.stagesDone = r.int(1, 11); v.updated = ageDays(0.1, 4);
    } else if (state.status === "incompleto") {
      v.updated = ageDays(0.5, 12);
      if (state.kind === "voice-error") v.voice = "error: GenAIPro respondió 429 (créditos agotados)";
    } else if (state.status === "en pausa") {
      v.stagesDone = r.int(0, 10); v.updated = ageDays(2, 20);
    } else {                                                     // hecho
      v.stagesDone = 15; v.hasVideo = true;
      if (state.kind === "published") {
        const at = NOW - (fixed.agePublished ?? r.float(1, 170, 3)) * DAY_MS;
        v.published = {at: isoAt(at)};
        if (fixed.url !== false && !state.noUrl) v.published.url = watch(r.id());
        v.updated = (at + r.int(1, 30) * 60000) / 1000;
        if (NOW - at > 8 * DAY_MS && !fixed.keepVideo) { v.hasVideo = false; v.removed = {at: isoAt(at + 7 * DAY_MS), gb: r.float(0.8, 2.4, 1)}; }
      } else v.updated = ageDays(0.3, 21);
    }
    if (v.stagesDone) { v.minutes = Math.round(v.stagesDone * r.float(3, 9, 1) * (short ? 0.4 : 1)); v.costUsd = +(v.stagesDone / 15 * r.float(0.45, 1.6) * (short ? 0.3 : 1)).toFixed(2); }
    if (state.archived) v.archived = true;
    videos.push(v);
    return v;
  };

  // one of each state with a fixed name, all in «coches» (one of the partner's channels: the same routes work for both)
  make({status: "haciendo"}, {channel: "coches", slug: SPECIAL.haciendo, subject: "el DeLorean DMC-12", short: false, stageNumber: 6,
    title: "La caída del DeLorean DMC-12: el coche del futuro que arruinó a su creador"});
  make({status: "en cola", kind: "retry"}, {channel: "coches", slug: SPECIAL.reintento, subject: "el Pegaso Z-102", short: false,
    title: "Pegaso Z-102: el superdeportivo español que humilló a Ferrari y desapareció"}).lastError = ERRORS[1];
  make({status: "error", error: ERRORS[6]}, {channel: "coches", slug: SPECIAL.error, subject: "Saab", short: false,
    title: "Por qué Saab quebró: del avión al coche, y del coche a la nada"});
  make({status: "hecho"}, {channel: "coches", slug: SPECIAL.hecho, subject: "el Citroën DS", short: false,
    title: "El Citroën DS: el coche que llegó del futuro en 1955 y salvó la vida de un presidente"});
  make({status: "hecho", kind: "published"}, {channel: "coches", slug: SPECIAL.publicado, subject: "el Lancia Stratos", short: false, agePublished: 12.4, keepVideo: true,
    title: "Lancia Stratos: la bestia que nadie sabía conducir y que ganó tres mundiales"});
  for (const v of videos) { if (v.slug === SPECIAL.reintento) { v.stagesDone = 6; v.minutes = 31; v.costUsd = 0.52; } if (v.slug === SPECIAL.error) { v.stagesDone = 5; v.minutes = 24; v.costUsd = 0.41; } }

  make({status: "haciendo"}); make({status: "haciendo"}, {short: true});
  const queued = [...Array(7).fill("retry"), ...Array(2).fill("retry-turn"), ...Array(3).fill("quota-yt"), ...Array(3).fill("quota-api"),
    ...Array(10).fill("started"), ...Array(3).fill("voice"), ...Array(11).fill("")];
  queued.forEach((kind, i) => make({status: "en cola", kind}, i < 6 ? {channel: PARTNERS.marc[i % 5]} : {}));
  ERRORS.forEach((error, i) => make({status: "error", error}, i % 3 === 0 ? {channel: PARTNERS.marc[i % 5]} : {}));
  make({status: "error", error: ERRORS[1]}); make({status: "error", error: ERRORS[2]});
  ["", "", "", "voice-error", ""].forEach((kind, i) => make({status: "incompleto", kind}, i === 0 ? {channel: "trenes", noTitle: true} : {}));
  for (let i = 0; i < 4; i++) make({status: "en pausa"}, i === 0 ? {channel: "volcanes"} : {});
  for (let i = 0; i < 59; i++) make({status: "hecho"});
  for (let i = 0; i < 159; i++) make({status: "hecho", kind: "published", noUrl: i % 40 === 7});
  for (let i = 0; i < 16; i++) make(i % 2 ? {status: "hecho", kind: "published", archived: true} : {status: "hecho", archived: true});
  // the dubbed copies (their own channel, the original's name + language): finished and uploaded like the rest
  for (const [channel, [base, lang]] of Object.entries(DUBBED)) {
    const originals = videos.filter((v) => v.channel === base && v.status === "hecho" && !v.archived && !v.short).slice(0, 5);
    originals.forEach((o, i) => {
      const v = {...o, slug: `${o.slug}-${lang}`, channel, dubOf: o.slug,
        title: lang === "pt" ? o.title.replace(/^La caída de/, "A queda de").replace(/^Por qué/, "Por que").replace(/^El /, "O ") : "The untold story: " + o.title.split(":")[0]};
      v.published = i < 3 ? {at: isoAt(NOW - (4 + 9 * i) * DAY_MS), url: watch(r.id())} : null;
      v.hasVideo = true; v.removed = null; v.costUsd = +(o.costUsd * 0.2).toFixed(2); v.updated = o.updated + 3600 * (i + 1);
      // these 15 replace 15 of the plain uploaded ones so the total stays ~300
      const drop = videos.findIndex((x) => x.published && !x.archived && !Object.values(SPECIAL).includes(x.slug) && !PARTNERS.marc.includes(x.channel) && !x.keep && x.channel !== base);
      if (drop >= 0) videos.splice(drop, 1);
      v.keep = true; videos.push(v);
    });
  }
  videos.forEach((v) => delete v.keep);
  videos.sort((a, b) => b.updated - a.updated);
  return videos;
}

// --- the calendar: a port of pipeline/agenda.py (videos, plan, reserve, board) ---------------------------------------
const WEEKDAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"];
const READINESS = {"hecho": 0, "haciendo": 1, "en cola": 2, "error": 2, "falta voz": 3, "falta guion": 3};

function buildSchedule() {
  const r = rng(77), schedule = {};
  const patterns = [[0, 2, 4], [0, 2, 4], [0, 2, 4], [1, 3, 5], [0, 1, 2, 3, 4], [2, 5], [0, 3, 6]];
  for (const c of CHANNELS) schedule[c] = {days: r.pick(patterns), time: r.pick(["18:00", "18:00", "17:30", "19:00", "20:15", "12:00"]), enabled: !(c in DUBBED)};
  schedule["coches"] = {days: [0, 2, 4], time: "18:00", enabled: true};
  return schedule;
}

function agendaVideos(st) {
  return st.videos.filter((v) => !v.archived && !v.dubOf).map((v) => ({
    slug: v.slug, channel: v.channel,
    status: v.published ? "subido" : v.status === "hecho" ? "hecho" : v.status === "en pausa" ? "en pausa" : v.status === "haciendo" ? "haciendo"
      : v.status === "incompleto" ? (hashOf(v.slug) % 2 ? "falta voz" : "falta guion") : v.status === "error" ? "error" : "en cola",
    title: v.title || "", published: v.published && /^\d{4}-\d{2}-\d{2}/.test(v.published.at || "") ? v.published.at.slice(0, 10) : null,
    url: (v.published || {}).url || "", doneAt: v.hasVideo ? +v.updated.toFixed(3) : null, created: +(v.updated - 86400 * 2).toFixed(3),
  }));
}

function plan(st, days, listed) {
  const cfg = st.agenda, now = Date.now();
  const start = Date.parse(TODAY + "T00:00:00Z");
  const at = (iso, clock) => Date.parse(`${iso}T${clock.padStart(5, "0")}:00Z`);
  const byChannel = {};
  for (const v of listed) (byChannel[v.channel] = byChannel[v.channel] || []).push(v);
  let slots = [];
  for (const [channel, rule] of Object.entries(cfg.schedule)) {
    if (!rule.enabled) continue;
    const mine = byChannel[channel] || [];
    const pinned = {};
    for (const v of mine) if (cfg.assigned[v.slug]) pinned[v.slug] = cfg.assigned[v.slug];
    const inRange = (iso) => { const t = Date.parse(iso + "T00:00:00Z"); return t >= start && t < start + days * DAY_MS; };
    const wanted = new Set();
    for (let n = 0; n < days; n++) { const d = new Date(start + n * DAY_MS); if (rule.days.includes((d.getUTCDay() + 6) % 7)) wanted.add(isoDay(d.getTime())); }
    Object.values(pinned).filter(inRange).forEach((d) => wanted.add(d));
    mine.filter((v) => v.published && inRange(v.published)).forEach((v) => wanted.add(v.published));
    const mineSlots = [...wanted].sort().map((d) => ({date: d, time: rule.time, channel, video: null}));
    const used = new Set();
    for (const s of mineSlots) { const v = mine.find((x) => x.published === s.date && !used.has(x.slug)); if (v) { s.video = v; used.add(v.slug); } }
    for (const s of mineSlots) if (!s.video) { const v = mine.find((x) => pinned[x.slug] === s.date && !used.has(x.slug) && x.status !== "subido"); if (v) { s.video = v; s.pinned = true; used.add(v.slug); } }
    const ready = mine.filter((v) => !used.has(v.slug) && v.status in READINESS && !(v.slug in pinned))
      .sort((a, b) => READINESS[a.status] - READINESS[b.status] || (a.doneAt || a.created) - (b.doneAt || b.created));
    for (const s of mineSlots) if (!s.video && at(s.date, s.time) >= now - 12 * 3600000 && ready.length) s.video = ready.shift();
    for (const s of mineSlots) {
      const when = at(s.date, s.time), v = s.video;
      s.deadline = new Date(when - cfg.lead_hours * 3600000).toISOString().slice(0, 16);
      s.past = when < now;
      s.ok = !!(v && ["hecho", "subido"].includes(v.status));
      const needs = !v || ["falta guion", "falta voz"].includes(v.status);
      s.gap = !s.ok && !s.past && (!v || !["haciendo", "en cola"].includes(v.status));
      s.late = !s.ok && !s.past && needs && now > when - cfg.lead_hours * 3600000;
    }
    slots = slots.concat(mineSlots);
  }
  return slots.sort((a, b) => (a.date + a.time + a.channel < b.date + b.time + b.channel ? -1 : 1));
}

function reserve(st, listed) {
  return Object.fromEntries(Object.entries(st.agenda.schedule).filter(([, r]) => r.enabled)
    .map(([c]) => [c, listed.filter((v) => v.channel === c && v.status === "hecho").length]));
}

function uploadDates(st) {
  const listed = agendaVideos(st), out = {};
  for (const s of plan(st, 60, listed)) if (s.video) out[s.video.slug] = {date: s.date, time: s.time};
  // a few that should already be out (the calendar of last week) and a few for today
  const waiting = listed.filter((v) => v.status === "hecho").sort((a, b) => (a.slug < b.slug ? -1 : 1));
  waiting.slice(0, 4).forEach((v, i) => { out[v.slug] = {date: day(-1 - (i % 3)), time: "18:00"}; });
  waiting.slice(4, 7).forEach((v, i) => { out[v.slug] = {date: TODAY, time: ["12:00", "18:00", "20:15"][i]}; });
  if (out[SPECIAL.hecho]) out[SPECIAL.hecho] = {date: TODAY, time: "18:00"};
  return out;
}

function board(st) {
  const columns = {"idea": [], "falta voz": [], "en cola": [], "hecho": [], "subido": []};
  const listed = agendaVideos(st), days = {};
  for (const s of plan(st, 60, listed)) if (s.video) days[s.video.slug] = s.date;
  for (const idea of [...st.agenda.ideas, ...st.savedIdeas])
    columns.idea.push({kind: "idea", id: idea.id, title: idea.title, channel: idea.channel || "", note: idea.note || idea.angle || "", date: idea.date || "", idea});
  for (const v of listed) {
    const column = v.status === "subido" ? "subido" : v.status === "hecho" ? "hecho" : ["falta voz", "falta guion"].includes(v.status) ? "falta voz" : "en cola";
    columns[column].push({...v, kind: "video", date: days[v.slug] || ""});
  }
  columns.subido = columns.subido.sort((a, b) => (b.published || "").localeCompare(a.published || "")).slice(0, 12);
  return columns;
}

// --- texts ----------------------------------------------------------------------------------------------------------
function scriptText(v) {
  const x = v.title.split(":")[0];
  return `## Capítulo 1 · El principio\n${x} no empezó como un fracaso. En 1974 era la promesa de toda una industria: tres mil pedidos antes de enseñar un solo prototipo, una fábrica nueva pagada con dinero público y un fundador que salía en todas las portadas.\n\n` +
    `## Capítulo 2 · La primera grieta\nEl primer aviso llegó en una carta de dos páginas que nadie contestó. Un ingeniero de 29 años advertía de que las cifras no cuadraban: cada unidad costaba 1.400 dólares más de lo que se cobraba por ella.\n\n` +
    `## Capítulo 3 · El día que todo se torció\nEl 19 de octubre, a las 6:40 de la mañana, sonó el teléfono. Lo que pasó en las siguientes 72 horas todavía se estudia en las escuelas de negocio.\n\n` +
    `## Capítulo 4 · Lo que quedó\nHoy quedan 6.500 unidades, un museo en una nave industrial y una pregunta: ¿se pudo evitar? La respuesta corta es que sí. La larga es este vídeo.\n`;
}

function logText(v, r) {
  const lines = [`===== ${v.slug} · canal ${v.channel} · ${isoAt(NOW - 3 * 3600000).replace("T", " ")} =====`];
  const upto = v.stage ? v.stage.number : Math.min(15, v.stagesDone + (v.error || v.lastError ? 1 : 0));
  for (let n = 1; n <= upto; n++) {
    const name = ORDER[n - 1];
    lines.push(`[${n}/15] ${name}: empieza`);
    const body = 8 + r.int(0, 14);
    for (let i = 0; i < body; i++) {
      const shot = "s" + String(r.int(1, 58)).padStart(3, "0");
      lines.push(r.pick([
        `  ${shot}: 4 candidatos · mejor nota 0.${r.int(61, 93)} (${r.pick(["youtube", "foto", "stock", "biblioteca"])})`,
        `  ${shot}: descargado tramo ${r.int(10, 400)}-${r.int(401, 800)} s · ${r.float(1.2, 38.5, 1)} MB en ${r.float(0.8, 9.9, 1)} s`,
        `  Tráfico por rainproxy-resi-es: ${r.float(0.01, 0.4)} GB · sesión ${r.id(6)}`,
        `  AVISO ${shot}: el juez descarta la primera opción (texto encima); pasa al siguiente candidato`,
        `  ${shot}: siguiente candidato ${r.id()} de «${r.pick(["Motor Clásico TV", "British Pathé", "AP Archive", "RTVE Archivo"])}»`,
        `  caché: ${r.int(3, 40)} búsquedas reutilizadas, ${r.int(0, 6)} nuevas (${r.int(0, 600)} unidades)`,
        `  ${shot}: plano de ${r.float(2.1, 7.9, 1)} s · «${r.pick(["la fábrica de Dunmurry", "el túnel de viento", "la rueda de prensa", "el circuito de pruebas"])}»`,
      ]));
    }
    if (n < upto || (!v.stage && !v.error && !v.lastError)) lines.push(`[${n}/15] ${name}: hecho en ${r.float(4, 620, 1)} s · RAM máx. ${r.float(0.9, 5.8, 1)} GB`);
  }
  if (v.error || v.lastError) lines.push(...String(v.error || v.lastError).split("\n").map((l, i) => (i ? l : "ERROR " + l)), `FALLO en la etapa ${ORDER[Math.min(14, v.stagesDone)]}: el vídeo vuelve a la cola`);
  return lines.join("\n");
}

function diagnosisText(v) {
  return `# Diagnóstico de ${v.slug}\n\n**Resultado:** ${v.status === "hecho" ? "vídeo terminado sin avisos graves" : "a medias"} · coste ${v.costUsd} $ · ${v.minutes} min de trabajo.\n\n` +
    `## Planos\n\n| Origen | Planos | Segundos | Nota media |\n|---|---|---|---|\n| YouTube | 31 | 214 | 0.81 |\n| Fotos | 14 | 71 | 0.77 |\n| Stock | 6 | 28 | 0.69 |\n| Gráficos | 7 | 44 | — |\n\n` +
    `## Avisos\n\n- 3 planos usan la **segunda opción** del juez (la primera tenía texto encima)\n- 1 plano de relleno de \`stock\` en el capítulo 3: revisa «Decisiones del relleno»\n- El gancho cumple la promesa del título a los _11 segundos_\n\n` +
    `## Hoja de contacto\n\n![contacto](qa/contacto.jpg)\n\n## Coste por servicio\n\n| Servicio | Llamadas | $ |\n|---|---|---|\n| OpenRouter (juez) | 212 | 0.38 |\n| GenAIPro (voz) | 9 | 0.21 |\n| Whisper (alineado) | 1 | 0.04 |\n\n` +
    `Más detalle en [el registro](#/video/${v.slug}).\n\n\`\`\`\nplanner: 58 planos · 11,4 cortes/min\njudge: 212 veredictos (64 reutilizados)\n\`\`\`\n`;
}

const youtubeTxt = (v) => `TÍTULO\n1. ${v.title}\n2. ${v.title.split(":")[0]}: lo que nadie te contó\n3. El error de 250 millones detrás de ${v.title.split(":")[0]}\n\nDESCRIPCIÓN\n${v.title}. La historia completa, con imágenes de archivo y las cifras reales.\n\n00:00 El principio\n02:14 La primera grieta\n05:48 El día que todo se torció\n09:30 Lo que quedó\n\nFuentes: hemerotecas de El País y La Vanguardia, British Pathé, AP Archive.\n\nETIQUETAS\nhistoria, documental, ${v.channel}, fracasos, ${slugify(v.title.split(":")[0]).replace(/-/g, " ")}\n\nCOMENTARIO FIJADO\n¿Conocías esta historia? ¿Qué otro caso quieres que contemos? 👇\n\nPOST DE COMUNIDAD\nHoy a las 18:00: ${v.title}. ¿Crees que se pudo evitar? 🅰️ Sí 🅱️ No\n\nIDEAS PARA LA MINIATURA\n«250 MILLONES» · «NADIE LO VIO» · «EL ERROR»\n`;

function sections(text) {
  const out = {}; let key = null;
  for (const line of text.split("\n")) { if (/^[A-ZÁÉÍÓÚÑ ]{5,}$/.test(line.trim())) { key = line.trim(); out[key] = ""; } else if (key) out[key] += line + "\n"; }
  for (const k of Object.keys(out)) out[k] = out[k].trim();
  return out;
}

function videoDetail(st, slug) {
  const v = st.videos.find((x) => x.slug === slug);
  if (!v) return null;
  const r = rng("detail:" + slug);
  const done = v.stagesDone;
  const stages = ORDER.slice(0, done).map((name, i) => ({name, seconds: r.float(8, name === "render" ? 900 : name === "sourcing" ? 700 : 260, 1),
    ram: r.float(0.8, 6.2, 1), cpu: r.int(35, 390), at: isoAt(NOW - (done - i) * 600000)}));
  const finished = v.status === "hecho", has = v.hasVideo;
  const costs = Object.fromEntries(ORDER.slice(0, done).filter((n) => ["factcheck", "planner", "judge", "analysis", "package", "align"].includes(n)).map((n) => [n, r.float(0.01, 0.4)]));
  const base = st.videos.filter((x) => x.dubOf === slug);
  const lang = {pt: "Portugués", en: "Inglés", de: "Alemán", fr: "Francés"};
  let dubs = [];
  if (slug === SPECIAL.hecho) dubs = [
    {lang: "pt", name: lang.pt, slug: slug + "-pt", script: "", title: "", own: false, voice: false, voiceId: true, manual: false, done: true, review: false, skipped: false, old: false, error: "", adapted: ""},
    {lang: "en", name: lang.en, slug: slug + "-en", script: "## Chapter 1\nThe Citroën DS did not look like a car. In 1955 it looked like the future…\n\n## Chapter 2\nTwelve thousand orders on the first day.", title: "The Citroën DS: the car from the future", own: false, voice: false, voiceId: true, manual: false, done: false, review: true, skipped: false, old: false, error: "",
      adapted: "Adaptación\n\n- Las pesetas pasan a dólares de la época\n- «La DGT» se explica como **la autoridad de tráfico española**\n- El refrán del capítulo 3 se cambia por uno inglés"},
    {lang: "de", name: lang.de, slug: slug + "-de", script: "", title: "", own: false, voice: false, voiceId: false, manual: false, done: false, review: false, skipped: true, old: false, error: "", adapted: ""},
    {lang: "fr", name: lang.fr, slug: slug + "-fr", script: "## Chapitre 1\nLa DS ne ressemblait à rien de connu.", title: "", own: true, voice: false, voiceId: true, manual: false, done: false, review: false, skipped: false, old: false, error: "GenAIPro: 429 al generar el trozo 3 de 9 (se reintenta)", adapted: ""}];
  else if (base.length) dubs = base.map((d) => ({lang: d.slug.split("-").pop(), name: lang[d.slug.split("-").pop()] || "Portugués", slug: d.slug, script: "", title: d.title, own: false, voice: true, voiceId: true, manual: false, done: true, review: false, skipped: false, old: false, error: "", adapted: ""}));
  const thumbnails = has || finished ? ["miniaturas/miniatura-1.jpg", "miniaturas/miniatura-2.jpg", "miniaturas/miniatura-3.jpg"] : [];
  const shorts = has && !v.short ? ["shorts/short-1.mp4", "shorts/short-2.mp4", "shorts/short-3.mp4"] : [];
  const requests = 180 + r.int(0, 400), ok = Math.round(requests * r.float(0.62, 0.97));
  return {
    ...v, stages, log: logText(v, r),
    diagnosis: done >= 5 ? diagnosisText(v) : null,
    factcheck: done >= 1 ? `# Verificación del guion\n\n- ✅ **1974**: fecha de fundación confirmada (dos fuentes)\n- ✅ **3.000 pedidos**: coincide con la prensa de la época\n- ⚠️ **1.400 dólares por unidad**: una sola fuente; dilo como «según un informe interno»\n- ❌ «el más vendido de Europa»: no consta; quítalo o matízalo\n` : null,
    youtubeTxt: finished ? youtubeTxt(v) : null,
    graphics: done >= 11 ? `# Gráficos\n\n| Minuto | Tipo | Texto |\n|---|---|---|\n| 0:42 | cifra | 3.000 pedidos |\n| 2:14 | mapa | Belfast → Nueva York |\n| 5:50 | línea de tiempo | 1974 – 1982 |\n| 9:31 | cita | «Nadie quiso verlo» |\n` : null,
    hook: done >= 10 ? `# Gancho\n\n**Veredicto:** ✅ cumple a los 11 s.\n\n- Promesa del título: explicar la caída\n- Primera frase: una fecha y una cifra\n- Lo más fuerte del guion está en el minuto 5:48: súbelo a la apertura la próxima vez\n` : null,
    retention: v.published ? `# Retención\n\n**Media vista:** 41 % · **a los 30 s:** 68 %\n\n| Minuto | Se va | Qué se decía | Qué se veía |\n|---|---|---|---|\n| 0:28 | 9 % | la presentación del canal | logo 4 s |\n| 3:10 | 6 % | lista de cifras seguidas | la misma foto 11 s |\n| 7:45 | 4 % | resumen de lo ya dicho | stock genérico |\n\n- Quita la presentación: empieza en la fecha\n- Corta cada 4 s en las listas de cifras\n` : null,
    rhythm: done >= 12 ? `# Ritmo\n\n- 11,4 cortes por minuto (objetivo del canal: 10-13)\n- Plano más largo: 9,8 s en 6:02 (foto fija)\n- 2 tramos de más de 20 s sin gráfico\n` : null,
    audit: done >= 11 ? Array.from({length: 40}, (_, i) => `${Math.floor(i * 14 / 60)}:${String(i * 14 % 60).padStart(2, "0")}  «${r.pick(["En 1974 nadie dudaba", "La carta llegó un martes", "Tres mil pedidos", "El teléfono sonó a las 6:40", "Quedan 6.500 unidades"])}…» → ${r.pick(["youtube", "foto", "stock", "gráfico"])}:${r.id()} · ${r.pick(["juez", "siguiente opción", "protagonista", "relleno"])}`).join("\n") : null,
    thumbnails, scenesPreview: slug === SPECIAL.hecho || KINDS[v.channel] === "simulacion" && finished ? "vista-previa.jpg" : "",
    shorts, files: [...(has ? ["video-final.mp4", "preview.mp4"] : []), ...thumbnails, ...shorts, "log.txt", "diagnostico.md"],
    preview: has, script: v.status === "incompleto" && !v.title ? "" : scriptText(v),
    format: {name: KINDS[v.channel] === "simulacion" ? "simulacion" : r.pick(["historia", "caso-real", "caida-y-regreso"]), auto: r.chance(0.5), why: "El guion cuenta un ascenso, un error y sus consecuencias: encaja con «caída y regreso»."},
    dubs,
    youtube: done >= 4 ? {hours: 24, proxy: ["rainproxy-resi-es", "casa-pc:8899"], requests, ok, failed: requests - ok, files: 64, files_ok: 58 + r.int(0, 6),
      proxy_gb: r.float(0.3, 2.8), sessions: r.int(3, 19), errors: {bot: r.int(0, 30), 403: r.int(0, 9), timeout: r.int(0, 5)},
      details: [["Sign in to confirm you’re not a bot", r.int(2, 30)], ["HTTP Error 403: Forbidden", r.int(1, 9)], ["Read timed out", r.int(1, 5)]],
      allTime: {requests: requests * 3, ok: ok * 3 - 40, files: 180, files_ok: 151, proxy_gb: r.float(2, 7)}} : null,
    costs,
  };
}

function porque(st, slug) {
  const v = st.videos.find((x) => x.slug === slug);
  if (!v || !v.published || !v.published.url) return {curve: null, report: null};
  const r = rng("porque:" + slug);
  const marks = [1, 3, 6, 12, 24, 48, 96, 168, 336, 720], age = (NOW - Date.parse(v.published.at + "Z")) / 3600000;
  const top = r.int(4000, 90000);
  const points = marks.filter((h) => h <= age).map((h) => [h, Math.round(top * Math.pow(h / 720, 0.55))]);
  const normal = marks.map((h) => { const m = Math.round(top * 0.6 * Math.pow(h / 720, 0.6)); return {hours: h, low: Math.round(m * 0.6), median: m, high: Math.round(m * 1.7)}; });
  const views = points.length ? points[points.length - 1][1] : 0;
  const usual = (normal.filter((b) => b.hours <= age).pop() || normal[0]).median;
  return {curve: {points, normal, views, age: +age.toFixed(1), usual, ratio: +(views / Math.max(1, usual)).toFixed(1)},
    report: {topic: "Una marca conocida con un final que casi nadie sabe: curiosidad alta desde el título.", title: "Nombre propio + contradicción («ganó tres mundiales» / «nadie sabía conducir»).",
      length: "11 minutos: dentro de lo que mejor retiene el canal (9-13).", hook: "Cumple la promesa a los 9 s con una imagen de archivo en movimiento.",
      lesson: "Repite la fórmula «bestia indomable» con otro coche de rally de los 70.", at: isoAt(NOW - 2 * DAY_MS)}};
}

const repeticion = (slug) => ({risk: hashOf(slug) % 3 === 0 ? "medio" : "bajo", compared: 12, checks: [
  {name: "Título", status: "ok", text: "No repite la plantilla de los últimos 12 (máximo 2 con «La caída de…»)."},
  {name: "Miniatura", status: hashOf(slug) % 3 === 0 ? "warn" : "ok", text: "Composición parecida a 4 de las últimas 12: mismo encuadre y mismo color de texto."},
  {name: "Metraje", status: "ok", text: "8 % de segundos compartidos con otros vídeos del canal (límite 25 %)."},
  {name: "Estructura", status: "ok", text: "Capítulos de duración distinta a los del vídeo anterior."},
  {name: "Voz", status: "skip", text: "La misma voz de siempre: YouTube no lo cuenta como repetición."}]});

function review(st, slug) {
  const r = rng("review:" + slug);
  const reasons = {persona_equivocada: "Sale otra persona", no_tiene_que_ver: "No tiene que ver con la frase", dibujo_animado: "Dibujo animado / videojuego",
    roto: "Roto, negro o muy mala calidad", texto_marca_agua: "Texto encima o marca de agua", repetido: "Repetido", habia_mejor: "Había una opción mejor", otro: "Otro"};
  const phrases = ["En 1955 nadie había visto nada igual", "Doce mil pedidos el primer día", "La suspensión hidroneumática lo cambiaba todo", "De Gaulle salió ileso del atentado de Petit-Clamart",
    "Los ingenieros trabajaron en secreto durante dieciocho años", "El salón de París se quedó en silencio", "Podía circular con tres ruedas", "Flaminio Bertoni lo esculpió como una estatua",
    "La prensa lo llamó «la diosa»", "Su fábrica de Javel ya no existe", "Costaba el sueldo de dos años de un obrero", "El motor, en cambio, era de antes de la guerra"];
  const shots = Array.from({length: 60}, (_, i) => {
    const id = "s" + String(i + 1).padStart(3, "0"), yt = r.id();
    const label = i < 22 ? {verdict: i % 9 === 4 ? "incorrecta" : i % 7 === 3 ? "dudosa" : "correcta", reason: i % 9 === 4 ? r.pick(Object.keys(reasons)) : ""} : null;
    return {id, text: r.pick(phrases) + (i % 5 === 0 ? ", y aquello fue solo el principio de una historia que duraría veinte años" : ""), at: +(i * 11.3).toFixed(1),
      title: i % 6 === 5 ? "" : r.pick(["Citroën DS 19 – Salon de Paris 1955 (INA)", "La DS: historia de un mito", "British Pathé: Paris Motor Show", "Petit-Clamart: el atentado", "Citroën, les années DS"]),
      credit: r.pick(["INA", "British Pathé", "Wikimedia Commons", "Citroën Origins"]), source: r.pick(["youtube", "foto", "stock"]), url: i % 6 === 5 ? "" : watch(yt), label};
  });
  return {shots, reasons, job: IDLE()};
}

function decisions(st, slug) {
  const r = rng("decisions:" + slug);
  const kinds = ["la primera elección no se pudo descargar", "el juez la rechazó al ver los fotogramas", "duraba menos que el plano", "ya se había usado en este vídeo", "tenía texto encima"];
  const items = Array.from({length: 12}, (_, i) => {
    const shot = "s" + String(3 + i * 4).padStart(3, "0");
    const options = Array.from({length: 2 + (i % 4)}, (_, k) => ({key: `${k ? "yt" : "orig"}-${r.id(8)}`, title: r.pick(["Citroën DS 19 – Salon de Paris 1955", "La DS en el túnel de viento de Javel", "De Gaulle y su DS presidencial (archivo)", "Así funciona la suspensión hidroneumática explicada con una maqueta"]),
      channel: r.pick(["INA Officiel", "Citroën Origins", "British Pathé", "Petrolicious"]), score: k === 1 && i % 5 === 0 ? null : r.float(0.5, 0.95), kind: k === 2 ? "image" : "video", original: k === 0}));
    return {shot, text: r.pick(["Doce mil pedidos el primer día", "Podía circular con tres ruedas", "La prensa lo llamó «la diosa»", "El salón de París se quedó en silencio"]),
      verdict: i % 4 === 1 ? "correcta" : null, pick: i % 4 === 2 ? options[1].key : null, kind: kinds[i % kinds.length],
      reason: i % 3 === 0 ? "ERROR: unable to download video data: HTTP Error 403: Forbidden (tras 3 intentos por rainproxy-resi-es y 1 por casa-pc); se pasa al siguiente candidato de la lista del juez" : kinds[i % kinds.length],
      judgeReason: i % 2 ? "Se ve un coche parecido pero es un ID 19 de 1962, no el DS de la presentación; además lleva un rótulo de televisión en la esquina." : "",
      method: r.pick(["Siguiente opción", "Otro clip del protagonista", "Foto de archivo", "Stock"]), resolved: i !== 7, options};
  });
  return {items, summary: {tips: ["De 31 decisiones recuperadas por ti, 19 fueron por «texto encima»: esa comprobación descarta demasiado en vídeos de archivo.", "El relleno con foto de archivo se marca «bien así» el 86 % de las veces."]}, job: IDLE()};
}

// --- radar ----------------------------------------------------------------------------------------------------------
function buildRadar() {
  const r = rng(4242);
  const makers = ["Historias del Motor", "Archivo Secreto", "El Mapa de Sebas", "Memorias de Pez", "Academia Play", "Curiosidades con Mike", "VisualPolitik", "Un Mundo Inmenso", "Doc Tops", "El Robot de Platón", "Lemmino en español", "Zoomin"];
  const tile = (channel, i) => { const id = r.id(), subject = r.pick(SUBJECTS[channel] || SUBJECTS["historia-rara"]);
    const ratio = r.float(2, i < 3 ? 48 : 9, 1), ageDays = r.int(1, 30);
    return {id, url: watch(id), thumbnail: thumb(id), title: fill(r.pick(TEMPLATES), subject), channel: r.pick(makers), subscribers: r.chance(0.9) ? r.int(8, 900) * 1000 : null,
      views: r.int(20, 2400) * 1000, ageDays, ratio, new: r.chance(0.3), why: r.chance(0.6) ? r.pick(["Nombre propio + cifra en el título", "Tema de actualidad esta semana", "Miniatura con una sola cara y dos palabras", "Formato «caída y regreso» en 12 minutos"]) : "",
      ...(i % 4 === 0 ? {viral: Math.min(100, Math.round(50 * Math.log10(ratio)) + (ageDays <= 7 ? 10 : 0))} : {})}; };
  const radarChannels = ["ajedrez", "aviones", "barcos", "coches", "crimenes", "espacio", "estafas", "formula1", "gimnasia", "historia-rara", "trenes", "volcanes"];
  const channels = Object.fromEntries(radarChannels.map((c, n) => [c, {top: Array.from({length: n === 4 ? 0 : r.int(12, 20)}, (_, i) => tile(c, i)),
    errors: n % 5 === 1 ? ["@CanalQueYaNoExiste: no encontrado", "cuota: 2 búsquedas sin hacer"] : []}]));
  const rising = Array.from({length: 9}, (_, i) => { const id = r.id(), c = r.pick(BASE_CHANNELS), subject = r.pick(SUBJECTS[c]);
    return {thumbnail: i % 4 === 3 ? "" : avatar(r.id(20)), url: "https://www.youtube.com/channel/UC" + r.id(22), title: r.pick(["Crónicas de Acero", "El Archivo Perdido", "Minuto Histórico", "Ruedas y Ruina", "Planeta Récord", "La Caja Negra", "Oficios Extintos", "Deportes Olvidados", "Mapas que Hablan"]) + (i > 5 ? " " + (i - 4) : ""),
      new: i % 3 === 0, subscribers: r.int(2, 48) * 1000, videos: r.int(6, 80), ageDays: r.int(40, 700), fit: i % 5 === 4 ? null : r.int(2, 9),
      best: {url: watch(id), thumbnail: thumb(id), title: fill(r.pick(TEMPLATES), subject), views: r.int(150, 3200) * 1000}, multiple: r.float(6, 140, 1), medianViews: i % 4 ? r.int(8, 90) * 1000 : 0,
      format: r.pick(["Documental de archivo con voz en off, 10-14 min", "Mapas animados con narración", "Ranking con cuenta atrás", "Un caso real contado como thriller"]),
      why: "Títulos con nombre propio y una contradicción; miniaturas de una sola imagen de archivo muy contrastada.", how: i % 2 ? "Se puede hacer tal cual con el formato «caso real» y fotos de hemeroteca." : "",
      latest: i % 3 === 2 ? [] : Array.from({length: 5}, () => ({url: watch(r.id()), title: fill(r.pick(TEMPLATES), r.pick(SUBJECTS[c])), views: r.int(4, 900) * 1000})),
      query: i % 4 === 1 ? "" : slugify(subject).replace(/-/g, " ") + " documental", niche: i % 2 ? "Historias de " + c : ""}; });
  const verdicts = ["hueco", "hueco en inglés", "a vigilar", "saturado", "sin demanda"];
  const gapNames = ["Desastres de ingeniería", "Marcas de coches desaparecidas", "Récords deportivos imposibles", "Estafas piramidales españolas", "Trenes abandonados", "Submarinos perdidos", "Oficios que ya no existen", "Ciudades fantasma", "Aerolíneas quebradas",
    "Juicios históricos", "Expediciones polares", "Inventos españoles olvidados", "Accidentes de montaña rusa", "Bancos que quebraron", "Islas deshabitadas", "Puentes que se cayeron", "Motos de los 80", "Videoclubs y Blockbuster"];
  const gaps = gapNames.map((name, i) => ({name, new: i % 5 === 0, query_es: name.toLowerCase(), query_en: i % 3 === 2 ? "" : slugify(name).replace(/-/g, " ") + " documentary", date: day(-(i % 6)), origin: i % 7 === 3 ? "manual" : "radar",
    score: r.float(1.2, 9.6, 1), trend: i % 4 === 0 ? null : r.float(-1.8, 2.2, 1), verdict: verdicts[i % 5 === 4 ? 4 : i % 4], demand: r.int(30, 900) * 1000, perDay: r.int(200, 9000), recent: r.int(2, 48), recentChannels: r.int(2, 30),
    smallWins: r.int(0, 6), bigShare: r.float(0.1, 0.9), englishGap: i % 3 === 2 ? 0 : r.float(1.1, 8.4, 1), englishDemand: r.int(200, 4000) * 1000, searched: i % 6 === 5 ? null : r.int(1, 10), fit: i % 7 === 6 ? null : r.int(3, 10),
    why: i % 2 ? "Mucha búsqueda y solo dos canales medianos lo cubren con regularidad; el mismo tema en inglés multiplica las visitas." : "",
    examples: Array.from({length: i % 6 === 1 ? 0 : 4}, () => { const id = r.id(); return {url: watch(id), title: fill(r.pick(TEMPLATES), r.pick(SUBJECTS["ingenieria"])), views: r.int(40, 2000) * 1000, channel: r.pick(makers), subscribers: r.chance(0.8) ? r.int(5, 600) * 1000 : null, thumbnail: thumb(id)}; }),
    ideas: i % 3 === 0 ? ["El puente que se cayó a los cuatro meses de inaugurarse", "La presa que nadie quiso revisar"] : []}));
  const nicheNames = ["Aviones que nunca volaron", "Trampas legales en el deporte", "Pueblos comprados enteros", "Robos sin resolver", "Líneas de metro fantasma", "Coches del bloque soviético", "Barcos encallados", "Superordenadores olvidados", "El negocio de los faros",
    "Naufragios del Cantábrico", "Circuitos abandonados", "Marcas blancas y quién las fabrica", "Récords Guinness absurdos", "Minas a cielo abierto", "Túneles imposibles", "Parques de atracciones cerrados", "Aeropuertos sin aviones", "Los Juegos Olímpicos que arruinaron ciudades",
    "Animales invasores", "Imperios de un solo hombre", "Rascacielos vacíos", "Fábricas del franquismo", "Estaciones de esquí sin nieve", "Cadenas de comida rápida desaparecidas"];
  const niches = nicheNames.map((name, i) => ({name, near: i % 3 === 0 ? "descubierto" : i % 3 === 1 ? r.pick(BASE_CHANNELS) : "libre", date: day(-(i % 9)), score: r.float(1.5, 9.4, 1),
    examples: Array.from({length: i % 8 === 7 ? 0 : 3}, () => { const id = r.id(); return {url: watch(id), title: name + ": " + r.pick(["la historia completa", "lo que nadie cuenta", "el final"]), ratio: r.float(3, 40, 1), channel: r.pick(makers), thumbnail: thumb(id)}; }),
    smallHits: r.int(1, 14), hits: r.int(3, 40), medianViews: r.int(12, 700) * 1000, medianRatio: r.float(1.2, 7.5, 1), why: i % 2 ? "Canales de menos de 20 mil suscriptores con varios vídeos por encima de 300 mil visitas en el último mes." : "",
    query: name.toLowerCase(), ideas: i % 4 === 0 ? r.int(3, 9) : 0}));
  const story = (channel) => { const subject = r.pick(SUBJECTS[channel] || SUBJECTS["historia-rara"]);
    return {name: subject[0].toUpperCase() + subject.slice(1), views: r.int(30, 4000) * 1000, channels: r.int(1, 6), speed: r.int(400, 42000),
      videos: Array.from({length: r.int(2, 5)}, () => { const id = r.id(); return {url: watch(id), thumbnail: thumb(id), title: fill(r.pick(TEMPLATES), subject), channel: r.pick(makers), perHour: r.int(100, 9000), ageHours: r.float(0.4, 47, 1)}; }),
      idea: {title: `${subject[0].toUpperCase() + subject.slice(1)}: qué ha pasado y por qué importa`, note: `Noticia de hoy sobre ${subject}: contar el contexto (de dónde viene), qué ha cambiado esta semana y qué puede pasar ahora. Fuentes: los tres vídeos que más suben.`, format: "caso-real"}}; };
  const newsChannels = ["general", "coches", "formula1", "gimnasia", "tenis", "espacio", "trenes"];
  const news = {at: isoAt(NOW - 3 * 3600000), channels: Object.fromEntries(newsChannels.map((c, i) => [c, Array.from({length: i === 5 ? 0 : r.int(3, 8)}, () => story(c === "general" ? "historia-rara" : c))])),
    comebacks: {gimnasia: [story("gimnasia"), story("gimnasia")], tenis: [story("tenis")], coches: [story("formula1")]}, errors: ["tenis: 1 búsqueda sin datos"]};
  for (const list of Object.values(news.comebacks)) for (const s of list) s.idea = {...s.idea, format: "caida-y-regreso"};
  const saved = Array.from({length: 7}, (_, i) => { const c = [...PARTNERS.marc, "aviones", "barcos"][i]; const subject = SUBJECTS[c][i % 6];
    return {id: "idea-" + r.id(8), title: fill(TEMPLATES[i], subject), channel: c, format: i % 2 ? "caso-real" : "", angle: "Contarlo desde la persona que avisó y a la que nadie escuchó; cerrar con qué queda hoy.",
      hook: "Una carta de dos páginas pudo evitarlo todo.", outline: ["La promesa", "La primera grieta", "El día clave", "Lo que quedó"], protagonist: subject}; });
  return {latest: {date: TODAY, outOfQuota: false, channels, rising}, niches, job: IDLE(), newsJob: IDLE(), gaps, saved, channels: CHANNELS, news};
}

function myChannel(channel) {
  const r = rng("mychannel:" + channel);
  const monthNames = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
  const months = Array.from({length: 12}, (_, i) => { const d = new Date(NOW); d.setUTCMonth(d.getUTCMonth() - 11 + i);
    return {month: `${monthNames[d.getUTCMonth()]} ${d.getUTCFullYear()}`, long: r.int(2, 13), shorts: r.int(0, 9), views: r.int(20, 900) * 1000, ratio: i === 3 ? null : r.float(0.4, 2.3, 1)}; });
  const vt = (good) => Array.from({length: 8}, (_, i) => { const id = r.id(), subject = r.pick(SUBJECTS[channel]);
    return {id, url: watch(id), thumbnail: thumb(id), title: fill(r.pick(TEMPLATES), subject), views: good ? r.int(80, 1900) * 1000 : r.int(1, 12) * 1000, ratio: good ? r.float(2.1, 14, 1) : r.float(0.1, 0.6, 1),
      short: i % 4 === 3, published: isoAt(NOW - r.int(9, 400) * DAY_MS) + "Z", subscribers: null}; });
  return {handle: "@" + channel.split("-").map((w) => w[0].toUpperCase() + w.slice(1)).join("") + "Docu", job: IDLE(), report: {
    generated: isoAt(NOW - 26 * 3600000) + "Z", channel: {title: "Historias de " + channel.replace(/-/g, " ")},
    numbers: {subscribers: r.int(8, 240) * 1000, views: r.int(2, 60) * 1e6, videos: r.int(80, 320), long: r.int(60, 180), shorts: r.int(20, 120), medianLong: r.int(8, 60) * 1000, medianShort: r.int(2, 30) * 1000,
      hits: r.int(6, 40), last28: {videos: r.int(6, 22), views: r.int(90, 1400) * 1000}},
    months, winners: vt(true), losers: vt(false), timezone: "Madrid",
    blocks: ["0-3", "3-6", "6-9", "9-12", "12-15", "15-18", "18-21", "21-24"], days: ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"],
    heat: Array.from({length: 7}, () => Array.from({length: 8}, (_, b) => { const count = b < 2 ? 0 : r.chance(0.7) ? r.int(1, 14) : 0; return {count, ratio: count ? r.float(0.4, 2.4, 1) : null}; })),
    perDay: ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"].map((d) => ({day: d, count: r.int(4, 40), ratio: r.float(0.6, 1.9, 1)})),
    consistencyNote: "En agosto subiste la mitad que en julio y las visitas por vídeo cayeron un 30 % el mes siguiente: mantén al menos 8 al mes.",
    titles: {typicalLength: 58, traits: [["Lleva un nombre propio", 1.8, 64], ["Lleva una cifra", 1.4, 41], ["Es una pregunta", 0.7, 23], ["Tiene dos puntos (:)", 1.2, 77], ["Más de 70 letras", 0.6, 19], ["Empieza por «Por qué»", 1.6, 28], ["Lleva paréntesis", 0.9, 12]]
      .map(([name, factor, count]) => ({name, factor, count}))},
    durations: [["Menos de 6 min", 9, 0.6], ["6-9 min", 31, 0.9], ["9-13 min", 58, 1.4], ["13-20 min", 22, 1.1], ["Más de 20 min", 3, null]].map(([name, count, ratio]) => ({name, count, ratio})),
    topics: SUBJECTS[channel].map((s, i) => ({name: s[0].toUpperCase() + s.slice(1), thumbnail: i === 4 ? "" : thumb(r.id()), ratio: r.float(0.3, 2.6, 1), count: r.int(3, 24), hits: r.int(0, 7), medianViews: r.int(4, 140) * 1000}))
      .sort((a, b) => b.ratio - a.ratio),
    tips: ["Tus vídeos de 9 a 13 minutos rinden un 40 % más que el resto: apunta ahí.", "Los jueves y domingos por la tarde son tus mejores franjas.", "Un nombre propio en el título casi duplica las visitas."]}};
}

// --- stats, spend ---------------------------------------------------------------------------------------------------
const median = (list) => { const s = [...list].sort((a, b) => a - b); return s.length ? (s.length % 2 ? s[(s.length - 1) / 2] : (s[s.length / 2 - 1] + s[s.length / 2]) / 2) : 0; };

function stats(st, mine) {
  const rows = [], perChannel = {};
  for (const v of st.videos) {
    if (v.status !== "hecho" || v.archived || v.dubOf || (mine && !mine.includes(v.channel))) continue;
    const r = rng("stats:" + v.slug);
    let youtube = null;
    if (v.published && v.published.url) {
      const ageDays = Math.max(1, Math.round((NOW - Date.parse(v.published.at + "Z")) / DAY_MS));
      const views = Math.round(Math.pow(10, r.float(2.6, 5.6, 3)) * (v.short ? 0.6 : 1)), minutes = v.short ? r.float(0.5, 1) : r.float(7, 16, 1);
      youtube = {title: r.chance(0.8) ? v.title : v.title.split(":")[0] + " | Documental", thumbnail: thumb(v.published.url.slice(-11)), views, perDay: Math.round(views / ageDays),
        at48h: ageDays >= 2 && r.chance(0.9) ? Math.round(views * r.float(0.1, 0.4)) : null, at7d: ageDays >= 7 && r.chance(0.9) ? Math.round(views * r.float(0.4, 0.8)) : null,
        watchHours: Math.round(views * minutes / 60 * 0.35), vsChannel: null, likesPer1k: r.float(12, 68, 1), commentsPer1k: r.float(0.4, 9, 1), ageDays, minutes};
    }
    rows.push({slug: v.slug, title: v.title || v.slug, channel: v.channel, status: v.published ? "subido" : "hecho", url: (v.published || {}).url || "", publishedDay: v.published ? v.published.at.slice(0, 10) : null, youtube,
      production: {usd: v.costUsd, ytUnits: r.chance(0.85) ? r.int(8, 90) * 100 : 0, ytEstimated: r.chance(0.2), minutes: v.minutes, duration: v.short ? r.int(28, 58) : r.int(420, 960), cutsPerMin: r.float(7, 16, 1),
        mix: Object.fromEntries([["youtube", r.int(12, 40)], ["fotos", r.int(4, 22)], ["stock", r.int(0, 9)], ["generadas", r.int(0, 4)], ["gráficos", r.int(2, 9)]].filter(([, n]) => n)),
        labels: r.chance(0.3) ? {correcta: r.int(20, 58), incorrecta: r.int(0, 7)} : {correcta: 0, incorrecta: 0}}});
  }
  for (const row of rows) (perChannel[row.channel] = perChannel[row.channel] || []).push(row);
  const channels = Object.entries(perChannel).sort().map(([channel, list]) => {
    const yt = list.filter((x) => x.youtube), views = yt.reduce((a, x) => a + x.youtube.views, 0), usd = +list.reduce((a, x) => a + x.production.usd, 0).toFixed(2);
    const med = median(yt.map((x) => x.youtube.views));
    for (const x of yt) x.youtube.vsChannel = med ? +(x.youtube.views / med).toFixed(1) : null;
    const best = [...yt].sort((a, b) => b.youtube.views - a.youtube.views)[0];
    const hours = yt.reduce((a, x) => a + x.youtube.watchHours, 0);
    return {channel, views, watchHours: hours, published: list.filter((x) => x.status === "subido").length, made: list.length, usd, watchHours12m: Math.round(hours * 0.8), median: med,
      usdPerVideo: +(usd / list.length).toFixed(2), usdPer1kViews: views ? +(1000 * usd / views).toFixed(3) : null, best: best ? {title: best.youtube.title, views: best.youtube.views} : null};
  });
  const totals = Object.fromEntries(["views", "watchHours", "published", "made", "usd"].map((k) => [k, +channels.reduce((a, c) => a + (c[k] || 0), 0).toFixed(2)]));
  return {videos: rows, channels, fetched: Math.round(NOW / 1000) - 5400, retention: 0.35, totals};
}

function gasto(st, mine, who) {
  const providers = ["OpenRouter (juez y planos)", "GenAIPro (voz)", "Whisper (alineado)", "Anthropic (guion y verificación)", "Replicate (imágenes)"];
  const videos = [];
  for (const v of st.videos) {
    if (!v.stagesDone || !v.costUsd || (mine && !mine.includes(v.channel))) continue;
    const r = rng("gasto:" + v.slug), done = v.status === "hecho", usd = v.costUsd;
    const parts = [0.46, 0.28, 0.06, 0.15, 0.05].map((p) => +(usd * p).toFixed(3));
    const px = r.chance(0.8) ? r.float(0.2, 2.6) : 0;
    videos.push({slug: v.slug, channel: v.channel, last: isoAt(v.updated * 1000).replace("T", " ").slice(0, 16), usd, proxyUsd: +(px * 3.5).toFixed(2), proxyGb: px, proxyRequests: px ? r.int(120, 900) : 0, proxyEstimated: px > 0 && r.chance(0.15),
      savedUsd: r.chance(0.5) ? r.float(0.02, 0.4) : 0, reused: r.chance(0.8) ? {judge: r.int(0, 90), voice: r.int(0, 6000)} : undefined, workSeconds: v.minutes * 60, ytUnits: r.chance(0.85) ? r.int(8, 90) * 100 : 0, ytSearches: r.int(8, 90),
      ytEstimated: r.chance(0.2), minutes: done ? (v.short ? r.float(0.5, 1) : r.float(7, 16, 1)) : 0, done, providers: Object.fromEntries(providers.map((p, i) => [p, parts[i]]).filter(([, x]) => x > 0))});
  }
  const sum = (list, k) => +list.reduce((a, x) => a + (x[k] || 0), 0).toFixed(2);
  const agg = (list) => { const done = list.filter((x) => x.done), usd = done.map((x) => x.usd), mins = sum(done, "minutes");
    return {average: done.length ? +(sum(done, "usd") / done.length).toFixed(2) : null, median: done.length ? +median(usd).toFixed(2) : null, perMinute: mins ? +(sum(done, "usd") / mins).toFixed(3) : null, done: done.length, videos: list.length,
      total: sum(list, "usd"), inProgress: sum(list.filter((x) => !x.done), "usd"), ytUnits: done.length ? Math.round(sum(done, "ytUnits") / done.length) : null, ytSearches: done.length ? Math.round(sum(done, "ytSearches") / done.length) : null,
      ytKeys: done.length ? +(sum(done, "ytUnits") / done.length / 10000).toFixed(1) : null, proxyUsd: done.length ? +(sum(done, "proxyUsd") / done.length).toFixed(2) : null, proxyGb: done.length ? +(sum(done, "proxyGb") / done.length).toFixed(2) : null}; };
  const byChannel = {};
  for (const v of videos) (byChannel[v.channel] = byChannel[v.channel] || []).push(v);
  const channels = Object.entries(byChannel).sort().map(([channel, list]) => { const dearest = [...list].sort((a, b) => b.usd - a.usd)[0]; return {channel, ...agg(list), dearest: {slug: dearest.slug, usd: dearest.usd}}; });
  const r = rng("gasto-days" + (who || ""));
  const scale = mine ? 0.18 : 1;
  const days = Array.from({length: 30}, (_, i) => ({day: day(i - 29), usd: i % 11 === 6 ? 0 : +(r.float(1.5, 14) * scale).toFixed(2)}));
  const total = sum(videos, "usd");
  const provTotals = Object.fromEntries(providers.map((p) => [p, +videos.reduce((a, v) => a + (v.providers[p] || 0), 0).toFixed(2)]));
  const month = (n) => { const d = new Date(NOW); d.setUTCDate(1); d.setUTCMonth(d.getUTCMonth() - n); return d.toISOString().slice(0, 7); };
  const person = (name, k) => { const api = +(r.float(20, 160) * k).toFixed(2), voice = +(r.float(6, 50) * k).toFixed(2), gb = +(r.float(4, 40) * k).toFixed(2), server = 16;
    return {who: name, videos: videos.filter((v) => (name ? PARTNERS[name].includes(v.channel) : true)).slice(0, name ? 9 : 40).map((v) => v.slug), api, voice, proxyUsd: +(gb * 3.5).toFixed(2), proxyGb: gb, server, total: +(api + voice + gb * 3.5 + server).toFixed(2)}; };
  const invoices = [0, 1, 2].map((n) => ({month: month(n), serverUsd: 48, parts: 3, hours: null, people: n === 2 && who ? [] : (who ? [person(who, 0.25)] : [person("", 1), person("marc", 0.25), person("laia", 0.1)])}));
  const o = agg(videos);
  const stageNames = ["Verificar datos", "Alinear la voz", "Planificar planos", "Buscar material", "Analizar clips", "Elegir (juez)", "Descargar en HD", "Personas", "Rellenar huecos", "Apertura", "Montaje", "Revisión", "Render", "Shorts", "Títulos y miniaturas"];
  const done = videos.filter((x) => x.done), seconds = done.reduce((a, x) => a + x.workSeconds, 0);
  const share = [2, 3, 4, 22, 9, 12, 14, 3, 6, 2, 4, 3, 11, 3, 2];
  return {today: +(days[29].usd).toFixed(2), total, overall: {...o, week: sum(days.slice(-7), "usd"), month: sum(days.slice(-new Date(NOW).getUTCDate()), "usd")}, others: {total: +(31.4 * scale).toFixed(2)}, days, channels, providers: provTotals, videos,
    savings: {perVerdict: 0.0018, perKChars: 0.024, usd: +(42.7 * scale).toFixed(2), share: 0.17, verdicts: Math.round(18400 * scale), verdictsUsd: +(33.1 * scale).toFixed(2), voiceChars: Math.round(402000 * scale), voiceUsd: +(9.648 * scale).toFixed(3)},
    pipeline: {videos: done.length, seconds, usd: sum(done, "usd"), averageSeconds: done.length ? Math.round(seconds / done.length) : null, averageUsd: o.average,
      stages: stageNames.map((name, i) => ({name, seconds: Math.round(seconds * share[i] / 100)})).sort((a, b) => b.seconds - a.seconds)},
    ytToday: {used: 38400, total: 60000, searches: 371, searchesPerDay: 600, keys: 6, reset: "09:00"},
    proxy: {usd: +(sum(videos, "proxyUsd")).toFixed(2), gb: sum(videos, "proxyGb"), requests: videos.reduce((a, v) => a + v.proxyRequests, 0), videos: videos.filter((v) => v.proxyGb).length, since: Math.round((NOW - 96 * DAY_MS) / 1000), usdPerGb: 3.5,
      estimatedVideos: videos.filter((v) => v.proxyEstimated).length, mbPerRequest: 0.4, metadataUsdPerGb: 8},
    allChannels: mine || CHANNELS, invoices, ...(who ? {partner: who} : {serverUsdMonth: 48})};
}

function proxyReport(days) {
  const r = rng("proxy" + days);
  const perDay = Array.from({length: Math.round(days)}, (_, i) => ({day: day(i - Math.round(days) + 1), gb: r.float(0.4, 6.2, 3)}));
  const totalGb = +perDay.reduce((a, d) => a + d.gb, 0).toFixed(3);
  return {days, usdPerGb: 3.5, totalGb, usd: +(totalGb * 3.5).toFixed(2), videos: 41, finished: 33, gbPerFinished: +(totalGb / 33).toFixed(3), perDay,
    proxies: [{proxy: "rainproxy-resi-es", requests: 18420, ok: 16210, failed: 2210, ok_share: 88, sessions: 412, gb: +(totalGb * 0.86).toFixed(3), errors: {bot: 1320, 403: 410, 429: 64, timeout: 233, other: 183},
      details: [["Sign in to confirm you’re not a bot", 1320], ["HTTP Error 403: Forbidden", 410], ["Read timed out. (read timeout=30)", 233], ["HTTP Error 429: Too Many Requests", 64], ["Tunnel connection failed: 502 Bad Gateway", 41]]},
    {proxy: "casa-pc:8899", requests: 2140, ok: 2011, failed: 129, ok_share: 94, sessions: 0, gb: +(totalGb * 0.14).toFixed(3), errors: {timeout: 88, other: 41}, details: [["Read timed out", 88]]}]};
}

function servidor(st) {
  const r = rng("servidor");
  const pending = st.videos.filter((v) => !v.archived && ["haciendo", "en cola", "error", "incompleto", "en pausa"].includes(v.status));
  const queue = pending.slice(0, 44).map((v) => {
    const kind = v.status === "haciendo" ? "haciendo" : v.status === "en pausa" ? "pausa" : v.status === "incompleto" ? "falta" : v.status === "error" ? "error"
      : v.quotaWait ? (v.quotaWait.startsWith("espera a YouTube") ? "youtube" : "cuota") : v.lastError ? "cola" : "turno";
    const why = {haciendo: `Etapa ${(v.stage || {}).number || 1}/15 · ${(v.stage || {}).stage || ""} desde hace ${r.int(2, 34)} min`, pausa: "Quitado de la cola por ti: no se hará hasta que lo vuelvas a poner",
      falta: v.voice ? "La voz automática falló: " + v.voice : "Falta el guion o la voz (sube guion.txt y voz.mp3)", error: String(v.error || "").split("\n")[0].slice(0, 160), youtube: v.quotaWait, cuota: v.quotaWait,
      cola: `Falló la última vez; se reintenta${v.retryAt ? " a las " + v.retryAt : " en su turno"}`, turno: `En su turno: ${v.stagesDone ? v.stagesDone + " de 15 etapas hechas" : "por empezar"} · sale el ${day(r.int(1, 12))}`}[kind];
    return {slug: v.slug, channel: v.channel, kind, why};
  });
  return {machine: {ramUsed: 21.4, ramTotal: 31.3, swapUsed: 1.2, cpu: 63.5, cores: 16, load: 9.84, diskFree: 142.6, diskTotal: 492},
    api: {searches: 371, searchesPerDay: 600, searchesLeft: 229, perHour: 34.5, keys: 6, runsOut: "hacia las 22:40", reset: "09:00"},
    proxy: {leftGb: 31.6, videosLeft: 23, bought: 100, usedGb: 68.4, since: day(-34), requests: 48210, videos: 51, perVideoGb: 1.34},
    ways: [["rainproxy-resi-es · sesión a1 (web)", "libre", 212, 400], ["rainproxy-resi-es · sesión a2 (tv)", "libre", 188, 400], ["rainproxy-resi-es · sesión b7 (ios)", "en cuarentena hasta las 19:20", 64, 400],
      ["casa-pc:8899 (proxy-youtube en el PC de casa)", "libre", 41, 0], ["directo (IP de la VPS)", "bloqueado: «no eres un bot»", 0, 0], ["API de YouTube (6 claves)", "libre", 34, 0]].map(([name, state, hour, perHour]) => ({name, state, hour, perHour})),
    queue, at: new Date(NOW).toISOString().slice(11, 19),
    backup: {name: `edit-vid3-${day(-3)}.tar.gz`, mb: 184.6, at: Math.round((NOW - 3 * DAY_MS) / 1000), folder: "/srv/copias"}};
}

const doctor = () => ({at: Math.round(NOW / 1000) - 240, rows: [
  {level: "ok", area: "ffmpeg", text: "ffmpeg 7.0 con libx264 y NVENC"}, {level: "ok", area: "Claves", text: "OPENROUTER, ANTHROPIC, GENAIPRO y 6 de YouTube presentes"},
  {level: "aviso", area: "Disco", text: "Quedan 142 GB: a este ritmo se llena en 19 días (se borran solos los vídeos subidos hace más de 7 días)"},
  {level: "aviso", area: "Proxy", text: "Una sesión de rainproxy en cuarentena desde las 17:20"}, {level: "error", area: "Cookies", text: "cookies.txt caducó el día 3: las descargas con cuenta fallan (súbelo otra vez)"},
  {level: "ok", area: "Telegram", text: "Bot conectado"}, {level: "ok", area: "Cola", text: "El vigilante late (hace 40 s)"}]});

// --- small pages ----------------------------------------------------------------------------------------------------
function buildVoices() {
  const r = rng(909), voices = {}, dubbing = {};
  CHANNELS.forEach((c, i) => {
    if (i % 4 !== 3) voices[c] = {voice_id: r.id(20), name: r.pick(["Narrador documental (Dani)", "Voz grave pausada", "Martín – cercano", "Lucía – noticias", "Hugo (deportes)"]), model_id: i % 5 === 0 ? "eleven_turbo_v2_5" : "eleven_multilingual_v2",
      ...(i % 3 === 0 ? {speed: 1.05, stability: 0.45, similarity: 0.8} : {})};
    dubbing[c] = c === "gimnasia" || c === "aviones" ? {languages: ["pt"], voices: {pt: {voice_id: r.id(20)}}, existing: true} : c === "historia-rara" ? {languages: ["en"], voices: {}, existing: false}
      : c === "coches" ? {languages: ["pt", "en", "fr"], voices: {pt: {voice_id: r.id(20)}}, existing: true} : c === "simulacion-trafico" ? {languages: ["pt", "de"], voices: {}, existing: true} : {languages: [], voices: {}};
  });
  return {voices, dubbing};
}

function voicesAnswer(st, mine, who) {
  const list = mine || CHANNELS, only = (o) => Object.fromEntries(Object.entries(o).filter(([c]) => list.includes(c)));
  return {voices: only(st.voices), channels: list, models: ["eleven_multilingual_v2", "eleven_turbo_v2_5", "eleven_flash_v2_5", "eleven_v3", "eleven_v4"],
    defaults: {model_id: "eleven_multilingual_v2", stability: 0.5, similarity: 0.75, style: 0.0, speed: 1.0, use_speaker_boost: true}, hasKey: true,
    dubbing: only(st.dubbing), dubLanguages: ["pt", "de", "fr", "en", "it"],
    speaks: Object.fromEntries(list.map((c) => [c, !!st.voices[c] || c in DUBBED])),
    dubOptions: only({"simulacion-trafico": [{lang: "pt", name: "Portugués", channel: "simulacion-trafico-br", voice: "Rafael (BR)"}, {lang: "de", name: "Alemán", channel: "simulacion-trafico-de", voice: null}, {lang: "en", name: "Inglés", channel: null, voice: "Adam"}],
      "simulacion-ciudades": [{lang: "pt", name: "Portugués", channel: "simulacion-ciudades-br", voice: "Rafael (BR)"}]}), ...(who ? {partner: who} : {})};
}

function piloto(st) {
  const r = rng(31337);
  return {radarDate: TODAY, channels: ["aviones", "coches", "estafas", "formula1", "gimnasia", "historia-rara", "trenes", "volcanes"].map((channel, i) => ({channel, on: i % 3 === 0, perDay: 1 + (i % 3), voice: !!st.voices[channel],
    error: i === 2 ? "El guion salió con 3 datos [COMPROBAR] sin fuente: no se puso en cola" : "", job: {...IDLE(), ...(i === 5 ? {failed: true, log: "Traceback…\nValueError: el radar de hoy no trae candidatos nuevos para historia-rara"} : {})},
    candidates: Array.from({length: i === 6 ? 0 : r.int(2, 5)}, (_, k) => { const id = r.id(); return {id, url: watch(id), thumbnail: k % 4 === 3 ? "" : thumb(id), title: fill(r.pick(TEMPLATES), r.pick(SUBJECTS[channel])),
      evidence: [`${r.float(3, 40, 1)}× su canal`, `${r.int(80, 2400)} mil visitas en ${r.int(2, 20)} días`, r.pick(["canal de 40 mil subs", "tema sin tocar en tu canal", "puntuación viral 72"])]}; }),
    made: st.videos.filter((v) => v.channel === channel && v.status === "hecho" && !v.archived).slice(0, i % 2 ? 3 : 0).map((v, k) => ({date: day(-2 - 3 * k), slug: v.slug, title: v.title, fromTitle: fill(r.pick(TEMPLATES), r.pick(SUBJECTS[channel])), angle: k % 2 ? "desde el ingeniero que avisó" : ""}))}))};
}

function experimentos(st) {
  const videos = st.videos.filter((v) => v.status === "hecho" && !v.archived && !v.dubOf).map((v) => { const r = rng("exp:" + v.slug), pub = v.published && r.chance(0.85);
    return {slug: v.slug, channel: v.channel, published: v.published ? v.published.at.slice(0, 10) : "", status: "hecho", views7d: pub ? r.int(300, 90000) : null, score: pub ? r.float(0.2, 4.1, 1) : null,
      tried: {formato: r.pick(["historia", "caso-real", "caída y regreso"]), "búsqueda": r.pick(["por plano", "por escenas"]), "duración": r.pick(["< 8 min", "8-12 min", "> 12 min"]), ritmo: r.pick(["< 10 cortes/min", "10-13 cortes/min", "> 13 cortes/min"])},
      tags: r.chance(0.25) ? [r.pick(["miniatura con cara", "gancho con pregunta", "título con cifra", "apertura con clip"])] : [], retention30: r.chance(0.2) ? r.int(48, 81) : null, retentionAvg: r.chance(0.2) ? r.int(28, 55) : null, ctr: r.chance(0.2) ? r.float(2.5, 11, 1) : null}; });
  const cmp = (factor, kind, text, options) => ({factor, verdict: {kind, text}, options: options.map(([option, videos_, withResult, score, retentionAvg, ctr]) => ({option, videos: videos_, withResult, score, retentionAvg, ctr}))});
  return {minVideos: 5, videos, comparisons: [
    cmp("Formato", "gana", "«caída y regreso» rinde un 46 % más que «historia» (con 14 y 31 vídeos).", [["caída y regreso", 18, 14, 1.9, 44.2, 6.8], ["caso-real", 26, 19, 1.4, 41, 6.1], ["historia", 40, 31, 1.3, 38.5, null]]),
    cmp("Búsqueda", "empate", "Por plano y por escenas rinden parecido (menos de un 25 % de diferencia).", [["por escenas", 22, 16, 1.2, null, null], ["por plano", 150, 121, 1.1, 39, 5.4]]),
    cmp("Duración", "gana", "De 8 a 12 minutos rinde un 38 % más que menos de 8.", [["8-12 min", 96, 80, 1.5, 42, 6], ["> 12 min", 41, 30, 1.2, 36, 5.2], ["< 8 min", 30, 22, 1.1, 47, 5.9]]),
    cmp("Ritmo", "falta", "Faltan vídeos con más de 13 cortes por minuto (hay 3 de 5).", [["10-13 cortes/min", 120, 96, 1.3, null, null], ["> 13 cortes/min", 4, 3, 1.7, null, null], ["< 10 cortes/min", 44, 30, 1.0, null, null]]),
    cmp("Etiqueta: miniatura con cara", "falta", "Solo 4 vídeos con la etiqueta tienen ya 7 días.", [["con la etiqueta", 6, 4, 2.2, null, 8.9], ["sin la etiqueta", 160, 130, 1.2, null, 5.6]]),
    cmp("Etiqueta: apertura con clip", "gana", "Con clip de apertura, un 31 % más.", [["con la etiqueta", 9, 7, 1.7, 45, null], ["sin la etiqueta", 157, 126, 1.3, 39, null]])]};
}

const tiempos = () => ({markdown: "# Dónde se va el tiempo\n\nMedia de los últimos 40 vídeos terminados: **1 h 12 min** de trabajo por vídeo.\n\n| Etapa | Media | % | Lo más lento |\n|---|---|---|---|\n| Buscar material | 15,8 min | 22 % | esperar turno del proxy |\n| Descargar en HD | 10,1 min | 14 % | 1080p por el proxy residencial |\n| Elegir (juez) | 8,6 min | 12 % | 212 veredictos por vídeo |\n| Render | 7,9 min | 11 % | CPU (sin NVENC en la VPS) |\n| Analizar clips | 6,5 min | 9 % | CLIP en CPU |\n\n- El 31 % del tiempo de «Buscar material» es **espera entre peticiones** (ritmo anti-bloqueo)\n- Con la búsqueda por escenas, «Buscar material» baja a _9,2 min_\n"});

const ytbench = () => ({job: IDLE(), result: {at: isoAt(NOW - 5 * DAY_MS), summary: [
  ["rainproxy-resi-es", "tv", 5, 5, 1.8, 6.4, 1.6, 4.9, 4.1, "https", true, ""], ["rainproxy-resi-es", "web", 5, 5, 2.4, 5.1, 2.0, 3.8, 5.3, "https", true, ""], ["casa-pc:8899", "tv", 5, 5, 1.1, 3.9, 2.6, 2.7, 7.4, "https", true, ""],
  ["rainproxy-resi-es", "ios", 3, 5, 3.9, 2.2, 4.5, null, null, "m3u8", false, "Sign in to confirm you’re not a bot (2 de 5)"], ["directo", "web", 0, 5, null, null, null, null, null, "", false, "Sign in to confirm you’re not a bot. Use --cookies-from-browser or --cookies for the authentication"]]
  .map(([way, client, ok, of, details_s, mbps360, piece360_s, mbps1080, piece1080_s, protocol, storyboard, error]) => ({way, client, ok, of, details_s, mbps360, piece360_s, mbps1080, piece1080_s, protocol, storyboard, error}))}});

const scenebench = (st) => { const refs = st.videos.filter((v) => v.status === "hecho" && !v.short).slice(0, 4).map((v) => v.slug);
  const side = (k) => ({shots: 174, searches: Math.round(522 * k), extracts: Math.round(1310 * k), shotsWithoutYouTube: k < 1 ? 9 : 6, optionsPerShot: k < 1 ? 5.1 : 6.3, differentSources: k < 1 ? 3.8 : 4.4, judgeChoiceKept: k < 1 ? 0.83 : 1, titleMatch: k < 1 ? 0.71 : 0.66,
    searchesWithoutData: k < 1 ? 4 : 0, extractsWithoutData: k < 1 ? 11 : 0, visualBest: k < 1 ? 0.29 : 0.3, visualAboveFloor: k < 1 ? 0.88 : 0.91, simulatedSources: k < 1 ? 41 : 47, simulatedRepeats: k < 1 ? 0.12 : 0.09, simulatedScore: 0.28, simulatedMargin: null});
  return {job: IDLE(), result: {at: isoAt(NOW - 9 * DAY_MS), scenes: 31, api: true, set: {old: side(1), new: side(0.34)},
    videos: refs.map((video, i) => ({video, scenes: 28 + i * 3, old: {searches: 160 + 11 * i, extracts: 420 + 30 * i, shots: 54 + i * 2}, new: {searches: 52 + 4 * i, extracts: 150 + 9 * i}}))}}; };

function scriptsNeeded(st, days, mine) {
  const listed = agendaVideos(st), per = {};
  for (const s of plan(st, days, listed)) {
    if (s.past || (mine && !mine.includes(s.channel))) continue;
    const e = per[s.channel] = per[s.channel] || {channel: s.channel, empty: [], noScript: [], slots: 0, ready: 0};
    e.slots++;
    if (!s.video) e.empty.push({date: s.date, time: s.time, deadline: s.deadline});
    else if (s.video.status === "falta guion") e.noScript.push({date: s.date, slug: s.video.slug});
    else e.ready++;
  }
  const full = stats(st, mine);
  return Object.values(per).sort((a, b) => (a.channel < b.channel ? -1 : 1)).map((e) => { const r = rng("scripts:" + e.channel);
    const winners = full.videos.filter((v) => v.channel === e.channel && v.youtube).sort((a, b) => b.youtube.views - a.youtube.views).slice(0, e.channel.length % 3 ? 3 : 0)
      .map((v, i) => ({slug: v.slug, title: v.youtube.title, views: v.youtube.views, vsChannel: i === 2 ? null : v.youtube.vsChannel, thumbnail: i === 1 ? "" : v.youtube.thumbnail, format: i ? "" : "caso-real"}));
    const ideas = [...st.agenda.ideas, ...st.savedIdeas].filter((i) => i.channel === e.channel).map((i) => ({id: i.id, title: i.title, note: i.note || i.angle || "", idea: i, channel: i.channel}));
    const extra = (SUBJECTS[e.channel] || []).slice(0, e.channel.length % 4).map((s, i) => ({id: `auto-${slugify(s)}`, title: fill(TEMPLATES[(i + e.channel.length) % 8], s), note: i % 2 ? "Del radar de ayer: 3 canales pequeños lo han subido con más de 200 mil visitas." : "", idea: {format: "caso-real"}, channel: e.channel}));
    return {channel: e.channel, missing: e.empty.length + e.noScript.length, ready: e.ready, slots: e.slots, empty: e.empty, noScript: e.noScript, winners, ideas: [...ideas, ...extra], _r: r.int(0, 1)}; });
}

function toUpload(st, mine) {
  const listed = agendaVideos(st), dates = uploadDates(st), out = [];
  for (const v of listed) {
    if (v.status !== "hecho" || (mine && !mine.includes(v.channel))) continue;
    const full = st.videos.find((x) => x.slug === v.slug), r = rng("upload:" + v.slug), s = sections(youtubeTxt(full));
    const titles = (s["TÍTULO"] || "").split("\n").map((t) => t.replace(/^\d+\.\s*/, "").trim()).filter(Boolean);
    delete s["TÍTULO"];
    const files = [{label: "Vídeo", path: "video-final.mp4", mb: full.short ? r.int(18, 60) : r.int(480, 1500)},
      ...[1, 2, 3].map((n) => ({label: `Miniatura ${n}`, path: `miniaturas/miniatura-${n}.jpg`, image: true})),
      ...(full.short ? [] : [1, 2, 3, 4, 5, 6, 7, 8].map((n) => ({label: `Fotograma ${n}`, path: `fotogramas/fotograma-${n}.jpg`, still: true}))),
      ...(r.chance(0.3) ? [{label: "Recorte del protagonista (PNG)", path: "fotogramas/recorte.png"}] : []), {label: "Subtítulos (es)", path: "subtitulos.es.srt"},
      ...(full.short ? [] : [1, 2, 3].map((n) => ({label: `Short ${n}`, path: `shorts/short-${n}.mp4`})))];
    const slot = dates[v.slug] || {};
    out.push({...v, minutes: full.minutes, titles, sections: s, files, date: slot.date || null, time: slot.time || null,
      shortsText: full.short ? "" : "SHORT 1\nEl error de 250 millones #shorts\n\nSHORT 2\n«Nadie quiso verlo» #historia\n\nSHORT 3\nLa carta que lo avisó todo"});
  }
  return out.sort((a, b) => (a.date || "9999").localeCompare(b.date || "9999") || (a.doneAt || 0) - (b.doneAt || 0));
}

function compilations(st) {
  const per = {};
  for (const v of st.videos) if (v.status === "hecho" && !v.archived && !v.short && !v.dubOf) (per[v.channel] = per[v.channel] || []).push(v.title || v.slug);
  return Object.entries(per).sort().filter(([, t]) => t.length >= 2).slice(0, 14).map(([channel, titles]) => ({channel, videos: titles.length, titles: titles.slice(0, 12)}));
}

function buildLibrary() {
  const r = rng(5150), entities = [];
  const people = Object.values(SUBJECTS).flat().filter((s) => /^[A-ZÁÉÍÓÚ][a-záéíóúñ]+ [A-ZÁÉÍÓÚČ«]/.test(s) && !/^(Brawn|Deep|Fórum|Imperio)/.test(s));
  const topics = Object.values(SUBJECTS).flat().filter((s) => /^(el|la|los|las) /.test(s)).slice(0, 44).map((s) => s.replace(/^(el|la|los|las) /, ""));
  for (const name of people) entities.push({key: slugify(name), name, kind: "person", cutout: r.chance(0.3), videos: r.int(1, 14), photos: r.int(0, 22), inVideos: r.int(1, 6)});
  for (const name of topics) entities.push({key: slugify(name), name: name[0].toUpperCase() + name.slice(1), kind: r.chance(0.5) ? "topic" : "place", cutout: false, videos: r.int(0, 11), photos: r.int(0, 15), inVideos: r.int(1, 4)});
  return entities.sort((a, b) => b.videos + b.photos - (a.videos + a.photos) || a.name.localeCompare(b.name));
}

function libraryEntity(st, key) {
  const e = st.library.find((x) => x.key === key);
  if (!e) return null;
  const r = rng("lib:" + key);
  const sources = Array.from({length: 14}, (_, i) => { const id = r.id(), kind = i % 4 === 3 ? "photos" : "videos";
    const clips = kind === "videos" && i % 3 !== 2 ? Array.from({length: 1 + (i % 4)}, (_, k) => ({file: `${SPECIAL.publicado}/clips/s${String(10 + i + k).padStart(3, "0")}.mp4`, text: r.pick(["El 1 de agosto de 1976, en la segunda vuelta de Nürburgring, su Ferrari se salió en la curva de Bergwerk", "Cuarenta y dos días después estaba otra vez en un coche", "Se retiró en mitad de una carrera, bajo la lluvia de Fuji"]), video: r.pick([SPECIAL.publicado, SPECIAL.hecho, "ayrton-senna"])})) : [];
    return {id, kind, title: i === 5 ? "" : `${e.name}: ${r.pick(["entrevista de 1984 (archivo RTVE)", "el accidente de Nürburgring, imágenes originales", "rueda de prensa completa", "documental de la BBC", "retrato en el paddock"])}`,
      channel: r.pick(["RTVE Archivo", "FORMULA 1", "British Pathé", "Wikimedia Commons", "AP Archive"]), url: kind === "videos" ? watch(id) : `https://commons.wikimedia.org/wiki/File:${id}.jpg`,
      used: r.int(0, 5), approved: r.int(0, 3), right: i % 5 === 0 ? r.int(1, 4) : 0, videos: i % 3 ? [SPECIAL.publicado, "ayrton-senna"].slice(0, 1 + (i % 2)) : [], clips, preview: i % 6 !== 4}; });
  return {key, name: e.name, kind: e.kind, sources};
}

function errorsSummary(st) {
  const r = rng(8086);
  const done = st.videos.filter((v) => v.hasVideo).slice(0, 38);
  const videos = done.map((v) => { const c = r.int(18, 58), i = r.int(0, 8), d = r.int(0, 5); return {slug: v.slug, correcta: c, incorrecta: i, dudosa: d, accuracy: r.chance(0.05) ? null : Math.round(100 * c / (c + i))}; });
  const total = {correcta: videos.reduce((a, v) => a + v.correcta, 0), incorrecta: videos.reduce((a, v) => a + v.incorrecta, 0), dudosa: videos.reduce((a, v) => a + v.dudosa, 0)};
  return {accuracy: Math.round(100 * total.correcta / (total.correcta + total.incorrecta)), total, videos,
    reasons: [["No tiene que ver con la frase", 61], ["Sale otra persona", 44], ["Texto encima o marca de agua", 31], ["Había una opción mejor", 22], ["Repetido", 12], ["Roto, negro o muy mala calidad", 9], ["Dibujo animado / videojuego", 6], ["Otro", 3]].map(([name, count]) => ({name, count})),
    methods: [["Juez (búsqueda del plano)", 1104, 74, 31, 94], ["Puntuación directa", 212, 38, 12, 85], ["Elegido a mano", 40, 1, 0, 98], ["Siguiente opción", 96, 31, 9, 76], ["Otro clip del protagonista", 71, 29, 14, 71], ["Relleno (stock)", 38, 21, 8, 64]]
      .map(([name, correcta, incorrecta, dudosa, accuracy]) => ({name, correcta, incorrecta, dudosa, accuracy})),
    tips: ["«Otro clip del protagonista» acierta solo el 71 %: se ha subido el mínimo de parecido de cara de 0,55 a 0,62.", "El 34 % de los fallos son «no tiene que ver con la frase» en planos de menos de 3 s: el juez ahora ve dos fotogramas más."]};
}

function search(st, q, mine) {
  const words = String(q || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").split(/[^a-z0-9]+/).filter((w) => w.length > 2);
  const whole = words.length >= 40;
  if (!words.length) return {query: q, results: []};
  const plain = (t) => String(t).toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
  let results = st.videos.filter((v) => !mine || mine.includes(v.channel)).map((v) => { const text = plain(`${v.slug.replace(/-/g, " ")} ${v.title}`);
    const hits = whole ? 0 : words.filter((w) => text.includes(w)).length; return [v, whole ? (hashOf(v.slug) % 100 < 3 ? 0.3 + (hashOf(v.slug) % 40) / 100 : 0) : hits / words.length]; })
    .filter(([, score]) => score >= (whole ? 0.25 : 0.6)).sort((a, b) => b[1] - a[1]).slice(0, 30)
    .map(([v, score]) => ({slug: v.slug, title: v.title, channel: v.channel, status: v.status, archived: v.archived, published: v.published, score: +score.toFixed(3),
      snippet: `Lo que pasó con ${v.title.split(":")[0]} empezó mucho antes: ${q.length < 60 ? "los " + q + " ya" : "todo"} estaba escrito en una carta de dos páginas que nadie contestó.`}));
  const ideas = whole || mine ? [] : [...st.agenda.ideas, ...st.savedIdeas].filter((i) => words.some((w) => plain(i.title + " " + (i.note || "")).includes(w))).slice(0, 10)
    .map((i) => ({title: i.title, channel: i.channel || "", where: i.id.startsWith("idea-") ? "idea guardada" : "tablero", note: (i.note || i.angle || "").slice(0, 200), score: 1}));
  return {query: q, whole, results, ideas};
}

// --- the whole state ------------------------------------------------------------------------------------------------
function buildState() {
  const st = {videos: buildVideos()};
  st.agenda = {schedule: buildSchedule(), lead_hours: 36, buffer: 2, morning_hour: 9, assigned: {}, ideas: []};
  const r = rng(1234);
  // pinned: two finished videos of «coches» to fixed days
  const coches = st.videos.filter((v) => v.channel === "coches" && v.status === "hecho" && !v.published && !v.archived && v.slug !== SPECIAL.hecho);
  if (coches[0]) st.agenda.assigned[coches[0].slug] = day(3);
  if (coches[1]) st.agenda.assigned[coches[1].slug] = day(8);
  st.agenda.ideas = Array.from({length: 18}, (_, i) => { const c = i < 6 ? PARTNERS.marc[i % 5] : i === 9 ? "" : r.pick(BASE_CHANNELS), subject = r.pick(SUBJECTS[c || "historia-rara"]);
    return {id: "b" + r.id(7), title: i === 3 ? "Los dingos y la valla más larga del mundo" : fill(TEMPLATES[i % 8], subject), channel: c, note: i % 3 ? "Ángulo: la persona que avisó. Gancho: una cifra en los primeros 5 segundos. Fuentes: hemeroteca y un documental de la época." : "",
      date: i % 4 === 0 ? day(2 + i) : "", ...(i % 6 === 1 ? {escenas: "Escena 1 · bloque 1 · ~30 s · tráfico denso\nQué se ve: una rotonda saturada", hook: "¿Y si la rotonda fuera el problema?"} : {})}; });
  const radar = buildRadar();
  st.radar = radar; st.savedIdeas = radar.saved;
  Object.assign(st, buildVoices());
  st.library = buildLibrary();
  if (!st.library.some((e) => e.key === SLUGS.library)) st.library.unshift({key: SLUGS.library, name: "Niki Lauda", kind: "person", cutout: true, videos: 9, photos: 14, inVideos: 4});
  st.settings = {daily_usd: 20, per_video_usd: 1.5, proxy_gb_per_day: 8, server_usd_month: 48, paused: false,
    channel_priority: ["coches", "gimnasia", "aviones", "historia-rara"],
    my_channels: Object.fromEntries(CHANNELS.filter((c, i) => i % 3 !== 2 || PARTNERS.marc.includes(c)).map((c) => [c, "@" + c.split("-").map((w) => w[0].toUpperCase() + w.slice(1)).join("") + "Docu"]))};
  st.users = [{name: "laia", channels: PARTNERS.laia, created: day(-80), telegram: false, limits: {daily_usd: 3, proxy_gb_per_day: 0}},
    {name: "marc", channels: PARTNERS.marc, created: day(-41), telegram: true, limits: {daily_usd: 5, proxy_gb_per_day: 2}}];
  st.reviews = {}; st.decisions = {}; st.experiments = {};
  return st;
}

function overview(st, who) {
  const mine = who ? PARTNERS[who] : null;
  const service = {watching: true, paused: st.settings.paused, queueRunning: true, youtubeBlocked: null, lastBeat: isoAt(NOW - 40000).replace("T", " "),
    code: {id: "a3f9c1e", at: isoAt(NOW - 26 * 3600000) + "+01:00", what: "Calendario: los canales doblados salen con su original"}};
  if (mine) return {service: {...service, lastBeat: null, code: null}, budget: {today: 1.37, limit: 0, proxyGbToday: null, proxyGbLimit: 0}, videos: st.videos.filter((v) => mine.includes(v.channel)).map(pub),
    channels: CHANNELS.filter((c) => mine.includes(c)), channelKinds: Object.fromEntries(mine.map((c) => [c, KINDS[c]])), formats: FORMATS, youtube: null, partner: who};
  const errors = {bot: 1384, 403: 421, 429: 64, timeout: 321, other: 190};
  return {service, budget: {today: 7.42, limit: st.settings.daily_usd, proxyGbToday: 3.18, proxyGbLimit: st.settings.proxy_gb_per_day},
    videos: st.videos.map(pub), channels: CHANNELS, channelKinds: KINDS, formats: FORMATS,
    youtube: {requests: 20560, ok: 18221, failed: 2339, errors, files: 2210, files_ok: 2034, megabytes: 61840, mbps: 4.7, with_cookies: 0, pot: true, clients: ["tv", "web", "ios"], answer_avg: 2.3, wait_avg: 6.1, proxy_gb: 27.4, sessions: 412,
      byProxy: [{proxy: "rainproxy-resi-es", requests: 2811, ok: 2504, failed: 307, errors: {bot: 188, 403: 61, timeout: 58}, files: 318, files_ok: 296, mbps: 4.4, seconds_per_file: 7.9, proxy_gb: 3.18},
        {proxy: "casa-pc:8899", requests: 402, ok: 377, failed: 25, errors: {timeout: 25}, files: 61, files_ok: 58, mbps: 2.9, seconds_per_file: 11.2, proxy_gb: 0},
        {proxy: "(directo)", requests: 12, ok: 0, failed: 12, errors: {bot: 12}, files: 0, files_ok: 0, mbps: 0, seconds_per_file: 0, proxy_gb: 0}]}};
}
const pub = (v) => { const {dubOf, ...rest} = v; return rest; };

module.exports = {ORDER, NOW, TODAY, day, isoAt, rng, hashOf, CHANNELS, KINDS, FORMATS, PARTNERS, DUBBED, SUBJECTS, TEMPLATES, fill, SLUGS, SPECIAL, WEEKDAYS, IDLE, thumb, watch,
  buildState, overview, agendaVideos, plan, reserve, uploadDates, board, videoDetail, porque, repeticion, review, decisions, myChannel, stats, gasto, proxyReport, servidor, doctor,
  voicesAnswer, piloto, experimentos, tiempos, ytbench, scenebench, scriptsNeeded, toUpload, compilations, libraryEntity, errorsSummary, search};
