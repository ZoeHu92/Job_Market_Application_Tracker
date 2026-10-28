"""RawJob → structured row (JOB_COLUMNS)."""
from __future__ import annotations

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
    rank, tenure = C.detect_rank(raw.title, text, region)

    posted = C.parse_date_string(raw.posted_date, today)
    ref = posted or today
    dl = C.extract_deadline(full, ref)
    if raw.deadline_raw:
        src_deadline = C.parse_date_string(raw.deadline_raw, ref)
        if src_deadline:
            if dl["deadline"] and dl["deadline"] != src_deadline.isoformat():
                dl["deadline_note"] = f"Listed deadline {C.fmt_date(src_deadline)}; text says: {dl['deadline_note']}"
            elif not dl["deadline_note"]:
                dl["deadline_note"] = f"Deadline {C.fmt_date(src_deadline)}"
            dl["deadline"] = src_deadline.isoformat()

    if raw.salary_min:
        sal = {"salary_min": raw.salary_min, "salary_max": raw.salary_max or raw.salary_min,
               "salary_currency": raw.salary_currency, "salary_text": raw.salary_text}
    else:
        sal = C.extract_salary(f"salary {raw.salary_label}") if raw.salary_label else C.extract_salary("")
        if not sal["salary_text"]:
            sal = C.extract_salary(text)
        if not sal["salary_text"] and raw.salary_label and len(raw.salary_label) < 80:
            sal["salary_text"] = raw.salary_label  # e.g. "Competitive" / "Commensurate with experience"

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
    })
    return row
