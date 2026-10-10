// Hyimg 3D, the engine: three.js, the scene and the editor, loaded by canvas.js only when needed (a double click, a card the picture
// cache has nothing for, a scene changed by an agent). A double click opens the editor: drag turns the camera around the scene, a click
// picks an object, a second click a layer of it, V G R S T pick, move, turn, scale and pull. Panels at the edges of the window: the
// layer tree, the settings (DialKit), the tools, the axes. «Снимок» (P) saves the view with its layers for an image model: the plain
// view, a colour per object (masks) and depth, all with a json.
//
// The scene lives in the library as 3d/scenes/<name>/scene.json (format in scene.js): the canvas writes it, an agent applies it in
// Blender or exports a .blend into it with blender/hyimg_scene.py. Nothing drives Blender from here (owner: the data is enough).
// The card on the board: {type: "model3d", scene: <scene.json path>, camera: <camera id>, x, y, w, h}. Older cards {model, cam, colors}
// are shown through the same scene maths and become a scene file when first opened.
import * as THREE from "./vendor/three/build/three.module.js";
import { OrbitControls } from "./vendor/three/examples/jsm/controls/OrbitControls.js";
import { TransformControls } from "./vendor/three/examples/jsm/controls/TransformControls.js";
import { SceneView, newDoc, tidy, stateKey, toV, fromV, look, lensFor, cameraBack, readBack, newId, ensureAssembled, MASKS, fileUrl, heavyText, layerPath, modelHeight, loadGLB, LIMITS } from "./scene.js";
import { readChosen, loadObject, toGlb, digest, extOf, stemOf, isCad, cadGlb } from "./loaders.js";   // a 3D file of any format into a scene (owner 2026-10-06)
import { createDialKit, createDialRoot } from "./vendor/dialkit/index.js";   // DialKit 2.0.2 (MIT, Josh Puckett): the inspector's controls
import { setT as sceneWords } from "./scene.js";
import { translator } from "./lang.js";   // English or Russian, as the board is set (owner 2026-10-06)
import { attachBlender, studioAngle, bridgeApi } from "./blender.js";   // a studio's scene in Blender: three.js · EEVEE · Cycles and «Render» on a plate at the card (owner 2026-10-06)
import { initHistory, itemFields, remember, settle, undo, undoState, historyTab, shotTaken } from "./history.js";   // ⌘Z, ↶ ↷ and History (2026-10-07)
import { initTools, tools } from "./tools.js";   // each tool its own drag, the camera on ⌥ and the middle button, the view on Space (2026-10-10)
import { initView, viewOf, putVersion, askCancel, cancelled, changedSince, originalCamera, syncCamera, sharedKey } from "./view.js";   // the card's view, Save, Cancel
import { writeScene, writeUi, openingBoard, boardDiffers } from "./view.js";   // Save waits for the file, Cancel keeps others' work (P4 2026-10-10)
import { layout as layoutSecs, drag as dragSecs, fold as foldSecs, reset as resetSecs } from "./sections.js";   // the layer list's sections as one stack
import { outSize, atLong, keepShape, ratioKey, reshape, PRESETS } from "./frame.js";   // the card's frame and output size, set in the Scene panel
import { drawFrame, warmGhost } from "./ghost.js";   // the frame with its highlight: the pick seen whole through what is in front of it (2026-10-07)
import { lightPane as lightPaneOf } from "./lights.js";   // a light's panel, its temperature and softness (2026-10-07)
import { attachLook } from "./variants.js";   // «Свет и материалы»: the card's variant of light and materials, A/B (owner 2026-10-07)
import { outlinerMicro, camLed, scrubSize, oneLine, holdText } from "./micro.js";   // round 15's micro UI, round 16's scrub (owner 2026-10-09/10), one-line fields
import { sizeKeys, searchKeys, treeRename } from "./fields.js";   // Esc, ↵, Tab by Hyimg's one rule in W and H, the search, a row's rename (P4 2026-10-10)
import { attachAnn } from "./annot.js"; import { studioDock } from "./dock.js";   // annotations tied to the scene's objects and layers, pins in the view (owner 2026-10-09, round 15)

const TYPE = "model3d";
const SHOTS = "3d/shots";
const SCENES = "3d/scenes";
const INBOX = "3d/scenes/inbox.json";
// the project's models (3d/models/<id>/model.json) come from this plugin's server route (models.py), asked when «+» opens
const PLUGIN = (new URL(import.meta.url).pathname.match(/\/plugins\/([^/]+)\//) || [])[1] || "3d";
async function projectModels() {
  try {
    const r = await fetch(`/api/plugin/${encodeURIComponent(PLUGIN)}/models`, { method: "POST", body: "{}" });
    return r.ok ? ((await r.json()).models || []) : [];
  } catch (e) { return []; }
}
// names in English, shown through t() (lang.js)
const ADD = [
  ["box", "Cube"], ["cylinder", "Cylinder"], ["sphere", "Sphere"], ["plane", "Plane"],
  ["area", "Area light"], ["spot", "Spotlight"], ["point", "Point light"], ["sun", "Sun"], ["camera", "Camera"],
];
const PRIM = { box: [0.1, 0.1, 0.1], cylinder: [0.08, 0.08, 0.2], sphere: [0.08, 0.08, 0.08], plane: [0.5, 0.5, 0] };
const LIGHT_W = { area: 20, spot: 30, point: 10, sun: 3 };
const LIGHT_NAMES = { area: "Area light", spot: "Spotlight", point: "Point light", sun: "Sun" };   // through t()
const SLOW_MS = 120, STOP_MS = 300, POSTER_SLOW_MS = 1200;   // a frame of the editor: lower the quality, then stop and ask; a poster: refresh rarely
// the frame of a card: free, or locked to a ratio (width:height); the same choice as the bar the canvas shows over the card
const RATIOS = ["1:1", "4:5", "5:4", "3:4", "4:3", "2:3", "3:2", "9:16", "16:9"];   // with t("Free") first in the list

let HY, renderer;
// the interface's words (owner 2026-10-06: «make 2 versions, Russian and English»): t is the plugin's (lang.js), K the labels of the
// inspector's controls. DialKit shows a control's key as its label, so the panels' values are keyed by these words of the page's language
// (a change of language reloads the page; nothing stores DialKit's values, the pull tool's settings are prefs m3.pull.*)
let t = k => k, K = {};
const LABELS = { pos: "Location, cm", rot: "Rotation, °", dist: "Distance, cm", az: "Azimuth, °", inc: "Inclination, °", roll: "Twist, °",
  sensor: "Sensor, mm", fit: "Sensor fit", shiftX: "Shift X", shiftY: "Shift Y", near: "Clip start, cm", far: "Clip end, m", reset: "Reset",
  color: "Color", material: "Material", visible: "Visible", resetLayer: "Reset layer", name: "Name", size: "Size, cm", diam: "Diameter",
  height: "Height", scale: "Scale, %", shadow: "Shadow only", gen: "For generation", mask: "Mask", ai: "Prompt", del: "Delete", source: "Source",
  type: "Type", cone: "Cone, °", coords: "Coordinates", move: "Move", lens: "Lens, mm", campos: "Camera position", cammore: "Camera: more",
  showcard: "Make active", camera: "Camera", frame: "Frame", dolly: "Wide ↔ isometric", bg: "Background", transparent: "Transparent",
  transparency: "Transparency, %", world: "World light", strength: "Strength", highlight: "Selection highlight", pull: "Pull tool",
  pivot: "Pivot", gel: "Viscosity", newcam: "New camera from this view", allcams: "All cameras onto the canvas", original: "Original camera", syncscene: "Sync with the scene" };
const SC = new Map();     // scene path -> {view, doc, raw, key, saving, timer}
let live = null;          // the card being edited

function ensureRenderer() {
  if (renderer) return renderer;
  // alpha: a card can be see-through; stencil: the pick's ghost (ghost.js)
  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true, stencil: true });
  renderer.setPixelRatio(1); renderer.outputColorSpace = THREE.SRGBColorSpace; renderer.toneMapping = THREE.AgXToneMapping;
  renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  // the graphics card dropped the context (too much memory): everything waits, nothing is redrawn until it comes back
  renderer.domElement.addEventListener("webglcontextlost", e => { e.preventDefault(); HY.toast(t("3D: the graphics card dropped the scenes, waiting for it")); if (live) pause(live, 0, t("The graphics card dropped the scene.")); });
  renderer.domElement.addEventListener("webglcontextrestored", () => { for (const e of SC.values()) e.view.envKey = ""; for (const p of SC.keys()) repaint(p, true); });
  return renderer;
}
// scenes load one after another, so opening a board full of 3D cards does not load them all at once
let chain = Promise.resolve();
const queued = fn => { const p = chain.then(fn, fn); chain = p.catch(() => {}); return p; };

// ---- scene files
async function entry(path, doc) {
  let e = SC.get(path);
  if (!e) { e = { view: new SceneView(path, ensureRenderer()), doc: null, raw: "", key: "", ready: null }; SC.set(path, e); }
  if (doc) { e.doc = doc; e.ready = queued(() => e.view.apply(doc)); }
  else if (!e.ready) e.ready = queued(() => refresh(path));
  await e.ready; return e;
}
async function refresh(path) {
  const e = SC.get(path); if (path.startsWith("legacy:")) return false;
  const r = await fetch(fileUrl(path) + `&t=${Date.now()}`, { cache: "no-store" });
  if (!r.ok) throw new Error(t("no scene file {path}", { path }));
  const raw = await r.text(); if (raw === e.raw || e.timer) return false;   // an edit waiting to be saved wins
  const doc = JSON.parse(raw); if (e.doc && (doc.rev || 0) < (e.doc.rev || 0)) return false;   // read before our last write landed: older
  e.raw = raw; e.doc = doc; e.key = stateKey(e.doc); await e.view.apply(e.doc);
  return true;
}
// the canvas writes only on a real change: what Blender or an agent wrote is not written back unchanged
function save(path, now, force) {
  const e = SC.get(path); if (!e || path.startsWith("legacy:")) return;
  // the studio writes its scene on «Save» only (owner 2026-10-07: Cancel leaves scene.json as it was, nothing written meanwhile)
  if (!force && live && live.path === path) return;
  clearTimeout(e.timer); e.timer = null;
  if (!now) { e.timer = setTimeout(() => save(path, true), 300); return; }
  tidy(e.doc); const key = stateKey(e.doc); if (key === e.key) return;
  e.doc.rev = (e.doc.rev || 0) + 1; e.doc.by = "canvas"; e.doc.t = new Date().toISOString().slice(0, 19).replace("T", " ");
  const raw = JSON.stringify(e.doc, null, 1); e.key = key; e.raw = raw;
  return fetch(`/api/file?p=${encodeURIComponent(path)}`, { method: "POST", body: raw }).then(async r => { if (!r.ok) HY.toast(t("Scene not saved: {e}", { e: await r.text() })); return r.ok; });
}
const scenePath = () => `${SCENES}/${new Date().toISOString().slice(2, 19).replace(/[-:]/g, "").replace("T", "-")}/scene.json`;

// an older card (one model, an orbit camera in the model's units) as a scene in memory
function legacyDoc(it) {
  const doc = newDoc(it.w / it.h, it.model ? { id: it.model, height_m: 0.1634 } : null), H = 0.1634, k = H / 3.38, c = Object.assign({ az: -32, el: 14, dist: 9.5, fov: 24, tx: 0, ty: 0, tz: 0 }, it.cam || {});
  const az = c.az * Math.PI / 180, el = c.el * Math.PI / 180, lift = new THREE.Vector3(0, H / 2, 0);
  const P = new THREE.Vector3(c.tx + c.dist * Math.cos(el) * Math.sin(az), c.ty + c.dist * Math.sin(el), c.tz + c.dist * Math.cos(el) * Math.cos(az)).multiplyScalar(k).add(lift);
  const T = new THREE.Vector3(c.tx, c.ty, c.tz).multiplyScalar(k).add(lift), cam = doc.cameras[0];
  cam.loc = fromV(P); cam.rot = look(cam.loc, fromV(T)); cam.lens = +lensFor(c.fov, cam, it.w / it.h).toFixed(2);
  const colors = {}; for (const [key, v] of Object.entries(it.colors || {})) { const role = key.split("/")[0]; if (!colors[role]) colors[role] = v; }
  if (Object.keys(colors).length) doc.objects[0].colors = colors;
  return tidy(doc);
}
const keyOf = (id, it) => it.scene || `legacy:${id}`;
async function entryOf(id, it) { const p = keyOf(id, it); return p.startsWith("legacy:") && !SC.has(p) ? entry(p, legacyDoc(it)) : entry(p); }

// ---- the card at rest: the view of its camera as a picture
// the card's still view, drawn with three.js when canvas.js finds the project's still missing or older than the scene; dest {path, ext}
// is where it goes (<scene>/.posters/<card>-<view>.<ext>), so the next page load and anyone opening the project show it without this engine
// The base scene of a card that has no file yet (owner 2026-10-06: «with the dark background it is simply invisible on the dark board; maybe add a
// preview of the base scene, a landscape with a gradient as usual in 3D mode»): the stand-in on its floor under the key and fill lights, with a
// vertical gradient behind them, so it reads on a dark board; the card's own still, drawn once like any other and kept in the scene's .posters.
let BACKDROP = null;
function backdrop() {
  if (BACKDROP) return BACKDROP;
  const c = document.createElement("canvas"); c.width = 4; c.height = 256; const g = c.getContext("2d"), grad = g.createLinearGradient(0, 0, 0, 256);
  grad.addColorStop(0, "#3d4455"); grad.addColorStop(0.55, "#7d8696"); grad.addColorStop(1, "#b9bfca");
  g.fillStyle = grad; g.fillRect(0, 0, 4, 256);
  BACKDROP = new THREE.CanvasTexture(c); BACKDROP.colorSpace = THREE.SRGBColorSpace; return BACKDROP;
}
export function renderPoster(el, it, id, dest) {
  const img = el.querySelector("img.m3"), badge = el.querySelector(".b3"); if (!img) return;
  if (!img.src) badge.textContent = t("3D · loading");
  entryOf(id, it).then(e => {
    if (live && live.id === id) return;
    const old = el.querySelector(".h3"); if (old) old.remove();
    const s = Math.min(2, 900 / Math.max(it.w, it.h)), pw = Math.round(it.w * s), ph = Math.round(it.h * s);
    const cam = e.view.camera(it.camera || e.doc.active_camera, pw, ph, it.view); cam.layers.set(0);   // the card's own view wins (item.view)
    const bg = it.bg, see = bg && (bg.transparent || (bg.opacity ?? 100) < 100);
    const t0 = performance.now(), hid = hideEditor(e), plain = e.view.scene.background;
    if (it.empty && !bg) e.view.scene.background = backdrop();   // the base scene's backdrop (the editor's own world colour is not touched)
    try { e.view.render(cam, pw, ph, "beauty", bg); } finally { e.view.scene.background = plain; hid(); }
    const shot = see ? renderer.domElement.toDataURL("image/png") : renderer.domElement.toDataURL("image/jpeg", 0.9);   // a see-through card keeps its alpha
    img.src = shot; img._u = "";   // canvas.js shows the written file from now on
    // the file is made from this same picture, taken now: toBlob reads the canvas later in WebKit, by then the shared renderer has drawn
    // the next card at another size, and the file came out black (owner 2026-10-04: two black cards on «phonerefs»)
    if (dest) fetch(shot).then(r => r.blob())
      .then(b => fetch(`/api/file?p=${encodeURIComponent(dest.path)}`, { method: "POST", body: b }))
      .then(r => r.ok ? r.json() : null).then(res => { if (res) H.posted(dest.path, res.mtime); }).catch(() => {});
    e.posterMs = performance.now() - t0; e.posterAt = Date.now(); badge.textContent = "3D";
    if (live) live.redraw();   // the renderer is shared: the card being edited gets its view back
  }).catch(err => {
    if (err.heavy) return heavyCard(el, it, id, err);
    badge.textContent = "3D ⚠"; el.title = t("scene did not load: {e}", { e: err.message }); console.error(err);
  });
}
// a scene over the limits waits on its card for a yes
function heavyCard(el, it, id, err) {
  el.querySelector(".b3").textContent = "3D ⏸";
  if (el.querySelector(".h3")) return;
  const d = document.createElement("div"); d.className = "h3";
  d.innerHTML = `<div>${heavyText(err.heavy)[0].toUpperCase() + heavyText(err.heavy).slice(1)}. ${t("The computer may freeze.")}</div><button>${t("Load")}</button>`;
  d.addEventListener("pointerdown", e => e.stopPropagation());
  d.querySelector("button").onclick = () => { allow(keyOf(id, it)); d.remove(); };
  el.appendChild(d);
}
function allow(path) { const e = SC.get(path); if (!e) return; e.view.allow = true; e.ready = null; e.raw = ""; repaint(path, true); }
function hideEditor(e) {
  if (!live || live.e !== e) return () => {};
  const h = live.tc.getHelper(); h.visible = false; e.view.helpers.visible = false;
  return () => { h.visible = true; e.view.helpers.visible = true; };
}
function repaint(path, force) {
  const e = SC.get(path);   // a scene that draws slowly is redrawn on its cards at most every 20 s
  if (!force && e && e.posterMs > POSTER_SLOW_MS && Date.now() - (e.posterAt || 0) < 20000) {   // later, once
    if (!e.later) e.later = setTimeout(() => { e.later = null; repaint(path, true); }, 20000 - (Date.now() - e.posterAt));
    return;
  }
  for (const el of document.querySelectorAll(`.plg[data-type=${TYPE}]`)) {
    const it = HY.board.items[el.dataset.id]; if (it && keyOf(el.dataset.id, it) === path) H.poster(el, it, el.dataset.id, e && e.doc, force);
  }
}

// canvas.js watches the scene files and inbox.json; the engine refreshes what it has loaded and places cards
export async function refreshScene(path) {
  if (!SC.has(path) || (live && live.path === path && live.busy)) return false;
  const changed = await refresh(path); if (changed && live && live.path === path) live.reload();
  return changed;
}
export async function placeCardsFor(path, ids) { const e = await entry(path); return placeCards(path, e, ids); }
export const isLive = id => !!live && (id === undefined || live.id === id);
export const liveUnsaved = () => !!live && changedSince(live);   // a browser asks before it unloads it (Hyimg ui/modes.js unsaved)
export const histInfo = () => live && { hi: live.hi, steps: live.hist.map(h => h.label), pressed: live.pressed, waiting: !!live.hmT || !!live.hmWhat };   // for the tests
// for the tests: which tool the editor is in, what its gizmo does, what is picked and what is under the mouse
const nameOf = n => n ? (n.userData.id || n.name || true) : null;
export const liveInfo = () => live && { id: live.id, tool: live.tool, mode: live.tc.mode, attached: !!live.tc.object, selected: nameOf(live.sel), hovered: nameOf(live.hov) };
export const livePath = () => live ? live.path : null;
// for the tests and a selection of many to come: the objects, lights or layers with these ids (a unit's id, or a node's name) are the
// view's pick, the first one the panels'; and one frame of the editor drawn now, its time in ms
export function liveSelect(ids) {
  if (!live) return; const L = live, ns = [];
  for (const k of ids) {
    const u = L.view.units.get(k); let n = u ? u.obj : null;
    if (!n) L.view.scene.traverse(x => { if (!n && x.name === k) n = x; });
    if (n) ns.push(n);
  }
  pick(L, ns[0] || null, true); L.multi = ns.length > 1 ? ns : null; L.need();
}
export const liveFrame = () => { if (!live || !live.redraw) return null; const t0 = performance.now(); live.redraw(); return performance.now() - t0; };
export const docOf = path => { const e = SC.get(path); return e && e.doc; };
async function placeCards(path, e, ids) {
  const have = new Set(Object.values(HY.board.items).filter(it => it.type === TYPE && it.scene === path).map(it => it.camera));
  const todo = ids.filter(c => !have.has(c) && e.doc.cameras.some(x => x.id === c)); if (!todo.length) return [];
  const r = e.doc.render || { x: 1600, y: 2000 }, w = 420, h = Math.round(w * r.y / r.x), c = HY.viewCenter(), before = HY.snap(), out = [];
  todo.forEach((cam, i) => { const id = HY.uid("m"); HY.board.items[id] = { type: TYPE, scene: path, camera: cam, view: viewOf(e.doc.cameras.find(x => x.id === cam)), x: Math.round(c.x - (todo.length * (w + 40)) / 2 + i * (w + 40)), y: Math.round(c.y - h / 2), w, h }; out.push(id); });   // its own view from the start
  if (live && live.path === path) out.forEach(x => live.made.add(x));   // the studio's own: its Cancel takes them away (view.js openingBoard)
  HY.commit(before, todo.length === 1 ? t("3D: camera card") : t("3D: {n} camera cards", { n: todo.length })); HY.select(out);
  return out;
}

