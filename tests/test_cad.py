"""STEP files as 3D files (owner 2026-10-06: «STEP support: convert a STEP file once to a 3D model with FreeCAD, which is already on this Mac,
and keep the result, the same way videos already get a WebM copy. After that it opens in the 3D card and turns in the library»).

The plugin's cad.py runs FreeCAD headless on a STEP file once per content and keeps the glb; the library lists the file in its «3D» filter
with a turntable drawn from that glb, the empty 3D card takes it from «Open file…», the library and «Recent». The STEP files are made here
by FreeCAD itself (a box and a cylinder, in millimetres), nothing is downloaded; without FreeCAD on the Mac the tests skip. FreeCAD is
reached through a wrapper script that counts its runs, so «once» is counted, not assumed. The test servers get their own cache folder and
their own FreeCAD user folder: the owner's FreeCAD, its settings and its RPC bridge are not touched.

  HYIMG_REPO=<Hyimg checkout> python3 -m pytest tests/test_cad.py
"""
import json, os, re, stat, struct, subprocess, sys, time, urllib.request, uuid
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import cad   # noqa: E402  the plugin's own module, for the in-process cases
from test_canvas_3d import HERE, REPO, free_port, tiny_model, wait_file   # noqa: E402
from test_3d_files import ENGINES, get, new_card, open_3d, open_board, open_library, scene_of, card_doc, objects_of_files   # noqa: E402

FC = cad.freecad()
pytestmark = pytest.mark.skipif(FC is None, reason="no FreeCAD on this Mac (nothing is installed or downloaded for the tests)")

@pytest.fixture(scope="session")
def steps(tmp_path_factory):
    """two STEP files FreeCAD writes: part.step, 60 x 40 x 20 mm with a 16 mm cylinder 30 mm tall on top (60 x 50 x 40 mm in all), and
    big.step, a metre long box"""
    d = tmp_path_factory.mktemp("steps"); script = d / "make.py"
    script.write_text(f"""
import FreeCAD, Part, Import, os
doc = FreeCAD.newDocument("m")
a = doc.addObject("Part::Feature", "base"); a.Shape = Part.makeBox(60, 40, 20)
b = doc.addObject("Part::Feature", "post"); b.Shape = Part.makeCylinder(8, 30, FreeCAD.Vector(30, 20, 20))
Import.export([a, b], {str(d / "part.step")!r})
doc2 = FreeCAD.newDocument("n")
c = doc2.addObject("Part::Feature", "slab"); c.Shape = Part.makeBox(1000, 500, 300)
Import.export([c], {str(d / "big.step")!r})
os._exit(0)
""")
    subprocess.run([FC["cmd"], str(script)], capture_output=True, timeout=120, env={k: v for k, v in os.environ.items() if not k.startswith(("PYTHON",))})
    assert (d / "part.step").stat().st_size > 1000 and (d / "big.step").stat().st_size > 500, "FreeCAD wrote no STEP"
    return d


def wrapper(dir_, delay=0.0, real=None):
    """a FreeCAD.app look-alike whose two programs log each run and then start the real ones: dir_/FreeCAD.app/Contents/Resources/bin/{freecadcmd,freecad}"""
    log = dir_ / "runs.log"; bin_ = dir_ / "FreeCAD.app/Contents/Resources/bin"; bin_.mkdir(parents=True)
    for name, real_exe in (("freecadcmd", (real or FC)["cmd"]), ("freecad", (real or FC)["gui"])):
        if not real_exe: continue
        (bin_ / name).write_text(f'#!/bin/sh\necho {name} >> "{log}"\nsleep {delay}\nexec "{real_exe}" "$@"\n')
        (bin_ / name).chmod(0o755)
    return dir_ / "FreeCAD.app", log


def runs(log): return log.read_text().split() if log.exists() else []


