"""Light and materials on a built look, non-destructive (owner 2026-10-07: «было бы шикарно, если можно как-то свет тестировать и
материалы»). Runs inside Blender, imported by bridge_server.py. Nothing here writes a .blend of the studio: every change is made on the
look the bridge holds in memory, recorded, and taken back before the next render (restore), so the same built look renders any variant.

A variant as the bridge sends it (bridge.py, variants.plan):

  {"light": {"source": "studio"} | {"source": "angle", "key", "look", "view", "camera"} | {"source": "own", "lights": [<scene.json lights>]},
   "env": 1.0,                                 the world's strength, × (every Background of the world)
   "materials": {"<material name>": {"<param>": value | {"mul": x} | {"tint": [r, g, b]}}}}

  studio  the look's own lights, as the studio's script left them
  angle   the light of the picture's own look (M07 lit each angle its own way): that look is built once for the view and camera, its
          lamps, light cards and world are kept in the bridge's cache as a .blend (capture), and put on the current look in place of its
          own (its lamps and cards hidden, its world swapped)
  own     the scene's own lights from scene.json (the editor's outliner), in place of the look's lamps; the look's world stays

A parameter is an input of the material's main Principled BSDF (the first one from the output). An input without a link takes the value;
an input driven by nodes (the grain of the anodized aluminium) keeps them: a number is multiplied ({"mul": x}), a colour tinted
({"tint": [r, g, b]}), so the texture stays. A plain value on a linked input replaces the link.
"""
import json
import os

import bpy

PARAMS = {   # key: (the Principled input, colour or number)
    "base_color": ("Base Color", "color"), "metallic": ("Metallic", "num"), "roughness": ("Roughness", "num"),
    "coat": ("Coat Weight", "num"), "coat_roughness": ("Coat Roughness", "num"), "specular": ("Specular IOR Level", "num"),
    "ior": ("IOR", "num"), "transmission": ("Transmission Weight", "num"), "emission_color": ("Emission Color", "color"),
    "emission": ("Emission Strength", "num"),
}
OWN = "Hyimg own lights"
OV = {"undo": [], "rigs": {}, "applied": None}   # what to take back, the rigs appended to this build, the last variant's summary


def reset():
    """a new build: everything recorded belonged to the old one"""
    OV.update(undo=[], rigs={}, applied=None)


# ---- materials
def main_principled(mat):
    """the Principled BSDF nearest to the material's output, or None"""
    tree = mat.node_tree if mat and mat.use_nodes else None
    if not tree:
        return None
    outs = [n for n in tree.nodes if n.bl_idname == "ShaderNodeOutputMaterial"]
    out = next((n for n in outs if n.is_active_output), outs[0] if outs else None)
    if not out:
        return None
    seen, queue = set(), [out]
    while queue:
        n = queue.pop(0)
        if n.bl_idname == "ShaderNodeBsdfPrincipled":
            return n
        for i in n.inputs:
            for link in i.links:
                if link.from_node.name not in seen:
                    seen.add(link.from_node.name)
                    queue.append(link.from_node)
    return None


def _value(inp):
    v = inp.default_value
    return [round(float(x), 5) for x in list(v)[:3]] if hasattr(v, "__len__") else round(float(v), 5)


def report(scene=None):
    """the materials of the built look: name, how many objects and which use it, the main Principled's parameters (value, linked)"""
    sc = scene or bpy.context.scene
    users = {}
    for o in sc.objects:
        if o.type == "MESH" and not (o.visible_camera is False and o.name.startswith("C05 ")):
            for s in o.material_slots:
                if s.material:
                    users.setdefault(s.material.name, []).append(o.name)
    out = []
    for name in sorted(users):
        m = bpy.data.materials[name]
        p = main_principled(m)
        params = {}
        if p:
            for key, (inp, _kind) in PARAMS.items():
                i = p.inputs.get(inp)
                if i is not None:
                    params[key] = {"value": None if i.is_linked else _value(i), "linked": i.is_linked}
        out.append({"name": name, "users": len(users[name]), "parts": sorted(set(users[name]))[:12], "principled": p.name if p else None, "params": params})
    return out


