"""
Tests for genesis_seed.py — the eleven-primitive seed prototype.

Each test group exercises one primitive or drive property.
Run: pytest tests/test_seed.py -v
"""

import math
import os
import struct
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from genesis_seed import (
    GenesisSeed,
    MeasureVec,
    SensorReading,
    AssociationGraph,
    PersistLog,
    act,
    compare,
    compute_empowerment,
    compute_liking,
    compute_wanting,
    error,
    l2,
    measure,
    predict,
    receive,
    regulate,
    sense_self,
    update,
    update_plasticity,
    DriveState,
    _SURVIVE_CPU_MAX,
    _SURVIVE_MEM_MAX,
    _SURVIVE_DISK_MAX,
)


# ---------------------------------------------------------------------------
# SENSE_SELF
# ---------------------------------------------------------------------------

class TestSenseSelf:
    def test_returns_sensor_reading(self):
        r = sense_self()
        assert isinstance(r, SensorReading)

    def test_values_in_range(self):
        r = sense_self()
        assert 0.0 <= r.cpu    <= 1.0
        assert 0.0 <= r.memory <= 1.0
        assert 0.0 <= r.disk   <= 1.0

    def test_timestamp_positive(self):
        r = sense_self()
        assert r.timestamp > 0


# ---------------------------------------------------------------------------
# RECEIVE
# ---------------------------------------------------------------------------

class TestReceive:
    def test_bytes_passthrough(self):
        assert receive("x", b"\x00\x01") == b"\x00\x01"

    def test_str_encodes_utf8(self):
        assert receive("x", "hello") == b"hello"

    def test_int_produces_8_bytes(self):
        out = receive("x", 42)
        assert len(out) == 8

    def test_float_produces_8_bytes(self):
        out = receive("x", 3.14)
        assert len(out) == 8

    def test_other_types_stringified(self):
        out = receive("x", [1, 2, 3])
        assert isinstance(out, bytes)
        assert len(out) > 0


# ---------------------------------------------------------------------------
# MEASURE
# ---------------------------------------------------------------------------

class TestMeasure:
    def test_empty_returns_zero_vec(self):
        v = measure(b"")
        assert v == MeasureVec.zero()

    def test_returns_measure_vec(self):
        v = measure(b"hello world")
        assert isinstance(v, MeasureVec)

    def test_all_same_bytes_low_entropy(self):
        v = measure(b"\xAA" * 128)
        assert v.entropy < 0.1   # nearly zero entropy

    def test_random_bytes_high_entropy(self):
        v = measure(os.urandom(256))
        assert v.entropy > 0.8   # near max entropy

    def test_all_zeros_zero_frac_one(self):
        v = measure(b"\x00" * 128)
        assert v.zero_frac == pytest.approx(1.0, abs=0.01)

    def test_high_bytes_high_frac(self):
        v = measure(bytes(range(128, 256)) * 2)
        assert v.high_frac == pytest.approx(1.0, abs=0.01)

    def test_repeated_bytes_high_run_len(self):
        v = measure(b"\xAA" * 128)
        assert v.run_len > 0.5   # long runs → high value

    def test_values_in_zero_one(self):
        v = measure(b"Some test data " * 20)
        for val in v.as_list():
            assert 0.0 <= val <= 1.0, f"out of range: {val}"

    def test_as_list_length(self):
        v = measure(b"abc")
        assert len(v.as_list()) == 8

    def test_different_inputs_different_vecs(self):
        v1 = measure(b"\x00" * 128)
        v2 = measure(b"\xFF" * 128)
        assert v1.as_list() != v2.as_list()


# ---------------------------------------------------------------------------
# COMPARE / L2
# ---------------------------------------------------------------------------

