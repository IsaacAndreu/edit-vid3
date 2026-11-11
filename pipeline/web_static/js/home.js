let homeKind = (() => { try { return localStorage.getItem("inicio:tipo") || ""; } catch (e) { return ""; } })();   // "" | videos | shorts
window.pickKind = (k) => { homeKind = k; try { localStorage.setItem("inicio:tipo", k); } catch (e) {} drawHome(true); };
// the same block twice: the long videos, then the Shorts (each with its own count)
// «Para subir» and «En cola» can hide their Shorts (remembered in this browser): one line with how many and «Mostrar»
let hiddenShorts = (() => { try { return JSON.parse(localStorage.getItem("inicio:ocultarShorts") || "{}"); } catch (e) { return {}; } })();
window.toggleShorts = (key) => { hiddenShorts[key] = !hiddenShorts[key];
  try { localStorage.setItem("inicio:ocultarShorts", JSON.stringify(hiddenShorts)); } catch (e) {} drawHome(true); };
function splitBlock(title, list, opts = {}) {
  if (homeKind) return block(title, list, opts);
  const longs = list.filter((v) => !v.short), shorts = list.filter((v) => v.short);
  const key = opts.hideShorts;
  if (key && shorts.length && hiddenShorts[key]) {
    const line = `<div class="block"><div class="bh"><b>${title} · Shorts<span class="count">${shorts.length}</span></b>
      <span class="small"><span class="muted">ocultos</span> <button class="sm" onclick="toggleShorts('${key}')">Mostrar</button></span></div></div>`;
    return (longs.length ? block(longs.length && shorts.length ? `${title} · Vídeos` : title, longs, opts) : "") + line;
  }
  const hide = key ? ` <button class="sm" onclick="event.preventDefault();event.stopPropagation();toggleShorts('${key}')">Ocultar</button>` : "";
  if (!shorts.length || !longs.length) return block(`${title}${shorts.length ? " · Shorts" : ""}`, list,
    shorts.length && key ? {...opts, more: (opts.more || "") + hide} : opts);
  return block(`${title} · Vídeos`, longs, opts)
    + block(`${title} · Shorts`, shorts, {...opts, id: opts.id ? opts.id + "-s" : "", more: key ? hide.trim() : opts.more});
}
let homeChannel = (() => { try { return localStorage.getItem("inicio:canal") || ""; } catch (e) { return ""; } })();

function vrow(v, right = "") {
  const st = v.stage;
  const sub = [v.title && v.title !== v.slug ? v.slug : "", v.channel, v.minutes ? v.minutes + " min" : "", v.costUsd ? v.costUsd + " $" : ""]
    .filter(Boolean).join(" · ");
  const extra = st ? `<div class="small t-work mt-1">${st.number}/${st.of} · ${esc(STAGES[st.stage] || st.stage)} · desde hace ${ago(st.started)}</div>
      <div class="bar"><i style="--v:${Math.round(100 * (st.number - 1) / st.of)}%"></i></div>`
    : v.error ? `<div class="small t-bad mt-1">${esc(String(v.error).slice(0, 160))}</div>`
    : v.voice ? `<div class="small muted mt-1">${icon("mic")} ${v.voice === "generando" ? "generando la voz…" : "voz: " + esc(v.voice)}</div>`
    : v.lastError ? `<div class="small muted mt-1">${icon("repeat")} ${v.retryAt ? "reintento a las " + esc(v.retryAt) : "se reintenta en su turno"} · falló la última vez</div>` : "";
  return `<a class="vrow" href="#/video/${encodeURIComponent(v.slug)}">${dot(v.channel)}
    <div class="mw0"><div class="t">${esc(v.title || v.slug)}</div><div class="s">${esc(sub)}</div>${extra}</div>
    <div class="r">${right || pill(v.status)}</div></a>`;
}

