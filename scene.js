// Hyimg 3D scenes (owner 2026-10-03: "a universal system for 3D scenes, in sync with Blender both ways"). A scene is one file in the
// library, 3d/scenes/<name>/scene.json, that the canvas and Blender both read and write; geometry that only Blender has goes beside it
// as scene.glb. The file speaks Blender: metres, z up, quaternions [w, x, y, z], light power in watts, lens in mm on a sensor, so a
// person or an agent can read it next to the .blend. This module turns it into a three.js scene and back.
//
// {format: "hyimg-scene/1", rev, by, render: {x, y}, world: {color: [r, g, b] linear, strength, exposure, look, hdri, hdri_strength, hdri_rot},
//  glb: "scene.glb", glb_rev, active_camera: <id>, blend_file,
//  objects: [{id, name, src: {type: "prim", shape: box|cylinder|sphere|plane, size: [x, y, z]} | {type: "model", model} | {type: "file", path}
//             | {type: "node"} (a node of scene.glb), loc, rot, scale, color, finish: matte|glossy|metal, colors: {<role>: hex}, mask, ai,
//             hidden, shadow_only (only its shadow shows, Blender's shadow catcher),
//             layers: {"<path in the object's tree>": {color, finish, hidden}} (one part of a model: the case, a glass of the phone)}],
//  lights: [{id, name, type: point|spot|sun|area, loc, rot, color: [r, g, b] linear, power (W, W/m² for sun), size, size_y, shape, spot_size, spot_blend, angle}],
//  cameras: [{id, name, loc, rot, lens, sensor, sensor_h, fit: AUTO|HORIZONTAL|VERTICAL, shift: [x, y], clip: [start, end]}],
//  removed: [<id>]}   (ids deleted on one side, so the other deletes them too instead of bringing them back)
import * as THREE from "./vendor/three/build/three.module.js";
import { GLTFLoader } from "./vendor/three/examples/jsm/loaders/GLTFLoader.js";
import { DRACOLoader } from "./vendor/three/examples/jsm/loaders/DRACOLoader.js";
import { HDRLoader } from "./vendor/three/examples/jsm/loaders/HDRLoader.js";
import { EXRLoader } from "./vendor/three/examples/jsm/loaders/EXRLoader.js";
import { GLTFExporter } from "./vendor/three/examples/jsm/exporters/GLTFExporter.js";
import { RectAreaLightUniformsLib } from "./vendor/three/examples/jsm/lights/RectAreaLightUniformsLib.js";

export const FORMAT = "hyimg-scene/1";
const BASE = new URL(".", import.meta.url).href;
export const LIB = "3d/models";
export const MASKS = ["#2f6fe4", "#e4572e", "#3cb44b", "#f032e6", "#ffe119", "#42d4f4", "#911eb4", "#f58231", "#bfef45", "#469990", "#dcbeff", "#9a6324"];
export const fileUrl = p => `/file?p=${encodeURIComponent(p)}`;
RectAreaLightUniformsLib.init();

// ---- Blender (z up) and three.js (y up): the same axes the glTF exporter uses. A point (x, y, z) is (x, z, -y) here. An object's
// own axes turn with it (its mesh is converted too), a camera or a light keeps looking down its own -z in both programs.
const QA = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), -Math.PI / 2), QAi = QA.clone().invert();
export const toV = l => new THREE.Vector3(l[0], l[2], -l[1]);
export const fromV = v => [v.x, -v.z, v.y];
const bq = r => new THREE.Quaternion(r[1], r[2], r[3], r[0]);
const qb = q => [q.w, q.x, q.y, q.z];
export const objQ = r => QA.clone().multiply(bq(r)).multiply(QAi);
export const objR = q => qb(QAi.clone().multiply(q).multiply(QA));
export const viewQ = r => QA.clone().multiply(bq(r));
export const viewR = q => qb(QAi.clone().multiply(q));
const toS = s => new THREE.Vector3(s[0], s[2], s[1]);
const fromS = v => [v.x, v.z, v.y];

// the same rounding as the Blender side: both compare what they would write with what they last read, and write only on a real change
const r5 = x => Math.round(x * 1e5) / 1e5 || 0;
const rq = r => { const s = r[0] < 0 ? -1 : 1, n = Math.hypot(...r) || 1; return r.map(x => r5(x * s / n)); };
export function tidy(doc, active) {
  if (active && !doc.active_camera && doc.cameras && doc.cameras[0]) doc.active_camera = doc.cameras[0].id;
  for (const o of [...doc.objects || [], ...doc.lights || [], ...doc.cameras || []]) {
    if (o.loc) o.loc = o.loc.map(r5);
    if (o.rot) o.rot = rq(o.rot);
    if (o.scale) o.scale = o.scale.map(r5);
  }
  return doc;
}
export const stateKey = doc => { const d = Object.assign({}, doc); delete d.rev; delete d.by; delete d.t; return JSON.stringify(d); };

