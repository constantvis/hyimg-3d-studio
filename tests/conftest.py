"""No test leaves a server behind, and none writes into the person's ~/Library/Caches/Hyimg (owner 2026-10-07): the core's guard,
hyimg/tests/procguard.py, from the core's working copy (HYIMG_REPO, else beside this repository). Without the core there is nothing to
guard: the tests that start a server need it anyway. A test that writes into that cache fails the run (procguard.finish)."""
import importlib.util
import os
import sys
from pathlib import Path

_GUARD = Path(os.environ.get("HYIMG_REPO") or Path(__file__).resolve().parents[2] / "hyimg") / "tests" / "procguard.py"
procguard = sys.modules.get("procguard")   # one guard a session: tests/unit/conftest.py takes this one
if procguard is None and _GUARD.is_file():
    _spec = importlib.util.spec_from_file_location("procguard", _GUARD)
    procguard = sys.modules["procguard"] = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(procguard)
if procguard:
    procguard.install()


def pytest_sessionfinish(session, exitstatus):   # also after ⌃C: the servers this session started and did not stop, then the cache check
    if procguard:
        procguard.finish(session)
