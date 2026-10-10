"""«Save» and «Cancel» in the 3D studio, History, and the card as the truth for its view (owner 2026-10-07: «вместо Done нужно Save, ну и
Cancel тоже», «отсутствует история в 3D editor», «чтобы board был source of truth»; a board version had «restored» a wrong view because
the cameras lived only in the shared scene.json). Chromium and WebKit:

- Cancel after edits asks first, then leaves scene.json byte for byte, the card and the board as they were, nothing written meanwhile;
- Save keeps the card's view (item.view) and writes the scene only when what the cards share changed, its versions beside it; the board's
  ⌘Z then brings back the card's view and the scene (from .versions), ⇧⌘Z the saved one; the whole session is one board step;
- History lists the steps by name, a click goes there, the later ones dim and a new edit drops them;
- a card whose view differs from its scene's camera, or whose camera was deleted from scene.json, shows its own view and nothing is
  written on load; a card from before gets its view from the scene once, saved with the board, scene.json untouched;
- «Original camera» brings back the camera of the picture (studio.angles[id].camera0).
"""
import json, math, os, time, urllib.request
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from test_canvas_3d import SITE2, board_server, go_on
from test_studio_undo import DOC, wait_doc, slider, orbit, WEBKIT

ENGINES = ["chromium", "webkit"]
CARD = {"type": "model3d", "scene": "3d/scenes/a/scene.json", "camera": "jo1wd256", "x": 0, "y": 0, "w": 500, "h": 500}
CAM0 = {"loc": [-0.3, -0.7, 0.2], "rot": [0.7, 0.7, -0.1, -0.1], "lens": 120}


def launch(p, engine):
    if engine == "webkit": return p.webkit.launch()
    return p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])


def open_board(browser, port):
    page = browser.new_page(viewport={"width": 1600, "height": 1000})
    errors = []; page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(f"http://127.0.0.1:{port}/canvas.html")
    page.wait_for_function("() => typeof PLGST !== 'undefined' && PLGST.some(p => p.name === '3d' && p.ok)", timeout=20000)
    page.wait_for_function("() => Object.values(board.items).every(i => i.type !== 'model3d' || i.view)", timeout=20000)   # filled once
    page.wait_for_function("() => !dirty", timeout=10000)
    return page, errors


def studio(page, id="c"):
    page.dblclick(f".plg[data-id={id}]", position={"x": 30, "y": 30})
    page.wait_for_selector(".m3r .hy-slider", timeout=60000); page.wait_for_timeout(1200); go_on(page)


def eye(page, name):
    page.locator(".m3l .row", has_text=name).first.locator("[data-eye]").click(); page.wait_for_timeout(400)


def saved_board(lib):
    return json.loads((lib.parent / "state/boards/main.json").read_text())


