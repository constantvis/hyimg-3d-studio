// sections.js: the layer list's Objects / Lights / Cameras as one stack (owner 2026-10-06, three screenshots: «когда я двигаю за одну из
// этих, нижняя должна тоже с ней идти», «если я какое-то складываю, то у других появляется больше пространства», «странное расстояние,
// когда в сложенной позиции»). The numbers are the owner's scene: 87 objects, 3 lights, 18 cameras, rows of 28 px under 30 px titles.
import test from "node:test";
import assert from "node:assert/strict";
import { url } from "./load.mjs";

const { layout, drag, fold, reset } = await import(url("sections.js"));

const ROW = 28, PAD = 4, rows = n => n * ROW + PAD;
const OWNER = [{ k: "objects", content: rows(87) }, { k: "lights", content: rows(3) }, { k: "cameras", content: rows(18) }];
const SMALL = [{ k: "objects", content: rows(2) }, { k: "lights", content: rows(2) }, { k: "cameras", content: rows(1) }];
const H = 730, AVAIL = H - 3 * 30;   // the stack's height, and what is left for the rows under three titles
const auto = () => ({ objects: { size: null, shut: false }, lights: { size: null, shut: false }, cameras: { size: null, shut: false } });
const sum = L => Object.values(L.h).reduce((a, b) => a + b, 0);
const bottom = (L, k) => L.top[k] + 30 + L.h[k];   // where a section ends: its title and its rows

test("automatic: a short section hugs its rows, the long ones share the rest, the panel is full", () => {
  const L = layout(OWNER, auto(), H);
  assert.equal(L.h.lights, rows(3));
  assert.equal(L.h.objects + L.h.cameras, AVAIL - rows(3));
  assert.ok(Math.abs(L.h.objects - L.h.cameras) <= 1, L.h);
  assert.equal(L.free, 0);
  // the stack has no gaps: each title starts where the section above ends, the handle takes no room
  assert.equal(L.top.objects, 0); assert.equal(L.top.lights, bottom(L, "objects")); assert.equal(L.top.cameras, bottom(L, "lights"));
  assert.equal(bottom(L, "cameras"), H);
  assert.deepEqual(L.handles, { lights: "objects", cameras: "lights" });
});

test("a handle dragged down: the section above grows, the ones below keep their size and move with it, the last one gives the room", () => {
  const st = auto(), L0 = layout(OWNER, st, H), st1 = drag(OWNER, st, H, "lights", 60, L0), L1 = layout(OWNER, st1, H);
  assert.equal(L1.h.objects, L0.h.objects + 60);
  assert.equal(L1.h.lights, L0.h.lights); assert.equal(L1.top.lights, L0.top.lights + 60);
  assert.equal(L1.h.cameras, L0.h.cameras - 60); assert.equal(L1.top.cameras, L0.top.cameras + 60);
  assert.equal(bottom(L1, "cameras"), H);
  assert.equal(st1.lights.size, null, "Lights shows all its rows and stays automatic");
});

test("a handle dragged up is the mirror: the section above shrinks, the ones below move up, the last one takes the room", () => {
  const st = auto(), L0 = layout(OWNER, st, H), L1 = layout(OWNER, drag(OWNER, st, H, "lights", -60, L0), H);
  assert.equal(L1.h.objects, L0.h.objects - 60);
  assert.equal(L1.h.lights, L0.h.lights); assert.equal(L1.top.lights, L0.top.lights - 60);
  assert.equal(L1.h.cameras, L0.h.cameras + 60); assert.equal(bottom(L1, "cameras"), H);
});

test("down and back up again is where it started", () => {
  const st = auto(), L0 = layout(OWNER, st, H), st1 = drag(OWNER, st, H, "lights", 80, L0), L1 = layout(OWNER, st1, H);
  const L2 = layout(OWNER, drag(OWNER, st1, H, "lights", -80, L1), H);
  assert.deepEqual(L2.h, L0.h); assert.deepEqual(L2.top, L0.top);
});

test("past the room: the sections below shrink in order from the bottom, each down to one row, the handle stops", () => {
  const st = auto(), L0 = layout(OWNER, st, H), L1 = layout(OWNER, drag(OWNER, st, H, "lights", 5000, L0), H);
  assert.equal(L1.h.cameras, ROW); assert.equal(L1.h.lights, ROW);
  assert.equal(L1.h.objects, AVAIL - 2 * ROW); assert.equal(bottom(L1, "cameras"), H);
  // the lower handle pushed up past its one row pushes the one above it, as far as the last one has rows to show: the room never
  // ends up empty at the bottom while a section above is cut
  const L2 = layout(OWNER, drag(OWNER, st, H, "cameras", -5000, L0), H);
  assert.equal(L2.h.lights, ROW); assert.equal(L2.h.cameras, rows(18), "the last one grows up to its rows");
  assert.equal(L2.h.objects, AVAIL - ROW - rows(18)); assert.equal(L2.free, 0);
});

