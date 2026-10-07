// scene.js: Blender's terms (metres, z up, quaternions [w, x, y, z], lens on a sensor) and three.js's, both ways; the file's tidy form;
// a new scene; the heavy-scene guard's numbers. scene.js imports three.js from vendor/ and runs in node as it is.
import test from "node:test";
import assert from "node:assert/strict";
import * as THREE from "../../../vendor/three/build/three.module.js";
import * as S from "../../../scene.js";

const near = (a, b, eps = 1e-9, msg) => assert.ok(Math.abs(a - b) < eps, `${msg || ""} ${a} vs ${b}`);
const nearV = (a, b, eps = 1e-9, msg) => { assert.equal(a.length, b.length); a.forEach((x, i) => near(x, b[i], eps, `${msg || ""}[${i}]`)); };
// the same rotation: q and -q
const sameQ = (a, b, eps = 1e-9) => { const s = Math.sign(a[0] * b[0] + a[1] * b[1] + a[2] * b[2] + a[3] * b[3]) || 1; nearV(a, b.map(x => x * s), eps); };
const rng = seed => () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
const unitQ = r => { const v = [r() * 2 - 1, r() * 2 - 1, r() * 2 - 1, r() * 2 - 1], n = Math.hypot(...v); return v.map(x => x / n); };
const bq = r => new THREE.Quaternion(r[1], r[2], r[3], r[0]);

/* ---- axes */
test("a Blender point (x, y, z) is (x, z, -y) in three.js and back", () => {
  const v = S.toV([1, 2, 3]);
  assert.deepEqual([v.x, v.y, v.z], [1, 3, -2]);
  assert.deepEqual(S.fromV(v), [1, 2, 3]);
});

test("an object's rotation goes to three.js and back unchanged", () => {
  const r = rng(7);
  for (let i = 0; i < 50; i++) { const q = unitQ(r); sameQ(S.objR(S.objQ(q)), q, 1e-12); }
});

test("a camera's or light's rotation goes to three.js and back unchanged", () => {
  const r = rng(11);
  for (let i = 0; i < 50; i++) { const q = unitQ(r); sameQ(S.viewR(S.viewQ(q)), q, 1e-12); }
});

test("an object turned in Blender and then converted lands where the converted object turned in three.js lands", () => {
  const r = rng(3);
  for (let i = 0; i < 20; i++) {
    const q = unitQ(r), p = [r() - 0.5, r() - 0.5, r() - 0.5];
    const inBlender = new THREE.Vector3(...p).applyQuaternion(bq(q));   // Blender's own maths on its own axes
    const there = S.toV([inBlender.x, inBlender.y, inBlender.z]);
    const here = S.toV(p).applyQuaternion(S.objQ(q));
    nearV([here.x, here.y, here.z], [there.x, there.y, there.z], 1e-12);
  }
});

test("a camera with no rotation looks down Blender's -z, which is three.js's -y", () => {
  const dir = new THREE.Vector3(0, 0, -1).applyQuaternion(S.viewQ([1, 0, 0, 0]));
  nearV([dir.x, dir.y, dir.z], [0, -1, 0], 1e-12);
});

test("look() turns a camera at a point toward another", () => {
  const from = [0.32, -0.62, 0.2], to = [0, 0, 0.06];
  const dir = new THREE.Vector3(0, 0, -1).applyQuaternion(S.viewQ(S.look(from, to)));
  const want = S.toV(to).sub(S.toV(from)).normalize();
  nearV([dir.x, dir.y, dir.z], [want.x, want.y, want.z], 1e-9);
});

/* ---- the file's tidy form */
test("tidy rounds places to 0.01 mm and writes no negative zero", () => {
  const d = S.tidy({ objects: [{ loc: [0.1234567, -0.0000001, 2], scale: [1.000004, 1, 1] }] });
  assert.deepEqual(d.objects[0].loc, [0.12346, 0, 2]);
  assert.ok(!Object.is(d.objects[0].loc[1], -0));
  assert.deepEqual(d.objects[0].scale, [1.00000, 1, 1]);
});

test("tidy writes rotations as unit quaternions with w not negative", () => {
  const d = S.tidy({ lights: [{ rot: [-2, 0, 0, 0] }], cameras: [{ rot: [0.5, 0.5, 0.5, 0.5] }] });
  assert.deepEqual(d.lights[0].rot, [1, 0, 0, 0]);
  assert.deepEqual(d.cameras[0].rot, [0.5, 0.5, 0.5, 0.5]);
});

