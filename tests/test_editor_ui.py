"""The 3D editor's interface as the owner found it in the app (2026-10-06, screenshots): sliders drawn from two geometries, the key letters
always on the tool buttons, the panels climbing onto the app's top band, the panels jumping when the media library opens, and a new card that
is a dark nothing on a dark board. Chromium and WebKit, the app's page with the canvas in its frame (the way the app shows them).

  HYIMG_REPO=<Hyimg checkout> python3 -m pytest tests/test_editor_ui.py
"""
import json, re, time

import pytest
from playwright.sync_api import sync_playwright

from test_canvas_3d import CORNER, hy as _hy, wait_file   # noqa: F401
from test_3d_files import ENGINES, new_card, open_board, scene_of

hy = _hy


def go_on(frame):
    if frame.locator(".m3pause [data-go]").count(): frame.click(".m3pause [data-go]")


def library_away(page):
    """an empty board opens its library by itself a moment after load (the app, 2026-10-06): wait for that, then close it, so the card is under the pointer"""
    page.wait_for_timeout(1800)
    if page.evaluate("() => !document.body.classList.contains('cv-only')"):
        page.keyboard.press("Control+m"); page.wait_for_function("() => document.body.classList.contains('cv-only')", timeout=5000); page.wait_for_timeout(900)


def open_editor(frame, cid):
    library_away(frame.page)
    frame.dblclick(f".plg[data-id={cid}]", position=CORNER)
    frame.wait_for_selector(".m3ui .m3l .row", timeout=30000)
    go_on(frame)


SLIDER = """(label) => { const root = [...document.querySelectorAll('.m3r .hy-slider')].find(r => ((r.querySelector('.hy-slider-l') || {}).textContent || '').startsWith(label));
  if (!root) return null; const f = root.querySelector('.hy-slider-f').getBoundingClientRect(), t = root.querySelector('.hy-slider-t').getBoundingClientRect(), r = root.getBoundingClientRect(), i = root.querySelector('input');
  return { fill: f.right, thumb: t.left + t.width / 2, left: r.left, right: r.right, w: r.width, v: +i.value, min: +i.min, max: +i.max, shown: root.querySelector('.hy-slider-v').textContent,
    end: root.classList.contains('sm') ? 1 : r.height * .1 + 1 }; }"""   # end: the line's clamp inside the round ends, Hyimg's ui/slider.css --hy-sl-end (de77962)
# the slider at rest: a click glides its fill and its line (.jump, 0.22 s, Hyimg ui/slider.css); a busy machine can still be mid-glide after a fixed wait
RESTS = """(label) => { const root = [...document.querySelectorAll('.m3r .hy-slider')].find(r => ((r.querySelector('.hy-slider-l') || {}).textContent || '').startsWith(label));
  return !!root && !root.classList.contains('jump') && root.getAnimations({ subtree: true }).every(a => a.playState !== 'running'); }"""
LABELS = ["Lens", "Wide", "Distance", "Azimuth", "Inclination", "Twist", "Transparency"]


