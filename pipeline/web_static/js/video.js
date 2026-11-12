// a state mark in a list: the icon with the colour of the state (the label is what a screen reader says)
const vMark = (cls, name, label) => `<span class="${cls}">${icon(name, label)}</span>`;
const V_FIT = {bien: vMark("t-ok", "check", "Bien"), dudoso: vMark("t-warn", "alert", "Dudoso"), regular: vMark("t-warn", "alert", "Regular"),
  mal: vMark("t-bad", "x", "Mal"), no: vMark("t-bad", "x", "No")};

async function newVideo() {
  window.opening = null; window.openings = [];
  data = data || await api("/api/overview");
  let pre = window.prefill;
  if (!pre) { try { pre = JSON.parse(sessionStorage.getItem("prefill") || "null"); } catch (e) {} }
  window.prefill = pre;
  const idea = pre && pre.idea;
  show(`<h1>Nuevo vídeo</h1>
    ${idea ? `<div class="notice"><div class="row between"><b>Idea: ${esc(idea.title)}</b>
        <button onclick="window.prefill=null;try{sessionStorage.removeItem('prefill')}catch(e){};route()">Quitar idea</button></div>
      <div class="small">${esc(idea.angle || "")}</div>${idea.hook ? `<div class="small"><b>Gancho:</b> ${esc(idea.hook)}</div>` : ""}
      ${idea.outline && idea.outline.length ? `<ol class="small">${idea.outline.map((x) => `<li>${esc(x)}</li>`).join("")}</ol>` : ""}
      ${idea.research ? `<div class="small muted"><b>Comprobar antes:</b> ${esc(idea.research)}</div>` : ""}
      <div class="small muted mt-2">Se guarda como idea.md junto al guion. Escribe el guion con este esquema y graba la voz.</div></div>` : ""}
    <div class="card">
      <div class="fset"><div class="legend">Vídeo</div>
        <div class="two">
          ${field("Canal", `<select id="channel">${channelOptions(data)}</select>`, `<a href="#/canal-nuevo">+ nuevo canal</a>`, "channel")}
          ${field("Nombre", `<input id="name" placeholder="nombre-del-video">`, "Sin espacios: avion2, olga-korbut…", "name")}
        </div>
        <div class="two">
          ${field("Formato", `<select id="format"><option value="">Automático según el guion</option>
            ${data.formats.map((f) => `<option>${esc(f)}</option>`).join("")}</select>`, "Si no eliges, lo decide según el guion", "format")}
          ${field(`Serie <span class="opt">opcional</span>`, `<input id="serie" placeholder="p. ej. fracasos">`, "", "serie")}
        </div>
        <div class="two">
          ${field("Idioma del vídeo", `<select id="language"><option value="es">Español</option><option value="pt">Português (Brasil)</option><option value="en">English</option>
            <option value="fr">Français</option><option value="it">Italiano</option><option value="de">Deutsch</option></select>`,
            "El guion ya en ese idioma: se lee con la voz de ese idioma del canal, la de «Doblaje»", "language")}
          ${field(`Título de trabajo <span class="opt">opcional</span>`, `<input id="title">`, "Los títulos de YouTube se escriben solos", "title")}
        </div>
      </div>
      <div class="fset"><div class="legend">Guion</div>
        <div class="field"><label for="script">Guion</label>
          <textarea id="script" placeholder="## Capítulo 1&#10;Texto del guion…"></textarea>
          <div class="row"><label for="scriptfile" class="help n4">Pégalo o</label><input type="file" id="scriptfile" class="w-auto" accept=".txt,.md"></div></div>
        ${field(`Lista de escenas <span class="opt">opcional</span>`,
          `<textarea id="scenelist" class="mid" placeholder="Escena 1 · bloque 1 · ~30 s · tráfico&#10;Qué se ve: …&#10;Momento clave: …"></textarea>`,
          "Canales de simulación: la escena de cada bloque del guion; el programa la sigue", "scenelist")}
      </div>
      <div class="fset"><div class="legend">Voz y doblaje</div>
        <div id="dubbox"></div>
        ${field("Voz", `<input type="file" id="voice" accept="audio/*,.mp3,.wav,.m4a">`,
          "Mp3; también wav o m4a · si el canal tiene voz en Ajustes → Voces, déjalo vacío y se genera sola", "voice")}
      </div>
      <div class="fset"><div class="legend">Clip de apertura</div>
        <p class="help mt-2">Opcional: un momento real con su sonido y subtítulos traducidos, antes de la voz. Lo ves aquí antes de crear el vídeo</p>
        ${field("Qué momento", `<input id="opask" placeholder="«Simone Biles respondiendo en Instagram si hace falta un tipo de cuerpo»">`,
          "Vacío: lo propone según el título y el guion", "opask")}
        <div class="two">
          ${field(`O el enlace de YouTube <span class="opt">opcional</span>`, `<input id="opurl">`, "", "opurl")}
          <div class="two">
            ${field(`Desde <span class="opt">opcional</span>`, `<input id="opstart" placeholder="1:15">`, "", "opstart")}
            ${field(`Hasta <span class="opt">opcional</span>`, `<input id="opend" placeholder="1:32">`, "", "opend")}
          </div>
        </div>
        <div class="two">
          ${field("O sube tú el vídeo entero", `<input type="file" id="opfile" accept="video/*,.mp4,.mov,.mkv,.webm">`, "Lo recorto yo", "opfile")}
          ${field(`Fuente en pantalla <span class="opt">opcional</span>`, `<input id="opcredit">`, "«Vogue»; vacío = el canal de YouTube o quien habla", "opcredit")}
        </div>
        <div class="field"><label class="check"><input type="checkbox" id="opsubs" checked> Poner subtítulos traducidos</label>
          <p class="help">Quítalo si el clip ya los lleva</p></div>
        <div class="actions"><button id="opbtn" onclick="findOpening()">Buscar clip de apertura</button><span id="opmsg" class="small muted"></span></div>
        <div class="bar acc hide" id="opbar"><i></i></div>
        <div id="opbox"></div>
      </div>
      <div class="fset"><div class="legend">Comprobaciones</div>
        <div class="actions"><button id="hookbtn" onclick="checkHook()">Revisar el gancho</button><span class="help">Antes de grabar</span><span id="hookmsg" class="small muted"></span></div>
        <div id="hookbox"></div>
        <div class="actions"><button id="scenebtn" onclick="checkScenes()">Revisar escenas</button><span class="help">Canales de simulación</span><span id="scenemsg" class="small muted"></span></div>
        <div id="scenebox"></div>
      </div>
      <div class="fset">
        <div class="actions"><button class="main" id="create" onclick="createVideo()">Crear y poner en cola</button><b id="msg" class="t-warn"></b></div>
        <div class="bar acc hide" id="upbar"><i></i></div>
      </div>
    </div>`);
  $("#opsubs").onchange = $("#opcredit").oninput = () => {
    if (window.opening) Object.assign(window.opening, {subtitles: $("#opsubs").checked, credit: $("#opcredit").value});
  };
  $("#scriptfile").onchange = (e) => { const f = e.target.files[0]; if (f) f.text().then((t) => $("#script").value = t); };
  if (pre && pre.script) $("#script").value = pre.script;
  if (idea && idea.escenas) $("#scenelist").value = idea.escenas;      // a board idea comes with its scene list
  // a simulation channel: the languages it can be dubbed to, each only if it has a GenAIPro voice
  window.dubOptions = {};
  api("/api/voices").then((v) => { window.dubOptions = v.dubOptions || {}; showDub(); }).catch(() => {});
  window.showDub = () => {
    const list = window.dubOptions[$("#channel").value] || [];
    $("#dubbox").innerHTML = list.length ? `<div class="field"><div class="b small">Doblar a</div>
      <div class="row gap-4">${list.map((d) => `<label class="check"><input type="checkbox" class="dublang" value="${esc(d.lang)}" ${d.voice ? "checked" : "disabled"}>
        ${esc(d.name)} ${d.voice ? `<span class="small muted">· voz ${esc(d.voice)}${d.channel ? " · " + esc(d.channel) : ""}</span>`
          : `<span class="small t-bad">sin voz de GenAIPro: ponla en Ajustes → Voces (canal ${esc(d.channel || "—")})</span>`}</label>`).join("")}</div>
      <p class="help">El mismo vídeo con su voz y sus rótulos en ese idioma, en su canal, con sus Shorts</p></div>` : "";
  };
  $("#channel").addEventListener("change", () => showDub());
  if (idea) {
    if (pre.channel && data.channels.includes(pre.channel)) $("#channel").value = pre.channel;
    if (idea.format) $("#format").value = idea.format;
    $("#title").value = idea.title || "";
    $("#name").value = (idea.title || "").toLowerCase().normalize("NFD").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 40);
  }
}