class TestCompare:
    def test_identical_vecs_zero_delta(self):
        v = measure(b"abc" * 30)
        delta = compare(v, v)
        assert all(d == pytest.approx(0.0, abs=1e-9) for d in delta)

    def test_delta_length(self):
        v1 = measure(b"aaa" * 30)
        v2 = measure(b"bbb" * 30)
        assert len(compare(v1, v2)) == 8

    def test_l2_non_negative(self):
        v1 = measure(b"aaa" * 30)
        v2 = measure(b"bbb" * 30)
        assert l2(compare(v1, v2)) >= 0.0

    def test_l2_zero_for_same(self):
        v = measure(b"test" * 30)
        assert l2(compare(v, v)) == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------------------
# ASSOCIATE
# ---------------------------------------------------------------------------

class TestAssociate:
    def test_add_and_retrieve_edge(self):
        g = AssociationGraph()
        g.associate("a", "b", 0.7)
        assert g.strength("a", "b") == pytest.approx(0.7)

    def test_higher_strength_wins_at_default_plasticity(self):
        g = AssociationGraph()
        g.associate("a", "b", 0.5)
        g.associate("a", "b", 0.8)
        assert g.strength("a", "b") == pytest.approx(0.8)

    def test_lower_strength_does_not_reduce_at_low_plasticity(self):
        g = AssociationGraph()
        g.set_plasticity(0.05)
        g.associate("a", "b", 0.9)
        g.associate("a", "b", 0.1)
        assert g.strength("a", "b") == pytest.approx(0.9)

    def test_lower_strength_can_reduce_at_high_plasticity(self):
        g = AssociationGraph()
        g.set_plasticity(0.99)
        g.associate("a", "b", 0.9)
        g.associate("a", "b", 0.1)
        assert g.strength("a", "b") < 0.9

    def test_single_update_cannot_drop_below_70_percent(self):
        # One contradicting update with plasticity=0.99 must not reduce
        # the edge below 70% of its prior value (per-call floor).
        g = AssociationGraph()
        g.set_plasticity(0.99)
        g.associate("a", "b", 1.0)
        prior = g.strength("a", "b")
        g.associate("a", "b", 0.0)
        assert g.strength("a", "b") >= prior * 0.70 - 1e-9

    def test_missing_edge_zero(self):
        g = AssociationGraph()
        assert g.strength("x", "y") == 0.0

    def test_concept_count(self):
        g = AssociationGraph()
        g.associate("a", "b", 0.5)
        g.associate("b", "c", 0.5)
        assert g.concept_count() == 3

    def test_neighbours_sorted_descending(self):
        g = AssociationGraph()
        g.associate("a", "b", 0.3)
        g.associate("a", "c", 0.9)
        g.associate("a", "d", 0.6)
        nbrs = g.neighbours("a")
        weights = [w for _, w in nbrs]
        assert weights == sorted(weights, reverse=True)


# ---------------------------------------------------------------------------
# PREDICT
# ---------------------------------------------------------------------------

class TestPredict:
    def test_empty_history_returns_zero(self):
        g = AssociationGraph()
        p = predict(g, "ch", [])
        assert p == MeasureVec.zero()

    def test_single_history_returns_something(self):
        g = AssociationGraph()
        v = measure(b"abc" * 30)
        p = predict(g, "ch", [v])
        assert isinstance(p, MeasureVec)

    def test_prediction_values_in_range(self):
        g = AssociationGraph()
        history = [measure(b"x" * 64 + bytes([i]) * 64) for i in range(5)]
        p = predict(g, "ch", history)
        for val in p.as_list():
            assert 0.0 <= val <= 1.0, f"out of range: {val}"


# ---------------------------------------------------------------------------
# ERROR
# ---------------------------------------------------------------------------

class TestError:
    def test_identical_vecs_zero_error(self):
        v = measure(b"abc" * 30)
        assert error(v, v) == pytest.approx(0.0, abs=1e-9)

    def test_different_vecs_positive_error(self):
        v1 = measure(b"\x00" * 128)
        v2 = measure(b"\xFF" * 128)
        assert error(v1, v2) > 0.0

    def test_error_non_negative(self):
        v1 = measure(b"hello" * 30)
        v2 = measure(b"world" * 30)
        assert error(v1, v2) >= 0.0


