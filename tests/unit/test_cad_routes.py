"""cad.py's routes (POST /api/plugin/3d/cad, cadput, cadglb) and its jobs: request parsing, the library path check, refusals, and that a
file is hashed and converted once per content (owner 2026-10-06: «convert a STEP file once ... and keep the result»). The conversion
itself is a stand-in (cad._convert) and the background thread runs inline (sync_jobs)."""
import hashlib
import json
import os
import time

import pytest

import cad

STEP = b"ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\n#1=CARTESIAN_POINT('',(0.,0.,0.));\nENDSEC;\nEND-ISO-10303-21;\n"


def body(obj):
    return json.dumps(obj).encode()


def call(fn, b=b"", query=None):
    code, ctype, data = fn(b, query)
    return code, ctype, (json.loads(data) if ctype == "application/json" else data)


@pytest.fixture
def converter(monkeypatch):
    """cad._convert stand-in: writes a glb for the key (or fails as told) and counts its runs"""
    runs = []

    def convert(key, src, job, fail=None):
        runs.append({"key": key, "src": src, "src_existed": os.path.exists(src)})
        if converter_state["fail"]:
            job.update(state="failed", reason=converter_state["fail"], error="told to")
            return
        os.makedirs(cad.CACHE, exist_ok=True)
        open(cad._glb(key), "wb").write(b"glb of " + key.encode())
        job["state"] = "ready"

    converter_state = {"fail": None}
    monkeypatch.setattr(cad, "_convert", convert)
    convert.runs, convert.state = runs, converter_state
    return convert


@pytest.fixture
def hashes(monkeypatch):
    seen = []
    real = cad._sha1
    monkeypatch.setattr(cad, "_sha1", lambda p: seen.append(p) or real(p))
    return seen


# ---- the library path


def test_a_step_file_of_the_library_is_found(library):
    (library / "parts").mkdir()
    (library / "parts/a.STEP").write_bytes(STEP)
    assert cad._library_file("parts/a.STEP") == os.path.realpath(library / "parts/a.STEP")


@pytest.mark.parametrize("rel", ["../outside.step", "/etc/passwd", "parts/../../outside.step", "", None, 5, "a\0.step", "parts/model.obj", "parts/nothing.step", "parts"])
def test_a_path_outside_the_library_or_not_a_step_file_is_refused(library, tmp_path, rel):
    (library / "parts").mkdir()
    (library / "parts/model.obj").write_text("o x")
    (tmp_path / "outside.step").write_bytes(STEP)
    with pytest.raises(ValueError):
        cad._library_file(rel)


def test_a_symlink_that_leads_out_of_the_library_is_refused(library, tmp_path):
    (tmp_path / "secret.step").write_bytes(STEP)
    (library / "link.step").symlink_to(tmp_path / "secret.step")
    with pytest.raises(ValueError):
        cad._library_file("link.step")


def test_without_a_library_nothing_is_found(tmp_path):
    (tmp_path / "a.step").write_bytes(STEP)
    with pytest.raises(ValueError):
        cad._library_file("a.step")


def test_the_servers_config_module_names_the_library_when_the_env_does_not(tmp_path, monkeypatch):
    import types
    (tmp_path / "a.step").write_bytes(STEP)
    monkeypatch.setitem(__import__("sys").modules, "config", types.SimpleNamespace(W=str(tmp_path)))
    assert cad._library_file("a.step") == os.path.realpath(tmp_path / "a.step")


# ---- route cad


@pytest.mark.parametrize("b", [b"{oops", b"[1, 2]", b'"text"'])
def test_cad_refuses_a_body_that_is_not_a_json_object(b):
    assert call(cad.route_cad, b)[0] == 400


def test_cad_answers_404_for_a_path_that_is_not_a_step_file_of_the_library(library):
    code, _, d = call(cad.route_cad, body({"path": "../x.step"}))
    assert code == 404 and "STEP" in d["error"]


def test_a_library_step_file_is_converted_and_reported_ready(library, sync_jobs, converter):
    (library / "a.step").write_bytes(STEP)
    code, _, d = call(cad.route_cad, body({"path": "a.step"}))
    assert code == 200 and d["state"] == "ready" and d["key"] == hashlib.sha1(STEP).hexdigest()
    assert d["bytes"] == len(b"glb of ") + 40
    assert sync_jobs == ["cad"]


def test_asking_again_about_the_same_file_neither_hashes_nor_converts_again(library, sync_jobs, converter, hashes):
    (library / "a.step").write_bytes(STEP)
    call(cad.route_cad, body({"path": "a.step"}))
    call(cad.route_cad, body({"path": "a.step"}))
    assert len(converter.runs) == 1 and len(hashes) == 1 and sync_jobs == ["cad"]


