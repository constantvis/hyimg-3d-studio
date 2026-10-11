"""STEP and IGES files as 3D models (owner 2026-10-06: «STEP support: convert a STEP file once to a 3D model with FreeCAD, which is already
on this Mac, and keep the result, the same way videos already get a WebM copy. After that it opens in the 3D card and turns in the
library»). Loaded by models.py; its routes are served at POST /api/plugin/3d/<route>:

  cad     {"path": "<library path>"} or {"key": "<key>"} → the file's state: {"state": "ready" | "working" | "failed", "key", "reason", ...}
  cadput  the bytes of a chosen file (?name=part.step) → the same; for a file the person picked in the system's panel, which is not in the library
  cadglb  {"key": "<key>"} → the glb itself (model/gltf-binary)

The conversion is FreeCAD run headless in a process of its own (cad_freecad.py), once per content of the file (the key is its sha1), on a
background thread: a request only starts it and reports its state, so the server's request threads never wait for FreeCAD. The glb is kept in
the app's cache (~/Library/Caches/Hyimg/cad), never next to the owner's files, like the WebM copy of a video (review/webvideo.py); a scene
that takes the file in writes its own glb copy into the project (engine.js), so the cache can be emptied without breaking a scene.

Limits: one FreeCAD at a time (the rest queue), a source over 200 MB is refused, a conversion over 5 minutes is stopped, a glb over 60 MB is
made again from a coarser mesh, and the cache stays under 2 GB. FreeCAD is looked for where it lives (never installed or downloaded): the
app's GUI build run off screen when it is there (the STEP's colours come with it), else the console build.
"""
import hashlib
import json
import os
import plistlib
import re
import shutil
import signal
import struct
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "cad_freecad.py")
EXTS = (".step", ".stp", ".iges", ".igs")
CACHE = os.environ.get("HYIMG_CAD_CACHE") or os.path.join(os.environ.get("HYIMG_CACHE_ROOT") or os.path.expanduser("~/Library/Caches/Hyimg"), "cad")
TIMEOUT = int(os.environ.get("HYIMG_CAD_TIMEOUT") or 300)
SRC_MAX = int(os.environ.get("HYIMG_CAD_MAX_MB") or 200) << 20
GLB_MAX = 60 << 20
CACHE_MAX = int(os.environ.get("HYIMG_CAD_CACHE_MB") or 2048) << 20
SLOT = threading.Lock()          # one FreeCAD at a time
_LOCK = threading.Lock()
_JOBS = {}                       # job id -> {"state", "key", "reason", "error", "since"}
_MEMO = {}                       # (full, mtime, size) -> key: the file's content was hashed already


def _library():
    return os.environ.get("HYIMG_LIBRARY_ROOT") or getattr(sys.modules.get("config"), "W", None)


# ---- FreeCAD: where it is

def freecad():
    """{"cmd": <freecadcmd>, "gui": <freecad> | None, "version": str | None} of the FreeCAD on this Mac, or None. HYIMG_FREECAD names a
    FreeCAD.app or a folder with freecadcmd (tests), an empty value or a missing path means there is none."""
    own = os.environ.get("HYIMG_FREECAD")
    if own is not None:
        roots = [own] if own else []
    else:
        apps = []
        for base in ("/Applications", os.path.expanduser("~/Applications")):
            try: apps += [os.path.join(base, n) for n in sorted(os.listdir(base), reverse=True) if re.match(r"FreeCAD.*\.app$", n)]
            except OSError: pass
        roots = apps + [os.path.dirname(p) for p in (shutil.which("freecadcmd"), "/opt/homebrew/bin/freecadcmd", "/usr/local/bin/freecadcmd") if p and os.path.exists(p)]
    for r in roots:
        for bin_dir in (os.path.join(r, "Contents/Resources/bin"), r):
            cmd, gui = os.path.join(bin_dir, "freecadcmd"), os.path.join(bin_dir, "freecad")
            if os.path.isfile(cmd) and os.access(cmd, os.X_OK):
                version = None
                try: version = plistlib.load(open(os.path.join(r, "Contents/Info.plist"), "rb")).get("CFBundleShortVersionString") or None
                except (OSError, ValueError, plistlib.InvalidFileException): pass
                return {"cmd": cmd, "gui": gui if os.path.isfile(gui) and os.access(gui, os.X_OK) else None, "version": version}
    return None


