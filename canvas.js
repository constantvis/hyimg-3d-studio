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
const TYPE = "model3d";
const INBOX = "3d/scenes/inbox.json";
const CUBE = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="M12 3 4 7.5v9L12 21l8-4.5v-9z"/><path d="M4 7.5 12 12l8-4.5M12 12v9"/></svg>`;
const fileUrl = p => `/file?p=${encodeURIComponent(p)}`;

let HY, E = null, loading = null;
const engine = () => loading || (loading = import("./engine.js").then(m => { m.init(HY, { poster, posted }); E = m; return m; }));
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
  return { path: `${dir}.posters/${id}-${fnv(JSON.stringify([it.camera || "", it.bg || null, Math.round(it.w / it.h * 100) / 100]))}.${ext}`, ext };
}
// the engine wrote a still: its time is known, the card shows the file
function posted(path, mtime) { TIMES.set(path, mtime); }

// the card at rest: the still from the project when it is not older than the scene; else the engine draws it again and writes it
function poster(el, it, id, doc, force) {
  if (E && E.isLive(id)) return;
  let img = el.querySelector("img.m3");
  if (img && img.src && HY.dragging) return;   // while its frame is dragged the old still stretches; the new one is drawn on release
  if (!img) { el.innerHTML = `<img class="m3" alt="" decoding="async"><span class="b3" title="3D-сцена: двойной клик, чтобы редактировать">3D</span>`; img = el.querySelector("img.m3"); img.addEventListener("load", () => el.classList.add("lo")); }
  el.classList.toggle("see", see(it.bg));
  if (!it.scene) return void engine().then(m => m.renderPoster(el, it, id));   // an older card: only the engine knows how it looks
  const st = stillOf(it, id), old = oldStillOf(it, id), show = (t, s = st) => { const u = s.ext === "png" ? fileUrl(s.path) + `&v=${t}` : `/thumb?p=${encodeURIComponent(s.path)}&s=640&v=${t}`; if (img._u !== u) { img._u = u; img.src = u; } el.querySelector(".b3").textContent = "3D"; };
  if (force) return void engine().then(m => m.renderPoster(el, it, id, st));   // the editor just changed it: the engine has the newest scene
  times([it.scene, st.path, old.path]).then(() => {
    const ts = TIMES.get(it.scene), tp = TIMES.get(st.path), to = TIMES.get(old.path);
    if (tp) show(tp); else if (to) show(to, old);   // even an old still is better than an empty card while the new one is drawn
    if (!tp || (ts && ts > tp)) engine().then(m => m.renderPoster(el, it, id, st));
  });
}
const cardsOf = path => [...document.querySelectorAll(`.plg[data-type=${TYPE}]`)].filter(el => { const it = HY.board.items[el.dataset.id]; return it && it.scene === path; });

// an agent changed a scene file (an export from Blender): its cards follow; a request in inbox.json puts a card per camera
let inboxSeen = null, inboxT = undefined;
async function poll() {
  if (document.visibilityState !== "visible") return;
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
  return DOCS.get(path).doc;
}

export function register(hy) {
  HY = hy;
  const st = document.createElement("style"); st.textContent = `
    .plg[data-type=${TYPE}] img.m3 { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; pointer-events: none; }
    .plg[data-type=${TYPE}] .b3 { position: absolute; left: calc(6px / var(--z)); bottom: calc(6px / var(--z)); padding: 0 calc(6px / var(--z)); height: calc(22px / var(--z)); border-radius: calc(6px / var(--z));
      display: grid; place-items: center; background: rgba(20,20,22,.72); color: #fff; font: 700 calc(11px / var(--z)) var(--sans); letter-spacing: .04em; pointer-events: none; }
    .plg-live { outline: calc(2px / var(--z)) solid var(--sel) !important; overflow: visible !important; background: transparent !important; }
    .plg-live, .plg-live *, .m3ui .row { cursor: default !important; }   /* owner 2026-10-03: the mouse stays an arrow, no hand */
    .plg-live img.m3, .plg-live .b3 { visibility: hidden; }   /* the still picture under the live view would show through a see-through background */
    .plg-live canvas.m3live { position: absolute; inset: 0; width: 100%; height: 100%; display: block; touch-action: none; }
    /* grey while its still loads, like a picture (owner 2026-10-04); a see-through card turns clear once the still is there */
    .plg[data-type=${TYPE}] { background: var(--raise); } .plg[data-type=${TYPE}].lo.see { background: transparent; }
    .plg[data-type=${TYPE}]:has(img.m3[src^="data:image/png"]) { background: transparent; }
    body.m3edit #info { display: none !important; }
    .plg[data-type=${TYPE}] .h3 { position: absolute; inset: 0; display: grid; place-content: center; gap: calc(10px / var(--z)); padding: calc(16px / var(--z)); text-align: center;
      background: rgba(20,20,22,.78); color: #fff; font: 500 calc(13px / var(--z)) var(--sans); line-height: 1.45; z-index: 3; }
    .plg[data-type=${TYPE}] .h3 button { height: calc(30px / var(--z)); padding: 0 calc(14px / var(--z)); border: 0; border-radius: calc(8px / var(--z)); background: #fff; color: #111; font: 600 calc(12px / var(--z)) var(--sans); cursor: pointer; }
    /* the editor follows the interface's look and theme (owner 2026-10-04): «Студия» dark or light, its own palette; «Классика» the page's palette,
       Geist and glass panels like the rest of the classic canvas */
    .m3ui { --row-ink: color-mix(in srgb, var(--ink) 82%, var(--sub)); --tint: color-mix(in srgb, var(--ink) 3%, transparent);
      color: var(--ink); font: 400 12px/1.35 -apple-system, "SF Pro Text", system-ui, sans-serif; position: static; -webkit-font-smoothing: antialiased; }
    :root[data-ui="studio"] .m3ui, :root[data-ui="studio"][data-theme="dark"] .m3ui { --pink: #ff4fa3; --pink-ink: #1c0a13; --card: #1b1c1f; --raise: #25262a; --line: #2c2d32; --guide: #34353b; --ink: #ececef; --sub: #9a9ba3; --dim: #64656d; }
    :root[data-ui="studio"][data-theme="light"] .m3ui { --pink: #e5307f; --pink-ink: #fff; --card: #ffffff; --raise: #f0f0f2; --line: #e3e3e7; --guide: #d9d9de; --ink: #1b1c1f; --sub: #6b6c73; --dim: #9a9ba3; }
    :root:not([data-ui="studio"]) .m3ui { --pink: var(--sel); --pink-ink: #fff; --card: color-mix(in srgb, var(--panel) 92%, transparent); --guide: var(--line); --dim: var(--muted); font: 400 13px/1.4 var(--sans); }
    :root:not([data-ui="studio"]) .m3p { border-radius: 14px; -webkit-backdrop-filter: blur(18px) saturate(1.4); backdrop-filter: blur(18px) saturate(1.4); box-shadow: 0 12px 40px rgba(0,0,0,.35); }
    :root:not([data-ui="studio"]) .m3r .dk .dialkit-root { --dial-row-height: 34px; --dial-radius: 9px; --dial-surface: color-mix(in srgb, var(--ink) 6%, transparent);
      --dial-surface-hover: color-mix(in srgb, var(--ink) 10%, transparent); --dial-surface-active: color-mix(in srgb, var(--sel) 22%, transparent);
      --dial-text-root: var(--ink); --dial-text-section: var(--sub); --dial-text-label: var(--sub); --dial-text-primary: var(--ink); --dial-text-secondary: var(--sub); --dial-text-tertiary: var(--muted);
      --dial-border: var(--line); --dial-dropdown-bg: var(--panel); font-family: var(--sans); }
    :root:not([data-ui="studio"]) .m3r .dk .dialkit-root :is(.dialkit-slider-label, .dialkit-toggle-label, .dialkit-button, .dialkit-select-label, .dialkit-text-label, .dialkit-color-label, .dialkit-slider-value) { font-size: 13px; }
    .m3ui .ic { width: 15px; height: 15px; flex: none; }
    .m3p { position: fixed; z-index: 60; background: var(--card); border: 1px solid var(--line); border-radius: 12px; box-shadow: 0 16px 50px rgba(0,0,0,.35); }
    :root[data-ui="studio"][data-theme="light"] .m3p { box-shadow: 0 14px 40px rgba(20,20,30,.12); }
    .m3t { top: var(--t); left: calc(var(--l) + 252px); right: calc(var(--r) + 292px); width: fit-content; margin-inline: auto; display: flex; align-items: center; gap: 2px; padding: 5px; }
    .m3t button { position: relative; width: 30px; height: 30px; border: 0; border-radius: 8px; background: none; color: var(--sub); display: grid; place-items: center; }
    .m3t button:hover { background: var(--raise); color: var(--ink); } .m3t button.on { background: var(--pink); color: var(--pink-ink); }
    .m3t [data-key]::after { content: attr(data-key); position: absolute; right: 3px; bottom: 2px; font-size: 8px; opacity: .55; }
    .m3t .plus { background: var(--raise); color: var(--ink); } .m3t .sep { width: 1px; height: 18px; background: var(--line); margin: 0 5px; }
    .m3t .wide { width: auto; padding: 0 12px; display: flex; gap: 6px; color: var(--ink); background: var(--raise); margin-left: 4px; } .m3t .pri { background: var(--ink); color: var(--card); }
    .m3t .tip { position: relative; }
    .m3menu { position: absolute; top: 40px; left: -5px; z-index: 70; min-width: 180px; padding: 5px; background: var(--card); border: 1px solid var(--line); border-radius: 10px; box-shadow: 0 16px 40px rgba(0,0,0,.45); display: grid; gap: 1px; }
    .m3menu[hidden] { display: none; } .m3menu button { border: 0; border-radius: 6px; background: none; cursor: default; font: inherit; } .m3menu button:hover { background: var(--raise); color: var(--ink); } .m3menu button { width: 100%; height: 28px; display: flex; gap: 8px; justify-content: flex-start; padding: 0 8px; color: var(--row-ink); }
    .m3l { left: var(--l); top: var(--t); bottom: var(--b); width: 240px; display: flex; flex-direction: column; overflow: hidden; }
    .m3l .lh { display: flex; align-items: baseline; gap: 8px; padding: 12px 12px 8px; } .m3l .lh b { font-weight: 600; white-space: nowrap; }
    .m3l .lh code { color: var(--dim); font: 400 10px ui-monospace, Menlo, monospace; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; }
    .m3l .find { margin: 0 10px 4px; display: flex; align-items: center; gap: 6px; background: var(--raise); border-radius: 7px; padding: 0 8px; height: 28px; color: var(--dim); }
    .m3l .find input { flex: 1; min-width: 0; background: none; border: 0; outline: 0; color: var(--ink); font: inherit; } .m3l .find input::placeholder { color: var(--dim); }
    .m3l .opts { display: flex; justify-content: flex-end; padding: 2px 12px 2px; color: var(--dim); font-size: 11px; } .m3l .opts label { display: flex; gap: 5px; align-items: center; } .m3l .opts input { margin: 0; accent-color: var(--pink); }
    .m3l .tr { overflow: auto; flex: 1; padding: 0 6px 10px; } .m3l .sec { color: var(--dim); font-size: 11px; font-weight: 500; padding: 10px 8px 4px; } .m3l .none { color: var(--dim); padding: 14px 10px; }
    .m3l .row { display: flex; align-items: center; height: 25px; padding: 0 4px 0 6px; border-radius: 6px; color: var(--row-ink); user-select: none; }
    .m3l .row:hover, .m3l .row.hov { background: var(--raise); color: var(--ink); }
    .m3l .row.sel { color: var(--ink); background: color-mix(in srgb, var(--pink) 14%, transparent); box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--pink) 55%, transparent); }
    .m3l .row.in { background: var(--tint); } .m3l .row.hidden .nm, .m3l .row.hidden > .ic { opacity: .4; }
    .m3l .g { width: 14px; height: 25px; flex: none; position: relative; } .m3l .g::before { content: ""; position: absolute; left: 7px; top: -1px; bottom: -1px; border-left: 1px solid var(--guide); }
    .m3l .chev { width: 14px; height: 14px; padding: 0; border: 0; background: none; color: var(--dim); display: grid; place-items: center; flex: none; margin-right: 2px; }
    .m3l .chev .ic { width: 12px; height: 12px; stroke-width: 2.4; transition: transform .12s ease; }   /* Hyimg's one chevron (ui/look.css .hy-chev): 12 px, a 1.2 px line */ .m3l .row.closed .chev .ic { transform: rotate(-90deg); }
    .m3l .row > .ic { color: var(--sub); margin-right: 7px; width: 14px; height: 14px; }
    .m3l .nm { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; } .m3l .nm small { color: var(--dim); font-size: 10px; margin-left: 6px; }
    .m3l .cnt { color: var(--dim); font-size: 10px; font-variant-numeric: tabular-nums; margin-left: 4px; }
    .m3l .tag { font-size: 9.5px; color: var(--pink); border: 1px solid color-mix(in srgb, var(--pink) 45%, transparent); border-radius: 4px; padding: 0 4px; margin-left: 4px; }
    .m3l .acts { display: flex; margin-left: 2px; } .m3l .acts button { width: 20px; height: 20px; padding: 0; border: 0; background: none; color: var(--dim); display: grid; place-items: center; opacity: 0; }
    .m3l .acts .ic { width: 13px; height: 13px; } .m3l .row:hover .acts button, .m3l .acts button.keep { opacity: 1; } .m3l .acts button:hover { color: var(--ink); }
    .m3r { right: var(--r); top: var(--t); bottom: var(--b); width: 280px; overflow: auto; display: flex; flex-direction: column; }
    .m3r .ih { display: flex; align-items: center; gap: 10px; padding: 12px 14px 10px; border-bottom: 1px solid var(--line); position: sticky; top: 0; background: var(--card); z-index: 2; }
    .m3r .ih .ic { width: 18px; height: 18px; color: var(--sub); } .m3r .ih div { display: grid; min-width: 0; }
    .m3r .ih b { font-weight: 600; font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; } .m3r .ih span { color: var(--dim); font-size: 11px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .m3r .dk { padding: 8px; } .m3r .dk .dialkit-root { width: 100%; --dial-glass-bg: var(--card); --dial-row-height: 30px; --dial-row-gap: 4px; --dial-radius: 7px; --dial-surface: color-mix(in srgb, var(--ink) 5%, transparent); }
    .m3r .dialkit-panel-toolbar, .m3r .dialkit-panel-section-toolbar, .m3r .dialkit-panel-header { display: none; }
    .m3r .dk .dialkit-root :is(.dialkit-slider-label, .dialkit-toggle-label, .dialkit-button, .dialkit-select-label, .dialkit-text-label, .dialkit-color-label) { font-size: 12px; }
    .m3r .empty { padding: 10px 14px 0; color: var(--sub); line-height: 1.5; } .m3r .real { padding: 8px 14px 0; font-size: 11px; color: var(--dim); line-height: 1.5; word-break: break-all; }
    .m3x { position: fixed; z-index: 60; bottom: var(--b); left: calc(var(--l) + 252px); right: calc(var(--r) + 292px); width: fit-content; margin-inline: auto; }
    .m3x .axes { width: 90px; height: 90px; display: block; touch-action: none; } .m3x .ring { fill: color-mix(in srgb, var(--card) 88%, transparent); stroke: var(--line); transition: fill .15s; } .m3x .axes:hover .ring { fill: var(--raise); }
    .m3x .ax circle { transition: r .12s; } .m3x .ax:hover circle { r: 10px; } .m3x text { font: 600 9px -apple-system, system-ui, sans-serif; fill: #0e0f11; text-anchor: middle; pointer-events: none; }`;
  document.head.appendChild(st);
  hy.register(TYPE, {
    render(el, it, id) {
      id = id || el.dataset.id;
      // while this card is edited the wheel moves its camera, not the board; at rest the board zooms over it as over a picture
      if (!el._wheel) { el._wheel = true; el.addEventListener("wheel", e => { if (E && E.isLive(el.dataset.id)) e.stopPropagation(); }, { passive: true }); }
      if (E && E.isLive(id)) E.nudge(id);   // its frame changed size: the live view follows
      poster(el, it, id);
    },
    frame(id) { return !!(E && E.isLive(id)); },   // in the editor the card's frame changes like a picture's crop
    resized(id) { if (E) E.framed(id); },
    dblclick(id) { engine().then(m => m.goLive(id)); },
    onKey(e) { return E ? E.onKey(e) : false; },
    info(id, it) {
      if (it.scene && !(E && E.docOf(it.scene)) && !DOCS.has(it.scene)) docFor(it.scene).then(() => HY.render());   // read once, shown next time
      const d = (E && it.scene && E.docOf(it.scene)) || (it.scene && DOCS.get(it.scene) && DOCS.get(it.scene).doc), c = d && (d.cameras || []).find(x => x.id === (it.camera || d.active_camera));
      return { name: "3D-сцена", meta: d ? `${d.objects.length} предм., ${d.lights.length} света, ${d.cameras.length} кам.${c ? ` · ${c.name}, ${Math.round(c.lens)} мм` : ""}` : (it.scene || "старая карточка"),
        text: `Двойной клик: редактировать. Файл: ${it.scene || "появится при первом открытии"}. В Blender его переносит агент: blender/hyimg_scene.py в Hyimg-3d.` };
    },
  });
  hy.addButton(CUBE, "3D-сцена: предмет на полу, свет и камера, редактировать двойным кликом", () => engine().then(m => m.newScene()));
  setInterval(poll, 3000);
}
