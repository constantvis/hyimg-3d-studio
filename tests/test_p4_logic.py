"""3D Studio's critical and high findings of the П4 logic audit (2026-10-10, hyimg docs/process.md §5), each as the person meets it.
Chromium, the dark theme, a temporary library:

- S-01 Cancel › Discard takes back only the studio's own: a card another window added meanwhile stays, on the board and in its file
- S-03 «Close without saving?»: «Keep editing» has the focus, ↵ keeps the studio, Discard is a button of its own
- S-06 the board's keys wait behind the studio: L, 3, ⇧1, ⌘A, ⌘D, ⌘X leave the board as it was
- S-15 a control of the panels touched with the mouse leaves the studio's keys working (G picks Move)
- S-04 a Save the server refuses keeps the studio open with the work in it, one error note, the file as it was
- S-02 an agent writes scene.json meanwhile: Save keeps theirs as a version beside mine, Cancel leaves theirs as written
- S-22 ⌘Z after the studio's Save takes back only the studio's card, another window's card stays
- S-14 the name field is one line: ↵ applies as one step, Esc cancels
- S-20 a row's colour is written into scene.json at once and stays after Cancel
- S-21 Delete with two rows chosen deletes both
- S-13 ⌘Z in the studio is the studio's step, an annotation made there stays
- S-16 a thread on a thing the scene no longer has after Cancel is tied to the card

  HYIMG_REPO=<Hyimg checkout> nice -n 10 python3 -m pytest tests/test_p4_logic.py
"""
import json, time, urllib.request

from PIL import Image
from playwright.sync_api import sync_playwright

from test_canvas_3d import SITE2, board_server, go_on
from test_studio_undo import DOC, wait_doc

CARD = {"type": "model3d", "scene": "3d/scenes/a/scene.json", "camera": "jo1wd256", "x": 0, "y": 0, "w": 500, "h": 500}
ENG = "() => import('/plugins/3d/engine.js')"
LIVE = "() => import('/plugins/3d/engine.js').then(m => m.isLive())"
HOOK = "() => { window.__T = []; const o = window.hyToast; window.hyToast = (t, k, x) => { window.__T.push([String(t), k || '']); return o && o(t, k, x); }; }"
BOARD = """() => JSON.stringify([Object.keys(board.items).sort(), Object.values(board.items).map(i => [i.x, i.y, i.opacity ?? 1]),
  Object.keys(board.groups).length, [Math.round(cam.x), Math.round(cam.y), +cam.z.toFixed(3)]])"""


def launch(p):
    return p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])


def open_board(browser, port):
    page = browser.new_page(viewport={"width": 1600, "height": 1000}, color_scheme="dark")
    errors = []; page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(f"http://127.0.0.1:{port}/canvas.html")
    page.wait_for_function("() => typeof PLGST !== 'undefined' && PLGST.some(p => p.name === '3d' && p.ok)", timeout=20000)
    page.wait_for_function("() => Object.values(board.items).every(i => i.type !== 'model3d' || i.view)", timeout=20000)
    page.wait_for_function("() => !dirty", timeout=10000); page.evaluate(HOOK)
    return page, errors


def studio(page):
    page.dblclick(".plg[data-id=c]", position={"x": 30, "y": 30})
    page.wait_for_selector(".m3r .hy-slider", timeout=60000); page.wait_for_timeout(1200); go_on(page)
    # the camera's flight between the panels has ended, and its second fit once the library folded (Hyimg ui/modes.js, P4 S-61: up to 2 s)
    page.wait_for_timeout(1200); last, same = None, 0
    for _ in range(60):
        page.wait_for_timeout(150); c = page.evaluate("() => [cam.x, cam.y, cam.z].map(v => +v.toFixed(2)).join()")
        same = same + 1 if c == last else 0; last = c
        if same >= 3: break


def eye(page, name):
    page.locator(".m3l .row", has_text=name).first.locator("[data-eye]").click(); page.wait_for_timeout(400)


def board_blur(page): page.evaluate("document.activeElement && document.activeElement.blur(); window.focus()")


