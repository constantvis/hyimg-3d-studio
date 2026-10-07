"""The layer list's Objects / Lights / Cameras as one stack, on a scene like the owner's (87 objects, 3 lights, 18 cameras). Owner
2026-10-06, three screenshots:

- «когда я двигаю за одну из этих, нижняя должна тоже с ней идти»: a handle dragged down grows the section above it, Lights keeps its
  size and rides along, Cameras gives the room; up is the mirror;
- «если я какое-то складываю, то у других появляется больше пространства ... оно вниз не съехало»: folded Cameras goes to the panel's
  bottom, Lights hugs its three rows, Objects takes the room; unfolded, Cameras gets its size back;
- «странное расстояние, когда в сложенной позиции»: a handle takes no room, and there is none next to a folded section.
A double click on a handle makes the sections automatic again, a reload keeps what was set. Chromium and WebKit, the app's page with the
canvas in its frame. The layout itself is unit-tested without a page (tests/unit/js/sections.test.mjs).

  HYIMG_REPO=<Hyimg checkout> python3 -m pytest tests/test_outliner_sections.py
  M3_SHOTS=<folder> also saves screenshots
"""
import json, os

import pytest
from playwright.sync_api import sync_playwright

from test_canvas_3d import board_server, glb
from test_3d_files import ENGINES, open_board
from test_editor_ui import open_editor

SHOTS = os.environ.get("M3_SHOTS")


def shot(page, name):
    if SHOTS: os.makedirs(SHOTS, exist_ok=True); page.screenshot(path=os.path.join(SHOTS, name + ".png"))


