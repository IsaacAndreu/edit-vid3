// Mock of the Estudio server's /api/* (and its images/media), for Playwright.
//
//   const mock = require("./mock");
//   const handle = await mock.install(page, {partner: false});     // page.route on everything
//   handle.unmocked / handle.denied / handle.blocked / handle.state
//
// `answer(state, method, url, body, who)` is the transport-free core (weight.js drives it through CDP Fetch so the
// browser's HTTP cache stays on; page.route would switch it off).
"use strict";

const D = require("./mock-data");
const {SLUGS, PARTNERS, CHANNELS, KINDS, IDLE} = D;

const unmocked = [];          // every /api path nobody modelled: {method, path} (shared by all pages of the process)
const denied = [];            // 403s a partner got (as the real server would answer)
const blocked = [];           // external requests aborted

let pristine = null;
function freshState() { if (!pristine) pristine = D.buildState(); return structuredClone(pristine); }

// --- placeholders ---------------------------------------------------------------------------------------------------
function placeholder(url, square = false) {
  const h = D.hashOf(url.replace(/[?#].*$/, "")) % 360, w = square ? 176 : 1280, ht = square ? 176 : 720;
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${ht}" viewBox="0 0 ${w} ${ht}"><rect width="${w}" height="${ht}" fill="hsl(${h} 32% 34%)"/>` +
    `<path d="M0 ${ht} L${w * 0.3} ${ht * 0.45} L${w * 0.5} ${ht * 0.7} L${w * 0.72} ${ht * 0.3} L${w} ${ht} Z" fill="hsl(${h} 34% 22%)"/>` +
    `<circle cx="${w * 0.82}" cy="${ht * 0.24}" r="${ht * 0.1}" fill="hsl(${(h + 40) % 360} 65% 72%)"/></svg>`;
}
const IMAGE = /\.(jpe?g|png|webp|gif|avif)$/i, MEDIA = /\.(mp4|webm|mov|mp3|m4a|wav|ogg)$/i;
const image = (url) => ({status: 200, contentType: "image/svg+xml", body: placeholder(url, /ggpht|googleusercontent/.test(url))});
const media = () => ({status: 204, contentType: "application/octet-stream", body: ""});

// --- who may see what (pipeline/web.py: PARTNER_GET, PARTNER_POST, PARTNER_VIDEO_*) ---------------------------------
const PARTNER_GET = ["/api/overview", "/api/gasto", "/api/search", "/api/upload", "/api/upload/dates", "/api/factura.csv", "/api/voices", "/api/voices/search",
  "/api/cuenta", "/api/agenda", "/api/scripts", "/api/board", "/api/radar", "/api/stats", "/api/spending", "/api/canales"];
const PARTNER_POST = ["/api/videos", "/api/search", "/api/apertura", "/api/apertura/subir", "/api/hook", "/api/scenes", "/api/voices", "/api/voices/test", "/api/channels",
  "/api/telegram/link", "/api/telegram/unlink", "/api/agenda", "/api/scripts/draft", "/api/scripts/similar", "/api/board/idea", "/api/board/temas", "/api/ideas", "/api/ideas/save"];
const PARTNER_VIDEO_GET = [/^\/api\/video\/([^/]+)$/, /^\/api\/video\/([^/]+)\/(?:repeticion|porque|capcut|exportar|voz\.mp3)$/, /^\/api\/review\/([^/]+)$/,
  /^\/api\/review\/([^/]+)\/frame\/[A-Za-z0-9_-]+\.jpg$/, /^\/api\/decisions\/([^/]+)$/, /^\/api\/decisions\/([^/]+)\/frame$/, /^\/files\/([^/]+)\/.+$/];
const PARTNER_VIDEO_POST = [/^\/api\/video\/([^/]+)\/(?:voz|retencion|doblaje|retry|archive|hold|unhold|stop|redo|for-claude|porque|published|channel|fix|capcut|exportar)$/,
  /^\/api\/review\/([^/]+)\/[A-Za-z0-9_-]+$/, /^\/api\/decisions\/([^/]+)\/[A-Za-z0-9_-]+$/];
function partnerMay(st, mine, method, path) {
  if ((method === "GET" ? PARTNER_GET : PARTNER_POST).includes(path)) return true;
  let m = path.match(/^\/api\/mychannel\/([^/]+)(?:\/handle)?$/);
  if (m) return mine.includes(decodeURIComponent(m[1]));
  if (method === "GET" && /^\/api\/apertura\/[0-9a-f]{12}$/.test(path)) return true;
  if (["/api/password", "/api/logout", "/api/login", "/api/session"].includes(path)) return true;
  for (const pattern of method === "GET" ? PARTNER_VIDEO_GET : PARTNER_VIDEO_POST)
    if ((m = path.match(pattern))) return mine.includes((st.videos.find((v) => v.slug === decodeURIComponent(m[1])) || {}).channel);
  return false;
}

// --- GET ------------------------------------------------------------------------------------------------------------
function agendaAnswer(st, mine) {
  let listed = D.agendaVideos(st);
  let cfg = st.agenda;
  if (mine) {
    listed = listed.filter((v) => mine.includes(v.channel));
    cfg = {...cfg, schedule: Object.fromEntries(Object.entries(cfg.schedule).filter(([c]) => mine.includes(c))),
      assigned: Object.fromEntries(Object.entries(cfg.assigned).filter(([k]) => listed.some((v) => v.slug === k))), ideas: cfg.ideas.filter((i) => mine.includes(i.channel))};
  }
  const plan = D.plan(st, 28, listed).filter((s) => !mine || mine.includes(s.channel));
  const reserve = Object.fromEntries(Object.entries(D.reserve(st, listed)).filter(([c]) => !mine || mine.includes(c)));
  return {settings: cfg, weekdays: D.WEEKDAYS, plan, reserve, videos: listed};
}

// «Canales» (web.channels_health): the same fields, from the same mock agenda and stats
function canalesAnswer(st, mine) {
  const listed = D.agendaVideos(st), cfg = st.agenda, plan = D.plan(st, 14, listed), reserve = D.reserve(st, listed);
  const stats = D.stats(st, mine), today = D.day(0), DAY = 864e5;
  const weekStart = (i) => new Date(Date.parse(today + "T12:00:00Z") - 7 * (8 - i) * DAY);
  const channels = CHANNELS.filter((c) => !mine || mine.includes(c)).map((name) => {
    const rule = cfg.schedule[name] || {enabled: false, days: [], time: ""};
    const vids = listed.filter((v) => v.channel === name);
    const next = Array.from({length: 14}, (_, n) => { const date = D.day(n), s = plan.find((x) => x.channel === name && x.date === date);
      return {date, kind: !s ? null : s.late ? "late" : s.ok ? "ok" : s.gap ? "gap" : "work", video: s && s.video ? s.video.slug : null}; });
    const weeks = Array(8).fill(0);
    for (const row of stats.videos) {
      if (row.channel !== name || !row.youtube || !row.publishedDay) continue;
      const t = Date.parse(row.publishedDay + "T12:00:00Z");
      for (let i = 1; i <= 8; i++) { const a = weekStart(i).getTime(); if (t >= a && t < a + 7 * DAY) weeks[i - 1] += row.youtube.views || 0; }
    }
    const before = weeks.slice(0, 4).reduce((a, b) => a + b, 0), after = weeks.slice(4).reduce((a, b) => a + b, 0);
    const c = stats.channels.find((x) => x.channel === name) || {};
    return {channel: name, kind: KINDS[name] || "metraje", publishes: !!rule.enabled, days: rule.days || [], time: rule.time || "",
      reserve: reserve[name] ?? null, buffer: cfg.buffer, making: vids.filter((v) => v.status === "haciendo").length, queued: vids.filter((v) => v.status === "en cola").length,
      missing: vids.filter((v) => v.status === "falta guion" || v.status === "falta voz").length, errors: vids.filter((v) => v.status === "error").length,
      next, gaps: next.filter((d) => d.kind === "gap" || d.kind === "late").length, late: next.filter((d) => d.kind === "late").length,
      views: c.views || 0, median: c.median ?? null, published: c.published || 0, weeks, trend: before ? +((after - before) / before).toFixed(2) : null};
  });
  return {channels, weekdays: D.WEEKDAYS, buffer: cfg.buffer, today};
}

function settingsAnswer(st) {
  const s = st.settings;
  return {daily_usd: s.daily_usd, per_video_usd: s.per_video_usd, proxy_gb_per_day: s.proxy_gb_per_day, server_usd_month: s.server_usd_month, paused: s.paused,
    channels: CHANNELS, myChannels: s.my_channels, channel_priority: s.channel_priority, proxy_gb: 100, proxy_since: D.day(-34)};
}

function radarAnswer(st, mine) {
  const r = st.radar, state = {...r, saved: st.savedIdeas};
  if (!mine) return state;
  const only = (o) => Object.fromEntries(Object.entries(o || {}).filter(([k]) => mine.includes(k)));
  return {...state, latest: {...r.latest, channels: only(r.latest.channels), rising: [], gaps: [], niches: []}, niches: [], gaps: [],
    news: {...r.news, channels: only(r.news.channels), comebacks: only(r.news.comebacks), errors: []}, channels: mine, saved: st.savedIdeas.filter((i) => mine.includes(i.channel)), partner: true};
}

function get(st, path, query, who) {
  const mine = who ? PARTNERS[who] : null;
  let m;
  if (path === "/api/session") return {authorised: true, needsPassword: !!who, partner: who || null, channels: who ? mine : null};
  if (path === "/api/overview") return D.overview(st, who);
  if (path === "/api/upload/dates") { const dates = D.uploadDates(st); return mine ? Object.fromEntries(Object.entries(dates).filter(([k]) => mine.includes((st.videos.find((v) => v.slug === k) || {}).channel))) : dates; }
  if (path === "/api/upload") return mine ? {videos: D.toUpload(st, mine), compilations: [], compilationJob: null} : {videos: D.toUpload(st), compilations: D.compilations(st), compilationJob: IDLE()};
  if (path === "/api/agenda") return agendaAnswer(st, mine);
  if (path === "/api/canales") return canalesAnswer(st, mine);
  if (path === "/api/scripts") { const days = parseInt(query.get("days") || "14", 10); return {channels: D.scriptsNeeded(st, days, mine).map(({_r, ...e}) => e), days}; }
  if (path === "/api/board") { const columns = D.board(st); return mine ? {columns: Object.fromEntries(Object.entries(columns).map(([k, items]) => [k, items.filter((x) => mine.includes(x.channel))])), channels: mine, kinds: Object.fromEntries(mine.map((c) => [c, KINDS[c]]))}
    : {columns, channels: CHANNELS, kinds: KINDS}; }
  if (path === "/api/radar") return radarAnswer(st, mine);
  if (path === "/api/stats") return D.stats(st, mine);
  if (path === "/api/spending") { const r = D.rng("spending" + (who || "")); return Array.from({length: 14}, (_, i) => ({day: D.day(i - 13), usd: +(r.float(1.5, 14) * (who ? 0.18 : 1)).toFixed(2)})); }
  if (path === "/api/gasto") return D.gasto(st, mine, who);
  if (path === "/api/voices") return D.voicesAnswer(st, mine, who);
  if (path === "/api/voices/credits") return [{amount: 412800, type: "monthly"}, {amount: 96000, type: "extra"}];
  if (path === "/api/voices/search") return ["Dani – narrador documental", "Lucía – noticias", "Martín – cercano", "Hugo – deportes", "Carmen – cálida", "Álvaro – grave"].map((name, i) => ({voice_id: D.rng("voice" + i).id(20), name,
    gender: i % 2 ? "female" : "male", age: i % 3 ? "middle_aged" : "young", accent: i % 2 ? "peninsular" : "latin american", language: query.get("language") || "es", descriptive: ["calm", "confident", "warm"][i % 3],
    use_case: "narrative_story", category: "professional", preview_url: `https://storage.googleapis.com/eleven-public-prod/premade/voices/v${i}/preview.mp3`, description: ""}));
  if (path === "/api/cuenta") { const u = st.users.find((x) => x.name === who) || st.users[1]; return {name: u.name, channels: u.channels, telegram: u.telegram, limits: u.limits, spentToday: 1.37, proxyGbToday: 0.84}; }
  if (path === "/api/search") return D.search(st, query.get("q") || "", mine);
  if (path === "/api/users") return {users: st.users};
  if (path === "/api/doctor") return D.doctor();
  if (path === "/api/servidor") return D.servidor(st);
  if (path === "/api/proxy") return D.proxyReport(parseFloat(query.get("days") || "7"));
  if (path === "/api/experimentos") { const e = D.experimentos(st); for (const v of e.videos) Object.assign(v, st.experiments[v.slug] || {}); return e; }
  if (path === "/api/settings") return settingsAnswer(st);
  if (path === "/api/notify") return {telegram: true, token: true, email: false, studioUrl: "https://203-0-113-7.sslip.io"};
  if (path === "/api/library") return {entities: st.library};
  if ((m = path.match(/^\/api\/library\/([a-z0-9-]+)$/))) return D.libraryEntity(st, m[1]) || {__status: 404, error: "No existe"};
  if (path === "/api/piloto") return D.piloto(st);
  if (path === "/api/tiempos") return D.tiempos();
  if (path === "/api/scenebench") return D.scenebench(st);
  if (path === "/api/ytbench") return D.ytbench();
  if (path === "/api/errors") return D.errorsSummary(st);
  if ((m = path.match(/^\/api\/mychannel\/([^/]+)$/))) { const c = decodeURIComponent(m[1]); if (!CHANNELS.includes(c)) return {__status: 404, error: "No existe"};
    const full = D.myChannel(c); if (!st.settings.my_channels[c]) return {report: null, handle: "", job: IDLE()}; return {...full, handle: st.settings.my_channels[c]}; }
  if ((m = path.match(/^\/api\/apertura\/([0-9a-f]{12})$/))) { const id = D.rng("ap" + m[1]).id(); return {job: IDLE(), result: {maxSeconds: 30, plan: {about: "la presentación del coche en el Salón de París", speaker: "André Citroën", role: "fundador"},
    candidates: [{id, title: "Salon de l'Auto 1955 (INA)", channel: "INA Officiel", url: D.watch(id), start: 74.5, end: 92, why: "Se ve el momento exacto en que se descubre el coche; audio original en francés.",
      lines: [{from: 74.5, to: 79, text: "Señoras y señores, he aquí el futuro.", original: "Mesdames et messieurs, voici l'avenir."}, {from: 79, to: 85.5, text: "Doce mil pedidos en un solo día.", original: "Douze mille commandes en une seule journée."}]}]}}; }
  if ((m = path.match(/^\/api\/video\/([^/]+)$/))) return D.videoDetail(st, decodeURIComponent(m[1])) || {__status: 404, error: "No existe"};
  if ((m = path.match(/^\/api\/video\/([^/]+)\/(repeticion|porque|capcut|exportar|pilot)$/))) {
    const slug = decodeURIComponent(m[1]), v = st.videos.find((x) => x.slug === slug);
    if (!v) return {__status: 404, error: "No existe"};
    if (m[2] === "repeticion") return D.repeticion(slug);
    if (m[2] === "porque") return D.porque(st, slug);
    if (m[2] === "exportar") return {job: IDLE(), zip: slug === SLUGS.hecho ? `${slug}-premiere.zip` : null, mb: slug === SLUGS.hecho ? 412 : null};
    if (m[2] === "capcut") return {job: IDLE(), zip: slug === SLUGS.hecho ? `${slug}-capcut.zip` : null, mb: slug === SLUGS.hecho ? 688 : null};
    const refs = st.videos.filter((x) => x.status === "hecho" && !x.archived && !x.short && x.slug !== slug).slice(0, 30).map((x) => x.slug);
    if (slug === SLUGS.hecho) return {pilot: {reference: SLUGS.publicado, at: D.isoAt(D.NOW - 4 * 86400000)}, others: [], references: refs, report: pilotReport(slug)};
    return {pilot: null, others: [], references: refs, report: null};
  }
  if ((m = path.match(/^\/api\/review\/([^/]+)$/))) { const slug = decodeURIComponent(m[1]); st.reviews[slug] = st.reviews[slug] || D.review(st, slug); return st.reviews[slug]; }
  if ((m = path.match(/^\/api\/decisions\/([^/]+)$/))) { const slug = decodeURIComponent(m[1]); st.decisions[slug] = st.decisions[slug] || D.decisions(st, slug); return st.decisions[slug]; }
  return undefined;
}

function pilotReport(slug) {
  return {pilot: {video: slug}, reference: {video: SLUGS.publicado}, rows: [
    {label: "Búsquedas en YouTube", reference: 61, pilot: 22, better: true}, {label: "Extracciones (detalles)", reference: 148, pilot: 57, better: true}, {label: "«No eres un bot»", reference: 9, pilot: 2, better: true},
    {label: "Planos sin vídeo de YouTube", reference: 4, pilot: 6, better: false}, {label: "Fuentes distintas en pantalla", reference: 23, pilot: 21, better: null}, {label: "Clips marcados correctos", reference: 0.91, pilot: 0.88, better: false},
    {label: "Minutos de trabajo", reference: 74, pilot: 51, better: true}, {label: "Coste de API ($)", reference: 1.12, pilot: 1.04, better: true}, {label: "Visitas a 7 días", reference: 18400, pilot: null, better: null}],
    pending: ["Aún no tiene 7 días publicado: las visitas se comparan cuando los tenga.", "Marca sus clips en «Revisar clips» para comparar el acierto."]};
}

// --- POST -----------------------------------------------------------------------------------------------------------
const IDEAS = (seed) => { const r = D.rng(JSON.stringify(seed || {})); const subject = seed && (seed.name || seed.title || seed.query) || "el tema";
  return {evidence: [1, 2, 3, 4, 5].map((n) => ({title: `${subject}: caso ${n}`})), ideas: [0, 1, 2, 3].map((i) => ({id: "gen-" + r.id(8), title: D.fill(D.TEMPLATES[i], String(subject)), format: i % 2 ? "caso-real" : "historia", protagonist: i % 2 ? "Un ingeniero de 29 años" : "",
    angle: "Contado desde quien avisó del problema y no fue escuchado.", hook: "Una carta de dos páginas pudo evitarlo.", outline: ["La promesa", "La grieta", "El día clave", "Lo que quedó"], footage: "Archivo de prensa, noticiarios de la época, fotos de fábrica.",
    why: "Tres vídeos parecidos multiplican por 8 las visitas normales de sus canales.", research: "La cifra de pedidos y la fecha exacta de la quiebra."}))}; };

function post(st, path, body, who) {
  const mine = who ? PARTNERS[who] : null;
  let m;
  const ok = (message) => ({ok: true, ...(message ? {message} : {})});
  if (path === "/api/login" || path === "/api/logout" || path === "/api/password") return ok();
  if (path === "/api/search") return D.search(st, body.q || "", mine);
  if (path === "/api/agenda") {
    const a = st.agenda;
    if (body.channel && a.schedule[body.channel]) { const e = a.schedule[body.channel]; if ("days" in body) e.days = [...new Set(body.days.map(Number))].sort(); if ("time" in body) e.time = String(body.time); if ("enabled" in body) e.enabled = !!body.enabled; }
    for (const k of ["lead_hours", "buffer", "morning_hour"]) if (k in body) a[k] = Number(body[k]);
    if (body.assign) { if (body.date) a.assigned[body.assign] = String(body.date); else delete a.assigned[body.assign]; }
    return a;
  }
  if (path === "/api/settings") {
    const s = st.settings;
    for (const k of ["daily_usd", "per_video_usd", "proxy_gb_per_day", "server_usd_month"]) if (k in body) s[k] = Math.max(0, Number(body[k]) || 0);
    if (body.my_channels) for (const [k, v] of Object.entries(body.my_channels)) { if (String(v).trim()) s.my_channels[k] = String(v).trim(); else delete s.my_channels[k]; }
    if (Array.isArray(body.channel_priority)) s.channel_priority = [...new Set(body.channel_priority)].filter((c) => CHANNELS.includes(c));
    if ("paused" in body) s.paused = !!body.paused;
    return settingsAnswer(st);
  }
  if (path === "/api/users") {
    if (body.remove) st.users = st.users.filter((u) => u.name !== body.remove);
    else { let u = st.users.find((x) => x.name === body.name); if (!u) { u = {name: body.name, channels: [], created: D.TODAY, telegram: false, limits: {daily_usd: 0, proxy_gb_per_day: 0}}; st.users.push(u); }
      u.channels = body.channels || u.channels; if (body.limits) u.limits = body.limits; }
    return {users: st.users};
  }
  if (path === "/api/videos") return {ok: true, slug: body.name || "video-nuevo"};
  if (path === "/api/channels") return {ok: true, channel: body.name || "canal-nuevo"};
  if (path === "/api/niche-channel") return {ok: true, channel: body.name || "nicho", competitors: ["@ArchivoSecreto", "@MinutoHistorico"]};
  if (path === "/api/apertura") return {token: "0123456789ab"};
  if (path === "/api/apertura/subir") return {file: "apertura-subida-01.mp4"};
  if (path === "/api/hook") return {ok: false, verdict: "🟡 El gancho promete, pero tarda 38 s en cumplir", promise: "Explicar por qué desapareció.", rules: [{rule: "Cumple la promesa antes de 15 s", ok: false, detail: "llega a los 38 s"}, {rule: "Empieza con un hecho concreto", ok: true, detail: ""}],
    payoffSentence: "La empresa cerró un martes.", payoffSeconds: 38, strongestSentence: "Costaba 1.400 dólares más de lo que se cobraba.", strongestSeconds: 141, problems: ["La primera frase presenta el canal."], newOpening: "Cada coche que salía de la fábrica les costaba 1.400 dólares. Y vendieron nueve mil.",
    scriptWithOpening: "", tips: ["Lleva la cifra al principio."], topicFit: "bien", topicWhy: "Nombre propio y caída: lo que mejor rinde en el canal.", lengthNote: "Dentro de lo que mejor retiene (9-13).", minutes: 11, titles: ["El coche que perdía 1.400 dólares por unidad"]};
  if (path === "/api/scenes") return {coverage: 82, verdict: "🟡 El 82 % del guion se puede enseñar", warnings: ["2 bloques hablan de cifras que ningún mundo sabe dibujar"], escenas: "Escena 1 · bloque 1 · ~30 s · tráfico\nQué se ve: una rotonda saturada",
    blocks: [{n: 1, fit: "bien", world: "tráfico", scene: "rotonda saturada", seconds: 30, text: "Cada mañana, cuarenta mil coches intentan cruzar la misma rotonda y casi ninguno lo consigue a la primera", why: ""},
      {n: 2, fit: "no", world: "", scene: "", seconds: 22, text: "El ayuntamiento gastó doce millones en un estudio que nadie leyó", why: "no hay mundo para presupuestos"}]};
  if (path === "/api/ideas") return IDEAS(body.seed);
  if (path === "/api/ideas/save") { if (body.remove) st.savedIdeas = st.savedIdeas.filter((i) => i.id !== body.remove); else if (body.idea) st.savedIdeas.push({...body.idea, channel: body.channel || ""}); return ok(); }
  if (path === "/api/scripts/draft") return {title: (body.idea || {}).title || "Borrador", format: (body.idea || {}).format || "caso-real", words: 1480, check: 2,
    script: "## Capítulo 1\nEn 1974 nadie dudaba. [COMPROBAR: tres mil pedidos]\n\n## Capítulo 2\nLa carta llegó un martes.\n\n## Capítulo 3\nEl teléfono sonó a las 6:40. [COMPROBAR: la hora]\n"};
  if (path === "/api/scripts/similar") { const v = st.videos.find((x) => x.slug === body.slug) || {title: body.slug, channel: "coches"};
    return {title: v.title, ideas: (D.SUBJECTS[v.channel] || D.SUBJECTS["coches"]).slice(0, 4).map((s, i) => ({title: D.fill(D.TEMPLATES[i + 1], s), note: "Mismo patrón: nombre propio + caída + cifra.", format: "caso-real"}))}; }
  if (path === "/api/board/idea") { if (body.delete) { st.agenda.ideas = st.agenda.ideas.filter((i) => i.id !== body.delete); st.savedIdeas = st.savedIdeas.filter((i) => i.id !== body.delete); }
    else if (body.title) st.agenda.ideas.push({id: "b" + st.agenda.ideas.length + "n", title: body.title, channel: body.channel || "", note: body.note || "", date: body.date || ""}); return ok(); }
  if (path === "/api/board/temas") return {added: []};
  if (path === "/api/notify") return ok();
  if (path === "/api/update") return {ok: true, changed: false, message: "Ya estaba al día: Calendario: los canales doblados salen con su original"};
  if (path === "/api/restart-queue") return ok("Cola reiniciada. Si estaba haciendo un vídeo, sigue desde la última etapa terminada.");
  if (path === "/api/youtube/retry") return {ok: true, removed: [], message: "Listo: YouTube se vuelve a intentar ya."};
  if (path === "/api/queue") return ok("La cola ya está en marcha.");
  if (path === "/api/queue/retry-all") { for (const v of st.videos) if (v.status === "error") { v.status = "en cola"; v.lastError = v.error; v.error = null; } return ok("Todos los fallidos vuelven a la cola."); }
  if (["/api/ytbench", "/api/scenebench", "/api/radar", "/api/news", "/api/copia", "/api/compilations", "/api/dubbing", "/api/telegram/unlink"].includes(path)) return ok();
  if (path === "/api/radar/gap") return ok();
  if (path === "/api/telegram/link") return {code: "K7Q2ZP", url: ""};
  if (path === "/api/voices") { if (body.channel) { if (body.voice_id) st.voices[body.channel] = {voice_id: body.voice_id, name: body.name || "", model_id: body.model_id, speed: +body.speed || 1, stability: +body.stability || 0.5, similarity: +body.similarity || 0.75}; else delete st.voices[body.channel]; } return ok(); }
  if (path === "/api/voices/test") return {url: "/files/_pruebas/voz-prueba.mp3"};
  if ((m = path.match(/^\/api\/mychannel\/([^/]+)\/handle$/))) { st.settings.my_channels[decodeURIComponent(m[1])] = body.handle || ""; return ok(); }
  if ((m = path.match(/^\/api\/mychannel\/([^/]+)$/))) return ok();
  if ((m = path.match(/^\/api\/piloto\/([\w-]+)(?:\/(hacer|saltar))?$/))) return ok();
  if ((m = path.match(/^\/api\/experimentos\/([^/]+)$/))) { const slug = decodeURIComponent(m[1]), e = st.experiments[slug] = st.experiments[slug] || {};
    for (const [k, v] of Object.entries(body)) e[k] = k === "tags" ? String(v).split(",").map((t) => t.trim()).filter(Boolean) : v === "" ? null : Number(String(v).replace(",", ".")); return ok(); }
  if ((m = path.match(/^\/api\/library\/([a-z0-9-]+)\/remove$/))) { if (!body.id) st.library = st.library.filter((e) => e.key !== m[1]); return ok(); }
  if ((m = path.match(/^\/api\/review\/([^/]+)\/([A-Za-z0-9_-]+)$/))) { const rv = st.reviews[decodeURIComponent(m[1])], sh = rv && rv.shots.find((x) => x.id === m[2]);
    if (sh) sh.label = body.verdict ? {verdict: body.verdict, reason: body.reason || ""} : null; return ok(); }
  if ((m = path.match(/^\/api\/decisions\/([^/]+)\/apply$/))) return ok("En la cola: se rehará con tus elecciones.");
  if ((m = path.match(/^\/api\/decisions\/([^/]+)\/([A-Za-z0-9_-]+)$/))) { const d = st.decisions[decodeURIComponent(m[1])], it = d && d.items.find((x) => x.shot === m[2]);
    if (it) { if (body.ok) { it.verdict = "correcta"; it.pick = null; } else if (body.pick) { it.pick = body.pick; it.verdict = null; } } return ok(); }
  if ((m = path.match(/^\/api\/video\/([^/]+)\/([a-z-]+)$/))) {
    const slug = decodeURIComponent(m[1]), what = m[2], v = st.videos.find((x) => x.slug === slug);
    if (!v) return {__status: 404, error: "No existe"};
    if (what === "retry") { if (v.status !== "hecho") { v.lastError = null; v.error = null; v.retryAt = null; v.status = "en cola"; } return ok("En la cola: el vigilante lo coge en su próximo turno."); }
    if (what === "hold") { v.status = "en pausa"; v.error = v.lastError = null; return ok(); }
    if (what === "unhold") { v.status = "en cola"; return ok(); }
    if (what === "stop") { v.status = "en pausa"; v.stage = null; return ok("Parado: lo ya hecho se guarda."); }
    if (what === "archive") { v.archived = true; return ok(); }
    if (what === "redo") { v.status = "en cola"; return ok("En la cola: se rehará en su turno."); }
    if (what === "published") { v.published = body.value === false ? null : {at: D.isoAt(Date.now()), ...(body.url ? {url: body.url} : {})}; return ok(); }
    if (what === "channel") { if (CHANNELS.includes(body.channel)) v.channel = body.channel; return ok(); }
    if (what === "for-claude") return {text: `VÍDEO ${slug} · ${v.channel} · estado: ${v.status} · ${v.costUsd} $ · ${v.minutes} min\n\nERROR: ${v.error || v.lastError || "—"}\n\nÚLTIMAS LÍNEAS DEL REGISTRO:\n…`};
    if (what === "pilot") return body.report ? pilotReport(slug) : {ok: true, reference: body.reference || null};
    if (["voz", "retencion", "doblaje", "porque", "fix", "capcut", "exportar"].includes(what)) return ok();
  }
  return undefined;
}

// --- the transport-free core ----------------------------------------------------------------------------------------
// → {status, contentType, body} for anything of the app's origin the mock answers, or null (let the real server do it)
function answer(st, method, url, body, who) {
  const u = new URL(url), path = u.pathname;
  const json = (data, status = 200) => ({status, contentType: "application/json; charset=utf-8", body: JSON.stringify(data)});
  if (path.startsWith("/api/") || path.startsWith("/files/")) {
    if (who && !partnerMay(st, PARTNERS[who], method, path)) { denied.push({method, path, who}); return json({error: "No disponible"}, 403); }
    if (path.startsWith("/files/")) return IMAGE.test(path) ? image(url) : media();
    if (method === "GET") {
      if (/\/frame(\/|$)/.test(path) || /\/preview$/.test(path) || IMAGE.test(path)) return image(url);
      if (path === "/api/library/clip" || MEDIA.test(path)) return media();
      if (path === "/api/factura.csv") return {status: 200, contentType: "text/csv; charset=utf-8", body: "﻿concepto;usd\nAPI;31.20\n"};
      if (path === "/api/copia") return {status: 200, contentType: "application/gzip", body: ""};
    }
    let data;
    try { data = method === "GET" ? get(st, path, u.searchParams, who) : post(st, path, body || {}, who); }
    catch (error) { return json({error: `mock: ${error.stack || error}`}, 500); }
    if (data === undefined) { unmocked.push({method, path}); return json({}); }
    if (data && data.__status) { const {__status, ...rest} = data; return json(rest, __status); }
    return json(data);
  }
  if (IMAGE.test(path)) return image(url);
  return null;
}

// --- Playwright: every request of the page ---------------------------------------------------------------------------
async function install(page, {partner = false, origin = null} = {}) {
  const who = partner ? (typeof partner === "string" ? partner : SLUGS.partner) : "";
  const state = freshState();
  const handle = {state, unmocked: [], denied: [], blocked: [], who, origin};
  await page.route("**/*", async (route) => {
    const request = route.request(), url = request.url();
    if (!/^https?:/.test(url)) return route.continue();
    const u = new URL(url);
    if (!handle.origin && request.isNavigationRequest()) handle.origin = u.origin;         // the first document: the app
    if (u.origin === handle.origin) {
      let body = null;
      if (request.method() !== "GET") { try { body = request.postDataJSON(); } catch (e) { body = {}; } }
      const before = [unmocked.length, denied.length];
      const found = answer(state, request.method(), url, body, who);
      handle.unmocked.push(...unmocked.slice(before[0])); handle.denied.push(...denied.slice(before[1]));
      if (!found) return route.continue();                                                   // the page and its static files
      return route.fulfill({status: found.status, contentType: found.contentType, body: found.body});
    }
    // anything outside: images get a placeholder, the rest never leaves
    if (request.resourceType() === "image" || IMAGE.test(u.pathname) || /(^|\.)(ytimg\.com|ggpht\.com|googleusercontent\.com)$/.test(u.hostname)) {
      const found = image(url);
      return route.fulfill({status: 200, contentType: found.contentType, body: found.body});
    }
    if (request.resourceType() === "media" || MEDIA.test(u.pathname)) return route.fulfill({status: 204, body: ""});
    blocked.push(url); handle.blocked.push(url);
    return route.abort("blockedbyclient");
  });
  return handle;
}

module.exports = {install, answer, freshState, unmocked, denied, blocked, SLUGS, PARTNER_CHANNELS: PARTNERS[SLUGS.partner], CHANNELS};