// vertical angle of view of a Blender camera on a frame w/h; AUTO puts the sensor width along the longer side
export function camFov(c, aspect) {
  const lens = c.lens || 50, sw = c.sensor || 36, sh = c.sensor_h || 24, fit = c.fit || "AUTO";
  const h = 2 * Math.atan(sw / 2 / lens);
  const v = fit === "VERTICAL" ? 2 * Math.atan(sh / 2 / lens) : fit === "HORIZONTAL" || aspect >= 1 ? 2 * Math.atan(Math.tan(h / 2) / aspect) : h;
  return v * 180 / Math.PI;
}
export function lensFor(vdeg, c, aspect) {
  const t = Math.tan(vdeg * Math.PI / 360), sw = c.sensor || 36, sh = c.sensor_h || 24, fit = c.fit || "AUTO";
  if (fit === "VERTICAL") return sh / 2 / t;
  return fit === "HORIZONTAL" || aspect >= 1 ? sw / 2 / (t * aspect) : sw / 2 / t;
}

// ---- loading
const draco = new DRACOLoader(); draco.setDecoderPath(BASE + "vendor/draco/");
const gltf = new GLTFLoader(); gltf.setDRACOLoader(draco);
export const loadGLB = url => new Promise((ok, bad) => gltf.load(url, g => ok(g.scene), undefined, bad));
const GLBS = new Map();
const glbOnce = url => { if (!GLBS.has(url)) GLBS.set(url, loadGLB(url).catch(e => { GLBS.delete(url); throw e; })); return GLBS.get(url); };
const boxOf = o => { o.updateWorldMatrix(true, true); return new THREE.Box3().setFromObject(o); };
const sig = m => `${m.name || ""} ${(Array.isArray(m.material) ? m.material.map(x => x && x.name).join(" ") : (m.material && m.material.name) || "")}`.toLowerCase();
function normalize(group, scale) { const c = boxOf(group).getCenter(new THREE.Vector3()); group.scale.multiplyScalar(scale); group.position.sub(c.multiplyScalar(scale)); }

// a model of the library (3d/models/<id>/model.json {title, ai, height, height_m, parts: [{role, file, keep, mirror, rotate_y}]}): its
// parts put together in the model's own units (spec.height tall). A model with a "phone" part is a phone in its case: the case parts
// gather round the phone as a product configurator puts them; any other model keeps its parts where their files put them. root holds
// one group per part named by role
const MODELS = new Map();
export function assembleModel(id) {
  if (MODELS.has(id)) return MODELS.get(id);
  const p = (async () => {
    const spec = await (await fetch(fileUrl(`${LIB}/${id}/model.json`))).json();
    const root = new THREE.Group(); root.name = id;
    const groups = [];
    for (const part of spec.parts) {
      const src = (await glbOnce(fileUrl(`${LIB}/${id}/${part.file}`))).clone(true);
      if (part.keep) {   // a case file may hold metal and resin meshes: keep the ones of this part
        const drop = []; src.traverse(m => { if (!m.isMesh) return; const s = sig(m), resin = s.includes("resin"); const metal = !resin && /frame|metal|silver|chrome/.test(s); if (part.keep === "resin" ? !resin : !metal) drop.push(m); });
        drop.forEach(m => m.parent && m.parent.remove(m));
      }
      const g = new THREE.Group(); g.name = part.role; g.userData.part = part; g.userData.label = part.file; g.add(src);
      if (part.mirror) { const mir = src.clone(true); mir.scale.x = -1; mir.userData.mirror = true; g.add(mir); }
      if (part.rotate_y) g.rotation.y = part.rotate_y * Math.PI / 180;
      groups.push(g); root.add(g);
    }
    const phone = groups.find(g => g.name === "phone"), cases = groups.filter(g => g.name !== "phone");
    if (!phone) {   // a model of its own parts: one group, spec.height tall (as tall as its files make it without one)
      const all = new THREE.Group(); all.name = "model"; all.userData.label = spec.title || id; groups.forEach(g => all.add(g)); root.add(all);
      const h = boxOf(all).getSize(new THREE.Vector3()).y; spec.height = spec.height || h || 1; normalize(all, spec.height / Math.max(h, 1e-6));
      return { root, spec, files: spec.parts.map(p => `${LIB}/${id}/${p.file}`) };
    }
    const sz = boxOf(phone).getSize(new THREE.Vector3()), k = spec.height / Math.max(sz.y, 1e-3);
    normalize(phone, k);
    const caseRoot = new THREE.Group(); caseRoot.name = "case"; caseRoot.userData.label = "Чехол"; cases.forEach(g => caseRoot.add(g)); root.add(caseRoot); normalize(caseRoot, k);
    const pb = boxOf(phone), cb = boxOf(caseRoot), pc = pb.getCenter(new THREE.Vector3()), cc = cb.getCenter(new THREE.Vector3());
    caseRoot.position.x += pc.x - cc.x; caseRoot.position.y += pc.y - cc.y; caseRoot.position.z += pb.max.z - cb.max.z + (spec.clearance || 0);
    return { root, spec, files: spec.parts.map(p => `${LIB}/${id}/${p.file}`) };
  })();
  p.catch(() => MODELS.delete(id));
  MODELS.set(id, p); return p;
}
const roleOf = m => { let o = m; while (o && !["phone", "case"].includes(o.name)) o = o.parent; return o ? o.name : "part"; };
const NEUTRAL = { phone: ["#3a3b3f", 0.35, 0.42], case: ["#d8d9dc", 0.95, 0.22], part: ["#b8b8b4", 0, 0.6] };

