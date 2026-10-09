"""Each tool of the 3D studio does its own job (owner 2026-10-07: «неважно, какой инструмент я выбираю, все инструменты крутят почему-то,
кроме последнего, который двигает объект»). Chromium and WebKit, the scene read in the studio's memory:

- with nothing picked, Move says «Выдели объект» for a drag beside the object and the camera stays; Select's drag turns nothing;
- Move moves the phone by a drag on it, Rotate turns it, Scale makes it larger, the camera stays in each; ⌘Z takes the move back;
- ⌥ + drag turns the camera in every tool and leaves the object; the buttons say their keys, the Scene panel the camera's scheme.
"""
import math

import pytest
from playwright.sync_api import sync_playwright

from test_canvas_3d import SITE2, board_server, go_on
from test_studio_undo import DOC, WEBKIT

CARD = {"type": "model3d", "scene": "3d/scenes/a/scene.json", "camera": "jo1wd256", "x": 0, "y": 0, "w": 500, "h": 500}


def state(page):
    d = page.evaluate(DOC); return d["objects"][0], d["cameras"][0]


def drag(page, fx, fy, dx, dy, alt=False):
    go_on(page); b = page.locator("canvas.m3live").bounding_box(); x, y = b["x"] + b["width"] * fx, b["y"] + b["height"] * fy
    if alt: page.keyboard.down("Alt")
    page.mouse.move(x, y); page.mouse.down()
    for i in range(1, 9): page.mouse.move(x + dx * i / 8, y + dy * i / 8); page.wait_for_timeout(30)
    page.mouse.up()
    if alt: page.keyboard.up("Alt")
    page.wait_for_timeout(500); go_on(page)


def same(a, b, tol=1e-6): return math.dist(a, b) < tol


@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_each_tool_does_its_own_job_and_alt_turns_the_camera(tmp_path, engine):
    if engine == "webkit" and not WEBKIT: pytest.skip("no Playwright WebKit")
    port, lib, stop = board_server(tmp_path, {"c": dict(CARD)}, {"a": SITE2})
    try:
        with sync_playwright() as p:
            browser = p.webkit.launch() if engine == "webkit" else p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            errors = []; page.on("pageerror", lambda e: errors.append(str(e)))
            notes = []; page.expose_function("__note", lambda s: notes.append(s))
            page.goto(f"http://127.0.0.1:{port}/canvas.html")
            page.wait_for_function("() => typeof PLGST !== 'undefined' && PLGST.some(p => p.name === '3d' && p.ok)", timeout=20000)
            page.evaluate("() => { const t0 = window.hyToast; window.hyToast = (t, k, o) => { __note(String(t)); return t0 && t0(t, k, o); }; }")
            page.dblclick(".plg[data-id=c]", position={"x": 30, "y": 30}); page.wait_for_selector(".m3r .hy-slider", timeout=60000)
            page.wait_for_timeout(1200); go_on(page)
            assert "⌥ или пробел + перетаскивание" in page.locator(".m3r .m3hint").inner_text()
            titles = page.evaluate("() => Object.fromEntries([...document.querySelectorAll('.m3t [data-tool]')].map(b => [b.dataset.tool, b.title]))")
            assert [titles[k][-1] for k in ("select", "translate", "rotate", "scale", "smart")] == list("VGRST"), titles
            o0, c0 = state(page)

            # Select: a drag turns nothing
            drag(page, 0.15, 0.15, 120, 40)
            o, c = state(page); assert same(c["loc"], c0["loc"]) and same(o["loc"], o0["loc"]), "Select does not turn the camera"
            # Move with nothing picked, beside the object: a note, the camera stays
            page.click('.m3t [data-tool="translate"]'); page.keyboard.press("Escape") if page.evaluate("() => import('/plugins/3d/engine.js').then(m => m.liveInfo().selected)") else None
            drag(page, 0.12, 0.12, 120, 40)
            o, c = state(page); assert same(c["loc"], c0["loc"]) and any("Выдели объект" in n for n in notes), notes

            # Move: a drag on the phone moves it, the camera stays; ⌘Z takes it back
            drag(page, 0.5, 0.5, 90, -40)
            o1, c = state(page); assert not same(o1["loc"], o0["loc"], 1e-4) and same(c["loc"], c0["loc"]), (o0["loc"], o1["loc"])
            assert page.evaluate("() => import('/plugins/3d/engine.js').then(m => m.liveInfo().selected)") == o0["id"], "the dragged object is picked"
            page.keyboard.press("Meta+z"); page.wait_for_timeout(600)
            o, c = state(page); assert same(o["loc"], o0["loc"]), "⌘Z takes the move back"
            # Rotate: it turns, it stays in place
            page.click('.m3t [data-tool="rotate"]'); drag(page, 0.5, 0.5, 120, 0)
            o2, c = state(page); assert o2["rot"] != o0["rot"] and same(o2["loc"], o0["loc"], 1e-4) and same(c["loc"], c0["loc"]), o2
            page.keyboard.press("Meta+z"); page.wait_for_timeout(600)   # facing the camera again: its middle is under the pointer
            # Scale: up is larger
            page.click('.m3t [data-tool="scale"]'); drag(page, 0.5, 0.5, 0, -80)
            o3, c = state(page); assert o3["scale"][0] > o0["scale"][0] * 1.2 and same(c["loc"], c0["loc"]), o3["scale"]
            # ⌥ + drag: the camera in every tool, the object stays
            for tool in ("translate", "select", "smart"):
                page.click(f'.m3t [data-tool="{tool}"]'); o_, c_ = state(page)
                drag(page, 0.5, 0.5, 100, 20, alt=True)
                o, c = state(page); assert not same(c["loc"], c_["loc"], 1e-4) and o == o_, (tool, c_["loc"], c["loc"])
            page.click("hy-studio-actions [data-a=save]"); page.wait_for_function("() => !document.querySelector('.plg-live')", timeout=20000)
            assert not errors, errors
            browser.close()
    finally:
        stop()
