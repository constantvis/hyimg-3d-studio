// The look's materials in the 3D studio (owner 2026-10-07: «было бы шикарно, если можно как-то свет тестировать и материалы»): the
// outliner's «Материалы» rows (name, how many parts use it), a material's pane in the right panel with the overrides of the card's variant
// (variants.js), and three.js mirroring them roughly. The names and the parameters are Blender's: the bridge builds the look and reads each
// material's main Principled BSDF (blender/overrides.py report); only what that node has is offered. A parameter driven by nodes in the
// material (the grain of the anodized aluminium) is changed by a factor or a tint, so its texture stays. Until Blender answers, the rows
// come from the three.js scene (the names in scene.glb), and the pane says it is reading.
import * as THREE from "./vendor/three/build/three.module.js";

// key: [label, label when the input is driven by nodes, min, max, step]; colours have no range
const PARAMS = {
  base_color: ["Base color", "Color tint"], metallic: ["Metallic", "Metallic ×", 0, 1, 0.01], roughness: ["Roughness", "Roughness ×", 0, 1, 0.01],
  coat: ["Coat", "Coat ×", 0, 1, 0.01], coat_roughness: ["Coat roughness", "Coat roughness ×", 0, 1, 0.01], specular: ["Specular", "Specular ×", 0, 1, 0.01],
  ior: ["Index of refraction", "Index of refraction ×", 1, 3, 0.01], transmission: ["Transmission", "Transmission ×", 0, 1, 0.01],
  emission_color: ["Emission color", "Emission tint"], emission: ["Emission", "Emission ×", 0, 50, 0.1],
};
const COLOR = new Set(["base_color", "emission_color"]);
const MUL = [0, 3, 0.01];
const hexOf = c => "#" + new THREE.Color(c[0], c[1], c[2]).getHexString();
const linOf = h => { const c = new THREE.Color(h); return [+c.r.toFixed(4), +c.g.toFixed(4), +c.b.toFixed(4)]; };

// the bridge's list for the card's look: [{name, users, parts, principled, params: {key: {value, linked}}, look}]
export async function fetchMaterials(api, L, look) {
  return (await api({ action: "materials", scene: L.path, camera: L.camId(), look })).list || [];
}

// the materials the three.js scene shows, by name: how many meshes wear each
function shown(L) {
  const by = new Map();
  for (const u of L.view.units.values()) if (u.kind === "object") u.obj.traverse(m => {
    const b = m.userData.base; if (m.isMesh && b && b.mat.name) by.set(b.mat.name, (by.get(b.mat.name) || 0) + 1);
  });
  return by;
}

// the rows: Blender's list when it came, else three.js's names; a dot in the material's colour, the count of parts, a mark when overridden
export function materialRows(L, S, { query, sel, over, t, esc }) {
  const list = S.report ? S.report.map(m => ({ name: m.name, n: m.users, color: m.params.base_color && m.params.base_color.value }))
    : [...shown(L)].sort((a, b) => a[0].localeCompare(b[0])).map(([name, n]) => ({ name, n }));
  return list.filter(m => !query || m.name.toLowerCase().includes(query)).map(m => {
    const on = sel && sel.kind === "material" && sel.name === m.name, ov = over && over[m.name];
    const hex = m.color && hexOf(m.color);   // the app's swatch (ui/hy), shown only
    const dot = `<hy-swatch ${hex ? `color="${hex}" style="--hy-sw:${hex}"` : "none"} tabindex="-1" aria-hidden="true"></hy-swatch>`;
    const tip = esc(m.name) + (ov ? " · " + esc(t("changed in this variant")) : "");
    return `<div class="row${on ? " sel" : ""}${ov ? " m3ov" : ""}" data-mat="${esc(m.name)}" title="${tip}"><span class="chev"></span>${dot}`
      + `<span class="nm">${esc(m.name)}${ov ? `<i class="hy-dot" title="${esc(t("changed in this variant"))}"></i>` : ""}</span>`   // round 15's change dot (ui/hy)
      + `<span class="cnt">${m.n}</span></div>`;
  });
}

