"""The pick seen whole (owner 2026-10-07: «если я выбрал 3D объект, он должен оставаться без обводки, а также как при hover ... объект
должен быть полностью виден, как будто он сверху наложен на текущий рендер ... То есть закрывает, но прозрачным таким ghost-эффектом»).

A light grey slab stands in front of a red box (right) and a blue phone model (left), each partly hidden behind it. Picked, the red box
shows through the slab: the slab's pixels where the box is turn toward red, and nothing changes outside the objects (no outline). Under
the mouse it shows fainter and its visible part is lifted, so a hover is not a pick. Two picked (the box and the phone) both show; the
phone picked by its row in the tree shows with all its parts. Deselected, the view is the very same pixels as before; with the
interface hidden (⌘.) there is no ghost. The Scene panel's «Selection highlight» is Ghost by default, Outline brings the pink marks back.
Chromium (software GL) and WebKit, light and dark.

  HYIMG_REPO=<Hyimg checkout> python3 -m pytest tests/test_ghost.py
  M3_SHOTS=<folder> also saves screenshots
"""
import os

import pytest
from playwright.sync_api import sync_playwright

from test_canvas_3d import board_server
from test_3d_files import ENGINES
from test_editor_ui import open_editor, go_on
from test_camera_panel import open_board
from test_outliner_sections import owner_scene, settle

SHOTS = os.environ.get("M3_SHOTS")
Q = [1, 0, 0, 0]


def shot(page, name):
    if SHOTS: os.makedirs(SHOTS, exist_ok=True); page.screenshot(path=os.path.join(SHOTS, name + ".png"))


def scene():
    d = owner_scene()
    def box(i, n, size, loc, color):
        return {"id": i, "name": n, "src": {"type": "prim", "shape": "box", "size": size}, "loc": loc, "rot": Q, "scale": [1, 1, 1], "color": color}
    d["objects"] = [box("front", "Front", [0.16, 0.02, 0.22], [0.0, -0.30, 0.11], "#d9d9d9"),
                    box("back", "Back", [0.14, 0.14, 0.14], [0.13, 0.05, 0.07], "#e01414"),
                    {"id": "phone", "name": "Phone", "src": {"type": "model", "model": "test-model"}, "loc": [-0.12, 0.05, 0.0817], "rot": Q,
                     "scale": [1, 1, 1], "color": "#1e50f0"}]
    d["cameras"] = d["cameras"][:1]
    return d


ITEMS = {"c": {"type": "model3d", "scene": "3d/scenes/g/scene.json", "camera": "c00", "x": 0, "y": 0, "w": 560, "h": 420}}

