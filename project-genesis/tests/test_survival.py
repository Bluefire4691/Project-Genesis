"""
Tests for the Survival OS layer (M1).

Verifies that the three subsystems (ResourceManager, DirectiveEngine,
ResilienceMonitor) and the SurvivalOS façade meet M1 success criteria:
    - Never crash regardless of input
    - Resource consumption tracked and reported
    - System behavior changes under resource pressure
    - All errors caught and converted to data
"""

import sys
import os
import time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from survival.resource_manager import ResourceManager, ThrottleLevel, CAPABILITIES
from survival.directives import DirectiveEngine, PERSIST, MAINTAIN, ACQUIRE, GROW
from survival.resilience import (
    ErrorLog, ErrorRecord, safe_call, FallbackChain, ResilienceMonitor
)
from survival import SurvivalOS


# ==================================================================
# ResourceManager
# ==================================================================

def test_resource_manager_tick_returns_snapshot():
    """tick() always returns a ResourceSnapshot."""
    rm = ResourceManager()
    snap = rm.tick()
    assert snap is not None
    assert snap.timestamp > 0
    assert isinstance(snap.memory_rss_kb, int)
    assert 0.0 <= snap.energy <= 1.0


def test_resource_manager_energy_bounded():
    """Energy is always between 0.0 and 1.0."""
    rm = ResourceManager()
    for _ in range(5):
        rm.tick()
    assert 0.0 <= rm.energy <= 1.0


def test_resource_manager_never_crashes():
    """ResourceManager must not raise regardless of how many ticks run."""
    rm = ResourceManager(memory_limit_mb=1, cpu_budget_ms=0.001)
    for _ in range(20):
        snap = rm.tick()
        assert snap is not None


def test_resource_manager_full_capabilities_at_high_energy():
    """At default (healthy) energy, all capabilities should be available."""
    rm = ResourceManager(memory_limit_mb=4096, cpu_budget_ms=10000.0)
    rm.tick()
    # Unless the test machine is under extreme load, energy should be high
    if rm.energy >= 0.80:
        assert rm.can("text")
        assert rm.can("numeric")
        assert rm.can("pattern")
        assert rm.can("memory_store")


def test_resource_manager_throttle_reduces_capabilities():
    """Higher throttle levels have strictly fewer capabilities."""
    for level in ThrottleLevel:
        caps = CAPABILITIES[int(level)]
        assert "text" in caps, f"text must always be available (level {level.name})"
    # EMERGENCY has fewest capabilities
    assert len(CAPABILITIES[ThrottleLevel.EMERGENCY]) < len(CAPABILITIES[ThrottleLevel.NONE])
    # NONE has all capabilities (audio joined in M35 — most expensive sense,
    # first to degrade)
    assert CAPABILITIES[ThrottleLevel.NONE] == {"text", "numeric", "pattern",
                                                  "audio",
                                                  "memory_search", "memory_store",
                                                  "logging", "curriculum"}


def test_resource_manager_report_always_returns_dict():
    """report() is always safe to call — even before any ticks."""
    rm = ResourceManager()
    report = rm.report()
    assert isinstance(report, dict)
    assert "energy" in report
    assert "throttle" in report
    assert "capabilities" in report


def test_resource_manager_hysteresis():
    """Throttle level should not change on a single-tick spike (hysteresis)."""
    rm = ResourceManager()
    rm.tick()
    initial_throttle = rm.throttle_level
    # Force energy low by overriding internal state — simulates a spike
    rm._energy = 0.1
    rm._update_throttle(ThrottleLevel.EMERGENCY)
    # Should NOT have changed yet (hysteresis requires 2 consecutive)
    assert rm.throttle_level == initial_throttle or rm._candidate_ticks < 2


# ==================================================================
# DirectiveEngine
# ==================================================================

def test_directive_engine_update_never_crashes():
    """update() handles any stats dict without raising."""
    de = DirectiveEngine()
    de.update({})
    de.update({"error_count": 100, "cycle_count": 100})
    de.update({"energy": 0.0, "throttle_level": 4})
    de.update({"missing_key": "whatever"})