@pytest.mark.parametrize("engine", ENGINES)
def test_cancel_leaves_the_scene_the_card_and_the_board(tmp_path, engine):
    if engine == "webkit" and not WEBKIT: pytest.skip("no Playwright WebKit")
    port, lib, stop = board_server(tmp_path, {"c": dict(CARD)}, {"a": SITE2})
    scene = lib / "3d/scenes/a/scene.json"; raw0 = scene.read_bytes()
    try:
        with sync_playwright() as p:
            browser = launch(p, engine); page, errors = open_board(browser, port)
            item0, steps0 = page.evaluate("() => [JSON.stringify(board.items.c), past.length]")
            studio(page)
            slider(page, "Объектив", 0.3); eye(page, "Ключевой")
            page.locator(".m3r button", has_text="Новая камера из этого вида").first.click(); page.wait_for_timeout(500)
            wait_doc(page, lambda d: len(d["cameras"]) == 2 and d["lights"][0].get("hidden"))
            assert scene.read_bytes() == raw0, "nothing written while the studio is open"
            # changes: Cancel asks first, the image studio's dialog over everything; a newer note does not cover it, Esc keeps the studio
            page.click("hy-studio-actions [data-a=cancel]"); page.wait_for_selector("#hyConfirm.on", timeout=5000)
            assert page.locator("#hyConfirm .hc-t").inner_text().strip() == "Сохранить изменения в «a»?"   # Hyimg's one question (S-26)
            page.evaluate("() => { HY.toast('Новая заметка поверх', 'info'); HY.toast('Еще одна', 'info'); }"); page.wait_for_timeout(400)
            b = page.locator("#hyConfirm [data-a=ok]").bounding_box()
            assert page.evaluate("([x, y]) => !!document.elementFromPoint(x, y).closest('#hyConfirm')", [b["x"] + b["width"] / 2, b["y"] + b["height"] / 2])
            page.keyboard.press("Escape"); page.wait_for_function("() => !document.querySelector('#hyConfirm')", timeout=5000)
            assert page.evaluate("() => !!document.querySelector('.plg-live')"), "Esc on the question keeps the studio"
            page.click("hy-studio-actions [data-a=cancel]"); page.wait_for_selector("#hyConfirm.on", timeout=5000)   # Cancel again (Esc keeps the work, S-27)
            page.wait_for_timeout(400); b = page.locator("#hyConfirm [data-a=ok]").bounding_box()
            page.mouse.click(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2)   # «Сбросить»
            page.wait_for_function("() => !document.querySelector('.plg-live')", timeout=20000)
            page.wait_for_timeout(800)
            assert scene.read_bytes() == raw0
            assert page.evaluate("() => [JSON.stringify(board.items.c), past.length]") == [item0, steps0]
            d = page.evaluate(DOC); assert len(d["cameras"]) == 1 and not d["lights"][0].get("hidden"), "the scene in memory as it was"
            # nothing changed: Cancel closes at once, no question
            studio(page); page.click("hy-studio-actions [data-a=cancel]")
            page.wait_for_function("() => !document.querySelector('.plg-live')", timeout=20000)
            assert scene.read_bytes() == raw0 and not errors, errors
            browser.close()
    finally:
        stop()


@pytest.mark.parametrize("engine", ENGINES)
def test_save_keeps_the_view_and_the_board_brings_the_scene_back(tmp_path, engine):
    if engine == "webkit" and not WEBKIT: pytest.skip("no Playwright WebKit")
    port, lib, stop = board_server(tmp_path, {"c": dict(CARD)}, {"a": SITE2})
    scene = lib / "3d/scenes/a/scene.json"; raw0 = scene.read_bytes(); rev0 = json.loads(raw0).get("rev", 0)
    try:
        with sync_playwright() as p:
            browser = launch(p, engine); page, errors = open_board(browser, port)
            view0, steps0 = page.evaluate("() => [board.items.c.view, past.length]")
            studio(page); eye(page, "Ключевой"); orbit(page)
            page.click("hy-studio-actions [data-a=save]"); page.wait_for_function("() => !document.querySelector('.plg-live')", timeout=20000)
            page.wait_for_timeout(800)
            d = json.loads(scene.read_text()); rev1 = d["rev"]
            assert d["lights"][0].get("hidden") and rev1 > rev0, "what the cards share is written"
            vers = lib / "3d/scenes/a/.versions"
            assert (vers / f"{rev0}.json").read_bytes() == raw0 and json.loads((vers / f"{rev1}.json").read_text())["rev"] == rev1
            it = page.evaluate("() => board.items.c")
            assert it["sceneRev"] == rev1 and math.dist(it["view"]["loc"], view0["loc"]) > 1e-3, it
            assert page.evaluate("() => past.length") == steps0 + 1, "one step on the board"
            for _ in range(50):
                if saved_board(lib)["items"]["c"].get("sceneRev") == rev1: break
                time.sleep(0.1)
            # the board's ⌘Z: the card's view and the scene as they were
            page.keyboard.press("Meta+z")
            page.wait_for_function("v => JSON.stringify(board.items.c.view) === JSON.stringify(v)", arg=view0)
            for _ in range(80):
                d = json.loads(scene.read_text())
                if not d["lights"][0].get("hidden"): break
                time.sleep(0.1)
            assert not d["lights"][0].get("hidden") and d.get("from_rev") == rev0, d
            page.keyboard.press("Meta+Shift+z")
            for _ in range(80):
                d = json.loads(scene.read_text())
                if d["lights"][0].get("hidden"): break
                time.sleep(0.1)
            assert d["lights"][0].get("hidden") and d.get("from_rev") == rev1, d
            assert not errors, errors
            browser.close()
    finally:
        stop()


