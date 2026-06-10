"""
Tests for M27 SelfModel — Genesis knows what it knows.

Verifies that Genesis:
1. Assesses a known concept accurately (coverage, confidence, verdict)
2. Returns honest zeros for an unknown concept — never fabricates
3. Detects contested beliefs (held contradictions cap the verdict)
4. Tiers verdicts: unknown / sparse / partial / solid
5. Surfaces derived conclusions and open hypotheses in the assessment
6. Provides a global overview and strongest/weakest concept rankings
7. Is callable: brain.self_model("wolves") works directly
8. Conversation: "how well do you understand X?" answers qualitatively
   differently for well-known vs. unknown concepts (roadmap test 3)
9. Is strictly read-only — assessing never modifies the relation graph
"""
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from cognition.self_model import SelfModel


def _brain():
    """Fresh orchestrator on a tempfile DB — count assertions need isolation."""
    from orchestrator.orchestrator import Orchestrator
    db = tempfile.mktemp(suffix=".db")
    b = Orchestrator(verbose=False, db_path=db)
    return b, db


def _cleanup(db):
    if os.path.exists(db):
        os.unlink(db)


def _seed_solid(r, concept="wolves"):
    """Give a concept solid coverage: 8+ high-confidence relations."""
    r.add(concept, "CONTROLS", "deer", 0.85)
    r.add(concept, "PREDATES", "elk", 0.85)
    r.add(concept, "IS_A", "predator", 0.9)
    r.add(concept, "PREVENTS", "overgrazing", 0.8)
    r.add(concept, "AFFECTS", "rivers", 0.75)
    r.add(concept, "REQUIRES", "territory", 0.8)
    r.add("parks", "CONTAINS", concept, 0.8)
    r.add("hunting", "AFFECTS", concept, 0.75)


# ── Per-concept assessment ───────────────────────────────────────────────────

class TestAssessment:
    def test_known_concept_assessed(self):
        """Roadmap test 1: known concept → confidence > 0.6, relation_count > 0."""
        b, db = _brain()
        try:
            _seed_solid(b.relations)
            a = b.self_model("wolves")
            assert a["relation_count"] > 0
            assert a["confidence"] > 0.6
            assert a["verdict"] in ("partial", "solid")
        finally:
            _cleanup(db)

    def test_unknown_concept_honest_zeros(self):
        """Roadmap test 2: unknown concept → confidence 0, relation_count 0."""
        b, db = _brain()
        try:
            a = b.self_model("phlogiston")
            assert a["relation_count"] == 0
            assert a["confidence"] == 0.0
            assert a["verdict"] == "unknown"
        finally:
            _cleanup(db)

    def test_subject_object_split(self):
        b, db = _brain()
        try:
            r = b.relations
            r.add("wolves", "CONTROLS", "deer", 0.8)   # wolves as subject
            r.add("parks", "CONTAINS", "wolves", 0.8)  # wolves as object
            a = b.self_model("wolves")
            assert a["as_subject"] == 1
            assert a["as_object"] == 1
            assert a["relation_count"] == 2
        finally:
            _cleanup(db)

    def test_has_definition_detected(self):
        b, db = _brain()
        try:
            b.relations.add("wolves", "IS_A", "predator", 0.9)
            a = b.self_model("wolves")
            assert a["has_definition"] is True
            b.relations.add("deer", "CAUSES", "overgrazing", 0.9)
            a2 = b.self_model("deer")
            assert a2["has_definition"] is False
        finally:
            _cleanup(db)


# ── Verdict tiers ─────────────────────────────────────────────────────────────

class TestVerdicts:
    def test_sparse_for_thin_coverage(self):
        b, db = _brain()
        try:
            b.relations.add("axolotl", "IS_A", "amphibian", 0.8)
            a = b.self_model("axolotl")
            assert a["verdict"] == "sparse"
        finally:
            _cleanup(db)

    def test_sparse_for_low_confidence(self):
        b, db = _brain()
        try:
            r = b.relations
            r.add("quark", "IS_A", "particle", 0.35)
            r.add("quark", "CONTAINS", "charge", 0.35)
            r.add("quark", "AFFECTS", "matter", 0.35)
            r.add("atoms", "CONTAINS", "quark", 0.35)
            a = b.self_model("quark")
            assert a["verdict"] == "sparse", \
                "many edges at low confidence is still sparse understanding"
        finally:
            _cleanup(db)

    def test_solid_for_rich_confident_coverage(self):
        b, db = _brain()
        try:
            _seed_solid(b.relations)
            a = b.self_model("wolves")
            assert a["verdict"] == "solid"
        finally:
            _cleanup(db)

    def test_contested_caps_at_partial(self):
        """A held contradiction prevents 'solid' regardless of coverage."""
        b, db = _brain()
        try:
            _seed_solid(b.relations)
            b.relations.add("wolves", "CAUSES", "erosion", 0.8)
            b.relations.add("wolves", "PREVENTS", "erosion", 0.8)
            b.contradictions.scan(session_id="t")
            a = b.self_model("wolves")
            assert a["contested_count"] >= 1
            assert a["verdict"] == "partial", \
                "contested beliefs must cap the verdict at partial"
        finally:
            _cleanup(db)


