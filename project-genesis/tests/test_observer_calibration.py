"""
Tests for M14 — Observer Calibration.

ObserverCalibration derives Observer thresholds empirically from Genesis's own
behavioral history (archive entries, relation timestamps, reflection data) rather
than relying on hardcoded defaults.

Grounded in ACT-R utility learning (Anderson): each threshold is a production
rule whose utility is updated from observed outcomes. Calibration = updating
from archive data. Grounded in SOAR chunking (Newell/Laird): recurring patterns
compiled into lightweight rules.

The core invariant: if Genesis's typical relation-formation rate is X, then the
stagnation threshold should be proportional to X for THIS instance — not an
arbitrary constant chosen before any data exists.
"""

import json
import sqlite3
import sys
import os
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from interface.observer_calibration import (
    ObserverCalibration,
    CalibrationResult,
    _step_int,
    _step_float,
    _MIN_ARCHIVE_ENTRIES,
    _MIN_RELATIONS,
    _BOUNDS,
    _STATE_KEY,
)
from interface.observer import Observer
from orchestrator.orchestrator import Orchestrator


# ==================================================================
# Helpers
# ==================================================================

def _make_conn() -> sqlite3.Connection:
    """In-memory SQLite connection with the tables ObserverCalibration needs."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS archive_metadata (
            key TEXT PRIMARY KEY,
            session_id TEXT,
            significance REAL DEFAULT 0.5,
            domain_tags TEXT DEFAULT '[]',
            archived_at REAL NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS relations (
            rel_id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT,
            rel_type TEXT,
            object TEXT,
            confidence REAL DEFAULT 0.75,
            source_key TEXT,
            session_id TEXT,
            created_at REAL NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reflections (
            reflection_id INTEGER PRIMARY KEY AUTOINCREMENT,
            cycle INTEGER,
            created_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS consolidation_state (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    conn.commit()
    return conn


def _brain(**kwargs) -> Orchestrator:
    if "db_path" not in kwargs:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        kwargs["db_path"] = tmp.name
    return Orchestrator(verbose=False, **kwargs)


def _insert_archive_rows(conn, n: int, base_sig: float = 0.6) -> None:
    """Insert n archive rows spread over the last 300 seconds."""
    now = time.time()
    for i in range(n):
        t = now - (n - i) * (300.0 / max(n, 1))
        conn.execute(
            "INSERT OR IGNORE INTO archive_metadata (key, session_id, significance, archived_at) "
            "VALUES (?, 'test', ?, ?)",
            (f"key:{i}", base_sig, t),
        )
    conn.commit()


def _insert_relation_rows(conn, n: int) -> None:
    """Insert n relation rows spread over the last 600 seconds."""
    now = time.time()
    for i in range(n):
        t = now - (n - i) * (600.0 / max(n, 1))
        conn.execute(
            "INSERT INTO relations (subject, rel_type, object, confidence, created_at) "
            "VALUES (?, 'IS_A', ?, 0.8, ?)",
            (f"sub{i}", f"obj{i}", t),
        )
    conn.commit()


# ==================================================================
# Helper function tests
# ==================================================================

def test_step_int_moves_toward_target():
    assert _step_int(10, 14, 3) == 13   # capped by max_step
    assert _step_int(10, 12, 3) == 12   # reached target
    assert _step_int(10, 7, 3)  == 7    # downward, reached
    assert _step_int(10, 5, 3)  == 7    # downward, capped


def test_step_int_unchanged_at_target():
    assert _step_int(5, 5, 3) == 5


def test_step_float_moves_toward_target():
    result = _step_float(0.15, 0.30, 0.05)
    assert result == 0.20        # capped by max_step


def test_step_float_reaches_target():
    result = _step_float(0.15, 0.17, 0.05)
    assert result == 0.17


def test_step_float_unchanged_at_target():
    assert _step_float(0.20, 0.20, 0.05) == 0.20


def test_step_float_downward():
    result = _step_float(0.30, 0.10, 0.05)
    assert result == 0.25


# ==================================================================
# CalibrationResult dataclass
# ==================================================================

def test_calibration_result_defaults():
    r = CalibrationResult(
        thresholds={},
        rationale={},
        data_points=0,
        relation_count=0,
        confidence=0.0,
    )
    assert r.skipped is False
    assert r.skip_reason == ""


def test_calibration_result_skipped():
    r = CalibrationResult(
        thresholds={},
        rationale={},
        data_points=5,
        relation_count=2,
        confidence=0.0,
        skipped=True,
        skip_reason="not enough data",
    )
    assert r.skipped is True
    assert "not enough" in r.skip_reason


# ==================================================================
# Skips when below minimum data
# ==================================================================

def test_calibrate_skips_on_empty_db():
    conn = _make_conn()
    cal = ObserverCalibration(conn)
    observer = Observer()
    result = cal.calibrate(observer, 100)
    assert result.skipped is True
    assert result.data_points < _MIN_ARCHIVE_ENTRIES or result.relation_count < _MIN_RELATIONS


def test_calibrate_skips_with_only_relations():
    conn = _make_conn()
    _insert_relation_rows(conn, _MIN_RELATIONS + 5)
    cal = ObserverCalibration(conn)
    observer = Observer()
    result = cal.calibrate(observer, 100)
    # Still needs archive entries
    assert result.skipped is True


def test_calibrate_skips_with_only_archive():
    conn = _make_conn()
    _insert_archive_rows(conn, _MIN_ARCHIVE_ENTRIES + 10)
    cal = ObserverCalibration(conn)
    observer = Observer()
    result = cal.calibrate(observer, 100)
    # Still needs relations
    assert result.skipped is True


def test_calibrate_proceeds_with_sufficient_data():
    conn = _make_conn()
    _insert_archive_rows(conn, _MIN_ARCHIVE_ENTRIES + 20)
    _insert_relation_rows(conn, _MIN_RELATIONS + 10)
    cal = ObserverCalibration(conn)
    observer = Observer()
    result = cal.calibrate(observer, 200)
    assert result.skipped is False
    assert result.data_points >= _MIN_ARCHIVE_ENTRIES
    assert result.relation_count >= _MIN_RELATIONS


# ==================================================================
# Output structure
# ==================================================================

def test_calibrate_returns_calibration_result():
    conn = _make_conn()
    cal = ObserverCalibration(conn)
    observer = Observer()
    result = cal.calibrate(observer, 10)
    assert isinstance(result, CalibrationResult)


def test_calibrate_result_has_all_fields():
    conn = _make_conn()
    _insert_archive_rows(conn, _MIN_ARCHIVE_ENTRIES + 10)
    _insert_relation_rows(conn, _MIN_RELATIONS + 5)
    cal = ObserverCalibration(conn)
    observer = Observer()
    result = cal.calibrate(observer, 100)
    assert isinstance(result.thresholds, dict)
    assert isinstance(result.rationale, dict)
    assert isinstance(result.data_points, int)
    assert isinstance(result.relation_count, int)
    assert 0.0 <= result.confidence <= 1.0


def test_calibrate_thresholds_all_named():
    conn = _make_conn()
    _insert_archive_rows(conn, _MIN_ARCHIVE_ENTRIES + 20)
    _insert_relation_rows(conn, _MIN_RELATIONS + 15)
    cal = ObserverCalibration(conn)
    observer = Observer()
    result = cal.calibrate(observer, 300)
    if not result.skipped:
        expected = {
            "stagnation_no_associations_cycles",
            "stagnation_attention_freeze_cycles",
            "stagnation_min_new_memories",
            "danger_energy_floor",
            "commitment_cycles",
        }
        assert set(result.thresholds.keys()) == expected


# ==================================================================
# Threshold bounds
# ==================================================================

def test_calibrated_thresholds_within_bounds():
    conn = _make_conn()
    _insert_archive_rows(conn, _MIN_ARCHIVE_ENTRIES + 30)
    _insert_relation_rows(conn, _MIN_RELATIONS + 20)
    cal = ObserverCalibration(conn)
    observer = Observer()
    result = cal.calibrate(observer, 500)
    if not result.skipped:
        for name, value in result.thresholds.items():
            lo, hi = _BOUNDS.get(name, (0, 9999))
            assert lo <= value <= hi, (
                f"Threshold {name}={value} out of bounds [{lo}, {hi}]"
            )


def test_observer_thresholds_within_bounds_after_apply():
    conn = _make_conn()
    _insert_archive_rows(conn, _MIN_ARCHIVE_ENTRIES + 30)
    _insert_relation_rows(conn, _MIN_RELATIONS + 20)
    cal = ObserverCalibration(conn)
    observer = Observer()
    cal.calibrate(observer, 500)
    # Verify the Observer's actual attribute values stayed in bounds
    for attr, key in [
        ("_stagnation_no_associations_cycles", "stagnation_no_associations_cycles"),
        ("_stagnation_attention_freeze_cycles", "stagnation_attention_freeze_cycles"),
        ("_stagnation_min_new_memories",        "stagnation_min_new_memories"),
        ("_danger_energy_floor",                "danger_energy_floor"),
    ]:
        val = getattr(observer, attr)
        lo, hi = _BOUNDS[key]
        assert lo <= val <= hi, f"Observer.{attr}={val} out of bounds [{lo}, {hi}]"


# ==================================================================
# _apply sets Observer attributes
# ==================================================================

def test_apply_sets_observer_thresholds():
    conn = _make_conn()
    cal = ObserverCalibration(conn)
    observer = Observer()
    original = observer._stagnation_no_associations_cycles

    thresholds = {
        "stagnation_no_associations_cycles": original + 2,
        "stagnation_attention_freeze_cycles": 6,
        "stagnation_min_new_memories": 1,
        "danger_energy_floor": 0.18,
        "commitment_cycles": 7,
    }
    cal._apply(observer, thresholds)

    assert observer._stagnation_no_associations_cycles == original + 2
    assert observer._stagnation_attention_freeze_cycles == 6
    assert observer._stagnation_min_new_memories == 1
    assert observer._danger_energy_floor == 0.18
    assert observer.COMMITMENT_CYCLES == 7


def test_apply_clamps_out_of_bounds_values():
    conn = _make_conn()
    cal = ObserverCalibration(conn)
    observer = Observer()

    # Force out-of-bounds values
    cal._apply(observer, {
        "stagnation_no_associations_cycles": 9999,  # far above max=50
        "danger_energy_floor": -5.0,                # below min=0.05
    })

    lo_no_assoc, hi_no_assoc = _BOUNDS["stagnation_no_associations_cycles"]
    lo_energy, hi_energy = _BOUNDS["danger_energy_floor"]
    assert observer._stagnation_no_associations_cycles <= hi_no_assoc
    assert observer._danger_energy_floor >= lo_energy


# ==================================================================
# Persistence
# ==================================================================

def test_persist_writes_to_db():
    conn = _make_conn()
    cal = ObserverCalibration(conn)
    thresholds = {"stagnation_no_associations_cycles": 12}
    cal._persist(thresholds, confidence=0.5)

    row = conn.execute(
        "SELECT value FROM consolidation_state WHERE key=?", (_STATE_KEY,)
    ).fetchone()
    assert row is not None
    data = json.loads(row[0])
    assert data["thresholds"]["stagnation_no_associations_cycles"] == 12
    assert data["confidence"] == 0.5


def test_persist_overwrites_previous():
    conn = _make_conn()
    cal = ObserverCalibration(conn)
    cal._persist({"stagnation_no_associations_cycles": 10}, 0.3)
    cal._persist({"stagnation_no_associations_cycles": 15}, 0.6)

    row = conn.execute(
        "SELECT value FROM consolidation_state WHERE key=?", (_STATE_KEY,)
    ).fetchone()
    data = json.loads(row[0])
    assert data["thresholds"]["stagnation_no_associations_cycles"] == 15


# ==================================================================
# load_calibrated
# ==================================================================

def test_load_calibrated_returns_false_on_empty_db():
    conn = _make_conn()
    cal = ObserverCalibration(conn)
    observer = Observer()
    assert cal.load_calibrated(observer) is False


def test_load_calibrated_restores_thresholds():
    conn = _make_conn()
    cal = ObserverCalibration(conn)

    # Write a calibration record
    payload = json.dumps({
        "thresholds": {
            "stagnation_no_associations_cycles": 20,
            "danger_energy_floor": 0.25,
        },
        "confidence": 0.7,
        "calibrated_at": time.time(),
    })
    conn.execute(
        "INSERT INTO consolidation_state (key, value) VALUES (?, ?)",
        (_STATE_KEY, payload),
    )
    conn.commit()

    observer = Observer()
    result = cal.load_calibrated(observer)
    assert result is True
    assert observer._stagnation_no_associations_cycles == 20
    assert observer._danger_energy_floor == 0.25


def test_load_calibrated_handles_corrupt_data_gracefully():
    conn = _make_conn()
    conn.execute(
        "INSERT INTO consolidation_state (key, value) VALUES (?, ?)",
        (_STATE_KEY, "this is not JSON {{{"),
    )
    conn.commit()

    cal = ObserverCalibration(conn)
    observer = Observer()
    # Should not raise — graceful degradation
    result = cal.load_calibrated(observer)
    assert result is False


# ==================================================================
# Incremental adjustment (no thrashing)
# ==================================================================

def test_calibration_adjusts_incrementally():
    """
    Even if the computed target is far from current, each pass moves
    at most _MAX_STEP_CYCLES cycles.
    """
    from interface.observer_calibration import _MAX_STEP_CYCLES
    conn = _make_conn()
    _insert_archive_rows(conn, _MIN_ARCHIVE_ENTRIES + 40)
    _insert_relation_rows(conn, _MIN_RELATIONS + 30)
    cal = ObserverCalibration(conn)

    observer = Observer(stagnation_no_associations_cycles=10)
    original = observer._stagnation_no_associations_cycles

    result = cal.calibrate(observer, 1000)
    if not result.skipped:
        new_val = observer._stagnation_no_associations_cycles
        change = abs(new_val - original)
        assert change <= _MAX_STEP_CYCLES, (
            f"Single calibration pass moved threshold by {change}, max allowed={_MAX_STEP_CYCLES}"
        )


# ==================================================================
# Confidence scaling
# ==================================================================

def test_confidence_increases_with_more_data():
    conn = _make_conn()
    _insert_archive_rows(conn, _MIN_ARCHIVE_ENTRIES + 20)
    _insert_relation_rows(conn, _MIN_RELATIONS + 5)
    cal = ObserverCalibration(conn)
    observer = Observer()
    result = cal.calibrate(observer, 200)
    if not result.skipped:
        assert 0.0 < result.confidence <= 1.0


def test_confidence_at_500_entries_is_one():
    """500 archive entries → confidence asymptotes to 1.0."""
    conn = _make_conn()
    _insert_archive_rows(conn, 500)
    _insert_relation_rows(conn, _MIN_RELATIONS + 10)
    cal = ObserverCalibration(conn)
    observer = Observer()
    result = cal.calibrate(observer, 2000)
    if not result.skipped:
        assert result.confidence >= 0.99


# ==================================================================
# Integration: orchestrator.reflect() runs calibration
# ==================================================================

def test_reflect_does_not_crash_without_data():
    """reflect() with no behavioral data must not raise."""
    b = _brain()
    result = b.reflect()
    assert isinstance(result, dict)


def test_reflect_calibration_wired():
    """After reflect(), _calibration exists on the orchestrator."""
    b = _brain()
    assert hasattr(b, "_calibration")
    b.reflect()
    # No exception = M14 wiring works


def test_calibration_persists_across_orchestrator_sessions():
    """Calibration data written in session 1 is loaded in session 2."""
    db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db.close()

    b1 = Orchestrator(verbose=False, db_path=db.name)
    # Manually write calibration data via _calibration._persist
    b1._calibration._persist(
        {"stagnation_no_associations_cycles": 22, "danger_energy_floor": 0.20},
        confidence=0.8,
    )

    # New session on same DB
    b2 = Orchestrator(verbose=False, db_path=db.name)
    # The calibration should have been loaded into the Observer at startup
    assert b2.interaction._observer._stagnation_no_associations_cycles == 22
    assert b2.interaction._observer._danger_energy_floor == 0.20
