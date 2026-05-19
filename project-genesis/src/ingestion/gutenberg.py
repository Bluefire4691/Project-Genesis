"""
Project Gutenberg fetcher — replaces Wikipedia as Genesis's primary reading source.

70,000+ public domain books: Darwin, Faraday, Huxley, Aristotle, Mill, Thoreau,
complete works, not summaries. When Genesis is curious about a topic, this finds
a relevant book and reads the next passage — then remembers where it left off.

Progressive reading:
    Genesis does not get one chunk and move on. It tracks its position in each
    book and continues from where it stopped on the next curiosity cycle. A book
    about evolution is not consumed in one sitting; Genesis returns to it over
    days and sessions, building understanding the way a reader does.

    Position is stored in data/reading_positions.json. Book text is cached in
    data/book_cache/ so each book is only downloaded once.

Requires network access to gutendex.com and gutenberg.org.
Fails gracefully (returns None) when offline — feeder falls back to corpus.
"""

import json
import os
import re
import time
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Optional

_GUTENDEX_API = "https://gutendex.com/books/"
_CHUNK_CHARS = 4000          # ~650 words per reading session
_MIN_BOOK_CHARS = 10_000     # ignore tiny texts
_REQUEST_TIMEOUT = 5   # per attempt for actual book fetches
_AVAILABILITY_TIMEOUT = 3  # quick probe — fail fast when offline
_RETRY_DELAY = 1

_HEADERS = {
    "User-Agent": (
        "ProjectGenesis/1.0 (educational AI research; "
        "reads public domain books from Project Gutenberg)"
    )
}

# Gutenberg book headers/footers to strip — the legalese before and after the text
_HEADER_RE = re.compile(
    r"\*\*\*\s*START OF (THE|THIS) PROJECT GUTENBERG.*?\*\*\*",
    re.IGNORECASE | re.DOTALL,
)
_FOOTER_RE = re.compile(
    r"\*\*\*\s*END OF (THE|THIS) PROJECT GUTENBERG.*",
    re.IGNORECASE | re.DOTALL,
)


def _fetch_url(url: str, timeout: int = _REQUEST_TIMEOUT,
               retries: int = 2) -> Optional[bytes]:
    """Fetch a URL with retries. Returns raw bytes or None."""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=_HEADERS)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception:
            if attempt < retries - 1:
                time.sleep(_RETRY_DELAY)
    return None


def _strip_gutenberg_boilerplate(text: str) -> str:
    """Remove Project Gutenberg header/footer legalese from book text."""
    # Remove header up to and including the START marker
    match = _HEADER_RE.search(text)
    if match:
        text = text[match.end():]
    # Remove footer from END marker onward
    match = _FOOTER_RE.search(text)
    if match:
        text = text[:match.start()]
    return text.strip()