@pytest.mark.parametrize("engine", ENGINES)
def test_history_lists_the_steps_and_goes_there(tmp_path, engine):
    if engine == "webkit" and not WEBKIT: pytest.skip("no Playwright WebKit")
    port, lib, stop = board_server(tmp_path, {"c": dict(CARD)}, {"a": SITE2})
    rows = "() => [...document.querySelectorAll('.m3hist .hrow')].map(r => [r.textContent.trim(), r.classList.contains('cur'), r.classList.contains('fut')])"
    try:
        with sync_playwright() as p:
            browser = launch(p, engine); page, errors = open_board(browser, port)
            studio(page)
            slider(page, "Объектив", 0.3); eye(page, "Ключевой")
            page.locator(".m3r button", has_text="Новая камера из этого вида").first.click(); page.wait_for_timeout(700)
            page.click(".m3r [data-tab=hist]")
            r = page.evaluate(rows)
            assert [x[0].split(" ")[0] for x in r] == ["Открыто", "Объектив", "Свет", "Новая"], r
            assert r[1][0].startswith("Объектив ") and "→" in r[1][0] and r[2][0] == "Свет · Ключевой скрыт", r
            assert r[3][1] and not any(x[2] for x in r), "the last one is current, none dimmed"
            page.locator(".m3hist .hrow").nth(1).click()   # back to after the lens
            d = wait_doc(page, lambda d: len(d["cameras"]) == 1 and not d["lights"][0].get("hidden"))
            assert abs(d["cameras"][0]["lens"] - SITE2["cameras"][0]["lens"]) > 1
            r = page.evaluate(rows); assert [x[1] for x in r] == [False, True, False, False] and [x[2] for x in r] == [False, False, True, True], r
            page.click(".m3r [data-tab=props]"); eye(page, "Ключевой"); page.click(".m3r [data-tab=hist]")
            r = page.evaluate(rows); assert len(r) == 3 and r[2][0] == "Свет · Ключевой скрыт" and r[2][1], "a new edit drops the later steps"
            assert page.locator(".m3r .dk").is_hidden() and not errors, errors
            page.click("hy-studio-actions [data-a=save]"); page.wait_for_function("() => !document.querySelector('.plg-live')", timeout=20000)
            browser.close()
    finally:
        stop()


@pytest.mark.parametrize("engine", ENGINES)
def test_the_card_shows_its_own_view_and_load_writes_no_scene(tmp_path, engine):
    if engine == "webkit" and not WEBKIT: pytest.skip("no Playwright WebKit")
    own = {"name": "Свой", "loc": [0.4, -0.5, 0.3], "rot": [0.8, 0.5, 0.2, 0.2], "lens": 90, "sensor": 36, "sensor_h": 36, "fit": "AUTO", "shift": [0, 0]}
    items = {"c": dict(CARD, view=own),                              # its view, not the scene camera's
             "g": dict(CARD, camera="gone", view=own, x=600),       # its camera deleted from scene.json
             "o": dict(CARD, x=1200)}                                # from before: no view yet
    port, lib, stop = board_server(tmp_path, items, {"a": SITE2})
    scene = lib / "3d/scenes/a/scene.json"; raw0 = scene.read_bytes(); t0 = scene.stat().st_mtime_ns
    try:
        with sync_playwright() as p:
            browser = launch(p, engine); page, errors = open_board(browser, port)
            page.wait_for_function("() => [...document.querySelectorAll('.plg[data-type=model3d] img.m3')].filter(i => i.complete && i.naturalWidth).length === 3",
                                   timeout=60000)
            page.wait_for_timeout(1500)
            assert scene.read_bytes() == raw0 and scene.stat().st_mtime_ns == t0, "nothing written to the scene on load"
            v = saved_board(lib)["items"]["o"].get("view")
            assert v and v["loc"] == SITE2["cameras"][0]["loc"], "a card from before took its scene camera's view, saved with the board"
            assert page.evaluate("() => past.length") == 0, "not a step to undo"
            # the stills differ: each card its own view (the one without a camera in the scene too)
            px = """id => { const i = document.querySelector(`.plg[data-id="${id}"] img.m3`), c = document.createElement('canvas'); c.width = 24; c.height = 24;
              const x = c.getContext('2d'); x.drawImage(i, 0, 0, 24, 24); return [...x.getImageData(0, 0, 24, 24).data]; }"""
            a, g, o = (page.evaluate(px, k) for k in "cgo")
            dif = lambda u, w: sum(abs(x - y) for x, y in zip(u, w)) / len(u)
            assert dif(a, g) < 1 and dif(a, o) > 1, (dif(a, g), dif(a, o))
            assert not errors, errors
            browser.close()
    finally:
        stop()