function block(title, list, {cls = "", right = null, more = "", open = true, collapsible = false, limit = 0, id = ""} = {}) {
  if (!list.length) return "";
  const shown = limit ? list.slice(0, limit) : list;
  const rows = shown.map((v) => vrow(v, right ? right(v) : "")).join("")
    + (limit && list.length > limit ? `<div class="vrow"><span></span><span class="small muted">y ${list.length - limit} más…</span><span></span></div>` : "");
  const head = `<b>${title}<span class="count">${list.length}</span></b>${more ? `<span class="small">${more}</span>` : ""}`;
  const anchor = id ? ` id="${id}"` : "";
  return collapsible ? `<details${anchor} class="block ${cls}" ${open ? "open" : ""}><summary>${head}</summary>${rows}</details>`
    : `<div${anchor} class="block ${cls}"><div class="bh">${head}</div>${rows}</div>`;
}

let homeData = null;
async function home() {
  if (homeData) { drawHome(); apiCache.delete("/api/overview"); }        // what we have, at once; then the fresh answer
  const [overview, dates] = await Promise.all([api("/api/overview"), api("/api/upload/dates").catch(() => ({}))]);
  homeData = {overview, dates};
  drawHome();
}
async function unholdHome(slug) {      // «en pausa» (taken out of the queue): «Reintentar todos» leaves it out
  await post(`/api/video/${encodeURIComponent(slug)}/unhold`, {}); route();
}

