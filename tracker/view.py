"""Table building and filtering for the app (no Streamlit imports, so it is testable)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from .applications import stage_of
from .classify import format_salary, is_entry_level
from .schema import APP_BOOL_COLUMNS, APP_DATE_COLUMNS, JOB_COLUMNS

TRACK_COLUMNS = [*APP_BOOL_COLUMNS, *APP_DATE_COLUMNS, "notes"]


def _to_dt(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series.replace("", None), errors="coerce")


def _num(v):
    try:
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def build_frame(jobs: pd.DataFrame, manual: dict[str, dict], apps: dict[str, dict], today: date) -> pd.DataFrame:
    """One row per job (scraped + manual) with your statuses and display columns, indexed by job_id."""
    frames = [jobs[JOB_COLUMNS]] if len(jobs) else []
    if manual:
        frames.append(pd.DataFrame(list(manual.values()), columns=JOB_COLUMNS).fillna(""))
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=JOB_COLUMNS)
    df = df.astype(str).replace({"nan": "", "None": ""})
    df = df.drop_duplicates("job_id", keep="last").set_index("job_id", drop=False)
    df.index.name = None

    # Your tracking columns
    for c in APP_BOOL_COLUMNS:
        df[c] = [bool(apps.get(j, {}).get(c, False)) for j in df.index]
    for c in APP_DATE_COLUMNS:
        df[c] = _to_dt(pd.Series([apps.get(j, {}).get(c, "") for j in df.index], index=df.index))
    df["notes"] = [apps.get(j, {}).get("notes", "") for j in df.index]
    df["stage"] = [stage_of(apps.get(j)) for j in df.index]
    df["tracked"] = df["stage"] != ""

    # Display helpers
    t = pd.Timestamp(today)
    df["deadline_dt"] = _to_dt(df["deadline"])
    df["review_dt"] = _to_dt(df["review_start"])
    df["first_seen_dt"] = _to_dt(df["first_seen"])
    df["days_left"] = (df["deadline_dt"] - t).dt.days.astype("Int64")
    is_new = (df["first_seen_dt"] >= t - pd.Timedelta(days=7)) & (df["status"] == "Open")
    passed = (df["status"] == "Open") & (df["deadline_dt"] < t)
    df["status_disp"] = "🟢 Open"
    df.loc[is_new, "status_disp"] = "🆕 New"
    df.loc[passed, "status_disp"] = "🟠 Deadline passed"
    df.loc[df["status"] == "Closed", "status_disp"] = "⚫ Closed"
    df["is_new"] = is_new
    df["salary"] = [format_salary(_num(a), _num(b), c, raw) for a, b, c, raw in
                    zip(df["salary_min"], df["salary_max"], df["salary_currency"], df["salary_text"])]
    df["where"] = [", ".join(x for x in (loc if len(loc) <= 40 else "", ctry) if x) or reg
                   for loc, ctry, reg in zip(df["location"], df["country"], df["region"])]
    df["entry_level"] = df["rank"].map(is_entry_level)
    df["_search"] = (df["institution"] + " " + df["title"] + " " + df["department"] + " " + df["fields"] + " " +
                     df["location"] + " " + df["country"] + " " + df["requirements"] + " " + df["notes"] + " " +
                     df["categories"] + " " + df["description"].str[:3000]).str.lower()
    return df


@dataclass
class Filters:
    search: str = ""
    fields: list[str] = field(default_factory=list)       # empty = all
    ranks: list[str] = field(default_factory=list)
    regions: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    status: str = "Open"                                   # Open | Open + closed in last 30 days | All
    hide_passed: bool = False
    entry_level: bool = False
    tenure_only: bool = False
    phd_only: bool = True
    new_days: int = 0                                      # 0 = any
    deadline_days: int = 0                                 # 0 = any
    hide_duplicates: bool = True
    tracked_only: bool = False


def apply_filters(df: pd.DataFrame, f: Filters, today: date) -> pd.DataFrame:
    m = pd.Series(True, index=df.index)
    t = pd.Timestamp(today)
    if f.status == "Open":
        m &= df["status"] == "Open"
    elif f.status.startswith("Open +"):
        recent = _to_dt(df["closed_date"]) >= t - pd.Timedelta(days=30)
        m &= (df["status"] == "Open") | recent
    if f.hide_passed:
        m &= ~(df["deadline_dt"] < t)
    if f.fields:
        wanted = set(f.fields)
        m &= df["fields"].map(lambda s: bool(wanted & {x.strip() for x in s.split(";")})) | df["field"].isin(wanted)
    if f.ranks:
        m &= df["rank"].isin(f.ranks)
    if f.entry_level:
        m &= df["entry_level"]
    if f.regions:
        m &= df["region"].isin(f.regions)
    if f.sources:
        m &= df["source"].isin(f.sources)
    if f.tenure_only:
        m &= df["tenure_track"] != "No"
    if f.phd_only:
        m &= df["degree_req"] != "Master's+"
    if f.new_days:
        m &= df["first_seen_dt"] >= t - pd.Timedelta(days=f.new_days)
    if f.deadline_days:
        m &= df["deadline_dt"].between(t, t + pd.Timedelta(days=f.deadline_days))
    if f.hide_duplicates:
        m &= (df["duplicate_of"] == "") | df["tracked"]
    if f.tracked_only:
        m &= df["tracked"]
    if f.search.strip():
        for term in f.search.lower().split():
            m &= df["_search"].str.contains(term, regex=False)
    out = df[m]
    # Soonest deadline first; postings without a deadline after, newest first.
    return out.assign(_nodl=out["deadline_dt"].isna(), _passed=out["deadline_dt"] < t).sort_values(
        ["_passed", "_nodl", "deadline_dt", "first_seen_dt", "institution"],
        ascending=[True, True, True, False, True]).drop(columns=["_nodl", "_passed"])


def summary_counts(df: pd.DataFrame, today: date) -> dict:
    t = pd.Timestamp(today)
    open_ = df[(df["status"] == "Open") & (df["duplicate_of"] == "")]
    return {
        "open": len(open_),
        "new_week": int(open_["is_new"].sum()),
        "due_14": int(open_["deadline_dt"].between(t, t + pd.Timedelta(days=14)).sum()),
        "closed_week": int((_to_dt(df["closed_date"]) >= t - pd.Timedelta(days=7)).sum()),
        "tracked": int(df["tracked"].sum()),
    }


def normalize_cell(v, col: str):
    """Comparable value for a tracking cell coming back from st.data_editor."""
    if col in APP_BOOL_COLUMNS:
        return bool(v) if v is not None and not (isinstance(v, float) and v != v) and v is not pd.NA else False
    if col in APP_DATE_COLUMNS:
        if v is None or v is pd.NaT or (isinstance(v, float) and v != v):
            return ""
        try:
            ts = pd.Timestamp(v)
        except (ValueError, TypeError):
            return ""
        return "" if pd.isna(ts) else ts.date().isoformat()
    if v is None or v is pd.NA or (isinstance(v, float) and v != v):
        return ""
    return str(v)


def diff_edits(before: pd.DataFrame, after: pd.DataFrame, columns: list[str]) -> dict[str, dict]:
    """{job_id: {col: new_value}} for tracking cells the user changed in the editor."""
    changes: dict[str, dict] = {}
    for jid in before.index.intersection(after.index):
        for col in columns:
            a = normalize_cell(before.at[jid, col], col)
            b = normalize_cell(after.at[jid, col], col)
            if a != b:
                changes.setdefault(jid, {})[col] = b
    return changes


def deadline_soon_list(df: pd.DataFrame, today: date, days: int = 21) -> pd.DataFrame:
    """Jobs you plan to apply to (or starred) but have not applied to yet, by deadline."""
    t = pd.Timestamp(today)
    m = (df["planned"] | df["starred"]) & ~df["applied"] & ~df["rejected"] & (df["status"] == "Open")
    sub = df[m].copy()
    sub["_nodl"] = sub["deadline_dt"].isna()
    sub = sub[sub["_nodl"] | (sub["deadline_dt"] <= t + pd.Timedelta(days=days))]
    return sub.sort_values(["_nodl", "deadline_dt"]).drop(columns="_nodl")


def export_frame(df: pd.DataFrame) -> pd.DataFrame:
    cols = ["stage", *APP_BOOL_COLUMNS, *APP_DATE_COLUMNS, "notes", "institution", "title", "department", "field",
            "fields", "rank", "tenure_track", "degree_req", "deadline", "review_start", "deadline_note", "start_date",
            "salary", "location", "country", "region", "materials", "interview_venues", "requirements", "status",
            "status_note", "first_seen", "last_seen", "closed_date", "source", "url", "job_id"]
    out = df[cols].copy()
    for c in APP_DATE_COLUMNS:
        out[c] = out[c].dt.date
    return out
