// Annotations in 3D Studio (owner 2026-10-09 on round 15, r15-3d.html and r15-annotations-3d.html liked as drawn: «3D у нас, естественно,
// тоже не хватает аннотаций, чтобы можно было так же выделить какой-то слой и комментировать его»). A thread is tied to an object, a
// light, a camera or a layer of a model, and its pin follows it wherever it is moved or the camera turns:
//   C or «Annotation» in the dock   the tool: a click on the work drops a pin on the thing under it (the picked object's layer inside it),
//                                   a drag marks an area around the thing under its middle, Esc leaves the tool
//   the tree                        a row with open threads shows their count (a click opens the newest, again the next one)
//   «Annotations» beside «Layers»   Hyimg's one Annotations list (ui/annlist.js, Image Studio's too): the threads by object, Open | Resolved,
//                                   «This layer» keeps the picked one, a field annotates it
// The thread is the board's (Hyimg ui/comments.js): replies, @mentions, Resolve, the bell and hy.py comments. Its anchor names the card
// and the part (anchor.part, Hyimg review/comments.py clean_part): {kind: "object", id, name, layer?, local: [x, y, z]} in the thing's own
// axes. Its at and area stay the pin's place on the card's picture, put right after a Save (op place), so the board shows it where the
// card shows the thing. The pins here are Hyimg's round Studio pins (ui/studiopins.js) in the Studio's pink.
import { layerPath } from "./scene.js";

const CSS = `
  .m3l .m3ltabs { margin: -4px -6px 4px -2px; padding: 0; height: 30px; }
  .m3l.m3annon > :not(.m3ltabs, .m3ann) { display: none !important; }
  .m3l .m3ann { flex: 1; min-height: 0; display: flex; flex-direction: column; }
  .m3l .m3ann[hidden] { display: none; }
  body.m3ann-on .plg-live canvas.m3live { cursor: crosshair !important; }`;

let CUR = null;   // the live session's annotations (one at a time), for the board's position hook
let hooked = false;
const CM = () => window.hyComments;
const page = () => (typeof BOARD !== "undefined" ? BOARD : "main");   // the board's page (canvas.html)

async function listLib() {
  if (!window.hyAnnList) { try { await import("/ui/annlist.js"); } catch (e) { console.error("annotations list", e); } }
  return window.hyAnnList || null;
}
async function pinsLib() {
  if (!window.hyStudioPins) { try { await import("/ui/studiopins.js"); } catch (e) { console.error("studio pins", e); } }
  return window.hyStudioPins || null;
}

// the board asks where a thread's pin stands (ui/comments.js position): a thread on a part of the card open here, at its pin in the view
function hookBoard() {
  if (hooked || !CM() || !CM().position) return; hooked = true;
  CM().position(t => (CUR && t.anchor && t.anchor.obj === CUR.id ? CUR.boardAt(t) : undefined));
}

