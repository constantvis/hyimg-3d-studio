"""The 3D plugin in a real canvas (Chromium): a new scene card, the editor and its panels, a shape added and resized, the camera turned,
the snapshot with masks and depth, an agent's change of the scene file showing on the card, cards from inbox.json, a heavy scene
waiting for a yes. The model is a tiny one the test writes itself (a phone and its case as plain boxes), no real model is needed.

  HYIMG_REPO=<Hyimg checkout> python3 -m pytest tests/test_canvas_3d.py
"""
import json
import math, os, socket, struct, subprocess, sys, time, urllib.request, uuid
from pathlib import Path

import pytest
from playwright.sync_api import Page, sync_playwright

HERE = Path(__file__).resolve().parent.parent
REPO = Path(os.environ.get("HYIMG_REPO", HERE.parent / "hyimg"))   # the repositories sit side by side in one folder (2026-10-04)
SHOTS = os.environ.get("HYIMG_SHOTS")   # a folder for screenshots to look at
# a new card asks for a file in its middle (2026-10-06): a double click that opens the editor lands near its corner, clear of the selected
# card's 30 px corner square (it reaches 15 px into the card, shown from 62 px wide since the owner's lab, 2026-10-06)
CORNER = {"x": 22, "y": 22}
MODEL, TITLE, AI = "test-model", "Тестовая модель", "тестовая модель, форму не менять"


def glb(path, meshes):
    """a glTF binary of boxes: meshes = [(node name, material name, (x, y, z) size, (x, y, z) translation)], y up as glTF has it"""
    faces = [((1, 0, 0), (2, 1)), ((-1, 0, 0), (1, 2)), ((0, 1, 0), (0, 2)), ((0, -1, 0), (2, 0)), ((0, 0, 1), (0, 1)), ((0, 0, -1), (1, 0))]
    blob, views, accs, gl_meshes, nodes, mats = b"", [], [], [], [], []
    for name, mat, size, at in meshes:
        pos, nrm, idx = [], [], []
        for n, (a, b) in faces:
            ax = [i for i in range(3) if n[i]][0]
            for u, v in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                pt = [0.0, 0.0, 0.0]; pt[ax] = n[ax] * size[ax] / 2; pt[a] = u * size[a] / 2; pt[b] = v * size[b] / 2
                pos.append(pt); nrm.append([float(x) for x in n])
            k = len(pos) - 4; idx += [k, k + 1, k + 2, k, k + 2, k + 3]
        acc0 = len(accs)
        for data, fmt, kind, target in ((pos, "3f", "VEC3", 34962), (nrm, "3f", "VEC3", 34962), (idx, "H", "SCALAR", 34963)):
            raw = b"".join(struct.pack("<" + fmt, *(x if isinstance(x, list) else [x])) for x in data); raw += b"\0" * (-len(raw) % 4)
            views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(raw), "target": target}); blob += raw
            acc = {"bufferView": len(views) - 1, "componentType": 5123 if fmt == "H" else 5126, "count": len(data), "type": kind}
            if data is pos: acc.update(min=[-x / 2 for x in size], max=[x / 2 for x in size])
            accs.append(acc)
        mats.append({"name": mat, "pbrMetallicRoughness": {"baseColorFactor": [0.6, 0.6, 0.6, 1]}})
        gl_meshes.append({"name": name, "primitives": [{"attributes": {"POSITION": acc0, "NORMAL": acc0 + 1}, "indices": acc0 + 2, "material": len(mats) - 1}]})
        nodes.append({"name": name, "mesh": len(gl_meshes) - 1, "translation": list(at)})
    doc = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [len(nodes)]}], "nodes": nodes + [{"name": Path(path).stem, "children": list(range(len(nodes)))}],
           "meshes": gl_meshes, "materials": mats, "accessors": accs, "bufferViews": views, "buffers": [{"byteLength": len(blob)}]}
    js = json.dumps(doc).encode(); js += b" " * (-len(js) % 4)
    Path(path).write_bytes(struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(blob)) + struct.pack("<II", len(js), 0x4E4F534A) + js
                           + struct.pack("<II", len(blob), 0x004E4942) + blob)


def tiny_model(lib):
    """3d/models/test-model: a phone and the two halves of its case (metal and resin) as boxes, put together the way a phone model is"""
    d = lib / "3d/models" / MODEL; d.mkdir(parents=True)
    glb(d / "phone.glb", [("body", "glass", (0.775, 1.634, 0.083), (0, 0, 0)), ("camera", "lens", (0.3, 0.3, 0.03), (0.15, 0.6, -0.05))])
    glb(d / "case-metal.glb", [("frame", "frame metal", (0.42, 1.70, 0.12), (0.21, 0, 0)), ("inlay", "resin", (0.38, 1.6, 0.02), (0.19, 0, -0.07))])
    glb(d / "case-resin.glb", [("back", "resin", (0.40, 1.62, 0.03), (0.2, 0, -0.06)), ("rim", "frame metal", (0.42, 1.70, 0.02), (0.21, 0, 0.05))])
    (d / "model.json").write_text(json.dumps({"title": TITLE, "ai": AI, "height": 3.38, "clearance": 0.025, "height_m": 0.1634, "parts": [
        {"role": "phone", "file": "phone.glb", "rotate_y": 180}, {"role": "case", "file": "case-metal.glb", "keep": "metal", "mirror": True},
        {"role": "case", "file": "case-resin.glb", "keep": "resin", "mirror": True}]}, ensure_ascii=False))
    # a model that is not a phone: its parts stay where its file puts them, 25 cm tall, no "height" in its own units
    v = lib / "3d/models/vase"; v.mkdir(parents=True)
    glb(v / "vase.glb", [("foot", "clay", (0.5, 0.2, 0.5), (0, -0.4, 0)), ("neck", "clay", (0.3, 0.6, 0.3), (0, 0, 0))])
    (v / "model.json").write_text(json.dumps({"title": "Ваза", "height_m": 0.25, "parts": [{"role": "body", "file": "vase.glb"}]}, ensure_ascii=False))


def model_in_the_middle(page, scene):
    """as an agent would do it: the project's model takes the place of the new scene's stand-in shape, the card follows the file"""
    doc = wait_file(scene, lambda d: len(d["objects"]) == 2)
    page.wait_for_function("() => { const i = document.querySelector('.plg[data-type=model3d] img.m3'); return i && i.src.startsWith('data:image') }", timeout=30000)
    src0 = page.evaluate("() => document.querySelector('.plg[data-type=model3d] img.m3').src")
    first = doc["objects"][0]
    doc["objects"][0] = {"id": first["id"], "name": TITLE, "src": {"type": "model", "model": MODEL}, "loc": [0, 0, 0.1634 / 2 + 0.0005], "rot": [1, 0, 0, 0], "scale": [1, 1, 1], "ai": AI}
    doc["rev"] += 1; doc["by"] = "blender"; scene.write_text(json.dumps(doc, ensure_ascii=False))
    page.wait_for_function(f"() => document.querySelector('.plg[data-type=model3d] img.m3').src !== {json.dumps(src0)}", timeout=30000)
    return doc


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


