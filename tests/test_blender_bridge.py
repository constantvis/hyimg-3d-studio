"""The card in Blender (bridge.py, blender/bridge_server.py, blender/studio_looks.py, tools/studio_angles.py) against a tiny studio the
test makes itself: a cube in a .blend, a c05-env script (environment-driven, renders the views of C05_VIEWS) and a driver script (loops
over colours, skips what is rendered, publishes after its render). No real studio is touched.

  python3 -m pytest tests/test_blender_bridge.py      (needs Blender in /Applications or HYIMG_BLENDER; about a minute)

What it checks: a look is built read-only (the studio folder is byte for byte the same after a build, the scripts' own writes went to the
bridge's spill folder, the driver never reached its publishing); the persistent process starts once, answers, ends on request and when
idle; «OK» with the picture's camera and look gives the studio's picture to the pixel; a camera from the picture's json matrix lands
in Blender as that matrix; a newer render cancels an older one after its current step; a pointer written by the studio
(looks/current.json) is the look of the next render, and the derived look follows the newest series until then.
"""
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import bridge as B   # noqa: E402

EXE = B.blender_exe("Blender 5.1.1")
pytestmark = pytest.mark.skipif(not EXE, reason="no Blender")

MAKE = """
import bpy
sc = bpy.context.scene
sc.render.engine = "CYCLES"; sc.cycles.samples = 4; sc.cycles.device = "CPU"; sc.render.resolution_x = sc.render.resolution_y = 64
sc.cycles.use_denoising = False; sc.cycles.use_adaptive_sampling = False
bpy.ops.wm.save_as_mainfile(filepath=__import__("sys").argv[-1])
"""

ENV_SCRIPT = '''"""a c05-env script in small: the environment says the colour and the views"""
import hashlib, json, os
from pathlib import Path
import bpy
from mathutils import Vector
ROOT = Path(__file__).resolve().parent
out = ROOT / "renders" / f"c05-{os.environ.get('C05_TAG', 'T')}-01-{os.environ['PALETTE']}"
out.mkdir(parents=True, exist_ok=True)
(out / "driver_snapshot.py").write_text(Path(__file__).read_text())
sc = bpy.context.scene
cube = bpy.data.objects["Cube"]
mat = bpy.data.materials.new("tiny paint"); mat.use_nodes = True
mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = {"red": (1, 0, 0, 1), "blue": (0, 0, 1, 1)}[os.environ["PALETTE"]]
cube.data.materials.clear(); cube.data.materials.append(mat)
sc.cycles.samples = int(os.environ.get("C05_SAMPLES", "4"))
sc.render.resolution_x = sc.render.resolution_y = int(os.environ.get("C05_SIZE", "64"))
VIEWS = {"v01": (7, -7, 5), "v02": (-7, -7, 4)}
product = [cube]
for view in os.environ["C05_VIEWS"].split(","):
    cam = sc.camera
    cam.location = VIEWS[view]
    cam.rotation_euler = (Vector((0, 0, 0)) - cam.location).to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = str(out / f"{view}.png")
    bpy.ops.render.render(write_still=True)
    meta = {"model": "Blender 5.1.1 Cycles tiny", "tag": os.environ.get("C05_TAG", "T"), "view": view, "inputs": [str(ROOT / "tiny.blend")],
            "camera": [list(r) for r in cam.matrix_world], "resolution": [sc.render.resolution_x, sc.render.resolution_y], "samples": sc.cycles.samples,
            "exposure": sc.view_settings.exposure, "recipe": {k: v for k, v in os.environ.items() if k.startswith("C05_") or k == "PALETTE"},
            "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "camera_settings": {"lens_mm": cam.data.lens, "sensor_width_mm": cam.data.sensor_width, "shift_x": cam.data.shift_x, "shift_y": cam.data.shift_y}}
    (out / f"{view}.json").write_text(json.dumps(meta))
'''

