"""Generic extraction of job details from an HTML posting page.

Most job boards (Madgex, YM Careers, jobs.ac.uk, HigherEdJobs, university ATS
pages) embed schema.org JobPosting JSON-LD for Google for Jobs, so that is
tried first. Labeled fields (<dt>/<dd>, table rows, "Label: value" lines) and
the main text block fill the gaps.
"""
from __future__ import annotations

import html as htmllib
import json
import re
from typing import Any

from bs4 import BeautifulSoup

from .classify import looks_closed


def soupify(html: str | bytes) -> BeautifulSoup:
    try:
        return BeautifulSoup(html, "lxml")
    except Exception:  # noqa: BLE001 - lxml missing or choked; fall back
        return BeautifulSoup(html, "html.parser")


def html_to_text(fragment: str) -> str:
    """Convert an HTML fragment (e.g. a JSON-LD description) to readable text."""
    if not fragment:
        return ""
    if "<" not in fragment:
        return clean_text(htmllib.unescape(fragment))
    soup = soupify(fragment)
    for br in soup.find_all(["br"]):
        br.replace_with("\n")
    for block in soup.find_all(["p", "li", "div", "h1", "h2", "h3", "h4", "tr"]):
        block.insert_after("\n")
    return clean_text(soup.get_text(" "))


def clean_text(text: str) -> str:
    text = htmllib.unescape(text or "").replace("\xa0", " ")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# JSON-LD
# ---------------------------------------------------------------------------

def _iter_jsonld_objects(data: Any):
    if isinstance(data, list):
        for item in data:
            yield from _iter_jsonld_objects(item)
    elif isinstance(data, dict):
        yield data
        if "@graph" in data:
            yield from _iter_jsonld_objects(data["@graph"])


def _is_jobposting(obj: dict) -> bool:
    t = obj.get("@type")
    types = t if isinstance(t, list) else [t]
    return any(isinstance(x, str) and x.lower() == "jobposting" for x in types)


def _first(v: Any) -> Any:
    return v[0] if isinstance(v, list) and v else v


def _name(v: Any) -> str:
    v = _first(v)
    if isinstance(v, dict):
        return str(v.get("name") or v.get("legalName") or "").strip()
    return str(v or "").strip()


def _address_parts(loc: Any) -> tuple[str, str]:
    """(display location, country) from a JobPosting jobLocation value."""
    locs = loc if isinstance(loc, list) else [loc]
    displays, country = [], ""
    for item in locs:
        if not isinstance(item, dict):
            if item:
                displays.append(str(item))
            continue
        addr = item.get("address", item)
        if isinstance(addr, str):
            displays.append(addr)
            continue
        if not isinstance(addr, dict):
            continue
        c = addr.get("addressCountry")
        c = _name(c) if isinstance(c, (dict, list)) else str(c or "")
        parts = [addr.get("addressLocality"), addr.get("addressRegion"), c]
        displays.append(", ".join(str(p).strip() for p in parts if p and str(p).strip()))
        country = country or c.strip()
    return "; ".join(d for d in displays if d), country


def _salary(base: Any) -> dict:
    out = {"salary_min": None, "salary_max": None, "salary_currency": "", "salary_text": ""}
    base = _first(base)
    if not isinstance(base, dict):
        return out
    cur = str(base.get("currency") or "")
    val = base.get("value")
    unit = ""
    lo = hi = None
    if isinstance(val, dict):
        unit = str(val.get("unitText") or "")
        lo = val.get("minValue", val.get("value"))
        hi = val.get("maxValue", lo)
    elif val is not None:
        lo = hi = val
    try:
        lo = float(lo) if lo not in (None, "") else None
        hi = float(hi) if hi not in (None, "") else lo
    except (TypeError, ValueError):
        return out
    if lo is None or lo <= 0:
        return out
    if unit.upper() == "MONTH" and lo < 2000 or unit.upper() == "HOUR":
        return out  # hourly figures are adjunct pay, not a faculty salary
    sym = {"USD": "$", "GBP": "£", "EUR": "€"}.get(cur.upper(), (cur + " ") if cur else "")
    txt = f"{sym}{lo:,.0f}" + (f"–{sym}{hi:,.0f}" if hi and hi != lo else "")
    if unit:
        txt += f" per {unit.lower()}"
    out.update(salary_min=lo, salary_max=hi, salary_currency=cur.upper(), salary_text=txt)
    return out


