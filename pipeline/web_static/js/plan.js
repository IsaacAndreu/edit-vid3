let allFilter = {q: "", channel: "", state: "todos", kind: ""};
let allSort = {key: "updated", dir: -1};
function allSortBy(key) { allSort = {key, dir: allSort.key === key ? -allSort.dir : (key === "title" || key === "channel" ? 1 : -1)}; allVideosPage(); }
async function allVideosPage() {
  data = await api("/api/overview");
  const f = allFilter, words = f.q.toLowerCase().split(/\s+/).filter(Boolean);
  const stateOf = (v) => v.published ? "subidos" : v.archived ? "archivados" : v.status === "hecho" ? "sin subir" : "en marcha";
  const value = (v) => allSort.key === "title" ? (v.title || v.slug).toLowerCase() : allSort.key === "channel" ? (v.channel || "")
    : allSort.key === "published" ? String((v.published || {}).at || "") : allSort.key === "cost" ? (v.costUsd || 0) : allSort.key === "minutes" ? (v.minutes || 0) : v.updated;
  const list = data.videos.filter((v) => (!f.channel || (f.channel === "(sin canal)" ? !v.channel : v.channel === f.channel))
      && (f.state === "todos" || stateOf(v) === f.state)
      && (!f.kind || (f.kind === "shorts" ? v.short : !v.short))
      && words.every((w) => `${v.slug} ${v.title || ""}`.toLowerCase().includes(w)))
    .sort((a, b) => { const x = value(a), y = value(b); return (x < y ? -1 : x > y ? 1 : 0) * allSort.dir; });
  const count = (fn) => data.videos.filter(fn).length;
  const channels = [...new Set(data.videos.map((v) => v.channel).filter(Boolean))].sort();     // only those with videos
  const th = (key, name, cls = "") => `<th class="${cls}" style="cursor:pointer" onclick="allSortBy('${key}')">${name}${allSort.key === key ? (allSort.dir > 0 ? " ▴" : " ▾") : ""}</th>`;
  const state = (v) => v.published ? `<span class="pill hecho">subido</span> <span class="small muted">${esc(String(v.published.at || "").slice(0, 10))}</span>${v.published.url ? ` <a href="${esc(v.published.url)}" target="_blank" rel="noopener">↗</a>` : ""}`
    : v.archived ? '<span class="pill">archivado</span>' : pill(v.lastError && v.status === "en cola" ? "reintento" : v.status);
  $("#app").innerHTML = `<h1>Todos los vídeos</h1>
    <div class="hb" style="margin-top:0"><div class="tools">
      <input placeholder="Buscar por nombre o título" value="${esc(f.q)}" oninput="allFilter.q=this.value;clearTimeout(window.allT);window.allT=setTimeout(allVideosPage,300)" style="width:260px">
      <select onchange="allFilter.channel=this.value;allVideosPage()"><option value="">Todos los canales (${data.videos.length})</option>${[...channels, ...(count((v) => !v.channel) ? ["(sin canal)"] : [])].map((c) =>
        `<option value="${esc(c)}" ${f.channel === c ? "selected" : ""}>${esc(c)} (${count((v) => c === "(sin canal)" ? !v.channel : v.channel === c)})</option>`).join("")}</select>
      ${data.videos.some((v) => v.short) ? `<span class="seg">${[["", "Todo"], ["videos", "Vídeos"], ["shorts", "Shorts"]].map(([k, name]) => `<button class="${(f.kind || "") === k ? "on" : ""}" onclick="allFilter.kind='${k}';allVideosPage()">${name}</button>`).join("")}</span>` : ""}</div>
      <div class="tools"><span class="seg">${["todos", "en marcha", "sin subir", "subidos", "archivados"].map((st) => `<button class="${f.state === st ? "on" : ""}" onclick="allFilter.state='${st}';allVideosPage()">${st} <span class="muted">${st === "todos" ? data.videos.length : count((v) => stateOf(v) === st)}</span></button>`).join("")}</span></div></div>
    <div class="small muted" style="margin:4px 0 8px">${list.length} vídeo(s). El desplegable de canal cambia dónde cuenta el vídeo (no se rehace).</div>
    <div class="block"><div style="overflow:auto"><table class="vt"><thead><tr>${th("title", "Vídeo")}${th("channel", "Canal", "wide")}${th("updated", "Estado")}${th("minutes", "Dura", "r wide")}${th("cost", "API", "r wide")}</tr></thead>
      <tbody>${list.map((v) => `<tr><td class="t"><a href="#/video/${encodeURIComponent(v.slug)}">${esc(v.title || v.slug)}</a><div class="s">${esc(v.title ? v.slug : "")}</div></td>
        <td class="wide"><select style="width:auto;padding:2px 6px;font-size:12.5px" onchange="post('/api/video/${encodeURIComponent(v.slug)}/channel', {channel: this.value}).then(allVideosPage).catch((e)=>alert(e.message))">
          ${v.channel ? (data.channels.includes(v.channel) ? "" : `<option selected>${esc(v.channel)}</option>`) : "<option selected>(sin canal)</option>"}${data.channels.map((c) => `<option ${c === v.channel ? "selected" : ""}>${esc(c)}</option>`).join("")}</select></td>
        <td>${state(v)}</td><td class="r wide">${v.minutes ? v.minutes + " min" : "—"}</td><td class="r wide">${v.costUsd ? v.costUsd + " $" : "—"}</td></tr>`).join("")
        || '<tr><td colspan="5" class="muted" style="padding:14px">Ninguno con estos filtros.</td></tr>'}</tbody></table></div></div>`;
}