@pytest.fixture
def hy(tmp_path, request):
    lib, state, plugins = tmp_path / "lib", tmp_path / "state", tmp_path / "plugins"
    tiny_model(lib)
    (state / "boards").mkdir(parents=True); plugins.mkdir()
    # the interface's language (owner 2026-10-06: «make 2 versions, Russian and English»): the app's setting cv.lang in its settings file;
    # these tests read the Russian words, an English test asks for "en" (indirect parametrize), which is the app's default
    (state / "app-settings.json").write_text(json.dumps({"cv.lang": "ru"} if getattr(request, "param", "ru") == "ru" else {}))
    (state / "boards/main.json").write_text(json.dumps({"items": {}, "groups": {}, "revision": 1}))
    (plugins / "3d").symlink_to(HERE)
    port = free_port()
    env = {k: v for k, v in os.environ.items() if not k.startswith(("HYIMG_", "REVIEW_"))}
    env.update(HYIMG_LIBRARY_ROOT=str(lib), HYIMG_STATE_ROOT=str(state), HYIMG_PROJECT_ID=str(uuid.uuid4()), HYIMG_PLUGINS=str(plugins), HYIMG_SETTINGS=str(state / "app-settings.json"), PYTHONDONTWRITEBYTECODE="1")
    log = open(tmp_path / "server.log", "w+")
    proc = subprocess.Popen([sys.executable, str(REPO / "review/server.py"), str(port)], env=env, stdout=log, stderr=log)
    for _ in range(100):
        try: urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1); break
        except OSError: time.sleep(0.1)
    yield port, lib
    proc.terminate(); proc.wait(5); log.close()


def shot(page, name):
    if SHOTS: page.screenshot(path=os.path.join(SHOTS, name + ".png"))


def go_on(page):
    if page.locator(".m3pause [data-go]").count(): page.click(".m3pause [data-go]")


# The studio writes scene.json on «Save» only (owner 2026-10-07): while a page has it open, a scene's state is the studio's own, in
# memory. wait_file reads that one for the scene the open studio edits (every page these tests open is tracked), else the file
PAGES = []
_goto = Page.goto
def _tracked(self, *a, **k): PAGES.append(self); return _goto(self, *a, **k)   # noqa: E302
Page.goto = _tracked
LIVE = "p => document.querySelector('.plg-live') ? import('/plugins/3d/engine.js').then(m => m.livePath() === p ? m.docOf(p) : null).catch(() => null) : null"


def live_doc(path):
    rel = str(path).split("/lib/", 1)[-1]
    for pg in reversed(PAGES):
        try:
            if pg.is_closed(): continue
            for fr in pg.frames:
                d = fr.evaluate(LIVE, rel)
                if d: return d
        except Exception: pass
    return None


def scene_now(p):   # the open studio's scene, else the file
    return live_doc(p) or json.loads(p.read_text())


def wait_file(p, cond=lambda d: True, t=8):
    for _ in range(int(t * 10)):
        try:
            d = live_doc(p) or json.loads(p.read_text())
            if cond(d): return d
        except (OSError, ValueError): pass
        time.sleep(0.1)
    raise AssertionError(f"no {p} as expected")


