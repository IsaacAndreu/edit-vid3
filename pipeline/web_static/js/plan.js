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
  lazyLists.videos = data.channels;
  const channels = [...new Set(data.videos.map((v) => v.channel).filter(Boolean))].sort();     // only those with videos
  const th = (key, name, cls = "") => `<th class="${cls}" tabindex="0" aria-sort="${allSort.key === key ? (allSort.dir > 0 ? "ascending" : "descending") : "none"}" onclick="allSortBy('${key}')">${name}${allSort.key === key ? (allSort.dir > 0 ? " ▴" : " ▾") : ""}</th>`;
  const state = (v) => v.published ? `<span class="pill hecho">subido</span> <span class="small muted">${esc(String(v.published.at || "").slice(0, 10))}</span>${v.published.url ? ` <a href="${esc(v.published.url)}" target="_blank" rel="noopener">↗</a>` : ""}`
    : v.archived ? '<span class="pill">archivado</span>' : pill(v.lastError && v.status === "en cola" ? "reintento" : v.status);
  show(`<h1>Todos los vídeos</h1>
    <div class="hb mt-2"><div class="tools grow">
      <input type="search" aria-label="Buscar por nombre o título" placeholder="Buscar por nombre o título" value="${esc(f.q)}" oninput="allFilter.q=this.value;clearTimeout(window.allT);window.allT=setTimeout(allVideosPage,300)">
      <select class="w-auto" aria-label="Canal" onchange="allFilter.channel=this.value;allVideosPage()"><option value="">Todos los canales (${data.videos.length})</option>${[...channels, ...(count((v) => !v.channel) ? ["(sin canal)"] : [])].map((c) =>
        `<option value="${esc(c)}" ${f.channel === c ? "selected" : ""}>${esc(c)} (${count((v) => c === "(sin canal)" ? !v.channel : v.channel === c)})</option>`).join("")}</select>
      ${data.videos.some((v) => v.short) ? `<span class="seg">${[["", "Todo"], ["videos", "Vídeos"], ["shorts", "Shorts"]].map(([k, name]) => `<button class="${(f.kind || "") === k ? "on" : ""}" onclick="allFilter.kind='${k}';allVideosPage()">${name}</button>`).join("")}</span>` : ""}</div>
      <div class="tools mw0"><span class="seg">${["todos", "en marcha", "sin subir", "subidos", "archivados"].map((st) => `<button class="${f.state === st ? "on" : ""}" onclick="allFilter.state='${st}';allVideosPage()">${st} <span class="muted">${st === "todos" ? data.videos.length : count((v) => stateOf(v) === st)}</span></button>`).join("")}</span></div></div>
    <div class="small muted my-2">${list.length} vídeo(s). El desplegable de canal cambia dónde cuenta el vídeo (no se rehace).</div>
    <div class="card flush"><table class="vt"><thead><tr>${th("title", "Vídeo")}${th("channel", "Canal", "wide")}${th("updated", "Estado")}${th("minutes", "Dura", "r wide")}${th("cost", "API", "r wide")}</tr></thead>
      <tbody>${list.map((v) => `<tr><td class="t"><a href="#/video/${encodeURIComponent(v.slug)}">${esc(v.title || v.slug)}</a><div class="s">${esc(v.title ? v.slug : "")}</div></td>
        <td class="wide">${lazySelect("videos", v.channel || "(sin canal)", `class="sm w-auto" aria-label="Canal de ${esc(v.slug)}" onchange="post('/api/video/${encodeURIComponent(v.slug)}/channel', {channel: this.value}).then(allVideosPage).catch(oops)"`)}</td>
        <td>${state(v)}</td><td class="r wide">${v.minutes ? v.minutes + " min" : "—"}</td><td class="r wide">${v.costUsd ? v.costUsd + " $" : "—"}</td></tr>`).join("")
        || '<tr><td colspan="5" class="empty-row">Ninguno con estos filtros.</td></tr>'}</tbody></table></div>`);
}

let errFilter = "todos";
async function errorsPage() {
  const [e, o] = await Promise.all([api("/api/errors"), data && data.videos ? data : api("/api/overview")]);
  data = o;
  const done = o.videos.filter((v) => v.hasVideo).sort((a, b) => (b.updated || 0) - (a.updated || 0));
  const byVideo = Object.fromEntries(e.videos.map((v) => [v.slug, v]));
  const pending = done.filter((v) => !byVideo[v.slug]).length;
  const list = done.filter((v) => errFilter === "todos" || (errFilter === "sin revisar") === !byVideo[v.slug]);
  const maxReason = Math.max(1, ...e.reasons.map((r) => r.count));
  const acc = (r) => r.accuracy == null ? "—" : `<b class="${r.accuracy >= 90 ? "t-ok" : r.accuracy < 70 ? "t-bad" : ""}">${r.accuracy} %</b>`;
  const verdicts = (r) => `<span class="t-ok">${r.correcta}</span> · <span class="t-bad">${r.incorrecta}</span> · <span class="muted">${r.dudosa}</span>`;
  show(`<h1>Clips marcados</h1>
    <div class="small muted">Marca los clips de cada vídeo terminado (bien / mal / dudoso) y el programa aprende qué comprobaciones aflojar o apretar.</div>
    <div class="kpis">
      <div class="kpi"><div class="k">Clips bien</div><div class="v ${e.accuracy == null ? "" : e.accuracy >= 90 ? "ok" : e.accuracy < 70 ? "bad" : "warn"}">${e.accuracy == null ? "—" : e.accuracy + " %"}</div>
        <div class="d">${e.total.correcta} bien · ${e.total.incorrecta} mal · ${e.total.dudosa} dudosos</div></div>
      <div class="kpi"><div class="k">Vídeos revisados</div><div class="v">${e.videos.length} <small>/ ${done.length}</small></div>
        <div class="d">${pending ? `${pending} sin revisar` : "todos revisados"}</div></div>
      <div class="kpi"><div class="k">Fallo más común</div><div class="v txt">${e.reasons.length ? esc(e.reasons[0].name) : "—"}</div>
        <div class="d">${e.reasons.length ? `${e.reasons[0].count} clip(s)` : "sin clips marcados mal"}</div></div>
      <div class="kpi"><div class="k">Peor método</div><div class="v txt">${e.methods.length ? esc([...e.methods].sort((a, b) => a.accuracy - b.accuracy)[0].name) : "—"}</div>
        <div class="d">${e.methods.length ? `${[...e.methods].sort((a, b) => a.accuracy - b.accuracy)[0].accuracy} % de acierto` : "—"}</div></div>
    </div>
    ${e.tips.length ? `<div class="notice elf">${e.tips.map(esc).join("<br>")}</div>` : ""}
    <div class="hb"><h2>Vídeos terminados</h2>
      <span class="seg">${[["todos", `Todos <span class="muted">${done.length}</span>`], ["sin revisar", `Sin revisar <span class="muted">${pending}</span>`], ["revisados", `Revisados <span class="muted">${e.videos.length}</span>`]].map(([k, n]) =>
        `<button class="${k === errFilter ? "on" : ""}" onclick="errFilter='${k}';errorsPage()">${n}</button>`).join("")}</span></div>
    ${done.length ? `<div class="card flush"><table class="vt"><thead><tr><th>Vídeo</th><th class="wide">Canal</th><th class="wide">Clips bien · mal · dudosos</th><th class="r wide">Acierto</th><th></th></tr></thead>
      <tbody>${list.map((v) => { const r = byVideo[v.slug]; return `<tr><td class="t"><a href="#/video/${encodeURIComponent(v.slug)}">${esc(v.title || v.slug)}</a><div class="s">${esc(v.title ? v.slug : "")}<span class="ph"> · ${r ? `${verdicts(r)} · ${acc(r)}` : "sin revisar"}</span></div></td>
        <td class="wide"><span class="chan">${dot(v.channel, "sm")}${esc(v.channel || "—")}</span></td>
        <td class="wide">${r ? verdicts(r) : '<span class="muted">sin revisar</span>'}</td><td class="r wide">${r ? acc(r) : "—"}</td>
        <td class="acts t-r"><a class="btn sm ${r ? "" : "main"}" href="#/revisar/${encodeURIComponent(v.slug)}">${r ? "Clips" : "Revisar"}</a>
          <a class="btn sm" href="#/decisiones/${encodeURIComponent(v.slug)}" title="Planos donde el programa buscó otra cosa">Relleno</a></td></tr>`; }).join("")
        || '<tr><td colspan="5" class="empty-row">Ninguno con este filtro.</td></tr>'}</tbody></table></div>`
      : empty("film", "Aún no hay vídeos terminados.")}
    ${e.reasons.length || e.methods.length ? `<div class="grid2 mt-4">
      ${e.reasons.length ? `<div class="block"><div class="bh"><b>Por qué fallan los clips</b></div><div class="in">${e.reasons.map((r) => `<div class="row between nowrap small mt-2"><span>${esc(r.name)}</span><b>${r.count}</b></div>
        <div class="hbar bad"><i style="--v:${100 * r.count / maxReason}%"></i></div>`).join("")}</div></div>` : ""}
      ${e.methods.length ? `<div class="block"><div class="bh"><b>Acierto por cómo se encontró el clip</b></div><div class="scroll-x"><table class="vt"><thead><tr><th>Método</th><th class="r">Bien</th><th class="r">Mal</th><th class="r">Dudosos</th><th class="r">Acierto</th></tr></thead>
        <tbody>${[...e.methods].sort((a, b) => a.accuracy - b.accuracy).map((m) => `<tr><td>${esc(m.name)}</td><td class="r">${m.correcta}</td><td class="r">${m.incorrecta}</td><td class="r">${m.dudosa}</td><td class="r">${acc(m)}</td></tr>`).join("")}</tbody></table></div></div>` : ""}
    </div>` : ""}`);
}

