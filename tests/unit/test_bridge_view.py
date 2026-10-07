"""The card is the truth for its view (owner 2026-10-07): right before Blender renders a card, bridge.ensure_camera makes scene.json's camera
of that id the card's view, creates it when it was deleted, and writes nothing when it already is (no syncing in the background)."""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))
import bridge as B   # noqa: E402

VIEW = {"name": "01 · v01", "loc": [0.1, -0.5, 0.2], "rot": [0.7, 0.7, 0, 0], "lens": 185, "sensor": 36, "sensor_h": 36, "fit": "VERTICAL", "shift": [0, 0.1]}


def test_ensure_camera_updates_creates_and_leaves(tmp_path, monkeypatch):
    monkeypatch.setenv("HYIMG_LIBRARY_ROOT", str(tmp_path))
    path = "3d/scenes/a/scene.json"; f = tmp_path / path; f.parent.mkdir(parents=True)
    doc = {"rev": 4, "cameras": [{"id": "c1", "name": "01 · v01", "loc": [0, 0, 0], "rot": [1, 0, 0, 0], "lens": 50}]}
    f.write_text(json.dumps(doc))
    assert B.ensure_camera(path, json.loads(f.read_text()), "c1", VIEW)
    d = json.loads(f.read_text()); c = d["cameras"][0]
    assert c["loc"] == VIEW["loc"] and c["lens"] == 185 and d["rev"] == 5 and d["by"] == "bridge"
    raw = f.read_text()
    assert not B.ensure_camera(path, json.loads(raw), "c1", VIEW) and f.read_text() == raw, "already the card's view: nothing written"
    # deleted from the scene: made again from the card, with its name
    assert B.ensure_camera(path, json.loads(raw), "c9", dict(VIEW, name="09 · v09"))
    c9 = next(c for c in json.loads(f.read_text())["cameras"] if c["id"] == "c9")
    assert c9["name"] == "09 · v09" and c9["rot"] == VIEW["rot"]
    assert not B.ensure_camera(path, json.loads(f.read_text()), "c1", {"lens": 50}), "no place in it: not a view"
