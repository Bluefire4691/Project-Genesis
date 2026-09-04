"""
Tests for M31 InferenceProgramEngine — Genesis's declarative rule-authoring organ.

Verifies that Genesis:
1. Discovers two-hop chain patterns and authors rules from them
2. Requires MIN_EVIDENCE instances before promoting a pattern to a rule
3. Runs authored rules across the full graph to derive new edges
4. Never overwrites directly-observed edges with derived ones
5. Confirms derivations that are later independently observed
6. Tracks hit rate (program reliability)
7. Excludes IS_A from mining (M10 handles inheritance)
8. Keeps derivations strictly separate from observed relations
9. Integration: orchestrator has programs engine, reflect() mines and runs
10. Voice: Genesis can state a rule it has formulated
"""
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from cognition.inference_programs import InferenceProgramEngine


def _brain():
    """Fresh orchestrator on a tempfile DB — count assertions need isolation."""
    from orchestrator.orchestrator import Orchestrator
    db = tempfile.mktemp(suffix=".db")
    b = Orchestrator(verbose=False, db_path=db)
    return b, db


def _cleanup(db):
    if os.path.exists(db):
        os.unlink(db)


# ── Rule mining ──────────────────────────────────────────────────────────────

class TestMining:
    def test_mines_pattern_above_threshold(self):
        """Two instances of (CONTROLS + CAUSES → CAUSES) → one rule authored."""
        b, db = _brain()
        try:
            r = b.relations
            # Instance 1: wolves CONTROLS deer, deer CAUSES overgrazing
            #             wolves CAUSES overgrazing  (direct)
            r.add("wolves",      "CONTROLS", "deer",        0.9)
            r.add("deer",        "CAUSES",   "overgrazing", 0.9)
            r.add("wolves",      "CAUSES",   "overgrazing", 0.85)
            # Instance 2: lions CONTROLS gazelle, gazelle CAUSES grass_loss
            #             lions CAUSES grass_loss  (direct)
            r.add("lions",       "CONTROLS", "gazelle",     0.9)
            r.add("gazelle",     "CAUSES",   "grass_loss",  0.9)
            r.add("lions",       "CAUSES",   "grass_loss",  0.85)

            n = b.programs.mine()
            assert n >= 1, "should author at least one rule from two CONTROLS+CAUSES chains"
            rules = b.programs.programs()
            assert any(
                rule["rel_a"] == "CONTROLS" and rule["rel_b"] == "CAUSES"
                and rule["result_rel"] == "CAUSES"
                for rule in rules
            ), "should author a CONTROLS+CAUSES→CAUSES rule"
        finally:
            _cleanup(db)

    def test_no_rule_below_threshold(self):
        """Only one instance of a pattern — no rule authored."""
        b, db = _brain()
        try:
            r = b.relations
            r.add("wolves",  "CONTROLS", "deer",       0.9)
            r.add("deer",    "CAUSES",   "erosion",    0.9)
            r.add("wolves",  "CAUSES",   "erosion",    0.8)
            # Only one instance — below MIN_EVIDENCE (2)
            n = b.programs.mine()
            assert n == 0, "single instance should not produce a rule"
        finally:
            _cleanup(db)

    def test_is_a_excluded_from_mining(self):
        """IS_A relations must not be used in mined rules — M10 handles them."""
        b, db = _brain()
        try:
            r = b.relations
            for i in range(3):
                r.add(f"cat{i}", "IS_A",   "mammal",   0.95)
                r.add("mammal",  "CONTAINS","fur",      0.95)
                r.add(f"cat{i}", "CONTAINS","fur",      0.90)
            n = b.programs.mine()
            rules = b.programs.programs()
            # No rule should involve IS_A
            assert not any(
                rule["rel_a"] == "IS_A" or rule["rel_b"] == "IS_A"
                or rule["result_rel"] == "IS_A"
                for rule in rules
            ), "IS_A must not appear in mined rules"
        finally:
            _cleanup(db)

    def test_mine_idempotent(self):
        """Calling mine() twice does not double-count rules."""
        b, db = _brain()
        try:
            r = b.relations
            r.add("a", "CONTROLS", "b", 0.9)
            r.add("b", "CAUSES",   "c", 0.9)
            r.add("a", "CAUSES",   "c", 0.85)
            r.add("x", "CONTROLS", "y", 0.9)
            r.add("y", "CAUSES",   "z", 0.9)
            r.add("x", "CAUSES",   "z", 0.85)
            b.programs.mine()
            n_after_first = len(b.programs.programs())
            b.programs.mine()
            n_after_second = len(b.programs.programs())
            assert n_after_second == n_after_first, \
                "mining twice should not create duplicate rules"
        finally:
            _cleanup(db)

    def test_evidence_count_stored(self):
        """evidence_count on the authored rule reflects supporting instances."""
        b, db = _brain()
        try:
            r = b.relations
            r.add("a", "CONTROLS", "b", 0.9);  r.add("b", "CAUSES", "c", 0.9)
            r.add("a", "CAUSES",   "c", 0.85)
            r.add("x", "CONTROLS", "y", 0.9);  r.add("y", "CAUSES", "z", 0.9)
            r.add("x", "CAUSES",   "z", 0.85)
            b.programs.mine()
            rules = b.programs.programs()
            ctrl_cause = next(
                (rl for rl in rules
                 if rl["rel_a"] == "CONTROLS" and rl["rel_b"] == "CAUSES"),
                None,
            )
            assert ctrl_cause is not None
            assert ctrl_cause["evidence_count"] >= 2
        finally:
            _cleanup(db)