// --- Calendario: días de publicación por canal y qué vídeo sale en cada uno --------------------------------------
// One grid, channels × days: a cell per slot, coloured by what it still needs, so the gaps are seen at a glance.
// The controls of a slot (another video, «ya está subido», unpin) are built only for the cell that is picked.
let calData = null, calPicked = "", calOnlyGaps = false, calRules = false;
const calKind = (s) => !s.video ? (s.past ? "none" : s.late ? "late" : "gap")
  : s.video.status === "subido" ? "up" : s.ok ? "ok" : s.late ? "late" : s.gap ? "need" : "work";
const CAL_KINDS = {gap: "hueco", late: "ya vas tarde", need: "le falta guion o voz", work: "en marcha", ok: "listo", up: "subido", none: "sin vídeo"};
async function calendarPage() {
  calData = await api("/api/agenda");
  drawCalendar();
}
window.calPick = (key) => { calPicked = calPicked === key ? "" : key; drawCalendar(); };
function drawCalendar() {
  if (!calData || location.hash !== "#/calendario") return;
  const one = (c) => !studioChannel || c === studioChannel;               // the studio's channel, if one is picked
  const a = studioChannel ? {...calData, plan: calData.plan.filter((s) => one(s.channel)), reserve: Object.fromEntries(Object.entries(calData.reserve).filter(([c]) => one(c))),
    settings: {...calData.settings, schedule: Object.fromEntries(Object.entries(calData.settings.schedule).filter(([c]) => one(c)))}} : calData;
  const st = a.settings, today = new Date().toISOString().slice(0, 10);
  const slots = {};
  a.plan.forEach((s) => slots[s.channel + "|" + s.date] = s);
  const dates = a.plan.map((s) => s.date).sort();
  const days = [];
  if (dates.length) for (let d = new Date((dates[0] < today ? dates[0] : today) + "T12:00:00"); d.toISOString().slice(0, 10) <= dates[dates.length - 1]; d.setDate(d.getDate() + 1))
    days.push(d.toISOString().slice(0, 10));
  const open = a.plan.filter((s) => !s.past && (s.gap || s.late));              // what is still missing, soonest first
  const week = new Date(today + "T12:00:00"); week.setDate(week.getDate() + 7);
  const soon = open.filter((s) => s.date < week.toISOString().slice(0, 10));
  const missing = (c) => open.some((s) => s.channel === c);
  const rows = Object.keys(st.schedule).filter((c) => a.plan.some((s) => s.channel === c) && (!calOnlyGaps || missing(c)));
  const need = (s) => s.late ? "ya vas tarde" : "antes del " + DAY(s.deadline.slice(0, 10)) + " " + s.deadline.slice(11);
  const said = (s) => `${s.channel}, ${DAY(s.date)} ${s.time}: ${s.video ? (s.video.title || s.video.slug) + ", " : ""}${CAL_KINDS[calKind(s)]}${s.pinned ? ", fijado" : ""}`;
  const head = days.map((d) => { const day = new Date(d + "T12:00:00"), n = day.getDay();
    return `<th scope="col" class="${d === today ? "today" : ""} ${n === 1 ? "wk" : ""}" title="${DAY(d)}"><span>${"DLMXJVS"[n]}</span><b>${day.getDate()}</b></th>`; }).join("");
  const cell = (c, d) => { const s = slots[c + "|" + d], n = new Date(d + "T12:00:00").getDay(), key = c + "|" + d;
    return `<td class="${n === 1 ? "wk" : ""} ${n === 0 || n === 6 ? "we" : ""}">${s ? `<button class="${calKind(s)} ${s.pinned ? "pin" : ""} ${s.past ? "past" : ""}"
      aria-pressed="${calPicked === key}" aria-label="${esc(said(s))}" title="${esc(said(s))}" onclick="calPick('${esc(key)}')"></button>` : ""}</td>`; };
  const grid = rows.length ? `<div class="card flush cal-wrap" role="region" aria-label="Calendario de publicación" tabindex="0"><table class="cal">
      <thead><tr><th scope="col" class="t-l">Canal</th><th scope="col" title="Vídeos de reserva (objetivo ${st.buffer})">Res.</th>${head}</tr></thead>
      <tbody>${rows.map((c) => { const n = a.reserve[c];
        return `<tr><th scope="row" title="${esc(c)}">${dot(c, "sm")} ${esc(c)}</th><td class="res ${n != null && n < st.buffer ? "t-bad" : "muted"}">${n ?? ""}</td>${days.map((d) => cell(c, d)).join("")}</tr>`; }).join("")}</tbody></table></div>
    <div class="legend">${Object.entries(CAL_KINDS).filter(([k]) => k !== "none").map(([k, name]) => `<span class="cal-key"><i class="${k}"></i>${name}</span>`).join("")}<span class="cal-key"><i class="ok pin"></i>fijado</span></div>`
    : calOnlyGaps && a.plan.length ? empty("check", "Ningún hueco", "Todos los días de publicación de estas cuatro semanas tienen vídeo.")
    : empty("calendar", "No hay días de publicación", "Márcalos abajo, en «Días de publicación».");
  // the picked slot: what it has, what it needs and what you can do with it
  const s = slots[calPicked];
  const free = (channel) => a.videos.filter((v) => v.channel === channel && v.status !== "subido");
  const detail = !s ? (open.length ? `<div class="card mt"><b>Próximos huecos</b> <span class="small muted">toca uno para ponerle vídeo</span>
        <div class="tools">${open.slice(0, 10).map((g) => `<button class="chip" onclick="calPick('${esc(g.channel + "|" + g.date)}')">${dot(g.channel, "sm")} ${esc(g.channel)} · <span class="${g.late ? "t-bad" : "muted"}">${DAY(g.date)}</span></button>`).join("")}
        ${open.length > 10 ? `<span class="small muted">y ${open.length - 10} más</span>` : ""}</div></div>` : "")
    : (() => { const v = s.video;
      return `<div class="cal-detail card" id="cal-detail"><div class="row between nowrap top"><div class="mw0"><b>${dot(s.channel)} ${esc(s.channel)}</b> <span class="muted">· ${DAY(s.date)}${s.date === today ? " · hoy" : ""} · ${esc(s.time)}</span>
          <div class="mt-1">${!v ? `<span class="pill error">hueco</span> <span class="small muted">${s.past ? "" : (s.late ? "ya vas tarde" : "guion y voz " + need(s))}</span>`
            : `<a href="#/video/${encodeURIComponent(v.slug)}">${esc(v.title || v.slug)}</a> ${pill(v.status === "subido" ? "hecho" : v.status)} ${v.status === "subido" ? '<span class="small muted">subido</span>' : ""}
              ${s.pinned ? `<span class="small muted">${icon("pin")} fijado</span>` : ""}
              ${s.gap && !s.past ? `<span class="small muted">${s.late ? "ya vas tarde" : "listo " + need(s)}</span>` : ""}`}</div></div>
          <button class="icon ghost" aria-label="Cerrar" onclick="calPick('')">${icon("x")}</button></div>
        <div class="tools">${v && v.status === "hecho" && s.date <= today ? `<button onclick="uploaded('${esc(v.slug)}')">Ya está subido</button>` : ""}
          ${s.pinned ? `<button onclick="pin('${esc(v.slug)}', '')">Quitar fijado</button>` : ""}
          ${s.past ? "" : `<select class="w-auto" aria-label="Poner otro vídeo en este día" onchange="pin(this.value, '${s.date}')"><option value="">Poner otro…</option>${free(s.channel).map((x) =>
            `<option value="${esc(x.slug)}">${esc(x.slug)} (${esc(x.status)})</option>`).join("")}</select>`}</div></div>`; })();
  const publishing = Object.values(st.schedule).filter((r) => r.enabled).length;
  const rules = !calRules ? "" : `<div class="scroll-x"><table class="cal-rules"><thead><tr><th>Canal</th><th>Publica</th>${a.weekdays.map((d) => `<th class="t-c" title="${esc(d)}">${esc(d.slice(0, 1).toUpperCase())}</th>`).join("")}<th>Hora</th></tr></thead>
      <tbody>${Object.entries(st.schedule).map(([c, r]) => `<tr><td>${dot(c, "sm")} ${esc(c)}</td>
        <td><input type="checkbox" aria-label="${esc(c)}: publica en este canal" ${r.enabled ? "checked" : ""} onchange="rule('${esc(c)}', {enabled: this.checked})"></td>
        ${a.weekdays.map((d, i) => `<td class="t-c"><input type="checkbox" aria-label="${esc(c)}: ${esc(d)}" ${r.days.includes(i) ? "checked" : ""} onchange="toggleDay('${esc(c)}', ${i}, this.checked)"></td>`).join("")}
        <td><input type="time" class="sm w-auto" aria-label="${esc(c)}: hora" value="${esc(r.time)}" onchange="rule('${esc(c)}', {time: this.value})"></td></tr>`).join("")}</tbody></table></div>`;
  window.agendaRules = st.schedule;
  paint($("#app"), `<div class="hb"><div><h1>Calendario</h1>
      <div class="small muted">Lo que sale cada día en cada canal, y los huecos que aún no tienen vídeo.</div></div>
      <div class="tools"><span class="seg"><button class="${calOnlyGaps ? "" : "on"}" aria-pressed="${!calOnlyGaps}" onclick="calOnlyGaps=false;drawCalendar()">Todos los canales</button><button
        class="${calOnlyGaps ? "on" : ""}" aria-pressed="${calOnlyGaps}" onclick="calOnlyGaps=true;drawCalendar()">Solo con huecos <span class="muted">${Object.keys(st.schedule).filter(missing).length}</span></button></span></div></div>
    <div class="kpis">
      <div class="kpi"><div class="k">Huecos · 7 días</div><div class="v ${soon.length ? "bad" : "ok"}">${soon.length}</div><div class="d">${open.length} en las cuatro semanas</div></div>
      <div class="kpi"><div class="k">Ya vas tarde</div><div class="v ${open.some((x) => x.late) ? "bad" : ""}">${open.filter((x) => x.late).length}</div><div class="d">pasó el margen de ${st.lead_hours} h</div></div>
      <div class="kpi"><div class="k">Listos para salir</div><div class="v">${a.plan.filter((x) => !x.past && x.ok).length}</div><div class="d">de ${a.plan.filter((x) => !x.past).length} publicaciones</div></div>
      <div class="kpi"><div class="k">Reserva</div><div class="v ${Object.values(a.reserve).some((n) => n < st.buffer) ? "warn" : "ok"}">${Object.values(a.reserve).filter((n) => n < st.buffer).length}</div>
        <div class="d">canales con menos de ${st.buffer} vídeos</div></div></div>
    ${grid}${detail}
    <details class="block" ${calRules ? "open" : ""} ontoggle="if(this.open!==calRules){calRules=this.open;drawCalendar()}"><summary><b>Días de publicación<span class="count">${publishing} de ${Object.keys(st.schedule).length} canales publican</span></b></summary>${rules}</details>
    ${window.partner ? "" : `<div class="card mt"><div class="three">
      ${field("Margen para tener guion y voz", `<input id="cal-lead" type="number" min="6" step="1" value="${st.lead_hours}" onchange="option({lead_hours: +this.value})">`, "Horas antes de publicar.", "cal-lead")}
      ${field("Vídeos de reserva por canal", `<input id="cal-buffer" type="number" min="0" step="1" value="${st.buffer}" onchange="option({buffer: +this.value})">`, "Aviso si hay menos.", "cal-buffer")}
      ${field("Hora del resumen de la mañana", `<input id="cal-morning" type="number" min="0" max="23" value="${st.morning_hour}" onchange="option({morning_hour: +this.value})">`, "Por Telegram.", "cal-morning")}</div></div>`}`);
}
window.pin = async (slug, date) => { if (!slug) return; await post("/api/agenda", {assign: slug, date}); calendarPage(); };
window.uploaded = async (slug) => { const url = await askText("Enlace del vídeo en YouTube (para seguir sus vistas; opcional):", "", {placeholder: "https://youtu.be/…", ok: "Marcar como subido"}); if (url === null) return;
  try { await post(`/api/video/${encodeURIComponent(slug)}/published`, {value: true, url}); } catch (e) { return toast("No se pudo marcar: " + e.message, "bad"); }
  calendarPage(); };
