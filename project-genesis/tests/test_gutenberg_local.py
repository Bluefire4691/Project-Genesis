"""
Tests for the local Gutenberg reference library — the offline paths only.

These never touch the network. They verify that once a book is on disk it is
discoverable and readable with zero network calls, that the library index
persists, and that a transient network failure triggers a cooldown rather than
a permanent session-wide offline latch (the cause of "always falls back to
WordNet").
"""
import os
import sys
import json
import tempfile
import shutil

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ingestion.gutenberg import GutenbergFetcher, _OFFLINE_COOLDOWN


def _fetcher_with_book(topic="wolf", book_id="555", title="The Wolf Book"):
    """Create a fetcher whose local cache already contains one book."""
    tmp = tempfile.mkdtemp()
    cache_dir = os.path.join(tmp, "book_cache")
    os.makedirs(cache_dir)
    # A long-enough fake book with VARIED content so successive passages differ
    body = " ".join(
        f"Wolves hunt deer in region {i}. Deer eat grass near site {i}."
        for i in range(800)
    )
    with open(os.path.join(cache_dir, f"{book_id}.txt"), "w") as f:
        f.write(body)
    f_index = os.path.join(tmp, "book_index.json")
    with open(f_index, "w") as fh:
        json.dump({book_id: {"title": title, "topics": [topic]}}, fh)
    g = GutenbergFetcher(
        cache_dir=cache_dir,
        positions_file=os.path.join(tmp, "positions.json"),
        index_file=f_index,
    )
    return g, tmp, book_id, title


class TestCacheFirst:
    def test_cached_book_served_without_network(self):
        g, tmp, book_id, title = _fetcher_with_book()
        try:
            # Force "network down" — if it tried the net, this would fail.
            g._available = False
            g._last_probe_failed_at = 1.0  # in cooldown
            got_title, passage = g.fetch_for_topic("wolf")
            assert passage is not None and len(passage) > 0
            assert got_title == title
            assert "wolves" in passage.lower()
        finally:
            shutil.rmtree(tmp)

    def test_local_find_matches_recorded_topic(self):
        g, tmp, book_id, title = _fetcher_with_book(topic="ecology")
        try:
            found = g._find_book_local("ecology")
            assert found is not None
            assert found[0] == book_id
        finally:
            shutil.rmtree(tmp)

    def test_local_find_matches_title_word(self):
        g, tmp, book_id, title = _fetcher_with_book(topic="wolf", title="Nature Studies")
        try:
            found = g._find_book_local("nature")
            assert found is not None and found[0] == book_id
        finally:
            shutil.rmtree(tmp)

    def test_progressive_reading_advances(self):
        g, tmp, book_id, _ = _fetcher_with_book()
        try:
            g._available = False
            g._last_probe_failed_at = 1.0
            _, p1 = g.fetch_for_topic("wolf")
            _, p2 = g.fetch_for_topic("wolf")
            # Two reads should advance position (different passages)
            assert g._positions[book_id] > 0
            assert p1 != p2
        finally:
            shutil.rmtree(tmp)


class TestLibraryIndex:
    def test_record_topic_persists(self):
        g, tmp, book_id, _ = _fetcher_with_book()
        try:
            g._record_topic(book_id, "The Wolf Book", "predator")
            # New fetcher on same files should see the added topic
            g2 = GutenbergFetcher(
                cache_dir=str(g._cache_dir),
                positions_file=str(g._positions_file),
                index_file=str(g._index_file),
            )
            assert "predator" in g2._index[book_id]["topics"]
        finally:
            shutil.rmtree(tmp)

    def test_library_reports_cached_books(self):
        g, tmp, book_id, title = _fetcher_with_book()
        try:
            lib = g.library()
            assert any(b["book_id"] == book_id and b["cached"] for b in lib)
        finally:
            shutil.rmtree(tmp)


class TestOfflineCooldown:
    def test_failure_does_not_latch_forever(self):
        g, tmp, _, _ = _fetcher_with_book()
        try:
            g._note_network_failure()
            assert g._available is False
            assert not g._network_ok()  # in cooldown now
            # Simulate cooldown elapsing
            g._last_probe_failed_at = (
                g._last_probe_failed_at - _OFFLINE_COOLDOWN - 1
            )
            assert g._network_ok(), (
                "Network stayed disabled past the cooldown — one failure "
                "should not permanently disable book fetching."
            )
        finally:
            shutil.rmtree(tmp)