// how tall a model stands in a scene, in metres: model.json "height_m", 20 cm when it does not say
export const modelHeight = spec => (spec && spec.height_m > 0 ? spec.height_m : 0.2);

// the model at real size (spec.height_m) for a scene, with plain materials; colors {role: hex} recolour a part
async function modelInstance(id) {
  const { root, spec } = await assembleModel(id);
  const inner = root.clone(true); inner.visible = true;
  inner.traverse(m => {
    if (!m.isMesh) return;
    const src = Array.isArray(m.material) ? m.material[0] : m.material, [col, metal, rough] = NEUTRAL[roleOf(m)];
    m.material = new THREE.MeshStandardMaterial({ color: col, metalness: metal, roughness: rough, transparent: !!(src && src.transparent), opacity: src && src.opacity != null ? src.opacity : 1 });
    m.material.name = (src && src.name) || "";   // the file's material name stays readable in the layer tree
    m.userData.role = roleOf(m);
  });
  inner.scale.multiplyScalar(modelHeight(spec) / spec.height);
  return inner;
}

// the assembled model as one glb at real size, for Blender: 3d/models/<id>/assembled.glb, written once by the canvas
export async function ensureAssembled(id) {
  const path = `${LIB}/${id}/assembled.glb`;
  if ((await fetch(fileUrl(path), { method: "HEAD" })).ok) return path;
  const inner = await modelInstance(id), root = new THREE.Group(); root.name = id; root.add(inner);
  const buf = await new GLTFExporter().parseAsync(root, { binary: true });
  const r = await fetch(`/api/file?p=${encodeURIComponent(path)}`, { method: "POST", body: buf });
  if (!r.ok) throw new Error(await r.text());
  return path;
}

function primGeometry(shape, s) {
  if (shape === "box") return new THREE.BoxGeometry(s[0], s[2], s[1]);
  if (shape === "cylinder") return new THREE.CylinderGeometry(s[0] / 2, s[0] / 2, s[2], 48);
  if (shape === "sphere") return new THREE.SphereGeometry(s[0] / 2, 48, 24);
  return new THREE.PlaneGeometry(s[0], s[1]).rotateX(-Math.PI / 2);   // Blender's plane lies in xy and faces +z
}

// a layer of an object is named by the path of names from the object down, as the tree shows it; the mirrored half of a part
// carries «~зеркало», so the two halves can be told apart
export const nodeLabel = n => (n.userData.label || n.name || "узел") + (n.userData.mirror ? "~зеркало" : "");
export function layerPath(unit, node) {
  const seg = []; let n = node;
  while (n && n !== unit) { if (n.parent !== unit) seg.unshift(nodeLabel(n)); n = n.parent; }   // the unit's own wrapper is not part of the path
  return seg.join("/");
}
export const FINISH = { matte: [0, 0.7], glossy: [0.1, 0.2], metal: [0.95, 0.22] };
const SHADOW = new THREE.ShadowMaterial({ opacity: 0.3 });

const lin = c => new THREE.Color(c[0], c[1], c[2]);   // light and world colours are linear, as Blender keeps them
const TONE = { AgX: THREE.AgXToneMapping, Filmic: THREE.ACESFilmicToneMapping, Standard: THREE.NoToneMapping, "Khronos PBR Neutral": THREE.NeutralToneMapping };

