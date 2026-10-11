"""The 3D editor in the app's one UI system (owner 2026-10-06, screenshots: «почему они опять несинхронны, одни круглые другие квадратные»,
«почему-то они не круглые в 3d studio сами эти элементы», «why so much inconsistencies in ui, just make all ui consistant»):

- every control of a row in the inspector (sliders, selects, fields, buttons) has one radius, a block's well's 6 px in both shapes (round 12);
- the tools are circles in the board's dock and drawn in the frame editor's icon family (ui/icons.js);
- the layer list: the library's search field and rows, sections that fold and are sized by the app's splitter (a double click gives the
  sizes back to the content), a right click with the app's colour row whose colour marks a node and what is under it, kept in scene.json;
- the scene's title is a plate in the top band like a stuck group title;
- ⌘. hides the panels with the board's interface, the view shows no pink marks then.
Chromium and WebKit, the app's page with the canvas in its frame.

  HYIMG_REPO=<Hyimg checkout> python3 -m pytest tests/test_editor_consistency.py
  M3_SHOTS=<folder> also saves screenshots
"""
import json, os

import pytest
from playwright.sync_api import sync_playwright

from test_canvas_3d import hy as _hy, wait_file   # noqa: F401
from test_3d_files import ENGINES, new_card, open_board, scene_of
from test_editor_ui import go_on, open_editor

hy = _hy
SHOTS = os.environ.get("M3_SHOTS")


def shot(page, name):
    if SHOTS: os.makedirs(SHOTS, exist_ok=True); page.screenshot(path=os.path.join(SHOTS, name + ".png"))


RADII = """() => { const r = el => getComputedStyle(el).borderTopLeftRadius;
  const q = s => [...document.querySelectorAll(s)].filter(e => e.getClientRects().length);
  return { slider: q('.m3r .hy-slider').map(r), select: q('.m3r .dialkit-select-trigger').map(r), text: q('.m3r .dialkit-text-control').map(r),
    button: q('.m3r .dialkit-button, .m3r .dialkit-action-button').map(r), toggle: q('.m3r .dialkit-toggle').map(r), color: q('.m3r .dialkit-color-control').map(r),
    search: q('.m3l .hy-search > input').map(r) }; }"""


def radii_agree(frame, want):
    got = frame.evaluate(RADII)
    flat = {k: set(v) for k, v in got.items() if v}
    assert flat.get("slider") and flat.get("select"), got   # the scene's panel: lens, distance… and camera, frame
    for k, v in flat.items():
        assert v == {want}, (k, v, want, got)
    return got


@pytest.mark.parametrize("hy", ["en"], indirect=True)
@pytest.mark.parametrize("engine", ENGINES)
def test_one_radius_round_tools_and_one_icon_family(hy, engine):
    port, lib = hy
    with sync_playwright() as p:
        browser, page, frame, errors = open_board(p, engine, port)
        cid = new_card(frame); wait_file(scene_of(lib, frame, cid), lambda d: len(d["objects"]) == 2)
        open_editor(frame, cid)
        frame.wait_for_selector(".m3r .hy-slider", timeout=15000); frame.wait_for_selector(".m3r .dialkit-select-trigger")
        # every row control has one radius, the selects as the sliders: a block's well, 6 px in both shapes (round 12 «A · Line», owner
        # 2026-10-09: «реализуй уже A Line версию на весь интерфейс»; until then the app's --hy-row-r, a pill in the round shape)
        radii_agree(frame, "6px")
        # the tools in the board's dock are Hyimg's one dock button, 36 × 34 with round ends (owner 2026-10-10 on round 18: one size in every
        # dock; they were 34 × 34 circles since 2026-10-06)
        for k in ("select", "translate", "rotate", "scale", "smart"):
            b = frame.evaluate(f"() => {{ const b = document.querySelector('#dock .plgdock [data-tool={k}]'), r = b.getBoundingClientRect(); return {{ w: r.width, h: r.height, rad: parseFloat(getComputedStyle(b).borderTopLeftRadius) }}; }}")
            assert (round(b["w"]), round(b["h"])) == (36, 34) and b["rad"] >= b["h"] / 2, (k, b)
        # one icon family: the tools' drawings are ui/icons.js's, in its 1.85 line (the frame editor's)
        fam = frame.evaluate("""() => { const map = { select: 'select', translate: 'move', rotate: 'rotate', scale: 'scale', smart: 'pull' };
          return Object.entries(map).map(([k, f]) => { const s = document.querySelector(`#dock .plgdock [data-tool=${k}] svg`);
            const ref = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); ref.innerHTML = HY_TOOL_IC[f];
            return { k, same: s.innerHTML === ref.innerHTML, line: s.getAttribute('stroke-width') }; }); }""")
        assert all(f["same"] and f["line"] == "1.85" for f in fam), fam
        shot(page, f"3d-round-{engine}")
        # pro: the same controls, still one radius (the block's 6 px)
        frame.evaluate("() => { document.documentElement.dataset.shape = 'pro'; }"); frame.wait_for_timeout(200)
        radii_agree(frame, "6px")
        b = frame.evaluate("() => getComputedStyle(document.querySelector('#dock .plgdock [data-tool=select]')).borderTopLeftRadius")
        assert b == "8px", b
        shot(page, f"3d-pro-{engine}")
        frame.evaluate("() => { document.documentElement.dataset.shape = 'round'; }")
        assert not errors, errors
        browser.close()


