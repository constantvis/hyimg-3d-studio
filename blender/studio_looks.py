"""A Blender studio's look, built the way the studio's own scripts build it, read only (owner 2026-10-06: «I spin and turn the 3D card and
switch from three.js to Blender ... when I press OK I get the render like in the pictures ... use one and the same model with the materials
that are changing in parallel»). Runs inside Blender, imported by bridge_server.py.

A look is a record (bridge.py writes it, from the studio's pointer file looks/current.json or derived from its newest render's json):

  {"id": "M07", "kind": "c05-env" | "driver", "studio": <studio folder>, "blend": <.blend the script runs on>, "script": <the script>,
   "env": {<the recipe's environment>}, "overlay": <folder of frozen copies that win over the studio's files> | null,
   "colour_var": "color", "view_var": "view"}

  c05-env  a studio_c05_*.py script driven by environment variables (C05_*, PALETTE, EXPOSURE, ...): it renders C05_VIEWS one by one.
           It is run with the views of the picture's own run (its recipe's C05_VIEWS), the renders of the views before the asked one
           skipped, so whatever an earlier view leaves behind is there as it was, in a shadow folder (below), and stopped at the render
           of the asked view. A view the run did not have is run alone.
  driver   a render_c05_M*.py script that loops over colours and views (for color in colors, for color, view, kind in cases): the
           loops are cut to the colour and view asked for (the first element when the loop has no such one), «skip what is already
           rendered» is dropped, and it is stopped at its first render.
  blend    a scene the studio saved with its materials ("blend" may name {colour}): opened, nothing run.

Either way the scene is then exactly what the studio's script would have rendered; the bridge changes only what it is asked to (the
camera, the frame size, the engine and samples) and renders into its own cache.

Nothing is written into the studio folder: the studio's scripts write their logs, passes and json beside their renders, and the
c05 base paints its light tent into environment/ through Blender (image.save, out of Python's reach). So during a build
  - every write from Python whose real path is in the studio goes to the build's spill folder instead (open, pathlib, os, shutil);
    a read of such a file sees what the build wrote;
  - a c05-env script runs from a shadow folder: its own copy of the script (so ROOT, the folder of __file__, is the shadow), every other
    entry of the studio a symlink, and environment/ and renders/ real folders of symlinks, so what Blender itself writes there stays
    in the shadow;
  - subprocess calls and network writes are refused (a driver publishes to the board after its render, which is never reached),
    bpy.ops.wm.save_* does nothing, bpy.ops.render.render ends the build.
The studio's .blend files are opened, never saved.
"""
import ast
import builtins
import contextlib
import io
import os
import shutil
import subprocess
import sys
import time
import urllib.request

import bpy


class Built(Exception):
    """the script reached its render: the scene is built"""


def _real(p):
    return os.path.realpath(os.fspath(p))


class Sandbox:
    def __init__(self, studio, spill):
        self.studio, self.spill, self.redirected, self.skip = _real(studio), spill, [], 0

    def _in(self, r):
        return r == self.studio or r.startswith(self.studio + os.sep)

    def target(self, p):
        """where a write to p goes: p itself, or its place in the spill folder when it would land in the studio"""
        r = _real(p)
        if not self._in(r):
            return p
        q = os.path.join(self.spill, os.path.relpath(r, self.studio))
        os.makedirs(os.path.dirname(q), exist_ok=True)
        self.redirected.append(os.path.relpath(r, self.studio))
        return q

    def source(self, p):
        """what a read of p sees: this build's own copy when it wrote one"""
        if isinstance(p, int):
            return p
        r = _real(p)
        if self._in(r):
            q = os.path.join(self.spill, os.path.relpath(r, self.studio))
            if os.path.exists(q):
                return q
        return p