// ---- the editor (owner 2026-10-03, after the demo «Hyimg 3D Studio»): the layers of the real files on the left, tabs on the right
// (Объект, Свет, Камера, Фон) built with DialKit, tools under the card. The mouse stays an arrow. The pick and what is under the mouse
// show whole through what stands in front of them, without an outline (ghost.js, owner 2026-10-07); the Scene panel's «Selection
// highlight» can bring back the pink outline (the pick outlined, the hover filled). A click picks an object, a click inside the picked
// object picks the layer under the mouse; Esc climbs back up.

// the app's shared interface pieces, from Hyimg's review/ui (owner 2026-10-06: one UI system): the one slider (DialKit's sliders are drawn by
// it), the editors' one icon family (icons.js), the one section splitter (split.js) and Photoshop's eye drag (eyedrag.js). An older
// Hyimg without one keeps the plugin's own (without the eye drag, a click switches one row).
const UI_JS = { slider: () => window.hySlider, icons: () => window.HY_TOOL_IC, split: () => window.hySplit, eyedrag: () => window.hyEyeDrag };
const loadUI = name => UI_JS[name]() ? Promise.resolve() : (loadUI[name] = loadUI[name] || new Promise(ok => { const s = document.createElement("script"); s.src = `/ui/${name}.js`; s.onload = s.onerror = () => ok(); document.head.appendChild(s); }));
async function goLive(id) {
  await Promise.all(Object.keys(UI_JS).map(loadUI));
  if (live) { await stopLive(); if (live) return; }   // the open one saves first; refused, it stays open (P4 S-04)
  let it = HY.board.items[id]; const el0 = [...document.querySelectorAll(".plg")].find(x => x.dataset.id === id); if (!it || !el0) return;
  try { await entryOf(id, it); } catch (err) { if (err.heavy) HY.toast(t("3D: {why}. First “Load” on the card", { why: heavyText(err.heavy) })); else HY.toast("3D: " + err.message); return; }
  if (!it.scene) {   // an older card becomes a scene file
    const doc = legacyDoc(it), path = scenePath(), before = HY.snap();
    const e = await entry(path, doc); e.raw = ""; e.key = ""; save(path, true);
    Object.assign(it, { scene: path, camera: doc.active_camera }); delete it.model; delete it.cam; delete it.colors; SC.delete(`legacy:${id}`);
    HY.commit(before, t("3D: scene saved to {path}", { path }));
  }
  it = HY.board.items[id]; delete it.empty;   // the person builds the scene by hand: the card does not ask for a file any more
  const el = [...document.querySelectorAll(".plg")].find(x => x.dataset.id === id), path = it.scene, e = await entry(path), view = e.view;
  // the card is the truth for its view (owner 2026-10-07: «board был source of truth»): the studio opens on the card's camera (item.view),
  // put into the scene in memory only; the file as it was is kept for «Cancel» and the scene's versions
  const sceneOpen = clone(e.doc), rawOpen = await fetch(fileUrl(path) + `&t=${Date.now()}`, { cache: "no-store" }).then(r => r.ok ? r.text() : null).catch(() => null);
  { const cid0 = it.camera || e.doc.active_camera; if (it.view && cid0) { e.doc.cameras = e.doc.cameras || []; let c = e.doc.cameras.find(x => x.id === cid0);
    if (!c) e.doc.cameras.push(c = { id: cid0 }); Object.assign(c, clone(it.view)); await view.apply(e.doc); } }
  // each model of the scene gets its one-file copy for Blender (3d/models/<id>/assembled.glb), also when an agent put it in the file
  for (const m of new Set(e.doc.objects.filter(o => o.src && o.src.type === "model").map(o => o.src.model))) ensureAssembled(m).catch(() => {});
  ensureRenderer(); el.classList.add("plg-live"); document.body.classList.add("m3edit");
  if (HY.full) HY.full(true);   // the library folds while the editor is open (owner 2026-10-03), it comes back on «Готово»
  const cvs = renderer.domElement; cvs.className = "m3live"; cvs.style.zIndex = ""; el.appendChild(cvs);
  const cam = new THREE.PerspectiveCamera(); cam.layers.enable(1);
  const orbit = new OrbitControls(cam, cvs); orbit.enableDamping = false; orbit.screenSpacePanning = true; orbit.zoomSpeed = 0.6;
  const tc = new TransformControls(cam, cvs); tc.setSize(0.8); view.scene.add(tc.getHelper());
  // the editor's canvas is one for every session: its listeners belong to this session and go with it (2026-10-04: after a second
  // opening a pull ran twice, two strings and a double turn, and an old session's pick drew a second panel)
  const ac = new AbortController(), on = { signal: ac.signal };
  const startDoc = tidy(JSON.parse(JSON.stringify(e.doc)));   // what «Сбросить» takes things back to: the scene and the card at the opening
  live = { id, el, e, path, view, cam, orbit, tc, ac, on, start: { doc: startDoc, key: stateKey(noUi(startDoc)), item: JSON.parse(JSON.stringify(HY.board.items[id])) }, sel: null, hov: null, tool: "select", hl: HY.pref("m3.hl", "ghost"), open: new Set(), raw: false, tab: 0, kit: null,
    sceneOpen, rawOpen, icons: new Map(), before: HY.snap(), mark: HY.steps ?? -1, made: new Set(), hist: [], hi: -1, pressed: false, busy: false, scale: 1, times: [], paused: false, allowSlow: false };
  const L = live, camId = () => HY.board.items[id].camera || e.doc.active_camera;
  L.camId = camId;

  // the editor camera is the card's camera: turning it moves the scene camera, as in Blender's camera view
  const syncCam = () => {
    const sc = view.camera(camId(), el.clientWidth || 400, el.clientHeight || 500);
    cam.position.copy(sc.position); cam.quaternion.copy(sc.quaternion); cam.fov = sc.fov; cam.near = sc.near; cam.far = sc.far;
    if (sc.view) cam.setViewOffset(sc.view.fullWidth, sc.view.fullHeight, sc.view.offsetX, sc.view.offsetY, sc.view.width, sc.view.height); else cam.clearViewOffset();
    const b = view.bounds, ctr = b.getCenter(new THREE.Vector3()), f = new THREE.Vector3(0, 0, -1).applyQuaternion(cam.quaternion);
    const d = Math.max(0.05, ctr.clone().sub(cam.position).dot(f)), T = cam.position.clone().addScaledVector(f, d);
    // the camera's twist (KeyShot's «Крен»): the orbit control levels the horizon on every move, so the twist is kept apart and put
    // back after each move (2026-10-04: the twist slider did nothing, the control undid it at once)
    const level = new THREE.PerspectiveCamera(); level.position.copy(cam.position); level.lookAt(T);
    const tw = level.quaternion.invert().multiply(sc.quaternion.clone()); L.roll = 2 * Math.atan2(tw.z, tw.w);
    orbit.target.copy(T); orbit.update(); cam.quaternion.copy(sc.quaternion);
  };
  const size = () => { const r = el.getBoundingClientRect(), k = devicePixelRatio * L.scale, W = Math.max(64, Math.round(r.width * k)), H = Math.max(64, Math.round(r.height * k)); cam.aspect = W / H; cam.updateProjectionMatrix(); return [W, H]; };
  const px = new Uint8Array(4);
  L.redraw = () => {
    if (L.paused || live !== L) return;
    const [W, H] = size(), t0 = performance.now(), progs = renderer.info.programs.length; updateHelpers(L);
    // with the interface hidden (⌘.) the view is the picture alone: no pink pick or hover marks, no gizmo, no light and camera icons
    // (owner 2026-10-06: the model flashed pink on ⌘)
    drawFrame(renderer, L, W, H, HY.board.items[id].bg, document.documentElement.classList.contains("hy-hideui"));
    if (L.ui) L.ui.axes();
    const gl = renderer.getContext(); gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px);   // waits for the frame, so the time is the real one
    // a frame that built shaders (the first of a material, of the ghost) is no measure of the scene
    if (renderer.info.programs.length === progs) guard(L, performance.now() - t0);
    if (HY.drawn) HY.drawn(el);   // the board's looks follow each frame (the card's colour grade, canvas.js surface), out of the frame's timing
  };
  let rq = 0; L.need = () => { if (!rq) rq = requestAnimationFrame(() => { rq = 0; L.redraw(); }); };
  // after the file changed (undo, an agent's export): the camera, the icons, the pick if it still exists, the panels
  L.reload = () => { syncCam(); helpers(L); if (L.sel && !inScene(L.sel)) L.sel = null; if (L.hov && !inScene(L.hov)) L.hov = null; attach(L); L.ui.tree(); L.ui.panel(); L.redraw(); };
  L.changed = (what, immediate) => { save(path, immediate); remember(L, what); };
  // one gesture is one step (owner 2026-10-07: ⌘Z in the studio): while a button is down (a slider dragged, the camera turned, an object
  // moved) the changes wait, the step is taken when it is let go
  document.addEventListener("pointerdown", () => { L.pressed = true; }, { capture: true, signal: ac.signal });
  const letGo = () => { if (!L.pressed) return; L.pressed = false; if (L.hmWhat) { const w = L.hmWhat; L.hmWhat = null; remember(L, w); } };
  for (const ev of ["pointerup", "pointercancel"]) addEventListener(ev, letGo, { capture: true, signal: ac.signal });
  L.rsI = setInterval(() => resetState(L), 400);   // the reset buttons follow every change, also while a slow editor is paused
  L.recam = () => { syncCam(); L.redraw(); };
  L.ui = buildUI(L);
  try { L.look = attachLook(L, { HY, t, api: bridgeApi(PLUGIN) }); } catch (err) { console.error(err); }   // a studio's scene: light and materials
  try { L.ann = attachAnn(L, { HY, t, THREE, unitOf, head, pick: n => pick(L, n, true), esc, ico }); } catch (err) { console.error(err); }   // annot.js
  try { L.blender = attachBlender(L, { HY, t, plugin: PLUGIN }); } catch (err) { console.error(err); }   // only a scene with scene.studio gets it
  L.bimg = el.querySelector(":scope > img.m3bimg");   // Blender's frame, when it is shown the view draws only the ghost over it
  if (L.bimg) {
    new MutationObserver(() => L.need()).observe(L.bimg, { attributes: true, attributeFilter: ["hidden", "src"] });
    L.bimg.addEventListener("load", () => L.need(), L.on);
  }
  syncCam(); helpers(L); L.redraw(); remember(L, "start"); warmGhost(renderer, view, cam);
  L.ui.panel();   // the panel again now that the camera stands where it should (2026-10-04: «Положение камеры» showed 1 cm and zeros)
  HY.render();   // the board draws the frame bar and the edge handles of a card in its editor
  orbit.addEventListener("change", () => { if (L.roll) cam.quaternion.multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 0, 1), L.roll)); cameraBack(e.doc, camId(), cam); L.need(); save(path); });
  orbit.addEventListener("end", () => { remember(L, "camera"); const k = picked(L).kind; if (!k || k === "camera") L.ui.panel(); });   // the camera's numbers follow the mouse
  tc.addEventListener("dragging-changed", ev => { orbit.enabled = !ev.value; L.busy = ev.value; if (!ev.value) { view.bounds = view.meshBounds(); view.placeSuns(); L.changed("move", true); } });
  tc.addEventListener("objectChange", () => { const u = unitOf(L.sel); if (u) { readBack(view, u.userData.id); view.placeSuns(); L.need(); save(path); L.ui.sync(); } });

  // hover tints what the next click picks; a click picks the object, a click inside the picked object picks the layer under the mouse
  const ray = new THREE.Raycaster(); ray.layers.enableAll();
  const hit = ev => {
    const r = cvs.getBoundingClientRect();
    ray.setFromCamera(new THREE.Vector2(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1), cam);
    const locked = id => { const x = findAny(e.doc, id); return x && x.locked; };   // a locked thing is not picked in the frame, only in the tree
    const targets = [...L.icons.values()].filter(m => m.visible && !locked(m.userData.light || m.userData.cam));
    for (const [uid, u] of view.units) if (u.kind === "object" && u.obj.visible && !locked(uid)) u.obj.traverseVisible(m => { if (m.isMesh) targets.push(m); });
    const h = ray.intersectObjects(targets, false)[0]; if (!h) return null;
    const o = h.object;
    if (o.userData.light) return view.units.get(o.userData.light).obj;
    if (o.userData.cam) return o;
    const u = unitOf(o); if (!u) return null;
    return L.sel && (L.sel === u || u.getObjectById(L.sel.id)) ? head(u, o) : u;   // inside the picked object: the layer itself
  };
  let down = null, hovRaf = 0;
  cvs.addEventListener("pointermove", ev => {
    if (ev.buttons || tc.dragging) return;
    cancelAnimationFrame(hovRaf); hovRaf = requestAnimationFrame(() => { const h = hit(ev); if (h !== L.hov) { L.hov = h; L.ui.markTree(); L.need(); } });
  }, L.on);
  cvs.addEventListener("pointerleave", () => { if (L.hov) { L.hov = null; L.ui.markTree(); L.need(); } }, L.on);
  cvs.addEventListener("pointerdown", ev => { down = [ev.clientX, ev.clientY]; }, L.on);
  tools(L, cvs, { hit, ray, pick: n => pick(L, n, true), unitOf, findAny, readBack }); smartMove(L, cvs, ray);   // tools.js first: it decides the drag
  cvs.addEventListener("pointerup", ev => { if (!down || Math.hypot(ev.clientX - down[0], ev.clientY - down[1]) > 4 || tc.dragging) return; pick(L, hit(ev), true); }, L.on);
  for (const ev of ["pointerdown", "dblclick", "wheel"]) L.ui.root.addEventListener(ev, x => x.stopPropagation());
}

