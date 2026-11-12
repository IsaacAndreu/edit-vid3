// The frame around every page: the channel picked for the whole studio, and the command palette (⌘K / Ctrl+K).

// --- one channel for the whole studio -------------------------------------------------------------------------------
// Picked in the sidebar, it filters every page that lists videos or channels; each page's own picker still works and
// is reset to it when the studio channel changes. "" = every channel. Older keys (Inicio, Para subir) are kept in step.
let studioChannel = (() => { try { const v = localStorage.getItem("estudio:canal"); return v !== null ? v : localStorage.getItem("inicio:canal") || ""; } catch (e) { return ""; } })();
let studioRecent = (() => { try { return JSON.parse(localStorage.getItem("estudio:recientes") || "[]"); } catch (e) { return []; } })();
let studioChannels = [];                          // the channels this person can see (a partner: theirs)
let channelSynced = null;

function setStudioChannel(name) {
  studioChannel = name || "";
  if (studioChannel) studioRecent = [studioChannel, ...studioRecent.filter((c) => c !== studioChannel)].slice(0, 6);
  try {
    localStorage.setItem("estudio:canal", studioChannel); localStorage.setItem("inicio:canal", studioChannel);
    localStorage.setItem("subir:canal", studioChannel); localStorage.setItem("estudio:recientes", JSON.stringify(studioRecent));
  } catch (e) {}
  drawChannelPicker();
  route();
}

// before a page is drawn: its own channel filter follows the studio's when that changed
function syncChannelFilters() {
  if (channelSynced === studioChannel) return;
  channelSynced = studioChannel;
  homeChannel = statsChannel = uploadChannel = spendChannel = expChannel = studioChannel;
  allFilter.channel = studioChannel;
  if (studioChannel) { myChannel = studioChannel; radarChannel = studioChannel; }
}

async function loadStudioChannels() {
  try {
    const o = data && data.channels ? data : await api("/api/overview");
    const counts = {};
    (o.videos || []).forEach((v) => { if (!v.archived && v.channel) counts[v.channel] = (counts[v.channel] || 0) + 1; });
    studioChannels = (o.channels || []).map((name) => ({name, videos: counts[name] || 0}));
    if (studioChannel && !studioChannels.some((c) => c.name === studioChannel)) { studioChannel = ""; channelSynced = null; }
  } catch (e) {}
  drawChannelPicker();
}

const avatar = (name, cls = "") => `<span class="av ${cls}" style="--c:${chColor(name)}" aria-hidden="true">${esc(String(name).replace(/[^a-z0-9]/gi, "").slice(0, 2).toUpperCase())}</span>`;

function drawChannelPicker() {
  const box = $("#chpick");
  if (!box) return;
  const all = studioChannels.length;
  const recent = studioRecent.filter((c) => studioChannels.some((x) => x.name === c) && c !== studioChannel).slice(0, 5);
  paint(box, `<button type="button" class="chbtn" aria-haspopup="dialog" onclick="openChannelPicker()">
      ${studioChannel ? avatar(studioChannel) : `<span class="av all" aria-hidden="true">${all || ""}</span>`}
      <span class="mw0 grow"><b>${studioChannel ? esc(studioChannel) : "Todos los canales"}</b><small>${studioChannel ? "Cambiar de canal" : `${all} canales · elegir uno`}</small></span>
      ${icon("updown")}</button>
    ${recent.length || studioChannel ? `<div class="chrecent">${studioChannel ? `<button type="button" class="chip sm" onclick="setStudioChannel('')">Ver todos</button>` : ""}
      ${recent.map((c) => `<button type="button" class="avbtn" title="${esc(c)}" aria-label="Canal ${esc(c)}" onclick="setStudioChannel('${esc(c)}')">${avatar(c)}</button>`).join("")}</div>` : ""}`);
}

window.openChannelPicker = () => {
  const list = () => studioChannels.filter((c) => !q || c.name.includes(q));
  let q = "";
  const d = sheet(`<div class="row between nowrap"><h3 class="m-0">Canal</h3><button class="icon ghost" aria-label="Cerrar" onclick="document.getElementById('modal').close()">${icon("x")}</button></div>
    <input id="chq" type="search" class="mt-3" placeholder="Buscar canal…" aria-label="Buscar canal" autocomplete="off">
    <div id="chlist" class="pick mt-2" role="listbox" aria-label="Canales"></div>`);
  d.classList.add("narrow");
  const draw = () => {
    const items = [{name: "", videos: studioChannels.reduce((n, c) => n + c.videos, 0)}, ...list()];
    paint($("#chlist"), items.map((c, i) => `<button type="button" role="option" aria-selected="${c.name === studioChannel}" class="${c.name === studioChannel ? "on" : ""}"
      onclick="document.getElementById('modal').close();setStudioChannel('${esc(c.name)}')">${c.name ? avatar(c.name) : `<span class="av all" aria-hidden="true">${studioChannels.length}</span>`}
      <span class="grow">${c.name ? esc(c.name) : "Todos los canales"}</span><span class="muted small">${c.videos} vídeos</span></button>`).join(""));
  };
  draw();
  const input = $("#chq");
  input.oninput = () => { q = input.value.trim().toLowerCase(); draw(); };
  input.onkeydown = (e) => {
    const opts = [...document.querySelectorAll("#chlist button")];
    if (e.key === "Enter") { e.preventDefault(); (opts.find((b) => b.textContent.toLowerCase().includes(q) && q) || opts[0]).click(); }
    if (e.key === "ArrowDown") { e.preventDefault(); (opts[1] || opts[0]).focus(); }
  };
  $("#chlist").onkeydown = (e) => {
    const opts = [...document.querySelectorAll("#chlist button")], i = opts.indexOf(document.activeElement);
    if (e.key === "ArrowDown") { e.preventDefault(); (opts[i + 1] || opts[i]).focus(); }
    if (e.key === "ArrowUp") { e.preventDefault(); i <= 0 ? input.focus() : opts[i - 1].focus(); }
  };
  input.focus();
};

