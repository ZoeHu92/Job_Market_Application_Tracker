"""Import postings from a job-board page you saved in your browser.

For boards the scraper cannot read (FMA needs a member login; AMA, AOM, INFORMS,
AIS and jobs.ac.uk answer automated requests with a bot check): log in as usual,
open the job list, press Ctrl/Cmd+S, and upload the saved .html file in the app.
Nothing is sent anywhere and no password is involved.
"""
from __future__ import annotations

import difflib
import re
from datetime import date, timedelta
from urllib.parse import urljoin

from .classify import _field_hits, is_faculty_position, normalize_institution, parse_date_string
from .extract import clean_text, soupify
from .sources.base import RawJob, stable_id
from .sources.board import _institution_from_context, institution_from_text

_NAV = re.compile(
    r"^(home|jobs?|search|login|log in|sign in|sign out|register|my account|help|contact( us)?|about( us)?|"
    r"post a job|employers?|job seekers?|resources|faq|privacy|terms.*|next|previous|back|more|view all.*|"
    r"apply( now)?|save( job)?|share|print|email( this)?( job)?)$", re.I)
_JOB_HREF = re.compile(r"/jobs?/|job_?id|jobcode|listing|position|posting|vacanc|opening|details|ShowJob", re.I)
_BOARD_FIELD = {"FMA": "Finance", "AFA": "Finance", "AAA": "Accounting", "AMA": "Marketing",
                "AOM": "Management & Strategy", "INFORMS": "Operations & Supply Chain", "AIS": "Information Systems"}


# Labelled parts of a job tile (YM Careers boards such as jobs.fma.org mark them with
# aria-label="Hiring Company" / class="job-location" / class="job-posted-date").
_TILE_PARTS = {
    "institution": re.compile(r"company|employer|organi[sz]ation|institution|hiring", re.I),
    "location": re.compile(r"location|\bcity\b", re.I),
    "posted": re.compile(r"posted|\bdate\b", re.I),
}


def _tile_parts(a) -> dict:
    node = a
    for _ in range(6):
        node = node.parent
        if node is None or node.name in ("body", "html"):
            break
        found: dict[str, str] = {}
        for el in node.find_all(True):
            if el.find("a", href=True) or el.name == "a":
                continue
            label = " ".join([el.get("aria-label") or "", " ".join(el.get("class") or [])])
            for key, rx in _TILE_PARTS.items():
                if key not in found and rx.search(label):
                    txt = clean_text(el.get_text(" "))
                    if 2 <= len(txt) <= 150:
                        found[key] = txt
        if "institution" in found:
            loc = re.sub(r"\((on-site|remote|hybrid)\)|multiple locations", "", found.get("location", ""), flags=re.I)
            found["location"] = "; ".join(dict.fromkeys(x.strip(" ,") for x in loc.splitlines() if x.strip(" ,")))
            return found
    return {}


def _relative_date(text: str, today: date) -> str:
    """'1 day ago', '2 weeks ago', 'Today', or a normal date → ISO date."""
    t = (text or "").lower()
    if not t:
        return ""
    if re.search(r"today|just now|hour|minute|new", t):
        return today.isoformat()
    if "yesterday" in t:
        return (today - timedelta(days=1)).isoformat()
    m = re.search(r"(\d+)\+?\s*(day|week|month)s?", t)
    if m:
        n = int(m.group(1)) * {"day": 1, "week": 7, "month": 30}[m.group(2)]
        return (today - timedelta(days=n)).isoformat()
    d = parse_date_string(text, today)
    return d.isoformat() if d else ""


def _job_key(href: str) -> str:
    """Same posting, same key: the board's numeric id if the URL has one, else the URL without query."""
    m = re.search(r"/(\d{5,})(?:/|$|\?)", href)
    return m.group(1) if m else href.split("#")[0].split("?")[0].rstrip("/")


def _block_text(a) -> str:
    node = a
    for _ in range(5):
        node = node.parent
        if node is None or node.name in ("body", "html"):
            break
        if node.name in ("tr", "li", "article", "div", "td", "p"):
            txt = clean_text(node.get_text("\n"))
            if len(clean_text(a.get_text(" "))) + 15 < len(txt) < 1500:
                return txt
    return ""


def jobs_from_saved_page(html: str, board: str, base_url: str = "", today: date | None = None) -> list[RawJob]:
    """One RawJob per posting link on a saved job-list page."""
    today = today or date.today()
    m = re.search(r'<base[^>]+href="([^"]+)"', html, re.I) or re.search(
        r"<!-- saved from url=\(\d+\)(\S+?) -->", html)
    base_url = base_url or (m.group(1) if m else "")
    jobs, seen = [], set()
    for a in soupify(html).find_all("a", href=True):
        title = clean_text(a.get_text(" "))
        href = urljoin(base_url, a["href"].strip()) if base_url else a["href"].strip()
        if not (6 <= len(title) <= 200) or _NAV.match(title) or href.startswith(("javascript", "mailto", "#")):
            continue
        looks_like_job = is_faculty_position(title) or (bool(_field_hits(title)) and bool(_JOB_HREF.search(href)))
        key = _job_key(href)
        if not looks_like_job or key in seen:
            continue
        seen.add(key)
        ctx = _block_text(a)
        parts = _tile_parts(a)
        inst = parts.get("institution") or _institution_from_context(ctx.replace("\n", "  "), title) \
            or institution_from_text(ctx)
        jobs.append(RawJob(source=f"{board} (saved page)", source_id=stable_id(f"{board}|{key}"),
                           url=href, title=title, institution=inst, location=parts.get("location", ""),
                           description=ctx, posted_date=_relative_date(parts.get("posted", ""), today) or today.isoformat(),
                           categories=f"imported from a saved {board} page",
                           default_field=_BOARD_FIELD.get(board.upper(), "")))
    return jobs


def find_existing(title: str, institution: str, rows, field: str = "") -> str:
    """job_id of a posting already tracked (any board) that is the same position, else ''.

    rows: iterable of (job_id, title, institution) or (job_id, title, institution, field).
    A generic title ("Assistant Professor") at the same school only matches in the same field.
    """
    inst = normalize_institution(institution)
    if not inst:
        return ""
    for row in rows:
        jid, t, i = row[0], row[1], row[2]
        other_field = row[3] if len(row) > 3 else ""
        other = normalize_institution(i)
        if not other or not (inst == other or inst in other or other in inst):
            continue
        if difflib.SequenceMatcher(None, title.lower(), (t or "").lower()).ratio() < 0.6:
            continue
        if field and other_field and field != other_field:
            continue
        return jid
    return ""
