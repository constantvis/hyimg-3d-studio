"""Photoshop's eye drag in the 3D studio's outliner (Hyimg's ui/eyedrag.js; owner 2026-10-07: «если я зажимаю глаз ... и потом не
отпуская тяну вниз или вверх мышку, то и другой включается или выключается в зависимости от того, что с initial layer»; and about the
cameras: «и чтобы блокировать можно было камеры таким же образом ... если я вниз тяну за пределы скролла, то оно скроллится дальше»).
On the owner's kind of scene (87 objects, 3 lights, 18 cameras): an eye pressed and dragged over three more objects hides all four, an
object hidden before stays hidden, the scene's undo takes it back in one step; a camera's lock dragged past the bottom of the Cameras
section scrolls it and locks every camera passed, one ⌘Z unlocks them all. Chromium and WebKit.

  HYIMG_REPO=<Hyimg checkout> python3 -m pytest tests/test_eye_drag.py
  M3_SHOTS=<folder> also saves screenshots
"""
import pytest
from playwright.sync_api import sync_playwright

from test_3d_files import ENGINES, open_board
from test_canvas_3d import wait_file
from test_editor_ui import open_editor
from test_outliner_sections import ITEMS, owner, owner_scene, settle, shot  # noqa: F401  (owner is the fixture)


def center(frame, sel):
    b = frame.locator(sel).bounding_box(); return b["x"] + b["width"] / 2, b["y"] + b["height"] / 2


@pytest.mark.parametrize("engine", ENGINES)
def test_eye_drag_hides_objects_and_lock_drag_scrolls_the_cameras(owner, engine, tmp_path):
    scene = tmp_path / "lib/3d/scenes/big/scene.json"
    with sync_playwright() as p:
        browser, page, frame, errors = open_board(p, engine, owner)
        open_editor(frame, "c"); frame.wait_for_function("() => document.querySelectorAll('.m3l .row[data-cam]').length === 18", timeout=30000); settle(frame)
        rows = frame.evaluate("() => [...document.querySelectorAll('.m3l .ms[data-s=objects] .row[data-u]')].slice(0, 4).map(r => r.dataset.u)")
        # the second object hidden first (a click on its eye), then a drag from the first one's eye over the next three
        frame.click(f".m3l .row[data-u='{rows[1]}'] [data-eye]", force=True)
        wait_file(scene, lambda d: d["objects"][1].get("hidden"))
        frame.wait_for_timeout(500)   # the scene's undo keeps that step first
        x, y = center(frame, f".m3l .row[data-u='{rows[0]}'] [data-eye]"); _, y3 = center(frame, f".m3l .row[data-u='{rows[3]}'] [data-eye]")
        page.mouse.move(x, y); page.mouse.down(); page.mouse.move(x + 2, y3, steps=6); page.mouse.up()
        d = wait_file(scene, lambda d: all(o.get("hidden") for o in d["objects"][:4]))
        assert not any(o.get("hidden") for o in d["objects"][4:]), "only the rows passed"
        assert frame.evaluate(f"(us) => us.every(u => document.querySelector(`.m3l .row[data-u='${{u}}']`).classList.contains('hidden'))", rows)
        shot(page, f"eyedrag-objects-{engine}")
        frame.wait_for_timeout(500)
        page.keyboard.press("Meta+z")
        wait_file(scene, lambda d: [bool(o.get("hidden")) for o in d["objects"][:4]] == [False, True, False, False])   # one step: the one hidden before stays

        # Cameras: a lock on hover; dragged from the first one past the section's bottom, the section scrolls to its end and every camera locks
        box = ".m3l .ms[data-s=cameras] .msb"
        assert frame.evaluate(f"() => {{ const b = document.querySelector('{box}'); return b.scrollHeight > b.clientHeight + 40; }}")
        assert frame.locator(".m3l .row[data-cam=c00] [data-lock]").count() == 1
        frame.evaluate(f"() => document.querySelector('{box}').scrollTop = 0"); frame.wait_for_timeout(100)
        bb = frame.locator(box).bounding_box()
        x, y = center(frame, ".m3l .row[data-cam=c00] [data-lock]")
        page.mouse.move(x, y); page.mouse.down(); page.mouse.move(x, bb["y"] + bb["height"] + 30, steps=6)
        frame.wait_for_function(f"() => {{ const b = document.querySelector('{box}'); return b.scrollTop + b.clientHeight >= b.scrollHeight - 1; }}", timeout=10000)
        frame.wait_for_timeout(200); page.mouse.up()
        d = wait_file(scene, lambda d: all(c.get("locked") for c in d["cameras"]))
        assert frame.evaluate("() => [...document.querySelectorAll('.m3l .row[data-cam] [data-lock]')].every(b => b.classList.contains('keep'))")
        shot(page, f"eyedrag-cameras-locked-{engine}")
        frame.wait_for_timeout(500)
        page.keyboard.press("Meta+z")
        wait_file(scene, lambda d: not any(c.get("locked") for c in d["cameras"]) and d["objects"][1].get("hidden") and not d["objects"][0].get("hidden"))   # one step: only the locks
        assert not errors, errors
        browser.close()
