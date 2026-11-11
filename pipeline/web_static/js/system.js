// «Gasto de API»: per channel and per video (pipeline/gasto.py); averages only over finished videos
let spendSort = "last", spendChannel = "", invoiceMonth = "";

async function doctorCard(refresh) {
  const d = await api("/api/doctor" + (refresh ? "?refresh=1" : "")).catch(() => null), box = $("#doctor");
  if (!d || !box) return;
  const mark = {ok: `<span class="t-ok">${icon("check", "Bien")}</span>`, aviso: `<span class="t-warn">${icon("alert", "Aviso")}</span>`,
    error: `<span class="t-bad">${icon("x", "Error")}</span>`}, bad = d.rows.filter((r) => r.level !== "ok");
  box.innerHTML = `<div class="card side" style="--c:${bad.some((r) => r.level === "error") ? "var(--bad)" : bad.length ? "var(--accent)" : "var(--ok)"}">
    <div class="row between"><b>Chequeo ${bad.length ? `· ${bad.length} aviso(s)` : "· todo listo"}</b>
    <button onclick="doctorCard(true)">${icon("refresh")} Revisar ahora</button></div>
    ${(bad.length ? bad : d.rows).map((r) => `<div class="small mt-1">${mark[r.level]} <b>${esc(r.area)}</b>: ${esc(r.text)}</div>`).join("")}
    <div class="small muted mt-2">${new Date(d.at * 1000).toLocaleTimeString("es-ES")} · sin peticiones a YouTube ni a las IAs</div></div>`;
}

async function serverPage() {
  const [s, px] = await Promise.all([api("/api/servidor"), api("/api/proxy?days=7").catch(() => null)]);
  const m = s.machine || {}, a = s.api, p = s.proxy, b = s.backup;
  const bar = (x, of, warn) => `<div class="bar ${(x || 0) / Math.max(0.01, of || 0) > warn ? "bad" : "acc"}"><i style="--v:${Math.min(100, 100 * (x || 0) / Math.max(0.01, of || 0))}%"></i></div>`;
  const kinds = {haciendo: "haciendo", turno: "", cuota: "", youtube: "error", cola: "", error: "error", falta: "", pausa: ""};
  $("#app").innerHTML = `<h1>Estado del servidor</h1>
    <div class="small muted">Se actualiza solo cada 15 s · ${esc(s.at)}</div>
    <div id="doctor"></div>
    <h2>Máquina</h2>
    <div class="kpis">
      <div class="kpi"><div class="k">RAM</div><div class="v">${fmt(m.ramUsed)} / ${fmt(m.ramTotal)} GB</div>
        <div class="d">${m.swapUsed != null ? `swap ${fmt(m.swapUsed)} GB` : ""}</div>${bar(m.ramUsed, m.ramTotal, 0.85)}</div>
      <div class="kpi"><div class="k">CPU</div><div class="v">${m.cpu != null ? Math.round(m.cpu) + " %" : "—"}</div>
        <div class="d">${m.cores} núcleos${m.load != null ? ` · carga ${fmt(m.load)}` : ""}</div>${bar(m.cpu, 100, 0.95)}</div>
      <div class="kpi"><div class="k">Disco libre</div><div class="v">${fmt(m.diskFree)} GB</div>
        <div class="d">de ${fmt(m.diskTotal)} GB</div>${bar((m.diskTotal || 0) - (m.diskFree || 0), m.diskTotal, 0.9)}</div></div>
    <h2>API de YouTube</h2>
    ${a ? `<div class="kpis">
      <div class="kpi"><div class="k">Búsquedas hoy</div><div class="v">${fmt(a.searches)} / ${fmt(a.searchesPerDay)}</div>
        <div class="d">quedan ${fmt(a.searchesLeft)} · ${fmt(a.perHour)}/hora · ${a.keys} claves</div>${bar(a.searches, a.searchesPerDay, 0.9)}</div>
      <div class="kpi"><div class="k">Se acaba</div><div class="v txt">${esc(a.runsOut || "—")}</div><div class="d">al ritmo de hoy</div></div>
      <div class="kpi"><div class="k">Se renueva</div><div class="v txt">${esc(a.reset)}</div><div class="d">hora de España</div></div></div>`
      : '<div class="card muted">Sin claves de la API de YouTube.</div>'}
    ${proxySection(px)}
    ${p ? `<h2>Proxy de metadatos (saldo apuntado)</h2><div class="kpis">
      <div class="kpi"><div class="k">Queda</div><div class="v">${p.leftGb != null ? fmt(p.leftGb) + " GB" : "—"}</div>
        <div class="d">${p.videosLeft != null ? `≈ ${p.videosLeft} vídeos` : "apunta abajo los GB comprados"}</div>${p.bought ? bar(p.usedGb, p.bought, 0.85) : ""}</div>
      <div class="kpi"><div class="k">Gastado${p.since ? " desde " + esc(p.since) : ""}</div><div class="v">${fmt(p.usedGb)} GB</div>
        <div class="d">${fmt(p.requests)} peticiones · ${p.videos} vídeos · ${fmt(p.perVideoGb)} GB/vídeo</div></div></div>
      <form class="tools mt-3" onsubmit="event.preventDefault();post('/api/settings',{proxy_gb:this.gb.value,proxy_since:this.day.value}).then(serverPage)">
        <div class="unit"><label for="px-gb">Recarga: GB comprados</label><input id="px-gb" name="gb" inputmode="decimal" value="${p.bought ?? ""}"></div>
        <label for="px-day">el día</label><input id="px-day" name="day" type="date" class="w-auto" value="${esc(p.since || new Date().toISOString().slice(0, 10))}">
        <button>Guardar</button></form>
      <p class="help">Estimado con las peticiones de cada vídeo (el proveedor no da el saldo por API): si no cuadra con su panel, apunta allí lo que queda como una recarga de hoy. Avisa por Telegram cuando queden menos de 10 vídeos.</p>`
      : ""}
    <h2>Conexiones a YouTube</h2>
    <div class="card rows">${(s.ways || []).map((w) => `<div class="rowline">
        <div class="row between nowrap"><b class="break">${esc(w.name)}</b>
        <span class="pill ${w.state === "libre" ? "hecho" : "error"}">${esc(w.state)}</span></div>
        <div class="small muted">última hora ${fmt(w.hour)}${w.perHour ? " / " + fmt(w.perHour) : ""} peticiones</div></div>`).join("")}</div>
    <h2>Cola</h2>
    ${(s.queue || []).length ? `<div class="card rows">${s.queue.map((v) => `<a class="rowline" href="#/video/${encodeURIComponent(v.slug)}">
        <div class="row between nowrap"><span class="row gap-2 grow">${dot(v.channel)}
          <b>${esc(v.slug)}</b> <span class="small muted">${esc(v.channel)}</span></span>
          <span class="pill ${kinds[v.kind] || ""}">${esc(v.kind)}</span></div>
        <div class="small mt-1">${esc(v.why)}</div></a>`).join("")}</div>`
      : empty("inbox", "No hay vídeos pendientes")}
    <h2>Copia de seguridad</h2>
    <div class="card">${b ? `Última: <b>${esc(b.name)}</b> · ${fmt(b.mb)} MB · ${new Date(b.at * 1000).toLocaleString("es-ES")}
        <div class="small muted">En ${esc(b.folder)} del servidor. Lleva tus claves (.env): guárdala en un sitio privado.</div>`
        : '<span class="muted">Aún no hay ninguna (se hace sola cada semana).</span>'}
      <div class="actions">${b ? `<a class="btn" href="/api/copia">${icon("download")} Descargar</a>` : ""}
        <button onclick="this.disabled=true;this.textContent='Haciendo copia…';post('/api/copia').then(serverPage).catch((e)=>{alert(e.message||e);serverPage()})">Hacer copia ahora</button></div></div>`;
  doctorCard();
  schedule(serverPage, 15000);
}

