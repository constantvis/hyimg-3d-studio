// The pick seen whole (owner 2026-10-07: «если я выбрал 3D объект, он должен оставаться без обводки ... объект должен быть полностью
// виден, как будто он сверху наложен на текущий рендер, и его не закрывает что-то другое ... То есть закрывает, но прозрачным таким
// ghost-эффектом»). No outline and no tint: where the picked object shows in the frame it is exactly the render; where something stands
// in front of it, the object is laid over that something at part strength, in its own materials and light, so the thing in front reads
// as half see-through. What is under the mouse gets the same, fainter, and a faint lift where it shows, so a hover is never a pick.
//
// Per frame, after the editor's render (engine.js L.redraw), for the hovered set and then the picked set:
//  1. the set alone, with its own materials, lights and the frame's shadow maps (not redrawn), into a half-float target of the view's size
//     with its own depth: the object as if nothing else were there, its inner parts hidden by its outer ones;
//  2. the set twice more into the view, colour off, depth tested against the render's depth: farther than it marks the stencil «hidden»,
//     less or equal (pulled 4 units forward) marks «shown», the parts of it the render already has;
//  3. a full-view quad of the target where the stencil is hidden and not shown, at the set's strength, tone-mapped as the render is
//     (premultiplied, so it also lies right on a see-through card and on the empty canvas over Blender's frame);
//  4. for a hover, a white of a few percent where it is shown.
// The gizmo the render left out is drawn last, on top. The cost is two depth-only draws of the set's meshes and a few full-view quads,
// and one draw of the set into the target while some of it is hidden (probe() below); nothing when nothing is picked or hovered.
import * as THREE from "./vendor/three/build/three.module.js";

const HIDDEN = 1, SHOWN = 2;   // the stencil's bits, below
const KEEP = { stencilFail: THREE.KeepStencilOp, stencilZFail: THREE.KeepStencilOp, stencilZPass: THREE.KeepStencilOp };

export const GHOST = { pick: 0.55, hover: 0.28, lift: 0.08 };   // the share of the hidden part laid over what is in front; the hover's lift

let G = null;
function kit() {
  if (G) return G;
  const rt = new THREE.WebGLRenderTarget(1, 1, { type: THREE.HalfFloatType, samples: 4 });
  const vert = "varying vec2 vUv; void main(){ vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }";
  const over = (frag, ref, mask, toneMapped, uniforms) => new THREE.ShaderMaterial({
    uniforms, vertexShader: vert, fragmentShader: frag, toneMapped, transparent: true, depthTest: false, depthWrite: false,
    blending: THREE.CustomBlending, blendSrc: THREE.OneFactor, blendDst: THREE.OneMinusSrcAlphaFactor,
    blendSrcAlpha: THREE.OneFactor, blendDstAlpha: THREE.OneMinusSrcAlphaFactor,
    stencilWrite: true, stencilRef: ref, stencilFuncMask: mask, stencilFunc: THREE.EqualStencilFunc, stencilWriteMask: 0, ...KEEP,
  });
  // the set's colour is premultiplied in the target (a clear of 0, edges resolved over it): back to straight colour for the tone curve
  const ghost = over(`uniform sampler2D tex; uniform float k; varying vec2 vUv;
    void main(){
      vec4 c = texture2D(tex, vUv); if (c.a < 0.004) discard;
      gl_FragColor = vec4(c.rgb / c.a, 1.0);
      #include <tonemapping_fragment>
      #include <colorspace_fragment>
      float a = min(c.a, 1.0) * k; gl_FragColor = vec4(gl_FragColor.rgb * a, a); }`,
  HIDDEN, 3, true, { tex: { value: rt.texture }, k: { value: 0.5 } });
  const lift = over("uniform float k; void main(){ gl_FragColor = vec4(vec3(k), k); }", SHOWN, SHOWN, false, { k: { value: 0.08 } });
  const probe = Object.assign(over("void main(){ gl_FragColor = vec4(0.0); }", HIDDEN, 3, false, {}), { colorWrite: false });
  // the stencil's two bits: HIDDEN where some of the set is behind what the render has there (itself or another thing), SHOWN where some
  // of it is the nearest; hidden and not shown is where another thing stands in front of it. Samples the set does not cover get neither,
  // so its antialiased edge against the world or a thing behind it gets no fringe
  const mask = (side, bit) => new THREE.MeshBasicMaterial({ side, colorWrite: false, depthWrite: false,
    depthFunc: bit === SHOWN ? THREE.LessEqualDepth : THREE.GreaterDepth, polygonOffset: bit === SHOWN, polygonOffsetFactor: -1, polygonOffsetUnits: -4,
    stencilWrite: true, stencilRef: bit, stencilWriteMask: bit, stencilFunc: THREE.AlwaysStencilFunc, ...KEEP, stencilZPass: THREE.ReplaceStencilOp });
  const quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), ghost); quad.frustumCulled = false;
  const qs = new THREE.Scene(); qs.add(quad);
  const sides = [THREE.FrontSide, THREE.BackSide, THREE.DoubleSide], masks = [HIDDEN, SHOWN].map(bit => sides.map(side => mask(side, bit)));
  G = { rt, ghost, lift, probe, quad, qs, qc: new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1), masks, seen: new Map() };
  return G;
}
const drawable = o => o.isMesh || o.isLine || o.isPoints || o.isSprite;

