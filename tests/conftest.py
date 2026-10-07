"""No test leaves a server behind, and none writes into the person's ~/Library/Caches/Hyimg (owner 2026-10-07): the core's guard,
hyimg/tests/procguard.py, from the core's working copy (HYIMG_REPO, else beside this repository). Without the core there is nothing to
guard: the tests that start a server need it anyway."""
import importlib.util
import os
from pathlib import Path

_GUARD = Path(os.environ.get("HYIMG_REPO") or Path(__file__).resolve().parents[2] / "hyimg") / "tests" / "procguard.py"
procguard = None
if _GUARD.is_file():
    _spec = importlib.util.spec_from_file_location("procguard", _GUARD)
    procguard = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(procguard)
    procguard.install()


def pytest_sessionfinish(session, exitstatus):   # also after ⌃C: the servers this session started and did not stop
    if procguard:
        procguard.sweep()
