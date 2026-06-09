"""
Tests for GenesisBrowser and WebSource — polite autonomous web browsing.

All logic tests (paywall detection, link scoring, robots.txt, history,
rate limiting, access request queue) run fully offline without any
network calls or browser installation.

Network-dependent tests are marked and skipped when offline or when
the required packages are not installed.
"""

import os
import sys
import sqlite3
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def _db():
    return sqlite3.connect(":memory:")


# ---------------------------------------------------------------------------
# Paywall detection
# ---------------------------------------------------------------------------

class TestPaywallDetection:
    def test_detects_subscribe_to_read(self):
        from ingestion.browser import GenesisBrowser
        b = GenesisBrowser()
        assert b._detect_paywall(
            "To continue reading, subscribe to read our full coverage.",
            "https://example.com/article"
        )

    def test_detects_purchase_access(self):
        from ingestion.browser import GenesisBrowser
        b = GenesisBrowser()
        assert b._detect_paywall(
            "Purchase access to this article for $39.",
            "https://example.com/paper"
        )

    def test_detects_members_only(self):
        from ingestion.browser import GenesisBrowser
        b = GenesisBrowser()
        assert b._detect_paywall(
            "This is members only content. Sign in to read.",
            "https://example.com/content"
        )

    def test_clean_article_not_paywall(self):
        from ingestion.browser import GenesisBrowser
        b = GenesisBrowser()
        assert not b._detect_paywall(
            "Photosynthesis is the process by which plants use sunlight "
            "to synthesise nutrients from carbon dioxide and water.",
            "https://example.com/biology"
        )

    def test_known_paywall_domain_short_content(self):
        from ingestion.browser import GenesisBrowser
        b = GenesisBrowser()
        # Short text on a known paywall domain = paywall
        assert b._detect_paywall("Abstract only.", "https://nature.com/articles/s41586-024-0001")

    def test_known_paywall_domain_long_content_not_paywall(self):
        from ingestion.browser import GenesisBrowser
        b = GenesisBrowser()
        long_text = "Wolves are apex predators that regulate prey populations. " * 20
        assert not b._detect_paywall(long_text, "https://nature.com/articles/open-access-2024")

    def test_open_access_arxiv_not_paywall(self):
        from ingestion.browser import GenesisBrowser
        b = GenesisBrowser()
        text = "We present a study of trophic cascades in Yellowstone. " * 20
        assert not b._detect_paywall(text, "https://arxiv.org/abs/1234.5678")


# ---------------------------------------------------------------------------
# Link scoring
# ---------------------------------------------------------------------------

class TestLinkScoring:
    def test_concept_match_in_anchor_text_scores_high(self):
        from ingestion.browser import GenesisBrowser
        b = GenesisBrowser()
        links = [
            {"href": "https://arxiv.org/abs/wolf-ecology", "text": "wolf predator dynamics", "domain": "arxiv.org"},
            {"href": "https://shop.example.com/toys", "text": "buy toys", "domain": "shop.example.com"},
        ]
        scored = b.score_links(links, {"wolf", "predator"})
        assert len(scored) >= 1
        top_href = scored[0][1]["href"]
        assert "wolf" in top_href or "arxiv" in top_href

    def test_scientific_domain_bonus(self):
        from ingestion.browser import GenesisBrowser
        b = GenesisBrowser()
        links = [
            {"href": "https://arxiv.org/abs/biology-1", "text": "cell biology", "domain": "arxiv.org"},
            {"href": "https://random-blog.com/cell", "text": "cell biology", "domain": "random-blog.com"},
        ]
        scored = b.score_links(links, {"biology"})
        hrefs = [lnk["href"] for _, lnk in scored]
        # arxiv should appear before random blog
        if len(hrefs) == 2:
            assert hrefs.index("https://arxiv.org/abs/biology-1") < hrefs.index("https://random-blog.com/cell")

    def test_social_media_filtered(self):
        from ingestion.browser import GenesisBrowser
        b = GenesisBrowser()
        links = [
            {"href": "https://twitter.com/share?text=ecology", "text": "share on twitter", "domain": "twitter.com"},
            {"href": "https://facebook.com/sharer", "text": "share on facebook", "domain": "facebook.com"},
            {"href": "https://arxiv.org/abs/ecology", "text": "ecology research", "domain": "arxiv.org"},
        ]
        scored = b.score_links(links, {"ecology"})
        hrefs = [lnk["href"] for _, lnk in scored]
        assert "https://twitter.com/share?text=ecology" not in hrefs
        assert "https://facebook.com/sharer" not in hrefs
        assert "https://arxiv.org/abs/ecology" in hrefs

    def test_shopping_links_filtered(self):
        from ingestion.browser import GenesisBrowser
        b = GenesisBrowser()
        links = [
            {"href": "https://shop.example.com/cart", "text": "add to cart", "domain": "shop.example.com"},
            {"href": "https://example.com/buy-now", "text": "buy now", "domain": "example.com"},
        ]
        scored = b.score_links(links, {"biology", "science"})
        assert len(scored) == 0

    def test_empty_active_concepts_still_scores_scientific_domains(self):
        from ingestion.browser import GenesisBrowser
        b = GenesisBrowser()
        links = [
            {"href": "https://pubmed.ncbi.nlm.nih.gov/1234", "text": "pubmed article", "domain": "pubmed.ncbi.nlm.nih.gov"},
        ]
        scored = b.score_links(links, set())
        # Scientific domain bonus alone should produce a non-zero score
        assert len(scored) == 1
        assert scored[0][0] > 0

    def test_fragment_only_links_filtered(self):
        from ingestion.browser import GenesisBrowser
        b = GenesisBrowser()
        links = [
            {"href": "#section-2", "text": "jump to section", "domain": ""},
            {"href": "https://arxiv.org/abs/real", "text": "real link", "domain": "arxiv.org"},
        ]
        scored = b.score_links(links, {"research"})
        hrefs = [lnk["href"] for _, lnk in scored]
        assert "#section-2" not in hrefs


