"""RawJob → structured row (JOB_COLUMNS)."""
from __future__ import annotations

import hashlib
import re
from datetime import date

from . import classify as C
from .schema import JOB_COLUMNS
from .sources.base import RawJob


def enrich(raw: RawJob, today: date | None = None, keep_description: bool = False) -> dict:
    today = today or date.today()
    text = raw.description or ""
    full = "\n".join(x for x in (raw.title, raw.department, raw.categories, text) if x)

    country = C.detect_country(raw.location, raw.country, text)
    region = C.region_for(country)
    primary, fields = C.detect_fields(raw.title, raw.department, raw.categories, text, default=raw.default_field)
    if raw.field_override:
        primary, fields = raw.field_override, [raw.field_override] + [f for f in fields if f != raw.field_override]
    rank, tenure = C.detect_rank(raw.title, text, region)

    posted = C.parse_date_string(raw.posted_date, today)
    ref = posted or today
    dl = C.extract_deadline(full, ref)
    src_deadline = C.parse_date_string(raw.deadline_raw, ref) if raw.deadline_raw else None
    if src_deadline:
        # A board's "closing date" is often when the ad comes down; if the text asks for
        # applications earlier, the earlier date is the one that matters.
        text_dl = dl["deadline"]
        if text_dl and text_dl < src_deadline.isoformat():
            dl["deadline_note"] = f"{dl['deadline_note']}; listing closes {C.fmt_date(src_deadline)}"
        else:
            rest = [p for p in dl["deadline_note"].split("; ") if p and not p.lower().startswith("deadline")]
            dl["deadline_note"] = "; ".join([f"Deadline {C.fmt_date(src_deadline)}", *rest])
            dl["deadline"] = src_deadline.isoformat()

    if raw.salary_min:
        sal = {"salary_min": raw.salary_min, "salary_max": raw.salary_max or raw.salary_min,
               "salary_currency": raw.salary_currency, "salary_text": raw.salary_text}
    else:
        sal = C.extract_salary(f"salary {raw.salary_label}") if raw.salary_label else C.extract_salary("")
        if not sal["salary_text"]:
            sal = C.extract_salary(text)
        label = (raw.salary_label or "").strip()
        if (not sal["salary_text"] and label and len(label) < 90
                and not re.search(r"not (specified|stated|disclosed)|^n/?a$|^none$|^tbd$|^-+$", label, re.I)
                and label.lower() != raw.institution.strip().lower()):
            sal["salary_text"] = label  # e.g. "Competitive" / "Commensurate with experience"

    row = {c: "" for c in JOB_COLUMNS}
    row.update({
        "job_id": raw.job_id,
        "source": raw.source,
        "source_id": raw.source_id,
        "title": raw.title.strip(),
        "institution": raw.institution.strip(),
        "department": raw.department.strip(),
        "location": raw.location.strip(),
        "country": country,
        "region": region,
        "field": primary,
        "fields": "; ".join(fields),
        "rank": rank,
        "tenure_track": tenure,
        "degree_req": C.detect_degree(text),
        "is_business_school": C.is_business_school(raw.institution, raw.department, text[:800]),
        "deadline": dl["deadline"],
        "review_start": dl["review_start"],
        "open_until_filled": dl["open_until_filled"],
        "deadline_note": dl["deadline_note"],
        "start_date": raw.start_date_raw.strip() or C.extract_start_date(text),
        **sal,
        "materials": "; ".join(C.detect_materials(text)),
        "interview_venues": "; ".join(C.detect_interview_venues(text)),
        "requirements": C.requirement_highlights(text),
        "categories": raw.categories,
        "posted_date": posted.isoformat() if posted else "",
        "listing_expires": raw.listing_expires,
        "url": raw.url,
        "apply_url": raw.apply_url,
        "status": "Open",
        "status_note": f"Details unavailable: {raw.detail_error}" if raw.detail_error else "",
        "description": text if keep_description else "",
        "content_hash": hashlib.sha1(re.sub(r"\s+", " ", text).encode("utf-8")).hexdigest()[:12] if text else "",
    })
    return row
