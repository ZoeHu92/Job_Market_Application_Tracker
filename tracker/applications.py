"""Your private application statuses (my_data/, never committed).

applications.csv  one row per job you have touched (ticks, dates, notes)
manual_jobs.csv   postings you added yourself (from an email, a school website, ...)
preferences.json  your default filters in the app
backups/          a dated copy of applications.csv, one per day (last 60 kept)
"""
from __future__ import annotations

import csv
import json
import shutil
import uuid
from datetime import date, datetime
from pathlib import Path

from .config import DATA_ROOT
from .schema import APP_BOOL_COLUMNS, APP_COLUMNS, APP_DATE_COLUMNS, JOB_COLUMNS, STAGES

MY_DATA = DATA_ROOT / "my_data"
APPS_FILE = MY_DATA / "applications.csv"
MANUAL_FILE = MY_DATA / "manual_jobs.csv"
PREFS_FILE = MY_DATA / "preferences.json"
BACKUP_DIR = MY_DATA / "backups"

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


def load_applications(path: Path = APPS_FILE) -> dict[str, dict]:
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


def save_applications(apps: dict[str, dict], path: Path = APPS_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
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
    if path != APPS_FILE:
        return
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    target = BACKUP_DIR / f"applications-{date.today():%Y-%m-%d}.csv"
    shutil.copyfile(path, target)
    for old in sorted(BACKUP_DIR.glob("applications-*.csv"))[:-keep]:
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

def load_manual_jobs(path: Path = MANUAL_FILE) -> dict[str, dict]:
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as fh:
        return {r["job_id"]: {c: r.get(c, "") or "" for c in JOB_COLUMNS} for r in csv.DictReader(fh)}


def save_manual_jobs(jobs: dict[str, dict], path: Path = MANUAL_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=JOB_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for jid in sorted(jobs):
            w.writerow({c: jobs[jid].get(c, "") for c in JOB_COLUMNS})
    tmp.replace(path)


def new_manual_id() -> str:
    return f"Manual:{uuid.uuid4().hex[:10]}"


# ---------------------------------------------------------------------------
# Preferences
# ---------------------------------------------------------------------------

def load_prefs(path: Path = PREFS_FILE) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_prefs(prefs: dict, path: Path = PREFS_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(prefs, indent=1), encoding="utf-8")