@pytest.fixture
def cadhy(tmp_path, request):
    """a Hyimg server with the plugin, its own cache folder and the wrapper as its FreeCAD; param: {"lang", "delay", "freecad": "none" | "real"}"""
    opt = {"lang": "en", "delay": 0.0, "freecad": "wrapper", "timeout": None, **(getattr(request, "param", None) or {})}
    lib, state, plugins = tmp_path / "lib", tmp_path / "state", tmp_path / "plugins"
    tiny_model(lib); (lib / "models").mkdir()
    (state / "boards").mkdir(parents=True); plugins.mkdir()
    (state / "app-settings.json").write_text(json.dumps({"cv.lang": "ru"} if opt["lang"] == "ru" else {}))
    (state / "boards/main.json").write_text(json.dumps({"items": {}, "groups": {}, "revision": 1}))
    (plugins / "3d").symlink_to(HERE)
    app, log = wrapper(tmp_path, opt["delay"])
    port = free_port()
    env = {k: v for k, v in os.environ.items() if not k.startswith(("HYIMG_", "REVIEW_"))}
    env.update(HYIMG_LIBRARY_ROOT=str(lib), HYIMG_STATE_ROOT=str(state), HYIMG_PROJECT_ID=str(uuid.uuid4()), HYIMG_PLUGINS=str(plugins), HYIMG_SETTINGS=str(state / "app-settings.json"),
               HYIMG_CAD_CACHE=str(tmp_path / "cad-cache"), HYIMG_FREECAD="" if opt["freecad"] == "none" else str(app), PYTHONDONTWRITEBYTECODE="1")
    if opt["timeout"]: env["HYIMG_CAD_TIMEOUT"] = str(opt["timeout"])
    logf = open(tmp_path / "server.log", "w+")
    proc = subprocess.Popen([sys.executable, str(REPO / "review/server.py"), str(port)], env=env, stdout=logf, stderr=logf)
    for _ in range(100):
        try: urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1); break
        except OSError: time.sleep(0.1)
    try:   # the server goes even when the test fails or is interrupted
        yield port, lib, log, tmp_path / "cad-cache"
    finally:
        proc.terminate(); proc.wait(5); logf.close()


def put_steps(lib, steps, *names):
    for n in names: (lib / "models" / n).write_bytes((steps / n).read_bytes())


def ask(port, route, body):
    code, data, _h = get(port, f"/api/plugin/3d/{route}", json.dumps(body).encode())
    assert code == 200, (code, data[:200])
    return json.loads(data)


def until_ready(port, path, t=90):
    t0 = time.time(); st = ask(port, "cad", {"path": path})
    while st["state"] == "working" and time.time() - t0 < t:
        time.sleep(0.3); st = ask(port, "cad", {"path": path})
    return st, time.time() - t0


def glb_bounds(raw):
    jl, = struct.unpack("<I", raw[12:16]); doc = json.loads(raw[20:20 + jl])
    acc = [a for a in doc["accessors"] if a["type"] == "VEC3" and "max" in a]
    lo = [min(a["min"][i] for a in acc) for i in range(3)]; hi = [max(a["max"][i] for a in acc) for i in range(3)]
    return [round(h - l, 4) for l, h in zip(lo, hi)], doc


# ---- the server: one FreeCAD run per content, the glb kept, limits

