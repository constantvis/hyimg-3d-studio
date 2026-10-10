"""Space moves the view in 3D Studio as it does on the board; ⌥ + drag and the middle button turn the camera (owner 2026-10-10 on round 18,
r18-dock.html question 2, ★ yes: «Пробел в 3D двигает вид, как на доске, вращение на ⌥ и средней кнопке»). From 2026-10-07 until then
Space + drag turned the camera, like ⌥. A pan keeps the camera's direction and shifts it; a turn changes the direction. The card's camera
in the open studio (its scene in memory) is read after each drag. Chromium, dark."""
import math

from playwright.sync_api import sync_playwright

from test_canvas_3d import SITE2, board_server, go_on

CARD = {"type": "model3d", "scene": "3d/scenes/a/scene.json", "camera": "jo1wd256", "x": 0, "y": 0, "w": 500, "h": 500}
CAM = "() => import('/plugins/3d/engine.js').then(m => { const c = m.docOf('3d/scenes/a/scene.json').cameras[0]; return [c.loc, c.rot]; })"


def drag(page, key=None, button="left"):
    r = page.locator("canvas.m3live").bounding_box(); x, y = r["x"] + r["width"] * 0.35, r["y"] + r["height"] * 0.6
    page.mouse.move(x, y)
    if key: page.keyboard.down(key)
    page.mouse.down(button=button); page.mouse.move(x + 90, y + 20, steps=8); page.mouse.up(button=button)
    if key: page.keyboard.up(key)
    page.wait_for_timeout(400); go_on(page)


def test_space_moves_the_view_alt_and_the_middle_button_turn_it(tmp_path):
    port, lib, stop = board_server(tmp_path, {"c": dict(CARD)}, {"a": SITE2}, lang="en")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
            page = browser.new_page(viewport={"width": 1600, "height": 1000}, color_scheme="dark")
            errors = []; page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(f"http://127.0.0.1:{port}/canvas.html")
            page.wait_for_function("() => typeof PLGST !== 'undefined' && PLGST.some(p => p.name === '3d' && p.ok)", timeout=20000)
            page.dblclick(".plg[data-id=c]", position={"x": 30, "y": 30}); page.wait_for_selector(".m3r .hy-slider", timeout=60000)
            page.wait_for_function("() => /Orbit/.test([...document.querySelectorAll('hy-keyhint')].map(h => h.textContent).join(' | '))", timeout=8000)
            # the Hint bar as it opens: ⌥ «Orbit», Space no more (it said «⌥ / Space Orbit»)
            orbit = page.evaluate("() => [...document.querySelectorAll('hy-keyhint .kh-i[data-id=orbit] hy-kbd')].map(k => k.textContent)")
            page.wait_for_timeout(1200); go_on(page)
            # the board's camera settles first: the studio flies its card between the panels, and again once the library has folded (lesson 20)
            page.wait_for_timeout(2200); cam0 = None
            for _ in range(40):
                c = page.evaluate("() => ({ ...cam })")
                if c == cam0: break
                cam0 = c; page.wait_for_timeout(150)
            loc0, rot0 = page.evaluate(CAM)
            drag(page, " ")   # Space + drag: the view moves, the camera looks the same way
            loc1, rot1 = page.evaluate(CAM)
            assert math.dist(loc0, loc1) > 1e-4, "Space did not move the view"
            assert max(abs(a - b) for a, b in zip(rot0, rot1)) < 1e-4, ("Space turned the camera", rot0, rot1)
            assert page.evaluate("() => ({ ...cam })") == cam0, "Space moved the board, not the studio's view"
            drag(page, "Alt")   # ⌥ + drag: the camera turns
            loc2, rot2 = page.evaluate(CAM)
            assert max(abs(a - b) for a, b in zip(rot1, rot2)) > 1e-3, "⌥ did not turn the camera"
            drag(page, None, "middle")   # the middle button: the camera turns
            loc3, rot3 = page.evaluate(CAM)
            assert max(abs(a - b) for a, b in zip(rot2, rot3)) > 1e-3, "the middle button did not turn the camera"
            assert orbit == ["⌥"], orbit
            # the Scene panel's footnote says so
            foot = page.evaluate("() => document.querySelector('.m3hint').textContent")
            assert "Space + drag" in foot and "moves the view" in foot, foot
            assert not errors, errors
            browser.close()
    finally:
        stop()