let homeKey = "";
let homeView = (() => { try { return localStorage.getItem("inicio:vista") || "tabla"; } catch (e) { return "tabla"; } })();
let openSections = (() => { try { return JSON.parse(localStorage.getItem("inicio:secciones") || "{}"); } catch (e) { return {}; } })();
const expanded = {};
window.pickView = (v) => { homeView = v; try { localStorage.setItem("inicio:vista", v); } catch (e) {} drawHome(true); };
window.toggleSection = (k) => { openSections[k] = openSections[k] === false; try { localStorage.setItem("inicio:secciones", JSON.stringify(openSections)); } catch (e) {} drawHome(true); };
window.expandSection = (k) => { expanded[k] = true; drawHome(true); };
window.retryMany = async (slugs, button) => {
  if (button) { button.disabled = true; button.textContent = "En cola…"; }
  for (const slug of slugs) { try { await post(`/api/video/${encodeURIComponent(slug)}/retry`); } catch (e) { alert(`${slug}: ${e.message}`); } }
  setTimeout(() => { homeKey = ""; route(); }, 2000);
};
window.unholdMany = async (slugs, button) => {
  if (button) button.disabled = true;
  for (const slug of slugs) { try { await post(`/api/video/${encodeURIComponent(slug)}/unhold`, {}); } catch (e) { alert(`${slug}: ${e.message}`); } }
  setTimeout(() => { homeKey = ""; route(); }, 1500);
};
function drawHome(force = false) {               // the channel buttons redraw from what is already loaded: instant
  if (!homeData || !location.hash.match(/^(#\/?)?$/)) return;
  const {overview, dates} = homeData;
  data = overview;
  const s = data.service, b = data.budget, yt = data.youtube;
  const all = data.videos.filter((v) => !v.archived);
  // nothing changed since the last draw: leave the page alone (no flicker, no lost scroll) and look again later
  const key = JSON.stringify([homeChannel, homeKind, homeView, openSections, expanded, hiddenShorts, s, b, yt && yt.requests, all.map((v) => [v.slug, v.status, v.stage, v.error, v.lastError, v.retryAt, v.published, v.voice, v.quotaWait])]);
  if (!force && key === homeKey && $("#app").firstElementChild) { schedule(home, all.some((v) => v.status === "haciendo") ? 10000 : 30000); return; }
  homeKey = key;
  const channels = [...new Set(all.map((v) => v.channel).filter(Boolean))].sort();
  if (homeChannel && !channels.includes(homeChannel)) homeChannel = "";
  const vids = all.filter((v) => (!homeChannel || v.channel === homeChannel)
    && (!homeKind || (homeKind === "shorts" ? v.short : !v.short)));
  const by = (st) => vids.filter((v) => v.status === st);
  const toUpload = by("hecho").filter((v) => !v.published);
  const slot = dates || {};
  const today = new Date().toISOString().slice(0, 10);
  toUpload.sort((a, c) => ((slot[a.slug] || {}).date || "9999").localeCompare((slot[c.slug] || {}).date || "9999") || a.updated - c.updated);
  const uploaded = by("hecho").filter((v) => v.published)
    .sort((a, c) => String((c.published || {}).at || "").localeCompare(String((a.published || {}).at || "")));
  const making = by("haciendo");
  // everything that is not going to finish on its own: failed, waiting for a retry, held, missing files, voice error
  const attention = vids.filter((v) => (v.status === "error" || v.status === "incompleto" || v.status === "en pausa" || v.lastError || (v.voice || "").startsWith("error")) && !v.quotaWait);
  const queue = by("en cola").filter((v) => !attention.includes(v)).sort((a, c) => a.updated - c.updated);
  const failed = all.filter((v) => (v.status === "error" || v.lastError) && !v.quotaWait).length;
  const late = toUpload.filter((v) => (slot[v.slug] || {}).date && slot[v.slug].date < today).length;
  const when = (v) => { const d = (slot[v.slug] || {}).date; if (!d) return '<span class="muted">sin día</span>';
    return d < today ? `<span class="t-bad">${icon("alert")} tocaba ${DAY(d)}</span>` : d === today ? `<b class="t-warn">hoy · ${esc(slot[v.slug].time || "")}</b>` : `${icon("calendar")} ${DAY(d)}`; };
  // the server in one sentence, and what to do if it is not working
  const state = s.youtubeBlocked ? ["bad", "YouTube bloquea", `desde las ${esc(s.youtubeBlocked)} · se prueba cada hora`, '<a href="#/servidor">ver →</a>']
    : s.paused ? ["warn", "En pausa", "no empieza vídeos nuevos", '<a href="#/servidor">quitar la pausa →</a>']
    : s.watching ? ["ok", "Trabajando", making.length ? `${making.length} vídeo(s) haciéndose` : queue.length ? "entre vídeos: el siguiente empieza solo" : "vigilando: nada pendiente", ""]
    : s.queueRunning ? ["ok", "Cola en marcha", "sin vigilante: acabará la ronda y parará", ""] : ["bad", "Parado", "no hay vigilante", '<button class="sm" onclick="startQueue()">Arrancar la cola</button>'];
  if (window.partner) state[3] = "";                    // the server is the owner's: a partner only sees how it is
  // YouTube / proxy, the last 24 h: one number that says whether downloads are healthy
  const p24 = (yt && yt.byProxy || []).find((x) => /rainproxy|resi|residencial/.test(x.proxy)) || (yt && yt.byProxy || [])[0];
  const share = p24 && p24.requests ? Math.round(100 * p24.ok / p24.requests) : null;
  const ytKpi = window.partner ? "" : yt ? `<a class="kpi" href="#/servidor"><div class="k">YouTube · 24 h</div>
      <div class="v ${share == null ? "" : share >= 85 ? "ok" : share >= 60 ? "warn" : "bad"}">${share == null ? "—" : share + " %"}</div>
      <div class="d">${p24 ? `${p24.requests} peticiones bien${p24.proxy_gb ? ` · ${p24.proxy_gb.toFixed(2)} GB de proxy` : ""}${(p24.errors || {}).bot ? ` · ${p24.errors.bot} bot` : ""}` : `${yt.ok} de ${yt.requests} en la semana`}</div></a>`
    : `<div class="kpi"><div class="k">YouTube · 24 h</div><div class="v">—</div><div class="d">sin descargas todavía</div></div>`;
  // problems grouped by cause: one line per cause, the videos as chips, one action for all of them
  const explainOf = (v) => v.status === "incompleto" ? {kind: "warn", title: "Le falta el guion o la voz", hint: "Sube guion.txt y voz.mp3 (o activa la voz automática del canal).", actions: []}
    : v.status === "en pausa" ? {kind: "warn", title: "Quitados de la cola por ti", hint: "", actions: [{label: "Volver a la cola", many: "unhold"}]}
    : explain(v.error || v.lastError || v.voice || "", v);
  const groups = new Map();
  for (const v of attention) { const e = explainOf(v); const g = groups.get(e.title) || {e, vids: []}; g.vids.push(v); groups.set(e.title, g); }
  const causeRow = ([title, {e, vids: list}]) => {
    const slugs = list.map((v) => v.slug);
    const retry = e.actions.some((a) => a.go && a.go.startsWith("act(")) ? `<button class="main" onclick="retryMany(${esc(JSON.stringify(slugs))}, this)">Reintentar ${list.length > 1 ? `los ${list.length}` : "ahora"}</button>` : "";
    const unhold = e.actions.some((a) => a.many === "unhold") ? `<button class="main" onclick="unholdMany(${esc(JSON.stringify(slugs))}, this)">Volver a la cola${list.length > 1 ? ` (${list.length})` : ""}</button>` : "";
    const links = e.actions.filter((a) => a.href && !/decisiones/.test(a.href)).map(ACT).join("");
    const next = list.map((v) => v.retryAt).filter(Boolean).sort()[0];
    return `<div class="cause"><div><div class="t"><b>${esc(title)}</b> <span class="muted">· ${list.length === 1 ? "1 vídeo" : list.length + " vídeos"}${next ? ` · el vigilante reintenta a las ${esc(next)}` : ""}</span></div>
      ${e.hint ? `<div class="hint">${esc(e.hint)}</div>` : ""}
      <div class="vids">${list.map((v) => `<a href="#/video/${encodeURIComponent(v.slug)}" title="${esc(String(v.error || v.lastError || v.voice || "").slice(0, 300))}">${dot(v.channel, "sm")}${esc(v.slug)}</a>`).join("")}</div></div>
      <div class="act">${retry}${unhold}${links}${list.length === 1 && e.actions.some((a) => /decisiones/.test(a.href || "")) ? `<a class="btn" href="#/decisiones/${encodeURIComponent(slugs[0])}">Decisiones del relleno</a>` : ""}</div></div>`;
  };
  // the compact table: one line per video
  const chan = (v) => `<span class="chan">${dot(v.channel, "sm")}${esc(v.channel || "")}</span>`;
  const row = (v, extra) => `<tr><td class="t"><a href="#/video/${encodeURIComponent(v.slug)}">${esc(v.title || v.slug)}</a><div class="s">${esc(v.slug)}${v.minutes ? ` · ${v.minutes} min` : ""}${v.costUsd ? ` · ${v.costUsd} $` : ""}</div></td>
    <td class="wide">${chan(v)}</td>${extra}</tr>`;
  const table = (head, list, extra, opts = {}) => {
    if (!list.length) return "";
    const key = opts.key || head;
    const open = openSections[key] !== false;
    const shown = opts.limit && list.length > opts.limit && !expanded[key] ? list.slice(0, opts.limit) : list;
    return `<div class="block ${opts.cls || ""}"${opts.id ? ` id="${opts.id}"` : ""}><div class="bh click" onclick="toggleSection('${esc(key)}')"><b>${head}<span class="count">${list.length}</span></b><span class="small">${opts.more || ""} <span class="muted">${open ? "▴" : "▾"}</span></span></div>
      ${open ? `<div class="scroll-x"><table class="vt"><thead><tr><th>Vídeo</th><th class="wide">Canal</th>${opts.cols.map((c) => `<th class="${c.cls || ""}">${c.name}</th>`).join("")}</tr></thead>
      <tbody>${shown.map((v) => row(v, extra(v))).join("")}</tbody></table></div>
      ${shown.length < list.length ? `<div class="vrow click" onclick="expandSection('${esc(key)}')"><span></span><span class="small muted">y ${list.length - shown.length} más: ver todos</span><span></span></div>` : ""}` : ""}</div>`;
  };
  const makingRows = (v) => { const st = v.stage || {}; return `<td><span class="t-work">${esc(STAGES[st.stage] || st.stage || "")}</span> <span class="muted small">${st.number}/${st.of}</span></td>
    <td class="r"><span class="mini"><i style="--v:${Math.round(100 * ((st.number || 1) - 1) / (st.of || 15))}%"></i></span></td><td class="r wide">${ago(st.started)}</td>`; };
  const uploadRows = (v) => `<td>${when(v)}</td><td class="r wide">${v.minutes || "—"} min</td><td class="r"><a class="btn sm" href="#/video/${encodeURIComponent(v.slug)}">Abrir</a></td>`;
  const queueRows = (v) => `<td>${v.quotaWait ? `<span class="pill" title="${esc(v.quotaWait)}">${icon("pause")} ${v.quotaWait.startsWith("espera a YouTube") ? "espera YouTube" : "espera API"}</span>` : v.stagesDone ? `${v.stagesDone}/15 pasos` : '<span class="muted">por empezar</span>'}</td>
    <td class="r wide">${v.stagesDone ? `<span class="mini wait"><i style="--v:${Math.round(100 * v.stagesDone / 15)}%"></i></span>` : ""}</td>`;
  const doneRows = (v) => `<td>${v.published && v.published.at ? `subido ${esc(String(v.published.at).slice(0, 10))}` : "en YouTube"}</td><td class="r wide">${v.published && v.published.url ? `<a href="${esc(v.published.url)}" target="_blank" rel="noopener">ver ↗</a>` : ""}</td>`;
  const channelPick = channels.length > 6
    ? `<select class="w-auto" onchange="pickChannel(this.value)"><option value="">Todos los canales (${all.length})</option>${channels.map((c) => `<option value="${esc(c)}" ${c === homeChannel ? "selected" : ""}>${esc(c)} (${all.filter((v) => v.channel === c).length})</option>`).join("")}</select>`
    : channels.length > 1 ? `<div class="tools">${["", ...channels].map((c) => `<button class="chip ${c === homeChannel ? "on" : ""}" onclick="pickChannel('${esc(c)}')">${c ? `${dot(c)}${esc(c)} <span class="muted">${all.filter((v) => v.channel === c).length}</span>` : "Todos"}</button>`).join("")}</div>` : "";
  const kindPick = all.some((v) => v.short) ? `<span class="seg">${[["", "Todo"], ["videos", "Vídeos"], ["shorts", "Shorts"]].map(([k, name]) => `<button class="${k === homeKind ? "on" : ""}" onclick="pickKind('${k}')">${name}</button>`).join("")}</span>` : "";
  const viewPick = `<span class="seg"><button class="${homeView === "tabla" ? "on" : ""}" onclick="pickView('tabla')">Tabla</button><button class="${homeView === "lista" ? "on" : ""}" onclick="pickView('lista')">Tarjetas</button></span>`;
  const sections = homeView === "tabla"
    ? `${table("Haciéndose ahora", making, makingRows, {cls: "now", id: "h-now", cols: [{name: "Etapa"}, {name: "Avance", cls: "r"}, {name: "Desde hace", cls: "r wide"}]})}
       ${table("Para subir", toUpload, uploadRows, {more: '<a href="#/subir" onclick="event.stopPropagation()">Abrir «Para subir» →</a>', limit: 8, cols: [{name: "Cuándo"}, {name: "Dura", cls: "r wide"}, {name: "", cls: "r"}]})}
       ${table("En cola", queue, queueRows, {limit: 10, more: !s.watching && !s.queueRunning ? '<button class="main" onclick="event.stopPropagation();startQueue()">Hacer la cola ahora</button>' : "", cols: [{name: "Estado"}, {name: "", cls: "r wide"}]})}
       ${table("Subidos a YouTube", uploaded, doneRows, {key: "subidos", limit: 10, more: '<a href="#/videos" onclick="event.stopPropagation()">Ver la lista entera →</a>', cols: [{name: "Fecha"}, {name: "", cls: "r wide"}]})}`
    : `${splitBlock("Haciéndose ahora", making, {cls: "now", id: "h-now"})}
       ${splitBlock("Para subir", toUpload, {hideShorts: "subir", more: '<a href="#/subir">Abrir «Para subir» →</a>', right: when})}
       ${splitBlock("En cola", queue, {hideShorts: "cola", more: !s.watching && !s.queueRunning ? '<button class="main" onclick="startQueue()">Hacer la cola ahora</button>' : "",
         right: (v) => v.quotaWait ? `<span class="pill" title="${esc(v.quotaWait)}">${icon("pause")} ${v.quotaWait.startsWith("espera a YouTube") ? "espera YouTube" : "espera API"}</span>` : `<span class="muted">${v.stagesDone ? v.stagesDone + "/15 pasos" : "por empezar"}</span>`})}
       ${splitBlock("Subidos a YouTube", uploaded, {collapsible: true, open: false, limit: 30, more: '<a href="#/videos">Ver la lista entera →</a>',
         right: (v) => v.published && v.published.at ? `subido ${esc(String(v.published.at).slice(0, 10))}` : "en YouTube"})}`;
  $("#app").innerHTML = `
    <div class="glance">
      <a href="#/servidor" class="${state[0] === "bad" ? "bad" : ""}"><div class="n ${state[0] === "ok" ? "t-ok" : state[0] === "warn" ? "t-warn" : ""}">${icon(state[0] === "ok" ? "check" : state[0] === "warn" ? "pause" : "block", state[1])}</div><div class="l">${esc(state[1].toLowerCase())}</div></a>
      <a href="javascript:void(0)" onclick="document.getElementById('h-now')?.scrollIntoView({behavior:'smooth'})"><div class="n">${making.length}</div><div class="l">haciéndose</div></a>
      <a href="javascript:void(0)" class="${attention.length ? "bad" : ""}" onclick="document.getElementById('h-warn')?.scrollIntoView({behavior:'smooth'})"><div class="n">${attention.length}</div><div class="l">con problemas</div></a>
      <a href="#/subir"><div class="n">${toUpload.length}</div><div class="l">para subir${late ? ` · <span class="t-bad">${late} tarde</span>` : ""}</div></a></div>
    <form class="hero home-search" onsubmit="event.preventDefault();searchFrom(this.q.value)">
      <textarea name="q" placeholder="¿Ya lo hice? Escribe un tema o un nombre (dingos, Kratochvílová, A380…) o pega un guion entero"
        onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();searchFrom(this.value)}"></textarea>
      <button class="main">Buscar</button></form>
    <div class="kpis home-kpis">
      <div class="kpi"><a class="plain" href="#/servidor"><div class="k">Servidor</div><div class="v txt ${state[0]}">${state[1]}</div></a><div class="d">${[state[2], state[3]].filter(Boolean).join(" · ")}</div></div>
      ${ytKpi}
      <a class="kpi" href="#/subir"><div class="k">Para subir</div><div class="v ${late ? "bad" : ""}">${toUpload.length}</div>
        <div class="d">${late ? `${late} atrasado(s)` : toUpload.length ? "al día" : "nada pendiente"}${queue.length ? ` · ${queue.length} en cola` : ""}</div></a>
      <a class="kpi" href="#/gasto"><div class="k">Gasto de hoy</div><div class="v">${b.today.toFixed(2)} $</div>
        <div class="d">${b.limit ? "de " + b.limit.toFixed(2) + " $ de API" : "API, sin límite"}${b.proxyGbToday != null ? ` · proxy ${b.proxyGbToday.toFixed(2)} GB${b.proxyGbLimit ? ` de ${b.proxyGbLimit} GB` : ""} hoy` : yt && yt.proxy_gb ? ` · proxy ${yt.proxy_gb.toFixed(2)} GB/semana` : ""}</div>
        ${b.proxyGbLimit ? `<div class="bar ${(b.proxyGbToday || 0) / b.proxyGbLimit > 0.9 ? "bad" : ""}"><i style="--v:${Math.min(100, 100 * (b.proxyGbToday || 0) / b.proxyGbLimit)}%"></i></div>`
          : b.limit ? `<div class="bar acc"><i style="--v:${Math.min(100, 100 * b.today / b.limit)}%"></i></div>` : ""}</a>
    </div>
    ${attention.length ? `<div class="block warn" id="h-warn"><div class="bh"><b>Necesitan tu atención<span class="count">${attention.length}</span></b>
      ${failed > 1 ? `<span class="small"><button class="sm" onclick="retryAll()">Reintentar todos (${failed})</button> <span id="retrymsg" class="muted"></span></span>` : ""}</div>
      ${[...groups.entries()].sort((a, b) => b[1].vids.length - a[1].vids.length).map(causeRow).join("")}</div>` : ""}
    <div class="hb"><div class="tools">${channelPick}${kindPick}</div><div class="tools">${viewPick}</div></div>
    ${sections}
    ${vids.length ? "" : empty("film", "Aún no hay vídeos aquí", "", '<a class="btn main" href="#/nuevo">Crear uno</a>')}`;
  schedule(home, making.length ? 10000 : 30000);
}
window.retryOne = async (slug, button) => {
  if (button) { button.disabled = true; button.textContent = "En cola…"; }
  try { const r = await post(`/api/video/${encodeURIComponent(slug)}/retry`); if (r.message && button) button.textContent = r.message.slice(0, 40); }
  catch (e) { alert(e.message); }
  setTimeout(() => { homeKey = ""; route(); }, 2000);
};
window.pickChannel = (c) => { homeChannel = c; try { localStorage.setItem("inicio:canal", c); } catch (e) {} drawHome(true); };
window.searchFrom = (q) => { q = String(q || "").trim(); if (!q) return;
  if (q.length > 1500) { window.pendingSearch = q; location.hash = "#/buscar/" + encodeURIComponent("(guion pegado)"); }
  else location.hash = "#/buscar/" + encodeURIComponent(q); };

function marked(text, words) {
  let out = esc(text);
  for (const w of words.filter((x) => x.length > 2).slice(0, 12)) {
    const plain = w.normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    out = out.replace(new RegExp(`(${plain.split("").map((c) => c + "[\\u0300-\\u036f]?").join("")})`, "gi"), "<mark>$1</mark>");
  }
  return out;
}

async function searchPage(q) {
  const pasted = q === "(guion pegado)" && window.pendingSearch;
  const query = pasted ? window.pendingSearch : q;
  $("#app").innerHTML = `<h1>¿Ya lo hice?</h1><div class="muted">Buscando…</div>`;
  const r = await post("/api/search", {q: query});
  const words = query.split(/\s+/);
  $("#app").innerHTML = `<h1>¿Ya lo hice?</h1>
    <form class="hero" onsubmit="event.preventDefault();searchFrom(this.q.value)">
      <textarea name="q" onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();searchFrom(this.value)}">${pasted ? "" : esc(q)}</textarea>
      <button class="main">Buscar</button></form>
    <div class="small muted mb-2">${r.whole ? "Has pegado un guion: comparo sus nombres, lugares y cifras con todos tus guiones." : `Busco «${esc(q)}» en títulos y guiones de todos los vídeos (también los archivados y subidos).`}</div>
    ${r.results.length ? `<div class="block">${r.results.map((v) => `<a class="vrow hit" href="#/video/${encodeURIComponent(v.slug)}">
        ${dot(v.channel)}
        <div class="mw0"><div class="t">${esc(v.title || v.slug)}</div>
          <div class="s">${esc([v.title ? v.slug : "", v.channel, v.archived ? "archivado" : ""].filter(Boolean).join(" · "))}</div>
          ${v.snippet ? `<div class="small mt-1 ws">${r.whole ? esc(v.snippet) : marked(v.snippet, words)}</div>` : ""}</div>
        <div class="r">${r.whole ? `<b class="lg ${v.score >= 0.5 ? "t-bad" : "t-warn"}">${Math.round(v.score * 100)}% parecido</b><br>` : ""}
          ${v.published ? '<span class="pill hecho">en YouTube</span>' : pill(v.status)}</div></a>`).join("")}</div>`
      : empty("check", "No hay ningún vídeo con eso", r.whole ? "Este guion es nuevo." : "No lo has hecho todavía.", '<a class="btn main" href="#/nuevo">Crear vídeo →</a>')}
    ${(r.ideas || []).length ? `<h2>En tus ideas (sin hacer todavía)</h2><div class="block">${r.ideas.map((i) => `<a class="vrow hit" href="#/tablero">
        ${dot(i.channel)}
        <div class="mw0"><div class="t">${marked(i.title, words)}</div>
          <div class="s">${esc([i.channel || "sin canal", i.where].join(" · "))}</div>
          ${i.note ? `<div class="small mt-1 ws">${marked(i.note, words)}</div>` : ""}</div>
        <div class="r"><span class="pill">${icon("bulb")} idea</span></div></a>`).join("")}</div>` : ""}`;
}


async function startQueue() { await post("/api/queue"); setTimeout(route, 1500); }
async function retryAll() {
  const r = await post("/api/queue/retry-all");
  const box = $("#retrymsg"); if (box) box.textContent = r.message;
  setTimeout(route, 4000);
}