const inScene = n => { while (n) { if (n.isScene) return true; n = n.parent; } return false; };
const unitOf = n => { while (n && !(n.userData.id && n.userData.kind)) n = n.parent; return n; };
// a layer is named by its outermost wrapper (the row the tree shows): Sketchfab's root › GLTF_SceneRootNode › … is one row
function head(unit, n) {
  const wrap = unit.children[0];
  if (n === wrap || n === unit) return unit;
  while (n.parent && n.parent !== wrap && n.parent !== unit && !n.parent.isMesh && n.parent.children.length === 1 && !n.parent.userData.label && !n.parent.userData.mirror) n = n.parent;
  return n;
}
// what is picked, in the scene's terms
function picked(L, n = L.sel) {
  if (!n) return { kind: null };
  if (n.userData.cam) return { kind: "camera", id: n.userData.cam, node: n };
  const u = unitOf(n); if (!u) return { kind: null };
  if (u.userData.kind === "light") return { kind: "light", id: u.userData.id, node: u, unit: u };
  return u === n ? { kind: "object", id: u.userData.id, node: n, unit: u } : { kind: "layer", id: u.userData.id, node: n, unit: u, path: layerPath(u, n) };
}
function pick(L, n, reveal) {
  L.sel = n || null; L.lmSel = null;
  if (n && reveal) { let p = n.parent; while (p) { L.open.add(p.uuid); p = p.parent; } }
  attach(L); L.ui.tree(); L.ui.panel(); L.need();
  if (n && reveal) requestAnimationFrame(() => { const r = L.ui.root.querySelector(`[data-u="${n.uuid}"]`); if (r) r.scrollIntoView({ block: "nearest" }); });
}
// «Тянуть» (owner 2026-10-03: «as if a string is tied to the phone and you pull it, in a thick gel»). Ninth version, on the owner's own
// rules (2026-10-04): it only turns, never moves; the pivot is the touched point mirrored through the centre (touched at x 100 y 23 z 70
// from the centre, the pivot is at x −100 y −23 z −70); across the line from the pivot the drag turns it in the picture plane, along the
// line it tilts the touched point toward the camera or away (his pink and blue arrows); and «I pull up and it goes down» must never
// happen. So the touched point stays under the mouse, like a globe turned by a finger: it lies on a sphere round the pivot and goes where
// the ray from the camera through the mouse meets that sphere, on the same side it started on (toward the camera or away). Past the
// sphere's edge it stays on the edge. The turn is counted from the pose at the press, nothing drifts. Touched at the very centre there
// is nothing to turn about. «Ось» «Центр» turns it about its centre instead (its position does not change at all). «Вязкость» is the gel.
const PULL = { gel: 4, pivot: "mirror" };
const PIVOTS = [{ value: "mirror", label: "Mirrored point" }, { value: "center", label: "Center" }];   // labels through t()
function smartMove(L, cvs, ray) {
  let g = null, raf = 0;
  const at = ev => { const r = cvs.getBoundingClientRect(); ray.setFromCamera(new THREE.Vector2(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1), L.cam); };
  cvs.addEventListener("pointerdown", ev => {   // capture: it runs before the camera's own handler, which it switches off for the drag
    if (L.tool !== "smart" || ev.button !== 0 || L.turning) return;
    at(ev);
    const targets = []; for (const [uid, u] of L.view.units) { const x = findAny(L.e.doc, uid); if (u.kind === "object" && u.obj.visible && !(x && x.locked)) u.obj.traverseVisible(m => { if (m.isMesh) targets.push(m); }); }
    const h = ray.intersectObjects(targets, false)[0]; if (!h) return;
    const unit = unitOf(h.object), box = new THREE.Box3().setFromObject(unit), size = box.getSize(new THREE.Vector3()).length() / 2 || 0.05;
    L.orbit.enabled = false; cvs.setPointerCapture(ev.pointerId);
    const n = new THREE.Vector3(); L.cam.getWorldDirection(n);
    const center = box.getCenter(new THREE.Vector3()), reach = Math.max(1e-4, size), toC = center.clone().sub(h.point), r = toC.length();
    const mid = HY.pref("m3.pull.pivot", PULL.pivot) === "center";   // the pivot: the touched point mirrored through the centre, or the centre
    const len = r < 0.02 * reach ? 0 : mid ? r : 2 * r, pivot = len ? (mid ? center.clone() : center.clone().multiplyScalar(2).sub(h.point)) : null;
    // which crossing of the sphere the touched point is: the near one (facing the camera) or the far one
    const R = pivot ? h.point.distanceTo(pivot) : 0, o = L.cam.position.clone(), d0 = h.point.clone().sub(o).normalize();
    let near = true;
    if (pivot) { const oc = pivot.clone().sub(o), b = d0.dot(oc), k = Math.sqrt(Math.max(0, R * R - (oc.lengthSq() - b * b))), t = h.point.distanceTo(o); near = Math.abs(t - (b - k)) <= Math.abs(t - (b + k)); }
    g = { unit, pL: unit.worldToLocal(h.point.clone()), pivot, len, R, near, a0: pivot && h.point.clone().sub(pivot).normalize(), q0: unit.quaternion.clone(), p0: unit.position.clone(),
      ease: h.point.clone(), follow: 40 / +HY.pref("m3.pull.gel", PULL.gel),
      plane: new THREE.Plane().setFromNormalAndCoplanarPoint(n, h.point), target: h.point.clone(), t: performance.now() };
    const geo = new THREE.BufferGeometry().setFromPoints([h.point, h.point]);
    g.line = new THREE.Line(geo, new THREE.LineBasicMaterial({ color: 0xff4fa3, depthTest: false, toneMapped: false }));
    g.dot = new THREE.Mesh(new THREE.SphereGeometry(size * 0.035, 12, 8), new THREE.MeshBasicMaterial({ color: 0xff4fa3, depthTest: false, toneMapped: false }));
    for (const o of [g.line, g.dot]) { o.layers.set(1); o.renderOrder = 999; L.view.helpers.add(o); }
    if (L.sel !== unit) pick(L, unit);
    const step = now => {
      if (!g) return;
      const dt = Math.min(0.05, (now - g.t) / 1000); g.t = now;
      const u = g.unit; g.ease.lerp(g.target, 1 - Math.exp(-g.follow * dt));   // the gel: the mouse as the object feels it
      if (g.len) {   // touched at the very centre: nothing to turn about
        // the ray from the camera through the mouse meets the sphere round the pivot; past its edge, the edge point nearest the ray
        const o = L.cam.position, d = g.ease.clone().sub(o).normalize(), oc = g.pivot.clone().sub(o), b = d.dot(oc), disc = g.R * g.R - (oc.lengthSq() - b * b);
        const Q = disc >= 0 ? o.clone().addScaledVector(d, g.near ? b - Math.sqrt(disc) : b + Math.sqrt(disc))
          : g.pivot.clone().add(o.clone().addScaledVector(d, b).sub(g.pivot).setLength(g.R));
        const q = new THREE.Quaternion().setFromUnitVectors(g.a0, Q.sub(g.pivot).normalize());
        u.quaternion.copy(g.q0).premultiply(q); u.position.copy(g.p0).sub(g.pivot).applyQuaternion(q).add(g.pivot);
      }
      u.updateMatrixWorld(true);
      const p2 = u.localToWorld(g.pL.clone()); g.line.geometry.setFromPoints([p2, g.target]); g.dot.position.copy(p2);
      readBack(L.view, u.userData.id); L.need(); save(L.path);
      raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
  }, { capture: true, signal: L.ac.signal });
  cvs.addEventListener("pointermove", ev => { if (!g) return; at(ev); ray.ray.intersectPlane(g.plane, g.target); }, L.on);
  const end = () => {
    if (!g) return; cancelAnimationFrame(raf);
    L.view.helpers.remove(g.line); L.view.helpers.remove(g.dot); g = null;
    L.orbit.enabled = true; L.view.bounds = L.view.meshBounds(); L.changed("pull", true); L.ui.sync(); L.need();
  };
  cvs.addEventListener("pointerup", end, L.on); cvs.addEventListener("pointercancel", end, L.on);
}

function attach(L) {
  const p = picked(L), rec = p.id ? findAny(L.e.doc, p.id) : null, ok = (p.kind === "object" || p.kind === "light") && !(rec && rec.locked) && ["translate", "rotate", "scale"].includes(L.tool) && !(p.kind === "light" && L.tool === "scale");   // a locked thing keeps no gizmo
  if (ok) { L.tc.attach(p.unit); L.tc.setMode(L.tool); } else L.tc.detach();
}
function setTool(L, t) { L.tool = t; (L.ui.bar || L.ui.root).querySelectorAll("[data-tool]").forEach(b => b.classList.toggle("on", b.dataset.tool === t)); attach(L); L.need(); }

// the editor watches how long a frame takes: slow, it draws at half and then a third of the size; still too slow, it stops and asks
function guard(L, ms) {
  L.times.push(ms); if (L.times.length > 3) L.times.shift(); if (L.times.length < 3) return;
  const avg = L.times.reduce((a, b) => a + b, 0) / 3;
  if (avg > SLOW_MS && L.scale > 0.34) { L.scale = L.scale > 0.6 ? 0.5 : 0.33; L.times = []; HY.toast(t("3D: a frame takes {ms} ms, the preview got coarser", { ms: Math.round(avg) }), "info", { key: "m3slow" }); return; }
  if (avg > STOP_MS && !L.allowSlow) pause(L, avg);
}
function pause(L, ms, why) {
  if (L.paused) return; L.paused = true;
  const d = document.createElement("div"); d.className = "h3 m3pause";
  d.innerHTML = `<div>${why || t("The scene renders too slowly: {ms} ms a frame.", { ms: Math.round(ms) })} ${t("Rendering stopped so that Hyimg does not hang.")}</div><div><button data-go>${t("Continue")}</button> <button data-stop>${t("Close")}</button></div>`;
  d.addEventListener("pointerdown", e => e.stopPropagation());
  d.querySelector("[data-go]").onclick = () => { d.remove(); L.paused = false; L.allowSlow = true; L.times = []; L.redraw(); };
  d.querySelector("[data-stop]").onclick = () => { d.remove(); stopLive(); };
  L.el.appendChild(d);
}

// «Save» (keep) and «Cancel» (owner 2026-10-07: «вместо Done нужно Save, ну и Cancel тоже»). Save: the card takes its view (item.view, the
// truth for what it shows), the scene file is written only when what the cards share changed (objects, lights, world, other cameras), its
// before and after kept as versions so the board's undo and history bring the scene back with the card (sceneRev), and the session is
// one step on the board. Cancel: the scene in memory, the card and the board as they were at the opening, and scene.json as it was
async function stopLive(keep = true) {
  if (!live || live.saving) return;
  const L = live; settle(L);
  const d = L.e.doc, cid = L.camId(), card = HY.board.items[L.id], cam = (d.cameras || []).find(x => x.id === cid);
  // the scene is written first and waited for (P4 S-04): refused, the studio stays open with everything in it
  let wrote = false;
  if (keep && sharedKey(d, cid) !== sharedKey(L.sceneOpen, cid)) { L.saving = true; wrote = await writeScene(L); L.saving = false; if (!wrote || live !== L) return; }
  const lost = !keep && changedSince(L);
  if (keep && card && cam) card.view = viewOf(cam);
  live = null;
  L.ac.abort();   // every listener this session put on the shared canvas
  clearInterval(L.rsI);
  if (L.themeObs) L.themeObs.disconnect();
  if (L.sdock) L.sdock.destroy();   // the dock's list and Actions (dock.js)
  if (L.kit) L.kit.destroy(); if (L.dk) L.dk.destroy(); if (L.blender) L.blender.dispose(); if (L.look) L.look.dispose(); if (L.ann) L.ann.dispose(keep, keep ? d : L.sceneOpen);
  L.orbit.dispose(); L.tc.detach(); L.view.scene.remove(L.tc.getHelper()); L.tc.dispose();
  if (L.kh) L.kh.hide(); L.view.helpers.clear(); if (HY.dock) HY.dock(null); L.ui.root.remove(); L.unplace(); L.el.querySelectorAll(".m3pause").forEach(x => x.remove()); renderer.domElement.remove(); L.el.classList.remove("plg-live"); document.body.classList.remove("m3edit");
  if (HY.full) HY.full(false);
  if (!keep) return cancelled(L, lost);
  // one step on the board (owner 2026-10-07), its «before» the board now with the studio's own cards as opened (P4 S-22: ⌘Z took others'
  // work too). The scene's versions by rev; each card of the scene says which it shows (sceneRev): ⌘Z brings the scene back (canvas.js)
  if (HY.squash && L.mark >= 0) HY.squash(L.mark);
  const before = openingBoard(L);
  if (wrote) {
    const rev0 = (L.sceneOpen && L.sceneOpen.rev) || 0, rev1 = d.rev;
    if (L.rawOpen != null) putVersion(L.path, rev0, L.rawOpen);
    putVersion(L.path, rev1, L.e.raw);
    for (const [k, x] of Object.entries(HY.board.items)) if (x.type === TYPE && x.scene === L.path) { x.sceneRev = rev1; if (before.items[k]) before.items[k].sceneRev = rev0; }
  }
  if (boardDiffers(before, JSON.parse(HY.snap()))) HY.commit(JSON.stringify(before), t("3D: scene saved")); else HY.render();
  // the board redraws a plugin's card only when its item changes, and edits live in the scene file: the cards of this scene are
  // redrawn here (2026-10-03: after «Готово» the card kept the view from before the edit)
  repaint(L.path, true);
}

// the studio's steps and History are history.js; the card's view, «Save» and «Cancel» view.js (owner 2026-10-07)
const noUi = d => { const c = Object.assign({}, d); delete c.ui; return c; };
// light and camera icons: picked like objects, on layer 1, which only the editor camera sees
function helpers(L) {
  const v = L.view, g = v.helpers; g.clear(); L.icons.clear();
  const R = Math.max(0.006, v.bounds.getSize(new THREE.Vector3()).length() * 0.025), camId = L.camId();
  for (const l of L.e.doc.lights || []) {
    const m = new THREE.Mesh(new THREE.SphereGeometry(R, 16, 8), new THREE.MeshBasicMaterial({ color: 0xffc94a, toneMapped: false }));
    m.userData.light = l.id; g.add(m); L.icons.set(l.id, m);
    if (l.type !== "point") { const a = new THREE.ArrowHelper(new THREE.Vector3(0, 0, -1), new THREE.Vector3(), R * 6, 0xffb000, R * 1.6, R); a.userData.follow = l.id; g.add(a); }
  }
  for (const c of L.e.doc.cameras || []) {
    if (c.id === camId) continue;
    const m = new THREE.Mesh(new THREE.ConeGeometry(R * 1.6, R * 3, 4).rotateX(Math.PI / 2).rotateZ(Math.PI / 4).translate(0, 0, -R * 1.5), new THREE.MeshBasicMaterial({ color: 0x5aa0ff, wireframe: true, toneMapped: false }));
    m.userData.cam = c.id; g.add(m); L.icons.set(c.id, m);
  }
  g.traverse(o => o.layers.set(1));
  if (L.sel && L.sel.userData.cam) L.sel = L.icons.get(L.sel.userData.cam) || null;
}
function updateHelpers(L) {
  const v = L.view, far = v.bounds.getSize(new THREE.Vector3()).length() * 0.6;
  for (const h of v.helpers.children) {
    const lid = h.userData.light || h.userData.follow;
    if (lid) {
      const u = v.units.get(lid); if (!u) continue;
      h.position.copy(u.parts && u.parts.sun ? u.parts.main.target.position.clone().add(new THREE.Vector3(0, 0, 1).applyQuaternion(u.obj.quaternion).multiplyScalar(far)) : u.obj.position);
      if (h.userData.follow) h.setDirection(new THREE.Vector3(0, 0, -1).applyQuaternion(u.obj.quaternion));
    }
    if (h.userData.cam) { const c = L.e.doc.cameras.find(x => x.id === h.userData.cam); if (c) { h.position.copy(toV(c.loc)); h.quaternion.copy(v.camera(c.id, 4, 5).quaternion); } }
  }
}

const kindOf = (doc, id) => doc.objects.some(x => x.id === id) ? "objects" : doc.lights.some(x => x.id === id) ? "lights" : doc.cameras.some(x => x.id === id) ? "cameras" : null;
const findAny = (doc, id) => { const k = kindOf(doc, id); return k ? doc[k].find(x => x.id === id) : null; };

async function addThing(L, what) {
  // a new thing stands beside what is there (right of it, on the floor), not inside it
  const b = L.view.bounds, side = fromV(new THREE.Vector3(b.max.x, b.min.y, (b.min.z + b.max.z) / 2)), aim = fromV(L.orbit.target);
  const doc = L.e.doc, n = (base) => { let i = 1; while ([...doc.objects, ...doc.lights, ...doc.cameras].some(x => x.name === `${base} ${i}`)) i++; return `${base} ${i}`; };
  const id = newId();
  if (PRIM[what]) {
    const s = PRIM[what].slice(); doc.objects.push({ id, name: n(t(ADD.find(a => a[0] === what)[1])), src: { type: "prim", shape: what, size: s }, loc: [side[0] + s[0] / 2 + 0.03, side[1], s[2] / 2], rot: [1, 0, 0, 0], scale: [1, 1, 1], color: "#b8b8b4", ai: "" });
  } else if (what.startsWith("model:")) {   // a model of the project, picked in «+»: its name and its text for the AI come from model.json
    const m = (await projectModels()).find(x => x.id === what.slice(6)); if (!m) { HY.toast(t("The model is no longer in 3d/models")); return; }
    doc.objects.push({ id, name: n(m.title || m.id), src: { type: "model", model: m.id }, loc: [side[0] + 0.07, side[1], modelHeight(m) / 2 + 0.0005], rot: [1, 0, 0, 0], scale: [1, 1, 1], ai: m.ai || "" });
    ensureAssembled(m.id).catch(err => HY.toast(t("Model for Blender not written: {e}", { e: err.message })));
  } else if (LIGHT_W[what]) {
    const p = fromV(L.cam.position.clone().add(new THREE.Vector3(0, 0.35, 0)).add(new THREE.Vector3(-0.25, 0, 0).applyQuaternion(L.cam.quaternion)));
    doc.lights.push({ id, name: n(t(LIGHT_NAMES[what])), type: what, loc: p, rot: look(p, aim), color: [1, 1, 1], power: LIGHT_W[what], size: what === "area" ? 0.5 : 0.05, size_y: 0.5, shape: "SQUARE", spot_size: 45, spot_blend: 0.3 });
  } else if (what === "camera") {   // a copy of the card's camera; the card switches to it, the old one keeps its view
    const cur = findAny(doc, L.camId()) || doc.cameras[0];
    doc.cameras.push(Object.assign(JSON.parse(JSON.stringify(cur)), { id, name: n(t("Camera")) }));
    const before = HY.snap(); HY.board.items[L.id].camera = id; HY.commit(before, t("3D: new camera"));
  }
  await L.view.apply(doc); L.changed("add", true); L.reload();
  if (what !== "camera") pick(L, LIGHT_W[what] ? L.view.units.get(id).obj : L.view.units.get(id).obj, true);
}
async function removeThing(L, ids) {   // one id or several (the chosen rows), one step
  const doc = L.e.doc; let n = 0;
  for (const id of [].concat(ids)) {
    const k = kindOf(doc, id); if (!k) continue;
    if (k === "cameras" && doc.cameras.length < 2) { HY.toast(t("The last camera can't be deleted")); continue; }
    doc[k] = doc[k].filter(x => x.id !== id); doc.removed = [...new Set([...(doc.removed || []), id])]; n++;
    if (k !== "cameras") continue;
    const it = HY.board.items[L.id]; if (it.camera === id) { const before = HY.snap(); it.camera = doc.cameras[0].id; HY.commit(before, t("3D: camera deleted")); }
    if (doc.active_camera === id) doc.active_camera = doc.cameras[0].id;
  }
  if (!n) return; L.sel = null; L.multi = null; await L.view.apply(doc); L.changed("remove", true); L.reload();
}
function setCamera(L, cid) { const before = HY.snap(); HY.board.items[L.id].camera = cid; HY.commit(before, t("3D: card camera")); L.sel = null; L.reload(); remember(L, "camera"); }
// the card's frame changed (its edges, the ratio bar, the list): the scene's render size for Blender follows the card being edited
export function framed(id) {
  if (!live || live.id !== id) return; const L = live, it = HY.board.items[id]; if (!it) return;
  const s = outSize(it, (L.e.doc.cameras || []).find(x => x.id === L.camId()), L.e.doc); L.e.doc.render = { x: s[0], y: s[1] };   // the card's output size (frame.js)
  L.changed("ratio", true); requestAnimationFrame(() => L.reload());
}
// «Широкий ↔ изометрия» (owner 2026-10-04: «a slider that changes the zoom together with the lens width, the picture goes wide angle
// without moving away, or the other way into isometry»): a dolly zoom. The lens changes and the camera slides along its line of sight
// so that the point it looks at keeps its size (distance ∝ focal length); only the perspective changes. 0 is 12 mm, 100 is 800 mm,
// which reads almost as an isometric view. The clipping range follows the new distance, Blender gets it with the camera.
const DOLLY = [12, 800];
const dollyOf = lens => Math.round(100 * Math.log(Math.min(DOLLY[1], Math.max(DOLLY[0], lens)) / DOLLY[0]) / Math.log(DOLLY[1] / DOLLY[0]));
const lensOf = t => +(DOLLY[0] * Math.pow(DOLLY[1] / DOLLY[0], t / 100)).toFixed(1);
function dolly(L, c, lens) {
  const fwd = new THREE.Vector3(0, 0, -1).applyQuaternion(L.cam.quaternion), T = L.orbit.target.clone();
  const d = Math.max(0.05, T.clone().sub(L.cam.position).dot(fwd)), d2 = d * lens / c.lens;
  L.cam.position.copy(T).addScaledVector(fwd, -d2); L.cam.updateMatrixWorld(); c.lens = lens;
  const R = L.view.bounds.getSize(new THREE.Vector3()).length() / 2 || 0.1;
  c.clip = [Math.max(0.01, Math.min(0.5 * (d2 - 2 * R), 0.1 * d2)), Math.max(100, d2 + 4 * R)].map(x => +x.toFixed(3));
  cameraBack(L.e.doc, c.id, L.cam); L.recam(); L.changed("lens");
}
// the dolly zoom of any camera: the card's moves with the view (dolly), another one slides along its own line of sight to keep the point
// it looks at (orbitOf) the same size
function dollyAny(L, c, lens) {
  if (c.id === L.camId()) return dolly(L, c, lens);
  const o = orbitOf(L, c), d2 = o.dist * lens / c.lens, R = L.view.bounds.getSize(new THREE.Vector3()).length() / 2 || 0.1;
  c.lens = lens; c.clip = [Math.max(0.01, Math.min(0.5 * (d2 - 2 * R), 0.1 * d2)), Math.max(100, d2 + 4 * R)].map(x => +x.toFixed(3));
  setOrbit(L, c, { [K.dist]: d2 * 100, [K.az]: o.az, [K.inc]: o.inc, [K.roll]: o.roll });
}
// The camera as in KeyShot's «Position and Direction» (owner 2026-10-04: «add azimuth and the other two besides the coordinates»):
// distance, azimuth, inclination and twist about the point the camera looks at. Azimuth turns in the floor plane from +X toward +Y,
// inclination rises from the floor, as in Blender with z up; twist turns the camera about its line of sight. The point is the one the
// card's camera orbits; for another camera, the middle of the scene on its line of sight.
const D2R = Math.PI / 180, R2D = 180 / Math.PI;
function orbitOf(L, c) {
  const card = c.id === L.camId(), cam = card ? L.cam : L.view.camera(c.id, 400, 300), f = new THREE.Vector3(0, 0, -1).applyQuaternion(cam.quaternion);
  const T = card ? L.orbit.target.clone() : cam.position.clone().addScaledVector(f, Math.max(0.05, L.view.bounds.getCenter(new THREE.Vector3()).sub(cam.position).dot(f)));
  const v = cam.position.clone().sub(T), dist = v.length() || 1e-6;
  const level = new THREE.PerspectiveCamera(); level.position.copy(cam.position); level.lookAt(T);   // the same view without twist
  const tw = level.quaternion.clone().invert().multiply(cam.quaternion);
  return { T, card, dist, az: Math.atan2(-v.z, v.x) * R2D, inc: Math.asin(THREE.MathUtils.clamp(v.y / dist, -1, 1)) * R2D, roll: 2 * Math.atan2(tw.z, tw.w) * R2D };
}
const orbitVals = o => ({ [K.dist]: Math.round(o.dist * 1000) / 10, [K.az]: Math.round(o.az), [K.inc]: Math.round(o.inc), [K.roll]: Math.round(((o.roll + 540) % 360) - 180) });
const orbitCfg = o => { const v = orbitVals(o); return { [K.dist]: [v[K.dist], 1, Math.max(500, Math.ceil(v[K.dist] * 3)), 0.1],
  [K.az]: [v[K.az], -180, 180, 1], [K.inc]: [v[K.inc], -89, 89, 1], [K.roll]: [v[K.roll], -180, 180, 1] }; };
function setOrbit(L, c, k) {
  const o = orbitOf(L, c), a = k[K.az] * D2R, i = THREE.MathUtils.clamp(k[K.inc], -89, 89) * D2R, d = Math.max(0.01, k[K.dist] / 100);
  const t = new THREE.PerspectiveCamera(); t.position.copy(o.T).add(new THREE.Vector3(Math.cos(i) * Math.cos(a), Math.sin(i), -Math.cos(i) * Math.sin(a)).multiplyScalar(d));
  t.lookAt(o.T); t.quaternion.multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 0, 1), k[K.roll] * D2R));
  cameraBack(L.e.doc, c.id, t);
  if (o.card) L.recam(); else { helpers(L); L.need(); }
  L.changed("camera");
}
// Coordinates of a camera or a light as Blender shows them (owner 2026-10-04: «the coordinates go into a folder that opens, and the rest
// of the camera's settings too»): location in cm, rotation as Blender's XYZ Euler in degrees, straight from the file's numbers
const EUL = "ZYX";   // Blender's XYZ Euler applies X, then Y, then Z: in three.js terms the order "ZYX"
function coordCfg(x) {
  const e = new THREE.Euler().setFromQuaternion(new THREE.Quaternion(x.rot[1], x.rot[2], x.rot[3], x.rot[0]), EUL), r = v => Math.round(v * R2D * 10) / 10;
  return { [K.pos]: { X: [Math.round(x.loc[0] * 1000) / 10, -1000, 1000, 0.1], Y: [Math.round(x.loc[1] * 1000) / 10, -1000, 1000, 0.1], Z: [Math.round(x.loc[2] * 1000) / 10, -1000, 1000, 0.1] },
    [K.rot]: { X: [r(e.x), -180, 180, 0.1], Y: [r(e.y), -180, 180, 0.1], Z: [r(e.z), -180, 180, 0.1] }, _collapsed: true };
}
// A change counts only when the folder's own numbers changed (they are rounded: compared with the file they would nudge the camera on
// every other change), and anything else that moves the camera writes the folder's numbers anew (2026-10-04: after a dolly zoom the
// folder still held the old place and the next change put the camera back there)
const sameVals = (a, b) => JSON.stringify(a) === JSON.stringify(b);
function coordSet(x, k) {
  const P = k[K.pos], R = k[K.rot], q = new THREE.Quaternion().setFromEuler(new THREE.Euler(R.X * D2R, R.Y * D2R, R.Z * D2R, EUL));
  x.loc = [P.X / 100, P.Y / 100, P.Z / 100]; x.rot = [q.w, q.x, q.y, q.z];
}
const coordVals = x => { const c = coordCfg(x), v = {}; for (const f of [K.pos, K.rot]) { v[f] = {}; for (const a of "XYZ") v[f][a] = c[f][a][0]; } return v; };
const FITS = () => [{ value: "AUTO", label: t("Auto") }, { value: "HORIZONTAL", label: t("Horizontal") }, { value: "VERTICAL", label: t("Vertical") }];
const camMoreCfg = c => ({ [K.sensor]: [c.sensor || 36, 4, 100, 0.1], [K.fit]: { type: "select", seg: true, options: FITS(), default: c.fit || "AUTO" },
  [K.shiftX]: [(c.shift || [0, 0])[0], -1, 1, 0.01], [K.shiftY]: [(c.shift || [0, 0])[1], -1, 1, 0.01],
  [K.near]: [Math.round((c.clip || [0.01, 100])[0] * 1000) / 10, 0.1, 1000, 0.1], [K.far]: [(c.clip || [0.01, 100])[1], 1, 10000, 1], _collapsed: true });
