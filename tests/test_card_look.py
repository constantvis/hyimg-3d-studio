"""A 3D card is a picture for the board's looks (owner 2026-10-06: «why can't I make a 3D object more transparent, like a picture ...
and lay a colour grade over it? In the end it is a picture, even when it is rendered»). On a real canvas with the frames plugin beside
this one, in Chromium and WebKit:

- opacity: the bar's slider and the keys 1…9, 0 fade the whole 3D card, saved, one step to undo, carried by «Copy/Paste properties»;
- Raw Editor: the bar's button opens the same panel as on a picture, the grade changes the card's pixels exactly as the same grade
  changes a picture of the same file (pixel compare), the mark shows, copy and paste go picture → 3D and 3D → picture, undo;
- the grade belongs to the card, not to one frame of it (owner 2026-10-06: «if the render finished, my grade is always laid over it»):
  a new render arriving (the card's Blender still replaced, a Blender frame over the live view), the live three.js view while the camera
  turns, all graded with no extra step;
- «Render» in the Blender plate puts the final frame on the board as a picture that carries the card's grade as its own property (the
  file is never graded). The Blender bridge is answered by the test (page.route), no Blender is needed.

  HYIMG_REPO=<Hyimg checkout> HYIMG_FRAMES=<hyimg-frames checkout> python3 -m pytest tests/test_card_look.py
  HYIMG_SHOTS=<folder> also saves screenshots
"""
import hashlib, json, os, subprocess, sys, time, urllib.request, uuid
from pathlib import Path

import pytest
from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright

from test_canvas_3d import REPO, HERE, SITE2, tiny_model, free_port, go_on, CORNER

FRAMES = Path(os.environ.get("HYIMG_FRAMES", HERE.parent / "hyimg-frames"))
WEBKIT = any(Path(os.path.expanduser("~/Library/Caches/ms-playwright")).glob("webkit-*"))
ENGINES = ["chromium", "webkit"]
SHOTS = os.environ.get("HYIMG_SHOTS")
GRADE = {"exposure": 0.9, "contrast": 35, "temp": 55, "saturation": 40}
GRADED = "() => window.__gradeQ && __gradeQ() === 0"
STUDIO = dict(SITE2, studio={"angles": {"jo1wd256": {"look": "L1"}}})


