"""Reading/writing data/jobs.csv and merging a scrape run into it.

Lifecycle of a posting:
  * first seen  → status Open, first_seen = run date
  * seen again  → last_seen updated (a Closed job that reappears is re-opened)
  * missing from a *complete* listing of its source → its page is re-checked;
    if the page is gone or says expired/filled (or cannot be checked) the job is
    Closed with closed_date = run date. A source that errored or was only
    partly read never closes anything, so an outage cannot wipe the board.
  * deadline more than 90 days ago, or listing expiry passed → Closed.
"""
from __future__ import annotations

import csv
import difflib
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Iterable

from .classify import normalize_institution, parse_date_string
from .schema import JOB_COLUMNS
from .sources.base import SourceResult

csv.field_size_limit(10_000_000)


def read_jobs(path: str | Path) -> dict[str, dict]:
    path = Path(path)
    if not path.exists() or path.stat().st_size == 0:
        return {}
    with path.open(newline="", encoding="utf-8") as fh:
        rows = {}
        for r in csv.DictReader(fh):
            row = {c: r.get(c, "") or "" for c in JOB_COLUMNS}
            rows[row["job_id"]] = row
        return rows


def _cell(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "True" if v else ""
    if isinstance(v, float):
        return f"{v:.0f}" if v == int(v) else f"{v}"
    return str(v)


def write_jobs(rows: dict[str, dict] | Iterable[dict], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    items = list(rows.values()) if isinstance(rows, dict) else list(rows)
    items.sort(key=lambda r: r["job_id"])  # stable order keeps weekly git diffs small
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=JOB_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in items:
            w.writerow({c: _cell(r.get(c)) for c in JOB_COLUMNS})
    tmp.replace(path)


def _long_past_deadline(row: dict, today: date) -> bool:
    dl = parse_date_string(row.get("deadline", ""), today)
    return bool(dl and dl < today - timedelta(days=90))


def _close(row: dict, today: date, note: str) -> None:
    row["status"] = "Closed"
    row["closed_date"] = today.isoformat()
    row["status_note"] = note


# Fields refreshed when a known job's details are re-fetched.
_KEEP_ON_UPDATE = {"job_id", "first_seen", "status", "closed_date", "duplicate_of"}


def merge_results(rows: dict[str, dict], results: list[SourceResult], enriched: dict[str, dict], today: date,
                  verifier: Callable[[dict], str] | None = None, closure_cap: int = 60) -> dict[str, dict]:
    """Apply one scrape run to rows (in place). Returns per-source stats.

    enriched maps job_id → full row for non-stub jobs collected this run.
    verifier(row) → "gone" | "alive" | "unknown" re-checks a missing posting.
    """
    stats: dict[str, dict] = {}
    t = today.isoformat()
    for res in results:
        st = {"listed": 0, "new": 0, "reopened": 0, "closed": 0, "kept_open": 0, "closures_skipped": ""}
        seen: set[str] = set()
        for job in res.jobs:
            jid = job.job_id
            row = rows.get(jid)
            if row is None and jid not in enriched:
                continue  # a posting skipped as out of scope in an earlier run
            seen.add(jid)
            st["listed"] += 1
            if row is None:
                row = dict(enriched[jid])
                row.update(first_seen=t, last_seen=t, status="Open", closed_date="")
                rows[jid] = row
                st["new"] += 1
                continue
            if jid in enriched:
                for k, v in enriched[jid].items():
                    if k not in _KEEP_ON_UPDATE and v not in ("", None):
                        row[k] = v
            row["last_seen"] = t
            if row.get("status") == "Closed" and not _long_past_deadline(row, today):
                row.update(status="Open", closed_date="", status_note=f"Re-listed {t}")
                st["reopened"] += 1
            elif row.get("status_note", "").startswith("Not in latest listing"):
                row["status_note"] = ""

        open_before = [r for r in rows.values() if r["source"] == res.name and r.get("status") == "Open"]
        missing = [r for r in open_before if r["job_id"] not in seen]
        if not (res.ok and res.complete):
            st["closures_skipped"] = "source incomplete or unavailable this run"
        elif len(open_before) >= 10 and len(missing) > 0.6 * len(open_before):
            st["closures_skipped"] = f"{len(missing)} of {len(open_before)} open jobs missing - looks like a scraping problem"
        else:
            for i, r in enumerate(missing):
                verdict = verifier(r) if (verifier and i < closure_cap) else "unknown"
                if verdict == "alive":
                    r["status_note"] = f"Not in latest listing ({t}) but posting page is still online"
                    st["kept_open"] += 1
                else:
                    note = "Posting removed or marked closed" if verdict == "gone" else f"Removed from {res.name} listing"
                    _close(r, today, note)
                    st["closed"] += 1
        stats[res.name] = st

    expire_rows(rows, today)
    mark_duplicates(rows)
    return stats


def expire_rows(rows: dict[str, dict], today: date) -> int:
    """Close jobs whose deadline is long past, or whose listing expiry passed and that were not seen this run."""
    n = 0
    for r in rows.values():
        if r.get("status") != "Open":
            continue
        exp = parse_date_string(r.get("listing_expires", ""), today)
        if _long_past_deadline(r, today):
            _close(r, today, "Deadline passed more than 90 days ago")
            n += 1
        elif exp and exp < today - timedelta(days=3) and r.get("last_seen") != today.isoformat():
            _close(r, today, f"Listing expired {exp.isoformat()}")
            n += 1
    return n


def _rank_compatible(a: str, b: str) -> bool:
    if a == b or "Unspecified" in (a, b):
        return True
    asst = {"Assistant", "Assistant/Associate", "Open rank"}
    return a in asst and b in asst


def mark_duplicates(rows: dict[str, dict]) -> None:
    """Flag the same position cross-posted on several boards (keeps the earliest seen)."""
    groups: dict[tuple, list[dict]] = {}
    for r in rows.values():
        r["duplicate_of"] = ""
        if r.get("status") != "Open":
            continue
        key = (normalize_institution(r.get("institution", "")), r.get("field", ""))
        if key[0]:
            groups.setdefault(key, []).append(r)
    for members in groups.values():
        if len(members) < 2:
            continue
        members.sort(key=lambda r: (r.get("first_seen", ""), r["job_id"]))
        for i, r in enumerate(members):
            for canon in members[:i]:
                if canon["source"] == r["source"] or canon.get("duplicate_of"):
                    continue
                same_title = difflib.SequenceMatcher(None, canon["title"].lower(), r["title"].lower()).ratio() > 0.55
                if _rank_compatible(canon.get("rank", ""), r.get("rank", "")) and (same_title or canon.get("rank") == r.get("rank")):
                    r["duplicate_of"] = canon["job_id"]
                    break
