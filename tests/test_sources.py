import json

from tracker.sources.board import BoardSource
from tracker.sources.econjobmarket import EconJobMarketSource
from tracker.sources.joe import JoeSource
from tracker.sources.pages import PageWatchSource
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


def test_econjobmarket_mapping_and_filter():
    ads = [
        {"adtitle": "Assistant Professor of Finance", "adtext": "<p>Tenure-track position.</p>",
         "name": "Example Business School", "department": "Finance", "startdate": "2026-09-01",
         "enddate": "2026-12-31", "deadline_date": "2026-11-30",
         "locations": [{"city": "Paris", "state": "", "country_code": "FR"}],
         "position_types": [{"name": "Assistant Professor"}], "categories": [{"name": "Finance"}],
         "url": "https://econjobmarket.org/positions/101"},
        {"adtitle": "Assistant Professor", "adtext": "<p>The Department of Economics invites applications.</p>",
         "name": "Example University", "department": "Economics",
         "position_types": [{"name": "Assistant Professor"}],
         "categories": [{"name": "International Finance/Macro"}], "url": "https://econjobmarket.org/positions/102"},
        {"adtitle": "Research Economist", "adtext": "", "name": "Example Central Bank", "department": "Research",
         "position_types": [{"name": "Non-Academic"}], "categories": [], "url": "https://econjobmarket.org/positions/103"},
    ]
    url = "https://ejm.test/Ads"
    src = EconJobMarketSource({"name": "EJM", "api_url": url}, FakeFetcher({url: json.dumps(ads)}))
    res = src.run(set())
    assert res.ok and res.complete
    assert [j.source_id for j in res.jobs] == ["101"]
    j = res.jobs[0]
    assert j.institution == "Example Business School" and j.country == "FR" and j.deadline_raw == "2026-11-30"
    assert j.posted_date == "2026-09-01" and j.listing_expires == "2026-12-31" and "Finance" in j.categories


def test_detail_cap_defers_new_jobs_but_keeps_known_ones_seen():
    cfg = {**CFG, "max_new_details": 1}
    pages = {"https://b.test/jobs/": listing([1, 2, 3]),
             **{f"https://b.test/job/{i}/assistant-professor-{i}/": detail(i) for i in (1, 2, 3)}}
    res = BoardSource(cfg, FakeFetcher(pages)).run({"AFA:3"})
    assert res.details_fetched == 1 and not res.complete
    assert {j.source_id for j in res.jobs} == {"1", "3"}


MADGEX_FEED = """<?xml version="1.0" encoding="utf-8"?><rss version="2.0"><channel><title>Job Search RSS</title>
<item><title>Example University Department of Finance: Assistant / Associate Professor</title>
<description>
Commensurate upon experience:

Example University Department of Finance:
The College of Business invites applications for two tenure-track positions...
Blacksburg, Virginia
</description>
<link>https://m.test/job/{id}/assistant-associate-professor/?TrackID=8</link>
<pubDate>Tue, 13 Oct 2026 20:03:00 -0500</pubDate></item>
<item><title>Example College: Accounting Manager</title><description>x:

Example College:
Staff role.
Somewhere
</description><link>https://m.test/job/{id2}/accounting-manager/</link></item>
</channel></rss>"""


def test_madgex_feed_pagination_and_parsing():
    cfg = {"name": "AFA", "feeds": ["https://m.test/jobsrss/"], "feed_style": "madgex", "feed_page_param": "Page",
           "job_link_pattern": r"/job/(\d+)", "filter": "faculty", "fetch_details": False}
    pages = {"https://m.test/jobsrss/": MADGEX_FEED.format(id=1, id2=2),
             "https://m.test/jobsrss/?Page=2": MADGEX_FEED.format(id=3, id2=4),
             "https://m.test/jobsrss/?Page=3": MADGEX_FEED.format(id=3, id2=4)}
    res = BoardSource(cfg, FakeFetcher(pages)).run(set())
    assert sorted(j.source_id for j in res.jobs) == ["1", "3"]  # staff jobs dropped, page 3 adds nothing
    j = res.jobs[0]
    assert j.institution == "Example University Department of Finance"
    assert j.title == "Assistant / Associate Professor"
    assert j.location == "Blacksburg, Virginia" and j.salary_label == "Commensurate upon experience"
    assert res.complete


def test_higheredjobs_feed_parsing():
    feed = """<?xml version="1.0"?><rss version="2.0"><channel><title>HEJ</title>
      <item><title>Assistant Professor of Finance</title><description>Example State University (Austin, TX)</description>
      <link>https://www.higheredjobs.com/details.cfm?JobCode=179590084</link></item></channel></rss>"""
    cfg = {"name": "HigherEdJobs", "feeds": ["https://h.test/f"], "feed_style": "higheredjobs", "partial_listing": True,
           "job_link_pattern": r"JobCode=(\d+)", "filter": "business", "fetch_details": False}
    res = BoardSource(cfg, FakeFetcher({"https://h.test/f": feed})).run(set())
    assert [(j.source_id, j.institution, j.location) for j in res.jobs] == [
        ("179590084", "Example State University", "Austin, TX")]
    assert not res.complete  # partial feed: missing postings are never treated as closed


