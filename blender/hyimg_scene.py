"""Hyimg 3D scene <-> Blender (owner 2026-10-03: no remote control of Blender, the canvas only keeps the data and an agent applies it).

The canvas keeps a scene as 3d/scenes/<name>/scene.json in the library (format in ../scene.js). This script, run by an agent inside
Blender, moves it either way:

  apply   build or update the open .blend from scene.json: objects found by their id (custom property hyimg_id), the missing ones made
          (simple shapes, library models, glb files), positions, lights, cameras, the active camera, the frame size, the world
  export  write scene.json (and scene.glb with Blender's own geometry) from the open .blend; --cards asks the canvas to put one 3D card
          per camera on the board that is open (3d/scenes/inbox.json)

  blender file.blend -b --python hyimg_scene.py -- apply <scene.json> --save
  blender -b --factory-startup --python hyimg_scene.py -- apply <scene.json> --fresh --save-as <new.blend>
  blender file.blend -b --python hyimg_scene.py -- export <scene.json> --cards

Units are metres, z up, rotations quaternions [w, x, y, z] of the world matrix, light power in watts as Blender shows it.
"""
import json, math, os, sys, time, uuid

import bpy, bmesh
from mathutils import Matrix, Quaternion, Vector

FORMAT = "hyimg-scene/1"
MASKS = ["#2f6fe4", "#e4572e", "#3cb44b", "#f032e6", "#ffe119", "#42d4f4", "#911eb4", "#f58231", "#bfef45", "#469990", "#dcbeff", "#9a6324"]
LIGHT_T = {"POINT": "point", "SPOT": "spot", "SUN": "sun", "AREA": "area"}
LIGHT_B = {v: k for k, v in LIGHT_T.items()}
GEOM = {"MESH", "CURVE", "SURFACE", "META", "FONT", "CURVES", "POINTCLOUD", "VOLUME", "GREASEPENCIL"}


def r5(x):   # the same rounding as the canvas (Math.round), so both write the same numbers
    return math.floor(x * 1e5 + 0.5) / 1e5 + 0.0


def rq(q):
    s = -1 if q[0] < 0 else 1
    n = math.sqrt(sum(v * v for v in q)) or 1
    return [r5(v * s / n) for v in q]


def library_root(scene_path):
    """the library folder: the one that holds 3d/scenes/<name>/scene.json"""
    p = os.path.abspath(scene_path).replace(os.sep, "/")
    i = p.rfind("/3d/")
    if i < 0:
        raise SystemExit(f"сцена должна лежать в <библиотека>/3d/...: {scene_path}")
    return p[:i]


def srgb_to_linear(h):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c]


def new_id():
    return uuid.uuid4().hex[:8]


def trs(o):
    loc, rot, sca = o.matrix_world.decompose()
    return [r5(v) for v in loc], rq(list(rot)), [r5(v) for v in sca]


def set_trs(o, d):
    o.matrix_world = Matrix.LocRotScale(Vector(d.get("loc", [0, 0, 0])), Quaternion(d.get("rot", [1, 0, 0, 0])), Vector(d.get("scale", [1, 1, 1])))


def by_id():
    return {o["hyimg_id"]: o for o in bpy.data.objects if "hyimg_id" in o}


def link(o):
    bpy.context.scene.collection.objects.link(o)
    return o


def delete_tree(o):
    for c in list(o.children_recursive):
        bpy.data.objects.remove(c, do_unlink=True)
    bpy.data.objects.remove(o, do_unlink=True)