// The paid proxy, last days: one card that says whether YouTube downloads are healthy and what they cost
function proxySection(px, title = "Proxy") {
  if (!px || !px.proxies.length) return `<h2>${title}</h2><div class="card muted small">Sin peticiones por proxy en los últimos ${px ? px.days : 7} días.</div>`;
  const main = px.proxies.slice().sort((a, b) => b.requests - a.requests)[0];
  const share = main.ok_share, col = share >= 85 ? "ok" : share >= 60 ? "warn" : "bad";
  const maxDay = Math.max(0.01, ...px.perDay.map((d) => d.gb));
  const e = main.errors || {};
  return `<h2>${title} · últimos ${px.days} días</h2>
    <div class="kpis">
      <div class="kpi"><div class="k">Éxito</div><div class="v ${col}">${share} %</div><div class="d">${main.requests} peticiones por ${esc(main.proxy)}${main.sessions ? ` · ${main.sessions} sesiones` : ""}</div></div>
      <div class="kpi"><div class="k">GB por el proxy</div><div class="v">${px.totalGb.toFixed(2)}</div><div class="d">≈ ${px.usd.toFixed(2)} $ a ${px.usdPerGb} $/GB</div></div>
      <div class="kpi"><div class="k">Por vídeo terminado</div><div class="v">${px.gbPerFinished != null ? px.gbPerFinished.toFixed(2) + " GB" : "—"}</div>
        <div class="d">${px.finished} terminados de ${px.videos} con descargas${px.gbPerFinished != null ? ` · ${(px.gbPerFinished * px.usdPerGb).toFixed(2)} $/vídeo` : ""}</div></div>
      <div class="kpi"><div class="k">Errores</div><div class="v txt">${["bot", "403", "429", "timeout"].filter((k) => e[k]).map((k) => `${e[k]} ${k === "bot" ? "bot" : k}`).join(" · ") || "ninguno"}</div>
        <div class="d">${e.other ? `${e.other} otros` : "bot = «no eres un bot»"}</div></div></div>
    ${px.perDay.length > 1 ? `<div class="card mt-3"><div class="small muted">GB por día</div>
      <div class="spend sm">${px.perDay.map((d) => `<div style="--v:${Math.max(2, 100 * d.gb / maxDay)}%" title="${d.day}: ${d.gb.toFixed(2)} GB"><span>${d.day.slice(5)}</span></div>`).join("")}</div></div>` : ""}
    ${main.details && main.details.length ? `<div class="card small mt-3"><b>Errores más frecuentes</b><ul>${main.details.map(([t, n]) => `<li>${n}× ${esc(t)}</li>`).join("")}</ul></div>` : ""}`;
}

// «Factura»: each person's month (you see everyone, a partner only their own), with a CSV to send
function invoiceBlock(g, usd) {
  const months = g.invoices || [];
  if (!months.length) return "";
  const m = months.find((x) => x.month === invoiceMonth) || months[0];
  const name = (w) => w ? esc(w) : "Tú";
  return `<h2>${window.partner ? "Tu factura del mes" : "Factura por persona"}</h2>
    <div class="tools">${months.map((x) => `<button class="chip ${x.month === m.month ? "on" : ""}" onclick="invoiceMonth='${x.month}';spendPage()">${x.month}</button>`).join("")}</div>
    <div class="card flush"><table class="ytt">
      <thead><tr><th>Persona</th><th>API</th><th>Voz</th><th>Proxy</th><th>Servidor</th><th>Total</th><th></th></tr></thead>
      <tbody>${m.people.map((p) => `<tr class="v"><td><b>${name(p.who)}</b><div class="sub">${p.videos.length} vídeo${p.videos.length === 1 ? "" : "s"}</div></td>
        <td data-k="API">${usd(p.api)}</td><td data-k="Voz">${usd(p.voice)}</td>
        <td data-k="Proxy">${usd(p.proxyUsd)}<div class="sub">${p.proxyGb.toFixed(2)} GB</div></td>
        <td data-k="Servidor">${usd(p.server)}</td><td data-k="Total"><b>${usd(p.total)}</b></td>
        <td><a class="btn sm" href="/api/factura.csv?month=${m.month}&who=${encodeURIComponent(p.who)}">CSV</a></td></tr>`).join("")
        || '<tr><td colspan="7" class="empty-row">Sin gasto este mes.</td></tr>'}</tbody></table></div>
    <div class="small muted mt-2">API y voz por el día de cada llamada · proxy por los GB que llevó cada vídeo ·
      servidor: ${fmt(m.serverUsd)} al mes a partes iguales entre ${m.parts || 1} (${fmt(Math.round(100 * m.serverUsd / (m.parts || 1)) / 100)} cada uno).
      ${!window.partner && !m.serverUsd ? 'Pon lo que cuesta el servidor en <a href="#/ajustes">Ajustes</a>.' : ""}</div>`;
}

