"""Generic job-board adapter driven by config/sources.yaml.

Collects postings from RSS/Atom/RDF feeds (optionally paginated) and/or
paginated listing pages, then fetches detail pages only for postings not seen
before. Works for Madgex boards (AFA, AAA, Chronicle, Inside Higher Ed, Times
Higher Education), HigherEdJobs category feeds, AcademicJobsOnline and
similar sites without per-site code; per-site differences live in the YAML.
"""
from __future__ import annotations

import logging
import re
import time
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from ..classify import _field_hits, business_relevance, is_faculty_position
from ..extract import clean_text, extract_posting, html_to_text, soupify
from ..http import Fetcher, FetchError
from .base import RawJob, SourceResult, stable_id

log = logging.getLogger(__name__)

_NEXT_TEXT = re.compile(r"^\s*(next|next page|next ›|next »|›|»|>|>>|more results|older)\s*$", re.I)
_BLOCK_HINT = re.compile(r"job|result|listing|lister|item|posting|vacanc|position|row|card", re.I)

_OTHER_SUBJECT = re.compile(
    r"econom|polic|psycholog|sociolog|politic|histor|engineer|comput|biolog|chemi|physic|math|nurs|health|educat|"
    r"law\b|english|language|music|art\b|arts\b|design|communication|journalism|social work|criminal|philosoph|"
    r"anthropolog|geograph|environment|agricult|medic|pharm|kinesiolog|theat|film|religio", re.I)

# Fields a candidate can carry from a feed or listing into the RawJob.
_CAND_FIELDS = ("institution", "department", "location", "country", "categories", "deadline_raw", "posted_date",
                "listing_expires", "salary_label", "start_date_raw")


def set_param(url: str, key: str, value) -> str:
    p = urlparse(url)
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if k != key]
    q.append((key, str(value)))
    return urlunparse(p._replace(query=urlencode(q)))


def clean_anchor_title(text: str) -> str:
    """Listing links often wrap date + title + teaser; keep the first real line."""
    for line in clean_text(text).splitlines():
        line = line.strip(" |·-–")
        if len(line) < 4 or re.fullmatch(r"[\d\s./:年月日-]+", line):
            continue
        return line[:200]
    return ""


def parse_madgex_entry(title: str, summary: str) -> dict:
    """Madgex feeds: title 'Employer: Job title'; description lines
    'Salary text:' / 'Employer:' / snippet / location."""
    out: dict = {}
    if ": " in title:
        inst, title = title.split(": ", 1)
        out["institution"] = inst.strip()
    out["title"] = title.strip()
    lines = [ln.strip() for ln in summary.splitlines() if ln.strip()]
    inst = out.get("institution", "")
    if lines and lines[0].endswith(":") and lines[0][:-1].strip() != inst:
        out["salary_label"] = lines[0][:-1].strip()
        lines = lines[1:]
    if lines and lines[0].endswith(":") and len(lines[0]) < 160:
        lines = lines[1:]  # employer line
    if len(lines) >= 2:
        out["location"] = lines[-1]
        out["summary"] = " ".join(lines[:-1])
    elif lines:
        out["summary"] = lines[0]
    return out


def parse_hej_entry(title: str, summary: str) -> dict:
    """HigherEdJobs feeds: description 'Institution (City, ST)'."""
    m = re.match(r"^(.*?)\s*\(([^()]*)\)\s*$", summary.strip())
    if m:
        return {"title": title, "institution": m.group(1).strip(), "location": m.group(2).strip(), "summary": ""}
    return {"title": title, "institution": summary.strip(), "summary": ""}


