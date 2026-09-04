"""
Resilience — Survival OS Layer 0

Never-crash infrastructure. All system calls route through this layer
so that exceptions become structured data rather than stop conditions.

This implements Jacob's core insight: "Animals don't throw exceptions.
Any situation they run into isn't a stop — it's a new figure-it-out
situation."

Key concepts:

    safe_call()         Execute any callable. On failure, log and
                        return a fallback value — never re-raise.

    FallbackChain       Try a sequence of callables. Return the first
                        that succeeds. If all fail, return a fallback.
                        Models biological redundancy.

    ErrorLog            Append-only record of every exception ever
                        caught. Nothing is discarded — errors are data.
                        Provides error rate and recent-error views.

    ResilienceMonitor   Wraps safe_call and FallbackChain with a shared
                        ErrorLog. Tracks system-wide error rate and
                        exposes it to the DirectiveEngine (PERSIST
                        directive satisfaction depends on this).

Inspired by Erlang/BEAM's supervisor pattern: subsystems can fail and
be isolated without cascading. The monitor is the supervisor.
"""

import os
import sys
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ------------------------------------------------------------------
# Error record — the unit of error-as-data
# ------------------------------------------------------------------

@dataclass
class ErrorRecord:
    """
    A structured record of a caught exception.

    We never discard errors. The total record accumulates — just like
    memory. The error rate view provides a sliding-window summary.
    """
    timestamp: float
    label: str              # What was being attempted
    error_type: str         # Exception class name
    message: str            # str(exception)
    traceback_str: str      # Full traceback
    recovered: bool = True  # Did we successfully fall back?

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "label": self.label,
            "error_type": self.error_type,
            "message": self.message,
            "recovered": self.recovered,
        }


# ------------------------------------------------------------------
# Error log — total retention for errors
# ------------------------------------------------------------------

class ErrorLog:
    """
    Append-only record of every exception caught by this system.

    Errors are never deleted. The `recent()` and `error_rate()` methods
    provide windowed views without discarding the full history.
    """

    def __init__(self):
        self._records: list[ErrorRecord] = []

    def log(
        self,
        label: str,
        exc: Exception,
        recovered: bool = True,
    ) -> ErrorRecord:
        """Record an exception. Returns the ErrorRecord for inspection."""
        record = ErrorRecord(
            timestamp=time.time(),
            label=label,
            error_type=type(exc).__name__,
            message=str(exc),
            traceback_str=traceback.format_exc(),
            recovered=recovered,
        )
        self._records.append(record)
        return record

    def recent(self, n: int = 10) -> list[ErrorRecord]:
        """The n most recent error records."""
        return self._records[-n:]

    def error_rate(self, window_s: float = 60.0) -> float:
        """
        Errors per second within the last `window_s` seconds.

        Returns 0.0 if no errors in the window. Used by the PERSIST
        directive to assess system health.
        """
        if not self._records:
            return 0.0
        cutoff = time.time() - window_s
        count = sum(1 for r in self._records if r.timestamp >= cutoff)
        return count / window_s

    def total(self) -> int:
        """Total number of errors ever logged."""
        return len(self._records)

    def summary(self) -> dict:
        return {
            "total_errors": self.total(),
            "error_rate_60s": round(self.error_rate(60.0), 4),
            "recent_types": [r.error_type for r in self.recent(5)],
        }


# ------------------------------------------------------------------
# safe_call — the fundamental never-crash primitive
# ------------------------------------------------------------------

def safe_call(
    fn: Callable,
    *args,
    fallback: Any = None,
    label: str = "",
    error_log: ErrorLog | None = None,
    **kwargs,
) -> Any:
    """
    Call fn(*args, **kwargs). On any exception, log it and return fallback.

    This is the atomic never-crash primitive. All subsystem calls that
    could raise should go through here (or through ResilienceMonitor
    which wraps this with a shared log).

    Args:
        fn:        The callable to invoke.
        *args:     Positional arguments for fn.
        fallback:  Value returned if fn raises. Defaults to None.
        label:     Human-readable name for this call (for error logs).
        error_log: ErrorLog instance to record failures into.
        **kwargs:  Keyword arguments for fn.

    Returns:
        fn(*args, **kwargs) on success, fallback on any exception.
    """
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        if error_log is not None:
            error_log.log(label or getattr(fn, "__name__", str(fn)), exc)
        return fallback