def second_window(browser, port, x=0, y=900):
    """another window on the same board adds a picture card and saves it"""
    ctx = browser.new_context(viewport={"width": 1200, "height": 800}, color_scheme="dark"); p2 = ctx.new_page()
    p2.goto(f"http://127.0.0.1:{port}/canvas.html"); p2.wait_for_function("() => typeof board !== 'undefined' && board.items.c", timeout=20000)
    p2.wait_for_timeout(800)
    p2.evaluate(f"() => {{ const b = snap(); board.items.zz = {{ path: 'pics/lib.png', x: {x}, y: {y}, w: 300, ar: 1, crop: null }}; commit(b); render(); }}")
    return ctx


def saved_board(lib): return json.loads((lib.parent / "state/boards/main.json").read_text())


def with_picture(lib):
    (lib / "pics").mkdir(parents=True, exist_ok=True); Image.new("RGB", (300, 300), (120, 40, 160)).save(lib / "pics/lib.png")


def test_discard_keeps_others_work_and_the_question_is_safe(tmp_path):
    port, lib, stop = board_server(tmp_path, {"c": dict(CARD)}, {"a": SITE2}); with_picture(lib)
    scene = lib / "3d/scenes/a/scene.json"; raw0 = scene.read_bytes()
    try:
        with sync_playwright() as p:
            browser = launch(p); page, errors = open_board(browser, port)
            studio(page)
            # S-06: the board's keys wait while the studio is open
            board_blur(page); b0 = page.evaluate(BOARD)
            for k in ("l", "3", "Shift+Digit1", "Meta+a", "Meta+d", "Meta+x"):
                board_blur(page); page.keyboard.press(k); page.wait_for_timeout(250)
                assert page.evaluate(BOARD) == b0, f"{k} changed the board behind 3D Studio"
            assert page.evaluate(LIVE)
            # S-15: after a control of the panels was clicked, G still picks Move
            page.click(".m3l hy-minitoggle[data-raw]"); page.wait_for_timeout(200); page.keyboard.press("g"); page.wait_for_timeout(200)
            assert page.evaluate(ENG + ".then(m => m.liveInfo().tool)") == "translate", "a key after a click on a control did nothing"
            page.click(".m3l hy-minitoggle[data-raw]"); page.keyboard.press("v")
            # the studio's own change, and another window's card meanwhile
            eye(page, "Ключевой")
            ctx2 = second_window(browser, port)
            page.wait_for_function("() => !!board.items.zz", timeout=20000)
            # S-03: Cancel asks; «Keep editing» has the focus and ↵, Esc keeps it too
            page.click("hy-studio-actions [data-a=cancel]"); page.wait_for_selector("#hyConfirm.on", timeout=5000); page.wait_for_timeout(150)
            assert page.evaluate("() => document.activeElement && document.activeElement.dataset.a") == "no"
            page.keyboard.press("Enter"); page.wait_for_timeout(600)
            assert page.evaluate(LIVE) and not page.evaluate("() => !!document.getElementById('hyConfirm')"), "↵ in the question threw the work away"
            page.click("hy-studio-actions [data-a=cancel]"); page.wait_for_selector("#hyConfirm.on", timeout=5000)   # Cancel asks, Esc keeps (S-27)
            page.keyboard.press("Escape"); page.wait_for_timeout(500); assert page.evaluate(LIVE)
            # S-01: Discard: the scene and the card as at the opening, the other window's card stays on the board and in its file
            page.click("hy-studio-actions [data-a=cancel]"); page.wait_for_selector("#hyConfirm.on", timeout=5000); page.wait_for_timeout(300)
            page.click("#hyConfirm [data-a=ok]"); page.wait_for_function("() => !document.querySelector('.plg-live')", timeout=20000)
            page.wait_for_timeout(1500)
            assert page.evaluate("() => !!board.items.zz"), "Discard took another window's card off the board"
            for _ in range(50):
                if "zz" in saved_board(lib)["items"]: break
                time.sleep(0.1)
            assert "zz" in saved_board(lib)["items"], "Discard took another window's card out of the file"
            assert scene.read_bytes() == raw0
            ctx2.close()
            assert not errors, errors
            browser.close()
    finally:
        stop()