def test_scene_card_editor_snapshot_and_agent_changes(hy):
    port, lib = hy
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        page = browser.new_page(viewport={"width": 1500, "height": 950})
        errors = []; page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"http://127.0.0.1:{port}/canvas.html")
        page.wait_for_function("() => typeof PLGST !== 'undefined' && PLGST.some(p => p.name === '3d' && p.ok)", timeout=20000)
        page.click("#bplus"); page.click("#bplusm [title^='3D-сцена']")
        page.wait_for_function("() => Object.values(board.items).some(i => i.type === 'model3d' && i.scene)")
        card = page.evaluate("() => Object.entries(board.items).find(([k, i]) => i.type === 'model3d')")
        cid, it = card
        scene = lib / it["scene"]
        doc = wait_file(scene, lambda d: len(d["objects"]) == 2)
        assert doc["format"] == "hyimg-scene/1" and doc["cameras"][0]["id"] == it["camera"]
        # 2026-10-05: a new scene holds no model of anyone's, a plain stand-in shape with a neutral name and text for the AI
        stand = doc["objects"][0]
        assert stand["src"]["type"] == "prim" and stand["name"] == "Предмет" and stand["ai"] == "главный предмет кадра", stand
        assert not (lib / "3d/models" / MODEL / "assembled.glb").exists(), "no model is touched by a new scene"
        model_in_the_middle(page, scene)
        shot(page, "1-card")

        page.dblclick(".plg[data-type=model3d]", position=CORNER)
        page.wait_for_selector(".m3ui .m3l .row")
        assert page.locator(".m3ui .m3l .row").count() == 5   # the model, floor, two lights, camera
        for _ in range(150):   # opening a scene writes its model as one file for Blender
            f = lib / "3d/models" / MODEL / "assembled.glb"
            if f.is_file() and f.stat().st_size > 1000: break
            time.sleep(0.1)
        assert (lib / "3d/models" / MODEL / "assembled.glb").stat().st_size > 1000, "the assembled model for Blender"
        if os.environ.get("HYIMG_PROBE"):
            print(page.inner_html(".m3ui .m3r")[:6000])
        # the mouse is an arrow over the card, never a hand
        assert page.evaluate("() => getComputedStyle(document.querySelector('canvas.m3live')).cursor") == "default"
        # a click picks the model, a second click a layer of it; the tree opens down to that layer
        r = page.locator("canvas.m3live").bounding_box(); cx, cy = r["x"] + r["width"] * 0.5, r["y"] + r["height"] * 0.42
        page.mouse.click(cx, cy); page.wait_for_timeout(300)
        assert page.locator(".m3l .row.sel").inner_text().startswith(TITLE)
        page.mouse.click(cx, cy); page.wait_for_timeout(300)
        sel = page.locator(".m3l .row.sel"); assert sel.count() == 1 and not sel.inner_text().startswith(TITLE), "the second click picks a layer"
        assert page.locator(".m3r .real").inner_text().startswith(TITLE + " ›")
        page.keyboard.press("Escape"); page.keyboard.press("Escape"); page.keyboard.press("Escape")
        page.wait_for_timeout(200)
        if page.locator(".m3ui").count() == 0: page.dblclick(".plg[data-type=model3d]", position=CORNER); page.wait_for_selector(".m3ui .m3l .row")
        page.click(".m3t [data-plus]"); page.click(".m3menu [data-add=box]")
        doc = wait_file(scene, lambda d: any(o["src"].get("shape") == "box" for o in d["objects"]))
        box = next(o for o in doc["objects"] if o["src"].get("shape") == "box")
        # the box's height in the DialKit panel: focus its slider and step it with the keyboard
        z = page.locator(".m3r .hy-slider").filter(has_text="Z").last
        z.locator("input").focus(); [page.keyboard.press("ArrowRight") for _ in range(5)]
        doc = wait_file(scene, lambda d: next(o for o in d["objects"] if o["id"] == box["id"])["src"]["size"][2] > 0.1)
        box = next(o for o in doc["objects"] if o["id"] == box["id"])
        assert box["name"].startswith("Куб") and not box.get("ai"), "the panel of the box does not carry the phone's name or text"
        shot(page, "2-editor")
        # «Тянуть»: pulling the phone by its top corner sideways moves it and turns it, the file follows
        ph = next(o for o in json.loads(scene.read_text())["objects"] if o["src"].get("type") == "model")
        go_on(page); page.click('.m3t [data-tool="smart"]')
        r = page.locator("canvas.m3live").bounding_box()
        page.wait_for_timeout(1500); go_on(page)   # the guard may stop a slow frame right after the tool switch
        shot(page, "2a-before-pull"); page.mouse.move(r["x"] + r["width"] * 0.5, r["y"] + r["height"] * 0.3); page.mouse.down()
        for i in range(12): page.mouse.move(r["x"] + r["width"] * (0.5 + 0.02 * i), r["y"] + r["height"] * 0.3); page.wait_for_timeout(60)
        page.wait_for_timeout(400); shot(page, "2b-pulled"); page.mouse.up()
        moved = wait_file(scene, lambda d: next(o for o in d["objects"] if o["id"] == ph["id"])["rot"] != ph["rot"], t=15)
        ph2 = next(o for o in moved["objects"] if o["id"] == ph["id"])
        assert ph2["loc"] != ph["loc"], "a pull moves the phone as well as turning it"
        # 2026-10-04: pulled by its top the phone only turns, about the touched point mirrored through its centre (near its bottom end)
        def qrot(q, v):   # Blender [w, x, y, z] applied to a point
            w, x, y, z = q; tx, ty, tz = 2 * (y * v[2] - z * v[1]), 2 * (z * v[0] - x * v[2]), 2 * (x * v[1] - y * v[0])
            return [v[0] + w * tx + y * tz - z * ty, v[1] + w * ty + z * tx - x * tz, v[2] + w * tz + x * ty - y * tx]
        end = lambda o, s: [a + b for a, b in zip(o["loc"], qrot(o["rot"], [0, 0, s * 0.08]))]   # the ends of the 16 cm phone, centred on its origin
        mv = lambda s: math.dist(end(ph, s), end(ph2, s))
        q0, q1 = ph["rot"], ph2["rot"]; turn = 2 * math.degrees(math.acos(min(1, abs(sum(x * y for x, y in zip(q0, q1))))))
        if os.environ.get("HYIMG_PROBE"): print("pull turn", turn, "top moved", mv(1), "bottom moved", mv(-1))
        assert turn > 10 and mv(-1) < 0.2 * mv(1), f"turned {turn:.0f}°, top moved {mv(1) * 100:.1f} cm, bottom {mv(-1) * 100:.1f} cm"
        # «Ось: Центр»: the same pull turns it about its centre, its position stays
        page.click('.m3t [data-tool="select"]'); page.evaluate("() => HY.setPref('m3.pull.pivot', 'center')")
        go_on(page); page.click('.m3t [data-tool="smart"]'); page.wait_for_timeout(800); go_on(page)
        page.mouse.move(r["x"] + r["width"] * 0.56, r["y"] + r["height"] * 0.42); page.mouse.down()
        for i in range(8): page.mouse.move(r["x"] + r["width"] * (0.56 - 0.02 * i), r["y"] + r["height"] * 0.42); page.wait_for_timeout(60)
        page.wait_for_timeout(400); page.mouse.up()
        c3 = wait_file(scene, lambda d: next(o for o in d["objects"] if o["id"] == ph["id"])["rot"] != ph2["rot"], t=15)
        ph3 = next(o for o in c3["objects"] if o["id"] == ph["id"])
        assert math.dist(ph3["loc"], ph2["loc"]) < 0.002, (ph2["loc"], ph3["loc"])
        page.evaluate("() => HY.setPref('m3.pull.pivot', 'mirror')")
        page.click('.m3t [data-tool="select"]')

        # the axes: a click on Z flies the card's camera to the top view, the scene file follows
        cam_before = json.loads(scene.read_text())["cameras"][0]["rot"]
        go_on(page); page.click('.m3x [data-ax="Z+"] circle', force=True)
        wait_file(scene, lambda d: d["cameras"][0]["rot"] != cam_before, t=15)
        go_on(page)   # software GL here is slow: the guard may have paused the editor with its question
        loc0 = doc["cameras"][0]["loc"]
        r = page.locator("canvas.m3live").bounding_box()
        page.keyboard.down("Alt"); page.mouse.move(r["x"] + r["width"] * 0.3, r["y"] + r["height"] * 0.85); page.mouse.down()   # ⌥: the camera (tools.js)
        page.mouse.move(r["x"] + r["width"] * 0.6, r["y"] + r["height"] * 0.8, steps=8); page.mouse.up(); page.keyboard.up("Alt")
        doc = wait_file(scene, lambda d: d["cameras"][0]["loc"] != loc0)
        # «+» lists the project's models (3d/models, the plugin's route models.py); a picked one takes its name and AI text from model.json
        go_on(page); page.click(".m3t [data-plus]")
        page.wait_for_selector(f".m3menu [data-add='model:{MODEL}']")
        assert page.locator(f".m3menu [data-add='model:{MODEL}']").inner_text().strip() == TITLE
        page.click(f".m3menu [data-add='model:{MODEL}']")
        doc = wait_file(scene, lambda d: sum(o["src"].get("type") == "model" for o in d["objects"]) == 2)
        added = [o for o in doc["objects"] if o["src"].get("type") == "model"][-1]
        assert added["name"].startswith(TITLE) and added["ai"] == AI and added["src"]["model"] == MODEL, added
        go_on(page); page.click(".m3t [data-plus]"); page.click(".m3menu [data-add='model:vase']")
        doc = wait_file(scene, lambda d: any(o["src"].get("model") == "vase" for o in d["objects"]))
        vase = next(o for o in doc["objects"] if o["src"].get("model") == "vase")
        assert vase["name"] == "Ваза 1" and vase["ai"] == "" and abs(vase["loc"][2] - 0.1255) < 0.001, vase
        for _ in range(150):
            if (lib / "3d/models/vase/assembled.glb").is_file(): break
            time.sleep(0.1)
        assert (lib / "3d/models/vase/assembled.glb").stat().st_size > 500, "a model without a phone is put together too"
        go_on(page); page.keyboard.press("p")
        page.wait_for_function("() => Object.values(board.items).filter(i => i.path && i.path.startsWith('3d/shots/')).length === 3", timeout=30000)
        shots = sorted((lib / "3d/shots").rglob("*.json"))
        metas = [json.loads(x.read_text()) for x in shots]
        assert {m["pass"] for m in metas} == {"вид", "маски", "глубина"}
        assert all(m["scene"] == it["scene"] for m in metas) and any(AI in m["prompt"] for m in metas)
        before_edit = page.evaluate("() => document.querySelector('.plg[data-type=model3d] img.m3').src")
        page.keyboard.press("Escape"); page.keyboard.press("Meta+Enter")   # the pick dropped, then «Save» ⌘↵ (Esc with changes asks first)
        page.wait_for_function("() => !document.querySelector('.m3ui')")
        # «Готово» shows the edited scene on the card (2026-10-03: it kept the old view)
        page.wait_for_function(f"() => document.querySelector('.plg[data-type=model3d] img.m3').src !== {json.dumps(before_edit)}", timeout=30000)
        shot(page, "3-after-snapshot")

        # an agent rewrites the file (as hyimg_scene.py export does): the card follows what the cards share (here the world's colour); the
        # scene's camera of the card's id is only a copy now, the card keeps its own view (item.view, owner 2026-10-07)
        src0, v0 = page.evaluate("() => [document.querySelector('.plg[data-type=model3d] img.m3').src, Object.values(board.items).find(i => i.view).view]")
        d = json.loads(scene.read_text()); d["cameras"][0]["lens"] = 24; d["world"]["color"] = [0.7, 0.2, 0.2]; d["rev"] += 1; d["by"] = "blender"
        cam2 = dict(d["cameras"][0], id="cam2", name="Камера 2", lens=120); d["cameras"].append(cam2)
        scene.write_text(json.dumps(d, ensure_ascii=False))
        page.wait_for_function(f"() => document.querySelector('.plg[data-type=model3d] img.m3').src !== {json.dumps(src0)}", timeout=30000)   # a slow card (software GL here) waits up to 20 s
        assert page.evaluate("() => Object.values(board.items).find(i => i.view).view.lens") == v0["lens"] != 24, "the card keeps its own view"
        (lib / "3d/scenes/inbox.json").write_text(json.dumps({"id": "req1", "scene": it["scene"], "cameras": [d["cameras"][0]["id"], "cam2"]}))
        page.wait_for_function("() => Object.values(board.items).filter(i => i.type === 'model3d').length === 2", timeout=15000)
        assert page.evaluate("() => Object.values(board.items).filter(i => i.type === 'model3d').map(i => i.camera)").count("cam2") == 1

        # the card's own background: transparent lets the board through, the poster keeps its alpha
        page.evaluate(f"() => {{ const b = snap(); board.items[{json.dumps(cid)}].bg = {{transparent: true}}; commit(b); }}")
        page.wait_for_function(f"() => document.querySelector('.plg[data-id={cid}] img.m3').src.startsWith('data:image/png')", timeout=30000)

        # each card's still is a file of the project beside its scene, one per card (the card that changed its background left no old one)
        page.wait_for_timeout(1500)   # the last stills being written
        stills = sorted(p.name for p in (scene.parent / ".posters").iterdir())
        assert len(stills) == 2 and {n.split("-")[0] for n in stills} == {cid, page.evaluate("() => Object.keys(board.items).find(k => board.items[k].camera === 'cam2')")}, stills
        assert any(n.endswith(".png") for n in stills), "the see-through card's still keeps its alpha"
        # the next page load shows the cards from those files at once, without three.js (owner: «like ordinary pictures»)
        page.reload()
        page.wait_for_function("() => { const im = [...document.querySelectorAll('.plg[data-type=model3d] img.m3')]; return im.length >= 2 && im.every(i => i.complete && i.naturalWidth && i.src.includes('.posters')) }", timeout=15000)
        loaded = page.evaluate("() => performance.getEntriesByType('resource').map(r => r.name)")
        assert not any(n.endswith("engine.js") or "three.module" in n for n in loaded), "three.js loaded although every card had a cached picture"
        # 2026-10-04: a still under the name stills had before the frame was in it still shows at once, while the new one is drawn
        def fnv(s):
            h = 0x811c9dc5
            for ch in s: h = ((h ^ ord(ch)) * 0x01000193) & 0xffffffff
            return f"{h:08x}"
        k2 = page.evaluate("() => Object.keys(board.items).find(k => board.items[k].camera === 'cam2')"); it2 = page.evaluate(f"() => board.items[{json.dumps(k2)}]")
        new = next(p for p in (scene.parent / ".posters").iterdir() if p.name.startswith(k2 + "-"))
        oldname = f"{k2}-{fnv(json.dumps([it2.get('camera') or '', it2.get('bg')], separators=(',', ':'), ensure_ascii=False))}{new.suffix}"
        new.rename(new.with_name(oldname))
        page.reload()
        page.wait_for_function(f"() => {{ const i = document.querySelector('.plg[data-id={k2}] img.m3'); return i && i.src.includes({json.dumps(oldname)}) && i.complete && i.naturalWidth }}", timeout=5000)
        assert page.evaluate(f"() => document.querySelector('.plg[data-id={k2}]').classList.contains('lo')"), "a loaded card drops its grey"

        # a scene over the size limit waits on its card
        big = lib / "3d/big/huge.glb"; big.parent.mkdir(parents=True)
        with open(big, "wb") as f: f.truncate(120 * 1024 * 1024)
        hd = json.loads(scene.read_text()); hd["objects"] = [{"id": "h1", "name": "Огромная", "src": {"type": "file", "path": "3d/big/huge.glb"}, "loc": [0, 0, 0], "rot": [1, 0, 0, 0], "scale": [1, 1, 1]}]
        hs = lib / "3d/scenes/heavy/scene.json"; hs.parent.mkdir(parents=True); hs.write_text(json.dumps(hd, ensure_ascii=False))
        page.evaluate("() => { const b = snap(); board.items.hv = {type: 'model3d', scene: '3d/scenes/heavy/scene.json', camera: 'cam2', x: -900, y: 0, w: 400, h: 500}; commit(b); }")
        page.wait_for_selector(".plg[data-id=hv] .h3", state="attached", timeout=15000)   # after the reload the card may lie off screen
        assert "120 МБ" in page.text_content(".plg[data-id=hv] .h3")
        shot(page, "4-heavy")
        assert not errors, errors
        browser.close()


