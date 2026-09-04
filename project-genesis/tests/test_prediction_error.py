"""
Tests for M15 — Prediction Error Salience.

Prediction error is Genesis's belief-model-based surprise signal: how
unexpected is an input given what Genesis already knows? A concept with
many high-confidence relations generates low error; an unknown concept
generates maximum error. This replaces the heuristic wm_delta boost as
the primary driver of archive significance.

Grounded in Friston (2010): all learning is minimization of prediction
error against an internal generative model.
"""

import sys
import os
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from orchestrator.orchestrator import Orchestrator
from utils.types import Stage


def _brain(**kwargs) -> Orchestrator:
    if "db_path" not in kwargs:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        kwargs["db_path"] = tmp.name
    b = Orchestrator(verbose=False, **kwargs)
    b.curriculum.current_stage = Stage.OPEN
    return b


# ==================================================================
# RelationGraph.prediction_error() unit tests
# ==================================================================

def test_unknown_concept_has_max_error():
    b = _brain()
    err = b.relations.prediction_error(["completely_unknown_xyzzy"])
    assert err == 1.0, f"Unknown concept should have error=1.0, got {err}"


def test_empty_concepts_returns_neutral():
    b = _brain()
    err = b.relations.prediction_error([])
    assert err == 0.5, f"Empty list should return 0.5, got {err}"


def test_known_concept_has_lower_error():
    b = _brain()
    # Teach Genesis about neuron with multiple high-confidence relations
    for s in [
        "A neuron is a cell.",
        "A neuron contains dendrites.",
        "A neuron enables signaling.",
        "A neuron is a biological unit.",
    ]:
        b.process_input("text", s)
    err_known = b.relations.prediction_error(["neuron"])
    err_unknown = b.relations.prediction_error(["xyzzy_unknown"])
    assert err_known < err_unknown, (
        f"Known concept should have lower error: known={err_known}, "
        f"unknown={err_unknown}"
    )


def test_error_is_bounded():
    b = _brain()
    for s in ["A mammal is a vertebrate.", "A mammal contains hair."]:
        b.process_input("text", s)
    err = b.relations.prediction_error(["mammal", "cell", "completely_unknown"])
    assert 0.0 <= err <= 1.0, f"Error should be in [0, 1]: {err}"


def test_mixed_concepts_averages_error():
    b = _brain()
    for s in ["A neuron is a cell.", "A neuron contains dendrites.",
              "A neuron enables signaling."]:
        b.process_input("text", s)
    err_only_known = b.relations.prediction_error(["neuron"])
    err_only_unknown = b.relations.prediction_error(["xyzzy_unknown"])
    err_mixed = b.relations.prediction_error(["neuron", "xyzzy_unknown"])
    assert err_only_known < err_mixed < err_only_unknown, (
        f"Mixed should be between known and unknown: "
        f"known={err_only_known}, mixed={err_mixed}, unknown={err_only_unknown}"
    )


# ==================================================================
# Integration: prediction_error in process_input return dict
# ==================================================================

def test_process_input_returns_prediction_error():
    b = _brain()
    result = b.process_input("text", "A galaxy is a system.")
    assert "prediction_error" in result, "process_input should return prediction_error"


def test_prediction_error_is_float():
    b = _brain()
    result = b.process_input("text", "A neuron is a cell.")
    assert isinstance(result["prediction_error"], float)


def test_repeated_input_lowers_prediction_error():
    """
    Teaching Genesis about a concept repeatedly should reduce prediction
    error for subsequent inputs about the same concept.
    """
    b = _brain()
    # First encounter — high error expected
    r1 = b.process_input("text", "A neuron is a cell.")
    err1 = r1["prediction_error"]

    # Teach more about neurons
    b.process_input("text", "A neuron contains dendrites.")
    b.process_input("text", "A neuron enables signaling.")
    b.process_input("text", "A neuron is a biological unit.")

    # Now encounter neuron again — should be less surprising
    r2 = b.process_input("text", "A neuron is a nerve cell.")
    err2 = r2["prediction_error"]

    assert err2 <= err1, (
        f"After learning about neurons, prediction error should not increase: "
        f"first={err1:.3f}, after_learning={err2:.3f}"
    )


def test_novel_concept_has_higher_direct_error_than_familiar():
    """Direct prediction_error() call confirms the signal is correct."""
    b = _brain()
    # Teach many relations about neuron to establish strong beliefs
    for s in [
        "A neuron is a cell.", "A neuron contains dendrites.",
        "A neuron enables signaling.", "A neuron is a biological unit.",
        "A neuron contains an axon.", "A neuron requires energy.",
        "A neuron is part of the nervous system.",
    ]:
        b.process_input("text", s)

    err_known = b.relations.prediction_error(["neuron"])
    err_unknown = b.relations.prediction_error(["xyzzy_qqqq_zzzz"])

    assert err_unknown > err_known, (
        f"Unknown concept should have higher prediction error: "
        f"known={err_known:.3f}, unknown={err_unknown:.3f}"
    )


# ==================================================================
# Interoception
# ==================================================================

def test_interoception_does_not_crash():
    from processors.interoception import interoception_sample
    b = _brain()
    # Force cycle count to a multiple of the interval
    b.cycle_count = 50
    sample = interoception_sample(b)
    # Either returns a dict or None — neither should raise
    assert sample is None or isinstance(sample, dict)


def test_interoception_sample_has_expected_keys():
    from processors.interoception import interoception_sample, _INTERO_INTERVAL
    b = _brain()
    b.cycle_count = _INTERO_INTERVAL
    sample = interoception_sample(b)
    if sample is not None:
        assert "label" in sample
        assert "metrics" in sample
        metrics = sample["metrics"]
        assert "energy" in metrics
        assert "memory_pressure" in metrics


def test_interoception_off_interval_returns_none():
    from processors.interoception import interoception_sample, _INTERO_INTERVAL
    b = _brain()
    b.cycle_count = _INTERO_INTERVAL + 1  # not on interval
    sample = interoception_sample(b)
    assert sample is None


def test_interoception_metrics_bounded():
    from processors.interoception import interoception_sample, _INTERO_INTERVAL
    b = _brain()
    b.cycle_count = _INTERO_INTERVAL
    sample = interoception_sample(b)
    if sample is not None:
        m = sample["metrics"]
        assert 0.0 <= m["energy"] <= 1.0
        assert 0.0 <= m["memory_pressure"] <= 1.0
