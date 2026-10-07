"""The 3D card's frame and output size in the Scene panel, not over the card (owner 2026-10-07: «вот это в рендере я бы убрал, оно мешает,
лучше это добавить где-то справа в настройках. Потому что там же тоже размер должен быть. Я не вижу, где там настройки размера сцены»):

- in the studio the board draws no frame bar over the card (the plugin's frameBar: false);
- under Frame the panel has W × H px with the app's W ↔ H link, the presets on the long side and ⇄; a ratio, a preset or a size typed in
  shapes the card on the board and is the scene's render size (scene.json render, Blender's «Render» size), each one step of the undo;
- a camera the card does not look through shows the size greyed with its reason.
Chromium and WebKit, light and dark, the app's page with the canvas in its frame.

  HYIMG_REPO=<Hyimg checkout> python3 -m pytest tests/test_frame_panel.py
  M3_SHOTS=<folder> also saves screenshots
"""
import json, os

import pytest
from playwright.sync_api import sync_playwright

from test_canvas_3d import board_server, wait_file
from test_3d_files import ENGINES
from test_editor_ui import open_editor
from test_outliner_sections import ITEMS, settle
from test_camera_panel import open_board, scene

SHOTS = os.environ.get("M3_SHOTS")


def shot(page, name):
    if SHOTS: os.makedirs(SHOTS, exist_ok=True); page.screenshot(path=os.path.join(SHOTS, name + ".png"))


SIZE = "() => [...document.querySelectorAll('.m3r .m3res input')].map(i => +i.value)"
CARD = "() => { const c = board.items.c; return { w: c.w, h: c.h, lock: c.lock || null, res: c.res || null }; }"
PRESSED = "() => [...document.querySelectorAll('.m3r .m3res [data-long]')].filter(b => b.getAttribute('aria-pressed') === 'true').map(b => +b.dataset.long)"


def size_is(frame, want, t=20000):
    """the panel is drawn again after each change (a software-GL frame can take a while): wait until it shows want"""
    frame.wait_for_function(f"() => JSON.stringify(({SIZE})()) === {json.dumps(json.dumps(want, separators=(',', ':')))}", timeout=t)
    return True


def pick_frame(frame, label):
    frame.locator(".m3r .dialkit-select-trigger", has_text="Frame").first.click()
    frame.locator(".dialkit-select-option", has_text=label).first.click(); frame.wait_for_timeout(700)


def typed(frame, k, v):
    i = frame.locator(f".m3r .m3res input[data-k={k}]"); i.wait_for(timeout=20000); i.click(); i.fill(str(v)); i.press("Enter"); frame.wait_for_timeout(700)


def undo(page, frame):
    frame.evaluate("() => document.activeElement && document.activeElement.blur()")
    page.keyboard.press("Meta+z"); frame.wait_for_timeout(700)


@pytest.mark.parametrize("engine", ENGINES)
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_the_frame_and_the_output_size_are_in_the_scene_panel(tmp_path, engine, theme):
    port, lib, stop = board_server(tmp_path, ITEMS, {"big": scene()}, lang="en")
    path = lib / "3d/scenes/big/scene.json"
    try:
        with sync_playwright() as p:
            browser, page, frame, errors = open_board(p, engine, port, theme)
            open_editor(frame, "c"); settle(frame); frame.wait_for_selector(".m3r .m3res input", timeout=10000); frame.wait_for_timeout(500)
            # no frame bar over the card in the studio; the panel's size under Frame
            assert frame.locator("#handles .tidy.cratio").count() == 0, "the board's frame bar stays off the 3D card"
            order = frame.evaluate("""() => { const f = [...document.querySelectorAll('.m3r .dialkit-select-trigger')].find(x => x.textContent.startsWith('Frame')), r = document.querySelector('.m3r .m3res');
              return !!(f && r && (f.compareDocumentPosition(r) & Node.DOCUMENT_POSITION_FOLLOWING)); }""")
            assert order, "W × H stands under Frame"
            assert size_is(frame, [1600, 1200])   # a 640 × 480 card: its shape at 1600 px
            shot(page, f"frame-panel-{theme}-{engine}")

            # a ratio: the card turns square, so does the size
            pick_frame(frame, "1:1")
            c = frame.evaluate(CARD); assert c["w"] == c["h"] and c["lock"] == "1:1", c
            assert size_is(frame, [1600, 1600])
            # a preset: 4096 on the long side, the scene's render size with it
            frame.click(".m3r .m3res [data-long='4096']"); frame.wait_for_timeout(700)
            assert size_is(frame, [4096, 4096]) and frame.evaluate(PRESSED) == [4096] and frame.evaluate(CARD)["res"] == [4096, 4096]
            d = wait_file(path, lambda d: d.get("render") == {"x": 4096, "y": 4096}); assert d["render"] == {"x": 4096, "y": 4096}
            # one step of the undo
            undo(page, frame)
            assert frame.evaluate(CARD)["res"] is None and size_is(frame, [1600, 1600]), frame.evaluate(CARD)
            # W typed with the link on: H follows, the card keeps its shape
            typed(frame, "w", 2000)
            assert size_is(frame, [2000, 2000]) and frame.evaluate(CARD)["w"] == frame.evaluate(CARD)["h"]
            # the link off, H typed: the card takes 16:9, its lock with it
            frame.click(".m3r .m3res [data-link]"); frame.wait_for_timeout(200)
            assert not frame.evaluate("() => document.querySelector('.m3r .m3res [data-link]').classList.contains('on')")
            typed(frame, "h", 1125)
            c = frame.evaluate(CARD); assert c["res"] == [2000, 1125] and c["lock"] == "16:9" and abs(c["w"] / c["h"] - 16 / 9) < 0.02, c
            assert size_is(frame, [2000, 1125])
            shot(page, f"frame-panel-16x9-{theme}-{engine}")
            undo(page, frame)
            c = frame.evaluate(CARD); assert c["w"] == c["h"] and c["res"] == [2000, 2000], c
            frame.click(".m3r .m3res [data-link]")   # the link back on for the next test (a pref)
            # ⇄ turns the frame: a 4:5 card becomes 5:4, the size turns with it
            pick_frame(frame, "4:5"); frame.wait_for_function(f"() => {{ const s = ({SIZE})(); return s.length === 2 && s[1] > s[0]; }}", timeout=20000); s = frame.evaluate(SIZE)
            frame.click(".m3r .m3res [data-flip]"); frame.wait_for_timeout(700)
            assert size_is(frame, [s[1], s[0]]) and frame.evaluate(CARD)["lock"] == "5:4", frame.evaluate(CARD)

            # a camera the card does not look through: the size greyed with its reason
            frame.click(".m3l .row[data-cam=c03]"); frame.wait_for_timeout(700); frame.wait_for_selector(".m3r .m3res", timeout=5000)
            g = frame.evaluate("() => { const b = document.querySelector('.m3r .m3res'); return { na: b.classList.contains('m3na'), title: b.title, op: +getComputedStyle(b).opacity }; }")
            assert g["na"] and "make this camera active" in g["title"] and g["op"] < 0.6, g
            assert not errors, errors
            browser.close()
    finally:
        stop()
