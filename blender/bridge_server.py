"""The Blender half of the bridge (owner 2026-10-06: «a switch: I spin and turn the 3D card and can switch from three.js to Blender»).
bridge.py starts it once per project and keeps it while it is used:

  Blender -b --factory-startup -P bridge_server.py -- --port-file <file> --parent <pid> --idle <s> --cache <folder>
  (the token comes in the environment, HYIMG_BRIDGE_TOKEN, so it is not in the process list)

It listens on 127.0.0.1 at a port of the system's choosing, writes {"port", "pid"} into the port file and takes one JSON line per
connection, {"token", "cmd", ...}; the answer is JSON lines, one event each, until the last one.

  ping                       → {"ev": "pong", "pid", "look"}
  render  {job, look, colour, view, camera, res, engine, device, steps, threads, exposure, out, follow}
                             → {"ev": "built", "seconds", "report"} when the look had to be built, then {"ev": "frame", "path", "samples",
                               "seconds"} per step, then {"ev": "done"}; {"ev": "cancelled"} when a newer render came first; {"ev": "error"}
  materials {look, colour, view} → {"ev": "materials", "list": [...]}: the built look's materials and their Principled parameters
  cancel                     → the render running now stops after its current step
  quit                       → the process ends

A look is built once (studio_looks.build: the studio's .blend and script, stopped at its render) and kept while the requests ask for the
same look, colour and, for a look whose light follows the view (c05-env), the same view. Steps render one after another (4, 16, 64
samples): each is written and sent, and a newer request ends the series after the step that is running. A step itself cannot be
interrupted from Python; bridge.py stops a long final render by ending the process. The process ends by itself when idle for --idle
seconds or when its parent (Hyimg's server) is gone.

  Blender -b --factory-startup -P bridge_server.py -- --once <request.json> [--out <png>]
renders one saved request (the json beside a picture made with «OK» holds it as "request") without a server: the reproduce command.

A render may carry a variant (owner 2026-10-07: «свет тестировать и материалы»), light and material overrides put on the built look in
memory and taken back before the next render (overrides.py). «Свет ракурса» first builds the picture's own look for the view and keeps
its light in the cache (make_rig), then builds the current look again and puts that light on it.
"""
import ast
import hmac
import json
import os
import queue
import socket
import sys
import threading
import time

import bpy
from mathutils import Matrix, Quaternion, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import studio_looks   # noqa: E402
import overrides   # noqa: E402

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(name, default=None):
    return ARGS[ARGS.index(name) + 1] if name in ARGS and ARGS.index(name) + 1 < len(ARGS) else default


TOKEN = os.environ.pop("HYIMG_BRIDGE_TOKEN", "")
studio_looks.BASE_ENV.pop("HYIMG_BRIDGE_TOKEN", None)
CACHE = arg("--cache") or os.path.join(os.path.expanduser("~/Library/Caches/Hyimg"), "blender")
IDLE = float(arg("--idle", "600"))
PARENT = int(arg("--parent", "0") or 0)
INBOX = queue.Queue()
STATE = {"key": None, "ns": None, "report": None, "look": None, "view": None, "busy": False, "last": time.time(), "cancel": 0}


def send(conn, ev):
    if conn is None:
        print("BRIDGE", json.dumps(ev), flush=True)
        return
    try:
        conn.sendall((json.dumps(ev) + "\n").encode())
    except OSError:
        pass


# ---- the look: built once, kept while asked for
def look_key(look, colour, view):
    return json.dumps([look.get("key") or look.get("id"), look.get("script"), look.get("blend"), colour,
                       view if look.get("kind") == "c05-env" else None, sorted((look.get("env") or {}).items())])


def ensure(look, colour, view, conn):
    key = look_key(look, colour, view)
    if STATE["key"] == key:
        return False
    STATE.update(key=None, ns=None, report=None)
    ns, report = studio_looks.build(look, colour, view, os.path.join(CACHE, "build"))
    overrides.reset()   # a new main file: what the last variant changed went with the old one
    built_cam = bpy.context.scene.camera
    STATE.update(key=key, ns=ns, report=report, look=look, view=view,
                 cam0=({k: getattr(built_cam, k).copy() if hasattr(getattr(built_cam, k), "copy") else getattr(built_cam, k) for k in ("location", "rotation_mode", "rotation_euler", "rotation_quaternion", "rotation_axis_angle", "scale")},
                       {k: getattr(built_cam.data, k) for k in ("lens", "sensor_width", "sensor_height", "sensor_fit", "shift_x", "shift_y")}) if built_cam else None)
    send(conn, {"ev": "built", "seconds": report["seconds"], "report": report})
    return True