def parse_jsonld_jobposting(soup: BeautifulSoup) -> dict:
    """Return normalized fields from the first JobPosting JSON-LD block, or {}."""
    for script in soup.find_all("script", attrs={"type": re.compile("ld\\+json", re.I)}):
        raw = script.string or script.get_text() or ""
        raw = raw.strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            try:  # common breakage: raw newlines / trailing commas
                data = json.loads(re.sub(r",\s*([}\]])", r"\1", raw.replace("\n", " ")))
            except json.JSONDecodeError:
                continue
        for obj in _iter_jsonld_objects(data):
            if not _is_jobposting(obj):
                continue
            location, country = _address_parts(obj.get("jobLocation"))
            ident = obj.get("identifier")
            ident = _first(ident)
            if isinstance(ident, dict):
                ident = ident.get("value")
            out = {
                "title": htmllib.unescape(str(obj.get("title") or "")).strip(),
                "institution": htmllib.unescape(_name(obj.get("hiringOrganization"))),
                "description": html_to_text(str(obj.get("description") or "")),
                "posted_date": str(obj.get("datePosted") or "")[:10],
                "listing_expires": str(obj.get("validThrough") or "")[:10],
                "location": location,
                "country": country,
                "employment_type": ", ".join(obj["employmentType"]) if isinstance(obj.get("employmentType"), list)
                else str(obj.get("employmentType") or ""),
                "identifier": str(ident or ""),
                "url": str(obj.get("url") or ""),
            }
            out.update(_salary(obj.get("baseSalary") or obj.get("estimatedSalary")))
            return out
    return {}


# ---------------------------------------------------------------------------
# Labeled fields and main text
# ---------------------------------------------------------------------------

LABEL_MAP = {
    "institution": r"^(institution|employer|organi[sz]ation|company|university|school|hiring organi[sz]ation|recruiter|"
                   r"institution name|college)$",
    "department": r"^(department|division|unit|faculty|department/division|school/department|academic unit|college/school)$",
    "location": r"^(location|city|job location|address|campus|work location|city/state|state)$",
    "country": r"^(country|nation)$",
    "deadline": r"^(application deadline|deadline|closing date|closes|close date|apply by|applications? due|"
                r"review date|application due date|last date|expiry date|expires)$",
    "salary": r"^(salary|compensation|pay|salary range|remuneration|salary/pay|pay range)$",
    "posted_date": r"^(posted|date posted|posted on|placed on|published|date published|posting date|listed|start of posting)$",
    "categories": r"^(jel classifications?|jel codes?|categories|category|keywords?|subject areas?|disciplines?|fields?|"
                  r"research fields?|job category|job function|type|position type|job type|section|areas?)$",
    "title": r"^(title|position|job title|position title|rank)$",
    "start_date": r"^(start date|starting date|anticipated start date|appointment start)$",
}
_LABEL_RES = {k: re.compile(v, re.I) for k, v in LABEL_MAP.items()}