// the ghost's shaders built before the first hover: the scene's materials as they draw into the target (a target draws them without the
// tone curve, which three.js builds as other programs), the quads and the depth-only masks. Built in the background when the editor
// opens, so the first hover does not wait for them (WebKit, 2026-10-07: the first hover's frames took long enough to coarsen the view)
export function warmGhost(r, view, cam) {
  const g = kit(), tone = r.toneMapping, at = r.getRenderTarget(), jobs = [];
  try {
    // the scene's own materials compiled without waiting on them: compileAsync polls each material's program and threw in a timer when the
    // scene's materials were rebuilt meanwhile (Save, Cancel, a History step, the next card's still: «reading 'isReady'», 2026-10-07)
    r.setRenderTarget(g.rt); r.compile(view.scene, cam); r.setRenderTarget(at);
    r.toneMapping = view.tone;
    for (const m of [g.ghost, g.lift, g.probe]) { g.quad.material = m; jobs.push(r.compileAsync(g.qs, g.qc)); }
    const ms = new THREE.Scene(); g.masks.flat().forEach(m => ms.add(new THREE.Mesh(new THREE.BoxGeometry(), m))); jobs.push(r.compileAsync(ms, cam));
  } catch (err) { /* an older three.js without compileAsync: the shaders build on the first hover */ }
  finally { r.toneMapping = tone; r.setRenderTarget(at); g.quad.material = g.ghost; }
  return Promise.all(jobs).catch(() => {});
}

// Is any of the set hidden? An occlusion query over the stencil's «hidden, not shown» answers a frame or two later. While the last answer
// for this set is «no» (the usual case: the whole model picked, nothing in front of it) the set is not drawn into the target at all, which
// on the owner's Vase (1.15 million triangles) is most of the ghost's cost; a «yes» after a frame that left it out asks for another frame
function probe(r, g, key, need) {
  const gl = r.getContext(), st = g.seen.get(key) || { hidden: null }; g.seen.set(key, st);
  if (!gl.createQuery || st.q) return st;   // WebGL 1 (none), or the last question is not answered yet
  if (g.seen.size > 32) for (const k of [...g.seen.keys()].slice(0, 16)) if (k !== key) g.seen.delete(k);
  st.q = gl.createQuery(); gl.beginQuery(gl.ANY_SAMPLES_PASSED_CONSERVATIVE, st.q);
  g.quad.material = g.probe; r.render(g.qs, g.qc); gl.endQuery(gl.ANY_SAMPLES_PASSED_CONSERVATIVE);
  const ask = () => {
    if (!st.q) return;
    if (gl.isContextLost() || !gl.getQueryParameter(st.q, gl.QUERY_RESULT_AVAILABLE)) { requestAnimationFrame(ask); return; }
    const hidden = !!gl.getQueryParameter(st.q, gl.QUERY_RESULT); gl.deleteQuery(st.q); st.q = null;
    const missed = hidden && st.skipped; st.hidden = hidden; st.skipped = false;
    if (missed && need) need();
  };
  requestAnimationFrame(ask);
  return st;
}