let errFilter = "todos";
async function errorsPage() {
  const [e, o] = [await api("/api/errors"), data && data.videos ? data : await api("/api/overview")];
  data = o;
  const done = o.videos.filter((v) => v.hasVideo).sort((a, b) => (b.updated || 0) - (a.updated || 0));
  const byVideo = Object.fromEntries(e.videos.map((v) => [v.slug, v]));
  const pending = done.filter((v) => !byVideo[v.slug]).length;
  const list = done.filter((v) => errFilter === "todos" || (errFilter === "sin revisar") === !byVideo[v.slug]);
  const maxReason = Math.max(1, ...e.reasons.map((r) => r.count));
  const acc = (r) => r.accuracy == null ? "—" : `<b class="${r.accuracy >= 90 ? "ok" : r.accuracy < 70 ? "bad" : ""}">${r.accuracy} %</b>`;
  const verdicts = (r) => `<span class="ok">${r.correcta}</span> · <span class="bad">${r.incorrecta}</span> · <span class="muted">${r.dudosa}</span>`;
  $("#app").innerHTML = `<h1>Clips marcados</h1>
    <div class="small muted" style="margin:-4px 0 12px">Marca los clips de cada vídeo terminado (bien / mal / dudoso) y el programa aprende qué comprobaciones aflojar o apretar.</div>
    <div class="kpis">
      <div class="kpi"><div class="k">Clips bien</div><div class="v ${e.accuracy == null ? "" : e.accuracy >= 90 ? "ok" : e.accuracy < 70 ? "bad" : "warn"}">${e.accuracy == null ? "—" : e.accuracy + " %"}</div>
        <div class="d">${e.total.correcta} bien · ${e.total.incorrecta} mal · ${e.total.dudosa} dudosos</div></div>
      <div class="kpi"><div class="k">Vídeos revisados</div><div class="v">${e.videos.length} <span class="muted" style="font-size:16px;font-weight:600">/ ${done.length}</span></div>
        <div class="d">${pending ? `${pending} sin revisar` : "todos revisados"}</div></div>
      <div class="kpi"><div class="k">Fallo más común</div><div class="v" style="font-size:17px;line-height:1.3">${e.reasons.length ? esc(e.reasons[0].name) : "—"}</div>
        <div class="d">${e.reasons.length ? `${e.reasons[0].count} clip(s)` : "sin clips marcados mal"}</div></div>
      <div class="kpi"><div class="k">Peor método</div><div class="v" style="font-size:17px;line-height:1.3">${e.methods.length ? esc([...e.methods].sort((a, b) => a.accuracy - b.accuracy)[0].name) : "—"}</div>
        <div class="d">${e.methods.length ? `${[...e.methods].sort((a, b) => a.accuracy - b.accuracy)[0].accuracy} % de acierto` : "—"}</div></div>
    </div>
    ${e.tips.length ? `<div class="elf">🧝 ${e.tips.map(esc).join("<br>")}</div>` : ""}
    <div class="hb"><h2 style="margin:0">Vídeos terminados</h2>
      <span class="seg">${[["todos", `Todos <span class="muted">${done.length}</span>`], ["sin revisar", `Sin revisar <span class="muted">${pending}</span>`], ["revisados", `Revisados <span class="muted">${e.videos.length}</span>`]].map(([k, n]) =>
        `<button class="${k === errFilter ? "on" : ""}" onclick="errFilter='${k}';errorsPage()">${n}</button>`).join("")}</span></div>
    <div class="block" style="margin-top:6px"><div style="overflow:auto"><table class="vt"><thead><tr><th>Vídeo</th><th class="wide">Canal</th><th class="wide">Clips bien · mal · dudosos</th><th class="r wide">Acierto</th><th></th></tr></thead>
      <tbody>${list.map((v) => { const r = byVideo[v.slug]; return `<tr><td class="t"><a href="#/video/${encodeURIComponent(v.slug)}">${esc(v.title || v.slug)}</a><div class="s">${esc(v.title ? v.slug : "")}<span class="ph"> · ${r ? `${verdicts(r)} · ${acc(r)}` : "sin revisar"}</span></div></td>
        <td class="wide"><span class="chan"><i style="width:8px;height:8px;border-radius:50%;background:${chColor(v.channel)}"></i>${esc(v.channel || "—")}</span></td>
        <td class="wide">${r ? verdicts(r) : '<span class="muted">sin revisar</span>'}</td><td class="r wide">${r ? acc(r) : "—"}</td>
        <td class="acts" style="text-align:right"><a class="btn ${r ? "" : "main"}" href="#/revisar/${encodeURIComponent(v.slug)}">${r ? "Clips" : "Revisar"}</a>
          <a class="btn" href="#/decisiones/${encodeURIComponent(v.slug)}" title="Planos donde el programa buscó otra cosa">Relleno</a></td></tr>`; }).join("")
        || `<tr><td colspan="5" class="muted" style="padding:14px">${done.length ? "Ninguno con este filtro." : "Aún no hay vídeos terminados."}</td></tr>`}</tbody></table></div></div>
    ${e.reasons.length || e.methods.length ? `<div class="grid2" style="margin-top:16px">
      ${e.reasons.length ? `<div class="block"><div class="bh"><b>Por qué fallan los clips</b></div><div style="padding:8px 16px 12px">${e.reasons.map((r) => `<div class="row small" style="justify-content:space-between;margin-top:6px"><span>${esc(r.name)}</span><b>${r.count}</b></div>
        <div class="hbar"><i style="width:${100 * r.count / maxReason}%;background:var(--bad)"></i></div>`).join("")}</div></div>` : ""}
      ${e.methods.length ? `<div class="block"><div class="bh"><b>Acierto por cómo se encontró el clip</b></div><table class="vt"><thead><tr><th>Método</th><th class="r">Bien</th><th class="r">Mal</th><th class="r">Dudosos</th><th class="r">Acierto</th></tr></thead>
        <tbody>${[...e.methods].sort((a, b) => a.accuracy - b.accuracy).map((m) => `<tr><td>${esc(m.name)}</td><td class="r">${m.correcta}</td><td class="r">${m.incorrecta}</td><td class="r">${m.dudosa}</td><td class="r">${acc(m)}</td></tr>`).join("")}</tbody></table></div>` : ""}
    </div>` : ""}`;
}