def _set_input(tree, node, inp_name, val, kind):
    """one input of one node to a value, a factor or a tint; recorded so restore() takes it back"""
    i = node.inputs.get(inp_name)
    if i is None:
        return False
    if i.is_linked and isinstance(val, dict):
        src = i.links[0].from_socket
        if "mul" in val and kind == "num":
            n = tree.nodes.new("ShaderNodeMath")
            n.operation = "MULTIPLY"
            n.inputs[1].default_value = float(val["mul"])
            n.label = "Hyimg override ×"
        elif "tint" in val and kind == "color":
            n = tree.nodes.new("ShaderNodeMix")
            n.data_type, n.blend_type = "RGBA", "MULTIPLY"
            n.inputs[0].default_value = 1.0
            n.inputs[7].default_value = (*[float(x) for x in val["tint"][:3]], 1.0)
            n.label = "Hyimg override tint"
        else:
            return False
        a, b = (n.inputs[6], n.outputs[2]) if n.bl_idname == "ShaderNodeMix" else (n.inputs[0], n.outputs[0])
        tree.links.new(src, a)
        tree.links.new(b, i)
        OV["undo"].append(("node", tree, n.name, src, i))
        return True
    if isinstance(val, dict):   # a factor or a tint of an input without a link: on its own value
        cur = i.default_value
        if "mul" in val and kind == "num":
            val = float(cur) * float(val["mul"])
        elif "tint" in val and kind == "color":
            val = [float(a) * float(b) for a, b in zip(list(cur)[:3], val["tint"])]
        else:
            return False
    old = tuple(i.default_value) if hasattr(i.default_value, "__len__") else i.default_value
    if i.is_linked:   # a plain value on a driven input replaces the link
        src = i.links[0].from_socket
        tree.links.remove(i.links[0])
        OV["undo"].append(("link", tree, src, i))
    i.default_value = (*[float(x) for x in val[:3]], 1.0) if kind == "color" else float(val)
    OV["undo"].append(("value", i, old))
    return True


def apply_materials(over):
    done, missing = 0, []
    for name, params in (over or {}).items():
        m = bpy.data.materials.get(name)
        p = main_principled(m) if m else None
        if not p:
            missing.append(name)
            continue
        for key, val in (params or {}).items():
            if key in PARAMS and _set_input(m.node_tree, p, PARAMS[key][0], val, PARAMS[key][1]):
                done += 1
    return done, missing


def apply_env(k, scene):
    """the world's strength × k: every Background node of the world"""
    w = scene.world
    if k is None or abs(float(k) - 1) < 1e-6 or not (w and w.node_tree):
        return 0
    n = 0
    for node in w.node_tree.nodes:
        if node.bl_idname == "ShaderNodeBackground":
            n += _set_input(w.node_tree, node, "Strength", {"mul": float(k)}, "num")
    return n


# ---- lights
def is_card(o):
    """a light card of a studio: a mesh the camera does not see, glowing for the product (studio_c05 «diffusion»)"""
    if o.type != "MESH" or o.visible_camera:
        return False
    return any(s.material and s.material.node_tree and any(n.bl_idname == "ShaderNodeEmission" for n in s.material.node_tree.nodes)
               for s in o.material_slots)


def hide_look_lights(scene):
    n = 0
    for o in scene.objects:
        if (o.type == "LIGHT" or is_card(o)) and not o.hide_render:
            OV["undo"].append(("hide", o))
            o.hide_render = True
            n += 1
    return n


def _kelvin(L, d):
    if d.get("temp") and hasattr(L, "use_temperature"):
        L.use_temperature, L.temperature = True, float(d["temp"])


