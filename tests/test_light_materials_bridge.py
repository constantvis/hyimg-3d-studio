"""«Свет и материалы» in Blender (owner 2026-10-07: «было бы шикарно, если можно как-то свет тестировать и материалы»): variants.py checks
a card's variant and plans it, blender/overrides.py puts it on the look the bridge holds in memory and takes it back before the next
render. A tiny studio the test makes itself, as test_blender_bridge.py does: a c05-env script (the picture's look, M01) lights each view
with its own lamp and a world colour, a driver (the current look, M02) has a fixed sun and a material whose roughness is driven by a
texture. No real studio is touched.

  python3 -m pytest tests/test_light_materials_bridge.py      (needs Blender in /Applications or HYIMG_BLENDER)

What it checks: the materials list names the look's materials with their Principled parameters, linked or not; a material override
changes the frame and the next render without it is the base frame again (nothing stays on the look); a factor on a linked input keeps
its texture; «Свет ракурса» captures the picture's light once (a rig in the cache) and puts it on the current look; «Свой свет» lights
it with the scene's lights; the world's factor dims it; «Рендер» of a variant is named after it and its json keeps the whole set; the
studio folder is byte for byte the same.
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
sc.render.engine = "CYCLES"; sc.cycles.samples = 8; sc.cycles.device = "CPU"; sc.render.resolution_x = sc.render.resolution_y = 64
sc.cycles.use_denoising = False; sc.cycles.use_adaptive_sampling = False; sc.cycles.seed = 0
for o in [o for o in sc.objects if o.type == "LIGHT"]: bpy.data.objects.remove(o)
sc.world = bpy.data.worlds.new("tent"); sc.world.use_nodes = True
sc.world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.05, 0.05, 0.05, 1)
bpy.ops.wm.save_as_mainfile(filepath=__import__("sys").argv[-1])
"""

# the picture's look: each view lit by its own lamp, placed from the camera, and a brighter, warm world
ENV_SCRIPT = '''import hashlib, json, os
from pathlib import Path
import bpy
from mathutils import Vector
ROOT = Path(__file__).resolve().parent
out = ROOT / "renders" / f"c05-M01-01-{os.environ['PALETTE']}"
out.mkdir(parents=True, exist_ok=True)
sc = bpy.context.scene
cube = bpy.data.objects["Cube"]
mat = bpy.data.materials.new("tiny paint"); mat.use_nodes = True
mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.8, 0.8, 0.8, 1)
cube.data.materials.clear(); cube.data.materials.append(mat)
sc.world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.4, 0.3, 0.2, 1)
VIEWS = {"v01": (7, -7, 5), "v02": (-7, -7, 4)}
for view_name in os.environ["C05_VIEWS"].split(","):
    cam = sc.camera
    cam.location = VIEWS[view_name]
    cam.rotation_euler = (Vector((0, 0, 0)) - cam.location).to_track_quat("-Z", "Y").to_euler()
    old = bpy.data.objects.get("C05 near softbox")
    if old: bpy.data.objects.remove(old)
    data = bpy.data.lights.new("C05 near softbox", "AREA"); data.energy = 900; data.size = 2
    lamp = bpy.data.objects.new("C05 near softbox", data); sc.collection.objects.link(lamp)
    lamp.location = cam.location * 0.6 + Vector((0, 0, 2))
    lamp.rotation_euler = (Vector((0, 0, 0)) - lamp.location).to_track_quat("-Z", "Y").to_euler()
    rec = bpy.data.collections.get("C05 body key receivers") or bpy.data.collections.new("C05 body key receivers")
    if cube.name not in rec.objects: rec.objects.link(cube)
    lamp.light_linking.receiver_collection = rec
    sc.render.filepath = str(out / f"{view_name}.png")
    bpy.ops.render.render(write_still=True)
    meta = {"model": "Blender 5.1.1 Cycles tiny", "tag": "M01", "view": view_name, "inputs": [str(ROOT / "tiny.blend")],
            "camera": [list(r) for r in cam.matrix_world], "resolution": [64, 64], "samples": 8, "exposure": sc.view_settings.exposure,
            "recipe": {k: v for k, v in os.environ.items() if k.startswith("C05_") or k == "PALETTE"},
            "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "camera_settings": {"lens_mm": cam.data.lens, "sensor_width_mm": cam.data.sensor_width, "shift_x": 0, "shift_y": 0}}
    (out / f"{view_name}.json").write_text(json.dumps(meta))
'''

