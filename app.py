"""Academic Job Market Tracker - business-school faculty positions.

Run:  streamlit run app.py      (or double-click start_tracker.command / start_tracker.bat)
"""
from __future__ import annotations

import hashlib
import io
import os
import re
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from tracker import __version__, paths
from tracker import applications as A
from tracker.appdata import (data_is_stale, download_latest, load_jobs_union, newest_data_dir, run_local_scrape,
                             save_email_credentials)
from tracker.classify import fmt_date
from tracker.config import load_settings, load_sources
from tracker.enrich import enrich
from tracker.extract import extract_posting
from tracker.http import Fetcher, FetchError
from tracker.schema import APP_DATE_COLUMNS, FIELDS, RANKS, REGIONS
from tracker.sources.base import RawJob
from tracker.view import (TRACK_COLUMNS, Filters, apply_filters, build_frame, deadline_soon_list, diff_edits,
                          export_frame, normalize_cell, summary_counts)

st.set_page_config(page_title="Job Market Tracker", page_icon="🎓", layout="wide")

TODAY = date.today()
SETTINGS = load_settings()

ss = st.session_state
ss.setdefault("gens", {"jobs": 0, "apps": 0})

# --------------------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------------------

if "auto_checked" not in ss and not os.environ.get("TRACKER_NO_AUTO_UPDATE"):
    # Once per session: if the local copy is more than a week old, quietly fetch the
    # latest weekly data from GitHub (works without git; ignored when offline).
    ss.auto_checked = True
    _, _rep = newest_data_dir()
    if data_is_stale(_rep, days=7):
        try:
            download_latest(SETTINGS["github_repo"], timeout=8)
        except Exception:  # noqa: BLE001
            pass


@st.cache_data(show_spinner=False)
def _jobs_cached(stamp: tuple) -> tuple[pd.DataFrame, dict, str]:
    jobs, report, folder = load_jobs_union()
    return jobs, report, str(folder)


def _stamp() -> tuple:
    return tuple(p.stat().st_mtime if p.exists() else 0.0
                 for p in (paths.repo_data_dir() / "jobs.csv", paths.latest_dir() / "jobs.csv"))


JOBS, REPORT, _folder = _jobs_cached(_stamp())
DATA_DIR = Path(_folder)


def _latest_release() -> tuple[str, str]:
    """(tag, url) of the newest GitHub release, or ('', '') when offline."""
    try:
        import requests
        r = requests.get(f"https://api.github.com/repos/{SETTINGS['github_repo']}/releases/latest", timeout=5)
        if r.status_code == 200:
            d = r.json()
            return d.get("tag_name", ""), d.get("html_url", "")
    except Exception:  # noqa: BLE001
        pass
    return "", ""


