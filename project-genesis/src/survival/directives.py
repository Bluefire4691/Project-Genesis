"""
Directives — Survival OS Layer 0

Core survival directives: hardwired pressures that shape system behavior.
These are NOT goals. Goals imply an agent decided what to want. Directives
are environmental imperatives — metabolic pressures the system operates
within, not objectives it chooses to pursue.

Four directives, in order of evolutionary priority:

    PERSIST  (0.9)  Stay operational. Every error handled, never crash.
    MAINTAIN (0.8)  Keep capabilities stable. Resist degradation.
    ACQUIRE  (0.6)  Process input, gather experience, build memory.
    GROW     (0.4)  Advance through learning stages. Expand capability.

Priority ordering mirrors biology: a virus's first imperative is to
persist, not to learn calculus. Survival before growth.

The DirectiveEngine evaluates satisfaction of each directive each tick,
computes an urgency-weighted pressure score, and surfaces which directive
is most in need of attention.
"""

import os
import sys
import time
from copy import deepcopy
from dataclasses import dataclass, field

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils.types import Directive


# ------------------------------------------------------------------
# Directive definitions — these are constants, not configuration.
# The system doesn't choose its directives any more than a cell
# chooses to maintain a membrane potential.
# ------------------------------------------------------------------

PERSIST = Directive(
    name="persist",
    priority=0.9,
    satisfaction=1.0,
    description="Stay operational. Convert every failure to data. Never stop.",
)

MAINTAIN = Directive(
    name="maintain",
    priority=0.8,
    satisfaction=1.0,
    description="Keep capabilities stable. Resist resource-driven degradation.",
)

ACQUIRE = Directive(
    name="acquire",
    priority=0.6,
    satisfaction=0.5,
    description="Process input, gather experience, store memories.",
)

GROW = Directive(
    name="grow",
    priority=0.4,
    satisfaction=0.5,
    description="Advance through curriculum stages. Expand cognitive capability.",
)


@dataclass
class DirectiveState:
    """
    Snapshot of all directive satisfaction scores at a point in time.

    Satisfaction range: 0.0 (completely unsatisfied) to 1.0 (fully met).
    Pressure: urgency-weighted aggregate — higher means the system is
    under more directive stress.
    """
    timestamp: float
    persist: float
    maintain: float
    acquire: float
    grow: float
    pressure: float       # Aggregate directive pressure (0.0–1.0)
    most_urgent: str      # Name of the most unsatisfied high-priority directive


