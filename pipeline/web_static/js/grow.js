let statsSort = "views", statsChannel = "";
function benchCard(bench) {
  const r = bench.result, job = bench.job || {};
  const rows = r ? r.summary.map((x, i) => `<tr${i === 0 && x.ok ? ' style="font-weight:700"' : ""}><td>${esc(x.way)}</td><td>${esc(x.client)}</td>
      <td>${x.ok}/${x.of}</td><td>${x.details_s ?? "—"} s</td><td>${x.mbps360 ?? "—"} <span class="muted">(${x.piece360_s ?? "—"} s)</span></td><td>${x.mbps1080 ?? "—"} <span class="muted">(${x.piece1080_s ?? "—"} s)</span></td>
      <td>${esc(x.protocol || "")}</td><td>${x.storyboard ? "✅" : "—"}</td>
      <td class="small muted">${x.ok < x.of ? esc(String(x.error || "").slice(0, 80)) : ""}</td></tr>`).join("") : "";
  return `<div class="card" style="margin-top:20px"><div class="row" style="justify-content:space-between">
      <b>🧪 Prueba de velocidad de YouTube</b>
      <button onclick="runBench(this)" ${job.running ? "disabled" : ""}>${job.running ? "Probando… (5-15 min)" : "Probar ahora"}</button></div>
    <div class="small muted" style="margin-top:4px">Cada proxy × cada cliente de YouTube: cuánto tardan los detalles de un vídeo y a qué velocidad baja un trozo de 360p y de 1080p.
      El de arriba (en negrita) es el más rápido que funciona: dímelo y lo pongo por defecto.</div>
    ${r ? `<div class="small muted" style="margin-top:6px">Última prueba: ${esc(r.at.replace("T", " ").slice(0, 16))}</div>
      <div style="overflow-x:auto"><table style="margin-top:6px"><tr><th>Salida</th><th>Cliente</th><th>Vídeos OK</th><th>Detalles</th><th>360p MB/s (s por trozo)</th><th>1080p MB/s (s por trozo)</th><th>Protocolo</th><th>Storyboard</th><th></th></tr>${rows}</table></div>` : ""}
    ${job.running && job.log ? `<pre style="max-height:160px">${esc(job.log.split("\n").slice(-8).join("\n"))}</pre>` : ""}</div>`;
}
const SCENE_ROWS = [["searches", "Búsquedas"], ["extracts", "Extracciones (detalles)"], ["shotsWithoutYouTube", "Planos sin YouTube"],
  ["optionsPerShot", "Opciones por plano"], ["differentSources", "Fuentes distintas"], ["judgeChoiceKept", "Clip que eligió el juez, aún entre las opciones"],
  ["titleMatch", "Título ↔ plano"], ["searchesWithoutData", "Búsquedas sin datos (caché)"], ["extractsWithoutData", "Vídeos sin datos (caché)"],
  ["visualBest", "CLIP: mejor opción de cada plano"], ["visualAboveFloor", "CLIP: planos sobre el mínimo del juez"],
  ["simulatedSources", "Simulado: fuentes distintas en pantalla"], ["simulatedRepeats", "Simulado: fuentes repetidas"],
  ["simulatedScore", "Simulado: CLIP de lo elegido"], ["simulatedMargin", "Simulado con judge.variety_margin"]];
function sceneCard(bench) {
  const r = bench.result, job = bench.job || {};
  const pct = (k, x) => x == null ? "—" : ["judgeChoiceKept", "titleMatch", "visualAboveFloor", "simulatedRepeats"].includes(k) ? Math.round(x * 100) + " %" : x;
  return `<div class="card" style="margin-top:20px"><div class="row" style="justify-content:space-between">
      <b>🎬 Búsqueda por plano vs por escenas</b>
      <button onclick="runScenes(this)" ${job.running ? "disabled" : ""}>${job.running ? "Comparando…" : "Comparar ahora"}</button></div>
    <div class="small muted" style="margin-top:4px">Sin pedir nada a YouTube: repite las dos formas de buscar con lo guardado de vídeos ya hechos, siempre sobre el mismo conjunto de ~30 escenas.
      Menos búsquedas y extracciones = menos «no eres un bot»; las opciones, las fuentes distintas y el clip que eligió el juez dicen si se pierde calidad.</div>
    ${r ? `<div class="small muted" style="margin-top:6px">${esc(r.at.replace("T", " ").slice(0, 16))} · ${r.scenes} escenas, ${r.set.old.shots} planos${r.api ? " · con la API" : ""}</div>
      <div style="overflow-x:auto"><table style="margin-top:6px"><tr><th></th><th>Por plano</th><th>Por escenas</th></tr>
      ${SCENE_ROWS.filter(([k]) => k in r.set.old).map(([k, label]) => `<tr><td>${label}</td><td>${pct(k, r.set.old[k])}</td><td><b>${pct(k, r.set.new[k])}</b></td></tr>`).join("")}</table></div>
      <div class="small" style="margin-top:8px"><b>Documentales enteros</b> (búsquedas / extracciones):
      ${r.videos.map((v) => `<div>${esc(v.video)}: ${v.old.searches} / ${v.old.extracts} → <b>${v.new.searches} / ${v.new.extracts}</b>
        <span class="muted">(${v.old.shots} planos, ${v.scenes} escenas)</span></div>`).join("")}</div>` : ""}
    ${job.running && job.log ? `<pre style="max-height:160px">${esc(job.log.split("\n").slice(-8).join("\n"))}</pre>` : ""}</div>`;
}

window.runScenes = async (button) => {
  button.disabled = true; await post("/api/scenebench"); setTimeout(() => stats(), 4000);
};
window.runBench = async (button) => {
  if (!confirm("¿Probar ahora? Tarda 5-15 min y hace unas 50 peticiones a YouTube (mejor cuando la cola no esté a tope).")) return;
  button.disabled = true; await post("/api/ytbench"); setTimeout(() => stats(), 3000);
};