def test_ajo_feed_fields():
    feed = """<?xml version="1.0"?><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
      xmlns="http://purl.org/rss/1.0/" xmlns:ads="https://academicjobsonline.org/ajo/ads.rss">
      <channel rdf:about="x"><title>AJO</title></channel>
      <item rdf:about="https://academicjobsonline.org/ajo/Example/Business/555?rss">
        <title>Assistant Professor of Finance</title>
        <link>https://academicjobsonline.org/ajo/Example/Business/555?rss</link>
        <description>Tenure-track position. Applications due December 1, 2026.</description>
        <ads:Univ>Example University</ads:Univ><ads:Dept>College of Business</ads:Dept>
        <ads:Deadline>Tue, 01 Dec 2026 23:59:59 EST</ads:Deadline><ads:Country>US</ads:Country>
        <ads:Disciplines>Finance</ads:Disciplines></item>
      <item rdf:about="https://academicjobsonline.org/ajo/Example/Physics/556?rss">
        <title>Postdoc in Physics</title><link>https://academicjobsonline.org/ajo/Example/Physics/556?rss</link>
        <description>Physics.</description><ads:Univ>Example University</ads:Univ><ads:Dept>Physics</ads:Dept>
        <ads:Disciplines>Physics</ads:Disciplines></item></rdf:RDF>"""
    cfg = {"name": "AJO", "feeds": ["https://a.test/rss"], "fetch_details": False, "filter": "business",
           "feed_fields": {"institution": "ads_univ", "department": "ads_dept", "deadline_raw": "ads_deadline",
                           "country": "ads_country", "categories": "ads_disciplines"},
           "job_link_pattern": r"academicjobsonline\.org/ajo/.*?/(\d+)(?:\?rss)?$"}
    res = BoardSource(cfg, FakeFetcher({"https://a.test/rss": feed})).run(set())
    assert [j.source_id for j in res.jobs] == ["555"]
    j = res.jobs[0]
    assert (j.institution, j.department, j.country, j.categories) == (
        "Example University", "College of Business", "US", "Finance")
    assert "01 Dec 2026" in j.deadline_raw


JOE_XML = """<JOE_EXPORT><year joe_year_ID="2026"><issue joe_issue_ID="2">
  <position jp_id="111"><jp_section>US: Full-Time Academic (Permanent, Tenure Track or Tenured)</jp_section>
    <jp_title>Assistant Professor</jp_title><jp_institution>Example University</jp_institution>
    <jp_division>Example School of Business</jp_division><jp_department>Finance</jp_department>
    <jp_salary_range></jp_salary_range><jp_application_deadline>2026-11-15 00:00:00</jp_application_deadline>
    <jp_full_text>Tenure-track position in finance. PhD expected by the start date.</jp_full_text>
    <jp_keywords>Asset pricing</jp_keywords><jp_status></jp_status>
    <locations><location id="1"><country>UNITED STATES</country><state>Ohio</state><city>COLUMBUS</city></location></locations>
    <JEL_Classifications><jel_class id="2"><jc_code>G1</jc_code><jc_description>General Financial Markets</jc_description></jel_class></JEL_Classifications>
  </position>
  <position jp_id="222"><jp_section>US: Full-Time Academic (Permanent, Tenure Track or Tenured)</jp_section>
    <jp_title>Assistant Professor</jp_title><jp_institution>Example College</jp_institution>
    <jp_division>College of Arts and Sciences</jp_division><jp_department>Economics</jp_department>
    <jp_full_text>Department of Economics, any field.</jp_full_text><jp_status></jp_status></position>
  <position jp_id="333"><jp_section>Full-Time Nonacademic</jp_section><jp_title>Economist</jp_title>
    <jp_institution>Example Bank</jp_institution><jp_full_text>Finance research.</jp_full_text></position>
</issue></year></JOE_EXPORT>"""


def test_joe_xml_export():
    listing = '<a href="/joe/resultset_output.php?mode=full_xml&amp;q=abc">XML</a>'
    pages = {"https://www.aeaweb.org/joe/listings": listing,
             "https://www.aeaweb.org/joe/resultset_output.php?mode=full_xml&q=abc": JOE_XML}
    res = JoeSource({"name": "JOE"}, FakeFetcher(pages)).run(set())
    assert res.ok and res.complete
    assert [j.source_id for j in res.jobs] == ["111"]
    j = res.jobs[0]
    assert j.url.endswith("JOE_ID=2026-02_111")
    assert j.department == "Example School of Business - Finance"
    assert j.deadline_raw == "2026-11-15" and j.location == "Columbus, Ohio" and j.country == "United States"
    assert "G1 General Financial Markets" in j.categories


def test_page_watcher_always_returns_full_records():
    html = "<html><body><div class='content'>" + "<p>We invite applications for faculty positions in finance, " \
        "at all ranks, with a PhD required.</p>" * 4 + "</div></body></html>"
    cfg = {"name": "School-pages", "pages": [{"url": "https://s.test/rec", "institution": "Example SEM",
                                              "title": "Faculty positions", "field": "Finance"},
                                             {"url": "https://s.test/missing"}]}
    res = PageWatchSource(cfg, FakeFetcher({"https://s.test/rec": html})).run({"School-pages:x"})
    assert res.ok and not res.complete  # one page failed, so nothing is closed
    assert len(res.jobs) == 1 and not res.jobs[0].stub
    assert res.jobs[0].institution == "Example SEM" and res.jobs[0].field_override == "Finance"
