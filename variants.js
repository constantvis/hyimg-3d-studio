// «Свет и материалы» in the 3D studio (owner 2026-10-07: «было бы шикарно, если можно как-то свет тестировать и материалы», after the
// finding that the studio's current materials render the M07 angles lighter and pinker because the studio's light is fixed in its scene
// while M07 lit each angle its own way). A variant is a light and a set of material overrides with a name; the scene keeps them, a card
// shows one, Blender renders it in memory and never saves it (bridge.py, variants.py, blender/overrides.py):
//
//   scene.json "variants": [{id, name, light: "studio" | "angle" | "own", env (the world's strength ×), materials: {<name>: {<param>: ...}}}]
//   the card: item.variant (an id; none is the look as it is, «Без изменений»), item.compare (A/B: "base" or an id, the left half)
//
// This module is the studio's side: the variant row and the materials in the outliner's «Материалы» section (materials.js draws the
// materials), the variant's pane (name, light, environment), the bar's variant list and A/B (blender.js shows them), what Blender is sent,
// and the names of the steps in History. Every change is a step of the studio (⌘Z, History), «Сохранить» writes it, «Отмена» drops it.
import { materialRows, materialPane, mirror, fetchMaterials } from "./materials.js";
import { studioAngle } from "./blender.js";

const clone = x => x === undefined ? undefined : JSON.parse(JSON.stringify(x));
const LIGHTS = [["studio", "Studio light"], ["angle", "Angle light"], ["own", "Own light"]];
export const variantsOf = doc => (doc && Array.isArray(doc.variants) ? doc.variants : []);
export const variantOf = (doc, id) => (id ? variantsOf(doc).find(v => v.id === id) || null : null);
const newId = () => "v" + Math.random().toString(16).slice(2, 8);
// what Blender is sent for a variant: the variant and, for «Свой свет», the scene's lights as they are now
export const bodyFor = (doc, v) => (v ? { variant: clone(v), lights: v.light === "own" ? clone(doc.lights || []) : undefined } : {});
// what changes Blender's frame: the variant's light, world and materials, and the lights it lights with
export const keyFor = (doc, v) => (v ? JSON.stringify([v.light || "studio", v.env ?? 1, v.materials || {}, v.light === "own" ? doc.lights : 0]) : "");

// a step's name in History (history.js stepLabel), or null when no variant changed
export function variantStep(A, B, ca, cb, t) {
  const name = (doc, id) => { const v = variantOf(doc, id); return v ? v.name : t("No changes"); };
  const lightWord = v => t(LIGHTS.find(l => l[0] === (v.light || "studio"))[1]);
  // what a variant holds that another does not: its first material, its light, its environment
  const what = (w, v) => {
    const mats = new Set([...Object.keys(w.materials || {}), ...Object.keys(v.materials || {})]);
    for (const m of mats) if (JSON.stringify((w.materials || {})[m]) !== JSON.stringify((v.materials || {})[m])) return { label: t("{name} · {mat}", { name: v.name, mat: m }), ico: "model" };
    if ((w.light || "studio") !== (v.light || "studio")) return { label: t("{name} · {light}", { name: v.name, light: lightWord(v) }), ico: "light" };
    if ((w.env ?? 1) !== (v.env ?? 1)) return { label: t("{name} · environment {a} → {b} %", { name: v.name, a: Math.round((w.env ?? 1) * 100), b: Math.round((v.env ?? 1) * 100) }), ico: "light" };
    return null;
  };
  const a = variantsOf(A), b = variantsOf(B);
  if (JSON.stringify(a) !== JSON.stringify(b)) {
    for (const v of b) if (!a.some(x => x.id === v.id)) return what({ name: v.name }, v) || { label: t("Variant {name} added", { name: v.name }), ico: "plus" };
    for (const v of a) if (!b.some(x => x.id === v.id)) return { label: t("Variant {name} deleted", { name: v.name }), ico: "trash" };
    for (const v of b) {
      const w = a.find(x => x.id === v.id); if (JSON.stringify(w) === JSON.stringify(v)) continue;
      if (w.name !== v.name) return { label: t("Variant renamed: {name}", { name: v.name }), ico: "rename" };
      return what(w, v) || { label: t("{name} · changed", { name: v.name }), ico: "light" };
    }
  }
  if ((ca.variant || "") !== (cb.variant || "")) return { label: t("Card variant: {name}", { name: name(B, cb.variant) }), ico: "light" };
  if ((ca.compare || "") !== (cb.compare || "")) return { label: cb.compare ? t("A/B with {name}", { name: name(B, cb.compare === "base" ? "" : cb.compare) }) : t("A/B off"), ico: "compare" };
  return null;
}

