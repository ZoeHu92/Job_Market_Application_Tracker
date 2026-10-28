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
