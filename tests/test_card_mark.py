"""The 3D card's «3D» is the board's kind pill (owner 2026-10-06: «why is it not consistent with the marks on pictures and videos»,
then one system for every mark, with the numbers of the owner's lab, 2026-10-06): a cube icon before «3D» as ▶ before a video's time,
26 px tall at full size, 8.5 px from the card's bottom right corner, the icon 66% of the plate, 11 px type, folded into a circle on a card
under 104 px, gone (scaled to 0, then display:none) under 24 px.

  HYIMG_REPO=<Hyimg checkout> python3 -m pytest tests/test_card_mark.py
"""
import json, os, subprocess, sys, time, urllib.request, uuid

from playwright.sync_api import sync_playwright

from test_canvas_3d import REPO, HERE, SITE2, tiny_model, free_port

PILL = """() => { const el = document.querySelector('.plg[data-type=model3d]'), m = el.querySelector('.mk-kind'), c = el.getBoundingClientRect(), r = m.getBoundingClientRect(), s = getComputedStyle(m);
  const i = m.querySelector('.kp svg'), ib = i ? i.getBoundingClientRect() : { height: 0 };
  return { r: c.right - r.right, b: c.bottom - r.bottom, w: r.width, h: r.height, icon: ib.height, d: i ? i.querySelector('path').getAttribute('d') : '', text: m.querySelector('.b3').textContent,
    font: parseFloat(getComputedStyle(m.querySelector('.kt')).fontSize) * cam.z, display: s.display, bg: s.backgroundColor }; }"""


def test_the_3d_mark_is_the_boards_kind_pill(tmp_path):
    lib, state, plugins = tmp_path / "lib", tmp_path / "state", tmp_path / "plugins"
    tiny_model(lib)
    (lib / "3d/scenes/a").mkdir(parents=True); (lib / "3d/scenes/a/scene.json").write_text(json.dumps(SITE2))
    items = {"m1": {"type": "model3d", "scene": "3d/scenes/a/scene.json", "camera": "jo1wd256", "x": 0, "y": 0, "w": 300, "h": 300}}
    (state / "boards").mkdir(parents=True); plugins.mkdir(); (plugins / "3d").symlink_to(HERE)
    (state / "app-settings.json").write_text(json.dumps({}))
    (state / "boards/main.json").write_text(json.dumps({"items": items, "groups": {}, "revision": 1}))
    port = free_port()
    env = {k: v for k, v in os.environ.items() if not k.startswith(("HYIMG_", "REVIEW_"))}
    env.update(HYIMG_LIBRARY_ROOT=str(lib), HYIMG_STATE_ROOT=str(state), HYIMG_PROJECT_ID=str(uuid.uuid4()), HYIMG_PLUGINS=str(plugins), HYIMG_SETTINGS=str(state / "app-settings.json"), PYTHONDONTWRITEBYTECODE="1")
    log = open(tmp_path / "server.log", "w+")
    proc = subprocess.Popen([sys.executable, str(REPO / "review/server.py"), str(port)], env=env, stdout=log, stderr=log)
    try:
        for _ in range(100):
            try: urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1); break
            except OSError: time.sleep(0.1)
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
            page = browser.new_page(viewport={"width": 1200, "height": 800})
            errors = []; page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(f"http://127.0.0.1:{port}/canvas.html")
            page.wait_for_function("() => typeof PLGST !== 'undefined' && PLGST.some(p => p.name === '3d' && p.ok) && document.querySelector('.plg[data-type=model3d] .mk-kind')", timeout=20000)
            page.evaluate("() => { cam.x = -40; cam.y = -40; cam.z = 1; renderCam(); render(); }")
            # grown in (a mark comes by scaling up from 0; the software GL here keeps the page busy while it draws the still)
            settled = "() => { const s = getComputedStyle(document.querySelector('.plg[data-type=model3d] .mk-kind')); return s.scale === '1' && s.opacity === '1'; }"
            page.wait_for_function(settled, timeout=20000)
            m = page.evaluate(PILL)
            assert m["d"] == page.evaluate("() => /d=\"([^\"]*)/.exec(HY_TOOL_IC.scene3d)[1]") and m["text"].startswith("3D"), m
            assert abs(m["h"] - 26) < 0.6 and abs(m["r"] - 8.5) < 0.6 and abs(m["b"] - 8.5) < 0.6 and abs(m["icon"] - 26 * .66) < 0.6 and abs(m["font"] - 11) < 0.3, m
            assert m["w"] > 40 and m["bg"].replace(" ", "") == "rgba(20,20,22,0.72)", m
            page.evaluate("() => { cam.z = 0.3; renderCam(); render(); }")   # 90 px: a circle
            page.wait_for_function("() => { const m = document.querySelector('.plg[data-type=model3d] .mk-kind').getBoundingClientRect(); return Math.abs(m.width - m.height) < 0.6; }", timeout=20000)
            m = page.evaluate(PILL)
            assert abs(m["w"] - m["h"]) < 0.6, m
            page.evaluate("() => { cam.z = 0.07; renderCam(); render(); }")   # 21 px: gone
            page.wait_for_function("() => getComputedStyle(document.querySelector('.plg[data-type=model3d] .mk-kind')).display === 'none'")
            assert not errors, errors
            browser.close()
    finally:
        proc.terminate(); proc.wait(5); log.close()
