from datetime import date

from tracker.importer import find_existing, jobs_from_saved_page

PAGE = """<html><head><base href="https://www.fma.org/"></head><body>
  <nav><a href="/jobs">Jobs</a><a href="/login">Member Login</a></nav>
  <ul>
    <li><a href="/jobs/101">Assistant Professor of Finance</a> <span>Example University</span> <span>Boston, MA</span></li>
    <li><a href="/jobs/102">Clinical Professor of Finance</a> <span>Example College</span></li>
    <li><a href="/job-details?id=103">Finance</a> <span>Example State University</span> <span>Columbus, OH</span></li>
  </ul></body></html>"""


def test_saved_board_page_import():
    jobs = jobs_from_saved_page(PAGE, "FMA", today=date(2026, 10, 28))
    assert [j.title for j in jobs] == ["Assistant Professor of Finance", "Clinical Professor of Finance", "Finance"]
    assert jobs[0].url == "https://www.fma.org/jobs/101" and jobs[0].source == "FMA (saved page)"
    assert jobs[0].institution == "Example University" and jobs[0].default_field == "Finance"


def test_saved_from_comment_gives_base_url():
    html = "<!-- saved from url=(0030)https://placement.example.org/ -->" + PAGE.replace(
        '<base href="https://www.fma.org/">', "")
    assert jobs_from_saved_page(html, "FMA")[0].url == "https://placement.example.org/jobs/101"


def test_find_existing_matches_cross_posted_job():
    rows = [("AFA:1", "Assistant Professor of Finance", "The Example University - College of Business"),
            ("AFA:2", "Associate Professor of Accounting", "Example University")]
    assert find_existing("Assistant Professor in Finance", "Example University", rows) == "AFA:1"
    assert find_existing("Assistant Professor of Marketing", "Other College", rows) == ""


# Structure of YM Careers job tiles (e.g. jobs.fma.org); content is made up.
TILES = """<html><body><div class="job-results-list"><div class="job-result-tiles">
  <div class="job-tile job-tile-111111"><div class="job-main-data"><div class="job-details">
    <div class="job-detail-row"><div class="job-title" aria-label="Job Title">
      <a href="https://jobs.example.org/job/assistant-professor/111111/">Assistant Professor</a></div></div>
    <div class="job-company-row" aria-label="Hiring Company"> Example State University </div>
    <div class="job-subtext-row"><div class="job-location" aria-label="Job Location"> Multiple Locations
      <br>Columbus, Ohio, United States <span class="workplace-location">(on-site)</span></div>
      <div class="job-posted-date" aria-label="Job Posted Date"> 2 days ago </div></div></div></div></div>
  <div class="job-tile job-tile-222222"><div class="job-main-data"><div class="job-details">
    <div class="job-detail-row"><div class="job-title" aria-label="Job Title">
      <a href="https://jobs.example.org/job/assistant-professor/222222/">Assistant Professor</a></div></div>
    <div class="job-company-row" aria-label="Hiring Company"> Example College </div>
    <div class="job-subtext-row"><div class="job-location" aria-label="Job Location"> Boston, MA </div>
      <div class="job-posted-date" aria-label="Job Posted Date"> 30+ days ago </div></div></div></div></div>
  <div class="job-tile job-tile-333333"><div class="job-details">
    <div class="job-title"><a href="https://jobs.example.org/job/summer-associate/333333/">Summer Associate</a></div>
    <div class="job-company-row" aria-label="Hiring Company"> Example Bank </div></div></div>
</div></div></body></html>"""


def test_ym_careers_tiles():
    jobs = jobs_from_saved_page(TILES, "FMA", today=date(2026, 10, 28))
    # same title twice is two postings (different ids); non-faculty roles are skipped
    assert [(j.title, j.institution) for j in jobs] == [("Assistant Professor", "Example State University"),
                                                         ("Assistant Professor", "Example College")]
    assert jobs[0].location == "Columbus, Ohio, United States" and jobs[0].posted_date == "2026-10-26"
    assert jobs[1].posted_date == "2026-09-28"
    assert jobs[0].source_id != jobs[1].source_id


def test_generic_title_needs_same_field():
    rows = [("AAA:1", "Assistant Professor", "San Jose State University", "Accounting")]
    assert find_existing("Assistant Professor", "San Jose State University", rows, "Finance") == ""
    assert find_existing("Assistant Professor", "San Jose State University", rows, "Accounting") == "AAA:1"
