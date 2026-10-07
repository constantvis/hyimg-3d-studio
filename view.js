// The card is the truth for its view (owner 2026-10-07: «чтобы board был source of truth, и от него мы плясали уже в Blender»), and the
// studio's «Save» and «Cancel» (owner 2026-10-07: «вместо Done нужно Save, ну и Cancel тоже»). engine.js calls these with the session L.
import { fileUrl, stateKey, tidy } from "./scene.js";
import { studioAngle } from "./blender.js";
import { cardOf, cardOfItem } from "./history.js";
let HY = null, t = k => k, getLive = () => null, stop = () => {};
export function initView(c) { HY = c.HY; t = c.t; getLive = c.live; stop = c.stop; }
const clone = x => x === undefined ? undefined : JSON.parse(JSON.stringify(x));
const noUi = d => { const c = Object.assign({}, d); delete c.ui; return c; };
// a card's view: its camera as it shows it (item.view, the board is the truth for it; owner 2026-10-07). scene.json's camera of the same id
// is only a copy, written when something reads it (Blender right before a render, «Sync with the scene», hy.py camera3d)
const VIEWF = ["name", "loc", "rot", "lens", "sensor", "sensor_h", "fit", "shift", "clip"];
export const viewOf = c => { const v = {}; for (const f of VIEWF) if (c && c[f] !== undefined) v[f] = clone(c[f]); return v; };
// what the cards of a scene share: everything but the bookkeeping and the view of this card's camera (that is the card's own)
export const sharedKey = (d, cid) => {
  const x = noUi(clone(d) || {}); delete x.rev; delete x.by; delete x.t; x.cameras = (x.cameras || []).map(c => c.id === cid ? { id: c.id } : c); return JSON.stringify(x);
};
// a scene's version, kept beside it: <scene dir>/.versions/<rev>.json (a board undo or a board version restores the scene from it)
export const versionOf = (path, rev) => `${path.replace(/[^/]+$/, "")}.versions/${rev}.json`;
export function putVersion(path, rev, raw) { if (raw == null) return; fetch(`/api/file?p=${encodeURIComponent(versionOf(path, rev))}`, { method: "POST", body: raw }).catch(() => {}); }
// anything to lose: the scene, the card or the board not as at the opening
export function changedSince(L) {
  const o = JSON.parse(L.before);
  return stateKey(noUi(tidy(clone(L.e.doc)))) !== stateKey(noUi(tidy(clone(L.sceneOpen)))) || JSON.stringify(cardOf(L)) !== JSON.stringify(cardOfItem(L.start.item))
    || JSON.stringify([o.items, o.groups]) !== JSON.stringify([HY.board.items, HY.board.groups]);
}
// «Cancel» or Esc: closes at once with nothing changed; else asks first, as the image studio does (owner 2026-10-07)
export function askCancel(L) {
  if (getLive() !== L) return;
  if (!changedSince(L)) return stop(false);
  // the image studio's question, as a dialog over everything that only its answer closes (owner 2026-10-07: a note hid behind a newer one)
  const act = keep => () => { if (getLive() === L) stop(keep); };
  import("/ui/confirm.js").then(m => m.hyConfirm({ title: t("Close without saving?"), note: t("The changes made since the last save will be lost."),
    ok: t("Discard"), cancel: t("Cancel"), onOk: act(false) })).catch(() => {   // a Hyimg without ui/confirm.js: the note with its buttons
    HY.toast(t("Close without saving?"), "info", { sticky: true, actions: [{ label: t("Discard"), fn: act(false) }, { label: t("Save"), fn: act(true) }] });
  });
}
// «Cancel»: nothing of the session stays (a Blender preview may have written the card's camera into the file: the file as it was)
export function cancelled(L, lost) {
  const d = L.e.doc; for (const k of Object.keys(d)) delete d[k]; Object.assign(d, clone(L.sceneOpen));
  L.e.view.apply(d).catch(() => {});
  if (HY.squash && L.mark >= 0) {
    const o = JSON.parse(L.before); HY.squash(L.mark);
    if (JSON.stringify([o.items, o.groups]) !== JSON.stringify([HY.board.items, HY.board.groups])) {   // back as it was, saved, no step
      const n = HY.steps, b = HY.snap(); HY.board.items = o.items; HY.board.groups = o.groups; HY.commit(b); HY.squash(n);
    } else HY.render();
  } else HY.render();
  if (L.rawOpen != null) fetch(fileUrl(L.path) + `&t=${Date.now()}`, { cache: "no-store" }).then(r => r.ok ? r.text() : null).then(now => {
    if (now != null && now !== L.rawOpen) return fetch(`/api/file?p=${encodeURIComponent(L.path)}`, { method: "POST", body: L.rawOpen }).then(() => { L.e.raw = L.rawOpen; });
  }).catch(() => {});
  if (lost) HY.toast(t("Closed without saving"));
}
// the camera as in its picture: the studio's angle it came from (studio.angles[id].camera0), a step of the studio, saved with «Save»
export function originalCamera(L, cid) {
  const a = studioAngle(L.e.doc, cid), c = (L.e.doc.cameras || []).find(x => x.id === cid); if (!a || !a.camera0 || !c) return;
  for (const f of ["loc", "rot", "lens", "sensor", "sensor_h", "fit", "shift"]) if (a.camera0[f] !== undefined) c[f] = clone(a.camera0[f]);
  L.view.apply(L.e.doc).then(() => { L.reload(); L.changed("original", true); HY.toast(t("3D: the camera {name} is as in its picture", { name: c.name || cid })); });
}
// the camera's view into scene.json now, that camera only, the rest of the file as it is on disk (what Blender and hy.py read)
export async function syncCamera(L, cid) {
  const c = (L.e.doc.cameras || []).find(x => x.id === cid); if (!c) return;
  try {
    const d = await (await fetch(fileUrl(L.path) + `&t=${Date.now()}`, { cache: "no-store" })).json();
    d.cameras = d.cameras || []; let k = d.cameras.find(x => x.id === cid); if (!k) d.cameras.push(k = { id: cid });
    Object.assign(k, viewOf(c)); d.rev = Math.max(d.rev || 0, L.e.doc.rev || 0) + 1; d.by = "canvas";
    const r = await fetch(`/api/file?p=${encodeURIComponent(L.path)}`, { method: "POST", body: JSON.stringify(d, null, 1) }); if (!r.ok) throw new Error(await r.text());
    HY.toast(t("3D: the scene's camera {name} is this view now", { name: c.name || cid }), "success");
  } catch (e) { HY.toast(t("Scene not saved: {e}", { e: e.message }), "error"); }
}
