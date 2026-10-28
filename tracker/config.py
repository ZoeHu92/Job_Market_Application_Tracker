"""Load config/settings.yaml and config/sources.yaml."""
from __future__ import annotations

import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
# Folder holding data/ and my_data/ (overridable for tests and demos).
DATA_ROOT = Path(os.environ.get("TRACKER_DATA_ROOT") or ROOT)

DEFAULT_SETTINGS = {
    "keep_full_description": False,
    "request_delay_seconds": 1.5,
    "max_new_details_per_source": 600,
    "closure_checks_per_source": 60,
    "weekly_digest_issue": True,
    "digest_fields": [],
    "github_repo": "ZoeHu92/Job_Market_Application_Tracker",
}


def load_settings(config_dir: str | Path = CONFIG_DIR) -> dict:
    path = Path(config_dir) / "settings.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    return {**DEFAULT_SETTINGS, **(data or {})}


def load_sources(config_dir: str | Path = CONFIG_DIR) -> list[dict]:
    path = Path(config_dir) / "sources.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return list(data.get("sources") or [])
