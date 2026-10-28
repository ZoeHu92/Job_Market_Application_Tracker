"""Turn free-text job postings into structured fields.

Everything here is heuristic and deliberately conservative: when a value cannot
be found with reasonable confidence it is left blank (or "Unknown") rather than
guessed. Each function is pure and unit-tested in tests/test_classify.py.
"""
from __future__ import annotations

import re
from datetime import date, timedelta

# ---------------------------------------------------------------------------
# Business fields
# ---------------------------------------------------------------------------

# Phrases that contain a field word but belong to another field; they are
# rewritten before matching so e.g. "financial accounting" is not Finance.
_REWRITES = [
    (r"financial (accounting|reporting|statements?|statement analysis)", r"accounting \1"),
    (r"management accounting", "accounting"),
    (r"financial aid", ""),
    (r"(operations|supply chain|project|production|service|logistics) management", r"operations \1"),
    (r"management science", "operations research"),
    (r"management information systems?", "information systems"),
    (r"information (technology )?management", "information systems"),
    (r"(human resources?|people|talent) management", "human resources"),
    (r"risk management", "risk-management"),
    (r"(hospitality|hotel|tourism|sport|sports|event) management", r"\1"),
    (r"(health ?care|health|engineering|construction|public|arts) management", r"\1 admin"),
    (r"financial management association", "fma"),
    (r"(school|college|faculty|department|institute|division) of management", "business school"),
    (r"management (school|college|faculty)", "business school"),
    (r"business administration", "business school"),
]

FIELD_PATTERNS: dict[str, list[str]] = {
    "Finance": [
        r"\bfinance\b", r"\bfinancial (economics|markets?|institutions?|engineering|technology|intermediation|management)\b",
        r"\bbanking\b", r"\binvestments?\b", r"\basset pricing\b", r"\bcorporate finance\b", r"\bfintech\b",
        r"\bjel[: ]*g\d", r"\bquantitative finance\b",
    ],
    "Accounting": [r"\baccounting\b", r"\baccountancy\b", r"\baudit(ing)?\b", r"\btaxation\b", r"\bjel[: ]*m4\d?"],
    "Marketing": [
        r"\bmarketing\b", r"\bconsumer (behaviou?r|research|psychology)\b", r"\badvertising\b",
        r"\bretailing\b", r"\bjel[: ]*m3\d?",
    ],
    "Management & Strategy": [
        r"\bstrategy\b", r"\bstrategic management\b", r"\bbusiness policy\b", r"\bmanagement\b",
        r"\bjel[: ]*m1\d?",
    ],
    "Organizational Behavior & HR": [
        r"\borgani[sz]ational (behaviou?r|theory|studies|psychology)\b", r"\bhuman resources?\b", r"\bhrm\b",
        r"\bleadership\b", r"\b(industrial|labou?r|employment) relations\b", r"\bnegotiations?\b",
        r"\bwork and organi[sz]ations?\b", r"\bjel[: ]*m5\d?",
    ],
    "Operations & Supply Chain": [
        r"\boperations\b", r"\boperations research\b", r"\bsupply chain\b", r"\blogistics\b",
        r"\bdecision sciences?\b", r"\bjel[: ]*m11\b",
    ],
    "Information Systems": [
        r"\binformation systems\b", r"\bmis\b", r"\binformation technology\b", r"\bdigital (innovation|transformation|business|platforms?)\b",
        r"\be-?commerce\b", r"\bbusiness information\b", r"\bjel[: ]*m15\b",
    ],
    "Business Analytics & Statistics": [
        r"\b(business )?analytics\b", r"\bdata science\b", r"\bstatistics\b", r"\bmachine learning\b",
        r"\bartificial intelligence\b", r"\bquantitative methods\b", r"\bdecision analytics\b",
    ],
    "Economics": [r"\beconomics\b", r"\beconomist\b", r"\bmanagerial economics\b", r"\bbusiness economics\b"],
    "Real Estate": [r"\breal estate\b", r"\burban land\b", r"\bproperty\b", r"\bjel[: ]*r3\d?"],
    "Insurance & Risk": [r"\binsurance\b", r"\brisk-management\b", r"\bactuarial\b"],
    "Entrepreneurship & Innovation": [
        r"\bentrepreneur(ship|ial)?\b", r"\binnovation\b", r"\bventure\b", r"\bfamily business\b",
        r"\btechnology management\b",
    ],
    "International Business": [r"\binternational business\b", r"\bglobal business\b", r"\binternational management\b"],
    "Business Law & Ethics": [r"\bbusiness law\b", r"\blegal studies\b", r"\bbusiness ethics\b", r"\blaw and ethics\b"],
    "Hospitality & Tourism": [r"\bhospitality\b", r"\btourism\b", r"\bhotel\b"],
}
# Chinese-language postings (CJK characters are \\w, so these patterns have no \\b).
FIELD_PATTERNS_ZH: dict[str, list[str]] = {'Finance': ['金融', '投资学', '资产定价', '公司财务'], 'Accounting': ['会计', '审计', '财务管理', '税务'], 'Marketing': ['营销'], 'Management & Strategy': ['战略', '企业管理', '工商管理'], 'Organizational Behavior & HR': ['组织行为', '组织管理', '人力资源', '领导力'], 'Operations & Supply Chain': ['运营管理', '运作管理', '供应链', '物流', '管理科学', '运筹'], 'Information Systems': ['信息系统', '信息管理', '信息、技术与创新', '信息技术与创新'], 'Business Analytics & Statistics': ['商业分析', '商务智能', '大数据', '统计学'], 'Economics': ['经济学', '经济系'], 'Real Estate': ['房地产'], 'Insurance & Risk': ['保险', '精算', '风险管理'], 'Entrepreneurship & Innovation': ['创业'], 'International Business': ['国际商务'], 'Hospitality & Tourism': ['旅游', '酒店管理']}
for _f, _pats in FIELD_PATTERNS_ZH.items():
    FIELD_PATTERNS[_f] = FIELD_PATTERNS[_f] + _pats
_FIELD_RES = {f: [re.compile(p, re.I) for p in pats] for f, pats in FIELD_PATTERNS.items()}

BUSINESS_FIELDS = [f for f in FIELD_PATTERNS if f != "Economics"]


