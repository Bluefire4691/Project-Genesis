"""
Wikipedia Fetcher — Ingestion Pipeline.

Fetches article text from Wikipedia using the public REST API.
No API key required. No external dependencies — urllib is stdlib.

Rate-limits automatically (1 request/second) to respect Wikipedia's
terms of service. Uses a descriptive User-Agent as required.
"""

import json
import time
import urllib.request
import urllib.parse
import urllib.error
from typing import Optional


_USER_AGENT = "ProjectGenesis/1.0 (developmental-ai; educational)"
_RATE_LIMIT_S = 1.2  # seconds between requests


class WikipediaFetcher:
    """
    Fetches plain-text article content from Wikipedia.

    Usage:
        fetcher = WikipediaFetcher()
        title, text = fetcher.fetch("gray wolf")
        # text is plain prose, ready for TextProcessor
    """

    def __init__(self, language: str = "en"):
        self._lang = language
        self._base = f"https://{language}.wikipedia.org"
        self._last_request: float = 0.0
        self._total_fetched: int = 0
        self._failed: int = 0

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def fetch(self, topic: str) -> tuple[str, str]:
        """
        Fetch a Wikipedia article by topic.

        Searches first to find the canonical title, then fetches full text.
        Returns (canonical_title, plain_text). Returns ("", "") on failure.
        """
        # Search for best-matching title
        title = self._search(topic)
        if not title:
            self._failed += 1
            return "", ""

        # Fetch full article text
        text = self._fetch_extract(title)
        if not text:
            # Fall back to summary
            text = self._fetch_summary(title)

        if text:
            self._total_fetched += 1
            return title, text
        else:
            self._failed += 1
            return "", ""

    def fetch_summary(self, topic: str) -> tuple[str, str]:
        """
        Fetch only the summary section (2-3 paragraphs).
        Faster than fetch(); good for initial concept seeding.
        """
        title = self._search(topic)
        if not title:
            self._failed += 1
            return "", ""
        text = self._fetch_summary(title)
        if text:
            self._total_fetched += 1
            return title, text
        self._failed += 1
        return "", ""

    def stats(self) -> dict:
        return {
            "total_fetched": self._total_fetched,
            "failed": self._failed,
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _rate_limit(self):
        """Ensure at least _RATE_LIMIT_S seconds between requests."""
        elapsed = time.monotonic() - self._last_request
        if elapsed < _RATE_LIMIT_S:
            time.sleep(_RATE_LIMIT_S - elapsed)
        self._last_request = time.monotonic()

    def _get(self, url: str) -> Optional[dict]:
        """Make a GET request, return parsed JSON or None on failure."""
        self._rate_limit()
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": _USER_AGENT, "Accept": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception:
            return None

    def _search(self, query: str) -> str:
        """Return the best-matching Wikipedia article title for a query."""
        encoded = urllib.parse.quote(query)
        url = (
            f"{self._base}/w/api.php"
            f"?action=opensearch&search={encoded}&limit=3&format=json&redirects=resolve"
        )
        data = self._get(url)
        if not data or len(data) < 2 or not data[1]:
            return ""
        return data[1][0]  # First result title

    def _fetch_summary(self, title: str) -> str:
        """Fetch the REST summary endpoint (intro paragraphs, plain text)."""
        encoded = urllib.parse.quote(title.replace(" ", "_"))
        url = f"{self._base}/api/rest_v1/page/summary/{encoded}"
        data = self._get(url)
        if not data:
            return ""
        return data.get("extract", "")

    def _fetch_extract(self, title: str) -> str:
        """Fetch the full article extract via MediaWiki API (plain text)."""
        encoded = urllib.parse.quote(title)
        url = (
            f"{self._base}/w/api.php"
            f"?action=query&prop=extracts&exintro=false&explaintext=true"
            f"&titles={encoded}&format=json&redirects=1"
        )
        data = self._get(url)
        if not data:
            return ""
        try:
            pages = data["query"]["pages"]
            page = next(iter(pages.values()))
            return page.get("extract", "")
        except Exception:
            return ""
