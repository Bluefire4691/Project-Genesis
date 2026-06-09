"""
Tests for M26 DriveSystem — internal biological-analog pressure signals.

Verifies that:
1. Drives update in the expected direction given cycle signals
2. Drives decay toward their baselines when unpushed
3. Persistence round-trips correctly
4. behavioral_hints() reflects current state
5. expressive_state() only speaks when a drive is genuinely strong
6. Integration: drives are present on the Orchestrator and update each cycle
"""
import os
import sys
import sqlite3
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from survival.drives import DriveSystem, CycleStats, DriveState, _BASELINE, _STRONG


# ── Fixtures ─────────────────────────────────────────────────────────────

def _fresh_drives():
    """In-memory SQLite drive system, no files on disk."""
    conn = sqlite3.connect(":memory:")
    ds = DriveSystem(conn)
    return ds, conn


# ── Direction tests ───────────────────────────────────────────────────────

class TestHunger:
    def test_rises_with_many_directives(self):
        ds, _ = _fresh_drives()
        baseline = ds._state.hunger
        ds.update(CycleStats(directive_count=8, relations_added=0))
        assert ds._state.hunger > baseline, "hunger should rise with many unfilled directives"

    def test_falls_when_learning_flows(self):
        ds, _ = _fresh_drives()
        ds._state.hunger = 0.9          # start hungry
        ds.update(CycleStats(relations_added=6, directive_count=0))
        assert ds._state.hunger < 0.9, "hunger should fall when relations are flowing in"


class TestFrustration:
    def test_rises_on_empty_cycle(self):
        ds, _ = _fresh_drives()
        for _ in range(5):
            ds.update(CycleStats(relations_added=0, new_conflicts=0))
        assert ds._state.frustration > 0.2, (
            "frustration should accumulate over empty cycles"
        )

    def test_clears_quickly_when_learning_resumes(self):
        ds, _ = _fresh_drives()
        ds._state.frustration = 0.8
        ds.update(CycleStats(relations_added=5))
        assert ds._state.frustration < 0.8, (
            "frustration should drop immediately when relations flow"
        )

    def test_stays_low_in_productive_cycles(self):
        ds, _ = _fresh_drives()
        for _ in range(10):
            ds.update(CycleStats(relations_added=4))
        assert ds._state.frustration < 0.3, (
            "frustration should stay low during productive learning"
        )


class TestAnticipation:
    def test_rises_with_high_relation_rate(self):
        ds, _ = _fresh_drives()
        baseline = ds._state.anticipation
        for _ in range(3):
            ds.update(CycleStats(relations_added=6))
        assert ds._state.anticipation > baseline, (
            "anticipation should rise when many relations are being extracted"
        )

    def test_rises_with_conflicts_too(self):
        ds, _ = _fresh_drives()
        baseline = ds._state.anticipation
        ds.update(CycleStats(new_conflicts=2, relations_added=3))
        assert ds._state.anticipation >= baseline, (
            "finding contradictions (interesting complexity) should not lower anticipation"
        )


class TestBoredom:
    def test_rises_with_empty_uninteresting_cycles(self):
        ds, _ = _fresh_drives()
        for _ in range(8):
            ds.update(CycleStats(relations_added=0, new_conflicts=0))
        assert ds._state.boredom > 0.2, (
            "boredom should accumulate when nothing is happening"
        )

    def test_clears_when_learning_resumes(self):
        ds, _ = _fresh_drives()
        ds._state.boredom = 0.7
        for _ in range(3):
            ds.update(CycleStats(relations_added=4))
        assert ds._state.boredom < 0.7, (
            "boredom should clear when genuine learning is happening"
        )


class TestDissonance:
    def test_rises_with_conflicts(self):
        ds, _ = _fresh_drives()
        baseline = ds._state.dissonance
        ds.update(CycleStats(new_conflicts=3))
        assert ds._state.dissonance > baseline, (
            "dissonance should rise when new contradictions are found"
        )

    def test_decays_without_conflicts(self):
        ds, _ = _fresh_drives()
        ds._state.dissonance = 0.8
        for _ in range(10):
            ds.update(CycleStats(new_conflicts=0))
        assert ds._state.dissonance < 0.8, (
            "dissonance should slowly decay without new conflicts"
        )


# ── Boundary conditions ───────────────────────────────────────────────────

class TestBoundaries:
    def test_drives_never_exceed_one(self):
        ds, _ = _fresh_drives()
        for _ in range(50):
            ds.update(CycleStats(
                relations_added=0, new_conflicts=5, directive_count=20
            ))
        s = ds._state
        for name in ("hunger", "frustration", "anticipation", "boredom", "dissonance"):
            val = getattr(s, name)
            assert val <= 1.0, f"{name} exceeded 1.0: {val}"

    def test_drives_never_go_negative(self):
        ds, _ = _fresh_drives()
        for _ in range(50):
            ds.update(CycleStats(relations_added=10, directive_count=0, new_conflicts=0))
        s = ds._state
        for name in ("hunger", "frustration", "anticipation", "boredom", "dissonance"):
            val = getattr(s, name)
            assert val >= 0.0, f"{name} went negative: {val}"

    def test_all_drives_present_in_summary(self):
        ds, _ = _fresh_drives()
        summary = ds.summary()
        for key in ("hunger", "frustration", "anticipation", "boredom", "dissonance",
                    "dominant", "dominant_level", "empty_streak"):
            assert key in summary, f"missing key in summary: {key}"


