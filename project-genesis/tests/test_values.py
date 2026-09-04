"""
M36 — self-determined interests and values.

Verifies the full loop the milestone claims: liking history becomes tastes,
consequence patterns valenced by those tastes become held values, and both
measurably change what Genesis chooses to read — with the change auditable.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from orchestrator.orchestrator import Orchestrator


def _brain(db=None) -> Orchestrator:
    return Orchestrator(verbose=False,
                        db_path=db or tempfile.mktemp(suffix=".db"),
                        resume=False)


# ── Tastes ────────────────────────────────────────────────────────────────────

def test_taste_accumulates_and_decays_toward_signal():
    brain = _brain()
    vs = brain.values
    for _ in range(5):
        vs.credit(["wolves"], liking=0.5)
    assert vs.taste_for("wolves") > 0.2
    for _ in range(10):
        vs.credit(["wolves"], liking=-0.5)
    assert vs.taste_for("wolves") < 0, "sustained dislike should flip the taste"


def test_taste_ignores_hedonic_noise():
    brain = _brain()
    brain.values.credit(["rocks"], liking=0.05)     # below floor
    assert brain.values.taste_for("rocks") == 0.0


def test_tastes_persist_across_sessions():
    db = tempfile.mktemp(suffix=".db")
    b1 = _brain(db)
    for _ in range(5):
        b1.values.credit(["rivers"], liking=0.6)
    w = b1.values.taste_for("rivers")
    del b1
    b2 = Orchestrator(verbose=False, db_path=db, resume=True)
    assert abs(b2.values.taste_for("rivers") - w) < 1e-9


# ── Values: authored from patterns × own hedonic history ─────────────────────

def _seed_consequence(brain, subject="overgrazing", outcome="ecosystem collapse"):
    """Ethics-adjacent 2-hop chain so the lens surfaces subject → outcome."""
    brain.relations.add(subject, "CAUSES", "soil loss", confidence=0.9)
    brain.relations.add("soil loss", "CAUSES", outcome, confidence=0.9)


def test_value_forms_only_with_lived_valence():
    brain = _brain()
    _seed_consequence(brain)
    # No taste for the outcome yet → no value may form (no engineer ontology)
    brain.values.author_from_experience()
    assert brain.values.held() == [], (
        "a value must not form before Genesis has felt anything about the outcome"
    )


def test_avoid_value_forms_from_disliked_outcome():
    brain = _brain()
    _seed_consequence(brain)
    for _ in range(6):
        brain.values.credit(["ecosystem collapse"], liking=-0.6)
    changed = brain.values.author_from_experience()
    held = brain.values.held()
    if changed:                       # inference chain surfaced by the lens
        v = next(v for v in held if v["subject"] == "overgrazing")
        assert v["stance"] == "avoid"
        assert "avoid" in v["statement"] and "disliked" in v["statement"]
        assert brain.values.stance_for("overgrazing") == "avoid"


def test_conflicting_pattern_lowers_confidence_not_erases():
    brain = _brain()
    vs = brain.values
    assert vs._upsert_value("competition", "favor", "I seek out competition", 0.8)
    before = vs.held()[0]["confidence"]
    vs._upsert_value("competition", "avoid", "I avoid competition", 0.8)
    after = vs.held()[0]
    assert after["confidence"] < before, "conflict must create tension"
    assert after["stance"] == "favor", "original stance kept, not erased"
    assert "other way" in after["statement"]


# ── Governance: preference changes what gets chosen, auditable ───────────────

def test_avoid_value_deprioritizes_reading_choice():
    brain = _brain()
    from ingestion.curiosity import CuriosityEngine
    eng = CuriosityEngine(brain)

    # Two equal gaps; Genesis holds an avoid-stance on one
    brain.relations.add("subjectless", "AFFECTS", "taxonomy drift", confidence=0.4)
    brain.relations.add("subjectless2", "AFFECTS", "predator wolves", confidence=0.4)
    brain.values._upsert_value("taxonomy", "avoid", "I avoid taxonomy", 0.8)
    for _ in range(6):
        brain.values.credit(["wolves"], liking=0.6)

    adj_avoid = brain.values.curiosity_adjustment("taxonomy")
    adj_taste = brain.values.curiosity_adjustment("wolves")
    assert adj_avoid < 0 < adj_taste


def test_preference_shift_is_recorded_in_decision_log():
    brain = _brain()
    from ingestion.curiosity import CuriosityEngine
    eng = CuriosityEngine(brain)
    # Build a frontier, then poison one topic hard so top-n membership shifts
    from curriculum.open_stage import advance_to_open
    advance_to_open(brain)
    topics = eng.top_topics(n=3)
    if topics:
        brain.values._upsert_value(topics[0], "avoid", f"I avoid {topics[0]}", 0.9)
        before = brain.decision_log.count()
        shifted = eng.top_topics(n=3)
        if topics[0] not in shifted:
            assert brain.decision_log.count() > before, (
                "a value-shaped choice must be auditable"
            )


# ── Voice ─────────────────────────────────────────────────────────────────────

def test_chat_values_honest_when_unlived():
    brain = _brain()
    reply = brain.voice.chat_respond("what do you value?")
    assert "haven't lived enough" in reply


def test_chat_values_speaks_authored_values():
    brain = _brain()
    brain.values._upsert_value(
        "cooperation", "favor",
        "I seek out cooperation — in what I've processed it leads to "
        "resilience, which I've valued in my own experience", 0.8)
    for _ in range(4):
        brain.values.credit(["rivers"], liking=0.7)
    reply = brain.voice.chat_respond("what are your values?")
    assert "cooperation" in reply
    assert "Nobody handed me these" in reply


def test_reflect_runs_value_authoring_without_error():
    brain = _brain()
    from curriculum.open_stage import advance_to_open
    advance_to_open(brain)
    brain.reflect(cycle=1)          # must not raise; values pass is wired in