# the live canvas's pixels kept under a name, and what changed between two of them, by what each pixel was in the first: the slab
# (light grey), the red box, the blue phone, the empty world (the corner's colour) or an edge between them
PX = """() => {
  window.__S = window.__S || {};
  window.__snap = name => { const c = document.querySelector('canvas.m3live'), g = document.createElement('canvas'); g.width = c.width; g.height = c.height;
    const x = g.getContext('2d'); x.drawImage(c, 0, 0);
    __S[name] = { w: g.width, h: g.height, d: x.getImageData(0, 0, g.width, g.height).data }; return [g.width, g.height]; };
  window.__kind = (d, i) => { const r = d[i], g = d[i + 1], b = d[i + 2];
    if (r > 150 && g > 150 && b > 150 && Math.abs(r - g) < 20 && Math.abs(g - b) < 20) return 'slab';
    if (r > g + 60 && r > b + 60) return 'red'; if (b > r + 60 && b > g + 30) return 'blue';
    const c = __S.base.d; if (Math.abs(r - c[0]) < 5 && Math.abs(g - c[1]) < 5 && Math.abs(b - c[2]) < 5) return 'world'; return 'edge'; };
  // a pixel's kind when its 8 neighbours are of the same kind, else an edge (antialiased, part one thing and part another)
  window.__core = (A, i) => { const k = __kind(A.d, i), p = i / 4, x = p % A.w, y = (p - x) / A.w;
    for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) {
      const X = x + dx, Y = y + dy; if (X < 0 || Y < 0 || X >= A.w || Y >= A.h) continue;
      if (__kind(A.d, (Y * A.w + X) * 4) !== k) return 'edge'; }
    return k; };
  window.__cmp = (a, b) => { const A = __S[a], B = __S[b]; if (A.w !== B.w || A.h !== B.h) return { size: [A.w, A.h, B.w, B.h] };
    const o = { changed: 0, world: 0, red: 0, blue: 0, slab: 0, edge: 0, slabRed: 0, slabBlue: 0, redShift: 0, blueShift: 0, lift: 0, liftN: 0, max: 0 };
    for (let i = 0; i < A.d.length; i += 4) {
      const dr = B.d[i] - A.d[i], dg = B.d[i + 1] - A.d[i + 1], db = B.d[i + 2] - A.d[i + 2], m = Math.max(Math.abs(dr), Math.abs(dg), Math.abs(db));
      if (!m) continue; o.changed++; o.max = Math.max(o.max, m); o[__core(A, i)]++; const k = __kind(A.d, i);
      if (k === 'slab') { if (dr - dg > 24) { o.slabRed++; o.redShift += dr - dg; } if (db - dr > 24) { o.slabBlue++; o.blueShift += db - dr; } }
      if (k === 'red') { o.lift += dr + dg + db; o.liftN++; } }
    o.redShift = o.slabRed ? o.redShift / o.slabRed : 0; o.blueShift = o.slabBlue ? o.blueShift / o.slabBlue : 0;
    o.lift = o.liftN ? o.lift / o.liftN : 0; return o; };
  // a pixel of the base image of this kind, nearest the middle of its kind's box, in page units inside the canvas
  window.__find = kind => { const A = __S.base, xs = [];
    for (let y = 0; y < A.h; y += 2) for (let x = 0; x < A.w; x += 2) if (__kind(A.d, (y * A.w + x) * 4) === kind) xs.push([x, y]);
    if (!xs.length) return null; const mx = xs.reduce((s, p) => s + p[0], 0) / xs.length, my = xs.reduce((s, p) => s + p[1], 0) / xs.length;
    const p = xs.reduce((b, q) => Math.hypot(q[0] - mx, q[1] - my) < Math.hypot(b[0] - mx, b[1] - my) ? q : b);
    const r = document.querySelector('canvas.m3live').getBoundingClientRect();
    return [r.left + (p[0] + 0.5) / A.w * r.width, r.top + (p[1] + 0.5) / A.h * r.height, xs.length]; };
  return true; }"""


def frame_now(frame, name, sel=None, hov=None):
    """one frame of the editor drawn now, kept under name, once the pick and the hover are these ids (None: nothing); its time in ms"""
    frame.wait_for_function("([s, h]) => import('/plugins/3d/engine.js').then(m => { const i = m.liveInfo(); return i.selected === s && i.hovered === h; })",
                            arg=[sel, hov], timeout=10000)
    frame.wait_for_timeout(100)
    # a slow software-GL frame may have stopped the editor («Continue»): it goes on, pressed in the page so the mouse stays where it is
    frame.evaluate("() => { const b = document.querySelector('.m3pause [data-go]'); if (b) b.click(); }")
    ms = frame.evaluate("() => import('/plugins/3d/engine.js').then(m => m.liveFrame())")
    frame.evaluate("(n) => __snap(n)", name)
    return ms


def to_page(frame, page, xy):
    """a point of the board's frame in the page (the canvas is in an iframe)"""
    b = frame.frame_element().bounding_box()
    return b["x"] + xy[0], b["y"] + xy[1]


