"""Pictures of a Blender studio as one 3D scene with a camera per picture (owner 2026-10-06: «put my 3D previews to the right of this
group, where I can switch between Blender and our three.js ... one and the same model»). Run in Blender:

  Blender -b --factory-startup -P tools/studio_angles.py -- --library <library> --scene 3d/scenes/<name>/scene.json \
      --colour burgundy --out renderings <picture.json> ...

For each picture its own look is built the way the studio built it (blender/studio_looks.py, nothing written into the studio), and the
camera the studio's script set is read back: matrix, lens, sensor, fit, shift and frame size, checked against the picture's json. The
scene gets the studio's product geometry once (scene.glb, one object), a camera per picture named «<NN> · <view>» in the pictures'
order, three plain lights for three.js, and {"studio": {...}}: the studio folder, the colourway, where «OK» saves, and per camera the
picture it came from with its frame size, samples and exposure (bridge.py reads it). Writes only the scene's folder in the library.
"""
import json
import os
import re
import sys

import bpy
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "blender"))
sys.path.insert(0, os.path.join(HERE, ".."))
import studio_looks   # noqa: E402
import hyimg_scene    # noqa: E402
import bridge         # noqa: E402  (the look of a picture, as the bridge finds it)

ARGS = sys.argv[sys.argv.index("--") + 1:]


def opt(name, default=None):
    if name in ARGS:
        i = ARGS.index(name)
        v = ARGS[i + 1]
        del ARGS[i:i + 2]
        return v
    return default


LIB = os.path.abspath(opt("--library"))
SCENE = opt("--scene")
COLOUR = opt("--colour")
OUT = opt("--out", "3d/renders")
WORK = opt("--work", os.path.join(os.path.expanduser("~/Library/Caches/Hyimg"), "blender", "angles"))
PICS = ARGS
os.environ["HYIMG_LIBRARY_ROOT"] = LIB


def dress(glb, ns):
    """the glb's materials readable by three.js: the studio's are procedural (their colour comes from nodes the glTF exporter cannot
    follow, so the body and the back came out white); the colourway's palette goes into the base colours, nothing in Blender changes"""
    import struct
    data = open(glb, "rb").read()
    jl, = struct.unpack("<I", data[12:16])
    doc = json.loads(data[20:20 + jl])
    rest = data[20 + jl:]
    pal = (ns.get("PALETTES") or {}).get(COLOUR) or {"body": (0.3, 0.3, 0.3), "back": (0.3, 0.3, 0.3)}
    scale = float(os.environ.get("BODY_SCALE", "1") or 1)
    body = [min(1, c * scale) for c in pal["body"]] + [1]
    plan = {"Phone | anodized aluminum": (body, 1, 0.32), "Phone | glass over reflective colored backing": (list(pal["back"]) + [1], 0.6, 0.4),
            "Camera | black machined bezel": ([0.01, 0.01, 0.01, 1], 0, 0.2), "Phone | off display cover": ([0.004, 0.004, 0.004, 1], 0, 0.05),
            "Vase | polished neutral chrome": ([0.8, 0.8, 0.8, 1], 1, 0.065)}
    for m in doc.get("materials", []):
        if m.get("name") in plan:
            col, metal, rough = plan[m["name"]]
            p = m.setdefault("pbrMetallicRoughness", {})
            p.update(baseColorFactor=col, metallicFactor=metal, roughnessFactor=rough)
    text = json.dumps(doc, separators=(",", ":")).encode()
    text += b" " * (-len(text) % 4)
    out = data[:8] + struct.pack("<I", 12 + 8 + len(text) + len(rest)) + struct.pack("<II", len(text), 0x4E4F534A) + text + rest
    with open(glb, "wb") as f:
        f.write(out)


