"""Watch schools' standing recruitment pages.

Many schools (especially in China) keep one "Faculty positions" page that is
rewritten each hiring season instead of posting separate ads. Each configured
page is tracked as one posting; when its text changes the posting is marked
"updated" in the app.
"""
from __future__ import annotations

import time

from ..extract import extract_posting
from ..http import Fetcher, FetchError
from .base import RawJob, SourceResult, stable_id


class PageWatchSource:
    def __init__(self, cfg: dict, fetcher: Fetcher, settings: dict | None = None):
        self.cfg = cfg
        self.name = cfg["name"]
        self.fetcher = fetcher

    def run(self, known_ids: set[str]) -> SourceResult:
        t0 = time.monotonic()
        result = SourceResult(name=self.name)
        failures = 0
        for page in self.cfg.get("pages") or []:
            url = page["url"]
            try:
                r = self.fetcher.get(url)
                if r.status_code >= 400:
                    raise FetchError(url, f"HTTP {r.status_code}", r.status_code)
            except FetchError as exc:
                failures += 1
                result.notes.append(f"{url}: {exc.reason}")
                continue
            result.pages += 1
            d = extract_posting(r.content, r.url)
            # Always a full record (never a stub) so changes to the page text are picked up.
            result.jobs.append(RawJob(
                source=self.name, source_id=stable_id(url), url=url,
                title=page.get("title") or d["title"], institution=page.get("institution") or d["institution"],
                department=page.get("department", ""), location=page.get("location") or d["location"],
                country=page.get("country", ""), description=d["description"], deadline_raw=d["deadline_raw"],
                default_field=page.get("field", ""), field_override=page.get("field", ""),
                categories="School recruitment page",
            ))
        pages = len(self.cfg.get("pages") or [])
        result.ok = failures < pages or pages == 0
        if not result.ok:
            result.error = "no recruitment page could be loaded"
        # A page that fails to load is not treated as removed.
        result.complete = failures == 0 and pages > 0
        result.seconds = round(time.monotonic() - t0, 1)
        return result