async function checkHook() {
  const msg = $("#hookmsg"); msg.textContent = "Leyendo el arranque… (~15 s)"; $("#hookbtn").disabled = true;
  try {
    const sent = $("#script").value;
    const r = await post("/api/hook", {title: $("#title").value, script: sent, channel: $("#channel").value});
    window.hookResult = {...r, script: sent};
    msg.textContent = "";
    const cls = r.ok ? "ok" : r.verdict.startsWith("❌") ? "bad" : "";
    $("#hookbox").innerHTML = `<div class="notice ${cls}"><b>${esc(r.verdict)}</b>
      <div class="small mt-2"><b>Lo que promete el título:</b> ${esc(r.promise)}</div>
      ${(r.rules || []).length ? `<div class="small mt-2">${r.rules.map((x) => `<div>${x.ok ? vMark("t-ok", "check", "Cumple") : vMark("t-bad", "x", "No cumple")} ${esc(x.rule)}${x.detail ? ` <span class="muted">— ${esc(x.detail)}</span>` : ""}</div>`).join("")}</div>` : ""}
      ${r.payoffSentence ? `<div class="small"><b>Se cumple por primera vez (≈${Math.round(r.payoffSeconds)} s):</b> «${esc(r.payoffSentence)}»</div>` : ""}
      ${r.strongestSentence ? `<div class="small"><b>Lo más fuerte del guion (≈${Math.round(r.strongestSeconds)} s):</b> «${esc(r.strongestSentence)}»</div>` : ""}
      ${r.problems.length ? `<ul class="small">${r.problems.map((p) => `<li>${esc(p)}</li>`).join("")}</ul>` : ""}
      ${r.newOpening ? `<div class="small mt-2"><b>Apertura propuesta (~15 s):</b></div><blockquote id="newopen">${esc(r.newOpening)}</blockquote>
        <div class="row"><button onclick="useOpening()">${r.scriptWithOpening ? "Cambiar el arranque del guion por esta apertura" : "Poner esta apertura al principio del guion"}</button><button onclick="navigator.clipboard.writeText(document.getElementById('newopen').innerText)">${icon("copy")} Copiar</button></div>` : ""}
      ${r.tips.length ? `<ul class="small">${r.tips.map((t) => `<li>${esc(t)}</li>`).join("")}</ul>` : ""}
      ${r.topicFit ? `<div class="small mt-3"><b>${V_FIT[r.topicFit] || "•"} El tema y el título frente a lo que funciona en tu canal:</b> ${esc(r.topicWhy)}</div>
        ${r.lengthNote ? `<div class="small"><b>Duración (~${r.minutes} min):</b> ${esc(r.lengthNote)}</div>` : ""}
        ${r.titles.length ? `<div class="small mt-2"><b>Títulos con el patrón que funciona:</b></div><ul class="small">${r.titles.map((t) => `<li>${esc(t)} <button class="sm" onclick="$('#title').value=this.parentElement.firstChild.textContent.trim()">Usar</button></li>`).join("")}</ul>` : ""}` : ""}</div>`;
  } catch (e) { msg.textContent = e.message; }
  $("#hookbtn").disabled = false;
}
// the opening clip: searched in the background, each candidate playing with its translated subtitles on top
function opClock(s) { s = Math.max(0, +s || 0); return `${Math.floor(s / 60)}:${(s % 60).toFixed(1).padStart(4, "0")}`; }
function ytApi() {
  if (window.YT && window.YT.Player) return Promise.resolve();
  return new Promise((resolve) => {
    const before = window.onYouTubeIframeAPIReady;
    window.onYouTubeIframeAPIReady = () => { if (before) before(); resolve(); };
    if (!document.getElementById("ytapi")) {
      const tag = document.createElement("script"); tag.id = "ytapi"; tag.src = "https://www.youtube.com/iframe_api"; document.head.appendChild(tag);
    }
  });
}
function uploadOpening(file) {     // the same file is uploaded once, however many times you search
  if (window.opUpload && window.opUpload.file === file) return Promise.resolve(window.opUpload.ticket);
  $("#opbar").classList.remove("hide");
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/apertura/subir");
    xhr.setRequestHeader("Content-Type", "application/octet-stream");
    xhr.upload.onprogress = (e) => { if (e.lengthComputable) $("#opbar i").style.setProperty("--v", (100 * e.loaded / e.total) + "%"); };
    xhr.onload = () => {
      $("#opbar").classList.add("hide");
      if (xhr.status >= 300) return reject(new Error(JSON.parse(xhr.responseText || "{}").error || xhr.statusText));
      const ticket = JSON.parse(xhr.responseText).file;
      window.opUpload = {file, ticket, src: URL.createObjectURL(file)};
      resolve(ticket);
    };
    xhr.onerror = () => { $("#opbar").classList.add("hide"); reject(new Error("Fallo de red al subir el vídeo")); };
    xhr.send(file);
  });
}
async function findOpening() {
  const msg = $("#opmsg"); $("#opbtn").disabled = true; $("#opbox").innerHTML = "";
  try {
    const own = $("#opfile").files[0];
    let file = "";
    if (own) { msg.textContent = "Subiendo el vídeo…"; file = await uploadOpening(own); }
    msg.textContent = own ? "Escuchando el vídeo y buscando el momento… (2-5 min)" : "Buscando el momento y traduciendo… (1-3 min)";
    const {token} = await post("/api/apertura", {channel: $("#channel").value, title: $("#title").value, script: $("#script").value,
      ask: $("#opask").value, url: own ? "" : $("#opurl").value, file, start: $("#opstart").value, end: $("#opend").value,
      language: $("#language").value, subtitles: $("#opsubs").checked});
    let r;
    for (let i = 0; i < 200; i++) {
      await new Promise((ok) => setTimeout(ok, 3000));
      r = await api("/api/apertura/" + token);
      if (r.result || !r.job.running) break;
    }
    msg.textContent = "";
    if (!r.result) throw new Error("La búsqueda se cortó: " + (r.job.log || "").slice(-300));
    if (r.result.error) throw new Error(r.result.error);
    showOpenings(r.result);
  } catch (e) { msg.textContent = e.message; }
  $("#opbtn").disabled = false;
}
function showOpenings(result) {
  const list = result.candidates || [], plan = result.plan || {};
  window.openings = list; window.opening = null; list.max = result.maxSeconds;
  $("#opbox").innerHTML = `<div class="notice">
    <div class="small"><b>Busca:</b> ${esc(plan.about || "")}${plan.speaker ? ` · <b>Habla:</b> ${esc(plan.speaker)}${plan.role ? " (" + esc(plan.role) + ")" : ""}` : ""}</div>
    ${list.length ? "" : `<div class="small mt-2">No he encontrado el momento en ningún vídeo. Prueba a describirlo de otra forma o pega el enlace (y el segundo).</div>`}
    ${list.map((c, i) => `<div class="cand">
      <div class="small"><b>${i + 1}. ${c.file ? "Tu vídeo" : esc(c.title || c.id)}</b>${c.file ? "" : ` <span class="muted">· ${esc(c.channel || "")} · <a href="${esc(c.url)}&t=${Math.floor(c.start)}s" target="_blank">abrir en YouTube</a></span>`}</div>
      <div class="small muted">${esc(c.why || "")}</div>
      <div class="player">${c.file
        ? `<video id="opv${i}" src="${window.opUpload ? window.opUpload.src : ""}#t=${c.start}" controls playsinline preload="metadata"></video>`
        : `<div id="opv${i}"></div>`}
        <div id="ops${i}" class="subs"></div></div>
      <div class="row small mt-2"><label for="opa${i}" class="n4">desde</label> <input id="opa${i}" class="w-xs" value="${c.start}"> <label for="opb${i}" class="n4">hasta</label> <input id="opb${i}" class="w-xs" value="${c.end}"> s
        <button onclick="replayOpening(${i})">${icon("play")} Ver este tramo</button> <button class="main" onclick="useOpeningClip(${i})">Usar esta</button> <b id="opok${i}" class="t-warn"></b></div>
      <details class="small mt-1"><summary>Subtítulos</summary><div id="opl${i}"></div></details></div>`).join("")}</div>`;
  list.forEach((c, i) => { listLines(i); $("#opa" + i).oninput = $("#opb" + i).oninput = () => listLines(i); });
  window.opPlayers = [];
  list.forEach((c, i) => {        // your own video: the browser plays the file you picked, stopping at «hasta»
    if (!c.file) return;
    const v = document.getElementById("opv" + i);
    v.ontimeupdate = () => { if (v.currentTime > +$("#opb" + i).value) v.pause(); };
    window.opPlayers[i] = {getCurrentTime: () => v.currentTime,
      loadVideoById: (o) => { v.currentTime = o.startSeconds; v.play(); }};
  });
  if (list.some((c) => !c.file)) ytApi().then(() => list.forEach((c, i) => {
    if (c.file) return;
    window.opPlayers[i] = new YT.Player("opv" + i, {videoId: c.id, width: "100%", height: "100%",
      playerVars: {start: Math.floor(c.start), end: Math.ceil(c.end), rel: 0, cc_load_policy: 0}});
  }));
  clearInterval(window.opTimer);
  window.opTimer = setInterval(() => {
    if (!document.getElementById("opbox")) return clearInterval(window.opTimer);
    (window.openings || []).forEach((c, i) => {
      const p = (window.opPlayers || [])[i], box = document.getElementById("ops" + i);
      if (!p || !p.getCurrentTime || !box) return;
      const t = p.getCurrentTime(), a = +$("#opa" + i).value, b = +$("#opb" + i).value;
      const line = t >= a && t <= b ? (c.lines || []).find((l) => t >= l.from && t < l.to) : null;
      box.textContent = line && $("#opsubs").checked ? line.text : "";
    });
  }, 150);
}
function listLines(i) {
  const c = window.openings[i], a = +$("#opa" + i).value, b = +$("#opb" + i).value;
  $("#opl" + i).innerHTML = (c.lines || []).map((l) => `<div class="${l.to < a || l.from > b ? "dim" : ""}">
    <span class="muted">${opClock(l.from)}</span> ${esc(l.text)} <span class="muted">· ${esc(l.original)}</span></div>`).join("")
    + `<div class="muted">${(b - a).toFixed(1)} s${b - a > (window.openings.max || 30) ? " (se recorta al máximo)" : ""}</div>`;
}
function replayOpening(i) {
  const c = window.openings[i], p = (window.opPlayers || [])[i];
  if (p && p.loadVideoById) p.loadVideoById({videoId: c.id, startSeconds: +$("#opa" + i).value, endSeconds: +$("#opb" + i).value});
}
function useOpeningClip(i) {
  window.opening = {candidate: window.openings[i], start: $("#opa" + i).value, end: $("#opb" + i).value,
    subtitles: $("#opsubs").checked, credit: $("#opcredit").value};
  window.openings.forEach((c, k) => { const b = $("#opok" + k); if (b) b.textContent = k === i ? "✓ Elegida: irá antes de la voz" : ""; });
}
async function checkScenes() {
  const msg = $("#scenemsg"); msg.textContent = "Mirando qué se puede enseñar… (~20 s)"; $("#scenebtn").disabled = true;
  try {
    const r = await post("/api/scenes", {script: $("#script").value, channel: $("#channel").value});
    msg.textContent = "";
    window.proposedScenes = r.escenas || "";
    $("#scenebox").innerHTML = `<div class="notice ${r.coverage >= 85 && !r.warnings.length ? "ok" : ""}"><b>${esc(r.verdict)}</b>
      ${r.warnings.length ? `<ul class="small">${r.warnings.map((w) => `<li>${vMark("t-warn", "alert", "Aviso")} ${esc(w)}</li>`).join("")}</ul>` : ""}
      <ul class="small">${(r.blocks || []).map((b) => `<li>${V_FIT[b.fit] || "•"} <b>[${b.n}]</b> ${esc(b.world || "—")} ${esc(b.scene || "")}
        <span class="muted">· ~${b.seconds} s · «${esc(b.text.slice(0, 90))}…»</span>${b.why ? `<br><i>Falta:</i> ${esc(b.why)}` : ""}</li>`).join("")}</ul>
      ${r.escenas ? `<button onclick="$('#scenelist').value = window.proposedScenes; this.textContent = 'Lista de escenas puesta ✓'">Usar esta lista de escenas</button>` : ""}</div>`;
  } catch (e) { msg.textContent = e.message; }
  $("#scenebtn").disabled = false;
}
function useOpening() {
  const box = $("#script"), text = document.getElementById("newopen").innerText.trim();
  if (window.hookResult && window.hookResult.scriptWithOpening && window.hookResult.script === box.value) {
    box.value = window.hookResult.scriptWithOpening;          // the old opening sentences go, the new ones in their place
    $("#hookmsg").textContent = "Arranque cambiado: léelo y vuelve a revisar.";
    return;
  }
  if (!box.value.startsWith(text)) box.value = text + "\n\n" + box.value;
  $("#hookmsg").textContent = "Añadida al principio: ajusta el resto del arranque para que no se repita y vuelve a revisar.";
}