function camMoreSet(c, k) {
  if (!k) return false;
  const n = { sensor: k[K.sensor], fit: k[K.fit], shift: [k[K.shiftX], k[K.shiftY]], clip: [k[K.near] / 100, k[K.far]] };
  const was = { sensor: c.sensor || 36, fit: c.fit || "AUTO", shift: c.shift || [0, 0], clip: c.clip || [0.01, 100] };
  if (JSON.stringify(n) === JSON.stringify(was)) return false;
  Object.assign(c, n); return true;
}
// «Сбросить» (owner 2026-10-04: «a reset that brings back the position it had at the start, for every panel at its end; inactive while
// nothing changed, red once something did»; and one for everything in the dock, as the library's reset). The start is the scene and
// the card as they were when the editor opened. The buttons look the same everywhere (ui/ui.css .hy-reset).
const clone = x => x === undefined ? undefined : JSON.parse(JSON.stringify(x));
const norm = x => { const c = clone(x); if (c && c.cam) tidy({ cameras: [c.cam] }); else if (c && c.loc) tidy({ objects: [c] }); return JSON.stringify(c === undefined ? null : c); };
function scopeOf(L) {
  const d = L.e.doc, s = L.start.doc, k = L.paneKind || "scene", it = HY.board.items[L.id] || {}, is = L.start.item;
  const one = (arr, id) => ({ arr, id, now: () => (d[arr] || []).find(x => x.id === id), was: (s[arr] || []).find(x => x.id === id) });
  if (k === "object" || k === "layer") { const p = picked(L); return p.id ? one("objects", p.id) : null; }
  if (k === "light") return one("lights", L.lightSel);
  if (k === "camera") return one("cameras", L.camSel);
  const cid = L.camId(), pick = (doc, item) => ({ cam: (doc.cameras || []).find(x => x.id === cid), world: doc.world, render: doc.render, bg: item.bg, lock: item.lock, w: item.w, h: item.h });
  return { scene: true, cid, now: () => pick(d, it), was: pick(s, is) };
}
function resetState(L) {
  if (live !== L || !L.ui) return;
  const sc = scopeOf(L), paneChanged = !!(sc && sc.was) && norm(sc.now()) !== norm(sc.was);
  const pb = [...L.ui.root.querySelectorAll(".dk button")].find(b => b.textContent.trim() === K.reset);
  if (pb) { pb.classList.add("hy-reset"); pb.disabled = !paneChanged; pb.title = paneChanged ? t("Back to how it was when the studio opened") : t("Nothing changed"); }
  if (L.syncRes) L.syncRes();   // the output size follows the card (an undo, an edge dragged on the board)
  // each action button says what it does (owner 2026-10-07: «Delete» read «Nothing changed»; that is Reset's reason alone)
  const del = { camera: "Delete camera", light: "Delete light", object: "Delete object" }[L.paneKind];
  for (const b of L.ui.root.querySelectorAll(".dk .dialkit-button")) {
    const w = b.textContent.trim(), tip = w === K.del ? (del ? t(del) : "") : w === K.showcard ? t("The card will look through this camera") : null;
    if (tip !== null && b.title !== tip) b.title = tip;
  }
  const it = HY.board.items[L.id] || {}, allChanged = stateKey(noUi(tidy(clone(L.e.doc)))) !== L.start.key || itemFields.some(f => JSON.stringify(it[f]) !== JSON.stringify(L.start.item[f]));
  const db = L.ui.bar && L.ui.bar.querySelector("[data-a=reset]"); if (db) db.disabled = !allChanged;
}
async function resetPane(L) {
  const sc = scopeOf(L); if (!sc || !sc.was) return; const d = L.e.doc;
  if (sc.scene) {
    const i = d.cameras.findIndex(x => x.id === sc.cid); if (i >= 0 && sc.was.cam) d.cameras[i] = clone(sc.was.cam);
    if (sc.was.world === undefined) delete d.world; else d.world = clone(sc.was.world);
    if (sc.was.render) d.render = clone(sc.was.render);
    const it = HY.board.items[L.id], before = HY.snap(); for (const f of ["bg", "lock", "w", "h"]) { if (L.start.item[f] === undefined) delete it[f]; else it[f] = clone(L.start.item[f]); } HY.commit(before);
  } else { const i = d[sc.arr].findIndex(x => x.id === sc.id); if (i >= 0) d[sc.arr][i] = clone(sc.was); }
  await L.view.apply(d); L.reload(); L.changed("reset", true); resetState(L);
}
async function resetAll(L) {
  const d = L.e.doc, s = clone(L.start.doc);
  for (const k of Object.keys(d)) if (!["rev", "by", "t", "ui"].includes(k)) delete d[k];
  for (const k of Object.keys(s)) if (!["rev", "by", "t", "ui"].includes(k)) d[k] = s[k];
  const it = HY.board.items[L.id], before = HY.snap(); for (const f of itemFields) { if (L.start.item[f] === undefined) delete it[f]; else it[f] = clone(L.start.item[f]); } HY.commit(before);
  L.sel = null; await L.view.apply(d); L.reload(); L.changed("reset", true); resetState(L);
}
export function nudge(id) { if (live && live.id === id) live.need(); }
// the card's editor bar on the board (canvas.html def.editBar): Blender's controls when the scene came from a studio (blender.js)
export function editBar(el, id) { if (live && live.id === id && live.blender) live.blender.mount(el); }

// ---- snapshot: the plain view (with the card's background, transparent if so), the masks and the depth of the card's camera
async function shoot(L) {
  const it = HY.board.items[L.id], doc = L.e.doc, r = { x: it.w, y: it.h }, long = 1600;   // the card's own frame
  const W = r.x >= r.y ? long : Math.round(long * r.x / r.y), H = r.x >= r.y ? Math.round(long * r.y / r.x) : long;
  const cid = it.camera || doc.active_camera, c = findAny(doc, cid), cam = L.view.camera(cid, W, H); cam.layers.set(0);
  const hid = hideEditor(L.e), blobs = {};
  for (const pass of ["beauty", "mask", "depth"]) { L.view.render(cam, W, H, pass, it.bg); blobs[pass] = await new Promise(ok => renderer.domElement.toBlob(ok, "image/png")); }
  hid(); L.redraw();
  const objs = doc.objects.filter(o => !o.hidden && !o.shadow_only), legend = objs.map((o, i) => ({ mask: L.view.units.get(o.id) ? L.view.units.get(o.id).mask : MASKS[i % MASKS.length], name: o.name, ai: o.ai || "" }));
  const lens = Math.round(c.lens), what = legend.map(m => `${m.mask} ${m.ai || m.name}`).join("; ");
  const common = { model: t("Hyimg 3D (three.js r180, preview, not a Blender render)"), route: "hyimg-3d", scene: L.path, scene_rev: doc.rev, camera: c, render: { x: W, y: H },
    background: it.bg || { world: true }, masks: legend, reproduce: `в Blender: blender -b --python <Hyimg-3d>/blender/hyimg_scene.py -- apply <библиотека>/${L.path} --fresh --save-as <файл.blend>, камера ${c.name}${it.bg && it.bg.transparent ? ", Film › Transparent" : ""}` };
  try {
    const before = HY.snap(), x0 = it.x + it.w + Math.round(it.w * 0.05);
    const b = await HY.snapshot(blobs.beauty, "3d-scene", SHOTS, Object.assign({ prompt: t("3D sketch of a scene for generation: camera {cam}, lens {lens} mm; objects by masks: {what}", { cam: c.name, lens, what }), pass: "вид" }, common));
    // each picture on the board as soon as its file is written: a pass refused later leaves no file without its card (P4 S-44)
    const bw = it.h * b.ar, bid = HY.addPicture(b.path, b.ar, x0, it.y, bw), ids = [bid], sh = it.h / 2 - 8;
    if (it.grade && HY.board.items[bid]) HY.board.items[bid].grade = JSON.parse(JSON.stringify(it.grade));   // the view is the card's picture: it keeps the card's grade, the file is not graded
    try {
      const m = await HY.snapshot(blobs.mask, "3d-mask", SHOTS, Object.assign({ prompt: t("object masks for {path}: {what}", { path: b.path, what }), pass: "маски", of: b.path }, common));
      ids.push(HY.addPicture(m.path, m.ar, x0 + bw + 16, it.y, sh * m.ar));
      const d = await HY.snapshot(blobs.depth, "3d-depth", SHOTS, Object.assign({ prompt: t("depth for {path}: white is near, black is far", { path: b.path }), pass: "глубина", of: b.path }, common));
      ids.push(HY.addPicture(d.path, d.ar, x0 + bw + 16, it.y + sh + 16, sh * d.ar));
    } catch (err) { HY.toast(t("Snapshot not saved: {e}", { e: err.message }), "error"); }
    // one step of the board, and of the Studio's ⌘Z; the pictures stay after Cancel, they are what was made (history.js shotTaken, P4 S-44)
    HY.commit(before, t("3D: snapshot, masks and depth beside it")); shotTaken(L, ids);
  } catch (err) { HY.toast(t("Snapshot not saved: {e}", { e: err.message })); }
}

// ---- panels, after Spline (owner 2026-10-03): layers left with search and nesting lines, the inspector right without tabs (it shows
// what is picked, the scene when nothing is), an icon toolbar on top with «+», the axes at the bottom (drag turns the camera, a click on
// an axis flies it there)
const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const hexOf = c => "#" + new THREE.Color(c[0], c[1], c[2]).getHexString();
const linOf = h => { const c = new THREE.Color(h); return [+c.r.toFixed(4), +c.g.toFixed(4), +c.b.toFixed(4)]; };
const r1 = x => Math.round(x * 10) / 10;
// a layer's path as the editor shows it: the path's own names are keys in the scene file (scene.js nodeLabel: «Чехол», «узел», «~зеркало»
// stay as they are in the file), shown in the page's language
const shownPath = path => path.split("/").map(seg => { const m = seg.endsWith("~зеркало"), b = m ? seg.slice(0, -"~зеркало".length) : seg;
  return (b === "Чехол" ? t("Case") : b === "узел" ? t("node") : b) + (m ? "~" + t("mirror") : ""); });
// one icon family with the image studio and the board (owner 2026-10-06: «почему-то они не круглые в 3d studio», the tools drawn in another
// hand; 2026-10-07: «одно значение, одна иконка»): every icon here is Hyimg's (ui/icons.js hyIcon), the studio draws none of its own. The
// studio's names for them, each to its registry name: a scene's camera wears the camera, Snapshot the photo camera, an added box «primBox»;
// a group is the Board's group, Figma's dashed square (owner 2026-10-09: «let's make same as in figma and apply it»), no longer a folder
const FAMILY = { translate: "move", smart: "pull", off: "eyeoff", unlock: "lockOpen", file: "doc", box: "primBox", shot: "snapshot" };   // hy-icon-names
const ico = (k, cls = "ic") => hyIcon(FAMILY[k] || k, 0, 1.85, cls);
const hasIco = k => !!(window.HY_TOOL_IC && HY_TOOL_IC[FAMILY[k] || k]);
// the library's own folder search field (review/v2.html #ffilt in ui/look.css .hy-search: its magnifier, height, radius, padding, ground)
const LIB_FIND = hyIcon("search", 0, 2);
// the app's one chevron (ui/icons.js HY_CHEV): the layer list's sections and rows fold with it
const CHEV = () => window.HY_CHEV;
// the layer list's sections, in this order, each folding and each sized by the line under the one above (ui/split.js)
const SECS = ["objects", "lights", "cameras", "materials"], SEC_NAME = { objects: "Objects", lights: "Lights", cameras: "Cameras", materials: "Materials" };
// a tree node's navigation colour (owner 2026-10-06: right click on a file, a group or a folder of the list, «a colour row on top», the board's
// sticky-note colours): it marks the row and what is under it, never the object's material. The app's marking colours and their row of
// swatches are Hyimg's (ui/menu.js HY_COLORS, hyMenuColors), the same as the library's folder tree; the copy here is for an older Hyimg.
// The scene file keeps the name of the colour (ui.colors in scene.json, scene.js)
const OLD_COLS = { yellow: "#f4c430", orange: "#f59a3d", red: "#ef6a6a", pink: "#f08cc4", purple: "#b79cf2", blue: "#7dbbf5", green: "#7fd49b", grey: "#d9d9de" };
const navCols = () => window.HY_COLORS || OLD_COLS;
const navHex = name => (name && navCols()[name]) || null;
// a material: the file's own or a finish; the list shows names in the page's language, FIN_KEY turns a name back into the finish
const FIN_WORDS = { "": "As in the file", matte: "Matte", glossy: "Gloss", metal: "Metal" };
let FIN_NAME = {}, FIN_KEY = {};
const MENU_ICON = { box: "box", cylinder: "cylinder", sphere: "sphere", plane: "plane", model: "model", camera: "camera" };