def follow_source(look):
    """the statements of a c05-env script that place the light for the camera of a view (HDR anchor, near cards, display card), taken from
    its per-view loop as the studio wrote them; the framing of a macro view (lens, shift) is left out: the camera is the card's"""
    try:
        tree = ast.parse(open(STATE["ns"]["__file__"], encoding="utf-8").read())
    except (OSError, KeyError, SyntaxError):
        return None
    loop = next((n for n in tree.body if isinstance(n, ast.For) and isinstance(n.target, ast.Name) and n.target.id == "view_name"), None)
    if loop is None:
        return None
    body = loop.body
    start = next((i for i, s in enumerate(body) if isinstance(s, ast.Assign) and ast.unparse(s.targets[0]) == "lighting_override"), None)
    if start is None:
        return None
    keep = []
    for s in body[start:]:
        text = ast.unparse(s)
        if isinstance(s, ast.If) and ast.unparse(s.test) == "macro":
            continue
        if isinstance(s, ast.Expr) and text.startswith(("build_rig(", "add_display_card(")):
            keep.append(s)
            continue
        if text.startswith(("lighting_override", "anchor_mode", "rotation")) or (isinstance(s, ast.If) and "anchor_mode" in ast.unparse(s.test)):
            keep.append(s)
            continue
        if text.startswith("witness"):
            break
    mod = ast.Module(body=keep, type_ignores=[])
    ast.fix_missing_locations(mod)
    return compile(mod, STATE["ns"]["__file__"] + " (light for the camera)", "exec")


def place_camera(cam_req):
    """the card's camera on the built scene; None keeps the camera the studio's script set (the picture's own, to the last bit)"""
    sc = bpy.context.scene
    cam = sc.camera
    if cam is None:
        raise RuntimeError("the look has no camera")
    t0, d0 = STATE["cam0"]
    for k, v in t0.items():   # the studio's camera as its script left it: its own location and rotation, not a matrix made again of them
        setattr(cam, k, v.copy() if hasattr(v, "copy") else v)
    for k, v in d0.items():
        setattr(cam.data, k, v)
    if not cam_req:
        return False
    if cam_req.get("matrix"):
        cam.matrix_world = Matrix(cam_req["matrix"])
    else:   # a camera of scene.json: location and quaternion [w, x, y, z]
        cam.matrix_world = Matrix.Translation(Vector(cam_req["loc"])) @ Quaternion(cam_req["rot"]).to_matrix().to_4x4()
    for src, dst in (("lens", "lens"), ("sensor", "sensor_width"), ("sensor_h", "sensor_height"), ("fit", "sensor_fit")):
        if cam_req.get(src) is not None:
            setattr(cam.data, dst, cam_req[src])
    if cam_req.get("shift"):
        cam.data.shift_x, cam.data.shift_y = cam_req["shift"]
    return True


def follow_camera(look, view):
    """the light of a c05-env look goes with the camera as the studio's script places it for a view (its rig turns with the photographer)"""
    ns = STATE["ns"]
    if look.get("kind") != "c05-env" or not look.get("follow", True):
        return
    code = STATE.get("follow_code")
    if STATE.get("follow_for") != STATE["key"]:
        code = follow_source(look)
        STATE.update(follow_code=code, follow_for=STATE["key"])
    if code is None:
        return
    ns["view_name"] = view
    exec(code, ns)
    cam = bpy.context.scene.camera
    if callable(ns.get("project")) and callable(ns.get("set_shadow")) and not ns.get("macro") and cam.data.sensor_fit != "HORIZONTAL":
        px, py = ns["project"]()
        ns["bottom"] = .5 + (py.min() * cam.data.lens / cam.data.sensor_height - cam.data.shift_y)
        ns["set_shadow"](not ns.get("tabletop") and not ns.get("macro"), ns["bottom"])