window.rule = async (channel, change) => { await post("/api/agenda", {channel, ...change}); calendarPage(); };
window.toggleDay = (channel, day, on) => { const days = new Set(window.agendaRules[channel].days); on ? days.add(day) : days.delete(day); rule(channel, {days: [...days]}); };
window.option = async (change) => { await post("/api/agenda", change); calendarPage(); };
// the arrows move between the cells of the grid
document.addEventListener("keydown", (e) => {
  const from = e.target.closest && e.target.closest(".cal button");
  const step = {ArrowLeft: [0, -1], ArrowRight: [0, 1], ArrowUp: [-1, 0], ArrowDown: [1, 0]}[e.key];
  if (!from || !step) return;
  e.preventDefault();
  const body = from.closest("tbody");
  for (let r = from.closest("tr").sectionRowIndex + step[0], c = from.parentNode.cellIndex + step[1]; body.rows[r] && body.rows[r].cells[c]; r += step[0], c += step[1]) {
    const next = body.rows[r].cells[c].querySelector("button");
    if (next) { next.focus(); break; }
  }
});

// --- Para subir: lo hecho y no subido, con todo lo que pide YouTube Studio (pipeline/organizar.py) ----------------
const copyTexts = [];
function copyBox(label, text, rows = 3) {
  let n = copyTexts.indexOf(text);                  // the same text keeps its number: a refresh changes nothing
  if (n < 0) n = copyTexts.push(text) - 1;
  const button = `<button class="sm" onclick="copyIt(${n}, this)">${icon("copy")}<span>Copiar</span></button>`;
  if (!label) return `<div class="row nowrap mt-2"><input readonly class="grow" aria-label="Texto para copiar" value="${esc(text)}">${button}</div>`;
  return `<div class="mt-4"><div class="row between mb-1"><b class="small">${esc(label)}</b>${button}</div>
    <textarea readonly class="fit" rows="${rows}" aria-label="${esc(label)}">${esc(text)}</textarea></div>`;
}
// the label is the button's last element, so its icon stays while the text changes
window.copyIt = async (n, button) => {
  const label = button.lastElementChild || button;
  try { await navigator.clipboard.writeText(copyTexts[n]); label.textContent = "Copiado ✓"; setTimeout(() => label.textContent = "Copiar", 1500); }
  catch (e) { label.textContent = "Selecciona y copia"; }
};
function checked(slug, step) { try { return localStorage.getItem(`subir:${slug}:${step}`) === "1"; } catch (e) { return false; } }
window.check = (slug, step, on) => { try { localStorage.setItem(`subir:${slug}:${step}`, on ? "1" : "0"); } catch (e) {} };
const UPLOAD_STEPS = [["video", "Vídeo subido"], ["title", "Título"], ["description", "Descripción"], ["thumb", "Miniatura"],
  ["subs", "Subtítulos"], ["tags", "Etiquetas"], ["schedule", "Programado a su hora"], ["comment", "Comentario fijado"],
  ["community", "Post de comunidad"], ["shorts", "Shorts"]];