// ---- a guard against scenes this computer cannot carry (owner 2026-10-03: "a mega scene must not hang the whole program"). Before
// loading, the files are weighed (HEAD); after loading, triangles and texture memory are counted. Over a limit the scene stops with
// Heavy and is not drawn until the person says to go on (view.allow).
export const LIMITS = { mb: 80, tris: 3e6, texMb: 600 };
export class Heavy extends Error {
  constructor(info) { super(heavyText(info)); this.heavy = info; }
}
export function heavyText(h) {
  const parts = [];
  if (h.mb) parts.push(`${Math.round(h.mb)} МБ файлов`);
  if (h.tris) parts.push(`${(h.tris / 1e6).toFixed(1)} млн треугольников`);
  if (h.texMb) parts.push(`${Math.round(h.texMb)} МБ текстур`);
  return "тяжелая сцена: " + parts.join(", ");
}
const sizeOf = async url => { try { const r = await fetch(url, { method: "HEAD" }); return +(r.headers.get("Content-Length") || 0); } catch (e) { return 0; } };
export function weight(root) {
  let tris = 0, tex = 0; const seen = new Set();
  root.traverse(m => {
    if (!m.isMesh || !m.geometry) return;
    const g = m.geometry, n = g.index ? g.index.count : (g.attributes.position ? g.attributes.position.count : 0); tris += n / 3;
    for (const mat of Array.isArray(m.material) ? m.material : [m.material]) for (const v of Object.values(mat || {}))
      if (v && v.isTexture && v.image && !seen.has(v)) { seen.add(v); tex += (v.image.width || 0) * (v.image.height || 0) * 4 * 1.33; }
  });
  return { tris, texMb: tex / 1048576 };
}

// ---- one scene file as a three.js scene
export class SceneView {
  constructor(path, renderer) {
    this.path = path; this.dir = path.replace(/[^/]+$/, ""); this.renderer = renderer;
    this.scene = new THREE.Scene(); this.units = new Map(); this.doc = null; this.cams = new Map();
    this.helpers = new THREE.Group(); this.helpers.name = "helpers"; this.scene.add(this.helpers);
    this.pmrem = new THREE.PMREMGenerator(renderer); this.envKey = ""; this.bounds = new THREE.Box3(new THREE.Vector3(-0.2, 0, -0.2), new THREE.Vector3(0.2, 0.3, 0.2));
  }

  // build or update everything from the file; loads what is new (models, glb nodes, files), keeps what did not change
  async apply(doc) {
    this.doc = doc;
    const want = new Set(), glbUrl = doc.glb ? fileUrl(this.dir + doc.glb) + `&r=${doc.glb_rev || 0}` : null;
    if (!this.allow) {   // weigh what is not loaded yet
      const urls = new Set();
      for (const o of doc.objects || []) {
        const s = o.src || {};
        if (s.type === "file") urls.add(fileUrl(s.path));
        if (s.type === "node" && glbUrl) urls.add(glbUrl);
        if (s.type === "model" && !MODELS.has(s.model)) { try { const spec = await (await fetch(fileUrl(`${LIB}/${s.model}/model.json`))).json(); spec.parts.forEach(p => urls.add(fileUrl(`${LIB}/${s.model}/${p.file}`))); } catch (e) { /* reported when it loads */ } }
      }
      const fresh = [...urls].filter(u => !GLBS.has(u)), mb = (await Promise.all(fresh.map(u => sizeOf(u.replace(/&r=\d+$/, ""))))).reduce((a, b) => a + b, 0) / 1048576;
      if (mb > LIMITS.mb) throw new Heavy({ mb });
    }
    for (const [i, o] of (doc.objects || []).entries()) {
      want.add(o.id);
      const key = JSON.stringify([o.src, o.src && o.src.type === "node" ? glbUrl : 0, o.src && o.src.type === "prim" ? o.src.size : 0]);
      let u = this.units.get(o.id);
      if (!u || u.key !== key) {
        let obj;
        try { obj = await this.makeObject(o, glbUrl); }
        catch (e) { console.warn("3d: object not loaded", o.name, e); obj = new THREE.Group(); obj.userData.broken = String(e.message || e); }
        if (u) this.scene.remove(u.obj);
        const unit = new THREE.Group(); unit.add(obj); unit.name = o.name; unit.userData.id = o.id; unit.userData.kind = "object";
        unit.traverse(m => {
          if (!m.isMesh) return;
          m.castShadow = m.receiveShadow = true; m.userData.unit = o.id;
          // each mesh gets its own material (a glb clone shares them), and remembers how it came from the file
          if (Array.isArray(m.material)) m.material = m.material[0];
          if (m.material && !m.userData.own) { m.material = m.material.clone(); m.userData.own = true; }
          const mt = m.material; m.userData.base = { mat: mt, color: mt.color ? "#" + mt.color.getHexString() : null, metal: mt.metalness, rough: mt.roughness };
        });
        this.scene.add(unit); u = { key, obj: unit, kind: "object" }; this.units.set(o.id, u);
      }
      const g = u.obj; g.name = o.name; g.visible = !o.hidden;
      g.position.copy(toV(o.loc || [0, 0, 0])); g.quaternion.copy(objQ(o.rot || [1, 0, 0, 0])); g.scale.copy(toS(o.scale || [1, 1, 1]));
      u.mask = o.mask || MASKS[i % MASKS.length];
      this.paint(u, o);
    }
    for (const l of doc.lights || []) { want.add(l.id); this.applyLight(l); }
    for (const c of doc.cameras || []) want.add(c.id);
    for (const [id, u] of this.units) if (!want.has(id)) { this.scene.remove(u.obj); this.units.delete(id); }
    for (const id of [...this.cams.keys()]) if (!want.has(id)) this.cams.delete(id);
    this.bounds = this.meshBounds();
    this.placeSuns();
    await this.applyWorld(doc.world || {});
    this.weight = weight(this.scene);
    if (!this.allow && (this.weight.tris > LIMITS.tris || this.weight.texMb > LIMITS.texMb))
      throw new Heavy({ tris: this.weight.tris > LIMITS.tris ? this.weight.tris : 0, texMb: this.weight.texMb > LIMITS.texMb ? this.weight.texMb : 0 });
  }