def test_a_step_converts_once_in_the_background_and_the_glb_is_kept(cadhy, steps):
    port, lib, log, cache = cadhy
    put_steps(lib, steps, "part.step")
    first = ask(port, "cad", {"path": "models/part.step"})
    assert first["state"] == "working", "the request only starts the job, it does not wait for FreeCAD"
    st, took = until_ready(port, "models/part.step")
    assert st["state"] == "ready" and st["key"] and st["bytes"] > 1000 and st["parts"] == 2, st
    raw = get(port, "/api/plugin/3d/cadglb", json.dumps({"key": st["key"]}).encode())[1]
    size, doc = glb_bounds(raw)
    # millimetres became metres, z up became y up: 60 x 40 x 20 + the post = 60 mm wide, 50 mm tall, 40 mm deep
    assert raw[:4] == b"glTF" and size == [0.06, 0.05, 0.04], size
    assert all("pbrMetallicRoughness" in m and m["pbrMetallicRoughness"]["metallicFactor"] < 1 for m in doc["materials"]) and all("material" in p for m in doc["meshes"] for p in m["primitives"]), "no part is left a black mirror"
    assert [n["name"] for n in doc["nodes"] if "mesh" in n] == ["base", "post"], "the parts keep their names"
    assert runs(log) == ["freecad"], f"one FreeCAD run, the GUI build off screen: {runs(log)}"
    assert (cache / (st["key"] + ".glb")).read_bytes() == raw and not list(cache.glob("work-*")), "the work folder is gone"
    # the second request, and the same content under another name and in another folder, are answered from the cache: no new run
    (lib / "models/copy of part.stp").write_bytes((lib / "models/part.step").read_bytes())
    again = ask(port, "cad", {"path": "models/part.step"}); other = ask(port, "cad", {"path": "models/copy of part.stp"})
    assert again["state"] == "ready" and again["key"] == st["key"]
    t0 = time.time(); other2, _ = until_ready(port, "models/copy of part.stp", 20)
    assert other2["state"] == "ready" and other2["key"] == st["key"] and runs(log) == ["freecad"], runs(log)
    # a file the person chose (not in the library) with the same content: the same glb
    code, put, _h = get(port, "/api/plugin/3d/cadput?name=part.step", (steps / "part.step").read_bytes())
    assert code == 200 and json.loads(put)["state"] == "ready" and json.loads(put)["key"] == st["key"] and runs(log) == ["freecad"]
    print(f"\nSTEP 60x40x20 mm + post, {(steps / 'part.step').stat().st_size} bytes: ready in {took:.1f} s, glb {st['bytes']} bytes ({st['mode']}, FreeCAD {st['version']}, {st['seconds']} s in FreeCAD)")


def test_a_chosen_file_is_sent_converted_and_asked_for_by_its_key(cadhy, steps):
    port, lib, log, cache = cadhy
    code, put, _h = get(port, "/api/plugin/3d/cadput?name=big.step", (steps / "big.step").read_bytes())
    st = json.loads(put); assert code == 200 and st["state"] in ("working", "ready") and re.fullmatch("[0-9a-f]{40}", st["key"]), st
    t0 = time.time()
    while st["state"] == "working" and time.time() - t0 < 60: time.sleep(0.3); st = ask(port, "cad", {"key": st["key"]})
    assert st["state"] == "ready"
    size, _doc = glb_bounds(get(port, "/api/plugin/3d/cadglb", json.dumps({"key": st["key"]}).encode())[1])
    assert size == [1.0, 0.3, 0.5], size
    assert not list((cache / "src").glob("*.big*")) and not list((cache / "src").glob("*.step*")), "the sent copy is not kept"


def test_a_broken_empty_or_foreign_file_gives_a_reason_and_the_list_stays(cadhy, steps):
    port, lib, log, cache = cadhy
    (lib / "models/broken.step").write_text("this is not a STEP file at all\n" * 20)
    (lib / "models/empty.step").write_bytes(b"")
    (lib / "models/notes.txt").write_text("x")
    put_steps(lib, steps, "part.step")
    bad, _ = until_ready(port, "models/broken.step")
    assert bad["state"] == "failed" and bad["reason"] in ("unreadable", "nogeometry"), bad
    empty = ask(port, "cad", {"path": "models/empty.step"})
    assert empty["state"] == "failed" or until_ready(port, "models/empty.step")[0]["reason"] == "empty"
    assert until_ready(port, "models/empty.step")[0]["reason"] == "empty"
    n = len(runs(log)); assert ask(port, "cad", {"path": "models/broken.step"})["state"] == "failed" and len(runs(log)) == n, "a failed file is not tried again at every look"
    for p in ("models/notes.txt", "../outside.step", "models/gone.step", "/etc/passwd", ""):
        assert get(port, "/api/plugin/3d/cad", json.dumps({"path": p}).encode())[0] == 404, p
    assert get(port, "/api/plugin/3d/cadglb", json.dumps({"key": "0" * 40}).encode())[0] == 404
    assert get(port, "/api/plugin/3d/cadput?name=a.txt", b"x")[0] == 400
    # the library still lists everything, the broken files too
    paths = {i["path"]: i for i in json.loads(get(port, "/api/models3d")[1])}
    assert {"models/part.step", "models/broken.step", "models/empty.step"} <= set(paths) and "models/notes.txt" not in paths and paths["models/part.step"]["ext"] == "STEP", sorted(paths)
    assert (until_ready(port, "models/part.step")[0]["state"] == "ready"), "and the good file after the broken ones converts"