function buildUI(L) {
  // one DialKit root (dark, as in the demo the owner approved) holds every panel: the tree and the bars use its tokens, the inspector
  // its controls
  // DialKit takes the page's theme, and follows it when the settings change it while the editor is open (owner 2026-10-04)
  const pageTheme = () => document.documentElement.dataset.theme === "light" ? "light" : "dark";
  const root = document.createElement("div"); root.className = "m3ui dialkit-root"; root.dataset.theme = pageTheme();
  L.themeObs = new MutationObserver(() => { const t = pageTheme(); root.dataset.theme = t; root.querySelectorAll(".dialkit-root").forEach(r => { r.dataset.theme = t; }); });
  L.themeObs.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme", "data-ui"] });
  root.innerHTML = `
    <div class="m3p m3t"><span class="tip"><button class="plus hy-dkb" data-plus title="${t("Add")}" aria-label="${t("Add")}">${ico("plus")}</button><div class="menu m3menu" hidden>${ADD.map(([k, w]) => hyMenuItem(`data-add="${k}"`, ico(MENU_ICON[k] || "light"), t(w))).join("")}</div></span>
      <span class="sep"></span>${[["select", "Select", "V"], ["translate", "Move", "G"], ["rotate", "Rotate", "R"], ["scale", "Scale", "S"], ["smart", "Pull: by a point, as on a string in thick gel", "T"]].map(([k, w, key]) => `<button class="hy-dkb" data-tool="${k}" data-key="${key}" title="${t(w)} · ${key}" aria-label="${t(w)}">${ico(k)}<kbd>${key}</kbd></button>`).join("")}
      <span class="sep"></span><button class="m3ic hy-dkb" data-a="undo" title="${t("Undo · ⌘Z")}" aria-label="${t("Undo")}" disabled>${hyIcon("undo", 0, 2)}</button>
      <button class="m3ic hy-dkb" data-a="redo" title="${t("Redo · ⇧⌘Z")}" aria-label="${t("Redo")}" disabled>${hyIcon("redo", 0, 2)}</button>
      <button class="m3reset hy-dkb" data-a="reset" title="${t("Reset all: the scene and the card as they were when the studio opened")}" aria-label="${t("Reset all")}" disabled>${hyIcon("reset", 0, 2)}</button><span class="sep"></span><span class="dgrp" data-dk="view"></span><span class="sep"></span>
      <button class="wide" data-a="shot" title="${t("View, masks and depth beside the card · P")}">${ico("shot")}${t("Snapshot")}</button><span data-dk="acts"></span></div>
    <div class="m3title hy-plate" data-hyui><b>${t("3D scene")}</b><code class="fp"></code></div>
    <div class="m3p m3l hy-blk" data-hyui><div class="lhd"><label class="hy-search">${LIB_FIND}<input data-q type="search" placeholder="${t("Search layers")}" aria-label="${t("Search layers")}" autocomplete="off" spellcheck="false"></label>
      <hy-minitoggle data-raw title="${t("Show the files' wrappers without geometry")}">${t("All nodes")}</hy-minitoggle></div>
      <div class="tr">${SECS.map((k, i) => `${i ? `<div class="msp" data-before="${k}"></div>` : ""}<section class="ms" data-s="${k}" hidden><div class="msh hy-sh" role="button" aria-expanded="true" title="${t("Fold or unfold")}"><span class="mtg hy-sh-cv">${CHEV()}</span><span class="mst">${t(SEC_NAME[k])}</span><span class="cnt hy-sh-n"></span></div><div class="msb"><div class="msi"></div></div></section>`).join("")}<div class="none" hidden>${t("Nothing found")}</div></div></div>
    <div class="m3p m3r hy-blk" data-hyui><div class="m3tabs hy-bh" role="tablist"><button class="m3tab hy-bh-tab on" data-tab="props" role="tab" aria-selected="true">${ico("properties", "")}${t("Properties")}</button><button class="m3tab hy-bh-tab" data-tab="hist" role="tab" aria-selected="false">${ico("history", "")}${t("History")}</button></div><div class="ih"></div><div class="inf"></div><div class="dk"></div><div class="m3hist" role="list" hidden></div></div>
    <div class="m3x" data-hyui><svg class="axes" viewBox="0 0 90 90" aria-label="${t("Axes: drag turns the camera, a click on an axis puts the camera along it")}"></svg></div>`;
  document.body.appendChild(root);
  // Cancel and Save stand top right, Hyimg's one place for a Studio's session actions (ui/hy/actions.js; owner 2026-10-09: «кнопки Done у
  // нас всегда стандартизированы справа вверху, а не внизу»); a click reaches onBar below by its data-a, the keys stay Esc and ⌘↵
  root.appendChild(Object.assign(document.createElement("hy-studio-actions"), { actions: [
    { id: "cancel", label: t("Cancel"), title: t("Close without saving") },   // Esc keeps the work (owner decision 2026-10-10, S-27)
    { id: "save", label: t("Save"), title: t("Save the scene and the card's view and close · ⌘↵"), key: "⌘↵", primary: true }] }));
  const q = s => root.querySelector(s), doc = () => L.e.doc;
  q(".m3title .fp").textContent = L.path; q(".m3title").title = L.path;
  // the scene's title is a plate in the top band (owner 2026-10-06: «3D scene 3d/scenes/…» on top, as a group's title when you are zoomed
  // into the group): the board's stuck group title (canvas.html stickTitles, #gsticky .gst), on the crumb's middle line right after it. It
  // comes in from the left panel's top, where the title stood, and glides along when the crumb grows or the library moves it
  const plate = q(".m3title"); let plateAt = null;
  const placePlate = () => {
    if (document.documentElement.classList.contains("hy-hideui")) return;   // hidden with the rest: it leaves from where it stands
    const c = document.getElementById("crumb"), cb = c && c.getClientRects().length ? c.getBoundingClientRect() : null;
    const l = parseFloat(root.style.getPropertyValue("--l")) || 12, x = Math.round(cb && cb.width ? cb.right + 8 : l), y = Math.round(cb && cb.width ? cb.top + (cb.height - plate.offsetHeight) / 2 : 12);
    if (plateAt && (plateAt[0] !== x || plateAt[1] !== y)) glidePlate();
    plateAt = [x, y]; plate.style.transform = `translate(${x}px, ${y}px)`;
  };
  const glidePlate = () => { plate.classList.add("glide"); clearTimeout(plate._g); plate._g = setTimeout(() => plate.classList.remove("glide"), 320); };
  const place = () => {   // inside the stage, right of the library panel, clear of the dock
    const r = HY.stage.getBoundingClientRect(), inset = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--inset")) || 0;
    root.style.setProperty("--l", (r.left + inset + 12) + "px"); root.style.setProperty("--r", (innerWidth - r.right + 12) + "px");
    // the panels start below the app's top band, as the library and the frame editor's panels do (owner 2026-10-06: «the top panel climbs onto
    // our interface»): under the crumb plate and the window buttons, which stay visible and clickable
    const crumb = document.getElementById("crumb"), band = crumb && crumb.getClientRects().length ? crumb.getBoundingClientRect().bottom + 8 : 0;
    root.style.setProperty("--t", Math.max(r.top + 12, band) + "px"); root.style.setProperty("--b", (innerHeight - r.bottom + 76) + "px");
    if (plateAt) placePlate();
  };
  // the panels follow the window and the library's edge (--inset changes when the library folds or opens)
  const mo = new MutationObserver(place); mo.observe(document.documentElement, { attributes: true, attributeFilter: ["style"] });
  place(); addEventListener("resize", place);
  plate.style.transform = `translate(${parseFloat(root.style.getPropertyValue("--l")) || 12}px, ${parseFloat(root.style.getPropertyValue("--t")) || 12}px)`;   // where the panel's title stood
  requestAnimationFrame(() => { glidePlate(); placePlate(); });
  const crumbRo = new ResizeObserver(() => placePlate()), crumbEl = document.getElementById("crumb"); if (crumbEl) crumbRo.observe(crumbEl);
  // ⌘. hides the interface (the board's :root.hy-hideui, the panels carry data-hyui): the plate goes with it, the view shows no marks (onHide)
  const onHide = ev => { requestAnimationFrame(placePlate); if (ev.detail && ev.detail.on) { L.hov = null; markTree(); } L.need(); };
  document.addEventListener("hy:hideui", onHide);
  L.unplace = () => { removeEventListener("resize", place); mo.disconnect(); crumbRo.disconnect(); document.removeEventListener("hy:hideui", onHide); };
  L.dk = createDialRoot({ mode: "inline", target: q(".dk"), theme: pageTheme() }); oneLine(q(".dk"), { content: K.ai, primary: () => stopLive(true) });   // one-line text fields (P4 S-14, S-25)

  // -- the tree, as in Spline: thin lines show nesting, eye and lock appear on hover. A wrapper without geometry and with one child
  // folds into the row below it unless «все узлы» is on; the search keeps matching rows and the rows they sit in
  let query = "";
  const folds = n => !L.raw && !n.isMesh && n.children.length === 1 && !n.userData.label && !n.userData.mirror && !(n.userData.id && n.userData.kind);
  const chainOf = n => { const c = [n]; while (folds(c[c.length - 1])) c.push(c[c.length - 1].children[0]); return c; };
  const meshCount = n => { let k = 0; n.traverse(m => { if (m.isMesh) k++; }); return k; };
  const kidsOf = n => { if (n.userData.kind === "object") { const w = n.children[0]; return !w || w.isMesh ? [] : w.children; } return n.isMesh || n.userData.kind ? [] : n.children; };
  const hits = (n, label) => { if (!query) return true; if ((label || "").toLowerCase().includes(query)) return true; let f = false; n.traverse(x => { if (!f && ((x.userData.shown || x.userData.label || x.name || "").toLowerCase().includes(query))) f = true; }); return f; };
  // a row's navigation colour: its own (ui.colors[key] in the scene file) or the one of the row it sits in; the key is the thing's id, or
  // «<object id>/<layer path>» for a part of a model (the same path the layer settings use, scene.js layerPath)
  const navOf = () => (doc().ui && doc().ui.colors) || {};
  const keyOf = (n, rec) => { if (rec) return rec.id; const u = unitOf(n); return u && u !== n ? `${u.userData.id}/${layerPath(u, n)}` : ""; };
  const tint = c => c ? ` nc" style="--nc:${navHex(c)}` : "";
  // the app's one padlock (Hyimg's ui/icons.js hyLockIcon, owner 2026-10-07: its shackle swings open and shut); the row just switched
  // from the keys or the menu plays the move once (L.lockGo), a drag switches the drawn icons in place
  const lockIco = (on, id) => window.hyLockIcon ? window.hyLockIcon(on, 13, { cls: "ic", go: L.lockGo === id }) : ico(on ? "lock" : "unlock");
  // several chosen rows (⌘ or ⇧ click in the list, owner 2026-10-07): L.multi holds them with the pick first, as the view's selection of many
  const many = () => (L.multi && L.sel && L.multi[0] === L.sel && L.multi.length > 1 ? L.multi : null);
  const chosenIn = chain => { const m = many(); return !!m && m.some(x => chain.includes(x)); };
  // ih, il: a thing above the row is hidden, locked; inherited, never written into the row's own flags (owner 2026-10-07: «если группу
  // выключаю или включаю lock или глаз, то это не сбрасывает настройки у тех layers»); the row shows it faintly
  const row = (rows, n, guides, label, rec, inh, ih, il) => {
    if (!hits(n, label)) return false;
    const chain = n.userData.kind ? [n] : chainOf(n), last = chain[chain.length - 1], kids = n.userData.kind ? kidsOf(n) : kidsOf(last), open = L.open.has(n.uuid) || !!query;
    const isSel = (L.sel && chain.includes(L.sel)) || chosenIn(chain), within = !isSel && L.sel && n.getObjectById(L.sel.id);
    const kind = n.userData.kind === "light" ? "light" : n.userData.kind === "object" ? (kids.length ? "model" : (rec && rec.src && rec.src.shape) || "mesh") : n.userData.label ? "file" : last.isMesh ? "mesh" : "group";
    const hidden = n.visible === false || last.visible === false, locked = rec && rec.locked, gh = ih && !hidden, gl = il && !locked;
    const name = label || n.userData.shown || n.userData.label || n.name || last.name || (last.isMesh ? t("mesh") : t("node"));
    const sub = last.isMesh ? (last.userData.base && last.userData.base.mat.name ? last.userData.base.mat.name : "") : chain.length > 1 && last.name !== name ? last.name : "";
    const cnt = kids.length ? meshCount(last) : 0, key = keyOf(n, rec), col = navCols()[navOf()[key]] ? navOf()[key] : inh;
    rows.push(`<div class="row hy-hovrow${isSel ? " sel" : ""}${within ? " in" : ""}${hidden ? " hidden" : ""}${gh ? " ghid" : ""}${kids.length && !open ? " closed" : ""}${tint(col)}" data-u="${n.uuid}" data-k="${esc(key)}" title="${esc(chain.map(c => c.name || "·").join(" › "))}">
      ${guides.map(g => `<i class="g${g.on ? " on" : ""}${tint(g.c)}"></i>`).join("")}${kids.length ? `<button class="chev" data-open="${n.uuid}" aria-label="${t("Expand")}">${CHEV()}</button>` : '<span class="chev"></span>'}${ico(hasIco(kind) ? kind : "mesh")}
      <span class="nm">${esc(name)}${n.userData.mirror || last.userData.mirror ? `<small>${t("mirror")}</small>` : ""}${sub ? `<small>${esc(sub)}</small>` : ""}</span>${cnt > 1 ? `<span class="cnt">${cnt}</span>` : ""}
      <span class="acts">${rec ? `<button data-lock="${rec.id}" class="hy-ri${locked ? " keep" : ""}" aria-label="${t("Lock")}">${lockIco(locked, rec.id)}</button>` : gl ? `<span class="inhlk" title="${t("Locked by its group")}">${lockIco(true, "")}</span>` : ""}<button data-eye="${n.uuid}" class="hy-ri${hidden || gh ? " keep" : ""}${gh ? " inh" : ""}" aria-label="${t("Hide or show")}"${gh ? ` title="${t("Hidden by its group")}"` : ""}>${ico(hidden || gh ? "off" : "eye")}</button></span></div>`);
    // the lines under this row's children take its colour, and so do the children that have none of their own
    if (kids.length && open) kids.forEach((c, i) => row(rows, c, [...guides, { on: i < kids.length - 1, c: col }], undefined, undefined, col, ih || hidden, il || !!locked));
    return true;
  };
  const scope = outlinerMicro(L, root, { q, tree: () => tree() });   // «All nodes», the one switch of the files' wrappers (micro.js)
  const secEl = Object.fromEntries(SECS.map(k => [k, q(`.ms[data-s="${k}"]`)]));
  const tree = () => {
    const d = doc(), cardCam = L.camId(), nav = navOf(), out = { objects: [], lights: [], cameras: [], materials: [] }, top = { objects: 0, lights: 0, cameras: 0, materials: 0 }, led = camLed(t);
    for (const o of d.objects) { const u = L.view.units.get(o.id); if (u && row(out.objects, u.obj, [], o.name, o)) top.objects++; }
    for (const l of d.lights) { const u = L.view.units.get(l.id); if (u && row(out.lights, u.obj, [], l.name, l)) top.lights++; }
    // a camera's lock as an object's (owner 2026-10-07: «и чтобы блокировать можно было камеры таким же образом»): locked, its icon is not
    // picked in the view, so it is not dragged there by mistake; the list still picks it
    for (const c of d.cameras) if (!query || c.name.toLowerCase().includes(query)) { top.cameras++; out.cameras.push(`<div class="row hy-hovrow${(L.sel && L.sel.userData.cam === c.id) || chosenIn([L.icons.get(c.id)]) ? " sel" : ""}${tint(navCols()[nav[c.id]] && nav[c.id])}" data-cam="${c.id}" data-k="${esc(c.id)}"><span class="chev"></span>${ico("camera")}<span class="nm">${esc(c.name)}</span>${c.id === cardCam ? led : ""}<span class="acts"><button data-lock="${c.id}" class="hy-ri${c.locked ? " keep" : ""}" aria-label="${t("Lock")}">${lockIco(!!c.locked, c.id)}</button></span></div>`); }
    if (L.look) L.look.rows(out, top, query);   // the card's variant and the look's materials (variants.js)
    for (const k of SECS) { secEl[k].hidden = !out[k].length; secEl[k].querySelector(".msi").innerHTML = out[k].join(""); secEl[k].querySelector(".cnt").textContent = top[k] || ""; }
    q(".tr > .none").hidden = SECS.some(k => out[k].length);
    scope(d); L.lockGo = null; lay();
  };

  // -- the sections: each folds by its title (the app's chevron turns, the rows close with the app's curve), and the line between two open
  // ones is the app's one splitter (ui/split.js, the frame editor's), laid over the line so it takes no room. They move as one stack
  // (sections.js, owner 2026-10-06): a handle moves the section above it and the ones below ride along, a folded section's room goes to the
  // open ones, a double click makes the sections it sized automatic again. Every height is set here in px; folds and sizes are the
  // person's (pref m3.sections, v 2), not the scene's. Sizes kept before the stack (no v: an old drag sized both sides of a line) meant
  // something else and are dropped once (owner 2026-10-07: Lights kept one row of an old drag); the folds stay
  let secSt = (() => { let v = {}; try { v = JSON.parse(HY.pref("m3.sections", "{}")) || {}; } catch (e) { v = {}; }
    const now = v.v === 2;
    return Object.fromEntries(SECS.map(k => { const x = v[k] || {}, o = { size: now && typeof x.size === "number" && x.size >= 0 ? Math.round(x.size) : null, shut: !!x.shut };
      if (now && x.by && SECS.includes(x.by)) o.by = x.by; if (now && x.was > 0) o.was = Math.round(x.was); return [k, o]; })); })();
  const saveSecs = () => HY.setPref("m3.sections", JSON.stringify({ v: 2, ...secSt }));
  const body = k => secEl[k].querySelector(".msb");
  const tr = q(".tr");
  // the shown sections with their rows' height, and the stack's height (a search shows every section, without changing what is kept).
  // A tree's rows gliding open or shut (.kids) count at the height they glide to. How short a section may get: its active and selected rows
  // (owner 2026-10-07: Cameras squeezed shows the active camera; Lights with nothing picked folds down to its title, still open)
  const pinned = k => secEl[k].querySelectorAll(".msi .row.sel, .msi .row.act");
  const measure = () => {
    const list = SECS.filter(k => !secEl[k].hidden).map(k => {
      const msi = secEl[k].querySelector(".msi"), row = msi.querySelector(".row"), rowH = row ? row.offsetHeight : 28;
      let content = msi.offsetHeight; msi.querySelectorAll(".kids").forEach(w => { content += +w.dataset.to - w.offsetHeight; });
      return { k, content, min: pinned(k).length * rowH };
    });
    const head = list.length ? secEl[list[0].k].querySelector(".msh").offsetHeight || 30 : 30;
    return { list, H: tr.clientHeight, o: { head, open: !!query } };
  };
  let secNow = null;   // what is drawn: the list, the height and the layout, where a drag starts from
  // why: "drag" and "resize" follow the pointer and the window; anything else that changes a height (a picked row, a tree opened, a
  // search) glides along the app's curve
  const lay = why => {
    const m = measure(), Lo = layoutSecs(m.list, secSt, m.H, m.o), was = secNow && secNow.L.h; secNow = { ...m, L: Lo };
    if (was && why !== "drag" && why !== "resize" && !document.documentElement.classList.contains("hy-splitting") && SECS.some(k => (Lo.h[k] || 0) !== (was[k] || 0))) glide();
    for (const k of SECS) {
      const s = secEl[k], sh = !!Lo.shut[k];
      s.classList.toggle("shut", sh); s.classList.toggle("fixed", !sh && secSt[k].size != null); s.querySelector(".msh").setAttribute("aria-expanded", String(!sh));
      if (!s.hidden) body(k).style.height = (Lo.h[k] || 0) + "px";
    }
    // a squeezed section keeps its active or selected row in view
    for (const x of m.list) {
      const h = Lo.h[x.k] || 0, r = pinned(x.k)[0], b = body(x.k); if (!r || h >= x.content) continue;
      const top = r.offsetTop, rh = r.offsetHeight;
      if (top < b.scrollTop || top + rh > b.scrollTop + h) b.scrollTop = Math.max(0, top - Math.max(0, (h - rh) / 2));
    }
    // a line stands between two shown sections; its handle works only between two open ones
    tr.querySelectorAll(".msp").forEach(sp => {
      const k = sp.dataset.before, i = m.list.findIndex(x => x.k === k);
      sp.hidden = i < 1; sp.classList.toggle("off", !Lo.handles[k]);
    });
    markCams();
  };
  // the active camera, the one the card looks through (owner 2026-10-07: «почему я не вижу, какая камера активна?»): its row is marked
  // whatever is selected (its name at full contrast and round 15's LED after it); the selected row keeps the list's selection. A click on
  // another camera's icon makes it the active one (a double click renames, as every row, P4 S-45)
  const markCams = () => {
    const act = L.camId();
    for (const r of tr.querySelectorAll(".row[data-cam]")) {
      const on = r.dataset.cam === act; r.classList.toggle("act", on);
      r.title = on ? t("Active camera: the card looks through it") : t("A click on its icon: the card looks through it");
    }
  };
  // a double click on a row's name renames it, a click on a camera's icon makes it the card's (fields.js, P4 S-45)
  treeRename(L, tr, { t, setCamera: id => setCamera(L, id), primary: () => stopLive(true), rename: (id, v) => { const x = findAny(doc(), id); if (x) { x.name = v; L.view.apply(doc()).then(() => L.reload()); L.changed("rename", true); } } });
  const fold = k => {
    const m = measure(); secSt = foldSecs(m.list, secSt, m.H, k, m.o); saveSecs(); glide(); lay("fold");
  };
  // a fold and a double click change the heights along the app's curve; a drag, a window resize and a new row do not glide
  const glide = () => { tr.classList.add("glide"); clearTimeout(tr._g); tr._g = setTimeout(() => tr.classList.remove("glide"), 360); };
  new ResizeObserver(() => { if (tr.isConnected) lay("resize"); }).observe(tr);   // a taller or shorter window gives the stack its new height
  // the rows' height is measured anew whenever it changes, whatever changed it (a tree opened, a search, «all nodes», a thing added); a frame
  // later, so WebKit sees no ResizeObserver loop
  const rowsRo = new ResizeObserver(() => requestAnimationFrame(() => { if (tr.isConnected) lay("content"); }));
  SECS.forEach(k => rowsRo.observe(secEl[k].querySelector(".msi")));
  // a tree's rows glide open and shut (owner 2026-10-07: «когда раскладываешь объект, тоже нет плавной анимации»): the rows under the
  // row are wrapped while they move (one height for 87 rows, not 87), the chevron turns with them, the wrapper goes when they are there
  const KIDS_MS = 240, depth = r => r.querySelectorAll(":scope > .g").length;
  const rowsUnder = r => { const d = depth(r), out = []; for (let n = r.nextElementSibling; n && n.classList.contains("row") && depth(n) > d; n = n.nextElementSibling) out.push(n); return out; };
  const wrapKids = (rows, from, to) => {
    const w = document.createElement("div"); w.className = "kids"; w.dataset.to = to; rows[0].before(w); w.append(...rows);
    w.style.height = from + "px"; void w.offsetHeight; w.style.transition = `height ${KIDS_MS}ms cubic-bezier(.32,.72,0,1)`; w.style.height = to + "px";
    return w;
  };
  const rowOf = u => tr.querySelector(`.row[data-u="${CSS.escape(u)}"]`);
  tr.addEventListener("click", ev => {
    const o = ev.target.closest("[data-open]"); if (!o) return;
    ev.stopImmediatePropagation();
    const u = o.dataset.open, opening = !L.open.has(u), still = matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (opening) {
      L.open.add(u); tree(); if (still) return;
      const r = rowOf(u), kids = r ? rowsUnder(r) : []; if (!kids.length) return;
      r.classList.add("closed"); void r.offsetHeight; r.classList.remove("closed");   // the chevron turns from where it was
      const w = wrapKids(kids, 0, kids.reduce((n, x) => n + x.offsetHeight, 0));
      setTimeout(() => { if (w.isConnected) { w.replaceWith(...w.childNodes); lay("content"); } }, KIDS_MS + 30);
    } else {
      const r = rowOf(u), kids = r && !still ? rowsUnder(r) : [];
      if (!kids.length) { L.open.delete(u); tree(); return; }
      r.classList.add("closed"); wrapKids(kids, kids.reduce((n, x) => n + x.offsetHeight, 0), 0); lay("content");
      setTimeout(() => { L.open.delete(u); tree(); }, KIDS_MS + 30);
    }
  }, true);
  tr.querySelectorAll(".msp").forEach(sp => window.hySplit && window.hySplit(sp, {
    start: () => (secNow && secNow.L.handles[sp.dataset.before] ? { ...secNow, st: secSt } : null),
    move: (dy, c) => { if (!c) return; secSt = dragSecs(c.list, c.st, c.H, sp.dataset.before, dy, c.L, c.o); lay("drag"); },
    end: c => { if (c) saveSecs(); },
    reset: () => { if (!secNow) return; secSt = resetSecs(secNow.list, secSt, sp.dataset.before); saveSecs(); glide(); lay("reset"); },
  }));
  const byUuid = u => L.view.scene.getObjectByProperty("uuid", u);
  const markTree = () => root.querySelectorAll(".tr .row[data-u]").forEach(r => { const n = byUuid(r.dataset.u); r.classList.toggle("hov", !!(L.hov && n && (n === L.hov || chainOf(n).includes(L.hov)))); });
  q(".tr").addEventListener("click", ev => {
    const h = ev.target.closest(".msh"); if (h) return fold(h.parentNode.dataset.s);
    const o = ev.target.closest("[data-open]"); if (o) { const u = o.dataset.open; L.open.has(u) ? L.open.delete(u) : L.open.add(u); return tree(); }
    const v = ev.target.closest("[data-eye]"); if (v) return toggleSeen(L, byUuid(v.dataset.eye));
    const lk = ev.target.closest("[data-lock]"); if (lk) return lockThing(lk.dataset.lock);
    const add = ev.metaKey || ev.ctrlKey || ev.shiftKey;
    const c = ev.target.closest("[data-cam]"); if (c) { const icon = L.icons.get(c.dataset.cam); if (icon) return add ? choose(icon) : (L.multi = null, pick(L, icon)); L.camSel = c.dataset.cam; return panel("camera"); }
    const r = ev.target.closest(".row[data-u]"); if (!r) return;
    const n = byUuid(r.dataset.u); if (!n) return; const ch = n.userData.kind ? [n] : chainOf(n), to = ch[ch.length - 1].isMesh ? head(unitOf(n), ch[ch.length - 1]) : n;
    if (add) return choose(to);
    L.multi = null; pick(L, to);
  });
  // ⌘ or ⇧ click: the row joins the chosen ones or leaves them; the last one added is the pick (the panels', the gizmo's)
  const choose = n => {
    const cur = many() || (L.sel ? [L.sel] : []), rest = cur.filter(x => x !== n), next = cur.includes(n) ? rest : [n, ...rest];
    L.multi = null; pick(L, next[0] || null); L.multi = next.length > 1 ? next : null; tree(); L.need();
  };
  // a locked thing stays picked: its panel shows it locked and grey, the gizmo leaves it (attach)
  const setLock = (x, on) => { if (on) x.locked = true; else delete x.locked; if (L.sel && ((unitOf(L.sel) && unitOf(L.sel).userData.id === x.id) || L.sel.userData.cam === x.id)) { attach(L); panel(); } };
  const lockThing = id => { const x = findAny(doc(), id); if (!x) return; setLock(x, !x.locked); L.changed("lock", true); L.lockGo = id; tree(); };
  // Photoshop's eye drag (Hyimg's ui/eyedrag.js, owner 2026-10-07): a press on an eye or a lock switches its row, every row passed while
  // held takes the same state, past a section's edge its rows scroll on; the scene's undo gets one step for the drag. The click handler
  // above stays for the keys
  if (window.hyEyeDrag) {
    let seenQ = Promise.resolve();
    const redraw = () => { seenQ = seenQ.then(() => L.view.apply(doc())).then(() => { tree(); L.need(); }); };
    // a press on one of several chosen rows sets every chosen row (owner 2026-10-07: «Shift + выбор двух и более объектов ... блокирую все
    // выбранные или выключаю все выбранные»); a row outside the choice switches alone
    const chosenRows = (b, done, key) => { const r = b.closest(".row"); if (!r.classList.contains("sel") || !many()) return [];
      return [...q(".tr").querySelectorAll(".row.sel")].filter(x => x !== r).map(x => x.querySelector(key)).filter(x => x && !done.has(x.dataset.eye || x.dataset.lock)); };
    window.hyEyeDrag(q(".tr"), { selector: "[data-eye]", key: b => b.dataset.eye, get: b => !b.closest(".row").classList.contains("hidden"),
      also: (b, on, done) => { let k = 0; chosenRows(b, done, "[data-eye]").forEach(x => { done.add(x.dataset.eye); const n = byUuid(x.dataset.eye); if (!n || seenFlag(L, n) === !on) return; setSeen(L, n, !on); x.closest(".row").classList.toggle("hidden", !on); k++; }); if (k) redraw(); return k; },
      set: (b, on) => { const n = byUuid(b.dataset.eye); if (!n) return; setSeen(L, n, !on); b.closest(".row").classList.toggle("hidden", !on); redraw(); },
      end: k => { if (k) seenQ.then(() => L.changed("seen", true)); } });
    window.hyEyeDrag(q(".tr"), { selector: "[data-lock]", key: b => b.dataset.lock, get: b => { const x = findAny(doc(), b.dataset.lock); return !!(x && x.locked); },
      also: (b, on, done) => { let k = 0; chosenRows(b, done, "[data-lock]").forEach(x => { done.add(x.dataset.lock); const r = findAny(doc(), x.dataset.lock); if (!r || !!r.locked === on) return; setLock(r, on); x.classList.toggle("keep", on); const ic = x.querySelector(".hy-lock"); if (ic) ic.classList.toggle("locked", on); k++; }); return k; },
      set: (b, on) => { const x = findAny(doc(), b.dataset.lock); if (!x) return; setLock(x, on); b.classList.toggle("keep", on);
        const ic = b.querySelector(".hy-lock"); if (ic) ic.classList.toggle("locked", on); else b.innerHTML = lockIco(on, ""); },   // in place: the shackle swings
      end: k => { if (k) L.changed("lock", true); setTimeout(() => { if (q(".tr").isConnected) tree(); }, 300); } });   // the list redraws once the shackle has moved
  }

  // -- a row's right click: the app's own menu (the board's #ctx, its items ui/menu.js hyMenuItem) with the colour row on top, the sticky
  // notes' circles and «no colour» first. The colour is the scene file's (ui.colors), kept apart from the scene's undo and reset: it is
  // how the person finds things, not a change of the scene. A right click on one of several chosen rows colours them all (owner 2026-10-07)
  const setNav = (keys, name) => {
    const d = doc(), ui = d.ui = d.ui || {}, c = ui.colors = ui.colors || {};
    for (const key of keys) if (name) c[key] = name; else delete c[key];
    if (!Object.keys(c).length) delete ui.colors; if (!Object.keys(ui).length) delete d.ui;
    writeUi(L); tree();   // into the file now, the studio's Save and Cancel keep it (P4 S-20: the colours were never written)
  };
  // Esc closes the menu (the board's own rule) and nothing more: the editor's Esc would drop the pick too
  let ctxMine = false;
  addEventListener("keydown", e => { if (e.key === "Escape" && ctxMine) { ctxMine = false; e.stopPropagation(); } }, { capture: true, signal: L.ac.signal });
  document.addEventListener("pointerdown", e => { if (!e.target.closest("#ctx")) ctxMine = false; }, { capture: true, signal: L.ac.signal });
  q(".tr").addEventListener("contextmenu", ev => {
    const r = ev.target.closest(".row[data-k]"); const m = document.getElementById("ctx");
    ev.preventDefault(); ev.stopPropagation(); if (!r || !r.dataset.k || !m) return;
    const key = r.dataset.k, cur = navOf()[key] || "", n = r.dataset.u ? byUuid(r.dataset.u) : null, rec = findAny(doc(), key);
    const keys = r.classList.contains("sel") && many() ? [...new Set([...q(".tr").querySelectorAll(".row.sel[data-k]")].map(x => x.dataset.k).filter(Boolean))] : [key];
    const items = [], mi = k => (window.hyToolIcon && hyToolIcon(k, 15)) || "";
    if (n) items.push(hyMenuItem('data-m3="seen"', mi(n.visible === false ? "eye" : "eyeoff"), n.visible === false ? t("Show") : t("Hide")));
    if (rec && n && unitOf(n) === n) items.push(hyMenuItem('data-m3="lock"', mi(rec.locked ? "lockOpen" : "lock"), rec.locked ? t("Unlock") : t("Lock")));
    const cols = window.hyMenuColors ? hyMenuColors(cur) : `<div class="msw">${["", ...Object.keys(OLD_COLS)].map(k => `<button data-color="${k}" style="--c:${OLD_COLS[k] || "transparent"}" aria-label="${k || t("No colour")}"></button>`).join("")}</div>`;
    m.innerHTML = cols + items.join("");
    m.onclick = e => {
      const b = e.target.closest("[data-color],[data-m3]"); if (!b) return; m.classList.remove("open"); ctxMine = false;
      const pc = window.hyColorPick ? hyColorPick(e) : b.dataset.color ?? null;   // Hyimg's own reading of the swatch row; an older one: the button's
      if (pc !== null) return setNav(keys, pc);
      if (b.dataset.m3 === "seen") return toggleSeen(L, n);
      if (b.dataset.m3 === "lock") return lockThing(key);
    };
    m.classList.add("open"); ctxMine = true;
    const w = m.offsetWidth, hh = m.offsetHeight;
    m.style.left = Math.min(ev.clientX, innerWidth - w - 8) + "px"; m.style.top = Math.min(ev.clientY, innerHeight - hh - 8) + "px";
  });
  q(".tr").addEventListener("mouseover", ev => { const r = ev.target.closest(".row[data-u]"); const n = r ? byUuid(r.dataset.u) : null; if (n !== L.hov) { L.hov = n; L.need(); } });
  q(".tr").addEventListener("mouseleave", () => { L.hov = null; L.need(); });
  q("[data-q]").addEventListener("input", ev => { query = ev.target.value.trim().toLowerCase(); tree(); }); searchKeys(q("[data-q]"), () => { query = ""; tree(); });

  // -- the inspector: no tabs, it shows what is picked; with nothing picked, the scene (the card's camera, frame, background, world)
  let syncing = false, dialN = 0;
  const dial = (name, cfg, apply, onAction) => {
    if (live !== L) return;   // a closed session never draws a panel: DialKit shows every panel it knows in every root
    if (L.kit) L.kit.destroy();
    if (!Object.keys(cfg).some(k => k.startsWith(K.reset))) cfg[K.reset] = { type: "action" };
    const act = a => { if (a.endsWith(K.reset)) return resetPane(L); if (onAction) onAction(a); };
    L.kit = createDialKit(name, cfg, { id: `m3-${Date.now().toString(36)}-${++dialN}`, onAction: act });   // a fresh id, also across sessions: DialKit keeps an id's values
    requestAnimationFrame(() => resetState(L));
    // DialKit hands changes over in batches: the last value of a drag can arrive while the editor itself writes the panel (quiet below).
    // Dropped then, it was applied at the next touch of any control (owner 2026-10-04: the transparency moved the camera; it was the end
    // of a «Широкий ↔ изометрия» drag). It waits and is applied right after; apply() acts only on what differs from what it knows
    L.kit.subscribe(v => { if (syncing) pend = v; else if (!holdText(v, apply)) apply(v); }, false);   // a name typed: once, at ↵ (micro.js)
    L.applyNow = apply;
  };
  let pend = null;
  const quiet = vals => {
    syncing = true; try { L.kit.setValues(vals); } finally { syncing = false; }
    if (pend) { const v = pend; pend = null; queueMicrotask(() => { if (L.kit && L.applyNow) L.applyNow(v); }); }
  };
  const edit = async fn => { fn(doc()); await L.view.apply(doc()); L.need(); L.changed("edit"); };
  const trs = n => { const d = 180 / Math.PI, e = new THREE.Euler().setFromQuaternion(n.quaternion, "XYZ");
    return { pos: { X: r1(n.position.x * 100), Y: r1(-n.position.z * 100), Z: r1(n.position.y * 100) }, rot: { X: r1(e.x * d), Y: r1(-e.z * d), Z: r1(e.y * d) } }; };
  const sync = () => { const p = picked(L); if (!L.kit || p.kind !== "object") return; const tr = trs(p.unit); quiet({ [K.pos]: tr.pos, [K.rot]: tr.rot }); };
  const inf = html => { q(".inf").innerHTML = (L.why ? `<p class="hy-hint m3why">${lockIco(true, "")}<span>${esc(L.why)}</span></p>` : "") + (html || ""); };
  // why the pick's settings are grey (owner 2026-10-07: «и настройки серым цветом disabled для них»): locked itself, or a part of a locked
  // or hidden thing; null while they can change
  const whyGrey = p => {
    const x = p.kind === "camera" ? findAny(doc(), p.id) : p.id ? findAny(doc(), p.id) : null; if (!x) return null;
    if (p.kind !== "layer") return x.locked ? t("Locked") : null;
    if (x.locked) return t("Locked by its group");
    for (let a = p.node.parent; a; a = a.parent) { if (a.visible === false) return t("Hidden by its group"); if (a === p.unit) break; }
    return x.hidden ? t("Hidden by its group") : null;
  };
  const ih = (kind, title, sub) => { q(".ih").innerHTML = `${ico(hasIco(kind) ? kind : "mesh")}<div><b>${esc(title)}</b>${sub ? `<span>${esc(sub)}</span>` : ""}</div>`; };
  const panel = force => {
    if (!force && L.lmSel && L.look) return L.look.pane();   // a material or the card's variant (variants.js, materials.js)
    if (L.kit) { L.kit.destroy(); L.kit = null; }
    const p = picked(L), k = force || p.kind; L.why = force ? null : whyGrey(p); q(".dk").classList.toggle("m3dis", !!L.why); inf(""); L.paneKind = k === "object" || k === "layer" || k === "light" || k === "camera" ? k : "scene";
    if (k === "object" || k === "layer") { const o = doc().objects.find(x => x.id === p.id); ih(k === "layer" ? (p.node.isMesh ? "mesh" : "group") : (o && o.src && o.src.type === "model" ? "model" : (o && o.src && o.src.shape) || "mesh"), k === "layer" ? (p.node.userData.shown || p.node.userData.label || p.node.name || t("Layer")) : o ? o.name : "", k === "layer" ? t("layer of “{name}”", { name: o ? o.name : "" }) : t("object")); return objPane(); }
    if (k === "light") { const l = doc().lights.find(x => x.id === p.id); ih("light", l ? l.name : t("Light"), l ? t(LIGHT_NAMES[l.type]).toLowerCase() : ""); return lightPane(); }
    if (k === "camera") { const c = doc().cameras.find(x => x.id === (p.kind === "camera" ? p.id : L.camSel)); ih("camera", c ? c.name : t("Camera"), c && c.id === L.camId() ? t("active camera") : t("camera")); return camPane(); }
    ih("model", t("Scene"), t("nothing selected")); scenePane();
  };

  const objPane = () => {
    const p = picked(L);
    const o = doc().objects.find(x => x.id === p.id); if (!o) return;
    if (p.kind === "layer") {
      const n = p.node, ov = (o.layers || {})[p.path] || {}, m0 = (() => { let m = null; n.traverse(x => { if (!m && x.isMesh) m = x; }); return m; })();
      inf(`<div class="real">${esc(o.name)} › ${esc(shownPath(p.path).join(" › "))}${m0 && m0.userData.base && m0.userData.base.mat.name ? `<br>${esc(t("material in the file: {name}", { name: m0.userData.base.mat.name }))}` : ""}</div>`);
      const color = ov.color || (m0 && m0.material.color ? "#" + m0.material.color.getHexString() : "#b8b8b4");
      return dial(n.userData.shown || n.userData.label || n.name || t("Layer"), { [K.color]: color, [K.material]: { type: "select", options: Object.values(FIN_NAME), default: FIN_NAME[ov.finish || ""] }, [K.visible]: !ov.hidden, [K.resetLayer]: { type: "action" } }, v => edit(() => {
        const L2 = o.layers = o.layers || {}, cur = L2[p.path] = L2[p.path] || {};
        if (v[K.color] !== color || cur.color) cur.color = v[K.color]; cur.finish = FIN_KEY[v[K.material]] || undefined; cur.hidden = !v[K.visible] || undefined;
        for (const k of Object.keys(cur)) if (cur[k] === undefined) delete cur[k]; if (!Object.keys(cur).length) delete L2[p.path];
      }).then(tree), () => edit(() => { if (o.layers) delete o.layers[p.path]; }).then(() => { tree(); panel(); }));
    }
    const u = p.unit, tr = trs(u), s = o.src || {}, cfg = { [K.name]: { type: "text", default: o.name } };
    cfg[K.pos] = { X: [tr.pos.X, -300, 300, 0.1], Y: [tr.pos.Y, -300, 300, 0.1], Z: [tr.pos.Z, -100, 300, 0.1] };
    cfg[K.rot] = { X: [tr.rot.X, -180, 180, 1], Y: [tr.rot.Y, -180, 180, 1], Z: [tr.rot.Z, -180, 180, 1] };
    if (s.type === "prim") {
      const sz = s.size.map(x => r1(x * 100));
      cfg[K.size] = s.shape === "sphere" ? { [K.diam]: [sz[0], 0.5, 300, 0.1] } : s.shape === "cylinder" ? { [K.diam]: [sz[0], 0.5, 300, 0.1], [K.height]: [sz[2], 0.5, 300, 0.1] } : s.shape === "plane" ? { X: [sz[0], 1, 1000, 0.5], Y: [sz[1], 1, 1000, 0.5] } : { X: [sz[0], 0.5, 300, 0.1], Y: [sz[1], 0.5, 300, 0.1], Z: [sz[2], 0.5, 300, 0.1] };
    } else cfg[K.scale] = [Math.round((o.scale || [1])[0] * 100), 1, 500, 1];
    if (s.type !== "model") cfg[K.color] = o.color || "#b8b8b4";
    cfg[K.material] = { type: "select", options: Object.values(FIN_NAME), default: FIN_NAME[o.finish || ""] };
    cfg[K.shadow] = !!o.shadow_only; cfg[K.visible] = !o.hidden;
    cfg[K.gen] = { [K.mask]: (L.view.units.get(o.id) || {}).mask || o.mask || "#2f6fe4", [K.ai]: { type: "text", default: o.ai || "" } };
    cfg[K.del] = { type: "action" };
    inf(`<div class="real">${esc(s.type === "model" ? t("model {id}", { id: s.model }) : s.type === "file" ? s.path : s.type === "node" ? t("geometry from Blender (scene.glb)") : t("simple shape"))}</div>`);
    dial(o.name, cfg, v => edit(() => {
      if (v[K.name] !== o.name) { o.name = v[K.name]; }
      const P = v[K.pos], R = v[K.rot], d = Math.PI / 180;
      u.position.set(P.X / 100, P.Z / 100, -P.Y / 100); u.quaternion.setFromEuler(new THREE.Euler(R.X * d, R.Z * d, -R.Y * d, "XYZ")); readBack(L.view, o.id);
      if (v[K.scale]) o.scale = [1, 1, 1].map(() => v[K.scale] / 100);
      const S = v[K.size]; if (S) { const z = s.size; if (s.shape === "sphere") s.size = [S[K.diam] / 100, S[K.diam] / 100, S[K.diam] / 100]; else if (s.shape === "cylinder") s.size = [S[K.diam] / 100, S[K.diam] / 100, S[K.height] / 100]; else if (s.shape === "plane") s.size = [S.X / 100, S.Y / 100, 0]; else s.size = [S.X / 100, S.Y / 100, S.Z / 100]; if (JSON.stringify(z) === JSON.stringify(s.size)) s.size = z; }
      if (v[K.color]) o.color = v[K.color];
      o.finish = FIN_KEY[v[K.material]] || undefined; if (!o.finish) delete o.finish;
      o.shadow_only = v[K.shadow] || undefined; if (!o.shadow_only) delete o.shadow_only;
      o.hidden = !v[K.visible] || undefined; if (!o.hidden) delete o.hidden;
      o.mask = v[K.gen][K.mask]; o.ai = v[K.gen][K.ai];
    }).then(tree), () => removeThing(L, o.id));
  };
  const lightPane = () => lightPaneOf(L, { t, K, doc, picked, dial, edit, inf, helpers, pick, panel, tree, removeThing, setTool, coordCfg, coordVals, coordSet, sameVals,
    LIGHT_NAMES, LIGHT_W, hexOf, linOf, studio: !!L.look, blenderSees: () => !!L.look && L.look.light() === "own", useOwn: () => L.look && L.look.setLight("own") });
  // -- one camera block for the Scene panel (the card's camera) and a camera's own panel (owner 2026-10-07: «почему настройки разные в
  // камере и в начальной главной настройке, Wide ↔ isometric отсутствует»): the same controls in the same order. What does not apply to a
  // camera the card does not look through stays in its place, greyed, its reason in its tooltip (greyCtl)
  const camBlock = c => {
    const d = doc(), it = HY.board.items[L.id], on = c.id === L.camId(), FREE = t("Free"), ratio = it.lock || FREE;
    let cur = orbitVals(orbitOf(L, c)), crd = coordVals(c), dollyCur = dollyOf(c.lens);   // what the controls show (see quiet: a rounded value is no move)
    const cfg = {
      [K.camera]: { type: "select", options: d.cameras.map(x => ({ value: x.id, label: x.name })), default: L.camId() },
      [K.lens]: [Math.round(c.lens), DOLLY[0], DOLLY[1], 1], [K.frame]: { type: "select", options: [FREE, ...RATIOS], default: ratio },
      [K.dolly]: [dollyCur, 0, 100, 1],
      [K.campos]: orbitCfg(orbitOf(L, c)), [K.coords]: coordCfg(c), [K.cammore]: camMoreCfg(c),
    };
    const moved = () => { if (on) L.recam(); else { helpers(L); L.need(); } L.changed("camera"); };
    // true when the change was the camera's; the Scene panel goes on with its own controls otherwise
    const apply = v => {
      const KP = v[K.campos];
      if (KP && Object.keys(cur).some(k => KP[k] !== cur[k])) { cur = { ...KP }; setOrbit(L, c, KP); crd = coordVals(c); quiet({ [K.coords]: crd }); return true; }
      const C = v[K.coords]; if (C && !sameVals(C, crd)) { crd = JSON.parse(JSON.stringify(C)); coordSet(c, C); moved(); cur = orbitVals(orbitOf(L, c)); quiet({ [K.campos]: cur }); return true; }
      if (camMoreSet(c, v[K.cammore])) { moved(); return true; }
      if (v[K.camera] !== L.camId()) { setTimeout(() => setCamera(L, v[K.camera])); return true; }
      if (on && v[K.frame] !== ratio) { HY.frame(L.id, v[K.frame] === FREE ? "free" : v[K.frame]); return true; }
      if (v[K.dolly] !== dollyCur) {   // the dolly zoom: the lens and the distance together, the lens slider follows
        dollyCur = v[K.dolly]; dollyAny(L, c, lensOf(dollyCur)); cur = orbitVals(orbitOf(L, c)); crd = coordVals(c);
        quiet({ [K.lens]: Math.round(c.lens), [K.campos]: cur, [K.coords]: crd }); return true;
      }
      if (Math.round(c.lens) !== v[K.lens]) {   // the lens alone zooms; the dolly slider shows where it now is
        c.lens = v[K.lens]; if (on) L.recam(); else L.need(); L.changed("lens"); dollyCur = dollyOf(c.lens); quiet({ [K.dolly]: dollyCur }); return true;
      }
      return false;
    };
    const greys = on ? [] : [[K.frame, t("The frame is the card's: make this camera active to change it")]];
    if (it.lock && !RATIOS.includes(it.lock)) cfg[K.frame].options.push(it.lock), cfg[K.frame].default = it.lock;   // W × H typed in: its own ratio
    return { cfg, apply, greys, on };
  };
  // the card's output size under Frame (owner 2026-10-07: «вот это в рендере я бы убрал, оно мешает, лучше это добавить где-то справа в
  // настройках. Потому что там же тоже размер должен быть»): W × H px with the app's W ↔ H link (ui/icons.js linkWH, look.css .hy-link),
  // the presets on the long side and ⇄ turning the frame. It is the card's (it.res, frame.js outSize): it shapes the card on the board and
  // is the size of Blender's «Render» (blender.js); each change is one step of the board's undo. The board's frame bar is off (frameBar)
  const camOf = () => (doc().cameras || []).find(x => x.id === L.camId());
  L.outSize = () => outSize(HY.board.items[L.id], camOf(), doc());
  let resLink = HY.pref("m3.reslink", "1") !== "0";
  const setRes = (W, H) => {
    const it = HY.board.items[L.id], before = HY.snap(), a = it.w / it.h;
    it.res = [W, H];
    if (Math.abs(W / H - a) > 0.01 * a) { Object.assign(it, reshape(it, W, H)); if (it.lock) it.lock = ratioKey(W, H, RATIOS); }
    HY.commit(before, t("3D: output size {w} × {h} px", { w: W, h: H })); framed(L.id);
  };
  const icon = (n, z, line) => (window.hyIcon ? window.hyIcon(n, z, line) : "");
  const sizeRow = (on, tries = 0) => requestAnimationFrame(() => {   // once DialKit has drawn the panel: under its Frame row
    const fr = [...q(".dk").querySelectorAll(".dialkit-select-trigger")].find(x => { const l = x.querySelector(".dialkit-select-label"); return l && l.textContent.trim() === K.frame; });
    if (!fr) { if (tries < 30) sizeRow(on, tries + 1); return; }
    q(".dk").querySelectorAll(".m3res").forEach(x => x.remove());
    const box = document.createElement("div"); box.className = "m3res";
    box.innerHTML = `<div class="wh"><label><span>W</span><input data-k="w" inputmode="numeric" autocomplete="off" aria-label="${t("Width, px")}"></label>`
      + `<button type="button" class="lk" data-link title="${t("Keep the proportions")}" aria-label="${t("Keep the proportions")}">${icon("linkWH", 16).replace("<svg", '<svg class="hy-link"')}</button>`
      + `<label><span>H</span><input data-k="h" inputmode="numeric" autocomplete="off" aria-label="${t("Height, px")}"></label><span class="u">px</span></div>`
      + `<div class="pre"><div class="seg">${PRESETS.map(n => `<button type="button" data-long="${n}" title="${t("{n} px on the long side", { n })}">${n}</button>`).join("")}</div>`
      + `<button type="button" class="lk" data-flip title="${t("Turn the frame")}" aria-label="${t("Turn the frame")}">${icon("orientation", 15, 2)}</button></div>`;
    (fr.closest(".dialkit-select-row") || fr).after(box);
    const ins = [...box.querySelectorAll("input")], link = box.querySelector("[data-link]"), flip = box.querySelector("[data-flip]");
    const sync = () => {
      if (!box.isConnected) return; const s = L.outSize(), it = HY.board.items[L.id];
      ins.forEach((x, i) => { if (document.activeElement !== x && x.value !== String(s[i])) x.value = s[i]; });
      box.querySelectorAll("[data-long]").forEach(b => b.setAttribute("aria-pressed", String(+b.dataset.long === Math.max(...s))));
      link.classList.toggle("on", resLink); link.setAttribute("aria-pressed", String(resLink)); flip.disabled = Math.abs(it.w - it.h) < 1;
    };
    L.syncRes = sync; sync(); if (window.hySeg) window.hySeg(box);
    if (!on) {   // a camera the card does not look through: greyed with the reason, as Frame
      box.classList.add("m3na"); box.setAttribute("aria-disabled", "true"); box.title = t("The size is the card's: make this camera active to change it");
      for (const ev of ["pointerdown", "mousedown", "click", "keydown", "focusin"]) box.addEventListener(ev, e => { e.preventDefault(); e.stopPropagation(); if (e.target.blur) e.target.blur(); }, true);
      return;
    }
    const typed = x => {
      const v = Math.round(+x.value); if (!(v >= 16 && v <= 16384)) return sync();
      const it = HY.board.items[L.id], s = L.outSize(), k = x.dataset.k;
      const [W, H] = resLink ? keepShape(it, k, v) : k === "w" ? [v, s[1]] : [s[0], v];
      if (W !== s[0] || H !== s[1]) setRes(W, H); else sync();
    };
    sizeKeys(ins, typed, sync, () => stopLive(true));   // ↵, Esc, ↑ ↓ and Tab (fields.js, P4 S-56)
    scrubSize(ins, typed, sync);   // the W and H letters drag the size (micro.js)
    link.addEventListener("click", () => { resLink = !resLink; HY.setPref("m3.reslink", resLink ? "1" : "0"); sync(); });
    box.querySelectorAll("[data-long]").forEach(b => b.addEventListener("click", () => { const it = HY.board.items[L.id], [W, H] = atLong(+b.dataset.long, it.w / it.h), s = L.outSize(); if (W !== s[0] || H !== s[1]) setRes(W, H); }));
    flip.addEventListener("click", () => HY.frame(L.id, "flip"));
  });
  // a control that does not apply here: greyed, its reason in its tooltip, a press does nothing (DialKit has no disabled state of its own)
  const greyCtl = list => requestAnimationFrame(() => {
    for (const [label, why] of list) {
      const el = [...q(".dk").querySelectorAll(".dialkit-select-trigger, .hy-slider")].find(x => {
        const l = x.querySelector(".dialkit-select-label, .hy-slider-l"); return l && l.textContent.trim() === label; });
      if (!el || el.classList.contains("m3na")) continue;
      el.classList.add("m3na"); el.setAttribute("aria-disabled", "true"); el.title = why;
      el.querySelectorAll("button, input").forEach(x => { x.tabIndex = -1; });
      for (const ev of ["pointerdown", "mousedown", "click", "keydown"]) el.addEventListener(ev, e => { e.preventDefault(); e.stopPropagation(); }, true);
    }
  });
  // a camera's own actions (owner 2026-10-07): «Original camera» when it came from a picture (studio.angles[id].camera0), «Sync with the
  // scene» writes its view into scene.json now (Blender and the agent's tools read it there; nothing else writes it in the background)
  const camActs = (c, cfg) => { if (studioAngle(doc(), c.id) && studioAngle(doc(), c.id).camera0) cfg[K.original] = { type: "action" }; cfg[K.syncscene] = { type: "action" }; return cfg; };
  const camAct = (c, a) => { if (a === K.original) { originalCamera(L, c.id); return true; } if (a === K.syncscene) { syncCamera(L, c.id); return true; } return false; };
  const camPane = () => {
    const d = doc(), p = picked(L), cardCam = L.camId(), c = d.cameras.find(x => x.id === (p.kind === "camera" ? p.id : L.camSel)) || d.cameras.find(x => x.id === cardCam); L.camSel = c.id;
    const B = camBlock(c), cfg = { ...B.cfg };
    if (c.id !== cardCam) cfg[K.showcard] = { type: "action" };
    camActs(c, cfg);
    cfg[K.del] = { type: "action" };
    dial(c.name, cfg, v => { B.apply(v); }, a => { if (a === K.showcard) setCamera(L, c.id); else if (!camAct(c, a)) removeThing(L, c.id); });
    greyCtl(B.greys); sizeRow(B.on);
  };
  const scenePane = () => {
    const d = doc(), it = HY.board.items[L.id], cardCam = L.camId(), c = d.cameras.find(x => x.id === cardCam) || d.cameras[0], CB = camBlock(c);
    const w = d.world = d.world || {}, bg = Object.assign({ transparent: false, color: hexOf((w.color || [0.18, 0.18, 0.18]).map(x => x * (w.strength ?? 1))), opacity: 100 }, it.bg || {});
    inf(`<p class="hy-hint m3hint">${t("<b>⌥ + drag</b> turns the camera · <b>Space + drag</b> or <b>right drag</b> moves the view · <b>wheel</b> zooms")}</p>`);   // the app's footnote (ui/look.css .hy-hint): the controls, key words lit
    // the camera block keeps what «Широкий ↔ изометрия» shows: compared with the lens it rounds differently, and every later change of the
    // panel (the background's transparency) took that for a move of the slider and drove the camera in again (owner 2026-10-04)
    dial(t("Scene"), {
      ...CB.cfg,
      [K.bg]: { [K.transparent]: bg.transparent, [K.color]: bg.color, [K.transparency]: [100 - bg.opacity, 0, 100, 1] },   // the owner reads it as see-through: 0 is a solid background (2026-10-04)
      [K.world]: { [K.color]: hexOf(w.color || [0.18, 0.18, 0.18]), [K.strength]: [w.strength ?? 1, 0, 5, 0.05], _collapsed: true },
      [K.highlight]: { type: "select", seg: true, options: [{ value: "ghost", label: t("Ghost") }, { value: "outline", label: t("Outline") }], default: L.hl },
      [K.pull]: { [K.pivot]: { type: "select", seg: true, options: PIVOTS.map(p => ({ value: p.value, label: t(p.label) })), default: HY.pref("m3.pull.pivot", PULL.pivot) }, [K.gel]: [+HY.pref("m3.pull.gel", PULL.gel), 1, 10, 0.5], _collapsed: true },
      ...camActs(c, {}),
      [K.newcam]: { type: "action" }, [K.allcams]: { type: "action" },
    }, v => {
      if (CB.apply(v)) return;
      if (v[K.pull]) { HY.setPref("m3.pull.gel", String(v[K.pull][K.gel])); if (v[K.pull][K.pivot]) HY.setPref("m3.pull.pivot", v[K.pull][K.pivot]); }
      if (v[K.highlight] && v[K.highlight] !== L.hl) { L.hl = v[K.highlight]; HY.setPref("m3.hl", L.hl); L.need(); }
      const B = v[K.bg], nb = { transparent: B[K.transparent], color: B[K.color], opacity: 100 - B[K.transparency] };
      if (JSON.stringify(nb) !== JSON.stringify(Object.assign({}, bg, it.bg || {}))) { const before = HY.snap(); HY.board.items[L.id].bg = nb; Object.assign(bg, nb); HY.commit(before, t("3D: card background")); remember(L, "bg"); }
      const W = v[K.world]; if (W && (hexOf(w.color || [0.18, 0.18, 0.18]) !== W[K.color] || (w.strength ?? 1) !== W[K.strength])) edit(() => { w.color = linOf(W[K.color]); w.strength = W[K.strength]; }); else L.need();
    }, async a => {
      if (camAct(c, a)) return;
      if (a === K.newcam) addThing(L, "camera");
      else { const ids = await placeCards(L.path, L.e, doc().cameras.map(x => x.id)); if (!ids.length) HY.toast(t("Every camera already has a card")); }
    });
    sizeRow(true);
  };

  // -- the toolbar
  const menu = q(".menu");
  // the project's models in «+», after the shapes: one line each, or a hint where to put one (2026-10-05: no model by default)
  const fillModels = async () => {
    const list = await projectModels();
    menu.querySelectorAll("[data-models]").forEach(x => x.remove());
    const at = menu.querySelector('[data-add="area"]'), add = h => at.insertAdjacentHTML("beforebegin", h);
    if (!list.length) add(hyMenuItem(`data-models disabled title="${esc(t("Model: 3d/models/<name>/model.json and its .glb in the board's folder"))}"`, ico("model"), t("No models in 3d/models")));
    for (const m of list) add(hyMenuItem(`data-models data-add="model:${esc(m.id)}" title="3d/models/${esc(m.id)}"`, ico("model"), esc(m.title || m.id)));
  };
  const bar = q(".m3t");
  // «+» opens Hyimg's dock list over the dock (hyimg ui/dock.js through dock.js, owner 2026-10-10: the board's «+» and this one alike)
  const onBar = ev => {
    const t = ev.target.closest("[data-tool],[data-a]"); if (!t) return;
    if (t.dataset.tool) return setTool(L, t.dataset.tool);
    if (t.dataset.a === "shot") return shoot(L);
    if (t.dataset.a === "reset") return resetAll(L);
    if (t.dataset.a === "undo" || t.dataset.a === "redo") return step(L, t.dataset.a === "redo" ? 1 : -1);
    if (t.dataset.a === "save") return stopLive(true);
    if (t.dataset.a === "cancel") return askCancel(L);
  };
  root.addEventListener("click", onBar);
  root.querySelector('[data-tool="select"]').classList.add("on");
  // the toolbar goes down into the board's dock while the editor is open (owner 2026-10-04: «the bottom menu changes in 3D, the buttons
  // that are at the top now go there, in our design»); its «+» menu stays with the editor's panels and opens upward
  if (HY.dock) {
    bar.classList.remove("m3p"); root.appendChild(menu); bar.addEventListener("click", onBar); bar.addEventListener("pointerdown", e => e.stopPropagation());
    HY.dock(bar);
  }
  L.sdock = studioDock(L, { t, ico, bar, menu, fillModels, ADD, MENU_ICON, addThing, setTool, shoot, resetAll, undo: d => step(L, d), save: () => stopLive(true), cancel: () => askCancel(L) });

  // -- the axes: Blender's colours (x red, y green, z blue up). Drag turns the card's camera around what it looks at, a click on an
  // axis flies it there in 0.4 s (owner 2026-10-03: the circle must turn and the jump be smooth); angles go on a sphere, so a top view
  // never flips
  const AX = [["X", 1, 0, 0, "#ff4d5e"], ["Y", 0, 0, -1, "#5fd35a"], ["Z", 0, 1, 0, "#4c8dff"]], svg = q(".axes");
  // hy-allow-begin: icon-inline the axes gizmo: the scene's three axes as the camera sees them, redrawn each frame, not icons
  const axes = () => {
    const inv = L.cam.quaternion.clone().invert(), out = [];
    for (const [n, x, y, z, c] of AX) for (const sgn of [1, -1]) { const v = new THREE.Vector3(x * sgn, y * sgn, z * sgn).applyQuaternion(inv); out.push({ n, sgn, c, x: 45 + v.x * 30, y: 45 - v.y * 30, z: v.z }); }
    out.sort((a, b) => a.z - b.z);
    svg.innerHTML = '<circle cx="45" cy="45" r="43" class="ring"/>' + out.map(p => (p.sgn > 0 ? `<line x1="45" y1="45" x2="${p.x}" y2="${p.y}" stroke="${p.c}" stroke-width="2" stroke-linecap="round"/>` : "")
      + `<g class="ax" data-ax="${p.n}${p.sgn > 0 ? "+" : "-"}"><circle cx="${p.x}" cy="${p.y}" r="${p.sgn > 0 ? 8.5 : 6}" fill="${p.c}" fill-opacity="${p.sgn > 0 ? 1 : 0.35}"/>${p.sgn > 0 ? `<text x="${p.x}" y="${p.y + 3.5}">${p.n}</text>` : ""}</g>`).join("");
  };
  // hy-allow-end
  const sph = () => new THREE.Spherical().setFromVector3(L.cam.position.clone().sub(L.orbit.target));
  const placeCam = s => { s.phi = Math.min(Math.PI - 1e-3, Math.max(1e-3, s.phi)); L.cam.position.copy(L.orbit.target).add(new THREE.Vector3().setFromSpherical(s)); L.cam.lookAt(L.orbit.target); L.orbit.update(); };
  const VIEWS = { "X+": [Math.PI / 2, Math.PI / 2], "X-": [-Math.PI / 2, Math.PI / 2], "Y+": [Math.PI, Math.PI / 2], "Y-": [0, Math.PI / 2], "Z+": [null, 1e-3], "Z-": [null, Math.PI - 1e-3] };
  let fly = 0, gz = null;
  const flyTo = (theta, phi) => {
    const s0 = sph(), t0 = performance.now(); let dt = theta - s0.theta; dt = Math.atan2(Math.sin(dt), Math.cos(dt));   // the short way round
    cancelAnimationFrame(fly);
    const step = now => { const k = Math.max(0, Math.min(1, (now - t0) / 420)), e = k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2;
      placeCam(new THREE.Spherical(s0.radius, s0.phi + (phi - s0.phi) * e, s0.theta + dt * e)); if (k < 1) fly = requestAnimationFrame(step); else remember(L, "camera"); };
    fly = requestAnimationFrame(step);
  };
  svg.addEventListener("pointerdown", ev => { ev.stopPropagation(); cancelAnimationFrame(fly); gz = { x: ev.clientX, y: ev.clientY, moved: false, ax: ev.target.closest("[data-ax]")?.dataset.ax }; svg.setPointerCapture(ev.pointerId); });
  svg.addEventListener("pointermove", ev => {
    if (!gz) return; const dx = ev.clientX - gz.x, dy = ev.clientY - gz.y; if (!gz.moved && Math.hypot(dx, dy) < 3) return;
    gz.moved = true; gz.x = ev.clientX; gz.y = ev.clientY; const s = sph(); s.theta -= dx * 0.012; s.phi -= dy * 0.012; placeCam(s);
  });
  svg.addEventListener("pointerup", () => { if (gz && !gz.moved && gz.ax) { const [th, ph] = VIEWS[gz.ax]; flyTo(th === null ? sph().theta : th, ph); } else if (gz && gz.moved) remember(L, "camera"); gz = null; });

  Object.assign(L, { dial, inf, ih });   // the studio's panes of other modules draw with these (variants.js, materials.js)
  tree(); panel();
  const hist = historyTab(L, q, ico, esc);   // the History tab beside Properties (history.js)
  return { root, bar, tree, panel, markTree, sync, axes, hist };
}
// a thing or a part of a model hidden or shown in the scene file (the view follows once applied)
function seenFlag(L, n) {
  const doc = L.e.doc, u = unitOf(n);
  if (n === u) { const x = findAny(doc, u.userData.id); return !!(x && x.hidden); }
  const o = doc.objects.find(x => x.id === u.userData.id), l = o && o.layers && o.layers[layerPath(u, n)]; return !!(l && l.hidden);
}
function setSeen(L, n, hidden) {
  const doc = L.e.doc, u = unitOf(n);
  if (n === u) { const x = findAny(doc, u.userData.id); if (x) { if (hidden) x.hidden = true; else delete x.hidden; } }
  else { const o = doc.objects.find(x => x.id === u.userData.id), path = layerPath(u, n); o.layers = o.layers || {}; const cur = o.layers[path] = o.layers[path] || {}; if (hidden) cur.hidden = true; else delete cur.hidden; if (!Object.keys(cur).length) delete o.layers[path]; }
}
function toggleSeen(L, n) {
  if (!n) return;
  setSeen(L, n, !seenFlag(L, n));
  L.view.apply(L.e.doc).then(() => { L.changed("seen", true); L.ui.tree(); L.need(); });
}