DRIVER = '''"""a driver in small: loops over colours, skips what is rendered, publishes after its render"""
import json, subprocess
from pathlib import Path
import bpy
root = Path(__file__).resolve().parent
output = root / "renders/c05-M02-tiny"
output.mkdir(parents=True, exist_ok=True)
colors = ["red", "blue"]
sc = bpy.context.scene
cube = bpy.data.objects["Cube"]
mat = bpy.data.materials.new("tiny satin"); mat.use_nodes = True
cube.data.materials.clear(); cube.data.materials.append(mat)
for view in ["v01"]:
    for color in colors:
        path = output / f"{color}-{view}.png"
        if path.exists() and path.with_suffix(".json").exists():
            continue
        mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = {"red": (.5, 0, 0, 1), "blue": (0, 0, .5, 1)}[color]
        sc.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        path.with_suffix(".json").write_text(json.dumps({"model": "Blender 5.1.1 Cycles M02", "series": "M02", "color": color, "view": view,
            "inputs": [str(root / "tiny.blend")], "camera": [list(r) for r in sc.camera.matrix_world], "resolution": [64, 64], "samples": 4}))
        subprocess.run(["touch", str(root / "PUBLISHED")])
'''


def tree(folder):
    """every file of a folder with its bytes' hash: what a build must not change"""
    out = {}
    for dp, dn, fn in os.walk(folder):
        for f in fn:
            p = os.path.join(dp, f)
            out[os.path.relpath(p, folder)] = hashlib.sha1(open(p, "rb").read()).hexdigest()
    return out


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    root = tmp_path_factory.mktemp("bridge")
    studio, lib, cache = root / "studio", root / "lib", root / "cache"
    for d in (studio / "renders", lib / "renderings/M01/red", cache):
        d.mkdir(parents=True)
    make = root / "make.py"; make.write_text(MAKE)
    subprocess.run([EXE, "-b", "--factory-startup", "-P", str(make), "--", str(studio / "tiny.blend")], check=True, capture_output=True)
    (studio / "studio_c05_tiny.py").write_text(ENV_SCRIPT)
    (studio / "render_c05_M02_tiny.py").write_text(DRIVER)
    # the studio renders its first look, M01, two views of the red colourway, as its own scripts do
    env = dict(os.environ, PALETTE="red", C05_VIEWS="v01,v02", C05_TAG="M01", C05_SAMPLES="4", C05_SIZE="64")
    subprocess.run([EXE, "-b", str(studio / "tiny.blend"), "--factory-startup", "-P", str(studio / "studio_c05_tiny.py")], cwd=studio, env=env, check=True, capture_output=True)
    for i, v in enumerate(["v01", "v02"], 1):
        for ext in ("png", "json"):
            (lib / f"renderings/M01/red/{i:02d}-{v}.{ext}").write_bytes((studio / f"renders/c05-M01-01-red/{v}.{ext}").read_bytes())
    # the studio's next step, M02, a driver that renders both colours
    subprocess.run([EXE, "-b", str(studio / "tiny.blend"), "--factory-startup", "-P", str(studio / "render_c05_M02_tiny.py")], cwd=studio, check=True, capture_output=True)
    (studio / "PUBLISHED").unlink()
    # the scene of the pictures' angles, as tools/studio_angles.py makes it for the board
    scene = "3d/scenes/tiny/scene.json"
    subprocess.run([EXE, "-b", "--factory-startup", "-P", str(HERE / "tools/studio_angles.py"), "--", "--library", str(lib), "--scene", scene,
                    "--colour", "red", "--out", "renderings", "--work", str(cache / "angles"),
                    "renderings/M01/red/01-v01.json", "renderings/M01/red/02-v02.json"], check=True, capture_output=True)
    os.environ.update(HYIMG_LIBRARY_ROOT=str(lib), HYIMG_BLENDER_CACHE=str(cache), HYIMG_BLENDER_IDLE="600")
    B.CACHE = str(cache)
    yield {"studio": studio, "lib": lib, "scene": scene, "cache": cache}
    B._stop_all()


def call(**kw):
    st, ctype, body = B.route(json.dumps(kw).encode())
    return json.loads(body) if ctype == "application/json" else body


def wait(job, t=90):
    t0 = time.time()
    while time.time() - t0 < t:
        r = call(action="job", job=job)
        if r["state"] not in ("building", "rendering", "saving"):
            return r
        time.sleep(0.1)
    raise AssertionError(f"job {job} did not end")


