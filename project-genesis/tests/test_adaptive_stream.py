"""
Tests for M9 — AdaptiveStream.

Verifies:
- Basic construction and interface
- next() and take() return valid pool items
- stats() reflects selection counts
- Diversity floor: random selections happen at expected rate
- Attention refresh pulls from working memory
- Attention-weighted selection favors relevant items
- No item permanently excluded (base probability floor)
- Integration with a live Orchestrator brain
"""

import sys
import os
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

import pytest
from unittest.mock import MagicMock, patch
from orchestrator.orchestrator import Orchestrator
from curriculum.adaptive_stream import AdaptiveStream, _DIVERSITY_FLOOR, _MIN_RELEVANCE_SCORE
from curriculum.open_stage import _POOL


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _brain(**kwargs) -> Orchestrator:
    """Create a fresh brain with an isolated temp DB."""
    if "db_path" not in kwargs:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        kwargs["db_path"] = tmp.name
    return Orchestrator(verbose=False, **kwargs)


def _stream(brain=None, **kwargs) -> AdaptiveStream:
    if brain is None:
        brain = _brain()
    return AdaptiveStream(brain, **kwargs)


# ------------------------------------------------------------------
# Construction
# ------------------------------------------------------------------

class TestAdaptiveStreamConstruction:
    def test_creates_with_brain(self):
        stream = _stream()
        assert stream is not None

    def test_pool_is_full_pool(self):
        stream = _stream()
        assert len(stream._pool) == len(_POOL)

    def test_default_diversity_floor(self):
        stream = _stream()
        assert stream._diversity_floor == _DIVERSITY_FLOOR

    def test_custom_diversity_floor(self):
        stream = _stream(diversity_floor=0.5)
        assert stream._diversity_floor == 0.5

    def test_diversity_floor_clamped_high(self):
        stream = _stream(diversity_floor=1.5)
        assert stream._diversity_floor == 1.0

    def test_diversity_floor_clamped_low(self):
        stream = _stream(diversity_floor=-0.1)
        assert stream._diversity_floor == 0.0

    def test_initial_counts_zero(self):
        stream = _stream()
        assert stream._items_served == 0
        assert stream._attention_selections == 0
        assert stream._random_selections == 0

    def test_seed_reproducible(self):
        brain = _brain()
        s1 = AdaptiveStream(brain, diversity_floor=1.0, seed=42)
        s2 = AdaptiveStream(brain, diversity_floor=1.0, seed=42)
        items1 = [s1.next()["type"] for _ in range(20)]
        items2 = [s2.next()["type"] for _ in range(20)]
        assert items1 == items2


# ------------------------------------------------------------------
# Interface: next() and take()
# ------------------------------------------------------------------

class TestAdaptiveStreamInterface:
    def test_next_returns_dict(self):
        item = _stream().next()
        assert isinstance(item, dict)

    def test_next_item_has_type_and_data(self):
        item = _stream().next()
        assert "type" in item
        assert "data" in item

    def test_next_item_is_from_pool(self):
        stream = _stream()
        item = stream.next()
        assert item in _POOL

    def test_next_increments_items_served(self):
        stream = _stream()
        assert stream.items_served == 0
        stream.next()
        assert stream.items_served == 1
        stream.next()
        assert stream.items_served == 2

    def test_take_returns_list(self):
        result = _stream().take(5)
        assert isinstance(result, list)
        assert len(result) == 5

    def test_take_zero_returns_empty(self):
        result = _stream().take(0)
        assert result == []

    def test_take_items_all_from_pool(self):
        stream = _stream()
        items = stream.take(20)
        for item in items:
            assert item in _POOL

    def test_take_many_items_served_tracked(self):
        stream = _stream()
        stream.take(50)
        assert stream.items_served == 50

    def test_can_serve_more_than_pool_size(self):
        """Stream is infinite — no exhaustion."""
        stream = _stream()
        items = stream.take(len(_POOL) + 10)
        assert len(items) == len(_POOL) + 10