function newScene(into) {   // into: a card placed already, a dropped 3D file (place.js): it keeps its place, size and name, not its pending file
  const doc = newDoc(0.8), path = scenePath(), c = HY.viewCenter(), w = 400, h = 500, id = into || HY.uid("m"), before = HY.snap();
  entry(path, doc).then(e => { e.raw = ""; e.key = ""; save(path, true); });
  // empty: the card asks for a file first (Open file…, the media library, the recent ones: canvas.js); the scene under it is ready, its
  // light and camera stay when a file takes the stand-in's place. A double click opens the editor on the stand-in instead and clears it.
  HY.board.items[id] = { x: Math.round(c.x - w / 2), y: Math.round(c.y - h / 2), w, h, ...(into && HY.board.items[into]), type: TYPE, scene: path, camera: doc.active_camera, empty: true };
  HY.commit(before, t("3D scene: double-click to edit")); HY.select([id]);
  return id;
}

// ---- a 3D file into a card (owner 2026-10-06: «Open file…», the media library's 3D filter, the recent ones). The scene holds glb files;
// a file of another format becomes a glb once (loaders.js). A file the person chose is written into the project first, 3d/files/<hash>/
// <name>.glb, so the scene never points outside the library; one from the library stays where it is (a converted copy goes to
// 3d/converted/<hash>/). The stand-in shape of an empty card is replaced; the scene's light and camera stay, the file stands on the floor.
// A STEP or IGES file is converted by FreeCAD on the server once (cad.py): its glb is what lands in the project, as the file's copy.
const safeName = n => (String(n).replace(/[^A-Za-z0-9._-]+/g, "_").replace(/^[._]+/, "") || "model").slice(0, 80);
const fnv = text => { let h = 0x811c9dc5; for (let i = 0; i < text.length; i++) { h ^= text.charCodeAt(i); h = Math.imul(h, 0x01000193) >>> 0; } return h.toString(16).padStart(8, "0"); };
const exists = async p => { try { return (await fetch(fileUrl(p), { method: "HEAD" })).ok; } catch (e) { return false; } };
async function upload(path, data) {
  const r = await fetch(`/api/file?p=${encodeURIComponent(path)}`, { method: "POST", body: data });
  if (!r.ok) throw new Error(await r.text());
  return path;
}
async function chosenToLibrary(files) {
  const c = readChosen(files); if (!c) throw new Error(t("This is not a 3D file (glb, gltf, obj, stl, fbx, step, iges)"));
  try {
    if (c.file.size > LIMITS.mb * 1048576) throw new Error(t("The file is over {n} MB", { n: LIMITS.mb }));
    const buf = await c.file.arrayBuffer(), path = `3d/files/${await digest(buf)}/${safeName(stemOf(c.name))}.glb`;
    if (!(await exists(path))) await upload(path, extOf(c.name) === "glb" ? buf : isCad(c.name) ? await cadGlb({ name: c.name, file: c.file }) : await toGlb(await loadObject(c)));
    return { path, name: stemOf(c.name) };   // the object carries the chosen file's name, not the safe one of its copy
  } finally { c.done(); }
}
async function glbOf(path, ver) {   // a library file as a glb: a glb itself, else the copy made of it for this version
  if (extOf(path) === "glb") return path;
  const dest = `3d/converted/${fnv(`${path}@${ver || 0}`)}/${safeName(stemOf(path))}.glb`;
  if (await exists(dest)) return dest;
  if (isCad(path)) return upload(dest, await cadGlb({ name: path, path, ver }));   // FreeCAD's glb as it is: no second export
  const dir = path.replace(/[^/]+$/, "");
  return upload(dest, await toGlb(await loadObject({ name: path, url: fileUrl(path), resolve: n => fileUrl(dir + n) })));
}
async function recentAdd(path) {
  try { await fetch(`/api/plugin/${encodeURIComponent(PLUGIN)}/recent`, { method: "POST", body: JSON.stringify({ add: path }) }); } catch (e) { /* the list is a convenience */ }
}
// what to put: {path} of a library file, {model} a project model's model.json, or {files} chosen in the system's panel; ver: its version
// why FreeCAD gave nothing, in words (the reason is cad.py's)
const cadWhy = err => t({ nofreecad: "FreeCAD is needed to read STEP files: none found on this Mac", empty: "The CAD file is empty", toobig: "The CAD file is too big to convert",
  timeout: "FreeCAD took too long on this file", nogeometry: "The CAD file has no solids or surfaces", gone: "The conversion did not finish, try again", network: "The conversion did not finish, try again" }[err.cad] || "FreeCAD could not read this file");