  // colours and finishes: back to the file's, then the object's own, then its layers from the outside in; visibility of layers
  paint(u, o) {
    const g = u.obj, mats = [];
    g.traverse(m => {
      if (m.userData.base === undefined || !m.isMesh) { if (!m.isMesh && m !== g && m.userData.hid) { m.visible = true; m.userData.hid = false; } return; }
      const b = m.userData.base, mt = b.mat; m.material = o.shadow_only ? SHADOW : mt;
      if (mt.color && b.color) mt.color.set(b.color); if (b.metal !== undefined) { mt.metalness = b.metal; mt.roughness = b.rough; }
      const c = (o.colors && m.userData.role && o.colors[m.userData.role]) || o.color;
      if (c && mt.color) mt.color.set(c);
      if (o.finish && FINISH[o.finish] && "metalness" in mt) [mt.metalness, mt.roughness] = FINISH[o.finish];
      if (m.userData.hid) { m.visible = true; m.userData.hid = false; }
      mats.push(m);
    });
    const layers = Object.entries(o.layers || {}).sort((a, b) => a[0].split("/").length - b[0].split("/").length);
    if (!layers.length) return;
    const byPath = new Map(); g.traverse(n => { if (n !== g) byPath.set(layerPath(g, n), n); });
    for (const [path, ov] of layers) {
      const n = byPath.get(path); if (!n) continue;
      if (ov.hidden) { n.visible = false; n.userData.hid = true; }
      n.traverse(m => {
        if (!m.isMesh || !m.userData.base) return; const mt = m.userData.base.mat;
        if (ov.color && mt.color) mt.color.set(ov.color);
        if (ov.finish && FINISH[ov.finish] && "metalness" in mt) [mt.metalness, mt.roughness] = FINISH[ov.finish];
      });
    }
  }

  async makeObject(o, glbUrl) {
    const s = o.src || { type: "prim", shape: "box", size: [0.1, 0.1, 0.1] };
    if (s.type === "prim") return new THREE.Mesh(primGeometry(s.shape, s.size || [0.1, 0.1, 0.1]), new THREE.MeshStandardMaterial({ color: o.color || "#b8b8b4", roughness: 0.6 }));
    if (s.type === "model") return modelInstance(s.model);
    if (s.type === "file") return (await glbOnce(fileUrl(s.path))).clone(true);
    if (s.type === "node") {   // a node of scene.glb: Blender's geometry, found by the id Blender stored on it (glTF extras)
      if (!glbUrl) throw new Error("в сцене нет scene.glb");
      const root = await glbOnce(glbUrl); let hit = null;
      root.traverse(n => { if (!hit && n.userData && n.userData.hyimg_id === o.id) hit = n; });
      if (!hit) root.traverse(n => { if (!hit && n.name === o.name) hit = n; });
      if (!hit) throw new Error("нет в scene.glb");
      const c = hit.clone(true); c.position.set(0, 0, 0); c.quaternion.identity(); c.scale.set(1, 1, 1);
      return c;
    }
    throw new Error("неизвестный источник " + s.type);
  }

