"""
Interoception — Genesis's sense of its own internal state.

LeDoux (1996): the fast subcortical path carries internal-state signals
alongside external sensory input. The body's state is not separate from
perception — it shapes what gets attended to and how strongly.

For Genesis, internal state metrics (energy, memory pressure, inference
rate, contradiction accumulation) are real signals that should flow through
the same processing machinery as external text or numeric input. When they
do, Genesis can form relations like:

    "high memory pressure PRECEDES throttling"
    "low energy AFFECTS inference rate"
    "contradiction increase CAUSES consolidation salience"

This is proprioception for a digital mind: the system has beliefs about
its own internal dynamics, not just its external knowledge.

Interoception runs at a configurable interval (default: every 50 cycles)
to avoid dominating processing with self-monitoring.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


_INTERO_INTERVAL = 50   # sample internal state every N cognitive cycles


def interoception_sample(brain) -> dict | None:
    """
    Sample Genesis's current internal state and return it as a numeric
    input payload suitable for brain.process_input("numeric", payload).

    Returns None if it's not yet time to sample (based on cycle count).
    Returns None if sampling fails for any reason (errors are data,
    but we don't want interoception to crash the cycle).
    """
    try:
        cycle = getattr(brain, "cycle_count", 0)
        if cycle == 0 or cycle % _INTERO_INTERVAL != 0:
            return None

        survival = brain.survival
        resource = survival.resource if survival else None
        mem_stats = brain.memory.stats() if hasattr(brain, "memory") else {}
        rel_stats = brain.relations.stats() if hasattr(brain, "relations") else {}
        inf_stats = brain.inference.stats() if hasattr(brain, "inference") else {}
        con_stats = brain.consolidation.stats() if hasattr(brain, "consolidation") else {}

        wm = mem_stats.get("working_memory", {})
        wm_util = wm.get("utilization_pct", 0.0) / 100.0

        energy = resource.energy if resource else 1.0
        total_relations = rel_stats.get("total_relations", 0)
        total_inferences = inf_stats.get("total_inferences", 0)
        total_reflections = con_stats.get("total_reflections", 0)

        return {
            "label": "internal_state",
            "source": "interoception",
            "cycle": cycle,
            "values": [
                round(energy, 3),
                round(wm_util, 3),
            ],
            "metrics": {
                "energy":            round(energy, 3),
                "memory_pressure":   round(wm_util, 3),
                "total_relations":   total_relations,
                "total_inferences":  total_inferences,
                "total_reflections": total_reflections,
            },
        }
    except Exception:
        return None
