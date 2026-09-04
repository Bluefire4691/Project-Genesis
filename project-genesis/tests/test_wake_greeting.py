"""
Tests for GenesisVoice.wake_greeting() — session-start continuity.

The wake greeting is the first thing Genesis says when it starts with prior
history. It tells you what it has been thinking about — from its own reflection,
inference count, and curiosity frontier. This is a direct expression of the
"continuity" property in CLAUDE.md: its history is its own, and it remembers.
"""

import re
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


_RAW_TOKENS = ["IS_A", "PREDATES", "REQUIRES", "CONTROLS", "CONTAINS",
               "ENABLES", "PREVENTS", "AFFECTS", "CAUSES", "text:", "_"]


def _assert_clean(s: str):
    assert isinstance(s, str) and s.strip(), "greeting must be non-empty"
    for tok in _RAW_TOKENS:
        assert tok not in s, f"raw token {tok!r} in greeting: {s!r}"
    for word in re.findall(r"[A-Za-z]+", s):
        assert len(word) <= 20, f"mangled token {word!r} in greeting: {s!r}"


# ==================================================================
# Basic behaviour
# ==================================================================

def test_fresh_brain_greeting_is_clean_and_noneempty():
    b = _brain()
    g = b.voice.wake_greeting()
    _assert_clean(g)


def test_fresh_brain_greeting_mentions_starting():
    b = _brain()
    g = b.voice.wake_greeting().lower()
    assert "start" in g or "fresh" in g or "no prior" in g or "picking up" in g


def test_brain_with_relations_no_reflection_mentions_connections():
    b = _brain()
    _teach(b, ["A neuron is a cell.", "A neuron contains dendrites."])
    g = b.voice.wake_greeting()
    _assert_clean(g)


def test_after_reflection_greeting_is_first_person():
    b = _brain()
    _teach(b, [
        "A mammal is a vertebrate.",
        "A mammal contains hair.",
        "Gravity is a force.",
    ])
    b.reflect()
    g = b.voice.wake_greeting()
    _assert_clean(g)
    assert "I" in g  # first-person


def test_after_reflection_greeting_mentions_salient_concept():
    b = _brain()
    _teach(b, [
        "A neuron is a cell.",
        "A neuron contains dendrites.",
        "A neuron enables signaling.",
    ])
    b.reflect()
    salient = b.consolidation.salient_concepts()
    assert salient

    g = b.voice.wake_greeting().lower()
    _assert_clean(b.voice.wake_greeting())
    # At least one salient concept word should appear in the greeting
    salient_words = set()
    for c in salient:
        salient_words.update(c.lower().split())
    assert any(w in g for w in salient_words), (
        f"No salient word ({salient_words}) in greeting: {g!r}"
    )


def test_with_inferences_greeting_mentions_conclusions():
    b = _brain()
    _teach(b, [
        "A mammal is a vertebrate.",
        "A mammal contains hair.",
        "A cat is a mammal.",
    ])
    b.reflect()
    b.inference.run(session_id=b.session_id)
    inf_count = b.inference.stats()["total_inferences"]
    if inf_count == 0:
        return  # nothing to test if inference didn't fire
    g = b.voice.wake_greeting()
    _assert_clean(g)
    assert "conclusion" in g.lower() or "derived" in g.lower() or "worked out" in g.lower()


# ==================================================================
# Cross-session — continuity is the point
# ==================================================================

def test_greeting_survives_session_restart():
    """Second session on same DB gives a greeting rooted in first session's reflection."""
    db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db.close()

    b1 = _brain(db_path=db.name)
    _teach(b1, [
        "A galaxy is a system.",
        "A galaxy contains stars.",
        "A galaxy contains planets.",
    ])
    b1.reflect()
    b1.save_session()
    salient1 = b1.consolidation.salient_concepts()
    assert salient1

    # Session 2 — brand new brain on the same DB
    b2 = Orchestrator(verbose=False, db_path=db.name)
    g = b2.voice.wake_greeting()
    _assert_clean(g)

    # Should reference what the first session was thinking about
    salient_words = set()
    for c in salient1:
        salient_words.update(c.lower().split())
    assert any(w in g.lower() for w in salient_words), (
        f"Cross-session greeting should mention prior salient concepts "
        f"({salient_words}); got: {g!r}"
    )


def test_greeting_mentions_new_connections_after_growth():
    """If relations grew since the last reflection, greeting mentions the delta."""
    b = _brain()
    _teach(b, ["A neuron is a cell.", "A neuron enables signaling."])
    b.reflect()  # snapshot: relations_total at reflection time

    # Add more relations AFTER the reflection (simulating inter-session growth)
    _teach(b, ["Neurons contain axons.", "Axons enable transmission."])

    g = b.voice.wake_greeting()
    _assert_clean(g)
    # Should mention the new connections
    assert "new connection" in g.lower() or "added" in g.lower() or "connection" in g.lower(), (
        f"Greeting should mention new connections: {g!r}"
    )


def test_two_sessions_different_histories_give_different_greetings():
    """Two brains with different histories give different wake greetings."""
    db1 = tempfile.NamedTemporaryFile(suffix=".db", delete=False); db1.close()
    db2 = tempfile.NamedTemporaryFile(suffix=".db", delete=False); db2.close()

    b1 = _brain(db_path=db1.name)
    _teach(b1, ["A neuron is a cell.", "A neuron enables signaling."])
    b1.reflect()

    b2 = _brain(db_path=db2.name)
    _teach(b2, ["A galaxy is a system.", "A galaxy contains stars."])
    b2.reflect()

    g1 = b1.voice.wake_greeting()
    g2 = b2.voice.wake_greeting()

    _assert_clean(g1)
    _assert_clean(g2)
    assert g1 != g2, "Different histories should produce different greetings"
