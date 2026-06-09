"""
Pattern sensory processor.

Detects patterns, sequences, repetitions, and anomalies in ordered data.
Works on both numeric and categorical sequences.
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
            data = {"label": "unknown", "sequence": list(data)}

        label = data.get("label", "unknown")
        sequence = data.get("sequence", [])

        patterns_found = []
        importance = 0.3

        # Detect repetition
        if len(sequence) >= 2:
            for period in range(1, len(sequence) // 2 + 1):
                chunk = sequence[:period]
                repeats = True
                for i in range(period, len(sequence)):
                    if sequence[i] != chunk[i % period]:
                        repeats = False
                        break
                if repeats and period < len(sequence):
                    patterns_found.append(f"repeating (period {period}): {chunk}")
                    importance = 0.7
                    break

        # Detect anomalies in numeric sequences
        if all(isinstance(x, (int, float)) for x in sequence) and len(sequence) >= 3:
            avg = sum(sequence) / len(sequence)
            std = (sum((x - avg) ** 2 for x in sequence) / len(sequence)) ** 0.5
            if std > 0:
                anomalies = [x for x in sequence if abs(x - avg) > 2 * std]
                if anomalies:
                    patterns_found.append(f"anomalies: {anomalies}")
                    importance = max(importance, 0.65)

        # Detect sorted order
        if sequence == sorted(sequence):
            patterns_found.append("ascending order")
        elif sequence == sorted(sequence, reverse=True):
            patterns_found.append("descending order")

        return ProcessorOutput(
            source=self.name,
            input_data=data,
            extracted={
                "label": label,
                "sequence_length": len(sequence),
                "patterns": patterns_found,
            },
            importance=importance,
            suggested_key=f"pattern:{label.replace(' ', '_')}",
            context=f"Pattern '{label}': {', '.join(patterns_found) if patterns_found else 'no clear pattern'} "
                    f"(length: {len(sequence)})",
        )
