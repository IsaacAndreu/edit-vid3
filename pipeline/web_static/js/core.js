const STAGES = {factcheck: "Verificar datos", align: "Alinear la voz", planner: "Planificar planos", sourcing: "Buscar material",
  analysis: "Analizar clips", judge: "Elegir (juez)", ingest: "Descargar en HD", people: "Personas", fallback: "Rellenar huecos",
  coldopen: "Apertura", timeline: "Montaje", qa: "Revisión", render: "Render", shorts: "Shorts", package: "Títulos y miniaturas",
  dub: "Doblaje (montaje, render y Shorts)"};
const $ = (s) => document.querySelector(s);
const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
let timer = null, data = null;

// GETs answered in the last few seconds are served from memory (coming back to a page is instant); the page then
// refreshes itself from the network when its own timer fires
const apiCache = new Map();
async function api(path, options = {}) {
  const isGet = !options.method || options.method === "GET";
  const hit = isGet && apiCache.get(path);
  if (hit && Date.now() - hit.at < 8000) return hit.body;
  const res = await fetch(path, {credentials: "same-origin", ...options});
  if (res.status === 401) { showLogin(); throw new Error("login"); }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.error || res.statusText);
  if (isGet) apiCache.set(path, {at: Date.now(), body});
  else apiCache.clear();              // something changed on the server: nothing cached is trusted any more
  return body;
}
const post = (path, body) => api(path, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body || {})});

function showLogin() { $("#login").classList.remove("hide"); $("#top").classList.add("hide"); $("#app").innerHTML = ""; $("#pw").focus(); }
async function login() {
  try { await post("/api/login", {password: $("#pw").value}); $("#login").classList.add("hide"); start(); }
  catch (e) { $("#loginmsg").textContent = e.message; }
}
$("#pw").addEventListener("keydown", (e) => e.key === "Enter" && login());

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
  const inline = (t) => t.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, (_, a, src) => `<img alt="${a}" src="${/^https?:/.test(src) ? src : base + src.replace(/^\.?\//, "")}">`)
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
    return {kind: "bad", title: "Fallo del programa (un error de código)", hint: "No es culpa del vídeo. Copia el informe para Claude y pégalo en el chat: con eso se arregla.", actions: [{label: "📋 Copiar para Claude", go: `copyForClaude('${esc(v.slug || "")}', this)`}, retry]};
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
  const groups = [["metraje", "🎬 Contenido de terceros (metraje)"], ["simulacion", "🧪 Simulación"], ["stickman", "✏️ Monigotes"], ["mapas", "🗺️ Mapas"]];
  const html = groups.map(([k, name]) => {
    const list = d.channels.filter((c) => (kinds[c] || "metraje") === k);
    return list.length ? `<optgroup label="${name}">${list.map((c) => `<option>${esc(c)}</option>`).join("")}</optgroup>` : "";
  }).join("");
  return html || d.channels.map((c) => `<option>${esc(c)}</option>`).join("");
}