def test_library_folds_while_the_editor_is_open(hy):
    """Owner 2026-10-03: opening the 3D editor folds the media library if it is open, «Готово» brings it back."""
    port, lib = hy
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        page = browser.new_page(viewport={"width": 1500, "height": 950})
        errors = []; page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"http://127.0.0.1:{port}/")
        page.evaluate("() => localStorage.setItem('view', 'panel')"); page.reload()
        page.wait_for_function("() => document.body.classList.contains('cv-on') && !document.body.classList.contains('cv-only')")
        cv = page.frame_locator("#cvFrame")
        frame = next(f for f in page.frames if "/canvas" in f.url)
        frame.wait_for_function("() => typeof PLGST !== 'undefined' && PLGST.some(p => p.name === '3d' && p.ok)", timeout=20000)
        cv.locator("#bplus").click(); cv.locator("#bplusm [title^='3D-сцена']").click()
        frame.wait_for_function("() => { const i = document.querySelector('.plg[data-type=model3d] img.m3'); return i && i.src.startsWith('data:image') }", timeout=30000)
        cv.locator(".plg[data-type=model3d]").dblclick(position=CORNER)
        page.wait_for_function("() => document.body.classList.contains('cv-only')", timeout=15000)
        assert page.evaluate("() => localStorage.getItem('view')") == "panel", "the remembered view stays"
        go_on(cv)
        cv.locator("hy-studio-actions [data-a=save]").click()
        page.wait_for_function("() => !document.body.classList.contains('cv-only') && document.body.classList.contains('cv-on')", timeout=15000)
        assert not errors, errors
        browser.close()


