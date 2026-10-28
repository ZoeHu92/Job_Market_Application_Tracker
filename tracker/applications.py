"""Your private application statuses, in your progress folder (see tracker/paths.py; never committed).

applications.csv  one row per job you have touched (ticks, dates, notes)
manual_jobs.csv   postings you added yourself (from an email, a school website, ...)
preferences.json  your default filters in the app
backups/          a dated copy of applications.csv and manual_jobs.csv, one per day (last 60 kept)
"""
from __future__ import annotations

import csv
import json
import shutil
import uuid
from datetime import date, datetime
from pathlib import Path

from . import paths
from .schema import APP_BOOL_COLUMNS, APP_COLUMNS, APP_DATE_COLUMNS, JOB_COLUMNS, STAGES

# Ticking a later stage implies the earlier ones.
_IMPLIES = {"interview": ["applied"], "flyout": ["interview", "applied"], "offer": ["applied"]}
_DATE_FOR = {"applied": "applied_date", "interview": "interview_date", "flyout": "flyout_date", "offer": "offer_date"}


def _truthy(v) -> bool:
    return str(v).strip().lower() in {"true", "1", "yes", "y", "x", "✓"}


def blank_app(job_id: str) -> dict:
    app = {c: "" for c in APP_COLUMNS}
    app["job_id"] = job_id
    for c in APP_BOOL_COLUMNS:
        app[c] = False
    return app


def load_applications(path: Path | None = None) -> dict[str, dict]:
    path = path or paths.apps_file()
    if not path.exists():
        return {}
    apps = {}
    with path.open(newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            app = blank_app(r.get("job_id", ""))
            for c in APP_COLUMNS:
                if c in APP_BOOL_COLUMNS:
                    app[c] = _truthy(r.get(c, ""))
                elif c != "job_id":
                    app[c] = r.get(c, "") or ""
            if app["job_id"]:
                apps[app["job_id"]] = app
    return apps


def is_empty(app: dict) -> bool:
    return not any(app.get(c) for c in APP_BOOL_COLUMNS) and not any(
        app.get(c) for c in [*APP_DATE_COLUMNS, "notes"])


def save_applications(apps: dict[str, dict], path: Path | None = None) -> None:
    path = path or paths.apps_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")  # hidden, so sync services ignore it
    with tmp.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=APP_COLUMNS)
        w.writeheader()
        for jid in sorted(apps):
            app = apps[jid]
            if is_empty(app):
                continue
            w.writerow({c: ("True" if app.get(c) is True else "" if app.get(c) is False else app.get(c, ""))
                        for c in APP_COLUMNS})
    tmp.replace(path)
    _daily_backup(path)


def _daily_backup(path: Path, keep: int = 60) -> None:
    if path not in (paths.apps_file(), paths.manual_file()):
        return
    backups = paths.backup_dir()
    backups.mkdir(parents=True, exist_ok=True)
    target = backups / f"{path.stem}-{date.today():%Y-%m-%d}.csv"
    shutil.copyfile(path, target)
    for old in sorted(backups.glob(f"{path.stem}-*.csv"))[:-keep]:
        old.unlink(missing_ok=True)


def _iso(v) -> str:
    """Date-like value from the UI (date, datetime, pandas Timestamp/NaT, str) → 'YYYY-MM-DD' or ''."""
    if v is None or (isinstance(v, float) and v != v) or str(v).strip().lower() in {"", "nat", "nan", "none"}:
        return ""
    if isinstance(v, datetime):  # also pandas.Timestamp
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    return str(v).strip()[:10]


def update_application(apps: dict[str, dict], job_id: str, changes: dict, today: date | None = None) -> dict:
    """Apply changes from the UI with the convenience rules:

    * ticking Applied / Interview / Flyout / Offer fills its date with today if empty
    * ticking a later stage also ticks the earlier ones (Flyout ⇒ Interview ⇒ Applied)
    * un-ticking a stage clears its date
    """
    today = today or date.today()
    app = apps.get(job_id) or blank_app(job_id)
    for k, v in changes.items():
        if k in APP_BOOL_COLUMNS:
            app[k] = bool(v) and str(v).lower() not in {"false", "nan", "none", ""}
        elif k in APP_DATE_COLUMNS:
            app[k] = _iso(v)
        elif k == "notes":
            app[k] = "" if v is None or (isinstance(v, float) and v != v) else str(v)
    for stage, implied in _IMPLIES.items():
        if app.get(stage):
            for other in implied:
                app[other] = True
    for stage, dcol in _DATE_FOR.items():
        if app.get(stage) and not app.get(dcol):
            app[dcol] = today.isoformat()
        if not app.get(stage) and dcol not in changes:
            app[dcol] = ""
    app["updated_at"] = datetime.now().isoformat(timespec="seconds")
    apps[job_id] = app
    return app