async function createVideo() {
  const voice = $("#voice").files[0], msg = $("#msg");
  let auto = false;
  if (!voice) {
    msg.textContent = "Comprobando…";
    try { auto = !!(await api("/api/voices")).speaks[$("#channel").value]; } catch (e) {}   // gimnasia-br: gimnasia's voice
    if (!auto) { msg.textContent = "Falta el archivo de voz (o pon una voz a este canal en Ajustes → Voces por canal)"; return; }
  }
  // «¿ya lo hice?»: the same story twice is easy to miss with many channels. Warned on the page, a second click
  // creates it: confirm() is silenced by some browsers and apps, and then the button did nothing at all
  const said = $("#script").value;
  if (window.twinOk !== said) {
    msg.textContent = "Comprobando…";
    try {
      const twin = ((await post("/api/search", {q: said})).results || []).find((r) => r.score >= 0.5);
      if (twin) {
        window.twinOk = said;
        msg.textContent = `⚠️ Este guion se parece un ${Math.round(twin.score * 100)} % a «${twin.title || twin.slug}» (${twin.slug}, ` +
          `${twin.published ? "ya en YouTube" : twin.status}). Pulsa «Crear y poner en cola» otra vez para crearlo igualmente.`;
        return;
      }
    } catch (e) {}
  }
  $("#create").disabled = true; msg.textContent = "Creando…";
  try {
    const made = await post("/api/videos", {channel: $("#channel").value, name: $("#name").value.trim(), format: $("#format").value,
      serie: $("#serie").value, language: $("#language").value, title: $("#title").value, script: $("#script").value, scenes: $("#scenelist").value,
      ...((window.dubOptions || {})[$("#channel").value] ? {dub: [...document.querySelectorAll(".dublang:checked")].map((x) => x.value)} : {}), idea: window.prefill ? window.prefill.idea : null, opening: window.opening || null});
    window.prefill = null; try { sessionStorage.removeItem("prefill"); } catch (e) {}
    if (auto) { location.hash = "#/video/" + encodeURIComponent(made.slug); return; }   // GenAIPro makes the voice
    msg.textContent = "Subiendo la voz…"; $("#upbar").classList.remove("hide");
    await new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `/api/video/${encodeURIComponent(made.slug)}/voz`);
      xhr.setRequestHeader("Content-Type", "application/octet-stream");
      xhr.upload.onprogress = (e) => { if (e.lengthComputable) $("#upbar i").style.setProperty("--v", (100 * e.loaded / e.total) + "%"); };
      xhr.onload = () => xhr.status < 300 ? resolve() : reject(new Error(JSON.parse(xhr.responseText || "{}").error || xhr.statusText));
      xhr.onerror = () => reject(new Error("Fallo de red al subir"));
      xhr.send(voice);
    });
    location.hash = "#/video/" + encodeURIComponent(made.slug);
  } catch (e) { msg.textContent = e.message; $("#create").disabled = false; }
}

let tab = "diagnosis";
// «Editar»: the CapCut-style editor of the video (pipeline/editor.py), full screen, served at /editor/<slug>/
async function editorPage(slug) {
  const src = `/editor/${encodeURIComponent(slug)}/`;
  show(`<div class="editbar"><a class="btn sm" href="#/video/${encodeURIComponent(slug)}">${icon("right")} Ficha del vídeo</a>
      <b class="mw0">Editor · ${esc(slug)}</b><span class="small muted phone-only">El editor está pensado para pantallas grandes: aquí, cambios sencillos.</span>
      <a class="btn sm push" href="${src}" target="_blank" rel="noopener">${icon("external")} Abrir en otra pestaña</a></div>
    <iframe class="editframe" src="${src}" title="Editor de vídeo de ${esc(slug)}"></iframe>`);
}