def test_card_frame_changes_like_a_picture_crop(hy):
    """Owner 2026-10-03: «why can't I change the size like a picture, 1:1, free and so on». In the editor the card's frame works like a
    crop: the list «Кадр» in the Scene panel (Свободно, 1:1, 4:5 …) and its ⇄, edges and corners that move freely. Since 2026-10-07 the
    choice is only in the panel, no ratio bar over the card (owner: «вот это в рендере я бы убрал, оно мешает», frameBar: false).
    The card keeps its frame, the scene's render size follows it, and the still is drawn again in the new frame."""
    port, lib = hy
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        page = browser.new_page(viewport={"width": 1500, "height": 950})
        errors = []; page.on("pageerror", lambda e: errors.append(str(e)))
        # every listener put on a canvas, alive until its signal aborts: what the editor canvas carries at any moment
        page.add_init_script("""(() => { let L = []; const P = HTMLCanvasElement.prototype, add = P.addEventListener, rm = P.removeEventListener, cap = o => !!(o === true || (o && o.capture));
          P.addEventListener = function (t, f, o) { L.push({ el: this, t, f, c: cap(o), o }); return add.call(this, t, f, o); };
          P.removeEventListener = function (t, f, o) { const i = L.findIndex(x => x.el === this && x.t === t && x.f === f && x.c === cap(o)); if (i >= 0) L.splice(i, 1); return rm.call(this, t, f, o); };
          window.__m3on = () => { const c = document.querySelector('canvas.m3live'); return L.filter(x => x.el === c && !(x.o && x.o.signal && x.o.signal.aborted)).length; }; })()""")
        page.goto(f"http://127.0.0.1:{port}/canvas.html")
        page.wait_for_function("() => typeof PLGST !== 'undefined' && PLGST.some(p => p.name === '3d' && p.ok)", timeout=20000)
        page.click("#bplus"); page.click("#bplusm [title^='3D-сцена']")
        page.wait_for_function("() => Object.values(board.items).some(i => i.type === 'model3d' && i.scene)")
        cid, it = page.evaluate("() => Object.entries(board.items).find(([k, i]) => i.type === 'model3d')")
        scene = lib / it["scene"]
        model_in_the_middle(page, scene)
        size = lambda: page.evaluate(f"() => {{ const i = board.items[{json.dumps(cid)}]; return [i.w, i.h, i.lock || null]; }}")
        assert not page.locator(".tidy.cratio").count(), "at rest the card scales like a picture, no frame bar"
        page.dblclick(".plg[data-type=model3d]", position=CORNER); page.wait_for_selector(".m3ui .m3l .row"); go_on(page)
        live1 = page.evaluate("() => window.__m3on()")
        # «Сбросить» (owner 2026-10-04): pale while nothing changed; a change of the background's transparency leaves the camera where it was
        # (a stale coordinates folder moved it) and lights the dock's reset and the panel's; the dock's reset brings everything back
        doc0 = scene_now(scene); item0 = page.evaluate(f"() => JSON.parse(JSON.stringify(board.items[{json.dumps(cid)}]))")
        page.wait_for_timeout(500)
        assert page.locator("#dock [data-a=reset]").is_disabled() and page.locator(".m3r .dk button.hy-reset").is_disabled()
        tr = page.locator(".m3r .hy-slider").filter(has_text="Прозрачность").first
        tr.locator("input").focus(); [page.keyboard.press("ArrowRight") for _ in range(10)]; go_on(page)
        page.wait_for_function(f"() => (board.items[{json.dumps(cid)}].bg || {{}}).opacity === 90", timeout=10000); page.wait_for_timeout(600)
        assert scene_now(scene)["cameras"][0]["loc"] == doc0["cameras"][0]["loc"], "the camera stays when the background changes"
        assert page.locator("#dock [data-a=reset]").is_enabled() and page.locator(".m3r .dk button.hy-reset").is_enabled()
        # the dock's reset is a neutral round icon among the tools (owner 2026-10-06: red is only for deleting), its words in its label;
        # read it once it rests (a finished entrance animation with fill stays in getAnimations(): only running ones count)
        page.wait_for_function("() => document.querySelector('#dock [data-a=reset]').getAnimations().every(a => a.playState !== 'running')", timeout=5000)
        bgc = page.evaluate("() => getComputedStyle(document.querySelector('#dock [data-a=reset]')).backgroundColor")
        r, g, b = [float(x) for x in __import__("re").findall(r"[\d.]+", bgc)[:3]]
        assert not (r > 180 and g < 90 and b < 90), f"the dock's reset is not red: {bgc}"
        assert "Сбросить" in page.locator("#dock [data-a=reset]").get_attribute("aria-label"), "the reset carries its word"
        page.click("#dock [data-a=reset]"); go_on(page)
        page.wait_for_function(f"() => JSON.stringify(board.items[{json.dumps(cid)}].bg) === {json.dumps(json.dumps(item0.get('bg'), separators=(',', ':')))} || board.items[{json.dumps(cid)}].bg === undefined", timeout=10000)
        page.wait_for_timeout(500)
        assert page.locator("#dock [data-a=reset]").is_disabled()
        dist = page.locator(".m3r .hy-slider").filter(has_text="Расстояние").first
        assert float(dist.inner_text().split()[-1]) > 20, "«Положение камеры» shows the camera's real distance at once"
        bw = page.evaluate("() => [...document.querySelectorAll('#dock .plgdock .wide')].map(b => b.scrollWidth <= b.clientWidth + 1)")
        assert bw and all(bw), "«Снимок» and «Готово» fit their buttons"
        # the editor's buttons are in the board's dock, the board's own are away until «Готово» (owner 2026-10-04)
        assert page.locator("#dock.plg-mode .m3t [data-tool=smart]").is_visible() and not page.locator("#dock #tlib").is_visible()
        shot(page, "dock-3d")
        assert not page.locator(".tidy.cratio").count(), "no ratio bar over the card in the studio: the frame is in the Scene panel"
        # «Тянуть» (owner 2026-10-04: «I pull up and it goes down»): the touched point stays under the mouse. A drag from the top of the
        # phone down toward its pivot (near the bottom) brings the top toward the camera, and the top goes down on screen with the mouse
        def qrot(q, v):
            w, x, y, z = q; tx, ty, tz = 2 * (y * v[2] - z * v[1]), 2 * (z * v[0] - x * v[2]), 2 * (x * v[1] - y * v[0])
            return [v[0] + w * tx + y * tz - z * ty, v[1] + w * ty + z * tx - x * tz, v[2] + w * tz + x * ty - y * tx]
        top = lambda o: [a + b for a, b in zip(o["loc"], qrot(o["rot"], [0, 0, 0.08]))]
        d0 = scene_now(scene); ph = next(o for o in d0["objects"] if o["src"].get("type") == "model"); cam = d0["cameras"][0]["loc"]
        page.click('.m3t [data-tool="smart"]'); page.wait_for_timeout(800); go_on(page)
        r = page.locator("canvas.m3live").bounding_box()
        page.mouse.move(r["x"] + r["width"] * 0.5, r["y"] + r["height"] * 0.3); page.mouse.down()
        for i in range(8): page.mouse.move(r["x"] + r["width"] * 0.5, r["y"] + r["height"] * (0.3 + 0.02 * i)); page.wait_for_timeout(60)
        page.wait_for_timeout(500); page.mouse.up(); go_on(page)
        ph1 = next(o for o in wait_file(scene, lambda d: next(o for o in d["objects"] if o["id"] == ph["id"])["rot"] != ph["rot"], t=15)["objects"] if o["id"] == ph["id"])
        assert math.dist(top(ph1), cam) < math.dist(top(ph), cam) - 0.01, (top(ph), top(ph1), cam)
        page.click('.m3t [data-tool="select"]'); page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.keyboard.press("Escape"); page.wait_for_selector(".m3r .ih >> text=Сцена")   # Esc drops the pick: the scene's settings again
        def frame_to(label):   # the Scene panel's «Кадр», the same choice as the board's frame bar
            page.locator(".m3r .dialkit-select-trigger", has_text="Кадр").first.click()
            page.locator(".dialkit-select-option", has_text=label).first.click(); page.wait_for_timeout(700); go_on(page)
        frame_to("1:1")
        w, h, lock = size(); assert abs(w - h) <= 1 and lock == "1:1", (w, h, lock)
        wait_file(scene, lambda d: d["render"]["x"] == d["render"]["y"])
        assert page.locator(".m3r .dialkit-select-trigger", has_text="Кадр").first.inner_text().strip().endswith("1:1")
        frame_to("Свободно")
        assert size()[2] is None
        e = page.locator(f".he[data-resize={cid}][data-rc=e]").bounding_box()
        page.mouse.move(e["x"] + e["width"] / 2, e["y"] + e["height"] / 2); page.mouse.down()
        page.mouse.move(e["x"] + e["width"] / 2 + 160, e["y"] + e["height"] / 2, steps=6); page.mouse.up(); go_on(page)
        w2, h2, _ = size(); assert w2 > w + 50 and abs(h2 - h) <= 1, (w, h, w2, h2)
        wait_file(scene, lambda d: abs(d["render"]["x"] / d["render"]["y"] - w2 / h2) < 0.01)
        # «Положение камеры», as in KeyShot (owner 2026-10-04): the azimuth turns the camera round the point it looks at, the distance stays
        k0 = scene_now(scene)["cameras"][0]
        az = page.locator(".m3r .hy-slider").filter(has_text="Азимут").first
        v0 = float(az.inner_text().split()[-1]); az.locator("input").focus(); [page.keyboard.press("ArrowRight") for _ in range(30)]; go_on(page)
        k1 = wait_file(scene, lambda d: d["cameras"][0]["loc"] != k0["loc"])["cameras"][0]; page.wait_for_timeout(400); k1 = scene_now(scene)["cameras"][0]
        hz = lambda l: math.hypot(l[0], l[1])   # the phone stands at the origin: the camera keeps its height and its distance on the floor
        assert abs(k1["loc"][2] - k0["loc"][2]) < 0.01 and abs(hz(k1["loc"]) - hz(k0["loc"])) < 0.02, (k0["loc"], k1["loc"])
        assert float(az.inner_text().split()[-1]) != v0
        # the twist stays when the camera is then turned with the mouse (2026-10-04: the orbit control undid it at once)
        tw = page.locator(".m3r .hy-slider").filter(has_text="Крен").first
        tw.locator("input").focus(); [page.keyboard.press("ArrowRight") for _ in range(12)]; go_on(page); page.wait_for_timeout(600)
        r = page.locator("canvas.m3live").bounding_box(); page.keyboard.down("Alt"); page.mouse.move(r["x"] + r["width"] * 0.3, r["y"] + r["height"] * 0.8)
        page.mouse.down(); page.mouse.move(r["x"] + r["width"] * 0.36, r["y"] + r["height"] * 0.8, steps=4); page.mouse.up(); page.keyboard.up("Alt")
        page.wait_for_timeout(800); go_on(page)
        twist = float(page.locator(".m3r .hy-slider").filter(has_text="Крен").first.inner_text().split()[-1])
        assert abs(twist - 12) <= 2, f"twist after a mouse turn: {twist}"
        # «Координаты» (a folder that opens): the camera's location as Blender shows it
        c0 = scene_now(scene)["cameras"][0]["loc"]
        page.locator(".m3r").get_by_text("Координаты", exact=True).first.click(); page.wait_for_timeout(300)
        cx = page.locator(".m3r .hy-slider").filter(has_text="X").first
        cx.locator("input").focus(); [page.keyboard.press("ArrowRight") for _ in range(20)]; go_on(page)
        c1 = wait_file(scene, lambda d: abs(d["cameras"][0]["loc"][0] - c0[0]) > 0.01)["cameras"][0]["loc"]
        assert abs(c1[1] - c0[1]) < 0.005 and abs(c1[2] - c0[2]) < 0.005, (c0, c1)
        # «Широкий ↔ изометрия»: a dolly zoom; the lens grows, the camera backs away along its line of sight by the same factor
        c1 = scene_now(scene)["cameras"][0]; shot(page, "dolly-0")
        sl = page.locator(".m3r .hy-slider").filter(has_text="Широкий").first
        sl.locator("input").focus(); [page.keyboard.press("ArrowRight") for _ in range(15)]; go_on(page)
        c2 = wait_file(scene, lambda d: d["cameras"][0]["lens"] > c1["lens"] * 1.5)["cameras"][0]
        page.wait_for_timeout(500); c2 = scene_now(scene)["cameras"][0]
        shot(page, "dolly-1")
        sl.locator("input").focus(); [page.keyboard.press("ArrowLeft") for _ in range(45)]; go_on(page); page.wait_for_timeout(800); shot(page, "dolly-2")
        sl.locator("input").focus(); [page.keyboard.press("ArrowRight") for _ in range(40)]; go_on(page); page.wait_for_timeout(800)
        c2 = scene_now(scene)["cameras"][0]
        assert max(abs(x - y) for x, y in zip(c2["rot"], c1["rot"])) < 1e-9, ("the camera keeps its direction (to the float's last digits)", c1["rot"], c2["rot"])
        dv = [b - a for a, b in zip(c1["loc"], c2["loc"])]; dist = math.sqrt(sum(x * x for x in dv))
        d1 = dist / (c2["lens"] / c1["lens"] - 1)   # the distance to the point it looks at, from how far it moved
        if os.environ.get("HYIMG_PROBE"): print("DOLLY", c1["loc"], c1["rot"], c1["lens"], c2["loc"], c2["rot"], c2["lens"], dist, d1)
        assert 0.3 < d1 < 1.5, (c1, c2, d1)
        assert page.locator(".m3r .hy-slider").filter(has_text="Объектив").first.inner_text().strip().endswith(str(round(c2["lens"])))
        # the list on the right is the same choice: 16:9 from it turns the card wide
        page.evaluate(f"() => HY.frame({json.dumps(cid)}, '16:9')"); go_on(page)
        w3, h3, lock3 = size(); assert lock3 == "16:9" and abs(w3 / h3 - 16 / 9) < 0.01
        page.click(".m3r .m3res [data-flip]"); go_on(page)
        w4, h4, lock4 = size(); assert lock4 == "9:16" and abs(w4 / h4 - 9 / 16) < 0.01
        go_on(page); page.click('.m3t [data-tool="smart"]'); page.click("hy-studio-actions [data-a=save]")   # closed with «Тянуть» on, as the owner did
        page.wait_for_function("() => !document.querySelector('.m3ui')")
        assert page.locator("#dock #tlib").is_visible() and not page.locator("#dock .plgdock").count(), "the dock is the board's again"
        page.wait_for_function(f"() => {{ const i = document.querySelector('.plg[data-id={cid}] img.m3'); return i && i.complete && i.naturalWidth && Math.abs(i.naturalWidth / i.naturalHeight - 9 / 16) < 0.02 }}", timeout=30000)
        page.wait_for_timeout(1500)
        stills = [p.name for p in (scene.parent / ".posters").iterdir()]
        assert len(stills) == 1 and stills[0].startswith(cid), stills
        assert not page.locator(".tidy.cratio").count()
        # opened again: the first session's listeners went with it (2026-10-04: a pull ran twice and a click drew two panels)
        page.dblclick(f".plg[data-id={cid}]", position=CORNER); page.wait_for_selector(".m3ui .m3l .row"); go_on(page)
        page.click('.m3t [data-tool="smart"]'); go_on(page)
        r = page.locator("canvas.m3live").bounding_box(); page.mouse.move(r["x"] + r["width"] * 0.5, r["y"] + r["height"] * 0.45); page.mouse.down()
        for i in range(5): page.mouse.move(r["x"] + r["width"] * (0.5 + 0.02 * i), r["y"] + r["height"] * 0.45); page.wait_for_timeout(60)
        page.mouse.up(); page.wait_for_timeout(800); go_on(page)
        heads = page.locator(".m3r .dialkit-panel-header").count(); assert heads == 1, f"{heads} panels"
        live2 = page.evaluate("() => window.__m3on()"); assert live2 == live1, f"listeners on the editor canvas: {live1} in the first session, {live2} now"
        assert not errors, errors
        browser.close()


