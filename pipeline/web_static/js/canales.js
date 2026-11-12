// --- Canales: the health of every channel at a glance (web.channels_health) ----------------------------------------
let chanFilter = "todos", chanSort = "urgente";
const CHAN_FILTERS = [["todos", "Todos"], ["huecos", "Con huecos"], ["reserva", "Sin reserva"], ["errores", "Con errores"]];
const chanState = (c) => !c.publishes ? ["no publica", ""] : c.late ? ["va tarde", "error"] : c.errors ? [c.errors === 1 ? "1 error" : `${c.errors} errores`, "error"]
  : c.reserve != null && c.reserve < c.buffer ? ["sin reserva", "warn"] : c.gaps ? [c.gaps === 1 ? "1 hueco" : `${c.gaps} huecos`, "warn"] : ["bien", "hecho"];
const chanUrgency = (c) => (c.late * 100 + c.errors * 20 + c.gaps * 5 + Math.max(0, (c.buffer || 0) - (c.reserve || 0)) * 3) * (c.publishes ? 1 : 0.01);

async function canalesPage() {
  const r = await api("/api/canales");
  const passes = (c, k = chanFilter) => k === "todos" || (k === "huecos" ? c.gaps > 0 : k === "reserva" ? c.publishes && c.reserve != null && c.reserve < c.buffer : c.errors > 0);
  const counts = Object.fromEntries(CHAN_FILTERS.map(([k]) => [k, r.channels.filter((c) => passes(c, k)).length]));
  const list = r.channels.filter((c) => (!studioChannel || c.channel === studioChannel) && passes(c))
    .sort((a, b) => chanSort === "nombre" ? a.channel.localeCompare(b.channel) : chanSort === "visitas" ? b.views - a.views : chanUrgency(b) - chanUrgency(a) || a.channel.localeCompare(b.channel));
  const days = (c) => c.days.length === 7 ? "a diario" : c.days.map((d) => (r.weekdays[d] || "").slice(0, 3)).join(" ") || "—";
  const SLOT = {ok: "listo", work: "en marcha", gap: "hueco", late: "ya vas tarde"};
  const card = (c) => {
    const [state, tone] = chanState(c), top = Math.max(1, ...c.weeks);
    const trend = c.trend == null ? "" : `<span class="${c.trend >= 0 ? "t-ok" : "t-bad"} small" title="Las 4 últimas semanas frente a las 4 anteriores">${c.trend >= 0 ? "▲" : "▼"} ${c.trend > 2 ? "×" + fmt(1 + c.trend) : Math.abs(Math.round(100 * c.trend)) + " %"}</span>`;
    return `<article class="card chcard">
      <div class="row nowrap">${avatar(c.channel)}
        <div class="grow mw0"><button class="linkbtn b" onclick="setStudioChannel('${esc(c.channel)}');location.hash='#/'">${esc(c.channel)}</button>
          <div class="small muted">${esc({metraje: "Metraje", simulacion: "Simulación", stickman: "Monigotes", mapas: "Mapas"}[c.kind] || c.kind)} · ${c.publishes ? `publica ${esc(days(c))}${c.time ? " · " + esc(c.time) : ""}` : "sin días de publicación"}</div></div>
        <span class="pill ${tone}">${state}</span></div>
      <div class="cols3 chstats">
        <div><span>Reserva</span><b class="${c.publishes && c.reserve != null && c.reserve < c.buffer ? "t-bad" : ""}">${c.reserve ?? "—"}${c.reserve != null ? `<small> / ${c.buffer}</small>` : ""}</b></div>
        <div><span>En marcha</span><b>${c.making + c.queued}</b>${c.missing ? `<small class="t-warn">${c.missing} sin guion o voz</small>` : ""}</div>
        <div><span>Visitas</span><b>${kfmt(c.views)}</b>${trend}</div></div>
      <div><div class="row between small muted mb-1"><span>Próximas 2 semanas</span><span class="${c.late || c.gaps ? "t-bad" : ""}">${c.late ? `${c.late} ya tarde` : c.gaps ? `${c.gaps} sin vídeo` : c.publishes ? "todo cubierto" : ""}</span></div>
        <div class="strip14">${c.next.map((d) => `<span class="${d.kind || "none"}" title="${esc(DAY(d.date))}${d.kind ? ": " + SLOT[d.kind] : ""}${d.video ? " · " + esc(d.video) : ""}"></span>`).join("")}</div></div>
      <div><div class="small muted mb-1">Visitas de lo subido cada semana · 8 semanas</div>
        <div class="weeks" style="--c:${chColor(c.channel)}" role="img" aria-label="Visitas por semana: ${c.weeks.map(kfmt).join(", ")}">${c.weeks.map((w, i) => `<i class="${i === 7 ? "now" : ""}" style="--v:${Math.max(w ? 6 : 2, Math.round(100 * w / top))}%" title="${kfmt(w)}"></i>`).join("")}</div></div>
      <div class="actions mt-0"><a class="btn sm" href="#/calendario" onclick="setStudioChannel('${esc(c.channel)}')">${icon("calendar")} Calendario</a>
        ${c.gaps ? `<a class="btn sm" href="#/guiones" onclick="setStudioChannel('${esc(c.channel)}')">${icon("pen")} Guiones</a>` : ""}
        <a class="btn sm" href="#/canal" onclick="setStudioChannel('${esc(c.channel)}')">${icon("trend")} Mi canal</a></div>
    </article>`;
  };
  show(`<div class="hb"><div><h1>Canales</h1><div class="small muted">La salud de cada canal de un vistazo: reserva, próximas publicaciones, lo que está en marcha y cómo van sus vídeos.</div></div>
      <div class="tools"><span class="seg">${CHAN_FILTERS.map(([k, n]) => `<button class="${chanFilter === k ? "on" : ""}" aria-pressed="${chanFilter === k}" onclick="chanFilter='${k}';canalesPage()">${n} <span class="muted">${counts[k]}</span></button>`).join("")}</span>
        <select class="w-auto" aria-label="Ordenar" onchange="chanSort=this.value;canalesPage()">${[["urgente", "Lo urgente primero"], ["nombre", "Por nombre"], ["visitas", "Más visitas"]].map(([k, n]) => `<option value="${k}" ${chanSort === k ? "selected" : ""}>${n}</option>`).join("")}</select></div></div>
    ${studioChannel ? `<div class="notice small">Solo <b>${esc(studioChannel)}</b>, el canal elegido en el menú. <button class="sm" onclick="setStudioChannel('')">Ver todos</button></div>` : ""}
    ${list.length ? `<div class="cards chgrid">${list.map(card).join("")}</div>` : empty("check", "Ningún canal con esto", "Prueba con otro filtro.")}
    <div class="legend mt-4"><span class="strip14 key"><span class="ok"></span></span>listo o subido <span class="strip14 key"><span class="work"></span></span>en marcha
      <span class="strip14 key"><span class="gap"></span></span>hueco <span class="strip14 key"><span class="late"></span></span>ya vas tarde <span class="strip14 key"><span class="none"></span></span>no publica ese día</div>`);
  schedule(canalesPage, 60000);
}