SECS = """() => Object.fromEntries([...document.querySelectorAll('.m3l .ms')].map(s => [s.dataset.s, { shown: !s.hidden, shut: s.classList.contains('shut'),
  h: Math.round(s.querySelector('.msb').getBoundingClientRect().height), fixed: s.classList.contains('fixed') }]))"""


@pytest.mark.parametrize("hy", ["en"], indirect=True)
@pytest.mark.parametrize("engine", ENGINES)
def test_the_layer_list_sections_colours_and_the_title_plate(hy, engine):
    port, lib = hy
    with sync_playwright() as p:
        browser, page, frame, errors = open_board(p, engine, port)
        cid = new_card(frame); scene = scene_of(lib, frame, cid); wait_file(scene, lambda d: len(d["objects"]) == 2)
        open_editor(frame, cid)
        # the search field is a block's well, 28 px (round 12, Hyimg ui/hy/block.css), the rows the library's
        look = frame.evaluate("""() => { const i = document.querySelector('.m3l .hy-search > input'), cs = getComputedStyle(i), row = document.querySelector('.m3l .row[data-u]'), rs = getComputedStyle(row);
          return { h: i.getBoundingClientRect().height, pad: cs.paddingLeft, rowH: row.getBoundingClientRect().height, rowR: rs.borderTopLeftRadius }; }""")
        assert look == {"h": 28, "pad": "30px", "rowH": 28, "rowR": "8px"}, look
        frame.click(".m3l .row[data-u]:has-text('Object')"); frame.wait_for_timeout(300)
        sel = frame.evaluate("() => { const r = document.querySelector('.m3l .row.sel'), cs = getComputedStyle(r); return { bg: cs.backgroundColor, ring: cs.boxShadow, raise: getComputedStyle(document.documentElement).getPropertyValue('--raise').trim() }; }")
        assert "rgba(0, 0, 0, 0)" != sel["bg"] and "255, 79" not in sel["ring"], ("the picked row: a grey fill and a hairline, no pink outline", sel)
        # three sections with a line between them («Материалы», 5d6d864, shows only for a scene with materials: tests/test_light_materials.py)
        s0 = {k: v for k, v in frame.evaluate(SECS).items() if k in ("objects", "lights", "cameras")}
        assert all(v["shown"] and not v["shut"] and not v["fixed"] for v in s0.values()), s0
        assert frame.locator(".m3l .msp.hy-split:visible").count() == 2
        # fold and unfold Lights by its title: the rows close with the app's curve, the chevron turns
        GLIDE = "() => { const tr = document.querySelector('.m3l .tr'), on = tr.classList.contains('glide'); tr.classList.add('glide'); const v = getComputedStyle(tr.querySelector('.ms[data-s=lights] .msb')).transitionTimingFunction; tr.classList.toggle('glide', on); return v; }"
        assert frame.evaluate(GLIDE) == "cubic-bezier(0.32, 0.72, 0, 1)"
        HL = "() => Math.round(document.querySelector('.m3l .ms[data-s=lights] .msb').getBoundingClientRect().height)"
        frame.click(".m3l .ms[data-s=lights] .msh"); frame.wait_for_function(HL + " === 0", timeout=5000)
        s1 = frame.evaluate(SECS); assert s1["lights"]["shut"] and s1["lights"]["h"] == 0, s1
        ROT = "() => { const m = new DOMMatrix(getComputedStyle(document.querySelector('.m3l .ms[data-s=%s] .mtg .hy-chev')).transform); return Math.round(Math.atan2(m.b, m.a) * 180 / Math.PI); }"
        frame.wait_for_function(f"() => ({ROT % 'lights'})() === 0", timeout=5000)   # folded: the chevron points right
        assert frame.evaluate(ROT % "objects") == 90, "open: turned down"
        frame.click(".m3l .ms[data-s=lights] .msh"); frame.wait_for_function(f"() => ({HL})() === {s0['lights']['h']} && !document.querySelector('.m3l .tr').classList.contains('glide')", timeout=5000)
        s2 = frame.evaluate(SECS); assert not s2["lights"]["shut"] and s2["lights"]["h"] == s0["lights"]["h"], (s0, s2)
        # drag the line under Objects up: every section shows all its rows, so nothing moves (the stack never cuts a section to leave the
        # room empty) and nothing gets a size; a double click keeps them automatic (the stack on a full panel: test_outliner_sections.py)
        sp = frame.locator(".m3l .msp[data-before=lights]"); b = sp.bounding_box()
        page.mouse.move(b["x"] + b["width"] / 2, b["y"] + 4); page.mouse.down(); page.mouse.move(b["x"] + b["width"] / 2, b["y"] + 4 - 20, steps=6); page.mouse.up(); frame.wait_for_timeout(200)
        s3 = frame.evaluate(SECS)
        assert all(s3[k]["h"] == s0[k]["h"] and not s3[k]["fixed"] for k in s0), (s0, s3)
        shot(page, f"3d-sections-dragged-{engine}")
        sp.dblclick(); frame.wait_for_function("() => !document.querySelector('.m3l .ms[data-s=objects]').classList.contains('fixed')", timeout=5000); frame.wait_for_timeout(450)
        s4 = frame.evaluate(SECS)
        assert not s4["objects"]["fixed"] and not s4["lights"]["fixed"] and s4["objects"]["h"] == s0["objects"]["h"], (s0, s4)
        # a right click on the object: the app's menu with the colour row on top; blue marks the row and the rows under it
        frame.click(".m3l .row[data-u]:has-text('Object')", button="right"); frame.wait_for_selector("#ctx.open .msw button[data-color=blue]")
        assert frame.locator("#ctx.open .msw button").first.get_attribute("data-color") == "", "«no colour» first"
        shot(page, f"3d-menu-{engine}")
        frame.click("#ctx.open .msw button[data-color=blue]"); frame.wait_for_timeout(300)
        assert not frame.evaluate("() => document.getElementById('ctx').classList.contains('open')")
        oid = frame.evaluate("() => document.querySelector('.m3l .row[data-u].nc').dataset.k")
        d = wait_file(scene, lambda d: (d.get("ui") or {}).get("colors", {}).get(oid) == "blue")
        assert d["objects"][0].get("color") in (None, d["objects"][0].get("color")), "the material is not touched"
        tint = frame.evaluate("() => { const r = document.querySelector(`.m3l .row[data-k='${CSS.escape(" + json.dumps(oid) + ")}']`); return { nc: r.style.getPropertyValue('--nc'), label: getComputedStyle(r.querySelector('.nm')).color, icon: getComputedStyle(r.querySelector(':scope > .ic')).color }; }")
        assert tint["nc"] == "#7dbbf5" and tint["label"] == "rgb(125, 187, 245)" and tint["icon"] == "rgb(125, 187, 245)", tint
        # the undo and the reset of the scene leave the list's colours alone: the reset button stays pale
        assert frame.evaluate("() => document.querySelector('#dock .plgdock [data-a=reset]').disabled"), "a colour is not a change of the scene"
        # inheritance: a light without its own colour has none; a light coloured red keeps red; the camera row gets green
        frame.click(".m3l .row[data-u]:has-text('Key')", button="right"); frame.click("#ctx.open .msw button[data-color=red]"); frame.wait_for_timeout(300)
        frame.click(".m3l .row[data-cam]", button="right"); frame.click("#ctx.open .msw button[data-color=green]"); frame.wait_for_timeout(300)
        d = wait_file(scene, lambda d: len((d.get("ui") or {}).get("colors", {})) == 3)
        # no colour clears it
        frame.click(".m3l .row[data-cam]", button="right"); frame.click("#ctx.open .msw button[data-color='']"); frame.wait_for_timeout(300)
        d = wait_file(scene, lambda d: len((d.get("ui") or {}).get("colors", {})) == 2)
        shot(page, f"3d-colours-{engine}")
        # the scene's name: the crumb's last step (Hyimg ui/modes.js doc(), round 20 «Одна оболочка», 2026-10-11), the path in its tooltip;
        # the plate «3D scene 3d/scenes/…» beside the crumb is gone
        step = frame.evaluate("() => { const s = document.getElementById('cStudio'); return s && [s.textContent.trim(), s.title, s === document.getElementById('crumb').lastElementChild]; }")
        assert step and step[0] == "3D scene" and step[1].endswith("/scene.json") and step[2], step
        assert frame.locator(".m3title").count() == 0
        assert frame.locator(".m3l .lh").count() == 0, "the title left the panel"
        # the colours come back after the editor closes and opens again (they are the scene file's)
        page.keyboard.press("Meta+Enter"); frame.wait_for_function("() => !document.querySelector('.m3ui')", timeout=15000)
        open_editor(frame, cid)
        assert frame.locator(".m3l .row.nc").count() >= 2
        assert not errors, errors
        browser.close()


