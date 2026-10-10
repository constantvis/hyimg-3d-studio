// 3D Studio's dock on Hyimg's one dock (hyimg review/ui/dock.js, ui/palette.js; owner 2026-10-10 on round 18, r18-dock.html, ★ yes):
//   «+» Add | Select, Move, Rotate, Scale, Pull, Annotation | Undo, Redo, Reset | the view % | Snapshot, Actions | the switch of Studios
// every icon button 36 × 34 with no plate (it had round plates, 34 and 38 wide). «+» opens Hyimg's dock list (hyDock.menu), the same one
// as the board's «+». Undo and Redo name their step on a plate over them under the pointer and for 2 s after ⌘Z or ⇧⌘Z (hyDock.steps,
// the names of the History tab, history.js). Actions (⌘K, Hyimg's palette as in Image Studio) lists what the dock and the keys do.
// Snapshot (P) renders the view, the masks and the depth as pictures beside the card (engine.js shoot); it is in Actions too.
//   const D = studioDock(L, o)   D.done(dir)   D.toggle()   D.destroy()
//   o: { t, ico, bar, menu, fillModels, ADD, MENU_ICON, addThing, setTool, shoot, resetAll, undo(dir), save, cancel }
const TOOLS = [["select", "Select", "V"], ["translate", "Move", "G"], ["rotate", "Rotate", "R"], ["scale", "Scale", "S"], ["smart", "Pull", "T"]];
export function studioDock(L, o) {
  const D = window.hyDock, bar = o.bar, t = o.t; if (!D || !bar) return null;
  const q = s => bar.querySelector(s);
  const AM = D.menu(q("[data-plus]"), o.menu, { fill: () => { o.fillModels().then(() => { if (AM.isOpen) AM.place(); }); }, pick: b => b.dataset.add && o.addThing(L, b.dataset.add) });
  // the step Undo would take back is the one that made the state now; Redo's the next one in the list
  const name = dir => { const h = L.hist[dir === "undo" ? L.hi : L.hi + 1]; return h && (dir === "redo" || L.hi > 0) ? h.label : ""; };
  const S = D.steps({ undo: q("[data-a=undo]"), redo: q("[data-a=redo]"), name });
  const items = () => {
    const g = { add: t("Add"), tools: t("Tools"), edit: t("Edit"), view: t("View"), studio: "3D Studio" };
    return [
      ...o.ADD.map(([k, w]) => ({ label: t(w), group: g.add, icon: o.ico(o.MENU_ICON[k] || "light"), fn: () => o.addThing(L, k) })),
      ...TOOLS.map(([k, w, key]) => ({ label: t(w), group: g.tools, icon: o.ico(k), keys: [key], fn: () => o.setTool(L, k) })),
      { label: t("Annotation"), group: g.tools, icon: o.ico("comment"), keys: ["C"], fn: () => { const b = q("[data-ann]"); if (b) b.click(); } },
      { label: t("Undo"), group: g.edit, icon: o.ico("undo"), keys: ["⌘", "Z"], hint: name("undo"), dis: L.hi < 1, fn: () => o.undo(-1) },
      { label: t("Redo"), group: g.edit, icon: o.ico("redo"), keys: ["⇧", "⌘", "Z"], hint: name("redo"), dis: L.hi >= L.hist.length - 1, fn: () => o.undo(1) },
      { label: t("Reset all"), group: g.edit, icon: o.ico("reset"), fn: () => o.resetAll(L) },
      { label: t("Snapshot"), group: g.view, icon: o.ico("shot"), keys: ["P"], hint: t("view, masks and depth beside the card"), fn: () => o.shoot(L) },
      { label: t("Fit the card between the panels"), group: g.view, icon: o.ico("fit"), fn: () => { const f = document.getElementById("bfit"); if (f) f.click(); } },
      { label: t("Save"), group: g.studio, icon: o.ico("check"), keys: ["⌘", "↵"], fn: o.save },
      { label: t("Cancel"), group: g.studio, icon: o.ico("close"), fn: o.cancel },
    ];
  };
  const P = window.hyPalette ? window.hyPalette({ id: "3d", items, primary: o.save, anchor: () => { const d = document.getElementById("dock"); return d && d.getBoundingClientRect(); } }) : null;
  const slot = q("[data-dk=acts]"); if (slot && P) slot.replaceWith(D.acts(() => P.toggle()));
  return {
    done: dir => S.done(dir),
    toggle: () => P && P.toggle(),
    get open() { return !!(P && P.isOpen); },
    destroy() { AM.close(); if (P) P.destroy(); },
  };
}
