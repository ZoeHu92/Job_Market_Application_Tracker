from datetime import date

import pytest

from tracker import classify as C

REF = date(2026, 9, 1)


@pytest.mark.parametrize("text,deadline,review,until", [
    ("Review of applications will begin October 1, 2026 and continue until the position is filled. "
     "Applications received by November 15, 2026 will receive full consideration.", "2026-11-15", "2026-10-01", True),
    ("Closing date: 12 November 2026.", "2026-11-12", "", False),
    ("Applications are due by 12/01/2026.", "2026-12-01", "", False),
    ("Deadline: Oct 30.", "2026-10-30", "", False),
    ("Applications should be submitted no later than January 5, 2027.", "2027-01-05", "", False),
    ("Screening will begin on September 15, 2026.", "", "2026-09-15", False),
    ("We may hire in May 2027. The founding of the school dates to March 3, 1901.", "", "", False),
    ("Open until filled.", "", "", True),
])
def test_extract_deadline(text, deadline, review, until):
    d = C.extract_deadline(text, REF)
    assert d["deadline"] == deadline
    assert d["review_start"] == review
    assert d["open_until_filled"] is until


def test_deadline_without_year_rolls_forward():
    assert C.extract_deadline("Deadline: January 10", date(2026, 10, 1))["deadline"] == "2027-01-10"


def test_earliest_deadline_wins_and_note_mentions_final():
    d = C.extract_deadline("Priority deadline November 1, 2026; final deadline December 15, 2026.", REF)
    assert d["deadline"] == "2026-11-01"
    assert "final Dec 15, 2026" in d["deadline_note"]


@pytest.mark.parametrize("text,lo,hi,cur", [
    ("The salary range for this position is $220,000 - $260,000 per academic year.", 220000, 260000, "USD"),
    ("Salary: £45,585 to £56,021 per annum", 45585, 56021, "GBP"),
    ("Hiring range: $150K-$175K.", 150000, 175000, "USD"),
    ("Annual salary of HK$1,200,000", 1200000, 1200000, "HKD"),
])
def test_extract_salary(text, lo, hi, cur):
    s = C.extract_salary(text)
    assert (s["salary_min"], s["salary_max"], s["salary_currency"]) == (lo, hi, cur)


@pytest.mark.parametrize("text", [
    "We offer startup funds of $50,000 and summer support.",
    "The school received a $25 million gift.",
    "Application fee: $50.",
])
def test_salary_ignores_non_salary_money(text):
    assert C.extract_salary(text)["salary_text"] == ""


@pytest.mark.parametrize("text,expected", [
    ("Candidates must hold a Ph.D. in Finance, or expect to complete it by the start of the appointment.", "PhD (ABD OK)"),
    ("PhD in accounting required by August 2027.", "PhD (ABD OK)"),
    ("ABD candidates will be considered; a doctorate is required.", "PhD (ABD OK)"),
    ("A Ph.D. in Marketing is required.", "PhD required"),
    ("Master's degree required; PhD preferred.", "Master's+"),
    ("Teach undergraduate courses.", "Not stated"),
])
def test_detect_degree(text, expected):
    assert C.detect_degree(text) == expected


@pytest.mark.parametrize("title,region,rank", [
    ("Assistant Professor of Finance", "United States", "Assistant"),
    ("Assistant, Associate, or Full Professor of Finance", "United States", "Open rank"),
    ("Assistant/Associate Professor", "United States", "Assistant/Associate"),
    ("Associate or Full Professor of Information Systems", "United States", "Associate/Full"),
    ("Open Rank Professor of Business Analytics", "United States", "Open rank"),
    ("Clinical Assistant Professor, Department of Finance", "United States", "Clinical/Teaching"),
    ("Professor of Practice in Finance", "United States", "Clinical/Teaching"),
    ("Visiting Assistant Professor of Management", "United States", "Visiting"),
    ("Postdoctoral Research Fellow in Finance", "Europe", "Postdoc"),
    ("Lecturer in Accounting and Finance", "UK & Ireland", "Lecturer"),
    ("Senior Lecturer in Marketing", "UK & Ireland", "Associate"),
    ("Professor of Finance", "United States", "Full"),
    ("Dean, College of Business", "United States", "Dean/Admin"),
])
def test_detect_rank(title, region, rank):
    assert C.detect_rank(title, "", region)[0] == rank


