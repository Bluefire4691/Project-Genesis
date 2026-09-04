"""Tests for the M3 Interaction Layer."""

import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from memory.memory import MemorySystem
from interface.expression import ExpressionEngine, ExpressionSnapshot
from interface.observer import Observer, SystemState
from interface.interaction_log import InteractionLog, EventKind
from interface.interventions import InterventionEngine
from interface import InteractionLayer


def _tmp_db(name="test.db") -> str:
    return os.path.join(tempfile.mkdtemp(), name)


def _mem(n_items=10) -> MemorySystem:
    mem = MemorySystem(db_path=_tmp_db("mem.db"), working_capacity=100)
    for i in range(n_items):
        mem.store(f"key:{i}", f"content about topic {i}", f"context {i}", "text", 0.5)
    return mem


# ==================================================================
# ExpressionEngine
# ==================================================================

def test_expression_snapshot_structure():
    mem = _mem(5)
    eng = ExpressionEngine(mem)
    snap = eng.snapshot(cycle=1)
    assert isinstance(snap, ExpressionSnapshot)
    assert snap.cycle == 1
    assert 0.0 <= snap.working_memory_load <= 1.0
    assert isinstance(snap.attention_top, list)
    assert isinstance(snap.association_clusters, list)
    assert isinstance(snap.unresolved, list)
    assert isinstance(snap.source_diversity, dict)


def test_expression_surfaces_attention():
    mem = _mem(10)
    # Access one item many times so it rises to top
    for _ in range(5):
        mem.recall("key:3")
    eng = ExpressionEngine(mem)
    snap = eng.snapshot(cycle=1)
    keys = [item["key"] for item in snap.attention_top]
    assert "key:3" in keys


def test_expression_never_crashes():
    """snapshot() must not raise on empty or unusual memory state."""
    mem = MemorySystem(db_path=_tmp_db(), working_capacity=100)
    eng = ExpressionEngine(mem)
    snap = eng.snapshot(cycle=0)
    assert snap is not None


def test_expression_summary_is_string():
    mem = _mem(3)
    eng = ExpressionEngine(mem)
    snap = eng.snapshot(1)
    assert isinstance(snap.summary(), str)


def test_expression_to_dict():
    mem = _mem(3)
    snap = ExpressionEngine(mem).snapshot(1)
    d = snap.to_dict()
    assert "timestamp" in d
    assert "attention_top" in d
    assert "association_clusters" in d
    assert "unresolved" in d


def test_expression_unresolved_low_relevance():
    """Items with very low relevance and no associations appear in unresolved."""
    mem = MemorySystem(db_path=_tmp_db(), working_capacity=100)
    mem.store("orphan", "strange isolated thing", "ctx", "text", 0.05)
    snap = ExpressionEngine(mem, unresolved_threshold=0.2).snapshot(1)
    unresolved_keys = [u["key"] for u in snap.unresolved]
    assert "orphan" in unresolved_keys


def test_expression_source_diversity():
    mem = MemorySystem(db_path=_tmp_db(), working_capacity=100)
    mem.store("t1", "text item", "ctx", "text", 0.5)
    mem.store("n1", "numeric item", "ctx", "numeric", 0.5)
    snap = ExpressionEngine(mem).snapshot(1)
    assert "text" in snap.source_diversity
    assert "numeric" in snap.source_diversity


# ==================================================================
# Observer
# ==================================================================

def _make_snap(cycle=1, top_key="k1", load=0.5, diversity=2, sources=None) -> ExpressionSnapshot:
    return ExpressionSnapshot(
        timestamp=time.time(),
        cycle=cycle,
        attention_top=[{"key": top_key, "content": "x", "context": "x",
                        "relevance": 0.5, "access_count": 1, "source": "text"}],
        association_clusters=[],
        unresolved=[],
        source_diversity=sources or {"text": 3, "numeric": 2},
        working_memory_load=load,
    )


def test_observer_normal_state_by_default():
    obs = Observer()
    snap = _make_snap()
    report = obs.observe(snap, energy=0.9, error_count=0,
                         new_memories_this_cycle=2, total_associations=5)
    # Needs many cycles to detect stagnation — starts normal
    assert report.state == SystemState.NORMAL


def test_observer_detects_stagnation_no_new_memories():
    obs = Observer(stagnation_no_associations_cycles=3)
    obs.COMMITMENT_CYCLES = 3
    # Feed many cycles with zero new memories
    for i in range(10):
        snap = _make_snap(cycle=i, top_key=f"k{i}")
        obs.observe(snap, energy=0.9, error_count=0,
                    new_memories_this_cycle=0, total_associations=0)
    assert obs.state == SystemState.STAGNANT


