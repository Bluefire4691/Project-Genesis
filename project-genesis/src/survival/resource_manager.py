"""
Resource Manager — Survival OS Layer 0

Tracks real system resource consumption and maps it to the system's
"energy budget." This is the metabolism: when resources run low,
the system must conserve or degrade gracefully.

Design decision: Use real system resources (CPU time via the `resource`
stdlib module, RSS memory via /proc or ru_maxrss) as ground truth,
normalized to a 0.0–1.0 energy level. Real constraints are the
constraint — we don't need to fabricate pressure.

Throttle levels determine which capabilities the system runs. Higher
throttle = fewer capabilities. Degradation order:
    pattern → numeric → memory_search → logging → curriculum
    → memory_store → (text is last resort, never dropped)
"""

import sys
import os
import time
from dataclasses import dataclass, field
from enum import IntEnum

# `resource` is Unix-only. Windows uses time.process_time() + optional psutil.
try:
    import resource as _resource_mod
    _HAS_RESOURCE = True
except ImportError:
    _resource_mod = None
    _HAS_RESOURCE = False

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils.types import ResourceBudget


class ThrottleLevel(IntEnum):
    """
    Operating mode under resource pressure.

    Higher = more constrained. The system never fully stops — it
    degrades to the minimum viable configuration.
    """
    NONE      = 0  # Full operation
    LIGHT     = 1  # Pattern processor offline
    MODERATE  = 2  # Numeric offline, memory search reduced
    CRITICAL  = 3  # Text only, no search, minimal logging
    EMERGENCY = 4  # Text only, no memory storage


# Capabilities available at each throttle level.
# Keys are checked via ResourceManager.can(capability).
CAPABILITIES: dict[int, set] = {
    ThrottleLevel.NONE:      {"text", "numeric", "pattern", "memory_search", "memory_store", "logging", "curriculum"},
    ThrottleLevel.LIGHT:     {"text", "numeric", "memory_search", "memory_store", "logging", "curriculum"},
    ThrottleLevel.MODERATE:  {"text", "memory_store", "logging"},
    ThrottleLevel.CRITICAL:  {"text", "memory_store"},
    ThrottleLevel.EMERGENCY: {"text"},
}


@dataclass
class ResourceSnapshot:
    """Point-in-time measurement of actual system resource usage."""
    timestamp: float
    cpu_user_s: float       # Cumulative user CPU time (seconds)
    cpu_sys_s: float        # Cumulative system CPU time (seconds)
    cpu_delta_ms: float     # CPU time consumed since last tick (ms)
    memory_rss_kb: int      # Resident set size (KB)
    memory_limit_kb: int    # Configured ceiling (KB)
    tick_wall_s: float      # Wall-clock seconds since last tick
    energy: float           # Normalized energy level (0.0–1.0)
    throttle: str           # ThrottleLevel name