def cams(world):
    doc = json.loads((world["lib"] / world["scene"]).read_text())
    return doc, {c["name"]: c for c in doc["cameras"]}


def test_scene_of_angles(world):
    doc, by = cams(world)
    assert [c["name"] for c in doc["cameras"]] == ["01 · v01", "02 · v02"]
    st = doc["studio"]
    assert st["folder"] == str(world["studio"]) and st["colour"] == "red" and st["out"] == "renderings"
    a = st["angles"][by["01 · v01"]["id"]]
    assert a["source"] == "renderings/M01/red/01-v01.json" and a["view"] == "v01" and a["resolution"] == [64, 64] and a["samples"] == 4
    assert (world["lib"] / "3d/scenes/tiny/scene.glb").stat().st_size > 0


def test_derived_look_is_the_newest_series(world):
    look = B.current_look(str(world["studio"]), "red")
    assert (look["id"], look["kind"], look["source"]) == ("M02", "driver", "derived")
    assert look["script"].endswith("render_c05_M02_tiny.py") and look["blend"].endswith("tiny.blend")
    angle = B.look_from_json(str(world["studio"]), json.loads((world["lib"] / "renderings/M01/red/01-v01.json").read_text()), "red", "x")
    assert (angle["id"], angle["kind"]) == ("M01", "c05-env") and angle["script"].endswith("studio_c05_tiny.py")


def test_ok_reproduces_the_picture_and_studio_is_untouched(world):
    before = tree(world["studio"])
    doc, by = cams(world)
    c = by["01 · v01"]
    r = call(action="final", scene=world["scene"], camera=c["id"], w=64, h=64, look="angle")
    r = wait(r["job"])
    assert r["state"] == "done", r
    assert r["exact_camera"] is True and r["saved"]["path"].startswith("renderings/") and "-3d-M01/01-v01-red" in r["saved"]["path"]
    from PIL import Image, ImageChops
    a = Image.open(world["studio"] / "renders/c05-M01-01-red/v01.png").convert("RGB")
    b = Image.open(world["lib"] / r["saved"]["path"]).convert("RGB")
    assert ImageChops.difference(a, b).getbbox() is None, "the OK frame differs from the studio's picture"
    meta = json.loads((world["lib"] / r["saved"]["path"]).with_suffix(".json").read_text())
    assert meta["derived_from"] == "renderings/M01/red/01-v01.json" and meta["look"]["id"] == "M01" and meta["request"]["look"]["kind"] == "c05-env"
    # a second OK never overwrites the first
    r2 = wait(call(action="final", scene=world["scene"], camera=c["id"], w=64, h=64, look="angle")["job"])
    assert r2["saved"]["path"] != r["saved"]["path"]
    assert tree(world["studio"]) == before, "a build changed the studio folder"
    assert not (world["studio"] / "PUBLISHED").exists()
    spill = list((world["cache"]).rglob("spill/renders/c05-M01-01-red/driver_snapshot.py"))
    assert spill, "the script's own write did not go to the spill folder"


def test_process_starts_once_and_answers(world):
    b = B.bridge()
    doc, by = cams(world)
    wait(call(action="preview", scene=world["scene"], camera=by["01 · v01"]["id"], w=64, h=64, engine="CYCLES")["job"])
    pid = b.pid
    assert pid
    wait(call(action="preview", scene=world["scene"], camera=by["02 · v02"]["id"], w=64, h=64, engine="CYCLES")["job"])
    assert b.pid == pid, "a second request started another Blender"
    s = b.send({"cmd": "ping"})
    pong = json.loads(s.makefile().readline()); s.close()
    assert pong["ev"] == "pong" and pong["pid"] == pid
    assert call(action="status")["pid"] == pid