def test_observer_detects_danger_energy_collapse():
    obs = Observer(danger_energy_floor=0.15)
    obs.COMMITMENT_CYCLES = 3
    for i in range(10):
        snap = _make_snap(cycle=i, top_key=f"k{i % 3}")
        obs.observe(snap, energy=0.05, error_count=0,
                    new_memories_this_cycle=1, total_associations=i)
    assert obs.state == SystemState.DANGER


def test_observer_detects_danger_diversity_collapse():
    obs = Observer(danger_diversity_floor=1)
    obs.COMMITMENT_CYCLES = 3
    for i in range(10):
        snap = _make_snap(cycle=i, top_key=f"k{i}", sources={"text": 10})
        obs.observe(snap, energy=0.8, error_count=0,
                    new_memories_this_cycle=1, total_associations=i)
    assert obs.state == SystemState.DANGER


def test_observer_state_returns_normal_when_healthy():
    obs = Observer()
    # Vary top key and provide new memories — no stagnation signal
    for i in range(20):
        snap = _make_snap(cycle=i, top_key=f"k{i}", sources={"text": 3, "numeric": 2})
        obs.observe(snap, energy=0.8, error_count=0,
                    new_memories_this_cycle=2, total_associations=i * 2)
    assert obs.state == SystemState.NORMAL


def test_observer_report_structure():
    obs = Observer()
    snap = _make_snap()
    report = obs.observe(snap, energy=0.8, error_count=0,
                         new_memories_this_cycle=1, total_associations=3)
    d = report.to_dict()
    assert "state" in d
    assert "recommendation" in d
    assert "stagnation_signals" in d
    assert "danger_signals" in d


def test_observer_never_crashes():
    obs = Observer()
    empty_snap = ExpressionSnapshot(
        timestamp=time.time(), cycle=0,
        attention_top=[], association_clusters=[], unresolved=[],
        source_diversity={}, working_memory_load=0.0,
    )
    report = obs.observe(empty_snap, energy=0.5, error_count=0,
                         new_memories_this_cycle=0, total_associations=0)
    assert report is not None


# ==================================================================
# InteractionLog
# ==================================================================

def test_log_human_input():
    log = InteractionLog(_tmp_db())
    entry = log.log_human_input(1, "text", "hello world")
    assert entry.kind == EventKind.HUMAN_INPUT.value
    assert entry.source == "human"


def test_log_genesis_expression():
    log = InteractionLog(_tmp_db())
    snap_dict = {"attention_top": [{"key": "k1"}], "cycle": 1}
    entry = log.log_genesis_expression(1, snap_dict)
    assert entry.kind == EventKind.GENESIS_EXPR.value
    assert entry.source == "genesis"


def test_log_intervention():
    log = InteractionLog(_tmp_db())
    entry = log.log_intervention(1, "pause", "danger signal", {})
    assert entry.kind == EventKind.INTERVENTION.value


def test_log_total_retention():
    log = InteractionLog(_tmp_db())
    for i in range(30):
        log.log_human_input(i, "text", f"input {i}")
    assert log.total() == 30


def test_log_persists_across_reopen():
    path = _tmp_db()
    log1 = InteractionLog(path)
    log1.log_human_input(1, "text", "persist me")
    log1.close()
    log2 = InteractionLog(path)
    assert log2.total() >= 1


def test_log_by_kind():
    log = InteractionLog(_tmp_db())
    log.log_human_input(1, "text", "a")
    log.log_human_input(2, "text", "b")
    log.log_intervention(3, "pause", "test", {})
    human_entries = log.by_kind(EventKind.HUMAN_INPUT)
    assert len(human_entries) == 2


def test_log_stats():
    log = InteractionLog(_tmp_db())
    log.log_human_input(1, "text", "x")
    log.log_system_event(1, "start")
    s = log.stats()
    assert "total_entries" in s
    assert "by_kind" in s


# ==================================================================
# InterventionEngine
# ==================================================================

def test_interventions_pause_and_resume():
    ie = InterventionEngine()
    assert not ie.is_paused
    ie.pause("test reason", cycle=1)
    assert ie.is_paused
    assert ie.pause_reason == "test reason"
    result = ie.resume(cycle=2)
    assert result is True
    assert not ie.is_paused


def test_interventions_resume_when_not_paused():
    ie = InterventionEngine()
    result = ie.resume(cycle=1)
    assert result is False


