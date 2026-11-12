const STAGES = {factcheck: "Verificar datos", align: "Alinear la voz", planner: "Planificar planos", sourcing: "Buscar material",
  analysis: "Analizar clips", judge: "Elegir (juez)", ingest: "Descargar en HD", people: "Personas", fallback: "Rellenar huecos",
  coldopen: "Apertura", timeline: "Montaje", qa: "Revisión", render: "Render", shorts: "Shorts", package: "Títulos y miniaturas",
  dub: "Doblaje (montaje, render y Shorts)"};
const $ = (s) => document.querySelector(s);
const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
let timer = null, data = null;
let navStop = null, navId = 0;                 // the page being opened: its requests are dropped when another one is

// the channel <select> of every row of a long table carries only its own option until it is used: the other channels
// are added when it gets the focus or a touch (one per row × 30 channels was most of «Todos los vídeos» and «Gasto»)
const lazyLists = {};
const lazySelect = (list, current, attrs) => `<select ${attrs} onfocus="lazyFill(this, '${list}')" onpointerdown="lazyFill(this, '${list}')"><option selected>${esc(current)}</option></select>`;
window.lazyFill = (select, list) => {
  if (select.options.length > 1) return;
  const current = select.value, all = lazyLists[list] || [];
  select.innerHTML = (all.includes(current) ? all : [current, ...all]).map((c) => `<option ${c === current ? "selected" : ""}>${esc(c)}</option>`).join("");
};