@pytest.mark.parametrize("engine", ENGINES)
def test_original_camera_brings_back_the_pictures_view(tmp_path, engine):
    if engine == "webkit" and not WEBKIT: pytest.skip("no Playwright WebKit")
    doc = dict(SITE2, studio={"folder": "/nowhere", "angles": {"jo1wd256": {"look": "L1", "camera0": CAM0}}})
    port, lib, stop = board_server(tmp_path, {"c": dict(CARD)}, {"a": doc})
    try:
        with sync_playwright() as p:
            browser = launch(p, engine); page, errors = open_board(browser, port)
            studio(page)
            page.locator(".m3r button", has_text="Вернуть исходную камеру").first.click()
            d = wait_doc(page, lambda d: math.dist(d["cameras"][0]["loc"], CAM0["loc"]) < 1e-4)
            assert abs(d["cameras"][0]["lens"] - 120) < 1e-6
            page.click(".m3r [data-tab=hist]")
            page.wait_for_function("() => (document.querySelector('.m3hist .hrow.cur') || {}).textContent === 'Камера: как на картинке'", timeout=5000)
            page.click("hy-studio-actions [data-a=save]"); page.wait_for_function("() => !document.querySelector('.plg-live')", timeout=20000)
            assert math.dist(page.evaluate("() => board.items.c.view.loc"), CAM0["loc"]) < 1e-4
            assert not errors, errors
            browser.close()
    finally:
        stop()