// --- the command palette: go anywhere, run the usual actions, or ask «¿ya lo hice?» -----------------------------------
const PALETTE_ACTIONS = [
  {name: "Nuevo vídeo", icon: "plus", go: () => { location.hash = "#/nuevo"; }},
  {name: "Reintentar todos los que fallaron", icon: "repeat", owner: true, go: () => retryAll()},
  {name: "Hacer la cola ahora", icon: "play", owner: true, go: () => startQueue()},
  {name: "Pausar o reanudar la cola", icon: "pause", owner: true, go: () => { location.hash = "#/ajustes"; }},
  {name: "Ver todos los canales", icon: "chart", go: () => { location.hash = "#/canales"; }},
];
function openPalette() {
  if (document.getElementById("modal")) return;
  const d = sheet(`<div class="cmdk"><div class="cmdk-in">${icon("search")}<input id="cmdq" type="search" placeholder="Ir a un vídeo, un canal o una página… o buscar «¿ya lo hice?»"
      aria-label="Buscar o ir a" autocomplete="off" role="combobox" aria-expanded="true" aria-controls="cmdlist"><kbd>Esc</kbd></div>
    <div id="cmdlist" role="listbox" aria-label="Resultados"></div></div>`);
  d.classList.add("palette");
  let at = 0, items = [];
  const norm = (t) => String(t || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
  const draw = () => {
    const q = norm($("#cmdq").value.trim());
    const has = (t) => !q || q.split(/\s+/).every((w) => norm(t).includes(w));
    const pages = [...document.querySelectorAll("header nav a")].map((a) => ({kind: "Ir a", name: a.textContent.trim(), href: a.getAttribute("href")}))
      .filter((p) => has(p.name)).slice(0, q ? 6 : 4);
    const chans = studioChannels.filter((c) => has(c.name)).slice(0, q ? 6 : 3).map((c) => ({kind: "Canal", name: c.name, channel: c.name, sub: `${c.videos} vídeos`}));
    const vids = q ? ((data && data.videos) || []).filter((v) => has(`${v.title || ""} ${v.slug} ${v.channel}`)).slice(0, 8)
      .map((v) => ({kind: "Vídeo", name: v.title || v.slug, sub: `${v.channel || ""} · ${v.published ? "subido" : v.status}`, href: "#/video/" + encodeURIComponent(v.slug), channel: v.channel})) : [];
    const acts = PALETTE_ACTIONS.filter((a) => (!a.owner || !window.partner) && has(a.name)).map((a) => ({kind: "Acción", ...a}));
    const raw = $("#cmdq").value.trim();
    const search = raw ? [{kind: "Buscar", name: `¿Ya lo hice? «${raw.slice(0, 60)}» en títulos y guiones`, icon: "search", go: () => searchFrom(raw)}] : [];
    items = [...vids, ...chans, ...pages, ...acts, ...search];
    at = Math.min(at, Math.max(0, items.length - 1));
    paint($("#cmdlist"), items.map((it, i) => `<button type="button" role="option" id="cmd-${i}" aria-selected="${i === at}" class="${i === at ? "on" : ""}" data-i="${i}">
        ${it.kind === "Vídeo" || it.kind === "Canal" ? (it.channel ? avatar(it.channel, "sm") : "") : icon(it.icon || (it.kind === "Ir a" ? "right" : "spark"))}
        <span class="grow mw0"><span class="t">${esc(it.name)}</span>${it.sub ? `<span class="s">${esc(it.sub)}</span>` : ""}</span><span class="k">${it.kind}</span></button>`).join("")
      || '<p class="muted small m-0">Nada con eso.</p>');
    $("#cmdq").setAttribute("aria-activedescendant", items.length ? "cmd-" + at : "");
  };
  const run = (i) => {
    const it = items[i];
    if (!it) return;
    d.close();
    if (it.go) it.go(); else if (it.href) location.hash = it.href; else if (it.channel) setStudioChannel(it.channel);
  };
  $("#cmdlist").onclick = (e) => { const b = e.target.closest("button[data-i]"); if (b) run(+b.dataset.i); };
  const input = $("#cmdq");
  input.oninput = () => { at = 0; draw(); };
  input.onkeydown = (e) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); at = (at + (e.key === "ArrowDown" ? 1 : -1) + items.length) % Math.max(1, items.length); draw();
      const on = document.getElementById("cmd-" + at); if (on) on.scrollIntoView({block: "nearest"}); }
    if (e.key === "Enter") { e.preventDefault(); run(at); }
  };
  draw();
  input.focus();
  if (!data || !data.videos) api("/api/overview").then((o) => { data = data || o; draw(); }).catch(() => {});
}
window.openPalette = openPalette;
document.addEventListener("keydown", (e) => {
  if ((e.metaKey || e.ctrlKey) && !e.altKey && e.key.toLowerCase() === "k" && $("#top") && !$("#top").classList.contains("hide")) { e.preventDefault(); openPalette(); }
});
