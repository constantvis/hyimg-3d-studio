"""The 3D card in Blender (owner 2026-10-06: «a switch: I spin and turn [the 3D card] and can switch from three.js to Blender (Cycles,
EEVEE) ... when I press OK I get the render like in the pictures ... one and the same model with the materials that are changing in
parallel»). Loaded once by models.py and kept; its routes are served at POST /api/plugin/3d/blender with {"action": ...}:

  preview  {scene, camera, cam: <the card's camera now>, w, h, engine: "EEVEE" | "CYCLES", look: "current" | "angle"}
           → {job, look}: Blender renders the card's view in steps (Cycles 4, 16, 64 samples on the graphics card; EEVEE 8, 32)
  final    the same → {job}: «OK», the angle's own frame size, samples and exposure, Cycles on the processor like the studio; when it is
           done the picture is saved as a new file in <scene.studio.out>/<YYMMDDHHmm>-3d-<look>/ with its json, never over anything (the
           frames of one sitting, within the hour, share the folder)
  job      {job} → {state: "building" | "rendering" | "saving" | "done" | "cancelled" | "error", frames: n, last, look, saved, error}
  frame    {job, n} → the png of step n
  look     {scene} → the look the cards use now: {id, source: "pointer" | "derived", updated, ...}
  materials {scene, camera, look} → {list}: the look's materials with their Principled parameters (Blender builds the look if it must)
  cancel   {job} → a final render is stopped by ending the Blender process (it starts again on the next request)
  status   → the Blender process: pid, port, idle seconds

preview and final may carry the card's variant ({variant, lights}, variants.py, owner 2026-10-07: «свет тестировать и материалы»): the
light (the look's own, the picture's own per angle, the scene's lights), the world's factor and material overrides, applied by Blender in
memory (blender/overrides.py); «OK» names its file after the variant and its json keeps the whole set.

A scene that can go to Blender carries {"studio": {...}} (written by tools/studio_angles.py): the studio folder, the colourway, where
«OK» saves, and per camera the picture it came from (its json: the studio's look, camera, frame size, samples, exposure).

The look. The studio keeps a pointer to the materials it is working on, looks/current.json in its folder (asked of Codex in its
CLAUDE_TO_CODEX.md, 2026-10-06): {id, blend, script, kind, scripts: {name: sha256}, env, colourways, renders, updated}. Until it is
there, the current look is derived from the studio's newest series of renders (renders/c05-M<n>*: the highest number, its newest
json): the .blend it names in "inputs", and the script that made it (a c05-env script found by the json's source_sha256, else the
render_c05_*.py that writes into that folder). The pointer is read again before each render, so a new step of the materials (M24)
reaches the cards at their next frame; the cards ask «look» every few seconds and show «материалы обновились».

The process. One Blender per project (blender/bridge_server.py), started on the first request, ended after IDLE seconds without one
and when Hyimg's server ends (atexit; the Blender side also watches its parent). Only this module's own child is ever stopped. While a
Blender of the studio itself is rendering (a process started from the studio folder), the bridge uses 2 processor threads, else 4.
"""
import atexit
import hashlib
import json
import os
import re
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.join(HERE, "blender", "bridge_server.py")
CACHE = os.environ.get("HYIMG_BLENDER_CACHE") or os.path.join(os.environ.get("HYIMG_CACHE_ROOT") or os.path.expanduser("~/Library/Caches/Hyimg"), "blender")
IDLE = float(os.environ.get("HYIMG_BLENDER_IDLE") or 600)
PREVIEW_LONG = 480
STEPS = {"CYCLES": [4, 16, 64], "EEVEE": [8, 32]}
_LOCK = threading.Lock()


def _load(name, file):
    """a sibling module by its path (models.py reads this file by path, so it cannot import its neighbours)"""
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, file))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


V = _load("hyimg_3d_variants", "variants.py")
_BRIDGES = {}   # library root -> Bridge
_JOBS = {}      # job id -> job dict
JOBS_MAX = 60


def _library():
    return os.environ.get("HYIMG_LIBRARY_ROOT") or getattr(sys.modules.get("config"), "W", None)


