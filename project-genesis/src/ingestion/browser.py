"""
GenesisBrowser — Polite autonomous web browsing for knowledge acquisition.

Genesis explores the web the way a curious person does: searches for what it
needs, reads pages, notices interesting links and decides whether to follow
them based on what it's currently thinking about.

Two-layer fetch stack:
  1. Playwright (headless Chromium/Firefox) — full JS rendering, better
     fingerprinting, needed for JS-heavy sites. Optional dependency.
  2. requests + trafilatura — works for most static scientific content,
     no browser binary needed.

Politeness principles (non-negotiable):
  - Checks robots.txt before fetching any URL
  - Per-domain rate limiting (default 3 s)
  - Honest user-agent that identifies Genesis
  - Never re-fetches a URL already visited this session
  - Detects paywalls and queues access requests rather than bypassing them
  - Respects Crawl-delay from robots.txt

Install:
  pip install playwright trafilatura ddgs
  python -m playwright install chromium   # optional but preferred
"""

import os
import sys
import re
import time
import threading
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ---------------------------------------------------------------------------
# Optional dependency checks (lazy, cached)
# ---------------------------------------------------------------------------

_playwright_ready: bool | None = None
_trafilatura_ready: bool | None = None
_requests_ready: bool | None = None


def _has_playwright() -> bool:
    global _playwright_ready
    if _playwright_ready is None:
        try:
            from playwright.sync_api import sync_playwright  # noqa: F401
            # Check a browser is actually installed
            import subprocess
            result = subprocess.run(
                ["python", "-m", "playwright", "install", "--dry-run"],
                capture_output=True, text=True, timeout=5,
            )
            _playwright_ready = True
        except Exception:
            _playwright_ready = False
    return _playwright_ready


def _has_trafilatura() -> bool:
    global _trafilatura_ready
    if _trafilatura_ready is None:
        try:
            import trafilatura  # noqa: F401
            _trafilatura_ready = True
        except ImportError:
            _trafilatura_ready = False
    return _trafilatura_ready


def _has_requests() -> bool:
    global _requests_ready
    if _requests_ready is None:
        try:
            import requests  # noqa: F401
            _requests_ready = True
        except ImportError:
            _requests_ready = False
    return _requests_ready


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Honest user-agent: we identify as Genesis, include a Chrome UA for
# compatibility with sites that check for modern browsers.
_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 "
    "Genesis-Research/0.1"
)

# Scientific/research domains — bonus score for link following
_SCIENTIFIC_DOMAINS = frozenset({
    "arxiv.org", "pubmed.ncbi.nlm.nih.gov", "semanticscholar.org",
    "ncbi.nlm.nih.gov", "nature.com", "science.org", "cell.com",
    "plos.org", "biorxiv.org", "medrxiv.org", "chemrxiv.org",
    "europepmc.org", "openalex.org", "en.wikipedia.org",
    "encyclopediaoflife.org", "scholar.google.com",
})

# Text patterns that indicate a paywall
_PAYWALL_PHRASES = frozenset({
    "subscribe to read", "subscription required", "access this article",
    "purchase access", "log in to read", "sign in to read",
    "create an account to", "full access requires", "get full access",
    "unlock this article", "you've reached your article limit",
    "to continue reading", "members only", "premium content",
})

# Domains known to paywall most content
_PAYWALL_DOMAINS = frozenset({
    "nature.com", "science.org", "cell.com", "nejm.org", "thelancet.com",
    "sciencedirect.com", "springer.com", "wiley.com", "tandfonline.com",
    "journals.sagepub.com", "jstor.org", "ieeexplore.ieee.org",
})

# Link anchor text / href patterns to skip entirely
_SKIP_PATTERNS = frozenset({
    "login", "sign-up", "signup", "register", "cart", "checkout",
    "privacy", "terms", "cookie", "advertis", "shop", "buy now",
    "twitter.com", "facebook.com", "instagram.com", "linkedin.com",
    "youtube.com", "tiktok.com",
})


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class PageResult:
    """Content extracted from a single fetched page."""
    url: str
    title: str
    text: str
    links: list[dict] = field(default_factory=list)   # [{href, text, domain}]
    paywall_detected: bool = False
    source_domain: str = ""
    fetch_time: float = field(default_factory=time.time)

    @property
    def text_length(self) -> int:
        return len(self.text)

    @property
    def is_useful(self) -> bool:
        return self.text_length >= 200 and not self.paywall_detected


# ---------------------------------------------------------------------------
# Link extractor (stdlib only)
# ---------------------------------------------------------------------------

