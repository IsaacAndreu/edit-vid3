const { chromium } = require('playwright'); const mock = require('./mock.js');
const BASE = process.argv[2] || 'http://127.0.0.1:8099';
const ROUTES = ['#/', '#/nuevo', '#/subir', '#/videos', '#/guiones', '#/calendario', '#/tablero', '#/competencia', '#/canal', '#/estadisticas', '#/experimentos', '#/piloto', '#/biblioteca', '#/biblioteca/niki-lauda', '#/errores', '#/gasto', '#/servidor', '#/ajustes', '#/voces', '#/canal-nuevo', '#/buscar/dingos', '#/video/delorean', '#/video/pegaso-z102', '#/video/saab-quiebra', '#/video/citroen-ds', '#/video/lancia-stratos', '#/revisar/citroen-ds', '#/decisiones/citroen-ds'];
(async () => {
  const b = await chromium.launch(); const all = {};
  await Promise.all([0, 1, 2, 3].map(async (w) => {
    const p = await b.newPage({viewport: {width: 1440, height: 900}}); await mock.install(p, {});
    for (let i = w; i < ROUTES.length; i += 4) {
      const r = ROUTES[i]; await p.goto(BASE + '/' + r); await p.waitForTimeout(900);
      all[r] = await p.evaluate(() => {
        const name = (el) => (el.getAttribute('aria-label') || el.getAttribute('aria-labelledby') && 'x' || el.title || el.textContent || '').trim() || (el.querySelector('img[alt]:not([alt=""])') ? 'img' : '');
        const sel = (el) => el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + (el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.') : '') + ' «' + (el.outerHTML.slice(0, 90)) + '»';
        const out = [];
        for (const el of document.querySelectorAll('#app button, #app a[href], header button')) if (!name(el)) out.push('no name: ' + sel(el));
        for (const el of document.querySelectorAll('#app input:not([type=hidden]), #app select, #app textarea')) {
          const ok = el.labels && el.labels.length || el.getAttribute('aria-label') || el.getAttribute('aria-labelledby') || el.title;
          if (!ok) out.push('no label: ' + sel(el) + (el.placeholder ? ' ph=' + el.placeholder.slice(0, 30) : ''));
        }
        for (const el of document.querySelectorAll('#app img:not([alt])')) out.push('img no alt: ' + sel(el));
        for (const el of document.querySelectorAll('#app [onclick]')) {
          const t = el.tagName; if (/^(BUTTON|A|INPUT|SELECT|TEXTAREA|SUMMARY|LABEL)$/.test(t) || el.hasAttribute('tabindex') || el.closest('button, a')) continue;
          out.push('click no kbd: ' + sel(el));
        }
        return [...new Set(out)];
      });
    }
    await p.close();
  }));
  let n = 0; for (const r of ROUTES) if (all[r].length) { console.log('== ' + r); all[r].slice(0, 12).forEach((x) => console.log('  ' + x)); if (all[r].length > 12) console.log('  … +' + (all[r].length - 12)); n += all[r].length; }
  console.log('total', n); await b.close();
})();