let uploadChannel = (() => { try { return localStorage.getItem("subir:canal") || ""; } catch (e) { return ""; } })();
window.pickUploadChannel = (c) => { uploadChannel = c; try { localStorage.setItem("subir:canal", c); } catch (e) {} uploadPage(); };
let uploadOpenAll = false;
// «Descartar»: the videos marked to never upload (kept while the page refreshes; gone with what was discarded)
const uploadPicked = new Set();
function discardBar() {
  const bar = $("#discardbar");
  if (!bar) return;
  const n = uploadPicked.size;
  bar.querySelector(".n").textContent = n ? `${n} marcado${n === 1 ? "" : "s"}` : "Marca los vídeos que no vas a subir";
  bar.querySelector(".go").disabled = !n;
  bar.querySelector(".none").hidden = !n;
}
window.pickUpload = (slug, on) => { on ? uploadPicked.add(slug) : uploadPicked.delete(slug); discardBar(); };
window.pickAllUpload = (on) => {
  document.querySelectorAll("input.pick").forEach((box) => { box.checked = on; on ? uploadPicked.add(box.dataset.slug) : uploadPicked.delete(box.dataset.slug); });
  discardBar();
};
window.discardPicked = async () => {
  const slugs = [...uploadPicked];
  if (!slugs.length) return;
  if (!(await ask(`¿Descartar ${slugs.length} vídeo${slugs.length === 1 ? "" : "s"}? Se borran el vídeo final, los Shorts y todo lo que se descargó para hacerlo${slugs.length === 1 ? "" : "s"}; el guion queda en materiales/_descartados. No se puede deshacer.`, {ok: `Descartar ${slugs.length}`, danger: true}))) return;
  let r;
  try { r = await post("/api/upload/discard", {slugs}); } catch (e) { return toast("No se pudo descartar: " + e.message, "bad"); }
  r.discarded.forEach((slug) => uploadPicked.delete(slug));
  toast(`${r.discarded.length} descartado${r.discarded.length === 1 ? "" : "s"} · ${r.gb} GB liberados${r.skipped.length ? ` · ${r.skipped.length} no (se están haciendo ahora)` : ""}`, r.skipped.length ? "" : "ok");
  uploadPage();
};
window.uploadBody = (details, slug) => {
  const box = details.querySelector(".in"), make = (window.uploadBodies || {})[slug];
  if (details.open && make && !box.firstElementChild) fill(box, make());
};
async function uploadPage() {
  const r = await api("/api/upload");
  window.uploadBodies = {};
  const today = new Date().toISOString().slice(0, 10);
  show(`<h1>Para subir</h1>
    <div class="small muted">Vídeos terminados que aún no están en YouTube, por el día que les toca en el calendario.
      Copia cada parte en YouTube Studio, marca los pasos y al final pulsa «Ya está subido».</div>
    ${r.videos.length ? "" : empty("check", "No hay nada pendiente de subir.", 'Mira <a href="#/guiones">Guiones</a> para preparar los siguientes.')}
    ${r.compilations && r.compilations.length ? `<div class="card"><b>Compilaciones largas</b>
      <div class="small muted">Junta los mejores vídeos terminados de un canal en uno de 2-3 horas («3 HORAS de…»): mucho tiempo de visualización con trabajo ya hecho. Tarda ~30-60 min.</div>
      ${jobLine(r.compilationJob, "Montando la compilación")}
      <div class="row mt-3">${r.compilations.map((c) =>
        `<button onclick="makeCompilation('${esc(c.channel)}', this)" ${r.compilationJob.running || c.videos < 3 ? "disabled" : ""} title="${esc(c.titles.join(" · "))}">${icon("film")} ${esc(c.channel)} (${c.videos} vídeos)</button>`).join("")}</div></div>` : ""}
    ${(() => { const chans = [...new Set(r.videos.map((v) => v.channel))].sort();
      return chans.length > 1 ? `<div class="tools mt-4">${["", ...chans].map((c) => `<button class="chip ${c === uploadChannel ? "on" : ""}" onclick="pickUploadChannel('${esc(c)}')">
        ${c ? `${dot(c)}${esc(c)} <span class="muted">${r.videos.filter((v) => v.channel === c).length}</span>` : "Todos"}</button>`).join("")}</div>` : ""; })()}
    ${!window.partner && r.videos.length ? `<div class="row between mt-4 discardbar" id="discardbar"><span class="small muted n"></span>
      <span class="row end"><button class="sm" onclick="pickAllUpload(true)">Marcar todos</button>
        <button class="sm none" onclick="pickAllUpload(false)" hidden>Desmarcar</button>
        <button class="sm b-bad go" onclick="discardPicked()" disabled>${icon("trash")} Descartar</button></span></div>` : ""}
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
      <details class="upl" ${i === 0 && !uploadOpenAll ? "open" : ""} ontoggle="uploadBody(this, '${esc(v.slug)}')"><summary>${window.partner ? "" : `<input type="checkbox" class="pick" data-slug="${esc(v.slug)}" aria-label="Marcar para descartar: ${esc(v.title || v.slug)}" ${uploadPicked.has(v.slug) ? "checked" : ""} onclick="event.stopPropagation()" onchange="pickUpload(this.dataset.slug, this.checked)">`}${dot(v.channel)}
        <div class="mw0"><b class="lg">${esc(v.title || v.slug)}</b>
          <div class="small muted">${esc(v.channel)} · ${esc(v.slug)}${v.minutes ? ` · ${v.minutes} min` : ""} · <span class="mini ok"><i style="--v:${Math.round(100 * done / UPLOAD_STEPS.length)}%"></i></span> ${done}/${UPLOAD_STEPS.length} pasos</div></div>
        <span class="row end"><span class="pill ${late ? "error" : "hecho"}">${late ? "tocaba " : ""}${when}</span>
          ${video ? `<a class="btn sm" href="${f(video.path)}" download onclick="event.stopPropagation()">${icon("download")} Vídeo${video.mb ? ` (${video.mb} MB)` : ""}</a>` : ""}</span></summary><div class="in">${
        // what is inside a closed video is built when it is opened (60 videos × their boxes and buttons was most of the page)
        (window.uploadBodies[v.slug] = () => `
        <div class="small mt-2"><a href="#/video/${encodeURIComponent(v.slug)}">Abrir la ficha del vídeo →</a></div>
        <div class="row gap-4 small mt-3 mb-3">${UPLOAD_STEPS.map(([k, name]) =>
          `<label class="check"><input type="checkbox"
            ${checked(v.slug, k) ? "checked" : ""} onchange="check('${esc(v.slug)}','${k}',this.checked)">${name}</label>`).join("")}</div>
        <div class="row">${v.files.filter((x) => !x.image && !x.still).map((x) =>
          `<a class="btn" href="${f(x.path)}" download>${icon("download")} ${esc(x.label)}${x.mb ? ` (${x.mb} MB)` : ""}</a>`).join("")}</div>
        ${v.files.some((x) => x.image) ? `<div class="thumbs mt-3">${v.files.filter((x) => x.image).map((x) =>
          `<a href="${f(x.path)}" download title="Descargar">${thumb(f(x.path), "", x.label)}</a>`).join("")}</div>` : ""}
        ${v.files.some((x) => x.still) ? `<div class="mt-4"><b class="small">Fotogramas para tu miniatura (1920×1080, clic para descargar)</b>
          <div class="thumbs mt-2">${v.files.filter((x) => x.still).map((x) =>
          `<a href="${f(x.path)}" download title="${esc(x.label)}">${thumb(f(x.path), "", x.label)}</a>`).join("")}</div></div>` : ""}
        ${s["IDEAS PARA LA MINIATURA"] ? copyBox("Ideas de texto para la miniatura", s["IDEAS PARA LA MINIATURA"], 3) : ""}
        ${v.titles.length ? `<div class="mt-4"><b class="small">Título (elige uno)</b>${v.titles.map((t) => copyBox("", t, 1)).join("")}</div>` : ""}
        ${s["DESCRIPCIÓN"] ? copyBox("Descripción (con capítulos y fuentes)", s["DESCRIPCIÓN"], 6) : ""}
        ${s["ETIQUETAS"] ? copyBox("Etiquetas", s["ETIQUETAS"], 2) : ""}
        ${s["COMENTARIO FIJADO"] ? copyBox("Comentario fijado (publícalo y fíjalo)", s["COMENTARIO FIJADO"], 2) : ""}
        ${s["POST DE COMUNIDAD"] ? copyBox("Post de comunidad (el día de la publicación)", s["POST DE COMUNIDAD"], 3) : ""}
        ${v.shortsText ? copyBox("Shorts (títulos y textos)", v.shortsText, 4) : ""}
        <div class="actions"><button class="main" onclick="doneUpload('${esc(v.slug)}')">Ya está subido</button></div>`) && i === 0 && !uploadOpenAll ? window.uploadBodies[v.slug]() : ""}</div></details>`;
    }).join("")}`);
  window.makeCompilation = async (channel, button) => {
    if (!(await ask(`¿Montar una compilación larga con los mejores vídeos de ${channel}? Saldrá aquí cuando esté (30-60 min).`, {ok: "Montarla"}))) return;
    button.disabled = true; await post("/api/compilations", {channel}); uploadPage();
  };
  // a mark on a video that is no longer here (uploaded, discarded) goes
  for (const slug of [...uploadPicked]) if (!r.videos.some((v) => v.slug === slug)) uploadPicked.delete(slug);
  discardBar();
  if (r.compilationJob && r.compilationJob.running) schedule(uploadPage, 10000);
  window.doneUpload = async (slug) => {
    const url = await askText("Enlace del vídeo en YouTube (para seguir sus vistas a las 48 h y 7 días; opcional):", "", {placeholder: "https://youtu.be/…", ok: "Marcar como subido"});
    if (url === null) return;
    try { await post(`/api/video/${encodeURIComponent(slug)}/published`, {value: true, url}); } catch (e) { return toast("No se pudo marcar: " + e.message, "bad"); }
    uploadPage();
  };
}

// --- Guiones: qué días del calendario siguen sin vídeo, ideas y borrador ----------------------------------------
async function scriptsPage(days = 14) {
  const r = {...await api(`/api/scripts?days=${days}`)};             // a copy: the channel filter below must not touch the cached answer
  data = data || await api("/api/overview");            // the formats of the drafts (the page can be the first one opened)
  if (studioChannel) r.channels = r.channels.filter((c) => c.channel === studioChannel);   // the studio's channel, if one is picked
  const total = r.channels.reduce((n, c) => n + c.missing, 0);
  window.scriptIdeas = {};
  show(`<h1>Guiones</h1>
    <div class="row between nowrap top mb-3"><div class="small muted grow">Los días de tu calendario que aún no tienen vídeo.
      Elige una idea, pide un borrador y revísalo: al crearlo, la voz y los capítulos se hacen solos.</div>
      <select class="w-auto" aria-label="Días" onchange="scriptsPage(+this.value)">${[7, 14, 30].map((d) => `<option value="${d}" ${d === days ? "selected" : ""}>${d} días</option>`).join("")}</select></div>
    <div class="notice ${total ? "" : "ok"}">${total ? `Te faltan <b>${total}</b> guion(es) para los próximos ${days} días.` : `Los próximos ${days} días están cubiertos.`}
      ${r.channels.length ? "" : ' Pon los días de publicación de cada canal en <a href="#/calendario">Calendario</a>.'}</div>
    ${r.channels.map((c) => `<div class="card">
      <div class="row between"><b class="lg">${esc(c.channel)}</b>
        <span class="pill ${c.missing ? "error" : "hecho"}">${c.missing ? `faltan ${c.missing}` : "cubierto"} · ${c.ready} en marcha o hechos</span></div>
      ${c.winners && c.winners.length ? `<div class="cand">
        <b class="small">Lo que mejor te funciona en ${esc(c.channel)}</b>${c.winners.map((w) => `<div class="media mt-3">${w.thumbnail ? thumb(w.thumbnail, "", "") : ""}
            <div><div class="small">${esc(w.title)}</div><div class="small muted">${kfmt(w.views)} visitas${w.vsChannel ? ` · ${times(w.vsChannel)} tu media` : ""}${w.format ? ` · formato ${esc(w.format)}` : ""}</div>
          <button class="sm mt-2" onclick="moreLike('${esc(w.slug)}', '${esc(c.channel)}', this)">${icon("bulb")} Más como este</button></div></div>`).join("")}
        <div id="similar-${esc(c.channel)}"></div></div>` : ""}
      ${c.empty.length ? `<div class="small cand"><b>Días sin vídeo</b><div class="datechips">${c.empty.map((x) =>
        `<span class="datechip"><b>${DAY(x.date)} · ${esc(x.time)}</b><span>guion antes del ${DAY(x.deadline.slice(0, 10))}, ${esc(x.deadline.slice(11))}</span></span>`).join("")}</div></div>` : ""}
      ${c.noScript.length ? `<div class="small mt-2"><b>Vídeos sin guion:</b> ${c.noScript.map((x) => `<a href="#/video/${encodeURIComponent(x.slug)}">${esc(x.slug)}</a> (${DAY(x.date)})`).join(", ")}</div>` : ""}
      ${c.missing ? `<div class="cand"><b class="small">Ideas para ${esc(c.channel)}</b>
        ${c.ideas.length ? `<div>${c.ideas.map((i) => { const id = `${c.channel}:${i.id}`; window.scriptIdeas[id] = {channel: c.channel, idea: {...(i.idea || {}), title: i.title, note: i.note}};
          return `<div class="rowline row between"><div><div>${esc(i.title)}</div>
            ${i.note ? `<div class="small muted">${esc(i.note)}</div>` : ""}</div>
            <div class="row"><button class="sm" onclick="draftFrom('${esc(id)}', this)">${icon("pen")} Borrador de guion</button><button class="sm" onclick="writeOwn('${esc(id)}')">Lo escribo yo</button></div></div>`; }).join("")}</div>`
          : `<div class="small muted mt-1">No hay ideas para este canal: añádelas en <a href="#/tablero">Tablero</a> o búscalas en <a href="#/competencia">Competencia</a>.</div>`}
        <div class="row mt-3"><label class="small muted n4" for="fmt-${esc(c.channel)}">Formato del borrador:</label>
          <select id="fmt-${esc(c.channel)}" class="w-auto"><option value="">— el del canal —</option>
          ${(data.formats || []).map((f) => `<option ${f === "caso-real" ? "" : ""}>${esc(f)}</option>`).join("")}</select></div>
        <div class="row nowrap mt-2"><input id="quick-${esc(c.channel)}" class="grow" aria-label="Idea rápida para ${esc(c.channel)}" placeholder="Idea rápida: un título…">
          <button onclick="quickDraft('${esc(c.channel)}', this)">${icon("pen")} Borrador</button></div></div>` : ""}
    </div>`).join("")}`);
  const toNew = (channel, idea, draft) => {
    const pre = {channel, idea: {...idea, title: (draft && draft.title) || idea.title, format: (draft && draft.format) || idea.format || ""},
      script: draft ? draft.script : ""};
    try { sessionStorage.setItem("prefill", JSON.stringify(pre)); } catch (e) {}
    window.prefill = pre; location.hash = "#/nuevo";
  };
  const draft = async (channel, idea, button) => {
    button.disabled = true; const label = button.innerHTML; button.textContent = "Escribiendo… (~1 min)";
    try {
      const d = await post("/api/scripts/draft", {channel, idea});
      if (d.check) toast(`Borrador de ${d.words} palabras. Tiene ${d.check} dato(s) marcados [COMPROBAR]: revísalos antes de crear el vídeo.`);
      toNew(channel, idea, d);
    } catch (e) { oops(e); button.disabled = false; button.innerHTML = label; }
  };
  const withFormat = (channel, idea) => { const f = (document.getElementById(`fmt-${channel}`) || {}).value;
    return f ? {...idea, format: f} : idea; };
  window.moreLike = async (slug, channel, button) => {
    const label = button.innerHTML;
    button.disabled = true; button.textContent = "Pensando… (~20 s)";
    try {
      const r = await post("/api/scripts/similar", {slug});
      const box = document.getElementById(`similar-${channel}`);
      box.innerHTML = `<div class="small muted mt-3">Otros como «${esc(r.title)}»:</div>` + r.ideas.map((i, n) => {
        const id = `similar:${slug}:${n}`; window.scriptIdeas[id] = {channel, idea: {title: i.title, note: i.note, format: i.format}};
        return `<div class="rowline row between"><div><div>${esc(i.title)}</div>
          <div class="small muted">${esc(i.note)}</div></div><button class="sm" onclick="draftFrom('${esc(id)}', this)">${icon("pen")} Borrador</button></div>`; }).join("");
      button.innerHTML = label;
    } catch (e) { oops(e); button.innerHTML = label; }
    button.disabled = false;
  };
  window.draftFrom = (id, button) => { const x = window.scriptIdeas[id]; draft(x.channel, withFormat(x.channel, x.idea), button); };
  window.writeOwn = (id) => { const x = window.scriptIdeas[id]; toNew(x.channel, x.idea, null); };
  window.quickDraft = (channel, button) => {
    const title = document.getElementById(`quick-${channel}`).value.trim();
    if (!title) return toast("Escribe el título de la idea", "bad");
    draft(channel, withFormat(channel, {title}), button);
  };
}

// --- Biblioteca: las buenas fuentes de cada persona y tema (pipeline/library.py) -------------------------------
async function libraryPage() {
  const r = await api("/api/library");
  const people = r.entities.filter((e) => e.kind === "person"), topics = r.entities.filter((e) => e.kind !== "person");
  const tile = (e) => `<a class="card click plain" href="#/biblioteca/${encodeURIComponent(e.key)}">
    <b>${esc(e.name)}</b>${e.cutout ? ' <span class="small muted">· recorte</span>' : ""}
    <div class="small muted">${e.videos} vídeo(s) · ${e.photos} foto(s) · usada en ${e.inVideos} vídeo(s)</div></a>`;
  const grid = (list) => `<div class="cards sm">${list.map(tile).join("")}</div>`;
  show(`<h1>Biblioteca</h1>
    <div class="small muted">Lo que ha funcionado de cada persona y tema. El próximo vídeo que hable de ellos parte de aquí
      (otros momentos de las mismas fuentes: nunca repite un fragmento). Se llena sola con cada vídeo terminado; «Correcta» en Errores sube una fuente.</div>
    <div class="tools"><input id="libfilter" type="search" aria-label="Buscar persona o tema" placeholder="Buscar persona o tema…" oninput="document.querySelectorAll('#libgrid a.card').forEach((a) => a.classList.toggle('hide', !a.textContent.toLowerCase().includes(this.value.toLowerCase())))"></div>
    <div id="libgrid">
      <h2>Personas (${people.length})</h2>${people.length ? grid(people) : empty("user", "Aún ninguna.")}
      <h2>Temas, empresas, lugares (${topics.length})</h2>${topics.length ? grid(topics) : empty("inbox", "Se llenan con los próximos vídeos terminados.")}
    </div>`);
}
async function libraryEntity(key) {
  const e = await api(`/api/library/${encodeURIComponent(key)}`);
  show(`<div class="small"><a href="#/biblioteca">← Biblioteca</a></div>
    <div class="hb mt-2"><h1>${esc(e.name)}</h1>
      <button onclick="libRemove('${esc(key)}', null)">Borrar todo</button></div>
    <div class="small muted mb-3">${e.kind === "person" ? "Persona" : "Tema"} · ${e.sources.length} fuente(s). Quita las que no quieras volver a ver con «Quitar».</div>
    <div class="cards sm">${e.sources.map((x) => `<div class="card col">
      ${x.clips && x.clips.length ? `<video controls muted playsinline preload="none"
          poster="${x.preview ? `/api/library/${encodeURIComponent(key)}/preview?id=${encodeURIComponent(x.id)}` : ""}"
          src="/api/library/clip?file=${encodeURIComponent(x.clips[0].file)}"></video>
        <div class="small muted">${icon("film")} ${x.clips.length} clip(s) usados${x.clips.length > 1 ? ": " + x.clips.slice(1, 6).map((c, i) =>
          `<a href="/api/library/clip?file=${encodeURIComponent(c.file)}" target="_blank" title="${esc(c.text)}">${i + 2}</a>`).join(" ") : ""}
          · «${esc((x.clips[0].text || "").slice(0, 80))}» (${esc(x.clips[0].video)})</div>`
      : x.preview ? `<div title="miniaturas de todo el vídeo (aún sin clip guardado)">${thumb(`/api/library/${encodeURIComponent(key)}/preview?id=${encodeURIComponent(x.id)}`, "shot", "")}</div>` : ""}
      <div><a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.title || x.id)}</a>
        <div class="small muted">${esc(x.channel)} · ${x.kind === "videos" ? "vídeo" : "foto"}</div></div>
      ${x.used || x.approved || x.right ? `<div class="small row gap-4">${x.used ? `<span class="nw"><span class="t-ok">${icon("check")}</span> usada ${x.used}</span>` : ""}${x.approved ? `<span class="nw"><span class="t-ok">${icon("thumb")}</span> buena ${x.approved}</span>` : ""}${x.right ? `<span class="nw"><span class="t-warn">${icon("spark")}</span> correcta ${x.right}</span>` : ""}</div>` : ""}
      ${x.videos.length ? `<div class="small muted">${x.videos.map(esc).join(", ")}</div>` : ""}
      <div class="row"><button class="sm" onclick="libRemove('${esc(key)}', '${esc(x.id)}')">Quitar</button></div></div>`).join("")}</div>`);
}
window.libRemove = async (key, id) => {
  if (!(await ask(id ? "¿Quitar esta fuente? No volverá a ofrecerse para este tema." : "¿Borrar toda la biblioteca de este tema?", {ok: id ? "Quitar" : "Borrar", danger: true}))) return;
  await post(`/api/library/${encodeURIComponent(key)}/remove`, id ? {id} : {});
  if (id) libraryEntity(key); else location.hash = "#/biblioteca";
};

// --- Tablero: de la idea al vídeo subido ---------------------------------------------------------------------------
async function boardPage() {
  const b = await api("/api/board"), names = {"idea": "Ideas", "falta voz": "Falta guion o voz", "en cola": "En cola", "hecho": "Hecho", "subido": "Subido"};
  window.boardIdeas = {};
  const card = (x) => {
    if (x.kind === "idea") {
      window.boardIdeas[x.id] = x;
      return `<div class="item"><b>${esc(x.title)}</b><div class="small muted">${esc(x.channel || "sin canal")}${x.date ? " · para el " + esc(DAY(x.date)) : ""}</div>
        ${x.note ? `<div class="small mt-1">${esc(String(x.note).slice(0, 160))}</div>` : ""}
        <div class="row mt-2"><button class="main sm" onclick="makeVideo('${esc(x.id)}')">Crear vídeo</button>
        <button class="sm" onclick="dropIdea('${esc(x.id)}')">Quitar</button></div></div>`;
    }
    return `<div class="item"><a href="#/video/${encodeURIComponent(x.slug)}"><b>${esc(x.title || x.slug)}</b></a>
      <div class="small muted">${esc(x.channel)} · ${esc(x.status)}${x.date ? " · sale el " + esc(DAY(x.date)) : x.published ? " · " + esc(x.published) : ""}</div></div>`;
  };
  show(`<h1>Tablero</h1>
    <div class="card"><div class="fset"><div class="legend">Nueva idea</div>
      <div class="three">
        ${field("Título", '<input id="bt">', "", "bt")}
        ${field("Canal", `<select id="bc"><option value="">canal…</option>${b.channels.map((c) => `<option>${esc(c)}</option>`).join("")}</select>`, "", "bc")}
        ${field('Para qué día <span class="opt">opcional</span>', '<input id="bd" type="date">', "", "bd")}</div>
      ${field('Notas <span class="opt">opcional</span>', '<input id="bn" placeholder="Ángulo, gancho, fuentes…">', "", "bn")}
      <div class="actions"><button class="main" onclick="addIdea()">Añadir idea</button></div></div></div>
    <div class="card"><b>Ideas que ya se pueden simular</b>
      <div class="small muted">Ideas de vídeo que los mundos del canal saben enseñar, una por día desde mañana, con su gancho y sus escenas.</div>
      <div class="row mt-3"><select id="tc" class="w-md" aria-label="Canal de simulación">${b.channels.filter((c) => (b.kinds || {})[c] === "simulacion").map((c) => `<option>${esc(c)}</option>`).join("")}</select>
      <button class="main" id="tbtn" onclick="topicIdeas()">Llenar 10 días</button> <button id="tbtn2" onclick="topicIdeas('y-si')" title="Serie «¿Y si…?»: un mundo, un dial, una pregunta">Serie «¿Y si…?»</button><span id="tmsg" class="small muted"></span></div></div>
    <div class="kanban mt-4">${Object.entries(b.columns).map(([k, all]) => [k, all.filter((x) => !studioChannel || !x.channel || x.channel === studioChannel)]).map(([k, items]) => `<div class="col"><h3>${names[k] || k} <span class="muted">${items.length}</span></h3>
      ${items.map(card).join("") || '<div class="small muted">—</div>'}</div>`).join("")}</div>`);
  window.addIdea = async () => { try { await post("/api/board/idea", {title: $("#bt").value, channel: $("#bc").value, date: $("#bd").value, note: $("#bn").value}); boardPage(); }
    catch (e) { oops(e); } };
  window.topicIdeas = async (serie) => { $("#tbtn").disabled = true; $("#tbtn2").disabled = true; $("#tmsg").textContent = "Pensando ideas… (~30 s)";
    try { const r = await post("/api/board/temas", {channel: $("#tc").value, serie: serie || ""}); $("#tmsg").textContent = `${r.added.length} ideas añadidas`; boardPage(); }
    catch (e) { $("#tmsg").textContent = e.message; $("#tbtn").disabled = false; $("#tbtn2").disabled = false; } };
  window.dropIdea = async (id) => { if (!(await ask("¿Quitar esta idea?", {ok: "Quitar", danger: true}))) return; await post("/api/board/idea", {delete: id}); boardPage(); };
  window.makeVideo = (id) => { const x = window.boardIdeas[id], idea = {...(x.idea || {}), title: x.title, ...(x.escenas ? {escenas: x.escenas} : {}), ...(x.hook && !(x.idea || {}).hook ? {hook: x.hook} : {})};
    try { sessionStorage.setItem("prefill", JSON.stringify({idea, channel: x.channel})); } catch (e) {}
    window.prefill = {idea, channel: x.channel}; location.hash = "#/nuevo"; };
}

// «Puntería»: the automatic reviewer's score of each video (flagged shots per 100 with a picture), per channel, oldest
// first — lower is better. One series per channel: columns in one hue, the details on hover and in the table under it.
async function punteriaPage() {
  const p = await api("/api/punteria");
  const P = p.problems || {};
  const name = (k) => esc(P[k] || k);
  const bars = (videos) => {
    const max = Math.max(10, ...videos.map((v) => v.per100));
    const W = 640, H = 120, gap = 2, bw = Math.max(4, Math.min(28, (W - gap * videos.length) / Math.max(1, videos.length)));
    return `<svg class="pchart" viewBox="0 0 ${W} ${H + 18}" preserveAspectRatio="xMinYMid meet" role="img" aria-label="Marcados por cada 100 planos, vídeo a vídeo">
      <line x1="0" x2="${W}" y1="${H}" y2="${H}" stroke="var(--line)" stroke-width="1"/>
      ${videos.map((v, i) => { const h = Math.max(2, H * v.per100 / max), x = i * (bw + gap);
        return `<g class="pbar"><rect x="${x}" y="0" width="${bw}" height="${H}" fill="transparent"/>
          <path d="M${x} ${H}V${H - h + 4}q0-4 4-4h${Math.max(0, bw - 8)}q4 0 4 4V${H}z" fill="var(--work)"/>
          <title>${esc(v.slug)} · ${v.at} · ${v.per100} marcados por 100${v.asText != null ? ` · ${v.asText} en texto` : ""}</title></g>`; }).join("")}
      <text x="0" y="${H + 14}" class="ptick">${esc(videos[0].at.slice(0, 10))}</text>
      ${videos.length >= 4 ? `<text x="${videos.length * (bw + gap) - gap}" y="${H + 14}" class="ptick" text-anchor="end">${esc(videos[videos.length - 1].at.slice(0, 10))}</text>` : ""}</svg>`;
  };
  // objetivo-videos-referencia.md: our last video beside the channel's reference (referencias/canales/<canal>/)
  const reference = (c) => {
    if (!c.reference) return "";
    const o = c.ours || {}, r = c.reference;
    const row = (label, key, unit) => `<tr><td>${label}</td><td class="r">${o[key] ?? "—"}${o[key] != null ? unit : ""}</td>
      <td class="r">${r[key] ?? "—"}${r[key] != null ? unit : ""}</td></tr>`;
    return `<div class="tablewrap mt-2"><table class="small"><tr><th>Frente a la referencia</th>
      <th class="r">${esc(o.slug || "nuestro último")}</th><th class="r">${esc(r.file)}</th></tr>
      ${row("Segundos por corte", "cutSeconds", " s")}${row("1.ª imagen", "firstImage", " s")}
      ${row("Texto o vacío", "textShare", " %")}${row("En tarjeta sobre fondo", "cardShare", " %")}
      ${row("Rótulos por minuto", "labelsPerMinute", "")}</table></div>`;
  };
  show(`<h1>Puntería</h1>
    <div class="small muted">Lo que el revisor automático marca en cada vídeo: planos que no tienen que ver con la frase, otra persona,
      repetidos, huecos tapados… por cada 100 planos con imagen. <b>Cuanto más bajo, mejor.</b> «En texto»: planos que acabaron sin imagen
      (no cuentan como fallo, pero si suben, el vídeo enseña menos).</div>
    ${p.videos ? "" : `<div class="notice mt-3">Aún no hay notas. Se calculan solas al montar cada vídeo con <code>revisor: {nota: true}</code>
      en config.local.yaml (1-2 céntimos por vídeo), o a mano: <code>python -m pipeline.revisor &lt;vídeo&gt;</code>.</div>`}
    ${(p.channels || []).map((c) => `<section class="card mt-3"><div class="hb"><h2>${esc(c.channel)}</h2>
        <span class="small">últimos 5: <b>${c.recent}</b> por 100${c.videos.length > 1 ? ` · el primero: ${c.first}` : ""}</span></div>
      ${bars(c.videos)}
      ${reference(c)}
      <div class="tablewrap"><table class="small"><tr><th>Vídeo</th><th>Fecha</th><th class="r">Planos</th><th class="r">Por 100</th>
        <th class="r">En texto</th><th class="r" title="Parte del vídeo sin clip ni foto (pizarra, palabras o nada)">Texto o vacío</th>
        <th class="r" title="Segundo del primer clip o foto">1.ª imagen</th>
        <th class="r" title="Fuentes distintas en pantalla por minuto">Fuentes/min</th>
        <th class="r" title="Sucesos clave (planner.cobertura): funciones encontradas / pedidas">Funciones</th><th>Lo más marcado</th></tr>
        ${[...c.videos].reverse().map((v) => { const top = Object.entries(v.counts).sort((a, b) => b[1] - a[1]).slice(0, 3);
          return `<tr><td><a href="#/video/${encodeURIComponent(v.slug)}">${esc(v.slug)}</a></td><td class="nw">${esc(v.at)}</td>
          <td class="r">${v.shots}</td><td class="r"><b>${v.per100}</b></td><td class="r">${v.asText ?? "—"}</td>
          <td class="r ${v.textShare > 10 ? "t-bad" : ""}">${v.textShare != null ? v.textShare + " %" : "—"}</td>
          <td class="r ${v.firstImage > 5 ? "t-bad" : ""}">${v.firstImage != null ? v.firstImage + " s" : "—"}</td>
          <td class="r">${v.sourcesPerMinute ?? "—"}</td><td class="r">${v.functions ?? "—"}</td>
          <td>${top.map(([k, n]) => `${name(k)} ${n}`).join(" · ") || "—"}${v.sentBack ? ` <span class="muted">(${v.sentBack} corregidos antes del render)</span>` : ""}</td></tr>`; }).join("")}
      </table></div></section>`).join("")}`);
}

// «Qué hacer ahora» (pipeline/recomendar.py): empezar, doblar, dejar o cambiar — each entry with its numbers, what it
// does not know and a button. Only what was measured is a recommendation.
async function queHacerPage() {
  const r = await api("/api/recomendaciones");
  const k = (n) => n == null ? "—" : n >= 1e6 ? `${(n / 1e6).toFixed(1)} M` : n >= 1e3 ? `${Math.round(n / 1e3)} mil` : String(n);
  const unknown = (list) => list && list.length ? `<div class="small muted">No se sabe: ${list.map(esc).join(" · ")}</div>` : "";
  const job = (name) => { const j = (r.jobs || {})[name] || {}; return j.running ? `<span class="small">midiendo…</span>`
    : j.failed ? `<span class="small t-bad">falló (mira out/_tareas/${name}.log)</span>` : ""; };
  const q = r.quota;
  const start = (r.start || []).map((e) => `<div class="card mt-2"><div class="hb"><b>${esc(e.topic || "")}</b>
      <span class="small">en ${esc(e.langName)} · <b>${e.score}</b>/10 · ${esc(e.verdict || "")}</span></div>
      <div class="small">Mediana de visitas de lo más visto del año: <b>${k(e.demand)}</b> · ${e.recent ?? "—"} vídeos el último mes
        · ${e.smallWins ?? 0} canales pequeños que ganan${e.gap ? ` · hueco x${e.gap} frente al idioma de origen` : ""}
        ${e.suggestions != null ? ` · ${e.suggestions} sugerencias del autocompletado` : ""}</div>
      <div class="small">${esc(e.fit || "")} · esfuerzo: ~${e.videosPerWeek} vídeos/semana${e.costPerVideo != null ? ` a ${e.costPerVideo} $ de API cada uno` : ""}
        ${e.income != null ? ` · ~${e.income} $ por vídeo típico (con tu RPM)` : ""}${e.formula ? ` · fórmula: ${esc(e.formula)}` : ""}</div>
      ${e.why ? `<div class="small muted">${esc(e.why)}</div>` : ""}${unknown(e.unknown)}
      <div class="small muted">medido el ${esc(e.measured || "?")}</div></div>`).join("") || `<div class="muted small mt-2">Aún no hay
      temas medidos con hueco. Mide uno abajo o espera al radar de mañana.</div>`;
  const dub = (r.dub || []).map((d) => `<tr><td><b>${esc(d.channel)}</b> → ${esc(d.lang)}</td><td class="r"><b>${d.score}</b></td>
      <td>${esc(d.verdict || "")}${d.gap ? ` · x${d.gap}` : ""}</td><td class="r">${k(d.demand)}</td><td class="r">${d.readyCount}</td>
      <td class="r">${d.cost} $</td><td title="${esc(d.dependencyWhy || "")}">${esc(d.dependency)}</td></tr>`).join("");
  const checks = (r.dubChecks || []).map((c) => `<li>${esc(c.channel)} → ${esc(c.lang)} (${esc(c.dubbedChannel || "")}):
      ${esc(c.check || "")}${c.dubbedRatio != null ? ` · saca ${Math.round(c.dubbedRatio * 100)} % de las visitas del original` : ""}</li>`).join("");
  const leave = (r.leave || []).map((l) => `<div class="card mt-2"><b>${esc(l.channel)}</b>
      <div class="small">${l.reasons.map(esc).join(" · ")}</div>${unknown(l.unknown)}
      <a class="small" href="#/canal">Ver Mi canal →</a></div>`).join("") || `<div class="muted small mt-2">Ningún canal propio lo pide.</div>`;
  const learned = (r.learned || []).map((x) => `<tr><td>${esc(x.kind)} · ${esc(x.topic || x.channel || "")} → ${esc(x.lang || "")}</td>
      <td>${esc(x.date)}</td><td class="r">${k(x.predicted)}</td><td class="r">${k(x.real && x.real.median)}</td><td>${esc(x.verdict)}</td></tr>`).join("");
  show(`<h1>Qué hacer ahora</h1>
    <div class="small muted">${esc(r.signsNote || "")}${r.rpmSet ? "" : " Sin tu tabla de RPM (radar.rpm) no se calcula lo que se gana."}</div>
    ${q ? `<div class="small mt-2">Cuota de hoy para medir idiomas: ${q.unitsLeft} unidades (tope ${q.cap}, siempre quedan ${q.reserve} para la cola)
      → caben <b>${q.topicsToday}</b> tema(s) más en ${(r.languages || []).length} idiomas.</div>` : `<div class="small muted mt-2">Sin claves de la API: no se puede medir.</div>`}
    <section class="mt-3"><div class="hb"><h2>Empezar</h2>${job("huecos-idiomas")}</div>${start}
      <div class="row mt-2"><input id="qhTopic" placeholder="Un tema, p. ej. «isla de las serpientes»" style="flex:1">
        <button onclick="post('/api/recomendaciones/idiomas',{topic:document.getElementById('qhTopic').value}).then(()=>queHacerPage())">Medir en todos los idiomas</button></div></section>
    <section class="mt-3"><div class="hb"><h2>Doblar</h2><span>${job("doblar")}
      <button onclick="post('/api/recomendaciones/doblar').then(()=>queHacerPage())">Medir otra vez</button></span></div>
      ${dub ? `<div class="tablewrap"><table class="small"><tr><th>Canal → idioma</th><th class="r">Nota</th><th>Hueco</th>
        <th class="r">Mediana allí</th><th class="r">Vídeos listos</th><th class="r">Coste</th><th>Material</th></tr>${dub}</table></div>`
        : `<div class="muted small mt-2">Sin medir todavía: dale a «Medir otra vez».</div>`}
      ${checks ? `<div class="small mt-2"><b>Comprobación con los canales ya doblados</b><ul>${checks}</ul></div>` : ""}
      ${(r.dubWaiting || []).length ? `<div class="small muted">Sin medir: ${r.dubWaiting.map(esc).join(" · ")}</div>` : ""}</section>
    <section class="mt-3"><h2>Dejar o cambiar</h2>${leave}</section>
    <section class="mt-3"><div class="hb"><h2>Canal desde 5-8 vídeos de referencia</h2>${job("formula")} ${job("formula-montaje")}</div>
      <div class="small muted">Se replica la fórmula (estructura, ritmo, tipo de imagen por frase), nunca el guion, los títulos ni los clips de un vídeo.</div>
      <textarea id="fxLinks" rows="4" style="width:100%" placeholder="Pega de 5 a 8 enlaces de YouTube del mismo nicho"></textarea>
      <div class="row"><input id="fxNiche" placeholder="Nombre del nicho" style="flex:1">
        <button onclick="post('/api/formula/analizar',{links:document.getElementById('fxLinks').value,niche:document.getElementById('fxNiche').value}).then(()=>queHacerPage())">Sacar la fórmula</button></div>
      ${(r.formulas || []).map(formulaCard).join("")}</section>
    ${learned ? `<section class="mt-3"><h2>¿Acertó la nota?</h2><div class="small muted">A los 30 días y 10 vídeos del canal empezado o doblado.</div>
      <div class="tablewrap"><table class="small"><tr><th>Recomendación</th><th>Fecha</th><th class="r">Previsto</th><th class="r">Real</th><th></th></tr>${learned}</table></div></section>` : ""}`);
}

function formulaCard(f) {
  const m = f.measured || {}, mo = m.montage, it = f.interpreted || {};
  const vids = (f.videos || []).map((v) => `<tr><td>${esc(v.name || "")}</td><td class="r">${v.ratio != null ? v.ratio + "x" : "—"}</td>
    <td class="r">${v.wpm ?? "—"}</td><td class="r">${Math.round((v.duration || 0) / 60)} min</td>
    <td class="r">${v.montage ? v.montage.cutSeconds + " s" : "—"}</td><td class="r">${v.montage ? v.montage.cardShare + " %" : "—"}</td></tr>`).join("");
  const pilot = f.pilot ? `<div class="small mt-2"><b>Piloto ${esc(f.pilot.slug)}</b>${f.pilot.seen ? " · visto" : ""}<table class="small">
    ${(f.pilot.table || []).map((p) => `<tr><td>${esc(p.name)}</td><td class="r">${p.cutSeconds ?? "—"} s/corte</td><td class="r">${p.firstImage ?? "—"} s</td>
    <td class="r">${p.textShare ?? "—"} % texto</td><td class="r">${p.cardShare ?? "—"} % tarjeta</td></tr>`).join("")}</table>
    ${f.pilot.seen ? "" : `<button onclick="post('/api/formula/visto',{key:'${esc(f.key)}'}).then(()=>queHacerPage())">Lo he visto: puede entrar en el piloto automático</button>`}</div>` : "";
  return `<div class="card mt-2"><div class="hb"><b>${esc(f.niche || f.key)}</b><span class="small">${esc(f.date || "")}${f.channel ? ` · canal ${esc(f.channel)}` : ""}</span></div>
    <div class="small"><b>Medido</b>: ${esc(f.summary || "")} · títulos: ${(m.titleTraits || []).map(esc).join(", ") || "sin rasgo común"}
      · visitas ${m.ratio ?? "—"}x lo normal de su canal${mo ? ` · ${mo.firstImage} s hasta la 1.ª imagen · ${mo.textShare} % texto · ${mo.cardShare} % tarjeta` : ""}</div>
    <div class="small"><b>Interpretado por el modelo</b>: ${it.blocks ?? "—"} bloques · una promesa cada ${it.promisesEverySeconds ?? "—"} s
      · frases: ${Object.entries(it.sentenceKinds || {}).map(([k, v]) => `${esc(k)} ${v} %`).join(", ") || "—"}</div>
    ${(f.lonely || []).length ? `<div class="small muted">Solo en un vídeo (no es fórmula): ${f.lonely.map(esc).join(" · ")}</div>` : ""}
    ${(f.sources || []).length ? `<div class="small">Acreditan: ${f.sources.map(esc).join(", ")}</div>` : ""}
    <div class="tablewrap"><table class="small"><tr><th>Referencia</th><th class="r">Visitas/normal</th><th class="r">Pal./min</th><th class="r">Dura</th><th class="r">Corte</th><th class="r">Tarjeta</th></tr>${vids}</table></div>
    <div class="row mt-2">${mo ? "" : `<button onclick="formulaMontage('${esc(f.key)}')">Medir el montaje (~${f.montageMB} MB por el proxy)</button>`}
      ${f.channel ? `<input id="fxPilot-${esc(f.key)}" placeholder="vídeo piloto ya montado"><button onclick="post('/api/formula/piloto',{key:'${esc(f.key)}',slug:document.getElementById('fxPilot-${esc(f.key)}').value}).then(()=>queHacerPage())">Medir el piloto</button>`
        : `<input id="fxName-${esc(f.key)}" placeholder="nombre del canal nuevo"><button onclick="post('/api/formula/crear',{key:'${esc(f.key)}',name:document.getElementById('fxName-${esc(f.key)}').value}).then(()=>queHacerPage())">Crear canal</button>`}</div>${pilot}</div>`;
}

async function formulaMontage(key) {
  const asked = await post("/api/formula/montaje", {key});
  if (asked.needsConfirmation && !confirm(asked.message)) return;
  await post("/api/formula/montaje", {key, confirm: true});
  queHacerPage();
}

// «Material primero» (pipeline/expediente.py): first the real material of the topic is found and read, then the
// script is written from it. The list, a new one, and each video's case file.
async function materialPage() {
  const r = await api("/api/material-primero");
  const rows = (r.videos || []).map((v) => `<tr><td><a href="#/material/${encodeURIComponent(v.slug)}">${esc(v.title)}</a></td>
    <td>${esc(v.kind)}</td><td class="r">${v.count}</td><td>${v.expediente ? "expediente listo" : "investigando…"}${v.bloques ? " · guion por bloques" : ""}</td></tr>`).join("");
  show(`<h1>Material primero</h1>
    <div class="small muted">Primero se busca y se lee el material real del tema (fuentes, lo que dicen, quién habla); después se escribe
      el guion con lo encontrado. No baja vídeos: solo subtítulos.</div>
    <div class="card mt-3"><b>Nuevo</b>
      <input id="mfTitle" placeholder="Título, p. ej. «Top 5 persecuciones policiales más largas»" style="width:100%">
      <div class="row mt-2"><select id="mfKind"><option value="top">Top</option><option value="noticia">Noticia</option><option value="documental">Documental</option></select>
        <input id="mfCount" type="number" value="5" min="1" max="10" style="width:5em" title="puestos o partes">
        <input id="mfMinutes" type="number" value="6" min="2" max="30" style="width:5em" title="minutos">
        <select id="mfChannel"><option value="">sin canal</option>${(r.channels || []).map((c) => `<option>${esc(c)}</option>`).join("")}</select></div>
      <textarea id="mfLinks" rows="3" style="width:100%" placeholder="Opcional: un enlace de YouTube por puesto, en orden"></textarea>
      <button onclick="materialNew()">Investigar</button></div>
    ${rows ? `<div class="tablewrap mt-3"><table class="small"><tr><th>Vídeo</th><th>Tipo</th><th class="r">Puestos</th><th>Estado</th></tr>${rows}</table></div>` : ""}`);
  let pre = null;                            // coming from «Desde un título»: its title and links
  try { pre = JSON.parse(sessionStorage.getItem("materialPrefill") || "null"); sessionStorage.removeItem("materialPrefill"); } catch (e) {}
  if (pre) {
    document.getElementById("mfTitle").value = pre.title || "";
    document.getElementById("mfLinks").value = (pre.links || []).join("\n");
    if (pre.channel) document.getElementById("mfChannel").value = pre.channel;
  }
}

async function materialNew() {
  const v = (id) => document.getElementById(id).value;
  const res = await post("/api/material-primero/nuevo", {title: v("mfTitle"), kind: v("mfKind"), count: +v("mfCount"),
    minutes: +v("mfMinutes"), channel: v("mfChannel"), links: v("mfLinks").split(/\s+/).filter(Boolean)});
  location.hash = `#/material/${encodeURIComponent(res.slug)}`;
}