def test_a_touched_file_with_the_same_bytes_is_hashed_again_but_not_converted_again(library, sync_jobs, converter, hashes):
    f = library / "a.step"
    f.write_bytes(STEP)
    k1 = call(cad.route_cad, body({"path": "a.step"}))[2]["key"]
    os.utime(f, (time.time() + 100, time.time() + 100))
    k2 = call(cad.route_cad, body({"path": "a.step"}))[2]["key"]
    assert k1 == k2 and len(hashes) == 2 and len(converter.runs) == 1


def test_a_file_whose_bytes_changed_gets_a_new_key_and_a_new_conversion(library, sync_jobs, converter):
    f = library / "a.step"
    f.write_bytes(STEP)
    k1 = call(cad.route_cad, body({"path": "a.step"}))[2]["key"]
    f.write_bytes(STEP + b"/* one more part */\n")
    k2 = call(cad.route_cad, body({"path": "a.step"}))[2]["key"]
    assert k1 != k2 and [r["key"] for r in converter.runs] == [k1, k2]


def test_two_library_files_with_the_same_bytes_share_one_glb(library, sync_jobs, converter):
    (library / "a.step").write_bytes(STEP)
    (library / "copy of a.stp").write_bytes(STEP)
    k1 = call(cad.route_cad, body({"path": "a.step"}))[2]["key"]
    k2 = call(cad.route_cad, body({"path": "copy of a.stp"}))[2]["key"]
    assert k1 == k2 and len(converter.runs) == 1


def test_an_empty_step_file_fails_as_empty_without_a_conversion(library, sync_jobs, converter):
    (library / "a.step").write_bytes(b"")
    d = call(cad.route_cad, body({"path": "a.step"}))[2]
    assert (d["state"], d["reason"]) == ("failed", "empty") and converter.runs == []


def test_a_step_file_over_the_size_limit_fails_as_toobig(library, sync_jobs, converter, monkeypatch):
    monkeypatch.setattr(cad, "SRC_MAX", 10)
    (library / "a.step").write_bytes(STEP)
    d = call(cad.route_cad, body({"path": "a.step"}))[2]
    assert (d["state"], d["reason"]) == ("failed", "toobig") and converter.runs == []


def test_a_failed_file_is_not_converted_again_at_every_hover(library, sync_jobs, converter):
    (library / "a.step").write_bytes(STEP)
    converter.state["fail"] = "unreadable"
    d1 = call(cad.route_cad, body({"path": "a.step"}))[2]
    d2 = call(cad.route_cad, body({"path": "a.step"}))[2]
    assert d1["state"] == d2["state"] == "failed" and d2["reason"] == "unreadable"
    assert len(converter.runs) == 1


def test_a_job_that_failed_for_want_of_freecad_starts_again_once_freecad_is_there(library, sync_jobs, converter, monkeypatch):
    (library / "a.step").write_bytes(STEP)
    converter.state["fail"] = "nofreecad"
    assert call(cad.route_cad, body({"path": "a.step"}))[2]["reason"] == "nofreecad"
    converter.state["fail"] = None
    monkeypatch.setattr(cad, "freecad", lambda: {"cmd": "/fc", "gui": None, "version": None})
    assert call(cad.route_cad, body({"path": "a.step"}))[2]["state"] == "ready"
    assert len(converter.runs) == 2


def test_a_ready_file_whose_glb_was_pruned_is_converted_again(library, sync_jobs, converter):
    (library / "a.step").write_bytes(STEP)
    key = call(cad.route_cad, body({"path": "a.step"}))[2]["key"]
    os.remove(cad._glb(key))
    assert call(cad.route_cad, body({"path": "a.step"}))[2]["state"] == "ready"
    assert len(converter.runs) == 2


def test_a_working_job_is_reported_as_working_without_a_second_thread(library, converter, monkeypatch):
    import threading
    import types
    started = []   # a thread that is started and never runs: the job stays working
    monkeypatch.setattr(cad, "threading", types.SimpleNamespace(Lock=threading.Lock, get_ident=threading.get_ident,
                                                                Thread=lambda target=None, daemon=None, name=None: types.SimpleNamespace(start=lambda: started.append(name))))
    (library / "a.step").write_bytes(STEP)
    d1 = call(cad.route_cad, body({"path": "a.step"}))[2]
    d2 = call(cad.route_cad, body({"path": "a.step"}))[2]
    assert d1 == d2 == {"state": "working", "key": None}
    assert started == ["cad"]


def test_a_job_that_raises_ends_failed_and_never_stays_working(sync_jobs):
    def boom(job):
        raise RuntimeError("FreeCAD went away")
    job = cad._start(("path", "x", 1, 1), boom)
    assert (job["state"], job["reason"]) == ("failed", "unreadable") and job["error"] == "RuntimeError: FreeCAD went away"


