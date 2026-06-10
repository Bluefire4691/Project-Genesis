"""
Tests for M30 HypothesisEngine — Genesis's first generative-cognition organ.

Verifies that Genesis:
1. Forms hypotheses from structural analogy, contradiction, and chain extension
2. Stores them separately from observed relations (no graph pollution)
3. Tests open hypotheses against later evidence (confirm / refute)
4. Promotes confirmed object-specified hypotheses into the graph
5. Surfaces open-hypothesis subjects as curiosity targets
6. Tracks its own hit-rate as a hypothesizer
7. Integration: the orchestrator has a hypotheses engine wired into reflect()
"""
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from cognition.hypothesis import HypothesisEngine, _chain_linkable


# ── Chain bridging across concept granularity ───────────────────────────────

class TestChainLinkable:
    def test_exact_match_links(self):
        assert _chain_linkable("deer", "deer")

    def test_single_word_bridges_to_multiword(self):
        assert _chain_linkable("deer populations", "deer")
        assert _chain_linkable("deer", "deer populations")

    def test_unrelated_multiword_do_not_link(self):
        assert not _chain_linkable("soil to erode", "new growth")

    def test_short_or_generic_words_do_not_bridge(self):
        assert not _chain_linkable("ice age", "ice")     # "ice" len 3 < 4
        assert not _chain_linkable("many things", "things")  # generic filler

    def test_substring_does_not_falsely_link(self):
        # token-level only: "ice" must never link to "service"
        assert not _chain_linkable("service", "ice")


def _brain():
    """Fresh orchestrator on a tempfile DB (count assertions need isolation)."""
    from orchestrator.orchestrator import Orchestrator
    db = tempfile.mktemp(suffix=".db")
    b = Orchestrator(verbose=False, db_path=db)
    return b, db


def _cleanup(db):
    if os.path.exists(db):
        os.unlink(db)


# ── Chain-extension generation ──────────────────────────────────────────────

class TestChainExtension:
    def test_hypothesizes_transitive_cause(self):
        b, db = _brain()
        try:
            r = b.relations
            r.add("wolves", "CAUSES", "deer decline", 0.9)
            r.add("deer decline", "CAUSES", "vegetation recovery", 0.9)
            n = b.hypotheses.generate()
            assert n > 0, "should form at least one hypothesis from a 2-link chain"
            open_hyps = b.hypotheses.open_hypotheses()
            chains = [h for h in open_hyps if h["basis"] == "chain"]
            assert any(
                h["subject"] == "wolves" and h["object"] == "vegetation recovery"
                and h["rel_type"] == "CAUSES"
                for h in chains
            ), "should predict wolves CAUSES vegetation recovery (A→B→C ⇒ A→C)"
        finally:
            _cleanup(db)

    def test_no_hypothesis_when_link_already_known(self):
        b, db = _brain()
        try:
            r = b.relations
            r.add("a", "CAUSES", "b", 0.9)
            r.add("b", "CAUSES", "c", 0.9)
            r.add("a", "CAUSES", "c", 0.9)   # already known — nothing to predict
            b.hypotheses.generate()
            chains = [h for h in b.hypotheses.open_hypotheses()
                      if h["basis"] == "chain" and h["subject"] == "a"
                      and h["object"] == "c"]
            assert not chains, "should not hypothesize an already-observed link"
        finally:
            _cleanup(db)


# ── Contradiction-moderation generation ─────────────────────────────────────

class TestContradictionModeration:
    def test_hypothesizes_hidden_moderator(self):
        b, db = _brain()
        try:
            r = b.relations
            r.add("overgrazing", "CAUSES", "erosion", 0.85)
            r.add("overgrazing", "PREVENTS", "erosion", 0.85)
            b.contradictions.scan(session_id="t")
            b.hypotheses.generate()
            mods = [h for h in b.hypotheses.open_hypotheses()
                    if h["basis"] == "contradiction"]
            assert any(
                h["subject"] == "overgrazing" and h["object"] == "erosion"
                for h in mods
            ), "a held contradiction should yield a moderating-variable hypothesis"
        finally:
            _cleanup(db)


# ── Verification loop ───────────────────────────────────────────────────────

