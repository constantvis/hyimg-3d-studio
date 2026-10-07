"""The 3D outliner's row colours (owner 2026-10-07: «в layers при нажатии правой кнопки добавить colors как в notes ... и так в любых: 3D
editor, image editor»; «multi-selection applies to all selected rows»).

A right click on a row opens the app's menu with the swatch row first («no colour» its first swatch); a swatch colours the row and the
colour lands in scene.json ui.colors under the row's key: an object's or a light's or a camera's id, «<object id>/<layer path>» for a part
of a model. With several rows chosen (⌘ click) a right click on one of them colours them all, across the sections; a right click on a row
outside the choice colours that row alone. Chromium and WebKit.

  HYIMG_REPO=<Hyimg checkout> python3 -m pytest tests/test_outliner_colors.py
  M3_SHOTS=<folder> also saves screenshots
"""
import pytest
from playwright.sync_api import sync_playwright

from test_3d_files import ENGINES, open_board
from test_canvas_3d import board_server, wait_file
from test_editor_ui import open_editor
from test_outliner_inherit import scene
from test_outliner_sections import settle, shot

ITEMS = {"c": {"type": "model3d", "scene": "3d/scenes/big/scene.json", "camera": "c00", "x": 0, "y": 0, "w": 640, "h": 480}}
HEX = {"blue": "#7dbbf5", "green": "#7fd49b", "red": "#ef6a6a"}


@pytest.fixture
def srv(tmp_path):
    port, lib, stop = board_server(tmp_path, ITEMS, {"big": scene()}, lang="en")
    yield port, lib / "3d/scenes/big/scene.json"
    stop()


def colors(d): return (d.get("ui") or {}).get("colors") or {}


def menu(frame, sel):
    """right click on a row: the board's menu opens with the swatch row first, «no colour» first in it"""
    frame.click(sel, button="right"); frame.wait_for_selector("#ctx.open .msw button[data-color=blue]")
    first = frame.evaluate("() => { const f = document.querySelector('#ctx.open').firstElementChild; return { msw: f.classList.contains('msw'), c: f.querySelector('button').dataset.color }; }")
    assert first == {"msw": True, "c": ""}, first


def pick(frame, color):
    frame.click(f"#ctx.open .msw button[data-color='{color}']"); frame.wait_for_timeout(300)
    assert not frame.evaluate("() => document.getElementById('ctx').classList.contains('open')")


@pytest.mark.parametrize("engine", ENGINES)
def test_a_row_and_all_chosen_rows_take_a_colour_into_the_scene_file(srv, engine):
    port, path = srv
    with sync_playwright() as p:
        browser, page, frame, errors = open_board(p, engine, port)
        open_editor(frame, "c"); frame.wait_for_function("() => document.querySelectorAll('.m3l .row[data-cam]').length === 3", timeout=30000); settle(frame)
        obj = lambda name: f".m3l .ms[data-s=objects] .row:has(> .nm:text-is('{name}'))"
        light = lambda name: f".m3l .ms[data-s=lights] .row:has(> .nm:text-is('{name}'))"
        cam = lambda cid: f".m3l .row[data-cam='{cid}']"
        tint = lambda sel: frame.locator(sel).evaluate("r => r.classList.contains('nc') ? r.style.getPropertyValue('--nc') : ''")

        # 1. one row: the swatch row first, blue colours it and lands in the file under the object's id
        menu(frame, obj("Part 1") + " .nm"); pick(frame, "blue")
        wait_file(path, lambda d: colors(d) == {"o000": "blue"})
        assert tint(obj("Part 1")) == HEX["blue"]

        # 2. several chosen rows across the sections (two objects, a light, a camera): a right click on one of them colours all four
        frame.click(obj("Part 2") + " .nm"); frame.click(obj("Part 3") + " .nm", modifiers=["Meta"])
        frame.click(light("Key") + " .nm", modifiers=["Meta"]); frame.click(cam("c01") + " .nm", modifiers=["Meta"]); frame.wait_for_timeout(300)
        assert frame.locator(".m3l .row.sel").count() == 4
        menu(frame, obj("Part 3") + " .nm"); pick(frame, "green")
        d = wait_file(path, lambda d: len(colors(d)) == 5)
        assert colors(d) == {"o000": "blue", "o001": "green", "o002": "green", "l0": "green", "c01": "green"}, colors(d)
        for sel in (obj("Part 2"), obj("Part 3"), light("Key"), cam("c01")): assert tint(sel) == HEX["green"], sel
        assert tint(obj("Part 1")) == HEX["blue"], "a row outside the choice keeps its colour"
        assert frame.locator(".m3l .row.sel").count() == 4, "the right click leaves the choice as it was"
        shot(page, f"colors-3d-chosen-{engine}")

        # 3. a right click on a row outside the choice: that row alone («no colour» clears it)
        menu(frame, obj("Part 1") + " .nm"); pick(frame, "")
        d = wait_file(path, lambda d: "o000" not in colors(d))
        assert len(colors(d)) == 4 and tint(obj("Part 1")) == ""

        # 4. a part of a model: its key is «<object id>/<layer path>»
        frame.click(obj("Vase") + " [data-open]"); frame.wait_for_timeout(500)
        part = frame.evaluate("""() => { const rows = [...document.querySelectorAll('.m3l .ms[data-s=objects] .row[data-u]')];
          const i = rows.findIndex(r => r.querySelector('.nm').textContent.startsWith('Vase')), r = rows.slice(i + 1).find(r => r.querySelector('.g')); return r && r.dataset.k; }""")
        assert part and part.startswith("shell/"), part
        menu(frame, f".m3l .row[data-k='{part}'] .nm"); pick(frame, "red")
        d = wait_file(path, lambda d: colors(d).get(part) == "red")
        assert tint(f".m3l .row[data-k='{part}']") == HEX["red"]
        assert not any("color" in o for o in d["objects"] if o["id"] in ("o001", "o002")), "the material is not touched"

        for th in ("dark", "light"):
            for doc in (page, frame): doc.evaluate(f"() => document.documentElement.dataset.theme = '{th}'")
            frame.wait_for_timeout(300)
            shot(page, f"colors-3d-{th}-{engine}")
        assert not errors, errors
        browser.close()
