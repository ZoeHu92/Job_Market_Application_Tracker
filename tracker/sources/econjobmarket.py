"""EconJobMarket public ad feed (JSON).

Documented endpoint: https://backend.econjobmarket.org/data/zz_public/json/Ads
returns all open ads as a JSON array. Field names are read defensively because
the schema is only partially documented; the first record's keys are written to
the scrape report so the mapping can be tightened if EJM changes it.
"""
from __future__ import annotations

import json
import time

from ..extract import html_to_text
from ..http import Fetcher, FetchError
from .base import RawJob, SourceResult
from .board import looks_business

DEFAULT_URL = "https://backend.econjobmarket.org/data/zz_public/json/Ads"


def _get(d: dict, *keys: str, default=""):
    """First non-empty value among keys (case-insensitive, also one level of nesting)."""
    if not isinstance(d, dict):
        return default
    lower = {k.lower(): v for k, v in d.items()}
    for key in keys:
        v = lower.get(key.lower())
        if v not in (None, "", [], {}):
            return v
    for v in d.values():
        if isinstance(v, dict):
            inner = _get(v, *keys, default=None)
            if inner not in (None, "", [], {}):
                return inner
    return default


def _names(v) -> str:
    if isinstance(v, list):
        return "; ".join(_names(x) for x in v if x)
    if isinstance(v, dict):
        return str(_get(v, "name", "category", "title", "label", "type", default=""))
    return str(v or "")


def _ads(payload) -> list[dict]:
    if isinstance(payload, list):
        return [a for a in payload if isinstance(a, dict)]
    if isinstance(payload, dict):
        for key in ("ads", "Ads", "data", "results", "positions", "items"):
            if isinstance(payload.get(key), list):
                return [a for a in payload[key] if isinstance(a, dict)]
    return []


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
            ads = _ads(json.loads(r.content))
        except (FetchError, ValueError) as exc:
            result.ok = False
            result.error = getattr(exc, "reason", None) or f"bad JSON: {exc}"[:200]
            return result
        result.pages = 1
        if not ads:
            result.ok = False
            result.error = "feed returned no ads"
            return result
        result.notes.append("first ad keys: " + ", ".join(sorted(ads[0].keys()))[:400])
        for ad in ads:
            ad_id = str(_get(ad, "id", "adid", "ad_id", "posid", "position_id", "positionid"))
            if not ad_id:
                continue
            title = str(_get(ad, "title", "position_title", "ad_title", "positiontitle", "name"))
            inst = _get(ad, "institution", "inst_name", "institution_name", "organization", "employer",
                        "recruiter", "recruiter_name", "orgname")
            inst = _names(inst) if isinstance(inst, (dict, list)) else str(inst)
            dept = str(_get(ad, "department", "dept", "division", "unit", "department_name"))
            cats = "; ".join(x for x in (_names(_get(ad, "categories", "fields", "category", default=[])),
                                         _names(_get(ad, "position_types", "positiontypes", "type", default=[]))) if x)
            desc = html_to_text(str(_get(ad, "description", "ad_text", "adtext", "text", "details", "body")))
            url = str(_get(ad, "url", "link", "position_url", "ad_url", "ejm_url")) or \
                f"https://econjobmarket.org/positions/{ad_id}"
            job = RawJob(
                source=self.name, source_id=ad_id, url=url, title=title, institution=inst, department=dept,
                location=", ".join(str(x) for x in (_get(ad, "city", "location"), _get(ad, "state", "region"))
                                   if x and not isinstance(x, (dict, list))),
                country=_names(_get(ad, "country", "country_name", "countrycode")),
                categories=cats, description=desc,
                posted_date=str(_get(ad, "created", "posted", "posted_date", "date_posted", "startdate"))[:10],
                deadline_raw=str(_get(ad, "deadline", "enddate", "end_date", "closing_date",
                                      "application_deadline"))[:10],
                start_date_raw=str(_get(ad, "position_start", "job_start", "start_of_job")),
                default_field=self.cfg.get("default_field", ""),
            )
            if job.job_id in known_ids:
                job.stub = True
                result.jobs.append(job)
                continue
            if not looks_business(title, " ".join([inst, dept, cats, desc[:1500]])):
                result.skipped_filtered += 1
                continue
            result.jobs.append(job)
        # The feed is the complete set of open ads.
        result.complete = True
        result.seconds = round(time.monotonic() - t0, 1)
        return result
