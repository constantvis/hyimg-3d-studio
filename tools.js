// The studio's tools each do their own job (owner 2026-10-07: «неважно, какой инструмент я выбираю, все инструменты крутят почему-то,
// кроме последнего, который двигает объект»). A left drag in the view belongs to the tool, never to the camera:
//   Select (V): a click picks, a drag does nothing. Move (G), Rotate (R), Scale (S): a drag on an object picks it and moves it in the
//   picture's plane (the point under the mouse stays under it), turns it about the vertical as a turntable, scales it (up larger);
//   the gizmo's handles still hold it to one axis. Pull (T): its own drag (engine.js smartMove).
//   With nothing under the pointer and nothing picked, a tool says «Select an object» instead of turning the camera.
// The camera in every tool, one scheme (the Scene panel's footnote): ⌥ + drag, Space + drag or the middle button turn it, the right
// button pans, the wheel zooms.
let THREE = null, HY = null, t = k => k;
export function initTools(c) { THREE = c.THREE; HY = c.HY; t = c.t; }

// h: { hit(ev) the thing under the pointer, ray (the view's raycaster, set by hit), pick(n), unitOf, findAny, readBack }
export function tools(L, cvs, h) {
  const O = L.orbit, M = THREE.MOUSE, on = { signal: L.ac.signal }, cap = { capture: true, signal: L.ac.signal };
  O.mouseButtons = { LEFT: -1, MIDDLE: M.ROTATE, RIGHT: M.PAN };
  let space = false, g = null, said = 0;
  // Hyimg's one rule for keys while typing (its ui/typing.js); the old test when the core is older
  const typing = e => (window.hyTyping ? window.hyTyping(e) : !!(e.target && e.target.closest && e.target.closest("input, textarea, [contenteditable=true]")));
  addEventListener("keydown", e => { if (e.code === "Space" && !typing(e)) space = true; }, cap);
  addEventListener("keyup", e => { if (e.code === "Space") space = false; }, cap);
  addEventListener("blur", () => { space = false; }, on);
  const say = () => { if (performance.now() - said > 1500) { said = performance.now(); HY.toast(t("Select an object")); } };
  const at = (ev, plane) => { h.ray.setFromCamera(ndc(cvs, ev), L.cam); return h.ray.ray.intersectPlane(plane, new THREE.Vector3()); };
  cvs.addEventListener("pointerdown", ev => {   // capture: before the camera's, the gizmo's and the pull's own handlers
    if (ev.button !== 0) return;
    L.turning = ev.altKey || space;
    O.mouseButtons.LEFT = L.turning ? M.ROTATE : -1;   // ⌥ or Space: the camera, whatever the tool
    L.tc.enabled = !L.turning;   // and not the gizmo under the pointer (its centre covers the object)
    // an axis handle of the gizmo under the pointer: the gizmo's drag along it; its centre (it covers the object) is the tool's own drag
    if (L.turning || L.tc.dragging || (L.tc.axis && !CENTRE.includes(L.tc.axis)) || L.tool === "select") return;
    const n = h.hit(ev), u = n && h.unitOf(n), x = u && h.findAny(L.e.doc, u.userData.id);
    const ok = u && !(x && x.locked) && (u.userData.kind === "object" || (u.userData.kind === "light" && L.tool === "translate"));
    if (L.tool === "smart") { if (!ok) say(); return; }   // the pull takes it from here
    if (!ok) { if (!L.sel) say(); return; }
    if (h.unitOf(L.sel) !== u) h.pick(u);
    L.tc.enabled = false;   // this press is the tool's, not the gizmo's centre
    ev.stopPropagation(); cvs.setPointerCapture(ev.pointerId);
    const n0 = L.cam.getWorldDirection(new THREE.Vector3()), w0 = u.getWorldPosition(new THREE.Vector3()), plane = new THREE.Plane().setFromNormalAndCoplanarPoint(n0, w0);
    g = { u, x: ev.clientX, y: ev.clientY, w0, plane, start: at(ev, plane), pos: u.position.clone(), quat: u.quaternion.clone(), scl: u.scale.clone(), moved: false };
  }, cap);
  cvs.addEventListener("pointermove", ev => {
    if (!g) return;
    const dx = ev.clientX - g.x, dy = ev.clientY - g.y; if (!g.moved && Math.hypot(dx, dy) < 3) return; g.moved = true;
    const u = g.u;
    if (L.tool === "translate") {
      const p = at(ev, g.plane); if (!p || !g.start) return;
      const to = g.w0.clone().add(p.sub(g.start)), par = u.parent;   // the same move in the parent's space
      u.position.copy(g.pos).add(par ? par.worldToLocal(to).sub(par.worldToLocal(g.w0.clone())) : to.sub(g.w0));
    } else if (L.tool === "rotate") u.quaternion.copy(g.quat).premultiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), dx / 400 * Math.PI * 2));
    else if (L.tool === "scale") u.scale.copy(g.scl).multiplyScalar(Math.max(0.05, Math.exp(-dy / 200)));
    u.updateMatrixWorld(true); h.readBack(L.view, u.userData.id); L.need();
  }, on);
  const end = () => {
    L.tc.enabled = true; L.turning = false;
    if (!g) return; const was = g; g = null;
    if (was.moved) { L.view.bounds = L.view.meshBounds(); L.view.placeSuns(); L.changed(L.tool === "translate" ? "move" : L.tool, true); L.ui.sync(); }
  };
  cvs.addEventListener("pointerup", end, on); cvs.addEventListener("pointercancel", end, on);
}
const CENTRE = ["XYZ", "XYZE", "E"];
const ndc = (cvs, ev) => { const r = cvs.getBoundingClientRect(); return new THREE.Vector2(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1); };