SITE2 = {"format": "hyimg-scene/1", "rev": 1, "render": {"x": 2048, "y": 2048}, "world": {"color": [0.18, 0.18, 0.18], "strength": 1, "exposure": 0, "look": "AgX"},
         "objects": [{"id": "oqpn6rf1", "name": "Телефон", "src": {"type": "model", "model": MODEL}, "loc": [0, 0, 0], "rot": [1, 0, 0, 0], "scale": [1, 1, 1]}],
         "lights": [{"id": "e9oq2esx", "name": "Ключевой", "type": "area", "loc": [-0.45, -0.55, 0.55], "rot": [0.82954, 0.44592, -0.15918, -0.29612], "color": [1, 1, 1], "power": 25, "size": 0.6, "size_y": 0.6, "shape": "SQUARE"}],
         "cameras": [{"name": "Ракурс 2", "loc": [-0.5046, -0.6013, -0.0814], "rot": [0.66446, 0.66446, -0.24186, -0.24186], "lens": 154.21, "sensor": 36, "sensor_h": 36,
                      "fit": "VERTICAL", "shift": [-0.0098, 0.4548], "clip": [0.01, 100], "id": "jo1wd256"}], "active_camera": "jo1wd256"}


def board_server(tmp_path, items, scenes, lang="ru"):
    """a server on a fresh library with the given scenes ({folder: doc}) and board items; returns (port, lib, stop). lang: the app's
    interface language (cv.lang; "en" is the app's default and leaves the setting out)"""
    lib, state, plugins = tmp_path / "lib", tmp_path / "state", tmp_path / "plugins"
    tiny_model(lib)
    for n, doc in scenes.items():
        (lib / f"3d/scenes/{n}").mkdir(parents=True); (lib / f"3d/scenes/{n}/scene.json").write_text(json.dumps(doc))
    (state / "boards").mkdir(parents=True); plugins.mkdir(); (plugins / "3d").symlink_to(HERE)
    (state / "app-settings.json").write_text(json.dumps({"cv.lang": "ru"} if lang == "ru" else {}))
    (state / "boards/main.json").write_text(json.dumps({"items": items, "groups": {}, "revision": 1}))
    port = free_port()
    env = {k: v for k, v in os.environ.items() if not k.startswith(("HYIMG_", "REVIEW_"))}
    env.update(HYIMG_LIBRARY_ROOT=str(lib), HYIMG_STATE_ROOT=str(state), HYIMG_PROJECT_ID=str(uuid.uuid4()), HYIMG_PLUGINS=str(plugins), HYIMG_SETTINGS=str(state / "app-settings.json"), PYTHONDONTWRITEBYTECODE="1")
    log = open(tmp_path / "server.log", "w+")
    proc = subprocess.Popen([sys.executable, str(REPO / "review/server.py"), str(port)], env=env, stdout=log, stderr=log)
    for _ in range(100):
        try: urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1); break
        except OSError: time.sleep(0.1)
    def stop(): proc.terminate(); proc.wait(5); log.close()
    return port, lib, stop