async function spendPage() {
  const [g, px] = await Promise.all([api("/api/gasto"), window.partner ? null : api("/api/proxy?days=7").catch(() => null)]);
  const usd = (n, d = 2) => n == null ? "—" : Number(n).toFixed(d) + " $";
  const o = g.overall, max = Math.max(0.01, ...g.days.map((d) => d.usd));
  const top = Math.max(0.01, ...g.channels.map((c) => c.average || 0));
  const provTotal = Object.values(g.providers).reduce((a, b) => a + b, 0) || 1;
  const rows = g.videos.filter((v) => !spendChannel || v.channel === spendChannel)
    .sort((a, b) => spendSort === "usd" ? b.usd - a.usd : spendSort === "minutes" ? b.minutes - a.minutes
      : spendSort === "work" ? (b.workSeconds || 0) - (a.workSeconds || 0) : b.last.localeCompare(a.last));
  $("#app").innerHTML = `<h1>${window.partner ? "Mi gasto" : "Gasto de API"}</h1>
    <div class="small muted">Lo que cuestan las APIs de pago (guion, planos, juez, voz…). Las medias cuentan solo vídeos terminados; lo de vídeos a medias va aparte («en curso»).</div>
    <div class="kpis">
      <div class="kpi"><div class="k">Hoy</div><div class="v">${usd(g.today)}</div><div class="d">desde las 00:00 (UTC)</div></div>
      <div class="kpi"><div class="k">Media por vídeo</div><div class="v">${usd(o.average)}</div><div class="d">mediana ${usd(o.median)} · ${o.done} terminados</div></div>
      <div class="kpi"><div class="k">Por minuto de vídeo</div><div class="v">${usd(o.perMinute, 3)}</div><div class="d">coste / minutos de vídeo final</div></div>
      <div class="kpi"><div class="k">Últimos 7 días</div><div class="v">${usd(o.week)}</div><div class="d">este mes ${usd(o.month)}</div></div>
      <div class="kpi"><div class="k">Total</div><div class="v">${usd(g.total)}</div><div class="d">${usd(o.inProgress)} en curso${g.others ? ` · ${usd(g.others.total)} en radar e ideas` : ""}</div></div>
    ${px && px.proxies.length ? `
      <a class="kpi" href="#/servidor"><div class="k">Proxy · 7 días</div><div class="v">${usd(px.usd)}</div><div class="d">${px.totalGb.toFixed(2)} GB a ${px.usdPerGb} $/GB</div></a>
      <a class="kpi" href="#/servidor"><div class="k">Proxy por vídeo terminado</div><div class="v">${px.gbPerFinished != null ? usd(px.gbPerFinished * px.usdPerGb) : "—"}</div>
        <div class="d">${px.gbPerFinished != null ? px.gbPerFinished.toFixed(2) + " GB" : "sin vídeos terminados"}</div></a>
      <div class="kpi"><div class="k">API + proxy por vídeo</div><div class="v">${o.average != null && px.gbPerFinished != null ? usd(o.average + px.gbPerFinished * px.usdPerGb) : "—"}</div>
        <div class="d">lo que cuesta de verdad un vídeo terminado</div></div>` : ""}</div>

    ${invoiceBlock(g, usd)}

    ${(() => { const s = g.savings, p = g.pipeline, hm = (x) => x == null ? "—" : x >= 3600 ? `${Math.floor(x / 3600)} h ${String(Math.round(x % 3600 / 60)).padStart(2, "0")} min` : `${Math.round(x / 60)} min`;
      const most = Math.max(1, ...(p.stages || []).map((x) => x.seconds));
      return `<h2>Ahorro por reutilizar</h2>
    <div class="small muted">Lo que no se pagó otra vez, valorado con lo que cuesta aquí lo mismo: un veredicto del juez ${usd(s.perVerdict, 4)},
      1.000 caracteres de voz ${usd(s.perKChars, 3)}.</div>
    <div class="kpis">
      <div class="kpi"><div class="k">Ahorrado</div><div class="v">${usd(s.usd)}</div><div class="d">${Math.round(100 * s.share)} % de lo que habría costado</div></div>
      <div class="kpi"><div class="k">Veredictos del juez reutilizados</div><div class="v">${fmt(s.verdicts)}</div><div class="d">${usd(s.verdictsUsd)} (los mismos fotogramas ya juzgados)</div></div>
      <div class="kpi"><div class="k">Voz reutilizada</div><div class="v">${fmt(s.voiceChars)}</div><div class="d">caracteres · ${usd(s.voiceUsd, 3)} (trozos ya hechos)</div></div></div>

    <h2>Tiempo de pipeline</h2>
    <div class="small muted">Vídeos terminados: lo que tardó cada etapa trabajando (sin contar la espera de su turno en la cola).</div>
    <div class="kpis">
      <div class="kpi"><div class="k">Vídeos medidos</div><div class="v">${p.videos}</div><div class="d">terminados con sus tiempos</div></div>
      <div class="kpi"><div class="k">Tiempo total</div><div class="v">${hm(p.seconds)}</div><div class="d">coste total ${usd(p.usd)}</div></div>
      <div class="kpi"><div class="k">Tiempo medio</div><div class="v">${hm(p.averageSeconds)}</div><div class="d">coste medio ${usd(p.averageUsd)}</div></div></div>
    ${(p.stages || []).length ? `<div class="card mt-3"><b>Tiempo por etapa</b>
      ${p.stages.map((x) => `<div class="mt-3"><div class="row between small"><span>${esc(x.name)}</span><b>${hm(x.seconds)}</b></div>
        <div class="bar acc mt-1"><i style="--v:${100 * x.seconds / most}%"></i></div></div>`).join("")}</div>` : ""}`; })()}

    <h2>Cuota de la API de YouTube</h2>
    <div class="kpis">
      <div class="kpi"><div class="k">Por vídeo</div><div class="v">${o.ytUnits != null ? kfmt(o.ytUnits) : "—"}</div>
        <div class="d">unidades · ${o.ytSearches ?? "—"} búsquedas · ≈ ${o.ytKeys ?? "—"} claves</div></div>
      ${g.ytToday ? `<div class="kpi"><div class="k">Hoy</div><div class="v">${kfmt(g.ytToday.used)}</div>
        <div class="d">de ${kfmt(g.ytToday.total)} unidades · ${g.ytToday.searches}/${g.ytToday.searchesPerDay} búsquedas</div>
        <div class="bar acc"><i style="--v:${Math.min(100, 100 * g.ytToday.used / Math.max(1, g.ytToday.total))}%"></i></div></div>
      <div class="kpi"><div class="k">Da para</div><div class="v">${o.ytUnits ? fmt(Math.floor(g.ytToday.total / o.ytUnits * 10) / 10) : "—"}</div>
        <div class="d">vídeos al día con ${g.ytToday.keys} claves</div></div>
      <div class="kpi"><div class="k">Se renueva</div><div class="v txt">${esc(g.ytToday.reset)}</div><div class="d">hora de España</div></div>` : ""}</div>
    <div class="small muted mt-2">Cada búsqueda (search.list) cuesta 100 unidades y cada clave da 10.000 al día (y 100 búsquedas). Gratis en dinero, pero limita cuántos vídeos salen al día.
      Los vídeos de antes del registro se estiman por sus búsquedas (marcados con ≈).</div>

    ${g.proxy ? `<h2>Proxy, desde el principio</h2>
    <div class="kpis">
      <div class="kpi"><div class="k">Por vídeo</div><div class="v">${usd(o.proxyUsd, 2)}</div><div class="d">media de los terminados${o.proxyGb != null ? ` · ${o.proxyGb.toFixed(2)} GB` : ""}</div></div>
      <div class="kpi"><div class="k">Total</div><div class="v">${usd(g.proxy.usd)}</div>
        <div class="d">${g.proxy.gb.toFixed(2)} GB · ${fmt(g.proxy.requests)} peticiones · ${g.proxy.videos} vídeos</div></div>
      <div class="kpi"><div class="k">Desde</div><div class="v txt">${g.proxy.since ? new Date(g.proxy.since * 1000).toLocaleString("es-ES", {day: "numeric", month: "short", hour: "2-digit", minute: "2-digit"}) : "—"}</div>
        <div class="d">primera petición por el proxy</div></div></div>
    <div class="small muted mt-2">Los GB del proxy residencial son los medidos en cada petición, a ${g.proxy.usdPerGb} $/GB (sourcing.youtube.proxy_usd_per_gb).
      ${g.proxy.estimatedVideos ? `Los ${g.proxy.estimatedVideos} vídeos marcados con ≈ usaron el proxy de metadatos antiguo, que no guardaba tamaños: se estima con ${g.proxy.mbPerRequest} MB por petición y ${g.proxy.metadataUsdPerGb} $/GB.` : ""}</div>` : ""}

    <h2>Media por canal</h2>
    <div class="card flush"><table class="ytt">
      <thead><tr><th>Canal</th><th>Media por vídeo</th><th>Mediana</th><th>Por minuto</th><th>Cuota YT / vídeo</th><th>Proxy / vídeo</th><th>Terminados</th><th>Total</th><th>En curso</th><th>Más caro</th></tr></thead>
      <tbody>${g.channels.map((c) => `<tr class="v click" onclick="spendChannel='${esc(c.channel)}';spendPage()">
        <td><span class="row nowrap">${dot(c.channel)}<b>${esc(c.channel)}</b></span></td>
        <td data-k="Media"><b>${usd(c.average)}</b><div class="vbar" style="--v:${Math.max(3, 100 * (c.average || 0) / top)}%"></div></td>
        <td data-k="Mediana">${usd(c.median)}</td><td data-k="Por minuto">${usd(c.perMinute, 3)}</td>
        <td data-k="Cuota YT" title="${c.ytSearches ?? "—"} búsquedas">${c.ytUnits != null ? kfmt(c.ytUnits) + " u · " + c.ytKeys + " claves" : "—"}</td>
        <td data-k="Proxy">${c.proxyUsd != null ? usd(c.proxyUsd, 2) + (c.proxyGb != null ? ` <span class="muted small">${c.proxyGb.toFixed(2)} GB</span>` : "") : "—"}</td><td data-k="Terminados">${c.done} de ${c.videos}</td>
        <td data-k="Total">${usd(c.total)}</td><td data-k="En curso" class="wide">${usd(c.inProgress)}</td>
        <td data-k="Más caro" class="wide">${c.dearest ? `${esc(c.dearest.slug)} · ${usd(c.dearest.usd)}` : "—"}</td></tr>`).join("")}
      <tr class="group"><td>Todos los canales</td><td>${usd(o.average)}</td><td>${usd(o.median)}</td>
        <td>${usd(o.perMinute, 3)}</td><td>${o.ytUnits != null ? kfmt(o.ytUnits) + " u · " + o.ytKeys + " claves" : "—"}</td>
        <td>${o.proxyUsd != null ? usd(o.proxyUsd, 2) : "—"}</td>
        <td>${o.done} de ${o.videos}</td><td>${usd(o.total)}</td>
        <td class="wide">${usd(o.inProgress)}</td><td class="wide"></td></tr></tbody></table></div>

    <div class="grid2 mt-3">
      <div class="card"><b>En qué se va</b><div class="small muted">Todo el gasto, por servicio</div>
        ${Object.entries(g.providers).map(([k, v]) => `<div class="mt-3"><div class="row between small"><span>${esc(k)}</span>
          <span><b>${usd(v)}</b> <span class="muted">${Math.round(100 * v / provTotal)} %</span></span></div>
          <div class="bar acc mt-1"><i style="--v:${100 * v / provTotal}%"></i></div></div>`).join("")}</div>
      <div class="card"><b>Por día</b><div class="small muted">Últimos 30 días · máximo ${usd(max)}</div>
        <div class="spend tight">${g.days.map((d) => `<div title="${esc(d.day)}: ${usd(d.usd)}" style="--v:${Math.max(d.usd ? 2 : 0, 100 * d.usd / max)}%"></div>`).join("")}</div>
        <div class="row between small muted mt-1"><span>${esc(g.days[0].day.slice(5))}</span><span>hoy</span></div></div></div>

    <h2>Por vídeo</h2>
    <div class="tools">
      <button class="chip ${spendChannel ? "" : "on"}" onclick="spendChannel='';spendPage()">Todos</button>
      ${g.channels.map((c) => `<button class="chip ${c.channel === spendChannel ? "on" : ""}" onclick="spendChannel='${esc(c.channel)}';spendPage()">
        ${dot(c.channel, "sm")}${esc(c.channel)}</button>`).join("")}
      <label class="row nowrap small gap-1 n4 push">Ordenar:<select class="sm w-auto" onchange="spendSort=this.value;spendPage()">
        ${[["last", "Más reciente"], ["usd", "Más caro"], ["minutes", "Más largo"], ["work", "Más lento"]].map(([k, l]) => `<option value="${k}" ${spendSort === k ? "selected" : ""}>${l}</option>`).join("")}</select></label></div>
    <div class="card flush tall"><table class="ytt">
      <thead><tr><th>Vídeo</th><th>Gasto</th><th>Ahorrado</th><th>Tiempo</th><th>Cuota YT</th><th>Proxy</th><th>Duración</th><th>Por minuto</th><th>Estado</th><th class="l">Desglose</th></tr></thead>
      <tbody>${rows.map((v) => `<tr class="v"><td><a class="t" href="#/video/${encodeURIComponent(v.slug)}">${esc(v.slug)}</a>
          <div class="sub">${dot(v.channel, "sm")}
            <select class="sm w-auto" title="Cambiar de canal" onchange="post('/api/video/${encodeURIComponent(v.slug)}/channel', {channel: this.value}).then(spendPage)">
              ${(g.allChannels.includes(v.channel) ? g.allChannels : [v.channel, ...g.allChannels]).map((c) => `<option ${c === v.channel ? "selected" : ""}>${esc(c)}</option>`).join("")}</select>
            <span class="nw">· ${esc(v.last)}</span></div></td>
        <td data-k="Gasto"><b>${usd(v.usd)}</b>${v.proxyUsd ? `<div class="sub" title="API + proxy">con proxy ${usd(v.usd + v.proxyUsd)}</div>` : ""}</td>
        <td data-k="Ahorrado" title="${fmt(v.reused?.judge || 0)} veredictos · ${fmt(v.reused?.voice || 0)} caracteres de voz">${v.savedUsd ? usd(v.savedUsd) : "—"}</td>
        <td data-k="Tiempo">${v.workSeconds ? (v.workSeconds >= 3600 ? `${Math.floor(v.workSeconds / 3600)} h ${String(Math.round(v.workSeconds % 3600 / 60)).padStart(2, "0")} min` : `${Math.round(v.workSeconds / 60)} min`) : "—"}</td>
        <td data-k="Cuota YT" title="${v.ytSearches ?? 0} búsquedas">${v.ytUnits ? (v.ytEstimated ? "≈ " : "") + kfmt(v.ytUnits) + " u" : "—"}</td>
        <td data-k="Proxy" title="${v.proxyRequests ?? 0} peticiones por el proxy${v.proxyEstimated ? " · estimado por peticiones (proxy de metadatos antiguo)" : ""}">${v.proxyUsd ? (v.proxyEstimated ? "≈ " : "") + usd(v.proxyUsd, 2) + (v.proxyGb ? `<div class="sub">${v.proxyGb.toFixed(2)} GB</div>` : "") : "—"}</td><td data-k="Duración">${v.minutes ? fmt(v.minutes) + " min" : "—"}</td>
        <td data-k="Por minuto">${v.minutes ? usd(v.usd / v.minutes, 3) : "—"}</td>
        <td data-k="Estado">${v.done ? '<span class="pill hecho">terminado</span>' : '<span class="pill">en curso</span>'}</td>
        <td class="wide small muted l">${Object.entries(v.providers).slice(0, 3).map(([k, x]) => `${esc(k.split(" (")[0])} ${usd(x)}`).join(" · ")}</td></tr>`).join("")
        || '<tr><td colspan="10" class="empty-row">Sin gasto registrado.</td></tr>'}</tbody></table></div>`;
}

