"""
Layer 0: Survival OS

The foundation everything else runs on. Manages the system's continued
existence through resource tracking, core directives, and never-crash
resilience infrastructure.

Public façade: SurvivalOS wires the three subsystems together and
exposes the interface the Orchestrator (Layer 2) uses.

    survival = SurvivalOS()
    survival.tick(orchestrator_stats)   # called each cognitive cycle
    survival.can("numeric")             # check capability availability
    survival.safe_call(fn, data)        # never-crash call wrapper
    survival.report()                   # full status dict
"""

import os
import sys
from typing import Any, Callable

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from survival.resource_manager import ResourceManager, ThrottleLevel
from survival.directives import DirectiveEngine
from survival.resilience import ResilienceMonitor


class SurvivalOS:
    """
    Layer 0: Survival OS façade.

    Wires together resource management, directives, and resilience.
    The Orchestrator calls tick() once per cognitive cycle to update
    all three subsystems in sequence.

    Responsibilities:
        - Resource tracking and throttle level (ResourceManager)
        - Directive satisfaction and pressure (DirectiveEngine)
        - Never-crash infrastructure (ResilienceMonitor)

    The Orchestrator checks can() to decide which processors and memory
    operations are available this cycle. It calls safe_call() for any
    operation that could fail.
    """

    def __init__(
        self,
        memory_limit_mb: int = 512,
        cpu_budget_ms: float = 100.0,
    ):
        self.resource = ResourceManager(
            memory_limit_mb=memory_limit_mb,
            cpu_budget_ms=cpu_budget_ms,
        )
        self.directives = DirectiveEngine()
        self.resilience = ResilienceMonitor()

        self._tick_count: int = 0

    def tick(self, orchestrator_stats: dict | None = None) -> dict:
        """
        Advance one cognitive cycle.

        Samples resources, updates directive satisfaction, and returns
        a combined state snapshot. Called by the Orchestrator at the
        start of each processing cycle.

        Args:
            orchestrator_stats: Optional dict from the Orchestrator with
                keys: error_count, cycle_count, throttle_level, energy,
                memories_stored, current_stage, max_stage, stage_score.
                If None, directives use last-known state.

        Returns:
            Combined state dict from all three subsystems.
        """
        self._tick_count += 1

        # 1. Sample real resources — updates energy and throttle
        snap = self.resilience.safe_call(
            self.resource.tick,
            fallback=None,
            label="resource_manager.tick",
        )

        # 2. Update directives with current system stats
        stats = orchestrator_stats or {}
        stats.setdefault("energy", self.resource.energy)
        stats.setdefault("throttle_level", int(self.resource.throttle_level))

        directive_state = self.resilience.safe_call(
            self.directives.update,
            stats,
            fallback=None,
            label="directives.update",
        )

        return {
            "tick": self._tick_count,
            "energy": self.resource.energy,
            "throttle": self.resource.throttle_level.name,
            "pressure": self.directives.pressure(),
            "most_urgent": self.directives.most_urgent().name,
            "capabilities": sorted(self.resource.capabilities()),
        }

    def can(self, capability: str) -> bool:
        """Return True if `capability` is available at the current throttle level."""
        return self.resource.can(capability)

    def safe_call(
        self,
        fn: Callable,
        *args,
        fallback: Any = None,
        label: str = "",
        **kwargs,
    ) -> Any:
        """Never-crash call wrapper bound to the shared error log."""
        return self.resilience.safe_call(
            fn, *args,
            fallback=fallback,
            label=label,
            **kwargs,
        )

    def report(self) -> dict:
        """Full Survival OS status. Always safe to call."""
        return {
            "survival_os": {
                "tick_count": self._tick_count,
                "resource": self.resource.report(),
                "directives": self.directives.report(),
                "resilience": self.resilience.report(),
            }
        }