def _rewrite(text: str) -> str:
    out = text.lower()
    for pat, rep in _REWRITES:
        out = re.sub(pat, rep, out)
    return out


def _field_hits(text: str, positions: dict[str, int] | None = None) -> dict[str, int]:
    """Count keyword hits per field; optionally record each field's first match offset."""
    text = _rewrite(text or "")
    hits = {}
    for field, regs in _FIELD_RES.items():
        matches = [m.start() for r in regs for m in r.finditer(text)]
        if matches:
            hits[field] = len(matches)
            if positions is not None:
                positions[field] = min(matches)
    # "management" alone is weak evidence when a more specific field is present.
    if "Management & Strategy" in hits and len(hits) > 1:
        specific = re.search(r"\bstrateg|business policy", text)
        if not specific:
            hits.pop("Management & Strategy")
    return hits


def detect_fields(title: str = "", department: str = "", categories: str = "",
                  description: str = "", default: str = "") -> tuple[str, list[str]]:
    """Return (primary field, all fields) for a posting.

    Title evidence dominates, then department and source categories. The
    description is only used when nothing else matched, because it usually
    mentions sibling departments ("our college has departments of ...").
    """
    scores: dict[str, float] = {}
    order: list[str] = []
    for text, weight in ((title, 5.0), (department, 3.0), (categories, 3.0)):
        pos: dict[str, int] = {}
        hits = _field_hits(text, pos)
        for f in sorted(hits, key=pos.get):  # earlier mention wins ties ("Accounting and Finance")
            scores[f] = scores.get(f, 0) + weight * hits[f]
            if f not in order:
                order.append(f)
    if not scores and description:
        for f, n in _field_hits(description[:2500]).items():
            scores[f] = scores.get(f, 0) + min(n, 4)
            if f not in order:
                order.append(f)
        # Require some repetition before trusting description-only evidence.
        scores = {f: s for f, s in scores.items() if s >= 2}
    if not scores:
        return (default or "Other / General Business", [default] if default else [])
    ranked = sorted(scores, key=lambda f: (-scores[f], order.index(f)))
    primary = ranked[0]
    if default and default in scores and scores[default] >= scores[primary] * 0.6:
        primary = default
    fields = [primary] + [f for f in ranked if f != primary and scores[f] >= 3]
    return primary, fields


# ---------------------------------------------------------------------------
# Business-school and faculty detection
# ---------------------------------------------------------------------------

_BSCHOOL_RE = re.compile(
    r"business school|school of business|college of business|business administration|"
    r"graduate school of (business|management)|(school|college|faculty|institute) of (economics and )?management|"
    r"economics and management|management and economics|faculty of (business|commerce)|school of commerce|"
    r"business and economics|economics and business|school of (accountancy|accounting|finance)|"
    r"\b(wharton|insead|hec (paris|montr[ée]al|lausanne)|ceibs|ckgsb|kenan-flagler)\b",
    re.I,
)


_BSCHOOL_ZH = re.compile(r"商学院|管理学院|经济管理学院|经济与管理学院|经管学院|金融学院|会计学院|工商管理学院|"
                         r"高级金融学院|经济与工商管理学院|财经大学|金融科技学院")


def is_business_school(*texts: str) -> bool:
    return any(t and (_BSCHOOL_RE.search(_rewrite(t)) or _BSCHOOL_ZH.search(t)) for t in texts)


# Subject words that, in a title / employer / department, mark a business-school position.
# Deliberately narrower than FIELD_PATTERNS: "management", "statistics", "innovation"
# or "leadership" on their own also describe public-policy, science and admin jobs.
_BIZ_SUBJECT = re.compile(
    r"\b(finance|financial (economics|markets?|engineering|technology|management)|fintech|banking|accounting|"
    r"accountancy|auditing|taxation|marketing|strateg(y|ic management)|organi[sz]ational behaviou?r|"
    r"organi[sz]ation(al)? (theory|studies)|human resource|operations management|supply chain|management science|"
    r"decision sciences?|information systems|business analytics|entrepreneur\w*|international business|real estate|"
    r"insurance|risk management|business (law|ethics|economics|administration|studies)|managerial economics|"
    r"(professor|lecturer|faculty|department|area|group) (of|in) management|management (department|area|group|unit))\b",
    re.I,
)


_BIZ_SUBJECT_ZH = re.compile(r"金融|会计|审计|财务|营销|战略管理|企业管理|工商管理|组织行为|组织管理|人力资源|运营管理|"
                             r"供应链|管理科学|信息系统|商业分析|商务智能|创业|国际商务|房地产|保险|精算")


def business_relevance(title: str = "", institution: str = "", department: str = "", categories: str = "",
                       text: str = "") -> bool:
    """Is this a business-school position?

    True when a business subject is named in the title, employer or department;
    when a short category list (not EJM-style "any field" lists) names one; or
    when the employer / department / opening text names a business school.
    """
    head = " ".join([title or "", institution or "", department or ""])
    if _BIZ_SUBJECT.search(head) or _BIZ_SUBJECT_ZH.search(head):
        return True
    cats = [c for c in re.split(r"[;,\n|]", categories or "") if c.strip()]
    if 0 < len(cats) <= 5 and _BIZ_SUBJECT.search(categories):
        return True
    return is_business_school(institution, department, (text or "")[:500])


_FACULTY_RE = re.compile(
    r"professor|lecturer|faculty|instructor|post-?doc|postdoctoral|research fellow|reader\b|"
    r"tenure|chair\b|chair in|teaching fellow|assistant prof|associate prof|\bdean\b|academic position|"
    r"教授|讲师|教师|博士后|研究员|师资|教职|教研|教学科研|诚聘|英才|人才招聘",
    re.I,
)
_NON_FACULTY_RE = re.compile(
    r"\b(analyst|accountant|bookkeeper|clerk|controller|coordinator|specialist|technician|officer|"
    r"advisor|adviser|counsel(or)?|assistant to|administrative|payroll|bursar|recruiter|manager|director|"
    r"engineer|programmer|scientist|economists?|research (associate|assistant)|associate in research|intern(ship)?|"
    r"phd (hire|researcher))\b",
    re.I,
)


def is_faculty_position(title: str, context: str = "") -> bool:
    """True for professor / lecturer / postdoc style roles, False for staff jobs."""
    title = title or ""
    if _FACULTY_RE.search(title):
        return True
    if _NON_FACULTY_RE.search(title):
        return False
    return bool(context and _FACULTY_RE.search(context[:600]))


