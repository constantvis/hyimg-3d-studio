"""The 3D outliner: chosen rows switch together, a thing's eye and lock are inherited by its parts and never written into them, and what a
lock holds is grey (owner 2026-10-07: «Shift + выбор двух и более объектов, и когда потом нажимаю на lock или глаз, то блокирую все
выбранные или выключаю все выбранные»; «если группу выключаю или включаю lock или глаз, то это не сбрасывает настройки у тех layers, которые
лежат в группе»; «и настройки серым цветом disabled для них, чтобы не было такого, что я могу что-то менять там»).

A model with parts and three boxes: ⌘-click chooses two boxes, a press on one's eye hides both and its lock locks both, one ⌘Z each; a part
hidden by itself stays hidden when its model is hidden and shown again, the other parts' rows dim with a faint eye while the model is
hidden; the model locked: its parts show a faint padlock, a part's panel is grey with «Locked by its group», the model's own with
«Locked». Chromium and WebKit.

  HYIMG_REPO=<Hyimg checkout> python3 -m pytest tests/test_outliner_inherit.py
  M3_SHOTS=<folder> also saves screenshots
"""
import pytest
from playwright.sync_api import sync_playwright

from test_3d_files import ENGINES, open_board
from test_canvas_3d import board_server, wait_file
from test_editor_ui import open_editor
from test_outliner_sections import owner_scene, settle, shot

ITEMS = {"c": {"type": "model3d", "scene": "3d/scenes/big/scene.json", "camera": "c00", "x": 0, "y": 0, "w": 640, "h": 480}}


def scene():
    d = owner_scene()
    d["objects"] = [{"id": "shell", "name": "Vase", "src": {"type": "model", "model": "test-model"}, "loc": [0, 0, 0], "rot": [1, 0, 0, 0], "scale": [1, 1, 1]}] + d["objects"][:3]
    d["cameras"] = d["cameras"][:3]
    return d


def press(page, frame, sel):
    b = frame.locator(sel).bounding_box(); page.mouse.move(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2); page.mouse.down(); page.mouse.up()


@pytest.fixture
def srv(tmp_path):
    port, lib, stop = board_server(tmp_path, ITEMS, {"big": scene()}, lang="en")
    yield port, lib / "3d/scenes/big/scene.json"
    stop()


