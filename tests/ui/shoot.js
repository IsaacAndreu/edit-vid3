#!/usr/bin/env node
// Screenshots + metrics of every page of the Estudio, against the mock (mock.js).
//   node shoot.js --base http://127.0.0.1:8099 --out <dir> [--partner] [--routes "#/,#/calendario"] [--no-shots]
//                 [--only desktop-dark] [--jobs 6]
// It only knows `#app`, `header nav a` and the hash routes of the front-end.
"use strict";

const fs = require("fs");
const path = require("path");
const {chromium} = require("playwright");
const mock = require("./mock");

const S = mock.SLUGS;
const OWNER_ROUTES = ["#/", "#/nuevo", "#/subir", "#/videos", "#/guiones", "#/calendario", "#/tablero", "#/competencia", "#/canal", "#/estadisticas",
  "#/experimentos", "#/piloto", "#/biblioteca", `#/biblioteca/${S.library}`, "#/errores", "#/gasto", "#/servidor", "#/ajustes", "#/voces", "#/canal-nuevo",
  `#/buscar/${S.search}`, `#/video/${S.haciendo}`, `#/video/${S.reintento}`, `#/video/${S.error}`, `#/video/${S.hecho}`, `#/video/${S.publicado}`,
  `#/revisar/${S.review}`, `#/decisiones/${S.decisions}`];
// PARTNER_PAGES + one of each PARTNER_PREFIXES of the app (index.html), plus #/cuenta
const PARTNER_ROUTES = ["#/", "#/nuevo", "#/canal-nuevo", "#/subir", "#/videos", "#/guiones", "#/calendario", "#/tablero", "#/competencia", "#/canal", "#/estadisticas",
  "#/gasto", "#/voces", "#/cuenta", `#/buscar/${S.search}`, `#/video/${S.haciendo}`, `#/video/${S.reintento}`, `#/video/${S.error}`, `#/video/${S.hecho}`,
  `#/video/${S.publicado}`, `#/revisar/${S.review}`, `#/decisiones/${S.decisions}`];
const PARTNER_FORBIDDEN = ["#/servidor", "#/ajustes", "#/piloto", "#/experimentos", "#/biblioteca", "#/errores"];     // must land on #/
const PARTNER_NAV = ["#/nuevo", "#/", "#/subir", "#/videos", "#/guiones", "#/calendario", "#/tablero", "#/competencia", "#/canal", "#/estadisticas", "#/gasto", "#/voces", "#/cuenta"];
const VIEWPORTS = {desktop: {viewport: {width: 1440, height: 900}}, mobile: {viewport: {width: 390, height: 844}, isMobile: true, hasTouch: true}};
const SCHEMES = ["dark", "light"];
const MAX_SHOT_HEIGHT = 5000, SETTLE_MS = 400, SETTLE_CAP_MS = 12000;