// the look of the rows, the bar's controls and the A/B line: the app's tokens only (ui/look.css), sizes in the card divided by the board's zoom
const CSS = `
  .m3ui .row hy-swatch { display: inline-block; flex: none; width: 11px; height: 11px; margin: 0 7px 0 2px; border: 0; border-radius: 50%; background: var(--hy-sw);
    box-shadow: inset 0 0 0 1px var(--line); pointer-events: none; }   /* a dot of the material's colour, also where ui/hy is not loaded */
  .m3ui .row.m3ov .nm > .hy-dot { margin-left: 6px; }   /* changed in this variant: round 15's change dot (ui/hy/micro.css) */
  .m3ui .row[data-lm] .nm small, .m3ui .row[data-mat] .nm { overflow: hidden; text-overflow: ellipsis; }
  .tidy.plgedit .m3var .v { max-width: 150px; } .tidy.plgedit .m3abto .v { max-width: 120px; }
  .tidy.plgedit :is(.m3var, .m3abto) .v { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .tidy.plgedit .m3ab { flex: none; height: 34px; gap: 5px; padding: 0 12px 0 10px; border-radius: 999px; color: var(--sub); font: 500 13px var(--sans); }
  .tidy.plgedit .m3ab:hover, .tidy.plgedit .m3ab[aria-pressed=true] { color: var(--ink); }
  .tidy.plgedit .m3ab[aria-pressed=true] { background: var(--raise); }
  :root[data-shape=pro] .tidy.plgedit .m3ab { border-radius: 8px; }
  .plg-live img.m3bimgA { z-index: 2; clip-path: inset(0 calc(100% - var(--ab, .5) * 100%) 0 0); }
  .plg-live .m3split { position: absolute; inset: 0; z-index: 3; pointer-events: none; }
  .plg-live .m3split .ln { position: absolute; top: 0; bottom: 0; left: calc(var(--ab, .5) * 100%); width: calc(2px / var(--z)); margin-left: calc(-1px / var(--z)); background: var(--panel);
    box-shadow: 0 0 0 calc(1px / var(--z)) color-mix(in srgb, var(--ink) 30%, transparent); }
  .plg-live .m3split .hd { position: absolute; top: 50%; left: calc(var(--ab, .5) * 100%); width: calc(22px / var(--z)); height: calc(22px / var(--z));
    margin: calc(-11px / var(--z)) 0 0 calc(-11px / var(--z));
    border-radius: 50%; background: var(--panel); box-shadow: 0 calc(1px / var(--z)) calc(6px / var(--z)) color-mix(in srgb, var(--ink) 35%, transparent); pointer-events: auto; touch-action: none; }
  .plg-live .m3split :is(.la, .lb) { position: absolute; top: calc(8px / var(--z)); max-width: 45%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    padding: calc(3px / var(--z)) calc(9px / var(--z)); border-radius: 999px; background: color-mix(in srgb, var(--ink) 72%, transparent); color: var(--panel);
    font: 500 calc(11px / var(--z)) var(--sans); }
  .plg-live .m3split .la { left: calc(8px / var(--z)); } .plg-live .m3split .lb { right: calc(8px / var(--z)); }`;
const css = () => { if (document.getElementById("m3look-css")) return; const st = document.createElement("style"); st.id = "m3look-css"; st.textContent = CSS; document.head.appendChild(st); };

// for the tests: what three.js shows of a material in the open studio (its first mesh's metalness, roughness and colour)
let ACTIVE = null;
export function liveMaterial(name) {
  let out = null; if (!ACTIVE) return null;
  for (const u of ACTIVE.view.units.values()) if (!out && u.kind === "object") u.obj.traverse(m => { const b = m.userData.base;
    if (!out && m.isMesh && b && b.mat.name === name) out = { metalness: b.mat.metalness, roughness: b.mat.roughness, color: "#" + b.mat.color.getHexString() }; });
  return out;
}