# ---------------------------------------------------------------------------
# Rank and tenure
# ---------------------------------------------------------------------------

_LECTURER_REGIONS = {"UK & Ireland", "Asia-Pacific", "Greater China", "Europe"}


def detect_rank(title: str, description: str = "", region: str = "") -> tuple[str, str]:
    """Return (rank label, tenure-track Yes/No/Unknown)."""
    t = (title or "").lower()
    d = (description or "")[:4000].lower()

    asst = bool(re.search(r"assistant[\s/,-]*(professor|prof\.?)\b|\basst\.? prof", t))
    assoc = bool(re.search(r"associate[\s/,-]*(professor|prof\.?)\b|\bassoc\.? prof", t))
    # "Assistant/Associate Professor", "Assistant or Associate Professor"
    if re.search(r"assistant\s*(/|,|or|and|&)\s*(\w+\s+)?associate", t):
        asst = assoc = True
    if re.search(r"associate\s*(/|,|or|and|&)\s*(full\s*)?professor", t):
        assoc = True
    plain_prof = bool(re.search(r"\bprofessor\b(?! of (the )?practice)", t)) and not re.search(
        r"(clinical|teaching|visiting|adjunct|research|assistant|associate|practice)\s+professor", t)
    full = bool(re.search(r"\bfull\b", t)) or (plain_prof and not asst and not assoc)
    open_rank = bool(re.search(r"open[- ]rank|all ranks|any rank|rank open|rank is open|ranks? (are|is) open", t + " " + d[:600]))

    if re.search(r"\bdean\b|department (head|chair)|head of (department|school)|director of", t):
        rank = "Dean/Admin"
    elif re.search(r"post-?doc|postdoctoral|post-doctoral", t):
        rank = "Postdoc"
    elif re.search(r"\bvisiting\b", t):
        rank = "Visiting"
    elif re.search(r"clinical|teaching (professor|track|faculty|stream)|professor of (the )?practice|practice professor|"
                   r"\binstructor\b|\badjunct\b|lecturer in practice|professional track|pro tem|non[- ]tenure|"
                   r"part[- ]time|practice track", t):
        rank = "Clinical/Teaching"
    elif open_rank or (asst and assoc and full):
        rank = "Open rank"
    elif asst and assoc:
        rank = "Assistant/Associate"
    elif asst:
        rank = "Assistant"
    elif assoc and full:
        rank = "Associate/Full"
    elif assoc:
        rank = "Associate"
    elif re.search(r"endowed|distinguished|chair\b|chaired", t):
        rank = "Chair/Endowed"
    elif re.search(r"senior lecturer|associate lecturer|\blecturer\b|\breader\b", t):
        if re.search(r"(?<!senior )(?<!associate )\blecturer\b", t) and "senior lecturer" in t:
            rank = "Lecturer"  # "Lecturer/Senior Lecturer": open to entry level
        elif "senior lecturer" in t or "reader" in t:
            rank = "Associate" if region in _LECTURER_REGIONS else "Clinical/Teaching"
        else:
            rank = "Lecturer" if region in _LECTURER_REGIONS or not region else "Clinical/Teaching"
    elif full:
        rank = "Full"
    elif re.search(r"tenure[- ]track|faculty position|faculty member|faculty", t):
        # "Tenure-track faculty position in Finance" - usually assistant-level unless stated.
        if re.search(r"assistant professor", d):
            rank = "Assistant" if not re.search(r"associate professor", d) else "Assistant/Associate"
        else:
            rank = "Open rank" if re.search(r"(all|any|open) ranks?|rank open", d) else "Unspecified"
    elif re.search(r"research fellow", t):
        rank = "Postdoc"
    else:
        rank = "Unspecified"

    if rank == "Unspecified":
        rank = _rank_zh(title or "", (description or "")[:3000]) or _rank_from_text(d[:2500]) or rank

    both = t + " " + d
    if re.search(r"non[- ]tenure|not tenure[- ]track|fixed[- ]term|one[- ]year|term appointment", both) or rank in (
            "Clinical/Teaching", "Visiting", "Postdoc"):
        tenure = "No"
    elif re.search(r"tenure[- ](track|eligible|stream|line)|tenured|tenure system|\bon tenure\b|长聘|预聘|准聘|常任轨|终身教职", both):
        tenure = "Yes"
    elif rank == "Lecturer" and re.search(r"permanent|open[- ]ended|indefinite", both):
        tenure = "Yes"
    else:
        tenure = "Unknown"
    return rank, tenure


def _rank_from_text(d: str) -> str:
    """Rank words in an English description, for titles like '金融系2027年度招聘'."""
    if re.search(r"all (ranks|levels)|open[- ]rank|any rank", d):
        return "Open rank"
    asst = "assistant professor" in d
    assoc = "associate professor" in d
    full = bool(re.search(r"(?<!assistant )(?<!associate )\b(full )?professors?\b(?! of practice)", d))
    if asst and assoc and full:
        return "Open rank"
    if asst and assoc:
        return "Assistant/Associate"
    if asst:
        return "Assistant"
    if assoc:
        return "Associate/Full" if full else "Associate"
    return ""


def _rank_zh(title: str, desc: str) -> str:
    """Rank from Chinese wording (助理教授 / 副教授 / 教授 / 讲师 / 博士后)."""
    for text in (title, desc):
        if not text:
            continue
        if re.search(r"各级|所有职级|不限职级|各职级|职级不限", text):
            return "Open rank"
        asst = "助理教授" in text or "讲师" in text
        assoc = "副教授" in text
        full = bool(re.search(r"(?<!助理)(?<!副)教授", text))
        if asst and assoc and full:
            return "Open rank"
        if asst and assoc:
            return "Assistant/Associate"
        if assoc and full:
            return "Associate/Full"
        if "助理教授" in text:
            return "Assistant"
        if assoc:
            return "Associate"
        if "博士后" in text:
            return "Postdoc"
        if "讲师" in text:
            return "Lecturer"
        if full:
            return "Full"
    return ""


def is_entry_level(rank: str) -> bool:
    return rank in {"Assistant", "Assistant/Associate", "Open rank", "Lecturer", "Postdoc", "Visiting", "Unspecified"}