@contextlib.contextmanager
def guard(sb):
    import pathlib
    saved = {}

    def patch(obj, name, fn):
        saved[(obj, name)] = getattr(obj, name)
        setattr(obj, name, fn)

    real_open = io.open

    def g_open(file, mode="r", *a, **k):
        if isinstance(file, (str, bytes, os.PathLike)):
            file = sb.target(file) if any(c in mode for c in "wax+") else sb.source(file)
        return real_open(file, mode, *a, **k)

    def g_mkdir(self, mode=0o777, parents=False, exist_ok=False):
        if sb._in(_real(self)):
            if not os.path.isdir(self):   # a folder the studio has is used as it is, a new one is made in the spill folder
                real_makedirs(os.path.join(sb.spill, os.path.relpath(_real(self), sb.studio)), exist_ok=True)
            return
        return saved[(pathlib.Path, "mkdir")](self, mode, parents, exist_ok)

    real_makedirs = os.makedirs

    def g_makedirs(name, mode=0o777, exist_ok=False):
        if sb._in(_real(name)):
            if os.path.isdir(name):
                if exist_ok:
                    return
            return real_makedirs(os.path.join(sb.spill, os.path.relpath(_real(name), sb.studio)), exist_ok=True)
        return real_makedirs(name, mode, exist_ok)

    def two(fn):
        def g(src, dst, *a, **k):
            return fn(sb.source(src), sb.target(dst), *a, **k)
        return g

    def gone(fn):
        def g(p, *a, **k):
            if sb._in(_real(p)):
                q = sb.source(p)
                return fn(q, *a, **k) if q != p else None   # only this build's own copy goes
            return fn(p, *a, **k)
        return g

    def refused(what):
        def g(*a, **k):
            raise PermissionError(f"{what} is not run while a studio look is built (Hyimg bridge)")
        return g

    real_urlopen = urllib.request.urlopen

    def g_urlopen(url, data=None, *a, **k):
        if data is not None or (isinstance(url, urllib.request.Request) and (url.data is not None or url.get_method() != "GET")):
            raise PermissionError("network writes are not made while a studio look is built (Hyimg bridge)")
        return real_urlopen(url, data, *a, **k)

    ops = sys.modules["bpy.ops"]
    real_sub = ops._bpy_ops_submodule__getattr__

    def stop(*a, **k):
        if sb.skip > 0:   # an earlier view of the same run: its state is kept, its render is not made
            sb.skip -= 1
            return {"FINISHED"}
        raise Built()

    def nothing(*a, **k):
        return {"CANCELLED"}

    def g_sub(module, func):
        if (module, func) == ("render", "render"):
            return stop
        if module == "wm" and func.startswith(("save", "open")):
            return nothing
        return real_sub(module, func)

    try:
        patch(io, "open", g_open)
        patch(builtins, "open", g_open)
        patch(pathlib.Path, "mkdir", g_mkdir)
        patch(os, "makedirs", g_makedirs)
        for name in ("replace", "rename"):
            patch(os, name, two(getattr(os, name)))
        for name in ("remove", "unlink"):
            patch(os, name, gone(getattr(os, name)))
        for name in ("copy", "copy2", "copyfile", "move"):
            patch(shutil, name, two(getattr(shutil, name)))
        patch(shutil, "rmtree", refused("shutil.rmtree"))
        for name in ("run", "Popen", "call", "check_call", "check_output"):
            patch(subprocess, name, refused("subprocess." + name))
        patch(urllib.request, "urlopen", g_urlopen)
        patch(ops, "_bpy_ops_submodule__getattr__", g_sub)
        yield sb
    finally:
        for (obj, name), v in saved.items():
            setattr(obj, name, v)


def make_shadow(studio, entry, dest, overlay=None):
    """the folder a c05-env script runs from: its own copy of the script, symlinks to everything else of the studio (the overlay's frozen
    copies first), environment/ and renders/ as real folders of symlinks. Made fresh for every build: new renders appear in it."""
    if os.path.isdir(dest):
        shutil.rmtree(dest)
    os.makedirs(dest)
    over = {n: os.path.join(overlay, n) for n in os.listdir(overlay)} if overlay and os.path.isdir(overlay) else {}
    for name in os.listdir(studio):
        if name.startswith("."):
            continue
        src = over.get(name, os.path.join(studio, name))
        if name in ("environment", "renders") and os.path.isdir(src):
            os.makedirs(os.path.join(dest, name))
            for sub in os.listdir(src):
                os.symlink(os.path.join(src, sub), os.path.join(dest, name, sub))
        elif name != os.path.basename(entry):
            os.symlink(src, os.path.join(dest, name))
    for name, src in over.items():   # frozen files the studio no longer has
        if not os.path.lexists(os.path.join(dest, name)) and name != os.path.basename(entry):
            os.symlink(src, os.path.join(dest, name))
    script = over.get(os.path.basename(entry), entry)
    shutil.copy2(script, os.path.join(dest, os.path.basename(entry)))
    return os.path.join(dest, os.path.basename(entry))


def pick(items, spec):
    """one element of a driver's loop: the one whose loop variables have the asked values, the first ones in spec first; [] -> []"""
    items = list(items)
    for i, want in spec:
        got = [x for x in items if (x if i is None else x[i]) == want]
        if got:
            items = got
    return items[:1]