@pytest.mark.parametrize("hy", ["en"], indirect=True)
@pytest.mark.parametrize("engine", ENGINES)
def test_every_slider_draws_its_fill_and_its_line_from_one_geometry_and_drags_smoothly(hy, engine):
    port, lib = hy
    with sync_playwright() as p:
        browser, page, frame, errors = open_board(p, engine, port)
        cid = new_card(frame); wait_file(scene_of(lib, frame, cid), lambda d: len(d["objects"]) == 2)
        open_editor(frame, cid)
        frame.wait_for_selector(".m3r .hy-slider", timeout=15000)
        assert frame.locator(".m3r .dialkit-slider").count() == 0, "DialKit's own sliders are gone: the app's one slider draws them"
        shown = frame.evaluate("() => [...document.querySelectorAll('.m3r .hy-slider-l')].map(e => e.textContent)")
        for w in LABELS: assert any(s.startswith(w) for s in shown), (w, shown)
        # the line is centred on the fill's end, clamped inside the track's round ends (--hy-sl-end, the app's one rule since Hyimg de77962:
        # at 0 the line stood in the curve, a crescent «(»): within 1 px, at the ends and between, for every slider
        worst = 0
        for w in LABELS:
            for frac in (0.0, 0.1, 0.5, 0.9, 1.0):
                idx = next(i for i, s in enumerate(frame.evaluate("() => [...document.querySelectorAll('.m3r .hy-slider-l')].map(e => e.textContent)")) if s.startswith(w))
                box = frame.locator(".m3r .hy-slider").nth(idx).bounding_box()
                frame.locator(".m3r .hy-slider").nth(idx).click(position={"x": max(2, min(box["width"] - 2, box["width"] * frac)), "y": box["height"] / 2})
                frame.wait_for_timeout(420); go_on(frame); frame.wait_for_function(RESTS, arg=w, timeout=5000)
                m = frame.evaluate(SLIDER, w)
                gap = abs(m["thumb"] - min(max(m["fill"], m["left"] + m["end"]), m["right"] - m["end"])); worst = max(worst, gap)
                assert gap <= 1.01, (w, frac, m)
                assert m["left"] + m["end"] - 0.5 <= m["thumb"] <= m["right"] - m["end"] + 0.5, ("the line stays inside the round ends", w, frac, m)
                assert abs((m["fill"] - m["left"]) / m["w"] - (m["v"] - m["min"]) / (m["max"] - m["min"])) < 0.01 or (m["fill"] - m["left"]) < 1.01, ("the fill is the value's share", w, frac, m)
        # a drag moves the value from where it was grabbed: no jump at the press, the value follows the pointer, it goes on outside the control (pointer capture)
        lens = frame.locator(".m3r .hy-slider").filter(has_text="Lens").first
        lens.click(position={"x": lens.bounding_box()["width"] * 0.5, "y": 10}); frame.wait_for_timeout(420); go_on(frame)   # the loop above left it at its end
        frame.evaluate("() => document.activeElement && document.activeElement.blur()")
        b = lens.bounding_box(); m0 = frame.evaluate(SLIDER, "Lens"); y = b["y"] + b["height"] / 2; x0 = b["x"] + b["width"] * 0.3
        page.mouse.move(x0, y); page.mouse.down(); frame.wait_for_timeout(120)
        assert frame.evaluate(SLIDER, "Lens")["v"] == m0["v"], "no jump when the pointer goes down"
        seen = []
        for i in range(1, 9):
            page.mouse.move(x0 + b["width"] * 0.04 * i, y); frame.wait_for_timeout(60); seen.append(frame.evaluate(SLIDER, "Lens")["v"])
        span = m0["max"] - m0["min"]
        assert seen == sorted(seen) and len(set(seen)) >= 5, ("the value follows the pointer smoothly", seen)
        assert abs((seen[-1] - m0["v"]) - span * 0.32) <= span * 0.02 + 1, (m0, seen)
        page.mouse.move(b["x"] + b["width"] + 300, y); frame.wait_for_timeout(100)
        assert frame.evaluate(SLIDER, "Lens")["v"] == m0["max"], "the drag goes on outside the control"
        page.mouse.up(); go_on(frame)
        # the keyboard still works (a native range input is inside) and the number is a field
        lens.locator("input[type=range]").focus(); before = frame.evaluate(SLIDER, "Lens")["v"]
        page.keyboard.press("ArrowLeft"); frame.wait_for_timeout(200)
        assert frame.evaluate(SLIDER, "Lens")["v"] < before
        lens.locator(".hy-slider-v").click(); lens.locator("input.hy-slider-ed").fill("50"); page.keyboard.press("Enter"); frame.wait_for_timeout(300)
        assert frame.evaluate(SLIDER, "Lens")["v"] == 50
        print(f"\n{engine}: the line is within {worst:.2f} px of the fill's end at every tried value of {len(LABELS)} sliders")
        assert not errors, errors
        browser.close()


