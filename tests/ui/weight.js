#!/usr/bin/env node
// What the app weighs on the wire: the document and every static file (everything that is not /api), on a first
// load and on a reload with the browser's cache on.
//   node weight.js --base http://127.0.0.1:8099 [--route "#/"] [--partner]
// /api is answered by the mock through CDP Fetch (page.route would switch the HTTP cache off).
"use strict";

const zlib = require("zlib");
const {chromium} = require("playwright");
const mock = require("./mock");

const a = process.argv.slice(2), opt = {base: "http://127.0.0.1:8099", route: "#/"};
for (let i = 0; i < a.length; i++) {
  if (a[i] === "--base") opt.base = a[++i].replace(/\/$/, "");
  else if (a[i] === "--route") opt.route = a[++i];
  else if (a[i] === "--partner") opt.partner = true;
}

(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext({viewport: {width: 1440, height: 900}, colorScheme: "dark", locale: "es-ES"});
  const page = await context.newPage();
  const cdp = await context.newCDPSession(page);
  const state = mock.freshState(), who = opt.partner ? mock.SLUGS.partner : "";
  const origin = new URL(opt.base).origin;
  await cdp.send("Network.enable");
  await cdp.send("Fetch.enable", {patterns: [{urlPattern: origin + "/api/*"}, {urlPattern: origin + "/files/*"}]});
  cdp.on("Fetch.requestPaused", async (e) => {
    let body = null;
    try { body = e.request.postData ? JSON.parse(e.request.postData) : null; } catch (error) { body = {}; }
    const found = mock.answer(state, e.request.method, e.request.url, body, who) || {status: 404, contentType: "text/plain", body: ""};
    await cdp.send("Fetch.fulfillRequest", {requestId: e.requestId, responseCode: found.status === 204 ? 200 : found.status,
      responseHeaders: [{name: "Content-Type", value: found.contentType}], body: Buffer.from(found.body, "utf8").toString("base64")}).catch(() => {});
  });

  let phase = "first", last = Date.now();
  const requests = new Map(), rows = {first: [], repeat: []};
  cdp.on("Network.requestWillBeSent", (e) => { last = Date.now(); requests.set(e.requestId, {phase, url: e.request.url, type: e.type, acceptEncoding: null}); });
  cdp.on("Network.requestWillBeSentExtraInfo", (e) => { const r = requests.get(e.requestId); const h = e.headers || {};
    const value = h["Accept-Encoding"] || h["accept-encoding"]; if (r && value) r.acceptEncoding = value; else if (value) pendingAE.set(e.requestId, value); });
  const pendingAE = new Map();
  cdp.on("Network.requestServedFromCache", (e) => { const r = requests.get(e.requestId); if (r) r.memoryCache = true; });
  cdp.on("Network.responseReceived", (e) => { last = Date.now(); const r = requests.get(e.requestId); if (!r) return;
    const h = Object.fromEntries(Object.entries(e.response.headers).map(([k, v]) => [k.toLowerCase(), v]));
    Object.assign(r, {status: e.response.status, mime: e.response.mimeType, fromDiskCache: !!e.response.fromDiskCache, protocol: e.response.protocol,
      cacheControl: h["cache-control"] || null, etag: h["etag"] || null, lastModified: h["last-modified"] || null, contentEncoding: h["content-encoding"] || null,
      contentLength: h["content-length"] ? +h["content-length"] : null, vary: h["vary"] || null}); });
  cdp.on("Network.responseReceivedExtraInfo", (e) => { const r = requests.get(e.requestId); if (r) r.wireStatus = e.statusCode; });     // 304 on a revalidation
  const done = [];
  cdp.on("Network.loadingFinished", (e) => { last = Date.now(); const r = requests.get(e.requestId); if (!r) return; r.transfer = e.encodedDataLength;
    done.push(cdp.send("Network.getResponseBody", {requestId: e.requestId}).then((b) => { const buf = Buffer.from(b.body, b.base64Encoded ? "base64" : "utf8");
      r.bytes = buf.length; r.gzip = zlib.gzipSync(buf, {level: 6}).length; }).catch(() => {})); });
  cdp.on("Network.loadingFailed", (e) => { const r = requests.get(e.requestId); if (r) r.failed = e.errorText; });
  const idle = async () => { for (;;) { await page.waitForTimeout(150); if (Date.now() - last > 1200) break; } await Promise.all(done.splice(0)); };

  await page.goto(opt.base + "/" + opt.route, {waitUntil: "load"}); await idle();
  phase = "repeat";
  await page.reload({waitUntil: "load"}); await idle();
  await browser.close();

  const isStatic = (r) => { const u = new URL(r.url); return u.origin === origin && !u.pathname.startsWith("/api/") && !u.pathname.startsWith("/files/"); };
  for (const [id, r] of requests) { if (!r.acceptEncoding && pendingAE.has(id)) r.acceptEncoding = pendingAE.get(id); if (/^https?:/.test(r.url) && isStatic(r)) rows[r.phase].push(r); }
  const key = (r) => new URL(r.url).pathname;
  const assets = rows.first.map((f) => { const again = rows.repeat.find((x) => key(x) === key(f));
    // what a gzip-serving server would send: the gzip body the first time; a reload costs a 304 (headers only) if it
    // can be revalidated, nothing if it is fresh in the cache, the whole gzip body if it cannot be cached at all
    const cacheable = !!(f.etag || f.lastModified || /max-age=[1-9]|immutable/.test(f.cacheControl || "")) && !/no-store/.test(f.cacheControl || "");
    return {path: key(f), type: f.type, status: f.status, bytes: f.bytes ?? null, gzip: f.gzip ?? null, firstTransfer: f.transfer ?? null,
      repeatStatus: again ? (again.wireStatus || again.status) : null, repeatTransfer: again ? (again.memoryCache || again.fromDiskCache ? 0 : again.transfer ?? null) : 0,
      repeatFrom: !again ? "no se pidió (caché en memoria)" : again.fromDiskCache || again.memoryCache ? "caché" : (again.wireStatus || again.status) === 304 ? "304" : "red",
      cacheControl: f.cacheControl, etag: f.etag, lastModified: f.lastModified, contentEncoding: f.contentEncoding, vary: f.vary, acceptEncodingSent: f.acceptEncoding, cacheable}; });
  const sum = (k) => assets.reduce((n, x) => n + (x[k] || 0), 0);
  const HEADERS_304 = 250;
  const totals = {assets: assets.length, uncompressedBytes: sum("bytes"), firstLoadTransfer: sum("firstTransfer"), repeatLoadTransfer: sum("repeatTransfer"),
    firstLoadIfGzip: assets.reduce((n, x) => n + (x.contentEncoding ? x.firstTransfer : (x.gzip || 0) + HEADERS_304), 0),
    repeatLoadIfGzip: assets.reduce((n, x) => n + (x.cacheable ? (x.repeatFrom === "caché" || /^no se/.test(x.repeatFrom) ? 0 : HEADERS_304) : (x.gzip || 0) + HEADERS_304), 0),
    repeatLoadIfGzipAsServedNow: assets.reduce((n, x) => n + (x.repeatFrom === "red" ? (x.contentEncoding ? x.repeatTransfer : (x.gzip || 0) + HEADERS_304) : x.repeatTransfer), 0)};
  const kb = (n) => n == null ? "—" : (n / 1024).toFixed(1) + " KB";
  console.log(`${"archivo".padEnd(34)} ${"estado".padEnd(7)} ${"sin comprimir".padStart(13)} ${"gzip".padStart(10)} ${"1ª carga".padStart(10)} ${"recarga".padStart(10)}  de`);
  for (const x of assets) console.log(`${x.path.padEnd(34).slice(0, 34)} ${String(x.status).padEnd(7)} ${kb(x.bytes).padStart(13)} ${kb(x.gzip).padStart(10)} ${kb(x.firstTransfer).padStart(10)} ${kb(x.repeatTransfer).padStart(10)}  ${x.repeatFrom}${x.repeatStatus ? " (" + x.repeatStatus + ")" : ""}`);
  console.log("\nCabeceras:");
  for (const x of assets) console.log(`  ${x.path}: Cache-Control: ${x.cacheControl || "—"} · ETag: ${x.etag || "—"} · Last-Modified: ${x.lastModified || "—"} · Content-Encoding: ${x.contentEncoding || "—"} · Vary: ${x.vary || "—"} · (enviado Accept-Encoding: ${x.acceptEncodingSent || "?"})`);
  console.log(`\nPrimera carga: ${kb(totals.firstLoadTransfer)} medidos · ${kb(totals.firstLoadIfGzip)} si fuera con gzip`);
  console.log(`Recarga:       ${kb(totals.repeatLoadTransfer)} medidos · ${kb(totals.repeatLoadIfGzip)} si fuera con gzip y revalidación (ETag/304 o caché)\n`);
  console.log(JSON.stringify({base: opt.base, route: opt.route, totals, assets}, null, 1));
})().catch((error) => { console.error(error); process.exit(2); });