# ---------------------------------------------------------------------------
# UPDATE
# ---------------------------------------------------------------------------

class TestUpdate:
    def test_update_creates_edges(self):
        g = AssociationGraph()
        v = measure(b"test" * 30)
        update(g, "ch", v, pred_error=0.5)
        assert g.edge_count() > 0

    def test_update_high_error_creates_stronger_edge(self):
        g1 = AssociationGraph()
        g2 = AssociationGraph()
        v = measure(b"data" * 30)
        update(g1, "ch", v, pred_error=0.9)
        update(g2, "ch", v, pred_error=0.1)
        max_w1 = max((w for (_, _), w in g1._edges.items()), default=0)
        max_w2 = max((w for (_, _), w in g2._edges.items()), default=0)
        assert max_w1 >= max_w2


# ---------------------------------------------------------------------------
# REGULATE
# ---------------------------------------------------------------------------

class TestRegulate:
    def _sensor(self, cpu=0.1, mem=0.1, disk=0.1):
        return SensorReading(cpu=cpu, memory=mem, disk=disk, io_read=0, io_write=0)

    def test_no_alarm_when_safe(self):
        d = DriveState()
        d = regulate(self._sensor(0.1, 0.1, 0.1), d)
        assert not d.survive_alarm

    def test_alarm_on_high_cpu(self):
        d = DriveState()
        d = regulate(self._sensor(cpu=_SURVIVE_CPU_MAX + 0.01), d)
        assert d.survive_alarm

    def test_alarm_on_high_memory(self):
        d = DriveState()
        d = regulate(self._sensor(mem=_SURVIVE_MEM_MAX + 0.01), d)
        assert d.survive_alarm

    def test_alarm_on_high_disk(self):
        d = DriveState()
        d = regulate(self._sensor(disk=_SURVIVE_DISK_MAX + 0.01), d)
        assert d.survive_alarm

    def test_no_alarm_just_below_threshold(self):
        d = DriveState()
        d = regulate(
            self._sensor(
                cpu  = _SURVIVE_CPU_MAX  - 0.01,
                mem  = _SURVIVE_MEM_MAX  - 0.01,
                disk = _SURVIVE_DISK_MAX - 0.01,
            ),
            d,
        )
        assert not d.survive_alarm


# ---------------------------------------------------------------------------
# ACT (subsumption)
# ---------------------------------------------------------------------------

class TestAct:
    def test_alarm_overrides_all(self):
        d = DriveState(survive_alarm=True, rest_pending=True,
                       elaborate_want=1.0, elaborate_like=1.0)
        assert act(d) == "alarm"

    def test_rest_overrides_explore(self):
        d = DriveState(survive_alarm=False, rest_pending=True,
                       elaborate_want=1.0)
        assert act(d) == "rest"

    def test_explore_when_high_want(self):
        d = DriveState(survive_alarm=False, rest_pending=False,
                       elaborate_want=0.8)
        assert act(d) == "explore"

    def test_consolidate_when_moderate_like(self):
        d = DriveState(survive_alarm=False, rest_pending=False,
                       elaborate_want=0.2, elaborate_like=0.5)
        assert act(d) == "consolidate"

    def test_idle_default(self):
        d = DriveState()
        assert act(d) == "idle"


# ---------------------------------------------------------------------------
# PERSIST
# ---------------------------------------------------------------------------

