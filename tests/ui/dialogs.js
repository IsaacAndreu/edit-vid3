const { chromium } = require('playwright'); const mock = require('./mock.js');
const BASE = process.argv[2] || 'http://127.0.0.1:8099';
(async () => {
  const b = await chromium.launch(); const errs = []; let natives = 0;
  const p = await b.newPage({viewport: {width: 1440, height: 900}}); p.on('pageerror', (e) => errs.push(e.message)); p.on('dialog', (d) => { natives++; d.dismiss(); });
  await mock.install(p, {});
  const act = () => p.evaluate(() => { const a = document.activeElement; return a ? (a.tagName + (a.id ? '#' + a.id : '') + ' ' + (a.textContent || a.value || '').trim().slice(0, 30)) : '-'; });
  // 1. prompt → askText on «Ya está subido»
  await p.goto('http://127.0.0.1:8099/#/video/citroen-ds'); await p.waitForTimeout(1000);
  await p.click('.more > button'); const item = p.locator('.more button', {hasText: 'Ya está subido'}); await item.focus(); await p.keyboard.press('Enter'); await p.waitForTimeout(200);
  console.log('askText open:', await p.locator('dialog[open]').count(), '| focus:', await act());
  for (let i = 0; i < 5; i++) await p.keyboard.press('Tab');
  console.log('after 5×Tab focus inside dialog:', await p.evaluate(() => !!document.activeElement.closest('dialog')));
  await p.keyboard.press('Escape'); await p.waitForTimeout(200);
  console.log('Esc closed:', await p.locator('dialog').count() === 0, '| focus back on:', await act());
  // 2. confirm → ask (danger) on «Quitar de la lista» path: use restartQueue on Ajustes
  await p.goto('http://127.0.0.1:8099/#/ajustes'); await p.waitForTimeout(1000);
  const btn = p.locator('button', {hasText: 'Reiniciar la cola'}); await btn.click(); await p.waitForTimeout(200);
  console.log('ask text:', (await p.locator('dialog p').innerText()).slice(0, 40), '| focus:', await act());
  await p.keyboard.press('Enter'); await p.waitForTimeout(500);
  console.log('toast after yes:', await p.locator('#toasts .toast').count(), (await p.locator('#toasts').innerText()).slice(0, 60).replace(/\n/g, ' '), '| focus:', await act());
  // 3. error toast
  await p.route('**/api/settings', (r) => r.request().method() === 'POST' ? r.fulfill({status: 500, json: {error: 'Fallo de prueba'}}) : r.fallback());
  await p.locator('.setting button', {hasText: 'Guardar'}).first().click(); await p.waitForTimeout(400);
  console.log('error shown:', (await p.locator('#toasts').innerText()).replace(/\n/g, ' ').slice(0, 120));
  // 4. ideas sheet on Radar: Esc closes
  await p.goto('http://127.0.0.1:8099/#/competencia'); await p.waitForTimeout(1200);
  const ideas = p.locator('button', {hasText: 'Ideas'}).first(); await ideas.click(); await p.waitForTimeout(800);
  console.log('ideas sheet open:', await p.locator('dialog#modal[open]').count()); await p.screenshot({path: require('os').tmpdir() + '/sheet.png'});
  await p.keyboard.press('Escape'); await p.waitForTimeout(500);
  console.log('ideas Esc closed:', await p.locator('dialog#modal').count() === 0, '| still on radar:', await p.locator('#app h1').first().innerText());
  console.log('native dialogs fired:', natives, 'errors:', errs); await b.close();
})();