# ── Rule execution ────────────────────────────────────────────────────────────

class TestExecution:
    def test_run_derives_new_edge(self):
        """run_all() uses an authored rule to produce new derivations."""
        b, db = _brain()
        try:
            r = b.relations
            # Seed the rule: CONTROLS + CAUSES → CAUSES
            r.add("a", "CONTROLS", "b", 0.9)
            r.add("b", "CAUSES",   "c", 0.9)
            r.add("a", "CAUSES",   "c", 0.85)
            r.add("x", "CONTROLS", "y", 0.9)
            r.add("y", "CAUSES",   "z", 0.9)
            r.add("x", "CAUSES",   "z", 0.85)
            b.programs.mine()
            # New chain matching the rule — no direct edge yet
            r.add("lions",   "CONTROLS", "deer",       0.8)
            r.add("deer",    "CAUSES",   "vegetation", 0.8)
            # No lions CAUSES vegetation observed
            n = b.programs.run_all()
            assert n >= 1, "should derive at least one new edge from the rule"
            derivations = b.programs.top_derivations()
            assert any(
                d["subject"] == "lions" and d["object"] == "vegetation"
                and d["rel_type"] == "CAUSES"
                for d in derivations
            ), "should derive lions CAUSES vegetation"
        finally:
            _cleanup(db)

    def test_run_skips_observed_edges(self):
        """run_all() must not derive an edge that already exists as observed."""
        b, db = _brain()
        try:
            r = b.relations
            r.add("a", "CONTROLS", "b", 0.9);  r.add("b", "CAUSES", "c", 0.9)
            r.add("a", "CAUSES",   "c", 0.85)
            r.add("x", "CONTROLS", "y", 0.9);  r.add("y", "CAUSES", "z", 0.9)
            r.add("x", "CAUSES",   "z", 0.85)
            b.programs.mine()

            before = len(b.programs.top_derivations())
            # All matching chains already have direct observed edges — nothing new
            n = b.programs.run_all()
            after = len(b.programs.top_derivations())
            # Any new derivations should only come from truly unobserved chains
            # For the seeded examples (a→c, x→z already observed), 0 new derivations
            # from those specific pairs
            deriv_subjs = {d["subject"] for d in b.programs.top_derivations()}
            assert "a" not in deriv_subjs, "should not re-derive an already-observed edge"
            assert "x" not in deriv_subjs, "should not re-derive an already-observed edge"
        finally:
            _cleanup(db)

    def test_application_count_updated(self):
        """After run_all(), application_count on the rule is positive."""
        b, db = _brain()
        try:
            r = b.relations
            r.add("a", "CONTROLS", "b", 0.9);  r.add("b", "CAUSES", "c", 0.9)
            r.add("a", "CAUSES",   "c", 0.85)
            r.add("x", "CONTROLS", "y", 0.9);  r.add("y", "CAUSES", "z", 0.9)
            r.add("x", "CAUSES",   "z", 0.85)
            b.programs.mine()
            # Add a novel chain the rule can act on
            r.add("p", "CONTROLS", "q", 0.8);  r.add("q", "CAUSES", "s", 0.8)
            b.programs.run_all()
            rules = b.programs.programs()
            ctrl_cause = next(
                (rl for rl in rules
                 if rl["rel_a"] == "CONTROLS" and rl["rel_b"] == "CAUSES"),
                None,
            )
            assert ctrl_cause is not None
            assert ctrl_cause["application_count"] > 0
        finally:
            _cleanup(db)