def main():
    angles, studio, product_names = [], None, None
    for pic in PICS:
        rel = os.path.relpath(os.path.abspath(pic if os.path.isabs(pic) else os.path.join(LIB, pic)), LIB)
        doc = json.load(open(os.path.join(LIB, rel), encoding="utf-8"))
        studio = studio or os.path.dirname(doc["inputs"][0])
        look = bridge.look_from_json(studio, doc, COLOUR, os.path.join(LIB, rel))
        ns, rep = studio_looks.build(look, COLOUR, doc["view"], WORK)
        cam = bpy.context.scene.camera
        diff = max(abs(a - b) for r1, r2 in zip(cam.matrix_world, doc["camera"]) for a, b in zip(r1, r2))
        if diff > 1e-6:
            raise SystemExit(f"{rel}: the built camera differs from the picture's by {diff}")
        res = [bpy.context.scene.render.resolution_x, bpy.context.scene.render.resolution_y]
        if res != doc["resolution"]:
            raise SystemExit(f"{rel}: frame {res} ≠ {doc['resolution']}")
        m = re.match(r"(\d+)", os.path.basename(rel))
        angles.append({"source": rel, "view": doc["view"], "ordinal": int(m.group(1)) if m else len(angles) + 1, "look": look["id"],
                       "matrix": [list(r) for r in cam.matrix_world], "lens": cam.data.lens, "sensor": cam.data.sensor_width,
                       "sensor_h": cam.data.sensor_height, "fit": cam.data.sensor_fit, "shift": [cam.data.shift_x, cam.data.shift_y],
                       "clip": [cam.data.clip_start, cam.data.clip_end], "resolution": res, "samples": doc.get("samples"), "exposure": doc.get("exposure")})
        product_names = product_names or [o.name for o in (ns.get("product") or [o for o in bpy.context.scene.objects if o.type == "MESH"])]
        print("ANGLE", rel, doc["view"], res, cam.data.sensor_fit, rep["seconds"], "s", flush=True)
    # the last built scene keeps only the product: one object of the studio's meshes, as they stand
    sc = bpy.context.scene
    keep = set(product_names)
    for o in list(sc.objects):
        if o.name not in keep:
            bpy.data.objects.remove(o, do_unlink=True)
    root = bpy.data.objects.new("Vase · модель студии", None)
    sc.collection.objects.link(root)
    for name in product_names:
        o = bpy.data.objects[name]
        mw = o.matrix_world.copy()
        o.parent = root
        o.matrix_world = mw
    root["hyimg_ai"] = "наш предмет, геометрия студии Blender, форму и детали не менять"
    for a in angles:
        data = bpy.data.cameras.new(f"{a['ordinal']:02d} · {a['view']}")
        data.lens, data.sensor_width, data.sensor_height, data.sensor_fit = a["lens"], a["sensor"], a["sensor_h"], a["fit"]
        data.shift_x, data.shift_y = a["shift"]
        data.clip_start, data.clip_end = a["clip"]
        o = bpy.data.objects.new(data.name, data)
        sc.collection.objects.link(o)
        o.matrix_world = Matrix(a["matrix"])
        a["object"] = o
    sc.camera = angles[0]["object"]
    sc.render.resolution_x, sc.render.resolution_y = angles[0]["resolution"]
    sc.render.resolution_percentage = 100
    corners = [bpy.data.objects[n].matrix_world @ Vector(c) for n in product_names for c in bpy.data.objects[n].bound_box]
    centre = sum(corners, Vector()) / len(corners)
    for name, loc, power, size in (("Ключевой", (-0.45, -0.55, 0.55), 25, 0.6), ("Заполняющий", (0.7, -0.2, 0.25), 8, 1.0), ("Контровой", (0.2, 0.6, 0.5), 10, 0.5)):
        ld = bpy.data.lights.new(name, "AREA")
        ld.energy, ld.size = power, size
        lo = bpy.data.objects.new(name, ld)
        sc.collection.objects.link(lo)
        lo.location = loc
        lo.rotation_euler = (centre - lo.location).to_track_quat("-Z", "Y").to_euler()
    path = os.path.join(LIB, SCENE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    doc = hyimg_scene.export_scene(path)
    dress(os.path.join(os.path.dirname(path), "scene.glb"), ns)
    by_name = {c["name"]: c for c in doc["cameras"]}
    st = {"folder": studio, "colour": COLOUR, "look": "current", "out": OUT, "angles": {}}
    for a in angles:
        c = by_name[a["object"].name]
        c["render"] = a["resolution"]
        st["angles"][c["id"]] = {k: a[k] for k in ("source", "view", "ordinal", "look", "resolution", "samples", "exposure", "fit", "sensor_h")}
        st["angles"][c["id"]]["camera0"] = {k: c[k] for k in ("loc", "rot", "lens", "sensor", "sensor_h", "fit", "shift")}
    doc["cameras"] = [by_name[a["object"].name] for a in angles]
    doc["active_camera"] = doc["cameras"][0]["id"]
    doc["render"] = {"x": angles[0]["resolution"][0], "y": angles[0]["resolution"][1]}
    doc["world"] = {"color": [0.62, 0.62, 0.62], "strength": 1, "exposure": 0, "look": "AgX"}
    doc["studio"] = st
    doc["note"] = (f"Ракурсы студии Blender ({len(angles)} шт., {COLOUR}): камера каждой карточки = камера картинки {angles[0]['source'].rsplit('/', 2)[0]}. "
                   "Модель = геометрия студии (scene.glb). В Blender карточка рендерит текущие материалы студии (bridge.py), «OK» сохраняет кадр с json. "
                   "Сделано tools/studio_angles.py")
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(doc, ensure_ascii=False, indent=1))
    print("SCENE", SCENE, len(doc["cameras"]), "cameras", flush=True)


main()
