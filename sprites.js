// Hyimg 3D, the turntable of a 3D file (owner 2026-10-06: «on hover it spins 360° around its own axis», in the library's 3D filter and in
// the 3D card's recent list). A WebGL context per tile cannot be: a browser allows about 16. So each file gets one sheet, N views of it
// around its vertical axis laid in a grid, drawn once here with three.js and kept by Hyimg's server (/api/sprite, per version of the
// file, like a thumbnail); the page turns it by stepping the views (review/ui/spin.js), which costs nothing. The first view is the still
// picture. The library page and the board's canvas both load this module (the manifest's "sprites"); one renderer draws one file at a
// time, a file is drawn by one page (Web Locks), and a file over the heavy-scene limits is not drawn at all.
import * as THREE from "./vendor/three/build/three.module.js";
import { RoomEnvironment } from "./vendor/three/examples/jsm/environments/RoomEnvironment.js";
import { loadObject, extOf, fileUrl, isCad } from "./loaders.js";
import { SHEET, sheetUrl, stillUrl, spinOf } from "./turn.js";
export { SHEET, sheetUrl, stillUrl, spinOf };
const MAX_MB = 80, MAX_TRIS = 3e6;                   // the same limits as a scene (scene.js LIMITS)
const START = 28 * Math.PI / 180;                     // the first view: a three-quarter view, as a product shot

let R = null, env = null;
function renderer() {
  if (R) return R;
  const c = document.createElement("canvas"); c.width = c.height = SHEET.cell;
  R = new THREE.WebGLRenderer({ canvas: c, antialias: true, alpha: true });
  R.setPixelRatio(1); R.setSize(SHEET.cell, SHEET.cell, false); R.setClearColor(0x000000, 0);
  R.outputColorSpace = THREE.SRGBColorSpace; R.toneMapping = THREE.NeutralToneMapping;
  const pm = new THREE.PMREMGenerator(R); env = pm.fromScene(new RoomEnvironment(), 0.04).texture; pm.dispose();
  R.domElement.addEventListener("webglcontextlost", e => { e.preventDefault(); R = null; env = null; });
  return R;
}

// how far the object reaches from its vertical axis and how tall it is, in its own units: what a turn must keep in the frame
function reach(obj) {
  obj.updateWorldMatrix(true, true);
  const box = new THREE.Box3().setFromObject(obj), c = box.getCenter(new THREE.Vector3()), p = new THREE.Vector3(); let r2 = 0, tris = 0;
  obj.traverse(m => {
    if (!m.isMesh || !m.geometry || !m.geometry.attributes.position) return;
    const a = m.geometry.attributes.position, n = a.count, step = Math.max(1, Math.floor(n / 150000));
    tris += (m.geometry.index ? m.geometry.index.count : n) / 3;
    for (let i = 0; i < n; i += step) { p.fromBufferAttribute(a, i).applyMatrix4(m.matrixWorld); r2 = Math.max(r2, (p.x - c.x) ** 2 + (p.z - c.z) ** 2); }
  });
  return { center: c, r: Math.sqrt(r2), h: box.max.y - box.min.y, tris };
}

// the object of a library entry: a project model (3d/models/<id>/model.json) is assembled by the scene's code, a file is read by its format
export async function objectOf(it) {
  if (it.model) { const { assembleModel } = await import("./scene.js"); return (await assembleModel(it.model)).root.clone(true); }
  const dir = it.path.replace(/[^/]+$/, "");
  return loadObject({ name: it.path, path: it.path, ver: it.ver, url: fileUrl(it.path), resolve: n => fileUrl(dir + n) });   // path: a STEP is converted by the server (cad.py)
}
const sizeMb = async it => { try { const r = await fetch(fileUrl(it.path), { method: "HEAD" }); return +(r.headers.get("Content-Length") || 0) / 1048576; } catch (e) { return 0; } };