// the studio's session: ctx { HY, t, api (the bridge) }; only a scene from a Blender studio (scene.studio) has it
export function attachLook(L, ctx) {
  const { HY, t } = ctx, doc = () => L.e.doc, item = () => HY.board.items[L.id];
  if (!studioAngle(doc(), L.camId())) return null;
  css(); ACTIVE = L;
  ctx.lookId = () => (L.blender && L.blender.lookId()) || "?";
  ctx.angleLook = () => (studioAngle(doc(), L.camId()) || {}).look;
  const S = { report: null, loading: null, error: "" };
  const current = () => variantOf(doc(), item().variant);
  const words = { light: t("Light"), env: t("Environment, %"), name: t("Name"), add: t("New variant"), dup: t("Duplicate variant"), del: t("Delete variant"),
    reset: t("Reset variant") };
  // «Сбросить вариант», as every reset of the studio: the card's variant and its content as they were when the studio opened
  const startOf = () => ({ id: L.start.item.variant || "", v: variantOf(L.start.doc, L.start.item.variant) });
  const resetDiff = () => { const s = startOf(), v = current(); return (item().variant || "") !== s.id || JSON.stringify(v) !== JSON.stringify(s.v); };
  const resetVariant = () => {
    const s = startOf(), v = current(), d = doc();
    if (v) { const was = variantOf(L.start.doc, v.id); d.variants = variantsOf(d).map(x => x.id === v.id ? clone(was) : x).filter(Boolean); if (!d.variants.length) delete d.variants; }
    if (s.v && !variantOf(d, s.id)) (d.variants = variantsOf(d)).push(clone(s.v));
    setCard({ variant: s.id || null }); return changed("reset").then(() => L.ui.panel());
  };
  // the card's variant, made when the first change asks for one (the look as it is stays as it is, the left of an A/B)
  const ensure = why => {
    let v = current(); if (v) return v;
    const d = doc(), list = d.variants = variantsOf(d), n = list.length + 1;
    v = { id: newId(), name: `${ctx.lookId()} · ${why || t("variant {n}", { n })}`, light: "studio" }; list.push(v);
    setCard({ variant: v.id }); return v;
  };
  const setCard = fields => {
    const it = item(), before = HY.snap();
    for (const [k, x] of Object.entries(fields)) { if (x == null || x === "") delete it[k]; else it[k] = x; }
    HY.commit(before, t("3D: card variant"));
  };
  // a change of the variants: the view follows (three.js mirrors the materials), the studio takes a step, the panels and bar redraw
  const changed = async what => { await L.view.apply(doc()); L.need(); L.changed(what || "variant"); L.ui.tree(); sync(); };
  const setLight = light => { const v = ensure(t(LIGHTS.find(l => l[0] === light)[1]).toLowerCase()); v.light = light; return changed("light"); };
  const choose = id => {
    if (id === "+new") {
      const d = doc(), list = d.variants = variantsOf(d), v = { id: newId(), name: `${ctx.lookId()} · ${t("variant {n}", { n: list.length + 1 })}`, light: "studio" };
      list.push(v); setCard({ variant: v.id });
    } else if (id === "+dup") {
      const c = current(); if (c) { const v = Object.assign(clone(c), { id: newId(), name: t("{name} copy", { name: c.name }) }); doc().variants.push(v); setCard({ variant: v.id }); }
    }
    else if (id === "+del") { const c = current(); if (c) { doc().variants = variantsOf(doc()).filter(v => v.id !== c.id); if (!doc().variants.length) delete doc().variants;
      setCard({ variant: null, compare: item().compare === c.id ? "base" : item().compare }); } }
    else setCard({ variant: id || null, compare: item().compare && item().compare === id ? "base" : item().compare });
    L.lmSel = L.lmSel && L.lmSel.kind === "material" ? L.lmSel : (L.lmSel ? { kind: "variant" } : null);
    changed("variant").then(() => L.ui.panel());
  };

  // -- the outliner's «Материалы»: the card's variant first, then the look's materials (materials.js)
  const rows = (out, top, query) => {
    const v = current(), sel = L.lmSel, ico = n => window.hyIcon ? window.hyIcon(n, 0, 1.85, "ic") : "";
    const sub = v ? `${t(LIGHTS.find(l => l[0] === (v.light || "studio"))[1]).toLowerCase()}${v.env != null && v.env !== 1 ? ` · ${Math.round(v.env * 100)} %` : ""}` : t("the look as it is");
    const vname = v ? v.name : t("No changes");
    if (!query || vname.toLowerCase().includes(query)) out.materials.push(`<div class="row${sel && sel.kind === "variant" ? " sel" : ""}" data-lm="variant" `
      + `title="${t("The card's variant: light and material overrides")}"><span class="chev"></span>${ico("light")}<span class="nm">${esc(vname)}<small>${esc(sub)}</small></span></div>`);
    const mr = materialRows(L, S, { query, sel, over: v && v.materials, t, esc });
    out.materials.push(...mr); top.materials = mr.length;
  };
  const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const tr = L.ui.root.querySelector(".tr");
  const onRow = ev => {
    const r = ev.target.closest(".row[data-lm],.row[data-mat]"); if (!r) return;
    ev.stopPropagation();
    L.sel = null; L.multi = null; L.tc.detach();
    L.lmSel = r.dataset.lm ? { kind: "variant" } : { kind: "material", name: r.dataset.mat };
    if (L.lmSel.kind === "material" && !S.report) load();
    L.ui.tree(); L.ui.panel(); L.need();
  };
  tr.addEventListener("click", onRow);
  const load = () => {   // Blender's list of the look's materials, once (the pane says it is reading meanwhile)
    if (S.loading) return S.loading;
    S.error = "";
    S.loading = fetchMaterials(ctx.api, L, item().look === "angle" ? "angle" : "current").then(r => { S.report = r; }, e => { S.error = e.message; })
      .finally(() => { S.loading = null; if (L.lmSel) L.ui.panel(); L.ui.tree(); });
    return S.loading;
  };

  // -- the right panel: the variant (name, light, environment, new, copy, delete) or a material (materials.js)
  const pane = () => {
    const sel = L.lmSel; L.paneKind = "look"; L.why = null;
    const q = s => L.ui.root.querySelector(s); q(".dk").classList.remove("m3dis");
    if (sel.kind === "material") return materialPane(L, S, { t, esc, current, ensure, changed, load });
    const v = current(), light = (v && v.light) || "studio", own = ctx.angleLook ? ctx.angleLook() : "";
    L.ih("light", v ? v.name : t("No changes"), t("variant of the card"));
    // the three lights in key words; the whole of it in the ⓘ's tooltip (the app's rule for panel prose)
    const more = t("Studio light: the look's own lamps and world. Angle light: the lamps and world the picture of this angle was made with ({own}), "
      + "placed for this camera; its first frame takes a few seconds. Own light: the scene's lamps from Lights").replace("{own}", own || "?");
    L.inf(`<p class="hy-hint m3hint">${t("<b>Studio</b> as the look has it · <b>angle</b> as in the picture {own} · <b>own</b> the scene's lamps").replace("{own}", esc(own || "?"))}`
      + ` <button type="button" class="hy-info" title="${esc(more)}" aria-label="${esc(more)}"></button></p>`);
    const cfg = {
      [words.name]: { type: "text", default: v ? v.name : "" },
      [words.light]: { type: "select", options: LIGHTS.map(([value, label]) => ({ value, label: t(label) })), default: light },
      [words.env]: [Math.round(((v && v.env) ?? 1) * 100), 0, 200, 1],
      [words.add]: { type: "action" },
    };
    if (v) { cfg[words.dup] = { type: "action" }; cfg[words.del] = { type: "action" }; }
    cfg[words.reset] = { type: "action" };
    L.dial(t("Variant"), cfg, val => {
      const cur = current();
      if (val[words.light] !== light) return setLight(val[words.light]).then(() => L.ui.panel());
      const name = String(val[words.name] || "").trim(), env = val[words.env] / 100;
      if (cur ? name && name !== cur.name : name) { const x = ensure(name); x.name = name; return changed("rename"); }
      if (Math.abs(env - ((cur && cur.env) ?? 1)) > 1e-6) { const x = ensure(t("environment")); if (Math.abs(env - 1) < 1e-6) delete x.env; else x.env = +env.toFixed(2); return changed("env"); }
    }, a => {
      if (a.endsWith(words.add)) choose("+new"); else if (a.endsWith(words.dup)) choose("+dup");
      else if (a.endsWith(words.del)) choose("+del"); else if (a.endsWith(words.reset)) resetVariant();
    });
    requestAnimationFrame(() => {
      const b = [...L.ui.root.querySelectorAll(".dk .dialkit-button")].find(x => x.textContent.trim() === words.reset); if (!b) return;
      const on = resetDiff(); b.classList.add("hy-reset"); b.disabled = !on; b.title = on ? t("Back to how it was when the studio opened") : t("Nothing changed");
    });
  };

  // -- the bar over the card (blender.js): the card's variant, A/B and what A is
  const chev = () => window.HY_CHEV || "", abIco = () => (window.hyIcon ? window.hyIcon("compare", 0, 1.9) : "");
  const barHtml = () => `<label class="m3lk m3var" title="${t("The card's variant: light and material overrides")}"><span class="v"></span>${chev()}`
    + `<select data-var aria-label="${t("Variant")}"></select></label>`
    + `<button type="button" class="m3ab" data-ab aria-pressed="false" title="${t("A/B: two variants side by side in the card, a line to drag between them")}">${abIco()}<span>A/B</span></button>`
    + `<label class="m3lk m3abto" hidden title="${t("A, the left half")}"><span class="v"></span>${window.HY_CHEV || ""}<select data-abto aria-label="${t("A, the left half")}"></select></label>`;
  let bar = null;
  const opt = (value, label, on) => `<option value="${esc(value)}"${on ? " selected" : ""}>${esc(label)}</option>`;
  function sync() {
    if (!bar) return;
    const it = item(), v = current(), list = variantsOf(doc()), sel = bar.querySelector("[data-var]"), to = bar.querySelector("[data-abto]");
    sel.innerHTML = opt("", t("No changes"), !v) + list.map(x => opt(x.id, x.name, v && x.id === v.id)).join("") + `<option disabled>──────</option>`
      + opt("+new", t("New variant")) + (v ? opt("+dup", t("Duplicate variant")) + opt("+del", t("Delete variant")) : "");
    bar.querySelector(".m3var .v").textContent = v ? v.name : t("No changes");
    const ab = bar.querySelector("[data-ab]"), on = !!it.compare; ab.setAttribute("aria-pressed", String(on)); ab.classList.toggle("on", on);
    to.innerHTML = opt("base", t("No changes"), it.compare === "base") + list.filter(x => !v || x.id !== v.id).map(x => opt(x.id, x.name, it.compare === x.id)).join("");
    bar.querySelector(".m3abto").hidden = !on; bar.querySelector(".m3abto .v").textContent = "A · " + (to.selectedOptions[0] ? to.selectedOptions[0].textContent : "");
  }
  const wireBar = wrap => {
    bar = wrap; sync();
    wrap.querySelector("[data-var]").addEventListener("change", e => { const id = e.target.value; choose(id); });
    wrap.querySelector("[data-ab]").addEventListener("click", e => { e.stopPropagation(); setCard({ compare: item().compare ? null : "base" }); L.changed("compare"); sync(); });
    wrap.querySelector("[data-abto]").addEventListener("change", e => { setCard({ compare: e.target.value }); L.changed("compare"); sync(); });
  };

  // three.js mirrors the card's material overrides (colour, roughness, metalness) on every apply of the scene
  const plain = L.view.apply;
  L.view.apply = async function (d) { const r = await plain.call(this, d); mirror(this, (current() || {}).materials); return r; };
  L.view.apply(doc()).then(() => { L.need(); L.ui.tree(); });
  return {
    rows, pane, barHtml, wireBar, sync, load,
    light: () => ((current() || {}).light || "studio"), setLight,
    key: id => keyFor(doc(), id === undefined ? current() : variantOf(doc(), id === "base" ? "" : id)),
    body: id => bodyFor(doc(), id === undefined ? current() : variantOf(doc(), id === "base" ? "" : id)),
    nameOf: id => { const v = variantOf(doc(), id === "base" ? "" : id); return v ? v.name : t("No changes"); },
    dispose() { tr.removeEventListener("click", onRow); delete L.view.apply; L.view.apply(doc()).catch(() => {}); if (ACTIVE === L) ACTIVE = null; },
  };
}
