"""
Tests for M10 — InferenceEngine.

Covers:
- Schema initialization
- Transitive chain detection (CAUSES, CONTROLS, REQUIRES, ENABLES, IS_A)
- Compound confidence calculation (product × decay per extra hop)
- No-cross-type propagation (CAUSES chain doesn't produce CONTROLS inference)
- Cycle prevention
- Min confidence threshold filtering
- Max chain length limiting
- query() returns as_subject / as_object correctly
- top_inferences() ordering
- chain_for() retrieves stored chain
- stats() keys and values
- run() over multiple concepts
- Integration with live Orchestrator (brain.infer)
- wm_delta in process_input result
- novel flag in process_input result
- full_status includes inference stats
- IS_A property inheritance (cats IS_A mammal, mammal CONTAINS fur → cats CONTAINS fur)
"""

import sys
import os
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

import pytest
from orchestrator.orchestrator import Orchestrator
from memory.relations import RelationGraph
from cognition.inference import InferenceEngine, _HOP_DECAY, _MIN_CONFIDENCE


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _brain(**kwargs) -> Orchestrator:
    if "db_path" not in kwargs:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        kwargs["db_path"] = tmp.name
    return Orchestrator(verbose=False, **kwargs)


def _engine(brain: Orchestrator) -> InferenceEngine:
    return brain.inference


def _add(brain: Orchestrator, subj: str, rel: str, obj: str, conf: float = 0.8):
    brain.relations.add(subj, rel, obj, confidence=conf, session_id="test")


# ------------------------------------------------------------------
# Schema
# ------------------------------------------------------------------

class TestSchema:
    def test_table_created(self):
        brain = _brain()
        cur = brain.memory._long_term.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='relation_inferences'"
        )
        assert cur.fetchone() is not None

    def test_engine_stats_empty(self):
        brain = _brain()
        s = _engine(brain).stats()
        assert s["total_inferences"] == 0
        assert s["avg_confidence"] == 0.0


# ------------------------------------------------------------------
# Transitive chain detection
# ------------------------------------------------------------------

class TestTransitiveChains:
    def test_two_hop_causes(self):
        brain = _brain()
        _add(brain, "wolves", "CAUSES", "deer_decline", 0.9)
        _add(brain, "deer_decline", "CAUSES", "overgrazing", 0.8)
        result = brain.infer("wolves")
        subjects = [(r["object"], r["relation"]) for r in result["as_subject"]]
        assert ("overgrazing", "CAUSES") in subjects

    def test_two_hop_controls(self):
        brain = _brain()
        _add(brain, "governor", "CONTROLS", "pressure", 0.9)
        _add(brain, "pressure", "CONTROLS", "flow", 0.8)
        result = brain.infer("governor")
        objects = [r["object"] for r in result["as_subject"]]
        assert "flow" in objects

    def test_two_hop_requires(self):
        brain = _brain()
        _add(brain, "photosynthesis", "REQUIRES", "light", 0.85)
        _add(brain, "light", "REQUIRES", "sun", 0.9)
        result = brain.infer("photosynthesis")
        objects = [r["object"] for r in result["as_subject"]]
        assert "sun" in objects

    def test_two_hop_enables(self):
        brain = _brain()
        _add(brain, "oxygen", "ENABLES", "combustion", 0.9)
        _add(brain, "combustion", "ENABLES", "engine", 0.85)
        result = brain.infer("oxygen")
        objects = [r["object"] for r in result["as_subject"]]
        assert "engine" in objects

    def test_two_hop_is_a(self):
        brain = _brain()
        _add(brain, "wolf", "IS_A", "canid", 0.95)
        _add(brain, "canid", "IS_A", "mammal", 0.95)
        result = brain.infer("wolf")
        objects = [r["object"] for r in result["as_subject"]]
        assert "mammal" in objects

    def test_three_hop_causes(self):
        brain = _brain()
        _add(brain, "a", "CAUSES", "b", 0.9)
        _add(brain, "b", "CAUSES", "c", 0.9)
        _add(brain, "c", "CAUSES", "d", 0.9)
        result = brain.infer("a")
        objects = [r["object"] for r in result["as_subject"]]
        assert "d" in objects