// --- Calendario: días de publicación por canal y qué vídeo sale en cada uno --------------------------------------

async function calendarPage() {
  const a = await api("/api/agenda"), st = a.settings, today = new Date().toISOString().slice(0, 10);
  const byDay = {};
  a.plan.forEach((s) => (byDay[s.date] = byDay[s.date] || []).push(s));
  const free = (channel) => a.videos.filter((v) => v.channel === channel && !["subido"].includes(v.status));
  const slot = (s) => {
    const v = s.video, cls = s.ok ? "ok" : s.gap ? "gap" : "";
    const state = !v ? `<span class="pill error">hueco</span> <span class="small muted">${s.past ? "" : (s.late ? "⏰ ya vas tarde" : "guion y voz antes del " + DAY(s.deadline.slice(0, 10)) + " " + s.deadline.slice(11))}</span>`
      : `<a href="#/video/${encodeURIComponent(v.slug)}">${esc(v.title || v.slug)}</a> ${pill(v.status === "subido" ? "hecho" : v.status)} ${v.status === "subido" ? '<span class="small muted">subido</span>' : ""}
         ${s.pinned ? '<span class="small muted">📌 fijado</span>' : ""}
         ${s.gap && !s.past ? `<span class="small muted">${s.late ? "⏰ ya vas tarde" : "listo antes del " + DAY(s.deadline.slice(0, 10)) + " " + s.deadline.slice(11)}</span>` : ""}`;
    const choose = s.past ? "" : `<select onchange="pin(this.value, '${s.date}')"><option value="">Poner otro…</option>${free(s.channel).map((x) =>
      `<option value="${esc(x.slug)}">${esc(x.slug)} (${esc(x.status)})</option>`).join("")}</select>`;
    const done = v && v.status === "hecho" && s.date <= today ? `<button onclick="uploaded('${esc(v.slug)}')">Ya está subido</button>` : "";
    const unpin = s.pinned ? `<button onclick="pin('${esc(v.slug)}', '')">Quitar fijado</button>` : "";
    return `<div class="slot ${cls} ${s.past ? "past" : ""}"><b>${esc(s.channel)} · ${esc(s.time)}</b><span>${state}</span>
      <span style="margin-left:auto" class="row">${done}${unpin}${choose}</span></div>`;
  };
  const short = Object.entries(a.reserve).filter(([, n]) => n < st.buffer), fine = Object.keys(a.reserve).length - short.length;
  const reserve = `<div class="reserve">${short.length ? `<span class="small muted">Con pocos vídeos de reserva (objetivo ${st.buffer}):</span>
      ${short.slice(0, 8).map(([c, n]) => `<span class="pill">${esc(c)} <b style="color:var(--bad)">${n}</b></span>`).join("")}
      ${short.length > 8 ? `<span class="pill" title="${esc(short.slice(8).map(([c, n]) => c + ": " + n).join(", "))}">+${short.length - 8} más</span>` : ""}`
      : `<span class="pill hecho">✓ Todos los canales con reserva</span>`}
      ${short.length && fine ? `<span class="small muted">· ${fine} canal${fine === 1 ? "" : "es"} bien</span>` : ""}</div>`;
  const rules = Object.entries(st.schedule).map(([c, r]) => `<div class="card" style="margin-bottom:10px">
      <div class="row" style="justify-content:space-between"><b>${esc(c)}</b>
        <label style="margin:0;font-weight:400"><input type="checkbox" style="width:auto" ${r.enabled ? "checked" : ""} onchange="rule('${esc(c)}', {enabled: this.checked})"> publica en este canal</label></div>
      <div class="days" style="margin-top:8px">${a.weekdays.map((d, i) => `<label><input type="checkbox" ${r.days.includes(i) ? "checked" : ""}
        onchange="toggleDay('${esc(c)}', ${i}, this.checked)"> ${d.slice(0, 3)}</label>`).join("")}
        <input type="time" value="${esc(r.time)}" style="width:auto;margin-left:8px" onchange="rule('${esc(c)}', {time: this.value})"></div></div>`).join("");
  window.agendaRules = st.schedule;
  $("#app").innerHTML = `<h1>Calendario</h1>
    <div class="small muted">Lo que sale cada día en cada canal, y los huecos que aún no tienen vídeo.</div>
    ${reserve}
    ${Object.keys(byDay).sort().map((d) => `<div class="cal-day ${d === today ? "today" : ""}">${DAY(d)}${d === today ? " · hoy" : ""}</div>${byDay[d].map(slot).join("")}`).join("")
      || '<div class="notice">No hay días de publicación: márcalos abajo.</div>'}
    <h2>Días de publicación</h2>${rules}
    ${window.partner ? "" : `<div class="card"><div class="two">
      <div><label>Margen para tener guion y voz <span class="muted">(horas antes de publicar)</span></label>
        <input type="number" min="6" step="1" value="${st.lead_hours}" onchange="option({lead_hours: +this.value})"></div>
      <div><label>Vídeos de reserva por canal <span class="muted">(aviso si hay menos)</span></label>
        <input type="number" min="0" step="1" value="${st.buffer}" onchange="option({buffer: +this.value})"></div>
      <div><label>Hora del resumen de la mañana <span class="muted">(Telegram)</span></label>
        <input type="number" min="0" max="23" value="${st.morning_hour}" onchange="option({morning_hour: +this.value})"></div></div></div>`}`;
  window.pin = async (slug, date) => { if (!slug) return; await post("/api/agenda", {assign: slug, date}); calendarPage(); };
  window.uploaded = async (slug) => { const url = prompt("Enlace del vídeo en YouTube (para seguir sus vistas; opcional):", ""); if (url === null) return;
    try { await post(`/api/video/${encodeURIComponent(slug)}/published`, {value: true, url}); } catch (e) { return alert("No se pudo marcar: " + e.message); }
    calendarPage(); };
  window.rule = async (channel, change) => { await post("/api/agenda", {channel, ...change}); calendarPage(); };
  window.toggleDay = (channel, day, on) => { const days = new Set(window.agendaRules[channel].days); on ? days.add(day) : days.delete(day); rule(channel, {days: [...days]}); };
  window.option = async (change) => { await post("/api/agenda", change); calendarPage(); };
}

