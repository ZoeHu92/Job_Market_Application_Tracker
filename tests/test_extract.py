import json

from tracker.extract import extract_posting, html_to_text

JSONLD = {
    "@context": "https://schema.org",
    "@graph": [
        {"@type": "WebPage", "name": "x"},
        {
            "@type": "JobPosting",
            "title": "Assistant Professor of Finance",
            "hiringOrganization": {"@type": "Organization", "name": "Example University"},
            "datePosted": "2026-09-01T00:00:00",
            "validThrough": "2026-12-31",
            "description": "<p>The <b>Department of Finance</b> seeks...</p><ul><li>PhD required</li></ul>",
            "jobLocation": {"@type": "Place", "address": {"addressLocality": "Columbus", "addressRegion": "OH",
                                                           "addressCountry": "US"}},
            "baseSalary": {"@type": "MonetaryAmount", "currency": "USD",
                           "value": {"@type": "QuantitativeValue", "minValue": 200000, "maxValue": 250000,
                                     "unitText": "YEAR"}},
        },
    ],
}


def test_jsonld_jobposting():
    html = f"<html><head><script type='application/ld+json'>{json.dumps(JSONLD)}</script></head><body></body></html>"
    d = extract_posting(html)
    assert d["title"] == "Assistant Professor of Finance"
    assert d["institution"] == "Example University"
    assert d["posted_date"] == "2026-09-01"
    assert d["listing_expires"] == "2026-12-31"
    assert d["location"] == "Columbus, OH, US"
    assert d["country"] == "US"
    assert d["salary_min"] == 200000 and d["salary_max"] == 250000 and d["salary_currency"] == "USD"
    assert "Department of Finance" in d["description"] and "PhD required" in d["description"]
    assert d["has_jsonld"] and not d["closed_hint"]


def test_labeled_fields_without_jsonld():
    html = """<html><head><title>Job | Board</title></head><body>
      <h1>Lecturer in Accounting</h1>
      <dl><dt>Employer:</dt><dd>University of Exampleshire</dd>
          <dt>Location:</dt><dd>Exampleshire, United Kingdom</dd>
          <dt>Closing date:</dt><dd>12 November 2026</dd>
          <dt>Salary:</dt><dd>£45,585 to £56,021 per annum</dd></dl>
      <div class="job-description">""" + "We seek a lecturer in accounting. " * 20 + """</div>
    </body></html>"""
    d = extract_posting(html)
    assert d["title"] == "Lecturer in Accounting"
    assert d["institution"] == "University of Exampleshire"
    assert d["location"] == "Exampleshire, United Kingdom"
    assert d["deadline_raw"] == "12 November 2026"
    assert d["salary_label"].startswith("£45,585")
    assert d["description"].startswith("We seek a lecturer")


def test_table_labels_and_closed_hint():
    html = """<html><body><table><tr><th>Institution</th><td>Example College</td></tr>
      <tr><th>JEL Classifications</th><td>G1 - General Financial Markets</td></tr></table>
      <p>Sorry, this job has expired.</p></body></html>"""
    d = extract_posting(html)
    assert d["institution"] == "Example College"
    assert d["categories"].startswith("G1")
    assert d["closed_hint"]


def test_html_to_text_keeps_paragraphs():
    assert html_to_text("<p>One</p><p>Two&nbsp;three</p>") == "One\nTwo three"


def test_page_title_drops_site_suffix():
    html = "<html><head><title>Assistant Professor of Finance | Example Job Board</title></head><body></body></html>"
    assert extract_posting(html)["title"] == "Assistant Professor of Finance"