@pytest.mark.parametrize("hy", ["en"], indirect=True)
@pytest.mark.parametrize("engine", ENGINES)
def test_the_tool_buttons_work_and_their_letters_show_only_under_command(hy, engine):
    port, lib = hy
    info = "() => import('/plugins/3d/engine.js').then(m => m.liveInfo())"
    with sync_playwright() as p:
        browser, page, frame, errors = open_board(p, engine, port)
        cid = new_card(frame); wait_file(scene_of(lib, frame, cid), lambda d: len(d["objects"]) == 2)
        open_editor(frame, cid)
        frame.wait_for_selector("#dock .plgdock [data-tool]", timeout=15000)
        btn = lambda k: frame.locator(f"#dock .plgdock [data-tool={k}]")
        # the letters are the button's own <kbd>, hidden at rest, the app's rule (ui/keyhints.js): shown over the button's right end under ⌘, no wider
        for k, key in (("select", "V"), ("translate", "G"), ("rotate", "R"), ("scale", "S"), ("smart", "T")):
            assert frame.evaluate(f"() => {{ const b = document.querySelector('#dock .plgdock [data-tool={k}]'); const c = b.querySelector(':scope > kbd'); return c && c.textContent; }}") == key, k
        w0 = btn("translate").bounding_box()["width"]
        assert frame.evaluate("() => getComputedStyle(document.querySelector('#dock .plgdock [data-tool=translate] > kbd')).opacity") == "0", "no letters at rest"
        assert frame.evaluate("() => getComputedStyle(document.querySelector('#dock .plgdock [data-tool=translate]'), '::after').content") in ("none", "normal", '""'), "no letter drawn by CSS content"
        page.keyboard.down("Meta"); page.wait_for_timeout(500)
        frame.wait_for_function("() => getComputedStyle(document.querySelector('#dock .plgdock [data-tool=translate] > kbd')).opacity === '1'", timeout=8000)   # under ⌘ the letters show (a software-GL frame can be slow to come)
        assert abs(btn("translate").bounding_box()["width"] - w0) < 0.5, "and the button does not widen"
        page.keyboard.up("Meta")
        frame.wait_for_function("() => getComputedStyle(document.querySelector('#dock .plgdock [data-tool=translate] > kbd')).opacity === '0'", timeout=8000)
        # a thing is picked (the stand-in shape): then each tool is the button's, the key's, and the gizmo follows
        frame.click(".m3l .row[data-u]:has-text('Object')"); frame.wait_for_timeout(300)
        assert (frame.evaluate(info))["selected"], "the shape is picked"
        modes = {"select": (False, "translate"), "translate": (True, "translate"), "rotate": (True, "rotate"), "scale": (True, "scale"), "smart": (False, "translate")}
        for k, (attached, mode) in modes.items():
            btn(k).click(); frame.wait_for_timeout(250); go_on(frame)
            st = frame.evaluate(info)
            assert st["tool"] == k and st["attached"] is attached and (not attached or st["mode"] == mode), (k, st)
            on = frame.evaluate("() => [...document.querySelectorAll('#dock .plgdock [data-tool]')].filter(b => b.classList.contains('on')).map(b => b.dataset.tool)")
            assert on == [k], (k, on)
        for key, k, attached in (("g", "translate", True), ("r", "rotate", True), ("s", "scale", True), ("t", "smart", False), ("v", "select", False)):
            frame.evaluate("() => document.activeElement && document.activeElement.blur()"); page.keyboard.press(key); frame.wait_for_timeout(250); go_on(frame)
            st = frame.evaluate(info)
            assert st["tool"] == k and st["attached"] is attached, (key, st)
            assert frame.evaluate("() => [...document.querySelectorAll('#dock .plgdock [data-tool].on')].map(b => b.dataset.tool)") == [k], key
        assert not errors, errors
        browser.close()


@pytest.mark.parametrize("hy", ["en"], indirect=True)
@pytest.mark.parametrize("engine", ENGINES)
def test_the_panels_start_below_the_apps_top_band_and_the_crumb_stays_clickable(hy, engine):
    port, lib = hy
    with sync_playwright() as p:
        browser, page, frame, errors = open_board(p, engine, port)
        cid = new_card(frame); wait_file(scene_of(lib, frame, cid), lambda d: len(d["objects"]) == 2)
        open_editor(frame, cid)
        crumb = frame.locator("#crumb").bounding_box(); left = frame.locator(".m3ui .m3l").bounding_box(); right = frame.locator(".m3ui .m3r").bounding_box()
        assert crumb and left and right
        assert left["y"] >= crumb["y"] + crumb["height"] + 4 and right["y"] >= crumb["y"] + crumb["height"] + 4, (crumb, left, right)
        assert left["y"] >= 56, "as far down as the library (--lt: 58px) and the frame editor's panels"
        # the crumb is on top where the panel was going to be: a click on it lands on it
        hit = frame.evaluate("""() => { const r = document.getElementById('crumb').getBoundingClientRect(); const e = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2); return !!e && !!e.closest('#crumb'); }""")
        assert hit, "the crumb plate is not covered"
        assert not errors, errors
        browser.close()