def test_save_refused_then_an_outside_write_and_undo(tmp_path):
    port, lib, stop = board_server(tmp_path, {"c": dict(CARD)}, {"a": SITE2}); with_picture(lib)
    scene = lib / "3d/scenes/a/scene.json"; raw0 = scene.read_bytes()
    try:
        with sync_playwright() as p:
            browser = launch(p); page, errors = open_board(browser, port)
            studio(page); eye(page, "Ключевой")
            # S-04: the write refused: the studio stays open with its change, one error note, the file as it was
            page.route("**/api/file?p=3d%2Fscenes%2Fa%2Fscene.json", lambda r: r.fulfill(status=500, body="refused (test)") if r.request.method == "POST" else r.continue_())
            page.evaluate("() => window.__T.splice(0)"); board_blur(page); page.keyboard.press("Meta+Enter"); page.wait_for_timeout(1500)
            assert page.evaluate(LIVE), "a refused Save closed the studio"
            notes = [t for t, k in page.evaluate("() => window.__T.splice(0)")]
            assert len(notes) == 1 and "refused" in notes[0], notes
            assert scene.read_bytes() == raw0 and page.evaluate(DOC)["lights"][0].get("hidden"), "the work stays in the studio"
            page.unroute("**/api/file?p=3d%2Fscenes%2Fa%2Fscene.json")
            # S-02: an agent writes the scene meanwhile; another window adds a card
            d = json.loads(raw0); d["lights"][0]["power"] = 777; d["rev"] = 6; d["by"] = "agent"; theirs = json.dumps(d).encode()
            urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{port}/api/file?p=3d/scenes/a/scene.json", data=theirs, method="POST"))
            ctx2 = second_window(browser, port); page.wait_for_function("() => !!board.items.zz", timeout=20000)
            view0 = page.evaluate("() => board.items.c.view")
            board_blur(page); page.keyboard.press("Meta+Enter"); page.wait_for_function("() => !document.querySelector('.plg-live')", timeout=20000)
            page.wait_for_timeout(800)
            mine = json.loads(scene.read_text())
            assert mine["lights"][0].get("hidden") and mine["rev"] > 6, mine
            kept = lib / "3d/scenes/a/.versions/6.json"
            assert kept.exists() and json.loads(kept.read_text())["lights"][0]["power"] == 777, "theirs is kept as a version"
            # S-22: ⌘Z on the board: the card's own step back, the other window's card stays
            board_blur(page); page.keyboard.press("Meta+z")
            page.wait_for_function("v => JSON.stringify(board.items.c.view) === JSON.stringify(v)", arg=view0, timeout=10000)
            assert page.evaluate("() => !!board.items.zz"), "⌘Z after the studio's Save took another window's card away"
            ctx2.close()
            assert not errors, errors
            browser.close()
    finally:
        stop()


