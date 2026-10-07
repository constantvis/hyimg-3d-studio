// A light of the scene in the 3D studio's right panel (owner 2026-10-07: «было бы шикарно, если можно как-то свет тестировать и
// материалы»): the source, type, power, colour and its temperature in kelvin, how soft it is (an area light's size and shape, a point's or
// a spot's radius, the sun's angle), the spot's cone and blend, the coordinates (folded), Move and Delete. The lights are scene.json's
// (the outliner's Lights): three.js shows them always, Blender when the card's variant says «Свой свет» (variants.js); for a studio's scene
// the panel says so and offers to switch. engine.js hands over what the panel needs (X), so this module draws nothing of its own.

// a black body's colour at k kelvin as linear RGB, its brightest channel 1 (Tanner Helland's fit of the CIE data, then sRGB to linear):
// the three.js preview's light; Blender takes the kelvin itself (light.temperature)
export function kelvin(k) {
  const t = Math.min(40000, Math.max(1000, +k || 6500)) / 100, c = x => Math.min(255, Math.max(0, x));
  const r = t <= 66 ? 255 : c(329.698727446 * Math.pow(t - 60, -0.1332047592));
  const g = t <= 66 ? c(99.4708025861 * Math.log(t) - 161.1195681661) : c(288.1221695283 * Math.pow(t - 60, -0.0755148492));
  const b = t >= 66 ? 255 : t <= 19 ? 0 : c(138.5177312231 * Math.log(t - 10) - 305.0447927307);
  const lin = v => { v /= 255; return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
  const out = [lin(r), lin(g), lin(b)], m = Math.max(...out) || 1;
  return out.map(v => v / m);
}

const SHAPES = [["SQUARE", "Square"], ["RECTANGLE", "Rectangle"], ["DISK", "Disk"], ["ELLIPSE", "Ellipse"]];
const D = Math.PI / 180;
const r1 = x => Math.round(x * 10) / 10;

// X: { t, K, doc, picked, dial, edit, inf, helpers, pick, panel, tree, removeThing, setTool, coordCfg, coordVals, coordSet, sameVals,
//      LIGHT_NAMES, LIGHT_W, hexOf, linOf, studio: a Blender studio's scene, blenderSees(): Blender renders these lights, useOwn() }
export function lightPane(L, X) {
  const { t, K } = X, d = X.doc(), p = X.picked(L);
  const l = d.lights.find(x => x.id === (p.kind === "light" ? p.id : L.lightSel)) || d.lights[0]; L.lightSel = l.id;
  const W = { temp: t("Temperature, K"), byTemp: t("By temperature"), shape: t("Shape"), sizeY: t("Size y, cm"), soft: t("Softness, cm"), angle: t("Angle, °"),
    blend: t("Blend"), own: t("Use these lamps in Blender") };
  const max = l.type === "sun" ? 20 : 400, PW = t("Power, {unit}", { unit: t(l.type === "sun" ? "W/m²" : "W") }), wide = l.shape === "RECTANGLE" || l.shape === "ELLIPSE";
  const cfg = {
    [K.source]: { type: "select", options: d.lights.map(x => ({ value: x.id, label: x.name })), default: l.id },
    [K.type]: { type: "select", options: Object.entries(X.LIGHT_NAMES).map(([value, label]) => ({ value, label: t(label) })), default: l.type },
    [PW]: [Math.min(max, l.power), 0, max, l.type === "sun" ? 0.1 : 1], [K.color]: X.hexOf(l.color || [1, 1, 1]),
    [W.byTemp]: !!l.temp, [W.temp]: [Math.round(l.temp || 5500), 1000, 12000, 50],
  };
  if (l.type === "area") {
    cfg[W.shape] = { type: "select", options: SHAPES.map(([value, label]) => ({ value, label: t(label) })), default: l.shape || "SQUARE" };
    cfg[K.size] = [Math.round((l.size || 0.5) * 100), 1, 300, 1];
    if (wide) cfg[W.sizeY] = [Math.round((l.size_y || l.size || 0.5) * 100), 1, 300, 1];
  }
  if (l.type === "point" || l.type === "spot") cfg[W.soft] = [r1((l.size ?? 0.1) * 100), 0, 100, 0.1];
  if (l.type === "spot") { cfg[K.cone] = [Math.round(l.spot_size || 45), 5, 170, 1]; cfg[W.blend] = [l.spot_blend ?? 0.15, 0, 1, 0.01]; }
  if (l.type === "sun") cfg[W.angle] = [r1((l.angle ?? 0.00918) / D), 0, 45, 0.1];
  cfg[K.visible] = !l.hidden; cfg[K.coords] = X.coordCfg(l); let crd = X.coordVals(l); cfg[K.move] = { type: "action" };
  if (X.studio && !X.blenderSees()) cfg[W.own] = { type: "action" };
  cfg[K.del] = { type: "action" };
  if (X.studio) X.inf(`<p class="hy-hint m3hint">${X.blenderSees() ? t("Blender renders the card with these lamps (the variant's light: own)")
    : t("Blender renders the studio's light now: these lamps are three.js only until the card's variant takes its own light")}</p>`);
  X.dial(l.name, cfg, v => {
    const C = v[K.coords]; if (C && !X.sameVals(C, crd)) { crd = JSON.parse(JSON.stringify(C)); X.coordSet(l, C); return X.edit(() => {}).then(() => { X.helpers(L); L.need(); }); }
    if (v[K.source] !== l.id) { const u = L.view.units.get(v[K.source]); return setTimeout(() => X.pick(L, u && u.obj, true)); }
    if (v[K.type] !== l.type) return X.edit(() => { l.type = v[K.type]; l.power = X.LIGHT_W[l.type]; }).then(() => { X.helpers(L); X.panel(); X.tree(); });
    if (l.type === "area" && (v[W.shape] || "SQUARE") !== (l.shape || "SQUARE")) return X.edit(() => { l.shape = v[W.shape]; }).then(() => X.panel());
    X.edit(() => {
      l.power = v[PW]; l.color = X.linOf(v[K.color]);
      if (v[W.byTemp]) l.temp = v[W.temp]; else delete l.temp;
      if (l.type === "area") { l.size = v[K.size] / 100; l.size_y = (wide ? v[W.sizeY] : v[K.size]) / 100; }
      if (v[W.soft] != null) l.size = v[W.soft] / 100;
      if (v[K.cone]) l.spot_size = v[K.cone];
      if (v[W.blend] != null) l.spot_blend = v[W.blend];
      if (v[W.angle] != null) l.angle = +(v[W.angle] * D).toFixed(5);
      l.hidden = !v[K.visible] || undefined; if (!l.hidden) delete l.hidden;
    });
  }, a => {
    if (a.endsWith(K.del)) return X.removeThing(L, l.id);
    if (a.endsWith(W.own)) { X.useOwn(); return X.panel(); }
    X.pick(L, L.view.units.get(l.id).obj, true); X.setTool(L, "translate");
  });
}