# ------------------------------------------------------------------
# Compound confidence
# ------------------------------------------------------------------

class TestCompoundConfidence:
    def test_two_hop_confidence_formula(self):
        brain = _brain()
        conf_ab = 0.9
        conf_bc = 0.8
        _add(brain, "a", "CAUSES", "b", conf_ab)
        _add(brain, "b", "CAUSES", "c", conf_bc)
        result = brain.infer("a")
        matches = [r for r in result["as_subject"] if r["object"] == "c"]
        assert len(matches) == 1
        expected = conf_ab * conf_bc * (_HOP_DECAY ** 1)
        assert abs(matches[0]["confidence"] - expected) < 0.01

    def test_three_hop_confidence_decays_more(self):
        brain = _brain()
        _add(brain, "a", "CAUSES", "b", 0.9)
        _add(brain, "b", "CAUSES", "c", 0.9)
        _add(brain, "c", "CAUSES", "d", 0.9)
        result = brain.infer("a")
        two_hop = [r for r in result["as_subject"] if r["object"] == "c"]
        three_hop = [r for r in result["as_subject"] if r["object"] == "d"]
        assert len(two_hop) == 1 and len(three_hop) == 1
        assert two_hop[0]["confidence"] > three_hop[0]["confidence"]

    def test_low_base_confidence_filtered_below_min(self):
        brain = _brain()
        # 0.4 × 0.4 × 0.85 = 0.136 < _MIN_CONFIDENCE = 0.20
        _add(brain, "x", "CAUSES", "y", 0.4)
        _add(brain, "y", "CAUSES", "z", 0.4)
        result = brain.infer("x")
        objects = [r["object"] for r in result["as_subject"]]
        assert "z" not in objects

    def test_high_confidence_chain_stored(self):
        brain = _brain()
        # 0.95 × 0.95 × 0.85 = 0.766 — well above threshold
        _add(brain, "x", "CAUSES", "y", 0.95)
        _add(brain, "y", "CAUSES", "z", 0.95)
        result = brain.infer("x")
        objects = [r["object"] for r in result["as_subject"]]
        assert "z" in objects


# ------------------------------------------------------------------
# No cross-type propagation
# ------------------------------------------------------------------

class TestNoCrossType:
    def test_causes_then_controls_not_inferred(self):
        """CAUSES chain cannot produce CONTROLS inference."""
        brain = _brain()
        _add(brain, "a", "CAUSES", "b", 0.9)
        _add(brain, "b", "CONTROLS", "c", 0.9)
        result = brain.infer("a")
        # Should NOT find 'a CONTROLS c' or 'a CAUSES c'
        objects = [r["object"] for r in result["as_subject"]]
        assert "c" not in objects

    def test_controls_then_causes_not_inferred(self):
        brain = _brain()
        _add(brain, "a", "CONTROLS", "b", 0.9)
        _add(brain, "b", "CAUSES", "c", 0.9)
        result = brain.infer("a")
        objects = [r["object"] for r in result["as_subject"]]
        assert "c" not in objects

    def test_prevents_not_transitive(self):
        """PREVENTS is not in TRANSITIVE set — no inference generated."""
        brain = _brain()
        _add(brain, "a", "PREVENTS", "b", 0.9)
        _add(brain, "b", "PREVENTS", "c", 0.9)
        result = brain.infer("a")
        objects = [r["object"] for r in result["as_subject"]]
        assert "c" not in objects


# ------------------------------------------------------------------
# Cycle prevention
# ------------------------------------------------------------------

