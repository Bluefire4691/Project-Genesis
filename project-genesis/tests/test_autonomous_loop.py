"""Tests for M20: AutonomousLoop."""
import os, sys, tempfile, time
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from cognition.autonomous_loop import AutonomousLoop


def _brain(db=None):
    from orchestrator.orchestrator import Orchestrator
    return Orchestrator(verbose=False, db_path=db or tempfile.mktemp(suffix=".db"))


class TestLifecycle:
    def test_not_running_before_start(self):
        b = _brain(); al = AutonomousLoop(b)
        assert not al.is_running
        os.unlink(b.memory._long_term._db_path)

    def test_running_after_start(self):
        b = _brain(); al = AutonomousLoop(b)
        al.start()
        time.sleep(0.05)
        assert al.is_running
        al.stop()
        os.unlink(b.memory._long_term._db_path)

    def test_not_running_after_stop(self):
        b = _brain(); al = AutonomousLoop(b)
        al.start(); al.stop()
        assert not al.is_running
        os.unlink(b.memory._long_term._db_path)

    def test_double_start_safe(self):
        b = _brain(); al = AutonomousLoop(b)
        al.start(); al.start()
        assert al.is_running
        al.stop()
        os.unlink(b.memory._long_term._db_path)

    def test_session_id_is_auto_prefixed(self):
        b = _brain(); al = AutonomousLoop(b)
        assert al.session_id.startswith("auto-")
        os.unlink(b.memory._long_term._db_path)


class TestTickOnce:
    def test_tick_once_returns_bool(self):
        b = _brain(); al = AutonomousLoop(b)
        result = al.tick_once()
        assert isinstance(result, bool)
        os.unlink(b.memory._long_term._db_path)

    def test_tick_once_increments_count(self):
        b = _brain(); al = AutonomousLoop(b)
        al.tick_once(); al.tick_once()
        assert al._tick_count == 2
        os.unlink(b.memory._long_term._db_path)

    def test_tick_once_logs_activity(self):
        b = _brain(); al = AutonomousLoop(b)
        al.tick_once()
        log = al.activity_log()
        assert len(log) >= 1
        os.unlink(b.memory._long_term._db_path)

    def test_tick_with_directive_runs_curiosity_action(self):
        b = _brain()
        b._curiosity_directives = {"wolves": 0.9}
        al = AutonomousLoop(b)
        al.tick_once()
        log = al.activity_log()
        action_types = [a["type"] for e in log for a in e.get("actions", [])]
        assert "curiosity" in action_types
        os.unlink(b.memory._long_term._db_path)

    def test_tick_reflect_runs_every_n_ticks(self):
        b = _brain(); al = AutonomousLoop(b, reflect_every=3)
        for _ in range(3):
            al.tick_once()
        log = al.activity_log()
        action_types = [a["type"] for e in log for a in e.get("actions", [])]
        assert "reflection" in action_types
        os.unlink(b.memory._long_term._db_path)

    def test_tick_error_does_not_crash_loop(self):
        b = _brain(); al = AutonomousLoop(b)
        # Corrupt directives to trigger an error path
        b._curiosity_directives = None  # type: ignore
        al.tick_once()  # must not raise
        b._curiosity_directives = {}
        os.unlink(b.memory._long_term._db_path)


class TestStatus:
    def test_status_has_required_keys(self):
        b = _brain(); al = AutonomousLoop(b)
        s = al.status()
        for key in ("running", "session_id", "tick_count",
                    "total_fetched", "total_revised", "total_reflects"):
            assert key in s
        os.unlink(b.memory._long_term._db_path)

    def test_last_active_at_none_before_ticks(self):
        b = _brain(); al = AutonomousLoop(b)
        assert al.last_active_at() is None
        os.unlink(b.memory._long_term._db_path)


class TestOrchestratorIntegration:
    def test_orchestrator_has_autonomous(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db = f.name
        try:
            from orchestrator.orchestrator import Orchestrator
            o = Orchestrator(verbose=False, db_path=db)
            assert hasattr(o, "autonomous")
            assert isinstance(o.autonomous, AutonomousLoop)
        finally:
            os.unlink(db)

    def test_start_stop_autonomous_methods(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db = f.name
        try:
            from orchestrator.orchestrator import Orchestrator
            o = Orchestrator(verbose=False, db_path=db)
            o.start_autonomous(tick_interval=60.0)
            time.sleep(0.05)
            assert o.autonomous.is_running
            o.stop_autonomous()
            assert not o.autonomous.is_running
        finally:
            os.unlink(db)
