"""A 3D file into a card (owner 2026-10-06: «When you press 3D it gives you our 3D frame, which offers: a button "Open file", or another button
"Open media library", where everything is already filtered to 3D files, and on hover they rotate so you can judge them. And also a list of
recent ones with previews and the same ability: on hover it automatically spins 360° around its own axis»).

The server lists the library's 3D files apart from its frames and keeps each file's turntable (a sheet of views) like a thumbnail; the
plugin draws the sheets with three.js; an empty card offers Open file…, the media library and the recent files; the library's «3D»
filter shows the files, which turn under the pointer; a click sends a file to the card that asked. Runs in Chromium and WebKit where
Playwright has them. The models are tiny ones the test writes itself, nothing is downloaded.

  HYIMG_REPO=<Hyimg checkout> python3 -m pytest tests/test_3d_files.py
"""
import base64, io, json, os, re, struct, time, urllib.error, urllib.request
from pathlib import Path

import pytest
from PIL import Image
from playwright.sync_api import sync_playwright

from test_canvas_3d import glb, hy as _hy, wait_file   # the fixture starts a temp server with this plugin mounted; the helpers write a glTF of boxes

hy = _hy
ENGINES = ["chromium", "webkit"]
GL = {"chromium": ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"], "webkit": []}


def gltf_text(glb_path):
    """a .gltf with its buffer inside as a data uri, made of a glb"""
    raw = Path(glb_path).read_bytes()
    jl, = struct.unpack("<I", raw[12:16]); doc = json.loads(raw[20:20 + jl]); bl, = struct.unpack("<I", raw[20 + jl:24 + jl]); blob = raw[28 + jl:28 + jl + bl]
    doc["buffers"] = [{"byteLength": len(blob), "uri": "data:application/octet-stream;base64," + base64.b64encode(blob).decode()}]
    return json.dumps(doc)


CUBE_OBJ = "o cube\nv -1 -1 -1\nv 1 -1 -1\nv 1 1 -1\nv -1 1 -1\nv -1 -1 1\nv 1 -1 1\nv 1 1 1\nv -1 1 1\nf 4 3 2 1\nf 5 6 7 8\nf 1 2 6 5\nf 2 3 7 6\nf 3 4 8 7\nf 4 1 5 8\n"
TETRA_STL = ("solid t\nfacet normal 0 0 -1\nouter loop\nvertex 0 0 0\nvertex 0 10 0\nvertex 10 0 0\nendloop\nendfacet\n"
             "facet normal 0 -1 0\nouter loop\nvertex 0 0 0\nvertex 10 0 0\nvertex 0 0 10\nendloop\nendfacet\n"
             "facet normal -1 0 0\nouter loop\nvertex 0 0 0\nvertex 0 0 10\nvertex 0 10 0\nendloop\nendfacet\n"
             "facet normal 1 1 1\nouter loop\nvertex 10 0 0\nvertex 0 10 0\nvertex 0 0 10\nendloop\nendfacet\nendsolid t\n")


@pytest.fixture
def files(hy):
    """the library's own 3D files, in folders of the library: models/ (glb, gltf, obj, stl), and a folder with a frame beside them"""
    port, lib = hy
    m = lib / "models"; m.mkdir()
    glb(m / "cube.glb", [("body", "grey", (0.1, 0.1, 0.1), (0, 0, 0))])
    # the tower leans to one side: its turn shows, a cube's would not
    glb(m / "tower.glb", [("base", "stone", (0.1, 0.04, 0.1), (0, 0, 0)), ("shaft", "stone", (0.03, 0.16, 0.03), (0.03, 0.1, 0)), ("flag", "red", (0.05, 0.03, 0.01), (0.07, 0.17, 0))])
    (m / "arch.gltf").write_text(gltf_text(m / "tower.glb"))
    (m / "crate.obj").write_text(CUBE_OBJ)
    (m / "tetra.stl").write_text(TETRA_STL)
    Image.new("RGB", (64, 64), (90, 20, 20)).save(lib / "models" / "frame.png")   # a picture: stays in the library's frames
    return port, lib


def get(port, path, body=None, headers=None):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=body, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=20) as r: return r.status, r.read(), r.headers
    except urllib.error.HTTPError as e: return e.code, e.read(), e.headers