async function videoPage(slug) {
  const v = await api("/api/video/" + encodeURIComponent(slug));
  if (tab === "diagnosis" && !window.tabPicked && (v.error || v.lastError) && v.log) tab = "log";   // the answer is in the log
  const base = `/files/${encodeURIComponent(slug)}/`;
  const st = v.stage;
  const ORDER = ["factcheck", "align", "planner", "sourcing", "analysis", "judge", "ingest", "people", "fallback", "coldopen", "timeline", "qa", "render", "shorts", "package"];
  const done = Object.fromEntries(v.stages.map((x) => [x.name, x]));
  const costs = v.costs || {};
  const failedAt = !st && (v.error || v.lastError) ? ORDER.find((n) => !done[n]) : null;
  const totalMin = v.stages.reduce((a, x) => a + (x.seconds || 0), 0) / 60;
  const cls = (n) => st && st.stage === n ? "now" : done[n] ? "done" : n === failedAt ? "failed" : "";
  const stagesView = `<div class="card"><div class="row between"><b>${st ? `Haciendo ${esc(STAGES[st.stage] || st.stage)} (${st.number}/${st.of}) · desde hace ${ago(st.started)}`
      : v.status === "hecho" ? `Terminado · ${v.stages.length} etapas` : `${v.stages.length} de ${ORDER.length} etapas hechas${failedAt ? ` · se paró en <span class="t-bad">${esc(STAGES[failedAt] || failedAt)}</span>` : ""}`}</b>
      <span class="small muted">${totalMin ? `${Math.round(totalMin)} min de trabajo` : ""}${v.costUsd ? ` · ${v.costUsd} $ de API` : ""}</span></div>
    <div class="stages">${ORDER.map((n) => `<div class="${cls(n)}" title="${esc(STAGES[n] || n)}${done[n] ? " · " + mins(done[n].seconds) : ""}"></div>`).join("")}</div>
    <details><summary class="small muted">Ver las etapas una a una</summary><div class="stagelist">${ORDER.map((n) => {
      const d = done[n]; const now = st && st.stage === n;
      return `<div class="${now ? "now" : d ? "" : "pend"}"><span>${now ? icon("play", "En curso") : d ? vMark("t-ok", "check", "Hecha") : icon("minus", "Pendiente")} ${esc(STAGES[n] || n)}</span><span class="n">${now ? ago(st.started) : d ? mins(d.seconds) + (costs[n] ? ` · ${costs[n].toFixed(2)} $` : "") : ""}</span></div>`; }).join("")}</div></details></div>`;
  const doing = stagesView;
  // what happened, in plain words, with the whole text one click away
  const rawError = v.error || v.lastError || "";
  const ex = rawError ? explain(rawError, v) : null;
  const whyView = !ex ? "" : `<div class="card why ${ex.kind}"><h3>${esc(ex.title)}</h3>
      ${v.lastError ? `<p>En cola: ${v.retryAt ? `el vigilante lo reintenta solo a las <b>${esc(v.retryAt)}</b>, antes si pulsas «Hacer ahora».` : "el vigilante lo hará en su turno."}</p>` : ""}
      ${ex.hint ? `<p>${esc(ex.hint)}</p>` : ""}
      <div class="row mt-2">${ex.actions.map(ACT).join("")}</div>
      <details><summary>El error completo</summary><pre>${esc(rawError)}</pre></details></div>`;
  const y = v.youtube;
  const pct = y && y.requests ? Math.round(100 * y.ok / y.requests) : 0;
  const ytView = !y ? "" : `<div class="card"><div class="row between"><b>YouTube y proxy en este vídeo${y.hours ? ` <span class="muted n4">· últimas ${y.hours} h</span>` : ""}</b><span class="small muted">${y.proxy && y.proxy.length ? "por " + esc(y.proxy.join(", ")) : "sin proxy"}</span></div>
    <div class="facts">
      <div><b class="${pct >= 85 ? "t-ok" : pct >= 60 ? "t-warn" : "t-bad"}">${pct} %</b><span>peticiones bien (${y.ok} de ${y.requests})</span></div>
      <div><b>${y.files_ok}/${y.files}</b><span>clips descargados</span></div>
      <div><b>${(y.proxy_gb || 0).toFixed(2)} GB</b><span>por el proxy${y.sessions ? ` · ${y.sessions} sesiones` : ""}</span></div>
      <div><b>${(y.errors || {}).bot || 0}</b><span>«no eres un bot»</span></div></div>
    ${(y.details || []).length ? `<div class="small muted mt-3">Errores más frecuentes:</div><ul class="small m-0 mt-1">${y.details.map(([t, n]) => `<li>${n}× ${esc(t)}</li>`).join("")}</ul>` : ""}
    ${y.allTime ? `<div class="small muted mt-3">Desde el principio: ${y.allTime.requests} peticiones (${y.allTime.requests ? Math.round(100 * y.allTime.ok / y.allTime.requests) : 0} % bien) · ${y.allTime.files_ok}/${y.allTime.files} clips · ${(y.allTime.proxy_gb || 0).toFixed(2)} GB. Incluye intentos de otros días, con proxies y fallos que ya no están.</div>` : ""}</div>`;
  const titles = v.youtubeTxt ? `<h2>Para YouTube</h2><div class="card"><pre id="yt">${esc(v.youtubeTxt)}</pre>
      <button onclick="navigator.clipboard.writeText(document.getElementById('yt').innerText)">${icon("copy")} Copiar</button></div>` : "";
  const scenesPreview = v.scenesPreview ? `<h2>Vista previa de las escenas</h2><div class="card"><a href="${base + v.scenesPreview}" target="_blank">
      <img class="sheet" src="${base + v.scenesPreview}" alt="Vista previa de las escenas" loading="lazy" decoding="async"></a><div class="small muted mt-2">Una imagen de cada escena, sacada antes del render.</div></div>` : "";
  const thumbs = v.thumbnails.length ? `<h2>Miniaturas</h2><div class="thumbs">${v.thumbnails.map((t) =>
      `<a href="${base + t}?download" title="Descargar">${thumb(base + t, "shot", "Miniatura")}</a>`).join("")}</div>` : "";
  const dubState = (d) => d.skipped && !d.done && !d.manual ? icon("pause") + " no se dobla a este idioma (pulsa «Doblar a " + esc(d.name) + "»)"
    : d.old && !d.done && !d.manual && !d.voice && !d.script ? icon("pause") + " vídeo anterior al doblaje (en Ajustes: «solo los nuevos»): pulsa «Doblar a " + esc(d.name) + "»"
    : d.manual ? vMark("t-ok", "check") + " doblado por ti (la cola no lo hace)" : d.done ? `${vMark("t-ok", "check")} hecho · <a href="#/video/${encodeURIComponent(d.slug)}">ver ${esc(d.slug)}</a>`
    : d.voice ? icon("mic") + " voz lista: la cola hará el vídeo doblado" : d.review ? icon("eye") + " adaptado: espera tu revisión antes de grabar la voz"
    : d.script ? icon("pen") + (d.own ? " tu guion: falta la voz (se hace sola en unos minutos)" : " traducido: falta la voz")
    : "sin guion todavía (se traducirá solo, o pega el tuyo)";
  const dubs = (v.dubs || []).length ? `<h2>Doblaje</h2>${v.dubs.map((d) => `<details class="card" ${d.done || d.manual ? "" : "open"}>
      <summary><b>${esc(d.name)}</b> · <span class="small">${dubState(d)}</span>${d.voiceId ? "" : ' <span class="pill error">sin voz elegida para este idioma</span>'}</summary>
      ${d.error ? `<div class="notice bad small">${esc(d.error)}</div>` : ""}
      ${d.done || d.manual ? "" : (d.skipped || d.old) && !d.voice && !d.script
        ? `<div class="row my-2"><button class="main" onclick="dubChoose('${d.lang}', true, this)">Doblar a ${esc(d.name)}</button></div>`
        : !d.voice ? `<div class="row my-2"><button onclick="dubChoose('${d.lang}', false, this)">No doblar a ${esc(d.name)}</button></div>` : ""}
      ${d.adapted ? `<div class="small my-2"><b>Adaptado a su público:</b><div class="md">${md(d.adapted.split("\n").slice(2).join("\n"), "")}</div></div>` : ""}
      ${d.done ? "" : `<div class="small muted my-2">Pega aquí tu guion ya traducido (con sus «## » de capítulo si los tiene). Se leerá con la voz de ${esc(d.name)} y se hará ${esc(d.slug)} con los mismos clips.</div>
        <input id="dubt-${d.lang}" aria-label="Título en ${esc(d.name)}" placeholder="Título en ${esc(d.name)} (opcional)" value="${esc(d.title)}" class="mb-2">
        <textarea id="dubs-${d.lang}" aria-label="Guion en ${esc(d.name)}" rows="${d.review ? 14 : 8}" placeholder="Guion en ${esc(d.name)}…">${esc(d.own || d.review ? d.script : "")}</textarea>
        ${d.review ? `<div class="small muted my-2">Revísalo (o pásaselo a un corrector nativo): si está bien, apruébalo; si lo corriges aquí, «Usar mi guion y doblar».</div>` : ""}
        <div class="row mt-2">${d.review ? `<button class="main" onclick="dubApprove('${d.lang}', this)">Aprobar y grabar la voz</button>` : ""}
        <button class="${d.review ? "" : "main"}" onclick="dubScript('${d.lang}', this)">Usar mi guion y doblar</button>`}
        <button onclick="dubManual('${d.lang}', ${!d.manual})">${d.manual ? "Deshacer «lo doblé yo»" : "Ya lo doblé yo"}</button>${d.done ? "" : "</div>"}</details>`).join("")}` : "";
  window.dubScript = async (lang, button) => {
    button.disabled = true;
    try { await post(`/api/video/${encodeURIComponent(slug)}/doblaje`, {lang, script: $("#dubs-" + lang).value, title: $("#dubt-" + lang).value}); route(); }
    catch (e) { oops(e); button.disabled = false; }
  };
  window.dubApprove = async (lang, button) => { button.disabled = true;
    try { await post(`/api/video/${encodeURIComponent(slug)}/doblaje`, {lang, approve: true}); route(); } catch (e) { oops(e); button.disabled = false; } };
  window.dubChoose = async (lang, on, button) => { button.disabled = true;
    try { await post(`/api/video/${encodeURIComponent(slug)}/doblaje`, {lang, on}); route(); } catch (e) { oops(e); button.disabled = false; } };
  window.dubManual = async (lang, manual) => { await post(`/api/video/${encodeURIComponent(slug)}/doblaje`, {lang, manual}); route(); };
  const shorts = v.shorts.length ? `<h2>Shorts</h2><div class="row">${v.shorts.map((t) => `<a class="btn" href="${base + t}?download">${icon("download")} ${esc(t.split("/").pop())}</a>`).join("")}</div>` : "";
  const docs = {diagnosis: ["Diagnóstico", v.diagnosis], factcheck: ["Verificación del guion", v.factcheck], hook: ["Gancho", v.hook], graphics: ["Gráficos", v.graphics], rhythm: ["Ritmo", v.rhythm],
                retention: ["Retención", null], audit: ["Auditoría", null], log: ["Registro", null], script: ["Guion", null], stages: ["Etapas", null]};
  window.uploadRetention = async () => {
    const file = $("#retfile").files[0], msg = $("#retmsg");
    if (!file) { msg.textContent = "Elige el CSV exportado de YouTube Studio"; return; }
    msg.textContent = "Analizando… (~20 s)";
    try { await post(`/api/video/${encodeURIComponent(slug)}/retencion`, {csv: await file.text()}); route(); }
    catch (e) { msg.textContent = e.message; }
  };
  const body = tab === "retention" ? `<div class="small muted">Cuando el vídeo lleve unos días publicado: YouTube Studio → Estadísticas → <b>Modo avanzado</b>
        → este vídeo → <b>Retención de audiencia</b> → Exportar la vista actual → <b>CSV</b>. Súbelo aquí: te digo dónde se va la gente,
        qué se decía y qué se veía en ese momento, y qué cambiar en el próximo guion.</div>
        <div class="row my-2"><input type="file" id="retfile" class="w-auto" accept=".csv,.txt,.tsv">
        <button class="main" onclick="uploadRetention()">Analizar retención</button><span id="retmsg" class="small muted"></span></div>
        ${v.retention ? `<div class="md">${md(v.retention, base)}</div>` : ""}`
    : tab === "log" ? (() => {
        const lines = (v.log || "").split("\n");
        const important = lines.filter((l) => /AVISO|ERROR|Error|Traceback|Tráfico|sesión|descarta|siguiente candidato|=====|\[\d+\/15\]/.test(l));
        const paint = (l) => /ERROR|Traceback|FALLO/.test(l) ? `<span class="err">${esc(l)}</span>` : /AVISO|descarta/.test(l) ? `<span class="warn">${esc(l)}</span>` : /hecho en/.test(l) ? `<span class="ok">${esc(l)}</span>` : esc(l);
        const all = window.logAll;
        return `<div class="tools"><span class="small muted">${all ? `${lines.length} líneas` : `${important.length} líneas con avisos, errores y etapas (de ${lines.length})`}</span>
          <button onclick="window.logAll=!window.logAll;route()">${all ? "Solo lo importante" : "Ver todo el registro"}</button>
          <button onclick="navigator.clipboard.writeText(document.getElementById('log').innerText);this.textContent='Copiado ✓'">Copiar</button></div>
          <pre id="log" class="log">${(all ? lines : important).map(paint).join("\n") || "Todavía no hay registro."}</pre>`; })()
    : tab === "audit" ? (v.audit ? `<div class="small muted">Minuto · lo que se dice → de dónde sale la imagen · quién la eligió. Cópialo y pégalo en el chat para revisarlo.</div>
        <div class="tools"><button onclick="navigator.clipboard.writeText(document.getElementById('audit').innerText);this.textContent='Copiado ✓'">${icon("copy")} Copiar todo</button></div><pre id="audit">${esc(v.audit)}</pre>`
        : "Todavía no hay montaje (sale después de la etapa «timeline»).")
    : tab === "script" ? `<div class="row mb-2"><audio controls preload="none" src="/api/video/${encodeURIComponent(v.slug)}/voz.mp3"></audio>
        <a class="btn" href="/api/video/${encodeURIComponent(v.slug)}/voz.mp3?download">${icon("download")} Descargar voz</a></div><pre>${esc(v.script)}</pre>`
    : tab === "stages" ? `<table><tr><th>Etapa</th><th class="r">Tiempo</th><th class="r">RAM máx.</th><th class="r">CPU máx.</th></tr>${v.stages.map((s) =>
        `<tr><td>${esc(STAGES[s.name] || s.name)}</td><td class="r nw">${mins(s.seconds)}</td><td class="r nw">${s.ram ?? "—"} GB</td><td class="r nw">${s.cpu ?? "—"} %</td></tr>`).join("")}</table>`
    : `<div class="md">${md(docs[tab][1], base)}</div>`;
  const primary = v.status === "error" ? '<button class="main" onclick="act(\'retry\')">Reintentar</button>'
    : v.status === "en cola" || v.status === "incompleto" && v.stagesDone ? '<button class="main" onclick="act(\'retry\')">Hacer ahora</button>'
    : v.status === "haciendo" ? '<button onclick="ask(\'¿Parar este vídeo y sacarlo de la cola? Lo ya hecho se guarda.\', {ok: \'Parar\', danger: true}).then((yes) => yes && act(\'stop\'))">Parar</button>'
    : v.status === "en pausa" ? '<button class="main" onclick="act(\'unhold\')">Volver a la cola</button>'
    : v.hasVideo ? `<a class="btn main" href="${base}video-final.mp4?download">${icon("download")} Descargar vídeo</a>` : "";
  const secondary = [
    v.status === "hecho" ? `<a class="btn" href="#/revisar/${encodeURIComponent(v.slug)}">Revisar clips</a>` : "",
    v.stagesDone >= 9 ? `<a class="btn" href="#/decisiones/${encodeURIComponent(v.slug)}">Decisiones del relleno</a>` : "",
    `<button onclick="copyForClaude('${esc(v.slug)}', this)" title="Error, etapas, diagnóstico y el final del registro en un solo texto">${icon("copy")} Copiar para Claude</button>`,
    v.status === "en cola" || v.status === "error" ? '<button onclick="act(\'hold\')" title="No se hará hasta que lo vuelvas a poner">Quitar de la cola</button>' : "",
    !v.published && v.status !== "haciendo" && (v.status === "hecho" || v.hasVideo || v.stagesDone) ? '<button onclick="markUploaded()">Ya está subido a YouTube</button>' : "",
    v.status !== "haciendo" && v.stagesDone ? '<button onclick="redoFrom(this)" title="Vuelve a la cola y se rehace desde el paso que elijas (reaprovecha descargas y voz)">Rehacer desde…</button>' : "",
    v.hasVideo ? '<button onclick="act(\'archive\')" title="Sacarlo de la lista (materiales/_hechos)">Archivar</button>'
      : v.status !== "haciendo" ? '<button onclick="ask(\'¿Quitar este vídeo de la lista? No se borra nada: va a materiales/_hechos.\', {ok: \'Quitar de la lista\'}).then((yes) => yes && act(\'archive\'))" title="Sin vídeo hecho: sale de la lista y de la cola (materiales/_hechos)">Quitar de la lista</button>' : "",
    `<button onclick="changeChannel('${esc(v.slug)}', '${esc(v.channel)}', this)">Cambiar de canal</button>`,
  ].filter(Boolean);
  show(`
    <div class="vhead"><div class="mw0"><h1>${esc(v.title || v.slug)}${v.title && v.title !== v.slug ? `<span class="slug">${esc(v.slug)}</span>` : ""} ${pill(v.lastError && v.status === "en cola" ? "reintento" : v.status)}</h1>
        <div class="meta">${esc(v.channel)}${v.format ? ` · formato <b>${esc(v.format.name)}</b>${v.format.auto ? ` <span title="${esc(v.format.why)}">(elegido por el guion)</span>` : ""}` : ""}
          ${v.minutes ? ` · ${v.minutes} min de trabajo` : ""} · ${v.costUsd} $ de API</div></div>
      <div class="primary">${primary}${done.timeline && v.status !== "haciendo" ? `<a class="btn" href="#/editor/${encodeURIComponent(v.slug)}" title="Cambiar planos, cortes, transiciones, efectos, textos y música antes del render">${icon("scissors")} Editar</a>` : ""}
        <span class="more"><button onclick="event.stopPropagation();this.parentNode.classList.toggle('open')">Más ${icon("down")}</button><div>${secondary.join("")}</div></span></div></div>
    ${whyView}
    ${v.quotaWait ? `<div class="notice">${icon("pause")} En espera: ${esc(v.quotaWait)}. La cola sigue con los demás vídeos y este se reintenta solo.</div>` : ""}
    ${v.published ? `<div class="notice ok">${vMark("t-ok", "check")} Subido a YouTube${v.published.url ? ` · <a href="${esc(v.published.url)}" target="_blank" rel="noopener">verlo</a>` : ""}
      ${v.removed ? ` · los archivos pesados se borraron el ${esc(v.removed.at.slice(0, 10))} (${v.removed.gb} GB)` : " · el vídeo final se borrará del servidor a los 7 días para dejar sitio"}
      <button class="sm ml-2" onclick="markUploaded(false)">No, aún no está subido</button></div>` : ""}
    <div class="vlayout"><div class="vmain">
    ${v.hasVideo ? "" : doing}
    ${v.hasVideo ? `<video controls playsinline preload="metadata"
        ${v.thumbnails.length ? `poster="${base + v.thumbnails[0]}"` : ""} src="${base}${v.preview ? "preview.mp4" : "video-final.mp4"}"></video>
      <div class="small muted mt-1">${v.preview ? `Copia ligera en 720p para verlo rápido (también en el móvil) · <a href="${base}video-final.mp4" target="_blank" rel="noopener">ver el original en 1080p</a>`
        : "Preparando una copia ligera para verlo sin cortes en el móvil (unos minutos); mientras tanto, el original pesa mucho y puede ir a trompicones."}</div>
      <div class="row mt-2"><a class="btn main" href="${base}video-final.mp4?download">${icon("download")} Descargar vídeo</a>
        <button onclick="exportPremiere(this)" title="Una carpeta con timeline.xml, los clips en pistas, la voz, la música, los efectos y los subtítulos">${icon("film")} Proyecto para Premiere / DaVinci</button>
        <span id="exportBox" class="small"></span>
        <button onclick="exportCapcut(this)" title="Clips limpios por plano, voz, música, efectos sueltos y rótulos editables, para montarlo a tu manera en CapCut">${icon("scissors")} Proyecto para CapCut</button>
        <span id="capcutBox" class="small"></span></div>` : ""}
    ${v.stagesDone >= 11 || v.hasVideo ? '<section id="storyBox" aria-label="Storyboard"></section>' : ""}
    ${scenesPreview}${dubs}
    ${v.hasVideo || v.published ? '<div id="repBox"></div>' : ""}
    ${v.published ? '<div id="whyBox"></div>' : ""}
    <div class="tabs">${Object.entries(docs).map(([k, [name]]) => `<button class="${k === tab ? "on" : ""}" onclick="tab='${k}';window.tabPicked=1;route()">${name}</button>`).join("")}</div>
    <div class="card">${body}</div></div>
    <aside class="vside">${v.hasVideo ? doing : ""}${ytView}<div class="row" id="pilotBox"></div><div id="pilotReport"></div>${titles}${thumbs}${shorts}</aside></div>`);
  // the storyboard: every shot with its frame, its minute, where the footage came from and its line of the script
  if ($("#storyBox")) api("/api/review/" + encodeURIComponent(slug)).then((r) => {
    const shots = r.shots || [], seen = {correcta: 0, dudosa: 0, incorrecta: 0};
    shots.forEach((sh) => { const k = sh.label && sh.label.verdict; if (k in seen) seen[k]++; });
    const left = shots.length - seen.correcta - seen.dudosa - seen.incorrecta, shown = shots.slice(0, 24);
    fill($("#storyBox"), shots.length ? `<div class="hb"><h2>Storyboard · ${shots.length} planos</h2>
        <div class="tools small"><span><b class="t-ok">${seen.correcta}</b> bien</span><span><b class="t-warn">${seen.dudosa}</b> dudosos</span><span><b class="t-bad">${seen.incorrecta}</b> mal</span>
          <span class="muted">${left} sin revisar</span><a href="#/revisar/${encodeURIComponent(slug)}">Revisar clips →</a></div></div>
      <div class="story">${shown.map((sh) => `<a class="shot ${(sh.label && sh.label.verdict) || ""}" href="#/revisar/${encodeURIComponent(slug)}" title="${esc(sh.title || sh.credit || sh.source || "")}">
          <span class="f">${thumb(`/api/review/${encodeURIComponent(slug)}/frame/${sh.id}.jpg`, "", "")}<span class="tl">${clock(sh.at)}</span>${sh.source ? `<span class="tr">${esc(String(sh.source).slice(0, 14))}</span>` : ""}</span>
          <span class="q">«${esc(sh.text || "—")}»</span></a>`).join("")}</div>
      ${shots.length > shown.length ? `<a class="btn sm mt-2" href="#/revisar/${encodeURIComponent(slug)}">Ver los ${shots.length} planos</a>` : ""}` : "");
  }).catch(() => {});
  const repLoad = async () => {
    const box = $("#repBox");
    if (!box) return;
    const r = await api(`/api/video/${encodeURIComponent(slug)}/repeticion`);
    const mark = {ok: vMark("t-ok", "check", "Bien"), warn: vMark("t-warn", "alert", "Aviso"), skip: vMark("muted", "minus", "No se comprueba")};
    fill(box, `<h2>Riesgo de repetición: <span class="${{bajo: "t-ok", medio: "t-warn", alto: "t-bad"}[r.risk]}">${{bajo: "bajo", medio: "medio", alto: "alto"}[r.risk]}</span></h2>
      <div class="card small"><div class="muted mb-2">YouTube no castiga la voz de IA sino los vídeos que parecen copias unos de otros
        (actualización del programa de socios de julio de 2025). Comparado con los ${r.compared} últimos vídeos del canal.</div>
        ${r.checks.map((c) => `<div class="mt-1">${mark[c.status]} <b>${esc(c.name)}:</b> ${esc(c.text)}</div>`).join("")}</div>`);
  };
  repLoad();
  const whyLoad = async () => {
    const box = $("#whyBox");
    if (!box) return;
    const w = await api(`/api/video/${encodeURIComponent(slug)}/porque`);
    if (!w.curve || !w.curve.points.length) { fill(box, '<h2>¿Por qué funcionó?</h2><div class="card small muted">Aún sin visitas registradas: el vigilante las apunta a la 1 h, 3 h, 6 h, 12 h, 1, 2, 4, 7, 14 y 30 días (hace falta el enlace de YouTube).</div>'); return; }
    const c = w.curve, r = w.report, W = 640, H = 220, P = 34;
    const hours = [1, ...c.points.map((p) => p[0]), ...c.normal.map((b) => b.hours)];
    const maxH = Math.max(...hours), maxV = Math.max(1, ...c.points.map((p) => p[1]), ...c.normal.map((b) => b.high));
    const x = (h) => P + (W - 2 * P) * Math.log(Math.max(h, 1)) / Math.log(Math.max(maxH, 2));
    const y = (v) => H - P + (2 * P - H) * v / maxV;
    const band = c.normal.length ? `<polygon points="${c.normal.map((b) => `${x(b.hours)},${y(b.high)}`).join(" ")} ${[...c.normal].reverse().map((b) => `${x(b.hours)},${y(b.low)}`).join(" ")}" fill="rgba(150,150,150,.22)"/>
      <polyline points="${c.normal.map((b) => `${x(b.hours)},${y(b.median)}`).join(" ")}" fill="none" stroke="#d6a400" stroke-width="2" stroke-dasharray="6 5"/>` : "";
    const ticks = [[1, "1 h"], [6, "6 h"], [24, "1 d"], [168, "7 d"], [720, "30 d"]].filter(([h]) => h <= maxH * 1.01);
    const fmt = (n) => n >= 1000 ? (n / 1000).toFixed(1).replace(".", ",") + " K" : String(n);
    const line = (k, label) => r && r[k] ? `<div class="mt-1"><b class="t-warn">${label}:</b> ${esc(r[k])}</div>` : "";
    fill(box, `<h2>¿Por qué funcionó?</h2><div class="card">
      <svg class="chart" viewBox="0 0 ${W} ${H}">${band}
        <polyline points="${c.points.map((p) => `${x(p[0])},${y(p[1])}`).join(" ")}" fill="none" stroke="#2bb3e6" stroke-width="3"/>
        ${c.points.map((p) => `<circle cx="${x(p[0])}" cy="${y(p[1])}" r="3.5" fill="#2bb3e6"/>`).join("")}
        <line x1="${P}" x2="${W - P}" y1="${H - P}" y2="${H - P}" class="muted" stroke="currentColor"/>
        ${ticks.map(([h, t]) => `<text x="${x(h)}" y="${H - P + 16}" font-size="11" text-anchor="middle" class="muted" fill="currentColor">${t}</text>`).join("")}
        <text x="${P}" y="${P - 10}" font-size="11" class="muted" fill="currentColor">${fmt(maxV)}</text></svg>
      <div class="small muted">— este vídeo · - - lo normal del canal · gris: lo normal (la mitad central de sus vídeos)</div>
      <div class="mt-2"><b>${fmt(c.views)}</b> visitas a ${c.age < 48 ? Math.round(c.age) + " h" : Math.round(c.age / 24) + " días"}${c.usual ? ` · lo normal del canal a esa edad: ${fmt(c.usual)} (<b>${String(c.ratio).replace(".", ",")}x</b>)` : " · aún pocos vídeos del canal para comparar"}</div>
      ${r ? `${line("topic", "tema")}${line("title", "título")}${line("length", "duración")}${line("hook", "gancho")}${line("lesson", "lección")}
        <div class="small muted mt-2">Analizado el ${esc(r.at.slice(0, 10))}: la lección entra en los próximos guiones del canal.</div>` : ""}
      <button class="mt-2" onclick="whyAnalyse(this)">${r ? "Volver a analizar" : "Analizar ahora"}</button></div>`);
  };
  window.whyAnalyse = async (button) => {
    button.disabled = true; button.textContent = "Analizando…";
    try { await post(`/api/video/${encodeURIComponent(slug)}/porque`); } catch (e) { oops(e); }
    whyLoad();
  };
  whyLoad();
  window.exportPremiere = async (button) => {
    button.disabled = true;
    try { await post(`/api/video/${encodeURIComponent(slug)}/exportar`); } catch (e) { oops(e); button.disabled = false; return; }
    exportWatch();
  };
  const exportWatch = async () => {
    const box = $("#exportBox");
    if (!box) return;
    const e = await api(`/api/video/${encodeURIComponent(slug)}/exportar`);
    if (e.zip) fill(box, `<a class="btn" href="${base}${encodeURIComponent(e.zip)}?download">Descargar proyecto (${e.mb} MB)</a>`);
    else if (e.job.failed) fill(box, `<span class="pill error">No se pudo: ${esc((e.job.log || "").trim().split("\n").pop() || "error")}</span>`);
    else if (e.job.running) { fill(box, "Preparando el proyecto…"); setTimeout(exportWatch, 3000); }
  };
  exportWatch();
  window.exportCapcut = async (button) => {
    button.disabled = true;
    try { await post(`/api/video/${encodeURIComponent(slug)}/capcut`); } catch (e) { oops(e); button.disabled = false; return; }
    capcutWatch();
  };
  const capcutWatch = async () => {
    const box = $("#capcutBox");
    if (!box) return;
    const e = await api(`/api/video/${encodeURIComponent(slug)}/capcut`);
    if (e.zip) fill(box, `<a class="btn" href="${base}${encodeURIComponent(e.zip)}?download">Descargar para CapCut (${e.mb} MB)</a>`);
    else if (e.job.failed) fill(box, `<span class="pill error">No se pudo: ${esc((e.job.log || "").trim().split("\n").pop() || "error")}</span>`);
    else if (e.job.running) { fill(box, "Preparando el proyecto de CapCut (unos minutos)…"); setTimeout(capcutWatch, 4000); }
  };
  capcutWatch();
  window.markUploaded = async (value = true) => {
    const url = value ? await askText("Enlace del vídeo en YouTube (opcional):", "", {placeholder: "https://youtu.be/…", ok: "Marcar como subido"}) : "";
    if (url === null) return;
    try { await post(`/api/video/${encodeURIComponent(slug)}/published`, {value, url}); } catch (e) { return toast("No se pudo marcar: " + e.message, "bad"); }
    route();
  };
  // «Rehacer desde…»: the choice on the page itself (prompt() is silenced in some browsers and in the app, and then
  // the button did nothing at all)
  window.redoFrom = (btn) => {
    const old = document.getElementById("redobox");
    if (old) { old.remove(); return; }
    const box = document.createElement("div");
    box.id = "redobox";
    box.className = "notice";
    box.innerHTML = `<b>¿Desde dónde lo rehago?</b>
      <div class="row mt-2">
        <button onclick="redoGo(['timeline'])">Solo el montaje (rápido)</button>
        <button class="main" onclick="redoGo(['judge'])">Elegir imágenes otra vez (juez y relleno)</button>
        <button onclick="redoGo(['planner'])">Todo (planificación, búsqueda y montaje)</button>
        <button onclick="document.getElementById('redobox').remove()">Cancelar</button></div>
      <div id="redomsg" class="small muted mt-2">Reaprovecha las descargas y la voz.</div>`;
    const head = document.querySelector(".vhead");          // under the title, not inside the «Más ▾» menu
    head ? head.insertAdjacentElement("afterend", box) : $("#app").prepend(box);
    document.querySelectorAll(".more.open").forEach((m) => m.classList.remove("open"));
    box.scrollIntoView({behavior: "smooth", block: "nearest"});
  };
  window.redoGo = async (stages) => {
    const msg = document.getElementById("redomsg");
    if (msg) msg.textContent = "Poniéndolo en la cola…";
    try {
      const r = await post(`/api/video/${encodeURIComponent(slug)}/redo`, {stages});
      if (msg) msg.textContent = r.message || "En la cola: se rehará en su turno.";
      setTimeout(route, 1500);
    } catch (e) { if (msg) msg.textContent = "No se pudo: " + e.message; }
  };
  window.act = async (what) => {
    try {
      const r = await post(`/api/video/${encodeURIComponent(slug)}/${what}`);
      if (r.message) toast(r.message, "ok");
      what === "archive" && r.ok !== false ? (location.hash = "#/") : setTimeout(route, 2500);
    } catch (e) { oops(e); }
  };
  const logBox = $("#log"); if (logBox) logBox.scrollTop = logBox.scrollHeight;
  pilotBox(v.slug, v);
  if (v.status === "haciendo") schedule(() => { apiCache.clear(); route(); }, 10000);
}
document.addEventListener("click", (e) => { if (!e.target.closest(".more")) document.querySelectorAll(".more.open").forEach((m) => m.classList.remove("open")); });

