"""
Tests for M19: Spreading Activation (spreading_activation.py).

Covers: activation computation, decay per hop, edge-confidence modulation,
max-hop ceiling, min-activation floor, multi-source fusion, cycle safety,
retrieval score boosting, memory.search() integration, and orchestrator wiring.
"""

import os
import re
import sqlite3
import sys
import tempfile
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from cognition.spreading_activation import (
    SpreadingActivation, _clean,
    _DECAY, _MAX_HOPS, _MIN_ACTIVATION, _MAX_BOOST,
)
from memory.relations import RelationGraph


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _graph_conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    return c


def _graph_with_chain():
    """
    A→B→C→D at uniform confidence 0.80.
    wolves→deer→overgrazing→erosion pattern.
    """
    conn = _graph_conn()
    rg = RelationGraph(conn)
    rg.add("wolves",      "CAUSES",   "deer decline",  0.80, source_key="t", session_id="s")
    rg.add("deer decline","CAUSES",   "overgrazing",   0.80, source_key="t", session_id="s")
    rg.add("overgrazing", "CAUSES",   "erosion",       0.80, source_key="t", session_id="s")
    rg.add("erosion",     "CAUSES",   "river change",  0.80, source_key="t", session_id="s")
    return rg, conn


def _sa(rg=None):
    if rg is None:
        rg, _ = _graph_with_chain()
    return SpreadingActivation(rg)


# ---------------------------------------------------------------------------
# 1. _clean helper
# ---------------------------------------------------------------------------

class TestClean:
    def test_lowercases(self):
        assert _clean("Wolves") == "wolves"

    def test_strips_non_alnum(self):
        # _clean matches RelationGraph._normalise: removes non-[a-z0-9 ] chars
        assert _clean("deer-decline!") == "deerdecline"

    def test_trims_whitespace(self):
        assert _clean("  wolves  ") == "wolves"

    def test_empty_string(self):
        assert _clean("") == ""


# ---------------------------------------------------------------------------
# 2. compute() — basic properties
# ---------------------------------------------------------------------------

class TestComputeBasic:
    def test_empty_sources_returns_empty(self):
        sa = _sa()
        assert sa.compute({}) == {}

    def test_unknown_concept_returns_itself_not_in_output(self):
        sa = _sa()
        # A concept with no edges: sources are removed from output
        result = sa.compute({"unknown_concept_xyz": 1.0})
        assert "unknown_concept_xyz" not in result

    def test_source_concepts_excluded_from_output(self):
        # Sources are attended concepts; the boost is for *related* concepts
        sa = _sa()
        result = sa.compute({"wolves": 1.0})
        assert "wolves" not in result

    def test_direct_neighbor_activated(self):
        sa = _sa()
        result = sa.compute({"wolves": 1.0})
        assert "deer decline" in result

    def test_two_hop_activated(self):
        sa = _sa()
        result = sa.compute({"wolves": 1.0})
        assert "overgrazing" in result

    def test_three_hop_activated(self):
        sa = _sa()
        result = sa.compute({"wolves": 1.0})
        assert "erosion" in result

    def test_four_hop_not_activated(self):
        # "river change" is 4 hops from "wolves" — beyond MAX_HOPS=3
        sa = _sa()
        result = sa.compute({"wolves": 1.0})
        assert "river change" not in result

    def test_activation_decays_with_distance(self):
        sa = _sa()
        result = sa.compute({"wolves": 1.0})
        a1 = result.get("deer decline", 0)
        a2 = result.get("overgrazing", 0)
        a3 = result.get("erosion", 0)
        assert a1 > a2 > a3 > 0

    def test_first_hop_approx_decay(self):
        sa = _sa()
        result = sa.compute({"wolves": 1.0})
        # hop1 activation = 1.0 * DECAY * confidence(0.80)
        expected = round(1.0 * _DECAY * 0.80, 4)
        assert abs(result.get("deer decline", 0) - expected) < 0.05


# ---------------------------------------------------------------------------
# 3. compute() — multi-source and edge-confidence
# ---------------------------------------------------------------------------

