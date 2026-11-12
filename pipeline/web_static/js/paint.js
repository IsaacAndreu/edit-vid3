// Painting without replacing: paint(el, html) patches what is on screen so that it matches `html`.
// - the same html as last time → the DOM is not touched at all (automatic refreshes cost nothing);
// - otherwise only the nodes that differ change: the scroll, the focus, what is being typed, the <details> the user
//   opened and the boxes filled later (paint(box, …) by a second request) stay as they are.
// `quiet` is true while a page refreshes itself on its timer and nobody has touched anything since: then ticks and
// selects keep what the user left in them too; after a click or a key they show again what the page says.
let quiet = false;
for (const kind of ["pointerdown", "keydown", "change"]) document.addEventListener(kind, () => { quiet = false; }, true);

function paint(root, html, fresh = false) {
  if (!root) return;
  html = String(html);
  if (!fresh && root._html === html) return;
  const first = root._html === undefined && !root.firstChild;
  root._html = html;
  if (fresh || first) { root.innerHTML = html; remember(root); return; }
  const next = document.createElement("template");
  next.innerHTML = html;
  const active = document.activeElement, inside = active && root.contains(active) && active !== document.body;
  const caret = inside && typeof active.selectionStart === "number" ? [active.selectionStart, active.selectionEnd] : null;
  patchChildren(root, next.content);
  if (!quiet) {                 // after a click or a key: every tick and every choice shows what the page says
    for (const c of root.querySelectorAll("input[type=checkbox], input[type=radio]")) if (c.checked !== c.defaultChecked) c.checked = c.defaultChecked;
    for (const c of root.querySelectorAll("select")) {
      const want = Math.max(0, [...c.options].findIndex((o) => o.defaultSelected));
      if (c !== active && !c.multiple && c.selectedIndex !== want) c.selectedIndex = want;
    }
  }
  if (inside && document.activeElement !== active) {             // moved or replaced: the focus goes back to it
    const again = active.isConnected ? active : active.id && document.getElementById(active.id);
    if (again) { again.focus({preventScroll: true}); if (caret) try { again.setSelectionRange(...caret); } catch (e) {} }
  }
}

// what the page said about each <details>: only a change in that (not the user's click) opens or closes it later
function remember(node) {
  if (node.nodeType !== 1 && node.nodeType !== 11) return;
  if (node.nodeName === "DETAILS") node._open = node.hasAttribute("open");
  for (const d of node.querySelectorAll("details")) d._open = d.hasAttribute("open");
}

const sameNode = (a, b) => a.nodeType === b.nodeType && a.nodeName === b.nodeName
  && (a.nodeType !== 1 || ((a.id || "") === (b.id || "") && a.getAttribute("type") === b.getAttribute("type")));

function patchChildren(parent, next) {
  let old = parent.firstChild;
  for (let node = next.firstChild; node;) {
    const following = node.nextSibling;
    let match = old;
    if (node.nodeType === 1 && node.id && !(old && old.id === node.id)) {        // an element with an id is found wherever it is
      match = null;
      for (let c = old; c; c = c.nextSibling) if (c.id === node.id) { match = c; break; }
    }
    if (match && sameNode(match, node)) {
      if (match === old) old = old.nextSibling; else parent.insertBefore(match, old);
      patch(match, node);
    } else { remember(node); parent.insertBefore(node, old); }
    node = following;
  }
  while (old) { const gone = old; old = old.nextSibling; gone.remove(); }
}

function patch(el, next) {
  if (el.nodeType !== 1) { if (el.nodeValue !== next.nodeValue) el.nodeValue = next.nodeValue; return; }
  const name = el.nodeName, focused = el === document.activeElement;
  if (name === "DETAILS") {                                    // the user's open/closed wins until the page changes its mind
    const want = next.hasAttribute("open");
    if (el._open !== undefined && el._open !== want) el.open = want;
    el._open = want;
    el.open ? next.setAttribute("open", "") : next.removeAttribute("open");
  }
  const text = name === "TEXTAREA" || (name === "INPUT" && !/^(checkbox|radio|file|button|submit)$/.test(el.type));
  const said = text ? el.defaultValue : name === "INPUT" ? el.defaultChecked : name === "OPTION" ? el.defaultSelected : null;   // what the page said last time
  if (!el.isEqualNode(next)) {
    for (const a of [...el.attributes]) if (!next.hasAttribute(a.name)) el.removeAttribute(a.name);
    for (const a of next.attributes) if (el.getAttribute(a.name) !== a.value) el.setAttribute(a.name, a.value);
    if (el._kept && !next.firstChild) { /* a box painted on its own (fill(box, …)): the page leaves it alone */ }
    else if (name === "TEXTAREA") el.defaultValue = next.defaultValue;
    else patchChildren(el, next);
  }
  // what is being typed is never lost: a text takes the page's value only when the page changed it (or nobody typed)
  if (text) {
    if (!focused && (next.defaultValue !== said || el.value === said) && el.value !== next.defaultValue) el.value = next.defaultValue;
  } else if (name === "INPUT" && next.defaultChecked !== said) el.checked = next.defaultChecked;
  else if (name === "OPTION" && next.defaultSelected !== said) el.selected = next.defaultSelected;
}

// the page itself: another route starts clean and at the top; the same route is patched in place
function show(html) {
  const app = $("#app"), hash = location.hash || "#/", moved = app._hash !== hash;
  app._hash = hash;
  paint(app, html, moved);
  if (moved) window.scrollTo(0, 0);
}

// a box of the page that a later request fills (the doctor card, the repetition report…): painted with the same
// care, and kept when the page around it is painted again
function fill(box, html) { if (box) { box._kept = true; paint(box, html); } }
