"""Progress folder: moving it to a (cloud) folder, merging two computers, sync-conflict copies."""
from datetime import date

import pytest

from tracker import applications as A
from tracker import paths


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setenv("TRACKER_DATA_ROOT", str(tmp_path / "pc"))
    monkeypatch.delenv("TRACKER_PORTABLE", raising=False)
    return tmp_path


def _tick(job, today, **changes):
    apps = A.load_applications()
    A.update_application(apps, job, changes, today)
    A.save_applications(apps)


def test_default_is_this_computer(root):
    assert paths.user_dir() == root / "pc" / "my_data"
    assert not paths.user_dir_is_custom()


def test_move_to_cloud_folder_then_second_computer_joins(root, monkeypatch):
    cloud = root / "Dropbox" / "AcademicJobTracker"
    _tick("AFA:1", date(2026, 10, 1), planned=True)
    msg = A.move_progress(cloud)
    assert "Moved 1" in msg and paths.user_dir() == cloud and paths.user_dir_is_custom()
    assert A.load_applications()["AFA:1"]["planned"]
    assert not (paths.home_dir() / "applications.csv").exists()  # archived, one live copy
    assert (paths.home_dir() / "backups" / "before-sync-applications.csv").exists()

    # second computer: its own home folder, its own earlier ticks
    monkeypatch.setenv("TRACKER_DATA_ROOT", str(root / "laptop"))
    _tick("JOE:9", date(2026, 10, 2), applied=True)
    msg = A.move_progress(cloud)
    assert msg.startswith("Merged: 2 tracked jobs")
    assert set(A.load_applications()) == {"AFA:1", "JOE:9"}


def test_newest_edit_wins_when_merging():
    old = {"j": {**A.blank_app("j"), "planned": True, "updated_at": "2026-10-01T10:00:00"}}
    new = {"j": {**A.blank_app("j"), "applied": True, "updated_at": "2026-10-03T09:00:00"}}
    assert A.merge_applications(new, old)["j"]["applied"]
    assert A.merge_applications(old, new)["j"]["applied"]


def test_conflict_copies_are_detected_and_merged(root):
    _tick("AFA:1", date(2026, 10, 1), planned=True)
    folder = paths.user_dir()
    other = {"AFA:2": {**A.blank_app("AFA:2"), "applied": True, "updated_at": "2026-10-05T09:00:00"}}
    A.save_applications(other, folder / "applications (Zoe's conflicted copy 2026-10-05).csv")
    (folder / "applications 2.csv").write_text((folder / "applications.csv").read_text())
    assert [p.name for p in paths.conflict_copies()] == ["applications (Zoe's conflicted copy 2026-10-05).csv",
                                                         "applications 2.csv"]
    assert A.resolve_conflict_copies() == 2
    assert set(A.load_applications()) == {"AFA:1", "AFA:2"}
    assert paths.conflict_copies() == []
    assert len(list(paths.backup_dir().glob("merged-*"))) == 2


def test_stop_syncing_returns_to_this_computer(root):
    cloud = root / "OneDrive" / "AcademicJobTracker"
    _tick("AFA:1", date(2026, 10, 1), offer=True)
    A.move_progress(cloud)
    A.move_progress(paths.home_dir())
    paths.set_user_dir(None)
    assert not paths.user_dir_is_custom()
    assert A.load_applications()["AFA:1"]["offer"]


def test_portable_build_uses_per_user_folder(monkeypatch, tmp_path):
    monkeypatch.delenv("TRACKER_DATA_ROOT", raising=False)
    monkeypatch.setenv("TRACKER_PORTABLE", "1")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setattr(paths.Path, "home", lambda: tmp_path)
    assert paths.home_dir().name == "AcademicJobTracker"
    assert paths.APP_DIR not in paths.home_dir().parents


def test_daily_backup_covers_ticks_and_added_jobs(root):
    _tick("AFA:1", date(2026, 10, 1), planned=True)
    A.save_manual_jobs({"Manual:abc": {"job_id": "Manual:abc", "title": "Assistant Professor of Finance"}})
    names = sorted(p.name.rsplit("-", 3)[0] for p in paths.backup_dir().glob("*.csv"))
    assert names == ["applications", "manual_jobs"]
