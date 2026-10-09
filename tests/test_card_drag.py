"""A 3D card drags and drops like a picture (owner 2026-10-07: «глючит перетаскивание 3d item, и когда отпускаю, оно не опускается»,
two board screenshots: the card's outline lower than its corner squares, the info panel still on the picture selected before).

The cause was in the board: render() reused a card's element by id whatever kind it held. The image studio on a picture (a double click)
makes the picture a frame card under the same id and gives the picture back on leaving; the picture's render then ran on the frame's
element, stopped on its missing kind pill and threw on every redraw after that. Each redraw moved the cards before that one in the
board's order and stopped before the corner squares, the bar and the info panel; on release the redraw threw before the drag ended, so
the card kept following the pointer with the button up and nothing was saved (Hyimg 0dc7b0e makes such an element again).

Here, in Chromium and WebKit with the frames plugin beside this one: a picture after the 3D cards in the board's order goes through the
image studio and back (Esc), then the 3D card, two cards at once and the picture are dragged with the mouse: each lands where it was let
go, its element and its corner squares agree, the drag is over, the move is one undo step and saved, and the page threw nothing.

  HYIMG_REPO=<Hyimg checkout> HYIMG_FRAMES=<hyimg-image-studio checkout> python3 -m pytest tests/test_card_drag.py
"""
import json, os, subprocess, sys, time, urllib.request, uuid
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from test_canvas_3d import REPO, HERE, SITE2, tiny_model, free_port
from test_card_look import FRAMES, picture

WEBKIT = any(Path(os.path.expanduser("~/Library/Caches/ms-playwright")).glob("webkit-*"))


@pytest.fixture
def board_dir(tmp_path):
    lib, state, plugins = tmp_path / "lib", tmp_path / "state", tmp_path / "plugins"
    tiny_model(lib)
    (lib / "3d/scenes/a").mkdir(parents=True); (lib / "3d/scenes/a/scene.json").write_text(json.dumps(SITE2))
    (lib / "pics").mkdir()
    picture(600, 400, (190, 60, 40), (240, 190, 90)).save(lib / "pics/a.png")
    picture(600, 400, (30, 60, 190), (90, 200, 230)).save(lib / "pics/b.png")
    card = lambda x, y: {"type": "model3d", "scene": "3d/scenes/a/scene.json", "camera": "jo1wd256", "x": x, "y": y, "w": 300, "h": 200}
    # the board's order: a picture, the two 3D cards, then the picture that goes through the image studio (after them, as on the owner's board)
    items = {"p0": {"path": "pics/b.png", "x": 0, "y": 260, "w": 300, "ar": 1.5, "crop": None},
             "m1": card(0, 0), "m2": card(340, 0),
             "p1": {"path": "pics/a.png", "x": 680, "y": 260, "w": 300, "ar": 1.5, "crop": None}}
    (state / "boards").mkdir(parents=True); plugins.mkdir()
    (plugins / "3d").symlink_to(HERE); (plugins / "frames").symlink_to(FRAMES)
    (state / "app-settings.json").write_text(json.dumps({"cv.lang": "ru"}))
    (state / "boards/main.json").write_text(json.dumps({"items": items, "groups": {}, "revision": 1}))
    port = free_port()
    env = {k: v for k, v in os.environ.items() if not k.startswith(("HYIMG_", "REVIEW_"))}
    env.update(HYIMG_LIBRARY_ROOT=str(lib), HYIMG_STATE_ROOT=str(state), HYIMG_PROJECT_ID=str(uuid.uuid4()), HYIMG_PLUGINS=str(plugins),
               HYIMG_SETTINGS=str(state / "app-settings.json"), PYTHONDONTWRITEBYTECODE="1")
    log = open(tmp_path / "server.log", "w+")
    proc = subprocess.Popen([sys.executable, str(REPO / "review/server.py"), str(port)], env=env, stdout=log, stderr=log)
    for _ in range(100):
        try: urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1); break
        except OSError: time.sleep(0.1)
    try:   # the server goes even when the test fails or is interrupted
        yield port, state
    finally:
        proc.terminate(); proc.wait(5); log.close()


# where the card is drawn, where its corner squares are, what the model says, and whether a drag is still going on
LOOK = """id => { const el = document.querySelector(`#items [data-id="${id}"]`), r = el.getBoundingClientRect(), it = board.items[id];
  const nw = document.querySelector(`#handles .h[data-resize="${id}"][data-rc="nw"]`), h = nw && nw.getBoundingClientRect();
  const sb = stage.getBoundingClientRect();
  return { el: [r.left, r.top], h: h && [h.left + h.width / 2, h.top + h.height / 2], model: [(it.x - cam.x) * cam.z + sb.left, (it.y - cam.y) * cam.z + sb.top],
           xy: [it.x, it.y], drag: !!drag, info: document.querySelector('#iN').textContent }; }"""


def saved(state, id):
    return json.loads((state / "boards/main.json").read_text())["items"][id]


