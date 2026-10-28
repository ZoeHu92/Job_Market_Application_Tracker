"""AEA Job Openings for Economists (JOE) via its official XML export.

The listings page links to "Output current result set to: XML"
(/joe/resultset_output.php?mode=full_xml&q=...), which returns every current
listing with full text, deadline, salary, JEL codes and location in one
request. Only academic sections at business schools (or with a business field
in the title / department) are kept.
"""
from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from html import unescape
from urllib.parse import urljoin

from ..classify import business_relevance, is_faculty_position
from ..http import Fetcher, FetchError
from .base import RawJob, SourceResult

LISTINGS_URL = "https://www.aeaweb.org/joe/listings"


def _text(el, tag: str) -> str:
    v = el.findtext(tag) or ""
    return unescape(unescape(v)).strip()


class JoeSource:
    def __init__(self, cfg: dict, fetcher: Fetcher, settings: dict | None = None):
        self.cfg = cfg
        self.name = cfg["name"]
        self.fetcher = fetcher
        self.listings_url = cfg.get("listings_url", LISTINGS_URL)

    def export_url(self) -> str:
        r = self.fetcher.get(self.listings_url)
        if r.status_code >= 400:
            raise FetchError(self.listings_url, f"HTTP {r.status_code}", r.status_code)
        m = re.search(r'href="([^"]*resultset_output\.php\?mode=full_xml[^"]*)"', r.text)
        if not m:
            raise FetchError(self.listings_url, "XML export link not found on the listings page")
        return urljoin(self.listings_url, unescape(m.group(1)))

    def run(self, known_ids: set[str]) -> SourceResult:
        t0 = time.monotonic()
        result = SourceResult(name=self.name)
        try:
            url = self.export_url()
            r = self.fetcher.get(url)
            if r.status_code >= 400:
                raise FetchError(url, f"HTTP {r.status_code}", r.status_code)
            root = ET.fromstring(r.content)
        except (FetchError, ET.ParseError) as exc:
            result.ok = False
            result.error = getattr(exc, "reason", None) or f"bad XML: {exc}"[:200]
            return result
        result.pages = 2
        n = 0
        for year in root.iter("year"):
            for issue in year.iter("issue"):
                prefix = f"{year.get('joe_year_ID')}-{int(issue.get('joe_issue_ID') or 0):02d}"
                for pos in issue.iter("position"):
                    n += 1
                    self._one(pos, prefix, known_ids, result)
        result.notes.append(f"{n} listings in the XML export")
        result.complete = n > 0
        result.ok = n > 0
        if not n:
            result.error = "XML export contained no listings"
        result.seconds = round(time.monotonic() - t0, 1)
        return result

    def _one(self, pos, prefix: str, known_ids: set[str], result: SourceResult) -> None:
        jp_id = pos.get("jp_id") or ""
        if not jp_id:
            return
        section = _text(pos, "jp_section")
        title = _text(pos, "jp_title")
        inst = _text(pos, "jp_institution")
        dept = " - ".join(x for x in (_text(pos, "jp_division"), _text(pos, "jp_department")) if x)
        url = f"https://www.aeaweb.org/joe/listing.php?JOE_ID={prefix}_{jp_id}"
        job = RawJob(source=self.name, source_id=jp_id, url=url, title=title, institution=inst, department=dept)
        if job.job_id in known_ids:
            job.stub = True
            result.jobs.append(job)
            return
        status = _text(pos, "jp_status")
        if "nonacademic" in section.lower() or re.search(r"closed|filled|withdrawn|cancel", status, re.I):
            result.skipped_filtered += 1
            return
        text = _text(pos, "jp_full_text")
        if not is_faculty_position(title, text[:600]) and "academic" not in section.lower():
            result.skipped_filtered += 1
            return
        if not business_relevance(title, inst, dept, "", text):
            result.skipped_filtered += 1
            return
        loc = pos.find("locations/location")
        jels = [f"{c.findtext('jc_code', '').strip()} {c.findtext('jc_description', '').strip()}".strip()
                for c in pos.iter("jel_class")]
        keywords = "; ".join(k.strip() for k in _text(pos, "jp_keywords").splitlines() if k.strip())
        job.location = ", ".join(x for x in ((loc.findtext("city") or "").strip().title() if loc is not None else "",
                                             (loc.findtext("state") or "").strip() if loc is not None else "") if x)
        job.country = (loc.findtext("country") or "").strip().title() if loc is not None else ""
        job.categories = "; ".join(x for x in (section, keywords, "JEL " + ", ".join(jels) if jels else "") if x)
        job.description = text
        job.deadline_raw = (pos.findtext("jp_application_deadline") or "")[:10]
        salary = _text(pos, "jp_salary_range")
        if salary and re.search(r"\d", salary):
            job.salary_label = salary
        result.jobs.append(job)
