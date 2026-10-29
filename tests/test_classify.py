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


# ---- Chinese-language postings ------------------------------------------------------------
ZH = ("上海交通大学安泰经济与管理学院金融系2027年度招聘。招聘助理教授、副教授、教授（长聘教轨）。"
      "申请人须已获得或在2027年8月前获得金融学或经济学博士学位。申请截止日期：2026年12月31日。年薪 40-80万。"
      "请提交简历、求职信、Job Market Paper及三封推荐信。")


def test_chinese_posting():
    assert C.detect_fields("金融系2027年度招聘", "", "", ZH)[0] == "Finance"
    assert C.detect_rank("金融系2027年度招聘", ZH) == ("Open rank", "Yes")
    assert C.detect_degree(ZH) == "PhD (ABD OK)"
    assert C.extract_deadline(ZH, REF)["deadline"] == "2026-12-31"
    s = C.extract_salary(ZH)
    assert (s["salary_min"], s["salary_max"], s["salary_currency"]) == (400000, 800000, "CNY")
    assert C.detect_materials(ZH) == ["Cover letter", "CV", "Job market paper", "Reference letters"]
    assert C.detect_country("", "", ZH) == "China"
    assert C.business_relevance("金融系2027年度招聘", "上海交通大学", "")
    assert C.is_faculty_position("经济学院专任教师招聘公告")


def test_chinese_deadline_forms():
    assert C.extract_deadline("报名截止时间为2026年11月30日17:00", REF)["deadline"] == "2026-11-30"
    assert C.extract_deadline("请于12月15日前提交材料", REF)["deadline"] == "2026-12-15"
    assert C.extract_deadline("招满为止", REF)["open_until_filled"]


def test_business_relevance_rules():
    assert C.business_relevance("Assistant Professor (Applied Microeconomics)", "Arizona State University",
                                "W. P. Carey School of Business - Economics")
    assert not C.business_relevance("Assistant Professor", "Example University", "Department of Economics")
    assert not C.business_relevance("Assistant/Associate Professor", "Simon Fraser University", "Economics")
    assert not C.business_relevance("Faculty", "X", "All departments",
                                    "Econometrics; Finance; Macro; Labor; Marketing; Any field; IO")
    assert C.business_relevance("Faculty", "X", "", "Finance")


@pytest.mark.parametrize("text,day_first,expected", [
    ("05/11/2026", None, "2026-05-11"),                                   # US order by default
    ("05/11/2026", True, "2026-11-05"),                                   # source says day first
    ("22/10/2026", None, "2026-10-22"),                                   # only day/month is possible
    ("Posted 22/10/2026. Deadline: 05/11/2026", None, "2026-11-05"),      # the other date decides
    ("10/22/2026 and 11/05/2026", None, "2026-11-05"),
    ("30.11.2026", None, "2026-11-30"),                                   # dotted dates are day first
])
def test_numeric_dates(text, day_first, expected):
    assert str(C.find_dates(text, REF, day_first)[-1][2]) == expected


def test_european_deadline_forms():
    assert C.extract_deadline("The deadline for submission is 30.11.2026, at midnight.", REF)["deadline"] == "2026-11-30"
    assert C.extract_deadline("Closing date: 05/11/2026", REF, day_first=True)["deadline"] == "2026-11-05"


def test_phd_places_are_not_faculty_jobs():
    assert not C.is_faculty_position("Fully Funded Four-Year PhD Graduate Teaching Fellowships in Management")
    assert not C.is_faculty_position("PhD Candidate in Marketing")
    assert not C.is_faculty_position("Ph.D. Programme in Accounting, Economics, Finance, and Management")
    assert C.is_faculty_position("Postdoctoral Position for PhD graduates in Finance")


def test_european_titles():
    assert C.is_faculty_position("Lectureships in Finance and Marketing")
    assert C.is_faculty_position("Professeur de Stratégie en Executive Education")
    assert C.detect_rank("Assistant Professorship (Tenure Track) in Entrepreneurship")[0] == "Assistant"
    assert C.detect_rank("Associate Professorship / Assistant Professorship in Innovation")[0] == "Assistant/Associate"
    assert C.detect_rank("Lecturers and Graduate Tutors in Marketing", "", "Asia-Pacific")[0] == "Lecturer"
    # "all ranks" in the school's blurb does not override a title that names one rank
    assert C.detect_rank("Assistant Professor in Marketing", "The school hires at all ranks.")[0] == "Assistant"
    assert C.detect_rank("Faculty Positions", "The school hires at all ranks.")[0] == "Open rank"


def test_non_business_subjects_at_business_schools():
    desc = "The school is known for finance research and its finance, accounting and finance programmes."
    assert C.detect_fields("Assistant Professor – Geopolitics", "", "Geopolitics", desc)[0] == "Other / General Business"
    assert C.detect_fields("Assistant / Associate Professor of Law", "", "Law", desc)[0] == "Business Law & Ethics"
    # a law faculty's name is not a business-law position
    assert "Business Law & Ethics" not in C.detect_fields("Full Professor Banking & Finance",
                                                          "Faculty of Law, Economics and Governance")[1]


def test_more_business_schools_and_countries():
    assert C.is_business_school("Grenoble Ecole de Management")
    assert C.is_business_school("University of St.Gallen")
    assert C.is_business_school("EDHEC Business School") and C.is_business_school("ESCP")
    assert not C.is_business_school("Higher Education Commission (HEC), Pakistan")
    assert C.business_relevance("Assistant Professor in Sales, Business Development, Negotiation")
    assert C.detect_country("Cambodia / Phnom Penh") == "Cambodia"


def test_far_future_board_date_is_not_a_deadline():
    from tracker.enrich import enrich
    from tracker.sources.base import RawJob
    today = date(2026, 10, 29)
    far = enrich(RawJob(source="THE", source_id="1", url="u", title="Assistant Professor in Accounting",
                        description="Applications are reviewed until the position is filled.",
                        deadline_raw="29/10/2027", day_first=True), today)
    assert far["deadline"] == "" and "listed until Oct 29, 2027" in far["deadline_note"]
    near = enrich(RawJob(source="THE", source_id="2", url="u", title="Assistant Professor in Accounting",
                         deadline_raw="15/01/2027", day_first=True), today)
    assert near["deadline"] == "2027-01-15"
