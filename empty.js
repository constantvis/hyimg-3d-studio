// Hyimg 3D, a new card asks for a file (owner 2026-10-06: «When you press 3D it gives you our 3D frame, which offers: a button "Open file",
// or another button "Open media library", where everything is already filtered to 3D files, and on hover they rotate. And also a list of
// recent ones with previews and the same ability: on hover it automatically spins 360° around its own axis»). Drawn inside the card
// while its item has empty: true; a file, from any of the three ways, takes the scene's stand-in shape's place (engine.js putFile) and
// the card shows the scene as before. Loaded by canvas.js only when a card is empty.
//
// The block is a plate of constant screen size over the card's picture, the base scene (see style() below).
// The previews are the recent files' turntables: a still picture at rest that turns on hover (review/ui/spin.js), drawn once per file
// by sprites.js when nobody has yet.
import { ACCEPT } from "./loaders.js";   // the formats; no three.js is loaded until a file is read
import { stillUrl, spinOf } from "./turn.js";

const esc = s => String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
// the app's icons (ui/icons.js, owner 2026-10-07: «одно значение, одна иконка»): a 3D scene, a folder for a file from disk, the board's library
const CUBE = hyIcon("scene3d", 0, 1.8), FOLDER = hyIcon("folder", 0, 1.8), GRID = hyIcon("library", 0, 1.8);

let C = null, css = false;   // C: {HY, t, engine, plugin} from canvas.js
let spinReady = null;
const loadSpin = () => spinReady || (spinReady = window.hySpin ? Promise.resolve() : new Promise(ok => { const s = document.createElement("script"); s.src = "/ui/spin.js"; s.onload = s.onerror = () => ok(); document.head.appendChild(s); }));
let sprites = null;
const spritesMod = () => sprites || (sprites = import("./sprites.js"));   // three.js: only to draw a turntable that is missing