@pytest.mark.parametrize("cadhy", [{"freecad": "none"}], indirect=True)
def test_without_freecad_the_state_says_so_and_nothing_hangs(cadhy, steps):
    port, lib, log, cache = cadhy
    put_steps(lib, steps, "part.step")
    st, took = until_ready(port, "models/part.step", 10)
    assert st["state"] == "failed" and st["reason"] == "nofreecad" and took < 5, st
    assert runs(log) == []


def test_a_conversion_over_the_time_limit_is_stopped(tmp_path, steps, monkeypatch):
    app, log = wrapper(tmp_path, delay=60)
    for k, v in (("HYIMG_FREECAD", str(app)), ("HYIMG_LIBRARY_ROOT", str(tmp_path / "lib"))): monkeypatch.setenv(k, v)
    (tmp_path / "lib").mkdir(); (tmp_path / "lib/p.step").write_bytes((steps / "part.step").read_bytes())
    monkeypatch.setattr(cad, "CACHE", str(tmp_path / "cache")); monkeypatch.setattr(cad, "TIMEOUT", 11); monkeypatch.setattr(cad, "_JOBS", {}); monkeypatch.setattr(cad, "_MEMO", {})
    t0 = time.time(); st = json.loads(cad.route_cad(json.dumps({"path": "p.step"}).encode())[2])
    assert st["state"] == "working" and time.time() - t0 < 2, "the route returns at once"
    while st["state"] == "working" and time.time() - t0 < 40: time.sleep(0.3); st = json.loads(cad.route_cad(json.dumps({"path": "p.step"}).encode())[2])
    assert st["state"] == "failed" and st["reason"] == "timeout" and 10 < time.time() - t0 < 25, (st, time.time() - t0)
    assert not subprocess.run(["pgrep", "-f", f"{tmp_path}/FreeCAD.app"], capture_output=True).stdout.strip(), "the process is gone, not left running"
    assert not list((tmp_path / "cache").glob("work-*"))


def test_a_source_over_the_size_limit_is_refused_before_any_run(tmp_path, steps, monkeypatch):
    app, log = wrapper(tmp_path)
    for k, v in (("HYIMG_FREECAD", str(app)), ("HYIMG_LIBRARY_ROOT", str(tmp_path / "lib"))): monkeypatch.setenv(k, v)
    (tmp_path / "lib").mkdir(); (tmp_path / "lib/p.step").write_bytes((steps / "part.step").read_bytes())
    monkeypatch.setattr(cad, "CACHE", str(tmp_path / "cache")); monkeypatch.setattr(cad, "SRC_MAX", 500); monkeypatch.setattr(cad, "_JOBS", {}); monkeypatch.setattr(cad, "_MEMO", {})
    st = json.loads(cad.route_cad(json.dumps({"path": "p.step"}).encode())[2])
    t0 = time.time()
    while st["state"] == "working" and time.time() - t0 < 10: time.sleep(0.1); st = json.loads(cad.route_cad(json.dumps({"path": "p.step"}).encode())[2])
    assert st["state"] == "failed" and st["reason"] == "toobig" and runs(log) == []


def test_the_console_build_is_the_fallback_and_its_glb_gets_a_grey(tmp_path, steps, monkeypatch):
    """no GUI build (a FreeCAD with only freecadcmd): the geometry comes without the STEP's colours and is dressed in one neutral grey"""
    app, log = wrapper(tmp_path, real={"cmd": FC["cmd"], "gui": None})
    for k, v in (("HYIMG_FREECAD", str(app)), ("HYIMG_LIBRARY_ROOT", str(tmp_path / "lib"))): monkeypatch.setenv(k, v)
    (tmp_path / "lib").mkdir(); (tmp_path / "lib/p.step").write_bytes((steps / "part.step").read_bytes())
    monkeypatch.setattr(cad, "CACHE", str(tmp_path / "cache")); monkeypatch.setattr(cad, "_JOBS", {}); monkeypatch.setattr(cad, "_MEMO", {})
    st = json.loads(cad.route_cad(json.dumps({"path": "p.step"}).encode())[2]); t0 = time.time()
    while st["state"] == "working" and time.time() - t0 < 60: time.sleep(0.2); st = json.loads(cad.route_cad(json.dumps({"path": "p.step"}).encode())[2])
    assert st["state"] == "ready" and st["mode"] == "console" and runs(log) == ["freecadcmd"], (st, runs(log))
    size, doc = glb_bounds(cad.route_cadglb(json.dumps({"key": st["key"]}).encode())[2])
    assert size == [0.06, 0.05, 0.04] and [m["name"] for m in doc["materials"]] == ["cad grey"] and doc["materials"][0]["pbrMetallicRoughness"]["metallicFactor"] < 1