async function materialVideoPage(slug) {
  const r = await api(`/api/material-primero/${encodeURIComponent(slug)}`);
  const e = r.expediente, jobs = r.jobs || {};
  const running = (jobs.expediente || {}).running;
  const t = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
  const who = (sp) => !sp ? "" : `<b>${esc(sp.name || "")}</b>${sp.name ? " · " : ""}${esc(sp.role)} <span class="muted">(${esc(sp.evidence || "")},
    seguridad ${Math.round((sp.confidence || 0) * 100)} %)</span>${sp.droppedName ? ` <span class="t-bad" title="El modelo dio este nombre pero no está escrito ni dicho en la fuente: no saldrá">· nombre descartado: ${esc(sp.droppedName)}</span>` : ""}`;
  let segN = 0;                                    // the same ids as the blocks (t1, t2… in this order)
  const seg = (src, s) => `<tr><td class="nw muted">t${++segN}</td><td class="nw"><a href="${esc(src.url)}&t=${Math.floor(s.start)}" target="_blank">${t(s.start)}-${t(s.end)}</a></td>
    <td>${esc(s.type)}</td><td>${esc(s.seen || "")}${s.fact ? `<div><b>dato:</b> ${esc(s.fact)}</div>` : ""}</td>
    <td>${s.said ? `«${esc(s.said.slice(0, 220))}${s.said.length > 220 ? "…" : ""}»` : ""}<div class="small">${who(s.speaker)}</div></td></tr>`;
  const items = !e ? "" : e.items.map((it) => `<section class="card mt-3"><div class="hb"><h2>${it.n}. ${esc(it.name)}</h2>
      <span class="small muted">${esc(it.whereWhen || "")}</span></div>
      ${it.sources.map((src) => `<div class="mt-2"><b><a href="${esc(src.url)}" target="_blank">${esc(src.title || src.id)}</a></b>
        <span class="small"> · ${esc(src.channel || "")} · ${esc(src.kind || "")} · ${Math.round((src.duration || 0) / 60)} min
        · subtítulos: ${esc(src.subtitles || "no")}${src.eventMatch != null ? ` · de este suceso: ${Math.round(src.eventMatch * 100)} %` : ""}</span>
        ${src.note ? `<div class="small muted">${esc(src.note)}</div>` : ""}
        ${src.segments.length ? `<div class="tablewrap"><table class="small">${src.segments.map((s) => seg(src, s)).join("")}</table></div>` : ""}</div>`).join("")
      || `<div class="small muted">Ninguna fuente encontrada.</div>`}</section>`).join("");
  const sum = e ? e.summary.items.map((s) => `<tr><td>${s.n}. ${esc(s.name)}</td><td class="r">${s.sources}</td><td class="r">${s.statements}</td>
    <td class="r">${s.named}</td><td class="r">${s.footageSeconds} s</td><td class="r">${s.facts}</td></tr>`).join("") : "";
  show(`<h1>${esc(e ? e.title : slug)}</h1>
    <div class="row"><a href="#/material">← Material primero</a>
      <button onclick="post('/api/material-primero/${encodeURIComponent(slug)}/investigar').then(()=>materialVideoPage('${esc(slug)}'))">Investigar otra vez</button>
      ${e ? `<button onclick="post('/api/material-primero/${encodeURIComponent(slug)}/bloques').then(()=>materialVideoPage('${esc(slug)}'))">Escribir el guion por bloques</button>` : ""}</div>
    ${running ? `<div class="notice mt-2">Investigando… (recarga en un rato)</div>` : ""}
    ${e ? `<div class="tablewrap mt-3"><table class="small"><tr><th>Puesto</th><th class="r">Fuentes</th><th class="r">Declaraciones</th>
      <th class="r">…con nombre de la fuente</th><th class="r">Metraje</th><th class="r">Datos</th></tr>${sum}</table></div>
      ${e.summary.weak.length ? `<div class="small t-bad">Poco material: ${e.summary.weak.map(esc).join(", ")}</div>` : ""}
      ${(e.notes || []).length ? `<div class="small muted">${e.notes.map(esc).join(" · ")}</div>` : ""}
      <div class="small muted">Unidades de API: ${e.apiUnits}</div>` : (running ? "" : `<div class="muted mt-2">Aún no hay expediente.</div>`)}
    ${(jobs.montar || {}).running ? `<div class="notice mt-2">Montando… (bajar, comprobar, voz, render: puede tardar una hora)</div>` : ""}
    ${(jobs.montar || {}).failed ? `<div class="notice mt-2 t-bad">El montaje falló: ${esc(((jobs.montar || {}).log || "").slice(-300))}</div>` : ""}
    ${r.montaje ? `<div class="card mt-3"><b>Montado</b>: ${r.montaje.seconds} s · ${r.montaje.clips} tramos · gancho de ${r.montaje.hookCuts} cortes
      · declaraciones comprobadas: ${Object.values(r.montaje.statementsChecked || {}).filter((v) => v >= 0.55).length} de ${Object.keys(r.montaje.statementsChecked || {}).length}
      ${r.hasVideo ? ` · <a href="#/video/${encodeURIComponent(slug)}">ver el vídeo</a>` : ""}</div>` : ""}
    ${typeof bloquesView === "function" && r.bloques ? bloquesView(slug, r.bloques) : ""}
    ${items}`);
}

