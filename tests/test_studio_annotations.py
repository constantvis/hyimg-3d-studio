"""Annotations on 3D Studio's objects and layers (owner 2026-10-09 on round 15, r15-3d.html and r15-annotations-3d.html liked as drawn: «3D у
нас, естественно, тоже не хватает аннотаций, чтобы можно было так же выделить какой-то слой и комментировать его»). Chromium, dark:

- C takes the Annotation tool (its button in the dock after Pull, in the studio's pink); a click on the phone drops a pin and the board's
  thread window opens; the thread is stored with its anchor: the card, the object's id and name, the point in the object's own axes;
- the pin is round, pink, over the view; the object's row in the tree shows a count of 1; the left block's tabs say Layers and
  Annotations, and the Annotations tab lists the thread under its object;
- the object moved with Move, the pin moves with it; Save puts the thread's place on the card right (op place), so after a reload the
  board's pin is there and the studio's pin is on the object again; hy.py comments names the object;
- Resolve hides the pin and the row's count; Esc leaves the tool.
"""
import json
import os
import subprocess
import sys
import urllib.request

from playwright.sync_api import sync_playwright

from test_canvas_3d import REPO, SITE2, board_server, go_on

CARD = {"type": "model3d", "scene": "3d/scenes/a/scene.json", "camera": "jo1wd256", "x": 0, "y": 0, "w": 500, "h": 500}
GL = ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"]
# the pin's point: its sharp bottom left corner (Hyimg ui/hy/apin.css, owner 2026-10-10: «круг с уголком внизу слева»)
PIN = "() => { const b = document.querySelector('.hy-spins .hy-spin'); if (!b) return null; const r = b.getBoundingClientRect(); return [r.x, r.y + r.height]; }"
OBJ = SITE2["objects"][0]


def threads(port):
    return json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/comments?name=main"))["items"]


def open_studio(page, port):
    page.goto(f"http://127.0.0.1:{port}/canvas.html")
    page.wait_for_function("() => typeof PLGST !== 'undefined' && PLGST.some(p => p.name === '3d' && p.ok)", timeout=20000)
    page.dblclick(".plg[data-id=c]", position={"x": 30, "y": 30}); page.wait_for_selector(".m3r .hy-slider", timeout=60000)
    page.wait_for_timeout(1200); go_on(page)
    last, same = None, 0   # the camera's flight between the panels and its second fit have ended (Hyimg ui/modes.js, P4 S-61)
    for _ in range(60):
        page.wait_for_timeout(150); c = page.evaluate("() => [cam.x, cam.y, cam.z].map(v => +v.toFixed(2)).join()")
        same = same + 1 if c == last else 0; last = c
        if same >= 3: break