class BoardSource:
    def __init__(self, cfg: dict, fetcher: Fetcher, settings: dict | None = None):
        self.cfg = cfg
        self.name = cfg["name"]
        self.fetcher = fetcher
        self.settings = settings or {}
        self.link_re = re.compile(cfg["job_link_pattern"], re.I) if cfg.get("job_link_pattern") else None
        self.max_pages = int(cfg.get("max_pages", 10))
        self.max_new = int(cfg.get("max_new_details", self.settings.get("max_new_details_per_source", 300)))
        self.filter = cfg.get("filter", "none")  # none | faculty | business
        self.blocked = 0  # consecutive bot-protection answers on detail pages

    # -- link collection ---------------------------------------------------

    def _source_id(self, url: str) -> str:
        if self.link_re:
            m = self.link_re.search(url)
            if m and m.groups() and m.group(1):
                return m.group(1)
        return stable_id(url.split("#")[0].split("?")[0].rstrip("/"))

    def _context(self, a) -> str:
        node = a
        for _ in range(6):
            node = node.parent
            if node is None or node.name in ("body", "html"):
                break
            ident = " ".join([node.get("id") or "", " ".join(node.get("class") or [])])
            if node.name in ("li", "tr", "article") or _BLOCK_HINT.search(ident):
                txt = clean_text(node.get_text(" "))
                if len(txt) < 1500:
                    return txt
        return ""

    def _links_from_page(self, html: bytes | str, base_url: str) -> list[dict]:
        soup = soupify(html)
        found: dict[str, dict] = {}
        for a in soup.find_all("a", href=True):
            href = urljoin(base_url, a["href"].strip())
            if not self.link_re or not self.link_re.search(href):
                continue
            sid = self._source_id(href)
            title = clean_anchor_title(a.get_text("\n")) or clean_text(a.get("title") or "")
            prev = found.get(sid)
            if prev is None or len(title) > len(prev["title"]):
                found[sid] = {"source_id": sid, "url": href.split("#")[0], "title": title,
                              "context": self._context(a)}
        return list(found.values())

    def _next_page(self, html: bytes | str, base_url: str) -> str:
        soup = soupify(html)
        link = soup.find("link", rel=lambda v: v and "next" in v)
        if link and link.get("href"):
            return urljoin(base_url, link["href"])
        for a in soup.find_all("a", href=True):
            rel = a.get("rel") or []
            if "next" in rel or _NEXT_TEXT.match(a.get_text(" ", strip=True) or "") or re.search(
                    r"\bnext( page)?\b", a.get("aria-label") or "", re.I):
                href = urljoin(base_url, a["href"])
                if href != base_url and not href.startswith("javascript"):
                    return href
        return ""

    def _feed_entries(self, feed_url: str) -> list[dict]:
        import feedparser  # local import keeps app start-up light

        r = self.fetcher.get(feed_url)
        if r.status_code >= 400:
            raise FetchError(feed_url, f"HTTP {r.status_code}", r.status_code)
        parsed = feedparser.parse(r.content)
        if parsed.bozo and not parsed.entries:
            raise FetchError(feed_url, "not a valid RSS/Atom feed")
        style = self.cfg.get("feed_style", "")
        mapping = self.cfg.get("feed_fields") or {}
        out = []
        for e in parsed.entries:
            link = (e.get("link") or "").strip()
            if not link or (self.link_re and not self.link_re.search(link)):
                continue  # not a job posting (site news feed, etc.)
            title = clean_text(e.get("title") or "")
            summary = html_to_text(e.get("summary") or e.get("description") or "")
            cand = {"source_id": self._source_id(link), "url": link, "title": title, "summary": summary,
                    "from_feed": True}
            if style == "madgex":
                cand.update(parse_madgex_entry(title, summary))
            elif style == "higheredjobs":
                cand.update(parse_hej_entry(title, summary))
            for key, feed_key in mapping.items():
                val = e.get(feed_key)
                if val:
                    cand[key] = clean_text(str(val))
            if e.get("published_parsed") and not cand.get("posted_date"):
                cand["posted_date"] = time.strftime("%Y-%m-%d", e.published_parsed)
            cand["context"] = " ".join(x for x in (cand.get("institution", ""), cand.get("department", ""),
                                                   cand.get("summary", "")) if x)[:1500]
            out.append(cand)
        return out

    def _discover_feeds(self, html: bytes | str, base_url: str) -> list[str]:
        soup = soupify(html)
        return [urljoin(base_url, ln["href"]) for ln in
                soup.find_all("link", attrs={"type": re.compile(r"(rss|atom)\+xml", re.I)}) if ln.get("href")]

    def collect(self, result: SourceResult) -> list[dict]:
        cfg = self.cfg
        candidates: dict[str, dict] = {}
        errors: list[str] = []
        truncated = False

        def add(c: dict) -> bool:
            prev = candidates.get(c["source_id"])
            if prev is None:
                candidates[c["source_id"]] = c
                return True
            for k, v in c.items():
                if v and not prev.get(k):
                    prev[k] = v
            return False

        feed_urls = list(cfg.get("feeds") or [])
        for start in cfg.get("start_urls") or []:
            url, page_no, seen_pages = start, 1, set()
            while url and url not in seen_pages:
                if page_no > self.max_pages:
                    truncated = True
                    result.notes.append(f"stopped at max_pages={self.max_pages} for {start}")
                    break
                seen_pages.add(url)
                try:
                    r = self.fetcher.get(url)
                except FetchError as exc:
                    errors.append(f"listing {url}: {exc.reason}")
                    break
                if r.status_code >= 400:
                    errors.append(f"listing {url}: HTTP {r.status_code}")
                    break
                result.pages += 1
                new = [c for c in self._links_from_page(r.content, r.url) if add(c)]
                if page_no == 1 and cfg.get("discover_feeds"):
                    feed_urls += [f for f in self._discover_feeds(r.content, r.url) if f not in feed_urls]
                nxt = self._next_page(r.content, r.url)
                if not nxt and cfg.get("page_param") and new:
                    nxt = set_param(start, cfg["page_param"], page_no + 1)
                if not new and page_no > 1:
                    break
                url, page_no = nxt, page_no + 1

        page_param = cfg.get("feed_page_param")
        feed_max = int(cfg.get("feed_max_pages", 40 if page_param else 1))
        for feed in dict.fromkeys(feed_urls):
            page, url, n_items = 1, feed, 0
            while True:
                try:
                    entries = self._feed_entries(url)
                except FetchError as exc:
                    errors.append(f"feed {url}: {exc.reason}")
                    break
                result.pages += 1
                n_items += len(entries)
                new = [e for e in entries if add(e)]
                if not page_param or not entries or not new:
                    break
                page += 1
                if page > feed_max:
                    truncated = True
                    result.notes.append(f"stopped at feed_max_pages={feed_max} for {feed}")
                    break
                url = set_param(feed, page_param, page)
            result.notes.append(f"feed {feed}: {n_items} items over {page} page(s)")

        if errors:
            result.notes.extend(errors)
        if not candidates:
            result.ok = False
            result.error = errors[0] if errors else "no job links found (page layout may have changed)"
        # Missing jobs are only closed when every listing page and feed was read.
        result.complete = bool(candidates) and not errors and not truncated and not cfg.get("partial_listing")
        return list(candidates.values())

    # -- filtering and details ----------------------------------------------

    def keep(self, cand: dict) -> bool:
        """Cheap pre-filter on listing/feed text, before any detail page is fetched."""
        if self.filter == "none":
            return True
        title, ctx = cand.get("title", ""), cand.get("context", "")
        if not is_faculty_position(title, ctx):
            return False
        if self.filter != "business":
            return True
        if business_relevance(title, cand.get("institution", ""), cand.get("department", ""),
                              cand.get("categories", ""), cand.get("summary") or ctx):
            return True
        # A title naming no subject at all ("Assistant Professor", "Faculty Openings") is decided
        # on the full posting; one naming another subject ("... of Psychology") is dropped here.
        generic = not _field_hits(title) and not _OTHER_SUBJECT.search(title)
        return (generic or len(ctx) < 40) and self.cfg.get("fetch_details", True)

    def run(self, known_ids: set[str]) -> SourceResult:
        t0 = time.monotonic()
        result = SourceResult(name=self.name)
        candidates = self.collect(result)
        deferred = 0
        for cand in candidates:
            jid = f"{self.name}:{cand['source_id']}"
            if jid in known_ids:
                result.jobs.append(RawJob(source=self.name, source_id=cand["source_id"], url=cand["url"],
                                          title=cand.get("title", ""), stub=True))
                continue
            if not self.keep(cand):
                result.skipped_filtered += 1
                continue
            if self.cfg.get("fetch_details", True) and result.details_fetched >= self.max_new:
                deferred += 1  # picked up next run; known jobs above still count as seen
                continue
            job = self._detail(cand, result)
            if job is not None:
                result.jobs.append(job)
        if deferred:
            result.notes.append(f"detail cap {self.max_new} reached; {deferred} new postings left for next run")
            result.complete = False
        result.seconds = round(time.monotonic() - t0, 1)
        return result

    def _detail(self, cand: dict, result: SourceResult) -> RawJob | None:
        job = RawJob(source=self.name, source_id=cand["source_id"], url=cand["url"],
                     title=cand.get("title", ""), description=cand.get("summary") or cand.get("context", ""),
                     default_field=self.cfg.get("default_field", ""),
                     **{k: cand.get(k, "") for k in _CAND_FIELDS})
        if self.cfg.get("fetch_details", True) and self.blocked < 3:
            try:
                r = self.fetcher.get(cand["url"])
                result.details_fetched += 1
                if r.status_code in (404, 410):
                    result.skipped_ids.append(job.job_id)
                    return None
                d = extract_posting(r.content, r.url)
                if d.get("closed_hint") and not d.get("has_jsonld"):
                    result.skipped_ids.append(job.job_id)
                    return None
                # Feed titles are clean; listing link text is often not, so the page title wins there.
                if len(d["title"] or "") >= 6 and (not job.title or not cand.get("from_feed")):
                    job.title = d["title"]
                if len(d["description"]) > len(job.description):
                    job.description = d["description"]
                for k in ("institution", "department", "location", "country", "categories", "posted_date",
                          "listing_expires", "start_date_raw", "salary_label"):
                    if d.get(k):
                        setattr(job, k, d[k])
                if d.get("deadline_raw"):
                    job.deadline_raw = d["deadline_raw"]
                for k in ("salary_min", "salary_max", "salary_currency", "salary_text"):
                    if d.get(k):
                        setattr(job, k, d[k])
                self.blocked = 0
            except FetchError as exc:
                job.detail_error = exc.reason
                result.notes.append(f"detail {cand['url']}: {exc.reason}")
                if "bot protection" in exc.reason:
                    self.blocked += 1
                    if self.blocked == 3:
                        result.notes.append("posting pages are bot-protected: using feed data only from here on")
        if not job.institution:
            job.institution = (self.cfg.get("default_institution") or institution_from_text(job.title)
                               or _institution_from_context(cand.get("context", ""), job.title))
        # Re-check relevance with the full text (e.g. titles that are just "Assistant Professor").
        if self.filter == "business" and not business_relevance(
                job.title, job.institution, job.department, job.categories, job.description):
            result.skipped_filtered += 1
            if not job.detail_error:
                result.skipped_ids.append(job.job_id)
            return None
        return job


_ZH_INST = re.compile(r"[\u4e00-\u9fa5]{2,10}大学(?:[\u4e00-\u9fa5]{2,12}?(?:学院|研究院))?|[\u4e00-\u9fa5]{2,12}(?:商学院|管理学院)")


def institution_from_text(text: str) -> str:
    """Chinese notices name the school in the title: 西南财经大学经济学院教师招聘公告 → 西南财经大学经济学院."""
    m = _ZH_INST.search(text or "")
    return m.group(0) if m else ""


def _institution_from_context(context: str, title: str) -> str:
    """Listing rows usually read 'Title  Institution  Location ...'; take the line after the title."""
    if not context:
        return ""
    rest = context.replace(title, " ", 1) if title else context
    for piece in re.split(r"\s{2,}|\n| \| | · ", rest):
        piece = piece.strip(" -–,")
        if 4 <= len(piece) <= 120 and re.search(r"universit|college|school|institut|business|academy|polytechnic", piece, re.I):
            return piece
    return ""