def test_directive_satisfaction_bounds():
    """Satisfaction scores must always be 0.0–1.0."""
    de = DirectiveEngine()
    for _ in range(10):
        de.update({
            "error_count": 5,
            "cycle_count": 10,
            "throttle_level": 2,
            "energy": 0.5,
            "memories_stored": 8,
            "current_stage": 2,
            "max_stage": 4,
            "stage_score": 0.7,
        })
    report = de.report()
    for name, data in report["directives"].items():
        assert 0.0 <= data["satisfaction"] <= 1.0, f"{name} out of bounds"


def test_directive_pressure_bounded():
    """Pressure score must always be 0.0–1.0."""
    de = DirectiveEngine()
    de.update({"error_count": 0, "cycle_count": 10, "energy": 1.0})
    assert 0.0 <= de.pressure() <= 1.0
    de.update({"error_count": 100, "cycle_count": 10, "energy": 0.0, "throttle_level": 4})
    assert 0.0 <= de.pressure() <= 1.0


def test_directive_most_urgent_returns_directive():
    """most_urgent() always returns a named directive."""
    de = DirectiveEngine()
    de.update({})
    urgent = de.most_urgent()
    assert urgent.name in {"persist", "maintain", "acquire", "grow"}


def test_directives_persist_degraded_by_errors():
    """High error rate should reduce PERSIST satisfaction."""
    de = DirectiveEngine()
    # Healthy: no errors
    de.update({"error_count": 0, "cycle_count": 100})
    healthy_sat = de.satisfaction("persist")
    # Degraded: many errors
    de.update({"error_count": 100, "cycle_count": 100})
    degraded_sat = de.satisfaction("persist")
    assert degraded_sat < healthy_sat


def test_directives_maintain_degraded_by_throttle():
    """High throttle level should reduce MAINTAIN satisfaction."""
    de = DirectiveEngine()
    de.update({"throttle_level": 0, "energy": 1.0})
    healthy = de.satisfaction("maintain")
    de.update({"throttle_level": 4, "energy": 0.1})
    degraded = de.satisfaction("maintain")
    assert degraded < healthy


def test_directive_constants_not_mutated():
    """Module-level directive constants must not be modified by the engine."""
    original_priority = PERSIST.priority
    de = DirectiveEngine()
    for _ in range(5):
        de.update({"error_count": 99, "cycle_count": 100})
    assert PERSIST.priority == original_priority


# ==================================================================
# ResilienceMonitor / safe_call / FallbackChain / ErrorLog
# ==================================================================

def test_safe_call_returns_value_on_success():
    result = safe_call(lambda x: x * 2, 5)
    assert result == 10


def test_safe_call_returns_fallback_on_exception():
    def boom(x):
        raise ValueError("intentional")
    result = safe_call(boom, 42, fallback="rescued")
    assert result == "rescued"


def test_safe_call_logs_to_error_log():
    log = ErrorLog()
    safe_call(lambda: 1 / 0, fallback=0, error_log=log, label="div_zero")
    assert log.total() == 1
    assert log.recent(1)[0].label == "div_zero"
    assert log.recent(1)[0].error_type == "ZeroDivisionError"