# ── Derivation tracking ───────────────────────────────────────────────────────

class TestVerification:
    def test_verify_confirms_when_observed(self):
        """verify_derivations() marks a derivation confirmed when independently observed."""
        b, db = _brain()
        try:
            r = b.relations
            r.add("a", "CONTROLS", "b", 0.9);  r.add("b", "CAUSES", "c", 0.9)
            r.add("a", "CAUSES",   "c", 0.85)
            r.add("x", "CONTROLS", "y", 0.9);  r.add("y", "CAUSES", "z", 0.9)
            r.add("x", "CAUSES",   "z", 0.85)
            b.programs.mine()
            r.add("lions", "CONTROLS", "deer", 0.8)
            r.add("deer",  "CAUSES",   "veg",  0.8)
            b.programs.run_all()
            # Now independently observe the derived edge
            r.add("lions", "CAUSES", "veg", 0.75)
            confirmed = b.programs.verify_derivations()
            assert confirmed >= 1
        finally:
            _cleanup(db)

    def test_hit_count_incremented_on_confirm(self):
        """Each confirmed derivation increments the rule's hit_count."""
        b, db = _brain()
        try:
            r = b.relations
            r.add("a", "CONTROLS", "b", 0.9);  r.add("b", "CAUSES", "c", 0.9)
            r.add("a", "CAUSES",   "c", 0.85)
            r.add("x", "CONTROLS", "y", 0.9);  r.add("y", "CAUSES", "z", 0.9)
            r.add("x", "CAUSES",   "z", 0.85)
            b.programs.mine()
            r.add("lions", "CONTROLS", "deer", 0.8)
            r.add("deer",  "CAUSES",   "veg",  0.8)
            b.programs.run_all()
            r.add("lions", "CAUSES", "veg", 0.75)
            b.programs.verify_derivations()
            rules = b.programs.programs()
            rule = next(
                (rl for rl in rules
                 if rl["rel_a"] == "CONTROLS" and rl["rel_b"] == "CAUSES"),
                None,
            )
            assert rule is not None
            assert rule["hit_count"] >= 1
        finally:
            _cleanup(db)


# ── Separation — derivations must not pollute the relation graph ──────────────

class TestSeparation:
    def test_derivations_not_in_relation_graph(self):
        """run_all() must never insert rows into the relations table."""
        b, db = _brain()
        try:
            r = b.relations
            r.add("a", "CONTROLS", "b", 0.9);  r.add("b", "CAUSES", "c", 0.9)
            r.add("a", "CAUSES",   "c", 0.85)
            r.add("x", "CONTROLS", "y", 0.9);  r.add("y", "CAUSES", "z", 0.9)
            r.add("x", "CAUSES",   "z", 0.85)
            b.programs.mine()
            r.add("p", "CONTROLS", "q", 0.8);  r.add("q", "CAUSES", "s", 0.8)
            before = r.stats()["total_relations"]
            b.programs.run_all()
            after = r.stats()["total_relations"]
            assert after == before, \
                "run_all() must not modify the observed relation graph"
        finally:
            _cleanup(db)


# ── Stats ─────────────────────────────────────────────────────────────────────

class TestStats:
    def test_stats_structure(self):
        """stats() returns all expected keys."""
        b, db = _brain()
        try:
            s = b.programs.stats()
            for key in ("total_programs", "avg_confidence", "total_derivations",
                        "confirmed_derivations", "total_applications",
                        "total_hits", "hit_rate"):
                assert key in s, f"missing key: {key}"
        finally:
            _cleanup(db)

    def test_hit_rate_none_with_no_applications(self):
        """hit_rate is None when no programs have ever been applied."""
        b, db = _brain()
        try:
            assert b.programs.stats()["hit_rate"] is None
        finally:
            _cleanup(db)

    def test_hit_rate_range(self):
        """hit_rate, when present, is between 0 and 1."""
        b, db = _brain()
        try:
            r = b.relations
            r.add("a", "CONTROLS", "b", 0.9);  r.add("b", "CAUSES", "c", 0.9)
            r.add("a", "CAUSES",   "c", 0.85)
            r.add("x", "CONTROLS", "y", 0.9);  r.add("y", "CAUSES", "z", 0.9)
            r.add("x", "CAUSES",   "z", 0.85)
            b.programs.mine()
            r.add("p", "CONTROLS", "q", 0.8);  r.add("q", "CAUSES", "s", 0.8)
            b.programs.run_all()
            r.add("p", "CAUSES", "s", 0.75)
            b.programs.verify_derivations()
            hr = b.programs.stats()["hit_rate"]
            if hr is not None:
                assert 0.0 <= hr <= 1.0
        finally:
            _cleanup(db)