async function pilotBox(slug, v) {
  const box = $("#pilotBox"); if (!box) return;
  const p = await api(`/api/video/${encodeURIComponent(slug)}/pilot`).catch(() => null); if (!p) return;
  const url = `/api/video/${encodeURIComponent(slug)}/pilot`;
  if (p.pilot) {
    fill(box, `<span class="pill">${icon("flask")} Piloto por escenas · referencia ${esc(p.pilot.reference || "—")}</span>
      ${v.status === "hecho" ? `<button onclick="pilotReport('${esc(slug)}')">Informe del piloto</button>` : ""}
      <button onclick="ask('¿Volver este vídeo a la búsqueda por plano?', {ok: 'Quitar piloto'}).then((yes) => yes && post('${url}', {on: false}).then(() => route()))">Quitar piloto</button>`);
    if (p.report) showPilot(p.report);
  } else if (!p.others.length && !v.stagesDone) {
    fill(box, `<button title="Solo este vídeo buscará por escenas; el resto sigue igual" onclick="startPilot('${esc(slug)}', ${esc(JSON.stringify(p.references))})">${icon("flask")} Hacer de piloto por escenas</button>`);
  }
}
window.startPilot = async (slug, refs) => {
  const ref = await askText("Vídeo ya hecho de referencia, de tema y complejidad parecidos (escribe su nombre o elígelo de la lista):", "", {options: refs.slice(-15), ok: "Activar piloto"});
  if (ref === null || !ref.trim()) return;
  try { const r = await post(`/api/video/${encodeURIComponent(slug)}/pilot`, {reference: ref.trim()}); toast("Piloto activado. Referencia: " + (r.reference || "ninguna"), "ok"); route(); }
  catch (e) { oops(e); }
};
window.pilotReport = async (slug) => {
  try { showPilot(await post(`/api/video/${encodeURIComponent(slug)}/pilot`, {report: true})); } catch (e) { oops(e); }
};
function showPilot(r) {
  const show = (x) => x == null ? "—" : (typeof x === "number" && x > 0 && x < 1 && !Number.isInteger(x)) ? Math.round(x * 100) + " %" : x;
  fill($("#pilotReport"), `<div class="card"><b>Piloto: ${esc(r.pilot.video)} frente a ${esc(r.reference.video)}</b>
    <div class="scroll-x mt-2"><table><tr><th></th><th>Referencia</th><th>Piloto</th><th></th></tr>
    ${r.rows.map((x) => `<tr><td>${esc(x.label)}</td><td>${show(x.reference)}</td><td><b>${show(x.pilot)}</b></td><td>${x.better == null ? "" : x.better ? vMark("t-ok", "check", "Mejor") : vMark("t-warn", "alert", "Peor")}</td></tr>`).join("")}</table></div>
    ${r.pending.map((p) => `<div class="notice">${esc(p)}</div>`).join("")}</div>`);
}

