"""
Tests for M8 — Education Data Expansion.

Verifies the expanded open-stage pool (56 → 130+ items) has:
- Correct structure (type + data fields in every item)
- Sufficient coverage per domain
- All 6 new M8 domains present
- No empty data values
- Expected distribution of types (text / numeric / pattern)
- Ethics items express consequences, not rules
- Philosophy items present
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

from curriculum.open_stage import _POOL, DataStream


# ------------------------------------------------------------------
# Pool structure
# ------------------------------------------------------------------

class TestPoolStructure:
    def test_pool_is_nonempty(self):
        assert len(_POOL) > 0

    def test_pool_significantly_expanded(self):
        """M8 expanded pool beyond the original 56; expect at least 100 items."""
        assert len(_POOL) >= 100

    def test_every_item_has_type(self):
        for item in _POOL:
            assert "type" in item, f"Missing 'type': {item}"

    def test_every_item_has_data(self):
        for item in _POOL:
            assert "data" in item, f"Missing 'data': {item}"

    def test_valid_types_only(self):
        valid = {"text", "numeric", "pattern"}
        for item in _POOL:
            assert item["type"] in valid, f"Unknown type: {item['type']}"

    def test_no_none_data(self):
        for item in _POOL:
            assert item["data"] is not None, f"None data in: {item}"

    def test_no_empty_string_data(self):
        for item in _POOL:
            if item["type"] == "text":
                assert item["data"].strip(), f"Empty text data: {item}"

    def test_numeric_items_have_label_and_values(self):
        numeric_items = [i for i in _POOL if i["type"] == "numeric"]
        assert len(numeric_items) > 0
        for item in numeric_items:
            d = item["data"]
            assert "label" in d, f"Numeric missing label: {d}"
            # Accept both "values" (list) and "value" (scalar) forms
            has_values = "values" in d or "value" in d
            assert has_values, f"Numeric missing value/values: {d}"
            if "values" in d:
                assert len(d["values"]) >= 3, f"Numeric too few values: {d}"

    def test_pattern_items_have_label_and_sequence(self):
        pattern_items = [i for i in _POOL if i["type"] == "pattern"]
        assert len(pattern_items) > 0
        for item in pattern_items:
            d = item["data"]
            assert "label" in d, f"Pattern missing label: {d}"
            assert "sequence" in d, f"Pattern missing sequence: {d}"
            assert len(d["sequence"]) >= 4, f"Pattern too short: {d}"

    def test_text_items_have_substance(self):
        """Text items should be at least one full sentence."""
        text_items = [i for i in _POOL if i["type"] == "text"]
        for item in text_items:
            assert len(item["data"]) >= 20, f"Text too short: {item['data']}"


# ------------------------------------------------------------------
# Type distribution
# ------------------------------------------------------------------

class TestTypeDistribution:
    def test_has_text_items(self):
        texts = [i for i in _POOL if i["type"] == "text"]
        assert len(texts) >= 60

    def test_has_numeric_items(self):
        numerics = [i for i in _POOL if i["type"] == "numeric"]
        assert len(numerics) >= 15

    def test_has_pattern_items(self):
        patterns = [i for i in _POOL if i["type"] == "pattern"]
        assert len(patterns) >= 10

    def test_text_is_majority(self):
        """Text should be the largest category."""
        texts = sum(1 for i in _POOL if i["type"] == "text")
        assert texts > len(_POOL) * 0.5


# ------------------------------------------------------------------
# Domain coverage (M8 new domains)
# ------------------------------------------------------------------

def _text_corpus() -> str:
    """Join all text data items into one corpus for keyword search."""
    return " ".join(
        item["data"] if item["type"] == "text" else
        item["data"].get("label", "") if item["type"] in ("numeric", "pattern") else ""
        for item in _POOL
    ).lower()


def _label_corpus() -> str:
    """Join all labels from numeric/pattern items."""
    return " ".join(
        item["data"].get("label", "")
        for item in _POOL
        if item["type"] in ("numeric", "pattern")
    ).lower()


class TestM8Domains:
    """Verify the 6 new M8 domains are present."""

    def test_history_causation_domain(self):
        corpus = _text_corpus()
        keywords = ["rome", "empire", "war", "revolution", "collapse",
                    "century", "trade", "empire", "conquered", "civilization"]
        assert any(kw in corpus for kw in keywords), \
            "No history/causation items found in pool"

    def test_science_fundamentals_domain(self):
        corpus = _text_corpus()
        keywords = ["entropy", "thermodynamics", "conservation", "energy",
                    "momentum", "gravity", "radiation", "pressure", "mass"]
        assert any(kw in corpus for kw in keywords), \
            "No science fundamentals items found in pool"

    def test_biology_genetics_domain(self):
        corpus = _text_corpus()
        keywords = ["dna", "gene", "mutation", "evolution", "inherit",
                    "chromosome", "cell", "protein", "neuron", "neural"]
        assert any(kw in corpus for kw in keywords), \
            "No biology/genetics items found in pool"

    def test_mathematics_logic_domain(self):
        corpus = _text_corpus()
        keywords = ["prime", "probability", "logic", "infinity", "theorem",
                    "implies", "set", "proof", "axiom", "paradox"]
        assert any(kw in corpus for kw in keywords), \
            "No mathematics/logic items found in pool"

    def test_ethics_as_narrative_domain(self):
        corpus = _text_corpus()
        # Ethics items are consequences-based stories; look for narrative keywords
        keywords = ["village", "starved", "commons", "exhausted",
                    "collapsed", "consequence", "trust", "punished",
                    "factory", "factory", "farmer", "farmer"]
        assert any(kw in corpus for kw in keywords), \
            "No ethics-as-narrative items found in pool"

    def test_philosophy_epistemology_domain(self):
        corpus = _text_corpus()
        keywords = ["model", "falsif", "belief", "knowledge", "observation",
                    "empirical", "hypothesis", "consciousness", "perception",
                    "map", "territory", "philosophy"]
        assert any(kw in corpus for kw in keywords), \
            "No philosophy/epistemology items found in pool"


# ------------------------------------------------------------------
# Ethics items: consequences, not rules
# ------------------------------------------------------------------

class TestEthicsAsNarrative:
    """Ethics items should describe events and consequences, not declare rules."""

    def _ethics_items(self):
        """Heuristic: ethics items mention social/moral consequences."""
        ethics_keywords = {
            "starved", "collapsed", "died", "punished", "consequence",
            "village", "commons", "exhausted", "trusted", "betrayed",
            "factory", "workers", "farmer", "neighbor", "community",
        }
        return [
            item for item in _POOL
            if item["type"] == "text"
            and any(kw in item["data"].lower() for kw in ethics_keywords)
        ]

    def test_ethics_items_exist(self):
        assert len(self._ethics_items()) >= 5, \
            "Expected at least 5 ethics-as-narrative items"

    def test_ethics_items_are_not_rules(self):
        """Ethics items must not contain 'you should', 'you must', 'it is wrong'."""
        rule_phrases = ["you should", "you must", "it is wrong", "it is right",
                        "never do", "always do", "moral duty", "thou shalt"]
        for item in self._ethics_items():
            text = item["data"].lower()
            for phrase in rule_phrases:
                assert phrase not in text, \
                    f"Ethics item contains rule phrase '{phrase}': {item['data'][:80]}"

    def test_ethics_items_describe_events(self):
        """Each ethics item should have at least one past-tense verb (event narration)."""
        past_tense_signals = [
            "ed ", "happened", "starved", "collapsed", "died",
            "exhausted", "trusted", "betrayed", "built", "spread"
        ]
        for item in self._ethics_items():
            text = item["data"].lower()
            has_event = any(sig in text for sig in past_tense_signals)
            assert has_event, \
                f"Ethics item lacks past-tense narration: {item['data'][:80]}"


# ------------------------------------------------------------------
# DataStream
# ------------------------------------------------------------------

class TestDataStream:
    def test_stream_creates(self):
        stream = DataStream(shuffle=False)
        assert stream is not None

    def test_stream_pool_size_matches_pool(self):
        stream = DataStream(shuffle=False)
        assert stream.pool_size == len(_POOL)

    def test_stream_next_returns_valid_item(self):
        stream = DataStream(shuffle=False)
        item = stream.next()
        assert "type" in item
        assert "data" in item

    def test_stream_loops(self):
        """DataStream should loop — can produce more items than pool size."""
        stream = DataStream(shuffle=False)
        items = [stream.next() for _ in range(len(_POOL) + 5)]
        assert len(items) == len(_POOL) + 5

    def test_stream_stats_has_pool_composition(self):
        stream = DataStream(shuffle=False)
        stats = stream.stats()
        assert "pool_composition" in stats

    def test_shuffle_produces_different_order(self):
        """Two shuffled streams should (very likely) differ in first 10 items."""
        s1 = DataStream(shuffle=True)
        s2 = DataStream(shuffle=True)
        items1 = [s1.next()["data"] for _ in range(min(20, len(_POOL)))]
        items2 = [s2.next()["data"] for _ in range(min(20, len(_POOL)))]
        # With 120+ items, collision probability is astronomically low
        assert items1 != items2 or len(_POOL) <= 1
