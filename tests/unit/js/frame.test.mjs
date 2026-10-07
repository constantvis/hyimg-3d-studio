// frame.js: the 3D card's output size (owner 2026-10-07: the frame and the size move from the bar over the card into the Scene panel)
import test from "node:test";
import assert from "node:assert/strict";
import { url } from "./load.mjs";

const { outSize, atLong, keepShape, ratioKey, reshape, PRESETS } = await import(url("frame.js"));
const RATIOS = ["1:1", "4:5", "5:4", "3:4", "4:3", "2:3", "3:2", "9:16", "16:9"];

test("a card made from a picture renders at the picture's own size while it keeps the picture's shape", () => {
  const cam = { render: [2048, 1365] };
  assert.deepEqual(outSize({ w: 600, h: 400 }, cam, {}), [2048, 1365]);
  // reshaped to a square, the picture's long side at the new shape
  assert.deepEqual(outSize({ w: 500, h: 500 }, cam, {}), [2048, 2048]);
});

test("the card's own size wins when it has the card's shape, else its long side at the card's shape", () => {
  assert.deepEqual(outSize({ w: 640, h: 360, res: [1920, 1080] }, { render: [2048, 1365] }, {}), [1920, 1080]);
  assert.deepEqual(outSize({ w: 400, h: 500, res: [1920, 1080] }, null, {}), [1536, 1920]);
});

test("without a size anywhere: the scene's, then 1600 px on the long side", () => {
  assert.deepEqual(outSize({ w: 300, h: 600 }, null, { render: { x: 1000, y: 2000 } }), [1000, 2000]);
  assert.deepEqual(outSize({ w: 900, h: 600 }, null, {}), [1600, 1067]);
});

test("the presets are the long side, the proportions kept when W or H is typed", () => {
  assert.deepEqual(PRESETS, [1080, 2048, 4096]);
  assert.deepEqual(atLong(4096, 16 / 9), [4096, 2304]); assert.deepEqual(atLong(1080, 4 / 5), [864, 1080]);
  assert.deepEqual(keepShape({ w: 800, h: 450 }, "w", 1920), [1920, 1080]); assert.deepEqual(keepShape({ w: 800, h: 450 }, "h", 720), [1280, 720]);
});

test("W × H as a ratio of the board's when it is one, and the card reshaped around its centre", () => {
  assert.equal(ratioKey(1920, 1080, RATIOS), "16:9"); assert.equal(ratioKey(2048, 1365, RATIOS), "2048:1365");
  const r = reshape({ x: 0, y: 0, w: 600, h: 400 }, 1080, 1080);
  assert.equal(r.w, r.h); assert.ok(Math.abs(r.w * r.h - 240000) < 1000); assert.equal(r.x + r.w / 2, 300);
});