# the current look: a fixed weak sun, and a satin whose roughness a texture drives
DRIVER = '''import json
from pathlib import Path
import bpy
root = Path(__file__).resolve().parent
output = root / "renders/c05-M02-tiny"
output.mkdir(parents=True, exist_ok=True)
sc = bpy.context.scene
cube = bpy.data.objects["Cube"]
mat = bpy.data.materials.new("tiny satin"); mat.use_nodes = True
p = mat.node_tree.nodes["Principled BSDF"]
p.inputs["Base Color"].default_value = (0.6, 0.6, 0.6, 1)
noise = mat.node_tree.nodes.new("ShaderNodeTexNoise")
mat.node_tree.links.new(noise.outputs["Fac"], p.inputs["Roughness"])
cube.data.materials.clear(); cube.data.materials.append(mat)
sun = bpy.data.objects.new("M02 key", bpy.data.lights.new("M02 key", "SUN")); sun.data.energy = 1.5; sc.collection.objects.link(sun)
for view in ["v01"]:
    for color in ["red"]:
        path = output / f"{color}-{view}.png"
        if path.exists() and path.with_suffix(".json").exists():
            continue
        sc.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        path.with_suffix(".json").write_text(json.dumps({"model": "Blender 5.1.1 Cycles M02", "series": "M02", "color": color, "view": view,
            "inputs": [str(root / "tiny.blend")], "camera": [list(r) for r in sc.camera.matrix_world], "resolution": [64, 64], "samples": 8}))
'''


def tree(folder):
    out = {}
    for dp, dn, fn in os.walk(folder):
        for f in fn:
            p = os.path.join(dp, f)
            out[os.path.relpath(p, folder)] = hashlib.sha1(open(p, "rb").read()).hexdigest()
    return out


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    root = tmp_path_factory.mktemp("lightmat")
    studio, lib, cache = root / "studio", root / "lib", root / "cache"
    for d in (studio / "renders", lib / "renderings/M01/red", cache):
        d.mkdir(parents=True)
    make = root / "make.py"; make.write_text(MAKE)
    subprocess.run([EXE, "-b", "--factory-startup", "-P", str(make), "--", str(studio / "tiny.blend")], check=True, capture_output=True)
    (studio / "studio_c05_tiny.py").write_text(ENV_SCRIPT)
    (studio / "render_c05_M02_tiny.py").write_text(DRIVER)
    env = dict(os.environ, PALETTE="red", C05_VIEWS="v01,v02")
    subprocess.run([EXE, "-b", str(studio / "tiny.blend"), "--factory-startup", "-P", str(studio / "studio_c05_tiny.py")], cwd=studio, env=env, check=True, capture_output=True)
    for i, v in enumerate(["v01", "v02"], 1):
        for ext in ("png", "json"):
            (lib / f"renderings/M01/red/{i:02d}-{v}.{ext}").write_bytes((studio / f"renders/c05-M01-01-red/{v}.{ext}").read_bytes())
    subprocess.run([EXE, "-b", str(studio / "tiny.blend"), "--factory-startup", "-P", str(studio / "render_c05_M02_tiny.py")], cwd=studio, check=True, capture_output=True)
    scene = "3d/scenes/tiny/scene.json"
    subprocess.run([EXE, "-b", "--factory-startup", "-P", str(HERE / "tools/studio_angles.py"), "--", "--library", str(lib), "--scene", scene,
                    "--colour", "red", "--out", "renderings", "--work", str(cache / "angles"),
                    "renderings/M01/red/01-v01.json", "renderings/M01/red/02-v02.json"], check=True, capture_output=True)
    os.environ.update(HYIMG_LIBRARY_ROOT=str(lib), HYIMG_BLENDER_CACHE=str(cache), HYIMG_BLENDER_IDLE="600")
    B.CACHE = str(cache)
    before = tree(studio)
    yield {"studio": studio, "lib": lib, "scene": scene, "cache": cache, "before": before}
    B._stop_all()


def call(**kw):
    st, ctype, body = B.route(json.dumps(kw).encode())
    return json.loads(body) if ctype == "application/json" else body


def wait(job, t=120):
    t0 = time.time()
    while time.time() - t0 < t:
        r = call(action="job", job=job)
        if r["state"] not in ("building", "rendering", "saving"):
            return r
        time.sleep(0.1)
    raise AssertionError(f"job {job} did not end")


def cam(world, name="01 · v01"):
    doc = json.loads((world["lib"] / world["scene"]).read_text())
    return doc, next(c for c in doc["cameras"] if c["name"] == name)


def frame(world, **kw):
    """one preview of v01, its last frame's pixels (mean r, g, b) and the job's answer"""
    from PIL import Image, ImageStat
    doc, c = cam(world)
    r = wait(call(action="preview", scene=world["scene"], camera=c["id"], w=64, h=64, engine="CYCLES", **kw)["job"])
    assert r["state"] == "done", r
    ev = B._JOBS[r["job"]]["frames"][-1]
    im = Image.open(ev["path"]).convert("RGB")
    return [round(x, 2) for x in ImageStat.Stat(im).mean], r, im


def test_the_materials_list_comes_from_blender(world):
    doc, c = cam(world)
    r = call(action="materials", scene=world["scene"], camera=c["id"])
    m = {x["name"]: x for x in r["list"]}
    assert "tiny satin" in m, r
    p = m["tiny satin"]["params"]
    assert p["roughness"]["linked"] is True and p["roughness"]["value"] is None, "the texture's input is said to be driven"
    assert p["base_color"]["linked"] is False and p["base_color"]["value"] == [0.6, 0.6, 0.6]
    assert m["tiny satin"]["users"] == 1 and m["tiny satin"]["parts"] == ["Cube"] and m["tiny satin"]["look"] == "M02"