def test_finished_jobs_older_than_an_hour_are_forgotten(sync_jobs):
    cad._JOBS[("path", "old", 1, 1)] = {"state": "failed", "reason": "unreadable", "since": time.time() - 4000}
    cad._JOBS[("path", "busy", 1, 1)] = {"state": "working", "since": time.time() - 4000}
    cad._start(("path", "new", 1, 1), lambda job: job.update(state="failed", reason="x"))
    assert ("path", "old", 1, 1) not in cad._JOBS and ("path", "busy", 1, 1) in cad._JOBS


@pytest.mark.parametrize("key", ["A" * 40, "a" * 39, "../" + "a" * 37, 7])
def test_cad_by_key_with_a_malformed_key_is_read_as_a_path_and_refused(library, key):
    assert call(cad.route_cad, body({"key": key}))[0] == 404


def test_cad_by_key_of_an_unknown_conversion_says_it_is_gone():
    d = call(cad.route_cad, body({"key": "f" * 40}))[2]
    assert (d["state"], d["reason"]) == ("failed", "gone")


def test_cad_by_key_of_a_cached_glb_is_ready():
    os.makedirs(cad.CACHE)
    open(cad._glb("f" * 40), "wb").write(b"1234")
    assert call(cad.route_cad, body({"key": "f" * 40}))[2] == {"state": "ready", "key": "f" * 40, "bytes": 4}


# ---- route cadput


@pytest.mark.parametrize("name", ["part.obj", "part", "part.step.zip", "step"])
def test_cadput_refuses_a_name_that_is_not_a_step_or_iges_file(name):
    assert call(cad.route_cadput, STEP, {"name": [name]})[0] == 400


def test_cadput_without_a_name_takes_the_bytes_as_a_step_file(sync_jobs, converter):
    d = call(cad.route_cadput, STEP, {})[2]
    assert d["state"] == "ready" and converter.runs[0]["src"].endswith(".step")


def test_cadput_of_no_bytes_fails_as_empty():
    code, _, d = call(cad.route_cadput, b"", {"name": ["a.step"]})
    assert code == 200 and (d["state"], d["reason"]) == ("failed", "empty")


def test_cadput_over_the_size_limit_fails_as_toobig(monkeypatch):
    monkeypatch.setattr(cad, "SRC_MAX", 4)
    assert call(cad.route_cadput, STEP, {"name": ["a.IGS"]})[2]["reason"] == "toobig"


def test_cadput_converts_from_a_copy_in_the_cache_and_removes_the_copy_afterwards(sync_jobs, converter):
    d = call(cad.route_cadput, STEP, {"name": ["Part 1.IGES"]})[2]
    key = hashlib.sha1(STEP).hexdigest()
    assert d["state"] == "ready" and d["key"] == key
    run = converter.runs[0]
    assert run["src"] == os.path.join(cad.CACHE, "src", key + ".iges") and run["src_existed"]
    assert not os.path.exists(run["src"]) and not os.path.exists(run["src"] + ".part")


def test_cadput_of_bytes_already_converted_answers_from_the_cache_without_a_job(sync_jobs, converter):
    call(cad.route_cadput, STEP, {"name": ["a.step"]})
    d = call(cad.route_cadput, STEP, {"name": ["other name.stp"]})[2]
    assert d["state"] == "ready" and len(converter.runs) == 1 and sync_jobs == ["cad"]


def test_cadput_and_cad_by_key_report_the_same_failed_job(sync_jobs, converter):
    converter.state["fail"] = "nogeometry"
    key = call(cad.route_cadput, STEP, {"name": ["a.step"]})[2]["key"]
    d = call(cad.route_cad, body({"key": key}))[2]
    assert (d["state"], d["reason"], d["key"]) == ("failed", "nogeometry", key)


def test_putting_a_file_that_already_failed_again_leaves_no_copy_in_the_cache(sync_jobs, converter):
    converter.state["fail"] = "nogeometry"
    call(cad.route_cadput, STEP, {"name": ["a.step"]})
    call(cad.route_cadput, STEP, {"name": ["a.step"]})
    src = os.path.join(cad.CACHE, "src")
    assert os.listdir(src) == []


# ---- route cadglb


def test_cadglb_sends_the_cached_glb_as_model_gltf_binary():
    os.makedirs(cad.CACHE)
    open(cad._glb("e" * 40), "wb").write(b"glTF....")
    assert cad.route_cadglb(body({"key": "e" * 40})) == (200, "model/gltf-binary", b"glTF....")


@pytest.mark.parametrize("b", [b"", b"{bad", b"[]", b'"key"', body({"key": "E" * 40}), body({"key": "../" * 13 + "a"}), body({"key": "d" * 40})])
def test_cadglb_answers_404_for_a_bad_body_a_malformed_key_or_a_missing_glb(b):
    code, ctype, d = call(cad.route_cadglb, b)
    assert code == 404 and d == {"error": "no such model"}


def test_the_routes_table_names_the_three_routes():
    assert set(cad.ROUTES) == {"cad", "cadput", "cadglb"}