# ---------------------------------------------------------------------------
# Degree requirement
# ---------------------------------------------------------------------------

_PHD_RE = re.compile(r"ph\.?\s?d\b|doctoral degree|doctorate|d\.b\.a\.?|\bdba\b|terminal degree|博士学位|博士研究生|博士", re.I)
_ABD_RE = re.compile(
    r"\babd\b|all[- ]but[- ]dissertation|near(ing)? completion|expected (to (be )?(complete|completed|conferred|finish)|by|before)|"
    r"anticipated|(completed?|conferred|in hand|awarded) (by|before|prior to) (the )?(start|time|date|beginning)|"
    r"by the (start|time|beginning) of (the )?(appointment|employment)|final stages|candidates? (who are )?close to|"
    r"near the completion|will (have )?complete|应届|即将获得|预计.{0,12}获得|博士在读|前获得|毕业前|"
    r"(required|expected|needed|in hand) (by|before|prior to) (the )?(start|beginning|time|date|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|fall|summer|autumn)",
    re.I,
)
_MASTERS_RE = re.compile(r"master'?s degree|\bmba\b|master of", re.I)


_PHD_PREFERRED_RE = re.compile(r"(ph\.?\s?d\.?|doctora\w*|terminal degree)[^.;]{0,40}\b(preferred|desirable|a plus|an advantage)|"
                               r"(preferred|desirable)[^.;]{0,30}(ph\.?\s?d|doctora\w*)", re.I)


def detect_degree(text: str) -> str:
    t = text or ""
    if _MASTERS_RE.search(t) and _PHD_PREFERRED_RE.search(t):
        return "Master's+"
    if _PHD_RE.search(t):
        # ABD language is meaningful only near a doctoral mention.
        for m in _PHD_RE.finditer(t):
            window = t[max(0, m.start() - 250): m.end() + 300]
            if _ABD_RE.search(window):
                return "PhD (ABD OK)"
            # "...a doctoral degree in finance by August 10, 2027" (same sentence only)
            start = max(t.rfind(".", 0, m.start()), t.rfind("\n", 0, m.start()), t.rfind("•", 0, m.start())) + 1
            ends = [i for i in (t.find(". ", m.end()), t.find("\n", m.end())) if i >= 0]
            sentence = t[start:min(ends) if ends else len(t)]
            if re.search(r"\bby (the )?(start|beginning|time|date|commencement|(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|fall|summer|autumn)\w*)",
                         sentence, re.I):
                return "PhD (ABD OK)"
        return "PhD required"
    if _MASTERS_RE.search(t):
        return "Master's+"
    return "Not stated"


# ---------------------------------------------------------------------------
# Dates: deadlines, review start, start date
# ---------------------------------------------------------------------------

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3, "apr": 4, "april": 4,
    "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7, "aug": 8, "august": 8, "sep": 9, "sept": 9,
    "september": 9, "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
_MON = r"(?P<mon>jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?"
_DAY = r"(?P<day>\d{1,2})(?:st|nd|rd|th)?"
_YEAR = r"(?P<year>(?:19|20)\d{2})"
_DATE_PATTERNS = [
    re.compile(r"(?P<year>20\d{2})\s*年\s*(?P<month>\d{1,2})\s*月\s*(?P<day>\d{1,2})\s*[日号]"),
    re.compile(r"(?<![\d年])(?P<month>\d{1,2})\s*月\s*(?P<day>\d{1,2})\s*[日号]"),
    re.compile(rf"\b{_MON}\s+{_DAY}(?:\s*,\s*|\s+){_YEAR}\b", re.I),
    re.compile(rf"\b{_DAY}\s+(?:of\s+)?{_MON}(?:\s*,\s*|\s+){_YEAR}\b", re.I),
    re.compile(rf"\b(?P<year>(?:19|20)\d{{2}})-(?P<month>\d{{1,2}})-(?P<day>\d{{1,2}})\b"),
    re.compile(r"\b(?P<month>\d{1,2})/(?P<day>\d{1,2})/(?P<year>(?:20)?\d{2})\b"),
    re.compile(rf"\b{_MON}\s+{_DAY}\b(?!\s*,?\s*(?:19|20)\d{{2}})", re.I),
    re.compile(rf"\b{_DAY}\s+(?:of\s+)?{_MON}\b(?!\s*,?\s*(?:19|20)\d{{2}})", re.I),
]

_DEADLINE_CUE = re.compile(
    r"deadline|\bdue\b|closing date|\bcloses?\b|close of applications|apply by|apply no later|"
    r"(received|submitted|complete[d]?|considered|accepted|apply|applications?)\b[^.;\n]{0,40}\b(by|before|no later than|prior to|until)\b|"
    r"no later than|full consideration|priority consideration|priority deadline|applications? (will be )?accepted until|"
    r"截止|截至|报名时间|申请时间|申请期限",
    re.I,
)
_REVIEW_CUE = re.compile(
    r"review (of )?(applications|applicants|candidates|files)?\s*(will )?(begin|start|commence)|"
    r"(screening|consideration|evaluation|interviews?) (of applications )?(will )?(begin|start|commence)|"
    r"begin (reviewing|to review|review)|start (reviewing|to review)",
    re.I,
)
_UNTIL_FILLED = re.compile(
    r"until (the )?(position|positions|search|vacancy|post|role|job)s? (is|are|has been|have been)? ?(filled|closed|completed)|"
    r"open until filled|until filled|until a suitable candidate|until an appointment is made|until the search (is )?(concluded|complete)|"
    r"招满为止|直至招满|招满即止|长期有效|直至岗位招满",
    re.I,
)


def _mk_date(year: int | None, month: int, day: int, ref: date) -> date | None:
    try:
        if year is None:
            d = date(ref.year, month, day)
            # A year-less date refers to the next occurrence after the posting date.
            if d < ref - timedelta(days=45):
                d = date(ref.year + 1, month, day)
            return d
        if year < 100:
            year += 2000
        return date(year, month, day)
    except ValueError:
        return None