@pytest.mark.parametrize("engine", ENGINES)
def test_chosen_rows_and_inherited_eyes_and_locks(srv, engine):
    port, path = srv
    with sync_playwright() as p:
        browser, page, frame, errors = open_board(p, engine, port)
        open_editor(frame, "c"); frame.wait_for_function("() => document.querySelectorAll('.m3l .row[data-cam]').length === 3", timeout=30000); settle(frame)
        row = lambda name: f".m3l .ms[data-s=objects] .row:has(> .nm:text-is('{name}'))"
        # 1. Part 1 and Part 2 chosen: one press on Part 2's eye hides both, Part 3 stays; one ⌘Z shows both
        frame.click(row("Part 1") + " .nm"); frame.click(row("Part 2") + " .nm", modifiers=["Meta"]); frame.wait_for_timeout(300)
        assert frame.locator(".m3l .ms[data-s=objects] .row.sel").count() == 2
        frame.wait_for_timeout(500)
        press(page, frame, row("Part 2") + " [data-eye]")
        d = wait_file(path, lambda d: d["objects"][1].get("hidden") and d["objects"][2].get("hidden"))
        assert not d["objects"][3].get("hidden")
        frame.wait_for_timeout(500); page.keyboard.press("Meta+z")
        wait_file(path, lambda d: not any(o.get("hidden") for o in d["objects"]))
        # the lock of a chosen row locks both; a row outside the choice alone (chosen again: an undo may rebuild the scene's nodes)
        frame.wait_for_timeout(500)
        frame.click(row("Part 1") + " .nm"); frame.click(row("Part 2") + " .nm", modifiers=["Shift"]); frame.wait_for_timeout(300)
        assert frame.locator(".m3l .ms[data-s=objects] .row.sel").count() == 2
        frame.wait_for_timeout(500)
        press(page, frame, row("Part 1") + " [data-lock]")
        wait_file(path, lambda d: d["objects"][1].get("locked") and d["objects"][2].get("locked") and not d["objects"][3].get("locked"))
        frame.wait_for_timeout(500); page.keyboard.press("Meta+z")
        wait_file(path, lambda d: not any(o.get("locked") for o in d["objects"]))
        frame.wait_for_timeout(400)

        # 2. the model's parts: one hidden by itself stays hidden through the model's hide and show
        frame.click(row("Vase") + " [data-open]"); frame.wait_for_timeout(500)
        parts = frame.evaluate("() => { const rows = [...document.querySelectorAll('.m3l .ms[data-s=objects] .row[data-u]')]; const i = rows.findIndex(r => r.querySelector('.nm').textContent.startsWith('Vase')); return rows.slice(i + 1).filter(r => r.querySelector('.g')).map(r => r.dataset.u); }")
        assert len(parts) >= 2, parts
        a, b = parts[0], parts[1]
        press(page, frame, f".m3l .row[data-u='{a}'] [data-eye]")
        d = wait_file(path, lambda d: any(v.get("hidden") for v in (d["objects"][0].get("layers") or {}).values()))
        hidden_paths = [k for k, v in d["objects"][0]["layers"].items() if v.get("hidden")]
        frame.wait_for_timeout(500)
        press(page, frame, row("Vase") + " [data-eye]")
        wait_file(path, lambda d: d["objects"][0].get("hidden"))
        frame.wait_for_timeout(400)
        g = frame.evaluate(f"""() => {{ const r = document.querySelector(".m3l .row[data-u='{b}']"), e = r.querySelector('[data-eye]');
          return {{ dim: r.classList.contains('ghid'), inh: e.classList.contains('inh'), op: +getComputedStyle(e).opacity, own: document.querySelector(".m3l .row[data-u='{a}'] [data-eye]").classList.contains('inh') }}; }}""")
        assert g["dim"] and g["inh"] and 0.2 < g["op"] < 0.8 and not g["own"], g
        shot(page, f"inherit-3d-hidden-{engine}")
        frame.wait_for_timeout(500)
        press(page, frame, row("Vase") + " [data-eye]")
        d = wait_file(path, lambda d: not d["objects"][0].get("hidden"))
        assert [k for k, v in d["objects"][0]["layers"].items() if v.get("hidden")] == hidden_paths, "the part keeps its own eye"

        # 3. the model locked: its parts show a faint padlock, a part's panel is grey with the reason, the model's own says «Locked»
        frame.wait_for_timeout(500)
        press(page, frame, row("Vase") + " [data-lock]")
        wait_file(path, lambda d: d["objects"][0].get("locked"))
        frame.wait_for_timeout(500)
        assert frame.locator(f".m3l .row[data-u='{b}'] .inhlk").count() == 1
        frame.click(f".m3l .row[data-u='{b}'] .nm"); frame.wait_for_timeout(500)
        p1 = frame.evaluate("() => ({ why: (document.querySelector('.m3r .m3why') || {}).textContent, dis: document.querySelector('.m3r .dk').classList.contains('m3dis'), pe: getComputedStyle(document.querySelector('.m3r .dk')).pointerEvents })")
        assert p1["why"] == "Locked by its group" and p1["dis"] and p1["pe"] == "none", p1
        for th in ("dark", "light"):
            for d in (page, frame): d.evaluate(f"() => document.documentElement.dataset.theme = '{th}'")
            frame.wait_for_timeout(300)
            shot(page, f"inherit-3d-locked-{th}-{engine}")
        frame.click(row("Vase") + " .nm"); frame.wait_for_timeout(500)
        assert frame.evaluate("() => (document.querySelector('.m3r .m3why') || {}).textContent") == "Locked"
        # unlocked: the panel works again
        press(page, frame, row("Vase") + " [data-lock]")
        wait_file(path, lambda d: not d["objects"][0].get("locked")); frame.wait_for_timeout(500)
        frame.click(row("Vase") + " .nm"); frame.wait_for_timeout(500)
        assert not frame.evaluate("() => document.querySelector('.m3r .m3why')") and not frame.evaluate("() => document.querySelector('.m3r .dk').classList.contains('m3dis')")
        assert not errors, errors
        browser.close()