function args() {
  const a = process.argv.slice(2), o = {base: "http://127.0.0.1:8099", out: path.join(__dirname, "out"), jobs: 6, shots: true};
  for (let i = 0; i < a.length; i++) {
    if (a[i] === "--base") o.base = a[++i].replace(/\/$/, "");
    else if (a[i] === "--out") o.out = a[++i];
    else if (a[i] === "--partner") o.partner = true;
    else if (a[i] === "--routes") o.routes = a[++i].split(",").map((r) => r.trim()).filter(Boolean);
    else if (a[i] === "--no-shots") o.shots = false;
    else if (a[i] === "--only") o.only = a[++i];
    else if (a[i] === "--jobs") o.jobs = +a[++i];
    else { console.error("Opción desconocida: " + a[i]); process.exit(2); }
  }
  return o;
}
const slugOf = (route) => route === "#/" ? "inicio" : route.replace(/^#\//, "").replace(/[^a-zA-Z0-9_-]+/g, "_");

// every DOM change stamps the clock: «settled» = nothing changed for SETTLE_MS and no request is in flight
const INIT = () => {
  window.__lastMut = performance.now(); window.__muts = 0;
  const start = () => new MutationObserver((list) => { window.__lastMut = performance.now(); window.__muts += list.length; })
    .observe(document.documentElement, {subtree: true, childList: true, attributes: true, characterData: true});
  if (document.documentElement) start(); else document.addEventListener("readystatechange", start, {once: true});
  window.alert = () => {}; window.confirm = () => false; window.prompt = () => null;
};

async function settle(page, track, cap = SETTLE_CAP_MS) {
  const t0 = Date.now();
  let state = null;
  while (Date.now() - t0 < cap) {
    state = await page.evaluate(() => ({quiet: performance.now() - window.__lastMut, last: window.__lastMut, now: performance.now(),
      painted: !!(document.querySelector("#app") && document.querySelector("#app").firstElementChild), loading: !!document.querySelector("#app.loading")})).catch(() => null);
    if (state && state.painted && !state.loading && state.quiet >= SETTLE_MS && track.inflight.size === 0) return {...state, settled: true};
    await page.waitForTimeout(80);
  }
  return {...(state || {}), settled: false};
}

const MEASURE = (configured) => {
  const short = (el) => { if (!el || el.nodeType !== 1) return ""; const cls = typeof el.className === "string" ? el.className.trim().split(/\s+/).filter(Boolean).slice(0, 3).join(".") : "";
    return el.tagName.toLowerCase() + (el.id ? "#" + el.id : "") + (cls ? "." + cls : ""); };
  const doc = document.documentElement, width = configured || window.innerWidth;      // a phone zooms out to fit: innerWidth grows with the overflow
  const overflow = doc.scrollWidth > width || window.innerWidth > width;
  const offenders = [];
  if (overflow) {
    const clipped = (el) => { for (let p = el.parentElement; p && p !== document.body && p !== doc; p = p.parentElement) { const s = getComputedStyle(p);
      if (/(auto|scroll|hidden|clip)/.test(s.overflowX)) return true; if (s.position === "fixed") return false; } return false; };
    const wide = [...document.querySelectorAll("body *")].filter((el) => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0 && r.right > width + 1 && !clipped(el); });
    const set = new Set(wide);
    for (const el of wide) {                                   // the innermost ones: the element that pushes, not its wrappers
      if ([...el.children].some((c) => set.has(c))) continue;
      const r = el.getBoundingClientRect();
      offenders.push(`${short(el.parentElement)} > ${short(el)} (+${Math.round(r.right - width)}px, ancho ${Math.round(r.width)})`);
      if (offenders.length >= 5) break;
    }
  }
  return {hash: location.hash, nodes: document.querySelectorAll("*").length, appNodes: document.querySelectorAll("#app *").length, height: doc.scrollHeight, scrollWidth: Math.max(doc.scrollWidth, window.innerWidth), innerWidth: width,
    styled: document.querySelectorAll("[style]").length, overflow, offenders, text: (document.querySelector("#app") || {innerText: ""}).innerText.length,
    images: document.images.length, appError: (document.querySelector("#app > .notice.bad:only-child") || {}).textContent || ""};
};

async function shoot(page, track, opt, rec, from) {
  // lazy images below the fold would be grey boxes in a full-page shot
  await page.evaluate(async () => { document.querySelectorAll('img[loading="lazy"]').forEach((i) => { i.loading = "eager"; });
    await Promise.race([Promise.all([...document.images].filter((i) => !i.complete).map((i) => new Promise((ok) => { i.onload = i.onerror = ok; }))), new Promise((ok) => setTimeout(ok, 4000))]); });
  await settle(page, track, 3000);
  const size = await page.evaluate(() => ({w: document.documentElement.clientWidth, h: document.documentElement.scrollHeight}));
  rec.shot = `${slugOf(rec.route)}.${rec.viewport}.${rec.scheme}.png`; rec.shotFrom = from;
  await page.screenshot({path: path.join(opt.out, rec.shot), fullPage: true, animations: "disabled", clip: {x: 0, y: 0, width: size.w, height: Math.min(size.h, MAX_SHOT_HEIGHT)}});
}

