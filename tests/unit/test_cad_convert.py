"""cad._convert(): which FreeCAD build converts (the GUI build off screen first, for the STEP's colours, then the console build), what
each failure becomes in the job, and that the glb lands in the cache whole or not at all. FreeCAD is a stand-in for subprocess.Popen:
nothing is started."""
import json
import os
import struct
import subprocess
import types

import pytest

import cad

KEY = "a" * 40
FC = {"cmd": "/fc/bin/freecadcmd", "gui": "/fc/bin/freecad", "version": "1.0.2"}


def glb_bytes():
    j = b'{"asset":{"version":"2.0"},"meshes":[{"primitives":[{}]}]}'
    j += b" " * (-len(j) % 4)
    return b"glTF" + struct.pack("<II", 2, 20 + len(j)) + struct.pack("<II", len(j), 0x4E4F534A) + j


def answer(result=None, glb=None, log=""):
    """what one FreeCAD run does: writes result.json and out.glb, prints a log"""
    def run(env):
        if glb is not None:
            open(env["HY_CAD_OUT"], "wb").write(glb)
        if result is not None:
            open(env["HY_CAD_RESULT"], "w").write(result if isinstance(result, str) else json.dumps(result))
        return log
    return run


OK = {"ok": True, "mode": "gui", "version": "1.0.2", "parts": 2, "faces": 12, "diagonal_mm": 70.7, "deviation_percent": 0.05, "seconds": 1.5}


class FakeFreeCAD:
    def __init__(self, gui=None, console=None):
        self.plan = {"gui": gui, "console": console}
        self.runs, self.killed = [], []

    def popen(self, args, env=None, **kw):
        mode = "gui" if args[0] == FC["gui"] else "console"
        self.runs.append({"mode": mode, "args": args, "env": env, "kw": kw})
        if isinstance(self.plan[mode], BaseException):
            raise self.plan[mode]
        return FakeProc(self, mode, env)


class FakeProc:
    pid = -1

    def __init__(self, fc, mode, env):
        self.fc, self.mode, self.env, self.calls = fc, mode, env, 0

    def communicate(self, timeout=None):
        self.calls += 1
        act = self.fc.plan[self.mode]
        if act == "timeout":
            if self.calls == 1:
                raise subprocess.TimeoutExpired("freecad", timeout)
            return "", None
        return (act(self.env) if act else ""), None


@pytest.fixture
def fake_fc(monkeypatch):
    def make(gui=None, console=None, have=FC):
        fc = FakeFreeCAD(gui, console)
        monkeypatch.setattr(cad, "freecad", lambda: dict(have) if have else None)
        monkeypatch.setattr(cad, "subprocess", types.SimpleNamespace(
            Popen=fc.popen, DEVNULL=subprocess.DEVNULL, PIPE=subprocess.PIPE, STDOUT=subprocess.STDOUT,
            TimeoutExpired=subprocess.TimeoutExpired, SubprocessError=subprocess.SubprocessError))
        monkeypatch.setattr(cad, "_kill", lambda proc: fc.killed.append(proc.mode))
        return fc
    return make


def run(src="/lib/part.step"):
    job = {"state": "working", "key": KEY}
    cad._convert(KEY, src, job)
    return job


def test_without_freecad_the_job_fails_as_nofreecad_and_nothing_starts(fake_fc):
    fc = fake_fc(have=None)
    job = run()
    assert job["state"] == "failed" and job["reason"] == "nofreecad"
    assert fc.runs == []


def test_the_gui_build_is_tried_first_off_screen_and_its_glb_is_kept(fake_fc):
    fc = fake_fc(gui=answer(OK, glb_bytes()))
    job = run()
    assert job["state"] == "ready"
    assert [r["mode"] for r in fc.runs] == ["gui"]
    assert fc.runs[0]["args"] == [FC["gui"], cad.SCRIPT]
    assert fc.runs[0]["env"]["QT_QPA_PLATFORM"] == "offscreen"
    assert os.path.isfile(cad._glb(KEY))


def test_without_the_gui_build_the_console_build_converts_on_screen_free(fake_fc):
    fc = fake_fc(console=answer(OK, glb_bytes()), have=dict(FC, gui=None))
    assert run()["state"] == "ready"
    assert [r["mode"] for r in fc.runs] == ["console"]
    assert "QT_QPA_PLATFORM" not in fc.runs[0]["env"]


def test_when_the_gui_build_fails_the_console_build_is_tried(fake_fc):
    fc = fake_fc(gui=answer({"ok": False, "reason": "unreadable", "error": "Qt"}), console=answer(dict(OK, mode="console"), glb_bytes()))
    job = run()
    assert job["state"] == "ready"
    assert [r["mode"] for r in fc.runs] == ["gui", "console"]
    assert cad._ready(KEY)["mode"] == "console"


def test_a_file_without_geometry_is_not_tried_again_with_the_console_build(fake_fc):
    fc = fake_fc(gui=answer({"ok": False, "reason": "nogeometry", "error": "no solids or surfaces in the file"}), console=answer(OK, glb_bytes()))
    job = run()
    assert (job["state"], job["reason"], job["error"]) == ("failed", "nogeometry", "no solids or surfaces in the file")
    assert [r["mode"] for r in fc.runs] == ["gui"]


def test_a_freecad_that_writes_no_answer_fails_as_unreadable_with_the_end_of_its_log(fake_fc):
    fake_fc(gui=answer(log="noise\n" * 100 + "Exception: boom\n"), console=answer(log="Segmentation fault\n"))
    job = run()
    assert job["state"] == "failed" and job["reason"] == "unreadable"
    assert job["error"].endswith("Segmentation fault") and len(job["error"]) <= 300