def mute_outputs(tree):
    """the studio's file outputs (clean passes beside its renders) are switched off: a bridge frame writes only its own png"""
    if tree is None:
        return
    for n in tree.nodes:
        if n.bl_idname == "CompositorNodeOutputFile":
            n.mute = True
        elif getattr(n, "node_tree", None) is not None:
            mute_outputs(n.node_tree)


def set_device(sc, device, threads):
    if device == "GPU":
        prefs = bpy.context.preferences.addons["cycles"].preferences
        if prefs.compute_device_type != "METAL" or not any(d.use and d.type == "METAL" for d in prefs.devices):
            prefs.compute_device_type = "METAL"
            prefs.get_devices()   # the list is empty until asked, also when the type is METAL already
            for d in prefs.devices:
                d.use = d.type == "METAL"
        if not any(d.use and d.type == "METAL" for d in prefs.devices):
            device = "CPU"
    sc.cycles.device = device
    if threads:
        sc.render.threads_mode = "FIXED"
        sc.render.threads = int(threads)
    return device


def newer():
    """a newer render or a cancel is waiting"""
    with INBOX.mutex:
        return any(r.get("cmd") in ("render", "cancel", "quit") for r, _c in INBOX.queue)


def make_rig(light, colour, conn):
    """«Свет ракурса»: the picture's own look built for the view and camera, its light kept in the cache (once per key)"""
    if overrides.have_rig(CACHE, light["key"]):
        return
    t0 = time.time()
    ensure(light["look"], colour, light.get("view"), conn)
    overrides.restore()
    if place_camera(light.get("camera")):
        follow_camera(light["look"], light.get("view"))
    blend, meta = overrides.rig_paths(CACHE, light["key"])
    overrides.capture_rig(blend, meta, os.path.join(CACHE, "build"))
    STATE.update(key=None)   # the capture changed that build: it is made again when asked for
    overrides.prune_rigs(CACHE)
    send(conn, {"ev": "rig", "seconds": round(time.time() - t0, 2), "look": light["look"].get("id"), "view": light.get("view")})


def materials(req, conn):
    try:
        ensure(req["look"], req.get("colour"), req.get("view"), conn)
        overrides.restore()
        send(conn, {"ev": "materials", "list": overrides.report()})
    except Exception as e:
        STATE.update(key=None)
        send(conn, {"ev": "error", "error": f"{type(e).__name__}: {e}"})