def blender_exe(model=""):
    """the Blender to run: HYIMG_BLENDER, else the one whose version the studio names («Blender 5.1.1 Cycles c05»), else the newest"""
    own = os.environ.get("HYIMG_BLENDER")
    if own:
        return own if os.path.isfile(own) else None
    apps = []
    for base in ("/Applications", os.path.expanduser("~/Applications")):
        try:
            apps += [os.path.join(base, n) for n in os.listdir(base) if re.match(r"Blender.*\.app$", n)]
        except OSError:
            pass
    want = re.search(r"Blender (\d+\.\d+(?:\.\d+)?)", model or "")
    ver = lambda p: tuple(int(x) for x in (re.findall(r"\d+", os.path.basename(p)) or ["0"]))
    apps.sort(key=lambda p: (bool(want) and want.group(1) in os.path.basename(p), ver(p)), reverse=True)
    for a in apps:
        exe = os.path.join(a, "Contents/MacOS/Blender")
        if os.path.isfile(exe):
            return exe
    return None


def studio_busy(studio):
    """a Blender of the studio itself is running (started from its folder): then the bridge leaves it the processor"""
    try:
        out = subprocess.run(["ps", "-axo", "pid=,command="], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    mine = {b.pid for b in _BRIDGES.values() if b.proc}
    for line in out.splitlines():
        pid, _, cmd = line.strip().partition(" ")
        if "Blender" in cmd and " -b" in cmd and pid.isdigit() and int(pid) not in mine and "bridge_server.py" not in cmd:
            try:
                cwd = subprocess.run(["lsof", "-a", "-p", pid, "-d", "cwd", "-Fn"], capture_output=True, text=True, timeout=5).stdout
            except (OSError, subprocess.SubprocessError):
                cwd = ""
            if studio and (studio in cmd or studio in cwd):
                return True
    return False


# ---- looks
def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


_SHA = {}


def sha(path):
    st = os.stat(path)
    k = (path, st.st_mtime_ns, st.st_size)
    if k not in _SHA:
        _SHA[k] = _sha(path)
    return _SHA[k]


def _abs(studio, p):
    return p if os.path.isabs(p) else os.path.join(studio, p)


def script_by_hash(studio, digest):
    """(script, overlay) of a c05-env picture: the studio's file with that sha256, the frozen bundle (c05-reproducible-*) that holds it"""
    found, overlay = None, None
    for n in sorted(os.listdir(studio)):
        p = os.path.join(studio, n)
        if n.endswith(".py") and os.path.isfile(p) and sha(p) == digest:
            found = p
            break
    for n in sorted(os.listdir(studio), reverse=True):
        d = os.path.join(studio, n)
        if n.startswith("c05-reproducible-") and os.path.isdir(d):
            for m in os.listdir(d):
                if m.endswith(".py") and sha(os.path.join(d, m)) == digest:
                    overlay = d
                    found = found or os.path.join(d, m)
                    break
        if overlay:
            break
    return found, overlay


def driver_for(studio, series):
    """the render_c05_*.py that wrote a series folder: it names the folder and renders itself (not a script that runs another)"""
    best = None
    for n in sorted(os.listdir(studio)):
        if not (n.startswith("render_") and n.endswith(".py")):
            continue
        try:
            text = open(os.path.join(studio, n), encoding="utf-8").read()
        except OSError:
            continue
        stem = series[4:] if series.startswith("c05-") else series   # a driver may build the folder's name (M24: «M24-palette-views»)
        if (series in text or stem in text or stem.replace("-", "_") in n) and "bpy.ops.render.render" in text:
            if best is None or len(n) < len(best):
                best = n
    return os.path.join(studio, best) if best else None


def look_from_json(studio, doc, colour, where=""):
    """the look a picture of the studio was made with, from its json"""
    blend = next((p for p in doc.get("inputs", []) if str(p).endswith(".blend")), None)
    if not blend:
        raise ValueError(f"no .blend in the json's inputs ({where})")
    tag = doc.get("tag") or doc.get("series") or (re.search(r"Cycles (\S+)", doc.get("model", "")) or [None, "?"])[1]
    if doc.get("recipe") and doc.get("source_sha256"):
        script, overlay = script_by_hash(studio, doc["source_sha256"])
        if not script:
            raise ValueError(f"the studio has no script with sha256 {doc['source_sha256'][:12]}… ({where})")
        env = dict(doc["recipe"])
        if colour:
            env["PALETTE"] = colour
        return {"id": tag, "kind": "c05-env", "studio": studio, "blend": _abs(studio, blend), "script": script, "overlay": overlay,
                "env": env, "model": doc.get("model", ""), "from": where}
    series = os.path.basename(os.path.dirname(where)) if where else ""
    script = driver_for(studio, series) if series else None
    if not script:
        raise ValueError(f"no script found that renders {series or where}")
    return {"id": doc.get("series") or tag, "kind": "driver", "studio": studio, "blend": _abs(studio, blend), "script": script, "overlay": None,
            "env": {}, "colour_var": "color", "view_var": "view", "model": doc.get("model", ""), "from": where}


SERIES = re.compile(r"^c05-M(\d+)([A-Z]*)(?:-|$)")


def derive_current(studio, colour):
    """the studio's newest step of materials: the series folder with the highest M number, its newest json of the colourway"""
    root = os.path.join(studio, "renders")
    groups = {}
    for n in os.listdir(root):
        m = SERIES.match(n)
        if m and os.path.isdir(os.path.join(root, n)):
            groups.setdefault(int(m.group(1)), []).append(n)
    for num in sorted(groups, reverse=True):
        cands = []
        for n in groups[num]:
            d = os.path.join(root, n)
            for f in os.listdir(d):
                if not f.endswith(".json") or f in ("validation.json",) or f.startswith(("_", ".")):
                    continue
                p = os.path.join(d, f)
                try:
                    doc = json.load(open(p, encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if not isinstance(doc, dict) or not doc.get("model") or not doc.get("inputs"):
                    continue
                c = doc.get("color") or (doc.get("recipe") or {}).get("PALETTE")
                cands.append(((c == colour), os.path.getmtime(p), p, doc))
        if not cands:
            continue
        cands.sort(key=lambda x: (x[0], x[1]), reverse=True)
        _, mtime, p, doc = cands[0]
        look = look_from_json(studio, doc, colour, p)
        look.update(source="derived", updated=time.strftime("%Y-%m-%d %H:%M", time.localtime(mtime)), series=os.path.basename(os.path.dirname(p)))
        return look
    raise ValueError("the studio has no series of renders (renders/c05-M*)")


def pointer_look(studio, colour):
    """the studio's own pointer, looks/current.json, when it is there"""
    p = os.path.join(studio, "looks", "current.json")
    try:
        doc = json.load(open(p, encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(doc, dict) or not doc.get("blend") or not (doc.get("script") or doc.get("kind") == "blend"):
        return None
    script = _abs(studio, doc["script"]) if doc.get("script") else None
    kind = doc.get("kind") or ("blend" if not script else "driver" if os.path.basename(script).startswith("render_") else "c05-env")
    env = {k: str(v) for k, v in (doc.get("env") or {}).items()}
    if kind == "c05-env" and colour:
        env["PALETTE"] = colour
    look = {"id": str(doc.get("id") or "?"), "kind": kind, "studio": studio, "blend": _abs(studio, doc["blend"]), "script": script,
            "overlay": _abs(studio, doc["overlay"]) if doc.get("overlay") else None, "env": env, "colour_var": doc.get("colour_var", "color"),
            "view_var": doc.get("view_var", "view"), "model": doc.get("model", ""), "source": "pointer", "updated": doc.get("updated"),
            "from": p, "note": doc.get("note"), "colourways": doc.get("colourways")}
    stated = doc.get("scripts") or {}
    bad = [n for n, h in stated.items() if os.path.isfile(_abs(studio, n)) and sha(_abs(studio, n)) != h]
    if bad:
        look["warning"] = "скрипты изменились после записи указателя: " + ", ".join(bad)
    return look


def fingerprint(look):
    """what makes a look this look: its script and .blend as they are now, its environment"""
    blend = look["blend"].replace("{colour}", look.get("colour") or "")
    parts = [look["id"], look["kind"], sha(look["script"]) if look.get("script") else "", blend, os.path.getsize(blend), os.path.getmtime(blend),
             json.dumps(look.get("env") or {}, sort_keys=True), look.get("overlay") or ""]
    if look.get("from") and os.path.isfile(look["from"]):
        parts.append(os.path.getmtime(look["from"]) if look.get("source") == "pointer" else 0)
    return hashlib.sha1(json.dumps(parts, default=str).encode()).hexdigest()[:12]


def current_look(studio, colour):
    look = pointer_look(studio, colour) or derive_current(studio, colour)
    look["colour"] = colour
    look["key"] = fingerprint(look)
    return look


def angle_look(studio, angle, colour):
    lib = _library()
    doc = json.load(open(os.path.join(lib, angle["source"]), encoding="utf-8"))
    look = look_from_json(studio, doc, colour, os.path.join(lib, angle["source"]))
    look.update(source="angle", colour=colour)
    look["key"] = fingerprint(look)
    return look, doc


# ---- the process
class Bridge:
    def __init__(self, lib):
        self.lib, self.proc, self.port, self.token, self.last, self.exe = lib, None, None, None, time.time(), None
        self.key = hashlib.sha1(lib.encode()).hexdigest()[:10]
        self.cache = os.path.join(CACHE, self.key)
        self.lock = threading.Lock()

    @property
    def pid(self):
        return self.proc.pid if self.proc and self.proc.poll() is None else None

    def start(self, model=""):
        if self.pid:
            return
        exe = blender_exe(model)
        if not exe:
            raise RuntimeError("Blender not found in /Applications")   # the page says it in the board's language (blender.js tidyErr)
        os.makedirs(self.cache, exist_ok=True)
        port_file = os.path.join(self.cache, "port.json")
        try:
            os.remove(port_file)
        except OSError:
            pass
        self.token = secrets.token_urlsafe(24)
        env = {k: v for k, v in os.environ.items() if not k.startswith(("HYIMG_", "REVIEW_", "PYTHON"))}
        env["HYIMG_BRIDGE_TOKEN"] = self.token
        log = open(os.path.join(self.cache, "blender.log"), "ab")
        self.proc = subprocess.Popen([exe, "-b", "--factory-startup", "-P", SERVER, "--", "--port-file", port_file, "--parent", str(os.getpid()),
                                      "--idle", str(int(IDLE) + 60), "--cache", self.cache],
                                     env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True, cwd=self.cache)
        self.exe = exe
        t0 = time.time()
        while time.time() - t0 < 60:
            if self.proc.poll() is not None:
                raise RuntimeError(f"Blender закрылся при запуске (код {self.proc.returncode}), журнал {os.path.join(self.cache, 'blender.log')}")
            try:
                info = json.load(open(port_file))
                self.port = info["port"]
                return
            except (OSError, ValueError, KeyError):
                time.sleep(0.1)
        self.stop()
        raise RuntimeError("Blender не ответил за 60 с")

    def stop(self):
        """ends this bridge's own Blender: a quit, then its process group if it did not go"""
        p, self.proc = self.proc, None
        if not p or p.poll() is not None:
            return
        try:
            self.send({"cmd": "quit"}, timeout=3, events=False)
        except OSError:
            pass
        try:
            p.wait(5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except OSError:
                p.kill()
            p.wait(5)

    def connect(self, timeout=10):
        s = socket.create_connection(("127.0.0.1", self.port), timeout=timeout)
        return s

    def send(self, req, timeout=10, events=True):
        """one request; the open connection and a reader of its event lines, or None"""
        s = self.connect(timeout)
        s.sendall((json.dumps(dict(req, token=self.token)) + "\n").encode())
        if not events:
            s.close()
            return None
        s.settimeout(None)
        return s


def bridge():
    lib = _library()
    if not lib:
        raise RuntimeError("no library")
    with _LOCK:
        if not _WATCHING:   # the idle watch starts with the first bridge, not on import (tools import the look functions)
            _WATCHING.append(threading.Thread(target=_watch, daemon=True, name="hyimg-blender-idle"))
            _WATCHING[0].start()
        b = _BRIDGES.get(lib)
        if b is None:
            b = _BRIDGES[lib] = Bridge(lib)
        return b


def _stop_all():
    for b in list(_BRIDGES.values()):
        try:
            b.stop()
        except Exception:
            pass


atexit.register(_stop_all)


def _watch():
    while True:
        time.sleep(15)
        for b in list(_BRIDGES.values()):
            busy = any(j["state"] in ("building", "rendering", "saving") and j.get("bridge") is b for j in list(_JOBS.values()))
            if b.pid and not busy and time.time() - b.last > IDLE:
                b.stop()


_WATCHING = []


# ---- the card's scene
def _scene(path):
    lib = _library()
    if not isinstance(path, str) or ".." in path.split("/") or path.startswith("/") or not path.endswith(".json"):
        raise ValueError("bad scene path")
    doc = json.load(open(os.path.join(lib, path), encoding="utf-8"))
    st = doc.get("studio")
    if not isinstance(st, dict) or not st.get("folder"):
        raise ValueError("this scene has no studio (scene.studio)")
    return doc, st


def _close(a, b, tol=2e-4):
    try:
        return all(abs(float(x) - float(y)) <= tol for x, y in zip(a, b)) and len(a) == len(b)
    except (TypeError, ValueError):
        return False


def same_camera(cam, cam0):
    """the card's camera is still the picture's camera (scene.json rounds to 1e-5)"""
    if not cam or not cam0:
        return False
    q = cam.get("rot") or []
    q0 = cam0.get("rot") or []
    flip = q and q0 and sum(a * b for a, b in zip(q, q0)) < 0
    return (_close(cam.get("loc", []), cam0.get("loc", [])) and (_close(q, q0) or (flip and _close([-v for v in q], q0)))
            and abs(float(cam.get("lens", 0)) - float(cam0.get("lens", 0))) < 1e-3 and _close(cam.get("shift", [0, 0]), cam0.get("shift", [0, 0]), 1e-4)
            and (cam.get("fit") or "AUTO") == (cam0.get("fit") or "AUTO"))


VIEW_KEYS = ("loc", "rot", "lens", "sensor", "sensor_h", "fit", "shift", "clip")


def ensure_camera(path, doc, cid, cam):
    """The card is the truth for its view (owner 2026-10-07): right before Blender renders a card, the scene's camera of that id becomes
    the card's view, made again when it is missing. Written only when it differs; returns True when scene.json was written"""
    if not cid or not isinstance(cam, dict):
        return False
    want = {k: cam[k] for k in VIEW_KEYS if cam.get(k) is not None}
    if not want.get("loc") or not want.get("rot"):
        return False
    cams = doc.setdefault("cameras", [])
    cur = next((c for c in cams if c.get("id") == cid), None)
    if cur is not None and all(cur.get(k) == v for k, v in want.items()):
        return False
    if cur is None:
        cur = {"id": cid, "name": cam.get("name") or cid}
        cams.append(cur)
    cur.update(want)
    doc["rev"] = int(doc.get("rev") or 0) + 1
    doc["by"] = "bridge"
    full = os.path.join(_library(), path)
    tmp = full + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    os.replace(tmp, full)
    return True


def frame_size(angle_res, w, h, long_side=None):
    """the frame Blender renders: the angle's own when the card has its shape, else the card's shape at the angle's longer side"""
    ax, ay = angle_res
    if not w or not h or abs((ax / ay) - (w / h)) < 0.01 * (ax / ay):
        x, y = ax, ay
    else:
        L = max(ax, ay)
        x, y = (L, round(L * h / w)) if w >= h else (round(L * w / h), L)
    if long_side and max(x, y) > long_side:
        k = long_side / max(x, y)
        x, y = round(x * k), round(y * k)
    return [max(16, int(x)), max(16, int(y))]


def out_size(angle_res, body, final):
    """the frame of a render: «Render» at the card's output size from the Scene panel (body res, W × H px, owner 2026-10-07: «там же тоже
    размер должен быть»), a preview at the card's shape no longer than PREVIEW_LONG; without a size, the angle's (frame_size)"""
    res = body.get("res")
    ok = isinstance(res, (list, tuple)) and len(res) == 2 and all(isinstance(v, (int, float)) and 16 <= v <= 16384 for v in res)
    if final and ok:
        return [int(round(res[0])), int(round(res[1]))]
    return frame_size(list(res) if ok else angle_res, body.get("w"), body.get("h"), None if final else PREVIEW_LONG)


def _job(**kw):
    jid = secrets.token_hex(6)
    j = dict(id=jid, state="building", frames=[], error=None, saved=None, started=time.time(), **kw)
    with _LOCK:
        _JOBS[jid] = j
        for old in sorted(_JOBS.values(), key=lambda x: x["started"])[:-JOBS_MAX]:
            if old["state"] not in ("building", "rendering", "saving"):
                _JOBS.pop(old["id"], None)
                for ev in old["frames"]:   # its frames leave the cache with it
                    try:
                        os.remove(ev["path"])
                    except OSError:
                        pass
    return j


def _run(b, j, req):
    """the request to Blender, its events into the job"""
    try:
        with b.lock:
            b.start(req["look"].get("model", ""))
        b.last = time.time()
        s = b.send(req)
        f = s.makefile("r", encoding="utf-8")
        for line in f:
            ev = json.loads(line)
            b.last = time.time()
            if ev["ev"] == "built":
                j["built"] = ev
                j["state"] = "rendering"
            elif ev["ev"] == "rig":
                j["rig"] = ev
            elif ev["ev"] == "frame":
                j["state"] = "rendering"
                j["frames"].append(ev)
            elif ev["ev"] in ("done", "cancelled", "error"):
                j["state"] = "saving" if ev["ev"] == "done" and j.get("final") else ev["ev"]   # done only once the file is in the library
                if ev["ev"] == "error":
                    j["error"] = ev.get("error")
                    j["trace"] = ev.get("trace")
                break
        s.close()
        if j["state"] == "rendering":   # the connection ended without a last word: the process went
            j["state"] = "cancelled" if j.get("killed") else "error"
            j["error"] = j["error"] or "Blender closed"
        if j["state"] == "saving":
            j["saved"] = save_final(j)
            j["state"] = "done"
    except Exception as e:
        j["state"], j["error"] = "error", f"{type(e).__name__}: {e}"
    finally:
        j["ended"] = time.time()
        b.last = time.time()


def start(body, final=False):
    lib = _library()
    doc, st = _scene(body.get("scene"))
    cid = body.get("camera") or doc.get("active_camera")
    angle = (st.get("angles") or {}).get(cid)
    if not angle:
        raise ValueError(f"camera {cid} has no studio angle")
    studio, colour = st["folder"], st.get("colour")
    which = body.get("look") or st.get("look") or "current"
    if ".." in str(angle.get("source", "")).split("/") or str(angle.get("source", "")).startswith("/"):
        raise ValueError("bad angle source")
    adoc = json.load(open(os.path.join(lib, angle["source"]), encoding="utf-8"))
    if which == "angle":
        look, _ = angle_look(studio, angle, colour)
    else:
        look = current_look(studio, colour)
    if body.get("cam"):   # the card's view, from the board: the scene's camera follows it now, not before (no syncing in the background)
        ensure_camera(body.get("scene"), doc, cid, body["cam"])
    cam = body.get("cam") or next((c for c in doc.get("cameras", []) if c.get("id") == cid), None)
    unchanged = same_camera(cam, angle.get("camera0"))
    own = which == "angle"
    if unchanged and own:
        camera = None   # the studio's script sets the picture's camera itself, to the last bit
    elif unchanged:
        cs = adoc.get("camera_settings") or {}
        camera = {"matrix": adoc["camera"], "lens": cs.get("lens_mm", cs.get("lens")), "sensor": cs.get("sensor_width_mm", cs.get("sensor_width")),
                  "sensor_h": angle.get("sensor_h"), "fit": angle.get("fit"), "shift": [cs.get("shift_x", 0), cs.get("shift_y", 0)]}
    else:
        camera = {k: cam.get(k) for k in ("loc", "rot", "lens", "sensor", "sensor_h", "fit", "shift")}
    var = V.clean(body.get("variant"))
    vplan = V.plan(var, which=which, colour=colour, view=angle.get("view"), angle_look=lambda: angle_look(studio, angle, colour)[0],
                   rig_camera=None if unchanged else {k: cam.get(k) for k in ("loc", "rot", "lens", "sensor", "sensor_h", "fit", "shift")}, lights=body.get("lights"))
    ares = angle.get("resolution") or adoc.get("resolution") or [480, 480]
    engine = "CYCLES" if final else ("EEVEE" if str(body.get("engine", "")).upper() == "EEVEE" else "CYCLES")
    b = bridge()
    req = {"cmd": "render", "look": look, "colour": colour, "view": angle.get("view"), "camera": camera, "engine": engine,
           "res": out_size(ares, body, final),
           "out": os.path.join(b.cache, "frames"), "follow": True}
    if vplan:
        req["variant"] = vplan
    if final:
        req.update(device="CPU", steps=[int(angle.get("samples") or adoc.get("samples") or 128)], final=True,
                   exposure=None if (own or angle.get("exposure") is None) else float(angle["exposure"]))
    else:
        req.update(device="GPU", steps=STEPS[engine])
        if not own and angle.get("exposure") is not None:
            req["exposure"] = float(angle["exposure"])
    inside = lambda p: p and os.path.realpath(p).startswith(os.path.realpath(studio) + os.sep)
    rig = ((vplan or {}).get("light") or {}).get("look")
    for lk in [look] + ([rig] if rig else []):
        if not inside(lk["blend"].replace("{colour}", colour or "")) or (lk.get("script") and not inside(lk["script"])) or (lk.get("overlay") and not inside(lk["overlay"])):
            raise ValueError("the look's files must lie in the studio folder")   # Blender runs only the studio's own scripts
    req["threads"] = 2 if studio_busy(studio) else 4
    j = _job(final=final, scene=body.get("scene"), camera_id=cid, angle=angle, look={k: look.get(k) for k in ("id", "kind", "source", "updated", "key", "series", "warning", "from")},
             request=req, card=body.get("card"), exact_camera=unchanged, bridge=b, variant=var, vplan=vplan)
    req["job"] = j["id"]
    if final:
        for o in _JOBS.values():   # one final at a time
            if o is not j and o.get("final") and o["state"] in ("building", "rendering", "saving"):
                raise RuntimeError("рендер OK уже идет")
    threading.Thread(target=_run, args=(b, j, req), daemon=True, name="hyimg-blender-job").start()
    return j


def save_final(j):
    """the finished frame into the library: <out>/<YYMMDDHHmm>-3d-<look>/<NN>-<view>-<colour>.png and its json; never over a file"""
    lib = _library()
    doc, st = _scene(j["scene"])
    angle, look, req, ev = j["angle"], j["look"], j["request"], j["frames"][-1]
    out, short = st.get("out") or "3d/renders", "3d-" + re.sub(r"[^A-Za-z0-9]+", "-", look["id"]).strip("-")
    folder = os.path.join(out, time.strftime("%y%m%d%H%M", time.localtime(j["started"])) + "-" + short)
    try:   # one batch for a sitting: the newest folder of this look when it was made within the hour
        have = sorted(n for n in os.listdir(os.path.join(lib, out)) if re.fullmatch(r"\d{10}-" + re.escape(short), n))
        if have and time.time() - os.path.getctime(os.path.join(lib, out, have[-1])) < 3600:
            folder = os.path.join(out, have[-1])
    except OSError:
        pass
    os.makedirs(os.path.join(lib, folder), exist_ok=True)
    stem = f"{angle.get('ordinal', 0):02d}-{angle.get('view', 'view')}-{st.get('colour') or 'scene'}"
    if j.get("variant") and V.slug(j["variant"].get("name")):   # the variant's name in the file's (owner 2026-10-07: «Рендер» with the variant's name)
        stem += "-" + V.slug(j["variant"]["name"])
    name, k = stem, 2
    while os.path.exists(os.path.join(lib, folder, name + ".png")) or os.path.exists(os.path.join(lib, folder, name + ".json")):
        name = f"{stem}~{k}"
        k += 1
    rel = f"{folder}/{name}.png"
    shutil.copyfile(ev["path"], os.path.join(lib, rel))
    full_look = req["look"]
    scripts = {os.path.relpath(full_look["script"], full_look["studio"]): sha(full_look["script"])}
    exe = j["bridge"].exe or blender_exe(full_look.get("model", ""))
    rq = {k: v for k, v in req.items() if k not in ("out", "job", "threads")}
    meta = {
        "model": f"Blender 5.1.1 Cycles {look['id']} (Hyimg 3D bridge)" if "5.1.1" in (exe or "") else f"Blender Cycles {look['id']} (Hyimg 3D bridge)",
        "prompt": f"{look['id']} · {st.get('colour', '')} · ракурс {angle.get('view')}: финальный кадр Cycles из 3D-карточки, "
                  + ("камера ракурса без изменений" if j["exact_camera"] else "камера повернута в карточке") + f", материалы {look['id']} ({'указатель студии' if look.get('source') == 'pointer' else 'материалы ракурса' if look.get('source') == 'angle' else 'последняя серия студии'})",
        "inputs": [full_look["blend"]],
        "derived_from": angle.get("source"),
        "look": {"id": look["id"], "kind": full_look["kind"], "source": look.get("source"), "series": look.get("series"), "updated": look.get("updated"),
                 "script": full_look["script"], "scripts_sha256": scripts, "blend": full_look["blend"], "overlay": full_look.get("overlay"), "pointer_or_json": look.get("from"),
                 "env": full_look.get("env")},
        "recipe": {"resolution": ev["res"], "samples": ev["samples"], "exposure": ev.get("exposure"), "angle_resolution": angle.get("resolution"),
                   "angle_samples": angle.get("samples"), "angle_exposure": angle.get("exposure")},
        "camera": ev.get("camera"), "camera_settings": ev.get("camera_settings"), "exact_camera": j["exact_camera"],
        "resolution": ev["res"], "samples": ev["samples"], "exposure": ev.get("exposure"), "engine": "Cycles", "device": ev.get("device"),
        "seconds": ev["seconds"] if ev.get("seconds") is not None else round(time.time() - j["started"], 2), "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "compute": f"local · Blender Cycles · {ev.get('device') or req.get('device') or 'CPU'} · {ev['samples']} samples",   # owner 2026-10-11, Hyimg runmeta
        "scene": j["scene"], "scene_camera": j["camera_id"],
        "colour": st.get("colour"), "view": angle.get("view"), "request": rq,
        "variant": V.sidecar(j.get("variant"), j.get("vplan")), "variant_applied": ev.get("variant"),
        "reproduce": f"'{exe}' -b --factory-startup -P '{SERVER}' -- --once '<этот json>' --out <файл.png>",
    }
    with open(os.path.join(lib, folder, name + ".json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    from PIL import Image
    with Image.open(os.path.join(lib, rel)) as im:
        w, h = im.size
    return {"path": rel, "ar": w / h}


def materials(body):
    """the look's materials as Blender has them, for the studio's «Материалы» list"""
    doc, st = _scene(body.get("scene"))
    cid = body.get("camera") or doc.get("active_camera")
    angle = (st.get("angles") or {}).get(cid) or next(iter((st.get("angles") or {}).values()), None)
    if not angle:
        raise ValueError("the scene has no studio angle")
    look = angle_look(st["folder"], angle, st.get("colour"))[0] if body.get("look") == "angle" else current_look(st["folder"], st.get("colour"))
    inside = lambda p: p and os.path.realpath(p).startswith(os.path.realpath(st["folder"]) + os.sep)
    if not inside(look["blend"].replace("{colour}", st.get("colour") or "")) or (look.get("script") and not inside(look["script"])):
        raise ValueError("the look's files must lie in the studio folder")
    b = bridge()
    with b.lock:
        b.start(look.get("model", ""))
    b.last = time.time()
    s = b.send({"cmd": "materials", "look": look, "colour": st.get("colour"), "view": angle.get("view")})
    try:
        s.settimeout(180)
        f = s.makefile("r", encoding="utf-8")
        for line in f:
            ev = json.loads(line)
            if ev["ev"] == "materials":
                return [dict(m, look=look["id"]) for m in ev["list"]]
            if ev["ev"] == "error":
                raise RuntimeError(ev.get("error"))
        raise RuntimeError("Blender закрылся")
    finally:
        s.close()
        b.last = time.time()


def _public(j):
    last = j["frames"][-1] if j["frames"] else None
    return {"job": j["id"], "state": j["state"], "frames": len(j["frames"]), "error": j.get("error"), "saved": j.get("saved"), "look": j["look"],
            "final": j.get("final"), "exact_camera": j.get("exact_camera"), "built": (j.get("built") or {}).get("seconds"),
            "rig": (j.get("rig") or {}).get("seconds"), "variant": last.get("variant") if last else None,
            "last": {k: last[k] for k in ("samples", "step", "steps", "seconds", "engine", "device", "res")} if last else None,
            "elapsed": round((j.get("ended") or time.time()) - j["started"], 1)}


def route(body=b"", query=None):
    try:
        req = json.loads(body or b"{}")
    except ValueError:
        return 400, "application/json", b'{"error": "bad json"}'
    if not isinstance(req, dict):
        return 400, "application/json", b'{"error": "bad json"}'
    act = req.get("action")
    ok = lambda d: (200, "application/json", json.dumps(d, ensure_ascii=False).encode())
    try:
        if act in ("preview", "final"):
            return ok(_public(start(req, final=act == "final")))
        if act == "job":
            j = _JOBS.get(req.get("job"))
            return ok(_public(j)) if j else (404, "application/json", b'{"error": "no such job"}')
        if act == "frame":
            j = _JOBS.get(req.get("job"))
            if not j or not j["frames"]:
                return 404, "application/json", b'{"error": "no frame"}'
            n = req.get("n")
            ev = j["frames"][n if isinstance(n, int) and -len(j["frames"]) <= n < len(j["frames"]) else -1]
            return 200, "image/png", open(ev["path"], "rb").read()
        if act == "look":
            _doc, st = _scene(req.get("scene"))
            look = current_look(st["folder"], st.get("colour"))
            return ok({k: look.get(k) for k in ("id", "kind", "source", "updated", "key", "series", "warning", "note", "from")})
        if act == "materials":
            return ok({"list": materials(req)})
        if act == "cancel":
            j = _JOBS.get(req.get("job"))
            if j and j["state"] in ("building", "rendering", "saving"):
                j["killed"] = True
                if j.get("final"):
                    j["bridge"].stop()   # a step of Cycles cannot be interrupted from Python: the process goes, the next request starts it
                else:
                    try:
                        j["bridge"].send({"cmd": "cancel"}, events=False)
                    except OSError:
                        pass
            return ok({"ok": True})
        if act == "status":
            b = _BRIDGES.get(_library())
            return ok({"pid": b.pid if b else None, "port": b.port if b and b.pid else None, "idle": round(time.time() - b.last) if b else None, "exe": b.exe if b else None})
    except (ValueError, OSError, RuntimeError, KeyError) as e:
        return 400, "application/json", json.dumps({"error": f"{e}"}, ensure_ascii=False).encode()
    return 400, "application/json", b'{"error": "unknown action"}'