def test_a_dolly_then_the_background_leaves_the_camera(tmp_path):
    """Owner 2026-10-04: «I change the transparency and the object jumps and turns». DialKit hands changes over in batches; the end of
    a «Широкий ↔ изометрия» drag arrived while the editor wrote the panel, was dropped, and was applied at the next touch of any
    control: the background's transparency drove the camera in. Both are dragged with the mouse here, as the owner does."""
    port, lib, stop = board_server(tmp_path, {"c": {"type": "model3d", "scene": "3d/scenes/a/scene.json", "camera": "jo1wd256", "x": 0, "y": 0, "w": 600, "h": 600}}, {"a": SITE2})
    scene = lib / "3d/scenes/a/scene.json"
    def drag(page, name, to):
        b = page.locator(".m3r .hy-slider").filter(has_text=name).first.bounding_box(); y = b["y"] + b["height"] / 2
        page.mouse.move(b["x"] + b["width"] * 0.6, y); page.mouse.down()
        for i in range(1, 9): page.mouse.move(b["x"] + b["width"] * (0.6 + (to - 0.6) * i / 8), y); page.wait_for_timeout(40)
        page.mouse.up(); page.wait_for_timeout(1500); go_on(page)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            errors = []; page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(f"http://127.0.0.1:{port}/canvas.html")
            page.wait_for_function("() => typeof PLGST !== 'undefined' && PLGST.some(p => p.name === '3d' && p.ok)", timeout=20000)
            page.wait_for_timeout(2000); page.dblclick(".plg[data-id=c]"); page.wait_for_timeout(2000); go_on(page)
            page.wait_for_selector(".m3r .hy-slider"); page.wait_for_timeout(1000)
            drag(page, "Широкий", 0.35)
            k0 = wait_file(scene, lambda d: d["cameras"][0]["lens"] != SITE2["cameras"][0]["lens"])["cameras"][0]   # the studio's scene (wait_file)
            drag(page, "Прозрачность", 0.2)
            k1 = scene_now(scene)["cameras"][0]
            assert k1["lens"] == k0["lens"] and math.dist(k1["loc"], k0["loc"]) < 1e-4, (k0, k1)
            assert not errors, errors
            browser.close()
    finally:
        stop()


def test_three_cards_get_real_stills_and_one_link(tmp_path):
    """Owner 2026-10-04 on «phonerefs»: two of three 3D cards were black, and with the three selected the right-click menu had no
    «Копировать ссылку». The stills of several cards are drawn one after another on one shared renderer; WebKit read the canvas for the
    file later, when the next card had already been drawn there, so the file came out black. Here toBlob is made late on purpose, as in
    WebKit: every still written must be a picture, and the menu offers a link to the whole selection."""
    lib, state, plugins = tmp_path / "lib", tmp_path / "state", tmp_path / "plugins"
    tiny_model(lib)
    for n in ("a", "b"):
        (lib / f"3d/scenes/{n}").mkdir(parents=True); (lib / f"3d/scenes/{n}/scene.json").write_text(json.dumps(SITE2))
    card = lambda n, x, y, **k: {"type": "model3d", "scene": f"3d/scenes/{n}/scene.json", "camera": "jo1wd256", "x": x, "y": y, "w": 380, "h": 380, **k}
    items = {"m1": card("a", 0, 0), "m2": card("b", 400, 0, w=300), "m3": card("a", 0, 420, bg={"transparent": False, "color": "#767676", "opacity": 48})}
    (state / "boards").mkdir(parents=True); plugins.mkdir(); (plugins / "3d").symlink_to(HERE)
    (state / "app-settings.json").write_text(json.dumps({"cv.lang": "ru"}))   # the board's Russian words (owner 2026-10-06: two languages)
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
            page = browser.new_page(viewport={"width": 1500, "height": 950})
            errors = []; page.on("pageerror", lambda e: errors.append(str(e)))
            page.add_init_script("""(() => { const tb = HTMLCanvasElement.prototype.toBlob;
              HTMLCanvasElement.prototype.toBlob = function (...a) { setTimeout(() => tb.apply(this, a), 400); }; })()""")
            page.goto(f"http://127.0.0.1:{port}/canvas.html")
            page.wait_for_function("() => typeof PLGST !== 'undefined' && PLGST.some(p => p.name === '3d' && p.ok)", timeout=20000)
            stills = lambda: sorted((lib / "3d/scenes").glob("*/.posters/*"))
            for _ in range(600):
                if len(stills()) == 3: break
                time.sleep(0.1)
            time.sleep(1.5)
            from PIL import Image
            for f in stills():
                im = Image.open(f); lo, hi = im.convert("L").getextrema(); it = items[f.name.split("-")[0]]
                assert hi - lo > 20, f"{f.name} is one flat colour ({lo}..{hi})"
                assert abs(im.width / im.height - it["w"] / it["h"]) < 0.02, f"{f.name} holds another card's picture: {im.size}"
            page.evaluate("() => { sel = new Set(['m1', 'm2', 'm3']); render(); }")
            b = page.locator(".plg[data-id=m2]").bounding_box()
            # the link is in «Копировать как ›» since hyimg 58e3147, what it links to in its tooltip
            def link_tip():
                page.mouse.click(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, button="right")
                page.locator("#ctx [data-sub=copyas]").hover()
                return page.locator("#ctx .hy-sub [data-act=link]").get_attribute("title")
            assert link_tip() == "Копировать ссылку на выделенное (3)"
            page.keyboard.press("Escape"); page.keyboard.press("Escape"); page.evaluate("() => { sel = new Set(); render(); }")
            assert link_tip() == "Копировать ссылку на 3D-сцену"
            assert not errors, errors
            browser.close()
    finally:
        proc.terminate(); proc.wait(5); log.close()


