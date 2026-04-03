"""
Pattern sensory processor — rich structural detection.

Detects patterns, sequences, repetitions, and anomalies in ordered data.
Works on both numeric sequences (arithmetic, geometric, Fibonacci, power,
periodic) and categorical/symbolic sequences (n-gram, dominant elements).

Pattern detection returns ALL patterns found, ranked by confidence.
The processor never crashes — every failure returns a graceful result.
"""

from typing import Any

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from utils.types import ProcessorOutput
from processors.base import BaseProcessor


class PatternProcessor(BaseProcessor):
    name = "pattern"

    def _process(self, data: Any) -> ProcessorOutput:
        if not isinstance(data, dict):
            data = {"label": "unknown", "sequence": list(data) if hasattr(data, "__iter__") else []}

        label = data.get("label", "unknown")
        sequence = data.get("sequence", [])

        patterns_found = []
        confidence = 0.3

        is_numeric = (
            len(sequence) >= 2
            and all(isinstance(x, (int, float)) for x in sequence)
        )

        if is_numeric:
            stats = _statistical_profile(sequence)
            trend = _detect_trend(sequence)

            # Structural pattern detection — most specific first
            fib_conf, fib_desc = _detect_fibonacci(sequence)
            if fib_conf > 0.6:
                patterns_found.append(fib_desc)
                confidence = max(confidence, fib_conf)

            pow_conf, pow_desc = _detect_power(sequence)
            if pow_conf > 0.7:
                patterns_found.append(pow_desc)
                confidence = max(confidence, pow_conf)

            geo_conf, geo_desc = _detect_geometric(sequence)
            if geo_conf > 0.7:
                patterns_found.append(geo_desc)
                confidence = max(confidence, geo_conf)

            ari_conf, ari_desc = _detect_arithmetic(sequence)
            if ari_conf > 0.7:
                patterns_found.append(ari_desc)
                confidence = max(confidence, ari_conf)

            per_conf, per_period = _detect_periodic(sequence)
            if per_conf > 0.7:
                patterns_found.append(f"periodic (period={per_period}, conf={per_conf:.2f})")
                confidence = max(confidence, per_conf)

            # Repeating exact subsequence
            rep_found, rep_period = _detect_repeating(sequence)
            if rep_found:
                patterns_found.append(f"repeating (period {rep_period}): {sequence[:rep_period]}")
                confidence = max(confidence, 0.85)

            # Anomalies
            anomalies = _detect_anomalies(sequence)
            if anomalies:
                patterns_found.append(f"anomalies: {anomalies}")
                confidence = max(confidence, 0.65)

            # Sorted order
            if sequence == sorted(sequence):
                patterns_found.append("ascending order")
            elif sequence == sorted(sequence, reverse=True):
                patterns_found.append("descending order")

            # Always include trend and stats summary
            patterns_found.append(f"trend: {trend}")

            extracted = {
                "label": label,
                "sequence_length": len(sequence),
                "patterns": patterns_found,
                "stats": stats,
                "trend": trend,
            }
        else:
            # Symbolic / categorical sequence
            rep_found, rep_period = _detect_repeating(sequence)
            if rep_found:
                patterns_found.append(f"repeating (period {rep_period}): {sequence[:rep_period]}")
                confidence = 0.7

            if sequence == sorted(sequence, key=str):
                patterns_found.append("lexicographic order")

            if len(sequence) >= 2:
                ngrams = _ngram_freq(sequence, n=2)
                if ngrams:
                    top = max(ngrams, key=ngrams.get)
                    patterns_found.append(f"dominant bigram {top} ({ngrams[top]}x)")

            if not patterns_found:
                patterns_found.append("no clear structural pattern")

            extracted = {
                "label": label,
                "sequence_length": len(sequence),
                "patterns": patterns_found,
            }

        return ProcessorOutput(
            source=self.name,
            input_data=data,
            extracted=extracted,
            importance=confidence,
            suggested_key=f"pattern:{label.replace(' ', '_')}",
            context=(
                f"Pattern '{label}': {'; '.join(patterns_found[:3])}"
                f" (length: {len(sequence)})"
            ),
        )


# ==================================================================
# Numeric pattern detectors
# ==================================================================

def _detect_arithmetic(sequence: list) -> tuple[float, str]:
    """Detect arithmetic progression (constant difference)."""
    if len(sequence) < 3:
        return 0.0, ""
    diffs = [sequence[i + 1] - sequence[i] for i in range(len(sequence) - 1)]
    mean_diff = sum(diffs) / len(diffs)
    if mean_diff == 0:
        return 0.0, ""
    variance = sum((d - mean_diff) ** 2 for d in diffs) / len(diffs)
    std = variance ** 0.5
    cv = abs(std / mean_diff)
    conf = max(0.0, min(1.0, 1.0 - cv))
    if conf > 0.7:
        return conf, f"arithmetic progression (step={mean_diff:.4g})"
    return 0.0, ""


def _detect_geometric(sequence: list) -> tuple[float, str]:
    """Detect geometric progression (constant ratio)."""
    if len(sequence) < 3:
        return 0.0, ""
    if any(x == 0 for x in sequence):
        return 0.0, ""
    try:
        ratios = [sequence[i + 1] / sequence[i] for i in range(len(sequence) - 1)]
    except ZeroDivisionError:
        return 0.0, ""
    if any(r <= 0 for r in ratios):
        return 0.0, ""
    mean_ratio = sum(ratios) / len(ratios)
    variance = sum((r - mean_ratio) ** 2 for r in ratios) / len(ratios)
    std = variance ** 0.5
    cv = abs(std / mean_ratio) if mean_ratio != 0 else float("inf")
    conf = max(0.0, min(1.0, 1.0 - cv * 5))
    if conf > 0.7:
        return conf, f"geometric progression (ratio={mean_ratio:.4g})"
    return 0.0, ""


