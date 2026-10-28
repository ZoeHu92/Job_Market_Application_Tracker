from datetime import date

from tracker.enrich import enrich
from tracker.sources.base import RawJob, SourceResult
from tracker.store import expire_rows, mark_duplicates, merge_results, read_jobs, write_jobs

D1, D2 = date(2026, 10, 5), date(2026, 10, 12)


def raw(i, src="AFA", inst="Example University", title="Assistant Professor of Finance", stub=False):
    return RawJob(source=src, source_id=str(i), url=f"https://x.test/{src}/{i}", title=title, institution=inst,
                  description="Applications due by December 1, 2026.", stub=stub)


def run(rows, jobs, today, ok=True, complete=True, verifier=None, name="AFA"):
    res = SourceResult(name=name, jobs=jobs, ok=ok, complete=complete)
    enriched = {j.job_id: enrich(j, today) for j in jobs if not j.stub}
    return merge_results(rows, [res], enriched, today, verifier)[name]


def test_new_then_closed_when_removed():
    rows = {}
    st = run(rows, [raw(1), raw(2, inst="Other College")], D1)
    assert st["new"] == 2 and rows["AFA:1"]["first_seen"] == "2026-10-05"
    st = run(rows, [raw(1, stub=True)], D2, verifier=lambda r: "gone")
    assert st["closed"] == 1
    assert rows["AFA:2"]["status"] == "Closed" and rows["AFA:2"]["closed_date"] == "2026-10-12"
    assert rows["AFA:1"]["status"] == "Open" and rows["AFA:1"]["last_seen"] == "2026-10-12"


def test_missing_but_page_alive_stays_open():
    rows = {}
    run(rows, [raw(1), raw(2, inst="Other College")], D1)
    st = run(rows, [raw(1, stub=True)], D2, verifier=lambda r: "alive")
    assert st["kept_open"] == 1 and rows["AFA:2"]["status"] == "Open"
    assert rows["AFA:2"]["status_note"].startswith("Not in latest listing")


def test_failed_or_partial_source_never_closes():
    rows = {}
    run(rows, [raw(1), raw(2, inst="B")], D1)
    st = run(rows, [], D2, ok=False, complete=False)
    assert st["closed"] == 0 and all(r["status"] == "Open" for r in rows.values())
    st = run(rows, [raw(1, stub=True)], D2, ok=True, complete=False)
    assert st["closed"] == 0


def test_mass_disappearance_is_treated_as_scraping_problem():
    rows = {}
    run(rows, [raw(i, inst=f"School {i}") for i in range(20)], D1)
    st = run(rows, [raw(0, stub=True)], D2, verifier=lambda r: "gone")
    assert st["closed"] == 0 and "scraping problem" in st["closures_skipped"]


def test_reopen_when_relisted():
    rows = {}
    run(rows, [raw(1), raw(2, inst="B")], D1)
    run(rows, [raw(1, stub=True)], D2, verifier=lambda r: "gone")
    st = run(rows, [raw(1, stub=True), raw(2, stub=True, inst="B")], date(2026, 10, 19))
    assert st["reopened"] == 1 and rows["AFA:2"]["status"] == "Open" and rows["AFA:2"]["closed_date"] == ""


def test_expire_old_deadlines_and_listing_expiry():
    rows = {"a": {"job_id": "a", "status": "Open", "deadline": "2026-01-01", "listing_expires": ""},
            "b": {"job_id": "b", "status": "Open", "deadline": "", "listing_expires": "2026-10-01"},
            "c": {"job_id": "c", "status": "Open", "deadline": "2026-10-01", "listing_expires": ""}}
    assert expire_rows(rows, D2) == 2
    assert rows["c"]["status"] == "Open"


def test_cross_board_duplicates():
    rows = {}
    run(rows, [raw(1, inst="The University of Example - Business School")], D1)
    run(rows, [raw(9, src="JOE", inst="University of Example")], D2, name="JOE")
    mark_duplicates(rows)
    assert rows["JOE:9"]["duplicate_of"] == "AFA:1" and rows["AFA:1"]["duplicate_of"] == ""


def test_csv_roundtrip(tmp_path):
    rows = {}
    run(rows, [raw(1), raw(2, inst='Quote "and", comma')], D1)
    write_jobs(rows, tmp_path / "jobs.csv")
    back = read_jobs(tmp_path / "jobs.csv")
    assert back["AFA:2"]["institution"] == 'Quote "and", comma'
    assert back["AFA:1"]["deadline"] == "2026-12-01"


def test_listing_expiry_ignored_while_still_listed():
    t = D2.isoformat()
    rows = {"a": {"job_id": "a", "status": "Open", "deadline": "", "listing_expires": "2026-10-01", "last_seen": t},
            "b": {"job_id": "b", "status": "Open", "deadline": "", "listing_expires": "2026-10-01", "last_seen": ""}}
    assert expire_rows(rows, D2) == 1
    assert rows["a"]["status"] == "Open" and rows["b"]["status"] == "Closed"


def test_long_expired_job_is_not_reopened_by_relisting():
    rows = {}
    old = RawJob(source="AFA", source_id="7", url="u", title="Assistant Professor", institution="X",
                 description="Applications due by January 5, 2026.")
    run(rows, [old], date(2026, 1, 1))
    expire_rows(rows, D2)
    assert rows["AFA:7"]["status"] == "Closed"
    st = run(rows, [RawJob(source="AFA", source_id="7", url="u", stub=True)], D2)
    assert st["reopened"] == 0 and rows["AFA:7"]["status"] == "Closed"


def test_watched_page_change_sets_updated_date():
    rows = {}
    page = RawJob(source="AFA", source_id="p", url="u", title="Faculty positions", institution="X",
                  description="Version one of the recruitment page.")
    run(rows, [page], D1)
    assert rows["AFA:p"]["updated_date"] == ""
    page2 = RawJob(source="AFA", source_id="p", url="u", title="Faculty positions", institution="X",
                   description="Version two: new openings in finance.")
    run(rows, [page2], D2)
    assert rows["AFA:p"]["updated_date"] == D2.isoformat()


def test_stale_rows_close_after_four_months():
    rows = {"a": {"job_id": "a", "status": "Open", "deadline": "", "listing_expires": "", "last_seen": "2026-05-01"}}
    assert expire_rows(rows, D2) == 1 and rows["a"]["status"] == "Closed"