def render(req, conn):
    STATE["busy"] = True
    try:
        look, colour, view, var = req["look"], req.get("colour"), req.get("view"), req.get("variant") or {}
        if (var.get("light") or {}).get("source") == "angle":
            make_rig(var["light"], colour, conn)
        ensure(look, colour, view, conn)
        overrides.restore()   # the last variant off the look before the camera and its light move
        sc = bpy.context.scene
        moved = place_camera(req.get("camera"))
        if moved and req.get("follow", True):
            follow_camera(look, view)
        if req.get("res"):
            sc.render.resolution_x, sc.render.resolution_y = (int(v) for v in req["res"])
            sc.render.resolution_percentage = 100
        if req.get("exposure") is not None:
            sc.view_settings.exposure = float(req["exposure"])
        mute_outputs(getattr(sc, "compositing_node_group", None))
        applied = overrides.apply(var, CACHE, sc) if var else None
        engine = req.get("engine", "CYCLES")
        sc.render.engine = "BLENDER_EEVEE" if engine == "EEVEE" else "CYCLES"
        device = set_device(sc, req.get("device", "CPU"), req.get("threads")) if engine != "EEVEE" else "GPU"
        sc.render.use_persistent_data = not req.get("final")
        sc.render.use_border = False
        sc.render.image_settings.file_format = "PNG"
        os.makedirs(req["out"], exist_ok=True)
        steps = req.get("steps") or [sc.cycles.samples]
        for i, s in enumerate(steps):
            if engine == "EEVEE":
                sc.eevee.taa_render_samples = int(s)
            else:
                sc.cycles.samples = int(s)
            path = os.path.join(req["out"], f"{req.get('job', 'frame')}-{i}.png")
            sc.render.filepath = path
            t0 = time.time()
            bpy.ops.render.render(write_still=True)
            send(conn, {"ev": "frame", "path": path, "samples": int(s), "step": i, "steps": len(steps), "seconds": round(time.time() - t0, 2),
                        "engine": engine, "device": device, "res": [sc.render.resolution_x, sc.render.resolution_y], "camera_moved": moved,
                        "camera": [list(r) for r in sc.camera.matrix_world], "exposure": sc.view_settings.exposure,
                        "camera_settings": {k: getattr(sc.camera.data, k) for k in ("lens", "sensor_width", "sensor_height", "sensor_fit", "shift_x", "shift_y")},
                        "variant": applied})
            if i + 1 < len(steps) and (newer() or STATE["cancel"]):
                send(conn, {"ev": "cancelled", "after": i})
                return
        send(conn, {"ev": "done"})
    except Exception as e:   # the look could not be built or rendered: said to the card, the process stays
        import traceback
        STATE.update(key=None)
        send(conn, {"ev": "error", "error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()[-2000:]})
    finally:
        STATE["busy"] = False
        STATE["cancel"] = 0
        STATE["last"] = time.time()


# ---- the server
def reader(srv):
    while True:
        try:
            conn, _ = srv.accept()
        except OSError:
            return
        conn.settimeout(10)
        try:
            buf = b""
            while not buf.endswith(b"\n") and len(buf) < 1 << 20:
                part = conn.recv(65536)
                if not part:
                    break
                buf += part
            req = json.loads(buf or b"{}")
        except (OSError, ValueError):
            conn.close()
            continue
        if not isinstance(req, dict) or not TOKEN or not hmac.compare_digest(str(req.get("token", "")), TOKEN):
            conn.close()
            continue
        conn.settimeout(None)
        cmd = req.get("cmd")
        if cmd == "ping":
            send(conn, {"ev": "pong", "pid": os.getpid(), "busy": STATE["busy"], "look": (STATE["look"] or {}).get("id"), "report": STATE["report"]})
            conn.close()
        elif cmd == "cancel":
            STATE["cancel"] = 1
            send(conn, {"ev": "ok"})
            conn.close()
        else:
            INBOX.put((req, conn))


def alive(pid):
    if not pid:
        return True
    if os.getppid() != pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def orphan_watch():
    """ends Blender within 2 s of Hyimg's server ending, also in the middle of a render, when the loop below cannot look (owner
    2026-10-07: no Blender left behind by a server that is gone)"""
    while alive(PARENT):
        time.sleep(2)
    os._exit(0)


def serve():
    if PARENT:
        threading.Thread(target=orphan_watch, daemon=True, name="hyimg-orphan").start()
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(16)
    port_file = arg("--port-file")
    tmp = port_file + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"port": srv.getsockname()[1], "pid": os.getpid()}, f)
    os.replace(tmp, port_file)
    threading.Thread(target=reader, args=(srv,), daemon=True).start()
    while True:
        try:
            req, conn = INBOX.get(timeout=1)
        except queue.Empty:
            if time.time() - STATE["last"] > IDLE or not alive(PARENT):
                break
            continue
        # only the newest render is made: the ones waiting before it are answered «cancelled»
        while req.get("cmd") == "render":
            try:
                nxt = INBOX.get_nowait()
            except queue.Empty:
                break
            send(conn, {"ev": "cancelled", "after": -1})
            conn.close()
            req, conn = nxt
        STATE["last"] = time.time()
        if req.get("cmd") == "quit":
            send(conn, {"ev": "bye"})
            conn.close()
            break
        if req.get("cmd") == "render":
            render(req, conn)
        elif req.get("cmd") == "materials":
            materials(req, conn)
        else:
            send(conn, {"ev": "error", "error": f"unknown command {req.get('cmd')}"})
        conn.close()
    try:
        srv.close()
        os.remove(port_file)
    except OSError:
        pass
    sys.stdout.flush()
    os._exit(0)


def once(path, out):
    req = json.load(open(path, encoding="utf-8"))
    req = req.get("request", req)
    if out:
        req["out"] = os.path.dirname(os.path.abspath(out)) or "."
        req["job"] = os.path.splitext(os.path.basename(out))[0]
    req["steps"] = req.get("steps", [])[-1:] or None
    render(req, None)
    if out:
        os.replace(os.path.join(req["out"], f"{req['job']}-0.png"), out)


if arg("--once"):
    once(arg("--once"), arg("--out"))
else:
    serve()