async function restartQueue(button) {
  if (!confirm("¿Reiniciar la cola? El vídeo que se esté haciendo sigue luego desde su última etapa terminada.")) return;
  button.disabled = true;
  try { alert((await post("/api/restart-queue")).message); } catch (e) { alert(e.message); }
  button.disabled = false;
}
async function youtubeRetry(button) {
  if (!confirm("¿YouTube ya funciona? Ábrelo en una ventana privada desde el wifi de casa: si NO pide «no eres un bot», sigue.\n\nSe quitan la pausa por bloqueo, las cuarentenas y la espera de 72 h, y la cola vuelve a buscar ya.")) return;
  button.disabled = true;
  try { alert((await post("/api/youtube/retry")).message); } catch (e) { alert(e.message); }
  button.disabled = false;
}

async function updateNow(button) {
  button.disabled = true; button.textContent = "Actualizando…";
  try {
    const r = await post("/api/update");
    alert(r.message);
    setTimeout(() => location.reload(), r.changed ? 4000 : 300);    // «ya al día» too: the tab may be older
  } catch (e) { alert(e.message); }
  button.disabled = false; button.innerHTML = `${icon("refresh")} Actualizar ahora`;
}

function movePrio(i, step) {                       // up, down and remove in «Prioridad en la cola»
  const list = [...(window.prioList || [])];
  if (step === 0) list.splice(i, 1);
  else [list[i], list[i + step]] = [list[i + step], list[i]];
  save({channel_priority: list});
}

