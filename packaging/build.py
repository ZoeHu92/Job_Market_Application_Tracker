"""Build a portable, double-click release of the tracker for the current OS.

    python packaging/build.py --version 1.0.0 --name windows-x64

Produces dist/AcademicJobTracker/ (python/ + app/ + a "Start Job Tracker" launcher)
and dist/AcademicJobTracker-<version>-<name>.zip. Needs uv (https://docs.astral.sh/uv/)
to download a relocatable Python, so the person using the release installs nothing.
"""
from __future__ import annotations

import argparse
import os
import shutil
import stat
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_FILES = ["app.py", "launch.py", "README.md", "requirements.txt", "LICENSE"]
APP_DIRS = ["tracker", "config", ".streamlit", "data"]
IS_WIN = sys.platform.startswith("win")

WIN_LAUNCHER = r"""@echo off
title Academic Job Market Tracker
cd /d "%~dp0app"
"%~dp0python\python.exe" launch.py
if errorlevel 1 pause
"""

MAC_LAUNCHER = """#!/bin/bash
# Double-click to start the tracker. The first time, macOS blocks it because this build is not signed by
# Apple: see README.txt for the one-time "Open Anyway" step.
DIR="$(cd "$(dirname "$0")" && pwd)"
# Files downloaded from the internet are flagged by macOS; clear the flag on this folder once.
xattr -dr com.apple.quarantine "$DIR" 2>/dev/null
cd "$DIR/app" || exit 1
exec "$DIR/python/bin/python3" launch.py
"""

README_TXT = """Academic Job Market Tracker {version}

Start:   {start}
Quit:    close the window that opens with it.

Your progress (ticks, dates, notes, added jobs) is private. It is stored only on
this computer, in
{data}
and is never uploaded. Because it is kept outside this folder, you can replace this
folder with a newer version at any time. To share progress between computers, open
Data & sources in the app and pick a cloud-drive folder (iCloud Drive, OneDrive,
Dropbox, Google Drive, Nutstore).

The job list updates itself from GitHub each week while you have internet.

User guide: https://github.com/ZoeHu92/Job_Market_Application_Tracker/blob/HEAD/docs/USER_GUIDE.md
Privacy:    https://github.com/ZoeHu92/Job_Market_Application_Tracker/blob/HEAD/PRIVACY.md
"""


def run(cmd: list[str], **kw) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, **kw)


def fetch_python(version: str, workdir: Path) -> Path:
    """Download a relocatable CPython (python-build-standalone) with uv; return its root folder."""
    if workdir.exists():
        shutil.rmtree(workdir)
    run(["uv", "python", "install", version, "--install-dir", str(workdir)])
    roots = [p for p in workdir.iterdir() if p.is_dir() and p.name.startswith("cpython-") and not p.is_symlink()]
    if not roots:
        raise SystemExit(f"no Python found in {workdir}")
    return max(roots, key=lambda p: len(p.name))  # the fully versioned folder, not the short alias


def python_exe(py_root: Path) -> Path:
    return py_root / "python.exe" if IS_WIN else py_root / "bin" / "python3"


def copy_app(dest: Path) -> None:
    dest.mkdir(parents=True)
    for f in APP_FILES:
        shutil.copy2(ROOT / f, dest / f)
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", "*.tmp")
    for d in APP_DIRS:
        if (ROOT / d).exists():
            shutil.copytree(ROOT / d, dest / d, ignore=ignore)
    (dest / "portable.txt").write_text(
        "Packaged release: progress is stored in your user folder, not here (see README.txt).\n")


def make_zip(folder: Path, zip_path: Path) -> None:
    if sys.platform == "darwin":
        # ditto keeps permissions, symlinks and extended attributes the way Finder expects
        run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(folder), str(zip_path)])
        return
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for path in sorted(folder.rglob("*")):
            arc = str(Path(folder.name) / path.relative_to(folder))
            st = path.lstat()
            if path.is_symlink():
                info = zipfile.ZipInfo(arc)
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                z.writestr(info, os.readlink(path))
            elif path.is_file():
                info = zipfile.ZipInfo.from_file(path, arc)
                info.external_attr = (st.st_mode & 0xFFFF) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                with open(path, "rb") as fh:
                    z.writestr(info, fh.read())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", required=True)
    ap.add_argument("--name", required=True, help="platform label used in the zip name, e.g. windows-x64")
    ap.add_argument("--python", default="3.12")
    ap.add_argument("--dist", default=str(ROOT / "dist"))
    args = ap.parse_args()

    dist = Path(args.dist)
    out = dist / "AcademicJobTracker"
    if out.exists():
        shutil.rmtree(out)
    dist.mkdir(parents=True, exist_ok=True)

    py_root = fetch_python(args.python, ROOT / "build" / "python")
    shutil.copytree(py_root, out / "python", symlinks=True)
    exe = python_exe(out / "python")
    run(["uv", "pip", "install", "--python", str(exe), "--break-system-packages", "--no-cache",
         "-r", str(ROOT / "packaging" / "requirements-release.txt")])
    copy_app(out / "app")
    # Byte-compile so the first start is quick.
    run([str(exe), "-m", "compileall", "-q", str(out / "app" / "tracker")])

    if IS_WIN:
        (out / "Start Job Tracker.bat").write_text(WIN_LAUNCHER.replace("\n", "\r\n"), encoding="ascii")
        start = ('double-click "Start Job Tracker.bat".\n'
                 '         If Windows says "Windows protected your PC": More info > Run anyway.')
        data = r"%APPDATA%\AcademicJobTracker"
    else:
        launcher = out / "Start Job Tracker.command"
        launcher.write_text(MAC_LAUNCHER, encoding="utf-8")
        launcher.chmod(0o755)
        start = ('double-click "Start Job Tracker.command".\n'
                 "         The first time, macOS blocks it because it is not signed by Apple. Click Done,\n"
                 "         then open System Settings > Privacy & Security, scroll down and click\n"
                 "         Open Anyway next to it (macOS 14 or older: right-click the file > Open > Open).")
        data = ("~/Library/Application Support/AcademicJobTracker" if sys.platform == "darwin"
                else "~/.local/share/AcademicJobTracker")
    (out / "README.txt").write_text(README_TXT.format(version=args.version, start=start, data=data), encoding="utf-8")
    (out / "app" / "VERSION").write_text(args.version + "\n")

    zip_path = dist / f"AcademicJobTracker-{args.version}-{args.name}.zip"
    zip_path.unlink(missing_ok=True)
    make_zip(out, zip_path)
    print(f"built {zip_path} ({zip_path.stat().st_size / 1e6:.0f} MB)")


if __name__ == "__main__":
    main()
