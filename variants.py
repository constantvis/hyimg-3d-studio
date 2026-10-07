"""«Свет и материалы» on the server's side (owner 2026-10-07: «было бы шикарно, если можно как-то свет тестировать и материалы»): a variant
of a 3D card as the page sends it, checked, and turned into what Blender is asked to do (blender/overrides.py applies it in memory).
bridge.py loads this by its path, the tests import it.

A variant lives in scene.json, "variants": [...], and a card shows one (item.variant, its id on the board):

  {"id": "v1a2b3c", "name": "M26 · свет ракурса",
   "light": "studio" | "angle" | "own",       the look's own light, the picture's own (M07's per angle), or the scene's lights
   "env": 1.0,                                 the world's strength × (optional)
   "materials": {"<material name>": {"base_color": [r, g, b] | {"tint": [r, g, b]}, "metallic": 0.8 | {"mul": 0.7}, ...}}}

Colours are linear RGB, as Blender and scene.json keep them. A parameter driven by nodes in the material (its grain) takes a factor or a
tint, so the texture stays; one without takes the value.
"""
import hashlib
import json
import re

LIGHTS = ("studio", "angle", "own")
NUM = {"metallic": (0, 1), "roughness": (0, 1), "coat": (0, 1), "coat_roughness": (0, 1), "specular": (0, 1), "ior": (1, 3),
       "transmission": (0, 1), "emission": (0, 100)}
COLOR = ("base_color", "emission_color")
LIGHT_KEYS = ("id", "name", "type", "loc", "rot", "color", "power", "size", "size_y", "shape", "spot_size", "spot_blend", "angle", "temp", "hidden")


def _num(x, lo, hi):
    if isinstance(x, bool) or not isinstance(x, (int, float)) or x != x:
        raise ValueError(f"not a number: {x!r}")
    return round(min(hi, max(lo, float(x))), 5)


def _rgb(x):
    if not isinstance(x, (list, tuple)) or len(x) < 3:
        raise ValueError(f"not a colour: {x!r}")
    return [_num(v, 0, 100) for v in x[:3]]


def clean_param(key, val):
    if key in NUM:
        if isinstance(val, dict):
            return {"mul": _num(val.get("mul"), 0, 20)}
        return _num(val, *NUM[key])
    if key in COLOR:
        if isinstance(val, dict):
            return {"tint": _rgb(val.get("tint"))}
        return _rgb(val)
    raise ValueError(f"unknown parameter {key}")


def clean(v):
    """the variant as stored and sent, or None; anything unknown is dropped, a bad value is an error"""
    if not v:
        return None
    if not isinstance(v, dict):
        raise ValueError("a variant is an object")
    out = {"id": str(v.get("id") or "")[:40], "name": str(v.get("name") or "")[:80], "light": v.get("light") if v.get("light") in LIGHTS else "studio"}
    if v.get("env") is not None and v.get("env") != 1:
        out["env"] = _num(v["env"], 0, 10)
    mats = {}
    for name, params in (v.get("materials") or {}).items():
        if not isinstance(params, dict) or not isinstance(name, str):
            continue
        p = {k: clean_param(k, x) for k, x in params.items() if k in NUM or k in COLOR}
        if p:
            mats[name[:200]] = p
    if mats:
        out["materials"] = mats
    return out


def own_lights(lights):
    out = []
    for d in lights or []:
        if isinstance(d, dict) and d.get("type") in ("point", "spot", "sun", "area") and isinstance(d.get("loc"), list) and isinstance(d.get("rot"), list):
            out.append({k: d[k] for k in LIGHT_KEYS if k in d})
    return out


def rig_key(angle_look, colour, view, camera):
    """one capture of the picture's light: its look as it is now, the colourway, the view and the camera it follows"""
    raw = json.dumps([angle_look.get("key"), angle_look.get("id"), colour, view, camera], sort_keys=True, default=str)
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def plan(v, *, which, colour, view, angle_look=None, rig_camera=None, lights=None):
    """what Blender does for a clean variant: the light (with what it needs), the world's factor, the materials; None when nothing.
    which: the look the card renders ("angle": the picture's own, whose light is the angle's already)"""
    if not v:
        return None
    out = {}
    src = v.get("light", "studio")
    if src == "angle" and which != "angle":
        if angle_look is None:
            raise ValueError("this camera has no picture of its own: no angle light")
        look = angle_look()
        out["light"] = {"source": "angle", "look": look, "view": view, "camera": rig_camera, "key": rig_key(look, colour, view, rig_camera)}
    elif src == "own":
        out["light"] = {"source": "own", "lights": own_lights(lights)}
    if v.get("env") is not None:
        out["env"] = v["env"]
    if v.get("materials"):
        out["materials"] = v["materials"]
    return out or None


def slug(name):
    """a variant's name in a file name: letters of any alphabet, digits, dashes"""
    s = re.sub(r"[^\w]+", "-", str(name or ""), flags=re.UNICODE).strip("-_").lower()
    return s[:40]


def sidecar(v, p):
    """what the json beside a «Рендер» says of its variant: enough to make it again or hand it on as a recommendation"""
    if not v:
        return None
    light = (p or {}).get("light") or {}
    out = {"id": v.get("id"), "name": v.get("name"), "light": v.get("light", "studio"), "env": v.get("env", 1), "materials": v.get("materials") or {}}
    if light.get("source") == "angle":
        lk = light["look"]
        out["angle_light"] = {"look": lk.get("id"), "script": lk.get("script"), "blend": lk.get("blend"), "env": lk.get("env"), "view": light.get("view"),
                              "camera": light.get("camera") or "the picture's own", "rig": light.get("key")}
    if light.get("source") == "own":
        out["own_lights"] = light.get("lights")
    return out