let mineOpen = false, mineEmpty = false;
// Ajustes → «Personas»: who else uses the studio, with their password and their channels (they see only those)
async function peopleBlock(all) {
  const u = (await api("/api/users").catch(() => ({users: []}))).users;
  const owner = Object.fromEntries(u.flatMap((x) => x.channels.map((c) => [c, x.name])));
  const boxes = (who, mine) => all.map((c) => `<label class="check small${owner[c] && owner[c] !== who ? " off" : ""}">
    <input type="checkbox" class="pc-${esc(who || "_new")}" value="${esc(c)}" ${mine.includes(c) ? "checked" : ""} ${owner[c] && owner[c] !== who ? "disabled" : ""}>${esc(c)}${owner[c] && owner[c] !== who ? ` <span class="muted">(${esc(owner[c])})</span>` : ""}</label>`).join("");
  const picked = (who) => [...document.querySelectorAll(".pc-" + (who || "_new") + ":checked")].map((x) => x.value);
  window.savePerson = async (who) => {
    const msg = $("#pmsg-" + (who || "_new"));
    const name = who || $("#pname").value.trim().toLowerCase(), password = $("#ppass-" + (who || "_new")).value;
    const limits = who ? {daily_usd: parseFloat($("#plim-usd-" + who).value || 0), proxy_gb_per_day: parseFloat($("#plim-gb-" + who).value || 0)} : undefined;
    try { await post("/api/users", {name, password, channels: picked(who), limits}); settingsPage(); }
    catch (e) { msg.textContent = e.message; }
  };
  window.removePerson = async (who) => {
    if (!confirm(`¿Quitar a ${who}? No podrá entrar más; sus vídeos se quedan.`)) return;
    await post("/api/users", {remove: who}); settingsPage();
  };
  return `<details class="block"${u.length ? " open" : ""}><summary><b>Personas que comparten el estudio
      <span class="count">${u.length ? u.length + (u.length === 1 ? " persona" : " personas") : "solo tú"}</span></b></summary>
    <div class="in"><p class="help">Cada persona entra con su contraseña y solo ve sus canales: sus vídeos, su gasto y su factura.
      Nada de lo tuyo (ni Ajustes, ni el servidor, ni los demás canales). Un canal es de una sola persona; los que no son de nadie, tuyos.</p>
    ${u.map((x) => `<div class="card mt"><div class="row between"><b>${esc(x.name)}</b>
        <button class="sm" onclick="removePerson('${esc(x.name)}')">Quitar</button></div>
      <div class="row gap-4 mt-2">${boxes(x.name, x.channels)}</div>
      <div class="setting mt-3"><div><div class="small b">Sus topes al día</div>
          <p class="help">0 = sin tope · Telegram: ${x.telegram ? `<span class="t-ok">${icon("check")}</span> conectado` : "sin conectar (sus avisos te llegan a ti)"}</p></div>
        <div class="row gap-4"><div class="unit"><input id="plim-usd-${esc(x.name)}" type="number" min="0" step="0.5" value="${x.limits.daily_usd || 0}"><span class="nw">$ de API</span></div>
          <div class="unit"><input id="plim-gb-${esc(x.name)}" type="number" min="0" step="0.5" value="${x.limits.proxy_gb_per_day || 0}"><span class="nw">GB de proxy</span></div></div></div>
      <div class="actions"><input id="ppass-${esc(x.name)}" class="grow" type="password" autocomplete="new-password" placeholder="Nueva contraseña (vacío = la misma)">
        <button onclick="savePerson('${esc(x.name)}')">Guardar</button><span id="pmsg-${esc(x.name)}" class="small t-bad"></span></div></div>`).join("")}
    <div class="card mt"><b>Añadir persona</b>
      <div class="row mt-2"><input id="pname" class="w-md" placeholder="nombre (p. ej. marc)">
        <input id="ppass-_new" class="w-md" type="password" autocomplete="new-password" placeholder="Contraseña (8 o más)"></div>
      <div class="row gap-4 mt-3">${boxes("", [])}</div>
      <div class="actions"><button class="main" onclick="savePerson('')">Añadir</button><span id="pmsg-_new" class="small t-bad"></span></div></div></div>
  </details>`;
}

