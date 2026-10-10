"""The cameras in the 3D studio (owner 2026-10-07):

- «почему я не вижу, какая камера активна?»: the camera the card looks through is marked in CAMERAS whatever is selected (.act: a dot,
  the name at full contrast, the «card» chip); the selected camera keeps the list's selection; a double click on another camera, or the
  Scene panel's Camera select, makes it the active one and the mark follows;
- «почему настройки разные в камере и в начальной главной настройке, Wide ↔ isometric отсутствует»: a camera's own panel and the Scene
  panel show one camera block, the same controls in the same order; Frame is the card's, so for a camera the card does not look through
  it stays greyed with its reason; Wide ↔ isometric works for any camera;
- «Delete» showed the tooltip «Nothing changed»: each action says what it does, Reset's reason is Reset's alone, Delete is not red.
Chromium and WebKit, light and dark, the app's page with the canvas in its frame.

  HYIMG_REPO=<Hyimg checkout> python3 -m pytest tests/test_camera_panel.py
  M3_SHOTS=<folder> also saves screenshots
"""
import json, os

import pytest
from playwright.sync_api import sync_playwright

from test_canvas_3d import board_server, wait_file
from test_3d_files import ENGINES, GL
from test_editor_ui import open_editor
from test_outliner_sections import owner_scene, ITEMS, settle

SHOTS = os.environ.get("M3_SHOTS")


def shot(page, name):
    if SHOTS: os.makedirs(SHOTS, exist_ok=True); page.screenshot(path=os.path.join(SHOTS, name + ".png"))


def scene():
    d = owner_scene(); d["objects"] = d["objects"][:5]; d["cameras"] = d["cameras"][:6]
    for i, c in enumerate(d["cameras"]): c["loc"] = [0.2 * i - 0.5, -1.2, 0.3]
    return d


def open_board(p, engine, port, theme):
    """open_board of test_3d_files in a light or a dark system theme (the app follows it: cv.theme «auto»)"""
    try: browser = getattr(p, engine).launch(args=GL[engine])
    except Exception as error: pytest.skip(f"no {engine} for Playwright: {error}")
    page = browser.new_page(viewport={"width": 1500, "height": 950}, color_scheme=theme)
    errors = []; page.on("pageerror", lambda e: errors.append(f"{e} {(e.stack or '')[:400]}"))
    page.goto(f"http://127.0.0.1:{port}/")
    page.evaluate("() => localStorage.setItem('view', 'canvas')"); page.reload()
    page.wait_for_function("() => document.body.classList.contains('cv-on')")
    frame = None
    for _ in range(200):
        frame = next((f for f in page.frames if "/canvas" in f.url), None)
        if frame: break
        page.wait_for_timeout(100)
    frame.wait_for_function("() => typeof PLGST !== 'undefined' && PLGST.some(p => p.name === '3d' && p.ok)", timeout=30000)
    return browser, page, frame, errors


ROWS = "() => [...document.querySelectorAll('.m3l .row[data-cam]')].map(r => ({ id: r.dataset.cam, act: r.classList.contains('act'), sel: r.classList.contains('sel'), title: r.title }))"
# the camera block's controls in order: selects and sliders by their labels, folders by their titles, up to «Camera: more»
BLOCK = """() => { const out = [];
  for (const e of document.querySelectorAll('.m3r .dk :is(.dialkit-select-label, .hy-slider-l, .dialkit-folder-title-row)')) {
    const w = e.textContent.trim(); if (!w || (out.length && out[out.length - 1] === w)) continue; out.push(w); if (w === 'Camera: more') break; }
  return out.slice(out.indexOf('Camera')); }"""
BUTTONS = "() => [...document.querySelectorAll('.m3r .dk .dialkit-button')].map(b => ({ w: b.textContent.trim(), title: b.title, red: b.classList.contains('hy-reset') && !b.disabled, bg: getComputedStyle(b).backgroundColor, cls: b.className }))"
WANT = ["Camera", "Lens, mm", "Frame", "Wide ↔ isometric", "Camera position", "Distance, cm", "Azimuth, °", "Inclination, °", "Twist, °", "Coordinates"]


def active(rows): return [r["id"] for r in rows if r["act"]]