def test_interventions_inject_stimulus():
    ie = InterventionEngine()
    assert not ie.stimulus_pending
    ie.inject_stimulus("hello world", "text", "stagnation")
    assert ie.stimulus_pending
    result = ie.next_stimulus()
    assert result is not None
    assert result == ("text", "hello world")
    assert not ie.stimulus_pending


def test_interventions_stimulus_queue_fifo():
    ie = InterventionEngine()
    ie.inject_stimulus("first", "text")
    ie.inject_stimulus("second", "text")
    assert ie.next_stimulus() == ("text", "first")
    assert ie.next_stimulus() == ("text", "second")
    assert ie.next_stimulus() is None


def test_interventions_pause_idempotent():
    ie = InterventionEngine()
    ie.pause("reason1", 1)
    ie.pause("reason2", 2)  # Should not create a second record
    assert ie._total_pauses == 1


def test_interventions_report():
    ie = InterventionEngine()
    ie.pause("test", 1)
    r = ie.report()
    assert r["is_paused"] is True
    assert r["pause_reason"] == "test"


# ==================================================================
# InteractionLayer (integration)
# ==================================================================

def test_interaction_layer_cycle_returns_state():
    mem = _mem(5)
    layer = InteractionLayer(mem, log_db_path=_tmp_db(), auto_intervene=False)
    state = layer.cycle({"energy": 0.9, "error_count": 0, "memories_stored": 5}, cycle=1)
    assert "is_paused" in state
    assert "state" in state


def test_interaction_layer_feed_queues_stimulus():
    mem = _mem(3)
    layer = InteractionLayer(mem, log_db_path=_tmp_db(), auto_intervene=False)
    layer.feed("text", "a new idea")
    assert layer._interventions.stimulus_pending
    result = layer.next_stimulus()
    assert result == ("text", "a new idea")


def test_interaction_layer_manual_pause_resume():
    mem = _mem(3)
    layer = InteractionLayer(mem, log_db_path=_tmp_db(), auto_intervene=False)
    layer.pause("manual test")
    assert layer.is_paused
    layer.resume()
    assert not layer.is_paused


def test_interaction_layer_expression_not_none_after_cycle():
    mem = _mem(5)
    layer = InteractionLayer(mem, log_db_path=_tmp_db(),
                             expression_cadence=1, auto_intervene=False)
    layer.cycle({"energy": 0.9, "error_count": 0, "memories_stored": 5}, cycle=1)
    assert layer.expression() is not None


def test_interaction_layer_report_structure():
    mem = _mem(3)
    layer = InteractionLayer(mem, log_db_path=_tmp_db(), auto_intervene=False)
    layer.cycle({"energy": 0.9, "error_count": 0, "memories_stored": 3}, cycle=1)
    r = layer.report()
    assert "interaction_layer" in r
    inner = r["interaction_layer"]
    assert "observer" in inner
    assert "interventions" in inner
    assert "log" in inner


def test_interaction_layer_log_records_human_feed():
    mem = _mem(3)
    layer = InteractionLayer(mem, log_db_path=_tmp_db(), auto_intervene=False)
    layer.feed("text", "test input", note="manual feed test")
    entries = layer._log.by_kind(EventKind.HUMAN_INPUT)
    assert len(entries) >= 1


def test_interaction_layer_with_orchestrator():
    """Full integration: Orchestrator with InteractionLayer processes input."""
    from orchestrator.orchestrator import Orchestrator
    brain = Orchestrator(verbose=False)
    result = brain.process_input("text", "Cooperation enables things no individual could do alone.")
    assert result["status"] == "processed"
    status = brain.full_status()
    assert "interaction_layer" in status


def test_interaction_layer_paused_orchestrator_holds():
    """When paused, Orchestrator returns 'paused' status without processing."""
    from orchestrator.orchestrator import Orchestrator
    brain = Orchestrator(verbose=False)
    brain.interaction.pause("test pause")
    result = brain.process_input("text", "this should not be processed")
    assert result["status"] == "paused"
    brain.interaction.resume()
    result = brain.process_input("text", "this should be processed")
    assert result["status"] == "processed"


# ==================================================================
# Runner
# ==================================================================

if __name__ == "__main__":
    import traceback
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            print(f"  ✅ {test.__name__}")
            passed += 1
        except Exception as e:
            print(f"  ❌ {test.__name__}: {e}")
            traceback.print_exc()
            failed += 1
    print(f"\n  {passed} passed, {failed} failed")