async function settingsPage() {
  const [s, n] = [await api("/api/settings"), await api("/api/notify")];
  window.prioList = s.channel_priority || [];
  const guessUrl = n.studioUrl || (location.hostname === "127.0.0.1" || location.hostname === "localhost" ? "" : location.origin);
  if (!data) data = await api("/api/overview");
  const code = data && data.service && data.service.code;
  const filled = s.channels.filter((c) => s.myChannels[c]).length;
  const people = await peopleBlock(s.channels);
  $("#app").innerHTML = `<h1>Ajustes</h1>
    ${code ? `<div class="notice ok">Código del servidor: <b>${esc(code.what)}</b> · ${esc(code.at.slice(0, 16).replace("T", " "))}
      <div class="small muted">Se actualiza solo: el estudio cada 2 minutos y la cola entre vídeo y vídeo. No hace falta SSH.</div>
      <div class="actions mt-3"><button onclick="updateNow(this)">${icon("refresh")} Actualizar ahora</button>
      <button onclick="restartQueue(this)" title="Si la cola parece parada o colgada">${icon("restart")} Reiniciar la cola</button>
      <button onclick="youtubeRetry(this)" title="Quita la pausa por bloqueo, las cuarentenas y la espera de 72 h">${icon("play")} Reintentar YouTube ahora</button></div></div>` : ""}
    <div class="notice">${icon("mic")} <a href="#/voces"><b>Voces por canal (GenAIPro)</b></a>: la voz se genera sola a partir del guion, sin grabarla.</div>
    ${people}
    <h2>Cola y límites</h2>
    <div class="card">
      <div class="setting"><div><div class="small b">Hacer vídeos</div>
          <p class="help">${s.paused ? "En pausa: no empieza vídeos nuevos (el que está en marcha termina)." : "Activo."}</p></div>
        <div class="unit"><button class="${s.paused ? "main" : ""}" onclick="save({paused: ${!s.paused}})">${s.paused ? `${icon("play")} Reanudar` : `${icon("pause")} Pausar`}</button></div></div>
      <div class="setting"><div><label for="limit">Límite de gasto de API al día</label><p class="help">De tus vídeos; cada persona tiene el suyo en «Personas» · 0 = sin límite; al llegar, espera a mañana</p></div>
        <div class="unit"><input id="limit" type="number" min="0" step="0.5" value="${s.daily_usd ?? 0}"><span>$</span>
          <button onclick="save({daily_usd: parseFloat(document.getElementById('limit').value || 0)})">Guardar</button></div></div>
      <div class="setting"><div><label for="proxyday">Tope de proxy al día</label><p class="help">GB de tus vídeos por el proxy residencial; al llegar, los vídeos que necesitan YouTube esperan a mañana y los doblajes siguen · 0 = sin tope</p></div>
        <div class="unit">${data && data.budget && data.budget.proxyGbToday != null ? `<span class="small nw">hoy ${data.budget.proxyGbToday.toFixed(2)} GB</span>` : ""}
          <input id="proxyday" type="number" min="0" step="0.5" value="${s.proxy_gb_per_day ?? 0}"><span>GB</span>
          <button onclick="save({proxy_gb_per_day: parseFloat(document.getElementById('proxyday').value || 0)})">Guardar</button></div></div>
      <div class="setting"><div><label for="pervideo">Límite por vídeo</label><p class="help">Lo que puede gastar un intento; si lo pasa, se para y sale de la cola para que lo mires · 0 = sin límite</p></div>
        <div class="unit"><input id="pervideo" type="number" min="0" step="0.1" value="${s.per_video_usd ?? 1.5}"><span>$</span>
          <button onclick="save({per_video_usd: parseFloat(document.getElementById('pervideo').value || 0)})">Guardar</button></div></div>
      <div class="setting"><div><label for="servermonth">Coste del servidor al mes</label><p class="help">Para la factura de cada persona en «Gasto»: a partes iguales entre tú y cada persona</p></div>
        <div class="unit"><input id="servermonth" type="number" min="0" step="0.5" value="${s.server_usd_month ?? 0}"><span>$</span>
          <button onclick="save({server_usd_month: parseFloat(document.getElementById('servermonth').value || 0)})">Guardar</button></div></div>
      <p class="help mt-3">Cada vídeo gasta normalmente 0,7-1,2 $ (sale en su diagnóstico).</p>
    </div>
    <h2>Avisos al móvil (Telegram)</h2>
    <div class="card">
      <div>${n.telegram ? '<span class="pill hecho">Conectado</span> Cada vídeo terminado te llega con su miniatura y un botón a «Revisar clips»; si uno falla, también.' : '<span class="pill">Sin conectar</span>'}</div>
      ${n.telegram ? "" : `<ol class="small mt-3">
        <li>En Telegram abre <b>@BotFather</b>, escribe <code>/newbot</code>, ponle un nombre y copia el <b>token</b> que te da.</li>
        <li>Abre tu bot nuevo (el enlace t.me/… que te da BotFather) y pulsa <b>Iniciar</b>.</li>
        <li>Pega el token aquí y pulsa «Conectar y probar».</li></ol>`}
      ${n.token && n.telegram ? "" : field("Token del bot", '<input id="tg-token" placeholder="123456789:AA…" autocomplete="off">', "", "tg-token")}
      ${field("Dirección del estudio", `<input id="tg-url" placeholder="https://1-2-3-4.sslip.io" value="${esc(guessUrl)}">`, "Para el botón «Revisar clips»; en la VPS: https://…sslip.io", "tg-url")}
      ${!guessUrl ? '<p class="help mt-2">En tu PC el estudio solo se abre en el propio PC: los avisos llegan igual, pero el botón solo funciona con el estudio de la VPS.</p>' : ""}
      <div class="actions"><button class="main" id="tg-go">${n.telegram ? "Guardar y enviar prueba" : "Conectar y probar"}</button><span id="tg-msg" class="small muted"></span></div>
    </div>
    <h2>Canales</h2>
    <div class="card"><div class="row">${s.channels.map((c) => `<span class="pill">${esc(c)}</span>`).join("")}
      <a class="btn main" href="#/canal-nuevo">${icon("plus")} Añadir canal</a></div>
      <div class="field"><label for="prio-add">Prioridad en la cola</label>
      <p class="help">Se hacen primero los vídeos de estos canales, en este orden; los demás, después</p>
      <div id="prio">${(s.channel_priority || []).map((c, i, all) => `<div class="row mt-2">
        <b>${i + 1}.</b><span class="pill ch" style="--c:${chColor(c)}">${esc(c)}</span>
        <button class="icon sm" ${i ? "" : "disabled"} onclick="movePrio(${i}, -1)" title="Subir" aria-label="Subir">${icon("up")}</button>
        <button class="icon sm" ${i < all.length - 1 ? "" : "disabled"} onclick="movePrio(${i}, 1)" title="Bajar" aria-label="Bajar">${icon("down")}</button>
        <button class="icon sm" onclick="movePrio(${i}, 0)" title="Quitar de la lista" aria-label="Quitar de la lista">${icon("x")}</button></div>`).join("") || '<div class="small muted mt-2">Sin prioridad: la cola va por fecha de publicación y antigüedad.</div>'}</div>
      <div class="row mt-2"><select id="prio-add" class="w-auto"><option value="">Añadir canal…</option>
        ${s.channels.filter((c) => !(s.channel_priority || []).includes(c)).map((c) => `<option>${esc(c)}</option>`).join("")}</select>
        <button onclick="const c = document.getElementById('prio-add').value; if (c) save({channel_priority: [...(window.prioList || []), c]})">Añadir</button></div></div></div>
    <details class="block" ${mineOpen ? "open" : ""} ontoggle="mineOpen=this.open"><summary><b>Mi canal de YouTube en cada perfil <span class="count">${filled} de ${s.channels.length} con @canal</span></b></summary>
      <div class="in">
      <p class="help mb-2">Tu @canal o su URL: lo usan «Mi canal» y las ideas. ${s.channels.length - filled ? `<a href="javascript:mineEmpty=!mineEmpty;route()">${mineEmpty ? "Ver todos" : `Ver solo los ${s.channels.length - filled} sin rellenar`}</a>` : ""}</p>
      ${s.channels.filter((c) => !mineEmpty || !s.myChannels[c]).map((c) => `<div class="mine-row"><div><span class="pill ch" style="--c:${chColor(c)}">${esc(c)}</span></div>
        <input class="mine" data-c="${esc(c)}" placeholder="@TuCanal" value="${esc(s.myChannels[c] || "")}"></div>`).join("")}
      <div class="actions"><button class="main" onclick="save({my_channels: {...${JSON.stringify(s.myChannels || {}).replace(/"/g, "&quot;")}, ...Object.fromEntries([...document.querySelectorAll('.mine')].map((i) => [i.dataset.c, i.value]))}})">Guardar</button></div>
      </div></details>`;
  window.save = async (body) => { await post("/api/settings", body); route(); };
  $("#tg-go").onclick = async () => {
    const msg = $("#tg-msg"); msg.textContent = "Enviando…";
    try {
      const r = await post("/api/notify", {token: $("#tg-token") ? $("#tg-token").value : "", studio_url: $("#tg-url").value});
      msg.innerHTML = r.ok ? `<span class="t-ok">${icon("check")}</span> Mira tu Telegram: te ha llegado un mensaje de prueba.` : "No se pudo enviar";
      if (r.ok) setTimeout(route, 2500);
    } catch (e) { msg.textContent = e.message; }
  };
}