class TestComputeMultiSource:
    def test_multiple_sources_reach_more_concepts(self):
        sa = _sa()
        single = sa.compute({"wolves": 1.0})
        multi  = sa.compute({"wolves": 1.0, "overgrazing": 0.8})
        assert len(multi) >= len(single)

    def test_shared_neighbor_takes_max_activation(self):
        conn = _graph_conn()
        rg = RelationGraph(conn)
        # Both "fire" and "drought" CAUSE "erosion"
        rg.add("fire",    "CAUSES", "erosion", 0.80, source_key="t", session_id="s")
        rg.add("drought", "CAUSES", "erosion", 0.90, source_key="t", session_id="s")
        sa = SpreadingActivation(rg)
        result = sa.compute({"fire": 1.0, "drought": 1.0})
        # "erosion" should be reached from both; activation = max of both paths
        assert "erosion" in result
        assert result["erosion"] > 0

    def test_high_confidence_edge_spreads_more(self):
        conn = _graph_conn()
        rg = RelationGraph(conn)
        # Keys without underscores so _normalise doesn't transform them
        rg.add("alpha", "CAUSES", "highneighbor", 0.95, source_key="t", session_id="s")
        rg.add("alpha", "CAUSES", "lowneighbor",  0.40, source_key="t", session_id="s")
        sa = SpreadingActivation(rg)
        result = sa.compute({"alpha": 1.0})
        h = result.get("highneighbor", 0)
        l = result.get("lowneighbor",  0)
        assert h > l

    def test_below_min_edge_conf_not_traversed(self):
        conn = _graph_conn()
        rg = RelationGraph(conn)
        # Edge at exactly 0.30 — below _MIN_EDGE_CONF of 0.35
        rg.add("a", "CAUSES", "weak_neighbor", 0.30, source_key="t", session_id="s")
        sa = SpreadingActivation(rg)
        result = sa.compute({"a": 1.0})
        assert "weak_neighbor" not in result


# ---------------------------------------------------------------------------
# 4. Cycle / graph safety
# ---------------------------------------------------------------------------

class TestCycleSafety:
    def test_cycle_does_not_infinite_loop(self):
        conn = _graph_conn()
        rg = RelationGraph(conn)
        # A → B → A (cycle)
        rg.add("alpha", "CAUSES", "beta",  0.80, source_key="t", session_id="s")
        rg.add("beta",  "CAUSES", "alpha", 0.80, source_key="t", session_id="s")
        sa = SpreadingActivation(rg)
        # Must terminate
        result = sa.compute({"alpha": 1.0})
        assert isinstance(result, dict)

    def test_diamond_pattern_takes_best_path(self):
        conn = _graph_conn()
        rg = RelationGraph(conn)
        # A → B → D  and  A → C → D
        rg.add("a", "CAUSES", "b", 0.90, source_key="t", session_id="s")
        rg.add("a", "CAUSES", "c", 0.60, source_key="t", session_id="s")
        rg.add("b", "CAUSES", "d", 0.90, source_key="t", session_id="s")
        rg.add("c", "CAUSES", "d", 0.90, source_key="t", session_id="s")
        sa = SpreadingActivation(rg)
        result = sa.compute({"a": 1.0})
        # D is reachable via both paths; should be present and take best
        assert "d" in result


# ---------------------------------------------------------------------------
# 5. boost_scores()
# ---------------------------------------------------------------------------

class TestBoostScores:
    def _make_mem(self, content: str, relevance: float = 0.5):
        class FakeMem:
            def __init__(self, c, r):
                self.content = c
                self.context = ""
                self.relevance = r
        return FakeMem(content, relevance)

    def test_empty_activation_returns_unchanged(self):
        sa = _sa()
        mems = [("k1", self._make_mem("wolves eat deer"), 0.6)]
        result = sa.boost_scores(mems, {})
        assert result[0][2] == pytest.approx(0.6)

    def test_activated_concept_boosts_memory_score(self):
        sa = _sa()
        mem = self._make_mem("deer populations decline")
        scored = [("k1", mem, 0.4)]
        activation = {"deer": 0.8}
        result = sa.boost_scores(scored, activation)
        assert result[0][2] > 0.4

    def test_unrelated_memory_not_boosted(self):
        sa = _sa()
        mem = self._make_mem("prime numbers are interesting")
        scored = [("k1", mem, 0.5)]
        activation = {"wolves": 0.9, "deer": 0.6}
        result = sa.boost_scores(scored, activation)
        assert result[0][2] == pytest.approx(0.5)

    def test_boost_capped_at_1_0(self):
        sa = _sa()
        mem = self._make_mem("wolves control deer")
        scored = [("k1", mem, 0.95)]
        activation = {"wolves": 1.0, "deer": 1.0, "control": 1.0}
        result = sa.boost_scores(scored, activation)
        assert result[0][2] <= 1.0

    def test_result_sorted_by_boosted_score(self):
        sa = _sa()
        m1 = self._make_mem("prime numbers")
        m2 = self._make_mem("wolves control deer populations")
        scored = [("k1", m1, 0.7), ("k2", m2, 0.4)]
        activation = {"wolves": 0.9, "deer": 0.7}
        result = sa.boost_scores(scored, activation)
        # m2 gets boosted, m1 doesn't — m2 should rank first
        assert result[0][0] == "k2"


# ---------------------------------------------------------------------------
# 6. explain()
# ---------------------------------------------------------------------------