// The script by blocks (pipeline/bloques.py), seen and edited before any money goes to voice and downloads.
function bloquesView(slug, b) {
  const e = b.estimate || {};
  const label = {narrador: "Narrador", declaracion: "Declaración", secuencia: "Secuencia", tarjeta: "Tarjeta"};
  const act = (i, action) => `post('/api/material-primero/${encodeURIComponent(slug)}/bloque',{position:${i},action:'${action}'${action === "cambiar" ? `,ref:prompt('Id del tramo de la otra declaración (t1, t2…)')` : ""}}).then(()=>materialVideoPage('${esc(slug)}'))`;
  const body = (x) => x.type === "narrador" ? `${esc(x.text)} ${x.refs.length ? `<span class="muted">[${x.refs.map(esc).join(", ")}]</span>` : `<span class="muted">(conecta)</span>`}`
    : x.type === "tarjeta" ? `<b>${x.number != null ? `#${x.number} ` : ""}${esc(x.title || "")}</b>`
    : `<a href="${esc(x.url || "")}&t=${Math.floor(x.start)}" target="_blank">${esc(x.channel || x.source)} ${Math.floor(x.start)}-${Math.floor(x.end)} s</a>`
      + (x.type === "declaracion" ? ` · <b>${esc(x.speaker || "")}</b>${x.speaker ? " · " : ""}${esc(x.role)}: «${esc(x.said)}»${x.translation ? `<div class="muted">${esc(x.translation)}</div>` : ""}` : "");
  return `<section class="card mt-3"><div class="hb"><h2>Guion por bloques</h2><span class="small">${e.minutes} min · voz ajena ${Math.round((e.otherVoiceShare || 0) * 100)} %
      · ${e.clips} tramos a bajar: <b>~${e.downloadMB} MB por el proxy</b></span></div>
    ${b.criterion ? `<div class="small">Orden: ${esc(b.criterion)}</div>` : ""}
    ${(b.notes || []).length ? `<div class="small t-bad">${b.notes.map(esc).join(" · ")}</div>` : ""}
    <div class="row mt-2"><button class="main" onclick="if(confirm('Va a bajar unos ${e.downloadMB} MB por el proxy y a gastar en la voz del narrador. ¿Seguimos?'))post('/api/material-primero/${encodeURIComponent(slug)}/montar',{confirm:true}).then(()=>materialVideoPage('${esc(slug)}'))">Montar el vídeo</button>
      <span class="small muted">Baja los tramos, comprueba cada declaración, pone la voz al narrador, monta el gancho y renderiza.</span></div>
    <div class="tablewrap"><table class="small">${(b.blocks || []).map((x, i) => `<tr><td class="nw">${label[x.type] || x.type}</td><td>${body(x)}</td>
      <td class="nw"><button class="small" onclick="${act(i, "quitar")}">Quitar</button>${x.type === "declaracion" ? ` <button class="small" onclick="${act(i, "cambiar")}">Cambiar</button>` : ""}</td></tr>`).join("")}</table></div></section>`;
}