// --- Voces por canal (GenAIPro) ----------------------------------------------------------------------------------
async function voicesPage() {
  const v = await api("/api/voices");
  const row = (c) => { const x = v.voices[c] || {};
    return `<div class="card"><div class="row"><b>${esc(c)}</b> ${x.voice_id ? `<span class="pill hecho">${esc(x.name || x.voice_id)}</span>` : '<span class="pill">sin voz: se graba a mano</span>'}</div>
      <div class="three">
        ${field("ID de la voz", `<input id="vid-${esc(c)}" value="${esc(x.voice_id || "")}" placeholder="p. ej. JBFqnCBsd6RMkjVDRZzb">`, "", "vid-" + esc(c))}
        ${field("Nombre", `<input id="vname-${esc(c)}" value="${esc(x.name || "")}">`, "Para reconocerla", "vname-" + esc(c))}
        ${field("Modelo", `<select id="vmodel-${esc(c)}">${v.models.map((m) => `<option ${m === (x.model_id || v.defaults.model_id) ? "selected" : ""}>${m}</option>`).join("")}</select>`, "", "vmodel-" + esc(c))}
        ${field("Velocidad", `<input id="vspeed-${esc(c)}" type="number" step="0.05" min="0.7" max="1.2" value="${x.speed ?? v.defaults.speed}">`, "0,7-1,2", "vspeed-" + esc(c))}
        ${field("Estabilidad", `<input id="vstab-${esc(c)}" type="number" step="0.05" min="0" max="1" value="${x.stability ?? v.defaults.stability}">`, "0-1; más = más regular", "vstab-" + esc(c))}
        ${field("Parecido", `<input id="vsim-${esc(c)}" type="number" step="0.05" min="0" max="1" value="${x.similarity ?? v.defaults.similarity}">`, "0-1", "vsim-" + esc(c))}
      </div>
      <div class="actions"><button class="main" onclick="saveVoice('${esc(c)}')">Guardar</button>
        <button onclick="testVoice('${esc(c)}')">${icon("play")} Probar</button>${x.voice_id ? `<button onclick="clearVoice('${esc(c)}')">Quitar voz</button>` : ""}
        <span id="vmsg-${esc(c)}" class="small muted"></span></div><div id="vplay-${esc(c)}"></div>
      ${dubBox(c)}</div>`; };
  const LANGS = {pt: "Portugués", de: "Alemán", fr: "Francés", en: "Inglés", it: "Italiano"};
  const dubBox = (c) => { if (window.partner) return "";      // dubbing sends videos to other channels: set up by the owner
    const d = (v.dubbing || {})[c] || {}, on = d.languages || [];
    return `<details class="fset" ${on.length ? "open" : ""}><summary class="mt-3"><b>Doblaje</b> ${on.length ? `<span class="pill hecho">${on.map((l) => LANGS[l] || l).join(", ")}</span>` : '<span class="muted small">apagado</span>'}</summary>
      <p class="help my-2">Cada vídeo terminado de este canal se traduce y se vuelve a leer en esos idiomas; la cola monta el vídeo doblado
        (mismos clips, textos de pantalla traducidos) en una carpeta <code>&lt;vídeo&gt;-pt</code>, <code>-de</code>… Coste: la traducción (céntimos) y los caracteres de GenAIPro (lo mismo que la voz original, por idioma).</p>
      ${(v.dubLanguages || []).map((l) => `<div class="mine-row">
        <label class="check"><input type="checkbox" class="dub-${esc(c)}" value="${l}" ${on.includes(l) ? "checked" : ""}> ${LANGS[l] || l}</label>
        <input id="dubv-${esc(c)}-${l}" placeholder="ID de voz nativa (vacío = la voz del canal, modelo multilingüe)" value="${esc(((d.voices || {})[l] || {}).voice_id || "")}"></div>`).join("")}
      <label class="check mt-3"><input type="checkbox" id="dubex-${esc(c)}" ${d.existing === false ? "" : "checked"}>
        Doblar también los vídeos ya hechos</label>
      <p class="help">Si no, solo los que se terminen a partir de ahora</p>
      <div class="actions"><button class="main" onclick="saveDub('${esc(c)}')">Guardar doblaje</button><span id="dubmsg-${esc(c)}" class="small muted"></span></div></details>`; };
  window.saveDub = async (c) => {
    const languages = [...document.querySelectorAll(".dub-" + CSS.escape(c))].filter((x) => x.checked).map((x) => x.value);
    const voices = {}; languages.forEach((l) => { const id = $("#dubv-" + CSS.escape(c) + "-" + l).value.trim(); if (id) voices[l] = {voice_id: id}; });
    try { await post("/api/dubbing", {channel: c, languages, voices, existing: $("#dubex-" + CSS.escape(c)).checked});
      $("#dubmsg-" + CSS.escape(c)).textContent = languages.length ? "Guardado ✓ (empieza en unos minutos)" : "Doblaje apagado"; }
    catch (e) { $("#dubmsg-" + CSS.escape(c)).textContent = e.message; } };
  $("#app").innerHTML = `<h1>Voces por canal</h1>
    ${v.hasKey ? "" : '<div class="notice bad">Falta <b>GENAIPRO_API_KEY</b> en el .env del servidor (genaipro.io → avatar → Manage Account → API Key). Ponla y reinicia el estudio.</div>'}
    <p class="muted small">Con una voz puesta, un vídeo de ese canal solo necesita el guion: la voz se genera al empezar el vídeo. Si subes tu voz.mp3, se usa la tuya.
      <span id="credits"></span></p>
    ${v.channels.map(row).join("")}
    <h2>Buscar voces</h2>
    <div class="card"><div class="three">
      <div class="field"><input id="vq" placeholder="nombre o estilo: narrator, documentary, deep…"></div>
      <div class="field"><select id="vlang"><option value="es">español</option><option value="pt">portugués</option><option value="de">alemán</option>
        <option value="fr">francés</option><option value="en">inglés</option><option value="it">italiano</option><option value="">todas</option></select></div>
      <div class="field"><select id="vgender"><option value="">hombre o mujer</option><option value="male">hombre</option><option value="female">mujer</option></select></div></div>
      <div class="actions"><button class="main" onclick="searchVoices()">Buscar</button></div><div id="vresults" class="mt-3"></div></div>`;
  const read = (c) => ({channel: c, voice_id: $("#vid-" + c).value.trim(), name: $("#vname-" + c).value.trim(), model_id: $("#vmodel-" + c).value,
    speed: $("#vspeed-" + c).value, stability: $("#vstab-" + c).value, similarity: $("#vsim-" + c).value});
  window.saveVoice = async (c) => { try { await post("/api/voices", read(c)); voicesPage(); } catch (e) { $("#vmsg-" + c).textContent = e.message; } };
  window.clearVoice = async (c) => { await post("/api/voices", {channel: c, voice_id: ""}); voicesPage(); };
  window.testVoice = async (c) => { const m = $("#vmsg-" + c); m.textContent = "Generando la prueba… (10-40 s)";
    try { const r = await post("/api/voices/test", {...read(c), text: ""}); m.textContent = "";
      $("#vplay-" + c).innerHTML = `<audio class="w-full mt-2" controls autoplay src="${r.url}"></audio>`; } catch (e) { m.textContent = e.message; } };
  window.searchVoices = async () => { const box = $("#vresults"); box.textContent = "Buscando…";
    try { const list = await api(`/api/voices/search?q=${encodeURIComponent($("#vq").value)}&language=${$("#vlang").value}&gender=${$("#vgender").value}`);
      box.innerHTML = list.map((x) => `<div class="slot"><b>${esc(x.name || "")}</b><span class="small muted">${esc([x.gender, x.age, x.accent, x.language, x.use_case, x.descriptive].filter(Boolean).join(" · "))}</span>
        ${x.preview_url ? `<audio class="sm" controls preload="none" src="${esc(x.preview_url)}"></audio>` : ""}
        <code class="small">${esc(x.voice_id)}</code>
        <select class="sm w-auto push" onchange="if(this.value){document.getElementById('vid-'+this.value).value='${esc(x.voice_id)}';document.getElementById('vname-'+this.value).value='${esc(x.name || "")}';saveVoice(this.value)}">
          <option value="">Usar en canal…</option>${v.channels.map((c) => `<option>${esc(c)}</option>`).join("")}</select></div>`).join("") || "Nada con eso.";
    } catch (e) { box.textContent = e.message; } };
  if (v.hasKey) api("/api/voices/credits").then((cr) => { const n = (cr || []).reduce((a, x) => a + (x.amount || 0), 0);
    $("#credits").textContent = ` · Créditos de voz: ${n.toLocaleString("es-ES")}`; }).catch(() => {});
}