class GutenbergFetcher:
    """
    Finds books on Project Gutenberg relevant to a curiosity topic and reads
    them progressively across sessions.

    Each book is fetched once and cached locally. Reading position is tracked
    per book so Genesis never re-reads the same passage.
    """

    def __init__(self, cache_dir: str = "data/book_cache",
                 positions_file: str = "data/reading_positions.json"):
        self._cache_dir = Path(cache_dir)
        self._positions_file = Path(positions_file)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._positions: dict[str, int] = self._load_positions()
        self._available: Optional[bool] = None  # None = not yet tested

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def fetch_for_topic(self, topic: str) -> tuple[Optional[str], Optional[str]]:
        """
        Find a book relevant to the topic and return the next unread passage.

        Returns (title, passage_text) or (None, None) if unavailable.
        """
        # Fast path: skip all network calls if we already know we're offline
        if self._available is False:
            return None, None

        book = self._find_book(topic)
        if not book:
            # Mark offline after a failed search so future calls are instant
            if self._available is None:
                self._available = False
            return None, None

        book_id = str(book["id"])
        title = book["title"]
        text_url = self._get_text_url(book)
        if not text_url:
            return None, None

        book_text = self._get_or_fetch_book(book_id, title, text_url)
        if not book_text:
            return None, None

        passage = self._next_passage(book_id, book_text)
        if not passage:
            return None, None

        return title, passage

    @property
    def available(self) -> bool:
        """Return True if gutendex.com is reachable. Cached after first probe."""
        if self._available is None:
            # Short single-attempt probe — fail fast when offline
            data = _fetch_url(_GUTENDEX_API + "?search=nature",
                              timeout=_AVAILABILITY_TIMEOUT, retries=1)
            self._available = data is not None
        return self._available

    def reading_status(self) -> dict:
        """Report how far Genesis has read in each cached book."""
        status = {}
        for book_id, pos in self._positions.items():
            cache_file = self._cache_dir / f"{book_id}.txt"
            if cache_file.exists():
                total = cache_file.stat().st_size
                pct = round(100 * pos / max(total, 1))
                status[book_id] = {"position": pos, "total": total,
                                   "percent_read": pct}
        return status

    # ------------------------------------------------------------------
    # Book discovery
    # ------------------------------------------------------------------

    def _find_book(self, topic: str) -> Optional[dict]:
        """
        Search gutendex for a book relevant to the topic.

        Prefers books where Genesis has already started reading (continuity).
        Otherwise picks the highest-download public domain text.
        """
        query = urllib.parse.quote(topic)
        data = _fetch_url(f"{_GUTENDEX_API}?search={query}&languages=en")
        if not data:
            return None

        try:
            results = json.loads(data).get("results", [])
        except Exception:
            return None

        if not results:
            return None

        # Prefer a book Genesis has already started
        for book in results:
            if str(book["id"]) in self._positions:
                return book

        # Otherwise take the first result that has a plain-text format
        for book in results:
            if self._get_text_url(book):
                return book

        return None

    def _get_text_url(self, book: dict) -> Optional[str]:
        """Extract the plain-text URL from a gutendex book record."""
        formats = book.get("formats", {})
        # Prefer UTF-8 plain text
        for mime in ("text/plain; charset=utf-8", "text/plain"):
            if mime in formats:
                return formats[mime]
        # Accept any text/plain variant
        for mime, url in formats.items():
            if "text/plain" in mime:
                return url
        return None

    # ------------------------------------------------------------------
    # Book caching
    # ------------------------------------------------------------------

    def _get_or_fetch_book(self, book_id: str, title: str,
                           text_url: str) -> Optional[str]:
        """Return book text from local cache, fetching and caching if needed."""
        cache_file = self._cache_dir / f"{book_id}.txt"

        if cache_file.exists():
            return cache_file.read_text(encoding="utf-8", errors="replace")

        raw = _fetch_url(text_url)
        if not raw:
            return None

        try:
            text = raw.decode("utf-8", errors="replace")
        except Exception:
            return None

        text = _strip_gutenberg_boilerplate(text)

        if len(text) < _MIN_BOOK_CHARS:
            return None

        cache_file.write_text(text, encoding="utf-8")
        return text

    # ------------------------------------------------------------------
    # Progressive reading
    # ------------------------------------------------------------------

    def _next_passage(self, book_id: str, book_text: str) -> Optional[str]:
        """
        Return the next unread passage from the book and advance the position.

        Finds a clean sentence boundary so Genesis doesn't start mid-sentence.
        When the book is exhausted, resets to the beginning (the book is worth
        re-reading — understanding deepens on second pass).
        """
        pos = self._positions.get(book_id, 0)
        total = len(book_text)

        if pos >= total:
            # Book finished — start over (second reading builds on first)
            pos = 0

        # Advance to next sentence boundary from current position
        end = min(pos + _CHUNK_CHARS, total)
        # Find clean end: next sentence boundary (. or \n\n) after end
        for boundary in (". ", ".\n", "\n\n"):
            idx = book_text.find(boundary, end)
            if idx != -1 and idx < end + 500:
                end = idx + len(boundary)
                break

        passage = book_text[pos:end].strip()
        if not passage:
            return None

        self._positions[book_id] = end
        self._save_positions()
        return passage

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load_positions(self) -> dict[str, int]:
        if self._positions_file.exists():
            try:
                return json.loads(self._positions_file.read_text())
            except Exception:
                pass
        return {}

    def _save_positions(self) -> None:
        try:
            self._positions_file.write_text(
                json.dumps(self._positions, indent=2)
            )
        except Exception:
            pass
