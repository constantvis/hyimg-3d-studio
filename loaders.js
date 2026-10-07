// Hyimg 3D, files of other formats (owner 2026-10-06: «Open file…» and the media library's 3D filter). The scene holds glb files (scene.js
// src {type: "file"}); a file of another format is read here into a three.js object, and a scene gets it as a glb written once beside the
// file's copy (engine.js putFile), so Blender and the rest of the plugin see one format. Formats: glb, gltf (with its .bin and pictures
// beside it), obj (no .mtl: plain grey), stl (z up, as CAD gives it), fbx. STEP and IGES (owner 2026-10-06: «convert a STEP file once to a 3D
// model with FreeCAD, which is already on this Mac, and keep the result, the same way videos already get a WebM copy»): the server converts
// them once to a glb with FreeCAD in the background (cad.py, kept in the app's cache) and this file fetches that glb; metres, y up, colours kept.
import * as THREE from "./vendor/three/build/three.module.js";
import { GLTFLoader } from "./vendor/three/examples/jsm/loaders/GLTFLoader.js";
import { DRACOLoader } from "./vendor/three/examples/jsm/loaders/DRACOLoader.js";
import { GLTFExporter } from "./vendor/three/examples/jsm/exporters/GLTFExporter.js";

export const CAD = ["step", "stp", "iges", "igs"];
export const EXTS = ["glb", "gltf", "obj", "stl", "fbx", ...CAD];
export const ACCEPT = EXTS.map(e => "." + e).join(",");
export const extOf = name => ((/\.([A-Za-z0-9]+)$/.exec(name || "") || [])[1] || "").toLowerCase();
export const is3d = name => EXTS.includes(extOf(name)) || /(^|\/)model\.json$/.test(name || "");
export const isCad = name => CAD.includes(extOf(name));
export const stemOf = name => String(name || "").replace(/^.*\//, "").replace(/\.[^.]+$/, "");
export const fileUrl = p => `/file?p=${encodeURIComponent(p)}`;

const BASE = new URL(".", import.meta.url).href;
const RES = "hyimg-res://";   // what a gltf's relative links resolve to; the manager hands each one to resolve(name)
const NEUTRAL = () => new THREE.MeshStandardMaterial({ color: "#b8b8b4", roughness: 0.6, metalness: 0 });   // as the scene's plain shapes

// ---- STEP and IGES: the glb FreeCAD made of the file. A library file is asked for by its path, a chosen one (not in the library) is sent
// first; both answer {state: "working" | "ready" | "failed", key, reason}. The page sees it as a "hy3d-cad" event on window ({name, path,
// state, reason}): the library's tile says «converting…» and why it could not, the empty card says it too.
const PLUGIN = (/\/plugins\/([^/]+)\//.exec(import.meta.url) || [])[1] || "3d";
const post = (route, body, q = "") => fetch(`/api/plugin/${encodeURIComponent(PLUGIN)}/${route}${q}`, { method: "POST", body });
export class CadError extends Error { constructor(reason, detail) { super(`cad: ${reason}${detail ? ` (${detail})` : ""}`); this.cad = reason; this.detail = detail || ""; } }
const sleep = ms => new Promise(ok => setTimeout(ok, ms));
const ASKED = new Map();   // path@version -> the glb's bytes in flight: a sheet and a card asking for the same file wait for one answer
// src: {name, path?} of a library file, or {name, file} chosen in the system's panel; the glb as bytes
export function cadGlb(src) {
  const k = src.path ? `${src.path}@${src.ver || 0}` : null;
  if (k && ASKED.has(k)) return ASKED.get(k);
  const p = cadFetch(src).finally(() => k && ASKED.delete(k));
  if (k) ASKED.set(k, p);
  return p;
}
async function cadFetch(src) {
  const info = { name: stemOf(src.name), path: src.path || null }, say = d => { try { dispatchEvent(new CustomEvent("hy3d-cad", { detail: { ...info, ...d } })); } catch (e) { /* no window */ } };
  try {
    const ask = body => post("cad", JSON.stringify(body)).then(r => r.json());
    let st = src.file ? await post("cadput", await src.file.arrayBuffer(), `?name=${encodeURIComponent(src.name)}`).then(r => r.json()) : await ask({ path: src.path });
    for (let i = 0; st.state === "working" && i < 2000; i++) {   // the server's own limit is 5 minutes for a file, the others queue behind it
      say({ state: "working" }); await sleep(i < 5 ? 400 : 900);
      st = await ask(src.file ? { key: st.key } : { path: src.path });
    }
    if (st.state !== "ready") throw new CadError(st.state === "working" ? "timeout" : st.reason || "unreadable", st.error);
    const r = await post("cadglb", JSON.stringify({ key: st.key }));
    if (!r.ok) throw new CadError("gone");
    const bytes = await r.arrayBuffer(); say({ state: "ready" });
    return bytes;
  } catch (e) {
    const err = e instanceof CadError ? e : new CadError("network", e && e.message);
    say({ state: "failed", reason: err.cad, detail: err.detail }); throw err;
  }
}

// src: {name, url, resolve?(name) -> url}: the file's name decides the format, url is where its bytes are (the library's /file, or a blob:
// of a file the person chose), resolve finds the files a gltf names beside it; path (a library file) or file (a chosen one) is what a STEP needs
export async function loadObject(src) {
  const ext = extOf(src.name), manager = new THREE.LoadingManager();
  manager.setURLModifier(u => (u.startsWith(RES) && src.resolve ? src.resolve(decodeURIComponent(u.slice(RES.length))) || u : u));
  if (CAD.includes(ext)) {   // FreeCAD's glb (cad.py), read as any glb
    const glb = await cadGlb(src);
    return new Promise((ok, bad) => new GLTFLoader(manager).parse(glb, "", g => ok(g.scene), bad));
  }
  if (ext === "glb" || ext === "gltf") {
    const draco = new DRACOLoader(manager); draco.setDecoderPath(BASE + "vendor/draco/");
    const loader = new GLTFLoader(manager); loader.setDRACOLoader(draco); loader.setResourcePath(RES);
    const g = await new Promise((ok, bad) => loader.load(src.url, ok, undefined, bad)); draco.dispose();
    return g.scene;
  }
  const bytes = async () => { const r = await fetch(src.url); if (!r.ok) throw new Error(`${src.name}: ${r.status}`); return r; };
  if (ext === "obj") {
    const { OBJLoader } = await import("./vendor/three/examples/jsm/loaders/OBJLoader.js");
    const o = new OBJLoader(manager).parse(await (await bytes()).text());
    o.traverse(m => { if (m.isMesh) m.material = NEUTRAL(); });
    return o;
  }
  if (ext === "stl") {
    const { STLLoader } = await import("./vendor/three/examples/jsm/loaders/STLLoader.js");
    const geo = new STLLoader(manager).parse(await (await bytes()).arrayBuffer());
    if (!geo.attributes.normal) geo.computeVertexNormals();
    const mesh = new THREE.Mesh(geo, NEUTRAL()), g = new THREE.Group(); mesh.rotation.x = -Math.PI / 2; g.add(mesh);   // z up in the file, y up here
    return g;
  }
  if (ext === "fbx") {
    const { FBXLoader } = await import("./vendor/three/examples/jsm/loaders/FBXLoader.js");
    return new FBXLoader(manager).parse(await (await bytes()).arrayBuffer(), RES);
  }
  throw new Error(`unknown format .${ext}`);
}

// the files a person chose in the system's panel: the one that is a 3D file, and where the others (a gltf's .bin, its pictures) are
export function readChosen(files) {
  const list = [...files], rank = e => EXTS.indexOf(e), main = list.filter(f => is3d(f.name)).sort((a, b) => rank(extOf(a.name)) - rank(extOf(b.name)))[0];
  if (!main) return null;
  const urls = new Map(list.map(f => [f.name, URL.createObjectURL(f)]));
  return { file: main, name: main.name, url: urls.get(main.name), resolve: n => urls.get(n.replace(/^.*\//, "")) || null, done: () => urls.forEach(u => URL.revokeObjectURL(u)) };
}

// an object as one glb (binary), for the scene and for Blender
export const toGlb = obj => { const root = new THREE.Group(); root.add(obj); return new GLTFExporter().parseAsync(root, { binary: true }); };

// a short hash of bytes or text, for a file's folder name (a file chosen twice is written once)
export async function digest(buf) {
  if (globalThis.crypto && crypto.subtle) { try { return [...new Uint8Array(await crypto.subtle.digest("SHA-1", buf))].slice(0, 6).map(b => b.toString(16).padStart(2, "0")).join(""); } catch (e) { /* not a secure page */ } }
  let h = 0x811c9dc5; const v = new Uint8Array(buf); for (let i = 0; i < v.length; i++) { h ^= v[i]; h = Math.imul(h, 0x01000193) >>> 0; }
  return h.toString(16).padStart(8, "0") + v.length.toString(16);
}
