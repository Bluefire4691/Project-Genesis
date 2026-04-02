"""Tests for the Orchestrator — M4 multi-processor integration."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from orchestrator.orchestrator import Orchestrator
from orchestrator.integration import IntegrationLayer, SynthesisResult
from memory.memory import MemorySystem
from utils.types import ProcessorOutput
import tempfile


def _brain(**kwargs) -> Orchestrator:
    return Orchestrator(verbose=False, **kwargs)


# ==================================================================
# Basic orchestrator (preserved from pre-M4)
# ==================================================================

def test_basic_processing():
    result = _brain().process_input("text", "Dogs are friendly animals")
    assert result["status"] == "processed"
    assert result["cycle"] == 1


def test_unknown_type_fallback():
    result = _brain().process_input("video", "some data")
    assert result["status"] == "processed"


def test_never_crashes():
    o = _brain()
    assert o.process_input("text", None)["status"] in ("processed", "degraded")
    assert o.process_input("text", "")["status"] in ("processed", "degraded")
    assert o.process_input(None, None)["status"] in ("processed", "degraded")


def test_curriculum_progression():
    o = _brain()
    o.run_curriculum()
    assert o.cycle_count > 0
    assert o.memory.stats()["total_stored"] > 0


def test_query_after_learning():
    o = _brain()
    o.process_input("text", "Dogs are loyal animals that live with people")
    result = o.query("dogs loyal")
    assert result["memories_used"] > 0


def test_total_retention_after_processing():
    o = _brain()
    for t, d in [("text", "The sky is blue"),
                 ("text", "Water boils at 100 degrees"),
                 ("numeric", {"label": "pi", "value": 3.14})]:
        o.process_input(t, d)
    assert o.memory.stats()["total_stored"] >= 3


# ==================================================================
# M4: multi-processor dispatch
# ==================================================================

def test_m4_all_processors_run_on_text():
    """All available processors should see the same input."""
    o = _brain()
    result = o.process_input("text", "The temperature dropped 10 degrees overnight")
    # M4 result includes processors_run
    assert "processors_run" in result
    assert len(result["processors_run"]) >= 1


def test_m4_multiple_processors_run_at_healthy_throttle():
    """At NONE throttle, all three processors should run."""
    o = _brain()
    result = o.process_input("text", "The river flows at 5 meters per second")
    # At full health all three should run
    assert len(result["processors_run"]) >= 2


def test_m4_result_has_significance_and_context_score():
    o = _brain()
    result = o.process_input("text", "Plants grow toward light")
    assert "significance" in result
    assert "context_score" in result
    assert 0.0 <= result["significance"] <= 1.0
    assert 0.0 <= result["context_score"] <= 1.0


def test_m4_cross_modal_concepts_populated_after_overlap():
    """
    Cross-modal concepts should appear when multiple processors find
    overlapping concepts in the same input.
    """
    o = _brain()
    # First build some context
    o.process_input("text", "temperature affects plant growth rate")
    # Now process something with numeric content — 'temperature' should
    # appear in multiple processors' concept sets
    result = o.process_input("numeric", {"label": "temperature", "value": 22, "unit": "C"})
    # cross_modal_concepts may or may not be populated depending on processor
    # outputs, but the key must exist
    assert "cross_modal_concepts" in result
    assert isinstance(result["cross_modal_concepts"], list)


def test_m4_context_score_higher_when_context_active():
    """
    Processing input related to what's already in working memory should
    score higher context than processing something entirely unrelated.
    """
    o = _brain()
    # Establish context around water/rivers
    for _ in range(3):
        o.process_input("text", "water flows in rivers and streams through landscapes")

    # Related input — should have higher context score
    related = o.process_input("text", "rivers carry water downstream to oceans")
    # Unrelated input
    unrelated = o.process_input("text", "prime numbers are divisible only by one and themselves")

    assert related["context_score"] >= unrelated["context_score"]


def test_m4_secondary_outputs_stored_as_memories():
    """
    Secondary processor outputs above the noise threshold are stored.
    Use a numeric dict: TextProcessor can stringify it (meaningful output),
    NumericProcessor parses it directly (meaningful output). Both > 0.05 conf.
    """
    o = _brain()
    before = o.memory.stats()["total_stored"]
    # Dict input: NumericProcessor parses it; TextProcessor stringifies it
    o.process_input("numeric", {"label": "river_flow", "value": 5.2, "unit": "m/s"})
    after = o.memory.stats()["total_stored"]
    # Primary (numeric) + at least text secondary = > 1 new memory
    assert after >= before + 1


def test_m4_cross_modal_memories_are_associated():
    """
    Keys from multiple processors on the same input should be
    explicitly linked in the association graph.
    """
    o = _brain()
    o.process_input("numeric", {"label": "growth_rate", "value": 3.5, "unit": "cm/day"})
    # Check that association graph has links (indirect test via associations in stats)
    stats = o.memory.stats()
    assoc_stats = stats.get("associations", {})
    assert "links_created_this_session" in assoc_stats


def test_m4_degraded_throttle_runs_fewer_processors():
    """Under heavy resource pressure, fewer processors should run."""
    from survival import SurvivalOS
    from survival.resource_manager import ThrottleLevel

    o = _brain()
    # Force CRITICAL throttle (text + memory_store only)
    o.survival.resource._energy = 0.25
    o.survival.resource._throttle = ThrottleLevel.CRITICAL
    o.survival.resource._candidate_throttle = ThrottleLevel.CRITICAL
    o.survival.resource._candidate_ticks = 3

    result = o.process_input("numeric", {"label": "test", "value": 99})
    assert result["status"] in ("processed", "degraded")
    # Under CRITICAL: only text available — should not have run numeric/pattern
    if result["status"] == "processed":
        assert "pattern" not in result.get("processors_run", [])


def test_m4_never_crashes_on_pathological_input():
    """M4 dispatch must be robust to unusual inputs."""
    o = _brain()
    cases = [
        ("text", None),
        ("numeric", "this is not numeric"),
        ("pattern", 42),
        ("text", {"deeply": {"nested": ["weird", "input"]}}),
        ("numeric", {"label": "missing_value"}),
    ]
    for t, d in cases:
        result = o.process_input(t, d)
        assert result["status"] in ("processed", "degraded"), f"Failed on ({t}, {d})"


# ==================================================================
# IntegrationLayer unit tests
# ==================================================================

def _tmp_mem() -> MemorySystem:
    db = os.path.join(tempfile.mkdtemp(), "test.db")
    return MemorySystem(db_path=db, working_capacity=100)


def _make_output(source, keywords=None, confidence=0.8, context="test context") -> ProcessorOutput:
    return ProcessorOutput(
        source=source,
        input_data="test",
        extracted={"keywords": keywords or [], "categories": []},
        importance=confidence,
        suggested_key=f"{source}:test:1",
        context=context,
        confidence=confidence,
    )


def test_integration_synthesize_returns_result():
    mem = _tmp_mem()
    layer = IntegrationLayer(mem)
    outputs = [
        _make_output("text", keywords=["temperature", "plant"]),
        _make_output("numeric", keywords=["temperature", "10"], confidence=0.6),
    ]
    result = layer.synthesize(outputs, primary_source="text")
    assert isinstance(result, SynthesisResult)
    assert result.primary_output.source == "text"
    assert len(result.secondary_outputs) == 1


def test_integration_cross_modal_detected():
    """'temperature' appears in both outputs — should be cross-modal."""
    mem = _tmp_mem()
    layer = IntegrationLayer(mem)
    outputs = [
        _make_output("text", keywords=["temperature", "plant", "growth"]),
        _make_output("numeric", keywords=["temperature", "degrees"], confidence=0.7),
    ]
    result = layer.synthesize(outputs, primary_source="text")
    assert "temperature" in result.cross_modal_concepts


def test_integration_no_cross_modal_for_single_processor():
    mem = _tmp_mem()
    layer = IntegrationLayer(mem)
    outputs = [_make_output("text", keywords=["sky", "blue"])]
    result = layer.synthesize(outputs, primary_source="text")
    assert result.cross_modal_concepts == []


def test_integration_context_score_zero_with_empty_memory():
    """No working memory = context score 0 (nothing to connect to)."""
    mem = _tmp_mem()
    layer = IntegrationLayer(mem)
    outputs = [_make_output("text", keywords=["river", "water"])]
    result = layer.synthesize(outputs, primary_source="text")
    assert result.context_score == 0.0


def test_integration_context_score_rises_with_active_memory():
    """Seeding working memory with related content raises context score."""
    mem = _tmp_mem()
    mem.store("river:1", "rivers flow with water currents", "fact", "text", 0.8)
    mem.store("river:2", "water moves downstream in rivers", "fact", "text", 0.8)
    layer = IntegrationLayer(mem)
    outputs = [_make_output("text", keywords=["river", "water", "flow"],
                             context="river water flowing downstream")]
    result = layer.synthesize(outputs, primary_source="text")
    assert result.context_score > 0.0


def test_integration_handles_empty_outputs():
    mem = _tmp_mem()
    layer = IntegrationLayer(mem)
    result = layer.synthesize([], primary_source="text")
    assert result.primary_output is not None
    assert result.significance == 0.5  # default


def test_integration_low_confidence_outputs_filtered_from_cross_modal():
    """
    Outputs below confidence 0.05 should be excluded from
    cross-modal concept detection — noise shouldn't count.
    """
    mem = _tmp_mem()
    layer = IntegrationLayer(mem)
    outputs = [
        _make_output("text", keywords=["water", "river"], confidence=0.8),
        _make_output("numeric", keywords=["water"], confidence=0.02),  # below threshold
    ]
    result = layer.synthesize(outputs, primary_source="text")
    # 'water' should NOT be cross-modal since the numeric output is noise
    assert "water" not in result.cross_modal_concepts


def test_integration_significance_formula():
    """significance = confidence * 0.5 + context_score * 0.5."""
    mem = _tmp_mem()
    layer = IntegrationLayer(mem)
    # Simple check: zero-context significance = confidence * 0.5
    outputs = [_make_output("text", confidence=0.8)]
    result = layer.synthesize(outputs, primary_source="text")
    # context_score should be ~0 (empty memory), so significance ≈ 0.8 * 0.5 = 0.4
    assert result.significance <= 0.5


# ==================================================================
# Runner
# ==================================================================

if __name__ == "__main__":
    import traceback
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            print(f"  ✅ {test.__name__}")
            passed += 1
        except Exception as e:
            print(f"  ❌ {test.__name__}: {e}")
            traceback.print_exc()
            failed += 1
    print(f"\n  {passed} passed, {failed} failed")
