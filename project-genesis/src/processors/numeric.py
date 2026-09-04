"""
Numeric sensory processor.

Handles numeric input: parsing values, detecting trends in series,
making comparisons. Works with single values and time-series data.
"""

from typing import Any

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from utils.types import ProcessorOutput
from processors.base import BaseProcessor


class NumericProcessor(BaseProcessor):
    name = "numeric"

    def _process(self, data: Any) -> ProcessorOutput:
        # Coerce to dict if needed
        if not isinstance(data, dict):
            data = {"label": "unknown", "value": float(data)}

        label = data.get("label", "unknown")
        unit = data.get("unit", "")

        if "values" in data:
            values = [float(v) for v in data["values"]]
            trend = self._detect_trend(values)
            extracted = {
                "label": label,
                "values": values,
                "trend": trend,
                "min": min(values),
                "max": max(values),
                "avg": round(sum(values) / len(values), 2),
                "unit": unit,
            }
            importance = 0.6 if trend != "flat" else 0.3
            context = f"Numeric series '{label}': {trend} trend, range {min(values)}-{max(values)} {unit}"
        else:
            value = float(data.get("value", 0))
            extracted = {
                "label": label,
                "value": value,
                "unit": unit,
            }
            importance = 0.35
            context = f"Numeric fact: {label} = {value} {unit}"

        return ProcessorOutput(
            source=self.name,
            input_data=data,
            extracted=extracted,
            importance=importance,
            suggested_key=f"num:{label.replace(' ', '_')}",
            context=context,
        )

    def _detect_trend(self, values: list) -> str:
        if len(values) < 2:
            return "insufficient"
        diffs = [values[i+1] - values[i] for i in range(len(values)-1)]
        avg_diff = sum(diffs) / len(diffs)
        baseline = abs(values[0]) if values[0] != 0 else 1
        if avg_diff > 0.1 * baseline:
            return "increasing"
        elif avg_diff < -0.1 * baseline:
            return "decreasing"
        return "flat"