// draws the sheet: a png blob of SHEET.n views
export async function drawSheet(it) {
  if (!it.model && !isCad(it.path) && (await sizeMb(it)) > MAX_MB) throw Object.assign(new Error("heavy"), { heavy: true });
  const obj = await objectOf(it), { center, r, h, tris } = reach(obj);
  // a preview shows what is there from every side: a thin plane, a model whose faces look the other way, are not an empty frame (the
  // materials are copied first: a project model's are the editor's too)
  obj.traverse(m => { if (m.isMesh) { m.material = Array.isArray(m.material) ? m.material.map(x => x.clone()) : m.material.clone(); for (const x of [].concat(m.material)) x.side = THREE.DoubleSide; } });
  if (tris > MAX_TRIS) throw Object.assign(new Error("heavy"), { heavy: true });
  const { n, cols, cell } = SHEET, rows = Math.ceil(n / cols), gl = renderer();
  const scene = new THREE.Scene(); scene.environment = env;
  const key = new THREE.DirectionalLight(0xffffff, 1.4); key.position.set(1.5, 3, 2); scene.add(key);
  const pivot = new THREE.Group(), holder = new THREE.Group(); holder.add(obj); obj.position.sub(center); pivot.add(holder); scene.add(pivot);
  // the whole turn fits: a cylinder of radius r and height h seen from a little above
  const el = 18 * Math.PI / 180, fov = 28, half = Math.max(r, h / 2 * Math.cos(el) + r * Math.sin(el)) || 0.5;
  const cam = new THREE.PerspectiveCamera(fov, 1, 0.01, 1000), d = half * 1.12 / Math.tan(fov / 2 * Math.PI / 180) + r;
  cam.position.set(0, Math.sin(el) * d, Math.cos(el) * d); cam.near = d / 100; cam.far = d * 10; cam.updateProjectionMatrix(); cam.lookAt(0, 0, 0);
  const sheet = document.createElement("canvas"); sheet.width = cols * cell; sheet.height = rows * cell; const ctx = sheet.getContext("2d");
  for (let i = 0; i < n; i++) {
    pivot.rotation.y = START + i * 2 * Math.PI / n;
    gl.render(scene, cam);
    ctx.drawImage(gl.domElement, (i % cols) * cell, Math.floor(i / cols) * cell);   // in the same task, before the buffer is cleared
    if (i % 6 === 5) await new Promise(ok => setTimeout(ok));   // the page stays alive between views
  }
  scene.traverse(m => { if (m.isMesh) { m.geometry.dispose(); for (const mt of [].concat(m.material)) { for (const v of Object.values(mt || {})) if (v && v.isTexture) v.dispose(); mt && mt.dispose(); } } });
  const blob = await new Promise((ok, bad) => sheet.toBlob(b => b ? ok(b) : bad(new Error("png")), "image/png"));
  return { blob, n, cols, cell };
}

// ---- the queue: one file at a time, each file once per version, one page at a time for a file
const KEEP = new Map();   // path@version -> Promise<meta | null>
const queue = []; let busy = false;
const keyOf = it => `${it.path}@${it.ver || 0}`;
async function wait(it) {   // another page draws it: look for the sheet until it is there
  for (let i = 0; i < 90; i++) {
    await new Promise(ok => setTimeout(ok, 700));
    try { const r = await (await fetch("/api/models3d", { method: "POST", body: JSON.stringify({ paths: [it.path] }) })).json(); if (r[0] && r[0].sprite) return r[0].sprite; } catch (e) { /* again */ }
  }
  return null;
}
async function make(it) {
  const run = async () => {
    const { blob, n, cols, cell } = await drawSheet(it);
    const r = await fetch(`/api/sprite?p=${encodeURIComponent(it.path)}&n=${n}&cols=${cols}&cell=${cell}`, { method: "POST", body: blob });
    if (!r.ok) throw new Error(await r.text());
    const m = await r.json(); return { n: m.n, cols: m.cols, cell: m.cell, v: m.v };
  };
  if (!navigator.locks) return run();
  return navigator.locks.request("hyimg-sprite:" + keyOf(it), { ifAvailable: true }, lock => lock ? run() : wait(it));
}
async function pump() {
  if (busy) return; busy = true;
  while (queue.length) {
    const { it, ok } = queue.shift();
    try { ok(await make(it)); } catch (e) { if (!e.heavy && !e.cad) console.warn("3d: no turntable for", it.path, e); ok(null); }   // e.cad: said by the "hy3d-cad" event already
  }
  busy = false;
}
// the turntable of an entry {path, ver, model?} of /api/models3d: resolves to {n, cols, cell, v} when it is there (drawn now, or by a
// page that was first), null when the file cannot be drawn (too heavy, not readable)
export function ensure(it) {
  if (it.sprite) return Promise.resolve(it.sprite);
  const k = keyOf(it);
  if (!KEEP.has(k)) KEEP.set(k, new Promise(ok => { queue.push({ it, ok }); pump(); }));
  return KEEP.get(k);
}
export const known = it => KEEP.has(keyOf(it));
export { extOf };
// a 3D file in the library's viewer, as a model to turn (owner 2026-10-07): viewer.js, loaded only when one is opened
export const view = (el, it, o) => import("./viewer.js").then(m => m.mount(el, it, o));