@pytest.mark.parametrize("hy", ["en"], indirect=True)
@pytest.mark.parametrize("engine", ENGINES)
def test_the_panel_glides_with_the_library_and_the_library_opens_half_while_the_editor_is_open(hy, engine):
    port, lib = hy
    # the transition is recorded by its own event (a software-GL editor frame can take longer than the move, so sampling frames would show nothing)
    watch = """() => { const el = document.querySelector('.m3ui .m3l'); window.__tr = []; el.addEventListener('transitionrun', e => { if (e.propertyName === 'left') { const cs = getComputedStyle(el); window.__tr.push({ dur: cs.transitionDuration.split(',')[0], ease: cs.transitionTimingFunction.split('), ')[0] + ')', from: el.getBoundingClientRect().left }); } }); }"""
    with sync_playwright() as p:
        browser, page, frame, errors = open_board(p, engine, port)
        cid = new_card(frame); wait_file(scene_of(lib, frame, cid), lambda d: len(d["objects"]) == 2)
        # a remembered full-width library
        library_away(page)
        page.keyboard.press("Control+m"); page.wait_for_function("() => !document.body.classList.contains('cv-only')")
        page.wait_for_timeout(900); page.click("#lwide"); page.wait_for_timeout(900)
        assert page.evaluate("() => document.body.classList.contains('lwide')")
        page.keyboard.press("Control+m"); page.wait_for_function("() => document.body.classList.contains('cv-only')", timeout=5000); page.wait_for_timeout(900)
        open_editor(frame, cid)
        x_closed = frame.evaluate("() => document.querySelector('.m3ui .m3l').getBoundingClientRect().left")
        assert page.evaluate("() => document.body.classList.contains('ed-open')")
        # the library opens: the panel's left edge glides over the library's own 0.72 s on the app's curve, to where the library ends, instead of jumping
        frame.evaluate(watch); page.keyboard.press("Control+m")
        frame.wait_for_function("() => window.__tr.length > 0", timeout=8000)
        tr = frame.evaluate("() => window.__tr[0]")
        assert tr["dur"] == "0.72s" and tr["ease"] == "cubic-bezier(0.32, 0.72, 0, 1)", tr
        page.wait_for_timeout(1500)
        opened = frame.evaluate("() => document.querySelector('.m3ui .m3l').getBoundingClientRect().left")
        main_right = page.evaluate("() => document.querySelector('main').getBoundingClientRect().right")
        assert opened > x_closed + 200 and abs(opened - (main_right + 12 + 12)) < 30, ("the panel ends clear of the library", x_closed, opened, main_right)
        # the library is at its normal width, never full, while the editor is open
        assert not page.evaluate("() => document.body.classList.contains('lwide')"), "no full width"
        assert page.evaluate("() => document.querySelector('main').getBoundingClientRect().width") < page.evaluate("() => innerWidth") * 0.7
        assert page.locator("#lwide").is_hidden(), "the full-width button is away while the editor is open"
        # and closing it glides back, over the closing move's 0.56 s
        frame.evaluate(watch); page.keyboard.press("Control+m")
        frame.wait_for_function("() => window.__tr.length > 0", timeout=8000)
        assert frame.evaluate("() => window.__tr[0].dur") == "0.56s"
        page.wait_for_timeout(1500)
        assert abs(frame.evaluate("() => document.querySelector('.m3ui .m3l').getBoundingClientRect().left") - x_closed) < 2
        # after «Done» the remembered full width is back
        frame.click("#dock [data-a=save]"); page.wait_for_timeout(1200)
        assert page.evaluate("() => document.body.classList.contains('lwide')"), "the full width comes back with the library"
        assert not errors, errors
        browser.close()