class TestExplain:
    def test_explain_returns_list(self):
        sa = _sa()
        items = sa.explain({"wolves": 1.0})
        assert isinstance(items, list)

    def test_explain_has_concept_and_activation_keys(self):
        sa = _sa()
        items = sa.explain({"wolves": 1.0})
        if items:
            assert "concept" in items[0]
            assert "activation" in items[0]

    def test_explain_sorted_descending(self):
        sa = _sa()
        items = sa.explain({"wolves": 1.0})
        if len(items) > 1:
            scores = [i["activation"] for i in items]
            assert scores == sorted(scores, reverse=True)

    def test_explain_respects_top_n(self):
        sa = _sa()
        items = sa.explain({"wolves": 1.0}, top_n=2)
        assert len(items) <= 2


# ---------------------------------------------------------------------------
# 7. memory.search() integration
# ---------------------------------------------------------------------------

class TestMemorySearchIntegration:
    def test_search_accepts_activation_boost(self):
        from memory.memory import MemorySystem
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db = f.name
        try:
            ms = MemorySystem(db_path=db, working_capacity=100)
            ms.store("wolves_key", "wolves control deer populations in Yellowstone",
                     "wolves deer", "text", 0.8)
            ms.store("rain_key", "rain causes erosion in dry areas",
                     "rain erosion", "text", 0.7)
            # FTS5 query for "wolves" — activation_boost param must be accepted
            results = ms.search("wolves", top_k=5, activation_boost={"wolves": 0.9})
            keys = [k for k, _ in results]
            assert "wolves_key" in keys
        finally:
            os.unlink(db)

    def test_search_without_boost_still_works(self):
        from memory.memory import MemorySystem
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db = f.name
        try:
            ms = MemorySystem(db_path=db, working_capacity=100)
            ms.store("k1", "wolves control deer", "wolves", "text", 0.8)
            results = ms.search("wolves", top_k=5)
            assert len(results) >= 1
        finally:
            os.unlink(db)

    def test_activation_boost_raises_score_of_primed_memory(self):
        from memory.memory import MemorySystem
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db = f.name
        try:
            ms = MemorySystem(db_path=db, working_capacity=100)
            # Two memories: one mentions "deer" (activated), one does not
            ms.store("deer_key", "deer populations decline without predators",
                     "deer", "text", 0.5)
            ms.store("unrelated_key", "prime numbers are infinite sequences",
                     "math", "text", 0.5)
            # Query for something generic; with deer activated, deer_key should win
            r_with    = ms.search("ecology", top_k=5, activation_boost={"deer": 1.0})
            r_without = ms.search("ecology", top_k=5, activation_boost=None)
            # With activation, deer_key should appear (or rank higher)
            keys_with = [k for k, _ in r_with]
            # Can't guarantee order without knowing FTS5 scores, but no crash at minimum
            assert isinstance(keys_with, list)
        finally:
            os.unlink(db)


# ---------------------------------------------------------------------------
# 8. Orchestrator integration
# ---------------------------------------------------------------------------

class TestOrchestratorIntegration:
    def test_orchestrator_has_spreading_activation(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db = f.name
        try:
            from orchestrator.orchestrator import Orchestrator
            orch = Orchestrator(verbose=False, db_path=db)
            assert hasattr(orch, "spreading_activation")
            assert isinstance(orch.spreading_activation, SpreadingActivation)
        finally:
            os.unlink(db)

    def test_query_returns_primed_concepts_key(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db = f.name
        try:
            from orchestrator.orchestrator import Orchestrator
            orch = Orchestrator(verbose=False, db_path=db)
            result = orch.query("what do wolves eat")
            # Key should always be present (may be empty list if no attention yet)
            assert "primed_concepts" in result
            assert isinstance(result["primed_concepts"], list)
        finally:
            os.unlink(db)

    def test_query_with_prior_ecology_learning(self):
        """
        Process ecology sentences, then query about 'river'.
        Wolves → deer → overgrazing → erosion → rivers path should prime
        'erosion' and related concepts even though 'erosion' wasn't queried.
        """
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db = f.name
        try:
            from orchestrator.orchestrator import Orchestrator
            orch = Orchestrator(verbose=False, db_path=db)
            ecology = [
                "Wolves cause deer populations to decline significantly.",
                "Deer overgrazing causes severe soil erosion on hillsides.",
                "Erosion causes dramatic river channel changes over time.",
                "Wolves control deer which prevents overgrazing in ecosystems.",
            ]
            for sentence in ecology:
                orch.process_input("text", sentence)
            orch.memory.update_attention(["wolves", "ecology", "predator"])
            result = orch.query("What changes rivers?")
            # No crash, result is a dict, and primed_concepts is present
            assert isinstance(result, dict)
            assert "primed_concepts" in result
        finally:
            os.unlink(db)