export async function putFile(id, what) {
  let it = HY.board.items[id]; if (!it || !it.scene) return false;
  const ov = document.querySelector(`.plg[data-id="${id}"] .e3`); if (ov) ov.classList.add("busy");   // the empty card waits (empty.js says why while FreeCAD works)
  try {
    const chosen = what.files ? await chosenToLibrary(what.files) : null, path = chosen ? chosen.path : what.path, ver = what.ver, isModel = /(^|\/)model\.json$/.test(path || "");
    const e = await entryOf(id, it), doc = e.doc, before = HY.snap(); it = HY.board.items[id];
    const stand = it.empty && doc.objects[0] && doc.objects[0].src && doc.objects[0].src.type === "prim" ? doc.objects[0] : null;
    let name, src, loc, scale = [1, 1, 1], ai = stand ? stand.ai : "";
    if (isModel) {   // a project model: as «+» puts it, at its own height
      const spec = await (await fetch(fileUrl(path))).json(), mid = path.split("/").slice(-2, -1)[0];
      name = spec.title || mid; src = { type: "model", model: mid }; loc = [0, 0, modelHeight(spec) / 2 + 0.0005]; ai = spec.ai || ai;
      ensureAssembled(mid).catch(() => {});
    } else {
      const glb = await glbOf(path, ver), root = await loadGLB(fileUrl(glb)); root.updateWorldMatrix(true, true);
      const box = new THREE.Box3().setFromObject(root), size = box.getSize(new THREE.Vector3()), big = Math.max(size.x, size.y, size.z);
      if (!(big > 0)) throw new Error(t("The file has no geometry"));
      const k = big >= 0.05 && big <= 0.3 ? 1 : 0.2 / big, c = box.getCenter(new THREE.Vector3());   // real size when it is a few cm to 30 cm, else 20 cm
      name = chosen ? chosen.name : stemOf(path); src = { type: "file", path: glb }; scale = [k, k, k];
      loc = fromV(new THREE.Vector3(-k * c.x, -k * box.min.y + 0.0005, -k * c.z));   // its middle on the floor's centre, its foot on the floor
    }
    const o = { id: newId(), name, src, loc, rot: [1, 0, 0, 0], scale, ai };
    if (stand) doc.objects[doc.objects.indexOf(stand)] = o; else doc.objects.push(o);
    tidy(doc); await e.view.apply(doc); save(it.scene, true);
    delete it.empty; it.name = name; HY.commit(before, t("3D: file {name}", { name })); HY.render();   // the name: hy.py find finds the card by its file
    repaint(it.scene, true);
    recentAdd(path);   // a file of the library by its own path (a converted copy is not the file), a chosen one by the copy in 3d/files
    return true;
  } catch (err) { HY.toast(err.heavy ? t("3D: {why}. First “Load” on the card", { why: heavyText(err.heavy) }) : err.cad ? "3D: " + cadWhy(err) : "3D: " + (err.message || err)); return false; }
  finally { if (ov) ov.classList.remove("busy"); }
}

