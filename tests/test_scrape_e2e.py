"""Full weekly run against a fake job board: new jobs, then a removal two runs later."""
import json
from datetime import date

import yaml

from tests.fakes import FakeFetcher
from tests.test_sources import detail, listing
from tracker.scrape import run
from tracker.store import read_jobs


def make_config(tmp_path):
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "settings.yaml").write_text(yaml.safe_dump({"request_delay_seconds": 0, "weekly_digest_issue": True}))
    (cfg / "sources.yaml").write_text(yaml.safe_dump({"sources": [
        {"name": "AFA", "kind": "board", "enabled": True, "start_urls": ["https://b.test/jobs/"],
         "job_link_pattern": r"/job/(\d+)", "default_field": "Finance", "filter": "faculty"},
        {"name": "Broken", "kind": "board", "enabled": True, "start_urls": ["https://down.test/"],
         "job_link_pattern": r"/job/(\d+)"},
        {"name": "Off", "kind": "board", "enabled": False, "start_urls": ["https://off.test/"]},
    ]}))
    return cfg


def pages(ids):
    return {"https://b.test/jobs/": listing(ids), "https://down.test/": (500, "err"),
            **{f"https://b.test/job/{i}/assistant-professor-{i}/": detail(i) for i in ids}}


def test_weekly_runs(tmp_path):
    cfg, data = make_config(tmp_path), tmp_path / "data"
    rep = run(data, config_dir=cfg, today=date(2026, 10, 5), fetcher=FakeFetcher(pages([1, 2, 3])))
    assert [s["name"] for s in rep["sources"]] == ["AFA", "Broken"]
    assert rep["totals"]["new"] == 3
    rows = read_jobs(data / "jobs.csv")
    assert rows["AFA:1"]["deadline"] == "2026-11-15" and rows["AFA:1"]["field"] == "Finance"
    assert rows["AFA:1"]["description"] == ""  # not stored while keep_full_description is false
    digest = (data / "weekly_digest.md").read_text()
    assert "New this week (3)" in digest and "| Broken | ❌" in digest

    # Week 2: job 3 vanished from the board and its page now 404s; job 4 is new.
    p = pages([1, 2, 4])
    fetcher = FakeFetcher(p)
    rep = run(data, config_dir=cfg, today=date(2026, 10, 12), fetcher=fetcher)
    rows = read_jobs(data / "jobs.csv")
    assert rows["AFA:3"]["status"] == "Closed" and rows["AFA:3"]["closed_date"] == "2026-10-12"
    assert rows["AFA:4"]["first_seen"] == "2026-10-12"
    afa = next(s for s in rep["sources"] if s["name"] == "AFA")
    assert afa["new"] == 1 and afa["closed"] == 1
    # Known jobs were not re-fetched: only the listing, job 4, and job 3's closure check.
    assert sorted(fetcher.calls) == sorted(["https://b.test/jobs/", "https://down.test/",
                                            "https://b.test/job/4/assistant-professor-4/",
                                            rows["AFA:3"]["url"]])
    assert json.loads((data / "scrape_report.json").read_text())["run_date"] == "2026-10-12"