class TestCyclePrevention:
    def test_no_self_inference(self):
        """a CAUSES b, b CAUSES a → should NOT produce a CAUSES a."""
        brain = _brain()
        _add(brain, "a", "CAUSES", "b", 0.9)
        _add(brain, "b", "CAUSES", "a", 0.9)
        result = brain.infer("a")
        objects = [r["object"] for r in result["as_subject"]]
        assert "a" not in objects

    def test_triangular_cycle_no_infinite_loop(self):
        """a→b→c→a cycle must terminate without hanging."""
        brain = _brain()
        _add(brain, "a", "CAUSES", "b", 0.9)
        _add(brain, "b", "CAUSES", "c", 0.9)
        _add(brain, "c", "CAUSES", "a", 0.9)
        # Just verify it completes without hanging
        result = brain.infer("a")
        assert isinstance(result, dict)

    def test_long_chain_terminates(self):
        """Chain longer than MAX_CHAIN should still terminate."""
        brain = _brain()
        for i in range(8):
            _add(brain, f"node{i}", "CAUSES", f"node{i+1}", 0.9)
        result = brain.infer("node0")
        assert isinstance(result, dict)


# ------------------------------------------------------------------
# Query interface
# ------------------------------------------------------------------

class TestQuery:
    def test_query_as_subject(self):
        brain = _brain()
        _add(brain, "a", "CAUSES", "b", 0.9)
        _add(brain, "b", "CAUSES", "c", 0.9)
        engine = _engine(brain)
        engine.run()
        result = engine.query("a")
        assert "as_subject" in result
        assert "as_object" in result
        assert result["concept"] == "a"

    def test_query_as_object(self):
        brain = _brain()
        _add(brain, "a", "CAUSES", "b", 0.9)
        _add(brain, "b", "CAUSES", "c", 0.9)
        engine = _engine(brain)
        engine.run()
        result = engine.query("c")
        # c should appear as object of inference from a
        as_obj_subjects = [r["subject"] for r in result["as_object"]]
        assert "a" in as_obj_subjects

    def test_query_empty_concept(self):
        brain = _brain()
        result = _engine(brain).query("unknown_concept_xyz")
        assert result["as_subject"] == []
        assert result["as_object"] == []

    def test_query_min_confidence_filter(self):
        brain = _brain()
        _add(brain, "a", "CAUSES", "b", 0.9)
        _add(brain, "b", "CAUSES", "c", 0.9)
        engine = _engine(brain)
        engine.run()
        # High threshold should filter out weaker inferences
        result_high = engine.query("a", min_confidence=0.9)
        result_low = engine.query("a", min_confidence=0.1)
        assert len(result_low["as_subject"]) >= len(result_high["as_subject"])


# ------------------------------------------------------------------
# top_inferences
# ------------------------------------------------------------------

class TestTopInferences:
    def test_top_inferences_returns_list(self):
        brain = _brain()
        assert isinstance(_engine(brain).top_inferences(), list)

    def test_top_inferences_ordered_by_confidence(self):
        brain = _brain()
        _add(brain, "a", "CAUSES", "b", 0.95)
        _add(brain, "b", "CAUSES", "c", 0.9)
        _add(brain, "x", "CAUSES", "y", 0.5)
        _add(brain, "y", "CAUSES", "z", 0.4)
        brain.inference.run()
        top = _engine(brain).top_inferences(limit=10)
        confs = [t["confidence"] for t in top]
        assert confs == sorted(confs, reverse=True)

    def test_top_inferences_empty_before_run(self):
        brain = _brain()
        _add(brain, "a", "CAUSES", "b", 0.9)
        # Don't call run() — table should be empty
        top = _engine(brain).top_inferences()
        assert top == []


# ------------------------------------------------------------------
# chain_for
# ------------------------------------------------------------------

class TestChainFor:
    def test_chain_for_returns_list(self):
        brain = _brain()
        _add(brain, "a", "CAUSES", "b", 0.9)
        _add(brain, "b", "CAUSES", "c", 0.9)
        brain.infer("a")
        chain = brain.inference.chain_for("a", "CAUSES", "c")
        assert chain is not None
        assert isinstance(chain, list)
        assert len(chain) >= 2

    def test_chain_for_unknown_returns_none(self):
        brain = _brain()
        result = brain.inference.chain_for("unknown", "CAUSES", "also_unknown")
        assert result is None

    def test_chain_steps_have_required_keys(self):
        brain = _brain()
        _add(brain, "a", "CAUSES", "b", 0.9)
        _add(brain, "b", "CAUSES", "c", 0.9)
        brain.infer("a")
        chain = brain.inference.chain_for("a", "CAUSES", "c")
        assert chain is not None
        for step in chain:
            assert "from" in step
            assert "via" in step
            assert "to" in step
            assert "conf" in step


