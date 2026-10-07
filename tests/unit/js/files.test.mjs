// loaders.js (which files are 3D, the files a person chose, the STEP conversion's answers, a file's short hash), turn.js and
// sprites.js (the turntable sheet's numbers and urls)
import test from "node:test";
import assert from "node:assert/strict";
import * as L from "../../../loaders.js";
import * as T from "../../../turn.js";
import * as SP from "../../../sprites.js";
import { stubFetch } from "./load.mjs";

/* ---- loaders.js: names */
test("a file's format is its extension, any case, and nothing without one", () => {
  assert.equal(L.extOf("a/b/Model.GLB"), "glb");
  assert.equal(L.extOf("part.step"), "step");
  assert.equal(L.extOf("archive.tar.gz"), "gz");
  assert.equal(L.extOf("README"), "");
  assert.equal(L.extOf(""), "");
  assert.equal(L.extOf(null), "");
});

test("3D files are the listed formats and a project model's model.json", () => {
  for (const n of ["a.glb", "a.gltf", "a.obj", "a.stl", "a.fbx", "a.step", "a.STP", "a.iges", "a.igs", "3d/models/shell/model.json", "model.json"]) assert.ok(L.is3d(n), n);
  for (const n of ["a.png", "a.json", "mymodel.json", "a.blend", "", null]) assert.equal(L.is3d(n), false, String(n));
});

test("STEP and IGES are the CAD formats", () => {
  assert.deepEqual(["a.step", "a.stp", "a.iges", "a.IGS", "a.glb"].map(L.isCad), [true, true, true, true, false]);
});

test("the file picker accepts exactly the 3D formats", () => {
  assert.equal(L.ACCEPT, ".glb,.gltf,.obj,.stl,.fbx,.step,.stp,.iges,.igs");
});

test("a file's stem is its name without folder or extension", () => {
  assert.equal(L.stemOf("a/b/Vase v2.final.glb"), "Vase v2.final");
  assert.equal(L.stemOf("x"), "x");
  assert.equal(L.stemOf(undefined), "");
});

test("a library file's url encodes its path as one parameter", () => {
  assert.equal(L.fileUrl("a b/c&d.glb"), "/file?p=a%20b%2Fc%26d.glb");
});

/* ---- loaders.js: chosen files */
test("of the chosen files the 3D one is opened, the best format first, and the others are found beside it by name", () => {
  const files = [new File(["x"], "scene.bin"), new File(["x"], "tex.png"), new File(["x"], "scene.obj"), new File(["x"], "scene.gltf")];
  const c = L.readChosen(files);
  assert.equal(c.name, "scene.gltf");
  assert.match(c.url, /^blob:/);
  assert.match(c.resolve("textures/tex.png"), /^blob:/, "a gltf's link with a folder finds the chosen file by its name");
  assert.equal(c.resolve("missing.png"), null);
  c.done();
});

test("chosen files without a 3D one give nothing", () => {
  assert.equal(L.readChosen([new File(["x"], "a.png")]), null);
  assert.equal(L.readChosen([]), null);
});

/* ---- loaders.js: the STEP conversion */
test("a STEP file the server has converted comes back as its glb's bytes", async () => {
  const glb = new Uint8Array([103, 108, 84, 70]).buffer;
  const f = stubFetch(u => (u.endsWith("/cad") ? { json: { state: "ready", key: "k1" } } : u.endsWith("/cadglb") ? { bytes: glb } : { status: 404 }));
  try {
    const bytes = await L.cadGlb({ name: "part.step", path: "cad/part.step", ver: 2 });
    assert.equal(bytes, glb);
    assert.deepEqual(f.calls.map(c => [c[0], c[1].body]), [["/api/plugin/3d/cad", '{"path":"cad/part.step"}'], ["/api/plugin/3d/cadglb", '{"key":"k1"}']]);
  } finally { f.restore(); }
});

test("two asks for the same STEP file at the same version share one conversion", async () => {
  const f = stubFetch(u => (u.endsWith("/cad") ? { json: { state: "ready", key: "k" } } : { bytes: new ArrayBuffer(1) }));
  try {
    const src = { name: "p.step", path: "p.step", ver: 1 };
    const [a, b] = await Promise.all([L.cadGlb(src), L.cadGlb(src)]);
    assert.equal(a, b);
    assert.equal(f.calls.length, 2, "one /cad and one /cadglb");
    await L.cadGlb(src);
    assert.equal(f.calls.length, 4, "once answered, a later ask asks again");
  } finally { f.restore(); }
});

