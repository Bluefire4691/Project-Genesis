"""
GenesisEngine integration tests — the shared session engine both frontends
(ui.py, gui.py) drive.

Real Orchestrator, real threads, no mocks.  Asserts user-observable outcomes:
cognition makes progress, commands answer, resource controls apply, parsing
rules keep conversation and commands apart, stop() saves.
"""

import os
import sys
import time
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from engine import GenesisEngine
from orchestrator.orchestrator import Orchestrator


def _brain(db=None) -> Orchestrator:
    return Orchestrator(verbose=False,
                        db_path=db or tempfile.mktemp(suffix=".db"),
                        resume=False)


# ── Parsing / classification ──────────────────────────────────────────────────

def test_parse_slash_only_returns_none():
    assert GenesisEngine.parse("/") is None
    assert GenesisEngine.parse("///") is None
    assert GenesisEngine.parse("") is None


def test_parse_forms():
    assert GenesisEngine.parse("speed 8") == ("speed", "8")
    assert GenesisEngine.parse("/reflect") == ("reflect", "")
    assert GenesisEngine.parse("relations:wolf") == ("relations", "wolf")
    assert GenesisEngine.parse("Hello there") == ("hello", "there")


def test_resource_words_with_prose_are_not_commands():
    assert not GenesisEngine.is_local("memory", "is fascinating")
    assert not GenesisEngine.is_local("speed", "matters to thinking")
    assert not GenesisEngine.is_local("explore", "the sea")
    assert GenesisEngine.is_local("memory", "800")
    assert GenesisEngine.is_local("speed", "")
    assert GenesisEngine.is_local("explore", "")


def test_quit_requires_bare_word():
    assert GenesisEngine.is_quit("quit", "")
    assert not GenesisEngine.is_quit("quit", "smoking is hard")


# ── Resource controls ─────────────────────────────────────────────────────────

def test_setters_clamp_and_apply():
    brain = _brain()
    eng = GenesisEngine(brain)
    assert eng.set_speed(99) == 10
    assert eng.set_speed(0) == 1
    assert eng.set_batch(5000) == 1000
    assert eng.set_memory(50) == 100          # floor
    assert brain.memory._working.capacity == 100
    assert eng.set_memory(1200) == 1200
    assert brain.memory._working.capacity == 1200
    snap = eng.snapshot_controls()
    assert snap["speed"] == 1 and snap["memory"] == 1200


def test_run_local_messages():
    eng = GenesisEngine(_brain())
    assert "Speed 5" in eng.run_local("speed", "5")
    assert "Usage" in eng.run_local("speed", "fast")
    assert "topic" in eng.run_local("explore", "").lower()


# ── run_command against a real brain ──────────────────────────────────────────

def test_run_command_status_and_chat():
    brain = _brain()
    from curriculum.open_stage import advance_to_open
    advance_to_open(brain)

    eng = GenesisEngine(brain)

    events = eng.run_command("status", "", "status")
    assert events and events[0][0] == "genesis"
    assert "Cycle" in events[0][1]

    events = eng.run_command("hello", "", "hello")
    assert events and events[0][1]          # some reply, never empty


def test_run_command_learn_with_prose_is_conversation():
    brain = _brain()
    from curriculum.open_stage import advance_to_open
    advance_to_open(brain)
    eng = GenesisEngine(brain)
    # Must NOT trigger a fetch — falls through to chat
    events = eng.run_command("learn", "something for me", "learn something for me")
    assert events and events[0][0] == "genesis"


def test_run_command_never_raises_on_unknown():
    eng = GenesisEngine(_brain())
    events = eng.run_command("relations", "", "relations")   # no arg → chat path
    assert isinstance(events, list) and events


# ── Live engine: cognition progresses, stop() saves ──────────────────────────

def test_engine_runs_and_stops_with_save():
    db = tempfile.mktemp(suffix=".db")
    brain = _brain(db)
    from curriculum.open_stage import advance_to_open
    advance_to_open(brain)

    said = []
    status = []
    eng = GenesisEngine(
        brain, speed=10, batch=20,
        on_genesis=said.append,
        on_status=status.append,
    )
    start_cycle = brain.cycle_count
    eng.start()
    time.sleep(3.0)
    assert brain.cycle_count > start_cycle, "cognition made no progress"
    assert status, "no status snapshots emitted"
    snap = status[-1]
    assert {"cycle", "drives", "controls", "cyc_per_sec", "concepts"} <= set(snap)
    # Full biological drives present (regression: process_input result lacks them)
    assert "hunger" in snap["drives"]

    assert eng.stop(timeout=30.0), "stop() failed to save"

    # A fresh brain on the same DB resumes past the saved cycle count
    brain2 = Orchestrator(verbose=False, db_path=db, resume=True)
    assert brain2.cycle_count > 0