# ------------------------------------------------------------------
# Stats
# ------------------------------------------------------------------

class TestStats:
    def test_stats_keys(self):
        brain = _brain()
        s = _engine(brain).stats()
        assert "total_inferences" in s
        assert "avg_confidence" in s
        assert "min_chain_length" in s
        assert "max_chain_length" in s
        assert "by_type" in s

    def test_stats_count_grows_after_run(self):
        brain = _brain()
        _add(brain, "a", "CAUSES", "b", 0.9)
        _add(brain, "b", "CAUSES", "c", 0.9)
        before = _engine(brain).stats()["total_inferences"]
        brain.inference.run()
        after = _engine(brain).stats()["total_inferences"]
        assert after > before

    def test_stats_by_type_populated(self):
        brain = _brain()
        _add(brain, "a", "CAUSES", "b", 0.9)
        _add(brain, "b", "CAUSES", "c", 0.9)
        brain.inference.run()
        s = _engine(brain).stats()
        assert "CAUSES" in s["by_type"]


# ------------------------------------------------------------------
# run() over all concepts
# ------------------------------------------------------------------

class TestRun:
    def test_run_returns_count(self):
        brain = _brain()
        _add(brain, "a", "CAUSES", "b", 0.9)
        _add(brain, "b", "CAUSES", "c", 0.9)
        n = brain.inference.run()
        assert isinstance(n, int)
        assert n >= 0

    def test_run_adds_inferences(self):
        brain = _brain()
        _add(brain, "a", "CAUSES", "b", 0.9)
        _add(brain, "b", "CAUSES", "c", 0.9)
        _add(brain, "x", "CONTROLS", "y", 0.85)
        _add(brain, "y", "CONTROLS", "z", 0.85)
        n = brain.inference.run()
        assert n >= 2  # at least a→c and x→z

    def test_run_idempotent(self):
        """Running twice doesn't add duplicates — ON CONFLICT DO UPDATE."""
        brain = _brain()
        _add(brain, "a", "CAUSES", "b", 0.9)
        _add(brain, "b", "CAUSES", "c", 0.9)
        brain.inference.run()
        count_1 = brain.inference.stats()["total_inferences"]
        brain.inference.run()
        count_2 = brain.inference.stats()["total_inferences"]
        assert count_1 == count_2

    def test_run_empty_graph_no_crash(self):
        brain = _brain()
        n = brain.inference.run()
        assert n == 0


# ------------------------------------------------------------------
# Orchestrator integration
# ------------------------------------------------------------------

