"""3D Studio has no board blue left (owner 2026-10-09: «Давай еще раз проверь цвета, чтобы у нас все режимы соответствовали»; on the
white Discard of «Close without saving?»: «Она должна быть такого цвета, в каком режиме мы сейчас находимся»). While the studio is open
Hyimg's switch puts its pink on the board's root (hyimg ui/modes.js: data-studio, --hy-studio), so --sel, --hy-sel and the notes' info
colour are the pink, and the question before closing (hyimg ui/confirm.js) has its Discard filled with it, white words, Cancel as it was.
The test walks every visible element of the window (and its ::before and ::after) with a layer row picked, the tool in hand, an info
note up and the question open, and finds no computed colour equal to a board blue. Back on the board the selection is blue again.
Chromium, dark, the classic look (where the selection is blue).
"""
from playwright.sync_api import sync_playwright

from test_canvas_3d import SITE2, board_server, go_on

CARD = {"type": "model3d", "scene": "3d/scenes/a/scene.json", "camera": "jo1wd256", "x": 0, "y": 0, "w": 500, "h": 500}
# the board's blues: the selection (--sel dark #3b82f6, light #2563eb) and the notes' info (#0a84ff, light #007aff), any alpha, in the two
# forms Chromium gives a computed colour (rgb() and, from color-mix, color(srgb …))
WALK = """() => {
  const BLUE = [[59, 130, 246], [37, 99, 235], [10, 132, 255], [0, 122, 255]];
  const rgbs = s => [...s.matchAll(/rgba?\\(([^)]*)\\)/g)].map(m => m[1].split(/[\\s,\\/]+/).filter(Boolean).slice(0, 3).map(Number))
    .concat([...s.matchAll(/color\\(srgb ([^)]*)\\)/g)].map(m => m[1].split(/[\\s\\/]+/).filter(Boolean).slice(0, 3).map(x => +x * 255)));
  const blue = s => rgbs(s).some(c => BLUE.some(b => b.every((x, i) => Math.abs(x - c[i]) < 2.5)));
  const seen = el => { for (let e = el; e && e.nodeType === 1; e = e.parentElement) { const s = getComputedStyle(e); if (s.opacity === '0' || s.visibility === 'hidden') return false; } return true; };
  const name = el => el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + [...el.classList].slice(0, 3).map(c => '.' + c).join('');
  const out = [];
  for (const el of document.querySelectorAll('body *')) {
    const r = el.getBoundingClientRect(); if (!r.width || !r.height || r.right < 0 || r.bottom < 0 || r.left > innerWidth || r.top > innerHeight || !seen(el)) continue;
    const text = [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim()) || el instanceof SVGElement;
    for (const ps of [null, '::before', '::after']) {
      const s = getComputedStyle(el, ps); if (ps && (s.content === 'none' || s.content === 'normal')) continue;
      const props = ['background-color', 'background-image', 'box-shadow', 'fill', 'stroke'];
      if (text || ps) props.push('color');
      if (s.outlineStyle !== 'none' && parseFloat(s.outlineWidth)) props.push('outline-color');
      for (const sd of ['top', 'right', 'bottom', 'left']) if (parseFloat(s.getPropertyValue(`border-${sd}-width`))) props.push(`border-${sd}-color`);
      for (const p of props) { const v = s.getPropertyValue(p); if (v && blue(v)) out.push([name(el) + (ps || ''), p, v]); }
    }
  }
  return out;
}"""
PROBE = """([v, prop]) => { const p = document.createElement('i'); p.style.setProperty(prop, v); document.body.append(p);
  const c = getComputedStyle(p).getPropertyValue(prop); p.remove(); return c; }"""
BTN = "(s) => { const c = getComputedStyle(document.querySelector(s)); return [c.backgroundColor, c.color]; }"


def no_blue(page, where):
    found = page.evaluate(WALK)
    assert found == [], where + ":\n" + "\n".join(" ".join(f) for f in found)


def test_3d_studio_has_no_board_blue(tmp_path):
    port, lib, stop = board_server(tmp_path, {"c": dict(CARD)}, {"a": SITE2})
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
            page = browser.new_page(viewport={"width": 1600, "height": 1000}, color_scheme="dark")
            errors = []; page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(f"http://127.0.0.1:{port}/canvas.html")
            page.wait_for_function("() => typeof PLGST !== 'undefined' && PLGST.some(p => p.name === '3d' && p.ok)", timeout=20000)
            page.evaluate("() => { setPref('theme', 'dark'); renderBg(); }")
            assert page.evaluate("() => [document.documentElement.dataset.theme, document.documentElement.dataset.ui]") == ["dark", "classic"]
            pink, blue = page.evaluate(PROBE, ["#ff4fa3", "color"]), page.evaluate(PROBE, ["var(--sel)", "color"])
            assert blue == "rgb(59, 130, 246)", blue

            page.dblclick(".plg[data-id=c]", position={"x": 30, "y": 30}); page.wait_for_selector(".m3r .hy-slider", timeout=60000)
            page.wait_for_timeout(1200); go_on(page)
            page.wait_for_function("() => document.documentElement.dataset.studio === '3d'", timeout=3000)
            assert page.evaluate(PROBE, ["var(--sel)", "color"]) == pink   # the root's selection colour is the Studio's while it is open
            # a picked layer row, the tool in hand, an info note up
            page.click(".m3l .row[data-u]"); page.wait_for_selector(".m3l .row.sel", timeout=5000)
            page.click('#dock .plgdock [data-tool="translate"]')
            page.evaluate("() => hyToast('3D Studio: a note', 'info')"); page.wait_for_timeout(500)
            note = page.evaluate("() => getComputedStyle([...document.querySelectorAll('#hyToasts .ht')].pop()).color")
            assert note == pink, note
            no_blue(page, "the studio with a picked row, the tool in hand and a note")

            # something changed (the card moved on the board), Cancel: «Close without saving?», Discard in the pink, white words
            page.evaluate("() => { board.items.c.x += 10; }")
            page.click("[data-a=cancel]"); page.wait_for_selector("#hyConfirm.on [data-a=ok]", timeout=5000); page.wait_for_timeout(350)
            assert page.evaluate(BTN, "#hyConfirm [data-a=ok]") == [pink, "rgb(255, 255, 255)"], page.evaluate(BTN, "#hyConfirm [data-a=ok]")
            assert page.evaluate(BTN, "#hyConfirm [data-a=no]")[0] != pink
            no_blue(page, "the question before closing")
            page.click("#hyConfirm [data-a=ok]"); page.wait_for_function("() => !document.querySelector('.plg-live')", timeout=20000)

            # back on the board: the board's blue on the root again
            page.wait_for_function("() => !document.documentElement.dataset.studio", timeout=3000)
            assert page.evaluate(PROBE, ["var(--sel)", "color"]) == blue
            assert not errors, errors
            browser.close()
    finally:
        stop()