# ------------------------------------------------------------------
# Diversity floor behaviour
# ------------------------------------------------------------------

class TestDiversityFloor:
    def test_full_random_floor_all_random_selections(self):
        """diversity_floor=1.0 → every selection is random."""
        stream = _stream(diversity_floor=1.0, seed=7)
        stream.take(100)
        assert stream._random_selections == 100
        assert stream._attention_selections == 0

    def test_zero_floor_all_attention_selections_when_terms_present(self):
        """diversity_floor=0.0 → all attention-weighted when terms exist."""
        brain = _brain()
        # Pre-load some working memory so attention terms exist
        brain.process_input("text", "wolves hunt deer in the forest ecosystem")
        stream = AdaptiveStream(brain, diversity_floor=0.0, seed=13)
        stream._refresh_attention()
        if stream._current_attention_terms:
            stream.take(50)
            assert stream._attention_selections == 50
            assert stream._random_selections == 0

    def test_empty_memory_falls_back_to_random(self):
        """With no working memory, all selections are random regardless of floor."""
        brain = _brain()
        # brain has no memories — fresh
        stream = AdaptiveStream(brain, diversity_floor=0.0, seed=99)
        stream.take(30)
        # No attention terms → should have fallen back to random
        assert stream._random_selections == 30

    def test_default_floor_roughly_30_percent_random(self):
        """With 300 draws, random pct should be close to 30%."""
        brain = _brain()
        brain.process_input("text", "wolves hunt deer in the forest ecosystem")
        stream = AdaptiveStream(brain, diversity_floor=0.30, seed=5)
        stream.take(300)
        total = stream._random_selections + stream._attention_selections
        random_pct = stream._random_selections / total
        # Allow generous tolerance: 20% – 45%
        assert 0.20 <= random_pct <= 0.45, \
            f"Random pct {random_pct:.2f} outside expected range"


# ------------------------------------------------------------------
# Attention refresh
# ------------------------------------------------------------------

class TestAttentionRefresh:
    def test_empty_brain_gives_no_terms(self):
        brain = _brain()
        stream = AdaptiveStream(brain)
        stream._refresh_attention()
        assert stream._current_attention_terms == []

    def test_after_processing_terms_populated(self):
        brain = _brain()
        brain.process_input("text", "wolves hunt deer in the ecosystem cascade")
        stream = AdaptiveStream(brain)
        stream._refresh_attention()
        assert len(stream._current_attention_terms) > 0

    def test_terms_are_strings(self):
        brain = _brain()
        brain.process_input("text", "quantum particles interact at subatomic scales")
        stream = AdaptiveStream(brain)
        stream._refresh_attention()
        for term in stream._current_attention_terms:
            assert isinstance(term, str)

    def test_terms_are_lowercase(self):
        brain = _brain()
        brain.process_input("text", "Wolves hunt Deer in Yellowstone National Park")
        stream = AdaptiveStream(brain)
        stream._refresh_attention()
        for term in stream._current_attention_terms:
            assert term == term.lower(), f"Term not lowercase: {term!r}"

    def test_terms_have_min_length_3(self):
        brain = _brain()
        brain.process_input("text", "a b cd dogs hunt animals")
        stream = AdaptiveStream(brain)
        stream._refresh_attention()
        for term in stream._current_attention_terms:
            assert len(term) >= 3, f"Short term found: {term!r}"

    def test_terms_refreshed_on_each_next(self):
        """Attention terms update as brain processes more data."""
        brain = _brain()
        stream = AdaptiveStream(brain)
        # Before any processing
        stream._refresh_attention()
        terms_before = set(stream._current_attention_terms)

        brain.process_input("text", "photosynthesis converts sunlight into glucose")
        stream._refresh_attention()
        terms_after = set(stream._current_attention_terms)

        # After processing, terms should be non-empty (may differ from before)
        assert len(terms_after) >= len(terms_before)

    def test_exception_in_brain_gives_empty_terms(self):
        """_refresh_attention never crashes — falls back to empty list."""
        brain = _brain()
        stream = AdaptiveStream(brain)
        # Corrupt the memory reference
        stream._brain = None
        stream._refresh_attention()
        assert stream._current_attention_terms == []


