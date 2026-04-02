"""Tests for sensory processors — they must never crash."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from processors import TextProcessor, NumericProcessor, PatternProcessor


def test_text_processor_basic():
    p = TextProcessor()
    result = p.process("A dog is a friendly animal")
    assert result.source == "text"
    assert "animal" in result.extracted["categories"]
    assert result.importance > 0


def test_text_processor_sentiment():
    p = TextProcessor()
    pos = p.process("This is a wonderful beautiful day")
    neg = p.process("This is a terrible horrible situation")
    assert pos.extracted["sentiment"] == "positive"
    assert neg.extracted["sentiment"] == "negative"


def test_text_processor_never_crashes():
    """Processor must handle any input without raising."""
    p = TextProcessor()
    # Empty string
    result = p.process("")
    assert result.source == "text"
    # None (coerced to string)
    result = p.process(None)
    assert result.source == "text"
    # Number
    result = p.process(42)
    assert result.source == "text"
    # Nested dict
    result = p.process({"weird": [1, 2, 3]})
    assert result.source == "text"


def test_numeric_processor_single():
    p = NumericProcessor()
    result = p.process({"label": "temperature", "value": 72, "unit": "F"})
    assert result.extracted["label"] == "temperature"
    assert result.extracted["value"] == 72


def test_numeric_processor_trend():
    p = NumericProcessor()
    result = p.process({"label": "growth", "values": [1, 3, 5, 8, 12]})
    assert result.extracted["trend"] == "increasing"


def test_numeric_processor_never_crashes():
    p = NumericProcessor()
    # Bare number
    result = p.process(42)
    assert result.source == "numeric"
    # String that can't be a number — should hit BaseProcessor error handler
    result = p.process("not a number")
    assert result.source == "numeric"  # Error handler still returns processor name


def test_pattern_processor_repetition():
    p = PatternProcessor()
    result = p.process({"label": "test", "sequence": [1, 2, 1, 2, 1, 2]})
    assert any("repeating" in pat for pat in result.extracted["patterns"])


def test_pattern_processor_never_crashes():
    p = PatternProcessor()
    result = p.process({"label": "empty", "sequence": []})
    assert result.source == "pattern"
    result = p.process("just a string")
    assert result.source == "pattern"


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