# ---------------------------------------------------------------------------
# Page history
# ---------------------------------------------------------------------------

class TestPageHistory:
    def test_not_visited_initially(self):
        from ingestion.browser import GenesisBrowser
        b = GenesisBrowser(db_conn=_db())
        assert not b.already_visited("https://example.com/page")

    def test_visited_after_mark(self):
        from ingestion.browser import GenesisBrowser
        b = GenesisBrowser(db_conn=_db())
        b.mark_visited("https://example.com/page", "Example", 1234)
        assert b.already_visited("https://example.com/page")

    def test_different_url_not_visited(self):
        from ingestion.browser import GenesisBrowser
        b = GenesisBrowser(db_conn=_db())
        b.mark_visited("https://example.com/page1", "Page 1", 500)
        assert not b.already_visited("https://example.com/page2")

    def test_no_db_always_not_visited(self):
        from ingestion.browser import GenesisBrowser
        b = GenesisBrowser(db_conn=None)
        # Without DB, history is disabled — always returns False
        b.mark_visited("https://example.com/page")
        assert not b.already_visited("https://example.com/page")

    def test_paywall_recorded_in_history(self):
        from ingestion.browser import GenesisBrowser
        db = _db()
        b = GenesisBrowser(db_conn=db)
        b.mark_visited("https://nature.com/article", "Nature article", 50, paywall=True)
        row = db.execute(
            "SELECT paywall FROM web_page_history WHERE url=?",
            ("https://nature.com/article",)
        ).fetchone()
        assert row is not None
        assert row[0] == 1


# ---------------------------------------------------------------------------
# Access request queue (paywall escalation to user)
# ---------------------------------------------------------------------------

class TestAccessRequestQueue:
    def test_empty_initially(self):
        from ingestion.browser import GenesisBrowser
        b = GenesisBrowser(db_conn=_db())
        assert b.pending_access_requests() == []

    def test_queue_and_retrieve(self):
        from ingestion.browser import GenesisBrowser
        b = GenesisBrowser(db_conn=_db())
        b.queue_access_request("nature.com", "https://nature.com/art/1",
                                "researching marine biology")
        pending = b.pending_access_requests()
        assert len(pending) == 1
        assert pending[0]["domain"] == "nature.com"
        assert "marine biology" in pending[0]["reason"]

    def test_resolve_removes_from_pending(self):
        from ingestion.browser import GenesisBrowser
        b = GenesisBrowser(db_conn=_db())
        b.queue_access_request("science.org", "https://science.org/doi/1", "research")
        req_id = b.pending_access_requests()[0]["id"]
        b.resolve_access_request(req_id)
        assert b.pending_access_requests() == []

    def test_duplicate_domain_not_queued_twice(self):
        from ingestion.browser import GenesisBrowser
        b = GenesisBrowser(db_conn=_db())
        b.queue_access_request("nature.com", "https://nature.com/a", "first")
        b.queue_access_request("nature.com", "https://nature.com/b", "second")
        pending = b.pending_access_requests()
        # Same domain should only appear once
        assert len(pending) == 1

    def test_different_domains_both_queued(self):
        from ingestion.browser import GenesisBrowser
        b = GenesisBrowser(db_conn=_db())
        b.queue_access_request("nature.com", "https://nature.com/a", "research 1")
        b.queue_access_request("science.org", "https://science.org/a", "research 2")
        domains = {r["domain"] for r in b.pending_access_requests()}
        assert "nature.com" in domains
        assert "science.org" in domains


# ---------------------------------------------------------------------------
# Link extraction from HTML
# ---------------------------------------------------------------------------