  applyLight(l) {
    let u = this.units.get(l.id);
    if (!u || u.type !== l.type) {
      if (u) this.scene.remove(u.obj);
      const g = new THREE.Group(); g.userData.id = l.id; g.userData.kind = "light"; const parts = {};
      if (l.type === "point") { parts.main = new THREE.PointLight(0xffffff, 1, 0, 2); parts.main.castShadow = true; parts.main.shadow.mapSize.set(1024, 1024); }
      else if (l.type === "spot" || l.type === "area") {
        const s = new THREE.SpotLight(0xffffff, 1, 0, Math.PI / 4, 0.3, 2); s.castShadow = true; s.shadow.mapSize.set(2048, 2048); s.shadow.bias = -0.0002;
        s.target.position.set(0, 0, -1); g.add(s.target); parts.main = s;
        if (l.type === "area") { parts.rect = new THREE.RectAreaLight(0xffffff, 1, 1, 1); g.add(parts.rect); parts.shadow = s; }
      } else if (l.type === "sun") {   // placed in world space by placeSuns: only its direction matters
        const d = new THREE.DirectionalLight(0xffffff, 1); d.castShadow = true; d.shadow.mapSize.set(2048, 2048); d.shadow.bias = -0.0002;
        this.scene.add(d.target); parts.main = d; parts.sun = true;
      }
      g.add(parts.main); this.scene.add(g); u = { obj: g, kind: "light", type: l.type, parts }; this.units.set(l.id, u);
    }
    const g = u.obj, p = u.parts, col = lin(l.color || [1, 1, 1]), P = l.power != null ? l.power : 10;
    g.name = l.name; g.visible = !l.hidden;
    g.position.copy(toV(l.loc || [0, 0, 1])); g.quaternion.copy(viewQ(l.rot || [1, 0, 0, 0]));
    // watts as the glTF exporter reads them, without its 683 lm/W (three.js and Blender both render in their own units, so the same
    // numbers give about the same brightness): a point or spot of P W has P/4π, a sun of S W/m² gives S, an area light emits P/(π·area)
    if (l.type === "point") { p.main.color.copy(col); p.main.intensity = P / (4 * Math.PI); p.main.shadow.radius = 2 + 40 * (l.size || 0.1); }
    if (l.type === "spot") {
      p.main.color.copy(col); p.main.intensity = P / (4 * Math.PI); p.main.angle = Math.min(Math.PI / 2 - 0.01, (l.spot_size || 45) * Math.PI / 360);
      p.main.penumbra = l.spot_blend != null ? l.spot_blend : 0.15; p.main.shadow.radius = 2 + 40 * (l.size || 0.1);
    }
    if (l.type === "area") {   // three.js area lights cast no shadow: 30 % of the power goes to a wide soft spot that does
      const w = l.size || 0.5, h = l.shape === "RECTANGLE" || l.shape === "ELLIPSE" ? (l.size_y || w) : w, area = (l.shape === "DISK" || l.shape === "ELLIPSE" ? Math.PI / 4 : 1) * w * h;
      p.rect.color.copy(col); p.rect.width = w; p.rect.height = h; p.rect.intensity = 0.7 * P / (Math.PI * area);
      p.shadow.color.copy(col); p.shadow.intensity = 0.3 * P / Math.PI; p.shadow.angle = Math.PI * 0.44; p.shadow.penumbra = 1; p.shadow.shadow.radius = 4 + 30 * w;
    }
    if (l.type === "sun") { p.main.color.copy(col); p.main.intensity = P; }
  }

  meshBounds() {
    const b = new THREE.Box3(), all = new THREE.Box3();
    for (const u of this.units.values()) {
      if (u.kind !== "object" || !u.obj.visible) continue;
      const bb = boxOf(u.obj); if (bb.isEmpty()) continue; all.union(bb);
      const s = bb.getSize(new THREE.Vector3()); if (Math.max(s.x, s.y, s.z) < 3) b.union(bb);   // a floor or a backdrop does not set the shadow area
    }
    const r = b.isEmpty() ? all : b;
    return r.isEmpty() ? new THREE.Box3(new THREE.Vector3(-0.2, 0, -0.2), new THREE.Vector3(0.2, 0.3, 0.2)) : r;
  }

  placeSuns() {
    const c = this.bounds.getCenter(new THREE.Vector3()), R = Math.max(0.1, this.bounds.getSize(new THREE.Vector3()).length());
    for (const u of this.units.values()) {
      if (!u.parts || !u.parts.sun) continue;
      const d = new THREE.Vector3(0, 0, -1).applyQuaternion(u.obj.quaternion), L = u.parts.main;
      u.obj.position.copy(c).addScaledVector(d, -2 * R); L.position.set(0, 0, 0); L.target.position.copy(c);
      Object.assign(L.shadow.camera, { left: -R, right: R, top: R, bottom: -R, near: 0.01, far: 4 * R }); L.shadow.camera.updateProjectionMatrix();
    }
  }

