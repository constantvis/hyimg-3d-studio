"""Blender's bar over a 3D card in its editor (owner 2026-10-06: «it must be in the centre, as the standard menu over a picture»; 2026-10-07:
«не внизу, а вверху», and «Render» was under the Scene panel and the axes): the board's own selection bar (canvas.html renderHandles,
def.editBar) stands always above the card (on the frame bar, when the card has one), centred on the card and pushed only as far as
it must to stay in the board's free part (the board minus the side panels, the top row and the dock with the axes: ui/bars.js), pinned to that part's top when there is no
room above, and inside it at any zoom, with the card larger than the free part or half off it; «Render» can be clicked. The dock keeps
the tools and a neutral reset.
Chromium and WebKit; no Blender is needed (the scene names a studio that is not there, the bar shows all the same).

  HYIMG_REPO=<Hyimg checkout> python3 -m pytest tests/test_blender_bar.py
"""
import json, os

import pytest
from playwright.sync_api import sync_playwright

from test_canvas_3d import hy as _hy, wait_file   # noqa: F401
from test_3d_files import ENGINES, new_card, open_board, scene_of
from test_editor_ui import open_editor

hy = _hy
SHOTS = os.environ.get("HYIMG_SHOTS")
BOXES = """(cid) => { const r = e => { if (!e) return null; const b = e.getBoundingClientRect(); return { l: b.left, r: b.right, t: b.top, b: b.bottom, cx: (b.left + b.right) / 2 }; };
  const card = r(document.querySelector(`.plg[data-id="${cid}"]`)), f = freeArea(), ok = document.querySelector('#handles .tidy.plgedit .m3rend');
  const o = ok && ok.getBoundingClientRect(), hit = o && document.elementFromPoint((o.left + o.right) / 2, (o.top + o.bottom) / 2);
  return { bar: r(document.querySelector('#handles .tidy.plgedit')), frame: r(document.querySelector('#handles .tidy.cratio')), card, free: f,
    axes: r(document.querySelector('.m3ui .m3x')), seen: { l: Math.max(card.l, f.l), r: Math.min(card.r, f.r) }, okClickable: !!(hit && ok.contains(hit)) }; }"""


def studio_scene(path):
    """the card's scene as tools/studio_angles.py makes it: a studio block naming the picture of its camera"""
    doc = json.loads(path.read_text())
    cam = doc["active_camera"]
    doc["studio"] = {"folder": str(path.parent / "no-studio"), "colour": "burgundy", "look": "current", "out": "renderings",
                     "angles": {cam: {"source": "renderings/none.json", "view": "v01", "ordinal": 1, "look": "M07", "resolution": [480, 480], "samples": 4, "exposure": 0}}}
    doc["rev"] = doc.get("rev", 0) + 1; doc["by"] = "blender"
    path.write_text(json.dumps(doc))