def _detect_fibonacci(sequence: list) -> tuple[float, str]:
    """Detect Fibonacci-like sequences: each element = sum of previous two."""
    if len(sequence) < 5:
        return 0.0, ""
    errors = []
    for i in range(2, len(sequence)):
        expected = sequence[i - 1] + sequence[i - 2]
        if expected == 0:
            continue
        errors.append(abs(sequence[i] - expected) / (abs(expected) + 1e-9))
    if not errors:
        return 0.0, ""
    avg_error = sum(errors) / len(errors)
    conf = max(0.0, min(1.0, 1.0 - avg_error * 10))
    if conf > 0.6:
        return conf, "fibonacci-like (each = sum of previous two)"
    return 0.0, ""


def _detect_power(sequence: list) -> tuple[float, str]:
    """Detect power sequences: n², n³, etc. (1-indexed)."""
    if len(sequence) < 4:
        return 0.0, ""
    for k in [2, 3]:
        errors = []
        for i, val in enumerate(sequence):
            expected = (i + 1) ** k
            if expected == 0:
                continue
            errors.append(abs(val - expected) / (abs(expected) + 1e-9))
        if errors and sum(errors) / len(errors) < 0.05:
            return 0.9, f"power sequence (n^{k})"
    return 0.0, ""


def _detect_periodic(sequence: list) -> tuple[float, int]:
    """Detect numeric periodicity with tolerance. Returns (confidence, period)."""
    if len(sequence) < 6:
        return 0.0, 0
    best_conf, best_period = 0.0, 0
    for period in range(2, len(sequence) // 2 + 1):
        errors = []
        for i in range(period, len(sequence)):
            denom = abs(sequence[i - period]) + 1e-9
            err = abs(sequence[i] - sequence[i - period]) / denom
            errors.append(err)
        if not errors:
            continue
        avg_err = sum(errors) / len(errors)
        conf = max(0.0, min(1.0, 1.0 - avg_err * 3))
        if conf > best_conf:
            best_conf = conf
            best_period = period
    return best_conf, best_period


def _detect_repeating(sequence: list) -> tuple[bool, int]:
    """Detect exact repeating subsequence (categorical or numeric)."""
    if len(sequence) < 2:
        return False, 0
    for period in range(1, len(sequence) // 2 + 1):
        chunk = sequence[:period]
        if all(sequence[i] == chunk[i % period] for i in range(period, len(sequence))):
            return True, period
    return False, 0


def _detect_anomalies(sequence: list) -> list:
    """Return values that are > 2 standard deviations from the mean."""
    if len(sequence) < 3:
        return []
    avg = sum(sequence) / len(sequence)
    variance = sum((x - avg) ** 2 for x in sequence) / len(sequence)
    std = variance ** 0.5
    if std == 0:
        return []
    return [x for x in sequence if abs(x - avg) > 2 * std]


def _detect_trend(sequence: list) -> str:
    """Classify the overall trend of a numeric sequence."""
    if len(sequence) < 2:
        return "insufficient_data"
    diffs = [sequence[i + 1] - sequence[i] for i in range(len(sequence) - 1)]
    pos = sum(1 for d in diffs if d > 0)
    neg = sum(1 for d in diffs if d < 0)

    if pos == len(diffs):
        return "strictly_increasing"
    if neg == len(diffs):
        return "strictly_decreasing"
    if pos > neg * 2:
        return "generally_increasing"
    if neg > pos * 2:
        return "generally_decreasing"
    if pos == 0 and neg == 0:
        return "constant"

    # Check alternating (oscillating)
    signs = [1 if d > 0 else -1 if d < 0 else 0 for d in diffs]
    non_zero = [s for s in signs if s != 0]
    if len(non_zero) >= 2 and all(
        non_zero[i] != non_zero[i + 1] for i in range(len(non_zero) - 1)
    ):
        return "oscillating"

    return "variable"


def _statistical_profile(sequence: list) -> dict:
    """Compute descriptive statistics for a numeric sequence."""
    n = len(sequence)
    if n == 0:
        return {}
    mean = sum(sequence) / n
    variance = sum((x - mean) ** 2 for x in sequence) / n
    std = variance ** 0.5
    rng = max(sequence) - min(sequence)
    cv = round(std / abs(mean), 4) if mean != 0 else None

    # Linear trend slope via least-squares
    if n >= 2:
        x_mean = (n - 1) / 2.0
        xy_sum = sum(i * (sequence[i] - mean) for i in range(n))
        xx_sum = sum((i - x_mean) ** 2 for i in range(n))
        slope = xy_sum / xx_sum if xx_sum != 0 else 0.0
    else:
        slope = 0.0

    return {
        "mean": round(mean, 4),
        "std": round(std, 4),
        "min": min(sequence),
        "max": max(sequence),
        "range": round(rng, 4),
        "coeff_variation": cv,
        "trend_slope": round(slope, 6),
    }


# ==================================================================
# Symbolic / categorical helpers
# ==================================================================

def _ngram_freq(sequence: list, n: int = 2) -> dict:
    """N-gram frequency for symbolic sequences. Returns top-5 n-grams."""
    if len(sequence) < n:
        return {}
    counts: dict = {}
    for i in range(len(sequence) - n + 1):
        gram = str(tuple(sequence[i : i + n]))
        counts[gram] = counts.get(gram, 0) + 1
    return dict(sorted(counts.items(), key=lambda x: x[1], reverse=True)[:5])
