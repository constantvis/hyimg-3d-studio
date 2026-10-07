"""variants.py, the card's light and material variant on the server's side (owner 2026-10-07: «свет тестировать и материалы»): what is kept
of a variant the page sends, what Blender is asked to do for it, and what the json beside a «Рендер» says of it. No Blender."""
import pytest

import variants as V

LOOK = {"id": "M07", "key": "abc123", "kind": "c05-env", "script": "/studio/studio_c05_M07.py", "blend": "/studio/r29.blend", "env": {"C05_TAG": "M07"}}


def test_clean_keeps_what_blender_can_do_and_drops_the_rest():
    v = V.clean({"id": "v1", "name": "M24 · металл темнее", "light": "angle", "env": 0.8, "junk": 1,
                 "materials": {"Phone | anodized aluminum": {"metallic": 1.4, "roughness": {"mul": 0.5}, "base_color": [0.1, 0.02, 0.05, 1], "colour": "#fff"},
                               "Vase | chrome": {"nothing": 2}, "Phone | logo": {"base_color": {"tint": [0.5, 0.5, 0.5]}}}})
    assert v == {"id": "v1", "name": "M24 · металл темнее", "light": "angle", "env": 0.8,
                 "materials": {"Phone | anodized aluminum": {"metallic": 1.0, "roughness": {"mul": 0.5}, "base_color": [0.1, 0.02, 0.05]},
                               "Phone | logo": {"base_color": {"tint": [0.5, 0.5, 0.5]}}}}
    assert V.clean({"light": "sky"})["light"] == "studio" and "env" not in V.clean({"env": 1})
    assert V.clean(None) is None and V.clean({}) is None
    with pytest.raises(ValueError):
        V.clean({"materials": {"m": {"roughness": "very"}}})
    with pytest.raises(ValueError):
        V.clean({"materials": {"m": {"base_color": [1, 2]}}})


def test_plan_of_each_light():
    assert V.plan(V.clean({"id": "a", "light": "studio"}), which="current", colour="burgundy", view="v01") is None
    a = V.plan(V.clean({"id": "a", "light": "angle"}), which="current", colour="burgundy", view="v01", angle_look=lambda: LOOK, rig_camera=None)
    assert a["light"]["source"] == "angle" and a["light"]["look"] is LOOK and a["light"]["view"] == "v01" and a["light"]["camera"] is None
    moved = V.plan(V.clean({"id": "a", "light": "angle"}), which="current", colour="burgundy", view="v01", angle_look=lambda: LOOK, rig_camera={"loc": [0, -1, 0]})
    assert moved["light"]["key"] != a["light"]["key"], "a turned camera is another capture of the picture's light"
    assert V.plan(V.clean({"id": "a", "light": "angle"}), which="angle", colour="burgundy", view="v01") is None, "the picture's own look has its light"
    with pytest.raises(ValueError):
        V.plan(V.clean({"id": "a", "light": "angle"}), which="current", colour="burgundy", view="v01", angle_look=None)
    lamp = {"id": "l", "name": "Ключ", "type": "area", "loc": [0, 0, 1], "rot": [1, 0, 0, 0], "power": 20, "temp": 3200, "x": 1}
    o = V.plan(V.clean({"id": "a", "light": "own", "env": 0.5}), which="current", colour="c", view="v01", lights=[lamp, {"type": "cloud"}])
    assert o == {"light": {"source": "own", "lights": [{k: v for k, v in lamp.items() if k != "x"}]}, "env": 0.5}


def test_slug_and_sidecar():
    assert V.slug("M24 · свет ракурса") == "m24-свет-ракурса" and V.slug("") == ""
    v = V.clean({"id": "a", "name": "M24 · свет ракурса", "light": "angle", "materials": {"m": {"metallic": 0.5}}})
    p = V.plan(v, which="current", colour="c", view="v02", angle_look=lambda: LOOK)
    s = V.sidecar(v, p)
    assert s["name"] == "M24 · свет ракурса" and s["light"] == "angle" and s["env"] == 1 and s["materials"] == {"m": {"metallic": 0.5}}
    assert s["angle_light"]["look"] == "M07" and s["angle_light"]["view"] == "v02" and s["angle_light"]["camera"] == "the picture's own"
    assert V.sidecar(None, None) is None
