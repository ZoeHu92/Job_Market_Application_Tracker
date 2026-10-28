import json

from tracker.sources.board import BoardSource
from tracker.sources.econjobmarket import EconJobMarketSource
from tests.fakes import FakeFetcher


def listing(ids, next_url=None):
    items = "".join(
        f"<li class='lister__item'><a href='/job/{i}/assistant-professor-{i}/'>Assistant Professor of Finance {i}</a>"
        f"<span>Example University {i}</span></li>" for i in ids)
    nxt = f"<a rel='next' href='{next_url}'>Next</a>" if next_url else ""
    return f"<html><body><ul>{items}</ul>{nxt}</body></html>"


def detail(i, extra=""):
    ld = {"@type": "JobPosting", "title": f"Assistant Professor of Finance {i}",
          "hiringOrganization": {"name": f"Example University {i}"},
          "description": "Tenure-track. PhD in finance required. Applications due by November 15, 2026." + extra,
          "datePosted": "2026-09-01", "jobLocation": {"address": {"addressLocality": "Boston", "addressRegion": "MA",
                                                                    "addressCountry": "US"}}}
    return f"<html><script type='application/ld+json'>{json.dumps(ld)}</script><body>x</body></html>"


CFG = {"name": "AFA", "kind": "board", "start_urls": ["https://b.test/jobs/"], "job_link_pattern": r"/job/(\d+)",
       "default_field": "Finance", "filter": "faculty", "max_pages": 5}


def test_board_pagination_and_details():
    pages = {"https://b.test/jobs/": listing([1, 2], "/jobs/?Page=2"),
             "https://b.test/jobs/?Page=2": listing([3]),
             **{f"https://b.test/job/{i}/assistant-professor-{i}/": detail(i) for i in (1, 2, 3)}}
    res = BoardSource(CFG, FakeFetcher(pages)).run(set())
    assert res.ok and res.complete
    assert sorted(j.source_id for j in res.jobs) == ["1", "2", "3"]
    j = next(j for j in res.jobs if j.source_id == "2")
    assert j.institution == "Example University 2"
    assert "November 15, 2026" in j.description
    assert j.country == "US"


def test_known_jobs_are_not_refetched():
    pages = {"https://b.test/jobs/": listing([1, 2])}
    fetcher = FakeFetcher(pages)
    res = BoardSource(CFG, fetcher).run({"AFA:1", "AFA:2"})
    assert all(j.stub for j in res.jobs)
    assert fetcher.calls == ["https://b.test/jobs/"]


def test_listing_error_marks_incomplete():
    pages = {"https://b.test/jobs/": listing([1], "/jobs/?Page=2"), "https://b.test/jobs/?Page=2": (503, "down"),
             "https://b.test/job/1/assistant-professor-1/": detail(1)}
    res = BoardSource(CFG, FakeFetcher(pages)).run(set())
    assert res.ok and not res.complete and len(res.jobs) == 1


def test_source_down_reports_error():
    res = BoardSource(CFG, FakeFetcher({"https://b.test/jobs/": (403, "blocked")})).run(set())
    assert not res.ok and "403" in res.error


def test_business_filter_drops_economics_department_jobs():
    cfg = {**CFG, "name": "JOE", "filter": "business", "default_field": ""}
    econ = detail(2).replace("Assistant Professor of Finance 2", "Assistant Professor").replace(
        "PhD in finance required", "Department of Economics, College of Arts and Sciences")
    pages = {"https://b.test/jobs/": listing([1, 2]),
             "https://b.test/job/1/assistant-professor-1/": detail(1),
             "https://b.test/job/2/assistant-professor-2/": econ}
    res = BoardSource(cfg, FakeFetcher(pages)).run(set())
    assert [j.source_id for j in res.jobs] == ["1"]
    assert res.skipped_ids == ["JOE:2"]


def test_rss_feed_source():
    feed = """<?xml version="1.0"?><rss version="2.0"><channel><title>Jobs</title>
      <item><title>Lecturer in Finance</title><link>https://f.test/job/ABC123/lecturer/</link>
        <description>University of Exampleshire. Closing date: 12 November 2026</description>
        <pubDate>Mon, 26 Oct 2026 09:00:00 GMT</pubDate></item>
      <item><title>Payroll Officer</title><link>https://f.test/job/XYZ9/payroll/</link>
        <description>Finance office</description></item></channel></rss>"""
    cfg = {"name": "jobs.ac.uk", "feeds": ["https://f.test/feed.xml"], "job_link_pattern": r"/job/([A-Za-z0-9]+)",
           "filter": "business", "fetch_details": False}
    res = BoardSource(cfg, FakeFetcher({"https://f.test/feed.xml": feed})).run(set())
    assert [j.source_id for j in res.jobs] == ["ABC123"]
    assert res.jobs[0].posted_date == "2026-10-26"
    assert res.complete


def test_feed_index_discovery():
    index = """<html><body><a href="/feeds/accountancy-finance.xml">Accountancy &amp; Finance</a>
      <a href="/feeds/hospitality.xml">Hospitality RSS</a><a href="/about">About</a></body></html>"""
    cfg = {"name": "x", "feed_index": "https://f.test/feeds", "feed_index_filter": "finance",
           "job_link_pattern": r"/job/(\w+)", "fetch_details": False}
    src = BoardSource(cfg, FakeFetcher({"https://f.test/feeds": index}))
    assert src._feeds_from_index("https://f.test/feeds", "finance") == ["https://f.test/feeds/accountancy-finance.xml"]


def test_econjobmarket_mapping_and_filter():
    ads = [
        {"id": 101, "title": "Assistant Professor of Finance", "institution": {"name": "Example Business School"},
         "department": "Finance", "city": "Paris", "country": "France", "deadline": "2026-11-30",
         "categories": [{"name": "Financial Economics"}], "position_types": [{"name": "Assistant Professor"}]},
        {"id": 102, "title": "Assistant Professor", "institution": "Example University",
         "department": "Department of Economics", "categories": [{"name": "Labor Economics"}]},
    ]
    url = "https://ejm.test/Ads"
    src = EconJobMarketSource({"name": "EJM", "api_url": url}, FakeFetcher({url: json.dumps(ads)}))
    res = src.run(set())
    assert res.ok and res.complete
    assert [j.source_id for j in res.jobs] == ["101"]
    j = res.jobs[0]
    assert j.institution == "Example Business School" and j.country == "France" and j.deadline_raw == "2026-11-30"
    assert "Financial Economics" in j.categories
    assert any("first ad keys" in n for n in res.notes)


def test_detail_cap_defers_new_jobs_but_keeps_known_ones_seen():
    cfg = {**CFG, "max_new_details": 1}
    pages = {"https://b.test/jobs/": listing([1, 2, 3]),
             **{f"https://b.test/job/{i}/assistant-professor-{i}/": detail(i) for i in (1, 2, 3)}}
    res = BoardSource(cfg, FakeFetcher(pages)).run({"AFA:3"})
    assert res.details_fetched == 1 and not res.complete
    assert {j.source_id for j in res.jobs} == {"1", "3"}