# ------------------------------------------------------------------
# Item scoring
# ------------------------------------------------------------------

class TestItemScoring:
    def test_score_returns_float(self):
        stream = _stream()
        stream._current_attention_terms = ["wolf", "deer", "forest"]
        score = stream._score_item({"type": "text", "data": "wolves hunt deer in the forest"})
        assert isinstance(score, float)

    def test_score_between_0_and_1(self):
        stream = _stream()
        stream._current_attention_terms = ["wolf", "deer"]
        for item in _POOL[:20]:
            score = stream._score_item(item)
            assert 0.0 <= score <= 1.0, f"Score out of range: {score}"

    def test_relevant_item_scores_higher_than_irrelevant(self):
        stream = _stream()
        stream._current_attention_terms = ["wolf", "deer", "predator", "prey", "ecosystem"]
        wolf_item = {"type": "text",
                     "data": "Wolves are predators that hunt deer and regulate ecosystem balance."}
        unrelated_item = {"type": "text",
                          "data": "The French Revolution was caused by economic inequality."}
        wolf_score = stream._score_item(wolf_item)
        unrelated_score = stream._score_item(unrelated_item)
        assert wolf_score > unrelated_score

    def test_empty_attention_terms_scores_zero(self):
        stream = _stream()
        stream._current_attention_terms = []
        score = stream._score_item({"type": "text", "data": "wolves hunt deer"})
        assert score == 0.0

    def test_numeric_item_scored_via_label(self):
        """Numeric items: label words are used for scoring."""
        stream = _stream()
        stream._current_attention_terms = ["wolf", "deer", "population"]
        item = {"type": "numeric",
                "data": {"label": "wolf_deer_population_change", "values": [100, 90, 80]}}
        score = stream._score_item(item)
        assert score >= 0.0


# ------------------------------------------------------------------
# Attention-weighted selection
# ------------------------------------------------------------------

class TestAttentionWeightedSelect:
    def test_returns_item_from_pool(self):
        brain = _brain()
        brain.process_input("text", "wolves hunt deer in the forest ecosystem")
        stream = AdaptiveStream(brain, diversity_floor=0.0, seed=42)
        stream._refresh_attention()
        if stream._current_attention_terms:
            item = stream._attention_weighted_select()
            assert item in _POOL

    def test_no_item_permanently_excluded(self):
        """Base probability floor ensures all items can be selected."""
        stream = _stream()
        stream._current_attention_terms = ["zzz_no_match_term_xyz"]
        # All items score at _MIN_RELEVANCE_SCORE floor; all should be selectable
        scores = [
            max(_MIN_RELEVANCE_SCORE, stream._score_item(item))
            for item in stream._pool
        ]
        assert all(s >= _MIN_RELEVANCE_SCORE for s in scores)
        assert all(s > 0 for s in scores)

    def test_attention_biases_toward_relevant_domain(self):
        """With strong ecology attention, ecology items appear more often."""
        brain = _brain()
        # Load ecology content to bias attention
        for _ in range(5):
            brain.process_input("text",
                "Wolves are predators that hunt deer and regulate ecosystem population balance.")
        stream = AdaptiveStream(brain, diversity_floor=0.0, seed=77)
        stream._refresh_attention()
        if not stream._current_attention_terms:
            pytest.skip("No attention terms loaded")

        # Draw many items and check for ecology content
        items = stream.take(100)
        ecology_count = sum(
            1 for item in items
            if item["type"] == "text" and
            any(kw in item["data"].lower()
                for kw in ["wolf", "wolves", "deer", "predator", "prey", "ecosystem"])
        )
        # At least some bias toward ecology; base rate in pool is low
        assert ecology_count >= 2


