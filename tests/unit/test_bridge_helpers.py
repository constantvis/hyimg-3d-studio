"""bridge.py without Blender: the frame Blender renders for a card, «is the card's camera still the picture's», the studio's current
look from its newest series (also a driver that builds its folder's name, as M24 does) and from its pointer."""
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))
import bridge as B   # noqa: E402


def test_frame_size_keeps_the_angle_or_follows_the_card():
    assert B.frame_size([480, 600], 320, 400) == [480, 600]
    assert B.frame_size([480, 480], 320, 160) == [480, 240]
    assert B.frame_size([480, 360], 300, 400) == [360, 480]
    assert B.frame_size([1000, 1000], 320, 320, 480) == [480, 480]


def test_same_camera_reads_through_rounding_and_the_quaternion_sign():
    c0 = {"loc": [0.1, -0.2, 0.3], "rot": [0.5, 0.5, -0.5, 0.5], "lens": 185.08, "shift": [0.0095, -0.0275], "fit": "VERTICAL"}
    assert B.same_camera(dict(c0, loc=[0.10001, -0.2, 0.3]), c0)
    assert B.same_camera(dict(c0, rot=[-0.5, -0.5, 0.5, -0.5]), c0)
    assert not B.same_camera(dict(c0, loc=[0.11, -0.2, 0.3]), c0)
    assert not B.same_camera(dict(c0, lens=120), c0)
    assert not B.same_camera(None, c0)


def studio(tmp_path):
    s = tmp_path / "studio"
    (s / "renders/c05-M23R-grain-satin").mkdir(parents=True)
    (s / "renders/c05-M24-palette-views").mkdir(parents=True)
    (s / "base.blend").write_bytes(b"BLENDER")
    (s / "render_c05_M23_grain_satin.py").write_text("output=root/'renders/c05-M23R-grain-satin'\nbpy.ops.render.render(write_still=True)\n")
    (s / "render_c05_M23_silver_update.py").write_text("output=root/'renders/c05-M23R-grain-satin'\nexec(source)\n")
    (s / "render_c05_M24_palette_views.py").write_text("base=base.replace('M23R-grain-satin','M24-palette-views')\nbpy.ops.render.render(write_still=True)\n")
    for d, series in (("c05-M23R-grain-satin", "M23R"), ("c05-M24-palette-views", "M24")):
        for c in ("burgundy", "black"):
            (s / "renders" / d / f"{c}-v01.json").write_text(json.dumps({"model": f"Blender 5.1.1 Cycles {series}", "series": series, "color": c, "inputs": [str(s / "base.blend")]}))
    (s / "renders/c05-M24-palette-views/validation.json").write_text("{}")
    return s


def test_current_look_is_the_newest_series(tmp_path):
    s = studio(tmp_path)
    look = B.current_look(str(s), "burgundy")
    assert (look["id"], look["kind"], look["source"], look["series"]) == ("M24", "driver", "derived", "c05-M24-palette-views")
    assert look["script"].endswith("render_c05_M24_palette_views.py") and look["from"].endswith("burgundy-v01.json")


def test_pointer_wins_and_names_its_look(tmp_path):
    s = studio(tmp_path)
    (s / "looks").mkdir()
    (s / "looks/current.json").write_text(json.dumps({"id": "M25", "blend": "scenes/M25/{colour}.blend", "kind": "blend", "updated": "2026-10-07 10:00"}))
    (s / "scenes/M25").mkdir(parents=True)
    (s / "scenes/M25/burgundy.blend").write_bytes(b"BLENDER")
    look = B.current_look(str(s), "burgundy")
    assert (look["id"], look["kind"], look["source"]) == ("M25", "blend", "pointer")
    k1 = look["key"]
    os.utime(s / "scenes/M25/burgundy.blend", (1, 1))
    assert B.current_look(str(s), "burgundy")["key"] != k1, "a newer saved scene is another look"


def test_route_answers_without_a_scene(tmp_path, monkeypatch):
    monkeypatch.setenv("HYIMG_LIBRARY_ROOT", str(tmp_path))
    st, ctype, body = B.route(json.dumps({"action": "look", "scene": "../x.json"}).encode())
    assert st == 400 and b"bad scene path" in body
    st, ctype, body = B.route(b"[1]")
    assert st == 400
    st, ctype, body = B.route(json.dumps({"action": "status"}).encode())
    assert st == 200 and json.loads(body)["pid"] is None


def test_render_takes_the_cards_output_size_a_preview_stays_small():
    """owner 2026-10-07: the size set in the Scene panel is the size «Render» makes; the preview keeps the card's shape at PREVIEW_LONG"""
    assert B.out_size([2048, 1365], {"res": [1920, 1080], "w": 640, "h": 360}, True) == [1920, 1080]
    assert max(B.out_size([2048, 1365], {"res": [1920, 1080], "w": 640, "h": 360}, False)) == B.PREVIEW_LONG
    assert B.out_size([2048, 1365], {"w": 600, "h": 400}, True) == [2048, 1365]   # no size: the angle's
    assert B.out_size([2048, 1365], {"res": [5, 99999], "w": 600, "h": 400}, True) == [2048, 1365]   # nonsense is ignored
