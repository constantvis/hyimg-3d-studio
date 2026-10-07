"""«3D Studio» on the bar over a 3D card (owner 2026-10-07, a screenshot of the bar with only the Raw Editor wheel and the opacity): the
first button, the cube and «3D-студия» with its key ↵ and a line after it, as «Crop» over a picture; a click opens the studio for that
card (the dock's 3D segment and a double click do the same), Enter too; over two cards there is none. Chromium and WebKit, the board in
Russian.

  HYIMG_REPO=<Hyimg checkout> HYIMG_FRAMES=<hyimg-frames checkout> python3 -m pytest tests/test_studio_button.py
  HYIMG_SHOTS=<folder> also saves the bar in both themes
"""
import os
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from test_card_drag import board_dir, WEBKIT   # noqa: F401  (the fixture: two 3D cards m1, m2 and two pictures)

SHOTS = os.environ.get("HYIMG_SHOTS")
BAR = """() => { const t = document.querySelector('#handles .tidy'); if (!t) return null;
  return [...t.children].map(c => c.matches('button') ? (c.dataset.plgbar !== undefined ? 'plg:' : '') + c.textContent.trim() : c.className.split(' ')[0]); }"""


@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_the_bar_over_a_3d_card_opens_its_studio(board_dir, engine):
    if engine == "webkit" and not WEBKIT: pytest.skip("no Playwright WebKit")
    port, state = board_dir
    with sync_playwright() as p:
        browser = p.webkit.launch() if engine == "webkit" else p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        for theme in ("dark", "light"):
            page = browser.new_page(viewport={"width": 1500, "height": 950}, color_scheme=theme)
            errors = []; page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(f"http://127.0.0.1:{port}/canvas.html", wait_until="domcontentloaded")
            page.wait_for_function("() => typeof PLGST !== 'undefined' && ['3d', 'frames'].every(n => PLGST.some(p => p.name === n && p.ok))", timeout=30000)
            page.evaluate("() => { cam.x = -60; cam.y = -160; cam.z = 0.99; renderCam(); render(); }")
            page.wait_for_function("() => [...document.querySelectorAll('.plg[data-type=model3d] img.m3')].filter(i => i.complete && i.naturalWidth).length === 2", timeout=60000)
            b = page.locator('#items [data-id="m1"]').bounding_box(); page.mouse.click(b["x"] + 40, b["y"] + 40); page.wait_for_timeout(300)
            bar = page.evaluate(BAR)
            assert bar and bar[0] == "plg:3D-студия↵" and bar[1] == "sep", bar   # first, its key cap, a line after it
            assert page.evaluate("() => document.querySelector('#handles .tidy button').title") == "Открыть 3D-студию для этой карточки · Enter или двойной клик"
            if SHOTS:
                Path(SHOTS).mkdir(parents=True, exist_ok=True)
                t = page.locator("#handles .tidy").bounding_box()
                page.screenshot(path=str(Path(SHOTS) / f"studio-button-{engine}-{theme}.png"), clip={"x": t["x"] - 20, "y": t["y"] - 20, "width": t["width"] + 40, "height": 330})
            if theme == "light":   # the rest once
                page.close(); continue
            # over two cards: none
            b = page.locator('#items [data-id="m2"]').bounding_box()
            page.keyboard.down("Shift"); page.mouse.click(b["x"] + 40, b["y"] + 40); page.keyboard.up("Shift"); page.wait_for_timeout(200)
            assert "plg:3D-студия↵" not in (page.evaluate(BAR) or []), page.evaluate(BAR)
            # a click on the button opens the studio for that card, as the dock's 3D segment does
            page.mouse.click(1400, 900); page.mouse.click(b["x"] + 40, b["y"] + 40); page.wait_for_timeout(200)
            assert page.evaluate("() => [...sel]") == ["m2"]
            page.locator("#handles .tidy button[data-plgbar]").first.click()
            page.wait_for_function("() => document.querySelector('.plg-live') && document.querySelector('.plg-live').dataset.id === 'm2' && MODES.open === '3d'", timeout=60000)
            assert "plg:3D-студия↵" not in (page.evaluate(BAR) or []), "not on the studio's own bar"
            page.keyboard.press("Meta+Enter")   # the studio's Save
            page.wait_for_function("() => !document.querySelector('.plg-live') && MODES.open === 'board'", timeout=20000)
            # Enter on a selected 3D card opens it too
            b = page.locator('#items [data-id="m1"]').bounding_box(); page.mouse.click(b["x"] + 40, b["y"] + 40); page.wait_for_timeout(200)
            page.keyboard.press("Enter")
            page.wait_for_function("() => document.querySelector('.plg-live') && document.querySelector('.plg-live').dataset.id === 'm1'", timeout=60000)
            page.keyboard.press("Meta+Enter")
            page.wait_for_function("() => !document.querySelector('.plg-live')", timeout=20000)
            assert not errors, errors
            page.close()
        browser.close()