async function newChannelPage() {
  data = await api("/api/overview");
  $("#app").innerHTML = `<h1>Nuevo canal</h1>
    <div class="card">
      <div class="fset"><div class="legend">Canal</div>
        <div class="two">
          ${field("Nombre", '<input id="ch-name" placeholder="coches">', "Minúsculas, sin espacios: coches, historia-f1…", "ch-name")}
          ${field('Tu canal en YouTube <span class="opt">opcional</span>', '<input id="ch-mine" placeholder="@TuCanal">', "", "ch-mine")}
        </div>
        ${field("¿De qué va?", '<input id="ch-about" placeholder="documentales sobre la historia de marcas de coches y sus fracasos, de ~10 min">', "Una frase; la usan las ideas y el radar", "ch-about")}
        <div class="two">
          ${field("Aspecto copiado de", `<select id="ch-base"><option value="">— el de por defecto —</option>
            ${data.channels.map((c) => `<option>${esc(c)}</option>`).join("")}</select>`, "Colores, música, gráficos", "ch-base")}
          ${field("Formato habitual", `<select id="ch-format"><option value="">— historia (por defecto) —</option>
            ${data.formats.map((f) => `<option>${esc(f)}</option>`).join("")}</select>`, "", "ch-format")}
        </div></div>
      <div class="fset"><div class="legend">Radar e ideas</div>
        ${field("Competidores", '<input id="ch-comp" placeholder="@canal1, @canal2">', "@canales separados por comas; el radar mira sus vídeos que mejor van", "ch-comp")}
        ${field("Búsquedas del nicho", '<textarea id="ch-queries" class="mid" placeholder="historia de marcas de coches&#10;car brand history&#10;why this car failed"></textarea>', "Una por línea; para el radar y las ideas", "ch-queries")}
        ${field('Patrón de títulos <span class="opt">opcional</span>', '<input id="ch-pattern">', "P. ej. «marca + fracaso + cifra»", "ch-pattern")}</div>
      <div class="actions"><button class="main" id="ch-go">Crear canal</button><span id="ch-msg" class="small muted"></span></div>
    </div>`;
  $("#ch-go").onclick = async () => {
    const msg = $("#ch-msg"); msg.textContent = "Creando…";
    try {
      const r = await post("/api/channels", {name: $("#ch-name").value, about: $("#ch-about").value, base: $("#ch-base").value,
        format: $("#ch-format").value, competitors: $("#ch-comp").value, queries: $("#ch-queries").value,
        pattern: $("#ch-pattern").value, my_channel: $("#ch-mine").value});
      if ($("#ch-mine").value.trim() && !window.partner) await post("/api/settings", {my_channels: {[r.channel]: $("#ch-mine").value.trim()}});
      data = null; msg.innerHTML = `<span class="t-ok">${icon("check")}</span> Canal «${esc(r.channel)}» creado. Ya puedes elegirlo al crear un vídeo.`;
      setTimeout(() => { location.hash = "#/nuevo"; }, 1200);
    } catch (e) { msg.textContent = e.message; }
  };
}

// «Mi cuenta» (a partner): Telegram for their videos' messages, their daily caps, their password
async function accountPage() {
  const a = await api("/api/cuenta");
  const cap = (v, unit) => v ? `${v} ${unit}` : "sin tope propio";
  $("#app").innerHTML = `<h1>Mi cuenta</h1>
    <div class="small muted">${esc(a.name)} · tus canales: ${a.channels.map(esc).join(", ") || "ninguno todavía"}</div>
    <div class="kpis">
      <div class="kpi"><div class="k">Gasto de API hoy</div><div class="v">${a.spentToday.toFixed(2)} $</div><div class="d">tope: ${cap(a.limits.daily_usd, "$ al día")}</div>
        ${a.limits.daily_usd ? `<div class="bar acc"><i style="--v:${Math.min(100, 100 * a.spentToday / a.limits.daily_usd)}%"></i></div>` : ""}</div>
      <div class="kpi"><div class="k">Proxy hoy</div><div class="v">${a.proxyGbToday.toFixed(2)} GB</div><div class="d">tope: ${cap(a.limits.proxy_gb_per_day, "GB al día")}</div>
        ${a.limits.proxy_gb_per_day ? `<div class="bar acc"><i style="--v:${Math.min(100, 100 * a.proxyGbToday / a.limits.proxy_gb_per_day)}%"></i></div>` : ""}</div></div>
    <div class="small muted mt-2">Al llegar a un tope, tus vídeos esperan a mañana (los de otros no cuentan). Los topes los pone quien administra el estudio.</div>
    <h2>Avisos en Telegram</h2>
    <div class="card">${a.telegram
      ? `<span class="t-ok">${icon("check")}</span> Conectado: te llegan los avisos de tus vídeos (terminado, error, falta la voz).
         <div class="actions"><button onclick="post('/api/telegram/unlink').then(accountPage)">Desconectar</button></div>`
      : `Recibe en el móvil cuándo termina o falla cada vídeo tuyo.
         <div class="actions"><button class="main" id="tglink">Conectar Telegram</button><span id="tgmsg" class="small muted"></span></div>`}</div>
    <h2>Contraseña</h2>
    <div class="card"><div class="two">
      ${field("Actual", '<input id="pw-old" type="password" autocomplete="current-password">', "", "pw-old")}
      ${field("Nueva", '<input id="pw-new" type="password" autocomplete="new-password">', "8 o más", "pw-new")}</div>
      <div class="actions"><button class="main" id="pw-go">Cambiar</button><span id="pw-msg" class="small muted"></span></div></div>
    <div class="actions mt-5"><button onclick="logout()">Cerrar sesión</button></div>`;
  if ($("#tglink")) $("#tglink").onclick = async () => {
    try {
      const r = await post("/api/telegram/link");
      $("#tgmsg").innerHTML = r.url ? `Abre <a href="${esc(r.url)}" target="_blank" rel="noopener">este enlace</a> y pulsa «Iniciar» en el bot; luego vuelve aquí.`
        : `Escribe al bot del estudio: <code>/start ${esc(r.code)}</code> (vale 30 min)`;
      if (r.url) window.open(r.url, "_blank");
      const until = Date.now() + 10 * 60000;
      const poll = async () => { if (location.hash !== "#/cuenta" || Date.now() > until) return;
        if ((await api("/api/cuenta")).telegram) return accountPage(); setTimeout(poll, 4000); };
      setTimeout(poll, 4000);
    } catch (e) { $("#tgmsg").textContent = e.message; }
  };
  $("#pw-go").onclick = async () => {
    try { await post("/api/password", {current: $("#pw-old").value, new: $("#pw-new").value}); $("#pw-msg").innerHTML = `<span class="t-ok">${icon("check")}</span> Cambiada`;
      $("#pw-old").value = $("#pw-new").value = ""; }
    catch (e) { $("#pw-msg").textContent = e.message; }
  };
}
