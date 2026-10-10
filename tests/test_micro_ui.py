"""Round 15's micro UI in 3D Studio (owner 2026-10-09 on r15-micro.html: «Все топ, все делай, кроме номера пять»; r15-3d.html): «All nodes»
is a mini toggle beside the search and the search's count «part / all» is the same switch; the current camera wears a 6 px LED in 3D
Studio's pink instead of the «card» pill; the rows' eye and lock show on hover and a set one stays (.hy-ri); an inspector's on or off is a
mini toggle (Visible), its 2 to 4 short choices micro segments (Selection highlight); a material changed in the card's variant wears the
change dot; the Blender line's state is an LED. Chromium, dark.
"""
import os

from playwright.sync_api import sync_playwright

from test_canvas_3d import SITE2, board_server, go_on

CARD = {"type": "model3d", "scene": "3d/scenes/a/scene.json", "camera": "jo1wd256", "x": 0, "y": 0, "w": 500, "h": 500}
PROBE = """([v, prop]) => { const p = document.createElement('i'); p.style.setProperty(prop, v); document.body.append(p);
  const c = getComputedStyle(p).getPropertyValue(prop); p.remove(); return c; }"""
BOX = "(e) => { const r = e.getBoundingClientRect(); return [Math.round(r.width), Math.round(r.height)]; }"