# ---- simple shapes, the same sizes as on the canvas: size is the full extent along x, y, z in metres
def prim_mesh(name, shape, s):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    if shape == "box":
        bmesh.ops.create_cube(bm, size=1.0)
        bmesh.ops.scale(bm, vec=Vector(s), verts=bm.verts)
    elif shape == "cylinder":
        bmesh.ops.create_cone(bm, cap_ends=True, segments=48, radius1=s[0] / 2, radius2=s[0] / 2, depth=s[2])
    elif shape == "sphere":
        bmesh.ops.create_uvsphere(bm, u_segments=48, v_segments=24, radius=s[0] / 2)
    else:   # plane in xy facing +z
        v = [bm.verts.new((x * s[0] / 2, y * s[1] / 2, 0)) for x, y in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        bm.faces.new(v)
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = shape in ("cylinder", "sphere")
    return me


def paint(o, hexcol):
    """a shape's colour as its own material (Principled base colour)"""
    if not hexcol or o.type != "MESH":
        return
    name = f"hyimg {o.name}"
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    bsdf = m.node_tree.nodes.get("Principled BSDF") if m.node_tree else None
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (*srgb_to_linear(hexcol), 1)
        bsdf.inputs["Roughness"].default_value = 0.6
    m.diffuse_color = (*srgb_to_linear(hexcol), 1)
    o.data.materials.clear()
    o.data.materials.append(m)


FINISH = {"matte": (0.0, 0.7), "glossy": (0.1, 0.2), "metal": (0.95, 0.22)}


def paint_layers(o, layers):
    """the canvas's settings for parts of an object, found by name under it. A path ends with the part's name as in its file;
    «~зеркало» marks the mirrored half, which Blender keeps as the same name with .001: both halves get the setting"""
    notes = []
    for path, ov in sorted(layers.items(), key=lambda kv: kv[0].count("/")):
        base = path.split("/")[-1].replace("~зеркало", "")
        hits = [c for c in o.children_recursive if c.name == base or (c.name.startswith(base + ".") and c.name[len(base) + 1:].isdigit())]
        if not hits:
            notes.append(f"{o.name}: нет слоя {path}")
            continue
        for h in hits:
            if "hidden" in ov:
                h.hide_render = h.hide_viewport = bool(ov["hidden"])
            for m in [h] + list(h.children_recursive):
                if m.type != "MESH" or not (ov.get("color") or ov.get("finish")):
                    continue
                name = f"hyimg {o.name} {base}"
                mat = bpy.data.materials.get(name)
                if mat is None:
                    mat = (m.active_material.copy() if m.active_material else bpy.data.materials.new(name))
                    mat.name = name
                bsdf = mat.node_tree.nodes.get("Principled BSDF") if mat.node_tree else None
                if bsdf and ov.get("color"):
                    bsdf.inputs["Base Color"].default_value = (*srgb_to_linear(ov["color"]), 1)
                if bsdf and ov.get("finish") in FINISH:
                    bsdf.inputs["Metallic"].default_value, bsdf.inputs["Roughness"].default_value = FINISH[ov["finish"]]
                m.data.materials.clear()
                m.data.materials.append(mat)
    return notes


def import_glb(path, name):
    """a glb as one object: its roots under an empty named like the scene object"""
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    roots = [o for o in new if o.parent not in new]
    if len(roots) == 1 and roots[0].type == "EMPTY":
        return roots[0]
    e = link(bpy.data.objects.new(name, None))
    for r in roots:
        mw = r.matrix_world.copy()
        r.parent = e
        r.matrix_world = mw
    return e


# ---- scene.json -> Blender
def apply_scene(scene_path, fresh=False):
    doc = json.load(open(scene_path, encoding="utf-8"))
    root, here = library_root(scene_path), os.path.dirname(os.path.abspath(scene_path))
    if fresh:
        for o in list(bpy.data.objects):
            bpy.data.objects.remove(o, do_unlink=True)
    have = by_id()
    for rid in doc.get("removed", []):
        if rid in have:
            delete_tree(have.pop(rid))
    notes = []
    for i, d in enumerate(doc.get("objects", [])):
        o, src = have.get(d["id"]), d.get("src") or {}
        kind = src.get("type")
        want = {"prim": f"prim:{src.get('shape')}", "model": f"model:{src.get('model')}", "file": f"file:{src.get('path')}"}.get(kind, "")
        if o is not None and kind == "prim" and (o.get("hyimg_src") != want or list(o.get("hyimg_size", [])) != list(src.get("size", []))):
            if o.get("hyimg_src", "").startswith("prim:"):   # a shape that changed size or kind on the canvas is made again
                delete_tree(o)
                o = None
        if o is None:
            try:
                if kind == "prim":
                    o = link(bpy.data.objects.new(d["name"], prim_mesh(d["name"], src.get("shape", "box"), src.get("size", [0.1] * 3))))
                    o["hyimg_size"] = list(src.get("size", []))
                elif kind == "model":
                    o = import_glb(os.path.join(root, "3d/models", src["model"], "assembled.glb"), d["name"])
                elif kind == "file":
                    o = import_glb(os.path.join(root, src["path"]), d["name"])
                elif kind == "node":
                    glb = os.path.join(here, doc.get("glb") or "scene.glb")
                    o = import_glb(glb, d["name"]) if os.path.isfile(glb) else None
                    if o is not None:   # the whole glb came in: keep the node of this object, drop the rest
                        keep = next((c for c in o.children_recursive if c.get("hyimg_id") == d["id"] or c.name == d["name"]), None)
                        if keep is None:
                            delete_tree(o)
                            o = None
                        else:
                            mw = keep.matrix_world.copy()
                            keep.parent = None
                            keep.matrix_world = mw
                            delete_tree(o)
                            o = keep
                if o is None:
                    notes.append(f"{d['name']}: нет геометрии ({kind})")
                    continue
            except FileNotFoundError as e:
                notes.append(f"{d['name']}: нет файла {e}")
                continue
            o["hyimg_id"] = d["id"]
            if want:
                o["hyimg_src"] = want
        o.name = d["name"]
        set_trs(o, d)
        for k in ("color", "mask", "ai"):
            if d.get(k):
                o[f"hyimg_{k}"] = d[k]
        o["hyimg_mask"] = d.get("mask") or MASKS[i % len(MASKS)]
        if d.get("colors"):
            o["hyimg_colors"] = json.dumps(d["colors"], ensure_ascii=False)
        if kind == "prim":
            paint(o, d.get("color"))
        o.hide_render = o.hide_viewport = bool(d.get("hidden"))
        o.hide_select = bool(d.get("locked"))   # locked on the canvas: not picked in the viewport either
        for x in [o] + list(o.children_recursive):   # only its shadow shows: Cycles' shadow catcher
            if hasattr(x, "is_shadow_catcher"):
                x.is_shadow_catcher = bool(d.get("shadow_only"))
        notes += paint_layers(o, d.get("layers") or {})
    for d in doc.get("lights", []):
        o = have.get(d["id"])
        t = LIGHT_B.get(d.get("type"), "POINT")
        if o is None or o.type != "LIGHT":
            o = link(bpy.data.objects.new(d["name"], bpy.data.lights.new(d["name"], t)))
            o["hyimg_id"] = d["id"]
        L = o.data
        if L.type != t:
            L.type = t
        o.name = d["name"]
        set_trs(o, dict(d, scale=[1, 1, 1]))
        L.color = d.get("color", [1, 1, 1])
        # power in watts as Blender shows it, whatever exposure the light has
        L.energy = d.get("power", 10) / (2 ** getattr(L, "exposure", 0))
        if hasattr(L, "use_temperature"):   # the colour temperature in K (the canvas's temp, 2026-10-07): the colour × a black body
            L.use_temperature = bool(d.get("temp"))
            if d.get("temp"):
                L.temperature = float(d["temp"])
        if t == "AREA":
            L.shape = d.get("shape", "SQUARE")
            L.size = d.get("size", 0.5)
            L.size_y = d.get("size_y", L.size)
            if hasattr(L, "normalize"):
                L.normalize = True
        elif t in ("POINT", "SPOT"):
            L.shadow_soft_size = d.get("size", 0.1)
        if t == "SPOT":
            L.spot_size = math.radians(d.get("spot_size", 45))
            L.spot_blend = d.get("spot_blend", 0.15)
        if t == "SUN" and d.get("angle") is not None:
            L.angle = d["angle"]
        o.hide_render = o.hide_viewport = bool(d.get("hidden"))
    for d in doc.get("cameras", []):
        o = have.get(d["id"])
        if o is None or o.type != "CAMERA":
            o = link(bpy.data.objects.new(d["name"], bpy.data.cameras.new(d["name"])))
            o["hyimg_id"] = d["id"]
        c = o.data
        o.name = d["name"]
        set_trs(o, dict(d, scale=[1, 1, 1]))
        c.type = "PERSP"
        c.lens = d.get("lens", 50)
        c.sensor_width = d.get("sensor", 36)
        c.sensor_height = d.get("sensor_h", 24)
        c.sensor_fit = d.get("fit", "AUTO")
        c.shift_x, c.shift_y = (d.get("shift") or [0, 0])[:2]
        c.clip_start, c.clip_end = (d.get("clip") or [0.01, 100])[:2]
    have = by_id()
    sc = bpy.context.scene
    if doc.get("active_camera") in have:
        sc.camera = have[doc["active_camera"]]
    r = doc.get("render") or {}
    if r.get("x") and r.get("y"):
        sc.render.resolution_x, sc.render.resolution_y = int(r["x"]), int(r["y"])
        sc.render.resolution_percentage = 100
    w = doc.get("world") or {}
    if w:
        world = sc.world or bpy.data.worlds.new("World")
        sc.world = world
        bg = next((n for n in world.node_tree.nodes if n.type == "BACKGROUND"), None) if world.node_tree else None
        if bg is not None:
            if not bg.inputs["Color"].is_linked and w.get("color"):
                bg.inputs["Color"].default_value = (*w["color"][:3], 1)
            if w.get("strength") is not None:
                bg.inputs["Strength"].default_value = w["strength"]
        elif w.get("color"):
            world.color = w["color"][:3]
        sc.view_settings.exposure = w.get("exposure", 0)
        try:
            sc.view_settings.view_transform = w.get("look") or "AgX"
        except TypeError:
            notes.append(f"нет преобразования вида {w.get('look')}")
    return notes


# ---- Blender -> scene.json
def units():
    """what the scene file lists: every camera and light, and every object at the top of the tree that has geometry under it
    (an imported model is an empty with its parts under it: one object)"""
    out = []
    for o in bpy.context.scene.objects:
        if o.type in ("CAMERA", "LIGHT"):
            out.append(o)
        elif o.parent is None and (o.type in GEOM or any(c.type in GEOM for c in o.children_recursive)):
            out.append(o)
    return out


def export_scene(scene_path, cards=False):
    old = {}
    try:
        old = json.load(open(scene_path, encoding="utf-8"))
    except (OSError, ValueError):
        pass
    here = os.path.dirname(os.path.abspath(scene_path))
    os.makedirs(here, exist_ok=True)
    olds = {x["id"]: x for k in ("objects", "lights", "cameras") for x in old.get(k, [])}
    sc = bpy.context.scene
    bpy.context.view_layer.update()   # world matrices of what a script just moved
    objs, lights, cams, nodes = [], [], [], []
    for o in units():
        if "hyimg_id" not in o:
            o["hyimg_id"] = new_id()
        oid, prev = o["hyimg_id"], olds.get(o["hyimg_id"], {})
        loc, rot, sca = trs(o)
        if o.type == "CAMERA":
            c = o.data
            cams.append({"id": oid, "name": o.name, "loc": loc, "rot": rot, "lens": r5(c.lens), "sensor": r5(c.sensor_width), "sensor_h": r5(c.sensor_height),
                         "fit": c.sensor_fit, "shift": [r5(c.shift_x), r5(c.shift_y)], "clip": [r5(c.clip_start), r5(c.clip_end)]})
            continue
        if o.type == "LIGHT":
            L = o.data
            power = L.energy * 2 ** getattr(L, "exposure", 0)
            if L.type == "AREA" and hasattr(L, "normalize") and not L.normalize:
                power *= L.area(matrix_world=o.matrix_world)
            d = {"id": oid, "name": o.name, "type": LIGHT_T[L.type], "loc": loc, "rot": rot, "color": [r5(v) for v in L.color], "power": r5(power)}
            if L.type == "AREA":
                d.update(size=r5(L.size), size_y=r5(L.size_y), shape=L.shape)
            elif L.type in ("POINT", "SPOT"):
                d["size"] = r5(L.shadow_soft_size)
            if L.type == "SPOT":
                d.update(spot_size=r5(math.degrees(L.spot_size)), spot_blend=r5(L.spot_blend))
            if L.type == "SUN":
                d["angle"] = r5(L.angle)
            if getattr(L, "use_temperature", False):
                d["temp"] = r5(L.temperature)
            if o.hide_render:
                d["hidden"] = True
            lights.append(d)
            continue
        s = o.get("hyimg_src", "")
        if s.startswith("prim:") and list(o.get("hyimg_size", [])):
            src = {"type": "prim", "shape": s[5:], "size": list(o["hyimg_size"])}
        elif s.startswith("model:"):
            src = {"type": "model", "model": s[6:]}
        elif s.startswith("file:"):
            src = {"type": "file", "path": s[5:]}
        else:
            src = {"type": "node"}
            nodes.append(o)
        d = {"id": oid, "name": o.name, "src": src, "loc": loc, "rot": rot, "scale": sca}
        for k in ("color", "mask", "ai"):
            v = o.get(f"hyimg_{k}") or prev.get(k)
            if v:
                d[k] = v
        for k in ("finish", "layers"):   # the canvas's settings that Blender does not hold on its own: kept from the file
            if prev.get(k):
                d[k] = prev[k]
        if getattr(o, "is_shadow_catcher", False):
            d["shadow_only"] = True
        if o.hide_select:
            d["locked"] = True
        if o.get("hyimg_colors"):
            d["colors"] = json.loads(o["hyimg_colors"])
        if o.hide_render:
            d["hidden"] = True
        objs.append(d)
    doc = dict(old)
    doc.update(format=FORMAT, objects=objs, lights=lights, cameras=cams, by="blender", t=time.strftime("%Y-%m-%d %H:%M:%S"),
               rev=int(old.get("rev", 0)) + 1, render={"x": sc.render.resolution_x * sc.render.resolution_percentage // 100,
                                                       "y": sc.render.resolution_y * sc.render.resolution_percentage // 100},
               blend_file=bpy.data.filepath or old.get("blend_file", ""))
    gone = [i for i in olds if i not in {x["id"] for x in objs + lights + cams}]
    doc["removed"] = sorted(set(old.get("removed", [])) | set(gone))
    if sc.camera is not None and "hyimg_id" in sc.camera:
        doc["active_camera"] = sc.camera["hyimg_id"]
    doc["world"] = dict(old.get("world") or {}, **world_info(sc))
    if nodes:   # Blender's own geometry beside the file; the canvas finds each object by its id in the glb (glTF extras)
        sel = [o for o in bpy.context.selected_objects]
        for o in bpy.context.scene.objects:
            o.select_set(False)
        for o in nodes:
            for x in [o] + list(o.children_recursive):
                x.select_set(True)
        bpy.ops.export_scene.gltf(filepath=os.path.join(here, "scene.glb"), export_format="GLB", use_selection=True, export_extras=True,
                                  export_yup=True, export_apply=True, export_cameras=False, export_lights=False, export_draco_mesh_compression_enable=True)
        for o in bpy.context.scene.objects:
            o.select_set(o in sel)
        doc["glb"], doc["glb_rev"] = "scene.glb", int(old.get("glb_rev", 0)) + 1
    with open(scene_path, "w", encoding="utf-8") as f:   # in place: the folder keeps its time, the library does not rescan
        f.write(json.dumps(doc, ensure_ascii=False, indent=1))
    if cards:
        root = library_root(scene_path)
        rel = os.path.relpath(os.path.abspath(scene_path), root).replace(os.sep, "/")
        with open(os.path.join(root, "3d/scenes/inbox.json"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"id": new_id(), "scene": rel, "cameras": [c["id"] for c in cams], "t": doc["t"]}, ensure_ascii=False))
    return doc


def world_info(sc):
    w, out = sc.world, {"exposure": r5(sc.view_settings.exposure), "look": sc.view_settings.view_transform}
    if w is None:
        return out
    bg = next((n for n in w.node_tree.nodes if n.type == "BACKGROUND"), None) if w.node_tree else None
    if bg is None:
        out.update(color=[r5(v) for v in w.color], strength=1)
        return out
    out["strength"] = r5(bg.inputs["Strength"].default_value)
    col = bg.inputs["Color"]
    if col.is_linked and col.links[0].from_node.type == "TEX_ENVIRONMENT" and col.links[0].from_node.image:
        out["hdri_abs"] = bpy.path.abspath(col.links[0].from_node.image.filepath)
        out["hdri_strength"] = out["strength"]
        mp = next((n for n in w.node_tree.nodes if n.type == "MAPPING"), None)
        out["hdri_rot"] = r5(mp.inputs["Rotation"].default_value[2]) if mp else 0
    else:
        out["color"] = [r5(v) for v in col.default_value[:3]]
    return out


def main(argv):
    if not argv or argv[0] not in ("apply", "export"):
        print(__doc__)
        return 2
    cmd, path = argv[0], os.path.abspath(argv[1])
    if cmd == "apply":
        notes = apply_scene(path, fresh="--fresh" in argv)
        for n in notes:
            print("hyimg:", n)
        if "--save-as" in argv:
            bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(argv[argv.index("--save-as") + 1]))
        elif "--save" in argv and bpy.data.filepath:
            bpy.ops.wm.save_mainfile()
        print(f"hyimg: сцена применена ({len(notes)} замечаний)")
    else:
        doc = export_scene(path, cards="--cards" in argv)
        print(f"hyimg: выгружено {len(doc['objects'])} предметов, {len(doc['lights'])} света, {len(doc['cameras'])} камер")
    return 0


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if args:
        code = main(args)
        if bpy.app.background:
            sys.exit(code)
