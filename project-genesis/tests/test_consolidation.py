"""
Tests for the ConsolidationEngine — self-authored reflection ("sleep") pass.

Consolidation is the process by which Genesis decides what mattered from its
own signals (recent relation growth, connectivity, reasoning, tension) rather
than an engineer's category scheme. These tests check that:

  - it surfaces concepts Genesis actually built structure around,
  - it never raises (errors are data),
  - reflections persist across sessions (continuity),
  - it reflects on the *recent* window, not the whole history every time.
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

def test_reflect_never_raises_on_empty_brain():
    brain = _brain()
    rep = brain.reflect()
    assert rep["status"] in ("reflected", "degraded")
    # No knowledge yet → nothing salient, but a valid report.
    assert isinstance(rep["summary"], str)


def test_reflection_surfaces_built_concepts():
    brain = _brain()
    # Build clear structure around a few concepts.
    _teach(brain, [
        "A neuron is a cell.",
        "A neuron contains dendrites.",
        "A mammal is a vertebrate.",
        "A mammal contains hair.",
    ])
    rep = brain.reflect()
    assert rep["status"] == "reflected"
    concepts = {s["concept"] for s in rep["salient"]}
    # The things it built relations around should be what it reflects on.
    assert "neuron" in concepts or "mammal" in concepts


def test_summary_is_first_person_and_grounded():
    brain = _brain()
    _teach(brain, ["A dog is a mammal.", "A dog is an animal."])
    rep = brain.reflect()
    assert rep["summary"]
    # First-person framing — this is Genesis's own reflection.
    assert "I" in rep["summary"]


def test_salient_concepts_are_clean():
    brain = _brain()
    _teach(brain, [
        "Photosynthesis is a chemical process.",
        "A galaxy is a system.",
        "Gravity is a force.",
    ])
    brain.reflect()
    for c in brain.consolidation.salient_concepts():
        # No digits, no over-long phrases.
        assert not any(ch.isdigit() for ch in c)
        assert len(c.split()) <= 2


# ==================================================================
# Recency window — reflect on what changed, not everything every time
# ==================================================================

def test_second_reflection_uses_new_window():
    brain = _brain()
    _teach(brain, ["A neuron is a cell.", "A neuron contains dendrites."])
    rep1 = brain.reflect()
    g1 = sum(s["growth"] for s in rep1["salient"])
    assert g1 > 0  # first reflection sees the initial growth

    # Teach something different, then reflect again.
    _teach(brain, ["An empire is a state.", "An empire contains provinces."])
    rep2 = brain.reflect()
    # The second reflection's growth signal comes from the new material.
    concepts2 = {s["concept"] for s in rep2["salient"]}
    assert "empire" in concepts2 or any(s["growth"] > 0 for s in rep2["salient"])


def test_reflections_accumulate():
    brain = _brain()
    _teach(brain, ["A cat is a mammal."])
    brain.reflect()
    _teach(brain, ["A bird is an animal."])
    brain.reflect()
    assert brain.consolidation.stats()["total_reflections"] == 2
    hist = brain.consolidation.history()
    assert len(hist) == 2


# ==================================================================
# Continuity — reflections survive a restart on the same DB
# ==================================================================

def test_reflection_persists_across_sessions():
    db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db.close()

    b1 = _brain(db_path=db.name)
    _teach(b1, ["A neuron is a cell.", "A neuron contains dendrites."])
    b1.reflect()
    b1.save_session()
    first_summary = b1.latest_reflection()["summary"]

    # New brain, same DB — it should remember what it had been thinking about.
    b2 = Orchestrator(verbose=False, db_path=db.name)
    latest = b2.latest_reflection()
    assert latest is not None
    assert latest["summary"] == first_summary


# ==================================================================
# Consolidation acts through attention, never deletes
# ==================================================================

def test_consolidation_preserves_all_relations():
    brain = _brain()
    _teach(brain, [
        "A neuron is a cell.",
        "A mammal is a vertebrate.",
        "An atom contains electrons.",
    ])
    before = brain.relations.stats().get("total_relations", 0)
    brain.reflect()
    after = brain.relations.stats().get("total_relations", 0)
    # Reflection strengthens/derives — it never discards. (Total retention.)
    assert after >= before
