// Hyimg 3D: a 3D scene as a card on the canvas (owner 2026-10-03). This module is the light part: it registers the card and shows its
// still view at once, as a file of the project, so a page with 3D cards opens like a page of pictures (owner: «they must show at once,
// like ordinary pictures, we do not load three.js»), also for someone who opens the project from a link or, later, from the cloud.
// A card's still is <scene folder>/.posters/<card>-<view>.jpg (png when the card's background lets the board through); <view> is a
// short hash of the camera and the background, so a card that changes them gets a new file and the old one is removed by the server:
// one file per card, rewritten in place, nothing piles up. One /api/stat call gives the times of all scenes and stills on the board;
// a still older than its scene, or missing, is drawn again by the engine (engine.js: three.js, the scene, the editor), which loads
// only then, or for the editor. Thousands of cards cost one small request at load and one every few seconds after.
//
// The scene lives in the library as 3d/scenes/<name>/scene.json (format in scene.js); the card on the board is
// {type: "model3d", scene, camera, bg, x, y, w, h}. Older cards {model, cam, colors} are drawn by the engine.
import { translator } from "./lang.js";   // English or Russian, as the board is set (owner 2026-10-06)
import { placeAs, adopt, heal } from "./place.js";   // a 3D file of the library dropped on the board is a 3D card (2026-10-07)
const TYPE = "model3d";
const INBOX = "3d/scenes/inbox.json";
const CUBE = hyIcon("scene3d", 18, 1.8);   // a 3D scene (ui/icons.js)
const fileUrl = p => `/file?p=${encodeURIComponent(p)}`;
const PLUGIN = (new URL(import.meta.url).pathname.match(/\/plugins\/([^/]+)\//) || [])[1] || "3d";

let HY, E = null, loading = null, t = k => k;
const engine = () => loading || (loading = import("./engine.js").then(m => { m.init(HY, { poster, posted }); E = m; return m; }));
// the studio for a card: a double click, Enter, the bar's «3D Studio», the dock's 3D segment all come here
const studio = id => engine().then(m => m.goLive(id));
const oneCard = () => { const ids = [...HY.sel].filter(i => HY.board.items[i]); return ids.length === 1 && HY.board.items[ids[0]].type === TYPE ? ids[0] : null; };
const DOCS = new Map();   // scene path -> doc, for the card's description; read only when a scene changed

// the times of files, many in one request: the scenes and stills on the board, inbox.json
const TIMES = new Map();
let ask = null;
function times(paths) {
  if (!ask) { ask = { paths: new Set(), wait: null }; ask.wait = new Promise(r => setTimeout(r, 30)).then(async () => {
    const list = [...ask.paths]; ask = null;
    const r = await fetch("/api/stat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ paths: list }) });
    const got = r.ok ? await r.json() : {}; for (const p of list) TIMES.set(p, got[p] ?? null); return got;
  }); }
  paths.forEach(p => ask.paths.add(p)); return ask.wait;
}

const see = bg => !!bg && (bg.transparent || (bg.opacity ?? 100) < 100);
const fnv = t => { let h = 0x811c9dc5; for (let i = 0; i < t.length; i++) { h ^= t.charCodeAt(i); h = Math.imul(h, 0x01000193) >>> 0; } return h.toString(16).padStart(8, "0"); };
// the name stills had before the frame was in it (2026-10-04): shown while the new one is drawn, so no card waits for three.js empty
const oldStillOf = (it, id) => { const ext = see(it.bg) ? "png" : "jpg"; return { path: `${it.scene.replace(/[^/]+$/, "")}.posters/${id}-${fnv(JSON.stringify([it.camera || "", it.bg || null]))}.${ext}`, ext }; };
function stillOf(it, id) {
  const ext = see(it.bg) ? "png" : "jpg", dir = it.scene.replace(/[^/]+$/, "");
  // the frame is in the name too: a card turned from 4:5 to 16:9 is another picture (and an undo finds that it has to draw again)
  // its own view too (item.view): a board undo of the view shows the still of that view
  const k = [it.camera || "", it.bg || null, Math.round(it.w / it.h * 100) / 100, ...(it.empty ? ["empty"] : []), ...(it.view ? [it.view] : [])];
  return { path: `${dir}.posters/${id}-${fnv(JSON.stringify(k))}.${ext}`, ext };   // an empty card has a still of its own: the base scene (engine.js backdrop)
}
// the engine wrote a still: its time is known, the card shows the file
function posted(path, mtime) { TIMES.set(path, mtime); }

// The card is the truth for its view (owner 2026-10-07: «чтобы board был source of truth, и от него мы плясали уже в Blender»): item.view is
// its camera as it shows it (engine.js viewOf, the same fields), the board's undo, history and copy carry it; scene.json's camera of that id
// is a copy written only when something reads it. A card from before has none: it takes its scene camera's view once, quietly (saved
// with the board, no step), and nothing is written to the scene
const VIEWF = ["name", "loc", "rot", "lens", "sensor", "sensor_h", "fit", "shift", "clip"];
const viewOf = c => { const v = {}; for (const f of VIEWF) if (c && c[f] !== undefined) v[f] = JSON.parse(JSON.stringify(c[f])); return v; };
const FILL = new Set(); let fillT = 0;
function fillView(id, it) {
  if (it.view || !it.scene || it.empty || FILL.has(id) || !HY.squash) return;
  FILL.add(id); clearTimeout(fillT);
  fillT = setTimeout(async () => {
    const ids = [...FILL].filter(i => HY.board.items[i] && !HY.board.items[i].view); FILL.clear();
    await Promise.all([...new Set(ids.map(i => HY.board.items[i].scene))].map(p => docFor(p)));
    const n = HY.steps, b = HY.snap(); let any = false;
    for (const i of ids) {
      const x = HY.board.items[i], d = x && DOCS.get(x.scene) && DOCS.get(x.scene).doc, c = d && (d.cameras || []).find(k => k.id === (x.camera || d.active_camera));
      if (x && !x.view && c) { x.view = viewOf(c); if (!x.camera) x.camera = c.id; any = true; }
    }
    if (any && !HY.dragging) { HY.commit(b); HY.squash(n); }   // saved with the board, not a step to undo
  }, 300);
}
// The scene follows the board back (owner 2026-10-07: a board version «restored» a wrong view, the cameras lived in scene.json only):
// every card of a scene says which version of it it shows (sceneRev, set by the studio's «Save», which keeps the versions in
// <scene dir>/.versions/<rev>.json). After the board's ⌘Z or ⇧⌘Z, for a card whose sceneRev changed, and after a board version is
// restored, for every card, the scene is put back from that version when it is not the one on disk (every card of that scene shows it)
let PRE = null;
const revs = () => new Map(Object.entries(HY.board.items).filter(([, x]) => x.type === TYPE && x.scene).map(([k, x]) => [k, x.sceneRev]));
async function sceneBack(why) {
  const before = PRE; PRE = null; const want = new Map();
  for (const [k, x] of Object.entries(HY.board.items))
    if (x.type === TYPE && x.scene && x.sceneRev != null && (why === "version" || !before || before.get(k) !== x.sceneRev)) want.set(x.scene, x.sceneRev);
  for (const [path, rev] of want) {
    try {
      const cur = await (await fetch(fileUrl(path) + `&t=${Date.now()}`, { cache: "no-store" })).json(); if ((cur.rev || 0) === rev) continue;
      const v = await fetch(fileUrl(`${path.replace(/[^/]+$/, "")}.versions/${rev}.json`) + `&t=${Date.now()}`, { cache: "no-store" }); if (!v.ok) continue;
      // the version's content as the newest write (its rev past the file's), so every reader takes it
      const doc = await v.json(); doc.rev = Math.max(cur.rev || 0, doc.rev || 0) + 1; doc.by = "board"; doc.from_rev = rev;
      const w = await fetch(`/api/file?p=${encodeURIComponent(path)}`, { method: "POST", body: JSON.stringify(doc, null, 1) }); if (!w.ok) continue;
      DOCS.delete(path); if (E) await E.refreshScene(path);
      for (const el of cardsOf(path)) poster(el, HY.board.items[el.dataset.id], el.dataset.id);
      HY.toast(t("3D: the scene {path} is back as it was with the board", { path }));
    } catch (e) { console.error("3D scene back", e); }
  }
}

// the card's «3D» mark in the board's pill (.mk.mk-kind): the cube icon, then the text, which engine.js writes into .b3 («3D ⏸», «3D ⚠»)
const mark = () => `<span class="mk mk-br mk-kind" title="${t("3D scene: double-click to edit")}"><b class="kp">${window.hyMarkIcon ? window.hyMarkIcon("scene3d") : ""}</b><span class="kw"><span><span class="kt b3">3D</span></span></span></span>`;
// the card at rest: the still from the project when it is not older than the scene; else the engine draws it again and writes it
function poster(el, it, id, doc, force) {
  if (E && E.isLive(id)) return;
  let img = el.querySelector("img.m3");
  if (img && img.src && HY.dragging) return;   // while its frame is dragged the old still stretches; the new one is drawn on release
  if (!img) { el.innerHTML = `<img class="m3" alt="" decoding="async">${mark()}`; img = el.querySelector("img.m3"); img.addEventListener("load", () => el.classList.add("lo")); }
  el.classList.toggle("see", see(it.bg));
  if (!it.scene) return void engine().then(m => m.renderPoster(el, it, id));   // an older card: only the engine knows how it looks
  const st = stillOf(it, id), old = oldStillOf(it, id), show = (t, s = st) => { const u = s.ext === "png" ? fileUrl(s.path) + `&v=${t}` : `/thumb?p=${encodeURIComponent(s.path)}&s=640&v=${t}`; if (img._u !== u) { img._u = u; img.src = u; } el.querySelector(".b3").textContent = "3D"; };
  // a card shown in Blender (blender.js, owner 2026-10-06): at rest it shows its last Blender frame, a file of its own in .posters
  if (it.render && it.blenderStill) return void times([it.blenderStill]).then(() => {
    if (TIMES.get(it.blenderStill)) { const u = fileUrl(it.blenderStill) + `&v=${TIMES.get(it.blenderStill)}`; if (img._u !== u) { img._u = u; img.src = u; } el.querySelector(".b3").textContent = it.render === "EEVEE" ? "3D · EEVEE" : "3D · Cycles"; }
    else poster(el, Object.assign({}, it, { render: null }), id, doc, force);
  });
  if (force) return void engine().then(m => m.renderPoster(el, it, id, st));   // the editor just changed it: the engine has the newest scene
  times([it.scene, st.path, old.path]).then(() => {
    const ts = TIMES.get(it.scene), tp = TIMES.get(st.path), to = TIMES.get(old.path);
    if (tp) show(tp); else if (to) show(to, old);   // even an old still is better than an empty card while the new one is drawn
    if (!tp || (ts && ts > tp)) engine().then(m => m.renderPoster(el, it, id, st));
  });
}
// The card is a picture for the board's looks (owner 2026-10-06: «why can't I make a 3D object more transparent, like a picture ... and lay
// a colour grade over it? In the end it is a picture, even when it is rendered»): the board fades the whole card, and the colour grade
// (Hyimg-frames) is laid over the picture the card shows now, whatever made it, and again each time it changes («if the render finished,
// my grade is always laid over it»). surface(): in the editor Blender's frame while it is shown, else the live three.js view; at rest
// the still (three.js or the last Blender frame). Each new picture tells the board (HY.drawn): a still or a Blender frame loaded, the
// live view drawn (engine.js), another element now showing (Blender's frame shown or hidden, the editor opened or closed)
function surface(el) {
  if (el.classList.contains("plg-live")) {
    const b = el.querySelector(":scope > img.m3bimg");
    if (b && !b.hidden && b.complete && b.naturalWidth) return b;
    const c = el.querySelector(":scope > canvas.m3live"); if (c) return c;
  }
  return el.querySelector(":scope > img.m3");
}
function watchLook(el) {
  el._look = true; if (!HY.drawn) return;   // a Hyimg older than 2026-10-06: no looks on plugin cards
  const tell = () => { el._sf = surface(el); HY.drawn(el); };
  el.addEventListener("load", e => { if (e.target.tagName === "IMG") tell(); }, true);
  new MutationObserver(() => { if (surface(el) !== el._sf) tell(); }).observe(el, { childList: true, subtree: true, attributes: true, attributeFilter: ["hidden", "class"] });
}
const cardsOf = path => [...document.querySelectorAll(`.plg[data-type=${TYPE}]`)].filter(el => { const it = HY.board.items[el.dataset.id]; return it && it.scene === path; });

// an agent changed a scene file (an export from Blender): its cards follow; a request in inbox.json puts a card per camera
let inboxSeen = null, inboxT = undefined;
async function poll() {
  if (document.visibilityState !== "visible") return;
  heal(HY);   // a picture card of a 3D file (hy.py place) becomes a 3D card
  const paths = [...new Set(Object.values(HY.board.items).filter(it => it.type === TYPE && it.scene).map(it => it.scene))];
  const before = new Map(paths.map(p => [p, TIMES.get(p)])), was = TIMES.get(INBOX);
  await times([...paths, INBOX]);
  for (const p of paths) {
    if (before.get(p) === undefined || before.get(p) === TIMES.get(p)) continue;   // first look, or the file did not change
    if (E && E.livePath() === p) continue;   // the editor is writing it: its cards are drawn again once, on «Готово»
    try {
      if (E) await E.refreshScene(p);   // the engine takes it too (it keeps its own while an edit waits to be saved)
      DOCS.delete(p);
      for (const el of cardsOf(p)) poster(el, HY.board.items[el.dataset.id], el.dataset.id);
    } catch (e) { /* the file is being written */ }
  }
  const t = TIMES.get(INBOX); if (inboxT === undefined) { inboxT = t; return; }   // what was there before this page opened is old
  if (!t || t === was) return;
  try {
    const req = await (await fetch(fileUrl(INBOX) + `&t=${t}`, { cache: "no-store" })).json();
    if (!req.id || req.id === inboxSeen) return; inboxSeen = req.id;
    (await engine()).placeCardsFor(req.scene, req.cameras || []);
  } catch (e) { /* being written */ }
}
async function docFor(path) {
  if (!DOCS.has(path)) { const slot = { doc: null }; DOCS.set(path, slot); slot.doc = await fetch(fileUrl(path) + `&t=${Date.now()}`, { cache: "no-store" }).then(r => r.json()).catch(() => null); }
  const slot = DOCS.get(path); return slot ? slot.doc : null;   // a scene changed meanwhile (poll, the board's undo) dropped its slot
}

export function register(hy) {
  HY = hy; t = translator(hy);
  const st = document.createElement("style"); st.textContent = `
    .plg[data-type=${TYPE}] img.m3 { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; pointer-events: none; }
    /* the «3D» mark is the board's kind mark (owner 2026-10-06: «why is it not consistent with the marks on pictures and videos»): the
       board's .mk pill (review/canvas.html, the marks' one system), a cube before «3D» as ▶ before a video's time; its place, size, fold
       and the way it leaves and comes are the board's, which sizes it from the card on screen as every other mark (cull, mkApply) */
    /* no outline round a live card (owner 2026-10-08: «обводка эта дурацкая вокруг»): Hyimg lifts the card a mode edits with a shadow;
       the rule was global, it drew round the frames plugin's HTML live view and Dev mode's page too */
    .plg-live { overflow: visible !important; background: transparent !important; }
    .plg-live, .plg-live *, .m3ui .row { cursor: default !important; }   /* owner 2026-10-03: the mouse stays an arrow, no hand */
    .plg-live img.m3, .plg-live .mk { visibility: hidden; }   /* the still picture under the live view would show through a see-through background */
    .plg-live canvas.m3live { position: absolute; inset: 0; width: 100%; height: 100%; display: block; touch-action: none; }
    /* grey while its still loads, like a picture (owner 2026-10-04); a see-through card turns clear once the still is there */
    .plg[data-type=${TYPE}] { background: var(--raise); } .plg[data-type=${TYPE}].lo.see { background: transparent; }
    .plg[data-type=${TYPE}]:has(img.m3[src^="data:image/png"]) { background: transparent; }
    body.m3edit #info { display: none !important; }
    /* Blender's frame over the live view and its line of state (blender.js) */
    .plg-live img.m3bimg { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; pointer-events: none; z-index: 1; }
    .plg-live .m3bst { position: absolute; left: calc(8px / var(--z)); bottom: calc(8px / var(--z)); z-index: 3; max-width: calc(100% - 16px / var(--z)); overflow: hidden; text-overflow: ellipsis;
      padding: calc(3px / var(--z)) calc(9px / var(--z)); border-radius: 999px; background: rgba(20,20,22,.72); color: #fff; font: 500 calc(11px / var(--z)) var(--sans); white-space: nowrap; pointer-events: none; }
    /* the reset among the tools: a neutral round icon like them (owner 2026-10-06: red is only for deleting) */
    .bar .plgdock button:is(.m3reset, .m3ic) { width: 38px; padding: 0 !important; justify-content: center; } .m3t button:is(.m3reset, .m3ic) { width: 30px; }
    :root[data-ui="studio"] .bar .plgdock button:is(.m3reset, .m3ic) { width: 32px; }
    /* Blender's controls in the board's selection bar over the card (.tidy.plgedit, canvas.html): its 44 px, glass, shadow and clamping;
       the app's .seg, a select with the app's chevron, «Render» the one dark button, every control 34 px as the bar's buttons */
    .m3bplate { display: contents; }
    .tidy.plgedit { gap: 4px; }
    .tidy.plgedit svg { width: 14px; height: 14px; flex: none; }
    .tidy.plgedit .seg { flex: none; height: 34px; box-sizing: border-box; }
    .tidy.plgedit .seg > button { height: 28px; padding: 0 10px 0 8px; gap: 5px; font: 500 13px var(--sans); color: var(--sub); }
    .tidy.plgedit .seg > button:hover { background: transparent; color: var(--ink); } .tidy.plgedit .seg > button[aria-pressed=true] { color: var(--ink); }
    .tidy.plgedit .m3lk { position: relative; flex: none; height: 34px; box-sizing: border-box; display: inline-flex; align-items: center; gap: 4px; padding: 0 10px 0 14px; border-radius: 999px;
      background: var(--raise); color: var(--ink); font: 500 13px var(--sans); cursor: pointer; transition: background .2s cubic-bezier(.32,.72,0,1); }
    .tidy.plgedit .m3lk:hover { background: color-mix(in srgb, var(--raise) 80%, var(--ink) 8%); }
    .tidy.plgedit .m3lk .hy-chev { width: 12px; height: 12px; color: var(--sub); transform: rotate(90deg); }
    .tidy.plgedit .m3lk select { position: absolute; inset: 0; width: 100%; height: 100%; opacity: 0; cursor: pointer; font: inherit; border: 0; }
    .tidy.plgedit :is(button, select):focus, .tidy.plgedit :is(button, select):focus-visible { outline: none; box-shadow: none; }
    /* Render, the bar's primary, in 3D Studio's pink with white words, its progress the band over it as before (owner 2026-10-09: «Она должна
       быть такого цвета, в каком режиме мы сейчас находимся») */
    .tidy.plgedit .m3rend { position: relative; overflow: hidden; flex: none; min-width: 84px; padding: 0 16px; justify-content: center; background: var(--pink);
      color: var(--hy-on-accent, #fff); font-weight: 600; font-variant-numeric: tabular-nums; }
    .tidy.plgedit .m3rend:hover { background: color-mix(in srgb, var(--pink) 88%, var(--panel)); }
    .tidy.plgedit .m3rend .pr { position: absolute; inset: 0 auto 0 0; width: calc(var(--p, 0) * 100%); background: color-mix(in srgb, var(--panel) 26%, transparent); transition: width .5s cubic-bezier(.32,.72,0,1); }
    .tidy.plgedit .m3rend .l { position: relative; } .tidy.plgedit .m3rend.busy { cursor: default; }
    .tidy.plgedit .m3stop { width: 34px; padding: 0; justify-content: center; color: var(--sub); } .tidy.plgedit .m3stop:hover { color: var(--ink); }
    .tidy.plgedit [hidden] { display: none !important; }
    :root[data-shape=pro] .tidy.plgedit :is(.m3lk, .m3rend, .m3stop) { border-radius: 8px; }
    .plg[data-type=${TYPE}] .h3 { position: absolute; inset: 0; display: grid; place-content: center; gap: calc(10px / var(--z)); padding: calc(16px / var(--z)); text-align: center;
      background: rgba(20,20,22,.78); color: #fff; font: 500 calc(13px / var(--z)) var(--sans); line-height: 1.45; z-index: 3; }
    .plg[data-type=${TYPE}] .h3 button { height: calc(30px / var(--z)); padding: 0 calc(14px / var(--z)); border: 0; border-radius: calc(8px / var(--z)); background: #fff; color: #111; font: 600 calc(12px / var(--z)) var(--sans); cursor: pointer; }
    /* the editor follows the interface's look and theme (owner 2026-10-04): «Студия» dark or light, its own palette; «Классика» the page's palette,
       Geist and glass panels like the rest of the classic canvas */
    /* one radius for every control of a row (owner 2026-10-06: «одни круглые другие квадратные»): the app's --hy-row-r (ui/look.css), the
       studio look's --st-r; the sliders, DialKit's rows, the search and the tool buttons all read --m3-r */
    .m3ui { --m3-r: var(--hy-row-r, 999px); } :root[data-ui="studio"] .m3ui { --m3-r: var(--st-r, 8px); }
    .m3ui .hy-slider { --hy-sl-r: var(--m3-r); }
    .m3ui { --row-ink: color-mix(in srgb, var(--ink) 82%, var(--sub)); --tint: color-mix(in srgb, var(--ink) 3%, transparent);
      color: var(--ink); font: 400 12px/1.35 -apple-system, "SF Pro Text", system-ui, sans-serif; position: static; -webkit-font-smoothing: antialiased; }
    :root[data-ui="studio"] .m3ui, :root[data-ui="studio"][data-theme="dark"] .m3ui { --pink-ink: #1c0a13; --card: #1b1c1f; --raise: #25262a; --line: #2c2d32; --guide: #34353b; --ink: #ececef; --sub: #9a9ba3; --dim: #64656d; }
    :root[data-ui="studio"][data-theme="light"] .m3ui { --pink-ink: #fff; --card: #ffffff; --raise: #f0f0f2; --line: #e3e3e7; --guide: #d9d9de; --ink: #1b1c1f; --sub: #6b6c73; --dim: #9a9ba3; }
    /* 3D Studio wears its colour, its pink (--pink), in both looks (owner 2026-10-09, «конечно» to «3D Studio и Dev Studio пока остаются
       синими. Дать им их цвета?»; Image Studio's purple is the precedent, hyimg-frames 6e04f1a): every chosen, checked or primary thing of
       the studio (the picked row, a checked box, a chosen option, a value's fill, the tool in hand and Save in the dock) and the 3D segment
       of the dock's switch (HY.mode color). It is on the board's root because the dock reads it; blue stays the board's selection */
    :root { --pink: #ff4fa3; } :root[data-theme="light"] { --pink: #e5307f; }
    .m3ui { --sel: var(--pink); --hy-sel: var(--pink); --hy-acc: var(--pink); --hy-tint-bg: color-mix(in srgb, var(--pink) 16%, transparent); --hy-tint-ink: var(--pink);
      --hy-trow-on: color-mix(in srgb, var(--pink) 14%, transparent); --hy-trow-ring: inset 0 0 0 1px color-mix(in srgb, var(--pink) 55%, transparent);
      --hy-val: color-mix(in srgb, var(--pink) 30%, transparent); --hy-val-drag: color-mix(in srgb, var(--pink) 44%, transparent);
      --hy-val-on: color-mix(in srgb, var(--pink) 30%, var(--hy-well)); --hy-val-ink: color-mix(in srgb, var(--pink) 14%, var(--ink)); }
    #dock .plgdock.m3t button:is(.on, .pri) { background: var(--pink) !important; color: var(--hy-on-accent, #fff) !important; }   /* over canvas.html's ink */
    .m3ui .dialkit-root .dialkit-toggle[data-checked="true"] .dialkit-toggle-track { background: var(--pink); }
    .m3ui .dialkit-root .dialkit-toggle[data-checked="true"] .dialkit-toggle-thumb { background: var(--hy-on-accent, #fff); }
    /* the panels are the media library's panel (owner 2026-10-06: «why so much inconsistencies in ui»; review/v2.html body.cv-on main): the
       paper, a hairline, 18 px corners, no glass; its rows are the library's rows, 28 px, 13 px type */
    :root:not([data-ui="studio"]) .m3ui { --pink-ink: #fff; --card: var(--paper, var(--panel)); --guide: var(--line); --dim: var(--muted); font: 400 13px/1.4 var(--sans); }
    :root:not([data-ui="studio"]) .m3p:not(.hy-blk) { border-radius: 18px; }
    /* the layer list and the inspector are blocks of the app, round 12 «A · Line» (owner 2026-10-09: «реализуй уже A Line версию на весь
       интерфейс»): Hyimg ui/hy/block.css draws their surface, the inspector's tabs, the sections' heads and the wells of their controls */
    .m3l.hy-blk, .m3r.hy-blk { --card: var(--hy-blk); --m3-r: var(--hy-ctl-r); }
    :root:not([data-ui="studio"]) .m3r .dk .dialkit-root { --dial-row-height: var(--hy-ctl-h); --dial-radius: var(--m3-r); --dial-surface: var(--hy-well);
      --dial-surface-hover: var(--hy-well-hov); --dial-surface-active: var(--hy-val); --dial-surface-subtle: var(--hy-pline);
      --dial-text-root: var(--ink); --dial-text-section: var(--sub); --dial-text-label: var(--sub); --dial-text-primary: var(--ink); --dial-text-secondary: var(--sub); --dial-text-tertiary: var(--muted);
      --dial-border: var(--line); --dial-dropdown-bg: var(--panel); font-family: var(--sans); }
    :root:not([data-ui="studio"]) .m3r .dk .dialkit-root :is(.dialkit-slider-label, .dialkit-toggle-label, .dialkit-button, .dialkit-select-label, .dialkit-text-label, .dialkit-color-label, .dialkit-slider-value) { font-size: 12px; }
    /* a group of the inspector is a section of the app (.hy-sh): its chevron before its words, 12 px in --sub */
    .m3r.hy-blk .dk .dialkit-folder:not(.dialkit-folder-root) > .dialkit-folder-header > .dialkit-folder-header-top { flex-direction: row-reverse; justify-content: flex-end; gap: 6px; }
    .m3r.hy-blk .dk .dialkit-folder-title { font: 500 12px var(--sans); letter-spacing: 0; color: var(--sub); }
    .m3r.hy-blk .dk .dialkit-folder-icon { width: 16px; height: 16px; padding: 2.5px; opacity: 1; color: var(--muted); transition: rotate .25s var(--hy-ease); }
    .m3r.hy-blk .dk .dialkit-folder[data-open="true"] > .dialkit-folder-header .dialkit-folder-icon { rotate: 180deg; }   /* open ⌄, shut › as the app's sections */
    .m3r.hy-blk .dk .dialkit-folder[data-open="false"] > .dialkit-folder-header .dialkit-folder-icon { rotate: -90deg; }
    .m3r.hy-blk .dk .dialkit-root .dialkit-button { background: var(--hy-wbtn); }   /* a button lies on the block, not in a well (.hy-wbtn) */
    .m3r.hy-blk .dk .dialkit-root .dialkit-button:hover { background: var(--hy-wbtn-hov); }
    .m3ui .ic { width: 15px; height: 15px; flex: none; }
    .m3p { position: fixed; z-index: 60; background: var(--card); border: 1px solid var(--line); border-radius: 12px; box-shadow: 0 16px 50px rgba(0,0,0,.35); }
    .m3p.hy-blk { border-color: var(--hy-pline); border-radius: var(--hy-blk-r); box-shadow: var(--plate-sh); }   /* a block (ui/hy/block.css), its depth by «Тени» */
    /* ⌘. hides them with the board's interface (data-hyui: the board's hyUiOut / hyUiZoom around the window's centre, back with hyUiBack);
       the slide sends each toward its own edge */
    .m3l { --hx: -16px; } .m3r { --hx: 18px; } .m3x { --hy: 16px; } .m3title { --hy: -16px; }
    :root[data-ui="studio"][data-theme="light"] .m3p { box-shadow: 0 14px 40px rgba(20,20,30,.12); }
    .m3t { top: var(--t); left: calc(var(--l) + 252px); right: calc(var(--r) + 292px); width: fit-content; margin-inline: auto; display: flex; align-items: center; gap: 2px; padding: 5px; }
    .m3t button { position: relative; width: 30px; height: 30px; border: 0; border-radius: var(--m3-r); background: none; color: var(--sub); display: grid; place-items: center; }
    /* the tools are circles, as the frame editor's (owner 2026-10-06: «почему-то они не круглые в 3d studio сами эти элементы»): in the
       board's dock a tool button is as wide as the dock's buttons are tall, the dock's 999 px makes it round, «pro» squares it to 8 px */
    #dock .plgdock :is(button[data-tool], button[data-plus]) { width: 34px !important; }
    :root[data-ui="studio"] #dock .plgdock :is(button[data-tool], button[data-plus]) { width: var(--st-h, 30px) !important; }
    .m3t button:hover { background: var(--raise); color: var(--ink); } .m3t button.on { background: var(--pink); color: var(--pink-ink); }
    /* the key letters are the button's own <kbd> child: the app's rule (ui/keyhints.js, owner 2026-10-05) shows them only while ⌘ is held, over the button's right end, never widening it */
    .m3t button > kbd { display: inline-grid; place-items: center; min-width: 16px; height: 16px; padding: 0 4px; border-radius: 5px; font: 600 10px/1 var(--sans, system-ui); background: var(--raise); color: var(--sub); }
    .m3t .plus { background: var(--raise); color: var(--ink); } .m3t .sep { width: 1px; height: 18px; background: var(--line); margin: 0 5px; }
    .m3t .wide { width: auto; padding: 0 12px; display: flex; gap: 6px; color: var(--ink); background: var(--raise); margin-left: 4px; } .m3t .pri { background: var(--pink); color: var(--hy-on-accent, #fff); }
    .m3t .tip { position: relative; }
    .m3menu { position: absolute; top: 40px; left: -5px; z-index: 70; min-width: 180px; padding: 5px; background: var(--card); border: 1px solid var(--line); border-radius: 10px; box-shadow: var(--hy-sh-pop, 0 16px 40px rgba(0,0,0,.45)); display: grid; gap: 1px; }
    .m3menu[hidden] { display: none; } .m3menu button { border: 0; border-radius: 6px; background: none; cursor: default; font: inherit; } .m3menu button:hover { background: var(--raise); color: var(--ink); } .m3menu button { width: 100%; height: 28px; display: flex; gap: 8px; justify-content: flex-start; padding: 0 8px; color: var(--row-ink); }
    .m3l { left: var(--l); top: var(--t); bottom: var(--b); width: 240px; display: flex; flex-direction: column; overflow: hidden; padding: 8px 10px 6px; box-sizing: border-box; }
    /* the panels glide with the library when it opens or closes (owner 2026-10-06: «it should move in unison»): --inset-ms is how long the library's own move takes
       (the app's page sends it with --inset), the curve is the library's; a window resize sends 0 and nothing glides */
    .m3l, .m3x { transition: left var(--inset-ms, 0ms) cubic-bezier(.32, .72, 0, 1), right var(--inset-ms, 0ms) cubic-bezier(.32, .72, 0, 1); }
    .m3t:not(.plgdock) { transition: left var(--inset-ms, 0ms) cubic-bezier(.32, .72, 0, 1), right var(--inset-ms, 0ms) cubic-bezier(.32, .72, 0, 1); }
    /* the search is the library's «Find folder» (ui/look.css .hy-search: the same field, magnifier, height, radius and ground) */
    .m3l .lhd { display: flex; flex: none; padding-bottom: 6px; } .m3l .lhd .hy-search > input { color: var(--ink); }
    .m3l .opts { display: flex; justify-content: flex-end; padding: 0 4px 2px; color: var(--dim); font-size: 11px; flex: none; } .m3l .opts label { display: flex; gap: 5px; align-items: center; } .m3l .opts input { margin: 0; accent-color: var(--sel, var(--pink)); }
    /* the sections Objects, Lights, Cameras (engine.js tree): a title that folds (the app's chevron, turned with the app's curve), the rows,
       the app's splitter between two (ui/split.js). One stack (sections.js): engine.js sets each section's rows in px, a fold glides along
       the app's curve (.tr.glide), a drag does not */
    .m3l .tr { flex: 1; min-height: 0; display: flex; flex-direction: column; overflow: hidden; } .m3l .tr > .none { color: var(--dim); padding: 14px 8px; }
    .m3l .ms { display: flex; flex-direction: column; flex: none; } .m3l .ms[hidden], .m3l .msp[hidden] { display: none; }
    .m3l .msh { user-select: none; cursor: default; }   /* a section's head of the app (.hy-sh, ui/hy/block.css) */
    .m3l .msh:hover { color: var(--ink); }
    .m3l .mtg .hy-chev, .m3l .chev .hy-chev { transition: transform .32s cubic-bezier(.32,.72,0,1); }
    .m3l .ms:not(.shut) .mtg .hy-chev, .m3l .row:not(.closed) .chev .hy-chev { transform: rotate(90deg); }
    .m3l .msb { flex: none; min-height: 0; overflow: hidden auto; scrollbar-width: none; } .m3l .tr.glide .msb { transition: height .32s cubic-bezier(.32,.72,0,1); }
    .m3l .msb::-webkit-scrollbar { display: none; } .m3l .ms.shut .msb { overflow: hidden; }
    :root.hy-splitting .m3l .msb { transition: none; }
    .m3l .msi { padding-bottom: 4px; } .m3l .msb { position: relative; }   /* a row's offsetTop is its place in the section (a squeezed one scrolls to its picked row) */
    .m3l .kids { overflow: hidden; }   /* a tree's rows gliding open or shut (engine.js wrapKids) */
    /* the splitter takes no room (owner 2026-10-06: «странное расстояние ... для этого хендлера»): its 9 px sit over the line between two
       sections, the negative margins give them back, the hairline is drawn in its middle; next to a folded section only the hairline stays */
    .m3l .msp.hy-split { height: 9px; margin: -4px 0 -5px; z-index: 2; }   /* the app's Line (ui/split.js): a hairline, the accent under the pointer */
    .m3l .hy-split.off { opacity: 1; }   /* the hairline stays between sections, the accent only where it can move */
    /* the rows are the library's folder rows (review/v2.html .frow, ui/look.css --hy-trow-*): 28 px, 8 px corners, grey hover; the picked one
       is the app's selected row, the image editor's selected layer: a fill and a line in the selection colour (owner 2026-10-07) */
    .m3l .row { display: flex; align-items: center; height: var(--hy-trow-h, 28px); padding: 0 4px 0 4px; border-radius: var(--hy-trow-r, 8px); color: var(--sub); user-select: none; font-size: 13px; }
    .m3l .row:hover, .m3l .row.hov { background: var(--hy-trow-hover, var(--raise)); color: var(--ink); }
    .m3l .row.sel { color: var(--ink); background: var(--hy-trow-on, color-mix(in srgb, var(--sel, #3b82f6) 14%, transparent));
      box-shadow: var(--hy-trow-ring, inset 0 0 0 1px color-mix(in srgb, var(--sel, #3b82f6) 55%, transparent)); }   /* the app's selected row (ui/look.css), the image editor's */
    .m3l .row.in { background: var(--tint); } .m3l .row.hidden .nm, .m3l .row.hidden > .ic { opacity: .4; }
    .m3l .g { width: 14px; height: var(--hy-trow-h, 28px); flex: none; position: relative; } .m3l .g::before { content: ""; position: absolute; left: 7px; top: -1px; bottom: -1px; border-left: 1px solid var(--guide); }
    /* a row's colour in the list (its right click): the icon, the name and the lines under it */
    .m3l .row.nc > .ic, .m3l .row.nc > .nm { color: var(--nc); } .m3l .g.nc::before { border-left-color: color-mix(in srgb, var(--nc) 70%, transparent); }
    .m3l .chev { width: 16px; height: 16px; padding: 0; border: 0; background: none; color: var(--muted, var(--dim)); display: grid; place-items: center; flex: none; margin-right: 2px; }
    .m3l .row > .ic { color: var(--sub); margin-right: 7px; width: 15px; height: 15px; }
    .m3l .nm { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; } .m3l .nm small { color: var(--dim); font-size: 10px; margin-left: 6px; }
    .m3l .cnt { color: var(--dim); font-size: 10px; font-variant-numeric: tabular-nums; margin-left: 4px; }
    .m3l .tag { font-size: 9.5px; color: var(--pink); border: 1px solid color-mix(in srgb, var(--pink) 45%, transparent); border-radius: 4px; padding: 0 4px; margin-left: 4px; }
    .m3l .acts { display: flex; margin-left: 2px; } .m3l .acts button { width: 20px; height: 20px; padding: 0; border: 0; background: none; color: var(--dim); display: grid; place-items: center; opacity: 0; }
    .m3l .acts .ic { width: 13px; height: 13px; } .m3l .row:hover .acts button, .m3l .acts button.keep { opacity: 1; } .m3l .acts button:hover { color: var(--ink); }
    .m3l .acts button[data-lock].keep { color: var(--sub); }   /* a locked padlock at the list's full contrast (owner 2026-10-07), as in the image studio's layers */
    /* a thing's eye and lock as its parts inherit them (owner 2026-10-07): the row dimmed, the parent's state faint beside the row's own */
    .m3l .row.ghid .nm, .m3l .row.ghid > .ic { opacity: .55; } .m3l .acts button.inh, .m3l .row:hover .acts button.inh { opacity: .42; }
    .m3l .acts .inhlk { width: 20px; height: 20px; display: grid; place-items: center; color: var(--dim); opacity: .42; }
    /* the pick's settings while a lock holds them: grey and inert, the reason over them */
    .m3r .dk.m3dis { opacity: .42; pointer-events: none; filter: saturate(0); }
    .m3r .m3why { display: flex; align-items: center; gap: 6px; margin: 8px 14px 0; } .m3r .m3why svg { flex: none; }
    .m3r { right: var(--r); top: var(--t); bottom: var(--b); width: 280px; overflow: auto; display: flex; flex-direction: column; }
    /* the inspector's head is a row of the same system: the thing's icon, its name, what it is, at the panel's padding */
    .m3r .ih { display: flex; align-items: center; gap: 8px; min-height: var(--hy-trow-h, 28px); padding: 4px 14px 8px 14px; position: sticky; top: 0; background: var(--card); z-index: 2; }
    /* Properties | History: the block header's tabs (.hy-bh), as Image Studio's; its History rows (.hrow, .cur, .fut) */
    .m3r.hist > :is(.ih, .inf, .dk) { display: none; }
    .m3r .m3hist:not([hidden]) { padding: 6px; display: flex; flex-direction: column; gap: 1px; }
    .m3r .hrow { display: flex; align-items: center; gap: 9px; height: 32px; padding: 0 8px; border: 0; border-radius: var(--m3-r, 6px); background: transparent;
      color: var(--ink); font: 400 12.5px var(--sans, system-ui); width: 100%; text-align: left; cursor: pointer; transition: background .15s cubic-bezier(.32,.72,0,1), opacity .2s; }
    .m3r .hrow:hover { background: var(--raise); } .m3r .hrow .ic { width: 15px; height: 15px; flex: none; color: var(--sub); }
    .m3r .hrow.cur { background: color-mix(in srgb, var(--sel) 14%, transparent); box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--sel) 55%, transparent); }
    .m3r .hrow.fut { opacity: .42; } .m3r .hrow .ht { flex: 1; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .m3r .ih .ic { width: 15px; height: 15px; color: var(--sub); flex: none; } .m3r .ih div { display: flex; align-items: baseline; gap: 8px; min-width: 0; }
    .m3r .ih b { font-weight: 600; font-size: 13px; color: var(--ink); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; } .m3r .ih span { color: var(--muted, var(--dim)); font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .m3r .dk { padding: 8px 10px; } .m3r .dk .dialkit-root { width: 100%; --dial-glass-bg: var(--card); --dial-row-height: 30px; --dial-row-gap: 4px; --dial-radius: var(--m3-r); --dial-surface: color-mix(in srgb, var(--ink) 5%, transparent); }
    /* the radius is a row's: what is a box, not a row (a list that opens, a colour plane, a preview) keeps a box's corners */
    .m3ui .dialkit-root :is(.dialkit-select-dropdown, .dialkit-color-plane, .dialkit-image-frame, .dialkit-image-empty, .dialkit-image-option, .dialkit-image-option-preview, .dialkit-pad-surface, .dialkit-spring-viz, .dialkit-easing-viz) { border-radius: 10px; }
    :root[data-shape="pro"] .m3ui .dialkit-root :is(.dialkit-select-dropdown, .dialkit-color-plane, .dialkit-image-frame, .dialkit-image-empty, .dialkit-image-option, .dialkit-image-option-preview, .dialkit-pad-surface, .dialkit-spring-viz, .dialkit-easing-viz) { border-radius: 8px; }
    .m3ui .dialkit-root .dialkit-segmented-pill { border-radius: calc(var(--m3-r) - 2px); }
    .m3r .dialkit-panel-toolbar, .m3r .dialkit-panel-section-toolbar, .m3r .dialkit-panel-header { display: none; }
    .m3r .dk .dialkit-root :is(.dialkit-slider-label, .dialkit-toggle-label, .dialkit-button, .dialkit-select-label, .dialkit-text-label, .dialkit-color-label) { font-size: 12px; }
    /* the active camera's row (engine.js markCams): a dot where a tree row has its chevron, the name and icon at full contrast, the chip
       filled; the selection stays the list's own (.sel) */
    .m3l .row.act > .chev { position: relative; } .m3l .row.act > .chev::after { content: ""; width: 6px; height: 6px; border-radius: 50%; background: var(--pink); }
    .m3l .row.act > .nm { color: var(--ink); font-weight: 600; } .m3l .row.act:not(.nc) > .ic { color: var(--ink); }
    .m3l .row.act .tag { background: color-mix(in srgb, var(--pink) 16%, transparent); }
    /* a control that does not apply to this camera (engine.js greyCtl): greyed in its place, its reason in its tooltip */
    .m3r .dk .m3na { opacity: .4; cursor: default; } .m3r .dk .m3na * { cursor: default !important; }
    /* the card's output size under Frame (engine.js sizeRow): W × H in the rows' fields with the app's W ↔ H link between them (look.css .hy-link,
       the image studio's key), the presets on the long side in the app's switch (.seg) and ⇄ */
    .m3r .m3res { display: grid; gap: 4px; margin: 4px 0; } .m3r .m3res :is(.wh, .pre) { display: flex; align-items: center; gap: 4px; }
    .m3r .m3res label { flex: 1; min-width: 0; display: flex; align-items: center; gap: 6px; height: 30px; padding: 0 10px; border-radius: var(--m3-r); background: color-mix(in srgb, var(--ink) 5%, transparent); color: var(--sub); font-size: 12px; }
    .m3r .m3res input { flex: 1; min-width: 0; width: 100%; border: 0; outline: 0; padding: 0; background: none; color: var(--ink); font: inherit; font-variant-numeric: tabular-nums; text-align: right; }
    .m3r .m3res .u { color: var(--muted, var(--dim)); font-size: 11px; }
    .m3r .m3res .lk { width: 26px; height: 26px; flex: none; padding: 0; border: 0; border-radius: var(--m3-r); background: none; color: var(--muted, var(--dim)); display: grid; place-items: center; }
    .m3r .m3res .lk:hover { background: var(--raise); color: var(--ink); } .m3r .m3res .lk.on { color: var(--ink); background: var(--raise); box-shadow: inset 0 0 0 1px var(--line); }
    .m3r .m3res .lk:disabled { opacity: .35; } .m3r .m3res .seg { flex: 1; display: flex; } .m3r .m3res .seg button { flex: 1; font-variant-numeric: tabular-nums; }
    .m3r .m3res.m3na { opacity: .4; }
    /* in the block (round 12): W and H are wells, the sizes a choice in a well with its 24 px options on the Studio's plate, the link a 24 px key */
    .m3r.hy-blk .m3res label { height: var(--hy-ctl-h); padding: 0 8px; background: var(--hy-well); } .m3r.hy-blk .m3res label:hover { background: var(--hy-well-hov); }
    .m3r.hy-blk .m3res input { height: 100%; }
    .m3r.hy-blk .m3res .lk { width: var(--hy-ctl-h); height: var(--hy-ctl-h); } .m3r.hy-blk .m3res .lk.on { background: var(--hy-val-on); color: var(--hy-val-ink); box-shadow: none; }
    .m3r.hy-blk .m3res .seg { --hy-seg-pad: 2px; height: var(--hy-h-m); border-radius: var(--hy-well-r) !important; background: var(--hy-well); }
    .m3r.hy-blk .m3res .seg > :is(.st, button) { border-radius: var(--hy-well-in-r) !important; } .m3r.hy-blk .m3res .seg > .st { background: var(--hy-val-on); box-shadow: none; }
    .m3r.hy-blk .m3res .seg > button { height: var(--hy-h-s); }
    .m3r.hy-blk .dk .dialkit-root .dialkit-labeled-control:has(> .dialkit-segmented) { --hy-seg-pad: 2px; height: var(--hy-h-m); }   /* a choice's options 24 px in its row */
    .m3r .m3hint { padding: 10px 14px 0; } .m3r .real { padding: 8px 14px 0; font-size: 11px; color: var(--dim); line-height: 1.5; word-break: break-all; }
    .m3x { position: fixed; z-index: 60; bottom: var(--b); left: calc(var(--l) + 252px); right: calc(var(--r) + 292px); width: fit-content; margin-inline: auto; }
    .m3x .axes { width: 90px; height: 90px; display: block; touch-action: none; } .m3x .ring { fill: color-mix(in srgb, var(--card) 88%, transparent); stroke: var(--line); transition: fill .15s; } .m3x .axes:hover .ring { fill: var(--raise); }
    /* the scene's title in the top band: the board's stuck group title (canvas.html #gsticky .gst), on the crumb's line after it. A plate of
       the app's top row (Hyimg ui/look.css .hy-plate, owner 2026-10-07: «breadcrumb area тоже разношерстная»): the crumb's height, glass,
       shadow, corners and words; here only where it stands and how its two parts share it */
    .m3title { position: fixed; left: 0; top: 0; z-index: 61; display: flex; align-items: center; gap: 8px; cursor: default; }
    .m3title b { font-weight: inherit; color: var(--ink); flex: none; }
    .m3title code { font: 400 12px ui-monospace, Menlo, monospace; color: var(--muted, var(--dim)); overflow: hidden; text-overflow: ellipsis; min-width: 0; }
    .m3title.glide { transition: transform .3s cubic-bezier(.32,.72,0,1); }
    body.m3edit #gsticky { visibility: hidden; }   /* a group's stuck title would sit where the scene's is */
    body.m3edit #ctx { z-index: 70; }   /* the app's right-click menu opens over the editor's panels (the layer list's colours) */
    .m3x .ax circle { transition: r .12s; } .m3x .ax:hover circle { r: 10px; } .m3x text { font: 600 9px -apple-system, system-ui, sans-serif; fill: #0e0f11; text-anchor: middle; pointer-events: none; }`;
  document.head.appendChild(st);
  if (hy.placeAs) hy.placeAs(placeAs);   // a 3D file dropped from the library: a 3D card, not a picture
  hy.register(TYPE, {
    render(el, it, id) {
      id = id || el.dataset.id;
      if (it.pending && !it.scene) return void adopt(HY, engine, id);   // a dropped 3D file: its scene first (place.js)
      // while this card is edited the wheel moves its camera, not the board; at rest the board zooms over it as over a picture
      if (!el._wheel) { el._wheel = true; el.addEventListener("wheel", e => { if (E && E.isLive(el.dataset.id)) e.stopPropagation(); }, { passive: true }); }
      if (E && E.isLive(id)) E.nudge(id);   // its frame changed size: the live view follows
      if (!el._look) watchLook(el);
      fillView(id, it);
      poster(el, it, id);
      // a new card asks for a file first (owner 2026-10-06): Open file…, the media library, the recent ones; empty.js is loaded only then
      if (it.empty || el.querySelector(":scope > .e3")) import("./empty.js").then(m => m.showEmpty({ HY, t, engine, plugin: PLUGIN }, el, HY.board.items[id] || it, id));
    },
    surface,   // a picture for the board's looks: the opacity, the colour grade (HY.pic), on whatever the card shows now
    frame(id) { return !!(E && E.isLive(id)); },   // in the editor the card's frame changes like a picture's crop
    editBar(el, id) { if (E && E.isLive(id)) E.editBar(el, id); },   // the board's bar over the card in its editor: three.js · EEVEE · Cycles, «Render»
    frameBar: false,   // the frame and the output size live in the studio's Scene panel (owner 2026-10-07: «вот это в рендере я бы убрал»)
    resized(id) { if (E) E.framed(id); },
    dblclick(id) { studio(id); },
    onKey(e) {
      if (E && E.onKey(e)) return true;
      const id = oneCard(); if (e.key !== "Enter" || e.metaKey || e.ctrlKey || e.altKey || !id || (E && E.isLive())) return false;
      e.preventDefault(); studio(id); return true;   // Enter opens the selected 3D card's studio, as it opens a frame
    },
    info(id, it) {
      if (it.scene && !(E && E.docOf(it.scene)) && !DOCS.has(it.scene)) docFor(it.scene).then(() => HY.render());   // read once, shown next time
      const d = (E && it.scene && E.docOf(it.scene)) || (it.scene && DOCS.get(it.scene) && DOCS.get(it.scene).doc), c = d && (d.cameras || []).find(x => x.id === (it.camera || d.active_camera));
      return { name: t("3D scene"), meta: d ? `${t("{n} objects", { n: d.objects.length })}, ${t("{n} lights", { n: d.lights.length })}, ${t("{n} cameras", { n: d.cameras.length })}${c ? ` · ${c.name}, ${t("{n} mm", { n: Math.round(c.lens) })}` : ""}` : (it.scene || t("old card")),
        text: t("Double-click to edit · {file}", { file: it.scene || t("appears on the first opening") }) };
    },
  });
  if (hy.restored) { if (hy.history) hy.history(() => { PRE = revs(); }); hy.restored(why => sceneBack(why)); }
  hy.addButton(CUBE, t("3D scene: an object on the floor, light and a camera, double-click to edit"), () => engine().then(m => m.newScene()));
  // «3D Studio» first on the bar over one 3D card (owner 2026-10-07), as «Crop» over a picture: what a double click, Enter and the dock's
  // 3D segment do. Not over several cards or in the studio itself (its own bar is there then)
  if (hy.bar) hy.bar(ids => ids.length === 1 && oneCard() === ids[0] && !(E && E.isLive()) ? [{ first: true, icon: CUBE.replace('width="18" height="18"', 'width="15" height="15"'), label: t("3D Studio"), keys: "↵",
    title: t("Open 3D Studio for this card · Enter or a double click"), fn: () => studio(ids[0]) }] : []);
  // the 3D studio is a mode of the board's dock switch (owner 2026-10-06: «3D studio turns on only when we entered a 3D object, otherwise
  // not»): chosen while the editor is open, enabled when one 3D card is selected (a click opens it); leaving is the editor's Done (Enter)
  // color: the chosen segment in 3D Studio's pink, not the board's blue (owner 2026-10-09: «конечно», to giving 3D Studio its colour)
  if (hy.mode) hy.mode("3d", { label: t("3D"), name: t("3D Studio"), order: 30, icon: CUBE.replace('width="18" height="18"', 'width="16" height="16"'), color: "var(--pink)",
    title: t("3D Studio for the selected 3D card"), hint: t("Select a 3D card or enter one: 3D Studio opens for it"),
    isOpen: () => !!(E && E.isLive()),
    target: ids => ids.length === 1 && HY.board.items[ids[0]] && HY.board.items[ids[0]].type === TYPE ? ids[0] : null,
    enter: id => studio(id),
    leave() { if (!E || !E.isLive()) return; if (document.activeElement && document.activeElement.blur) document.activeElement.blur(); E.onKey({ key: "Enter", metaKey: true, preventDefault() {}, stopPropagation() {} }); }   // the dock's Board saves, as ⌘↵,
  });
  // the media library's 3D filter picked a file (review/v2.html): into the card that asked for it, or into a new one
  addEventListener("message", async e => {
    const d = e.data; if (e.origin !== location.origin || !d || d.type !== "model3dPick" || typeof d.path !== "string") return;
    const m = await engine(), card = d.card && HY.board.items[d.card] && HY.board.items[d.card].type === TYPE ? d.card : m.newScene();
    m.putFile(card, { path: d.path, ver: d.ver });
  });
  setInterval(poll, 3000);
}