def test_3d_studio_wears_the_micro_ui(tmp_path):
    port, lib, stop = board_server(tmp_path, {"c": dict(CARD)}, {"a": SITE2}, lang="en")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            errors = []; page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(f"http://127.0.0.1:{port}/canvas.html")
            page.wait_for_function("() => typeof PLGST !== 'undefined' && PLGST.some(p => p.name === '3d' && p.ok)", timeout=20000)
            page.evaluate("() => { setPref('theme', 'dark'); renderBg(); }")
            pink = page.evaluate(PROBE, ["#ff4fa3", "background-color"])
            page.dblclick(".plg[data-id=c]", position={"x": 30, "y": 30}); page.wait_for_selector(".m3r .hy-slider", timeout=60000)
            page.wait_for_timeout(1200); go_on(page)

            # 3 · nothing picked yet, the scene's settings: Selection highlight's two choices are micro segments, a radiogroup the arrows move
            seg = page.locator(".m3r .dk .dialkit-microseg-row hy-segmented[variant=micro]")
            assert seg.count() >= 1, page.locator(".m3r .dk").inner_text()
            assert seg.count() == 3   # Sensor fit (in «Camera: more»), Selection highlight, the pull's Pivot (folded)
            s0 = page.locator(".m3r .dk .dialkit-microseg-row", has_text="Selection highlight").locator("hy-segmented")
            assert s0.evaluate("s => [s.getAttribute('role'), [...s.querySelectorAll('button')].every(b => b.getAttribute('role') === 'radio')]") == ["radiogroup", True]
            assert s0.evaluate(BOX)[1] == 22 and s0.locator("button").first.evaluate(BOX)[1] == 18
            was = s0.evaluate("s => s.value")
            s0.locator("button.on").focus(); page.keyboard.press("ArrowRight"); page.wait_for_timeout(300)
            assert s0.evaluate("s => s.value") != was
            s0.locator("button.on").focus(); page.keyboard.press("ArrowLeft"); page.wait_for_timeout(300)
            assert s0.evaluate("s => s.value") == was
            # 1 · «All nodes»: the mini toggle in the search's row, no checkbox of its own; a switch for VoiceOver, 22 px tall
            assert page.locator(".m3l .opts, .m3l input[type=checkbox][data-raw]").count() == 0
            mt = page.locator(".m3l .lhd > hy-minitoggle[data-raw]")
            assert mt.count() == 1 and mt.inner_text().strip() == "All nodes"
            assert mt.evaluate(BOX)[1] == 22 and mt.evaluate("m => m.input.getAttribute('role')") == "switch"
            # 2 · the search's count is the same switch: part / all, a click shows every node and turns the toggle on
            sc = page.locator(".m3l .lhd .hy-search > hy-scope[data-scope]")
            assert sc.count() == 1
            part, total = sc.evaluate("s => [+s.getAttribute('shown'), +s.getAttribute('total')]")
            assert 0 < part <= total, (part, total)
            print("scope", part, total)
            if os.environ.get("HYIMG_TEST_SHOTS"):
                page.screenshot(path=os.path.join(os.environ["HYIMG_TEST_SHOTS"], "micro-3d.png"))
            if total > part:
                assert sc.is_visible() and sc.evaluate(BOX)[1] == 18
                sc.locator("button").click(); page.wait_for_timeout(200)
                assert sc.evaluate("s => [s.hasAttribute('all'), s.button.getAttribute('aria-pressed')]") == [True, "true"]
                assert mt.evaluate("m => [m.hasAttribute('checked'), m.input.checked]") == [True, True]
                rows_all = page.locator(".m3l .ms[data-s=objects] .row").count()
                mt.click(); page.wait_for_timeout(200)
                assert not sc.evaluate("s => s.hasAttribute('all')") and page.locator(".m3l .ms[data-s=objects] .row").count() <= rows_all
            else:
                assert not sc.is_visible()
            mt.locator("input").focus(); page.keyboard.press("Space"); page.wait_for_timeout(200)
            assert mt.evaluate("m => m.hasAttribute('checked')") and sc.evaluate("s => s.hasAttribute('all')")
            page.keyboard.press("Space"); page.wait_for_timeout(200)

            # 4 · the current camera: a 6 px LED in the pink, flat, where the «card» pill stood
            cam = page.locator(".m3l .row[data-cam=jo1wd256]")
            assert cam.locator(".tag").count() == 0 and cam.locator(".chev").evaluate("c => getComputedStyle(c, '::after').content") in ("none", "normal")
            led = cam.locator("hy-led")
            assert led.count() == 1 and led.evaluate(BOX) == [6, 6]
            assert led.evaluate("l => [getComputedStyle(l).backgroundColor, getComputedStyle(l).boxShadow, l.getAttribute('role'), l.getAttribute('aria-label')]") \
                == [pink, "none", "img", "The current camera"]

            # 8 · the rows' eye and lock: .hy-ri in a .hy-hovrow, hidden until the row is hovered, a locked one stays
            row = page.locator(".m3l .ms[data-s=objects] .row[data-u]").first
            assert row.evaluate("r => r.classList.contains('hy-hovrow')")
            eye = row.locator("button[data-eye]")
            assert eye.evaluate("b => b.classList.contains('hy-ri')") and eye.evaluate(BOX) == [20, 20]
            op = lambda want: eye.evaluate("(b, w) => new Promise(ok => { const t0 = performance.now(), f = () => +getComputedStyle(b).opacity === w || "
                                           "performance.now() - t0 > 3000 ? ok(+getComputedStyle(b).opacity) : requestAnimationFrame(f); f(); })", want)   # once it has eased
            page.mouse.move(5, 500)
            assert op(0) == 0
            row.hover()
            assert op(1) == 1
            row.locator("button[data-lock]").click(); page.wait_for_timeout(300); page.mouse.move(5, 500); page.wait_for_timeout(300)
            lock = page.locator(".m3l .ms[data-s=objects] .row[data-u]").first.locator("button[data-lock]")
            assert lock.evaluate("b => [b.classList.contains('keep'), getComputedStyle(b).opacity]") == [True, "1"]
            lock.click(force=True); page.wait_for_timeout(300)

            # an inspector's on or off is the mini toggle (Visible of a layer), its short choices micro segments (Selection highlight)
            page.locator(".m3l .ms[data-s=objects] .row[data-u] .nm").first.click(); page.wait_for_timeout(600)
            tog = page.locator(".m3r .dk .dialkit-minitoggle-row hy-minitoggle")
            assert tog.count() >= 1 and page.locator(".m3r .dk .dialkit-labeled-control .dialkit-segmented-button").filter(has_text="On").count() == 0
            assert tog.first.evaluate("m => m.input.getAttribute('role')") == "switch" and tog.first.evaluate(BOX)[1] == 22
            assert not errors, errors
            browser.close()
    finally:
        stop()


def test_the_change_dot_and_the_blender_led_are_the_primitives():
    """a material changed in the variant and the Blender line, read from the code that draws them (no Blender on a test machine)"""
    from pathlib import Path
    here = Path(__file__).resolve().parents[1]
    mats, blender = (here / "materials.js").read_text(), (here / "blender.js").read_text()
    assert '<i class="hy-dot"' in mats and ".nm::after" not in (here / "variants.js").read_text()
    assert 'createElement("hy-led")' in blender and '"off"' in blender


