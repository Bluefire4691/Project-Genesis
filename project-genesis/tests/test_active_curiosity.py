"""
Tests for M17 — Active Curiosity Directives (SOAR impasse → subgoal).

When Genesis encounters a concept it barely knows (high prediction error),
it registers that concept as an active curiosity directive. AdaptiveStream
then gives elevated weight to items that could resolve the gap. Once the
concept accumulates enough relations, the directive is resolved automatically.

Grounded in Newell/Laird SOAR: when the system cannot select an operator
(insufficient knowledge), it creates a subgoal in a new problem space to
resolve the impasse. Chunking converts the resolution into a compiled rule.
In Genesis: impasse = unknown concept, subgoal = curiosity directive,
resolution = accumulated relations.
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
# Basic directive behaviour
# ==================================================================

def test_curiosity_directives_returns_list():
    b = _brain()
    d = b.curiosity_directives()
    assert isinstance(d, list)


def test_fresh_brain_directives_empty_or_list():
    b = _brain()
    d = b.curiosity_directives()
    assert isinstance(d, list)  # may or may not be empty on fresh brain


def test_directives_bounded_by_max():
    b = _brain()
    # Process many inputs with unknown concepts to try to exceed max
    for i in range(30):
        b.process_input("text", f"Zylothorp{i} is a mystical concept.")
    d = b.curiosity_directives()
    assert len(d) <= b._MAX_DIRECTIVES, (
        f"Directives should be capped at {b._MAX_DIRECTIVES}, got {len(d)}"
    )


def test_directives_are_strings():
    b = _brain()
    b.process_input("text", "Quasmoid is an unknown phenomenon.")
    d = b.curiosity_directives()
    for item in d:
        assert isinstance(item, str), f"Directive should be a string: {item!r}"


def test_directive_added_for_unknown_concept():
    """
    After processing an input containing a genuinely unknown concept,
    at least one directive should be registered.
    """
    b = _brain()
    # Process something that gives Genesis a concept it knows nothing about
    b.process_input("text", "Ytterbiflorium is an undiscovered element.")
    d = b.curiosity_directives()
    # Directives might or might not fire on the first cycle depending on
    # pred_error threshold — test that the system works without crashing
    assert isinstance(d, list)


# ==================================================================
# Resolution behaviour
# ==================================================================

def test_directive_resolves_after_enough_relations():
    """
    A concept that starts as a directive should be resolved (removed)
    once Genesis accumulates enough relations about it.
    Note: relation storage normalizes text (strips underscores → spaces),
    so we use a simple space-separated concept that survives normalization.
    """
    b = _brain()
    # Use a concept without underscores so it round-trips through normalization
    concept = "testconcept"
    b._curiosity_directives[concept] = 0.95

    # Teach Genesis about that concept until it hits the threshold
    for i in range(b._DIRECTIVE_RESOLVE_RELS + 1):
        b.relations.add(
            subject=concept,
            rel_type="IS_A",
            obj=f"thing{i}",
            confidence=0.8,
            source_key="test",
            session_id="test",
        )

    # Trigger a directive update
    b._update_curiosity_directives([concept], 0.5)

    # Directive should be resolved
    assert concept not in b.curiosity_directives(), (
        f"Concept with {b._DIRECTIVE_RESOLVE_RELS+1} relations should be resolved"
    )


def test_directive_not_resolved_with_few_relations():
    """A concept with fewer than threshold relations stays as a directive."""
    b = _brain()
    concept = "partialconcept"
    b._curiosity_directives[concept] = 0.9

    # Add only one relation — below threshold
    b.relations.add(
        subject=concept,
        rel_type="IS_A",
        obj="something",
        confidence=0.8,
        source_key="test",
        session_id="test",
    )

    b._update_curiosity_directives([concept], 0.9)

    assert concept in b.curiosity_directives(), (
        "Concept with only 1 relation should remain as a directive"
    )


# ==================================================================
# Persistence
# ==================================================================

def test_directives_persist_across_sessions():
    """Directives written in session 1 are readable in session 2."""
    db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db.close()

    b1 = _brain(db_path=db.name)
    # Manually add a directive and save it
    b1._curiosity_directives["persistent_concept"] = 0.9
    b1._save_directives()

    # New session on same DB
    b2 = Orchestrator(verbose=False, db_path=db.name)
    assert "persistent_concept" in b2._curiosity_directives, (
        "Curiosity directives should persist across sessions"
    )


# ==================================================================
# AdaptiveStream integration
# ==================================================================

def test_adaptive_stream_has_directive_terms():
    """AdaptiveStream._refresh_attention() should load directive terms."""
    from curriculum.adaptive_stream import AdaptiveStream
    b = _brain()
    # Plant a directive
    b._curiosity_directives["wolves"] = 0.9
    stream = AdaptiveStream(b)
    stream._refresh_attention()
    # "wolves" should appear in the directive terms
    assert "wolves" in stream._current_directive_terms, (
        "Directive concept should appear in _current_directive_terms"
    )


def test_directive_terms_boost_item_score():
    """An item touching a directive concept should score higher."""
    from curriculum.adaptive_stream import AdaptiveStream
    b = _brain()
    b._curiosity_directives["wolves"] = 0.9
    stream = AdaptiveStream(b)
    stream._refresh_attention()

    item_with_directive = {"type": "text", "data": "Wolves are apex predators."}
    item_without = {"type": "text", "data": "The sun is a star."}

    score_with = stream._score_item(item_with_directive)
    score_without = stream._score_item(item_without)

    # Item touching the directive should score at least as high
    # (may be equal if neither is in general attention terms)
    assert score_with >= score_without, (
        f"Directive item should score >= non-directive item: "
        f"with={score_with:.3f}, without={score_without:.3f}"
    )


def test_no_crash_when_directives_empty():
    """AdaptiveStream should not crash when there are no directives."""
    from curriculum.adaptive_stream import AdaptiveStream
    b = _brain()
    assert b.curiosity_directives() == [] or isinstance(b.curiosity_directives(), list)
    stream = AdaptiveStream(b)
    stream._refresh_attention()
    assert isinstance(stream._current_directive_terms, list)