// --- Para subir: lo hecho y no subido, con todo lo que pide YouTube Studio (pipeline/organizar.py) ----------------
const copyTexts = [];
function copyBox(label, text, rows = 3) {
  const n = copyTexts.push(text) - 1;
  if (!label) return `<div class="row" style="margin:6px 0;gap:6px"><input readonly value="${esc(text)}" style="flex:1"><button onclick="copyIt(${n}, this)">Copiar</button></div>`;
  return `<div style="margin:10px 0"><div class="row" style="justify-content:space-between"><b class="small">${esc(label)}</b>
    <button onclick="copyIt(${n}, this)">Copiar</button></div>
    <textarea readonly rows="${rows}" style="min-height:0">${esc(text)}</textarea></div>`;
}
window.copyIt = async (n, button) => {
  try { await navigator.clipboard.writeText(copyTexts[n]); button.textContent = "Copiado ✓"; setTimeout(() => button.textContent = "Copiar", 1500); }
  catch (e) { button.textContent = "Selecciona y copia"; }
};
function checked(slug, step) { try { return localStorage.getItem(`subir:${slug}:${step}`) === "1"; } catch (e) { return false; } }
window.check = (slug, step, on) => { try { localStorage.setItem(`subir:${slug}:${step}`, on ? "1" : "0"); } catch (e) {} };
const UPLOAD_STEPS = [["video", "Vídeo subido"], ["title", "Título"], ["description", "Descripción"], ["thumb", "Miniatura"],
  ["subs", "Subtítulos"], ["tags", "Etiquetas"], ["schedule", "Programado a su hora"], ["comment", "Comentario fijado"],
  ["community", "Post de comunidad"], ["shorts", "Shorts"]];
