const { chromium } = require('playwright'); const mock = require('./mock.js');
const BASE = process.argv[2] || 'http://127.0.0.1:8099';
(async () => {
  const b = await chromium.launch(); const ctx = await b.newContext(); const p = await ctx.newPage(); const errs = [];
  p.on('pageerror', (e) => errs.push(e.message));
  await mock.install(p, {});
  const go = async (h) => { await p.evaluate((h) => { location.hash = h; }, h); await p.waitForTimeout(700); };
  await p.goto(BASE + '/#/'); await p.waitForTimeout(900);
  // (a) a refresh with the same data must not touch the DOM
  const out = {};
  for (const r of ['#/', '#/calendario', '#/videos', '#/subir', '#/servidor', '#/video/citroen-ds', '#/estadisticas', '#/ajustes', '#/gasto', '#/competencia']) {
    await go(r);
    await p.evaluate(() => { window.muts = 0; window.mo = new MutationObserver((m) => window.muts += m.length); window.mo.observe(document.getElementById('app'), {subtree: true, childList: true, attributes: true, characterData: true}); window.scrollTo(0, 300); });
    await p.evaluate(async () => { apiCache.clear(); quiet = true; await route(); }); await p.waitForTimeout(500);
    out[r] = await p.evaluate(() => { window.mo.disconnect(); return window.muts + ' muts, scrollY ' + window.scrollY; });
  }
  console.log('refresh same data:', JSON.stringify(out, null, 1));
  // (b) Home → Ajustes → Home with unchanged data shows Home
  await go('#/'); await go('#/ajustes'); await go('#/');
  console.log('back home h1/first:', (await p.locator('#app').innerText()).slice(0, 30).replace(/\n/g, ' | '));
  // (c) a slow answer of the old page must not paint over the new one
  await p.route('**/api/servidor', async (route) => { await new Promise((r) => setTimeout(r, 1500)); route.fulfill({json: {}}); });
  await p.evaluate(() => { apiCache.clear(); location.hash = '#/servidor'; }); await p.waitForTimeout(200);
  await p.evaluate(() => { location.hash = '#/nuevo'; }); await p.waitForTimeout(2200);
  console.log('after slow nav shows:', await p.locator('#app h1').first().innerText());
  // (d) typing survives a refresh whose data changed; focus and caret too
  await go('#/videos');
  await p.fill('#app input[type=search]', 'air'); await p.waitForTimeout(600);
  console.log('search keeps focus:', await p.evaluate(() => document.activeElement && document.activeElement.type), await p.locator('#app input[type=search]').inputValue());
  await go('#/video/citroen-ds');
  const ta = p.locator('#app textarea').first(); await ta.fill('borrador mío');
  const det = p.locator('#app details:not([open])').first(); const hasDet = await det.count(); if (hasDet) await det.locator('summary').click();
  await p.evaluate(async () => { apiCache.clear(); quiet = true; document.querySelector('#app h1').firstChild.textContent = 'cambiado '; $("#app")._html = ''; await route(); }); await p.waitForTimeout(600);
  console.log('draft kept:', await ta.inputValue(), '| details stays open:', hasDet ? await p.evaluate(() => [...document.querySelectorAll('#app details')].filter((d) => d.open).length) : 'n/a', '| h1 repaired:', (await p.locator('#app h1').innerText()).slice(0, 20));
  console.log('pageerrors', errs); await b.close();
})();