test("a conversion that failed says why: the server's reason, a lost glb, the network", async () => {
  const cases = [
    [u => (u.endsWith("/cad") ? { json: { state: "failed", reason: "nofreecad" } } : {}), "nofreecad"],
    [u => (u.endsWith("/cad") ? { json: { state: "failed" } } : {}), "unreadable"],
    [u => (u.endsWith("/cad") ? { json: { state: "ready", key: "k" } } : { status: 410 }), "gone"],
    [() => new Error("offline"), "network"],
  ];
  for (const [route, why] of cases) {
    const f = stubFetch(route);
    try {
      await assert.rejects(L.cadGlb({ name: "x.step", path: "x.step" }), e => e instanceof L.CadError && e.cad === why, why);
    } finally { f.restore(); }
  }
});

test("a CAD error's message carries its reason and detail", () => {
  const e = new L.CadError("timeout", "5 min");
  assert.equal(e.message, "cad: timeout (5 min)");
  assert.equal(e.detail, "5 min");
  assert.equal(new L.CadError("gone").message, "cad: gone");
});

/* ---- loaders.js: digest */
test("the same bytes give the same short hash, other bytes another", async () => {
  const a = await L.digest(new TextEncoder().encode("hello").buffer), b = await L.digest(new TextEncoder().encode("hello").buffer);
  const c = await L.digest(new TextEncoder().encode("hellp").buffer);
  assert.equal(a, b);
  assert.notEqual(a, c);
  assert.match(a, /^[0-9a-f]{12}$/, "six bytes of SHA-1 in hex");
  assert.equal(a, "aaf4c61ddcc5");
});

/* ---- turn.js, sprites.js */
test("the turntable is 36 views in 6 columns of 256 px", () => {
  assert.deepEqual({ ...T.SHEET }, { n: 36, cols: 6, cell: 256 });
  assert.equal(T.SHEET.n % T.SHEET.cols, 0, "the sheet is a full grid");
});

test("a sheet's url names the file and its version: the asked one, then the sheet's, then the file's", () => {
  const it = { path: "3d/a b.glb", ver: 3, sprite: { v: 7, n: 36, cols: 6 } };
  assert.equal(T.sheetUrl(it, 9), "/api/sprite?p=3d%2Fa%20b.glb&v=9");
  assert.equal(T.sheetUrl(it), "/api/sprite?p=3d%2Fa%20b.glb&v=7");
  assert.equal(T.sheetUrl({ path: "x.glb", ver: 3 }), "/api/sprite?p=x.glb&v=3");
  assert.equal(T.sheetUrl({ path: "x.glb" }), "/api/sprite?p=x.glb&v=0");
  assert.equal(T.stillUrl({ path: "x.glb" }), "/api/sprite?p=x.glb&v=0&s=240");
  assert.equal(T.stillUrl({ path: "x.glb" }, 120), "/api/sprite?p=x.glb&v=0&s=120");
});

test("a tile's data-spin carries the sheet and its grid, empty while there is no sheet", () => {
  const it = { path: "x.glb", sprite: { v: 2, n: 24, cols: 4 } };
  assert.deepEqual(JSON.parse(T.spinOf(it)), { sheet: "/api/sprite?p=x.glb&v=2", n: 24, cols: 4 });
  assert.equal(T.spinOf({ path: "x.glb" }), "");
});

test("sprites.js gives the same sheet numbers and urls as turn.js", () => {
  assert.equal(SP.SHEET, T.SHEET);
  assert.equal(SP.sheetUrl, T.sheetUrl);
  assert.equal(SP.spinOf, T.spinOf);
});

test("a file that already has its sheet is not drawn again", async () => {
  const it = { path: "x.glb", ver: 1, sprite: { n: 36, cols: 6, cell: 256, v: 1 } };
  assert.equal(await SP.ensure(it), it.sprite);
  assert.equal(SP.known(it), false, "nothing was queued");
});
