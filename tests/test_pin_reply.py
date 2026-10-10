"""A click on an annotation's pin in 3D Studio puts the cursor in the reply at once, as on the board (owner 2026-10-10, round 18
question 20, r18-small.html, version A: «Да, все окей, давай так»). The thread is the board's (Hyimg ui/comments.js hyComments.open, one
rule for the board and every Studio): after the click the letters typed are the reply, the Studio's keys stay quiet (R, T, G, S would
change the tool). The same for the count on an object's row. Chromium, dark, the mouse.
"""
from playwright.sync_api import sync_playwright

from test_canvas_3d import SITE2, board_server
from test_studio_annotations import CARD, GL, OBJ, open_studio

FOCUS = "() => !!(document.activeElement && document.activeElement.matches('#cmthread.open textarea'))"
TOOL = "() => (document.querySelector('.m3t [data-tool].on') || {}).dataset?.tool || ''"


def test_a_click_on_a_pin_in_3d_studio_puts_the_cursor_in_the_reply(tmp_path):
    port, lib, stop = board_server(tmp_path, {"c": dict(CARD)}, {"a": SITE2}, lang="en")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=GL)
            page = browser.new_page(viewport={"width": 1600, "height": 1000}, color_scheme="dark")
            errors = []; page.on("pageerror", lambda e: errors.append(str(e)))
            open_studio(page, port)
            page.keyboard.press("c"); page.wait_for_function("() => document.querySelector('.m3t [data-ann]').classList.contains('on')")
            bb = page.locator("canvas.m3live").bounding_box(); x, y = bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2
            page.mouse.click(x, y); page.wait_for_selector("#cmthread.open textarea", timeout=5000)
            page.keyboard.type("Thinner edge"); page.keyboard.press("Enter")
            page.wait_for_function("() => { const t = document.querySelector('#cmthread.open'); return t && t.dataset.c !== 'draft'; }", timeout=5000)
            tid = page.evaluate("() => document.querySelector('#cmthread').dataset.c")
            page.keyboard.press("Escape"); page.wait_for_function("() => !document.querySelector('#cmthread.open')")
            page.mouse.click(bb["x"] - 20, bb["y"] + 200); page.keyboard.press("Escape")
            page.wait_for_function("() => !document.querySelector('.m3t [data-ann]').classList.contains('on')")
            page.wait_for_function(f"() => document.querySelector('.hy-spins .hy-spin[data-c=\"{tid}\"]')", timeout=5000)
            tool = page.evaluate(TOOL); assert tool == "select", tool

            # the pin over the view: a click, the reply has the cursor, R and T go into it and not to the tools
            page.locator(f'.hy-spins .hy-spin[data-c="{tid}"]').click()
            page.wait_for_selector(f'#cmthread.open[data-c="{tid}"] textarea')
            page.wait_for_function(FOCUS, timeout=3000)
            page.keyboard.type("go route")
            assert page.evaluate("() => document.querySelector('#cmthread textarea').value") == "go route"
            assert page.evaluate(TOOL) == tool
            page.keyboard.press("Escape"); page.wait_for_function("() => !document.querySelector('#cmthread.open')")

            # the count on the object's row: the same
            page.locator(f".m3l .row[data-k='{OBJ['id']}'] [data-ann-n]").click()
            page.wait_for_selector(f'#cmthread.open[data-c="{tid}"] textarea')
            page.wait_for_function(FOCUS, timeout=3000)
            page.keyboard.type("!")
            assert page.evaluate("() => document.querySelector('#cmthread textarea').value") == "go route!"
            assert page.evaluate(TOOL) == tool
            assert not errors, errors
            browser.close()
    finally:
        stop()
