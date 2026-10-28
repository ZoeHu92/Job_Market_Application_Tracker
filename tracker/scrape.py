"""Weekly scrape: python -m tracker.scrape [--sources AFA,EJM] [--data-dir data]

Reads config/sources.yaml, collects postings from every enabled source,
classifies new ones, merges into <data-dir>/jobs.csv (closing jobs that left
their board), and writes <data-dir>/scrape_report.json and weekly_digest.md.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from .config import CONFIG_DIR, load_settings, load_sources
from .digest import build_digest
from .enrich import enrich
from .extract import extract_posting
from .http import Fetcher, FetchError
from .sources.base import SourceResult
from .sources.board import BoardSource
from .sources.econjobmarket import EconJobMarketSource
from .store import merge_results, read_jobs, write_jobs

log = logging.getLogger("tracker.scrape")

ADAPTERS = {"board": BoardSource, "econjobmarket": EconJobMarketSource}


def make_verifier(fetcher: Fetcher, trust_listing: set[str] | None = None):
    """Re-check a posting that vanished from its board: 'gone' | 'alive' | 'unknown'.

    Sources in trust_listing (verify_closures: false) publish a complete feed of
    open ads, so absence alone means closed.
    """
    trust_listing = trust_listing or set()

    def verify(row: dict) -> str:
        if row.get("source") in trust_listing:
            return "gone"
        url = row.get("url") or ""
        if not url:
            return "unknown"
        try:
            r = fetcher.get(url)
        except FetchError:
            return "unknown"
        if r.status_code in (404, 410):
            return "gone"
        if row.get("source_id") and row["source_id"] not in r.url and urlparse(r.url).path.rstrip("/") != urlparse(url).path.rstrip("/"):
            return "gone"  # redirected to a search/listing page
        return "gone" if extract_posting(r.content, r.url).get("closed_hint") else "alive"

    return verify


def run(data_dir: Path, baseline: Path | None = None, only: list[str] | None = None,
        config_dir: Path = CONFIG_DIR, today: date | None = None, check_closures: bool = True,
        fetcher: Fetcher | None = None, keep_description: bool | None = None) -> dict:
    today = today or date.today()
    settings = load_settings(config_dir)
    sources = load_sources(config_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    rows = read_jobs(baseline or data_dir / "jobs.csv")
    fetcher = fetcher or Fetcher(delay=float(settings["request_delay_seconds"]))
    skipped_path = data_dir / "skipped_ids.json"
    skipped: dict[str, str] = json.loads(skipped_path.read_text()) if skipped_path.exists() else {}
    known = set(rows) | set(skipped)
    started = datetime.now(timezone.utc)

    results: list[SourceResult] = []
    labels = {}
    for cfg in sources:
        name = cfg["name"]
        if only and name.lower() not in [o.lower() for o in only]:
            continue
        if not only and not cfg.get("enabled", True):
            continue
        labels[name] = cfg.get("label", name)
        adapter_cls = ADAPTERS.get(cfg.get("kind", "board"))
        log.info("== %s", name)
        t0 = time.monotonic()
        try:
            res = adapter_cls(cfg, fetcher, settings).run(known)
        except Exception as exc:  # noqa: BLE001 - one broken source must not stop the run
            log.exception("source %s crashed", name)
            res = SourceResult(name=name, ok=False, error=f"crashed: {exc!r}"[:300])
        res.seconds = res.seconds or round(time.monotonic() - t0, 1)
        log.info("   ok=%s complete=%s jobs=%d new_details=%d %s", res.ok, res.complete, len(res.jobs),
                 res.details_fetched, res.error)
        results.append(res)

    keep_desc = bool(settings.get("keep_full_description")) if keep_description is None else keep_description
    enriched = {j.job_id: enrich(j, today, keep_desc) for res in results for j in res.jobs if not j.stub}
    trust = {c["name"] for c in sources if c.get("verify_closures") is False}
    verifier = make_verifier(fetcher, trust) if check_closures else None
    stats = merge_results(rows, results, enriched, today, verifier, int(settings["closure_checks_per_source"]))
    if not keep_desc:
        for r in rows.values():
            r["description"] = ""
    write_jobs(rows, data_dir / "jobs.csv")
    for res in results:
        for jid in res.skipped_ids:
            skipped.setdefault(jid, today.isoformat())
    horizon = date.fromordinal(today.toordinal() - 180).isoformat()
    skipped = {k: v for k, v in sorted(skipped.items()) if v >= horizon and k not in rows}
    skipped_path.write_text(json.dumps(skipped, indent=0), encoding="utf-8")

    report = {
        "started_at": started.isoformat(timespec="seconds"),
        "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "run_date": today.isoformat(),
        "requests": fetcher.requests_made,
        "totals": {
            "jobs": len(rows),
            "open": sum(r.get("status") == "Open" for r in rows.values()),
            "new": sum(s["new"] for s in stats.values()),
            "closed": sum(r.get("closed_date") == today.isoformat() for r in rows.values()),
        },
        "sources": [
            {"name": r.name, "label": labels.get(r.name, r.name), "ok": r.ok, "complete": r.complete,
             "error": r.error, "pages": r.pages, "details_fetched": r.details_fetched,
             "skipped_filtered": r.skipped_filtered, "seconds": r.seconds, "notes": r.notes[:25],
             **stats.get(r.name, {})}
            for r in results
        ],
    }
    (data_dir / "scrape_report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    digest = build_digest(rows, report, today, settings.get("digest_fields") or [])
    (data_dir / "weekly_digest.md").write_text(digest, encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", default="data", help="output folder (default: data)")
    ap.add_argument("--baseline", default=None, help="jobs.csv to start from (default: <data-dir>/jobs.csv)")
    ap.add_argument("--sources", default="", help="comma-separated source names (default: all enabled)")
    ap.add_argument("--config-dir", default=str(CONFIG_DIR))
    ap.add_argument("--no-closure-check", action="store_true", help="close missing jobs without re-checking pages")
    ap.add_argument("--keep-description", action="store_true",
                    help="store full posting text even if settings say not to (for private local data)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(message)s")
    only = [s.strip() for s in args.sources.split(",") if s.strip()] or None
    report = run(Path(args.data_dir), Path(args.baseline) if args.baseline else None, only,
                 Path(args.config_dir), check_closures=not args.no_closure_check,
                 keep_description=True if args.keep_description else None)
    print("\nSource            ok   complete  listed  new  closed  error")
    for s in report["sources"]:
        print(f"{s['name']:<17} {str(s['ok']):<5} {str(s['complete']):<9} {s.get('listed', 0):>6} {s.get('new', 0):>4} "
              f"{s.get('closed', 0):>7}  {s['error'][:70]}")
    t = report["totals"]
    print(f"\nTotal: {t['open']} open of {t['jobs']} tracked; {t['new']} new, {t['closed']} closed this run.")
    # Fail the workflow only if every source failed, so partial outages still save data.
    return 0 if any(s["ok"] for s in report["sources"]) or not report["sources"] else 1


if __name__ == "__main__":
    sys.exit(main())