def picture(w, h, a, b):   # a gradient with a light square: something to see
    im = Image.new("RGB", (w, h)); d = ImageDraw.Draw(im)
    for y in range(h): d.line([(0, y), (w, y)], fill=tuple(int(a[k] + (b[k] - a[k]) * y / h) for k in range(3)))
    d.rectangle([w // 4, h // 4, w // 2, h // 2], fill=(235, 235, 235)); return im


@pytest.fixture
def look(tmp_path):
    lib, state, plugins = tmp_path / "lib", tmp_path / "state", tmp_path / "plugins"
    tiny_model(lib)
    for n, doc in (("a", SITE2), ("s", STUDIO)):
        (lib / f"3d/scenes/{n}").mkdir(parents=True); (lib / f"3d/scenes/{n}/scene.json").write_text(json.dumps(doc))
    (lib / "pics").mkdir()
    picture(600, 400, (190, 60, 40), (240, 190, 90)).save(lib / "pics/a.png")
    picture(600, 400, (30, 60, 190), (90, 200, 230)).save(lib / "pics/b.png")
    card = lambda n, x, w, h, y=0, **k: {"type": "model3d", "scene": f"3d/scenes/{n}/scene.json", "camera": "jo1wd256", "x": x, "y": y, "w": w, "h": h, **k}
    items = {"p1": {"path": "pics/a.png", "x": 0, "y": 0, "w": 300, "ar": 1.5, "crop": None},
             "p2": {"path": "pics/b.png", "x": 0, "y": 260, "w": 300, "ar": 1.5, "crop": None},
             # a card shown in Blender: at rest its last Blender frame, here the very file of p1
             "m1": card("a", 340, 300, 200, render="EEVEE", blenderStill="pics/a.png"),
             "m2": card("a", 680, 300, 200),
             "m3": card("s", 340, 300, 300, y=240)}
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
        yield port, lib, state
    finally:
        proc.terminate(); proc.wait(5); log.close()


def open_board(p, port, engine, theme=None):
    if engine == "webkit": browser = p.webkit.launch()
    else: browser = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
    page = browser.new_page(viewport={"width": 1500, "height": 950}, color_scheme=theme or "light")
    errors = []; page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(f"http://127.0.0.1:{port}/canvas.html", wait_until="domcontentloaded")
    page.wait_for_function("() => typeof PLGST !== 'undefined' && ['3d', 'frames'].every(n => PLGST.some(p => p.name === n && p.ok))", timeout=30000)
    page.evaluate("() => { cam.x = -60; cam.y = -60; cam.z = 1; renderCam(); render(); }")
    # every 3D card shows its still (m2, m3 are drawn by three.js first)
    page.wait_for_function("() => [...document.querySelectorAll('.plg[data-type=model3d] img.m3')].filter(i => i.complete && i.naturalWidth).length === 3", timeout=60000)
    return browser, page, errors


def sha(p): return hashlib.sha1(Path(p).read_bytes()).hexdigest()


def board(state): return json.loads((state / "boards/main.json").read_text())


def shot(page, name):
    if SHOTS: Path(SHOTS).mkdir(parents=True, exist_ok=True); page.screenshot(path=str(Path(SHOTS) / name))


# a card's pixels, small: what it shows (src: the element the plugin draws its picture in, else the graded canvas over it), w × h
PIX = """([id, which, w, h]) => { const el = document.querySelector(`#items [data-id="${id}"]`); if (!el) return null;
  const src = which === 'grd' ? el.querySelector(':scope > canvas.grd') : el.querySelector(which); if (!src || !(src.naturalWidth || src.width)) return null;
  const c = document.createElement('canvas'); c.width = w; c.height = h; const x = c.getContext('2d', { willReadFrequently: true });
  x.drawImage(src, 0, 0, w, h); return [...x.getImageData(0, 0, w, h).data]; }"""


def pix(page, id, which, w=24, h=16):
    return page.evaluate(PIX, [id, which, w, h])


def diff(a, b):
    """the mean difference per channel of two pictures of the same size (alpha left out)"""
    assert a and b and len(a) == len(b), (a and len(a), b and len(b))
    n = len(a) // 4
    return sum(abs(a[i] - b[i]) for i in range(len(a)) if i % 4 != 3) / (3 * n)


def put_grade(page, ids, g=GRADE):
    """the grade put on cards as a paste of properties does it (one step), then drawn"""
    page.evaluate("([ids, g]) => pasteProps({ grade: g }, ids, null, 'grade')", [ids, g])
    page.wait_for_function("ids => ids.every(id => board.items[id].grade)", arg=ids)
    page.wait_for_function(GRADED); page.wait_for_timeout(150); page.wait_for_function(GRADED)


@pytest.mark.parametrize("engine", ENGINES)
def test_opacity_on_a_3d_card(look, engine):
    if engine == "webkit" and not WEBKIT: pytest.skip("no Playwright WebKit")
    port, lib, state = look
    with sync_playwright() as p:
        browser, page, errors = open_board(p, port, engine)
        page.evaluate("() => { sel = new Set(['m2']); render(); }"); page.wait_for_timeout(300)
        # the bar over one 3D card has the pictures' opacity plate
        assert page.locator(".tidy [data-op]").count() == 1, page.evaluate("() => document.querySelector('#handles').innerHTML")
        page.evaluate("() => { const i = document.querySelector('.tidy [data-op]'); i.value = 50; i.dispatchEvent(new Event('input', { bubbles: true })); i.dispatchEvent(new Event('change', { bubbles: true })); }")
        assert page.evaluate("() => board.items.m2.opacity") == 0.5
        page.wait_for_function("() => getComputedStyle(document.querySelector('.plg[data-id=m2]')).opacity === '0.5'")
        page.wait_for_function("() => !dirty", timeout=10000)
        for _ in range(50):
            if board(state)["items"]["m2"].get("opacity") == 0.5: break
            time.sleep(0.1)
        assert board(state)["items"]["m2"].get("opacity") == 0.5, "saved"
        page.keyboard.press("Meta+z")
        page.wait_for_function("() => board.items.m2.opacity === undefined && getComputedStyle(document.querySelector('.plg[data-id=m2]')).opacity === '1'")
        page.keyboard.press("Digit3")   # the keys 1…9 and 0, as on a picture
        page.wait_for_function("() => board.items.m2.opacity === 0.3 && getComputedStyle(document.querySelector('.plg[data-id=m2]')).opacity === '0.3'")
        # Copy/Paste properties: the opacity kind applies to a 3D card, goes 3D → picture and picture → 3D
        assert page.evaluate("() => appliesTo(PROPS.get('opacity'), board.items.m2)") is True
        page.evaluate("() => { copyProps('m2', ['opacity']); const c = propsClip(); return pasteProps(c.kinds, ['p1'], c.src, null, c); }")
        page.wait_for_function("() => board.items.p1.opacity === 0.3")
        page.evaluate("() => { board.items.p1.opacity = 0.6; copyProps('p1', ['opacity']); const c = propsClip(); return pasteProps(c.kinds, ['m1'], c.src, null, c); }")
        page.wait_for_function("() => board.items.m1.opacity === 0.6 && getComputedStyle(document.querySelector('.plg[data-id=m1]')).opacity === '0.6'")
        # the whole card fades, also while it is edited (the live three.js view in it)
        page.evaluate("() => { sel = new Set(); render(); }")
        page.dblclick(".plg[data-id=m2]", position=CORNER); page.wait_for_selector(".plg[data-id=m2] canvas.m3live", timeout=30000); go_on(page)
        assert page.evaluate("() => getComputedStyle(document.querySelector('.plg[data-id=m2]')).opacity") == "0.3"
        assert not errors, errors
        browser.close()


@pytest.mark.parametrize("engine", ENGINES)
def test_raw_editor_on_a_3d_card_like_a_picture(look, engine):
    if engine == "webkit" and not WEBKIT: pytest.skip("no Playwright WebKit")
    port, lib, state = look
    with sync_playwright() as p:
        browser, page, errors = open_board(p, port, engine)
        page.evaluate("() => { sel = new Set(['m1']); render(); }"); page.wait_for_timeout(300)
        btn = page.locator('.tidy button.ic[aria-label="Raw Editor"]')
        assert btn.count() == 1, page.evaluate("() => document.querySelector('#handles').innerHTML")
        btn.click(); page.wait_for_selector("#hcgp.in .hcg", timeout=10000)
        page.locator("#hcgp .hcg-pbtn").first.evaluate("b => b.click()")
        page.locator('#hcgp .hcg-menu.open button[data-k="Punchy"]').first.evaluate("b => b.click()")   # by its English key: the label is in the page's language
        page.wait_for_function("() => board.items.m1.grade && board.items.m1.grade.contrast === 26", timeout=20000)
        page.wait_for_function("() => past.length && !dirty", timeout=10000)
        page.wait_for_function(GRADED)
        assert diff(pix(page, "m1", "grd"), pix(page, "m1", "img.m3")) > 3, "the 3D card's picture is graded"
        page.keyboard.press("Escape"); page.wait_for_function("() => !document.querySelector('#hcgp')", timeout=5000)
        # the grade's mark on the 3D card, by the marks' law (top right), a click on it opens the grading
        page.evaluate("() => { sel = new Set(); render(); }")
        page.wait_for_function("""() => { const m = document.querySelector('.plg[data-id=m1] > .mk-grade'); if (!m) return false; const s = getComputedStyle(m);
          return s.display !== 'none' && +s.opacity > .9 && m.getBoundingClientRect().width > 8; }""", timeout=5000)
        # undo takes the grade back, the card shows its picture as it is; redo brings it back
        page.keyboard.press("Meta+z")
        page.wait_for_function("() => !board.items.m1.grade && !document.querySelector('.plg[data-id=m1] > canvas.grd')")
        page.keyboard.press("Meta+Shift+z")
        page.wait_for_function("() => board.items.m1.grade && board.items.m1.grade.contrast === 26"); page.wait_for_function(GRADED)
        # the same strong grade on the picture p1 and the 3D card m1 that shows the same file: the same pixels
        put_grade(page, ["p1", "m1", "m2"])
        a, b = pix(page, "p1", "grd"), pix(page, "m1", "grd")
        assert diff(a, pix(page, "p1", "img")) > 12, "the picture is graded"
        assert diff(a, b) < 4, f"a picture and a 3D card with one grade look the same: {diff(a, b):.2f}"
        # the three.js still of a 3D card is graded too
        assert diff(pix(page, "m2", "grd"), pix(page, "m2", "img.m3")) > 8
        cover = page.evaluate("""() => { const el = document.querySelector('.plg[data-id=m2]'), r = el.getBoundingClientRect(), c = el.querySelector(':scope > canvas.grd').getBoundingClientRect();
          return Math.abs(c.left - r.left) < 1 && Math.abs(c.right - r.right) < 1 && Math.abs(c.top - r.top) < 1 && Math.abs(c.bottom - r.bottom) < 1; }""")
        assert cover, "the graded picture covers the 3D card"
        for theme in ("light", "dark"):   # the screenshots to look at: a picture and a 3D card graded alike, a 3D card at 50 %
            page.emulate_media(color_scheme=theme)
            page.evaluate("() => { board.items.m3.opacity = 0.5; render(); }"); page.wait_for_timeout(400)
            shot(page, f"look-{engine}-{theme}.png")
        page.evaluate("() => { delete board.items.m3.opacity; render(); }")
        # copy and paste of the grade: 3D → picture and picture → 3D, each one step
        page.evaluate("() => { copyProps('m1', ['grade']); const c = propsClip(); return pasteProps(c.kinds, ['p2'], c.src, null, c); }")
        page.wait_for_function("() => JSON.stringify(board.items.p2.grade) === JSON.stringify(board.items.m1.grade)")
        page.evaluate("() => { board.items.p2.grade = { exposure: -0.8 }; copyProps('p2', ['grade']); const c = propsClip(); return pasteProps(c.kinds, ['m3'], c.src, null, c); }")
        page.wait_for_function("() => board.items.m3.grade && board.items.m3.grade.exposure === -0.8"); page.wait_for_function(GRADED)
        assert page.evaluate("() => appliesTo(PROPS.get('grade'), board.items.m3)") is True
        assert diff(pix(page, "m3", "grd"), pix(page, "m3", "img.m3")) > 5
        page.keyboard.press("Meta+z")
        page.wait_for_function("() => !board.items.m3.grade && !document.querySelector('.plg[data-id=m3] > canvas.grd')")
        page.wait_for_function("() => !dirty", timeout=10000)
        for _ in range(50):
            if board(state)["items"]["m1"].get("grade") == GRADE: break
            time.sleep(0.1)
        assert board(state)["items"]["m1"].get("grade") == GRADE, "the grade is saved on the 3D card"
        assert not errors, errors
        browser.close()


@pytest.mark.parametrize("engine", ENGINES)
def test_the_grade_follows_every_new_render(look, engine):
    """«if the render finished, my grade is always laid over it»: the grade is the card's, whatever picture it shows next"""
    if engine == "webkit" and not WEBKIT: pytest.skip("no Playwright WebKit")
    port, lib, state = look
    with sync_playwright() as p:
        browser, page, errors = open_board(p, port, engine)
        put_grade(page, ["m1", "p2", "m2"])
        # a finished Blender render arrives: the card's still is now another file (pics/b.png); it is graded as p2 (the same file) is
        page.evaluate("() => { board.items.m1.blenderStill = 'pics/b.png'; render(); }")
        page.wait_for_function("() => (document.querySelector('.plg[data-id=m1] img.m3').src || '').includes('b.png') && document.querySelector('.plg[data-id=m1] img.m3').complete", timeout=10000)
        page.wait_for_timeout(300); page.wait_for_function(GRADED)
        new, want = pix(page, "m1", "grd"), pix(page, "p2", "grd")
        assert diff(new, want) < 4, f"the new render is graded: {diff(new, want):.2f}"
        # the live three.js view while it is edited: graded, and still graded after the camera turned
        page.dblclick(".plg[data-id=m2]", position=CORNER); page.wait_for_selector(".plg[data-id=m2] canvas.m3live", timeout=30000); go_on(page)
        page.wait_for_timeout(500); page.wait_for_function(GRADED)
        live = lambda: pix(page, "m2", "canvas.m3live")
        before = pix(page, "m2", "grd")
        assert diff(before, live()) > 8, "the live view is graded"
        order = page.evaluate("() => { const el = document.querySelector('.plg[data-id=m2]'), cv = el.querySelector(':scope > canvas.grd'), lv = el.querySelector('canvas.m3live'); return !!cv && !!(lv.compareDocumentPosition(cv) & Node.DOCUMENT_POSITION_FOLLOWING); }")
        assert order, "the graded picture lies over the live view"
        r = page.locator(".plg[data-id=m2] canvas.m3live").bounding_box()
        x0, y0 = r["x"] + 60, r["y"] + 30   # the card's top left: the background, clear of the model and of the editor's panels
        assert page.evaluate(f"() => document.elementFromPoint({x0}, {y0}).matches('canvas.m3live')")
        page.keyboard.down("Alt"); page.mouse.move(x0, y0); page.mouse.down()   # ⌥: the camera, in every tool (tools.js)
        for i in range(1, 9): page.mouse.move(x0 - 10 * i, y0); page.wait_for_timeout(40)
        page.wait_for_timeout(100)
        during = pix(page, "m2", "grd")
        assert diff(during, before) > 1, "the grade follows the turning camera"
        assert diff(during, live()) > 8, "while the camera turns the view stays graded"
        page.mouse.up(); page.keyboard.up("Alt"); page.wait_for_timeout(300); go_on(page)
        # a Blender frame over the live view (blender.js shows it in img.m3bimg): the grade goes over it
        page.evaluate("""() => { const el = document.querySelector('.plg[data-id=m2]'), i = document.createElement('img'); i.className = 'm3bimg'; i.hidden = true; el.appendChild(i);
          i.src = '/file?p=pics%2Fb.png'; i.onload = () => { i.hidden = false; }; }""")
        page.wait_for_function("() => { const i = document.querySelector('.plg[data-id=m2] img.m3bimg'); return i && !i.hidden && i.complete; }")
        page.wait_for_timeout(300); page.wait_for_function(GRADED)
        on = page.evaluate("""() => { const el = document.querySelector('.plg[data-id=m2]'), cv = el.querySelector(':scope > canvas.grd'), b = el.querySelector('img.m3bimg');
          return !!(b.compareDocumentPosition(cv) & Node.DOCUMENT_POSITION_FOLLOWING) && +getComputedStyle(cv).zIndex >= +getComputedStyle(b).zIndex; }""")
        assert on, "the graded picture lies over Blender's frame"
        g, w = pix(page, "m2", "grd", 24, 24), pix(page, "p2", "grd", 24, 24)
        assert diff(g, w) < 6, f"Blender's frame is graded as the same picture is: {diff(g, w):.2f}"
        assert not errors, errors
        browser.close()


def test_render_saves_a_picture_that_carries_the_grade(look):
    """«Render» in the Blender plate: the final frame is a new picture beside the card, with the card's grade as its own property"""
    port, lib, state = look
    calls = []

    def bridge(route):
        body = json.loads(route.request.post_data or "{}"); calls.append(body.get("action"))
        ans = {"look": {"id": "L1", "key": "k1", "source": "pointer"}, "final": {"job": "j1"},
               "job": {"state": "done", "saved": {"path": "pics/b.png", "ar": 1.5}, "elapsed": 1}}.get(body.get("action"))
        route.fulfill(status=200 if ans else 400, content_type="application/json", body=json.dumps(ans or {"error": "not in this test"}))

    with sync_playwright() as p:
        browser, page, errors = open_board(p, port, "chromium")
        page.route("**/api/plugin/*/blender", bridge)
        put_grade(page, ["m3"]); b0 = sha(lib / "pics/b.png")
        page.dblclick(".plg[data-id=m3]", position=CORNER); page.wait_for_selector(".m3bplate [data-ok]", timeout=30000); go_on(page)
        n0 = page.evaluate("() => Object.keys(board.items).length")
        page.click(".m3bplate [data-ok]")
        page.wait_for_function(f"() => Object.keys(board.items).length === {n0 + 1}", timeout=15000)
        new = page.evaluate("() => { const id = Object.keys(board.items).pop(); return [id, board.items[id]]; }")
        assert new[1]["path"] == "pics/b.png" and new[1].get("grade") == GRADE, new
        assert "final" in calls
        page.wait_for_function(GRADED)
        assert diff(pix(page, new[0], "grd"), pix(page, new[0], "img")) > 12, "the new picture shows graded, its file is not"
        assert sha(lib / "pics/b.png") == b0, "the render's file is not graded"
        assert not errors, errors
        browser.close()
