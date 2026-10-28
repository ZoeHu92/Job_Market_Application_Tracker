"""Postings that arrive by e-mail: job alerts from boards that block scraping or need a
member login (FMA, AMA, AOM, INFORMS, AIS, jobs.ac.uk), SSRN announcement e-mails, and
listserv posts (AISWorld, ELMAR, AOM divisions, ...).

Setup (README, "Email alerts"): filter those e-mails into one mailbox folder / Gmail
label, create an app password, and provide TRACKER_IMAP_USER and TRACKER_IMAP_PASSWORD
as GitHub Actions secrets or in my_data/email.env. The tracker only reads that folder
(read-only); it never sends, moves or deletes mail.
"""
from __future__ import annotations

import email
import imaplib
import os
import re
import time
from datetime import date, timedelta
from email.policy import default as default_policy
from email.utils import parsedate_to_datetime
from pathlib import Path

from ..classify import business_relevance, is_faculty_position
from ..extract import clean_text, html_to_text, soupify
from .base import RawJob, SourceResult, stable_id
from .board import _institution_from_context, institution_from_text

SENDER_LABELS = [
    (r"fma\.org|memberclicks", "FMA"), (r"\bama\.org", "AMA"), (r"aom\.org", "AOM"), (r"informs\.org", "INFORMS"),
    (r"aisnet\.org", "AIS"), (r"jobs\.ac\.uk", "jobs.ac.uk"), (r"ssrn\.com", "SSRN"), (r"afajof\.org", "AFA"),
    (r"aaahq\.org", "AAA"), (r"aeaweb\.org", "JOE"), (r"econjobmarket", "EJM"), (r"higheredjobs", "HigherEdJobs"),
    (r"chronicle\.com", "Chronicle"), (r"insidehighered", "InsideHigherEd"), (r"timeshighereducation", "THE"),
    (r"academicpositions", "AcademicPositions"), (r"euraxess", "EURAXESS"),
]
# Alerts from these senders are business-school jobs by construction.
BUSINESS_SENDERS = {"FMA", "AMA", "AOM", "INFORMS", "AIS", "AFA", "AAA"}

_SKIP_LINK = re.compile(
    r"unsubscribe|preferences|privacy|manage|log ?in|sign ?in|view (this|in|it in) (e-?mail|browser)|facebook|twitter|"
    r"linkedin|instagram|youtube|^mailto:|\bhelp\b|terms|my account|edit (your )?alert|see all|view all|more jobs|"
    r"forward to a friend|update profile", re.I)
_ALERT_SUBJECT = re.compile(r"job alert|new jobs?|jobs? (matching|for you|digest)|latest (jobs|positions)|"
                            r"announcements?|e-?journal|weekly (jobs|digest)", re.I)
_SUBJECT_PREFIX = re.compile(r"^\s*((re|fw|fwd|aw)\s*:\s*|\[[^\]]{1,40}\]\s*|(job|position|job opening|vacancy)\s*:\s*)+", re.I)


def load_credentials(env_file: Path) -> tuple[str, str]:
    user = os.environ.get("TRACKER_IMAP_USER", "")
    password = os.environ.get("TRACKER_IMAP_PASSWORD", "")
    if (not user or not password) and env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k == "TRACKER_IMAP_USER" and not user:
                user = v
            elif k == "TRACKER_IMAP_PASSWORD" and not password:
                password = v
    return user, password


def sender_label(msg) -> str:
    """Listserv name from List-Id (e.g. AISWorld), else the job board behind the sender address."""
    list_id = str(msg.get("List-Id", "")).strip()
    if list_id:
        m = re.match(r'\s*"?([^"<]+?)"?\s*<', list_id) or re.match(r"\s*<?([\w-]+)", list_id)
        if m:
            return m.group(1).strip()[:30]
    headers = " ".join(str(msg.get(h, "")) for h in ("From", "Sender", "Reply-To"))
    for pat, label in SENDER_LABELS:
        if re.search(pat, headers, re.I):
            return label
    m = re.match(r'\s*"?([^"<@]+?)"?\s*<', str(msg.get("From", "")))
    return (m.group(1).strip() if m else "Email")[:30]


def message_parts(msg) -> tuple[str, str]:
    html = text = ""
    for part in msg.walk() if msg.is_multipart() else [msg]:
        ctype = part.get_content_type()
        if part.get_content_disposition() == "attachment":
            continue
        try:
            payload = part.get_content()
        except (LookupError, ValueError):
            payload = (part.get_payload(decode=True) or b"").decode("utf-8", "replace")
        if ctype == "text/html" and not html:
            html = payload
        elif ctype == "text/plain" and not text:
            text = payload
    return html, text


def _block_text(a) -> str:
    node = a
    for _ in range(5):
        node = node.parent
        if node is None or node.name in ("body", "html"):
            break
        if node.name in ("tr", "li", "p", "div", "td", "table"):
            txt = clean_text(node.get_text("\n"))
            if len(txt) > len(clean_text(a.get_text(" "))) + 15:
                return txt[:900]
    return ""


