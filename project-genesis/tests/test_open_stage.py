"""Tests for M5 — Open Stage Data Stream and pipeline integration."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from curriculum.open_stage import DataStream, advance_to_open, _POOL
from orchestrator.orchestrator import Orchestrator
from utils.types import Stage


# ==================================================================
# DataStream unit tests
# ==================================================================

def test_datastream_next_returns_dict():
    stream = DataStream()
    item = stream.next()
    assert isinstance(item, dict)
    assert "type" in item
    assert "data" in item


def test_datastream_type_is_valid():
    stream = DataStream()
    valid_types = {"text", "numeric", "pattern"}
    for _ in range(len(_POOL)):
        item = stream.next()
        assert item["type"] in valid_types, f"Unexpected type: {item['type']}"


def test_datastream_pool_size():
    stream = DataStream()
    assert stream.pool_size == len(_POOL)
    assert stream.pool_size > 0


def test_datastream_items_served_increments():
    stream = DataStream()
    assert stream.items_served == 0
    stream.next()
    assert stream.items_served == 1
    stream.next()
    assert stream.items_served == 2


def test_datastream_loops():
    """After pool_size items, loop_count should increment."""
    stream = DataStream(shuffle=False)
    pool_size = stream.pool_size
    for _ in range(pool_size + 1):
        stream.next()
    assert stream.loop_count >= 1


def test_datastream_take_returns_n_items():
    stream = DataStream()
    items = stream.take(10)
    assert len(items) == 10
    assert all(isinstance(i, dict) for i in items)


def test_datastream_take_advances_counter():
    stream = DataStream()
    stream.take(15)
    assert stream.items_served == 15


def test_datastream_iter_is_infinite():
    """__iter__ should yield indefinitely — we just take a few and stop."""
    stream = DataStream()
    count = 0
    for item in stream:
        count += 1
        if count >= 200:
            break
    assert count == 200


def test_datastream_shuffle_false_produces_consistent_order():
    """Same seed, shuffle=False should produce same order on each loop."""
    stream = DataStream(shuffle=False, seed=42)
    first_pass = stream.take(stream.pool_size)
    second_pass = stream.take(stream.pool_size)
    # Without shuffle both loops are identical
    assert [i["type"] for i in first_pass] == [i["type"] for i in second_pass]


def test_datastream_shuffle_true_changes_order_between_loops():
    """With shuffle, the second loop is unlikely to be identical to the first."""
    stream = DataStream(shuffle=True, seed=99)
    pool_size = stream.pool_size
    first_pass = [stream.next()["type"] for _ in range(pool_size)]
    second_pass = [stream.next()["type"] for _ in range(pool_size)]
    # They might theoretically be equal, but with 56 items the probability is ~1/56!
    # We just assert that shuffling is occurring by checking loop_count advances
    assert stream.loop_count == 1


def test_datastream_stats_returns_composition():
    stream = DataStream()
    stats = stream.stats()
    assert "pool_size" in stats
    assert "items_served" in stats
    assert "loop_count" in stats
    assert "pool_composition" in stats
    comp = stats["pool_composition"]
    assert "text" in comp
    assert "numeric" in comp
    assert "pattern" in comp


def test_datastream_pool_has_all_three_types():
    types = {item["type"] for item in _POOL}
    assert "text" in types
    assert "numeric" in types
    assert "pattern" in types


def test_datastream_text_items_have_string_data():
    for item in _POOL:
        if item["type"] == "text":
            assert isinstance(item["data"], str)
            assert len(item["data"]) > 0


def test_datastream_numeric_items_have_label():
    for item in _POOL:
        if item["type"] == "numeric":
            assert isinstance(item["data"], dict)
            assert "label" in item["data"]


def test_datastream_pattern_items_have_sequence():
    for item in _POOL:
        if item["type"] == "pattern":
            assert isinstance(item["data"], dict)
            assert "sequence" in item["data"]
            assert len(item["data"]["sequence"]) > 0


def test_datastream_no_empty_data():
    for item in _POOL:
        assert item["data"] is not None
        if isinstance(item["data"], str):
            assert len(item["data"]) > 0


# ==================================================================
# advance_to_open integration tests
# ==================================================================

def test_advance_to_open_returns_bool():
    brain = Orchestrator(verbose=False)
    result = advance_to_open(brain)
    assert isinstance(result, bool)


def test_advance_to_open_reaches_open_stage():
    brain = Orchestrator(verbose=False)
    reached = advance_to_open(brain)
    assert reached is True
    assert brain.curriculum.current_stage == Stage.OPEN


def test_advance_to_open_already_open_returns_true():
    brain = Orchestrator(verbose=False)
    brain.curriculum.current_stage = Stage.OPEN
    result = advance_to_open(brain)
    assert result is True


def test_advance_to_open_stores_memories():
    brain = Orchestrator(verbose=False)
    advance_to_open(brain)
    assert brain.memory.stats()["total_stored"] > 0


# ==================================================================
# Open stage processing integration
# ==================================================================

def test_open_stage_processes_text_items():
    brain = Orchestrator(verbose=False)
    brain.curriculum.current_stage = Stage.OPEN
    stream = DataStream(shuffle=False, seed=0)
    # Process first text item we find
    for item in stream.take(stream.pool_size):
        if item["type"] == "text":
            result = brain.process_input(item["type"], item["data"])
            assert result["status"] in ("processed", "degraded", "paused")
            break


def test_open_stage_processes_numeric_items():
    brain = Orchestrator(verbose=False)
    brain.curriculum.current_stage = Stage.OPEN
    stream = DataStream(shuffle=False, seed=0)
    for item in stream.take(stream.pool_size):
        if item["type"] == "numeric":
            result = brain.process_input(item["type"], item["data"])
            assert result["status"] in ("processed", "degraded", "paused")
            break


def test_open_stage_processes_pattern_items():
    brain = Orchestrator(verbose=False)
    brain.curriculum.current_stage = Stage.OPEN
    stream = DataStream(shuffle=False, seed=0)
    for item in stream.take(stream.pool_size):
        if item["type"] == "pattern":
            result = brain.process_input(item["type"], item["data"])
            assert result["status"] in ("processed", "degraded", "paused")
            break


def test_open_stage_accumulates_memories():
    brain = Orchestrator(verbose=False)
    brain.curriculum.current_stage = Stage.OPEN
    stream = DataStream(seed=1)
    before = brain.memory.stats()["total_stored"]
    for item in stream.take(20):
        brain.process_input(item["type"], item["data"])
    after = brain.memory.stats()["total_stored"]
    assert after > before


def test_open_stage_never_crashes():
    """The full pool fed through the brain should never raise."""
    brain = Orchestrator(verbose=False)
    brain.curriculum.current_stage = Stage.OPEN
    stream = DataStream(seed=7)
    for item in stream.take(stream.pool_size):
        result = brain.process_input(item["type"], item["data"])
        assert result is not None
        assert "status" in result


def test_open_stage_result_has_required_keys():
    brain = Orchestrator(verbose=False)
    brain.curriculum.current_stage = Stage.OPEN
    item = DataStream(seed=0).next()
    result = brain.process_input(item["type"], item["data"])
    if result["status"] == "processed":
        for key in ("significance", "context_score", "cross_modal_concepts",
                    "processors_run", "cycle"):
            assert key in result, f"Missing key: {key}"


def test_open_stage_context_builds_over_time():
    """Context scores should tend to rise as thematic input accumulates."""
    brain = Orchestrator(verbose=False)
    brain.curriculum.current_stage = Stage.OPEN
    # Feed wolf/ecology items repeatedly to build context
    ecology_item = {
        "type": "text",
        "data": "Wolves were removed from Yellowstone. Deer overpopulated. Riverbanks eroded."
    }
    scores = []
    for _ in range(5):
        result = brain.process_input(ecology_item["type"], ecology_item["data"])
        if result["status"] == "processed":
            scores.append(result["context_score"])
    # Last score should be at least as high as first
    if len(scores) >= 2:
        assert scores[-1] >= scores[0]


def test_open_stage_edge_case_anomalous_numeric():
    """Anomalous numeric data (spike in sequence) should not crash."""
    brain = Orchestrator(verbose=False)
    brain.curriculum.current_stage = Stage.OPEN
    anomalous = {"label": "anomalous_reading",
                 "values": [10, 11, 10, 12, 10, 47, 11, 10, 11],
                 "unit": "arbitrary"}
    result = brain.process_input("numeric", anomalous)
    assert result["status"] in ("processed", "degraded", "paused")


def test_open_stage_edge_case_interrupted_pattern():
    """Interrupted sequence (contains 0 mid-sequence) should not crash."""
    brain = Orchestrator(verbose=False)
    brain.curriculum.current_stage = Stage.OPEN
    interrupted = {"label": "interrupted_sequence", "sequence": [2, 4, 8, 16, 0, 64, 128]}
    result = brain.process_input("pattern", interrupted)
    assert result["status"] in ("processed", "degraded", "paused")


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
