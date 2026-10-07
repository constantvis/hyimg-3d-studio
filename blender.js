// The 3D card in Blender (owner 2026-10-06: «a switch: I spin and turn [the 3D card] and can switch from three.js to Blender (Cycles,
// EEVEE and so on) ... when I press OK I get the render like in the pictures»). For a scene that came from a Blender studio
// (scene.studio, tools/studio_angles.py) a bar stands centred over the card, on the board's frame bar, as the selection bar over a picture
// (owner 2026-10-06: «it must be in the centre, as the standard menu over a picture»): the app's one switch «three.js · EEVEE · Cycles», the
// materials it renders with and «Render» (the dock keeps only the tools). three.js is the editor as it is (it turns at 60 fps); on EEVEE
// or Cycles the card shows Blender's frame of its camera: while the camera turns the card shows three.js, a moment after the mouse lets go
// Blender renders that view in steps (4, 16, 64 samples), each one shown as it comes; a newer view ends the older render. «Render»
// renders the angle's final frame (its size, samples, exposure, Cycles on the processor as the studio does) and puts it on the board
// beside the card, saved as a new picture with its json. The server side is bridge.py; this module only asks it and shows what it answers.
//
// The card remembers its mode (item.render: "EEVEE" | "CYCLES", none for three.js), the look it asks for (item.look: "angle" for the
// picture's own materials, else the studio's current ones) and its last Blender frame (item.blenderStill, shown at rest by canvas.js).
// The card's variant of light and materials (variants.js, owner 2026-10-07: «свет тестировать и материалы») goes with each frame, and A/B
// (item.compare) renders a second variant after the first: the card shows them side by side, a line to drag between them.
const PAUSE_MS = 350, POLL_MS = 200, LOOK_MS = 5000;
const fnv = s => { let h = 0x811c9dc5; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 0x01000193) >>> 0; } return h.toString(16).padStart(8, "0"); };
const sleep = ms => new Promise(r => setTimeout(r, ms));

export function studioAngle(doc, camId) { return doc && doc.studio && doc.studio.angles && doc.studio.angles[camId] ? doc.studio.angles[camId] : null; }

// the bridge's route (bridge.py): JSON in and out, or a frame's png (raw)
export const bridgeApi = plugin => async (body, raw) => {
  const r = await fetch(`/api/plugin/${encodeURIComponent(plugin)}/blender`, { method: "POST", body: JSON.stringify(body) });
  if (raw) { if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || r.statusText); return r.blob(); }
  const j = await r.json().catch(() => ({ error: r.statusText })); if (!r.ok || j.error && !j.job) throw new Error(j.error || r.statusText); return j;
};