def own_lights(lights, scene):
    """the scene's lights (scene.json, metres, z up, quaternion [w, x, y, z], watts) as Blender lamps, as hyimg_scene.apply_scene makes them"""
    from mathutils import Matrix, Quaternion, Vector
    import math
    col = bpy.data.collections.new(OWN)
    scene.collection.children.link(col)
    OV["undo"].append(("collection", col))
    kinds = {"point": "POINT", "spot": "SPOT", "sun": "SUN", "area": "AREA"}
    for d in lights or []:
        if d.get("hidden"):
            continue
        t = kinds.get(d.get("type"), "POINT")
        L = bpy.data.lights.new("Hyimg · " + str(d.get("name") or d.get("id")), t)
        o = bpy.data.objects.new(L.name, L)
        col.objects.link(o)
        o.matrix_world = Matrix.Translation(Vector(d.get("loc") or [0, 0, 1])) @ Quaternion(d.get("rot") or [1, 0, 0, 0]).to_matrix().to_4x4()
        L.color = [float(x) for x in (d.get("color") or [1, 1, 1])[:3]]
        L.energy = float(d.get("power", 10))
        _kelvin(L, d)
        if t == "AREA":
            L.shape = d.get("shape") or "SQUARE"
            L.size = float(d.get("size") or 0.5)
            L.size_y = float(d.get("size_y") or L.size)
            if hasattr(L, "normalize"):
                L.normalize = True
        elif t in ("POINT", "SPOT"):
            L.shadow_soft_size = float(d.get("size") if d.get("size") is not None else 0.1)
        if t == "SPOT":
            L.spot_size = math.radians(float(d.get("spot_size") or 45))
            L.spot_blend = float(d.get("spot_blend") if d.get("spot_blend") is not None else 0.15)
        if t == "SUN" and d.get("angle") is not None:
            L.angle = float(d["angle"])
    return len(col.objects)


def _real(p):
    return os.path.realpath(bpy.path.abspath(p)) if p else p


def capture_rig(blend_path, json_path, work):
    """the light of the look built now (its lamps, light cards and world) into a .blend of the bridge's cache and a json of what the .blend
    cannot keep (light linking goes by the names of the objects lit); images the build made in its own folder are packed, files of the
    studio are named by their real path. The built look is changed by this (links cleared): the bridge builds anew after it"""
    sc = bpy.context.scene
    objs = [o for o in sc.objects if (o.type == "LIGHT" or is_card(o)) and not o.hide_render]
    meta = {"objects": [], "world": sc.world.name if sc.world else None, "exposure": sc.view_settings.exposure}
    names = lambda c: sorted(x.name for x in c.all_objects) if c else None
    for o in objs:
        ll = o.light_linking
        meta["objects"].append({"name": o.name, "type": o.data.type if o.type == "LIGHT" else "CARD", "receivers": names(ll.receiver_collection),
                                "blockers": names(ll.blocker_collection), "matrix": [list(r) for r in o.matrix_world]})
        ll.receiver_collection = None
        ll.blocker_collection = None
        if o.parent:
            m = o.matrix_world.copy()
            o.parent = None
            o.matrix_world = m
    work = os.path.realpath(work)
    for im in bpy.data.images:
        p = _real(im.filepath)
        if im.packed_file or not p:
            continue
        if p.startswith(work + os.sep) or not os.path.exists(p):
            try:
                im.pack()
            except RuntimeError:
                pass
        else:
            im.filepath = p
    blocks = set(objs) | ({sc.world} if sc.world else set())
    os.makedirs(os.path.dirname(blend_path), exist_ok=True)
    bpy.data.libraries.write(blend_path, blocks, path_remap="ABSOLUTE", fake_user=False)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=1)
    return meta


