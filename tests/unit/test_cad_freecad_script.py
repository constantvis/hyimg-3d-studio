"""cad_freecad.py, the script FreeCAD runs: it is run here with stand-in FreeCAD, Import, ImportGui and Part modules, so what it decides
(which reader, how fine a mesh, when to try a coarser one, which answer it writes) is checked without FreeCAD. Its os._exit() is
replaced by a SystemExit for the test's duration, so the test process is never left."""
import json
import os
import runpy
import sys
import types

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(ROOT, "cad_freecad.py")


class Shape:
    def __init__(self, faces=6, diag=100.0, null=False):
        self.Faces = [object()] * faces
        self.BoundBox = diag
        self.tessellated = []
        self._null = null

    def isNull(self):
        return self._null

    def tessellate(self, tol):
        self.tessellated.append(tol)


class Obj:
    def __init__(self, shape, kind="Part::Feature", gui=False):
        self.Shape, self.kind = shape, kind
        self.ViewObject = types.SimpleNamespace(Deviation=None, AngularDeflection=None) if gui else None

    def isDerivedFrom(self, t):
        return t == self.kind


class World:
    """the stand-in FreeCAD: objects the reader 'finds', the glb sizes the writer 'writes' (one per export)"""

    def __init__(self, objects, sizes=(1000,), gui=False, insert_error=None):
        self.objects, self.sizes, self.gui, self.insert_error = objects, list(sizes), gui, insert_error
        self.inserted, self.exports, self.deviations = [], [], []

    def modules(self):
        world = self

        class BoundBox:
            def __init__(self):
                self.DiagonalLength = 0.0

            def add(self, d):
                self.DiagonalLength = d if not self.DiagonalLength else max(self.DiagonalLength, d)

        doc = types.SimpleNamespace(Name="hycad", Objects=self.objects, RootObjects=self.objects)
        fc = types.SimpleNamespace(GuiUp=self.gui, newDocument=lambda name: doc, BoundBox=BoundBox, Version=lambda: ["1", "0", "2", "39319 (Git)"])

        def insert(reader):
            def f(path, docname):
                if world.insert_error:
                    raise world.insert_error
                world.inserted.append((reader, path, docname))
            return f

        def export(objs, out):
            world.deviations.append([o.ViewObject.Deviation for o in objs if o.ViewObject])
            n = world.sizes.pop(0) if world.sizes else 0
            world.exports.append(out)
            if n:
                with open(out, "wb") as fh:
                    fh.write(b"g" * n)

        reader = lambda name: types.SimpleNamespace(insert=insert(name), export=export)
        return {"FreeCAD": fc, "Import": reader("Import"), "ImportGui": reader("ImportGui"), "Part": types.SimpleNamespace(insert=insert("Part"))}


@pytest.fixture
def run_script(tmp_path, monkeypatch):
    def run(world, src="part.step", limit=None):
        for name, mod in world.modules().items():
            monkeypatch.setitem(sys.modules, name, mod)
        res, out = tmp_path / "result.json", tmp_path / "out.glb"
        monkeypatch.setenv("HY_CAD_IN", str(tmp_path / src))
        monkeypatch.setenv("HY_CAD_OUT", str(out))
        monkeypatch.setenv("HY_CAD_RESULT", str(res))
        if limit is not None:
            monkeypatch.setenv("HY_CAD_LIMIT", str(limit))

        def leave(code):
            raise SystemExit(code)
        monkeypatch.setattr(os, "_exit", leave)
        with pytest.raises(SystemExit) as ex:
            runpy.run_path(SCRIPT, run_name="__main__")
        assert ex.value.code == 0
        assert not os.path.exists(str(res) + ".tmp")
        return json.loads(res.read_text())
    return run


def test_a_step_file_is_read_with_the_console_reader_and_tessellated_by_the_models_size(run_script):
    a, b = Shape(faces=6, diag=50.0), Shape(faces=4, diag=200.0)
    w = World([Obj(a), Obj(b)])
    r = run_script(w)
    assert r["ok"] is True and r["mode"] == "console" and r["version"] == "1.0.2"
    assert (r["parts"], r["faces"], r["diagonal_mm"], r["deviation_percent"], r["bytes"]) == (2, 10, 200.0, 0.05, 1000)
    assert w.inserted[0][0] == "Import"
    assert a.tessellated == b.tessellated == [200.0 * 0.05 / 100]


def test_the_gui_build_reads_with_importgui_and_sets_the_deviation_on_the_view(run_script):
    w = World([Obj(Shape(), gui=True)], gui=True)
    r = run_script(w)
    assert r["mode"] == "gui" and w.inserted[0][0] == "ImportGui"
    assert w.deviations == [[0.05]]


def test_an_iges_file_is_read_by_parts_own_reader(run_script):
    w = World([Obj(Shape())])
    run_script(w, src="part.IGES")
    assert w.inserted[0][0] == "Part"


@pytest.mark.parametrize("faces, first", [(8000, 0.05), (8001, 0.15), (40000, 0.15), (40001, 0.5)])
def test_a_model_with_many_faces_starts_with_a_coarser_mesh(run_script, faces, first):
    assert run_script(World([Obj(Shape(faces=faces))]))["deviation_percent"] == first


def test_the_gui_build_makes_a_glb_over_the_limit_again_from_coarser_meshes(run_script):
    w = World([Obj(Shape(), gui=True)], sizes=(5000, 3000, 900), gui=True)
    r = run_script(w, limit=1000)
    assert w.deviations == [[0.05], [0.15], [0.5]]
    assert (r["ok"], r["deviation_percent"], r["bytes"]) == (True, 0.5, 900)


def test_the_coarsest_mesh_is_kept_even_when_it_is_still_over_the_limit(run_script):
    w = World([Obj(Shape(), gui=True)], sizes=(5000, 4000, 3000), gui=True)
    r = run_script(w, limit=1000)
    assert r["ok"] is True and r["bytes"] == 3000 and len(w.exports) == 3


def test_the_console_build_does_not_retry_a_heavy_glb(run_script):
    w = World([Obj(Shape())], sizes=(5000,))
    r = run_script(w, limit=1000)
    assert r["ok"] is True and r["bytes"] == 5000 and len(w.exports) == 1


def test_a_file_with_no_solids_or_surfaces_answers_nogeometry(run_script):
    objs = [Obj(Shape(faces=0)), Obj(Shape(null=True)), Obj(Shape(), kind="App::Annotation")]
    r = run_script(World(objs))
    assert (r["ok"], r["reason"]) == (False, "nogeometry")


@pytest.mark.parametrize("diag", [0.0, 1e10, float("nan")])
def test_a_model_without_a_sensible_size_answers_nogeometry(run_script, diag):
    r = run_script(World([Obj(Shape(diag=diag))]))
    assert (r["ok"], r["reason"]) == (False, "nogeometry") and "no size" in r["error"]


def test_a_writer_that_writes_nothing_answers_unreadable(run_script):
    r = run_script(World([Obj(Shape())], sizes=(0,)))
    assert (r["ok"], r["reason"], r["error"]) == (False, "unreadable", "FreeCAD wrote no glb")


def test_whatever_freecad_throws_becomes_an_unreadable_answer_with_its_message(run_script):
    r = run_script(World([], insert_error=RuntimeError("Cannot read STEP: bad header")))
    assert (r["ok"], r["reason"]) == (False, "unreadable")
    assert r["error"] == "RuntimeError: Cannot read STEP: bad header"
    assert isinstance(r["seconds"], float)