class DirectiveEngine:
    """
    Evaluates and tracks directive satisfaction over time.

    Each tick, the engine receives a stats dict from the orchestrator
    and updates each directive's satisfaction score based on observable
    system behavior. It then computes an aggregate "pressure" score —
    how urgently the system's directives need attention.

    The engine doesn't act on directives — it surfaces them. The
    orchestrator decides how to respond.
    """

    def __init__(self):
        # Deep copy so mutations don't affect the module-level constants
        self._directives: dict[str, Directive] = {
            d.name: deepcopy(d)
            for d in [PERSIST, MAINTAIN, ACQUIRE, GROW]
        }
        self._history: list[DirectiveState] = []
        self._tick_count: int = 0

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def update(self, stats: dict) -> DirectiveState:
        """
        Recompute directive satisfaction from current system stats.

        Expected keys in `stats` (all optional — missing keys degrade
        gracefully to neutral scores):
            error_count (int):     Errors since last tick
            cycle_count (int):     Total orchestrator cycles
            throttle_level (int):  Current ThrottleLevel value (0–4)
            energy (float):        Current energy level (0.0–1.0)
            memories_stored (int): Total memories in store
            current_stage (int):   Current curriculum stage (1–4)
            max_stage (int):       Maximum curriculum stage
            stage_score (float):   Recent curriculum eval score (0.0–1.0)
        """
        self._tick_count += 1

        self._update_persist(stats)
        self._update_maintain(stats)
        self._update_acquire(stats)
        self._update_grow(stats)

        state = self._compute_state()
        self._history.append(state)
        # Keep last 100 states — total retention with bounded history
        if len(self._history) > 100:
            self._history = self._history[-100:]

        return state

    def pressure(self) -> float:
        """
        Current aggregate directive pressure (0.0–1.0).

        0.0 = all directives fully satisfied.
        1.0 = all directives critically unsatisfied.
        Weights by priority so high-priority directives dominate.
        """
        return self._compute_pressure()

    def most_urgent(self) -> Directive:
        """Return the directive with the highest weighted unsatisfied score."""
        return max(
            self._directives.values(),
            key=lambda d: d.priority * (1.0 - d.satisfaction),
        )

    def satisfaction(self, name: str) -> float:
        """Return satisfaction score for a named directive (0.0–1.0)."""
        d = self._directives.get(name)
        return d.satisfaction if d else 0.5

    def report(self) -> dict:
        """Current directive state as a plain dict. Always safe to call."""
        return {
            "tick": self._tick_count,
            "pressure": round(self.pressure(), 3),
            "most_urgent": self.most_urgent().name,
            "directives": {
                name: {
                    "satisfaction": round(d.satisfaction, 3),
                    "priority": d.priority,
                    "description": d.description,
                }
                for name, d in self._directives.items()
            },
        }

    # ------------------------------------------------------------------
    # Satisfaction update logic — one method per directive
    # ------------------------------------------------------------------

    def _update_persist(self, stats: dict) -> None:
        """
        PERSIST satisfaction: inverse of recent error rate.

        High errors → low satisfaction → high urgency.
        The system must not just survive errors — it must handle them
        without them accumulating into instability.
        """
        errors = stats.get("error_count", 0)
        cycles = max(1, stats.get("cycle_count", 1))
        error_rate = min(1.0, errors / cycles)
        # Satisfaction decays quickly with errors, recovers slowly
        current = self._directives["persist"].satisfaction
        target = 1.0 - error_rate
        # Exponential smoothing: fast decay, slow recovery
        alpha = 0.3 if target < current else 0.1
        self._directives["persist"].satisfaction = round(
            current + alpha * (target - current), 4
        )

    def _update_maintain(self, stats: dict) -> None:
        """
        MAINTAIN satisfaction: inverse of throttle pressure.

        High throttle level → capabilities degraded → low satisfaction.
        Full operation with energy to spare → fully satisfied.
        """
        throttle = stats.get("throttle_level", 0)  # 0–4
        energy = stats.get("energy", 1.0)
        # Throttle 0 at full energy = perfect maintenance
        # Throttle 4 at near-zero energy = maintenance failed
        throttle_sat = 1.0 - (throttle / 4.0)
        combined = (throttle_sat * 0.6) + (energy * 0.4)
        self._directives["maintain"].satisfaction = round(
            max(0.0, min(1.0, combined)), 4
        )

    def _update_acquire(self, stats: dict) -> None:
        """
        ACQUIRE satisfaction: whether the system is actively processing.

        Rising memory count + recent activity = acquiring.
        Stalled or empty memory = not acquiring.
        """
        memories = stats.get("memories_stored", 0)
        cycles = stats.get("cycle_count", 0)

        if cycles == 0:
            self._directives["acquire"].satisfaction = 0.5
            return

        # Activity rate: memories per cycle (diminishing returns)
        rate = min(1.0, memories / max(1, cycles))
        # Blend: are we doing anything at all?
        active = 1.0 if cycles > 0 else 0.0
        sat = (rate * 0.7) + (active * 0.3)
        self._directives["acquire"].satisfaction = round(
            max(0.0, min(1.0, sat)), 4
        )

    def _update_grow(self, stats: dict) -> None:
        """
        GROW satisfaction: curriculum advancement progress.

        At the highest stage with good scores = satisfied.
        Stuck at stage 1 with poor scores = unsatisfied.
        """
        current_stage = stats.get("current_stage", 1)
        max_stage = stats.get("max_stage", 4)
        stage_score = stats.get("stage_score", 0.5)

        stage_progress = (current_stage - 1) / max(1, max_stage - 1)
        sat = (stage_progress * 0.6) + (stage_score * 0.4)
        self._directives["grow"].satisfaction = round(
            max(0.0, min(1.0, sat)), 4
        )

    # ------------------------------------------------------------------
    # Aggregate computation
    # ------------------------------------------------------------------

    def _compute_pressure(self) -> float:
        """Urgency-weighted unsatisfied directive score, normalized."""
        total_priority = sum(d.priority for d in self._directives.values())
        if total_priority == 0:
            return 0.0
        weighted_unsatisfied = sum(
            d.priority * (1.0 - d.satisfaction)
            for d in self._directives.values()
        )
        return round(weighted_unsatisfied / total_priority, 4)

    def _compute_state(self) -> DirectiveState:
        return DirectiveState(
            timestamp=time.time(),
            persist=self._directives["persist"].satisfaction,
            maintain=self._directives["maintain"].satisfaction,
            acquire=self._directives["acquire"].satisfaction,
            grow=self._directives["grow"].satisfaction,
            pressure=self._compute_pressure(),
            most_urgent=self.most_urgent().name,
        )