def find_dates(text: str, ref: date) -> list[tuple[int, int, date]]:
    """All dates in text as (start, end, date), non-overlapping, in text order."""
    found: list[tuple[int, int, date]] = []
    taken: list[tuple[int, int]] = []
    for pat in _DATE_PATTERNS:
        for m in pat.finditer(text):
            if any(m.start() < e and s < m.end() for s, e in taken):
                continue
            g = m.groupdict()
            if g.get("mon"):
                month = _MONTHS.get(g["mon"].lower().rstrip("."), 0)
                if not month and g["mon"].lower().startswith("sept"):
                    month = 9
            else:
                month = int(g["month"])
            if not month or month > 12:
                continue
            year = int(g["year"]) if g.get("year") else None
            # Bare "May 5" style matches are only trusted with a cue; "may" is also a verb.
            if g.get("mon") and g["mon"].lower() == "may" and year is None:
                continue
            d = _mk_date(year, month, int(g["day"]), ref)
            if d:
                found.append((m.start(), m.end(), d))
                taken.append((m.start(), m.end()))
    found.sort()
    return found


def _sentence_window(text: str, start: int, end: int) -> tuple[str, str]:
    """Text before (same sentence, max 160 chars) and after (max 40 chars) a span."""
    left = text[max(0, start - 160):start]
    cut = max(left.rfind(". "), left.rfind("\n"), left.rfind("; "), left.rfind("。"), left.rfind("；"))
    if cut >= 0:
        left = left[cut + 1:]
    right = text[end:end + 40]
    return left, right


def fmt_date(d: date) -> str:
    return f"{d:%b} {d.day}, {d.year}"


def parse_date_string(value: str, ref: date | None = None) -> date | None:
    """Parse one date from a short string such as a source's 'Deadline' field."""
    if not value:
        return None
    ref = ref or date.today()
    v = str(value).strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", v)
    if m:
        return _mk_date(int(m.group(1)), int(m.group(2)), int(m.group(3)), ref)
    ds = find_dates(v, ref)
    return ds[0][2] if ds else None


def extract_deadline(text: str, ref: date | None = None) -> dict:
    """Find application deadline, review start and 'open until filled' language.

    Returns dict(deadline, review_start, open_until_filled, note) with ISO dates
    or "" for unknown. When several deadlines are stated, the earliest one that
    is not long before the posting date is returned, because that is the date a
    candidate must act by.
    """
    ref = ref or date.today()
    text = re.sub(r"\s+", " ", text or "")
    deadlines: list[date] = []
    reviews: list[date] = []
    for s, e, d in find_dates(text, ref):
        left, right = _sentence_window(text, s, e)
        if _REVIEW_CUE.search(left):
            reviews.append(d)
        elif _DEADLINE_CUE.search(left[-110:]) or re.match(r"\s*(is|will be)? ?the (application )?deadline", right, re.I) \
                or re.match(r"\s*(\d{1,2}[:：]\d{2})?\s*(前|之前|以前|止|截止)", right):
            deadlines.append(d)
    floor = ref - timedelta(days=120)
    deadlines = sorted(x for x in deadlines if x >= floor)
    reviews = sorted(x for x in reviews if x >= floor)
    until = bool(_UNTIL_FILLED.search(text))
    parts = []
    if deadlines:
        parts.append(f"Deadline {fmt_date(deadlines[0])}")
        if len(set(deadlines)) > 1:
            parts.append(f"final {fmt_date(deadlines[-1])}")
    if reviews:
        parts.append(f"review begins {fmt_date(reviews[0])}")
    if until:
        parts.append("open until filled")
    note = "; ".join(parts)
    return {
        "deadline": deadlines[0].isoformat() if deadlines else "",
        "review_start": reviews[0].isoformat() if reviews else "",
        "open_until_filled": until,
        "deadline_note": note[:1].upper() + note[1:] if note else "",
    }


_START_RE = re.compile(
    r"(?:start(?:ing)?|begin(?:ning|s)?|commenc(?:e|ing|es)|effective|appointment)\s*(?:date\s*)?:?\s*"
    r"(?:is\s+|will be\s+|on\s+|in\s+|as early as\s+|of\s+)?"
    r"(?P<when>(?:fall|autumn|spring|summer|winter)\s+(?:semester\s+)?(?:of\s+)?20\d{2}|"
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?\s+(?:\d{1,2}(?:st|nd|rd|th)?,?\s+)?20\d{2}|"
    r"(?:the\s+)?(?:20\d{2}[-–/]20?\d{2}|20\d{2})\s+academic year)",
    re.I,
)
_SEASON_RE = re.compile(r"\b(fall|autumn)\s+(semester\s+)?(of\s+)?(20\d{2})\b", re.I)


def extract_start_date(text: str) -> str:
    t = re.sub(r"\s+", " ", text or "")
    m = _START_RE.search(t)
    if m:
        return re.sub(r"\s+", " ", m.group("when")).strip().title().replace("Of ", "of ")
    m = _SEASON_RE.search(t)
    return f"Fall {m.group(4)}" if m else ""


# ---------------------------------------------------------------------------
# Salary
# ---------------------------------------------------------------------------

_CUR = (r"(?P<cur>US\$|USD|CAD|C\$|A\$|AUD|NZ\$|HK\$|HKD|S\$|SGD|CHF|EUR|GBP|RMB|CNY|JPY|KRW|"
        r"\$|£|€|¥)")
_AMT = r"(?P<amt>\d{1,3}(?:[,.\s]\d{3})+(?:\.\d{2})?|\d+(?:\.\d+)?\s?[kK]\b|\d{4,7}(?:\.\d{2})?)"
_SAL_RE = re.compile(
    rf"{_CUR}\s?{_AMT}"
    rf"(?:\s*(?:-|–|—|to|and)\s*(?:{_CUR.replace('cur', 'cur2')})?\s?{_AMT.replace('amt', 'amt2')})?"
    r"(?:\s*(?P<period>per (?:annum|year|month|academic year|nine[- ]month)|annually|/\s?(?:yr|year|month|mo)|a year|p\.?a\.?))?",
    re.I,
)
_SAL_CUE = re.compile(r"salary|compensation|pay (range|scale|band)|base pay|hiring range|remuneration|grade|"
                      r"stipend|per annum|annual|starting at|range is|range of", re.I)
_SAL_NEG = re.compile(r"research (fund|grant|support|budget|account)|start-?up|endow|million|travel|"
                      r"summer support|fee|tuition|scholarship|award|prize|gift", re.I)