// stroke icons, the same family as the sidebar's: icon("search"), or icon("alert", "Aviso") when it stands alone
const ICONS = {
  search: '<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>',
  refresh: '<path d="M21 12a9 9 0 1 1-2.6-6.4"/><path d="M21 4v5h-5"/>',
  restart: '<path d="M3 12a9 9 0 1 0 2.6-6.4"/><path d="M3 4v5h5"/>',
  undo: '<path d="M9 14 4 9l5-5"/><path d="M4 9h10a6 6 0 0 1 0 12h-3"/>',
  repeat: '<path d="m17 2 4 4-4 4"/><path d="M3 11V9a3 3 0 0 1 3-3h15M7 22l-4-4 4-4"/><path d="M21 13v2a3 3 0 0 1-3 3H3"/>',
  play: '<path d="m7 4 13 8-13 8z"/>', pause: '<path d="M8 5v14M16 5v14"/>', stop: '<rect x="6" y="6" width="12" height="12" rx="1.5"/>',
  mic: '<path d="M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3z"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>',
  phone: '<rect x="7" y="2" width="10" height="20" rx="2"/><path d="M11 18h2"/>',
  film: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 4v16M17 4v16M3 9h4M3 15h4M17 9h4M17 15h4"/>',
  news: '<path d="M4 5h13v14H6a2 2 0 0 1-2-2z"/><path d="M17 9h3v8a2 2 0 0 1-2 2M8 9h5M8 13h5"/>',
  trend: '<path d="M3 17l6-6 4 4 8-8"/><path d="M14 7h7v7"/>',
  target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
  trophy: '<path d="M8 21h8M12 17v4M7 4h10v5a5 5 0 0 1-10 0z"/><path d="M17 5h3v2a3 3 0 0 1-3 3M7 5H4v2a3 3 0 0 0 3 3"/>',
  ruler: '<path d="M3 17 17 3l4 4L7 21z"/><path d="m7 13 2 2M10 10l2 2M13 7l2 2"/>',
  bulb: '<path d="M9 18h6M10 21h4"/><path d="M12 3a6 6 0 0 0-4 10.5c.8.8 1 1.5 1 2.5h6c0-1 .2-1.7 1-2.5A6 6 0 0 0 12 3z"/>',
  pen: '<path d="M4 20h4L20 8l-4-4L4 16z"/><path d="m14 6 4 4"/>',
  flask: '<path d="M9 3h6M10 3v6l-6 10a2 2 0 0 0 1.7 3h12.6a2 2 0 0 0 1.7-3L14 9V3"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
  download: '<path d="M12 4v12"/><path d="m6 10 6 6 6-6"/><path d="M4 20h16"/>', upload: '<path d="M12 16V4"/><path d="m6 10 6-6 6 6"/><path d="M4 20h16"/>',
  copy: '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V6a2 2 0 0 1 2-2h9"/>',
  scissors: '<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M8.1 8.1 20 20M8.1 15.9 20 4"/>',
  x: '<path d="M6 6l12 12M18 6 6 18"/>', updown: '<path d="m7 9 5-5 5 5M7 15l5 5 5-5"/>', check: '<path d="m5 12 5 5 9-10"/>', plus: '<path d="M12 5v14M5 12h14"/>', minus: '<path d="M5 12h14"/>',
  up: '<path d="m6 15 6-6 6 6"/>', down: '<path d="m6 9 6 6 6-6"/>', right: '<path d="m9 6 6 6-6 6"/>',
  external: '<path d="M14 4h6v6M20 4l-9 9"/><path d="M18 14v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4"/>',
  alert: '<path d="M12 4 2.5 20h19z"/><path d="M12 10v4M12 17v.5"/>', info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7v.5"/>',
  block: '<circle cx="12" cy="12" r="9"/><path d="m5.6 5.6 12.8 12.8"/>',
  pin: '<path d="M12 17v5M8 3h8l-1 6 3 4H6l3-4z"/>', fire: '<path d="M12 3c1 4 5 5 5 10a5 5 0 0 1-10 0c0-2 1-3 2-4 0 2 1 3 2 3 0-3-1-5 1-9z"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>', eye: '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  inbox: '<path d="M3 13h5l1 3h6l1-3h5"/><path d="M5 5h14l2 8v6H3v-6z"/>', doc: '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6M8 13h8M8 17h8"/>',
  chart: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>', map: '<path d="m3 6 6-2 6 2 6-2v14l-6 2-6-2-6 2z"/><path d="M9 4v14M15 6v14"/>',
  compass: '<circle cx="12" cy="12" r="9"/><path d="m15 9-2 4-4 2 2-4z"/>', spark: '<path d="M12 3v5M12 16v5M3 12h5M16 12h5M6 6l3 3M15 15l3 3M18 6l-3 3M9 15l-3 3"/>',
  thumb: '<path d="M7 11v9H4v-9zM7 11l4-8a2 2 0 0 1 3 2l-1 4h5a2 2 0 0 1 2 2.4l-1.4 6A2 2 0 0 1 16.6 20H7"/>',
  chat: '<path d="M4 5h16v11H9l-5 4z"/>', money: '<path d="M12 2v20M17 6.5H9.5a2.5 2.5 0 0 0 0 5h5a2.5 2.5 0 0 1 0 5H7"/>',
};
const icon = (name, label = "") => `<svg class="i" viewBox="0 0 24 24" ${label ? `role="img" aria-label="${esc(label)}"` : 'aria-hidden="true"'}>${ICONS[name] || ""}</svg>`;
// the dot with the colour of a channel
const dot = (channel, cls = "") => `<span class="dot ${cls}" style="--c:${chColor(channel)}"></span>`;
// a form field: the label, the control and its help under it (never a long parenthesis inside the label)
const field = (label, control, help = "", id = "") => `<div class="field"><label${id ? ` for="${id}"` : ""}>${label}</label>${control}${help ? `<p class="help">${help}</p>` : ""}</div>`;
// nothing here yet: what it is, and the one thing to do about it
const empty = (name, title, text = "", action = "") => `<div class="empty">${icon(name)}<b>${title}</b>${text ? `<p>${text}</p>` : ""}${action}</div>`;
// a thumbnail that never makes the page jump: lazy, decoded off the main thread, its 16:9 box reserved
const thumb = (src, cls = "shot", alt = "") => `<img class="${cls}" src="${esc(src)}" alt="${esc(alt)}" loading="lazy" decoding="async" width="320" height="180">`;

// GETs answered in the last few seconds are served from memory (coming back to a page is instant); the page then
// refreshes itself from the network when its own timer fires
const apiCache = new Map();
async function api(path, options = {}) {
  const isGet = !options.method || options.method === "GET";
  const hit = isGet && apiCache.get(path);
  if (hit && Date.now() - hit.at < 8000) return hit.body;
  // a GET belongs to the page that asked for it: when another page is opened its answer never arrives (the promise
  // stays pending), so a slow answer cannot paint the old page over the new one
  const stop = isGet ? navStop : null;
  let res;
  try { res = await fetch(path, {credentials: "same-origin", ...(stop ? {signal: stop.signal} : {}), ...options}); }
  catch (e) { if (stop && stop.signal.aborted) return new Promise(() => {}); throw e; }
  if (stop && stop.signal.aborted) return new Promise(() => {});
  if (res.status === 401) { showLogin(); throw new Error("login"); }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.error || res.statusText);
  if (isGet) apiCache.set(path, {at: Date.now(), body});
  else apiCache.clear();              // something changed on the server: nothing cached is trusted any more
  return body;
}
const post = (path, body) => api(path, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body || {})});