def test_tenure_detection():
    assert C.detect_rank("Assistant Professor", "This is a tenure-track position.")[1] == "Yes"
    assert C.detect_rank("Clinical Assistant Professor")[1] == "No"
    assert C.detect_rank("Assistant Professor", "a one-year, non-tenure-track appointment")[1] == "No"


@pytest.mark.parametrize("title,dept,field", [
    ("Assistant Professor of Finance", "", "Finance"),
    ("Assistant Professor in Financial Accounting", "", "Accounting"),
    ("Lecturer in Accounting and Finance", "", "Accounting"),
    ("Assistant Professor of Supply Chain Management", "", "Operations & Supply Chain"),
    ("Assistant Professor of Management Information Systems", "", "Information Systems"),
    ("Assistant Professor - Organizational Behavior and Human Resources", "", "Organizational Behavior & HR"),
    ("Assistant Professor of Risk Management and Insurance", "", "Insurance & Risk"),
    ("Assistant Professor in Strategy and Entrepreneurship", "", "Management & Strategy"),
    ("Assistant Professor of Real Estate", "", "Real Estate"),
    ("Assistant Professor", "Department of Marketing", "Marketing"),
    ("Assistant Professor", "School of Management", "Other / General Business"),
])
def test_detect_fields(title, dept, field):
    assert C.detect_fields(title, dept)[0] == field


def test_default_field_used_when_nothing_matches():
    assert C.detect_fields("Assistant Professor", default="Finance")[0] == "Finance"


def test_description_mentions_of_sibling_departments_do_not_decide_field():
    desc = "Our college houses departments of accounting, marketing and management. " * 2 + \
           "We seek a finance scholar in asset pricing; finance research is valued."
    assert C.detect_fields("Assistant Professor", "Department of Finance", "", desc)[0] == "Finance"


def test_faculty_filter():
    assert C.is_faculty_position("Assistant Professor of Finance")
    assert C.is_faculty_position("Lecturer in Marketing")
    assert not C.is_faculty_position("Financial Analyst")
    assert not C.is_faculty_position("Director of Finance")


def test_business_school_detection():
    assert C.is_business_school("The Wharton School")
    assert C.is_business_school("", "College of Business Administration")
    assert not C.is_business_school("Department of Economics", "College of Arts and Sciences")


@pytest.mark.parametrize("loc,country,expected", [
    ("Chicago, IL", "", "United States"),
    ("Austin, Texas", "", "United States"),
    ("Hong Kong", "", "Hong Kong"),
    ("London, United Kingdom", "", "United Kingdom"),
    ("Shanghai", "", "China"),
    ("Toronto, Ontario", "", "Canada"),
    ("", "GB", "United Kingdom"),
    ("", "DE", "Germany"),
])
def test_detect_country(loc, country, expected):
    assert C.detect_country(loc, country) == expected


def test_region_mapping():
    assert C.region_for("Hong Kong") == "Greater China"
    assert C.region_for("Singapore") == "Asia-Pacific"
    assert C.region_for("") == "Unknown"


def test_materials_and_venues():
    text = ("Please submit a cover letter, CV, job market paper, research statement, teaching statement, "
            "and three letters of recommendation. We will interview at the FMA Annual Meeting and at the "
            "AFA/ASSA meetings in January, or via Zoom.")
    assert C.detect_materials(text) == ["Cover letter", "CV", "Job market paper", "Research statement",
                                        "Teaching statement", "Reference letters"]
    assert C.detect_interview_venues(text) == ["AFA/ASSA", "FMA", "Virtual"]


def test_start_date():
    assert C.extract_start_date("The position begins in Fall 2027.") == "Fall 2027"
    assert C.extract_start_date("Start date: July 1, 2027") == "July 1, 2027"


def test_looks_closed():
    assert C.looks_closed("Sorry, this job has expired.")
    assert C.looks_closed("This position has been filled.")
    assert not C.looks_closed("Applications will be reviewed until the position is filled.")


def test_normalize_institution():
    assert C.normalize_institution("The University of Texas at Austin - McCombs School of Business") == \
        C.normalize_institution("University of Texas at Austin")