def _load_rig(blend_path, json_path, scene):
    meta = json.load(open(json_path, encoding="utf-8"))
    want = [x["name"] for x in meta["objects"]]
    with bpy.data.libraries.load(blend_path, link=False) as (src, dst):
        dst.objects = [n for n in want if n in src.objects]
        dst.worlds = [meta["world"]] if meta.get("world") in src.worlds else []
    objs = [o for o in dst.objects if o is not None]
    missing = []
    for o, rec in zip(objs, [x for x in meta["objects"] if x["name"] in want]):
        for field in ("receivers", "blockers"):
            if rec.get(field) is None:
                continue
            col = bpy.data.collections.new(f"Hyimg rig {field} {o.name}")
            for n in rec[field]:
                x = scene.objects.get(n)
                if x is not None:
                    col.objects.link(x)
                else:
                    missing.append(n)
            setattr(o.light_linking, "receiver_collection" if field == "receivers" else "blocker_collection", col)
    world = dst.worlds[0] if dst.worlds else None
    return {"objects": objs, "world": world, "meta": meta, "missing": sorted(set(missing))}


def angle_light(light, scene, cache):
    """the picture's light on the current look: its lamps and world from the rig .blend (loaded once per build), the look's own hidden"""
    key = light["key"]
    rig = OV["rigs"].get(key)
    if rig is None:
        base = os.path.join(cache, "rigs", key)
        rig = OV["rigs"][key] = _load_rig(base + ".blend", base + ".json", scene)
    hide_look_lights(scene)
    for o in rig["objects"]:
        scene.collection.objects.link(o)
        OV["undo"].append(("unlink", scene.collection, o))
    if rig["world"] is not None:
        OV["undo"].append(("world", scene, scene.world))
        scene.world = rig["world"]
    return {"lamps": len(rig["objects"]), "missing_receivers": rig["missing"]}


def rig_paths(cache, key):
    base = os.path.join(cache, "rigs", key)
    return base + ".blend", base + ".json"


def have_rig(cache, key):
    return all(os.path.isfile(p) for p in rig_paths(cache, key))


def prune_rigs(cache, keep=24):
    d = os.path.join(cache, "rigs")
    try:
        files = sorted((os.path.join(d, n) for n in os.listdir(d) if n.endswith(".blend")), key=os.path.getmtime)
    except OSError:
        return
    for p in files[:-keep]:
        for q in (p, p[:-6] + ".json"):
            try:
                os.remove(q)
            except OSError:
                pass


# ---- the variant on the look, and back
def restore():
    """every change of the last apply() taken back, newest first"""
    while OV["undo"]:
        op = OV["undo"].pop()
        try:
            if op[0] == "value":
                op[1].default_value = op[2]
            elif op[0] == "link":
                op[1].links.new(op[2], op[3])
            elif op[0] == "node":
                tree, name, src, inp = op[1:]
                n = tree.nodes.get(name)
                if n is not None:
                    tree.nodes.remove(n)
                tree.links.new(src, inp)
            elif op[0] == "hide":
                op[1].hide_render = False
            elif op[0] == "unlink":
                if op[2].name in op[1].objects:
                    op[1].objects.unlink(op[2])
            elif op[0] == "world":
                op[1].world = op[2]
            elif op[0] == "collection":
                col = op[1]
                for o in list(col.objects):
                    data = o.data
                    bpy.data.objects.remove(o, do_unlink=True)
                    if data is not None and data.users == 0:
                        bpy.data.lights.remove(data)
                bpy.data.collections.remove(col)
        except ReferenceError:   # the thing went with a step of the look's own script (follow_camera rebuilds its cards)
            pass
    OV["applied"] = None


def apply(variant, cache, scene=None):
    """a variant on the built look; returns what was done, for the frame's event and the render's json"""
    sc = scene or bpy.context.scene
    v = variant or {}
    light = v.get("light") or {}
    out = {"light": light.get("source") or "studio"}
    if light.get("source") == "angle":
        out.update(angle_light(light, sc, cache))
    elif light.get("source") == "own":
        out["hidden"] = hide_look_lights(sc)
        out["lamps"] = own_lights(light.get("lights"), sc)
    out["env"] = apply_env(v.get("env"), sc)
    out["materials"], out["missing_materials"] = apply_materials(v.get("materials"))
    OV["applied"] = out
    return out