function showLogin() { $("#login").classList.remove("hide"); $("#top").classList.add("hide"); paint($("#app"), "", true); $("#pw").focus(); }
async function login() {
  try { await post("/api/login", {password: $("#pw").value}); $("#login").classList.add("hide"); start(); }
  catch (e) { $("#loginmsg").textContent = e.message; }
}

function ago(iso) {
  if (!iso) return "";
  const m = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  return m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${m % 60} min`;
}
function mins(s) { return s == null ? "—" : s >= 60 ? `${(s / 60).toFixed(1)} min` : `${Math.round(s)} s`; }

// minimal markdown: headings, lists, tables, bold/italic, code, links, images (relative to the video's files)
function md(text, base) {
  if (!text) return '<p class="muted">Todavía no hay.</p>';
  const lines = esc(text).split("\n"); let html = "", inList = false, table = [], code = false;
  const inline = (t) => t.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, (_, a, src) => `<img alt="${a}" loading="lazy" decoding="async" src="${/^https?:/.test(src) ? src : base + src.replace(/^\.?\//, "")}">`)
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
    .replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>").replace(/(^|\s)_([^_]+)_/g, "$1<i>$2</i>").replace(/`([^`]+)`/g, "<code>$1</code>");
  const flush = () => { if (inList) { html += "</ul>"; inList = false; }
    if (table.length) { html += "<table>" + table.filter((r) => !/^\|?\s*-{2,}/.test(r)).map((r, i) => "<tr>" + r.replace(/^\||\|$/g, "").split("|")
      .map((c) => i ? `<td>${inline(c.trim())}</td>` : `<th>${inline(c.trim())}</th>`).join("") + "</tr>").join("") + "</table>"; table = []; } };
  for (const line of lines) {
    if (line.startsWith("```")) { flush(); html += code ? "</pre>" : "<pre>"; code = !code; continue; }
    if (code) { html += line + "\n"; continue; }
    if (/^\s*\|/.test(line)) { table.push(line.trim()); continue; }
    if (/^\s*[-*] /.test(line)) { if (table.length) flush(); if (!inList) { html += "<ul>"; inList = true; } html += `<li>${inline(line.replace(/^\s*[-*] /, ""))}</li>`; continue; }
    flush();
    const h = line.match(/^(#{1,4}) (.*)/);
    if (h) html += `<h${h[1].length + 1}>${inline(h[2])}</h${h[1].length + 1}>`;
    else if (line.trim()) html += `<p>${inline(line)}</p>`;
  }
  flush(); return html;
}

function pill(status) { return `<span class="pill ${status === "en cola" ? "cola" : status === "en pausa" ? "pausa" : status}">${esc(status)}</span>`; }

// What an error means and what to do about it, in plain words (the raw text stays available in full).
function explain(error, v = {}) {
  const t = String(error || "");
  const slug = encodeURIComponent(v.slug || "");
  const retry = {label: "Reintentar ahora", go: `act('retry')`};
  if (/Stopped|Parado por la señal|SIGTERM|SIGHUP|interrumpido/i.test(t))
    return {kind: "warn", title: "Interrumpido por un reinicio", hint: "No falló: el servicio se reinició (actualización o reinicio a mano). Las etapas hechas se conservan; al reintentar sigue donde estaba.", actions: [retry]};
  if (/no eres un bot|YouTubeBlocked|no deja descargar|bloquea/i.test(t))
    return {kind: "bad", title: "YouTube rechazó las descargas", hint: "Casi siempre es la IP de salida del proxy. El programa cambia de sesión solo; si vuelve a pasar, mira «Estado del servidor» → proxy.", actions: [retry, {label: "Estado del servidor", href: "#/servidor"}]};
  if (/sin ninguna imagen|planos sin|pizarras de texto|rechazó casi todo/i.test(t))
    return {kind: "bad", title: "A la mayoría de planos no les encontró imagen", hint: "El juez rechazó casi todo lo que había. Revisa qué descartó y por qué, o permite el stock como último recurso en el canal.", actions: [{label: "Ver decisiones del relleno", href: `#/decisiones/${slug}`}, retry]};
  if (/proxy .*no responde|ProxyDown|Tunnel connection|unable to connect to proxy/i.test(t))
    return {kind: "warn", title: "El proxy no respondía", hint: "Se reintenta solo cuando vuelve. Si es el proxy de casa, comprueba que el PC está encendido y proxy-youtube abierto.", actions: [retry, {label: "Estado del servidor", href: "#/servidor"}]};
  if (/cuota|quota|búsquedas hoy|ApiSearchesShort/i.test(t))
    return {kind: "warn", title: "Se acabó la cuota de la API de YouTube", hint: "Espera sola a la cuota nueva de mañana; no hace falta hacer nada.", actions: []};
  if (/sin saldo|insufficient|401|clave .* no vale|API key/i.test(t))
    return {kind: "bad", title: "Una clave de API no vale o no tiene saldo", hint: "Recarga o renueva la clave en .env y pulsa reintentar.", actions: [retry, {label: "Ajustes", href: "#/ajustes"}]};
  if (/Traceback|TypeError|NameError|KeyError|AttributeError|ValueError|IndexError/.test(t))
    return {kind: "bad", title: "Fallo del programa (un error de código)", hint: "No es culpa del vídeo. Copia el informe para Claude y pégalo en el chat: con eso se arregla.", actions: [{label: icon("copy") + " Copiar para Claude", go: `copyForClaude('${esc(v.slug || "")}', this)`}, retry]};
  if (/voz|GenAIPro|tts/i.test(t))
    return {kind: "warn", title: "La voz no se pudo generar", hint: "Revisa los créditos de GenAIPro o sube tu propio voz.mp3.", actions: [retry]};
  return {kind: "bad", title: "Falló", hint: "", actions: [retry]};
}
const ACT = (a) => a.href ? `<a class="btn" href="${a.href}">${a.label}</a>` : `<button onclick="event.preventDefault();event.stopPropagation();${a.go}">${a.label}</button>`;

const hue = (name) => { let h = 0; for (const c of String(name || "")) h = (h * 31 + c.charCodeAt(0)) % 360; return h; };
const chColor = (name) => name ? `hsl(${hue(name)} 70% 58%)` : "var(--muted)";

const fmt = (n) => n == null ? "—" : Number(n).toLocaleString("es-ES", {maximumFractionDigits: 1});
const kfmt = (n) => n == null ? "—" : n >= 1e6 ? fmt(n / 1e6) + " M" : n >= 1e3 ? fmt(n / 1e3) + " mil" : fmt(n);
const times = (r) => r == null ? "—" : fmt(r) + "×";
const clock = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
function jobLine(job, what) {
  if (!job) return "";
  if (job.running) return `<div class="notice">${what}… <span class="small muted">(se actualiza solo)</span><pre class="small">${esc(job.log.split("\n").slice(-6).join("\n"))}</pre></div>`;
  if (job.failed) return `<div class="notice bad">Falló: <pre class="small">${esc(job.log.split("\n").slice(-10).join("\n"))}</pre></div>`;
  return "";
}

const DAY = (iso) => { const d = new Date(iso + "T12:00:00"); return d.toLocaleDateString("es-ES", {weekday: "long", day: "numeric", month: "short"}); };

// the new-video form: channels grouped by how their videos are made, so each kind is found at a glance
function channelOptions(d) {
  const kinds = d.channelKinds || {};
  const groups = [["metraje", "Contenido de terceros (metraje)"], ["simulacion", "Simulación"], ["stickman", "Monigotes"], ["mapas", "Mapas"]];
  const html = groups.map(([k, name]) => {
    const list = d.channels.filter((c) => (kinds[c] || "metraje") === k);
    return list.length ? `<optgroup label="${name}">${list.map((c) => `<option>${esc(c)}</option>`).join("")}</optgroup>` : "";
  }).join("");
  return html || d.channels.map((c) => `<option>${esc(c)}</option>`).join("");
}