def listing_links(html: str, base_url: str = "") -> list[tuple[str, str, str]]:
    """(title, url, surrounding text) for every faculty-job link in an alert e-mail."""
    from urllib.parse import urljoin

    out, seen = [], set()
    for a in soupify(html).find_all("a", href=True):
        title = clean_text(a.get_text(" "))
        href = urljoin(base_url, a["href"].strip()) if base_url else a["href"].strip()
        if not href.startswith("http") or not (8 <= len(title) <= 200) or _SKIP_LINK.search(f"{title} {href[:120]}"):
            continue
        if not is_faculty_position(title) or title.lower() in seen:
            continue
        seen.add(title.lower())
        out.append((title, href, _block_text(a)))
    return out


def parse_message(msg, today: date | None = None) -> list[RawJob]:
    """Turn one e-mail into postings: an alert digest yields one per listed job, a
    listserv post or single announcement yields one."""
    today = today or date.today()
    label = sender_label(msg)
    source = f"{label} (email)"
    subject = clean_text(str(msg.get("Subject", "")))
    try:
        sent = parsedate_to_datetime(str(msg.get("Date"))).date().isoformat()
    except (TypeError, ValueError):
        sent = today.isoformat()
    html, text = message_parts(msg)
    body = html_to_text(html) if html else clean_text(text)

    links = listing_links(html) if html else []

    jobs: list[RawJob] = []
    if len(links) >= 2 or (links and _ALERT_SUBJECT.search(subject)):
        for title, href, ctx in links:
            inst = _institution_from_context(ctx.replace("\n", "  "), title) or institution_from_text(ctx)
            jobs.append(RawJob(source=source, source_id=stable_id(f"{title.lower()}|{inst.lower()}"), url=href,
                               title=title, institution=inst, description=ctx, posted_date=sent,
                               categories=f"via {label} e-mail"))
    else:
        title = _SUBJECT_PREFIX.sub("", subject).strip() or subject
        url = links[0][1] if links else ""
        if not url:
            m = re.search(r"https?://[^\s<>\"')]+", body)
            url = m.group(0) if m else ""
        inst = institution_from_text(title) or _institution_from_context(body[:600].replace("\n", "  "), title)
        msg_id = str(msg.get("Message-ID", "")) or f"{subject}|{sent}"
        jobs.append(RawJob(source=source, source_id=stable_id(msg_id), url=url, title=title, institution=inst,
                           description=body[:20000], posted_date=sent, categories=f"via {label} e-mail"))

    keep = []
    for j in jobs:
        if not is_faculty_position(j.title, j.description):
            continue
        if label not in BUSINESS_SENDERS and not business_relevance(j.title, j.institution, "", "", j.description):
            continue
        keep.append(j)
    return keep


class EmailSource:
    def __init__(self, cfg: dict, fetcher=None, settings: dict | None = None):
        from .. import paths

        self.cfg = cfg
        self.name = cfg["name"]
        opts = {**(settings or {}).get("email", {}), **cfg}
        self.host = opts.get("imap_host", "imap.gmail.com")
        self.folder = opts.get("folder", "JobAlerts")
        self.lookback = int(opts.get("lookback_days", 30))
        self.max_messages = int(opts.get("max_messages", 300))
        self.env_file = paths.email_env()

    def run(self, known_ids: set[str], today: date | None = None, imap_factory=imaplib.IMAP4_SSL) -> SourceResult:
        t0 = time.monotonic()
        today = today or date.today()
        result = SourceResult(name=self.name)
        if os.environ.get("TRACKER_PUBLIC_REPO", "").lower() in ("1", "true", "yes"):
            result.notes.append("skipped: this repository is public, so member-only postings from e-mail are not "
                                "collected in the cloud (make the repo private, or check e-mail from the app)")
            return result
        user, password = load_credentials(self.env_file)
        if not user or not password:
            result.notes.append("e-mail alerts not set up (see README: Email alerts)")
            return result
        try:
            imap = imap_factory(self.host)
            imap.login(user, password)
            status, _ = imap.select(f'"{self.folder}"', readonly=True)
            if status != "OK":
                raise imaplib.IMAP4.error(f"folder '{self.folder}' not found")
            since = (today - timedelta(days=self.lookback)).strftime("%d-%b-%Y")
            status, data = imap.search(None, f"(SINCE {since})")
            ids = (data[0] or b"").split()[-self.max_messages:] if status == "OK" else []
            for num in ids:
                status, parts = imap.fetch(num, "(BODY.PEEK[])")
                raw = next((p[1] for p in parts or [] if isinstance(p, tuple)), None)
                if status != "OK" or not raw:
                    continue
                result.pages += 1
                msg = email.message_from_bytes(raw, policy=default_policy)
                for job in parse_message(msg, today):
                    if job.job_id in known_ids:
                        job.stub = True
                    result.jobs.append(job)
            try:
                imap.logout()
            except Exception:  # noqa: BLE001
                pass
        except (imaplib.IMAP4.error, OSError) as exc:
            result.ok = False
            result.error = f"mailbox: {exc}"[:200]
            return result
        # Old e-mails age out of the look-back window, so absence never means "closed".
        result.complete = False
        result.notes.append(f"read {result.pages} e-mails from '{self.folder}'")
        result.seconds = round(time.monotonic() - t0, 1)
        return result