def test_camera_from_the_json_matrix(world):
    """the current look (M02, another script) at the picture's camera: Blender gets the json's matrix, to the float"""
    doc, by = cams(world)
    r = wait(call(action="preview", scene=world["scene"], camera=by["02 · v02"]["id"], w=64, h=64, engine="CYCLES")["job"])
    assert r["state"] == "done" and r["look"]["id"] == "M02"
    ev = B._JOBS[r["job"]]["frames"][-1]
    want = json.loads((world["lib"] / "renderings/M01/red/02-v02.json").read_text())["camera"]
    assert max(abs(a - b) for r1, r2 in zip(ev["camera"], want) for a, b in zip(r1, r2)) < 1e-6
    # a turned camera: the card's own location and turn
    moved = dict(by["02 · v02"], loc=[0, -9, 3])
    r = wait(call(action="preview", scene=world["scene"], camera=moved["id"], cam=moved, w=64, h=64, engine="CYCLES")["job"])
    assert r["exact_camera"] is False
    ev = B._JOBS[r["job"]]["frames"][-1]
    assert [round(ev["camera"][i][3], 4) for i in range(3)] == [0, -9, 3]


def test_a_newer_render_cancels_the_older(world, monkeypatch):
    doc, by = cams(world)
    monkeypatch.setitem(B.STEPS, "CYCLES", [1, 20000, 20000])   # the second step outlasts the next request
    first = call(action="preview", scene=world["scene"], camera=by["01 · v01"]["id"], w=64, h=64, engine="CYCLES")["job"]
    t0 = time.time()
    while call(action="job", job=first)["frames"] < 1 and time.time() - t0 < 60:
        time.sleep(0.05)
    monkeypatch.setitem(B.STEPS, "CYCLES", [1])
    second = call(action="preview", scene=world["scene"], camera=by["02 · v02"]["id"], w=64, h=64, engine="CYCLES")["job"]
    r1 = wait(first); assert r1["state"] == "cancelled", (r1, [(f["samples"], f["seconds"]) for f in B._JOBS[first]["frames"]])
    assert wait(second)["state"] == "done"


def test_pointer_wins_and_its_change_is_seen(world):
    studio = world["studio"]
    (studio / "looks").mkdir()
    try:
        (studio / "looks/current.json").write_text(json.dumps({"id": "M03", "kind": "driver", "blend": "tiny.blend", "script": "render_c05_M02_tiny.py", "updated": "now"}))
        a = call(action="look", scene=world["scene"])
        assert (a["id"], a["source"]) == ("M03", "pointer")
        doc, by = cams(world)
        r = wait(call(action="preview", scene=world["scene"], camera=by["01 · v01"]["id"], w=64, h=64, engine="CYCLES")["job"])
        assert r["state"] == "done" and r["look"]["id"] == "M03" and r["built"] is not None, "a new look is built for the next frame"
        time.sleep(0.01)
        (studio / "looks/current.json").write_text(json.dumps({"id": "M04", "kind": "driver", "blend": "tiny.blend", "script": "render_c05_M02_tiny.py", "updated": "later"}))
        b = call(action="look", scene=world["scene"])
        assert b["id"] == "M04" and b["key"] != a["key"]
    finally:
        for p in (studio / "looks").iterdir():
            p.unlink()
        (studio / "looks").rmdir()


def test_stop_ends_the_process(world):
    b = B.bridge()
    pid = b.pid or 0
    b.stop()
    assert b.pid is None
    if pid:
        with pytest.raises(OSError):
            os.kill(pid, 0)


def test_idle_and_orphan_end_by_themselves(world, tmp_path):
    """the Blender side ends when idle, and when its parent is gone"""
    port_file = tmp_path / "port.json"
    env = dict(os.environ, HYIMG_BRIDGE_TOKEN="t")
    p = subprocess.Popen([EXE, "-b", "--factory-startup", "-P", str(HERE / "blender/bridge_server.py"), "--", "--port-file", str(port_file),
                          "--idle", "2", "--cache", str(tmp_path)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        assert p.wait(40) == 0
    finally:
        if p.poll() is None:
            p.kill()
    gone = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(0.5)"])
    q = subprocess.Popen([EXE, "-b", "--factory-startup", "-P", str(HERE / "blender/bridge_server.py"), "--", "--port-file", str(tmp_path / "p2.json"),
                          "--parent", str(gone.pid), "--idle", "600", "--cache", str(tmp_path)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    gone.wait()
    try:
        assert q.wait(40) == 0
    finally:
        if q.poll() is None:
            q.kill()
