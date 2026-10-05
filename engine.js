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
import { SceneView, newDoc, tidy, stateKey, toV, fromV, look, lensFor, cameraBack, readBack, newId, ensureAssembled, MASKS, fileUrl, heavyText, layerPath, modelHeight } from "./scene.js";
import { createDialKit, createDialRoot } from "./vendor/dialkit/index.js";   // DialKit 2.0.2 (MIT, Josh Puckett): the inspector's controls

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
const CUBE = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="M12 3 4 7.5v9L12 21l8-4.5v-9z"/><path d="M4 7.5 12 12l8-4.5M12 12v9"/></svg>`;
const ADD = [
  ["box", "Куб"], ["cylinder", "Цилиндр"], ["sphere", "Шар"], ["plane", "Плоскость"],
  ["area", "Свет-панель"], ["spot", "Прожектор"], ["point", "Лампа"], ["sun", "Солнце"], ["camera", "Камера"],
];
const PRIM = { box: [0.1, 0.1, 0.1], cylinder: [0.08, 0.08, 0.2], sphere: [0.08, 0.08, 0.08], plane: [0.5, 0.5, 0] };
const LIGHT_W = { area: 20, spot: 30, point: 10, sun: 3 };
const LIGHT_NAMES = { area: "Свет-панель", spot: "Прожектор", point: "Лампа", sun: "Солнце" };
const SLOW_MS = 120, STOP_MS = 300, POSTER_SLOW_MS = 1200;   // a frame of the editor: lower the quality, then stop and ask; a poster: refresh rarely
// the frame of a card: free, or locked to a ratio (width:height); the same choice as the bar the canvas shows over the card
const FRAMES = ["Свободно", "1:1", "4:5", "5:4", "3:4", "4:3", "2:3", "3:2", "9:16", "16:9"];

let HY, renderer;
const SC = new Map();     // scene path -> {view, doc, raw, key, saving, timer}
let live = null;          // the card being edited

function ensureRenderer() {
  if (renderer) return renderer;
  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });   // alpha: a card can be see-through
  renderer.setPixelRatio(1); renderer.outputColorSpace = THREE.SRGBColorSpace; renderer.toneMapping = THREE.AgXToneMapping;
  renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  // the graphics card dropped the context (too much memory): everything waits, nothing is redrawn until it comes back
  renderer.domElement.addEventListener("webglcontextlost", e => { e.preventDefault(); HY.toast("3D: видеокарта сбросила сцены, жду ее"); if (live) pause(live, 0, "Видеокарта сбросила сцену."); });
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
  if (!r.ok) throw new Error(`нет файла сцены ${path}`);
  const raw = await r.text(); if (raw === e.raw || e.timer) return false;   // an edit waiting to be saved wins
  const doc = JSON.parse(raw); if (e.doc && (doc.rev || 0) < (e.doc.rev || 0)) return false;   // read before our last write landed: older
  e.raw = raw; e.doc = doc; e.key = stateKey(e.doc); await e.view.apply(e.doc);
  return true;
}
// the canvas writes only on a real change: what Blender or an agent wrote is not written back unchanged
function save(path, now) {
  const e = SC.get(path); if (!e || path.startsWith("legacy:")) return;
  clearTimeout(e.timer); e.timer = null;
  if (!now) { e.timer = setTimeout(() => save(path, true), 300); return; }
  tidy(e.doc); const key = stateKey(e.doc); if (key === e.key) return;
  e.doc.rev = (e.doc.rev || 0) + 1; e.doc.by = "canvas"; e.doc.t = new Date().toISOString().slice(0, 19).replace("T", " ");
  const raw = JSON.stringify(e.doc, null, 1); e.key = key; e.raw = raw;
  fetch(`/api/file?p=${encodeURIComponent(path)}`, { method: "POST", body: raw }).then(async r => { if (!r.ok) HY.toast("Сцена не сохранена: " + await r.text()); });
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
export function renderPoster(el, it, id, dest) {
  const img = el.querySelector("img.m3"), badge = el.querySelector(".b3"); if (!img) return;
  if (!img.src) badge.textContent = "3D · загрузка";
  entryOf(id, it).then(e => {
    if (live && live.id === id) return;
    const old = el.querySelector(".h3"); if (old) old.remove();
    const s = Math.min(2, 900 / Math.max(it.w, it.h)), pw = Math.round(it.w * s), ph = Math.round(it.h * s);
    const cam = e.view.camera(it.camera || e.doc.active_camera, pw, ph); cam.layers.set(0);
    const bg = it.bg, see = bg && (bg.transparent || (bg.opacity ?? 100) < 100);
    const t0 = performance.now(), hid = hideEditor(e); e.view.render(cam, pw, ph, "beauty", bg); hid();
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
    badge.textContent = "3D ⚠"; el.title = "сцена не загрузилась: " + err.message; console.error(err);
  });
}
// a scene over the limits waits on its card for a yes
function heavyCard(el, it, id, err) {
  el.querySelector(".b3").textContent = "3D ⏸";
  if (el.querySelector(".h3")) return;
  const d = document.createElement("div"); d.className = "h3";
  d.innerHTML = `<div>${heavyText(err.heavy)[0].toUpperCase() + heavyText(err.heavy).slice(1)}. Компьютер может подвиснуть.</div><button>Загрузить</button>`;
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
export const livePath = () => live ? live.path : null;
export const docOf = path => { const e = SC.get(path); return e && e.doc; };
async function placeCards(path, e, ids) {
  const have = new Set(Object.values(HY.board.items).filter(it => it.type === TYPE && it.scene === path).map(it => it.camera));
  const todo = ids.filter(c => !have.has(c) && e.doc.cameras.some(x => x.id === c)); if (!todo.length) return [];
  const r = e.doc.render || { x: 1600, y: 2000 }, w = 420, h = Math.round(w * r.y / r.x), c = HY.viewCenter(), before = HY.snap(), out = [];
  todo.forEach((cam, i) => { const id = HY.uid("m"); HY.board.items[id] = { type: TYPE, scene: path, camera: cam, x: Math.round(c.x - (todo.length * (w + 40)) / 2 + i * (w + 40)), y: Math.round(c.y - h / 2), w, h }; out.push(id); });
  HY.commit(before, `3D: ${todo.length === 1 ? "карточка камеры" : todo.length + " карточки камер"}`); HY.select(out);
  return out;
}

// ---- the editor (owner 2026-10-03, after the demo «Hyimg 3D Studio»): the layers of the real files on the left, tabs on the right
// (Объект, Свет, Камера, Фон) built with DialKit, tools under the card. The mouse stays an arrow. What is under it turns pink, the
// pick is outlined in pink (variant A; B and C stay in the top bar until the owner chooses). A click picks an object, a click inside
// the picked object picks the layer under the mouse; Esc climbs back up.
const VARIANTS = { A: [1, 0, 0, 1], B: [0, 1, 1, 0], C: [1, 0, 0.5, 1] };   // hover fill, hover outline, pick fill, pick outline
let marks = null;
function markLayer() {   // a mask of the pick (red) and the hover (green), drawn over the view as pink fill or outline
  if (marks) return marks;
  const rt = new THREE.WebGLRenderTarget(1, 1), q = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), new THREE.ShaderMaterial({
    transparent: true, depthTest: false, depthWrite: false, toneMapped: false,
    uniforms: { mask: { value: rt.texture }, px: { value: new THREE.Vector2() }, col: { value: new THREE.Vector3(1, 0.31, 0.64) }, mode: { value: new THREE.Vector4() } },
    vertexShader: "varying vec2 vUv; void main(){ vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }",
    fragmentShader: `uniform sampler2D mask; uniform vec2 px; uniform vec3 col; uniform vec4 mode; varying vec2 vUv;
      void main(){
        vec4 m = texture2D(mask, vUv); float sn = 0.0, hn = 0.0;
        for (int x = -2; x <= 2; x++) for (int y = -2; y <= 2; y++) { vec4 n = texture2D(mask, vUv + vec2(float(x), float(y)) * px); sn = max(sn, n.r); hn = max(hn, n.g); }
        float a = max(max(m.g * mode.x * 0.42, m.r * mode.z * 0.38), max(hn * (1.0 - m.g) * mode.y * 0.7, sn * (1.0 - m.r) * mode.w));
        gl_FragColor = vec4(col, a); }`,
  }));
  const sc = new THREE.Scene(); sc.add(q);
  const mm = c => Object.assign(new THREE.MeshBasicMaterial({ color: c }), { toneMapped: false });
  marks = { rt, q, sc, cam: new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1), sel: mm(0xff0000), hov: mm(0x00ff00), both: mm(0xffff00), none: mm(0x000000) };
  return marks;
}
const meshesOf = (L, n) => {
  const out = []; if (!n) return out;
  n.traverse(m => { if (m.isMesh && m.visible !== false) out.push(m); });
  if (n.userData.kind === "light" && L.icons.get(n.userData.id)) out.push(L.icons.get(n.userData.id));
  return out;
};
function drawMarks(L, W, H) {
  const sel = meshesOf(L, L.sel), hov = L.hov === L.sel ? [] : meshesOf(L, L.hov);
  if (!sel.length && !hov.length) return;
  const M = markLayer(), helper = L.tc.getHelper(), was = helper.visible, keep = [];
  helper.visible = false;
  L.view.scene.traverse(m => { if (!m.isMesh) return; const s = sel.includes(m), h = hov.includes(m); keep.push([m, m.material]); m.material = s && h ? M.both : s ? M.sel : h ? M.hov : M.none; });
  const tone = renderer.toneMapping, bg = L.view.scene.background; renderer.toneMapping = THREE.NoToneMapping; L.view.scene.background = null;
  if (M.rt.width !== W || M.rt.height !== H) M.rt.setSize(W, H);
  renderer.setRenderTarget(M.rt); renderer.setClearColor(0x000000, 1); renderer.clear(); renderer.render(L.view.scene, L.cam); renderer.setRenderTarget(null);
  keep.forEach(([m, mt]) => { m.material = mt; }); helper.visible = was; renderer.toneMapping = tone; L.view.scene.background = bg; renderer.setClearColor(0x000000, 0);
  M.q.material.uniforms.px.value.set(1 / W, 1 / H); M.q.material.uniforms.mode.value.fromArray(VARIANTS[L.variant] || VARIANTS.A);
  renderer.autoClear = false; renderer.render(M.sc, M.cam); renderer.autoClear = true;
}

async function goLive(id) {
  if (live) stopLive();
  let it = HY.board.items[id]; const el0 = [...document.querySelectorAll(".plg")].find(x => x.dataset.id === id); if (!it || !el0) return;
  try { await entryOf(id, it); } catch (err) { if (err.heavy) HY.toast("3D: " + heavyText(err.heavy) + ". Сначала «Загрузить» на карточке"); else HY.toast("3D: " + err.message); return; }
  if (!it.scene) {   // an older card becomes a scene file
    const doc = legacyDoc(it), path = scenePath(), before = HY.snap();
    const e = await entry(path, doc); e.raw = ""; e.key = ""; save(path, true);
    Object.assign(it, { scene: path, camera: doc.active_camera }); delete it.model; delete it.cam; delete it.colors; SC.delete(`legacy:${id}`);
    HY.commit(before, "3D: сцена сохранена в " + path);
  }
  it = HY.board.items[id];
  const el = [...document.querySelectorAll(".plg")].find(x => x.dataset.id === id), path = it.scene, e = await entry(path), view = e.view;
  // each model of the scene gets its one-file copy for Blender (3d/models/<id>/assembled.glb), also when an agent put it in the file
  for (const m of new Set(e.doc.objects.filter(o => o.src && o.src.type === "model").map(o => o.src.model))) ensureAssembled(m).catch(() => {});
  ensureRenderer(); el.classList.add("plg-live"); document.body.classList.add("m3edit");
  if (HY.full) HY.full(true);   // the library folds while the editor is open (owner 2026-10-03), it comes back on «Готово»
  const cvs = renderer.domElement; cvs.className = "m3live"; el.appendChild(cvs);
  const cam = new THREE.PerspectiveCamera(); cam.layers.enable(1);
  const orbit = new OrbitControls(cam, cvs); orbit.enableDamping = false; orbit.screenSpacePanning = true; orbit.zoomSpeed = 0.6;
  const tc = new TransformControls(cam, cvs); tc.setSize(0.8); view.scene.add(tc.getHelper());
  // the editor's canvas is one for every session: its listeners belong to this session and go with it (2026-10-04: after a second
  // opening a pull ran twice, two strings and a double turn, and an old session's pick drew a second panel)
  const ac = new AbortController(), on = { signal: ac.signal };
  const startDoc = tidy(JSON.parse(JSON.stringify(e.doc)));   // what «Сбросить» takes things back to: the scene and the card at the opening
  live = { id, el, e, path, view, cam, orbit, tc, ac, on, start: { doc: startDoc, key: stateKey(startDoc), item: JSON.parse(JSON.stringify(HY.board.items[id])) }, sel: null, hov: null, tool: "select", variant: HY.pref("m3.variant", "A"), open: new Set(), raw: false, tab: 0, kit: null,
    icons: new Map(), before: HY.snap(), hist: [], hi: -1, busy: false, scale: 1, times: [], paused: false, allowSlow: false };
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
    const [W, H] = size(), t0 = performance.now(); updateHelpers(L);
    view.render(cam, W, H, "beauty", HY.board.items[id].bg); drawMarks(L, W, H); if (L.ui) L.ui.axes();
    const gl = renderer.getContext(); gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px);   // waits for the frame, so the time is the real one
    guard(L, performance.now() - t0);
  };
  let rq = 0; L.need = () => { if (!rq) rq = requestAnimationFrame(() => { rq = 0; L.redraw(); }); };
  // after the file changed (undo, an agent's export): the camera, the icons, the pick if it still exists, the panels
  L.reload = () => { syncCam(); helpers(L); if (L.sel && !inScene(L.sel)) L.sel = null; if (L.hov && !inScene(L.hov)) L.hov = null; attach(L); L.ui.tree(); L.ui.panel(); L.redraw(); };
  L.changed = (what, immediate) => { save(path, immediate); remember(L, what); };
  L.rsI = setInterval(() => resetState(L), 400);   // the reset buttons follow every change, also while a slow editor is paused
  L.recam = () => { syncCam(); L.redraw(); };
  L.ui = buildUI(L);
  syncCam(); helpers(L); L.redraw(); remember(L, "start");
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
    for (const [uid, u] of view.units) if (u.kind === "object" && u.obj.visible && !locked(uid)) u.obj.traverse(m => { if (m.isMesh && m.visible) targets.push(m); });
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
  smartMove(L, cvs, ray);
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
function picked(L) {
  const n = L.sel; if (!n) return { kind: null };
  if (n.userData.cam) return { kind: "camera", id: n.userData.cam, node: n };
  const u = unitOf(n); if (!u) return { kind: null };
  if (u.userData.kind === "light") return { kind: "light", id: u.userData.id, node: u, unit: u };
  return u === n ? { kind: "object", id: u.userData.id, node: n, unit: u } : { kind: "layer", id: u.userData.id, node: n, unit: u, path: layerPath(u, n) };
}
function pick(L, n, reveal) {
  L.sel = n || null;
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
const PIVOTS = [{ value: "mirror", label: "Зеркальная точка" }, { value: "center", label: "Центр" }];
function smartMove(L, cvs, ray) {
  let g = null, raf = 0;
  const at = ev => { const r = cvs.getBoundingClientRect(); ray.setFromCamera(new THREE.Vector2(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1), L.cam); };
  cvs.addEventListener("pointerdown", ev => {   // capture: it runs before the camera's own handler, which it switches off for the drag
    if (L.tool !== "smart" || ev.button !== 0) return;
    at(ev);
    const targets = []; for (const [uid, u] of L.view.units) { const x = findAny(L.e.doc, uid); if (u.kind === "object" && u.obj.visible && !(x && x.locked)) u.obj.traverse(m => { if (m.isMesh && m.visible) targets.push(m); }); }
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
  const p = picked(L), ok = (p.kind === "object" || p.kind === "light") && ["translate", "rotate", "scale"].includes(L.tool) && !(p.kind === "light" && L.tool === "scale");
  if (ok) { L.tc.attach(p.unit); L.tc.setMode(L.tool); } else L.tc.detach();
}
function setTool(L, t) { L.tool = t; (L.ui.bar || L.ui.root).querySelectorAll("[data-tool]").forEach(b => b.classList.toggle("on", b.dataset.tool === t)); attach(L); L.need(); }

// the editor watches how long a frame takes: slow, it draws at half and then a third of the size; still too slow, it stops and asks
function guard(L, ms) {
  L.times.push(ms); if (L.times.length > 3) L.times.shift(); if (L.times.length < 3) return;
  const avg = L.times.reduce((a, b) => a + b, 0) / 3;
  if (avg > SLOW_MS && L.scale > 0.34) { L.scale = L.scale > 0.6 ? 0.5 : 0.33; L.times = []; HY.toast(`3D: кадр считается ${Math.round(avg)} мс, предпросмотр стал грубее`); return; }
  if (avg > STOP_MS && !L.allowSlow) pause(L, avg);
}
function pause(L, ms, why) {
  if (L.paused) return; L.paused = true;
  const d = document.createElement("div"); d.className = "h3 m3pause";
  d.innerHTML = `<div>${why || `Сцена считается слишком медленно: ${Math.round(ms)} мс на кадр.`} Расчет остановлен, чтобы Hyimg не завис.</div><div><button data-go>Продолжить</button> <button data-stop>Закрыть</button></div>`;
  d.addEventListener("pointerdown", e => e.stopPropagation());
  d.querySelector("[data-go]").onclick = () => { d.remove(); L.paused = false; L.allowSlow = true; L.times = []; L.redraw(); };
  d.querySelector("[data-stop]").onclick = () => { d.remove(); stopLive(); };
  L.el.appendChild(d);
}

function stopLive() {
  if (!live) return;
  const L = live; live = null;
  save(L.path, true);
  L.ac.abort();   // every listener this session put on the shared canvas
  clearInterval(L.rsI);
  if (L.themeObs) L.themeObs.disconnect();
  if (L.kit) L.kit.destroy(); if (L.dk) L.dk.destroy();
  L.orbit.dispose(); L.tc.detach(); L.view.scene.remove(L.tc.getHelper()); L.tc.dispose();
  L.view.helpers.clear(); if (HY.dock) HY.dock(null); L.ui.root.remove(); L.unplace(); L.el.querySelectorAll(".m3pause").forEach(x => x.remove()); renderer.domElement.remove(); L.el.classList.remove("plg-live"); document.body.classList.remove("m3edit");
  if (HY.full) HY.full(false);
  HY.commit(L.before, "3D: сцена сохранена"); HY.render();
  // the board redraws a plugin's card only when its item changes, and edits live in the scene file: the cards of this scene are
  // redrawn here (2026-10-03: after «Готово» the card kept the view from before the edit)
  repaint(L.path, true);
}

// undo inside the editor: the scene file is not the board, so it keeps its own steps
function remember(L, what) {
  clearTimeout(L.hmT);
  L.hmT = setTimeout(() => {
    const s = JSON.stringify(L.e.doc); if (L.hist[L.hi] === s) return;
    L.hist = L.hist.slice(0, L.hi + 1); L.hist.push(s); if (L.hist.length > 80) L.hist.shift(); L.hi = L.hist.length - 1;
  }, what === "start" ? 0 : 250);
}
async function undo(L, dir) {
  const i = L.hi + dir; if (i < 0 || i >= L.hist.length) return;
  L.hi = i; L.e.doc = JSON.parse(L.hist[i]); await L.view.apply(L.e.doc); save(L.path, true); L.reload();
}

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
  const b = L.view.bounds, side = fromV(new THREE.Vector3(b.max.x, b.min.y, (b.min.z + b.max.z) / 2)), t = fromV(L.orbit.target);
  const doc = L.e.doc, n = (base) => { let i = 1; while ([...doc.objects, ...doc.lights, ...doc.cameras].some(x => x.name === `${base} ${i}`)) i++; return `${base} ${i}`; };
  const id = newId();
  if (PRIM[what]) {
    const s = PRIM[what].slice(); doc.objects.push({ id, name: n(ADD.find(a => a[0] === what)[1]), src: { type: "prim", shape: what, size: s }, loc: [side[0] + s[0] / 2 + 0.03, side[1], s[2] / 2], rot: [1, 0, 0, 0], scale: [1, 1, 1], color: "#b8b8b4", ai: "" });
  } else if (what.startsWith("model:")) {   // a model of the project, picked in «+»: its name and its text for the AI come from model.json
    const m = (await projectModels()).find(x => x.id === what.slice(6)); if (!m) { HY.toast("Модели больше нет в 3d/models"); return; }
    doc.objects.push({ id, name: n(m.title || m.id), src: { type: "model", model: m.id }, loc: [side[0] + 0.07, side[1], modelHeight(m) / 2 + 0.0005], rot: [1, 0, 0, 0], scale: [1, 1, 1], ai: m.ai || "" });
    ensureAssembled(m.id).catch(err => HY.toast("Модель для Blender не записана: " + err.message));
  } else if (LIGHT_W[what]) {
    const p = fromV(L.cam.position.clone().add(new THREE.Vector3(0, 0.35, 0)).add(new THREE.Vector3(-0.25, 0, 0).applyQuaternion(L.cam.quaternion)));
    doc.lights.push({ id, name: n(LIGHT_NAMES[what]), type: what, loc: p, rot: look(p, t), color: [1, 1, 1], power: LIGHT_W[what], size: what === "area" ? 0.5 : 0.05, size_y: 0.5, shape: "SQUARE", spot_size: 45, spot_blend: 0.3 });
  } else if (what === "camera") {   // a copy of the card's camera; the card switches to it, the old one keeps its view
    const cur = findAny(doc, L.camId()) || doc.cameras[0];
    doc.cameras.push(Object.assign(JSON.parse(JSON.stringify(cur)), { id, name: n("Камера") }));
    const before = HY.snap(); HY.board.items[L.id].camera = id; HY.commit(before, "3D: новая камера");
  }
  await L.view.apply(doc); L.changed("add", true); L.reload();
  if (what !== "camera") pick(L, LIGHT_W[what] ? L.view.units.get(id).obj : L.view.units.get(id).obj, true);
}
async function removeThing(L, id) {
  const doc = L.e.doc, k = kindOf(doc, id); if (!k) return;
  if (k === "cameras" && doc.cameras.length < 2) { HY.toast("Последнюю камеру не удалить"); return; }
  doc[k] = doc[k].filter(x => x.id !== id); doc.removed = [...new Set([...(doc.removed || []), id])];
  if (k === "cameras") { const it = HY.board.items[L.id]; if (it.camera === id) { const before = HY.snap(); it.camera = doc.cameras[0].id; HY.commit(before, "3D: камера удалена"); } if (doc.active_camera === id) doc.active_camera = doc.cameras[0].id; }
  L.sel = null; await L.view.apply(doc); L.changed("remove", true); L.reload();
}
function setCamera(L, cid) { const before = HY.snap(); HY.board.items[L.id].camera = cid; HY.commit(before, "3D: камера карточки"); L.sel = null; L.reload(); }
// the card's frame changed (its edges, the ratio bar, the list): the scene's render size for Blender follows the card being edited
export function framed(id) {
  if (!live || live.id !== id) return; const L = live, it = HY.board.items[id]; if (!it) return; const a = it.w / it.h;
  L.e.doc.render = { x: a >= 1 ? 1600 : Math.round(1600 * a), y: a >= 1 ? Math.round(1600 / a) : 1600 };
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
const orbitVals = o => ({ "Расстояние, см": Math.round(o.dist * 1000) / 10, "Азимут, °": Math.round(o.az), "Наклон, °": Math.round(o.inc), "Крен, °": Math.round(((o.roll + 540) % 360) - 180) });
const orbitCfg = o => { const v = orbitVals(o); return { "Расстояние, см": [v["Расстояние, см"], 1, Math.max(500, Math.ceil(v["Расстояние, см"] * 3)), 0.1],
  "Азимут, °": [v["Азимут, °"], -180, 180, 1], "Наклон, °": [v["Наклон, °"], -89, 89, 1], "Крен, °": [v["Крен, °"], -180, 180, 1] }; };
function setOrbit(L, c, k) {
  const o = orbitOf(L, c), a = k["Азимут, °"] * D2R, i = THREE.MathUtils.clamp(k["Наклон, °"], -89, 89) * D2R, d = Math.max(0.01, k["Расстояние, см"] / 100);
  const t = new THREE.PerspectiveCamera(); t.position.copy(o.T).add(new THREE.Vector3(Math.cos(i) * Math.cos(a), Math.sin(i), -Math.cos(i) * Math.sin(a)).multiplyScalar(d));
  t.lookAt(o.T); t.quaternion.multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 0, 1), k["Крен, °"] * D2R));
  cameraBack(L.e.doc, c.id, t);
  if (o.card) L.recam(); else { helpers(L); L.need(); }
  L.changed("camera");
}
// Coordinates of a camera or a light as Blender shows them (owner 2026-10-04: «the coordinates go into a folder that opens, and the rest
// of the camera's settings too»): location in cm, rotation as Blender's XYZ Euler in degrees, straight from the file's numbers
const EUL = "ZYX";   // Blender's XYZ Euler applies X, then Y, then Z: in three.js terms the order "ZYX"
function coordCfg(x) {
  const e = new THREE.Euler().setFromQuaternion(new THREE.Quaternion(x.rot[1], x.rot[2], x.rot[3], x.rot[0]), EUL), r = v => Math.round(v * R2D * 10) / 10;
  return { "Положение, см": { X: [Math.round(x.loc[0] * 1000) / 10, -1000, 1000, 0.1], Y: [Math.round(x.loc[1] * 1000) / 10, -1000, 1000, 0.1], Z: [Math.round(x.loc[2] * 1000) / 10, -1000, 1000, 0.1] },
    "Поворот, °": { X: [r(e.x), -180, 180, 0.1], Y: [r(e.y), -180, 180, 0.1], Z: [r(e.z), -180, 180, 0.1] }, _collapsed: true };
}
// A change counts only when the folder's own numbers changed (they are rounded: compared with the file they would nudge the camera on
// every other change), and anything else that moves the camera writes the folder's numbers anew (2026-10-04: after a dolly zoom the
// folder still held the old place and the next change put the camera back there)
const sameVals = (a, b) => JSON.stringify(a) === JSON.stringify(b);
function coordSet(x, k) {
  const P = k["Положение, см"], R = k["Поворот, °"], q = new THREE.Quaternion().setFromEuler(new THREE.Euler(R.X * D2R, R.Y * D2R, R.Z * D2R, EUL));
  x.loc = [P.X / 100, P.Y / 100, P.Z / 100]; x.rot = [q.w, q.x, q.y, q.z];
}
const coordVals = x => { const c = coordCfg(x), v = {}; for (const f of ["Положение, см", "Поворот, °"]) { v[f] = {}; for (const a of "XYZ") v[f][a] = c[f][a][0]; } return v; };
const FITS = [{ value: "AUTO", label: "Авто" }, { value: "HORIZONTAL", label: "По ширине" }, { value: "VERTICAL", label: "По высоте" }];
const camMoreCfg = c => ({ "Сенсор, мм": [c.sensor || 36, 4, 100, 0.1], "Подгонка кадра": { type: "select", options: FITS, default: c.fit || "AUTO" },
  "Сдвиг X": [(c.shift || [0, 0])[0], -1, 1, 0.01], "Сдвиг Y": [(c.shift || [0, 0])[1], -1, 1, 0.01],
  "Ближняя граница, см": [Math.round((c.clip || [0.01, 100])[0] * 1000) / 10, 0.1, 1000, 0.1], "Дальняя граница, м": [(c.clip || [0.01, 100])[1], 1, 10000, 1], _collapsed: true });
function camMoreSet(c, k) {
  if (!k) return false;
  const n = { sensor: k["Сенсор, мм"], fit: k["Подгонка кадра"], shift: [k["Сдвиг X"], k["Сдвиг Y"]], clip: [k["Ближняя граница, см"] / 100, k["Дальняя граница, м"]] };
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
const itemFields = ["camera", "bg", "lock", "w", "h"];
function resetState(L) {
  if (live !== L || !L.ui) return;
  const sc = scopeOf(L), paneChanged = !!(sc && sc.was) && norm(sc.now()) !== norm(sc.was);
  const pb = [...L.ui.root.querySelectorAll(".dk button")].find(b => b.textContent.trim() === "Сбросить");
  if (pb) { pb.classList.add("hy-reset"); pb.disabled = !paneChanged; pb.title = paneChanged ? "Вернуть, как было при открытии редактора" : "Ничего не менялось"; }
  const it = HY.board.items[L.id] || {}, allChanged = stateKey(tidy(clone(L.e.doc))) !== L.start.key || itemFields.some(f => JSON.stringify(it[f]) !== JSON.stringify(L.start.item[f]));
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
  for (const k of Object.keys(d)) if (!["rev", "by", "t"].includes(k)) delete d[k];
  for (const k of Object.keys(s)) if (!["rev", "by", "t"].includes(k)) d[k] = s[k];
  const it = HY.board.items[L.id], before = HY.snap(); for (const f of itemFields) { if (L.start.item[f] === undefined) delete it[f]; else it[f] = clone(L.start.item[f]); } HY.commit(before);
  L.sel = null; await L.view.apply(d); L.reload(); L.changed("reset", true); resetState(L);
}
export function nudge(id) { if (live && live.id === id) live.need(); }

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
  const common = { model: "Hyimg 3D (three.js r180, предпросмотр, не рендер Blender)", route: "hyimg-3d", scene: L.path, scene_rev: doc.rev, camera: c, render: { x: W, y: H },
    background: it.bg || { world: true }, masks: legend, reproduce: `в Blender: blender -b --python <Hyimg-3d>/blender/hyimg_scene.py -- apply <библиотека>/${L.path} --fresh --save-as <файл.blend>, камера ${c.name}${it.bg && it.bg.transparent ? ", Film › Transparent" : ""}` };
  try {
    const before = HY.snap(), x0 = it.x + it.w + Math.round(it.w * 0.05);
    const b = await HY.snapshot(blobs.beauty, "3d-scene", SHOTS, Object.assign({ prompt: `3D-набросок сцены для генерации: камера ${c.name}, объектив ${lens} мм; предметы по маскам: ${what}`, pass: "вид" }, common));
    const m = await HY.snapshot(blobs.mask, "3d-mask", SHOTS, Object.assign({ prompt: `маски предметов к ${b.path}: ${what}`, pass: "маски", of: b.path }, common));
    const d = await HY.snapshot(blobs.depth, "3d-depth", SHOTS, Object.assign({ prompt: `глубина к ${b.path}: белое близко, черное далеко`, pass: "глубина", of: b.path }, common));
    const bw = it.h * b.ar; HY.addPicture(b.path, b.ar, x0, it.y, bw);
    const sh = it.h / 2 - 8; HY.addPicture(m.path, m.ar, x0 + bw + 16, it.y, sh * m.ar); HY.addPicture(d.path, d.ar, x0 + bw + 16, it.y + sh + 16, sh * d.ar);
    HY.commit(before, "3D: снимок, маски и глубина рядом");
    L.before = HY.snap();
  } catch (err) { HY.toast("Снимок не сохранен: " + err.message); }
}

// ---- panels, after Spline (owner 2026-10-03): layers left with search and nesting lines, the inspector right without tabs (it shows
// what is picked, the scene when nothing is), an icon toolbar on top with «+», the axes at the bottom (drag turns the camera, a click on
// an axis flies it there)
const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const hexOf = c => "#" + new THREE.Color(c[0], c[1], c[2]).getHexString();
const linOf = h => { const c = new THREE.Color(h); return [+c.r.toFixed(4), +c.g.toFixed(4), +c.b.toFixed(4)]; };
const r1 = x => Math.round(x * 10) / 10;
const SVG = {
  model: '<path d="M8 3h8a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/>', group: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  file: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>', mesh: '<path d="M12 3 4 7.5v9L12 21l8-4.5v-9z"/><path d="M4 7.5 12 12l8-4.5M12 12v9"/>',
  light: '<circle cx="12" cy="12" r="4"/><path d="M12 3v2M12 19v2M3 12h2M19 12h2"/>', camera: '<rect x="3" y="6" width="13" height="12" rx="2"/><path d="M16 10l5-3v10l-5-3z"/>',
  eye: '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>', off: '<path d="M3 3l18 18M10.6 6.1A9.8 9.8 0 0 1 12 6c5 0 9 6 9 6a15.7 15.7 0 0 1-3 3.4M6.4 6.4C4.2 8 3 12 3 12s4 6 9 6a8.7 8.7 0 0 0 3.6-.8"/>',
  chev: '<path d="M6 9l6 6 6-6"/>', lock: '<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>', unlock: '<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 7.5-2"/>',
  plus: '<path d="M12 5v14M5 12h14"/>', smart: '<circle cx="7" cy="7" r="2.6"/><path d="M9 9.2c2.5 2.6 1.6 6.8 6.4 8.4"/><path d="M14.5 21l3.4-3.3-3.3-3.4"/>', search: '<circle cx="11" cy="11" r="6"/><path d="M20 20l-4-4"/>', select: '<path d="M6 3l12 7-5.5 1.5L10 17z"/>',
  translate: '<path d="M12 3v18M3 12h18M12 3l-3 3M12 3l3 3M12 21l-3-3M12 21l3-3M3 12l3-3M3 12l3 3M21 12l-3-3M21 12l-3 3"/>', rotate: '<path d="M20 12a8 8 0 1 1-2.3-5.7"/><path d="M20 4v5h-5"/>',
  scale: '<path d="M4 20l7-7M4 20v-5M4 20h5M20 4l-7 7M20 4v5M20 4h-5"/>', shot: '<path d="M4 8a2 2 0 0 1 2-2h2l2-2h4l2 2h2a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z"/><circle cx="12" cy="12.5" r="3.5"/>',
  box: '<path d="M12 3 4 7.5v9L12 21l8-4.5v-9z"/><path d="M4 7.5 12 12l8-4.5M12 12v9"/>', sphere: '<circle cx="12" cy="12" r="8"/><path d="M4 12c3 3 13 3 16 0"/>',
  cylinder: '<ellipse cx="12" cy="6" rx="7" ry="2.5"/><path d="M5 6v12c0 1.4 3 2.5 7 2.5s7-1.1 7-2.5V6"/>', plane: '<path d="M3 15l6-6h12l-6 6z"/>',
};
const ico = (k, cls = "ic") => `<svg class="${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">${SVG[k]}</svg>`;
const FIN_RU = { "": "Как в файле", matte: "Мат", glossy: "Глянец", metal: "Металл" }, FIN_EN = Object.fromEntries(Object.entries(FIN_RU).map(([k, v]) => [v, k]));
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
    <div class="m3p m3t"><span class="tip"><button class="plus" data-plus title="Добавить" aria-label="Добавить">${ico("plus")}</button><div class="menu m3menu" hidden>${ADD.map(([k, t]) => `<button data-add="${k}">${ico(MENU_ICON[k] || "light")}${t}</button>`).join("")}</div></span>
      <span class="sep"></span>${[["select", "Выбор", "V"], ["translate", "Двигать", "G"], ["rotate", "Вращать", "R"], ["scale", "Размер", "S"], ["smart", "Тянуть: за точку, как на нитке в густом геле", "T"]].map(([k, t, key]) => `<button data-tool="${k}" data-key="${key}" title="${t} · ${key}" aria-label="${t}">${ico(k)}</button>`).join("")}
      <span class="sep"></span><button class="hy-reset" data-a="reset" title="Сбросить все: сцена и карточка, как при открытии редактора" aria-label="Сбросить все" disabled><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/></svg>Сбросить</button><button class="wide" data-a="shot" title="Вид, маски и глубина рядом с карточкой · P">${ico("shot")}Снимок</button><button class="wide pri" data-a="done" title="Готово · Enter">Готово</button></div>
    <div class="m3p m3l"><div class="lh"><b>3D-сцена</b><code class="fp"></code></div>
      <label class="find">${ico("search")}<input data-q placeholder="Поиск слоя" autocomplete="off"></label>
      <div class="opts"><label title="Показать обертки из файлов без геометрии"><input type="checkbox" data-raw> все узлы</label></div><div class="tr"></div></div>
    <div class="m3p m3r"><div class="ih"></div><div class="inf"></div><div class="dk"></div></div>
    <div class="m3x"><svg class="axes" viewBox="0 0 90 90" aria-label="Оси: перетаскивание крутит камеру, клик по оси ставит камеру вдоль нее"></svg></div>`;
  document.body.appendChild(root);
  const q = s => root.querySelector(s), doc = () => L.e.doc;
  q(".m3l .fp").textContent = L.path;
  const place = () => {   // inside the stage, right of the library panel, clear of the dock
    const r = HY.stage.getBoundingClientRect(), inset = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--inset")) || 0;
    root.style.setProperty("--l", (r.left + inset + 12) + "px"); root.style.setProperty("--r", (innerWidth - r.right + 12) + "px");
    root.style.setProperty("--t", (r.top + 12) + "px"); root.style.setProperty("--b", (innerHeight - r.bottom + 76) + "px");
  };
  // the panels follow the window and the library's edge (--inset changes when the library folds or opens)
  const mo = new MutationObserver(place); mo.observe(document.documentElement, { attributes: true, attributeFilter: ["style"] });
  place(); addEventListener("resize", place); L.unplace = () => { removeEventListener("resize", place); mo.disconnect(); };
  L.dk = createDialRoot({ mode: "inline", target: q(".dk"), theme: pageTheme() });

  // -- the tree, as in Spline: thin lines show nesting, eye and lock appear on hover. A wrapper without geometry and with one child
  // folds into the row below it unless «все узлы» is on; the search keeps matching rows and the rows they sit in
  let query = "";
  const folds = n => !L.raw && !n.isMesh && n.children.length === 1 && !n.userData.label && !n.userData.mirror && !(n.userData.id && n.userData.kind);
  const chainOf = n => { const c = [n]; while (folds(c[c.length - 1])) c.push(c[c.length - 1].children[0]); return c; };
  const meshCount = n => { let k = 0; n.traverse(m => { if (m.isMesh) k++; }); return k; };
  const kidsOf = n => { if (n.userData.kind === "object") { const w = n.children[0]; return !w || w.isMesh ? [] : w.children; } return n.isMesh || n.userData.kind ? [] : n.children; };
  const hits = (n, label) => { if (!query) return true; if ((label || "").toLowerCase().includes(query)) return true; let f = false; n.traverse(x => { if (!f && ((x.userData.label || x.name || "").toLowerCase().includes(query))) f = true; }); return f; };
  const row = (rows, n, guides, label, rec) => {
    if (!hits(n, label)) return;
    const chain = n.userData.kind ? [n] : chainOf(n), last = chain[chain.length - 1], kids = n.userData.kind ? kidsOf(n) : kidsOf(last), open = L.open.has(n.uuid) || !!query;
    const isSel = L.sel && chain.includes(L.sel), within = !isSel && L.sel && n.getObjectById(L.sel.id);
    const kind = n.userData.kind === "light" ? "light" : n.userData.kind === "object" ? (kids.length ? "model" : (rec && rec.src && rec.src.shape) || "mesh") : n.userData.label ? "file" : last.isMesh ? "mesh" : "group";
    const hidden = n.visible === false || last.visible === false, locked = rec && rec.locked;
    const name = label || n.userData.label || n.name || last.name || (last.isMesh ? "меш" : "узел");
    const sub = last.isMesh ? (last.userData.base && last.userData.base.mat.name ? last.userData.base.mat.name : "") : chain.length > 1 && last.name !== name ? last.name : "";
    const cnt = kids.length ? meshCount(last) : 0;
    rows.push(`<div class="row${isSel ? " sel" : ""}${within ? " in" : ""}${hidden ? " hidden" : ""}${kids.length && !open ? " closed" : ""}" data-u="${n.uuid}" title="${esc(chain.map(c => c.name || "·").join(" › "))}">
      ${guides.map(g => `<i class="g${g ? " on" : ""}"></i>`).join("")}${kids.length ? `<button class="chev" data-open="${n.uuid}" aria-label="Развернуть">${ico("chev")}</button>` : '<span class="chev"></span>'}${ico(SVG[kind] ? kind : "mesh")}
      <span class="nm">${esc(name)}${n.userData.mirror || last.userData.mirror ? "<small>зеркало</small>" : ""}${sub ? `<small>${esc(sub)}</small>` : ""}</span>${cnt > 1 ? `<span class="cnt">${cnt}</span>` : ""}
      <span class="acts">${rec ? `<button data-lock="${rec.id}" class="${locked ? "keep" : ""}" aria-label="Заблокировать">${ico(locked ? "lock" : "unlock")}</button>` : ""}<button data-eye="${n.uuid}" class="${hidden ? "keep" : ""}" aria-label="Скрыть или показать">${ico(hidden ? "off" : "eye")}</button></span></div>`);
    if (kids.length && open) kids.forEach((c, i) => row(rows, c, [...guides, i < kids.length - 1]));
  };
  const tree = () => {
    const d = doc(), rows = [], cardCam = L.camId(), sec = (t, list) => { const at = rows.length; list(); if (rows.length > at) rows.splice(at, 0, `<div class="sec">${t}</div>`); };
    sec("Объекты", () => { for (const o of d.objects) { const u = L.view.units.get(o.id); if (u) row(rows, u.obj, [], o.name, o); } });
    sec("Свет", () => { for (const l of d.lights) { const u = L.view.units.get(l.id); if (u) row(rows, u.obj, [], l.name, l); } });
    sec("Камеры", () => { for (const c of d.cameras) if (!query || c.name.toLowerCase().includes(query)) rows.push(`<div class="row${L.sel && L.sel.userData.cam === c.id ? " sel" : ""}" data-cam="${c.id}"><span class="chev"></span>${ico("camera")}<span class="nm">${esc(c.name)}</span>${c.id === cardCam ? '<span class="tag">кадр</span>' : ""}</div>`); });
    q(".tr").innerHTML = rows.join("") || '<div class="none">Ничего не нашлось</div>';
  };
  const byUuid = u => L.view.scene.getObjectByProperty("uuid", u);
  const markTree = () => root.querySelectorAll(".tr .row[data-u]").forEach(r => { const n = byUuid(r.dataset.u); r.classList.toggle("hov", !!(L.hov && n && (n === L.hov || chainOf(n).includes(L.hov)))); });
  q(".tr").addEventListener("click", ev => {
    const o = ev.target.closest("[data-open]"); if (o) { const u = o.dataset.open; L.open.has(u) ? L.open.delete(u) : L.open.add(u); return tree(); }
    const v = ev.target.closest("[data-eye]"); if (v) return toggleSeen(L, byUuid(v.dataset.eye));
    const lk = ev.target.closest("[data-lock]"); if (lk) { const x = findAny(doc(), lk.dataset.lock); if (x) { x.locked = !x.locked || undefined; if (!x.locked) delete x.locked; if (x.locked && L.sel && unitOf(L.sel) && unitOf(L.sel).userData.id === x.id) pick(L, null); L.changed("lock", true); tree(); } return; }
    const c = ev.target.closest("[data-cam]"); if (c) { const icon = L.icons.get(c.dataset.cam); if (icon) return pick(L, icon); L.camSel = c.dataset.cam; return panel("camera"); }
    const r = ev.target.closest(".row[data-u]"); if (!r) return;
    const n = byUuid(r.dataset.u); if (!n) return; const ch = n.userData.kind ? [n] : chainOf(n); pick(L, ch[ch.length - 1].isMesh ? head(unitOf(n), ch[ch.length - 1]) : n);
  });
  q(".tr").addEventListener("mouseover", ev => { const r = ev.target.closest(".row[data-u]"); const n = r ? byUuid(r.dataset.u) : null; if (n !== L.hov) { L.hov = n; L.need(); } });
  q(".tr").addEventListener("mouseleave", () => { L.hov = null; L.need(); });
  root.addEventListener("change", ev => { if (ev.target.matches("[data-raw]")) { L.raw = ev.target.checked; tree(); } });
  q("[data-q]").addEventListener("input", ev => { query = ev.target.value.trim().toLowerCase(); tree(); });

  // -- the inspector: no tabs, it shows what is picked; with nothing picked, the scene (the card's camera, frame, background, world)
  let syncing = false, dialN = 0;
  const dial = (name, cfg, apply, onAction) => {
    if (live !== L) return;   // a closed session never draws a panel: DialKit shows every panel it knows in every root
    if (L.kit) L.kit.destroy();
    if (!Object.keys(cfg).some(k => k.startsWith("Сбросить"))) cfg["Сбросить"] = { type: "action" };
    const act = a => { if (a.endsWith("Сбросить")) return resetPane(L); if (onAction) onAction(a); };
    L.kit = createDialKit(name, cfg, { id: `m3-${++dialN}`, onAction: act });   // a fresh id: DialKit shares values between panels of one id
    requestAnimationFrame(() => resetState(L));
    // DialKit hands changes over in batches: the last value of a drag can arrive while the editor itself writes the panel (quiet below).
    // Dropped then, it was applied at the next touch of any control (owner 2026-10-04: the transparency moved the camera; it was the end
    // of a «Широкий ↔ изометрия» drag). It waits and is applied right after; apply() acts only on what differs from what it knows
    L.kit.subscribe(v => { if (syncing) pend = v; else apply(v); }, false);
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
  const sync = () => { const p = picked(L); if (!L.kit || p.kind !== "object") return; const t = trs(p.unit); quiet({ "Положение, см": t.pos, "Поворот, °": t.rot }); };
  const inf = html => { q(".inf").innerHTML = html || ""; };
  const ih = (kind, title, sub) => { q(".ih").innerHTML = `${ico(SVG[kind] ? kind : "mesh")}<div><b>${esc(title)}</b>${sub ? `<span>${esc(sub)}</span>` : ""}</div>`; };
  const panel = force => {
    if (L.kit) { L.kit.destroy(); L.kit = null; } inf("");
    const p = picked(L), k = force || p.kind; L.paneKind = k === "object" || k === "layer" || k === "light" || k === "camera" ? k : "scene";
    if (k === "object" || k === "layer") { const o = doc().objects.find(x => x.id === p.id); ih(k === "layer" ? (p.node.isMesh ? "mesh" : "group") : (o && o.src && o.src.type === "model" ? "model" : (o && o.src && o.src.shape) || "mesh"), k === "layer" ? (p.node.userData.label || p.node.name || "Слой") : o ? o.name : "", k === "layer" ? `слой «${o ? o.name : ""}»` : "предмет"); return objPane(); }
    if (k === "light") { const l = doc().lights.find(x => x.id === p.id); ih("light", l ? l.name : "Свет", l ? LIGHT_NAMES[l.type].toLowerCase() : ""); return lightPane(); }
    if (k === "camera") { const c = doc().cameras.find(x => x.id === (p.kind === "camera" ? p.id : L.camSel)); ih("camera", c ? c.name : "Камера", c && c.id === L.camId() ? "камера карточки" : "камера"); return camPane(); }
    ih("model", "Сцена", "ничего не выбрано"); scenePane();
  };

  const objPane = () => {
    const p = picked(L);
    const o = doc().objects.find(x => x.id === p.id); if (!o) return;
    if (p.kind === "layer") {
      const n = p.node, ov = (o.layers || {})[p.path] || {}, m0 = (() => { let m = null; n.traverse(x => { if (!m && x.isMesh) m = x; }); return m; })();
      inf(`<div class="real">${esc(o.name)} › ${esc(p.path.split("/").join(" › "))}${m0 && m0.userData.base && m0.userData.base.mat.name ? `<br>материал в файле: ${esc(m0.userData.base.mat.name)}` : ""}</div>`);
      const color = ov.color || (m0 && m0.material.color ? "#" + m0.material.color.getHexString() : "#b8b8b4");
      return dial(n.userData.label || n.name || "Слой", { "Цвет": color, "Материал": { type: "select", options: Object.values(FIN_RU), default: FIN_RU[ov.finish || ""] }, "Видно": !ov.hidden, "Сбросить слой": { type: "action" } }, v => edit(() => {
        const L2 = o.layers = o.layers || {}, cur = L2[p.path] = L2[p.path] || {};
        if (v["Цвет"] !== color || cur.color) cur.color = v["Цвет"]; cur.finish = FIN_EN[v["Материал"]] || undefined; cur.hidden = !v["Видно"] || undefined;
        for (const k of Object.keys(cur)) if (cur[k] === undefined) delete cur[k]; if (!Object.keys(cur).length) delete L2[p.path];
      }).then(tree), () => edit(() => { if (o.layers) delete o.layers[p.path]; }).then(() => { tree(); panel(); }));
    }
    const u = p.unit, t = trs(u), s = o.src || {}, cfg = { "Имя": { type: "text", default: o.name } };
    cfg["Положение, см"] = { X: [t.pos.X, -300, 300, 0.1], Y: [t.pos.Y, -300, 300, 0.1], Z: [t.pos.Z, -100, 300, 0.1] };
    cfg["Поворот, °"] = { X: [t.rot.X, -180, 180, 1], Y: [t.rot.Y, -180, 180, 1], Z: [t.rot.Z, -180, 180, 1] };
    if (s.type === "prim") {
      const sz = s.size.map(x => r1(x * 100));
      cfg["Размер, см"] = s.shape === "sphere" ? { "Диаметр": [sz[0], 0.5, 300, 0.1] } : s.shape === "cylinder" ? { "Диаметр": [sz[0], 0.5, 300, 0.1], "Высота": [sz[2], 0.5, 300, 0.1] } : s.shape === "plane" ? { X: [sz[0], 1, 1000, 0.5], Y: [sz[1], 1, 1000, 0.5] } : { X: [sz[0], 0.5, 300, 0.1], Y: [sz[1], 0.5, 300, 0.1], Z: [sz[2], 0.5, 300, 0.1] };
    } else cfg["Масштаб, %"] = [Math.round((o.scale || [1])[0] * 100), 1, 500, 1];
    if (s.type !== "model") cfg["Цвет"] = o.color || "#b8b8b4";
    cfg["Материал"] = { type: "select", options: Object.values(FIN_RU), default: FIN_RU[o.finish || ""] };
    cfg["Только тень"] = !!o.shadow_only; cfg["Видно"] = !o.hidden;
    cfg["Для генерации"] = { "Маска": (L.view.units.get(o.id) || {}).mask || o.mask || "#2f6fe4", "Для ИИ": { type: "text", default: o.ai || "" } };
    cfg["Удалить"] = { type: "action" };
    inf(`<div class="real">${esc(s.type === "model" ? `модель ${s.model}` : s.type === "file" ? s.path : s.type === "node" ? "геометрия из Blender (scene.glb)" : "простая фигура")}</div>`);
    dial(o.name, cfg, v => edit(() => {
      if (v["Имя"] !== o.name) { o.name = v["Имя"]; }
      const P = v["Положение, см"], R = v["Поворот, °"], d = Math.PI / 180;
      u.position.set(P.X / 100, P.Z / 100, -P.Y / 100); u.quaternion.setFromEuler(new THREE.Euler(R.X * d, R.Z * d, -R.Y * d, "XYZ")); readBack(L.view, o.id);
      if (v["Масштаб, %"]) o.scale = [1, 1, 1].map(() => v["Масштаб, %"] / 100);
      const S = v["Размер, см"]; if (S) { const z = s.size; if (s.shape === "sphere") s.size = [S["Диаметр"] / 100, S["Диаметр"] / 100, S["Диаметр"] / 100]; else if (s.shape === "cylinder") s.size = [S["Диаметр"] / 100, S["Диаметр"] / 100, S["Высота"] / 100]; else if (s.shape === "plane") s.size = [S.X / 100, S.Y / 100, 0]; else s.size = [S.X / 100, S.Y / 100, S.Z / 100]; if (JSON.stringify(z) === JSON.stringify(s.size)) s.size = z; }
      if (v["Цвет"]) o.color = v["Цвет"];
      o.finish = FIN_EN[v["Материал"]] || undefined; if (!o.finish) delete o.finish;
      o.shadow_only = v["Только тень"] || undefined; if (!o.shadow_only) delete o.shadow_only;
      o.hidden = !v["Видно"] || undefined; if (!o.hidden) delete o.hidden;
      o.mask = v["Для генерации"]["Маска"]; o.ai = v["Для генерации"]["Для ИИ"];
    }).then(tree), () => removeThing(L, o.id));
  };
  const lightPane = () => {
    const d = doc();
    const p = picked(L), l = d.lights.find(x => x.id === (p.kind === "light" ? p.id : L.lightSel)) || d.lights[0]; L.lightSel = l.id;
    const max = l.type === "sun" ? 20 : 400, cfg = {
      "Источник": { type: "select", options: d.lights.map(x => ({ value: x.id, label: x.name })), default: l.id },
      "Тип": { type: "select", options: Object.entries(LIGHT_NAMES).map(([value, label]) => ({ value, label })), default: l.type },
      [`Мощность, ${l.type === "sun" ? "Вт/м²" : "Вт"}`]: [Math.min(max, l.power), 0, max, l.type === "sun" ? 0.1 : 1], "Цвет": hexOf(l.color || [1, 1, 1]),
    };
    if (l.type === "area") cfg["Размер, см"] = [Math.round((l.size || 0.5) * 100), 5, 300, 1];
    if (l.type === "spot") cfg["Конус, °"] = [Math.round(l.spot_size || 45), 5, 170, 1];
    cfg["Видно"] = !l.hidden; cfg["Координаты"] = coordCfg(l); let crd = coordVals(l); cfg["Двигать"] = { type: "action" }; cfg["Удалить"] = { type: "action" };
    dial(l.name, cfg, v => {
      const C = v["Координаты"]; if (C && !sameVals(C, crd)) { crd = JSON.parse(JSON.stringify(C)); coordSet(l, C); return edit(() => {}).then(() => { helpers(L); L.need(); }); }
      if (v["Источник"] !== l.id) { const u = L.view.units.get(v["Источник"]); return setTimeout(() => pick(L, u && u.obj, true)); }
      if (v["Тип"] !== l.type) { return edit(() => { l.type = v["Тип"]; l.power = LIGHT_W[l.type]; }).then(() => { helpers(L); panel(); tree(); }); }
      edit(() => { l.power = v[Object.keys(v).find(k => k.startsWith("Мощность"))]; l.color = linOf(v["Цвет"]); if (v["Размер, см"]) l.size = l.size_y = v["Размер, см"] / 100; if (v["Конус, °"]) l.spot_size = v["Конус, °"]; l.hidden = !v["Видно"] || undefined; if (!l.hidden) delete l.hidden; });
    }, a => { if (a.endsWith("Удалить")) removeThing(L, l.id); else { pick(L, L.view.units.get(l.id).obj, true); setTool(L, "translate"); } });
  };
  const camPane = () => {
    const d = doc(), p = picked(L), cardCam = L.camId(), c = d.cameras.find(x => x.id === (p.kind === "camera" ? p.id : L.camSel)) || d.cameras.find(x => x.id === cardCam); L.camSel = c.id;
    const cfg = { "Объектив, мм": [Math.round(c.lens), DOLLY[0], DOLLY[1], 1], "Положение камеры": orbitCfg(orbitOf(L, c)), "Координаты": coordCfg(c), "Камера: дополнительно": camMoreCfg(c) };
    if (c.id !== cardCam) cfg["Показать в карточке"] = { type: "action" };
    cfg["Удалить"] = { type: "action" };
    let cur = orbitVals(orbitOf(L, c)), crd = coordVals(c);
    const moved = () => { if (c.id === cardCam) L.recam(); else { helpers(L); L.need(); } L.changed("camera"); };
    dial(c.name, cfg, v => {
      const K = v["Положение камеры"];
      if (K && Object.keys(cur).some(k => K[k] !== cur[k])) { cur = { ...K }; setOrbit(L, c, K); crd = coordVals(c); quiet({ "Координаты": crd }); return; }
      const C = v["Координаты"]; if (C && !sameVals(C, crd)) { crd = JSON.parse(JSON.stringify(C)); coordSet(c, C); moved(); cur = orbitVals(orbitOf(L, c)); quiet({ "Положение камеры": cur }); return; }
      if (camMoreSet(c, v["Камера: дополнительно"])) return moved();
      if (Math.round(c.lens) !== v["Объектив, мм"]) { c.lens = v["Объектив, мм"]; if (c.id === cardCam) L.recam(); else L.need(); L.changed("lens"); }
    },
      a => { if (a.includes("Показать")) setCamera(L, c.id); else removeThing(L, c.id); });
  };
  const scenePane = () => {
    const d = doc(), it = HY.board.items[L.id], cardCam = L.camId(), c = d.cameras.find(x => x.id === cardCam) || d.cameras[0];
    const ratio = it.lock && FRAMES.includes(it.lock) ? it.lock : "Свободно";
    let camCur, camCrd;   // what the camera's folders show, set below once the camera is known
    const w = d.world = d.world || {}, bg = Object.assign({ transparent: false, color: hexOf((w.color || [0.18, 0.18, 0.18]).map(x => x * (w.strength ?? 1))), opacity: 100 }, it.bg || {});
    inf(`<div class="empty">Перетаскивание в кадре крутит камеру карточки, правая кнопка двигает, колесо приближает. Фон карточки отдельный слой, как у картинки: прозрачный пропускает холст под карточкой.</div>`);
    camCur = orbitVals(orbitOf(L, c)); camCrd = coordVals(c);
    // what «Широкий ↔ изометрия» shows: compared with the lens it rounds differently, and every later change of the panel (the
    // background's transparency) took that for a move of the slider and drove the camera in again (owner 2026-10-04: «I change the
    // transparency and the object jumps and turns»)
    let dollyCur = dollyOf(c.lens);
    dial("Сцена", {
      "Камера": { type: "select", options: d.cameras.map(x => ({ value: x.id, label: x.name })), default: c.id },
      "Объектив, мм": [Math.round(c.lens), DOLLY[0], DOLLY[1], 1], "Кадр": { type: "select", options: FRAMES, default: ratio },
      "Широкий ↔ изометрия": [dollyOf(c.lens), 0, 100, 1],
      "Положение камеры": orbitCfg(orbitOf(L, c)), "Координаты": coordCfg(c), "Камера: дополнительно": camMoreCfg(c),
      "Фон": { "Прозрачный": bg.transparent, "Цвет": bg.color, "Прозрачность, %": [100 - bg.opacity, 0, 100, 1] },   // the owner reads it as see-through: 0 is a solid background (2026-10-04)
      "Свет мира": { "Цвет": hexOf(w.color || [0.18, 0.18, 0.18]), "Сила": [w.strength ?? 1, 0, 5, 0.05], _collapsed: true },
      "Подсветка выбора": { type: "select", options: [{ value: "A", label: "A · контур" }, { value: "B", label: "B · заливка" }, { value: "C", label: "C · оба" }], default: L.variant },
      "Тянуть (T)": { "Ось": { type: "select", options: PIVOTS, default: HY.pref("m3.pull.pivot", PULL.pivot) }, "Вязкость": [+HY.pref("m3.pull.gel", PULL.gel), 1, 10, 0.5], _collapsed: true },
      "Новая камера из этого вида": { type: "action" }, "Все камеры на холст": { type: "action" },
    }, v => {
      const K = v["Положение камеры"];
      if (K && Object.keys(camCur).some(k => K[k] !== camCur[k])) { camCur = { ...K }; setOrbit(L, c, K); camCrd = coordVals(c); quiet({ "Координаты": camCrd }); return; }
      const C = v["Координаты"]; if (C && !sameVals(C, camCrd)) { camCrd = JSON.parse(JSON.stringify(C)); coordSet(c, C); L.recam(); L.changed("camera"); camCur = orbitVals(orbitOf(L, c)); quiet({ "Положение камеры": camCur }); return; }
      if (camMoreSet(c, v["Камера: дополнительно"])) { L.recam(); L.changed("camera"); return; }
      if (v["Тянуть (T)"]) { HY.setPref("m3.pull.gel", String(v["Тянуть (T)"]["Вязкость"])); if (v["Тянуть (T)"]["Ось"]) HY.setPref("m3.pull.pivot", v["Тянуть (T)"]["Ось"]); }
      if (v["Камера"] !== c.id) return setTimeout(() => setCamera(L, v["Камера"]));
      if (v["Кадр"] !== ratio) return HY.frame(L.id, v["Кадр"] === "Свободно" ? "free" : v["Кадр"]);
      if (v["Подсветка выбора"] !== L.variant) { L.variant = v["Подсветка выбора"]; HY.setPref("m3.variant", L.variant); }
      if (v["Широкий ↔ изометрия"] !== dollyCur) {   // the dolly zoom: the lens and the distance together, the lens slider follows
        dollyCur = v["Широкий ↔ изометрия"]; dolly(L, c, lensOf(dollyCur)); camCur = orbitVals(orbitOf(L, c)); camCrd = coordVals(c);
        quiet({ "Объектив, мм": Math.round(c.lens), "Положение камеры": camCur, "Координаты": camCrd }); return;
      }
      if (Math.round(c.lens) !== v["Объектив, мм"]) {   // the lens alone zooms; the dolly slider shows where it now is
        c.lens = v["Объектив, мм"]; L.recam(); L.changed("lens"); dollyCur = dollyOf(c.lens); quiet({ "Широкий ↔ изометрия": dollyCur });
      }
      const B = v["Фон"], nb = { transparent: B["Прозрачный"], color: B["Цвет"], opacity: 100 - B["Прозрачность, %"] };
      if (JSON.stringify(nb) !== JSON.stringify(Object.assign({}, bg, it.bg || {}))) { const before = HY.snap(); HY.board.items[L.id].bg = nb; Object.assign(bg, nb); HY.commit(before, "3D: фон карточки"); }
      const W = v["Свет мира"]; if (W && (hexOf(w.color || [0.18, 0.18, 0.18]) !== W["Цвет"] || (w.strength ?? 1) !== W["Сила"])) edit(() => { w.color = linOf(W["Цвет"]); w.strength = W["Сила"]; }); else L.need();
    }, async a => {
      if (a.includes("Новая")) addThing(L, "camera");
      else { const ids = await placeCards(L.path, L.e, doc().cameras.map(x => x.id)); if (!ids.length) HY.toast("У каждой камеры уже есть карточка"); }
    });
  };

  // -- the toolbar
  const menu = q(".menu");
  // the project's models in «+», after the shapes: one line each, or a hint where to put one (2026-10-05: no model by default)
  const fillModels = async () => {
    const list = await projectModels();
    menu.querySelectorAll("[data-models]").forEach(x => x.remove());
    const at = menu.querySelector('[data-add="area"]'), add = h => at.insertAdjacentHTML("beforebegin", h);
    if (!list.length) add(`<button data-models disabled title="Модель: 3d/models/<имя>/model.json и ее .glb в папке доски">${ico("model")}Моделей в 3d/models нет</button>`);
    for (const m of list) add(`<button data-models data-add="model:${esc(m.id)}" title="3d/models/${esc(m.id)}">${ico("model")}${esc(m.title || m.id)}</button>`);
  };
  const bar = q(".m3t");
  const onBar = ev => {
    if (ev.target.closest("[data-plus]")) {
      menu.hidden = !menu.hidden;
      if (!menu.hidden) fillModels();
      if (!menu.hidden && bar.classList.contains("plgdock")) {   // in the dock the menu opens upward, over the board
        const r = ev.target.closest("[data-plus]").getBoundingClientRect(); Object.assign(menu.style, { position: "fixed", left: r.left + "px", top: "auto", bottom: innerHeight - r.top + 10 + "px" });
      }
      return;
    }
    const t = ev.target.closest("[data-add],[data-tool],[data-a]"); if (!menu.contains(ev.target)) menu.hidden = true; if (!t) return;
    if (t.dataset.add) { menu.hidden = true; return addThing(L, t.dataset.add); }
    if (t.dataset.tool) return setTool(L, t.dataset.tool);
    if (t.dataset.a === "shot") return shoot(L);
    if (t.dataset.a === "reset") return resetAll(L);
    if (t.dataset.a === "done") return stopLive();
  };
  root.addEventListener("click", onBar);
  root.querySelector('[data-tool="select"]').classList.add("on");
  // the toolbar goes down into the board's dock while the editor is open (owner 2026-10-04: «the bottom menu changes in 3D, the buttons
  // that are at the top now go there, in our design»); its «+» menu stays with the editor's panels and opens upward
  if (HY.dock) {
    bar.classList.remove("m3p"); root.appendChild(menu); bar.addEventListener("click", onBar); bar.addEventListener("pointerdown", e => e.stopPropagation());
    HY.dock(bar);
  }

  // -- the axes: Blender's colours (x red, y green, z blue up). Drag turns the card's camera around what it looks at, a click on an
  // axis flies it there in 0.4 s (owner 2026-10-03: the circle must turn and the jump be smooth); angles go on a sphere, so a top view
  // never flips
  const AX = [["X", 1, 0, 0, "#ff4d5e"], ["Y", 0, 0, -1, "#5fd35a"], ["Z", 0, 1, 0, "#4c8dff"]], svg = q(".axes");
  const axes = () => {
    const inv = L.cam.quaternion.clone().invert(), out = [];
    for (const [n, x, y, z, c] of AX) for (const sgn of [1, -1]) { const v = new THREE.Vector3(x * sgn, y * sgn, z * sgn).applyQuaternion(inv); out.push({ n, sgn, c, x: 45 + v.x * 30, y: 45 - v.y * 30, z: v.z }); }
    out.sort((a, b) => a.z - b.z);
    svg.innerHTML = '<circle cx="45" cy="45" r="43" class="ring"/>' + out.map(p => (p.sgn > 0 ? `<line x1="45" y1="45" x2="${p.x}" y2="${p.y}" stroke="${p.c}" stroke-width="2" stroke-linecap="round"/>` : "")
      + `<g class="ax" data-ax="${p.n}${p.sgn > 0 ? "+" : "-"}"><circle cx="${p.x}" cy="${p.y}" r="${p.sgn > 0 ? 8.5 : 6}" fill="${p.c}" fill-opacity="${p.sgn > 0 ? 1 : 0.35}"/>${p.sgn > 0 ? `<text x="${p.x}" y="${p.y + 3.5}">${p.n}</text>` : ""}</g>`).join("");
  };
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

  tree(); panel();
  return { root, bar, tree, panel, markTree, sync, axes };
}
function toggleSeen(L, n) {
  if (!n) return;
  const doc = L.e.doc, u = unitOf(n);
  if (n === u) { const x = findAny(doc, u.userData.id); if (x) { x.hidden = !x.hidden || undefined; if (!x.hidden) delete x.hidden; } }
  else { const o = doc.objects.find(x => x.id === u.userData.id), path = layerPath(u, n); o.layers = o.layers || {}; const cur = o.layers[path] = o.layers[path] || {}; cur.hidden = !cur.hidden || undefined; if (!cur.hidden) delete cur.hidden; if (!Object.keys(cur).length) delete o.layers[path]; }
  L.view.apply(doc).then(() => { L.changed("seen", true); L.ui.tree(); L.need(); });
}

