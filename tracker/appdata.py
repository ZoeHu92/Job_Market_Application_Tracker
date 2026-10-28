"""Data plumbing for the app: pick the newest jobs file, download the weekly data, run a local scrape."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

from .applications import MY_DATA
from .config import DATA_ROOT, ROOT
from .schema import JOB_COLUMNS

REPO_DATA = DATA_ROOT / "data"
LOCAL_DATA = MY_DATA / "latest"   # downloaded from GitHub or scraped on this computer


def _report(folder: Path) -> dict:
    try:
        return json.loads((folder / "scrape_report.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def newest_data_dir() -> tuple[Path, dict]:
    """The folder (repo data/ or my_data/latest/) holding the most recent run."""
    best, best_rep = REPO_DATA, _report(REPO_DATA)
    rep = _report(LOCAL_DATA)
    if (LOCAL_DATA / "jobs.csv").exists() and rep.get("finished_at", "") > best_rep.get("finished_at", ""):
        best, best_rep = LOCAL_DATA, rep
    return best, best_rep


def read_jobs_frame(folder: Path) -> pd.DataFrame:
    path = folder / "jobs.csv"
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame(columns=JOB_COLUMNS)
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    for c in JOB_COLUMNS:
        if c not in df.columns:
            df[c] = ""
    return df[JOB_COLUMNS]


def download_latest(repo: str, timeout: float = 30) -> str:
    """Fetch data/jobs.csv and the report from the repo's default branch into my_data/latest/."""
    api = requests.get(f"https://api.github.com/repos/{repo}", timeout=timeout)
    api.raise_for_status()
    branch = api.json().get("default_branch", "main")
    LOCAL_DATA.mkdir(parents=True, exist_ok=True)
    for name in ("jobs.csv", "scrape_report.json", "skipped_ids.json"):
        r = requests.get(f"https://raw.githubusercontent.com/{repo}/{branch}/data/{name}", timeout=timeout)
        if r.status_code == 404:
            if name == "jobs.csv":
                raise FileNotFoundError(f"No data/jobs.csv on branch '{branch}' yet - has the weekly workflow run?")
            continue
        r.raise_for_status()
        (LOCAL_DATA / name).write_bytes(r.content)
    rep = _report(LOCAL_DATA)
    return f"Downloaded data from {repo}@{branch} (run finished {rep.get('finished_at', 'unknown')})."


def local_scrape_command(sources: list[str] | None = None) -> list[str]:
    base, _ = newest_data_dir()
    cmd = [sys.executable, "-m", "tracker.scrape", "--data-dir", str(LOCAL_DATA),
           "--baseline", str(base / "jobs.csv"), "--keep-description"]
    if sources:
        cmd += ["--sources", ",".join(sources)]
    return cmd


def run_local_scrape(sources: list[str] | None = None) -> subprocess.CompletedProcess:
    LOCAL_DATA.mkdir(parents=True, exist_ok=True)
    base, _ = newest_data_dir()
    if base != LOCAL_DATA and (base / "skipped_ids.json").exists() and not (LOCAL_DATA / "skipped_ids.json").exists():
        (LOCAL_DATA / "skipped_ids.json").write_bytes((base / "skipped_ids.json").read_bytes())
    return subprocess.run(local_scrape_command(sources), cwd=ROOT, capture_output=True, text=True, timeout=3 * 3600)


def data_is_stale(report: dict, days: int = 8) -> bool:
    fin = (report.get("run_date") or "")[:10]
    try:
        return date.fromisoformat(fin) < date.today() - timedelta(days=days)
    except ValueError:
        return True