@pytest.mark.parametrize("hy", ["en"], indirect=True)
@pytest.mark.parametrize("engine", ENGINES)
def test_the_blender_bar_is_centred_over_the_card_and_clamped_like_the_selection_bar(hy, engine):
    port, lib = hy
    with sync_playwright() as p:
        browser, page, frame, errors = open_board(p, engine, port)
        cid = new_card(frame); scene = scene_of(lib, frame, cid)
        wait_file(scene, lambda d: len(d["objects"]) == 2)
        studio_scene(scene); frame.wait_for_timeout(4000)   # the canvas reads the changed file on its next look (3 s)
        open_editor(frame, cid)
        frame.wait_for_selector("#handles .tidy.plgedit .m3eng", timeout=15000)
        assert [s.strip() for s in frame.locator(".m3bplate [data-eng]").all_inner_texts()] == ["three.js", "EEVEE", "Cycles"]
        # the dock keeps the tools: no engine, no render, the reset a plain icon among them
        assert frame.locator("#dock .m3eng, #dock [data-ok]").count() == 0
        assert frame.locator("#dock .hy-reset").count() == 0 and frame.locator("#dock .m3reset").count() == 1
        for b in frame.locator(".m3bplate .seg > button").all():   # every label fits its button
            assert frame.evaluate("e => e.scrollWidth <= e.clientWidth + 1", b.element_handle())
        def check(what):
            frame.wait_for_timeout(600)
            m = frame.evaluate(BOXES, cid); f = m["free"]
            if SHOTS: page.screenshot(path=os.path.join(SHOTS, f"blender-bar-{engine}-{what}.png"))
            bars = [k for k in ("bar", "frame") if m[k]]   # the frame bar may be off (def.frameBar: false, the frame in the Scene panel)
            for k in bars:   # inside the free part of the board
                assert m[k]["l"] >= f["l"] - 0.5 and m[k]["r"] <= f["r"] + 0.5 and m[k]["t"] >= f["t"] - 0.5 and m[k]["b"] <= f["b"] + 0.5, (what, k, m)
            # above the card, or pinned to the free part's top over it; with a frame bar the render bar is 8 px above it
            near = m["frame"] or m["bar"]
            assert near["b"] <= m["card"]["t"] + 1 or abs(m["bar"]["t"] - f["t"]) <= 1, ("above the card", what, m)
            if m["frame"]: assert 6 <= m["frame"]["t"] - m["bar"]["b"] <= 10, ("the render bar on the frame bar", what, m)
            # centred on the card, moved only as far as the wider bar needs to stay in the free part
            wide = max(m[k]["r"] - m[k]["l"] for k in bars)
            want = min(max(m["card"]["cx"], f["l"] + wide / 2), f["r"] - wide / 2)
            assert all(abs(m[k]["cx"] - want) <= 1 for k in bars), ("centred on the card, on one axis", what, m)
            a = m["axes"]
            if a: assert m["bar"]["b"] <= a["t"] or m["bar"]["t"] >= a["b"] or m["bar"]["r"] <= a["l"] or m["bar"]["l"] >= a["r"], ("clear of the axes", what, m)
            assert m["okClickable"], ("«Render» can be clicked", what, m)
            return m
        stage = frame.locator("#stage").bounding_box()
        aside = (stage["x"] + 30, stage["y"] + stage["height"] - 140)   # a point of the board away from the card: the wheel zooms the board there
        for zoom in (0, 2):
            for _ in range(zoom):
                page.mouse.move(*aside); page.keyboard.down("Control"); page.mouse.wheel(0, -100); page.keyboard.up("Control"); frame.wait_for_timeout(150)
            check(f"zoom{zoom}")
        # the camera moved as a pan or a zoom does (renderCam): the card wider than the board and under both side panels, then its top
        # above the free part (no room above: the bars pinned to the top, over the card), then half off the free part's left edge
        put = "([cid, k, dy]) => { const c = rectOf(cid), st = stage.getBoundingClientRect(); cam.z = st.width * k / c.w; cam.x = c.x + c.w / 2 - st.width / 2 / cam.z; cam.y = c.y - dy / cam.z; renderCam(); }"
        frame.evaluate(put, [cid, 1.3, 200]); m = check("wide")
        assert m["card"]["l"] < m["free"]["l"] and m["card"]["r"] > m["free"]["r"], ("the card is under both side panels", m)
        frame.evaluate(put, [cid, 1.3, -40]); m = check("pinned")
        assert abs(m["bar"]["t"] - m["free"]["t"]) <= 1 and m["card"]["t"] < m["free"]["t"], ("pinned to the top over the card", m)
        frame.evaluate("(cid) => { const st = stage.getBoundingClientRect(), f = freeArea(), c = document.querySelector(`.plg[data-id=\"${cid}\"]`).getBoundingClientRect(); cam.z = 0.6 * st.width / (c.width / cam.z) * 0.5; renderCam();"
                       " const d = document.querySelector(`.plg[data-id=\"${cid}\"]`).getBoundingClientRect(); cam.x += ((d.left + d.right) / 2 - (f.l + 20)) / cam.z; cam.y += (d.top - (f.t + 160)) / cam.z; renderCam(); }", cid)
        m = check("edge")
        assert m["card"]["l"] < m["free"]["l"], ("the card is partly off the free part", m)
        assert not errors, errors
        browser.close()