def test_the_cache_forgets_what_was_used_longest_ago(tmp_path, monkeypatch):
    monkeypatch.setattr(cad, "CACHE", str(tmp_path)); monkeypatch.setattr(cad, "CACHE_MAX", 2500)
    keys = [f"{i:040x}" for i in range(3)]
    for i, k in enumerate(keys):
        (tmp_path / f"{k}.glb").write_bytes(b"x" * 1000); (tmp_path / f"{k}.json").write_text("{}"); os.utime(tmp_path / f"{k}.glb", (1000 + i, 1000 + i))
    cad.prune(keep=keys[2])
    assert not (tmp_path / f"{keys[0]}.glb").exists() and not (tmp_path / f"{keys[0]}.json").exists() and (tmp_path / f"{keys[1]}.glb").exists() and (tmp_path / f"{keys[2]}.glb").exists()


def test_iges_goes_the_same_way(cadhy, steps, tmp_path):
    port, lib, log, cache = cadhy
    mk = tmp_path / "igs.py"
    mk.write_text(f"import FreeCAD, Part, Import, os\nd = FreeCAD.newDocument('i')\no = d.addObject('Part::Feature', 'b'); o.Shape = Part.makeBox(30, 20, 10)\nImport.export([o], {str(lib / 'models/box.igs')!r})\nos._exit(0)\n")
    subprocess.run([FC["cmd"], str(mk)], capture_output=True, timeout=60)
    assert (lib / "models/box.igs").exists()
    st, _ = until_ready(port, "models/box.igs")
    assert st["state"] == "ready", st
    assert glb_bounds(get(port, "/api/plugin/3d/cadglb", json.dumps({"key": st["key"]}).encode())[1])[0] == [0.03, 0.01, 0.02]
    assert "models/box.igs" in {i["path"]: i for i in json.loads(get(port, "/api/models3d")[1])}


# ---- the browser

def library_tile(page, name): return page.locator(f".card.m3d[aria-label='{name}']")


@pytest.mark.parametrize("cadhy", [{"delay": 2.0}], indirect=True)
@pytest.mark.parametrize("engine", ENGINES)
def test_the_3d_filter_lists_step_files_says_converting_and_turns_them(cadhy, steps, engine):
    port, lib, log, cache = cadhy
    put_steps(lib, steps, "part.step")
    (lib / "models/broken.step").write_text("nonsense " * 50); (lib / "models/empty.step").write_bytes(b"")
    with sync_playwright() as p:
        browser, page, errors = open_library(p, engine, port)
        open_3d(page)
        assert library_tile(page, "part").locator(".pill.kd").text_content() == "STEP"
        # while FreeCAD works (it is slowed to take 2 s more) the tile says so
        page.wait_for_function("() => { const c = [...document.querySelectorAll('.card.m3d')].find(e => e.getAttribute('aria-label') === 'part'); return c && c.dataset.note === 'converting…'; }", timeout=30000)
        # then its turntable is drawn from the converted glb and the tile turns into the picture
        page.wait_for_function("() => { const c = [...document.querySelectorAll('.card.m3d')].find(e => e.getAttribute('aria-label') === 'part'); return c && !c.classList.contains('nosp') && !c.dataset.note; }", timeout=120000)
        sheet = get(port, "/api/sprite?p=models/part.step")
        assert sheet[0] == 200, "the sheet is kept for the STEP file"
        from PIL import Image
        import io
        im = Image.open(io.BytesIO(sheet[1])).convert("RGBA"); cell = im.crop((0, 0, 256, 256))
        assert sum(1 for px in cell.getdata() if px[3] > 128) > 256 * 256 * 0.06, "the model is in the picture"
        # the broken and the empty file say why, in words, and the good one is not touched by them
        page.wait_for_function("() => { const n = e => [...document.querySelectorAll('.card.m3d')].find(c => c.getAttribute('aria-label') === e); return n('broken') && n('broken').dataset.note && n('empty') && n('empty').dataset.note; }", timeout=60000)
        notes = {n: library_tile(page, n).get_attribute("data-note") for n in ("broken", "empty")}
        assert notes["empty"] == "The file is empty" and notes["broken"] in ("FreeCAD could not read this file", "No solids in the file"), notes
        assert library_tile(page, "broken").evaluate("e => e.classList.contains('bad')") and library_tile(page, "part").get_attribute("data-note") is None
        # it turns under the pointer like the others
        card = library_tile(page, "part"); card.scroll_into_view_if_needed(); card.hover()
        page.wait_for_function("() => { const c = [...document.querySelectorAll('.card.m3d')].find(e => e.getAttribute('aria-label') === 'part'); return c.querySelector('.m3s').classList.contains('spinning'); }", timeout=5000)
        assert not errors, errors
        browser.close()
    assert runs(log).count("freecad") == 2, "one run for part.step and one for broken.step (the empty file has none)"


