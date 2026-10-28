"""Shared types for source adapters."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field


@dataclass
class RawJob:
    """A posting as collected from a source, before classification."""

    source: str
    source_id: str
    url: str
    title: str = ""
    institution: str = ""
    department: str = ""
    location: str = ""
    country: str = ""
    categories: str = ""
    description: str = ""
    posted_date: str = ""
    deadline_raw: str = ""
    listing_expires: str = ""
    start_date_raw: str = ""
    salary_label: str = ""
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str = ""
    salary_text: str = ""
    apply_url: str = ""
    default_field: str = ""
    # True when the job was already known and only its presence was confirmed
    # (no detail page fetched this run).
    stub: bool = False
    detail_error: str = ""

    @property
    def job_id(self) -> str:
        return f"{self.source}:{self.source_id}"


@dataclass
class SourceResult:
    name: str
    jobs: list[RawJob] = field(default_factory=list)
    ok: bool = True          # the source responded and parsed
    complete: bool = False   # the full listing was seen, so missing jobs can be closed
    error: str = ""
    notes: list[str] = field(default_factory=list)
    pages: int = 0
    details_fetched: int = 0
    skipped_filtered: int = 0
    # Postings whose detail page was fetched but that were rejected (not a
    # business-school faculty job, or already closed). Remembered so they are
    # not fetched again every week.
    skipped_ids: list[str] = field(default_factory=list)
    seconds: float = 0.0


def stable_id(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
