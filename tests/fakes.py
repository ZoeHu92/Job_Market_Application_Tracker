"""A fake Fetcher serving canned pages, so source adapters are tested without the network."""
from __future__ import annotations

from tracker.http import FetchError


class FakeResponse:
    def __init__(self, url: str, body: str | bytes, status: int = 200):
        self.url = url
        self.status_code = status
        self.content = body.encode() if isinstance(body, str) else body
        self.text = self.content.decode("utf-8", "replace")


class FakeFetcher:
    def __init__(self, pages: dict[str, str | tuple[int, str] | Exception]):
        self.pages = pages
        self.calls: list[str] = []
        self.requests_made = 0

    def get(self, url: str, **_):
        self.calls.append(url)
        self.requests_made += 1
        page = self.pages.get(url)
        if page is None:
            return FakeResponse(url, "not found", 404)
        if isinstance(page, Exception):
            raise page
        if isinstance(page, tuple):
            status, body = page
            if status >= 400 and status not in (404, 410):
                raise FetchError(url, f"HTTP {status}", status)
            return FakeResponse(url, body, status)
        return FakeResponse(url, page)
