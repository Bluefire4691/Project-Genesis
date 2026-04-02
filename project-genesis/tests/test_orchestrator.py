"""Tests for the orchestrator — it must never crash."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from orchestrator.orchestrator import Orchestrator


def test_basic_processing():
    o = Orchestrator(verbose=False)
    result = o.process_input("text", "Dogs are friendly animals")
    assert result["status"] == "processed"
    assert result["cycle"] == 1


def test_unknown_type_fallback():
    """Unknown input types should route to fallback, not crash."""
    o = Orchestrator(verbose=False)
    result = o.process_input("video", "some data")
    assert result["status"] == "processed"  # Fell back to text processor


def test_never_crashes():
    """The orchestrator must handle anything without raising."""
    o = Orchestrator(verbose=False)
    # None input
    result = o.process_input("text", None)
    assert result["status"] in ("processed", "degraded")
    # Empty string
    result = o.process_input("text", "")
    assert result["status"] in ("processed", "degraded")
    # Bizarre input
    result = o.process_input(None, None)
    assert result["status"] in ("processed", "degraded")


def test_curriculum_progression():
    o = Orchestrator(verbose=False)
    o.run_curriculum()
    # Should have processed items and potentially advanced
    assert o.cycle_count > 0
    assert o.memory.stats()["total_stored"] > 0


def test_query_after_learning():
    o = Orchestrator(verbose=False)
    o.process_input("text", "Dogs are loyal animals that live with people")
    result = o.query("dogs loyal")
    assert result["memories_used"] > 0


def test_total_retention_after_processing():
    """Everything processed should be in memory."""
    o = Orchestrator(verbose=False)
    inputs = [
        ("text", "The sky is blue"),
        ("text", "Water boils at 100 degrees"),
        ("numeric", {"label": "pi", "value": 3.14}),
    ]
    for t, d in inputs:
        o.process_input(t, d)
    assert o.memory.stats()["total_stored"] >= 3


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            print(f"  ✅ {test.__name__}")
            passed += 1
        except Exception as e:
            print(f"  ❌ {test.__name__}: {e}")
            failed += 1
    print(f"\n  {passed} passed, {failed} failed")
