"""Polite HTTP fetching: identifies itself, honours robots.txt, rate-limits per host."""
from __future__ import annotations

import logging
import time
import urllib.robotparser
from urllib.parse import urlparse

import requests

log = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (compatible; AcademicJobTracker/0.1; personal weekly job-market tracker; "
    "+https://github.com/ZoeHu92/Job_Market_Application_Tracker)"
)
ROBOTS_AGENT = "AcademicJobTracker"


class FetchError(Exception):
    def __init__(self, url: str, reason: str, status: int | None = None):
        super().__init__(f"{reason} ({url})")
        self.url = url
        self.reason = reason
        self.status = status


class Fetcher:
    """requests.Session wrapper with per-host delay, retries and robots.txt checks."""

    def __init__(self, delay: float = 1.5, timeout: float = 30, retries: int = 2,
                 respect_robots: bool = True, user_agent: str = USER_AGENT):
        self.delay = delay
        self.timeout = timeout
        self.retries = retries
        self.respect_robots = respect_robots
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json;q=0.8,*/*;q=0.7",
            "Accept-Language": "en-US,en;q=0.9",
        })
        self._last: dict[str, float] = {}
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self.requests_made = 0

    def _host(self, url: str) -> str:
        p = urlparse(url)
        return f"{p.scheme}://{p.netloc}"

    def allowed(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        host = self._host(url)
        if host not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                r = self.session.get(host + "/robots.txt", timeout=self.timeout)
                if r.status_code == 200:
                    rp.parse(r.text.splitlines())
                    self._robots[host] = rp
                else:
                    self._robots[host] = None  # no robots.txt → everything allowed
            except requests.RequestException:
                self._robots[host] = None
        rp = self._robots[host]
        return True if rp is None else rp.can_fetch(ROBOTS_AGENT, url)

    def _wait(self, url: str) -> None:
        host = self._host(url)
        elapsed = time.monotonic() - self._last.get(host, 0)
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last[host] = time.monotonic()

    def get(self, url: str, **kwargs) -> requests.Response:
        """GET a URL or raise FetchError. 404/410 are returned (callers treat them as 'gone')."""
        if not self.allowed(url):
            raise FetchError(url, "disallowed by robots.txt")
        last_exc: Exception | None = None
        for attempt in range(self.retries + 1):
            self._wait(url)
            try:
                self.requests_made += 1
                r = self.session.get(url, timeout=self.timeout, **kwargs)
            except requests.RequestException as exc:
                last_exc = exc
                time.sleep(2 * (attempt + 1))
                continue
            if r.status_code in (429, 500, 502, 503, 504) and attempt < self.retries:
                time.sleep(float(r.headers.get("Retry-After", 0) or 0) or 4 * (attempt + 1))
                continue
            if r.status_code in (404, 410):
                return r
            if r.status_code >= 400:
                hint = ""
                if r.status_code in (401, 403) and ("cloudflare" in r.text.lower() or "captcha" in r.text.lower()):
                    hint = " (blocked by bot protection)"
                raise FetchError(url, f"HTTP {r.status_code}{hint}", r.status_code)
            return r
        raise FetchError(url, f"network error: {last_exc!r}"[:300])