def stage_of(app: dict | None) -> str:
    if not app:
        return ""
    if app.get("rejected"):
        return "Rejected / closed"
    for key, label in STAGES:
        if app.get(key):
            return label
    return ""


# ---------------------------------------------------------------------------
# Manually added jobs
# ---------------------------------------------------------------------------

def load_manual_jobs(path: Path | None = None) -> dict[str, dict]:
    path = path or paths.manual_file()
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as fh:
        return {r["job_id"]: {c: r.get(c, "") or "" for c in JOB_COLUMNS} for r in csv.DictReader(fh)}


def save_manual_jobs(jobs: dict[str, dict], path: Path | None = None) -> None:
    path = path or paths.manual_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    with tmp.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=JOB_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for jid in sorted(jobs):
            w.writerow({c: jobs[jid].get(c, "") for c in JOB_COLUMNS})
    tmp.replace(path)
    _daily_backup(path)


def new_manual_id() -> str:
    return f"Manual:{uuid.uuid4().hex[:10]}"


# ---------------------------------------------------------------------------
# Preferences
# ---------------------------------------------------------------------------

def load_prefs(path: Path | None = None) -> dict:
    path = path or paths.prefs_file()
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_prefs(prefs: dict, path: Path | None = None) -> None:
    path = path or paths.prefs_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(prefs, indent=1), encoding="utf-8")


# ---------------------------------------------------------------------------
# Moving / merging the progress folder (cloud sync)
# ---------------------------------------------------------------------------

def _newer(a: dict, b: dict) -> dict:
    return a if (a.get("updated_at") or "") >= (b.get("updated_at") or "") else b


def merge_applications(*sets: dict[str, dict]) -> dict[str, dict]:
    """Union of several application sets; for a job in more than one, the latest edit wins."""
    out: dict[str, dict] = {}
    for apps in sets:
        for jid, app in apps.items():
            out[jid] = _newer(app, out[jid]) if jid in out else app
    return out


def move_progress(target: Path) -> str:
    """Point the progress folder at target (e.g. a cloud drive), merging with anything already there.

    Returns a short description of what happened.
    """
    target = Path(target).expanduser()
    target.mkdir(parents=True, exist_ok=True)
    source = paths.user_dir()
    here_apps, there_apps = load_applications(), load_applications(target / "applications.csv")
    here_jobs, there_jobs = load_manual_jobs(), load_manual_jobs(target / "manual_jobs.csv")
    merged = merge_applications(there_apps, here_apps)
    save_applications(merged, target / "applications.csv")
    save_manual_jobs({**there_jobs, **here_jobs}, target / "manual_jobs.csv")
    if not (target / "preferences.json").exists() and paths.prefs_file().exists():
        shutil.copyfile(paths.prefs_file(), target / "preferences.json")
    paths.set_user_dir(target)
    if source == paths.home_dir() and target != source:
        # Leaving this computer's own folder: archive the old copies so there is one live copy.
        # (A cloud folder is never emptied - other computers may still use it.)
        archive = source / "backups"
        archive.mkdir(parents=True, exist_ok=True)
        for name in paths.PROGRESS_FILES:
            if (source / name).exists():
                (source / name).replace(archive / f"before-sync-{name}")
    if there_apps and here_apps:
        return f"Merged: {len(merged)} tracked jobs ({len(there_apps)} were already in that folder)."
    if there_apps:
        return f"Using the {len(there_apps)} tracked jobs already in that folder."
    return f"Moved {len(here_apps)} tracked jobs there."


def resolve_conflict_copies() -> int:
    """Fold sync-conflict copies back into the main files, newest edit per job winning.
    The copies are moved into backups/. Returns how many copies were merged."""
    copies = paths.conflict_copies()
    if not copies:
        return 0
    apps, jobs = load_applications(), load_manual_jobs()
    backups = paths.backup_dir()
    backups.mkdir(parents=True, exist_ok=True)
    for c in copies:
        if c.name.lower().startswith("applications"):
            apps = merge_applications(apps, load_applications(c))
        else:
            jobs = {**load_manual_jobs(c), **jobs}
        c.replace(backups / f"merged-{c.name}")
    save_applications(apps)
    save_manual_jobs(jobs)
    return len(copies)
