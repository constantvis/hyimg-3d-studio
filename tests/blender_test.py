"""Blender side of the scene file, headless: export -> apply into an empty file -> export gives the same scene; a canvas edit (a new
shape, a moved camera, a removed light) lands in Blender. Also writes official.gltf (Blender's own exporter, cameras and lights) for
convert_test.mjs, which checks the canvas maths against it.

  blender -b --factory-startup --python tests/blender_test.py -- <empty folder>
"""
import json, math, os, sys
import bpy
from mathutils import Euler, Vector

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "blender"))
import hyimg_scene as H

out = os.path.abspath(sys.argv[sys.argv.index("--") + 1])
scene = os.path.join(out, "3d/scenes/test/scene.json")
os.makedirs(os.path.dirname(scene), exist_ok=True)
fails = []
def check(ok, what):
    print(("ok   " if ok else "FAIL ") + what)
    if not ok: fails.append(what)

sc = bpy.context.scene
cube = bpy.data.objects["Cube"]
cube.location = (0.3, -0.2, 0.5); cube.rotation_euler = Euler((0.3, -0.5, 1.1)); cube.scale = (0.5, 1.5, 0.25)
cam = bpy.data.objects["Camera"]
cam.location = (2.0, -3.0, 1.2); cam.rotation_euler = Euler((math.radians(78), 0.1, math.radians(33)))
cam.data.lens = 85; cam.data.shift_x = 0.1; cam.data.shift_y = -0.05
sc.render.resolution_x, sc.render.resolution_y = 1080, 1350
for t, loc, rot in (("AREA", (1, -1, 2), (0.6, 0.2, 0.4)), ("SUN", (0, 0, 5), (0.4, -0.3, 0.2)), ("SPOT", (-1, -2, 1.5), (1.1, 0, -0.5))):
    o = bpy.data.objects.new(t.title(), bpy.data.lights.new(t.title(), t)); sc.collection.objects.link(o)
    o.location = loc; o.rotation_euler = Euler(rot)
bpy.data.objects["Area"].data.energy = 40; bpy.data.objects["Area"].data.size = 0.7
bpy.data.objects["Spot"].data.spot_size = math.radians(50)

a = H.export_scene(scene)
json.dump(a, open(os.path.join(out, "first.json"), "w"), ensure_ascii=False)
check(os.path.isfile(os.path.join(out, "3d/scenes/test/scene.glb")), "scene.glb written for the cube")
check(len(a["objects"]) == 1 and a["objects"][0]["src"] == {"type": "node"}, "the cube is a node of scene.glb")
check(len(a["lights"]) == 4 and len(a["cameras"]) == 1, "four lights and a camera listed")
check(a["render"] == {"x": 1080, "y": 1350}, "frame size")
# Blender's own glTF of the same scene, for the canvas maths
bpy.ops.export_scene.gltf(filepath=os.path.join(out, "official.gltf"), export_format="GLTF_SEPARATE", export_cameras=True, export_lights=True, export_extras=True, export_yup=True)

# into an empty file and out again: the same numbers
bpy.ops.wm.read_factory_settings(use_empty=True)
notes = H.apply_scene(scene, fresh=True)
check(not notes, f"applied without notes {notes}")
copy = os.path.join(out, "3d/scenes/test2/scene.json"); os.makedirs(os.path.dirname(copy), exist_ok=True)
b = H.export_scene(copy)
def same(x, y, path=""):
    if isinstance(x, (int, float)) and isinstance(y, (int, float)): return abs(x - y) < 2e-4 or (fails.append(f"{path}: {x} != {y}") and False)
    if isinstance(x, list): return len(x) == len(y) and all(same(p, q, f"{path}[{i}]") for i, (p, q) in enumerate(zip(x, y)))
    if isinstance(x, dict): return all(same(x[k], y.get(k), f"{path}.{k}") for k in x if k not in ("blend_file",))
    return x == y or (fails.append(f"{path}: {x!r} != {y!r}") and False)
for k in ("objects", "lights", "cameras", "render", "active_camera"):
    check(same(a[k], b[k], k), f"round trip keeps {k}")

# a canvas edit: a new box, the camera moved, the sun removed
d = json.load(open(scene))
d["objects"].append({"id": "box1", "name": "Подставка", "src": {"type": "prim", "shape": "box", "size": [0.2, 0.1, 0.05]}, "loc": [0, 0, 0.025], "rot": [1, 0, 0, 0], "scale": [1, 1, 1], "color": "#d0c8b8", "ai": "подиум из мрамора", "shadow_only": True})
d["cameras"][0]["loc"] = [0.5, -1.0, 0.4]
sun = next(l for l in d["lights"] if l["type"] == "sun"); d["lights"].remove(sun); d["removed"].append(sun["id"])
d["by"], d["rev"] = "canvas", d["rev"] + 1
json.dump(d, open(scene, "w"), ensure_ascii=False)
H.apply_scene(scene)
ids = H.by_id()
box = ids.get("box1")
check(box is not None and all(abs(p - q) < 1e-5 for p, q in zip(box.dimensions, (0.2, 0.1, 0.05))), "the box from the canvas is 20 x 10 x 5 cm")
check(box is not None and box.get("hyimg_ai") == "подиум из мрамора", "its text for the image model came along")
check(box is not None and box.is_shadow_catcher, "«только тень» became Blender's shadow catcher")
check(sun["id"] not in ids, "the removed sun is gone")
cam = ids[d["cameras"][0]["id"]]
check((cam.matrix_world.translation - Vector((0.5, -1.0, 0.4))).length < 1e-5, "the camera moved")
c = H.export_scene(scene)
check(any(o["id"] == "box1" and o["src"]["type"] == "prim" and o.get("shadow_only") for o in c["objects"]), "the box goes back out as a shape that only shows its shadow")
print("FAILS:", fails)
sys.exit(1 if fails else 0)