let uploadChannel = (() => { try { return localStorage.getItem("subir:canal") || ""; } catch (e) { return ""; } })();
window.pickUploadChannel = (c) => { uploadChannel = c; try { localStorage.setItem("subir:canal", c); } catch (e) {} uploadPage(); };
let uploadOpenAll = false;
async function uploadPage() {
  const r = await api("/api/upload");
  copyTexts.length = 0;
  const today = new Date().toISOString().slice(0, 10);
  $("#app").innerHTML = `<h1>Para subir</h1>
    <div class="small muted" style="margin-bottom:12px">Vídeos terminados que aún no están en YouTube, por el día que les toca en el calendario.
      Copia cada parte en YouTube Studio, marca los pasos y al final pulsa «Ya está subido».</div>
    ${r.videos.length ? "" : '<div class="notice ok">No hay nada pendiente de subir. 🎉 Mira <a href="#/guiones">Guiones</a> para preparar los siguientes.</div>'}
    ${r.compilations && r.compilations.length ? `<div class="card"><b>📼 Compilaciones largas</b>
      <div class="small muted">Junta los mejores vídeos terminados de un canal en uno de 2-3 horas («3 HORAS de…»): mucho tiempo de visualización con trabajo ya hecho. Tarda ~30-60 min.</div>
      ${jobLine(r.compilationJob, "Montando la compilación")}
      <div class="row" style="gap:8px;margin-top:8px;flex-wrap:wrap">${r.compilations.map((c) =>
        `<button onclick="makeCompilation('${esc(c.channel)}', this)" ${r.compilationJob.running || c.videos < 3 ? "disabled" : ""} title="${esc(c.titles.join(" · "))}">📼 ${esc(c.channel)} (${c.videos} vídeos)</button>`).join("")}</div></div>` : ""}
    ${(() => { const chans = [...new Set(r.videos.map((v) => v.channel))].sort();
      return chans.length > 1 ? `<div class="chiprow">${["", ...chans].map((c) => `<button class="${c === uploadChannel ? "on" : ""}" onclick="pickUploadChannel('${esc(c)}')">
        ${c ? `<span class="dot" style="background:${chColor(c)};margin-right:6px"></span>${esc(c)} <span class="muted">${r.videos.filter((v) => v.channel === c).length}</span>` : "Todos"}</button>`).join("")}</div>` : ""; })()}
    ${r.videos.filter((v) => !uploadChannel || v.channel === uploadChannel).map((v, i, list) => {
      const s = v.sections || {}, f = (p) => `/files/${encodeURIComponent(v.slug)}/${p.split("/").map(encodeURIComponent).join("/")}`;
      const when = v.date ? `${DAY(v.date)} · ${esc(v.time)}` : "sin día en el calendario";
      const late = v.date && v.date < today;
      const group = !v.date ? "Sin día en el calendario" : late ? "Atrasados" : v.date === today ? "Hoy" : DAY(v.date);
      const prev = i ? list[i - 1] : null;
      const prevGroup = !prev ? null : !prev.date ? "Sin día en el calendario" : prev.date < today ? "Atrasados" : prev.date === today ? "Hoy" : DAY(prev.date);
      const done = UPLOAD_STEPS.filter(([k]) => checked(v.slug, k)).length;
      const video = v.files.find((x) => !x.image && !x.still && /video|mp4/i.test(x.label + " " + x.path));
      return `${group !== prevGroup ? `<div class="daylabel ${late ? "late" : v.date === today ? "today" : ""}">${esc(group)}</div>` : ""}
      <details class="upl" ${i === 0 && !uploadOpenAll ? "open" : ""}><summary><span class="dot" style="background:${chColor(v.channel)}"></span>
        <div style="min-width:0"><b style="font-size:1.05em">${esc(v.title || v.slug)}</b>
          <div class="small muted">${esc(v.channel)} · ${esc(v.slug)}${v.minutes ? ` · ${v.minutes} min` : ""} · <span class="mini" style="display:inline-block;width:70px;height:6px;background:var(--panel2);border-radius:99px;vertical-align:middle;overflow:hidden"><i style="display:block;height:100%;width:${Math.round(100 * done / UPLOAD_STEPS.length)}%;background:var(--ok)"></i></span> ${done}/${UPLOAD_STEPS.length} pasos</div></div>
        <span class="row" style="gap:6px;justify-content:flex-end"><span class="pill ${late ? "error" : "hecho"}">${late ? "tocaba " : ""}${when}</span>
          ${video ? `<a class="btn" href="${f(video.path)}" download onclick="event.stopPropagation()" style="padding:5px 10px;font-size:12.5px">⬇ Vídeo${video.mb ? ` (${video.mb} MB)` : ""}</a>` : ""}</span></summary><div class="in">
        <div class="small"><a href="#/video/${encodeURIComponent(v.slug)}">Abrir la ficha del vídeo →</a></div>
        <div class="row" style="flex-wrap:wrap;gap:6px;margin:12px 0">${UPLOAD_STEPS.map(([k, name]) =>
          `<label class="small" style="display:flex;gap:4px;align-items:center;font-weight:400"><input type="checkbox" style="width:auto"
            ${checked(v.slug, k) ? "checked" : ""} onchange="check('${esc(v.slug)}','${k}',this.checked)">${name}</label>`).join("")}</div>
        <div class="row" style="flex-wrap:wrap;gap:8px">${v.files.filter((x) => !x.image && !x.still).map((x) =>
          `<a class="btn" href="${f(x.path)}" download>⬇ ${esc(x.label)}${x.mb ? ` (${x.mb} MB)` : ""}</a>`).join("")}</div>
        ${v.files.some((x) => x.image) ? `<div class="row" style="gap:8px;margin-top:10px;flex-wrap:wrap">${v.files.filter((x) => x.image).map((x) =>
          `<a href="${f(x.path)}" download title="Descargar"><img src="${f(x.path)}" style="width:200px;border-radius:6px"></a>`).join("")}</div>` : ""}
        ${v.files.some((x) => x.still) ? `<div style="margin-top:12px"><b class="small">Fotogramas para tu miniatura (1920×1080, clic para descargar)</b>
          <div class="row" style="gap:8px;margin-top:6px;flex-wrap:wrap">${v.files.filter((x) => x.still).map((x) =>
          `<a href="${f(x.path)}" download title="${esc(x.label)}"><img loading="lazy" src="${f(x.path)}" style="width:160px;border-radius:6px"></a>`).join("")}</div></div>` : ""}
        ${s["IDEAS PARA LA MINIATURA"] ? copyBox("Ideas de texto para la miniatura", s["IDEAS PARA LA MINIATURA"], 3) : ""}
        ${v.titles.length ? `<div style="margin-top:10px"><b class="small">Título (elige uno)</b>${v.titles.map((t) => copyBox("", t, 1)).join("")}</div>` : ""}
        ${s["DESCRIPCIÓN"] ? copyBox("Descripción (con capítulos y fuentes)", s["DESCRIPCIÓN"], 6) : ""}
        ${s["ETIQUETAS"] ? copyBox("Etiquetas", s["ETIQUETAS"], 2) : ""}
        ${s["COMENTARIO FIJADO"] ? copyBox("Comentario fijado (publícalo y fíjalo)", s["COMENTARIO FIJADO"], 2) : ""}
        ${s["POST DE COMUNIDAD"] ? copyBox("Post de comunidad (el día de la publicación)", s["POST DE COMUNIDAD"], 3) : ""}
        ${v.shortsText ? copyBox("Shorts (títulos y textos)", v.shortsText, 4) : ""}
        <div class="row" style="margin-top:12px"><button class="main" onclick="doneUpload('${esc(v.slug)}')">Ya está subido</button></div>
      </div></details>`;
    }).join("")}`;
  window.makeCompilation = async (channel, button) => {
    if (!confirm(`¿Montar una compilación larga con los mejores vídeos de ${channel}? Saldrá aquí cuando esté (30-60 min).`)) return;
    button.disabled = true; await post("/api/compilations", {channel}); uploadPage();
  };
  if (r.compilationJob && r.compilationJob.running) schedule(uploadPage, 10000);
  window.doneUpload = async (slug) => {
    const url = prompt("Enlace del vídeo en YouTube (para seguir sus vistas a las 48 h y 7 días; opcional):", "");
    if (url === null) return;
    try { await post(`/api/video/${encodeURIComponent(slug)}/published`, {value: true, url}); } catch (e) { return alert("No se pudo marcar: " + e.message); }
    uploadPage();
  };
}