def test_fields_rows_annotations_and_cancel(tmp_path):
    port, lib, stop = board_server(tmp_path, {"c": dict(CARD)}, {"a": SITE2})
    scene = lib / "3d/scenes/a/scene.json"
    threads = lambda: json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/comments?name=main"))["items"]
    try:
        with sync_playwright() as p:
            browser = launch(p); page, errors = open_board(browser, port)
            studio(page)
            # S-20: a row's colour goes into the file at once
            page.locator(".m3l .row", has_text="Ключевой").first.click(button="right"); page.wait_for_selector("#ctx.open", timeout=3000)
            page.locator("#ctx [data-color]").nth(2).click(); page.wait_for_timeout(1200)
            assert json.loads(scene.read_text()).get("ui", {}).get("colors"), "the row's colour was not written"
            # S-14: the name is one line: ↵ applies as one step, Esc cancels
            page.locator(".m3l .row", has_text="Телефон").first.click(); page.wait_for_timeout(400)
            f = page.locator(".m3r .dialkit-text-input").first
            n0 = page.evaluate(ENG + ".then(m => m.histInfo().steps.length)")
            f.click(); f.evaluate("t => t.setSelectionRange(t.value.length, t.value.length)"); page.keyboard.type(" X"); page.wait_for_timeout(500)
            assert page.evaluate(DOC)["objects"][0]["name"] == "Телефон", "each letter was a change"
            page.keyboard.press("Enter"); wait_doc(page, lambda d: d["objects"][0]["name"] == "Телефон X")
            page.wait_for_timeout(600)
            assert page.evaluate(ENG + ".then(m => m.histInfo().steps.length)") == n0 + 1, "one step for the whole name"
            assert f.input_value() == "Телефон X"
            f.click(); page.keyboard.type("YZ"); page.keyboard.press("Escape"); page.wait_for_timeout(500)
            assert page.evaluate(DOC)["objects"][0]["name"] == "Телефон X" and page.evaluate(LIVE)
            # S-21: two cubes, both rows chosen, Delete: both go
            for _ in range(2):
                page.locator("[data-plus]").first.click(); page.wait_for_timeout(200); page.locator(".m3menu [data-add=box]").first.click(); page.wait_for_timeout(900); go_on(page)
            cubes = [o["id"] for o in page.evaluate(DOC)["objects"] if o.get("src", {}).get("shape") == "box"]
            assert len(cubes) == 2
            page.evaluate(f"ids => import('/plugins/3d/engine.js').then(m => m.liveSelect(ids))", cubes)
            board_blur(page); page.keyboard.press("Delete")
            wait_doc(page, lambda d: not any(o.get("src", {}).get("shape") == "box" for o in d["objects"]))
            # S-13: an annotation in the studio, then ⌘Z: the studio's step goes, the annotation stays
            page.locator("[data-plus]").first.click(); page.wait_for_timeout(200); page.locator(".m3menu [data-add=box]").first.click(); page.wait_for_timeout(900); go_on(page)
            cube = [o["id"] for o in page.evaluate(DOC)["objects"] if o.get("src", {}).get("shape") == "box"][0]
            page.evaluate(f"ids => import('/plugins/3d/engine.js').then(m => m.liveSelect(ids))", [cube]); page.wait_for_timeout(300)
            pane = page.evaluate("() => { const r = document.querySelector('canvas.m3live').getBoundingClientRect(); return [r.x, r.y, r.width, r.height]; }")
            spot = page.evaluate("""([x, y, w, h]) => { for (let fy = .2; fy < .9; fy += .05) for (let fx = .2; fx < .9; fx += .05) {
              const px = x + w * fx, py = y + h * fy; if (document.elementFromPoint(px, py) === document.querySelector('canvas.m3live')) return [px, py]; } return null; }""", pane)
            board_blur(page); page.keyboard.press("c"); page.wait_for_timeout(200)
            page.mouse.click(*spot); page.wait_for_selector("#cmthread.open textarea", timeout=5000)
            page.keyboard.type("A note in the studio"); page.keyboard.press("Enter"); page.wait_for_timeout(1000)
            assert len(threads()) == 1
            page.keyboard.press("Escape"); page.wait_for_timeout(200); board_blur(page); page.keyboard.press("Escape"); page.wait_for_timeout(200)
            board_blur(page); page.keyboard.press("Meta+z"); page.wait_for_timeout(1200)
            assert len(threads()) == 1, "⌘Z in the studio deleted the annotation"
            # S-16: a thread on a part this session added (when it has one), Cancel › Discard: tied to the card from then on
            page.locator("[data-plus]").first.click(); page.wait_for_timeout(200); page.locator(".m3menu [data-add=sphere]").first.click(); page.wait_for_timeout(900); go_on(page)
            ball = [o["id"] for o in page.evaluate(DOC)["objects"] if o.get("src", {}).get("shape") == "sphere"][0]
            urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{port}/api/comments", method="POST", data=json.dumps({"op": "new", "name": "main",
                "anchor": {"obj": "c", "kind": "model3d", "file": CARD["scene"], "part": {"kind": "object", "id": ball, "name": "Ball", "local": [0, 0, 0]}},
                "at": [0.5, 0.5], "text": "On the ball"}).encode(), headers={"Content-Type": "application/json"}))
            page.evaluate("() => window.hyComments && hyComments.load && hyComments.load()"); page.wait_for_timeout(800)
            page.click("hy-studio-actions [data-a=cancel]"); page.wait_for_selector("#hyConfirm.on", timeout=5000); page.wait_for_timeout(300)
            page.click("#hyConfirm [data-a=ok]"); page.wait_for_function("() => !document.querySelector('.plg-live')", timeout=20000)
            for _ in range(50):
                on_ball = [t for t in threads() if t["messages"][0]["text"] == "On the ball"]
                if on_ball and "part" not in on_ball[0]["anchor"]: break
                time.sleep(0.1)
            assert on_ball and "part" not in on_ball[0]["anchor"] and on_ball[0]["anchor"]["obj"] == "c", on_ball
            assert json.loads(scene.read_text()).get("ui", {}).get("colors"), "Cancel took the row's colour away"
            assert not errors, errors
            browser.close()
    finally:
        stop()