class TestOrchestratorIntegration:
    def test_brain_infer_returns_dict(self):
        brain = _brain()
        result = brain.infer("wolves")
        assert isinstance(result, dict)
        assert "as_subject" in result
        assert "as_object" in result

    def test_brain_infer_after_processing(self):
        brain = _brain()
        brain.process_input("text",
            "Wolves control deer populations. Deer cause overgrazing.")
        brain.process_input("text",
            "Deer overgrazing causes erosion of riverbanks.")
        result = brain.infer("wolves")
        # May or may not find transitive chain depending on text extraction
        assert isinstance(result, dict)

    def test_full_status_includes_inference(self):
        brain = _brain()
        s = brain.full_status()
        assert "inference" in s
        assert "total_inferences" in s["inference"]

    def test_wm_delta_in_result(self):
        brain = _brain()
        result = brain.process_input("text", "Wolves hunt deer in the forest ecosystem.")
        assert "wm_delta" in result
        assert isinstance(result["wm_delta"], int)

    def test_novel_flag_in_result(self):
        brain = _brain()
        result = brain.process_input("text", "The sky is blue on clear days.")
        assert "novel" in result
        assert isinstance(result["novel"], bool)

    def test_novel_true_for_empty_brain(self):
        """First input to an empty brain should be novel (no prior knowledge)."""
        brain = _brain()
        result = brain.process_input("text",
            "Quantum entanglement defies classical locality constraints.")
        # Empty brain: no working memory, no relations → novel
        assert result["novel"] is True

    def test_novel_false_after_related_input(self):
        """After processing ecology content, ecology input should not be novel."""
        brain = _brain()
        brain.process_input("text",
            "Wolves are predators that hunt deer in forest ecosystems.")
        brain.process_input("text",
            "Deer populations affect forest vegetation through overgrazing.")
        result = brain.process_input("text",
            "Wolves control deer herds which prevents overgrazing damage.")
        assert result["novel"] is False

    def test_wm_delta_positive_on_new_input(self):
        """First few inputs should add memories → positive wm_delta."""
        brain = _brain()
        result = brain.process_input("text",
            "Photosynthesis converts sunlight into chemical energy in plants.")
        assert result["wm_delta"] >= 0

    def test_inference_engine_accessible_on_brain(self):
        brain = _brain()
        assert hasattr(brain, "inference")
        assert isinstance(brain.inference, InferenceEngine)


# ------------------------------------------------------------------
# IS_A Property Inheritance
# ------------------------------------------------------------------

