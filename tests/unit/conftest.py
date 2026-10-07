"""Fast unit tests of the 3D plugin's Python (cad.py, cad_freecad.py, models.py): no FreeCAD, no Blender, no server, no network.

  python3 -m pytest tests/unit -q

Every test runs with the plugin's HYIMG_* settings cleared, the conversion cache in its own tmp_path and FreeCAD «not installed»
(HYIMG_FREECAD=""), so nothing of the owner's (the library, ~/Library/Caches/Hyimg, the installed plugins, a running Hyimg) is read or written.
"""
import os
import sys
import threading
import types
from pathlib import Path

import pytest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# cad.py reads its settings when it is imported: before that, nothing may point at the owner's folders
for _k in [k for k in os.environ if k.startswith(("HYIMG_", "REVIEW_"))]:
    del os.environ[_k]
os.environ["HYIMG_FREECAD"] = ""                                   # no FreeCAD unless a test makes one
os.environ["HYIMG_CAD_CACHE"] = "/nonexistent/hyimg-unit-cad-cache"   # a write here fails loudly instead of landing in ~/Library

import cad  # noqa: E402
import models  # noqa: E402


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """each test: clean env, a cache of its own, no jobs or hashes left from another test, no config module of a server"""
    for k in [k for k in os.environ if k.startswith(("HYIMG_", "REVIEW_"))]:
        monkeypatch.delenv(k)
    monkeypatch.setenv("HYIMG_FREECAD", "")
    monkeypatch.delitem(sys.modules, "config", raising=False)
    monkeypatch.setattr(cad, "CACHE", str(tmp_path / "cad-cache"))
    monkeypatch.setattr(cad, "_JOBS", {})
    monkeypatch.setattr(cad, "_MEMO", {})
    return tmp_path


class SyncThread:
    """threading.Thread that runs its target inside start(): a job is finished when the route returns"""
    started = []

    def __init__(self, target=None, daemon=None, name=None, **_kw):
        self.target, self.name = target, name

    def start(self):
        SyncThread.started.append(self.name)
        self.target()


@pytest.fixture
def sync_jobs(monkeypatch):
    """cad's background jobs run inline (cad.threading is swapped for a stand-in; the real threading module is untouched)"""
    SyncThread.started = []
    monkeypatch.setattr(cad, "threading", types.SimpleNamespace(Thread=SyncThread, Lock=threading.Lock, get_ident=threading.get_ident))
    return SyncThread.started


@pytest.fixture
def library(tmp_path, monkeypatch):
    lib = tmp_path / "lib"
    lib.mkdir()
    monkeypatch.setenv("HYIMG_LIBRARY_ROOT", str(lib))
    return lib
