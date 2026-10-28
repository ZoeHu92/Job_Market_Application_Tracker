from datetime import date

import pandas as pd

from tests.sample_data import sample_rows
from tracker.view import Filters, apply_filters, build_frame, diff_edits, deadline_soon_list, summary_counts

TODAY = date(2026, 10, 28)


def frame(apps=None, manual=None):
    rows = sample_rows(TODAY)
    jobs = pd.DataFrame(list(rows.values())).astype(str).replace({"None": "", "nan": ""})
    return build_frame(jobs, manual or {}, apps or {}, TODAY)


def test_build_frame_columns_and_status():
    df = frame()
    assert df.index.is_unique and len(df) == 30
    passed = df[df["deadline_dt"] < pd.Timestamp(TODAY)]
    assert (passed["status_disp"] == "🟠 Deadline passed").all()
    assert df.loc["AFA:1001", "salary"].startswith("$220,000")


def test_filters():
    df = frame()
    fin = apply_filters(df, Filters(fields=["Finance"]), TODAY)
    assert set(fin["field"]) == {"Finance"} or all("Finance" in f for f in fin["fields"])
    assert "Master's+" not in set(apply_filters(df, Filters(), TODAY)["degree_req"])
    gc = apply_filters(df, Filters(regions=["Greater China"]), TODAY)
    assert set(gc["region"]) == {"Greater China"}
    hk = apply_filters(df, Filters(search="hong kong"), TODAY)
    assert len(hk) == 3
    soon = apply_filters(df, Filters(deadline_days=14), TODAY)
    assert soon["days_left"].between(0, 14).all()


def test_sort_puts_soonest_deadline_first_and_passed_last():
    view = apply_filters(df := frame(), Filters(phd_only=False), TODAY)
    dl = view["days_left"].dropna()
    upcoming = dl[dl >= 0]
    assert list(upcoming) == sorted(upcoming)
    assert view["deadline_dt"].iloc[-1] < pd.Timestamp(TODAY) or pd.isna(view["deadline_dt"].iloc[-1])
    assert len(df) >= len(view)


def test_tracking_columns_and_todo():
    apps = {"AFA:1001": {"planned": True}, "AAA:1009": {"applied": True, "applied_date": "2026-10-20"}}
    df = frame(apps)
    assert df.loc["AFA:1001", "stage"] == "Planned" and df.loc["AAA:1009", "stage"] == "Applied"
    assert summary_counts(df, TODAY)["tracked"] == 2
    todo = deadline_soon_list(df, TODAY)
    assert list(todo.index) == ["AFA:1001"]
    assert apply_filters(df, Filters(tracked_only=True), TODAY).index.tolist() != []


def test_diff_edits_normalizes_types():
    df = frame()
    cols = ["planned", "applied_date", "notes"]
    before = df[cols].copy()
    after = before.copy()
    after.loc["AFA:1001", "planned"] = True
    after.loc["AFA:1001", "applied_date"] = pd.Timestamp("2026-10-27")
    after.loc["AFA:1002", "notes"] = "email chair"
    assert diff_edits(before, after, cols) == {
        "AFA:1001": {"planned": True, "applied_date": "2026-10-27"}, "AFA:1002": {"notes": "email chair"}}
    assert diff_edits(before, before.copy(), cols) == {}
