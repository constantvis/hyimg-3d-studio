// Hyimg 3D, a 3D file of the library onto the board (owner 2026-10-07, project «Field Kit»: STEP files in «modeling C4D», «я не могу
// их смотреть через наш 3D просмотрщик»). The library lists 3D files in their folders like any file; dragged onto the board, alone, with
// pictures or as a whole folder, one becomes a 3D card, not a picture: the board places the card where the drop puts it (HY.placeAs) with
// the file waiting in it (pending), then the card makes its scene and puts the file in (engine.js newScene, putFile); a STEP is converted
// by FreeCAD first and the card says so meanwhile (empty.js). A picture card of a 3D file (hy.py place, a board from a Hyimg without this
// plugin) is turned into such a card in its place. The drop stays one step of the board's undo.
const TYPE = "model3d";
export const is3dPath = p => /\.(glb|gltf|obj|stl|fbx|step|stp|iges|igs)$/i.test(p || "") || /(^|\/)3d\/models\/[^/]+\/model\.json$/.test(p || "");
const stem = p => String(p || "").replace(/^.*\//, "").replace(/\.[^.]+$/, "");

// HY.placeAs: the card of a dropped library file, or null (a picture). lib is the library's entry (kind "model" for a 3D file)
export function placeAs(path, lib) {
  if (lib ? lib.kind !== "model" : !is3dPath(path)) return null;
  return { type: TYPE, ar: 0.8, empty: true, name: (lib && lib.name) || stem(path), pending: { path, ver: (lib && lib.ver) || 0 } };
}

// the scene of a placed card and its file; the board's steps made meanwhile by this are folded into the drop's own
const DOING = new Set();
export function adopt(HY, engine, id) {
  if (DOING.has(id)) return; DOING.add(id);
  engine().then(async m => {
    const it = HY.board.items[id]; if (!it || it.scene || !it.pending) return;
    const what = it.pending; delete it.pending;   // newScene keeps the rest of the card
    const fold = async fn => { const n = HY.steps; await fn(); if (HY.squash && HY.steps === n + 1) HY.squash(n); };
    await fold(() => m.newScene(id));
    await fold(() => m.putFile(id, what));
  }).catch(e => console.error("3D: a dropped file", e)).finally(() => DOING.delete(id));
}

// a picture card whose file is a 3D file becomes a 3D card in the same place, the width kept (quietly: not a step of its own)
export function heal(HY) {
  const bad = Object.entries(HY.board.items).filter(([, it]) => !it.type && it.path && is3dPath(it.path));
  if (!bad.length || HY.dragging) return false;
  const n = HY.steps, b = HY.snap();
  for (const [id, it] of bad) {
    const w = Math.round(it.w || 320);
    HY.board.items[id] = { ...placeAs(it.path, null), name: stem(it.path), x: Math.round(it.x || 0), y: Math.round(it.y || 0), w, h: Math.round(w / 0.8) };
    delete HY.board.items[id].ar;
  }
  HY.commit(b); if (HY.squash) HY.squash(n); HY.render();
  return true;
}