@pytest.mark.parametrize("engine", ENGINES)
def test_a_board_version_brings_the_scene_and_the_cards_back(tmp_path, engine):
    """A board version restored (the board's History › «Use this version») puts back each 3D card's view and the scene version it showed
    (sceneRev, from <scene dir>/.versions): scene.json, the studio's scene in memory and the card follow (owner 2026-10-07: a board version
    had «restored» a wrong view, the cameras lived only in scene.json)"""
    if engine == "webkit" and not WEBKIT: pytest.skip("no Playwright WebKit")
    port, lib, stop = board_server(tmp_path, {"c": dict(CARD)}, {"a": SITE2})
    scene = lib / "3d/scenes/a/scene.json"
    post = lambda body: json.loads(urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{port}/api/history", json.dumps(body).encode(),
                                                                                 {"Content-Type": "application/json"})).read())
    def saved_rev(rev):
        for _ in range(80):
            if saved_board(lib)["items"]["c"].get("sceneRev") == rev: return
            time.sleep(0.1)
        raise AssertionError(saved_board(lib)["items"]["c"])
    try:
        with sync_playwright() as p:
            browser = launch(p, engine); page, errors = open_board(browser, port)
            # session A: the light hidden (shared by the cards), the camera turned; saved: the scene's rev A, the card's view A
            studio(page); eye(page, "Ключевой"); orbit(page)
            page.click("hy-studio-actions [data-a=save]"); page.wait_for_function("() => !document.querySelector('.plg-live')", timeout=20000)
            rev_a, view_a = page.evaluate("() => [board.items.c.sceneRev, board.items.c.view]")
            saved_rev(rev_a); assert json.loads(scene.read_text())["lights"][0].get("hidden")
            ver = post({"name": "main", "action": "save", "label": "A"})   # the owner's version of the board, as «Save version» does
            # session B: the light shown again, the camera turned again
            studio(page); eye(page, "Ключевой"); orbit(page)
            page.click("hy-studio-actions [data-a=save]"); page.wait_for_function("() => !document.querySelector('.plg-live')", timeout=20000)
            rev_b, view_b = page.evaluate("() => [board.items.c.sceneRev, board.items.c.view]")
            saved_rev(rev_b); assert rev_b > rev_a and view_b != view_a and not json.loads(scene.read_text())["lights"][0].get("hidden")
            # the board's version A: the card's view and its scene come back
            page.evaluate("id => useVersion(id)", ver["id"])
            page.wait_for_function("r => board.items.c && board.items.c.sceneRev === r", arg=rev_a, timeout=15000)
            assert page.evaluate("() => board.items.c.view") == view_a
            for _ in range(80):
                d = json.loads(scene.read_text())
                if d.get("from_rev") == rev_a: break
                time.sleep(0.1)
            assert d.get("from_rev") == rev_a and d["lights"][0].get("hidden") and d["rev"] > rev_b, d
            for _ in range(50):   # the scene in memory reads the restored file after it is written, a moment later
                if page.evaluate(DOC)["lights"][0].get("hidden"): break
                time.sleep(0.1)
            assert page.evaluate(DOC)["lights"][0].get("hidden"), "the scene in memory follows"
            page.wait_for_function("() => document.querySelector('#hyToasts') && document.querySelector('#hyToasts').textContent.includes('снова такая')",
                                   timeout=10000)
            assert not errors, errors
            browser.close()
    finally:
        stop()


@pytest.mark.parametrize("engine", ENGINES)
def test_enter_takes_a_number_and_only_cmd_enter_saves(tmp_path, engine):
    """⌘↵ saves the studio, as in the image studio; a plain Enter never does (owner 2026-10-07: «просто Enter можно случайно нажать или
    применить, например, при изменении чисел в параметрах»): Enter in the lens's number field only takes the value, Enter in the view too
    leaves the studio open, ⌘↵ saves and closes"""
    if engine == "webkit" and not WEBKIT: pytest.skip("no Playwright WebKit")
    port, lib, stop = board_server(tmp_path, {"c": dict(CARD)}, {"a": SITE2})
    try:
        with sync_playwright() as p:
            browser = launch(p, engine); page, errors = open_board(browser, port)
            studio(page)
            lens = page.locator(".m3r .hy-slider").filter(has_text="Объектив").first
            lens.locator(".hy-slider-v").click(); lens.locator("input.hy-slider-ed").fill("50"); page.keyboard.press("Enter"); page.wait_for_timeout(600)
            wait_doc(page, lambda d: abs(d["cameras"][0]["lens"] - 50) < 1e-6)
            assert page.evaluate("() => !!document.querySelector('.plg-live')"), "Enter in a number field takes the value, it does not save"
            page.locator("canvas.m3live").click(position={"x": 20, "y": 20}); page.keyboard.press("Enter"); page.wait_for_timeout(600)
            assert page.evaluate("() => !!document.querySelector('.plg-live')"), "a plain Enter never saves"
            assert "⌘↵" in page.locator("hy-studio-actions [data-a=save]").get_attribute("title")
            page.keyboard.press("Meta+Enter")
            page.wait_for_function("() => !document.querySelector('.plg-live')", timeout=20000)
            assert abs(page.evaluate("() => board.items.c.view.lens") - 50) < 1e-6, "⌘↵ saved the card's view"
            assert not errors, errors
            browser.close()
    finally:
        stop()