test("tidy is stable: a tidy file tidied again is the same", () => {
  const a = S.tidy(S.newDoc(1.2)), b = S.tidy(JSON.parse(JSON.stringify(a)));
  assert.deepEqual(b, a);
});

test("an active scene gets its first camera as the active one when it has none", () => {
  assert.equal(S.tidy({ cameras: [{ id: "c1" }, { id: "c2" }] }, true).active_camera, "c1");
  assert.equal(S.tidy({ cameras: [{ id: "c1" }], active_camera: "c9" }, true).active_camera, "c9");
  assert.equal(S.tidy({ cameras: [{ id: "c1" }] }).active_camera, undefined);
});

test("the state key ignores who wrote the file, when and its revision", () => {
  const a = { format: S.FORMAT, objects: [1], rev: 3, by: "blender", t: 99 }, b = { format: S.FORMAT, objects: [1], rev: 9, by: "canvas", t: 1 };
  assert.equal(S.stateKey(a), S.stateKey(b));
  assert.notEqual(S.stateKey(a), S.stateKey({ ...b, objects: [2] }));
  assert.equal(a.rev, 3, "the file itself is not changed");
});

/* ---- lens and angle of view */
test("a 50 mm lens on a 36 mm sensor sees 39.6° along the sensor's width", () => {
  near(S.camFov({ lens: 50, fit: "VERTICAL", sensor_h: 36 }, 1), 2 * Math.atan(18 / 50) * 180 / Math.PI, 1e-12);
  near(S.camFov({ lens: 50 }, 0.8), 39.5978, 1e-4, "a portrait frame: the width runs along its long side");
});

test("a landscape frame on AUTO gets the vertical angle from the width and the aspect", () => {
  const h = 2 * Math.atan(18 / 50);
  near(S.camFov({ lens: 50 }, 1.5), 2 * Math.atan(Math.tan(h / 2) / 1.5) * 180 / Math.PI, 1e-12);
});

test("lensFor is the inverse of camFov for every fit and aspect", () => {
  for (const fit of ["AUTO", "HORIZONTAL", "VERTICAL"]) for (const aspect of [0.5, 0.8, 1, 1.5, 2.4]) for (const lens of [12, 35, 50, 85, 200]) {
    const c = { lens, sensor: 36, sensor_h: 24, fit };
    near(S.lensFor(S.camFov(c, aspect), c, aspect), lens, 1e-9, `${fit} ${aspect} ${lens}`);
  }
});

test("a camera without lens or sensor is Blender's default 50 mm on 36 × 24", () => {
  near(S.camFov({}, 1.5), S.camFov({ lens: 50, sensor: 36, sensor_h: 24, fit: "AUTO" }, 1.5), 1e-12);
});

/* ---- writing back */
test("an object moved on the canvas is written back in Blender's terms", () => {
  const o = { id: "a", loc: [0, 0, 0], rot: [1, 0, 0, 0], scale: [1, 1, 1] };
  const g = new THREE.Object3D();
  g.position.copy(S.toV([0.1, -0.2, 0.3])); g.quaternion.copy(S.objQ([Math.SQRT1_2, 0, 0, Math.SQRT1_2])); g.scale.set(2, 4, 3);   // three's y is Blender's z
  S.readBack({ units: new Map([["a", { kind: "object", obj: g }]]), doc: { objects: [o], lights: [] } }, "a");
  nearV(o.loc, [0.1, -0.2, 0.3], 1e-12);
  sameQ(o.rot, [Math.SQRT1_2, 0, 0, Math.SQRT1_2], 1e-12);
  assert.deepEqual(o.scale, [2, 3, 4]);
});

test("a camera moved on the canvas is written back, an unknown camera is left alone", () => {
  const doc = { cameras: [{ id: "c", loc: [0, 0, 0], rot: [1, 0, 0, 0] }] }, cam = new THREE.PerspectiveCamera();
  cam.position.copy(S.toV([1, 2, 3])); cam.quaternion.copy(S.viewQ([0.5, 0.5, 0.5, 0.5]));
  S.cameraBack(doc, "c", cam);
  nearV(doc.cameras[0].loc, [1, 2, 3], 1e-12);
  sameQ(doc.cameras[0].rot, [0.5, 0.5, 0.5, 0.5], 1e-12);
  assert.doesNotThrow(() => S.cameraBack(doc, "nope", cam));
});

