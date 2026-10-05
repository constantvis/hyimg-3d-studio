// The canvas maths against Blender's own glTF exporter: the same camera, lights and object, converted by scene.js from the scene file
// and by Blender into glTF, must stand in the same place, turn the same way and see the same angle. Run after blender_test.py:
//   node tests/convert_test.mjs <the folder blender_test.py wrote>
import fs from "node:fs";
import path from "node:path";
const dir = process.argv[2];
globalThis.fetch = globalThis.fetch || (() => { throw new Error("no fetch"); });
// scene.js imports loaders that touch the DOM only when used; RectAreaLightUniformsLib.init needs nothing from the page
const S = await import(path.resolve(new URL(".", import.meta.url).pathname, "../scene.js"));
const doc = JSON.parse(fs.readFileSync(path.join(dir, "first.json"), "utf8"));
const g = JSON.parse(fs.readFileSync(path.join(dir, "official.gltf"), "utf8"));
const node = name => g.nodes.find(n => n.name === name);
let fails = 0;
const near = (a, b, eps, what) => { const ok = a.every((v, i) => Math.abs(v - b[i]) < eps); console.log((ok ? "ok   " : "FAIL ") + what + (ok ? "" : ` ${JSON.stringify(a)} vs ${JSON.stringify(b)}`)); if (!ok) fails++; };
const qsame = (q, n, what) => { const a = [q.x, q.y, q.z, q.w], b = n.rotation || [0, 0, 0, 1], s = Math.sign(a.reduce((t, v, i) => t + v * b[i], 0)) || 1; near(a.map(v => v * s), b, 1e-4, what); };

const cam = doc.cameras[0], cn = node(cam.name);
const v = S.toV(cam.loc); near([v.x, v.y, v.z], cn.translation, 1e-4, "camera position");
qsame(S.viewQ(cam.rot), cn, "camera turn");
const yfov = g.cameras[cn.camera].perspective.yfov * 180 / Math.PI, aspect = doc.render.x / doc.render.y;
near([S.camFov(cam, aspect)], [yfov], 1e-3, `camera vertical angle (${yfov.toFixed(3)}°)`);
near([S.lensFor(S.camFov(cam, aspect), cam, aspect)], [cam.lens], 1e-6, "lens back from the angle");
for (const l of doc.lights) {
  const n = node(l.name); if (!n) { console.log("FAIL no glTF node for " + l.name); fails++; continue; }
  // the exporter turns a light by its own fix-up node when the light has children; ours have none, so the node carries the light
  const p = S.toV(l.loc); near([p.x, p.y, p.z], n.translation || [0, 0, 0], 1e-4, `${l.type} light position`);
  qsame(S.viewQ(l.rot), n, `${l.type} light turn`);
}
const o = doc.objects[0], on = node(o.name);
const p = S.toV(o.loc); near([p.x, p.y, p.z], on.translation, 1e-4, "object position");
qsame(S.objQ(o.rot), on, "object turn");
near([o.scale[0], o.scale[2], o.scale[1]], on.scale, 1e-4, "object scale");
// and back: three.js -> Blender gives the file's numbers
const r = S.objR(S.objQ(o.rot)), c = S.viewR(S.viewQ(cam.rot));
near(r.map(x => x * Math.sign(r[0])), o.rot, 1e-5, "object turn back"); near(c.map(x => x * Math.sign(c[0])), cam.rot, 1e-5, "camera turn back");
console.log(fails ? `FAILS: ${fails}` : "FAILS: 0");
process.exit(fails ? 1 : 0);
