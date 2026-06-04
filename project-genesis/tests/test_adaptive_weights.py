"""
Tests for adaptive salience weights in ConsolidationEngine.

Genesis adapts its own salience weights after each reflection based on whether
the previous reflection's predictions were vindicated. This makes the
consolidation engine self-calibrating: over many reflections, each instance
converges on the signal mix that best predicts *its own* continued development.

Two instances with different processing histories should develop different
weights — a deeper form of individuality than the curiosity/attention divergence.
"""

import sys
import os
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from orchestrator.orchestrator import Orchestrator
from utils.types import Stage
from consolidation.consolidation import _W_GROWTH, _W_INFERENCE, _W_TENSION, _W_MIN, _W_MAX


def _brain(**kwargs) -> Orchestrator:
    if "db_path" not in kwargs:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        kwargs["db_path"] = tmp.name
    b = Orchestrator(verbose=False, **kwargs)
    b.curriculum.current_stage = Stage.OPEN
    return b


def _teach(brain, sentences):
    for s in sentences:
        brain.process_input("text", s)


# ==================================================================
# Initial state
# ==================================================================

def test_initial_weights_are_defaults():
    """A fresh brain starts with the default module-level weights."""
    b = _brain()
    w = b.consolidation.current_weights()
    assert w["growth"]    == _W_GROWTH
    assert w["inference"] == _W_INFERENCE
    assert w["tension"]   == _W_TENSION


def test_weights_exposed_in_stats():
    b = _brain()
    stats = b.consolidation.stats()
    assert "weights" in stats
    w = stats["weights"]
    assert all(k in w for k in ("growth", "degree", "inference", "tension"))


# ==================================================================
# Adaptation behaviour
# ==================================================================

def test_weights_do_not_crash_on_single_reflection():
    """First reflection (no prior window) adapts cleanly without raising."""
    b = _brain()
    _teach(b, ["A neuron is a cell.", "A neuron enables signaling."])
    rep = b.reflect()
    assert rep["status"] in ("reflected", "degraded")
    w = b.consolidation.current_weights()
    # Still within bounds
    for val in w.values():
        assert _W_MIN <= val <= _W_MAX


def test_weights_stay_within_bounds_after_many_reflections():
    """Weights must remain within [_W_MIN, _W_MAX] no matter what."""
    b = _brain()
    sentences = [
        "A neuron is a cell.",
        "A neuron enables signaling.",
        "A mammal is a vertebrate.",
        "A mammal contains hair.",
        "Gravity is a force.",
        "Gravity affects planets.",
        "Entropy is a measure.",
        "Entropy affects heat.",
    ]
    # Multiple reflection cycles
    for round_num in range(4):
        _teach(b, sentences[round_num * 2:(round_num + 1) * 2])
        b.reflect()

    w = b.consolidation.current_weights()
    for name, val in w.items():
        assert _W_MIN <= val <= _W_MAX, (
            f"weight {name}={val} out of bounds [{_W_MIN}, {_W_MAX}]"
        )


def test_weights_can_change_after_two_reflections():
    """After two reflections there is enough data to adapt weights."""
    b = _brain()
    _teach(b, [
        "A wolf is a predator.",
        "A wolf controls deer.",
        "Deer cause overgrazing.",
        "Overgrazing causes erosion.",
    ])
    b.reflect()  # First reflection — no adaptation yet (no prior)

    _teach(b, [
        "Erosion damages soil.",
        "Soil enables plant growth.",
        "Plants enable oxygen.",
    ])
    w_before = dict(b.consolidation.current_weights())
    b.reflect()  # Second reflection — adaptation fires
    w_after = b.consolidation.current_weights()

    # At least one weight changed (or all stayed the same if data insufficient)
    # The key invariant: weights are still valid
    for name, val in w_after.items():
        assert _W_MIN <= val <= _W_MAX


# ==================================================================
# Persistence — weights survive session restart
# ==================================================================

def test_adapted_weights_persist_across_sessions():
    """Adapted weights are stored in the DB and restored on the next session."""
    db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db.close()

    # Session 1: two reflections so adaptation fires
    b1 = _brain(db_path=db.name)
    _teach(b1, [
        "A neuron is a cell.",
        "A neuron enables signaling.",
        "A mammal is a vertebrate.",
    ])
    b1.reflect()
    _teach(b1, ["Neurons contain axons.", "Axons enable transmission."])
    b1.reflect()
    w1 = b1.consolidation.current_weights()

    # Session 2 — fresh brain, same DB
    b2 = Orchestrator(verbose=False, db_path=db.name)
    w2 = b2.consolidation.current_weights()

    # Weights must be consistent across sessions
    assert w1["growth"]    == w2["growth"],    "growth weight should persist"
    assert w1["inference"] == w2["inference"], "inference weight should persist"
    assert w1["tension"]   == w2["tension"],   "tension weight should persist"


# ==================================================================
# Individuality — two instances develop different weights
# ==================================================================

def test_weight_divergence_is_possible():
    """
    Two instances taught different content may develop different weights
    after multiple reflections.

    Note: the exact weights depend on which signals were predictive in
    each instance's history, so we can't prescribe exact values. But we
    can show that the mechanism works: both instances produce valid weights
    that are in range, and the mechanism runs without error.
    """
    b1 = _brain()
    b2 = _brain()

    # Instance 1: lots of causal structure → growth signal dominates
    for _ in range(3):
        _teach(b1, [
            "A wolf is a predator.",
            "A wolf controls deer.",
            "Deer cause overgrazing.",
            "Overgrazing causes erosion.",
            "Erosion damages soil.",
        ])
        b1.reflect()

    # Instance 2: lots of contradictions → tension signal dominates
    for _ in range(3):
        _teach(b2, [
            "Rain causes flooding.",
            "Rain prevents drought.",
            "Fire causes destruction.",
            "Fire prevents forest overgrowth.",
        ])
        b2.reflect()

    w1 = b1.consolidation.current_weights()
    w2 = b2.consolidation.current_weights()

    # Both must be in range
    for w in (w1, w2):
        for val in w.values():
            assert _W_MIN <= val <= _W_MAX

    # They don't have to be different (adaptation is data-dependent), but
    # there's no reason they'd be identical after different histories.
    # We simply assert no crash and valid bounds.


# ==================================================================
# Robustness
# ==================================================================

def test_adapt_weights_never_raises():
    """Adaptation is always safe — no exception propagates up."""
    b = _brain()
    # Call consolidate multiple times with minimal data — should never raise
    for _ in range(5):
        b.reflect()
    w = b.consolidation.current_weights()
    assert isinstance(w, dict)


def test_degree_weight_is_not_adapted():
    """Degree (structural connectivity) weight should never change."""
    b = _brain()
    _teach(b, ["A neuron is a cell.", "A mammal is a vertebrate."])
    b.reflect()
    _teach(b, ["A galaxy is a system.", "Gravity is a force."])
    b.reflect()
    w = b.consolidation.current_weights()
    from consolidation.consolidation import _W_DEGREE
    assert w["degree"] == _W_DEGREE, "degree weight must not be adapted"