class _Cut(ast.NodeTransformer):
    """a driver's loops cut to one colour and one view (for color in colors, for color, view, kind in cases); «skip what is rendered»
    dropped"""
    def __init__(self, picks):
        self.picks = picks   # [(loop variable, wanted value)], the first one wins

    def visit_For(self, node):
        self.generic_visit(node)
        t = node.target
        names = [t.id] if isinstance(t, ast.Name) else [e.id if isinstance(e, ast.Name) else None for e in t.elts] if isinstance(t, ast.Tuple) else []
        spec = [(None if isinstance(t, ast.Name) else names.index(var), want) for var, want in self.picks if var in names and want is not None]
        if spec:
            node.iter = ast.Call(ast.Name("_hy_pick", ast.Load()), [node.iter, ast.Constant(tuple(tuple(x) for x in spec))], [])
        return node

    def visit_If(self, node):
        self.generic_visit(node)
        if len(node.body) == 1 and isinstance(node.body[0], ast.Continue) and "exists" in ast.unparse(node.test):
            return None
        return node


def driver_source(path, picks):
    tree = ast.parse(open(path, encoding="utf-8").read(), filename=path)
    keep = []
    for node in tree.body:   # the check that the board runs for this library: not ours to make
        if isinstance(node, ast.With) and "urlopen" in ast.unparse(node.items[0].context_expr):
            continue
        keep.append(node)
    tree.body = keep
    tree = _Cut(list(picks.items())).visit(tree)
    ast.fix_missing_locations(tree)
    return compile(tree, path, "exec")


BASE_ENV = dict(os.environ)


def build(look, colour, view, work):
    """open the look's .blend and run its script up to its render; returns (namespace, report). work: this build's folder (spill, shadow)"""
    t0 = time.time()
    os.makedirs(work, exist_ok=True)
    spill = os.path.join(work, "spill")
    if os.path.isdir(spill):
        shutil.rmtree(spill)
    os.makedirs(spill)
    studio = look["studio"]
    look = dict(look, blend=look["blend"].replace("{colour}", colour or ""))
    bpy.ops.wm.open_mainfile(filepath=look["blend"], load_ui=False)
    env = dict(BASE_ENV)
    env.update({k: str(v) for k, v in (look.get("env") or {}).items()})
    skip = 0
    if look["kind"] == "c05-env":
        # the views the studio rendered in one run, in order: the scene is built through the earlier ones (their renders skipped), so
        # whatever one view leaves behind for the next is there as it was
        run = [v for v in str(env.get("C05_VIEWS", "")).split(",") if v]
        if view in run:
            skip = run.index(view)
        else:
            env["C05_VIEWS"] = view
        env["C05_SAVE_ONLY"] = "0"
        if colour:
            env["PALETTE"] = colour
    os.environ.clear()
    os.environ.update(env)
    sb = Sandbox(studio, spill)
    sb.skip = skip
    if look["kind"] == "c05-env":
        entry = make_shadow(studio, look["script"], os.path.join(work, "shadow"), look.get("overlay"))
        code = compile(open(entry, encoding="utf-8").read(), entry, "exec")
    elif look["kind"] == "driver":
        entry = look["script"]
        code = driver_source(entry, {look.get("colour_var", "color"): colour, look.get("view_var", "view"): view})
    elif look["kind"] == "blend":   # a scene the studio saved with its materials (scenes/M24/<colour>.blend): nothing to run
        entry, code = look["blend"], None
    else:
        raise ValueError(f"unknown look kind {look['kind']}")
    ns = {"__name__": "__main__", "__file__": entry, "__builtins__": builtins, "_hy_pick": pick}
    built = code is None
    with guard(sb):
        try:
            if code is not None:
                exec(code, ns)
        except Built:
            built = True
        except SystemExit as e:
            raise RuntimeError(f"the look's script ended before its render (exit {e.code})") from None
    if not built:
        raise RuntimeError("the look's script ended without a render: nothing to build")
    bpy.context.view_layer.update()   # what the render would evaluate first: a location set just before it is in the matrices now
    sc = bpy.context.scene
    cam = sc.camera
    report = {"seconds": round(time.time() - t0, 2), "redirected_writes": sorted(set(sb.redirected)), "scene": sc.name,
              "camera": [list(r) for r in cam.matrix_world] if cam else None,
              "camera_settings": {"lens": cam.data.lens, "sensor_width": cam.data.sensor_width, "sensor_height": cam.data.sensor_height,
                                  "sensor_fit": cam.data.sensor_fit, "shift_x": cam.data.shift_x, "shift_y": cam.data.shift_y} if cam else None,
              "resolution": [sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage],
              "engine": sc.render.engine, "samples": sc.cycles.samples, "exposure": sc.view_settings.exposure,
              "view_transform": sc.view_settings.view_transform, "look": sc.view_settings.look, "device": sc.cycles.device}
    return ns, report