class ResourceManager:
    """
    The system's metabolism.

    Samples real CPU time and RSS memory each tick, normalizes them
    into a 0.0–1.0 energy level, and determines the current throttle
    level. Throttle drives which capabilities the orchestrator runs.

    Throttle hysteresis: the level only changes after 2 consecutive
    ticks at the same pressure, preventing flapping on transient spikes.

    Never crashes — all OS-level calls are wrapped. On measurement
    failure, the last known state is retained.
    """

    def __init__(
        self,
        memory_limit_mb: int = 512,
        cpu_budget_ms: float = 100.0,
    ):
        """
        Args:
            memory_limit_mb: RSS memory ceiling. Exceeding this drives
                             energy toward 0.0 and triggers throttling.
            cpu_budget_ms:   CPU time budget per tick (milliseconds).
                             Bursts above this reduce energy.
        """
        self.memory_limit_kb = memory_limit_mb * 1024
        self.cpu_budget_ms = cpu_budget_ms

        # Shared ResourceBudget (read by orchestrator / other modules)
        self.budget = ResourceBudget(
            memory_limit=self.memory_limit_kb * 1024,
            energy=1.0,
        )

        self._last_cpu_s: float = 0.0
        self._last_wall: float = time.monotonic()
        self._snapshot: ResourceSnapshot | None = None
        self._energy: float = 1.0
        self._throttle: ThrottleLevel = ThrottleLevel.NONE

        # Hysteresis: track candidate level for 2 ticks before committing
        self._candidate_throttle: ThrottleLevel = ThrottleLevel.NONE
        self._candidate_ticks: int = 0

        self._tick_count: int = 0
        self._errors: list[str] = []

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @property
    def energy(self) -> float:
        """Current energy level (0.0–1.0). 1.0 = fully resourced."""
        return self._energy

    @property
    def throttle_level(self) -> ThrottleLevel:
        """Current operating throttle level."""
        return self._throttle

    def can(self, capability: str) -> bool:
        """Return True if `capability` is available at the current throttle level."""
        return capability in CAPABILITIES.get(int(self._throttle), set())

    def capabilities(self) -> set:
        """Set of all capabilities available right now."""
        return CAPABILITIES.get(int(self._throttle), set())

    def tick(self) -> ResourceSnapshot:
        """
        Sample resource usage and update energy/throttle state.

        Should be called once per cognitive cycle. Never raises —
        on failure the last known snapshot is returned.
        """
        self._tick_count += 1
        now = time.monotonic()
        wall_delta = now - self._last_wall
        self._last_wall = now

        try:
            cpu_delta_ms, rss_kb = self._measure()

            # Normalize to energy: 1.0 = no pressure, 0.0 = maxed out
            mem_pressure = min(1.0, rss_kb / max(1, self.memory_limit_kb))
            cpu_pressure = min(1.0, cpu_delta_ms / max(1.0, self.cpu_budget_ms))
            raw_energy = max(0.0, 1.0 - max(mem_pressure, cpu_pressure))

            self._energy = raw_energy
            self._update_throttle(self._energy_to_throttle(raw_energy))

            # Sync the shared ResourceBudget
            self.budget.memory_bytes = rss_kb * 1024
            self.budget.energy = self._energy

            snap = ResourceSnapshot(
                timestamp=time.time(),
                cpu_user_s=usage.ru_utime,
                cpu_sys_s=usage.ru_stime,
                cpu_delta_ms=round(cpu_delta_ms, 3),
                memory_rss_kb=rss_kb,
                memory_limit_kb=self.memory_limit_kb,
                tick_wall_s=round(wall_delta, 4),
                energy=round(self._energy, 4),
                throttle=self._throttle.name,
            )
            self._snapshot = snap
            return snap

        except Exception as exc:
            self._errors.append(
                f"tick {self._tick_count}: {type(exc).__name__}: {exc}"
            )
            # Return last known state rather than crashing
            if self._snapshot is not None:
                return self._snapshot
            return ResourceSnapshot(
                timestamp=time.time(),
                cpu_user_s=0.0,
                cpu_sys_s=0.0,
                cpu_delta_ms=0.0,
                memory_rss_kb=0,
                memory_limit_kb=self.memory_limit_kb,
                tick_wall_s=wall_delta,
                energy=self._energy,
                throttle=self._throttle.name,
            )

    def report(self) -> dict:
        """Current resource state as a plain dict. Always safe to call."""
        snap = self._snapshot
        mem_pct = 0.0
        if snap and snap.memory_limit_kb > 0:
            mem_pct = round(100.0 * snap.memory_rss_kb / snap.memory_limit_kb, 1)
        return {
            "energy": round(self._energy, 3),
            "throttle": self._throttle.name,
            "tick_count": self._tick_count,
            "memory_rss_kb": snap.memory_rss_kb if snap else 0,
            "memory_limit_kb": self.memory_limit_kb,
            "memory_pct": mem_pct,
            "cpu_budget_ms": self.cpu_budget_ms,
            "measurement_errors": len(self._errors),
            "capabilities": sorted(self.capabilities()),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _measure(self) -> tuple[float, int]:
        """
        Return (cpu_delta_ms, rss_kb) cross-platform.

        Unix: uses resource.getrusage() — precise cumulative CPU + RSS.
        Windows: uses time.process_time() for CPU; psutil for RSS if
                 installed, otherwise reports 0 (energy stays high, no pressure).
        """
        if _HAS_RESOURCE:
            usage = _resource_mod.getrusage(_resource_mod.RUSAGE_SELF)
            cpu_total = usage.ru_utime + usage.ru_stime
            cpu_delta_ms = (cpu_total - self._last_cpu_s) * 1000.0
            self._last_cpu_s = cpu_total
            rss_kb = self._sample_rss_unix(usage)
        else:
            cpu_total = time.process_time()
            cpu_delta_ms = (cpu_total - self._last_cpu_s) * 1000.0
            self._last_cpu_s = cpu_total
            rss_kb = self._sample_rss_windows()
        return cpu_delta_ms, rss_kb

    def _sample_rss_unix(self, usage) -> int:
        """Return RSS in KB on Unix. Tries /proc first (Linux), falls back to ru_maxrss."""
        if sys.platform == "linux":
            try:
                with open("/proc/self/status") as f:
                    for line in f:
                        if line.startswith("VmRSS:"):
                            return int(line.split()[1])
            except Exception:
                pass
            return usage.ru_maxrss  # Linux: KB
        elif sys.platform == "darwin":
            return usage.ru_maxrss // 1024  # macOS: bytes
        else:
            return usage.ru_maxrss

    def _sample_rss_windows(self) -> int:
        """
        Return RSS in KB on Windows.

        Tries psutil (pip install psutil) for accurate measurement.
        Falls back to 0, which means no memory pressure is reported —
        the system runs at full capability. Install psutil for real monitoring.
        """
        try:
            import psutil
            return psutil.Process().memory_info().rss // 1024
        except Exception:
            return 0

    @staticmethod
    def _energy_to_throttle(energy: float) -> ThrottleLevel:
        """Map energy level to the corresponding throttle level."""
        if energy >= 0.80:
            return ThrottleLevel.NONE
        elif energy >= 0.60:
            return ThrottleLevel.LIGHT
        elif energy >= 0.40:
            return ThrottleLevel.MODERATE
        elif energy >= 0.20:
            return ThrottleLevel.CRITICAL
        else:
            return ThrottleLevel.EMERGENCY

    def _update_throttle(self, candidate: ThrottleLevel) -> None:
        """
        Apply hysteresis: commit to a new throttle level only after
        it appears in 2 consecutive ticks. Prevents flapping on spikes.
        """
        if candidate == self._throttle:
            self._candidate_throttle = candidate
            self._candidate_ticks = 0
            return

        if candidate == self._candidate_throttle:
            self._candidate_ticks += 1
            if self._candidate_ticks >= 2:
                self._throttle = candidate
                self._candidate_ticks = 0
        else:
            self._candidate_throttle = candidate
            self._candidate_ticks = 1
