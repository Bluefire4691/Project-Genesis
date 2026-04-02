"""
Observer — trend-based stagnation and danger detection.

The Observer doesn't judge what Genesis values or where it's going.
It watches for two specific failure modes:

    STAGNATION   — the system has stopped developing. Not going somewhere
                   we didn't expect — just stopped. Nothing is growing,
                   linking, or turning over. Like a plant that's stopped
                   responding to light.

    DANGER       — self-regulation has broken down. The system is in a
                   destructive trend: consuming itself (resources declining
                   past what throttling can fix) or collapsing diversity
                   (all processing converging on one thing, closed loop).

Everything between those two thresholds is normal operation. The Observer
has no opinion about what Genesis should be doing — only about whether
it's doing anything at all, and whether it's destroying the conditions
for its own continued existence.

Detection is trend-based, not point-in-time. A single bad cycle is noise.
A sustained direction is a signal. N consecutive cycles showing the same
pattern before a state change is triggered.

On state change:
    STAGNANT → the InteractionLayer calls inject_stimulus()
    DANGER   → the InteractionLayer calls pause()

Neither of those tells Genesis what to do. They're the minimum
intervention consistent with keeping it alive and developing.
"""

import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from interface.expression import ExpressionSnapshot


class SystemState(Enum):
    """
    The three states the Observer can report.

    NORMAL:    operating within bounds — full autonomy
    STAGNANT:  development has stopped — stimulus warranted
    DANGER:    self-regulation failing — pause warranted
    """
    NORMAL   = "normal"
    STAGNANT = "stagnant"
    DANGER   = "danger"


@dataclass
class ObservationRecord:
    """A single cycle's observation data fed into the trend analysis."""
    timestamp: float
    cycle: int
    energy: float
    working_memory_load: float
    association_count_delta: int   # new associations formed since last record
    source_diversity_count: int    # number of distinct source types active
    attention_top_key: str         # top attention item key (change = development)
    new_memories_this_cycle: int   # memories stored this cycle
    error_count: int


@dataclass
class ObserverReport:
    """What the Observer is currently seeing."""
    timestamp: float
    state: SystemState
    cycles_in_state: int           # consecutive cycles at current state
    stagnation_signals: list[str]  # which stagnation indicators are active
    danger_signals: list[str]      # which danger indicators are active
    last_change_cycle: int         # cycle when state last changed
    recommendation: str            # plain-language summary

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "state": self.state.value,
            "cycles_in_state": self.cycles_in_state,
            "stagnation_signals": self.stagnation_signals,
            "danger_signals": self.danger_signals,
            "last_change_cycle": self.last_change_cycle,
            "recommendation": self.recommendation,
        }