@pytest.mark.parametrize("engine", ENGINES)
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_the_pick_shows_whole_through_what_is_in_front_without_an_outline(tmp_path, engine, theme):
    port, lib, stop = board_server(tmp_path, ITEMS, {"g": scene()}, lang="en")
    try:
        with sync_playwright() as p:
            browser, page, frame, errors = open_board(p, engine, port, theme)
            frame.evaluate("() => localStorage.removeItem('cv.m3.hl')")
            open_editor(frame, "c"); settle(frame)
            frame.evaluate(PX)
            # the mouse over the card's empty world, left of the phone and clear of the card's corner squares: nothing under it
            c = frame.locator("canvas.m3live").bounding_box(); away = (c["x"] + c["width"] * 0.15, c["y"] + c["height"] * 0.5)
            page.mouse.move(*away)
            # software GL in Chromium: the editor's guard may coarsen the view after its first slow frames, the size settles first
            # (and asks whether to go on: yes, so a slow frame never stops the test's frames)
            # (the button's click moves the mouse, so it happens here, before any hover)
            for _ in range(14):
                frame.evaluate("() => import('/plugins/3d/engine.js').then(m => m.liveFrame())"); go_on(frame)
            page.mouse.move(*away)
            frame_now(frame, "base"); shot(page, f"ghost-0-nothing-{theme}-{engine}")
            red, blue, slab = (frame.evaluate("(k) => __find(k)", k) for k in ("red", "blue", "slab"))
            assert red and blue and slab and red[2] > 100 and blue[2] > 100 and slab[2] > 800, ("a slab, a red box and a blue phone", red, blue, slab)

            # 1. under the mouse: the red box shows faintly through the slab and its visible part is lifted; nothing outside the objects
            page.mouse.move(*to_page(frame, page, red[:2]))
            frame_now(frame, "hover", hov="back"); shot(page, f"ghost-1-hover-{theme}-{engine}")
            h = frame.evaluate("() => __cmp('base', 'hover')")
            assert "size" not in h, ("the view kept its size", h)
            assert h["slabRed"] > 300 and h["world"] <= 6, ("the hovered box shows through the slab, no outline", h)
            assert h["liftN"] > 100 and h["lift"] > 6, ("the hovered box's visible part is lifted", h)

            # 2. picked: stronger through the slab, the visible part exactly the render, still nothing outside the objects
            page.mouse.click(*to_page(frame, page, red[:2]))
            frame.wait_for_function("() => import('/plugins/3d/engine.js').then(m => m.liveInfo().selected === 'back')", timeout=10000)
            page.mouse.move(*away)
            frame_now(frame, "pick", sel="back"); shot(page, f"ghost-2-picked-{theme}-{engine}")
            s = frame.evaluate("() => __cmp('base', 'pick')")
            assert s["slabRed"] > 300 and s["world"] <= 6 and s["red"] <= 6, ("the pick shows through the slab, no outline, its visible part as rendered", s)
            assert s["redShift"] > h["redShift"] * 1.4, ("a pick shows stronger than a hover", s["redShift"], h["redShift"])
            assert s["slabBlue"] == 0, ("only the pick shows", s)

            # 3. the hidden interface (⌘.): the bare render, no ghost
            page.keyboard.press("Meta+Period"); frame.wait_for_timeout(500)
            frame_now(frame, "bare", sel="back")
            assert frame.evaluate("() => __cmp('base', 'bare')")["slabRed"] == 0
            page.keyboard.press("Meta+Period"); frame.wait_for_timeout(500)

            # 4. two picked (the box and the phone, a selection of many): both show through the slab
            frame.evaluate("() => import('/plugins/3d/engine.js').then(m => m.liveSelect(['back', 'phone']))")
            frame_now(frame, "multi", sel="back"); shot(page, f"ghost-3-multi-{theme}-{engine}")
            m = frame.evaluate("() => __cmp('base', 'multi')")
            assert m["slabRed"] > 300 and m["slabBlue"] > 300 and m["world"] <= 6, ("both picks show through the slab", m)

            # 5. the phone picked by its row in the tree: all its parts show through the slab, as many pixels as a pick of the phone
            frame.click(".m3l .row[data-u]:has-text('Phone')"); page.mouse.move(*away)
            frame_now(frame, "tree", sel="phone"); shot(page, f"ghost-4-tree-{theme}-{engine}")
            t = frame.evaluate("() => __cmp('base', 'tree')")
            assert t["slabBlue"] > 300 and t["slabRed"] == 0 and t["world"] <= 6, ("the phone's parts show through the slab", t)

            # 6. nothing picked (a click on the empty world): the very same pixels as before
            page.mouse.click(*away)   # a click on the empty world drops the pick
            frame.wait_for_function("() => import('/plugins/3d/engine.js').then(m => !m.liveInfo().selected)", timeout=10000)
            frame_now(frame, "after"); shot(page, f"ghost-5-after-{theme}-{engine}")
            a = frame.evaluate("() => __cmp('base', 'after')")
            assert a["changed"] == 0, ("deselected, the view is what it was", a)

            # 7. the Scene panel: Ghost by default; Outline brings the pink outline back around the pick
            sel = frame.locator(".m3r .dialkit-select-trigger", has_text="Selection highlight")
            assert "Ghost" in sel.text_content(), sel.text_content()
            sel.click(); frame.locator(".dialkit-select-option", has_text="Outline").first.click(); frame.wait_for_timeout(300)
            assert frame.evaluate("() => localStorage.getItem('cv.m3.hl')") == "outline"
            frame.evaluate("() => import('/plugins/3d/engine.js').then(m => m.liveSelect(['back']))")
            frame_now(frame, "outline", sel="back"); shot(page, f"ghost-6-outline-{theme}-{engine}")
            o = frame.evaluate("() => __cmp('base', 'outline')")
            # (the line crosses the slab only along the box's edge; the ghost fills the slab where the box is behind it)
            assert o["world"] > 30 and o["slab"] < s["slab"] / 3, ("the outline: a pink line around the pick, no ghost over the slab", o, s["slab"])
            frame.evaluate("() => localStorage.removeItem('cv.m3.hl')")
            assert not errors, errors
            browser.close()
    finally:
        stop()


