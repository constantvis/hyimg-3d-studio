"""A STEP put on the board by an agent (hy.py do 'model <file>.step') leaves its glb in the library with a json beside it: what it was made
from, how long FreeCAD took and where it ran (owner 2026-10-11: «затраченное время на генерацию или рендеринг, обязательный параметр»,
«ну это для 3д генераций в том числе»). FreeCAD is the one on this Mac, through test_cad.py's counting wrapper; skipped without it.

  HYIMG_REPO=<Hyimg checkout> python3 -m pytest tests/test_cad_run.py
"""
import json
import os
import subprocess
import sys

from test_cad import REPO, cadhy, put_steps, steps  # noqa: F401  (the fixtures; test_cad skips the module without FreeCAD)
from test_cad import pytestmark  # noqa: F401


def test_a_step_from_hy_py_leaves_its_glb_with_seconds_and_compute(cadhy, steps):
    port, lib, log, cache = cadhy
    put_steps(lib, steps, "part.step")
    env = {k: v for k, v in os.environ.items() if not k.startswith("HYIMG_")} | {"HYIMG_PORT": str(port), "PYTHONDONTWRITEBYTECODE": "1"}
    out = subprocess.run([sys.executable, str(REPO / "review/hy.py"), "do", "model models/part.step x=0 y=0", "--page", "main", "--quiet"],
                         env=env, capture_output=True, text=True, timeout=400)
    assert out.returncode == 0, out.stdout + out.stderr
    glbs = list((lib / "3d/converted").rglob("part.glb"))
    assert len(glbs) == 1, glbs
    meta = json.loads(glbs[0].with_name("part.glb.json").read_text())
    assert meta["inputs"] == ["models/part.step"] and meta["model"].startswith("FreeCAD "), meta
    assert isinstance(meta["seconds"], (int, float)) and meta["seconds"] > 0 and meta["compute"].startswith("local · FreeCAD "), meta
