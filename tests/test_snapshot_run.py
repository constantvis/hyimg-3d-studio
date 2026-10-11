"""A snapshot of 3D Studio says how long it took and where it ran (owner 2026-10-11: «затраченное время на генерацию или рендеринг,
обязательный параметр ... либо compute power какой-то условный», «ну это для 3д генераций в том числе»): the view, its masks and its depth
in 3d/shots each have "seconds" and "compute" in their json, Hyimg's fields (its docs/data.md). Chromium, the plugin's own server fixture."""
import json

from playwright.sync_api import sync_playwright

from test_canvas_3d import CORNER, go_on, hy, wait_file  # noqa: F401  (the fixture)


def test_a_snapshot_records_its_seconds_and_compute(hy):
    port, lib = hy
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        page = browser.new_page(viewport={"width": 1500, "height": 950}, color_scheme="dark")
        errors = []; page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"http://127.0.0.1:{port}/canvas.html")
        page.wait_for_function("() => typeof PLGST !== 'undefined' && PLGST.some(p => p.name === '3d' && p.ok)", timeout=20000)
        page.click("#bplus"); page.click("#bplusm [title^='3D-сцена']")
        page.wait_for_function("() => Object.values(board.items).some(i => i.type === 'model3d' && i.scene)")
        it = page.evaluate("() => Object.values(board.items).find(i => i.type === 'model3d')")
        wait_file(lib / it["scene"], lambda d: len(d["objects"]) == 2)
        page.wait_for_function("() => { const i = document.querySelector('.plg[data-type=model3d] img.m3'); return i && i.src.startsWith('data:image') }", timeout=30000)
        page.dblclick(".plg[data-type=model3d]", position=CORNER)
        page.wait_for_selector(".m3ui .m3l .row")
        go_on(page); page.keyboard.press("p")
        page.wait_for_function("() => Object.values(board.items).filter(i => i.path && i.path.startsWith('3d/shots/')).length === 3", timeout=60000)
        metas = [json.loads(x.read_text()) for x in sorted((lib / "3d/shots").rglob("*.json"))]
        assert {m["pass"] for m in metas} == {"вид", "маски", "глубина"}, metas
        assert all(isinstance(m.get("seconds"), (int, float)) and m["seconds"] > 0 and m.get("compute") == "local · three.js r180 · WebGL" for m in metas), metas
        assert not errors, errors
        browser.close()