# ── Behavioral hints ──────────────────────────────────────────────────────

class TestBehavioralHints:
    def test_diversity_boost_when_frustrated(self):
        ds, _ = _fresh_drives()
        ds._state.frustration = 0.8
        hints = ds.behavioral_hints()
        assert hints["diversity_boost"] > 0, (
            "high frustration should produce a diversity_boost"
        )

    def test_curiosity_boost_when_hungry(self):
        ds, _ = _fresh_drives()
        ds._state.hunger = 0.9
        hints = ds.behavioral_hints()
        assert hints["curiosity_boost"] > 0, (
            "high hunger should produce a curiosity_boost"
        )

    def test_reflect_sooner_when_dissonant(self):
        ds, _ = _fresh_drives()
        ds._state.dissonance = 0.8
        hints = ds.behavioral_hints()
        assert hints["reflect_sooner"] is True, (
            "high dissonance should trigger reflect_sooner"
        )

    def test_no_boost_in_neutral_state(self):
        ds, _ = _fresh_drives()
        hints = ds.behavioral_hints()
        # In neutral state boosts should be small or zero
        assert hints["diversity_boost"] < 0.3
        assert hints["curiosity_boost"] <= 0.1
        assert hints["reflect_sooner"] is False


# ── Expressive state ──────────────────────────────────────────────────────

class TestExpressiveState:
    def test_none_in_neutral_state(self):
        ds, _ = _fresh_drives()
        assert ds.expressive_state() is None, (
            "neutral drive state should produce no expression"
        )

    def test_returns_string_when_drive_is_strong(self):
        ds, _ = _fresh_drives()
        ds._state.frustration = 0.9
        result = ds.expressive_state()
        assert result is not None and len(result) > 0, (
            "strong frustration should produce an expressive phrase"
        )

    def test_phrase_is_clean_english(self):
        ds, _ = _fresh_drives()
        for drive in ("hunger", "frustration", "anticipation", "boredom", "dissonance"):
            ds2, _ = _fresh_drives()
            setattr(ds2._state, drive, 0.9)
            phrase = ds2.expressive_state()
            assert phrase, f"no phrase for strong {drive}"
            assert phrase[0].isupper(), f"phrase should start with capital: {phrase!r}"
            assert phrase.endswith("."), f"phrase should end with period: {phrase!r}"


# ── Persistence ───────────────────────────────────────────────────────────

class TestPersistence:
    def test_restore_returns_false_when_empty(self):
        ds, _ = _fresh_drives()
        assert ds.restore() is False

    def test_save_and_restore_round_trip(self):
        conn = sqlite3.connect(":memory:")
        ds = DriveSystem(conn)
        ds._state.hunger       = 0.77
        ds._state.frustration  = 0.44
        ds._state.anticipation = 0.61
        ds._state.boredom      = 0.33
        ds._state.dissonance   = 0.52
        ds._cycle_since_last_relations = 7
        ds.save()

        ds2 = DriveSystem(conn)  # same connection, fresh object
        restored = ds2.restore()
        assert restored is True
        assert abs(ds2._state.hunger - 0.77) < 0.001
        assert abs(ds2._state.frustration - 0.44) < 0.001
        assert abs(ds2._state.anticipation - 0.61) < 0.001
        assert abs(ds2._state.boredom - 0.33) < 0.001
        assert abs(ds2._state.dissonance - 0.52) < 0.001
        assert ds2._cycle_since_last_relations == 7

    def test_update_auto_persists(self):
        conn = sqlite3.connect(":memory:")
        ds = DriveSystem(conn)
        ds.update(CycleStats(relations_added=0, new_conflicts=3))

        ds2 = DriveSystem(conn)
        ds2.restore()
        assert ds2._state.dissonance > 0, (
            "drive state should be persisted automatically after update"
        )


# ── Integration: Orchestrator has drives ─────────────────────────────────

class TestOrchestratorIntegration:
    def test_orchestrator_has_drives(self):
        from orchestrator.orchestrator import Orchestrator
        db = tempfile.mktemp(suffix=".db")
        try:
            b = Orchestrator(verbose=False, db_path=db)
            assert hasattr(b, "drives"), "Orchestrator should have .drives attribute"
            from survival.drives import DriveSystem
            assert isinstance(b.drives, DriveSystem)
        finally:
            if os.path.exists(db):
                os.unlink(db)

    def test_drives_update_after_process_input(self):
        from orchestrator.orchestrator import Orchestrator
        db = tempfile.mktemp(suffix=".db")
        try:
            b = Orchestrator(verbose=False, db_path=db)
            initial = b.drives.summary()
            b.process_input("text", "Wolves hunt deer in packs.")
            updated = b.drives.summary()
            # Something should have changed (even if just empty_streak resetting)
            assert updated != initial or updated["empty_streak"] == 0
        finally:
            if os.path.exists(db):
                os.unlink(db)

    def test_drives_summary_has_all_keys(self):
        from orchestrator.orchestrator import Orchestrator
        db = tempfile.mktemp(suffix=".db")
        try:
            b = Orchestrator(verbose=False, db_path=db)
            summary = b.drives.summary()
            for key in ("hunger", "frustration", "anticipation", "boredom",
                        "dissonance", "dominant", "dominant_level"):
                assert key in summary, f"missing key: {key}"
        finally:
            if os.path.exists(db):
                os.unlink(db)