  async applyWorld(w) {
    const key = JSON.stringify([w.color, w.strength, w.hdri, w.hdri_strength, w.hdri_rot]);
    this.tone = TONE[w.look || "AgX"] ?? THREE.AgXToneMapping; this.exposure = Math.pow(2, w.exposure || 0);
    if (key === this.envKey) return; this.envKey = key;
    const s = w.strength != null ? w.strength : 1, col = lin(w.color || [0.05, 0.05, 0.05]).multiplyScalar(s);
    if (w.hdri && /\.(hdr|exr)$/i.test(w.hdri)) {
      try {
        const tex = await (w.hdri.toLowerCase().endsWith(".exr") ? new EXRLoader() : new HDRLoader()).loadAsync(fileUrl(w.hdri));
        tex.mapping = THREE.EquirectangularReflectionMapping;
        // Blender's equirect faces -x where three.js faces +x: half a turn, then the mapping's turn about z (y here)
        const rot = Math.PI + (w.hdri_rot || 0);
        Object.assign(this.scene, { environment: this.pmrem.fromEquirectangular(tex).texture, background: tex, environmentIntensity: w.hdri_strength ?? 1, backgroundIntensity: w.hdri_strength ?? 1 });
        this.scene.environmentRotation.set(0, rot, 0); this.scene.backgroundRotation.set(0, rot, 0);
        return;
      } catch (e) { console.warn("3d: hdri not loaded", w.hdri, e); }
    }
    // a plain world: a uniform light from everywhere (it also gives the chrome something to reflect), the same colour behind
    const env = new THREE.Scene(); env.background = col;
    Object.assign(this.scene, { environment: this.pmrem.fromScene(env, 0).texture, background: col.clone(), environmentIntensity: 1, backgroundIntensity: 1 });
  }

  // the three.js camera of a scene camera on a frame w×h
  camera(id, w, h) {
    const c = (this.doc.cameras || []).find(x => x.id === id) || (this.doc.cameras || [])[0];
    let cam = this.cams.get(c ? c.id : "_"); if (!cam) { cam = new THREE.PerspectiveCamera(); this.cams.set(c ? c.id : "_", cam); }
    if (!c) { cam.position.set(0.3, 0.2, 0.6); cam.lookAt(0, 0.08, 0); return cam; }
    const a = w / h; cam.aspect = a; cam.fov = camFov(c, a);
    const clip = c.clip || [0.01, 100]; cam.near = clip[0]; cam.far = clip[1];
    cam.position.copy(toV(c.loc)); cam.quaternion.copy(viewQ(c.rot));
    const sh = c.shift || [0, 0];
    if (sh[0] || sh[1]) { const L = Math.max(w, h); cam.setViewOffset(w, h, sh[0] * L, -sh[1] * L, w, h); } else cam.clearViewOffset();
    cam.updateProjectionMatrix(); cam.userData.id = c.id;
    return cam;
  }

  // a plain view, the colour of each object (its mask) or its distance (white near): the layers an image model reads the scene from
  // bg: the card's own background {transparent, color, opacity}, a layer apart from the scene (owner 2026-10-03: like a picture's
  // background, it never touches the objects); without it the world's colour or HDRI is behind them
  render(cam, W, H, pass = "beauty", bg = null) {
    const r = this.renderer; r.setSize(W, H, false);
    const tone = r.toneMapping, exp = r.toneMappingExposure; r.toneMapping = this.tone; r.toneMappingExposure = this.exposure;
    const helpersOn = cam.layers.isEnabled(1);
    if (pass === "beauty") {
      const back = this.scene.background;
      if (bg && (bg.transparent || bg.color)) { this.scene.background = null; r.setClearColor(bg.color || "#000000", bg.transparent ? 0 : (bg.opacity ?? 100) / 100); }
      r.render(this.scene, cam); this.scene.background = back; r.setClearColor(0x000000, 0);
      r.toneMapping = tone; r.toneMappingExposure = exp; return;
    }
    const keep = [], back = this.scene.background, env = this.scene.environment;
    this.scene.background = new THREE.Color(0); this.scene.environment = null; cam.layers.disable(1);
    let depthMat = null;
    if (pass === "depth") {
      const d = this.depthRange(cam);
      depthMat = new THREE.ShaderMaterial({ uniforms: { near: { value: d[0] }, far: { value: d[1] } }, toneMapped: false,
        vertexShader: "varying float vz; void main(){ vec4 mv = modelViewMatrix * vec4(position, 1.0); vz = -mv.z; gl_Position = projectionMatrix * mv; }",
        fragmentShader: "uniform float near; uniform float far; varying float vz; void main(){ float d = clamp((vz - near) / (far - near), 0.0, 1.0); gl_FragColor = vec4(vec3(1.0 - d), 1.0); }" });
    }
    for (const u of this.units.values()) {
      if (u.kind !== "object") continue;
      const m = pass === "mask" ? new THREE.MeshBasicMaterial({ color: u.mask, toneMapped: false }) : depthMat;
      u.obj.traverse(x => { if (x.isMesh) { keep.push([x, x.material]); x.material = m; } });
    }
    r.render(this.scene, cam);
    keep.forEach(([x, m]) => { x.material = m; });
    this.scene.background = back; this.scene.environment = env; if (helpersOn) cam.layers.enable(1);
    r.toneMapping = tone; r.toneMappingExposure = exp;
  }