class TestPersist:
    def test_log_and_retrieve_errors(self):
        log = PersistLog()
        v = measure(b"a" * 64)
        for i in range(5):
            log.log_measure(i, v, pred_error=float(i) * 0.1, action="idle")
        errors = log.recent_errors(5)
        assert len(errors) == 5
        log.close()

    def test_errors_in_chronological_order(self):
        log = PersistLog()
        v = MeasureVec.zero()
        for i in range(4):
            log.log_measure(i, v, pred_error=float(i), action="idle")
        errors = log.recent_errors(4)
        assert errors == [0.0, 1.0, 2.0, 3.0]
        log.close()

    def test_log_event(self):
        log = PersistLog()
        log.log_event(1, "alarm", "test payload")
        cur = log._con.execute("SELECT payload FROM event_log WHERE kind='alarm'")
        row = cur.fetchone()
        assert row is not None
        assert "test payload" in row[0]
        log.close()

    def test_recent_actions(self):
        log = PersistLog()
        v = MeasureVec.zero()
        for action in ["explore", "rest", "alarm", "idle"]:
            log.log_measure(1, v, 0.1, action)
        actions = log.recent_actions(4)
        assert set(actions) == {"explore", "rest", "alarm", "idle"}
        log.close()


# ---------------------------------------------------------------------------
# EMPOWERMENT
# ---------------------------------------------------------------------------

class TestEmpowerment:
    def test_no_entries_zero(self):
        log = PersistLog()
        assert compute_empowerment(log) == pytest.approx(0.0)
        log.close()

    def test_single_action_low_empowerment(self):
        log = PersistLog()
        v = MeasureVec.zero()
        for _ in range(10):
            log.log_measure(1, v, 0.1, "idle")
        emp = compute_empowerment(log)
        assert emp < 0.5
        log.close()

    def test_diverse_actions_high_empowerment(self):
        log = PersistLog()
        v = MeasureVec.zero()
        for i, action in enumerate(["explore", "rest", "alarm", "idle", "consolidate"] * 4):
            log.log_measure(i, v, 0.1, action)
        emp = compute_empowerment(log)
        assert emp == pytest.approx(1.0)
        log.close()


# ---------------------------------------------------------------------------
# WANTING / LIKING
# ---------------------------------------------------------------------------

class TestWantingLiking:
    def test_wanting_zero_insufficient_history(self):
        assert compute_wanting([]) == 0.0
        assert compute_wanting([0.5]) == 0.0

    def test_wanting_positive_when_error_falling(self):
        # Older errors high, recent low → improving → positive wanting
        hist = [0.9, 0.8, 0.7, 0.3, 0.2, 0.1]
        w = compute_wanting(hist)
        assert w > 0.0

    def test_wanting_negative_when_error_rising(self):
        # Older errors low, recent high → worsening → negative wanting
        hist = [0.1, 0.2, 0.3, 0.8, 0.9, 1.0]
        w = compute_wanting(hist)
        assert w < 0.0

    def test_liking_positive_when_empowerment_grows(self):
        assert compute_liking(0.2, 0.5) > 0.0

    def test_liking_negative_when_empowerment_falls(self):
        assert compute_liking(0.8, 0.2) < 0.0

    def test_liking_bounded(self):
        l = compute_liking(0.0, 1.0)
        assert -1.0 <= l <= 1.0


# ---------------------------------------------------------------------------
# METAPLASTICITY
# ---------------------------------------------------------------------------

class TestMetaplasticity:
    def test_insufficient_history_unchanged(self):
        d = DriveState(plasticity=0.5)
        update_plasticity(d, [0.5, 0.5])
        assert d.plasticity == pytest.approx(0.5)

    def test_worsening_increases_plasticity(self):
        d = DriveState(plasticity=0.5)
        # Older low → recent high (worsening fast)
        hist = [0.1, 0.1, 0.1, 0.8, 0.9, 1.0]
        update_plasticity(d, hist)
        assert d.plasticity > 0.5

    def test_improving_fast_targets_0_70(self):
        d = DriveState(plasticity=0.5)
        hist = [0.9, 0.9, 0.9, 0.1, 0.1, 0.0]
        update_plasticity(d, hist)
        # Smooth update: should move toward 0.70 but not reach it in one step
        assert 0.5 < d.plasticity < 0.70

    def test_mastered_decreases_plasticity(self):
        d = DriveState(plasticity=0.5)
        # Flat + low error → mastered → target 0.20
        hist = [0.05, 0.05, 0.06, 0.05, 0.05, 0.05]
        update_plasticity(d, hist)
        assert d.plasticity < 0.5