def test_a_freecad_that_says_nothing_at_all_fails_with_a_plain_message(fake_fc):
    fake_fc(have=dict(FC, gui=None), console=answer())
    assert run()["error"] == "FreeCAD gave no answer"


def test_a_garbage_answer_file_is_read_as_no_answer(fake_fc):
    fake_fc(have=dict(FC, gui=None), console=answer("{{{ not json", glb_bytes(), log="bad"))
    job = run()
    assert (job["state"], job["reason"]) == ("failed", "unreadable")


def test_an_ok_answer_with_a_file_that_is_not_a_glb_fails_and_caches_nothing(fake_fc):
    fake_fc(have=dict(FC, gui=None), console=answer(OK, b"<html>not a glb</html>"))
    job = run()
    assert (job["state"], job["reason"]) == ("failed", "unreadable") and job["error"].startswith("ValueError")
    assert not os.path.exists(cad._glb(KEY))


def test_a_conversion_over_the_time_limit_is_killed_and_fails_as_timeout(fake_fc):
    fc = fake_fc(gui="timeout", console=answer(OK, glb_bytes()))
    job = run()
    assert (job["state"], job["reason"]) == ("failed", "timeout")
    assert fc.killed == ["gui"]
    assert [r["mode"] for r in fc.runs] == ["gui"]   # the time is spent: the console build is not started
    assert not os.path.exists(cad._glb(KEY))


def test_with_under_ten_seconds_left_no_freecad_is_started_and_the_job_times_out(fake_fc, monkeypatch):
    monkeypatch.setattr(cad, "TIMEOUT", 5)
    fc = fake_fc(gui=answer(OK, glb_bytes()))
    job = run()
    assert (job["state"], job["reason"]) == ("failed", "timeout")
    assert fc.runs == []


def test_a_freecad_that_cannot_be_started_fails_as_unreadable(fake_fc):
    fake_fc(have=dict(FC, gui=None), console=FileNotFoundError(2, "No such file", FC["cmd"]))
    job = run()
    assert job["reason"] == "unreadable" and job["error"].startswith("FileNotFoundError")


def test_freecad_gets_the_paths_and_an_empty_user_folder_but_none_of_hyimgs_settings(fake_fc, monkeypatch):
    monkeypatch.setenv("HYIMG_LIBRARY_ROOT", "/owner/lib")
    monkeypatch.setenv("REVIEW_SECRET", "x")
    monkeypatch.setenv("PYTHONPATH", "/somewhere")
    fc = fake_fc(gui=answer(OK, glb_bytes()))
    run(src="/lib/part.step")
    env = fc.runs[0]["env"]
    assert not [k for k in env if k.startswith(("HYIMG_", "REVIEW_", "PYTHON"))]
    assert env["HY_CAD_IN"] == "/lib/part.step"
    assert env["HY_CAD_LIMIT"] == str(cad.GLB_MAX)
    assert env["FREECAD_USER_HOME"] == os.path.join(cad.CACHE, "freecad-home")
    assert os.path.dirname(env["HY_CAD_OUT"]).startswith(os.path.join(cad.CACHE, "work-" + KEY))
    kw = fc.runs[0]["kw"]
    assert kw["start_new_session"] is True and kw["stdin"] == subprocess.DEVNULL


def test_the_work_folder_is_removed_whether_it_went_well_or_not(fake_fc):
    fake_fc(gui=answer(OK, glb_bytes()))
    run()
    fake_fc(have=dict(FC, gui=None), console=answer({"ok": False, "reason": "unreadable"}))
    cad._convert("b" * 40, "/x.step", {"state": "working"})
    assert not [n for n in os.listdir(cad.CACHE) if n.startswith("work-")]


def test_the_glb_is_written_dressed_with_its_meta_and_no_part_file_is_left(fake_fc):
    fake_fc(gui=answer(OK, glb_bytes()))
    run()
    data = open(cad._glb(KEY), "rb").read()
    assert data == cad.dress(glb_bytes())
    meta = json.load(open(cad._meta(KEY)))
    assert meta == {**{k: OK[k] for k in ("seconds", "mode", "version", "parts", "faces", "diagonal_mm", "deviation_percent")}, "bytes": len(data)}
    assert not [n for n in os.listdir(cad.CACHE) if n.endswith(".part")]


def test_a_glb_another_job_made_meanwhile_is_taken_without_running_freecad(fake_fc):
    fc = fake_fc(gui=answer(OK, glb_bytes()))
    os.makedirs(cad.CACHE)
    open(cad._glb(KEY), "wb").write(b"made already")
    assert run()["state"] == "ready"
    assert fc.runs == []


def test_a_new_glb_prunes_the_cache_but_keeps_itself(fake_fc, monkeypatch):
    monkeypatch.setattr(cad, "CACHE_MAX", 10)
    os.makedirs(cad.CACHE)
    open(cad._glb("c" * 40), "wb").write(b"x" * 50)
    fake_fc(gui=answer(OK, glb_bytes()))
    run()
    assert os.path.exists(cad._glb(KEY)) and not os.path.exists(cad._glb("c" * 40))


def test_kill_stops_the_whole_process_group_and_falls_back_to_the_process(monkeypatch):
    seen = []

    class P:
        pid = 4242424

        def kill(self):
            seen.append("kill")

    def killpg(pid, sig):
        seen.append(("killpg", pid))
        raise ProcessLookupError

    monkeypatch.setattr(cad, "os", types.SimpleNamespace(killpg=killpg))
    cad._kill(P())
    assert seen == [("killpg", 4242424), "kill"]