@pytest.mark.parametrize("cadhy", [{"freecad": "none"}], indirect=True)
def test_without_freecad_the_tile_and_the_card_say_so_once(cadhy, steps, tmp_path):
    port, lib, log, cache = cadhy
    put_steps(lib, steps, "part.step", "big.step")
    with sync_playwright() as p:
        browser, page, errors = open_library(p, "chromium", port)
        open_3d(page)
        page.wait_for_function("() => [...document.querySelectorAll('.card.m3d')].filter(c => c.dataset.note === 'FreeCAD is needed to read STEP files').length === 2", timeout=30000)
        page.wait_for_timeout(500)
        assert page.locator(".hytoast, .toast").filter(has_text="FreeCAD is needed").count() <= 1, "the note in the corner is said once, not for each tile"
        browser.close()
        browser, page, frame, errors = open_board(p, "chromium", port)
        cid = new_card(frame)
        with page.expect_file_chooser() as fc:
            frame.click(f".plg[data-id={cid}] .e3-b[data-a=file]")
        fc.value.set_files(str(steps / "part.step"))
        said = "() => document.documentElement.innerHTML.includes('FreeCAD is needed to read STEP files: none found on this Mac')"   # the note is the board's toast: in the frame or the page around it
        for _ in range(200):
            if frame.evaluate(said) or page.evaluate(said): break
            page.wait_for_timeout(100)
        else: raise AssertionError("the card did not say that FreeCAD is missing")
        assert frame.evaluate(f"() => board.items[{json.dumps(cid)}].empty") is True and not frame.locator(f".plg[data-id={cid}] .e3.busy").count(), "the card still asks for a file"
        assert not errors, errors
        browser.close()