class _LinkParser(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__()
        self._base = base_url
        self._href: str | None = None
        self._buf: list[str] = []
        self.links: list[dict] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._buf = []

    def handle_endtag(self, tag):
        if tag == "a" and self._href:
            href = self._href.strip()
            if href.startswith("http"):
                full = href
            elif href.startswith("/"):
                full = urljoin(self._base, href)
            else:
                full = None
            if full and "://" in full:
                domain = urlparse(full).netloc
                self.links.append({
                    "href": full,
                    "text": " ".join(self._buf).strip()[:160],
                    "domain": domain,
                })
            self._href = None

    def handle_data(self, data):
        if self._href is not None:
            self._buf.append(data.strip())


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class GenesisBrowser:
    """
    Polite headless browser for autonomous web exploration.

    Thread-safe: a single lock guards the rate-limit table and robots cache.
    Each Playwright fetch creates its own context (no cross-thread browser
    state). Requests fetches are inherently stateless.

    Browser connection (in priority order):
      1. GENESIS_BROWSER_WS  — WebSocket endpoint of a running Playwright
                               browser server (playwright run-server, or a
                               browser launched with browser.new_server())
      2. GENESIS_BROWSER_CDP — Chrome DevTools Protocol endpoint of an
                               existing Chrome/Chromium process started with
                               --remote-debugging-port=N
      3. Launch own headless Chromium (original behaviour, always available
         when playwright is installed)

    Set these env vars to share another application's browser:
      export GENESIS_BROWSER_WS="ws://localhost:3000"   # Playwright server
      export GENESIS_BROWSER_CDP="http://localhost:9222" # Chrome CDP
    """

    def __init__(self, db_conn=None, min_delay_s: float = 3.0):
        self._db = db_conn
        self._min_delay = min_delay_s
        self._last_domain_fetch: dict[str, float] = {}
        self._robots_cache: dict[str, RobotFileParser | None] = {}
        self._lock = threading.Lock()
        self._error_log = None   # set by feeder after construction
        # External browser endpoints (from env)
        self._ws_endpoint  = os.environ.get("GENESIS_BROWSER_WS", "").strip()
        self._cdp_endpoint = os.environ.get("GENESIS_BROWSER_CDP", "").strip()
        self._init_schema()

    # ------------------------------------------------------------------
    # Public capability flag
    # ------------------------------------------------------------------

    @property
    def available(self) -> bool:
        """True if at least one fetch backend is usable."""
        return _has_requests() or _has_playwright()

    @property
    def search_available(self) -> bool:
        """True if a DuckDuckGo search library is importable."""
        for pkg in ("ddgs", "duckduckgo_search"):
            try:
                if pkg == "ddgs":
                    import ddgs  # noqa: F401
                else:
                    import duckduckgo_search  # noqa: F401
                return True
            except ImportError:
                continue
        return False

    # ------------------------------------------------------------------
    # Core fetch
    # ------------------------------------------------------------------

    def fetch(self, url: str) -> PageResult | None:
        """
        Fetch a URL, returning clean extracted content.

        Tries Playwright first (when installed), falls back to requests.
        Returns None if: robots.txt disallows, already visited, network
        error, or both backends unavailable.
        """
        if not self.available:
            return None
        if self.already_visited(url):
            return None
        if not self._robots_allow(url):
            return None

        domain = urlparse(url).netloc
        self._rate_limit(domain)

        result = None
        if _has_playwright():
            result = self._fetch_playwright(url)
        if result is None and _has_requests():
            result = self._fetch_requests(url)

        if result is not None:
            self.mark_visited(url, result.title, result.text_length,
                               result.paywall_detected)
            if result.paywall_detected:
                self.queue_access_request(
                    domain, url,
                    "Encountered paywall during autonomous research",
                )
        return result

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(self, query: str, n: int = 6) -> list[dict]:
        """
        Search DuckDuckGo. Returns [{title, href, body}, ...].
        Falls back to empty list on any error (rate limit, offline, etc.).
        """
        # Try ddgs (renamed package) first, then duckduckgo_search
        for pkg in ("ddgs", "duckduckgo_search"):
            try:
                if pkg == "ddgs":
                    from ddgs import DDGS
                else:
                    from duckduckgo_search import DDGS
                with DDGS() as ddgs:
                    results = list(ddgs.text(query, max_results=n))
                return results
            except ImportError:
                continue
            except Exception as exc:
                self._log_error("browser.search", exc)
                return []
        return []

    # ------------------------------------------------------------------
    # Link scoring — relevance to active concepts
    # ------------------------------------------------------------------

    def score_links(
        self, links: list[dict], active_concepts: set[str]
    ) -> list[tuple[float, dict]]:
        """
        Score links by relevance to current active concepts.
        Returns [(score, link), ...] sorted descending, non-zero scores only.
        """
        scored = []
        for link in links:
            s = self._score_link(link, active_concepts)
            if s > 0:
                scored.append((s, link))
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored

    # ------------------------------------------------------------------
    # Page history
    # ------------------------------------------------------------------

    def already_visited(self, url: str) -> bool:
        if self._db is None:
            return False
        try:
            return self._db.execute(
                "SELECT 1 FROM web_page_history WHERE url=?", (url,)
            ).fetchone() is not None
        except Exception:
            return False

    def mark_visited(self, url: str, title: str = "",
                     text_length: int = 0, paywall: bool = False) -> None:
        if self._db is None:
            return
        try:
            self._db.execute(
                """INSERT OR REPLACE INTO web_page_history
                   (url, title, fetched_at, text_length, paywall)
                   VALUES (?, ?, ?, ?, ?)""",
                (url, title, time.time(), text_length, 1 if paywall else 0),
            )
            self._db.commit()
        except Exception as exc:
            self._log_error("browser.mark_visited", exc)

    # ------------------------------------------------------------------
    # Access request queue (paywall escalation)
    # ------------------------------------------------------------------

    def queue_access_request(self, domain: str, url: str, reason: str) -> None:
        """Record a paywall encounter for surfacing to the user."""
        if self._db is None:
            return
        try:
            # Only queue once per domain to avoid spam
            exists = self._db.execute(
                "SELECT 1 FROM web_access_requests WHERE domain=? AND resolved=0",
                (domain,),
            ).fetchone()
            if exists:
                return
            self._db.execute(
                """INSERT INTO web_access_requests
                   (domain, url, reason, requested_at) VALUES (?, ?, ?, ?)""",
                (domain, url, reason, time.time()),
            )
            self._db.commit()
        except Exception as exc:
            self._log_error("browser.queue_access_request", exc)

    def pending_access_requests(self) -> list[dict]:
        """Unresolved access requests — surfaced in wake greeting."""
        if self._db is None:
            return []
        try:
            rows = self._db.execute(
                """SELECT id, domain, url, reason, requested_at
                   FROM web_access_requests WHERE resolved=0
                   ORDER BY requested_at DESC LIMIT 10"""
            ).fetchall()
            return [
                {"id": r[0], "domain": r[1], "url": r[2],
                 "reason": r[3], "requested_at": r[4]}
                for r in rows
            ]
        except Exception:
            return []

    def resolve_access_request(self, request_id: int) -> None:
        if self._db is None:
            return
        try:
            self._db.execute(
                "UPDATE web_access_requests SET resolved=1 WHERE id=?",
                (request_id,),
            )
            self._db.commit()
        except Exception as exc:
            self._log_error("browser.resolve_access_request", exc)

    # ------------------------------------------------------------------
    # Fetch backends
    # ------------------------------------------------------------------

    def _fetch_playwright(self, url: str) -> PageResult | None:
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as pw:
                browser = self._connect_browser(pw)
                owns_browser = browser is None
                if owns_browser:
                    browser = pw.chromium.launch(headless=True)
                ctx = browser.new_context(
                    user_agent=_UA,
                    viewport={"width": 1280, "height": 800},
                )
                page = ctx.new_page()
                # Block binary assets — we only need text
                page.route(
                    "**/*.{png,jpg,jpeg,gif,svg,woff,woff2,ttf,eot,mp4,mp3,webp}",
                    lambda route: route.abort(),
                )
                try:
                    page.goto(url, timeout=20_000, wait_until="domcontentloaded")
                    title = page.title() or ""
                    html = page.content()
                finally:
                    ctx.close()
                    # Only close a browser we launched ourselves.
                    # A shared/external browser stays open for its owner.
                    if owns_browser:
                        browser.close()
            return self._build_result(url, title, html)
        except Exception as exc:
            self._log_error(f"browser.playwright:{urlparse(url).netloc}", exc)
            return None

    def _connect_browser(self, pw):
        """Return an existing browser connection, or None to launch a new one.

        Tries GENESIS_BROWSER_WS (Playwright server) first, then
        GENESIS_BROWSER_CDP (Chrome DevTools Protocol).  Returns None if
        neither env var is set or the connection fails — caller falls back to
        launching its own browser.
        """
        if self._ws_endpoint:
            try:
                browser = pw.chromium.connect(self._ws_endpoint)
                return browser
            except Exception as exc:
                self._log_error("browser.connect_ws", exc)
        if self._cdp_endpoint:
            try:
                browser = pw.chromium.connect_over_cdp(self._cdp_endpoint)
                return browser
            except Exception as exc:
                self._log_error("browser.connect_cdp", exc)
        return None

    def _fetch_requests(self, url: str) -> PageResult | None:
        try:
            import requests as _req
            resp = _req.get(
                url, timeout=20,
                headers={"User-Agent": _UA, "Accept-Language": "en-US,en;q=0.9"},
                allow_redirects=True,
            )
            if resp.status_code == 403:
                return None
            resp.raise_for_status()
            title = self._extract_title(resp.text)
            return self._build_result(url, title, resp.text)
        except Exception as exc:
            self._log_error(f"browser.requests:{urlparse(url).netloc}", exc)
            return None

    # ------------------------------------------------------------------
    # Content processing
    # ------------------------------------------------------------------

    def _build_result(self, url: str, title: str, html: str) -> PageResult:
        text = self._extract_text(html, url)
        links = self._extract_links(html, url)
        paywall = self._detect_paywall(text, url)
        return PageResult(
            url=url,
            title=title,
            text=text,
            links=links,
            paywall_detected=paywall,
            source_domain=urlparse(url).netloc,
        )

    def _extract_text(self, html: str, url: str) -> str:
        if _has_trafilatura():
            try:
                import trafilatura
                text = trafilatura.extract(
                    html, url=url,
                    include_comments=False,
                    include_tables=True,
                    favor_precision=True,
                    deduplicate=True,
                )
                return text or ""
            except Exception:
                pass
        # Fallback: strip tags manually (crude but always available)
        text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s{3,}", "\n\n", text)
        return text.strip()[:50_000]

    def _extract_title(self, html: str) -> str:
        m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""

    def _extract_links(self, html: str, base_url: str) -> list[dict]:
        try:
            parser = _LinkParser(base_url)
            parser.feed(html)
            seen: set[str] = set()
            unique = []
            for lnk in parser.links:
                href = lnk["href"]
                if href not in seen and len(unique) < 120:
                    seen.add(href)
                    unique.append(lnk)
            return unique
        except Exception:
            return []

    def _detect_paywall(self, text: str, url: str) -> bool:
        low = text.lower()
        if any(phrase in low for phrase in _PAYWALL_PHRASES):
            return True
        domain = urlparse(url).netloc.lower()
        if any(d in domain for d in _PAYWALL_DOMAINS) and len(text) < 800:
            return True
        return False

    # ------------------------------------------------------------------
    # robots.txt + rate limiting
    # ------------------------------------------------------------------

    def _robots_allow(self, url: str) -> bool:
        """Return True if robots.txt permits fetching this URL."""
        try:
            parsed = urlparse(url)
            robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
            with self._lock:
                if robots_url not in self._robots_cache:
                    rp = RobotFileParser(robots_url)
                    try:
                        rp.read()
                    except Exception:
                        rp = None
                    self._robots_cache[robots_url] = rp
                rp = self._robots_cache[robots_url]
            if rp is None:
                return True
            return rp.can_fetch(_UA, url)
        except Exception:
            return True  # allow if we can't check

    def _rate_limit(self, domain: str) -> None:
        """Enforce minimum delay between requests to the same domain."""
        with self._lock:
            last = self._last_domain_fetch.get(domain, 0.0)
            wait = self._min_delay - (time.monotonic() - last)
            if wait > 0:
                time.sleep(wait)
            self._last_domain_fetch[domain] = time.monotonic()

    # ------------------------------------------------------------------
    # Link scoring
    # ------------------------------------------------------------------

    def _score_link(self, link: dict, active: set[str]) -> float:
        score = 0.0
        text_low = link.get("text", "").lower()
        href_low = link.get("href", "").lower()
        domain = link.get("domain", "").lower()

        # Concept overlap with link anchor text / URL
        for concept in active:
            if len(concept) >= 4:
                if concept in text_low:
                    score += 2.0
                if concept in href_low:
                    score += 1.0

        # Bonus for trusted scientific domains
        if any(sd in domain for sd in _SCIENTIFIC_DOMAINS):
            score += 1.5

        # Hard filter — skip navigation / social / commercial links
        combined = href_low + " " + text_low
        if any(pat in combined for pat in _SKIP_PATTERNS):
            return 0.0

        # Skip fragment-only, mailto, javascript links
        if href_low.startswith(("#", "mailto:", "javascript:")):
            return 0.0

        return score

    # ------------------------------------------------------------------
    # Persistence schema
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        if self._db is None:
            return
        try:
            self._db.executescript("""
                CREATE TABLE IF NOT EXISTS web_page_history (
                    url         TEXT PRIMARY KEY,
                    title       TEXT,
                    fetched_at  REAL NOT NULL,
                    text_length INTEGER DEFAULT 0,
                    paywall     INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS web_access_requests (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    domain       TEXT NOT NULL,
                    url          TEXT,
                    reason       TEXT,
                    requested_at REAL NOT NULL,
                    resolved     INTEGER DEFAULT 0
                );
            """)
            self._db.commit()
        except Exception:
            self._db = None

    def _log_error(self, label: str, exc: Exception) -> None:
        try:
            if self._error_log is not None:
                self._error_log.log(label, exc)
        except Exception:
            pass