def test_numbers_are_typed_and_a_drag_goes_from_the_value(tmp_path):
    """Owner 2026-10-04: «I cannot type the numbers into these lines, and the step is far too wide; usually the mouse's speed solves it
    and typing the value». A click on the number types it, a double click on the line too; a drag moves the value from where it was by
    the mouse's way, with Shift ten times finer."""
    port, lib, stop = board_server(tmp_path, {"c": {"type": "model3d", "scene": "3d/scenes/a/scene.json", "camera": "jo1wd256", "x": 0, "y": 0, "w": 600, "h": 600}}, {"a": SITE2})
    scene = lib / "3d/scenes/a/scene.json"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            errors = []; page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(f"http://127.0.0.1:{port}/canvas.html")
            page.wait_for_function("() => typeof PLGST !== 'undefined' && PLGST.some(p => p.name === '3d' && p.ok)", timeout=20000)
            page.wait_for_timeout(2000); page.dblclick(".plg[data-id=c]"); page.wait_for_timeout(2000); go_on(page)
            page.wait_for_selector(".m3r .hy-slider"); page.wait_for_timeout(1000)
            lens = page.locator(".m3r .hy-slider-wrapper").filter(has_text="Объектив").first
            lens.locator(".hy-slider-v").hover(); page.wait_for_timeout(100); lens.locator(".hy-slider-v").click()
            lens.locator("input.hy-slider-ed").fill("50"); page.keyboard.press("Enter"); go_on(page)
            wait_file(scene, lambda d: d["cameras"][0]["lens"] == 50)
            tilt = page.locator(".m3r .hy-slider-wrapper").filter(has_text="Наклон").first
            tilt.locator(".hy-slider").dblclick(position={"x": 60, "y": 10})
            assert tilt.locator("input.hy-slider-ed").is_visible(), "a double click on the line types the number"
            page.keyboard.press("Escape")
            az = page.locator(".m3r .hy-slider").filter(has_text="Азимут").first
            val = lambda: float(az.inner_text().split()[-1].replace("−", "-"))
            def move(dx, shift=False):
                b = az.bounding_box(); x, y = b["x"] + b["width"] * 0.3, b["y"] + b["height"] / 2; v0 = val()
                if shift: page.keyboard.down("Shift")
                page.mouse.move(x, y); page.mouse.down(); page.mouse.move(x + dx, y, steps=6); page.mouse.up()
                if shift: page.keyboard.up("Shift")
                page.wait_for_timeout(500); go_on(page); return val() - v0, b["width"]
            d, w = move(40)
            assert abs(d - 40 / w * 360) <= 2, (d, w)   # from the value, by the mouse's way: no jump to where the mouse went down
            d, w = move(40, shift=True)
            assert abs(d - 40 / w * 36) <= 1.5 and abs(d) >= 1, (d, w)
            assert not errors, errors
            browser.close()
    finally:
        stop()


@pytest.mark.parametrize("hy", ["en"], indirect=True)
def test_the_plugin_speaks_english_by_default(hy):
    """The interface in English (owner 2026-10-06: «make 2 versions, Russian and English, switchable in settings», English the default):
    without cv.lang in the app's settings everything the plugin shows is English: the dock button, the card's badge and info, a new
    scene's names, the editor's toolbar, «+» menu, layers and every inspector panel (scene, object, light, camera), the board's undo
    notes. Scoped to the plugin's own elements: the board's own words are another module's."""
    port, lib = hy
    cyr = __import__("re").compile(r"[А-Яа-яЁё]")
    # the project's models in «+» carry their own titles (model.json, the owner's data: the test model's is Russian), left out
    texts = """(sel) => [...document.querySelectorAll(sel)].map(r0 => { const r = r0.cloneNode(true); r.querySelectorAll('[data-models]').forEach(x => x.remove());
        return r.textContent + ' ' + [r, ...r.querySelectorAll('[title],[aria-label],[placeholder]')]
        .map(e => [e.getAttribute('title'), e.getAttribute('aria-label'), e.getAttribute('placeholder')].filter(Boolean).join(' ')).join(' '); }).join(' | ')"""
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        page = browser.new_page(viewport={"width": 1500, "height": 950})
        errors = []; page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"http://127.0.0.1:{port}/canvas.html")
        page.wait_for_function("() => typeof PLGST !== 'undefined' && PLGST.some(p => p.name === '3d' && p.ok)", timeout=20000)
        assert page.evaluate("() => HY.lang") == "en"
        page.evaluate("() => { window.__notes = []; const c = window.commit; window.commit = (b, n) => { if (n) __notes.push(n); return c(b, n); }; }")
        page.click("#bplus")   # the dock's «+» › 3D scene (a button of its own until 2026-10-10)
        tip = page.locator("#bplusm [title^='3D scene']").get_attribute("title")
        assert not cyr.search(tip), tip
        page.click("#bplusm [title^='3D scene']")
        page.wait_for_function("() => Object.values(board.items).some(i => i.type === 'model3d' && i.scene)")
        cid, it = page.evaluate("() => Object.entries(board.items).find(([k, i]) => i.type === 'model3d')")
        doc = wait_file(lib / it["scene"], lambda d: len(d["objects"]) == 2)
        names = [o["name"] for o in doc["objects"]] + [l["name"] for l in doc["lights"]] + [c["name"] for c in doc["cameras"]]
        assert names == ["Object", "Floor", "Key", "Fill", "Camera 1"] and not cyr.search(doc["objects"][0]["ai"]), doc
        page.wait_for_function("() => { const i = document.querySelector('.plg[data-type=model3d] img.m3'); return i && i.src.startsWith('data:image') }", timeout=30000)
        assert not cyr.search(page.evaluate(texts, ".plg[data-type=model3d]"))
        page.evaluate(f"() => {{ sel = new Set([{json.dumps(cid)}]); render(); }}"); page.wait_for_timeout(300)
        page.evaluate(f"() => {{ sel = new Set([{json.dumps(cid)}]); render(); }}"); page.wait_for_timeout(300)   # the info card reads the scene once
        info = page.locator("#iN").inner_text() + " " + page.locator("#iM").inner_text() + " " + page.locator("#iNotes").inner_text()   # the body: Hyimg's spec sheet (2026-10-10)
        assert "3D scene" in info and "2 objects, 2 lights, 1 camera" in info and not cyr.search(info), info
        # the editor: the scene's panel, then an object, a light and the camera
        page.dblclick(".plg[data-type=model3d]", position=CORNER); page.wait_for_selector(".m3ui .m3l .row"); go_on(page)
        seen = []
        def look(what):
            go_on(page); page.wait_for_timeout(300)
            t = " ".join(page.evaluate(texts, ".m3ui, #dock .plgdock").split()); seen.append(t)   # DialKit puts a space before a capital: «Power,  W»
            assert not cyr.search(t), (what, [w for w in cyr.findall(t)][:5], t[:3000])
        look("scene")
        assert "Lens, mm" in seen[-1] and "Wide ↔ isometric" in seen[-1] and "Snapshot" in seen[-1] and "Reset" in seen[-1]
        page.locator(".m3l .row", has_text="Object").first.click(); look("object")
        assert "Location, cm" in seen[-1] and "Prompt" in seen[-1]
        page.locator(".m3l .row", has_text="Key").first.click(); look("light")
        assert "Power, W" in seen[-1]
        page.locator(".m3l .row[data-cam]").first.click(); look("camera")
        assert "Camera position" in seen[-1]
        page.click(".m3t [data-plus]"); look("menu")
        assert "Cube" in seen[-1] and "Area light" in seen[-1]
        page.click(".m3menu [data-add=box]"); go_on(page)
        doc = wait_file(lib / it["scene"], lambda d: any(o["src"].get("shape") == "box" for o in d["objects"]))
        assert any(o["name"] == "Cube 1" for o in doc["objects"]), doc["objects"]
        look("box")
        page.keyboard.press("Escape"); page.keyboard.press("Escape"); page.keyboard.press("Meta+Enter")   # «Save» ⌘↵: Esc with changes asks first
        page.wait_for_function("() => !document.querySelector('.m3ui')", timeout=15000)
        notes = page.evaluate("() => __notes")
        assert notes and not any(cyr.search(n) for n in notes), notes
        assert not errors, errors
        browser.close()