# ── Integration ────────────────────────────────────────────────────────────────

class TestOrchestratorIntegration:
    def test_orchestrator_has_programs(self):
        """brain.programs is an InferenceProgramEngine."""
        b, db = _brain()
        try:
            assert hasattr(b, "programs")
            assert isinstance(b.programs, InferenceProgramEngine)
        finally:
            _cleanup(db)

    def test_reflect_mines_and_runs(self):
        """reflect() should mine rules and run them when the graph has patterns."""
        b, db = _brain()
        try:
            r = b.relations
            # Two instances seeded — enough for mining
            r.add("wolves", "CONTROLS", "deer",    0.9)
            r.add("deer",   "CAUSES",   "erosion", 0.9)
            r.add("wolves", "CAUSES",   "erosion", 0.85)
            r.add("lions",  "CONTROLS", "gazelle", 0.9)
            r.add("gazelle","CAUSES",   "loss",    0.9)
            r.add("lions",  "CAUSES",   "loss",    0.85)
            # Novel chain for the rule to act on
            r.add("dogs",   "CONTROLS", "rabbits", 0.8)
            r.add("rabbits","CAUSES",   "damage",  0.8)
            b.reflect()
            # After reflect(), rules should have been authored and run
            stats = b.programs.stats()
            assert stats["total_programs"] >= 1, \
                "reflect() should have authored at least one rule"
        finally:
            _cleanup(db)


# ── Voice ─────────────────────────────────────────────────────────────────────

class TestVoiceRules:
    def test_compose_rule_returns_string(self):
        """voice._compose_rule() returns a non-empty string when rules exist."""
        b, db = _brain()
        try:
            r = b.relations
            r.add("a", "CONTROLS", "b", 0.9);  r.add("b", "CAUSES", "c", 0.9)
            r.add("a", "CAUSES",   "c", 0.85)
            r.add("x", "CONTROLS", "y", 0.9);  r.add("y", "CAUSES", "z", 0.9)
            r.add("x", "CAUSES",   "z", 0.85)
            b.programs.mine()
            stmt = b.voice._compose_rule()
            assert stmt is not None and isinstance(stmt, str) and len(stmt) > 10
        finally:
            _cleanup(db)

    def test_compose_rule_none_when_no_rules(self):
        """voice._compose_rule() returns None on a fresh brain with no patterns."""
        b, db = _brain()
        try:
            assert b.voice._compose_rule() is None
        finally:
            _cleanup(db)

    def test_say_rules_returns_string(self):
        """voice._say_rules() always returns a non-empty string."""
        b, db = _brain()
        try:
            reply = b.voice._say_rules()
            assert isinstance(reply, str) and len(reply) > 10
        finally:
            _cleanup(db)

    def test_say_rules_mentions_rule_language(self):
        """When rules exist, _say_rules() uses natural-language rule phrasing."""
        b, db = _brain()
        try:
            r = b.relations
            r.add("a", "CONTROLS", "b", 0.9);  r.add("b", "CAUSES", "c", 0.9)
            r.add("a", "CAUSES",   "c", 0.85)
            r.add("x", "CONTROLS", "y", 0.9);  r.add("y", "CAUSES", "z", 0.9)
            r.add("x", "CAUSES",   "z", 0.85)
            b.programs.mine()
            reply = b.voice._say_rules()
            # Should mention a rule-like phrase
            assert any(
                phrase in reply.lower()
                for phrase in ("rule", "pattern", "principle", "tends to", "worked out")
            ), f"_say_rules() should mention rule language, got: {reply}"
        finally:
            _cleanup(db)
