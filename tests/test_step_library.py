"""STEP files as files of their folders (owner 2026-10-07, project «Field Kit»: the folder «modeling C4D» holds STEP files, «я не могу
их смотреть через наш 3D просмотрщик»). The library listed 3D files only under its «3D» filter: the folder view showed the folder's PNG
pictures and not the STEP beside them, a folder holding only a .stp was not there at all, a click on a 3D tile put it on the board, a
3D tile could not be dragged, its turntable was drawn only in the 3D filter, and a 3D card made in the app could not be found by hy.py
by its file's name.

Now a 3D file is a card of its folder like a PSD or a PDF: its kind on the tile (STEP, STP), «converting…» while FreeCAD works, its
turntable when done, the reason when it cannot be read; a click opens it in the library's viewer as a 3D model to turn; dragged onto the
board (or placed there by hy.py as a picture) it becomes a 3D card, which converts it and shows it. The names are the owner's kind:
commas, spaces, dots in folder names, .stp beside .step. The STEP files are made by FreeCAD in the test (test_cad.py), nothing is
downloaded; without FreeCAD the tests skip. Chromium and WebKit.

  HYIMG_REPO=<Hyimg checkout> python3 -m pytest tests/test_step_library.py
"""
import io, json, os, subprocess, sys, time
from pathlib import Path

import pytest
from PIL import Image
from playwright.sync_api import sync_playwright

from test_cad import FC, cadhy, steps, ask, until_ready, runs   # noqa: F401  (fixtures: a server with the plugin and its own cache; FreeCAD's STEP files)
from test_3d_files import ENGINES, get, open_library, open_board, png_sheet
from test_canvas_3d import REPO

pytestmark = pytest.mark.skipif(FC is None, reason="no FreeCAD on this Mac (nothing is installed or downloaded for the tests)")
CABLE = "snap shot.9/bracket 0,6ft v1.1.step"   # a dotted folder, a comma, spaces
PROTO = "drafts/hinge prototype.stp"           # a folder that holds nothing but this .stp
SHOTS = Path(os.environ.get("HYIMG_SHOTS") or "/tmp/hyimg-step-shots")


def lay_out(lib, steps):
    for rel in (CABLE, PROTO):
        (lib / rel).parent.mkdir(parents=True, exist_ok=True); (lib / rel).write_bytes((steps / "part.step").read_bytes())
    Image.new("RGB", (80, 60), (40, 40, 44)).save(lib / "snap shot.9/pic1.png")   # the folder's picture, as the owner's snapshot folders have


def items(port): return {i["path"]: i for i in json.loads(get(port, "/api/items")[1])}


def tile(page, name): return page.locator(f"#list .card.m3d[aria-label={json.dumps(name)}]")


def test_3d_files_are_cards_of_their_folders(cadhy, steps):
    port, lib, log, cache = cadhy
    lay_out(lib, steps)
    got = items(port)
    assert CABLE in got and PROTO in got and "snap shot.9/pic1.png" in got, sorted(got)
    c, p = got[CABLE], got[PROTO]
    assert (c["kind"], c["ext"], c["folder"], c["name"]) == ("model", "STEP", "snap shot.9", "bracket 0,6ft v1.1"), c
    assert (p["kind"], p["ext"], p["folder"]) == ("model", "STP", "drafts") and p["sprite"] is None and p["ver"] > 0, p
    assert c["title"] and c["feedback"] == {} and c["tags"] == [] and isinstance(c["refpaths"], list), "a 3D file has the fields of a frame"
    assert "models/test.glb" not in got or got["models/test.glb"]["kind"] == "model"
    # nothing makes a picture of it the slow way (Quick Look on a STEP): no turntable yet is a 404 at once
    t0 = time.time(); assert get(port, "/thumb?p=" + PROTO.replace(" ", "%20") + "&s=320")[0] == 404 and time.time() - t0 < 3
    # its ratings go into its own json, <file>.stp.json: a picture of the same name beside it keeps its own
    r = get(port, "/api/feedback", json.dumps({"path": PROTO, "name": p["name"], "fav": True}).encode(), {"Content-Type": "application/json"})
    assert r[0] == 200, r
    assert (lib / (PROTO + ".json")).is_file() and not (lib / "drafts/hinge prototype.json").exists()
    assert items(port)[PROTO]["feedback"].get("fav") is True
    # a turntable drawn by a page shows in the list at once, and the thumbnail is its first view
    assert get(port, "/api/sprite?p=" + PROTO.replace(" ", "%20") + "&n=36&cols=6&cell=256", png_sheet(), {"Content-Type": "image/png"})[0] == 200
    assert items(port)[PROTO]["sprite"]["n"] == 36
    code, body, _h = get(port, "/thumb?p=" + PROTO.replace(" ", "%20") + "&s=320")
    assert code == 200 and Image.open(io.BytesIO(body)).size[0] > 100


