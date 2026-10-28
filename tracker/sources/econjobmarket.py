"""EconJobMarket public ad feed (JSON).

Endpoint: https://backend.econjobmarket.org/data/zz_public/json/Ads returns
every open ad as a list of objects with keys adtitle, adtext (HTML), name
(institution), department, startdate (posted), enddate, deadline_date,
locations [{city, state, country_code}], position_types [{name}],
categories [{name}] and url (…/positions/<id>).
"""
from __future__ import annotations

import json
import re
import time

from ..classify import business_relevance, is_faculty_position
from ..extract import html_to_text
from ..http import Fetcher, FetchError
from .base import RawJob, SourceResult

DEFAULT_URL = "https://backend.econjobmarket.org/data/zz_public/json/Ads"


def _names(v) -> str:
    if isinstance(v, list):
        return "; ".join(x for x in (_names(i) for i in v) if x)
    if isinstance(v, dict):
        return str(v.get("name") or "")
    return str(v or "")


class EconJobMarketSource:
    def __init__(self, cfg: dict, fetcher: Fetcher, settings: dict | None = None):
        self.cfg = cfg
        self.name = cfg["name"]
        self.fetcher = fetcher
        self.url = cfg.get("api_url", DEFAULT_URL)

    def run(self, known_ids: set[str]) -> SourceResult:
        t0 = time.monotonic()
        result = SourceResult(name=self.name)
        try:
            r = self.fetcher.get(self.url, headers={"Accept": "application/json"})
            if r.status_code >= 400:
                raise FetchError(self.url, f"HTTP {r.status_code}", r.status_code)
            ads = json.loads(r.content)
        except (FetchError, ValueError) as exc:
            result.ok = False
            result.error = getattr(exc, "reason", None) or f"bad JSON: {exc}"[:200]
            return result
        if isinstance(ads, dict):
            ads = ads.get("ads") or ads.get("data") or []
        ads = [a for a in ads if isinstance(a, dict)]
        result.pages = 1
        if not ads:
            result.ok = False
            result.error = "feed returned no ads"
            return result
        for ad in ads:
            url = str(ad.get("url") or "")
            m = re.search(r"/positions/(\d+)", url)
            ad_id = m.group(1) if m else str(ad.get("id") or "")
            if not ad_id:
                continue
            loc = (ad.get("locations") or [{}])[0] or {}
            title = str(ad.get("adtitle") or "").strip()
            text = html_to_text(str(ad.get("adtext") or ""))
            job = RawJob(
                source=self.name, source_id=ad_id, url=url or f"https://econjobmarket.org/positions/{ad_id}",
                title=title, institution=str(ad.get("name") or "").strip(),
                department=str(ad.get("department") or "").strip(),
                location=", ".join(str(x) for x in (loc.get("city"), loc.get("state")) if x),
                country=str(loc.get("country_code") or ""),
                categories="; ".join(x for x in (_names(ad.get("position_types")), _names(ad.get("categories"))) if x),
                description=text,
                posted_date=str(ad.get("startdate") or "")[:10],
                listing_expires=str(ad.get("enddate") or "")[:10],
                deadline_raw=str(ad.get("deadline_date") or "")[:10],
                default_field=self.cfg.get("default_field", ""),
            )
            if job.job_id in known_ids:
                job.stub = True
                result.jobs.append(job)
                continue
            # EJM category lists describe research fields ("International Finance/Macro"), not the
            # hiring unit, so only the title, employer, department and ad text decide relevance.
            if not is_faculty_position(title, _names(ad.get("position_types"))) or \
                    not business_relevance(title, job.institution, job.department, "", text):
                result.skipped_filtered += 1
                continue
            # Many EJM ads put the real position title in the first heading of the ad text.
            heading = re.match(r"\s*([^\n]{8,140})\n", text)
            if heading and re.search(r"professor|lecturer|faculty|postdoc|fellow", heading.group(1), re.I) \
                    and not re.search(r"professor|lecturer|postdoc|fellow", title, re.I):
                job.title = f"{heading.group(1).strip()} ({title})"
            result.jobs.append(job)
        result.complete = True  # the feed is the complete set of open ads
        result.seconds = round(time.monotonic() - t0, 1)
        return result
