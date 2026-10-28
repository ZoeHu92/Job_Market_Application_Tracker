"""Synthetic postings for tests and UI smoke runs. Institutions are fictional ("Example ...")."""
from __future__ import annotations

from datetime import date, timedelta

from tracker.enrich import enrich
from tracker.sources.base import RawJob

TEMPLATES = [
    ("AFA", "Assistant Professor of Finance", "Example State University", "Department of Finance", "Columbus, OH",
     "The Department of Finance invites applications for a tenure-track Assistant Professor position beginning Fall 2027. "
     "Candidates must hold a Ph.D. in Finance or Economics, or expect to complete it by the start of the appointment. "
     "Applications received by {d1} will receive full consideration. Please submit a cover letter, CV, job market paper, "
     "and three letters of recommendation. We will interview at the FMA Annual Meeting and virtually. "
     "The salary range for this position is $220,000 - $260,000."),
    ("AFA", "Assistant, Associate, or Full Professor of Finance", "University of Example Hong Kong", "School of Business",
     "Hong Kong", "Open-rank positions in finance. PhD required. Review of applications will begin {d1} and continue "
     "until the positions are filled. Interviews at the AFA/ASSA meetings."),
    ("JOE", "Assistant Professor", "Example College of Business", "Department of Accounting and Finance", "Boston, MA",
     "Tenure-track position in Accounting. Applications are due {d2}. Submit CV, research statement, teaching "
     "statement and transcripts. Doctorate in accounting (ABD considered)."),
    ("AOM", "Assistant Professor of Strategy", "Example Business School", "Strategy Department", "London, United Kingdom",
     "We seek a scholar in strategic management. Closing date: {d2}. Salary £75,000 per annum. PhD near completion."),
    ("AMA", "Assistant Professor of Marketing (Quantitative)", "Example Tech University", "Marketing Department",
     "Singapore", "Quantitative marketing position. Deadline: {d3}. PhD in marketing, economics or statistics."),
    ("INFORMS", "Tenure-Track Faculty Position in Operations Management", "Example Polytechnic", "School of Management",
     "Shanghai, China", "Operations management and supply chain. Applications should be submitted no later than {d3}."),
    ("jobs.ac.uk", "Lecturer in Accounting", "University of Exampleshire", "Business School", "Exampleshire, United Kingdom",
     "Lecturer in Accounting. Closing date: {d1}. PhD (or nearing completion) in Accounting."),
    ("EJM", "Clinical Assistant Professor of Finance", "Example University", "Department of Finance", "Austin, Texas",
     "Non-tenure track clinical position teaching corporate finance. Master's degree required; PhD preferred. "
     "Deadline {d4}."),
    ("AAA", "Assistant Professor of Accounting", "Example A&M University", "School of Accountancy", "Example, TX",
     "Tenure-track accounting faculty. Applications due by {d4}. PhD in accounting required by August 2027."),
    ("AFA", "Postdoctoral Research Fellow in Finance", "Example Institute of Technology", "Finance Group",
     "Zurich, Switzerland", "Two-year postdoc in empirical asset pricing. Deadline: {d5}."),
]


def sample_rows(today: date, n_repeat: int = 3) -> dict[str, dict]:
    rows = {}
    k = 0
    for rep in range(n_repeat):
        for src, title, inst, dept, loc, text in TEMPLATES:
            k += 1
            ds = {f"d{i}": (today + timedelta(days=d)).strftime("%B %d, %Y")
                  for i, d in enumerate([5 + rep * 9, 12 + rep * 7, 25, 40, -3], start=1)}
            raw = RawJob(source=src, source_id=f"{1000 + k}", url=f"https://example.org/job/{1000 + k}",
                         title=title, institution=inst if rep == 0 else f"{inst} {rep + 1}", department=dept,
                         location=loc, description=text.format(**ds),
                         posted_date=(today - timedelta(days=k % 20)).isoformat())
            row = enrich(raw, today, keep_description=True)
            row["first_seen"] = (today - timedelta(days=k % 15)).isoformat()
            row["last_seen"] = today.isoformat()
            rows[row["job_id"]] = row
    return rows
