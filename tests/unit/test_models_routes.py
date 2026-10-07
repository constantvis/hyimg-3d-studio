"""models.py, the 3D plugin's server routes: the project's models for the editor's «+» (2026-10-05), the «Recent» 3D files of the empty
3D card (2026-10-06), and the STEP routes handed on to cad.py."""
import json
import os
import sys
import types

import pytest

import models


def call(fn, b=b"", q=None):
    code, ctype, data = fn(b, q)
    assert ctype == "application/json"
    return code, json.loads(data)


def model(lib, name, spec):
    d = lib / "3d" / "models" / name
    d.mkdir(parents=True)
    (d / "model.json").write_text(spec if isinstance(spec, str) else json.dumps(spec))


# ---- models


def test_without_a_library_there_are_no_models():
    assert call(models.models) == (200, {"models": []})


def test_a_library_without_a_models_folder_has_no_models(library):
    assert call(models.models)[1] == {"models": []}


def test_the_projects_models_are_listed_by_folder_name_with_their_title_ai_and_height(library):
    model(library, "shell-v2", {"title": "Vase V2", "ai": "a vase", "height_m": 0.165, "parts": [{"glb": "a.glb"}]})
    model(library, "box", {"parts": [{}]})
    assert call(models.models)[1]["models"] == [
        {"id": "box", "title": "box", "ai": "", "height_m": None},
        {"id": "shell-v2", "title": "Vase V2", "ai": "a vase", "height_m": 0.165},
    ]


@pytest.mark.parametrize("height", [0, -1, "0.2", None, [1]])
def test_a_height_that_is_not_a_positive_number_is_left_out(library, height):
    model(library, "m", {"parts": [{}], "height_m": height})
    assert call(models.models)[1]["models"][0]["height_m"] is None


@pytest.mark.parametrize("spec", ["{broken", "[]", json.dumps({"parts": []}), json.dumps({"parts": "a.glb"}), json.dumps({"title": "no parts"})])
def test_a_model_without_parts_or_with_a_broken_spec_is_skipped(library, spec):
    model(library, "bad", spec)
    model(library, "good", {"parts": [{}]})
    assert [m["id"] for m in call(models.models)[1]["models"]] == ["good"]


@pytest.mark.parametrize("name", [".hidden", "_draft", "with space", "-dash"])
def test_a_folder_whose_name_is_not_a_model_id_is_skipped(library, name):
    model(library, name, {"parts": [{}]})
    assert call(models.models)[1]["models"] == []


def test_a_folder_without_model_json_is_skipped(library):
    (library / "3d/models/empty").mkdir(parents=True)
    assert call(models.models)[1]["models"] == []


def test_the_servers_config_module_names_the_library_when_the_env_does_not(tmp_path, monkeypatch):
    model(tmp_path, "m", {"parts": [{}]})
    monkeypatch.setitem(sys.modules, "config", types.SimpleNamespace(W=str(tmp_path)))
    assert [m["id"] for m in call(models.models)[1]["models"]] == ["m"]


# ---- recent


@pytest.fixture
def state(tmp_path, monkeypatch):
    s = tmp_path / "state"
    monkeypatch.setenv("HYIMG_STATE_ROOT", str(s))
    return s


def recent(obj):
    return call(models.recent, json.dumps(obj).encode())


def test_recent_without_a_state_folder_answers_500(tmp_path):
    assert recent({})[0] == 500


@pytest.mark.parametrize("b", [b"{", b"[]", b"3"])
def test_recent_refuses_a_body_that_is_not_a_json_object(state, b):
    assert call(models.recent, b)[0] == 400


def test_recent_starts_empty_and_asking_writes_nothing(state):
    assert recent({}) == (200, {"recent": []})
    assert not (state / "3d-recent.json").exists()


def test_an_added_file_goes_first_and_is_kept_in_the_projects_state_folder(state):
    recent({"add": "a/one.glb"})
    assert recent({"add": "b/two.step"})[1] == {"recent": ["b/two.step", "a/one.glb"]}
    assert json.loads((state / "3d-recent.json").read_text()) == {"recent": ["b/two.step", "a/one.glb"]}


def test_adding_a_file_that_is_already_there_moves_it_to_the_front_once(state):
    for p in ("a.glb", "b.glb", "c.glb"):
        recent({"add": p})
    assert recent({"add": "a.glb"})[1]["recent"] == ["a.glb", "c.glb", "b.glb"]


def test_recent_keeps_the_eight_newest(state):
    for i in range(12):
        recent({"add": f"m/{i}.glb"})
    assert recent({})[1]["recent"] == [f"m/{i}.glb" for i in range(11, 3, -1)]


def test_a_removed_file_leaves_the_list(state):
    recent({"add": "a.glb"})
    recent({"add": "b.glb"})
    assert recent({"remove": "a.glb"})[1]["recent"] == ["b.glb"]


@pytest.mark.parametrize("bad", ["../secret.glb", "a/../../x.glb", "/Volumes/x/a.glb", "~/a.glb", "", 5, None, ["a.glb"], "x" * 500])
def test_a_path_that_is_not_a_library_path_is_not_added(state, bad):
    assert recent({"add": bad})[1]["recent"] == []
    assert not (state / "3d-recent.json").exists()


def test_bad_entries_in_the_stored_file_are_dropped_and_a_broken_file_reads_as_empty(state):
    state.mkdir()
    (state / "3d-recent.json").write_text(json.dumps({"recent": ["ok.glb", "../x.glb", 7, "/abs.glb"]}))
    assert recent({})[1]["recent"] == ["ok.glb"]
    (state / "3d-recent.json").write_text("{broken")
    assert recent({})[1]["recent"] == []
    (state / "3d-recent.json").write_text("[1, 2]")
    assert recent({})[1]["recent"] == []


def test_an_unchanged_list_is_not_written_again(state):
    recent({"add": "a.glb"})
    f = state / "3d-recent.json"
    os.utime(f, (1000, 1000))
    recent({"add": "a.glb"})
    recent({"remove": "not-there.glb"})
    assert os.path.getmtime(f) == 1000
    assert not (state / "3d-recent.json.tmp").exists()


def test_the_servers_config_module_names_the_state_folder_when_the_env_does_not(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "config", types.SimpleNamespace(HERE=str(tmp_path / "st")))
    recent({"add": "a.glb"})
    assert (tmp_path / "st" / "3d-recent.json").exists()


# ---- the STEP routes


def test_the_step_routes_are_handed_to_cad_py_loaded_once(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "hyimg_3d_cad", None)   # removed again after the test
    monkeypatch.setenv("HYIMG_CAD_CACHE", str(tmp_path / "cache"))
    assert models.ROUTES["cadglb"](json.dumps({"key": "bad"}).encode(), None)[0] == 404
    first = sys.modules["hyimg_3d_cad"]
    assert first.CACHE == str(tmp_path / "cache")
    assert models.ROUTES["cad"](b"[]", None)[0] == 400
    assert models.ROUTES["cadput"](b"x", {"name": ["a.obj"]})[0] == 400
    assert sys.modules["hyimg_3d_cad"] is first


def test_the_routes_table_names_every_route():
    assert set(models.ROUTES) == {"models", "recent", "cad", "cadput", "cadglb", "blender"}