@pytest.mark.parametrize("hy", ["en"], indirect=True)
@pytest.mark.parametrize("engine", ENGINES)
def test_hide_interface_takes_the_panels_and_the_view_shows_no_marks(hy, engine):
    port, lib = hy
    with sync_playwright() as p:
        browser, page, frame, errors = open_board(p, engine, port)
        cid = new_card(frame); wait_file(scene_of(lib, frame, cid), lambda d: len(d["objects"]) == 2)
        # the pink outline, the Scene panel's other highlight (the ghost, the default, has its own hidden-interface check: test_ghost.py)
        frame.evaluate("() => localStorage.setItem('cv.m3.hl', 'outline')")
        open_editor(frame, cid)
        frame.click(".m3l .row[data-u]:has-text('Object')"); frame.wait_for_timeout(400)
        assert frame.evaluate("() => ['.m3l', '.m3r', '.m3x'].every(s => document.querySelector(s).hasAttribute('data-hyui'))")
        pink = """() => { const c = document.querySelector('canvas.m3live'), g = document.createElement('canvas'); g.width = c.width; g.height = c.height; const x = g.getContext('2d'); x.drawImage(c, 0, 0);
          const d = x.getImageData(0, 0, g.width, g.height).data; let n = 0; for (let i = 0; i < d.length; i += 4) if (d[i] > 200 && d[i + 1] < 140 && d[i + 2] > 120 && d[i + 2] < 220) n++; return n; }"""
        frame.evaluate("() => import('/plugins/3d/engine.js').then(m => m.nudge(m.liveInfo().id))"); frame.wait_for_timeout(400); go_on(frame)
        before = frame.evaluate(pink)
        assert before > 50, ("the picked object is outlined in pink while the interface shows", before)
        page.keyboard.press("Meta+Period"); frame.wait_for_timeout(600)
        assert frame.evaluate("() => document.documentElement.classList.contains('hy-hideui')")
        OP = "() => ['.m3l', '.m3r', '.m3x', '#crumb'].map(s => +getComputedStyle(document.querySelector(s)).opacity)"
        frame.wait_for_function(f"() => ({OP})().every(o => o < 0.05)", timeout=8000)   # a software-GL frame can be slow: the board's animation runs on
        assert frame.evaluate(pink) == 0, "the bare view: no pick or hover marks"
        shot(page, f"3d-hidden-{engine}")
        page.keyboard.press("Meta+Period")
        frame.wait_for_function(f"() => ({OP})().every(o => o > 0.95)", timeout=8000)
        assert not errors, errors
        browser.close()