# ── Evidence sources ──────────────────────────────────────────────────────────

class TestEvidenceSources:
    def test_open_hypotheses_counted(self):
        b, db = _brain()
        try:
            r = b.relations
            r.add("wolves", "CAUSES", "deer decline", 0.9)
            r.add("deer decline", "CAUSES", "vegetation recovery", 0.9)
            b.hypotheses.generate()
            a = b.self_model("wolves")
            assert a["open_hypotheses"] >= 1
        finally:
            _cleanup(db)

    def test_inferences_counted(self):
        b, db = _brain()
        try:
            r = b.relations
            r.add("wolves", "CONTROLS", "deer", 0.9)
            r.add("deer", "CAUSES", "overgrazing", 0.9)
            b.inference.run(session_id="t")
            a = b.self_model("wolves")
            assert a["inference_count"] >= 1
        finally:
            _cleanup(db)


# ── Global overview ───────────────────────────────────────────────────────────

class TestOverview:
    def test_overview_structure(self):
        b, db = _brain()
        try:
            o = b.self_model.overview()
            for key in ("total_relations", "total_concepts", "mean_confidence",
                        "contested_total", "strongest", "weakest"):
                assert key in o, f"missing key: {key}"
        finally:
            _cleanup(db)

    def test_overview_counts(self):
        b, db = _brain()
        try:
            _seed_solid(b.relations)
            o = b.self_model.overview()
            assert o["total_relations"] >= 8
            assert o["total_concepts"] >= 5
            assert 0.0 < o["mean_confidence"] <= 1.0
        finally:
            _cleanup(db)

    def test_weakest_ranks_low_confidence_first(self):
        b, db = _brain()
        try:
            r = b.relations
            _seed_solid(r, "wolves")
            r.add("muon", "IS_A", "particle", 0.3)
            weakest = b.self_model.weakest_concepts(limit=5)
            assert weakest, "should rank at least one concept"
            names = [w["concept"] for w in weakest]
            assert "muon" in names
            # wolves (high coverage × confidence) must rank weaker-last
            assert names.index("muon") < (
                names.index("wolves") if "wolves" in names else len(names)
            )
        finally:
            _cleanup(db)

    def test_strongest_ranks_solid_first(self):
        b, db = _brain()
        try:
            r = b.relations
            _seed_solid(r, "wolves")
            r.add("muon", "IS_A", "particle", 0.3)
            strongest = b.self_model.strongest_concepts(limit=3)
            assert strongest and strongest[0]["concept"] == "wolves"
        finally:
            _cleanup(db)


# ── Interface + separation ────────────────────────────────────────────────────

class TestInterface:
    def test_orchestrator_has_callable_self_model(self):
        b, db = _brain()
        try:
            assert isinstance(b.self_model, SelfModel)
            a = b.self_model("anything")
            assert isinstance(a, dict) and "verdict" in a
        finally:
            _cleanup(db)

    def test_assess_is_read_only(self):
        """Assessing a concept must never modify the relation graph."""
        b, db = _brain()
        try:
            _seed_solid(b.relations)
            before = b.relations.stats()["total_relations"]
            b.self_model("wolves")
            b.self_model("phlogiston")
            b.self_model.overview()
            after = b.relations.stats()["total_relations"]
            assert after == before
        finally:
            _cleanup(db)


# ── Conversation integration (roadmap test 3) ─────────────────────────────────

class TestConversation:
    def test_known_vs_unknown_qualitatively_different(self):
        b, db = _brain()
        try:
            _seed_solid(b.relations)
            known = b.voice.chat_respond("how well do you understand wolves?")
            unknown = b.voice.chat_respond("how well do you understand phlogiston?")
            assert known != unknown
            # The known answer reports actual coverage
            assert "connection" in known.lower()
            # The unknown answer admits ignorance rather than performing
            assert any(
                phrase in unknown.lower()
                for phrase in ("not at all", "nothing", "barely", "don't know")
            ), f"unknown-concept reply should admit ignorance, got: {unknown}"
        finally:
            _cleanup(db)

    def test_contested_concept_mentions_conflict(self):
        b, db = _brain()
        try:
            _seed_solid(b.relations)
            b.relations.add("wolves", "CAUSES", "erosion", 0.8)
            b.relations.add("wolves", "PREVENTS", "erosion", 0.8)
            b.contradictions.scan(session_id="t")
            reply = b.voice.chat_respond("how well do you know wolves?")
            assert "conflict" in reply.lower() or "haven't settled" in reply.lower(), \
                f"reply should disclose the contested belief, got: {reply}"
        finally:
            _cleanup(db)

    def test_say_understanding_resolves_multiword_topic(self):
        """'plate tectonics' should resolve to whichever form the graph holds."""
        b, db = _brain()
        try:
            r = b.relations
            r.add("tectonics", "CAUSES", "earthquakes", 0.85)
            r.add("tectonics", "CAUSES", "mountains", 0.85)
            r.add("tectonics", "IS_A", "geological process", 0.85)
            reply = b.voice._say_understanding("plate tectonics")
            assert "tectonics" in reply.lower()
            assert "connection" in reply.lower()
        finally:
            _cleanup(db)
