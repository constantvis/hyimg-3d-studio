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
// «Cancel»: closes at once with nothing changed; else asks Hyimg's one question before unsaved work is left (ui/confirm.js hyLeave, owner
// decision 2026-10-10, P4 S-26 A): «Keep editing» (the focus, ↵, Esc), «Discard», «Save» (primary, ⌘↵). Esc no longer comes here: the last
// Esc keeps the work, as the Board segment does (S-27 A)
export function askCancel(L) {
  if (getLive() !== L) return;
  if (!changedSince(L)) return stop(false);
  // the name: Hyimg's crumb step says it (ui/modes.js doc(), engine.js liveDoc); this one is for a Hyimg without it, never the folder (S-07)
  const d = (L.e && L.e.doc) || {};
  const act = keep => () => { if (getLive() === L) stop(keep); }, name = d.name || t("3D scene");
  import("/ui/confirm.js").then(m => m.hyLeave ? m.hyLeave({ name, discard: act(false), save: act(true) })
    : m.hyConfirm({ title: t("Close without saving?"), note: t("The changes made since the last save will be lost."), ok: t("Discard"), cancel: t("Keep editing"), onOk: act(false),
      save: { label: t("Save"), run: act(true) } })).catch(() => {   // a Hyimg without ui/confirm.js
    HY.toast(t("Close without saving?"), "info", { sticky: true, actions: [{ label: t("Discard"), fn: act(false) }, { label: t("Save"), fn: act(true) }] });
  });
}
// the board as it was for the studio's own things (P4 S-01, S-22): the board now, the cards of this scene as at the opening (by id) and the
// cards the session put beside it (L.made: a snapshot, a render, camera cards) gone. What others did meanwhile stays, and so do their steps
export function openingBoard(L) {
  const o = JSON.parse(L.before), b = JSON.parse(HY.snap()), mine = (id, x) => id === L.id || (x && x.type === "model3d" && x.scene === L.path);
  for (const [id, x] of Object.entries(o.items)) if (mine(id, x)) b.items[id] = x;
  for (const id of L.made || []) if (!o.items[id]) delete b.items[id];
  for (const g of Object.values(b.groups || {})) if (Array.isArray(g.members)) g.members = g.members.filter(m => b.items[m] || b.groups[m]);
  return b;
}
export const boardDiffers = (a, b) => JSON.stringify([a.items, a.groups]) !== JSON.stringify([b.items, b.groups]);
// scene.json written by someone else while the studio was open (P4 S-02): an agent, hy.py, another window. The studio's own writes change
// only the card's camera (a Blender preview, «Sync with the scene») or the list's colours (ui), so those do not count
export function outside(L, raw) {
  if (raw == null || raw === L.rawOpen) return false;
  let d, o; try { d = JSON.parse(raw); o = L.rawOpen != null ? JSON.parse(L.rawOpen) : L.sceneOpen; } catch { return true; }
  return ![L.start.item.camera, L.camId(), o.active_camera].filter(Boolean).some(cid => sharedKey(d, cid) === sharedKey(o, cid));
}
const readDisk = path => fetch(fileUrl(path) + `&t=${Date.now()}`, { cache: "no-store" }).then(r => r.ok ? r.text() : null).catch(() => null);
// «Save» writes the scene and waits for it (P4 S-04): refused, the studio stays open, the scene's numbers as they were, one toast. Written
// meanwhile by someone else (S-02), theirs is kept as a version beside it and the toast says where; mine is the scene from now on
export async function writeScene(L) {
  const e = L.e, d = e.doc, path = L.path, disk = await readDisk(path), theirs = outside(L, disk) ? JSON.parse(disk) : null;
  const was = { rev: d.rev, by: d.by, t: d.t }; tidy(d);
  d.rev = Math.max(d.rev || 0, (theirs && theirs.rev) || 0) + 1; d.by = "canvas"; d.t = new Date().toISOString().slice(0, 19).replace("T", " ");
  const raw = JSON.stringify(d, null, 1);
  try {
    const r = await fetch(`/api/file?p=${encodeURIComponent(path)}`, { method: "POST", body: raw });
    if (!r.ok) throw new Error((await r.text().catch(() => "")) || String(r.status));
  } catch (err) {
    for (const k of ["rev", "by", "t"]) { if (was[k] === undefined) delete d[k]; else d[k] = was[k]; }
    HY.toast(t("Scene not saved: {e}", { e: err.message }), "error"); return false;
  }
  e.key = stateKey(d); e.raw = raw;
  if (theirs) {
    putVersion(path, theirs.rev || 0, disk);
    HY.toast(t("The scene had changed on disk meanwhile: that version is kept as {path}", { path: versionOf(path, theirs.rev || 0) }), "info");
  }
  return true;
}
// the list's colours (ui.colors) are how the person finds things, not a change of the scene: written at once, kept by Cancel too (P4 S-20)
export async function writeUi(L) {
  const ui = clone(L.e.doc.ui), put = raw => { const x = JSON.parse(raw); if (ui) x.ui = ui; else delete x.ui; return JSON.stringify(x, null, 1); };
  if (ui) L.sceneOpen.ui = clone(ui); else delete L.sceneOpen.ui;
  if (L.rawOpen != null) L.rawOpen = put(L.rawOpen);
  const disk = await readDisk(L.path); if (disk == null) return;
  const raw = put(disk), r = await fetch(`/api/file?p=${encodeURIComponent(L.path)}`, { method: "POST", body: raw }).catch(() => null);
  if (r && r.ok) { if (L.e.raw === disk) L.e.raw = raw; } else HY.toast(t("Scene not saved: {e}", { e: r ? await r.text() : "offline" }), "error");
}
// «Cancel»: nothing of the session stays (a Blender preview may have written the card's camera into the file: the file as it was), only
// the studio's own things go back (S-01); a scene someone else wrote meanwhile stays as they wrote it (S-02)
export function cancelled(L, lost) {
  const d = L.e.doc; for (const k of Object.keys(d)) delete d[k]; Object.assign(d, clone(L.sceneOpen));
  L.e.view.apply(d).catch(() => {});
  if (HY.squash && L.mark >= 0) HY.squash(L.mark);
  const b = openingBoard(L);
  if (boardDiffers(b, JSON.parse(HY.snap()))) {   // back as it was, saved, no step
    const n = HY.steps, s = HY.snap(); HY.board.items = b.items; HY.board.groups = b.groups; HY.commit(s); HY.squash(n);
  } else HY.render();
  if (L.rawOpen != null) readDisk(L.path).then(now => {
    if (now == null || now === L.rawOpen) return;
    if (outside(L, now)) {   // theirs stays, the scene in memory is theirs
      const x = JSON.parse(now); for (const k of Object.keys(d)) delete d[k]; Object.assign(d, x); L.e.raw = now; L.e.key = stateKey(d);
      return L.e.view.apply(d).then(() => HY.toast(t("The scene changed on disk meanwhile: it stays as written there")));
    }
    return fetch(`/api/file?p=${encodeURIComponent(L.path)}`, { method: "POST", body: L.rawOpen }).then(() => { L.e.raw = L.rawOpen; });
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