@pytest.mark.parametrize("cadhy", [{"delay": 1.5}], indirect=True)
@pytest.mark.parametrize("engine", ENGINES)
def test_a_step_goes_into_an_empty_card_from_the_dialog_the_library_and_the_recent_list(cadhy, steps, engine):
    port, lib, log, cache = cadhy
    put_steps(lib, steps, "part.step")
    with sync_playwright() as p:
        browser, page, frame, errors = open_board(p, engine, port)
        # 1. «Open file…» with a STEP: the card says it converts, then the glb is the file's copy in the project and the model stands on the floor in its own size
        cid = new_card(frame); scene = scene_of(lib, frame, cid)
        wait_file(scene, lambda d: len(d["objects"]) == 2)
        assert "step" in frame.locator(".e3 .e3-fm").inner_text() and ".step" in (frame.locator(".e3 input[type=file]").get_attribute("accept") or "")
        with page.expect_file_chooser() as fc:
            frame.click(f".plg[data-id={cid}] .e3-b[data-a=file]")
        fc.value.set_files(str(steps / "part.step"))
        frame.wait_for_function(f"() => document.querySelector('.plg[data-id={cid}] .e3-fm').textContent.startsWith('Converting part with FreeCAD')", timeout=20000)
        doc = wait_file(scene, lambda d: any(o["src"]["type"] == "file" for o in d["objects"]), t=90)
        o = objects_of_files(doc)[0]
        assert re.fullmatch(r"3d/files/[0-9a-f]{12}/part\.glb", o["src"]["path"]) and (lib / o["src"]["path"]).read_bytes()[:4] == b"glTF", o["src"]
        assert o["name"] == "part" and abs(o["scale"][0] - 1) < 1e-6, "60 x 50 x 40 mm is a real size: kept"
        # the STEP's origin is a corner of the part, so the card moves the part's middle (30, 20 mm) onto the floor's centre and its foot onto the floor
        assert abs(o["loc"][2] - 0.0005) < 1e-4 and abs(o["loc"][0] + 0.03) < 1e-3 and abs(o["loc"][1] + 0.02) < 1e-3, f"on the floor, in the middle: {o['loc']}"
        frame.wait_for_function(f"() => !board.items[{json.dumps(cid)}].empty && !document.querySelector('.plg[data-id={cid}] .e3')", timeout=10000)
        n = len(runs(log))
        # 2. a metre long STEP is fitted to 20 cm, like any large file
        cid2 = new_card(frame); scene2 = scene_of(lib, frame, cid2)
        with page.expect_file_chooser() as fc:
            frame.click(f".plg[data-id={cid2}] .e3-b[data-a=file]")
        fc.value.set_files(str(steps / "big.step"))
        o2 = objects_of_files(wait_file(scene2, lambda d: any(x["src"]["type"] == "file" for x in d["objects"]), t=90))[0]
        assert abs(o2["scale"][0] - 0.2) < 1e-6, o2["scale"]
        # 3. the same STEP chosen again: its glb is already in the project and in the cache, FreeCAD is not run again
        cid3 = new_card(frame); scene3 = scene_of(lib, frame, cid3); k = len(runs(log))
        with page.expect_file_chooser() as fc:
            frame.click(f".plg[data-id={cid3}] .e3-b[data-a=file]")
        fc.value.set_files(str(steps / "part.step"))
        o3 = objects_of_files(wait_file(scene3, lambda d: any(x["src"]["type"] == "file" for x in d["objects"]), t=30))[0]
        assert o3["src"]["path"] == o["src"]["path"] and len(runs(log)) == k, "once per file content"
        # 4. from the library's 3D filter: the glb copy of the library file goes to 3d/converted, and the recent list remembers the STEP file
        cid4 = new_card(frame)
        frame.click(f".plg[data-id={cid4}] .e3-b[data-a=lib]")
        page.wait_for_function("() => document.querySelectorAll('.card.m3d').length >= 3", timeout=15000)
        page.click(".card.m3d[title='models/part.step']")   # (the glb copy that «Open file…» made in 3d/files is a tile named «part» too)
        o4 = objects_of_files(card_doc(lib, frame, cid4, lambda d: len(objects_of_files(d)) == 1))[0]
        assert re.fullmatch(r"3d/converted/[0-9a-f]{8}/part\.glb", o4["src"]["path"]) and (lib / o4["src"]["path"]).read_bytes()[:4] == b"glTF" and o4["name"] == "part", o4
        recent = json.loads((lib.parent / "state/3d-recent.json").read_text())["recent"]
        assert recent[0] == "models/part.step" and o["src"]["path"] in recent, recent
        # 5. the next empty card lists the STEP file among the recent ones, with its turntable (drawn from the converted glb)
        cid5 = new_card(frame)
        frame.wait_for_function(f"() => [...document.querySelectorAll('.plg[data-id={cid5}] .e3-t')].some(t => t.dataset.path === 'models/part.step')", timeout=20000)
        frame.wait_for_function(f"() => !!document.querySelector(\".plg[data-id={cid5}] .e3-t[data-path='models/part.step'] [data-spin]\")", timeout=120000)
        frame.click(f".plg[data-id={cid5}] .e3-t[data-path='models/part.step']")
        o5 = objects_of_files(card_doc(lib, frame, cid5, lambda d: len(objects_of_files(d)) == 1))[0]
        assert o5["src"]["path"] == o4["src"]["path"], "the library file's copy is made once"
        assert not errors, errors
        browser.close()
