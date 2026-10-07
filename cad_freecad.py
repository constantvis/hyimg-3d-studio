"""STEP and IGES into a glb, run INSIDE FreeCAD (owner 2026-10-06: «STEP support: convert a STEP file once to a 3D model with FreeCAD, which
is already on this Mac, and keep the result, the same way videos already get a WebM copy»). cad.py starts this file as a separate FreeCAD
process (never the owner's open FreeCAD, never its RPC bridge: the process has its own empty user folder) with the paths in the
environment, and reads the answer from a json file, because FreeCAD prints plenty of its own noise on stdout.

  HY_CAD_IN      the .step / .stp / .iges / .igs file
  HY_CAD_OUT     where the glb goes
  HY_CAD_RESULT  where the answer goes: {"ok": true, ...numbers} or {"ok": false, "reason": "...", "error": "..."}
  HY_CAD_LIMIT   the largest glb in bytes: a coarser mesh is tried when the first one is bigger

The glb comes from FreeCAD's own glTF writer (OpenCascade's), so the units are metres, y is up and the parts keep their names and the
document's tree. With the GUI build run off screen (QT_QPA_PLATFORM=offscreen) the STEP's colours come along; the console build
(freecadcmd) cannot read them and gives plain geometry, which cad.py then dresses in a neutral grey.
"""
import json
import os
import time

SRC, OUT, RES = os.environ["HY_CAD_IN"], os.environ["HY_CAD_OUT"], os.environ["HY_CAD_RESULT"]
LIMIT = int(os.environ.get("HY_CAD_LIMIT") or 60 << 20)
T0 = time.time()
# the mesh gets finer with the model's size, not with a fixed millimetre: the deviation is a percent of the model's diagonal; a model with many faces
# starts coarser (its glb would be heavy), and a glb over the limit is made again from the next, coarser, step
STEPS = (0.05, 0.15, 0.5)
ANGLE = 20.0   # degrees between neighbouring normals on a curve


def done(**kw):
    kw.setdefault("seconds", round(time.time() - T0, 2))
    with open(RES + ".tmp", "w", encoding="utf-8") as f:
        json.dump(kw, f)
    os.replace(RES + ".tmp", RES)
    os._exit(0)   # the GUI build would sit in its event loop, the console build waits for nothing: leave at once


try:
    import FreeCAD
    gui = bool(FreeCAD.GuiUp)
    if gui:
        import ImportGui as reader
    else:
        import Import as reader
    doc = FreeCAD.newDocument("hycad")
    if SRC.lower().endswith((".igs", ".iges")):
        import Part
        Part.insert(SRC, doc.Name)   # the STEP reader leaves an IGES file empty: Part's own reader takes it (shapes without the file's colours)
    else:
        reader.insert(SRC, doc.Name)
    parts = [o for o in doc.Objects if o.isDerivedFrom("Part::Feature") and getattr(o, "Shape", None) is not None and not o.Shape.isNull() and o.Shape.Faces]
    if not parts:
        done(ok=False, reason="nogeometry", error="no solids or surfaces in the file")
    box = FreeCAD.BoundBox()
    for o in parts:
        box.add(o.Shape.BoundBox)
    diag = box.DiagonalLength
    faces = sum(len(o.Shape.Faces) for o in parts)
    if not (diag > 0 and diag < 1e9):
        done(ok=False, reason="nogeometry", error=f"the model has no size ({diag})")
    step = 0 if faces <= 8000 else 1 if faces <= 40000 else 2
    size = 0
    while True:
        dev = STEPS[step]
        if gui:
            for o in parts:
                v = getattr(o, "ViewObject", None)
                if v is not None:
                    v.Deviation = dev
                    v.AngularDeflection = ANGLE
        else:
            for o in parts:
                o.Shape.tessellate(diag * dev / 100.0)   # leaves the triangles on the shape, which the glTF writer takes
        if os.path.exists(OUT):
            os.remove(OUT)
        reader.export(doc.RootObjects, OUT)
        size = os.path.getsize(OUT) if os.path.exists(OUT) else 0
        if size == 0:
            done(ok=False, reason="unreadable", error="FreeCAD wrote no glb")
        if size <= LIMIT or step == len(STEPS) - 1 or not gui:
            break   # (the console build keeps the finer triangles it made: a coarser pass would change nothing)
        step += 1
    done(ok=True, mode="gui" if gui else "console", version=".".join(str(v) for v in FreeCAD.Version()[:3]), parts=len(parts), faces=faces,
         diagonal_mm=round(diag, 3), deviation_percent=dev, bytes=size)
except SystemExit:
    raise
except BaseException as ex:   # noqa: BLE001 - whatever FreeCAD throws is the answer
    done(ok=False, reason="unreadable", error=f"{type(ex).__name__}: {str(ex)[:300]}")