  depthRange(cam) {
    const b = this.meshBounds(), pts = [], f = new THREE.Vector3(0, 0, -1).applyQuaternion(cam.quaternion);
    for (const x of [b.min.x, b.max.x]) for (const y of [b.min.y, b.max.y]) for (const z of [b.min.z, b.max.z]) pts.push(new THREE.Vector3(x, y, z).sub(cam.position).dot(f));
    const near = Math.max(cam.near, Math.min(...pts)), far = Math.max(near + 0.01, Math.max(...pts));
    return [near, far];
  }

  dispose() { this.pmrem.dispose(); }
}

// ---- edits made on the canvas, written back into the file in Blender's terms
export function readBack(view, id) {
  const u = view.units.get(id), doc = view.doc; if (!u) return;
  const g = u.obj;
  if (u.kind === "object") { const o = doc.objects.find(x => x.id === id); o.loc = fromV(g.position); o.rot = objR(g.quaternion); o.scale = fromS(g.scale); }
  if (u.kind === "light") { const l = doc.lights.find(x => x.id === id); l.loc = fromV(g.position); l.rot = viewR(g.quaternion); }
}
export function cameraBack(doc, id, cam) {
  const c = doc.cameras.find(x => x.id === id); if (!c) return;
  c.loc = fromV(cam.position); c.rot = viewR(cam.quaternion);
}

export const newId = () => Math.random().toString(36).slice(2, 10);
export const look = (from, to) => { const c = new THREE.PerspectiveCamera(); c.position.copy(toV(from)); c.lookAt(toV(to)); return viewR(c.quaternion); };

// a new scene (2026-10-05: no product of anyone's by default): a plain shape standing on a floor, a soft key light, a fill, one camera.
// The shape is a stand-in for the subject; a model of the project (3d/models) goes in from «+» when the person picks one. An older
// card that named its model keeps it: model = {id, height_m, title, ai}
export function newDoc(aspect = 0.8, model = null) {
  const rx = aspect >= 1 ? 1600 : Math.round(1600 * aspect), ry = aspect >= 1 ? Math.round(1600 / aspect) : 1600;
  const D = 0.12, H = model ? modelHeight(model) : D;
  const subject = model
    ? { id: newId(), name: model.title || "Модель", src: { type: "model", model: model.id }, loc: [0, 0, H / 2 + 0.0005], rot: [1, 0, 0, 0], scale: [1, 1, 1], ai: model.ai || "" }
    : { id: newId(), name: "Предмет", src: { type: "prim", shape: "sphere", size: [D, D, D] }, loc: [0, 0, D / 2], rot: [1, 0, 0, 0], scale: [1, 1, 1], color: "#b8b8b4", ai: "главный предмет кадра" };
  const key = [-0.45, -0.55, 0.55], fill = [0.7, -0.2, 0.25];
  return tidy({
    format: FORMAT, rev: 0, by: "", render: { x: rx, y: ry },
    world: { color: [0.18, 0.18, 0.18], strength: 1, exposure: 0, look: "AgX" },
    objects: [
      subject,
      { id: newId(), name: "Пол", src: { type: "prim", shape: "plane", size: [3, 3, 0] }, loc: [0, 0, 0], rot: [1, 0, 0, 0], scale: [1, 1, 1], color: "#c9c8c3", ai: "пол студии" },
    ],
    lights: [
      { id: newId(), name: "Ключевой", type: "area", loc: key, rot: look(key, [0, 0, 0.08]), color: [1, 1, 1], power: 25, size: 0.6, size_y: 0.6, shape: "SQUARE" },
      { id: newId(), name: "Заполняющий", type: "area", loc: fill, rot: look(fill, [0, 0, 0.08]), color: [1, 1, 1], power: 8, size: 1, size_y: 1, shape: "SQUARE" },
    ],
    cameras: [{ id: newId(), name: "Камера 1", loc: [0.32, -0.62, 0.2], rot: look([0.32, -0.62, 0.2], [0, 0, +(H / 2 + 0.003).toFixed(3)]), lens: 70, sensor: 36, sensor_h: 24, fit: "AUTO", shift: [0, 0], clip: [0.01, 100] }],
    removed: [],
  }, "active");
}