// r: the renderer, its canvas holding the frame just drawn (its depth too); view: the SceneView (scene, tone, exposure); cam: the view's
// camera; sets: [{meshes, k, lift}] drawn in order; top: the gizmo to draw over everything, or null; need: asks for another frame
export function drawGhost(r, view, cam, W, H, sets, top, need) {
  const g = kit(), sc = view.scene;
  if (g.rt.width !== W || g.rt.height !== H) g.rt.setSize(W, H);
  const keep = { bg: sc.background, tone: r.toneMapping, exp: r.toneMappingExposure, shadows: r.shadowMap.autoUpdate, auto: r.autoClear,
    clear: r.getClearColor(new THREE.Color()), alpha: r.getClearAlpha() };
  const all = []; sc.traverseVisible(o => { if (drawable(o)) all.push(o); });
  sc.background = null; r.shadowMap.autoUpdate = false; r.autoClear = false;
  const only = (list, fn) => {   // the scene with only these drawn
    const on = new Set(list), off = all.filter(o => !on.has(o)); off.forEach(o => { o.visible = false; });
    try { fn(); } finally { off.forEach(o => { o.visible = true; }); }
  };
  try {
    for (const s of sets) {
      if (!s.meshes.length) continue;
      let st = null;
      only(s.meshes, () => {
        r.clear(false, false, true);
        const mats = s.meshes.map(m => m.material), side = mats.map(m => (Array.isArray(m) ? m[0] : m).side);
        const at = side.map(v => v === THREE.BackSide ? 1 : v === THREE.DoubleSide ? 2 : 0);
        try { for (const set of g.masks) { s.meshes.forEach((m, i) => { m.material = set[at[i]]; }); r.render(sc, cam); } }
        finally { s.meshes.forEach((m, i) => { m.material = mats[i]; }); }
        st = probe(r, g, `${s.k}|${s.meshes.length}|${s.meshes[0].uuid}|${s.meshes[s.meshes.length - 1].uuid}`, need);
        st.skipped = st.hidden === false;
        if (!st.skipped) { r.setRenderTarget(g.rt); r.setClearColor(0x000000, 0); r.clear(true, true, false); r.render(sc, cam); r.setRenderTarget(null); }
      });
      r.toneMapping = view.tone; r.toneMappingExposure = view.exposure;
      if (!st.skipped) { g.ghost.uniforms.k.value = s.k; g.quad.material = g.ghost; r.render(g.qs, g.qc); }
      if (s.lift) { g.lift.uniforms.k.value = s.lift; g.quad.material = g.lift; r.render(g.qs, g.qc); }
      r.toneMapping = keep.tone; r.toneMappingExposure = keep.exp;
    }
    if (top) {   // the gizmo turns its own handles on and off as it draws: all of them stay in, the rest of the scene out
      const was = top.visible, mine = []; top.visible = true; top.traverse(o => { if (drawable(o)) mine.push(o); });
      try { only(mine, () => r.render(sc, cam)); } finally { top.visible = was; }
    }
  } finally {
    sc.background = keep.bg; r.shadowMap.autoUpdate = keep.shadows; r.autoClear = keep.auto; r.toneMapping = keep.tone; r.toneMappingExposure = keep.exp;
    r.setClearColor(keep.clear, keep.alpha); r.setRenderTarget(null);
  }
}

// ---- the editor's frame with its highlight (engine.js L.redraw): the Scene panel's «Selection highlight» is the ghost (the default) or the
// pink outline of before 2026-10-07 (the pick outlined, what is under the mouse filled)
const OUTLINE = [1, 0, 0, 1];   // the outline's hover fill, hover outline, pick fill, pick outline
// what the view shows as picked: the pick, or several when a selection of many sets L.multi with the pick first (engine.js liveSelect)
const picks = L => (L.multi && L.sel && L.multi[0] === L.sel ? L.multi : [L.sel]).filter(Boolean);
const meshesOf = (L, n) => {   // a node's meshes, and a light's icon with it
  const out = []; if (!n) return out;
  n.traverse(m => { if (m.isMesh && m.visible !== false) out.push(m); });
  if (n.userData.kind === "light" && L.icons.get(n.userData.id)) out.push(L.icons.get(n.userData.id));
  return out;
};
// the ghost's sets: what is under the mouse first (fainter, lifted where it shows), then the pick over it; null when there is neither
function ghostSets(L) {
  const ps = picks(L), sel = [...new Set(ps.flatMap(n => meshesOf(L, n)))], hov = L.hov && !ps.includes(L.hov) ? meshesOf(L, L.hov) : [], out = [];
  if (hov.length) out.push({ meshes: hov, k: GHOST.hover, lift: GHOST.lift });
  if (sel.length) out.push({ meshes: sel, k: GHOST.pick, lift: 0 });
  return out.length ? out : null;
}