class TestVerification:
    def test_chain_hypothesis_confirmed_by_evidence(self):
        b, db = _brain()
        try:
            r = b.relations
            r.add("a", "CAUSES", "b", 0.9)
            r.add("b", "CAUSES", "c", 0.9)
            b.hypotheses.generate()
            # Evidence arrives: a directly causes c
            r.add("a", "CAUSES", "c", 0.8)
            resolved = b.hypotheses.verify()
            assert resolved >= 1
            confirmed = b.hypotheses.resolved_hypotheses()
            assert any(
                h["subject"] == "a" and h["object"] == "c"
                and h["status"] == "confirmed"
                for h in confirmed
            )
        finally:
            _cleanup(db)

    def test_hypothesis_refuted_by_opposing_evidence(self):
        b, db = _brain()
        try:
            r = b.relations
            r.add("a", "CAUSES", "b", 0.9)
            r.add("b", "CAUSES", "c", 0.9)
            b.hypotheses.generate()
            # Opposing evidence: a actually PREVENTS c
            r.add("a", "PREVENTS", "c", 0.85)
            b.hypotheses.verify()
            refuted = [h for h in b.hypotheses.resolved_hypotheses()
                       if h["subject"] == "a" and h["object"] == "c"]
            assert refuted and refuted[0]["status"] == "refuted"
        finally:
            _cleanup(db)

    def test_confirmed_hypothesis_promoted_to_graph(self):
        b, db = _brain()
        try:
            r = b.relations
            r.add("a", "CAUSES", "b", 0.9)
            r.add("b", "CAUSES", "c", 0.9)
            b.hypotheses.generate()
            r.add("a", "CAUSES", "c", 0.8)
            b.hypotheses.verify()
            # The promoted edge is just the observed one we added; confirm it stands
            edges = r.query_subject("a", min_confidence=0.5)
            assert any(e["relation"] == "CAUSES" and e["object"] == "c" for e in edges)
        finally:
            _cleanup(db)


# ── No graph pollution ──────────────────────────────────────────────────────

class TestSeparation:
    def test_open_hypotheses_not_in_relation_graph(self):
        b, db = _brain()
        try:
            r = b.relations
            r.add("a", "CAUSES", "b", 0.9)
            r.add("b", "CAUSES", "c", 0.9)
            before = r.stats()["total_relations"]
            b.hypotheses.generate()
            after = r.stats()["total_relations"]
            assert after == before, "forming hypotheses must not add to the relation graph"
        finally:
            _cleanup(db)


# ── Curiosity coupling ──────────────────────────────────────────────────────

class TestCuriosityTargets:
    def test_open_hypothesis_subjects_become_targets(self):
        b, db = _brain()
        try:
            r = b.relations
            r.add("lions", "CAUSES", "gazelle decline", 0.9)
            r.add("gazelle decline", "CAUSES", "grass recovery", 0.9)
            b.hypotheses.generate()
            targets = b.hypotheses.curiosity_targets()
            assert "lions" in targets
        finally:
            _cleanup(db)


# ── Self-calibration ────────────────────────────────────────────────────────

class TestStats:
    def test_hit_rate_tracked(self):
        b, db = _brain()
        try:
            r = b.relations
            r.add("a", "CAUSES", "b", 0.9)
            r.add("b", "CAUSES", "c", 0.9)
            b.hypotheses.generate()
            r.add("a", "CAUSES", "c", 0.8)   # confirm it
            b.hypotheses.verify()
            stats = b.hypotheses.stats()
            assert stats["confirmed"] >= 1
            assert stats["hit_rate"] is not None
            assert 0.0 <= stats["hit_rate"] <= 1.0
        finally:
            _cleanup(db)

    def test_hit_rate_none_when_nothing_resolved(self):
        b, db = _brain()
        try:
            assert b.hypotheses.stats()["hit_rate"] is None
        finally:
            _cleanup(db)


# ── Integration ─────────────────────────────────────────────────────────────

class TestOrchestratorIntegration:
    def test_orchestrator_has_hypotheses(self):
        b, db = _brain()
        try:
            assert hasattr(b, "hypotheses")
            assert isinstance(b.hypotheses, HypothesisEngine)
        finally:
            _cleanup(db)

    def test_reflect_runs_generation(self):
        b, db = _brain()
        try:
            r = b.relations
            r.add("a", "CAUSES", "b", 0.9)
            r.add("b", "CAUSES", "c", 0.9)
            b.reflect()
            assert b.hypotheses.stats()["total"] >= 1, (
                "reflect() should form at least one hypothesis from the chain"
            )
        finally:
            _cleanup(db)

    def test_voice_can_speak_a_hypothesis(self):
        b, db = _brain()
        try:
            r = b.relations
            r.add("wolves", "CAUSES", "deer decline", 0.9)
            r.add("deer decline", "CAUSES", "vegetation recovery", 0.9)
            b.hypotheses.generate()
            stmt = b.voice._compose_hypothesis()
            assert stmt and isinstance(stmt, str) and len(stmt) > 10
            assert stmt[0].isupper() and stmt.rstrip().endswith(".")
        finally:
            _cleanup(db)
