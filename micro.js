// Round 15's micro UI in 3D Studio (owner 2026-10-09 on r15-micro.html: «Все топ, все делай»; r15-3d.html) and round 16's scrub (owner
// 2026-10-10 on r16-scrub.html, version A: «отлично, беру»), with Hyimg's primitives (review/ui/hy):
//   outlinerMicro  «All nodes» is a mini toggle beside the layer list's search (<hy-minitoggle>). Until 2026-10-10 the search's count
//                  «part / all» (<hy-scope>) was the same switch; two places for one switch, it went (owner 2026-10-10, round 18
//                  question 18, version B: «только мини-тогл»)
//   camLed         the active camera's LED after its name (<hy-led>, the Studio's pink), where the «card» chip stood
//   scrubSize      the render size's W and H letters drag the number (window.hyScrub); the card takes the size once at the end of a drag,
//                  a size being a whole new render; Esc puts it back
// The inspector's own on/off, short choices and X Y Z rows are DialKit patches (vendor/dialkit/index.js: mountToggle, mountMicroSeg, mountVec).

/**
 * Wires «All nodes» beside the outliner's search; returns sync(doc), to call after each redraw of the list.
 * @param {any} L the live editor
 * @param {HTMLElement} root the panels' root
 * @param {{ q: (s: string) => any, tree: () => void }} o
 */
export function outlinerMicro(L, root, { q, tree }) {
  root.addEventListener("hy-change", ev => {
    if (!ev.target.matches("hy-minitoggle[data-raw]")) return;
    L.raw = !!ev.detail.checked; tree();
  });
  return () => { q("hy-minitoggle[data-raw]").toggleAttribute("checked", !!L.raw); };
}

/** @param {(k: string) => string} t */
export const camLed = t => `<hy-led title="${t("The current camera")}"></hy-led>`;

/**
 * @param {HTMLInputElement[]} ins the W and H fields, each after its letter
 * @param {(x: HTMLInputElement) => void} typed applies a field's number
 * @param {() => void} sync shows the card's size again
 */
export function scrubSize(ins, typed, sync) {
  if (!window.hyScrub) return;
  for (const x of ins) window.hyScrub(x.previousElementSibling, { get: () => +x.value || 0, set: v => { x.value = String(Math.round(v)); }, min: 16, max: 16384,
    field: x.parentElement, end: () => typed(x), cancel: sync, click: () => x.focus() });
}

/**
 * DialKit's text fields (a name, a prompt, a variant's name) as one-line fields with the rules of a rename in the crumb (P4 S-14, П4 audit
 * 2026-10-10: a textarea took ↵ as a new line and wrote each letter as a change): ↵ applies, Esc puts a name back (a prompt keeps its
 * words, S-25), a click away applies, and the whole edit is one change, one step of History. DialKit keeps hearing each letter (its own
 * field stays as typed); what it hands over while such a field has the focus waits in holdText() and is applied once, when the edit is
 * applied.
 * @param {HTMLElement} host the inspector's DialKit root
 */
let held = null;   // {v, apply}: the panel's values handed over while a text field is being typed in
export function holdText(v, apply) {
  const a = document.activeElement; if (!a || !a.classList || !a.classList.contains("dialkit-text-input")) return false;
  held = { v, apply }; return true;
}
export function oneLine(host, o = {}) {
  const isText = el => !!el && !!el.classList && el.classList.contains("dialkit-text-input");
  const apply = () => { const h = held; held = null; if (h) h.apply(h.v); };
  // Esc by Hyimg's one rule (owner decision 2026-10-10, P4 S-25): a prompt (o.content, its label) keeps what was typed, a name goes back;
  // ⌘↵ applies and saves (o.primary, S-28); the keys are Hyimg's one helper's (ui/typing.js hyTyping.keys)
  const back = el => { el._esc = true; el.value = el._was ?? el.value; el.dispatchEvent(new Event("input", { bubbles: true })); el.blur(); };
  host.addEventListener("focusin", e => {
    const el = e.target; if (!isText(el)) return; el._was = el.value; el._esc = false; held = null;
    if (el._hyk || !window.hyTyping || !window.hyTyping.keys) return;
    const label = el.closest(".dialkit-text-control")?.querySelector(".dialkit-text-label")?.textContent || "";
    el._hyk = window.hyTyping.keys(el, { esc: o.content && label === o.content ? "apply" : "cancel", enter: "line", apply: () => el.blur(), cancel: () => back(el), primary: o.primary });
  });
  host.addEventListener("keydown", e => {   // a Hyimg without the helper
    const el = e.target; if (!isText(el) || e.isComposing || el._hyk) return;
    if (e.key === "Enter") { e.preventDefault(); e.stopPropagation(); el.blur(); }   // the click away's way: focusout applies
    else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); back(el); }   // the text as it was, in the field and in DialKit
  }, true);
  host.addEventListener("input", e => {   // a pasted line break is a space
    const el = e.target; if (isText(el) && /[\r\n]/.test(el.value)) { el.value = el.value.replace(/\s*[\r\n]+\s*/g, " "); }
  }, true);
  host.addEventListener("focusout", e => { const el = e.target; if (!isText(el)) return; if (el._esc) { el._esc = false; held = null; } else apply(); }, true);
}
