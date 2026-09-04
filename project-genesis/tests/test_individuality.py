"""
Tests for individuality — the property that makes two Genesis instances
started from the same seed diverge over time purely through their
processing history.

The mechanism: reflections mark concepts as salient → those concepts
boost curiosity scores and augment the adaptive-stream attention window →
this instance gravitates toward related material → further salience on those
concepts → a self-reinforcing attractor that is specific to this history.

No two instances that have processed genuinely different inputs will share
the same attractor. That divergence IS the individuality.
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
# Reflection targets feed back into curiosity
# ==================================================================

def test_reflection_targets_appear_in_curiosity():
    """After reflection, curiosity engine includes reflection-salient concepts."""
    b = _brain()
    _teach(b, [
        "A neuron is a cell.",
        "A neuron contains dendrites.",
        "A neuron contains axons.",
        "A neuron enables signaling.",
    ])
    b.reflect()

    from ingestion.curiosity import CuriosityEngine
    ce = CuriosityEngine(b)
    reflection_hits = ce._reflection_targets()

    # Should have yielded something from reflection
    assert len(reflection_hits) > 0
    concepts_from_reflection = {c for _, c in reflection_hits}
    assert "neuron" in concepts_from_reflection


def test_reflection_score_band():
    """Reflection targets score in the expected band (200–440), below pure gaps (1000+)."""
    b = _brain()
    _teach(b, [
        "A mammal is a vertebrate.",
        "A mammal contains hair.",
        "A mammal enables warmth.",
    ])
    b.reflect()

    from ingestion.curiosity import CuriosityEngine
    ce = CuriosityEngine(b)
    hits = ce._reflection_targets()

    assert len(hits) > 0
    for score, _ in hits:
        assert 100.0 <= score <= 500.0, f"reflection score {score} out of band"


def test_reflection_targets_included_in_top_topics():
    """top_topics() incorporates reflection-salient concepts."""
    b = _brain()
    _teach(b, [
        "A galaxy is a system.",
        "A galaxy contains stars.",
        "A galaxy contains planets.",
        "A galaxy contains dust.",
    ])
    b.reflect()
    salient = b.consolidation.salient_concepts()
    assert salient, "need at least one salient concept for this test"

    from ingestion.curiosity import CuriosityEngine
    ce = CuriosityEngine(b)
    topics = ce.top_topics(n=20)

    # At least one salient concept should appear in curiosity (or a word from it)
    salient_words = set()
    for c in salient:
        salient_words.update(c.lower().split())
    topic_words = set()
    for t in topics:
        topic_words.update(t.lower().split())
    assert salient_words & topic_words, (
        f"no salient concept ({salient_words}) appeared in top_topics: {topics}"
    )


def test_curiosity_report_includes_reflection_source():
    """curiosity_report() labels reflection-sourced entries correctly."""
    b = _brain()
    _teach(b, [
        "Gravity is a force.",
        "Gravity affects planets.",
        "Gravity affects stars.",
    ])
    b.reflect()

    from ingestion.curiosity import CuriosityEngine
    ce = CuriosityEngine(b)
    report = ce.curiosity_report()

    sources = {entry["source"] for entry in report}
    assert "reflection" in sources, f"no reflection-sourced entry in report: {sources}"


# ==================================================================
# Adaptive stream reflects this instance's interests
# ==================================================================

def test_adaptive_stream_attention_includes_reflection_terms():
    """After reflection, AdaptiveStream attention window contains salient words."""
    b = _brain()
    _teach(b, [
        "A photon is a particle.",
        "A photon enables light.",
        "A photon affects electrons.",
    ])
    b.reflect()
    salient = b.consolidation.salient_concepts()
    assert salient, "need salient concepts for this test"

    from curriculum.adaptive_stream import AdaptiveStream
    stream = AdaptiveStream(b, seed=42)
    stream._refresh_attention()
    terms = stream.attention_terms

    # At least one word from salient concepts should appear in attention terms
    salient_words = set()
    for c in salient:
        salient_words.update(c.lower().split())
    term_set = set(terms)
    assert salient_words & term_set, (
        f"salient words {salient_words} not in attention terms {term_set}"
    )


def test_adaptive_stream_cold_wm_still_has_reflection_terms():
    """Reflection-backed attention persists across sessions (cold WM at restart)."""
    db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db.close()

    # Session 1: teach and reflect
    b1 = _brain(db_path=db.name)
    _teach(b1, [
        "Entropy is a measure.",
        "Entropy affects heat.",
        "Entropy affects disorder.",
    ])
    b1.reflect()
    salient = b1.consolidation.salient_concepts()
    assert salient

    # Session 2: fresh brain on same DB — WM is empty, reflection history is not
    b2 = Orchestrator(verbose=False, db_path=db.name)
    assert len(b2.memory.memories) == 0

    from curriculum.adaptive_stream import AdaptiveStream
    stream = AdaptiveStream(b2, seed=0)
    stream._refresh_attention()
    terms = stream.attention_terms

    salient_words = set()
    for c in salient:
        salient_words.update(c.lower().split())

    assert salient_words & set(terms), (
        "After session restart with cold WM, reflection terms should appear in attention"
    )


# ==================================================================
# Divergence — the core individuality claim
# ==================================================================

def test_two_instances_have_different_salient_concepts():
    """Two instances taught different content reflect on different concepts."""
    b1 = _brain()
    b2 = _brain()

    _teach(b1, [
        "A neuron is a cell.",
        "A neuron contains dendrites.",
        "A neuron enables signaling.",
        "Dendrites receive signals.",
    ])
    _teach(b2, [
        "A galaxy is a system.",
        "A galaxy contains stars.",
        "A galaxy contains planets.",
        "Stars produce light.",
    ])

    b1.reflect()
    b2.reflect()

    s1 = set(b1.consolidation.salient_concepts())
    s2 = set(b2.consolidation.salient_concepts())

    assert s1, "b1 should have salient concepts"
    assert s2, "b2 should have salient concepts"
    assert s1 != s2, (
        f"Instances with different histories should have different salient "
        f"concepts; both got {s1}"
    )


def test_two_instances_have_different_curiosity():
    """Instances with different histories are curious about different things."""
    b1 = _brain()
    b2 = _brain()

    _teach(b1, [
        "A neuron is a cell.",
        "A neuron contains dendrites.",
        "A neuron enables signaling.",
    ])
    _teach(b2, [
        "A galaxy is a system.",
        "A galaxy contains stars.",
        "A galaxy contains planets.",
    ])

    b1.reflect()
    b2.reflect()

    from ingestion.curiosity import CuriosityEngine
    t1 = set(CuriosityEngine(b1).top_topics(n=10))
    t2 = set(CuriosityEngine(b2).top_topics(n=10))

    # They shouldn't share every topic — at least one unique item each
    assert t1 != t2, (
        f"Different histories should yield different curiosity; both got {t1}"
    )


def test_two_instances_have_different_attention():
    """AdaptiveStream attention terms differ between instances with different histories."""
    b1 = _brain()
    b2 = _brain()

    _teach(b1, [
        "A neuron is a cell.",
        "A neuron contains dendrites.",
        "Dendrites receive signals.",
    ])
    _teach(b2, [
        "A galaxy is a system.",
        "A galaxy contains stars.",
        "Stars produce heat.",
    ])

    b1.reflect()
    b2.reflect()

    from curriculum.adaptive_stream import AdaptiveStream
    s1 = AdaptiveStream(b1, seed=7)
    s2 = AdaptiveStream(b2, seed=7)
    s1._refresh_attention()
    s2._refresh_attention()

    t1 = set(s1.attention_terms)
    t2 = set(s2.attention_terms)

    assert t1 != t2, (
        f"Instances with different histories should have different attention terms"
    )


# ==================================================================
# Robustness — no reflection yet, no crash
# ==================================================================

def test_no_reflection_yet_does_not_crash_curiosity():
    """CuriosityEngine._reflection_targets() degrades gracefully before any reflection."""
    b = _brain()
    _teach(b, ["A cell is a unit."])
    # No reflect() call

    from ingestion.curiosity import CuriosityEngine
    ce = CuriosityEngine(b)
    hits = ce._reflection_targets()
    assert isinstance(hits, list)
    # Empty is fine — nothing reflected yet
    assert hits == []


def test_no_reflection_yet_does_not_crash_stream():
    """AdaptiveStream._refresh_attention() works with no prior reflection."""
    b = _brain()
    _teach(b, ["A cell is a unit."])

    from curriculum.adaptive_stream import AdaptiveStream
    stream = AdaptiveStream(b, seed=1)
    stream._refresh_attention()  # should not raise
    assert isinstance(stream.attention_terms, list)