async function stats(refresh = false) {
  const [o, spend, st] = [await api("/api/overview"), await api("/api/spending"), await api("/api/stats" + (refresh ? "?refresh=1" : ""))];
  const bench = window.partner ? {} : await api("/api/ytbench").catch(() => ({}));       // the server's: the owner's
  const scenesBench = window.partner ? {} : await api("/api/scenebench").catch(() => ({}));
  const times_ = window.partner ? {} : await api("/api/tiempos").catch(() => ({}));
  const y = o.youtube, max = Math.max(1, ...spend.map((d) => d.usd));
  const vids = st.videos.filter((v) => !statsChannel || v.channel === statsChannel);
  const out = vids.filter((v) => v.youtube).sort((a, b) => (b.youtube[statsSort] ?? -1) - (a.youtube[statsSort] ?? -1));
  const vs = (r) => r == null ? "" : `<span class="pill ${r >= 1.5 ? "hecho" : r < 0.7 ? "error" : ""}">${times(r)}</span>`;
  const mixBar = (mix) => { const total = Object.values(mix).reduce((a, b) => a + b, 0) || 1;
    const colors = {youtube: "#e5534b", fotos: "#3b82f6", stock: "#a371f7", generadas: "#f2cc60", "gráficos": "#3fb950", otros: "#8b949e"};
    return `<div style="display:flex;height:10px;border-radius:5px;overflow:hidden;min-width:120px">${Object.entries(mix).map(([k, n]) =>
      `<i title="${esc(k)}: ${n} planos" style="width:${100 * n / total}%;background:${colors[k] || "#8b949e"}"></i>`).join("")}</div>`; };
  const head = (key, label) => `<th style="cursor:pointer;text-align:right;white-space:nowrap" onclick="statsSort='${key}';stats()">${label}${statsSort === key ? " ▾" : ""}</th>`;
  $("#app").innerHTML = `<div class="row" style="justify-content:space-between"><h1>Estadísticas</h1>
      <div class="row" style="gap:6px"><select style="width:auto" onchange="statsChannel=this.value;stats()"><option value="">Todos los canales</option>
        ${st.channels.map((c) => `<option ${c.channel === statsChannel ? "selected" : ""}>${esc(c.channel)}</option>`).join("")}</select>
      <button onclick="stats(true)">↻ Actualizar de YouTube</button></div></div>
    <div class="small muted">${st.fetched ? "Datos de YouTube de " + new Date(st.fetched * 1000).toLocaleString("es-ES") : "Sin datos de YouTube aún (hace falta el enlace del vídeo: «Ya está subido» con su URL)."}</div>
    ${(() => { const cs = st.channels.filter((c) => !statsChannel || c.channel === statsChannel);
      const sum = (k) => cs.reduce((a, c) => a + (c[k] || 0), 0);
      return `<div class="kpis" style="margin-top:12px">
        <div class="kpi"><div class="k">Visitas</div><div class="v">${kfmt(sum("views"))}</div><div class="d">${sum("published")} vídeos subidos</div></div>
        <div class="kpi"><div class="k">Horas vistas (estimadas)</div><div class="v">${kfmt(sum("watchHours"))} h</div>
          <div class="d">${Math.round(100 * st.retention)} % de cada vídeo de media</div></div>
        <div class="kpi"><div class="k">Hechos</div><div class="v">${sum("made")}</div><div class="d">${sum("made") - sum("published")} por subir</div></div>
        <div class="kpi"><div class="k">Gasto en API</div><div class="v">${sum("usd").toFixed(2)} $</div>
          <div class="d">${sum("views") ? (1000 * sum("usd") / sum("views")).toFixed(3) + " $ / 1.000 visitas" : "—"}</div></div></div>`; })()}

    <h2>Por canal</h2>
    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:10px">${st.channels.filter((c) => !statsChannel || c.channel === statsChannel).map((c) => `<div class="card" style="margin:0;border-top:3px solid ${chColor(c.channel)}">
      <b>${esc(c.channel)}</b><div class="stat">${kfmt(c.views)}</div><div class="small muted">visitas en ${c.published} vídeo(s) subido(s) · ${c.made} hechos</div>
      <div class="small" style="margin-top:8px">⏱ <b>${kfmt(c.watchHours12m)} h</b> de 4.000 h para monetizar <span class="muted">(estimado, últimos 12 meses, sin Shorts)</span></div>
      <div class="bar" style="margin-top:4px"><i style="width:${Math.min(100, c.watchHours12m / 40)}%;background:${chColor(c.channel)}"></i></div>
      <div class="small" style="margin-top:6px">Mediana: <b>${kfmt(c.median)}</b> · coste medio <b>${Number(c.usdPerVideo).toFixed(2)} $</b>${c.usdPer1kViews != null ? ` · ${Number(c.usdPer1kViews).toFixed(3)} $ / 1.000 visitas` : ""}</div>
      ${c.best ? `<div class="small muted" style="margin-top:4px">🏆 ${esc(c.best.title)} (${kfmt(c.best.views)})</div>` : ""}</div>`).join("")}</div>

    <h2>En YouTube</h2>
    ${out.length ? `<div id="yttable"></div>
    <div class="small muted" style="margin-top:6px">«vs canal»: visitas frente a la mediana del mismo canal (en verde 1,5× o más; en rojo, por debajo de 0,7×). 👍 y 💬 por cada 1.000 visitas: cuánto engancha a quien lo ve.
      Horas (est.): visitas × duración × ${Math.round(100 * st.retention)} % (la media de lo que se ve de cada vídeo; pon la tuya de YouTube Studio en
      config.local.yaml → <code>stats: {retention: 0.40}</code>). Las horas exactas, la retención, el CTR y las impresiones solo salen con YouTube Analytics (inicio de sesión del canal).</div>`
      : '<div class="notice">Ningún vídeo subido con su enlace todavía. En «Para subir» o en el vídeo, «Ya está subido» y pega la URL.</div>'}

    <h2>Cómo se hizo cada vídeo</h2>
    <div class="small muted" style="margin:-4px 0 8px">Coste en dinero y cuota de YouTube de cada vídeo; medias por canal en <a href="#/gasto">💸 Gasto de API</a>.</div>
    <div class="card" style="overflow-x:auto;padding:0"><table style="width:100%;border-collapse:collapse;font-size:14px">
      <tr style="text-align:left"><th style="padding:8px">Vídeo</th><th style="text-align:right">Coste</th><th style="text-align:right" title="Unidades de la API de YouTube">Cuota YT</th><th style="text-align:right">Tiempo</th><th style="text-align:right">Duración</th>
        <th style="text-align:right">Cortes/min</th><th>Qué sale en pantalla</th><th style="text-align:right;padding-right:8px;white-space:nowrap">Errores ✅/❌</th></tr>
      ${vids.map((v) => { const p = v.production, l = p.labels; return `<tr style="border-top:1px solid var(--line)">
        <td style="padding:8px"><a href="#/video/${encodeURIComponent(v.slug)}">${esc(v.title)}</a><div class="small muted">${esc(v.channel)} · ${v.status === "subido" ? "en YouTube" : "por subir"}</div></td>
        <td style="text-align:right">${Number(p.usd).toFixed(2)} $</td><td style="text-align:right">${p.ytUnits ? (p.ytEstimated ? "≈ " : "") + kfmt(p.ytUnits) : "—"}</td><td style="text-align:right">${p.minutes} min</td>
        <td style="text-align:right">${Math.floor(p.duration / 60)}:${String(p.duration % 60).padStart(2, "0")}</td><td style="text-align:right">${fmt(p.cutsPerMin)}</td>
        <td style="min-width:150px">${mixBar(p.mix)}<div class="small muted">${Object.entries(p.mix).map(([k, n]) => `${esc(k)} ${n}`).join(" · ")}</div></td>
        <td style="text-align:right;padding-right:8px">${l.correcta || l.incorrecta ? `${l.correcta} / ${l.incorrecta}` : "—"}</td></tr>`; }).join("")}
    </table></div>

    ${window.partner ? "" : benchCard(bench) + sceneCard(scenesBench)}
    ${times_.markdown ? `<h2>⏱ Dónde se va el tiempo</h2><div class="card">${md(times_.markdown.replace(/^# .*\n/, ""))}</div>` : ""}
    <details style="margin-top:24px"><summary class="small muted" style="cursor:pointer">Técnico: descargas de YouTube y gasto de API por día</summary>
    ${y ? `<div class="grid" style="margin-top:10px">
      <div class="card"><div class="muted small">Peticiones (7 días)</div><div class="stat">${y.requests}</div><div class="small muted">${y.ok} bien · ${y.failed} fallidas</div></div>
      <div class="card"><div class="muted small">Errores</div><div class="small" style="margin-top:6px">${Object.entries(y.errors).map(([k, n]) => `${esc(k)}: <b>${n}</b>`).join(" · ") || "ninguno ✅"}</div></div>
      <div class="card"><div class="muted small">Descargas</div><div class="stat">${y.files_ok}/${y.files}</div><div class="small muted">${y.megabytes} MB · ${y.mbps} MB/s</div></div>
      <div class="card"><div class="muted small">Cómo</div><div class="small" style="margin-top:6px">Con cuenta: ${y.with_cookies} · PO Token: ${y.pot ? "sí" : "no"}<br>${esc(y.clients.join(", "))}
        ${y.answer_avg ? `<br>Cada petición: <b>${y.answer_avg} s</b> YouTube + ${y.wait_avg} s en nuestra cola` : ""}</div></div>
    </div>
    ${(y.byProxy || []).length ? `<div class="card" style="margin-top:12px"><b>Por proxy (últimas 24 h)</b>
      <div class="small muted">Por dónde sale cada petición a YouTube. Un proxy con muchas fallidas o «no responde» → reinicia su script; con pocos MB/s → mira su conexión (mejor por cable).</div>
      <table style="margin-top:8px"><tr><th>Proxy</th><th>Peticiones</th><th>Fallidas</th><th>«No eres un bot»</th><th>Descargas</th><th>MB/s</th><th>s por archivo</th></tr>
      ${y.byProxy.map((p) => `<tr><td>${esc(p.proxy)}</td><td>${p.requests}</td>
        <td style="color:${p.requests && p.failed / p.requests > 0.15 ? "var(--bad)" : "inherit"}">${p.failed}${p.requests ? ` (${Math.round(100 * p.failed / p.requests)} %)` : ""}</td>
        <td>${p.errors.bot || 0}</td><td>${p.files_ok}/${p.files}</td><td><b>${p.mbps}</b></td><td>${p.seconds_per_file}</td></tr>`).join("")}</table></div>` : ""}
    ` : '<div class="notice">Todavía no hay datos de YouTube.</div>'}
    <div class="card"><div class="spend">${spend.map((d) => `<div style="height:${100 * d.usd / max}%" title="${d.usd} $"><span>${d.day.slice(5)}</span></div>`).join("")}</div>
      <div style="height:26px"></div><div class="small muted">Total en estos días: ${spend.reduce((a, d) => a + d.usd, 0).toFixed(2)} $</div></div></details>`;
  statsRows = st.videos.filter((v) => v.youtube);
  drawYtTable();
  if (bench.job && bench.job.running) schedule(() => stats(), 15000);      // the speed test shows its progress
}

let expChannel = "";
async function saveExperiment(slug, field, value) {
  try {
    await post(`/api/experimentos/${encodeURIComponent(slug)}`, {[field]: value});
  } catch (e) {
    alert(e.message || e);
  }
}

async function pilotPage() {
  const g = await api("/api/piloto");
  const busy = g.channels.some((c) => c.job && c.job.running);
  $("#app").innerHTML = `
    <h1>Piloto automático</h1>
    <div class="small muted" style="margin:-4px 0 12px">Ideas de lo que funciona hoy en el nicho de cada canal (radar del ${esc(g.radarDate || "—")}).
      «Hacer este vídeo» escribe un vídeo PROPIO sobre ese tema (otro ángulo, nunca una copia), con el guion en el formato del canal; la voz de
      GenAIPro lo lee y la cola lo hace. Con el canal en <b>VÍDEOS ON</b> lo hace solo cada día. Nunca sube nada: el vídeo te espera en «Para subir».</div>
    ${g.channels.map((c) => `<div class="card" style="margin-bottom:14px">
      <div class="row" style="justify-content:space-between;gap:8px;flex-wrap:wrap">
        <div class="row" style="gap:8px"><b style="font-size:18px">${esc(c.channel)}</b>
          <button class="${c.on ? "main" : ""}" onclick="pilotSet('${esc(c.channel)}', {on: ${!c.on}})">${c.on ? "VÍDEOS ON" : "EN PAUSA"}</button>
          <select style="width:auto" onchange="pilotSet('${esc(c.channel)}', {perDay: +this.value})">${[1, 2, 3].map((n) => `<option value="${n}" ${n === c.perDay ? "selected" : ""}>${n} al día</option>`).join("")}</select></div>
        <span class="small">${c.voice ? '<span class="pill hecho">🎙️ voz lista</span>' : '<span class="pill" title="Sin voz de GenAIPro: el vídeo esperará a que subas la voz (Ajustes → Voces)">🎙️ sin voz automática</span>'}</span></div>
      ${c.error ? `<div class="notice bad small">Último intento: ${esc(c.error)}</div>` : ""}
      ${c.job && c.job.running ? '<div class="notice small">✍️ Escribiendo el guion… (un par de minutos)</div>' : ""}
      ${c.job && c.job.failed ? `<div class="notice bad small">${esc((c.job.log || "").trim().split("\n").pop())}</div>` : ""}
      ${c.candidates.length ? c.candidates.map((v) => `<div class="row" style="gap:10px;margin-top:10px;align-items:flex-start">
          ${v.thumbnail ? `<img src="${esc(v.thumbnail)}" style="width:120px;border-radius:6px" loading="lazy">` : ""}
          <div style="flex:1"><a href="${esc(v.url)}" target="_blank" rel="noopener"><b>${esc(v.title)}</b></a>
            <div class="small muted">${v.evidence.map(esc).join(" · ")}</div>
            <div class="row" style="gap:6px;margin-top:6px"><button class="main" ${busy ? "disabled" : ""} onclick="pilotMake('${esc(c.channel)}', '${esc(v.id)}', this)">▶ Hacer este vídeo</button>
              <button onclick="pilotSkip('${esc(c.channel)}', '${esc(v.id)}')">No me interesa</button></div></div></div>`).join("")
        : '<div class="small muted" style="margin-top:8px">Sin ideas todavía: el radar las trae cada día (Crecer › Radar › Buscar ahora).</div>'}
      ${c.made.length ? `<h3 style="margin-top:14px">Hechos por el piloto</h3>${c.made.map((m) => `<div class="small">${esc(m.date)} · <a href="#/video/${encodeURIComponent(m.slug)}">${esc(m.title)}</a>
        <span class="muted">· de «${esc(m.fromTitle || "")}»${m.angle ? " · ángulo: " + esc(m.angle) : ""}</span></div>`).join("")}` : ""}</div>`).join("")}`;
  window.pilotSet = async (channel, change) => { await post(`/api/piloto/${encodeURIComponent(channel)}`, change); pilotPage(); };
  window.pilotSkip = async (channel, id) => { await post(`/api/piloto/${encodeURIComponent(channel)}/saltar`, {id}); pilotPage(); };
  window.pilotMake = async (channel, id, button) => {
    button.disabled = true;
    try { await post(`/api/piloto/${encodeURIComponent(channel)}/hacer`, {id}); } catch (e) { alert(e.message); }
    pilotPage();
  };
  if (busy) timer = setTimeout(() => location.hash === "#/piloto" && pilotPage(), 5000);
}

async function experimentsPage() {
  const g = await api("/api/experimentos");
  const times = (x) => x == null ? "—" : String(x).replace(".", ",") + "×";
  const pct = (x) => x == null ? "" : String(x).replace(".", ",") + " %";
  const kind = {gana: "hecho", falta: "", empate: "error"};
  const rows = g.videos.filter((v) => !expChannel || v.channel === expChannel);
  const channelsList = [...new Set(g.videos.map((v) => v.channel))];
  const top = Math.max(1, ...g.comparisons.flatMap((c) => c.options.map((o) => o.score || 0)));
  $("#app").innerHTML = `
    <h1>Experimentos</h1>
    <div class="small muted" style="margin:-4px 0 12px">Qué ha probado cada vídeo y cómo le ha ido: sus visitas a los 7 días frente a la mediana de su canal
      (1,4× = un 40 % más de lo habitual en ese canal). El formato, la búsqueda, la duración y el ritmo se anotan solos; añade tus etiquetas
      («miniatura con cara», «gancho con pregunta») y, si quieres, la retención y el CTR de YouTube Studio. Cambia una cosa cada vez:
      con ${g.minVideos} vídeos por opción y más de un 25 % de diferencia, hay veredicto.</div>
    <h2>Lo aprendido</h2>
    ${g.comparisons.length ? `<div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(340px,1fr))">${g.comparisons.map((c) => `
      <div class="card"><div class="row" style="justify-content:space-between;gap:8px"><b>${esc(c.factor)}</b>
        <span class="pill ${kind[c.verdict.kind]}">${c.verdict.kind === "gana" ? "veredicto" : c.verdict.kind === "empate" ? "sin diferencia" : "faltan datos"}</span></div>
        <div class="small muted" style="margin:4px 0 8px">${esc(c.verdict.text)}</div>
        ${c.options.map((o) => `<div style="margin-top:6px"><div class="row small" style="justify-content:space-between">
          <span>${esc(o.option)} <span class="muted">· ${o.withResult} de ${o.videos} con 7 días</span></span>
          <span><b>${times(o.score)}</b>${o.retentionAvg != null ? ` <span class="muted">· ret. ${pct(o.retentionAvg)}</span>` : ""}${o.ctr != null ? ` <span class="muted">· CTR ${pct(o.ctr)}</span>` : ""}</span></div>
          <div class="bar"><i style="width:${100 * (o.score || 0) / top}%;background:var(--accent)"></i></div></div>`).join("")}</div>`).join("")}</div>`
      : '<div class="card muted">Aún no hay nada que comparar: hace falta que los vídeos prueben cosas distintas (otro formato, la búsqueda por escenas, una etiqueta…).</div>'}
    <h2>Por vídeo</h2>
    <div class="yt-tools">
      <button class="yt-chip ${expChannel ? "" : "on"}" onclick="expChannel='';experimentsPage()">Todos</button>
      ${channelsList.map((c) => `<button class="yt-chip ${c === expChannel ? "on" : ""}" onclick="expChannel='${esc(c)}';experimentsPage()">
        <i class="dot" style="background:${chColor(c)}"></i>${esc(c)}</button>`).join("")}</div>
    <div class="card" style="overflow:auto;padding:0;max-height:75vh"><table class="ytt">
      <thead><tr><th>Vídeo</th><th>7 días</th><th>Frente al canal</th><th style="text-align:left">Probó</th><th style="text-align:left">Etiquetas</th>
        <th title="Retención a los 30 s (YouTube Studio)">Ret. 30 s %</th><th title="Porcentaje medio visto">Ret. media %</th><th>CTR %</th></tr></thead>
      <tbody>${rows.map((v) => `<tr class="v"><td><a href="#/video/${encodeURIComponent(v.slug)}" style="font-weight:600">${esc(v.slug)}</a>
          <div class="sub"><i class="dot" style="background:${chColor(v.channel)}"></i> ${esc(v.channel)} · ${esc(v.published || v.status)}</div></td>
        <td data-k="7 días">${v.views7d != null ? fmt(v.views7d) : '<span class="muted">—</span>'}</td>
        <td data-k="Frente al canal"><b>${times(v.score)}</b></td>
        <td class="wide small" style="text-align:left">${Object.entries(v.tried).map(([k, x]) => `<span class="pill" title="${esc(k)}">${esc(x)}</span>`).join(" ")}</td>
        <td data-k="Etiquetas" style="text-align:left"><input style="min-width:160px" placeholder="p. ej. miniatura con cara" value="${esc((v.tags || []).join(", "))}"
          onchange="saveExperiment('${esc(v.slug)}', 'tags', this.value).then(experimentsPage)"></td>
        ${["retention30", "retentionAvg", "ctr"].map((k) => `<td data-k="${k}"><input style="width:64px" inputmode="decimal" value="${v[k] ?? ""}"
          onchange="saveExperiment('${esc(v.slug)}', '${k}', this.value).then(experimentsPage)"></td>`).join("")}</tr>`).join("")
        || '<tr><td colspan="8" class="muted" style="text-align:center;padding:20px">Aún no hay vídeos terminados.</td></tr>'}</tbody></table></div>`;
}

// «En YouTube»: sorted, filtered and grouped in the page, without asking the server again
let statsRows = [], statsDir = -1, statsQuery = "", statsGroup = false;
const YT_COLS = [["views", "Visitas"], ["perDay", "Al día"], ["at48h", "48 h"], ["at7d", "7 días"], ["watchHours", "Horas (est.)"],
  ["vsChannel", "vs canal"], ["likesPer1k", "👍/1.000"], ["commentsPer1k", "💬/1.000"], ["ageDays", "Días"]];
function ytSort(key) { statsDir = statsSort === key ? -statsDir : (key === "title" || key === "channel" ? 1 : -1); statsSort = key; drawYtTable(); }
function drawYtTable(typing = false) {
  const box = $("#yttable");
  if (!box) return;
  const q = statsQuery.trim().toLowerCase();
  const val = (v, key) => key === "title" ? (v.youtube.title || v.title || "").toLowerCase() : key === "channel" ? v.channel.toLowerCase() : v.youtube[key];
  const rows = statsRows.filter((v) => (!statsChannel || v.channel === statsChannel)
      && (!q || `${v.youtube.title || ""} ${v.title} ${v.slug} ${v.channel}`.toLowerCase().includes(q)))
    .sort((a, b) => { const x = val(a, statsSort), y = val(b, statsSort);
      if (x == null && y == null) return 0; if (x == null) return 1; if (y == null) return -1;
      return (typeof x === "string" ? x.localeCompare(y) : x - y) * statsDir; });
  const counts = {}; statsRows.forEach((v) => counts[v.channel] = (counts[v.channel] || 0) + 1);
  const maxViews = Math.max(1, ...rows.map((v) => v.youtube.views || 0));
  const arrow = (key) => statsSort === key ? (statsDir > 0 ? " ▴" : " ▾") : "";
  const vs = (r) => r == null ? "—" : `<span class="pill ${r >= 1.5 ? "hecho" : r < 0.7 ? "error" : ""}">${times(r)}</span>`;
  const row = (v) => { const y = v.youtube; return `<tr class="v">
    <td><div class="row" style="gap:10px;flex-wrap:nowrap">
      <a href="${esc(v.url)}" target="_blank" rel="noopener">${y.thumbnail ? `<img class="thumb" src="${esc(y.thumbnail)}" loading="lazy" alt="">` : '<div class="thumb"></div>'}</a>
      <div style="min-width:0"><a href="#/video/${encodeURIComponent(v.slug)}" style="font-weight:600">${esc(y.title || v.title)}</a>
        <div class="sub"><i class="dot" style="background:${chColor(v.channel)}"></i>${esc(v.channel)} · ${esc(v.slug)}${v.publishedDay ? " · " + esc(v.publishedDay) : ""}${y.minutes ? " · " + fmt(y.minutes) + " min" : ""}</div></div></div></td>
    <td data-k="Visitas" title="${fmt(y.views)} visitas"><b>${kfmt(y.views)}</b><div class="vbar" style="width:${Math.max(3, 100 * (y.views || 0) / maxViews)}%"></div></td>
    <td data-k="Al día">${kfmt(y.perDay)}</td><td data-k="48 h" class="wide">${y.at48h != null ? kfmt(y.at48h) : "—"}</td>
    <td data-k="7 días" class="wide">${y.at7d != null ? kfmt(y.at7d) : "—"}</td><td data-k="Horas">${kfmt(y.watchHours)}</td>
    <td data-k="vs canal">${vs(y.vsChannel)}</td><td data-k="👍/1.000">${fmt(y.likesPer1k)}</td>
    <td data-k="💬/1.000" class="wide">${fmt(y.commentsPer1k)}</td><td data-k="Días">${fmt(y.ageDays)}</td></tr>`; };
  let body = "";
  if (statsGroup) {
    const groups = {}; rows.forEach((v) => (groups[v.channel] = groups[v.channel] || []).push(v));
    const order = Object.keys(groups).sort((a, b) => groups[b].reduce((s, v) => s + v.youtube.views, 0) - groups[a].reduce((s, v) => s + v.youtube.views, 0));
    body = order.map((c) => { const g = groups[c], views = g.reduce((s, v) => s + (v.youtube.views || 0), 0), hours = g.reduce((s, v) => s + (v.youtube.watchHours || 0), 0);
      return `<tr class="group"><td colspan="10"><span class="row" style="gap:8px"><i class="dot" style="background:${chColor(c)};width:11px;height:11px"></i>${esc(c)}
        <span class="muted small" style="font-weight:400">${g.length} vídeo(s) · ${kfmt(views)} visitas · ${kfmt(hours)} h (est.)</span></span></td></tr>${g.map(row).join("")}`; }).join("");
  } else body = rows.map(row).join("");
  box.innerHTML = `<div class="yt-tools">
      <input type="search" placeholder="Buscar título o carpeta…" value="${esc(statsQuery)}" oninput="statsQuery=this.value;drawYtTable(true)">
      <button class="yt-chip ${statsChannel ? "" : "on"}" onclick="statsChannel='';drawYtTable()">Todos <span class="muted">${statsRows.length}</span></button>
      ${Object.keys(counts).sort().map((c) => `<button class="yt-chip ${c === statsChannel ? "on" : ""}" onclick="statsChannel='${esc(c)}';drawYtTable()">
        <i class="dot" style="background:${chColor(c)}"></i>${esc(c)} <span class="muted">${counts[c]}</span></button>`).join("")}
      <span class="row small" style="gap:4px;margin-left:auto;flex-wrap:nowrap">Ordenar:
        <select style="width:auto" onchange="statsSort=this.value;statsDir=['title','channel'].includes(this.value)?1:-1;drawYtTable()">
          ${[["channel", "Canal"], ["title", "Título"], ...YT_COLS].map(([k, label]) => `<option value="${k}" ${statsSort === k ? "selected" : ""}>${label}</option>`).join("")}</select>
        <button title="Al revés" onclick="statsDir=-statsDir;drawYtTable()">${statsDir > 0 ? "▴" : "▾"}</button></span>
      <label class="small" style="display:flex;gap:6px;align-items:center;cursor:pointer;white-space:nowrap">
        <input type="checkbox" ${statsGroup ? "checked" : ""} onchange="statsGroup=this.checked;drawYtTable()"> Agrupar por canal</label></div>
    <div class="card" style="overflow:auto;padding:0;max-height:75vh"><table class="ytt">
      <thead><tr><th class="${statsSort === "title" ? "on" : ""}" onclick="ytSort('title')">Vídeo${arrow("title")}
        <span style="margin-left:10px" class="${statsSort === "channel" ? "on" : ""}" onclick="event.stopPropagation();ytSort('channel')">· Canal${arrow("channel")}</span></th>
        ${YT_COLS.map(([k, label]) => `<th class="${statsSort === k ? "on" : ""} ${["at48h", "at7d", "commentsPer1k"].includes(k) ? "wide" : ""}" onclick="ytSort('${k}')">${label}${arrow(k)}</th>`).join("")}</tr></thead>
      <tbody>${body || '<tr><td colspan="10" class="muted" style="text-align:center;padding:20px">Ningún vídeo con ese filtro.</td></tr>'}</tbody>
    </table></div>
    <div class="small muted" style="margin-top:4px">${rows.length} de ${statsRows.length} vídeos · ${kfmt(rows.reduce((s, v) => s + (v.youtube.views || 0), 0))} visitas · ${kfmt(rows.reduce((s, v) => s + (v.youtube.watchHours || 0), 0))} h (est.) · toca una columna para ordenar (otra vez: al revés)</div>`;
  if (typing) { const input = box.querySelector("input[type=search]"); input.focus(); input.setSelectionRange(input.value.length, input.value.length); }
}

// --- Competencia ---------------------------------------------------------------------------------------------------
let radarChannel = null;
// the same formula as radar.viral_score(): log scale of the multiple over its channel (10x → 50, 100x → 100), +10 in its first week
function viralScore(v) {
  if (v.viral != null) return v.viral;
  const r = +v.ratio || 0;
  return r <= 1 ? 0 : Math.max(0, Math.min(100, Math.round(50 * Math.log10(r)) + ((v.ageDays ?? 99) <= 7 ? 10 : 0)));
}
function viralBadge(v) {
  const n = viralScore(v), color = n >= 60 ? "#3fb950" : n >= 35 ? "#f2cc60" : "#8b949e";
  return `<span title="Puntuación viral 0-100: cuánto supera a su propio canal (y +10 si tiene menos de una semana)"
    style="display:inline-flex;align-items:center;gap:4px;border:2px solid ${color};color:${color};border-radius:999px;padding:1px 8px;font-weight:800">${n >= 60 ? "🔥" : ""}${n}<span style="font-size:10px;font-weight:600">VIRAL</span></span>`;
}
function videoTile(v, actions = "") {
  return `<div class="card"><a href="${esc(v.url)}" target="_blank" rel="noopener"><img loading="lazy" src="${esc(v.thumbnail)}" alt=""></a>
    <div class="body"><div class="row" style="justify-content:space-between"><span class="row" style="gap:8px">${viralBadge(v)}<span class="big">${times(v.ratio)}</span></span>${v.new ? '<span class="pill hecho">nuevo</span>' : ""}</div>
    <a href="${esc(v.url)}" target="_blank" rel="noopener" style="display:block;margin:4px 0;color:var(--text)">${esc(v.title)}</a>
    <div class="small muted">${esc(v.channel)}${v.subscribers != null ? " · " + kfmt(v.subscribers) + " subs" : ""} · ${kfmt(v.views)} visitas · hace ${v.ageDays} días</div>
    ${v.why ? `<div class="small muted">${esc(v.why)}</div>` : ""}${actions ? `<div class="row" style="margin-top:8px">${actions}</div>` : ""}</div></div>`;
}

// --- ideas: for a niche, or «like this video» ---------------------------------------------------------------------
let ideaSeeds = [], shownIdeas = {};
function seedButton(seed, label) {
  ideaSeeds.push(seed);
  return `<button onclick="openIdeas(${ideaSeeds.length - 1})">${label}</button>`;
}
function ideaCard(i, channel) {
  shownIdeas[i.id] = i;
  return `<div class="card idea"><h3>${esc(i.title)}</h3>
    <div class="row small">${i.format ? `<span class="pill">${esc(i.format)}</span>` : ""}${i.protagonist ? `<span class="muted">${esc(i.protagonist)}</span>` : ""}</div>
    <p>${esc(i.angle)}</p>${i.hook ? `<p class="small"><b>Gancho:</b> ${esc(i.hook)}</p>` : ""}
    ${i.outline && i.outline.length ? `<ol class="small">${i.outline.map((x) => `<li>${esc(x)}</li>`).join("")}</ol>` : ""}
    ${i.footage ? `<p class="small muted"><b>Metraje:</b> ${esc(i.footage)}</p>` : ""}
    ${i.why ? `<p class="small muted"><b>Por qué:</b> ${esc(i.why)}</p>` : ""}
    ${i.research ? `<p class="small muted"><b>Comprobar antes:</b> ${esc(i.research)}</p>` : ""}
    <div class="row" style="margin-top:8px"><button class="main" onclick="ideaToVideo('${i.id}','${esc(channel || "")}')">Crear vídeo</button>
      <button onclick="saveIdea('${i.id}','${esc(channel || "")}',this)">Guardar</button></div></div>`;
}
function closeIdeas() { const m = document.getElementById("modal"); if (m) m.remove(); route(); }
async function openIdeas(n, more = false) {
  const seed = ideaSeeds[n];
  let box = document.getElementById("modal");
  if (!box) { box = document.createElement("div"); box.id = "modal"; box.className = "modal"; box.onclick = (e) => e.target === box && closeIdeas(); document.body.appendChild(box); }
  const title = seed.kind === "niche" ? `Ideas · ${esc(seed.name || seed.query)}` : `Ideas como «${esc(seed.title)}»`;
  const keep = more && box.querySelector("#ideas-list") ? box.querySelector("#ideas-list").innerHTML : "";
  box.innerHTML = `<div><div class="row" style="justify-content:space-between"><h1 style="margin:0">${title}</h1><button onclick="closeIdeas()">✕</button></div>
    <div id="ideas-list">${keep}</div><div class="notice" id="ideas-wait">Pensando ideas a partir de lo que funciona… (~20-40 s)</div></div>`;
  try {
    const r = await post("/api/ideas", {seed, more});
    const channel = seed.channel || (seed.near && seed.near !== "libre" ? seed.near : "");
    box.firstElementChild.innerHTML = `<div class="row" style="justify-content:space-between"><h1 style="margin:0">${title}</h1><button onclick="closeIdeas()">✕</button></div>
      <div class="small muted" style="margin-top:6px">Basadas en ${r.evidence.length} vídeos que superan a su canal: ${r.evidence.slice(0, 3).map((v) => "«" + esc(v.title) + "»").join(", ")}…</div>
      <div id="ideas-list">${r.ideas.map((i) => ideaCard(i, channel)).join("")}</div>
      <div class="row" style="margin-top:16px"><button onclick="openIdeas(${n}, true)">Más ideas</button>
        ${seed.kind === "niche" ? `<button onclick="nicheChannel(${n})">Convertir este nicho en canal</button>` : ""}</div>`;
  } catch (e) { const w = box.querySelector("#ideas-wait"); if (w) { w.className = "notice bad"; w.textContent = e.message; } }
}
async function saveIdea(id, channel, button) {
  await post("/api/ideas/save", {idea: shownIdeas[id], channel}); button.textContent = "Guardada ✓"; button.disabled = true;
}
function ideaToVideo(id, channel) {
  try { sessionStorage.setItem("prefill", JSON.stringify({idea: shownIdeas[id], channel})); } catch (e) {}
  window.prefill = {idea: shownIdeas[id], channel};
  const m = document.getElementById("modal"); if (m) m.remove();
  location.hash = "#/nuevo";
}
async function nicheChannel(n) {
  const seed = ideaSeeds[n];
  const name = prompt("Nombre del canal nuevo (sin espacios):", (seed.name || seed.query).toLowerCase().normalize("NFD").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 30));
  if (!name) return;
  try { const r = await post("/api/niche-channel", {query: seed.query, name});
    alert(`Canal «${r.channel}» creado: el radar lo sigue desde mañana` + (r.competitors.length ? ` (competidores: ${r.competitors.join(", ")})` : "") + ". Ponle colores y formato en canales/" + r.channel + ".yaml cuando quieras.");
    data = null;
  } catch (e) { alert(e.message); }
}
let newsTab = null, nicheFilter = "todos", gapFilter = "todos";
async function radarPage() {
  const r = await api("/api/radar");
  ideaSeeds = [];
  const latest = r.latest, names = latest ? Object.keys(latest.channels) : [];
  radarChannel = names.includes(radarChannel) ? radarChannel : names[0];
  const info = latest && radarChannel ? latest.channels[radarChannel] : null;
  const news = r.news, newsNames = news ? Object.keys(news.channels) : [];
  newsTab = newsNames.includes(newsTab) ? newsTab : newsNames[0];
  window.newsIdeas = {};
  const ago = (h) => h < 1 ? "hace un momento" : h < 24 ? `hace ${Math.round(h)} h` : `hace ${Math.round(h / 24)} d`;
  const storyCard = (st, i, channel) => { window.newsIdeas[i] = {...st.idea, channel: channel || undefined};
    const label = st.idea && st.idea.format === "caida-y-regreso" ? "✍️ Guion «caída y regreso»" : "✍️ Guion «caso real»";
    return `<div class="card" style="margin:0">
      <div class="row" style="justify-content:space-between;align-items:flex-start"><div><div style="font-size:1.25em;font-weight:700">${esc(st.name)}</div>
        <div class="small muted">${kfmt(st.views)} visitas · ${st.channels} canal(es) lo cuentan</div></div>
        <span class="pill ${st.channels >= 2 ? "error" : "haciendo"}" title="visitas por hora entre todos sus vídeos">🔥 ${kfmt(st.speed)}/h</span></div>
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin-top:10px">${st.videos.slice(0, 3).map((v) =>
        `<a href="${esc(v.url)}" target="_blank" rel="noopener" style="text-decoration:none;color:inherit"><img loading="lazy" src="${esc(v.thumbnail)}" style="width:100%;border-radius:6px">
          <div class="small" style="line-height:1.25;margin-top:2px">${esc(v.title.slice(0, 70))}</div>
          <div class="small muted">${esc(v.channel)} · ${kfmt(v.perHour)}/h · ${ago(v.ageHours)}</div></a>`).join("")}</div>
      <div class="row" style="margin-top:10px;gap:6px"><button class="main" onclick="newsDraft('${i}', this)">${label}</button>
        <button onclick="newsSave('${i}', this)">Guardar idea</button></div></div>`; };
  const originLabel = (n) => n.near === "descubierto" ? "🔎 descubierto en YouTube" : n.near === "libre" ? "✨ tema libre" : "🧭 cerca de " + n.near;
  const niches = r.niches.filter((n) => nicheFilter === "todos" || (nicheFilter === "descubiertos" ? n.near === "descubierto"
    : nicheFilter === "libres" ? n.near === "libre" : !["descubierto", "libre"].includes(n.near)));
  const scoreColor = (x) => x >= 7 ? "var(--ok)" : x >= 4 ? "var(--accent)" : "var(--muted,#888)";
  $("#app").innerHTML = `<div class="row" style="justify-content:space-between"><h1>Radar</h1>
      <div class="row" style="gap:6px"><button onclick="runNews()" ${r.newsJob.running ? "disabled" : ""}>📰 Noticias ahora</button>
      <button class="main" onclick="runRadar()" ${r.job.running ? "disabled" : ""}>Buscar todo ahora</button></div></div>
    <div class="small muted">${latest ? `Radar del ${esc(latest.date)} · se hace solo cada día a las 13:00 y te llega el resumen por Telegram` : "Todavía no hay radar: pulsa «Buscar todo ahora» (necesita YOUTUBE_API_KEY)."}
      ${latest && latest.outOfQuota ? " · ⚠ se acabó la cuota de la API a mitad" : ""}</div>
    ${jobLine(r.job, "Buscando en YouTube")}${jobLine(r.newsJob, "Buscando noticias")}

    <h2>🚀 Canales revelación</h2>
    <div class="small muted">Canales pequeños (menos de 50 mil subs) con vídeos recientes que multiplican sus suscriptores en visitas:
      YouTube está empujando ese formato a gente que no los sigue. «Encaje» = si esta herramienta lo puede hacer (voz + archivo + gráficos).</div>
    ${latest && latest.rising && latest.rising.length ? `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:12px;margin-top:10px">${latest.rising.map((c) => `<div class="card" style="margin:0">
      <div class="row" style="justify-content:space-between;align-items:flex-start;flex-wrap:nowrap;gap:8px">
        <div class="row" style="gap:8px;flex-wrap:nowrap">${c.thumbnail ? `<img src="${esc(c.thumbnail)}" style="width:40px;height:40px;border-radius:50%">` : ""}
          <div><a href="${esc(c.url)}" target="_blank" rel="noopener" style="font-weight:700">${esc(c.title)}</a>${c.new ? ' <span class="pill hecho">nuevo</span>' : ""}
          <div class="small muted">${kfmt(c.subscribers)} subs · ${c.videos} vídeos · canal de hace ${c.ageDays} días</div></div></div>
        ${c.fit != null ? `<div style="text-align:center;min-width:52px"><div style="font-size:1.5em;font-weight:800;color:${c.fit >= 7 ? "var(--ok)" : c.fit >= 4 ? "var(--accent)" : "var(--muted,#888)"}">${c.fit}</div><div class="small muted">encaje</div></div>` : ""}</div>
      <a href="${esc(c.best.url)}" target="_blank" rel="noopener" style="display:block;margin-top:8px;text-decoration:none;color:inherit">
        <img loading="lazy" src="${esc(c.best.thumbnail)}" style="width:100%;border-radius:6px">
        <div class="small" style="margin-top:4px">${esc(c.best.title)}</div></a>
      <div class="row" style="gap:6px;flex-wrap:wrap;margin-top:6px"><span class="pill error">🔥 ${kfmt(c.best.views)} visitas = ${fmt(c.multiple)}× sus subs</span>
        ${c.medianViews ? `<span class="pill">mediana ${kfmt(c.medianViews)}</span>` : ""}</div>
      ${c.format ? `<div style="margin-top:8px"><b>${esc(c.format)}</b></div>` : ""}
      ${c.why ? `<div class="small muted">${esc(c.why)}</div>` : ""}
      ${c.how ? `<div class="small" style="margin-top:4px">👉 ${esc(c.how)}</div>` : ""}
      ${c.latest && c.latest.length ? `<details style="margin-top:6px"><summary class="small muted" style="cursor:pointer">Sus últimos vídeos</summary>
        <div class="small">${c.latest.map((v) => `<div>· <a href="${esc(v.url)}" target="_blank" rel="noopener">${esc(v.title)}</a> — ${kfmt(v.views)}</div>`).join("")}</div></details>` : ""}
      ${c.query ? `<div class="row" style="margin-top:8px">${seedButton({kind: "niche", query: c.query, name: c.niche || c.format, near: "revelación"}, "💡 Ideas con este formato")}</div>` : ""}
    </div>`).join("")}</div>` : '<div class="notice">Sale con el radar de cada día (a las 13:00) o con «Buscar todo ahora».</div>'}

    <h2>🎯 Huecos: público y poca competencia</h2>
    <div class="small muted">Cada tema se mide en YouTube: <b>demanda</b> (mediana de visitas de los vídeos más vistos del último año),
      <b>competencia</b> (vídeos largos en español subidos en 30 días), <b>canales pequeños que ganan</b>, cuánto se llevan los canales grandes
      y el <b>hueco frente al inglés</b> (×N = el mismo tema tiene N veces más público en inglés). Verde = hueco: entra antes que nadie.</div>
    <div class="row" style="gap:6px;margin:10px 0"><input id="gapTopic" placeholder="Mide un tema que tengas en mente: p. ej. «desastres de ingeniería»" style="flex:1;min-width:220px">
      <button class="main" onclick="measureGap(this)">📏 Medir (~20 s)</button></div>
    ${r.gaps && r.gaps.length ? `<div class="chips" style="margin-bottom:8px">${["todos", "hueco", "hueco en inglés", "a vigilar", "saturado", "sin demanda"].map((f) =>
      `<a href="javascript:gapFilter='${f}';route()" style="${f === gapFilter ? "font-weight:700;text-decoration:underline" : ""}">${f === "todos" ? "Todos" : f}</a>`).join("")}</div>
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:12px">${r.gaps.filter((g) => gapFilter === "todos" || g.verdict === gapFilter).map((g) => {
        const color = {"hueco": "var(--ok)", "hueco en inglés": "var(--ok)", "a vigilar": "var(--accent)"}[g.verdict] || "var(--muted,#888)";
        const trend = g.trend == null ? "" : g.trend > 0 ? ` <span class="small" style="color:var(--ok)">▲${fmt(g.trend)}</span>` : g.trend < 0 ? ` <span class="small" style="color:var(--err,#c33)">▼${fmt(-g.trend)}</span>` : "";
        return `<div class="card" style="margin:0">
        <div class="row" style="justify-content:space-between;align-items:flex-start;flex-wrap:nowrap;gap:8px"><div>
          <div style="font-size:1.15em;font-weight:700">${esc(g.name)}${g.new ? ' <span class="pill hecho">nuevo</span>' : ""}</div>
          <div class="small muted">«${esc(g.query_es)}»${g.query_en ? ` · 🇬🇧 «${esc(g.query_en)}»` : ""} · ${esc(g.date)}${g.origin === "manual" ? " · medido por ti" : ""}</div></div>
          <div style="text-align:center;min-width:60px"><div style="font-size:1.6em;font-weight:800;color:${color}">${fmt(g.score)}${trend}</div>
            <div class="small" style="color:${color};font-weight:700">${esc(g.verdict)}</div></div></div>
        <div class="hbar" style="margin:8px 0"><i style="width:${10 * g.score}%;background:${color}"></i></div>
        <div class="row" style="gap:6px;flex-wrap:wrap">
          <span class="pill" title="mediana de visitas de los vídeos más vistos del último año en español">👁 ${kfmt(g.demand)} · ${kfmt(g.perDay)}/día</span>
          <span class="pill ${g.recent <= 10 ? "hecho" : g.recent >= 30 ? "error" : ""}" title="vídeos largos en español sobre esto en los últimos 30 días (${g.recentChannels} canales)">📅 ${g.recent} vídeos/mes</span>
          <span class="pill ${g.smallWins ? "hecho" : ""}" title="vídeos del top de canales de menos de 50 mil subs con muchas más visitas que suscriptores">🌱 ${g.smallWins} pequeños ganan</span>
          <span class="pill ${g.bigShare >= 0.6 ? "error" : ""}" title="parte de las visitas del top que se llevan canales de más de 500 mil subs">🏢 ${Math.round(100 * g.bigShare)} % grandes</span>
          ${g.englishGap ? `<span class="pill ${g.englishGap >= 3 ? "hecho" : ""}" title="mediana en inglés: ${kfmt(g.englishDemand)}">🇬🇧 ×${fmt(g.englishGap)}</span>` : ""}
          ${g.searched != null ? `<span class="pill" title="sugerencias del buscador de YouTube en español (0-10): la gente lo escribe">🔎 ${g.searched}/10</span>` : ""}
          ${g.fit != null ? `<span class="pill" title="si esta herramienta lo puede hacer">🤖 encaje ${g.fit}/10</span>` : ""}</div>
        ${g.why ? `<div class="small" style="margin-top:6px">${esc(g.why)}</div>` : ""}
        ${g.examples && g.examples.length ? `<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:4px;margin-top:8px">${g.examples.map((v) =>
          `<a href="${esc(v.url)}" target="_blank" rel="noopener" title="${esc(v.title)} · ${kfmt(v.views)} visitas · ${esc(v.channel || "")}${v.subscribers != null ? " (" + kfmt(v.subscribers) + " subs)" : ""}"><img loading="lazy" src="${esc(v.thumbnail)}" style="width:100%;border-radius:6px"></a>`).join("")}</div>` : ""}
        ${g.ideas && g.ideas.length ? `<div class="small" style="margin-top:6px">${g.ideas.map((t) => `<div>💡 ${esc(t)}</div>`).join("")}</div>` : ""}
        <div class="row" style="margin-top:8px;gap:6px">${seedButton({kind: "niche", query: g.query_es, name: g.name, near: "hueco"}, "💡 Más ideas")}
          <a class="small" href="https://www.youtube.com/results?search_query=${encodeURIComponent(g.query_es)}" target="_blank" rel="noopener">Ver en YouTube ↗</a></div>
      </div>`; }).join("")}</div>` : '<div class="notice">Salen con el radar de cada día (a las 13:00), o mide tú un tema arriba.</div>'}

    ${news && news.comebacks && Object.keys(news.comebacks).length ? `<h2>🔁 Caída y regreso: candidatos de hoy</h2>
      <div class="small muted">Deportistas que vuelven a ser noticia estos días: su historia entera (la caída, el fondo, el regreso) con el formato «caída y regreso».</div>
      ${Object.entries(news.comebacks).map(([name, stories]) => `<div style="margin-top:10px"><b>${esc(name)}</b>
        <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:12px;margin-top:6px">${stories.map((st, i) => storyCard(st, `c-${name}-${i}`, name)).join("")}</div></div>`).join("")}` : ""}

    <h2>📰 Noticias del día</h2>
    <div class="small muted">Historias de tus nichos que están subiendo ahora (vídeos de las últimas 48 h). Un vídeo en 24 h sobre ellas llega cuando la gente lo busca.
      ${news ? `Actualizado: ${esc(news.at.replace("T", " "))}.` : ""}</div>
    ${news ? `<div class="tabs">${newsNames.map((n) => `<button class="${n === newsTab ? "on" : ""}" onclick="newsTab='${esc(n)}';route()">${esc(n)} (${news.channels[n].length})</button>`).join("")}</div>
      ${(news.channels[newsTab] || []).length ? `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:12px">${news.channels[newsTab].map((st, i) => storyCard(st, i)).join("")}</div>`
        : '<div class="notice">Nada sube con fuerza ahora en este nicho. Pon búsquedas propias en canales/<canal>.yaml → radar.news_queries.</div>'}
      ${news.errors && news.errors.length ? `<div class="small muted" style="margin-top:6px">${news.errors.map(esc).join(" · ")}</div>` : ""}`
      : '<div class="notice">Aún no hay noticias: pulsa «📰 Noticias ahora».</div>'}

    <h2>🏆 Lo que mejor funciona en tus nichos</h2>
    ${names.length ? `<div class="tabs">${names.map((n) => `<button class="${n === radarChannel ? "on" : ""}" onclick="radarChannel='${esc(n)}';route()">${esc(n)}
      (${latest.channels[n].top.filter((v) => v.new).length} nuevos)</button>`).join("")}</div>` : ""}
    ${info ? `${info.top.length ? `<div class="vids">${info.top.map((v) => videoTile(v, seedButton({kind: "video", id: v.id, title: v.title,
        author: v.channel, views: v.views, ratio: v.ratio, channel: radarChannel}, "💡 Ideas como este"))).join("")}</div>` : '<div class="notice">Nada por encima de 2× en estos días. Añade competidores en canales/' + esc(radarChannel) + '.yaml (ideas.competitors).</div>'}
      ${info.errors.length ? `<div class="small muted" style="margin-top:8px">${info.errors.map(esc).join(" · ")}</div>` : ""}` : '<div class="notice">Sale con el primer radar completo.</div>'}
    ${r.saved.length ? `<h2>Ideas guardadas (${r.saved.length})</h2><div class="card">${r.saved.map((i) => { shownIdeas[i.id] = i;
      return `<div class="trait"><div class="row"><b>${esc(i.title)}</b><span class="small muted">${esc(i.channel || "")}${i.format ? " · " + esc(i.format) : ""}</span></div>
      <div class="small muted">${esc(i.angle || "")}</div><div class="row" style="margin-top:6px"><button class="main" onclick="ideaToVideo('${i.id}','${esc(i.channel || "")}')">Crear vídeo</button>
      <button onclick="post('/api/ideas/save', {remove: '${i.id}'}).then(route)">Quitar</button></div></div>`; }).join("")}</div>` : ""}

    <h2>🧭 Nichos nuevos</h2>
    <div class="small muted">Cada día busca en YouTube vídeos de canales pequeños (menos de 100 mil subs) que triplican sus visitas normales, los agrupa en nichos y los mide.
      Nota alta = muchos éxitos de canales pequeños: un canal nuevo puede entrar.</div>
    <div class="chips" style="margin:10px 0">${["todos", "descubiertos", "cerca", "libres"].map((f) => `<a href="javascript:nicheFilter='${f}';route()" class="${f === nicheFilter ? "on" : ""}"
      style="${f === nicheFilter ? "font-weight:700;text-decoration:underline" : ""}">${{todos: "Todos", descubiertos: "🔎 Descubiertos en YouTube", cerca: "🧭 Cerca de mis canales", libres: "✨ Libres"}[f]}</a>`).join("")}</div>
    ${niches.length ? `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px">${niches.map((n) => `<div class="card" style="margin:0">
      <div class="row" style="justify-content:space-between;align-items:flex-start"><div><div style="font-size:1.15em;font-weight:700">${esc(n.name)}</div>
        <div class="small muted">${originLabel(n)} · ${esc(n.date)}</div></div>
        <div style="text-align:center;min-width:56px"><div style="font-size:1.6em;font-weight:800;color:${scoreColor(n.score)}">${fmt(n.score)}</div><div class="small muted">/10</div></div></div>
      <div class="hbar" style="margin:8px 0"><i style="width:${10 * n.score}%;background:${scoreColor(n.score)}"></i></div>
      ${n.examples.length ? `<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:4px">${n.examples.slice(0, 3).map((v) => `<a href="${esc(v.url)}" target="_blank" rel="noopener" title="${esc(v.title)} · ${times(v.ratio)} · ${esc(v.channel || "")}"><img loading="lazy" src="${esc(v.thumbnail)}" style="width:100%;border-radius:6px"></a>`).join("")}</div>` : ""}
      <div class="row" style="gap:6px;flex-wrap:wrap;margin-top:8px">
        <span class="pill hecho" title="éxitos de canales pequeños">🌱 ${n.smallHits} pequeños</span>
        <span class="pill" title="vídeos que triplican a su canal">🚀 ${n.hits} éxitos</span>
        <span class="pill" title="mediana de visitas">👁 ${kfmt(n.medianViews)}</span>
        <span class="pill" title="mediana frente a lo normal del canal">${times(n.medianRatio)}</span></div>
      ${n.why ? `<div class="small" style="margin-top:6px">${esc(n.why)}</div>` : ""}
      <div class="small muted">«${esc(n.query)}»</div>
      <div class="row" style="margin-top:8px">${seedButton({kind: "niche", query: n.query, name: n.name, near: n.near}, n.ideas ? `💡 Ver ideas (${n.ideas})` : "💡 Ideas para este nicho")}</div>
    </div>`).join("")}</div>` : '<div class="notice">Aún no hay nichos en este filtro.</div>'}`;
  if (window.partner) {          // a partner: their channels' competitors and news; the server-wide finds are the owner's
    for (const h of [...document.querySelectorAll("#app h2")].filter((x) => /^(🚀|🎯|🧭)/.test(x.textContent.trim()))) {
      let next = h.nextElementSibling;
      while (next && next.tagName !== "H2") { const gone = next; next = next.nextElementSibling; gone.remove(); }
      h.remove();
    }
    document.querySelectorAll('#app button[onclick^="runNews"], #app button[onclick^="runRadar"]').forEach((b) => b.remove());
    document.querySelectorAll("#app .notice, #app .small").forEach((n) => { if (/pulsa «(Buscar todo ahora|📰 Noticias ahora)»/.test(n.textContent))
      n.textContent = "Todavía no hay: llega con el radar de cada día."; });
    $("#app h1").insertAdjacentHTML("afterend", '<div class="small muted">El radar se actualiza solo cada día con los competidores de tus canales (los pones al crear el canal).</div>');
  }
  window.runRadar = async () => { await post("/api/radar"); route(); };
  window.measureGap = async (button) => {
    const topic = ($("#gapTopic").value || "").trim();
    if (!topic) return;
    button.disabled = true; button.textContent = "Midiendo…";
    try { await post("/api/radar/gap", {topic}); gapFilter = "todos"; route(); }
    catch (e) { alert(e.message); button.disabled = false; button.textContent = "📏 Medir (~20 s)"; }
  };
  window.runNews = async () => { await post("/api/news"); route(); };
  window.newsDraft = async (i, button) => {
    const idea = window.newsIdeas[i], channel = idea.channel || (newsTab === "general" ? (data && data.channels ? data.channels[0] : "") : newsTab);
    const label = button.textContent;
    button.disabled = true; button.textContent = "Escribiendo… (~1 min)";
    try {
      const d = await post("/api/scripts/draft", {channel, idea});
      if (d.check) alert(`Borrador de ${d.words} palabras con ${d.check} dato(s) [COMPROBAR]: revísalos antes de crear el vídeo.`);
      const pre = {channel, idea: {...idea, title: d.title || idea.title, format: d.format || "caso-real"}, script: d.script};
      try { sessionStorage.setItem("prefill", JSON.stringify(pre)); } catch (e) {}
      window.prefill = pre; location.hash = "#/nuevo";
    } catch (e) { alert(e.message); button.disabled = false; button.textContent = label; }
  };
  window.newsSave = async (i, button) => {
    const idea = window.newsIdeas[i];
    await post("/api/board/idea", {title: idea.title, channel: idea.channel || (newsTab === "general" ? "" : newsTab), note: idea.note.slice(0, 600)});
    button.textContent = "Guardada en Tablero ✓"; button.disabled = true;
  };
  if (r.job.running || r.newsJob.running) schedule(route, 8000);
}

// --- Mi canal --------------------------------------------------------------------------------------------------------
let myChannel = null;
function heatColor(r) {
  if (r == null) return "#30363d";
  const scale = ["#e5534b", "#a8302c", "#5c1f1d", "#3a3f46", "#1c3a6e", "#1f5fbf", "#3b8bf0", "#a8cdfb"];
  const steps = [0.5, 0.7, 0.9, 1.1, 1.3, 1.6, 2.0];
  return scale[steps.filter((s) => r >= s).length];
}
async function channelPage() {
  data = data && data.channels ? data : await api("/api/overview");
  myChannel = myChannel || data.channels[0];
  const c = await api("/api/mychannel/" + encodeURIComponent(myChannel));
  const r = c.report;
  const head = `<div class="row" style="justify-content:space-between"><h1>Mi canal</h1>
      <div class="row"><select onchange="myChannel=this.value;route()" style="width:auto">${data.channels.map((n) => `<option ${n === myChannel ? "selected" : ""}>${esc(n)}</option>`).join("")}</select>
      <button class="main" onclick="analyse()" ${c.job.running || !c.handle ? "disabled" : ""}>Analizar ahora</button></div></div>
    ${c.handle ? `<div class="small muted">${esc(c.handle)}${r ? " · análisis del " + new Date(r.generated).toLocaleString("es-ES") : ""}</div>`
      : `<div class="notice">¿Cuál es este canal en YouTube?
          <div class="row" style="margin-top:8px"><input id="myhandle" placeholder="@TuCanal" style="max-width:260px">
          <button class="main" onclick="post('/api/mychannel/' + encodeURIComponent(myChannel) + '/handle', {handle: $('#myhandle').value}).then(route)">Guardar</button></div></div>`}
    ${jobLine(c.job, "Analizando el canal")}`;
  window.analyse = async () => { await post("/api/mychannel/" + encodeURIComponent(myChannel)); route(); };
  if (c.job.running) schedule(route, 6000);
  if (!r) { $("#app").innerHTML = head + (c.handle ? '<div class="notice">Pulsa «Analizar ahora» (necesita YOUTUBE_API_KEY).</div>' : ""); return; }
  const n = r.numbers, maxMonth = Math.max(1, ...r.months.map((m) => m.long + m.shorts));
  const maxDay = Math.max(2, ...r.perDay.map((d) => d.ratio || 0));
  const card = (label, value, sub) => `<div class="card"><div class="muted small">${label}</div><div class="stat">${value}</div><div class="small muted">${sub || ""}</div></div>`;
  const diverge = (f) => { const w = Math.min(50, Math.abs(Math.log2(f)) * 60);
    return `<div class="diverge"><i style="${f >= 1 ? `left:50%;width:${w}%;background:#3b82f6` : `right:50%;width:${w}%;background:#e5534b`}"></i></div>`; };
  $("#app").innerHTML = head + `
    <div class="chips">${["Números", "Evolución", "Ganadores", "Horarios", "Constancia", "Títulos", "Duración", "Temas"].map((t) => `<a href="javascript:document.getElementById('k-${t}').scrollIntoView({behavior:'smooth'})">${t}</a>`).join("")}</div>
    ${r.tips.length ? `<div class="elf">🧝 ${r.tips.map(esc).join("<br>")}</div>` : ""}

    <div class="kicker" id="k-Números">Números</div><h2>${esc(r.channel.title || "")}</h2>
    <div class="grid">${card("Suscriptores", kfmt(n.subscribers))}${card("Visitas totales", kfmt(n.views))}
      ${card("Vídeos", fmt(n.videos), `${n.long} largos · ${n.shorts} Shorts analizados`)}
      ${card("Lo normal (mediana)", kfmt(n.medianLong), `largos · Shorts ${kfmt(n.medianShort)}`)}
      ${card("Éxitos", fmt(n.hits), "vídeos con 2× o más")}${card("Últimos 28 días", fmt(n.last28.videos) + " vídeos", kfmt(n.last28.views) + " visitas entre ellos")}</div>

    <div class="kicker" id="k-Evolución">Evolución</div><h2>Cómo rinden tus vídeos mes a mes</h2>
    <div class="card"><table><tr><th>Mes</th><th>Vídeos</th><th>Visitas</th><th>Rinden</th></tr>
      ${r.months.slice().reverse().map((m) => `<tr><td>${esc(m.month)}</td><td>${m.long + m.shorts}</td><td>${kfmt(m.views)}</td><td style="color:${heatColor(m.ratio)}"><b>${times(m.ratio)}</b></td></tr>`).join("")}</table></div>

    <div class="kicker" id="k-Ganadores">Ganadores</div><h2>Los que más superaron a lo normal</h2>
    <div class="vids">${r.winners.map((v) => videoTile({...v, channel: v.short ? "Short" : "Vídeo largo", ageDays: Math.round((Date.now() - new Date(v.published)) / 864e5)})).join("")}</div>
    <h2>Los que peor fueron</h2>
    <div class="vids">${r.losers.map((v) => videoTile({...v, channel: v.short ? "Short" : "Vídeo largo", ageDays: Math.round((Date.now() - new Date(v.published)) / 864e5)})).join("")}</div>

    <div class="kicker" id="k-Horarios">Cuándo publicar</div><h2>Días y horas que mejor te funcionan</h2>
    <div class="small muted">Hora de ${esc(r.timezone)}. Cada vídeo se compara con la mediana de su tipo, así los Shorts y los largos se pueden mezclar: 1× = un vídeo normal tuyo.</div>
    <div class="card" style="margin-top:10px"><b>Mapa de calor: día × hora</b><div class="small muted" style="margin-bottom:10px">El número es cuántos vídeos subiste en esa franja; el color, cómo les fue.</div>
      <div class="heat"><div></div>${r.blocks.map((b) => `<div class="muted">${b}</div>`).join("")}
        ${r.days.map((d, i) => `<div class="muted" style="align-self:center">${d}</div>${r.heat[i].map((c) => c.count
          ? `<div class="c ${c.count <= 2 ? "few" : ""}" style="background:${heatColor(c.ratio)}" title="${c.count} vídeos · ${times(c.ratio)}">${c.count}</div>` : '<div class="c none"></div>').join("")}`).join("")}</div>
      <div class="legend">peor ${["#e5534b", "#a8302c", "#5c1f1d", "#3a3f46", "#1c3a6e", "#1f5fbf", "#3b8bf0", "#a8cdfb"].map((x) => `<i style="background:${x}"></i>`).join("")} mejor · borde punteado = 1 o 2 vídeos</div></div>
    <div class="card" style="margin-top:12px"><b>Por día de la semana</b><div class="small muted">Barras por encima de la línea: rinde más que lo normal.</div>
      <div class="months" style="height:150px;position:relative"><i style="position:absolute;left:0;right:0;bottom:calc((100% - 18px) * ${1 / maxDay});border-top:1px dashed var(--muted)" title="1× = lo normal"></i>${r.perDay.map((d) => `<div title="${d.count} vídeos"><i class="l" style="height:${100 * (d.ratio || 0) / maxDay}%;background:${heatColor(d.ratio)}"></i><b>${times(d.ratio)}</b><span>${d.day}</span></div>`).join("")}</div><div style="height:22px"></div></div>

    <div class="kicker" id="k-Constancia">Constancia</div><h2>Cuántos vídeos subes por mes</h2>
    <div class="small muted">Últimos 12 meses. Al algoritmo le gusta un ritmo parejo.</div>
    <div class="card" style="margin-top:10px"><div class="legend"><i style="background:#3b82f6"></i> Vídeos largos <i style="background:#ea580c"></i> Shorts</div>
      <div class="months">${r.months.map((m) => `<div><i class="l" style="height:${100 * m.long / maxMonth}%"></i><i class="s" style="height:${100 * m.shorts / maxMonth}%"></i><b>${m.long + m.shorts}</b><span title="${esc(m.month)}">${esc(m.month.split(" ")[0])}</span></div>`).join("")}</div>
      <div style="height:22px"></div>${r.consistencyNote ? `<div class="elf">🧝 ${esc(r.consistencyNote)}</div>` : ""}</div>

    <div class="kicker" id="k-Títulos">Títulos</div><h2>Qué tienen tus títulos que funcionan</h2>
    <div class="small muted">Compara los vídeos que tienen cada rasgo con los que no (mediana frente a lo normal de su tipo). Largo típico de tus títulos: ${r.titles.typicalLength} letras.</div>
    <div class="card" style="margin-top:10px">${r.titles.traits.map((t) => `<div class="trait"><div class="row"><b>${esc(t.name)}</b>
      <b style="color:${t.factor >= 1 ? "var(--ok)" : "var(--bad)"}">${t.factor >= 1 ? fmt(t.factor) + "× más" : Math.round(100 * (1 - t.factor)) + " % menos"}</b></div>
      <div class="small muted">${t.count} vídeos lo tienen</div>${diverge(t.factor)}</div>`).join("") || '<div class="muted">Pocos vídeos para comparar.</div>'}</div>

    <div class="kicker" id="k-Duración">Duración</div><h2>Qué duración te funciona (vídeos largos)</h2>
    <div class="card">${r.durations.map((d) => `<div class="trait"><div class="row"><b>${esc(d.name)}</b><span>${d.count} vídeos · <b>${times(d.ratio)}</b></span></div>
      ${d.ratio ? diverge(d.ratio) : ""}</div>`).join("")}</div>

    <div class="kicker" id="k-Temas">Temas</div><h2>Ranking de temas</h2>
    <div class="small muted">La IA agrupó tus vídeos por tema; los números salen de tus visitas reales. Azul = rinde más que lo normal; rojo = menos.</div>
    <div class="card" style="margin-top:10px">${r.topics.map((t, i) => `<div class="topic"><b class="muted" style="font-size:20px">${i + 1}</b>
      ${t.thumbnail ? `<img src="${esc(t.thumbnail)}" alt="">` : "<div></div>"}
      <div><b>${esc(t.name)}</b><div class="hbar"><i style="width:${Math.min(100, 40 * (t.ratio || 0))}%;background:${(t.ratio || 0) >= 1 ? "#3b82f6" : "#e5534b"}"></i></div>
      <div class="small muted"><b>${times(t.ratio)}</b> lo normal · ${t.count} vídeos · ${t.hits} éxitos · mediana ${kfmt(t.medianViews)}</div></div></div>`).join("") || '<div class="muted">Sin temas (pocos vídeos o sin IA configurada).</div>'}</div>`;
}