def test_an_annotation_on_an_object_follows_it(tmp_path):
    port, lib, stop = board_server(tmp_path, {"c": dict(CARD)}, {"a": SITE2}, lang="en")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=GL)
            page = browser.new_page(viewport={"width": 1600, "height": 1000}, color_scheme="dark")
            errors = []; page.on("pageerror", lambda e: errors.append(str(e)))
            open_studio(page, port)
            # the dock's Annotation after Pull, the left block's tabs
            assert page.evaluate("() => { const b = document.querySelector('.m3t [data-ann]'); return !!b && b.previousElementSibling.dataset.tool === 'smart'; }")
            assert page.locator(".m3l .m3ltabs [data-ltab]").all_inner_texts()[0].startswith("Layers")
            # C: the tool; a click on the phone in the middle of the view
            page.keyboard.press("c"); page.wait_for_timeout(150)
            assert page.evaluate("() => document.querySelector('.m3t [data-ann]').classList.contains('on')")
            bb = page.locator("canvas.m3live").bounding_box(); x, y = bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2
            page.mouse.click(x, y); page.wait_for_selector("#cmthread.open textarea", timeout=5000)
            assert OBJ["name"] in page.locator("#cmthread .cm-w").inner_text()
            page.keyboard.type("Thinner edge"); page.keyboard.press("Enter"); page.wait_for_timeout(900)
            ts = threads(port); assert len(ts) == 1, ts
            an = ts[0]["anchor"]
            assert an["obj"] == "c" and an["part"]["kind"] == "object" and an["part"]["id"] == OBJ["id"] and an["part"]["name"] == OBJ["name"], an
            assert len(an["part"]["local"]) == 3
            # the pin: Hyimg's one annotation pin (a bubble, its bottom left corner sharp and on the click), the studio's pink; the row's count,
            # compact; the Annotations tab
            page.wait_for_function("() => document.querySelectorAll('.hy-spins .hy-spin').length === 1 && getComputedStyle(document.querySelector('.hy-spin')).visibility === 'visible'")
            look = page.evaluate("() => { const b = document.querySelector('.hy-spin'), c = getComputedStyle(b), p = document.createElement('i'); p.style.color = 'var(--pink)';"
                                 " document.body.append(p); const k = getComputedStyle(p).color; p.remove(); return [c.borderRadius, c.backgroundColor, k, b.offsetWidth, b.offsetHeight]; }")
            assert look[0].endswith(" 3px") and look[0].startswith("999px") and look[1] == look[2] and look[4] == 24, look
            pin = page.evaluate(PIN); assert abs(pin[0] - x) < 1.5 and abs(pin[1] - y) < 1.5, (pin, x, y)
            nb = page.evaluate(f"() => {{ const r = document.querySelector('.m3l .row[data-k=\"{OBJ['id']}\"] [data-ann-n]').getBoundingClientRect(); return r.height; }}")
            assert nb <= 16, f"a row's count is no taller than its lock and eye: {nb}"
            assert page.evaluate(f"() => document.querySelector('.m3l .row[data-k=\"{OBJ['id']}\"] [data-ann-n]').textContent") == "1"
            page.keyboard.press("Escape"); page.wait_for_timeout(150)   # the thread's window
            page.click('.m3ltabs [data-ltab="ann"]'); page.wait_for_timeout(300)
            assert page.locator(".m3ann .at .ah b").all_inner_texts() == [OBJ["name"]] and "Thinner edge" in page.locator(".m3ann .an").inner_text()
            page.click('.m3ltabs [data-ltab="layers"]'); page.wait_for_timeout(200)
            # Esc leaves the tool; Move drags the phone, the pin goes along
            page.mouse.click(bb["x"] - 20, bb["y"] + 200); page.keyboard.press("Escape"); page.wait_for_timeout(150)
            assert not page.evaluate("() => document.querySelector('.m3t [data-ann]').classList.contains('on')")
            page.click('.m3t [data-tool="translate"]')
            page.mouse.move(x + 40, y + 120); page.mouse.down()
            for i in range(1, 9): page.mouse.move(x + 40 + 90 * i / 8, y + 120 - 40 * i / 8); page.wait_for_timeout(30)
            page.mouse.up(); page.wait_for_timeout(600)
            pin2 = page.evaluate(PIN); assert abs(pin2[0] - pin[0] - 90) < 12 and abs(pin2[1] - pin[1] + 40) < 12, (pin, pin2)
            # Save: the place on the card follows (op place); hy.py comments names the object
            card = page.evaluate("() => { const r = document.querySelector('.plg[data-id=c]').getBoundingClientRect(); return [r.x, r.y, r.width, r.height]; }")
            page.keyboard.press("Meta+Enter"); page.wait_for_timeout(1500)   # the card as the studio showed it: leaving flies the board back (S-61)
            t1 = threads(port)[0]
            assert abs(t1["at"][0] - (pin2[0] - card[0]) / card[2]) < 0.01 and abs(t1["at"][1] - (pin2[1] - card[1]) / card[3]) < 0.01, (t1["at"], pin2, card)
            out = subprocess.run([sys.executable, str(REPO / "review/hy.py"), "comments"], env={**os.environ, "HYIMG_PORT": str(port)},
                                 capture_output=True, text=True, timeout=60).stdout
            assert f"объект 3D-сцены «{OBJ['name']}» (object {OBJ['id']}" in out and "Thinner edge" in out, out
            # after a reload: the board's pin on the moved place, the studio's on the object
            page.reload(); page.wait_for_function("() => typeof PLGST !== 'undefined' && PLGST.some(p => p.name === '3d' && p.ok)", timeout=20000)
            page.wait_for_function("() => document.querySelectorAll('#cmpins .cmpin').length === 1", timeout=15000)
            bp = page.evaluate("() => { const b = document.querySelector('#cmpins .cmpin'); return [parseFloat(b.style.left), parseFloat(b.style.top)]; }")
            assert abs(bp[0] - t1["at"][0] * 500) < 1 and abs(bp[1] - t1["at"][1] * 500) < 1, bp
            page.dblclick(".plg[data-id=c]", position={"x": 30, "y": 30}); page.wait_for_selector(".m3r .hy-slider", timeout=60000); page.wait_for_timeout(1500); go_on(page)
            page.wait_for_function("() => document.querySelectorAll('.hy-spins .hy-spin').length === 1", timeout=10000)
            pin3 = page.evaluate(PIN); assert abs(pin3[0] - pin2[0]) < 3 and abs(pin3[1] - pin2[1]) < 3, (pin2, pin3)
            # the count opens the thread; Resolve hides the pin and the count
            page.click(f".m3l .row[data-k='{OBJ['id']}'] [data-ann-n]"); page.wait_for_selector("#cmthread.open", timeout=5000)
            page.click("#cmthread [data-cm=resolve]"); page.wait_for_timeout(800)
            assert page.evaluate("() => document.querySelectorAll('.hy-spins .hy-spin').length") == 0
            assert page.evaluate("() => document.querySelectorAll('.m3l [data-ann-n]').length") == 0
            assert threads(port)[0]["resolved"]
            assert not errors, errors
            browser.close()
    finally:
        stop()
