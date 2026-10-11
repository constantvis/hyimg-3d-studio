"""What the 3D plugin makes says how long it took and where it ran (owner 2026-10-11: «затраченное время на генерацию или рендеринг,
обязательный параметр ... либо compute power какой-то условный», «ну это для 3д генераций в том числе»): a Blender render saved into the
library has "seconds" and "compute" in its json, a STEP converted by FreeCAD answers both with its state (hy.py writes them beside the glb).
No Blender, no FreeCAD: the job and the converter are stand-ins."""
import json
import os
import sys
import time
import types
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))
import bridge as B   # noqa: E402
import cad   # noqa: E402
from test_cad_convert import KEY, OK, answer, fake_fc, glb_bytes, run  # noqa: E402,F401  (the fixture)


def test_a_freecad_conversion_says_its_seconds_and_where_it_ran(fake_fc):
    fake_fc(gui=answer(OK, glb_bytes()))
    assert run()["state"] == "ready"
    st = cad._ready(KEY)
    assert st["seconds"] == 1.5 and st["compute"] == "local · FreeCAD 1.0.2 · gui", st


def test_a_blender_render_in_the_library_has_seconds_and_compute(tmp_path, monkeypatch):
    lib, studio = tmp_path / "lib", tmp_path / "lib/studio"
    (lib / "3d/scenes/s").mkdir(parents=True); studio.mkdir()
    (studio / "look.py").write_text("# the look's script\n"); (studio / "base.blend").write_bytes(b"BLENDER")
    frame = tmp_path / "frame.png"; Image.new("RGB", (40, 30), (90, 20, 30)).save(frame)
    monkeypatch.setattr(B, "_library", lambda: str(lib))
    monkeypatch.setattr(B, "_scene", lambda path: ({}, {"folder": str(studio), "colour": "burgundy", "out": "3d/renders"}))
    look = {"script": str(studio / "look.py"), "studio": str(studio), "blend": str(studio / "base.blend"), "kind": "series", "model": ""}
    ev = {"path": str(frame), "res": [40, 30], "samples": 128, "device": "GPU", "seconds": 41.3, "camera": None, "camera_settings": None}
    j = {"scene": "3d/scenes/s/scene.json", "camera_id": "c1", "started": time.time() - 50, "exact_camera": True, "variant": None, "vplan": None,
         "angle": {"ordinal": 1, "view": "front", "source": "angles/front.json"}, "look": {"id": "M30", "source": "series"},
         "request": {"look": look, "device": "GPU", "engine": "CYCLES"}, "frames": [ev], "bridge": types.SimpleNamespace(exe="/Applications/Blender.app")}
    rel = B.save_final(j)["path"]
    meta = json.loads((lib / rel).with_suffix(".json").read_text())
    assert meta["seconds"] == 41.3 and meta["compute"] == "local · Blender Cycles · GPU · 128 samples", meta
    # Blender gave no time: the job's own, from its start to the file, never nothing
    ev.pop("seconds"); rel = B.save_final(j)["path"]
    meta = json.loads((lib / rel).with_suffix(".json").read_text())
    assert isinstance(meta["seconds"], float) and 49 <= meta["seconds"] < 120, meta
