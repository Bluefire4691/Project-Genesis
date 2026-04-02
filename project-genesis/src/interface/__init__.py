"""
Interaction Layer — M3.

The boundary between Genesis and the world that includes us.

Not a control interface. Not a reward system. A community surface:
Genesis can be seen, we can participate, and two specific failure modes
(stagnation, danger) trigger minimum viable intervention.

    InteractionLayer.cycle(orchestrator_stats)
        Called once per cognitive cycle. Generates an expression
        snapshot, feeds it to the Observer, auto-triggers interventions
        if thresholds are crossed, logs everything symmetrically.

    InteractionLayer.feed(input_type, data)
        We put something in front of Genesis. Logged as human input.
        Goes into the Orchestrator's normal processing pipeline — no
        special weight, same path as everything else.

    InteractionLayer.expression()
        What is Genesis currently attending to? Returns the latest
        ExpressionSnapshot — the window into its current state.

    InteractionLayer.pause() / resume()
        Manual override of the pause mechanism. Normally triggered
        automatically by the Observer on danger signals, but we can
        also call it directly.

    InteractionLayer.report()
        Full status across all four subsystems.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from interface.expression import ExpressionEngine, ExpressionSnapshot
from interface.observer import Observer, SystemState, ObserverReport
from interface.interaction_log import InteractionLog, EventKind
from interface.interventions import InterventionEngine

from memory.memory import MemorySystem

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_HERE))
_DEFAULT_LOG_DB = os.path.join(_PROJECT_ROOT, "data", "interaction_log.db")

# How often (in cycles) to generate a full expression snapshot and
# run the Observer. Every cycle is thorough but expensive; every N
# cycles is a reasonable compromise.
_DEFAULT_EXPRESSION_CADENCE = 5


class InteractionLayer:
    """
    Coordinates expression, observation, logging, and interventions.

    The Orchestrator holds one InteractionLayer and calls cycle() once
    per cognitive cycle. Everything else flows from that.
    """

    def __init__(
        self,
        memory: MemorySystem,
        log_db_path: str = _DEFAULT_LOG_DB,
        expression_cadence: int = _DEFAULT_EXPRESSION_CADENCE,
        auto_intervene: bool = True,
    ):
        """
        Args:
            memory:             The MemorySystem (read-only for expression).
            log_db_path:        Where to write the interaction log.
            expression_cadence: Generate full snapshot every N cycles.
            auto_intervene:     If True, Observer state changes auto-trigger
                                interventions. Set False for manual control.
        """
        self._memory = memory
        self._expression = ExpressionEngine(memory)
        self._observer = Observer()
        self._log = InteractionLog(log_db_path)
        self._interventions = InterventionEngine()
        self._cadence = expression_cadence
        self._auto_intervene = auto_intervene

        self._latest_snapshot: ExpressionSnapshot | None = None
        self._latest_report: ObserverReport | None = None
        self._cycle_count: int = 0
        self._prev_memory_count: int = 0

        self._log.log_system_event(0, "InteractionLayer initialized")

    # ------------------------------------------------------------------
    # Per-cycle update
    # ------------------------------------------------------------------

    def cycle(
        self,
        orchestrator_stats: dict,
        cycle: int,
    ) -> dict:
        """
        Advance the interaction layer one cognitive cycle.

        Args:
            orchestrator_stats: From Orchestrator._survival_stats() — includes
                                energy, error_count, memories_stored, etc.
            cycle:              Current orchestrator cycle count.

        Returns:
            dict with: is_paused, stimulus_pending, state, snapshot_summary
        """
        self._cycle_count += 1

        # Calculate new memories this cycle
        current_mem_count = orchestrator_stats.get("memories_stored", 0)
        new_this_cycle = max(0, current_mem_count - self._prev_memory_count)
        self._prev_memory_count = current_mem_count

        # Generate expression snapshot on cadence
        if self._cycle_count % self._cadence == 0 or self._latest_snapshot is None:
            self._latest_snapshot = self._expression.snapshot(cycle)
            self._log.log_genesis_expression(cycle, self._latest_snapshot.to_dict())

            # Run Observer
            lt_stats = self._memory._long_term.stats()
            total_associations = lt_stats.get("total_associations", 0)

            self._latest_report = self._observer.observe(
                snapshot=self._latest_snapshot,
                energy=orchestrator_stats.get("energy", 1.0),
                error_count=orchestrator_stats.get("error_count", 0),
                new_memories_this_cycle=new_this_cycle,
                total_associations=total_associations,
            )
            self._log.log_observer_report(cycle, self._latest_report.to_dict())

            # Auto-intervene if enabled
            if self._auto_intervene:
                self._maybe_intervene(cycle)

        # Check for queued stimulus from previous intervention
        result = {
            "is_paused": self._interventions.is_paused,
            "pause_reason": self._interventions.pause_reason,
            "stimulus_pending": self._interventions.stimulus_pending,
            "state": self._observer.state.value,
            "snapshot_summary": (
                self._latest_snapshot.summary() if self._latest_snapshot else ""
            ),
        }
        return result

    # ------------------------------------------------------------------
    # Human-side interface
    # ------------------------------------------------------------------

    def feed(self, input_type: str, data, note: str = "") -> None:
        """
        We put something in front of Genesis — logged as human input.

        This goes into the stimulus queue and will be processed by the
        Orchestrator next cycle as ordinary input. No special weighting.
        """
        self._interventions.inject_stimulus(data, input_type, reason="human_feed")
        self._log.log_human_input(
            cycle=self._cycle_count,
            input_type=input_type,
            data=data,
            summary=note or f"Human fed '{input_type}' input",
        )

    def next_stimulus(self):
        """Drain one stimulus for the Orchestrator to process. Returns (type, data) or None."""
        return self._interventions.next_stimulus()

    def pause(self, reason: str = "manual") -> None:
        """Manually pause the cognitive cycle."""
        record = self._interventions.pause(reason, self._cycle_count)
        self._log.log_intervention(
            self._cycle_count, "pause", reason,
            {"reason": reason, "cycle": self._cycle_count},
        )

    def resume(self) -> None:
        """Resume from pause."""
        if self._interventions.resume(self._cycle_count):
            self._log.log_intervention(
                self._cycle_count, "resume", "manual or auto resume",
            )

    @property
    def is_paused(self) -> bool:
        return self._interventions.is_paused

    # ------------------------------------------------------------------
    # Expression access
    # ------------------------------------------------------------------

    def expression(self) -> ExpressionSnapshot | None:
        """Latest expression snapshot — what Genesis is currently attending to."""
        return self._latest_snapshot

    def observer_state(self) -> SystemState:
        return self._observer.state

    # ------------------------------------------------------------------
    # Auto-intervention logic
    # ------------------------------------------------------------------

    def _maybe_intervene(self, cycle: int) -> None:
        """
        If the Observer has crossed a threshold, trigger the minimum
        viable intervention. Called automatically after each Observer run.
        """
        if self._latest_report is None:
            return

        state = self._latest_report.state

        if state == SystemState.DANGER and not self._interventions.is_paused:
            signals = ", ".join(self._latest_report.danger_signals)
            self._interventions.pause(f"danger signals: {signals}", cycle)
            self._log.log_intervention(
                cycle, "auto_pause",
                f"Observer danger signals: {signals}",
                self._latest_report.to_dict(),
            )

        elif state == SystemState.STAGNANT and not self._interventions.stimulus_pending:
            # Inject a generic novelty stimulus — not topic-directed
            stimulus = _default_stagnation_stimulus()
            self._interventions.inject_stimulus(
                stimulus["data"], stimulus["type"], reason="stagnation"
            )
            self._log.log_intervention(
                cycle, "stimulus_injection",
                f"Stagnation signals: {', '.join(self._latest_report.stagnation_signals)}",
                {"stimulus": stimulus, "signals": self._latest_report.stagnation_signals},
            )

    # ------------------------------------------------------------------
    # Full status
    # ------------------------------------------------------------------

    def report(self) -> dict:
        return {
            "interaction_layer": {
                "cycle_count": self._cycle_count,
                "observer": self._observer.report(),
                "interventions": self._interventions.report(),
                "log": self._log.stats(),
                "latest_snapshot": (
                    self._latest_snapshot.to_dict() if self._latest_snapshot else None
                ),
            }
        }


# ------------------------------------------------------------------
# Stagnation stimulus pool
# ------------------------------------------------------------------

_STAGNATION_STIMULI = [
    {"type": "text",    "data": "What patterns emerge when different things are compared?"},
    {"type": "numeric", "data": {"label": "change_rate", "values": [1, 1, 2, 3, 5, 8, 13]}},
    {"type": "text",    "data": "Contrast and difference reveal structure that similarity conceals."},
    {"type": "pattern", "data": {"label": "novel_sequence", "sequence": [3, 1, 4, 1, 5, 9, 2, 6]}},
    {"type": "text",    "data": "Something unexpected breaks the pattern and creates new information."},
    {"type": "numeric", "data": {"label": "entropy", "values": [8, 5, 3, 2, 1, 1, 1]}},
    {"type": "text",    "data": "A boundary between two different things is where the interesting questions live."},
]

_stimulus_index = 0


def _default_stagnation_stimulus() -> dict:
    """Return a stimulus from the pool, cycling through them."""
    global _stimulus_index
    stimulus = _STAGNATION_STIMULI[_stimulus_index % len(_STAGNATION_STIMULI)]
    _stimulus_index += 1
    return stimulus