_CUR_NORMAL = {"US$": "USD", "$": "USD", "USD": "USD", "£": "GBP", "GBP": "GBP", "€": "EUR", "EUR": "EUR",
               "CAD": "CAD", "C$": "CAD", "A$": "AUD", "AUD": "AUD", "NZ$": "NZD", "HK$": "HKD", "HKD": "HKD",
               "S$": "SGD", "SGD": "SGD", "CHF": "CHF", "RMB": "CNY", "CNY": "CNY", "¥": "CNY", "JPY": "JPY",
               "KRW": "KRW"}


def _amount(s: str) -> float | None:
    s = s.strip().replace(" ", "")
    mult = 1000 if s[-1:] in "kK" else 1
    s = s.rstrip("kK")
    if re.fullmatch(r"\d{1,3}([.,]\d{3})+(\.\d{2})?", s):
        # 120,000 / 120.000 (European) / 120,000.00
        if re.search(r"\.\d{2}$", s) and "," in s:
            s = s[:-3]
        s = re.sub(r"[.,]", "", s)
    try:
        return float(s) * mult
    except ValueError:
        return None


_SAL_ZH = re.compile(r"(年薪|薪酬|待遇|薪资)[^。；\n]{0,20}?(?P<a>\d+(?:\.\d+)?)\s*(?:-|—|–|~|～|至|到)\s*(?P<b>\d+(?:\.\d+)?)\s*万"
                     r"|(?P<a2>\d+(?:\.\d+)?)\s*(?:-|—|–|~|～|至|到)\s*(?P<b2>\d+(?:\.\d+)?)\s*万(元)?\s*/\s*年")


def extract_salary(text: str) -> dict:
    """Find a stated salary (range). Returns dict(salary_min, salary_max, salary_currency, salary_text)."""
    empty = {"salary_min": None, "salary_max": None, "salary_currency": "", "salary_text": ""}
    t = re.sub(r"\s+", " ", text or "")
    m = _SAL_ZH.search(t)
    if m:
        a, b = float(m.group("a") or m.group("a2")), float(m.group("b") or m.group("b2"))
        if 5 <= a <= b <= 1000:
            return {"salary_min": a * 10000, "salary_max": b * 10000, "salary_currency": "CNY",
                    "salary_text": f"RMB {a:g}–{b:g}万/yr"}
    best = None
    for m in _SAL_RE.finditer(t):
        left = t[max(0, m.start() - 120):m.start()]
        right = t[m.end():m.end() + 30]
        if not (_SAL_CUE.search(left[-90:]) or m.group("period") or _SAL_CUE.search(right)):
            continue
        clause_left = re.split(r"[.;]\s", left[-70:])[-1]
        clause_right = re.split(r"[.;]\s", right)[0][:20]
        if _SAL_NEG.search(clause_left + " " + clause_right):
            continue
        a = _amount(m.group("amt"))
        b = _amount(m.group("amt2")) if m.group("amt2") else None
        if a is None:
            continue
        period = (m.group("period") or "").lower()
        monthly = "month" in period or "/mo" in period
        floor = 2000 if monthly else 20000
        if a < floor or (b is not None and (b < a or b > a * 4)):
            continue
        cur = _CUR_NORMAL.get((m.group("cur") or "").upper(), _CUR_NORMAL.get(m.group("cur") or "", ""))
        best = (a, b, cur, m.group(0).strip())
        break
    if not best:
        return empty
    a, b, cur, raw = best
    return {"salary_min": a, "salary_max": b if b is not None else a, "salary_currency": cur, "salary_text": raw}


def format_salary(lo, hi, cur: str, raw: str = "") -> str:
    if raw:
        return raw
    if lo is None or lo != lo:  # NaN
        return ""
    sym = {"USD": "$", "GBP": "£", "EUR": "€"}.get(cur, (cur + " ") if cur else "")
    if hi and hi != lo:
        return f"{sym}{lo:,.0f}–{sym}{hi:,.0f}"
    return f"{sym}{lo:,.0f}"


# ---------------------------------------------------------------------------
# Materials, interview venues, requirement sentences, closure language
# ---------------------------------------------------------------------------

MATERIALS = {
    "Cover letter": r"cover letter|letter of (application|interest)|application letter|求职信|申请信",
    "CV": r"\bcv\b|curriculum vita|resume|résumé|简历",
    "Job market paper": r"job[- ]market paper|\bjmp\b",
    "Research papers": r"(research|working) papers?|writing samples?|samples? of (research|scholarship|written work)|"
                       r"(publications|papers) (and|or) working papers|research samples?|代表作|代表性论文|工作论文",
    "Research statement": r"research (statement|agenda|plan|interests? statement)|statement of research|研究计划|研究陈述",
    "Teaching statement": r"teaching (statement|philosophy|portfolio)|statement of teaching|教学陈述|教学计划",
    "Teaching evaluations": r"teaching evaluations?|course evaluations|student evaluations",
    "Diversity statement": r"diversity (statement|and inclusion statement)|statement (on|of) (diversity|contributions to diversity)|dei statement|inclusive excellence statement",
    "Reference letters": r"letters? of (recommendation|reference)|reference letters?|recommendation letters?|"
                         r"(three|3|two|2|four|4) (letters|references|referees)|names? (and contact information )?of (three|3|referees|references)|推荐信",
    "Transcripts": r"transcripts?",
}
_MATERIAL_RES = {k: re.compile(v, re.I) for k, v in MATERIALS.items()}

VENUES = {
    "AFA/ASSA": r"\bassa\b|allied social science|american finance association (annual )?meeting|\bafa (annual )?meeting|afa\s*/\s*assa|afa meetings?",
    "FMA": r"\bfma\b|financial management association",
    "AAA": r"\baaa (annual )?meeting|american accounting association|rookie camp",
    "AMA": r"\bama\b.{0,30}(conference|meeting)|american marketing association|ama[- ]sheth|summer academic conference|winter academic conference",
    "AOM": r"academy of management (annual )?meeting|\baom\b",
    "INFORMS": r"\binforms\b",
    "ICIS": r"\bicis\b",
    "EFA/Europe": r"european finance association|\befa\b|\beea\b|\beea-esem\b",
    "Virtual": r"virtual(ly)? interview|zoom|video (conference|interview)|online interview|remote interview",
}
_VENUE_RES = {k: re.compile(v, re.I) for k, v in VENUES.items()}