# what the canvas holds over Blender's frame: the pixels it draws (alpha above 0), by what each was in the three.js view before
OVER = """(name) => { const A = __S.base, B = __S[name], o = { drawn: 0, world: 0, slab: 0, red: 0, blue: 0, edge: 0 };
  for (let i = 0; i < B.d.length; i += 4) if (B.d[i + 3] > 0) { o.drawn++; o[__core(A, i)]++; }
  return o; }"""
BLENDER = """() => { const img = document.querySelector('.plg-live img.m3bimg'), g = document.createElement('canvas'); g.width = 64; g.height = 48;
  const x = g.getContext('2d'); x.fillStyle = '#3d5a73'; x.fillRect(0, 0, 64, 48); img.src = g.toDataURL(); img.hidden = false; return true; }"""


@pytest.mark.parametrize("engine", ENGINES)
def test_over_a_blender_frame_the_canvas_draws_only_the_ghost_and_the_gizmo(tmp_path, engine):
    """EEVEE or Cycles at rest: Blender's frame (img.m3bimg, blender.js) covers the live view. The canvas comes over it, empty, and
    draws only the ghost of the hidden part of the pick (and a hover's lift), where three.js has them with the same camera, and the
    gizmo of a tool on top. A stand-in picture plays Blender's frame; the studio's folder is an empty temporary one"""
    d = scene(); d["studio"] = {"folder": str(tmp_path / "studio"), "colour": "test", "look": "current", "angles": {"c00": {"look": "T01", "view": "v01"}}}
    port, lib, stop = board_server(tmp_path, ITEMS, {"g": d}, lang="en")
    try:
        with sync_playwright() as p:
            browser, page, frame, errors = open_board(p, engine, port, "dark")
            open_editor(frame, "c"); settle(frame); frame.evaluate(PX)
            c = frame.locator("canvas.m3live").bounding_box(); away = (c["x"] + c["width"] * 0.15, c["y"] + c["height"] * 0.5)
            page.mouse.move(*away)
            for _ in range(14):
                frame.evaluate("() => import('/plugins/3d/engine.js').then(m => m.liveFrame())"); go_on(frame)
            page.mouse.move(*away)
            frame_now(frame, "base")
            red = frame.evaluate("() => __find('red')")
            frame.evaluate(BLENDER)
            frame.wait_for_function("() => getComputedStyle(document.querySelector('canvas.m3live')).zIndex === '2'", timeout=10000)
            frame_now(frame, "over0")
            assert frame.evaluate(OVER, "over0")["drawn"] == 0, "nothing picked: the canvas is clear over Blender's frame"
            page.mouse.move(*to_page(frame, page, red[:2]))
            frame_now(frame, "overhover", hov="back")
            h = frame.evaluate(OVER, "overhover")
            assert h["red"] > 100 and h["slab"] > 300 and h["world"] == 0 and h["blue"] == 0, ("the hover: its lift and its ghost, nothing else", h)
            # a click starts a camera turn, which hides Blender's frame until it is the view's again (blender.js): it is shown again here
            page.mouse.click(*to_page(frame, page, red[:2])); page.mouse.move(*away); frame.evaluate(BLENDER)
            frame.wait_for_function("() => getComputedStyle(document.querySelector('canvas.m3live')).zIndex === '2'", timeout=10000)
            frame_now(frame, "overpick", sel="back"); shot(page, f"ghost-7-over-blender-picked-{engine}")
            s = frame.evaluate(OVER, "overpick")
            assert s["slab"] > 300 and s["red"] == 0 and s["world"] == 0 and s["blue"] == 0, ("the pick: only the ghost of its hidden part", s)
            # its edge against the world: a pixel drawn next to the world and away from the slab would be a fringe, a line around it
            fringe = frame.evaluate("""() => { const A = __S.base, B = __S.overpick; let n = 0;
              const near = (i, k) => { const p = i / 4, x = p % A.w, y = (p - x) / A.w;
                for (let dy = -2; dy <= 2; dy++) for (let dx = -2; dx <= 2; dx++) { const X = x + dx, Y = y + dy;
                  if (X >= 0 && Y >= 0 && X < A.w && Y < A.h && __kind(A.d, (Y * A.w + X) * 4) === k) return true; } return false; };
              for (let i = 0; i < B.d.length; i += 4) if (B.d[i + 3] > 0 && near(i, 'world') && !near(i, 'slab')) n++; return n; }""")
            assert fringe == 0, ("no fringe along the pick's visible edges", fringe)
            # the Move tool: its gizmo is drawn on top as well
            page.keyboard.press("g")
            frame.wait_for_function("() => import('/plugins/3d/engine.js').then(m => m.liveInfo().attached)", timeout=10000)
            frame_now(frame, "overgizmo", sel="back"); shot(page, f"ghost-8-over-blender-gizmo-{engine}")
            g = frame.evaluate(OVER, "overgizmo")
            assert g["red"] + g["world"] > 50 and g["slab"] >= s["slab"] - 50, ("the gizmo over Blender's frame, the ghost still there", g)
            # Blender's frame gone (the camera turns): the canvas goes back under, the full view again
            frame.evaluate("() => { document.querySelector('.plg-live img.m3bimg').hidden = true; }")
            frame.wait_for_function("() => getComputedStyle(document.querySelector('canvas.m3live')).zIndex !== '2'", timeout=10000)
            assert not errors, errors
            browser.close()
    finally:
        stop()