def test_a_material_override_changes_the_frame_and_goes_with_the_next_render(world):
    base, _, im0 = frame(world)
    green, r, _ = frame(world, variant={"id": "a", "name": "зеленый", "materials": {"tiny satin": {"base_color": [0, 0.8, 0], "roughness": {"mul": 0.2}}}})
    assert green[1] - green[0] > base[1] - base[0] + 3, (base, green)
    assert r["variant"]["materials"] == 2 and r["variant"]["missing_materials"] == []
    again, _, im1 = frame(world)
    from PIL import ImageChops
    assert ImageChops.difference(im0, im1).getbbox() is None, "the look is not as it was after the variant"


def test_the_world_factor_dims_the_frame(world):
    base, _, _ = frame(world)
    dim, _, _ = frame(world, variant={"id": "b", "name": "темнее", "env": 0})
    assert sum(dim) < sum(base) - 3, (base, dim)


def test_own_light_lights_the_look_with_the_scenes_lights(world):
    base, _, _ = frame(world)
    lamp = {"id": "l1", "name": "Ключ", "type": "point", "loc": [3, -3, 4], "rot": [1, 0, 0, 0], "color": [1, 0.2, 0.2], "power": 4000, "size": 0.2}
    own, r, _ = frame(world, variant={"id": "c", "name": "свой", "light": "own"}, lights=[lamp])
    assert r["variant"]["light"] == "own" and r["variant"]["lamps"] == 1 and r["variant"]["hidden"] >= 1
    assert own[0] > base[0] + 5, (base, own)
    warm, _, _ = frame(world, variant={"id": "c", "name": "свой", "light": "own"}, lights=[dict(lamp, color=[1, 1, 1], temp=2000)])
    cold, _, _ = frame(world, variant={"id": "c", "name": "свой", "light": "own"}, lights=[dict(lamp, color=[1, 1, 1], temp=12000)])
    assert warm[0] - warm[2] > cold[0] - cold[2] + 5, ("the colour temperature reaches Blender", warm, cold)


def test_angle_light_is_captured_once_and_lights_the_current_look(world):
    base, _, _ = frame(world)
    rigs = Path(B.bridge().cache) / "rigs"   # the bridge's cache of this library
    t0 = time.time()
    lit, r, _ = frame(world, variant={"id": "d", "name": "свет ракурса", "light": "angle"})
    first = time.time() - t0
    assert r["look"]["id"] == "M02", "the current look renders, with the picture's light"
    assert r["rig"] is not None and r["variant"]["light"] == "angle" and r["variant"]["lamps"] == 1 and r["variant"]["missing_receivers"] == []
    assert len(list(rigs.glob("*.blend"))) == 1 and len(list(rigs.glob("*.json"))) == 1
    assert sum(lit) > sum(base) + 10, ("the picture's lamp and warm world light the cube", base, lit)
    t0 = time.time()
    again, r2, _ = frame(world, variant={"id": "d", "name": "свет ракурса", "light": "angle"})
    assert r2["rig"] is None and len(list(rigs.glob("*.blend"))) == 1, "the rig is kept, not captured again"
    assert all(abs(a - b) < 1.5 for a, b in zip(lit, again)), (lit, again)
    print(f"angle light: first {first:.1f} s (capture and two builds), then {time.time() - t0:.1f} s")
    back, _, _ = frame(world)
    assert all(abs(a - b) < 1.5 for a, b in zip(base, back)), ("studio light again", base, back)


def test_render_of_a_variant_is_named_after_it_and_its_json_keeps_the_set(world):
    doc, c = cam(world)
    var = {"id": "e", "name": "M02 · металл темнее", "light": "angle", "env": 0.8, "materials": {"tiny satin": {"metallic": 0.9, "base_color": [0.1, 0.1, 0.1]}}}
    r = wait(call(action="final", scene=world["scene"], camera=c["id"], w=64, h=64, variant=var)["job"])
    assert r["state"] == "done", r
    path = r["saved"]["path"]
    assert path.endswith("01-v01-red-m02-металл-темнее.png"), path
    meta = json.loads((world["lib"] / path).with_suffix(".json").read_text())
    v = meta["variant"]
    assert v["name"] == var["name"] and v["light"] == "angle" and v["env"] == 0.8 and v["materials"] == var["materials"]
    assert v["angle_light"]["look"] == "M01" and v["angle_light"]["view"] == "v01" and v["angle_light"]["rig"]
    assert meta["request"]["variant"]["materials"] == var["materials"], "the reproduce command renders the same set"
    assert meta["variant_applied"]["materials"] == 2


def test_the_studio_folder_is_untouched(world):
    assert tree(world["studio"]) == world["before"]