def png_sheet(n=36, cols=6, cell=256):
    rows = -(-n // cols); im = Image.new("RGBA", (cols * cell, rows * cell), (0, 0, 0, 0))
    for i in range(n): im.paste((20 + 6 * i, 200 - 4 * i, 90, 255), ((i % cols) * cell + 40, (i // cols) * cell + 40, (i % cols) * cell + 200, (i // cols) * cell + 200))
    b = io.BytesIO(); im.save(b, "PNG"); return b.getvalue()


# ---- the server: the list, the turntable, the recent files

def test_the_library_lists_3d_files_apart_from_its_frames(files):
    port, lib = files
    items = json.loads(get(port, "/api/models3d")[1])
    paths = {i["path"]: i for i in items}
    assert {"models/cube.glb", "models/tower.glb", "models/arch.gltf", "models/crate.obj", "models/tetra.stl"} <= set(paths), sorted(paths)
    assert paths["models/crate.obj"]["ext"] == "OBJ" and paths["models/cube.glb"]["kind"] == "model" and paths["models/cube.glb"]["sprite"] is None
    # a project model is one entry (its model.json), not its part files
    assert "3d/models/test-model/model.json" in paths and not any("test-model/phone.glb" in p for p in paths), sorted(paths)
    assert paths["3d/models/test-model/model.json"]["model"] == "test-model" and paths["3d/models/test-model/model.json"]["ext"] == "MODEL"
    # the main list has them too, as files of their folders (owner 2026-10-07, test_step_library.py): kind "model", beside the pictures
    frames = {f["path"]: f for f in json.loads(get(port, "/api/items")[1])}
    assert "models/frame.png" in frames and "kind" not in frames["models/frame.png"] and {frames[p]["kind"] for p in paths} == {"model"} and set(paths) <= set(frames)
    # a file the plugin keeps for a scene (scene.glb) is not a file of the person's
    (lib / "3d/scenes/x").mkdir(parents=True); glb(lib / "3d/scenes/x/scene.glb", [("a", "m", (0.1, 0.1, 0.1), (0, 0, 0))])
    assert "3d/scenes/x/scene.glb" not in {i["path"] for i in json.loads(get(port, "/api/models3d?fresh=1")[1])}


def test_a_turntable_is_kept_per_version_of_the_file(files):
    port, lib = files
    assert get(port, "/api/sprite?p=models/cube.glb")[0] == 404
    code, body, _ = get(port, "/api/sprite?p=models/cube.glb&n=36&cols=6&cell=256", png_sheet(), {"Content-Type": "image/png"}); assert code == 200, body
    meta = json.loads(body); assert meta["n"] == 36 and meta["cols"] == 6 and meta["cell"] == 256 and meta["bytes"] < 60000, meta
    code, sheet, headers = get(port, "/api/sprite?p=models/cube.glb"); assert code == 200 and headers["Content-Type"] == "image/webp"
    im = Image.open(io.BytesIO(sheet)); assert im.size == (1536, 1536) and im.mode == "RGBA"
    assert im.getpixel((100, 100))[3] == 255 and im.getpixel((5, 5))[3] == 0, "the sheet keeps its see-through background"
    code, still, _ = get(port, "/api/sprite?p=models/cube.glb&s=240"); assert code == 200 and Image.open(io.BytesIO(still)).size == (240, 240)
    assert get(port, "/api/sprite?p=models/cube.glb&s=7")[0] == 400
    item = next(i for i in json.loads(get(port, "/api/models3d")[1]) if i["path"] == "models/cube.glb")
    assert item["sprite"]["n"] == 36 and item["sprite"]["v"] == item["ver"]
    # a changed file has no turntable until it is drawn again, and the old sheet goes
    time.sleep(1.1); (lib / "models/cube.glb").write_bytes((lib / "models/cube.glb").read_bytes() + b"\0\0\0\0")
    assert get(port, "/api/sprite?p=models/cube.glb")[0] == 404
    assert get(port, "/api/sprite?p=models/cube.glb&n=36&cols=6&cell=256", png_sheet(), {"Content-Type": "image/png"})[0] == 200
    pid = json.loads(get(port, "/api/health")[1])["projectId"]   # turntables are in the app's cache, not the state folder (2026-10-07)
    thumbs = Path(os.environ["HYIMG_CACHE_ROOT"]) / pid / "thumbs"
    assert len([n for n in thumbs.iterdir() if "cube.glb" in n.name and n.name.endswith(".webp")]) == 1
    # what is not a sheet of those numbers, or not a 3D file of the library, is refused
    assert get(port, "/api/sprite?p=models/cube.glb&n=36&cols=6&cell=128", png_sheet(), {"Content-Type": "image/png"})[0] == 400
    assert get(port, "/api/sprite?p=models/frame.png&n=36&cols=6&cell=256", png_sheet(), {"Content-Type": "image/png"})[0] == 400
    assert get(port, "/api/sprite?p=../x.glb&n=36&cols=6&cell=256", png_sheet(), {"Content-Type": "image/png"})[0] in (400, 403)
    assert get(port, "/api/sprite?p=models/cube.glb&n=36&cols=6&cell=256", b"not a png", {"Content-Type": "image/png"})[0] == 400


def test_recent_files_newest_first_eight_at_most(files):
    port, lib = files
    recent = lambda **b: json.loads(get(port, "/api/plugin/3d/recent", json.dumps(b).encode())[1])["recent"]
    assert recent() == []
    for p in ("a.glb", "b.glb", "c.glb"): recent(add=f"models/{p}")
    assert recent() == ["models/c.glb", "models/b.glb", "models/a.glb"]
    assert recent(add="models/a.glb") == ["models/a.glb", "models/c.glb", "models/b.glb"], "a file used again goes to the top"
    for i in range(10): recent(add=f"models/n{i}.glb")
    got = recent(); assert len(got) == 8 and got[0] == "models/n9.glb" and got[-1] == "models/n2.glb"
    assert recent(remove="models/n5.glb").count("models/n5.glb") == 0
    assert recent(add="../outside.glb") == recent() and recent(add="/etc/passwd") == recent(), "only paths of the library"
    # kept per project: in its state folder
    assert json.loads((lib.parent / "state/3d-recent.json").read_text())["recent"][0] == "models/n9.glb"
    info = json.loads(get(port, "/api/models3d", json.dumps({"paths": ["models/cube.glb", "models/gone.glb", "../x.glb"]}).encode())[1])
    assert info[0]["path"] == "models/cube.glb" and info[1] is None and info[2] is None, info


# ---- the browser

def open_board(p, engine, port):
    """the library and the canvas as the app shows them (the canvas in its frame): the board's frame, and the page"""
    try: browser = getattr(p, engine).launch(args=GL[engine])
    except Exception as error: pytest.skip(f"no {engine} for Playwright: {error}")
    page = browser.new_page(viewport={"width": 1500, "height": 950})
    errors = []; page.on("pageerror", lambda e: errors.append(f"{e} {(e.stack or '')[:400]}"))
    page.goto(f"http://127.0.0.1:{port}/")
    page.evaluate("() => localStorage.setItem('view', 'canvas')"); page.reload()
    page.wait_for_function("() => document.body.classList.contains('cv-on')")
    frame = None
    for _ in range(200):   # WebKit lists the canvas frame a moment after the page is up
        frame = next((f for f in page.frames if "/canvas" in f.url), None)
        if frame: break
        page.wait_for_timeout(100)
    assert frame, "the canvas frame"
    frame.wait_for_function("() => typeof PLGST !== 'undefined' && PLGST.some(p => p.name === '3d' && p.ok)", timeout=30000)
    return browser, page, frame, errors


def open_3d(page):
    """the library's 3D mode, as the empty card's «Media library» asks for it (a message to the library page): the library's filter window is the
    app's own, reworked by its owner's other sessions, and its «3D» chip is not what these tests are about"""
    page.evaluate("() => postMessage({ type: 'open3d', card: null }, location.origin)")
    page.wait_for_function("() => document.body.classList.contains('m3dmode')", timeout=15000)


def filter_off(page):
    page.evaluate("() => { vfilter = ''; render(); }")
    page.wait_for_function("() => !document.body.classList.contains('m3dmode')", timeout=15000)


def library_closed(page):
    """an empty board opens its library by itself a moment after load (2026-10-06): wait for that, then close it, so a test starts with the library closed"""
    page.wait_for_timeout(1800)
    if page.evaluate("() => !document.body.classList.contains('cv-only')"):
        page.keyboard.press("Control+m"); page.wait_for_function("() => document.body.classList.contains('cv-only')", timeout=5000); page.wait_for_timeout(900)


def new_card(frame):
    frame.click("button[title^='3D scene']")
    frame.wait_for_selector(".plg[data-type=model3d] .e3 .e3-b", timeout=30000)
    return frame.evaluate("() => Object.keys(board.items).find(k => board.items[k].type === 'model3d' && board.items[k].empty)")


def scene_of(lib, frame, cid):
    return lib / frame.evaluate(f"() => board.items[{json.dumps(cid)}].scene")


@pytest.mark.parametrize("hy", ["en"], indirect=True)
@pytest.mark.parametrize("engine", ENGINES)
def test_a_new_card_asks_for_a_file_and_a_chosen_file_takes_the_stand_ins_place(files, engine, tmp_path):
    port, lib = files
    with sync_playwright() as p:
        browser, page, frame, errors = open_board(p, engine, port)
        cid = new_card(frame)
        scene = scene_of(lib, frame, cid)
        doc = wait_file(scene, lambda d: len(d["objects"]) == 2 and d["objects"][0]["src"]["type"] == "prim")
        light, cam = doc["lights"], doc["cameras"]
        # the card's own frame offers the two ways, in the app's words
        assert frame.locator(".e3 .e3-b").all_inner_texts() == ["Open file…", "Media library"]
        assert frame.locator(".e3 .e3-rc").is_hidden(), "no recent files yet: no list"
        assert not re.search("[А-Яа-яЁё]", frame.locator(".e3").inner_text()), "English by default"
        # a 3D file chosen in the system's panel (outside the library): written into the project, the stand-in is replaced, light and camera stay
        mine = tmp_path / "my vase.glb"; glb(mine, [("foot", "clay", (0.06, 0.02, 0.06), (0, 0, 0)), ("neck", "clay", (0.03, 0.12, 0.03), (0, 0.07, 0))])
        with page.expect_file_chooser() as fc:
            frame.click(".e3 .e3-b[data-a=file]")
        assert fc.value.is_multiple() and ".glb" in (fc.value.element.get_attribute("accept") or "")
        fc.value.set_files(str(mine))
        doc = wait_file(scene, lambda d: any(o["src"]["type"] == "file" for o in d["objects"]), t=30)
        obj = next(o for o in doc["objects"] if o["src"]["type"] == "file")
        assert len(doc["objects"]) == 2 and not any(o["src"]["type"] == "prim" and o["name"] != "Floor" for o in doc["objects"]), "the stand-in shape is gone"
        assert obj["src"]["path"].startswith("3d/files/") and obj["src"]["path"].endswith("/my_vase.glb") and (lib / obj["src"]["path"]).read_bytes() == mine.read_bytes()
        assert obj["name"] == "my vase" and obj["ai"] == "the main object of the shot" and abs(obj["scale"][0] - 1) < 1e-6, "a vase of 14 cm keeps its size"
        assert doc["lights"] == light and doc["cameras"] == cam, "the scene's light and camera stay"
        # its foot (1 cm under the file's own origin) is on the floor, its middle on the floor's centre
        assert abs(obj["loc"][2] - 0.0105) < 1e-4 and abs(obj["loc"][0]) < 1e-3 and abs(obj["loc"][1]) < 1e-3, obj["loc"]
        frame.wait_for_function(f"() => !board.items[{json.dumps(cid)}].empty && !document.querySelector('.plg[data-id={cid}] .e3')", timeout=10000)
        # the file is the first of the recent ones
        assert json.loads((lib.parent / "state/3d-recent.json").read_text())["recent"] == [obj["src"]["path"]]
        # the card shows the scene with the file in it: its still is drawn again and written beside the scene
        for _ in range(600):
            if any(f.stat().st_size > 2000 for f in (scene.parent / ".posters").glob("*")): break
            time.sleep(0.1)
        assert any(f.stat().st_size > 2000 for f in (scene.parent / ".posters").glob("*")), "the card's still"
        frame.wait_for_function(f"() => {{ const i = document.querySelector('.plg[data-id={cid}] img.m3'); return i && i.complete && i.naturalWidth > 0 }}", timeout=60000)
        # a file of another format becomes a glb in the project (the scene holds glb files; Blender reads them)
        cid2 = new_card(frame); scene2 = scene_of(lib, frame, cid2)
        crate = tmp_path / "crate.obj"; crate.write_text(CUBE_OBJ)
        with page.expect_file_chooser() as fc:
            frame.click(f".plg[data-id={cid2}] .e3-b[data-a=file]")
        fc.value.set_files(str(crate))
        doc2 = wait_file(scene2, lambda d: any(o["src"]["type"] == "file" for o in d["objects"]), t=30)
        o2 = next(o for o in doc2["objects"] if o["src"]["type"] == "file")
        assert o2["src"]["path"].endswith("/crate.glb") and (lib / o2["src"]["path"]).read_bytes()[:4] == b"glTF"
        assert abs(o2["scale"][0] - 0.1) < 1e-6, "a cube 2 units wide is fitted to 20 cm"   # 2 units -> 0.2 m: scale 0.1
        # a file that is not 3D is refused with a word, the card still asks
        cid3 = new_card(frame)
        junk = tmp_path / "notes.txt"; junk.write_text("not a model")
        with page.expect_file_chooser() as fc:
            frame.click(f".plg[data-id={cid3}] .e3-b[data-a=file]")
        fc.value.set_files(str(junk))
        page.wait_for_timeout(800)
        assert frame.evaluate(f"() => board.items[{json.dumps(cid3)}].empty") is True
        assert not errors, errors
        browser.close()


def open_library(p, engine, port):
    """the library beside the canvas (the canvas frame is there too)"""
    try: browser = getattr(p, engine).launch(args=GL[engine])
    except Exception as error: pytest.skip(f"no {engine} for Playwright: {error}")
    page = browser.new_page(viewport={"width": 1500, "height": 950})
    errors = []; page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(f"http://127.0.0.1:{port}/?view=panel")
    page.wait_for_function("() => document.body.classList.contains('cv-on') && !document.body.classList.contains('cv-only')")
    return browser, page, errors


def frame_of(sheet_bytes, k, cols=6, cell=256):
    im = Image.open(io.BytesIO(sheet_bytes)).convert("RGBA")
    return im.crop(((k % cols) * cell, (k // cols) * cell, (k % cols + 1) * cell, (k // cols + 1) * cell))


def watch_views(target, selector):
    """records, inside the page, every view the tile shows from now on (a MutationObserver on its data-view), so the count does not depend on how fast the
    test looks, each with its time, and when the turn started (the class spinning: the sheet is up and its clock starts, Hyimg ui/spin.js)"""
    target.evaluate("""sel => { const s = document.querySelector(sel); window.__views = new Set([+s.dataset.view || 0]); window.__t = []; window.__tv = []; window.__on = null;
        new MutationObserver(() => { const now = performance.now(), v = +s.dataset.view || 0;
          if (window.__on === null && s.classList.contains('spinning')) window.__on = now;
          window.__views.add(v); window.__t.push(now); if (window.__on !== null) window.__tv.push([now - window.__on, v]); })
          .observe(s, { attributes: true, attributeFilter: ['data-view', 'class'] }); }""", selector)


def views_seen(target):
    return target.evaluate("""() => ({ views: [...window.__views].sort((a, b) => a - b), steps: window.__t.length, span: window.__t.length > 1 ? window.__t[window.__t.length - 1] - window.__t[0] : 0,
      tv: window.__tv })""")


TURN, VIEWS = 3000, 36   # Hyimg ui/spin.js: a turn in 3 s, 36 views on a sheet


def assert_turns_with_its_clock(seen):
    """the views step round by the sheet's clock, a turn of 36 in 3 s, and the whole way round: each view shown is the one the clock says at
    that moment (within one view). How many of the 36 a page shows depends on its frame rate (software GL on a busy machine drew 8 to 12 a
    second where 12 are due, 2026-10-07: 27 to 34 views in 3.4 s, at HEAD and before the ghost and the light commits alike); the clock
    skips a late frame's views instead of slowing the turn, and that is what is checked here, not a count of frames"""
    tv = seen["tv"]; per = TURN / VIEWS
    assert len(tv) >= 18 and len(seen["views"]) >= 18, ("the views step, not jump", seen)
    off = [(t, v, int(t // per) % VIEWS) for t, v in tv if min(abs(v - int(t // per) % VIEWS), VIEWS - abs(v - int(t // per) % VIEWS)) > 1]
    assert not off, ("a view the clock did not say (ms since the turn began, the view, the clock's)", off[:6], seen)
    assert any(t >= TURN and v < VIEWS // 2 for t, v in tv) and max(v for _, v in tv) >= VIEWS - 4, ("the whole way round in 3 s", seen)


def view_now(page):
    return page.evaluate("() => { const c = document.querySelector('.card.m3d'); const s = c.querySelector('.m3s'); return {view: +s.dataset.view || 0, on: s.classList.contains('spinning'), pos: s.style.backgroundPosition, img: s.style.backgroundImage}; }")


@pytest.mark.parametrize("hy", ["en"], indirect=True)
@pytest.mark.parametrize("engine", ENGINES)
def test_the_3d_filter_lists_files_and_each_turns_under_the_pointer(files, engine):
    port, lib = files
    with sync_playwright() as p:
        browser, page, errors = open_library(p, engine, port)
        open_3d(page)
        page.wait_for_selector(".card.m3d")
        tiles = page.locator(".card.m3d")
        names = sorted(tiles.evaluate_all("els => els.map(e => e.getAttribute('aria-label'))"))
        assert names == sorted(["cube", "tower", "arch", "crate", "tetra", "Тестовая модель", "Ваза"]) and page.locator("#list .card:not(.m3d)").count() == 0, names   # no frame among them
        assert page.evaluate("() => document.body.classList.contains('m3dmode')") and page.locator(".card.m3d").count() == 7
        assert sorted(page.locator(".card.m3d .pill.kd").evaluate_all("els => els.map(e => e.textContent)")) == sorted(["GLB", "GLB", "GLTF", "OBJ", "STL", "MODEL", "MODEL"])
        # a turntable is drawn for each, once, by the plugin's module (three.js: a file in each of its formats)
        t0 = time.time()
        page.wait_for_function("() => document.querySelectorAll('.card.m3d').length === 7 && document.querySelectorAll('.card.m3d.nosp').length === 0", timeout=180000)
        drawn = time.time() - t0
        items = json.loads(get(port, "/api/models3d")[1]); assert all(i["sprite"] for i in items), [i["path"] for i in items if not i["sprite"]]
        # the sheet really turns: the tower seen from the other side is another picture, and each view has the object in it, not an empty frame
        sheet = get(port, "/api/sprite?p=models/tower.glb")[1]
        a, b = frame_of(sheet, 0), frame_of(sheet, 18)
        cover = lambda im: sum(1 for px in im.getdata() if px[3] > 128) / (256 * 256)
        assert 0.04 < cover(a) < 0.8 and 0.04 < cover(b) < 0.8, (cover(a), cover(b))
        from PIL import ImageChops
        diff = ImageChops.difference(a, b).convert("L"); assert sum(diff.getdata()) / (256 * 256) > 3, "the view from the other side differs"
        # at rest a tile shows the still picture; under the pointer its views step round, 36 of them in 3 s, and the turn is on
        card = page.locator(".card.m3d").first
        assert "&s=320" in view_now(page)["img"] and not view_now(page)["on"] and view_now(page)["view"] == 0
        watch_views(page, ".card.m3d .m3s")
        box = card.bounding_box(); page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.wait_for_timeout(3400)
        seen = views_seen(page)
        assert view_now(page)["on"] and "&s=" not in view_now(page)["img"], "the sheet is shown while it turns"
        assert_turns_with_its_clock(seen)   # 36 views in a turn of 3 s, by the clock; a slow frame skips some
        # off the tile it settles on the rest view and shows the still picture again
        page.mouse.move(box["x"] + box["width"] + 400, box["y"] + 100)
        page.wait_for_function("() => { const s = document.querySelector('.card.m3d .m3s'); return !s.classList.contains('spinning') && (+s.dataset.view || 0) === 0 }", timeout=3000)
        assert "&s=320" in view_now(page)["img"] and view_now(page)["pos"] in ("", "0% 0%")
        print(f"\n{engine}: {len(items)} turntables drawn in {drawn:.1f} s, sheet of the tower {len(sheet) / 1024:.0f} KB")
        assert not errors, errors
        browser.close()


@pytest.mark.parametrize("hy", ["en"], indirect=True)
def test_the_filter_follows_search_and_folders_and_goes_off(files):
    port, lib = files
    with sync_playwright() as p:
        browser, page, errors = open_library(p, "chromium", port)
        open_3d(page); page.wait_for_selector(".card.m3d")
        page.fill("#q", "cu"); page.wait_for_function("() => document.querySelectorAll('.card.m3d').length === 1")
        assert page.locator(".card.m3d").get_attribute("aria-label") == "cube"
        page.fill("#q", "")
        page.click(".frow[data-f=models]") if page.locator(".frow[data-f=models]").count() else page.evaluate("() => chooseFolder('models')")
        page.wait_for_function("() => document.querySelectorAll('.card.m3d').length === 5")   # the folder's own: the two project models are in 3d/
        # off again: the folder as it is, its picture and its 3D files (owner 2026-10-07: 3D files are files of their folders, test_step_library.py)
        filter_off(page)
        page.wait_for_function("() => !document.body.classList.contains('m3dmode') && document.querySelectorAll('#list .card:not(.m3d)').length === 1")
        assert page.locator("#list .card:not(.m3d)").get_attribute("aria-label") == "frame" and page.locator("#list .card.m3d").count() == 5
        browser.close()


def card_doc(lib, frame, cid, cond):
    return wait_file(scene_of(lib, frame, cid), cond, t=60)


def objects_of_files(doc): return [o for o in doc["objects"] if o["src"]["type"] == "file"]


@pytest.mark.parametrize("hy", ["en"], indirect=True)
@pytest.mark.parametrize("engine", ENGINES)
def test_the_media_library_button_opens_the_3d_filter_and_a_click_sends_the_file_to_the_card(files, engine):
    port, lib = files
    with sync_playwright() as p:
        browser, page, frame, errors = open_board(p, engine, port)
        library_closed(page); assert page.evaluate("() => document.body.classList.contains('cv-only')"), "the library starts closed"
        cid = new_card(frame)
        light = card_doc(lib, frame, cid, lambda d: len(d["objects"]) == 2)["lights"]
        frame.click(f".plg[data-id={cid}] .e3-b[data-a=lib]")
        # the library comes in beside the canvas, the 3D filter on, everything else out of the way
        page.wait_for_function("() => document.body.classList.contains('cv-on') && !document.body.classList.contains('cv-only') && document.querySelectorAll('.card.m3d').length === 7", timeout=15000)
        assert page.evaluate("() => document.body.classList.contains('m3dmode')") and page.input_value("#q") == ""
        # a click on a file: it goes into the card that asked, the library goes back and the filter off
        page.click(".card.m3d[aria-label=tower]")
        doc = card_doc(lib, frame, cid, lambda d: len(objects_of_files(d)) == 1)
        o = objects_of_files(doc)[0]
        assert o["src"]["path"] == "models/tower.glb" and o["name"] == "tower" and doc["lights"] == light and len(doc["objects"]) == 2, o
        page.wait_for_function("() => document.body.classList.contains('cv-only') && !document.body.classList.contains('m3dmode')", timeout=15000)
        frame.wait_for_function(f"() => !board.items[{json.dumps(cid)}].empty && !document.querySelector('.plg[data-id={cid}] .e3')", timeout=10000)
        assert json.loads((lib.parent / "state/3d-recent.json").read_text())["recent"] == ["models/tower.glb"]
        # the filter used by hand, no card asking: a click puts the file on the canvas as a new 3D card
        page.click("#tlibR"); page.wait_for_function("() => !document.body.classList.contains('cv-only')")
        open_3d(page); page.wait_for_selector(".card.m3d[aria-label=cube]")
        page.click(".card.m3d[aria-label=cube]")
        frame.wait_for_function("() => Object.values(board.items).filter(i => i.type === 'model3d').length === 2", timeout=20000)
        cid2 = frame.evaluate(f"() => Object.keys(board.items).find(k => board.items[k].type === 'model3d' && k !== {json.dumps(cid)})")
        doc2 = card_doc(lib, frame, cid2, lambda d: len(objects_of_files(d)) == 1)
        assert objects_of_files(doc2)[0]["src"]["path"] == "models/cube.glb" and not frame.evaluate(f"() => !!board.items[{json.dumps(cid2)}].empty")
        assert json.loads((lib.parent / "state/3d-recent.json").read_text())["recent"] == ["models/cube.glb", "models/tower.glb"]
        assert not errors, errors
        browser.close()


@pytest.mark.parametrize("hy", ["en"], indirect=True)
@pytest.mark.parametrize("engine", ENGINES)
def test_the_recent_files_of_an_empty_card_turn_under_the_pointer_and_go_into_the_card(files, engine):
    port, lib = files
    recent = lambda **b: json.loads(get(port, "/api/plugin/3d/recent", json.dumps(b).encode())[1])["recent"]
    for n in ("crate.obj", "cube.glb", "tower.glb"): recent(add=f"models/{n}")
    recent(add="models/gone.glb")   # a file that has gone since
    # turntables of the first two exist; the third is drawn by the card itself (a made-up sheet is enough for the tiles)
    for n in ("crate.obj", "cube.glb"):
        assert get(port, f"/api/sprite?p=models/{n}&n=36&cols=6&cell=256", png_sheet(), {"Content-Type": "image/png"})[0] == 200
    with sync_playwright() as p:
        browser, page, frame, errors = open_board(p, engine, port)
        cid = new_card(frame)
        frame.wait_for_function(f"() => document.querySelectorAll('.plg[data-id={cid}] .e3-t').length === 3", timeout=20000)
        order = lambda: frame.evaluate(f"() => [...document.querySelectorAll('.plg[data-id={cid}] .e3-t')].map(t => t.dataset.path)")
        assert order() == ["models/tower.glb", "models/cube.glb", "models/crate.obj"], "newest first, the gone file left out"
        assert "models/gone.glb" not in recent(), "and forgotten"
        assert frame.locator(".e3 .e3-rc").is_visible()
        # the tower has no turntable yet: the card draws it (three.js, one file) and the tile turns into its picture
        frame.wait_for_function(f"() => document.querySelectorAll('.plg[data-id={cid}] .e3-t [data-spin]').length === 3", timeout=120000)
        assert get(port, "/api/sprite?p=models/tower.glb")[0] == 200
        # under the pointer a tile's views step round and it settles on its rest view when the pointer leaves
        tile = frame.locator(f".plg[data-id={cid}] .e3-t").nth(1); box = tile.bounding_box()
        view = lambda: frame.evaluate(f"() => {{ const s = document.querySelectorAll('.plg[data-id={cid}] .e3-t .e3-s')[1]; return {{v: +s.dataset.view || 0, on: s.classList.contains('spinning')}}; }}")
        assert view() == {"v": 0, "on": False}
        watch_views(frame, f".plg[data-id={cid}] .e3-t:nth-child(2) .e3-s")
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 3)
        page.wait_for_timeout(3400)
        seen = views_seen(frame)
        assert view()["on"], seen
        assert_turns_with_its_clock(seen)
        page.mouse.move(box["x"] - 300, box["y"] - 100)
        frame.wait_for_function(f"() => {{ const s = document.querySelectorAll('.plg[data-id={cid}] .e3-t .e3-s')[1]; return !s.classList.contains('spinning') && (+s.dataset.view || 0) === 0; }}", timeout=3000)
        # a click on a recent file (an obj: its glb is made once) puts it into the card, and the file is the newest of the recent ones
        frame.click(f".plg[data-id={cid}] .e3-t[data-path='models/crate.obj']")
        doc = card_doc(lib, frame, cid, lambda d: len(objects_of_files(d)) == 1)
        src = objects_of_files(doc)[0]["src"]["path"]
        assert src.startswith("3d/converted/") and src.endswith("/crate.glb") and (lib / src).read_bytes()[:4] == b"glTF" and objects_of_files(doc)[0]["name"] == "crate", src
        assert recent()[:3] == ["models/crate.obj", "models/tower.glb", "models/cube.glb"], "the original file is what the list remembers, not its copy"
        # the next empty card shows the new order
        cid2 = new_card(frame)
        frame.wait_for_function(f"() => [...document.querySelectorAll('.plg[data-id={cid2}] .e3-t')].map(t => t.dataset.path).join() === 'models/crate.obj,models/tower.glb,models/cube.glb'", timeout=20000)
        assert not errors, errors
        browser.close()


@pytest.mark.parametrize("hy", ["en"], indirect=True)
def test_the_card_outside_the_app_has_no_library_button_and_the_words_follow_the_language(files, tmp_path):
    """the canvas on its own page has no library beside it: its card offers the file and the recent files only; in Russian the same words are Russian"""
    port, lib = files
    with sync_playwright() as p:
        browser = p.chromium.launch(args=GL["chromium"]); page = browser.new_page(viewport={"width": 1200, "height": 800})
        page.goto(f"http://127.0.0.1:{port}/canvas.html")
        page.wait_for_function("() => typeof PLGST !== 'undefined' && PLGST.some(p => p.name === '3d' && p.ok)", timeout=30000)
        page.click("button[title^='3D scene']"); page.wait_for_selector(".e3 .e3-b", timeout=30000)
        assert page.locator(".e3 .e3-b").all_inner_texts() == ["Open file…"]
        browser.close()


@pytest.mark.parametrize("hy", ["ru"], indirect=True)
def test_an_empty_card_speaks_russian_when_the_app_does(files):
    port, lib = files
    with sync_playwright() as p:
        browser, page, frame, errors = open_board(p, "chromium", port)
        frame.click("button[title^='3D-сцена']"); frame.wait_for_selector(".e3 .e3-b", timeout=30000)
        assert frame.locator(".e3 .e3-b").all_inner_texts() == ["Открыть файл…", "Медиатека"]
        assert "3D-файл" in frame.locator(".e3 .e3-fm").inner_text()
        assert not errors, errors
        browser.close()