test("a drag never leaves a gap: a section that shows all its rows does not grow, and none is cut to leave room empty", () => {
  const st = auto(), L0 = layout(SMALL, st, H), L1 = layout(SMALL, drag(SMALL, st, H, "lights", 60, L0), H);
  assert.deepEqual(L1.h, L0.h);
  const st2 = drag(SMALL, st, H, "lights", -20, L0), L2 = layout(SMALL, st2, H);
  assert.deepEqual(L2.h, L0.h); assert.equal(st2.objects.size, null, "it stays automatic");
});

test("what a drag leaves is what the layout draws, at every step", () => {
  const st = auto(), L0 = layout(OWNER, st, H);
  for (const [k, dy] of [["lights", 37], ["lights", -91], ["cameras", 50], ["cameras", -200], ["lights", 400]]) {
    const st1 = drag(OWNER, st, H, k, dy, L0), L1 = layout(OWNER, st1, H);
    assert.ok(sum(L1) + L1.free === AVAIL, [k, dy, L1]);
    // the handle went where the pointer went, as far as there was room
    const at = L => L.top[k];
    const a = OWNER[OWNER.findIndex(s => s.k === k) - 1];
    if (Math.abs(at(L1) - at(L0)) !== Math.abs(dy)) assert.ok(L1.h[a.k] === a.content || Object.values(L1.h).some(h => h === ROW) || L1.h.cameras === rows(18), [k, dy, L1]);
    // and it stays put: the next drag starts from exactly what is drawn
    assert.deepEqual(layout(OWNER, drag(OWNER, st1, H, k, 0, L1), H).h, L1.h);
  }
});

test("folding the last section: its title goes to the bottom, Lights hugs its rows, Objects takes the room", () => {
  const st = auto(), L0 = layout(OWNER, st, H), st1 = fold(OWNER, st, H, "cameras"), L1 = layout(OWNER, st1, H);
  assert.equal(st1.cameras.shut, true);
  assert.equal(L1.h.cameras, 0); assert.equal(L1.top.cameras, H - 30, "the folded title sits at the panel's bottom");
  assert.equal(L1.h.lights, rows(3)); assert.equal(L1.h.objects, L0.h.objects + L0.h.cameras);
  assert.deepEqual(L1.handles, { lights: "objects" }, "no handle next to a folded section");
  // unfolded, it comes back at its size
  assert.deepEqual(layout(OWNER, fold(OWNER, st1, H, "cameras"), H).h, L0.h);
});

test("folding after a drag: the dragged section takes the room, unfolding gives the folded one its size back", () => {
  const st = auto(), L0 = layout(OWNER, st, H), st1 = drag(OWNER, st, H, "lights", 60, L0), L1 = layout(OWNER, st1, H);
  const st2 = fold(OWNER, st1, H, "cameras"), L2 = layout(OWNER, st2, H);
  assert.equal(L2.top.cameras, H - 30); assert.equal(L2.h.lights, rows(3)); assert.equal(L2.h.objects, L1.h.objects + L1.h.cameras); assert.equal(L2.free, 0);
  const L3 = layout(OWNER, fold(OWNER, st2, H, "cameras"), H);
  assert.deepEqual(L3.h, L1.h);
});

test("folding a middle section: no handle around it, the titles touch, the open ones share its room", () => {
  const st = auto(), L0 = layout(OWNER, st, H), L1 = layout(OWNER, fold(OWNER, st, H, "lights"), H);
  assert.deepEqual(L1.handles, {});
  assert.equal(L1.top.lights, bottom(L1, "objects")); assert.equal(L1.top.cameras, L1.top.lights + 30);
  assert.equal(L1.h.objects + L1.h.cameras, L0.h.objects + L0.h.cameras + L0.h.lights); assert.equal(bottom(L1, "cameras"), H);
});

test("short sections: the folded last title comes right after the rows above it, the free room stays below", () => {
  const st = auto(), L0 = layout(SMALL, st, H), L1 = layout(SMALL, fold(SMALL, st, H, "cameras"), H);
  assert.deepEqual([L1.h.objects, L1.h.lights], [rows(2), rows(2)]);
  assert.equal(L1.top.cameras, bottom(L1, "lights")); assert.ok(L1.free > 0);
  assert.equal(L0.free, AVAIL - rows(2) * 2 - rows(1));
});

test("a double click on a handle gives the sections it sized back to the content", () => {
  const st = auto(), L0 = layout(OWNER, st, H), st1 = drag(OWNER, st, H, "lights", 60, L0);
  assert.notEqual(st1.objects.size, null);
  const st2 = reset(OWNER, st1, "lights");
  assert.equal(st2.objects.size, null); assert.equal(st2.cameras.size, null);
  assert.deepEqual(layout(OWNER, st2, H).h, L0.h);
});

test("a smaller panel squeezes the sized sections from the bottom, never below one row, never past the panel", () => {
  const st = auto(), L0 = layout(OWNER, st, H), st1 = drag(OWNER, st, H, "lights", 60, L0);
  for (const h of [600, 400, 250, 180]) {
    const L = layout(OWNER, st1, h);
    assert.ok(sum(L) <= Math.max(h - 90, 3 * ROW), [h, L]); assert.ok(Object.values(L.h).every(x => x >= ROW), [h, L]);
  }
});

