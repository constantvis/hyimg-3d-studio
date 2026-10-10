// 3D Studio's fields by Hyimg's one rule for Esc, ↵ and Tab (owner decision 2026-10-10, P4 S-25, Figma's split, the board's since B-15):
// what is written on the canvas keeps its text on Esc (a prompt), a name or a value goes back to what it was (an object's, a light's or a
// camera's name, a variant's name, a number). Every field asks Hyimg's one helper, hyTyping.keys (review/ui/typing.js), and ⌘↵ in any of
// them applies it and saves, the Studio's primary action (S-28).
//   sizeKeys(ins, typed, sync, primary)   the output size's W and H: ↵ applies, Esc puts the number back, ↑ ↓ step by 1 (⇧ by 10) and a burst
//                                         of presses is one change (S-38, S-56), Tab the other field (the panel is drawn again after a change)
//   searchKeys(input, clear)              the layer list's search: the first Esc clears it, the next gives the keys back to the Studio (S-57)
//   treeRename(L, tr, o)                  a double click on a row's name renames an object, a light or a camera (S-45); the camera's icon
//                                         on its row makes it the card's camera (the double click did that before)

const K = () => (window.hyTyping && window.hyTyping.keys ? window.hyTyping : null);

/**
 * @param {HTMLInputElement[]} ins the W and H fields
 * @param {(x: HTMLInputElement) => void} typed applies a field's number (one board step)
 * @param {() => void} sync shows the card's size again
 * @param {() => void} primary the Studio's Save
 */
export function sizeKeys(ins, typed, sync, primary) {
  for (const x of ins) {
    x.addEventListener("change", () => typed(x));
    const H = K();
    if (!H) {   // a Hyimg without the helper: the keys as before
      x.addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); typed(x); x.blur(); } else if (e.key === "Escape") { x.value = ""; sync(); x.blur(); } e.stopPropagation(); });
      continue;
    }
    let burst = 0;
    const land = () => { if (burst) { clearTimeout(burst); burst = 0; typed(x); } };
    x.addEventListener("blur", land);
    H.keys(x, { esc: "cancel", enter: "line", tab: "own", apply: () => { land(); typed(x); x.blur(); }, cancel: () => { clearTimeout(burst); burst = 0; x.value = ""; sync(); x.blur(); },
      primary,
      key: e => {
        if (e.key === "Tab") {   // the other field, found again: a change draws the panel anew
          e.preventDefault(); const k = x.dataset.k === "w" ? "h" : "w", box = x.closest(".m3res"); land(); typed(x);
          let n = 0;
          const go = () => { const f = (box && box.isConnected ? box : document).querySelector(`.m3res input[data-k="${k}"]`);
            if (f) { f.focus(); f.select(); } else if (++n < 10) requestAnimationFrame(go); };
          requestAnimationFrame(go); return;
        }
        if (e.key !== "ArrowUp" && e.key !== "ArrowDown") return;
        e.preventDefault();
        x.value = String(Math.max(16, Math.min(16384, Math.round(+x.value || 0) + (e.key === "ArrowUp" ? 1 : -1) * (e.shiftKey ? 10 : 1))));
        clearTimeout(burst); burst = setTimeout(() => { burst = 0; typed(x); }, 600);   // presses in a row: one change, one step
      } });
  }
}

/**
 * @param {HTMLInputElement} input
 * @param {() => void} clear empties the search and draws the list
 */
export function searchKeys(input, clear) {
  input.addEventListener("keydown", e => {
    if (e.key !== "Escape" && e.key !== "Enter") return;
    e.preventDefault(); e.stopPropagation();
    if (e.key === "Escape" && input.value) { input.value = ""; clear(); return; }   // the words first
    input.blur(); try { window.focus(); } catch { /* a closed window */ }   // then the keys go back to the Studio
  });
}

/**
 * @param {any} L the live Studio
 * @param {HTMLElement} tr the layer list
 * @param {{ t: (k: string, v?: any) => string, rename: (id: string, name: string) => void, setCamera: (id: string) => void, primary: () => void }} o
 */
export function treeRename(L, tr, o) {
  // two clicks on one row's name, counted here: the first click draws the list again, so the browser's dblclick lands on a new row
  let last = null;
  const idOf = r => r.dataset.cam || (r.querySelector("[data-lock]") || { dataset: {} }).dataset.lock || "";
  tr.addEventListener("click", ev => {
    const r = ev.target.closest(".row[data-k]"); if (!r || ev.target.closest(".acts, [data-open], input")) { last = null; return; }
    const id = idOf(r);
    if (r.dataset.cam && ev.target.closest(".row > svg, .row > .ic, hy-led")) {   // the camera's icon: the card looks through it
      ev.stopImmediatePropagation(); last = null; if (id !== L.camId()) o.setCamera(id); return;
    }
    const now = performance.now(), twice = !!id && last && last.id === id && now - last.at < 450 && ev.target.closest(".nm");
    last = twice ? null : { id, at: now };
    if (!twice) return;
    ev.stopImmediatePropagation();
    requestAnimationFrame(() => edit(id));
  }, true);
  function edit(id) {
    const r = [...tr.querySelectorAll(".row[data-k]")].find(x => idOf(x) === id), nm = r && r.querySelector(".nm"); if (!nm) return;
    const was = nm.firstChild && nm.firstChild.nodeType === 3 ? nm.firstChild.nodeValue : nm.textContent;
    const inp = document.createElement("input"); inp.className = "m3ren"; inp.value = was; inp.spellcheck = false; inp.setAttribute("aria-label", o.t("Name"));
    nm.replaceChildren(inp); inp.focus(); inp.select();
    let fin = false;
    const done = ok => { if (fin) return; fin = true; const v = inp.value.trim(); if (ok && v && v !== was) o.rename(id, v); else nm.textContent = was; };
    const H = K();
    if (H) H.keys(inp, { esc: "cancel", enter: "line", apply: () => done(true), cancel: () => done(false), primary: o.primary });   // a name
    else inp.addEventListener("keydown", e => { e.stopPropagation(); if (e.key === "Enter") done(true); if (e.key === "Escape") done(false); });
    inp.addEventListener("blur", () => done(true));
    for (const ev of ["pointerdown", "click", "dblclick"]) inp.addEventListener(ev, e => e.stopPropagation());
  }
}
