"""⌘Z and ⇧⌘Z in the 3D studio (owner 2026-10-07: «cmd + z не работает в 3D studio, пока я там редачу»). One gesture is one step: a
slider dragged in the Scene panel, the camera turned (⌥-drag), a light hidden by its eye in the layer list, a new camera from the view
(which the card also switches to). ⌘Z takes each back in turn and ⇧⌘Z brings it again, wherever the focus is after the gesture (the
slider keeps it, the list's button keeps it); the 3D dock's ↶ ↷ do the same. After «Save» the whole session is one step on the board.
The studio's scene is read in memory (the engine's docOf): nothing is written to scene.json while the studio is open, and with only the
card's own camera changed «Save» leaves it as it was (the card keeps its view, item.view). Chromium and WebKit.

  HYIMG_REPO=<Hyimg checkout> python3 -m pytest tests/test_studio_undo.py
"""
import json, math, os, time
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from test_canvas_3d import SITE2, board_server, go_on

WEBKIT = any(Path(os.path.expanduser("~/Library/Caches/ms-playwright")).glob("webkit-*"))


DOC = "() => import('/plugins/3d/engine.js').then(m => m.docOf('3d/scenes/a/scene.json'))"


def wait_doc(page, cond, t=8):
    for _ in range(int(t * 10)):
        d = page.evaluate(DOC)
        if d and cond(d): return d
        page.wait_for_timeout(100)
    raise AssertionError(json.dumps(page.evaluate(DOC))[:600])


def slider(page, name, to):
    b = page.locator(".m3r .hy-slider").filter(has_text=name).first.bounding_box(); y = b["y"] + b["height"] / 2
    page.mouse.move(b["x"] + b["width"] * 0.6, y); page.mouse.down()
    for i in range(1, 9): page.mouse.move(b["x"] + b["width"] * (0.6 + (to - 0.6) * i / 8), y); page.wait_for_timeout(40)
    page.mouse.up(); page.wait_for_timeout(600); go_on(page)   # a slow software renderer pauses the view: on


def orbit(page):   # ⌥ + drag turns the camera in every tool
    go_on(page)
    b = page.locator("canvas.m3live").bounding_box(); x, y = b["x"] + b["width"] * 0.3, b["y"] + b["height"] * 0.5
    page.keyboard.down("Alt"); page.mouse.move(x, y); page.mouse.down()
    for i in range(1, 9): page.mouse.move(x + 14 * i, y + 3 * i); page.wait_for_timeout(30)
    page.mouse.up(); page.keyboard.up("Alt"); page.wait_for_timeout(600); go_on(page)


@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_cmd_z_takes_back_the_studios_steps(tmp_path, engine):
    if engine == "webkit" and not WEBKIT: pytest.skip("no Playwright WebKit")
    item = {"type": "model3d", "scene": "3d/scenes/a/scene.json", "camera": "jo1wd256", "x": 0, "y": 0, "w": 500, "h": 500}
    port, lib, stop = board_server(tmp_path, {"c": item}, {"a": SITE2})
    scene = lib / "3d/scenes/a/scene.json"; raw0 = scene.read_bytes()
    cam0 = lambda d: next(c for c in d["cameras"] if c["id"] == "jo1wd256")
    try:
        with sync_playwright() as p:
            browser = p.webkit.launch() if engine == "webkit" else p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            errors = []; page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(f"http://127.0.0.1:{port}/canvas.html")
            page.wait_for_function("() => typeof PLGST !== 'undefined' && PLGST.some(p => p.name === '3d' && p.ok)", timeout=20000)
            page.wait_for_timeout(1500)
            steps0 = page.evaluate("() => past.length")
            page.dblclick(".plg[data-id=c]"); page.wait_for_selector(".m3r .hy-slider", timeout=60000); page.wait_for_timeout(1500); go_on(page)
            lens0 = SITE2["cameras"][0]["lens"]

            # a slider: one drag, one step, the focus left where the drag left it
            slider(page, "Объектив", 0.25)
            lens1 = wait_doc(page, lambda d: abs(cam0(d)["lens"] - lens0) > 1)["cameras"][0]["lens"]
            page.keyboard.press("Meta+z"); wait_doc(page, lambda d: abs(cam0(d)["lens"] - lens0) < 1e-6)
            page.keyboard.press("Meta+Shift+z"); wait_doc(page, lambda d: abs(cam0(d)["lens"] - lens1) < 1e-6)

            # the camera turned: one step
            loc1 = cam0(page.evaluate(DOC))["loc"]
            orbit(page)
            wait_doc(page, lambda d: math.dist(cam0(d)["loc"], loc1) > 1e-3)
            page.keyboard.press("Meta+z"); wait_doc(page, lambda d: math.dist(cam0(d)["loc"], loc1) < 1e-6 and abs(cam0(d)["lens"] - lens1) < 1e-6)

            # a light hidden by its eye in the list
            page.locator(".m3l .row", has_text="Ключевой").first.locator("[data-eye]").click(); page.wait_for_timeout(400)
            wait_doc(page, lambda d: d["lights"][0].get("hidden"))
            page.keyboard.press("Meta+z"); wait_doc(page, lambda d: not d["lights"][0].get("hidden"))
            page.keyboard.press("Meta+Shift+z"); wait_doc(page, lambda d: d["lights"][0].get("hidden"))
            page.keyboard.press("Meta+z"); wait_doc(page, lambda d: not d["lights"][0].get("hidden"))

            # a new camera from this view: the scene gets it and the card switches to it; one step takes back both
            page.locator(".m3r button", has_text="Новая камера из этого вида").first.click(); page.wait_for_timeout(600)
            wait_doc(page, lambda d: len(d["cameras"]) == 2)
            assert page.evaluate("() => board.items.c.camera") != "jo1wd256"
            page.keyboard.press("Meta+z"); wait_doc(page, lambda d: len(d["cameras"]) == 1)
            page.wait_for_function("() => board.items.c.camera === 'jo1wd256'")
            # the dock's ↷ and ↶ drive the same steps
            page.click(".m3t [data-a=redo]"); wait_doc(page, lambda d: len(d["cameras"]) == 2)
            page.wait_for_function("() => board.items.c.camera !== 'jo1wd256'")
            page.click(".m3t [data-a=undo]"); wait_doc(page, lambda d: len(d["cameras"]) == 1)
            page.wait_for_function("() => board.items.c.camera === 'jo1wd256'")
            # back to the opening, step by step: the lens, then nothing more
            page.keyboard.press("Meta+z"); wait_doc(page, lambda d: abs(cam0(d)["lens"] - lens0) < 1e-6)
            page.keyboard.press("Meta+Shift+z"); wait_doc(page, lambda d: abs(cam0(d)["lens"] - lens1) < 1e-6)

            assert scene.read_bytes() == raw0, "nothing written while the studio is open"
            # «Save»: the card keeps its view, the session is one step on the board, and scene.json (only the card's camera changed) stays
            page.click("hy-studio-actions [data-a=save]"); page.wait_for_function("() => !document.querySelector('.plg-live')", timeout=20000)
            v = page.evaluate("() => board.items.c.view")
            assert v and abs(v["lens"] - lens1) < 1e-6, v
            assert page.evaluate("() => past.length") == steps0 + 1
            page.wait_for_timeout(800); assert scene.read_bytes() == raw0, "only the card's view changed: scene.json is not written"
            page.keyboard.press("Meta+z"); page.wait_for_function("() => !board.items.c.view || board.items.c.view.lens !== %r" % lens1)
            assert not errors, errors
            browser.close()
    finally:
        stop()