test("a search opens every section without changing what is kept", () => {
  const st1 = fold(OWNER, auto(), H, "cameras"), L = layout(OWNER, st1, H, { open: true });
  assert.ok(L.h.cameras > 0); assert.equal(st1.cameras.shut, true);
});

// the owner's live panel (2026-10-07, dark, about 1470 px): Objects one row (a model's tree, folded), Lights 3, Cameras 18. It showed one
// row of Lights and every camera with room left below: a small section is never cut while a big one shows all its rows
const LIVE = [{ k: "objects", content: rows(1) }, { k: "lights", content: rows(3) }, { k: "cameras", content: rows(18) }];

test("the owner's live panel, 1470 and 900 px: everything fits, every section shows all its rows", () => {
  for (const h of [1340, 780]) {
    const L = layout(LIVE, auto(), h);
    assert.deepEqual(L.h, { objects: rows(1), lights: rows(3), cameras: rows(18) }, h);
    assert.equal(L.free, h - 90 - rows(1) - rows(3) - rows(18));
  }
});

test("a size cut below the rows never leaves room empty: a short section gets its rows back before the room stays free", () => {
  const st = auto(); st.lights.size = ROW; st.cameras.size = rows(18);   // what the panel kept from before the stack (both sides of a drag)
  const L = layout(LIVE, st, 1340);
  assert.equal(L.h.lights, rows(3)); assert.equal(L.h.cameras, rows(18)); assert.equal(L.h.objects, rows(1));
});

test("too little room: the biggest gives first, the short ones keep their rows, sized or not", () => {
  const st = auto(); st.cameras.size = rows(18);
  for (const s of [st, auto()]) {
    const L = layout(LIVE, s, 400);
    assert.equal(L.h.objects, rows(1)); assert.equal(L.h.lights, rows(3));
    assert.equal(L.h.cameras, 400 - 90 - rows(1) - rows(3)); assert.equal(L.free, 0);
  }
  // two big ones: cut to one level, the short one untouched
  const L = layout(OWNER, (() => { const x = auto(); x.objects.size = 1000; return x; })(), H);
  assert.equal(L.h.lights, rows(3)); assert.ok(Math.abs(L.h.objects - L.h.cameras) <= 1, L.h);
});

// a section's least is what must stay in view (owner 2026-10-07): the active camera, a selected row; with nothing, its title alone, still open
test("a section with nothing active or selected squeezes to its title alone; one with a picked row keeps that row", () => {
  const list = [{ k: "objects", content: rows(87) }, { k: "lights", content: rows(3), min: 0 }, { k: "cameras", content: rows(18), min: ROW }];
  const st = auto(), L0 = layout(list, st, H), L1 = layout(list, drag(list, st, H, "cameras", -5000, L0), H);
  assert.equal(L1.h.lights, 0); assert.equal(L1.shut.lights, false);
  const L2 = layout(list, drag(list, st, H, "lights", 5000, L0), H);
  assert.equal(L2.h.cameras, ROW, "the active camera's row stays"); assert.equal(L2.h.lights, 0);
  // a light picked: its row comes back
  const picked = list.map(s => s.k === "lights" ? { ...s, min: ROW } : s);
  assert.equal(layout(picked, drag(list, st, H, "cameras", -5000, L0), H).h.lights, ROW);
});

test("a tree opened in Objects: the section's rows are measured anew and a drag grows it as far as there is room", () => {
  const shut = [{ k: "objects", content: rows(1) }, { k: "lights", content: rows(3) }, { k: "cameras", content: rows(18) }], tall = 1110;
  const st = auto(), L0 = layout(shut, st, tall);
  assert.equal(L0.h.objects, rows(1));
  const open = [{ k: "objects", content: rows(89) }, ...shut.slice(1)], L1 = layout(open, st, tall);
  assert.equal(L1.h.objects + L1.h.cameras, tall - 90 - rows(3), "the two big ones share what Lights leaves"); assert.ok(Math.abs(L1.h.objects - L1.h.cameras) <= 1);
  const L2 = layout(open, drag(open, st, tall, "lights", 200, L1), tall);
  assert.equal(L2.h.objects, L1.h.objects + 200); assert.equal(L2.h.lights, L1.h.lights); assert.equal(L2.h.cameras, L1.h.cameras - 200);
});

test("squeezed to its least, a section follows what must stay in view: a light picked later shows, none again folds it to its title", () => {
  const list = [{ k: "objects", content: rows(87) }, { k: "lights", content: rows(3), min: 0 }, { k: "cameras", content: rows(18), min: ROW }];
  const st = auto(), L0 = layout(list, st, H), st1 = drag(list, st, H, "cameras", -5000, L0);
  assert.equal(st1.lights.size, 0);
  const picked = list.map(s => s.k === "lights" ? { ...s, min: ROW } : s);
  assert.equal(layout(picked, st1, H).h.lights, ROW); assert.equal(layout(list, st1, H).h.lights, 0);
});
