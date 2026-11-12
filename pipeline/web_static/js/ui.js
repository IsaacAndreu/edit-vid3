// Messages and questions in the page's own style. Never alert/confirm/prompt: some browsers and apps silence them
// (and then a button did nothing at all), and they cannot be styled or read well on a phone.
// - toast(text, "ok" | "bad" | ""): a note in a corner that goes away on its own (an error stays longer);
// - await ask(text, {ok, danger}) → true / false;   await askText(text, value, {ok, options}) → the text, or null.
// The questions are <dialog>s opened with showModal(): Esc closes, the focus stays inside and goes back where it was.
function toast(text, kind = "") {
  if (!text) return;
  const box = $("#toasts"), host = document.querySelector("dialog[open]") || document.body;
  if (box.parentNode !== host) host.appendChild(box);          // above an open dialog too
  const note = document.createElement("div");
  note.className = "toast " + kind;
  note.setAttribute("role", kind === "bad" ? "alert" : "status");
  note.innerHTML = `${icon(kind === "bad" ? "alert" : kind === "ok" ? "check" : "info")}<span></span><button class="icon ghost sm" type="button" aria-label="Cerrar aviso">${icon("x")}</button>`;
  note.children[1].textContent = text;
  let timer = 0;
  const close = () => { clearTimeout(timer); note.remove(); };
  const wait = (ms) => { clearTimeout(timer); timer = setTimeout(close, ms); };
  note.lastChild.onclick = close;
  note.onmouseenter = note.onfocusin = () => clearTimeout(timer);
  note.onmouseleave = note.onfocusout = () => wait(2500);
  box.appendChild(note);
  while (box.children.length > 4) box.firstChild.remove();
  wait(kind === "bad" ? 10000 : Math.min(10000, 3500 + 45 * String(text).length));
}
const oops = (error) => { if (error && error.message !== "login") toast(error.message || String(error), "bad"); };
// an action that forgot its own catch: the error is shown instead of being lost in the console
window.addEventListener("unhandledrejection", (e) => { if (e.reason && e.reason.name !== "AbortError") { oops(e.reason); e.preventDefault(); } });
// a button that was disabled while it worked (and so lost the focus) gets it back when it is done
function busy(button, on) {
  if (!button) return;
  if (on) { button._hadFocus = document.activeElement === button || document.activeElement === document.body; button.disabled = true; }
  else { button.disabled = false; if (button._hadFocus && document.activeElement === document.body && button.isConnected) button.focus(); }
}

function dialog({text, title = "", value = null, placeholder = "", options = [], ok = "Aceptar", cancel = "Cancelar", danger = false}) {
  return new Promise((resolve) => {
    const d = document.createElement("dialog");
    d.className = "dialog";
    d.setAttribute("aria-labelledby", "dlg-text");
    d.innerHTML = `<form method="dialog">${title ? "<h3></h3>" : ""}<p id="dlg-text"></p>
      ${value === null ? "" : `<input id="dlg-input" aria-labelledby="dlg-text" autocomplete="off" ${options.length ? 'list="dlg-list"' : ""}>
        ${options.length ? `<datalist id="dlg-list">${options.map((o) => `<option value="${esc(o)}">`).join("")}</datalist>` : ""}`}
      <div class="actions end"><button type="button" value="no">${esc(cancel)}</button><button class="${danger ? "b-bad" : "main"}" value="ok">${esc(ok)}</button></div></form>`;
    if (title) d.querySelector("h3").textContent = title;
    d.querySelector("p").textContent = text;
    const input = d.querySelector("input");
    if (input) { input.value = value; input.placeholder = placeholder; }
    d.querySelector("button[value=no]").onclick = () => d.close("no");
    d.addEventListener("click", (e) => { if (e.target === d) d.close("no"); });          // a click on the backdrop
    d.addEventListener("close", () => { const yes = d.returnValue === "ok"; const answer = input ? (yes ? input.value : null) : yes; d.remove(); resolve(answer); });
    document.body.appendChild(d);
    d.showModal();
    if (input) { input.focus(); input.select(); } else d.querySelector(danger ? "button[value=no]" : "button[value=ok]").focus();
  });
}
const ask = (text, options = {}) => dialog({text, ok: "Sí", ...options});
const askText = (text, value = "", options = {}) => dialog({text, value, ok: "Guardar", ...options});

// a big sheet over the page (the ideas of a niche, a text to copy by hand): the same <dialog>, wider
function sheet(html, onClose) {
  let d = document.getElementById("modal");
  if (!d) {
    d = document.createElement("dialog");
    d.id = "modal"; d.className = "dialog sheet";
    d.addEventListener("click", (e) => { if (e.target === d) d.close(); });
    d.addEventListener("close", () => { d.remove(); if (onClose) onClose(); });
    document.body.appendChild(d);
    d.showModal();
  }
  d.innerHTML = `<div>${html}</div>`;
  return d;
}