def detect_materials(text: str) -> list[str]:
    return [k for k, r in _MATERIAL_RES.items() if r.search(text or "")]


def detect_interview_venues(text: str) -> list[str]:
    t = text or ""
    out = []
    for k, r in _VENUE_RES.items():
        for m in r.finditer(t):
            ctx = t[max(0, m.start() - 200): m.end() + 200].lower()
            if re.search(r"interview|meet|conference|meeting|attend", ctx):
                out.append(k)
                break
    return out


_REQ_RE = re.compile(
    r"(ph\.?\s?d|doctora|qualif|require|must (have|hold|possess)|should (have|hold|possess)|expected to|"
    r"candidates? (will|should|must)|successful candidate|record of|potential for|demonstrat|abd|"
    r"teach(ing)? (load|responsibilit|courses?)|research (excellence|productivity|agenda)|publish|要求|具有|具备|博士|条件)",
    re.I,
)


def requirement_highlights(text: str, max_chars: int = 700) -> str:
    """Pick the sentences that state qualifications / expectations."""
    t = re.sub(r"\s+", " ", text or "")
    sentences = re.split(r"(?<=[.!?;])\s+(?=[A-Z•\-*])|(?<=[。；])", t)
    picked: list[str] = []
    total = 0
    for s in sentences:
        s = s.strip(" •-*")
        if 25 <= len(s) <= 400 and _REQ_RE.search(s):
            if total + len(s) > max_chars:
                break
            picked.append(s)
            total += len(s)
    return " ".join(picked)


_CLOSED_RE = re.compile(
    r"(this|the) (job|position|vacancy|posting|listing|advert(isement)?) (has )?(expired|closed|been filled|is (now )?(closed|filled|no longer))|"
    r"no longer (accepting|available|active|open)|position (has been )?filled|job (is )?(no longer|not) available|"
    r"this job has expired|listing (is )?(closed|expired)|applications? (are|is) (now )?closed",
    re.I,
)


def looks_closed(text: str) -> bool:
    """True when a page says the posting itself is expired/filled.

    "Applications will be reviewed until the position is filled" is the opposite
    signal, so matches introduced by until/unless/once/when are ignored.
    """
    t = text or ""
    for m in _CLOSED_RE.finditer(t):
        before = t[max(0, m.start() - 40):m.start()].lower()
        if not re.search(r"\b(until|unless|once|when|after|before|if|till)\b[^.]*$", before):
            return True
    return False


# ---------------------------------------------------------------------------
# Location → country / region
# ---------------------------------------------------------------------------

US_STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado",
    "CT": "Connecticut", "DE": "Delaware", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana",
    "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York", "NC": "North Carolina",
    "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
    "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas",
    "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia", "PR": "Puerto Rico",
}
CA_PROVINCES = ["Ontario", "Quebec", "Québec", "British Columbia", "Alberta", "Manitoba", "Saskatchewan",
                "Nova Scotia", "New Brunswick", "Newfoundland", "Prince Edward Island"]