// the pane of one material: its parameters as Blender has them, or the variant's override of them
export function materialPane(L, S, { t, esc, current, ensure, changed, load }) {
  const name = L.lmSel.name, m = (S.report || []).find(x => x.name === name), ov = ((current() || {}).materials || {})[name] || {};
  L.ih("model", name, t("material"));
  if (!m) {
    L.inf(`<p class="hy-hint m3hint">${S.error ? esc(t("Blender: {e}", { e: S.error })) : t("Blender is reading the look's materials…")}</p>`);
    if (!S.loading && !S.error) load();
    return L.dial(name, { [t("Reset material")]: { type: "action" } }, () => {});
  }
  const parts = m.parts.slice(0, 6).join(", ") + (m.users > 6 ? ` … (${m.users})` : "");
  if (!m.principled) {
    L.inf(`<p class="hy-hint m3hint">${t("This material has no Principled BSDF: it cannot be changed here")}</p><div class="real">${esc(parts)}</div>`);
    return L.dial(name, { [t("Reset material")]: { type: "action" } }, () => {});
  }
  const driven = Object.keys(m.params).filter(k => m.params[k].linked);
  L.inf(`<div class="real">${esc(t("{n} parts: {list}", { n: m.users, list: parts }))}<br>${esc(t("in Blender: {look}", { look: m.look }))}</div>`
    + (driven.length ? `<p class="hy-hint m3hint">${t("Where nodes drive a parameter (a grain, a texture) it takes a factor or a tint, the texture stays")}</p>` : ""));
  const label = k => t(PARAMS[k][m.params[k].linked ? 1 : 0]), cfg = {}, reset = t("Reset material");
  for (const k of Object.keys(PARAMS)) {
    const p = m.params[k]; if (!p) continue;
    const o = ov[k];
    if (COLOR.has(k)) cfg[label(k)] = p.linked ? hexOf((o && o.tint) || [1, 1, 1]) : hexOf(Array.isArray(o) ? o : p.value);
    else { const [, , lo, hi, st] = PARAMS[k]; cfg[label(k)] = p.linked ? [o && o.mul != null ? o.mul : 1, ...MUL] : [o != null && typeof o === "number" ? o : p.value, lo, hi, st]; }
  }
  cfg[reset] = { type: "action" };
  // «Сбросить материал» looks like every reset of the studio: grey while the variant leaves this material as it is
  const resetLook = () => requestAnimationFrame(() => {
    const b = [...L.ui.root.querySelectorAll(".dk .dialkit-button")].find(x => x.textContent.trim() === reset); if (!b) return;
    const on = !!(((current() || {}).materials || {})[name]);
    b.classList.add("hy-reset"); b.disabled = !on; b.title = on ? t("Back to the look's own material") : t("Nothing changed");
  });
  L.dial(name, cfg, v => {
    const next = {};
    for (const k of Object.keys(PARAMS)) {
      const p = m.params[k]; if (!p || v[label(k)] === undefined) continue;
      const x = v[label(k)];
      if (COLOR.has(k)) { if (p.linked) { if (x.toLowerCase() !== "#ffffff") next[k] = { tint: linOf(x) }; } else if (x.toLowerCase() !== hexOf(p.value)) next[k] = linOf(x); }
      else if (p.linked) { if (Math.abs(x - 1) > 1e-4) next[k] = { mul: +x.toFixed(4) }; }
      else if (Math.abs(x - p.value) > 1e-4) next[k] = +x.toFixed(4);
    }
    const cur = current(); if (JSON.stringify(next) === JSON.stringify(((cur || {}).materials || {})[name] || {})) return;
    const w = ensure(t("materials")); w.materials = w.materials || {};
    if (Object.keys(next).length) w.materials[name] = next; else delete w.materials[name];
    if (!Object.keys(w.materials).length) delete w.materials;
    changed("material").then(resetLook);
  }, a => {
    if (!a.endsWith(reset)) return;
    const w = current(); if (!w || !w.materials || !w.materials[name]) return;
    delete w.materials[name]; if (!Object.keys(w.materials).length) delete w.materials;
    changed("material").then(() => L.ui.panel());
  });
  resetLook();

}

// three.js after each apply of the scene: the variant's colour, metalness and roughness on the meshes of each material (an approximation;
// Blender's frame is the truth). SceneView.paint has just put every mesh back to its file's values
export function mirror(view, mats) {
  if (!mats) return;
  for (const u of view.units.values()) if (u.kind === "object") u.obj.traverse(m => {
    const b = m.userData.base; if (!m.isMesh || !b) return;
    const o = mats[b.mat.name], mt = b.mat; if (!o) return;
    const c = o.base_color;
    if (c && mt.color) { if (Array.isArray(c)) mt.color.setRGB(c[0], c[1], c[2]); else if (c.tint) mt.color.multiply(new THREE.Color(c.tint[0], c.tint[1], c.tint[2])); }
    for (const [k, f] of [["metallic", "metalness"], ["roughness", "roughness"]]) {
      const x = o[k]; if (x == null || !(f in mt)) continue;
      mt[f] = Math.min(1, Math.max(0, typeof x === "number" ? x : mt[f] * x.mul));
    }
  });
}