let H;   // canvas.js: poster(el, it, id, doc, force) shows a card through the cache
export function init(hy, hooks) {
  HY = hy; H = hooks;
  t = translator(hy); initHistory({ HY, t, live: () => live }); initTools({ THREE, HY, t }); initView({ HY, t, live: () => live, stop: keep => stopLive(keep) }); sceneWords(t); K = Object.fromEntries(Object.entries(LABELS).map(([k, w]) => [k, t(w)]));
  FIN_NAME = Object.fromEntries(Object.entries(FIN_WORDS).map(([k, w]) => [k, t(w)])); FIN_KEY = Object.fromEntries(Object.entries(FIN_NAME).map(([k, v]) => [v, k]));
  const dkCss = document.createElement("link"); dkCss.rel = "stylesheet"; dkCss.href = new URL("./vendor/dialkit/styles.css", import.meta.url).href; document.head.appendChild(dkCss);
}
export { goLive, newScene, stopLive };
// a step of ⌘Z, ⇧⌘Z or the dock's ↶ ↷, then its name over the button for 2 s (dock.js, Hyimg's hyDock.steps)
const step = (L, d) => undo(L, d).then(() => { if (L.sdock && live === L) L.sdock.done(d < 0 ? "undo" : "redo"); });
export function onKey(e) {
  if (!live) return false;
  const L = live, k = e.key.toLowerCase(), mod = e.metaKey || e.ctrlKey;
  // ⌘Z ⇧⌘Z are the studio's steps wherever the focus is after a gesture (a slider, a row of the list); a field being typed in keeps its own
  // (the board does not hand those keys over then). A DialKit control kept ⌘Z before (owner 2026-10-07: «cmd + z не работает в 3D studio»)
  if (mod && !e.altKey && (k === "z" || k === "я")) { e.preventDefault(); step(L, e.shiftKey ? 1 : -1); return true; }
  if (mod && !e.altKey && !e.shiftKey && (e.code === "KeyK" || k === "k" || k === "л")) { e.preventDefault(); if (L.sdock) L.sdock.toggle(); return true; }   // ⌘K Actions (dock.js)
  // a control of the panels with the focus keeps no key from the studio (P4 S-15, the board asks hyTyping): Esc only lets go of it
  const ae = document.activeElement; if (e.key === "Escape" && ae && ae !== document.body && L.ui.root.contains(ae)) { e.preventDefault(); ae.blur(); return true; }
  if (L.ann && L.ann.key(e)) return true;   // annot.js: C, Esc
  if (e.key === "Escape") {   // a press, a step: a Blender render, the «+» menu (S-42), layer to object, the pick; the last keeps the work (S-27)
    e.preventDefault(); const p = picked(L), mn = document.querySelector(".m3menu:not([hidden])");
    if (L.blender && L.blender.escape()) return true; if (mn) { mn.hidden = true; return true; }
    if (p.kind === "layer") { let n = p.node.parent; while (n && n !== p.unit && head(p.unit, n) !== n) n = n.parent; pick(L, n && n !== p.unit.children[0] ? n : p.unit); }
    else if (p.kind || L.lmSel) pick(L, null); else stopLive(true);
    return true;
  }
  // ⌘↵ saves, as in the image studio; a plain Enter never does (owner 2026-10-07: «просто Enter можно случайно нажать или применить, например,
  // при изменении чисел в параметрах»): in a number field it only takes the value
  if (e.key === "Enter") { if (mod && !e.altKey && !e.shiftKey) { e.preventDefault(); stopLive(true); } return true; }
  if (e.key === " ") { e.preventDefault(); return true; }   // Space + drag moves the view (tools.js), the studio's own hand, not the board's
  if (e.key === "Backspace" || e.key === "Delete") {   // every chosen row, not only the first (P4 S-21)
    const ids = (L.multi && L.multi.length > 1 ? L.multi : [L.sel]).map(n => picked(L, n)).filter(p => p.kind && p.kind !== "layer").map(p => p.id);
    if (ids.length) { e.preventDefault(); removeThing(L, ids); } else if (picked(L).kind === "layer") HY.toast(t("A layer is part of its model's file: hide it with its eye"), "info", { key: "m3layer" }); return true;
  }
  if (!mod && (k === "p" || k === "з")) { e.preventDefault(); shoot(L); return true; }
  const tool = { v: "select", м: "select", g: "translate", п: "translate", r: "rotate", к: "rotate", s: "scale", ы: "scale", t: "smart", е: "smart" }[k];
  if (!mod && tool) { e.preventDefault(); setTool(L, tool); return true; }
  return ["c", "n"].includes(k) || mod;   // nothing else of the board while editing
}