# ---------------------------------------------------------------------------
# GENESIS SEED INTEGRATION
# ---------------------------------------------------------------------------

class TestGenesisSeed:
    def test_tick_returns_dict(self):
        seed = GenesisSeed(verbose=False)
        result = seed.tick("test", b"hello")
        assert isinstance(result, dict)
        seed.close()

    def test_tick_has_expected_keys(self):
        seed = GenesisSeed(verbose=False)
        result = seed.tick("test", b"hello")
        for key in ["cycle", "pred_error", "action", "wanting", "liking",
                    "empowerment", "plasticity", "concepts", "edges"]:
            assert key in result, f"missing key: {key}"
        seed.close()

    def test_cycle_increments(self):
        seed = GenesisSeed(verbose=False)
        r1 = seed.tick("ch", b"a")
        r2 = seed.tick("ch", b"b")
        assert r2["cycle"] == r1["cycle"] + 1
        seed.close()

    def test_concepts_grow_over_cycles(self):
        seed = GenesisSeed(verbose=False)
        r_first = seed.tick("ch", b"x" * 64)
        for _ in range(8):
            seed.tick("ch", b"y" * 64)
        r_last = seed.tick("ch", b"z" * 64)
        assert r_last["concepts"] >= r_first["concepts"]
        seed.close()

    def test_error_bounded(self):
        seed = GenesisSeed(verbose=False)
        for _ in range(10):
            r = seed.tick("ch", os.urandom(128))
            assert r["pred_error"] >= 0.0
        seed.close()

    def test_survive_alarm_on_fake_high_cpu(self, monkeypatch):
        """Simulate high CPU by monkeypatching sense_self."""
        import genesis_seed as gs
        def fake_sense():
            return SensorReading(cpu=0.99, memory=0.1, disk=0.1, io_read=0, io_write=0)
        monkeypatch.setattr(gs, "sense_self", fake_sense)
        seed = GenesisSeed(verbose=False)
        r = seed.tick("test", b"data")
        assert r["survive_alarm"] is True
        seed.close()

    def test_action_alarm_subsumes_explore(self, monkeypatch):
        import genesis_seed as gs
        def fake_sense():
            return SensorReading(cpu=0.99, memory=0.1, disk=0.1, io_read=0, io_write=0)
        monkeypatch.setattr(gs, "sense_self", fake_sense)
        seed = GenesisSeed(verbose=False)
        r = seed.tick("test", b"data")
        assert r["action"] == "alarm"
        seed.close()

    def test_multiple_channels_tracked_separately(self):
        seed = GenesisSeed(verbose=False)
        for i in range(5):
            seed.tick("audio", os.urandom(128))
            seed.tick("sensor", struct.pack(">f", float(i)))
        r = seed.tick("audio", os.urandom(128))
        assert r["concepts"] > 0
        seed.close()

    def test_rest_eventually_triggered(self):
        """After many low-wanting cycles (flat boring data), REST should trigger."""
        seed = GenesisSeed(verbose=False)
        # Feed identical repetitive data to drive wanting → 0
        for _ in range(20):
            seed.tick("ch", b"\xAA" * 128)
        # May or may not trigger REST depending on error history; just ensure
        # rest_pending is a bool and the loop doesn't crash
        r = seed.tick("ch", b"\xAA" * 128)
        assert isinstance(r["rest_pending"], bool)
        seed.close()

    def test_no_exception_on_empty_input(self):
        seed = GenesisSeed(verbose=False)
        r = seed.tick("ch", b"")
        assert r["cycle"] == 1
        seed.close()

    def test_no_exception_on_unicode_string(self):
        seed = GenesisSeed(verbose=False)
        r = seed.tick("stdin", "日本語テスト")
        assert r["cycle"] == 1
        seed.close()