def _version_tuple(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


if "release_checked" not in ss:
    ss.release_checked = True
    ss.new_release = ("", "")
    if paths.is_portable() and not os.environ.get("TRACKER_NO_AUTO_UPDATE"):
        tag, url = _latest_release()
        if tag and _version_tuple(tag) > _version_tuple(__version__):
            ss.new_release = (tag, url)
APPS = A.load_applications()
MANUAL = A.load_manual_jobs()
DF = build_frame(JOBS, MANUAL, APPS, TODAY)


def _refresh_excel_copy() -> None:
    """Keep 'My job applications.xlsx' next to a synced progress folder up to date (for phones)."""
    if not paths.user_dir_is_custom() or not paths.apps_file().exists():
        return
    out = paths.export_file()
    if out.exists() and out.stat().st_mtime >= paths.apps_file().stat().st_mtime:
        return
    try:
        export_frame(DF[DF["tracked"]]).to_excel(out, index=False, sheet_name="My applications")
    except OSError:
        pass  # e.g. the file is open in Excel; try again next time


_refresh_excel_copy()

# --------------------------------------------------------------------------------------
# Saving edits
# --------------------------------------------------------------------------------------


def persist(changes: dict[str, dict], editor: str | None = None) -> None:
    """Save tracking edits and refresh. Editors other than the one edited are reset so a
    stale edit buffer can never overwrite a newer change."""
    apps = A.load_applications()
    changed = reset_self = False
    for jid, ch in changes.items():
        before = {k: v for k, v in (apps.get(jid) or A.blank_app(jid)).items() if k != "updated_at"}
        after = A.update_application(apps, jid, ch)
        if {k: v for k, v in after.items() if k != "updated_at"} != before:
            changed = True
        # A convenience rule (e.g. Flyout implies Interview) overrode what was clicked.
        if any(normalize_cell(after.get(c), c) != v for c, v in ch.items()):
            reset_self = True
    if changed:
        A.save_applications(apps)
        st.toast("Saved", icon="✅")
    if changed or reset_self:
        for name in ss.gens:
            if name != editor or reset_self:
                ss.gens[name] += 1
        st.rerun()


CC = {
    "starred": st.column_config.CheckboxColumn("⭐", help="Shortlist / interested", width="small"),
    "planned": st.column_config.CheckboxColumn("Plan", help="Plan to apply", width="small"),
    "applied": st.column_config.CheckboxColumn("Applied", width="small"),
    "applied_date": st.column_config.DateColumn("Applied on", format="YYYY-MM-DD", width="small"),
    "interview": st.column_config.CheckboxColumn("Interview", help="First-round interview (FMA, AFA/ASSA, virtual…)",
                                                 width="small"),
    "interview_date": st.column_config.DateColumn("Interview on", format="YYYY-MM-DD", width="small"),
    "flyout": st.column_config.CheckboxColumn("Flyout", help="Campus visit", width="small"),
    "flyout_date": st.column_config.DateColumn("Flyout on", format="YYYY-MM-DD", width="small"),
    "offer": st.column_config.CheckboxColumn("Offer", width="small"),
    "offer_date": st.column_config.DateColumn("Offer on", format="YYYY-MM-DD", width="small"),
    "rejected": st.column_config.CheckboxColumn("✗ Out", help="Rejected, withdrew, or search cancelled", width="small"),
    "institution": st.column_config.TextColumn("School", width="medium"),
    "title": st.column_config.TextColumn("Position", width="large"),
    "field": st.column_config.TextColumn("Field", width="small"),
    "rank": st.column_config.TextColumn("Rank", width="small"),
    "deadline_dt": st.column_config.DateColumn("Deadline", format="MMM D, YYYY", width="small"),
    "days_left": st.column_config.NumberColumn("Days left", format="%d", width="small"),
    "salary": st.column_config.TextColumn("Salary", width="small"),
    "where": st.column_config.TextColumn("Location", width="small"),
    "status_disp": st.column_config.TextColumn("Status", width="small"),
    "stage": st.column_config.TextColumn("Stage", width="small"),
    "source": st.column_config.TextColumn("Board", width="small"),
    "url": st.column_config.LinkColumn("Posting", display_text="Open ↗", width="small"),
    "notes": st.column_config.TextColumn("Notes", width="medium"),
}


def tracking_editor(view: pd.DataFrame, columns: list[str], name: str, height: int | str = 620) -> None:
    editable = [c for c in columns if c in TRACK_COLUMNS]
    order_hash = hashlib.md5("|".join(view.index).encode()).hexdigest()[:10]
    shown = view[columns]
    edited = st.data_editor(
        shown, key=f"ed-{name}-{ss.gens[name]}-{order_hash}", column_config=CC, column_order=columns,
        disabled=[c for c in columns if c not in editable], hide_index=True, height=height, num_rows="fixed")
    changes = diff_edits(shown, edited, editable)
    if changes:
        persist(changes, editor=name)


def label_for(jid: str) -> str:
    r = DF.loc[jid]
    dl = f" · due {fmt_date(r['deadline_dt'].date())}" if pd.notna(r["deadline_dt"]) else ""
    return f"{r['institution'] or '(school?)'} — {r['title']}{dl}"


def open_details(jid: str) -> None:
    ss.detail_job = jid
    st.switch_page(PAGES["details"])


# --------------------------------------------------------------------------------------
# Sidebar filters (shared by all pages)
# --------------------------------------------------------------------------------------

FILTER_KEYS = {
    "search": "", "fields": [], "ranks": [], "entry_level": False, "regions": [], "sources": [],
    "status": "Open", "hide_passed": False, "tenure_only": False, "phd_only": True, "new_days": 0,
    "deadline_days": 0, "hide_duplicates": True,
}
STATUS_OPTIONS = ["Open", "Open + closed in last 30 days", "All"]
SOURCE_OPTIONS = sorted(set(DF["source"]) | {s["name"] for s in load_sources()})
OPTIONS = {"fields": FIELDS, "ranks": RANKS, "regions": REGIONS, "sources": SOURCE_OPTIONS}

if "filters_init" not in ss:
    ss.filters_init = True
    prefs = A.load_prefs()
    for k, default in FILTER_KEYS.items():
        v = prefs.get(k, default)
        if k in OPTIONS:
            v = [x for x in v if x in OPTIONS[k]]
        if k == "status" and v not in STATUS_OPTIONS:
            v = "Open"
        ss[f"f_{k}"] = v


def _reset_filters() -> None:
    for k, v in FILTER_KEYS.items():
        ss[f"f_{k}"] = v


with st.sidebar:
    st.subheader("Filters")
    st.text_input("Search", key="f_search", placeholder="school, keyword, city, JEL…")
    st.multiselect("Fields", FIELDS, key="f_fields", placeholder="All fields")
    st.multiselect("Rank", RANKS, key="f_ranks", placeholder="All ranks")
    st.checkbox("Entry level only", key="f_entry_level",
                help="Assistant, Assistant/Associate, Open rank, Lecturer (UK etc.), Postdoc, Visiting, Unspecified")
    st.multiselect("Region", REGIONS, key="f_regions", placeholder="Anywhere")
    st.selectbox("Status", STATUS_OPTIONS, key="f_status")
    st.checkbox("Hide jobs whose deadline has passed", key="f_hide_passed")
    st.checkbox("Tenure-track / research positions only", key="f_tenure_only",
                help="Hides positions marked clinical, teaching, visiting, postdoc or non-tenure.")
    st.checkbox("PhD-level positions only", key="f_phd_only", help="Hides postings that only ask for a master's degree.")
    st.selectbox("Posted within", [0, 7, 14, 30], key="f_new_days",
                 format_func=lambda d: "Any time" if not d else f"Last {d} days")
    st.selectbox("Deadline within", [0, 7, 14, 30, 60], key="f_deadline_days",
                 format_func=lambda d: "Any" if not d else f"Next {d} days")
    st.multiselect("Job boards", SOURCE_OPTIONS, key="f_sources", placeholder="All boards")
    st.checkbox("Hide cross-posted duplicates", key="f_hide_duplicates",
                help="The same position listed on several boards is shown once.")
    c1, c2 = st.columns(2)
    if c1.button("Save as default", width="stretch", help="Use these filters every time the app opens"):
        A.save_prefs({k: ss[f"f_{k}"] for k in FILTER_KEYS})
        st.toast("Default filters saved", icon="💾")
    c2.button("Reset", width="stretch", on_click=_reset_filters)

FILTERS = Filters(**{k: ss[f"f_{k}"] for k in FILTER_KEYS})

with st.sidebar:
    if ss.new_release[0]:
        st.info(f"Version {ss.new_release[0]} is available (you have v{__version__}). "
                f"[Download it]({ss.new_release[1]}); your progress is kept.", icon="⬆️")
    st.caption(f"Academic Job Market Tracker v{__version__}")


def common_banners() -> None:
    if ss.get("flash"):
        st.success(ss.pop("flash"))
    copies = paths.conflict_copies()
    if copies:
        c1, c2 = st.columns([4, 1])
        c1.warning(f"Your cloud drive made {len(copies)} conflict copies of your progress "
                   f"({', '.join(p.name for p in copies[:3])}), probably because two computers saved at the "
                   "same time. Merge them so no tick is lost.", icon="⚠️")
        if c2.button("Merge now", type="primary"):
            n = A.resolve_conflict_copies()
            ss.flash = f"Merged {n} conflict copies; the newest change for each job was kept."
            for k in ss.gens:
                ss.gens[k] += 1
            st.rerun()


# --------------------------------------------------------------------------------------
# Pages
# --------------------------------------------------------------------------------------


def data_banner() -> None:
    if not REPORT:
        return
    run = REPORT.get("run_date", "?")
    where = "weekly GitHub run" if DATA_DIR != paths.latest_dir() else "latest download / local scrape"
    bad = [s["name"] for s in REPORT.get("sources", []) if not s.get("ok")]
    msg = f"Data from {run} ({where})."
    if bad:
        msg += f" Boards with problems this run: {', '.join(bad)} — see Data & sources."
    st.caption(msg)
    if data_is_stale(REPORT, days=8):
        st.warning("The job data is more than a week old. Go to **Data & sources** to fetch the latest.", icon="⏰")


def welcome() -> None:
    st.info(
        "**No postings yet.** The job list fills up after the first weekly scrape. Either:\n\n"
        "1. On GitHub: **Actions → Weekly job scrape → Run workflow** (then *Get latest data* on the Data & sources page), or\n"
        "2. **Data & sources → Run the scraper now** (on this computer), or\n"
        "3. Add postings yourself on the **Add jobs** page.", icon="👋")


def page_jobs() -> None:
    st.title("🎓 Business-school job market")
    common_banners()
    data_banner()
    if DF.empty:
        welcome()
        return
    c = summary_counts(DF, TODAY)
    m = st.columns(5)
    m[0].metric("Open positions", c["open"])
    m[1].metric("New this week", c["new_week"])
    m[2].metric("Deadlines ≤ 14 days", c["due_14"])
    m[3].metric("Closed this week", c["closed_week"])
    m[4].metric("You're tracking", c["tracked"])

    view = apply_filters(DF, FILTERS, TODAY)
    st.caption(f"**{len(view)}** positions match your filters. Tick the boxes to track your progress — "
               "changes save automatically. Ticking a later stage fills in the earlier ones and today's date.")
    if view.empty:
        st.write("Nothing matches — try clearing some filters in the sidebar.")
        return
    tracking_editor(view, ["starred", "planned", "applied", "interview", "flyout", "offer", "rejected",
                           "institution", "title", "deadline_dt", "days_left", "field", "rank", "salary", "where",
                           "status_disp", "url", "source", "notes"], "jobs")
    pick = st.selectbox("See full details for", view.index, index=None, format_func=label_for,
                        placeholder="Choose a position…")
    if pick:
        open_details(pick)


def page_mine() -> None:
    st.title("✅ My applications")
    common_banners()
    tracked = DF[DF["tracked"]]
    counts = [("⭐ Starred", "starred"), ("📝 Planned", "planned"), ("📤 Applied", "applied"),
              ("🎤 Interviews", "interview"), ("✈️ Flyouts", "flyout"), ("🎉 Offers", "offer"), ("✗ Out", "rejected")]
    cols = st.columns(len(counts))
    for col, (label, key) in zip(cols, counts):
        col.metric(label, int(tracked[key].sum()) if len(tracked) else 0)
    if tracked.empty:
        st.info("You are not tracking anything yet. Tick **⭐** or **Plan** next to a job on the Jobs page.", icon="☝️")
        return

    todo = deadline_soon_list(DF, TODAY)
    if len(todo):
        st.subheader("⏰ To apply — planned or starred, not yet sent")
        for jid, r in todo.iterrows():
            if pd.isna(r["deadline_dt"]):
                when, color = "no deadline stated", "gray"
            else:
                d = int(r["days_left"])
                when = "due today" if d == 0 else (f"{-d} days overdue" if d < 0 else f"{d} days left")
                color = "red" if d <= 7 else ("orange" if d <= 14 else "blue")
            line = st.columns([6, 2, 1])
            line[0].markdown(f"**{r['institution']}** — {r['title']}  \n"
                             f"<small>{r['deadline_note'] or ''}</small>", unsafe_allow_html=True)
            line[1].badge(when, color=color)
            if line[2].button("Details", key=f"todo-{jid}"):
                open_details(jid)

    st.subheader("Pipeline")
    order = {"Offer": 0, "Flyout": 1, "Interview": 2, "Applied": 3, "Planned": 4, "Starred": 5, "Rejected / closed": 6}
    view = tracked.assign(_o=tracked["stage"].map(order)).sort_values(["_o", "deadline_dt"]).drop(columns="_o")
    tracking_editor(view, ["stage", "institution", "title", "field", "deadline_dt", "starred", "planned", "applied",
                           "applied_date", "interview", "interview_date", "flyout", "flyout_date", "offer",
                           "offer_date", "rejected", "status_disp", "url", "notes"], "apps", height="auto")
    buf = io.BytesIO()
    export_frame(view).to_excel(buf, index=False, sheet_name="My applications")
    st.download_button("⬇️ Download my applications (Excel)", buf.getvalue(), "my_applications.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def _cached_description(url: str) -> str:
    path = paths.descriptions_dir() / (hashlib.sha1(url.encode()).hexdigest()[:16] + ".txt")
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _fetch_description(url: str) -> str:
    r = Fetcher(delay=0).get(url)
    text = extract_posting(r.content, r.url)["description"]
    cache = paths.descriptions_dir()
    cache.mkdir(parents=True, exist_ok=True)
    (cache / (hashlib.sha1(url.encode()).hexdigest()[:16] + ".txt")).write_text(text, encoding="utf-8")
    return text


def page_details() -> None:
    st.title("🔍 Job details")
    common_banners()
    if DF.empty:
        welcome()
        return
    view = apply_filters(DF, FILTERS, TODAY)
    options = list(dict.fromkeys([*([ss.detail_job] if ss.get("detail_job") in DF.index else []), *view.index]))
    if not options:
        st.write("No positions match the sidebar filters.")
        return
    jid = st.selectbox("Position", options, format_func=label_for, key="detail_pick")
    ss.detail_job = jid
    r = DF.loc[jid]

    st.header(r["title"] or "(untitled)")
    st.markdown(f"**{r['institution']}**" + (f" · {r['department']}" if r["department"] else "")
                + (f" · {r['location'] or r['country']}" if (r["location"] or r["country"]) else ""))
    badges = st.container(horizontal=True)
    badges.badge(r["status_disp"], color="green" if r["status"] == "Open" else "gray")
    badges.badge(r["field"], color="blue")
    badges.badge(r["rank"], color="violet")
    if r["tenure_track"] == "Yes":
        badges.badge("Tenure track", color="green")
    if r["stage"]:
        badges.badge(f"My stage: {r['stage']}", color="orange")
    if r["duplicate_of"]:
        badges.badge("Also posted on another board", color="gray")

    left, right = st.columns([3, 2], gap="large")
    with left:
        facts = {
            # the note reads "Deadline Oct 30, 2026; review begins ..." and the label already says Deadline
            "Deadline": re.sub(r"^Deadline\s+", "", r["deadline_note"]) or (
                fmt_date(r["deadline_dt"].date()) if pd.notna(r["deadline_dt"]) else "Not stated"),
            "Start date": r["start_date"] or "—",
            "Salary": r["salary"] or "Not stated",
            "Degree": r["degree_req"],
            "Tenure track": r["tenure_track"],
            "All fields": r["fields"] or r["field"],
            "Materials requested": r["materials"] or "—",
            "Interviews at": r["interview_venues"] or "—",
            "Board / categories": f"{r['source']}" + (f" — {r['categories']}" if r["categories"] else ""),
            "Posted / first seen": f"{r['posted_date'] or '?'} / {r['first_seen'] or '?'}",
            "Last seen on board": r["last_seen"] or "—",
            "Status note": r["status_note"] or "—",
        }
        st.markdown("  \n".join(f"**{k}:** {str(v).replace('$', chr(92) + '$')}" for k, v in facts.items()))
        if r["url"]:
            st.link_button("Open the original posting ↗", r["url"], type="primary")
        if r["requirements"]:
            st.markdown("**Requirements (extracted)**")
            st.write(r["requirements"])
        text = r["description"] or (_cached_description(r["url"]) if r["url"] else "")
        if text:
            with st.expander("Full posting text", expanded=not r["requirements"]):
                st.text(text)
        elif r["url"] and st.button("Load full posting text from the board"):
            try:
                _fetch_description(r["url"])
                st.rerun()
            except FetchError as exc:
                st.error(f"Could not load the page: {exc.reason}")

    with right:
        st.subheader("My progress")
        app = APPS.get(jid) or A.blank_app(jid)
        with st.form(f"form-{jid}"):
            starred = st.checkbox("⭐ Interested / shortlist", app["starred"])
            planned = st.checkbox("📝 Plan to apply", app["planned"])
            vals = {"starred": starred, "planned": planned}
            for key, label in (("applied", "📤 Applied"), ("interview", "🎤 First-round interview"),
                               ("flyout", "✈️ Flyout / campus visit"), ("offer", "🎉 Offer")):
                c1, c2 = st.columns([1, 1])
                vals[key] = c1.checkbox(label, app[key])
                dv = app.get(f"{key}_date") or None
                vals[f"{key}_date"] = c2.date_input("Date", date.fromisoformat(dv) if dv else None,
                                                    key=f"{jid}-{key}-date", label_visibility="collapsed",
                                                    format="YYYY-MM-DD")
            vals["rejected"] = st.checkbox("✗ Rejected / withdrew / search cancelled", app["rejected"])
            vals["notes"] = st.text_area("Notes", app["notes"], placeholder="Contacts, materials tailored, "
                                         "interview questions, offer terms…", height=140)
            if st.form_submit_button("Save", type="primary", width="stretch"):
                apps = A.load_applications()
                A.update_application(apps, jid, vals)
                A.save_applications(apps)
                for k in ss.gens:
                    ss.gens[k] += 1
                st.toast("Saved", icon="✅")
                st.rerun()
        if jid.startswith("Manual:") and st.button("Delete this manually added job"):
            jobs = A.load_manual_jobs()
            jobs.pop(jid, None)
            A.save_manual_jobs(jobs)
            ss.pop("detail_job", None)
            st.rerun()


def import_saved_pages() -> None:
    st.subheader("📥 From FMA or another member-only board")
    st.markdown(
        "1. Log in to the board in your browser and open its job list (FMA: *For Job Seekers → View Positions on "
        "the Professional Job Board*).\n"
        "2. Save the page: **Ctrl+S** (Windows) or **Cmd+S** (Mac). In Safari choose *Format: Page Source*.\n"
        "3. Drop the saved `.html` file(s) here. Postings already in the tracker, from any board, are skipped.")
    c1, c2 = st.columns([1, 3])
    board = c1.selectbox("Board", ["FMA", "AMA", "AOM", "INFORMS", "AIS", "jobs.ac.uk", "Other"], key="import_board")
    files = c2.file_uploader("Saved page(s)", type=["html", "htm"], accept_multiple_files=True, key="import_pages")
    if files and st.button("Import postings", type="primary"):
        from tracker.importer import find_existing, jobs_from_saved_page
        jobs = A.load_manual_jobs()
        existing = list(zip(DF.index, DF["title"], DF["institution"], DF["field"]))
        found = added = 0
        for f in files:
            for raw in jobs_from_saved_page(f.getvalue().decode("utf-8", "replace"), board, today=TODAY):
                found += 1
                row = enrich(raw, TODAY, keep_description=True)
                if find_existing(raw.title, raw.institution, existing, row["field"]):
                    continue
                jid = A.new_manual_id()
                row.update(job_id=jid, source=raw.source, source_id=jid.split(":", 1)[1], status="Open",
                           first_seen=TODAY.isoformat(), last_seen=TODAY.isoformat())
                jobs[jid] = row
                existing.append((jid, row["title"], row["institution"], row["field"]))
                added += 1
        A.save_manual_jobs(jobs)
        if found:
            st.success(f"Found {found} postings: {added} new, {found - added} already in the tracker.")
        else:
            st.warning("No postings found in that file. Make sure you saved the job *list* page after logging in "
                       "(if the list sits inside a frame, open it in its own tab first).")


def page_add() -> None:
    st.title("➕ Add jobs")
    common_banners()
    import_saved_pages()
    st.divider()
    st.subheader("✍️ One posting at a time")
    st.write("From a school's website, a listserv e-mail or your advisor: paste the link (or the text) to fill "
             "the form automatically, then check it.")
    url = st.text_input("Posting URL (optional)", key="add_url", placeholder="https://…")
    if st.button("Fetch details from this link", disabled=not url):
        try:
            r = Fetcher(delay=0).get(url)
            d = extract_posting(r.content, r.url)
            raw = RawJob(source="Manual", source_id="new", url=url, title=d["title"], institution=d["institution"],
                         department=d["department"], location=d["location"], country=d["country"],
                         categories=d["categories"], description=d["description"], posted_date=d["posted_date"],
                         deadline_raw=d["deadline_raw"], salary_label=d["salary_label"],
                         **{k: d[k] for k in ("salary_min", "salary_max", "salary_currency", "salary_text") if d.get(k)})
            ss.add_prefill = enrich(raw, TODAY, keep_description=True)
            st.success("Filled in what could be found — please check every field.")
        except FetchError as exc:
            st.error(f"Could not load the page ({exc.reason}). Fill in the form by hand.")
    with st.expander("…or paste the posting text (listserv e-mail, PDF, WeChat article)"):
        pasted = st.text_area("Posting text", key="add_text", height=180,
                              placeholder="Paste the whole announcement here; the first line is used as the title.")
        if st.button("Fill the form from this text", disabled=not pasted.strip()):
            lines = [ln.strip() for ln in pasted.strip().splitlines() if ln.strip()]
            from tracker.sources.board import institution_from_text
            raw = RawJob(source="Manual", source_id="new", url="", title=lines[0][:200],
                         institution=institution_from_text(pasted[:400]), description=pasted)
            ss.add_prefill = enrich(raw, TODAY, keep_description=True)
            st.success("Filled in what could be found — please check every field.")
    pre = ss.get("add_prefill") or {}

    with st.form("add-job", clear_on_submit=True):
        c1, c2 = st.columns(2)
        inst = c1.text_input("School / institution *", pre.get("institution", ""))
        title = c2.text_input("Position title *", pre.get("title", ""))
        dept = c1.text_input("Department", pre.get("department", ""))
        loc = c2.text_input("Location", pre.get("location", ""))
        field_i = FIELDS.index(pre["field"]) if pre.get("field") in FIELDS else 0
        fld = c1.selectbox("Field", FIELDS, index=field_i)
        rank_i = RANKS.index(pre["rank"]) if pre.get("rank") in RANKS else 0
        rank = c2.selectbox("Rank", RANKS, index=rank_i)
        region_i = REGIONS.index(pre["region"]) if pre.get("region") in REGIONS else 0
        region = c1.selectbox("Region", REGIONS, index=region_i)
        dl_pre = date.fromisoformat(pre["deadline"]) if pre.get("deadline") else None
        deadline = c2.date_input("Application deadline", dl_pre, format="YYYY-MM-DD")
        salary = c1.text_input("Salary", pre.get("salary_text", ""))
        link = c2.text_input("Link", pre.get("url", "") or url)
        reqs = st.text_area("Requirements / notes about the posting", pre.get("requirements", ""), height=120)
        plan = st.checkbox("Mark as **Plan to apply**", True)
        if st.form_submit_button("Add job", type="primary"):
            if not inst.strip() or not title.strip():
                st.error("School and position title are required.")
            else:
                row = dict(pre)
                jid = A.new_manual_id()
                row.update(job_id=jid, source="Manual", source_id=jid.split(":", 1)[1], institution=inst.strip(),
                           title=title.strip(), department=dept, location=loc, field=fld,
                           fields=pre.get("fields") or fld, rank=rank, region=region,
                           deadline=deadline.isoformat() if deadline else "", salary_text=salary, url=link,
                           requirements=reqs, status="Open", first_seen=TODAY.isoformat(),
                           last_seen=TODAY.isoformat())
                if deadline and not row.get("deadline_note"):
                    row["deadline_note"] = f"Deadline {fmt_date(deadline)}"
                jobs = A.load_manual_jobs()
                jobs[jid] = row
                A.save_manual_jobs(jobs)
                if plan:
                    apps = A.load_applications()
                    A.update_application(apps, jid, {"planned": True})
                    A.save_applications(apps)
                ss.pop("add_prefill", None)
                st.success(f"Added {inst} — {title}.")

    if MANUAL:
        st.subheader("Jobs you added")
        mdf = DF.loc[[j for j in MANUAL if j in DF.index]]
        st.dataframe(mdf[["institution", "title", "field", "deadline_dt", "stage", "url"]], hide_index=True,
                     column_config=CC)
        st.caption("To edit or delete one, open it on the Job details page.")


def progress_folder_section() -> None:
    st.subheader("💾 Where your progress is stored")
    current = paths.user_dir()
    if paths.user_dir_is_custom():
        st.success(f"Synced folder: `{current}`", icon="☁️")
    else:
        st.info(f"This computer only: `{current}`", icon="💻")
    st.caption("Your progress is private: it is kept only in this folder and is never uploaded to GitHub or "
               "anywhere else. See PRIVACY.md in the repository for details.")
    st.markdown(
        "**Use the tracker on several computers:** keep your progress in a cloud-drive folder (iCloud Drive, "
        "OneDrive, Dropbox, Google Drive, Nutstore). Choose the same folder on each computer; ticks, dates, notes "
        "and added jobs then stay in sync. Your phone can open the read-only copy *My job applications.xlsx* from "
        "that folder in the cloud-drive app. The weekly job list is downloaded on each computer separately.")
    found = paths.cloud_folders()
    labels = [f"{label}: {p}" for label, p in found] + ["Another folder..."]
    c1, c2 = st.columns([3, 2])
    choice = c1.selectbox("Cloud-drive folder", labels, key="sync_choice")
    if choice == "Another folder...":
        typed = c1.text_input("Folder path", key="sync_path",
                              placeholder="e.g. /Users/you/Dropbox  or  C:\\Users\\you\\OneDrive")
        base = Path(typed).expanduser() if typed.strip() else None
    else:
        base = found[labels.index(choice)][1]
    target = base / paths.APP_NAME if base else None
    if target:
        c1.caption(f"Progress will be kept in `{target}`. If that folder already has progress from another "
                   "computer, the two are merged (the newest change for each job wins).")
    if c2.button("☁️ Use this folder", disabled=target is None or target == current, type="primary"):
        if not target.parent.is_dir():
            st.error(f"Folder not found: {target.parent}")
        else:
            ss.flash = A.move_progress(target)
            st.rerun()
    if paths.user_dir_is_custom() and c2.button("💻 Stop syncing (keep a copy on this computer only)"):
        ss.flash = A.move_progress(paths.home_dir())
        paths.set_user_dir(None)
        st.rerun()


def _report_sources(folder: Path) -> list[dict]:
    try:
        import json
        return json.loads((folder / "scrape_report.json").read_text(encoding="utf-8")).get("sources", [])
    except (OSError, ValueError):
        return []


def page_data() -> None:
    st.title("⚙️ Data & sources")
    common_banners()
    where = "the weekly GitHub run (data/)" if DATA_DIR != paths.latest_dir() else "my_data/latest (download or local scrape)"
    if REPORT:
        t = REPORT.get("totals", {})
        st.write(f"Showing data from **{where}**, run on **{REPORT.get('run_date', '?')}** — "
                 f"{t.get('open', 0)} open of {t.get('jobs', 0)} tracked postings.")
    else:
        st.write("No scrape has run yet.")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Get the latest weekly data**  \nDownloads what the GitHub workflow collected (takes seconds).")
        if st.button("⬇️ Get latest data from GitHub", type="primary"):
            with st.spinner("Downloading…"):
                try:
                    st.success(download_latest(SETTINGS["github_repo"]))
                    st.cache_data.clear()
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Download failed: {exc}")
    with c2:
        st.markdown("**Scrape now from this computer**  \nVisits every board with your own internet connection. "
                    "Takes 10–30 minutes; leave this tab open.")
        if st.button("🕷️ Run the scraper now"):
            with st.spinner("Scraping job boards… this can take a while."):
                proc = run_local_scrape()
            if proc.returncode == 0:
                st.success("Done.")
                st.cache_data.clear()
            else:
                st.error("The scraper reported a problem.")
            with st.expander("Scraper output"):
                st.code((proc.stdout or "")[-6000:] + (proc.stderr or "")[-4000:])

    progress_folder_section()

    with st.expander("Advanced (optional): read job-alert e-mails automatically"):
        st.caption("Most people do not need this: the Add jobs page imports member-only boards from a saved page. "
                   "Use this only if you want alert e-mails (FMA, AMA, SSRN, listservs) read without any clicks.")
        st.markdown(
            "Boards that need a member login or block automated access can still reach the tracker through their "
            "**job-alert e-mails**. Set up the alerts on each site, add a mail filter that puts them (and listserv "
            f"posts) in one label, e.g. **{SETTINGS['email']['folder']}**, then enter a mailbox *app password* below. "
            "The tracker only reads that one folder. Full steps are in the README under *Email alerts*.")
        m1, m2 = st.columns([3, 2])
        with m1.form("email-setup"):
            st.caption(f"Mail server: {SETTINGS['email']['imap_host']} · folder: {SETTINGS['email']['folder']} "
                       "(change both in config/settings.yaml)")
            user = st.text_input("E-mail address", placeholder="you@gmail.com")
            pw = st.text_input("App password", type="password",
                               help="Gmail: Google Account → Security → 2-Step Verification → App passwords. "
                                    "Not your normal password; you can revoke it any time.")
            if st.form_submit_button("Save on this computer"):
                if user and pw:
                    save_email_credentials(user, pw)
                    st.success(f"Saved to {paths.email_env()} (stays on this computer).")
                else:
                    st.error("Enter both the address and the app password.")
        with m2:
            configured = paths.email_env().exists() or bool(os.environ.get("TRACKER_IMAP_USER"))  # after a save above
            st.write("Status: " + ("✅ mailbox configured" if configured else "not set up yet"))
            if st.button("📬 Check my e-mail alerts now", disabled=not configured):
                with st.spinner("Reading the alert folder…"):
                    proc = run_local_scrape(["Email"])
                note = next((s for s in _report_sources(paths.latest_dir()) if s["name"] == "Email"), {})
                if proc.returncode == 0 and note.get("ok", True):
                    st.success(f"Done: {note.get('new', 0)} new postings from e-mail.")
                    st.cache_data.clear()
                else:
                    st.error(note.get("error") or "Could not read the mailbox.")
                with st.expander("Details"):
                    st.code((proc.stdout or "")[-3000:] + (proc.stderr or "")[-2000:])

    st.subheader("Job boards")
    srcs = {s["name"]: s for s in load_sources()}
    rows = []
    rep = {s["name"]: s for s in REPORT.get("sources", [])}
    for name, cfg in srcs.items():
        s = rep.get(name, {})
        status = "—" if not s else ("✅ OK" if s.get("ok") else "❌ Failed")
        rows.append({"Board": name, "Description": cfg.get("label", ""), "Enabled": bool(cfg.get("enabled", True)),
                     "Last run": status, "Listed": s.get("listed", ""), "New": s.get("new", ""),
                     "Closed": s.get("closed", ""),
                     "Problem / note": s.get("error") or s.get("closures_skipped") or "",
                     "Verified": cfg.get("verified") or "not yet", "Site": cfg.get("homepage", "")})
    st.dataframe(pd.DataFrame(rows), hide_index=True,
                 column_config={"Site": st.column_config.LinkColumn("Site", display_text="open ↗")})
    st.caption("Boards are configured in config/sources.yaml. A board that fails never closes its jobs, "
               "so a temporary outage cannot wipe your list.")
    with st.expander("Technical notes from the last run"):
        for s in REPORT.get("sources", []):
            st.markdown(f"**{s['name']}** — pages {s.get('pages')}, detail pages {s.get('details_fetched')}, "
                        f"filtered out {s.get('skipped_filtered')}, {s.get('seconds')}s")
            for n in s.get("notes", [])[:10]:
                st.text(f"  {n}")

    st.subheader("Export & backup")
    e1, e2, e3 = st.columns(3)
    buf = io.BytesIO()
    export_frame(DF).to_excel(buf, index=False, sheet_name="Jobs")
    e1.download_button("⬇️ All jobs + my statuses (Excel)", buf.getvalue(), f"job_market_{TODAY}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    if paths.apps_file().exists():
        e2.download_button("💾 Back up my statuses (CSV)", paths.apps_file().read_bytes(),
                           f"applications_backup_{TODAY}.csv", mime="text/csv")
    up = e3.file_uploader("Restore statuses from a backup", type="csv")
    if up is not None and st.button("Restore this backup (replaces current statuses)"):
        paths.apps_file().parent.mkdir(parents=True, exist_ok=True)
        paths.apps_file().write_bytes(up.getvalue())
        st.success(f"Restored {len(A.load_applications())} tracked jobs.")
        st.rerun()


PAGES = {
    "jobs": st.Page(page_jobs, title="Jobs", icon="📋", default=True),
    "mine": st.Page(page_mine, title="My applications", icon="✅", url_path="mine"),
    "details": st.Page(page_details, title="Job details", icon="🔍", url_path="details"),
    "add": st.Page(page_add, title="Add jobs", icon="➕", url_path="add"),
    "data": st.Page(page_data, title="Data & sources", icon="⚙️", url_path="data"),
}
st.navigation(list(PAGES.values()), position="top").run()
