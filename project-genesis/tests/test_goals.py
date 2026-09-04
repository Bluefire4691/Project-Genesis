"""
M29 — Persistent Goal Formation integration tests.

Roadmap requirements:
  1. A goal formed in session 1 persists into session 2 and is worked on
     without being re-stated
  2. A self-formed goal (from pattern transfer) appears in brain.goals
     without any conversation trigger
  3. chat_respond("what are you trying to learn?") reflects the active goals

Plus: formation dedupe/cap, satisfaction via self-model verdict,
DecisionLog integration, and the conversation-formation intent.
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


# ── Formation ─────────────────────────────────────────────────────────────────

def test_form_and_query():
    brain = _brain()
    goal = brain.form_goal("plate tectonics")
    assert goal is not None
    assert goal.topic == "plate tectonics"
    assert goal.status == "active"
    active = brain.goals.active()
    assert len(active) == 1 and active[0].topic == "plate tectonics"


def test_form_dedupes_by_topic():
    brain = _brain()
    assert brain.form_goal("osmosis") is not None
    assert brain.form_goal("osmosis") is None
    assert brain.form_goal("Osmosis ") is None      # normalised
    assert len(brain.goals.active()) == 1


def test_active_cap():
    brain = _brain()
    for i in range(15):
        brain.goals.form(f"topic_{i}")
    assert len(brain.goals.active()) == 12          # _MAX_ACTIVE
    assert brain.goals.form("one_more") is None


def test_formation_recorded_in_decision_log():
    brain = _brain()
    brain.form_goal("plate tectonics")
    records = brain.recent_decisions(n=5)
    assert any(r.subsystem == "goals" and "plate tectonics" in r.decision
               for r in records)


def test_formation_pushes_directive_immediately():
    brain = _brain()
    brain.form_goal("volcanism")
    assert "volcanism" in brain._curiosity_directives


# ── Roadmap 1: persistence across sessions, worked on without re-statement ───

def test_goal_persists_and_is_worked_on_in_next_session():
    db = tempfile.mktemp(suffix=".db")
    brain1 = _brain(db)
    from curriculum.open_stage import advance_to_open
    advance_to_open(brain1)
    brain1.form_goal("plate tectonics")
    brain1.save_session()
    del brain1

    brain2 = Orchestrator(verbose=False, db_path=db, resume=True)
    active = brain2.goals.active()
    assert any(g.topic == "plate tectonics" for g in active), (
        "Goal did not persist into session 2"
    )
    # Worked on without re-statement: a reflection re-arms the directive
    brain2._curiosity_directives.pop("plate tectonics", None)
    brain2.reflect(cycle=1)
    assert "plate tectonics" in brain2._curiosity_directives, (
        "Session 2 reflection did not resume pursuing the goal"
    )


# ── Roadmap 2: self-formed goal without conversation ──────────────────────────

def test_self_formed_goal_from_analog_gap(monkeypatch):
    brain = _brain()
    from curriculum.open_stage import advance_to_open
    advance_to_open(brain)

    # Boundary-mock the analog detector (pattern transfer itself is covered
    # in test_pattern_transfer.py); the goal path must promote its output.
    monkeypatch.setattr(brain.pattern_transfer, "curiosity_from_analogs",
                        lambda: ["mitochondria"])
    brain.reflect(cycle=1)

    active = brain.goals.active()
    self_formed = [g for g in active if g.origin == "self"]
    assert any(g.topic == "mitochondria" for g in self_formed), (
        "Analog gap was not promoted to a self-formed goal"
    )
    assert "mirrors" in self_formed[0].statement


# ── Roadmap 3: voice reflects the goal set ────────────────────────────────────

def test_chat_what_are_you_trying_to_learn():
    brain = _brain()
    brain.form_goal("plate tectonics")
    reply = brain.voice.chat_respond("what are you trying to learn?")
    assert "plate tectonics" in reply, (
        f"Reply doesn't reflect the active goal: {reply[:200]}"
    )


def test_chat_remember_to_learn_forms_goal_not_fetch():
    brain = _brain()
    reply = brain.voice.chat_respond("remember to learn about plate tectonics")
    assert any(g.topic == "plate tectonics" for g in brain.goals.active()), (
        f"Goal was not formed from conversation; reply: {reply[:200]}"
    )
    assert "goal" in reply.lower() or "keep working" in reply.lower()


def test_chat_no_goals_answer_is_honest():
    brain = _brain()
    reply = brain.voice.chat_respond("what are your goals?")
    assert "don't have a standing goal" in reply


# ── Satisfaction: measured by the self-model, not edge counts ─────────────────

def test_goal_satisfied_when_self_model_solid():
    brain = _brain()
    brain.form_goal("wolves")

    # Build genuinely solid coverage: >=8 relations at >=0.65 confidence
    rels = [
        ("wolves", "IS_A", "predator"), ("wolves", "CAUSES", "deer decline"),
        ("wolves", "PREVENTS", "overgrazing"), ("wolves", "AFFECTS", "ecosystem"),
        ("wolves", "REQUIRES", "territory"), ("wolves", "CONTAINS", "pack structure"),
        ("wolves", "ENABLES", "trophic cascade"), ("wolves", "CONTROLS", "elk population"),
        ("wolves", "AFFECTS", "river banks"),
    ]
    for s, r, o in rels:
        brain.relations.add(s, r, o, confidence=0.9)

    assert brain.self_model("wolves")["verdict"] == "solid"

    satisfied = brain.goals.check_satisfaction()
    assert "wolves" in satisfied
    assert not brain.goals.active()
    assert any(g.topic == "wolves" for g in brain.goals.satisfied())


def test_unsatisfied_goal_stays_active():
    brain = _brain()
    brain.form_goal("dark matter")           # nothing known about it
    assert brain.goals.check_satisfaction() == []
    assert len(brain.goals.active()) == 1


def test_satisfaction_recorded_in_decision_log():
    brain = _brain()
    brain.form_goal("wolves")
    for i in range(9):
        brain.relations.add("wolves", "AFFECTS", f"thing_{i}", confidence=0.9)
    brain.reflect(cycle=1)
    records = brain.recent_decisions(n=10)
    assert any(r.subsystem == "goals" and "satisfied" in r.decision
               and "wolves" in r.decision for r in records)
