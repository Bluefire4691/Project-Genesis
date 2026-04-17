"""
Tests for M11 — ContradictionLog.

Covers:
- Schema initialization
- scan() detects CAUSES↔PREVENTS, ENABLES↔PREVENTS, REQUIRES↔PREVENTS
- No false positives (non-opposing pairs not flagged)
- Neither conflicting triple is deleted
- scan() idempotent (no duplicates on repeated scan)
- query() returns stored conflicts
- query_concept() filters by concept
- most_contested() ordering
- stats() keys and values
- are_opposing() helper
- Integration: contradictions detected after processing conflicting text
- full_status includes contradiction stats
"""

import sys
import os
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

import pytest
from orchestrator.orchestrator import Orchestrator
from cognition.contradictions import ContradictionLog, are_opposing


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _brain(**kwargs) -> Orchestrator:
    if "db_path" not in kwargs:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        kwargs["db_path"] = tmp.name
    return Orchestrator(verbose=False, **kwargs)


def _add(brain, subj, rel, obj, conf=0.8):
    brain.relations.add(subj, rel, obj, confidence=conf, session_id="test")


# ------------------------------------------------------------------
# are_opposing helper
# ------------------------------------------------------------------

class TestAreOpposing:
    def test_causes_prevents(self):
        assert are_opposing("CAUSES", "PREVENTS")
        assert are_opposing("PREVENTS", "CAUSES")

    def test_enables_prevents(self):
        assert are_opposing("ENABLES", "PREVENTS")
        assert are_opposing("PREVENTS", "ENABLES")

    def test_requires_prevents(self):
        assert are_opposing("REQUIRES", "PREVENTS")
        assert are_opposing("PREVENTS", "REQUIRES")

    def test_causes_controls_not_opposing(self):
        assert not are_opposing("CAUSES", "CONTROLS")

    def test_causes_enables_not_opposing(self):
        assert not are_opposing("CAUSES", "ENABLES")

    def test_same_type_not_opposing(self):
        assert not are_opposing("CAUSES", "CAUSES")
        assert not are_opposing("PREVENTS", "PREVENTS")

    def test_is_a_not_opposing(self):
        assert not are_opposing("IS_A", "PREVENTS")


# ------------------------------------------------------------------
# Schema
# ------------------------------------------------------------------

class TestSchema:
    def test_table_created(self):
        brain = _brain()
        cur = brain.memory._long_term.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='contradiction_log'"
        )
        assert cur.fetchone() is not None

    def test_stats_empty(self):
        brain = _brain()
        s = brain.contradictions.stats()
        assert s["total_contradictions"] == 0
        assert s["by_pair"] == {}


# ------------------------------------------------------------------
# scan() — detection
# ------------------------------------------------------------------

class TestScan:
    def test_detects_causes_prevents(self):
        brain = _brain()
        _add(brain, "fire", "CAUSES", "ash", 0.9)
        _add(brain, "fire", "PREVENTS", "ash", 0.7)
        n = brain.contradictions.scan()
        assert n >= 1

    def test_detects_enables_prevents(self):
        brain = _brain()
        _add(brain, "oxygen", "ENABLES", "combustion", 0.9)
        _add(brain, "oxygen", "PREVENTS", "combustion", 0.6)
        n = brain.contradictions.scan()
        assert n >= 1

    def test_detects_requires_prevents(self):
        brain = _brain()
        _add(brain, "growth", "REQUIRES", "water", 0.9)
        _add(brain, "growth", "PREVENTS", "water", 0.5)
        n = brain.contradictions.scan()
        assert n >= 1

    def test_no_false_positive_controls_causes(self):
        brain = _brain()
        _add(brain, "valve", "CONTROLS", "flow", 0.9)
        _add(brain, "valve", "CAUSES", "flow", 0.8)
        n = brain.contradictions.scan()
        assert n == 0

    def test_no_false_positive_different_objects(self):
        """Same subject, same rel types, different objects — not a conflict."""
        brain = _brain()
        _add(brain, "fire", "CAUSES", "ash", 0.9)
        _add(brain, "fire", "PREVENTS", "ice", 0.8)
        n = brain.contradictions.scan()
        assert n == 0

    def test_no_false_positive_different_subjects(self):
        brain = _brain()
        _add(brain, "fire", "CAUSES", "ash", 0.9)
        _add(brain, "water", "PREVENTS", "ash", 0.8)
        n = brain.contradictions.scan()
        assert n == 0

    def test_scan_idempotent(self):
        brain = _brain()
        _add(brain, "a", "CAUSES", "b", 0.9)
        _add(brain, "a", "PREVENTS", "b", 0.7)
        n1 = brain.contradictions.scan()
        n2 = brain.contradictions.scan()
        assert n1 >= 1
        assert n2 == 0  # already stored, no new ones

    def test_scan_empty_graph(self):
        brain = _brain()
        n = brain.contradictions.scan()
        assert n == 0

    def test_scan_no_conflict_returns_zero(self):
        brain = _brain()
        _add(brain, "a", "CAUSES", "b", 0.9)
        _add(brain, "b", "CAUSES", "c", 0.8)
        n = brain.contradictions.scan()
        assert n == 0


# ------------------------------------------------------------------
# Data integrity — neither triple deleted
# ------------------------------------------------------------------

