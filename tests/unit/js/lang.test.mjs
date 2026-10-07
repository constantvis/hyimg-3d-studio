// lang.js: the plugin's Russian words, how they reach the board's T, the English a board without T shows, and the editor's
// control labels (engine.js LABELS), which DialKit shows with a space put before every Latin capital
import test from "node:test";
import assert from "node:assert/strict";
import { read, url } from "./load.mjs";

let n = 0;
const fresh = () => import(url("lang.js") + "?fresh=" + ++n);   // a module of its own: its «strings handed over» flag starts unset
const holes = s => [...String(s).matchAll(/\{(\w+)\}/g)].map(m => m[1]).sort().join(",");
const asked = f => [...new Set([...read(f).matchAll(/\bt\(\s*"((?:[^"\\]|\\.)*)"/g)].map(m => JSON.parse('"' + m[1] + '"')))];
// engine.js's LABELS: the words its controls are named by, read from the source (engine.js needs a page to run)
const LABELS = (() => { const s = read("engine.js"), a = s.indexOf("const LABELS = "), b = s.indexOf("};", a); return Function("return " + s.slice(a + 15, b + 1))(); })();

test("every Russian word has exactly the placeholders of its English key, in every form", async () => {
  const { RU } = await fresh(), bad = [];
  for (const [k, v] of Object.entries(RU)) for (const form of [].concat(v)) if (holes(form) !== holes(k)) bad.push(`«${k}» → «${form}»`);
  assert.deepEqual(bad, []);
});

test("every English plural has two forms, every one of them with {n}", async () => {
  const { EN } = await fresh();
  for (const [k, v] of Object.entries(EN)) { assert.equal(v.length, 2, k); for (const f of v) assert.match(f, /\{n\}/, k); }
});

test("a Russian count agrees with its number: an English plural has three Russian forms", {
  todo: "lang.js:13-15 «{n} objects», «{n} lights», «{n} cameras» are one Russian string each; «{n} предм.» and «{n} кам.» read with any number, but «{n} света» gives «1 света» and «5 света» (the card's meta line, canvas.js:236)",
}, async () => {
  const { RU, EN } = await fresh();
  for (const k of Object.keys(EN)) assert.ok(Array.isArray(RU[k]) && RU[k].length === 3, `«${k}»: ${JSON.stringify(RU[k])}`);
});

test("every key the editor, the scene and the empty card ask for has its Russian", async () => {
  const { RU } = await fresh(), missing = [];
  // canvas.js is being edited by another session right now
  for (const f of ["engine.js", "scene.js", "empty.js", "sprites.js", "loaders.js"]) for (const k of asked(f)) if (!(k in RU)) missing.push(`${f}: «${k}»`);
  assert.deepEqual(missing, []);
});

test("every control label of the editor has its Russian", async () => {
  const { RU } = await fresh();
  assert.ok(Object.keys(LABELS).length > 20);
  for (const w of Object.values(LABELS)) assert.ok(w in RU, `«${w}»`);
});

test("no control label has a Latin capital DialKit would split off, in either language", {
  todo: "lang.js:212 «Pull tool» is «Тянуть (T)»: DialKit's formatLabel (vendor/dialkit/index.js:266) shows it as «Тянуть ( T)», the rule of lang.js:6-7",
}, async () => {
  const { RU } = await fresh(), split = w => /[^\s][A-Z]/.test(w), bad = [];
  for (const w of Object.values(LABELS)) { if (split(w)) bad.push(w); if (RU[w] && split(RU[w])) bad.push(`${w} → ${RU[w]}`); }
  assert.deepEqual(bad, []);
});

test("a board with T gets the words once, every key under the plugin's prefix", async () => {
  const L = await fresh(), handed = [];
  const HY = { t: (k, v) => `T(${k})${v ? JSON.stringify(v) : ""}`, strings: d => handed.push(d) };
  const t = L.translator(HY); L.translator(HY);
  assert.equal(handed.length, 1);
  assert.ok(Object.keys(handed[0].ru).every(k => k.startsWith("3d::")));
  assert.equal(Object.keys(handed[0].ru).length, Object.keys(L.RU).length);
  assert.equal(t("3D scene"), "T(3d::3D scene)");
});

test("a board without T shows the English, plurals by the number", async () => {
  const { translator } = await fresh(), t = translator({});
  assert.equal(t("3D scene"), "3D scene");
  assert.equal(t("{n} lights", { n: 1 }), "1 light");
  assert.equal(t("{n} lights", { n: 0 }), "0 lights");
  assert.equal(t("3D: file {name}", { name: "a.glb" }), "3D: file a.glb");
});