def owner_scene():
    q = [1, 0, 0, 0]
    objects = [{"id": f"o{i:03d}", "name": f"Part {i + 1}", "src": {"type": "prim", "shape": "box", "size": [0.02, 0.02, 0.02]},
                "loc": [(i % 10) * 0.03 - 0.15, (i // 10) * 0.03 - 0.15, 0.01], "rot": q, "scale": [1, 1, 1]} for i in range(87)]
    lights = [{"id": f"l{i}", "name": n, "type": "area", "loc": [0.5 - i * 0.4, -0.6, 0.6], "rot": [0.83, 0.45, -0.16, -0.3], "color": [1, 1, 1], "power": 20,
               "size": 0.6, "size_y": 0.6, "shape": "SQUARE"} for i, n in enumerate(["Key", "Fill", "Rim"])]
    cameras = [{"id": f"c{i:02d}", "name": f"View {i + 1}", "loc": [0, -1.2, 0.3], "rot": [0.77, 0.63, 0, 0], "lens": 50, "sensor": 36, "fit": "AUTO",
                "clip": [0.01, 100]} for i in range(18)]
    return {"format": "hyimg-scene/1", "rev": 1, "render": {"x": 1600, "y": 1200}, "world": {"color": [0.18, 0.18, 0.18], "strength": 1},
            "objects": objects, "lights": lights, "cameras": cameras, "active_camera": "c00"}


ITEMS = {"c": {"type": "model3d", "scene": "3d/scenes/big/scene.json", "camera": "c00", "x": 0, "y": 0, "w": 640, "h": 480}}

# each shown section: its title's top and the end of its rows, from the top of the stack; the rows' own height; the handles that work
GEO = """() => { const tr = document.querySelector('.m3l .tr').getBoundingClientRect(), r = x => Math.round(x * 2) / 2, o = { tr: r(tr.height) };
  for (const s of document.querySelectorAll('.m3l .ms')) { if (s.hidden) continue;
    const t = s.querySelector('.msh').getBoundingClientRect(), b = s.querySelector('.msb').getBoundingClientRect();
    o[s.dataset.s] = { top: r(t.top - tr.top), head: r(t.height), h: r(b.height), end: r(Math.max(t.bottom, b.bottom) - tr.top), rows: s.querySelector('.msi').offsetHeight,
      shut: s.classList.contains('shut'), fixed: s.classList.contains('fixed') }; }
  o.handles = [...document.querySelectorAll('.m3l .msp')].filter(x => !x.hidden && x.getClientRects().length && getComputedStyle(x).pointerEvents !== 'none').map(x => x.dataset.before);
  return o; }"""


def near(a, b, tol=1.0): return abs(a - b) <= tol


def settle(frame):
    """the fold's .32 s curve has run (a software-GL frame of 87 objects can be slow, the animation clock with it)"""
    frame.wait_for_function("""() => !document.querySelector('.m3l .tr').classList.contains('glide')
      && !document.getAnimations().some(a => a.effect && a.effect.target && a.effect.target.classList && a.effect.target.classList.contains('msb'))""", timeout=15000)
    frame.wait_for_timeout(100)


# every height change that glides, with its curve: a drag must not glide, a fold glides along the app's curve
WATCH = """() => { window.__glides = []; document.querySelector('.m3l .tr').addEventListener('transitionrun', e => {
  if (e.propertyName === 'height' && e.target.classList.contains('msb')) __glides.push(getComputedStyle(e.target).transitionTimingFunction); }); }"""
GLIDES = "() => { const g = __glides; window.__glides = []; return g; }"


def drag(page, frame, below, dy):
    b = frame.locator(f".m3l .msp[data-before={below}]").bounding_box(); x, y = b["x"] + b["width"] / 2, b["y"] + b["height"] / 2
    page.mouse.move(x, y); page.mouse.down(); page.mouse.move(x, y + dy, steps=8); page.mouse.up(); frame.wait_for_timeout(150)


def fold(frame, k): frame.click(f".m3l .ms[data-s={k}] .msh"); settle(frame)


def stack_has_no_gaps(g):
    """each title starts where the section above it ends: a handle takes no room"""
    ks = [k for k in ("objects", "lights", "cameras") if k in g]
    for a, b in zip(ks, ks[1:]): assert near(g[b]["top"], g[a]["end"], 0.5), (a, b, g)


@pytest.fixture
def owner(tmp_path):
    port, lib, stop = board_server(tmp_path, ITEMS, {"big": owner_scene()}, lang="en")
    yield port
    stop()


@pytest.mark.parametrize("engine", ENGINES)
def test_the_sections_move_as_one_stack(owner, engine):
    with sync_playwright() as p:
        browser, page, frame, errors = open_board(p, engine, owner)
        open_editor(frame, "c"); frame.wait_for_function("() => document.querySelectorAll('.m3l .row[data-cam]').length === 18", timeout=30000); settle(frame)
        frame.evaluate(WATCH)
        g0 = frame.evaluate(GEO); shot(page, f"outliner-0-auto-{engine}")
        # automatic: Lights shows its three rows, Objects and Cameras share the rest, the stack fills the panel without gaps
        assert g0["lights"]["h"] == g0["lights"]["rows"] and near(g0["objects"]["h"], g0["cameras"]["h"]), g0
        assert near(g0["cameras"]["end"], g0["tr"]) and g0["handles"] == ["lights", "cameras"], g0
        stack_has_no_gaps(g0)

        # 1. the upper handle down by 60: Objects +60, Lights the same size and 60 lower, Cameras gives the room; nothing glides while dragging
        drag(page, frame, "lights", 60); settle(frame)
        assert frame.evaluate(GLIDES) == [], "a drag follows the pointer, it does not glide"
        g1 = frame.evaluate(GEO)
        assert near(g1["objects"]["h"], g0["objects"]["h"] + 60), (g0, g1)
        assert g1["lights"]["h"] == g0["lights"]["h"] and near(g1["lights"]["top"], g0["lights"]["top"] + 60), (g0, g1)
        assert near(g1["cameras"]["h"], g0["cameras"]["h"] - 60) and near(g1["cameras"]["end"], g1["tr"]), (g0, g1)
        stack_has_no_gaps(g1)
        shot(page, f"outliner-1-dragged-{engine}")
        # and up again: back where it was (the mirror)
        drag(page, frame, "lights", -60); g1b = frame.evaluate(GEO)
        for k in ("objects", "lights", "cameras"): assert near(g1b[k]["h"], g0[k]["h"]) and near(g1b[k]["top"], g0[k]["top"]), (k, g0, g1b)
        drag(page, frame, "lights", 60); g1 = frame.evaluate(GEO)

        # 2. Cameras folded: its title at the panel's bottom, Lights hugs its rows, Objects took the room, no handle next to Cameras; the
        #    rows close with the app's curve
        fold(frame, "cameras"); g2 = frame.evaluate(GEO)
        ease = frame.evaluate(GLIDES)
        assert len(ease) >= 2 and set(ease) == {"cubic-bezier(0.32, 0.72, 0, 1)"}, ("Cameras closes and Objects opens along the app's curve", ease)
        assert g2["cameras"]["shut"] and g2["cameras"]["h"] == 0 and near(g2["cameras"]["end"], g2["tr"]), g2
        assert g2["lights"]["h"] == g2["lights"]["rows"], ("no empty room inside Lights", g2)
        assert near(g2["objects"]["h"], g1["objects"]["h"] + g1["cameras"]["h"]), (g1, g2)
        assert g2["handles"] == ["lights"], g2
        stack_has_no_gaps(g2)
        shot(page, f"outliner-2-cameras-folded-{engine}")
        # unfolded: Cameras gets its size back
        fold(frame, "cameras"); g2b = frame.evaluate(GEO)
        for k in ("objects", "lights", "cameras"): assert near(g2b[k]["h"], g1[k]["h"]), (k, g1, g2b)

        # 3. Lights folded: no handle around it, the titles touch as any two titles do, Objects and Cameras share its room
        fold(frame, "lights"); g3 = frame.evaluate(GEO)
        assert g3["handles"] == [] and g3["lights"]["h"] == 0, g3
        assert near(g3["lights"]["top"], g3["objects"]["end"], 0.5) and near(g3["cameras"]["top"], g3["lights"]["top"] + g3["lights"]["head"], 0.5), g3
        assert near(g3["cameras"]["end"], g3["tr"]), g3
        shot(page, f"outliner-3-lights-folded-{engine}")
        fold(frame, "lights")

        # 4. a reload keeps the sizes and the folds
        fold(frame, "cameras"); g4 = frame.evaluate(GEO)
        page.reload(); page.wait_for_function("() => document.body.classList.contains('cv-on')")
        frame = None
        for _ in range(200):
            frame = next((f for f in page.frames if "/canvas" in f.url), None)
            if frame: break
            page.wait_for_timeout(100)
        frame.wait_for_function("() => typeof PLGST !== 'undefined' && PLGST.some(p => p.name === '3d' && p.ok)", timeout=30000)
        open_editor(frame, "c"); frame.wait_for_function("() => document.querySelectorAll('.m3l .row[data-cam]').length === 18", timeout=30000); settle(frame)
        g5 = frame.evaluate(GEO)
        for k in ("objects", "lights", "cameras"): assert near(g5[k]["h"], g4[k]["h"]) and g5[k]["shut"] == g4[k]["shut"], (k, g4, g5)
        fold(frame, "cameras")

        # 5. a double click on the upper handle: automatic again, as at the start
        frame.locator(".m3l .msp[data-before=lights]").dblclick(); settle(frame)
        g6 = frame.evaluate(GEO)
        for k in ("objects", "lights", "cameras"): assert near(g6[k]["h"], g0[k]["h"]) and not g6[k]["fixed"], (k, g0, g6)
        shot(page, f"outliner-4-auto-again-{engine}")
        assert not errors, errors
        browser.close()


def live_scene():
    """the owner's live panel (2026-10-07): one model whose tree is folded into one row, 3 lights, 18 cameras"""
    d = owner_scene()
    d["objects"] = [{"id": "shell", "name": "Vase", "src": {"type": "model", "model": "test-model"}, "loc": [0, 0, 0], "rot": [1, 0, 0, 0], "scale": [1, 1, 1]}]
    return d


@pytest.mark.parametrize("engine", ENGINES)
@pytest.mark.parametrize("tall", [1600, 1030])
def test_a_short_section_is_never_cut_while_the_rows_fit(tmp_path, engine, tall):
    """Owner 2026-10-07, dark, a panel of about 1470 px: Objects one row, Lights showed one of its 3 rows, Cameras all 18 with room left
    below. A size the panel kept from before the stack (both sides of an old drag) must not cut a section while there is room"""
    port, lib, stop = board_server(tmp_path, ITEMS, {"big": live_scene()}, lang="en")
    try:
        with sync_playwright() as p:
            browser, page, frame, errors = open_board(p, engine, port)
            page.set_viewport_size({"width": 1500, "height": tall})
            # what the panel kept: at 1600 the old drag's sizes (no v: dropped once), at 1030 the same sizes as the stack keeps them (v 2), which
            # the layout itself must not let cut Lights while there is room
            old = tall == 1600
            frame.evaluate("""(old) => localStorage.setItem('cv.m3.sections', JSON.stringify(Object.assign(old ? {} : { v: 2 }, { objects: { size: null, shut: false },
              lights: { size: 28, shut: false }, cameras: { size: 508, shut: false } })))""", old)
            open_editor(frame, "c"); frame.wait_for_function("() => document.querySelectorAll('.m3l .row[data-cam]').length === 18", timeout=30000); settle(frame)
            g = frame.evaluate(GEO); shot(page, f"outliner-live-{tall}-{engine}")
            for k in ("objects", "lights", "cameras"): assert g[k]["h"] == g[k]["rows"], (k, g)
            if old: assert not any(g[k]["fixed"] for k in ("objects", "lights", "cameras")), ("an old drag's sizes are dropped", g)
            assert g["objects"]["rows"] <= 40 and g["lights"]["rows"] == 88 and g["cameras"]["rows"] == 508, g
            stack_has_no_gaps(g)
            # a shorter panel: Cameras, the biggest, gives the room; Objects keeps its row, Lights its rows (automatic) or the size a
            # drag gave it (v 2): only room to spare goes past a size, a shortage takes from the biggest
            page.set_viewport_size({"width": 1500, "height": 620})
            frame.wait_for_function("(h) => document.querySelector('.m3l .tr').getBoundingClientRect().height < h - 100", arg=g["tr"], timeout=15000)
            frame.wait_for_function("() => { const tr = document.querySelector('.m3l .tr').getBoundingClientRect(), c = document.querySelector('.m3l .ms[data-s=cameras] .msb').getBoundingClientRect(); return c.bottom <= tr.bottom + 1; }", timeout=15000)
            settle(frame)
            g2 = frame.evaluate(GEO); shot(page, f"outliner-live-{tall}-then-620-{engine}")
            assert g2["lights"]["h"] == (88 if old else 28) and g2["objects"]["h"] == g2["objects"]["rows"] and g2["cameras"]["h"] < 508 and near(g2["cameras"]["end"], g2["tr"]), g2
            assert not errors, errors
            browser.close()
    finally:
        stop()



def shell_scene(lib):
    """the owner's Vase: one model of 87 parts (its tree folded into one row), 3 lights, 18 cameras"""
    m = lib / "3d/models/shell"; m.mkdir(parents=True)
    glb(m / "body.glb", [(f"part_{i:02d}", "resin", (0.01, 0.01, 0.01), ((i % 10) * 0.012, (i // 10) * 0.012, 0)) for i in range(87)])
    (m / "model.json").write_text(json.dumps({"title": "Vase", "height_m": 0.16, "parts": [{"role": "body", "file": "body.glb"}]}))
    d = owner_scene()
    d["objects"] = [{"id": "shell", "name": "Vase", "src": {"type": "model", "model": "shell"}, "loc": [0, 0, 0], "rot": [1, 0, 0, 0], "scale": [1, 1, 1]}]
    (lib / "3d/scenes/big/scene.json").write_text(json.dumps(d))


@pytest.fixture
def shell(tmp_path):
    port, lib, stop = board_server(tmp_path, ITEMS, {"big": owner_scene()}, lang="en")
    shell_scene(lib)
    yield port
    stop()


# the tree's rows that glide open or shut: every height transition of a wrapper of rows, with its curve
WATCH_KIDS = """() => { window.__kids = []; document.querySelector('.m3l .tr').addEventListener('transitionrun', e => {
  if (e.propertyName === 'height' && e.target.classList.contains('kids')) __kids.push(getComputedStyle(e.target).transitionTimingFunction); }); }"""
KIDS = "() => { const g = __kids; window.__kids = []; return g; }"
OBJ_ROWS = "() => document.querySelectorAll('.m3l .ms[data-s=objects] .msi .row').length"


@pytest.mark.parametrize("engine", ENGINES)
def test_a_tree_opens_smoothly_and_its_section_grows_under_the_handle(shell, engine):
    """Owner 2026-10-07: «когда раскладываешь объект, тоже нет плавной анимации. И если я что-то разложил, а потом тяну вниз, у меня должна
    быть возможность тянуть вниз, а я не могу, потому что оно зафиксировалось»"""
    with sync_playwright() as p:
        browser, page, frame, errors = open_board(p, engine, shell)
        page.set_viewport_size({"width": 1500, "height": 1200})
        open_editor(frame, "c"); frame.wait_for_function("() => document.querySelectorAll('.m3l .row[data-cam]').length === 18", timeout=30000); settle(frame)
        assert frame.evaluate(OBJ_ROWS) == 1
        frame.evaluate(WATCH_KIDS)
        # open the tree down to its 87 parts (the model, then its file's node): the rows glide open along the app's curve
        OPEN = ".m3l .ms[data-s=objects] .row.closed [data-open]"
        for _ in range(6):
            if frame.evaluate(OBJ_ROWS) > 80 or not frame.locator(OPEN).count(): break
            frame.evaluate(KIDS); frame.click(OPEN); settle(frame); frame.wait_for_timeout(300)
        assert frame.evaluate(OBJ_ROWS) >= 88, frame.evaluate("() => [...document.querySelectorAll('.m3l .ms[data-s=objects] .msi .row')].map(r => r.textContent.trim()).slice(0, 6)")
        kids = frame.evaluate(KIDS); assert kids == ["cubic-bezier(0.32, 0.72, 0, 1)"], kids
        assert frame.locator(".m3l .kids").count() == 0, "the wrapper goes once the rows are open"
        g1 = frame.evaluate(GEO); shot(page, f"outliner-tree-open-{engine}")
        assert g1["objects"]["rows"] > 2000 and g1["objects"]["h"] < g1["objects"]["rows"], g1
        # the handle under Objects pulled down 200 px: Objects grows 200 px, Lights rides along
        drag(page, frame, "lights", 200); g2 = frame.evaluate(GEO)
        assert near(g2["objects"]["h"], g1["objects"]["h"] + 200) and g2["lights"]["h"] == g1["lights"]["h"] and near(g2["lights"]["top"], g1["lights"]["top"] + 200), (g1, g2)
        # shut again: the rows glide shut, then the list has its one row
        frame.click(".m3l .ms[data-s=objects] .row [data-open]"); settle(frame); frame.wait_for_timeout(400)
        assert frame.evaluate(OBJ_ROWS) == 1 and frame.evaluate(KIDS) == ["cubic-bezier(0.32, 0.72, 0, 1)"]
        assert frame.locator(".m3l .kids").count() == 0
        assert not errors, errors
        browser.close()


IN_VIEW = """(sel) => { const r = document.querySelector(sel), b = r.closest('.msb').getBoundingClientRect(), x = r.getBoundingClientRect();
  return x.top >= b.top - 0.5 && x.bottom <= b.bottom + 0.5; }"""


@pytest.mark.parametrize("engine", ENGINES)
def test_a_section_squeezes_to_what_is_active_or_selected_in_it(owner, engine):
    """Owner 2026-10-07: Cameras squeezed to one row shows the active camera, «это отлично»; «у Lights почему-то он до конца не складывается,
    несмотря на то, что там ничего не выбрано, не активно». A section's least is its active and selected rows, else its title alone, open"""
    with sync_playwright() as p:
        browser, page, frame, errors = open_board(p, engine, owner)
        open_editor(frame, "c"); frame.wait_for_function("() => document.querySelectorAll('.m3l .row[data-cam]').length === 18", timeout=30000); settle(frame)
        # a camera in the middle of the list is the active one
        frame.dblclick(".m3l .row[data-cam=c09]"); frame.wait_for_timeout(800); settle(frame)
        assert frame.evaluate("() => board.items.c.camera") == "c09"
        # a light picked, then the lower handle pushed all the way up: Lights keeps the picked light's row
        frame.click(".m3l .row[data-u]:has-text('Fill')"); frame.wait_for_timeout(400); settle(frame)
        drag(page, frame, "cameras", -700); settle(frame); g = frame.evaluate(GEO)
        assert g["lights"]["h"] == 28 and frame.evaluate(IN_VIEW, ".m3l .ms[data-s=lights] .row.sel"), g
        # nothing picked: Lights glides down to its title alone and stays open
        page.keyboard.press("Escape"); frame.wait_for_timeout(100); settle(frame); g = frame.evaluate(GEO)
        assert g["lights"]["h"] == 0 and not g["lights"]["shut"], g
        shot(page, f"outliner-lights-squeezed-{engine}")
        # the upper handle pulled all the way down: Cameras keeps its active camera's row, in view
        drag(page, frame, "lights", 1500); settle(frame); g = frame.evaluate(GEO)
        assert g["cameras"]["h"] == 28 and frame.evaluate(IN_VIEW, ".m3l .row[data-cam=c09]"), g
        shot(page, f"outliner-cameras-squeezed-{engine}")
        assert not errors, errors
        browser.close()
