// Hyimg 3D, a 3D file in the library's viewer (owner 2026-10-07, project «Field Kit»: STEP files in «modeling C4D», «я не могу их
// смотреть через наш 3D просмотрщик»). A click on a 3D file in the library opens the viewer as for a picture; in place of the picture
// this draws the model with three.js: a drag turns it round its middle, the wheel or a pinch brings it closer, a right drag moves it. A
// STEP or IGES is converted by FreeCAD on the server first (cad.py, once per content, kept in the app's cache): while it works the view
// says so, and when it cannot be read it says why. One WebGL context for the viewer, kept from file to file; drawn only when something
// moved. Loaded by sprites.js (view) only when a 3D file is opened; Hyimg's ui/lib3d.js puts it in the viewer.
import * as THREE from "./vendor/three/build/three.module.js";
import { RoomEnvironment } from "./vendor/three/examples/jsm/environments/RoomEnvironment.js";
import { OrbitControls } from "./vendor/three/examples/jsm/controls/OrbitControls.js";
import { objectOf } from "./sprites.js";
import { isCad } from "./loaders.js";

// why a file shows nothing, in words (the reasons are cad.py's); the page's t() gives them in its language
const WHY = { nofreecad: "FreeCAD is needed to read STEP files", empty: "The file is empty", toobig: "The file is too big to convert",
  timeout: "FreeCAD took too long on this file", nogeometry: "No solids in the file", unreadable: "FreeCAD could not read this file" };
const HEAVY = { mb: 200, tris: 6e6 };   // a viewer of one file can take more than a turntable tile (sprites.js: 80 MB, 3 M triangles)

let R = null, env = null;
function renderer() {
  if (R) return R;
  R = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  R.setClearColor(0x000000, 0); R.outputColorSpace = THREE.SRGBColorSpace; R.toneMapping = THREE.NeutralToneMapping;
  const pm = new THREE.PMREMGenerator(R); env = pm.fromScene(new RoomEnvironment(), 0.04).texture; pm.dispose();
  R.domElement.addEventListener("webglcontextlost", e => { e.preventDefault(); R = null; env = null; });
  return R;
}

const free = root => root.traverse(m => {
  if (!m.isMesh) return;
  m.geometry.dispose();
  for (const mt of [].concat(m.material)) { for (const v of Object.values(mt || {})) if (v && v.isTexture) v.dispose(); if (mt) mt.dispose(); }
});

// el: the viewer's box (sized by the page); it: the library's entry {path, ver, name, model?}; o.t: the page's words; o.alive(): false once
// the page has moved on to another file (a model still loading then never takes the shared view).
// Resolves to {close()} once the model is shown or the reason is said; el.dataset.state is "converting", "loading", "ready" or "failed"
export async function mount(el, it, o = {}) {
  const t = o.t || (k => k), note = document.createElement("div"); note.className = "v3d-note";
  let closed = false, gl = null, root = null, controls = null, ro = null, raf = 0;
  const gone = () => closed || (o.alive && !o.alive());
  const say = (state, words) => { el.dataset.state = state; note.textContent = words || ""; note.hidden = !words; };
  const onCad = e => {   // the server converts a STEP: loaders.js tells the page while it waits
    const d = e.detail || {};
    if (d.path === it.path && d.state === "working" && el.dataset.state !== "ready") say("converting", t("FreeCAD converts the file into a 3D model…"));
  };
  el.appendChild(note); say("loading", t("Loading the 3D model…"));
  addEventListener("hy3d-cad", onCad);
  const close = () => {
    if (closed) return; closed = true; removeEventListener("hy3d-cad", onCad); cancelAnimationFrame(raf);
    if (ro) ro.disconnect(); if (controls) controls.dispose(); if (root) free(root);
    if (gl && gl.domElement.parentNode === el && el._v3dOwner === note) el.removeChild(gl.domElement);
    note.remove();
  };
  try {
    if (!it.model && !isCad(it.path)) {
      const r = await fetch(`/file?p=${encodeURIComponent(it.path)}`, { method: "HEAD" }), mb = +(r.headers.get("Content-Length") || 0) / 1048576;
      if (mb > HEAVY.mb) throw Object.assign(new Error("heavy"), { words: t("The file is over {n} MB", { n: HEAVY.mb }) });
    }
    root = await objectOf(it);
    if (gone()) { close(); return { close }; }
    gl = renderer(); el._v3dOwner = note; el.appendChild(gl.domElement); gl.domElement.className = "v3d-gl";
    const scene = new THREE.Scene(); scene.environment = env;
    const key = new THREE.DirectionalLight(0xffffff, 1.4); key.position.set(1.5, 3, 2); scene.add(key);
    scene.add(root); root.updateWorldMatrix(true, true);
    let tris = 0; root.traverse(m => { if (m.isMesh && m.geometry.attributes.position) tris += (m.geometry.index ? m.geometry.index.count : m.geometry.attributes.position.count) / 3; });
    if (tris > HEAVY.tris) throw Object.assign(new Error("heavy"), { words: t("Too many triangles to show here: {n} million", { n: Math.round(tris / 1e6) }) });
    // seen from a three-quarter view a little above, the whole of it in the frame: its bounding sphere fits the narrower side
    const box = new THREE.Box3().setFromObject(root), c = box.getCenter(new THREE.Vector3()), r = box.getBoundingSphere(new THREE.Sphere()).radius || 0.1;
    const cam = new THREE.PerspectiveCamera(30, 1, r / 100, r * 100), dir = new THREE.Vector3(0.62, 0.42, 0.66).normalize();
    controls = new OrbitControls(cam, gl.domElement); controls.target.copy(c); controls.minDistance = r * 0.2; controls.maxDistance = r * 20;
    const fit = () => {
      const w = el.clientWidth || 1, h = el.clientHeight || 1; gl.setPixelRatio(Math.min(2, devicePixelRatio || 1)); gl.setSize(w, h, false);
      gl.domElement.style.width = w + "px"; gl.domElement.style.height = h + "px"; cam.aspect = w / h; cam.updateProjectionMatrix();
    };
    const draw = () => { raf = 0; if (!closed) gl.render(scene, cam); };
    const ask = () => { if (!raf && !closed) raf = requestAnimationFrame(draw); };
    fit();
    const half = Math.atan(Math.tan(cam.fov * Math.PI / 360) * Math.min(1, cam.aspect));
    cam.position.copy(c).addScaledVector(dir, r * 1.15 / Math.sin(half)); cam.lookAt(c); controls.update();
    controls.addEventListener("change", ask);
    ro = new ResizeObserver(() => { fit(); ask(); }); ro.observe(el);
    el._v3d = { cam, controls, draw: () => gl.render(scene, cam) };   // for the tests
    gl.render(scene, cam); say("ready", "");
  } catch (e) {
    if (gone()) { close(); return { close }; }
    say("failed", e.words || (e.cad ? t(WHY[e.cad] || WHY.unreadable) : t("This 3D file cannot be shown")));
    if (gl && gl.domElement.parentNode === el && el._v3dOwner === note) el.removeChild(gl.domElement);
  }
  return { close };
}
