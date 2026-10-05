"""The 3D plugin's server route (2026-10-05: a new scene starts with a plain shape, a model comes from the project when the person picks
one). Hyimg loads this file by manifest.json "server" and serves it at POST /api/plugin/<plugin>/models:

  POST .../models → {"models": [{"id", "title", "ai", "height_m"}]}: the project's models, 3d/models/<id>/model.json, for the editor's «+»

A route is fn(body bytes, query dict) -> (status, content type, bytes).
"""
import json
import os
import re
import sys


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


ROUTES = {"models": models}