// «Cambiar de canal»: a select in place of the ✏️; the video is not made again, it is only counted elsewhere
async function changeChannel(slug, current, el) {
  const list = (await api("/api/settings")).channels || [];
  const select = document.createElement("select");
  select.className = "w-auto";
  select.innerHTML = list.map((c) => `<option ${c === current ? "selected" : ""}>${esc(c)}</option>`).join("");
  select.onchange = async () => { await post(`/api/video/${encodeURIComponent(slug)}/channel`, {channel: select.value}); route(); };
  el.replaceWith(select); select.focus();
}

async function copyForClaude(slug, button) {
  let text = "";
  try { text = (await post(`/api/video/${encodeURIComponent(slug)}/for-claude`)).text; }
  catch (e) { oops(e); return; }
  try { await navigator.clipboard.writeText(text); button.textContent = "Copiado ✓ pégalo en el chat"; return; }
  catch (e) {}                                     // Safari refuses the clipboard after waiting for the server
  const modal = sheet(`<div class="row between"><b>Para Claude</b>
    <button onclick="document.getElementById('modal').close()">Cerrar</button></div>
    <div class="small muted my-2">Mantén pulsado el texto → Seleccionar todo → Copiar, y pégalo en el chat.</div>
    <textarea readonly class="tall" aria-label="Texto para Claude">${esc(text)}</textarea>`);
  const box = modal.querySelector("textarea"); box.focus(); box.select();
}

