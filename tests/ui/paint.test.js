const { chromium } = require('playwright'); const path = require('path'); const assert = require('assert');
(async () => {
  const b = await chromium.launch(); const p = await b.newPage(); p.on('pageerror', e => { console.log('PAGEERROR', e.message); process.exitCode = 1; });
  // paint.js of the studio itself, on an empty page
  await p.setContent('<!doctype html><meta charset="utf-8"><div id="app"></div>');
  await p.addScriptTag({path: path.join(__dirname, '..', '..', 'pipeline', 'web_static', 'js', 'paint.js')});
  const ev = (f, ...a) => p.evaluate(f, ...a);
  const page = (o = {}) => `<h1>T ${o.t || 1}</h1><input id="a" value="${o.a || "x"}"><input class="noid" value="k"><textarea id="ta">${o.ta || "hola"}</textarea>
    <label><input type="checkbox" id="c" ${o.c ? "checked" : ""}> c</label><select id="s"><option value="">Poner…</option><option value="1" ${o.s ? "selected" : ""}>uno</option><option value="2">dos</option></select>
    <details id="d" ${o.d ? "open" : ""}><summary>s</summary><p>in</p></details><div id="box"></div><ul>${(o.list || [1, 2, 3]).map((x) => `<li id="li${x}" tabindex="0">item ${x}</li>`).join("")}</ul><p class="tail">${o.tail || "end"}</p>`;
  await ev((h) => paint(document.getElementById('app'), h), page());
  // 1. same html → no mutation at all
  await ev(() => { window.muts = 0; new MutationObserver((m) => window.muts += m.length).observe(document.getElementById('app'), {subtree: true, childList: true, attributes: true, characterData: true}); });
  await ev((h) => paint(document.getElementById('app'), h), page()); await p.waitForTimeout(20);
  assert.equal(await ev(() => window.muts), 0, 'same html must not touch the DOM');
  // 2. typing + focus + details + checkbox survive a quiet refresh with other data changed; only the changed text node mutates
  await p.focus('#a'); await p.keyboard.type('YZ'); await p.click('#d summary'); await p.fill('#ta', 'draft'); await p.focus('#a');
  await ev(() => { document.getElementById('a').setSelectionRange(1, 2); document.getElementById('c').checked = true; document.getElementById('s').value = "2"; window.muts = 0; quiet = true; window.keep = document.getElementById('a'); });
  await ev((h) => paint(document.getElementById('app'), h), page({t: 2, tail: 'fin'})); await p.waitForTimeout(20);
  const st = await ev(() => ({a: a.value, same: window.keep === document.getElementById('a'), act: document.activeElement.id, sel: [a.selectionStart, a.selectionEnd], ta: ta.value, d: d.open, c: c.checked, s: s.value, h1: document.querySelector('h1').textContent, tail: document.querySelector('.tail').textContent, muts: window.muts}));
  assert.deepEqual(st, {a: 'YZx', same: true, act: 'a', sel: [1, 2], ta: 'draft', d: true, c: true, s: '2', h1: 'T 2', tail: 'fin', muts: 2});
  // 3. loud paint (after a user action): ticks and selects follow the page; text drafts and details stay
  await ev(() => { quiet = false; }); await ev((h) => paint(document.getElementById('app'), h), page({t: 3}));
  assert.deepEqual(await ev(() => ({a: a.value, ta: ta.value, d: d.open, c: c.checked, s: s.value})), {a: 'YZx', ta: 'draft', d: true, c: false, s: ''});
  // 4. the page changes its mind: new value (not focused), details closed→open→closed, selected option
  await p.focus('#ta');
  await ev((h) => paint(document.getElementById('app'), h), page({t: 4, a: 'server', d: 1, s: 1, c: 1}));
  assert.deepEqual(await ev(() => ({a: a.value, d: d.open, c: c.checked, s: s.value, ta: ta.value})), {a: 'server', d: true, c: true, s: '1', ta: 'draft'});
  await ev((h) => paint(document.getElementById('app'), h), page({t: 5, a: 'server', ta: 'nuevo'}));
  assert.deepEqual(await ev(() => ({d: d.open, ta: ta.value, c: c.checked})), {d: false, ta: 'draft', c: false});   // textarea focused: kept
  // 5. boxes filled later are kept; keyed list reorder keeps nodes
  await ev(() => { fill(document.getElementById('box'), '<b>report</b>'); window.li3 = document.getElementById('li3'); li3.focus(); });
  await ev((h) => paint(document.getElementById('app'), h), page({t: 6, a: 'server', ta: 'nuevo', list: [3, 1, 4]}));
  assert.deepEqual(await ev(() => ({box: box.innerHTML, li: [...document.querySelectorAll('li')].map((l) => l.id).join(), same: window.li3 === document.getElementById('li3'), act: document.activeElement.id})), {box: '<b>report</b>', li: 'li3,li1,li4', same: true, act: 'li3'});
  await ev(() => fill(document.getElementById('box'), '<b>report 2</b>')); assert.equal(await ev(() => box.innerHTML), '<b>report 2</b>');
  // 6. fresh paint replaces everything
  await ev((h) => paint(document.getElementById('app'), h, true), page());
  assert.deepEqual(await ev(() => ({a: a.value, box: box.innerHTML, ta: ta.value})), {a: 'x', box: '', ta: 'hola'});
  // 7. tables and nested structures
  const tbl = (n) => `<table><thead><tr><th>a</th></tr></thead><tbody>${Array.from({length: n}, (_, i) => `<tr><td>${i}</td><td><select onchange="1"><option>a</option><option ${i % 2 ? "selected" : ""}>b</option></select></td></tr>`).join("")}</tbody></table>`;
  await ev((h) => paint(document.getElementById('app'), h, true), tbl(3)); await ev((h) => paint(document.getElementById('app'), h), tbl(5));
  assert.equal(await ev(() => document.querySelectorAll('#app tbody tr').length), 5);
  await ev((h) => paint(document.getElementById('app'), h), tbl(2)); assert.ok(await ev((h) => { const t = document.createElement('div'); t.innerHTML = h; return t.innerHTML === document.getElementById('app').innerHTML; }, tbl(2)));
  console.log('paint.js OK'); await b.close();
})().catch((e) => { console.error(e.message); process.exit(1); });