class Observer:
    """
    Watches Genesis for stagnation and self-regulation failure.

    State changes require N consecutive cycles of the same signal before
    committing. This prevents reacting to transient noise — a single bad
    cycle is not a pattern.

    All thresholds are configurable so they can be tuned as we observe
    real behavior. The defaults are conservative: we'd rather miss a
    stagnation event than wrongly intervene.
    """

    # How many consecutive cycles a signal must hold before state change
    COMMITMENT_CYCLES = 5

    def __init__(
        self,
        # Stagnation thresholds
        stagnation_min_new_memories: int = 0,     # per cycle floor
        stagnation_attention_freeze_cycles: int = 8,  # same top item for N cycles
        stagnation_no_associations_cycles: int = 10,  # zero new links for N cycles
        # Danger thresholds
        danger_energy_floor: float = 0.15,        # energy below this for N cycles
        danger_diversity_floor: int = 1,          # only 1 source type for N cycles
        danger_loop_cycles: int = 6,              # same top-attention key for N cycles
                                                  # with zero new memories
    ):
        self._stagnation_min_new_memories = stagnation_min_new_memories
        self._stagnation_attention_freeze_cycles = stagnation_attention_freeze_cycles
        self._stagnation_no_associations_cycles = stagnation_no_associations_cycles
        self._danger_energy_floor = danger_energy_floor
        self._danger_diversity_floor = danger_diversity_floor
        self._danger_loop_cycles = danger_loop_cycles

        self._history: deque[ObservationRecord] = deque(maxlen=50)
        self._state: SystemState = SystemState.NORMAL
        self._cycles_in_state: int = 0
        self._last_change_cycle: int = 0
        self._candidate_state: SystemState = SystemState.NORMAL
        self._candidate_cycles: int = 0
        self._total_associations_seen: int = 0

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def observe(
        self,
        snapshot: ExpressionSnapshot,
        energy: float,
        error_count: int,
        new_memories_this_cycle: int,
        total_associations: int,
    ) -> ObserverReport:
        """
        Process a new observation and return current assessment.

        Args:
            snapshot:              Current ExpressionSnapshot from ExpressionEngine.
            energy:                Current Survival OS energy level (0.0–1.0).
            error_count:           Total errors logged so far.
            new_memories_this_cycle: Memories stored in the current cycle.
            total_associations:    Total association links in the store.
        """
        assoc_delta = total_associations - self._total_associations_seen
        self._total_associations_seen = total_associations

        record = ObservationRecord(
            timestamp=time.time(),
            cycle=snapshot.cycle,
            energy=energy,
            working_memory_load=snapshot.working_memory_load,
            association_count_delta=assoc_delta,
            source_diversity_count=len(snapshot.source_diversity),
            attention_top_key=snapshot.attention_top[0]["key"] if snapshot.attention_top else "",
            new_memories_this_cycle=new_memories_this_cycle,
            error_count=error_count,
        )
        self._history.append(record)
        self._cycles_in_state += 1

        stagnation_signals = self._check_stagnation()
        danger_signals = self._check_danger()

        # Determine candidate state
        if danger_signals:
            candidate = SystemState.DANGER
        elif stagnation_signals:
            candidate = SystemState.STAGNANT
        else:
            candidate = SystemState.NORMAL

        # Apply commitment: N consecutive cycles before state change
        self._apply_commitment(candidate, snapshot.cycle)

        return ObserverReport(
            timestamp=time.time(),
            state=self._state,
            cycles_in_state=self._cycles_in_state,
            stagnation_signals=stagnation_signals,
            danger_signals=danger_signals,
            last_change_cycle=self._last_change_cycle,
            recommendation=self._recommend(),
        )

    @property
    def state(self) -> SystemState:
        return self._state

    def report(self) -> dict:
        return {
            "state": self._state.value,
            "cycles_in_state": self._cycles_in_state,
            "observations_recorded": len(self._history),
            "last_change_cycle": self._last_change_cycle,
            "recommendation": self._recommend(),
        }

    # ------------------------------------------------------------------
    # Signal detection — stagnation
    # ------------------------------------------------------------------

    def _check_stagnation(self) -> list[str]:
        """
        Check for stagnation signals across recent history.
        Returns list of active signal names.
        """
        if len(self._history) < 3:
            return []

        signals = []
        recent = list(self._history)

        # Signal 1: no new memories being stored
        recent_new = [r.new_memories_this_cycle for r in recent[-self._stagnation_no_associations_cycles:]]
        if (len(recent_new) >= self._stagnation_no_associations_cycles
                and all(n <= self._stagnation_min_new_memories for n in recent_new)):
            signals.append("no_new_memories")

        # Signal 2: attention frozen — same top item for many cycles
        if len(recent) >= self._stagnation_attention_freeze_cycles:
            top_keys = [r.attention_top_key for r in recent[-self._stagnation_attention_freeze_cycles:]]
            if len(set(top_keys)) == 1 and top_keys[0] != "":
                signals.append("attention_frozen")

        # Signal 3: no new associations forming
        if len(recent) >= self._stagnation_no_associations_cycles:
            recent_assoc_deltas = [r.association_count_delta for r in recent[-self._stagnation_no_associations_cycles:]]
            if all(d == 0 for d in recent_assoc_deltas):
                signals.append("no_new_associations")

        return signals

    # ------------------------------------------------------------------
    # Signal detection — danger
    # ------------------------------------------------------------------

    def _check_danger(self) -> list[str]:
        """
        Check for danger signals — self-regulation failure trends.
        Returns list of active signal names.
        """
        if len(self._history) < 3:
            return []

        signals = []
        recent = list(self._history)

        # Signal 1: energy critically low and sustained — consuming itself
        window = min(self.COMMITMENT_CYCLES, len(recent))
        energy_recent = [r.energy for r in recent[-window:]]
        if (len(energy_recent) >= window
                and all(e < self._danger_energy_floor for e in energy_recent)):
            signals.append("sustained_energy_collapse")

        # Signal 2: diversity collapse — only one source type for extended period
        if len(recent) >= self.COMMITMENT_CYCLES:
            diversity_recent = [r.source_diversity_count for r in recent[-self.COMMITMENT_CYCLES:]]
            if all(d <= self._danger_diversity_floor for d in diversity_recent):
                signals.append("diversity_collapse")

        # Signal 3: closed loop — same top item, zero new memories, for N cycles
        # (processing its own output, not taking in the world)
        if len(recent) >= self._danger_loop_cycles:
            loop_window = recent[-self._danger_loop_cycles:]
            top_keys = [r.attention_top_key for r in loop_window]
            new_mems = [r.new_memories_this_cycle for r in loop_window]
            if (len(set(top_keys)) == 1
                    and top_keys[0] != ""
                    and all(n == 0 for n in new_mems)):
                signals.append("closed_loop")

        return signals

    # ------------------------------------------------------------------
    # State commitment (hysteresis)
    # ------------------------------------------------------------------

    def _apply_commitment(self, candidate: SystemState, cycle: int) -> None:
        """Commit to a state change only after N consecutive matching cycles."""
        if candidate == self._state:
            self._candidate_cycles = 0
            self._candidate_state = candidate
            return

        if candidate == self._candidate_state:
            self._candidate_cycles += 1
            if self._candidate_cycles >= self.COMMITMENT_CYCLES:
                self._state = candidate
                self._cycles_in_state = 0
                self._last_change_cycle = cycle
                self._candidate_cycles = 0
        else:
            self._candidate_state = candidate
            self._candidate_cycles = 1

    # ------------------------------------------------------------------
    # Recommendation
    # ------------------------------------------------------------------

    def _recommend(self) -> str:
        if self._state == SystemState.NORMAL:
            return "Operating normally. Observe and participate — no intervention needed."
        elif self._state == SystemState.STAGNANT:
            return (
                "Development has stalled. Consider injecting novel stimulus — "
                "new input type or topic Genesis hasn't encountered. "
                "No direction required, just novelty."
            )
        elif self._state == SystemState.DANGER:
            return (
                "Self-regulation signals present. Recommend pausing the cycle "
                "and inspecting current state before resuming. "
                "Do not reprogram — assess first."
            )
        return "Unknown state."