COUNTRY_REGION = {
    "United States": "United States", "Canada": "Canada",
    "United Kingdom": "UK & Ireland", "Ireland": "UK & Ireland",
    "China": "Greater China", "Hong Kong": "Greater China", "Macau": "Greater China", "Macao": "Greater China",
    "Taiwan": "Greater China",
    "Singapore": "Asia-Pacific", "Japan": "Asia-Pacific", "South Korea": "Asia-Pacific", "Australia": "Asia-Pacific",
    "New Zealand": "Asia-Pacific", "India": "Asia-Pacific", "Malaysia": "Asia-Pacific", "Thailand": "Asia-Pacific",
    "Indonesia": "Asia-Pacific", "Vietnam": "Asia-Pacific", "Philippines": "Asia-Pacific", "Pakistan": "Asia-Pacific",
    "Kazakhstan": "Asia-Pacific", "Uzbekistan": "Asia-Pacific", "Bangladesh": "Asia-Pacific",
    "Sri Lanka": "Asia-Pacific", "Mongolia": "Asia-Pacific", "Macao": "Greater China",
    "Germany": "Europe", "France": "Europe", "Netherlands": "Europe", "Switzerland": "Europe", "Italy": "Europe",
    "Spain": "Europe", "Portugal": "Europe", "Belgium": "Europe", "Austria": "Europe", "Sweden": "Europe",
    "Norway": "Europe", "Denmark": "Europe", "Finland": "Europe", "Iceland": "Europe", "Luxembourg": "Europe",
    "Poland": "Europe", "Czech Republic": "Europe", "Hungary": "Europe", "Greece": "Europe", "Cyprus": "Europe",
    "Estonia": "Europe", "Latvia": "Europe", "Lithuania": "Europe", "Slovenia": "Europe", "Croatia": "Europe",
    "Romania": "Europe", "Bulgaria": "Europe", "Slovakia": "Europe", "Monaco": "Europe", "Liechtenstein": "Europe",
    "Malta": "Europe", "Serbia": "Europe", "Ukraine": "Europe", "Russia": "Europe", "Turkey": "Middle East & Africa",
    "Israel": "Middle East & Africa", "United Arab Emirates": "Middle East & Africa", "Qatar": "Middle East & Africa",
    "Saudi Arabia": "Middle East & Africa", "Kuwait": "Middle East & Africa", "Bahrain": "Middle East & Africa",
    "Oman": "Middle East & Africa", "Lebanon": "Middle East & Africa", "Egypt": "Middle East & Africa",
    "South Africa": "Middle East & Africa", "Nigeria": "Middle East & Africa", "Kenya": "Middle East & Africa",
    "Morocco": "Middle East & Africa", "Ghana": "Middle East & Africa",
    "Mexico": "Latin America", "Brazil": "Latin America", "Chile": "Latin America", "Colombia": "Latin America",
    "Peru": "Latin America", "Argentina": "Latin America", "Uruguay": "Latin America", "Costa Rica": "Latin America",
    "Ecuador": "Latin America",
}
_COUNTRY_ALIASES = {
    "usa": "United States", "u.s.a.": "United States", "u.s.": "United States", "us": "United States",
    "united states of america": "United States", "america": "United States",
    "uk": "United Kingdom", "u.k.": "United Kingdom", "england": "United Kingdom", "scotland": "United Kingdom",
    "wales": "United Kingdom", "northern ireland": "United Kingdom", "great britain": "United Kingdom", "gb": "United Kingdom",
    "korea": "South Korea", "republic of korea": "South Korea", "korea, republic of": "South Korea",
    "prc": "China", "mainland china": "China", "people's republic of china": "China", "p.r. china": "China",
    "hong kong sar": "Hong Kong", "hong kong sar, china": "Hong Kong", "macao sar": "Macau",
    "uae": "United Arab Emirates", "the netherlands": "Netherlands", "holland": "Netherlands",
    "czechia": "Czech Republic", "türkiye": "Turkey", "turkiye": "Turkey",
    "de": "Germany", "fr": "France", "nl": "Netherlands", "ch": "Switzerland", "it": "Italy", "es": "Spain",
    "ca": "Canada", "au": "Australia", "cn": "China", "hk": "Hong Kong", "sg": "Singapore", "jp": "Japan",
    "kr": "South Korea", "ie": "Ireland", "se": "Sweden", "dk": "Denmark", "no": "Norway", "fi": "Finland",
    "be": "Belgium", "at": "Austria", "pt": "Portugal", "nz": "New Zealand", "in": "India", "il": "Israel",
    "ae": "United Arab Emirates", "qa": "Qatar", "tw": "Taiwan", "mo": "Macau", "br": "Brazil", "mx": "Mexico",
    "cl": "Chile",
    # ISO 3166 alpha-2 codes used by job boards
    "us": "United States", "gb": "United Kingdom", "eg": "Egypt", "my": "Malaysia", "lb": "Lebanon", "tr": "Turkey",
    "sa": "Saudi Arabia", "uz": "Uzbekistan", "gr": "Greece", "kz": "Kazakhstan", "kw": "Kuwait", "bh": "Bahrain",
    "om": "Oman", "pk": "Pakistan", "th": "Thailand", "vn": "Vietnam", "id": "Indonesia", "ph": "Philippines",
    "za": "South Africa", "ng": "Nigeria", "ke": "Kenya", "ma": "Morocco", "gh": "Ghana", "co": "Colombia",
    "pe": "Peru", "ar": "Argentina", "uy": "Uruguay", "cr": "Costa Rica", "ec": "Ecuador", "pl": "Poland",
    "cz": "Czech Republic", "hu": "Hungary", "ro": "Romania", "bg": "Bulgaria", "sk": "Slovakia", "si": "Slovenia",
    "hr": "Croatia", "rs": "Serbia", "ua": "Ukraine", "ru": "Russia", "ee": "Estonia", "lv": "Latvia",
    "lt": "Lithuania", "lu": "Luxembourg", "is": "Iceland", "mt": "Malta", "cy": "Cyprus", "mc": "Monaco",
    "li": "Liechtenstein", "bd": "Bangladesh", "lk": "Sri Lanka", "mn": "Mongolia",
}
_CHINA_CITIES = re.compile(r"\b(beijing|shanghai|shenzhen|guangzhou|hangzhou|nanjing|wuhan|chengdu|xiamen|tianjin|"
                           r"xi'?an|suzhou|ningbo|dalian|jinan|qingdao|changsha|hefei|chongqing|zhuhai|kunshan)\b", re.I)


_CHINA_CITIES_ZH = re.compile(r"北京|上海|广州|深圳|杭州|南京|武汉|成都|西安|天津|厦门|重庆|长沙|合肥|济南|青岛|大连|苏州|"
                              r"海口|海南|珠海|昆山|宁波|沈阳|哈尔滨|长春|兰州|昆明|南昌|福州|郑州|太原|石家庄|中国|清华|北大|复旦|"
                              r"交大|浙大|人大|中山大学|南开|武大|厦大|财经大学")


def _norm_country(c: str) -> str:
    c = (c or "").strip().strip(".")
    if not c:
        return ""
    low = c.lower()
    if low in _COUNTRY_ALIASES:
        return _COUNTRY_ALIASES[low]
    for name in COUNTRY_REGION:
        if low == name.lower():
            return name
    return c


def detect_country(location: str = "", country: str = "", text: str = "") -> str:
    c = _norm_country(country)
    if c:
        return c
    loc = location or ""
    for name in sorted(COUNTRY_REGION, key=len, reverse=True):
        if re.search(rf"\b{re.escape(name)}\b", loc, re.I):
            return name
    for alias, name in _COUNTRY_ALIASES.items():
        if len(alias) > 2 and re.search(rf"(^|[\s,(]){re.escape(alias)}($|[\s,)])", loc, re.I):
            return name
    if re.search(r",\s*(" + "|".join(US_STATES) + r")\b(\s+\d{5})?\s*$", loc) or any(
            re.search(rf"\b{s}\b", loc) for s in US_STATES.values()):
        return "United States"
    if any(p.lower() in loc.lower() for p in CA_PROVINCES):
        return "Canada"
    if _CHINA_CITIES.search(loc) or _CHINA_CITIES_ZH.search(loc):
        return "China"
    for zh_name, name in (("香港", "Hong Kong"), ("澳门", "Macau"), ("台湾", "Taiwan"), ("台北", "Taiwan")):
        if zh_name in loc:
            return name
    probe = (text or "")[:800]
    for zh_name, name in (("香港", "Hong Kong"), ("澳门", "Macau")):
        if zh_name in probe[:200]:
            return name
    if _CHINA_CITIES.search(probe) or _CHINA_CITIES_ZH.search(probe):
        return "China"
    for name in ("Hong Kong", "Singapore", "United Kingdom", "Canada", "Australia"):
        if re.search(rf"\b{name}\b", probe):
            return name
    return ""


def region_for(country: str) -> str:
    return COUNTRY_REGION.get(country, "Unknown") if country else "Unknown"


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------

def normalize_institution(name: str) -> str:
    n = (name or "").lower()
    n = re.split(r"\s+[-–|]\s+|,\s+(?=(school|college|department|faculty)\b)", n)[0]
    n = re.sub(r"^the\s+", "", n)
    n = re.sub(r"[^a-z0-9 ]+", " ", n)
    n = re.sub(r"\b(the|of|at|and|in)\b", " ", n)
    return re.sub(r"\s+", " ", n).strip()
