"""Tests for SessionManager — save, restore, and warm-start."""

import sys, os, sqlite3
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from persistence.session import SessionManager
from orchestrator.orchestrator import Orchestrator
from utils.types import Stage


def _manager() -> SessionManager:
    """Fresh in-memory SessionManager."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return SessionManager(conn)


def _brain() -> Orchestrator:
    return Orchestrator(verbose=False)


# ==================================================================
# has_state
# ==================================================================

def test_has_state_false_initially():
    m = _manager()
    assert m.has_state() is False


def test_has_state_true_after_save():
    brain = _brain()
    m = _manager()
    m.save(brain)
    assert m.has_state() is True


# ==================================================================
# save / restore — cycle count
# ==================================================================

def test_restore_cycle_count():
    brain = _brain()
    brain.cycle_count = 42
    m = _manager()
    m.save(brain)

    brain2 = _brain()
    m.restore(brain2)
    assert brain2.cycle_count == 42


def test_restore_zero_cycle_count():
    brain = _brain()
    brain.cycle_count = 0
    m = _manager()
    m.save(brain)

    brain2 = _brain()
    brain2.cycle_count = 99  # pre-existing
    m.restore(brain2)
    assert brain2.cycle_count == 0


def test_restore_large_cycle_count():
    brain = _brain()
    brain.cycle_count = 100_000
    m = _manager()
    m.save(brain)

    brain2 = _brain()
    m.restore(brain2)
    assert brain2.cycle_count == 100_000


# ==================================================================
# save / restore — curriculum stage
# ==================================================================

def test_restore_foundation_stage():
    brain = _brain()
    brain.curriculum.current_stage = Stage.FOUNDATION
    m = _manager()
    m.save(brain)

    brain2 = _brain()
    m.restore(brain2)
    assert brain2.curriculum.current_stage == Stage.FOUNDATION


def test_restore_open_stage():
    brain = _brain()
    brain.curriculum.current_stage = Stage.OPEN
    m = _manager()
    m.save(brain)

    brain2 = _brain()
    m.restore(brain2)
    assert brain2.curriculum.current_stage == Stage.OPEN


def test_restore_relations_stage():
    brain = _brain()
    brain.curriculum.current_stage = Stage.RELATIONS
    m = _manager()
    m.save(brain)

    brain2 = _brain()
    m.restore(brain2)
    assert brain2.curriculum.current_stage == Stage.RELATIONS


# ==================================================================
# save / restore — working memory warm-start
# ==================================================================

def test_restore_warm_starts_working_memory():
    """Memories stored in brain1 should appear in brain2 after restore."""
    brain = _brain()
    brain.memory.store("key:wolf", "Wolves shape river banks", "ecology", "text", 0.9)
    brain.memory.store("key:deer", "Deer overgraze without wolves", "ecology", "text", 0.7)

    m = _manager()
    m.save(brain)

    # brain2 shares the same SQLite DB
    brain2 = Orchestrator(verbose=False, db_path=brain.memory._long_term._db_path)
    m2 = SessionManager(brain2.memory._long_term.conn)
    m2.save(brain)  # save from brain into m2 (same schema, different manager instance)

    brain3 = Orchestrator(verbose=False, db_path=brain.memory._long_term._db_path)
    m2.restore(brain3)
    # warm-started keys should be in working memory
    wm = brain3.memory.memories
    assert len(wm) > 0


def test_restore_returns_true_when_state_found():
    brain = _brain()
    m = _manager()
    m.save(brain)
    brain2 = _brain()
    result = m.restore(brain2)
    assert result is True


def test_restore_returns_false_when_no_state():
    m = _manager()
    brain = _brain()
    result = m.restore(brain)
    assert result is False


# ==================================================================
# saved_at
# ==================================================================

def test_saved_at_none_before_save():
    m = _manager()
    assert m.saved_at() is None


def test_saved_at_float_after_save():
    brain = _brain()
    m = _manager()
    m.save(brain)
    ts = m.saved_at()
    assert ts is not None
    assert isinstance(ts, float)
    assert ts > 0


# ==================================================================
# clear
# ==================================================================

def test_clear_removes_state():
    brain = _brain()
    m = _manager()
    m.save(brain)
    m.clear()
    assert m.has_state() is False


def test_clear_then_restore_returns_false():
    brain = _brain()
    m = _manager()
    m.save(brain)
    m.clear()
    brain2 = _brain()
    result = m.restore(brain2)
    assert result is False


# ==================================================================
# Multiple saves — last write wins
# ==================================================================

def test_multiple_saves_last_wins():
    brain = _brain()
    m = _manager()

    brain.cycle_count = 10
    m.save(brain)

    brain.cycle_count = 99
    m.save(brain)

    brain2 = _brain()
    m.restore(brain2)
    assert brain2.cycle_count == 99


# ==================================================================
# Orchestrator integration — resume=True via shared DB
# ==================================================================

def test_orchestrator_save_session_method_exists():
    brain = _brain()
    assert hasattr(brain, "save_session")
    # Should not raise
    brain.save_session()


def test_orchestrator_has_session_id():
    brain = _brain()
    assert hasattr(brain, "session_id")
    assert len(brain.session_id) > 0


def test_orchestrator_has_archive():
    brain = _brain()
    assert hasattr(brain, "archive")
    stats = brain.archive.stats()
    assert "total_tagged" in stats


def test_orchestrator_archive_tags_on_process():
    """Processing input should auto-tag memories in the archive."""
    brain = _brain()
    brain.curriculum.current_stage = Stage.OPEN
    brain.process_input("text", "Wolves were reintroduced to Yellowstone in 1995.")
    stats = brain.archive.stats()
    assert stats["total_tagged"] > 0


def test_orchestrator_archive_query_after_process():
    brain = _brain()
    brain.curriculum.current_stage = Stage.OPEN
    brain.process_input("text", "Ant colonies self-organize without central control.")
    results = brain.archive.query(domain="language")
    assert len(results) > 0


# ==================================================================
# Runner
# ==================================================================

if __name__ == "__main__":
    import traceback
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for t in tests:
        try:
            t()
            print(f"  ✅ {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  ❌ {t.__name__}: {e}")
            traceback.print_exc()
            failed += 1
    print(f"\n  {passed} passed, {failed} failed")