DOC = "() => import('/plugins/3d/engine.js').then(m => m.docOf('3d/scenes/a/scene.json'))"


def test_3d_studio_numbers_scrub_by_their_letter(tmp_path):
    """round 16's scrub, version A (owner 2026-10-10 on r16-scrub.html: «отлично, беру»): Location and Rotation are one row of X Y Z
    <hy-scrub> fields each (the DialKit patch mountVec), the letter drags, ⇧ ×10, Esc puts it back and keeps the studio open, one history
    step a drag; the render size's W and H letters drag too"""
    port, lib, stop = board_server(tmp_path, {"c": dict(CARD)}, {"a": SITE2}, lang="en")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            errors = []; page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(f"http://127.0.0.1:{port}/canvas.html")
            page.wait_for_function("() => typeof PLGST !== 'undefined' && PLGST.some(p => p.name === '3d' && p.ok)", timeout=20000)
            page.evaluate("() => { setPref('theme', 'dark'); renderBg(); }")
            page.dblclick(".plg[data-id=c]", position={"x": 30, "y": 30}); page.wait_for_selector(".m3r .hy-slider", timeout=60000)
            page.wait_for_timeout(1200); go_on(page)
            # the render size: W and H are handles
            assert page.locator(".m3r .m3res .wh label > span.hy-scrub-h").count() == 2
            # an object picked: Location, cm and Rotation, ° as rows of three scrub fields
            page.locator(".m3l .ms[data-s=objects] .row[data-u] .nm").first.click(); page.wait_for_timeout(600)
            vec = page.locator(".m3r .dk .dialkit-vec", has_text="Location, cm")
            assert vec.locator("hy-scrub").evaluate_all("fs => fs.map(f => f.getAttribute('label'))") == ["X", "Y", "Z"]
            assert page.locator(".m3r .dk .dialkit-vec", has_text="Rotation, °").locator("hy-scrub").count() == 3
            if os.environ.get("HYIMG_TEST_SHOTS"):
                page.screenshot(path=os.path.join(os.environ["HYIMG_TEST_SHOTS"], "micro-3d-scrub.png"))
            x = vec.locator('hy-scrub[label="X"]')
            assert x.evaluate("f => [Math.round(f.getBoundingClientRect().height), getComputedStyle(f.handle).cursor]") == [24, "ew-resize"]
            loc0 = page.evaluate(DOC)["objects"][0]["loc"][0]

            def hist():
                page.click('.m3tabs [data-tab="hist"]'); page.wait_for_timeout(200)
                n = page.locator(".m3hist .hrow").count()
                page.click('.m3tabs [data-tab="props"]'); page.wait_for_timeout(300)
                return n
            h0 = hist()
            x = page.locator(".m3r .dk .dialkit-vec", has_text="Location, cm").locator('hy-scrub[label="X"]')
            b = x.locator(".hy-scrub-h").bounding_box(); cx, cy = b["x"] + b["width"] / 2, b["y"] + b["height"] / 2
            page.mouse.move(cx, cy); page.mouse.down()
            for i in range(1, 5): page.mouse.move(cx + 5 * i, cy)
            page.mouse.up(); page.wait_for_timeout(500)
            loc1 = page.evaluate(DOC)["objects"][0]["loc"][0]
            assert abs((loc1 - loc0) - 0.02) < 1e-6, (loc0, loc1)   # 20 px of 0.1 cm
            assert hist() == h0 + 1
            x = page.locator(".m3r .dk .dialkit-vec", has_text="Location, cm").locator('hy-scrub[label="X"]')
            b = x.locator(".hy-scrub-h").bounding_box(); cx, cy = b["x"] + b["width"] / 2, b["y"] + b["height"] / 2
            page.mouse.move(cx, cy); page.mouse.down(); page.keyboard.down("Shift")
            for i in range(1, 5): page.mouse.move(cx + 5 * i, cy)
            page.keyboard.press("Escape"); page.keyboard.up("Shift"); page.mouse.up(); page.wait_for_timeout(500)
            assert abs(page.evaluate(DOC)["objects"][0]["loc"][0] - loc1) < 1e-6 and page.locator(".plg-live").count() == 1
            assert not errors, errors
            browser.close()
    finally:
        stop()
