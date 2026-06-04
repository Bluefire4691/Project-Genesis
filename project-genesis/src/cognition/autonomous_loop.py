"""
Autonomous Cognitive Loop — M20.

Genesis runs between interactions. This module is the difference between
a system that answers questions and an entity that thinks.

What the loop does on each tick, in priority order:
    1. Follow curiosity directives — concepts Genesis knows it doesn't
       understand. Directives are formed when prediction error is high.
       The loop fetches knowledge for the highest-priority directive.
    2. Re-evaluate belief tensions — TENSION/RESIST contradictions that
       need more data to resolve. The loop processes any that can now
       be decided based on accumulated corroboration.
    3. Reflect/consolidate — periodically integrate what has been
       processed. This is the "sleep" pass.

The loop adapts its pace: high prediction error (lots of gaps) →
fetch more aggressively. All relations quiet → back off and reflect.

Architecture:
    - Daemon thread — shuts down cleanly when the host process ends
    - Uses the same Orchestrator instance (SQLite is check_same_thread=False)
    - Has its own session_id so its contributions are tracked separately
       from interactive sessions
    - Activity is logged and queryable
    - Errors are data — a tick failure never stops the loop
"""

import threading
import time
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orchestrator.orchestrator import Orchestrator


# How long to sleep between ticks when there is little to do (seconds)
_IDLE_INTERVAL   = 60.0
# How long to sleep when there is active work (directives, tensions)
_ACTIVE_INTERVAL = 15.0
# Reflect every N ticks regardless of activity
_REFLECT_EVERY   = 6
# Maximum knowledge topics to fetch per tick
_FETCH_TOPICS    = 2
# Maximum tension evaluations per tick
_TENSION_LIMIT   = 5
# Keep only this many activity log entries in memory
_LOG_CAP         = 200