// --- Errores: review the clips of a video -------------------------------------------------------------------------
let reviewFilter = "todos";
async function reviewPage(slug) {
  const r = await api("/api/review/" + encodeURIComponent(slug));
  const shots = r.shots;
  const verdictOf = (sh) => sh.label && sh.label.verdict;
  const counts = () => { const c = {correcta: 0, incorrecta: 0, dudosa: 0}; shots.forEach((sh) => verdictOf(sh) && c[verdictOf(sh)]++); return c; };
  const shownList = () => shots.filter((sh) => reviewFilter === "todos" || (reviewFilter === "pendientes" ? !sh.label : verdictOf(sh) === reviewFilter));
  const options = Object.entries(r.reasons).map(([k, n]) => `<option value="${k}">${esc(n)}</option>`).join("");
  const card = (sh, i) => { const v = verdictOf(sh); return `<div class="card ${v || ""}" id="r-${sh.id}" data-i="${i}" tabindex="0" onclick="focusCard(${i})">
        <span class="n">${i + 1}</span>
        ${thumb(`/api/review/${encodeURIComponent(slug)}/frame/${sh.id}.jpg`)}
        <div class="body">
          <div class="quote">«${esc(sh.text || "—")}»</div>
          <div class="src">${clock(sh.at)} · ${esc(sh.title || sh.credit || sh.source || "")}${sh.url ? ` · <a href="${esc(sh.url)}" target="_blank" rel="noopener">fuente</a>` : ""}</div>
          <div class="acts">
            <button class="b-ok ${v && v !== "correcta" ? "off" : ""}" onclick="event.stopPropagation();mark('${sh.id}','correcta')" title="tecla 1">Correcta</button>
            <select id="why-${sh.id}" aria-label="Por qué es incorrecta" onclick="event.stopPropagation()">${options}</select>
            <button class="b-bad ${v && v !== "incorrecta" ? "off" : ""}" onclick="event.stopPropagation();mark('${sh.id}','incorrecta')" title="tecla 3">Incorrecta</button>
            <button class="b-doubt ${v && v !== "dudosa" ? "off" : ""}" onclick="event.stopPropagation();mark('${sh.id}','dudosa')" title="tecla 2">Dudosa</button>
            ${v ? `<button onclick="event.stopPropagation();mark('${sh.id}',null)" class="icon" aria-label="Quitar (tecla 0)" title="Quitar (tecla 0)">${icon("undo")}</button>` : ""}
          </div></div></div>`; };
  const header = () => { const c = counts(), left = shots.length - c.correcta - c.incorrecta - c.dudosa; return `
    <div class="row between"><h1 class="m-0">Revisar clips <span class="small muted n4">${esc(slug)}</span></h1>
      <span class="row"><a class="btn" href="#/video/${encodeURIComponent(slug)}">Ficha del vídeo</a>
      ${c.incorrecta ? `<button class="main" onclick="fixVideo()" ${r.job.running ? "disabled" : ""}>Rehacer con correcciones (${c.incorrecta})</button>` : ""}</span></div>
    <div class="row gap-3 mt-2"><div class="bar ok grow m-0"><i style="--v:${Math.round(100 * (shots.length - left) / Math.max(1, shots.length))}%"></i></div>
      <span class="small muted">${shots.length - left} de ${shots.length} revisados</span></div>
    <div class="row between"><div class="tabs">${[["todos", `Todos (${shots.length})`], ["pendientes", `Sin revisar (${left})`], ["incorrecta", `Incorrectos (${c.incorrecta})`],
      ["dudosa", `Dudosos (${c.dudosa})`], ["correcta", `Correctos (${c.correcta})`]].map(([k, n]) =>
      `<button class="${k === reviewFilter ? "on" : ""}" onclick="reviewFilter='${k}';route()">${n}</button>`).join("")}</div>
      <span class="keys"><kbd>←</kbd><kbd>→</kbd> moverse · <kbd>1</kbd> correcta · <kbd>2</kbd> dudosa · <kbd>3</kbd> incorrecta · <kbd>0</kbd> quitar</span></div>`; };
  show(`<div class="rtool" id="rtool">${header()}</div>
    <div class="small muted mb-2">Marca cada clip. Lo incorrecto no se vuelve a usar en ningún vídeo; «Rehacer con correcciones» cambia esos planos y vuelve a montar el vídeo.</div>
    ${jobLine(r.job, "Rehaciendo el vídeo con tus correcciones")}
    <div class="review" id="review">${shownList().map(card).join("") || '<div class="notice">Nada en este filtro.</div>'}</div>`);
  shots.forEach((sh) => { const sel = document.getElementById("why-" + sh.id); if (sel && sh.label && sh.label.reason) sel.value = sh.label.reason; });
  let focus = -1;
  const cards = () => [...document.querySelectorAll("#review .card[data-i]")];
  window.focusCard = (i, scroll = false) => {
    const list = cards(); if (!list.length) return;
    focus = Math.max(0, Math.min(list.length - 1, i));
    list.forEach((c) => c.classList.toggle("focus", +c.dataset.i === focus));
    if (scroll) list.find((c) => +c.dataset.i === focus).scrollIntoView({block: "center", behavior: "smooth"});
  };
  // marking repaints only that card (no reload, no lost scroll) and moves the focus to the next one
  window.mark = async (id, verdict) => {
    const sel = document.getElementById("why-" + id);
    const reason = verdict === "incorrecta" && sel ? sel.value : "";
    const sh = shots.find((x) => x.id === id);
    try { await post(`/api/review/${encodeURIComponent(slug)}/${id}`, {verdict, reason}); } catch (e) { return oops(e); }
    sh.label = verdict ? {verdict, reason} : null;
    const old = document.getElementById("r-" + id);
    if (old) { const i = +old.dataset.i; old.outerHTML = card(sh, i); if (sel) { const again = document.getElementById("why-" + id); if (again) again.value = sel.value; } }
    fill($("#rtool"), header());
    if (verdict && reviewFilter !== "todos") { const el = document.getElementById("r-" + id); if (el && (reviewFilter === "pendientes" || reviewFilter !== verdict)) el.remove(); focusCard(focus, true); }
    else focusCard(focus + 1, true);
  };
  window.fixVideo = async () => { await post(`/api/video/${encodeURIComponent(slug)}/fix`); route(); };
  const keys = (e) => {
    if (e.target.matches("input, textarea, select")) return;
    const list = cards(); if (!list.length) return;
    const current = list.find((c) => +c.dataset.i === focus);
    const id = current && current.id.slice(2);
    if (e.key === "ArrowRight" || e.key === "j") { e.preventDefault(); focusCard(focus < 0 ? 0 : focus + 1, true); }
    else if (e.key === "ArrowLeft" || e.key === "k") { e.preventDefault(); focusCard(Math.max(0, focus - 1), true); }
    else if (id && e.key === "1") mark(id, "correcta");
    else if (id && e.key === "2") mark(id, "dudosa");
    else if (id && e.key === "3") mark(id, "incorrecta");
    else if (id && e.key === "0") mark(id, null);
  };
  pageKeys = keys;
  if (r.job.running) schedule(route, 8000);
}

