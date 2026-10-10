"""3D Studio's medium and low findings of the П4 logic audit (2026-10-10, hyimg docs/process.md §5) and the owner's decisions of that day,
each as the person meets it. Chromium, the dark theme, a temporary library; each fails on the code before:

- S-42 Esc puts the open «+» menu away first, the studio stays
- S-45 a double click on a row's name renames a light (lights and cameras had no way), a click on a camera's icon makes it the card's
- S-43 a step that adds something is named by what it added, not «Camera: turned»; a rename is «Renamed: a → b»
- S-58 Delete on a layer says why nothing happened
- S-57 the search: the first Esc clears it, the second gives the keys back to the studio
- S-56 W and H: ↑ ↓ step, a burst of presses is one step of the board, Tab goes to the other field
- S-62 the finish menu is in sentence case («As in the file»)
- S-33, S-32 the Annotations tab's field: ⇧↵ a new line, Esc keeps the words, they are there again after the studio closed and opened
- S-44 a snapshot is a step of the studio (⌘Z takes it off the board, ⇧⌘Z puts it back) and stays after Cancel
- S-46 an object whose model file is missing says so

  HYIMG_REPO=<Hyimg checkout> nice -n 10 python3 -m pytest tests/test_p4_medium.py
"""
import copy

from playwright.sync_api import sync_playwright

from test_canvas_3d import SITE2, board_server, go_on
from test_p4_logic import CARD, DOC, ENG, LIVE, board_blur, launch, open_board, studio
from test_studio_undo import wait_doc

STEPS = ENG + ".then(m => m.histInfo().steps)"


def toasts(page): return page.evaluate("() => window.__T.splice(0).map(x => x[0])")


def test_esc_menu_rename_history_layer_search_size_and_case(tmp_path):
    port, lib, stop = board_server(tmp_path, {"c": CARD}, {"a": SITE2}, lang="en")
    try:
        with sync_playwright() as p:
            browser = launch(p); page, errors = open_board(browser, port); studio(page)
            # S-42: the «+» menu open, Esc closes it and nothing else
            page.locator("[data-plus]").first.click(); page.wait_for_selector(".m3menu:not([hidden])")
            board_blur(page); page.keyboard.press("Escape"); page.wait_for_timeout(500)
            assert page.evaluate(LIVE), "Esc with the «+» menu open left the studio"
            assert page.evaluate("() => !document.querySelector('.m3menu:not([hidden])')"), "the «+» menu stayed open"
            # S-45: a light renamed by a double click on its name; S-43: the step says so
            light = SITE2["lights"][0]["name"]
            page.locator(".m3l .row", has_text=light).first.locator(".nm").dblclick(); page.wait_for_selector(".m3l .m3ren", timeout=3000)
            page.keyboard.press("Meta+a"); page.keyboard.type("Fill"); page.keyboard.press("Enter")
            wait_doc(page, lambda d: d["lights"][0]["name"] == "Fill"); page.wait_for_timeout(600)
            assert page.evaluate(STEPS)[-1].startswith("Renamed"), page.evaluate(STEPS)
            page.locator(".m3l .row", has_text="Fill").first.locator(".nm").dblclick(); page.wait_for_selector(".m3l .m3ren")
            page.keyboard.type("Nope"); page.keyboard.press("Escape"); page.wait_for_timeout(500)   # a name: Esc puts it back
            assert page.evaluate(DOC)["lights"][0]["name"] == "Fill" and page.evaluate(LIVE)
            # S-43: a new box is «… added», whatever the camera did
            page.locator("[data-plus]").first.click(); page.locator(".m3menu [data-add=box]").first.click(); page.wait_for_timeout(1200); go_on(page)
            assert page.evaluate(STEPS)[-1].endswith("added"), page.evaluate(STEPS)
            # S-45: a second camera, its icon makes it the card's
            page.locator("[data-plus]").first.click(); page.locator(".m3menu [data-add=camera]").first.click(); page.wait_for_timeout(1200); go_on(page)
            cams = [c["id"] for c in page.evaluate(DOC)["cameras"]]; other = [c for c in cams if c != page.evaluate("() => board.items.c.camera")][0]
            page.locator(f".m3l .row[data-cam='{other}'] > svg").first.click(); page.wait_for_timeout(600)
            assert page.evaluate("() => board.items.c.camera") == other
            # S-58: Delete on a layer of the model says why
            page.evaluate(ENG + ".then(m => m.liveSelect(['body']))"); page.wait_for_timeout(300); toasts(page)
            board_blur(page); page.keyboard.press("Delete"); page.wait_for_timeout(400)
            assert any("eye" in x for x in toasts(page)), "Delete on a layer said nothing"
            # S-57: the search, Esc twice
            board_blur(page); page.keyboard.press("Escape"); page.keyboard.press("Escape"); page.wait_for_timeout(300)
            q = page.locator(".m3l [data-q]"); q.click(); page.keyboard.type("zz"); page.keyboard.press("Escape"); page.wait_for_timeout(200)
            assert q.input_value() == "" and page.evaluate("() => document.activeElement === document.querySelector('.m3l [data-q]')")
            page.keyboard.press("Escape"); page.wait_for_timeout(200)
            assert page.evaluate("() => document.activeElement !== document.querySelector('.m3l [data-q]')") and page.evaluate(LIVE)
            # S-56: W steps with ↑, three presses one step of the board, Tab to H
            page.evaluate(ENG + ".then(m => m.liveSelect([]))"); page.wait_for_selector(".m3r .m3res input[data-k=w]", timeout=20000)
            w0, past0 = page.evaluate("() => [document.querySelector('.m3res input[data-k=w]').value, past.length]")
            page.click(".m3res input[data-k=w]"); page.keyboard.press("ArrowUp"); page.keyboard.press("ArrowUp"); page.keyboard.press("ArrowUp")
            page.wait_for_timeout(1200)
            assert page.evaluate("() => board.items.c.res && board.items.c.res[0]") == int(w0) + 3
            assert page.evaluate("() => past.length") == past0 + 1, "a burst of ↑ is one step"
            page.click(".m3res input[data-k=w]"); page.keyboard.press("Tab"); page.wait_for_timeout(400)
            assert page.evaluate("() => document.activeElement && document.activeElement.dataset.k") == "h"
            # S-62: the finish menu in sentence case
            board_blur(page); page.evaluate(ENG + ".then(m => m.liveSelect([" + repr(SITE2["objects"][0]["id"]) + "]))"); page.wait_for_timeout(500)
            assert "As in the file" in page.locator(".m3r").inner_text()
            assert not errors, errors
            browser.close()
    finally:
        stop()