@pytest.mark.parametrize("engine", ENGINES)
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_the_active_camera_one_camera_block_and_the_actions_say_what_they_do(tmp_path, engine, theme):
    port, lib, stop = board_server(tmp_path, ITEMS, {"big": scene()}, lang="en")
    path = lib / "3d/scenes/big/scene.json"
    try:
        with sync_playwright() as p:
            browser, page, frame, errors = open_board(p, engine, port, theme)
            open_editor(frame, "c"); settle(frame)
            # the Scene panel: the card's camera, the block's controls in order
            rows = frame.evaluate(ROWS)
            assert active(rows) == ["c00"] and not any(r["sel"] for r in rows), rows
            assert "Active camera" in rows[0]["title"] and "icon" in rows[1]["title"], rows   # a click on its icon (P4 S-45)
            scene_block = frame.evaluate(BLOCK)
            assert scene_block[:len(WANT)] == WANT and scene_block[-1] == "Camera: more", scene_block

            # 1. another camera selected: it has the list's selection, the active one keeps its mark; its panel is the same block
            frame.click(".m3l .row[data-cam=c03]"); frame.wait_for_timeout(600)
            rows = frame.evaluate(ROWS)
            assert active(rows) == ["c00"] and [r["id"] for r in rows if r["sel"]] == ["c03"], rows
            # the selected row is the app's selected row, the image editor's selected layer: a fill and a line, still so under the pointer
            # (owner 2026-10-07: «выбранный объект вообще незаметен, должно быть, как вот здесь в эдиторе фото»), in 3D Studio's pink
            # since 2026-10-09 (owner: «конечно», to giving the Studio its colour; tests/test_studio_colour.py)
            SELBG = "() => { const r = document.querySelector('.m3l .row.sel'), cs = getComputedStyle(r); return [cs.backgroundColor, cs.boxShadow]; }"
            bg, ring = frame.evaluate(SELBG)
            import re as _re
            def rgba(x):   # rgb(…) or color(srgb …) as 0–255 and an alpha
                c = _re.search(r"(rgba?|color)\(([^)]*)\)", x); v = [float(n) for n in _re.findall(r"[\d.]+", c.group(2).replace("srgb", ""))]
                k = 255 if c.group(1) == "color" else 1; return [v[0] * k, v[1] * k, v[2] * k, v[3] if len(v) > 3 else 1]
            f = rgba(bg); assert f[0] > f[1] + 100 and f[0] > f[2] + 60 and f[3] > 0.05, ("a pink fill", bg)
            l = rgba(ring); assert "inset" in ring and l[0] > l[1] + 100 and l[0] > l[2] + 60 and l[3] > 0.3, ("a pink line", ring)
            frame.hover(".m3l .row[data-cam=c03]"); frame.wait_for_timeout(250)
            assert frame.evaluate(SELBG)[0] == bg, "a selected row under the pointer stays selected"
            head = frame.evaluate("() => document.querySelector('.m3r .ih').textContent")
            assert "View 4" in head and "active" not in head, head
            assert frame.evaluate(BLOCK) == scene_block, (frame.evaluate(BLOCK), scene_block)
            # Frame is the card's: greyed in its place with its reason, a press opens nothing
            fr = frame.evaluate("""() => { const e = [...document.querySelectorAll('.m3r .dialkit-select-trigger')].find(x => x.querySelector('.dialkit-select-label').textContent.trim() === 'Frame');
              return { na: e.classList.contains('m3na'), aria: e.getAttribute('aria-disabled'), title: e.title, op: +getComputedStyle(e).opacity }; }""")
            assert fr["na"] and fr["aria"] == "true" and "make this camera active" in fr["title"] and fr["op"] < 0.6, fr
            frame.locator(".m3r .dialkit-select-trigger.m3na").click(force=True); frame.wait_for_timeout(300)
            assert frame.locator(".dialkit-select-dropdown").count() == 0 or not frame.locator(".dialkit-select-dropdown").first.is_visible()
            # each action says what it does; Reset's reason is Reset's; Delete is a plain button, not red
            bs = {b["w"]: b for b in frame.evaluate(BUTTONS)}
            assert bs["Delete"]["title"] == "Delete camera" and "hy-reset" not in bs["Delete"]["cls"], bs
            assert bs["Make active"]["title"] == "The card will look through this camera", bs
            assert bs["Reset"]["title"] == "Nothing changed" and [w for w, b in bs.items() if b["title"] == "Nothing changed"] == ["Reset"], bs
            assert bs["Delete"]["bg"] == bs["Make active"]["bg"], ("Delete looks like the other actions", bs)
            shot(page, f"camera-panel-{theme}-{engine}")
            # Wide ↔ isometric moves this camera, not the card's: its lens and its distance change together
            c0 = json.loads(path.read_text())["cameras"]
            frame.evaluate("""() => { const r = [...document.querySelectorAll('.m3r .hy-slider')].find(x => x.querySelector('.hy-slider-l').textContent.trim().startsWith('Wide')),
              i = r.querySelector('input'); i.value = 70; i.dispatchEvent(new Event('input', { bubbles: true })); i.dispatchEvent(new Event('change', { bubbles: true })); }""")
            d = wait_file(path, lambda d: d["cameras"][3]["lens"] != c0[3]["lens"])
            assert d["cameras"][3]["lens"] > c0[3]["lens"] and d["cameras"][3]["loc"] != c0[3]["loc"], (c0[3], d["cameras"][3])
            assert d["cameras"][0]["lens"] == c0[0]["lens"] and d["cameras"][0]["loc"] == c0[0]["loc"], "the card's camera stays"

            # 2. «Make active»: View 4 is the card's camera, the mark moves
            frame.locator(".m3r .dk .dialkit-button", has_text="Make active").click(); frame.wait_for_timeout(800)
            assert active(frame.evaluate(ROWS)) == ["c03"] and frame.evaluate("() => board.items.c.camera") == "c03"
            # 3. a click on another camera row's icon makes it active (a double click renames it, P4 S-45)
            frame.click(".m3l .row[data-cam=c01] > svg"); frame.wait_for_timeout(800)
            assert active(frame.evaluate(ROWS)) == ["c01"] and frame.evaluate("() => board.items.c.camera") == "c01"
            # 4. the Camera select at the top of the camera block (the Scene panel's and a camera's alike) does the same
            trig = frame.locator(".m3r .dialkit-select-trigger", has_text="Camera").first
            trig.click(); frame.locator(".dialkit-select-option", has_text="View 5").first.click(); frame.wait_for_timeout(800)
            rows = frame.evaluate(ROWS)
            assert active(rows) == ["c04"] and frame.evaluate("() => board.items.c.camera") == "c04", rows
            shot(page, f"camera-active-{theme}-{engine}")
            assert not errors, errors
            browser.close()
    finally:
        stop()
