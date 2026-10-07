// The 3D card's frame and output size, without a page (owner 2026-10-07: «вот это в рендере я бы убрал, оно мешает, лучше это добавить
// где-то справа в настройках. Потому что там же тоже размер должен быть»). The frame is the card's shape on the board (it.w : it.h, it.lock
// when locked to a ratio); the output size is the picture Blender's «Render» makes, W × H px, always of the card's shape:
//   - the card's own (it.res, set in the Scene panel) when it has the card's shape;
//   - else, for a card that looks through a studio angle's camera (cam.render, the picture's own size, tools/studio_angles.py), that size
//     when it has the card's shape: a card made from a picture renders at the picture's size;
//   - else the card's shape at the long side of the first of these there is, 1600 px by default.
export const PRESETS = [1080, 2048, 4096];   // px on the long side
const shapeOf = it => (it && it.w > 0 && it.h > 0 ? it.w / it.h : 1);
const fits = (r, a) => Array.isArray(r) && r[0] > 0 && r[1] > 0 && Math.abs(r[0] / r[1] - a) <= 0.01 * a;

export function outSize(it, cam, doc) {
  const a = shapeOf(it), own = it && Array.isArray(it.res) ? it.res : null, pic = cam && Array.isArray(cam.render) ? cam.render : null;
  if (fits(own, a)) return own.map(Math.round);
  if (!own && fits(pic, a)) return pic.map(Math.round);
  const r = doc && doc.render, base = own || pic || (r && r.x && r.y ? [r.x, r.y] : [1600, 1600]);
  return atLong(Math.max(...base), a);
}
// the card's shape at a long side of n px
export function atLong(n, a) { n = Math.max(16, Math.round(n)); return a >= 1 ? [n, Math.max(1, Math.round(n / a))] : [Math.max(1, Math.round(n * a)), n]; }
// the long side, or the preset it is
export const longOf = s => Math.max(s[0], s[1]);
// W typed with the proportions kept: H follows the card's shape; H typed: W follows
export function keepShape(it, k, v) { const a = shapeOf(it); v = Math.max(16, Math.round(v)); return k === "w" ? [v, Math.max(1, Math.round(v / a))] : [Math.max(1, Math.round(v * a)), v]; }
// a ratio key for W × H: the board's own when it is one of them (16:9 for 1920 × 1080), else W:H as it is
export function ratioKey(w, h, known) {
  const g = (x, y) => (y ? g(y, x % y) : x), d = g(Math.round(w), Math.round(h)) || 1, k = `${Math.round(w) / d}:${Math.round(h) / d}`;
  return known.includes(k) ? k : `${Math.round(w)}:${Math.round(h)}`;
}
// the card reshaped to W × H: the same centre and about the same area, as the board's frame bar does it (canvas.html setFrame)
export function reshape(it, w, h) {
  const a = w / h, cx = it.x + it.w / 2, cy = it.y + it.h / 2, area = it.w * it.h;
  const W = Math.round(Math.sqrt(area * a)), H = Math.round(W / a);
  return { w: W, h: H, x: Math.round(cx - W / 2), y: Math.round(cy - H / 2) };
}
