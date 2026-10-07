"""cad.freecad(): where FreeCAD is found (owner 2026-10-06: «FreeCAD, which is already on this Mac»; never installed or downloaded).
The fake FreeCAD builds here are shell files that are never run."""
import os
import plistlib

import cad


def fake_app(root, gui=True, version="1.0.2", executable=True):
    """<root>/FreeCAD.app/Contents/Resources/bin/{freecadcmd, freecad} and its Info.plist"""
    app = root / "FreeCAD.app"
    bin_ = app / "Contents/Resources/bin"
    bin_.mkdir(parents=True)
    for name in ("freecadcmd",) + (("freecad",) if gui else ()):
        (bin_ / name).write_text("#!/bin/sh\nexit 99\n")
        (bin_ / name).chmod(0o755 if executable else 0o644)
    if version is not None:
        with open(app / "Contents/Info.plist", "wb") as f:
            plistlib.dump({"CFBundleShortVersionString": version}, f)
    return app


def test_an_empty_hyimg_freecad_means_there_is_no_freecad(monkeypatch):
    monkeypatch.setenv("HYIMG_FREECAD", "")
    assert cad.freecad() is None


def test_a_hyimg_freecad_that_does_not_exist_means_there_is_no_freecad(monkeypatch, tmp_path):
    monkeypatch.setenv("HYIMG_FREECAD", str(tmp_path / "Nowhere.app"))
    assert cad.freecad() is None


def test_an_app_bundle_gives_its_console_and_gui_builds_and_its_version(monkeypatch, tmp_path):
    app = fake_app(tmp_path)
    monkeypatch.setenv("HYIMG_FREECAD", str(app))
    fc = cad.freecad()
    assert fc == {"cmd": str(app / "Contents/Resources/bin/freecadcmd"), "gui": str(app / "Contents/Resources/bin/freecad"), "version": "1.0.2"}


def test_an_app_without_the_gui_build_still_converts_with_the_console_build(monkeypatch, tmp_path):
    app = fake_app(tmp_path, gui=False)
    monkeypatch.setenv("HYIMG_FREECAD", str(app))
    fc = cad.freecad()
    assert fc["gui"] is None and fc["cmd"].endswith("/freecadcmd")


def test_a_freecadcmd_that_cannot_be_run_is_not_a_freecad(monkeypatch, tmp_path):
    monkeypatch.setenv("HYIMG_FREECAD", str(fake_app(tmp_path, executable=False)))
    assert cad.freecad() is None


def test_a_plain_folder_with_freecadcmd_is_found_without_a_version(monkeypatch, tmp_path):
    (tmp_path / "freecadcmd").write_text("#!/bin/sh\n")
    (tmp_path / "freecadcmd").chmod(0o755)
    monkeypatch.setenv("HYIMG_FREECAD", str(tmp_path))
    assert cad.freecad() == {"cmd": str(tmp_path / "freecadcmd"), "gui": None, "version": None}


def test_a_broken_info_plist_leaves_the_version_unknown(monkeypatch, tmp_path):
    app = fake_app(tmp_path, version=None)
    (app / "Contents/Info.plist").write_bytes(b"\x00 not a plist")
    monkeypatch.setenv("HYIMG_FREECAD", str(app))
    assert cad.freecad()["version"] is None


class Proxy:
    """a module with some of its functions replaced"""

    def __init__(self, real, **over):
        self._real, self._over = real, over

    def __getattr__(self, name):
        return self._over[name] if name in self._over else getattr(self._real, name)


class FakeDisk:
    """os.listdir / isfile / access / exists and shutil.which as cad.freecad() sees them, for the search without HYIMG_FREECAD:
    the real /Applications and /opt/homebrew are never looked at"""

    def __init__(self, monkeypatch, apps=(), user_apps=(), files=(), which=None):
        self.home_apps = os.path.expanduser("~/Applications")
        self.dirs = {"/Applications": list(apps), self.home_apps: list(user_apps)}
        self.files = set(files)
        monkeypatch.delenv("HYIMG_FREECAD", raising=False)
        # cad sees stand-ins for os and shutil; the real modules stay as they are for everything else
        path = Proxy(os.path, isfile=lambda p: p in self.files, exists=lambda p: p in self.files)
        monkeypatch.setattr(cad, "os", Proxy(os, path=path, listdir=self.listdir, access=lambda p, mode: p in self.files))
        monkeypatch.setattr(cad, "shutil", Proxy(cad.shutil, which=lambda name: which))
        monkeypatch.setattr(cad, "open", self.open, raising=False)

    def listdir(self, d):
        if d in self.dirs and self.dirs[d]:
            return list(self.dirs[d])
        raise FileNotFoundError(d)

    def open(self, *a, **k):
        raise FileNotFoundError(a[0])


def test_the_newest_named_freecad_app_in_applications_is_chosen(monkeypatch):
    disk = FakeDisk(monkeypatch, apps=["FreeCAD-0.21.app", "FreeCAD.app", "Blender.app"],
                    files={"/Applications/FreeCAD-0.21.app/Contents/Resources/bin/freecadcmd", "/Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd"})
    assert cad.freecad()["cmd"] == "/Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd"
    assert disk


def test_an_app_in_the_users_applications_folder_is_found(monkeypatch):
    home = os.path.expanduser("~/Applications")
    FakeDisk(monkeypatch, user_apps=["FreeCAD.app"], files={home + "/FreeCAD.app/Contents/Resources/bin/freecadcmd"})
    assert cad.freecad()["cmd"] == home + "/FreeCAD.app/Contents/Resources/bin/freecadcmd"


def test_without_an_app_the_homebrew_console_build_is_used(monkeypatch):
    FakeDisk(monkeypatch, files={"/opt/homebrew/bin/freecadcmd"})
    assert cad.freecad() == {"cmd": "/opt/homebrew/bin/freecadcmd", "gui": None, "version": None}


def test_freecadcmd_on_the_path_is_used_before_homebrew(monkeypatch):
    FakeDisk(monkeypatch, files={"/usr/x/freecadcmd", "/opt/homebrew/bin/freecadcmd"}, which="/usr/x/freecadcmd")
    assert cad.freecad()["cmd"] == "/usr/x/freecadcmd"


def test_an_app_bundle_is_preferred_to_a_console_build_on_the_path(monkeypatch):
    FakeDisk(monkeypatch, apps=["FreeCAD.app"], which="/usr/x/freecadcmd",
             files={"/usr/x/freecadcmd", "/Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd", "/Applications/FreeCAD.app/Contents/Resources/bin/freecad"})
    fc = cad.freecad()
    assert fc["cmd"].startswith("/Applications/FreeCAD.app/") and fc["gui"] == "/Applications/FreeCAD.app/Contents/Resources/bin/freecad"


def test_nothing_anywhere_means_there_is_no_freecad(monkeypatch):
    FakeDisk(monkeypatch, apps=["Blender.app", "FreeCAD-notes.txt"])
    assert cad.freecad() is None