export function attachAnn(L, { HY, t, THREE, unitOf, head, pick, esc, ico }) {
  const cvs = L.el.querySelector(":scope > canvas.m3live"), on = { signal: L.ac.signal }, cap = { capture: true, signal: L.ac.signal };
  const A = { tool: false, tab: "layers", filter: "open", mine: false, live: null, draft: null, closedAt: 0, sig: "" };
  const style = document.createElement("style"); style.textContent = CSS; document.head.appendChild(style);
  // the board's own pins of this card step aside while its Studio shows them (ui/comments.js writes the card's id in data-o)
  style.textContent += `\n  #cmpins > [data-o="${CSS_ESC(L.id)}"], #cmpins > [data-c="draft"], #cmpins > [data-a="draft"], #cmpins > [data-a="live"] { display: none !important; }`;
  let P = null; pinsLib().then(lib => { if (lib && CUR === api) { P = lib.layer(HY.stage, { z: 31, onPin: id => openThread(id) }); draw(); } });

  // ---- what a thread is tied to ------------------------------------------------------------------------------------------------------
  const doc = () => L.e.doc;
  const keyOf = p => (p.layer ? `${p.id}/${p.layer}` : p.id);
  const mine = th => th && th.anchor && th.anchor.obj === L.id;
  const threads = () => (CM() && CM().threads ? CM().threads() : []).filter(mine).filter(th => !window.hyAnnot || !hyAnnot.visible || hyAnnot.visible(th.by));
  const nameOf = id => { const d = doc(); const x = [...(d.objects || []), ...(d.lights || []), ...(d.cameras || [])].find(o => o.id === id); return x ? x.name || id : id; };
  const shown = n => n.userData.shown || n.userData.label || n.name || "";
  // the node of a part: the object's or light's unit, the layer by its path, a camera's icon
  const nodes = new Map();
  function nodeOf(p) {
    const k = keyOf(p); if (nodes.has(k)) { const n = nodes.get(k); if (n && inScene(n)) return n; }
    const u = L.view.units.get(p.id); let n = null;
    if (u) { n = u.obj; if (p.layer) { let f = null; u.obj.traverse(x => { if (!f && x !== u.obj && layerPath(u.obj, x) === p.layer) f = x; }); n = f || u.obj; } }
    else n = L.icons.get(p.id) || null;
    nodes.set(k, n); return n;
  }
  const inScene = n => { while (n) { if (n.isScene) return true; n = n.parent; } return false; };
  // the part a picked node is: an object, a light or a camera, or a layer of a model
  function partOf(n) {
    if (!n) return null;
    if (n.userData.cam) return { kind: "object", id: n.userData.cam, name: nameOf(n.userData.cam) };
    const u = unitOf(n); if (!u) return null;
    const id = u.userData.id;
    if (u === n || u.userData.kind === "light") return { kind: "object", id, name: nameOf(id) };
    return { kind: "object", id, name: shown(n) || nameOf(id), layer: layerPath(u, n) };
  }

  // ---- the view's geometry ------------------------------------------------------------------------------------------------------------
  const rect = () => cvs.getBoundingClientRect();
  const stageAt = () => HY.stage.getBoundingClientRect();
  // a point in a node's own axes -> the screen; null behind the camera
  function screenOf(n, local) {
    if (!n) return null;
    const v = new THREE.Vector3(...(local || [0, 0, 0])); n.updateWorldMatrix(true, false); n.localToWorld(v); v.project(L.cam);
    if (!(v.z < 1 && v.z > -1)) return null;
    const r = rect(); return { x: r.left + (v.x + 1) / 2 * r.width, y: r.top + (1 - v.y) / 2 * r.height };
  }
  const shareOf = s => { const r = rect(); return [(s.x - r.left) / r.width, (s.y - r.top) / r.height]; };
  const fromShare = (u, v) => { const r = rect(); return { x: r.left + u * r.width, y: r.top + v * r.height }; };
  // the thing under a point of the view and the point on it: the same targets as a click's pick (engine.js hit), the layer of the
  // picked object inside it, else the object
  const ray = new THREE.Raycaster(); ray.layers.enableAll();
  function under(x, y) {
    const r = rect(); ray.setFromCamera(new THREE.Vector2((x - r.left) / r.width * 2 - 1, -(y - r.top) / r.height * 2 + 1), L.cam);
    const locked = id => { const d = doc(); const o = [...d.objects, ...d.lights, ...d.cameras].find(q => q.id === id); return o && o.locked; };
    const targets = [...L.icons.values()].filter(m => m.visible && !locked(m.userData.light || m.userData.cam));
    for (const [uid, u] of L.view.units) if (u.kind === "object" && u.obj.visible && !locked(uid)) u.obj.traverseVisible(m => { if (m.isMesh) targets.push(m); });
    const h = ray.intersectObjects(targets, false)[0]; if (!h) return null;
    const o = h.object;
    if (o.userData.light) { const n = L.view.units.get(o.userData.light).obj; return { n, local: [0, 0, 0] }; }
    if (o.userData.cam) return { n: o, local: [0, 0, 0] };
    const u = unitOf(o); if (!u) return null;
    const n = L.sel && (L.sel === u || u.getObjectById(L.sel.id)) ? head(u, o) : u;
    const p = n.worldToLocal(h.point.clone()); return { n, local: [p.x, p.y, p.z].map(v => Math.round(v * 1e5) / 1e5) };
  }
  // the middle of a node's meshes in its own axes (a thread from the panel's field), its origin for a light or a camera
  function middle(n) {
    const b = new THREE.Box3().setFromObject(n); if (b.isEmpty()) return [0, 0, 0];
    const c = n.worldToLocal(b.getCenter(new THREE.Vector3())); return [c.x, c.y, c.z].map(v => Math.round(v * 1e5) / 1e5);
  }

  // ---- where each pin stands ----------------------------------------------------------------------------------------------------------
  // a thread's place on the screen: its part's point (an area around it keeps its size on the card), else its share of the card
  function placeOf(th) {
    const p = th.anchor.part, ar = th.area, n = p && nodeOf(p);
    if (n) {   // the part's point; a part gone from the scene stands where the card last showed it
      const s = screenOf(n, p.local); if (!s) return null;
      if (!ar) return { pin: s };
      const r = rect(), w = ar[2] * r.width, h = ar[3] * r.height, box = { x: s.x - w / 2, y: s.y - h / 2, w, h };
      return { pin: { x: box.x + w, y: box.y }, box };
    }
    if (ar) { const a = fromShare(ar[0], ar[1]), r = rect(), box = { x: a.x, y: a.y, w: ar[2] * r.width, h: ar[3] * r.height }; return { pin: { x: box.x + box.w, y: box.y }, box }; }
    return { pin: fromShare(th.at[0], th.at[1]) };
  }
  const toBoard = s => { const r = rect(), b = HY.rectOf(L.id); return { x: b.x + (s.x - r.left) / r.width * b.w, y: b.y + (s.y - r.top) / r.height * b.h }; };
  function boardAt(th) {
    if (!th.anchor.part) return undefined;
    const q = placeOf(th); return q ? toBoard(q.pin) : null;
  }
  function draw() {
    if (!P || CUR !== api) return;
    const st = stageAt(), open = (CM() && CM().state) || {}, out = [], rel = s => ({ x: s.x - st.left, y: s.y - st.top });
    const relBox = b => b && { x: b.x - st.left, y: b.y - st.top, w: b.w, h: b.h };
    const hide = document.documentElement.classList.contains("hy-hideui") || (window.hyAnnot && hyAnnot.state && hyAnnot.state.show === false);
    if (!hide) for (const th of threads()) {
      if (th.resolved && open.open !== th.id) continue;
      const q = placeOf(th); if (!q) continue;
      const nm = th.anchor.part ? th.anchor.part.name || nameOf(th.anchor.part.id) : t("the card");
      out.push({ id: th.id, ...rel(q.pin), n: th.messages.length, on: open.open === th.id, area: relBox(q.box), title: `${nm}: ${(th.messages[0] || {}).text || ""}`.slice(0, 120),
        kept: !!(open.drafts && open.drafts.has(th.id)) && open.open !== th.id });   // a reply typed and not sent: the dot (P4 S-32)
    }
    if (!hide) for (const [k, w] of open.waits || []) {   // a new one typed and not sent, on this card: its pin with the dot, a click opens it again
      if (!w.d.anchor || w.d.anchor.obj !== L.id || (open.draft && open.draft.wid === k)) continue;
      const q = placeOf({ anchor: w.d.anchor, area: w.d.area, at: w.d.at || [0.5, 0.5] }); if (!q) continue;
      out.push({ id: k, ...rel(q.pin), draft: true, kept: true, area: relBox(q.box), title: t("Draft: {text}", { text: String(w.text).slice(0, 80) }) });
    }
    if (A.live) out.push({ id: "live", area: relBox(A.live) });
    if (A.draft && open.draft) { const s = A.draft.part ? screenOf(A.draft.n, A.draft.part.local) : A.draft.s; if (s) {
      const b = A.draft.wh ? { x: s.x - A.draft.wh[0] / 2, y: s.y - A.draft.wh[1] / 2, w: A.draft.wh[0], h: A.draft.wh[1] } : null;
      out.push({ id: "draft", draft: true, ...rel(b ? { x: b.x + b.w, y: b.y } : s), area: relBox(b) }); } }
    P.draw(out);
  }
  // the pins follow the view: each frame, only when the camera, the card or the threads changed
  let raf = 0, key = "";
  const loop = () => {
    raf = requestAnimationFrame(loop);
    const r = rect(), e = L.cam.matrixWorld.elements, k = [r.left, r.top, r.width, r.height, ...e.map(v => v.toFixed(5)), A.sig, !!A.live, !!A.draft,
      (CM() && CM().state && (CM().state.open || "") + (CM().state.draft ? "d" : "") + [...(CM().state.waits || new Map()).keys()] + (CM().state.drafts || new Map()).size) || ""].join(",");
    if (k === key && !A.live) return;
    key = k; draw(); if (CM() && CM().follow) CM().follow();
  };
  raf = requestAnimationFrame(loop);
  // a frame of the view (an object moved, ⌘Z, an agent's change): the pins are placed again on the next one
  const redraw0 = L.redraw; L.redraw = () => { redraw0(); key = ""; };

  // ---- the tool ---------------------------------------------------------------------------------------------------------------------------
  const bar = L.ui.bar, btn = document.createElement("button");
  btn.dataset.ann = ""; btn.setAttribute("aria-pressed", "false"); btn.title = t("Annotation: a layer or a spot · C"); btn.setAttribute("aria-label", t("Annotation"));
  btn.innerHTML = `${ico("comment")}<kbd>C</kbd>`;
  const pull = bar.querySelector('[data-tool="smart"]'); if (pull) pull.after(btn); else bar.appendChild(btn);
  btn.addEventListener("click", e => { e.stopPropagation(); setTool(!A.tool); }, on);
  function setTool(v) {
    A.tool = !!v; btn.classList.toggle("on", A.tool); btn.setAttribute("aria-pressed", String(A.tool)); document.body.classList.toggle("m3ann-on", A.tool);
  }
  // a press on the view with the tool: a click pins the thing under it, a drag marks an area; a press while a thread was open only closes it
  if (window.MutationObserver) {
    const mo = new MutationObserver(() => { const el = document.getElementById("cmthread"); if (el && !el.classList.contains("open")) A.closedAt = performance.now(); });
    const watch = () => { const el = document.getElementById("cmthread"); if (el) mo.observe(el, { attributes: true, attributeFilter: ["class"] }); else setTimeout(watch, 300); };
    watch(); L.ac.signal.addEventListener("abort", () => mo.disconnect());
  }
  let press = null;
  addEventListener("pointerdown", e => {
    if (!A.tool || e.target !== cvs || e.button !== 0 || e.altKey) return;
    e.stopPropagation(); e.preventDefault();
    if (performance.now() - A.closedAt < 80) return;   // the press closed an open thread (ui/comments.js): that is all it does
    press = { x: e.clientX, y: e.clientY, on: false };
  }, cap);
  addEventListener("pointermove", e => {
    if (!press) return; e.stopPropagation();
    if (!press.on && Math.hypot(e.clientX - press.x, e.clientY - press.y) < 5) return; press.on = true;
    A.live = { x: Math.min(press.x, e.clientX), y: Math.min(press.y, e.clientY), w: Math.abs(e.clientX - press.x), h: Math.abs(e.clientY - press.y) }; draw();
  }, cap);
  addEventListener("pointerup", e => {
    if (!press) { if (A.tool && e.target === cvs) e.stopPropagation(); return; }
    e.stopPropagation(); const p = press, box = A.live; press = null; A.live = null;
    if (p.on && box && box.w > 6 && box.h > 6) return newArea(box);
    newPin(p.x, p.y);
  }, cap);
  function anchor(part) {
    const it = HY.board.items[L.id], r = HY.rectOf(L.id);
    return { obj: L.id, kind: it.type, file: it.scene || "", r: [r.x, r.y, r.w, r.h], ...(part ? { part } : {}) };
  }
  function compose(s, part, n, o = {}) {
    const C = CM(); if (!C || !C.newAt) return;
    A.draft = { part, n, s, wh: o.wh || null };
    const at = shareOf(s).map(v => Math.round(v * 1e5) / 1e5);
    C.newAt(toBoard(s), { anchor: anchor(part), at: o.at || at, area: o.area || null, cancel: () => { A.draft = null; draw(); } });
    draw();
  }
  // an unsent new annotation opened again from its pin: the words back in the composer, its draft pin where it was (P4 S-32)
  function resume(id, w) {
    const p = w.d.anchor && w.d.anchor.part, n = p && nodeOf(p), q = placeOf({ anchor: w.d.anchor, area: w.d.area, at: w.d.at || [0.5, 0.5] });
    A.draft = { part: p || null, n, s: q ? q.pin : null, wh: null };
    CM().newAt(w.d.pos, { ...w.d, wid: id, text: w.text, ment: w.ment, cancel: () => { A.draft = null; draw(); } }); draw();
  }
  function newPin(x, y) {
    const h = under(x, y), part = h ? { ...partOf(h.n), local: h.local } : null;
    if (h) pick(h.n);
    compose({ x, y }, part, h && h.n);
  }
  function newArea(b) {
    const r = rect(), cx = b.x + b.w / 2, cy = b.y + b.h / 2, h = under(cx, cy), part = h ? { ...partOf(h.n), local: h.local } : null;
    if (h) pick(h.n);
    const area = [(b.x - r.left) / r.width, (b.y - r.top) / r.height, b.w / r.width, b.h / r.height].map(v => Math.round(v * 1e5) / 1e5);
    compose({ x: cx, y: cy }, part, h && h.n, { area, wh: [b.w, b.h], at: [area[0] + area[2], area[1]] });
  }
  function openThread(id) {
    const C = CM(), w = C && C.state && C.state.waits && C.state.waits.get(id); if (w) return resume(id, w);
    const th = C && C.threads().find(x => x.id === id); if (!th) return;
    const st = C.state || {}; if (st.open === id) { C.close(); return; }
    C.open(id);
  }
  // a thread opened from anywhere (its pin, a row's count, the list, the bell) picks its thing in the tree
  addEventListener("hy-comment-open", e => {
    const th = e.detail && e.detail.thread; if (!mine(th) || !th.anchor.part || (e.detail && e.detail.made)) return;
    const n = nodeOf(th.anchor.part); if (n && L.sel !== n) pick(n);
  }, on);

  // ---- the tree's counts and the Annotations tab ----------------------------------------------------------------------------------------
  const left = L.ui.root.querySelector(".m3l"), trEl = left.querySelector(".tr"), lib = () => window.hyStudioPins;
  const tabs = document.createElement("div"); tabs.className = "m3ltabs hy-bh"; tabs.setAttribute("role", "tablist");
  tabs.innerHTML = `<button class="hy-bh-tab on" data-ltab="layers" role="tab" aria-selected="true">${ico("layers", "")}${esc(t("Layers"))}<em></em></button>`
    + `<button class="hy-bh-tab" data-ltab="ann" role="tab" aria-selected="false">${ico("comment", "")}${esc(t("Annotations"))}<em></em></button>`;
  left.prepend(tabs);
  // the list: Hyimg's one (ui/annlist.js), in the left block under the tabs; its field's words outlive the session (draftKey: the scene)
  let AL = null, pane = document.createElement("div"); pane.className = "m3ann hy-annlist"; pane.hidden = true; left.appendChild(pane);
  tabs.addEventListener("click", e => { const b = e.target.closest("[data-ltab]"); if (b) showTab(b.dataset.ltab); }, on);
  function showTab(k) {
    A.tab = k; const ann = k === "ann";
    tabs.querySelectorAll("[data-ltab]").forEach(b => { const v = b.dataset.ltab === k; b.classList.toggle("on", v); b.setAttribute("aria-selected", String(v)); });
    left.classList.toggle("m3annon", ann); pane.hidden = !ann; if (ann) paneDraw(); else L.ui.tree();
  }
  const pickedPart = () => (L.sel ? partOf(L.sel) : null);
  // a new thread from the field: on the picked thing, its pin at its middle
  const send = async text => {
    const part = pickedPart(); if (!part || !window.hyAnnot) return false;
    const local = L.sel.userData.cam || L.sel.userData.kind === "light" ? [0, 0, 0] : middle(L.sel), s = screenOf(L.sel, local) || fromShare(0.5, 0.5);
    try {
      await hyAnnot.api("/api/comments", { op: "new", name: page(), anchor: anchor({ ...part, local }), at: shareOf(s).map(v => Math.round(v * 1e5) / 1e5), text });
      if (CM()) await CM().load(); return true;
    } catch (ex) { if (hyAnnot.fail) hyAnnot.fail(ex); return false; }
  };
  const icon = p => ico(!p ? "frame" : (doc().lights || []).some(x => x.id === p.id) ? "light" : (doc().cameras || []).some(x => x.id === p.id) ? "camera" : "mesh");
  listLib().then(lib => {
    if (!lib || CUR !== api) return;
    const old = pane; AL = lib.mount(left, { cls: "m3ann", threads, state: () => (CM() && CM().state) || {}, draftKey: "3d:" + L.path, picked: pickedPart, keyOf,
      nameOf: p => nameOf(p.id), iconOf: icon, open: id => openThread(id), send,
      face: by => (window.hyAvatarOf ? hyAvatarOf(by, 20) : ""), who: th => (window.hyWhoText ? hyWhoText(th) : ""), ago: iso => (window.T && window.T.ago ? window.T.ago(iso) : iso || "") });
    pane = AL.el; pane.hidden = old.hidden; old.remove(); paneDraw();
  });
  // a row's count: a click opens its newest thread, again the next one
  left.addEventListener("pointerdown", e => { if (e.target.closest && e.target.closest("[data-ann-n]")) { e.stopPropagation(); e.preventDefault(); } }, cap);
  left.addEventListener("click", e => {
    const b = e.target.closest && e.target.closest("[data-ann-n]"); if (!b) return; e.stopPropagation(); e.preventDefault();
    const row = b.closest("[data-k]"), k = row ? row.dataset.k : b.dataset.k; if (k) openKey(k);
  }, cap);
  function openKey(k) {
    const l = byKey().get(k); if (!l || !l.length) return;
    const st = (CM() && CM().state) || {}, i = l.findIndex(x => x.id === st.open);
    if (i >= 0 && l.length === 1) return CM().close();
    CM().open(l[(i + 1) % l.length].id);
  }
  // the open threads by the tree's row key (the thing's id, «<object id>/<layer path>» for a layer), newest first
  function byKey(all) {
    const m = new Map();
    for (const th of threads()) {
      if ((!all && th.resolved) || !th.anchor.part) continue; const k = keyOf(th.anchor.part);
      if (!m.has(k)) m.set(k, []); m.get(k).push(th);
    }
    for (const l of m.values()) l.sort((a, b) => String(b.updated || "").localeCompare(String(a.updated || "")));
    return m;
  }
  let rowsBusy = false;
  function rows() {
    const L2 = lib(); if (!L2) return; rowsBusy = true;
    try {
      const m = byKey();
      for (const r of trEl.querySelectorAll(".row[data-k]")) {
        const l = m.get(r.dataset.k), n = l ? l.length : 0, had = r.querySelector(":scope [data-ann-n]");
        if (had && String(n) === had.getAttribute("count")) continue;
        if (had) had.remove(); if (!n) continue;
        const nm = r.querySelector(".nm"); if (!nm) continue;
        nm.insertAdjacentHTML("afterend", L2.count(n, t("Open annotations: {n}, a click opens them", { n })));
      }
    } finally { rowsBusy = false; }
  }
  const tmo = new MutationObserver(() => { if (!rowsBusy) { rows(); counts(); } }); tmo.observe(trEl, { childList: true, subtree: true });   // counts: S-62
  function counts() {
    const d = doc(), nL = (d.objects || []).length + (d.lights || []).length + (d.cameras || []).length, nA = threads().filter(x => !x.resolved).length;
    const [a, b] = tabs.querySelectorAll("em"); a.textContent = nL || ""; b.textContent = nA || "";
  }
  function paneDraw() {
    counts(); if (A.tab !== "ann" || !AL) return; AL.draw();
  }

  // threads added, answered, resolved or gone (ui/comments.js «hy-comments»): the counts, the tab, the pins
  const changed = () => {
    nodes.clear();
    A.sig = threads().map(x => x.id + (x.resolved ? "r" : "") + x.messages.length).join("|");
    if (A.draft && !(CM() && CM().state && CM().state.draft)) A.draft = null;
    rows(); paneDraw(); key = "";
  };
  addEventListener("hy-comments", changed, on);
  addEventListener("hy-comment-open", () => { paneDraw(); key = ""; }, on);
  // the picked thing changes the field's words and «This layer»
  let selWas = null; const selT = setInterval(() => { if (L.sel !== selWas) { selWas = L.sel; if (A.tab === "ann") paneDraw(); } }, 250);
  L.ac.signal.addEventListener("abort", () => clearInterval(selT));

  // ---- keys and the end -----------------------------------------------------------------------------------------------------------------
  function keyDown(e) {
    const k = (e.key || "").toLowerCase(), mod = e.metaKey || e.ctrlKey;
    if (e.key === "Escape" && A.tool) { e.preventDefault(); setTool(false); return true; }
    if (!mod && !e.altKey && !e.shiftKey && (k === "c" || k === "с")) { e.preventDefault(); setTool(!A.tool); return true; }
    return false;
  }
  // Save: each thread on a part takes its pin's place on the card's picture as it is now (op place, no event), so the board shows it there
  async function settle() {
    if (!window.hyAnnot) return;
    const r = rect(), jobs = [];
    for (const th of threads()) {
      const p = th.anchor.part; if (!p) continue;
      const q = placeOf(th); if (!q) continue;
      const at = shareOf(q.pin).map(v => Math.round(Math.max(0, Math.min(1, v)) * 1e5) / 1e5);
      const area = q.box ? [(q.box.x - r.left) / r.width, (q.box.y - r.top) / r.height, q.box.w / r.width, q.box.h / r.height].map(v => Math.round(v * 1e5) / 1e5) : undefined;
      if (Math.abs(at[0] - th.at[0]) < 2e-3 && Math.abs(at[1] - th.at[1]) < 2e-3) continue;
      jobs.push(hyAnnot.api("/api/comments", { op: "place", name: th.page || page(), id: th.id, at, ...(area ? { area } : {}) }).catch(() => {}));
    }
    if (jobs.length) { await Promise.all(jobs); if (CM()) CM().load(); }
  }
  // the threads whose part is not in the scene that stays (a cube added and then Cancel, an object deleted and saved): tied to the card
  // itself from now on, at the place their pin had (P4 S-16, П4 audit 2026-10-10: a thread was tied to a thing that no longer existed)
  function reanchor(d) {
    if (!window.hyAnnot || !d) return;
    const ids = new Set([...(d.objects || []), ...(d.lights || []), ...(d.cameras || [])].map(x => x.id));
    for (const th of threads()) {
      const p = th.anchor.part; if (!p || ids.has(p.id)) continue;
      const { part, ...rest } = th.anchor;
      hyAnnot.api("/api/comments", { op: "move", name: th.page || page(), id: th.id, anchor: rest, at: th.at }).then(() => CM() && CM().load()).catch(() => {});
    }
  }
  function dispose(keep, final) {
    if (keep) settle(); reanchor(final);
    cancelAnimationFrame(raf); tmo.disconnect(); setTool(false);
    if (CM() && CM().state && CM().state.draft && A.draft) CM().close();
    if (L.redraw && redraw0) L.redraw = redraw0;
    if (P) P.destroy(); P = null; style.remove(); tabs.remove(); if (AL) AL.destroy(); pane.remove(); btn.remove(); left.classList.remove("m3annon");
    if (CUR === api) { CUR = null; if (CM() && CM().bounds) CM().bounds(null); }
    if (CM() && CM().draw) CM().draw();
  }
  const api = { id: L.id, boardAt, key: keyDown, dispose, rows, setTool, get tool() { return A.tool; }, showTab, draw };
  CUR = api; hookBoard(); changed(); counts();
  // the open thread stays in the free part of the board, off the Studio's side panels (Hyimg ui/bars.js)
  const inset = () => parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--inset")) || 0;
  if (CM() && CM().bounds) CM().bounds(() => (window.hyBars && hyBars.free ? hyBars.free(HY.stage, inset()) : null));
  return api;
}
const CSS_ESC = s => (window.CSS && CSS.escape ? CSS.escape(s) : String(s).replace(/"/g, '\\"'));
