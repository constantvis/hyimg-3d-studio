"""3D Studio wears its colour (owner 2026-10-09, «конечно» to «3D Studio и Dev Studio пока остаются синими. Дать им их цвета?»), as Image
Studio wears its purple (hyimg-frames 6e04f1a, tests/test_studio_dock.py there): inside the studio the chosen 3D segment of the dock's
switch, a checked box, the picked layer row, the tool in hand and the primary Save are in 3D Studio's pink (--pink), Save with white words,
Cancel as it was; back on the board the Board segment is the selection's blue again. Chromium, dark, the classic look (where the
selection is blue).
"""
from playwright.sync_api import sync_playwright

from test_canvas_3d import SITE2, board_server, go_on

CARD = {"type": "model3d", "scene": "3d/scenes/a/scene.json", "camera": "jo1wd256", "x": 0, "y": 0, "w": 500, "h": 500}
# a colour expression as the page computes it: the same notation as getComputedStyle gives for a real element
PROBE = """([v, prop]) => { const p = document.createElement('i'); p.style.setProperty(prop, v); document.body.append(p);
  const c = getComputedStyle(p).getPropertyValue(prop); p.remove(); return c; }"""
SEG = "() => { const b = document.querySelector('#dock #modes > button[aria-pressed=true]'); return [b.dataset.mode, getComputedStyle(b).color]; }"
BTN = "(s) => { const c = getComputedStyle(document.querySelector(s)); return [c.backgroundColor, c.color]; }"


def settle(page, want):
    """the chosen segment and its colour once it has eased (.2 s from whenever the switch caught up), or what it is after 3 s"""
    try: page.wait_for_function(f"(w) => JSON.stringify(({SEG})()) === JSON.stringify(w)", arg=want, timeout=3000)
    except Exception: pass
    assert page.evaluate(SEG) == want, page.evaluate(SEG)


def test_3d_studio_wears_its_colour(tmp_path):
    port, lib, stop = board_server(tmp_path, {"c": dict(CARD)}, {"a": SITE2})
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            errors = []; page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(f"http://127.0.0.1:{port}/canvas.html")
            page.wait_for_function("() => typeof PLGST !== 'undefined' && PLGST.some(p => p.name === '3d' && p.ok)", timeout=20000)
            page.evaluate("() => { setPref('theme', 'dark'); renderBg(); }")
            assert page.evaluate("() => [document.documentElement.dataset.theme, document.documentElement.dataset.ui]") == ["dark", "classic"]
            pink, blue = page.evaluate(PROBE, ["#ff4fa3", "color"]), page.evaluate(PROBE, ["var(--sel)", "color"])
            assert pink != blue and page.evaluate(PROBE, ["var(--pink)", "color"]) == pink, (pink, blue)

            page.dblclick(".plg[data-id=c]", position={"x": 30, "y": 30}); page.wait_for_selector(".m3r .hy-slider", timeout=60000)
            page.wait_for_timeout(1200); go_on(page)
            # the switch's chosen segment: 3D Studio's pink
            settle(page, ["3d", pink])
            # a checked box (the layer list's «all nodes»), on
            page.click(".m3l .opts input[data-raw]"); page.wait_for_timeout(200)
            assert page.evaluate("() => { const i = document.querySelector('.m3l .opts input[data-raw]'); return [i.checked, getComputedStyle(i).accentColor]; }") == [True, pink]
            page.click(".m3l .opts input[data-raw]"); page.wait_for_timeout(200)
            # the picked layer row: a fill and a line of the pink, the app's selected row
            page.click(".m3l .row[data-u]"); page.wait_for_selector(".m3l .row.sel", timeout=5000)
            row = page.evaluate("() => getComputedStyle(document.querySelector('.m3l .row.sel')).backgroundColor")
            assert row == page.evaluate(PROBE, ["color-mix(in srgb, #ff4fa3 14%, transparent)", "background-color"]), row
            # the tool in hand in the dock and Save top right: filled with the pink, white on it; Cancel as it was
            page.click('#dock .plgdock [data-tool="translate"]'); page.wait_for_timeout(300)
            assert page.evaluate(BTN, '#dock .plgdock [data-tool="translate"]') == [pink, "rgb(255, 255, 255)"]
            assert page.evaluate(BTN, "hy-studio-actions [data-a=save]") == [pink, "rgb(255, 255, 255)"]
            assert page.evaluate(BTN, "hy-studio-actions [data-a=cancel]")[0] != pink
            # back on the board: Board chosen, in the selection's blue
            page.click("hy-studio-actions [data-a=save]"); page.wait_for_function("() => !document.querySelector('.plg-live')", timeout=20000)
            settle(page, ["board", blue])
            assert not errors, errors
            browser.close()
    finally:
        stop()