/* ---- a new scene */
test("a new scene is a shape on a floor, a key and a fill light and one active camera", () => {
  const d = S.newDoc(0.8);
  assert.equal(d.format, S.FORMAT);
  assert.deepEqual(d.render, { x: 1280, y: 1600 });
  assert.deepEqual(d.objects.map(o => o.src.shape), ["sphere", "plane"]);
  assert.deepEqual(d.lights.map(l => l.type), ["area", "area"]);
  assert.equal(d.cameras.length, 1);
  assert.equal(d.active_camera, d.cameras[0].id);
  const ids = [...d.objects, ...d.lights, ...d.cameras].map(x => x.id);
  assert.equal(new Set(ids).size, ids.length, "every id is its own");
  near(d.objects[0].loc[2], 0.06, 1e-12, "the sphere stands on the floor");
});

test("a landscape scene renders 1600 px wide", () => {
  assert.deepEqual(S.newDoc(2).render, { x: 1600, y: 800 });
  assert.deepEqual(S.newDoc(1).render, { x: 1600, y: 1600 });
});

test("the lights of a new scene look at the subject", () => {
  const d = S.newDoc();
  for (const l of d.lights) {
    const dir = new THREE.Vector3(0, 0, -1).applyQuaternion(S.viewQ(l.rot));
    const want = S.toV([0, 0, 0.08]).sub(S.toV(l.loc)).normalize();
    assert.ok(dir.dot(want) > 0.9999, l.name);
  }
});

test("a scene made for a project model stands that model at its real height", () => {
  const d = S.newDoc(0.8, { id: "shell", height_m: 0.163, title: "Vase", ai: "a vase" });
  const m = d.objects[0];
  assert.deepEqual(m.src, { type: "model", model: "shell" });
  assert.equal(m.name, "Vase");
  near(m.loc[2], 0.163 / 2 + 0.0005, 1e-5);
});

test("a model that does not say its height is 20 cm tall", () => {
  assert.equal(S.modelHeight({}), 0.2);
  assert.equal(S.modelHeight(null), 0.2);
  assert.equal(S.modelHeight({ height_m: -1 }), 0.2);
  assert.equal(S.modelHeight({ height_m: 0.15 }), 0.15);
});

/* ---- layers */
test("a layer is named by the path of names under its object, the mirrored half marked", () => {
  const unit = new THREE.Group(), wrap = new THREE.Group(), phone = new THREE.Group(), glass = new THREE.Mesh();
  phone.name = "phone"; glass.name = "glass"; glass.userData.mirror = true;
  unit.add(wrap); wrap.add(phone); phone.add(glass);
  assert.equal(S.layerPath(unit, glass), "phone/glass~зеркало");
  assert.equal(S.layerPath(unit, phone), "phone");
  const anon = new THREE.Mesh(); phone.add(anon); anon.userData.label = "Back";
  assert.equal(S.layerPath(unit, anon), "phone/Back");
  assert.equal(S.nodeLabel(new THREE.Object3D()), "узел");
});

/* ---- heavy scenes */
test("the weight of a scene counts triangles and each texture's memory once", () => {
  const tex = new THREE.Texture(); tex.image = { width: 1024, height: 1024 };
  const mat = new THREE.MeshStandardMaterial({ map: tex, roughnessMap: tex });
  const root = new THREE.Group();
  root.add(new THREE.Mesh(new THREE.BoxGeometry(), mat));                                           // indexed: 12 triangles
  root.add(new THREE.Mesh(new THREE.BoxGeometry().toNonIndexed(), [mat, new THREE.MeshBasicMaterial()]));   // 36 vertices: 12 triangles
  const w = S.weight(root);
  assert.equal(w.tris, 24);
  near(w.texMb, 1024 * 1024 * 4 * 1.33 / 1048576, 1e-9);
});

test("a heavy scene says only what is over its limits", () => {
  assert.equal(S.heavyText({ mb: 120.4 }), "heavy scene: 120 MB of files");
  assert.equal(S.heavyText({ tris: 4.25e6, texMb: 700 }), "heavy scene: 4.3 million triangles, 700 MB of textures");
  const e = new S.Heavy({ mb: 90 });
  assert.ok(e instanceof Error);
  assert.deepEqual(e.heavy, { mb: 90 });
  assert.equal(e.message, "heavy scene: 90 MB of files");
});

test("the scene's words follow the language handed over", () => {
  S.setT((k, v) => "RU:" + k.replace(/\{(\w+)\}/g, (m, x) => v[x]));
  try { assert.equal(S.heavyText({ mb: 81 }), "RU:heavy scene: RU:81 MB of files"); }
  finally { S.setT((k, v) => (v ? k.replace(/\{(\w+)\}/g, (m, x) => (x in v ? String(v[x]) : m)) : k)); }
});