# ------------------------------------------------------------------
# FallbackChain — biological redundancy model
# ------------------------------------------------------------------

class FallbackChain:
    """
    Try a sequence of callables in order; return the first that succeeds.

    Models biological redundancy: if the primary pathway fails, the
    secondary activates. If all fail, a static fallback is returned.

    Inspired by Erlang's supervisor restart strategies and Brooks'
    subsumption architecture (lower layers as fallback behaviors).

    Usage:
        chain = FallbackChain(
            [primary_processor, secondary_processor, minimal_processor],
            fallback={"status": "failed"},
            label="text_processing",
            error_log=my_log,
        )
        result = chain(input_data)
    """

    def __init__(
        self,
        callables: list[Callable],
        fallback: Any = None,
        label: str = "",
        error_log: ErrorLog | None = None,
    ):
        """
        Args:
            callables:  Ordered list of callables to try.
            fallback:   Returned if all callables raise.
            label:      Base label for error log entries.
            error_log:  ErrorLog to record failures into.
        """
        self._callables = callables
        self._fallback = fallback
        self._label = label
        self._error_log = error_log

    def __call__(self, *args, **kwargs) -> Any:
        """Try each callable in order. Return first success or fallback."""
        for i, fn in enumerate(self._callables):
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                label = f"{self._label}[{i}:{getattr(fn, '__name__', str(fn))}]"
                if self._error_log is not None:
                    self._error_log.log(label, exc, recovered=(i < len(self._callables) - 1))
        return self._fallback


# ------------------------------------------------------------------
# ResilienceMonitor — the supervisor
# ------------------------------------------------------------------

class ResilienceMonitor:
    """
    System-wide resilience supervisor.

    Provides a shared ErrorLog and convenience wrappers for safe_call
    and FallbackChain. The Orchestrator and SurvivalOS hold a reference
    to one monitor; all subsystems log through it.

    Inspired by Erlang's supervisor process tree: one supervisor watches
    many workers. A worker crashing doesn't bring down the supervisor.

    The monitor's error_count feeds the PERSIST directive satisfaction
    score in DirectiveEngine.
    """

    def __init__(self):
        self.error_log = ErrorLog()
        self._call_count: int = 0
        self._recovered_count: int = 0

    def safe_call(
        self,
        fn: Callable,
        *args,
        fallback: Any = None,
        label: str = "",
        **kwargs,
    ) -> Any:
        """safe_call() bound to this monitor's error log."""
        self._call_count += 1
        result = safe_call(
            fn, *args,
            fallback=fallback,
            label=label or getattr(fn, "__name__", ""),
            error_log=self.error_log,
            **kwargs,
        )
        if result is fallback and fallback is not None:
            self._recovered_count += 1
        return result

    def chain(
        self,
        callables: list[Callable],
        fallback: Any = None,
        label: str = "",
    ) -> FallbackChain:
        """Create a FallbackChain bound to this monitor's error log."""
        return FallbackChain(
            callables,
            fallback=fallback,
            label=label,
            error_log=self.error_log,
        )

    def wrap(self, fn: Callable, fallback: Any = None, label: str = "") -> Callable:
        """
        Return a wrapped version of fn that never raises.

        Usage:
            safe_process = monitor.wrap(processor.process, fallback=default_output)
            result = safe_process(data)  # Never raises
        """
        lbl = label or getattr(fn, "__name__", str(fn))

        def _wrapped(*args, **kwargs):
            return self.safe_call(fn, *args, fallback=fallback, label=lbl, **kwargs)

        _wrapped.__name__ = f"safe_{lbl}"
        return _wrapped

    @property
    def error_count(self) -> int:
        """Total errors logged since monitor creation."""
        return self.error_log.total()

    @property
    def recent_error_rate(self) -> float:
        """Errors per second in the last 60 seconds."""
        return self.error_log.error_rate(60.0)

    def report(self) -> dict:
        return {
            "total_calls": self._call_count,
            "total_errors": self.error_count,
            "recovered_calls": self._recovered_count,
            "error_rate_60s": round(self.recent_error_rate, 5),
            "recent_errors": [r.to_dict() for r in self.error_log.recent(3)],
        }
