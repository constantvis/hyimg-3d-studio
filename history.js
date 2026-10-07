// The 3D studio's steps (owner 2026-10-07: «cmd + z не работает в 3D studio, пока я там редачу», «также отсутствует история в 3D
// editor»): ⌘Z ⇧⌘Z, the dock's ↶ ↷ and the History tab beside Properties, one list of steps of the scene and the card's own fields.
import { variantStep } from "./variants.js";   // the card's variant of light and materials (2026-10-07)
let HY = null, t = k => k, getLive = () => null;
export function initHistory(c) { HY = c.HY; t = c.t; getLive = c.live; }
export const itemFields = ["camera", "bg", "lock", "w", "h", "x", "y", "res", "variant", "compare"];   // its place, frame, output size, variant and A/B too
const clone = x => x === undefined ? undefined : JSON.parse(JSON.stringify(x));
const noUi = d => { const c = Object.assign({}, d); delete c.ui; return c; };
// undo inside the editor: the scene file is not the board, so it keeps its own steps (the list's colours, ui, are not one of them)
// A step is the scene and the card's own fields (its camera, background, frame: itemFields), so ⌘Z takes back «New camera from this
// view» whole, the card's switch to it too. A change while the pointer is down waits for its release (one gesture, one step), the rest
// a quarter of a second (a slider's batch of changes, keys held)
export const cardOfItem = it => { const c = {}; for (const f of itemFields) if (it && it[f] !== undefined) c[f] = it[f]; return c; };
export const cardOf = L => cardOfItem(HY.board.items[L.id]);
export function remember(L, what) {
  clearTimeout(L.hmT); L.hmT = 0;
  if (what !== "start" && L.pressed) { L.hmWhat = what; return; }
  if (what === "start") return record(L, what);
  L.hmT = setTimeout(() => { L.hmT = 0; record(L, what); }, 250);
}
function record(L, what) {
  if (getLive() !== L) return;
  const s = JSON.stringify({ doc: noUi(L.e.doc), card: cardOf(L) }); if (L.hist[L.hi] && L.hist[L.hi].s === s) return;
  const prev = L.hist[L.hi], lab = prev ? stepLabel(JSON.parse(prev.s), JSON.parse(s), what) : { label: t("Opened"), ico: "model" };
  L.hist = L.hist.slice(0, L.hi + 1); L.hist.push({ s, what, ...lab }); if (L.hist.length > 80) L.hist.shift(); L.hi = L.hist.length - 1;
  undoState(L);
}
// a step's name in History, from what changed between it and the one before (owner 2026-10-07: «Камера: поворот», «Объектив 128 → 185»,
// «Свет · Заполняющий скрыт», «Vase · перемещение», «Новая камера 05 · v05»); ico: the outliner's icon of what it touched
function stepLabel(a, b, what) {
  const same = (x, y) => JSON.stringify(x) === JSON.stringify(y), byId = l => new Map((l || []).map(x => [x.id, x]));
  const A = a.doc, B = b.doc, r = v => Math.round(v * 10) / 10;
  for (const [k, word, ico] of [["cameras", "camera", "camera"], ["lights", "light", "light"], ["objects", "object", "model"]]) {
    const ma = byId(A[k]), mb = byId(B[k]);
    for (const [id, x] of mb) if (!ma.has(id)) return { label: k === "cameras" ? t("New camera {name}", { name: x.name || id }) : t("{name} added", { name: x.name || id }), ico };
    for (const [id, x] of ma) if (!mb.has(id)) return { label: k === "cameras" ? t("Camera {name} deleted", { name: x.name || id }) : t("{name} deleted", { name: x.name || id }), ico };
    for (const [id, y] of mb) {
      const x = ma.get(id); if (same(x, y)) continue;
      const who = k === "lights" ? t("Light · {name}", { name: y.name || id }) : (y.name || id);
      if (!!x.hidden !== !!y.hidden) return { label: y.hidden ? t("{who} hidden", { who }) : t("{who} shown", { who }), ico: y.hidden ? "off" : "eye" };
      if (!!x.locked !== !!y.locked) return { label: y.locked ? t("{who} locked", { who }) : t("{who} unlocked", { who }), ico: y.locked ? "lock" : "unlock" };
      if (k === "cameras") {
        const d = Object.keys(y).filter(f => !same(x[f], y[f]));
        if (d.length === 1 && d[0] === "lens") return { label: t("Lens {a} → {b}", { a: r(x.lens), b: r(y.lens) }), ico };
        if (what === "original") return { label: t("Camera: as in its picture"), ico };
        if (d.every(f => f === "loc" || f === "rot")) return { label: t("Camera: turned"), ico };
        return { label: t("Camera {name} · changed", { name: y.name || id }), ico };
      }
      if (["loc", "rot", "scale"].some(f => !same(x[f], y[f]))) return { label: t("{who} · moved", { who }), ico: what === "pull" ? "smart" : "translate" };
      return { label: t("{who} · changed", { who }), ico };
    }
  }
  if (a.card.camera !== b.card.camera) {
    const c = (B.cameras || []).find(x => x.id === b.card.camera); return { label: t("Card camera: {name}", { name: c ? c.name : b.card.camera }), ico: "camera" };
  }
  if (!same(a.card.bg, b.card.bg)) return { label: t("Card background"), ico: "model" };
  if (["w", "h", "lock"].some(f => !same(a.card[f], b.card[f]))) return { label: t("Card frame"), ico: "model" };
  const vs = variantStep(A, B, a.card, b.card, t); if (vs) return vs;   // a variant of light and materials, the card's choice, A/B
  if (!same(A.world, B.world)) return { label: t("World light"), ico: "light" };
  return { label: t("Scene · changed"), ico: "model" };
}
// a step still waiting (the quarter second, a gesture not let go) is taken before ⌘Z, so ⌘Z right after a change takes that change back
export function settle(L) { if (L.hmT) { clearTimeout(L.hmT); L.hmT = 0; record(L, "edit"); } else if (L.hmWhat && !L.pressed) { L.hmWhat = null; record(L, "edit"); } }
export async function undo(L, dir) { settle(L); return jumpTo(L, L.hi + dir); }
export async function jumpTo(L, i) {
  settle(L);
  if (i < 0 || i >= L.hist.length || i === L.hi) return;
  L.hi = i; const st = JSON.parse(L.hist[i].s), ui = L.e.doc.ui;
  L.e.doc = st.doc; if (ui) L.e.doc.ui = ui; else delete L.e.doc.ui;   // the list's colours are not a step of the scene
  if (JSON.stringify(cardOf(L)) !== JSON.stringify(st.card)) {   // the card's camera, background or frame: on the board (one step of the session in the end)
    const it = HY.board.items[L.id], before = HY.snap(); for (const f of itemFields) { if (st.card[f] === undefined) delete it[f]; else it[f] = clone(st.card[f]); } HY.commit(before);
  }
  await L.view.apply(L.e.doc); L.reload(); undoState(L);   // the pick stays when it is still in the scene (L.reload)
}
// the dock's ↶ ↷ follow the steps
export function undoState(L) {
  if (L.ui && L.ui.hist) L.ui.hist();
  const b = L.ui && L.ui.bar; if (!b) return;
  const u = b.querySelector("[data-a=undo]"), r = b.querySelector("[data-a=redo]");
  if (u) u.disabled = L.hi <= 0; if (r) r.disabled = L.hi >= L.hist.length - 1;
}
// History, as the image studio's (owner 2026-10-07: «отсутствует история в 3D editor»): a tab beside Properties, each step by what it did,
// the current one lit, the steps after it dimmed until a new edit drops them; a click goes there (the same steps as ⌘Z ⇧⌘Z)
export function historyTab(L, q, ico, esc) {
  const histEl = q(".m3hist"), rp = q(".m3r");
  const hist = () => {
    if (histEl.hidden) return;
    const row = (h, i) => `<button class="hrow${i === L.hi ? " cur" : ""}${i > L.hi ? " fut" : ""}" data-to="${i}" role="listitem">`
      + `${ico(h.ico || "select")}<span class="ht">${esc(h.label || "")}</span></button>`;
    histEl.innerHTML = L.hist.map(row).join("");
    const c = histEl.querySelector(".cur"); if (c) c.scrollIntoView({ block: "nearest" });
  };
  q(".m3tabs").addEventListener("click", ev => {
    const b = ev.target.closest("[data-tab]"); if (!b) return; const on = b.dataset.tab === "hist";
    q(".m3tabs").querySelectorAll("[data-tab]").forEach(x => { x.classList.toggle("on", x === b); x.setAttribute("aria-selected", String(x === b)); });
    rp.classList.toggle("hist", on); histEl.hidden = !on; hist();
  });
  histEl.addEventListener("click", ev => { const b = ev.target.closest("[data-to]"); if (b) jumpTo(L, +b.dataset.to); });
  return hist;
}