export function attachBlender(L, { HY, t, plugin }) {
  if (!studioAngle(L.e.doc, L.camId())) return null;
  const api = bridgeApi(plugin);
  const item = () => HY.board.items[L.id];
  const mode = () => item().render || "three";
  // the editor's bar of the card (owner 2026-10-06: «this bottom menu, it is not clear at all what is going on there ... a thing hanging
  // there that sets and switches the modes», then «it must be in the centre, as the standard menu over a picture»): the engine (the app's
  // one switch), the materials (a select with the app's chevron) and «Render», with its progress inside and ✕ (Esc) beside it while it
  // runs; the dock keeps the tools
  // the engines' icons are the app's (ui/icons.js): three.js the board's own 3D, EEVEE fast, Cycles traced rays
  const ICON = { three: "scene3d", EEVEE: "eevee", CYCLES: "cycles" };   // hy-icon-names
  const svg = n => hyIcon(n, 0, 1.9);
  const chev = window.HY_CHEV;
  const wrap = document.createElement("div"); wrap.className = "m3bplate"; wrap.setAttribute("role", "toolbar"); wrap.setAttribute("aria-label", "Blender");
  wrap.innerHTML = `<div class="seg m3eng" role="group" aria-label="${t("Preview engine")}">`
    + [["three", "three.js", t("three.js: the fast preview, turns at 60 fps")], ["EEVEE", "EEVEE", t("Blender EEVEE: the studio's scene, a frame in about a second")], ["CYCLES", "Cycles", t("Blender Cycles: the studio's scene as the renders are made, in steps")]]
      .map(([k, w, tip]) => `<button type="button" data-eng="${k}" title="${tip}" aria-pressed="${mode() === k}">${svg(ICON[k])}<span>${w}</span></button>`).join("")
    + `</div><label class="m3lk"><span class="v"></span>${chev}<select data-look aria-label="${t("Materials")}"><option value="current"></option><option value="angle"></option></select></label>`
    + (L.look ? L.look.barHtml() : "")
    + `<button type="button" class="m3rend" data-ok title="${t("Render this angle's final frame in Blender Cycles (the picture's size, samples and exposure) and save it as a new picture beside the card")}"><i class="pr"></i><span class="l">${t("Render")}</span></button>`
    + `<button type="button" class="m3stop" data-stop hidden title="${t("Stop the render · Esc")}" aria-label="${t("Stop the render")}">${svg("close")}</button>`;
  if (L.look) L.look.wireBar(wrap);
  const okBtn = wrap.querySelector("[data-ok]"), okLabel = okBtn.querySelector(".l"), stopBtn = wrap.querySelector("[data-stop]"), lookSel = wrap.querySelector("[data-look]"), lookLabel = wrap.querySelector(".m3lk");
  // where it stands is the board's: the card's editor bar (canvas.html renderHandles, def.editBar) centred over the card on the frame bar,
  // kept on screen as every selection bar (clampBars); the board draws its bar again on each change and this same element moves in
  // the bar grows when its labels come (the look's name, the card's variant): the board keeps it inside its free part again (canvas.html clampBars)
  let barRo = null;
  const mount = el => {
    el.appendChild(wrap); if (window.hySeg) window.hySeg(wrap);
    if (barRo) barRo.disconnect();
    barRo = new ResizeObserver(() => { if (typeof window.clampBars === "function") window.clampBars(); }); barRo.observe(el);
  };
  // Blender's frame over the live view, and a line of state at its foot
  const img = document.createElement("img"); img.className = "m3bimg"; img.alt = ""; img.hidden = true; L.el.appendChild(img);
  // A/B: the compared variant's frame over the left part of the card, up to the line (--ab, a share of the width), and the names of both
  const imgA = document.createElement("img"); imgA.className = "m3bimg m3bimgA"; imgA.alt = ""; imgA.hidden = true; L.el.appendChild(imgA);
  const ab = document.createElement("div"); ab.className = "m3split"; ab.hidden = true;
  ab.innerHTML = `<i class="ln"></i><b class="hd" title="${t("Drag: where A ends and B begins")}"></b><span class="la"></span><span class="lb"></span>`; L.el.appendChild(ab);
  ab.querySelector(".hd").addEventListener("pointerdown", ev => {
    ev.stopPropagation(); ev.preventDefault(); const h = ev.currentTarget; h.setPointerCapture(ev.pointerId);
    const move = e => { const r = L.el.getBoundingClientRect(); L.el.style.setProperty("--ab", Math.min(0.98, Math.max(0.02, (e.clientX - r.left) / r.width)).toFixed(4)); };
    const up = () => { h.removeEventListener("pointermove", move); h.removeEventListener("pointerup", up); };
    h.addEventListener("pointermove", move); h.addEventListener("pointerup", up);
  });
  const st = document.createElement("div"); st.className = "m3bst"; st.hidden = true; L.el.appendChild(st);
  let look = null, shownKey = "", wantKey = "", changedAt = 0, dragging = false, job = null, okJob = null, url = "", lastLook = null, timer = 0, lookTimer = 0, dead = false;
  let urlA = "", shownA = "";

  const camNow = () => { const c = (L.e.doc.cameras || []).find(x => x.id === L.camId()); return c ? { loc: c.loc, rot: c.rot, lens: c.lens, sensor: c.sensor, sensor_h: c.sensor_h, fit: c.fit, shift: c.shift } : null; };
  const camFor = () => { const c = camNow(), k = (L.e.doc.cameras || []).find(x => x.id === L.camId()); return c && Object.assign({ name: k && k.name, clip: k && k.clip }, c); };   // the card's view for the bridge (it makes the scene's camera follow it before a render)
  const lookChoice = () => item().look === "angle" ? "angle" : "current";
  const keyNow = side => JSON.stringify([mode(), lookChoice(), L.camId(), camNow(), Math.round(item().w / item().h * 1000), look && look.key,
    L.look ? L.look.key(side === "A" ? item().compare : undefined) : ""]);
  const comparing = () => !!(L.look && item().compare);
  const say = (text, sticky) => { st.textContent = text; st.hidden = !text; clearTimeout(st._t); if (text && !sticky) st._t = setTimeout(() => { st.hidden = true; }, 4000); };
  const setLookLabel = () => {
    const a = studioAngle(L.e.doc, L.camId()), own = a ? a.look : "?";
    const [cur, pic] = lookSel.options;
    cur.textContent = t("{id} · current", { id: look ? look.id : "…" }); pic.textContent = t("{id} · as in the picture", { id: own });
    lookSel.value = lookChoice();
    lookLabel.querySelector(".v").textContent = lookSel.options[lookSel.selectedIndex].textContent;
    lookLabel.title = t("Materials of the Blender studio: the state it is in now{src}, or the ones this picture was rendered with ({own})",
      { own, src: look ? ` (${look.id}, ${look.source === "pointer" ? t("the studio's pointer") : t("its newest series")}${look.updated ? ", " + look.updated : ""})` : "" });
  };
  const showBlender = on => {
    img.hidden = !on || !url || mode() === "three";
    const a = !img.hidden && comparing() && !!urlA && shownA === keyNow("A"); imgA.hidden = ab.hidden = !a;
    if (a) { ab.querySelector(".la").textContent = "A · " + L.look.nameOf(item().compare); ab.querySelector(".lb").textContent = "B · " + L.look.nameOf(item().variant || "base"); }
  };
  const sync = () => {
    wrap.querySelectorAll("[data-eng]").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.eng === mode())));
    if (mode() === "three") { img.hidden = true; say(""); }
    setLookLabel(); showBlender(!dragging); if (L.look) L.look.sync();
  };

  async function readLook() {
    try {
      const l = await api({ action: "look", scene: L.path });
      if (dead) return;
      if (lastLook && l.key !== lastLook.key) { HY.toast(t("Materials updated: {id}", { id: l.id + (l.note ? ` · ${l.note}` : "") })); changedAt = Date.now(); }
      lastLook = look = l; setLookLabel();
    } catch (e) { /* the studio is not reachable: the label stays */ }
  }
  async function render(key, side) {
    const my = { key, side }; job = my;
    const body = { action: "preview", scene: L.path, camera: L.camId(), cam: camFor(), w: item().w, h: item().h, engine: mode(), look: lookChoice(), card: L.id,
      ...(L.look ? L.look.body(side === "A" ? item().compare : undefined) : {}) };
    let r;
    try { r = await api(body); } catch (e) { if (job === my) say(t("Blender: {e}", { e: e.message }), true); return; }
    my.id = r.job; let seen = 0;
    say(side === "A" ? t("Blender: A · {name}…", { name: L.look.nameOf(item().compare) }) : t("Blender: preparing the frame…"), true);
    while (job === my && !dead) {
      let s; try { s = await api({ action: "job", job: my.id }); } catch (e) { break; }
      if (job !== my) break;
      if (s.frames > seen) {
        seen = s.frames;
        try {
          const blob = await api({ action: "frame", job: my.id, n: seen - 1 }, true);
          if (job !== my) break;
          const l = s.last, own = L.look ? " · " + L.look.nameOf(side === "A" ? item().compare : item().variant || "base") : "";
          if (side === "A") { if (urlA) URL.revokeObjectURL(urlA); urlA = URL.createObjectURL(blob); imgA.src = urlA; shownA = key; }
          else { if (url) URL.revokeObjectURL(url); url = URL.createObjectURL(blob); img.src = url; shownKey = key; }
          showBlender(!dragging);
          const turned = s.exact_camera ? "" : " · " + t("camera turned");
          say(`${side === "A" ? "A · " : ""}${l.engine === "EEVEE" ? "EEVEE" : "Cycles"} · ${l.samples} ${t("samples")} · ${l.seconds} ${t("s")} · ${s.look.id}${own}${turned}`, l.step + 1 < l.steps);
          if (l.step + 1 === l.steps && side !== "A") keepStill(blob);
        } catch (e) { /* the next poll tries again */ }
      }
      if (!["building", "rendering"].includes(s.state)) { if (s.state === "error") say(t("Blender: {e}", { e: s.error }), true); break; }
      await sleep(POLL_MS);
    }
    my.done = true;
  }
  // the last frame is the card's picture at rest (canvas.js shows item.blenderStill), a file of its own per view in the scene's .posters
  async function keepStill(blob) {
    const dir = L.path.replace(/[^/]+$/, ""), path = `${dir}.posters/${L.id}-b-${fnv(keyNow())}.png`;
    try {
      const r = await fetch(`/api/file?p=${encodeURIComponent(path)}`, { method: "POST", body: blob });
      if (r.ok && !dead) item().blenderStill = path;
    } catch (e) { /* the editor keeps its view; the card shows three.js at rest */ }
  }
  function tick() {
    if (dead) return;
    const k = keyNow();
    if (mode() === "three") return;
    if (k !== wantKey) { wantKey = k; changedAt = Date.now(); if (shownKey !== k) img.hidden = true; }
    if (!dragging && k !== shownKey && (!job || job.key !== k) && Date.now() - changedAt >= PAUSE_MS) return render(k, "B");
    const ka = comparing() ? keyNow("A") : "";   // A/B: the compared variant once the card's own is there
    if (ka && !dragging && shownKey === k && ka !== shownA && (!job || job.key !== ka || job.side !== "A") && (!job || job.done) && Date.now() - changedAt >= PAUSE_MS) render(ka, "A");
    showBlender(!dragging);
  }
  function setMode(m) {
    const it = item(); if (m === "three") delete it.render; else it.render = m;
    sync(); wantKey = ""; shownKey = ""; job = null; img.hidden = true;
    L.allowSlow = L.allowSlow || m !== "three";   // three.js draws only while the camera turns: a slow frame of it does not stop the editor
    if (m !== "three") { readLook(); tick(); }
  }
  let expect = 30;   // seconds the last final took here: the progress inside «Render» is an estimate from it
  const progress = (on, secs) => {
    okBtn.classList.toggle("busy", on); stopBtn.hidden = !on;
    okBtn.style.setProperty("--p", on ? String(Math.min(0.95, secs / expect)) : "0");
    okLabel.textContent = on ? t("Render · {s} s", { s: Math.round(secs) }) : t("Render");
  };
  async function stop() {
    if (!okJob) return false;
    const my = okJob; okJob = null; progress(false, 0);
    try { if (my.id) await api({ action: "cancel", job: my.id }); } catch (e) { /* gone already */ }
    say(t("Render stopped"), false); return true;
  }
  async function ok() {
    if (okJob) return;
    const my = {}; okJob = my; progress(true, 0);
    let r;
    // at the card's output size, W × H px of the Scene panel (engine.js L.outSize, owner 2026-10-07)
    try { r = await api({ action: "final", scene: L.path, camera: L.camId(), cam: camFor(), w: item().w, h: item().h, res: L.outSize ? L.outSize() : undefined, look: lookChoice(), card: L.id,
      ...(L.look ? L.look.body() : {}) }); }
    catch (e) { okJob = null; progress(false, 0); HY.toast(t("Blender: {e}", { e: e.message })); return; }
    my.id = r.job; const t0 = Date.now();
    while (okJob === my && !dead) {
      progress(true, (Date.now() - t0) / 1000);
      let s; try { s = await api({ action: "job", job: my.id }); } catch (e) { break; }
      if (s.state === "done" && s.saved) { expect = Math.max(5, s.elapsed); place(s); break; }
      if (!["building", "rendering", "saving"].includes(s.state)) { if (s.state === "error") HY.toast(t("Blender: {e}", { e: s.error })); break; }
      await sleep(500);
    }
    if (okJob === my) { okJob = null; progress(false, 0); }
  }
  // the final frame beside its card: the first free place right of it in its row, inside the group when there is room
  function place(s) {
    const it = item(), w = it.w, h = Math.round(w / s.saved.ar), gap = 24, before = HY.snap();
    const rects = Object.keys(HY.board.items).filter(k => k !== L.id).map(k => HY.rectOf(k)).filter(r => r && r.x != null);
    let x = it.x + it.w + gap, y = it.y;
    for (let guard = 0; guard < 200; guard++) {
      const hit = rects.filter(r => r.x < x + w && r.x + r.w > x && r.y < y + h && r.y + r.h > y);
      if (!hit.length) break;
      x = Math.max(...hit.map(r => r.x + r.w)) + gap;
    }
    const id = HY.addPicture(s.saved.path, s.saved.ar, x, y, w);
    if (it.grade && HY.board.items[id]) HY.board.items[id].grade = JSON.parse(JSON.stringify(it.grade));   // the card's colour grade goes with its render as a property, the file is not graded
    HY.commit(before, t("3D: Blender frame {path} beside the card", { path: s.saved.path }));   // at «Done» part of the session's one step
    HY.toast(t("Saved {path} ({s} s), it is beside the card", { path: s.saved.path, s: s.elapsed }));
    return id;
  }

  wrap.addEventListener("click", ev => {
    const b = ev.target.closest("[data-eng],[data-ok],[data-stop]"); if (!b) return;
    ev.stopPropagation();
    if (b.dataset.eng) return setMode(b.dataset.eng);
    if (b.dataset.stop !== undefined) return stop();
    if (b.dataset.ok !== undefined) return ok();
  });
  lookSel.addEventListener("change", () => { const it = item(); if (lookSel.value === "angle") it.look = "angle"; else delete it.look; setLookLabel(); });
  for (const ev of ["pointerdown", "dblclick", "wheel"]) wrap.addEventListener(ev, x => x.stopPropagation());
  L.orbit.addEventListener("start", () => { dragging = true; showBlender(false); });
  L.orbit.addEventListener("end", () => { dragging = false; changedAt = Date.now(); if (shownKey === keyNow()) showBlender(true); });
  timer = setInterval(tick, 120);
  lookTimer = setInterval(() => { if (mode() !== "three") readLook(); }, LOOK_MS);
  if (mode() !== "three") L.allowSlow = true;
  sync(); readLook().then(() => tick());
  return {
    mount,
    escape() { if (!okJob) return false; stop(); return true; },   // Esc stops a running render before it closes anything
    lookId: () => (look ? look.id : null),
    dispose() {
      dead = true; clearInterval(timer); clearInterval(lookTimer); job = null; if (barRo) barRo.disconnect();
      img.remove(); imgA.remove(); ab.remove(); st.remove(); wrap.remove(); if (url) URL.revokeObjectURL(url); if (urlA) URL.revokeObjectURL(urlA);
    },
  };
}
