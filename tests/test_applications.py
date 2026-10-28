from datetime import date

from tracker import applications as A


def test_rules_fill_dates_and_imply_stages():
    apps = {}
    a = A.update_application(apps, "j", {"flyout": True}, date(2026, 11, 3))
    assert a["applied"] and a["interview"] and a["flyout"]
    assert a["applied_date"] == a["interview_date"] == a["flyout_date"] == "2026-11-03"
    a = A.update_application(apps, "j", {"flyout": False}, date(2026, 11, 4))
    assert not a["flyout"] and a["flyout_date"] == "" and a["interview"]


def test_user_dates_are_kept():
    apps = {}
    a = A.update_application(apps, "j", {"applied": True, "applied_date": "2026-10-01"}, date(2026, 11, 3))
    assert a["applied_date"] == "2026-10-01"


def test_save_load_roundtrip_and_empty_rows_dropped(tmp_path):
    apps = {}
    A.update_application(apps, "AFA:1", {"planned": True, "notes": 'Ask advisor, "quote"'})
    A.update_application(apps, "AFA:2", {"starred": False})
    path = tmp_path / "apps.csv"
    A.save_applications(apps, path)
    back = A.load_applications(path)
    assert list(back) == ["AFA:1"]
    assert back["AFA:1"]["planned"] is True and back["AFA:1"]["notes"] == 'Ask advisor, "quote"'


def test_stage_of():
    assert A.stage_of({"planned": True, "applied": True}) == "Applied"
    assert A.stage_of({"offer": True, "applied": True}) == "Offer"
    assert A.stage_of({"applied": True, "rejected": True}) == "Rejected / closed"
    assert A.stage_of({}) == ""