function style() {
  if (css) return; css = true;
  // The plate lies over the card's picture, the base scene (owner 2026-10-06: «and over that the UI, which does not grow to an endless size when we zoom
  // in further; it lies on top on a translucent plate»). It keeps one size on the screen at any zoom: it is laid out at 320 px and scaled by 1/--z (the
  // board's zoom, as the marks' calc(Npx / var(--z))), and by --k, the fit: 1 while the card on the screen is bigger than the plate, smaller when the card
  // is smaller (--w, --h are the card's size on the board, --ph the plate's height); below 40 % it gives way to the cube alone.
  const st = document.createElement("style"); st.textContent = `
    .plg[data-type=model3d] .e3 { position: absolute; inset: 0; z-index: 3; overflow: hidden; color: var(--ink); pointer-events: none;
      --k: clamp(0, min(1, calc((var(--w, 400) * var(--z, 1) - 24) / 320), calc((var(--h, 500) * var(--z, 1) - 24) / var(--ph, 300))), 1);
      animation: e3in .5s cubic-bezier(.32, .72, 0, 1) both; transition: opacity .3s cubic-bezier(.32, .72, 0, 1); }
    @keyframes e3in { from { opacity: 0; } }
    .plg[data-type=model3d] .e3.out { opacity: 0; }
    .plg[data-type=model3d] .e3.busy .e3-bx { filter: saturate(.6); } .plg[data-type=model3d] .e3.busy .e3-bx > * { opacity: .6; pointer-events: none; }
    .plg[data-type=model3d].plg-live .e3 { display: none; }
    .e3-bx { position: absolute; left: 50%; top: 50%; width: 320px; box-sizing: border-box; padding: 16px; display: grid; justify-items: center; gap: 12px; pointer-events: auto;
      font: 500 13px/1.3 var(--sans); border-radius: 18px; background: color-mix(in srgb, var(--panel) 72%, transparent); box-shadow: 0 0 0 1px color-mix(in srgb, var(--line) 80%, transparent), 0 14px 40px rgba(0, 0, 0, .35);
      -webkit-backdrop-filter: blur(18px) saturate(1.4); backdrop-filter: blur(18px) saturate(1.4);
      transform: translate(-50%, -50%) scale(calc(var(--k) / var(--z, 1))); transform-origin: 50% 50%; opacity: clamp(0, calc((var(--k) - .4) * 8), 1); visibility: visible; }
    :root[data-shape=pro] .e3-bx { border-radius: 10px; }
    .e3-bx > * { transition: opacity .3s cubic-bezier(.32, .72, 0, 1); }
    .e3-cube { position: absolute; left: 50%; top: 50%; width: 30px; height: 30px; color: #fff; filter: drop-shadow(0 1px 6px rgba(0, 0, 0, .45)); pointer-events: none;
      transform: translate(-50%, -50%) scale(calc(1 / var(--z, 1))); opacity: clamp(0, calc((.4 - var(--k)) * 8), 1); }
    .e3-cube svg { width: 100%; height: 100%; display: block; }
    .e3-ic { width: 26px; height: 26px; color: var(--muted); } .e3-ic svg { width: 100%; height: 100%; display: block; }
    .e3-bt { display: flex; flex-wrap: wrap; justify-content: center; gap: 8px; }
    .e3-b { display: inline-flex; align-items: center; gap: 7px; height: 34px; padding: 0 16px; border: 1px solid var(--line); border-radius: 999px; background: var(--panel); color: var(--ink);
      font: inherit; font-weight: 600; white-space: nowrap; cursor: pointer; outline: none;
      transition: background-color .25s cubic-bezier(.32, .72, 0, 1), color .25s cubic-bezier(.32, .72, 0, 1), transform .25s cubic-bezier(.32, .72, 0, 1), border-color .25s cubic-bezier(.32, .72, 0, 1); }
    .e3-b svg { width: 16px; height: 16px; flex: none; }
    .e3-b:hover { background: var(--raise); border-color: var(--muted); } .e3-b:active { transform: scale(.96); }
    .e3-b.pri { background: var(--ink); color: var(--panel); border-color: var(--ink); } .e3-b.pri:hover { background: var(--ink); opacity: .88; }
    :root[data-shape=pro] .e3-b { border-radius: 8px; }
    .e3-fm { color: var(--muted); font-weight: 400; font-size: 11px; text-align: center; }
    .e3-rc { width: 100%; display: grid; gap: 8px; margin-top: 2px; } .e3-rc[hidden] { display: none; }
    .e3-h { color: var(--sub); font-size: 11px; font-weight: 600; letter-spacing: .02em; text-align: left; padding-left: 2px; }
    .e3-gr { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
    .e3-t { position: relative; display: block; min-width: 0; padding: 0; border: 0; background: none; color: var(--sub); font: inherit; font-size: 10px; text-align: left; cursor: pointer; outline: none; }
    .e3-s { aspect-ratio: 1; border-radius: 10px; background: var(--panel) center / cover no-repeat; box-shadow: 0 0 0 1px var(--line);
      transition: box-shadow .25s cubic-bezier(.32, .72, 0, 1), transform .25s cubic-bezier(.32, .72, 0, 1); display: grid; place-items: center; color: var(--muted); }
    .e3-s svg { width: 38%; height: 38%; }
    :root[data-shape=pro] .e3-s { border-radius: 6px; }
    .e3-t:hover .e3-s { box-shadow: 0 0 0 2px var(--sel); } .e3-t:active .e3-s { transform: scale(.97); }
    .e3-t b { display: block; margin-top: 3px; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .e3-t:hover { color: var(--ink); }
    @media (prefers-reduced-motion: reduce) { .plg[data-type=model3d] .e3, .e3-b, .e3-s { transition: none; animation: none; } }`;
  document.head.appendChild(st);
}

const tile = it => {
  const sp = spinOf(it), still = it.sprite ? `style="background-image: url('${esc(stillUrl(it, 240))}')"` : "";
  return `<button class="e3-t" data-path="${esc(it.path)}" title="${esc(it.path)}"><i class="e3-s" ${sp ? `data-spin='${esc(sp)}'` : ""} ${still}>${it.sprite ? "" : CUBE}</i><b>${esc(it.name)}</b></button>`;
};

// the recent files of this project with their previews, newest first
async function recent() {
  try {
    const r = await (await fetch(`/api/plugin/${encodeURIComponent(C.plugin)}/recent`, { method: "POST", body: "{}" })).json(), paths = r.recent || [];
    if (!paths.length) return [];
    const info = await (await fetch("/api/models3d", { method: "POST", body: JSON.stringify({ paths }) })).json();
    paths.forEach((p, i) => { if (!info[i]) fetch(`/api/plugin/${encodeURIComponent(C.plugin)}/recent`, { method: "POST", body: JSON.stringify({ remove: p }) }).catch(() => {}); });   // a file that is gone
    return info.filter(Boolean);
  } catch (e) { return []; }
}