function newScene() {
  const doc = newDoc(0.8), path = scenePath(), c = HY.viewCenter(), w = 400, h = 500, id = HY.uid("m"), before = HY.snap();
  entry(path, doc).then(e => { e.raw = ""; e.key = ""; save(path, true); });
  HY.board.items[id] = { type: TYPE, scene: path, camera: doc.active_camera, x: Math.round(c.x - w / 2), y: Math.round(c.y - h / 2), w, h };
  HY.commit(before, "3D-сцена: двойной клик, чтобы редактировать"); HY.select([id]);
}

let H;   // canvas.js: poster(el, it, id, doc, force) shows a card through the cache
export function init(hy, hooks) {
  HY = hy; H = hooks;
  const dkCss = document.createElement("link"); dkCss.rel = "stylesheet"; dkCss.href = new URL("./vendor/dialkit/styles.css", import.meta.url).href; document.head.appendChild(dkCss);
}
export { goLive, newScene };
export function onKey(e) {
  if (!live) return false;
  if (document.activeElement && document.activeElement.closest(".dialkit-root")) return true;   // a DialKit control has the keys
  const L = live, k = e.key.toLowerCase(), mod = e.metaKey || e.ctrlKey;
  if (mod && (k === "z" || k === "я")) { e.preventDefault(); undo(L, e.shiftKey ? 1 : -1); return true; }
  if (e.key === "Escape") {   // Esc climbs from a layer to its object, then drops the pick, then closes the editor
    e.preventDefault(); const p = picked(L);
    if (p.kind === "layer") { let n = p.node.parent; while (n && n !== p.unit && head(p.unit, n) !== n) n = n.parent; pick(L, n && n !== p.unit.children[0] ? n : p.unit); }
    else if (p.kind) pick(L, null); else stopLive();
    return true;
  }
  if (e.key === "Enter") { e.preventDefault(); stopLive(); return true; }
  if ((e.key === "Backspace" || e.key === "Delete")) { const p = picked(L); if (p.kind && p.kind !== "layer") { e.preventDefault(); removeThing(L, p.id); } return true; }
  if (!mod && (k === "p" || k === "з")) { e.preventDefault(); shoot(L); return true; }
  const tool = { v: "select", м: "select", g: "translate", п: "translate", r: "rotate", к: "rotate", s: "scale", ы: "scale", t: "smart", е: "smart" }[k];
  if (!mod && tool) { e.preventDefault(); setTool(L, tool); return true; }
  return ["c", "n"].includes(k) || mod;   // nothing else of the board while editing
}
