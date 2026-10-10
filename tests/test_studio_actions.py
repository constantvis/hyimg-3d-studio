"""3D Studio's Cancel and Save top right (owner 2026-10-09: «кнопки Done у нас всегда стандартизированы справа вверху, а не внизу. То есть
вот эти вот кнопки Done, сохранить и так далее ... чтобы они везде были идентичны»): Hyimg's one element for a Studio's session actions
(ui/hy/actions.js) in the studio's root, at the top row's right end (no round buttons in a Studio); Cancel, then Save in the studio's pink with white words
and its key in the tooltip. The dock keeps the tools, Undo, Redo, Reset and Snapshot; Cancel and Save are not in it. Save from there
closes the studio, the actions go with it. Chromium, dark."""
from playwright.sync_api import sync_playwright

from test_canvas_3d import SITE2, board_server, go_on

CARD = {"type": "model3d", "scene": "3d/scenes/a/scene.json", "camera": "jo1wd256", "x": 0, "y": 0, "w": 500, "h": 500}
PROBE = "(v) => { const p = document.createElement('i'); p.style.color = v; document.body.append(p); const c = getComputedStyle(p).color; p.remove(); return c; }"
BOX = "(s) => { const r = document.querySelector(s).getBoundingClientRect(); return [Math.round(r.left), Math.round(r.top), Math.round(r.right), Math.round(r.height)]; }"


def test_3d_studio_actions_top_right(tmp_path):
    port, lib, stop = board_server(tmp_path, {"c": dict(CARD)}, {"a": SITE2})
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
            page = browser.new_page(viewport={"width": 1600, "height": 1000}, color_scheme="dark")
            errors = []; page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(f"http://127.0.0.1:{port}/canvas.html")
            page.wait_for_function("() => typeof PLGST !== 'undefined' && PLGST.some(p => p.name === '3d' && p.ok)", timeout=20000)
            page.evaluate("() => { setPref('theme', 'dark'); renderBg(); }")
            page.dblclick(".plg[data-id=c]", position={"x": 30, "y": 30}); page.wait_for_selector(".m3r .hy-slider", timeout=60000)
            page.wait_for_timeout(1200); go_on(page)
            # Cancel, then Save; the dock has neither
            assert page.evaluate("() => [...document.querySelectorAll('.m3ui hy-studio-actions > *')].map(b => b.dataset.a)") == ["cancel", "save"]
            assert page.evaluate("() => document.querySelectorAll('#dock [data-a=save], #dock [data-a=cancel]').length") == 0
            assert page.evaluate("() => ['undo', 'redo', 'reset', 'shot'].every(a => document.querySelector(`#dock .m3t [data-a=${a}]`))")
            # the top row's line and height, at its gutter: in a Studio the board's round buttons are away (owner 2026-10-09 on round
            # 14's 3D Studio: «В режиме студии мы вот эти все элементы убираем»)
            acts, width = page.evaluate(BOX, ".m3ui hy-studio-actions"), page.evaluate("() => innerWidth")
            assert acts[1] == 12 and acts[3] == 38 and acts[2] == width - 12, (acts, width)
            assert page.evaluate("() => ['#bntf', '#bkeys', '#bhist', '#bset'].every(q => !document.querySelector(q).getClientRects().length)")
            # Save: the studio's pink, white words, its key in the tooltip and on its key cap; Cancel on the row's glass
            pink = page.evaluate(PROBE, "#ff4fa3")
            save = page.evaluate("() => { const b = document.querySelector('.m3ui hy-studio-actions [data-a=save]'), c = getComputedStyle(b); "
                                 "return [b.getAttribute('variant'), c.backgroundColor, c.color, b.querySelector('kbd').textContent]; }")
            assert save == ["accent", pink, "rgb(255, 255, 255)", "⌘↵"], save
            cancel = page.evaluate("() => { const b = document.querySelector('.m3ui hy-studio-actions [data-a=cancel]'); return [getComputedStyle(b).backgroundColor, b.title]; }")
            assert cancel[0] != pink and not cancel[1].endswith("Esc"), cancel   # the last Esc keeps the work (owner decision 2026-10-10, S-27)
            # Save from the top closes the studio and takes the actions away
            page.click(".m3ui hy-studio-actions [data-a=save]")
            page.wait_for_function("() => !document.querySelector('.plg-live') && !document.querySelector('hy-studio-actions')", timeout=20000)
            assert not errors, errors
            browser.close()
    finally:
        stop()