async function fill(ov, id) {
  const box = ov.querySelector(".e3-rc"), gr = ov.querySelector(".e3-gr"); ov._at = Date.now();
  const list = await recent();
  if (!ov.isConnected) return;
  ov._list = list;
  const same = JSON.stringify(list.map(i => [i.path, !!i.sprite]));
  if (ov._same === same) return; ov._same = same;
  box.hidden = !list.length; gr.innerHTML = list.map(tile).join("");
  // the ones with no turntable yet get one drawn, one after another, and turn into their picture when it is there
  const missing = list.filter(i => !i.sprite);
  if (missing.length) {
    const m = await spritesMod();
    for (const it of missing) m.ensure(it).then(sp => { if (!sp || !ov.isConnected) return; it.sprite = sp; ov._same = ""; const el = gr.querySelector(`[data-path="${CSS.escape(it.path)}"]`); if (el) el.outerHTML = tile(it); });
  }
}

export function showEmpty(ctx, el, it, id) {
  C = Object.assign(C || {}, ctx); style();
  if (it.empty) { el.style.setProperty("--w", it.w || 400); el.style.setProperty("--h", it.h || 500); }   // the card's size on the board, for the plate's fit
  let ov = el.querySelector(":scope > .e3");
  if (!it.empty) {   // a file has come: the picture shows through
    if (ov && !ov.classList.contains("out")) { ov.classList.add("out"); setTimeout(() => ov.remove(), 320); }
    return;
  }
  if (ov) { if (ov.classList.contains("out")) { ov.remove(); ov = null; } else return; }   // drawn already: the card's changes do not redraw it
  const t = C.t, embed = !!C.HY.EMBED;
  ov = document.createElement("div"); ov.className = "e3"; ov.dataset.id = id;
  ov.innerHTML = `<div class="e3-bx"><div class="e3-ic">${CUBE}</div>
    <div class="e3-bt"><button class="e3-b pri" data-a="file">${FOLDER}${esc(t("Open file…"))}</button>${embed ? `<button class="e3-b" data-a="lib">${GRID}${esc(t("Media library"))}</button>` : ""}</div>
    <div class="e3-fm">${esc(t("3D file: glb, gltf, obj, stl, fbx, step or iges"))}</div>
    <div class="e3-rc" hidden><div class="e3-h">${esc(t("Recent"))}</div><div class="e3-gr"></div></div>
    <input type="file" hidden accept="${ACCEPT}" multiple></div><div class="e3-cube">${CUBE}</div>`;
  el.appendChild(ov);
  const bx = ov.querySelector(".e3-bx"); new ResizeObserver(() => ov.style.setProperty("--ph", bx.offsetHeight + 24)).observe(bx);   // the plate's own height: the fit needs it
  // a click on the card's buttons is theirs: the board neither drags nor opens the editor under them
  for (const ev of ["pointerdown", "dblclick", "contextmenu"]) ov.querySelector(".e3-bx").addEventListener(ev, e => { if (e.target.closest("button, input")) e.stopPropagation(); });
  const put = async what => { ov.classList.add("busy"); try { await (await C.engine()).putFile(id, what); } finally { ov.classList.remove("busy"); } };
  const input = ov.querySelector("input");
  input.addEventListener("change", () => { const files = [...input.files]; input.value = ""; if (files.length) put({ files }); });
  ov.addEventListener("click", e => {
    const b = e.target.closest("button"); if (!b) return;
    if (b.dataset.a === "file") { window.hyimgAccept = ACCEPT; input.click(); }   // the Mac app's own panel (WKWebView) narrows itself to these formats
    else if (b.dataset.a === "lib") parent.postMessage({ type: "open3d", card: id }, location.origin);   // the library beside the canvas, its 3D filter on
    else if (b.dataset.path) { const hit = (ov._list || []).find(x => x.path === b.dataset.path); put({ path: b.dataset.path, ver: hit && hit.ver }); }
  });
  // a STEP or IGES file is converted by FreeCAD on the server first (owner 2026-10-06): the line under the buttons says so while the card waits
  const fm = ov.querySelector(".e3-fm"), fmText = fm.textContent;
  const onCad = e => {
    if (!ov.isConnected) return removeEventListener("hy3d-cad", onCad);
    const d = e.detail || {};
    if (ov.classList.contains("busy") && d.state === "working") fm.textContent = t("Converting {name} with FreeCAD…", { name: d.name || "" });
    else if (d.state !== "working") fm.textContent = fmText;
  };
  addEventListener("hy3d-cad", onCad);
  loadSpin().then(() => window.hySpin && hySpin.bind(ov, ".e3-t"));
  ov.addEventListener("pointerenter", () => { if (Date.now() - (ov._at || 0) > 3000) fill(ov, id); });
  fill(ov, id);
}
