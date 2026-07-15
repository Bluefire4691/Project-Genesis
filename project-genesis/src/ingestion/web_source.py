"""
WebSource — Web browsing source for the knowledge feeder.

Bridges GenesisBrowser with the curiosity-driven feeder pipeline.
Translates a curiosity topic into a search query, fetches the best
result, then follows the most relevant links for serendipitous discovery.

The serendipity loop:
  1. Form a query from the active topic + current working-memory concepts
  2. Search DuckDuckGo for candidate pages
  3. Fetch the best result (skip paywalls, skip too-short pages)
  4. Score all outgoing links against Genesis's current activation state
  5. Follow up to MAX_FOLLOW_LINKS high-scoring links
  6. Return all extracted text chunks for processing

The link-following in step 4-5 is where unexpected discovery happens:
Genesis is reading about wolf predator dynamics, sees a link to
"trophic cascade analogs in immune response", and follows it because
"immune" and "response" are adjacent to active concepts in its graph.
That's not a search query — it's a discovery.
"""

import os
import sys
from typing import TYPE_CHECKING

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ingestion.browser import GenesisBrowser

if TYPE_CHECKING:
    from orchestrator.orchestrator import Orchestrator


# Max extra links to follow per primary fetch.  Keep low — the feeder
# calls this per topic and we don't want a single topic to dominate a cycle.
_MAX_FOLLOW_LINKS = 2

# Minimum link score to follow (calibrated to avoid noise)
_FOLLOW_THRESHOLD = 1.5

# Minimum text length (chars) for a page to be considered useful
_MIN_TEXT_LEN = 250


class WebSource:
    """
    Web-based knowledge source: search → fetch → follow links.

    Integrates into KnowledgeFeeder as a source alongside WordNet,
    Gutenberg, and NLTK corpus.  Called from _fetch_and_process when
    other sources produce nothing, or for any topic in OPEN stage.
    """

    def __init__(self, brain: "Orchestrator", browser: GenesisBrowser):
        self._brain = brain
        self._browser = browser

    @property
    def available(self) -> bool:
        return self._browser.available

    @property
    def search_available(self) -> bool:
        return self._browser.search_available

    def fetch_for_topic(self, topic: str) -> list[tuple[str, str]]:
        """
        Search for topic, fetch best result, follow interesting links.

        Returns list of (source_label, text) tuples ready for feeder
        processing.  Empty list if nothing useful was found.
        """
        results: list[tuple[str, str]] = []

        query = self._build_query(topic)
        search_hits = self._browser.search(query, n=8)
        if not search_hits:
            return results

        active = self._active_concepts()
        followed_links: list[dict] = []

        # Try search results in order until we get useful content
        for hit in search_hits:
            url = hit.get("href", "")
            if not url:
                continue
            if self._browser.is_blocked(url):
                continue
            if self._browser.already_visited(url):
                continue
            page = self._browser.fetch(url)
            if page is None:
                continue
            if page.paywall_detected:
                # access request already queued inside browser.fetch()
                continue
            if page.text_length < _MIN_TEXT_LEN:
                continue
            label = f"Web: {page.title or page.source_domain}"
            results.append((label, page.text))
            followed_links = page.links
            break  # one primary page is enough; follow links for depth

        if not results:
            return results

        # Follow the highest-scoring outgoing links for serendipitous discovery
        if followed_links and active:
            scored = self._browser.score_links(followed_links, active)
            followed = 0
            for score, link in scored:
                if followed >= _MAX_FOLLOW_LINKS or score < _FOLLOW_THRESHOLD:
                    break
                url = link["href"]
                if self._browser.is_blocked(url):
                    continue
                if self._browser.already_visited(url):
                    continue
                page = self._browser.fetch(url)
                if page and page.is_useful:
                    label = f"Web (discovered): {page.title or page.source_domain}"
                    results.append((label, page.text))
                    followed += 1

        return results

    # ------------------------------------------------------------------
    # Query formation
    # ------------------------------------------------------------------

    def _build_query(self, topic: str) -> str:
        """
        Build a search query from the topic and current cognitive state.

        If the topic is already a natural question, use it directly.
        Otherwise append contextual terms from working memory to improve
        result quality — a search for "membrane" when Genesis has been
        thinking about "cell" and "nucleus" gets better biology results
        than a bare "membrane" search.
        """
        is_question = any(
            topic.lower().startswith(w)
            for w in ("what ", "how ", "why ", "when ", "where ", "which ")
        )
        if is_question:
            return topic

        # Add up to 2 active concepts as query context
        active = self._active_concepts()
        context = [c for c in sorted(active) if c not in topic.lower()][:2]
        if context:
            return f"{topic} {' '.join(context)} research"
        return f"{topic} research overview"

    # ------------------------------------------------------------------
    # Working memory interface
    # ------------------------------------------------------------------

    def _active_concepts(self) -> set[str]:
        """Concepts currently in Genesis's working memory (attention window)."""
        try:
            terms = self._brain.memory._working._context_terms
            if terms:
                return {t.lower() for t in terms[:16] if len(t) >= 4}
        except Exception:
            pass
        return set()