@pytest.mark.parametrize("hy", ["en"], indirect=True)
@pytest.mark.parametrize("engine", ENGINES)
def test_an_empty_card_shows_the_base_scene_under_a_plate_of_constant_size(hy, engine):
    port, lib = hy
    sample = """() => { const img = document.querySelector('.plg[data-type=model3d] img.m3'); const c = document.createElement('canvas'); c.width = 40; c.height = 50; const g = c.getContext('2d');
      g.drawImage(img, 0, 0, 40, 50); const d = g.getImageData(0, 0, 40, 50).data; let n = 0, s = 0, s2 = 0; const dist = new Set();
      for (let i = 0; i < d.length; i += 4) { const l = 0.2126 * d[i] + 0.7152 * d[i + 1] + 0.0722 * d[i + 2]; s += l; s2 += l * l; n++; dist.add((d[i] >> 4) + ',' + (d[i + 1] >> 4) + ',' + (d[i + 2] >> 4)); }
      const m = s / n; return { mean: m, sd: Math.sqrt(Math.max(0, s2 / n - m * m)), colours: dist.size, w: img.naturalWidth }; }"""
    plate = """() => { const b = document.querySelector('.plg[data-type=model3d] .e3-bx').getBoundingClientRect(), c = document.querySelector('.plg[data-type=model3d]').getBoundingClientRect();
      return { w: b.width, h: b.height, cx: b.left + b.width / 2 - (c.left + c.width / 2), cy: b.top + b.height / 2 - (c.top + c.height / 2), inside: b.left >= c.left - 0.5 && b.right <= c.right + 0.5 && b.top >= c.top - 0.5 && b.bottom <= c.bottom + 0.5,
        cw: c.width, ch: c.height, op: +getComputedStyle(document.querySelector('.plg[data-type=model3d] .e3-bx')).opacity, cube: +getComputedStyle(document.querySelector('.plg[data-type=model3d] .e3-cube')).opacity }; }"""
    with sync_playwright() as p:
        browser, page, frame, errors = open_board(p, engine, port)
        frame.evaluate("() => { setPref('theme', 'dark'); renderBg(); }")   # the owner's board: dark
        assert frame.evaluate("() => document.documentElement.dataset.theme") == "dark"
        cid = new_card(frame)
        frame.wait_for_function("() => { const i = document.querySelector('.plg[data-type=model3d] img.m3'); return i && i.complete && i.naturalWidth > 0; }", timeout=90000)
        px = frame.evaluate(sample)
        assert px["mean"] > 45 and px["sd"] > 12 and px["colours"] > 12, f"the card's picture is the base scene, not a dark nothing: {px}"
        # the plate has the card's picture behind it (it is see-through) and sits in the middle
        assert frame.evaluate("() => getComputedStyle(document.querySelector('.plg[data-type=model3d] .e3')).backgroundColor") in ("rgba(0, 0, 0, 0)", "transparent")
        sizes = {}
        for z in (1, 4):
            frame.evaluate(f"() => {{ const r = stage.getBoundingClientRect(); const c = document.querySelector('.plg[data-type=model3d]').getBoundingClientRect(); cam.z = {z}; renderCam(); }}")
            frame.evaluate("() => { const it = Object.values(board.items).find(i => i.type === 'model3d'); const r = stage.getBoundingClientRect(); cam.x = it.x + it.w / 2 - r.width / 2 / cam.z; cam.y = it.y + it.h / 2 - r.height / 2 / cam.z; renderCam(); }")
            frame.wait_for_timeout(500)
            sizes[z] = frame.evaluate(plate)
        assert abs(sizes[1]["w"] - sizes[4]["w"]) <= 1 and abs(sizes[1]["h"] - sizes[4]["h"]) <= 1, ("one size on the screen at any zoom", sizes)
        assert sizes[4]["inside"] and sizes[1]["inside"] and abs(sizes[4]["cx"]) < 2 and abs(sizes[4]["cy"]) < 2, sizes
        # a small card: the plate shrinks to fit inside it, and below the minimum only the cube is left
        frame.evaluate("() => { const it = Object.values(board.items).find(i => i.type === 'model3d'); it.w = 200; it.h = 250; render(); }"); frame.wait_for_timeout(300)
        frame.evaluate("() => { cam.z = 1; renderCam(); const it = Object.values(board.items).find(i => i.type === 'model3d'); const r = stage.getBoundingClientRect(); cam.x = it.x + it.w / 2 - r.width / 2; cam.y = it.y + it.h / 2 - r.height / 2; renderCam(); }")
        frame.wait_for_timeout(500); small = frame.evaluate(plate)
        assert small["inside"] and small["w"] < sizes[1]["w"] and small["op"] > 0.9, small
        frame.evaluate("() => { const it = Object.values(board.items).find(i => i.type === 'model3d'); it.w = 80; it.h = 100; render(); cam.z = 1; renderCam(); }"); frame.wait_for_timeout(500)
        tiny = frame.evaluate(plate); assert tiny["op"] < 0.05 and tiny["cube"] > 0.9, ("only the cube is left on a tiny card", tiny)
        print(f"\n{engine}: base scene mean {px['mean']:.0f} sd {px['sd']:.0f}; plate {sizes[1]['w']:.1f} x {sizes[1]['h']:.1f} at zoom 1, {sizes[4]['w']:.1f} x {sizes[4]['h']:.1f} at 4; small card {small['w']:.0f} px")
        assert not errors, errors
        browser.close()
