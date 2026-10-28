"""Import postings from a job-board page you saved in your browser.

For boards the scraper cannot read (FMA needs a member login; AMA, AOM, INFORMS,
AIS and jobs.ac.uk answer automated requests with a bot check): log in as usual,
open the job list, press Ctrl/Cmd+S, and upload the saved .html file in the app.
Nothing is sent anywhere and no password is involved.
"""
from __future__ import annotations

import difflib
import re
from datetime import date
from urllib.parse import urljoin

from .classify import _field_hits, is_faculty_position, normalize_institution
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
        if not looks_like_job or title.lower() in seen:
            continue
        seen.add(title.lower())
        ctx = _block_text(a)
        inst = _institution_from_context(ctx.replace("\n", "  "), title) or institution_from_text(ctx)
        jobs.append(RawJob(source=f"{board} (saved page)", source_id=stable_id(f"{title.lower()}|{inst.lower()}"),
                           url=href, title=title, institution=inst, description=ctx, posted_date=today.isoformat(),
                           categories=f"imported from a saved {board} page",
                           default_field=_BOARD_FIELD.get(board.upper(), "")))
    return jobs


def find_existing(title: str, institution: str, rows) -> str:
    """job_id of a posting already tracked (any board) that is the same position, else ''.

    rows: iterable of (job_id, title, institution).
    """
    inst = normalize_institution(institution)
    if not inst:
        return ""
    for jid, t, i in rows:
        other = normalize_institution(i)
        if not other or not (inst == other or inst in other or other in inst):
            continue
        if difflib.SequenceMatcher(None, title.lower(), (t or "").lower()).ratio() >= 0.6:
            return jid
    return ""
