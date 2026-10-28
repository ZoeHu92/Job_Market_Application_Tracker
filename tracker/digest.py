"""Weekly markdown digest (posted as a GitHub issue by the workflow)."""
from __future__ import annotations

from datetime import date, timedelta

from .classify import parse_date_string


def _line(r: dict) -> str:
    inst = r.get("institution") or "(institution not parsed)"
    bits = [r.get("rank", "")]
    if r.get("deadline"):
        bits.append(f"deadline {r['deadline']}")
    elif r.get("review_start"):
        bits.append(f"review from {r['review_start']}")
    if r.get("salary_text"):
        bits.append(r["salary_text"])
    bits.append(r.get("source", ""))
    meta = " · ".join(b for b in bits if b)
    return f"- **{inst}** — [{r.get('title', '').strip() or 'posting'}]({r.get('url', '')}) ({meta})"


def build_digest(rows: dict[str, dict], report: dict, today: date, fields: list[str] | None = None,
                 max_per_field: int = 60) -> str:
    fields = [f for f in (fields or []) if f]
    t = today.isoformat()

    def wanted(r):
        return not fields or r.get("field") in fields

    new = [r for r in rows.values() if r.get("first_seen") == t and r.get("status") == "Open"
           and not r.get("duplicate_of") and wanted(r)]
    closed = [r for r in rows.values() if r.get("closed_date") == t and wanted(r)]
    soon = []
    for r in rows.values():
        if r.get("status") != "Open" or r.get("duplicate_of") or not wanted(r):
            continue
        d = parse_date_string(r.get("deadline", ""), today)
        if d and today <= d <= today + timedelta(days=14):
            soon.append((d, r))
    soon.sort(key=lambda x: x[0])

    out = [f"# Academic job market digest — {today:%B %d, %Y}", ""]
    if fields:
        out.append(f"_Fields: {', '.join(fields)}_\n")
    out.append(f"**{len(new)} new postings · {len(soon)} deadlines in the next 14 days · {len(closed)} closed this week**\n")

    out.append(f"## New this week ({len(new)})")
    by_field: dict[str, list[dict]] = {}
    for r in new:
        by_field.setdefault(r.get("field") or "Other", []).append(r)
    for f in sorted(by_field, key=lambda k: (-len(by_field[k]), k)):
        items = sorted(by_field[f], key=lambda r: (r.get("deadline") or "9999", r.get("institution", "")))
        out.append(f"\n### {f} ({len(items)})")
        out.extend(_line(r) for r in items[:max_per_field])
        if len(items) > max_per_field:
            out.append(f"- …and {len(items) - max_per_field} more (see the app)")
    if not new:
        out.append("_None this week._")

    out.append(f"\n## Deadlines in the next 14 days ({len(soon)})")
    out.extend(_line(r) for _, r in soon[:80])
    if not soon:
        out.append("_None._")

    out.append(f"\n## Closed / removed this week ({len(closed)})")
    out.extend(f"- {r.get('institution', '')} — {r.get('title', '')} ({r.get('status_note', '')})" for r in closed[:80])
    if not closed:
        out.append("_None._")

    out.append("\n## Source health")
    out.append("| Source | OK | Listed | New | Closed | Note |")
    out.append("|---|---|---|---|---|---|")
    for s in report.get("sources", []):
        note = s.get("error") or s.get("closures_skipped") or ""
        out.append(f"| {s['name']} | {'✅' if s.get('ok') else '❌'} | {s.get('listed', 0)} | {s.get('new', 0)} | "
                   f"{s.get('closed', 0)} | {note[:120]} |")
    body = "\n".join(out)
    return body[:60000]