def test_the_annotations_tab_field_keeps_its_words(tmp_path):
    port, lib, stop = board_server(tmp_path, {"c": CARD}, {"a": SITE2}, lang="en")
    try:
        with sync_playwright() as p:
            browser = launch(p); page, errors = open_board(browser, port); studio(page)
            page.evaluate(ENG + ".then(m => m.liveSelect([" + repr(SITE2["objects"][0]["id"]) + "]))"); page.wait_for_timeout(400)
            page.click('.m3ltabs [data-ltab="ann"]'); page.wait_for_selector(".m3ann textarea:not([disabled])", timeout=5000)
            f = page.locator(".m3ann textarea")
            f.click(); page.keyboard.type("Line one"); page.keyboard.press("Shift+Enter"); page.keyboard.type("two")
            assert f.input_value() == "Line one\ntwo", "⇧↵ is a new line, as in the composer"
            page.keyboard.press("Escape"); page.wait_for_timeout(300)
            assert f.input_value() == "Line one\ntwo" and page.evaluate(LIVE), "Esc keeps the words and the studio"
            assert "Annotate" in f.get_attribute("placeholder") and "· C" not in f.get_attribute("placeholder")
            page.evaluate(ENG + ".then(m => m.stopLive(false))"); page.wait_for_timeout(800)
            studio(page); page.click('.m3ltabs [data-ltab="ann"]'); page.wait_for_selector(".m3ann textarea", timeout=5000)
            assert page.locator(".m3ann textarea").input_value() == "Line one\ntwo", "the words are kept for the scene after the studio closed"
            assert not errors, errors
            browser.close()
    finally:
        stop()


def test_a_snapshot_is_a_studio_step_and_stays_after_cancel(tmp_path):
    port, lib, stop = board_server(tmp_path, {"c": CARD}, {"a": SITE2}, lang="en")
    try:
        with sync_playwright() as p:
            browser = launch(p); page, errors = open_board(browser, port); studio(page)
            n0 = page.evaluate("() => Object.keys(board.items).length")
            page.click("[data-a=shot]"); page.wait_for_function(f"() => Object.keys(board.items).length === {n0 + 3}", timeout=30000)
            page.wait_for_timeout(800)
            board_blur(page); page.keyboard.press("Meta+z")
            page.wait_for_function(f"() => Object.keys(board.items).length === {n0}", timeout=8000)
            board_blur(page); page.keyboard.press("Meta+Shift+z")
            page.wait_for_function(f"() => Object.keys(board.items).length === {n0 + 3}", timeout=8000)
            page.evaluate(ENG + ".then(m => m.stopLive(false))"); page.wait_for_timeout(1200)
            assert page.evaluate("() => Object.keys(board.items).length") == n0 + 3, "Cancel took the snapshot's pictures away"
            assert not errors, errors
            browser.close()
    finally:
        stop()


def test_a_missing_model_file_says_so(tmp_path):
    scene = copy.deepcopy(SITE2); scene["objects"][0]["src"] = {"type": "model", "model": "gone-model"}
    port, lib, stop = board_server(tmp_path, {"c": CARD}, {"a": scene}, lang="en")
    try:
        with sync_playwright() as p:
            browser = launch(p); page = browser.new_page(viewport={"width": 1600, "height": 1000}, color_scheme="dark")
            page.add_init_script("window.__T = []; addEventListener('DOMContentLoaded', () => { const o = window.hyToast;"
                                 " window.hyToast = (t, k, x) => { window.__T.push([String(t), k || '']); return o && o(t, k, x); }; });")
            page.goto(f"http://127.0.0.1:{port}/canvas.html")
            page.wait_for_function("() => window.__T.some(x => x[0].includes('gone-model'))", timeout=30000)
            browser.close()
    finally:
        stop()
