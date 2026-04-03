"""Tests for rich PatternProcessor — all structural detection methods."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from processors.pattern import (
    PatternProcessor,
    _detect_arithmetic, _detect_geometric, _detect_fibonacci,
    _detect_power, _detect_periodic, _detect_repeating,
    _detect_anomalies, _detect_trend, _statistical_profile, _ngram_freq,
)


P = PatternProcessor()


# ==================================================================
# Arithmetic progression
# ==================================================================

def test_arithmetic_clean():
    conf, desc = _detect_arithmetic([2, 4, 6, 8, 10])
    assert conf > 0.9
    assert "arithmetic" in desc

def test_arithmetic_negative_step():
    conf, desc = _detect_arithmetic([10, 7, 4, 1, -2])
    assert conf > 0.9

def test_arithmetic_noise_rejects():
    conf, _ = _detect_arithmetic([1, 2, 5, 7, 100])
    assert conf < 0.5

def test_arithmetic_too_short():
    conf, _ = _detect_arithmetic([1, 2])
    assert conf == 0.0


# ==================================================================
# Geometric progression
# ==================================================================

def test_geometric_clean():
    conf, desc = _detect_geometric([2, 4, 8, 16, 32])
    assert conf > 0.9
    assert "geometric" in desc

def test_geometric_ratio_3():
    conf, desc = _detect_geometric([1, 3, 9, 27, 81])
    assert conf > 0.9

def test_geometric_with_zero_rejects():
    conf, _ = _detect_geometric([0, 2, 4, 8])
    assert conf == 0.0

def test_geometric_noise_rejects():
    conf, _ = _detect_geometric([1, 2, 5, 7, 11])
    assert conf < 0.5


# ==================================================================
# Fibonacci-like
# ==================================================================

def test_fibonacci_standard():
    conf, desc = _detect_fibonacci([1, 1, 2, 3, 5, 8, 13, 21])
    assert conf > 0.8
    assert "fibonacci" in desc

def test_fibonacci_scaled():
    conf, desc = _detect_fibonacci([2, 2, 4, 6, 10, 16, 26])
    assert conf > 0.7

def test_fibonacci_too_short_rejects():
    conf, _ = _detect_fibonacci([1, 1, 2])
    assert conf == 0.0

def test_fibonacci_random_rejects():
    conf, _ = _detect_fibonacci([1, 5, 3, 9, 2, 8, 6, 4])
    assert conf < 0.4


# ==================================================================
# Power sequences
# ==================================================================

def test_power_squares():
    conf, desc = _detect_power([1, 4, 9, 16, 25, 36])
    assert conf > 0.8
    assert "n^2" in desc

def test_power_cubes():
    conf, desc = _detect_power([1, 8, 27, 64, 125])
    assert conf > 0.8
    assert "n^3" in desc

def test_power_random_rejects():
    conf, _ = _detect_power([1, 3, 7, 12, 20])
    assert conf == 0.0


# ==================================================================
# Periodic
# ==================================================================

def test_periodic_detected():
    seq = [1, 2, 3, 1, 2, 3, 1, 2, 3]
    conf, period = _detect_periodic(seq)
    assert conf > 0.7
    assert period == 3

def test_periodic_binary():
    seq = [0, 1, 0, 1, 0, 1, 0, 1]
    conf, period = _detect_periodic(seq)
    assert conf > 0.7

def test_periodic_too_short():
    conf, period = _detect_periodic([1, 2, 3])
    assert conf == 0.0 or period == 0


# ==================================================================
# Repeating subsequence (exact)
# ==================================================================

def test_repeating_numeric():
    found, period = _detect_repeating([1, 2, 1, 2, 1, 2])
    assert found
    assert period == 2

def test_repeating_symbolic():
    found, period = _detect_repeating(["a", "b", "c", "a", "b", "c"])
    assert found
    assert period == 3

def test_repeating_single_element():
    found, period = _detect_repeating([5, 5, 5, 5])
    assert found
    assert period == 1

def test_repeating_not_found():
    found, _ = _detect_repeating([1, 2, 3, 4, 5, 6])
    assert not found


# ==================================================================
# Anomaly detection
# ==================================================================

def test_anomaly_spike():
    anomalies = _detect_anomalies([10, 11, 10, 12, 10, 100, 11, 10])
    assert 100 in anomalies

def test_anomaly_none():
    anomalies = _detect_anomalies([10, 11, 12, 11, 10, 11, 12])
    assert anomalies == []

def test_anomaly_constant():
    # Constant sequence: std=0, no anomalies
    anomalies = _detect_anomalies([5, 5, 5, 5, 5])
    assert anomalies == []


# ==================================================================
# Trend detection
# ==================================================================

def test_trend_strictly_increasing():
    assert _detect_trend([1, 2, 3, 4, 5]) == "strictly_increasing"

def test_trend_strictly_decreasing():
    assert _detect_trend([5, 4, 3, 2, 1]) == "strictly_decreasing"

def test_trend_constant():
    assert _detect_trend([3, 3, 3, 3]) == "constant"

def test_trend_oscillating():
    assert _detect_trend([1, 3, 1, 3, 1, 3]) == "oscillating"

def test_trend_generally_increasing():
    t = _detect_trend([1, 2, 3, 2, 4, 5, 6, 7])
    assert t in ("generally_increasing", "variable")

def test_trend_single_element():
    assert _detect_trend([42]) == "insufficient_data"


# ==================================================================
# Statistical profile
# ==================================================================

def test_stats_mean():
    s = _statistical_profile([2, 4, 6])
    assert abs(s["mean"] - 4.0) < 0.001

def test_stats_std():
    s = _statistical_profile([0, 0, 0, 0])
    assert s["std"] == 0.0

def test_stats_range():
    s = _statistical_profile([1, 5, 3])
    assert s["range"] == 4.0

def test_stats_trend_slope_positive():
    s = _statistical_profile([1, 2, 3, 4, 5])
    assert s["trend_slope"] > 0

def test_stats_trend_slope_negative():
    s = _statistical_profile([5, 4, 3, 2, 1])
    assert s["trend_slope"] < 0

def test_stats_empty():
    s = _statistical_profile([])
    assert s == {}


# ==================================================================
# N-gram frequency
# ==================================================================

def test_ngram_bigram():
    ng = _ngram_freq([1, 2, 1, 2, 1, 2])
    assert len(ng) > 0

def test_ngram_symbolic():
    ng = _ngram_freq(["a", "b", "a", "b"])
    assert len(ng) > 0

def test_ngram_too_short():
    ng = _ngram_freq([1], n=2)
    assert ng == {}


# ==================================================================
# Full processor integration
# ==================================================================

def test_processor_arithmetic_output():
    result = P.process({"label": "even", "sequence": [2, 4, 6, 8, 10]})
    patterns = result.extracted["patterns"]
    assert any("arithmetic" in p for p in patterns)

def test_processor_fibonacci_output():
    result = P.process({"label": "fib", "sequence": [1, 1, 2, 3, 5, 8, 13, 21]})
    patterns = result.extracted["patterns"]
    assert any("fibonacci" in p for p in patterns)

def test_processor_geometric_output():
    result = P.process({"label": "powers_of_2", "sequence": [1, 2, 4, 8, 16, 32]})
    patterns = result.extracted["patterns"]
    assert any("geometric" in p for p in patterns)

def test_processor_includes_stats():
    result = P.process({"label": "nums", "sequence": [1, 2, 3, 4, 5]})
    assert "stats" in result.extracted
    assert "mean" in result.extracted["stats"]

def test_processor_includes_trend():
    result = P.process({"label": "inc", "sequence": [1, 2, 3, 4, 5]})
    assert result.extracted["trend"] == "strictly_increasing"

def test_processor_symbolic_sequence():
    result = P.process({"label": "sym", "sequence": ["a", "b", "c", "a", "b", "c"]})
    assert result.source == "pattern"
    assert any("repeating" in p for p in result.extracted["patterns"])

def test_processor_empty_sequence():
    result = P.process({"label": "empty", "sequence": []})
    assert result.source == "pattern"
    assert result.extracted["sequence_length"] == 0

def test_processor_anomaly_raises_confidence():
    # No-pattern baseline: random-ish values, no repeating structure
    baseline = P.process({"label": "baseline", "sequence": [10, 13, 11, 9, 12, 14, 10, 11]})
    # Same range but with a huge outlier — anomaly should push importance above baseline
    spiked = P.process({"label": "spike", "sequence": [10, 13, 11, 9, 12, 14, 10, 999]})
    assert spiked.importance >= baseline.importance

def test_processor_never_crashes_string_input():
    result = P.process("just a string")
    assert result.source == "pattern"

def test_processor_never_crashes_none():
    result = P.process(None)
    assert result.source == "pattern"

def test_processor_squares_detected():
    result = P.process({"label": "squares", "sequence": [1, 4, 9, 16, 25, 36]})
    patterns = result.extracted["patterns"]
    assert any("n^2" in p for p in patterns)


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
