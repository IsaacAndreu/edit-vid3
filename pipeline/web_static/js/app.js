function schedule(fn, ms) { clearTimeout(timer); timer = setTimeout(() => { if (!document.hidden) fn(); else schedule(fn, ms); }, ms); }

async function route() {
  clearTimeout(timer);
  document.body.classList.remove("menu");
  let hash = location.hash || "#/";
  if (window.partner && !partnerMay(hash)) { hash = "#/"; history.replaceState(null, "", "#/"); }
  document.querySelectorAll("header nav a").forEach((a) => a.classList.toggle("on", a.getAttribute("href") === hash.split("/").slice(0, 2).join("/") || (hash === "#/" && a.getAttribute("href") === "#/")));
  document.querySelectorAll("header .dd").forEach((d) => { d.classList.remove("open"); d.classList.toggle("on", !!d.querySelector("a.on")); });
  const slow = setTimeout(() => { $("#app").classList.add("loading");          // a slow answer shows it is working
    if (!$("#app").firstElementChild) $("#app").innerHTML = '<div class="skel"><div style="width:40%"></div><div class="kpis"><div></div><div></div><div></div><div></div></div><div class="tall"></div><div class="tall"></div></div>'; }, 250);
  try {
    if (hash.startsWith("#/video/")) await videoPage(decodeURIComponent(hash.slice(8)));
    else if (hash.startsWith("#/revisar/")) await reviewPage(decodeURIComponent(hash.slice(10)));
    else if (hash.startsWith("#/decisiones/")) await decisionsPage(decodeURIComponent(hash.slice(13)));
    else if (hash === "#/errores") await errorsPage();
    else if (hash === "#/competencia") await radarPage();
    else if (hash === "#/canal") await channelPage();
    else if (hash === "#/canal-nuevo") await newChannelPage();
    else if (hash === "#/nuevo") await newVideo();
    else if (hash === "#/calendario") await calendarPage();
    else if (hash === "#/subir") await uploadPage();
    else if (hash === "#/biblioteca") await libraryPage();
    else if (hash.startsWith("#/biblioteca/")) await libraryEntity(decodeURIComponent(hash.slice(13)));
    else if (hash === "#/guiones") await scriptsPage();
    else if (hash === "#/voces") await voicesPage();
    else if (hash === "#/tablero") await boardPage();
    else if (hash === "#/estadisticas") await stats();
    else if (hash === "#/gasto") await spendPage();
    else if (hash === "#/experimentos") await experimentsPage();
    else if (hash === "#/piloto") await pilotPage();
    else if (hash === "#/servidor") await serverPage();
    else if (hash === "#/videos") await allVideosPage();
    else if (hash === "#/ajustes") await settingsPage();
    else if (hash === "#/cuenta") await accountPage();
    else if (hash.startsWith("#/buscar/")) await searchPage(decodeURIComponent(hash.slice(9)));
    else await home();
    const s = data && data.service;
    // a tab opened before an update keeps the old page (it is one page): reload it once the server has new code
    if (s && s.code && s.code.id) {
      if (!window.codeId) window.codeId = s.code.id;
      else if (window.codeId !== s.code.id) { location.reload(); return; }
    }
    $("#service").textContent = window.partner ? "👤 " + window.partner : s ? (s.paused ? "⏸ en pausa" : s.watching ? "● vigilando" : "") : "";
    $("#service").title = s && s.code ? `Código del servidor: ${s.code.what} (${s.code.at.slice(0, 16).replace("T", " ")}) · se actualiza solo` : "";
  } catch (e) { if (e.message !== "login") $("#app").innerHTML = `<div class="notice bad">${esc(e.message)}</div>`; }
  clearTimeout(slow); $("#app").classList.remove("loading");
}

document.addEventListener("click", (e) => {     // menus of the header: open on click, close anywhere else
  const dd = e.target.closest(".dd");
  document.querySelectorAll("header .dd").forEach((d) => { if (d !== dd) d.classList.remove("open"); });
  if (dd && e.target.closest(".dd > button")) dd.classList.toggle("open");
  const link = e.target.closest("header a[href^='#/']");
  if (link && link.getAttribute("href") === (location.hash || "#/")) { e.preventDefault(); route(); }   // same page: reload it
});

async function logout() { await post("/api/logout").catch(() => {}); location.hash = "#/"; location.reload(); }

// A partner (another person with their own channels) sees only these pages; the server refuses the rest anyway
const PARTNER_PAGES = ["#/", "#/nuevo", "#/canal-nuevo", "#/subir", "#/videos", "#/guiones", "#/calendario", "#/tablero",
  "#/competencia", "#/canal", "#/estadisticas", "#/gasto", "#/voces", "#/cuenta"];
const PARTNER_PREFIXES = ["#/video/", "#/revisar/", "#/decisiones/", "#/buscar/"];
function partnerMay(hash) { return PARTNER_PAGES.includes(hash) || PARTNER_PREFIXES.some((p) => hash.startsWith(p)); }

async function start() {
  const session = await fetch("/api/session").then((r) => r.json());
  if (!session.authorised) return showLogin();
  window.partner = session.partner || null;
  if (window.partner) {
    document.body.classList.add("partner");
    document.querySelectorAll("header nav a").forEach((a) => { if (!PARTNER_PAGES.includes(a.getAttribute("href"))) a.remove(); });
    const spend = document.querySelector('header nav a[href="#/gasto"]');
    if (spend) spend.lastChild.textContent = "Mi gasto";
    const nav = document.querySelector("header nav");
    nav.querySelectorAll(".sec").forEach((sec) => sec.remove());
    nav.insertAdjacentHTML("beforeend", `<a href="#/voces"><span class="ic"><svg viewBox="0 0 24 24"><path d="M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3z"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/></svg></span>Voces</a>
      <a href="#/cuenta"><span class="ic"><svg viewBox="0 0 24 24"><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></svg></span>Mi cuenta</a>`);
    $("#service").textContent = "👤 " + window.partner;
  }
  $("#top").classList.remove("hide");
  document.body.classList.add("authed");
  window.onhashchange = () => { tab = "diagnosis"; window.tabPicked = 0; window.logAll = 0; route(); };
  route();
}
start();