# ---- the cache

def _glb(key): return os.path.join(CACHE, key + ".glb")
def _meta(key): return os.path.join(CACHE, key + ".json")


def _ready(key):
    if not os.path.isfile(_glb(key)): return None
    try: meta = json.load(open(_meta(key), encoding="utf-8"))
    except (OSError, ValueError): meta = {}
    try: os.utime(_glb(key))   # used now: the cache forgets what was used longest ago
    except OSError: pass
    got = {k: meta[k] for k in ("seconds", "mode", "version", "parts", "faces", "diagonal_mm") if k in meta}
    if got.get("version") or got.get("mode"):   # where it ran, Hyimg's one word for it (owner 2026-10-11: time, cost, compute of a 3D file too)
        got["compute"] = " · ".join(x for x in ("local", f"FreeCAD {got.get('version') or ''}".strip(), str(got.get("mode") or "")) if x)
    return {"state": "ready", "key": key, "bytes": os.path.getsize(_glb(key)), **got}


def prune(keep=None):
    try:
        files = [os.path.join(CACHE, f) for f in os.listdir(CACHE) if f.endswith(".glb")]
        files = sorted(((os.stat(f), f) for f in files), key=lambda x: max(x[0].st_atime, x[0].st_mtime))
        total = sum(st.st_size for st, _f in files)
        for st, f in files:
            if total <= CACHE_MAX: break
            if os.path.basename(f)[:-4] == keep: continue
            os.remove(f); total -= st.st_size
            try: os.remove(f[:-4] + ".json")
            except OSError: pass
    except OSError:
        pass


# ---- the glb as OpenCascade writes it, dressed for the scene

def dress(data):
    """a glb with a material on every part and none of them a mirror: OpenCascade writes no material for geometry without a colour and none
    of metalness, which glTF reads as a fully metallic, black surface. A part with no material gets a neutral grey, one with only a colour
    gets a mostly matte finish (a CAD colour says nothing about gloss)."""
    if len(data) < 28 or data[:4] != b"glTF": raise ValueError("not a glb")
    jl, jt = struct.unpack("<II", data[12:20])
    if jt != 0x4E4F534A: raise ValueError("no json chunk")
    doc = json.loads(data[20:20 + jl]); rest = data[20 + jl:]
    mats = doc.setdefault("materials", [])
    for m in mats:
        pbr = m.setdefault("pbrMetallicRoughness", {})
        pbr.setdefault("metallicFactor", 0.1); pbr.setdefault("roughnessFactor", 0.5)
    grey = None
    for mesh in doc.get("meshes", []):
        for prim in mesh.get("primitives", []):
            if "material" not in prim:
                if grey is None:
                    mats.append({"name": "cad grey", "doubleSided": True, "pbrMetallicRoughness": {"baseColorFactor": [0.47, 0.47, 0.46, 1], "metallicFactor": 0.1, "roughnessFactor": 0.5}})
                    grey = len(mats) - 1
                prim["material"] = grey
    text = json.dumps(doc, separators=(",", ":")).encode("utf-8")
    text += b" " * (-len(text) % 4)
    total = 12 + 8 + len(text) + len(rest)
    return data[:8] + struct.pack("<I", total) + struct.pack("<II", len(text), 0x4E4F534A) + text + rest


# ---- one conversion