class TestDataIntegrity:
    def test_both_triples_remain_after_conflict(self):
        brain = _brain()
        _add(brain, "deforestation", "CAUSES", "flooding", 0.9)
        _add(brain, "deforestation", "PREVENTS", "flooding", 0.6)
        brain.contradictions.scan()

        # Both triples should still be in the relations table
        causes = brain.relations.query_subject("deforestation", min_confidence=0.0)
        rel_types = [r["relation"] for r in causes if r["object"] == "flooding"]
        assert "CAUSES" in rel_types
        assert "PREVENTS" in rel_types

    def test_conflict_does_not_reduce_confidence(self):
        brain = _brain()
        _add(brain, "a", "CAUSES", "b", 0.95)
        _add(brain, "a", "PREVENTS", "b", 0.5)
        brain.contradictions.scan()

        causes = [r for r in brain.relations.query_subject("a", min_confidence=0.0)
                  if r["object"] == "b" and r["relation"] == "CAUSES"]
        assert causes[0]["confidence"] == 0.95  # unchanged


# ------------------------------------------------------------------
# query() and query_concept()
# ------------------------------------------------------------------

class TestQuery:
    def test_query_returns_list(self):
        brain = _brain()
        assert isinstance(brain.contradictions.query(), list)

    def test_query_returns_conflicts_after_scan(self):
        brain = _brain()
        _add(brain, "fire", "CAUSES", "ash", 0.9)
        _add(brain, "fire", "PREVENTS", "ash", 0.7)
        brain.contradictions.scan()
        conflicts = brain.contradictions.query()
        assert len(conflicts) >= 1

    def test_query_dict_keys(self):
        brain = _brain()
        _add(brain, "a", "CAUSES", "b", 0.9)
        _add(brain, "a", "PREVENTS", "b", 0.7)
        brain.contradictions.scan()
        c = brain.contradictions.query()[0]
        assert "subject" in c
        assert "rel_type_a" in c
        assert "rel_type_b" in c
        assert "object" in c
        assert "conf_a" in c
        assert "conf_b" in c

    def test_query_concept_finds_subject(self):
        brain = _brain()
        _add(brain, "wolves", "CAUSES", "deer_decline", 0.9)
        _add(brain, "wolves", "PREVENTS", "deer_decline", 0.6)
        brain.contradictions.scan()
        results = brain.contradictions.query_concept("wolves")
        assert len(results) >= 1
        assert all(
            r["subject"] == "wolves" or r["object"] == "wolves"
            for r in results
        )

    def test_query_concept_finds_object(self):
        brain = _brain()
        _add(brain, "rain", "CAUSES", "flooding", 0.9)
        _add(brain, "rain", "PREVENTS", "flooding", 0.5)
        brain.contradictions.scan()
        results = brain.contradictions.query_concept("flooding")
        assert len(results) >= 1

    def test_query_concept_empty_for_unknown(self):
        brain = _brain()
        results = brain.contradictions.query_concept("xyzzy_unknown")
        assert results == []


# ------------------------------------------------------------------
# most_contested
# ------------------------------------------------------------------

class TestMostContested:
    def test_most_contested_returns_list(self):
        brain = _brain()
        assert isinstance(brain.contradictions.most_contested(), list)

    def test_most_contested_ordering(self):
        brain = _brain()
        # concept_a appears in 2 conflicts, concept_b in 1
        _add(brain, "concept_a", "CAUSES", "x", 0.9)
        _add(brain, "concept_a", "PREVENTS", "x", 0.8)
        _add(brain, "concept_a", "ENABLES", "y", 0.9)
        _add(brain, "concept_a", "PREVENTS", "y", 0.7)
        _add(brain, "concept_b", "CAUSES", "z", 0.9)
        _add(brain, "concept_b", "PREVENTS", "z", 0.6)
        brain.contradictions.scan()
        contested = brain.contradictions.most_contested(limit=5)
        assert len(contested) >= 1
        if len(contested) >= 2:
            assert contested[0]["conflicts"] >= contested[1]["conflicts"]


# ------------------------------------------------------------------
# Stats
# ------------------------------------------------------------------

class TestStats:
    def test_stats_keys(self):
        brain = _brain()
        s = brain.contradictions.stats()
        assert "total_contradictions" in s
        assert "by_pair" in s

    def test_stats_count_after_scan(self):
        brain = _brain()
        _add(brain, "a", "CAUSES", "b", 0.9)
        _add(brain, "a", "PREVENTS", "b", 0.7)
        brain.contradictions.scan()
        assert brain.contradictions.stats()["total_contradictions"] >= 1

    def test_stats_by_pair_populated(self):
        brain = _brain()
        _add(brain, "a", "CAUSES", "b", 0.9)
        _add(brain, "a", "PREVENTS", "b", 0.7)
        brain.contradictions.scan()
        s = brain.contradictions.stats()
        assert len(s["by_pair"]) >= 1


# ------------------------------------------------------------------
# Orchestrator integration
# ------------------------------------------------------------------

class TestOrchestratorIntegration:
    def test_contradictions_accessible_on_brain(self):
        brain = _brain()
        assert hasattr(brain, "contradictions")
        assert isinstance(brain.contradictions, ContradictionLog)

    def test_full_status_includes_contradictions(self):
        brain = _brain()
        s = brain.full_status()
        assert "contradictions" in s
        assert "total_contradictions" in s["contradictions"]

    def test_scan_runs_after_conflicting_input(self):
        """After processing text that generates conflicting relations, scan detects them."""
        brain = _brain()
        # Directly add conflicting relations to simulate what text extraction might produce
        brain.relations.add("deforestation", "CAUSES", "flooding", 0.85, session_id="test")
        brain.relations.add("deforestation", "PREVENTS", "flooding", 0.6, session_id="test")
        n = brain.contradictions.scan(session_id=brain.session_id)
        assert n >= 1

    def test_count_method(self):
        brain = _brain()
        assert brain.contradictions.count() == 0
        brain.relations.add("a", "CAUSES", "b", 0.9, session_id="t")
        brain.relations.add("a", "PREVENTS", "b", 0.7, session_id="t")
        brain.contradictions.scan()
        assert brain.contradictions.count() >= 1