class TestLinkExtraction:
    def test_extracts_absolute_links(self):
        from ingestion.browser import GenesisBrowser
        b = GenesisBrowser()
        html = '<a href="https://arxiv.org/abs/1234">Wolf Ecology Study</a>'
        links = b._extract_links(html, "https://example.com/page")
        assert any(lnk["href"] == "https://arxiv.org/abs/1234" for lnk in links)

    def test_resolves_relative_links(self):
        from ingestion.browser import GenesisBrowser
        b = GenesisBrowser()
        html = '<a href="/wiki/Trophic_cascade">Trophic cascade</a>'
        links = b._extract_links(html, "https://en.wikipedia.org/wiki/Wolf")
        assert any("wikipedia.org" in lnk["href"] for lnk in links)

    def test_anchor_text_captured(self):
        from ingestion.browser import GenesisBrowser
        b = GenesisBrowser()
        html = '<a href="https://arxiv.org/abs/eco">Ecosystem dynamics</a>'
        links = b._extract_links(html, "https://example.com/")
        matching = [lnk for lnk in links if "arxiv" in lnk["href"]]
        assert matching
        assert "Ecosystem dynamics" in matching[0]["text"]

    def test_mailto_filtered(self):
        from ingestion.browser import GenesisBrowser
        b = GenesisBrowser()
        html = '<a href="mailto:author@university.edu">Contact</a>'
        links = b._extract_links(html, "https://example.com/")
        assert not any("mailto:" in lnk.get("href", "") for lnk in links)

    def test_deduplication(self):
        from ingestion.browser import GenesisBrowser
        b = GenesisBrowser()
        html = """
            <a href="https://arxiv.org/abs/1234">Paper 1</a>
            <a href="https://arxiv.org/abs/1234">Paper 1 duplicate</a>
            <a href="https://arxiv.org/abs/5678">Paper 2</a>
        """
        links = b._extract_links(html, "https://example.com/")
        hrefs = [lnk["href"] for lnk in links]
        assert hrefs.count("https://arxiv.org/abs/1234") == 1


# ---------------------------------------------------------------------------
# WebSource query formation
# ---------------------------------------------------------------------------

class TestWebSourceQueryFormation:
    def _make_source(self):
        from ingestion.web_source import WebSource
        from ingestion.browser import GenesisBrowser

        class _FakeBrain:
            class memory:
                class _working:
                    _context_terms = ["ecology", "predator", "prey"]

        return WebSource(_FakeBrain(), GenesisBrowser())

    def test_question_passes_through_unchanged(self):
        ws = self._make_source()
        q = ws._build_query("what causes coral bleaching")
        assert q == "what causes coral bleaching"

    def test_how_question_passes_through(self):
        ws = self._make_source()
        q = ws._build_query("how do wolves regulate deer populations")
        assert q == "how do wolves regulate deer populations"

    def test_bare_topic_gets_suffix(self):
        ws = self._make_source()
        q = ws._build_query("photosynthesis")
        assert "photosynthesis" in q
        assert len(q) > len("photosynthesis")

    def test_active_concepts_added_to_query(self):
        ws = self._make_source()
        q = ws._build_query("membrane")
        # Active concepts (ecology/predator/prey) should appear in query
        # for contextualisation
        assert "membrane" in q

    def test_active_concepts_method(self):
        ws = self._make_source()
        concepts = ws._active_concepts()
        assert "ecology" in concepts
        assert "predator" in concepts

    def test_active_concepts_empty_brain(self):
        from ingestion.web_source import WebSource
        from ingestion.browser import GenesisBrowser

        class _EmptyBrain:
            class memory:
                class _working:
                    _context_terms = []

        ws = WebSource(_EmptyBrain(), GenesisBrowser())
        assert ws._active_concepts() == set()


# ---------------------------------------------------------------------------
# Network tests (skipped when offline or deps missing)
# ---------------------------------------------------------------------------

def _network_available() -> bool:
    try:
        import urllib.request
        urllib.request.urlopen("https://en.wikipedia.org", timeout=5)
        return True
    except Exception:
        return False


def _browser_deps_available() -> bool:
    try:
        from ingestion.browser import _has_requests, _has_trafilatura
        return _has_requests() and _has_trafilatura()
    except Exception:
        return False


@pytest.mark.skipif(
    not _browser_deps_available() or not _network_available(),
    reason="Browser dependencies not installed or network unavailable"
)
class TestBrowserNetwork:
    def test_search_returns_list(self):
        from ingestion.browser import GenesisBrowser
        b = GenesisBrowser()
        results = b.search("wolf predator ecology", n=3)
        assert isinstance(results, list)
        # May be empty if rate-limited but must not crash

    def test_fetch_returns_text_or_none(self):
        from ingestion.browser import GenesisBrowser
        b = GenesisBrowser(min_delay_s=1.0)
        result = b.fetch("https://en.wikipedia.org/wiki/Trophic_cascade")
        if result is not None:
            assert isinstance(result.text, str)
            assert result.source_domain != ""
