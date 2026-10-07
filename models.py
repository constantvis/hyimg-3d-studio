"""The 3D plugin's server route (2026-10-05: a new scene starts with a plain shape, a model comes from the project when the person picks
one). Hyimg loads this file by manifest.json "server" and serves it at POST /api/plugin/<plugin>/models:

  POST .../models → {"models": [{"id", "title", "ai", "height_m"}]}: the project's models, 3d/models/<id>/model.json, for the editor's «+»
  POST .../recent {"add": path | "remove": path} → {"recent": [path, ...]}: the 3D files last put into a card, newest first, 8 at most
    (2026-10-06: the empty 3D card lists them); kept per project, in its state folder (3d-recent.json)
  POST .../cad, .../cadput, .../cadglb: STEP and IGES files converted to a glb by FreeCAD, once per content, in the background (cad.py)
  POST .../blender {"action": ...}: the card in Blender, a persistent Blender per project rendering the studio's current look (bridge.py)

A route is fn(body bytes, query dict) -> (status, content type, bytes).
"""
import json
import os
import re
import sys
import threading


def _library():
    return os.environ.get("HYIMG_LIBRARY_ROOT") or getattr(sys.modules.get("config"), "W", None)   # the server's library (config.py)


def models(body=b"", query=None):
    root = _library()
    folder = os.path.join(root, "3d", "models") if root else ""
    out = []
    for n in sorted(os.listdir(folder)) if folder and os.path.isdir(folder) else []:
        spec_file = os.path.join(folder, n, "model.json")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", n) or not os.path.isfile(spec_file):
            continue
        try:
            spec = json.load(open(spec_file, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(spec, dict) or not isinstance(spec.get("parts"), list) or not spec["parts"]:
            continue
        h = spec.get("height_m")
        out.append({"id": n, "title": str(spec.get("title") or n), "ai": str(spec.get("ai") or ""),
                    "height_m": h if isinstance(h, (int, float)) and h > 0 else None})
    return 200, "application/json", json.dumps({"models": out}, ensure_ascii=False).encode()


RECENT_MAX = 8
_LOCK = threading.Lock()


def _recent_file():
    state = os.environ.get("HYIMG_STATE_ROOT") or getattr(sys.modules.get("config"), "HERE", None)   # the project's own state folder (config.py)
    return os.path.join(state, "3d-recent.json") if state else None


def recent(body=b"", query=None):
    try: req = json.loads(body or b"{}")
    except ValueError: return 400, "application/json", b'{"error": "bad json"}'
    if not isinstance(req, dict): return 400, "application/json", b'{"error": "bad json"}'
    path = _recent_file()
    if not path: return 500, "application/json", b'{"error": "no state folder"}'
    ok = lambda p: isinstance(p, str) and p and ".." not in p.split("/") and not p.startswith(("/", "~")) and len(p) < 500   # a path of the library
    with _LOCK:
        try: have = [p for p in json.load(open(path, encoding="utf-8")).get("recent", []) if ok(p)]
        except (OSError, ValueError, AttributeError): have = []
        new = list(have)
        if ok(req.get("add")): new = [req["add"]] + [p for p in have if p != req["add"]]
        if ok(req.get("remove")): new = [p for p in new if p != req["remove"]]
        new = new[:RECENT_MAX]
        if new != have:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path + ".tmp", "w", encoding="utf-8") as f: json.dump({"recent": new}, f)
            os.replace(path + ".tmp", path)
    return 200, "application/json", json.dumps({"recent": new}).encode()


def _cad():
    """cad.py, the STEP and IGES conversion (2026-10-06): loaded once and kept, its jobs live in it; a route module is read by file path, so it cannot import it"""
    mod = sys.modules.get("hyimg_3d_cad")
    if mod is None:
        import importlib.util
        spec = importlib.util.spec_from_file_location("hyimg_3d_cad", os.path.join(os.path.dirname(os.path.abspath(__file__)), "cad.py"))
        mod = importlib.util.module_from_spec(spec); sys.modules["hyimg_3d_cad"] = mod; spec.loader.exec_module(mod)
    return mod


def _bridge():
    """bridge.py, the card in Blender (2026-10-06): loaded once and kept like cad.py; its Blender process and jobs live in it, so a newer
    models.py (loaded again by the server) does not lose them. A newer bridge.py is loaded again; the old one's Blender is ended first"""
    full = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bridge.py")
    mod = sys.modules.get("hyimg_3d_bridge")
    if mod is None or getattr(mod, "_MTIME", None) != os.path.getmtime(full):
        if mod is not None:
            try: mod._stop_all()
            except Exception: pass
        import importlib.util
        spec = importlib.util.spec_from_file_location("hyimg_3d_bridge", full)
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        mod._MTIME = os.path.getmtime(full); sys.modules["hyimg_3d_bridge"] = mod
    return mod


ROUTES = {"models": models, "recent": recent, "blender": lambda b=b"", q=None: _bridge().route(b, q),
          "cad": lambda b=b"", q=None: _cad().route_cad(b, q), "cadput": lambda b=b"", q=None: _cad().route_cadput(b, q), "cadglb": lambda b=b"", q=None: _cad().route_cadglb(b, q)}