async function runJob(browser, opt, job) {
  const {route, viewport, scheme} = job;
  const context = await browser.newContext({...VIEWPORTS[viewport], colorScheme: scheme, deviceScaleFactor: 1, locale: "es-ES", timezoneId: "Europe/Madrid"});
  await context.addInitScript(INIT);
  const page = await context.newPage();
  const rec = {route, viewport, scheme, partner: !!opt.partner, consoleErrors: [], pageErrors: [], failedRequests: [], badResponses: [], unmocked: [], denied: []};
  const track = {inflight: new Set(), phase: "carga"};
  const handle = await mock.install(page, {partner: opt.partner, origin: new URL(opt.base).origin});
  const mockedOut = (url) => handle.blocked.includes(url);
  page.on("request", (r) => track.inflight.add(r));
  page.on("requestfinished", (r) => track.inflight.delete(r));
  page.on("requestfailed", (r) => { track.inflight.delete(r); if (!mockedOut(r.url()) && !/\.(mp4|mp3|webm)(\?|#|$)/.test(r.url())) rec.failedRequests.push(`[${track.phase}] ${r.method()} ${r.url().replace(opt.base, "")} · ${(r.failure() || {}).errorText || ""}`); });
  page.on("response", (r) => { if (r.status() >= 400) rec.badResponses.push({phase: track.phase, status: r.status(), url: r.url().replace(opt.base, ""), method: r.request().method()}); });
  page.on("console", (m) => { if (m.type() !== "error") return; const where = (m.location() || {}).url || "";
    if (mockedOut(where)) return;
    rec.consoleErrors.push({phase: track.phase, text: m.text().slice(0, 500), url: where.replace(opt.base, "")}); });
  page.on("pageerror", (e) => rec.pageErrors.push(`[${track.phase}] ${String(e.stack || e.message || e).slice(0, 600)}`));
  try {
    // 1) a cold load of the page itself: what is measured and photographed
    const t0 = Date.now();
    await page.goto(opt.base + "/" + route, {waitUntil: "load"});
    const cold = await settle(page, track);
    rec.loadMs = Date.now() - t0 - (cold.settled ? SETTLE_MS : 0);
    rec.settled = cold.settled;
    Object.assign(rec, await page.evaluate(MEASURE, VIEWPORTS[viewport].viewport.width));
    rec.nav = await page.evaluate(() => [...document.querySelectorAll("header nav a")].map((a) => ({href: a.getAttribute("href"), label: a.textContent.trim()})));
    rec.coldError = rec.appError;
    if (opt.shots && !rec.appError) await shoot(page, track, opt, rec, "carga");
    // 2) the same page reached inside the app: from another page, set the hash and time it until the DOM is still
    track.phase = "navegación";
    const from = route === "#/" ? "#/videos" : "#/";
    await page.goto("about:blank");                             // a real load of the app, not a hash change of the page above
    await page.goto(opt.base + "/" + from, {waitUntil: "load"});
    await settle(page, track);
    const startAt = await page.evaluate((to) => { const t = performance.now(); window.__muts = 0; window.__lastMut = t; location.hash = to; return t; }, route);
    const warm = await settle(page, track);
    const after = await page.evaluate(() => ({last: window.__lastMut, muts: window.__muts, hash: location.hash, nodes: document.querySelectorAll("*").length}));
    rec.paintMs = after.muts ? Math.round(after.last - startAt) : null;
    rec.paintFrom = from; rec.paintSettled = warm.settled; rec.navNodes = after.nodes;
    if (rec.coldError) {            // the page only works when reached from another one (an app bug, reported): measure and shoot that
      Object.assign(rec, await page.evaluate(MEASURE, VIEWPORTS[viewport].viewport.width), {measuredFrom: "navegación"});
      if (opt.shots) await shoot(page, track, opt, rec, "navegación");
    }
  } catch (error) {
    rec.pageErrors.push(`[harness] ${String(error.message || error).slice(0, 400)}`);
  }
  rec.unmocked = handle.unmocked.map((u) => `${u.method} ${u.path}`);
  rec.denied = [...new Set(handle.denied.map((u) => `${u.method} ${u.path}`))];
  rec.blocked = [...new Set(handle.blocked)];
  // a 403 the real server gives a partner is the app's behaviour (reported apart), not a broken mock
  const deniedPaths = new Set(handle.denied.map((u) => u.path));
  const isDenied = (url) => { try { return deniedPaths.has(new URL(url, opt.base).pathname); } catch (e) { return false; } };
  rec.deniedConsole = rec.consoleErrors.filter((e) => isDenied(e.url)).length;
  rec.consoleErrors = rec.consoleErrors.filter((e) => !isDenied(e.url));
  rec.badResponses = rec.badResponses.filter((r) => !isDenied(r.url));
  await context.close();
  return rec;
}

async function partnerChecks(browser, opt) {
  const out = [];
  for (const route of PARTNER_FORBIDDEN) {
    const context = await browser.newContext({...VIEWPORTS.desktop, colorScheme: "dark", deviceScaleFactor: 1, locale: "es-ES"});
    await context.addInitScript(INIT);
    const page = await context.newPage();
    const track = {inflight: new Set()};
    page.on("request", (r) => track.inflight.add(r)); page.on("requestfinished", (r) => track.inflight.delete(r)); page.on("requestfailed", (r) => track.inflight.delete(r));
    await mock.install(page, {partner: true, origin: new URL(opt.base).origin});
    await page.goto(opt.base + "/" + route, {waitUntil: "load"});
    await settle(page, track);
    const got = await page.evaluate(() => ({hash: location.hash || "#/", nav: [...document.querySelectorAll("header nav a")].map((a) => ({href: a.getAttribute("href"), label: a.textContent.trim()}))}));
    const hrefs = got.nav.map((n) => n.href);
    out.push({check: `partner ${route} → #/`, ok: got.hash === "#/", got: got.hash});
    if (route === PARTNER_FORBIDDEN[0]) out.push({check: "partner nav = el conjunto del socio", ok: hrefs.length === PARTNER_NAV.length && PARTNER_NAV.every((h) => hrefs.includes(h)),
      got: hrefs.join(" "), expected: PARTNER_NAV.join(" "), nav: got.nav});
    await context.close();
  }
  return out;
}

(async () => {
  const opt = args();
  fs.mkdirSync(opt.out, {recursive: true});
  const routes = opt.routes || (opt.partner ? PARTNER_ROUTES : OWNER_ROUTES);
  const jobs = [];
  for (const route of routes) for (const viewport of Object.keys(VIEWPORTS)) for (const scheme of SCHEMES)
    if (!opt.only || opt.only === `${viewport}-${scheme}`) jobs.push({route, viewport, scheme});
  const browser = await chromium.launch();
  const started = Date.now(), results = new Array(jobs.length);
  let next = 0;
  await Promise.all(Array.from({length: Math.min(opt.jobs, jobs.length)}, async () => {
    while (next < jobs.length) { const i = next++; results[i] = await runJob(browser, opt, jobs[i]); process.stderr.write("."); }
  }));
  const checks = opt.partner ? await partnerChecks(browser, opt) : [];
  await browser.close();
  process.stderr.write("\n");
  const file = path.join(opt.out, "metrics.json");
  fs.writeFileSync(file, JSON.stringify(results, null, 1));
  if (checks.length) fs.writeFileSync(path.join(opt.out, "partner-checks.json"), JSON.stringify(checks, null, 1));

  const pad = (t, n) => String(t ?? "—").padEnd(n).slice(0, n), num = (t, n) => String(t ?? "—").padStart(n);
  console.log(`${pad("ruta", 30)} ${pad("vista", 13)} ${num("nodos", 6)} ${num("alto", 6)} ${num("style=", 6)} ${num("carga", 6)} ${num("pinta", 6)}  err  desb`);
  for (const r of results) console.log(`${pad(r.route, 30)} ${pad(r.viewport + "-" + r.scheme, 13)} ${num(r.nodes, 6)} ${num(r.height, 6)} ${num(r.styled, 6)} ${num(r.loadMs, 6)} ${num(r.paintMs, 6)}  ${num(r.consoleErrors.length + r.pageErrors.length, 3)}  ${r.overflow ? "SÍ " + (r.scrollWidth - r.innerWidth) + "px" : "no"}${r.settled === false ? "  (no se asentó)" : ""}`);

  const problems = [], findings = [], painted = [];
  for (const r of results) {
    const where = `${r.route} [${r.viewport}-${r.scheme}]`;
    for (const e of r.consoleErrors) problems.push(`consola   ${where} (${e.phase}): ${e.text}${e.url ? " · " + e.url : ""}`);
    for (const e of r.pageErrors) problems.push(`pageerror ${where}: ${e}`);
    if (r.overflow) problems.push(`desborde  ${where}: scrollWidth ${r.scrollWidth} > ${r.innerWidth} · ${r.offenders.join(" | ") || "(sin culpable claro)"}`);
    if (r.coldError) painted.push(`${where} al cargarla directamente: «${r.coldError.slice(0, 200)}»${r.appError ? "" : " (llegando desde otra página sí pinta: se midió y fotografió así)"}`);
    else if (r.appError) painted.push(`${where}: «${r.appError.slice(0, 200)}»`);
    if (opt.partner && r.hash !== r.route) problems.push(`ruta      ${where}: acabó en ${r.hash}`);
    for (const f of r.failedRequests) findings.push(`petición fallida ${where}: ${f}`);
    for (const f of r.badResponses) findings.push(`respuesta ${f.status} ${where} (${f.phase}): ${f.method} ${f.url}`);
    for (const u of r.unmocked) findings.push(`SIN MOCK ${where}: ${u}`);
  }
  for (const c of checks) if (!c.ok) problems.push(`socio     ${c.check}: obtuvo ${c.got}${c.expected ? " · esperaba " + c.expected : ""}`);
  const uniq = (list) => [...new Set(list)];
  const denied = uniq(results.flatMap((r) => r.denied.map((d) => `${d} (en ${r.route})`)));
  console.log(`\n${results.length} páginas en ${((Date.now() - started) / 1000).toFixed(1)} s · métricas en ${file}`);
  if (checks.length) console.log("Comprobaciones del socio:\n" + checks.map((c) => `  ${c.ok ? "✓" : "✗"} ${c.check}${c.ok ? "" : " → " + c.got}`).join("\n"));
  if (denied.length) console.log(`\n403 que el servidor real da al socio (comportamiento de la app, no del mock):\n  ${denied.join("\n  ")}`);
  console.log(`\nSin mock (/api no modelado): ${uniq(mock.unmocked.map((u) => `${u.method} ${u.path}`)).join(", ") || "ninguno"}`);
  if (painted.length) console.log("\nErrores que pinta la propia app (no cuentan para el código de salida):\n  " + painted.join("\n  "));
  if (uniq(findings).length) console.log("\nOtros hallazgos:\n  " + uniq(findings).join("\n  "));
  console.log(problems.length ? `\nPROBLEMAS (${problems.length}):\n  ` + problems.join("\n  ") : "\nSin errores de consola ni desbordes.");
  process.exit(problems.length ? 1 : 0);
})().catch((error) => { console.error(error); process.exit(2); });