// --- Guiones: qué días del calendario siguen sin vídeo, ideas y borrador ----------------------------------------
async function scriptsPage(days = 14) {
  const r = await api(`/api/scripts?days=${days}`);
  const total = r.channels.reduce((n, c) => n + c.missing, 0);
  window.scriptIdeas = {};
  $("#app").innerHTML = `<h1>Guiones</h1>
    <div class="row" style="justify-content:space-between;margin-bottom:12px"><div class="small muted">Los días de tu calendario que aún no tienen vídeo.
      Elige una idea, pide un borrador y revísalo: al crearlo, la voz y los capítulos se hacen solos.</div>
      <select style="width:auto" onchange="scriptsPage(+this.value)">${[7, 14, 30].map((d) => `<option value="${d}" ${d === days ? "selected" : ""}>${d} días</option>`).join("")}</select></div>
    <div class="notice ${total ? "" : "ok"}">${total ? `Te faltan <b>${total}</b> guion(es) para los próximos ${days} días.` : `Los próximos ${days} días están cubiertos. 💪`}
      ${r.channels.length ? "" : ' Pon los días de publicación de cada canal en <a href="#/calendario">Calendario</a>.'}</div>
    ${r.channels.map((c) => `<div class="card">
      <div class="row" style="justify-content:space-between"><b style="font-size:1.1em">${esc(c.channel)}</b>
        <span class="pill ${c.missing ? "error" : "hecho"}">${c.missing ? `faltan ${c.missing}` : "cubierto"} · ${c.ready} en marcha o hechos</span></div>
      ${c.winners && c.winners.length ? `<div style="margin-top:10px;padding:8px;border-radius:8px;background:var(--panel2)">
        <b class="small">🏆 Lo que mejor te funciona en ${esc(c.channel)}</b>${c.winners.map((w) => `<div class="row" style="justify-content:space-between;margin-top:6px;gap:8px;flex-wrap:nowrap">
          <div class="row" style="gap:8px;flex-wrap:nowrap">${w.thumbnail ? `<img src="${esc(w.thumbnail)}" style="width:80px;border-radius:4px">` : ""}
            <div><div class="small">${esc(w.title)}</div><div class="small muted">${kfmt(w.views)} visitas${w.vsChannel ? ` · ${times(w.vsChannel)} tu media` : ""}${w.format ? ` · formato ${esc(w.format)}` : ""}</div></div></div>
          <button onclick="moreLike('${esc(w.slug)}', '${esc(c.channel)}', this)">💡 Más como este</button></div>`).join("")}
        <div id="similar-${esc(c.channel)}"></div></div>` : ""}
      ${c.empty.length ? `<div class="small" style="margin-top:10px"><b>Días sin vídeo</b><div class="datechips">${c.empty.map((x) =>
        `<span class="datechip"><b>${DAY(x.date)} · ${esc(x.time)}</b><span>guion antes del ${DAY(x.deadline.slice(0, 10))}, ${esc(x.deadline.slice(11))}</span></span>`).join("")}</div></div>` : ""}
      ${c.noScript.length ? `<div class="small" style="margin-top:4px"><b>Vídeos sin guion:</b> ${c.noScript.map((x) => `<a href="#/video/${encodeURIComponent(x.slug)}">${esc(x.slug)}</a> (${DAY(x.date)})`).join(", ")}</div>` : ""}
      ${c.missing ? `<div style="margin-top:12px"><b class="small">Ideas para ${esc(c.channel)}</b>
        ${c.ideas.length ? c.ideas.map((i) => { const id = `${c.channel}:${i.id}`; window.scriptIdeas[id] = {channel: c.channel, idea: {...(i.idea || {}), title: i.title, note: i.note}};
          return `<div class="row" style="justify-content:space-between;border-top:1px solid var(--line);padding:6px 0"><div><div>${esc(i.title)}</div>
            ${i.note ? `<div class="small muted">${esc(i.note)}</div>` : ""}</div>
            <div class="row" style="gap:6px"><button onclick="draftFrom('${esc(id)}', this)">✍️ Borrador de guion</button><button onclick="writeOwn('${esc(id)}')">Lo escribo yo</button></div></div>`; }).join("")
          : `<div class="small muted">No hay ideas para este canal: añádelas en <a href="#/tablero">Tablero</a> o búscalas en <a href="#/competencia">Competencia</a>.</div>`}
        <div class="row" style="margin-top:8px;gap:6px"><span class="small muted">Formato del borrador:</span>
          <select id="fmt-${esc(c.channel)}" style="width:auto"><option value="">— el del canal —</option>
          ${(data.formats || []).map((f) => `<option ${f === "caso-real" ? "" : ""}>${esc(f)}</option>`).join("")}</select></div>
        <div class="row" style="margin-top:8px;gap:6px"><input id="quick-${esc(c.channel)}" placeholder="Idea rápida: un título…" style="flex:1">
          <button onclick="quickDraft('${esc(c.channel)}', this)">✍️ Borrador</button></div></div>` : ""}
    </div>`).join("")}`;
  const toNew = (channel, idea, draft) => {
    const pre = {channel, idea: {...idea, title: (draft && draft.title) || idea.title, format: (draft && draft.format) || idea.format || ""},
      script: draft ? draft.script : ""};
    try { sessionStorage.setItem("prefill", JSON.stringify(pre)); } catch (e) {}
    window.prefill = pre; location.hash = "#/nuevo";
  };
  const draft = async (channel, idea, button) => {
    button.disabled = true; const label = button.textContent; button.textContent = "Escribiendo… (~1 min)";
    try {
      const d = await post("/api/scripts/draft", {channel, idea});
      if (d.check) alert(`Borrador de ${d.words} palabras. Tiene ${d.check} dato(s) marcados [COMPROBAR]: revísalos antes de crear el vídeo.`);
      toNew(channel, idea, d);
    } catch (e) { alert(e.message); button.disabled = false; button.textContent = label; }
  };
  const withFormat = (channel, idea) => { const f = (document.getElementById(`fmt-${channel}`) || {}).value;
    return f ? {...idea, format: f} : idea; };
  window.moreLike = async (slug, channel, button) => {
    button.disabled = true; button.textContent = "Pensando… (~20 s)";
    try {
      const r = await post("/api/scripts/similar", {slug});
      const box = document.getElementById(`similar-${channel}`);
      box.innerHTML = `<div class="small muted" style="margin-top:8px">Otros como «${esc(r.title)}»:</div>` + r.ideas.map((i, n) => {
        const id = `similar:${slug}:${n}`; window.scriptIdeas[id] = {channel, idea: {title: i.title, note: i.note, format: i.format}};
        return `<div class="row" style="justify-content:space-between;border-top:1px solid var(--line);padding:6px 0"><div><div>${esc(i.title)}</div>
          <div class="small muted">${esc(i.note)}</div></div><button onclick="draftFrom('${esc(id)}', this)">✍️ Borrador</button></div>`; }).join("");
      button.textContent = "💡 Más como este";
    } catch (e) { alert(e.message); button.textContent = "💡 Más como este"; }
    button.disabled = false;
  };
  window.draftFrom = (id, button) => { const x = window.scriptIdeas[id]; draft(x.channel, withFormat(x.channel, x.idea), button); };
  window.writeOwn = (id) => { const x = window.scriptIdeas[id]; toNew(x.channel, x.idea, null); };
  window.quickDraft = (channel, button) => {
    const title = document.getElementById(`quick-${channel}`).value.trim();
    if (!title) return alert("Escribe el título de la idea");
    draft(channel, withFormat(channel, {title}), button);
  };
}

