"""
Tests for M30.2 ResearchProposal — Genesis authoring a research direction.

Verifies that Genesis:
1. Composes a multi-section first-person document from its own graph state
2. Returns None honestly when it has too little to say
3. Weaves in gaps, contradictions, analogs, and open hypotheses
4. Stores proposals and exposes latest()/history()
5. Names concrete read-targets (the forward-looking intent)
6. Integration: orchestrator exposes propose_research() and drafts during reflect()
"""
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from cognition.research_proposal import (
    ResearchProposal, _is_clean, _english_list, _confidence_word,
)


def _brain():
    from orchestrator.orchestrator import Orchestrator
    db = tempfile.mktemp(suffix=".db")
    b = Orchestrator(verbose=False, db_path=db)
    return b, db


def _cleanup(db):
    if os.path.exists(db):
        os.unlink(db)


def _seed_ecosystem(b):
    """A small but connected graph that gives the proposal real material."""
    r = b.relations
    r.add("wolves", "CONTROLS", "deer", 0.9)
    r.add("wolves", "PREVENTS", "overgrazing", 0.85)
    r.add("wolves", "PREDATES", "deer", 0.88)
    r.add("deer", "CAUSES", "overgrazing", 0.8)
    r.add("overgrazing", "CAUSES", "erosion", 0.85)
    r.add("lions", "CONTROLS", "gazelles", 0.9)
    r.add("lions", "PREDATES", "gazelles", 0.88)


# ── Honest floor ────────────────────────────────────────────────────────────

class TestEmptyState:
    def test_returns_none_with_empty_graph(self):
        b, db = _brain()
        try:
            assert b.research.compose() is None, (
                "with no graph, Genesis should propose nothing rather than fabricate"
            )
        finally:
            _cleanup(db)


# ── Composition ─────────────────────────────────────────────────────────────

class TestComposition:
    def test_composes_document_from_graph(self):
        b, db = _brain()
        try:
            _seed_ecosystem(b)
            doc = b.research.compose()
            assert doc and isinstance(doc, str)
            assert "What I understand" in doc
            # First-person, document-like
            assert "I" in doc
            assert len(doc) > 100
        finally:
            _cleanup(db)

    def test_includes_gap_section(self):
        b, db = _brain()
        try:
            _seed_ecosystem(b)   # erosion is a pure gap (incoming, no outgoing)
            doc = b.research.compose()
            assert "What I don't yet grasp" in doc
        finally:
            _cleanup(db)

    def test_includes_prediction_when_hypotheses_exist(self):
        b, db = _brain()
        try:
            _seed_ecosystem(b)
            b.hypotheses.generate()   # chain: deer→overgrazing→erosion etc.
            doc = b.research.compose()
            assert doc is not None
            # A prediction section appears when there is at least one open hypothesis
            if b.hypotheses.open_hypotheses():
                assert "What I predict" in doc
        finally:
            _cleanup(db)

    def test_names_read_targets(self):
        b, db = _brain()
        try:
            _seed_ecosystem(b)
            b.hypotheses.generate()
            b.research.compose()
            latest = b.research.latest()
            assert latest is not None
            assert isinstance(latest["targets"], list)
        finally:
            _cleanup(db)


# ── Persistence ─────────────────────────────────────────────────────────────

class TestPersistence:
    def test_latest_and_history(self):
        b, db = _brain()
        try:
            _seed_ecosystem(b)
            b.research.compose()
            b.research.compose()
            assert b.research.latest() is not None
            assert len(b.research.history()) == 2
            assert b.research.stats()["total_proposals"] == 2
        finally:
            _cleanup(db)

    def test_stored_body_matches_returned(self):
        b, db = _brain()
        try:
            _seed_ecosystem(b)
            doc = b.research.compose()
            assert b.research.latest()["body"] == doc
        finally:
            _cleanup(db)


# ── No graph pollution ──────────────────────────────────────────────────────

class TestSeparation:
    def test_proposal_does_not_add_relations(self):
        b, db = _brain()
        try:
            _seed_ecosystem(b)
            before = b.relations.stats()["total_relations"]
            b.research.compose()
            after = b.relations.stats()["total_relations"]
            assert after == before, "composing a proposal must not mutate the graph"
        finally:
            _cleanup(db)


# ── Integration ─────────────────────────────────────────────────────────────

class TestOrchestratorIntegration:
    def test_propose_research_method(self):
        b, db = _brain()
        try:
            _seed_ecosystem(b)
            doc = b.propose_research()
            assert doc and isinstance(doc, str)
        finally:
            _cleanup(db)

    def test_reflect_drafts_on_schedule(self):
        b, db = _brain()
        try:
            _seed_ecosystem(b)
            b._proposal_every = 1   # draft every reflection for the test
            b.reflect()
            assert b.research.stats()["total_proposals"] >= 1
        finally:
            _cleanup(db)

    def test_say_plans_mentions_direction(self):
        b, db = _brain()
        try:
            _seed_ecosystem(b)
            b.hypotheses.generate()
            b.research.compose()
            plans = b.voice._say_plans()
            assert isinstance(plans, str) and len(plans) > 0
        finally:
            _cleanup(db)


# ── Helpers ─────────────────────────────────────────────────────────────────

class TestHelpers:
    def test_is_clean(self):
        assert _is_clean("wolves")
        assert _is_clean("deer population")
        assert not _is_clean("")
        assert not _is_clean("a b c d e")
        assert not _is_clean("38 26")
        assert not _is_clean("x")

    def test_english_list(self):
        assert _english_list(["a"]) == "a"
        assert _english_list(["a", "b"]) == "a and b"
        assert _english_list(["a", "b", "c"]) == "a, b, and c"

    def test_confidence_word(self):
        assert _confidence_word(0.7) == "moderate"
        assert _confidence_word(0.5) == "low-to-moderate"
        assert _confidence_word(0.3) == "low"