def _norm_label(label: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[:*]+\s*$", "", label or "")).strip()


def labeled_fields(soup: BeautifulSoup) -> dict[str, str]:
    """Collect 'Label: value' pairs into canonical keys (first occurrence wins)."""
    pairs: list[tuple[str, str]] = []
    for dt in soup.find_all("dt"):
        dd = dt.find_next_sibling("dd")
        if dd:
            pairs.append((dt.get_text(" "), dd.get_text(" ")))
    for tr in soup.find_all("tr"):
        cells = tr.find_all(["th", "td"], recursive=False)
        if len(cells) == 2:
            pairs.append((cells[0].get_text(" "), cells[1].get_text(" ")))
    for tag in soup.find_all(["strong", "b", "label", "span", "h4", "h5", "div"]):
        txt = tag.get_text(" ", strip=True)
        if not txt or len(txt) > 40 or not txt.endswith(":"):
            continue
        # value = text following the label within the parent block
        sib = tag.next_sibling
        val = ""
        while sib is not None and len(val) < 300:
            piece = sib.get_text(" ") if hasattr(sib, "get_text") else str(sib)
            val += piece
            if hasattr(sib, "name") and sib.name in ("br", "p", "div", "li"):
                break
            sib = sib.next_sibling
        if val.strip():
            pairs.append((txt, val))
    out: dict[str, str] = {}
    for label, value in pairs:
        label = _norm_label(clean_text(label))
        value = clean_text(value)
        if not label or not value or len(value) > 600:
            continue
        for key, rx in _LABEL_RES.items():
            if key not in out and rx.match(label):
                out[key] = value
                break
    return out


_MAIN_HINT = re.compile(r"job[-_ ]?(description|details?|body|content|ad|posting)|description|jobdesc|"
                        r"vacancy|listing[-_ ]?(body|text|content)|posting|article|main-content|content-main", re.I)


def main_text(soup: BeautifulSoup) -> str:
    """Best-effort main posting text with navigation and boilerplate removed."""
    soup = soupify(str(soup))  # work on a copy
    for tag in soup(["script", "style", "noscript", "nav", "header", "footer", "form", "iframe", "svg", "aside"]):
        tag.decompose()
    candidates = []
    for el in soup.find_all(["div", "section", "article", "main", "td"]):
        ident = " ".join([el.get("id") or "", " ".join(el.get("class") or [])])
        if _MAIN_HINT.search(ident):
            txt = el.get_text("\n")
            if len(txt) > 300:
                candidates.append(txt)
    if candidates:
        # the shortest block that is still substantial tends to be the posting itself
        candidates.sort(key=len)
        best = next((c for c in candidates if len(c) > 800), candidates[-1])
        return clean_text(best)
    main = soup.find("main") or soup.find("article") or soup.body or soup
    return clean_text(main.get_text("\n"))


def page_title(soup: BeautifulSoup) -> str:
    h1 = soup.find("h1")
    if h1 and 6 <= len(h1.get_text(strip=True)) <= 200:
        return clean_text(h1.get_text(" "))
    og = soup.find("meta", attrs={"property": "og:title"})
    raw = og["content"] if og and og.get("content") else (soup.title.get_text(" ") if soup.title else "")
    # "Assistant Professor of Finance | Some Job Board" → drop the site name
    return re.sub(r"\s+\|\s+[^|]{2,80}$", "", clean_text(raw))


def extract_posting(html: str | bytes, url: str = "") -> dict:
    """All generic fields we can pull from a posting page.

    Keys: title, institution, department, location, country, description,
    posted_date, listing_expires, deadline_raw, salary_*, categories,
    start_date_raw, closed_hint (True when the page says the job expired/filled).
    """
    soup = soupify(html)
    data = parse_jsonld_jobposting(soup)
    labels = labeled_fields(soup)
    text = main_text(soup)
    desc = data.get("description") or ""
    if len(desc) < 200 and len(text) > len(desc):
        desc = text
    out = {
        "title": data.get("title") or labels.get("title") or page_title(soup),
        "institution": data.get("institution") or labels.get("institution", ""),
        "department": labels.get("department", ""),
        "location": data.get("location") or labels.get("location", ""),
        "country": data.get("country") or labels.get("country", ""),
        "description": desc,
        "posted_date": data.get("posted_date") or labels.get("posted_date", ""),
        "listing_expires": data.get("listing_expires", ""),
        "deadline_raw": labels.get("deadline", ""),
        "salary_label": labels.get("salary", ""),
        "categories": labels.get("categories", ""),
        "start_date_raw": labels.get("start_date", ""),
        "employment_type": data.get("employment_type", ""),
        "identifier": data.get("identifier", ""),
        "has_jsonld": bool(data),
        "closed_hint": looks_closed(text[:4000]),
    }
    for k in ("salary_min", "salary_max", "salary_currency", "salary_text"):
        out[k] = data.get(k)
    return out