// --- Biblioteca: las buenas fuentes de cada persona y tema (pipeline/library.py) -------------------------------
async function libraryPage() {
  const r = await api("/api/library");
  const people = r.entities.filter((e) => e.kind === "person"), topics = r.entities.filter((e) => e.kind !== "person");
  const tile = (e) => `<a class="card" href="#/biblioteca/${encodeURIComponent(e.key)}" style="display:block;text-decoration:none;color:inherit;margin:0">
    <b>${esc(e.name)}</b>${e.cutout ? ' <span class="small muted">· recorte</span>' : ""}
    <div class="small muted">${e.videos} vídeo(s) · ${e.photos} foto(s) · usada en ${e.inVideos} vídeo(s)</div></a>`;
  const grid = (list) => `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:10px">${list.map(tile).join("")}</div>`;
  $("#app").innerHTML = `<h1>Biblioteca</h1>
    <div class="small muted" style="margin-bottom:12px">Lo que ha funcionado de cada persona y tema. El próximo vídeo que hable de ellos parte de aquí
      (otros momentos de las mismas fuentes: nunca repite un fragmento). Se llena sola con cada vídeo terminado; «Correcta» en Errores sube una fuente.</div>
    <input id="libfilter" placeholder="Buscar persona o tema…" oninput="document.querySelectorAll('#libgrid a.card').forEach((a) => a.style.display = a.textContent.toLowerCase().includes(this.value.toLowerCase()) ? '' : 'none')">
    <div id="libgrid">
      <h2>Personas (${people.length})</h2>${people.length ? grid(people) : '<div class="small muted">Aún ninguna.</div>'}
      <h2>Temas, empresas, lugares (${topics.length})</h2>${topics.length ? grid(topics) : '<div class="small muted">Se llenan con los próximos vídeos terminados.</div>'}
    </div>`;
}
async function libraryEntity(key) {
  const e = await api(`/api/library/${encodeURIComponent(key)}`);
  $("#app").innerHTML = `<div class="small"><a href="#/biblioteca">← Biblioteca</a></div>
    <div class="row" style="justify-content:space-between"><h1>${esc(e.name)}</h1>
      <button onclick="libRemove('${esc(key)}', null)">Borrar todo</button></div>
    <div class="small muted" style="margin-bottom:12px">${e.kind === "person" ? "Persona" : "Tema"} · ${e.sources.length} fuente(s). Quita las que no quieras volver a ver con «Quitar».</div>
    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:10px">${e.sources.map((x) => `<div class="card" style="margin:0">
      ${x.clips && x.clips.length ? `<video controls muted playsinline preload="none" style="width:100%;border-radius:6px;background:#000"
          poster="${x.preview ? `/api/library/${encodeURIComponent(key)}/preview?id=${encodeURIComponent(x.id)}` : ""}"
          src="/api/library/clip?file=${encodeURIComponent(x.clips[0].file)}"></video>
        <div class="small muted">🎞 ${x.clips.length} clip(s) usados${x.clips.length > 1 ? ": " + x.clips.slice(1, 6).map((c, i) =>
          `<a href="/api/library/clip?file=${encodeURIComponent(c.file)}" target="_blank" title="${esc(c.text)}">${i + 2}</a>`).join(" ") : ""}
          · «${esc((x.clips[0].text || "").slice(0, 80))}» (${esc(x.clips[0].video)})</div>`
      : x.preview ? `<img loading="lazy" src="/api/library/${encodeURIComponent(key)}/preview?id=${encodeURIComponent(x.id)}" style="width:100%;border-radius:6px" title="miniaturas de todo el vídeo (aún sin clip guardado)">` : ""}
      <div style="margin-top:6px"><a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.title || x.id)}</a></div>
      <div class="small muted">${esc(x.channel)} · ${x.kind === "videos" ? "vídeo" : "foto"}</div>
      <div class="small">${x.used ? `✅ usada ${x.used}` : ""} ${x.approved ? `👍 buena ${x.approved}` : ""} ${x.right ? `⭐ correcta ${x.right}` : ""}
        <span class="muted">${x.videos.length ? "· " + x.videos.map(esc).join(", ") : ""}</span></div>
      <button style="margin-top:6px" onclick="libRemove('${esc(key)}', '${esc(x.id)}')">Quitar</button></div>`).join("")}</div>`;
}
window.libRemove = async (key, id) => {
  if (!confirm(id ? "¿Quitar esta fuente? No volverá a ofrecerse para este tema." : "¿Borrar toda la biblioteca de este tema?")) return;
  await post(`/api/library/${encodeURIComponent(key)}/remove`, id ? {id} : {});
  if (id) libraryEntity(key); else location.hash = "#/biblioteca";
};