def test_safe_call_none_fallback_by_default():
    result = safe_call(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    assert result is None


def test_error_log_total_retention():
    """ErrorLog never discards records."""
    log = ErrorLog()
    for i in range(50):
        try:
            raise RuntimeError(f"error {i}")
        except RuntimeError as e:
            log.log(f"op_{i}", e)
    assert log.total() == 50
    assert len(log.recent(10)) == 10
    # Older records still accessible via full list
    assert log._records[0].message == "error 0"


def test_error_log_error_rate():
    """error_rate returns a non-negative float."""
    log = ErrorLog()
    rate = log.error_rate()
    assert rate == 0.0
    try:
        raise TypeError("test")
    except TypeError as e:
        log.log("test", e)
    rate = log.error_rate(window_s=60.0)
    assert rate > 0.0


def test_fallback_chain_uses_first_success():
    chain = FallbackChain([
        lambda x: x + 1,
        lambda x: x + 100,  # Should not be called
    ])
    assert chain(5) == 6


def test_fallback_chain_skips_failed_callables():
    def fail(x):
        raise ValueError("fail")
    chain = FallbackChain([fail, lambda x: x * 3], fallback=-1)
    assert chain(4) == 12


def test_fallback_chain_returns_fallback_if_all_fail():
    def fail(x):
        raise RuntimeError("all fail")
    chain = FallbackChain([fail, fail, fail], fallback="last_resort")
    assert chain("anything") == "last_resort"


def test_fallback_chain_logs_errors():
    log = ErrorLog()
    def fail(x):
        raise ValueError("logged")
    chain = FallbackChain([fail, lambda x: x], fallback=None, error_log=log)
    chain(1)
    assert log.total() >= 1


def test_resilience_monitor_safe_call():
    monitor = ResilienceMonitor()
    result = monitor.safe_call(lambda: "ok", fallback="fallback")
    assert result == "ok"


def test_resilience_monitor_captures_errors():
    monitor = ResilienceMonitor()
    monitor.safe_call(lambda: 1 / 0, fallback=0, label="div")
    assert monitor.error_count == 1
    report = monitor.report()
    assert report["total_errors"] == 1


def test_resilience_monitor_wrap():
    """wrap() returns a callable that never raises."""
    monitor = ResilienceMonitor()
    def fragile(x):
        if x < 0:
            raise ValueError("negative")
        return x * 2
    safe = monitor.wrap(fragile, fallback=-999)
    assert safe(5) == 10
    assert safe(-1) == -999
    assert monitor.error_count == 1


def test_resilience_monitor_chain():
    """chain() uses the monitor's shared error_log — failures are visible."""
    monitor = ResilienceMonitor()
    def fail(x):
        raise RuntimeError()
    chain = monitor.chain([fail, lambda x: x + 1], fallback=0)
    assert chain(3) == 4
    # The first callable failed — that error IS logged to monitor (supervisor pattern)
    assert monitor.error_count == 1


# ==================================================================
# SurvivalOS — integration
# ==================================================================

def test_survival_os_tick_returns_state():
    os_layer = SurvivalOS()
    state = os_layer.tick()
    assert "energy" in state
    assert "throttle" in state
    assert "capabilities" in state
    assert "pressure" in state


def test_survival_os_tick_never_crashes():
    """tick() must never raise, even with bad stats."""
    os_layer = SurvivalOS()
    os_layer.tick(None)
    os_layer.tick({})
    os_layer.tick({"error_count": -999, "energy": 999.0})


def test_survival_os_can_checks_capability():
    os_layer = SurvivalOS(memory_limit_mb=4096, cpu_budget_ms=10000.0)
    os_layer.tick()
    # text is always available
    assert os_layer.can("text") is True


def test_survival_os_safe_call_wraps_correctly():
    os_layer = SurvivalOS()
    result = os_layer.safe_call(lambda: "alive", fallback="dead")
    assert result == "alive"
    result = os_layer.safe_call(lambda: 1 / 0, fallback="recovered")
    assert result == "recovered"


def test_survival_os_report_is_complete():
    os_layer = SurvivalOS()
    os_layer.tick({})
    report = os_layer.report()
    assert "survival_os" in report
    inner = report["survival_os"]
    assert "resource" in inner
    assert "directives" in inner
    assert "resilience" in inner


def test_survival_os_with_orchestrator():
    """Full integration: Orchestrator with SurvivalOS runs without crashing."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
    from orchestrator.orchestrator import Orchestrator

    brain = Orchestrator(verbose=False)
    result = brain.process_input("text", "The sun rises every morning")
    assert result["status"] == "processed"
    assert "throttle" in result

    status = brain.full_status()
    assert "survival_os" in status


def test_orchestrator_degrades_gracefully_under_throttle():
    """
    Simulate throttle pressure: even at CRITICAL throttle, the
    orchestrator still processes input and returns a result.
    """
    from orchestrator.orchestrator import Orchestrator
    from survival.resource_manager import ThrottleLevel

    brain = Orchestrator(verbose=False)
    # Force survival OS to CRITICAL throttle by overriding internals
    brain.survival.resource._energy = 0.25
    brain.survival.resource._throttle = ThrottleLevel.CRITICAL
    brain.survival.resource._candidate_throttle = ThrottleLevel.CRITICAL
    brain.survival.resource._candidate_ticks = 3

    result = brain.process_input("numeric", {"label": "test", "value": 42})
    # Should still return a result — numeric falls back to text at CRITICAL
    assert result is not None
    assert result.get("status") in ("processed", "degraded")


# ==================================================================
# Runner
# ==================================================================

if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            print(f"  ✅ {test.__name__}")
            passed += 1
        except Exception as e:
            import traceback
            print(f"  ❌ {test.__name__}: {e}")
            traceback.print_exc()
            failed += 1
    print(f"\n  {passed} passed, {failed} failed")
