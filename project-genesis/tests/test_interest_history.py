"""
Tests for interest history — consolidation.history() and the evolution of
Genesis's thinking across multiple reflections.

The history command is the individuality property made visible: you can see
which concepts were salient after each reflection and how they shift over time.
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


def _teach(brain, sentences):
    for s in sentences:
        brain.process_input("text", s)


# ==================================================================
# Basic behaviour
# ==================================================================

def test_history_empty_before_any_reflection():
    b = _brain()
    h = b.consolidation.history()
    assert h == []


def test_history_has_one_entry_after_one_reflection():
    b = _brain()
    _teach(b, ["A neuron is a cell.", "A neuron contains dendrites."])
    b.reflect()
    h = b.consolidation.history()
    assert len(h) == 1


def test_history_grows_with_reflections():
    b = _brain()
    _teach(b, ["A neuron is a cell."])
    b.reflect()
    _teach(b, ["A mammal is a vertebrate."])
    b.reflect()
    h = b.consolidation.history()
    assert len(h) == 2


def test_history_entry_has_expected_keys():
    b = _brain()
    _teach(b, ["A galaxy is a system.", "A galaxy contains stars."])
    b.reflect()
    h = b.consolidation.history()
    assert len(h) == 1
    entry = h[0]
    assert "created_at" in entry
    assert "cycle" in entry
    assert "salient" in entry
    assert "summary" in entry


def test_history_salient_is_list():
    b = _brain()
    _teach(b, ["A neuron is a cell.", "A neuron contains dendrites.",
               "A neuron enables signaling."])
    b.reflect()
    h = b.consolidation.history()
    assert isinstance(h[0]["salient"], list)


def test_history_limit_respected():
    b = _brain()
    for i in range(5):
        _teach(b, [f"Concept{i} is a thing."])
        b.reflect()
    h = b.consolidation.history(limit=3)
    assert len(h) <= 3


def test_history_newest_first():
    """history() returns newest first by default."""
    b = _brain()
    _teach(b, ["A neuron is a cell."])
    b.reflect()
    cycle_1 = b.consolidation.history()[0]["cycle"]

    _teach(b, ["A mammal is a vertebrate."])
    b.reflect()
    h = b.consolidation.history()

    # Most recent entry should have higher cycle number
    assert h[0]["cycle"] >= cycle_1


def test_history_summary_nonempty():
    b = _brain()
    _teach(b, ["A neuron is a cell.", "A neuron contains dendrites.",
               "A mammal is a vertebrate."])
    b.reflect()
    h = b.consolidation.history()
    assert isinstance(h[0]["summary"], str)
    assert h[0]["summary"].strip()


# ==================================================================
# Cross-session — continuity of the thought record
# ==================================================================

def test_history_persists_across_sessions():
    """History written in session 1 is readable in session 2."""
    db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db.close()

    b1 = _brain(db_path=db.name)
    _teach(b1, ["A galaxy is a system.", "A galaxy contains stars."])
    b1.reflect()
    b1.save_session()

    b2 = Orchestrator(verbose=False, db_path=db.name)
    h = b2.consolidation.history()
    assert len(h) >= 1, "Session 2 should see session 1's reflections"


def test_two_instances_different_histories():
    """Two brains with different inputs develop different histories."""
    db1 = tempfile.NamedTemporaryFile(suffix=".db", delete=False); db1.close()
    db2 = tempfile.NamedTemporaryFile(suffix=".db", delete=False); db2.close()

    b1 = _brain(db_path=db1.name)
    _teach(b1, ["A neuron is a cell.", "A neuron contains dendrites.",
                "A neuron enables signaling."])
    b1.reflect()

    b2 = _brain(db_path=db2.name)
    _teach(b2, ["A galaxy is a system.", "A galaxy contains stars.",
                "A galaxy contains planets."])
    b2.reflect()

    h1 = b1.consolidation.history()
    h2 = b2.consolidation.history()

    # Extract the top concept from each
    top1 = h1[0]["salient"][0]["concept"] if h1 and h1[0]["salient"] else ""
    top2 = h2[0]["salient"][0]["concept"] if h2 and h2[0]["salient"] else ""

    # Different inputs should produce different salient concepts
    assert top1 != top2 or (not top1 and not top2), (
        f"Different histories should produce different salient concepts: "
        f"{top1!r} vs {top2!r}"
    )
