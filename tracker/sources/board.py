"""Generic job-board adapter driven by config/sources.yaml.

Collects job links from RSS/Atom feeds and/or paginated listing pages, then
fetches detail pages only for postings not seen before. Works for Madgex
boards (AFA, Chronicle, Inside Higher Ed), YM Careers boards (AAA, AMA, AOM,
INFORMS, AIS), jobs.ac.uk, AEA JOE and similar sites without per-site code;
per-site differences live in the YAML entry.
"""
from __future__ import annotations

import logging
import re
import time
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from ..classify import BUSINESS_FIELDS, _field_hits, is_business_school, is_faculty_position
from ..extract import clean_text, extract_posting, html_to_text, soupify
from ..http import Fetcher, FetchError
from .base import RawJob, SourceResult, stable_id

log = logging.getLogger(__name__)

_NEXT_TEXT = re.compile(r"^\s*(next|next page|next ›|next »|›|»|>|>>|more results|older)\s*$", re.I)
_BLOCK_HINT = re.compile(r"job|result|listing|lister|item|posting|vacanc|position|row|card", re.I)


def _set_param(url: str, key: str, value) -> str:
    p = urlparse(url)
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if k != key]
    q.append((key, str(value)))
    return urlunparse(p._replace(query=urlencode(q)))


def looks_business(title: str, context: str = "") -> bool:
    """Business-school relevance from a title plus nearby listing text."""
    hits = _field_hits(f"{title} {context[:700]}")
    if any(f in hits for f in BUSINESS_FIELDS):
        return True
    return is_business_school(title, context[:700])


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

    # -- link collection ---------------------------------------------------

    def _source_id(self, url: str) -> str:
        if self.link_re:
            m = self.link_re.search(url)
            if m and m.groups() and m.group(1):
                return m.group(1)
        return stable_id(url.split("#")[0].rstrip("/"))

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
            title = clean_text(a.get_text(" ")) or clean_text(a.get("title") or "")
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
        out = []
        for e in parsed.entries:
            link = e.get("link") or ""
            if not link or (self.link_re and not self.link_re.search(link)):
                continue  # not a job posting (site news feed, etc.)
            summary = html_to_text(e.get("summary") or e.get("description") or "")
            published = ""
            if e.get("published_parsed"):
                published = time.strftime("%Y-%m-%d", e.published_parsed)
            out.append({"source_id": self._source_id(link), "url": link, "title": clean_text(e.get("title") or ""),
                        "context": summary[:1500], "posted_date": published, "summary": summary})
        return out

    def _discover_feeds(self, html: bytes | str, base_url: str) -> list[str]:
        soup = soupify(html)
        feeds = []
        for link in soup.find_all("link", attrs={"type": re.compile(r"(rss|atom)\+xml", re.I)}):
            if link.get("href"):
                feeds.append(urljoin(base_url, link["href"]))
        return feeds

    def _feeds_from_index(self, index_url: str, pattern: str) -> list[str]:
        r = self.fetcher.get(index_url)
        soup = soupify(r.content)
        rx = re.compile(pattern, re.I) if pattern else None
        feeds = []
        for a in soup.find_all("a", href=True):
            href = urljoin(index_url, a["href"])
            if not re.search(r"rss|feed|\.xml|atom", href, re.I) or href.rstrip("/") == index_url.rstrip("/"):
                continue
            label = clean_text(a.get_text(" ")) + " " + href
            if rx is None or rx.search(label):
                feeds.append(href)
        return list(dict.fromkeys(feeds))

    # -- main ----------------------------------------------------------------

    def collect(self, result: SourceResult) -> list[dict]:
        cfg = self.cfg
        candidates: dict[str, dict] = {}
        errors: list[str] = []
        truncated = False

        feed_urls = list(cfg.get("feeds") or [])
        indexes = cfg.get("feed_index") or []
        for index in [indexes] if isinstance(indexes, str) else indexes:
            try:
                found = self._feeds_from_index(index, cfg.get("feed_index_filter", ""))
                result.notes.append(f"{len(found)} feeds found on {index}")
                feed_urls += [f for f in found if f not in feed_urls]
            except FetchError as exc:
                errors.append(f"feed index {index}: {exc.reason}")

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
                links = self._links_from_page(r.content, r.url)
                new = [c for c in links if c["source_id"] not in candidates]
                for c in links:
                    candidates.setdefault(c["source_id"], c)
                if page_no == 1 and cfg.get("discover_feeds"):
                    feed_urls += [f for f in self._discover_feeds(r.content, r.url) if f not in feed_urls]
                nxt = self._next_page(r.content, r.url)
                if not nxt and cfg.get("page_param") and new:
                    nxt = _set_param(start, cfg["page_param"], page_no + int(cfg.get("page_step", 1)))
                if not new and page_no > 1:
                    break
                url, page_no = nxt, page_no + 1

        for feed in dict.fromkeys(feed_urls):
            try:
                entries = self._feed_entries(feed)
                result.notes.append(f"feed {feed}: {len(entries)} items")
                for e in entries:
                    prev = candidates.get(e["source_id"])
                    if prev is None:
                        candidates[e["source_id"]] = e
                    else:
                        for k in ("posted_date", "summary"):
                            prev.setdefault(k, e.get(k, ""))
            except FetchError as exc:
                errors.append(f"feed {feed}: {exc.reason}")

        if errors:
            result.notes.extend(errors)
        if not candidates:
            result.ok = False
            result.error = errors[0] if errors else "no job links found (page layout may have changed)"
        # Missing jobs are only closed when every listing page and feed was read.
        result.complete = bool(candidates) and not errors and not truncated
        return list(candidates.values())

    def keep(self, cand: dict) -> bool:
        """Cheap pre-filter on listing text, before any detail page is fetched."""
        if self.filter == "none":
            return True
        title, ctx = cand.get("title", ""), cand.get("context", "")
        if not is_faculty_position(title, ctx):
            return False
        if self.filter != "business" or len(ctx) < 40:
            # Without listing context the business check waits for the detail page.
            return True
        return looks_business(title, ctx)

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
            if result.details_fetched >= self.max_new:
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
                     posted_date=cand.get("posted_date", ""), default_field=self.cfg.get("default_field", ""))
        if self.cfg.get("fetch_details", True):
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
                job.title = d["title"] if len(d["title"] or "") >= 6 else job.title
                job.institution = d["institution"]
                job.department = d["department"]
                job.location = d["location"]
                job.country = d["country"]
                if len(d["description"]) > len(job.description):
                    job.description = d["description"]
                job.posted_date = d["posted_date"] or job.posted_date
                job.listing_expires = d["listing_expires"]
                job.deadline_raw = d["deadline_raw"]
                job.salary_label = d["salary_label"]
                job.categories = d["categories"]
                job.start_date_raw = d["start_date_raw"]
                for k in ("salary_min", "salary_max", "salary_currency", "salary_text"):
                    if d.get(k):
                        setattr(job, k, d[k])
            except FetchError as exc:
                job.detail_error = exc.reason
                result.notes.append(f"detail {cand['url']}: {exc.reason}")
        if not job.institution:
            job.institution = _institution_from_context(cand.get("context", ""), job.title)
        # A board-level filter may need the full text (e.g. JOE titles are just "Assistant Professor").
        if self.filter == "business" and not looks_business(job.title, " ".join(
                [job.institution, job.department, job.categories, job.description[:1500]])):
            result.skipped_filtered += 1
            if not job.detail_error:
                result.skipped_ids.append(job.job_id)
            return None
        return job


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