def drop(frame, paths, x=700, y=400):
    frame.evaluate("""([ps, x, y]) => { const dt = new DataTransfer(); dt.setData('text/x-frame', ps[0]); dt.setData('text/x-frames', JSON.stringify(ps));
      stage.dispatchEvent(new DragEvent('drop', { dataTransfer: dt, clientX: x, clientY: y, bubbles: true, cancelable: true })); }""", [paths, x, y])


def cards3d(frame): return frame.evaluate("() => Object.entries(board.items).filter(([k, i]) => i.type === 'model3d').map(([k, i]) => ({ id: k, ...i }))")


@pytest.mark.parametrize("cadhy", [{"delay": 2.0}], indirect=True)
@pytest.mark.parametrize("engine", ENGINES)
def test_the_folder_view_shows_a_step_opens_it_in_3d_and_puts_it_on_the_board(cadhy, steps, engine):
    port, lib, log, cache = cadhy
    lay_out(lib, steps)
    SHOTS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser, page, errors = open_library(p, engine, port)
        page.wait_for_selector("#list .card.m3d")
        assert not page.evaluate("() => document.body.classList.contains('m3dmode')"), "the folder view, not the 3D filter"
        assert page.locator("#list .card:not(.m3d)").count() >= 1, "the pictures stay beside them"
        assert tile(page, "bracket 0,6ft v1.1").locator(".pill.kd").text_content() == "STEP"
        assert tile(page, "hinge prototype").locator(".pill.kd").text_content() == "STP"
        assert page.locator(".frow[data-f='drafts']").count() == 1, "the folder of a lone .stp is a folder"
        # FreeCAD is slowed by 2 s: the tile says it converts, then turns into the turntable's picture
        page.wait_for_function("() => [...document.querySelectorAll('#list .card.m3d')].some(c => c.dataset.note === 'converting…')", timeout=30000)
        page.wait_for_function("() => [...document.querySelectorAll('#list .card.m3d')].every(c => !c.classList.contains('nosp') && !c.dataset.note)", timeout=150000)
        assert all(i["sprite"] for i in json.loads(get(port, "/api/models3d")[1]) if i["path"] in (CABLE, PROTO))
        assert tile(page, "bracket 0,6ft v1.1").get_attribute("draggable") == "true", "a 3D tile can be dragged onto the board"
        page.screenshot(path=str(SHOTS / f"{engine}-folder-view.png"))
        # a click opens the viewer with the model in 3D, which turns under a drag
        tile(page, "bracket 0,6ft v1.1").click()
        page.wait_for_function("() => document.querySelector('#viewer').classList.contains('open')")
        page.wait_for_function("() => { const v = document.querySelector('#viewer .v3d'); return v && !v.hidden && v.querySelector('canvas') && v.dataset.state === 'ready'; }", timeout=60000)
        assert page.evaluate("() => getComputedStyle(document.querySelector('#frame')).visibility") == "hidden", "no picture under the model"
        box = page.locator("#viewer .v3d canvas").bounding_box(); assert box["width"] > 300 and box["height"] > 300, box
        page.wait_for_timeout(500)
        a = Image.open(io.BytesIO(page.locator("#viewer .v3d canvas").screenshot())).convert("L")
        assert a.getextrema()[1] - a.getextrema()[0] > 40, "the model is drawn, not an empty view"
        page.screenshot(path=str(SHOTS / f"{engine}-viewer-cable.png"))
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2); page.mouse.down()
        page.mouse.move(box["x"] + box["width"] / 2 + 160, box["y"] + box["height"] / 2, steps=8); page.mouse.up(); page.wait_for_timeout(400)
        b = Image.open(io.BytesIO(page.locator("#viewer .v3d canvas").screenshot())).convert("L")
        from PIL import ImageChops
        assert sum(ImageChops.difference(a, b).getdata()) / (a.width * a.height) > 0.5, "a drag turns the model"
        assert page.evaluate("() => document.querySelector('#viewer').classList.contains('open')"), "the drag did not close or comment"
        # Escape closes the viewer and the 3D view goes with it
        page.keyboard.press("Escape")
        page.wait_for_function("() => !document.querySelector('#viewer').classList.contains('open')")
        assert page.evaluate("() => { const v = document.querySelector('#viewer .v3d'); return !v || v.hidden || !v.querySelector('canvas'); }")
        assert page.evaluate("() => getComputedStyle(document.querySelector('#frame')).visibility") != "hidden"
        # the library's drag carries the file; dropped on the board it is a 3D card that shows the model
        carried = tile(page, "bracket 0,6ft v1.1").evaluate("""c => { const dt = new DataTransfer();
            c.dispatchEvent(new DragEvent('dragstart', { dataTransfer: dt, bubbles: true, cancelable: true }));
            return dt.getData('text/x-frame'); }""")
        assert carried == CABLE, carried
        frame = next(f for f in page.frames if "/canvas" in f.url)
        frame.wait_for_function("() => typeof PLGST !== 'undefined' && PLGST.some(p => p.name === '3d' && p.ok)", timeout=30000)
        steps0 = frame.evaluate("() => past.length")
        drop(frame, [CABLE])
        frame.wait_for_function("() => Object.values(board.items).some(i => i.type === 'model3d')", timeout=10000)
        assert not frame.evaluate("() => Object.values(board.items).some(i => i.path)"), "not a picture card"
        frame.wait_for_function("() => Object.values(board.items).some(i => i.type === 'model3d' && i.scene && !i.empty && !i.pending)", timeout=120000)
        card = cards3d(frame)[0]
        assert card["name"] == "bracket 0,6ft v1.1" and abs(card["w"] / card["h"] - 0.8) < 0.02, card
        doc = json.loads((lib / card["scene"]).read_text())
        obj = next(o for o in doc["objects"] if o["src"]["type"] == "file")
        assert obj["src"]["path"].startswith("3d/converted/") and obj["name"] == "bracket 0,6ft v1.1", obj
        shown = f"() => {{ const i = document.querySelector('.plg[data-id={card['id']}] img.m3'); return i && i.complete && i.naturalWidth > 0; }}"
        frame.wait_for_function(shown, timeout=60000)
        page.wait_for_timeout(1500)
        page.screenshot(path=str(SHOTS / f"{engine}-board-card.png"))
        assert frame.evaluate("() => past.length") == steps0 + 1, "the drop is one step of the board"
        # hy.py finds the card by its file's name
        out = subprocess.run([sys.executable, str(REPO / "review/hy.py"), "find", "0,6ft", "--port", str(port)], capture_output=True, text=True, timeout=60)
        assert "model3d" in out.stdout and card["id"] in out.stdout, out.stdout + out.stderr
        assert not errors, errors
        browser.close()
    assert runs(log).count("freecad") == 1, f"one FreeCAD run for the two copies of one content: {runs(log)}"