def drag_by(page, id, dx, dy):
    b = page.locator(f'#items [data-id="{id}"]').bounding_box()
    x, y = b["x"] + b["width"] * 0.5, b["y"] + b["height"] * 0.6
    page.mouse.move(x, y); page.mouse.down()
    page.mouse.move(x + dx / 2, y + dy / 2, steps=6); page.mouse.move(x + dx, y + dy, steps=6)
    page.mouse.up(); page.wait_for_timeout(250)


@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_a_3d_card_drops_after_a_picture_went_through_the_image_studio(board_dir, engine):
    if engine == "webkit" and not WEBKIT: pytest.skip("no Playwright WebKit")
    port, state = board_dir
    with sync_playwright() as p:
        browser = p.webkit.launch() if engine == "webkit" else p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        page = browser.new_page(viewport={"width": 1500, "height": 950})
        errors = []; page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"http://127.0.0.1:{port}/canvas.html", wait_until="domcontentloaded")
        page.wait_for_function("() => typeof PLGST !== 'undefined' && ['3d', 'frames'].every(n => PLGST.some(p => p.name === n && p.ok))", timeout=30000)
        page.evaluate("() => { cam.x = -60; cam.y = -160; cam.z = 0.99; renderCam(); render(); }")   # the owner's zoom (99%)
        page.wait_for_function("() => [...document.querySelectorAll('.plg[data-type=model3d] img.m3')].filter(i => i.complete && i.naturalWidth).length === 2", timeout=60000)

        # the picture after the 3D cards goes into the image studio (a double click) and back without a Save (Esc)
        b = page.locator('#items [data-id="p1"]').bounding_box()
        page.mouse.dblclick(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2)
        page.wait_for_function("() => board.items.p1.type === 'imgframe'", timeout=30000)
        page.wait_for_timeout(500)
        page.keyboard.press("Escape")
        page.wait_for_function("() => !board.items.p1.type && MODES.open === 'board'", timeout=15000)
        page.wait_for_timeout(300)

        # the 3D card: selected by a click (the info panel follows), then dragged by its body
        b = page.locator('#items [data-id="m1"]').bounding_box(); page.mouse.click(b["x"] + 40, b["y"] + 40); page.wait_for_timeout(200)
        assert page.evaluate("() => document.querySelector('#iN').textContent") == "3D-сцена", "the info panel follows the selection"
        x0 = page.evaluate("() => board.items.m1.x")
        drag_by(page, "m1", 120, 150)
        s = page.evaluate(LOOK, "m1")
        assert not s["drag"], "the drag ends when the button is let go"
        assert abs(s["xy"][0] - (x0 + 120 / 0.99)) < 2, s
        for a, b_ in ((s["el"], s["model"]), (s["h"], s["model"])):
            assert b_ and a and abs(a[0] - b_[0]) < 1.5 and abs(a[1] - b_[1]) < 1.5, s   # the card and its corner squares where the model is
        page.mouse.move(900, 700, steps=5); page.wait_for_timeout(150)
        assert page.evaluate("() => board.items.m1.x") == s["xy"][0], "the card stays down after the release, it does not follow the pointer"
        page.wait_for_function("() => !dirty", timeout=10000)
        for _ in range(50):
            if abs(saved(state, "m1")["x"] - s["xy"][0]) < 0.01: break
            time.sleep(0.1)
        assert abs(saved(state, "m1")["x"] - s["xy"][0]) < 0.01, "the move is saved"
        page.keyboard.press("Meta+z"); page.wait_for_function("x => board.items.m1.x === x", arg=x0)   # one step

        # two cards at once (⇧-click), then the picture that went through the studio
        b = page.locator('#items [data-id="m2"]').bounding_box(); page.mouse.click(b["x"] + 40, b["y"] + 40)
        b = page.locator('#items [data-id="m1"]').bounding_box(); page.keyboard.down("Shift"); page.mouse.click(b["x"] + 40, b["y"] + 40); page.keyboard.up("Shift")
        assert page.evaluate("() => [...sel].sort()") == ["m1", "m2"]
        before = page.evaluate("() => [board.items.m1.x, board.items.m2.x]")
        drag_by(page, "m2", 60, 90)
        after = page.evaluate("() => [board.items.m1.x, board.items.m2.x, !!drag]")
        assert not after[2] and all(abs(a - b_ - 60 / 0.99) < 2 for a, b_ in zip(after[:2], before)), (before, after)
        for id in ("m1", "m2"):
            s = page.evaluate(LOOK, id); assert abs(s["el"][0] - s["model"][0]) < 1.5 and abs(s["el"][1] - s["model"][1]) < 1.5, (id, s)
        page.mouse.click(1400, 900); page.wait_for_timeout(150)
        b = page.locator('#items [data-id="p1"]').bounding_box(); page.mouse.click(b["x"] + 40, b["y"] + 40); page.wait_for_timeout(150)
        drag_by(page, "p1", -80, 120)
        s = page.evaluate(LOOK, "p1")
        assert not s["drag"] and abs(s["el"][0] - s["model"][0]) < 1.5 and s["h"] and abs(s["h"][0] - s["model"][0]) < 1.5, s
        assert not errors, errors
        browser.close()