def _kill(proc):
    try: os.killpg(proc.pid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        try: proc.kill()
        except OSError: pass


def _convert(key, src, job):
    """FreeCAD on `src` (a path of a file with the key's content), the glb into the cache; the job's state says how it went. One at a time."""
    fc = freecad()
    if not fc:
        job.update(state="failed", reason="nofreecad", error="no FreeCAD found"); return
    with SLOT:
        if os.path.isfile(_glb(key)):   # another job made it while this one waited
            job.update(state="ready"); return
        job["running"] = True
        os.makedirs(CACHE, exist_ok=True)
        work = os.path.join(CACHE, f"work-{key}-{os.getpid()}-{threading.get_ident()}"); os.makedirs(work, exist_ok=True)
        out, res = os.path.join(work, "out.glb"), os.path.join(work, "result.json")
        home = os.path.join(CACHE, "freecad-home"); os.makedirs(home, exist_ok=True)
        env = {k: v for k, v in os.environ.items() if not k.startswith(("HYIMG_", "REVIEW_", "PYTHON"))}
        env.update(HY_CAD_IN=src, HY_CAD_OUT=out, HY_CAD_RESULT=res, HY_CAD_LIMIT=str(GLB_MAX),
                   FREECAD_USER_HOME=home)   # an empty user folder: the owner's FreeCAD settings and its MCP bridge are not loaded, nothing is written there
        attempts = [("gui", fc["gui"])] if fc["gui"] else []
        attempts.append(("console", fc["cmd"]))
        answer, started = None, time.time()
        try:
            for mode, exe in attempts:
                left = TIMEOUT - (time.time() - started)
                if left < 10: break
                e = dict(env, QT_QPA_PLATFORM="offscreen") if mode == "gui" else env
                for f in (out, res):
                    if os.path.exists(f): os.remove(f)
                proc = subprocess.Popen([exe, SCRIPT], env=e, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True, text=True, errors="replace")
                try:
                    log, _ = proc.communicate(timeout=left)
                except subprocess.TimeoutExpired:
                    _kill(proc); proc.communicate()
                    job.update(state="failed", reason="timeout", error=f"over {TIMEOUT} s"); return
                try: answer = json.load(open(res, encoding="utf-8"))
                except (OSError, ValueError): answer = {"ok": False, "reason": "unreadable", "error": (log or "FreeCAD gave no answer").strip()[-300:]}
                if answer.get("ok") and os.path.getsize(out): break
                if answer.get("reason") == "nogeometry": break   # the other build would find the same
            if answer is None:
                job.update(state="failed", reason="timeout", error=f"over {TIMEOUT} s"); return
            if not answer.get("ok"):
                job.update(state="failed", reason=answer.get("reason") or "unreadable", error=answer.get("error", "")); return
            data = dress(open(out, "rb").read())
            tmp = _glb(key) + f".{os.getpid()}.part"
            with open(tmp, "wb") as fh: fh.write(data)
            meta = {k: answer[k] for k in ("seconds", "mode", "version", "parts", "faces", "diagonal_mm", "deviation_percent") if k in answer}
            meta["bytes"] = len(data)
            with open(_meta(key), "w", encoding="utf-8") as fh: json.dump(meta, fh)
            os.replace(tmp, _glb(key))   # whole or nothing: a half-written glb is never served
            job["state"] = "ready"
            prune(keep=key)
        except (OSError, ValueError, subprocess.SubprocessError) as ex:
            job.update(state="failed", reason="unreadable", error=f"{type(ex).__name__}: {str(ex)[:200]}")
        finally:
            shutil.rmtree(work, ignore_errors=True)


def _sha1(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""): h.update(chunk)
    return h.hexdigest()


def _view(job):
    d = {"state": job["state"], "key": job.get("key")}
    if job["state"] == "failed": d.update(reason=job.get("reason"), error=(job.get("error") or "")[:300])
    if job["state"] == "ready" and job.get("key"): d = _ready(job["key"]) or d
    return d


def _job_path(pk, full, job):
    try:
        size = os.path.getsize(full)
        if size == 0: job.update(state="failed", reason="empty", error="the file has no bytes"); return
        if size > SRC_MAX: job.update(state="failed", reason="toobig", error=f"{size >> 20} MB"); return
        key = _MEMO.get(pk) or _sha1(full)
        _MEMO[pk] = job["key"] = key
        if os.path.isfile(_glb(key)): job["state"] = "ready"; return
        _convert(key, full, job)
    except OSError as ex:
        job.update(state="failed", reason="unreadable", error=f"{type(ex).__name__}: {str(ex)[:200]}")


def _job_bytes(key, src, job):
    try: _convert(key, src, job)
    finally:
        try: os.remove(src)
        except OSError: pass


def _start(jid, target, *args):
    """the job of this id: a running or failed one is returned as it is (a failed file is not tried again at every hover: a changed file has
    another id, and a missing FreeCAD is looked for again), else a new one starts on its own thread"""
    with _LOCK:
        job = _JOBS.get(jid)
        if job and not (job["state"] == "failed" and job.get("reason") == "nofreecad" and freecad()):
            if job["state"] != "ready" or (job.get("key") and os.path.isfile(_glb(job["key"]))): return job
        job = _JOBS[jid] = {"state": "working", "key": jid[1] if jid[0] == "up" else None, "since": time.time()}
        for old in [k for k, j in _JOBS.items() if j["state"] != "working" and time.time() - j["since"] > 3600]: _JOBS.pop(old, None)
    def run():
        try: target(*args, job)
        except BaseException as ex:   # noqa: BLE001 - a job never stays «working» for good
            job.update(state="failed", reason="unreadable", error=f"{type(ex).__name__}: {str(ex)[:200]}")
    threading.Thread(target=run, daemon=True, name="cad").start()
    return job


# ---- the routes

def _json(code, obj): return code, "application/json", json.dumps(obj, ensure_ascii=False).encode()


def _library_file(rel):
    root = _library()
    if not root or not isinstance(rel, str) or not rel or "\0" in rel: raise ValueError("no such file")
    base = os.path.realpath(root); full = os.path.realpath(os.path.join(base, rel))
    if not full.startswith(base + os.sep) or not full.lower().endswith(EXTS) or not os.path.isfile(full): raise ValueError("no such file")
    return full


def route_cad(body=b"", query=None):
    try: req = json.loads(body or b"{}")
    except ValueError: return _json(400, {"error": "bad json"})
    if not isinstance(req, dict): return _json(400, {"error": "bad json"})
    key = req.get("key")
    if isinstance(key, str) and re.fullmatch(r"[0-9a-f]{40}", key):   # a file put in with cadput: its job, or the cache
        ready = _ready(key)
        if ready: return _json(200, ready)
        with _LOCK: job = _JOBS.get(("up", key))
        return _json(200, _view(job) if job else {"state": "failed", "key": key, "reason": "gone", "error": "no such conversion"})
    try: full = _library_file(req.get("path"))
    except ValueError: return _json(404, {"error": "not a STEP or IGES file of the library"})
    st = os.stat(full); pk = (full, st.st_mtime_ns, st.st_size)
    k = _MEMO.get(pk)
    if k and _ready(k): return _json(200, _ready(k))   # asked before: no thread, no hashing
    return _json(200, _view(_start(("path",) + pk, _job_path, pk, full)))


def route_cadput(body=b"", query=None):
    name = (query or {}).get("name", ["file.step"])[0]
    ext = os.path.splitext(name)[1].lower()
    if ext not in EXTS: return _json(400, {"error": "not a STEP or IGES file"})
    if not body: return _json(200, {"state": "failed", "reason": "empty", "error": "the file has no bytes"})
    if len(body) > SRC_MAX: return _json(200, {"state": "failed", "reason": "toobig", "error": f"{len(body) >> 20} MB"})
    key = hashlib.sha1(body).hexdigest()
    ready = _ready(key)
    if ready: return _json(200, ready)
    src = os.path.join(CACHE, "src", key + ext)
    with _LOCK: have = _JOBS.get(("up", key))
    if not (have and have["state"] == "working"):
        os.makedirs(os.path.dirname(src), exist_ok=True)
        with open(src + ".part", "wb") as fh: fh.write(body)
        os.replace(src + ".part", src)
    job = _start(("up", key), _job_bytes, key, src)
    if job["state"] == "failed":   # an earlier failure returned as it is: nobody reads the copy just written, so it goes (unit test, 2026-10-06)
        try: os.remove(src)
        except OSError: pass
    return _json(200, _view(job))


def route_cadglb(body=b"", query=None):
    try: key = json.loads(body or b"{}").get("key")
    except (ValueError, AttributeError): key = None
    if not isinstance(key, str) or not re.fullmatch(r"[0-9a-f]{40}", key) or not os.path.isfile(_glb(key)): return _json(404, {"error": "no such model"})
    with open(_glb(key), "rb") as fh: return 200, "model/gltf-binary", fh.read()


ROUTES = {"cad": route_cad, "cadput": route_cadput, "cadglb": route_cadglb}