// --- Decisiones del relleno ----------------------------------------------------------------------------------------
async function decisionsPage(slug) {
  const r = await api("/api/decisions/" + encodeURIComponent(slug));
  const picks = r.items.filter((i) => i.pick).length;
  const img = (shot, key) => `/api/decisions/${encodeURIComponent(slug)}/frame?shot=${shot}&key=${encodeURIComponent(key)}`;
  show(`
    <div class="row between"><h1>Decisiones del relleno · <a href="#/video/${encodeURIComponent(slug)}">${esc(slug)}</a></h1>
      <button class="main" onclick="applyPicks()" ${r.job.running ? "disabled" : ""}>Aplicar y rehacer${picks ? ` (${picks})` : ""}</button></div>
    <div class="small muted">Planos donde el programa no pudo usar la primera elección y buscó otra cosa. Mira lo que puso: si está bien, «Bien así»; si no, elige la opción que debería ir. Aprende de ello: lo que recuperas no vuelve a descartarse y te dice qué comprobación es demasiado estricta.</div>
    ${r.summary.tips.length ? `<div class="notice elf">${icon("bulb")} ${r.summary.tips.map(esc).join("<br>")}</div>` : ""}
    ${jobLine(r.job, "Rehaciendo el vídeo con tus elecciones")}
    <div class="keys mt-2"><kbd>←</kbd><kbd>→</kbd> moverse · <kbd>Enter</kbd> bien así · <kbd>1</kbd>…<kbd>9</kbd> usar esa opción</div>
    ${r.items.map((i) => `<div class="card mt-4" data-shot="${esc(i.shot)}" data-options="${esc(i.options.map((o) => o.key).join("\t"))}">
      <div class="row between nowrap top"><b class="mw0">${esc(i.shot)} · «${esc(i.text)}»</b>
        <span class="pill ${i.verdict === "correcta" ? "hecho" : i.pick ? "haciendo" : ""}">${i.verdict === "correcta" ? "bien así" : i.pick ? "elegida otra" : "sin revisar"}</span></div>
      <div class="small my-2"><b>Por qué buscó otra cosa:</b> ${esc(i.kind)}${i.reason && i.kind !== i.reason ? ` <span class="muted">(${esc(i.reason.slice(0, 140))}${i.reason.length > 140 ? "…" : ""})</span>` : ""}</div>
      ${i.judgeReason ? `<details class="small muted"><summary>Lo que dijo el juez</summary>${esc(i.judgeReason)}</details>` : ""}
      <div class="vids sm mt-3">
        <div class="card pick">${thumb(img(i.shot, "final"))}
          <div class="body small"><b>Lo que puso</b>${i.method ? ` · ${esc(i.method)}` : ""}${i.resolved ? "" : " · (no encontró nada)"}
          <div class="row mt-2"><button class="b-ok" onclick="decide('${i.shot}', {ok: true})">Bien así</button></div></div></div>
        ${i.options.map((o) => `<div class="card ${i.pick === o.key ? "correcta" : ""}">
          ${thumb(img(i.shot, o.key))}
          <div class="body small">${o.original ? '<b>La que eligió el juez</b> (descartada) · ' : ""}${esc(o.title).slice(0, 80)}
            <div class="muted">${esc(o.channel)}${o.score != null ? ` · nota ${o.score}` : ""}${o.kind === "image" ? " · foto" : ""}</div>
            <div class="row mt-2"><button onclick="decide('${i.shot}', {pick: '${esc(o.key)}'})">${i.pick === o.key ? `${icon("check")} Elegida` : `Usar esta${i.options.indexOf(o) < 9 ? ` <span class="muted">(${i.options.indexOf(o) + 1})</span>` : ""}`}</button></div></div></div>`).join("")}
      </div></div>`).join("") || empty("check", "En este vídeo el relleno no tuvo que decidir nada.")}`);
  window.decide = async (shot, body) => { const y = window.scrollY; await post(`/api/decisions/${encodeURIComponent(slug)}/${shot}`, body); await route(); window.scrollTo(0, y); };
  window.applyPicks = async () => { try { await post(`/api/decisions/${encodeURIComponent(slug)}/apply`); route(); } catch (e) { oops(e); } };
  // keyboard: ←/→ between shots, Enter = «bien así», 1-9 = that option
  let at = -1;
  const blocks = () => [...document.querySelectorAll("#app > .card[data-shot]")];
  const go = (i) => { const list = blocks(); if (!list.length) return; at = Math.max(0, Math.min(list.length - 1, i));
    list.forEach((b, j) => b.classList.toggle("focus", j === at)); list[at].scrollIntoView({block: "center", behavior: "smooth"}); };
  const keys = (e) => {
    if (e.target.matches("input, textarea, select")) return;
    const list = blocks(), b = list[at];
    if (e.key === "ArrowRight" || e.key === "j") { e.preventDefault(); go(at + 1); }
    else if (e.key === "ArrowLeft" || e.key === "k") { e.preventDefault(); go(Math.max(0, at - 1)); }
    else if (b && e.key === "Enter") decide(b.dataset.shot, {ok: true});
    else if (b && /^[1-9]$/.test(e.key)) { const key = (b.dataset.options || "").split("\t")[+e.key - 1]; if (key) decide(b.dataset.shot, {pick: key}); }
  };
  pageKeys = keys;
  if (r.job.running) schedule(route, 8000);
}