class AutonomousLoop:
    """
    Background cognitive process for Genesis.

    Start with start(). Stop with stop(). Query status with status().
    The loop survives tick failures — errors are data, not stop conditions.

    Parameters
    ----------
    orchestrator : Orchestrator
        The live Genesis brain instance.
    tick_interval : float
        Seconds between ticks when idle. The loop shortens this
        automatically when there is active work to do.
    reflect_every : int
        Number of ticks between consolidation passes.
    verbose : bool
        If True, emit per-tick console output.
    """

    def __init__(
        self,
        orchestrator: "Orchestrator",
        tick_interval: float = _IDLE_INTERVAL,
        reflect_every: int = _REFLECT_EVERY,
        verbose: bool = False,
    ):
        self._orch          = orchestrator
        self._idle_interval = tick_interval
        self._reflect_every = reflect_every
        self._verbose       = verbose

        self._running       = False
        self._thread: threading.Thread | None = None
        self._tick_count    = 0
        self._activity_log: list[dict] = []
        self._lock          = threading.Lock()

        # Autonomous session — separate from interactive sessions so
        # provenance is always distinguishable
        self.session_id = f"auto-{str(uuid.uuid4())[:8]}"

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background cognitive loop."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._loop,
            name="GenesisAutonomousLoop",
            daemon=True,       # dies with the host process — no cleanup needed
        )
        self._thread.start()
        if self._verbose:
            print(f"  [AUTO] Loop started (session={self.session_id})")

    def stop(self, timeout: float = 5.0) -> None:
        """Signal the loop to stop and wait for the current tick to finish."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        if self._verbose:
            print(f"  [AUTO] Loop stopped after {self._tick_count} ticks")

    @property
    def is_running(self) -> bool:
        return self._running and (self._thread is not None and self._thread.is_alive())

    # ------------------------------------------------------------------
    # Core loop
    # ------------------------------------------------------------------

    def _loop(self) -> None:
        while self._running:
            interval = self._idle_interval
            try:
                active = self._tick()
                interval = _ACTIVE_INTERVAL if active else self._idle_interval
            except Exception as e:
                self._log_activity({"error": str(e)})
            # Sleep in small increments so stop() is responsive
            deadline = time.time() + interval
            while self._running and time.time() < deadline:
                time.sleep(min(1.0, deadline - time.time()))

    def _tick(self) -> bool:
        """
        One cognitive unit of work.

        Returns True if Genesis did something substantive (active work
        found), False if it was quiet (no directives, no tensions).
        """
        self._tick_count += 1
        t = time.time()
        actions: list[dict] = []
        active = False

        # ── Priority 1: Follow curiosity directives ──────────────────
        try:
            directives = self._orch.curiosity_directives()
        except Exception:
            directives = []
        if directives:
            active = True
            try:
                result = self._orch.fetch_knowledge(
                    n_topics=_FETCH_TOPICS, verbose=self._verbose
                )
                fetched = result.get("topics_processed", 0)
                actions.append({
                    "type":       "curiosity",
                    "directives": directives[:3],
                    "fetched":    fetched,
                })
                if self._verbose and fetched:
                    print(f"  [AUTO tick={self._tick_count}] "
                          f"Followed {len(directives)} directive(s) → "
                          f"fetched {fetched} topic(s)")
            except Exception as e:
                actions.append({"type": "curiosity", "error": str(e)})

        # ── Priority 1b: Pattern-transfer curiosity ───────────────────
        # Concepts that play a structural role but lack expected edges
        # (e.g., a REGULATOR with no CAUSES edge) get added as directives.
        try:
            pt_targets = self._orch.pattern_transfer.curiosity_from_analogs()
            for concept in pt_targets:
                if (concept not in self._orch._curiosity_directives
                        and len(self._orch._curiosity_directives)
                        < self._orch._MAX_DIRECTIVES):
                    self._orch._curiosity_directives[concept] = 0.85
            if pt_targets:
                actions.append({"type": "pattern_curiosity", "targets": pt_targets})
        except Exception:
            pass

        # ── Priority 2: Re-evaluate belief tensions ───────────────────
        try:
            tensions = self._orch.belief_revision.pending_tensions(limit=_TENSION_LIMIT)
            if tensions:
                active = True
                revised = self._orch.belief_revision.evaluate_and_revise(
                    session_id=self.session_id
                )
                if revised:
                    actions.append({
                        "type":    "revision",
                        "revised": revised,
                        "pending": len(tensions),
                    })
                    if self._verbose:
                        print(f"  [AUTO tick={self._tick_count}] "
                              f"Revised {revised} belief(s) from {len(tensions)} tension(s)")
        except Exception as e:
            actions.append({"type": "revision", "error": str(e)})

        # ── Priority 3: Periodic reflection ───────────────────────────
        if self._tick_count % self._reflect_every == 0:
            try:
                self._orch.reflect()
                actions.append({"type": "reflection", "tick": self._tick_count})
                if self._verbose:
                    print(f"  [AUTO tick={self._tick_count}] Reflected")
            except Exception as e:
                actions.append({"type": "reflection", "error": str(e)})

        self._log_activity({
            "tick":     self._tick_count,
            "at":       t,
            "active":   active,
            "actions":  actions,
            "directives": len(directives) if directives else 0,
        })

        return active

    # ------------------------------------------------------------------
    # Activity log
    # ------------------------------------------------------------------

    def _log_activity(self, entry: dict) -> None:
        with self._lock:
            self._activity_log.append(entry)
            if len(self._activity_log) > _LOG_CAP:
                self._activity_log = self._activity_log[-_LOG_CAP:]

    def activity_log(self, limit: int = 20) -> list[dict]:
        """Recent autonomous activity — what Genesis has been doing."""
        with self._lock:
            return list(self._activity_log[-limit:])

    def last_active_at(self) -> float | None:
        """Timestamp of the last tick that did substantive work."""
        with self._lock:
            for entry in reversed(self._activity_log):
                if entry.get("active"):
                    return entry.get("at")
        return None

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def status(self) -> dict:
        recent = self.activity_log(limit=5)
        total_revised  = sum(
            a.get("revised", 0)
            for e in self._activity_log
            for a in e.get("actions", [])
            if a.get("type") == "revision"
        )
        total_fetched  = sum(
            a.get("fetched", 0)
            for e in self._activity_log
            for a in e.get("actions", [])
            if a.get("type") == "curiosity"
        )
        total_reflects = sum(
            1
            for e in self._activity_log
            for a in e.get("actions", [])
            if a.get("type") == "reflection"
        )
        return {
            "running":          self.is_running,
            "session_id":       self.session_id,
            "tick_count":       self._tick_count,
            "idle_interval_s":  self._idle_interval,
            "active_interval_s": _ACTIVE_INTERVAL,
            "reflect_every":    self._reflect_every,
            "total_fetched":    total_fetched,
            "total_revised":    total_revised,
            "total_reflects":   total_reflects,
            "last_active_at":   self.last_active_at(),
            "recent_activity":  recent,
        }

    def tick_once(self) -> bool:
        """
        Run exactly one tick synchronously — for tests and manual stepping.
        Does not require start() to have been called.
        """
        return self._tick()