// --- Tablero: de la idea al vídeo subido ---------------------------------------------------------------------------
async function boardPage() {
  const b = await api("/api/board"), names = {"idea": "💡 Ideas", "falta voz": "📝 Falta guion o voz", "en cola": "⏳ En cola", "hecho": "✅ Hecho", "subido": "📺 Subido"};
  window.boardIdeas = {};
  const card = (x) => {
    if (x.kind === "idea") {
      window.boardIdeas[x.id] = x;
      return `<div class="item"><b>${esc(x.title)}</b><div class="small muted">${esc(x.channel || "sin canal")}${x.date ? " · para el " + esc(DAY(x.date)) : ""}</div>
        ${x.note ? `<div class="small" style="margin-top:4px">${esc(String(x.note).slice(0, 160))}</div>` : ""}
        <div class="row" style="margin-top:8px"><button class="main" onclick="makeVideo('${esc(x.id)}')">Crear vídeo</button>
        <button onclick="dropIdea('${esc(x.id)}')">Quitar</button></div></div>`;
    }
    return `<div class="item"><a href="#/video/${encodeURIComponent(x.slug)}"><b>${esc(x.title || x.slug)}</b></a>
      <div class="small muted">${esc(x.channel)} · ${esc(x.status)}${x.date ? " · sale el " + esc(DAY(x.date)) : x.published ? " · " + esc(x.published) : ""}</div></div>`;
  };
  $("#app").innerHTML = `<h1>Tablero</h1>
    <div class="card" style="margin-bottom:14px"><div class="row">
      <input id="bt" placeholder="Nueva idea: título" style="flex:2;min-width:220px">
      <select id="bc" style="flex:1;min-width:140px"><option value="">canal…</option>${b.channels.map((c) => `<option>${esc(c)}</option>`).join("")}</select>
      <input id="bd" type="date" style="flex:1;min-width:150px" title="Para qué día (opcional)">
      <button class="main" onclick="addIdea()">Añadir idea</button></div>
      <input id="bn" placeholder="Notas (opcional): ángulo, gancho, fuentes…" style="margin-top:8px"></div>
    <div class="card" style="margin-bottom:14px"><div class="row">
      <b>🧪 Ideas que ya se pueden simular</b>
      <select id="tc" style="flex:1;min-width:160px">${b.channels.filter((c) => (b.kinds || {})[c] === "simulacion").map((c) => `<option>${esc(c)}</option>`).join("")}</select>
      <button class="main" id="tbtn" onclick="topicIdeas()">Llenar 10 días</button> <button id="tbtn2" onclick="topicIdeas('y-si')" title="Serie «¿Y si…?»: un mundo, un dial, una pregunta">Serie «¿Y si…?»</button><span id="tmsg" class="small muted"></span></div>
      <div class="small muted" style="margin-top:6px">Ideas de vídeo que los mundos del canal saben enseñar, una por día desde mañana, con su gancho y sus escenas.</div></div>
    <div class="kanban">${Object.entries(b.columns).map(([k, items]) => `<div class="col"><h3>${names[k] || k} <span class="muted">${items.length}</span></h3>
      ${items.map(card).join("") || '<div class="small muted" style="padding:4px">—</div>'}</div>`).join("")}</div>`;
  window.addIdea = async () => { try { await post("/api/board/idea", {title: $("#bt").value, channel: $("#bc").value, date: $("#bd").value, note: $("#bn").value}); boardPage(); }
    catch (e) { alert(e.message); } };
  window.topicIdeas = async (serie) => { $("#tbtn").disabled = true; $("#tbtn2").disabled = true; $("#tmsg").textContent = "Pensando ideas… (~30 s)";
    try { const r = await post("/api/board/temas", {channel: $("#tc").value, serie: serie || ""}); $("#tmsg").textContent = `${r.added.length} ideas añadidas`; boardPage(); }
    catch (e) { $("#tmsg").textContent = e.message; $("#tbtn").disabled = false; $("#tbtn2").disabled = false; } };
  window.dropIdea = async (id) => { if (!confirm("¿Quitar esta idea?")) return; await post("/api/board/idea", {delete: id}); boardPage(); };
  window.makeVideo = (id) => { const x = window.boardIdeas[id], idea = {...(x.idea || {}), title: x.title, ...(x.escenas ? {escenas: x.escenas} : {}), ...(x.hook && !(x.idea || {}).hook ? {hook: x.hook} : {})};
    try { sessionStorage.setItem("prefill", JSON.stringify({idea, channel: x.channel})); } catch (e) {}
    window.prefill = {idea, channel: x.channel}; location.hash = "#/nuevo"; };
}