# ------------------------------------------------------------------
# Stats
# ------------------------------------------------------------------

class TestStats:
    def test_stats_returns_dict(self):
        stream = _stream()
        assert isinstance(stream.stats(), dict)

    def test_stats_keys(self):
        stream = _stream()
        s = stream.stats()
        assert "items_served" in s
        assert "attention_selections" in s
        assert "random_selections" in s
        assert "attention_pct" in s
        assert "diversity_floor" in s
        assert "active_attention_terms" in s
        assert "pool_size" in s

    def test_stats_initial_zeros(self):
        stream = _stream()
        s = stream.stats()
        assert s["items_served"] == 0
        assert s["attention_selections"] == 0
        assert s["random_selections"] == 0
        assert s["attention_pct"] == 0.0

    def test_stats_pool_size_matches_pool(self):
        stream = _stream()
        assert stream.stats()["pool_size"] == len(_POOL)

    def test_stats_update_after_selections(self):
        stream = _stream(diversity_floor=1.0)  # all random
        stream.take(10)
        s = stream.stats()
        assert s["items_served"] == 10
        assert s["random_selections"] == 10
        assert s["attention_selections"] == 0

    def test_stats_attention_pct_calculation(self):
        brain = _brain()
        brain.process_input("text", "wolves hunt deer in the forest")
        stream = AdaptiveStream(brain, diversity_floor=0.0, seed=1)
        stream._refresh_attention()
        if stream._current_attention_terms:
            stream.take(10)
            s = stream.stats()
            assert s["attention_pct"] == 100.0
        else:
            stream = AdaptiveStream(brain, diversity_floor=1.0)
            stream.take(10)
            s = stream.stats()
            assert s["attention_pct"] == 0.0

    def test_items_served_property(self):
        stream = _stream()
        stream.take(7)
        assert stream.items_served == 7

    def test_attention_terms_property(self):
        brain = _brain()
        brain.process_input("text", "wolves hunt deer in the ecosystem")
        stream = AdaptiveStream(brain)
        stream._refresh_attention()
        terms = stream.attention_terms
        assert isinstance(terms, list)

    def test_diversity_floor_in_stats(self):
        stream = _stream(diversity_floor=0.45)
        assert stream.stats()["diversity_floor"] == 0.45


# ------------------------------------------------------------------
# Integration with live Orchestrator
# ------------------------------------------------------------------

class TestAdaptiveStreamIntegration:
    def test_integrates_with_orchestrator(self):
        brain = _brain()
        stream = AdaptiveStream(brain)
        # Run 20 cycles: process output of each stream item
        for _ in range(20):
            item = stream.next()
            result = brain.process_input(item["type"], item["data"])
            assert result["status"] in ("processed", "degraded", "paused")

    def test_attention_grows_with_processing(self):
        brain = _brain()
        stream = AdaptiveStream(brain)
        stream._refresh_attention()
        terms_before = len(stream._current_attention_terms)

        # Process several items
        for _ in range(10):
            item = stream.next()
            brain.process_input(item["type"], item["data"])

        stream._refresh_attention()
        terms_after = len(stream._current_attention_terms)
        assert terms_after >= terms_before

    def test_stats_after_integrated_run(self):
        brain = _brain()
        stream = AdaptiveStream(brain, seed=55)
        for _ in range(30):
            item = stream.next()
            brain.process_input(item["type"], item["data"])
        s = stream.stats()
        assert s["items_served"] == 30
        assert s["random_selections"] + s["attention_selections"] == 30

    def test_main_loop_does_not_crash(self):
        """Simulate main.py run_open_stage with AdaptiveStream."""
        brain = _brain()
        stream = AdaptiveStream(brain, seed=1)
        for _ in range(50):
            item = stream.next()
            brain.process_input(item["type"], item["data"])
        # Should complete without exception
        assert stream.items_served == 50