// L: the editor (view, cam, tc, hov, sel, hl, bimg); bg: the card's background; bare: the interface is hidden (⌘.), the picture alone.
// Over Blender's frame (blender.js L.bimg) the canvas lies on top of it, empty but for the ghost of the pick and the gizmo, drawn with the
// scene's depth: the same camera, so they stand where Blender's picture has them
export function drawFrame(r, L, W, H, bg, bare) {
  const view = L.view, gz = L.tc.getHelper(), gv = gz.visible, hv = view.helpers.visible, bi = L.bimg;
  const over = !!(bi && !bi.hidden && bi.complete && bi.naturalWidth);
  if (over !== !!L.over) { L.over = over; r.domElement.style.zIndex = over ? "2" : ""; }
  const sets = bare || L.hl === "outline" ? null : ghostSets(L);
  if (bare || sets) gz.visible = false;
  if (bare) view.helpers.visible = false;
  try {
    if (over && !sets) { r.setSize(W, H, false); r.setClearColor(0x000000, 0); r.clear(); }
    else view.render(L.cam, W, H, "beauty", bg);
    if (over && sets) { r.setClearColor(0x000000, 0); r.clear(true, false, false); }
    if (sets) drawGhost(r, view, L.cam, W, H, sets, gv && !bare ? gz : null, L.need); else if (!bare) drawMarks(r, L, W, H);
  } finally { gz.visible = gv; view.helpers.visible = hv; }
}

let marks = null;
function markLayer() {   // a mask of the pick (red) and the hover (green), drawn over the view as pink fill or outline
  if (marks) return marks;
  const rt = new THREE.WebGLRenderTarget(1, 1), q = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), new THREE.ShaderMaterial({
    transparent: true, depthTest: false, depthWrite: false, toneMapped: false,
    uniforms: { mask: { value: rt.texture }, px: { value: new THREE.Vector2() }, col: { value: new THREE.Vector3(1, 0.31, 0.64) },
      mode: { value: new THREE.Vector4() } },
    vertexShader: "varying vec2 vUv; void main(){ vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }",
    fragmentShader: `uniform sampler2D mask; uniform vec2 px; uniform vec3 col; uniform vec4 mode; varying vec2 vUv;
      void main(){
        vec4 m = texture2D(mask, vUv); float sn = 0.0, hn = 0.0;
        for (int x = -2; x <= 2; x++) for (int y = -2; y <= 2; y++) {
          vec4 n = texture2D(mask, vUv + vec2(float(x), float(y)) * px); sn = max(sn, n.r); hn = max(hn, n.g); }
        float a = max(max(m.g * mode.x * 0.42, m.r * mode.z * 0.38), max(hn * (1.0 - m.g) * mode.y * 0.7, sn * (1.0 - m.r) * mode.w));
        gl_FragColor = vec4(col, a); }`,
  }));
  const sc = new THREE.Scene(); sc.add(q);
  const mm = c => Object.assign(new THREE.MeshBasicMaterial({ color: c }), { toneMapped: false });
  marks = { rt, q, sc, cam: new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1), sel: mm(0xff0000), hov: mm(0x00ff00), both: mm(0xffff00), none: mm(0x000000) };
  return marks;
}
function drawMarks(r, L, W, H) {
  const ps = picks(L), sel = ps.flatMap(n => meshesOf(L, n)), hov = ps.includes(L.hov) ? [] : meshesOf(L, L.hov);
  if (!sel.length && !hov.length) return;
  const M = markLayer(), helper = L.tc.getHelper(), was = helper.visible, keep = [], sc = L.view.scene;
  helper.visible = false;
  sc.traverse(m => {
    if (!m.isMesh) return; const s = sel.includes(m), h = hov.includes(m);
    keep.push([m, m.material]); m.material = s && h ? M.both : s ? M.sel : h ? M.hov : M.none;
  });
  const tone = r.toneMapping, bg = sc.background; r.toneMapping = THREE.NoToneMapping; sc.background = null;
  if (M.rt.width !== W || M.rt.height !== H) M.rt.setSize(W, H);
  r.setRenderTarget(M.rt); r.setClearColor(0x000000, 1); r.clear(); r.render(sc, L.cam); r.setRenderTarget(null);
  keep.forEach(([m, mt]) => { m.material = mt; }); helper.visible = was; r.toneMapping = tone; sc.background = bg; r.setClearColor(0x000000, 0);
  M.q.material.uniforms.px.value.set(1 / W, 1 / H); M.q.material.uniforms.mode.value.fromArray(OUTLINE);
  r.autoClear = false; r.render(M.sc, M.cam); r.autoClear = true;
}
