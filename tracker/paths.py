"""Where everything is stored.

program folder   the code and data/ (weekly job data). Replaced when you update.
home folder      per computer: downloaded data, fetched posting texts, e-mail login,
                 and a pointer to your progress folder.
                   * git checkout: <program>/my_data
                   * packaged release: Windows %APPDATA%\\AcademicJobTracker,
                     macOS ~/Library/Application Support/AcademicJobTracker,
                     Linux ~/.local/share/AcademicJobTracker
progress folder  your ticks, added jobs, preferences and backups. Defaults to the home
                 folder; can be moved to a cloud-synced folder (iCloud Drive, OneDrive,
                 Dropbox, Google Drive, Nutstore) so several computers share it.

TRACKER_DATA_ROOT (tests, demos) puts everything under <root>/data and <root>/my_data.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
APP_NAME = "AcademicJobTracker"
PORTABLE_MARKER = APP_DIR / "portable.txt"   # written by packaging/build.py
_POINTER = "progress_folder.json"


def is_portable() -> bool:
    return PORTABLE_MARKER.exists() or os.environ.get("TRACKER_PORTABLE") == "1"


def _platform_home() -> Path:
    if sys.platform.startswith("win"):
        return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / APP_NAME


def home_dir() -> Path:
    root = os.environ.get("TRACKER_DATA_ROOT")
    if root:
        return Path(root) / "my_data"
    return _platform_home() if is_portable() else APP_DIR / "my_data"


def repo_data_dir() -> Path:
    root = os.environ.get("TRACKER_DATA_ROOT")
    return Path(root) / "data" if root else APP_DIR / "data"


def latest_dir() -> Path:
    return home_dir() / "latest"          # downloaded from GitHub or scraped on this computer


def descriptions_dir() -> Path:
    return home_dir() / "descriptions"


def email_env() -> Path:
    return home_dir() / "email.env"       # never synced: stays on this computer


def user_dir() -> Path:
    """Folder with your progress (possibly a cloud-synced folder)."""
    try:
        target = json.loads((home_dir() / _POINTER).read_text(encoding="utf-8")).get("folder", "")
    except (OSError, ValueError):
        target = ""
    if target:
        p = Path(target).expanduser()
        if p.is_dir():
            return p
    return home_dir()


def user_dir_is_custom() -> bool:
    return user_dir() != home_dir()


def set_user_dir(folder: Path | None) -> None:
    home_dir().mkdir(parents=True, exist_ok=True)
    pointer = home_dir() / _POINTER
    if folder is None:
        pointer.unlink(missing_ok=True)
    else:
        pointer.write_text(json.dumps({"folder": str(Path(folder).expanduser())}), encoding="utf-8")


def apps_file() -> Path:
    return user_dir() / "applications.csv"


def manual_file() -> Path:
    return user_dir() / "manual_jobs.csv"


def prefs_file() -> Path:
    return user_dir() / "preferences.json"


def backup_dir() -> Path:
    return user_dir() / "backups"


def export_file() -> Path:
    return user_dir() / "My job applications.xlsx"   # read-only copy, e.g. for a phone


# Files that make up "your progress" (moved / merged when the folder changes).
PROGRESS_FILES = ("applications.csv", "manual_jobs.csv", "preferences.json")


def cloud_folders() -> list[tuple[str, Path]]:
    """Cloud-drive folders found on this computer, as (label, path)."""
    home = Path.home()
    cands: list[tuple[str, Path]] = [
        ("iCloud Drive", home / "Library" / "Mobile Documents" / "com~apple~CloudDocs"),
        ("iCloud Drive", home / "iCloudDrive"),
        ("Dropbox", home / "Dropbox"),
        ("Nutstore", home / "Nutstore Files"),
        ("Nutstore", home / "\u6211\u7684\u575a\u679c\u4e91"),   # Nutstore's default folder name on Chinese systems
    ]
    for env in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        if os.environ.get(env):
            cands.append(("OneDrive", Path(os.environ[env])))
    cands += [("OneDrive", p) for p in sorted(home.glob("OneDrive*"))]
    cloud_storage = home / "Library" / "CloudStorage"   # macOS: Google Drive, OneDrive, Dropbox
    if cloud_storage.is_dir():
        for p in sorted(cloud_storage.iterdir()):
            name = p.name.split("-")[0]
            label = {"GoogleDrive": "Google Drive", "OneDrive": "OneDrive", "Dropbox": "Dropbox"}.get(name, name)
            mydrive = p / "My Drive"
            cands.append((label, mydrive if mydrive.is_dir() else p))
    cands += [("Google Drive", p) for p in (home / "Google Drive", home / "My Drive", Path("G:/My Drive"))]
    seen, out = set(), []
    for label, p in cands:
        if p.is_dir() and str(p) not in seen:
            seen.add(str(p))
            out.append((label, p))
    return out


_CONFLICT = re.compile(r"^(applications|manual_jobs)(?!\.csv$).*\.csv$", re.I)


def conflict_copies() -> list[Path]:
    """Copies a sync service made when two computers saved at the same time
    (e.g. 'applications (Zoe's conflicted copy).csv', 'applications 2.csv', 'applications-LAPTOP.csv')."""
    d = user_dir()
    if not d.is_dir():
        return []
    return sorted(p for p in d.iterdir() if p.is_file() and _CONFLICT.match(p.name))
