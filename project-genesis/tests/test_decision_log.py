"""
M28 — DecisionLog integration tests.

These test the real pipeline (no mocks), asserting user-observable outcomes:
  1. After a learning session, decisions accumulate per topic
  2. Each record has a non-empty rationale
  3. "what have you been deciding?" draws on actual decisions
  4. recent_decisions() is callable on Orchestrator and returns DecisionRecords
  5. Reflection records a decision
  6. Log survives a new Orchestrator on the same DB (cross-session persistence)
"""

import tempfile
import os
import pytest

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from orchestrator.orchestrator import Orchestrator


def _brain(tmp_path=None) -> Orchestrator:
    if tmp_path is None:
        tmp_path = tempfile.mktemp(suffix=".db")
    return Orchestrator(verbose=False, db_path=tmp_path, resume=False)


# ── Unit: DecisionLog directly ────────────────────────────────────────────────

def test_record_and_recent():
    brain = _brain()
    log = brain.decision_log

    assert log.count() == 0

    log.record("feeder", "learn about wolves", "hunger=0.7", cycle=1)
    log.record("feeder", "learn about deer",   "hunger=0.6", cycle=2)
    log.record("reflection", "consolidate: salient concepts [wolf, prey]",
               "cycle=2", cycle=2)

    assert log.count() == 3
    recent = log.recent(n=5)
    assert len(recent) == 3


def test_records_have_rationale():
    brain = _brain()
    log = brain.decision_log
    log.record("feeder", "learn about ecosystem", "hunger=0.8, wanting=+0.03")
    records = log.recent(n=1)
    assert records[0].rationale != ""


def test_recent_newest_first():
    brain = _brain()
    log = brain.decision_log
    log.record("feeder", "learn about A", "r1", cycle=1)
    log.record("feeder", "learn about B", "r2", cycle=2)
    records = log.recent(n=2)
    assert records[0].decision == "learn about B"
    assert records[1].decision == "learn about A"


def test_recent_n_limit():
    brain = _brain()
    log = brain.decision_log
    for i in range(10):
        log.record("feeder", f"learn about concept_{i}", "r", cycle=i)
    assert len(log.recent(n=3)) == 3
    assert len(log.recent(n=10)) == 10


def test_decision_record_fields():
    brain = _brain()
    log = brain.decision_log
    log.record("hypothesis", "formed 2 hypotheses, resolved 1",
               "generative pass at cycle 50", cycle=50)
    r = log.recent(n=1)[0]
    assert r.subsystem == "hypothesis"
    assert "hypothes" in r.decision
    assert r.cycle_count == 50
    assert r.timestamp > 0
    assert r.age_s >= 0


# ── Integration: Orchestrator.recent_decisions() ──────────────────────────────

def test_recent_decisions_callable():
    brain = _brain()
    result = brain.recent_decisions(n=5)
    assert isinstance(result, list)


def test_reflect_creates_decision():
    brain = _brain()
    from curriculum.open_stage import advance_to_open
    advance_to_open(brain)

    count_before = brain.decision_log.count()
    brain.reflect(cycle=10)
    count_after = brain.decision_log.count()

    assert count_after > count_before, (
        "reflect() should have added at least one DecisionRecord"
    )


def test_reflect_decision_has_rationale():
    brain = _brain()
    from curriculum.open_stage import advance_to_open
    advance_to_open(brain)

    brain.reflect(cycle=5)
    records = brain.recent_decisions(n=10)
    reflect_records = [r for r in records if r.subsystem == "reflection"]
    assert reflect_records, "No reflection record found"
    assert reflect_records[0].rationale != ""


# ── Integration: required by roadmap ─────────────────────────────────────────

def test_five_topic_session_produces_decisions():
    """
    Roadmap requirement: after a 5-topic learning session,
    len(brain.recent_decisions()) >= 5.

    Uses WordNet (offline) so the test doesn't need the network.
    """
    brain = _brain()
    from curriculum.open_stage import advance_to_open
    advance_to_open(brain)

    count_before = brain.decision_log.count()
    # WordNet + offline corpus always return something; network not required
    brain.fetch_knowledge(n_topics=5, verbose=False)
    count_after = brain.decision_log.count()

    assert (count_after - count_before) >= 5, (
        f"Expected ≥5 new decisions after 5-topic fetch; "
        f"got {count_after - count_before}"
    )


def test_all_decisions_have_rationale():
    """Roadmap requirement: each DecisionRecord has a non-empty rationale."""
    brain = _brain()
    from curriculum.open_stage import advance_to_open
    advance_to_open(brain)

    brain.fetch_knowledge(n_topics=3, verbose=False)
    brain.reflect(cycle=1)

    records = brain.recent_decisions(n=20)
    assert records, "No decisions were logged"
    for r in records:
        assert r.rationale.strip() != "", (
            f"Record [{r.subsystem}] '{r.decision}' has empty rationale"
        )


# ── Integration: voice layer ──────────────────────────────────────────────────

def test_chat_respond_what_have_you_been_deciding():
    """
    Roadmap requirement: chat_respond("what have you been deciding?")
    references at least one actual topic from the session.
    """
    brain = _brain()
    from curriculum.open_stage import advance_to_open
    advance_to_open(brain)

    brain.fetch_knowledge(n_topics=3, verbose=False)

    # Get the topics that were actually decided on
    records = brain.recent_decisions(n=10)
    learn_records = [r for r in records if r.subsystem == "feeder"
                     and r.decision.startswith("learn about ")]
    assert learn_records, "No learn decisions to reference"

    reply = brain.voice.chat_respond("what have you been deciding?")
    assert reply, "Got empty reply"

    # At least one decided topic should appear in the reply
    decided_topics = [r.decision.removeprefix("learn about ")
                      for r in learn_records[:3]]
    found = any(topic in reply for topic in decided_topics)
    assert found, (
        f"Reply '{reply[:200]}' doesn't reference any decided topic: "
        f"{decided_topics}"
    )


# ── Persistence: decisions survive a session restart ─────────────────────────

def test_decisions_persist_across_sessions():
    """Decisions survive closing and reopening the DB on the same path."""
    db = tempfile.mktemp(suffix=".db")
    brain1 = _brain(db)
    from curriculum.open_stage import advance_to_open
    advance_to_open(brain1)
    brain1.fetch_knowledge(n_topics=2, verbose=False)
    brain1.reflect(cycle=1)
    count1 = brain1.decision_log.count()
    del brain1

    brain2 = _brain(db)
    count2 = brain2.decision_log.count()
    assert count2 == count1, (
        f"Decisions lost across sessions: had {count1}, found {count2}"
    )
