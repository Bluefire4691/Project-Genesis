"""Tests for the curriculum engine."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from curriculum.curriculum import CurriculumEngine
from utils.types import Stage, ProcessorOutput


def test_starts_at_foundation():
    c = CurriculumEngine()
    assert c.current_stage == Stage.FOUNDATION


def test_has_curriculum_for_all_stages():
    c = CurriculumEngine()
    for stage in Stage:
        c.current_stage = stage
        items = c.get_curriculum()
        assert len(items) > 0, f"No curriculum for {stage.name}"


def test_advancement_requires_threshold():
    c = CurriculumEngine(advancement_threshold=0.6, min_items=3)
    # Feed low scores — should not advance
    for _ in range(5):
        c.record_score(0.3)
    assert not c.should_advance()


def test_advancement_on_good_scores():
    c = CurriculumEngine(advancement_threshold=0.6, min_items=3)
    for _ in range(5):
        c.record_score(0.8)
    assert c.should_advance()
    assert c.advance()
    assert c.current_stage == Stage.RELATIONS


def test_cannot_advance_past_open():
    c = CurriculumEngine()
    c.current_stage = Stage.OPEN
    assert not c.should_advance()
    assert not c.advance()


def test_status_reporting():
    c = CurriculumEngine()
    status = c.status()
    assert "current_stage" in status
    assert "score" in status
    assert "ready_to_advance" in status


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            print(f"  ✅ {test.__name__}")
            passed += 1
        except Exception as e:
            print(f"  ❌ {test.__name__}: {e}")
            failed += 1
    print(f"\n  {passed} passed, {failed} failed")