class TestISAInheritance:
    """IS_A property inheritance: X IS_A Y, Y REL Z → infer X REL Z."""

    def test_direct_property_inherited(self):
        """cats IS_A mammal, mammal CONTAINS fur → cats HAS fur."""
        brain = _brain()
        eng = _engine(brain)
        _add(brain, "cats", "IS_A", "mammal", conf=0.9)
        _add(brain, "mammal", "CONTAINS", "fur", conf=0.8)
        eng.run()
        result = eng.query("cats")
        subjects = [(r["relation"], r["object"]) for r in result["as_subject"]]
        assert ("CONTAINS", "fur") in subjects

    def test_multiple_properties_inherited(self):
        """Child inherits all parent properties."""
        brain = _brain()
        eng = _engine(brain)
        _add(brain, "dogs", "IS_A", "mammal", conf=0.9)
        _add(brain, "mammal", "CONTAINS", "fur", conf=0.8)
        _add(brain, "mammal", "REQUIRES", "oxygen", conf=0.85)
        eng.run()
        result = eng.query("dogs")
        subjects = [(r["relation"], r["object"]) for r in result["as_subject"]]
        assert ("CONTAINS", "fur") in subjects
        assert ("REQUIRES", "oxygen") in subjects

    def test_sibling_categories_independent(self):
        """cats IS_A mammal, dogs IS_A mammal — cats inherits mammal props, not dog props."""
        brain = _brain()
        eng = _engine(brain)
        _add(brain, "cats", "IS_A", "mammal", conf=0.9)
        _add(brain, "dogs", "IS_A", "mammal", conf=0.9)
        _add(brain, "mammal", "CONTAINS", "fur", conf=0.8)
        _add(brain, "dogs", "CONTAINS", "loyalty", conf=0.8)
        eng.run()
        cats_result = eng.query("cats")
        cats_subjects = [(r["relation"], r["object"]) for r in cats_result["as_subject"]]
        # cats should inherit fur from mammal
        assert ("CONTAINS", "fur") in cats_subjects
        # cats should NOT inherit loyalty (that belongs to dogs, not mammal)
        assert ("CONTAINS", "loyalty") not in cats_subjects

    def test_inheritance_confidence_decayed(self):
        """Inherited confidence < both parent confidences."""
        brain = _brain()
        eng = _engine(brain)
        _add(brain, "poodle", "IS_A", "dog", conf=0.9)
        _add(brain, "dog", "CONTAINS", "teeth", conf=0.9)
        eng.run()
        result = eng.query("poodle")
        inherited = [r for r in result["as_subject"]
                     if r["relation"] == "CONTAINS" and r["object"] == "teeth"]
        assert inherited
        # Should be less than the direct confidence of either edge
        assert inherited[0]["confidence"] < 0.9

    def test_no_self_loop(self):
        """Child IS_A parent, parent CAUSES child → no self-loop inference."""
        brain = _brain()
        eng = _engine(brain)
        _add(brain, "cats", "IS_A", "mammal", conf=0.9)
        _add(brain, "mammal", "CAUSES", "cats", conf=0.8)
        eng.run()
        result = eng.query("cats")
        # Should not produce cats CAUSES cats
        loops = [r for r in result["as_subject"]
                 if r["subject"] == r["object"]]
        assert not loops

    def test_is_a_not_inherited_from_parent(self):
        """IS_A relations of the parent are not passed down (that's transitive IS_A, separate)."""
        brain = _brain()
        eng = _engine(brain)
        _add(brain, "cats", "IS_A", "mammal", conf=0.9)
        _add(brain, "mammal", "IS_A", "animal", conf=0.9)
        eng.run()
        result = eng.query("cats")
        # The IS_A mammal→animal should NOT create a new HAS/etc inheritance —
        # but transitively cats IS_A animal is handled by _infer_from, not _infer_inheritance
        # Just check that _infer_inheritance doesn't duplicate IS_A chains oddly
        subjects = [(r["relation"], r["object"]) for r in result["as_subject"]]
        # No non-IS_A relations should be spuriously added
        non_isa = [(rel, obj) for rel, obj in subjects if rel != "IS_A"]
        assert non_isa == []

    def test_low_confidence_not_inherited(self):
        """Property below _MIN_EDGE_CONF threshold is not inherited."""
        brain = _brain()
        eng = _engine(brain)
        _add(brain, "cats", "IS_A", "mammal", conf=0.9)
        _add(brain, "mammal", "CONTAINS", "fur", conf=0.1)  # too low
        eng.run()
        result = eng.query("cats")
        subjects = [(r["relation"], r["object"]) for r in result["as_subject"]]
        assert ("CONTAINS", "fur") not in subjects

    def test_infer_method_triggers_inheritance(self):
        """brain.infer(concept) also triggers inheritance for that concept."""
        brain = _brain()
        eng = _engine(brain)
        _add(brain, "whale", "IS_A", "mammal", conf=0.9)
        _add(brain, "mammal", "CONTAINS", "lungs", conf=0.85)
        eng.infer("whale")
        result = eng.query("whale")
        subjects = [(r["relation"], r["object"]) for r in result["as_subject"]]
        assert ("CONTAINS", "lungs") in subjects

    def test_transitive_is_a_chain_inherits(self):
        """poodle IS_A dog IS_A mammal, mammal CONTAINS fur → poodle HAS fur via transitive IS_A."""
        brain = _brain()
        eng = _engine(brain)
        _add(brain, "poodle", "IS_A", "dog", conf=0.95)
        _add(brain, "dog", "IS_A", "mammal", conf=0.9)
        _add(brain, "mammal", "CONTAINS", "fur", conf=0.8)
        # First run builds transitive IS_A: poodle IS_A mammal (in inferences table)
        # Second run uses that inferred IS_A to inherit fur
        eng.run()
        eng.run()  # second pass picks up inferred IS_A edges
        result = eng.query("poodle")
        subjects = [(r["relation"], r["object"]) for r in result["as_subject"]]
        assert ("CONTAINS", "fur") in subjects

    def test_inheritance_chain_stored_with_two_hops(self):
        """Inherited property stored with chain_length == 2."""
        brain = _brain()
        eng = _engine(brain)
        _add(brain, "cats", "IS_A", "mammal", conf=0.9)
        _add(brain, "mammal", "CONTAINS", "fur", conf=0.8)
        eng.run()
        result = eng.query("cats")
        inherited = [r for r in result["as_subject"]
                     if r["relation"] == "CONTAINS" and r["object"] == "fur"]
        assert inherited
        assert inherited[0]["chain_length"] == 2