@pytest.mark.parametrize("engine", ENGINES)
def test_a_picture_card_of_a_3d_file_becomes_a_3d_card(cadhy, steps, engine):
    """hy.py place (or a Hyimg without the 3D plugin) puts a 3D file on the board as a picture: the plugin makes it a 3D card in its place"""
    port, lib, log, cache = cadhy
    lay_out(lib, steps)
    (lib.parent / "state/boards/main.json").write_text(json.dumps({"items": {"i1": {"path": PROTO, "x": 100, "y": 80, "w": 320, "ar": 1, "crop": None}}, "groups": {}, "revision": 2}))
    with sync_playwright() as p:
        browser, page, frame, errors = open_board(p, engine, port)
        frame.wait_for_function("() => board.items.i1 && board.items.i1.type === 'model3d' && !board.items.i1.path", timeout=20000)
        frame.wait_for_function("() => board.items.i1.scene && !board.items.i1.empty", timeout=120000)
        it = frame.evaluate("() => board.items.i1")
        assert (it["x"], it["y"], it["w"], it["name"]) == (100, 80, 320, "hinge prototype"), it
        # open_board loads the page twice: WebKit reports a fetch the reload cut off (a turntable being drawn) as an error of the old page
        assert not [e for e in errors if "due to access control checks" not in e], errors
        browser.close()
