"""
Interventions — minimum viable response to stagnation and danger.

Two interventions exist. That's intentional — we want the smallest
possible intervention set consistent with keeping Genesis alive and
developing.

    inject_stimulus(data, input_type)
        For stagnation. Introduces novel input without instructions.
        The data goes into the processing pipeline exactly as any
        other input would — Genesis decides what to do with it.
        We don't tell it what to conclude. We just put something
        new in front of it.

    pause() / resume()
        For danger signals. Stops the cognitive cycle. Doesn't modify
        any state — working memory, long-term store, associations, and
        directives are all left exactly as they were. We pause, inspect,
        decide together what the signal means, then resume or don't.

What these interventions are NOT:
    - They don't modify what Genesis values
    - They don't reweight memories or change relevance scores
    - They don't tell Genesis what to process next (stimulus is just input)
    - They don't reset or reprogram anything

The pause is the hard stop. If we're in danger state and something
genuinely destructive is happening, we stop the cycle and look. Not
because we've decided it's wrong — because we need to understand it
before deciding anything.
"""

import time
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class StimulusRecord:
    """Record of an injected stimulus."""
    timestamp: float
    input_type: str
    data: Any
    reason: str     # why stimulus was injected ("stagnation", "manual", etc.)


@dataclass
class PauseRecord:
    """Record of a pause event."""
    timestamp: float
    reason: str
    cycle_at_pause: int
    resumed_at: float | None = None
    resume_cycle: int | None = None


class InterventionEngine:
    """
    Manages the two intervention types and their history.

    The Orchestrator checks is_paused() at the start of each cycle.
    If paused, it holds without processing until resume() is called.

    Stimuli are queued and drained one per cycle — the Orchestrator
    calls next_stimulus() before its normal input processing. If a
    stimulus is waiting, it processes that instead.
    """

    def __init__(self):
        self._paused: bool = False
        self._pause_record: PauseRecord | None = None

        self._stimulus_queue: list[tuple[str, Any, str]] = []  # (input_type, data, reason)
        self._stimulus_history: list[StimulusRecord] = []
        self._pause_history: list[PauseRecord] = []

        self._total_stimuli: int = 0
        self._total_pauses: int = 0

    # ------------------------------------------------------------------
    # Pause / resume
    # ------------------------------------------------------------------

    def pause(self, reason: str, cycle: int) -> PauseRecord:
        """
        Pause the cognitive cycle.

        Idempotent — calling pause() when already paused updates the
        reason but doesn't create a new pause record.
        """
        if not self._paused:
            self._paused = True
            self._pause_record = PauseRecord(
                timestamp=time.time(),
                reason=reason,
                cycle_at_pause=cycle,
            )
            self._pause_history.append(self._pause_record)
            self._total_pauses += 1
        return self._pause_record

    def resume(self, cycle: int) -> bool:
        """
        Resume from pause.

        Returns True if we were paused and have now resumed,
        False if we weren't paused (no-op).
        """
        if not self._paused:
            return False
        self._paused = False
        if self._pause_record:
            self._pause_record.resumed_at = time.time()
            self._pause_record.resume_cycle = cycle
        self._pause_record = None
        return True

    @property
    def is_paused(self) -> bool:
        """True if the cognitive cycle is currently paused."""
        return self._paused

    @property
    def pause_reason(self) -> str | None:
        """Reason for current pause, or None if not paused."""
        return self._pause_record.reason if self._pause_record else None

    # ------------------------------------------------------------------
    # Stimulus injection
    # ------------------------------------------------------------------

    def inject_stimulus(self, data: Any, input_type: str = "text", reason: str = "stagnation") -> StimulusRecord:
        """
        Queue a stimulus for Genesis to process next cycle.

        The stimulus enters the processing pipeline as ordinary input —
        same path as any human or curriculum input. No special weighting.
        Genesis decides what to do with it.

        Args:
            data:       The input to inject (string, dict, number, etc.)
            input_type: Processor type ('text', 'numeric', 'pattern')
            reason:     Why this stimulus was injected (for the log)
        """
        self._stimulus_queue.append((input_type, data, reason))
        record = StimulusRecord(
            timestamp=time.time(),
            input_type=input_type,
            data=data,
            reason=reason,
        )
        self._stimulus_history.append(record)
        self._total_stimuli += 1
        return record

    def next_stimulus(self) -> tuple[str, Any] | None:
        """
        Drain one stimulus from the queue.

        Returns (input_type, data) if a stimulus is waiting, else None.
        Called by the Orchestrator at the start of each cycle.
        """
        if not self._stimulus_queue:
            return None
        input_type, data, _ = self._stimulus_queue.pop(0)
        return input_type, data

    @property
    def stimulus_pending(self) -> bool:
        """True if there are stimuli waiting to be processed."""
        return len(self._stimulus_queue) > 0

    # ------------------------------------------------------------------
    # History and stats
    # ------------------------------------------------------------------

    def recent_stimuli(self, n: int = 5) -> list[StimulusRecord]:
        return self._stimulus_history[-n:]

    def recent_pauses(self, n: int = 5) -> list[PauseRecord]:
        return self._pause_history[-n:]

    def report(self) -> dict:
        return {
            "is_paused": self._paused,
            "pause_reason": self.pause_reason,
            "stimulus_queue_depth": len(self._stimulus_queue),
            "total_stimuli_injected": self._total_stimuli,
            "total_pauses": self._total_pauses,
            "recent_pause_reasons": [p.reason for p in self.recent_pauses(3)],
        }
